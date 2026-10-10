"""路径和数据合同。方案只写了模型骨架，划分 / 终点 / 图源由本文件补上。

方案 2: IMAGE_SIZE=448, ROI_EXPAND 默认 0.20（区间 0.15-0.25）。
方案 3: EMBED_DIM=1152, WEIGHT_DIR = google/medsiglip-448 本地权重。
方案 6: CLINICAL_FIELDS 11 项，编码成 22 个数（每项 _norm + _missing）。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Workspace stays this directory. After it moved under external/, the repo root is one level higher.
if ROOT.name == "medsiglip" and ROOT.parent.name == "external":
    MAIN_ROOT = ROOT.parent.parent
elif ROOT.name == "medsiglip":
    MAIN_ROOT = ROOT.parent
else:
    MAIN_ROOT = ROOT
BM_DATASET_DIR = MAIN_ROOT / "dataset/task_datasets/binary_benign_malignant"
BM_CACHE_DIR = ROOT / "pipeline/data/medsiglip448_bm_frame_features/binary_multicenter_joint_unseen_20260820"
BM_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_bm_20260825"
BM_LORA_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_bm_lora_20260826"
BM_GASTRITIS_CLINICAL = MAIN_ROOT / "dataset/gastritis_external/clinical_records.csv"
BM_TSTAGING_CLINICAL_DIR = MAIN_ROOT / "pipeline/data/tstaging_4class"

PHASE0_DIR = ROOT / "pipeline/data/tstaging_4class_screened_eval_phase0_xiehe_20260610"
DATASET_DIR = ROOT / "dataset/task_datasets/t_staging/maincenter_retrospective_v20260821"
WADI_DATASET_DIR = MAIN_ROOT / "dataset/task_datasets/t_staging/wadi_research_freeze_v20260827"
WEIGHT_DIR = ROOT / "artifacts/model_weights/medsiglip-448"
CACHE_DIR = ROOT / "pipeline/data/medsiglip448_tstaging_frame_features/maincenter_retrospective_v20260821"
REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_20260821"
TABPFN_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_tabpfn_20260821"
PLAN_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_plan_20260821"
PLAN_COMPLETE_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_plan_complete_20260825"
DEEP_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_deep_20260825"
LARGECLF_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_largeclf_tabpfn_20260825"
RETRY_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_retry_20260825"
PHASE1_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_phase1_boundary_20260825"
PHASE1_SEED_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_phase1_seeds_20260825"
AIV2_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_aiv2_stack_20260825"
AVGROI_CACHE_DIR = ROOT / "pipeline/data/medsiglip448_tstaging_frame_features/maincenter_retrospective_v20260821_avgroi"
AREAROI_CACHE_DIR = ROOT / "pipeline/data/medsiglip448_tstaging_frame_features/maincenter_retrospective_v20260821_arearoi"
LARGE_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_large_20260821"
OPT_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_opt_xlarge_20260821"
T34_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_t34_20260822"
BINARY_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_binary_20260822"
PLAN_LITERAL_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_plan_literal_20260822"
EXPAND15_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_expand15_20260822"
EXPAND25_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_expand25_20260822"
UNFREEZE_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_unfreeze_lora_20260822"
TSTAGING_LORA_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_unfreeze_lora_20260826"
ENSEMBLE_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_ensemble_20260822"
ENSEMBLE2_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_ensemble2_20260822"
ENSEMBLE3_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_ensemble3_20260822"
ENSEMBLE4_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_ensemble4_20260822"
LEDGER_DIR = ROOT / "pipeline/experiments/reports/gastricus_ledger"
SPATIAL_CACHE_DIR = ROOT / "pipeline/data/medsiglip448_tstaging_frame_features/maincenter_retrospective_v20260821_spatial"
SPATIAL_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_spatial_20260822"
PREOP_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_preop_20260822"
LAYERS_CACHE_DIR = ROOT / "pipeline/data/medsiglip448_tstaging_frame_features/maincenter_retrospective_v20260821_layers4"
LAYERS_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_layers4_20260822"
MULTI1525_CACHE_DIR = ROOT / "pipeline/data/medsiglip448_tstaging_frame_features/maincenter_retrospective_v20260821_multi1525"
MULTI1525_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_multi1525_20260822"
STACK_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_stack_20260822"
MASK_GEOM_CACHE = CACHE_DIR / "mask_geom_patient.npz"
MASK_GEOM_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_maskgeom_20260822"
MASKVIEW_CACHE_DIR = ROOT / "pipeline/data/medsiglip448_tstaging_frame_features/maincenter_retrospective_v20260821_maskview"
MASKVIEW_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_maskview_20260822"
TABPFN_XLARGE_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_tabpfn_xlarge_20260822"
TABPFN_BOTH_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_tabpfn_both_20260823"
T2_ERROR_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_t2_error_20260822"
T2COST_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_t2cost_20260822"
MASKCUT_CACHE_DIR = ROOT / "pipeline/data/medsiglip448_tstaging_frame_features/maincenter_retrospective_v20260821_maskcut"
MASKCUT_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_maskcut_20260822"
LOCKMACRO_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_lockmacro_20260822"
LONGRUN_REPORT_DIR = ROOT / "pipeline/experiments/reports/medsiglip_gastricus_longrun_tabpfn_20260823"
DEFAULT_FOURCLASS_CKPT = OPT_REPORT_DIR / "mlp_concat_gated" / "best_model.pt"
PREOP_DROP_FIELDS = ("lauren_type", "differentiation")


def cache_dir_for_expand(expand: float) -> Path:
    expand = float(expand)
    if abs(expand - 0.20) < 1e-9:
        return CACHE_DIR
    return ROOT / (
        "pipeline/data/medsiglip448_tstaging_frame_features/"
        f"maincenter_retrospective_v20260821_expand{int(round(expand * 100))}"
    )


def cache_dir_for_pad(pad: str) -> Path:
    pad = str(pad).lower()
    if pad == "black":
        return CACHE_DIR
    return ROOT / (
        "pipeline/data/medsiglip448_tstaging_frame_features/"
        f"maincenter_retrospective_v20260821_pad{pad}"
    )


def report_dir_for_pad(pad: str) -> Path:
    pad = str(pad).lower()
    return ROOT / f"pipeline/experiments/reports/medsiglip_gastricus_pad{pad}_20260822"


def report_dir_for_expand(expand: float) -> Path:
    expand = float(expand)
    if abs(expand - 0.15) < 1e-9:
        return EXPAND15_REPORT_DIR
    if abs(expand - 0.25) < 1e-9:
        return EXPAND25_REPORT_DIR
    if abs(expand - 0.20) < 1e-9:
        return OPT_REPORT_DIR
    return ROOT / f"pipeline/experiments/reports/medsiglip_gastricus_expand{int(round(expand * 100))}_20260822"

CENTER_BY_SOURCE = {
    "int/2018": "xiehe_2018",
    "int/2019": "xiehe_2019",
    "int/2020_2023": "xiehe_2020_2023",
    "int/2024": "xiehe_2024",
    "int/prospective": "xiehe_2025",
    "ext/putian": "putian_college",
    "ext/putian2": "putian_first",
    "ext/zhongliu": "fujian_cancer",
    "ext/sanming": "sanming_second",
    "ext/福建省德化县医院": "dehua",
    "ext/北京友谊医院": "beijing_friendship",
    "ext/佛山市第一人民医院": "foshan_first",
    "ext/中核五〇四医院": "cnnc_504",
    "ext/福建省立医院": "fujian_provincial",
}

SPLIT_FILES = {
    "train": "splits/train.csv",
    "val": "splits/val.csv",
    "test_prospective": "splits/test_prospective.csv",
    "test_external": "splits/test_external.csv",
}

ROLE_BY_SPLIT = {
    "train": "训练",
    "val": "验证",
    "test_prospective": "前瞻",
    "test_external": "外部",
}

RETROSPECTIVE_SOURCES = ("int/2018", "int/2019", "int/2020_2023", "int/2024")

INTERNAL_CROP_UI = {
    "int/2018": ROOT / "dataset/internal/training_2018_2024/2018/crop_ui",
    "int/2019": ROOT / "dataset/internal/training_2018_2024/2019/crop_ui",
    "int/2020_2023": ROOT / "dataset/internal/training_2018_2024/2020_2023/crop_ui",
    "int/2024": ROOT / "dataset/internal/training_2018_2024/2024/crop_ui",
    "int/prospective": ROOT / "dataset/internal/prospective_2025/2025/crop_ui",
}

# 方案 6: processed clinical。11 项，编码成 22 个数。方案未指定字段名。
CLINICAL_FIELDS = (
    "age",
    "sex",
    "lauren_type",
    "differentiation",
    "tumor_length_cm",
    "tumor_thickness_cm",
    "tumor_location",
    "cea_value",
    "cea_binary",
    "ca199_value",
    "ca199_binary",
)

CONTINUOUS_FIELDS = (
    "age",
    "tumor_length_cm",
    "tumor_thickness_cm",
    "cea_value",
    "ca199_value",
)

CATEGORICAL_ALLOWED = {
    "sex": {0, 1},
    "lauren_type": {1, 2, 3},
    "differentiation": {1, 2, 3, 4},
    "tumor_location": {0, 1, 2, 3},
    "cea_binary": {0, 1},
    "ca199_binary": {0, 1},
}

MAX_CODE = {
    "sex": 1,
    "lauren_type": 3,
    "differentiation": 4,
    "tumor_location": 10,
    "cea_binary": 1,
    "ca199_binary": 1,
}

T_STAGE_TO_LABEL = {"T1": 0, "T2": 1, "T3": 2, "T4a": 3, "T4b": 3, "T4+": 3}

EMBED_DIM = 1152  # 方案 3: 每视图 1152 维
IMAGE_SIZE = 448  # 方案 2: 官方 processor
N_CLASSES = 4
ROI_EXPAND = 0.20  # 方案 2.2: 15%-25% 区间内的默认外扩
WEIGHT_SHA256 = "3e1722b8100cca8b87cfe16e42140737aa6d312854e9e6bc24dff6db70e21d72"
WEIGHT_BYTES = 3513309984
CLASS_NAMES = ("T1", "T2", "T3", "T4+")
