#!/usr/bin/env python3
"""OCR audit: burned-in hospital name on US frame headers vs folder label."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}

HOSPITAL_PATTERNS: list[tuple[str, str]] = [
    (r"lanzhou|lan zhou|兰州", "中核五〇四医院"),
    (r"504\s*hospital|504hospital", "中核五〇四医院"),
    (r"friendship|友谊", "北京友谊医院"),
    (r"foshan|佛山", "佛山市第一人民医院"),
    (r"dehua|德化", "福建省德化县医院"),
    (r"hubei|湖北|中西医结合", "湖北中西医结合医院"),
]


def crop_header(img: Image.Image, frac: float = 0.18) -> np.ndarray:
    w, h = img.size
    top_h = max(40, int(h * frac))
    return np.array(img.crop((0, 0, w, top_h)).convert("RGB"))


def detect_hospitals(text: str) -> list[str]:
    t = text.lower()
    hits: list[str] = []
    for pat, label in HOSPITAL_PATTERNS:
        if re.search(pat, t, re.I):
            hits.append(label)
    return hits


def audit_center(
    center_name: str,
    root: Path,
    reader,
    header_frac: float,
) -> list[dict]:
    rows: list[dict] = []
    images = sorted(p for p in root.rglob("*") if p.suffix.lower() in IMAGE_EXTS)
    for image_path in images:
        rel = str(image_path.relative_to(root))
        try:
            img = Image.open(image_path)
            texts = reader.readtext(crop_header(img, header_frac), detail=0, paragraph=True)
            ocr = " | ".join(texts)
            detected = detect_hospitals(ocr)
            mismatch = bool(detected) and center_name not in detected
            rows.append(
                {
                    "center_folder": center_name,
                    "file": rel,
                    "ocr_header": ocr[:300],
                    "detected_hospitals": ";".join(detected),
                    "mismatch": mismatch,
                    "expected_center": center_name,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "center_folder": center_name,
                    "file": rel,
                    "ocr_header": "",
                    "detected_hospitals": "",
                    "mismatch": True,
                    "expected_center": center_name,
                    "error": str(exc),
                }
            )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit burned-in hospital names on external US images.")
    parser.add_argument(
        "--review-root",
        type=Path,
        default=ROOT / "data" / "extracted_external_province_review",
    )
    parser.add_argument(
        "--dehua-root",
        type=Path,
        default=ROOT / "data" / "extracted_dehua_direct_surgery_review" / "福建省德化县医院",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "dataset" / "tables" / "external_hospital_overlay_audit.csv")
    parser.add_argument("--header-frac", type=float, default=0.18)
    parser.add_argument("--gpu", action="store_true", default=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    import easyocr

    reader = easyocr.Reader(["en", "ch_sim"], gpu=args.gpu, verbose=False)
    centers = [
        ("北京友谊医院", args.review_root / "北京友谊医院"),
        ("佛山市第一人民医院", args.review_root / "佛山市第一人民医院"),
        ("中核五〇四医院", args.review_root / "中核五〇四医院"),
        ("福建省德化县医院", args.dehua_root),
    ]
    # Legacy mislabeled folder (pre-2026-05-20); audit if still present
    legacy = args.review_root / "湖北中西医结合医院"
    if legacy.exists():
        centers.append(("湖北中西医结合医院(legacy)", legacy))
    all_rows: list[dict] = []
    for name, root in centers:
        if not root.exists():
            print(f"[skip] missing {name}: {root}")
            continue
        print(f"[audit] {name} ...")
        all_rows.extend(audit_center(name, root, reader, args.header_frac))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "center_folder",
        "file",
        "ocr_header",
        "detected_hospitals",
        "mismatch",
        "expected_center",
        "error",
    ]
    with args.output.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)

    mismatches = [r for r in all_rows if str(r.get("mismatch")).lower() in {"true", "1"}]
    by_center: dict[str, int] = {}
    for r in mismatches:
        by_center[r["center_folder"]] = by_center.get(r["center_folder"], 0) + 1
    print(f"Wrote {args.output} ({len(all_rows)} rows, {len(mismatches)} mismatches)")
    for center, count in sorted(by_center.items()):
        print(f"  mismatch {center}: {count}")


if __name__ == "__main__":
    main()
