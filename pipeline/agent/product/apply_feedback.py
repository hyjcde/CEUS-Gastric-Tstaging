#!/usr/bin/env python3
"""Apply doctor/pathology feedback and trigger memory reflect."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.core.repo_paths import PROJECT_ROOT
from agent.memory.evolver import (
    apply_feedback_action,
    build_case_episode_record,
    reflect_error_to_candidates,
    write_episode_from_analysis,
)
from agent.memory.store.jsonl_store import JsonlMemoryStore
from agent.memory.store.paths import resolve_store_paths


def apply_feedback(payload: Dict[str, Any]) -> Dict[str, Any]:
    store_path = payload.get("memory_store") or payload.get("memory_store_path")
    if not store_path:
        store_path = str(resolve_store_paths(run_id="default").root)
    store = JsonlMemoryStore(store_root=store_path)

    patient_id = str(payload.get("patient_id", ""))
    action = payload.get("action")
    record_id = payload.get("record_id")

    if action and record_id:
        entry = apply_feedback_action(
            store,
            record_id=str(record_id),
            action=str(action),
            reviewer=str(payload.get("reviewer", "workbench")),
        )
        return {
            "status": "ok" if entry else "not_found",
            "record_id": record_id,
            "action": action,
            "entry": entry.to_line() if entry else None,
            "memory_store": str(store.paths.root),
        }

    predicted_t = payload.get("predicted_t_stage") or payload.get("recommended_t_stage")
    final_t = payload.get("final_t_stage") or payload.get("gold_t_stage")
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
        "correction_text": payload.get("correction_text", ""),
        "error_type": payload.get("error_type", ""),
    }
    payload = dict(payload)
    payload["feedback"] = feedback

    write_episode_from_analysis(store, payload, report, status="active")

    candidates_written = []
    if predicted_t and final_t and str(predicted_t) != str(final_t):
        for cand in reflect_error_to_candidates(
            patient_id=patient_id,
            predicted_t=str(predicted_t),
            gold_t=str(final_t),
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
            candidates_written.append(entry.to_line())

    return {
        "status": "ok",
        "patient_id": patient_id,
        "memory_store": str(store.paths.root),
        "feedback": feedback,
        "candidates_written": len(candidates_written),
        "candidates": candidates_written,
    }


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Apply agent feedback to self-evolving memory store")
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
