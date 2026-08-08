#!/usr/bin/env python3
"""Extract GC-US growth / breakthrough_v2 features (SDF + max/P90 patient agg).

Writes pipeline/data/gc_us_tscore_features_v1/growth/{frame,patient}_*.csv
Patient table includes median (default cols) plus __max / __p90 for BT redesign.
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
    compute_growth_features,
    load_binary_mask,
    lumen_mask_from_box,
    resolve_mask_path,
)

OUT_DIR = PROJECT_ROOT / "pipeline" / "data" / "gc_us_tscore_features_v1" / "growth"

GROWTH_COLS = [
    "growth_valid",
    "bt_v2_max_outward_depth",
    "bt_v2_mean_outward_depth",
    "bt_v2_fraction_outside_lumen",
    "bt_v2_fraction_inside_lumen",
    "bt_v2_contact_arc_ratio",
    "bt_v2_breakthrough_flag",
    "growth_outward_protrusion_ratio",
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
    n_ok = n_miss = n_no_lumen = 0
    t0 = time.time()
    for _, row in tqdm(frames.iterrows(), total=len(frames), desc="growth"):
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
            feats = {c: 0.0 for c in GROWTH_COLS}
            rows.append({**base, **feats})
            continue
        mask = load_binary_mask(mask_path)
        if mask is None:
            n_miss += 1
            feats = {c: 0.0 for c in GROWTH_COLS}
            rows.append({**base, **feats})
            continue
        h, w = mask.shape[:2]
        lumen = lumen_mask_from_box(
            h,
            w,
            row.get("lumen_box_x1"),
            row.get("lumen_box_y1"),
            row.get("lumen_box_x2"),
            row.get("lumen_box_y2"),
        )
        if lumen is None:
            n_no_lumen += 1
        feats = compute_growth_features(mask, lumen)
        if feats["growth_valid"] > 0.5:
            n_ok += 1
        rows.append({**base, **feats})

    frame_df = pd.DataFrame(rows)
    frame_df.to_csv(out / "frame_features.csv", index=False)
    valid = frame_df[frame_df["growth_valid"] > 0.5].copy()
    patient = aggregate_patient_features(valid, GROWTH_COLS)
    patient.to_csv(out / "patient_features_median.csv", index=False)
    meta = {
        "n_frames": int(len(frame_df)),
        "n_valid_frames": int(n_ok),
        "n_missing_masks": int(n_miss),
        "n_no_lumen": int(n_no_lumen),
        "n_patients_valid": int(len(patient)),
        "elapsed_sec": round(time.time() - t0, 2),
        "feature_cols": GROWTH_COLS,
        "note": "patient table includes median + __max + __p90; prefer __max for BT redesign",
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
