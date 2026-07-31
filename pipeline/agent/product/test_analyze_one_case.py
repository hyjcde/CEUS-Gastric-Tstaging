#!/usr/bin/env python3
"""Run analyze_case.py end-to-end on one prospective frame (no LLM required)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = PROJECT_ROOT / "pipeline"
ANALYZE = PIPELINE_ROOT / "agent" / "product" / "analyze_case.py"


def _resolve_test_image() -> Path:
    import pandas as pd

    for csv_rel in (
        "pipeline/data/tstaging_4class/test_prospective.csv",
        "pipeline/data/tstaging_4class/train.csv",
    ):
        csv_path = PROJECT_ROOT / csv_rel
        if not csv_path.exists():
            continue
        for _, row in pd.read_csv(csv_path).iterrows():
            candidate = (PROJECT_ROOT / row["image_path"]).resolve()
            if candidate.exists():
                return candidate

    fallback = (
        PROJECT_ROOT
        / "dataset/lumen_detection/crop_ui_confirmed/images/train/train_000222.jpg"
    )
    if fallback.exists():
        return fallback.resolve()
    raise FileNotFoundError("No ultrasound image found for smoke test")


def main() -> int:
    image_path = _resolve_test_image()

    payload = {
        "patient_id": "smoke_test_patient",
        "image_path": str(image_path),
        "roi_path": None,
        "frame_count": 1,
        "data_source": "smoke_test",
        "session_id": "smoke_test_session",
    }

    print(f"Running analyze_case on {image_path.name} ...", flush=True)
    proc = subprocess.run(
        [sys.executable, str(ANALYZE)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
        env={**dict(**{"PYTHONPATH": str(PIPELINE_ROOT)}), **dict(__import__("os").environ)},
    )

    if proc.returncode != 0:
        print("STDERR:", proc.stderr, file=sys.stderr)
        print("STDOUT:", proc.stdout, file=sys.stderr)
        return proc.returncode

    result = json.loads(proc.stdout)
    te = result.get("tool_evidence", {})
    rv = result.get("runtime_verification", {})

    lumen = te.get("lumen_detection", {})
    seg = te.get("segmentation", {})
    cls = te.get("classification", {})
    report = result.get("report", {})
    checks = {
        "lumen_detection": lumen.get("lumen_detected") or lumen.get("available"),
        "wall_evidence": te.get("wall_evidence", {}).get("available"),
        "segmentation": seg.get("available") or seg.get("mask_available"),
        "classification": cls.get("available"),
        "clinical22_source": cls.get("clinical_vector_source"),
        "report_t_stage": report.get("recommended_t_stage"),
        "conflicting_evidence": report.get("conflicting_evidence", []),
        "rag_gate": report.get("rag_gate", {}),
        "agent_steps": len(result.get("agent_steps", [])),
        "wall_panel_source": result.get("prediction_artifacts", {}).get(
            "real_wall_analysis_panel_source"
        ),
    }
    print(json.dumps(checks, ensure_ascii=False, indent=2))

    inv_names = [i.get("component") for i in rv.get("invocations", [])]
    print("invocations:", inv_names)

    failed = []
    if not checks["lumen_detection"]:
        failed.append("lumen_detection")
    if not checks["segmentation"]:
        failed.append("segmentation")
    if not checks["classification"]:
        failed.append("classification")
    if checks["wall_evidence"] is False and checks.get("wall_panel_source") not in {
        "live_lumen_signed_distance",
        "live_current_image_composite",
        "live_current_image_heatmap_only",
    }:
        failed.append("wall_evidence_or_proxy")
    if checks["agent_steps"] < 10:
        failed.append(f"agent_steps={checks['agent_steps']}")

    if failed:
        print("FAILED checks:", failed, file=sys.stderr)
        return 2

    print("OK: full agent pipeline completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
