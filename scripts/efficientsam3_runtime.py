#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib
import json
import math
import random
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import yaml
from PIL import Image
from torch.utils.data import DataLoader, Dataset, Sampler, WeightedRandomSampler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_segmentation_example_panels import build_contact_sheet, pick_examples  # noqa: E402
from run_unet2d_segmentation_baseline import (  # noqa: E402
    compute_experiment_name,
    configure_matplotlib,
    device_from_config,
    ensure_dir,
    plot_evaluation_summary,
    plot_training_curves,
    resolve_project_path,
    save_json,
    set_seed,
    write_yaml,
)
from score_binary_segmentation_folder import draw_overlay  # noqa: E402


@dataclass(frozen=True)
class PromptableSampleRecord:
    case_id: str
    image_path: Path
    mask_path: Path
    overlay_image: Path
    source_split: str
    patient_id: str


@dataclass(frozen=True)
class ResizeMeta:
    original_width: int
    original_height: int
    resized_width: int
    resized_height: int
    pad_left: int
    pad_top: int
    resolution: int
    scale_x: float
    scale_y: float


@dataclass(frozen=True)
class PromptSpec:
    mode: str
    point_coords: np.ndarray | None
    point_labels: np.ndarray | None
    box_xyxy: np.ndarray | None


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping YAML: {path}")
    return data


def case_patient_id(case_id: str) -> str:
    base = case_id.removeprefix("lumen_")
    if "_" not in base:
        return base
    return base.rsplit("_", 1)[0]


def load_promptable_records(
    dataset_manifest_path: Path,
) -> tuple[list[PromptableSampleRecord], list[PromptableSampleRecord], dict[str, list[PromptableSampleRecord]]]:
    payload = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    training_records: list[PromptableSampleRecord] = []
    holdout_records: list[PromptableSampleRecord] = []
    for row in payload.get("cases", []):
        image_path = Path(row.get("original_image") or row["prepared_image"]).resolve()
        mask_path = Path(row.get("original_label") or row["prepared_label"]).resolve()
        overlay_image = Path(row.get("original_image") or row["prepared_image"]).resolve()
        record = PromptableSampleRecord(
            case_id=str(row["case_id"]),
            image_path=image_path,
            mask_path=mask_path,
            overlay_image=overlay_image,
            source_split=str(row["source_split"]),
            patient_id=case_patient_id(str(row["case_id"])),
        )
        if row["target_split"] == "training":
            training_records.append(record)
        elif row["target_split"] == "test":
            holdout_records.append(record)

    eval_sources: dict[str, list[PromptableSampleRecord]] = {}
    dataset_root = dataset_manifest_path.parent.resolve()
    for eval_name, summary in payload.get("evaluation_sources", {}).items():
        eval_root = Path(summary["output_root"]).resolve()
        label_dir = eval_root / "label"
        original_root = dataset_root / "eval_sources" / eval_name / "img"
        prepared_root = eval_root / "img"
        records: list[PromptableSampleRecord] = []
        for mask_path in sorted(label_dir.glob("*.png")):
            image_candidate = original_root / f"{mask_path.stem}.png"
            if not image_candidate.exists():
                image_candidate = prepared_root / f"{mask_path.stem}.png"
            if not image_candidate.exists():
                continue
            records.append(
                PromptableSampleRecord(
                    case_id=mask_path.stem,
                    image_path=image_candidate.resolve(),
                    mask_path=mask_path.resolve(),
                    overlay_image=image_candidate.resolve(),
                    source_split=eval_name,
                    patient_id=case_patient_id(mask_path.stem),
                )
            )
        eval_sources[eval_name] = records
    return training_records, holdout_records, eval_sources


def split_train_val(
    records: list[PromptableSampleRecord],
    val_fraction: float,
    seed: int,
) -> tuple[list[PromptableSampleRecord], list[PromptableSampleRecord], dict[str, int]]:
    grouped: dict[str, list[PromptableSampleRecord]] = {}
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


def load_rgb(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def load_mask(path: Path) -> Image.Image:
    return Image.open(path).convert("L")


def resize_with_pad(image: Image.Image, resolution: int, *, is_mask: bool) -> tuple[Image.Image, ResizeMeta]:
    original_width, original_height = image.size
    scale = min(resolution / max(original_width, 1), resolution / max(original_height, 1))
    resized_width = max(1, int(round(original_width * scale)))
    resized_height = max(1, int(round(original_height * scale)))
    resample = Image.NEAREST if is_mask else Image.BILINEAR
    resized = image.resize((resized_width, resized_height), resample=resample)
    canvas_mode = "L" if is_mask else "RGB"
    canvas_value = 0 if is_mask else (0, 0, 0)
    canvas = Image.new(canvas_mode, (resolution, resolution), color=canvas_value)
    pad_left = (resolution - resized_width) // 2
    pad_top = (resolution - resized_height) // 2
    canvas.paste(resized, (pad_left, pad_top))
    meta = ResizeMeta(
        original_width=original_width,
        original_height=original_height,
        resized_width=resized_width,
        resized_height=resized_height,
        pad_left=pad_left,
        pad_top=pad_top,
        resolution=resolution,
        scale_x=resized_width / max(original_width, 1),
        scale_y=resized_height / max(original_height, 1),
    )
    return canvas, meta


def transform_xy(coords: np.ndarray, meta: ResizeMeta) -> np.ndarray:
    out = coords.astype(np.float32).copy()
    out[:, 0] = out[:, 0] * meta.scale_x + meta.pad_left
    out[:, 1] = out[:, 1] * meta.scale_y + meta.pad_top
    return out


def transform_box_xyxy(box_xyxy: np.ndarray, meta: ResizeMeta) -> np.ndarray:
    coords = np.array(
        [
            [box_xyxy[0], box_xyxy[1]],
            [box_xyxy[2], box_xyxy[3]],
        ],
        dtype=np.float32,
    )
    coords = transform_xy(coords, meta)
    return np.array([coords[0, 0], coords[0, 1], coords[1, 0], coords[1, 1]], dtype=np.float32)


def mask_boundary(mask_bool: np.ndarray) -> np.ndarray:
    if mask_bool.size == 0:
        return mask_bool
    padded = np.pad(mask_bool, 1, mode="constant", constant_values=False)
    center = padded[1:-1, 1:-1]
    inner = center.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            inner &= padded[1 + dy : 1 + dy + center.shape[0], 1 + dx : 1 + dx + center.shape[1]]
    return center & ~inner


def mask_bbox(mask_bool: np.ndarray) -> np.ndarray:
    ys, xs = np.where(mask_bool)
    if len(xs) == 0:
        return np.array([0.0, 0.0, float(mask_bool.shape[1] - 1), float(mask_bool.shape[0] - 1)], dtype=np.float32)
    return np.array([float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())], dtype=np.float32)


def clip_box_xyxy(box_xyxy: np.ndarray, width: int, height: int) -> np.ndarray:
    x1, y1, x2, y2 = box_xyxy.astype(np.float32).tolist()
    x1 = max(0.0, min(x1, width - 1))
    y1 = max(0.0, min(y1, height - 1))
    x2 = max(x1 + 1.0, min(x2, width - 1))
    y2 = max(y1 + 1.0, min(y2, height - 1))
    return np.array([x1, y1, x2, y2], dtype=np.float32)


