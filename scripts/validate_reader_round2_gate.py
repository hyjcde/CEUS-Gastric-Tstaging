#!/usr/bin/env python3
"""Validate Round2 human-AI reader study go/no-go gate.

Exits 0 only when research Round2 data and expertise registration clear the gate.
Use --allow-prepared to exit 0 while documenting prepared_not_run scaffolding.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "data/registry/reader_round2_study_freeze_20260810.json"
EXPERTISE = ROOT / "data/registry/reader_expertise_registry_20260810.csv"
MANIFEST = ROOT / "data/registry/reader_round2_ai_assisted_manifest.csv"
ORDER = ROOT / "data/registry/reader_round2_case_order_20260810.csv"
EXPORT_STATUS = ROOT / "docs/clinical_validation/reader_round2_exports/export_status.json"
AUDIT_SUMMARY = ROOT / "docs/clinical_validation/reader_round2_exports/audit_events_summary.json"
CASE_AUDIT = ROOT / "docs/clinical_validation/reader_round2_exports/reader_case_level_from_audit.csv"
EXCLUSIONS = ROOT / "docs/reader_audit_exclusions_20260801.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--allow-prepared",
        action="store_true",
        help="Exit 0 when scaffolding is ready even if Round2 is not run",
    )
    args = ap.parse_args()

    checks: list[dict] = []
    freeze = json.loads(FREEZE.read_text(encoding="utf-8")) if FREEZE.exists() else {}

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("freeze_json_exists", FREEZE.exists(), str(FREEZE))
    add("manifest_exists", MANIFEST.exists(), str(MANIFEST))
    add("case_order_exists", ORDER.exists(), str(ORDER))
    add("expertise_exists", EXPERTISE.exists(), str(EXPERTISE))
    add("export_status_exists", EXPORT_STATUS.exists(), str(EXPORT_STATUS))

    if MANIFEST.exists() and freeze.get("manifest", {}).get("sha256"):
        got = sha256(MANIFEST)
        add("manifest_sha256", got == freeze["manifest"]["sha256"], f"got={got}")
    if ORDER.exists() and freeze.get("case_order", {}).get("sha256"):
        got = sha256(ORDER)
        add("case_order_sha256", got == freeze["case_order"]["sha256"], f"got={got}")

    primary_registered = 0
    primary_pending = 0
    if EXPERTISE.exists():
        rows = list(csv.DictReader(EXPERTISE.open(encoding="utf-8")))
        for r in rows:
            if str(r.get("include_in_primary_complete150")).lower() != "true":
                continue
            if r.get("registration_status") == "registered" and r.get("expertise_tier_primary") in {
                "junior",
                "senior",
                "intermediate",
            }:
                primary_registered += 1
            else:
                primary_pending += 1
    add(
        "expertise_primary_registered",
        primary_registered >= 14 and primary_pending == 0,
        f"registered={primary_registered}, pending={primary_pending}",
    )

    r2_done = 0
    if EXPORT_STATUS.exists():
        st = json.loads(EXPORT_STATUS.read_text(encoding="utf-8"))
        r2_done = int(st.get("round2_completed_rows") or 0)
        add("export_status_readable", True, st.get("execution_status", ""))

    completed_from_audit = 0
    completed_with_initial = 0
    if CASE_AUDIT.exists():
        for row in csv.DictReader(CASE_AUDIT.open(encoding="utf-8")):
            valid = str(row.get("research_valid_completion")).lower() in {"1", "true", "yes"}
            completed = str(row.get("completed")).lower() in {"1", "true", "yes"}
            if not (valid or (
                completed
                and str(row.get("environment") or "") == "research"
                and str(row.get("authenticated_reader_id") or "").strip()
                and str(row.get("has_initial_judgment")).lower() in {"1", "true", "yes"}
            )):
                continue
            completed_from_audit += 1
            if str(row.get("has_initial_judgment")).lower() in {"1", "true", "yes"}:
                completed_with_initial += 1
    effective_completed = max(r2_done, completed_from_audit)
    add(
        "round2_completed_rows_gt0",
        effective_completed > 0,
        f"export_status={r2_done}, research_valid_completed={completed_from_audit}",
    )
    add(
        "round2_completed_with_initial_judgment",
        effective_completed == 0 or completed_with_initial == effective_completed,
        f"completed_with_initial={completed_with_initial}, research_valid_completed={completed_from_audit}",
    )

    research_events = 0
    research_completed_summary = 0
    if AUDIT_SUMMARY.exists():
        summary = json.loads(AUDIT_SUMMARY.read_text(encoding="utf-8"))
        research_events = int(summary.get("event_count") or 0)
        research_completed_summary = int(summary.get("completed_case_count") or 0)
    add(
        "research_completed_cases_gt0",
        max(research_completed_summary, completed_from_audit) > 0,
        f"summary_completed={research_completed_summary}, audit_completed={completed_from_audit}, events={research_events}",
    )
    add("exclusions_file_exists", EXCLUSIONS.exists(), str(EXCLUSIONS))

    clinical_ready = all(
        c["ok"]
        for c in checks
        if c["name"]
        in {
            "freeze_json_exists",
            "manifest_exists",
            "case_order_exists",
            "expertise_exists",
            "manifest_sha256",
            "case_order_sha256",
            "expertise_primary_registered",
            "round2_completed_rows_gt0",
            "round2_completed_with_initial_judgment",
            "research_completed_cases_gt0",
            "exclusions_file_exists",
        }
    )
    scaffold_ready = all(
        c["ok"]
        for c in checks
        if c["name"]
        in {
            "freeze_json_exists",
            "manifest_exists",
            "case_order_exists",
            "expertise_exists",
            "export_status_exists",
            "manifest_sha256",
            "case_order_sha256",
        }
    )

    report = {
        "freeze_id": freeze.get("freeze_id"),
        "execution_status": freeze.get("execution_status", "unknown"),
        "clinical_claims_allowed": clinical_ready,
        "scaffold_ready": scaffold_ready,
        "checks": checks,
        "note": (
            "Clinical AI-assisted uplift claims are blocked until expertise is registered "
            "and Round2 research events produce completed paired rows."
        ),
    }
    out = ROOT / "docs/clinical_validation/reader_round2_exports/round2_gate_status.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if clinical_ready:
        return 0
    if args.allow_prepared and scaffold_ready:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
