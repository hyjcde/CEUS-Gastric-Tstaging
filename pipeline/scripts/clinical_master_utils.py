#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_TABLES_ROOT = PROJECT_ROOT / "dataset" / "tables"
BY_SOURCE_ROOT = DATASET_TABLES_ROOT / "by_source"
INDEX_PATH = DATASET_TABLES_ROOT / "clinical_table_index.csv"
MASTER_PATH = DATASET_TABLES_ROOT / "patient_clinical_master.csv"
CANDIDATE_PATH = DATASET_TABLES_ROOT / "patient_clinical_candidates.csv"
COVERAGE_OVERALL_PATH = DATASET_TABLES_ROOT / "patient_clinical_master_coverage_overall.csv"
COVERAGE_BY_GROUP_PATH = DATASET_TABLES_ROOT / "patient_clinical_master_coverage_by_group.csv"
SCHEMA_PATH = DATASET_TABLES_ROOT / "patient_clinical_schema.json"

TOOLKIT_ROOT = Path(__file__).resolve().parent / "t2_t3_toolkit"
if str(TOOLKIT_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLKIT_ROOT))

from common import longest_text, nonempty, normalize_patient_id, parse_float, parse_int, unique_join  # noqa: E402


@dataclass(frozen=True)
class DatasetConfig:
    dataset_key: str
    cohort: str
    hospital: str
    center: str
    year_group: str
    table_ids: tuple[str, ...]


@dataclass(frozen=True)
class ClinicalFieldSpec:
    name: str
    kind: str
    tier: str
    max_code: int | None = None


