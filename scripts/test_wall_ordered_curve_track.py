#!/usr/bin/env python3
"""Synthetic checks for ordered wall-curve tracking.

  python3 scripts/test_wall_ordered_curve_track.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from wall_lesion_aware_cluster import rasterize_polygon
from wall_ordered_curve_track import (  # noqa: E402
    pick_ordered_candidates,
    track_ordered_layers,
)


def make_bdb() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    height, width = 160, 280
    gray = np.full((height, width), 28.0, dtype=np.float32)
    wall_y = 80
    gray[wall_y - 7:wall_y - 3, :] = 210
    gray[wall_y - 3:wall_y + 2, :] = 46
    gray[wall_y + 2:wall_y + 6, :] = 198
    lesion = [[118, 70], [162, 70], [160, 104], [120, 104]]
    lesion_mask = rasterize_polygon(gray.shape, lesion)
    gray[lesion_mask > 0] = 22
    wall = np.array([[20.0, wall_y], [260.0, wall_y]], dtype=np.float32)
    lumen = np.array([[40.0, 18.0], [240.0, 18.0], [240.0, 48.0], [40.0, 48.0]], dtype=np.float32)
    return gray, wall, np.asarray(lesion, dtype=np.float32), lumen


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthetic test for ordered wall curves.")
    parser.parse_args()

    profile = np.array([40.0] * 8 + [200.0] * 4 + [50.0] * 5 + [190.0] * 4 + [40.0] * 8, dtype=np.float32)
    pick = pick_ordered_candidates(profile)
    assert pick["shallow"] is not None and pick["muscularis"] is not None and pick["serosa"] is not None
    assert pick["shallow"] < pick["muscularis"] < pick["serosa"]

    only_bright = np.array([30.0] * 12 + [200.0] * 5 + [30.0] * 12, dtype=np.float32)
    one = pick_ordered_candidates(only_bright)
    present = [key for key, idx in one.items() if idx is not None]
    assert len(present) <= 2, one

    gray, wall, lesion, lumen = make_bdb()
    lesion_mask = rasterize_polygon(gray.shape, lesion)
    track = track_ordered_layers(
        gray, wall, lesion_mask,
        lumen_center=lumen.mean(axis=0),
        lesion_poly=lesion,
        dilate_px=5,
        fit_side="right",
    )
    assert track.status == "ok", track.skip_reason
    by_id = {layer.id: layer for layer in track.layers}
    assert by_id["muscularis"].n_detected >= 8
    assert by_id["serosa"].n_detected >= 8
    if by_id["shallow"].n_mean is not None and by_id["serosa"].n_mean is not None:
        assert by_id["shallow"].n_mean < by_id["serosa"].n_mean
    # Solid curves stay out of the dilated lesion.
    blocked = lesion_mask
    for layer in track.layers:
        for x, y in layer.solid:
            xi, yi = int(round(x)), int(round(y))
            if 0 <= xi < blocked.shape[1] and 0 <= yi < blocked.shape[0]:
                assert blocked[yi, xi] == 0, (layer.id, x, y)
        # A dashed path may enter the lesion, but must not jump to the far flank.
        xs = [p[0] for p in layer.dashed]
        if xs:
            assert max(xs) < 200.0, (layer.id, xs[-1])
    print("wall_ordered_curve_track ok", {
        key: {"status": layer.status, "n": layer.n_detected, "gray": layer.gray_mean}
        for key, layer in by_id.items()
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
