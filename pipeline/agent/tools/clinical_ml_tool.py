"""Champion clinical tabular T-staging model (2026-09-15).

RandomForest (optuna-tuned, clin9_wb feature set) trained on the
region_contrastive_full train+val pool (n=1566 patients). Clean-set benchmark
(external n=381 / zml100 strict n=39): ACC 0.567 / 0.641, QWK 0.631 mean —
beats the imaging-only DINOv3 classifier (0.433 external) and the heuristic
clinical risk score it complements here.

Feature set ``clin9_wb`` = clin11 minus lauren/differentiation, because the
workbench never carries those as structured fields (they live in pathology
text). Encoding matches pipeline/data/tstaging_4class/clinical_norm_stats.json:
continuous z-score, categorical raw/max_code, missing -> norm 0.0 + flag 1.0.

Location coding follows the registry (source column 「超声位置分四类」):
0 = cardia+fundus, 1 = body+angle, 2 = antrum+pylorus, 3 = multi-site.
NOTE: this differs from clinical_vector._LOCATION_NAME_TO_CODE (legacy 4-way
anatomic coding) — do not reuse that map for this model.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from agent.core.repo_paths import PROJECT_ROOT

BUNDLE_DIR = PROJECT_ROOT / "pipeline" / "models" / "clinical_tstage_champion_20260915"

CLASSES = ("T1", "T2", "T3", "T4+")
# Feature order must match training (FEATS = CLIN9_WB + missing flags).
_NORM_ORDER = (
    "age", "sex", "tumor_length_cm", "tumor_thickness_cm", "tumor_location",
    "cea_value", "ca199_value", "cea_binary", "ca199_binary",
)
_CONTINUOUS = ("age", "tumor_length_cm", "tumor_thickness_cm", "cea_value", "ca199_value")
_CAT_SCALE = {"sex": 1.0, "tumor_location": 10.0, "cea_binary": 1.0, "ca199_binary": 1.0}

_SEX_TO_CODE = {
    "male": 1.0, "m": 1.0, "男": 1.0, "1": 1.0,
    "female": 0.0, "f": 0.0, "女": 0.0, "0": 0.0,
}
_LOCATION_TO_CODE = {
    "cardia/fundus": 0.0, "cardia": 0.0, "fundus": 0.0, "贲门": 0.0, "胃底": 0.0,
    "body/angle": 1.0, "body": 1.0, "胃体": 1.0, "胃角": 1.0,
    "antrum/pylorus": 2.0, "angle/antrum": 2.0, "antrum": 2.0, "胃窦": 2.0, "幽门": 2.0,
    "multiple sites": 3.0, "whole stomach": 3.0, "多部位": 3.0, "全胃": 3.0,
}


@lru_cache(maxsize=1)
def _load_bundle():
    import joblib

    model = joblib.load(BUNDLE_DIR / "model.joblib")
    transform = json.loads((BUNDLE_DIR / "transform.json").read_text(encoding="utf-8"))
    return model, transform


def _parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"nan", "na", "-", "unknown", "未知"}:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v == v else None  # NaN -> None


def _code_from_map(value: Any, mapping: Dict[str, float]) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        v = float(value)
        return v if v >= 0 else None
    text = str(value).strip()
    if not text:
        return None
    if text in mapping:
        return mapping[text]
    lowered = text.lower()
    if lowered in mapping:
        return mapping[lowered]
    return None


def build_feature_vector(clinical: Dict[str, Any]) -> tuple[list[float], int]:
    """Map the Next ``mapClinicalToAgentInput`` payload to the 18-dim vector.

    Returns (features, n_present).
    """
    _, transform = _load_bundle()
    cont_stats = transform["continuous"]

    size = clinical.get("tumorSize") or clinical.get("tumor_size") or {}
    if not isinstance(size, dict):
        size = {}
    biomarkers = clinical.get("biomarkers") or {}
    if not isinstance(biomarkers, dict):
        biomarkers = {}

    raw: Dict[str, Any] = {
        "age": clinical.get("age"),
        "sex": clinical.get("sex"),
        "tumor_length_cm": size.get("length", clinical.get("tumor_length_cm")),
        "tumor_thickness_cm": size.get("thickness", clinical.get("tumor_thickness_cm")),
        "tumor_location": clinical.get("location", clinical.get("tumor_location")),
        "cea_value": biomarkers.get("cea", clinical.get("cea_value")),
        "ca199_value": biomarkers.get("ca199", clinical.get("ca199_value")),
        "cea_binary": biomarkers.get("cea_positive", clinical.get("cea_binary")),
        "ca199_binary": biomarkers.get("ca199_positive", clinical.get("ca199_binary")),
    }

    norms: list[float] = []
    missings: list[float] = []
    n_present = 0
    for field in _NORM_ORDER:
        value = raw.get(field)
        if field in _CONTINUOUS:
            parsed = _parse_float(value)
            present = parsed is not None and parsed >= 0
            if present:
                stats = cont_stats[field]
                norms.append((parsed - stats["mean"]) / (stats["std"] or 1.0))
            else:
                norms.append(0.0)
        elif field == "sex":
            code = _code_from_map(value, _SEX_TO_CODE)
            present = code is not None
            norms.append(code / _CAT_SCALE[field] if present else 0.0)
        elif field == "tumor_location":
            code = _code_from_map(value, _LOCATION_TO_CODE)
            present = code is not None
            norms.append(code / _CAT_SCALE[field] if present else 0.0)
        else:  # binary flags
            if isinstance(value, bool):
                parsed = 1.0 if value else 0.0
            else:
                parsed = _parse_float(value)
            present = parsed is not None and parsed >= 0
            norms.append(float(parsed) if present else 0.0)
        missings.append(0.0 if present else 1.0)
        if present:
            n_present += 1
    return norms + missings, n_present


def predict_clinical_tstage(clinical: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return 4-class T-stage probabilities from the clinical table alone."""
    if not clinical or not isinstance(clinical, dict):
        return {"available": False, "reason": "no_clinical_payload"}
    try:
        model, _ = _load_bundle()
    except Exception as exc:  # bundle missing / load failure — never break analysis
        return {"available": False, "reason": f"bundle_unavailable: {exc}"}

    feats, n_present = build_feature_vector(clinical)
    if n_present < 4:
        return {"available": False, "reason": f"too_few_fields ({n_present}/9)"}

    import numpy as np

    proba = model.predict_proba(np.array([feats], dtype=np.float32))[0]
    probabilities = {stage: float(p) for stage, p in zip(CLASSES, proba)}
    top_idx = int(np.argmax(proba))
    return {
        "available": True,
        "model": "rf_tuned_clin9_wb_20260915",
        "n_fields_present": n_present,
        "probabilities": probabilities,
        "top1_stage": CLASSES[top_idx],
        "top1_prob": float(proba[top_idx]),
    }
