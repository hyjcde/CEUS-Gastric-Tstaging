#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import random
import shlex
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import yaml
from PIL import Image
from torch.utils.data import DataLoader, Dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_segmentation_example_panels import (  # noqa: E402
    build_contact_sheet,
    pick_examples,
)
from score_binary_segmentation_folder import draw_overlay  # noqa: E402


@dataclass(frozen=True)
class SampleRecord:
    case_id: str
    image_path: Path
    mask_path: Path
    original_image: Path
    original_label: Path
    source_split: str
    patient_id: str
    crop_box: tuple[int, int, int, int] | None = None
    lumen_box: tuple[int, int, int, int] | None = None
    full_width: int | None = None
    full_height: int | None = None
    view_type: str = "full_image"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train and evaluate a self-contained PyTorch UNet2D baseline.")
    parser.add_argument("--config", required=True, type=Path, help="UNet2D YAML config.")
    parser.add_argument("--exp-name", default=None, help="Optional explicit experiment directory name.")
    parser.add_argument("--override-epochs", type=int, default=None, help="Optional training epoch override.")
    parser.add_argument("--max-train-samples", type=int, default=None, help="Optional cap for smoke tests.")
    parser.add_argument("--max-eval-samples", type=int, default=None, help="Optional cap for smoke tests.")
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping YAML: {path}")
    return data


def resolve_project_path(value: str | None, *, required: bool = True) -> Path | None:
    if value in (None, ""):
        if required:
            raise ValueError("Missing required path in config")
        return None
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def compute_experiment_name(config: dict, explicit_name: str | None) -> str:
    if explicit_name:
        return explicit_name
    experiment_cfg = config.get("experiment", {})
    date_tag = datetime.now().strftime("%Y%m%d")
    return "_".join(
        [
            str(experiment_cfg.get("task_name", "segmentation")),
            str(experiment_cfg.get("model_alias", "unet2d")),
            str(experiment_cfg.get("data_version", "dataset_v00000000")),
            date_tag,
            str(experiment_cfg.get("run_id", "r001")),
        ]
    )


def case_patient_id(case_id: str) -> str:
    base = case_id.removeprefix("lumen_")
    if "_" not in base:
        return base
    return base.rsplit("_", 1)[0]


def parse_box(value: object) -> tuple[int, int, int, int] | None:
    if value in (None, "", []):
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        value = json.loads(text)
    if isinstance(value, (list, tuple)) and len(value) == 4:
        return tuple(int(round(float(v))) for v in value)
    return None


def load_records(dataset_manifest_path: Path) -> tuple[list[SampleRecord], list[SampleRecord], dict[str, list[SampleRecord]]]:
    payload = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    training_records: list[SampleRecord] = []
    holdout_records: list[SampleRecord] = []
    eval_sources: dict[str, list[SampleRecord]] = {}
    for row in payload.get("cases", []):
        record = SampleRecord(
            case_id=str(row["case_id"]),
            image_path=Path(row["prepared_image"]).resolve(),
            mask_path=Path(row["prepared_label"]).resolve(),
            original_image=Path(row["original_image"]).resolve(),
            original_label=Path(row.get("original_label", row["prepared_label"])).resolve(),
            source_split=str(row["source_split"]),
            patient_id=case_patient_id(str(row["case_id"])),
            crop_box=parse_box(row.get("crop_box")),
            lumen_box=parse_box(row.get("lumen_box")),
            full_width=int(row["original_width"]) if row.get("original_width") not in (None, "") else None,
            full_height=int(row["original_height"]) if row.get("original_height") not in (None, "") else None,
            view_type=str(row.get("view_type", "full_image")),
        )
        if row["target_split"] == "training":
            training_records.append(record)
        elif row["target_split"] == "test":
            holdout_records.append(record)
        else:
            eval_sources.setdefault(str(row["target_split"]), []).append(record)

    if eval_sources:
        return training_records, holdout_records, eval_sources

    dataset_root = dataset_manifest_path.parent.resolve()
    for eval_name, summary in payload.get("evaluation_sources", {}).items():
        eval_root = Path(summary["output_root"]).resolve()
        img_dir = eval_root / "img"
        label_dir = eval_root / "label"
        original_root = dataset_root / "eval_sources" / eval_name / "img"
        records: list[SampleRecord] = []
        for img_path in sorted(img_dir.glob("*.png")):
            mask_path = label_dir / f"{img_path.stem}.png"
            if not mask_path.exists():
                continue
            original_image = original_root / f"{img_path.stem}.png"
            records.append(
                SampleRecord(
                    case_id=img_path.stem,
                    image_path=img_path.resolve(),
                    mask_path=mask_path.resolve(),
                    original_image=original_image.resolve(),
                    original_label=mask_path.resolve(),
                    source_split=eval_name,
                    patient_id=case_patient_id(img_path.stem),
                )
            )
        eval_sources[eval_name] = records
    return training_records, holdout_records, eval_sources


def split_train_val(records: list[SampleRecord], val_fraction: float, seed: int) -> tuple[list[SampleRecord], list[SampleRecord], dict[str, int]]:
    grouped: dict[str, list[SampleRecord]] = {}
    for record in records:
        grouped.setdefault(record.patient_id, []).append(record)
    patient_ids = sorted(grouped)
    rng = random.Random(seed)
    rng.shuffle(patient_ids)
    val_patient_count = max(1, int(round(len(patient_ids) * val_fraction)))
    if val_patient_count >= len(patient_ids):
        val_patient_count = max(1, len(patient_ids) - 1)
    val_patients = set(patient_ids[:val_patient_count])
    train_records = [record for record in records if record.patient_id not in val_patients]
    val_records = [record for record in records if record.patient_id in val_patients]
    summary = {
        "train_patients": len({record.patient_id for record in train_records}),
        "val_patients": len({record.patient_id for record in val_records}),
        "train_images": len(train_records),
        "val_images": len(val_records),
    }
    return train_records, val_records, summary


def load_grayscale(path: Path) -> Image.Image:
    return Image.open(path).convert("L")


def resize_image(image: Image.Image, size: int, *, is_mask: bool) -> Image.Image:
    resample = Image.NEAREST if is_mask else Image.BILINEAR
    return image.resize((size, size), resample=resample)


