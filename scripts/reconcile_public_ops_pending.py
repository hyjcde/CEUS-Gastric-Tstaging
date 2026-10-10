#!/usr/bin/env python3
"""Pull leftover public-edge ops into the workstation runtime store.

Public Next dual-writes locally on Aliyun, then proxies to this GPU box.
When the reverse tunnel or :3300 is down (reboot, SAM still loading), events
land in Aliyun `doctor_operation_events_pending.jsonl` and never drain —
`/admin/ops` on the public host proxies to the workstation and never reads
that pending file.

This script is idempotent: it copies Aliyun runtime shards into a temp
staging dir, appends missing event_ids, and merges case-state only when the
merged entries actually change. It does not snapshot the workstation json
files. Case-order is restored only when the workstation copy is empty.
Remote pending is truncated after a successful ops merge.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_doctor_case_state_preserve import merge_stores, write_store

ROOT = Path("/data/research/gastric/GastricTstaging")
RUNTIME = ROOT / "runtime" / "gastric_scan_next"
DEFAULT_REMOTE = "aliyun-reader"
DEFAULT_REMOTE_DIR = "/var/www/runtime-data"
REMOTE_FILES = (
    "doctor_operation_events.jsonl",
    "doctor_operation_events-2026-08.jsonl",
    "doctor_operation_events-2026-08-24.jsonl",
    "doctor_operation_events_pending.jsonl",
    "doctor_operation_history.json",
    "doctor_case_state.json",
    "reader_audit_events.jsonl",
    "viewing_trace_events.jsonl",
    "reader_case_order_by_account.json",
)


def log(msg: str) -> None:
    print(msg, flush=True)


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def event_id(row: dict, keys: tuple[str, ...] = ("event_id", "id")) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def month_key(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        dt = datetime.now(timezone.utc)
    return f"{dt.year:04d}-{dt.month:02d}"


def day_key(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        dt = datetime.now(timezone.utc)
    return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"


def append_jsonl(path: Path, rows: list[dict]) -> int:
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    return len(rows)


def pull_remote(remote: str, remote_dir: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    sources = [f"{remote}:{remote_dir}/{name}" for name in REMOTE_FILES]
    cmd = [
        "rsync",
        "-az",
        "-e",
        "ssh -o BatchMode=yes -o ConnectTimeout=20",
        *sources,
        str(dest) + "/",
    ]
    subprocess.run(cmd, check=True)


def merge_ops(local_dir: Path, public_dir: Path) -> list[dict]:
    local_files = sorted(local_dir.glob("doctor_operation_events*.jsonl"))
    seen: set[str] = set()
    for path in local_files:
        if path.name.endswith("_pending.jsonl"):
            continue
        for row in load_jsonl(path):
            eid = event_id(row)
            if eid:
                seen.add(eid)

    incoming: list[dict] = []
    incoming_ids: set[str] = set()
    for name in (
        "doctor_operation_events_pending.jsonl",
        "doctor_operation_events-2026-08.jsonl",
        "doctor_operation_events.jsonl",
        "doctor_operation_events-2026-08-24.jsonl",
    ):
        for row in load_jsonl(public_dir / name):
            eid = event_id(row)
            if not eid or eid in seen or eid in incoming_ids:
                continue
            incoming.append(row)
            incoming_ids.add(eid)

    incoming.sort(key=lambda row: str(row.get("recorded_at") or ""))
    if not incoming:
        log("ops: no missing events")
        return []

    by_month: dict[str, list[dict]] = defaultdict(list)
    by_day: dict[str, list[dict]] = defaultdict(list)
    for row in incoming:
        recorded = str(row.get("recorded_at") or "")
        by_month[month_key(recorded)].append(row)
        by_day[day_key(recorded)].append(row)

    append_jsonl(local_dir / "doctor_operation_events.jsonl", incoming)
    for key, rows in by_month.items():
        append_jsonl(local_dir / f"doctor_operation_events-{key}.jsonl", rows)
    for key, rows in by_day.items():
        append_jsonl(local_dir / f"doctor_operation_events-{key}.jsonl", rows)

    accounts = {}
    for row in incoming:
        accounts[str(row.get("account_id") or "?")] = accounts.get(str(row.get("account_id") or "?"), 0) + 1
    log(f"ops: appended {len(incoming)} events {accounts}")
    return incoming


def upsert_history(local_dir: Path, events: list[dict]) -> int:
    path = local_dir / "doctor_operation_history.json"
    store = {"entries": []}
    if path.exists():
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            store["entries"] = list(parsed.get("entries") or [])
        except json.JSONDecodeError:
            store["entries"] = []

    added = 0
    for event in events:
        owner = str(event.get("account_id") or "").strip()
        session_id = str(event.get("session_id") or "").strip()
        case_id = str(event.get("case_id") or "").strip()
        if not owner or not session_id or not case_id or case_id == "_global":
            continue
        recorded = str(event.get("recorded_at") or datetime.now(timezone.utc).isoformat())
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        event_type = str(event.get("event_type") or "")
        action = str(event.get("op") or payload.get("action") or event_type)
        existing = next(
            (
                entry
                for entry in store["entries"]
                if entry.get("owner_account_id") == owner
                and entry.get("session_id") == session_id
                and not entry.get("deleted_at")
            ),
            None,
        )
        if existing:
            existing["case_id"] = case_id
            existing["patient_id"] = event.get("patient_id") or existing.get("patient_id")
            existing["title"] = existing.get("patient_id") or case_id
            existing["summary"] = action or event_type
            existing["event_count"] = int(existing.get("event_count") or 0) + 1
            existing["last_event_type"] = event_type
            existing["last_action"] = action or existing.get("last_action")
            existing["environment"] = event.get("access_channel") or existing.get("environment")
            existing["updated_at"] = recorded
            continue
        store["entries"].insert(
            0,
            {
                "history_id": f"hist_{owner}_{int(datetime.now().timestamp()):x}_{added:04d}",
                "owner_account_id": owner,
                "session_id": session_id,
                "case_id": case_id,
                "patient_id": event.get("patient_id"),
                "title": event.get("patient_id") or case_id,
                "summary": action or event_type,
                "event_count": 1,
                "last_event_type": event_type,
                "last_action": action or None,
                "environment": event.get("access_channel"),
                "created_at": recorded,
                "updated_at": recorded,
                "deleted_at": None,
            },
        )
        added += 1
    store["entries"] = store["entries"][:5000]
    path.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"history: upserted {len(events)} events, {added} new cards")
    return added


def canonical_rows(rows: list[dict]) -> str:
    return json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def merge_case_state_preserve(local_path: Path, public_path: Path) -> dict:
    from merge_doctor_case_state_preserve import load_store

    if not public_path.exists():
        log("case_state: public file missing, skip")
        return {}
    local_rows = load_store(local_path)
    result = merge_stores(local_rows, load_store(public_path))
    changed = canonical_rows(result["entries"]) != canonical_rows(local_rows)
    if changed:
        write_store(local_path, result["entries"])
    if result["conflicts"]:
        conflict_path = RUNTIME / "backups" / "case_state_conflicts.jsonl"
        conflict_path.parent.mkdir(parents=True, exist_ok=True)
        with conflict_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                        "conflicts": result["conflicts"],
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )
    log(
        f"case_state: added {result['added']} "
        f"merged_overlap {result['merged_overlap']} "
        f"conflicts {len(result['conflicts'])} "
        f"changed {int(changed)} "
        f"out {result['out_n']}"
    )
    return result


def restore_json_if_missing(local_path: Path, public_path: Path, label: str) -> bool:
    if not public_path.exists():
        log(f"{label}: public file missing, skip")
        return False
    if local_path.exists() and local_path.stat().st_size > 20:
        log(f"{label}: workstation already has {local_path.name} ({local_path.stat().st_size} bytes)")
        return False
    shutil.copy2(public_path, local_path)
    log(f"{label}: restored {local_path.name} from public ({public_path.stat().st_size} bytes)")
    return True


def merge_jsonl_by_id(local_path: Path, public_path: Path, label: str) -> int:
    if not public_path.exists():
        log(f"{label}: public file missing, skip")
        return 0
    seen: set[str] = set()
    for candidate in (local_path, local_path.with_name(local_path.stem + "_public.jsonl")):
        seen.update(event_id(row) for row in load_jsonl(candidate) if event_id(row))
    missing = [row for row in load_jsonl(public_path) if event_id(row) and event_id(row) not in seen]
    n = append_jsonl(local_path, missing)
    log(f"{label}: appended {n}")
    return n


def backfill_daily_from_monthly(local_dir: Path) -> int:
    monthly_files = sorted(local_dir.glob("doctor_operation_events-????-??.jsonl"))
    written = 0
    for monthly in monthly_files:
        day_seen: dict[str, set[str]] = {}
        for daily in local_dir.glob(monthly.stem + "-??.jsonl"):
            day = daily.name[len("doctor_operation_events-") : -len(".jsonl")]
            day_seen[day] = {event_id(row) for row in load_jsonl(daily) if event_id(row)}
        by_day: dict[str, list[dict]] = defaultdict(list)
        for row in load_jsonl(monthly):
            eid = event_id(row)
            if not eid:
                continue
            day = day_key(str(row.get("recorded_at") or ""))
            if eid in day_seen.get(day, set()):
                continue
            by_day[day].append(row)
            day_seen.setdefault(day, set()).add(eid)
        for day, rows in by_day.items():
            written += append_jsonl(local_dir / f"doctor_operation_events-{day}.jsonl", rows)
            log(f"daily backfill {day}: {len(rows)}")
    return written


def truncate_remote_pending(remote: str, remote_dir: str) -> None:
    remote_path = f"{remote_dir}/doctor_operation_events_pending.jsonl"
    subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", remote, f"cp -a {remote_path} {remote_path}.bak_restored && : > {remote_path}"],
        check=True,
    )
    log("remote pending truncated (backup .bak_restored)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument("--remote-dir", default=DEFAULT_REMOTE_DIR)
    parser.add_argument("--staging", default="/tmp/aliyun-runtime-restore")
    parser.add_argument("--skip-pull", action="store_true")
    parser.add_argument("--keep-remote-pending", action="store_true")
    args = parser.parse_args()

    staging = Path(args.staging)
    if not args.skip_pull:
        pull_remote(args.remote, args.remote_dir, staging)

    incoming = merge_ops(RUNTIME, staging)
    if incoming:
        upsert_history(RUNTIME, incoming)
    merge_case_state_preserve(RUNTIME / "doctor_case_state.json", staging / "doctor_case_state.json")
    restore_json_if_missing(
        RUNTIME / "reader_case_order_by_account.json",
        staging / "reader_case_order_by_account.json",
        "case_order",
    )
    merge_jsonl_by_id(RUNTIME / "reader_audit_events.jsonl", staging / "reader_audit_events.jsonl", "audit")
    merge_jsonl_by_id(RUNTIME / "viewing_trace_events.jsonl", staging / "viewing_trace_events.jsonl", "viewing")
    backfill_daily_from_monthly(RUNTIME)

    if incoming and not args.keep_remote_pending:
        truncate_remote_pending(args.remote, args.remote_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
