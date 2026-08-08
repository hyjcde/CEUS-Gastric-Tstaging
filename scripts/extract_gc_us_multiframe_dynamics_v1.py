#!/usr/bin/env python3
"""Multi-frame dynamics / consistency features for GC-US T-score.

From existing frame-level morph/margin/growth/wall CSVs, aggregate per patient:
  n_frames, median, max, std, iqr, max_minus_median, frac_high

Meeting / human-assist: multi-cut consistency matters more than single-frame peak.
Deepest-extremum alone was rejected for wall remain; here we keep **frac_high**
and **std** as consistency signals.

Writes:
  pipeline/data/gc_us_tscore_features_v1/dynamics/
    patient_features.csv
    meta.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FEAT = PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1"
OUT = FEAT / "dynamics"

# (subdir, valid_col, feature, high_threshold for frac_high)
SPECS = [
    ("morphology", "morph_valid", "morph_peak_sharpness_max", 0.35),
    ("morphology", "morph_valid", "morph_solidity", None),  # low solidity = irregular; use frac_low
    ("morphology", "morph_valid", "morph_nrl_roughness", 0.12),
    ("margin", "margin_valid", "margin_spic_robust", 0.35),
    ("margin", "margin_valid", "margin_shape_fd_high", 0.15),
    ("growth", "growth_valid", "bt_v2_max_outward_depth", 8.0),
    ("growth", "growth_valid", "growth_outward_protrusion_ratio", 0.25),
    ("wall_layer", "wall_valid", "wall_depth_frac_p90", 0.85),
    ("wall_layer", "wall_valid", "wall_serosa_interrupt", 0.22),
]

# wall v2 remain: high invasion when remain low → frac_low
WALL_V2_REMAIN = ("wall_layer", "frame_features_axis_v2.csv", "wall_v2_valid", "wall_v2_remain_px", 4.0)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    return ap.parse_args()


def agg_feature(df: pd.DataFrame, feat: str, high: float | None, low: float | None = None) -> pd.DataFrame:
    g = df.groupby("patient_id")[feat]
    out = pd.DataFrame(
        {
            "patient_id": g.median().index.astype(str),
            f"{feat}__med": g.median().values,
            f"{feat}__max": g.max().values,
            f"{feat}__std": g.std(ddof=0).fillna(0).values,
            f"{feat}__iqr": (g.quantile(0.75) - g.quantile(0.25)).values,
            f"{feat}__max_minus_med": (g.max() - g.median()).values,
            f"{feat}__n": g.size().values,
        }
    )
    if high is not None:
        frac = df.assign(_h=(df[feat] >= high).astype(float)).groupby("patient_id")["_h"].mean()
        out[f"{feat}__frac_high"] = out["patient_id"].map(frac).astype(float)
    if low is not None:
        frac = df.assign(_l=(df[feat] <= low).astype(float)).groupby("patient_id")["_l"].mean()
        out[f"{feat}__frac_low"] = out["patient_id"].map(frac).astype(float)
    return out


def load_frames(subdir: str, valid_col: str, csv_name: str = "frame_features.csv") -> pd.DataFrame | None:
    path = FEAT / subdir / csv_name
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df["patient_id"] = df["patient_id"].astype(str)
    if valid_col in df.columns:
        df = df[df[valid_col] > 0.5].copy()
    return df if len(df) else None


def main() -> None:
    args = parse_args()
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    pieces: list[pd.DataFrame] = []
    used = []
    for subdir, valid_col, feat, high in SPECS:
        df = load_frames(subdir, valid_col)
        if df is None or feat not in df.columns:
            continue
        low = 0.85 if feat == "morph_solidity" else None  # irregular if solidity low
        hi = None if feat == "morph_solidity" else high
        pieces.append(agg_feature(df, feat, hi, low))
        used.append({"subdir": subdir, "feature": feat, "high": high, "low": low})

    # wall v2 remain
    subdir, csv_name, valid_col, feat, low = WALL_V2_REMAIN
    df = load_frames(subdir, valid_col, csv_name)
    if df is not None and feat in df.columns:
        pieces.append(agg_feature(df, feat, high=None, low=low))
        used.append({"subdir": subdir, "feature": feat, "high": None, "low": low, "csv": csv_name})

    if not pieces:
        raise SystemExit("no frame features found")

    patient = pieces[0]
    for p in pieces[1:]:
        patient = patient.merge(p, on="patient_id", how="outer", suffixes=("", "_dup"))
        patient = patient[[c for c in patient.columns if not c.endswith("_dup")]]

    # global n_frames proxy: max of available n cols
    n_cols = [c for c in patient.columns if c.endswith("__n")]
    if n_cols:
        patient["dyn_n_frames"] = patient[n_cols].max(axis=1)
    # consistency score: mean frac_high across invasion-like cues
    frac_cols = [
        c
        for c in patient.columns
        if c.endswith("__frac_high")
        or c
        in (
            "morph_solidity__frac_low",
            "wall_v2_remain_px__frac_low",
        )
    ]
    if frac_cols:
        patient["dyn_invasion_agree"] = patient[frac_cols].mean(axis=1, skipna=True)

    patient.to_csv(out / "patient_features.csv", index=False)
    meta = {
        "n_patients": int(len(patient)),
        "n_feature_cols": int(len(patient.columns) - 1),
        "sources": used,
        "frac_cols_in_agree": frac_cols,
        "design": "multi-frame std/iqr/frac_high|low; dyn_invasion_agree = mean frac",
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