class GastricSegDataset(Dataset):
    def __init__(
        self,
        records: list[SampleRecord],
        image_size: int,
        *,
        augment: bool = False,
        brightness_jitter: float = 0.0,
        contrast_jitter: float = 0.0,
        hflip_prob: float = 0.0,
    ) -> None:
        self.records = records
        self.image_size = image_size
        self.augment = augment
        self.brightness_jitter = float(brightness_jitter)
        self.contrast_jitter = float(contrast_jitter)
        self.hflip_prob = float(hflip_prob)

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, object]:
        record = self.records[index]
        image = load_grayscale(record.image_path)
        mask = load_grayscale(record.mask_path)
        original_size = image.size

        image = resize_image(image, self.image_size, is_mask=False)
        mask = resize_image(mask, self.image_size, is_mask=True)
        image_arr = np.array(image, dtype=np.float32) / 255.0
        mask_arr = (np.array(mask, dtype=np.uint8) > 0).astype(np.float32)

        if self.augment:
            if random.random() < self.hflip_prob:
                image_arr = np.ascontiguousarray(np.fliplr(image_arr))
                mask_arr = np.ascontiguousarray(np.fliplr(mask_arr))
            if self.brightness_jitter > 0:
                scale = 1.0 + random.uniform(-self.brightness_jitter, self.brightness_jitter)
                image_arr = np.clip(image_arr * scale, 0.0, 1.0)
            if self.contrast_jitter > 0:
                mean = float(image_arr.mean())
                scale = 1.0 + random.uniform(-self.contrast_jitter, self.contrast_jitter)
                image_arr = np.clip((image_arr - mean) * scale + mean, 0.0, 1.0)

        return {
            "image": torch.from_numpy(image_arr[None, ...]),
            "mask": torch.from_numpy(mask_arr[None, ...]),
            "case_id": record.case_id,
            "mask_path": str(record.mask_path),
            "original_image": str(record.original_image),
            "original_label": str(record.original_label),
            "original_width": int(original_size[0]),
            "original_height": int(original_size[1]),
            "full_width": int(record.full_width or original_size[0]),
            "full_height": int(record.full_height or original_size[1]),
            "crop_box": list(record.crop_box) if record.crop_box is not None else None,
            "lumen_box": list(record.lumen_box) if record.lumen_box is not None else None,
            "view_type": record.view_type,
        }


class DoubleConv(nn.Module):
    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.block(x)


class UNet2D(nn.Module):
    def __init__(self, in_channels: int = 1, out_channels: int = 1, base_channels: int = 32) -> None:
        super().__init__()
        features = [base_channels, base_channels * 2, base_channels * 4, base_channels * 8]
        self.down1 = DoubleConv(in_channels, features[0])
        self.down2 = DoubleConv(features[0], features[1])
        self.down3 = DoubleConv(features[1], features[2])
        self.down4 = DoubleConv(features[2], features[3])
        self.pool = nn.MaxPool2d(2)
        self.bottleneck = DoubleConv(features[3], features[3] * 2)
        self.up4 = nn.ConvTranspose2d(features[3] * 2, features[3], kernel_size=2, stride=2)
        self.conv4 = DoubleConv(features[3] * 2, features[3])
        self.up3 = nn.ConvTranspose2d(features[3], features[2], kernel_size=2, stride=2)
        self.conv3 = DoubleConv(features[2] * 2, features[2])
        self.up2 = nn.ConvTranspose2d(features[2], features[1], kernel_size=2, stride=2)
        self.conv2 = DoubleConv(features[1] * 2, features[1])
        self.up1 = nn.ConvTranspose2d(features[1], features[0], kernel_size=2, stride=2)
        self.conv1 = DoubleConv(features[0] * 2, features[0])
        self.head = nn.Conv2d(features[0], out_channels, kernel_size=1)

    def forward_features(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        d1 = self.down1(x)
        d2 = self.down2(self.pool(d1))
        d3 = self.down3(self.pool(d2))
        d4 = self.down4(self.pool(d3))
        b = self.bottleneck(self.pool(d4))
        u4 = self.up4(b)
        u4 = self.conv4(torch.cat([u4, d4], dim=1))
        u3 = self.up3(u4)
        u3 = self.conv3(torch.cat([u3, d3], dim=1))
        u2 = self.up2(u3)
        u2 = self.conv2(torch.cat([u2, d2], dim=1))
        u1 = self.up1(u2)
        u1 = self.conv1(torch.cat([u1, d1], dim=1))
        return self.head(u1), u1

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        logits, _ = self.forward_features(x)
        return logits


class SegmentationAuxWrapper(nn.Module):
    def __init__(self, base_model: nn.Module, feature_channels: int, auxiliary_cfg: dict) -> None:
        super().__init__()
        self.base_model = base_model
        self.auxiliary_cfg = auxiliary_cfg
        hidden_dim = int(auxiliary_cfg.get("hidden_dim", max(32, feature_channels // 2)))
        self.boundary_head = nn.Conv2d(feature_channels, 1, kernel_size=1)
        self.irregularity_head = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Linear(feature_channels, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_dim, 1),
        )
        self.blur_head = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Linear(feature_channels, hidden_dim),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_dim, 1),
        )

    def _forward_base(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        if hasattr(self.base_model, "forward_features"):
            logits, features = self.base_model.forward_features(x)
            return logits, features
        if all(hasattr(self.base_model, attr) for attr in ("encoder", "decoder", "segmentation_head")):
            encoded = self.base_model.encoder(x)
            decoder_output = self.base_model.decoder(encoded)
            logits = self.base_model.segmentation_head(decoder_output)
            return logits, decoder_output
        logits = self.base_model(x)
        return logits, logits

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        logits, features = self._forward_base(x)
        return {
            "logits": logits,
            "boundary_logits": self.boundary_head(features),
            "irregularity": self.irregularity_head(features).squeeze(1),
            "blur": self.blur_head(features).squeeze(1),
        }


def infer_feature_channels(model: nn.Module) -> int:
    if hasattr(model, "head") and isinstance(model.head, nn.Conv2d):
        return int(model.head.in_channels)
    segmentation_head = getattr(model, "segmentation_head", None)
    if segmentation_head is not None:
        for module in segmentation_head.modules():
            if isinstance(module, nn.Conv2d):
                return int(module.in_channels)
    raise ValueError("Cannot infer segmentation decoder feature channels for auxiliary wrapper.")


def build_segmentation_model(model_cfg: dict) -> nn.Module:
    architecture = str(model_cfg.get("architecture", "unet2d")).strip().lower()
    in_channels = int(model_cfg.get("in_channels", 1))
    out_channels = int(model_cfg.get("out_channels", 1))

    if architecture in {"unet2d", "custom_unet2d", "unet"}:
        model: nn.Module = UNet2D(
            in_channels=in_channels,
            out_channels=out_channels,
            base_channels=int(model_cfg.get("base_channels", 32)),
        )
        auxiliary_cfg = model_cfg.get("auxiliary", {})
        if auxiliary_cfg.get("enabled", False):
            return SegmentationAuxWrapper(model, infer_feature_channels(model), auxiliary_cfg)
        return model

    if architecture in {"unetplusplus", "unet++", "unet_plus_plus"}:
        try:
            import segmentation_models_pytorch as smp
        except ImportError as exc:
            raise ImportError(
                "Unet++ requires `segmentation_models_pytorch`. "
                "Install it with `pip install segmentation-models-pytorch`."
            ) from exc

        encoder_weights = model_cfg.get("encoder_weights")
        if encoder_weights in ("", "none", "null", None):
            encoder_weights = None
        model = smp.UnetPlusPlus(
            encoder_name=str(model_cfg.get("encoder_name", "resnet34")),
            encoder_weights=encoder_weights,
            in_channels=in_channels,
            classes=out_channels,
        )
        auxiliary_cfg = model_cfg.get("auxiliary", {})
        if auxiliary_cfg.get("enabled", False):
            return SegmentationAuxWrapper(model, infer_feature_channels(model), auxiliary_cfg)
        return model

    raise ValueError(
        f"Unsupported model architecture: {architecture}. "
        "Expected one of: unet2d, unetplusplus."
    )


def dice_loss_from_logits(logits: torch.Tensor, targets: torch.Tensor, eps: float = 1e-6) -> torch.Tensor:
    probs = torch.sigmoid(logits)
    intersection = (probs * targets).sum(dim=(1, 2, 3))
    denom = probs.sum(dim=(1, 2, 3)) + targets.sum(dim=(1, 2, 3))
    dice = (2 * intersection + eps) / (denom + eps)
    return 1.0 - dice.mean()


def boundary_map_from_mask(mask: torch.Tensor, kernel_size: int = 5) -> torch.Tensor:
    padding = kernel_size // 2
    dilated = F.max_pool2d(mask, kernel_size=kernel_size, stride=1, padding=padding)
    eroded = 1.0 - F.max_pool2d(1.0 - mask, kernel_size=kernel_size, stride=1, padding=padding)
    return (dilated - eroded).clamp(0.0, 1.0)


def mask_irregularity_score(mask: torch.Tensor) -> torch.Tensor:
    boundary = boundary_map_from_mask(mask)
    perimeter = boundary.sum(dim=(1, 2, 3))
    area = mask.sum(dim=(1, 2, 3))
    return torch.log1p((perimeter * perimeter) / (area + 1e-6))


def image_gradient_map(images: torch.Tensor) -> torch.Tensor:
    sobel_x = images.new_tensor([[-1.0, 0.0, 1.0], [-2.0, 0.0, 2.0], [-1.0, 0.0, 1.0]]).view(1, 1, 3, 3)
    sobel_y = images.new_tensor([[-1.0, -2.0, -1.0], [0.0, 0.0, 0.0], [1.0, 2.0, 1.0]]).view(1, 1, 3, 3)
    grad_x = F.conv2d(images, sobel_x, padding=1)
    grad_y = F.conv2d(images, sobel_y, padding=1)
    return torch.sqrt(grad_x.square() + grad_y.square() + 1e-6)


def mask_blur_score(images: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    boundary = boundary_map_from_mask(mask)
    grad = image_gradient_map(images)
    clarity = (grad * boundary).sum(dim=(1, 2, 3)) / (boundary.sum(dim=(1, 2, 3)) + 1e-6)
    return torch.log1p(1.0 / (clarity + 1e-4))


def unpack_logits(outputs: torch.Tensor | dict[str, torch.Tensor]) -> torch.Tensor:
    if isinstance(outputs, dict):
        return outputs["logits"]
    return outputs


def compute_auxiliary_loss(
    outputs: torch.Tensor | dict[str, torch.Tensor],
    images: torch.Tensor,
    masks: torch.Tensor,
    auxiliary_cfg: dict,
) -> tuple[torch.Tensor, dict[str, float]]:
    if not isinstance(outputs, dict) or not auxiliary_cfg.get("enabled", False):
        zero = images.new_tensor(0.0)
        return zero, {
            "boundary_loss": 0.0,
            "irregularity_loss": 0.0,
            "blur_loss": 0.0,
        }

    boundary_target = boundary_map_from_mask(masks)
    boundary_loss = F.binary_cross_entropy_with_logits(outputs["boundary_logits"], boundary_target)
    irregularity_target = mask_irregularity_score(masks)
    irregularity_loss = F.smooth_l1_loss(outputs["irregularity"], irregularity_target)
    blur_target = mask_blur_score(images, masks)
    blur_loss = F.smooth_l1_loss(outputs["blur"], blur_target)
    total_loss = (
        float(auxiliary_cfg.get("boundary_weight", 0.2)) * boundary_loss
        + float(auxiliary_cfg.get("irregularity_weight", 0.1)) * irregularity_loss
        + float(auxiliary_cfg.get("blur_weight", 0.1)) * blur_loss
    )
    return total_loss, {
        "boundary_loss": float(boundary_loss.item()),
        "irregularity_loss": float(irregularity_loss.item()),
        "blur_loss": float(blur_loss.item()),
    }


def compute_binary_metrics(logits: torch.Tensor, targets: torch.Tensor, threshold: float) -> dict[str, float]:
    probs = torch.sigmoid(logits)
    preds = (probs >= threshold).float()
    intersection = (preds * targets).sum(dim=(1, 2, 3))
    pred_sum = preds.sum(dim=(1, 2, 3))
    target_sum = targets.sum(dim=(1, 2, 3))
    union = pred_sum + target_sum - intersection
    dice = (2 * intersection + 1e-6) / (pred_sum + target_sum + 1e-6)
    iou = (intersection + 1e-6) / (union + 1e-6)
    return {
        "dice": float(dice.mean().item()),
        "iou": float(iou.mean().item()),
    }


def collate_keep_meta(batch: list[dict[str, object]]) -> dict[str, object]:
    images = torch.stack([item["image"] for item in batch])
    masks = torch.stack([item["mask"] for item in batch])
    return {
        "image": images,
        "mask": masks,
        "case_id": [str(item["case_id"]) for item in batch],
        "mask_path": [str(item["mask_path"]) for item in batch],
        "original_image": [str(item["original_image"]) for item in batch],
        "original_label": [str(item["original_label"]) for item in batch],
        "original_width": [int(item["original_width"]) for item in batch],
        "original_height": [int(item["original_height"]) for item in batch],
        "full_width": [int(item["full_width"]) for item in batch],
        "full_height": [int(item["full_height"]) for item in batch],
        "crop_box": [item["crop_box"] for item in batch],
        "lumen_box": [item["lumen_box"] for item in batch],
        "view_type": [str(item["view_type"]) for item in batch],
    }


def create_loader(
    records: list[SampleRecord],
    image_size: int,
    batch_size: int,
    num_workers: int,
    *,
    shuffle: bool,
    augment: bool,
    brightness_jitter: float = 0.0,
    contrast_jitter: float = 0.0,
    hflip_prob: float = 0.0,
) -> DataLoader:
    dataset = GastricSegDataset(
        records,
        image_size,
        augment=augment,
        brightness_jitter=brightness_jitter,
        contrast_jitter=contrast_jitter,
        hflip_prob=hflip_prob,
    )
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
        collate_fn=collate_keep_meta,
    )


def autocast_context(device: torch.device, enabled: bool):
    if device.type == "cuda":
        return torch.amp.autocast(device_type="cuda", enabled=enabled)
    return torch.amp.autocast(device_type="cpu", enabled=False)


def device_from_config(value: str | None) -> torch.device:
    if value:
        return torch.device(value)
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    scaler: torch.cuda.amp.GradScaler | None,
    device: torch.device,
    threshold: float,
    bce_loss: nn.Module,
    bce_weight: float,
    dice_weight: float,
    use_amp: bool,
    auxiliary_cfg: dict,
) -> dict[str, float]:
    model.train()
    total_loss = 0.0
    total_batches = 0
    total_dice = 0.0
    total_iou = 0.0
    total_boundary_loss = 0.0
    total_irregularity_loss = 0.0
    total_blur_loss = 0.0
    for batch in loader:
        images = batch["image"].to(device=device, dtype=torch.float32, non_blocking=True)
        masks = batch["mask"].to(device=device, dtype=torch.float32, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)
        with autocast_context(device, use_amp):
            outputs = model(images)
            logits = unpack_logits(outputs)
            loss = bce_weight * bce_loss(logits, masks) + dice_weight * dice_loss_from_logits(logits, masks)
            aux_loss, aux_metrics = compute_auxiliary_loss(outputs, images, masks, auxiliary_cfg)
            loss = loss + aux_loss
        if scaler is not None:
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        else:
            loss.backward()
            optimizer.step()
        metrics = compute_binary_metrics(logits.detach(), masks, threshold)
        total_loss += float(loss.item())
        total_dice += metrics["dice"]
        total_iou += metrics["iou"]
        total_boundary_loss += aux_metrics["boundary_loss"]
        total_irregularity_loss += aux_metrics["irregularity_loss"]
        total_blur_loss += aux_metrics["blur_loss"]
        total_batches += 1
    return {
        "loss": total_loss / max(total_batches, 1),
        "dice": total_dice / max(total_batches, 1),
        "iou": total_iou / max(total_batches, 1),
        "boundary_loss": total_boundary_loss / max(total_batches, 1),
        "irregularity_loss": total_irregularity_loss / max(total_batches, 1),
        "blur_loss": total_blur_loss / max(total_batches, 1),
    }


@torch.no_grad()
def evaluate_loader(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
    threshold: float,
    bce_loss: nn.Module,
    bce_weight: float,
    dice_weight: float,
    use_amp: bool,
    auxiliary_cfg: dict,
) -> dict[str, float]:
    model.eval()
    total_loss = 0.0
    total_batches = 0
    total_dice = 0.0
    total_iou = 0.0
    total_boundary_loss = 0.0
    total_irregularity_loss = 0.0
    total_blur_loss = 0.0
    for batch in loader:
        images = batch["image"].to(device=device, dtype=torch.float32, non_blocking=True)
        masks = batch["mask"].to(device=device, dtype=torch.float32, non_blocking=True)
        with autocast_context(device, use_amp):
            outputs = model(images)
            logits = unpack_logits(outputs)
            loss = bce_weight * bce_loss(logits, masks) + dice_weight * dice_loss_from_logits(logits, masks)
            aux_loss, aux_metrics = compute_auxiliary_loss(outputs, images, masks, auxiliary_cfg)
            loss = loss + aux_loss
        metrics = compute_binary_metrics(logits, masks, threshold)
        total_loss += float(loss.item())
        total_dice += metrics["dice"]
        total_iou += metrics["iou"]
        total_boundary_loss += aux_metrics["boundary_loss"]
        total_irregularity_loss += aux_metrics["irregularity_loss"]
        total_blur_loss += aux_metrics["blur_loss"]
        total_batches += 1
    return {
        "loss": total_loss / max(total_batches, 1),
        "dice": total_dice / max(total_batches, 1),
        "iou": total_iou / max(total_batches, 1),
        "boundary_loss": total_boundary_loss / max(total_batches, 1),
        "irregularity_loss": total_irregularity_loss / max(total_batches, 1),
        "blur_loss": total_blur_loss / max(total_batches, 1),
    }


def save_checkpoint(path: Path, model: nn.Module, optimizer: torch.optim.Optimizer, epoch: int, best_val_dice: float, config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "epoch": epoch,
            "best_val_dice": best_val_dice,
            "config": config,
        },
        path,
    )


