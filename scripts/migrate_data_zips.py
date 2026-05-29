#!/usr/bin/env python3
"""Move stray zip files from data/ to artifacts/raw_imports/incoming/ with compat symlinks."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG = PROJECT_ROOT / "data/metadata/path_migration_log.csv"
INCOMING = PROJECT_ROOT / "artifacts/raw_imports/incoming"

ZIPS = [
    "外省整理.zip",
    "德化直接手术.zip",
]


def append_log(old: str, new: str, action: str, notes: str) -> None:
    exists = LOG.exists()
    with LOG.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["old_path", "new_path", "action", "date", "verified", "notes"])
        w.writerow([old, new, action, date.today().isoformat(), "yes", notes])


def migrate_one(name: str) -> None:
    src = PROJECT_ROOT / "data" / name
    if not src.exists():
        print(f"skip missing {src}")
        return
    INCOMING.mkdir(parents=True, exist_ok=True)
    dst = INCOMING / name
    if dst.exists():
        print(f"already at {dst}")
    else:
        src.rename(dst)
        print(f"mv {src} -> {dst}")
    link = PROJECT_ROOT / "data" / name
    if not link.exists():
        rel = Path("..") / "artifacts" / "raw_imports" / "incoming" / name
        link.symlink_to(rel)
        print(f"symlink {link} -> {rel}")
    append_log(f"data/{name}", f"artifacts/raw_imports/incoming/{name}", "mv+symlink", "phase B data zip")


def main() -> None:
    for z in ZIPS:
        migrate_one(z)
    print("done")


if __name__ == "__main__":
    main()
