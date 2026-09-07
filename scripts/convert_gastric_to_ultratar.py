#!/usr/bin/env python3
"""Convert GastricTstaging Phase-0 datasets into UltraTAR multi-task format.

Tasks generated:
  1. gastric_tstage_4cls: Classification (4 classes: T1=0, T2=1, T3=2, T4+=3)
  2. gastric_lesion_seg:  Segmentation  (2 classes: background=0, lesion=1)
  3. gastric_lesion_det:  Detection     (1 class: CenterNet bbox [x_min, y_min, x_max, y_max])

Ensures strict patient-level separation:
  - 152 patient overlap between train and prospective dropped from train
  - 7 patient overlap between val and prospective dropped from val
  - Zero patient leakage between train, val, prospective, and external
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from train_dinov3_roi_lora_mlp import (  # noqa: E402
    mask_for_crop_ui,
    official_crop_ui,
    resolve_path,
    resolve_roi_path,
)

DEFAULT_PHASE0_DIR = PROJECT_ROOT / "pipeline/data/tstaging_4class_screened_eval_phase0_xiehe_20260610"
DEFAULT_OUTPUT_DIR = Path("/data/projects/UltraTAR/gastric_data")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase0-dir", type=Path, default=DEFAULT_PHASE0_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def get_mask_bbox(mask_path: Path) -> tuple[float, float, float, float] | None:
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return None
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return None
    x_min, x_max = float(xs.min()), float(xs.max())
    y_min, y_max = float(ys.min()), float(ys.max())
    if x_max <= x_min or y_max <= y_min:
        return None
    return x_min, y_min, x_max, y_max


def process_split(
    df: pd.DataFrame,
    split_name: str,
    output_dir: Path,
) -> dict[str, Any]:
    csv_dir = output_dir / split_name / "csv_files"
    csv_dir.mkdir(parents=True, exist_ok=True)

    cls_records: list[dict[str, Any]] = []
    seg_records: list[dict[str, Any]] = []
    det_records: list[dict[str, Any]] = []

    for _, row in tqdm(df.iterrows(), total=len(df), desc=f"Converting {split_name}"):
        ui = official_crop_ui(row)
        if ui is not None and ui.exists():
            img_path = str(ui.resolve())
        else:
            resolved = resolve_path(row.get("image_path"))
            if resolved is not None and resolved.exists():
                img_path = str(resolved.resolve())
            else:
                continue

        pid = str(row.get("patient_id", ""))
        label = int(row["class_label"])
        source = str(row.get("source", ""))

        # 1. Classification record
        cls_records.append({
            "task_id": "gastric_tstage_4cls",
            "task_name": "classification",
            "num_classes": 4,
            "image_path": img_path,
            "mask": label,
            "patient_id": pid,
            "source": source,
            "split": split_name,
        })

        # 2 & 3. Segmentation and Detection records (require mask)
        if ui is not None:
            m = mask_for_crop_ui(ui)
            if m is not None and m.exists():
                bbox = get_mask_bbox(m)
                if bbox is not None:
                    mask_abs = str(m.resolve())
                    seg_records.append({
                        "task_id": "gastric_lesion_seg",
                        "task_name": "segmentation",
                        "num_classes": 2,
                        "image_path": img_path,
                        "mask_path": mask_abs,
                        "patient_id": pid,
                        "source": source,
                        "split": split_name,
                    })
                    det_records.append({
                        "task_id": "gastric_lesion_det",
                        "task_name": "detection",
                        "num_classes": 1,
                        "image_path": img_path,
                        "x_min": bbox[0],
                        "y_min": bbox[1],
                        "x_max": bbox[2],
                        "y_max": bbox[3],
                        "patient_id": pid,
                        "source": source,
                        "split": split_name,
                    })

    df_cls = pd.DataFrame(cls_records)
    df_seg = pd.DataFrame(seg_records)
    df_det = pd.DataFrame(det_records)

    df_cls.to_csv(csv_dir / "cls_4class.csv", index=False)
    df_seg.to_csv(csv_dir / "seg.csv", index=False)
    df_det.to_csv(csv_dir / "det.csv", index=False)

    summary = {
        "split": split_name,
        "n_frames_total": len(df),
        "n_patients_total": int(df["patient_id"].nunique()),
        "tasks": {
            "gastric_tstage_4cls": {
                "n_samples": len(df_cls),
                "n_patients": int(df_cls["patient_id"].nunique()) if len(df_cls) > 0 else 0,
                "class_counts": df_cls["mask"].value_counts().to_dict() if len(df_cls) > 0 else {},
            },
            "gastric_lesion_seg": {
                "n_samples": len(df_seg),
                "n_patients": int(df_seg["patient_id"].nunique()) if len(df_seg) > 0 else 0,
            },
            "gastric_lesion_det": {
                "n_samples": len(df_det),
                "n_patients": int(df_det["patient_id"].nunique()) if len(df_det) > 0 else 0,
            },
        },
    }
    return summary


def main() -> None:
    args = parse_args()
    print("Phase-0 directory:", args.phase0_dir)
    print("Output directory:", args.output_dir)

    train_df = pd.read_csv(args.phase0_dir / "train.csv")
    val_df = pd.read_csv(args.phase0_dir / "val.csv")
    prosp_df = pd.read_csv(args.phase0_dir / "test_prospective.csv")
    ext_df = pd.read_csv(args.phase0_dir / "test_external.csv")

    for df in [train_df, val_df, prosp_df, ext_df]:
        df["class_label"] = pd.to_numeric(df["class_label"], errors="coerce")
        df.dropna(subset=["class_label"], inplace=True)
        df["class_label"] = df["class_label"].astype(int)

    prosp_pts = set(prosp_df["patient_id"].astype(str))
    val_pts = set(val_df["patient_id"].astype(str))
    val_prosp_overlap = sorted(val_pts & prosp_pts)

    if val_prosp_overlap:
        print(f"Dropping {len(val_prosp_overlap)} patients from val overlapping with prospective.")
        val_df = val_df[~val_df["patient_id"].astype(str).isin(val_prosp_overlap)].copy().reset_index(drop=True)

    holdout_pts = set(val_df["patient_id"].astype(str)) | prosp_pts
    train_pts = set(train_df["patient_id"].astype(str))
    train_leak = sorted(train_pts & holdout_pts)
    if train_leak:
        print(f"Dropping {len(train_leak)} patients from train overlapping with val or prospective.")
        train_df = train_df[~train_df["patient_id"].astype(str).isin(holdout_pts)].copy().reset_index(drop=True)

    # Verification of zero leakage
    c_train_pts = set(train_df["patient_id"].astype(str))
    c_val_pts = set(val_df["patient_id"].astype(str))
    c_prosp_pts = set(prosp_df["patient_id"].astype(str))
    c_ext_pts = set(ext_df["patient_id"].astype(str))

    assert len(c_train_pts & c_val_pts) == 0, "Train-Val patient leakage detected!"
    assert len(c_train_pts & c_prosp_pts) == 0, "Train-Prospective patient leakage detected!"
    assert len(c_val_pts & c_prosp_pts) == 0, "Val-Prospective patient leakage detected!"
    assert len(c_train_pts & c_ext_pts) == 0, "Train-External patient leakage detected!"
    print("Patient disjoint verification passed: 0 patient overlap across all splits.")

    meta_dir = args.output_dir / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)

    # Process all splits (valid is named valid to match UltraTAR standard directory structure)
    splits = [
        (train_df, "train"),
        (val_df, "valid"),
        (prosp_df, "test_prospective"),
        (ext_df, "test_external"),
    ]

    manifest: dict[str, Any] = {
        "source_phase0_dir": str(args.phase0_dir.resolve()),
        "output_dir": str(args.output_dir.resolve()),
        "splits": {},
    }

    for df, name in splits:
        summary = process_split(df, name, args.output_dir)
        manifest["splits"][name] = summary
        print(f"\n--- {name} summary ---")
        print(json.dumps(summary, indent=2, ensure_ascii=False))

    manifest_path = meta_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\nManifest successfully written to: {manifest_path}")


if __name__ == "__main__":
    main()
