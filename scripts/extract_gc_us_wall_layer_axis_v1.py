#!/usr/bin/env python3
"""Extract breakthrough-axis wall-layer proxies (mask geometry only; fast).

Clinical intent: measure 占壁厚 / deepest layer along the invasion ray
(ContactGeom deep_idx / penetrationAt; EUS deepest-disrupted-layer).

Writes beside whole-lesion wall features:
  pipeline/data/gc_us_tscore_features_v1/wall_layer/
    frame_features_axis.csv
    patient_features_axis_median.csv
    meta_axis.json
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
    load_binary_mask,
    resolve_mask_path,
)
from gc_us_wall_layer_features import (  # noqa: E402
    SCORE_SEROSA,
    compute_wall_axis_features,
    depth_frac_to_wall_score,
    lumen_mask_from_box,
)

OUT_DIR = PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1/wall_layer"

AXIS_COLS = [
    "wall_axis_valid",
    "wall_axis_depth_frac",
    "wall_axis_depth_frac_sector_p90",
    "wall_axis_score_soft",
    "wall_axis_remain_frac",
    "wall_axis_thick_px",
    "wall_axis_extent_px",
    "wall_axis_overshoot",
    "wall_axis_serosa_hit",
    "wall_axis_contact_ratio",
    "wall_axis_deep_idx_norm",
    "wall_axis_angle_deg",
    "wall_axis_used_csv_angle",
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
    for _, row in tqdm(frames.iterrows(), total=len(frames), desc="wall_axis"):
        mask_path = resolve_mask_path(
            str(row.get("lesion_pred_mask_path", "") or row.get("mask_path", "")),
            hash_index,
        )
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
            "breakthrough_max_depth": row.get("breakthrough_max_depth"),
            "direction_outward_angle_deg": row.get("direction_outward_angle_deg"),
            "anatomic_outward_angle_deg": row.get("anatomic_outward_angle_deg"),
        }
        if mask_path is None:
            rows.append({**base, **{c: 0.0 for c in AXIS_COLS}})
            continue
        mask = load_binary_mask(mask_path)
        if mask is None:
            rows.append({**base, **{c: 0.0 for c in AXIS_COLS}})
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
            rows.append({**base, **{c: 0.0 for c in AXIS_COLS}})
            continue
        outer = load_binary_mask(outer_path) if outer_path else None
        ang = row.get("direction_outward_angle_deg")
        if ang is None or (isinstance(ang, float) and not pd.notna(ang)):
            ang = row.get("anatomic_outward_angle_deg")
        try:
            ang_f = float(ang) if ang is not None and pd.notna(ang) else None
        except Exception:
            ang_f = None
        try:
            feats = compute_wall_axis_features(mask, lumen, outer, outward_angle_deg=ang_f)
        except Exception:
            feats = {c: 0.0 for c in AXIS_COLS}
        n_ok += int(feats.get("wall_axis_valid", 0) > 0.5)
        rows.append({**base, **{c: feats.get(c, 0.0) for c in AXIS_COLS}})

    frame_df = pd.DataFrame(rows)
    if len(frame_df):
        scores = frame_df["wall_axis_depth_frac"].map(depth_frac_to_wall_score)
        bump = (frame_df["wall_axis_serosa_hit"] >= 0.5) & (
            frame_df["wall_axis_depth_frac"] >= 0.70
        )
        frame_df["wall_axis_score_soft"] = scores.where(~bump, float(SCORE_SEROSA))
    frame_df.to_csv(out / "frame_features_axis.csv", index=False)

    valid = frame_df[frame_df["wall_axis_valid"] > 0.5].copy()
    patient = aggregate_patient_features(valid if len(valid) else frame_df, AXIS_COLS)
    if len(patient):
        ps = patient["wall_axis_depth_frac"].map(depth_frac_to_wall_score)
        pb = (patient["wall_axis_serosa_hit"] >= 0.5) & (patient["wall_axis_depth_frac"] >= 0.70)
        patient["wall_axis_score_soft"] = ps.where(~pb, float(SCORE_SEROSA))
    patient.to_csv(out / "patient_features_axis_median.csv", index=False)

    meta = {
        "n_frames": int(len(frame_df)),
        "n_valid_frames": int(n_ok),
        "n_patients": int(len(patient)),
        "elapsed_sec": round(time.time() - t0, 2),
        "feature_cols": AXIS_COLS,
        "design": (
            "Breakthrough-axis 占壁厚 (ContactGeom deep_idx / penetrationAt); "
            "sector around direction_outward_angle or max-ratio ray; not histologic GT"
        ),
    }
    (out / "meta_axis.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
