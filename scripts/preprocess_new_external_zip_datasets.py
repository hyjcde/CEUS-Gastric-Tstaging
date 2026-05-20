#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import preprocess_direct_surgery_datasets as prep


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
DEFAULT_OUTPUT_ROOT = ROOT / "dataset" / "external"
DEFAULT_SPLIT_DIR = ROOT / "pipeline" / "data" / "tstaging_4class_region_contrastive_full" / "regions"


def normalize_key(value: object) -> str:
    text = "" if value is None or pd.isna(value) else str(value)
    text = text.strip()
    text = re.sub(r"\.0$", "", text)
    text = re.sub(r"\s+", "", text)
    if re.fullmatch(r"\d+", text):
        text = str(int(text))
    return text.lower()


def image_case_key(path: Path) -> str:
    stem = path.stem
    stem = re.sub(r"-\d+$", "", stem)
    return normalize_key(stem)


def label_from_pt(value: object) -> tuple[int | None, str]:
    if value is None or pd.isna(value):
        return None, ""
    text = str(value).strip()
    if not text:
        return None, ""
    try:
        number = int(float(text))
    except Exception:
        match = re.search(r"([1-5])", text)
        number = int(match.group(1)) if match else None
    if number is None:
        return None, text
    if number <= 1:
        return 0, "T1"
    if number == 2:
        return 1, "T2"
    if number == 3:
        return 2, "T3"
    return 3, "T4+"


def find_col(columns: list[object], patterns: list[str]) -> object | None:
    for col in columns:
        text = str(col)
        if any(pattern in text for pattern in patterns):
            return col
    return None


def load_label_map(root: Path) -> dict[str, dict]:
    labels: dict[str, dict] = {}
    for xlsx in sorted(root.rglob("*.xlsx")):
        try:
            excel = pd.ExcelFile(xlsx)
        except Exception:
            continue
        for sheet in excel.sheet_names:
            try:
                df = pd.read_excel(xlsx, sheet_name=sheet)
            except Exception:
                continue
            if df.empty:
                continue
            id_col = find_col(list(df.columns), ["ID", "住院号"])
            pt_col = find_col(list(df.columns), ["pT", "PT", "pＴ"])
            if id_col is None or pt_col is None:
                continue
            for _, row in df.iterrows():
                key = normalize_key(row.get(id_col))
                label, stage = label_from_pt(row.get(pt_col))
                if not key or label is None:
                    continue
                labels[key] = {
                    "label": label,
                    "T_stage": stage,
                    "pt_raw": row.get(pt_col),
                    "clinical_excel": str(xlsx),
                    "clinical_sheet": sheet,
                }
    return labels


def pair_images(root: Path) -> list[tuple[Path, Path]]:
    pairs = []
    for image_path in sorted([p for p in root.rglob("*") if p.suffix.lower() in IMAGE_EXTS]):
        mask_path = image_path.with_suffix(".nii.gz")
        if mask_path.exists():
            pairs.append((image_path, mask_path))
    return pairs


def rect_to_str(rect: tuple[int, int, int, int]) -> str:
    return ",".join(map(str, rect))


