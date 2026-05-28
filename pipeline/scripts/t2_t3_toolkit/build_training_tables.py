#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

PIPELINE_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(PIPELINE_SCRIPTS_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PIPELINE_SCRIPTS_ROOT))

from clinical_master_utils import CANDIDATE_PATH, ensure_patient_clinical_master  # noqa: E402
from common import (
    METADATA_DIR,
    ROOT,
    SPLIT_DIR,
    TRAINING_TABLES_DIR,
    canonical_image_key_from_stem,
    ensure_base_dirs,
    ensure_dir,
    extract_frame_index,
    extract_patient_and_frame,
    first_nonempty,
    longest_text,
    nonempty,
    normalize_patient_id,
    parse_float,
    parse_int,
    unique_join,
)


@dataclass(frozen=True)
class DatasetConfig:
    dataset_key: str
    cohort: str
    hospital: str
    year_group: str
    crop_ui_dir: Path
    table_ids: tuple[str, ...]
    manifest_kind: str


DATASET_CONFIGS = (
    DatasetConfig(
        dataset_key="internal_xh_2018",
        cohort="internal",
        hospital="Xiehe",
        year_group="2018",
        crop_ui_dir=ROOT / "dataset" / "internal" / "training_2018_2024" / "2018" / "crop_ui",
        table_ids=("internal_2018_direct_surgery",),
        manifest_kind="internal",
    ),
    DatasetConfig(
        dataset_key="internal_xh_2019",
        cohort="internal",
        hospital="Xiehe",
        year_group="2019",
        crop_ui_dir=ROOT / "dataset" / "internal" / "training_2018_2024" / "2019" / "crop_ui",
        table_ids=("internal_2019_direct_surgery",),
        manifest_kind="internal",
    ),
    DatasetConfig(
        dataset_key="internal_xh_2020_2023",
        cohort="internal",
        hospital="Xiehe",
        year_group="2020_2023",
        crop_ui_dir=ROOT / "dataset" / "internal" / "training_2018_2024" / "2020_2023" / "crop_ui",
        table_ids=("internal_2020_2023_direct_surgery",),
        manifest_kind="internal",
    ),
    DatasetConfig(
        dataset_key="internal_xh_2024",
        cohort="internal",
        hospital="Xiehe",
        year_group="2024",
        crop_ui_dir=ROOT / "dataset" / "internal" / "training_2018_2024" / "2024" / "crop_ui",
        table_ids=("internal_2024_direct_surgery",),
        manifest_kind="internal",
    ),
    DatasetConfig(
        dataset_key="internal_xh_2025",
        cohort="internal",
        hospital="Xiehe",
        year_group="2025",
        crop_ui_dir=ROOT / "dataset" / "internal" / "prospective_2025" / "2025" / "crop_ui",
        table_ids=("internal_2025_direct_surgery",),
        manifest_kind="internal",
    ),
    DatasetConfig(
        dataset_key="external_sanming",
        cohort="external",
        hospital="Sanming",
        year_group="external",
        crop_ui_dir=ROOT / "dataset" / "external" / "三明市第二医院" / "crop_ui",
        table_ids=("external_sanming_direct_surgery",),
        manifest_kind="external",
    ),
    DatasetConfig(
        dataset_key="external_tumor",
        cohort="external",
        hospital="TumorHospital",
        year_group="external",
        crop_ui_dir=ROOT / "dataset" / "external" / "福建省肿瘤医院" / "crop_ui",
        table_ids=("external_tumor_hospital_direct_surgery",),
        manifest_kind="external",
    ),
    DatasetConfig(
        dataset_key="external_putian1",
        cohort="external",
        hospital="Putian1",
        year_group="external",
        crop_ui_dir=ROOT / "dataset" / "external" / "莆田学院附属医院" / "crop_ui",
        table_ids=("external_putian1_direct_surgery",),
        manifest_kind="external",
    ),
    DatasetConfig(
        dataset_key="external_putian2",
        cohort="external",
        hospital="Putian2",
        year_group="external",
        crop_ui_dir=ROOT / "dataset" / "external" / "莆田市第一医院" / "crop_ui",
        table_ids=("external_putian2_direct_surgery",),
        manifest_kind="external",
    ),
    DatasetConfig(
        dataset_key="external_beijing_friendship",
        cohort="external",
        hospital="BeijingFriendship",
        year_group="external",
        crop_ui_dir=ROOT / "dataset" / "external" / "北京友谊医院" / "crop_ui",
        table_ids=("external_beijing_friendship_direct_surgery",),
        manifest_kind="external",
    ),
    DatasetConfig(
        dataset_key="external_foshan_first",
        cohort="external",
        hospital="FoshanFirst",
        year_group="external",
        crop_ui_dir=ROOT / "dataset" / "external" / "佛山市第一人民医院" / "crop_ui",
        table_ids=("external_foshan_first_direct_surgery",),
        manifest_kind="external",
    ),
    DatasetConfig(
        dataset_key="external_cnnc_504",
        cohort="external",
        hospital="CNNC504",
        year_group="external",
        crop_ui_dir=ROOT / "dataset" / "external" / "中核五〇四医院" / "crop_ui",
        table_ids=("external_cnnc_504_direct_surgery",),
        manifest_kind="external",
    ),
    DatasetConfig(
        dataset_key="external_dehua",
        cohort="external",
        hospital="Dehua",
        year_group="external",
        crop_ui_dir=ROOT / "dataset" / "external" / "福建省德化县医院" / "crop_ui",
        table_ids=("external_dehua_direct_surgery",),
        manifest_kind="external",
    ),
    DatasetConfig(
        dataset_key="external_fujian_provincial",
        cohort="external",
        hospital="FujianProvincial",
        year_group="external",
        crop_ui_dir=ROOT / "dataset" / "external" / "福建省立医院" / "crop_ui",
        table_ids=("external_fujian_provincial_direct_surgery",),
        manifest_kind="external",
    ),
)

