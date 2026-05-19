#!/usr/bin/env python3
"""Run analyze_case on N patients with images available on disk."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = PROJECT_ROOT / "pipeline"
ANALYZE = PIPELINE_ROOT / "agent" / "product" / "analyze_case.py"
OUT_DIR = PIPELINE_ROOT / "experiments" / "agent_smoke_test"


def _pick_cases(n: int, csv_name: str) -> list[dict]:
    from agent.core.case_card import load_case_cards_from_csv

    csv_path = PIPELINE_ROOT / "data" / "tstaging_4class" / csv_name
    cards = load_case_cards_from_csv(csv_path, require_existing_images=True)
    if not cards:
        fallback_img = (
            PROJECT_ROOT
            / "dataset/lumen_detection/crop_ui_confirmed/images/train/train_000222.jpg"
        )
        if fallback_img.exists():
            return [{
                "patient_id": "smoke_fallback",
                "image_path": str(fallback_img),
                "roi_path": None,
                "frame_count": 1,
                "data_source": "smoke_test",
                "session_id": "agent_batch_smoke",
            }]
        raise RuntimeError("No CaseCards with existing images and no lumen fallback image.")

    payloads = []
    for card in cards[:n]:
        frames = [
            {
                "image_path": frame.image_path,
                "roi_path": frame.roi_path,
                "annotation_path": frame.annotation_path,
            }
            for frame in card.frames[:3]
            if frame.image_path and Path(frame.image_path).exists()
        ]
        primary = frames[0] if frames else None
        if not primary:
            continue
        payloads.append({
            "patient_id": card.patient_id,
            "image_path": primary["image_path"],
            "roi_path": primary.get("roi_path"),
            "frames": frames,
            "frame_count": len(frames),
            "max_frames": 3,
            "data_source": card.data_source,
            "session_id": "agent_batch_smoke",
        })
    return payloads


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch analyze_case runner")
    parser.add_argument("-n", type=int, default=3)
    parser.add_argument("--csv", default="test_prospective.csv")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    cases = _pick_cases(args.n, args.csv)
    args.out.mkdir(parents=True, exist_ok=True)
    summary_rows = []
    ok = 0

    for payload in cases:
        proc = subprocess.run(
            [sys.executable, str(ANALYZE)],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            env={**{"PYTHONPATH": str(PIPELINE_ROOT)}, **dict(__import__("os").environ)},
        )
        if proc.returncode != 0:
            summary_rows.append({
                "patient_id": payload["patient_id"],
                "status": "error",
                "stderr": proc.stderr[:800],
            })
            print(f"FAIL {payload['patient_id']}: {proc.stderr[:500]}", file=sys.stderr)
            continue

        result = json.loads(proc.stdout)
        te = result.get("tool_evidence", {})
        report = result.get("report", {})
        row = {
            "patient_id": payload["patient_id"],
            "status": "ok",
            "lumen": te.get("lumen_detection", {}).get("lumen_detected"),
            "wall": te.get("wall_evidence", {}).get("available"),
            "seg": te.get("segmentation", {}).get("available"),
            "cls": te.get("classification", {}).get("available"),
            "T": report.get("recommended_t_stage"),
            "clinical22": te.get("classification", {}).get("clinical_vector_source"),
            "aggregation": result.get("frame_evidence", {}).get("aggregation"),
            "frame_count": result.get("frame_evidence", {}).get("frame_count"),
            "rag_weight": (report.get("rag_gate") or {}).get("rag_weight"),
            "conflicts": len(report.get("conflicting_evidence") or []),
        }
        summary_rows.append(row)
        print(f"OK {payload['patient_id']}: {row}")
        if row["cls"] and row["seg"]:
            ok += 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.out / f"batch_summary_{stamp}.json"
    out_path.write_text(
        json.dumps({"completed": ok, "total": len(cases), "rows": summary_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Completed {ok}/{len(cases)} with seg+cls available.")
    print(f"Summary: {out_path}")
    return 0 if ok == len(cases) else 2


if __name__ == "__main__":
    sys.path.insert(0, str(PIPELINE_ROOT))
    raise SystemExit(main())
