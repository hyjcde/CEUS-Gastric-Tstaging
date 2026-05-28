#!/usr/bin/env python
"""
统一预处理协和内部数据集和外部测试集中的胃癌直接手术图像。

输出内容包括：
1. 原图 JPG
2. 去 UI 裁剪图
3. ROI 紧框裁剪图
4. 原图 / 去 UI / ROI 三套 overlay
5. 原图 / 去 UI / ROI 三套 LabelMe 标注
6. 原图 / 去 UI / ROI 三套二值 ROI mask
7. manifest.csv 和 unmatched_files.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import nibabel as nib
import numpy as np
import pydicom


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "processed_datasets"

DEFAULT_DATASET_CONFIGS = {
    "internal": {
        "source": ROOT / "协和内部数据集" / "直接手术",
        "output": OUTPUT_ROOT / "internal_direct_surgery",
    },
    "external": {
        "source": ROOT / "胃癌直接手术外部测试集" / "直接手术图片",
        "output": OUTPUT_ROOT / "external_direct_surgery",
    },
}

EXTERNAL_CENTER_NAMES = {
    "三明市第二医院",
    "福建省肿瘤医院",
    "莆田学院附属医院",
    "莆田市第一医院",
    "北京友谊医院",
    "佛山市第一人民医院",
    "福建省德化县医院",
    "中核五〇四医院",
    "福建省立医院",
}

EXTERNAL_CENTER_ALIASES = {
    "中核五O四医院": "中核五〇四医院",
}


def normalize_external_center_name(name: str) -> str:
    return EXTERNAL_CENTER_ALIASES.get(name, name)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".bmp", ".png", ".dcm"}
MASK_EXTENSIONS = {".nii", ".nii.gz", ".gz"}

# 主要用于 crop_ui。思路是先按数据集与分辨率套用稳定的大框，
# 目标是稳定去掉 UI，而不是追求最紧主体框。
RESOLUTION_UI_PRESETS = {
    "internal_2018": {
        (960, 720): (0.08, 0.12, 0.91, 0.91),
        (1280, 1024): (0.08, 0.10, 0.92, 0.90),
    },
    "internal_2019": {
        (960, 720): (0.08, 0.12, 0.91, 0.91),
        (768, 576): (0.08, 0.12, 0.91, 0.91),
    },
    "internal_2020_2023": {
        (1280, 960): (0.12, 0.10, 0.90, 0.86),
        (1552, 970): (0.12, 0.10, 0.90, 0.86),
        (1292, 970): (0.12, 0.10, 0.90, 0.86),
        (1440, 1080): (0.12, 0.10, 0.90, 0.86),
        (960, 720): (0.10, 0.10, 0.90, 0.88),
    },
    "internal_2024": {
        (1280, 960): (0.11, 0.11, 0.91, 0.87),
        (1552, 873): (0.10, 0.08, 0.92, 0.88),
        (1920, 1080): (0.10, 0.08, 0.92, 0.88),
        (1442, 802): (0.10, 0.08, 0.92, 0.88),
    },
    "internal_2025": {
        (1280, 960): (0.10, 0.11, 0.91, 0.89),
        (1286, 1028): (0.10, 0.11, 0.91, 0.89),
    },
    "external_tumor_hospital": {
        (720, 576): (0.07, 0.06, 0.93, 0.92),
        (768, 576): (0.07, 0.06, 0.93, 0.92),
        (1024, 768): (0.07, 0.06, 0.93, 0.92),
        (1452, 1038): (0.05, 0.05, 0.97, 0.95),
        (1460, 1080): (0.05, 0.05, 0.97, 0.95),
        (1552, 970): (0.05, 0.05, 0.97, 0.93),
        (1552, 874): (0.05, 0.04, 0.97, 0.93),
        (1656, 992): (0.05, 0.05, 0.97, 0.94),
    },
    "external_putian2": {
        (1280, 960): (0.09, 0.11, 0.91, 0.86),
    },
    "external_putian1": {
        (720, 480): (0.11, 0.06, 0.86, 0.92),
        (768, 576): (0.14, 0.12, 0.85, 0.88),
        (960, 720): (0.10, 0.08, 0.90, 0.93),
        (1292, 970): (0.09, 0.08, 0.89, 0.92),
        (1200, 920): (0.09, 0.08, 0.89, 0.92),
        (1920, 1200): (0.10, 0.08, 0.88, 0.92),
        (1340, 1150): (0.09, 0.08, 0.89, 0.92),
        (680, 412): (0.10, 0.08, 0.90, 0.92),
    },
    "external_sanming": {
        (960, 720): (0.15, 0.13, 0.92, 0.90),
        (1280, 960): (0.15, 0.13, 0.92, 0.90),
    },
}


@dataclass
class FileEntry:
    path: Path
    relative_dir: Path
    base_name: str
    normalized_name: str
    extension: str


@dataclass
class PairEntry:
    image: FileEntry
    mask: FileEntry
    sample_id: str


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def file_extension(path: Path) -> str:
    suffix = "".join(path.suffixes).lower()
    if suffix in MASK_EXTENSIONS:
        return suffix
    if path.suffix.lower() == ".gz":
        return ".gz"
    return path.suffix.lower()


def is_image_file(path: Path) -> bool:
    return file_extension(path) in IMAGE_EXTENSIONS


def is_mask_file(path: Path) -> bool:
    return file_extension(path) in MASK_EXTENSIONS


def strip_known_extension(filename: str) -> str:
    lower = filename.lower()
    for ext in (".nii.gz", ".nii", ".dcm", ".jpg", ".jpeg", ".bmp", ".png", ".gz"):
        if lower.endswith(ext):
            return filename[: -len(ext)]
    return Path(filename).stem


def normalize_base_name(filename: str) -> str:
    base = strip_known_extension(filename).strip()
    # 类似 "1-100-1(15)" 末尾是厚度信息，需要去掉。
    base = re.sub(r"(?<!\s)\(\d+\)$", "", base)
    base = re.sub(r"\s+", " ", base).strip()
    return base


def compact_name(name: str) -> str:
    return re.sub(r"\s+", "", name)


def last_two_tokens(name: str) -> Optional[str]:
    tokens = compact_name(name).split("-")
    if len(tokens) >= 2:
        return "-".join(tokens[-2:])
    return None


def trailing_number(name: str) -> Optional[int]:
    match = re.search(r"(\d+)$", compact_name(name))
    if match:
        return int(match.group(1))
    return None


def group_prefix(name: str) -> Optional[str]:
    compact = compact_name(name)
    parts = compact.split("-")
    if len(parts) >= 2 and trailing_number(name) is not None:
        return "-".join(parts[:-1])
    return None


def candidate_keys(name: str) -> List[str]:
    keys = [name, compact_name(name)]
    tail = last_two_tokens(name)
    if tail:
        keys.append(tail)
    seen = set()
    ordered = []
    for key in keys:
        if key and key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def safe_slug(value: str) -> str:
    value = value.replace("/", "__").replace("\\", "__")
    value = re.sub(r"\s+", "_", value)
    # Keep CJK unified + 〇 (U+3007), common in hospital names like 五〇四.
    value = re.sub(r"[^0-9A-Za-z_\-().\u4e00-\u9fff\u3007]+", "_", value)
    return value.strip("._") or "sample"


def infer_crop_profile(dataset_key: str, entry: FileEntry) -> Optional[str]:
    if dataset_key == "internal":
        year = infer_internal_year(entry)
        if year == "2018":
            return "internal_2018"
        if year == "2019":
            return "internal_2019"
        if year == "2020_2023":
            return "internal_2020_2023"
        if year == "2024":
            return "internal_2024"
        if year == "2025":
            return "internal_2025"
        return None

    center = infer_external_center(entry)
    return external_crop_profile_for_center(center)


def external_crop_profile_for_center(center: str) -> Optional[str]:
    center = normalize_external_center_name(center)
    if center == "福建省肿瘤医院":
        return "external_tumor_hospital"
    if center == "三明市第二医院":
        return "external_sanming"
    if center == "莆田学院附属医院":
        return "external_putian1"
    if center == "莆田市第一医院":
        return "external_putian2"
    if center in {
        "北京友谊医院",
        "佛山市第一人民医院",
        "福建省德化县医院",
        "中核五〇四医院",
        "福建省立医院",
    }:
        return "external_tumor_hospital"
    return None


def relative_dir_parts(entry: FileEntry) -> Tuple[str, ...]:
    return tuple(entry.relative_dir.parts)


def infer_internal_year(entry: FileEntry) -> str:
    path_parts = relative_dir_parts(entry)
    joined = "/".join(path_parts)
    if "2018直接手术" in joined:
        return "2018"
    if "2019年直接手术" in joined:
        return "2019"
    if "20-23直接手术" in joined:
        return "2020_2023"
    if "2024年直接手术" in joined:
        return "2024"
    if "2025直接手术" in joined:
        return "2025"
    return "unknown_year"


def infer_external_center(entry: FileEntry, source_root: Optional[Path] = None) -> str:
    path_parts = relative_dir_parts(entry)
    for part in path_parts:
        normalized = normalize_external_center_name(part)
        if normalized in EXTERNAL_CENTER_NAMES:
            return normalized
    if source_root is not None:
        normalized = normalize_external_center_name(source_root.name)
        if normalized in EXTERNAL_CENTER_NAMES:
            return normalized
    return "未识别中心"


def collect_entries(source_root: Path) -> Tuple[List[FileEntry], List[FileEntry]]:
    return collect_entries_from_roots([source_root])


def collect_entries_from_roots(
    source_roots: Sequence[Path],
    exclude_stems: Optional[set[str]] = None,
) -> Tuple[List[FileEntry], List[FileEntry]]:
    image_entries: List[FileEntry] = []
    mask_entries: List[FileEntry] = []
    exclude_stems = exclude_stems or set()

    for source_root in source_roots:
        for path in sorted(source_root.rglob("*")):
            if not path.is_file():
                continue
            if path.name.startswith("._") or path.name == ".DS_Store":
                continue
            if path.name.startswith("~$"):
                continue

            ext = file_extension(path)
            if ext not in IMAGE_EXTENSIONS and ext not in MASK_EXTENSIONS:
                continue

            entry = FileEntry(
                path=path,
                relative_dir=path.parent.relative_to(source_root),
                base_name=strip_known_extension(path.name),
                normalized_name=normalize_base_name(path.name),
                extension=ext,
            )
            if is_image_file(path):
                if entry.normalized_name in exclude_stems or compact_name(entry.normalized_name) in exclude_stems:
                    continue
                image_entries.append(entry)
            elif is_mask_file(path):
                mask_entries.append(entry)

    return image_entries, mask_entries


def build_mask_index(mask_entries: Sequence[FileEntry]) -> Dict[str, List[FileEntry]]:
    index: Dict[str, List[FileEntry]] = defaultdict(list)
    for entry in mask_entries:
        for key in candidate_keys(entry.normalized_name):
            index[key].append(entry)
    return index


def match_score(image_entry: FileEntry, mask_entry: FileEntry) -> int:
    image_name = image_entry.normalized_name
    mask_name = mask_entry.normalized_name

    if image_name == mask_name:
        return 100
    if compact_name(image_name) == compact_name(mask_name):
        return 95

    image_tail = last_two_tokens(image_name)
    mask_tail = last_two_tokens(mask_name)
    if image_tail and mask_tail and image_tail == mask_tail:
        return 80

    if image_entry.relative_dir == mask_entry.relative_dir:
        return 5
    return 0


def pair_images_and_masks(
    image_entries: Sequence[FileEntry],
    mask_entries: Sequence[FileEntry],
) -> Tuple[List[PairEntry], List[FileEntry], List[FileEntry]]:
    mask_index = build_mask_index(mask_entries)
    used_masks: set[Path] = set()
    pairs: List[PairEntry] = []
    unmatched_images: List[FileEntry] = []

    for image_entry in image_entries:
        candidates: List[Tuple[int, FileEntry]] = []
        seen_mask_paths: set[Path] = set()
        for key in candidate_keys(image_entry.normalized_name):
            for mask_entry in mask_index.get(key, []):
                if mask_entry.path in used_masks or mask_entry.path in seen_mask_paths:
                    continue
                score = match_score(image_entry, mask_entry)
                if score > 0:
                    candidates.append((score, mask_entry))
                    seen_mask_paths.add(mask_entry.path)

        if not candidates:
            unmatched_images.append(image_entry)
            continue

        candidates.sort(
            key=lambda item: (
                -item[0],
                len(str(item[1].relative_dir)),
                str(item[1].path),
            )
        )
        mask_entry = candidates[0][1]
        used_masks.add(mask_entry.path)

        rel_dir_slug = safe_slug(str(image_entry.relative_dir))
        sample_id = safe_slug(f"{rel_dir_slug}__{image_entry.base_name}")
        pairs.append(PairEntry(image=image_entry, mask=mask_entry, sample_id=sample_id))

    remaining_images = list(unmatched_images)
    unmatched_images = []
    remaining_masks = [entry for entry in mask_entries if entry.path not in used_masks]

    # 第二轮回退匹配：
    # 某些外部数据是同一病人按顺序一一对应，但图片和标注的编号整体错开 1。
    image_groups: Dict[Tuple[str, str], List[FileEntry]] = defaultdict(list)
    mask_groups: Dict[Tuple[str, str], List[FileEntry]] = defaultdict(list)

    for entry in remaining_images:
        prefix = group_prefix(entry.normalized_name)
        if prefix:
            image_groups[(str(entry.relative_dir), prefix)].append(entry)

    for entry in remaining_masks:
        prefix = group_prefix(entry.normalized_name)
        if prefix:
            mask_groups[(str(entry.relative_dir), prefix)].append(entry)

    fallback_matched_images: set[Path] = set()
    fallback_matched_masks: set[Path] = set()

    for group_key, grouped_images in image_groups.items():
        grouped_masks = mask_groups.get(group_key, [])
        if not grouped_masks or len(grouped_images) != len(grouped_masks):
            continue

        image_numbers = [trailing_number(entry.normalized_name) for entry in grouped_images]
        mask_numbers = [trailing_number(entry.normalized_name) for entry in grouped_masks]
        if any(number is None for number in image_numbers + mask_numbers):
            continue

        sorted_images = sorted(grouped_images, key=lambda entry: trailing_number(entry.normalized_name))
        sorted_masks = sorted(grouped_masks, key=lambda entry: trailing_number(entry.normalized_name))

        for image_entry, mask_entry in zip(sorted_images, sorted_masks):
            fallback_matched_images.add(image_entry.path)
            fallback_matched_masks.add(mask_entry.path)
            rel_dir_slug = safe_slug(str(image_entry.relative_dir))
            sample_id = safe_slug(f"{rel_dir_slug}__{image_entry.base_name}")
            pairs.append(PairEntry(image=image_entry, mask=mask_entry, sample_id=sample_id))

    unmatched_images = [
        entry for entry in remaining_images if entry.path not in fallback_matched_images
    ]
    unmatched_masks = [
        entry for entry in remaining_masks if entry.path not in fallback_matched_masks
    ]
    return pairs, unmatched_images, unmatched_masks


def load_image(image_path: Path) -> np.ndarray:
    ext = file_extension(image_path)
    if ext == ".dcm":
        ds = pydicom.dcmread(str(image_path))
        pixel_array = ds.pixel_array
        if pixel_array.ndim == 2:
            gray = normalize_grayscale(pixel_array)
        else:
            if pixel_array.dtype != np.uint8:
                pixel_array = np.clip(pixel_array, 0, 255).astype(np.uint8)
            # 某些外院 DICOM 存的是伪 RGB：绿色通道接近常数，R/B 才是真正结构信息。
            channel_std = pixel_array.std(axis=(0, 1))
            channel_mean = pixel_array.mean(axis=(0, 1))
            if (
                pixel_array.shape[2] == 3
                and channel_mean[1] > channel_mean[0] * 2
                and channel_mean[1] > channel_mean[2] * 2
                and channel_std[1] < max(channel_std[0], channel_std[2]) * 0.35
            ):
                gray = np.maximum(pixel_array[:, :, 0], pixel_array[:, :, 2])
            else:
                gray = cv2.cvtColor(pixel_array, cv2.COLOR_RGB2GRAY)
        gray = enhance_grayscale_contrast(gray)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Unable to read image: {image_path}")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = enhance_grayscale_contrast(gray)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)


def normalize_grayscale(array: np.ndarray) -> np.ndarray:
    if array.dtype == np.uint8:
        return array
    arr_min = array.min()
    arr_max = array.max()
    if arr_max > arr_min:
        return ((array - arr_min) / (arr_max - arr_min) * 255).astype(np.uint8)
    return np.zeros_like(array, dtype=np.uint8)


def enhance_grayscale_contrast(gray: np.ndarray) -> np.ndarray:
    p_low = float(np.percentile(gray, 1))
    p_high = float(np.percentile(gray, 99))
    if p_high <= p_low + 1:
        stretched = gray.copy()
    else:
        stretched = np.clip((gray.astype(np.float32) - p_low) * 255.0 / (p_high - p_low), 0, 255).astype(np.uint8)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(stretched)


def load_mask(mask_path: Path, image_shape: Tuple[int, int]) -> np.ndarray:
    try:
        mask = nib.load(str(mask_path)).get_fdata()
    except nib.filebasedimages.ImageFileError:
        if mask_path.suffix.lower() != ".gz":
            raise

        # 某些文件内容其实是 nii.gz，但文件名只保留了 .gz。
        with tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as tmp:
            temp_path = Path(tmp.name)
        try:
            shutil.copy2(mask_path, temp_path)
            mask = nib.load(str(temp_path)).get_fdata()
        finally:
            if temp_path.exists():
                temp_path.unlink()

    mask = np.squeeze(mask)

    if mask.ndim != 2:
        raise ValueError(f"Mask is not 2D after squeeze: {mask_path} -> {mask.shape}")

    height, width = image_shape
    if mask.shape != (height, width):
        if mask.T.shape == (height, width):
            mask = mask.T
        else:
            raise ValueError(
                f"Shape mismatch: image {(height, width)} vs mask {mask.shape} for {mask_path}"
            )

    return (mask > 0).astype(np.uint8)


def clamp_rect(rect: Tuple[int, int, int, int], width: int, height: int) -> Tuple[int, int, int, int]:
    x1, y1, x2, y2 = rect
    x1 = max(0, min(int(x1), width - 1))
    y1 = max(0, min(int(y1), height - 1))
    x2 = max(x1 + 1, min(int(x2), width))
    y2 = max(y1 + 1, min(int(y2), height))
    return x1, y1, x2, y2


def rect_from_ratios(
    width: int,
    height: int,
    ratios: Tuple[float, float, float, float],
) -> Tuple[int, int, int, int]:
    x1 = int(round(width * ratios[0]))
    y1 = int(round(height * ratios[1]))
    x2 = int(round(width * ratios[2]))
    y2 = int(round(height * ratios[3]))
    return clamp_rect((x1, y1, x2, y2), width, height)


def expand_rect(
    rect: Tuple[int, int, int, int],
    width: int,
    height: int,
    margin_x: int,
    margin_y: int,
) -> Tuple[int, int, int, int]:
    x1, y1, x2, y2 = rect
    return clamp_rect((x1 - margin_x, y1 - margin_y, x2 + margin_x, y2 + margin_y), width, height)


def union_rect(
    rect_a: Tuple[int, int, int, int],
    rect_b: Tuple[int, int, int, int],
    width: int,
    height: int,
) -> Tuple[int, int, int, int]:
    x1 = min(rect_a[0], rect_b[0])
    y1 = min(rect_a[1], rect_b[1])
    x2 = max(rect_a[2], rect_b[2])
    y2 = max(rect_a[3], rect_b[3])
    return clamp_rect((x1, y1, x2, y2), width, height)


def rect_from_component_mask(mask: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    if count <= 1:
        return None
    best_index = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h, _ = stats[best_index]
    return int(x), int(y), int(x + w), int(y + h)


def rect_from_mean_threshold(
    gray: np.ndarray,
    threshold_x: float,
    threshold_y: float,
) -> Optional[Tuple[int, int, int, int]]:
    row_mean = gray.mean(axis=1)
    col_mean = gray.mean(axis=0)
    xs = np.where(col_mean > threshold_x)[0]
    ys = np.where(row_mean > threshold_y)[0]
    if len(xs) == 0 or len(ys) == 0:
        return None
    return int(xs[0]), int(ys[0]), int(xs[-1] + 1), int(ys[-1] + 1)


def trim_dark_edges(
    gray: np.ndarray,
    row_threshold: float,
    col_threshold: float,
    trim_top: bool = True,
    trim_bottom: bool = True,
    trim_left: bool = True,
    trim_right: bool = True,
) -> Optional[Tuple[int, int, int, int]]:
    row_mean = gray.mean(axis=1)
    col_mean = gray.mean(axis=0)
    height, width = gray.shape

    top = 0
    bottom = height
    left = 0
    right = width

    if trim_top:
        while top < bottom - 1 and row_mean[top] <= row_threshold:
            top += 1
    if trim_bottom:
        while bottom > top + 1 and row_mean[bottom - 1] <= row_threshold:
            bottom -= 1
    if trim_left:
        while left < right - 1 and col_mean[left] <= col_threshold:
            left += 1
    if trim_right:
        while right > left + 1 and col_mean[right - 1] <= col_threshold:
            right -= 1

    if right - left < max(40, int(width * 0.2)) or bottom - top < max(40, int(height * 0.2)):
        return None
    return left, top, right, bottom


def rect_from_bright_component(
    gray: np.ndarray,
    threshold: float,
    open_kernel: int = 5,
    close_kernel: int = 25,
) -> Optional[Tuple[int, int, int, int]]:
    _, thresh = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, np.ones((open_kernel, open_kernel), np.uint8))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, np.ones((close_kernel, close_kernel), np.uint8))
    return rect_from_component_mask(thresh)


def compute_auto_ui_crop_rect(
    image_rgb: np.ndarray,
    profile_key: Optional[str] = None,
    center_name: Optional[str] = None,
    mask: Optional[np.ndarray] = None,
) -> Tuple[int, int, int, int]:
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    height, width = gray.shape
    border = max(8, min(height, width) // 20)
    border_pixels = np.concatenate(
        [
            gray[:border, :].ravel(),
            gray[-border:, :].ravel(),
            gray[:, :border].ravel(),
            gray[:, -border:].ravel(),
        ]
    )
    default_threshold = float(np.percentile(border_pixels, 95) + 5)
    roi_rect = compute_roi_crop_rect(mask, margin_ratio=0.35) if mask is not None and np.any(mask > 0) else None

    preset = None
    if profile_key is not None:
        preset = RESOLUTION_UI_PRESETS.get(profile_key, {}).get((width, height))
    if preset is not None:
        rect = rect_from_ratios(width, height, preset)
        if roi_rect is not None:
            rect = union_rect(rect, roi_rect, width, height)
        return rect

    if center_name == "福建省肿瘤医院":
        trim_threshold = max(default_threshold, float(np.mean(border_pixels) + 1.0))
        rect = rect_from_mean_threshold(gray, trim_threshold, trim_threshold)
        if rect is None:
            rect = rect_from_bright_component(gray, trim_threshold)
        if rect is not None:
            rect = expand_rect(rect, width, height, max(18, int(width * 0.04)), max(18, int(height * 0.04)))
            if roi_rect is not None:
                rect = union_rect(rect, roi_rect, width, height)
            return rect

    if center_name == "莆田学院附属医院":
        component_threshold = max(default_threshold, float(np.mean(border_pixels) + 6.0))
        rect = rect_from_bright_component(gray, component_threshold, open_kernel=5, close_kernel=31)
        if rect is not None:
            rect = expand_rect(rect, width, height, max(20, int(width * 0.10)), max(20, int(height * 0.08)))
            if roi_rect is not None:
                rect = union_rect(rect, roi_rect, width, height)
            return rect

    if center_name == "莆田市第一医院":
        roi_fallback_rect = None
        if roi_rect is not None:
            roi_fallback_rect = expand_rect(
                roi_rect,
                width,
                height,
                max(180, int(width * 0.28)),
                max(140, int(height * 0.24)),
            )
        rect = trim_dark_edges(
            gray,
            row_threshold=8.0,
            col_threshold=8.0,
            trim_top=False,
            trim_bottom=True,
            trim_left=True,
            trim_right=True,
        )
        if rect is None:
            rect = rect_from_mean_threshold(gray, threshold_x=15.0, threshold_y=12.0)
        if rect is not None:
            area_ratio = ((rect[2] - rect[0]) * (rect[3] - rect[1])) / float(width * height)
            if area_ratio >= 0.93 and roi_fallback_rect is not None:
                rect = roi_fallback_rect
            rect = expand_rect(rect, width, height, max(20, int(width * 0.03)), max(12, int(height * 0.02)))
            if roi_rect is not None:
                rect = union_rect(rect, roi_rect, width, height)
            return rect
        if roi_fallback_rect is not None:
            return roi_fallback_rect

    rect = rect_from_bright_component(gray, default_threshold)
    if rect is None:
        return (0, 0, width, height)

    x1, y1, x2, y2 = rect
    area_ratio = ((x2 - x1) * (y2 - y1)) / float(width * height)
    if area_ratio >= 0.96:
        return (0, 0, width, height)

    rect = expand_rect(
        rect,
        width,
        height,
        max(20, int(round(width * 0.18)), int(round((x2 - x1) * 0.25))),
        max(20, int(round(height * 0.14)), int(round((y2 - y1) * 0.25))),
    )
    if roi_rect is not None:
        rect = union_rect(rect, roi_rect, width, height)
    return rect


def compute_roi_crop_rect(mask: np.ndarray, margin_ratio: float = 0.1) -> Tuple[int, int, int, int]:
    ys, xs = np.where(mask > 0)
    if len(xs) == 0 or len(ys) == 0:
        raise ValueError("Mask is empty, cannot compute ROI crop.")

    x1 = int(xs.min())
    x2 = int(xs.max()) + 1
    y1 = int(ys.min())
    y2 = int(ys.max()) + 1

    width = x2 - x1
    height = y2 - y1
    margin_x = max(12, int(round(width * margin_ratio)))
    margin_y = max(12, int(round(height * margin_ratio)))

    img_h, img_w = mask.shape
    x1 = max(0, x1 - margin_x)
    y1 = max(0, y1 - margin_y)
    x2 = min(img_w, x2 + margin_x)
    y2 = min(img_h, y2 + margin_y)
    return x1, y1, x2, y2


def crop_array(array: np.ndarray, rect: Tuple[int, int, int, int]) -> np.ndarray:
    x1, y1, x2, y2 = rect
    return array[y1:y2, x1:x2]


def create_overlay(image_rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    image_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
    overlay = image_bgr.copy()
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(overlay, contours, -1, (0, 255, 0), 2)
    return overlay


def mask_to_shapes(mask: np.ndarray) -> List[dict]:
    shapes: List[dict] = []
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for contour in contours:
        if cv2.contourArea(contour) < 10:
            continue
        epsilon = 0.001 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        points = approx.squeeze().tolist()
        if not isinstance(points, list) or len(points) < 3:
            continue
        if points and not isinstance(points[0], list):
            continue

        shapes.append(
            {
                "label": "lesion",
                "points": points,
                "group_id": None,
                "shape_type": "polygon",
                "flags": {},
            }
        )
    return shapes


def build_labelme_json(image_name: str, image_rgb: np.ndarray, mask: np.ndarray) -> dict:
    height, width = image_rgb.shape[:2]
    return {
        "version": "4.5.6",
        "flags": {},
        "shapes": mask_to_shapes(mask),
        "imagePath": f"../images/{image_name}",
        # 保持为 None，能明显减小 JSON 体积，后续训练也更方便。
        "imageData": None,
        "imageHeight": height,
        "imageWidth": width,
    }


def save_variant(
    variant_name: str,
    image_rgb: np.ndarray,
    mask: np.ndarray,
    sample_id: str,
    output_root: Path,
) -> None:
    images_dir = output_root / variant_name / "images"
    overlays_dir = output_root / variant_name / "overlays"
    masks_dir = output_root / variant_name / "roi_masks"
    annotations_dir = output_root / variant_name / "annotations"

    for path in (images_dir, overlays_dir, masks_dir, annotations_dir):
        ensure_dir(path)

    image_name = f"{sample_id}.jpg"
    overlay_name = f"{sample_id}_overlay.jpg"
    mask_name = f"{sample_id}.png"
    annotation_name = f"{sample_id}.json"

    cv2.imwrite(str(images_dir / image_name), cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(overlays_dir / overlay_name), create_overlay(image_rgb, mask))
    cv2.imwrite(str(masks_dir / mask_name), (mask > 0).astype(np.uint8) * 255)

    with open(annotations_dir / annotation_name, "w", encoding="utf-8") as f:
        json.dump(build_labelme_json(image_name, image_rgb, mask), f, indent=2, ensure_ascii=False)


def save_manifest_rows(rows: Iterable[dict], path: Path) -> None:
    rows = list(rows)
    if not rows:
        return
    ensure_dir(path.parent)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def clear_output_root(output_root: Path) -> None:
    if not output_root.exists():
        return

    for child in output_root.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def build_dataset_configs(
    internal_source: Optional[Path] = None,
    external_source: Optional[Path] = None,
    output_root: Optional[Path] = None,
) -> Dict[str, Dict[str, Path]]:
    base_output = output_root or OUTPUT_ROOT
    return {
        "internal": {
            "source": internal_source or DEFAULT_DATASET_CONFIGS["internal"]["source"],
            "output": base_output / "internal_direct_surgery",
        },
        "external": {
            "source": external_source or DEFAULT_DATASET_CONFIGS["external"]["source"],
            "output": base_output / "external_direct_surgery",
        },
    }


def destination_roots_for_pair(
    dataset_key: str,
    pair: PairEntry,
    dataset_configs: Dict[str, Dict[str, Path]],
    forced_center: Optional[str] = None,
    direct_output_root: Optional[Path] = None,
) -> List[Tuple[str, Path]]:
    if dataset_key == "internal":
        year = infer_internal_year(pair.image)
        if year in {"2018", "2019", "2020_2023", "2024"}:
            return [("training_2018_2024", dataset_configs["internal"]["output"] / "training_2018_2024" / year)]
        if year == "2025":
            return [("prospective_2025", dataset_configs["internal"]["output"] / "prospective_2025" / year)]
        else:
            return []

    center = forced_center or infer_external_center(pair.image)
    if direct_output_root is not None:
        return [(center, direct_output_root)]
    return [(center, dataset_configs["external"]["output"] / center)]


@dataclass
class ProcessHospitalResult:
    manifest_rows: List[dict]
    error_rows: List[dict]
    unmatched_rows: List[dict]
    matched_pairs: int


def process_external_hospital(
    center_name: str,
    source_root: Path,
    output_root: Path,
    limit: Optional[int] = None,
    clear_output: bool = True,
    extra_source_roots: Optional[Sequence[Path]] = None,
    exclude_stems: Optional[set[str]] = None,
) -> ProcessHospitalResult:
    center_name = normalize_external_center_name(center_name)
    print(f"[INFO] Processing external hospital: {center_name}")
    print(f"[INFO] Source: {source_root}")
    if extra_source_roots:
        print(f"[INFO] Extra sources: {', '.join(str(p) for p in extra_source_roots)}")
    print(f"[INFO] Output: {output_root}")

    source_roots = [source_root, *(extra_source_roots or [])]
    image_entries, mask_entries = collect_entries_from_roots(source_roots, exclude_stems=exclude_stems)
    print(f"[INFO] Found {len(image_entries)} image candidates and {len(mask_entries)} mask candidates.")

    pairs, unmatched_images, unmatched_masks = pair_images_and_masks(image_entries, mask_entries)
    if limit is not None:
        pairs = pairs[:limit]

    print(f"[INFO] Matched {len(pairs)} image-mask pairs.")
    print(f"[INFO] Unmatched images: {len(unmatched_images)}")
    print(f"[INFO] Unmatched masks: {len(unmatched_masks)}")

    if clear_output:
        clear_output_root(output_root)
    ensure_dir(output_root)

    manifest_rows: List[dict] = []
    error_rows: List[dict] = []
    unmatched_rows: List[dict] = []

    for entry in unmatched_images:
        unmatched_rows.append(
            {
                "type": "image",
                "path": str(entry.path),
                "normalized_name": entry.normalized_name,
            }
        )
    for entry in unmatched_masks:
        unmatched_rows.append(
            {
                "type": "mask",
                "path": str(entry.path),
                "normalized_name": entry.normalized_name,
            }
        )

    profile_key = external_crop_profile_for_center(center_name)

    for index, pair in enumerate(pairs, start=1):
        try:
            image_rgb = load_image(pair.image.path)
            height, width = image_rgb.shape[:2]
            mask = load_mask(pair.mask.path, (height, width))

            original_rect = (0, 0, width, height)
            ui_rect = compute_auto_ui_crop_rect(
                image_rgb,
                profile_key=profile_key,
                center_name=center_name,
                mask=mask,
            )
            roi_rect = compute_roi_crop_rect(mask)

            save_variant("original", image_rgb, mask, pair.sample_id, output_root)
            save_variant(
                "crop_ui",
                crop_array(image_rgb, ui_rect),
                crop_array(mask, ui_rect),
                pair.sample_id,
                output_root,
            )
            save_variant(
                "crop_roi",
                crop_array(image_rgb, roi_rect),
                crop_array(mask, roi_rect),
                pair.sample_id,
                output_root,
            )

            manifest_rows.append(
                {
                    "sample_id": pair.sample_id,
                    "image_source": str(pair.image.path),
                    "mask_source": str(pair.mask.path),
                    "group_targets": center_name,
                    "image_width": width,
                    "image_height": height,
                    "original_rect": ",".join(map(str, original_rect)),
                    "ui_crop_rect": ",".join(map(str, ui_rect)),
                    "roi_crop_rect": ",".join(map(str, roi_rect)),
                }
            )

            if index % 100 == 0:
                print(f"[INFO] Processed {index}/{len(pairs)} pairs...")

        except Exception as exc:  # noqa: BLE001
            error_rows.append(
                {
                    "sample_id": pair.sample_id,
                    "image_source": str(pair.image.path),
                    "mask_source": str(pair.mask.path),
                    "error": str(exc),
                }
            )

    save_manifest_rows(manifest_rows, output_root / "manifest.csv")
    save_manifest_rows(unmatched_rows, output_root / "unmatched_files.csv")
    save_manifest_rows(error_rows, output_root / "errors.csv")

    print(f"[INFO] Done: {center_name}")
    print(f"[INFO] Successful samples: {len(manifest_rows)}")
    print(f"[INFO] Errors: {len(error_rows)}")

    return ProcessHospitalResult(
        manifest_rows=manifest_rows,
        error_rows=error_rows,
        unmatched_rows=unmatched_rows,
        matched_pairs=len(pairs),
    )


def process_dataset(
    dataset_key: str,
    source_root: Path,
    output_root: Path,
    dataset_configs: Dict[str, Dict[str, Path]],
    limit: Optional[int] = None,
) -> None:
    print(f"[INFO] Processing dataset: {dataset_key}")
    print(f"[INFO] Source: {source_root}")
    print(f"[INFO] Output: {output_root}")

    image_entries, mask_entries = collect_entries(source_root)
    print(f"[INFO] Found {len(image_entries)} image candidates and {len(mask_entries)} mask candidates.")

    pairs, unmatched_images, unmatched_masks = pair_images_and_masks(image_entries, mask_entries)
    if limit is not None:
        pairs = pairs[:limit]

    print(f"[INFO] Matched {len(pairs)} image-mask pairs.")
    print(f"[INFO] Unmatched images: {len(unmatched_images)}")
    print(f"[INFO] Unmatched masks: {len(unmatched_masks)}")

    clear_output_root(output_root)
    ensure_dir(output_root)

    manifest_rows: List[dict] = []
    error_rows: List[dict] = []
    unmatched_rows: List[dict] = []

    for entry in unmatched_images:
        unmatched_rows.append(
            {
                "type": "image",
                "path": str(entry.path),
                "normalized_name": entry.normalized_name,
            }
        )
    for entry in unmatched_masks:
        unmatched_rows.append(
            {
                "type": "mask",
                "path": str(entry.path),
                "normalized_name": entry.normalized_name,
            }
        )

    for index, pair in enumerate(pairs, start=1):
        try:
            image_rgb = load_image(pair.image.path)
            height, width = image_rgb.shape[:2]
            mask = load_mask(pair.mask.path, (height, width))
            center_name = (
                normalize_external_center_name(infer_external_center(pair.image, source_root=source_root))
                if dataset_key == "external"
                else None
            )
            profile_key = (
                external_crop_profile_for_center(center_name)
                if dataset_key == "external" and center_name
                else infer_crop_profile(dataset_key, pair.image)
            )

            original_rect = (0, 0, width, height)
            ui_rect = compute_auto_ui_crop_rect(
                image_rgb,
                profile_key=profile_key,
                center_name=center_name,
                mask=mask,
            )
            roi_rect = compute_roi_crop_rect(mask)

            destinations = destination_roots_for_pair(dataset_key, pair, dataset_configs)
            if not destinations:
                continue
            for _, target_root in destinations:
                save_variant("original", image_rgb, mask, pair.sample_id, target_root)
                save_variant(
                    "crop_ui",
                    crop_array(image_rgb, ui_rect),
                    crop_array(mask, ui_rect),
                    pair.sample_id,
                    target_root,
                )
                save_variant(
                    "crop_roi",
                    crop_array(image_rgb, roi_rect),
                    crop_array(mask, roi_rect),
                    pair.sample_id,
                    target_root,
                )

            manifest_rows.append(
                {
                    "sample_id": pair.sample_id,
                    "image_source": str(pair.image.path),
                    "mask_source": str(pair.mask.path),
                    "group_targets": ";".join(group_name for group_name, _ in destinations),
                    "image_width": width,
                    "image_height": height,
                    "original_rect": ",".join(map(str, original_rect)),
                    "ui_crop_rect": ",".join(map(str, ui_rect)),
                    "roi_crop_rect": ",".join(map(str, roi_rect)),
                }
            )

            if index % 100 == 0:
                print(f"[INFO] Processed {index}/{len(pairs)} pairs...")

        except Exception as exc:  # noqa: BLE001
            error_rows.append(
                {
                    "sample_id": pair.sample_id,
                    "image_source": str(pair.image.path),
                    "mask_source": str(pair.mask.path),
                    "error": str(exc),
                }
            )

    save_manifest_rows(manifest_rows, output_root / "manifest.csv")
    save_manifest_rows(unmatched_rows, output_root / "unmatched_files.csv")
    save_manifest_rows(error_rows, output_root / "errors.csv")

    print(f"[INFO] Done: {dataset_key}")
    print(f"[INFO] Successful samples: {len(manifest_rows)}")
    print(f"[INFO] Errors: {len(error_rows)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preprocess direct-surgery gastric ultrasound datasets.")
    parser.add_argument(
        "--dataset",
        choices=["internal", "external", "all"],
        default="all",
        help="Choose which dataset to process.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Only process the first N matched pairs, useful for debugging.",
    )
    parser.add_argument(
        "--internal-source",
        type=Path,
        help="Optional override for the internal dataset source root.",
    )
    parser.add_argument(
        "--external-source",
        type=Path,
        help="Optional override for the external dataset source root.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        help="Optional override for the processed_datasets root.",
    )
    parser.add_argument(
        "--output-layout",
        choices=["processed_datasets", "dataset_external"],
        default="processed_datasets",
        help="Write external output under processed_datasets/external_direct_surgery or dataset/external/{hospital}.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_root = args.output_root
    if args.output_layout == "dataset_external" and output_root is None:
        output_root = ROOT / "dataset" / "external"
    dataset_configs = build_dataset_configs(
        internal_source=args.internal_source,
        external_source=args.external_source,
        output_root=output_root,
    )
    if args.output_layout == "dataset_external":
        dataset_configs["external"]["output"] = output_root or (ROOT / "dataset" / "external")

    dataset_keys = ["internal", "external"] if args.dataset == "all" else [args.dataset]

    for dataset_key in dataset_keys:
        config = dataset_configs[dataset_key]
        if dataset_key == "external" and args.output_layout == "dataset_external":
            source_root = config["source"]
            if not source_root.exists():
                raise FileNotFoundError(f"External source root not found: {source_root}")
            for hospital_dir in sorted(source_root.iterdir()):
                if not hospital_dir.is_dir():
                    continue
                center_name = normalize_external_center_name(hospital_dir.name)
                if center_name not in EXTERNAL_CENTER_NAMES:
                    print(f"[WARN] Skipping unrecognized hospital folder: {hospital_dir.name}")
                    continue
                process_external_hospital(
                    center_name=center_name,
                    source_root=hospital_dir,
                    output_root=dataset_configs["external"]["output"] / center_name,
                    limit=args.limit,
                )
            continue

        process_dataset(
            dataset_key=dataset_key,
            source_root=config["source"],
            output_root=config["output"],
            dataset_configs=dataset_configs,
            limit=args.limit,
        )


if __name__ == "__main__":
    main()
