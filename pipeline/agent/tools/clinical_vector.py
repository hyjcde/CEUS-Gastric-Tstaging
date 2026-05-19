"""
Build the 22-d clinical vector used by mask4ch + clinical22 classifiers.

Matches columns in pipeline/data/tstaging_4class/*_clinical.csv and
config.json ``clinical_cols`` (value + missing pairs).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from ..core.repo_paths import PROJECT_ROOT

PIPELINE_DATA = PROJECT_ROOT / "pipeline" / "data" / "tstaging_4class"
NORM_STATS_PATH = PIPELINE_DATA / "clinical_norm_stats.json"
SCHEMA_PATH = PIPELINE_DATA / "clinical_schema.json"

CONTINUOUS_FIELDS = (
    "age",
    "tumor_length_cm",
    "tumor_thickness_cm",
    "cea_value",
    "ca199_value",
)
CATEGORICAL_FIELDS = (
    "sex",
    "lauren_type",
    "differentiation",
    "tumor_location",
    "cea_binary",
    "ca199_binary",
)
ALL_FIELDS = CONTINUOUS_FIELDS + CATEGORICAL_FIELDS

_LOCATION_NAME_TO_CODE = {
    "cardia": 0,
    "贲门": 0,
    "upper": 1,
    "fundus": 1,
    "胃底": 1,
    "body": 2,
    "胃体": 2,
    "antrum": 3,
    "pylorus": 3,
    "幽门": 3,
    "窦": 3,
}


def normalize_frontend_clinical(clinical: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Map Next.js ``mapClinicalToAgentInput`` payload to training field names."""
    if not clinical:
        return {}

    out: Dict[str, Any] = {}
    if clinical.get("age") is not None:
        out["age"] = clinical.get("age")

    sex = clinical.get("sex")
    if isinstance(sex, str):
        sex_lc = sex.strip().lower()
        if sex_lc in {"男", "male", "m", "1"}:
            out["sex"] = 1
        elif sex_lc in {"女", "female", "f", "0"}:
            out["sex"] = 0
    elif sex is not None:
        out["sex"] = sex

    location = clinical.get("location") or clinical.get("tumor_location")
    if isinstance(location, int):
        out["tumor_location"] = location
    elif isinstance(location, str) and location.strip():
        loc_lc = location.strip().lower()
        for key, code in _LOCATION_NAME_TO_CODE.items():
            if key in loc_lc:
                out["tumor_location"] = code
                break

    tumor_size = clinical.get("tumorSize") or clinical.get("tumor_size") or {}
    if isinstance(tumor_size, dict):
        if tumor_size.get("length") is not None:
            out["tumor_length_cm"] = tumor_size.get("length")
        if tumor_size.get("thickness") is not None:
            out["tumor_thickness_cm"] = tumor_size.get("thickness")

    biomarkers = clinical.get("biomarkers") or {}
    if isinstance(biomarkers, dict):
        if biomarkers.get("cea") is not None:
            out["CEA_value"] = biomarkers.get("cea")
        if biomarkers.get("cea_positive") is not None:
            out["CEA_status"] = int(bool(biomarkers.get("cea_positive")))
        if biomarkers.get("ca199") is not None:
            out["CA199_value"] = biomarkers.get("ca199")
        if biomarkers.get("ca199_positive") is not None:
            out["CA199_status"] = int(bool(biomarkers.get("ca199_positive")))

    if clinical.get("differentiation") not in (None, ""):
        out["differentiation"] = clinical.get("differentiation")
    if clinical.get("lauren") not in (None, ""):
        out["lauren_type"] = clinical.get("lauren")

    return out


def _load_norm_stats() -> Dict[str, Dict[str, float]]:
    if NORM_STATS_PATH.exists():
        return json.loads(NORM_STATS_PATH.read_text(encoding="utf-8"))
    return {}


def _parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().replace("/", "")
        if not text or text.lower() in {"nan", "na", "-", "未知"}:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value: Any) -> Optional[int]:
    parsed = _parse_float(value)
    if parsed is None:
        return None
    return int(parsed)


def _encode_field(
    field: str,
    raw_value: Any,
    *,
    norm_stats: Dict[str, Dict[str, float]],
) -> tuple[float, int, float]:
    """Return (raw_storage, missing_flag, norm_value)."""
    if field in CONTINUOUS_FIELDS:
        val = _parse_float(raw_value)
        if val is None or val < 0:
            return -1.0, 1, 0.0
        stats = norm_stats.get(field, {"mean": 0.0, "std": 1.0})
        std = stats.get("std", 1.0) or 1.0
        norm = (val - stats.get("mean", 0.0)) / std
        return float(val), 0, float(norm)

    val = _parse_int(raw_value)
    if val is None or val < 0:
        return -1.0, 1, 0.0
    max_code = norm_stats.get(field, {}).get("max_code", 1.0) or 1.0
    return float(val), 0, float(val) / max(max_code, 1.0)


def _row_to_feature_dict(row: Dict[str, Any]) -> Dict[str, float]:
    """Read precomputed *_norm / *_missing columns from a clinical CSV row."""
    out: Dict[str, float] = {}
    for col in row:
        if col.endswith("_norm") or col.endswith("_missing"):
            try:
                out[col] = float(row[col])
            except (TypeError, ValueError):
                out[col] = 0.0
    return out


