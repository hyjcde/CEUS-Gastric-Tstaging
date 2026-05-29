#!/usr/bin/env python3
"""Phase 2: move small root assets to canonical dirs and leave root symlinks."""

from __future__ import annotations

import csv
import shutil
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_LOG = PROJECT_ROOT / "data" / "metadata" / "path_migration_log.csv"

MOVES: list[tuple[str, str]] = [
    ("direction_annotation_batch.json", "data/annotation/batches/direction_annotation_batch.json"),
    ("direction_annotations", "data/annotation/outputs/direction_annotations"),
    ("gradcam_rejected (2).csv", "artifacts/reports/gradcam_rejected.csv"),
]

WEIGHT_GLOB = "yolo11*.pt"
WEIGHT_DEST_DIR = "artifacts/model_weights/yolo"


def append_log(old_path: str, new_path: str, action: str, notes: str = "") -> None:
    MIGRATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with MIGRATION_LOG.open("a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([old_path, new_path, action, date.today().isoformat(), "yes", notes])


def ensure_symlink(link: Path, target: Path) -> None:
    target = target.resolve()
    if link.is_symlink():
        if link.resolve() == target:
            return
        link.unlink()
    elif link.exists():
        raise RuntimeError(f"Refusing to replace non-symlink: {link}")
    link.symlink_to(target)


def move_file_or_dir(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    if not src.exists():
        return
    if src.is_dir():
        shutil.move(str(src), str(dest))
    else:
        shutil.move(str(src), str(dest))


def main() -> None:
    for old_rel, new_rel in MOVES:
        src = PROJECT_ROOT / old_rel
        dest = PROJECT_ROOT / new_rel
        if src.exists() and not dest.exists():
            move_file_or_dir(src, dest)
            append_log(old_rel, new_rel, "mv+symlink", "phase2")
        if dest.exists():
            ensure_symlink(src, dest)

    weight_dir = PROJECT_ROOT / WEIGHT_DEST_DIR
    weight_dir.mkdir(parents=True, exist_ok=True)
    for weight in sorted(PROJECT_ROOT.glob(WEIGHT_GLOB)):
        dest = weight_dir / weight.name
        if weight.is_symlink():
            continue
        if not dest.exists() and weight.is_file():
            shutil.move(str(weight), str(dest))
            append_log(weight.name, str(dest.relative_to(PROJECT_ROOT)), "mv+symlink", "phase2")
        link = PROJECT_ROOT / weight.name
        if dest.exists():
            ensure_symlink(link, dest)

    incoming = PROJECT_ROOT / "artifacts" / "raw_imports" / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    for z in PROJECT_ROOT.glob("*.zip"):
        if z.name.startswith("."):
            continue
        dest = incoming / z.name
        if dest.exists():
            ensure_symlink(z, dest)
            continue
        if z.is_symlink():
            continue
        # Large zips: symlink only if already under artifacts, else move
        try:
            shutil.move(str(z), str(dest))
            append_log(z.name, str(dest.relative_to(PROJECT_ROOT)), "mv+symlink", "phase2 zip")
            ensure_symlink(z, dest)
        except OSError as exc:
            print(f"skip zip {z.name}: {exc}")

    print("Phase 2 migration done. Run: python scripts/verify_repo_paths.py")


if __name__ == "__main__":
    main()
