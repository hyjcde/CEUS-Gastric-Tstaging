"""
共用数据集类

支持:
- 纯图像分类 (ImageDataset)
- 图像 + 临床特征 (MultimodalDataset)
- Global + ROI 双输入 (DualInputDataset)

所有 Dataset 从 CSV 读取, CSV 必须包含 image_path + label 列.
"""

import cv2
import pandas as pd
import numpy as np
import re
import torch
from PIL import Image
from pathlib import Path
from torch.utils.data import Dataset, Sampler
import torchvision.transforms as T
import torchvision.transforms.functional as F
from torchvision.transforms import InterpolationMode
from collections import defaultdict
import random
import sys

from .transforms import HistogramEqualize, SpeckleReduction, get_normalize_stats

TOOLKIT_ROOT = Path(__file__).resolve().parents[1] / "scripts" / "t2_t3_toolkit"
if str(TOOLKIT_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLKIT_ROOT))

from common import extract_frame_index, extract_patient_and_frame, normalize_patient_id  # type: ignore


DATASET_IMAGE_DIRS = {
    "internal_xh_2018": Path("/data/research/gastric/GastricTstaging/dataset/internal/training_2018_2024/2018/crop_ui/images"),
    "internal_xh_2019": Path("/data/research/gastric/GastricTstaging/dataset/internal/training_2018_2024/2019/crop_ui/images"),
    "internal_xh_2020_2023": Path("/data/research/gastric/GastricTstaging/dataset/internal/training_2018_2024/2020_2023/crop_ui/images"),
    "internal_xh_2024": Path("/data/research/gastric/GastricTstaging/dataset/internal/training_2018_2024/2024/crop_ui/images"),
    "internal_xh_2025": Path("/data/research/gastric/GastricTstaging/dataset/internal/prospective_2025/2025/crop_ui/images"),
    "external_sanming": Path("/data/research/gastric/GastricTstaging/dataset/external/三明市第二医院/crop_ui/images"),
    "external_tumor": Path("/data/research/gastric/GastricTstaging/dataset/external/福建省肿瘤医院/crop_ui/images"),
    "external_putian1": Path("/data/research/gastric/GastricTstaging/dataset/external/莆田学院附属医院/crop_ui/images"),
    "external_putian2": Path("/data/research/gastric/GastricTstaging/dataset/external/莆田市第一医院/crop_ui/images"),
    "external_beijing_friendship": Path("/data/research/gastric/GastricTstaging/dataset/external/北京友谊医院/crop_ui/images"),
    "external_foshan_first": Path("/data/research/gastric/GastricTstaging/dataset/external/佛山市第一人民医院/crop_ui/images"),
    "external_cnnc_504": Path("/data/research/gastric/GastricTstaging/dataset/external/中核五〇四医院/crop_ui/images"),
    "external_dehua": Path("/data/research/gastric/GastricTstaging/dataset/external/福建省德化县医院/crop_ui/images"),
    "external_fujian_provincial": Path("/data/research/gastric/GastricTstaging/dataset/external/福建省立医院/crop_ui/images"),
}

SOURCE_TO_DATASET_CANDIDATES = {
    "int/2018": ("internal_xh_2018",),
    "int/2019": ("internal_xh_2019",),
    "int/2020_2023": ("internal_xh_2020_2023",),
    "int/2024": ("internal_xh_2024",),
    "int/prospective": ("internal_xh_2025",),
    "ext/putian": ("external_putian1", "external_putian2"),
    "ext/putian_2024": ("external_putian2", "external_putian1"),
    "ext/putian_2024_new": ("external_putian2", "external_putian1"),
    "ext/putian_2025_07_09": ("external_putian2", "external_putian1"),
    "ext/multicenter": ("external_tumor", "external_sanming"),
    "ext/zhongliu": ("external_tumor",),
    "ext/sanming": ("external_sanming",),
    "ext/putian2": ("external_putian2", "external_putian1"),
    "ext/北京友谊医院": ("external_beijing_friendship",),
    "ext/佛山市第一人民医院": ("external_foshan_first",),
    "ext/中核五〇四医院": ("external_cnnc_504",),
    "ext/福建省德化县医院": ("external_dehua",),
    "ext/福建省立医院": ("external_fujian_provincial",),
    "ext/newzip/北京友谊医院": ("external_beijing_friendship",),
    "ext/newzip/佛山市第一人民医院": ("external_foshan_first",),
    "ext/newzip/中核五〇四医院": ("external_cnnc_504",),
    "ext/newzip/福建省德化县医院": ("external_dehua",),
}

_IMAGE_INVENTORY_CACHE = None


def stable_image_key(stem: str, patient_id_hint=None) -> str:
    parsed_patient_id, _ = extract_patient_and_frame(stem)
    patient_id = normalize_patient_id(patient_id_hint) or parsed_patient_id or "unknown"
    frame_index = extract_frame_index(stem) or 0
    return f"{patient_id}::{int(frame_index):03d}"


def get_image_inventory():
    global _IMAGE_INVENTORY_CACHE
    if _IMAGE_INVENTORY_CACHE is not None:
        return _IMAGE_INVENTORY_CACHE

    index = {}
    valid_suffixes = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
    for dataset_key, image_dir in DATASET_IMAGE_DIRS.items():
        if not image_dir.exists():
            continue
        for image_path in image_dir.iterdir():
            if not image_path.is_file() or image_path.suffix.lower() not in valid_suffixes:
                continue
            index[(dataset_key, stable_image_key(image_path.stem))] = image_path.resolve()
    _IMAGE_INVENTORY_CACHE = index
    return _IMAGE_INVENTORY_CACHE


def _first_existing_path(row, columns):
    for col in columns:
        value = row.get(col, '')
        if pd.isna(value):
            continue
        value = str(value).strip()
        if not value:
            continue
        path = Path(value)
        if path.exists():
            return str(path)
    return None


def _putian_patient_aliases(*values):
    aliases: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None or pd.isna(value):
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        aliases.append(text)
        match = re.fullmatch(r"pty(\d+)", text, re.I)
        if match:
            alias = f"pt{match.group(1)}"
            if alias not in seen:
                seen.add(alias)
                aliases.append(alias)
    return aliases


