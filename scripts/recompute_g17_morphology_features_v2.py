#!/usr/bin/env python3
"""Recompute the G17 morphology triad with scale-normalized peak sharpness.

The workstation implementation is copied into ``scripts/gc_us_contour_features.py``.
This script keeps the previous feature pack intact and writes a versioned v2
feature table with:

* scale-normalized peak sharpness on the NRL contour signature;
* solidity from the lesion mask and convex hull;
* the existing image-backed robust spiculation index;
* peak stability across several circular smoothing windows.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from tqdm import tqdm

from gc_us_contour_features import (
    DEFAULT_ANATOMIC_DIR,
    DEFAULT_FRAME_CSVS,
    build_mask_hash_index,
    compute_robust_margin_features,
    find_substantial_peaks,
    largest_contour,
    load_binary_mask,
    moving_average_circular,
    nrl_signature,
    resolve_image_path,
    resolve_mask_path,
    resample_closed_contour,
)


FEATURES = (
    "g17_peak_sharpness_nrl_max",
    "g17_peak_sharpness_nrl_median",
    "g17_peak_stability",
    "g17_solidity",
    "g17_spiculation_robust",
)
TRIAD = ("g17_peak_sharpness_nrl_max", "g17_solidity", "g17_spiculation_robust")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anatomic-dir", type=Path, default=DEFAULT_ANATOMIC_DIR)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--existing-feature-pack",
        type=Path,
        default=None,
        help="Optional patient feature pack providing the existing image-backed spiculation feature.",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--num-points", type=int, default=256)
    return parser.parse_args()


def load_frames(anatomic_dir: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for name in DEFAULT_FRAME_CSVS:
        path = anatomic_dir / name
        if path.exists():
            frame = pd.read_csv(path)
            frame["split_file"] = name
            frames.append(frame)
    if not frames:
        raise FileNotFoundError(f"No frame CSVs under {anatomic_dir}")
    return pd.concat(frames, ignore_index=True)


def normalized_peak_metrics(mask: np.ndarray, num_points: int) -> dict[str, float]:
    contour = largest_contour(mask)
    if contour is None:
        return {
            "g17_peak_sharpness_nrl_max": 0.0,
            "g17_peak_sharpness_nrl_median": 0.0,
            "g17_peak_stability": 0.0,
            "g17_solidity": 0.0,
        }
    contour = resample_closed_contour(contour, num_points)
    raw_distance, _, _ = nrl_signature(contour)
    peak_values: list[float] = []
    peak_counts: list[int] = []
    for window in (7, 11, 15):
        smoothed = moving_average_circular(raw_distance, window)
        nrl = smoothed / max(float(smoothed.max()), 1e-6)
        peaks = find_substantial_peaks(
            nrl,
            min_rel_height=0.08,
            min_sep=max(6, num_points // 32),
        )
        peak_values.append(max((float(item["sharpness"]) for item in peaks), default=0.0))
        peak_counts.append(len(peaks))
    contour_i = np.round(contour).astype(np.int32)
    area = float(cv2.contourArea(contour_i))
    hull = cv2.convexHull(contour_i)
    hull_area = float(cv2.contourArea(hull))
    median_peak = float(np.median(peak_values))
    mad = float(np.median(np.abs(np.asarray(peak_values) - median_peak)))
    stability = float(np.clip(1.0 - mad / max(abs(median_peak), 1e-6), 0.0, 1.0))
    return {
        "g17_peak_sharpness_nrl_max": float(max(peak_values)),
        "g17_peak_sharpness_nrl_median": median_peak,
        "g17_peak_stability": stability,
        "g17_solidity": float(area / max(hull_area, 1e-6)),
    }


def numeric_spearman(frame: pd.DataFrame, feature: str) -> dict[str, Any]:
    valid = frame[[feature, "label"]].dropna()
    if len(valid) < 10 or valid[feature].nunique() < 2:
        return {"feature": feature, "n": int(len(valid)), "rho": None, "p": None}
    result = spearmanr(valid[feature], valid["label"])
    return {
        "feature": feature,
        "n": int(len(valid)),
        "rho": float(result.statistic),
        "p": float(result.pvalue),
    }


def aggregate_patient(frame: pd.DataFrame) -> pd.DataFrame:
    usable = frame[frame["feature_valid"] > 0].copy()
    if usable.empty:
        return pd.DataFrame(columns=["patient_id", "label", *FEATURES])
    agg = usable.groupby("patient_id", as_index=False).agg(
        label=("label", "first"),
        **{feature: (feature, "median") for feature in FEATURES},
    )
    return agg


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = load_frames(args.anatomic_dir)
    if args.limit > 0:
        frames = frames.head(args.limit).copy()
    existing_spiculation: dict[str, float] = {}
    if args.existing_feature_pack is not None:
        pack = pd.read_csv(args.existing_feature_pack)
        if {"patient_id", "margin_spic_robust"}.issubset(pack.columns):
            valid_pack = pack[["patient_id", "margin_spic_robust"]].dropna()
            existing_spiculation = (
                valid_pack.assign(patient_id=valid_pack["patient_id"].astype(str))
                .groupby("patient_id")["margin_spic_robust"]
                .median()
                .to_dict()
            )
    hash_index = build_mask_hash_index()
    rows: list[dict[str, Any]] = []
    for _, row in tqdm(frames.iterrows(), total=len(frames), desc="G17-v2"):
        mask_path = resolve_mask_path(str(row.get("lesion_pred_mask_path", "")), hash_index)
        base = {
            "patient_id": str(row.get("patient_id", "")),
            "label": row.get("label"),
            "source": row.get("source"),
            "split": row.get("split"),
            "split_file": row.get("split_file"),
            "image_path": row.get("image_path"),
            "mask_resolved": int(mask_path is not None),
            "feature_valid": 0.0,
        }
        values = {feature: 0.0 for feature in FEATURES}
        if mask_path is not None:
            mask = load_binary_mask(mask_path)
            if mask is not None:
                values.update(normalized_peak_metrics(mask, args.num_points))
                patient_id = str(row.get("patient_id", ""))
                if patient_id in existing_spiculation:
                    values["g17_spiculation_robust"] = float(existing_spiculation[patient_id])
                else:
                    image_path = resolve_image_path(row.get("image_path"))
                    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR) if image_path else None
                    if image is not None:
                        margin = compute_robust_margin_features(image, mask)
                        values["g17_spiculation_robust"] = float(margin.get("margin_spic_robust", 0.0))
                base["feature_valid"] = 1.0
        rows.append({**base, **values})

    frame = pd.DataFrame(rows)
    patient = aggregate_patient(frame)
    frame.to_csv(out_dir / "frame_features_v2.csv", index=False)
    patient.to_csv(out_dir / "patient_features_v2.csv", index=False)

    stats = [numeric_spearman(patient, feature) for feature in TRIAD]
    stage_medians = (
        patient.groupby("label")[list(TRIAD)].median().reset_index().rename(columns={"label": "stage"})
        if not patient.empty
        else pd.DataFrame()
    )
    stage_medians.to_csv(out_dir / "g17_stage_medians_v2.csv", index=False)
    pd.DataFrame(stats).to_csv(out_dir / "g17_spearman_v2.csv", index=False)
    pairwise: list[dict[str, Any]] = []
    for i, left in enumerate(TRIAD):
        for right in TRIAD[i + 1 :]:
            valid = patient[[left, right]].dropna()
            result = spearmanr(valid[left], valid[right]) if len(valid) >= 10 else None
            pairwise.append(
                {
                    "feature_a": left,
                    "feature_b": right,
                    "n": int(len(valid)),
                    "rho": float(result.statistic) if result is not None else None,
                    "p": float(result.pvalue) if result is not None else None,
                }
            )
    pd.DataFrame(pairwise).to_csv(out_dir / "g17_pairwise_spearman_v2.csv", index=False)
    meta = {
        "method": "scale-normalized NRL peak sharpness + mask solidity + existing image-backed robust spiculation",
        "num_points": args.num_points,
        "smoothing_windows": [7, 11, 15],
        "frame_count": int(len(frame)),
        "valid_frame_count": int(frame["feature_valid"].sum()),
        "patient_count": int(len(patient)),
        "features": list(FEATURES),
        "triad": list(TRIAD),
        "spiculation_source": (
            str(args.existing_feature_pack)
            if args.existing_feature_pack is not None
            else "recomputed from image and mask"
        ),
        "outputs": {
            "frame_features": str(out_dir / "frame_features_v2.csv"),
            "patient_features": str(out_dir / "patient_features_v2.csv"),
            "spearman": str(out_dir / "g17_spearman_v2.csv"),
            "stage_medians": str(out_dir / "g17_stage_medians_v2.csv"),
            "pairwise": str(out_dir / "g17_pairwise_spearman_v2.csv"),
        },
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
