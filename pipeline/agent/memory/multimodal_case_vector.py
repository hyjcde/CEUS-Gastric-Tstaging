"""
Multimodal case vector for Agent memory / similarity retrieval.

Medical rationale (经腹超声 T 分期):
  - T2/T3/T4+ discrimination depends on **wall-layer invasion pattern**, not global brightness.
  - Similar cases should match on: wall-band / outward depth / breakthrough side, then morphology,
    then clinical covariates (location, differentiation), then classifier logits (weak prior).

Block layout (28 dims, backward-compatible legacy 17-dim prefix):

  [0:4]   classification probabilities (T1..T4+)
  [4:9]   morphology (convexity, solidity, irregularity, compactness, area_ratio)
  [9:17]  clinical (normalized age, sex, location, size, CEA, CA199, differentiation)
  [17:24] wall evidence (penetration risk, SDF depths, contact arc, lumen ratio)
  [24:28] boundary signals (adjacent-stage mass, entropy, margin gap, wall×T3 interaction)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .feature_extractor import (
    AGE_MEAN,
    AGE_STD,
    LENGTH_MEAN,
    LENGTH_STD,
    THICKNESS_MEAN,
    THICKNESS_STD,
    VECTOR_DIM as LEGACY_VECTOR_DIM,
    _norm,
)

VECTOR_DIM = 28

BLOCK_SLICES: Dict[str, Tuple[int, int]] = {
    "classification": (0, 4),
    "morphology": (4, 9),
    "clinical": (9, 17),
    "wall": (17, 24),
    "boundary": (24, 28),
}

# Weights tuned for T-boundary retrieval (sum ≈ 1.0). Wall + boundary dominate.
DEFAULT_BLOCK_WEIGHTS: Dict[str, float] = {
    "classification": 0.12,
    "morphology": 0.13,
    "clinical": 0.10,
    "wall": 0.40,
    "boundary": 0.25,
}


@dataclass(frozen=True)
class CaseVectorBundle:
    legacy: np.ndarray
    extended: np.ndarray
    blocks: Dict[str, np.ndarray]
    metadata: Dict[str, Any]


def _risk_to_float(risk: Optional[str]) -> float:
    mapping = {"low": 0.0, "medium": 0.55, "high": 1.0}
    return mapping.get(str(risk or "low").strip().lower(), 0.0)


def _clip_norm(value: float, scale: float = 1.0) -> float:
    if scale <= 0:
        return 0.0
    return float(np.clip(value / scale, 0.0, 1.0))


def extract_multimodal_case_vector(
    cls_results: List[Dict[str, Any]],
    morph_results: List[Dict[str, Any]],
    clinical_info: Optional[Dict[str, Any]] = None,
    wall_evidence: Optional[Dict[str, Any]] = None,
) -> CaseVectorBundle:
    """Build legacy (17) + extended (28) vectors from Agent tool outputs."""
    vec = np.zeros(VECTOR_DIM, dtype=np.float32)
    blocks: Dict[str, np.ndarray] = {}

    # ── classification ─────────────────────────────────────────────
    if cls_results:
        prob_sums = np.zeros(4, dtype=np.float32)
        n = 0
        for cr in cls_results:
            probs = cr.get("probabilities", {})
            if probs:
                prob_sums[0] += probs.get("T1", 0)
                prob_sums[1] += probs.get("T2", 0)
                prob_sums[2] += probs.get("T3", 0)
                prob_sums[3] += probs.get("T4+", 0)
                n += 1
        if n > 0:
            vec[0:4] = prob_sums / n
    blocks["classification"] = vec[0:4].copy()

    # ── morphology ───────────────────────────────────────────────
    morph_keys = [
        "convexity",
        "solidity",
        "boundary_irregularity",
        "compactness",
        "lesion_area_ratio",
    ]
    if morph_results:
        morph_sum = np.zeros(5, dtype=np.float32)
        n = 0
        for mr in morph_results:
            if mr.get("valid", False):
                for j, key in enumerate(morph_keys):
                    morph_sum[j] += float(mr.get(key, 0.0))
                n += 1
        if n > 0:
            vec[4:9] = morph_sum / n
    blocks["morphology"] = vec[4:9].copy()

    # ── clinical ───────────────────────────────────────────────────
    if clinical_info:
        vec[9] = _norm(clinical_info.get("age"), AGE_MEAN, AGE_STD)
        vec[10] = float(clinical_info.get("sex", 0) or 0)
        vec[11] = float(clinical_info.get("tumor_location", 0) or 0) / 3.0
        vec[12] = _norm(clinical_info.get("tumor_length_cm"), LENGTH_MEAN, LENGTH_STD)
        vec[13] = _norm(clinical_info.get("tumor_thickness_cm"), THICKNESS_MEAN, THICKNESS_STD)
        vec[14] = float(clinical_info.get("CEA_status", 0) or 0)
        vec[15] = float(clinical_info.get("CA199_status", 0) or 0)
        diff = clinical_info.get("differentiation")
        vec[16] = float(diff or 0) / 3.0
    blocks["clinical"] = vec[9:17].copy()

    # ── wall evidence (T2/T3 core) ─────────────────────────────────
    wall = np.zeros(7, dtype=np.float32)
    wall_evidence = wall_evidence or {}
    wf = wall_evidence.get("wall_features") or {}
    if wall_evidence.get("available"):
        wall[0] = _risk_to_float(wall_evidence.get("penetration_risk"))
        wall[1] = _clip_norm(float(wf.get("max_outward_depth", 0.0)), scale=80.0)
        wall[2] = _clip_norm(float(wf.get("mean_outward_depth", 0.0)), scale=40.0)
        wall[3] = float(wf.get("fraction_outside_lumen", 0.0))
        wall[4] = float(wf.get("contact_arc_ratio", 0.0))
        lumen_area = max(float(wf.get("lumen_area_px", 0.0)), 1.0)
        wall[5] = _clip_norm(float(wf.get("lesion_area_px", 0.0)) / lumen_area, scale=1.5)
        wall[6] = float(wf.get("fraction_inside_lumen", 0.0))
    vec[17:24] = wall
    blocks["wall"] = wall.copy()

    # ── boundary signals ───────────────────────────────────────────
    boundary = np.zeros(4, dtype=np.float32)
    p = vec[0:4]
    boundary[0] = float(p[1] + p[2])  # T2+T3 mass → T2/T3 boundary
    boundary[1] = float(p[2] + p[3])  # T3+T4+ mass → T3/T4+ boundary
    if cls_results:
        unc = [float(cr.get("uncertainty", 1.0)) for cr in cls_results if "uncertainty" in cr]
        if unc:
            boundary[2] = float(np.mean(unc))
        gaps = []
        for cr in cls_results:
            if cr.get("available"):
                gaps.append(float(cr.get("top1_prob", 0.0)) - float(cr.get("top2_prob", 0.0)))
        if gaps:
            boundary[3] = float(np.clip(1.0 - np.mean(gaps), 0.0, 1.0))
    boundary[3] = max(boundary[3], wall[0] * float(p[2]))  # high wall risk × T3 prob
    vec[24:28] = boundary
    blocks["boundary"] = boundary.copy()

    legacy = vec[:LEGACY_VECTOR_DIM].copy()
    meta = {
        "vector_dim": VECTOR_DIM,
        "legacy_dim": LEGACY_VECTOR_DIM,
        "has_wall": bool(wall_evidence.get("available")),
        "penetration_risk": wall_evidence.get("penetration_risk"),
    }
    return CaseVectorBundle(legacy=legacy, extended=vec, blocks=blocks, metadata=meta)
