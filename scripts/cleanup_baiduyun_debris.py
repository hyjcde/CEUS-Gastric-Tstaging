#!/usr/bin/env python3
"""Remove Baidu Netdisk sync debris (*.baiduyun.uploading.cfg) under dataset/."""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS = [
    ROOT / "dataset" / "internal",
    ROOT / "dataset" / "external",
]


def find_debris(roots: list[Path]) -> list[Path]:
    hits: list[Path] = []
    for base in roots:
        if not base.exists():
            continue
        hits.extend(base.rglob("*.baiduyun.uploading.cfg"))
        hits.extend(base.rglob(".baiduyun.*"))
    return sorted(set(hits))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--root", type=Path, action="append", default=[])
    args = parser.parse_args()
    roots = [Path(r) for r in args.root] if args.root else DEFAULT_ROOTS
    files = find_debris(roots)
    if not files:
        print("No baiduyun debris found.")
        return
    print(f"Found {len(files)} file(s)")
    for path in files:
        if args.dry_run:
            print(f"  [dry-run] {path}")
        else:
            path.unlink(missing_ok=True)
            print(f"  deleted {path}")
    if not args.dry_run:
        remaining = find_debris(roots)
        print(f"Remaining: {len(remaining)}")


if __name__ == "__main__":
    main()
