#!/usr/bin/env python3
"""Synthetic checks for four-interface wall tracking."""
from __future__ import annotations

import numpy as np

from render_wall_directional_interfaces import _track_interfaces


def main() -> None:
    rng = np.random.default_rng(40)
    station_count = 90
    normal_count = 49
    station_axis = np.arange(station_count, dtype=np.float32)
    shift = np.rint(2.0 * np.sin(station_axis / 17.0)).astype(np.int32)
    expected = np.stack([12 + shift, 20 + shift, 28 + shift, 36 + shift], axis=1)
    strip = np.full((station_count, normal_count), 55.0, dtype=np.float32)
    for station, (edge1, edge2, edge3, edge4) in enumerate(expected):
        strip[station, edge1:edge2] = 205.0
        strip[station, edge2:edge3] = 42.0
        strip[station, edge3:edge4] = 190.0
    strip += rng.normal(0.0, 3.0, strip.shape).astype(np.float32)
    result = _track_interfaces(strip, np.ones_like(strip, dtype=bool))
    error = np.abs(result["indices"].astype(np.int32) - expected)
    assert result["phase"] == 1
    assert float(np.median(error)) <= 1.0
    assert np.all(np.diff(result["indices"], axis=1) >= 3)
    print({
        "phase": "bright-dark-bright",
        "median_boundary_error_px": float(np.median(error)),
    })


if __name__ == "__main__":
    main()
