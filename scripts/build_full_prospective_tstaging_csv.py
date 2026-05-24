#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_SCRIPTS = PROJECT_ROOT / "pipeline" / "scripts"
TOOLKIT_ROOT = PIPELINE_SCRIPTS / "t2_t3_toolkit"
for path in (PIPELINE_SCRIPTS, TOOLKIT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from clinical_master_utils import ensure_patient_clinical_master, generate_split_clinical_tables  # noqa: E402
from common import extract_patient_and_frame  # noqa: E402


DEFAULT_IMAGE_DIR = PROJECT_ROOT / "dataset" / "internal" / "prospective_2025" / "2025" / "crop_ui" / "images"
DEFAULT_MASK_DIR = PROJECT_ROOT / "dataset" / "internal" / "prospective_2025" / "2025" / "crop_ui" / "roi_masks"
DEFAULT_ROI_IMAGE_DIR = PROJECT_ROOT / "dataset" / "internal" / "prospective_2025" / "2025" / "crop_roi" / "images"
DEFAULT_BASE_DIR = PROJECT_ROOT / "pipeline" / "data" / "tstaging_4class"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "pipeline" / "data" / "tstaging_4class_prospective_full"

PT_TO_STAGE = {
    1: ("T1", 0),
    2: ("T2", 1),
    3: ("T3", 2),
    4: ("T4a", 3),
    5: ("T4b", 3),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a full internal 2025 prospective T-staging CSV from crop-ui images and clinical master rows."
    )
    parser.add_argument("--image-dir", type=Path, default=DEFAULT_IMAGE_DIR)
    parser.add_argument("--mask-dir", type=Path, default=DEFAULT_MASK_DIR)
    parser.add_argument("--roi-image-dir", type=Path, default=DEFAULT_ROI_IMAGE_DIR)
    parser.add_argument("--base-dir", type=Path, default=DEFAULT_BASE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--split-name",
        default="test_prospective_full",
        help="CSV stem for the rebuilt full prospective split.",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--include-all-images",
        action="store_true",
        help="Include every crop_ui frame even without pT/clinical (2430 total). "
        "Missing pT rows use placeholder label T1 for pipeline compatibility.",
    )
    return parser.parse_args()


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT))


def load_2025_master() -> dict[str, dict]:
    master = ensure_patient_clinical_master()
    master = master[
        (master["dataset_key"].astype(str) == "internal_xh_2025")
        & master["pT"].notna()
    ].copy()
    rows: dict[str, dict] = {}
    for row in master.to_dict("records"):
        try:
            pt = int(float(row["pT"]))
        except (TypeError, ValueError):
            continue
        if pt not in PT_TO_STAGE:
            continue
        row["pT_int"] = pt
        rows[str(row["patient_id_norm"])] = row
    return rows


def build_rows(
    image_dir: Path,
    mask_dir: Path,
    roi_image_dir: Path,
    master_by_pid: dict[str, dict],
    *,
    include_all_images: bool = False,
) -> tuple[pd.DataFrame, dict]:
    image_paths = sorted(
        path for path in image_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
    )
    rows: list[dict] = []
    missing_clinical: list[str] = []
    missing_mask: list[str] = []
    missing_roi_image: list[str] = []
    missing_patient_id: list[str] = []

    for image_path in image_paths:
        patient_id, _frame = extract_patient_and_frame(image_path.stem)
        if patient_id is None:
            missing_patient_id.append(image_path.name)
            continue
        master_row = master_by_pid.get(str(patient_id))
        if master_row is None:
            missing_clinical.append(image_path.name)
            if not include_all_images:
                continue
        mask_path = mask_dir / f"{image_path.stem}.png"
        if not mask_path.exists():
            missing_mask.append(image_path.name)
            continue
        roi_image_path = roi_image_dir / image_path.name
        if not roi_image_path.exists():
            missing_roi_image.append(image_path.name)
            continue
        if master_row is None:
            stage, class_label = ("T1", 0)
            pt_missing = 1
        else:
            stage, class_label = PT_TO_STAGE[int(master_row["pT_int"])]
            pt_missing = 0
        image_rel = rel(image_path)
        mask_rel = rel(mask_path)
        roi_rel = rel(roi_image_path)
        rows.append(
            {
                "sample_id": image_path.stem,
                "image_path": image_rel,
                "roi_path": roi_rel,
                "mask_path": mask_rel,
                "lesion_pred_mask_path": mask_rel,
                "patient_id": patient_id,
                "label": class_label,
                "T_stage": stage,
                "class_label": class_label,
                "source": "int/prospective",
                "split": "test_prospective_full",
                "pt_missing": pt_missing,
            }
        )

    summary = {
        "image_rows_scanned": len(image_paths),
        "rows_with_clinical_pt_and_mask": int(sum(1 for row in rows if not row.get("pt_missing"))),
        "rows_without_pt_placeholder_label": int(sum(1 for row in rows if row.get("pt_missing"))),
        "rows_written": len(rows),
        "unique_patients_with_rows": len({row["patient_id"] for row in rows}),
        "missing_patient_id_images": len(missing_patient_id),
        "missing_clinical_or_pt_images": len(missing_clinical),
        "missing_mask_images": len(missing_mask),
        "missing_roi_image_rows": len(missing_roi_image),
        "examples": {
            "missing_patient_id_images": missing_patient_id[:20],
            "missing_clinical_or_pt_images": missing_clinical[:20],
            "missing_mask_images": missing_mask[:20],
            "missing_roi_image_rows": missing_roi_image[:20],
        },
    }
    return pd.DataFrame(rows), summary


def main() -> None:
    args = parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()) and not args.overwrite:
        raise FileExistsError(f"{args.output_dir} already exists; pass --overwrite to refresh it.")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for stem in ("train", "val", "test"):
        src = args.base_dir / f"{stem}.csv"
        if src.exists():
            shutil.copy2(src, args.output_dir / src.name)

    master_by_pid = load_2025_master()
    full_df, summary = build_rows(
        args.image_dir,
        args.mask_dir,
        args.roi_image_dir,
        master_by_pid,
        include_all_images=args.include_all_images,
    )
    out_csv = args.output_dir / f"{args.split_name}.csv"
    full_df.to_csv(out_csv, index=False)

    clinical_summary = generate_split_clinical_tables(
        data_dir=args.output_dir,
        master_df=ensure_patient_clinical_master(),
        output_dir=args.output_dir,
    )
    summary["output_csv"] = rel(out_csv)
    summary["clinical_generation_summary"] = clinical_summary.get(args.split_name, {})
    (args.output_dir / "full_prospective_build_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