CONFIG_BY_KEY = {config.dataset_key: config for config in DATASET_CONFIGS}
TABLE_ID_TO_CONFIG = {
    table_id: config for config in DATASET_CONFIGS for table_id in config.table_ids
}

SOURCE_TO_DATASET_CANDIDATES = {
    "int/2018": ("internal_xh_2018",),
    "int/2019": ("internal_xh_2019",),
    "int/2020_2023": ("internal_xh_2020_2023",),
    "int/2024": ("internal_xh_2024",),
    "int/prospective": ("internal_xh_2025",),
    "ext/putian": ("external_putian1", "external_putian2"),
    "ext/putian2": ("external_putian2", "external_putian1"),
    "ext/putian_2024": ("external_putian2", "external_putian1"),
    "ext/putian_2024_new": ("external_putian2", "external_putian1"),
    "ext/putian_2025_07_09": ("external_putian2", "external_putian1"),
    "ext/multicenter": ("external_tumor", "external_sanming"),
    "ext/zhongliu": ("external_tumor",),
    "ext/sanming": ("external_sanming",),
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build unified training tables and patient-level split for T staging."
    )
    parser.add_argument(
        "--split-dir",
        type=Path,
        default=ROOT / "pipeline" / "data" / "tstaging_4class",
        help="Directory containing canonical train/val/test CSV files.",
    )
    return parser.parse_args()


def first_matching_column(columns: Iterable[str], keywords: tuple[str, ...]) -> str | None:
    for column in columns:
        if any(keyword in column for keyword in keywords):
            return column
    return None


def load_clinical_master() -> tuple[pd.DataFrame, pd.DataFrame]:
    master_df = ensure_patient_clinical_master()
    raw_df = pd.read_csv(CANDIDATE_PATH, low_memory=False) if CANDIDATE_PATH.exists() else pd.DataFrame()
    return master_df, raw_df


