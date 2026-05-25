"""
共用训练器

统一的训练循环，支持:
- AMP
- WeightedRandomSampler / FocalLoss / Class-Balanced Loss
- CosineAnnealing / OneCycleLR
- Early Stopping
- Gradient Accumulation
- 自动日志 & 模型保存
"""

import os
import json
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import DataLoader, WeightedRandomSampler
from lib.datasets import PatientSampler
from torch.optim.lr_scheduler import CosineAnnealingLR, OneCycleLR
from torch.cuda.amp import autocast, GradScaler
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import (accuracy_score, roc_auc_score, f1_score,
                             confusion_matrix, recall_score, precision_score)
from collections import Counter
from datetime import datetime
import logging
import time


# ============================================================
# Focal Loss
# ============================================================
class FocalLoss(nn.Module):
    def __init__(self, alpha=None, gamma=2.0, reduction='mean'):
        super().__init__()
        self.alpha = alpha  # class weights (tensor)
        self.gamma = gamma
        self.reduction = reduction

    def forward(self, inputs, targets):
        ce = nn.functional.cross_entropy(inputs, targets, weight=self.alpha, reduction='none')
        pt = torch.exp(-ce)
        focal = ((1 - pt) ** self.gamma) * ce
        if self.reduction == 'mean':
            return focal.mean()
        return focal.sum()


# ============================================================
# Ordinal Loss: CE + distance penalty (T1<T2<T3<T4)
# ============================================================
class OrdinalAwareLoss(nn.Module):
    """CE + Ordinal distance penalty.
    
    For ordinal classification (T1<T2<T3<T4), adds a penalty
    based on the expected distance between predicted and true ranks.
    
    L = CE(logits, y, weight) + lambda * E_p[|pred_rank - true_rank|]
    
    class_weight: 如果提供，传给 CE 做类别加权（对抗不均衡数据）
    """
    def __init__(self, num_classes=4, lambda_ord=0.5, label_smoothing=0.0,
                 class_weight=None):
        super().__init__()
        self.num_classes = num_classes
        self.lambda_ord = lambda_ord
        self.ce = nn.CrossEntropyLoss(weight=class_weight,
                                       label_smoothing=label_smoothing)
        ranks = torch.arange(num_classes, dtype=torch.float32)
        self.register_buffer('ranks', ranks)
    
    def forward(self, logits, targets):
        ce_loss = self.ce(logits, targets)
        probs = torch.softmax(logits.float(), dim=1)
        true_ranks = self.ranks[targets].unsqueeze(1)
        pred_ranks = self.ranks.unsqueeze(0)
        distances = torch.abs(pred_ranks - true_ranks)
        expected_distance = (probs * distances).sum(dim=1).mean()
        return ce_loss + self.lambda_ord * expected_distance


# ============================================================
# CORAL Loss (Consistent Rank Logits)
# ============================================================
class CORALLoss(nn.Module):
    """
    CORAL Loss for ordinal regression.
    The targets are integers in {0, ..., num_classes-1}.
    We convert them to binary labels of shape (num_classes-1).
    E.g. for num_classes=4:
    y=0 (T1)  -> [0, 0, 0]
    y=1 (T2)  -> [1, 0, 0]
    y=2 (T3)  -> [1, 1, 0]
    y=3 (T4+) -> [1, 1, 1]
    """
    def __init__(self, num_classes=4):
        super().__init__()
        self.num_classes = num_classes
    
    def forward(self, logits, targets):
        levels = []
        for i in range(self.num_classes - 1):
            levels.append((targets > i).float())
        levels = torch.stack(levels, dim=1)
        return F.binary_cross_entropy_with_logits(logits, levels)


# ============================================================
# Multi-task Loss: 主头 + 层级二分类辅助头
# ============================================================
class MultitaskLoss(nn.Module):
    """层级二分类辅助任务损失，用于改善 T2 学习。
    
    辅助任务分解（T1<T2<T3<T4+ 分期）：
      Aux-1 (early_late): T1+T2(0) vs T3+T4+(1)
            → 约束模型学习"外层是否破坏"这一关键视觉特征
            → 使 T2 稳定地落在"早期"侧，不被混淆进 T3+T4+
      Aux-2 (t1_vs_t2):   T1(0) vs T2(1)，仅对 T1/T2 样本计算
            → 专项训练"肌层侵犯"特征
            → 使 T2 从 T1 侧获得正向约束，而不只是被 T3 推开
      Aux-3 (t3_vs_t4):   T3(0) vs T4+(1)，仅对 T3/T4+ 样本计算
            → 专项训练"外侵程度"特征
    
    Loss = main_loss
         + lambda_binary * BCE_early_late(all samples)
         + lambda_t1t2   * BCE_T1vsT2(T1/T2 samples only)
         + lambda_t3t4   * BCE_T3vsT4(T3/T4 samples only)
    """
    def __init__(self, main_criterion, lambda_binary=0.3, lambda_t1t2=0.5,
                 lambda_t3t4=0.3):
        super().__init__()
        self.main_criterion = main_criterion
        self.lambda_binary = lambda_binary
        self.lambda_t1t2 = lambda_t1t2
        self.lambda_t3t4 = lambda_t3t4

    def forward(self, outputs, targets):
        if isinstance(outputs, dict):
            main_logits = outputs['main']
            aux_binary  = outputs['aux_binary']   # (B,) logits
            aux_t1t2    = outputs['aux_t1t2']     # (B,) logits
            aux_t3t4    = outputs.get('aux_t3t4')
        else:
            # 兼容：如果模型不是 multitask 模式
            return self.main_criterion(outputs, targets)

        main_loss = self.main_criterion(main_logits, targets)

        # Aux-1: T1+T2(0) vs T3+T4+(1)
        early_late_labels = (targets >= 2).float()
        aux1_loss = F.binary_cross_entropy_with_logits(aux_binary, early_late_labels)

        # Aux-2: T1(0) vs T2(1) — 只对 T1/T2 样本计算
        mask = targets <= 1
        if mask.sum() > 1:
            t1t2_labels = targets[mask].float()   # T1=0, T2=1
            aux2_loss = F.binary_cross_entropy_with_logits(
                aux_t1t2[mask], t1t2_labels)
        else:
            aux2_loss = torch.tensor(0.0, device=targets.device)

        if aux_t3t4 is not None:
            mask34 = targets >= 2
            if mask34.sum() > 1:
                t3t4_labels = (targets[mask34] - 2).float()  # T3=0, T4+=1
                aux3_loss = F.binary_cross_entropy_with_logits(
                    aux_t3t4[mask34], t3t4_labels)
            else:
                aux3_loss = torch.tensor(0.0, device=targets.device)
        else:
            aux3_loss = torch.tensor(0.0, device=targets.device)

        return (main_loss
                + self.lambda_binary * aux1_loss
                + self.lambda_t1t2   * aux2_loss
                + self.lambda_t3t4   * aux3_loss)


