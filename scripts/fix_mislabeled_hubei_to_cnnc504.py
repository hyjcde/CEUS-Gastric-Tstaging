#!/usr/bin/env python3
"""Reclassify 湖北中西医结合医院 pack (actually Lanzhou 504) to 中核五〇四医院."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OLD_CENTER = "湖北中西医结合医院"
NEW_CENTER = "中核五〇四医院"
OLD_REVIEW = ROOT / "data" / "extracted_external_province_review" / OLD_CENTER
NEW_REVIEW = ROOT / "data" / "extracted_external_province_review" / NEW_CENTER
OLD_DATASET = ROOT / "dataset" / "external" / OLD_CENTER
NEW_DATASET = ROOT / "dataset" / "external" / NEW_CENTER
CLINICAL_RENAME = {
    "湖北胃癌临床资料模板.xlsx": "中核五〇四医院胃癌临床资料模板.xlsx",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-preprocess", action="store_true", help="Only rename folders, do not rebuild crops.")
    parser.add_argument("--output-root", type=Path, default=ROOT / "dataset" / "external")
    parser.add_argument(
        "--review-root",
        type=Path,
        default=ROOT / "data" / "extracted_external_province_review",
    )
    return parser.parse_args()


def move_path(src: Path, dst: Path, dry_run: bool) -> None:
    if not src.exists():
        print(f"[skip] not found: {src}")
        return
    if dst.exists():
        raise FileExistsError(f"destination already exists: {dst}")
    print(f"[move] {src} -> {dst}")
    if dry_run:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def rename_clinical_files(review_dir: Path, dry_run: bool) -> None:
    for old_name, new_name in CLINICAL_RENAME.items():
        src = review_dir / old_name
        dst = review_dir / new_name
        if not src.exists():
            continue
        print(f"[rename] {src.name} -> {new_name}")
        if not dry_run:
            src.rename(dst)


def rebuild_manifests(output_root: Path, review_root: Path) -> dict:
    from scripts import preprocess_new_external_zip_datasets as prep

    rows, errors = prep.process_dataset(NEW_CENTER, NEW_REVIEW, output_root)
    all_rows: list[dict] = []
    all_errors: list[dict] = []
    datasets = [
        ("北京友谊医院", review_root / "北京友谊医院"),
        ("佛山市第一人民医院", review_root / "佛山市第一人民医院"),
        (NEW_CENTER, NEW_REVIEW),
    ]
    dehua = ROOT / "data" / "extracted_dehua_direct_surgery_review" / "福建省德化县医院"
    if dehua.exists():
        datasets.append(("福建省德化县医院", dehua))

    for name, root in datasets:
        if name == NEW_CENTER:
            all_rows.extend(rows)
            all_errors.extend(errors)
            continue
        if not (output_root / name / "manifest.csv").exists():
            r, e = prep.process_dataset(name, root, output_root)
            all_rows.extend(r)
            all_errors.extend(e)
        else:
            import pandas as pd

            manifest = output_root / name / "manifest.csv"
            df = pd.read_csv(manifest)
            all_rows.extend(df.to_dict(orient="records"))

    prep.write_csv(output_root / "new_external_zip_manifest.csv", all_rows)
    prep.write_csv(output_root / "new_external_zip_errors.csv", all_errors)
    split_dir = ROOT / "pipeline" / "data" / "tstaging_4class_region_contrastive_full" / "regions"
    split_csv = prep.build_split_csv(all_rows, split_dir, output_root)
    summary = {
        "rows": len(all_rows),
        "errors": len(all_errors),
        "labeled_rows": int(sum(row.get("label") not in ("", None) for row in all_rows)),
        "split_csv": str(split_csv),
        "reclassified_from": OLD_CENTER,
        "reclassified_to": NEW_CENTER,
    }
    (output_root / "new_external_zip_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def update_center_registry(dry_run: bool) -> None:
    """Registry is maintained in dataset/tables/center_name_registry.csv (see remediation doc)."""
    print("[registry] see dataset/tables/external_hubei_mislabel_remediation.md and center_name_registry.csv")


def main() -> None:
    args = parse_args()
    if not OLD_REVIEW.exists() and not NEW_REVIEW.exists():
        raise SystemExit(f"Neither review folder found: {OLD_REVIEW} / {NEW_REVIEW}")

    if OLD_REVIEW.exists():
        move_path(OLD_REVIEW, NEW_REVIEW, args.dry_run)
        rename_clinical_files(NEW_REVIEW, args.dry_run)

    if OLD_DATASET.exists():
        move_path(OLD_DATASET, NEW_DATASET, args.dry_run)

    if args.dry_run:
        print("[dry-run] stop before preprocess")
        return

    if not args.skip_preprocess:
        if not NEW_REVIEW.exists():
            raise SystemExit(f"Review folder missing after rename: {NEW_REVIEW}")
        summary = rebuild_manifests(args.output_root, args.review_root)
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    update_center_registry(args.dry_run)


if __name__ == "__main__":
    main()