def process_dataset(name: str, root: Path, output_root: Path) -> tuple[list[dict], list[dict]]:
    center_root = output_root / name
    center_root.mkdir(parents=True, exist_ok=True)
    for child in center_root.iterdir():
        if child.is_dir():
            import shutil

            shutil.rmtree(child)
        else:
            child.unlink()

    label_map = load_label_map(root)
    pairs = pair_images(root)
    manifest_rows: list[dict] = []
    error_rows: list[dict] = []

    for index, (image_path, mask_path) in enumerate(pairs, start=1):
        sample_id = prep.safe_slug(f"{name}__{image_path.relative_to(root).with_suffix('')}")
        try:
            image_rgb = prep.load_image(image_path)
            h, w = image_rgb.shape[:2]
            mask = prep.load_mask(mask_path, (h, w))
            original_rect = (0, 0, w, h)
            ui_rect = prep.compute_auto_ui_crop_rect(image_rgb, profile_key=None, center_name=name, mask=mask)
            roi_rect = prep.compute_roi_crop_rect(mask)
            prep.save_variant("original", image_rgb, mask, sample_id, center_root)
            prep.save_variant("crop_ui", prep.crop_array(image_rgb, ui_rect), prep.crop_array(mask, ui_rect), sample_id, center_root)
            prep.save_variant("crop_roi", prep.crop_array(image_rgb, roi_rect), prep.crop_array(mask, roi_rect), sample_id, center_root)

            key = image_case_key(image_path)
            label_info = label_map.get(key, {})
            manifest_rows.append({
                "sample_id": sample_id,
                "image_source": str(image_path),
                "mask_source": str(mask_path),
                "group_targets": name,
                "image_width": w,
                "image_height": h,
                "original_rect": rect_to_str(original_rect),
                "ui_crop_rect": rect_to_str(ui_rect),
                "roi_crop_rect": rect_to_str(roi_rect),
                "case_key": key,
                "label": label_info.get("label"),
                "T_stage": label_info.get("T_stage", ""),
                "pt_raw": label_info.get("pt_raw", ""),
                "clinical_excel": label_info.get("clinical_excel", ""),
                "clinical_sheet": label_info.get("clinical_sheet", ""),
            })
            if index % 100 == 0:
                print(f"[{name}] processed {index}/{len(pairs)}", flush=True)
        except Exception as exc:
            error_rows.append({
                "sample_id": sample_id,
                "image_source": str(image_path),
                "mask_source": str(mask_path),
                "error": str(exc),
            })
    write_csv(center_root / "manifest.csv", manifest_rows)
    write_csv(center_root / "errors.csv", error_rows)
    return manifest_rows, error_rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_split_csv(rows: list[dict], split_dir: Path, output_root: Path) -> Path:
    out = split_dir / "test_external_newzip_clinical.csv"
    records = []
    for row in rows:
        if row.get("label") == "" or pd.isna(row.get("label")):
            continue
        sample_id = row["sample_id"]
        center = row["group_targets"]
        base = output_root / center
        records.append({
            "sample_id": sample_id,
            "patient_id": row["case_key"],
            "image_path": str(base / "crop_ui" / "images" / f"{sample_id}.jpg"),
            "roi_path": str(base / "crop_roi" / "images" / f"{sample_id}.jpg"),
            "mask_path": str(base / "crop_ui" / "roi_masks" / f"{sample_id}.png"),
            "lesion_pred_mask_path": str(base / "crop_ui" / "roi_masks" / f"{sample_id}.png"),
            "label": int(row["label"]),
            "T_stage": row["T_stage"],
            "class_label": row["T_stage"],
            "source": f"ext/newzip/{center}",
            "split": "test_external_newzip",
            "crop_box_x1": int(str(row["roi_crop_rect"]).split(",")[0]),
            "crop_box_y1": int(str(row["roi_crop_rect"]).split(",")[1]),
            "crop_box_x2": int(str(row["roi_crop_rect"]).split(",")[2]),
            "crop_box_y2": int(str(row["roi_crop_rect"]).split(",")[3]),
            "pt_raw": row.get("pt_raw", ""),
            "clinical_excel": row.get("clinical_excel", ""),
            "clinical_sheet": row.get("clinical_sheet", ""),
        })
    pd.DataFrame(records).to_csv(out, index=False)
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preprocess newly added external zip datasets into dataset/external.")
    review_root = ROOT / "data" / "extracted_external_province_review"
    parser.add_argument("--review-root", type=Path, default=review_root)
    parser.add_argument("--dehua-root", type=Path, default=ROOT / "data" / "extracted_dehua_direct_surgery_review" / "福建省德化县医院")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--split-dir", type=Path, default=DEFAULT_SPLIT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    all_rows: list[dict] = []
    all_errors: list[dict] = []
    datasets = [
        ("北京友谊医院", args.review_root / "北京友谊医院"),
        ("佛山市第一人民医院", args.review_root / "佛山市第一人民医院"),
        ("中核五〇四医院", args.review_root / "中核五〇四医院"),
        ("福建省德化县医院", args.dehua_root),
    ]
    for name, root in datasets:
        rows, errors = process_dataset(name, root, args.output_root)
        all_rows.extend(rows)
        all_errors.extend(errors)
    write_csv(args.output_root / "new_external_zip_manifest.csv", all_rows)
    write_csv(args.output_root / "new_external_zip_errors.csv", all_errors)
    split_csv = build_split_csv(all_rows, args.split_dir, args.output_root)
    summary = {
        "rows": len(all_rows),
        "errors": len(all_errors),
        "labeled_rows": int(sum(not pd.isna(row.get("label")) and row.get("label") != "" for row in all_rows)),
        "split_csv": str(split_csv),
    }
    (args.output_root / "new_external_zip_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
