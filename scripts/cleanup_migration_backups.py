#!/usr/bin/env python3
"""Remove Phase-3 .bak_YYYYMMDD dirs after symlink + legacy paths verified."""

from __future__ import annotations

import csv
import shutil
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_LOG = PROJECT_ROOT / "data" / "metadata" / "path_migration_log.csv"

BACKUPS = [
    "胃癌分期.bak_20260529",
    "胃癌直接手术外部测试集.bak_20260529",
    "胃腔.bak_20260529",
    "胃壁区域可视化方向.bak_20260529",
]

LEGACY_SYMLINKS = [
    ("胃癌分期", "data/raw/legacy_gastric_staging"),
    ("胃腔", "data/raw/legacy_lumen"),
    ("胃癌直接手术外部测试集", "data/raw/legacy_external_direct_surgery"),
    ("胃壁区域可视化方向", "data/raw/legacy_wall_viz"),
]


def append_log(old_path: str, action: str, notes: str) -> None:
    with MIGRATION_LOG.open("a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([old_path, "", action, date.today().isoformat(), "yes", notes])


def main() -> None:
    for name, legacy_rel in LEGACY_SYMLINKS:
        link = PROJECT_ROOT / name
        legacy = PROJECT_ROOT / legacy_rel
        if not link.exists() or not legacy.is_dir():
            raise SystemExit(f"Abort: missing {name} or {legacy_rel}")

    freed = 0
    for bak_name in BACKUPS:
        bak = PROJECT_ROOT / bak_name
        if not bak.is_dir():
            print(f"skip (gone): {bak_name}")
            continue
        size = sum(f.stat().st_size for f in bak.rglob("*") if f.is_file())
        shutil.rmtree(bak)
        freed += size
        append_log(bak_name, "delete_backup", "phase8 cleanup after verify pass")
        print(f"removed {bak_name} ({size / 1e9:.2f} GB)")

    note = PROJECT_ROOT / "data" / "metadata" / "backup_dirs_20260529.md"
    if note.exists():
        text = note.read_text(encoding="utf-8")
        note.write_text(
            text.replace(
                "可**仅删除**上述 `.bak_*` 目录",
                "上述 `.bak_*` 目录已于 "
                f"{date.today().isoformat()} 删除",
            ),
            encoding="utf-8",
        )
    print(f"Total freed ~{freed / 1e9:.2f} GB. Run: python scripts/verify_repo_paths.py")


if __name__ == "__main__":
    main()