def jitter_box_xyxy(box_xyxy: np.ndarray, width: int, height: int, jitter_frac: float, rng: random.Random) -> np.ndarray:
    x1, y1, x2, y2 = box_xyxy.astype(np.float32).tolist()
    bw = max(x2 - x1, 1.0)
    bh = max(y2 - y1, 1.0)
    dx = bw * jitter_frac
    dy = bh * jitter_frac
    jittered = np.array(
        [
            x1 - rng.uniform(0.0, dx),
            y1 - rng.uniform(0.0, dy),
            x2 + rng.uniform(0.0, dx),
            y2 + rng.uniform(0.0, dy),
        ],
        dtype=np.float32,
    )
    return clip_box_xyxy(jittered, width, height)


def bbox_expand_xyxy(box_xyxy: np.ndarray, width: int, height: int, expand_frac: float) -> np.ndarray:
    x1, y1, x2, y2 = box_xyxy.astype(np.float32).tolist()
    bw = max(x2 - x1, 1.0)
    bh = max(y2 - y1, 1.0)
    expanded = np.array(
        [
            x1 - bw * expand_frac,
            y1 - bh * expand_frac,
            x2 + bw * expand_frac,
            y2 + bh * expand_frac,
        ],
        dtype=np.float32,
    )
    return clip_box_xyxy(expanded, width, height)


def sample_from_mask(mask_bool: np.ndarray, rng: random.Random) -> np.ndarray:
    ys, xs = np.where(mask_bool)
    if len(xs) == 0:
        return np.array([[0.5, 0.5]], dtype=np.float32)
    idx = rng.randrange(len(xs))
    return np.array([[float(xs[idx]), float(ys[idx])]], dtype=np.float32)


def centroid_from_mask(mask_bool: np.ndarray) -> np.ndarray:
    ys, xs = np.where(mask_bool)
    if len(xs) == 0:
        return np.array([[0.5, 0.5]], dtype=np.float32)
    return np.array([[float(xs.mean()), float(ys.mean())]], dtype=np.float32)


def nearest_positive(mask_bool: np.ndarray, target_xy: np.ndarray) -> np.ndarray:
    ys, xs = np.where(mask_bool)
    if len(xs) == 0:
        return target_xy[None, :].astype(np.float32)
    coords = np.stack([xs, ys], axis=1).astype(np.float32)
    dist2 = ((coords - target_xy[None, :]) ** 2).sum(axis=1)
    best = coords[int(np.argmin(dist2))]
    return best[None, :]


def sample_boundary_point(mask_bool: np.ndarray, rng: random.Random) -> np.ndarray:
    boundary = mask_boundary(mask_bool)
    if not boundary.any():
        return sample_from_mask(mask_bool, rng)
    return sample_from_mask(boundary, rng)


def sample_negative_point(
    mask_bool: np.ndarray,
    box_xyxy: np.ndarray,
    rng: random.Random,
    band_frac: float,
) -> np.ndarray:
    height, width = mask_bool.shape
    expanded = bbox_expand_xyxy(box_xyxy, width, height, band_frac)
    x1, y1, x2, y2 = expanded.astype(int).tolist()
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(x1 + 1, min(x2, width))
    y2 = max(y1 + 1, min(y2, height))
    candidate = np.zeros_like(mask_bool, dtype=bool)
    candidate[y1:y2, x1:x2] = True
    candidate &= ~mask_bool
    if not candidate.any():
        candidate = ~mask_bool
    if not candidate.any():
        return np.array([[0.5, 0.5]], dtype=np.float32)
    return sample_from_mask(candidate, rng)


def apply_point_jitter(
    point_xy: np.ndarray,
    mask_bool: np.ndarray,
    rng: random.Random,
    jitter_frac: float,
    box_xyxy: np.ndarray,
) -> np.ndarray:
    x1, y1, x2, y2 = box_xyxy.astype(np.float32).tolist()
    bw = max(x2 - x1, 1.0)
    bh = max(y2 - y1, 1.0)
    point = point_xy.astype(np.float32).copy()
    point[0, 0] += rng.uniform(-bw * jitter_frac, bw * jitter_frac)
    point[0, 1] += rng.uniform(-bh * jitter_frac, bh * jitter_frac)
    point[0, 0] = max(0.0, min(point[0, 0], mask_bool.shape[1] - 1))
    point[0, 1] = max(0.0, min(point[0, 1], mask_bool.shape[0] - 1))
    return nearest_positive(mask_bool, point[0])


class PromptBuilder:
    def __init__(
        self,
        train_modes: list[str],
        eval_modes: list[str],
        *,
        box_jitter: float = 0.1,
        point_jitter: float = 0.03,
        negative_band: float = 0.15,
        prompt_dropout_prob: float = 0.0,
        use_prompt_dropout: bool = False,
    ) -> None:
        self.train_modes = list(train_modes)
        self.eval_modes = list(eval_modes)
        self.box_jitter = float(box_jitter)
        self.point_jitter = float(point_jitter)
        self.negative_band = float(negative_band)
        self.prompt_dropout_prob = float(prompt_dropout_prob)
        self.use_prompt_dropout = bool(use_prompt_dropout)

    def choose_train_mode(self, rng: random.Random) -> str:
        if not self.train_modes:
            return "box"
        return rng.choice(self.train_modes)

    def build(
        self,
        mask_array: np.ndarray,
        meta: ResizeMeta,
        *,
        mode: str,
        rng: random.Random,
        jitter: bool,
    ) -> PromptSpec:
        mask_bool = mask_array > 0
        raw_box = mask_bbox(mask_bool)
        box_xyxy = raw_box.copy()
        if jitter:
            box_xyxy = jitter_box_xyxy(box_xyxy, meta.original_width, meta.original_height, self.box_jitter, rng)

        positive_point = centroid_from_mask(mask_bool)
        if mode in {"single_positive_point", "box_plus_point"}:
            positive_point = apply_point_jitter(positive_point, mask_bool, rng, self.point_jitter, box_xyxy) if jitter else positive_point
        if mode == "positive_plus_negative_points":
            positive_point = sample_boundary_point(mask_bool, rng)
            positive_point = apply_point_jitter(positive_point, mask_bool, rng, self.point_jitter, box_xyxy) if jitter else positive_point

        negative_point = sample_negative_point(mask_bool, box_xyxy, rng, self.negative_band)

        transformed_box = transform_box_xyxy(box_xyxy, meta)
        box_coords = np.array(
            [
                [transformed_box[0], transformed_box[1]],
                [transformed_box[2], transformed_box[3]],
            ],
            dtype=np.float32,
        )

        if mode == "box":
            coords = box_coords
            labels = np.array([2, 3], dtype=np.int64)
            box_value = transformed_box
        elif mode == "single_positive_point":
            coords = transform_xy(positive_point, meta)
            labels = np.array([1], dtype=np.int64)
            box_value = None
        elif mode == "positive_plus_negative_points":
            coords = transform_xy(np.concatenate([positive_point, negative_point], axis=0), meta)
            labels = np.array([1, 0], dtype=np.int64)
            box_value = None
        elif mode == "box_plus_point":
            coords = np.concatenate([box_coords, transform_xy(positive_point, meta)], axis=0)
            labels = np.array([2, 3, 1], dtype=np.int64)
            box_value = transformed_box
        else:
            raise ValueError(f"Unsupported prompt mode: {mode}")

        if self.use_prompt_dropout and rng.random() < self.prompt_dropout_prob and len(labels) > 1:
            keep_index = rng.randrange(len(labels))
            coords = coords[keep_index : keep_index + 1]
            labels = labels[keep_index : keep_index + 1]
            box_value = None if labels[0] not in (2, 3) else box_value

        return PromptSpec(mode=mode, point_coords=coords.astype(np.float32), point_labels=labels, box_xyxy=box_value)