def _putian_stem_aliases(stem: str):
    aliases = [stem]
    match = re.fullmatch(r"pty(\d+)-(\d+)", stem, re.I)
    if match:
        aliases.append(f"pt{match.group(1)}-{match.group(2)}")
    return aliases


def _lookup_inventory_match(inventory, dataset_keys, lookup_keys):
    for dataset_key in dataset_keys:
        for image_key in lookup_keys:
            match = inventory.get((dataset_key, image_key))
            if match is not None:
                return str(match)
    return None


def _lookup_putian_crop_by_stem(dataset_keys, stem_aliases):
    for dataset_key in dataset_keys:
        image_dir = DATASET_IMAGE_DIRS.get(dataset_key)
        if image_dir is None or not image_dir.exists():
            continue
        for stem_alias in stem_aliases:
            hits = sorted(image_dir.glob(f"*__直接手术__{stem_alias}.jpg"))
            if hits:
                return str(hits[0])
            hits = sorted(image_dir.glob(f"*{stem_alias}.jpg"))
            if hits:
                return str(hits[0])
    return None


def remap_legacy_image_path(row, value):
    text = str(value).strip()
    if not text:
        return None

    path = Path(text)
    if path.is_absolute() and path.exists():
        return str(path)
    if path.exists():
        return str(path.resolve())

    inventory = get_image_inventory()
    stem = path.stem
    source = str(row.get("source", "")).strip()
    candidates = list(SOURCE_TO_DATASET_CANDIDATES.get(source, ()))
    if source == "ext/multicenter" and stem.startswith("pt"):
        candidates = ["external_putian1", "external_putian2", *candidates]

    lookup_keys = []
    seen_keys: set[str] = set()
    stem_aliases = _putian_stem_aliases(stem) if source.startswith("ext/putian") else [stem]
    patient_aliases = _putian_patient_aliases(row.get("patient_id"), stem.split("-", 1)[0])
    for stem_alias in stem_aliases:
        for patient_alias in patient_aliases:
            image_key = stable_image_key(stem_alias, patient_alias)
            if image_key not in seen_keys:
                seen_keys.add(image_key)
                lookup_keys.append(image_key)

    match = _lookup_inventory_match(inventory, candidates, lookup_keys)
    if match is not None:
        return match
    match = _lookup_inventory_match(inventory, DATASET_IMAGE_DIRS, lookup_keys)
    if match is not None:
        return match
    if source.startswith("ext/putian"):
        match = _lookup_putian_crop_by_stem(candidates, stem_aliases)
        if match is not None:
            return match
        match = _lookup_putian_crop_by_stem(DATASET_IMAGE_DIRS, stem_aliases)
        if match is not None:
            return match
    return None


def resolve_global_image_path(row):
    """Resolve crop_ui/global image path for a manifest row (Dataset + GradCAM)."""
    priority_cols = ['global_image_path', 'full_image_path', 'original_image_path']
    direct = _first_existing_path(row, priority_cols)
    if direct is not None:
        return direct
    for col in priority_cols:
        remapped = remap_legacy_image_path(row, row.get(col, ''))
        if remapped is not None:
            return remapped
    image_path = _first_existing_path(row, ['image_path'])
    if image_path is not None:
        return image_path
    remapped = remap_legacy_image_path(row, row.get('image_path', ''))
    if remapped is not None:
        return remapped
    return None


# ============================================================
# Patient-Level Sampler: 每个epoch对每个患者随机采样K帧
# ============================================================
class PatientSampler(Sampler):
    """每个 epoch 对每个患者随机采样最多 K 张图，按类别加权。

    解决的问题:
    1. 多帧患者权重过大 → 每人最多K帧/epoch
    2. 类别不均衡 → 按患者数做类别加权上采样
    3. 每epoch看不同帧 → 动态随机选择

    修复历史:
    v1 (bug): oversampled = np.random.choice(pids, size=max_n, replace=True)
              同一患者被多次选中 → 同一帧在epoch中可能出现 >>K 次（实测最多24次）
    v2 (fix): 每类先扩充患者列表（整批重复），每个患者在epoch内恰好出现一次，
              取 min(K, pool_size) 帧。保证每帧每epoch最多出现一次。

    Args:
        dataset: 必须有 df 属性，df 包含 label 和 patient_id 列
        max_frames_per_patient: 每个患者每个 epoch 最多采样帧数
        class_balanced: 是否按类别加权（少数类上采样到多数类数量）
    """
    def __init__(self, dataset, max_frames_per_patient=3, class_balanced=True,
                 class_boost: dict | None = None):
        self.dataset = dataset
        self.K = max_frames_per_patient
        self.class_balanced = class_balanced
        self.class_boost = {int(k): float(v) for k, v in (class_boost or {}).items()}

        df = dataset.df
        pid_col = 'patient_id_unique' if 'patient_id_unique' in df.columns else 'patient_id'

        # 建立 患者→行索引 映射
        self.patient_indices = defaultdict(list)
        self.patient_labels = {}
        for idx, row in df.iterrows():
            pid = row[pid_col]
            self.patient_indices[pid].append(idx)
            self.patient_labels[pid] = int(row['label'])

        self.patients = list(self.patient_indices.keys())

        # 按类别分组
        self.class_patients = defaultdict(list)
        for pid in self.patients:
            self.class_patients[self.patient_labels[pid]].append(pid)

        # epoch 长度：class_balanced 时，每类扩充到多数类数量（可对指定类再放大）
        if self.class_balanced:
            base_max = max(len(pids) for pids in self.class_patients.values())
            self._class_targets = {
                cls: int(base_max * self.class_boost.get(cls, 1.0))
                for cls in self.class_patients
            }
            self._len = sum(self._class_targets.values()) * self.K
        else:
            self._class_targets = {}
            self._len = sum(min(self.K, len(self.patient_indices[pid]))
                           for pid in self.patients)

    def __iter__(self):
        indices = []

        if self.class_balanced:
            for cls_label, pids in self.class_patients.items():
                max_n = self._class_targets.get(
                    cls_label,
                    max(len(x) for x in self.class_patients.values()),
                )
                # ── 修复：先构造扩充后的患者列表（整批重复+随机补充），
                #         再打乱，保证每个患者在 epoch 内恰好出现一次
                n_pids = len(pids)
                repeats = max_n // n_pids          # 整批重复次数
                remainder = max_n % n_pids         # 不足一批的补充
                expanded = pids * repeats
                if remainder:
                    expanded += list(np.random.choice(pids, size=remainder, replace=False))
                np.random.shuffle(expanded)        # 打乱顺序
                for pid in expanded:
                    pool = self.patient_indices[pid]
                    k = min(self.K, len(pool))
                    sampled = np.random.choice(pool, size=k, replace=False).tolist()
                    indices.extend(sampled)
        else:
            for pid in self.patients:
                pool = self.patient_indices[pid]
                k = min(self.K, len(pool))
                sampled = np.random.choice(pool, size=k, replace=False).tolist()
                indices.extend(sampled)

        np.random.shuffle(indices)
        return iter(indices)

    def __len__(self):
        return self._len


