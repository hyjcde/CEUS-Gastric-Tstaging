#!/usr/bin/env python3
"""Precompute top-K similar cases for reader_study_v150 cases (offline, no GPU).

Purpose: the /reader workbench shows a low-key "similar cases" block even before
the doctor runs the live agent pipeline. Live retrieval stays the primary path;
this file only backfills cases that can be linked to the US clinical table.

Query side constraints (no leakage, no model run):
  - clinical block only: location code, size (cm), CEA/CA199 status
  - age / sex / differentiation are unavailable in the US table, left at 0
  - classification block stays zero (GT one-hot is memory-side only)
  - boundary / wall / morphology blocks stay zero (need live tool outputs)

Scoring: block weights are renormalized over query-available blocks (clinical),
so similarity stays in [0, 1] and reflects clinical-profile match only.

Self-exclusion: memory rows whose patient_id matches the case hospital id
(digit-normalized) are removed from that case's hits.

Usage:
  python3 scripts/precompute_reader_similar_cases.py
  python3 scripts/precompute_reader_similar_cases.py --top-k 5 --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

from agent.memory.case_similarity import block_cosine  # noqa: E402
from agent.memory.multimodal_case_vector import BLOCK_SLICES  # noqa: E402

BUNDLE_PATH = ROOT / "docs/clinical_validation/reader_study_v150/cases.bundle.js"
US_CLINICAL_PATH = (
    ROOT / "docs/clinical_validation/reader_study_v150/demo_assets/assist_us_clinical.js"
)
COVERAGE_CSV_PATH = (
    ROOT / "artifacts/eval/reader_study_v150_human_ai_comparison/static_image_coverage.csv"
)
MEMORY_DIR = ROOT / "pipeline/agent/memory/index/phase0_train_only_v1"
DEFAULT_OUT = ROOT / "apps/gastric_scan_next/data/reader_similar_cases.json"

HOSPITAL_RE = re.compile(r"(Z?\d{5,})", re.IGNORECASE)


def _load_js_assignment(path: Path, var_name: str) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    match = re.search(rf"{re.escape(var_name)}\s*=\s*", raw)
    if not match:
        raise SystemExit(f"{var_name} not found in {path}")
    return json.loads(raw[match.end():].rstrip().rstrip(";"))


def _hospital_candidates(token: str) -> List[str]:
    out: List[str] = []
    for match in HOSPITAL_RE.finditer(str(token or "")):
        raw = match.group(1).upper()
        digits = re.sub(r"^0+", "", raw.lstrip("Z")) or "0"
        out.extend([raw, digits, f"Z{digits}", digits.zfill(7), f"Z{digits.zfill(7)}"])
    seen = set()
    unique = []
    for item in out:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _norm_hospital_digits(token: str) -> Optional[str]:
    cands = _hospital_candidates(token)
    if not cands:
        return None
    return re.sub(r"^0+", "", cands[0].lstrip("Z")) or "0"


def _load_coverage_map(path: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    if not path.exists():
        return mapping
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            case_id = (row.get("case_id") or "").strip()
            blob = "|".join(
                [
                    row.get("media_tokens") or "",
                    row.get("example_image_source") or "",
                    row.get("example_crop_video") or "",
                ]
            )
            match = HOSPITAL_RE.search(blob)
            if case_id and match:
                mapping[case_id] = match.group(1)
    return mapping


def _marker_positive(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        return bool(re.search(r"阳|\+|positive|1", value, re.I))
    return False


def _lookup_us_row(case: Dict[str, Any], pack: Dict[str, Any], coverage: Dict[str, str]):
    """Mirror of apps/gastric_scan_next/lib/reader/us-clinical-server.ts lookup."""
    keys = [
        str(case.get(k) or "").strip() for k in ("case_id", "display_id", "patient_id")
    ]
    keys = [k for k in keys if k]

    by_case = pack.get("by_case") or {}
    for key in keys:
        if key in by_case:
            return by_case[key], keys

    coverage_hid = next((coverage[k] for k in keys if k in coverage), None)
    blob = "|".join(
        keys
        + [coverage_hid or ""]
        + [str(f.get("media_token", "")) for f in case.get("frames", [])]
    )
    by_hospital = pack.get("by_hospital") or {}
    for cand in _hospital_candidates(blob):
        if cand in by_hospital:
            return by_hospital[cand], keys
    return None, keys


def _clinical_query_vector(row: Dict[str, Any]) -> np.ndarray:
    """Fill only the clinical block (dims 9:17) of the 28-dim vector."""
    vec = np.zeros(28, dtype=np.float32)
    location_code = row.get("location_code")
    try:
        vec[11] = float(location_code) / 3.0 if location_code is not None else 0.0
    except (TypeError, ValueError):
        vec[11] = 0.0
    size_mm = row.get("tumor_size_mm")
    thick_mm = row.get("tumor_thickness_mm")
    # Memory side used _norm with LENGTH_MEAN/STD, THICKNESS_MEAN/STD (z-score in cm).
    from agent.memory.feature_extractor import (
        LENGTH_MEAN,
        LENGTH_STD,
        THICKNESS_MEAN,
        THICKNESS_STD,
        _norm,
    )

    if size_mm:
        vec[12] = _norm(float(size_mm) / 10.0, LENGTH_MEAN, LENGTH_STD)
    if thick_mm:
        vec[13] = _norm(float(thick_mm) / 10.0, THICKNESS_MEAN, THICKNESS_STD)
    vec[14] = 1.0 if _marker_positive(row.get("cea_positive")) else 0.0
    vec[15] = 1.0 if _marker_positive(row.get("ca199_positive")) else 0.0
    return vec


def _clinical_cosine(query: np.ndarray, memory_row: np.ndarray) -> float:
    start, end = BLOCK_SLICES["clinical"]
    return block_cosine(query, memory_row, start, end)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    bundle = _load_js_assignment(BUNDLE_PATH, "window.READER_CASES")
    pack = _load_js_assignment(US_CLINICAL_PATH, "window.ASSIST_US_CLINICAL")
    coverage = _load_coverage_map(COVERAGE_CSV_PATH)

    matrix = np.load(MEMORY_DIR / "case_matrix_extended.npy").astype(np.float32)
    metadata: List[Dict[str, Any]] = json.loads(
        (MEMORY_DIR / "case_metadata_extended.json").read_text(encoding="utf-8")
    )
    memory_pids = [
        re.sub(r"^0+", "", str(m.get("patient_id", "")).lstrip("Zz")) or "0"
        for m in metadata
    ]

    out_cases: Dict[str, Any] = {}
    n_available = 0
    for case in bundle.get("cases", []):
        case_id = str(case.get("case_id") or "")
        if not case_id:
            continue
        row, _keys = _lookup_us_row(case, pack, coverage)
        if not row:
            out_cases[case_id] = {
                "available": False,
                "reason": "no_clinical_link",
            }
            continue

        query = _clinical_query_vector(row)
        q_start, q_end = BLOCK_SLICES["clinical"]
        if float(np.linalg.norm(query[q_start:q_end])) < 1e-8:
            out_cases[case_id] = {
                "available": False,
                "reason": "insufficient_clinical_fields",
            }
            continue
        self_digits = _norm_hospital_digits(
            "|".join(
                [str(row.get("hospital_id") or "")]
                + [str(f.get("media_token", "")) for f in case.get("frames", [])]
            )
        )

        scored = []
        for idx in range(matrix.shape[0]):
            if self_digits and memory_pids[idx] == self_digits:
                continue
            sim = _clinical_cosine(query, matrix[idx])
            scored.append((idx, sim))
        scored.sort(key=lambda x: -x[1])

        hits = []
        for idx, sim in scored[: args.top_k]:
            meta = metadata[idx]
            hits.append(
                {
                    "rank": len(hits) + 1,
                    "patient_id": str(meta.get("patient_id", "")),
                    "T_stage": meta.get("T_stage", "unknown"),
                    "data_source": meta.get("data_source", "unknown"),
                    "similarity": round(float(sim), 4),
                }
            )

        stage_dist: Dict[str, int] = {}
        for hit in hits:
            stage_dist[hit["T_stage"]] = stage_dist.get(hit["T_stage"], 0) + 1

        out_cases[case_id] = {
            "available": True,
            "basis": ["clinical"],
            "clinical_summary": {
                "location": row.get("tumor_location"),
                "size_mm": row.get("tumor_size_mm"),
                "thickness_mm": row.get("tumor_thickness_mm"),
                "cea_positive": _marker_positive(row.get("cea_positive")),
                "ca199_positive": _marker_positive(row.get("ca199_positive")),
            },
            "similar_cases": hits,
            "stage_distribution": stage_dist,
        }
        n_available += 1

    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "scripts/precompute_reader_similar_cases.py",
        "memory_version": "phase0_train_only_v1",
        "query_mode": "clinical_block_only",
        "note": "Clinical-profile similarity only; live agent retrieval remains primary.",
        "top_k": args.top_k,
        "n_cases": len(out_cases),
        "n_available": n_available,
        "cases": out_cases,
    }

    print(json.dumps({k: payload[k] for k in ("n_cases", "n_available")}, indent=2))
    if args.dry_run:
        sample = next((c for c in out_cases.values() if c.get("available")), None)
        print(json.dumps(sample, ensure_ascii=False, indent=2))
        return

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