def build_sample_inventory() -> pd.DataFrame:
    rows: list[dict] = []
    for config in DATASET_CONFIGS:
        image_dir = config.crop_ui_dir / "images"
        annotation_dir = config.crop_ui_dir / "annotations"
        roi_mask_dir = config.crop_ui_dir / "roi_masks"
        for image_path in sorted(image_dir.iterdir()):
            if not image_path.is_file() or image_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue
            patient_id_norm, frame_index = extract_patient_and_frame(image_path.stem)
            rows.append(
                {
                    "dataset_key": config.dataset_key,
                    "cohort": config.cohort,
                    "hospital": config.hospital,
                    "year_group": config.year_group,
                    "image_name": image_path.name,
                    "image_stem": image_path.stem,
                    "image_key": canonical_image_key_from_stem(image_path.stem),
                    "patient_id_norm": patient_id_norm,
                    "frame_index": frame_index,
                    "image_path": str(image_path.relative_to(ROOT)),
                    "annotation_path": str((annotation_dir / f"{image_path.stem}.json").relative_to(ROOT)),
                    "roi_mask_path": (
                        str((roi_mask_dir / f"{image_path.stem}.png").relative_to(ROOT))
                        if (roi_mask_dir / f"{image_path.stem}.png").exists()
                        else ""
                    ),
                }
            )
    inventory_df = pd.DataFrame(rows)
    return inventory_df


def load_manifest_index() -> dict[tuple[str, str], dict]:
    external_center_to_key = {
        "三明市第二医院": "external_sanming",
        "福建省肿瘤医院": "external_tumor",
        "莆田学院附属医院": "external_putian1",
        "莆田市第一医院": "external_putian2",
        "北京友谊医院": "external_beijing_friendship",
        "佛山市第一人民医院": "external_foshan_first",
        "中核五〇四医院": "external_cnnc_504",
        "福建省德化县医院": "external_dehua",
        "福建省立医院": "external_fujian_provincial",
    }
    legacy_external_prefixes = {
        "external_sanming": ("三明市第二医院__", "三明胃癌直接手术__"),
        "external_tumor": ("福建省肿瘤医院__", "肿瘤医院直接手术__"),
        "external_putian1": ("莆田学院附属医院__", "莆田1胃癌直接手术__"),
        "external_putian2": ("莆田市第一医院__", "莆田2胃癌直接手术__"),
        "external_beijing_friendship": ("北京友谊医院__",),
        "external_foshan_first": ("佛山市第一人民医院__",),
        "external_cnnc_504": ("中核五〇四医院__",),
        "external_dehua": ("福建省德化县医院__",),
        "external_fujian_provincial": ("福建省立医院__",),
    }

    index: dict[tuple[str, str], dict] = {}
    for manifest_kind in ("internal", "external"):
        manifest_path = ROOT / "dataset" / manifest_kind / "manifest.csv"
        if not manifest_path.exists():
            continue
        manifest_df = pd.read_csv(manifest_path, dtype=str, low_memory=False)
        for _, row in manifest_df.iterrows():
            sample_id = row["sample_id"]
            image_key = canonical_image_key_from_stem(sample_id)
            dataset_key = None
            if manifest_kind == "external":
                group_target = str(row.get("group_targets", "")).split(";")[0]
                dataset_key = external_center_to_key.get(group_target)
                if dataset_key is None:
                    for candidate_key, prefixes in legacy_external_prefixes.items():
                        if any(sample_id.startswith(prefix) for prefix in prefixes):
                            dataset_key = candidate_key
                            break
            else:
                for config in DATASET_CONFIGS:
                    if config.manifest_kind != manifest_kind:
                        continue
                    if config.dataset_key.startswith("internal_xh_2020_2023") and sample_id.startswith("20-23直接手术"):
                        dataset_key = config.dataset_key
                    elif config.dataset_key == "internal_xh_2018" and sample_id.startswith("2018直接手术"):
                        dataset_key = config.dataset_key
                    elif config.dataset_key == "internal_xh_2019" and sample_id.startswith("2019"):
                        dataset_key = config.dataset_key
                    elif config.dataset_key == "internal_xh_2024" and "2024年直接手术" in sample_id:
                        dataset_key = config.dataset_key
                    elif config.dataset_key == "internal_xh_2025" and sample_id.startswith("2025直接手术"):
                        dataset_key = config.dataset_key
            if dataset_key is None:
                continue
            index[(dataset_key, image_key)] = {
                "manifest_sample_id": sample_id,
                "source_image": row.get("image_source", ""),
                "source_mask": row.get("mask_source", ""),
                "group_targets": row.get("group_targets", ""),
                "image_width": row.get("image_width", ""),
                "image_height": row.get("image_height", ""),
                "original_rect": row.get("original_rect", ""),
                "ui_crop_rect": row.get("ui_crop_rect", ""),
                "roi_crop_rect": row.get("roi_crop_rect", ""),
            }
    return index


