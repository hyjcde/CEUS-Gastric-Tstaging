#!/usr/bin/env python3
"""Ensure repo root only contains allowed workspace entries."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "data" / "metadata" / f"root_check_{date.today().strftime('%Y%m%d')}.json"

ALLOWED_FILES = {
    "START_HERE.md",
    "README.md",
    "REPO_LAYOUT.md",
    "MAINTENANCE.md",
    ".env",
    ".env.example",
    ".gitignore",
}

ALLOWED_DIRS = {
    "apps",
    "archive",
    "artifacts",
    "_compat",
    "configs",
    "data",
    "dataset",
    "docs",
    "experiments",
    "external",
    "models",
    "pipeline",
    "paper",
    "scripts",
    ".git",
    ".vscode",
}

# Warn-only: symlinks at root are discouraged but may exist in _compat migration period
DISCOURAGED_ROOT_PATTERNS = (".zip", ".pt", ".pth", ".ckpt")


def classify_entry(name: str) -> str:
    if name in ALLOWED_FILES:
        return "allowed_file"
    if name in ALLOWED_DIRS:
        return "allowed_dir"
    if name.endswith(DISCOURAGED_ROOT_PATTERNS):
        return "discouraged_asset_at_root"
    return "unexpected"


def main() -> int:
    unexpected: list[dict[str, str]] = []
    discouraged: list[dict[str, str]] = []
    allowed: list[str] = []

    for entry in sorted(PROJECT_ROOT.iterdir(), key=lambda p: p.name.lower()):
        kind = classify_entry(entry.name)
        if kind == "allowed_file" or kind == "allowed_dir":
            allowed.append(entry.name)
            continue
        item = {
            "name": entry.name,
            "kind": kind,
            "is_symlink": entry.is_symlink(),
            "resolved": str(entry.resolve()) if entry.exists() or entry.is_symlink() else None,
        }
        if kind == "discouraged_asset_at_root":
            discouraged.append(item)
        else:
            unexpected.append(item)

    ok = len(unexpected) == 0
    report = {
        "date": date.today().isoformat(),
        "pass": ok,
        "allowed_count": len(allowed),
        "unexpected": unexpected,
        "discouraged": discouraged,
        "hint": "Move unexpected items to artifacts/, data/raw/, or _compat/ per REPO_LAYOUT.md",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"pass": ok, "unexpected": len(unexpected), "discouraged": len(discouraged), "output": str(OUTPUT)}, ensure_ascii=False))
    if unexpected:
        for u in unexpected:
            print(f"  UNEXPECTED: {u['name']}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
