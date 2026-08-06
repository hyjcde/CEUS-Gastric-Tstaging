#!/usr/bin/env python3
"""Conservative T-stage evidence gate.

The wall SDF tool provides proxy geometry, not a pathological wall-layer
estimate. This module separates those concepts and only allows a provisional
stage when explicit layer/serosal evidence, sequence consistency and quality
are all present.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


STAGE_ORDER = {"T1": 0, "T2": 1, "T3": 2, "T4+": 3}
LAYER_TO_STAGE = {
    "mucosa": "T1",
    "mucosa_submucosa": "T1",
    "submucosa": "T1",
    "muscularis": "T2",
    "muscularis_propria": "T2",
    "subserosa": "T3",
    "serosa": "T4+",
    "adjacent_organ": "T4+",
    "adjacent": "T4+",
}
VALID_SOURCE_TYPES = {
    "image_observed",
    "video_observed",
    "doctor_input",
}


def _first(mapping: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _normalize_stage(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper().replace("CT", "")
    aliases = {"T4A": "T4+", "T4B": "T4+", "T4": "T4+"}
    text = aliases.get(text, text)
    return text if text in STAGE_ORDER else None


def _normalize_layer(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "mucosal": "mucosa",
        "mucosa_submucosal": "mucosa_submucosa",
        "muscle": "muscularis",
        "muscularis_propria": "muscularis_propria",
        "sub_serosa": "subserosa",
        "serosal": "serosa",
        "adjacent_organ_invasion": "adjacent_organ",
    }
    return aliases.get(text, text) if text in LAYER_TO_STAGE or text in aliases else None


def _as_quality(value: Any) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, score))


def _as_consistency(value: Any) -> float | None:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"consistent", "stable", "agree"}:
            return 1.0
        if lowered in {"inconsistent", "conflicting", "unstable"}:
            return 0.0
    return _as_quality(value)


def _model_stage_from_frames(frame_signals: Sequence[Mapping[str, Any]]) -> tuple[str | None, float | None, bool]:
    stages = []
    probabilities = []
    for signal in frame_signals:
        stage = _normalize_stage(signal.get("stage") or signal.get("top1_stage"))
        if stage:
            stages.append(stage)
        probability = _as_quality(signal.get("probability") or signal.get("top1_prob"))
        if probability is not None:
            probabilities.append(probability)
    if not stages:
        return None, None, False
    counts = {stage: stages.count(stage) for stage in set(stages)}
    top_stage = max(counts, key=counts.get)
    conflict = len(counts) > 1
    probability = sum(probabilities) / len(probabilities) if probabilities else None
    return top_stage, probability, conflict


def evaluate_t_stage_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Return a replayable safety decision from structured evidence.

    A proxy-only wall result can support a request for more evidence, but
    cannot independently support T1–T4+. ``recommended_t_stage`` remains
    ``indeterminate`` unless an explicit structural observation passes all
    quality and sequence gates.
    """

    wall = evidence.get("wall_evidence")
    wall = wall if isinstance(wall, Mapping) else {}
    layer = _normalize_layer(
        _first(
            evidence,
            ("wall_layer", "wall_layer_estimate_value", "layer_structure", "layer"),
        )
        or _first(wall, ("wall_layer", "wall_layer_estimate_value", "layer_structure", "layer"))
    )
    layer_source = str(
        _first(evidence, ("wall_layer_source_type", "source_type"))
        or _first(wall, ("wall_layer_source_type", "source_type"))
        or ""
    ).lower()
    layer_is_explicit = bool(layer and (layer_source in VALID_SOURCE_TYPES or evidence.get("allow_model_layer") is True))
    proxy_only = (
        str(wall.get("evidence_role") or "").lower() in {"proxy_geometry", "proxy_geometry_unavailable"}
        or wall.get("wall_layer_estimate") is False
    )

    serosa = str(
        _first(evidence, ("serosa_status", "serosal_status", "serosa_change"))
        or _first(wall, ("serosa_status", "serosal_status"))
        or ""
    ).strip().lower()
    adjacent = str(
        _first(evidence, ("adjacent_invasion", "adjacent_organ_invasion", "perigastric_invasion"))
        or ""
    ).strip().lower()

    frame_signals = evidence.get("frame_signals")
    frame_signals = frame_signals if isinstance(frame_signals, Sequence) and not isinstance(frame_signals, (str, bytes)) else []
    model_stage = _normalize_stage(evidence.get("model_stage"))
    model_probability = _as_quality(evidence.get("model_probability"))
    frame_stage, frame_probability, frame_conflict = _model_stage_from_frames(frame_signals)
    if model_stage is None:
        model_stage = frame_stage
    if model_probability is None:
        model_probability = frame_probability

    frame_count = evidence.get("frame_count")
    try:
        frame_count = int(frame_count)
    except (TypeError, ValueError):
        frame_count = len(frame_signals)
    consistency = _as_consistency(
        evidence.get("frame_consistency")
        if evidence.get("frame_consistency") is not None
        else (1.0 if frame_signals and not frame_conflict else None)
    )
    quality = _as_quality(
        evidence.get("wall_quality")
        if evidence.get("wall_quality") is not None
        else _first(wall, ("quality_score", "wall_quality", "confidence"))
    )

    reasons: list[str] = []
    conflicts: list[str] = []
    if proxy_only:
        reasons.append("wall_proxy_not_layer_truth")
    if not layer_is_explicit:
        reasons.append("explicit_wall_layer_missing")
    if frame_count < 2:
        reasons.append("single_frame_or_missing_sequence")
    if consistency is None:
        reasons.append("frame_consistency_missing")
    elif consistency < 0.75:
        reasons.append("cross_frame_inconsistency")
    if quality is None:
        reasons.append("wall_quality_missing")
    elif quality < 0.70:
        reasons.append("wall_quality_below_gate")
    if frame_conflict:
        conflicts.append("frame_stage_disagreement")

    structural_stage = LAYER_TO_STAGE.get(layer) if layer_is_explicit else None
    if adjacent in {"present", "yes", "positive", "invasion"} and layer_is_explicit:
        structural_stage = "T4+"
    if serosa in {"disrupted", "breached", "positive", "involved"} and layer_is_explicit:
        structural_stage = "T4+"

    if structural_stage and model_stage and structural_stage != model_stage:
        conflicts.append(f"structural_{structural_stage}_vs_model_{model_stage}")

    high_quality = (
        layer_is_explicit
        and not proxy_only
        and frame_count >= 2
        and consistency is not None
        and consistency >= 0.75
        and quality is not None
        and quality >= 0.70
    )
    if conflicts:
        status = "conflicting"
        recommended = "indeterminate"
        next_action = "inspect_conflict_frames"
    elif high_quality and structural_stage:
        status = "supported"
        recommended = structural_stage
        next_action = "request_doctor_confirmation"
    elif structural_stage or model_stage:
        status = "uncertain"
        recommended = "indeterminate"
        next_action = "request_wall_layer_annotation"
    else:
        status = "not_assessable"
        recommended = "indeterminate"
        next_action = "request_wall_layer_annotation"

    return {
        "gate_version": "t_stage_evidence_gate_v1",
        "recommended_t_stage": recommended,
        "structural_t_stage": structural_stage,
        "model_t_stage": model_stage,
        "model_probability": model_probability,
        "t_stage_status": status,
        "next_action": next_action,
        "uncertainty_reasons": sorted(set(reasons)),
        "conflicting_evidence": conflicts,
        "proxy_only_wall_evidence": proxy_only,
        "explicit_wall_layer": layer,
        "frame_count": frame_count,
        "frame_consistency": consistency,
        "wall_quality": quality,
    }