def normalize_rgb_tensor(image_arr: np.ndarray) -> torch.Tensor:
    tensor = torch.from_numpy(image_arr.transpose(2, 0, 1)).float() / 255.0
    return tensor


class EfficientSAM3TrainDataset(Dataset):
    def __init__(
        self,
        records: list[PromptableSampleRecord],
        *,
        resolution: int,
        prompt_builder: PromptBuilder,
        prompt_seed: int,
        train: bool,
        consistency_enabled: bool,
        brightness_jitter: float = 0.0,
        contrast_jitter: float = 0.0,
        hflip_prob: float = 0.0,
        compute_foreground_fractions: bool = False,
    ) -> None:
        self.records = records
        self.resolution = int(resolution)
        self.prompt_builder = prompt_builder
        self.prompt_seed = int(prompt_seed)
        self.train = bool(train)
        self.consistency_enabled = bool(consistency_enabled)
        self.brightness_jitter = float(brightness_jitter)
        self.contrast_jitter = float(contrast_jitter)
        self.hflip_prob = float(hflip_prob)
        self.foreground_fractions = (
            self._compute_foreground_fractions()
            if compute_foreground_fractions
            else [1.0] * len(self.records)
        )

    def _compute_foreground_fractions(self) -> list[float]:
        fractions: list[float] = []
        for record in self.records:
            mask = np.array(load_mask(record.mask_path), dtype=np.uint8) > 0
            fractions.append(float(mask.mean()))
        return fractions

    def sample_weights(self) -> list[float]:
        weights: list[float] = []
        for frac in self.foreground_fractions:
            if frac <= 0:
                weights.append(2.0)
            elif frac < 0.01:
                weights.append(3.0)
            elif frac < 0.03:
                weights.append(2.0)
            elif frac < 0.08:
                weights.append(1.4)
            else:
                weights.append(1.0)
        return weights

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, index: int) -> dict[str, Any]:
        record = self.records[index]
        rng = random.Random(self.prompt_seed + index * 9973)
        image = load_rgb(record.image_path)
        mask = load_mask(record.mask_path)
        image_padded, meta = resize_with_pad(image, self.resolution, is_mask=False)
        mask_padded, _ = resize_with_pad(mask, self.resolution, is_mask=True)

        image_arr = np.array(image_padded, dtype=np.uint8)
        mask_arr = (np.array(mask_padded, dtype=np.uint8) > 0).astype(np.float32)

        if self.train and rng.random() < self.hflip_prob:
            image_arr = np.ascontiguousarray(np.fliplr(image_arr))
            mask_arr = np.ascontiguousarray(np.fliplr(mask_arr))

        if self.train and self.brightness_jitter > 0:
            scale = 1.0 + rng.uniform(-self.brightness_jitter, self.brightness_jitter)
            image_arr = np.clip(image_arr.astype(np.float32) * scale, 0.0, 255.0).astype(np.uint8)
        if self.train and self.contrast_jitter > 0:
            mean = image_arr.astype(np.float32).mean(axis=(0, 1), keepdims=True)
            scale = 1.0 + rng.uniform(-self.contrast_jitter, self.contrast_jitter)
            image_arr = np.clip((image_arr.astype(np.float32) - mean) * scale + mean, 0.0, 255.0).astype(np.uint8)

        transformed_meta = ResizeMeta(
            original_width=self.resolution,
            original_height=self.resolution,
            resized_width=self.resolution,
            resized_height=self.resolution,
            pad_left=0,
            pad_top=0,
            resolution=self.resolution,
            scale_x=1.0,
            scale_y=1.0,
        )
        mode = self.prompt_builder.choose_train_mode(rng) if self.train else (self.prompt_builder.eval_modes[0] if self.prompt_builder.eval_modes else "box")
        prompt = self.prompt_builder.build(
            (mask_arr * 255.0).astype(np.uint8),
            transformed_meta,
            mode=mode,
            rng=rng,
            jitter=self.train,
        )
        alt_prompt = None
        if self.consistency_enabled:
            alt_mode_candidates = [value for value in self.prompt_builder.train_modes if value != mode]
            alt_mode = rng.choice(alt_mode_candidates) if alt_mode_candidates else mode
            alt_prompt = self.prompt_builder.build(
                (mask_arr * 255.0).astype(np.uint8),
                transformed_meta,
                mode=alt_mode,
                rng=random.Random(self.prompt_seed + index * 9973 + 17),
                jitter=self.train,
            )

        return {
            "image": normalize_rgb_tensor(image_arr),
            "mask": torch.from_numpy(mask_arr[None, ...]).float(),
            "case_id": record.case_id,
            "mask_path": str(record.mask_path),
            "overlay_image": str(record.overlay_image),
            "prompt": prompt,
            "alt_prompt": alt_prompt,
            "prompt_mode": prompt.mode,
            "original_width": meta.original_width,
            "original_height": meta.original_height,
        }


def collate_promptable(batch: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "image": torch.stack([item["image"] for item in batch]),
        "mask": torch.stack([item["mask"] for item in batch]),
        "case_id": [str(item["case_id"]) for item in batch],
        "mask_path": [str(item["mask_path"]) for item in batch],
        "overlay_image": [str(item["overlay_image"]) for item in batch],
        "prompt": [item["prompt"] for item in batch],
        "alt_prompt": [item["alt_prompt"] for item in batch],
        "prompt_mode": [str(item["prompt_mode"]) for item in batch],
        "original_width": [int(item["original_width"]) for item in batch],
        "original_height": [int(item["original_height"]) for item in batch],
    }


def build_sampler(records: list[PromptableSampleRecord], dataset: EfficientSAM3TrainDataset, enabled: bool, seed: int) -> Sampler[int] | None:
    if not enabled or not records:
        return None
    generator = torch.Generator()
    generator.manual_seed(seed)
    weights = torch.tensor(dataset.sample_weights(), dtype=torch.double)
    return WeightedRandomSampler(weights=weights, num_samples=len(records), replacement=True, generator=generator)


def create_promptable_loader(
    records: list[PromptableSampleRecord],
    *,
    resolution: int,
    batch_size: int,
    num_workers: int,
    prompt_builder: PromptBuilder,
    prompt_seed: int,
    train: bool,
    consistency_enabled: bool,
    brightness_jitter: float = 0.0,
    contrast_jitter: float = 0.0,
    hflip_prob: float = 0.0,
    hard_example_oversampling: bool = False,
) -> DataLoader:
    dataset = EfficientSAM3TrainDataset(
        records,
        resolution=resolution,
        prompt_builder=prompt_builder,
        prompt_seed=prompt_seed,
        train=train,
        consistency_enabled=consistency_enabled,
        brightness_jitter=brightness_jitter,
        contrast_jitter=contrast_jitter,
        hflip_prob=hflip_prob,
        compute_foreground_fractions=hard_example_oversampling and train,
    )
    sampler = build_sampler(records, dataset, hard_example_oversampling and train, prompt_seed)
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=sampler is None and train,
        sampler=sampler,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
        collate_fn=collate_promptable,
    )


