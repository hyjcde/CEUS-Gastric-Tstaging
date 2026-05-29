"""Canonical repository paths (single source for scripts)."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# --- 七类资产主目录 ---
DATASET_DIR = PROJECT_ROOT / "dataset"
DATA_DIR = PROJECT_ROOT / "data"
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
CONFIGS_DIR = PROJECT_ROOT / "configs"
EXPERIMENTS_DIR = PROJECT_ROOT / "experiments"
APPS_DIR = PROJECT_ROOT / "apps"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
DOCS_DIR = PROJECT_ROOT / "docs"
MODELS_INDEX = PROJECT_ROOT / "models"

# --- 原始数据（实体路径，勿依赖根目录中文名）---
RAW_LEGACY_GASTRIC = DATA_DIR / "raw" / "legacy_gastric_staging"
RAW_LEGACY_EXTERNAL_SURGERY = DATA_DIR / "raw" / "legacy_external_direct_surgery"
RAW_LEGACY_LUMEN = DATA_DIR / "raw" / "legacy_lumen"
RAW_LEGACY_WALL_VIZ = DATA_DIR / "raw" / "legacy_wall_viz"

# --- 标注 / 权重 ---
ANNOTATION_BATCH = DATA_DIR / "annotation" / "batches" / "direction_annotation_batch.json"
ANNOTATION_OUTPUTS = DATA_DIR / "annotation" / "outputs" / "direction_annotations"
YOLO_WEIGHTS_DIR = ARTIFACTS_DIR / "model_weights" / "yolo"

# --- 兼容层（旧路径 symlink，仅供过渡）---
COMPAT_DIR = PROJECT_ROOT / "_compat"


def resolve_yolo_weight(name: str) -> Path:
    """Resolve yolo11*.pt from artifacts, then _compat, then project root."""
    for base in (YOLO_WEIGHTS_DIR, COMPAT_DIR, PROJECT_ROOT):
        candidate = base / name
        if candidate.is_file():
            return candidate.resolve()
    return (PROJECT_ROOT / name).resolve()
