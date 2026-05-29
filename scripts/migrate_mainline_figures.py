#!/usr/bin/env python3
"""Move docs/mainline/figures export tree to artifacts/docs_exports/ (symlink back)."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "docs/mainline/figures"
DST = PROJECT_ROOT / "artifacts/docs_exports/mainline_figures"
LOG = PROJECT_ROOT / "data/metadata/path_migration_log.csv"
README_TEXT = """# Mainline figures (exported)

Large PNG/JSON exports were moved to keep `docs/mainline/` lightweight.

**Location:** [artifacts/docs_exports/mainline_figures](../../../artifacts/docs_exports/mainline_figures/)

Rebuild: run the figure scripts referenced in `docs/mainline/tstaging_current_mainline.md`.
"""


def log_move(old: str, new: str) -> None:
    with LOG.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([old, new, "mv+symlink", date.today().isoformat(), "yes", "phase E docs slim"])


def main() -> None:
    if not SRC.exists():
        print("no figures dir")
        return
    if SRC.is_symlink():
        print("already symlinked")
        readme_path = PROJECT_ROOT / "docs/mainline/figures/README.md"
        if not readme_path.exists():
            readme_path.write_text(README_TEXT, encoding="utf-8")
            print("wrote README")
        return
    DST.parent.mkdir(parents=True, exist_ok=True)
    if not DST.exists():
        if SRC.exists() and not SRC.is_symlink():
            SRC.rename(DST)
            print(f"mv {SRC} -> {DST}")
            log_move("docs/mainline/figures", "artifacts/docs_exports/mainline_figures")
        else:
            print(f"src missing, using existing {DST}")
    if not SRC.exists():
        SRC.symlink_to(Path("../../artifacts/docs_exports/mainline_figures"))
        print("created symlink docs/mainline/figures")
    readme_path = PROJECT_ROOT / "docs/mainline/figures/README.md"
    readme_path.write_text(README_TEXT, encoding="utf-8")
    print("symlink + README ok")


if __name__ == "__main__":
    main()
