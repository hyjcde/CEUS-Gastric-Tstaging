#!/usr/bin/env python3
"""Rename external center folders to standard hospital names and update path references."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Direct folder renames under dataset/external and extracted review roots.
DIRECT_RENAMES: dict[str, str] = {
    "莆田1胃癌直接手术": "莆田学院附属医院",
    "莆田2胃癌直接手术": "莆田市第一医院",
    "肿瘤医院直接手术": "福建省肿瘤医院",
    "三明胃癌直接手术": "三明市第二医院",
    "德化直接手术": "福建省德化县医院",
}

# Split legacy newzip bundle by filename marker.
NEWZIP_SPLIT_MARKERS: list[tuple[str, str]] = [
    ("__北京__", "北京友谊医院"),
    ("__广东__", "佛山市第一人民医院"),
    ("__湖北", "中核五〇四医院"),
]

# Extracted review layout uses province subfolders before hospital rename.
EXTRACTED_PROVINCE_RENAMES: dict[str, str] = {
    "北京": "北京友谊医院",
    "广东": "佛山市第一人民医院",
    "湖北窦": "中核五〇四医院",
}

EXTRACTED_DEHUA_RENAME = ("德化直接手术", "福建省德化县医院")

CLINICAL_CENTER_RENAMES: dict[str, str] = {
    "协和内部": "福建医科大学附属协和医院",
    **DIRECT_RENAMES,
}

SOURCE_RENAMES: dict[str, str] = {
    "ext/newzip/德化直接手术": "ext/newzip/福建省德化县医院",
}

TEXT_SUFFIXES = {".csv", ".json", ".md", ".txt", ".yaml", ".yml", ".py"}
SKIP_DIR_NAMES = {".git", "__pycache__", "node_modules", ".venv"}


def replace_text(content: str) -> str:
    out = content
    # newzip split in paths and sample ids first
    out = out.replace("外省整理__湖北窦", "中核五〇四医院")
    out = out.replace("湖北中西医结合医院", "中核五〇四医院")
    out = out.replace("外省整理__广东", "佛山市第一人民医院")
    out = out.replace("外省整理__北京", "北京友谊医院")
    out = out.replace("外省整理/湖北窦", "中核五〇四医院")
    out = out.replace("外省整理/广东", "佛山市第一人民医院")
    out = out.replace("外省整理/北京", "北京友谊医院")
    for old, new in DIRECT_RENAMES.items():
        out = out.replace(old, new)
    for old, new in SOURCE_RENAMES.items():
        out = out.replace(old, new)
    return out


def rename_in_filename(name: str) -> str:
    return replace_text(name)


def ensure_empty_hospital_tree(root: Path) -> None:
    for view in ("original", "crop_ui", "crop_roi"):
        for sub in ("images", "annotations", "roi_masks", "overlays"):
            (root / view / sub).mkdir(parents=True, exist_ok=True)


def move_file(src: Path, dst: Path, dry_run: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        return
    if dst.exists():
        dst.unlink()
    shutil.move(str(src), str(dst))


def rename_tree_dir(src: Path, dst: Path, dry_run: bool) -> None:
    if not src.exists():
        return
    if dry_run:
        print(f"[dry-run] rename dir {src} -> {dst}")
        return
    if dst.exists():
        raise FileExistsError(f"target already exists: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def rename_files_inside(root: Path, dry_run: bool) -> int:
    count = 0
    if not root.exists():
        return count
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        new_name = rename_in_filename(path.name)
        if new_name == path.name:
            continue
        target = path.with_name(new_name)
        move_file(path, target, dry_run)
        count += 1
    return count


def split_newzip_bundle(src_root: Path, external_root: Path, dry_run: bool) -> dict[str, int]:
    moved = {name: 0 for _, name in NEWZIP_SPLIT_MARKERS}
    if not src_root.exists():
        return moved
    for hospital in moved:
        ensure_empty_hospital_tree(external_root / hospital)
    for path in sorted(src_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src_root)
        parts = rel.parts
        if not parts or parts[0] not in {"original", "crop_ui", "crop_roi"}:
            continue
        marker = next((h for m, h in NEWZIP_SPLIT_MARKERS if m in path.name), None)
        if marker is None:
            raise RuntimeError(f"cannot classify newzip file: {path}")
        # keep view/subdir structure: original/images/file.jpg
        dst = external_root / marker / Path(*parts)
        move_file(path, dst, dry_run)
        moved[marker] += 1
    if not dry_run and src_root.exists():
        for extra in src_root.glob("*.csv"):
            extra.unlink()
        for extra in src_root.glob("*.json"):
            extra.unlink()
        leftovers = [p for p in src_root.rglob("*") if p.is_file()]
        if leftovers:
            raise RuntimeError(f"unclassified files remain under {src_root}: {leftovers[:5]}")
        shutil.rmtree(src_root)
    return moved


def migrate_extracted_review(dry_run: bool) -> None:
    province_root = ROOT / "data" / "extracted_external_province_review" / "外省整理"
    if not province_root.exists():
        return
    review_root = ROOT / "data" / "extracted_external_province_review"
    for old, new in EXTRACTED_PROVINCE_RENAMES.items():
        rename_tree_dir(province_root / old, review_root / new, dry_run)
    if not dry_run and province_root.exists() and not any(province_root.iterdir()):
        province_root.rmdir()

    dehua_root = ROOT / "data" / "extracted_dehua_direct_surgery_review"
    old, new = EXTRACTED_DEHUA_RENAME
    rename_tree_dir(dehua_root / old, dehua_root / new, dry_run)


def migrate_external_folders(dry_run: bool) -> None:
    external_root = ROOT / "dataset" / "external"
    split_counts = split_newzip_bundle(external_root / "外省整理", external_root, dry_run)
    print("split 外省整理:", split_counts)

    for old, new in DIRECT_RENAMES.items():
        src = external_root / old
        dst = external_root / new
        rename_tree_dir(src, dst, dry_run)
        renamed = rename_files_inside(dst, dry_run)
        print(f"renamed files inside {new}: {renamed}")

    for hospital in [h for _, h in NEWZIP_SPLIT_MARKERS] + [DIRECT_RENAMES["德化直接手术"]]:
        renamed = rename_files_inside(external_root / hospital, dry_run)
        if renamed:
            print(f"renamed files inside {hospital}: {renamed}")


def rewrite_text_file(path: Path, dry_run: bool) -> bool:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return False
    try:
        original = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False
    updated = replace_text(original)
    if updated == original:
        return False
    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return True


def patch_newzip_sources(path: Path, dry_run: bool) -> bool:
    if path.name != "test_external_newzip_clinical.csv":
        return False
    try:
        df = __import__("pandas").read_csv(path, low_memory=False)
    except Exception:
        return False
    if "source" not in df.columns or "image_path" not in df.columns:
        return False

    def map_source(p: str) -> str:
        p = str(p)
        if "德化" in p or "福建省德化县医院" in p:
            return "ext/newzip/福建省德化县医院"
        if "北京" in p or "北京友谊医院" in p:
            return "ext/newzip/北京友谊医院"
        if "广东" in p or "佛山市第一人民医院" in p:
            return "ext/newzip/佛山市第一人民医院"
        if "湖北" in p or "湖北中西医结合医院" in p or "中核五〇四医院" in p or "504" in p:
            return "ext/newzip/中核五〇四医院"
        return "ext/newzip/unknown"

    df["source"] = df["image_path"].map(map_source)
    if not dry_run:
        df.to_csv(path, index=False)
    return True


def infer_group_target(sample_id: str) -> str | None:
    for marker, hospital in NEWZIP_SPLIT_MARKERS:
        if marker in sample_id:
            return hospital
    for hospital in [h for _, h in NEWZIP_SPLIT_MARKERS] + list(DIRECT_RENAMES.values()):
        if sample_id.startswith(hospital + "__"):
            return hospital
    for old, new in DIRECT_RENAMES.items():
        if sample_id.startswith(old + "__") or old in sample_id:
            return new
    return None


def update_manifest_csv(path: Path, dry_run: bool) -> None:
    if not path.exists() or path.suffix != ".csv":
        return
    rows = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        for row in reader:
            new_row = {k: replace_text(v) if isinstance(v, str) else v for k, v in row.items()}
            if "group_targets" in new_row and "sample_id" in new_row:
                inferred = infer_group_target(str(new_row["sample_id"]))
                if inferred:
                    new_row["group_targets"] = inferred
            rows.append(new_row)
    if not dry_run:
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def rewrite_repo_references(dry_run: bool) -> int:
    changed = 0
    targets = [
        ROOT / "dataset",
        ROOT / "pipeline" / "data",
        ROOT / "scripts",
        ROOT / "docs",
    ]
    for base in targets:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if patch_newzip_sources(path, dry_run):
                changed += 1
                continue
            if rewrite_text_file(path, dry_run):
                changed += 1
    return changed


def update_clinical_master(dry_run: bool) -> None:
    path = ROOT / "dataset" / "tables" / "patient_clinical_master.csv"
    if not path.exists():
        return
    pd = __import__("pandas")
    df = pd.read_csv(path, low_memory=False)
    if "center" in df.columns:
        df["center"] = df["center"].replace(CLINICAL_CENTER_RENAMES)
    if not dry_run:
        df.to_csv(path, index=False)


def update_center_registry(dry_run: bool) -> None:
    path = ROOT / "dataset" / "tables" / "center_name_registry.csv"
    if not path.exists():
        return
    pd = __import__("pandas")
    df = pd.read_csv(path, low_memory=False)
    if "legacy_folder_name" in df.columns:
        mapping = {
            **DIRECT_RENAMES,
            "外省整理/北京": "北京友谊医院",
            "外省整理/广东": "佛山市第一人民医院",
            "外省整理/湖北窦": "中核五〇四医院",
        }
        df["legacy_folder_name"] = df["legacy_folder_name"].replace(mapping)
    if "legacy_source_prefix" in df.columns:
        df["legacy_source_prefix"] = df["legacy_source_prefix"].replace(
            {
                "ext/newzip/外省整理": "ext/newzip/{center}",
                "ext/newzip/德化直接手术": "ext/newzip/福建省德化县医院",
            }
        )
        df.loc[df["center_id"] == "external_beijing_friendship", "legacy_source_prefix"] = "ext/newzip/北京友谊医院"
        df.loc[df["center_id"] == "external_foshan_first", "legacy_source_prefix"] = "ext/newzip/佛山市第一人民医院"
        df.loc[df["center_id"] == "external_cnnc_504", "legacy_source_prefix"] = "ext/newzip/中核五〇四医院"
    if not dry_run:
        df.to_csv(path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    migrate_extracted_review(args.dry_run)
    migrate_external_folders(args.dry_run)

    for manifest in sorted((ROOT / "dataset" / "external").rglob("manifest.csv")):
        update_manifest_csv(manifest, args.dry_run)

    for manifest in [
        ROOT / "dataset" / "external" / "new_external_zip_manifest.csv",
        ROOT / "dataset" / "external" / "errors.csv",
        ROOT / "dataset" / "external" / "unmatched_files.csv",
    ]:
        update_manifest_csv(manifest, args.dry_run)

    update_clinical_master(args.dry_run)
    update_center_registry(args.dry_run)
    changed = rewrite_repo_references(args.dry_run)
    print(f"rewrote text references in {changed} files")


if __name__ == "__main__":
    main()
