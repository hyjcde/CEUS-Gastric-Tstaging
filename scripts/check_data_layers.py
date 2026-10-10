#!/usr/bin/env python3
"""Check that dataset/ stays a T-staging train, val, and test tree."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset"

ALLOWED_DIRS = {"train", "val", "test", "task_datasets", "tables", "internal", "external", "videos"}
ALLOWED_FILES = {"README.md", "DATASET_GUIDE.md", "patient_clinical_master.csv"}
ALLOWED_SYMLINKS = {
    "inflammation",
    "gastritis_external",
    "patients",
    "clinical_tables",
    "training_views",
}


def main() -> int:
    errors: list[str] = []
    if not DATASET.is_dir():
        print("dataset/ is missing", file=sys.stderr)
        return 1
    for entry in sorted(DATASET.iterdir()):
        name = entry.name
        if entry.is_symlink():
            if name not in ALLOWED_SYMLINKS:
                errors.append(f"unexpected symlink {name}")
            elif not entry.exists():
                errors.append(f"dangling symlink {name}")
            continue
        if entry.is_dir():
            if name not in ALLOWED_DIRS:
                errors.append(f"unexpected directory {name}")
            continue
        if entry.is_file():
            if name not in ALLOWED_FILES:
                errors.append(f"unexpected file {name}")
            continue
        errors.append(f"unexpected entry {name}")

    test = DATASET / "test"
    if test.is_dir():
        children = sorted(path.name for path in test.iterdir())
        if children != ["external", "prospective"]:
            errors.append(f"test/ must contain only prospective and external, found {children}")
    else:
        errors.append("test/ is missing")

    for name in ("train", "val"):
        if not (DATASET / name).is_dir():
            errors.append(f"{name}/ is missing")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("dataset layers ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