def dice_iou_from_arrays(pred: np.ndarray, gt: np.ndarray) -> dict[str, float | int]:
    pred_b = pred > 0
    gt_b = gt > 0
    tp = int(np.logical_and(pred_b, gt_b).sum())
    fp = int(np.logical_and(pred_b, ~gt_b).sum())
    fn = int(np.logical_and(~pred_b, gt_b).sum())
    tn = int(np.logical_and(~pred_b, ~gt_b).sum())
    dice = (2 * tp) / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 1.0
    iou = tp / (tp + fp + fn) if (tp + fp + fn) else 1.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "dice": dice, "iou": iou}


def boundary_from_array(mask: np.ndarray) -> np.ndarray:
    mask_t = torch.from_numpy((mask > 0).astype(np.float32))[None, None, ...]
    boundary = boundary_map_from_mask(mask_t).squeeze().numpy()
    return (boundary > 0.1).astype(np.uint8)


def boundary_f1_from_arrays(pred: np.ndarray, gt: np.ndarray) -> float:
    pred_b = boundary_from_array(pred) > 0
    gt_b = boundary_from_array(gt) > 0
    tp = float(np.logical_and(pred_b, gt_b).sum())
    fp = float(np.logical_and(pred_b, ~gt_b).sum())
    fn = float(np.logical_and(~pred_b, gt_b).sum())
    precision = tp / (tp + fp + 1e-6)
    recall = tp / (tp + fn + 1e-6)
    return float((2 * precision * recall) / (precision + recall + 1e-6))


def irregularity_score_from_array(mask: np.ndarray) -> float:
    mask_t = torch.from_numpy((mask > 0).astype(np.float32))[None, None, ...]
    return float(mask_irregularity_score(mask_t).item())


def inside_box_ratio(mask: np.ndarray, box: tuple[int, int, int, int] | None) -> float:
    if box is None:
        return 0.0
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return 0.0
    x1, y1, x2, y2 = box
    inside = (xs >= x1) & (xs <= x2) & (ys >= y1) & (ys <= y2)
    return float(inside.sum()) / float(len(xs))