class LoRALinear(nn.Module):
    def __init__(self, base: nn.Linear, rank: int, alpha: float, dropout: float) -> None:
        super().__init__()
        if rank <= 0:
            raise ValueError("LoRA rank must be positive")
        self.base = base
        self.rank = int(rank)
        self.alpha = float(alpha)
        self.scaling = self.alpha / self.rank
        self.dropout = nn.Dropout(dropout) if dropout > 0 else nn.Identity()
        self.lora_a = nn.Linear(base.in_features, self.rank, bias=False)
        self.lora_b = nn.Linear(self.rank, base.out_features, bias=False)
        nn.init.kaiming_uniform_(self.lora_a.weight, a=math.sqrt(5))
        nn.init.zeros_(self.lora_b.weight)
        for parameter in self.base.parameters():
            parameter.requires_grad = False

    @property
    def weight(self) -> torch.Tensor:
        return self.base.weight

    @property
    def bias(self) -> torch.Tensor | None:
        return self.base.bias

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.base(x) + self.lora_b(self.lora_a(self.dropout(x))) * self.scaling


def named_linear_modules(module: nn.Module) -> list[tuple[str, nn.Linear]]:
    return [(name, child) for name, child in module.named_modules() if isinstance(child, nn.Linear)]


def get_parent_module(root: nn.Module, dotted_name: str) -> tuple[nn.Module, str]:
    if "." not in dotted_name:
        return root, dotted_name
    parent_name, child_name = dotted_name.rsplit(".", 1)
    parent = root
    for part in parent_name.split("."):
        parent = getattr(parent, part)
    return parent, child_name


def apply_lora_by_patterns(
    module: nn.Module,
    *,
    include_patterns: list[str],
    exclude_patterns: list[str],
    rank: int,
    alpha: float,
    dropout: float,
) -> list[str]:
    include = [re.compile(pattern) for pattern in include_patterns]
    exclude = [re.compile(pattern) for pattern in exclude_patterns]
    patched: list[str] = []
    for name, child in named_linear_modules(module):
        if include and not any(pattern.search(name) for pattern in include):
            continue
        if exclude and any(pattern.search(name) for pattern in exclude):
            continue
        parent, attr = get_parent_module(module, name)
        setattr(parent, attr, LoRALinear(child, rank=rank, alpha=alpha, dropout=dropout))
        patched.append(name)
    return patched


class ClipSemanticAdapter(nn.Module):
    """Fuse CLIP patch, image-text similarity and text features into SAM features."""

    def __init__(self, clip_dim: int, target_channels: int) -> None:
        super().__init__()
        hidden = max(32, min(256, target_channels))
        self.visual_similarity = nn.Sequential(
            nn.Linear(clip_dim + 1, hidden),
            nn.GELU(),
            nn.Linear(hidden, target_channels),
        )
        self.text = nn.Sequential(
            nn.Linear(clip_dim, hidden),
            nn.GELU(),
            nn.Linear(hidden, target_channels),
        )
        # Zero semantic residual preserves the pretrained SAM output at step 0
        # while keeping a nonzero gradient for the adapter projections.
        nn.init.zeros_(self.visual_similarity[-1].weight)
        nn.init.zeros_(self.visual_similarity[-1].bias)
        nn.init.zeros_(self.text[-1].weight)
        nn.init.zeros_(self.text[-1].bias)
        self.gain = nn.Parameter(torch.ones(1))

    def forward(
        self,
        base_features: torch.Tensor,
        patch_features: torch.Tensor,
        text_features: torch.Tensor,
    ) -> torch.Tensor:
        batch_size, num_patches, _ = patch_features.shape
        side = int(round(math.sqrt(num_patches)))
        if side * side != num_patches:
            raise ValueError(f"Expected square CLIP patch grid, got {num_patches} patches")
        patch_features = F.normalize(patch_features, dim=-1)
        text_features = F.normalize(text_features, dim=-1)
        similarity = (patch_features * text_features[:, None, :]).sum(dim=-1, keepdim=True)
        visual_input = torch.cat([patch_features, similarity], dim=-1)
        visual_condition = self.visual_similarity(visual_input)
        visual_condition = visual_condition.transpose(1, 2).reshape(
            batch_size, -1, side, side
        )
        if base_features.ndim == 3:
            token_side = int(round(math.sqrt(base_features.shape[1])))
            if token_side * token_side != base_features.shape[1]:
                raise ValueError(
                    f"Expected square SAM token grid, got {base_features.shape[1]} tokens"
                )
            visual_condition = F.interpolate(
                visual_condition,
                size=(token_side, token_side),
                mode="bilinear",
                align_corners=False,
            )
            text_condition = self.text(text_features).unsqueeze(1)
            return base_features + self.gain * (
                visual_condition.flatten(2).transpose(1, 2) + text_condition
            )
        visual_condition = F.interpolate(
            visual_condition,
            size=base_features.shape[-2:],
            mode="bilinear",
            align_corners=False,
        )
        text_condition = self.text(text_features).view(batch_size, -1, 1, 1)
        return base_features + self.gain * (visual_condition + text_condition)