def encode_clinical_payload(
    clinical: Dict[str, Any],
    *,
    norm_stats: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, float]:
    """Encode agent ``clinical`` payload (whitelist fields) to norm/missing columns."""
    norm_stats = norm_stats or _load_norm_stats()
    features: Dict[str, float] = {}

    field_map = {
        "age": clinical.get("age"),
        "sex": clinical.get("sex"),
        "lauren_type": clinical.get("lauren_type"),
        "differentiation": clinical.get("differentiation"),
        "tumor_length_cm": clinical.get("tumor_length_cm"),
        "tumor_thickness_cm": clinical.get("tumor_thickness_cm"),
        "tumor_location": clinical.get("tumor_location"),
        "cea_value": clinical.get("CEA_value") or clinical.get("cea_value"),
        "cea_binary": clinical.get("CEA_status") or clinical.get("cea_binary"),
        "ca199_value": clinical.get("CA199_value") or clinical.get("ca199_value"),
        "ca199_binary": clinical.get("CA199_status") or clinical.get("ca199_binary"),
    }

    for field in ALL_FIELDS:
        raw, missing, norm = _encode_field(field, field_map.get(field), norm_stats=norm_stats)
        features[field] = raw
        features[f"{field}_missing"] = float(missing)
        features[f"{field}_norm"] = norm

    return features


def vector_from_feature_dict(
    feature_dict: Dict[str, float],
    clinical_cols: Sequence[str],
) -> List[float]:
    values: List[float] = []
    for col in clinical_cols:
        values.append(float(feature_dict.get(col, 0.0)))
    return values


@lru_cache(maxsize=8)
def _load_clinical_table(csv_name: str) -> pd.DataFrame:
    path = PIPELINE_DATA / csv_name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def lookup_clinical_row(
    *,
    patient_id: Optional[str] = None,
    image_path: Optional[str] = None,
    split_hint: str = "test_prospective",
) -> Optional[Dict[str, float]]:
    """Find precomputed clinical22 columns for a patient or image."""
    candidates = [
        f"{split_hint}_clinical.csv",
        "test_prospective_clinical.csv",
        "train_clinical.csv",
        "val_clinical.csv",
    ]
    seen: set[str] = set()
    for name in candidates:
        if name in seen:
            continue
        seen.add(name)
        df = _load_clinical_table(name)
        if df.empty:
            continue
        if image_path and "image_path" in df.columns:
            rel = str(image_path).replace(str(PROJECT_ROOT) + "/", "")
            hits = df[df["image_path"].astype(str) == rel]
            if hits.empty:
                hits = df[df["image_path"].astype(str).str.endswith(Path(image_path).name)]
            if not hits.empty:
                return _row_to_feature_dict(hits.iloc[0].to_dict())
        if patient_id is not None and "patient_id" in df.columns:
            hits = df[df["patient_id"].astype(str) == str(patient_id)]
            if not hits.empty:
                return _row_to_feature_dict(hits.iloc[0].to_dict())
    return None


def resolve_clinical22_vector(
    *,
    clinical_cols: Sequence[str],
    payload_clinical: Optional[Dict[str, Any]] = None,
    patient_id: Optional[str] = None,
    image_path: Optional[str] = None,
    split_hint: str = "test_prospective",
) -> tuple[List[float], str]:
    """
    Returns (vector, source_tag).

    source_tag: csv_lookup | payload_encoded | zeros_missing
    """
    if not clinical_cols:
        return [], "none"

    row = lookup_clinical_row(
        patient_id=patient_id,
        image_path=image_path,
        split_hint=split_hint,
    )
    if row:
        return vector_from_feature_dict(row, clinical_cols), "csv_lookup"

    normalized = normalize_frontend_clinical(payload_clinical)
    if normalized:
        encoded = encode_clinical_payload(normalized)
        return vector_from_feature_dict(encoded, clinical_cols), "payload_encoded"

    zeros = {col: 0.0 for col in clinical_cols}
    for field in ALL_FIELDS:
        zeros[f"{field}_missing"] = 1.0
        zeros[f"{field}_norm"] = 0.0
        zeros[field] = -1.0
    return vector_from_feature_dict(zeros, clinical_cols), "zeros_missing"


def clinical_vector_for_classifier(
    cfg: Dict[str, Any],
    *,
    payload_clinical: Optional[Dict[str, Any]] = None,
    patient_id: Optional[str] = None,
    image_path: Optional[str] = None,
    split_hint: str = "test_prospective",
) -> Optional[Dict[str, Any]]:
    """Return dict suitable for ClassificationTool (clinical_vector + metadata)."""
    clinical_cols = cfg.get("clinical_cols") or []
    clinical_dim = int(cfg.get("clinical_dim", 0) or 0)
    if clinical_dim <= 0 or not clinical_cols:
        return None

    vector, source = resolve_clinical22_vector(
        clinical_cols=clinical_cols,
        payload_clinical=payload_clinical,
        patient_id=patient_id,
        image_path=image_path,
        split_hint=split_hint,
    )
    return {
        "clinical_vector": vector,
        "clinical_vector_source": source,
        "clinical_dim": clinical_dim,
    }