def restore_mask_to_full_size(
    crop_mask: np.ndarray,
    crop_box: list[int] | tuple[int, int, int, int] | None,
    full_width: int,
    full_height: int,
) -> np.ndarray:
    if crop_box is None:
        if crop_mask.shape[1] == full_width and crop_mask.shape[0] == full_height:
            return crop_mask
        restored = np.array(Image.fromarray(crop_mask).resize((full_width, full_height), Image.NEAREST))
        return np.where(restored > 0, 255, 0).astype(np.uint8)
    x1, y1, x2, y2 = [int(v) for v in crop_box]
    crop_width = max(1, x2 - x1 + 1)
    crop_height = max(1, y2 - y1 + 1)
    if crop_mask.shape[1] != crop_width or crop_mask.shape[0] != crop_height:
        crop_mask = np.array(Image.fromarray(crop_mask).resize((crop_width, crop_height), Image.NEAREST))
        crop_mask = np.where(crop_mask > 0, 255, 0).astype(np.uint8)
    full_mask = np.zeros((full_height, full_width), dtype=np.uint8)
    full_mask[y1 : y2 + 1, x1 : x2 + 1] = crop_mask
    return full_mask


def configure_matplotlib() -> None:
    plt.style.use("dark_background")
    plt.rcParams["figure.facecolor"] = "black"
    plt.rcParams["axes.facecolor"] = "black"
    plt.rcParams["savefig.facecolor"] = "black"
    plt.rcParams["font.family"] = ["Times New Roman", "serif"]
    plt.rcParams["text.color"] = "white"
    plt.rcParams["axes.labelcolor"] = "white"
    plt.rcParams["axes.edgecolor"] = "white"
    plt.rcParams["xtick.color"] = "white"
    plt.rcParams["ytick.color"] = "white"


def plot_training_curves(history: list[dict[str, float]], output_path: Path) -> None:
    if not history:
        return
    configure_matplotlib()
    epochs = [int(row["epoch"]) for row in history]
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    ax = axes[0, 0]
    ax.plot(epochs, [row["train_loss"] for row in history], label="Train Loss", linewidth=2)
    ax.plot(epochs, [row["val_loss"] for row in history], label="Val Loss", linewidth=2)
    ax.set_title("Loss")
    ax.legend()

    ax = axes[0, 1]
    ax.plot(epochs, [row["train_dice"] for row in history], label="Train Dice", linewidth=2)
    ax.plot(epochs, [row["val_dice"] for row in history], label="Val Dice", linewidth=2)
    ax.set_title("Dice")
    ax.legend()

    ax = axes[1, 0]
    ax.plot(epochs, [row["train_iou"] for row in history], label="Train IoU", linewidth=2)
    ax.plot(epochs, [row["val_iou"] for row in history], label="Val IoU", linewidth=2)
    ax.set_title("IoU")
    ax.legend()

    ax = axes[1, 1]
    ax.plot(epochs, [row["lr"] for row in history], label="Learning Rate", linewidth=2)
    ax.set_title("Learning Rate")
    ax.legend()

    for ax in axes.flat:
        ax.grid(alpha=0.2)
        ax.set_xlabel("Epoch")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_evaluation_summary(summary_rows: list[dict[str, float | int | str]], output_path: Path) -> None:
    if not summary_rows:
        return
    configure_matplotlib()
    names = [str(row["name"]) for row in summary_rows]
    dices = [float(row["mean_dice"]) for row in summary_rows]
    ious = [float(row["mean_iou"]) for row in summary_rows]
    counts = [int(row["case_count"]) for row in summary_rows]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    x = np.arange(len(names))
    axes[0].bar(x, dices, color="#3ba272")
    axes[0].set_xticks(x, names, rotation=10)
    axes[0].set_ylim(0.0, 1.0)
    axes[0].set_title("Mean Dice")
    axes[0].grid(axis="y", alpha=0.2)

    count_norm = np.array(counts, dtype=np.float32) / max(max(counts), 1)
    axes[1].bar(x, ious, color="#5470c6")
    axes[1].plot(x, count_norm, color="#fac858", marker="o", linewidth=2, label="Normalized N")
    axes[1].set_xticks(x, names, rotation=10)
    axes[1].set_ylim(0.0, 1.0)
    axes[1].set_title("Mean IoU")
    axes[1].legend()
    axes[1].grid(axis="y", alpha=0.2)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def summarize_failed_cases(rows: list[dict[str, object]]) -> tuple[int, float]:
    zero_count = sum(1 for row in rows if float(row["dice"]) == 0.0)
    zero_ratio = zero_count / max(len(rows), 1)
    return zero_count, zero_ratio