class ClipSemanticGuidance(nn.Module):
    """CLIP semantic conditioning for FPN or TinyViT block features."""

    def __init__(
        self,
        config: dict[str, Any],
        block_specs: list[tuple[str, int]] | None = None,
    ) -> None:
        super().__init__()
        try:
            import open_clip
        except ImportError as exc:
            raise ImportError("clip_guidance requires the open_clip package") from exc

        model_name = str(config.get("model_name", "ViT-B-32"))
        pretrained = str(config.get("pretrained", "openai"))
        self.input_resolution = int(config.get("input_resolution", 224))
        self.injection_mode = str(config.get("injection_mode", "fpn")).strip().lower()
        self.block_specs = list(block_specs or [])
        self.block_key_by_name = {
            name: f"block_{index:03d}" for index, (name, _) in enumerate(self.block_specs)
        }
        self._block_hooks: list[Any] = []
        self._context: tuple[torch.Tensor, torch.Tensor] | None = None
        self.train_clip_vision = bool(config.get("train_clip_vision", False))
        self.clip_train_patterns = [
            re.compile(pattern) for pattern in config.get("clip_train_patterns", [])
        ]
        self.clip_model, _, _ = open_clip.create_model_and_transforms(
            model_name,
            pretrained=pretrained,
        )
        self.clip_model.visual.output_tokens = True
        self.clip_model.eval()
        set_requires_grad(self.clip_model, False)

        tokenizer = open_clip.get_tokenizer(model_name)
        text_prompts = list(
            config.get(
                "text_prompts",
                ["gastric wall lesion on ultrasound"],
            )
        )
        self.configured_text_prompts = text_prompts
        with torch.no_grad():
            text_tokens = tokenizer(text_prompts)
            text_features = self.clip_model.encode_text(text_tokens)
            text_features = F.normalize(text_features.float(), dim=-1).mean(dim=0, keepdim=True)
            text_features = F.normalize(text_features, dim=-1)
            dummy = torch.zeros(1, 3, self.input_resolution, self.input_resolution)
            _, patch_tokens = self.clip_model.visual(dummy)
            if self.clip_model.visual.proj is not None:
                patch_tokens = patch_tokens @ self.clip_model.visual.proj
            clip_dim = int(patch_tokens.shape[-1])
        self.register_buffer("text_features", text_features.float(), persistent=True)
        self.clip_dim = clip_dim
        if self.injection_mode == "block":
            if not self.block_specs:
                raise ValueError("Block semantic injection requires non-empty block_specs")
            self.adapters = nn.ModuleList()
            self.block_adapters = nn.ModuleDict(
                {
                    self.block_key_by_name[name]: ClipSemanticAdapter(clip_dim, int(channels))
                    for name, channels in self.block_specs
                }
            )
        else:
            target_channels = list(config.get("target_channels", [256, 32, 64]))
            self.adapters = nn.ModuleList(
                [ClipSemanticAdapter(clip_dim, int(channels)) for channels in target_channels]
            )
            self.block_adapters = nn.ModuleDict()
        self.register_buffer(
            "clip_mean",
            torch.tensor([0.48145466, 0.4578275, 0.40821073]).view(1, 3, 1, 1),
            persistent=False,
        )
        self.register_buffer(
            "clip_std",
            torch.tensor([0.26862954, 0.26130258, 0.27577711]).view(1, 3, 1, 1),
            persistent=False,
        )
        self.configure_trainable()

    def configure_trainable(self) -> None:
        set_requires_grad(self.clip_model, False)
        if self.train_clip_vision:
            for name, parameter in self.clip_model.visual.named_parameters():
                if not self.clip_train_patterns or any(
                    pattern.search(name) for pattern in self.clip_train_patterns
                ):
                    parameter.requires_grad = True
        set_requires_grad(self.adapters, True)
        set_requires_grad(self.block_adapters, True)

    def apply_train_mode(self, mode: bool) -> None:
        if mode and self.train_clip_vision:
            self.clip_model.train()
        else:
            self.clip_model.eval()
        self.adapters.train(mode)
        self.block_adapters.train(mode)

    def trainable_parameter_summary(self) -> dict[str, Any]:
        clip_trainable = sum(
            parameter.numel()
            for parameter in self.clip_model.parameters()
            if parameter.requires_grad
        )
        adapter_trainable = sum(
            parameter.numel() for parameter in self.adapters.parameters() if parameter.requires_grad
        )
        block_adapter_trainable = sum(
            parameter.numel()
            for parameter in self.block_adapters.parameters()
            if parameter.requires_grad
        )
        return {
            "model_name": self.clip_model.__class__.__name__,
            "injection_mode": self.injection_mode,
            "clip_trainable_parameters": clip_trainable,
            "adapter_trainable_parameters": adapter_trainable,
            "block_adapter_trainable_parameters": block_adapter_trainable,
            "block_adapter_count": len(self.block_adapters),
            "text_prompts": self.configured_text_prompts if hasattr(self, "configured_text_prompts") else [],
        }

    def attach_block_hooks(self, root: nn.Module) -> None:
        if self.injection_mode != "block":
            return
        modules = dict(root.named_modules())
        for name, _ in self.block_specs:
            if name not in modules:
                raise KeyError(f"Semantic adapter target module not found: {name}")
            key = self.block_key_by_name[name]
            self._block_hooks.append(
                modules[name].register_forward_hook(
                    lambda _module, _inputs, output, adapter_key=key: self.inject_block(
                        adapter_key,
                        output,
                    )
                )
            )

    def prepare_context(self, images: torch.Tensor) -> None:
        clip_images = F.interpolate(
            images,
            size=(self.input_resolution, self.input_resolution),
            mode="bicubic",
            align_corners=False,
        )
        clip_images = (clip_images - self.clip_mean) / self.clip_std
        context = (
            torch.enable_grad()
            if self.train_clip_vision and self.training
            else torch.no_grad()
        )
        with context:
            _, patch_tokens = self.clip_model.visual(clip_images)
            if self.clip_model.visual.proj is not None:
                patch_tokens = patch_tokens @ self.clip_model.visual.proj
            patch_tokens = patch_tokens.float()
        text_features = self.text_features.expand(images.shape[0], -1)
        self._context = (patch_tokens, text_features)

    def clear_context(self) -> None:
        self._context = None

    def inject_block(self, adapter_key: str, output: torch.Tensor) -> torch.Tensor:
        if self._context is None:
            return output
        patch_features, text_features = self._context
        return self.block_adapters[adapter_key](output, patch_features, text_features)

    def forward(
        self,
        images: torch.Tensor,
        image_embed: torch.Tensor,
        high_res_feats: list[torch.Tensor],
    ) -> tuple[torch.Tensor, list[torch.Tensor]]:
        if self.injection_mode != "fpn":
            raise RuntimeError("ClipSemanticGuidance.forward is only valid in fpn mode")
        self.prepare_context(images)
        patch_tokens, text_features = self._context
        features = [image_embed, *high_res_feats]
        try:
            conditioned = [
                adapter(base, patch_tokens, text_features)
                for adapter, base in zip(self.adapters, features)
            ]
            return conditioned[0], conditioned[1:]
        finally:
            self.clear_context()


def set_requires_grad(module: nn.Module, enabled: bool) -> None:
    for parameter in module.parameters():
        parameter.requires_grad = enabled


def freeze_all(module: nn.Module) -> None:
    set_requires_grad(module, False)


def autocast_context(device: torch.device, enabled: bool):
    if device.type == "cuda":
        return torch.amp.autocast(device_type="cuda", enabled=enabled)
    return torch.amp.autocast(device_type="cpu", enabled=False)


def ensure_efficientsam3_importable(root_value: str | None) -> Path:
    candidates: list[Path] = []
    if root_value not in (None, ""):
        root = resolve_project_path(root_value)
        if root is not None:
            candidates.append(root)
    candidates.extend(
        [
            PROJECT_ROOT / "external" / "efficientsam3",
            PROJECT_ROOT / "external" / "efficientsam3_src",
            Path("/tmp/efficientsam3_src"),
        ]
    )
    for root in candidates:
        package_root = root / "sam3"
        if (package_root / "sam3" / "model_builder.py").exists():
            if str(package_root) not in sys.path:
                sys.path.insert(0, str(package_root))
            importlib.invalidate_caches()
            return root
    try:
        import sam3  # noqa: F401
        return Path("site-packages")
    except ImportError as exc:
        raise ImportError(
            "Could not import EfficientSAM3. Set `paths.efficientsam3_root` to a local checkout "
            "of the upstream repository, or install it in the active environment."
        ) from exc


class EfficientSAM3Segmenter(nn.Module):
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__()
        self.config = config
        paths_cfg = config.get("paths", {})
        model_cfg = config.get("model", {})
        stage_name = str(config.get("train", {}).get("stage", "stage_a")).strip().lower()
        lora_cfg = model_cfg.get("lora", {})
        lora_enabled = bool(lora_cfg.get("enabled", False))

        ensure_efficientsam3_importable(str(paths_cfg.get("efficientsam3_root", "")))
        from sam3.model_builder import build_efficientsam3_image_model  # type: ignore

        checkpoint_path = model_cfg.get("checkpoint_path")
        checkpoint_path_resolved = None
        deferred_wrapper_state_dict: dict[str, torch.Tensor] | None = None
        if checkpoint_path not in (None, ""):
            checkpoint_path_resolved = str(resolve_project_path(str(checkpoint_path)))
            candidate_checkpoint = torch.load(checkpoint_path_resolved, map_location="cpu")
            if isinstance(candidate_checkpoint, dict) and "model_state_dict" in candidate_checkpoint:
                deferred_wrapper_state_dict = candidate_checkpoint["model_state_dict"]
                checkpoint_path_resolved = None

        self.model = build_efficientsam3_image_model(
            checkpoint_path=checkpoint_path_resolved,
            device="cpu",
            eval_mode=False,
            enable_inst_interactivity=True,
            enable_segmentation=bool(model_cfg.get("enable_segmentation", True)),
            backbone_type=str(model_cfg.get("backbone_type", "tinyvit")),
            model_name=str(model_cfg.get("model_name", "11m")),
            text_encoder_type=model_cfg.get("text_encoder_type"),
            text_encoder_context_length=int(model_cfg.get("text_encoder_context_length", 16)),
            text_encoder_pos_embed_table_size=model_cfg.get("text_encoder_pos_embed_table_size"),
            interpolate_pos_embed=bool(model_cfg.get("interpolate_pos_embed", False)),
        )
        clip_cfg = config.get("clip_guidance", {})
        clip_block_specs: list[tuple[str, int]] = []
        if bool(clip_cfg.get("enabled", False)) and str(
            clip_cfg.get("injection_mode", "fpn")
        ).strip().lower() == "block":
            block_patterns = [
                re.compile(pattern)
                for pattern in clip_cfg.get("block_target_patterns", [])
            ]
            for name, module in self.model.backbone.vision_backbone.named_modules():
                if not name.endswith(".mlp"):
                    continue
                if block_patterns and not any(pattern.search(name) for pattern in block_patterns):
                    continue
                fc2 = getattr(module, "fc2", None)
                channels = getattr(fc2, "out_features", None)
                if channels is None and hasattr(fc2, "base"):
                    channels = getattr(fc2.base, "out_features", None)
                if channels is not None:
                    clip_block_specs.append((name, int(channels)))
        self.clip_guidance: ClipSemanticGuidance | None = (
            ClipSemanticGuidance(clip_cfg, clip_block_specs)
            if bool(clip_cfg.get("enabled", False))
            else None
        )
        if self.clip_guidance is not None and self.clip_guidance.injection_mode == "block":
            self.clip_guidance.attach_block_hooks(self.model.backbone.vision_backbone)
        self.stage_name = stage_name
        self._patch_summary: dict[str, Any] = {}
        configured_before_load = False
        state_contains_lora = (
            deferred_wrapper_state_dict is not None
            and any(
                ".lora_a." in key or ".lora_b." in key or ".base." in key
                for key in deferred_wrapper_state_dict
            )
        )
        if lora_enabled and state_contains_lora:
            self._configure_trainable_modules()
            configured_before_load = True
        if deferred_wrapper_state_dict is not None:
            missing, unexpected = self.load_state_dict(deferred_wrapper_state_dict, strict=False)
            print(
                f"loaded {resolve_project_path(str(checkpoint_path))} via wrapper model_state_dict "
                f"and found missing keys: {len(missing)} and unexpected keys: {len(unexpected)}."
            )
            if missing:
                print(f"Sample missing: {missing[:5]}")
            if unexpected:
                print(f"Sample unexpected: {unexpected[:5]}")
        if not configured_before_load:
            self._configure_trainable_modules()

    def train(self, mode: bool = True):
        super().train(mode)
        clear_autocast_cache = getattr(torch, "clear_autocast_cache", None)
        if callable(clear_autocast_cache):
            clear_autocast_cache()
        self._clear_runtime_caches()
        if mode:
            self._apply_train_mode_overrides()
        return self

    def _clear_runtime_caches(self) -> None:
        for module in self.modules():
            cache = getattr(module, "cache", None)
            if isinstance(cache, dict):
                cache.clear()
            coord_cache = getattr(module, "coord_cache", None)
            if isinstance(coord_cache, dict):
                coord_cache.clear()
            if hasattr(module, "compilable_cord_cache"):
                module.compilable_cord_cache = None
            if hasattr(module, "compilable_stored_size"):
                module.compilable_stored_size = None

    def _configure_trainable_modules(self) -> None:
        freeze_all(self.model)
        predictor_model = self.model.inst_interactive_predictor.model
        model_cfg = self.config.get("model", {})
        set_requires_grad(
            predictor_model.sam_mask_decoder,
            bool(model_cfg.get("train_mask_decoder", True)),
        )
        mask_decoder_patterns = [
            re.compile(pattern)
            for pattern in model_cfg.get("mask_decoder_train_patterns", [])
        ]
        if mask_decoder_patterns and bool(model_cfg.get("train_mask_decoder", True)):
            for name, parameter in predictor_model.sam_mask_decoder.named_parameters():
                parameter.requires_grad = any(
                    pattern.search(name) for pattern in mask_decoder_patterns
                )
        set_requires_grad(
            predictor_model.sam_prompt_encoder,
            bool(model_cfg.get("train_prompt_encoder", True)),
        )

        lora_cfg = model_cfg.get("lora", {})
        lora_enabled = bool(lora_cfg.get("enabled", False))
        train_lora = bool(model_cfg.get("train_lora", True))
        if self.stage_name in {"stage_b", "stage_c"} and lora_enabled:
            include_patterns = list(lora_cfg.get("target_patterns", []))
            exclude_patterns = list(lora_cfg.get("exclude_patterns", []))
            patched = apply_lora_by_patterns(
                self.model.backbone.vision_backbone,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
                rank=int(lora_cfg.get("rank", 8)),
                alpha=float(lora_cfg.get("alpha", 16.0)),
                dropout=float(lora_cfg.get("dropout", 0.0)),
            )
            self._patch_summary["lora_modules"] = patched
            if not train_lora:
                for module in self.model.backbone.vision_backbone.modules():
                    if isinstance(module, LoRALinear):
                        set_requires_grad(module, False)
        else:
            self._patch_summary["lora_modules"] = []
        if self.clip_guidance is not None:
            self.clip_guidance.configure_trainable()

    def _apply_train_mode_overrides(self) -> None:
        model_cfg = self.config.get("model", {})
        predictor_model = self.model.inst_interactive_predictor.model
        if (
            not bool(model_cfg.get("train_mask_decoder", True))
            or bool(model_cfg.get("disable_trainable_dropout", False))
        ):
            predictor_model.sam_mask_decoder.eval()
        if not bool(model_cfg.get("train_prompt_encoder", True)):
            predictor_model.sam_prompt_encoder.eval()
        lora_cfg = model_cfg.get("lora", {})
        lora_enabled = bool(lora_cfg.get("enabled", False))
        vision_backbone = self.model.backbone.vision_backbone
        if self.stage_name in {"stage_b", "stage_c"} and lora_enabled:
            # TinyViT-11M has stochastic-depth blocks. Keep the frozen base
            # deterministic during LoRA training, while leaving LoRA dropout
            # and parameters in train mode.
            vision_backbone.eval()
            for module in vision_backbone.modules():
                if isinstance(module, LoRALinear) and any(
                    parameter.requires_grad for parameter in module.parameters()
                ):
                    module.train()
        elif not any(parameter.requires_grad for parameter in vision_backbone.parameters()):
            # Decoder-only stages also freeze the full vision backbone. Its
            # stochastic depth must stay off so train and eval use one model.
            vision_backbone.eval()
        if bool(model_cfg.get("freeze_backbone_norm_stats", False)):
            norm_types = (
                nn.BatchNorm1d,
                nn.BatchNorm2d,
                nn.BatchNorm3d,
                nn.SyncBatchNorm,
            )
            for module in self.model.backbone.vision_backbone.modules():
                if isinstance(module, norm_types):
                    module.eval()
        if self.clip_guidance is not None:
            self.clip_guidance.apply_train_mode(True)

    def dump_module_names(self) -> list[str]:
        return [name for name, _ in self.model.named_modules()]

    def trainable_parameter_summary(self) -> dict[str, Any]:
        trainable = sum(parameter.numel() for parameter in self.parameters() if parameter.requires_grad)
        total = sum(parameter.numel() for parameter in self.parameters())
        summary = {
            "trainable_parameters": trainable,
            "total_parameters": total,
            "trainable_ratio": (trainable / total) if total else 0.0,
            "lora_modules": self._patch_summary.get("lora_modules", []),
        }
        if self.clip_guidance is not None:
            summary["clip_guidance"] = self.clip_guidance.trainable_parameter_summary()
        return summary

    def _prepare_visual_features(self, images: torch.Tensor) -> tuple[torch.Tensor, list[torch.Tensor], dict[str, Any]]:
        block_injection = (
            self.clip_guidance is not None
            and self.clip_guidance.injection_mode == "block"
        )
        if block_injection:
            self.clip_guidance.prepare_context(images)
        normalized = (images - 0.5) / 0.5
        backbone_out = self.model.backbone.forward_image(normalized)
        sam2_backbone_out = backbone_out["sam2_backbone_out"]
        sam_mask_decoder = self.model.inst_interactive_predictor.model.sam_mask_decoder
        if "backbone_fpn" in sam2_backbone_out:
            sam2_backbone_out["backbone_fpn"][0] = sam_mask_decoder.conv_s0(sam2_backbone_out["backbone_fpn"][0])
            sam2_backbone_out["backbone_fpn"][1] = sam_mask_decoder.conv_s1(sam2_backbone_out["backbone_fpn"][1])
        (
            _,
            vision_feats,
            _,
            feat_sizes,
        ) = self.model.inst_interactive_predictor.model._prepare_backbone_features(sam2_backbone_out)
        vision_feats[-1] = vision_feats[-1] + self.model.inst_interactive_predictor.model.no_mem_embed
        feats = [
            feat.permute(1, 2, 0).view(images.shape[0], -1, *feat_size)
            for feat, feat_size in zip(vision_feats, feat_sizes)
        ]
        image_embed = feats[-1]
        high_res_feats = feats[:-1]
        if self.clip_guidance is not None:
            if block_injection:
                self.clip_guidance.clear_context()
            else:
                image_embed, high_res_feats = self.clip_guidance(
                    images,
                    image_embed,
                    high_res_feats,
                )
        return image_embed, high_res_feats, backbone_out

    def _build_prompt_tensors(self, prompts: list[PromptSpec], device: torch.device) -> tuple[torch.Tensor, torch.Tensor]:
        max_tokens = max(int(prompt.point_labels.shape[0]) if prompt.point_labels is not None else 0 for prompt in prompts)
        if max_tokens <= 0:
            raise ValueError("At least one prompt token is required per batch item.")
        coords = torch.zeros((len(prompts), max_tokens, 2), dtype=torch.float32, device=device)
        labels = torch.full((len(prompts), max_tokens), fill_value=-1, dtype=torch.int64, device=device)
        for batch_index, prompt in enumerate(prompts):
            if prompt.point_coords is None or prompt.point_labels is None:
                continue
            count = int(prompt.point_labels.shape[0])
            coords[batch_index, :count] = torch.from_numpy(prompt.point_coords).to(device=device, dtype=torch.float32)
            labels[batch_index, :count] = torch.from_numpy(prompt.point_labels).to(device=device, dtype=torch.int64)
        return coords, labels

    def forward_with_prompts(
        self,
        images: torch.Tensor,
        prompts: list[PromptSpec],
    ) -> dict[str, torch.Tensor]:
        image_embed, high_res_feats, _ = self._prepare_visual_features(images)
        predictor_model = self.model.inst_interactive_predictor.model
        coords, labels = self._build_prompt_tensors(prompts, images.device)
        sparse_embeddings, dense_embeddings = predictor_model.sam_prompt_encoder(
            points=(coords, labels),
            boxes=None,
            masks=None,
        )
        low_res_masks, iou_predictions, _, _ = predictor_model.sam_mask_decoder(
            image_embeddings=image_embed,
            image_pe=predictor_model.sam_prompt_encoder.get_dense_pe(),
            sparse_prompt_embeddings=sparse_embeddings,
            dense_prompt_embeddings=dense_embeddings,
            multimask_output=False,
            repeat_image=False,
            high_res_features=high_res_feats,
        )
        return {
            "low_res_masks": low_res_masks,
            "iou_predictions": iou_predictions,
        }


