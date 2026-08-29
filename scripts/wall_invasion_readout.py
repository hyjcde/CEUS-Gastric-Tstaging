#!/usr/bin/env python3
"""Single-frame wall-layer invasion readout.

The doctor heading is a search prior, not a continuity answer.
This module does not output a cT. Image-not-visible is not serosal invasion.

Protocol words (2026-08-28):
  continuous / suspected_interrupt / interrupted / cannot_judge
Two extra geometry states that are not interrupt:
  displaced = the outer echo still follows the lesion rim
  fused = this layer's gray meets the lesion interior

One frame can only raise suspected_interrupt. Hard interrupted needs
matching evidence on a second nearby frame, which this offline bag
does not have yet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

FUSE_GRAY_TOL = 18.0
SINGLE_FRAME_CONF_CAP = 0.62

VERDICT_ZH = {
    "continuous": "连续",
    "suspected_interrupt": "疑似中断",
    "interrupted": "中断",
    "cannot_judge": "无法判断",
    "displaced": "受压绕行",
    "fused": "与灶融合",
    "missing": "未检出",
}

# Figure / region chips reuse the older short labels.
VERDICT_TO_REGION = {
    "continuous": "visible",
    "suspected_interrupt": "interrupted",
    "interrupted": "interrupted",
    "cannot_judge": "obscured",
    "displaced": "displaced",
    "fused": "fused",
    "missing": "missing",
}


@dataclass
class LayerInvasion:
    id: str
    name_zh: str
    verdict: str
    verdict_zh: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "verdict": self.verdict,
            "verdict_zh": self.verdict_zh,
            "confidence": round(float(self.confidence), 3),
            "evidence": list(self.evidence),
            "note": self.note,
        }


def _item(layer_id: str, name_zh: str, verdict: str, confidence: float, evidence: list[str], note: str = "") -> LayerInvasion:
    conf = min(float(confidence), SINGLE_FRAME_CONF_CAP)
    return LayerInvasion(
        id=layer_id,
        name_zh=name_zh,
        verdict=verdict,
        verdict_zh=VERDICT_ZH.get(verdict, verdict),
        confidence=conf,
        evidence=evidence,
        note=note,
    )


def _near_lesion_gray(mid_gray: float | None, lesion_gray: float | None) -> bool:
    if mid_gray is None or lesion_gray is None:
        return False
    return abs(float(mid_gray) - float(lesion_gray)) <= FUSE_GRAY_TOL


def analyze_invasion(
    *,
    inner_n: int,
    outer_n: int,
    path_meets_lesion: bool,
    wrapped: bool,
    wrap_steps: int,
    mid_gray: float | None,
    lesion_gray: float | None,
    outer_stop_gray: float | None,
    single_frame: bool = True,
) -> list[LayerInvasion]:
    """Judge each layer from the tracked lines. Not a T stage."""
    fused_mid = _near_lesion_gray(mid_gray, lesion_gray)
    stop_looks_lesion = _near_lesion_gray(outer_stop_gray, lesion_gray)
    has_flank = inner_n >= 6 and outer_n >= 6

    # Mucosa: shallow band on the clear flank. Fusion at the tip is a muscularis question.
    if inner_n >= 6:
        mucosa = _item("mucosa", "黏膜复合层", "continuous", 0.58, ["inner_edge_on_flank"])
    elif inner_n > 0:
        mucosa = _item("mucosa", "黏膜复合层", "cannot_judge", 0.35, ["short_inner_edge"])
    else:
        mucosa = _item("mucosa", "黏膜复合层", "missing", 0.20, ["no_inner_edge"])

    # Muscularis: the dark band between the two lines.
    if fused_mid and path_meets_lesion:
        muscularis = _item(
            "muscularis", "固有肌层", "fused", 0.60,
            ["mid_band_gray_meets_lesion"],
            "The dark band and the lesion share gray. Do not paint the whole mass as muscle.",
        )
    elif has_flank and not fused_mid:
        muscularis = _item("muscularis", "固有肌层", "continuous", 0.56, ["dark_band_on_flank"])
    elif inner_n + outer_n > 0:
        muscularis = _item("muscularis", "固有肌层", "cannot_judge", 0.34, ["weak_mid_band"])
    else:
        muscularis = _item("muscularis", "固有肌层", "missing", 0.20, ["no_mid_band"])

    # Serosa: the T3/T4-relevant outer line. One frame cannot confirm interrupt.
    if wrapped and wrap_steps >= 8:
        serosa = _item(
            "serosa", "浆膜侧", "displaced", 0.60,
            ["outer_echo_follows_rim", f"wrap_steps={wrap_steps}"],
            "The outer echo is still there, pushed around the rim. That is not interrupt.",
        )
    elif path_meets_lesion and has_flank and not wrapped and (stop_looks_lesion or outer_n < 4):
        evidence = ["path_meets_lesion", "no_outer_wrap"]
        if stop_looks_lesion:
            evidence.append("stop_gray_meets_lesion")
        if single_frame:
            serosa = _item(
                "serosa", "浆膜侧", "suspected_interrupt", 0.48, evidence,
                "One frame only. A missing line here is not serosal invasion.",
            )
        else:
            serosa = _item(
                "serosa", "浆膜侧", "interrupted", 0.55, evidence + ["multi_frame"],
                "Still not a cT. Needs the doctor lock.",
            )
    elif outer_n >= 6:
        serosa = _item("serosa", "浆膜侧", "continuous", 0.55, ["outer_edge_on_flank"])
    elif outer_n > 0:
        serosa = _item("serosa", "浆膜侧", "cannot_judge", 0.32, ["short_outer_edge"])
    else:
        serosa = _item("serosa", "浆膜侧", "cannot_judge", 0.28, ["outer_edge_not_seen"])

    return [mucosa, muscularis, serosa]


def region_status(verdict: str) -> str:
    return VERDICT_TO_REGION.get(verdict, "obscured")