class BoundaryAwareLoss(nn.Module):
    """Main classification loss plus ordinal threshold supervision.

    This adds three adjacent boundary objectives:
      - target > 0: T1 vs T2/T3/T4+
      - target > 1: T1/T2 vs T3/T4+
      - target > 2: T1/T2/T3 vs T4+

    It keeps the 4-class head unchanged but encourages smoother, clinically
    meaningful separation around T2/T3/T4 boundaries.
    """
    def __init__(self, main_criterion, lambda_boundary=0.15,
                 boundary_weights=None):
        super().__init__()
        self.main_criterion = main_criterion
        self.lambda_boundary = float(lambda_boundary)
        self.boundary_weights = boundary_weights or [0.5, 1.0, 1.0]

    def forward(self, outputs, targets):
        logits = outputs['main'] if isinstance(outputs, dict) else outputs
        main_loss = self.main_criterion(logits, targets)
        probs = torch.softmax(logits.float(), dim=1)
        losses = []
        for threshold, weight in enumerate(self.boundary_weights):
            pos_prob = probs[:, threshold + 1:].sum(dim=1).clamp(1e-6, 1 - 1e-6)
            pos_logit = torch.logit(pos_prob)
            boundary_label = (targets > threshold).float()
            losses.append(float(weight) * F.binary_cross_entropy_with_logits(pos_logit, boundary_label))
        if not losses:
            return main_loss
        return main_loss + self.lambda_boundary * torch.stack(losses).mean()


class AsymmetricCostAuxLoss(nn.Module):
    """Add clinical cost penalty on top of any main loss (ordinal + boundary, etc.)."""

    def __init__(self, main_criterion, cost_matrix, lambda_cost=0.35):
        super().__init__()
        self.main_criterion = main_criterion
        self.lambda_cost = float(lambda_cost)
        self.register_buffer("cost_matrix", cost_matrix.float())

    def forward(self, logits, targets):
        main_loss = self.main_criterion(logits, targets)
        probs = torch.softmax(logits.float(), dim=1)
        costs = self.cost_matrix[targets]
        penalty = (probs * costs).sum(dim=1).mean()
        return main_loss + self.lambda_cost * penalty


# ============================================================
# Asymmetric Cost-Sensitive Loss (临床代价驱动)
# ============================================================
class AsymmetricCostLoss(nn.Module):
    """基于临床误判代价矩阵的非对称损失。
    
    T 分期误判的临床后果不对称：
      - T2→T1（漏掉手术）远比 T2→T3（多做化疗）严重
      - T3→T2（漏掉化疗）比 T3→T4（轻微过度）严重
    
    实现：CE loss + 代价加权的 soft penalty
      penalty = sum_j [ cost(y, j) * p(j) ]  (对错误类别的预测概率按代价加权)
    
    Args:
        cost_matrix: (C, C) tensor, cost_matrix[i][j] = 将真实类 i 误判为 j 的代价
        lambda_cost: penalty 权重
        class_weight: 可选的类别频率权重（传给 CE）
        label_smoothing: CE 的 label smoothing
    """
    def __init__(self, cost_matrix, lambda_cost=1.0, class_weight=None,
                 label_smoothing=0.0):
        super().__init__()
        self.lambda_cost = lambda_cost
        self.ce = nn.CrossEntropyLoss(weight=class_weight,
                                       label_smoothing=label_smoothing)
        self.register_buffer('cost_matrix', cost_matrix)
    
    def forward(self, logits, targets):
        ce_loss = self.ce(logits, targets)
        
        probs = torch.softmax(logits.float(), dim=1)  # (B, C)
        costs = self.cost_matrix[targets]              # (B, C)
        penalty = (probs * costs).sum(dim=1).mean()
        
        return ce_loss + self.lambda_cost * penalty


# ============================================================
# Attention Guidance Loss
# ============================================================
class AttentionGuidanceLoss(nn.Module):
    """引导 backbone feature map 的激活聚焦到病灶边界区域。
    
    将 feature map 沿 channel 维度取 L2-norm → spatial attention map，
    然后用 GT mask 的 border target（dilate - erode）作为监督信号。
    
    推理时完全不需要 mask，只是训练时多一个 loss 项。
    """
    def __init__(self, lambda_attn=0.5):
        super().__init__()
        self.lambda_attn = lambda_attn

    def forward(self, feat_map, border_target):
        """
        Args:
            feat_map: (B, C, H, W) backbone 最后一层输出
            border_target: (B, H', W') GT mask border attention target
        Returns:
            attention guidance loss (scalar)
        """
        if feat_map is None:
            return torch.tensor(0.0, requires_grad=False)
        
        attn = torch.norm(feat_map.float(), dim=1)  # (B, H, W)
        
        if attn.shape[-2:] != border_target.shape[-2:]:
            border_target = F.interpolate(
                border_target.unsqueeze(1),
                size=attn.shape[-2:],
                mode='bilinear',
                align_corners=False
            ).squeeze(1)
        
        attn_min = attn.amin(dim=(-2, -1), keepdim=True)
        attn_max = attn.amax(dim=(-2, -1), keepdim=True)
        attn_norm = (attn - attn_min) / (attn_max - attn_min + 1e-6)
        
        has_target = border_target.sum(dim=(-2, -1)) > 0
        if has_target.sum() == 0:
            return torch.tensor(0.0, device=feat_map.device, requires_grad=False)
        
        loss = F.mse_loss(
            attn_norm[has_target],
            border_target[has_target],
            reduction='mean'
        )
        
        return self.lambda_attn * loss


# ============================================================
# Mixup utility
# ============================================================
def mixup_data(x, y, alpha=0.2):
    """Mixup augmentation"""
    if alpha > 0:
        lam = np.random.beta(alpha, alpha)
    else:
        lam = 1.0
    batch_size = x.size(0)
    index = torch.randperm(batch_size, device=x.device)
    mixed_x = lam * x + (1 - lam) * x[index]
    y_a, y_b = y, y[index]
    return mixed_x, y_a, y_b, lam


def mixup_criterion(criterion, pred, y_a, y_b, lam):
    """Mixup loss"""
    return lam * criterion(pred, y_a) + (1 - lam) * criterion(pred, y_b)


# ============================================================
# EMA (Exponential Moving Average)
# ============================================================
class ModelEMA:
    """Exponential moving average of model parameters and buffers."""
    def __init__(self, model, decay=0.999):
        import copy
        self.ema_model = copy.deepcopy(model)
        self.ema_model.eval()
        self.decay = decay
        for p in self.ema_model.parameters():
            p.requires_grad_(False)
    
    def update(self, model):
        with torch.no_grad():
            for ema_p, model_p in zip(self.ema_model.parameters(), model.parameters()):
                ema_p.data.mul_(self.decay).add_(model_p.data, alpha=1 - self.decay)
            for ema_b, model_b in zip(self.ema_model.buffers(), model.buffers()):
                ema_b.data.copy_(model_b.data)
    
    def state_dict(self):
        return self.ema_model.state_dict()


