"""Validate memory records against self_evolving_multimodal_memory.schema.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple

from jsonschema import Draft202012Validator

from ...core.repo_paths import PROJECT_ROOT

SCHEMA_PATH = (
    PROJECT_ROOT
    / "pipeline"
    / "agent"
    / "memory"
    / "schemas"
    / "self_evolving_multimodal_memory.schema.json"
)
SCHEMA_VERSION = "0.1.0"


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_memory_record(record: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Return (ok, error_messages)."""
    errors = sorted({f"{'.'.join(str(p) for p in err.path)}: {err.message}" for err in _validator().iter_errors(record)})
    return (len(errors) == 0, errors)


def assert_valid_memory_record(record: Dict[str, Any]) -> None:
    ok, errors = validate_memory_record(record)
    if not ok:
        joined = "; ".join(errors[:8])
        raise ValueError(f"Invalid memory record: {joined}")