class ImageDataset(Dataset):
    """纯图像分类数据集
    
    CSV 格式: image_path, label, [patient_id, source, ...]
    """
    def __init__(self, csv_path, transform=None, image_size=224):
        self.df = pd.read_csv(csv_path)
        self.transform = transform
        self.image_size = image_size
        self._fallback_transform = T.Compose([
            T.Resize((image_size, image_size)),
            T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        try:
            img = Image.open(row['image_path']).convert('RGB')
        except Exception:
            img = Image.new('RGB', (self.image_size, self.image_size), (0, 0, 0))
        
        transform = self.transform or self._fallback_transform
        img = transform(img)
        
        return {
            'image': img,
            'label': int(row['label']),
        }


class MultimodalDataset(Dataset):
    """图像 + 临床特征数据集
    
    CSV 格式: image_path, label, age, sex, [lauren, differentiation, tumor_size, ...]
    clinical_cols 指定要用的临床特征列名。
    """
    def __init__(self, csv_path, transform=None, image_size=224,
                 clinical_cols=('age', 'sex'),
                 age_mean=None, age_std=None):
        self.df = pd.read_csv(csv_path)
        self.transform = transform
        self.image_size = image_size
        self.clinical_cols = list(clinical_cols)
        
        # Normalize age (if present)
        if 'age' in self.clinical_cols:
            self.age_mean = age_mean if age_mean is not None else self.df['age'].mean()
            self.age_std = age_std if age_std is not None else self.df['age'].std()
            if self.age_std == 0:
                self.age_std = 1.0
        
        self._fallback_transform = T.Compose([
            T.Resize((image_size, image_size)),
            T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])
    
    def __len__(self):
        return len(self.df)
    
    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        try:
            img = Image.open(row['image_path']).convert('RGB')
        except Exception:
            img = Image.new('RGB', (self.image_size, self.image_size), (0, 0, 0))
        
        transform = self.transform or self._fallback_transform
        img = transform(img)
        
        # Build clinical feature vector
        features = []
        for col in self.clinical_cols:
            val = row.get(col, 0)
            if col == 'age':
                val = (val - self.age_mean) / self.age_std
            features.append(float(val) if not pd.isna(val) else 0.0)
        
        import torch
        return {
            'image': img,
            'label': int(row['label']),
            'clinical': torch.tensor(features, dtype=torch.float32),
        }


class ClinicalOnlyDataset(Dataset):
    """仅使用临床特征的数据集。"""

    def __init__(self, csv_path, clinical_cols=('age', 'sex'),
                 age_mean=None, age_std=None):
        self.df = pd.read_csv(csv_path)
        self.clinical_cols = list(clinical_cols)

        if 'age' in self.clinical_cols:
            self.age_mean = age_mean if age_mean is not None else self.df['age'].mean()
            self.age_std = age_std if age_std is not None else self.df['age'].std()
            if self.age_std == 0 or pd.isna(self.age_std):
                self.age_std = 1.0

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        features = []
        for col in self.clinical_cols:
            val = row.get(col, 0)
            if col == 'age':
                val = (val - self.age_mean) / self.age_std
            features.append(float(val) if not pd.isna(val) else 0.0)

        import torch
        return {
            'label': int(row['label']),
            'clinical': torch.tensor(features, dtype=torch.float32),
        }


class USPathologyClinicalDataset(Dataset):
    """超声病灶 + 病理 tiles + 临床特征联合数据集。

    CSV 关键列:
        us_roi_path / roi_path / image_path
        pathology_tile_paths   以 ';' 连接的 tile 路径
        label
        [clinical cols...]
    """

    def __init__(self, csv_path, us_transform=None, pathology_transform=None,
                 us_image_size=224, pathology_image_size=224,
                 pathology_k_tiles=12, clinical_cols=('age', 'sex'),
                 age_mean=None, age_std=None, random_tile_sampling=False):
        self.df = pd.read_csv(csv_path)
        self.us_transform = us_transform
        self.pathology_transform = pathology_transform
        self.us_image_size = us_image_size
        self.pathology_image_size = pathology_image_size
        self.pathology_k_tiles = pathology_k_tiles
        self.random_tile_sampling = random_tile_sampling
        self.clinical_cols = list(clinical_cols)

        if 'age' in self.clinical_cols:
            self.age_mean = age_mean if age_mean is not None else self.df['age'].mean()
            self.age_std = age_std if age_std is not None else self.df['age'].std()
            if self.age_std == 0 or pd.isna(self.age_std):
                self.age_std = 1.0

        self._fallback_us_transform = T.Compose([
            T.Resize((us_image_size, us_image_size)),
            T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])
        self._fallback_pathology_transform = T.Compose([
            T.Resize((pathology_image_size, pathology_image_size)),
            T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])

    def __len__(self):
        return len(self.df)

    def _choose_us_path(self, row):
        for col in ('us_roi_path', 'roi_path', 'image_path'):
            val = row.get(col, '')
            if pd.notna(val) and str(val).strip():
                return str(val)
        return ''

    def _load_rgb(self, path_str, image_size, transform, fallback_transform):
        try:
            img = Image.open(path_str).convert('RGB')
        except Exception:
            img = Image.new('RGB', (image_size, image_size), (0, 0, 0))
        tf = transform or fallback_transform
        return tf(img)

    def _parse_tile_paths(self, row):
        raw = row.get('pathology_tile_paths', '')
        if pd.isna(raw) or not str(raw).strip():
            return []
        tiles = [p for p in str(raw).split(';') if p.strip()]
        if not tiles:
            return []
        if len(tiles) <= self.pathology_k_tiles:
            return tiles
        if self.random_tile_sampling:
            idx = np.random.choice(len(tiles), size=self.pathology_k_tiles, replace=False)
            idx = sorted(idx.tolist())
            return [tiles[i] for i in idx]
        return tiles[: self.pathology_k_tiles]

    def __getitem__(self, idx):
        row = self.df.iloc[idx]

        us_tensor = self._load_rgb(
            self._choose_us_path(row),
            self.us_image_size,
            self.us_transform,
            self._fallback_us_transform,
        )

        tile_paths = self._parse_tile_paths(row)
        pathology_tiles = []
        for tile_path in tile_paths:
            pathology_tiles.append(
                self._load_rgb(
                    tile_path,
                    self.pathology_image_size,
                    self.pathology_transform,
                    self._fallback_pathology_transform,
                )
            )

        valid_k = len(pathology_tiles)
        while len(pathology_tiles) < self.pathology_k_tiles:
            pathology_tiles.append(torch.zeros(3, self.pathology_image_size, self.pathology_image_size))
        pathology_stack = torch.stack(pathology_tiles, dim=0)
        pathology_mask = torch.zeros(self.pathology_k_tiles, dtype=torch.bool)
        pathology_mask[:valid_k] = True

        features = []
        for col in self.clinical_cols:
            val = row.get(col, 0)
            if col == 'age':
                val = (val - self.age_mean) / self.age_std
            features.append(float(val) if not pd.isna(val) else 0.0)

        return {
            'us_image': us_tensor,
            'pathology_images': pathology_stack,
            'pathology_mask': pathology_mask,
            'label': int(row['label']),
            'clinical': torch.tensor(features, dtype=torch.float32),
        }


class DualInputDataset(Dataset):
    """Global + ROI 双输入数据集

    CSV 格式: image_path, roi_path, label, [clinical cols...]

    Args:
        roi_fallback: 当 roi_path 缺失时的处理策略
            'center_crop' (默认): 对全图做中心裁剪 (裁剪比例由 roi_crop_ratio 控制)
                                  保证 Local 分支看到不同于 Global 的内容 (更小视野、更聚焦)
            'full_image':         直接用全图 (旧行为, 已废弃 — 导致两分支输入完全相同)
        roi_crop_ratio: center_crop 模式下保留的中心区域比例 (默认 0.6, 即60%)
                        超声图像病灶通常集中在画面中央偏下区域
    """
    def __init__(self, csv_path, global_transform=None, local_transform=None,
                 global_size=512, local_size=224,
                 clinical_cols=None, age_mean=None, age_std=None,
                 use_overlay_as_global=False,
                 roi_fallback='center_crop', roi_crop_ratio=0.6,
                 use_mask_channel=False, mask_dir=None,
                 mask_augment_align=False, aug_level='standard',
                 return_boundary_image=False, boundary_width=12,
                 boundary_crop_margin=24,
                 hist_eq=False, normalize_stats='imagenet',
                 attention_guidance=False,
                 attn_guide_dilate=15, attn_guide_erode=5,
                 attn_guide_source='annotation',
                 anatomic_focus_mask=False,
                 anatomic_focus_local=False,
                 anatomic_focus_graduated=True,
                 anatomic_wall_outer_px=14,
                 anatomic_wall_inner_px=6,
                 anatomic_local_margin=0.08,
                 anatomic_lumen_rim_px=10,
                 anatomic_lumen_corridor_expand=0.30):
        self.df = pd.read_csv(csv_path)
        self.global_transform = global_transform
        self.local_transform = local_transform
        self.global_size = global_size
        self.local_size = local_size
        self.clinical_cols = list(clinical_cols) if clinical_cols else []
        self.use_overlay_as_global = use_overlay_as_global
        self.roi_fallback = roi_fallback
        self.roi_crop_ratio = roi_crop_ratio
        self.use_mask_channel = use_mask_channel
        self.mask_dir = Path(mask_dir) if mask_dir else None
        self.mask_augment_align = mask_augment_align
        self.aug_level = aug_level
        self.return_boundary_image = return_boundary_image
        self.boundary_width = int(boundary_width)
        self.boundary_crop_margin = int(boundary_crop_margin)
        self.hist_eq = hist_eq
        self.normalize_stats = normalize_stats
        self.attention_guidance = attention_guidance
        self.attn_guide_dilate = attn_guide_dilate
        self.attn_guide_erode = attn_guide_erode
        self.attn_guide_source = attn_guide_source
        self.anatomic_focus_mask = anatomic_focus_mask
        self.anatomic_focus_local = anatomic_focus_local
        self.anatomic_focus_graduated = anatomic_focus_graduated
        self.anatomic_wall_outer_px = int(anatomic_wall_outer_px)
        self.anatomic_wall_inner_px = int(anatomic_wall_inner_px)
        self.anatomic_local_margin = float(anatomic_local_margin)
        self.anatomic_lumen_rim_px = int(anatomic_lumen_rim_px)
        self.anatomic_lumen_corridor_expand = float(anatomic_lumen_corridor_expand)

        if 'age' in self.clinical_cols:
            self.age_mean = age_mean if age_mean is not None else self.df['age'].mean()
            self.age_std = age_std if age_std is not None else self.df['age'].std()
            if self.age_std == 0:
                self.age_std = 1.0

        self._default_global = T.Compose([
            T.Resize((global_size, global_size)), T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])
        self._default_local = T.Compose([
            T.Resize((local_size, local_size)), T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])

    def _load_mask_pil(self, row):
        """读取 mask，并返回单通道 PIL；失败时返回 None。"""
        mask_loaded = False
        mask_np = None

        mask_path_col = row.get('mask_path', '')
        if pd.notna(mask_path_col) and str(mask_path_col).strip():
            mp = Path(str(mask_path_col))
            if mp.exists():
                mask_np = np.array(Image.open(mp).convert('L'))
                mask_loaded = True
            elif not mp.is_absolute():
                mp2 = Path(__file__).resolve().parents[1].parent / mp
                if mp2.exists():
                    mask_np = np.array(Image.open(mp2).convert('L'))
                    mask_loaded = True

        if not mask_loaded:
            from lib.anatomic_focus import resolve_row_mask_path
            resolved = resolve_row_mask_path(row)
            if resolved is not None:
                mask_np = np.array(Image.open(resolved).convert('L'))
                mask_loaded = True

        if not mask_loaded and self.mask_dir is not None:
            stem = Path(str(row['image_path'])).stem
            for stem_candidate in [stem, f"{stem}_mask"]:
                for ext in ['.png', '.jpg', '.npy']:
                    mp = self.mask_dir / f"{stem_candidate}{ext}"
                    if mp.exists():
                        if ext == '.npy':
                            mask_np = np.load(str(mp))
                        else:
                            mask_np = np.array(Image.open(mp).convert('L'))
                        mask_loaded = True
                        break
                if mask_loaded:
                    break

        if not mask_loaded or mask_np is None:
            return None

        mask_np = (mask_np > 127).astype(np.uint8) * 255
        return Image.fromarray(mask_np, mode='L')

    def _load_anatomic_focus_array(self, row, img_size):
        """Lumen-relative lesion + wall layers; float32 [0,1] or uint8 mask."""
        from lib.anatomic_focus import (
            anatomic_focus_float,
            anatomic_focus_mask_u8,
            build_anatomic_focus_float,
            build_anatomic_focus_mask_u8,
            lumen_box_from_row,
            mask_from_array,
        )

        h, w = img_size[1], img_size[0]
        lumen_box = lumen_box_from_row(row)
        if self.anatomic_focus_graduated:
            focus = anatomic_focus_float(
                (h, w),
                row=row,
                lumen_box=lumen_box,
                outer_px=self.anatomic_wall_outer_px,
                inner_px=self.anatomic_wall_inner_px,
                lumen_rim_px=self.anatomic_lumen_rim_px,
                lumen_corridor_expand=self.anatomic_lumen_corridor_expand,
            )
        else:
            focus = anatomic_focus_mask_u8(
                (h, w),
                row=row,
                outer_px=self.anatomic_wall_outer_px,
                inner_px=self.anatomic_wall_inner_px,
            ).astype(np.float32)

        if float(np.asarray(focus).sum()) == 0.0:
            mask_pil = self._load_mask_pil(row)
            if mask_pil is not None:
                if mask_pil.size != img_size:
                    mask_pil = mask_pil.resize(img_size, Image.NEAREST)
                lesion_u8 = mask_from_array(np.array(mask_pil), (h, w))
                if self.anatomic_focus_graduated:
                    focus = build_anatomic_focus_float(
                        lesion_u8,
                        lumen_box=lumen_box,
                        outer_px=self.anatomic_wall_outer_px,
                        inner_px=self.anatomic_wall_inner_px,
                        lumen_rim_px=self.anatomic_lumen_rim_px,
                        lumen_corridor_expand=self.anatomic_lumen_corridor_expand,
                    )
                else:
                    focus = build_anatomic_focus_mask_u8(
                        lesion_u8,
                        lumen_box=lumen_box,
                        outer_px=self.anatomic_wall_outer_px,
                        inner_px=self.anatomic_wall_inner_px,
                    ).astype(np.float32)
        return np.asarray(focus, dtype=np.float32)

    def _load_anatomic_focus_pil(self, row, img_size):
        from lib.anatomic_focus import focus_mask_to_pil

        focus = self._load_anatomic_focus_array(row, img_size)
        if float(focus.sum()) == 0.0:
            return self._load_mask_pil(row)
        return focus_mask_to_pil(focus)

    def _crop_local_from_anatomic_focus(self, g_pil: Image.Image, row) -> Image.Image:
        from lib.anatomic_focus import bbox_from_mask_u8, crop_pil_by_bbox

        w, h = g_pil.size
        focus_arr = self._load_anatomic_focus_array(row, (w, h))
        if float(focus_arr.sum()) == 0.0:
            return self._center_crop_pil(g_pil)
        focus_u8 = (focus_arr > 0.08).astype(np.uint8)
        bbox = bbox_from_mask_u8(focus_u8, margin_ratio=self.anatomic_local_margin)
        if bbox is not None:
            return crop_pil_by_bbox(g_pil, bbox)
        return self._center_crop_pil(g_pil)

    def _resolve_mask_pil_for_global(self, row, img_size):
        if self.anatomic_focus_mask:
            return self._load_anatomic_focus_pil(row, img_size)
        return self._load_mask_pil(row)

    def _load_gt_mask_from_annotation(self, row, img_size):
        """从 LabelMe JSON 加载 GT mask（polygon → binary mask）。
        
        Args:
            row: DataFrame 行
            img_size: (width, height)
        Returns:
            np.ndarray (H, W) uint8 binary mask, 或 None
        """
        img_path = Path(str(row['image_path']))
        ann_path = str(img_path).replace('/images/', '/annotations/').replace(
            img_path.suffix, '.json')
        
        if not Path(ann_path).exists():
            return None
        
        try:
            import json
            with open(ann_path) as f:
                ann = json.load(f)
            
            w, h = img_size
            mask = np.zeros((h, w), dtype=np.uint8)
            
            for shape in ann.get('shapes', []):
                pts = np.array(shape['points'], dtype=np.int32)
                if len(pts) >= 3:
                    cv2.fillPoly(mask, [pts], 1)
            
            return mask
        except Exception:
            return None

    def _make_border_target_from_mask(self, mask):
        if mask is None or mask.sum() == 0:
            feat_h = self.global_size // 32
            return np.zeros((feat_h, feat_h), dtype=np.float32)

        d_kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (self.attn_guide_dilate * 2 + 1,) * 2)
        e_kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (self.attn_guide_erode * 2 + 1,) * 2)

        dilated = cv2.dilate(mask.astype(np.uint8), d_kernel)
        eroded = cv2.erode(mask.astype(np.uint8), e_kernel)
        border = (dilated - eroded).astype(np.float32)

        feat_h = self.global_size // 32
        border_resized = cv2.resize(border, (feat_h, feat_h),
                                    interpolation=cv2.INTER_AREA)

        if border_resized.max() > 0:
            border_resized = border_resized / border_resized.max()

        border_resized = cv2.GaussianBlur(border_resized, (3, 3), 0.5)
        if border_resized.max() > 0:
            border_resized = border_resized / border_resized.max()

        return border_resized

    def _make_border_target(self, row, img_size, mask_override=None):
        """生成 border attention target（dilate - erode）。
        
        返回 resize 到 global_size 的 float32 二值 map，
        再做一次 Gaussian 平滑使目标更 soft。
        如果没有 GT mask，返回全零 target（相当于无约束）。
        """
        if mask_override is not None:
            mask = mask_override
        elif getattr(self, 'attn_guide_source', 'annotation') in {
            'pred_mask', 'mask', 'anatomic_focus', 'anatomic_focus_aug',
        }:
            if self.anatomic_focus_mask or self.attn_guide_source in {
                'anatomic_focus', 'anatomic_focus_aug',
            }:
                focus = self._load_anatomic_focus_array(row, img_size)
                mask = (focus > 0.08).astype(np.uint8)
            else:
                mask_pil = self._load_mask_pil(row)
                if mask_pil is None:
                    mask = None
                else:
                    mask_pil = mask_pil.resize(img_size, Image.NEAREST)
                    mask = (np.array(mask_pil, dtype=np.uint8) > 127).astype(np.uint8)
        else:
            mask = self._load_gt_mask_from_annotation(row, img_size)
        
        return self._make_border_target_from_mask(mask)

    def _apply_mask4ch_global_augment(self, g_pil, mask_pil, return_aug_mask=False):
        """对图像和 mask 施加一致的几何变换，再把 mask 作为第 4 通道拼接。"""
        import torch as _torch

        if self.hist_eq:
            g_pil = HistogramEqualize()(g_pil)

        if self.aug_level == 'light':
            g_pil = T.Resize((self.global_size, self.global_size))(g_pil)
            if mask_pil is not None:
                mask_pil = T.Resize((self.global_size, self.global_size), interpolation=InterpolationMode.NEAREST)(mask_pil)
            if random.random() < 0.5:
                g_pil = F.hflip(g_pil)
                if mask_pil is not None:
                    mask_pil = F.hflip(mask_pil)
        else:
            resize_size = self.global_size + 32
            g_pil = T.Resize((resize_size, resize_size))(g_pil)
            if mask_pil is not None:
                mask_pil = T.Resize((resize_size, resize_size), interpolation=InterpolationMode.NEAREST)(mask_pil)

            if self.aug_level == 'strong':
                crop_scale = (0.7, 1.0)
                rot_deg = 20
                cj = T.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.15)
                auto_p = 0.4
                speckle_p = 0.4
                gray_p = 0.05
                erasing_p = 0.2
            else:
                crop_scale = (0.8, 1.0)
                rot_deg = 15
                cj = T.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.1)
                auto_p = 0.3
                speckle_p = 0.3
                gray_p = 0.0
                erasing_p = 0.1

            i, j, h, w = T.RandomResizedCrop.get_params(g_pil, scale=crop_scale, ratio=(0.75, 1.3333))
            g_pil = F.resized_crop(g_pil, i, j, h, w, (self.global_size, self.global_size), InterpolationMode.BILINEAR)
            if mask_pil is not None:
                mask_pil = F.resized_crop(mask_pil, i, j, h, w, (self.global_size, self.global_size), InterpolationMode.NEAREST)

            if random.random() < 0.5:
                g_pil = F.hflip(g_pil)
                if mask_pil is not None:
                    mask_pil = F.hflip(mask_pil)

            angle = random.uniform(-rot_deg, rot_deg)
            g_pil = F.rotate(g_pil, angle, interpolation=InterpolationMode.BILINEAR, fill=0)
            if mask_pil is not None:
                mask_pil = F.rotate(mask_pil, angle, interpolation=InterpolationMode.NEAREST, fill=0)

            g_pil = cj(g_pil)
            if random.random() < auto_p:
                g_pil = T.RandomAutocontrast(p=1.0)(g_pil)
            if random.random() < speckle_p:
                g_pil = SpeckleReduction(p=1.0)(g_pil)
            if random.random() < gray_p:
                g_pil = T.RandomGrayscale(p=1.0)(g_pil)

        g_tensor = T.ToTensor()(g_pil)
        g_tensor = T.Normalize(*get_normalize_stats(self.normalize_stats))(g_tensor)

        if self.aug_level == 'strong':
            g_tensor = T.RandomErasing(p=0.2)(g_tensor)
        elif self.aug_level == 'light':
            pass
        else:
            g_tensor = T.RandomErasing(p=0.1)(g_tensor)

        if mask_pil is None:
            mask_tensor = _torch.zeros(1, self.global_size, self.global_size)
            mask_np = np.zeros((self.global_size, self.global_size), dtype=np.uint8)
        else:
            mask_arr = np.array(mask_pil, dtype=np.float32)
            if mask_arr.max() > 1.0:
                mask_arr = mask_arr / 255.0
            if self.anatomic_focus_graduated and self.anatomic_focus_mask:
                mask_tensor = _torch.from_numpy(mask_arr).unsqueeze(0)
                mask_np = (mask_arr > 0.08).astype(np.uint8)
            else:
                mask_np = (mask_arr > 0.5).astype(np.uint8)
                mask_tensor = _torch.from_numpy(mask_np.astype(np.float32)).unsqueeze(0)

        out = _torch.cat([g_tensor, mask_tensor], dim=0)
        if return_aug_mask:
            return out, mask_np
        return out

    def _append_mask_channel(self, rgb_tensor, row):
        """Load a predicted segmentation mask and concat it as the 4th channel.

        Looks for the mask PNG in self.mask_dir or in a 'mask_path' CSV column.
        The mask is resized to match global_size and appended to the 3-channel
        RGB tensor, producing a (4, H, W) tensor.
        """
        import torch as _torch

        mask_pil = self._resolve_mask_pil_for_global(row, (self.global_size, self.global_size))
        if mask_pil is None:
            mask_tensor = _torch.zeros(1, self.global_size, self.global_size)
        else:
            mask_resized = mask_pil.resize((self.global_size, self.global_size), Image.NEAREST)
            mask_tensor = _torch.from_numpy(np.array(mask_resized).astype(np.float32) / 255.0).unsqueeze(0)

        return _torch.cat([rgb_tensor, mask_tensor], dim=0)

    def _center_crop_pil(self, img: Image.Image) -> Image.Image:
        """对 PIL Image 做中心裁剪，保留 roi_crop_ratio 比例的中心区域。"""
        w, h = img.size
        crop_w = int(w * self.roi_crop_ratio)
        crop_h = int(h * self.roi_crop_ratio)
        left = (w - crop_w) // 2
        top  = (h - crop_h) // 2
        return img.crop((left, top, left + crop_w, top + crop_h))

    def _make_boundary_pil(self, g_pil: Image.Image, row, fallback_pil: Image.Image) -> Image.Image:
        """基于预测/提供的 mask 构造边界环带图。

        做法:
          1. 读取 mask
          2. 用膨胀-腐蚀差得到 boundary ring
          3. 裁出 ring 周围小框，框外保留黑底
        """
        mask_pil = self._resolve_mask_pil_for_global(row, g_pil.size) if self.anatomic_focus_mask else self._load_mask_pil(row)
        if mask_pil is None:
            return fallback_pil.copy()

        if mask_pil.size != g_pil.size:
            mask_pil = mask_pil.resize(g_pil.size, Image.NEAREST)

        mask_np = np.array(mask_pil, dtype=np.uint8)
        mask_bin = (mask_np > 127).astype(np.uint8)
        filter_size = max(3, self.boundary_width * 2 + 1)
        if filter_size % 2 == 0:
            filter_size += 1

        kernel = np.ones((filter_size, filter_size), dtype=np.uint8)
        dilated_np = cv2.dilate(mask_bin, kernel, iterations=1) > 0
        eroded_np = cv2.erode(mask_bin, kernel, iterations=1) > 0
        ring_np = np.logical_and(dilated_np, np.logical_not(eroded_np))
        if ring_np.sum() == 0:
            return fallback_pil.copy()

        ys, xs = np.where(dilated_np)
        if len(xs) == 0 or len(ys) == 0:
            return fallback_pil.copy()

        margin = self.boundary_crop_margin
        x1 = max(0, int(xs.min()) - margin)
        y1 = max(0, int(ys.min()) - margin)
        x2 = min(g_pil.size[0], int(xs.max()) + margin + 1)
        y2 = min(g_pil.size[1], int(ys.max()) + margin + 1)
        if x2 <= x1 or y2 <= y1:
            return fallback_pil.copy()

        rgb_np = np.array(g_pil, dtype=np.uint8)
        ring_crop = ring_np[y1:y2, x1:x2]
        rgb_crop = rgb_np[y1:y2, x1:x2].copy()
        rgb_crop[~ring_crop] = 0
        return Image.fromarray(rgb_crop)

    def _first_existing_path(self, row, columns):
        return _first_existing_path(row, columns)

    def _remap_legacy_image_path(self, row, value):
        return remap_legacy_image_path(row, value)

    def _resolve_global_path(self, row):
        return resolve_global_image_path(row)

    def _resolve_local_path(self, row):
        roi_source = str(row.get('roi_source', '')).strip().lower()

        # Predicted ROI CSVs store the crop separately from the original image.
        local_path = self._first_existing_path(
            row,
            ['predicted_roi_path', 'local_image_path'],
        )
        if local_path is not None:
            if roi_source in {'predicted', 'center_crop'}:
                return local_path, roi_source
            return local_path, 'predicted_roi'

        # Standard doctor-ROI CSVs keep ROI in roi_path.
        roi_path = self._first_existing_path(row, ['roi_path'])
        if roi_path is not None and roi_source not in {'predicted', 'center_crop'}:
            return roi_path, 'doctor_roi'

        # Predicted ROI / fallback rows often keep the ROI crop in image_path.
        if roi_source in {'predicted', 'center_crop'}:
            image_path = self._first_existing_path(row, ['image_path'])
            if image_path is not None:
                return image_path, roi_source

        return None, 'center_crop'

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]

        # ---------- Global image ----------
        img_path = self._resolve_global_path(row) or str(row['image_path'])
        if self.use_overlay_as_global:
            stem   = Path(img_path).stem
            suffix = Path(img_path).suffix
            overlay = img_path.replace('/images/', '/overlays/').replace(
                stem + suffix, stem + '_overlay' + suffix)
            if Path(overlay).exists():
                img_path = overlay

        try:
            g_pil = Image.open(img_path).convert('RGB')
        except Exception:
            g_pil = Image.new('RGB', (self.global_size, self.global_size), 0)

        # Append mask as 4th channel if enabled
        aug_mask_np = None
        if self.use_mask_channel:
            if self.mask_augment_align:
                mask_pil = self._resolve_mask_pil_for_global(row, g_pil.size)
                if self.attention_guidance and self.attn_guide_source in {
                    'aug_mask', 'pred_mask_aug', 'anatomic_focus_aug',
                }:
                    g_img, aug_mask_np = self._apply_mask4ch_global_augment(g_pil, mask_pil, return_aug_mask=True)
                else:
                    g_img = self._apply_mask4ch_global_augment(g_pil, mask_pil)
            else:
                g_transform = self.global_transform or self._default_global
                g_img = g_transform(g_pil)
                mask_pil = self._resolve_mask_pil_for_global(row, g_pil.size)
                if mask_pil is None:
                    g_img = self._append_mask_channel(g_img, row)
                else:
                    import torch as _torch
                    mask_resized = mask_pil.resize((self.global_size, self.global_size), Image.NEAREST)
                    mask_arr = np.array(mask_resized, dtype=np.float32)
                    if mask_arr.max() > 1.0:
                        mask_arr = mask_arr / 255.0
                    mask_tensor = _torch.from_numpy(mask_arr).unsqueeze(0)
                    g_img = _torch.cat([g_img, mask_tensor], dim=0)
        else:
            g_transform = self.global_transform or self._default_global
            g_img = g_transform(g_pil)

        # ---------- Local ROI ----------
        roi_path, local_source = self._resolve_local_path(row)
        roi_ok = roi_path is not None

        if self.anatomic_focus_local:
            l_pil = self._crop_local_from_anatomic_focus(g_pil, row)
            local_source = 'anatomic_focus'
            roi_ok = True
        elif roi_ok:
            try:
                l_pil = Image.open(str(roi_path)).convert('RGB')
            except Exception:
                # ROI 文件损坏 → 使用 center crop
                l_pil = self._center_crop_pil(g_pil)
                local_source = 'center_crop'
        else:
            # ROI 缺失，按 roi_fallback 策略处理
            if self.roi_fallback == 'center_crop':
                # 中心裁剪：保留病灶最可能所在的区域，视野比 Global 小
                # 优点：两分支输入不同；缺点：可能裁不到病灶（但比全图更聚焦）
                l_pil = self._center_crop_pil(g_pil)
                local_source = 'center_crop'
            else:
                # 'full_image'（旧行为，已废弃）: 两分支完全相同 → 双分支退化
                l_pil = g_pil.copy()
                local_source = 'full_image'

        l_transform = self.local_transform or self._default_local
        l_img = l_transform(l_pil)

        result = {
            'global_image': g_img,
            'local_image':  l_img,
            'label':        int(row['label']),
            'has_roi':      int(roi_ok),   # 供调试/分析使用
            'roi_source':   str(row.get('roi_source', '') or ''),
            'local_source':  local_source,
            'global_image_path': img_path,
        }

        if 'patient_id_unique' in self.df.columns and pd.notna(row.get('patient_id_unique')):
            result['patient_id'] = str(row['patient_id_unique'])
        elif 'patient_id' in self.df.columns and pd.notna(row.get('patient_id')):
            result['patient_id'] = str(row['patient_id'])

        if self.return_boundary_image:
            b_pil = self._make_boundary_pil(g_pil, row, l_pil)
            b_transform = self.local_transform or self._default_local
            result['boundary_image'] = b_transform(b_pil)

        if self.attention_guidance:
            import torch
            border_target = self._make_border_target(row, g_pil.size, mask_override=aug_mask_np)
            result['border_target'] = torch.from_numpy(border_target).float()

        # Clinical features
        if self.clinical_cols:
            import torch
            features = []
            for col in self.clinical_cols:
                val = row.get(col, 0)
                if col == 'age':
                    val = (val - self.age_mean) / self.age_std
                features.append(float(val) if not pd.isna(val) else 0.0)
            result['clinical'] = torch.tensor(features, dtype=torch.float32)

        return result


