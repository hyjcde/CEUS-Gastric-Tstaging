#!/usr/bin/env python3
"""Quarantine all loop_still crop MP4s out of active dataset/.

Moves files to dataset/_quarantine/loop_still/<original relative path>,
appends data/metadata/path_migration_log.csv, and clears crop_video_path
in data/registry/image_video_pair_index.csv for those samples.

Does NOT delete images/masks. Does NOT touch video_mode=cached files.
"""

from __future__ import annotations

import argparse
import csv
import shutil
from datetime import datetime, timezone
from pathlib import Path

from patient_media_common import PAIR_INDEX, PROJECT_ROOT, load_video_crop_modes

QUARANTINE_ROOT = PROJECT_ROOT / "dataset" / "_quarantine" / "loop_still"
MIGRATION_LOG = PROJECT_ROOT / "data" / "metadata" / "path_migration_log.csv"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--hard-delete", action="store_true", help="rm instead of quarantine (not recommended)")
    args = ap.parse_args()

    modes = load_video_crop_modes()
    loop_ids = {sid for sid, m in modes.items() if m == "loop_still"}
    print(f"[loop] samples with mode=loop_still: {len(loop_ids)}")

    pair_rows = list(csv.DictReader(PAIR_INDEX.open(encoding="utf-8-sig")))
    fields = list(pair_rows[0].keys()) if pair_rows else []

    moved = 0
    missing = 0
    cleared = 0
    log_rows: list[dict[str, str]] = []
    ts = utc_now()

    for row in pair_rows:
        sid = row.get("sample_id") or ""
        if sid not in loop_ids:
            continue
        rel = (row.get("crop_video_path") or "").strip()
        if not rel:
            continue
        src = PROJECT_ROOT / rel
        if not src.exists():
            missing += 1
            row["crop_video_path"] = ""
            if row.get("match_status") == "crop_only":
                row["match_status"] = "none"
            cleared += 1
            continue

        if args.hard_delete:
            new_rel = ""
            action = "delete_loop_still"
            if not args.dry_run:
                src.unlink()
            dest_note = "(deleted)"
        else:
            # preserve relative layout under quarantine
            dest = QUARANTINE_ROOT / rel
            new_rel = str(dest.relative_to(PROJECT_ROOT))
            action = "quarantine_move"
            dest_note = new_rel
            if not args.dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    dest.unlink()
                shutil.move(str(src), str(dest))

        log_rows.append(
            {
                "timestamp": ts,
                "action": action,
                "old_path": rel,
                "new_path": dest_note if not args.hard_delete else "",
                "note": f"loop_still sample_id={sid}",
            }
        )
        row["crop_video_path"] = ""
        if row.get("match_status") in {"crop_only", "raw+crop"}:
            # raw may remain; without crop, mark accordingly
            if (row.get("raw_video_path") or "").strip():
                row["match_status"] = "raw_only"
            else:
                row["match_status"] = "none"
        cleared += 1
        moved += 1

    print(f"[loop] files moved/deleted: {moved}  already_missing: {missing}  pair rows cleared: {cleared}")
    if args.dry_run:
        print("[dry-run] no changes written")
        return 0

    # rewrite pair index
    with PAIR_INDEX.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(pair_rows)
    print(f"[ok] updated {PAIR_INDEX.relative_to(PROJECT_ROOT)}")

    # append migration log (canonical header in this repo)
    MIGRATION_LOG.parent.mkdir(parents=True, exist_ok=True)
    header = ["old_path", "new_path", "action", "date", "verified", "notes"]
    write_header = not MIGRATION_LOG.exists() or MIGRATION_LOG.stat().st_size == 0
    with MIGRATION_LOG.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        if write_header:
            w.writeheader()
        for r in log_rows:
            w.writerow(
                {
                    "old_path": r["old_path"],
                    "new_path": r["new_path"],
                    "action": r["action"],
                    "date": r["timestamp"],
                    "verified": "yes",
                    "notes": r["note"],
                }
            )
    print(f"[ok] appended {len(log_rows)} rows -> {MIGRATION_LOG.relative_to(PROJECT_ROOT)}")
    print(f"[ok] quarantine root: {QUARANTINE_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
