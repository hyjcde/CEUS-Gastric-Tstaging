"""Self-evolution reflect / promote / quality_score updates (Evo-MedAgent + GSEM-lite)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.core.repo_paths import PROJECT_ROOT
from agent.memory.store.jsonl_store import JsonlMemoryStore, StoreEntry, build_source
from agent.memory.store.paths import resolve_store_paths
from agent.memory.store.schema_validate import SCHEMA_VERSION

logger = logging.getLogger("agent.memory.evolver")

STAGES = {"T1", "T2", "T3", "T4+", "T4", "T4a", "T4b"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_stage(stage: Optional[str]) -> str:
    raw = str(stage or "").strip().upper()
    if raw in {"T4", "T4A", "T4B"}:
        return "T4+"
    if raw == "T4+":
        return "T4+"
    return raw


def _is_t2_t3_adjacent(a: str, b: str) -> bool:
    return {_normalize_stage(a), _normalize_stage(b)} == {"T2", "T3"}


def build_case_episode_record(
    *,
    patient_id: str,
    case_token: str,
    cohort: str,
    agent_report: Dict[str, Any],
    feedback: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
    origin: str = "agent_analysis",
    path_or_uri: str = "",
) -> Dict[str, Any]:
    now = _utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": JsonlMemoryStore.new_record_id("ep"),
        "record_type": "case_episode",
        "created_at": now,
        "updated_at": now,
        "source": build_source(origin, path_or_uri, run_id=run_id, patient_id=patient_id),
        "case_episode": {
            "patient_id": patient_id,
            "case_token": case_token,
            "cohort": cohort,
            "modalities": ["ultrasound_image", "clinical_table", "similar_cases"],
            "agent_report": {
                "recommended_t_stage": agent_report.get("recommended_t_stage"),
                "confidence": agent_report.get("confidence"),
                "supporting_evidence": (agent_report.get("supporting_evidence") or [])[:6],
                "uncertainty_flags": (agent_report.get("uncertainty_flags") or [])[:6],
                "manual_review_recommended": bool(agent_report.get("uncertainty_flags")),
            },
            "feedback": feedback or {"feedback_type": "none"},
        },
    }


def reflect_error_to_candidates(
    *,
    patient_id: str,
    predicted_t: str,
    gold_t: str,
    error_type: Optional[str] = None,
    backend_id: str = "tstage_acc_boost2_screened_20260603",
    run_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """When pred != gold, emit procedural_rule / tool_governance candidates."""
    pred = _normalize_stage(predicted_t)
    gold = _normalize_stage(gold_t)
    if pred == gold:
        return []

    now = _utc_now()
    candidates: List[Dict[str, Any]] = []
    origin_path = f"reflect:{patient_id}:{now}"

    if _is_t2_t3_adjacent(pred, gold):
        candidates.append({
            "schema_version": SCHEMA_VERSION,
            "record_id": JsonlMemoryStore.new_record_id("pr"),
            "record_type": "procedural_rule",
            "created_at": now,
            "updated_at": now,
            "source": build_source("pathology_feedback", origin_path, run_id=run_id, patient_id=patient_id),
            "procedural_rule": {
                "rule_id": f"t2t3_boundary_{patient_id}_{now[:10]}",
                "title": "T2/T3 boundary case requires wall-layer and ROI quality review",
                "rule_text": (
                    f"Predicted {pred} vs gold {gold}. Prioritize lesion edge, gastric wall layers, "
                    "and predicted ROI coverage before trusting classifier top-1."
                ),
                "target_scenario": ["t2_t3_boundary", "t_staging_multimodal_review"],
                "priority": "high",
                "usage_count": 0,
                "observed_utility": 0.0,
            },
        })
        candidates.append({
            "schema_version": SCHEMA_VERSION,
            "record_id": JsonlMemoryStore.new_record_id("tg"),
            "record_type": "tool_governance",
            "created_at": now,
            "updated_at": now,
            "source": build_source("pathology_feedback", origin_path, run_id=run_id, patient_id=patient_id),
            "tool_governance": {
                "tool_name": "ClassificationTool",
                "backend_id": backend_id,
                "trust_label": "caution",
                "scenario": ["t2_t3_boundary"],
                "n_total": 1,
                "n_helpful": 0,
                "n_harmful": 1,
                "n_manual_review": 1,
                "rationale": f"T2/T3 confusion: pred={pred}, gold={gold}, error={error_type or 'adjacent_boundary'}",
            },
        })
    else:
        candidates.append({
            "schema_version": SCHEMA_VERSION,
            "record_id": JsonlMemoryStore.new_record_id("pr"),
            "record_type": "procedural_rule",
            "created_at": now,
            "updated_at": now,
            "source": build_source("pathology_feedback", origin_path, run_id=run_id, patient_id=patient_id),
            "procedural_rule": {
                "rule_id": f"staging_error_{patient_id}_{now[:10]}",
                "title": f"Staging mismatch review ({pred} vs {gold})",
                "rule_text": f"Case predicted {pred} but gold standard is {gold}. Require multimodal cross-check.",
                "target_scenario": ["t_staging_multimodal_review"],
                "priority": "medium",
                "usage_count": 0,
                "observed_utility": 0.0,
            },
        })

    return candidates


def write_episode_from_analysis(
    store: JsonlMemoryStore,
    payload: Dict[str, Any],
    report: Dict[str, Any],
    *,
    status: str = "active",
    episode_vector: Optional[List[float]] = None,
) -> StoreEntry:
    feedback = payload.get("feedback")
    record = build_case_episode_record(
        patient_id=str(payload.get("patient_id", "")),
        case_token=str(payload.get("case_token") or payload.get("patient_id") or ""),
        cohort=str(payload.get("dataset") or payload.get("data_source") or "unknown"),
        agent_report=report,
        feedback=feedback if isinstance(feedback, dict) else None,
        run_id=str(store.paths.root.name),
        path_or_uri=str(payload.get("trajectory_ref", {}).get("path", "")),
    )
    if episode_vector is not None:
        record["case_episode"]["_episode_vector"] = episode_vector
    return store.append_entry(
        record,
        status=status,
        quality_score=0.5,
        support_count=1,
        patient_id=str(payload.get("patient_id", "")),
        validate=False,  # _episode_vector is store-only extension
    )


def write_candidates_from_analysis(
    store: JsonlMemoryStore,
    candidates: List[Dict[str, Any]],
    patient_id: str,
) -> List[StoreEntry]:
    written: List[StoreEntry] = []
    for raw in candidates:
        record_type = str(raw.get("record_type", ""))
        if record_type not in {"procedural_rule", "tool_governance", "case_episode"}:
            continue
        now = _utc_now()
        record: Dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "record_id": JsonlMemoryStore.new_record_id(record_type[:2]),
            "record_type": record_type,
            "created_at": now,
            "updated_at": now,
            "source": build_source(
                "agent_analysis",
                f"candidate:{patient_id}:{now}",
                run_id=str(store.paths.root.name),
                patient_id=patient_id,
            ),
        }
        if record_type == "case_episode":
            record["case_episode"] = {
                "patient_id": patient_id,
                "case_token": raw.get("case_token", patient_id),
                "cohort": raw.get("cohort", "unknown"),
                "modalities": raw.get("modalities", []),
                "agent_report": {
                    "recommended_t_stage": raw.get("recommended_t_stage"),
                    "confidence": raw.get("confidence"),
                    "supporting_evidence": raw.get("supporting_evidence", []),
                    "uncertainty_flags": raw.get("uncertainty_flags", []),
                },
            }
        elif record_type == "procedural_rule":
            record["procedural_rule"] = {
                "rule_id": raw.get("rule_id") or JsonlMemoryStore.new_record_id("rule"),
                "title": raw.get("title", "Procedural candidate"),
                "rule_text": raw.get("rule_text") or raw.get("title", ""),
                "target_scenario": raw.get("target_scenario", ["t_staging_multimodal_review"]),
                "priority": raw.get("priority", "medium"),
                "usage_count": 0,
                "observed_utility": 0.0,
            }
        elif record_type == "tool_governance":
            record["tool_governance"] = {
                "tool_name": raw.get("tool_name", "unknown"),
                "backend_id": raw.get("backend_id", "unknown"),
                "trust_label": raw.get("trust_label", "unknown"),
                "scenario": raw.get("scenario", []),
                "n_total": int(raw.get("n_total", 0)),
                "n_helpful": int(raw.get("n_helpful", 0)),
                "n_harmful": int(raw.get("n_harmful", 0)),
                "n_manual_review": int(raw.get("n_manual_review", 0)),
                "rationale": raw.get("rationale", raw.get("title", "")),
            }
        entry = store.append_entry(
            record,
            status=str(raw.get("status", "candidate")),
            quality_score=0.5,
            support_count=1,
            patient_id=patient_id,
            validate=True,
            also_candidates=True,
        )
        written.append(entry)
    return written


def _update_quality(score: float, delta: float) -> float:
    return max(0.0, min(1.0, score + delta))


def promote_candidates(
    store: JsonlMemoryStore,
    *,
    min_support: int = 3,
    correct_delta: float = 0.05,
    wrong_delta: float = -0.08,
    allow_active_promotion: bool = False,
    doctor_review_status: str = "pending",
    gate_manifest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Promote candidate rules only with offline gate + doctor approval.

    Default keeps candidates non-active and only refreshes support counts.
    """
    stats: Dict[str, Any] = {
        "promoted": 0,
        "updated": 0,
        "rejected": 0,
        "blocked": 0,
        "active_promotion": False,
    }
    if not allow_active_promotion:
        for record_type in ("procedural_rule", "tool_governance"):
            path = store._file_for_type(record_type)
            entries = store.load_file(path)
            by_sig: Dict[str, List[StoreEntry]] = {}
            for entry in entries:
                if entry.status == "rejected":
                    continue
                by_sig.setdefault(entry.rule_signature, []).append(entry)
            changed = False
            for entry in entries:
                if entry.status != "candidate":
                    continue
                support = sum(max(1, g.support_count) for g in by_sig.get(entry.rule_signature, [entry]))
                if entry.support_count != support:
                    entry.support_count = support
                    entry.updated_at = _utc_now()
                    changed = True
                    stats["updated"] += 1
            if changed:
                store.rewrite_file(path, entries)
        stats["blocked"] = 1
        store.append_audit(
            "promote_blocked",
            {
                "reason": "allow_active_promotion=False; requires offline gate + doctor approval",
                "min_support": min_support,
            },
        )
        return stats

    if str(doctor_review_status).lower() != "approved":
        stats["blocked"] = 1
        store.append_audit(
            "promote_blocked",
            {"reason": "doctor_review_not_approved", "doctor_review_status": doctor_review_status},
        )
        return stats

    from agent.safety.evolution_gate import evaluate_candidate_manifest

    manifest = dict(gate_manifest or {})
    manifest.setdefault("candidate_id", f"promote_{store.paths.root.name}")
    manifest.setdefault("evolution_objects", ["evidence_navigation", "uncertainty_abstention"])
    manifest.setdefault("online_weight_update", False)
    manifest.setdefault("promotes_active_memory", False)
    manifest["doctor_review"] = {
        "status": "approved",
        "reviewer": (gate_manifest or {}).get("reviewer", "offline_gate"),
        "notes": (gate_manifest or {}).get("notes", "gated promote_candidates"),
    }
    gate = evaluate_candidate_manifest(manifest)
    if not gate.get("ok"):
        stats["blocked"] = 1
        stats["gate"] = gate
        store.append_audit("promote_blocked", {"reason": "evolution_gate_failed", "gate": gate})
        return stats

    for record_type in ("procedural_rule", "tool_governance"):
        path = store._file_for_type(record_type)
        entries = store.load_file(path)
        by_sig: Dict[str, List[StoreEntry]] = {}
        for entry in entries:
            if entry.status == "rejected":
                continue
            by_sig.setdefault(entry.rule_signature, []).append(entry)

        new_entries: List[StoreEntry] = []
        seen_sigs: set[str] = set()
        for entry in entries:
            if entry.status != "candidate":
                new_entries.append(entry)
                continue
            sig = entry.rule_signature
            if sig in seen_sigs:
                continue
            group = by_sig.get(sig, [entry])
            support = sum(max(1, g.support_count) for g in group)
            if support >= min_support:
                best = max(group, key=lambda g: g.quality_score)
                best.status = "active"
                best.support_count = support
                best.quality_score = _update_quality(best.quality_score, correct_delta)
                best.updated_at = _utc_now()
                pr = best.record.get("procedural_rule")
                if pr is not None:
                    pr["usage_count"] = int(pr.get("usage_count", 0)) + support
                tg = best.record.get("tool_governance")
                if tg is not None:
                    tg["n_total"] = int(tg.get("n_total", 0)) + support
                new_entries.append(best)
                stats["promoted"] += 1
                stats["active_promotion"] = True
                seen_sigs.add(sig)
            else:
                entry.support_count = support
                entry.updated_at = _utc_now()
                new_entries.append(entry)
                stats["updated"] += 1

        store.rewrite_file(path, new_entries)

    active_sigs = {
        e.rule_signature
        for rt in ("procedural_rule", "tool_governance")
        for e in store.load_file(store._file_for_type(rt))
        if e.status == "active"
    }
    cand_entries = store.load_file(store.paths.candidates)
    filtered = [e for e in cand_entries if e.rule_signature not in active_sigs or e.status == "candidate"]
    store.rewrite_file(store.paths.candidates, filtered)
    store.append_audit("promote_gated", {"stats": stats, "gate": gate})
    return stats


