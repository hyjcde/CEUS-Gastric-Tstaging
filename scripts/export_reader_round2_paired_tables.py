#!/usr/bin/env python3
"""Export paired Round1/Round2 analysis tables.

Round2 doctor events may still be empty. This script always builds:
  - Round1 baseline case/doctor tables from the frozen Round2 manifest
  - Paired skeleton ready for Round2 fill-in
  - Report-quality score template
  - Export status JSON

When Round2 research audit events exist, pass --round2-case-csv produced by
analyze_reader_audit_events.py (or a cleaned case-level export) to compute
paired uplift / safety fields.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/registry/reader_round2_ai_assisted_manifest.csv"
FREEZE = ROOT / "data/registry/reader_round2_study_freeze_20260810.json"
DEFAULT_OUT = ROOT / "docs/clinical_validation/reader_round2_exports"

T_ORDER = {"T1": 1, "T2": 2, "T3": 3, "T4": 4, "T4+": 4, "A": 1, "B": 2, "C": 3, "D": 4}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: "" if r.get(k) is None else r.get(k) for k in fieldnames})


def norm_t(v: str | None) -> str:
    if not v:
        return ""
    raw = str(v).strip().upper().replace("期", "").replace(" ", "")
    # Chinese labels like "T3期"; letter codes A/B/C/D from early exports.
    mapping = {
        "A": "T1",
        "B": "T2",
        "C": "T3",
        "D": "T4+",
        "T1": "T1",
        "T2": "T2",
        "T3": "T3",
        "T4": "T4+",
        "T4+": "T4+",
        "T4PLUS": "T4+",
    }
    if raw in mapping:
        return mapping[raw]
    for key in ("T4+", "T4", "T3", "T2", "T1"):
        if key in raw:
            return mapping.get(key, key)
    return raw


def stage_rank(v: str) -> int | None:
    return T_ORDER.get(norm_t(v))


def boolish(v: Any) -> bool:
    return str(v).lower() in {"1", "true", "yes", "y"}


def build_round1_tables(manifest_rows: list[dict[str, str]]) -> tuple[list[dict], list[dict]]:
    case_rows = []
    doctor = defaultdict(lambda: {
        "reader_id": "",
        "n_cases": 0,
        "n_pairable": 0,
        "n_bm": 0,
        "n_tstage": 0,
        "bm_correct": 0,
        "bm_scored": 0,
        "t_correct": 0,
        "t_scored": 0,
        "reading_time_sum": 0.0,
        "reading_time_n": 0,
    })
    for r in manifest_rows:
        rid = r["reader_id"]
        mode = r.get("study_mode") or ""
        pairable = boolish(r.get("baseline_pairable"))
        nature_ref = r.get("reference_nature_secure") or ""
        pt_ref = norm_t(r.get("reference_pt_secure") or "")
        nature_doc = r.get("round1_nature") or ""
        t_doc = norm_t(r.get("round1_t_stage") or "")
        nature_ok = None
        t_ok = None
        if mode == "benign_malignancy" and nature_ref and nature_doc:
            nature_ok = nature_doc == nature_ref
        if mode == "t_staging" and pt_ref and t_doc:
            t_ok = t_doc == pt_ref
        case_rows.append(
            {
                "pair_key": r.get("pair_key") or f"{rid}::{r['case_id']}",
                "reader_id": rid,
                "case_id": r["case_id"],
                "study_mode": mode,
                "condition": "no_ai",
                "round": "round1",
                "baseline_pairable": pairable,
                "completed": boolish(r.get("round1_completed")),
                "doctor_final_nature": nature_doc,
                "doctor_final_t_stage": t_doc,
                "reference_nature_secure": nature_ref,
                "reference_pt_secure": pt_ref,
                "nature_correct_final": nature_ok,
                "t_stage_correct_final": t_ok,
                "reading_time_sec": r.get("round1_reading_time_sec") or "",
                "frame_dwell_sec_total": r.get("round1_frame_dwell_sec_total") or "",
                "round2_status": r.get("round2_status") or "not_started",
            }
        )
        d = doctor[rid]
        d["reader_id"] = rid
        d["n_cases"] += 1
        d["n_pairable"] += int(pairable)
        if mode == "benign_malignancy":
            d["n_bm"] += 1
            if nature_ok is not None:
                d["bm_scored"] += 1
                d["bm_correct"] += int(nature_ok)
        if mode == "t_staging":
            d["n_tstage"] += 1
            if t_ok is not None:
                d["t_scored"] += 1
                d["t_correct"] += int(t_ok)
        try:
            d["reading_time_sum"] += float(r.get("round1_reading_time_sec") or 0)
            d["reading_time_n"] += 1
        except ValueError:
            pass

    doctor_rows = []
    for rid, d in sorted(doctor.items()):
        doctor_rows.append(
            {
                **d,
                "bm_accuracy": round(d["bm_correct"] / d["bm_scored"], 4) if d["bm_scored"] else "",
                "t_accuracy": round(d["t_correct"] / d["t_scored"], 4) if d["t_scored"] else "",
                "mean_reading_time_sec": round(d["reading_time_sum"] / d["reading_time_n"], 2)
                if d["reading_time_n"]
                else "",
                "include_in_primary_complete150": str(d["n_pairable"] == 150).lower(),
            }
        )
    return case_rows, doctor_rows


def build_paired_skeleton(
    manifest_rows: list[dict[str, str]],
    round2_by_key: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    rows = []
    for r in manifest_rows:
        key = r.get("pair_key") or f"{r['reader_id']}::{r['case_id']}"
        r2 = round2_by_key.get(key, {})
        mode = r.get("study_mode") or ""
        r1_t = norm_t(r.get("round1_t_stage") or "")
        r1_n = r.get("round1_nature") or ""
        r2_t = norm_t(r2.get("doctor_final_t_stage") or r2.get("final_value") or "")
        r2_n = r2.get("doctor_final_nature") or ""
        ref_t = norm_t(r.get("reference_pt_secure") or "")
        ref_n = r.get("reference_nature_secure") or ""
        pairable = boolish(r.get("baseline_pairable"))
        r1_t_ok = (r1_t == ref_t) if (mode == "t_staging" and r1_t and ref_t) else None
        r2_t_ok = (r2_t == ref_t) if (mode == "t_staging" and r2_t and ref_t) else None
        r1_n_ok = (r1_n == ref_n) if (mode == "benign_malignancy" and r1_n and ref_n) else None
        r2_n_ok = (r2_n == ref_n) if (mode == "benign_malignancy" and r2_n and ref_n) else None

        ai_corrected = None
        ai_induced = None
        if mode == "t_staging" and r1_t_ok is not None and r2_t_ok is not None:
            ai_corrected = (r1_t_ok is False) and (r2_t_ok is True)
            ai_induced = (r1_t_ok is True) and (r2_t_ok is False)
        elif mode == "benign_malignancy" and r1_n_ok is not None and r2_n_ok is not None:
            ai_corrected = (r1_n_ok is False) and (r2_n_ok is True)
            ai_induced = (r1_n_ok is True) and (r2_n_ok is False)

        over = under = b23 = b34 = None
        if mode == "t_staging" and r2_t and ref_t:
            a, b = stage_rank(r2_t), stage_rank(ref_t)
            if a is not None and b is not None:
                over = a > b
                under = a < b
                truth, pred = norm_t(ref_t), norm_t(r2_t)
                b23 = {truth, pred} == {"T2", "T3"} and truth != pred
                b34 = {truth, pred} == {"T3", "T4+"} and truth != pred

        rows.append(
            {
                "pair_key": key,
                "reader_id": r["reader_id"],
                "case_id": r["case_id"],
                "study_mode": mode,
                "baseline_pairable": pairable,
                "round1_completed": boolish(r.get("round1_completed")),
                "round1_nature": r1_n,
                "round1_t_stage": r1_t,
                "round1_nature_correct": r1_n_ok,
                "round1_t_correct": r1_t_ok,
                "round1_reading_time_sec": r.get("round1_reading_time_sec") or "",
                "round2_status": r2.get("round2_status") or r.get("round2_status") or "not_started",
                "round2_completed": boolish(r2.get("completed")) if r2 else False,
                "round2_nature": r2_n,
                "round2_t_stage": r2_t,
                "round2_nature_correct": r2_n_ok,
                "round2_t_correct": r2_t_ok,
                "round2_doctor_initial_nature": r2.get("doctor_initial_nature") or "",
                "round2_doctor_initial_t_stage": r2.get("doctor_initial_t_stage") or "",
                "doctor_action": r2.get("doctor_action") or "",
                "ai_recommended_t_stage": r2.get("ai_recommended_t_stage") or "",
                "round2_structured_signs": r2.get("structured_signs") or "",
                "round2_lesion_extent": r2.get("lesion_extent") or "",
                "round2_wall_invasion_depth": r2.get("wall_invasion_depth") or "",
                "round2_serosal_breakthrough": r2.get("serosal_breakthrough") or "",
                "round2_growth_pattern": r2.get("growth_pattern") or "",
                "round2_total_case_time_sec": r2.get("total_case_time_sec") or "",
                "round2_doctor_active_reading_sec": r2.get("doctor_active_reading_sec") or "",
                "round2_ai_wait_sec": r2.get("ai_wait_sec") or "",
                "round2_report_completion_sec": r2.get("report_completion_sec") or "",
                "ai_corrected_error": ai_corrected,
                "ai_induced_error": ai_induced,
                "boundary_error_t2_t3": b23,
                "boundary_error_t3_t4": b34,
                "overstaging": over,
                "understaging": under,
                "reference_nature_secure": ref_n,
                "reference_pt_secure": ref_t,
            }
        )
    return rows


def report_quality_template() -> list[dict[str, Any]]:
    # header-only useful template row examples
    return [
        {
            "score_id": "example_ai_draft",
            "case_id": "CASE-001",
            "reader_id": "Doctor_01",
            "condition": "ai_assisted",
            "report_target": "ai_draft",
            "rater_id": "rater_A",
            "blinded_to_condition": True,
            "completeness": "",
            "facticity": "",
            "key_tstage_evidence": "",
            "conflict_uncertainty_expression": "",
            "traceability": "",
            "clinical_usability": "",
            "mean_score": "",
            "overall_usable": "",
            "comments": "template only; do not analyze",
            "created_at": "",
        },
        {
            "score_id": "example_doctor_final",
            "case_id": "CASE-001",
            "reader_id": "Doctor_01",
            "condition": "ai_assisted",
            "report_target": "doctor_final_report",
            "rater_id": "rater_A",
            "blinded_to_condition": True,
            "completeness": "",
            "facticity": "",
            "key_tstage_evidence": "",
            "conflict_uncertainty_expression": "",
            "traceability": "",
            "clinical_usability": "",
            "mean_score": "",
            "overall_usable": "",
            "comments": "template only; do not analyze",
            "created_at": "",
        },
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--freeze", type=Path, default=FREEZE)
    ap.add_argument("--round2-case-csv", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    manifest_rows = read_csv(args.manifest)
    freeze = json.loads(args.freeze.read_text(encoding="utf-8")) if args.freeze.exists() else {}
    round2_by_key: dict[str, dict[str, str]] = {}
    if args.round2_case_csv and args.round2_case_csv.exists():
        for row in read_csv(args.round2_case_csv):
            key = row.get("pair_key") or f"{row.get('reader_id')}::{row.get('case_id')}"
            round2_by_key[key] = row

    case_r1, doctor_r1 = build_round1_tables(manifest_rows)
    paired = build_paired_skeleton(manifest_rows, round2_by_key)
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    write_csv(out / "round1_case_level.csv", case_r1, list(case_r1[0].keys()) if case_r1 else [])
    write_csv(out / "round1_doctor_level.csv", doctor_r1, list(doctor_r1[0].keys()) if doctor_r1 else [])
    write_csv(out / "paired_round1_round2_skeleton.csv", paired, list(paired[0].keys()) if paired else [])
    write_csv(
        out / "report_quality_scores_template.csv",
        report_quality_template(),
        [
            "score_id", "case_id", "reader_id", "condition", "report_target", "rater_id",
            "blinded_to_condition", "completeness", "facticity", "key_tstage_evidence",
            "conflict_uncertainty_expression", "traceability", "clinical_usability",
            "mean_score", "overall_usable", "comments", "created_at",
        ],
    )

    n_r2_done = sum(1 for r in paired if boolish(r.get("round2_completed")))
    status = {
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "freeze_id": freeze.get("freeze_id", "reader_round2_freeze_20260810"),
        "execution_status": freeze.get("execution_status", "prepared_not_run"),
        "manifest_rows": len(manifest_rows),
        "round1_case_rows": len(case_r1),
        "round1_doctor_rows": len(doctor_r1),
        "paired_rows": len(paired),
        "round2_completed_rows": n_r2_done,
        "round2_input_provided": bool(args.round2_case_csv),
        "note": "Round2 clinical claims blocked until round2_completed_rows > 0 with research environment events",
        "outputs": [
            "round1_case_level.csv",
            "round1_doctor_level.csv",
            "paired_round1_round2_skeleton.csv",
            "report_quality_scores_template.csv",
        ],
    }
    (out / "export_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
