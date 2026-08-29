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
from wall_invasion_readout import analyze_invasion
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
        assert float(np.percentile(jump, 90)) < 2.2, float(np.percentile(jump, 90))
        if len(solid) >= 12:
            d2 = np.linalg.norm(np.diff(np.diff(solid, axis=0), axis=0), axis=1)
            assert float(np.percentile(d2, 90)) < 0.28, float(np.percentile(d2, 90))
    musc = next((item for item in track.ribbons if item.get("id") == "muscularis"), None)
    if musc and len(musc.get("points") or []) >= 8:
        poly = np.asarray(musc["points"], dtype=np.float32)
        half = len(poly) // 2
        width = np.linalg.norm(poly[:half] - poly[half:][::-1][:half], axis=1)
        if len(width) >= 6:
            assert float(np.percentile(width, 90) / max(1.0, np.percentile(width, 10))) < 2.4
    assert any(len(item.get("points") or []) >= 6 for item in track.ribbons)
    pix = getattr(track, "pixels", None) or {}
    xs_p = np.asarray(pix.get("xs", []), dtype=np.int32)
    ys_p = np.asarray(pix.get("ys", []), dtype=np.int32)
    labs_p = np.asarray(pix.get("labels", []), dtype=np.int32)
    assert len(xs_p) >= 40, len(xs_p)
    # Labeled pixels must sit on the synthetic bright / dark / bright bands.
    for lab, lo, hi in ((0, 160.0, 255.0), (1, 20.0, 80.0), (2, 150.0, 255.0)):
        sel = labs_p == lab
        if int(sel.sum()) < 8:
            continue
        mean_g = float(gray[ys_p[sel], xs_p[sel]].mean())
        assert lo <= mean_g <= hi, (lab, mean_g)

    rng = np.random.RandomState(0)
    xs = np.linspace(20.0, 260.0, 90)
    wiggly = np.stack([xs, 80.0 + 2.2 * np.sin(xs / 9.0) + rng.normal(0.0, 1.6, size=len(xs))], axis=1)
    noisy = track_ordered_layers(
        gray, wiggly, lesion_mask,
        lumen_center=lumen.mean(axis=0),
        lesion_poly=lesion,
        dilate_px=5,
        fit_side="right",
    )
    wig_solid = np.asarray({item.id: item for item in noisy.boundaries}["inner"].solid_hi, dtype=np.float32)
    if len(wig_solid) >= 16:
        y = wig_solid[:, 1]
        kernel = np.ones(9, dtype=np.float32) / 9.0
        trend = np.convolve(y, kernel, mode="valid")
        resid = y[4:-4] - trend
        assert float(np.percentile(np.abs(resid), 90)) < 0.85, float(np.percentile(np.abs(resid), 90))
    assert "lost" not in {item.status for item in track.regions}
    inv = {item.id: item.verdict for item in track.invasion}
    assert set(inv) == {"mucosa", "muscularis", "serosa"}
    assert inv["muscularis"] in {"fused", "continuous"}, inv
    assert "interrupted" not in inv.values(), inv
    assert all(item.confidence <= 0.62 for item in track.invasion)

    # Protocol: one frame cannot confirm interrupt.
    one = analyze_invasion(
        inner_n=12, outer_n=12, path_meets_lesion=True, wrapped=False,
        wrap_steps=0, mid_gray=40.0, lesion_gray=38.0, outer_stop_gray=36.0,
        single_frame=True,
    )
    assert {item.id: item.verdict for item in one}["serosa"] == "suspected_interrupt"
    wrap = analyze_invasion(
        inner_n=12, outer_n=12, path_meets_lesion=True, wrapped=True,
        wrap_steps=12, mid_gray=80.0, lesion_gray=30.0, outer_stop_gray=90.0,
        single_frame=True,
    )
    assert {item.id: item.verdict for item in wrap}["serosa"] == "displaced"
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
