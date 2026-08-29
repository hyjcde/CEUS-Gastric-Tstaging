#!/usr/bin/env python3
"""Synthetic checks for direction-aware joint wall-band tracking."""
from __future__ import annotations

import numpy as np

from render_wall_directional_joint_bands import _joint_track, _smooth_offsets


def main() -> None:
    rng = np.random.default_rng(29)
    station_count = 90
    normal_count = 37
    axis = np.arange(station_count, dtype=np.float32)
    shift = np.rint(2.0 * np.sin(axis / 18.0)).astype(np.int32)
    expected = np.stack([10 + shift, 18 + shift, 26 + shift], axis=1)
    strip = np.full((station_count, normal_count), 105.0, dtype=np.float32)
    strip += rng.normal(0.0, 5.0, strip.shape).astype(np.float32)
    for index, (dark1, bright, dark2) in enumerate(expected):
        strip[index, dark1 - 1 : dark1 + 2] = 42.0
        strip[index, bright - 1 : bright + 2] = 205.0
        strip[index, dark2 - 1 : dark2 + 2] = 55.0
    valid = np.ones_like(strip, dtype=bool)
    result = _joint_track(strip, valid)
    predicted = result["indices"].astype(np.int32)
    error = np.abs(predicted - expected)
    assert float(np.median(error)) <= 1.0
    assert np.all(predicted[:, 0] < predicted[:, 1])
    assert np.all(predicted[:, 1] < predicted[:, 2])

    smooth = _smooth_offsets(result["offsets"])
    assert float(np.max(np.abs(smooth - result["offsets"]))) <= 1.0001
    print({
        "median_index_error": float(np.median(error)),
        "max_display_shift_px": float(np.max(np.abs(smooth - result["offsets"]))),
    })


if __name__ == "__main__":
    main()
