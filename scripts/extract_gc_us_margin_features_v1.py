#!/usr/bin/env python3
"""Extract GC-US margin features robust to imprecise masks.

Selected pack (see compute_robust_margin_features):
  Image (soft-band / circles, not exact contour):
    BoF high/mid/peakiness, NRG, MI, soft margin contrast
  Shape (heavy-smoothed NRL):
    solidity, NRL entropy/std, needle_like, fd_mid/high, lobulation
  Composites:
    margin_spic_robust, margin_clear_robust

Writes pipeline/data/gc_us_tscore_features_v1/margin/{frame,patient}_*.csv
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import pandas as pd
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from gc_us_contour_features import (  # noqa: E402
    DEFAULT_ANATOMIC_DIR,
    DEFAULT_FRAME_CSVS,
    aggregate_patient_features,
    build_mask_hash_index,
    compute_margin_features,
    load_binary_mask,
    resolve_image_path,
    resolve_mask_path,
)

OUT_DIR = PROJECT_ROOT / "pipeline" / "data" / "gc_us_tscore_features_v1" / "margin"

MARGIN_COLS = [
    "margin_valid",
    # primary robust
    "margin_bof_high_mean",
    "margin_bof_mid_mean",
    "margin_bof_peakiness",
    "margin_bof_high_maxscale",
    "margin_nrg_mean",
    "margin_mi_band",
    "margin_contrast_soft",
    "margin_band_grad_mean",
    "margin_shape_solidity",
    "margin_shape_overlap",
    "margin_shape_nrl_entropy",
    "margin_shape_nrl_std",
    "margin_shape_needle_like",
    "margin_shape_fd_mid",
    "margin_shape_fd_high",
    "margin_shape_lobulation",
    "margin_spic_robust",
    "margin_clear_robust",
    "margin_band_halfwidth_px",
    # legacy aliases
    "margin_spicule_score",
    "margin_gradient_mean",
    "margin_gradient_contrast",
    "margin_weak_segment_ratio",
]


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--anatomic-dir", type=Path, default=DEFAULT_ANATOMIC_DIR)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--limit", type=int, default=0)
    return ap.parse_args()


def load_frames(anatomic_dir: Path) -> pd.DataFrame:
    parts = []
    for name in DEFAULT_FRAME_CSVS:
        path = anatomic_dir / name
        if not path.exists():
            continue
        df = pd.read_csv(path)
        df["split_file"] = name
        parts.append(df)
    if not parts:
        raise FileNotFoundError(f"no frame CSVs under {anatomic_dir}")
    return pd.concat(parts, ignore_index=True)


def main() -> None:
    args = parse_args()
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    frames = load_frames(args.anatomic_dir)
    if args.limit > 0:
        frames = frames.head(args.limit).copy()

    hash_index = build_mask_hash_index()
    rows = []
    n_ok = n_miss = 0
    t0 = time.time()
    for _, row in tqdm(frames.iterrows(), total=len(frames), desc="margin"):
        mask_path = resolve_mask_path(str(row.get("lesion_pred_mask_path", "")), hash_index)
        img_path = resolve_image_path(row.get("image_path"))
        base = {
            "patient_id": str(row.get("patient_id", "")),
            "label": row.get("label"),
            "source": row.get("source"),
            "split": row.get("split"),
            "split_file": row.get("split_file"),
            "image_path": row.get("image_path"),
            "lesion_pred_mask_path": str(mask_path) if mask_path else row.get("lesion_pred_mask_path"),
            "mask_resolved": int(mask_path is not None),
            "image_resolved": int(img_path is not None),
        }
        if mask_path is None:
            n_miss += 1
            feats = {c: 0.0 for c in MARGIN_COLS}
            rows.append({**base, **feats})
            continue
        mask = load_binary_mask(mask_path)
        if mask is None:
            n_miss += 1
            feats = {c: 0.0 for c in MARGIN_COLS}
            rows.append({**base, **feats})
            continue
        image = cv2.imread(str(img_path)) if img_path is not None else None
        feats = compute_margin_features(image, mask)
        n_ok += 1
        rows.append({**base, **{c: feats.get(c, 0.0) for c in MARGIN_COLS}})

    frame_df = pd.DataFrame(rows)
    frame_df.to_csv(out / "frame_features.csv", index=False)
    valid = frame_df[frame_df["margin_valid"] > 0.5].copy()
    patient = aggregate_patient_features(valid, MARGIN_COLS)
    patient.to_csv(out / "patient_features_median.csv", index=False)
    meta = {
        "n_frames": int(len(frame_df)),
        "n_valid_frames": int(n_ok),
        "n_missing_masks": int(n_miss),
        "n_patients_valid": int(len(patient)),
        "elapsed_sec": round(time.time() - t0, 2),
        "feature_cols": MARGIN_COLS,
        "design": "mask-imprecision-aware: BoF circles + soft-band NRG/MI + heavy-smoothed NRL shape",
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
