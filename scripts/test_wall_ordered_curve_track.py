#!/usr/bin/env python3
"""Synthetic checks for two ordered wall interfaces.

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
from wall_ordered_curve_track import pick_interfaces, track_ordered_layers


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
    parser = argparse.ArgumentParser(description="Synthetic test for ordered wall interfaces.")
    parser.parse_args()

    profile = np.array([40.0] * 8 + [200.0] * 4 + [50.0] * 5 + [190.0] * 4 + [40.0] * 8, dtype=np.float32)
    b1, b2 = pick_interfaces(profile)
    assert b1 is not None and b2 is not None
    assert b1 < b2

    only_bright = np.array([30.0] * 12 + [200.0] * 5 + [30.0] * 12, dtype=np.float32)
    one = pick_interfaces(only_bright)
    present = [item for item in one if item is not None]
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
    by_b = {item.id: item for item in track.boundaries}
    assert by_b["inner"].n_detected >= 8
    assert by_b["outer"].n_detected >= 8
    if by_b["inner"].n_mean is not None and by_b["outer"].n_mean is not None:
        assert by_b["inner"].n_mean < by_b["outer"].n_mean
    solid = np.asarray(by_b["inner"].solid_hi, dtype=np.float32)
    if len(solid) >= 8:
        jump = np.sqrt(((solid[1:] - solid[:-1]) ** 2).sum(axis=1))
        # A natural wall line should not vibrate several pixels every step.
        assert float(np.percentile(jump, 90)) < 3.5, float(np.percentile(jump, 90))
    assert any(len(item.get("points") or []) >= 6 for item in track.ribbons)
    assert "lost" not in {item.status for item in track.regions}
    for item in track.boundaries:
        for x, y in item.solid_hi + item.solid_lo:
            xi, yi = int(round(x)), int(round(y))
            if 0 <= xi < lesion_mask.shape[1] and 0 <= yi < lesion_mask.shape[0]:
                assert lesion_mask[yi, xi] == 0, (item.id, x, y)
        xs = [p[0] for p in item.dashed]
        if xs:
            assert max(xs) < 200.0, (item.id, xs[-1])
    print("wall_ordered_curve_track ok", {
        "boundaries": {key: {"status": item.status, "n": item.n_detected} for key, item in by_b.items()},
        "regions": {item.id: item.status for item in track.regions},
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
