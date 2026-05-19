#!/usr/bin/env python3
"""Export project logic HTML to PDF (headless Chrome).

  python scripts/export_project_logic_pdf.py
  python scripts/export_project_logic_pdf.py --html docs/mainline/gastric_tstaging_project_logic_white.html
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HTML = PROJECT_ROOT / "docs" / "mainline" / "gastric_tstaging_project_logic_white.html"
DEFAULT_PDF = PROJECT_ROOT / "docs" / "mainline" / "gastric_tstaging_project_logic_white.pdf"


def find_chrome() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    raise SystemExit("Chrome/Chromium not found. Install google-chrome or set CHROME_BIN.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--wait-ms", type=int, default=8000, help="Wait for Mermaid render")
    args = parser.parse_args()

    html = args.html.resolve()
    pdf = args.pdf.resolve()
    if not html.is_file():
        raise SystemExit(f"HTML not found: {html}")

    chrome = find_chrome()
    url = html.as_uri()
    pdf.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--virtual-time-budget={args.wait_ms}",
        "--run-all-compositor-stages-before-draw",
        f"--print-to-pdf={pdf}",
        "--print-to-pdf-no-header",
        url,
    ]
    print(f"Exporting {html.name} -> {pdf}")
    subprocess.run(cmd, check=True)
    if pdf.is_file():
        print(f"OK: {pdf} ({pdf.stat().st_size // 1024} KB)")
        return 0
    print("PDF was not created.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
