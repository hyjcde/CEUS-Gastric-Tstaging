"""方案 5 / 6: 患者袋训练与方案完整网格。

PatientBagDataset 按 patient_id 装袋（方案 5: 帧数因人而异，不能按固定位置拼接）。
--head mlp     方案 6.1；临床 22 个数直接进头。
--head tabpfn  方案 6.2；临床先经 TabPFN 变成 4 类概率再与 z_image 拼接。
PLAN_RUNS      方案 4.x / 5.x / 6.x 唯一格子（5.1 跳过融合，故无 interact+mean）。
默认合同: concat + gated + mlp + xlarge，锁验证精确 ACC。方案未写损失 / 划分。
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
from torch.optim.lr_scheduler import LambdaLR
from torch.utils.data import DataLoader, Dataset

from .constants import (
    AREAROI_CACHE_DIR,
    AVGROI_CACHE_DIR,
    CACHE_DIR,
    CLASS_NAMES,
    CLINICAL_FIELDS,
    LARGECLF_REPORT_DIR,
    N_CLASSES,
    OPT_REPORT_DIR,
    PLAN_COMPLETE_REPORT_DIR,
    PREOP_DROP_FIELDS,
    REPORT_DIR,
    RETRY_REPORT_DIR,
    T34_REPORT_DIR,
    TABPFN_REPORT_DIR,
    cache_dir_for_expand,
)
from .metrics import center_of, confusion, md_confusion, per_center, score_arrays
from .model import GastricUSFromScratch
from .tabpfn_clinical import (
    TIME192_CACHE,
    TIME192_PREOP_CACHE,
    build_tabpfn_cache,
    build_time192_cache,
    load_tabpfn_both_map,
    load_tabpfn_map,
    load_time192_map,
    time192_dim,
)

def plan_cell(fusion: str, pool: str, head: str) -> str:
    """Map a run to GastricUS实验方案.md section numbers. 5.1 skips 4.x fusion."""
    if head in {"tabpfn_only", "tabpfn_clinical_only"} or fusion in {"none", "n/a"}:
        return "6.2 clinical-only"
    route = "6.1" if head == "mlp" else "6.2"
    if pool == "mean_views":
        return f"5.1 x {route}"
    fusion_tag = {"concat": "4.1", "interact": "4.2", "gate": "4.gate", "pair": "4.pair"}.get(fusion, fusion)
    pool_tag = {"stats": "5.2", "gated": "5.3", "mean_u": "5.mean_u", "attn_only": "5.attn_only"}.get(pool, pool)
    return f"{fusion_tag} x {pool_tag} x {route}"


# 对照 GastricUS实验方案.md 第 4 / 5 / 6 节。5.1 不使用 4.x，所以没有 interact+mean_views。
PLAN_RUNS = (
    {"name": "mlp_concat_mean", "fusion": "concat", "pool": "mean_views", "head": "mlp"},  # 5.1 x 6.1
    {"name": "tabpfn_concat_mean", "fusion": "concat", "pool": "mean_views", "head": "tabpfn"},  # 5.1 x 6.2
    {"name": "mlp_concat_stats", "fusion": "concat", "pool": "stats", "head": "mlp"},  # 4.1 x 5.2 x 6.1
    {"name": "mlp_concat_gated", "fusion": "concat", "pool": "gated", "head": "mlp"},  # 4.1 x 5.3 x 6.1 默认
    {"name": "mlp_interact_stats", "fusion": "interact", "pool": "stats", "head": "mlp"},  # 4.2 x 5.2 x 6.1
    {"name": "mlp_interact_gated", "fusion": "interact", "pool": "gated", "head": "mlp"},  # 4.2 x 5.3 x 6.1
    {"name": "tabpfn_concat_stats", "fusion": "concat", "pool": "stats", "head": "tabpfn"},  # 4.1 x 5.2 x 6.2
    {"name": "tabpfn_concat_gated", "fusion": "concat", "pool": "gated", "head": "tabpfn"},  # 4.1 x 5.3 x 6.2
    {"name": "tabpfn_interact_stats", "fusion": "interact", "pool": "stats", "head": "tabpfn"},  # 4.2 x 5.2 x 6.2
    {"name": "tabpfn_interact_gated", "fusion": "interact", "pool": "gated", "head": "tabpfn"},  # 4.2 x 5.3 x 6.2
)
# 方案外: 加宽对照 + 去临床。不是 4.x x 5.x 完整网格。
OPT_RUNS = (
    {"name": "mlp_concat_mean", "fusion": "concat", "pool": "mean_views", "head": "mlp", "clinical": "raw"},
    {"name": "mlp_concat_gated", "fusion": "concat", "pool": "gated", "head": "mlp", "clinical": "raw"},
    {"name": "mlp_interact_gated", "fusion": "interact", "pool": "gated", "head": "mlp", "clinical": "raw"},
    {"name": "mlp_concat_mean_img", "fusion": "concat", "pool": "mean_views", "head": "mlp", "clinical": "none"},
)
# 方案外: T3/T4 损失与锁点，不升格为默认。
T34_RUNS = (
    {
        "name": "gated_cost_qwk",
        "fusion": "concat",
        "pool": "gated",
        "lock": "qwk",
        "ordinal_mode": "cost",
        "ordinal_weight": 1.0,
        "t34_weight": 0.0,
        "aux_serosa_weight": 0.0,
        "clinical": "raw",
    },
    {
        "name": "gated_t34_acc",
        "fusion": "concat",
        "pool": "gated",
        "lock": "acc",
        "ordinal_mode": "rank",
        "ordinal_weight": 0.5,
        "t34_weight": 1.0,
        "aux_serosa_weight": 0.0,
        "clinical": "raw",
    },
    {
        "name": "gated_serosa_acc",
        "fusion": "concat",
        "pool": "gated",
        "lock": "acc",
        "ordinal_mode": "rank",
        "ordinal_weight": 0.5,
        "t34_weight": 0.0,
        "aux_serosa_weight": 0.5,
        "clinical": "raw",
    },
    {
        "name": "gated_all_qwk",
        "fusion": "concat",
        "pool": "gated",
        "lock": "qwk",
        "ordinal_mode": "cost",
        "ordinal_weight": 1.0,
        "t34_weight": 1.0,
        "aux_serosa_weight": 0.5,
        "clinical": "raw",
    },
    {
        "name": "mean_cost_acc",
        "fusion": "concat",
        "pool": "mean_views",
        "lock": "acc",
        "ordinal_mode": "cost",
        "ordinal_weight": 1.0,
        "t34_weight": 0.0,
        "aux_serosa_weight": 0.0,
        "clinical": "raw",
    },
)


def _select_frame_idx(n: int, max_frames: int, mode: str, pid: str, areas: list[float], seed: int) -> list[int]:
    """方案 5: 袋长超过 max_frames（默认 16）时截断。prefix=CSV 顺序；area/random 方案未写。"""
    if n <= max_frames:
        return list(range(n))
    if mode == "area" and areas:
        order = np.argsort(np.asarray(areas, dtype=np.float32))[::-1]
        return sorted(int(i) for i in order[:max_frames])
    if mode == "random":
        rng = np.random.RandomState((seed + (hash(pid) % 1_000_003)) % (2**31 - 1))
        return sorted(int(i) for i in rng.choice(n, size=max_frames, replace=False))
    return list(range(max_frames))


class PatientBagDataset(Dataset):
    """方案 5: 按 patient_id 把变长关键帧收成一袋，输出定长患者样本（评估不再对帧二次平均）。"""

    def __init__(
        self,
        npz_path: Path,
        max_frames: int = 16,
        tabpfn_map: dict[str, np.ndarray] | None = None,
        extra_map: dict[str, np.ndarray] | None = None,
        task: str = "t4",
        frame_sample: str = "prefix",
        seed: int = 20260821,
        keep_pids: set[str] | None = None,
    ) -> None:
        if frame_sample not in {"prefix", "random", "area"}:
            raise ValueError(frame_sample)
        with np.load(npz_path, allow_pickle=True) as data:
            e_full = np.asarray(data["e_full"])
            e_roi = np.asarray(data["e_roi"])
            clinical = np.asarray(data["clinical"])
            labels = np.asarray(data["label"])
            patient_ids = np.asarray(data["patient_id"]).astype(str)
            sources = np.asarray(data["source"]).astype(str) if "source" in data.files else np.full(len(patient_ids), "")
            areas = np.asarray(data["mask_area"], dtype=np.float32) if "mask_area" in data.files else None
        bags: dict[str, dict[str, list]] = defaultdict(
            lambda: {"full": [], "roi": [], "clinical": [], "label": [], "source": [], "area": []}
        )
        for i, pid in enumerate(patient_ids):
            bags[pid]["full"].append(e_full[i])
            bags[pid]["roi"].append(e_roi[i])
            bags[pid]["clinical"].append(clinical[i])
            bags[pid]["label"].append(int(labels[i]))
            bags[pid]["source"].append(str(sources[i]))
            bags[pid]["area"].append(float(areas[i]) if areas is not None else 0.0)
        self.task = task if task in {"t4", "serosa", "t34", "t123", "t12"} else "t4"
        self.bags = bags
        self.max_frames = max_frames
        self.tabpfn_map = tabpfn_map or {}
        self.extra_map = extra_map or {}
        self.frame_sample = frame_sample
        self.seed = seed
        pids = sorted(bags)
        if keep_pids is not None:
            keep = {str(x) for x in keep_pids}
            pids = [pid for pid in pids if pid in keep]
        if self.task in {"t34", "t123", "t12"}:
            keep = {2, 3} if self.task == "t34" else ({0, 1, 2} if self.task == "t123" else {0, 1})
            kept = []
            for pid in pids:
                ys = bags[pid]["label"]
                y = int(max(set(ys), key=ys.count))
                if y in keep:
                    kept.append(pid)
            pids = kept
        self.pids = pids

    def __len__(self) -> int:
        return len(self.pids)

    def labels(self) -> list[int]:
        out = []
        for pid in self.pids:
            ys = self.bags[pid]["label"]
            label = int(max(set(ys), key=ys.count))
            if self.task == "serosa":
                label = int(label >= 3)
            elif self.task == "t34":
                label = int(label == 3)
            out.append(label)
        return out

    def __getitem__(self, idx: int) -> dict[str, object]:
        pid = self.pids[idx]
        bag = self.bags[pid]
        idx_keep = _select_frame_idx(
            len(bag["full"]), self.max_frames, self.frame_sample, pid, bag["area"], self.seed
        )
        full = np.stack([bag["full"][i] for i in idx_keep], axis=0)
        roi = np.stack([bag["roi"][i] for i in idx_keep], axis=0)
        clinical = np.stack([bag["clinical"][i] for i in idx_keep], axis=0).mean(axis=0)
        n = len(idx_keep)
        if self.tabpfn_map:
            if pid not in self.tabpfn_map:
                raise KeyError(f"missing TabPFN clinical row for patient {pid}")
            clinical = self.tabpfn_map[pid]
        if self.extra_map:
            if pid not in self.extra_map:
                raise KeyError(f"missing extra clinical row for patient {pid}")
            clinical = np.concatenate([np.asarray(clinical, dtype=np.float32), self.extra_map[pid]], axis=0)
        labels = [bag["label"][i] for i in idx_keep]
        label = int(max(set(labels), key=labels.count))
        if self.task == "serosa":
            label = int(label >= 3)
        elif self.task == "t34":
            label = int(label == 3)
        source = Counter(bag["source"]).most_common(1)[0][0] if bag["source"] else ""
        return {
            "e_full": torch.from_numpy(full.astype(np.float32)),
            "e_roi": torch.from_numpy(roi.astype(np.float32)),
            "clinical": torch.from_numpy(np.asarray(clinical, dtype=np.float32)),
            "label": torch.tensor(label, dtype=torch.long),
            "n": torch.tensor(n, dtype=torch.long),
            "patient_id": pid,
            "source": source,
        }


def collate(batch: list[dict[str, object]]) -> dict[str, object]:
    max_t = max(int(item["n"]) for item in batch)
    dim = batch[0]["e_full"].shape[-1]
    bsz = len(batch)
    e_full = torch.zeros(bsz, max_t, dim)
    e_roi = torch.zeros(bsz, max_t, dim)
    valid = torch.zeros(bsz, max_t, dtype=torch.bool)
    clinical = torch.stack([item["clinical"] for item in batch], dim=0)
    labels = torch.stack([item["label"] for item in batch], dim=0)
    for i, item in enumerate(batch):
        n = int(item["n"])
        e_full[i, :n] = item["e_full"]
        e_roi[i, :n] = item["e_roi"]
        valid[i, :n] = True
    return {
        "e_full": e_full,
        "e_roi": e_roi,
        "valid": valid,
        "clinical": clinical,
        "label": labels,
        "patient_id": [item["patient_id"] for item in batch],
        "source": [item["source"] for item in batch],
    }


def _mask_preop_clinical(clinical: torch.Tensor) -> torch.Tensor:
    """Force Lauren and differentiation to missing. Keeps the 22-d layout."""
    out = clinical.clone()
    for name in PREOP_DROP_FIELDS:
        idx = CLINICAL_FIELDS.index(name)
        out[:, 2 * idx] = 0.0
        out[:, 2 * idx + 1] = 1.0
    return out


def _clinical_batch(
    batch: dict[str, object],
    device: str,
    clinical_dim: int,
    clinical: str = "raw",
) -> torch.Tensor:
    values = batch["clinical"].to(device)
    if clinical_dim == 0:
        return values[:, :0]
    if clinical == "preop" and clinical_dim == 22:
        return _mask_preop_clinical(values)
    return values


def ordinal_rank_loss(logits: torch.Tensor, y: torch.Tensor, n_classes: int = N_CLASSES) -> torch.Tensor:
    prob = torch.softmax(logits, dim=-1)
    ranks = torch.arange(n_classes, device=logits.device, dtype=prob.dtype)
    expected = (prob * ranks).sum(dim=-1)
    return torch.nn.functional.smooth_l1_loss(expected, y.float())


def ordinal_cost_loss(logits: torch.Tensor, y: torch.Tensor, n_classes: int = N_CLASSES) -> torch.Tensor:
    """Expected |class - y| under softmax. Penalizes +1 mass, unlike SmoothL1 on the expected rank."""
    prob = torch.softmax(logits, dim=-1)
    ranks = torch.arange(n_classes, device=logits.device, dtype=prob.dtype)
    cost = (ranks.unsqueeze(0) - y.unsqueeze(1).to(prob.dtype)).abs()
    return (prob * cost).sum(dim=-1).mean()


def t34_pair_loss(logits: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    """Mean probability on the other serosa-adjacent class when the label is T3 or T4+."""
    mask = (y == 2) | (y == 3)
    if not bool(mask.any()):
        return logits.new_zeros(())
    prob = torch.softmax(logits, dim=-1)
    wrong = torch.where(y == 2, prob[:, 3], prob[:, 2])
    return wrong[mask].mean()


def t2_off2_loss(logits: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    """Mean P(T1)+P(T4+) on true T2. Acc_boost made those two jumps the most expensive."""
    mask = y == 1
    if not bool(mask.any()):
        return logits.new_zeros(())
    prob = torch.softmax(logits, dim=-1)
    return (prob[mask, 0] + prob[mask, 3]).mean()


def _is_better(metrics: dict[str, object], best: dict, lock: str) -> bool:
    acc = float(metrics["acc"])
    adj = float(metrics["adj_acc"])
    qwk = float(metrics["qwk"])
    macro = float(metrics["macro_recall"])
    if lock == "adj":
        return adj > float(best["val_adj_acc"]) or (
            adj == float(best["val_adj_acc"]) and acc > float(best["val_acc"])
        )
    if lock == "qwk":
        return qwk > float(best["val_qwk"]) or (qwk == float(best["val_qwk"]) and acc > float(best["val_acc"]))
    if lock == "macro":
        return macro > float(best["val_macro_recall"]) or (
            macro == float(best["val_macro_recall"]) and acc > float(best["val_acc"])
        )
    return acc > float(best["val_acc"]) or (acc == float(best["val_acc"]) and adj > float(best["val_adj_acc"]))


@torch.no_grad()
def evaluate(
    model: torch.nn.Module,
    loader: DataLoader,
    device: str,
    clinical_dim: int = 22,
    clinical: str = "raw",
) -> dict[str, object]:
    model.eval()
    ys: list[int] = []
    preds: list[int] = []
    sources: list[str] = []
    pids: list[str] = []
    for batch in loader:
        logits = model(
            batch["e_full"].to(device),
            batch["e_roi"].to(device),
            batch["valid"].to(device),
            _clinical_batch(batch, device, clinical_dim, clinical=clinical),
        )
        pred = logits.argmax(dim=-1).cpu().numpy().astype(int)
        y = batch["label"].cpu().numpy().astype(int)
        ys.extend(y.tolist())
        preds.extend(pred.tolist())
        sources.extend(batch["source"])
        pids.extend(batch["patient_id"])
    y_arr = np.asarray(ys, dtype=int)
    pred_arr = np.asarray(preds, dtype=int)
    metrics = score_arrays(y_arr, pred_arr)
    metrics["confusion"] = confusion(y_arr, pred_arr)
    metrics["centers"] = per_center(y_arr, pred_arr, sources)
    metrics["predictions"] = [
        {"patient_id": pid, "source": src, "y": int(y), "pred": int(p)}
        for pid, src, y, p in zip(pids, sources, y_arr, pred_arr)
    ]
    return metrics


def _metric_row(name: str, metrics: dict[str, object]) -> str:
    return (
        "| {name} | {n} | {acc:.4f} | {adj:.4f} | {off2:.4f} | {qwk:.4f} | {serosa:.4f} | "
        "{macro:.4f} | {t1:.4f} | {t2:.4f} | {t3:.4f} | {t4:.4f} |"
    ).format(
        name=name,
        n=int(metrics["n"]),
        acc=float(metrics["acc"]),
        adj=float(metrics["adj_acc"]),
        off2=float(metrics["off2"]),
        qwk=float(metrics["qwk"]),
        serosa=float(metrics.get("serosa_acc", 0.0)),
        macro=float(metrics["macro_recall"]),
        t1=float(metrics["recall_T1"]),
        t2=float(metrics["recall_T2"]),
        t3=float(metrics["recall_T3"]),
        t4=float(metrics["recall_T4+"]),
    )


def _write_summary(
    report_dir: Path,
    spec: dict[str, str],
    best: dict,
    evals: dict[str, dict[str, object]],
) -> None:
    lines = [
        f"# MedSigLIP-448 GastricUS {spec['name']}",
        "",
        f"- plan: {spec.get('plan', plan_cell(str(spec.get('fusion', '')), str(spec.get('pool', '')), str(spec.get('head', ''))))}",
        f"- fusion: {spec['fusion']}"
        + (
            ""
            if spec["fusion"] in {"none", "n/a"}
            else f" (plan { {'concat': '4.1', 'interact': '4.2', 'gate': '4.gate', 'pair': '4.pair'}.get(str(spec['fusion']), spec['fusion']) })"
        ),
        f"- pool: {spec['pool']}",
        f"- head: {spec['head']}",
        f"- size: {spec.get('size', 'small')}",
        f"- trainable params: {spec.get('n_params', 0)}",
        f"- class weight: {spec.get('class_weight', 'balanced')}",
        f"- clinical: {spec.get('clinical', 'raw')}",
        f"- pool_proj: {spec.get('pool_proj', True)}",
        f"- ordinal weight: {spec.get('ordinal_weight', 0.0)}",
        f"- ordinal mode: {spec.get('ordinal_mode', 'rank')}",
        f"- t34 weight: {spec.get('t34_weight', 0.0)}",
        f"- t2 off2 weight: {spec.get('t2_off2_weight', 0.0)}",
        f"- aux serosa weight: {spec.get('aux_serosa_weight', 0.0)}",
        f"- best val epoch: {best['epoch']} (lock = val {spec.get('lock', 'acc')}, patience early stop)",
        "",
        "Adjacent ACC counts a prediction correct when `|pred - true| <= 1` on T1=0, T2=1, T3=2, T4+=3. "
        "`off2` is the share of jumps of two or more stages. "
        "`serosa` is T4+ vs not-T4+ accuracy.",
        "",
        "| split | n | ACC | adj ACC | off2 | QWK | serosa | macro-recall | T1 | T2 | T3 | T4+ |",
        "|-------|--:|----:|--------:|-----:|----:|-------:|-------------:|---:|---:|---:|----:|",
    ]
    for name, metrics in evals.items():
        lines.append(_metric_row(name, metrics))
    for name, metrics in evals.items():
        lines += ["", f"## {name} confusion (rows = true)", ""]
        lines += md_confusion(metrics["confusion"])
        lines += ["", f"## {name} by center", ""]
        lines += [
            "| center | n | ACC | adj ACC | off2 | QWK | serosa | macro-recall | T1 | T2 | T3 | T4+ |",
            "|--------|--:|----:|--------:|-----:|----:|-------:|-------------:|---:|---:|---:|----:|",
        ]
        for row in metrics["centers"]:
            lines.append(_metric_row(str(row["center"]), row))
    (report_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _jsonable(value):
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    return value


def _cosine_warmup(epoch: int, epochs: int, warmup: int) -> float:
    if epoch < warmup:
        return float(epoch + 1) / max(warmup, 1)
    progress = (epoch - warmup) / max(epochs - warmup, 1)
    return 0.01 + 0.5 * 0.99 * (1.0 + math.cos(math.pi * progress))


def train(
    device: str = "cuda:0",
    epochs: int = 80,
    batch_size: int = 16,
    lr: float = 2e-4,
    weight_decay: float = 2e-4,
    max_frames: int = 16,
    seed: int = 20260821,
    head: str = "mlp",
    tabpfn_device: str = "cpu",
    fusion: str = "concat",
    pool: str = "gated",
    class_weight: str = "balanced",
    size: str = "xlarge",
    warmup_epochs: int = 8,
    patience: int = 25,
    label_smoothing: float = 0.05,
    grad_clip: float = 1.0,
    lock: str = "acc",
    ordinal_weight: float = 0.5,
    ordinal_mode: str = "rank",
    t34_weight: float = 0.0,
    t2_off2_weight: float = 0.0,
    aux_serosa_weight: float = 0.0,
    pool_proj: bool = False,
    residual: bool = True,
    clinical: str = "raw",
    report_dir: Path | None = None,
    run_name: str = "",
    cache_dir: Path | None = None,
    frame_sample: str = "prefix",
    pool_out: int | None = None,
    extra_map: dict[str, np.ndarray] | None = None,
) -> dict[str, object]:
    """训一个方案格子。默认 4.1 concat + 5.3 gated + 6.1 mlp，与 CLI 一致。"""
    torch.manual_seed(seed)
    np.random.seed(seed)
    if head not in {"mlp", "tabpfn", "tabpfn_time", "tabpfn_both"}:
        raise ValueError(head)
    if lock not in {"acc", "adj", "qwk", "macro"}:
        raise ValueError(lock)
    if ordinal_mode not in {"rank", "cost"}:
        raise ValueError(ordinal_mode)
    if clinical not in {"raw", "none", "preop"}:
        raise ValueError(clinical)
    cache_dir = cache_dir or CACHE_DIR
    tabpfn_map = None
    clinical_dim = 0 if clinical == "none" else 22
    name = run_name or f"{head}_{fusion}_{pool}_{size}"
    if report_dir is None:
        report_dir = TABPFN_REPORT_DIR if head.startswith("tabpfn") else REPORT_DIR
    if head == "tabpfn":
        if clinical == "none":
            raise ValueError("TabPFN head needs clinical rows")
        build_tabpfn_cache(CACHE_DIR, device=tabpfn_device, seed=seed)
        tabpfn_map = load_tabpfn_map(CACHE_DIR)
        clinical_dim = 4
    elif head == "tabpfn_time":
        if clinical == "none":
            raise ValueError("TIME-192 head needs clinical rows")
        time_name = TIME192_PREOP_CACHE if clinical == "preop" else TIME192_CACHE
        drop = PREOP_DROP_FIELDS if clinical == "preop" else ()
        build_time192_cache(
            CACHE_DIR,
            device=tabpfn_device,
            seed=seed,
            drop_fields=drop,
            cache_name=time_name,
        )
        tabpfn_map = load_time192_map(CACHE_DIR, cache_name=time_name)
        clinical_dim = time192_dim(CACHE_DIR, cache_name=time_name)
    elif head == "tabpfn_both":
        if clinical == "none":
            raise ValueError("TabPFN both head needs clinical rows")
        build_tabpfn_cache(CACHE_DIR, device=tabpfn_device, seed=seed)
        build_time192_cache(CACHE_DIR, device=tabpfn_device, seed=seed)
        tabpfn_map = load_tabpfn_both_map(CACHE_DIR)
        clinical_dim = int(next(iter(tabpfn_map.values())).shape[-1])
    if extra_map:
        clinical_dim = int(clinical_dim) + int(next(iter(extra_map.values())).shape[-1])
    train_ds = PatientBagDataset(
        cache_dir / "train_embeddings.npz",
        max_frames=max_frames,
        tabpfn_map=tabpfn_map,
        extra_map=extra_map,
        frame_sample=frame_sample,
        seed=seed,
    )
    val_ds = PatientBagDataset(
        cache_dir / "val_embeddings.npz",
        max_frames=max_frames,
        tabpfn_map=tabpfn_map,
        extra_map=extra_map,
        frame_sample=frame_sample,
        seed=seed,
    )
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, collate_fn=collate)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, collate_fn=collate)
    extra_loaders = {}
    for split_name in ("test_prospective", "test_external"):
        path = cache_dir / f"{split_name}_embeddings.npz"
        if path.is_file():
            extra_loaders[split_name] = DataLoader(
                PatientBagDataset(
                    path,
                    max_frames=max_frames,
                    tabpfn_map=tabpfn_map,
                    extra_map=extra_map,
                    frame_sample=frame_sample,
                    seed=seed,
                ),
                batch_size=batch_size,
                shuffle=False,
                collate_fn=collate,
            )
    embed_dim = int(train_ds[0]["e_full"].shape[-1])
    model = GastricUSFromScratch(
        clinical_dim=clinical_dim,
        fusion=fusion,
        pool=pool,
        size=size,
        pool_proj=pool_proj,
        residual=residual,
        aux_serosa=aux_serosa_weight > 0,
        pool_out=pool_out,
        embed_dim=embed_dim,
    ).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = LambdaLR(opt, lambda epoch: _cosine_warmup(epoch, epochs, warmup_epochs))
    labels = train_ds.labels()
    if class_weight == "balanced":
        counts = Counter(labels)
        weights = [len(labels) / (N_CLASSES * max(counts.get(i, 1), 1)) for i in range(N_CLASSES)]
        loss_fn = torch.nn.CrossEntropyLoss(
            weight=torch.tensor(weights, dtype=torch.float32, device=device),
            label_smoothing=label_smoothing,
        )
    else:
        weights = [1.0] * N_CLASSES
        loss_fn = torch.nn.CrossEntropyLoss(label_smoothing=label_smoothing)
    best = {"val_adj_acc": -1.0, "val_acc": -1.0, "val_qwk": -1.0, "val_macro_recall": -1.0}
    history = []
    report_dir.mkdir(parents=True, exist_ok=True)
    ckpt = report_dir / "best_model.pt"
    spec = {
        "name": name,
        "fusion": fusion,
        "pool": pool,
        "head": head,
        "size": size,
        "n_params": model.n_parameters(),
        "class_weight": class_weight,
        "lr": lr,
        "epochs": epochs,
        "warmup_epochs": warmup_epochs,
        "patience": patience,
        "label_smoothing": label_smoothing,
        "lock": lock,
        "ordinal_weight": ordinal_weight,
        "ordinal_mode": ordinal_mode,
        "t34_weight": t34_weight,
        "t2_off2_weight": t2_off2_weight,
        "aux_serosa_weight": aux_serosa_weight,
        "pool_proj": pool_proj,
        "residual": residual,
        "clinical": clinical,
        "cache_dir": str(cache_dir),
        "frame_sample": frame_sample,
        "pool_out": pool_out,
        "clinical_dim": clinical_dim,
        "embed_dim": embed_dim,
        "extra_clinical": 0 if not extra_map else int(next(iter(extra_map.values())).shape[-1]),
        "plan": plan_cell(fusion, pool, head),
    }
    print(
        f"run {name} size={size} params={spec['n_params']} lock={lock} "
        f"ordinal={ordinal_mode}:{ordinal_weight} t34={t34_weight} t2off2={t2_off2_weight} serosa={aux_serosa_weight} "
        f"clinical={clinical} weights={weights}",
        flush=True,
    )
    stale = 0
    for epoch in range(1, epochs + 1):
        model.train()
        running = 0.0
        seen = 0
        correct = 0
        for batch in train_loader:
            opt.zero_grad(set_to_none=True)
            labels_b = batch["label"].to(device)
            clinical_b = _clinical_batch(batch, device, clinical_dim, clinical=clinical)
            if aux_serosa_weight > 0:
                logits, serosa_logit = model(
                    batch["e_full"].to(device),
                    batch["e_roi"].to(device),
                    batch["valid"].to(device),
                    clinical_b,
                    return_aux=True,
                )
            else:
                logits = model(
                    batch["e_full"].to(device),
                    batch["e_roi"].to(device),
                    batch["valid"].to(device),
                    clinical_b,
                )
            loss = loss_fn(logits, labels_b)
            if ordinal_weight > 0:
                ord_fn = ordinal_cost_loss if ordinal_mode == "cost" else ordinal_rank_loss
                loss = loss + ordinal_weight * ord_fn(logits, labels_b)
            if t34_weight > 0:
                loss = loss + t34_weight * t34_pair_loss(logits, labels_b)
            if t2_off2_weight > 0:
                loss = loss + t2_off2_weight * t2_off2_loss(logits, labels_b)
            if aux_serosa_weight > 0:
                serosa_y = (labels_b >= 3).to(logits.dtype)
                loss = loss + aux_serosa_weight * torch.nn.functional.binary_cross_entropy_with_logits(
                    serosa_logit, serosa_y
                )
            loss.backward()
            if grad_clip > 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
            opt.step()
            running += float(loss.item()) * int(batch["label"].numel())
            seen += int(batch["label"].numel())
            correct += int((logits.detach().argmax(dim=-1) == labels_b).sum().item())
        scheduler.step()
        val_metrics = evaluate(model, val_loader, device, clinical_dim=clinical_dim, clinical=clinical)
        slim = {
            k: val_metrics[k]
            for k in (
                "n",
                "acc",
                "adj_acc",
                "off2",
                "qwk",
                "serosa_acc",
                "t34_swap",
                "macro_recall",
                "t2_recall",
                "recall_T3",
            )
        }
        row = {
            "epoch": epoch,
            "train_loss": running / max(seen, 1),
            "train_acc": correct / max(seen, 1),
            "lr": float(scheduler.get_last_lr()[0]),
            **{f"val_{k}": v for k, v in slim.items()},
        }
        history.append(row)
        print(row, flush=True)
        if _is_better(val_metrics, best, lock):
            best = {
                "val_adj_acc": float(val_metrics["adj_acc"]),
                "val_acc": float(val_metrics["acc"]),
                "val_qwk": float(val_metrics["qwk"]),
                "val_macro_recall": float(val_metrics["macro_recall"]),
                "epoch": epoch,
                "val": slim,
            }
            torch.save({"model": model.state_dict(), "epoch": epoch, "val": slim, "spec": spec}, ckpt)
            stale = 0
        else:
            stale += 1
            if stale >= patience:
                print(f"early stop at epoch {epoch}, best={best['epoch']}", flush=True)
                break
    model.load_state_dict(torch.load(ckpt, map_location=device)["model"])
    final = {
        "best": best,
        "history": history,
        "eval": {"val": evaluate(model, val_loader, device, clinical_dim=clinical_dim, clinical=clinical)},
        "spec": spec,
    }
    for split_name, loader in extra_loaders.items():
        final["eval"][split_name] = evaluate(model, loader, device, clinical_dim=clinical_dim, clinical=clinical)
    for split_name, metrics in final["eval"].items():
        pred_path = report_dir / f"{split_name}_predictions.csv"
        rows = metrics.pop("predictions")
        pred_path.write_text(
            "split,center,patient_id,y,pred,T_true,T_pred,adjacent\n"
            + "".join(
                f"{split_name},{center_of(r['source'])},{r['patient_id']},{r['y']},{r['pred']},"
                f"{CLASS_NAMES[r['y']]},{CLASS_NAMES[r['pred']]},{int(abs(r['y']-r['pred'])<=1)}\n"
                for r in rows
            ),
            encoding="utf-8",
        )
    (report_dir / "metrics.json").write_text(json.dumps(_jsonable(final), indent=2), encoding="utf-8")
    _write_summary(report_dir, spec, best, final["eval"])
    return final


def _compare_markdown(results: list[dict[str, object]]) -> str:
    lines = [
        "# GastricUS plan variants",
        "",
        "Same frozen MedSigLIP-448 cache. Class weight = balanced.",
        "Plan 5.1 (`mean_views`) skips the 4.x fusion MLP and averages the two 1152-d views.",
        "Complete grid uses the current contract: lock validation exact ACC, ordinal rank loss, residual fusion, raw 2304-d mean views.",
        "",
        "Adjacent ACC: `|pred - true| <= 1`. off2: jump of two or more T stages.",
        "",
        "| plan | run | fusion | pool | head | val ACC | val adj | val off2 | val QWK | prosp ACC | prosp adj | ext ACC | ext adj |",
        "|------|-----|--------|------|------|--------:|--------:|---------:|--------:|----------:|----------:|--------:|--------:|",
    ]
    for item in results:
        ev = item["eval"]
        val = ev["val"]
        pro = ev.get("test_prospective", {})
        ext = ev.get("test_external", {})
        spec = item["spec"]
        lines.append(
            "| {plan} | {name} | {fusion} | {pool} | {head} | {va:.4f} | {vad:.4f} | {vo:.4f} | {vq:.4f} | {pa:.4f} | {pad:.4f} | {ea:.4f} | {ead:.4f} |".format(
                plan=spec.get("plan", plan_cell(str(spec["fusion"]), str(spec["pool"]), str(spec["head"]))),
                name=spec["name"],
                fusion=spec["fusion"],
                pool=spec["pool"],
                head=spec["head"],
                va=float(val["acc"]),
                vad=float(val["adj_acc"]),
                vo=float(val["off2"]),
                vq=float(val["qwk"]),
                pa=float(pro.get("acc", 0)),
                pad=float(pro.get("adj_acc", 0)),
                ea=float(ext.get("acc", 0)),
                ead=float(ext.get("adj_acc", 0)),
            )
        )
    lines += ["", "Per-run center tables and confusion matrices are in each run folder `SUMMARY.md`."]
    return "\n".join(lines) + "\n"


LARGECLF_RUNS = (
    {"name": "mlp_xlarge_gated", "head": "mlp", "fusion": "concat", "pool": "gated", "size": "xlarge"},
    {"name": "mlp_wideclf_gated", "head": "mlp", "fusion": "concat", "pool": "gated", "size": "wideclf"},
    {"name": "tabpfn_xlarge_gated", "head": "tabpfn", "fusion": "concat", "pool": "gated", "size": "xlarge"},
    {"name": "tabpfn_xlarge_mean", "head": "tabpfn", "fusion": "concat", "pool": "mean_views", "size": "xlarge"},
)


def train_largeclf_compare(
    device: str = "cuda:0",
    epochs: int = 80,
    batch_size: int = 16,
    lr: float = 2e-4,
    tabpfn_device: str = "cpu",
    warmup_epochs: int = 8,
    patience: int = 25,
    lock: str = "acc",
    ordinal_weight: float = 0.5,
) -> dict[str, object]:
    """Frozen-cache 6.1 wide classifier vs 6.2 TabPFN. Does not unfreeze MedSigLIP."""
    dest_root = LARGECLF_REPORT_DIR
    dest_root.mkdir(parents=True, exist_ok=True)
    (dest_root / "README.md").write_text(
        "\n".join(
            [
                "# Large classifier vs TabPFN (frozen MedSigLIP-448)",
                "",
                "Same 20% encode cache. Encoder stays frozen.",
                "wideclf keeps 4.1/5.3 widths and only widens the 6.1 MLP head.",
                "TabPFN is plan 6.2: clinical-11 -> 4-class probabilities, then MLP with z_image.",
                "Do not promote unless both held-out exact ACCs beat xlarge MLP.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    results = []
    for spec in LARGECLF_RUNS:
        print(f"=== largeclf {spec['name']} size={spec['size']} head={spec['head']} ===", flush=True)
        result = train(
            device=device,
            epochs=epochs,
            batch_size=batch_size,
            lr=lr,
            tabpfn_device=tabpfn_device,
            head=spec["head"],
            fusion=spec["fusion"],
            pool=spec["pool"],
            size=spec["size"],
            warmup_epochs=warmup_epochs,
            patience=patience,
            lock=lock,
            ordinal_weight=ordinal_weight,
            report_dir=dest_root / spec["name"],
            run_name=spec["name"],
        )
        results.append(result)
    lines = [
        "# Large classifier vs TabPFN",
        "",
        "Frozen 1152-d cache. No ViT gradients. Lock = validation exact ACC.",
        "",
        "| run | size | head | params | val ACC | prosp ACC | prosp adj | ext ACC | ext adj |",
        "|-----|------|------|-------:|--------:|----------:|----------:|--------:|--------:|",
    ]
    for item in results:
        ev = item["eval"]
        spec = item["spec"]
        val = ev["val"]
        pro = ev.get("test_prospective", {})
        ext = ev.get("test_external", {})
        lines.append(
            "| {name} | {size} | {head} | {n:,} | {va:.4f} | {pa:.4f} | {pad:.4f} | {ea:.4f} | {ead:.4f} |".format(
                name=spec["name"],
                size=spec["size"],
                head=spec["head"],
                n=int(spec.get("n_params", 0)),
                va=float(val["acc"]),
                pa=float(pro.get("acc", 0)),
                pad=float(pro.get("adj_acc", 0)),
                ea=float(ext.get("acc", 0)),
                ead=float(ext.get("adj_acc", 0)),
            )
        )
    lines += ["", "Per-run `SUMMARY.md` has confusion matrices. CLI default stays xlarge MLP."]
    compare = "\n".join(lines) + "\n"
    (dest_root / "COMPARE.md").write_text(compare, encoding="utf-8")
    print(compare, flush=True)
    return {"runs": [r["spec"]["name"] for r in results], "report": str(dest_root)}


def train_plan_sweep(
    device: str = "cuda:0",
    epochs: int = 80,
    batch_size: int = 16,
    lr: float = 2e-4,
    tabpfn_device: str = "cpu",
    size: str = "xlarge",
    warmup_epochs: int = 8,
    patience: int = 25,
    lock: str = "acc",
    ordinal_weight: float = 0.5,
    pool_proj: bool = False,
    residual: bool = True,
    clinical: str = "raw",
    report_dir: Path | None = None,
) -> dict[str, object]:
    """方案 4.x / 5.x / 6.x 完整唯一网格。5.1 跳过融合。合同与默认 train 相同。"""
    dest_root = report_dir or PLAN_COMPLETE_REPORT_DIR
    dest_root.mkdir(parents=True, exist_ok=True)
    grid_lines = [
        "# Plan complete grid",
        "",
        "One unique cell per `GastricUS实验方案.md` 4.x / 5.x / 6.x combination.",
        "Plan 5.1 does not use the 4.1 / 4.2 fusion MLP, so `interact + mean_views` is omitted.",
        "",
        f"- size: {size}",
        f"- residual: {residual}",
        f"- lock: {lock}",
        f"- ordinal_weight: {ordinal_weight}",
        f"- pool_proj: {pool_proj}",
        f"- clinical: {clinical}",
        "",
        "| plan | run | fusion | pool | head |",
        "|------|-----|--------|------|------|",
    ]
    for spec in PLAN_RUNS:
        grid_lines.append(
            f"| {plan_cell(spec['fusion'], spec['pool'], spec['head'])} | {spec['name']} | "
            f"{spec['fusion']} | {spec['pool']} | {spec['head']} |"
        )
    (dest_root / "PLAN_GRID.md").write_text("\n".join(grid_lines) + "\n", encoding="utf-8")
    results = []
    for spec in PLAN_RUNS:
        dest = dest_root / spec["name"]
        print(f"=== {spec['name']} plan={plan_cell(spec['fusion'], spec['pool'], spec['head'])} size={size} ===", flush=True)
        result = train(
            device=device,
            epochs=epochs,
            batch_size=batch_size,
            lr=lr,
            head=spec["head"],
            tabpfn_device=tabpfn_device,
            fusion=spec["fusion"],
            pool=spec["pool"],
            class_weight="balanced",
            size=size,
            warmup_epochs=warmup_epochs,
            patience=patience,
            lock=lock,
            ordinal_weight=ordinal_weight,
            pool_proj=pool_proj,
            residual=residual,
            clinical=clinical,
            report_dir=dest,
            run_name=spec["name"],
        )
        results.append(result)
    compare = _compare_markdown(results)
    (dest_root / "COMPARE.md").write_text(compare, encoding="utf-8")
    print(compare, flush=True)
    return {"runs": [r["spec"]["name"] for r in results], "report": str(dest_root), "size": size}


def train_opt_sweep(
    device: str = "cuda:0",
    epochs: int = 80,
    batch_size: int = 16,
    lr: float = 2e-4,
    size: str = "xlarge",
    warmup_epochs: int = 8,
    patience: int = 25,
    lock: str = "acc",
    ordinal_weight: float = 0.5,
) -> dict[str, object]:
    dest_root = OPT_REPORT_DIR
    dest_root.mkdir(parents=True, exist_ok=True)
    results = []
    for spec in OPT_RUNS:
        dest = dest_root / spec["name"]
        print(f"=== opt {spec['name']} size={size} ===", flush=True)
        result = train(
            device=device,
            epochs=epochs,
            batch_size=batch_size,
            lr=lr,
            head=spec["head"],
            fusion=spec["fusion"],
            pool=spec["pool"],
            class_weight="balanced",
            size=size,
            warmup_epochs=warmup_epochs,
            patience=patience,
            lock=lock,
            ordinal_weight=ordinal_weight,
            pool_proj=False,
            residual=True,
            clinical=spec.get("clinical", "raw"),
            report_dir=dest,
            run_name=spec["name"],
        )
        results.append(result)
    compare = _compare_markdown(results)
    (dest_root / "COMPARE.md").write_text(compare, encoding="utf-8")
    print(compare, flush=True)
    return {"runs": [r["spec"]["name"] for r in results], "report": str(dest_root), "size": size}


def _t34_compare_markdown(results: list[dict[str, object]]) -> str:
    lines = [
        "# GastricUS T3/T4 levers",
        "",
        "Same frozen MedSigLIP-448 cache and xlarge concat head as the 2026-08-21 opt default.",
        "This sweep changes lock, ordinal cost, T3/T4 pair loss, and a serosa auxiliary head.",
        "It does not widen the MLP again.",
        "",
        "serosa: T4+ vs not-T4+. t34_swap: share of T3↔T4+ swaps among all patients.",
        "",
        "| run | lock | ordinal | t34 | serosa_w | val ACC | val T3 | val serosa | prosp ACC | prosp T3 | prosp serosa | prosp t34_swap | ext ACC | ext T3 | ext serosa |",
        "|-----|------|---------|----:|---------:|--------:|-------:|-----------:|----------:|---------:|-------------:|---------------:|--------:|-------:|-----------:|",
    ]
    for item in results:
        ev = item["eval"]
        val = ev["val"]
        pro = ev.get("test_prospective", {})
        ext = ev.get("test_external", {})
        spec = item["spec"]
        lines.append(
            "| {name} | {lock} | {omode}:{ow} | {t34:.1f} | {sw:.1f} | {va:.4f} | {vt3:.4f} | {vs:.4f} | "
            "{pa:.4f} | {pt3:.4f} | {ps:.4f} | {psw:.4f} | {ea:.4f} | {et3:.4f} | {es:.4f} |".format(
                name=spec["name"],
                lock=spec.get("lock", "acc"),
                omode=spec.get("ordinal_mode", "rank"),
                ow=spec.get("ordinal_weight", 0.0),
                t34=float(spec.get("t34_weight", 0.0)),
                sw=float(spec.get("aux_serosa_weight", 0.0)),
                va=float(val["acc"]),
                vt3=float(val.get("recall_T3", 0.0)),
                vs=float(val.get("serosa_acc", 0.0)),
                pa=float(pro.get("acc", 0.0)),
                pt3=float(pro.get("recall_T3", 0.0)),
                ps=float(pro.get("serosa_acc", 0.0)),
                psw=float(pro.get("t34_swap", 0.0)),
                ea=float(ext.get("acc", 0.0)),
                et3=float(ext.get("recall_T3", 0.0)),
                es=float(ext.get("serosa_acc", 0.0)),
            )
        )
    lines += ["", "Per-run confusion matrices are in each run folder `SUMMARY.md`."]
    return "\n".join(lines) + "\n"


def train_t34_sweep(
    device: str = "cuda:0",
    epochs: int = 80,
    batch_size: int = 16,
    lr: float = 2e-4,
    size: str = "xlarge",
    warmup_epochs: int = 8,
    patience: int = 25,
) -> dict[str, object]:
    dest_root = T34_REPORT_DIR
    dest_root.mkdir(parents=True, exist_ok=True)
    results = []
    for spec in T34_RUNS:
        dest = dest_root / spec["name"]
        print(f"=== t34 {spec['name']} size={size} ===", flush=True)
        result = train(
            device=device,
            epochs=epochs,
            batch_size=batch_size,
            lr=lr,
            head="mlp",
            fusion=spec["fusion"],
            pool=spec["pool"],
            class_weight="balanced",
            size=size,
            warmup_epochs=warmup_epochs,
            patience=patience,
            lock=spec["lock"],
            ordinal_weight=float(spec["ordinal_weight"]),
            ordinal_mode=spec["ordinal_mode"],
            t34_weight=float(spec["t34_weight"]),
            aux_serosa_weight=float(spec["aux_serosa_weight"]),
            pool_proj=False,
            residual=True,
            clinical=spec.get("clinical", "raw"),
            report_dir=dest,
            run_name=spec["name"],
        )
        results.append(result)
    compare = _t34_compare_markdown(results)
    (dest_root / "COMPARE.md").write_text(compare, encoding="utf-8")
    print(compare, flush=True)
    return {"runs": [r["spec"]["name"] for r in results], "report": str(dest_root), "size": size}


RETRY_RUNS = (
    {"name": "tabpfn_mean_e15", "fusion": "concat", "pool": "mean_views", "head": "tabpfn", "size": "xlarge", "cache": "expand15"},
    {"name": "tabpfn_mean_e25", "fusion": "concat", "pool": "mean_views", "head": "tabpfn", "size": "xlarge", "cache": "expand25"},
    {"name": "mlp_mean_e15", "fusion": "concat", "pool": "mean_views", "head": "mlp", "size": "xlarge", "cache": "expand15"},
    {"name": "tabpfn_mean_avgroi", "fusion": "concat", "pool": "mean_views", "head": "tabpfn", "size": "xlarge", "cache": "avgroi"},
    {"name": "tabpfn_mean_arearoi", "fusion": "concat", "pool": "mean_views", "head": "tabpfn", "size": "xlarge", "cache": "arearoi"},
    {"name": "mlp_gate_gated", "fusion": "gate", "pool": "gated", "head": "mlp", "size": "xlarge", "cache": "20"},
    {"name": "mlp_pair_gated", "fusion": "pair", "pool": "gated", "head": "mlp", "size": "xlarge", "cache": "20"},
    {"name": "mlp_concat_meanu", "fusion": "concat", "pool": "mean_u", "head": "mlp", "size": "xlarge", "cache": "20"},
    {"name": "tabpfn_concat_meanu", "fusion": "concat", "pool": "mean_u", "head": "tabpfn", "size": "xlarge", "cache": "20"},
    {"name": "mlp_concat_attnonly", "fusion": "concat", "pool": "attn_only", "head": "mlp", "size": "xlarge", "cache": "20"},
    {"name": "mlp_mid_gated", "fusion": "concat", "pool": "gated", "head": "mlp", "size": "mid", "cache": "20"},
    {"name": "mlp_gate_meanu", "fusion": "gate", "pool": "mean_u", "head": "mlp", "size": "xlarge", "cache": "20"},
)


def _retry_cache(name: str) -> Path:
    if name == "expand15":
        return cache_dir_for_expand(0.15)
    if name == "expand25":
        return cache_dir_for_expand(0.25)
    if name == "avgroi":
        return AVGROI_CACHE_DIR
    if name == "arearoi":
        return AREAROI_CACHE_DIR
    return CACHE_DIR


def train_retry_sweep(
    device: str = "cuda:0",
    epochs: int = 80,
    batch_size: int = 16,
    lr: float = 2e-4,
    tabpfn_device: str = "cpu",
    warmup_epochs: int = 8,
    patience: int = 25,
    lock: str = "acc",
    ordinal_weight: float = 0.5,
) -> dict[str, object]:
    """New fusion / pool / ROI mixes on frozen caches. Does not change the CLI default."""
    from .mix_expand import merge_area_roi, merge_avg_roi

    if not (AVGROI_CACHE_DIR / "train_embeddings.npz").is_file():
        print("mix-avg", merge_avg_roi(), flush=True)
    if not (AREAROI_CACHE_DIR / "train_embeddings.npz").is_file():
        print("mix-area", merge_area_roi(), flush=True)
    dest_root = RETRY_REPORT_DIR
    dest_root.mkdir(parents=True, exist_ok=True)
    (dest_root / "README.md").write_text(
        "\n".join(
            [
                "# Retry sweep: new fusion, pooling, and ROI mixes",
                "",
                "Frozen MedSigLIP-448. No ViT gradients. Lock = validation exact ACC.",
                "Compares 15/25% ROI with the winning 5.1 x 6.2 cell, mixed ROI tokens,",
                "gate / pair fusion, mean-of-u, attention-only, and a mid-size frame transformer.",
                "Do not promote unless both held-out exact ACCs beat 5.1 x 6.2 (0.6424 / 0.5856).",
                "",
            ]
        ),
        encoding="utf-8",
    )
    results = []
    for spec in RETRY_RUNS:
        cache = _retry_cache(str(spec["cache"]))
        print(
            f"=== retry {spec['name']} fusion={spec['fusion']} pool={spec['pool']} "
            f"head={spec['head']} cache={spec['cache']} ===",
            flush=True,
        )
        result = train(
            device=device,
            epochs=epochs,
            batch_size=batch_size,
            lr=lr,
            tabpfn_device=tabpfn_device,
            head=spec["head"],
            fusion=spec["fusion"],
            pool=spec["pool"],
            size=spec["size"],
            warmup_epochs=warmup_epochs,
            patience=patience,
            lock=lock,
            ordinal_weight=ordinal_weight,
            cache_dir=cache,
            report_dir=dest_root / spec["name"],
            run_name=spec["name"],
        )
        result["spec"]["cache"] = spec["cache"]
        results.append(result)
    lines = [
        "# Retry sweep",
        "",
        "Frozen 1152-d caches. New fusion / pool / ROI mixes. Lock = validation exact ACC.",
        "Reference: plan-complete 5.1 x 6.2 TabPFN mean 0.6424 / 0.5856; default gated MLP 0.5976 / 0.5216.",
        "",
        "| run | cache | fusion | pool | head | size | params | val ACC | prosp ACC | prosp adj | ext ACC | ext adj |",
        "|-----|-------|--------|------|------|------|-------:|--------:|----------:|----------:|--------:|--------:|",
    ]
    for item in results:
        ev = item["eval"]
        spec = item["spec"]
        val = ev["val"]
        pro = ev.get("test_prospective", {})
        ext = ev.get("test_external", {})
        lines.append(
            "| {name} | {cache} | {fusion} | {pool} | {head} | {size} | {n:,} | {va:.4f} | {pa:.4f} | {pad:.4f} | {ea:.4f} | {ead:.4f} |".format(
                name=spec["name"],
                cache=spec.get("cache", "20"),
                fusion=spec["fusion"],
                pool=spec["pool"],
                head=spec["head"],
                size=spec.get("size", "xlarge"),
                n=int(spec.get("n_params", 0)),
                va=float(val["acc"]),
                pa=float(pro.get("acc", 0)),
                pad=float(pro.get("adj_acc", 0)),
                ea=float(ext.get("acc", 0)),
                ead=float(ext.get("adj_acc", 0)),
            )
        )
    lines += ["", "Per-run `SUMMARY.md` has confusion matrices. CLI default stays xlarge concat + gated + MLP."]
    compare = "\n".join(lines) + "\n"
    (dest_root / "COMPARE.md").write_text(compare, encoding="utf-8")
    print(compare, flush=True)
    return {"runs": [r["spec"]["name"] for r in results], "report": str(dest_root)}