def load_split_rows(split_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    tables = []
    fallback_tables = []
    for split_name in ("train", "val", "test"):
        df = pd.read_csv(split_dir / f"{split_name}.csv", dtype=str, low_memory=False)
        df["split"] = split_name
        df["split_source_file"] = f"{split_name}.csv"
        tables.append(df)
        fallback = pd.read_csv(split_dir / f"{split_name}_clinical.csv", dtype=str, low_memory=False)
        fallback["split"] = split_name
        fallback_tables.append(fallback)
    return pd.concat(tables, ignore_index=True), pd.concat(fallback_tables, ignore_index=True)


def resolve_split_dataset_key(source_value: str, image_stem: str) -> tuple[str | None, tuple[str, ...]]:
    candidates = SOURCE_TO_DATASET_CANDIDATES.get(source_value, ())
    if source_value == "ext/multicenter" and image_stem.startswith("pt"):
        candidates = ("external_putian1", "external_putian2", *candidates)
    return (candidates[0] if candidates else None), candidates


def build_split_sample_table(
    split_df: pd.DataFrame, inventory_df: pd.DataFrame, manifest_index: dict[tuple[str, str], dict]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    inventory_index = {
        (row.dataset_key, row.image_key): row for row in inventory_df.itertuples(index=False)
    }
    matched_rows: list[dict] = []
    unresolved_rows: list[dict] = []
    for row in split_df.itertuples(index=False):
        image_stem = Path(row.image_path).stem
        patient_id_norm = normalize_patient_id(row.patient_id)
        frame_index = extract_frame_index(image_stem)
        image_key = f"{patient_id_norm or 'unknown'}::{(frame_index or 0):03d}"
        _, dataset_candidates = resolve_split_dataset_key(row.source, image_stem)
        matched = None
        for dataset_key in dataset_candidates:
            matched = inventory_index.get((dataset_key, image_key))
            if matched is not None:
                break
        if matched is None:
            for dataset_key in CONFIG_BY_KEY:
                matched = inventory_index.get((dataset_key, image_key))
                if matched is not None:
                    break
        if matched is None:
            unresolved_rows.append(
                {
                    "split": row.split,
                    "source": row.source,
                    "image_path_legacy": row.image_path,
                    "roi_path_legacy": row.roi_path,
                    "patient_id": row.patient_id,
                    "image_key": image_key,
                }
            )
            continue
        manifest_meta = manifest_index.get((matched.dataset_key, matched.image_key), {})
        matched_rows.append(
            {
                "sample_uid": f"{matched.dataset_key}::{matched.image_stem}",
                "dataset_key": matched.dataset_key,
                "cohort": matched.cohort,
                "hospital": matched.hospital,
                "year_group": matched.year_group,
                "split": row.split,
                "split_source_file": row.split_source_file,
                "source": row.source,
                "image_path": matched.image_path,
                "annotation_path": matched.annotation_path,
                "roi_mask_path": matched.roi_mask_path,
                "image_name": matched.image_name,
                "image_stem": matched.image_stem,
                "image_key": matched.image_key,
                "patient_id": row.patient_id,
                    "patient_id_norm": patient_id_norm,
                "frame_index": matched.frame_index,
                "label": parse_int(row.label),
                "stage_label": row.T_stage,
                "class_label": parse_int(row.class_label),
                "image_path_legacy": row.image_path,
                "roi_path_legacy": row.roi_path,
                **manifest_meta,
            }
        )
    return pd.DataFrame(matched_rows), pd.DataFrame(unresolved_rows)


def build_fallback_master(split_clinical_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for row in split_clinical_df.itertuples(index=False):
        image_stem = Path(row.image_path).stem
        _, dataset_candidates = resolve_split_dataset_key(row.source, image_stem)
        if not dataset_candidates:
            continue
        dataset_key = dataset_candidates[0]
        patient_id_norm = normalize_patient_id(row.patient_id)
        if patient_id_norm is None:
            continue
        config = CONFIG_BY_KEY[dataset_key]
        rows.append(
            {
                "patient_uid": f"{dataset_key}::{patient_id_norm}",
                "patient_id": row.patient_id,
                "patient_id_norm": patient_id_norm,
                "dataset_key": dataset_key,
                "cohort": config.cohort,
                "hospital": config.hospital,
                "year_group": config.year_group,
                "record_origin": "split_clinical_fallback",
                "source_table_ids": "",
                "source_sheets": "",
                "sex": parse_int(row.sex),
                "age": parse_float(row.age),
                "tumor_long_diameter_cm": parse_float(row.tumor_length_cm),
                "tumor_thickness_cm": parse_float(row.tumor_thickness_cm),
                "tumor_location_code": parse_int(row.tumor_location),
                "cea_value": parse_float(row.cea_value),
                "cea_positive": parse_int(row.cea_binary),
                "ca199_value": parse_float(row.ca199_value),
                "ca199_positive": parse_int(row.ca199_binary),
                "pathology_text": None,
                "differentiation_code": parse_int(row.differentiation),
                "lauren_code": parse_int(row.lauren_type),
                "discharge_diagnosis": None,
                "pT": parse_int(row.label) + 1 if parse_int(row.label) is not None else None,
                "pN": None,
                "node_positive": None,
                "pM": None,
                "pStage": None,
            }
        )
    fallback_df = pd.DataFrame(rows)
    if fallback_df.empty:
        return fallback_df
    fallback_df = fallback_df.drop_duplicates(subset=["patient_uid"], keep="first")
    fallback_df["has_clinical_data"] = fallback_df[
        [
            "sex",
            "age",
            "tumor_long_diameter_cm",
            "tumor_thickness_cm",
            "tumor_location_code",
            "cea_value",
            "cea_positive",
            "ca199_value",
            "ca199_positive",
        ]
    ].notna().any(axis=1)
    fallback_df["has_pathology_data"] = False
    return fallback_df


def attach_clinical_features(sample_df: pd.DataFrame, master_df: pd.DataFrame) -> pd.DataFrame:
    merged = sample_df.merge(
        master_df,
        on=["patient_uid", "patient_id_norm", "dataset_key", "cohort", "hospital", "year_group"],
        how="left",
        suffixes=("", "_master"),
    )
    merged["has_clinical_match"] = merged["record_origin"].notna()
    return merged


def build_patient_split(sample_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for patient_uid, group in sample_df.groupby("patient_uid", sort=True):
        split_values = sorted(group["split"].dropna().unique().tolist())
        rows.append(
            {
                "patient_uid": patient_uid,
                "patient_id": first_nonempty(group["patient_id"]),
                "patient_id_norm": first_nonempty(group["patient_id_norm"]),
                "dataset_key": first_nonempty(group["dataset_key"]),
                "cohort": first_nonempty(group["cohort"]),
                "hospital": first_nonempty(group["hospital"]),
                "year_group": first_nonempty(group["year_group"]),
                "split": split_values[0] if len(split_values) == 1 else "mixed",
                "split_memberships": ";".join(split_values),
                "split_conflict": int(len(split_values) > 1),
                "sample_count": int(len(group)),
                "stage_labels": unique_join(group["stage_label"]),
            }
        )
    return pd.DataFrame(rows)


def save_outputs(
    master_df: pd.DataFrame,
    sample_df: pd.DataFrame,
    unresolved_df: pd.DataFrame,
    patient_split_df: pd.DataFrame,
) -> None:
    training_tables = TRAINING_TABLES_DIR
    ensure_dir(training_tables)
    internal_df = sample_df[sample_df["cohort"] == "internal"].copy()
    external_df = sample_df[sample_df["cohort"] == "external"].copy()

    master_path = training_tables / "patient_master_table.csv"
    split_copy_path = training_tables / "patient_split.csv"
    internal_path = training_tables / "training_sample_table_internal.csv"
    external_path = training_tables / "training_sample_table_external.csv"
    all_path = training_tables / "training_sample_table_all.csv"
    unresolved_path = training_tables / "unresolved_split_rows.csv"
    patient_split_path = SPLIT_DIR / "t2_t3_patient_split.csv"

    master_df.to_csv(master_path, index=False, encoding="utf-8-sig")
    internal_df.to_csv(internal_path, index=False, encoding="utf-8-sig")
    external_df.to_csv(external_path, index=False, encoding="utf-8-sig")
    sample_df.to_csv(all_path, index=False, encoding="utf-8-sig")
    unresolved_df.to_csv(unresolved_path, index=False, encoding="utf-8-sig")
    patient_split_df.to_csv(patient_split_path, index=False, encoding="utf-8-sig")
    patient_split_df.to_csv(split_copy_path, index=False, encoding="utf-8-sig")

    summary = {
        "patient_master_rows": int(len(master_df)),
        "training_sample_rows_all": int(len(sample_df)),
        "training_sample_rows_internal": int(len(internal_df)),
        "training_sample_rows_external": int(len(external_df)),
        "patient_split_rows": int(len(patient_split_df)),
        "patients_with_split_conflict": int(patient_split_df["split_conflict"].sum()) if len(patient_split_df) else 0,
        "samples_without_clinical_match": int((~sample_df["has_clinical_match"]).sum()) if len(sample_df) else 0,
        "unresolved_split_rows": int(len(unresolved_df)),
        "output_files": {
            "patient_master_table": str(master_path.relative_to(ROOT)),
            "patient_split": str(patient_split_path.relative_to(ROOT)),
            "training_sample_table_internal": str(internal_path.relative_to(ROOT)),
            "training_sample_table_external": str(external_path.relative_to(ROOT)),
            "training_sample_table_all": str(all_path.relative_to(ROOT)),
        },
    }
    (METADATA_DIR / "t2_t3_training_tables_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (training_tables / "README.md").write_text(
        "\n".join(
            [
                "# T2/T3 Training Tables",
                "",
                "- `patient_master_table.csv`: one row per patient, built from `dataset/tables/by_source/*.csv` with split-clinical fallback.",
                "- `patient_split.csv`: convenience copy of `data/splits/t2_t3_patient_split.csv`.",
                "- `training_sample_table_internal.csv`: canonical internal crop-ui samples merged with patient features.",
                "- `training_sample_table_external.csv`: canonical external crop-ui samples merged with patient features.",
                "- `training_sample_table_all.csv`: union of the internal and external training tables.",
                "- `unresolved_split_rows.csv`: split rows that could not be mapped back to the current crop-ui files.",
                "",
                "All analysis scripts under `pipeline/scripts/t2_t3_toolkit/` read these tables as their primary data contract.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()
    ensure_base_dirs()

    clinical_master_df, _ = load_clinical_master()
    sample_inventory_df = build_sample_inventory()
    manifest_index = load_manifest_index()
    split_df, split_clinical_df = load_split_rows(args.split_dir)
    sample_df, unresolved_df = build_split_sample_table(split_df, sample_inventory_df, manifest_index)

    sample_patient_uids = (
        sample_df["dataset_key"].astype(str) + "::" + sample_df["patient_id_norm"].astype(str)
    ).unique()
    clinical_master_df = clinical_master_df[
        clinical_master_df["patient_uid"].isin(sample_patient_uids)
    ].copy()
    fallback_master_df = build_fallback_master(split_clinical_df)
    fallback_master_df = fallback_master_df[
        ~fallback_master_df["patient_uid"].isin(clinical_master_df["patient_uid"])
    ].copy()
    master_frames = [frame for frame in (clinical_master_df, fallback_master_df) if not frame.empty]
    if master_frames:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            patient_master_df = pd.concat(master_frames, ignore_index=True)
    else:
        patient_master_df = pd.DataFrame()
    if len(patient_master_df):
        patient_master_df = patient_master_df.sort_values(
            ["cohort", "hospital", "year_group", "patient_id_norm"]
        ).reset_index(drop=True)

    sample_df["patient_uid"] = sample_df["dataset_key"].astype(str) + "::" + sample_df["patient_id_norm"].astype(str)
    sample_df = attach_clinical_features(sample_df, patient_master_df)
    sample_df = sample_df.sort_values(["split", "cohort", "hospital", "patient_id_norm", "frame_index"]).reset_index(drop=True)
    patient_split_df = build_patient_split(sample_df)
    save_outputs(patient_master_df, sample_df, unresolved_df, patient_split_df)

    print("Built training tables:")
    print(f"  patient_master_table.csv rows: {len(patient_master_df)}")
    print(f"  training_sample_table_all.csv rows: {len(sample_df)}")
    print(f"  unresolved split rows: {len(unresolved_df)}")


if __name__ == "__main__":
    main()
