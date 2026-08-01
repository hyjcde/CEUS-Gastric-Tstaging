"""Shared pre-model visual keyframe selection for Agent and Next runtime."""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np


def normalize_scores(values: Sequence[float]) -> list[float]:
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return []
    lo = float(arr.min())
    hi = float(arr.max())
    if np.isclose(lo, hi):
        return [1.0] * len(arr)
    return [float(value) for value in (arr - lo) / (hi - lo)]


def score_visual_quality(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score clarity and exposure; motion is metadata, not a quality reward."""
    if not rows:
        return []
    sharpness = normalize_scores([float(row.get("sharpness") or 0.0) for row in rows])
    contrast = normalize_scores([float(row.get("contrast") or 0.0) for row in rows])
    brightness_balance = [
        1.0 - min(abs(float(row.get("brightness") or 110.0) - 110.0) / 110.0, 1.0)
        for row in rows
    ]
    scored: list[dict[str, Any]] = []
    for row, sharp_n, contrast_n, brightness_n in zip(
        rows, sharpness, contrast, brightness_balance
    ):
        item = dict(row)
        score = 0.60 * sharp_n + 0.25 * contrast_n + 0.15 * brightness_n
        item["quality_score"] = round(float(score), 6)
        item["quality_components"] = {
            "sharpness": round(float(sharp_n), 6),
            "contrast": round(float(contrast_n), 6),
            "brightness_balance": round(float(brightness_n), 6),
        }
        scored.append(item)
    return scored


def temporal_diverse_topk(
    rows: Sequence[dict[str, Any]],
    *,
    n_key: int,
    min_gap: int,
) -> list[dict[str, Any]]:
    if not rows:
        return []
    ranked = sorted(rows, key=lambda row: float(row.get("quality_score") or 0.0), reverse=True)
    chosen: list[dict[str, Any]] = []
    for row in ranked:
        frame_index = int(row.get("frame_index", 0))
        if all(abs(frame_index - int(item.get("frame_index", 0))) >= min_gap for item in chosen):
            chosen.append(row)
        if len(chosen) >= n_key:
            break
    if len(chosen) < n_key:
        for row in ranked:
            if row not in chosen:
                chosen.append(row)
            if len(chosen) >= n_key:
                break
    return sorted(chosen, key=lambda row: int(row.get("frame_index", 0)))


def select_visual_keyframes(
    rows: Sequence[dict[str, Any]],
    *,
    n_key: int = 4,
    min_gap: int = 2,
) -> list[dict[str, Any]]:
    scored = score_visual_quality(rows)
    if not scored:
        return []
    return temporal_diverse_topk(
        scored,
        n_key=max(int(n_key), 1),
        min_gap=max(int(min_gap), 1),
    )
