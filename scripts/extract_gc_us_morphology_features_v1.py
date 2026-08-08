#!/usr/bin/env python3
"""Extract GC-US morphology features (NRL / substantial peaks / Fourier) from pred masks.

Reads anatomic phase0 frame CSVs + lesion pred masks, writes:
  pipeline/data/gc_us_tscore_features_v1/morphology/frame_features.csv
  pipeline/data/gc_us_tscore_features_v1/morphology/patient_features_median.csv
  (+ max / p90 columns in patient table)

Usage:
  python3 scripts/extract_gc_us_morphology_features_v1.py
  python3 scripts/extract_gc_us_morphology_features_v1.py --limit 200   # smoke
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

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
    compute_morphology_features,
    load_binary_mask,
    resolve_mask_path,
)

OUT_DIR = PROJECT_ROOT / "pipeline" / "data" / "gc_us_tscore_features_v1" / "morphology"

MORPH_COLS = [
    "morph_valid",
    "morph_area_px",
    "morph_perimeter_px",
    "morph_circularity",
    "morph_solidity",
    "morph_convexity",
    "morph_concavity_ratio",
    "morph_aspect_ratio",
    "morph_nrl_std",
    "morph_nrl_entropy",
    "morph_nrl_zero_crossing",
    "morph_nrl_roughness",
    "morph_nrl_area_ratio",
    "morph_n_substantial_peaks",
    "morph_n_spicule_like",
    "morph_n_lobule_like",
    "morph_peak_sharpness_max",
    "morph_peak_height_rel_max",
    "morph_fd_low_energy",
    "morph_fd_mid_energy",
    "morph_fd_high_energy",
    "morph_fd_very_high_energy",
    "morph_irregularity_index",
    "morph_legacy_perimeter_area",
]


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--anatomic-dir", type=Path, default=DEFAULT_ANATOMIC_DIR)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--limit", type=int, default=0, help="optional frame cap for smoke tests")
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
    for _, row in tqdm(frames.iterrows(), total=len(frames), desc="morphology"):
        mask_path = resolve_mask_path(str(row.get("lesion_pred_mask_path", "")), hash_index)
        base = {
            "patient_id": str(row.get("patient_id", "")),
            "label": row.get("label"),
            "source": row.get("source"),
            "split": row.get("split"),
            "split_file": row.get("split_file"),
            "image_path": row.get("image_path"),
            "lesion_pred_mask_path": str(mask_path) if mask_path else row.get("lesion_pred_mask_path"),
            "mask_resolved": int(mask_path is not None),
        }
        if mask_path is None:
            n_miss += 1
            feats = {c: 0.0 for c in MORPH_COLS}
            feats["morph_valid"] = 0.0
            rows.append({**base, **feats})
            continue
        mask = load_binary_mask(mask_path)
        if mask is None:
            n_miss += 1
            feats = {c: 0.0 for c in MORPH_COLS}
            rows.append({**base, **feats})
            continue
        feats = compute_morphology_features(mask)
        n_ok += 1
        rows.append({**base, **feats})

    frame_df = pd.DataFrame(rows)
    frame_path = out / "frame_features.csv"
    frame_df.to_csv(frame_path, index=False)

    valid = frame_df[frame_df["morph_valid"] > 0.5].copy()
    patient = aggregate_patient_features(valid, MORPH_COLS)
    patient_path = out / "patient_features_median.csv"
    patient.to_csv(patient_path, index=False)

    meta = {
        "n_frames": int(len(frame_df)),
        "n_valid_frames": int(n_ok),
        "n_missing_masks": int(n_miss),
        "n_patients_valid": int(len(patient)),
        "elapsed_sec": round(time.time() - t0, 2),
        "frame_csv": str(frame_path),
        "patient_csv": str(patient_path),
        "feature_cols": MORPH_COLS,
        "method": "NRL + substantial peaks + Fourier mid/high (exclude very-high as noise)",
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