def dice_loss_from_logits(logits: torch.Tensor, targets: torch.Tensor, eps: float = 1e-6) -> torch.Tensor:
    probs = torch.sigmoid(logits)
    intersection = (probs * targets).sum(dim=(1, 2, 3))
    denom = probs.sum(dim=(1, 2, 3)) + targets.sum(dim=(1, 2, 3))
    dice = (2 * intersection + eps) / (denom + eps)
    return 1.0 - dice.mean()


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


def consistency_loss_from_logits(primary_logits: torch.Tensor, secondary_logits: torch.Tensor) -> torch.Tensor:
    return F.mse_loss(torch.sigmoid(primary_logits), torch.sigmoid(secondary_logits))


def compute_loss_bundle(
    logits: torch.Tensor,
    masks: torch.Tensor,
    *,
    bce_loss: nn.Module,
    bce_weight: float,
    dice_weight: float,
    secondary_logits: torch.Tensor | None = None,
    lambda_consistency: float = 0.0,
) -> tuple[torch.Tensor, dict[str, float]]:
    seg_loss = bce_weight * bce_loss(logits, masks) + dice_weight * dice_loss_from_logits(logits, masks)
    total = seg_loss
    loss_parts = {
        "seg_loss": float(seg_loss.detach().item()),
        "consistency_loss": 0.0,
        "total_loss": float(seg_loss.detach().item()),
    }
    if secondary_logits is not None and lambda_consistency > 0:
        c_loss = consistency_loss_from_logits(logits, secondary_logits)
        total = total + lambda_consistency * c_loss
        loss_parts["consistency_loss"] = float(c_loss.detach().item())
        loss_parts["total_loss"] = float(total.detach().item())
    return total, loss_parts


def save_checkpoint(
    path: Path,
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    epoch: int,
    best_val_dice: float,
    config: dict[str, Any],
) -> None:
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


