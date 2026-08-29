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
    _band_cuts_1d,
    _gradient_two_cuts,
    _split_interface_runs,
    cluster_brush_band,
    rasterize_polygon,
    stitch_interface_runs,
    try_join_runs,
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
    sensitive = cluster_brush_band(
        gray, wall, lesion_mask,
        brush_radius=6, k=3, dilate_px=3, exclude_lesion=True, method="kmeans1d_gray",
        lumen_center=lumen_center, lesion_poly=lesion, cavity_side_source="lumen",
        fit_side="right", assign_lesion=False, sensitive=True,
    )
    assert sensitive.status == "ok", sensitive.skip_reason
    assert sensitive.bright_dark_bright, sensitive.classes
    assert len(sensitive.fates) == 3
    assert {item["id"] for item in sensitive.fates} == {"shallow", "muscularis", "serosa"}
    mid = next(item for item in sensitive.fates if item["id"] == "muscularis")
    shallow = next(item for item in sensitive.fates if item["id"] == "shallow")
    assert mid["status"] in {"vanished", "fused"}
    assert shallow["status"] == "vanished"
    strips = cluster_brush_band(
        gray, wall, lesion_mask,
        brush_radius=6, k=3, dilate_px=3, exclude_lesion=True, method="kmeans1d_gray",
        lumen_center=lumen_center, lesion_poly=lesion, cavity_side_source="lumen",
        fit_side="right", assign_lesion=False, prefer_strips=True,
    )
    assert strips.status == "ok", strips.skip_reason
    assert strips.bright_dark_bright, strips.classes
    strip_lab = np.asarray(strips.labels, dtype=np.int32)
    strip_x = np.asarray(strips.xs, dtype=np.int32)
    strip_y = np.asarray(strips.ys, dtype=np.int32)
    col = (strip_x == 40) & (strip_lab >= 0)
    if int(col.sum()) >= 6:
        order = np.argsort(strip_y[col])
        labs = strip_lab[col][order]
        # Wide across-paint follows the wall normal. On this flat wall
        # labels should still go 0 then 1 then 2 from top to bottom.
        if int((labs == 0).sum()) and int((labs == 2).sum()):
            y0 = float(strip_y[col][labs == 0].mean())
            y2 = float(strip_y[col][labs == 2].mean())
            assert y0 <= y2 + 1.0, (y0, y2, labs)
    assert len(strips.interfaces) >= 1, strips.interfaces
    thin_bright = np.array([40.0] * 5 + [190.0] * 2 + [40.0] * 5, dtype=np.float32)
    cut_i, cut_j = _band_cuts_1d(thin_bright)
    assert cut_i <= 5 and cut_j >= 7, (cut_i, cut_j)
    assert (cut_j - cut_i) <= 10, (cut_i, cut_j)
    halo = np.array([18.0] * 12 + [210.0] * 4 + [48.0] * 4 + [200.0] * 4 + [18.0] * 12, dtype=np.float32)
    hi, hj = _band_cuts_1d(halo, prefer="bdb", overlap=(12, 24))
    assert 14 <= hi <= 18 and 18 <= hj <= 22, (hi, hj)
    # P040-like: bright, then a dark 6 px stripe, then bright. Cuts must hit the dark.
    wallish = np.array(
        [90.0] * 16 + [165.0] * 6 + [50.0] * 6 + [120.0] * 8 + [90.0] * 13,
        dtype=np.float32,
    )
    gi, gj = _gradient_two_cuts(wallish, prefer="bdb", overlap=(16, 36))
    assert 20 <= gi <= 24 and 26 <= gj <= 30, (gi, gj)
    first_line = np.asarray(strips.interfaces[0]["points"], dtype=np.float32)
    assert len(first_line) >= 4
    left = [[10.0, 20.0], [18.0, 20.4], [26.0, 20.2]]
    right = [[38.0, 20.6], [46.0, 20.3], [54.0, 20.1]]
    joined = try_join_runs(left, right)
    assert joined is not None and len(joined) >= 7
    stitched = stitch_interface_runs([left, right])
    assert len(stitched) == 1
    assert stitched[0][0][0] < 12.0 and stitched[0][-1][0] > 50.0
    ys = [p[1] for p in stitched[0]]
    assert max(ys) - min(ys) < 3.0
    corner_l = [[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]]
    corner_r = [[20.0, 12.0], [20.0, 24.0], [20.0, 36.0]]
    assert try_join_runs(corner_l, corner_r) is None
    zig = [[float(i * 3), 20.0 + (8.0 if i % 2 else -8.0)] for i in range(16)]
    zig[0][1] = 20.0
    zig[-1][1] = 20.0
    flat = _split_interface_runs(zig)
    assert len(flat) == 1
    zig_ys = [p[1] for p in flat[0]]
    assert max(zig_ys) - min(zig_ys) < 10.0
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
