#!/usr/bin/env python3
"""Regenerate similar_cases_contact_sheet.png for agent artifact dirs (white bg + ext previews)."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline"))

from agent.product.analyze_case import _render_similar_cases_contact_sheet  # noqa: E402

AGENT_ROOTS = [
    PROJECT_ROOT / "tmp" / "agent_predictions" / "agent_batch_smoke",
]
TRAJECTORY_ROOT = PROJECT_ROOT / "tmp" / "agent_trajectories" / "agent_batch_smoke"
RESULTS_OUT = PROJECT_ROOT / "docs" / "mainline" / "figures" / "results"


def _load_similar_cases(agent_dir: Path) -> list[dict] | None:
    patient = agent_dir.name.split("_")[0]
    if TRAJECTORY_ROOT.is_dir():
        hits = sorted(TRAJECTORY_ROOT.glob(f"{patient}_*.json"), reverse=True)
        for path in hits:
            data = json.loads(path.read_text(encoding="utf-8"))
            cases = data.get("result", {}).get("similar_cases")
            if cases:
                return cases
    return None


def regenerate_dir(agent_dir: Path, sync_results: bool) -> bool:
    similar_cases = _load_similar_cases(agent_dir)
    if not similar_cases:
        print(f"skip (no similar_cases): {agent_dir.name}")
        return False

    patient = agent_dir.name.split("_")[0]
    artifact_info = {
        "dir": agent_dir,
        "relative_dir": Path(agent_dir.parent.name) / agent_dir.name,
    }
    out = _render_similar_cases_contact_sheet(
        artifact_dir=agent_dir,
        relative_dir=artifact_info["relative_dir"],
        similar_cases=similar_cases,
    )
    if out.get("similar_cases_contact_sheet_error"):
        print(f"error {agent_dir.name}: {out['similar_cases_contact_sheet_error']}")
        return False

    if sync_results:
        dest = RESULTS_OUT / f"case_agent_{patient}_similar_cases_contact_sheet.png"
        shutil.copy2(agent_dir / "similar_cases_contact_sheet.png", dest)
        print(f"synced -> {dest.name}")
    else:
        print(f"ok {agent_dir.name}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sync-results", action="store_true", help="Copy into docs/mainline/figures/results/")
    parser.add_argument("--patient", action="append", help="Only these patient IDs (e.g. 1166650)")
    args = parser.parse_args()

    ok = 0
    for root in AGENT_ROOTS:
        if not root.is_dir():
            continue
        dirs = sorted(root.iterdir())
        if args.patient:
            wanted = set(args.patient)
            dirs = [d for d in dirs if d.is_dir() and d.name.split("_")[0] in wanted]
        # newest run per patient
        seen: set[str] = set()
        for agent_dir in sorted(dirs, key=lambda p: p.name, reverse=True):
            if not agent_dir.is_dir():
                continue
            patient = agent_dir.name.split("_")[0]
            if patient in seen:
                continue
            seen.add(patient)
            if regenerate_dir(agent_dir, args.sync_results):
                ok += 1
    print(f"regenerated {ok} contact sheet(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
