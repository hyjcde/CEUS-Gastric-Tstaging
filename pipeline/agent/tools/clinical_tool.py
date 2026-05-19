"""
ClinicalTool — context-aware clinical risk assessment.

Goes beyond simple risk scoring: provides location-dependent staging-bias
alerts and ulceration-related calibration advice, so the LLM Agent can
reason like a clinician rather than follow a fixed checklist.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import BaseTool, ToolParameter

logger = logging.getLogger(__name__)

AGE_MEAN = 62.0
AGE_STD = 12.0

_LOCATION_BIAS: Dict[int, Dict[str, str]] = {
    0: {
        "name": "cardia",
        "eus_bias": "understage",
        "note": "Cardia tumours are technically difficult to stage with "
                "abdominal ultrasound due to oblique scanning angle. Classifier tends to "
                "understage. Consider upgrading if morphology is ambiguous.",
    },
    1: {
        "name": "upper_third/fundus",
        "eus_bias": "understage",
        "note": "Upper-third tumours are hard to visualise fully. "
                "Classifier may understage. If clinical features suggest "
                "advanced disease, consider upgrading.",
    },
    2: {
        "name": "body",
        "eus_bias": "neutral",
        "note": "Body tumours have the most reliable abdominal ultrasound staging accuracy. "
                "Trust the classifier unless conflicting evidence exists.",
    },
    3: {
        "name": "antrum/pylorus",
        "eus_bias": "overstage",
        "note": "Antral/pyloric tumours are prone to abdominal ultrasound OVERSTAGING "
                "because peri-tumour inflammation and fibrosis thicken the "
                "wall. If classifier says T3 but morphology is borderline, "
                "consider downgrading to T2.",
    },
}

_ULCER_ADVICE = {
    "ulcerative": (
        "Ulcerative gross type detected. IMPORTANT: peri-ulcer fibrosis "
        "and reactive inflammation cause abdominal ultrasound layer thickening that mimics "
        "deeper invasion. The classifier has a known OVERSTAGING bias for "
        "ulcerative tumours. If the classifier suggests T3 but the tumour "
        "is small (<3cm) with normal biomarkers, T2 is more likely."
    ),
    "elevated": (
        "Elevated/polypoid gross type. These tumours have well-defined "
        "borders on abdominal ultrasound, making staging more reliable. Trust the "
        "classifier output with higher confidence."
    ),
    "infiltrative": (
        "Infiltrative (Borrmann IV-like) gross type. These often show "
        "diffuse wall thickening without a clear mass. High risk of "
        "understaging — the true invasion may be deeper than abdominal ultrasound suggests."
    ),
}


class ClinicalTool(BaseTool):
    name = "clinical_risk"
    description = (
        "Analyse patient clinical features, compute risk score, and "
        "provide location-dependent staging calibration advice + "
        "ulceration adjustment guidance. Call this when the classifier "
        "is uncertain to get contextual clinical intelligence."
    )
    parameters = [
        ToolParameter("age", "int", "Patient age in years", required=False),
        ToolParameter("sex", "int", "0=female, 1=male", required=False),
        ToolParameter("tumor_location", "int",
                       "0=cardia, 1=upper, 2=body, 3=antrum", required=False),
        ToolParameter("tumor_length_cm", "float",
                       "Tumor length in cm", required=False),
        ToolParameter("tumor_thickness_cm", "float",
                       "Tumor thickness in cm", required=False),
        ToolParameter("CEA_status", "int",
                       "0=normal, 1=elevated", required=False),
        ToolParameter("CA199_status", "int",
                       "0=normal, 1=elevated", required=False),
        ToolParameter("differentiation", "int",
                       "1=well, 2=moderate, 3=poor, 4=undifferentiated",
                       required=False),
        ToolParameter("lauren_type", "int",
                       "1=intestinal, 2=diffuse, 3=mixed", required=False),
        ToolParameter("gross_type", "str",
                       "ulcerative / elevated / infiltrative (from pathology text)",
                       required=False),
    ]

    def execute(self, **kwargs) -> Dict[str, Any]:
        risk_factors: List[str] = []
        protective_factors: List[str] = []
        score = 0.0
        n_factors = 0

        # ── Age ────────────────────────────────────────────────────
        age = kwargs.get("age")
        if age is not None:
            if age >= 70:
                risk_factors.append(f"older_age ({age})")
                score += 0.6
            elif age >= 55:
                score += 0.3
            else:
                protective_factors.append(f"younger_age ({age})")
            n_factors += 1

        # ── Sex ────────────────────────────────────────────────────
        sex = kwargs.get("sex")
        if sex is not None:
            if sex == 1:
                risk_factors.append("male")
                score += 0.15
            n_factors += 1

        # ── Tumour size ────────────────────────────────────────────
        tumor_length = kwargs.get("tumor_length_cm")
        if tumor_length is not None:
            if tumor_length >= 5.0:
                risk_factors.append(f"large_tumor ({tumor_length}cm)")
                score += 0.7
            elif tumor_length >= 3.0:
                risk_factors.append(f"medium_tumor ({tumor_length}cm)")
                score += 0.4
            else:
                protective_factors.append(f"small_tumor ({tumor_length}cm)")
                score += 0.1
            n_factors += 1

        tumor_thickness = kwargs.get("tumor_thickness_cm")
        if tumor_thickness is not None:
            if tumor_thickness >= 1.5:
                risk_factors.append(f"thick_tumor ({tumor_thickness}cm)")
                score += 0.6
            elif tumor_thickness >= 0.8:
                score += 0.3
            else:
                protective_factors.append(
                    f"thin_tumor ({tumor_thickness}cm)")
            n_factors += 1

        # ── Biomarkers ─────────────────────────────────────────────
        cea = kwargs.get("CEA_status")
        if cea is not None:
            if cea == 1:
                risk_factors.append("elevated_CEA")
                score += 0.4
            else:
                protective_factors.append("normal_CEA")
            n_factors += 1

        ca199 = kwargs.get("CA199_status")
        if ca199 is not None:
            if ca199 == 1:
                risk_factors.append("elevated_CA199")
                score += 0.4
            else:
                protective_factors.append("normal_CA199")
            n_factors += 1

        # ── Differentiation ────────────────────────────────────────
        diff = kwargs.get("differentiation")
        if diff is not None:
            if diff >= 3:
                risk_factors.append("poorly_differentiated")
                score += 0.5
            elif diff == 2:
                score += 0.2
            else:
                protective_factors.append("well_differentiated")
            n_factors += 1

        # ── Lauren type ────────────────────────────────────────────
        lauren = kwargs.get("lauren_type")
        if lauren is not None:
            if lauren == 2:
                risk_factors.append("diffuse_lauren")
                score += 0.4
            elif lauren == 3:
                risk_factors.append("mixed_lauren")
                score += 0.3
            else:
                protective_factors.append("intestinal_lauren")
            n_factors += 1

        # ── Normalised risk score ──────────────────────────────────
        if n_factors > 0:
            clinical_risk_score = round(min(score / n_factors, 1.0), 3)
        else:
            clinical_risk_score = None

        # ── Location-dependent staging bias ────────────────────────
        location = kwargs.get("tumor_location")
        location_calibration = None
        if location is not None and location in _LOCATION_BIAS:
            location_calibration = _LOCATION_BIAS[location]

        # ── Ulceration / gross-type calibration ────────────────────
        gross_type = kwargs.get("gross_type")
        ulcer_calibration = None
        if gross_type and gross_type in _ULCER_ADVICE:
            ulcer_calibration = {
                "gross_type": gross_type,
                "advice": _ULCER_ADVICE[gross_type],
            }

        return {
            "clinical_risk_score": clinical_risk_score,
            "risk_factors": risk_factors,
            "protective_factors": protective_factors,
            "factors_available": n_factors,
            "location_calibration": location_calibration,
            "ulcer_calibration": ulcer_calibration,
        }
