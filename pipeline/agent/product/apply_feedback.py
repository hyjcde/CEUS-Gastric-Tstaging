#!/usr/bin/env python3
"""Apply doctor/pathology feedback as QA-gated evolution observations.

Changes vs legacy behaviour:
  - Doctor events are appended to evolution_observations.jsonl first.
  - Memory candidates stay status=candidate and require explicit QA approval.
  - Support-count based active memory promotion is disabled.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.core.repo_paths import PROJECT_ROOT
from agent.memory.evolver import (
    apply_feedback_action,
    reflect_error_to_candidates,
    write_episode_from_analysis,
)
from agent.memory.store.jsonl_store import JsonlMemoryStore
from agent.memory.store.paths import resolve_store_paths
from agent.safety.evolution_gate import evaluate_candidate_manifest, write_candidate_scaffold

EVOLUTION_OBS_PATH = PROJECT_ROOT / "apps/gastric_scan_next/data/evolution_observations.jsonl"
CANDIDATE_ROOT = PROJECT_ROOT / "data/evolution_candidates"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_evolution_observation(payload: Dict[str, Any]) -> Dict[str, Any]:
    EVOLUTION_OBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    obs = {
        "schema_version": "evolution_observation_v1",
        "observation_id": f"obs_{uuid.uuid4().hex[:12]}",
        "created_at": _utc_now(),
        "patient_id": str(payload.get("patient_id") or ""),
        "case_id": payload.get("case_id"),
        "session_id": payload.get("session_id") or payload.get("sessionId"),
        "sample_id": payload.get("sample_id"),
        "case_id": payload.get("case_id"),
        "event_type": str(payload.get("feedback_type") or payload.get("event_type") or "doctor_action"),
        "payload": {
            "predicted_t_stage": payload.get("predicted_t_stage") or payload.get("recommended_t_stage"),
            "final_t_stage": payload.get("final_t_stage") or payload.get("gold_t_stage"),
            "gold_t_stage": payload.get("gold_t_stage"),
            "correction_text": payload.get("correction_text", ""),
            "error_type": payload.get("error_type", ""),
            "candidate_action": payload.get("action", ""),
            "record_id": payload.get("record_id"),
            "review_action": payload.get("review_action", ""),
            "quality_flags": payload.get("quality_flags") or [],
            "accepted_evidence": payload.get("accepted_evidence") or [],
            "rejected_evidence": payload.get("rejected_evidence") or [],
            "reviewer": payload.get("reviewer", "workbench"),
        },
        "qa_status": "pending",
        "label_ready": False,
        "pathology_present": bool(payload.get("gold_t_stage")),
        "notes": "Observation only; not a training label until QA passes.",
    }
    with EVOLUTION_OBS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obs, ensure_ascii=False) + "\n")
    return obs


def apply_feedback(payload: Dict[str, Any]) -> Dict[str, Any]:
    """QA-gated candidate writer. Does not auto-promote active memory."""
    store_path = payload.get("memory_store") or payload.get("memory_store_path")
    if not store_path:
        store_path = str(resolve_store_paths(run_id="default").root)
    store = JsonlMemoryStore(store_root=store_path)

    patient_id = str(payload.get("patient_id", ""))
    action = payload.get("action")
    record_id = payload.get("record_id")

    observation = append_evolution_observation(payload)

    # Explicit reviewer actions on existing candidate records only.
    if action and record_id:
        requested_action = str(action).lower()
        action_aliases = {
            "approve": "accept",
            "hold": "defer",
            "needs_revision": "defer",
        }
        normalized_action = action_aliases.get(requested_action, requested_action)
        if normalized_action not in {"accept", "reject", "defer"}:
            return {
                "status": "blocked",
                "reason": "Only candidate actions accept/reject/defer are allowed",
                "observation": observation,
            }
        # An accept is recorded as a QA decision but remains a candidate until
        # offline replay and the evolution gate approve active promotion.
        applied_action = "defer" if normalized_action == "accept" else normalized_action
        entry = apply_feedback_action(
            store,
            record_id=str(record_id),
            action=applied_action,
            reviewer=str(payload.get("reviewer", "workbench")),
        )
        return {
            "status": "ok" if entry else "not_found",
            "record_id": record_id,
            "action": requested_action,
            "applied_action": applied_action,
            "active_promotion": False,
            "entry": entry.to_line() if entry else None,
            "memory_store": str(store.paths.root),
            "observation": observation,
        }

    predicted_t = payload.get("predicted_t_stage") or payload.get("recommended_t_stage")
    gold_t = payload.get("gold_t_stage")
    final_t = payload.get("final_t_stage") or gold_t
    feedback_type = payload.get("feedback_type", "doctor_correction")
    report = {
        "recommended_t_stage": predicted_t,
        "confidence": payload.get("confidence", "medium"),
        "supporting_evidence": payload.get("supporting_evidence", []),
        "uncertainty_flags": payload.get("uncertainty_flags", []),
    }
    feedback = {
        "feedback_type": feedback_type,
        "final_t_stage": final_t,
        "gold_t_stage": gold_t,
        "correction_text": payload.get("correction_text", ""),
        "error_type": payload.get("error_type", ""),
        "review_action": payload.get("review_action", ""),
        "quality_flags": payload.get("quality_flags") or [],
        "accepted_evidence": payload.get("accepted_evidence") or [],
        "rejected_evidence": payload.get("rejected_evidence") or [],
    }
    payload = dict(payload)
    payload["feedback"] = feedback

    # Episode stays non-active until QA.
    write_episode_from_analysis(store, payload, report, status="candidate")

    candidates_written = []
    candidate_dirs = []
    qa_required = True
    promote_active = bool(payload.get("force_active_promotion"))
    if promote_active:
        return {
            "status": "blocked",
            "reason": "force_active_promotion is forbidden; use offline evolution gate",
            "observation": observation,
        }

    comparison_t = gold_t or final_t
    if predicted_t and comparison_t and str(predicted_t) != str(comparison_t):
        for cand in reflect_error_to_candidates(
            patient_id=patient_id,
            predicted_t=str(predicted_t),
            gold_t=str(comparison_t),
            error_type=payload.get("error_type"),
            backend_id=str(payload.get("backend_id", "tstage_acc_boost2_screened_20260603")),
            run_id=store.paths.root.name,
        ):
            entry = store.append_entry(
                cand,
                status="candidate",
                quality_score=0.45,
                support_count=1,
                patient_id=patient_id,
                also_candidates=True,
            )
            # Do NOT bump to active based on support_count.
            candidates_written.append(entry.to_line())

        candidate_id = f"FB_{observation['observation_id']}"
        scaffold = write_candidate_scaffold(
            CANDIDATE_ROOT,
            candidate_id=candidate_id,
            evolution_objects=[
                "uncertainty_abstention",
                "clinical_communication_skill",
            ],
            baseline_ref="active_memory_shadow",
            notes="Feedback-derived candidate; awaiting doctor QA and replay gate.",
        )
        gate = evaluate_candidate_manifest(scaffold["manifest"])
        candidate_dirs.append(
            {
                "candidate_id": candidate_id,
                "dir": scaffold["candidate_dir"],
                "gate": gate,
            }
        )

    return {
        "status": "ok",
        "patient_id": patient_id,
        "memory_store": str(store.paths.root),
        "feedback": feedback,
        "candidates_written": len(candidates_written),
        "candidates": candidates_written,
        "candidate_dirs": candidate_dirs,
        "qa_required": qa_required,
        "active_promotion": False,
        "observation": observation,
        "evolution_observations_path": str(EVOLUTION_OBS_PATH),
    }


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="QA-gated agent feedback / evolution observation writer")
    p.add_argument("--payload-json", type=Path, help="JSON payload file")
    p.add_argument("--stdin", action="store_true", help="Read JSON payload from stdin")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    if args.stdin or not args.payload_json:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    else:
        payload = json.loads(args.payload_json.read_text(encoding="utf-8"))
    result = apply_feedback(payload)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