def reflect_batch_from_feedback_csv(
    store: JsonlMemoryStore,
    feedback_csv: Path,
    *,
    backend_id: str = "tstage_acc_boost2_screened_20260603",
) -> Dict[str, int]:
    stats = {"episodes": 0, "candidates": 0, "skipped": 0}
    if not feedback_csv.exists():
        raise FileNotFoundError(feedback_csv)

    with feedback_csv.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            patient_id = str(row.get("patient_id") or row.get("PatientID") or "")
            pred = row.get("predicted_t_stage") or row.get("pred_t") or row.get("recommended_t_stage")
            gold = row.get("gold_t_stage") or row.get("pathology_t") or row.get("final_t_stage")
            if not patient_id or not pred or not gold:
                stats["skipped"] += 1
                continue

            feedback = {
                "feedback_type": row.get("feedback_type", "pathology_result"),
                "final_t_stage": _normalize_stage(gold),
                "correction_text": row.get("correction_text", ""),
                "error_type": row.get("error_type", ""),
            }
            record = build_case_episode_record(
                patient_id=patient_id,
                case_token=str(row.get("case_token") or patient_id),
                cohort=str(row.get("cohort") or row.get("split") or "unknown"),
                agent_report={"recommended_t_stage": _normalize_stage(pred), "confidence": row.get("confidence", "medium")},
                feedback=feedback,
                run_id=str(store.paths.root.name),
                origin="pathology_feedback",
                path_or_uri=str(feedback_csv),
            )
            store.append_entry(record, status="candidate", patient_id=patient_id, validate=True)
            stats["episodes"] += 1

            for cand in reflect_error_to_candidates(
                patient_id=patient_id,
                predicted_t=str(pred),
                gold_t=str(gold),
                error_type=row.get("error_type"),
                backend_id=backend_id,
                run_id=str(store.paths.root.name),
            ):
                store.append_entry(
                    cand,
                    status="candidate",
                    quality_score=0.45,
                    support_count=1,
                    patient_id=patient_id,
                    also_candidates=True,
                )
                stats["candidates"] += 1

    store.append_audit("reflect_batch", {"feedback_csv": str(feedback_csv), **stats})
    return stats


