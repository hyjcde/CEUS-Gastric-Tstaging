#!/usr/bin/env python3
"""Shallow index of pipeline/experiments/tree/ (no file moves)."""

from __future__ import annotations

import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TREE = PROJECT_ROOT / "pipeline/experiments/tree"
OUT = PROJECT_ROOT / "pipeline/experiments/tree_index.csv"
MAX_DEPTH = 4


def task_from_path(rel: str) -> str:
    parts = rel.split("/")
    if "detection" in parts:
        return "detection"
    if "segmentation" in parts or "sms" in rel.lower():
        return "segmentation"
    if "classification" in parts or "tstage" in rel.lower():
        return "tstage"
    return "other"


def main() -> None:
    rows: list[dict[str, str]] = []
    if not TREE.exists():
        print(f"tree missing: {TREE}")
        return
    for p in sorted(TREE.rglob("*")):
        if not p.is_dir():
            continue
        rel = str(p.relative_to(PROJECT_ROOT))
        depth = len(Path(rel).parts)
        if depth > MAX_DEPTH + 3:
            continue
        try:
            size_mb = sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / (1024 * 1024)
        except OSError:
            size_mb = 0
        rows.append(
            {
                "path": rel,
                "size_mb": f"{size_mb:.1f}",
                "task": task_from_path(rel),
            }
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["path", "size_mb", "task"])
        w.writeheader()
        w.writerows(rows[:5000])
    print(f"Wrote {min(len(rows), 5000)} rows -> {OUT}")


if __name__ == "__main__":
    main()
