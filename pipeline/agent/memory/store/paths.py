"""Filesystem layout for self-evolving memory stores."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ...core.repo_paths import PROJECT_ROOT

DEFAULT_STORE_DATA_ROOT = PROJECT_ROOT / "pipeline" / "agent" / "memory" / "store_data"


@dataclass(frozen=True)
class MemoryStorePaths:
    root: Path
    episodes: Path
    procedural_rules: Path
    tool_governance: Path
    candidates: Path
    audit: Path

    def ensure(self) -> "MemoryStorePaths":
        self.root.mkdir(parents=True, exist_ok=True)
        for path in (
            self.episodes,
            self.procedural_rules,
            self.tool_governance,
            self.candidates,
            self.audit,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.touch()
        return self


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")


def default_store_root(run_id: Optional[str] = None) -> Path:
    rid = run_id or default_run_id()
    return DEFAULT_STORE_DATA_ROOT / rid


def resolve_store_paths(store_root: Optional[str | Path] = None, run_id: Optional[str] = None) -> MemoryStorePaths:
    root = Path(store_root) if store_root else default_store_root(run_id)
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    return MemoryStorePaths(
        root=root,
        episodes=root / "episodes.jsonl",
        procedural_rules=root / "procedural_rules.jsonl",
        tool_governance=root / "tool_governance.jsonl",
        candidates=root / "candidates.jsonl",
        audit=root / "audit.jsonl",
    )
