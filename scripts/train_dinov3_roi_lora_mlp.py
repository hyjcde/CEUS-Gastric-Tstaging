#!/usr/bin/env python3
"""Train a ROI DINOv3 classifier: frozen backbone + LoRA + two-layer MLP.

Uses the existing full-frame segmentation checkpoint as initialization, Phase-0
patient splits, and `roi_path` (GT crop_roi). No TabPFN / BETA. Research only.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
import yaml
from PIL import Image, ImageEnhance
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    cohen_kappa_score,
    f1_score,
    roc_auc_score,
)
from torch.utils.data import DataLoader, Dataset


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "pipeline") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "pipeline"))
from lib.datasets import DATASET_IMAGE_DIRS, SOURCE_TO_DATASET_CANDIDATES  # noqa: E402
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "segmentation" / "dinov3" / "vitb16_last2blocks_mlp_decoder.yaml"
DEFAULT_SEG_CKPT = (
    PROJECT_ROOT
    / "experiments"
    / "segmentation"
    / "segmentation_dinov3_vitb16_last2blocks_holdout_cropui_dataset_v20260409_20260511_r001"
    / "checkpoints"
    / "best.pt"
)
M025_SEG_CKPT = (
    PROJECT_ROOT
    / "experiments"
    / "segmentation"
    / "dinov3_vitb16_roi_lora_mlp_512_m025_20260828_full"
    / "checkpoints"
    / "best.pt"
)
PHASE0_DIR = PROJECT_ROOT / "pipeline" / "data" / "tstaging_4class_screened_eval_phase0_xiehe_20260610"
DEFAULT_OUTPUT = PROJECT_ROOT / "pipeline" / "experiments" / "reports" / "dinov3_roi_lora_mlp"
CLASS_NAMES = ["T1", "T2", "T3", "T4+"]
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--train-csv", type=Path, default=PHASE0_DIR / "train.csv")
    parser.add_argument("--val-csv", type=Path, default=PHASE0_DIR / "val.csv")
    parser.add_argument("--test-csv", type=Path, default=PHASE0_DIR / "test_prospective.csv")
    parser.add_argument("--external-csv", type=Path, default=PHASE0_DIR / "test_external.csv")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--init-seg-ckpt", type=Path, default=DEFAULT_SEG_CKPT)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--device", default="cuda:0" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--image-size", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--lora-rank", type=int, default=8)
    parser.add_argument("--lora-alpha", type=float, default=16.0)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument("--lora-blocks", type=int, default=4)
    parser.add_argument("--mlp-hidden", type=int, default=512)
    parser.add_argument("--mlp-dropout", type=float, default=0.2)
    parser.add_argument("--max-train-rows", type=int, default=None)
    parser.add_argument("--max-val-rows", type=int, default=None)
    parser.add_argument("--max-test-rows", type=int, default=None)
    parser.add_argument("--skip-external", action="store_true")
    parser.add_argument("--seed", type=int, default=20260828)
    parser.add_argument("--amp", action="store_true", default=True)
    parser.add_argument("--no-amp", action="store_false", dest="amp")
    parser.add_argument(
        "--allow-external-train-val",
        action="store_true",
        help="Allow ext/* rows in train/val. Legacy audit only.",
    )
    parser.add_argument(
        "--frozen-embedding",
        action="store_true",
        help="Inject LoRA, load init ckpt (including lora_A/B), freeze backbone+LoRA, train MLP only.",
    )
    parser.add_argument(
        "--continue-lora",
        action="store_true",
        help="Inject LoRA, load init ckpt including lora_A/B, keep LoRA and last-block LayerNorms trainable.",
    )
    parser.add_argument(
        "--full-coverage-roi",
        action="store_true",
        default=True,
        help="Keep every labeled row: official crop_roi, else mask box on crop_ui, else CSV image.",
    )
    parser.add_argument(
        "--official-roi-only",
        action="store_false",
        dest="full_coverage_roi",
        help="Drop rows without a resolvable official crop_roi (legacy Gate A coverage).",
    )
    parser.add_argument("--lora-lr", type=float, default=None, help="If set, LoRA/LN use this lr; MLP uses --lr.")
    parser.add_argument(
        "--input-blur-sigma",
        type=float,
        default=None,
        help="Gaussian blur sigma applied to input images (deblur-MAE transfer protocol, arXiv:2306.08249). "
        "Overrides config model.input_blur_sigma. 0 disables.",
    )
    return parser.parse_args()


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return payload


def resolve_path(value: object) -> Path | None:
    if value is None or pd.isna(value) or not str(value).strip():
        return None
    path = Path(str(value))
    if path.exists():
        return path
    if not path.is_absolute():
        candidate = PROJECT_ROOT / path
        if candidate.exists():
            return candidate
    return None


_ROI_INDEX: dict[tuple[str, str], Path] | None = None
_STEM_ID_RE = re.compile(r"(\d+)(?:-{1,2}(\d+))?$")


def tokens_from_name(name: str) -> list[str]:
    stem = Path(str(name)).stem.replace("_roi", "")
    tokens: list[str] = []
    match = _STEM_ID_RE.search(stem)
    if match:
        tokens.append(match.group(1))
        if match.group(2):
            tokens.append(f"{match.group(1)}-{match.group(2)}")
            tokens.append(f"{match.group(1)}--{match.group(2)}")
    tail = stem.split("__")[-1]
    if tail and tail not in tokens:
        tokens.append(tail)
    return [tok for tok in dict.fromkeys(tokens) if tok]


def roi_inventory() -> dict[tuple[str, str], Path]:
    global _ROI_INDEX
    if _ROI_INDEX is not None:
        return _ROI_INDEX
    index: dict[tuple[str, str], Path] = {}
    for dataset_key, ui_dir in DATASET_IMAGE_DIRS.items():
        roi_dir = Path(str(ui_dir).replace("/crop_ui/", "/crop_roi/"))
        if not roi_dir.exists():
            continue
        for path in roi_dir.iterdir():
            if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue
            for token in tokens_from_name(path.name):
                index.setdefault((dataset_key, token), path)
    _ROI_INDEX = index
    return index


def resolve_roi_path(row: pd.Series) -> Path | None:
    direct = resolve_path(row.get("roi_path"))
    if direct is not None:
        return direct
    source = str(row.get("source", ""))
    keys = list(SOURCE_TO_DATASET_CANDIDATES.get(source, ()))
    tokens: list[str] = []
    for value in (row.get("roi_path"), row.get("image_path"), row.get("patient_id")):
        tokens.extend(tokens_from_name(str(value or "")))
    index = roi_inventory()
    for key in keys:
        for token in tokens:
            hit = index.get((key, token))
            if hit is not None:
                return hit
    return None


_OFFICIAL_UI_INDEX: dict[tuple[str, str], Path] | None = None


def official_ui_index() -> dict[tuple[str, str], Path]:
    global _OFFICIAL_UI_INDEX
    if _OFFICIAL_UI_INDEX is not None:
        return _OFFICIAL_UI_INDEX
    index: dict[tuple[str, str], Path] = {}
    for dataset_key, ui_dir in DATASET_IMAGE_DIRS.items():
        if ui_dir is None or not ui_dir.exists():
            continue
        for path in ui_dir.iterdir():
            if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue
            for token in tokens_from_name(path.name):
                index.setdefault((dataset_key, token), path)
    _OFFICIAL_UI_INDEX = index
    return index


def official_crop_ui(row: pd.Series) -> Path | None:
    source = str(row.get("source", ""))
    keys = list(SOURCE_TO_DATASET_CANDIDATES.get(source, ()))
    tokens = tokens_from_name(str(row.get("image_path") or "")) + tokens_from_name(
        str(row.get("patient_id") or "")
    )
    index = official_ui_index()
    for key in keys:
        for token in tokens:
            hit = index.get((key, token))
            if hit is not None:
                return hit
    return None


def mask_for_crop_ui(image_path: Path) -> Path | None:
    if image_path.parent.name != "images" or image_path.parent.parent.name != "crop_ui":
        return None
    for folder in ("roi_masks", "masks"):
        for suffix in (".png", ".jpg"):
            candidate = image_path.parent.parent / folder / f"{image_path.stem}{suffix}"
            if candidate.is_file():
                return candidate
    return None


def crop_from_mask(
    image: Image.Image,
    mask: Image.Image,
    *,
    margin_ratio: float = 0.25,
    min_margin: int = 16,
    min_size: int = 96,
) -> Image.Image:
    if mask.size != image.size:
        mask = mask.resize(image.size, Image.NEAREST)
    arr = np.asarray(mask.convert("L"), dtype=np.uint8) > 0
    width, height = image.size
    if not arr.any():
        return image
    ys, xs = np.where(arr)
    x1, y1, x2, y2 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    lesion_w = max(1, x2 - x1)
    lesion_h = max(1, y2 - y1)
    margin = max(int(round(max(lesion_w, lesion_h) * margin_ratio)), int(min_margin))
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    crop_w = max(lesion_w + 2 * margin, int(min_size))
    crop_h = max(lesion_h + 2 * margin, int(min_size))
    nx1 = int(round(cx - crop_w / 2.0))
    ny1 = int(round(cy - crop_h / 2.0))
    nx2 = int(round(cx + crop_w / 2.0))
    ny2 = int(round(cy + crop_h / 2.0))
    if nx1 < 0:
        nx2 -= nx1
        nx1 = 0
    if ny1 < 0:
        ny2 -= ny1
        ny1 = 0
    if nx2 > width:
        nx1 -= nx2 - width
        nx2 = width
    if ny2 > height:
        ny1 -= ny2 - height
        ny2 = height
    nx1 = max(0, nx1)
    ny1 = max(0, ny1)
    nx2 = min(width, max(nx1 + 1, nx2))
    ny2 = min(height, max(ny1 + 1, ny2))
    return image.crop((nx1, ny1, nx2, ny2))


def load_roi_rgb(row: pd.Series) -> Image.Image | None:
    """Official crop_roi, else mask box on crop_ui (0.25/16), else CSV image."""
    direct = resolve_roi_path(row)
    if direct is not None:
        return Image.open(direct).convert("RGB")
    official = official_crop_ui(row)
    if official is not None:
        image = Image.open(official).convert("RGB")
        mask_path = mask_for_crop_ui(official)
        if mask_path is not None:
            return crop_from_mask(image, Image.open(mask_path))
        return image
    legacy = resolve_path(row.get("image_path"))
    if legacy is not None:
        return Image.open(legacy).convert("RGB")
    return None


def row_has_roi(row: pd.Series) -> bool:
    return (
        resolve_roi_path(row) is not None
        or official_crop_ui(row) is not None
        or resolve_path(row.get("image_path")) is not None
    )


def apply_gaussian_blur(image: Image.Image, sigma: float) -> Image.Image:
    """Match DeblurringMIM blurred_images.py: grayscale -> cv2.GaussianBlur((0,0), sigma) -> RGB."""
    import cv2

    arr = np.asarray(image.convert("L"), dtype=np.uint8)
    arr = cv2.GaussianBlur(arr, (0, 0), sigma)
    return Image.fromarray(arr, mode="L").convert("RGB")


def letterbox_rgb(image: Image.Image, size: int) -> Image.Image:
    w, h = image.size
    scale = min(size / max(w, 1), size / max(h, 1))
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    resized = image.resize((nw, nh), Image.BILINEAR)
    canvas = Image.new("RGB", (size, size), (0, 0, 0))
    canvas.paste(resized, ((size - nw) // 2, (size - nh) // 2))
    return canvas


def mild_augment(image: Image.Image, rng: random.Random) -> Image.Image:
    size = image.size
    angle = rng.uniform(-8.0, 8.0)
    image = image.rotate(angle, resample=Image.BILINEAR, fillcolor=(0, 0, 0))
    max_shift = max(1, int(round(size[0] * 0.05)))
    dx = rng.randint(-max_shift, max_shift)
    dy = rng.randint(-max_shift, max_shift)
    image = image.transform(size, Image.AFFINE, (1, 0, dx, 0, 1, dy), resample=Image.BILINEAR, fillcolor=(0, 0, 0))
    scale = rng.uniform(0.95, 1.05)
    if abs(scale - 1.0) > 1e-3:
        nw = max(1, int(round(size[0] * scale)))
        nh = max(1, int(round(size[1] * scale)))
        scaled = image.resize((nw, nh), Image.BILINEAR)
        canvas = Image.new("RGB", size, (0, 0, 0))
        canvas.paste(scaled, ((size[0] - nw) // 2, (size[1] - nh) // 2))
        image = canvas
    image = ImageEnhance.Brightness(image).enhance(rng.uniform(0.90, 1.10))
    image = ImageEnhance.Contrast(image).enhance(rng.uniform(0.90, 1.10))
    return image


def assert_no_external_rows(csv_path: Path, split_name: str, allow: bool) -> None:
    df = pd.read_csv(csv_path, low_memory=False, usecols=lambda col: col == "source")
    if "source" not in df.columns:
        return
    external = df["source"].astype(str).str.startswith("ext/")
    if external.any() and not allow:
        counts = df.loc[external, "source"].astype(str).value_counts().to_dict()
        raise RuntimeError(
            f"{split_name} contains ext/* rows in {csv_path}: {counts}. "
            "Use Phase 0 or pass --allow-external-train-val."
        )


def load_split_frame(csv_path: Path, max_rows: int | None, seed: int, *, full_coverage: bool) -> pd.DataFrame:
    df = pd.read_csv(csv_path, low_memory=False)
    df["class_label"] = pd.to_numeric(df["class_label"], errors="coerce")
    df = df[df["class_label"].notna()].copy()
    if full_coverage:
        keep = [row_has_roi(row) for _, row in df.iterrows()]
        df = df.loc[np.asarray(keep)].copy()
        df["resolved_roi_path"] = ""
    else:
        resolved = [resolve_roi_path(row) for _, row in df.iterrows()]
        df["resolved_roi_path"] = [str(path) if path is not None else "" for path in resolved]
        df = df[df["resolved_roi_path"].astype(str).str.len() > 0].copy()
    if max_rows is not None and len(df) > max_rows:
        df = df.sample(n=max_rows, random_state=seed).reset_index(drop=True)
    return df.reset_index(drop=True)


class RoiDataset(Dataset):
    def __init__(
        self,
        csv_path: Path,
        image_size: int,
        augment: bool,
        max_rows: int | None,
        seed: int,
        *,
        full_coverage: bool = True,
        blur_sigma: float = 0.0,
    ) -> None:
        self.df = load_split_frame(csv_path, max_rows, seed, full_coverage=full_coverage)
        if self.df.empty:
            raise RuntimeError(f"No usable ROI rows in {csv_path}")
        self.image_size = int(image_size)
        self.augment = bool(augment)
        self.seed = int(seed)
        self.full_coverage = bool(full_coverage)
        self.blur_sigma = float(blur_sigma)

    def __len__(self) -> int:
        return len(self.df)

    def __getitem__(self, index: int) -> dict[str, Any]:
        row = self.df.iloc[index]
        if self.full_coverage:
            image = load_roi_rgb(row)
        else:
            path = resolve_path(row.get("resolved_roi_path")) or resolve_roi_path(row)
            image = Image.open(path).convert("RGB") if path is not None else None
        if image is None:
            raise FileNotFoundError(row.get("image_path") or row.get("roi_path"))
        if self.blur_sigma > 0:
            image = apply_gaussian_blur(image, self.blur_sigma)
        image = letterbox_rgb(image, self.image_size)
        if self.augment:
            rng = random.Random(self.seed + index * 997 + int(row.get("class_label", 0)))
            image = mild_augment(image, rng)
            image = letterbox_rgb(image, self.image_size)
        arr = np.asarray(image, dtype=np.float32) / 255.0
        arr = (arr - IMAGENET_MEAN) / IMAGENET_STD
        return {
            "image": torch.from_numpy(arr).permute(2, 0, 1).contiguous(),
            "label": torch.tensor(int(row["class_label"]), dtype=torch.long),
            "patient_id": str(row.get("patient_id", "")),
            "sample_id": str(row.get("sample_id", row.get("image_path", index))),
        }


class LoRALinear(nn.Module):
    def __init__(self, linear: nn.Linear, rank: int, alpha: float, dropout: float) -> None:
        super().__init__()
        if linear.weight is None:
            raise ValueError("LoRALinear expects a Linear with weight")
        self.linear = linear
        self.in_features = linear.in_features
        self.out_features = linear.out_features
        for param in self.linear.parameters():
            param.requires_grad = False
        self.scale = float(alpha) / float(rank)
        self.dropout = nn.Dropout(dropout) if dropout > 0 else nn.Identity()
        self.lora_A = nn.Parameter(torch.empty(rank, linear.in_features))
        self.lora_B = nn.Parameter(torch.zeros(linear.out_features, rank))
        nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        delta = self.dropout(x) @ self.lora_A.t() @ self.lora_B.t()
        return self.linear(x) + delta * self.scale


class RoiLoraMlp(nn.Module):
    def __init__(self, backbone: nn.Module, embed_dim: int, hidden_dim: int, dropout: float, class_count: int = 4) -> None:
        super().__init__()
        self.backbone = backbone
        self.head = nn.Sequential(
            nn.LayerNorm(embed_dim * 2),
            nn.Linear(embed_dim * 2, hidden_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, class_count),
        )

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        if getattr(self.backbone, "_us_family", "dinov3") == "timm_mae":
            # timm ViT: forward_features returns normed [B, 1+N, C] (cls at 0).
            feats = self.backbone.forward_features(images)
            cls_token = feats[:, 0]
            patches = feats[:, 1:]
        else:
            layer = self.backbone.get_intermediate_layers(
                images, n=1, reshape=False, return_class_token=True, norm=True
            )[-1]
            patches, cls_token = layer
        pooled = torch.cat([cls_token, patches.mean(dim=1)], dim=1)
        return self.head(pooled)


def inject_lora(
    backbone: nn.Module,
    last_n: int,
    rank: int,
    alpha: float,
    dropout: float,
    *,
    train_norms: bool = True,
) -> int:
    if not hasattr(backbone, "blocks"):
        raise RuntimeError("DINOv3 backbone has no .blocks")
    replaced = 0
    for block in backbone.blocks[-last_n:]:
        attn = block.attn
        for name in ("qkv", "proj"):
            module = getattr(attn, name, None)
            if isinstance(module, nn.Linear):
                setattr(attn, name, LoRALinear(module, rank, alpha, dropout))
                replaced += 1
        if not train_norms:
            continue
        for norm_name in ("norm1", "norm2"):
            norm = getattr(block, norm_name, None)
            if norm is None:
                continue
            for param in norm.parameters():
                param.requires_grad = True
    if replaced == 0:
        raise RuntimeError("LoRA injection found no qkv/proj Linear modules")
    return replaced


def overlay_backbone_state(raw: dict[str, Any]) -> dict[str, Any]:
    overlay = {}
    for key, value in raw.items():
        name = str(key)
        if name.startswith("backbone."):
            overlay[name[len("backbone.") :]] = value
    return overlay


def load_timm_mae_backbone(model_cfg: dict[str, Any], pretrained: Path) -> nn.Module:
    """timm ViT-B/16 encoder from a (deblur-)MAE checkpoint; key-compatible state_dict."""
    import timm

    timm_model = str(model_cfg.get("timm_model", "vit_base_patch16_224"))
    backbone = timm.create_model(
        timm_model, pretrained=False, num_classes=0, global_pool="", dynamic_img_size=True
    )
    raw = torch.load(pretrained, map_location="cpu", weights_only=False)
    state = raw.get("model", raw) if isinstance(raw, dict) else raw
    state = {k: v for k, v in state.items() if not str(k).startswith(("decoder", "mask_token", "head"))}
    result = backbone.load_state_dict(state, strict=True)
    backbone._us_family = "timm_mae"
    print(
        json.dumps(
            {
                "backbone_family": "timm_mae",
                "timm_model": timm_model,
                "weights": str(pretrained),
                "missing": list(result.missing_keys),
                "unexpected": list(result.unexpected_keys),
            }
        ),
        flush=True,
    )
    return backbone


def load_backbone(
    config: dict[str, Any],
    init_seg_ckpt: Path,
    device: torch.device,
    *,
    lora_blocks: int,
    lora_rank: int,
    lora_alpha: float,
    lora_dropout: float,
    frozen_embedding: bool,
    continue_lora: bool = False,
) -> tuple[nn.Module, dict[str, Any], int]:
    if frozen_embedding and continue_lora:
        raise ValueError("Use only one of --frozen-embedding and --continue-lora.")
    paths_cfg = config.get("paths", {})
    model_cfg = config.get("model", {})
    family = str(model_cfg.get("backbone_family", "dinov3"))
    pretrained = resolve_path(paths_cfg.get("checkpoint_path"))
    if family == "timm_mae":
        # MAE-style encoder: no dinov3 seg-ckpt overlay (keys would silently collide).
        if frozen_embedding or continue_lora:
            raise ValueError("--frozen-embedding/--continue-lora require a dinov3 seg ckpt; not supported for timm_mae.")
        if pretrained is None:
            raise FileNotFoundError("Missing checkpoint_path for timm_mae backbone.")
        backbone = load_timm_mae_backbone(model_cfg, pretrained)
        info: dict[str, Any] = {
            "official_weights": str(pretrained),
            "seg_ckpt": "skipped (timm_mae family)",
            "loaded_backbone_tensors": 0,
            "loaded_lora_tensors": 0,
            "frozen_embedding": False,
            "continue_lora": False,
        }
        for param in backbone.parameters():
            param.requires_grad = False
        lora_n = inject_lora(backbone, lora_blocks, lora_rank, lora_alpha, lora_dropout, train_norms=True)
        info["lora_modules"] = lora_n
        return backbone.to(device), info, lora_n
    repo_dir = resolve_path(paths_cfg.get("dinov3_repo"))
    if repo_dir is None or pretrained is None:
        raise FileNotFoundError("Missing DINOv3 repo or official weights in config.")
    backbone = torch.hub.load(str(repo_dir), str(model_cfg.get("hub_model", "dinov3_vitb16")), source="local", weights=str(pretrained))
    info: dict[str, Any] = {
        "official_weights": str(pretrained),
        "seg_ckpt": None,
        "loaded_backbone_tensors": 0,
        "loaded_lora_tensors": 0,
        "frozen_embedding": bool(frozen_embedding),
        "continue_lora": bool(continue_lora),
    }
    lora_n = 0
    load_existing_lora = frozen_embedding or continue_lora
    if load_existing_lora:
        lora_n = inject_lora(
            backbone,
            lora_blocks,
            lora_rank,
            lora_alpha,
            lora_dropout,
            train_norms=bool(continue_lora),
        )
    seg_path = resolve_path(init_seg_ckpt)
    if seg_path is not None:
        ckpt = torch.load(seg_path, map_location="cpu", weights_only=False)
        raw = ckpt.get("model_state_dict", ckpt)
        overlay = overlay_backbone_state(raw)
        result = backbone.load_state_dict(overlay, strict=False)
        info["seg_ckpt"] = str(seg_path)
        info["loaded_backbone_tensors"] = int(len(overlay))
        info["loaded_lora_tensors"] = int(sum(1 for key in overlay if "lora_" in key))
        info["missing_keys"] = [key for key in result.missing_keys if "bias_mask" not in key]
        info["unexpected_keys"] = list(result.unexpected_keys)
        if load_existing_lora and info["loaded_lora_tensors"] == 0:
            raise RuntimeError(f"expected LoRA tensors in {seg_path}")
    if not load_existing_lora:
        for param in backbone.parameters():
            param.requires_grad = False
        lora_n = inject_lora(backbone, lora_blocks, lora_rank, lora_alpha, lora_dropout, train_norms=True)
    elif frozen_embedding:
        for param in backbone.parameters():
            param.requires_grad = False
    else:
        last_ids = {str(i) for i in range(len(backbone.blocks) - lora_blocks, len(backbone.blocks))}
        for name, param in backbone.named_parameters():
            parts = name.split(".")
            is_lora = "lora_" in name
            is_ln = (
                name.startswith("blocks.")
                and len(parts) >= 3
                and parts[1] in last_ids
                and parts[2] in {"norm1", "norm2"}
            )
            param.requires_grad = bool(is_lora or is_ln)
    info["lora_modules"] = lora_n
    return backbone.to(device), info, lora_n


def metrics_from_probs(labels: np.ndarray, probs: np.ndarray) -> dict[str, float]:
    pred = probs.argmax(axis=1)
    present = sorted(np.unique(labels).tolist())
    out = {
        "accuracy": float(accuracy_score(labels, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(labels, pred)),
        "macro_f1": float(f1_score(labels, pred, average="macro", zero_division=0)),
        "mae": float(np.mean(np.abs(pred.astype(np.float32) - labels.astype(np.float32)))),
        "off_by_one": float(np.mean(np.abs(pred - labels) == 1)),
        "off_by_two_plus": float(np.mean(np.abs(pred - labels) >= 2)),
        "quadratic_kappa": float(cohen_kappa_score(labels, pred, weights="quadratic")) if len(present) > 1 else float("nan"),
    }
    if len(present) < 2:
        out["auc_macro_ovr"] = float("nan")
    else:
        y_map = np.array([present.index(int(v)) for v in labels])
        sub = probs[:, present]
        sub = sub / np.maximum(sub.sum(axis=1, keepdims=True), 1e-8)
        if len(present) == 2:
            out["auc_macro_ovr"] = float(roc_auc_score(y_map, sub[:, 1]))
        else:
            out["auc_macro_ovr"] = float(roc_auc_score(y_map, sub, multi_class="ovr", average="macro"))
    early = (labels >= 2).astype(int)
    out["early_vs_advanced_auc"] = (
        float(roc_auc_score(early, probs[:, 2] + probs[:, 3])) if len(np.unique(early)) > 1 else float("nan")
    )
    for left, right, name in ((0, 1, "t1_t2"), (1, 2, "t2_t3"), (2, 3, "t3_t4")):
        mask = np.isin(labels, [left, right])
        if mask.sum() >= 8 and len(np.unique(labels[mask])) == 2:
            score = probs[mask, right] / np.maximum(probs[mask, left] + probs[mask, right], 1e-8)
            out[f"{name}_auc"] = float(roc_auc_score((labels[mask] == right).astype(int), score))
        else:
            out[f"{name}_auc"] = float("nan")
    return out


def patient_metrics(frame_df: pd.DataFrame) -> dict[str, float]:
    prob_cols = [f"prob_{name}" for name in CLASS_NAMES]
    grouped = frame_df.groupby("patient_id", sort=False)
    labels = grouped["class_label"].first().to_numpy(dtype=int)
    probs = grouped[prob_cols].mean().to_numpy(dtype=np.float64)
    out = metrics_from_probs(labels, probs)
    out["n_patients"] = float(len(labels))
    return out


def evaluate(model: nn.Module, loader: DataLoader, device: torch.device) -> tuple[pd.DataFrame, dict[str, float], dict[str, float]]:
    model.eval()
    rows = []
    with torch.no_grad():
        for batch in loader:
            images = batch["image"].to(device, dtype=torch.float32)
            labels = batch["label"].to(device)
            logits = model(images)
            probs = torch.softmax(logits, dim=1).cpu().numpy()
            for row_idx in range(len(labels)):
                row = {
                    "patient_id": batch["patient_id"][row_idx],
                    "sample_id": str(batch["sample_id"][row_idx]),
                    "class_label": int(labels[row_idx].cpu().item()),
                }
                for cls_idx, name in enumerate(CLASS_NAMES):
                    row[f"prob_{name}"] = float(probs[row_idx, cls_idx])
                rows.append(row)
    frame_df = pd.DataFrame(rows)
    frame_metrics = metrics_from_probs(
        frame_df["class_label"].to_numpy(dtype=int),
        frame_df[[f"prob_{name}" for name in CLASS_NAMES]].to_numpy(dtype=np.float64),
    )
    frame_metrics["n_frames"] = float(len(frame_df))
    return frame_df, frame_metrics, patient_metrics(frame_df)


def prefix_metrics(prefix: str, metrics: dict[str, float]) -> dict[str, float]:
    return {f"{prefix}{key}": value for key, value in metrics.items()}


def main() -> None:
    args = parse_args()
    set_seed(args.seed)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or (DEFAULT_OUTPUT / f"phase0_{stamp}")
    output_dir.mkdir(parents=True, exist_ok=True)
    assert_no_external_rows(args.train_csv, "train", args.allow_external_train_val)
    assert_no_external_rows(args.val_csv, "val", args.allow_external_train_val)
    config = load_yaml(args.config)
    device = torch.device(args.device)
    blur_sigma = args.input_blur_sigma
    if blur_sigma is None:
        blur_sigma = float(config.get("model", {}).get("input_blur_sigma", 0.0) or 0.0)
    if blur_sigma > 0:
        print(json.dumps({"input_blur_sigma": blur_sigma, "note": "deblur-MAE transfer protocol"}), flush=True)

    train_ds = RoiDataset(
        args.train_csv, args.image_size, True, args.max_train_rows, args.seed, full_coverage=args.full_coverage_roi,
        blur_sigma=blur_sigma,
    )
    val_ds = RoiDataset(
        args.val_csv, args.image_size, False, args.max_val_rows, args.seed + 1, full_coverage=args.full_coverage_roi,
        blur_sigma=blur_sigma,
    )
    test_ds = RoiDataset(
        args.test_csv, args.image_size, False, args.max_test_rows, args.seed + 2, full_coverage=args.full_coverage_roi,
        blur_sigma=blur_sigma,
    )
    loaders = {
        "train": DataLoader(
            train_ds,
            batch_size=args.batch_size,
            shuffle=True,
            num_workers=args.num_workers,
            pin_memory=torch.cuda.is_available(),
        ),
        "val": DataLoader(
            val_ds,
            batch_size=args.batch_size,
            shuffle=False,
            num_workers=args.num_workers,
            pin_memory=torch.cuda.is_available(),
        ),
        "test": DataLoader(
            test_ds,
            batch_size=args.batch_size,
            shuffle=False,
            num_workers=args.num_workers,
            pin_memory=torch.cuda.is_available(),
        ),
    }

    backbone, init_info, lora_modules = load_backbone(
        config,
        args.init_seg_ckpt,
        device,
        lora_blocks=args.lora_blocks,
        lora_rank=args.lora_rank,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        frozen_embedding=args.frozen_embedding,
        continue_lora=args.continue_lora,
    )
    embed_dim = int(getattr(backbone, "embed_dim", 768))
    model = RoiLoraMlp(backbone, embed_dim, args.mlp_hidden, args.mlp_dropout).to(device)
    lora_lr = float(args.lora_lr) if args.lora_lr is not None else float(args.lr)
    head_params = [param for name, param in model.named_parameters() if param.requires_grad and not name.startswith("backbone.")]
    lora_params = [param for name, param in model.named_parameters() if param.requires_grad and name.startswith("backbone.")]
    param_groups = []
    if lora_params:
        param_groups.append({"params": lora_params, "lr": lora_lr})
    if head_params:
        param_groups.append({"params": head_params, "lr": float(args.lr)})
    if not param_groups:
        raise RuntimeError("No trainable parameters")
    trainable = lora_params + head_params
    counts = np.bincount(train_ds.df["class_label"].astype(int).to_numpy(), minlength=4).astype(np.float32)
    weights = counts.sum() / np.maximum(counts, 1.0)
    weights = weights / max(float(weights.mean()), 1e-6)
    class_weights = torch.tensor(weights, dtype=torch.float32, device=device)
    optimizer = torch.optim.AdamW(param_groups, lr=args.lr, weight_decay=args.weight_decay)
    scaler = torch.cuda.amp.GradScaler() if args.amp and device.type == "cuda" else None

    best_state = None
    best_val = -np.inf
    bad_epochs = 0
    history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        losses = []
        for batch in loaders["train"]:
            optimizer.zero_grad(set_to_none=True)
            images = batch["image"].to(device, dtype=torch.float32, non_blocking=True)
            labels = batch["label"].to(device, non_blocking=True)
            with torch.cuda.amp.autocast(enabled=scaler is not None):
                logits = model(images)
                loss = F.cross_entropy(logits, labels, weight=class_weights)
            if scaler is not None:
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            else:
                loss.backward()
                optimizer.step()
            losses.append(float(loss.detach().cpu()))
        _, val_frame, val_patient = evaluate(model, loaders["val"], device)
        row = {
            "epoch": epoch,
            "train_loss": float(np.mean(losses)),
            **prefix_metrics("val_frame_", val_frame),
            **prefix_metrics("val_patient_", val_patient),
        }
        history.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        score = val_patient.get("auc_macro_ovr", float("nan"))
        if np.isfinite(score) and score > best_val:
            best_val = float(score)
            bad_epochs = 0
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        else:
            bad_epochs += 1
            if bad_epochs >= args.patience:
                print(json.dumps({"early_stop": True, "epoch": epoch, "best_val_patient_auc": best_val}), flush=True)
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    pd.DataFrame(history).to_csv(output_dir / "training_history.csv", index=False)
    result_rows = []
    eval_splits = [("val", loaders["val"]), ("test_prospective", loaders["test"])]
    if not args.skip_external and args.external_csv.exists():
        ext_ds = RoiDataset(
            args.external_csv,
            args.image_size,
            False,
            args.max_test_rows,
            args.seed + 3,
            full_coverage=args.full_coverage_roi,
            blur_sigma=blur_sigma,
        )
        eval_splits.append(
            (
                "test_external",
                DataLoader(
                    ext_ds,
                    batch_size=args.batch_size,
                    shuffle=False,
                    num_workers=args.num_workers,
                    pin_memory=torch.cuda.is_available(),
                ),
            )
        )
    for split_name, loader in eval_splits:
        pred, frame_metrics, pat_metrics = evaluate(model, loader, device)
        pred.to_csv(output_dir / f"{split_name}_frame_predictions.csv", index=False)
        result_rows.append({"split": split_name, "level": "frame", **frame_metrics})
        result_rows.append({"split": split_name, "level": "patient", **pat_metrics})
    pd.DataFrame(result_rows).to_csv(output_dir / "results.csv", index=False)
    ckpt_path = output_dir / "best_roi_lora_mlp.pt"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "class_names": CLASS_NAMES,
            "config": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
            "init_info": init_info,
            "lora_modules": lora_modules,
            "embed_dim": embed_dim,
        },
        ckpt_path,
    )
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "task": (
            "dinov3_frozen_embedding_mlp"
            if args.frozen_embedding
            else ("dinov3_roi_continue_lora_mlp" if args.continue_lora else "dinov3_roi_lora_mlp")
        ),
        "roi_source": "full_coverage_roi" if args.full_coverage_roi else "phase0_gt_crop_roi",
        "note": (
            "Frozen m025 ROI LoRA embedding + MLP. Full-coverage ROI letterboxed to 512. No BETA/TabPFN."
            if args.frozen_embedding
            else (
                "Continue m025 ROI LoRA on T-stage. Full-coverage ROI (crop_roi / mask box / CSV crop). No BETA/TabPFN."
                if args.continue_lora
                else "GT/full-coverage ROI letterboxed to 512. Not predicted-mask 1.25x. No BETA/TabPFN."
            )
        ),
        "frozen_embedding": bool(args.frozen_embedding),
        "continue_lora": bool(args.continue_lora),
        "full_coverage_roi": bool(args.full_coverage_roi),
        "input_blur_sigma": blur_sigma,
        "train_csv": str(args.train_csv),
        "val_csv": str(args.val_csv),
        "test_csv": str(args.test_csv),
        "image_size": args.image_size,
        "lora_rank": args.lora_rank,
        "lora_alpha": args.lora_alpha,
        "lora_blocks": args.lora_blocks,
        "lora_modules": lora_modules,
        "mlp_hidden": args.mlp_hidden,
        "trainable_tensors": int(sum(param.numel() for param in trainable)),
        "train_rows": int(len(train_ds)),
        "val_rows": int(len(val_ds)),
        "test_rows": int(len(test_ds)),
        "best_val_patient_auc": best_val,
        "init_info": init_info,
        "results": result_rows,
        "checkpoint": str(ckpt_path),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.frozen_embedding:
        readme = (
            "# DINOv3 frozen ROI embedding + MLP\n\n"
            "Phase-0 patient split. Full-coverage ROI letterboxed to 512. "
            "Backbone and LoRA are loaded from the init seg ckpt and frozen. "
            "Only the two-layer MLP on CLS+GAP (1536-d) is trained. BETA / TabPFN are off.\n"
        )
    elif args.continue_lora:
        readme = (
            "# DINOv3 continue ROI LoRA + MLP (T-stage)\n\n"
            "Phase-0 patient split. Full-coverage ROI: official crop_roi, else mask box "
            "on crop_ui (0.25 / 16), else CSV image crop. Loads m025 segmentation LoRA, "
            "keeps LoRA and last-block LayerNorms trainable, trains a new T-stage MLP. "
            "BETA / TabPFN are off. Not public Assist.\n"
        )
    else:
        readme = (
            "# DINOv3 ROI LoRA + MLP\n\n"
            "Phase-0 patient split. ROI letterboxed to 512, no stretch. Backbone starts "
            "from the 20260511 full-frame DINOv3 segmentation checkpoint. Last "
            f"{args.lora_blocks} blocks get LoRA on attn qkv/proj; LayerNorms in "
            "those blocks and a two-layer MLP head are trained. BETA / TabPFN are off.\n"
        )
    (output_dir / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