@torch.no_grad()
def run_prompt_mode_evaluation(
    model: EfficientSAM3Segmenter,
    records: list[PromptableSampleRecord],
    *,
    resolution: int,
    batch_size: int,
    num_workers: int,
    device: torch.device,
    threshold: float,
    experiment_dir: Path,
    split_name: str,
    prompt_mode: str,
    prompt_builder: PromptBuilder,
    prompt_seed: int,
    representative_examples_per_bucket: int,
) -> dict[str, Any]:
    dataset = EfficientSAM3TrainDataset(
        records,
        resolution=resolution,
        prompt_builder=prompt_builder,
        prompt_seed=prompt_seed,
        train=False,
        consistency_enabled=False,
    )
    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
        collate_fn=collate_promptable,
    )
    inference_root = ensure_dir(experiment_dir / "inference" / split_name / prompt_mode)
    pred_dir = ensure_dir(inference_root / "predictions_png")
    score_root = ensure_dir(experiment_dir / "evaluation" / split_name / prompt_mode / "sms_binary")
    source_dir = ensure_dir(score_root / "source_images")
    overlay_dir = ensure_dir(score_root / "overlays")

    rows: list[dict[str, Any]] = []
    model.eval()
    for batch in loader:
        images = batch["image"].to(device=device, dtype=torch.float32, non_blocking=True)
        prompts = []
        for index, case_id in enumerate(batch["case_id"]):
            rng = random.Random(prompt_seed + abs(hash((split_name, prompt_mode, case_id))) % 1000003)
            mask_np = (batch["mask"][index].squeeze(0).numpy() * 255.0).astype(np.uint8)
            transformed_meta = ResizeMeta(
                original_width=resolution,
                original_height=resolution,
                resized_width=resolution,
                resized_height=resolution,
                pad_left=0,
                pad_top=0,
                resolution=resolution,
                scale_x=1.0,
                scale_y=1.0,
            )
            prompts.append(
                prompt_builder.build(
                    mask_np,
                    transformed_meta,
                    mode=prompt_mode,
                    rng=rng,
                    jitter=False,
                )
            )
        outputs = model.forward_with_prompts(images, prompts)
        probs = torch.sigmoid(outputs["low_res_masks"]).cpu()
        preds = (probs >= threshold).float()
        for index, case_id in enumerate(batch["case_id"]):
            width = int(batch["original_width"][index])
            height = int(batch["original_height"][index])
            pred_resized = F.interpolate(preds[index : index + 1], size=(height, width), mode="nearest")
            pred_mask = (pred_resized.squeeze().numpy() > 0).astype(np.uint8) * 255
            gt_mask = (np.array(load_mask(Path(batch["mask_path"][index])), dtype=np.uint8) > 0).astype(np.uint8) * 255
            metrics = dice_iou_from_arrays(pred_mask, gt_mask)
            pred_path = pred_dir / f"{case_id}.png"
            Image.fromarray(pred_mask, mode="L").save(pred_path)

            overlay_source = Path(batch["overlay_image"][index])
            overlay_path = overlay_dir / f"{case_id}.jpg"
            with Image.open(overlay_source) as source_image:
                source_image.convert("RGB").save(source_dir / f"{case_id}.jpg", quality=95)
            draw_overlay(source_dir / f"{case_id}.jpg", pred_mask, gt_mask, overlay_path)
            rows.append(
                {
                    "case_id": case_id,
                    "source_image": f"{case_id}.jpg",
                    "prediction_mask": pred_path.name,
                    "gt_mask": Path(batch["mask_path"][index]).name,
                    "prompt_mode": prompt_mode,
                    "dice": float(metrics["dice"]),
                    "iou": float(metrics["iou"]),
                    "tp": int(metrics["tp"]),
                    "fp": int(metrics["fp"]),
                    "fn": int(metrics["fn"]),
                    "tn": int(metrics["tn"]),
                    "pred_foreground": int((pred_mask > 0).sum()),
                    "gt_foreground": int((gt_mask > 0).sum()),
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
                "prompt_mode",
                "dice",
                "iou",
                "tp",
                "fp",
                "fn",
                "tn",
                "pred_foreground",
                "gt_foreground",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    mean_dice = float(np.mean([float(row["dice"]) for row in rows])) if rows else 0.0
    mean_iou = float(np.mean([float(row["iou"]) for row in rows])) if rows else 0.0
    zero_dice_count = sum(1 for row in rows if float(row["dice"]) == 0.0)
    zero_dice_ratio = zero_dice_count / max(len(rows), 1)
    summary = {
        "split_name": split_name,
        "prompt_mode": prompt_mode,
        "case_count": len(rows),
        "mean_dice": mean_dice,
        "mean_iou": mean_iou,
        "zero_dice_count": zero_dice_count,
        "zero_dice_ratio": zero_dice_ratio,
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
        representative_examples_per_bucket,
    )
    overlay_paths: list[Path] = []
    example_dir = ensure_dir(experiment_dir / "evaluation" / "example_visualizations" / split_name / prompt_mode)
    for idx, row in enumerate(selected, start=1):
        overlay_path = example_dir / f"{idx:02d}_{row.bucket.lower()}_{row.case_id}.jpg"
        pred = np.array(Image.open(pred_dir / f"{row.case_id}.png"))
        gt_path = next(Path(record.mask_path) for record in records if record.case_id == row.case_id)
        gt = np.array(Image.open(gt_path))
        draw_overlay(source_dir / f"{row.case_id}.jpg", pred, gt, overlay_path)
        overlay_paths.append(overlay_path)
    contact_sheet_path = experiment_dir / "evaluation" / "example_visualizations" / f"{split_name}_{prompt_mode}_examples.jpg"
    build_contact_sheet(f"{split_name}:{prompt_mode}", selected, overlay_paths, contact_sheet_path)
    return {
        "name": f"{split_name}:{prompt_mode}",
        "split_name": split_name,
        "prompt_mode": prompt_mode,
        "case_count": len(rows),
        "mean_dice": mean_dice,
        "mean_iou": mean_iou,
        "zero_dice_count": zero_dice_count,
        "zero_dice_ratio": zero_dice_ratio,
        "summary_json": str(summary_path),
        "metrics_csv": str(metrics_csv),
        "example_contact_sheet": str(contact_sheet_path),
    }


def build_prompt_matrix(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, float]]]:
    matrix: dict[str, dict[str, dict[str, float]]] = {}
    for row in rows:
        matrix.setdefault(str(row["split_name"]), {})[str(row["prompt_mode"])] = {
            "mean_dice": float(row["mean_dice"]),
            "mean_iou": float(row["mean_iou"]),
            "case_count": float(row["case_count"]),
        }
    return matrix


def build_promptable_summary_markdown(
    experiment_name: str,
    config_path: Path,
    best_checkpoint: Path,
    evaluation_rows: list[dict[str, Any]],
) -> str:
    lines = [
        f"# `{experiment_name}`",
        "",
        "EfficientSAM3 prompt-conditioned ROI segmentation run.",
        "",
        f"- config: `{config_path}`",
        f"- best checkpoint: `{best_checkpoint}`",
        "",
        "## Prompt Robustness Matrix",
        "",
        "| Split | Prompt | Cases | Mean Dice | Mean IoU | Zero-Dice Cases | Zero-Dice Ratio |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in evaluation_rows:
        lines.append(
            f"| {row['split_name']} | {row['prompt_mode']} | {row['case_count']} | "
            f"{float(row['mean_dice']):.4f} | {float(row['mean_iou']):.4f} | "
            f"{row['zero_dice_count']} | {float(row['zero_dice_ratio']):.4f} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"

