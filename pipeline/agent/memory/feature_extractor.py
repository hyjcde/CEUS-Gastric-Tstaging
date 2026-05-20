"""
Feature extractor for building patient-level case vectors.

Runs classification + morphology + clinical tools on each patient and
concatenates the outputs into a fixed-dimension vector for FAISS indexing.

Vector layout (17 dims):
  [0:4]   classification probabilities (T1, T2, T3, T4+)
  [4:9]   morphology (convexity, solidity, irregularity, compactness, area_ratio)
  [9:17]  clinical (age_norm, sex, location, length_norm, thickness_norm,
                     CEA, CA199, differentiation_norm)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

VECTOR_DIM = 17

# Normalisation constants for clinical features
AGE_MEAN, AGE_STD = 62.0, 12.0
LENGTH_MEAN, LENGTH_STD = 4.0, 2.5
THICKNESS_MEAN, THICKNESS_STD = 1.0, 0.8


def _norm(val: Optional[float], mean: float, std: float) -> float:
    if val is None:
        return 0.0
    return (val - mean) / std


def extract_patient_vector(
    cls_results: List[Dict[str, Any]],
    morph_results: List[Dict[str, Any]],
    clinical_info: Optional[Dict[str, Any]] = None,
    wall_evidence: Optional[Dict[str, Any]] = None,
) -> np.ndarray:
    """
    Build patient vector for case memory / similarity retrieval.

    Returns extended 28-d when wall_evidence is available; otherwise legacy 17-d prefix.
    """
    from .multimodal_case_vector import extract_multimodal_case_vector

    bundle = extract_multimodal_case_vector(
        cls_results=cls_results,
        morph_results=morph_results,
        clinical_info=clinical_info,
        wall_evidence=wall_evidence,
    )
    if wall_evidence and wall_evidence.get("available"):
        return bundle.extended
    return bundle.legacy


def build_key_features_summary(
    cls_results: List[Dict[str, Any]],
    morph_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Create a compact summary for case metadata (stored alongside FAISS)."""
    summary: Dict[str, Any] = {}

    if cls_results:
        # Average probabilities
        probs = {}
        n = 0
        for cr in cls_results:
            p = cr.get("probabilities", {})
            if p:
                for k, v in p.items():
                    probs[k] = probs.get(k, 0.0) + v
                n += 1
        if n > 0:
            probs = {k: round(v / n, 4) for k, v in probs.items()}
            summary["avg_probabilities"] = probs
            sorted_stages = sorted(probs.items(), key=lambda x: -x[1])
            summary["top1_stage"] = sorted_stages[0][0]

        # Average uncertainty
        uncertainties = [cr.get("uncertainty", 1.0) for cr in cls_results
                          if "uncertainty" in cr]
        if uncertainties:
            summary["avg_uncertainty"] = round(
                sum(uncertainties) / len(uncertainties), 4)

    if morph_results:
        valid_morph = [m for m in morph_results if m.get("valid", False)]
        if valid_morph:
            summary["avg_convexity"] = round(
                sum(m.get("convexity", 0) for m in valid_morph) / len(valid_morph), 4)
            summary["avg_irregularity"] = round(
                sum(m.get("boundary_irregularity", 0) for m in valid_morph)
                / len(valid_morph), 4)

    return summary
