#!/usr/bin/env python3
"""Quick LDH alignment check for gastric_tstaging_paper_v2.tex."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEX = ROOT / "docs/paper_drafts/tex_v2_ldh/gastric_tstaging_paper_v2.tex"


def word_count(text: str) -> int:
    text = re.sub(r"%.*", "", text)
    text = re.sub(r"\\begin\{tcolorbox\}.*?\\end\{tcolorbox\}", " ", text, flags=re.S)
    text = re.sub(r"\\[a-zA-Z@]+(\[[^\]]*\])?(\{[^}]*\})*", " ", text)
    return len(re.findall(r"\b[A-Za-z][A-Za-z0-9\-]*\b", text))


def section_text(tex: str, name: str) -> str:
    if name == "Summary":
        m = re.search(r"\\section\*\{Summary\}(.*?)(?=\\section)", tex, re.S)
    else:
        m = re.search(rf"\\section\{{{name}\}}(.*?)(?=\\section)", tex, re.S)
    return m.group(1) if m else ""


def main() -> int:
    if not TEX.exists():
        print(f"ERROR: missing {TEX}", file=sys.stderr)
        return 1

    tex = TEX.read_text(encoding="utf-8", errors="ignore")
    cites = set()
    for block in re.findall(r"\\cite\{([^}]+)\}", tex):
        for k in block.split(","):
            cites.add(k.strip())
    bibs = set(re.findall(r"\\bibitem\{([^}]+)\}", tex))
    missing = sorted(c for c in cites if c not in bibs)

    checks = {
        "Summary section": bool(re.search(r"\\section\*\{Summary\}", tex)),
        "Summary Background": "textbf{Background}" in tex[:8000],
        "Summary Funding": "textbf{Funding}" in tex[:12000],
        "Research in context": "Research in context" in tex,
        "fig:cohortflow": "fig:cohortflow" in tex,
        "tab:benchmark": "tab:benchmark" in tex,
        "Statistical analysis": "Statistical analysis" in tex,
        "Contributors": "Contributors" in tex,
        "Appendix reader S10": "app:reader" in tex,
    }

    sections = ["Summary", "Introduction", "Methods", "Results", "Discussion"]
    print("=== LDH alignment check ===")
    print(f"TEX: {TEX.relative_to(ROOT)}")
    print()
    print("Structure:")
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print()
    print("Section word counts (rough):")
    total = 0
    for sec in sections:
        wc = word_count(section_text(tex, sec))
        total += wc
        print(f"  {sec:14s} {wc:5d}")
    print(f"  {'TOTAL (main)':14s} {total:5d}  target 3500-4500")
    print()
    print(f"Citations: {len(cites)}  Bibitems: {len(bibs)}")
    if missing:
        print(f"  MISSING bibitems: {missing}")
    else:
        print("  All citations resolved.")
    print()
    print("Next: docs/ldh_mainline/GAP_TRACKER.md")
    return 0 if all(checks.values()) and not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