@torch.no_grad()
def run_split_evaluation(
    model: nn.Module,
    records: list[SampleRecord],
    image_size: int,
    batch_size: int,
    num_workers: int,
    device: torch.device,
    threshold: float,
    save_probability: bool,
    experiment_dir: Path,
    split_name: str,
    examples_per_bucket: int,
) -> dict[str, object]:
    loader = create_loader(records, image_size, batch_size, num_workers, shuffle=False, augment=False)
    inference_root = ensure_dir(experiment_dir / "inference" / split_name)
    pred_dir = ensure_dir(inference_root / "predictions_png")
    if save_probability:
        prob_dir = ensure_dir(inference_root / "probabilities_npy")
    else:
        prob_dir = None
    score_root = ensure_dir(experiment_dir / "evaluation" / split_name / "sms_binary")
    source_dir = ensure_dir(score_root / "source_images_jpg")
    overlay_dir = ensure_dir(score_root / "overlays")

    model.eval()
    rows: list[dict[str, object]] = []
    for batch in loader:
        images = batch["image"].to(device=device, dtype=torch.float32, non_blocking=True)
        outputs = model(images)
        logits = unpack_logits(outputs)
        probs = torch.sigmoid(logits).cpu()
        preds = (probs >= threshold).float()
        for idx, case_id in enumerate(batch["case_id"]):
            width = int(batch["original_width"][idx])
            height = int(batch["original_height"][idx])
            full_width = int(batch["full_width"][idx])
            full_height = int(batch["full_height"][idx])
            pred_resized = F.interpolate(preds[idx : idx + 1], size=(height, width), mode="nearest")
            prob_resized = F.interpolate(probs[idx : idx + 1], size=(height, width), mode="bilinear", align_corners=False)
            crop_pred_mask = (pred_resized.squeeze().numpy() > 0).astype(np.uint8) * 255
            crop_box = batch["crop_box"][idx]
            pred_mask = restore_mask_to_full_size(crop_pred_mask, crop_box, full_width, full_height)
            gt_mask = (np.array(load_grayscale(Path(batch["original_label"][idx])), dtype=np.uint8) > 0).astype(np.uint8) * 255
            metrics = dice_iou_from_arrays(pred_mask, gt_mask)
            boundary_f1 = boundary_f1_from_arrays(pred_mask, gt_mask)
            pred_irregularity = irregularity_score_from_array(pred_mask)
            gt_irregularity = irregularity_score_from_array(gt_mask)
            shape_gap = abs(pred_irregularity - gt_irregularity)
            lumen_box = parse_box(batch["lumen_box"][idx])
            lumen_inside_ratio = inside_box_ratio(pred_mask, lumen_box)

            pred_path = pred_dir / f"{case_id}.png"
            Image.fromarray(pred_mask, mode="L").save(pred_path)
            if prob_dir is not None:
                np.save(prob_dir / f"{case_id}.npy", prob_resized.squeeze().numpy().astype(np.float32))

            source_image_path = Path(batch["original_image"][idx])
            source_jpg_path = source_dir / f"{case_id}.jpg"
            with Image.open(source_image_path) as source_image:
                source_image.convert("RGB").save(source_jpg_path, quality=95)
            draw_overlay(source_jpg_path, pred_mask, gt_mask, overlay_dir / f"{case_id}.jpg")

            rows.append(
                {
                    "case_id": case_id,
                    "source_image": source_jpg_path.name,
                    "prediction_mask": pred_path.name,
                    "gt_mask": Path(batch["mask_path"][idx]).name,
                    "dice": float(metrics["dice"]),
                    "iou": float(metrics["iou"]),
                    "tp": int(metrics["tp"]),
                    "fp": int(metrics["fp"]),
                    "fn": int(metrics["fn"]),
                    "tn": int(metrics["tn"]),
                    "pred_foreground": int((pred_mask > 0).sum()),
                    "gt_foreground": int((gt_mask > 0).sum()),
                    "boundary_f1": boundary_f1,
                    "pred_irregularity": pred_irregularity,
                    "gt_irregularity": gt_irregularity,
                    "shape_gap": shape_gap,
                    "inside_lumen_ratio": lumen_inside_ratio,
                    "view_type": batch["view_type"][idx],
                }
            )

    rows.sort(key=lambda row: float(row["dice"]))
    metrics_csv = score_root / "metrics.csv"
    with metrics_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case_id",
                "source_image",
                "prediction_mask",
                "gt_mask",
                "dice",
                "iou",
                "tp",
                "fp",
                "fn",
                "tn",
                "pred_foreground",
                "gt_foreground",
                "boundary_f1",
                "pred_irregularity",
                "gt_irregularity",
                "shape_gap",
                "inside_lumen_ratio",
                "view_type",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    mean_dice = float(np.mean([float(row["dice"]) for row in rows])) if rows else 0.0
    mean_iou = float(np.mean([float(row["iou"]) for row in rows])) if rows else 0.0
    mean_boundary_f1 = float(np.mean([float(row["boundary_f1"]) for row in rows])) if rows else 0.0
    mean_shape_gap = float(np.mean([float(row["shape_gap"]) for row in rows])) if rows else 0.0
    mean_inside_lumen_ratio = float(np.mean([float(row["inside_lumen_ratio"]) for row in rows])) if rows else 0.0
    zero_count, zero_ratio = summarize_failed_cases(rows)
    summary = {
        "case_count": len(rows),
        "mean_dice": mean_dice,
        "mean_iou": mean_iou,
        "mean_boundary_f1": mean_boundary_f1,
        "mean_shape_gap": mean_shape_gap,
        "mean_inside_lumen_ratio": mean_inside_lumen_ratio,
        "zero_dice_count": zero_count,
        "zero_dice_ratio": zero_ratio,
        "worst_k": 20,
        "worst_cases": [
            {
                "case_id": row["case_id"],
                "source_image": row["source_image"],
                "dice": row["dice"],
                "iou": row["iou"],
            }
            for row in rows[:20]
        ],
        "best_cases": [
            {
                "case_id": row["case_id"],
                "source_image": row["source_image"],
                "dice": row["dice"],
                "iou": row["iou"],
            }
            for row in rows[-20:]
        ],
    }
    summary_path = score_root / "summary.json"
    save_json(summary_path, summary)

    selected = pick_examples(
        [
            {
                "case_id": str(row["case_id"]),
                "source_image": str(row["source_image"]),
                "dice": str(row["dice"]),
                "iou": str(row["iou"]),
            }
            for row in rows
        ],
        examples_per_bucket,
    )
    overlay_paths: list[Path] = []
    example_dir = ensure_dir(experiment_dir / "evaluation" / "example_visualizations" / split_name)
    for idx, row in enumerate(selected, start=1):
        overlay_path = example_dir / f"{idx:02d}_{row.bucket.lower()}_{row.case_id}.jpg"
        pred = np.array(Image.open(pred_dir / f"{row.case_id}.png"))
        gt_path = next(Path(record.original_label) for record in records if record.case_id == row.case_id)
        gt = np.array(Image.open(gt_path))
        draw_overlay(source_dir / f"{row.case_id}.jpg", pred, gt, overlay_path)
        overlay_paths.append(overlay_path)
    contact_sheet_path = experiment_dir / "evaluation" / "example_visualizations" / f"{split_name}_examples.jpg"
    build_contact_sheet(split_name, selected, overlay_paths, contact_sheet_path)

    manifest = {
        "framework": "pytorch_unet2d",
        "split_name": split_name,
        "metrics_csv": str(metrics_csv),
        "summary_json": str(summary_path),
        "overlay_dir": str(overlay_dir),
        "example_contact_sheet": str(contact_sheet_path),
        "prediction_dir": str(pred_dir),
        "probability_dir": str(prob_dir) if prob_dir is not None else None,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    save_json(experiment_dir / f"unet2d_eval_manifest_{split_name}.json", manifest)
    return {
        "name": split_name,
        "case_count": len(rows),
        "mean_dice": mean_dice,
        "mean_iou": mean_iou,
        "mean_boundary_f1": mean_boundary_f1,
        "mean_shape_gap": mean_shape_gap,
        "mean_inside_lumen_ratio": mean_inside_lumen_ratio,
        "zero_dice_count": zero_count,
        "zero_dice_ratio": zero_ratio,
        "summary_json": str(summary_path),
        "metrics_csv": str(metrics_csv),
        "example_contact_sheet": str(contact_sheet_path),
    }


def build_overall_summary_markdown(
    experiment_name: str,
    config_path: Path,
    best_checkpoint: Path,
    split_summary: dict[str, dict[str, object]],
    split_summary_rows: list[dict[str, object]],
) -> str:
    lines = [
        f"# `{experiment_name}`",
        "",
        "PyTorch UNet2D segmentation baseline on the fixed `crop_ui` holdout dataset.",
        "",
        f"- config: `{config_path}`",
        f"- best checkpoint: `{best_checkpoint}`",
        "",
        "## Evaluation Summary",
        "",
        "| Split | Cases | Mean Dice | Mean IoU | Boundary F1 | Shape Gap | Inside Lumen Ratio | Zero-Dice Cases | Zero-Dice Ratio |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in split_summary_rows:
        lines.append(
            f"| {row['name']} | {row['case_count']} | {float(row['mean_dice']):.4f} | "
            f"{float(row['mean_iou']):.4f} | {float(row['mean_boundary_f1']):.4f} | "
            f"{float(row['mean_shape_gap']):.4f} | {float(row['mean_inside_lumen_ratio']):.4f} | "
            f"{row['zero_dice_count']} | {float(row['zero_dice_ratio']):.4f} |"
        )
    lines.extend(
        [
            "",
            "## Result Files",
            "",
            f"- training curves: `{experiment_name}/report/training_curves.png`",
            f"- evaluation summary: `{experiment_name}/report/evaluation_summary.png`",
            f"- internal examples: `{split_summary['internal_holdout']['example_contact_sheet']}`",
            f"- external examples: `{split_summary['external_eval']['example_contact_sheet']}`",
            f"- prospective examples: `{split_summary['prospective_eval']['example_contact_sheet']}`",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    config_path = args.config if args.config.is_absolute() else (PROJECT_ROOT / args.config)
    config_path = config_path.resolve()
    config = load_yaml(config_path)

    train_cfg = config.get("train", {})
    eval_cfg = config.get("evaluation", {})
    model_cfg = config.get("model", {})
    auxiliary_cfg = model_cfg.get("auxiliary", {})
    paths_cfg = config.get("paths", {})

    dataset_root = resolve_project_path(paths_cfg.get("dataset_root"))
    experiment_root = resolve_project_path(paths_cfg.get("experiment_root"))
    if dataset_root is None or experiment_root is None:
        raise ValueError("Missing dataset_root or experiment_root")

    dataset_manifest_path = dataset_root / "dataset_manifest.json"
    if not dataset_manifest_path.exists():
        raise FileNotFoundError(f"Missing dataset manifest: {dataset_manifest_path}")

    experiment_name = compute_experiment_name(config, args.exp_name)
    experiment_dir = experiment_root / experiment_name
    if experiment_dir.exists() and any(experiment_dir.iterdir()):
        raise FileExistsError(
            f"Experiment directory already exists and is not empty: {experiment_dir}. "
            "Use --exp-name to choose a new directory."
        )
    ensure_dir(experiment_dir)
    ensure_dir(experiment_dir / "checkpoints")
    ensure_dir(experiment_dir / "report")

    (experiment_dir / "run_command.sh").write_text(" ".join(shlex.quote(part) for part in sys.argv) + "\n", encoding="utf-8")
    write_yaml(experiment_dir / "project_config_snapshot.yaml", config)

    seed = int(train_cfg.get("seed", 666))
    set_seed(seed)

    train_records_all, holdout_records, eval_sources = load_records(dataset_manifest_path)
    train_records, val_records, split_summary = split_train_val(
        train_records_all,
        float(train_cfg.get("val_fraction", 0.1)),
        seed,
    )
    save_json(
        experiment_dir / "train_val_split.json",
        {
            "summary": split_summary,
            "train_case_ids": [record.case_id for record in train_records],
            "val_case_ids": [record.case_id for record in val_records],
        },
    )
    if args.max_train_samples is not None:
        train_records = train_records[: args.max_train_samples]
        val_records = val_records[: max(1, min(len(val_records), max(1, args.max_train_samples // 8)))]
        holdout_records = holdout_records[: max(1, min(len(holdout_records), max(1, args.max_train_samples // 4)))]
        eval_sources = {
            name: records[: max(1, min(len(records), args.max_eval_samples or 32))]
            for name, records in eval_sources.items()
        }
    elif args.max_eval_samples is not None:
        holdout_records = holdout_records[: args.max_eval_samples]
        eval_sources = {name: records[: args.max_eval_samples] for name, records in eval_sources.items()}

    image_size = int(train_cfg.get("image_size", 512))
    batch_size = int(train_cfg.get("batch_size", 16))
    num_workers = int(train_cfg.get("num_workers", 4))
    epochs = int(args.override_epochs or train_cfg.get("epochs", 30))
    threshold = float(train_cfg.get("threshold", 0.5))
    device = device_from_config(str(train_cfg.get("device", "cuda" if torch.cuda.is_available() else "cpu")))
    eval_device = device_from_config(str(eval_cfg.get("device", device.type)))
    use_amp = bool(train_cfg.get("amp", True)) and device.type == "cuda"

    aug_cfg = train_cfg.get("augmentation", {})
    train_loader = create_loader(
        train_records,
        image_size,
        batch_size,
        num_workers,
        shuffle=True,
        augment=True,
        brightness_jitter=float(aug_cfg.get("brightness_jitter", 0.0)),
        contrast_jitter=float(aug_cfg.get("contrast_jitter", 0.0)),
        hflip_prob=float(aug_cfg.get("hflip_prob", 0.0)),
    )
    val_loader = create_loader(
        val_records,
        image_size,
        batch_size,
        num_workers,
        shuffle=False,
        augment=False,
    )

    model = build_segmentation_model(model_cfg).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(train_cfg.get("lr", 1e-3)),
        weight_decay=float(train_cfg.get("weight_decay", 1e-4)),
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(epochs, 1))
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    pos_weight = torch.tensor([float(train_cfg.get("positive_class_weight", 1.0))], device=device)
    bce_loss = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    bce_weight = float(train_cfg.get("bce_weight", 0.5))
    dice_weight = float(train_cfg.get("dice_weight", 0.5))

    history: list[dict[str, float]] = []
    best_val_dice = -1.0
    best_epoch = -1
    patience = int(train_cfg.get("early_stopping_patience", 10))
    epochs_without_improvement = 0
    train_log_path = experiment_dir / "train_metrics.csv"
    with train_log_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "epoch",
                "train_loss",
                "train_dice",
                "train_iou",
                "train_boundary_loss",
                "train_irregularity_loss",
                "train_blur_loss",
                "val_loss",
                "val_dice",
                "val_iou",
                "val_boundary_loss",
                "val_irregularity_loss",
                "val_blur_loss",
                "lr",
            ],
        )
        writer.writeheader()
        for epoch in range(1, epochs + 1):
            train_metrics = train_one_epoch(
                model,
                train_loader,
                optimizer,
                scaler,
                device,
                threshold,
                bce_loss,
                bce_weight,
                dice_weight,
                use_amp,
                auxiliary_cfg,
            )
            val_metrics = evaluate_loader(
                model,
                val_loader,
                device,
                threshold,
                bce_loss,
                bce_weight,
                dice_weight,
                use_amp,
                auxiliary_cfg,
            )
            lr = float(optimizer.param_groups[0]["lr"])
            row = {
                "epoch": epoch,
                "train_loss": train_metrics["loss"],
                "train_dice": train_metrics["dice"],
                "train_iou": train_metrics["iou"],
                "train_boundary_loss": train_metrics["boundary_loss"],
                "train_irregularity_loss": train_metrics["irregularity_loss"],
                "train_blur_loss": train_metrics["blur_loss"],
                "val_loss": val_metrics["loss"],
                "val_dice": val_metrics["dice"],
                "val_iou": val_metrics["iou"],
                "val_boundary_loss": val_metrics["boundary_loss"],
                "val_irregularity_loss": val_metrics["irregularity_loss"],
                "val_blur_loss": val_metrics["blur_loss"],
                "lr": lr,
            }
            writer.writerow(row)
            history.append(row)
            handle.flush()
            print(json.dumps({"epoch": epoch, **row}, ensure_ascii=False))

            checkpoint_dir = experiment_dir / "checkpoints"
            if epoch % int(train_cfg.get("save_every_epochs", 5)) == 0 or epoch == epochs:
                save_checkpoint(checkpoint_dir / f"epoch_{epoch:03d}.pt", model, optimizer, epoch, best_val_dice, config)
            if val_metrics["dice"] > best_val_dice:
                best_val_dice = val_metrics["dice"]
                best_epoch = epoch
                epochs_without_improvement = 0
                save_checkpoint(checkpoint_dir / "best.pt", model, optimizer, epoch, best_val_dice, config)
            else:
                epochs_without_improvement += 1
            scheduler.step()
            if epochs_without_improvement >= patience:
                print(json.dumps({"early_stop_epoch": epoch, "best_epoch": best_epoch, "best_val_dice": best_val_dice}, ensure_ascii=False))
                break

    best_checkpoint = experiment_dir / "checkpoints" / "best.pt"
    if not best_checkpoint.exists():
        raise FileNotFoundError(f"Best checkpoint not found: {best_checkpoint}")
    checkpoint = torch.load(best_checkpoint, map_location=eval_device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model = model.to(eval_device)

    internal_summary = run_split_evaluation(
        model,
        holdout_records,
        image_size,
        int(eval_cfg.get("batch_size", batch_size)),
        int(eval_cfg.get("num_workers", max(0, num_workers // 2))),
        eval_device,
        float(eval_cfg.get("threshold", threshold)),
        bool(eval_cfg.get("save_probability", False)),
        experiment_dir,
        "internal_holdout",
        int(eval_cfg.get("representative_examples_per_bucket", 1)),
    )
    external_summary = run_split_evaluation(
        model,
        eval_sources.get("external_eval", []),
        image_size,
        int(eval_cfg.get("batch_size", batch_size)),
        int(eval_cfg.get("num_workers", max(0, num_workers // 2))),
        eval_device,
        float(eval_cfg.get("threshold", threshold)),
        bool(eval_cfg.get("save_probability", False)),
        experiment_dir,
        "external_eval",
        int(eval_cfg.get("representative_examples_per_bucket", 1)),
    )
    prospective_summary = run_split_evaluation(
        model,
        eval_sources.get("prospective_eval", []),
        image_size,
        int(eval_cfg.get("batch_size", batch_size)),
        int(eval_cfg.get("num_workers", max(0, num_workers // 2))),
        eval_device,
        float(eval_cfg.get("threshold", threshold)),
        bool(eval_cfg.get("save_probability", False)),
        experiment_dir,
        "prospective_eval",
        int(eval_cfg.get("representative_examples_per_bucket", 1)),
    )

    split_summaries = {
        "internal_holdout": internal_summary,
        "external_eval": external_summary,
        "prospective_eval": prospective_summary,
    }
    split_summary_rows = [internal_summary, external_summary, prospective_summary]
    save_json(experiment_dir / "evaluation" / "overall_summary.json", split_summaries)
    plot_training_curves(history, experiment_dir / "report" / "training_curves.png")
    plot_evaluation_summary(split_summary_rows, experiment_dir / "report" / "evaluation_summary.png")
    overall_md = build_overall_summary_markdown(
        experiment_name,
        config_path,
        best_checkpoint,
        split_summaries,
        split_summary_rows,
    )
    (experiment_dir / "evaluation" / "overall_summary.md").write_text(overall_md, encoding="utf-8")
    readme = "\n".join(
        [
            f"# {experiment_name}",
            "",
            "PyTorch binary segmentation training run.",
            "",
            f"- config: `{config_path}`",
            f"- dataset manifest: `{dataset_manifest_path}`",
            f"- model architecture: `{model_cfg.get('architecture', 'unet2d')}`",
            f"- best checkpoint: `{best_checkpoint}`",
            f"- report dir: `{experiment_dir / 'report'}`",
            "",
            "## Split Summary",
            "",
            f"- training images: `{split_summary['train_images']}`",
            f"- validation images: `{split_summary['val_images']}`",
            f"- internal holdout images: `{len(holdout_records)}`",
            f"- external eval images: `{len(eval_sources.get('external_eval', []))}`",
            f"- prospective eval images: `{len(eval_sources.get('prospective_eval', []))}`",
        ]
    )
    (experiment_dir / "README.md").write_text(readme + "\n", encoding="utf-8")

    run_manifest = {
        "framework": "pytorch_segmentation",
        "model_architecture": str(model_cfg.get("architecture", "unet2d")),
        "config_path": str(config_path),
        "dataset_root": str(dataset_root),
        "dataset_manifest": str(dataset_manifest_path),
        "experiment_dir": str(experiment_dir),
        "best_checkpoint": str(best_checkpoint),
        "best_epoch": best_epoch,
        "best_val_dice": best_val_dice,
        "train_split_summary": split_summary,
        "device": str(device),
        "eval_device": str(eval_device),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "completed",
        "report": {
            "training_curves": str(experiment_dir / "report" / "training_curves.png"),
            "evaluation_summary": str(experiment_dir / "report" / "evaluation_summary.png"),
            "overall_summary_md": str(experiment_dir / "evaluation" / "overall_summary.md"),
        },
    }
    save_json(experiment_dir / "unet2d_run_manifest.json", run_manifest)
    print(json.dumps({"experiment_dir": str(experiment_dir), "best_checkpoint": str(best_checkpoint)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
