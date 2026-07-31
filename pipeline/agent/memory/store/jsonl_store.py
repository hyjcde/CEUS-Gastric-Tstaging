"""Append-only JSONL store with status / quality metadata wrapper."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .paths import MemoryStorePaths, resolve_store_paths
from .schema_validate import assert_valid_memory_record


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rule_signature(record_type: str, body: Dict[str, Any]) -> str:
    parts: List[str] = [record_type]
    if record_type == "procedural_rule":
        pr = body.get("procedural_rule") or {}
        parts.extend([
            str(pr.get("title", "")),
            str(pr.get("rule_text", "")),
            ",".join(sorted(str(x) for x in (pr.get("target_scenario") or []))),
        ])
    elif record_type == "tool_governance":
        tg = body.get("tool_governance") or {}
        parts.extend([
            str(tg.get("tool_name", "")),
            str(tg.get("backend_id", "")),
            ",".join(sorted(str(x) for x in (tg.get("scenario") or []))),
        ])
    elif record_type == "case_episode":
        ce = body.get("case_episode") or {}
        parts.extend([
            str(ce.get("patient_id", "")),
            str((ce.get("agent_report") or {}).get("recommended_t_stage", "")),
        ])
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return digest


@dataclass
class StoreEntry:
    record: Dict[str, Any]
    status: str = "candidate"
    quality_score: float = 0.5
    support_count: int = 0
    rule_signature: str = ""
    patient_id: Optional[str] = None
    updated_at: str = field(default_factory=_utc_now)

    def to_line(self) -> Dict[str, Any]:
        return {
            "record": self.record,
            "status": self.status,
            "quality_score": round(float(self.quality_score), 4),
            "support_count": int(self.support_count),
            "rule_signature": self.rule_signature,
            "patient_id": self.patient_id,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_line(cls, line: Dict[str, Any]) -> "StoreEntry":
        record = line.get("record") or line
        record_type = str(record.get("record_type", ""))
        sig = str(line.get("rule_signature") or _rule_signature(record_type, record))
        patient_id = line.get("patient_id")
        if not patient_id and record.get("case_episode"):
            patient_id = (record.get("case_episode") or {}).get("patient_id")
        return cls(
            record=record,
            status=str(line.get("status", "candidate")),
            quality_score=float(line.get("quality_score", 0.5)),
            support_count=int(line.get("support_count", 0)),
            rule_signature=sig,
            patient_id=patient_id,
            updated_at=str(line.get("updated_at") or record.get("updated_at") or record.get("created_at") or _utc_now()),
        )


class JsonlMemoryStore:
    """Three-store JSONL backend plus candidates and audit trails."""

    def __init__(self, paths: Optional[MemoryStorePaths] = None, store_root: Optional[str | Path] = None):
        self.paths = paths or resolve_store_paths(store_root)
        self.paths.ensure()

    def _file_for_type(self, record_type: str) -> Path:
        mapping = {
            "case_episode": self.paths.episodes,
            "procedural_rule": self.paths.procedural_rules,
            "tool_governance": self.paths.tool_governance,
        }
        if record_type not in mapping:
            raise ValueError(f"Unknown record_type for store file: {record_type}")
        return mapping[record_type]

    def append_audit(self, event: str, payload: Dict[str, Any]) -> None:
        line = {"timestamp": _utc_now(), "event": event, **payload}
        with self.paths.audit.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")

    def append_entry(
        self,
        record: Dict[str, Any],
        *,
        status: str = "candidate",
        quality_score: float = 0.5,
        support_count: int = 0,
        patient_id: Optional[str] = None,
        validate: bool = True,
        also_candidates: bool = False,
    ) -> StoreEntry:
        if validate:
            assert_valid_memory_record(record)
        record_type = str(record["record_type"])
        sig = _rule_signature(record_type, record)
        entry = StoreEntry(
            record=record,
            status=status,
            quality_score=quality_score,
            support_count=support_count,
            rule_signature=sig,
            patient_id=patient_id,
        )
        target = self._file_for_type(record_type)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.to_line(), ensure_ascii=False) + "\n")
        if also_candidates or status == "candidate":
            with self.paths.candidates.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry.to_line(), ensure_ascii=False) + "\n")
        self.append_audit("append", {"record_id": record.get("record_id"), "record_type": record_type, "status": status})
        return entry

    def load_file(self, path: Path) -> List[StoreEntry]:
        if not path.exists():
            return []
        entries: List[StoreEntry] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                entries.append(StoreEntry.from_line(json.loads(raw)))
            except json.JSONDecodeError:
                continue
        return entries

    def load_all(self) -> Dict[str, List[StoreEntry]]:
        return {
            "episodes": self.load_file(self.paths.episodes),
            "procedural_rules": self.load_file(self.paths.procedural_rules),
            "tool_governance": self.load_file(self.paths.tool_governance),
            "candidates": self.load_file(self.paths.candidates),
        }

    def filter_entries(
        self,
        entries: Iterable[StoreEntry],
        *,
        patient_id: Optional[str] = None,
        status: Optional[str] = None,
        record_type: Optional[str] = None,
    ) -> List[StoreEntry]:
        out: List[StoreEntry] = []
        for entry in entries:
            if patient_id and entry.patient_id != patient_id:
                continue
            if status and entry.status != status:
                continue
            if record_type and entry.record.get("record_type") != record_type:
                continue
            out.append(entry)
        return out

    def rewrite_file(self, path: Path, entries: List[StoreEntry]) -> None:
        with path.open("w", encoding="utf-8") as fh:
            for entry in entries:
                fh.write(json.dumps(entry.to_line(), ensure_ascii=False) + "\n")

    def upsert_by_signature(self, record_type: str, entry: StoreEntry) -> None:
        path = self._file_for_type(record_type)
        entries = self.load_file(path)
        replaced = False
        for idx, existing in enumerate(entries):
            if existing.rule_signature == entry.rule_signature and existing.status == entry.status:
                entries[idx] = entry
                replaced = True
                break
        if not replaced:
            entries.append(entry)
        self.rewrite_file(path, entries)

    @staticmethod
    def new_record_id(prefix: str = "mem") -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"


def build_source(
    origin: str,
    path_or_uri: str,
    *,
    run_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    split: Optional[str] = None,
) -> Dict[str, Any]:
    src: Dict[str, Any] = {"origin": origin, "path_or_uri": path_or_uri}
    if run_id:
        src["run_id"] = run_id
    if patient_id:
        src["patient_id"] = patient_id
    if split:
        src["split"] = split
    return src
