#!/usr/bin/env python3
"""Generate data/metadata/asset_manifest.csv for top-level repo assets."""

from __future__ import annotations

import csv
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "data" / "metadata" / "asset_manifest.csv"

# Heuristic classification for root-level entries
TYPE_HINTS: dict[str, str] = {
    "_compat": "directory",
    "artifacts": "generated",
    "models": "directory",
    "apps": "code",
    "archive": "archive",
    "configs": "config",
    "data": "data_layer",
    "dataset": "dataset",
    "docs": "doc",
    "experiments": "experiment_artifacts",
    "pipeline": "code",
    "scripts": "code",
    "external": "third_party",
    "tmp": "temp",
    "output": "generated",
    "results": "generated",
    "paper": "doc",
    "frames_1fps": "cache",
    "direction_annotations": "annotation_output",
}

STATUS_HINTS: dict[str, str] = {
    "docs copy": "legacy",
    "胃癌分期": "legacy_raw",
    "胃癌直接手术外部测试集": "legacy_raw",
    "胃腔": "legacy_raw",
    "胃壁区域可视化方向": "legacy_raw",
    "archive": "archive",
    "tmp": "generated",
    "output": "generated",
}

GIT_POLICY_HINTS: dict[str, str] = {
    "dataset": "selective_track",
    "experiments": "ignore_large",
    "pipeline": "track_code_ignore_artifacts",
    "tmp": "ignore",
    "external": "ignore",
    "frames_1fps": "ignore",
    "artifacts": "ignore",
    "_compat": "ignore",
    "archive": "ignore",
    "models": "track",
}

# Plan-aligned lifecycle bucket (maps from type + status)
LIFECYCLE_MAP: dict[tuple[str, str], str] = {
    ("dataset", "current"): "current",
    ("code", "current"): "current",
    ("doc", "current"): "current",
    ("config", "current"): "current",
    ("data_layer", "current"): "current",
    ("experiment_artifacts", "current"): "generated",
    ("raw_archive", "legacy_import"): "source-data",
    ("model_weight", "current"): "generated",
    ("legacy_raw", "legacy"): "source-data",
    ("legacy", "legacy"): "archive",
    ("archive", "archive"): "archive",
    ("third_party", "current"): "third-party",
    ("generated", "generated"): "generated",
    ("temp", "generated"): "generated",
    ("cache", "generated"): "generated",
    ("annotation_output", "generated"): "generated",
    ("directory", "current"): "current",
    ("file", "current"): "current",
}


def dir_size_bytes(path: Path) -> int:
    try:
        out = subprocess.check_output(
            ["du", "-sb", str(path)],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return int(out.split()[0])
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        total = 0
        if path.is_file():
            return path.stat().st_size
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
        return total


def classify(name: str, is_dir: bool) -> tuple[str, str, str]:
    if name.endswith(".zip"):
        return "raw_archive", "legacy_import", "ignore"
    if name.endswith(".pt"):
        return "model_weight", "current", "ignore"
    if name.endswith(".csv") or name.endswith(".json"):
        return "metadata", "current", "track_or_ignore"
    if is_dir:
        asset_type = TYPE_HINTS.get(name, "directory")
        status = STATUS_HINTS.get(name, "current")
        git_policy = GIT_POLICY_HINTS.get(name, "review")
        return asset_type, status, git_policy
    return "file", "current", "review"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    scanned_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: list[dict[str, str]] = []

    for entry in sorted(PROJECT_ROOT.iterdir(), key=lambda p: p.name):
        if entry.name == ".git":
            continue
        is_dir = entry.is_dir()
        size = dir_size_bytes(entry)
        asset_type, status, git_policy = classify(entry.name, is_dir)
        notes = ""
        if entry.is_symlink():
            notes = f"symlink -> {entry.resolve()}"
        lifecycle = LIFECYCLE_MAP.get((asset_type, status), LIFECYCLE_MAP.get((asset_type, "current"), "review"))
        rows.append(
            {
                "path": entry.name,
                "is_dir": str(is_dir),
                "size_bytes": str(size),
                "type": asset_type,
                "status": status,
                "lifecycle": lifecycle,
                "git_policy": git_policy,
                "scanned_at": scanned_at,
                "notes": notes,
            }
        )

    fieldnames = [
        "path",
        "is_dir",
        "size_bytes",
        "type",
        "status",
        "lifecycle",
        "git_policy",
        "scanned_at",
        "notes",
    ]
    with OUTPUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