DATASET_CONFIGS = (
    DatasetConfig(
        dataset_key="internal_xh_2018",
        cohort="internal",
        hospital="Xiehe",
        center="协和内部",
        year_group="2018",
        table_ids=("internal_2018_direct_surgery",),
    ),
    DatasetConfig(
        dataset_key="internal_xh_2019",
        cohort="internal",
        hospital="Xiehe",
        center="协和内部",
        year_group="2019",
        table_ids=("internal_2019_direct_surgery",),
    ),
    DatasetConfig(
        dataset_key="internal_xh_2020_2023",
        cohort="internal",
        hospital="Xiehe",
        center="协和内部",
        year_group="2020_2023",
        table_ids=("internal_2020_2023_direct_surgery",),
    ),
    DatasetConfig(
        dataset_key="internal_xh_2024",
        cohort="internal",
        hospital="Xiehe",
        center="协和内部",
        year_group="2024",
        table_ids=("internal_2024_direct_surgery",),
    ),
    DatasetConfig(
        dataset_key="internal_xh_2025",
        cohort="internal",
        hospital="Xiehe",
        center="协和内部",
        year_group="2025",
        table_ids=("internal_2025_direct_surgery",),
    ),
    DatasetConfig(
        dataset_key="external_sanming",
        cohort="external",
        hospital="Sanming",
        center="三明市第二医院",
        year_group="external",
        table_ids=("external_sanming_direct_surgery",),
    ),
    DatasetConfig(
        dataset_key="external_tumor",
        cohort="external",
        hospital="TumorHospital",
        center="福建省肿瘤医院",
        year_group="external",
        table_ids=("external_tumor_hospital_direct_surgery",),
    ),
    DatasetConfig(
        dataset_key="external_putian1",
        cohort="external",
        hospital="Putian1",
        center="莆田学院附属医院",
        year_group="external",
        table_ids=("external_putian1_direct_surgery",),
    ),
    DatasetConfig(
        dataset_key="external_putian2",
        cohort="external",
        hospital="Putian2",
        center="莆田市第一医院",
        year_group="external",
        table_ids=("external_putian2_direct_surgery",),
    ),
    DatasetConfig(
        dataset_key="external_beijing_friendship",
        cohort="external",
        hospital="BeijingFriendship",
        center="北京友谊医院",
        year_group="external",
        table_ids=("external_beijing_friendship_direct_surgery",),
    ),
    DatasetConfig(
        dataset_key="external_foshan_first",
        cohort="external",
        hospital="FoshanFirst",
        center="佛山市第一人民医院",
        year_group="external",
        table_ids=("external_foshan_first_direct_surgery",),
    ),
    DatasetConfig(
        dataset_key="external_cnnc_504",
        cohort="external",
        hospital="CNNC504",
        center="中核五〇四医院",
        year_group="external",
        table_ids=("external_cnnc_504_direct_surgery",),
    ),
    DatasetConfig(
        dataset_key="external_dehua",
        cohort="external",
        hospital="Dehua",
        center="福建省德化县医院",
        year_group="external",
        table_ids=("external_dehua_direct_surgery",),
    ),
    DatasetConfig(
        dataset_key="external_fujian_provincial",
        cohort="external",
        hospital="FujianProvincial",
        center="福建省立医院",
        year_group="external",
        table_ids=("external_fujian_provincial_direct_surgery",),
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

CLINICAL_FIELD_SPECS = (
    ClinicalFieldSpec("age", "continuous", "core"),
    ClinicalFieldSpec("sex", "categorical", "core", max_code=1),
    ClinicalFieldSpec("lauren_type", "categorical", "pathology", max_code=3),
    ClinicalFieldSpec("differentiation", "categorical", "pathology", max_code=4),
    ClinicalFieldSpec("tumor_length_cm", "continuous", "core"),
    ClinicalFieldSpec("tumor_thickness_cm", "continuous", "core"),
    ClinicalFieldSpec("tumor_location", "categorical", "pathology", max_code=10),
    ClinicalFieldSpec("cea_value", "continuous", "marker"),
    ClinicalFieldSpec("cea_binary", "categorical", "marker", max_code=1),
    ClinicalFieldSpec("ca199_value", "continuous", "marker"),
    ClinicalFieldSpec("ca199_binary", "categorical", "marker", max_code=1),
)

FIELD_SPEC_BY_NAME = {spec.name: spec for spec in CLINICAL_FIELD_SPECS}
CONTINUOUS_FIELDS = [spec.name for spec in CLINICAL_FIELD_SPECS if spec.kind == "continuous"]
CATEGORICAL_FIELDS = [spec.name for spec in CLINICAL_FIELD_SPECS if spec.kind == "categorical"]
CLINICAL_FIELDS = [spec.name for spec in CLINICAL_FIELD_SPECS]

EXTRA_TEXT_FIELDS = ("pathology_text", "discharge_diagnosis")
EXTRA_NUMERIC_FIELDS = ("pT", "pN", "node_positive", "pM", "pStage")


def _source_uid(table_id: str, sheet_name: str, row_number: object) -> str:
    return f"{table_id}::{sheet_name}::{row_number}"


def first_matching_column(columns: list[str], keywords: tuple[str, ...]) -> str | None:
    for column in columns:
        if any(keyword in column for keyword in keywords):
            return column
    return None


def parse_binary(value: object) -> int | None:
    text = nonempty(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in {"1", "1.0", "true", "yes", "阳性"}:
        return 1
    if lowered in {"0", "0.0", "false", "no", "阴性"}:
        return 0
    parsed = parse_int(text)
    return parsed if parsed in (0, 1) else None


def parse_sex(value: object) -> int | None:
    text = nonempty(value)
    if text is None:
        return None
    parsed = parse_int(text)
    if parsed in (0, 1):
        return parsed
    if parsed == 2:
        return 1
    if "男" in text:
        return 1
    if "女" in text:
        return 0
    return None


def parse_lauren(value: object, pathology_text: object = None) -> int | None:
    text = nonempty(value)
    if text is not None:
        parsed = parse_int(text)
        if parsed in (1, 2, 3):
            return parsed
        if "肠" in text and "弥漫" not in text:
            return 1
        if "弥漫" in text and "肠" not in text:
            return 2
        if "混合" in text:
            return 3
    pathology = nonempty(pathology_text)
    if pathology is None:
        return None
    if "Lauren" not in pathology and "肠型" not in pathology and "弥漫型" not in pathology and "混合型" not in pathology:
        return None
    if "混合" in pathology:
        return 3
    if "弥漫" in pathology and "肠" not in pathology:
        return 2
    if "肠型" in pathology:
        return 1
    return None


def parse_differentiation(value: object, pathology_text: object = None) -> int | None:
    text = nonempty(value)
    if text is not None:
        parsed = parse_int(text)
        if parsed in (1, 2, 3, 4):
            return parsed
        if "未分化" in text:
            return 4
        if "低" in text:
            return 3 if "中-低" in text or "中低" in text else 4
        if "中" in text:
            return 2
        if "高" in text:
            return 1
    pathology = nonempty(pathology_text)
    if pathology is None:
        return None
    if "未分化" in pathology:
        return 4
    if "中-低分化" in pathology or "中低分化" in pathology:
        return 3
    if "低分化" in pathology:
        return 4
    if "中分化" in pathology:
        return 2
    if "高分化" in pathology:
        return 1
    return None


def parse_location(value: object) -> int | None:
    text = nonempty(value)
    if text is None:
        return None
    if any(marker in text for marker in ("贲门", "胃底")) and not text[:1].isdigit():
        return 0
    if "胃体" in text and not text[:1].isdigit():
        return 1
    if any(marker in text for marker in ("胃角", "胃窦", "幽门")) and not text[:1].isdigit():
        return 2
    if "全胃" in text and not text[:1].isdigit():
        return 3
    parsed = parse_int(text.split("、")[0].split(",")[0])
    if parsed is None:
        return None
    return parsed if 0 <= parsed <= 10 else None


def parse_continuous(value: object) -> float | None:
    parsed = parse_float(value)
    if parsed is None:
        return None
    return parsed if parsed >= 0 else None


def parse_text(value: object) -> str | None:
    return nonempty(value)


def detect_source_columns(columns: list[str]) -> dict[str, str | None]:
    return {
        "record_key": first_matching_column(columns, ("住院号", "ID", "序号")),
        "patient_name": first_matching_column(columns, ("姓名",)),
        "sex": first_matching_column(columns, ("性别",)),
        "age": first_matching_column(columns, ("年龄",)),
        "tumor_length_cm": first_matching_column(columns, ("长径",)),
        "tumor_thickness_cm": first_matching_column(columns, ("厚径",)),
        "tumor_location": first_matching_column(columns, ("肿瘤位置", "超声位置")),
        "pathology_text": first_matching_column(columns, ("病理",)),
        "differentiation": first_matching_column(columns, ("分化程度",)),
        "lauren_type": first_matching_column(columns, ("Lauren",)),
        "discharge_diagnosis": first_matching_column(columns, ("出院诊断",)),
        "pT": first_matching_column(columns, ("pT", "T:0=正常")),
        "pN": next((column for column in columns if column.startswith("N:") and "阴性" not in column), None),
        "node_positive": next((column for column in columns if column.startswith("N:") and "阴性" in column), None),
        "pM": first_matching_column(columns, ("M：", "M:", "M0")),
        "pStage": first_matching_column(columns, ("pStage",)),
        "cea_binary": next((column for column in columns if column.startswith("CEA：") or column.startswith("CEA:")), None),
        "ca199_binary": next((column for column in columns if column.startswith("CA199：") or column.startswith("CA199:")), None),
        "cea_value": next(
            (
                column
                for column in columns
                if "CEA" in column and "阳性" not in column and not (column.startswith("CEA：") or column.startswith("CEA:"))
            ),
            None,
        ),
        "ca199_value": next(
            (
                column
                for column in columns
                if ("CA199" in column or "CA19-9" in column)
                and "阳性" not in column
                and not (column.startswith("CA199：") or column.startswith("CA199:"))
            ),
            None,
        ),
    }


def _parse_field(field: str, row: dict[str, Any], column_map: dict[str, str | None]) -> tuple[Any, str | None, bool, bool]:
    column = column_map.get(field)
    raw_text = nonempty(row.get(column)) if column else None
    pathology_text = nonempty(row.get(column_map.get("pathology_text"))) if column_map.get("pathology_text") else None
    if field == "sex":
        value = parse_sex(raw_text)
    elif field == "age":
        value = parse_continuous(raw_text)
    elif field == "tumor_length_cm":
        value = parse_continuous(raw_text)
    elif field == "tumor_thickness_cm":
        value = parse_continuous(raw_text)
    elif field == "tumor_location":
        value = parse_location(raw_text)
    elif field == "lauren_type":
        value = parse_lauren(raw_text, pathology_text)
    elif field == "differentiation":
        value = parse_differentiation(raw_text, pathology_text)
    elif field in {"cea_value", "ca199_value"}:
        value = parse_continuous(raw_text)
    elif field in {"cea_binary", "ca199_binary"}:
        value = parse_binary(raw_text)
    elif field in EXTRA_TEXT_FIELDS:
        value = parse_text(raw_text)
    elif field in EXTRA_NUMERIC_FIELDS:
        value = parse_int(raw_text)
    else:
        value = None
    is_missing = raw_text is None
    parse_ok = value is not None
    return value, raw_text, is_missing, parse_ok


def resolve_split_dataset_candidates(source_value: str, image_stem: str) -> tuple[str, ...]:
    candidates = SOURCE_TO_DATASET_CANDIDATES.get(source_value, ())
    if source_value == "ext/multicenter" and image_stem.startswith("pt"):
        candidates = ("external_putian1", "external_putian2", *candidates)
    return candidates


def load_index_map(index_path: Path = INDEX_PATH) -> dict[tuple[str, str], dict[str, str]]:
    if not index_path.exists():
        return {}
    df = pd.read_csv(index_path, dtype=str, low_memory=False)
    index_map: dict[tuple[str, str], dict[str, str]] = {}
    for row in df.to_dict("records"):
        index_map[(str(row.get("table_id", "")), str(row.get("sheet_name", "")))] = row
    return index_map


def build_candidate_df(by_source_root: Path = BY_SOURCE_ROOT, index_path: Path = INDEX_PATH) -> pd.DataFrame:
    index_map = load_index_map(index_path)
    rows: list[dict[str, Any]] = []
    for path in sorted(by_source_root.glob("*.csv")):
        table_id = path.stem.split("__")[0]
        config = TABLE_ID_TO_CONFIG.get(table_id)
        if config is None:
            continue
        df = pd.read_csv(path, dtype=str, low_memory=False)
        columns = list(df.columns)
        column_map = detect_source_columns(columns)
        record_key_col = column_map.get("record_key")
        if record_key_col is None:
            continue
        sheet_name = str(df["sheet_name"].iloc[0]) if "sheet_name" in df.columns and len(df) else path.stem.split("__", 1)[-1]
        index_row = index_map.get((table_id, sheet_name), {})
        source_workbook_path = index_row.get("source_workbook_path", "")
        for row in df.to_dict("records"):
            patient_id_raw = nonempty(row.get(record_key_col))
            patient_id_norm = normalize_patient_id(patient_id_raw)
            if patient_id_norm is None:
                continue
            base = {
                "patient_uid": f"{config.dataset_key}::{patient_id_norm}",
                "patient_id_raw": patient_id_raw,
                "patient_id_norm": patient_id_norm,
                "dataset_key": config.dataset_key,
                "cohort": config.cohort,
                "hospital": config.hospital,
                "center": config.center,
                "year_group": config.year_group,
                "table_id": table_id,
                "sheet_name": row.get("sheet_name", sheet_name),
                "source_row_number": row.get("source_row_number", ""),
                "source_workbook_path": source_workbook_path,
                "source_uid": _source_uid(table_id, str(row.get("sheet_name", sheet_name)), row.get("source_row_number", "")),
                "source_row_json": json.dumps(
                    {
                        key: value
                        for key, value in row.items()
                        if key not in {"table_id", "cohort", "center", "year_group", "sheet_name", "source_row_number"}
                    },
                    ensure_ascii=False,
                ),
                "patient_name_raw": nonempty(row.get(column_map.get("patient_name"))) if column_map.get("patient_name") else None,
            }
            valid_count = 0
            for field in (*CLINICAL_FIELDS, *EXTRA_TEXT_FIELDS, *EXTRA_NUMERIC_FIELDS):
                value, raw_text, is_missing, parse_ok = _parse_field(field, row, column_map)
                base[field] = value
                base[f"{field}_raw_text"] = raw_text
                base[f"{field}_is_missing"] = int(is_missing)
                base[f"{field}_parse_ok"] = int(parse_ok)
                if field in CLINICAL_FIELDS and parse_ok:
                    valid_count += 1
            base["row_quality_score"] = valid_count
            rows.append(base)
    candidate_df = pd.DataFrame(rows)
    return candidate_df


def _aggregate_field(group: pd.DataFrame, field: str) -> dict[str, Any]:
    valid_mask = group[f"{field}_parse_ok"] == 1
    valid_group = group[valid_mask].copy()
    if not valid_group.empty:
        distinct_values = []
        for value in valid_group[field].tolist():
            if value not in distinct_values:
                distinct_values.append(value)
        best = valid_group.sort_values(
            by=["row_quality_score", "source_row_number"],
            ascending=[False, True],
        ).iloc[0]
        return {
            field: best[field],
            f"{field}_raw_text": best[f"{field}_raw_text"],
            f"{field}_source": best["source_uid"],
            f"{field}_is_missing": 0,
            f"{field}_parse_ok": 1,
            f"{field}_conflict": int(len(distinct_values) > 1),
            f"{field}_conflict_values": json.dumps(distinct_values, ensure_ascii=False),
        }

    raw_mask = group[f"{field}_raw_text"].notna()
    raw_group = group[raw_mask].copy()
    if not raw_group.empty:
        best = raw_group.sort_values(
            by=["row_quality_score", "source_row_number"],
            ascending=[False, True],
        ).iloc[0]
        return {
            field: None,
            f"{field}_raw_text": best[f"{field}_raw_text"],
            f"{field}_source": best["source_uid"],
            f"{field}_is_missing": 0,
            f"{field}_parse_ok": 0,
            f"{field}_conflict": 0,
            f"{field}_conflict_values": "[]",
        }

    return {
        field: None,
        f"{field}_raw_text": None,
        f"{field}_source": "",
        f"{field}_is_missing": 1,
        f"{field}_parse_ok": 0,
        f"{field}_conflict": 0,
        f"{field}_conflict_values": "[]",
    }


def aggregate_patient_master(candidate_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for patient_uid, group in candidate_df.groupby("patient_uid", sort=True):
        first = group.iloc[0]
        row: dict[str, Any] = {
            "patient_uid": patient_uid,
            "patient_id_raw": next((value for value in group["patient_id_raw"] if nonempty(value) is not None), first["patient_id_raw"]),
            "patient_id_norm": first["patient_id_norm"],
            "dataset_key": first["dataset_key"],
            "cohort": first["cohort"],
            "hospital": first["hospital"],
            "center": first["center"],
            "year_group": first["year_group"],
            "record_origin": "dataset_tables_patient_master",
            "candidate_row_count": int(len(group)),
            "max_row_quality_score": int(group["row_quality_score"].max()),
            "source_table_ids": unique_join(group["table_id"]),
            "source_sheets": unique_join(group["sheet_name"]),
            "source_workbook_paths": unique_join(group["source_workbook_path"]),
            "source_row_numbers": unique_join(group["source_row_number"]),
            "source_uids": unique_join(group["source_uid"]),
            "patient_name_raw": longest_text(group["patient_name_raw"]),
        }
        for field in (*CLINICAL_FIELDS, *EXTRA_TEXT_FIELDS, *EXTRA_NUMERIC_FIELDS):
            row.update(_aggregate_field(group, field))

        # Legacy aliases used by downstream toolkit scripts.
        row["tumor_long_diameter_cm"] = row["tumor_length_cm"]
        row["tumor_location_code"] = row["tumor_location"]
        row["cea_positive"] = row["cea_binary"]
        row["ca199_positive"] = row["ca199_binary"]
        row["lauren_code"] = row["lauren_type"]
        row["differentiation_code"] = row["differentiation"]

        clinical_missing_cols = [f"{field}_is_missing" for field in CLINICAL_FIELDS]
        row["has_clinical_data"] = int(any(int(row[col]) == 0 for col in clinical_missing_cols))
        row["has_pathology_data"] = int(row["pathology_text_is_missing"] == 0)
        rows.append(row)
    master_df = pd.DataFrame(rows).sort_values(
        by=["cohort", "hospital", "year_group", "patient_id_norm"]
    ).reset_index(drop=True)
    return master_df


def build_coverage_reports(master_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    overall_rows: list[dict[str, Any]] = []
    grouped_rows: list[dict[str, Any]] = []
    for field in CLINICAL_FIELDS:
        overall_rows.append(
            {
                "field": field,
                "tier": FIELD_SPEC_BY_NAME[field].tier,
                "rows": int(len(master_df)),
                "coverage": float((master_df[f"{field}_is_missing"] == 0).mean()) if len(master_df) else 0.0,
                "parse_success": float((master_df[f"{field}_parse_ok"] == 1).mean()) if len(master_df) else 0.0,
                "parse_failure_with_raw": float(
                    ((master_df[f"{field}_is_missing"] == 0) & (master_df[f"{field}_parse_ok"] == 0)).mean()
                )
                if len(master_df)
                else 0.0,
                "conflict_rate": float((master_df[f"{field}_conflict"] == 1).mean()) if len(master_df) else 0.0,
            }
        )
    for group_cols in (["cohort"], ["cohort", "center"], ["cohort", "center", "year_group"]):
        for keys, sub_df in master_df.groupby(group_cols, dropna=False, sort=True):
            if not isinstance(keys, tuple):
                keys = (keys,)
            key_map = dict(zip(group_cols, keys))
            for field in CLINICAL_FIELDS:
                grouped_rows.append(
                    {
                        **key_map,
                        "group_level": "+".join(group_cols),
                        "field": field,
                        "tier": FIELD_SPEC_BY_NAME[field].tier,
                        "rows": int(len(sub_df)),
                        "coverage": float((sub_df[f"{field}_is_missing"] == 0).mean()) if len(sub_df) else 0.0,
                        "parse_success": float((sub_df[f"{field}_parse_ok"] == 1).mean()) if len(sub_df) else 0.0,
                        "parse_failure_with_raw": float(
                            ((sub_df[f"{field}_is_missing"] == 0) & (sub_df[f"{field}_parse_ok"] == 0)).mean()
                        )
                        if len(sub_df)
                        else 0.0,
                        "conflict_rate": float((sub_df[f"{field}_conflict"] == 1).mean()) if len(sub_df) else 0.0,
                    }
                )
    return pd.DataFrame(overall_rows), pd.DataFrame(grouped_rows)


def write_master_outputs(
    master_df: pd.DataFrame,
    candidate_df: pd.DataFrame,
    output_root: Path = DATASET_TABLES_ROOT,
) -> dict[str, str]:
    output_root.mkdir(parents=True, exist_ok=True)
    master_path = output_root / MASTER_PATH.name
    candidate_path = output_root / CANDIDATE_PATH.name
    coverage_overall_path = output_root / COVERAGE_OVERALL_PATH.name
    coverage_by_group_path = output_root / COVERAGE_BY_GROUP_PATH.name
    schema_path = output_root / SCHEMA_PATH.name

    coverage_overall_df, coverage_by_group_df = build_coverage_reports(master_df)

    master_df.to_csv(master_path, index=False, encoding="utf-8-sig")
    candidate_df.to_csv(candidate_path, index=False, encoding="utf-8-sig")
    coverage_overall_df.to_csv(coverage_overall_path, index=False, encoding="utf-8-sig")
    coverage_by_group_df.to_csv(coverage_by_group_path, index=False, encoding="utf-8-sig")
    schema = {
        "clinical_fields": [
            {
                "name": spec.name,
                "kind": spec.kind,
                "tier": spec.tier,
                "max_code": spec.max_code,
            }
            for spec in CLINICAL_FIELD_SPECS
        ],
        "continuous_fields": CONTINUOUS_FIELDS,
        "categorical_fields": CATEGORICAL_FIELDS,
        "extra_text_fields": list(EXTRA_TEXT_FIELDS),
        "extra_numeric_fields": list(EXTRA_NUMERIC_FIELDS),
        "dataset_configs": [config.__dict__ for config in DATASET_CONFIGS],
    }
    schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "master_path": str(master_path),
        "candidate_path": str(candidate_path),
        "coverage_overall_path": str(coverage_overall_path),
        "coverage_by_group_path": str(coverage_by_group_path),
        "schema_path": str(schema_path),
    }


def build_and_write_patient_clinical_master(
    by_source_root: Path = BY_SOURCE_ROOT,
    index_path: Path = INDEX_PATH,
    output_root: Path = DATASET_TABLES_ROOT,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    candidate_df = build_candidate_df(by_source_root=by_source_root, index_path=index_path)
    master_df = aggregate_patient_master(candidate_df)
    paths = write_master_outputs(master_df, candidate_df, output_root=output_root)
    return master_df, candidate_df, paths


def load_patient_clinical_master(master_path: Path = MASTER_PATH) -> pd.DataFrame:
    return pd.read_csv(master_path, low_memory=False)


def ensure_patient_clinical_master(master_path: Path = MASTER_PATH) -> pd.DataFrame:
    if master_path.exists():
        return load_patient_clinical_master(master_path)
    master_df, _, _ = build_and_write_patient_clinical_master(output_root=master_path.parent)
    return master_df


def _match_master_row(
    row: pd.Series,
    master_index: dict[str, dict[str, Any]],
    pid_to_uids: dict[str, list[str]],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    image_stem = Path(str(row.get("image_path", ""))).stem
    pid_col = "patient_id_unique" if "patient_id_unique" in row.index else "patient_id"
    patient_id_norm = normalize_patient_id(row.get(pid_col))
    source_value = str(row.get("source", ""))
    candidates = list(resolve_split_dataset_candidates(source_value, image_stem))
    matched_uids = []
    if patient_id_norm is not None:
        for dataset_key in candidates:
            patient_uid = f"{dataset_key}::{patient_id_norm}"
            if patient_uid in master_index:
                matched_uids.append(patient_uid)
        if not matched_uids:
            fallback_uids = pid_to_uids.get(patient_id_norm, [])
            if len(fallback_uids) == 1:
                matched_uids = fallback_uids
    if len(matched_uids) == 1:
        uid = matched_uids[0]
        return master_index[uid], {
            "clinical_patient_uid": uid,
            "clinical_match_status": "matched",
            "clinical_match_candidates": json.dumps(candidates, ensure_ascii=False),
            "clinical_match_note": "",
        }
    if len(matched_uids) > 1:
        return None, {
            "clinical_patient_uid": "",
            "clinical_match_status": "ambiguous",
            "clinical_match_candidates": json.dumps(matched_uids, ensure_ascii=False),
            "clinical_match_note": "multiple_master_candidates",
        }
    return None, {
        "clinical_patient_uid": "",
        "clinical_match_status": "missing",
        "clinical_match_candidates": json.dumps(candidates, ensure_ascii=False),
        "clinical_match_note": "",
    }


def _coerce_feature_value(field: str, value: Any) -> float | int:
    if pd.isna(value):
        return -1.0 if field in CONTINUOUS_FIELDS else -1
    return float(value) if field in CONTINUOUS_FIELDS else int(value)


def _compute_norm_stats(train_df: pd.DataFrame) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for field in CONTINUOUS_FIELDS:
        valid = train_df[train_df[f"{field}_missing"] == 0][field]
        valid = pd.to_numeric(valid, errors="coerce").dropna()
        mean = float(valid.mean()) if len(valid) else 0.0
        std = float(valid.std()) if len(valid) else 0.0
        stats[field] = {"mean": mean, "std": std if std > 0 else 1.0}
    for spec in CLINICAL_FIELD_SPECS:
        if spec.kind == "categorical":
            stats[spec.name] = {"max_code": float(spec.max_code or 1)}
    return stats


def _apply_feature_contract(df: pd.DataFrame, norm_stats: dict[str, dict[str, float]]) -> pd.DataFrame:
    result = df.copy()
    for field in CONTINUOUS_FIELDS:
        valid_mask = result[f"{field}_missing"] == 0
        mean = norm_stats[field]["mean"]
        std = norm_stats[field]["std"]
        result[f"{field}_norm"] = np.where(
            valid_mask,
            (pd.to_numeric(result[field], errors="coerce") - mean) / std,
            0.0,
        )
    for field in CATEGORICAL_FIELDS:
        valid_mask = result[f"{field}_missing"] == 0
        max_code = norm_stats[field]["max_code"]
        result[f"{field}_norm"] = np.where(
            valid_mask,
            pd.to_numeric(result[field], errors="coerce") / max(max_code, 1.0),
            0.0,
        )
    return result


def generate_split_clinical_tables(
    data_dir: Path,
    master_df: pd.DataFrame,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    output_dir = output_dir or data_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    master_index = {
        str(row["patient_uid"]): row for row in master_df.to_dict("records")
    }
    pid_to_uids: dict[str, list[str]] = {}
    for row in master_df.to_dict("records"):
        pid_to_uids.setdefault(str(row["patient_id_norm"]), []).append(str(row["patient_uid"]))

    helper_stems = {
        "clinical_match_failures",
    }
    csv_paths = []
    for path in sorted(data_dir.glob("*.csv")):
        if path.stem.endswith("_clinical") or path.stem in helper_stems or path.stem.startswith("clinical_"):
            continue
        sample_df = pd.read_csv(path, nrows=1, low_memory=False)
        if "image_path" not in sample_df.columns or "patient_id" not in sample_df.columns:
            continue
        csv_paths.append(path)
    generated_frames: dict[str, pd.DataFrame] = {}
    unmatched_rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}

    for csv_path in csv_paths:
        df = pd.read_csv(csv_path, low_memory=False)
        feature_rows: list[dict[str, Any]] = []
        for row in df.to_dict("records"):
            row_series = pd.Series(row)
            master_row, match_meta = _match_master_row(row_series, master_index, pid_to_uids)
            merged = dict(row)
            merged.update(match_meta)
            if master_row is None:
                for field in CLINICAL_FIELDS:
                    merged[field] = -1.0 if field in CONTINUOUS_FIELDS else -1
                    merged[f"{field}_missing"] = 1
                unmatched_rows.append(
                    {
                        "csv_file": csv_path.name,
                        "image_path": row.get("image_path", ""),
                        "patient_id": row.get("patient_id", ""),
                        "source": row.get("source", ""),
                        **match_meta,
                    }
                )
            else:
                for field in CLINICAL_FIELDS:
                    merged[field] = _coerce_feature_value(field, master_row.get(field))
                    merged[f"{field}_missing"] = int(master_row.get(f"{field}_is_missing", 1))
            feature_rows.append(merged)
        out_df = pd.DataFrame(feature_rows)
        generated_frames[csv_path.stem] = out_df
        summary[csv_path.stem] = {
            "rows": int(len(out_df)),
            "matched_rows": int((out_df["clinical_match_status"] == "matched").sum()),
            "ambiguous_rows": int((out_df["clinical_match_status"] == "ambiguous").sum()),
            "missing_rows": int((out_df["clinical_match_status"] == "missing").sum()),
        }

    if "train" not in generated_frames:
        raise FileNotFoundError(f"Expected train.csv under {data_dir}")
    norm_stats = _compute_norm_stats(generated_frames["train"])

    schema = {
        "clinical_fields": [
            {
                "name": spec.name,
                "kind": spec.kind,
                "tier": spec.tier,
                "max_code": spec.max_code,
            }
            for spec in CLINICAL_FIELD_SPECS
        ],
        "continuous_fields": CONTINUOUS_FIELDS,
        "categorical_fields": CATEGORICAL_FIELDS,
        "norm_stats_source": "train_clinical.csv",
    }
    (output_dir / "clinical_schema.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "clinical_norm_stats.json").write_text(
        json.dumps(norm_stats, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for stem, frame in generated_frames.items():
        out_df = _apply_feature_contract(frame, norm_stats)
        out_df.to_csv(output_dir / f"{stem}_clinical.csv", index=False)

    unmatched_df = pd.DataFrame(unmatched_rows)
    unmatched_df.to_csv(output_dir / "clinical_match_failures.csv", index=False, encoding="utf-8-sig")
    (output_dir / "clinical_generation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary
