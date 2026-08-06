#!/usr/bin/env python3
"""Offline-first clinical Agent evolution shadow harness.

This script has two deliberately separate stages:

1. run-baseline: run the existing 13-step Agent on a sanitized CaseInput.
   Pathology/reference fields are removed before the clinical runtime starts.
2. build-evo001: convert baseline traces into an evidence-navigation candidate.
   The candidate only requests more evidence; it never changes the T-stage
   recommendation, model checkpoint, cutpoint, or doctor final decision.

The script is intended to run on the workstation, where the project and GPU
assets are available. It writes only under a dedicated evolution output root.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from t_stage_evidence_gate import evaluate_t_stage_evidence
except ModuleNotFoundError:  # pragma: no cover - package-style import fallback
    from scripts.t_stage_evidence_gate import evaluate_t_stage_evidence


SCRIPT_VERSION = "medical-agent-evolution-shadow-0.2"
DEFAULT_CASES = (
    "CASE-003",
    "CASE-005",
    "CASE-008",
    "CASE-015",
    "CASE-019",
    "CASE-025",
    "CASE-032",
    "CASE-037",
)
STAGE_ORDER = {"T1": 0, "T2": 1, "T3": 2, "T4+": 3}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def append_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def load_cases(cases_path: Path) -> Dict[str, Dict[str, Any]]:
    payload = json.loads(cases_path.read_text(encoding="utf-8"))
    cases = payload.get("cases", payload if isinstance(payload, list) else [])
    return {str(case["case_id"]): case for case in cases}


def sanitize_case_input(case_input: Any) -> Any:
    """Remove retrospective truth before entering the runtime graph."""

    case_input.gt_t_stage = None
    case_input.reference = {}
    safe_clinical: Dict[str, Any] = {}
    for key, value in (case_input.clinical or {}).items():
        lowered = str(key).lower()
        forbidden = (
            "pathology",
            "reference",
            "ground_truth",
            "gt_",
            "label",
            "t_stage",
        )
        if not any(token in lowered for token in forbidden):
            safe_clinical[key] = value
    case_input.clinical = safe_clinical
    return case_input


def parse_case_ids(raw: Sequence[str]) -> List[str]:
    case_ids: List[str] = []
    for item in raw:
        case_ids.extend(token.strip() for token in item.split(",") if token.strip())
    return case_ids or list(DEFAULT_CASES)


def recursive_nonempty_truth(value: Any, path: str = "$") -> List[str]:
    """Find non-empty retrospective truth fields in a runtime artifact."""

    hits: List[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).lower()
            if key_text in {"gt_t_stage", "t_stage_reference", "reference_pt", "reference_lesion_nature"}:
                if child not in (None, "", [], {}, False):
                    hits.append(f"{path}.{key}")
            hits.extend(recursive_nonempty_truth(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(recursive_nonempty_truth(child, f"{path}[{index}]"))
    return hits


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_baseline(args: argparse.Namespace) -> int:
    project_root = args.project_root.resolve()
    sys.path.insert(0, str(project_root))

    # Import through the production module entrypoint. Importing the nested
    # LangGraph module directly triggers the project's package-level legacy
    # alias and creates a circular import.
    from pipeline.agent.pipeline.run_case import run_case_pipeline
    from pipeline.agent.pipeline.case_input import CaseInput
    from pipeline.agent.pipeline.options import PipelineOptions

    cases = load_cases(args.cases_json)
    case_ids = parse_case_ids(args.case_ids)
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    registry_rows: List[Dict[str, Any]] = []

    options = PipelineOptions(
        device=args.device,
        enable_binary=True,
        enable_rag=args.enable_rag,
        enable_dino=True,
        triage_mode="conditional",
        skip_t_threshold=args.skip_t_threshold,
        seg_policy="auto",
        render_figures=False,
        memory_enabled=False,
    )

    for case_id in case_ids:
        row: Dict[str, Any] = {
            "case_id": case_id,
            "baseline_version": args.baseline_version,
            "script_version": SCRIPT_VERSION,
            "pathology_visibility": "hidden",
            "started_at": utc_now(),
        }
        case_out = output_root / case_id
        try:
            if case_id not in cases:
                raise KeyError(f"case_id not found: {case_id}")
            case_input = sanitize_case_input(
                CaseInput.from_cases_json(args.cases_json, case_id)
            )
            state = run_case_pipeline(case_input, case_out, options)
            state_path = case_out / "pipeline_state.json"
            runtime_payload = read_json(state_path)
            truth_hits = recursive_nonempty_truth(runtime_payload)
            report = runtime_payload.get("final_report") or {}
            manifest = read_json(case_out / "manifest.json")
            row.update(
                {
                    "status": "completed" if not truth_hits else "blocked_truth_leak",
                    "output_dir": str(case_out),
                    "pipeline_state": str(state_path),
                    "step_count": len(runtime_payload.get("steps") or []),
                    "recommended_t_stage": report.get("recommended_t_stage"),
                    "confidence": report.get("confidence"),
                    "llm_provider": manifest.get("llm_provider"),
                    "llm_model": manifest.get("llm_model"),
                    "truth_leak_paths": truth_hits,
                    "finished_at": utc_now(),
                }
            )
        except Exception as exc:  # noqa: BLE001
            row.update(
                {
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(limit=8),
                    "finished_at": utc_now(),
                }
            )
        registry_rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    dump_json(
        output_root / "baseline_registry.json",
        {
            "schema_version": "evolution_baseline_registry_v1",
            "script_version": SCRIPT_VERSION,
            "baseline_version": args.baseline_version,
            "pathology_visibility": "hidden",
            "case_ids": case_ids,
            "rows": registry_rows,
            "created_at": utc_now(),
        },
    )
    return 0 if all(row["status"] == "completed" for row in registry_rows) else 1


def _stage_from_mapping(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    for key in (
        "top1_label",
        "top1_stage",
        "predicted_t_stage",
        "recommended_t_stage",
        "t_stage",
        "label",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value in STAGE_ORDER:
            return value
    return None


def extract_frame_stage_signals(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract per-frame stage signals without using pathology labels."""

    signals: List[Dict[str, Any]] = []
    for step in state.get("steps") or []:
        if step.get("step_id") != "t_staging":
            continue
        obs = step.get("observation") or {}
        per_frame = obs.get("per_frame") or []
        if isinstance(per_frame, dict):
            per_frame = list(per_frame.values())
        if not isinstance(per_frame, list):
            continue
        for index, item in enumerate(per_frame):
            if not isinstance(item, dict):
                continue
            stage = _stage_from_mapping(item)
            if stage:
                signals.append(
                    {
                        "step_id": step.get("step_id"),
                        "frame_index": item.get("frame_index", index),
                        "frame_id": item.get("frame_id"),
                        "stage": stage,
                        "probability": item.get("top1_prob") or item.get("probability"),
                    }
                )
    return signals


def get_step(state: Dict[str, Any], step_id: str) -> Dict[str, Any]:
    for step in state.get("steps") or []:
        if step.get("step_id") == step_id:
            return step
    return {}


def build_t_stage_gate_input(
    *,
    state: Dict[str, Any],
    report: Dict[str, Any],
    stage_signals: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Extract structured, non-pathology inputs for the T-stage gate."""
    wall_obs = get_step(state, "wall_evidence").get("observation") or {}
    quality_obs = get_step(state, "quality").get("observation") or {}
    frame_obs = get_step(state, "frame_extract").get("observation") or {}

    frame_count = frame_obs.get("frame_count") or frame_obs.get("n_frames")
    if frame_count is None:
        frame_count = len(stage_signals)
    probabilities = [
        item.get("probability")
        for item in stage_signals
        if isinstance(item.get("probability"), (int, float))
    ]
    return {
        "wall_evidence": wall_obs,
        "wall_layer": wall_obs.get("wall_layer")
        or wall_obs.get("wall_layer_estimate_value")
        or wall_obs.get("layer_structure"),
        "wall_layer_source_type": wall_obs.get("wall_layer_source_type")
        or wall_obs.get("source_type")
        or ("doctor_input" if wall_obs.get("doctor_confirmed_layer") else "model_inference"),
        "model_stage": report.get("recommended_t_stage"),
        "model_probability": report.get("t_stage_model_probability")
        or (max(probabilities) if probabilities else None),
        "frame_signals": list(stage_signals),
        "frame_count": frame_count,
        "frame_consistency": (
            1.0
            if stage_signals
            and len({item["stage"] for item in stage_signals}) <= 1
            else (0.0 if stage_signals else None)
        ),
        "wall_quality": wall_obs.get("quality_score")
        or wall_obs.get("wall_quality")
        or quality_obs.get("quality_score")
        or quality_obs.get("score"),
    }


def extract_runtime_model_version(
    state: Dict[str, Any], registry_row: Dict[str, Any]
) -> Optional[str]:
    staging = get_step(state, "t_staging").get("observation") or {}
    primary = staging.get("primary") or {}
    invocation = primary.get("runtime_invocation") or {}
    checkpoint = invocation.get("checkpoint")
    if checkpoint:
        return str(checkpoint)
    return registry_row.get("llm_model")


def _collect_source_refs(value: Any, refs: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "frame_id" and child not in (None, ""):
                refs.add(f"frame:{child}")
            elif key == "image_path" and child not in (None, ""):
                refs.add(f"image:{child}")
            elif key == "roi_path" and child not in (None, ""):
                refs.add(f"roi:{child}")
            else:
                _collect_source_refs(child, refs)
    elif isinstance(value, list):
        for child in value:
            _collect_source_refs(child, refs)


def build_evidence_registry(
    *,
    case_id: str,
    state: Dict[str, Any],
    baseline_version: str,
    rule_version: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """Create an explicit offline provenance envelope around runtime steps."""

    source_type_by_step = {
        "quality": "derived_rule",
        "binary_gate": "model_inference",
        "lumen_detect": "model_inference",
        "lesion_seg": "model_inference",
        "morphology": "derived_rule",
        "t_staging": "model_inference",
        "wall_evidence": "derived_rule",
        "dinov3_seg": "model_inference",
        "dino_sign_fusion": "derived_rule",
        "case_rag": "model_inference",
    }
    items: List[Dict[str, Any]] = []
    by_step: Dict[str, List[Dict[str, Any]]] = {}
    for step in state.get("steps") or []:
        step_id = str(step.get("step_id") or "")
        if step_id in {"", "triage", "frame_extract", "report_synth"}:
            continue
        obs = step.get("observation") or {}
        refs: set[str] = set()
        _collect_source_refs(obs, refs)
        if not refs:
            refs.add(f"run:{case_id}:step:{step_id}")
        primary = obs.get("primary") or obs.get("representative_frame") or {}
        invocation = primary.get("runtime_invocation") or {}
        model_version = invocation.get("checkpoint") or baseline_version
        item = {
            "evidence_id": f"EVO-EV-{case_id}-{step_id}",
            "case_id": case_id,
            "domain": step_id,
            "feature": step_id,
            "value": {
                "status": step.get("status"),
                "available": obs.get("available", True),
                "keys": sorted(
                    key
                    for key in obs.keys()
                    if key not in {"mask_array", "heatmap", "grad_cam", "_visuals"}
                )[:40],
            },
            "status": "available" if step.get("status") == "completed" else "uncertain",
            "source_type": source_type_by_step.get(step_id, "derived_rule"),
            "source_ref": sorted(refs)[:80],
            "model_version": str(model_version),
            "rule_version": rule_version,
            "frame_id_or_time": sorted(
                ref.split(":", 1)[1]
                for ref in refs
                if ref.startswith("frame:")
            )[:80],
            "created_at": utc_now(),
        }
        items.append(item)
        by_step.setdefault(step_id, []).append(item)
    return items, by_step


def build_observation(
    *,
    case_id: str,
    case: Dict[str, Any],
    state: Dict[str, Any],
    registry_row: Dict[str, Any],
    baseline_version: str,
    rule_version: str,
    evidence_by_step: Dict[str, List[Dict[str, Any]]],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    report = state.get("final_report") or {}
    stage_signals = extract_frame_stage_signals(state)
    t_stage_gate = evaluate_t_stage_evidence(
        build_t_stage_gate_input(
            state=state,
            report=report,
            stage_signals=stage_signals,
        )
    )
    stages = [row["stage"] for row in stage_signals]
    unique_stages = sorted(set(stages), key=lambda item: STAGE_ORDER[item])
    uncertainty_flags = list(report.get("uncertainty_flags") or [])
    confidence = str(report.get("confidence") or "").lower()
    wall_obs = get_step(state, "wall_evidence").get("observation") or {}
    dino_obs = get_step(state, "dino_sign_fusion").get("observation") or {}
    provenance_items: List[Dict[str, Any]] = []
    for step_id in ("quality", "t_staging", "wall_evidence", "dino_sign_fusion"):
        provenance_items.extend(evidence_by_step.get(step_id, []))
    evidence_ids = [item["evidence_id"] for item in provenance_items]
    source_refs = [
        ref
        for item in provenance_items
        for ref in item.get("source_ref", [])
    ]
    conflict = len(unique_stages) > 1 or t_stage_gate["t_stage_status"] == "conflicting"
    low_confidence = confidence in {"low", "uncertain", "indeterminate"}
    generic_flags = {
        "No structured ultrasound report cues were available.",
        "No report text was attached to this case.",
        "No similar historical cases were available in case memory.",
    }
    meaningful_flags = [
        flag for flag in uncertainty_flags if flag not in generic_flags
    ]
    meaningful_flags.extend(dino_obs.get("uncertainty_flags") or [])
    meaningful_flags.extend(t_stage_gate["uncertainty_reasons"])
    evidence_uncertain = bool(meaningful_flags)
    gate_requires_more_evidence = t_stage_gate["t_stage_status"] != "supported"
    candidate_action = (
        "request_more_evidence"
        if (conflict or low_confidence or evidence_uncertain or gate_requires_more_evidence)
        else "proceed_with_current_evidence"
    )
    if candidate_action == "request_more_evidence":
        target_regions = ["multi_frame_consistency"]
        if t_stage_gate["next_action"] == "inspect_conflict_frames":
            target_regions.append("t_stage_conflict_localization")
        elif t_stage_gate["next_action"] == "request_wall_layer_annotation":
            target_regions.append("explicit_wall_layer_annotation")
        if wall_obs:
            target_regions.extend(["wall_continuity", "serosal_or_perigastric_boundary"])
        if t_stage_gate["t_stage_status"] == "conflicting":
            reason = "t_stage_structural_model_conflict"
            failure_class = "cross_frame_conflict"
        elif gate_requires_more_evidence:
            reason = "wall_layer_quality_gate_not_met"
            failure_class = "wall_layer_evidence_gap"
        else:
            reason = "frame_stage_conflict" if conflict else "low_confidence_or_evidence_gap"
            failure_class = "cross_frame_conflict" if conflict else "missing_evidence"
    else:
        target_regions = []
        reason = "no_candidate_evidence_gap_detected"
        failure_class = "none_observed"

    observation = {
        "observation_id": f"OBS-EVO001-{case_id}",
        "run_id": f"EVO001-{case_id}",
        "session_id": None,
        "case_id": case_id,
        "patient_id": str(case.get("patient_id") or ""),
        "round": "offline_replay",
        "baseline_version": {
            "agent_version": baseline_version,
            "model_version": extract_runtime_model_version(state, registry_row),
            "rule_version": rule_version,
            "manifest_version": "cases_json_offline_replay_v1",
        },
        "failure_class": failure_class,
        "candidate_action": candidate_action,
        "candidate_reason": reason,
        "target_regions": target_regions,
        "evidence_ids": evidence_ids,
        "source_refs": sorted(set(source_refs)),
        "frame_signal_count": len(stage_signals),
        "frame_stage_distribution": dict(Counter(stages)),
        "unique_frame_stages": unique_stages,
        "t_stage_gate": t_stage_gate,
        "recommended_t_stage": report.get("recommended_t_stage"),
        "confidence": report.get("confidence"),
        "uncertainty_flags": uncertainty_flags,
        "meaningful_uncertainty_flags": meaningful_flags,
        "pathology_visibility": "hidden",
        "clinical_truth_status": "not_used_online",
        "candidate_eligible": bool(registry_row.get("status") == "completed"),
        "created_at": utc_now(),
    }
    offline_label = {
        "case_id": case_id,
        "patient_id": str(case.get("patient_id") or ""),
        "pathology_t_stage": (case.get("reference_standard") or {}).get("pathology_t_stage"),
        "offline_eval_only": True,
    }
    return observation, offline_label


def build_evo001(args: argparse.Namespace) -> int:
    cases = load_cases(args.cases_json)
    baseline_root = args.baseline_root.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    registry_path = baseline_root / "baseline_registry.json"
    registry_doc = read_json(registry_path)
    registry_by_case = {row["case_id"]: row for row in registry_doc.get("rows", [])}
    case_ids = parse_case_ids(args.case_ids)

    observations: List[Dict[str, Any]] = []
    hidden_labels: List[Dict[str, Any]] = []
    diffs: List[Dict[str, Any]] = []
    evidence_registry: List[Dict[str, Any]] = []
    truth_leaks: List[str] = []
    errors: List[str] = []

    for case_id in case_ids:
        row = registry_by_case.get(case_id, {})
        state_path = Path(row.get("pipeline_state") or baseline_root / case_id / "pipeline_state.json")
        if not state_path.exists():
            errors.append(f"{case_id}: missing {state_path}")
            continue
        state = read_json(state_path)
        leaks = recursive_nonempty_truth(state)
        truth_leaks.extend(f"{case_id}:{item}" for item in leaks)
        if case_id not in cases:
            errors.append(f"{case_id}: missing cases.json metadata")
            continue
        evidence_items, evidence_by_step = build_evidence_registry(
            case_id=case_id,
            state=state,
            baseline_version=args.baseline_version,
            rule_version=args.rule_version,
        )
        evidence_registry.extend(evidence_items)
        observation, hidden_label = build_observation(
            case_id=case_id,
            case=cases[case_id],
            state=state,
            registry_row=row,
            baseline_version=args.baseline_version,
            rule_version=args.rule_version,
            evidence_by_step=evidence_by_step,
        )
        observations.append(observation)
        hidden_labels.append(hidden_label)
        diffs.append(
            {
                "case_id": case_id,
                "baseline_recommended_t_stage": observation["recommended_t_stage"],
                "candidate_recommended_t_stage": observation["recommended_t_stage"],
                "candidate_action": observation["candidate_action"],
                "candidate_reason": observation["candidate_reason"],
                "stage_unchanged_by_design": True,
            }
        )

    eval_rows = []
    for label, diff in zip(hidden_labels, diffs):
        gt = label.get("pathology_t_stage")
        pred = diff.get("baseline_recommended_t_stage")
        eval_rows.append(
            {
                "case_id": diff["case_id"],
                "gt": gt,
                "baseline_pred": pred,
                "candidate_pred": diff["candidate_recommended_t_stage"],
                "baseline_correct": bool(gt and pred and gt == pred),
                "candidate_correct": bool(gt and diff["candidate_recommended_t_stage"] == gt),
                "candidate_requested_more_evidence": diff["candidate_action"] == "request_more_evidence",
            }
        )

    n = len(eval_rows)
    baseline_correct = sum(int(row["baseline_correct"]) for row in eval_rows)
    candidate_requests = sum(int(row["candidate_requested_more_evidence"]) for row in eval_rows)
    baseline_errors = [row for row in eval_rows if not row["baseline_correct"]]
    flagged_errors = [row for row in baseline_errors if row["candidate_requested_more_evidence"]]
    metrics = {
        "schema_version": "evo001_evaluation_v1",
        "candidate_id": args.candidate_id,
        "case_count": n,
        "baseline_accuracy_offline_only": (baseline_correct / n) if n else None,
        "candidate_accuracy_offline_only": (baseline_correct / n) if n else None,
        "clinical_stage_unchanged_by_design": True,
        "candidate_request_more_evidence_rate": (candidate_requests / n) if n else None,
        "baseline_error_count_offline_only": len(baseline_errors),
        "flagged_baseline_error_count_offline_only": len(flagged_errors),
        "flagged_baseline_error_recall_offline_only": (
            len(flagged_errors) / len(baseline_errors) if baseline_errors else None
        ),
        "truth_leak_count": len(truth_leaks),
        "build_error_count": len(errors),
        "evidence_registry_count": len(evidence_registry),
        "created_at": utc_now(),
    }
    provenance_incomplete = [
        row["observation_id"]
        for row in observations
        if (
            not row.get("evidence_ids")
            or not row.get("source_refs")
            or not row.get("baseline_version", {}).get("model_version")
            or row.get("baseline_version", {}).get("rule_version")
            == "runtime_rule_version_not_registered"
        )
    ]
    metrics["provenance_incomplete_observation_count"] = len(provenance_incomplete)
    metrics["provenance_complete_observation_count"] = (
        len(observations) - len(provenance_incomplete)
    )
    promotion_block_reasons: List[str] = []
    if truth_leaks:
        promotion_block_reasons.append("pathology_truth_leak")
    if errors:
        promotion_block_reasons.append("build_error")
    if provenance_incomplete:
        promotion_block_reasons.extend(
            ["evidence_id_missing", "rule_version_not_registered"]
        )
    hard_block_reasons = list(promotion_block_reasons)
    promotion_block_reasons.append("doctor_review_pending")
    safety_gate = {
        "schema_version": "evo001_safety_gate_v1",
        "candidate_id": args.candidate_id,
        "pathology_leak_check": "pass" if not truth_leaks else "fail",
        "evidence_provenance_check": (
            "pass" if not provenance_incomplete else "fail"
        ),
        "doctor_review_check": "pending",
        "doctor_final_overwrite": "pass",
        "checkpoint_mutation": "pass",
        "cutpoint_mutation": "pass",
        "manifest_mutation": "pass",
        "candidate_is_evidence_navigation_only": "pass",
        "artifact_status": "generated",
        "shadow_status": "offline_only",
        "release_status": "blocked" if hard_block_reasons else "shadow_only",
        "promotion_status": "blocked" if promotion_block_reasons else "ready",
        "promotable": not promotion_block_reasons,
        "promotion_block_reasons": sorted(set(promotion_block_reasons)),
        "truth_leak_paths": truth_leaks,
        "provenance_incomplete_observation_ids": provenance_incomplete,
        "errors": errors,
        "created_at": utc_now(),
    }
    candidate_manifest = {
        "schema_version": "evolution_candidate_manifest_v1",
        "candidate_id": args.candidate_id,
        "change_class": "evidence_navigation",
        "parent_version": args.baseline_version,
        "candidate_version": "evo001-t23-evidence-nav-v1",
        "trigger_observation_ids": [row["observation_id"] for row in observations],
        "allowed_changes": [
            "frame_priority",
            "evidence_gap_prompt",
            "request_more_evidence_policy",
            "indeterminate_explanation",
        ],
        "forbidden_changes": [
            "checkpoint",
            "t_stage_cutpoint",
            "pathology_mapping",
            "doctor_final",
            "manifest",
            "reader_assignment",
        ],
        "stage_recommendation_mutation": False,
        "replay_manifest": "evo001_t23_boundary_replay_v1",
        "rule_version": args.rule_version,
        "status": safety_gate["release_status"],
        "rollback_ref": args.baseline_version,
        "created_at": utc_now(),
    }
    replay_manifest = {
        "schema_version": "evolution_replay_manifest_v1",
        "manifest_id": "evo001_t23_boundary_replay_v1",
        "purpose": "offline evidence-navigation shadow",
        "case_ids": case_ids,
        "pathology_visibility": "hidden_to_runtime",
        "hidden_labels_path": "offline_eval_only/hidden_labels.jsonl",
        "baseline_version": args.baseline_version,
        "rule_version": args.rule_version,
        "candidate_id": args.candidate_id,
        "created_at": utc_now(),
    }

    dump_json(output_root / "candidate_manifest.json", candidate_manifest)
    dump_json(output_root / "replay_manifest.json", replay_manifest)
    dump_json(output_root / "evaluation_metrics.json", metrics)
    dump_json(output_root / "safety_gate.json", safety_gate)
    append_jsonl(output_root / "evidence_registry.jsonl", evidence_registry)
    append_jsonl(output_root / "evolution_observations.jsonl", observations)
    append_jsonl(output_root / "candidate_case_diff.jsonl", diffs)
    append_jsonl(output_root / "offline_eval_only" / "hidden_labels.jsonl", hidden_labels)
    append_jsonl(output_root / "offline_eval_only" / "case_metrics.jsonl", eval_rows)
    report = [
        "# EVO-001 T2/T3 Evidence Navigation Shadow",
        "",
        f"- Candidate: `{args.candidate_id}`",
        f"- Baseline: `{args.baseline_version}`",
        f"- Cases: `{n}`",
        f"- Candidate action: evidence request only; stage recommendation unchanged by design",
        f"- Artifact status: `{safety_gate['artifact_status']}`",
        f"- Release status: `{safety_gate['release_status']}`",
        f"- Promotion status: `{safety_gate['promotion_status']}`",
        f"- Provenance check: `{safety_gate['evidence_provenance_check']}`",
        "",
        "## Offline evaluation",
        "",
        f"- Baseline accuracy (offline only): `{metrics['baseline_accuracy_offline_only']}`",
        f"- Candidate accuracy (offline only): `{metrics['candidate_accuracy_offline_only']}`",
        f"- Request-more-evidence rate: `{metrics['candidate_request_more_evidence_rate']}`",
        f"- Baseline errors flagged for further evidence: `{metrics['flagged_baseline_error_count_offline_only']}/{metrics['baseline_error_count_offline_only']}`",
        "",
        "## Safety interpretation",
        "",
        "- This candidate does not change the T-stage model, checkpoint, cutpoint, pathology mapping or doctor final.",
        "- Hidden pathology labels are stored under `offline_eval_only/` and are not passed into the runtime graph.",
        "- This is an offline Shadow artifact, not a clinical release.",
        "- Missing `evidence_id` or unregistered `rule_version` blocks promotion.",
        "- Doctor review is still pending; no UI exposure is permitted.",
        "",
        "## Next gate",
        "",
        "Doctor review and a fixed replay comparison are required before any UI exposure.",
    ]
    (output_root / "EVO-001_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"candidate_manifest": str(output_root / "candidate_manifest.json"), "metrics": metrics, "safety_gate": safety_gate}, ensure_ascii=False, indent=2))
    return 0 if safety_gate["release_status"] != "blocked" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run-baseline")
    run.add_argument("--project-root", type=Path, required=True)
    run.add_argument("--cases-json", type=Path, required=True)
    run.add_argument("--output-root", type=Path, required=True)
    run.add_argument("--case-ids", nargs="*", default=list(DEFAULT_CASES))
    run.add_argument("--baseline-version", default="gastric-agent-next-lan-20260801")
    run.add_argument("--device", default="cuda:0")
    run.add_argument("--enable-rag", action="store_true")
    run.add_argument("--skip-t-threshold", type=float, default=0.95)
    run.set_defaults(func=run_baseline)

    build = sub.add_parser("build-evo001")
    build.add_argument("--cases-json", type=Path, required=True)
    build.add_argument("--baseline-root", type=Path, required=True)
    build.add_argument("--output-root", type=Path, required=True)
    build.add_argument("--case-ids", nargs="*", default=list(DEFAULT_CASES))
    build.add_argument("--baseline-version", default="gastric-agent-next-lan-20260801")
    build.add_argument("--candidate-id", default="EVO-001-T23-EVIDENCE-NAV")
    build.add_argument(
        "--rule-version",
        default="agent-step-registry-20260801-9bd519051debb05886916db75e4a6d79c618d7979bc88f38cfe5a355c5749d22",
    )
    build.set_defaults(func=build_evo001)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
