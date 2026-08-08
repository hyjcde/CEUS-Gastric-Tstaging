#!/usr/bin/env python3
"""Extract GC-US wall-layer proxy features (frame + patient).

Uses anatomic Phase-0 clinical CSVs: lesion mask + lumen (mask or box) +
optional outer-wall mask. See gc_us_wall_layer_features.py for literature notes.

Writes pipeline/data/gc_us_tscore_features_v1/wall_layer/
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
    load_binary_mask,
    resolve_image_path,
    resolve_mask_path,
)
from gc_us_wall_layer_features import (  # noqa: E402
    SCORE_SEROSA,
    compute_wall_layer_features,
    depth_frac_to_wall_score,
    lumen_mask_from_box,
)

OUT_DIR = PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1/wall_layer"

FEATURE_COLS = [
    "wall_valid",
    "wall_thick_px_p50",
    "wall_depth_frac_p50",
    "wall_depth_frac_p90",
    "wall_depth_frac_max",
    "wall_layer_score_soft",
    "wall_mp_band_frac",
    "wall_outer_band_frac",
    "wall_serosa_interrupt",
    "wall_echo_transitions_lesion",
    "wall_echo_transitions_healthy",
    "wall_layer_disruption",
    "wall_contact_arc_ratio",
    "wall_has_outer_mask",
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


def resolve_rel(path_str: object) -> Path | None:
    if not path_str or not isinstance(path_str, str) or path_str.lower() == "nan":
        return None
    p = Path(path_str)
    if p.exists():
        return p
    alt = (PROJECT_ROOT / path_str).resolve()
    return alt if alt.exists() else None


def main() -> None:
    args = parse_args()
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    frames = load_frames(args.anatomic_dir)
    if args.limit > 0:
        frames = frames.head(args.limit).copy()

    hash_index = build_mask_hash_index()
    rows = []
    n_ok = 0
    t0 = time.time()
    for _, row in tqdm(frames.iterrows(), total=len(frames), desc="wall_layer"):
        mask_path = resolve_mask_path(str(row.get("lesion_pred_mask_path", "") or row.get("mask_path", "")), hash_index)
        img_path = resolve_image_path(row.get("image_path"))
        lumen_path = resolve_rel(row.get("anatomic_inner_lumen_mask_path"))
        outer_path = resolve_rel(row.get("anatomic_outer_wall_mask_path"))
        base = {
            "patient_id": str(row.get("patient_id", "")),
            "label": row.get("label"),
            "source": row.get("source"),
            "split": row.get("split"),
            "split_file": row.get("split_file"),
            "image_path": row.get("image_path"),
            "lesion_pred_mask_path": str(mask_path) if mask_path else row.get("lesion_pred_mask_path"),
            "image_resolved": int(img_path is not None),
            "mask_resolved": int(mask_path is not None),
        }
        if mask_path is None:
            rows.append({**base, **{c: 0.0 for c in FEATURE_COLS}})
            continue
        mask = load_binary_mask(mask_path)
        if mask is None:
            rows.append({**base, **{c: 0.0 for c in FEATURE_COLS}})
            continue
        lumen = load_binary_mask(lumen_path) if lumen_path else None
        if lumen is None:
            try:
                lumen = lumen_mask_from_box(
                    mask.shape,
                    float(row.get("lumen_box_x1", 0) or 0),
                    float(row.get("lumen_box_y1", 0) or 0),
                    float(row.get("lumen_box_x2", 0) or 0),
                    float(row.get("lumen_box_y2", 0) or 0),
                )
            except Exception:
                lumen = None
        if lumen is None or lumen.sum() < 30:
            rows.append({**base, **{c: 0.0 for c in FEATURE_COLS}})
            continue
        outer = load_binary_mask(outer_path) if outer_path else None
        image = cv2.imread(str(img_path), cv2.IMREAD_COLOR) if img_path is not None else None
        try:
            feats = compute_wall_layer_features(image, mask, lumen, outer)
        except Exception:
            feats = {c: 0.0 for c in FEATURE_COLS}
        n_ok += int(feats.get("wall_valid", 0) > 0.5)
        rows.append({**base, **{c: feats.get(c, 0.0) for c in FEATURE_COLS}})

    frame_df = pd.DataFrame(rows)
    # Recompute soft score from depth (+ conservative serosa bump) so definition
    # stays consistent if thresholds change without a full image re-pass.
    if len(frame_df):
        scores = frame_df["wall_depth_frac_p90"].map(depth_frac_to_wall_score)
        bump = (
            (frame_df["wall_serosa_interrupt"] >= 0.28)
            & (frame_df["wall_outer_band_frac"] >= 0.15)
        )
        frame_df["wall_layer_score_soft"] = scores.where(~bump, float(SCORE_SEROSA))
    frame_df.to_csv(out / "frame_features.csv", index=False)
    valid = frame_df[frame_df["wall_valid"] > 0.5].copy()
    patient = aggregate_patient_features(valid if len(valid) else frame_df, FEATURE_COLS)
    # Soft ordinal score: map patient median depth → score (not median of scores)
    if len(patient):
        ps = patient["wall_depth_frac_p90"].map(depth_frac_to_wall_score)
        pb = (
            (patient["wall_serosa_interrupt"] >= 0.28)
            & (patient["wall_outer_band_frac"] >= 0.15)
        )
        patient["wall_layer_score_soft"] = ps.where(~pb, float(SCORE_SEROSA))
    patient.to_csv(out / "patient_features_median.csv", index=False)
    meta = {
        "n_frames": int(len(frame_df)),
        "n_valid_frames": int(n_ok),
        "n_patients": int(len(patient)),
        "elapsed_sec": round(time.time() - t0, 2),
        "feature_cols": FEATURE_COLS,
        "design": "EUS 5-layer soft proxies via lumen→outer depth + echo disruption; not histologic GT",
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