def apply_feedback_action(
    store: JsonlMemoryStore,
    *,
    record_id: str,
    action: str,
    reviewer: str = "workbench",
    allow_active_promotion: bool = False,
) -> Optional[StoreEntry]:
    """Accept / reject / defer a candidate by record_id.

    Accept defaults to QA-defer (status stays candidate) unless
    allow_active_promotion=True for an offline gated CLI path.
    """
    action = action.lower()
    if action not in {"accept", "reject", "defer"}:
        raise ValueError(f"Unknown action: {action}")

    effective = action
    if action == "accept" and not allow_active_promotion:
        effective = "defer"

    for record_type in ("procedural_rule", "tool_governance", "case_episode"):
        path = store._file_for_type(record_type)
        entries = store.load_file(path)
        updated: Optional[StoreEntry] = None
        for idx, entry in enumerate(entries):
            if entry.record.get("record_id") != record_id:
                continue
            if effective == "accept" and allow_active_promotion:
                entry.status = "active"
                entry.support_count = max(entry.support_count, 3)
                entry.quality_score = _update_quality(entry.quality_score, 0.05)
            elif action == "reject":
                entry.status = "rejected"
                entry.quality_score = _update_quality(entry.quality_score, -0.1)
            else:
                entry.status = "candidate"
            entry.updated_at = _utc_now()
            entries[idx] = entry
            updated = entry
            break
        if updated:
            store.rewrite_file(path, entries)
            store.append_audit(
                "feedback_action",
                {
                    "record_id": record_id,
                    "action": action,
                    "applied_action": effective,
                    "active_promotion": bool(effective == "accept" and allow_active_promotion),
                    "reviewer": reviewer,
                },
            )
            return updated

    cand_path = store.paths.candidates
    entries = store.load_file(cand_path)
    for idx, entry in enumerate(entries):
        if entry.record.get("record_id") != record_id:
            continue
        if effective == "accept" and allow_active_promotion:
            entry.status = "active"
            rt = entry.record.get("record_type")
            if rt in {"procedural_rule", "tool_governance"}:
                store.upsert_by_signature(str(rt), entry)
        elif action == "reject":
            entry.status = "rejected"
        else:
            entry.status = "candidate"
        entries[idx] = entry
        store.rewrite_file(cand_path, entries)
        store.append_audit(
            "feedback_action",
            {
                "record_id": record_id,
                "action": action,
                "applied_action": effective,
                "active_promotion": bool(effective == "accept" and allow_active_promotion),
                "reviewer": reviewer,
            },
        )
        return entry
    return None


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Self-evolving memory evolver")
    p.add_argument("--action", required=True, choices=("reflect-batch", "promote", "feedback"))
    p.add_argument("--out-store", type=Path, default=None, help="Memory store root directory")
    p.add_argument("--feedback-csv", type=Path, default=None)
    p.add_argument("--min-support", type=int, default=3)
    p.add_argument("--record-id", default=None)
    p.add_argument("--feedback-action", choices=("accept", "reject", "defer"), default=None)
    p.add_argument("--backend-id", default="tstage_acc_boost2_screened_20260603")
    p.add_argument(
        "--allow-active-promotion",
        action="store_true",
        help="Opt-in active promotion; still requires doctor_review_status=approved for promote",
    )
    p.add_argument(
        "--doctor-review-status",
        default="pending",
        choices=("pending", "approved", "rejected", "needs_revision"),
    )
    return p.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    args = _parse_args()
    store_root = args.out_store or (PROJECT_ROOT / "pipeline/agent/memory/store_data/default")
    store = JsonlMemoryStore(store_root=store_root)

    if args.action == "reflect-batch":
        if not args.feedback_csv:
            raise SystemExit("--feedback-csv required for reflect-batch")
        stats = reflect_batch_from_feedback_csv(store, args.feedback_csv, backend_id=args.backend_id)
        logger.info("reflect-batch done: %s", stats)
        print(json.dumps(stats, indent=2))
    elif args.action == "promote":
        stats = promote_candidates(
            store,
            min_support=args.min_support,
            allow_active_promotion=bool(args.allow_active_promotion),
            doctor_review_status=args.doctor_review_status,
        )
        logger.info("promote done: %s", stats)
        print(json.dumps(stats, indent=2))
    elif args.action == "feedback":
        if not args.record_id or not args.feedback_action:
            raise SystemExit("--record-id and --feedback-action required for feedback")
        entry = apply_feedback_action(
            store,
            record_id=args.record_id,
            action=args.feedback_action,
            allow_active_promotion=bool(args.allow_active_promotion),
        )
        print(json.dumps(entry.to_line() if entry else {"status": "not_found"}, indent=2, default=str))


if __name__ == "__main__":
    main()
