#!/usr/bin/env python3
"""Merge public doctor_case_state into the workstation copy without dropping rows.

Public Next and the workstation each keep their own file. This adds public-only
rows and unions keyframes / activity on overlaps. Conflicting finals are kept
on the public side and written to a sidecar. Never replace the whole local file
with a shorter public or local snapshot.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path("/data/research/gastric/GastricTstaging")
DEFAULT_LOCAL = ROOT / "runtime" / "gastric_scan_next" / "doctor_case_state.json"

SCALAR_CONFLICT_FIELDS = (
    "initial_nature",
    "initial_stage",
    "final_nature",
    "final_stage",
)


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("account_id") or "").strip(), str(row.get("case_id") or "").strip())


def load_store(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("entries") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError(f"{path} has no entries[]")
    return [row for row in rows if isinstance(row, dict) and row_key(row)[0] and row_key(row)[1]]


def activity_key(item: dict[str, Any]) -> str:
    return str(item.get("id") or "").strip() or json.dumps(item, sort_keys=True, ensure_ascii=False)


def keyframe_key(item: dict[str, Any]) -> tuple[str, str]:
    kid = str(item.get("id") or "").strip()
    if kid:
        return ("id", kid)
    return ("t", str(item.get("timeSec") if item.get("timeSec") is not None else item.get("time_sec") or ""))


def keyframe_score(item: dict[str, Any]) -> int:
    return (
        len(item.get("wallPolygon") or [])
        + len(item.get("wallPaintSegments") or [])
        + len(item.get("polygon") or item.get("mask_polygon") or [])
        + len(item.get("lumenPolygon") or [])
    )


def union_by_key(
    first: list[Any] | None,
    second: list[Any] | None,
    key_fn,
    richer_fn=None,
) -> list[Any]:
    ordered: list[Any] = []
    index: dict[Any, int] = {}
    for item in list(first or []) + list(second or []):
        if not isinstance(item, dict):
            continue
        key = key_fn(item)
        if key in index:
            pos = index[key]
            if richer_fn and richer_fn(item) > richer_fn(ordered[pos]):
                ordered[pos] = item
            continue
        index[key] = len(ordered)
        ordered.append(item)
    return ordered


def merge_overlap(local: dict[str, Any], public: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    merged = dict(public)
    merged["activity_log"] = union_by_key(
        public.get("activity_log"),
        local.get("activity_log"),
        activity_key,
    )
    merged["doctor_keyframes"] = union_by_key(
        public.get("doctor_keyframes"),
        local.get("doctor_keyframes"),
        keyframe_key,
        keyframe_score,
    )
    for field in ("mask_save_count", "keyframe_mark_count"):
        merged[field] = max(int(local.get(field) or 0), int(public.get(field) or 0))
    local_done = bool(local.get("completed") or local.get("progress") == "completed")
    public_done = bool(public.get("completed") or public.get("progress") == "completed")
    merged["completed"] = local_done or public_done
    if merged["completed"]:
        merged["progress"] = "completed"
    for field in ("final_stage", "final_nature", "initial_stage", "initial_nature"):
        if not merged.get(field) and local.get(field):
            merged[field] = local.get(field)
    local_at = str(local.get("updated_at") or "")
    public_at = str(public.get("updated_at") or "")
    merged["updated_at"] = max(local_at, public_at)
    merged["created_at"] = min(str(local.get("created_at") or public_at), str(public.get("created_at") or local_at)) or merged.get("created_at")

    diffs = {}
    for field in SCALAR_CONFLICT_FIELDS:
        left = local.get(field)
        right = public.get(field)
        if left not in (None, "") and right not in (None, "") and str(left) != str(right):
            diffs[field] = {"local": left, "public": right}
    conflict = None
    if diffs:
        conflict = {
            "account_id": merged["account_id"],
            "case_id": merged["case_id"],
            "fields": diffs,
            "local_keyframes": len(local.get("doctor_keyframes") or []),
            "public_keyframes": len(public.get("doctor_keyframes") or []),
            "merged_keyframes": len(merged.get("doctor_keyframes") or []),
            "kept_finals_from": "public",
        }
    return merged, conflict


def merge_stores(local_rows: list[dict[str, Any]], public_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for row in local_rows:
        key = row_key(row)
        by_key[key] = row
        order.append(key)
    added = 0
    merged_overlap = 0
    conflicts: list[dict[str, Any]] = []
    for row in public_rows:
        key = row_key(row)
        if key not in by_key:
            by_key[key] = row
            order.append(key)
            added += 1
            continue
        merged, conflict = merge_overlap(by_key[key], row)
        by_key[key] = merged
        merged_overlap += 1
        if conflict:
            conflicts.append(conflict)
    return {
        "entries": [by_key[key] for key in order],
        "added": added,
        "merged_overlap": merged_overlap,
        "conflicts": conflicts,
        "local_n": len(local_rows),
        "public_n": len(public_rows),
        "out_n": len(order),
    }


def write_store(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{datetime.now().strftime('%Y%m%d%H%M%S')}.tmp")
    tmp.write_text(json.dumps({"entries": entries}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", type=Path, default=DEFAULT_LOCAL)
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--conflicts", type=Path, default=None)
    parser.add_argument("--backup-dir", type=Path, default=None)
    args = parser.parse_args()

    local_rows = load_store(args.local)
    public_rows = load_store(args.public)
    result = merge_stores(local_rows, public_rows)
    dest = args.out or args.local
    if args.backup_dir and args.local.exists():
        args.backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.local, args.backup_dir / args.local.name)
    write_store(dest, result["entries"])
    conflicts_path = args.conflicts
    if conflicts_path is None and result["conflicts"]:
        conflicts_path = dest.parent / "backups" / f"case_state_conflicts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    if conflicts_path and result["conflicts"]:
        conflicts_path.parent.mkdir(parents=True, exist_ok=True)
        conflicts_path.write_text(json.dumps(result["conflicts"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "added": result["added"],
                "merged_overlap": result["merged_overlap"],
                "conflicts": len(result["conflicts"]),
                "local_n": result["local_n"],
                "public_n": result["public_n"],
                "out_n": result["out_n"],
                "out": str(dest),
                "conflicts_path": str(conflicts_path) if conflicts_path and result["conflicts"] else None,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
