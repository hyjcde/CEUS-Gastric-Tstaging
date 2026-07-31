"""
Baseline methods for comparing against the Agent.

Baseline-Single: per-frame argmax (patient = most common frame prediction)
Baseline-Avg:    average frame probabilities, then argmax
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

CLASS_NAMES = ["T1", "T2", "T3", "T4+"]


def baseline_single_frame_argmax(
    cls_results_per_frame: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Baseline-Single: take the argmax of each frame independently,
    then majority-vote across frames.
    """
    if not cls_results_per_frame:
        return {"predicted_stage": None, "method": "baseline_single"}

    votes = []
    for cr in cls_results_per_frame:
        probs = cr.get("probabilities", {})
        if probs:
            top = max(probs, key=probs.get)
            votes.append(top)

    if not votes:
        return {"predicted_stage": None, "method": "baseline_single"}

    counter = Counter(votes)
    predicted = counter.most_common(1)[0][0]

    return {
        "predicted_stage": predicted,
        "method": "baseline_single",
        "frame_votes": dict(counter),
        "agreement_rate": counter.most_common(1)[0][1] / len(votes),
    }


def baseline_average(
    cls_results_per_frame: List[Dict[str, Any]],
    quality_scores: Optional[List[float]] = None,
    use_quality_weights: bool = False,
) -> Dict[str, Any]:
    """
    Baseline-Avg: average all frame probabilities (optionally quality-weighted),
    then argmax.
    """
    if not cls_results_per_frame:
        return {"predicted_stage": None, "method": "baseline_avg"}

    prob_arrays = []
    weights = []
    for i, cr in enumerate(cls_results_per_frame):
        probs = cr.get("probabilities", {})
        if probs:
            arr = np.array([probs.get(c, 0.0) for c in CLASS_NAMES],
                            dtype=np.float32)
            prob_arrays.append(arr)
            if use_quality_weights and quality_scores and i < len(quality_scores):
                weights.append(quality_scores[i])
            else:
                weights.append(1.0)

    if not prob_arrays:
        return {"predicted_stage": None, "method": "baseline_avg"}

    weights = np.array(weights, dtype=np.float32)
    total_w = weights.sum()
    if total_w == 0:
        total_w = 1.0

    avg_probs = sum(w * p for w, p in zip(weights, prob_arrays)) / total_w
    predicted_idx = int(np.argmax(avg_probs))

    return {
        "predicted_stage": CLASS_NAMES[predicted_idx],
        "method": "baseline_avg" + ("_qw" if use_quality_weights else ""),
        "averaged_probs": {CLASS_NAMES[i]: round(float(avg_probs[i]), 4)
                            for i in range(len(CLASS_NAMES))},
    }


def run_baselines_for_patient(
    cls_results_per_frame: List[Dict[str, Any]],
    quality_scores: Optional[List[float]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Run all baseline methods for one patient, return dict keyed by method."""
    return {
        "baseline_single": baseline_single_frame_argmax(cls_results_per_frame),
        "baseline_avg": baseline_average(cls_results_per_frame),
        "baseline_avg_qw": baseline_average(
            cls_results_per_frame, quality_scores, use_quality_weights=True),
    }
