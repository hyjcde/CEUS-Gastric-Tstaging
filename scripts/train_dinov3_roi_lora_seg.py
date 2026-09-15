#!/usr/bin/env python3
"""Train ROI DINOv3 LoRA segmentation and report Dice.

Uses the GT lesion-crop SMS set (crop from crop_ui + roi_masks). This is an
upper bound because eval boxes come from GT masks. Not T-stage classification.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import yaml
from PIL import Image, ImageEnhance
from torch.utils.data import DataLoader, Dataset


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from run_dinov3_segmentation import SegDinoModel, resolve_path  # noqa: E402
from run_unet2d_segmentation_baseline import (  # noqa: E402
    dice_loss_from_logits,
    load_records,
    split_train_val,
)
from train_dinov3_roi_lora_mlp import (  # noqa: E402
    LoRALinear,
    apply_gaussian_blur,
    inject_lora,
    load_timm_mae_backbone,
)


DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "segmentation" / "dinov3" / "vitb16_roi_lora_mlp_512.yaml"
DEFAULT_M025_CKPT = (
    PROJECT_ROOT
    / "experiments"
    / "segmentation"
    / "dinov3_vitb16_roi_lora_mlp_512_m025_20260828_full"
    / "checkpoints"
    / "best.pt"
)
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--exp-name", default=None)
    parser.add_argument("--device", default=None)
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--num-workers", type=int, default=None)
    parser.add_argument(
        "--resume",
        type=Path,
        default=None,
        help="Load a complete SegDinoModel checkpoint after construction (including LoRA and decoder).",
    )
    parser.add_argument(
        "--finetune-lr",
        type=float,
        default=None,
        help="Override both LoRA and decoder learning rates for a resumed fine-tuning run.",
    )
    parser.add_argument("--max-train-samples", type=int, default=None)
    parser.add_argument("--max-eval-samples", type=int, default=None)
    parser.add_argument("--skip-full-eval", action="store_true")
    parser.add_argument("--data-parallel", action="store_true",
                        help="Use nn.DataParallel across all visible GPUs.")
    parser.add_argument(
        "--input-blur-sigma",
        type=float,
        default=None,
        help="Gaussian blur sigma applied to input images (deblur-MAE transfer protocol). "
        "Overrides config model.input_blur_sigma. 0 disables.",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return payload


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def letterbox_pair(image: Image.Image, mask: Image.Image, size: int) -> tuple[Image.Image, Image.Image]:
    w, h = image.size
    scale = min(size / max(w, 1), size / max(h, 1))
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    image = image.resize((nw, nh), Image.BILINEAR)
    mask = mask.resize((nw, nh), Image.NEAREST)
    canvas_i = Image.new("RGB", (size, size), (0, 0, 0))
    canvas_m = Image.new("L", (size, size), 0)
    ox = (size - nw) // 2
    oy = (size - nh) // 2
    canvas_i.paste(image, (ox, oy))
    canvas_m.paste(mask, (ox, oy))
    return canvas_i, canvas_m


class RoiSegDataset(Dataset):
    def __init__(
        self,
        records: list,
        image_size: int,
        augment: bool,
        brightness: float,
        contrast: float,
        blur_sigma: float = 0.0,
    ) -> None:
        self.records = records
        self.image_size = int(image_size)
        self.augment = bool(augment)
        self.brightness = float(brightness)
        self.contrast = float(contrast)
        self.blur_sigma = float(blur_sigma)

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, Any]:
        record = self.records[index]
        image = Image.open(record.image_path).convert("RGB")
        mask = Image.open(record.mask_path).convert("L")
        if self.blur_sigma > 0:
            image = apply_gaussian_blur(image, self.blur_sigma)
        if self.augment:
            if self.brightness > 0:
                image = ImageEnhance.Brightness(image).enhance(1.0 + random.uniform(-self.brightness, self.brightness))
            if self.contrast > 0:
                image = ImageEnhance.Contrast(image).enhance(1.0 + random.uniform(-self.contrast, self.contrast))
        image, mask = letterbox_pair(image, mask, self.image_size)
        arr = np.asarray(image, dtype=np.float32) / 255.0
        arr = (arr - IMAGENET_MEAN) / IMAGENET_STD
        mask_arr = (np.asarray(mask, dtype=np.uint8) > 0).astype(np.float32)
        return {
            "image": torch.from_numpy(arr).permute(2, 0, 1).contiguous(),
            "mask": torch.from_numpy(mask_arr).unsqueeze(0),
            "case_id": record.case_id,
            "patient_id": record.patient_id,
        }


def upsample_logits(logits: torch.Tensor, size: tuple[int, int]) -> torch.Tensor:
    if logits.shape[-2:] != size:
        logits = F.interpolate(logits, size=size, mode="bilinear", align_corners=False)
    return logits


def batch_dice(logits: torch.Tensor, masks: torch.Tensor, threshold: float = 0.5, eps: float = 1e-6) -> list[float]:
    probs = torch.sigmoid(logits)
    preds = (probs >= threshold).float()
    inter = (preds * masks).sum(dim=(1, 2, 3))
    denom = preds.sum(dim=(1, 2, 3)) + masks.sum(dim=(1, 2, 3))
    dice = (2 * inter + eps) / (denom + eps)
    return [float(v) for v in dice.detach().cpu().tolist()]


def evaluate_loader(model: nn.Module, loader: DataLoader, device: torch.device, threshold: float) -> dict[str, float]:
    model.eval()
    scores: list[float] = []
    with torch.no_grad():
        for batch in loader:
            images = batch["image"].to(device, dtype=torch.float32)
            masks = batch["mask"].to(device, dtype=torch.float32)
            logits = upsample_logits(model(images), masks.shape[-2:])
            scores.extend(batch_dice(logits, masks, threshold))
    arr = np.asarray(scores, dtype=np.float64)
    return {
        "n": float(len(arr)),
        "dice": float(arr.mean()) if len(arr) else float("nan"),
        "zero_dice": float(np.mean(arr < 1e-6)) if len(arr) else float("nan"),
    }


def load_model(config: dict[str, Any], device: torch.device) -> tuple[nn.Module, dict[str, Any]]:
    paths_cfg = config.get("paths", {})
    model_cfg = config.get("model", {})
    lora_cfg = model_cfg.get("lora", {}) or {}
    family = str(model_cfg.get("backbone_family", "dinov3"))
    pretrained = resolve_path(paths_cfg.get("checkpoint_path"))
    if family == "timm_mae":
        # MAE-style encoder: skip the dinov3 seg-ckpt overlay (key collision would corrupt weights).
        if pretrained is None:
            raise FileNotFoundError("Missing checkpoint_path for timm_mae backbone")
        backbone = load_timm_mae_backbone(model_cfg, pretrained)
        info = {"official_weights": str(pretrained), "seg_ckpt": "skipped (timm_mae family)", "loaded_backbone_tensors": 0}
    else:
        repo_dir = resolve_path(paths_cfg.get("dinov3_repo"))
        if repo_dir is None or pretrained is None:
            raise FileNotFoundError("Missing DINOv3 repo or official weights")
        backbone = torch.hub.load(
            str(repo_dir),
            str(model_cfg.get("hub_model", "dinov3_vitb16")),
            source="local",
            weights=str(pretrained),
        )
        info = {"official_weights": str(pretrained), "seg_ckpt": None, "loaded_backbone_tensors": 0}
        init_ckpt = resolve_path(paths_cfg.get("init_seg_ckpt"))
        if init_ckpt is not None:
            ckpt = torch.load(init_ckpt, map_location="cpu", weights_only=False)
            raw = ckpt.get("model_state_dict", ckpt)
            overlay = {key[len("backbone.") :]: value for key, value in raw.items() if str(key).startswith("backbone.")}
            result = backbone.load_state_dict(overlay, strict=False)
            info["seg_ckpt"] = str(init_ckpt)
            info["loaded_backbone_tensors"] = int(len(overlay))
            info["missing_keys"] = list(result.missing_keys)
            info["unexpected_keys"] = list(result.unexpected_keys)
    for param in backbone.parameters():
        param.requires_grad = False
    lora_n = 0
    if lora_cfg.get("enabled", False):
        lora_n = inject_lora(
            backbone,
            int(lora_cfg.get("target_blocks", 4)),
            int(lora_cfg.get("rank", 8)),
            float(lora_cfg.get("alpha", 16)),
            float(lora_cfg.get("dropout", 0.05)),
        )
    model = SegDinoModel(backbone=backbone, model_cfg=model_cfg).to(device)
    info["lora_modules"] = lora_n
    info["trainable"] = int(sum(p.numel() for p in model.parameters() if p.requires_grad))
    info["total"] = int(sum(p.numel() for p in model.parameters()))
    return model, info


def main() -> None:
    args = parse_args()
    config = load_yaml(args.config)
    train_cfg = config.get("train", {})
    model_cfg = config.get("model", {})
    paths_cfg = config.get("paths", {})
    eval_cfg = config.get("evaluation", {})
    set_seed(int(train_cfg.get("seed", 666)))
    device = torch.device(args.device or train_cfg.get("device", "cuda:0" if torch.cuda.is_available() else "cpu"))
    image_size = int(model_cfg.get("input_size", 512))
    epochs = int(args.epochs or train_cfg.get("epochs", 40))
    batch_size = int(args.batch_size or train_cfg.get("batch_size", 2))
    num_workers = int(args.num_workers or train_cfg.get("num_workers", 4))
    threshold = float(eval_cfg.get("threshold", 0.5))
    dice_w = float(train_cfg.get("losses", {}).get("dice_weight", 0.5))
    bce_w = float(train_cfg.get("losses", {}).get("bce_weight", 0.5))
    aug = train_cfg.get("augmentation", {}) or {}
    blur_sigma = args.input_blur_sigma
    if blur_sigma is None:
        blur_sigma = float(model_cfg.get("input_blur_sigma", 0.0) or 0.0)
    if blur_sigma > 0:
        print(json.dumps({"input_blur_sigma": blur_sigma, "note": "deblur-MAE transfer protocol"}), flush=True)

    dataset_root = resolve_path(paths_cfg.get("dataset_root"))
    if dataset_root is None:
        raise FileNotFoundError("dataset_root missing")
    manifest_path = dataset_root / "dataset_manifest.json"
    train_all, holdout, eval_sources = load_records(manifest_path)
    train_records, val_records, split_summary = split_train_val(
        train_all, float(train_cfg.get("val_fraction", 0.10)), int(train_cfg.get("seed", 666))
    )
    if args.max_train_samples:
        train_records = train_records[: args.max_train_samples]
        val_records = val_records[: max(1, args.max_eval_samples or 12)]
    if args.max_eval_samples:
        holdout = holdout[: args.max_eval_samples]
        eval_sources = {key: rows[: args.max_eval_samples] for key, rows in eval_sources.items()}

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    exp_name = args.exp_name or f"dinov3_vitb16_roi_lora_mlp_512_{stamp}"
    exp_dir = PROJECT_ROOT / str(paths_cfg.get("experiment_root", "experiments/segmentation")) / exp_name
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "checkpoints").mkdir(exist_ok=True)

    def make_loader(records: list, shuffle: bool, augment: bool) -> DataLoader:
        ds = RoiSegDataset(
            records,
            image_size,
            augment,
            float(aug.get("brightness_jitter", 0.0)),
            float(aug.get("contrast_jitter", 0.0)),
            blur_sigma=blur_sigma,
        )
        return DataLoader(
            ds,
            batch_size=batch_size,
            shuffle=shuffle,
            num_workers=num_workers,
            pin_memory=device.type == "cuda",
        )

    train_loader = make_loader(train_records, True, True)
    val_loader = make_loader(val_records, False, False)
    model, init_info = load_model(config, device)
    raw_model = model
    if args.data_parallel and device.type == "cuda" and torch.cuda.device_count() > 1:
        model = nn.DataParallel(model)
        init_info["data_parallel_gpus"] = torch.cuda.device_count()
        print(json.dumps({"data_parallel": True, "gpus": torch.cuda.device_count()}), flush=True)
    if args.resume is not None:
        resume_path = args.resume.resolve()
        if not resume_path.exists():
            raise FileNotFoundError(f"--resume checkpoint not found: {resume_path}")
        payload = torch.load(resume_path, map_location="cpu", weights_only=False)
        state = payload.get("model_state_dict", payload)
        missing, unexpected = raw_model.load_state_dict(state, strict=False)
        missing = [key for key in missing if "bias_mask" not in key]
        unexpected = [key for key in unexpected if "bias_mask" not in key]
        if missing or unexpected:
            raise RuntimeError(f"resume state mismatch missing={missing} unexpected={unexpected}")
        init_info["resume_checkpoint"] = str(resume_path)
    decoder_params = [p for n, p in raw_model.named_parameters() if p.requires_grad and n.startswith("decoder.")]
    other_params = [p for n, p in raw_model.named_parameters() if p.requires_grad and not n.startswith("decoder.")]
    finetune_lr = args.finetune_lr
    decoder_lr = float(finetune_lr if finetune_lr is not None else train_cfg.get("decoder_lr", 1e-4))
    lora_lr = float(finetune_lr if finetune_lr is not None else train_cfg.get("lr", 1e-4))
    optimizer = torch.optim.AdamW(
        [
            {"params": decoder_params, "lr": decoder_lr},
            {"params": other_params, "lr": lora_lr},
        ],
        weight_decay=float(train_cfg.get("weight_decay", 1e-4)),
    )
    use_amp = bool(train_cfg.get("amp", True)) and device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda") if use_amp else None

    best_val = -math.inf
    best_state = None
    bad = 0
    history = []
    patience = int(train_cfg.get("early_stopping_patience", 8))
    for epoch in range(1, epochs + 1):
        model.train()
        losses = []
        for batch in train_loader:
            optimizer.zero_grad(set_to_none=True)
            images = batch["image"].to(device, dtype=torch.float32, non_blocking=True)
            masks = batch["mask"].to(device, dtype=torch.float32, non_blocking=True)
            with torch.amp.autocast("cuda", enabled=use_amp):
                logits = upsample_logits(model(images), masks.shape[-2:])
                loss = dice_w * dice_loss_from_logits(logits, masks) + bce_w * F.binary_cross_entropy_with_logits(logits, masks)
            if scaler is not None:
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            else:
                loss.backward()
                optimizer.step()
            losses.append(float(loss.detach().cpu()))
        val_metrics = evaluate_loader(model, val_loader, device, threshold)
        row = {"epoch": epoch, "train_loss": float(np.mean(losses)), "val_dice": val_metrics["dice"], "val_zero_dice": val_metrics["zero_dice"]}
        history.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if np.isfinite(val_metrics["dice"]) and val_metrics["dice"] > best_val:
            best_val = float(val_metrics["dice"])
            bad = 0
            best_state = {k: v.detach().cpu().clone() for k, v in raw_model.state_dict().items()}
            torch.save({"model_state_dict": best_state, "epoch": epoch, "best_val_dice": best_val, "config": config}, exp_dir / "checkpoints" / "best.pt")
        else:
            bad += 1
            if bad >= patience:
                print(json.dumps({"early_stop": True, "epoch": epoch, "best_val_dice": best_val}), flush=True)
                break

    if best_state is not None:
        raw_model.load_state_dict(best_state)
    result_rows = [{"split": "val", **evaluate_loader(model, val_loader, device, threshold)}]
    if not args.skip_full_eval:
        eval_sets = [("internal_holdout", holdout)]
        eval_sets.extend(sorted(eval_sources.items()))
        for name, records in eval_sets:
            if not records:
                continue
            result_rows.append({"split": name, **evaluate_loader(model, make_loader(records, False, False), device, threshold)})
    (exp_dir / "training_history.csv").write_text(
        "epoch,train_loss,val_dice,val_zero_dice\n"
        + "\n".join(f"{r['epoch']},{r['train_loss']},{r['val_dice']},{r['val_zero_dice']}" for r in history)
        + "\n",
        encoding="utf-8",
    )
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "task": "dinov3_roi_lora_segmentation",
        "dataset_root": str(dataset_root),
        "note": "GT lesion-crop upper bound. Dice on ROI crops. Not T-stage classification. Not deployable.",
        "exp_dir": str(exp_dir),
        "split_summary": split_summary,
        "input_blur_sigma": blur_sigma,
        "init_info": init_info,
        "resume_checkpoint": init_info.get("resume_checkpoint"),
        "finetune_lr": finetune_lr,
        "best_val_dice": best_val,
        "results": result_rows,
        "checkpoint": str(exp_dir / "checkpoints" / "best.pt"),
    }
    (exp_dir / "dinov3_run_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report_dir = PROJECT_ROOT / "pipeline" / "experiments" / "reports" / exp_name
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# DINOv3 ROI LoRA segmentation",
        "",
        "GT lesion-crop from crop_ui + roi_masks. Letterbox 512. Dice + BCE. Not T-stage.",
        "",
        f"Best val Dice: {best_val:.4f}",
        "",
        "| split | n | Dice | zero-Dice |",
        "|---|---:|---:|---:|",
    ]
    for row in result_rows:
        lines.append(f"| {row['split']} | {int(row['n'])} | {row['dice']:.4f} | {row['zero_dice']:.4f} |")
    (report_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
