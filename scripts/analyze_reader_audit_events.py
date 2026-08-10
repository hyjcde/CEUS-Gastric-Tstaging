#!/usr/bin/env python3
"""Analyze Next reader audit JSONL with QA exclusions applied.

Outputs case-level, doctor-level, AI-action, safety, and time summaries.
Research analyses must set --environment research and always load exclusions.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVENTS = ROOT / "apps/gastric_scan_next/data/reader_audit_events.jsonl"
DEFAULT_RUNTIME_EVENTS = ROOT / "apps/gastric_scan_next/runtime-data/reader_audit_events.jsonl"
DEFAULT_DEV_RUNTIME_EVENTS = Path("/tmp/gastric-scan-next/reader_audit_events.jsonl")
DEFAULT_EXCLUSIONS = ROOT / "docs/reader_audit_exclusions_20260801.json"
DEFAULT_OUT = ROOT / "docs/clinical_validation/reader_round2_exports"


def default_event_paths() -> list[Path]:
    candidates = [
        Path(os.environ["GASTRIC_RUNTIME_DATA_DIR"]) / "reader_audit_events.jsonl"
        if os.environ.get("GASTRIC_RUNTIME_DATA_DIR")
        else None,
        DEFAULT_RUNTIME_EVENTS,
        DEFAULT_DEV_RUNTIME_EVENTS,
        DEFAULT_EVENTS,
    ]
    result: list[Path] = []
    for path in candidates:
        if path is not None and path not in result and path.exists():
            result.append(path)
    return result


def load_exclusions(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "reader_ids": ["unknown_reader"],
            "rounds": ["qa"],
            "session_ids": [],
            "event_ids": [],
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "reader_ids": set(data.get("reader_ids", [])),
        "rounds": set(data.get("rounds", [])),
        "session_ids": set(data.get("session_ids", [])),
        "event_ids": set(data.get("event_ids", [])),
    }


def iter_events(path: Path):
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    """Promote event payload fields to the analysis row.

    Older browser clients wrote environment, action and timing fields inside
    payload. New clients write them at the top level. The analysis contract
    must accept both without changing the raw event.
    """
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return event
    merged = dict(payload)
    merged.update(event)
    merged["payload"] = payload
    # A payload-only `environment=research` was used by older smoke clients.
    # It is not research-grade because the server did not bind an authenticated
    # reader identity at the top level.
    if payload.get("environment") == "research" and event.get("environment") != "research":
        merged["environment"] = ""
    return merged


def is_excluded(ev: dict[str, Any], excl: dict[str, Any], allow_environments: set[str] | None) -> bool:
    rid = str(ev.get("reader_id") or "")
    rnd = str(ev.get("round") or "")
    sid = str(ev.get("session_id") or "")
    eid = str(ev.get("event_id") or "")
    env = str(ev.get("environment") or "")
    if env == "research" and not str(ev.get("authenticated_reader_id") or "").strip():
        return True
    if rid in excl["reader_ids"]:
        return True
    if rid.startswith("qa_smoke"):
        return True
    if rnd in excl["rounds"] and env != "research":
        # historical QA wrote round=round2; keep research round2
        if env in {"", "qa", "staging"} or rid in {"unknown_reader"}:
            return True
    if sid in excl["session_ids"] or eid in excl["event_ids"]:
        return True
    if allow_environments is not None and env and env not in allow_environments:
        return True
    if allow_environments is not None and not env and "research" in allow_environments:
        # missing environment is not research-grade
        return True
    return False


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_type = Counter(e.get("event_type") or e.get("type") or "unknown" for e in events)
    by_reader = Counter(e.get("reader_id") or "missing" for e in events)
    by_env = Counter(e.get("environment") or "missing" for e in events)
    actions = [
        e for e in events
        if (e.get("event_type") or e.get("type")) == "doctor_action"
    ]
    safety = []
    for e in actions:
        action = e.get("action_type") or e.get("doctor_action")
        if action in {"reject", "insufficient_evidence", "request_more_evidence"}:
            safety.append(e)
    return {
        "event_count": len(events),
        "event_type_counts": dict(by_type),
        "reader_counts": dict(by_reader),
        "environment_counts": dict(by_env),
        "doctor_action_count": len(actions),
        "safety_action_count": len(safety),
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def events_to_tables(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    case_rows: dict[tuple[str, str], dict[str, Any]] = {}
    action_rows: list[dict[str, Any]] = []
    time_rows: list[dict[str, Any]] = []
    safety_rows: list[dict[str, Any]] = []

    for e in events:
        rid = e.get("reader_id") or ""
        cid = e.get("case_id") or ""
        key = (rid, cid)
        slot = case_rows.setdefault(
            key,
            {
                "reader_id": rid,
                "case_id": cid,
                "session_id": e.get("session_id") or "",
                "authenticated_reader_id": e.get("authenticated_reader_id") or "",
                "environment": e.get("environment") or "",
                "round": e.get("round") or "",
                "condition": e.get("condition") or "ai_assisted",
                "event_count": 0,
                "has_ai_suggestion": False,
                "has_report": False,
                "doctor_initial_nature": "",
                "doctor_initial_t_stage": "",
                "doctor_action": "",
                "final_value": "",
                "ai_recommended_t_stage": "",
                "structured_signs": "",
                "lesion_extent": "",
                "wall_invasion_depth": "",
                "serosal_breakthrough": "",
                "growth_pattern": "",
            },
        )
        slot["event_count"] += 1
        et = e.get("event_type") or e.get("type") or ""
        if et == "ai_suggestion":
            slot["has_ai_suggestion"] = True
            slot["ai_suggestion_id"] = e.get("suggestion_id") or e.get("ai_suggestion_id") or ""
            slot["ai_recommended_t_stage"] = e.get("recommended_t_stage") or ""
            if e.get("structured_signs") is not None:
                slot["structured_signs"] = json.dumps(e["structured_signs"], ensure_ascii=False, sort_keys=True)
            if e.get("growth_pattern") is not None:
                slot["growth_pattern"] = json.dumps(e["growth_pattern"], ensure_ascii=False, sort_keys=True)
        if et == "report_generated":
            slot["has_report"] = True
        if et == "initial_judgment":
            slot["doctor_initial_nature"] = e.get("doctor_initial_nature") or ""
            slot["doctor_initial_t_stage"] = e.get("doctor_initial_t_stage") or ""
        if et == "doctor_action":
            action_payload = e.get("action") if isinstance(e.get("action"), dict) else {}
            action = (
                e.get("action_type")
                or e.get("doctor_action")
                or action_payload.get("action_type")
                or ""
            )
            slot["doctor_action"] = action
            slot["final_value"] = (
                e.get("after_value")
                or e.get("final_value")
                or action_payload.get("final_t_stage")
                or ""
            )
            slot["ai_recommended_t_stage"] = (
                e.get("before_value")
                or e.get("ai_recommended_t_stage")
                or action_payload.get("before_value")
                or ""
            )
            for field in (
                "structured_signs",
                "lesion_extent",
                "wall_invasion_depth",
                "serosal_breakthrough",
                "growth_pattern",
            ):
                if e.get(field) is not None:
                    slot[field] = json.dumps(e[field], ensure_ascii=False, sort_keys=True)
            evidence_ids = e.get("evidence_ids") or action_payload.get("evidence_ids") or []
            if not isinstance(evidence_ids, list):
                evidence_ids = [str(evidence_ids)]
            action_rows.append(
                {
                    "reader_id": rid,
                    "case_id": cid,
                    "authenticated_reader_id": e.get("authenticated_reader_id") or "",
                    "action_type": action,
                    "doctor_initial_nature": e.get("doctor_initial_nature") or action_payload.get("doctor_initial_nature") or "",
                    "doctor_initial_t_stage": e.get("doctor_initial_t_stage") or action_payload.get("doctor_initial_t_stage") or "",
                    "before_value": e.get("before_value") or action_payload.get("before_value") or "",
                    "after_value": e.get("after_value") or action_payload.get("after_value") or action_payload.get("final_t_stage") or "",
                    "reason": e.get("reason") or action_payload.get("reason") or "",
                    "evidence_ids": "|".join(str(item) for item in evidence_ids),
                    "suggestion_id": e.get("suggestion_id") or "",
                    "structured_signs": json.dumps(e.get("structured_signs") or {}, ensure_ascii=False, sort_keys=True),
                    "growth_pattern": json.dumps(e.get("growth_pattern") or {}, ensure_ascii=False, sort_keys=True),
                    "created_at": e.get("created_at") or e.get("timestamp") or "",
                }
            )
            if action in {"reject", "insufficient_evidence", "request_more_evidence"}:
                safety_rows.append(
                    {
                        "reader_id": rid,
                        "case_id": cid,
                        "safety_flag": action,
                        "created_at": e.get("created_at") or e.get("timestamp") or "",
                    }
                )
        timing = e.get("time_decomposition")
        timing = timing if isinstance(timing, dict) else {}
        time_event = {**timing, **e}
        if et in {"session_end", "case_completed"} or time_event.get("total_case_time_sec") is not None:
            time_rows.append(
                {
                    "reader_id": rid,
                    "case_id": cid,
                    "authenticated_reader_id": e.get("authenticated_reader_id") or "",
                    "condition": e.get("condition") or "ai_assisted",
                    "round": e.get("round") or "round2",
                    "total_case_time_sec": time_event.get("total_case_time_sec") or "",
                    "doctor_active_reading_sec": time_event.get("doctor_active_reading_sec") or "",
                    "ai_wait_sec": time_event.get("ai_wait_sec") or "",
                    "report_completion_sec": time_event.get("report_completion_sec") or "",
                    "first_interaction_sec": time_event.get("first_interaction_sec") or "",
                    "frame_dwell_sec_total": time_event.get("frame_dwell_sec_total") or "",
                    "created_at": e.get("created_at") or e.get("timestamp") or "",
                }
            )

    doctor_agg: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "reader_id": "",
        "cases_touched": 0,
        "events": 0,
        "ai_suggestions": 0,
        "reports": 0,
        "doctor_actions": 0,
    })
    for (rid, _cid), slot in case_rows.items():
        d = doctor_agg[rid]
        d["reader_id"] = rid
        d["cases_touched"] += 1
        d["events"] += int(slot["event_count"])
        d["ai_suggestions"] += int(bool(slot["has_ai_suggestion"]))
        d["reports"] += int(bool(slot["has_report"]))
        d["doctor_actions"] += int(bool(slot["doctor_action"]))

    return {
        "case": list(case_rows.values()),
        "doctor": list(doctor_agg.values()),
        "action": action_rows,
        "time": time_rows,
        "safety": safety_rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--events",
        type=Path,
        default=None,
        help="Single JSONL path; default scans configured/runtime/dev/legacy audit paths",
    )
    ap.add_argument("--exclusions", type=Path, default=DEFAULT_EXCLUSIONS)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--environment",
        default="research",
        help="Comma-separated allowed environments; empty means no env filter",
    )
    ap.add_argument("--include-excluded-summary", action="store_true")
    args = ap.parse_args()

    excl = load_exclusions(args.exclusions)
    allow = {x.strip() for x in args.environment.split(",") if x.strip()} or None
    event_paths = [args.events] if args.events else default_event_paths()
    kept: list[dict[str, Any]] = []
    dropped = 0
    seen_event_ids: set[str] = set()
    for event_path in event_paths:
        for raw_event in iter_events(event_path) or []:
            event_id = str(raw_event.get("event_id") or "")
            if event_id and event_id in seen_event_ids:
                continue
            if event_id:
                seen_event_ids.add(event_id)
            ev = normalize_event(raw_event)
            if is_excluded(ev, excl, allow):
                dropped += 1
                continue
            kept.append(ev)

    summary = summarize(kept)
    summary["excluded_event_count"] = dropped
    summary["events_path"] = [str(path) for path in event_paths]
    summary["exclusions_path"] = str(args.exclusions)
    summary["allowed_environments"] = sorted(allow) if allow else []

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    (out / "audit_events_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    tables = events_to_tables(kept)
    write_csv(out / "reader_case_level_from_audit.csv", tables["case"], [
        "reader_id", "authenticated_reader_id", "case_id", "session_id", "environment",
        "round", "condition", "event_count", "has_ai_suggestion", "has_report",
        "doctor_initial_nature", "doctor_initial_t_stage", "doctor_action", "final_value",
        "ai_suggestion_id", "ai_recommended_t_stage",
        "structured_signs", "lesion_extent", "wall_invasion_depth",
        "serosal_breakthrough", "growth_pattern",
    ])
    write_csv(out / "reader_doctor_level_from_audit.csv", tables["doctor"], [
        "reader_id", "cases_touched", "events", "ai_suggestions", "reports", "doctor_actions",
    ])
    write_csv(out / "reader_ai_action_level.csv", tables["action"], [
        "reader_id", "authenticated_reader_id", "case_id", "action_type",
        "doctor_initial_nature", "doctor_initial_t_stage", "before_value", "after_value",
        "reason", "evidence_ids", "suggestion_id", "structured_signs", "growth_pattern",
        "created_at",
    ])
    write_csv(out / "reader_time_decomposition.csv", tables["time"], [
        "reader_id", "authenticated_reader_id", "case_id", "condition", "round", "total_case_time_sec",
        "doctor_active_reading_sec", "ai_wait_sec", "report_completion_sec",
        "first_interaction_sec", "frame_dwell_sec_total", "created_at",
    ])
    write_csv(out / "reader_safety_events.csv", tables["safety"], [
        "reader_id", "case_id", "safety_flag", "created_at",
    ])
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