# ============================================================
# Multi-Frame Dataset: 按患者打包 K 帧
# ============================================================
class MultiFrameDataset(Dataset):
    """把同一患者的多帧打包成一个 sample。

    返回:
        images: (K, C, H, W)  已经过 transform
        mask:   (K,) bool      标记哪些帧有效（不足 K 帧的用 zero padding）
        label:  int            该患者的 T 分期
        clinical: (D,) float   可选临床特征

    使用方式:
        - DataLoader batch 后得到 (B, K, C, H, W)
        - 直接送入 MultiFrameClassifier
    """
    def __init__(self, csv_path, transform=None, image_size=384,
                 k_frames=4, clinical_cols=None,
                 age_mean=None, age_std=None):
        import torch
        self.torch = torch
        self.df = pd.read_csv(csv_path)
        self.transform = transform
        self.image_size = image_size
        self.K = k_frames
        self.clinical_cols = list(clinical_cols) if clinical_cols else []

        if 'age' in self.clinical_cols:
            self.age_mean = age_mean if age_mean is not None else self.df['age'].mean()
            self.age_std = age_std if age_std is not None else self.df['age'].std()
            if self.age_std == 0 or pd.isna(self.age_std):
                self.age_std = 1.0

        pid_col = 'patient_id_unique' if 'patient_id_unique' in self.df.columns else 'patient_id'
        self._pid_col = pid_col

        grouped = self.df.groupby(pid_col)
        self.patients = list(grouped.groups.keys())
        self.patient_rows = {pid: grouped.get_group(pid) for pid in self.patients}
        self.patient_labels = {pid: int(grp['label'].mode().iloc[0])
                               for pid, grp in grouped}

        self._fallback_transform = T.Compose([
            T.Resize((image_size, image_size)),
            T.ToTensor(),
            T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])

    def __len__(self):
        return len(self.patients)

    def _load_patient(self, pid):
        """加载一个患者的 K 帧图像 + 临床特征"""
        rows = self.patient_rows[pid]
        label = self.patient_labels[pid]

        n = len(rows)
        if n >= self.K:
            sampled = rows.sample(n=self.K, replace=False)
        else:
            sampled = rows

        transform = self.transform or self._fallback_transform
        imgs = []
        for _, row in sampled.iterrows():
            try:
                pil = Image.open(row['image_path']).convert('RGB')
            except Exception:
                pil = Image.new('RGB', (self.image_size, self.image_size), (0, 0, 0))
            imgs.append(transform(pil))

        valid_k = len(imgs)
        while len(imgs) < self.K:
            imgs.append(self.torch.zeros(3, self.image_size, self.image_size))

        images = self.torch.stack(imgs, dim=0)
        mask = self.torch.zeros(self.K, dtype=self.torch.bool)
        mask[:valid_k] = True

        result = {
            'images': images,
            'mask': mask,
            'label': label,
        }

        if self.clinical_cols:
            first_row = sampled.iloc[0]
            feats = []
            for col in self.clinical_cols:
                val = first_row.get(col, 0)
                if col == 'age':
                    val = (val - self.age_mean) / self.age_std
                feats.append(float(val) if not pd.isna(val) else 0.0)
            result['clinical'] = self.torch.tensor(feats, dtype=self.torch.float32)

        return result

    def __getitem__(self, idx):
        pid = self.patients[idx]
        return self._load_patient(pid)
