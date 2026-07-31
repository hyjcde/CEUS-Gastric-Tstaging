from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.repo_paths import TMP_DIR

SESSIONS_DIR = TMP_DIR / "agent_sessions"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SessionMemory:
    session_id: str
    created_at: str
    updated_at: str
    patient_ids: List[str] = field(default_factory=list)
    analyses: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def path(self) -> Path:
        return SESSIONS_DIR / f"{self.session_id}.json"

    def append_analysis(self, payload: Dict[str, Any]) -> None:
        patient_id = str(payload.get("patient_id", ""))
        if patient_id and patient_id not in self.patient_ids:
            self.patient_ids.append(patient_id)
        self.analyses.append(payload)
        self.updated_at = _utc_now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "patient_ids": self.patient_ids,
            "analyses": self.analyses,
        }

    def save(self) -> None:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def load_session(session_id: Optional[str] = None) -> SessionMemory:
    if session_id:
        path = SESSIONS_DIR / f"{session_id}.json"
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            return SessionMemory(
                session_id=raw["session_id"],
                created_at=raw["created_at"],
                updated_at=raw["updated_at"],
                patient_ids=list(raw.get("patient_ids", [])),
                analyses=list(raw.get("analyses", [])),
            )

    now = _utc_now()
    return SessionMemory(
        session_id=session_id or uuid.uuid4().hex,
        created_at=now,
        updated_at=now,
    )

