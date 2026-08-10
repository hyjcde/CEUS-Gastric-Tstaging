#!/usr/bin/env python3
"""Build Round2 expertise registry and seeded case-order freeze tables.

Creates:
  data/registry/reader_expertise_registry_20260810.csv
  data/registry/reader_round2_case_order_20260810.csv
  data/registry/reader_round2_case_order_20260810.summary.json

Expertise tiers are PRESET before unblinding. Known early-subset profiles are
kept as a separate reference cohort and are NOT auto-mapped onto Doctor_XX IDs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/registry/reader_round2_ai_assisted_manifest.csv"
EXPERTISE_OUT = ROOT / "data/registry/reader_expertise_registry_20260810.csv"
ORDER_OUT = ROOT / "data/registry/reader_round2_case_order_20260810.csv"
ORDER_SUMMARY = ROOT / "data/registry/reader_round2_case_order_20260810.summary.json"
EARLY_PROFILES = ROOT / "data/registry/reader_early_subset_profiles_20260810.csv"

SEED = 20260810

# Early 100-case multi-reader exports (NOT Round1 Doctor_XX IDs).
EARLY_SUBSET_PROFILES = [
    {
        "cohort": "early_100_ai_favorable_subset",
        "raw_id": "zy01",
        "reader_label": "Doctor 1 (early subset)",
        "title": "住院医师",
        "hospital_level": "三级甲等",
        "province": "福建省",
        "gi_us_years": 5,
        "source_file": "docs/clinical_validation/reader_study_150/multireader_5readers_en/reader_inputs/reader_session_mq81svs5_1781615436647.json",
    },
    {
        "cohort": "early_100_ai_favorable_subset",
        "raw_id": "qqf",
        "reader_label": "Doctor 3 (early subset)",
        "title": "主治医师",
        "hospital_level": "三级甲等",
        "province": "",
        "gi_us_years": 10,
        "source_file": "docs/clinical_validation/reader_study_150/multireader_5readers_en/reader_inputs/reader_session_mqhlqtpi_1781700024643.json",
    },
    {
        "cohort": "early_100_ai_favorable_subset",
        "raw_id": "czk",
        "reader_label": "Doctor 4 (early subset)",
        "title": "主任医师",
        "hospital_level": "三级甲等",
        "province": "",
        "gi_us_years": 10,
        "source_file": "docs/clinical_validation/reader_study_150/multireader_5readers_en/reader_inputs/reader_session_mqjb3wb2_1781824329689.json",
    },
    {
        "cohort": "early_100_ai_favorable_subset",
        "raw_id": "cyh",
        "reader_label": "Doctor 5 (early subset)",
        "title": "主治医师",
        "hospital_level": "三级甲等",
        "province": "",
        "gi_us_years": 7,
        "source_file": "docs/clinical_validation/reader_study_150/multireader_5readers_en/reader_inputs/reader_session_mqjlgdxh_1781804643277.json",
    },
]


def assign_expertise_tier(title: str, years: float | None) -> str:
    """Preset binary main tiers + intermediate sensitivity tier."""
    title = (title or "").strip()
    if title in {"住院医师", "医师", "规培医师"}:
        return "junior"
    if title in {"主任医师", "副主任医师"}:
        return "senior"
    if title in {"主治医师"}:
        if years is not None and years >= 10:
            return "senior"
        if years is not None and years < 7:
            return "junior"
        return "intermediate"
    if years is not None:
        if years < 7:
            return "junior"
        if years >= 10:
            return "senior"
        return "intermediate"
    return "pending"


def load_manifest_readers(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    by_reader: dict[str, dict] = {}
    for r in rows:
        rid = r["reader_id"]
        slot = by_reader.setdefault(
            rid,
            {
                "reader_id": rid,
                "planned_cases": 0,
                "pairable_cases": 0,
                "case_ids": [],
            },
        )
        slot["planned_cases"] += 1
        if r.get("baseline_pairable") == "True":
            slot["pairable_cases"] += 1
        slot["case_ids"].append(r["case_id"])
    # preserve first-seen case order from manifest for deterministic shuffle input
    return [by_reader[k] for k in sorted(by_reader)]


def write_expertise(readers: list[dict], out: Path) -> None:
    fields = [
        "reader_id",
        "study_role",
        "auth_binding_status",
        "title",
        "hospital_level",
        "center",
        "province",
        "gi_us_years",
        "annual_case_volume",
        "expertise_tier_primary",
        "expertise_tier_notes",
        "round1_pairable_cases",
        "round1_planned_cases",
        "include_in_primary_complete150",
        "registration_status",
        "registered_at",
        "source",
    ]
    rows = []
    for r in readers:
        complete = r["pairable_cases"] == 150
        rows.append(
            {
                "reader_id": r["reader_id"],
                "study_role": "round2_ai_assisted",
                "auth_binding_status": "required_before_start",
                "title": "",
                "hospital_level": "",
                "center": "",
                "province": "",
                "gi_us_years": "",
                "annual_case_volume": "",
                "expertise_tier_primary": "pending",
                "expertise_tier_notes": "Must register title and gi_us_years before Round2 start; tier preset by assign_expertise_tier()",
                "round1_pairable_cases": r["pairable_cases"],
                "round1_planned_cases": r["planned_cases"],
                "include_in_primary_complete150": str(complete).lower(),
                "registration_status": "pending",
                "registered_at": "",
                "source": "round1_server_doctor_id",
            }
        )
    # Doctor_05 missing Round1
    if "Doctor_05" not in {r["reader_id"] for r in readers}:
        rows.append(
            {
                "reader_id": "Doctor_05",
                "study_role": "round2_ai_assisted",
                "auth_binding_status": "blocked_until_round1_recovered",
                "title": "",
                "hospital_level": "",
                "center": "",
                "province": "",
                "gi_us_years": "",
                "annual_case_volume": "",
                "expertise_tier_primary": "pending",
                "expertise_tier_notes": "No Round1 progress.json; excluded from strict paired primary analysis until recovered",
                "round1_pairable_cases": 0,
                "round1_planned_cases": 0,
                "include_in_primary_complete150": "false",
                "registration_status": "blocked_missing_round1",
                "registered_at": "",
                "source": "round1_missing",
            }
        )
    rows.sort(key=lambda x: x["reader_id"])
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_early_profiles(out: Path) -> None:
    fields = [
        "cohort",
        "raw_id",
        "reader_label",
        "title",
        "hospital_level",
        "province",
        "gi_us_years",
        "expertise_tier_primary",
        "maps_to_round1_doctor_id",
        "source_file",
        "notes",
    ]
    rows = []
    for p in EARLY_SUBSET_PROFILES:
        rows.append(
            {
                **{k: p.get(k, "") for k in fields if k not in {"expertise_tier_primary", "maps_to_round1_doctor_id", "notes"}},
                "expertise_tier_primary": assign_expertise_tier(p["title"], float(p["gi_us_years"])),
                "maps_to_round1_doctor_id": "unknown_do_not_auto_map",
                "notes": "Early AI-favorable 100-case subset only; not interchangeable with Doctor_XX Round1 IDs",
            }
        )
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_case_order(
    readers: list[dict],
    out: Path,
    summary_out: Path,
    seed: int,
    *,
    created_at: str | None = None,
) -> None:
    fields = [
        "reader_id",
        "presentation_index",
        "case_id",
        "seed",
        "freeze_id",
        "created_at",
    ]
    # Keep created_at freeze-stable so re-runs with the same seed preserve SHA-256.
    created = created_at or "2026-08-10T03:43:20Z"
    rows = []
    for r in readers:
        cases = list(dict.fromkeys(r["case_ids"]))  # preserve unique order
        rng = random.Random(f"{seed}:{r['reader_id']}")
        shuffled = cases[:]
        rng.shuffle(shuffled)
        for i, cid in enumerate(shuffled, start=1):
            rows.append(
                {
                    "reader_id": r["reader_id"],
                    "presentation_index": i,
                    "case_id": cid,
                    "seed": seed,
                    "freeze_id": "reader_round2_freeze_20260810",
                    "created_at": created,
                }
            )
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    payload = {
        "seed": seed,
        "freeze_id": "reader_round2_freeze_20260810",
        "created_at": created,
        "reader_count": len(readers),
        "row_count": len(rows),
        "cases_per_reader": Counter(r["reader_id"] for r in rows),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "method": "per_reader_fisher_yates_shuffle",
    }
    # JSON can't serialize Counter values as Counter
    payload["cases_per_reader"] = dict(sorted(payload["cases_per_reader"].items()))
    summary_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing expertise template / case-order freeze artifacts",
    )
    ap.add_argument(
        "--skip-expertise",
        action="store_true",
        help="Do not rewrite reader_expertise_registry_*.csv",
    )
    ap.add_argument(
        "--skip-order",
        action="store_true",
        help="Do not rewrite frozen case-order CSV",
    )
    args = ap.parse_args()
    readers = load_manifest_readers(args.manifest)

    if not args.skip_expertise:
        if EXPERTISE_OUT.exists() and not args.force:
            print(f"SKIP expertise (exists; use --force or import_reader_expertise_registry.py): {EXPERTISE_OUT}")
        else:
            write_expertise(readers, EXPERTISE_OUT)
            print(f"Wrote {EXPERTISE_OUT}")
    write_early_profiles(EARLY_PROFILES)
    print(f"Wrote {EARLY_PROFILES}")

    if not args.skip_order:
        if ORDER_OUT.exists() and not args.force:
            print(f"SKIP case order (frozen artifact exists; refuse rewrite without --force): {ORDER_OUT}")
        else:
            write_case_order(readers, ORDER_OUT, ORDER_SUMMARY, args.seed)
            print(f"Wrote {ORDER_OUT}")
            print(f"Wrote {ORDER_SUMMARY}")


if __name__ == "__main__":
    main()
