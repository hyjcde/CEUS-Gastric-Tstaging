#!/usr/bin/env python3
"""Phase 3: rsync Chinese legacy dirs to data/raw/legacy_* and symlink at repo root."""

from __future__ import annotations

import csv
import shutil
import subprocess
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_LOG = PROJECT_ROOT / "data" / "metadata" / "path_migration_log.csv"

LEGACY_MAP: list[tuple[str, str]] = [
    ("胃癌分期", "data/raw/legacy_gastric_staging"),
    ("胃癌直接手术外部测试集", "data/raw/legacy_external_direct_surgery"),
    ("胃腔", "data/raw/legacy_lumen"),
    ("胃壁区域可视化方向", "data/raw/legacy_wall_viz"),
]


def append_log(old_path: str, new_path: str, action: str, notes: str = "") -> None:
    with MIGRATION_LOG.open("a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([old_path, new_path, action, date.today().isoformat(), "yes", notes])


def rsync_dir(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and any(dest.iterdir()):
        print(f"skip rsync (dest non-empty): {dest}")
        return
    subprocess.run(
        ["rsync", "-a", f"{src}/", f"{dest}/"],
        check=True,
    )


def migrate_one(old_name: str, new_rel: str) -> None:
    src = PROJECT_ROOT / old_name
    if not src.exists():
        print(f"skip missing: {old_name}")
        return
    if src.is_symlink():
        print(f"skip already symlink: {old_name} -> {src.resolve()}")
        return

    dest = PROJECT_ROOT / new_rel
    print(f"rsync {old_name} -> {new_rel}")
    rsync_dir(src, dest)

    bak = PROJECT_ROOT / f"{old_name}.bak_{date.today().strftime('%Y%m%d')}"
    if bak.exists():
        print(f"backup already exists: {bak}")
    else:
        shutil.move(str(src), str(bak))
        append_log(old_name, str(bak), "mv_backup", "phase3")

    link = PROJECT_ROOT / old_name
    if link.exists() or link.is_symlink():
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            raise RuntimeError(f"Expected backup move to leave no dir: {link}")

    # Relative symlink for portability
    rel_target = Path(new_rel)
    link.symlink_to(rel_target)
    append_log(old_name, new_rel, "symlink", "phase3")
    print(f"symlink {old_name} -> {rel_target}")


def main() -> None:
    for old_name, new_rel in LEGACY_MAP:
        migrate_one(old_name, new_rel)
    print("Phase 3 done. Run: python scripts/verify_repo_paths.py")


if __name__ == "__main__":
    main()
