#!/usr/bin/env python3
"""Rebuild dataset/external from 胃癌直接手术外部测试集 with unified manifest."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import preprocess_direct_surgery_datasets as prep
from scripts import preprocess_new_external_zip_datasets as newzip_prep

SOURCE_ROOT = ROOT / "胃癌直接手术外部测试集" / "直接手术图片"
DATASET_ROOT = ROOT / "dataset" / "external"
ARCHIVE_ROOT = ROOT / "archive" / "dataset_external_legacy_20260528"
AUDIT_REPORT = DATASET_ROOT / "rebuild_audit.json"
SUMMARY_REPORT = DATASET_ROOT / "rebuild_summary.json"
SPLIT_DIR = ROOT / "pipeline" / "data" / "tstaging_4class"

CENTER_SOURCE_PREFIX = {
    "莆田学院附属医院": "ext/putian",
    "莆田市第一医院": "ext/putian2",
    "福建省肿瘤医院": "ext/zhongliu",
    "三明市第二医院": "ext/sanming",
    "北京友谊医院": "ext/北京友谊医院",
    "佛山市第一人民医院": "ext/佛山市第一人民医院",
    "中核五〇四医院": "ext/中核五〇四医院",
    "福建省德化县医院": "ext/福建省德化县医院",
    "福建省立医院": "ext/福建省立医院",
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".dcm"}
MASK_EXTS = {".nii", ".nii.gz", ".gz"}


def is_image(path: Path) -> bool:
    ext = "".join(path.suffixes).lower() if path.suffixes else path.suffix.lower()
    return ext in IMAGE_EXTS


def is_mask(path: Path) -> bool:
    ext = "".join(path.suffixes).lower() if path.suffixes else path.suffix.lower()
    return ext in MASK_EXTS or ext == ".gz"


def list_hospital_dirs() -> list[tuple[str, Path]]:
    if not SOURCE_ROOT.exists():
        raise FileNotFoundError(f"Source root not found: {SOURCE_ROOT}")
    hospitals: list[tuple[str, Path]] = []
    for path in sorted(SOURCE_ROOT.iterdir()):
        if not path.is_dir():
            continue
        center = prep.normalize_external_center_name(path.name)
        if center in prep.EXTERNAL_CENTER_NAMES:
            hospitals.append((center, path))
    return hospitals


def putian_source_layout(hospital_dir: Path) -> tuple[Path, list[Path], set[str], dict]:
    primary = hospital_dir / "直接手术"
    secondary = hospital_dir / "莆田学院附属医院"
    meta: dict = {"primary": str(primary), "secondary": str(secondary) if secondary.exists() else None}

    primary_stems: set[str] = set()
    if primary.exists():
        for path in primary.rglob("*"):
            if path.is_file() and is_image(path):
                stem = prep.normalize_base_name(path.name)
                primary_stems.add(stem)
                primary_stems.add(prep.compact_name(stem))

    overlap_stems: set[str] = set()
    secondary_unique = 0
    if secondary.exists():
        for path in secondary.rglob("*"):
            if not path.is_file() or not is_image(path):
                continue
            stem = prep.normalize_base_name(path.name)
            if stem in primary_stems or prep.compact_name(stem) in primary_stems:
                overlap_stems.add(stem)
            else:
                secondary_unique += 1

    meta.update(
        {
            "primary_image_stems": len(primary_stems),
            "overlap_dropped": len(overlap_stems),
            "secondary_unique_images": secondary_unique,
        }
    )
    extra_roots = [secondary] if secondary.exists() else []
    return primary if primary.exists() else hospital_dir, extra_roots, overlap_stems, meta


def audit_hospital(center_name: str, hospital_dir: Path) -> dict:
    if center_name == "莆田学院附属医院":
        source_root, extra_roots, overlap_stems, putian_meta = putian_source_layout(hospital_dir)
        image_entries, mask_entries = prep.collect_entries_from_roots(
            [source_root, *extra_roots],
            exclude_stems=overlap_stems,
        )
        putian_meta["source_root"] = str(source_root)
        putian_meta["extra_roots"] = [str(p) for p in extra_roots]
    else:
        putian_meta = None
        image_entries, mask_entries = prep.collect_entries_from_roots([hospital_dir])

    pairs, unmatched_images, unmatched_masks = prep.pair_images_and_masks(image_entries, mask_entries)
    return {
        "center_name": center_name,
        "source_dir": str(hospital_dir),
        "image_candidates": len(image_entries),
        "mask_candidates": len(mask_entries),
        "expected_pairs": len(pairs),
        "unmatched_images": len(unmatched_images),
        "unmatched_masks": len(unmatched_masks),
        "putian_dedup": putian_meta,
    }


def cmd_audit(output_path: Path) -> dict:
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_root": str(SOURCE_ROOT),
        "hospitals": [],
        "totals": {},
    }
    total_pairs = 0
    total_images = 0
    total_masks = 0
    for center_name, hospital_dir in list_hospital_dirs():
        item = audit_hospital(center_name, hospital_dir)
        report["hospitals"].append(item)
        total_pairs += item["expected_pairs"]
        total_images += item["image_candidates"]
        total_masks += item["mask_candidates"]

    report["totals"] = {
        "hospitals": len(report["hospitals"]),
        "image_candidates": total_images,
        "mask_candidates": total_masks,
        "expected_pairs": total_pairs,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["totals"], ensure_ascii=False, indent=2))
    print(f"[INFO] Audit report written to {output_path}")
    return report


def cmd_archive(dry_run: bool = False) -> None:
    if not DATASET_ROOT.exists():
        print(f"[INFO] Nothing to archive: {DATASET_ROOT} does not exist")
        return
    if ARCHIVE_ROOT.exists():
        raise FileExistsError(f"Archive target already exists: {ARCHIVE_ROOT}")
    print(f"[INFO] Archiving {DATASET_ROOT} -> {ARCHIVE_ROOT}")
    if dry_run:
        return
    ARCHIVE_ROOT.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(DATASET_ROOT), str(ARCHIVE_ROOT))
    DATASET_ROOT.mkdir(parents=True, exist_ok=True)
    readme = DATASET_ROOT / "README_REBUILD.txt"
    readme.write_text(
        "External dataset rebuilt from 胃癌直接手术外部测试集/直接手术图片.\n"
        f"Legacy copy: {ARCHIVE_ROOT}\n",
        encoding="utf-8",
    )


def process_one_hospital(
    center_name: str,
    hospital_dir: Path,
    output_root: Path,
    limit: Optional[int],
    dry_run: bool,
) -> Optional[prep.ProcessHospitalResult]:
    if center_name == "莆田学院附属医院":
        source_root, extra_roots, overlap_stems, _ = putian_source_layout(hospital_dir)
    else:
        source_root = hospital_dir
        extra_roots = []
        overlap_stems = set()

    print(f"[INFO] Hospital {center_name}: source={source_root}")
    if dry_run:
        item = audit_hospital(center_name, hospital_dir)
        print(f"[INFO] dry-run expected pairs={item['expected_pairs']}")
        return None

    return prep.process_external_hospital(
        center_name=center_name,
        source_root=source_root,
        output_root=output_root,
        limit=limit,
        clear_output=True,
        extra_source_roots=extra_roots or None,
        exclude_stems=overlap_stems or None,
    )


def cmd_run(
    limit: Optional[int],
    hospital: Optional[str],
    dry_run: bool,
    skip_archive: bool,
) -> None:
    if not skip_archive and not dry_run:
        cmd_archive(dry_run=False)

    hospitals = list_hospital_dirs()
    if hospital:
        hospital = prep.normalize_external_center_name(hospital)
        hospitals = [(name, path) for name, path in hospitals if name == hospital]
        if not hospitals:
            raise ValueError(f"Hospital not found in source root: {hospital}")

    DATASET_ROOT.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}

    for center_name, hospital_dir in hospitals:
        output_root = DATASET_ROOT / center_name
        result = process_one_hospital(center_name, hospital_dir, output_root, limit, dry_run)
        if result is not None:
            results[center_name] = {
                "manifest_rows": len(result.manifest_rows),
                "errors": len(result.error_rows),
                "unmatched": len(result.unmatched_rows),
                "matched_pairs": result.matched_pairs,
            }

    if not dry_run and results:
        interim = DATASET_ROOT / "rebuild_run_summary.json"
        interim.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[INFO] Run summary written to {interim}")


def read_csv_rows(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return [{key.lstrip("\ufeff"): value for key, value in row.items()} for row in rows]


def write_csv_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def cmd_finalize() -> dict:
    hospitals = list_hospital_dirs()
    all_manifest: list[dict] = []
    all_errors: list[dict] = []
    all_unmatched: list[dict] = []
    per_center: dict[str, dict] = {}

    for center_name, _ in hospitals:
        center_root = DATASET_ROOT / center_name
        manifest_rows = read_csv_rows(center_root / "manifest.csv")
        error_rows = read_csv_rows(center_root / "errors.csv")
        unmatched_rows = read_csv_rows(center_root / "unmatched_files.csv")
        crop_ui_count = len(list((center_root / "crop_ui" / "images").glob("*.jpg"))) if (center_root / "crop_ui" / "images").exists() else 0

        all_manifest.extend(manifest_rows)
        all_errors.extend(error_rows)
        all_unmatched.extend(unmatched_rows)
        per_center[center_name] = {
            "manifest_rows": len(manifest_rows),
            "errors": len(error_rows),
            "unmatched": len(unmatched_rows),
            "crop_ui_images": crop_ui_count,
        }

    write_csv_rows(DATASET_ROOT / "manifest.csv", all_manifest)
    write_csv_rows(DATASET_ROOT / "errors.csv", all_errors)
    write_csv_rows(DATASET_ROOT / "unmatched_files.csv", all_unmatched)

    deprecated = DATASET_ROOT / "new_external_zip_manifest.csv"
    if deprecated.exists():
        backup = DATASET_ROOT / "new_external_zip_manifest.csv.deprecated"
        shutil.move(str(deprecated), str(backup))

    legacy_manifest = ARCHIVE_ROOT / "manifest.csv"
    legacy_count = len(read_csv_rows(legacy_manifest)) if legacy_manifest.exists() else None

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_root": str(SOURCE_ROOT),
        "dataset_root": str(DATASET_ROOT),
        "archive_root": str(ARCHIVE_ROOT) if ARCHIVE_ROOT.exists() else None,
        "total_manifest_rows": len(all_manifest),
        "total_errors": len(all_errors),
        "total_unmatched": len(all_unmatched),
        "legacy_manifest_rows": legacy_count,
        "delta_manifest_rows": (len(all_manifest) - legacy_count) if legacy_count is not None else None,
        "per_center": per_center,
    }
    SUMMARY_REPORT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"[INFO] Summary written to {SUMMARY_REPORT}")
    return summary


def patient_id_from_row(row: dict) -> str:
    image_source = row.get("image_source", "")
    if image_source:
        stem = Path(image_source).stem
        stem = re.sub(r"-\d+$", "", stem)
        stem = re.sub(r"\(\d+\)$", "", stem).strip()
        if stem:
            return stem.lower()
    sample_id = row.get("sample_id", "")
    tail = sample_id.split("__")[-1]
    tail = re.sub(r"-\d+$", "", tail)
    tail = re.sub(r"\.0$", "", tail.strip())
    return tail.lower()


def lookup_key_from_row(row: dict) -> str:
    image_source = row.get("image_source", "")
    if image_source:
        path = Path(image_source)
        stem = path.stem
        candidates = [
            newzip_prep.image_case_key(path),
            newzip_prep.normalize_key(stem),
            newzip_prep.normalize_key(re.sub(r"[-_ ]*\(\d+\)$", "", stem)),
            newzip_prep.normalize_key(re.sub(r"-\d+$", "", stem)),
        ]
        return candidates[0] if candidates else newzip_prep.normalize_key(stem)
    return newzip_prep.normalize_key(patient_id_from_row(row))


def lookup_label_info(label_map: dict[str, dict], row: dict) -> dict:
    image_source = row.get("image_source", "")
    candidate_keys: list[str] = []
    if image_source:
        path = Path(image_source)
        stem = path.stem
        candidate_keys.extend(
            [
                newzip_prep.image_case_key(path),
                newzip_prep.normalize_key(stem),
                newzip_prep.normalize_key(re.sub(r"[-_ ]*\(\d+\)$", "", stem)),
                newzip_prep.normalize_key(re.sub(r"-\d+$", "", stem)),
            ]
        )
    candidate_keys.append(newzip_prep.normalize_key(patient_id_from_row(row)))
    seen: set[str] = set()
    for key in candidate_keys:
        if not key or key in seen:
            continue
        seen.add(key)
        if key in label_map:
            return label_map[key]
    return {}


def build_center_label_maps(center_name: str, hospital_dir: Path) -> dict[str, dict]:
    label_map = newzip_prep.load_label_map(hospital_dir)

    if center_name == "莆田学院附属医院":
        by_source = ROOT / "dataset" / "tables" / "by_source" / "external_putian1_direct_surgery__sheet1.csv"
        if by_source.exists():
            df = pd.read_csv(by_source, low_memory=False)
            pt_col = next((col for col in df.columns if str(col).startswith("pT")), None)
            if pt_col is not None and "序号" in df.columns:
                for _, row in df.iterrows():
                    label, stage = newzip_prep.label_from_pt(row.get(pt_col))
                    if label is None:
                        continue
                    info = {
                        "label": label,
                        "T_stage": stage,
                        "pt_raw": row.get(pt_col),
                    }
                    seq_key = newzip_prep.normalize_key(row.get("序号"))
                    if seq_key:
                        label_map[seq_key] = info
                    if "住院号" in df.columns:
                        hid_key = newzip_prep.normalize_key(row.get("住院号"))
                        if hid_key:
                            label_map[hid_key] = info
    return label_map


def cmd_build_splits(split_dir: Path) -> dict:
    manifest_rows = read_csv_rows(DATASET_ROOT / "manifest.csv")
    if not manifest_rows:
        raise FileNotFoundError(f"Missing unified manifest: {DATASET_ROOT / 'manifest.csv'}")

    split_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    per_center: dict[str, dict] = {}

    for center_name, _ in list_hospital_dirs():
        hospital_dir = SOURCE_ROOT / (
            "中核五O四医院" if center_name == "中核五〇四医院" else center_name
        )
        label_map = build_center_label_maps(center_name, hospital_dir)
        center_records: list[dict] = []
        source_prefix = CENTER_SOURCE_PREFIX[center_name]

        for row in manifest_rows:
            if row.get("group_targets") != center_name:
                continue
            sample_id = row["sample_id"]
            patient_id = patient_id_from_row(row)
            label_info = lookup_label_info(label_map, row)
            label = label_info.get("label")
            if label is None or label == "":
                continue
            t_stage = label_info.get("T_stage", "")
            base = DATASET_ROOT / center_name
            record = {
                "image_path": str(base / "crop_ui" / "images" / f"{sample_id}.jpg"),
                "roi_path": str(base / "crop_roi" / "images" / f"{sample_id}.jpg"),
                "patient_id": patient_id,
                "label": int(label),
                "T_stage": t_stage,
                "class_label": int(label),
                "source": source_prefix,
                "split": "test",
            }
            records.append(record)
            center_records.append(record)

        per_center[center_name] = {
            "manifest_rows": sum(1 for row in manifest_rows if row.get("group_targets") == center_name),
            "labeled_rows": len(center_records),
        }
        center_out = split_dir / f"test_ext_{center_name}.csv"
        write_csv_rows(center_out, center_records)

    out_path = split_dir / "test_external.csv"
    write_csv_rows(out_path, records)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_csv": str(out_path),
        "total_labeled_rows": len(records),
        "per_center": per_center,
    }
    (split_dir / "test_external_rebuild_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild dataset/external from unified external source.")
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="Audit source data without writing outputs.")
    audit.add_argument("--output", type=Path, default=AUDIT_REPORT)

    archive = sub.add_parser("archive", help="Archive current dataset/external only.")
    archive.add_argument("--dry-run", action="store_true")

    run = sub.add_parser("run", help="Archive (unless skipped) and rebuild hospital crop outputs.")
    run.add_argument("--limit", type=int, default=None)
    run.add_argument("--hospital", type=str, default=None)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--skip-archive", action="store_true")

    sub.add_parser("finalize", help="Merge per-hospital manifests into dataset/external/manifest.csv")

    build_splits = sub.add_parser("build-splits", help="Build test_external.csv from unified manifest + clinical labels")
    build_splits.add_argument("--split-dir", type=Path, default=SPLIT_DIR)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "audit":
        cmd_audit(args.output)
    elif args.command == "archive":
        cmd_archive(dry_run=args.dry_run)
    elif args.command == "run":
        cmd_run(
            limit=args.limit,
            hospital=args.hospital,
            dry_run=args.dry_run,
            skip_archive=args.skip_archive,
        )
    elif args.command == "finalize":
        cmd_finalize()
    elif args.command == "build-splits":
        cmd_build_splits(args.split_dir)


if __name__ == "__main__":
    main()
