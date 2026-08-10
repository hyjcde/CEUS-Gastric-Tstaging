#!/usr/bin/env python3
"""Analyze Round1 baseline and Round2 expertise uplift endpoints.

Without Round2 completed pairs, writes blocked uplift/safety summaries and still
emits Round1 doctor-level baseline tables for the paper evidence chain.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAIRED = ROOT / "docs/clinical_validation/reader_round2_exports/paired_round1_round2_skeleton.csv"
DEFAULT_ROUND1_DOC = ROOT / "docs/clinical_validation/reader_round2_exports/round1_doctor_level.csv"
DEFAULT_EXPERTISE = ROOT / "data/registry/reader_expertise_registry_20260810.csv"
DEFAULT_OUT = ROOT / "docs/clinical_validation/reader_round2_exports"


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


def boolish(v: Any) -> bool:
    return str(v).lower() in {"1", "true", "yes", "y"}


def mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt((p * (1 - p) / n) + (z * z / (4 * n * n)))
    return center - half, center + half


def parse_bool_or_none(v: Any) -> bool | None:
    if v is None or v == "":
        return None
    s = str(v).lower()
    if s in {"true", "1", "yes"}:
        return True
    if s in {"false", "0", "no"}:
        return False
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--paired", type=Path, default=DEFAULT_PAIRED)
    ap.add_argument("--round1-doctor", type=Path, default=DEFAULT_ROUND1_DOC)
    ap.add_argument("--expertise", type=Path, default=DEFAULT_EXPERTISE)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    paired = read_csv(args.paired) if args.paired.exists() else []
    round1_doc = read_csv(args.round1_doctor) if args.round1_doctor.exists() else []
    expertise = {r["reader_id"]: r for r in read_csv(args.expertise)} if args.expertise.exists() else {}

    # Round1 doctor baseline with expertise join
    doctor_rows = []
    for r in round1_doc:
        rid = r["reader_id"]
        ex = expertise.get(rid, {})
        doctor_rows.append(
            {
                "reader_id": rid,
                "include_in_primary_complete150": r.get("include_in_primary_complete150"),
                "n_pairable": r.get("n_pairable"),
                "bm_accuracy_no_ai": r.get("bm_accuracy"),
                "t_accuracy_no_ai": r.get("t_accuracy"),
                "mean_reading_time_sec_no_ai": r.get("mean_reading_time_sec"),
                "title": ex.get("title", ""),
                "gi_us_years": ex.get("gi_us_years", ""),
                "expertise_tier_primary": ex.get("expertise_tier_primary", "pending"),
                "registration_status": ex.get("registration_status", "missing"),
                "center": ex.get("center", ""),
            }
        )

    primary = [r for r in doctor_rows if boolish(r.get("include_in_primary_complete150"))]
    t_acc = [float(r["t_accuracy_no_ai"]) for r in primary if r.get("t_accuracy_no_ai") not in ("", None)]
    bm_acc = [float(r["bm_accuracy_no_ai"]) for r in primary if r.get("bm_accuracy_no_ai") not in ("", None)]

    paired_primary = [
        r
        for r in paired
        if boolish(r.get("baseline_pairable"))
        and boolish(expertise.get(r["reader_id"], {}).get("include_in_primary_complete150"))
    ]
    r2_done = [r for r in paired_primary if boolish(r.get("round2_completed"))]
    t_pairs = [r for r in r2_done if r.get("study_mode") == "t_staging"]
    bm_pairs = [r for r in r2_done if r.get("study_mode") == "benign_malignancy"]

    def rate(rows: list[dict], key: str) -> dict[str, Any]:
        vals = [parse_bool_or_none(r.get(key)) for r in rows]
        scored = [v for v in vals if v is not None]
        k = sum(1 for v in scored if v)
        n = len(scored)
        lo, hi = wilson_ci(k, n)
        return {
            "k": k,
            "n": n,
            "rate": (k / n) if n else None,
            "ci95_low": lo,
            "ci95_high": hi,
        }

    # Doctor-level paired uplift when Round2 present
    uplift_rows = []
    by_doc: dict[str, list[dict]] = defaultdict(list)
    for r in r2_done:
        by_doc[r["reader_id"]].append(r)
    for rid, rows in sorted(by_doc.items()):
        ex = expertise.get(rid, {})
        t_rows = [x for x in rows if x.get("study_mode") == "t_staging"]
        r1_t = [parse_bool_or_none(x.get("round1_t_correct")) for x in t_rows]
        r2_t = [parse_bool_or_none(x.get("round2_t_correct")) for x in t_rows]
        r1_t = [v for v in r1_t if v is not None]
        r2_t = [v for v in r2_t if v is not None]
        acc1 = (sum(r1_t) / len(r1_t)) if r1_t else None
        acc2 = (sum(r2_t) / len(r2_t)) if r2_t else None
        uplift_rows.append(
            {
                "reader_id": rid,
                "expertise_tier_primary": ex.get("expertise_tier_primary", "pending"),
                "n_t_pairs": len(r1_t),
                "t_acc_no_ai": None if acc1 is None else round(acc1, 4),
                "t_acc_ai_assisted": None if acc2 is None else round(acc2, 4),
                "t_uplift": None if (acc1 is None or acc2 is None) else round(acc2 - acc1, 4),
                "ai_corrected_n": sum(1 for x in t_rows if parse_bool_or_none(x.get("ai_corrected_error")) is True),
                "ai_induced_n": sum(1 for x in t_rows if parse_bool_or_none(x.get("ai_induced_error")) is True),
            }
        )

    # Expertise interaction placeholders
    tiers = sorted({r.get("expertise_tier_primary") or "pending" for r in uplift_rows})
    tier_summary = []
    for tier in tiers:
        subset = [r for r in uplift_rows if r.get("expertise_tier_primary") == tier]
        ups = [float(r["t_uplift"]) for r in subset if r.get("t_uplift") not in (None, "")]
        tier_summary.append(
            {
                "expertise_tier_primary": tier,
                "n_readers": len(subset),
                "mean_t_uplift": None if not ups else round(mean(ups) or 0.0, 4),
            }
        )

    registered_primary = sum(
        1
        for r in doctor_rows
        if boolish(r.get("include_in_primary_complete150")) and r.get("registration_status") == "registered"
    )
    blocked = len(r2_done) == 0 or registered_primary < 14

    summary = {
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "freeze_id": "reader_round2_freeze_20260810",
        "status": "blocked_until_round2_data" if blocked else "estimated",
        "primary_complete150_readers": len(primary),
        "expertise_primary_registered": registered_primary,
        "round1_primary_mean_t_accuracy": None if not t_acc else round(mean(t_acc) or 0.0, 4),
        "round1_primary_mean_bm_accuracy": None if not bm_acc else round(mean(bm_acc) or 0.0, 4),
        "round2_completed_primary_rows": len(r2_done),
        "round2_t_pairs": len(t_pairs),
        "round2_bm_pairs": len(bm_pairs),
        "endpoints": {
            "primary_t_uplift": "not_estimable" if blocked else rate(t_pairs, "round2_t_correct"),
            "ai_corrected_error": "not_estimable" if blocked else rate(t_pairs, "ai_corrected_error"),
            "ai_induced_error": "not_estimable" if blocked else rate(t_pairs, "ai_induced_error"),
            "boundary_error_t2_t3": "not_estimable" if blocked else rate(t_pairs, "boundary_error_t2_t3"),
            "boundary_error_t3_t4": "not_estimable" if blocked else rate(t_pairs, "boundary_error_t3_t4"),
            "junior_ai_vs_senior_no_ai": "not_estimable_until_expertise_and_round2",
            "condition_x_expertise_interaction": "not_estimable_until_expertise_and_round2",
        },
        "claims_allowed": {
            "round1_no_ai_baseline": True,
            "ai_assisted_uplift": not blocked,
            "junior_exceeds_senior_no_ai": False,
            "report_quality_improvement": False,
            "inter_reader_variance_reduction": False,
        },
        "limitations": [
            "Fixed order no_ai then ai_assisted; learning/order effects cannot be balanced yet",
            "Expertise registry currently pending for primary readers",
            "No research Round2 completed pairs at analysis time" if len(r2_done) == 0 else "",
        ],
        "tier_summary": tier_summary,
    }
    summary["limitations"] = [x for x in summary["limitations"] if x]

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(
        out / "round1_expertise_join_doctor_level.csv",
        doctor_rows,
        list(doctor_rows[0].keys()) if doctor_rows else [],
    )
    write_csv(
        out / "round2_expertise_uplift_doctor_level.csv",
        uplift_rows,
        [
            "reader_id",
            "expertise_tier_primary",
            "n_t_pairs",
            "t_acc_no_ai",
            "t_acc_ai_assisted",
            "t_uplift",
            "ai_corrected_n",
            "ai_induced_n",
        ],
    )
    (out / "expertise_uplift_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
