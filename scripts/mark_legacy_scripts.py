#!/usr/bin/env python3
"""Add '# STATUS: legacy' header to scripts marked legacy in script_registry.csv."""

from __future__ import annotations

import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = PROJECT_ROOT / "scripts/script_registry.csv"
MARKER = "# STATUS: legacy"
HEADER = f'"""Legacy script — prefer README §1–3 mainline. Do not use as default entry."""\n{MARKER}\n\n'


def main() -> None:
    updated = 0
    with REGISTRY.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status") != "legacy":
                continue
            path = PROJECT_ROOT / "scripts" / row["script"]
            if not path.suffix == ".py" or not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            if MARKER in text:
                continue
            if text.startswith('"""') or text.startswith("#!"):
                # insert after shebang or first docstring block — simple prepend
                path.write_text(HEADER + text, encoding="utf-8")
            else:
                path.write_text(HEADER + text, encoding="utf-8")
            updated += 1
    print(f"marked {updated} legacy scripts")


if __name__ == "__main__":
    main()