# ============================================================
# Trainer
# ============================================================
class Trainer:
    """统一训练器
    
    Example:
        trainer = Trainer(config)
        trainer.fit(model, train_dataset, val_dataset)
        results = trainer.test(test_dataset)
    """
    
    def __init__(self, config):
        """
        config dict keys:
            output_dir, epochs, lr, weight_decay, batch_size, 
            num_workers, label_smoothing, early_stopping, 
            scheduler ('cosine'|'onecycle'), loss ('ce'|'focal'),
            accumulation_steps, gpu, seed
        """
        self.config = config
        self.output_dir = Path(config.get('output_dir', 'results'))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.device = torch.device(f"cuda" if torch.cuda.is_available() else "cpu")
        self.use_amp = config.get('amp', True)
        self.scaler = GradScaler(enabled=self.use_amp)
        
        # Logger
        self.logger = logging.getLogger('Trainer')
        self.logger.setLevel(logging.INFO)
        self.logger.handlers = []
        fh = logging.FileHandler(self.output_dir / 'training.log', mode='w', encoding='utf-8')
        ch = logging.StreamHandler()
        fmt = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        fh.setFormatter(fmt)
        ch.setFormatter(fmt)
        self.logger.addHandler(fh)
        self.logger.addHandler(ch)
    
    def _create_sampler(self, dataset):
        """创建采样器：支持患者级采样和普通加权采样
        
        如果配置了 patient_sampling 且 CSV 含 patient_id_unique 列，使用 PatientSampler；
        否则退回到 WeightedRandomSampler。
        MultiFrameDataset 已经是按患者打包的，返回 None 让 DataLoader 用默认 shuffle。
        """
        from lib.datasets import MultiFrameDataset
        if isinstance(dataset, MultiFrameDataset):
            labels = [dataset.patient_labels[p] for p in dataset.patients]
            counts = Counter(labels)
            weights = {c: 1.0 / n for c, n in counts.items()}
            sample_weights = [weights[l] for l in labels]
            self.logger.info(f"  MultiFrameDataset: {len(dataset)} patients, K={dataset.K}, "
                           f"class counts: {dict(counts)}")
            return WeightedRandomSampler(sample_weights, len(sample_weights))

        use_patient = self.config.get('patient_sampling', False)
        pid_col = 'patient_id_unique' if 'patient_id_unique' in dataset.df.columns else 'patient_id'
        
        if use_patient and pid_col in dataset.df.columns:
            K = self.config.get('max_frames_per_patient', 3)
            balanced = self.config.get('class_balanced_sampling', True)
            class_boost = self.config.get('class_boost')
            sampler = PatientSampler(
                dataset,
                max_frames_per_patient=K,
                class_balanced=balanced,
                class_boost=class_boost,
            )
            boost_msg = f", class_boost={class_boost}" if class_boost else ""
            self.logger.info(
                f"  PatientSampler: K={K}, balanced={balanced}{boost_msg}, "
                f"patients={len(sampler.patients)}, epoch_size≈{len(sampler)}"
            )
            return sampler
        else:
            labels = dataset.df['label'].values
            counts = Counter(labels)
            weights = {c: 1.0 / n for c, n in counts.items()}
            sample_weights = [weights[l] for l in labels]
            return WeightedRandomSampler(sample_weights, len(sample_weights))

    def _criterion_inputs(self, criterion, outputs):
        if isinstance(criterion, MultitaskLoss):
            return outputs
        if isinstance(outputs, dict):
            return outputs.get('main', outputs.get('logits'))
        return outputs
    
    def _build_class_weights(self, num_classes, class_counts):
        """构建类别权重 tensor。
        
        优先级:
          1. class_weights: [w0, w1, ...] — 手动指定（直接使用，归一化到mean=1）
          2. class_counts + focal_power  — 自动逆频率权重，power 控制强度
               power=1.0: w_i = total/(n_classes * count_i) （标准逆频率）
               power=0.5: sqrt of above （更温和）
               power=0.0: 均匀权重
        """
        manual = self.config.get('class_weights')
        if manual is not None:
            w = torch.tensor(manual, dtype=torch.float32)
            w = w / w.mean()
            return w.to(self.device)
        
        if class_counts:
            power = self.config.get('focal_power', 1.0)
            total = sum(class_counts.values())
            raw = [total / (num_classes * class_counts[i]) for i in range(num_classes)]
            w = torch.tensor([r ** power for r in raw], dtype=torch.float32)
            w = w / w.mean()
            return w.to(self.device)
        
        return None

    def _create_criterion(self, num_classes, class_counts=None):
        loss_type = self.config.get('loss', 'ce')
        label_smoothing = self.config.get('label_smoothing', 0.0)
        
        if loss_type == 'focal':
            alpha = self._build_class_weights(num_classes, class_counts)
            gamma = self.config.get('focal_gamma', 2.0)
            base = FocalLoss(alpha=alpha, gamma=gamma)
        elif loss_type == 'weighted_ce':
            weight = self._build_class_weights(num_classes, class_counts)
            base = nn.CrossEntropyLoss(weight=weight, label_smoothing=label_smoothing)
        elif loss_type == 'ordinal':
            lambda_ord = self.config.get('lambda_ord', 0.5)
            weight = self._build_class_weights(num_classes, class_counts)
            base = OrdinalAwareLoss(num_classes=num_classes, lambda_ord=lambda_ord,
                                   label_smoothing=label_smoothing,
                                   class_weight=weight).to(self.device)
        elif loss_type == 'coral':
            base = CORALLoss(num_classes=num_classes).to(self.device)
        elif loss_type == 'asymmetric':
            cost_cfg = self.config.get('cost_matrix')
            if cost_cfg is not None:
                cost_mat = torch.tensor(cost_cfg, dtype=torch.float32)
            else:
                # 默认 4-class T 分期临床代价矩阵
                cost_mat = torch.tensor([
                    [0.0, 2.0, 1.0, 1.0],   # T1: 过度治疗
                    [5.0, 0.0, 1.5, 1.5],   # T2: 漏掉手术代价最高
                    [2.0, 3.0, 0.0, 1.0],   # T3: 漏掉化疗
                    [2.0, 2.0, 2.0, 0.0],   # T4: 漏掉联合切除
                ], dtype=torch.float32)
            lambda_cost = self.config.get('lambda_cost', 0.5)
            weight = self._build_class_weights(num_classes, class_counts)
            base = AsymmetricCostLoss(
                cost_matrix=cost_mat, lambda_cost=lambda_cost,
                class_weight=weight, label_smoothing=label_smoothing
            ).to(self.device)
        else:
            base = nn.CrossEntropyLoss(label_smoothing=label_smoothing)
        
        if self.config.get('boundary_aware_loss', False):
            base = BoundaryAwareLoss(
                base,
                lambda_boundary=self.config.get('lambda_boundary', 0.15),
                boundary_weights=self.config.get('boundary_weights', [0.5, 1.0, 1.0]),
            )

        if self.config.get('asymmetric_cost_aux', False):
            cost_cfg = self.config.get('cost_matrix')
            if cost_cfg is not None:
                cost_mat = torch.tensor(cost_cfg, dtype=torch.float32)
            else:
                cost_mat = torch.tensor(
                    [
                        [0.0, 2.0, 1.0, 1.0],
                        [5.0, 0.0, 1.5, 1.5],
                        [2.0, 3.0, 0.0, 1.0],
                        [2.0, 2.0, 2.0, 0.0],
                    ],
                    dtype=torch.float32,
                )
            base = AsymmetricCostAuxLoss(
                base,
                cost_matrix=cost_mat,
                lambda_cost=self.config.get('lambda_asym_cost', 0.35),
            ).to(self.device)

        # 若开启 multitask，包装为 MultitaskLoss
        if self.config.get('multitask', False):
            lambda_binary = self.config.get('lambda_binary',
                            self.config.get('lambda_aux_binary', 0.3))
            lambda_t1t2   = self.config.get('lambda_t1t2',
                            self.config.get('lambda_aux_t1t2', 0.5))
            lambda_t3t4   = self.config.get('lambda_t3t4',
                            self.config.get('lambda_aux_t3t4', 0.3))
            return MultitaskLoss(base, lambda_binary=lambda_binary,
                                 lambda_t1t2=lambda_t1t2,
                                 lambda_t3t4=lambda_t3t4).to(self.device)
        return base
    
    @torch.no_grad()
    def _calibrate_bn(self, model, loader, max_batches=50):
        """Reset and recalibrate BatchNorm running stats for EMA weights."""
        # Reset all BN running stats
        for m in model.modules():
            if isinstance(m, (nn.BatchNorm1d, nn.BatchNorm2d, nn.SyncBatchNorm)):
                m.reset_running_stats()

        model.train()
        for i, batch in enumerate(loader):
            if i >= max_batches:
                break
            self._forward_model(model, batch)
        model.eval()
        self.logger.info(f"  BN calibration: {min(i + 1, max_batches)} batches")

    def _train_one_epoch(self, model, loader, optimizer, criterion):
        model.train()
        total_loss = 0
        total_attn_loss = 0
        accum = self.config.get('gradient_accumulation', 1)
        use_attn_guide = self.config.get('attention_guidance', False)
        optimizer.zero_grad()
        
        n_batches = len(loader)
        for i, batch in enumerate(loader):
            labels = batch['label'].to(self.device)
            
            with autocast(enabled=self.use_amp):
                outputs = self._forward_model(model, batch)
                loss_inputs = self._criterion_inputs(criterion, outputs)
                loss = criterion(loss_inputs, labels) / accum
                
                if use_attn_guide and isinstance(outputs, dict) and 'g_feat_map' in outputs:
                    border_target = batch.get('border_target')
                    if border_target is not None:
                        border_target = border_target.to(self.device)
                        attn_loss = self._attn_guide_loss(
                            outputs['g_feat_map'], border_target) / accum
                        loss = loss + attn_loss
                        total_attn_loss += attn_loss.item() * accum
            
            self.scaler.scale(loss).backward()
            
            is_last = (i + 1) == n_batches
            if (i + 1) % accum == 0 or is_last:
                self.scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 
                                                max_norm=self.config.get('grad_clip', 1.0))
                self.scaler.step(optimizer)
                self.scaler.update()
                optimizer.zero_grad()
                if hasattr(self, 'ema') and self.ema is not None:
                    self.ema.update(model)
            
            total_loss += loss.item() * accum
        
        return total_loss / n_batches

    def _forward_model(self, model, batch):
        """统一的前向传播：自动识别 multi_frame / dual / multimodal / single 格式"""
        if 'images' in batch:
            imgs = batch['images'].to(self.device)
            mask = batch.get('mask')
            if mask is not None:
                mask = mask.to(self.device)
            c = batch.get('clinical')
            if c is not None:
                c = c.to(self.device)
            return model(imgs, mask=mask, clinical=c)
        elif 'global_image' in batch:
            g = batch['global_image'].to(self.device)
            l = batch['local_image'].to(self.device)
            b = batch.get('boundary_image')
            if b is not None:
                b = b.to(self.device)
            c = batch.get('clinical')
            if c is not None:
                c = c.to(self.device)
            if b is not None:
                return model(g, l, b, c)
            return model(g, l, c)
        elif 'us_image' in batch and 'pathology_images' in batch:
            us = batch['us_image'].to(self.device)
            pathology = batch['pathology_images'].to(self.device)
            pathology_mask = batch.get('pathology_mask')
            if pathology_mask is not None:
                pathology_mask = pathology_mask.to(self.device)
            c = batch.get('clinical')
            if c is not None:
                c = c.to(self.device)
            return model(us, pathology, pathology_mask, c)
        elif 'clinical' in batch and 'image' in batch:
            images = batch['image'].to(self.device)
            c = batch['clinical'].to(self.device)
            return model(images, c)
        elif 'clinical' in batch:
            c = batch['clinical'].to(self.device)
            return model(c)
        else:
            images = batch['image'].to(self.device)
            return model(images)

    def _train_one_epoch_mixup(self, model, loader, optimizer, criterion, alpha=0.2):
        """训练一个epoch, 带Mixup增强（支持单分支/双分支/多模态）"""
        model.train()
        total_loss = 0
        accum = self.config.get('gradient_accumulation', 1)
        optimizer.zero_grad()
        
        n_batches = len(loader)
        for i, batch in enumerate(loader):
            labels = batch['label'].to(self.device)
            is_multi_frame = 'images' in batch
            is_dual = 'global_image' in batch
            is_tri = is_dual and 'boundary_image' in batch
            is_us_pathology = 'us_image' in batch and 'pathology_images' in batch
            is_multimodal = 'clinical' in batch and 'image' in batch and not is_dual and not is_multi_frame
            is_clinical_only = 'clinical' in batch and 'image' not in batch and not is_dual and not is_multi_frame
            
            if is_multi_frame:
                imgs = batch['images'].to(self.device)
                mask = batch.get('mask')
                if mask is not None:
                    mask = mask.to(self.device)
                c = batch.get('clinical')
                if c is not None:
                    c = c.to(self.device)
                B = imgs.size(0)
                perm = torch.randperm(B, device=imgs.device)
                lam = np.random.beta(alpha, alpha)
                mixed = lam * imgs + (1 - lam) * imgs[perm]
                y_a, y_b = labels, labels[perm]
                with autocast(enabled=self.use_amp):
                    outputs = model(mixed, mask=mask, clinical=c)
            elif is_dual:
                g = batch['global_image'].to(self.device)
                l = batch['local_image'].to(self.device)
                g, y_a, y_b, lam = mixup_data(g, labels, alpha)
                l = lam * l + (1 - lam) * l[torch.randperm(l.size(0), device=l.device)]
                b = batch.get('boundary_image')
                if b is not None:
                    b = b.to(self.device)
                    perm = torch.randperm(b.size(0), device=b.device)
                    b = lam * b + (1 - lam) * b[perm]
                c = batch.get('clinical')
                if c is not None:
                    c = c.to(self.device)
                with autocast(enabled=self.use_amp):
                    if is_tri:
                        outputs = model(g, l, b, c)
                    else:
                        outputs = model(g, l, c)
            elif is_us_pathology:
                us = batch['us_image'].to(self.device)
                pathology = batch['pathology_images'].to(self.device)
                pathology_mask = batch.get('pathology_mask')
                if pathology_mask is not None:
                    pathology_mask = pathology_mask.to(self.device)
                c = batch.get('clinical')
                if c is not None:
                    c = c.to(self.device)
                us, y_a, y_b, lam = mixup_data(us, labels, alpha)
                perm = torch.randperm(pathology.size(0), device=pathology.device)
                pathology = lam * pathology + (1 - lam) * pathology[perm]
                if pathology_mask is not None:
                    pathology_mask = pathology_mask | pathology_mask[perm]
                if c is not None:
                    c = lam * c + (1 - lam) * c[perm]
                with autocast(enabled=self.use_amp):
                    outputs = model(us, pathology, pathology_mask, c)
            elif is_multimodal:
                images = batch['image'].to(self.device)
                c = batch['clinical'].to(self.device)
                mixed_images, y_a, y_b, lam = mixup_data(images, labels, alpha)
                with autocast(enabled=self.use_amp):
                    outputs = model(mixed_images, c)
            elif is_clinical_only:
                c = batch['clinical'].to(self.device)
                mixed_c, y_a, y_b, lam = mixup_data(c, labels, alpha)
                with autocast(enabled=self.use_amp):
                    outputs = model(mixed_c)
            else:
                images = batch['image'].to(self.device)
                mixed_images, y_a, y_b, lam = mixup_data(images, labels, alpha)
                with autocast(enabled=self.use_amp):
                    outputs = model(mixed_images)
            
            with autocast(enabled=self.use_amp):
                loss_inputs = self._criterion_inputs(criterion, outputs)
                loss = mixup_criterion(criterion, loss_inputs, y_a, y_b, lam) / accum
                
                use_attn_guide = self.config.get('attention_guidance', False)
                if use_attn_guide and isinstance(outputs, dict) and 'g_feat_map' in outputs:
                    border_target = batch.get('border_target')
                    if border_target is not None:
                        border_target = border_target.to(self.device)
                        attn_loss = self._attn_guide_loss(
                            outputs['g_feat_map'], border_target) / accum
                        loss = loss + attn_loss
            
            self.scaler.scale(loss).backward()
            
            is_last = (i + 1) == n_batches
            if (i + 1) % accum == 0 or is_last:
                self.scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 
                                                max_norm=self.config.get('grad_clip', 1.0))
                self.scaler.step(optimizer)
                self.scaler.update()
                optimizer.zero_grad()
                if hasattr(self, 'ema') and self.ema is not None:
                    self.ema.update(model)
            
            total_loss += loss.item() * accum
        
        return total_loss / n_batches
    
    @torch.no_grad()
    def _evaluate(self, model, loader, num_classes):
        model.eval()
        all_probs, all_labels = [], []
        
        for batch in loader:
            labels = batch['label']
            
            with autocast(enabled=self.use_amp):
                outputs = self._forward_model(model, batch)
            
            # multitask 模式：eval() 时模型直接返回 main logits；
            # 但若意外返回 dict（如手动调用 train() 后又 evaluate），取 main
            if isinstance(outputs, dict):
                outputs = outputs['main']

            if self.config.get('loss') == 'coral':
                cum_probs = torch.sigmoid(outputs.float())
                cum_probs = torch.cat([
                    torch.ones(outputs.size(0), 1, device=outputs.device),
                    cum_probs,
                    torch.zeros(outputs.size(0), 1, device=outputs.device)
                ], dim=1)
                probs = cum_probs[:, :-1] - cum_probs[:, 1:]
                probs = torch.clamp(probs, min=0)
                probs = probs / probs.sum(dim=1, keepdim=True)
                probs = probs.cpu().numpy()
            else:
                probs = torch.softmax(outputs.float(), dim=1).cpu().numpy()
            all_probs.extend(probs)
            all_labels.extend(labels.numpy())
        
        all_probs = np.array(all_probs)
        all_labels = np.array(all_labels)
        all_preds = all_probs.argmax(axis=1)
        
        metrics = {
            'accuracy': float(accuracy_score(all_labels, all_preds)),
            'f1_macro': float(f1_score(all_labels, all_preds, average='macro', zero_division=0)),
        }
        
        # AUC (float64 for numerical stability)
        all_probs = all_probs.astype(np.float64)
        try:
            if num_classes == 2:
                metrics['auc'] = float(roc_auc_score(all_labels, all_probs[:, 1]))
            else:
                metrics['auc'] = float(roc_auc_score(
                    all_labels, all_probs, multi_class='ovr',
                    labels=list(range(num_classes)), average='macro'))
        except Exception:
            try:
                metrics['auc'] = float(roc_auc_score(
                    all_labels, all_probs, multi_class='ovr', average='weighted'))
            except Exception:
                metrics['auc'] = 0.0
        
        # Per-class recall
        cm = confusion_matrix(all_labels, all_preds, labels=list(range(num_classes)))
        for c in range(num_classes):
            total = cm[c].sum()
            metrics[f'recall_c{c}'] = float(cm[c, c] / total) if total > 0 else 0.0
        
        if num_classes == 2:
            metrics['sensitivity'] = metrics['recall_c1']
            metrics['specificity'] = metrics['recall_c0']
        
        metrics['confusion_matrix'] = cm.tolist()
        metrics['probs'] = all_probs
        metrics['labels'] = all_labels

        t23_mask = np.isin(all_labels, [1, 2])
        if t23_mask.sum() > 0:
            metrics['t2t3_overstage_rate'] = float((all_preds[t23_mask] == 3).mean())
        else:
            metrics['t2t3_overstage_rate'] = 0.0
        
        return metrics

    def _configure_trainable_params(self, model) -> list:
        """Optionally freeze ConvNeXt backbones; return params for optimizer."""
        freeze_all = self.config.get('freeze_backbones', False)
        freeze_global = freeze_all or self.config.get('freeze_global_backbone', False)
        freeze_local = freeze_all or self.config.get('freeze_local_backbone', False)
        if freeze_global or freeze_local:
            frozen = 0
            trainable = 0
            for name, param in model.named_parameters():
                if freeze_global and 'g_backbone' in name:
                    param.requires_grad = False
                    frozen += param.numel()
                elif freeze_local and 'l_backbone' in name:
                    param.requires_grad = False
                    frozen += param.numel()
                elif param.requires_grad:
                    trainable += param.numel()
            parts = []
            if freeze_global:
                parts.append('global')
            if freeze_local:
                parts.append('local')
            self.logger.info(
                f"  Freeze {'+'.join(parts)} backbone: {frozen:,} frozen, {trainable:,} trainable params"
            )
        return [p for p in model.parameters() if p.requires_grad]

    def _training_val_score(self, val_metrics: dict) -> float:
        """Score used for best-checkpoint selection (configurable)."""
        auc = val_metrics['auc'] if val_metrics.get('auc', 0) > 0 else val_metrics['accuracy']
        metric = self.config.get('early_stopping_metric', 'auc')
        if metric == 'auc_minus_overstage':
            penalty = float(self.config.get('overstage_penalty', 0.35))
            return auc - penalty * float(val_metrics.get('t2t3_overstage_rate', 0.0))
        if metric == 'balanced_accuracy':
            return float(val_metrics.get('balanced_accuracy', val_metrics['accuracy']))
        return float(auc)
    
    def fit(self, model, train_dataset, val_dataset, num_classes=2):
        """主训练循环 (支持 warmup, mixup, EMA)"""
        model = model.to(self.device)
        cfg = self.config
        
        # Data loaders
        sampler = self._create_sampler(train_dataset)
        loader_kwargs = dict(
            batch_size=cfg.get('batch_size', 32),
            num_workers=cfg.get('num_workers', 8),
            pin_memory=True,
            drop_last=True,
        )
        if sampler is not None:
            loader_kwargs['sampler'] = sampler
        else:
            loader_kwargs['shuffle'] = True
        train_loader = DataLoader(train_dataset, **loader_kwargs)
        val_loader = DataLoader(
            val_dataset, batch_size=cfg.get('batch_size', 32),
            shuffle=False, num_workers=cfg.get('num_workers', 8), pin_memory=True)
        
        # Optimizer (respect backbone freeze)
        base_lr = float(cfg.get('lr', 5e-5))
        train_params = self._configure_trainable_params(model)
        if not train_params:
            raise RuntimeError("No trainable parameters after freeze_backbones policy")
        optimizer = optim.AdamW(
            train_params,
            lr=base_lr,
            weight_decay=float(cfg.get('weight_decay', 0.05)),
        )
        
        # Scheduler with warmup
        warmup_epochs = cfg.get('warmup_epochs', 5)
        sched_name = cfg.get('scheduler', 'cosine')
        if sched_name == 'onecycle':
            scheduler = OneCycleLR(optimizer, max_lr=base_lr,
                                  epochs=cfg['epochs'], steps_per_epoch=len(train_loader))
        else:
            scheduler = CosineAnnealingLR(optimizer, T_max=cfg['epochs'] - warmup_epochs,
                                         eta_min=base_lr * 0.01)
        
        # Loss — MultiFrameDataset stores labels in patient_labels dict
        from lib.datasets import MultiFrameDataset
        if isinstance(train_dataset, MultiFrameDataset):
            class_counts = Counter(train_dataset.patient_labels.values())
        else:
            class_counts = Counter(train_dataset.df['label'].values)
        criterion = self._create_criterion(num_classes, class_counts)
        
        # EMA
        use_ema = cfg.get('ema', False)
        self.ema = ModelEMA(model, decay=cfg.get('ema_decay', 0.999)) if use_ema else None
        ema = self.ema
        if use_ema:
            self.logger.info(f"  EMA enabled, decay={cfg.get('ema_decay', 0.999)}")
        
        # Attention Guidance Loss
        use_attn_guide = cfg.get('attention_guidance', False)
        if use_attn_guide:
            lambda_attn = cfg.get('lambda_attn', 0.5)
            self._attn_guide_loss = AttentionGuidanceLoss(lambda_attn=lambda_attn).to(self.device)
            model._return_feat_map = True
            self.logger.info(f"  Attention Guidance enabled, lambda={lambda_attn}")
        
        # Mixup
        use_mixup = cfg.get('mixup', 0.0) > 0
        mixup_alpha = cfg.get('mixup', 0.0)
        if use_mixup:
            self.logger.info(f"  Mixup enabled, alpha={mixup_alpha}")
        
        # Training loop
        best_score = 0
        patience = 0
        max_patience = cfg.get('early_stopping', 20)
        best_state = None
        best_ema_state = None
        history = []
        
        self.logger.info(f"Training: {cfg['epochs']} epochs, LR={base_lr}, BS={cfg.get('batch_size', 32)}")
        self.logger.info(f"  Warmup: {warmup_epochs} epochs, Scheduler: {sched_name}")
        self.logger.info(f"  Loss: {cfg.get('loss', 'ce')}")
        es_metric = cfg.get('early_stopping_metric', 'auc')
        if es_metric == 'auc_minus_overstage':
            self.logger.info(
                f"  Early-stop metric: AUC - {cfg.get('overstage_penalty', 0.35)} * T2/T3->T4+ rate"
            )
        else:
            self.logger.info(f"  Early-stop metric: {es_metric}")
        self.logger.info(f"Train: {len(train_dataset)}, Val: {len(val_dataset)}, Classes: {num_classes}")
        self.logger.info(f"Class counts: {dict(class_counts)}")
        
        for epoch in range(1, cfg['epochs'] + 1):
            t0 = time.time()
            
            # Warmup: linearly increase LR during first warmup_epochs
            if epoch <= warmup_epochs and sched_name != 'onecycle':
                warmup_lr = base_lr * (epoch / warmup_epochs)
                for pg in optimizer.param_groups:
                    pg['lr'] = warmup_lr
            
            # Train one epoch (with optional mixup)
            if use_mixup:
                train_loss = self._train_one_epoch_mixup(
                    model, train_loader, optimizer, criterion, mixup_alpha)
            else:
                train_loss = self._train_one_epoch(model, train_loader, optimizer, criterion)
            
            # Step scheduler (after warmup)
            if sched_name != 'onecycle' and epoch > warmup_epochs:
                scheduler.step()
            
            # Evaluate: raw model for tracking, log EMA metrics too
            val_metrics = self._evaluate(model, val_loader, num_classes)
            if ema is not None:
                ema_metrics = self._evaluate(ema.ema_model, val_loader, num_classes)
                # Use the BETTER of raw or EMA for tracking
                ema_score = ema_metrics['auc'] if ema_metrics['auc'] > 0 else ema_metrics['accuracy']
                raw_score = val_metrics['auc'] if val_metrics['auc'] > 0 else val_metrics['accuracy']
                if ema_score > raw_score:
                    val_metrics = ema_metrics
            elapsed = time.time() - t0
            
            val_score = self._training_val_score(val_metrics)
            is_best = val_score > best_score
            if is_best:
                best_score = val_score
                best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
                if ema is not None:
                    best_ema_state = {k: v.cpu().clone() for k, v in ema.ema_model.state_dict().items()}
                patience = 0
                # Save immediately so interrupted runs still have best checkpoint
                final_state = best_ema_state if best_ema_state is not None else best_state
                if final_state:
                    save_dict = {'model_state_dict': final_state, 'config': cfg}
                    if best_state:
                        save_dict['raw_model_state_dict'] = best_state
                    torch.save(save_dict, self.output_dir / 'best_model.pth')
            else:
                patience += 1
            
            history.append({
                'epoch': epoch, 'train_loss': train_loss,
                'val_auc': val_metrics['auc'], 'val_acc': val_metrics['accuracy'],
                **{k: v for k, v in val_metrics.items() 
                   if k not in ('confusion_matrix', 'probs', 'labels')}
            })
            
            if epoch % 5 == 0 or is_best:
                over_msg = ""
                if 't2t3_overstage_rate' in val_metrics:
                    over_msg = f" T2/T3->T4+: {val_metrics['t2t3_overstage_rate']:.3f}"
                self.logger.info(
                    f"Epoch {epoch:3d} | Loss: {train_loss:.4f} | "
                    f"AUC: {val_metrics['auc']:.4f} Acc: {val_metrics['accuracy']:.4f} "
                    f"F1: {val_metrics['f1_macro']:.4f} Score: {val_score:.4f}{over_msg}"
                    f"{' BEST' if is_best else ''} [{elapsed:.0f}s]"
                )
            
            if patience >= max_patience:
                self.logger.info(f"Early stopping at epoch {epoch}")
                break
        
        # Save best model (prefer EMA if available)
        final_state = best_ema_state if best_ema_state is not None else best_state
        if final_state:
            model.load_state_dict(final_state)

            # Recalibrate BN running stats for EMA weights by doing a
            # forward pass through the training data in train mode with
            # frozen parameters.  This fixes the mismatch between EMA
            # parameter values and raw-model BN running statistics.
            if best_ema_state is not None:
                self._calibrate_bn(model, train_loader)

            # Re-snapshot the calibrated state
            final_state = {k: v.cpu().clone()
                           for k, v in model.state_dict().items()}

            save_dict = {'model_state_dict': final_state, 'config': cfg}
            if best_state:
                save_dict['raw_model_state_dict'] = best_state
            torch.save(save_dict, self.output_dir / 'best_model.pth')
        
        # Save history
        pd.DataFrame(history).to_csv(self.output_dir / 'training_history.csv', index=False)
        
        # Save config
        save_cfg = {k: v for k, v in cfg.items() if not callable(v)}
        with open(self.output_dir / 'config.json', 'w') as f:
            json.dump(save_cfg, f, indent=2, default=str)
        
        self.logger.info(f"Best Val Score: {best_score:.4f}")
        self.model = model
        return model
    
    def _find_optimal_threshold(self, labels, probs_positive):
        """Use Youden's J statistic to find optimal classification threshold"""
        from sklearn.metrics import roc_curve
        fpr, tpr, thresholds = roc_curve(labels, probs_positive)
        j_scores = tpr - fpr
        best_idx = np.argmax(j_scores)
        return float(thresholds[best_idx]), fpr, tpr, thresholds
    
    def _evaluate_at_threshold(self, labels, probs_positive, threshold):
        """Evaluate binary classification at a specific threshold"""
        preds = (probs_positive >= threshold).astype(int)
        cm = confusion_matrix(labels, preds, labels=[0, 1])
        tn, fp, fn, tp = cm.ravel()
        return {
            'threshold': threshold,
            'accuracy': float(accuracy_score(labels, preds)),
            'sensitivity': float(tp / (tp + fn)) if (tp + fn) > 0 else 0.0,
            'specificity': float(tn / (tn + fp)) if (tn + fp) > 0 else 0.0,
            'ppv': float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0,
            'npv': float(tn / (tn + fn)) if (tn + fn) > 0 else 0.0,
            'f1': float(f1_score(labels, preds, zero_division=0)),
            'confusion_matrix': cm.tolist(),
        }
    
    def _plot_roc_curve(self, fpr, tpr, auc_val, save_path, title='ROC Curve'):
        """Generate and save ROC curve plot"""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(1, 1, figsize=(8, 8))
            ax.plot(fpr, tpr, 'b-', lw=2, label=f'AUC = {auc_val:.4f}')
            ax.plot([0, 1], [0, 1], 'r--', lw=1, label='Random')
            ax.set_xlabel('False Positive Rate (1 - Specificity)', fontsize=12)
            ax.set_ylabel('True Positive Rate (Sensitivity)', fontsize=12)
            ax.set_title(title, fontsize=14)
            ax.legend(fontsize=12)
            ax.set_xlim([0, 1])
            ax.set_ylim([0, 1])
            ax.grid(True, alpha=0.3)
            fig.savefig(save_path, dpi=150, bbox_inches='tight')
            plt.close(fig)
        except Exception as e:
            self.logger.warning(f"Failed to plot ROC curve: {e}")
    
    def _evaluate_per_source(self, df, threshold):
        """Evaluate per-source breakdown"""
        if 'source' not in df.columns:
            return {}
        results = {}
        for src in sorted(df['source'].unique()):
            sub = df[df['source'] == src]
            n = len(sub)
            n0 = (sub['label'] == 0).sum()
            n1 = (sub['label'] == 1).sum()
            preds = (sub['prob_c1'] >= threshold).astype(int)
            acc = float(accuracy_score(sub['label'], preds))
            result = {'n': int(n), 'n_benign': int(n0), 'n_malignant': int(n1), 'accuracy': acc}
            try:
                result['auc'] = float(roc_auc_score(sub['label'], sub['prob_c1']))
            except:
                result['auc'] = None
            if n1 > 0:
                result['sensitivity'] = float(((preds == 1) & (sub['label'] == 1)).sum() / n1)
            if n0 > 0:
                result['specificity'] = float(((preds == 0) & (sub['label'] == 0)).sum() / n0)
            results[src] = result
        return results
    
    def test(self, test_dataset, num_classes=2, model=None):
        """在测试集上评估 (含阈值优化和分来源分析)"""
        if model is None:
            model = self.model
        model = model.to(self.device)
        
        test_loader = DataLoader(
            test_dataset, batch_size=self.config.get('batch_size', 32),
            shuffle=False, num_workers=self.config.get('num_workers', 8))
        
        metrics = self._evaluate(model, test_loader, num_classes)
        
        from lib.datasets import MultiFrameDataset
        if isinstance(test_dataset, MultiFrameDataset):
            preds_df = pd.DataFrame({
                'patient_id': test_dataset.patients,
                'label': [test_dataset.patient_labels[p] for p in test_dataset.patients],
            })
        else:
            preds_df = test_dataset.df.copy()
        for c in range(num_classes):
            preds_df[f'prob_c{c}'] = metrics['probs'][:, c]
        
        if num_classes == 2:
            probs_pos = metrics['probs'][:, 1]
            labels = metrics['labels']
            
            # === Threshold optimization ===
            opt_thresh, fpr, tpr, thresholds = self._find_optimal_threshold(labels, probs_pos)
            
            # Evaluate at default (argmax=0.5) and optimal threshold
            metrics_default = self._evaluate_at_threshold(labels, probs_pos, 0.5)
            metrics_optimal = self._evaluate_at_threshold(labels, probs_pos, opt_thresh)
            
            metrics['default_threshold'] = metrics_default
            metrics['optimal_threshold'] = metrics_optimal
            
            # Use optimal threshold for predictions
            preds_df['pred'] = (probs_pos >= opt_thresh).astype(int)
            preds_df['pred_default'] = (probs_pos >= 0.5).astype(int)
            
            # === ROC Curve ===
            self._plot_roc_curve(fpr, tpr, metrics['auc'],
                                self.output_dir / 'roc_curve.png',
                                title=f"ROC (AUC={metrics['auc']:.4f})")
            
            # === Per-source evaluation ===
            preds_df.to_csv(self.output_dir / 'test_predictions.csv', index=False)
            per_source = self._evaluate_per_source(preds_df, opt_thresh)
            metrics['per_source'] = per_source
            
            # === Patient-level evaluation ===
            if 'patient_id' in preds_df.columns:
                patient_df = preds_df.groupby('patient_id').agg({
                    'label': 'first', 'prob_c1': 'mean'
                }).reset_index()
                patient_df['pred'] = (patient_df['prob_c1'] >= opt_thresh).astype(int)
                try:
                    patient_auc = float(roc_auc_score(patient_df['label'], patient_df['prob_c1']))
                except:
                    patient_auc = 0.0
                pat_metrics = self._evaluate_at_threshold(
                    patient_df['label'].values, patient_df['prob_c1'].values, opt_thresh)
                pat_metrics['auc'] = patient_auc
                pat_metrics['n_patients'] = len(patient_df)
                metrics['patient_level'] = pat_metrics
            
            # === Detailed logging ===
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"TEST RESULTS (AUC: {metrics['auc']:.4f})")
            self.logger.info(f"{'='*60}")
            self.logger.info(f"  Default threshold (0.5):")
            self.logger.info(f"    Acc={metrics_default['accuracy']:.4f} "
                           f"Sens={metrics_default['sensitivity']:.4f} "
                           f"Spec={metrics_default['specificity']:.4f} "
                           f"F1={metrics_default['f1']:.4f}")
            self.logger.info(f"  Optimal threshold ({opt_thresh:.4f}):")
            self.logger.info(f"    Acc={metrics_optimal['accuracy']:.4f} "
                           f"Sens={metrics_optimal['sensitivity']:.4f} "
                           f"Spec={metrics_optimal['specificity']:.4f} "
                           f"F1={metrics_optimal['f1']:.4f}")
            
            if 'patient_level' in metrics:
                pl = metrics['patient_level']
                self.logger.info(f"  Patient-level ({pl['n_patients']} patients):")
                self.logger.info(f"    AUC={pl['auc']:.4f} "
                               f"Acc={pl['accuracy']:.4f} "
                               f"Sens={pl['sensitivity']:.4f} "
                               f"Spec={pl['specificity']:.4f}")
            
            if per_source:
                self.logger.info(f"\n  Per-source breakdown (threshold={opt_thresh:.4f}):")
                for src, sr in per_source.items():
                    auc_str = f"AUC={sr['auc']:.4f}" if sr.get('auc') is not None else "AUC=N/A"
                    sens_str = f"Sens={sr.get('sensitivity', 0):.4f}" if 'sensitivity' in sr else ""
                    spec_str = f"Spec={sr.get('specificity', 0):.4f}" if 'specificity' in sr else ""
                    self.logger.info(f"    {src:25s} n={sr['n']:>4d} {auc_str} Acc={sr['accuracy']:.4f} {sens_str} {spec_str}")
        else:
            # === 多类评估 (4分期等) ===
            preds_df['pred'] = metrics['probs'].argmax(axis=1)
            preds_df.to_csv(self.output_dir / 'test_predictions.csv', index=False)
            
            labels = metrics['labels']
            preds = metrics['probs'].argmax(axis=1)
            cm = metrics['confusion_matrix']
            
            # 类别名称
            class_names = self.config.get('class_names', [f'C{i}' for i in range(num_classes)])
            
            # Balanced accuracy
            per_class_recall = []
            for c in range(num_classes):
                r = metrics.get(f'recall_c{c}', 0)
                per_class_recall.append(r)
            balanced_acc = np.mean(per_class_recall)
            metrics['balanced_accuracy'] = float(balanced_acc)
            
            # Precision per class
            for c in range(num_classes):
                col_sum = sum(cm[r][c] for r in range(num_classes))
                metrics[f'precision_c{c}'] = float(cm[c][c] / col_sum) if col_sum > 0 else 0.0
            
            # Per-class AUC (one-vs-rest)
            all_probs_mc = metrics.get('probs', None)
            if all_probs_mc is not None:
                for c in range(num_classes):
                    binary_labels = (labels == c).astype(int)
                    if binary_labels.sum() > 0 and binary_labels.sum() < len(binary_labels):
                        try:
                            metrics[f'auc_c{c}'] = float(
                                roc_auc_score(binary_labels, all_probs_mc[:, c]))
                        except Exception:
                            metrics[f'auc_c{c}'] = 0.0
                    else:
                        metrics[f'auc_c{c}'] = 0.0
            
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"TEST RESULTS (Multi-class, {num_classes} classes)")
            self.logger.info(f"{'='*60}")
            self.logger.info(f"  AUC(OVR): {metrics['auc']:.4f}")
            self.logger.info(f"  Accuracy: {metrics['accuracy']:.4f}")
            self.logger.info(f"  Balanced Accuracy: {balanced_acc:.4f}")
            self.logger.info(f"  F1(macro): {metrics['f1_macro']:.4f}")
            
            self.logger.info(f"\n  Per-class metrics:")
            self.logger.info(f"  {'Class':>10s} {'Recall':>8s} {'Precision':>10s} {'Support':>8s}")
            for c in range(num_classes):
                name = class_names[c] if c < len(class_names) else f'C{c}'
                recall = metrics.get(f'recall_c{c}', 0)
                prec = metrics.get(f'precision_c{c}', 0)
                support = sum(cm[c])
                self.logger.info(f"  {name:>10s} {recall:8.1%} {prec:10.1%} {support:8d}")
            
            self.logger.info(f"\n  Confusion Matrix:")
            header = '  ' + ' '.join(f'{(class_names[c] if c < len(class_names) else f"C{c}"):>6s}' 
                                     for c in range(num_classes))
            self.logger.info(f"  Pred→{header}")
            for r in range(num_classes):
                name = class_names[r] if r < len(class_names) else f'C{r}'
                row_str = ' '.join(f'{cm[r][c]:6d}' for c in range(num_classes))
                self.logger.info(f"  {name:>6s} {row_str}")
            
            # === Per-source evaluation (multi-class) ===
            if 'source' in preds_df.columns:
                self.logger.info(f"\n  Per-source breakdown:")
                per_source_mc = {}
                for src in sorted(preds_df['source'].unique()):
                    sub = preds_df[preds_df['source'] == src]
                    n = len(sub)
                    src_acc = float(accuracy_score(sub['label'], sub['pred']))
                    src_bal = float(recall_score(sub['label'], sub['pred'], 
                                               average='macro', zero_division=0))
                    per_source_mc[src] = {'n': n, 'accuracy': src_acc, 'balanced_acc': src_bal}
                    self.logger.info(f"    {src:25s} n={n:>4d} Acc={src_acc:.4f} BalAcc={src_bal:.4f}")
                metrics['per_source'] = per_source_mc
            
            # === Patient-level evaluation (multi-class) ===
            pid_col = 'patient_id_unique' if 'patient_id_unique' in preds_df.columns else 'patient_id'
            if pid_col in preds_df.columns:
                # 对每个患者的概率取均值
                prob_cols = [f'prob_c{c}' for c in range(num_classes)]
                patient_agg = preds_df.groupby(pid_col).agg(
                    {**{pc: 'mean' for pc in prob_cols}, 'label': 'first'}
                ).reset_index()
                patient_agg['pred'] = patient_agg[prob_cols].values.argmax(axis=1)
                
                pat_acc = float(accuracy_score(patient_agg['label'], patient_agg['pred']))
                pat_bal = float(recall_score(patient_agg['label'], patient_agg['pred'],
                                           average='macro', zero_division=0))
                n_pat = len(patient_agg)
                
                metrics['patient_level'] = {
                    'n_patients': n_pat,
                    'accuracy': pat_acc,
                    'balanced_accuracy': pat_bal,
                }
                self.logger.info(f"\n  Patient-level ({n_pat} patients):")
                self.logger.info(f"    Acc={pat_acc:.4f} BalAcc={pat_bal:.4f}")
            
            # === Confusion Matrix Plot ===
            self._plot_confusion_matrix(cm, class_names, 
                                       self.output_dir / 'confusion_matrix.png')
        
        # Save comprehensive results
        save_metrics = {}
        for k, v in metrics.items():
            if k in ('probs', 'labels'):
                continue
            if isinstance(v, np.ndarray):
                save_metrics[k] = v.tolist()
            else:
                save_metrics[k] = v
        with open(self.output_dir / 'test_results.json', 'w') as f:
            json.dump(save_metrics, f, indent=2, default=str)
        
        return metrics
    
    # ------------------------------------------------------------------
    # Visualization helpers
    # ------------------------------------------------------------------
    def _plot_confusion_matrix(self, cm, class_names, save_path):
        """绘制并保存混淆矩阵热力图"""
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            import matplotlib.font_manager as fm
            
            n = len(class_names)
            fig, ax = plt.subplots(figsize=(max(6, n*1.5), max(5, n*1.2)))
            
            # 归一化 (按行, 即按真实标签)
            cm_arr = np.array(cm, dtype=float)
            row_sums = cm_arr.sum(axis=1, keepdims=True)
            cm_norm = np.divide(cm_arr, row_sums, where=row_sums != 0, 
                               out=np.zeros_like(cm_arr))
            
            im = ax.imshow(cm_norm, interpolation='nearest', cmap='Blues', 
                          vmin=0, vmax=1)
            fig.colorbar(im, ax=ax, shrink=0.8)
            
            # 标注文字
            for i in range(n):
                for j in range(n):
                    val = cm[i][j]
                    pct = cm_norm[i][j]
                    color = 'white' if pct > 0.5 else 'black'
                    ax.text(j, i, f'{val}\n({pct:.0%})', 
                           ha='center', va='center', color=color, fontsize=10)
            
            ax.set_xticks(range(n))
            ax.set_yticks(range(n))
            ax.set_xticklabels(class_names, fontsize=11)
            ax.set_yticklabels(class_names, fontsize=11)
            ax.set_xlabel('Predicted', fontsize=12)
            ax.set_ylabel('True', fontsize=12)
            ax.set_title('Confusion Matrix', fontsize=14)
            
            fig.tight_layout()
            fig.savefig(save_path, dpi=150)
            plt.close(fig)
            self.logger.info(f"  Confusion matrix saved to {save_path}")
        except Exception as e:
            self.logger.warning(f"  Failed to plot confusion matrix: {e}")