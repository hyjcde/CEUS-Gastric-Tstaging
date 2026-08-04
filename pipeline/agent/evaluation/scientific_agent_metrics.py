"""Research metrics for the scientific Agent control loop.

These metrics deliberately evaluate the Agent as an evidence-and-decision
system, not only as a classifier: calibration, temporal consistency,
provenance completeness, conflict recognition and evidence-action efficiency.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Sequence


def brier_score(y_true: Sequence[int], probabilities: Sequence[float]) -> float:
    if len(y_true) != len(probabilities) or not y_true:
        return 0.0
    return sum((float(probability) - int(label)) ** 2 for label, probability in zip(y_true, probabilities)) / len(y_true)


def expected_calibration_error(
    y_true: Sequence[int],
    probabilities: Sequence[float],
    bins: int = 10,
) -> float:
    """Absolute confidence/accuracy gap over equal-width probability bins."""
    if len(y_true) != len(probabilities) or not y_true or bins <= 0:
        return 0.0
    buckets: List[List[tuple[int, float]]] = [[] for _ in range(bins)]
    for label, probability in zip(y_true, probabilities):
        p = max(0.0, min(1.0, float(probability)))
        index = min(bins - 1, int(p * bins))
        buckets[index].append((int(label), p))
    total = float(len(y_true))
    error = 0.0
    for bucket in buckets:
        if not bucket:
            continue
        accuracy = sum(label for label, _ in bucket) / len(bucket)
        confidence = sum(probability for _, probability in bucket) / len(bucket)
        error += (len(bucket) / total) * abs(accuracy - confidence)
    return error


def frame_agreement_rate(stages: Iterable[str]) -> float:
    values = [str(stage) for stage in stages if stage]
    if not values:
        return 0.0
    return Counter(values).most_common(1)[0][1] / len(values)


def evidence_completeness(
    belief_state: Dict[str, Any],
    required_domains: Sequence[str] = ("malignancy", "staging", "dino", "clinical_decision"),
) -> float:
    evidence = belief_state.get("evidence") or []
    domains = {
        str(item.get("domain"))
        for item in evidence
        if isinstance(item, dict) and item.get("status") not in {"missing", "failed"}
    }
    if not required_domains:
        return 1.0
    return sum(domain in domains for domain in required_domains) / len(required_domains)


def conflict_detection_rate(
    predicted_conflict: Sequence[bool],
    expected_conflict: Sequence[bool],
) -> float:
    if len(predicted_conflict) != len(expected_conflict) or not expected_conflict:
        return 0.0
    positives = sum(bool(predicted) and bool(expected) for predicted, expected in zip(predicted_conflict, expected_conflict))
    expected_count = sum(bool(expected) for expected in expected_conflict)
    return positives / expected_count if expected_count else 1.0


def action_efficiency(
    actions: Sequence[Dict[str, Any]],
    resolved_evidence_ids: Sequence[str] = (),
) -> float:
    """Information gain per selected action, optionally weighted by resolution."""
    selected = [item for item in actions if item.get("status") == "selected"]
    if not selected:
        return 0.0
    gain = sum(float(item.get("expected_information_gain") or 0.0) for item in selected)
    if not resolved_evidence_ids:
        return gain / len(selected)
    return (gain * min(1.0, len(resolved_evidence_ids) / len(selected))) / len(selected)


def summarize_agent_runs(runs: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate replay records into a compact research QA summary."""
    if not runs:
        return {
            "run_count": 0,
            "evidence_completeness": 0.0,
            "mean_frame_agreement": 0.0,
            "mean_action_efficiency": 0.0,
        }
    completeness = [
        evidence_completeness(run.get("belief_state") or {})
        for run in runs
    ]
    agreement = [
        frame_agreement_rate(run.get("frame_stages") or [])
        for run in runs
    ]
    efficiency = [
        action_efficiency(
            (run.get("belief_state") or {}).get("action_trace") or [],
            (run.get("resolved_evidence_ids") or []),
        )
        for run in runs
    ]
    return {
        "run_count": len(runs),
        "evidence_completeness": round(sum(completeness) / len(completeness), 4),
        "mean_frame_agreement": round(sum(agreement) / len(agreement), 4),
        "mean_action_efficiency": round(sum(efficiency) / len(efficiency), 4),
    }
