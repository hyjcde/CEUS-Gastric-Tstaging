#!/usr/bin/env python3
"""Synthetic check: excluding a dark mass should recover bright-dark-bright.

  python3 scripts/test_wall_lesion_aware_cluster.py --help
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from wall_lesion_aware_cluster import (  # noqa: E402
    CLUSTER_METHODS,
    INSUFFICIENT,
    cluster_brush_band,
    rasterize_polygon,
)


def make_wall_image() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    height, width = 160, 280
    gray = np.full((height, width), 30.0, dtype=np.float32)
    wall_y = 80
    # Three bands fill a radius-6 brush: bright, dark, bright.
    gray[wall_y - 6:wall_y - 2, :] = 210
    gray[wall_y - 2:wall_y + 2, :] = 48
    gray[wall_y + 2:wall_y + 6, :] = 200
    # Dark lesion replaces the mid-band only in the center.
    lesion = [[118, 74], [162, 74], [160, 100], [120, 100]]
    lesion_mask = rasterize_polygon(gray.shape, lesion)
    gray[lesion_mask > 0] = 20
    wall = np.array([[20, wall_y], [260, wall_y]], dtype=np.float32)
    lumen = np.array([[40, 20], [240, 20], [240, 50], [40, 50]], dtype=np.float32)
    return gray, wall, np.asarray(lesion, dtype=np.float32), lumen


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthetic test for lesion-aware wall clustering.")
    parser.parse_args()
    gray, wall, lesion, lumen = make_wall_image()
    lesion_mask = rasterize_polygon(gray.shape, lesion)
    lumen_center = lumen.mean(axis=0)
    full = cluster_brush_band(
        gray, wall, lesion_mask,
        brush_radius=6, k=3, exclude_lesion=False,
        lumen_center=lumen_center, lesion_poly=lesion, cavity_side_source="lumen",
    )
    excl = cluster_brush_band(
        gray, wall, lesion_mask,
        brush_radius=6, k=3, dilate_px=3, exclude_lesion=True,
        lumen_center=lumen_center, lesion_poly=lesion, cavity_side_source="lumen",
    )
    assert full.status == "ok", full.skip_reason
    assert excl.status == "ok", excl.skip_reason
    assert excl.n_valid < full.n_valid, (excl.n_valid, full.n_valid)
    assert any(seg["side"] == "left" for seg in excl.flanks)
    assert any(seg["side"] == "right" for seg in excl.flanks)
    full_dark = min(item["mean_gray"] for item in full.classes)
    excl_dark = min(item["mean_gray"] for item in excl.classes)
    assert full_dark < excl_dark - 2, (full.classes, excl.classes)
    if not excl.bright_dark_bright:
        print("warn: exclude did not form bright-dark-bright", excl.classes)
    short_wall = np.array([[130.0, 80.0], [150.0, 80.0]], dtype=np.float32)
    short = cluster_brush_band(
        gray, short_wall, lesion_mask,
        brush_radius=6, k=3, exclude_lesion=True,
        lumen_center=lumen_center, lesion_poly=lesion,
    )
    assert short.status == INSUFFICIENT
    method_hits = {}
    for method in CLUSTER_METHODS:
        arm = cluster_brush_band(
            gray, wall, lesion_mask,
            brush_radius=6, k=3, dilate_px=3, exclude_lesion=True, method=method,
            lumen_center=lumen_center, lesion_poly=lesion, cavity_side_source="lumen",
        )
        method_hits[method] = arm.bright_dark_bright
        assert arm.status == "ok", (method, arm.skip_reason)
    right = cluster_brush_band(
        gray, wall, lesion_mask,
        brush_radius=6, k=3, dilate_px=3, exclude_lesion=True, method="kmeans1d_gray",
        lumen_center=lumen_center, lesion_poly=lesion, cavity_side_source="lumen",
        fit_side="right", assign_lesion=False,
    )
    assert right.status == "ok", right.skip_reason
    labels = np.asarray(right.labels, dtype=np.int32)
    xs = np.asarray(right.xs, dtype=np.int32)
    ys = np.asarray(right.ys, dtype=np.int32)
    lesion_pix = lesion_mask[ys, xs] > 0
    if lesion_pix.any():
        assert int((labels[lesion_pix] >= 0).sum()) == 0
    assert int((labels >= 0).sum()) >= 40
    # Spatial-only 1D may slice equally and still miss the gray pattern.
    assert method_hits["kmeans"] and method_hits["gmm"] and method_hits["fcm"], method_hits
    print("wall_lesion_aware_cluster ok", {
        "full_bdb": full.bright_dark_bright,
        "exclude_bdb": excl.bright_dark_bright,
        "full_n": full.n_valid,
        "exclude_n": excl.n_valid,
        "exclude_pattern": excl.pattern,
        "methods_bdb": method_hits,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
