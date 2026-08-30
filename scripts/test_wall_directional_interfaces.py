#!/usr/bin/env python3
"""Synthetic checks for four-interface wall tracking."""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from render_wall_directional_interfaces import (  # noqa: E402
    OFFSETS,
    _analyze_full_trajectory,
    _build_clinical_reasoning,
    _curated_gap_station,
    _expand_p008_lesion,
    _layer_pixel_continuity,
    _offsets_to_indices,
    _paint_three_bands,
    _record_assisted_invasion,
    _snap_offsets_to_gradient,
    _station_inside_lesion,
    _track_interfaces,
    _track_interfaces_with_lesion,
    _usable_lumen_center,
    track_case,
)
from wall_ordered_curve_track import _smooth_wall_stations  # noqa: E402

ALLOWED_VERDICTS = {"continuous", "suspected_interrupt", "cannot_judge"}


def _assert_single_frame_labels(invasion: dict) -> None:
    assert set(invasion["verdicts"].values()) <= ALLOWED_VERDICTS
    assert invasion.get("single_frame") is True
    assert invasion.get("ct_stage") is None
    assert "cT" not in str(invasion["verdicts"])


def _paint_bdb_column(height: int, wall_y: int, outward_sign: int) -> np.ndarray:
    """Paint one column. outward_sign=+1 means serosa is toward +Y."""
    column = np.full(height, 35, dtype=np.uint8)
    for y in range(height):
        offset = (y - wall_y) * outward_sign
        if -12 <= offset < -6:
            column[y] = 205
        elif -6 <= offset < 2:
            column[y] = 42
        elif 2 <= offset < 8:
            column[y] = 190
    return column


def _synthetic_wall_pack(
    *,
    lumen_side: str = "above",
    curved: bool = False,
    occlude: bool = False,
    noise: float = 0.0,
) -> dict:
    height, width = 140, 240
    gray = np.full((height, width), 35, dtype=np.uint8)
    wall_y = 72
    outward = 1 if lumen_side == "above" else -1
    lumen_y = 22.0 if lumen_side == "above" else 118.0
    xs = np.arange(width, dtype=np.float32)
    if curved:
        wall_ys = wall_y + 11.0 * np.sin(xs / 26.0)
    else:
        wall_ys = np.full(width, float(wall_y), dtype=np.float32)
    for x in range(width):
        gray[:, x] = _paint_bdb_column(height, int(round(float(wall_ys[x]))), outward)
    if occlude:
        cv2.ellipse(gray, (width // 2, int(wall_y)), (28, 16), 0, 0, 360, 16, -1)
    if noise:
        rng = np.random.default_rng(7)
        gray = np.clip(
            gray.astype(np.float32) + rng.normal(0.0, noise, gray.shape),
            0,
            255,
        ).astype(np.uint8)
    crop = np.dstack([gray, gray, gray])
    sample_x = np.linspace(16.0, width - 16.0, 48)
    wall = np.stack(
        [sample_x, np.interp(sample_x, xs, wall_ys)],
        axis=1,
    ).astype(np.float32)
    lesion_mask = np.zeros((height, width), dtype=np.uint8)
    lesion_poly = np.zeros((0, 2), dtype=np.float32)
    if occlude:
        cv2.ellipse(lesion_mask, (width // 2, int(wall_y)), (28, 16), 0, 0, 360, 255, -1)
        contours, _ = cv2.findContours(lesion_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if contours:
            lesion_poly = max(contours, key=cv2.contourArea)[:, 0, :].astype(np.float32)
    return {
        "crop": crop,
        "crop_mask": lesion_mask,
        "wall_crop": wall,
        "lesion_poly": lesion_poly,
        "crop_lumen": np.asarray([width / 2.0, lumen_y], dtype=np.float32),
        "cavity": "lumen_center",
        "mask_source": "synthetic",
        "meta": {"case_id": "SYN-WALL", "display_id": "SYN"},
    }


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

    perturbed = result["offsets"] + np.asarray([2.0, 1.5, -1.5, 2.0], dtype=np.float32)
    snapped = _snap_offsets_to_gradient(perturbed, result["gradient"], result["signed"])
    true_offsets = OFFSETS[expected]
    snap_error = float(np.median(np.abs(snapped - true_offsets)))
    raw_error = float(np.median(np.abs(perturbed - true_offsets)))
    assert snap_error < raw_error
    assert np.all(np.diff(snapped, axis=1) >= 2.0 - 1.0e-3)
    assert np.all(np.diff(snapped, axis=1) <= 10.0 + 1.0e-3)

    occluded = strip.copy()
    occluded[36:58] = 80.0
    inside = np.zeros(station_count, dtype=bool)
    inside[36:58] = True
    gapped = _track_interfaces_with_lesion(
        occluded,
        np.ones_like(occluded, dtype=bool),
        inside,
    )
    assert bool(gapped["extrapolated"][36:58].all())
    assert np.all(np.diff(gapped["offsets"], axis=1) >= 2.0 - 1.0e-3)
    assert float(np.median(gapped["confidence"][36:58])) < float(
        np.median(gapped["confidence"][:30])
    )

    mask = np.zeros((60, 80), dtype=np.uint8)
    cv2.ellipse(mask, (40, 28), (8, 4), 0, 0, 360, 255, -1)
    synthetic_crop = np.full((60, 80, 3), 180, dtype=np.uint8)
    cv2.ellipse(synthetic_crop, (40, 28), (12, 7), 0, 0, 360, (45, 45, 45), -1)

    class EmptySegmenter:
        kind = "empty_test_segmenter"

        @staticmethod
        def segment_crop(crop: np.ndarray) -> np.ndarray:
            return np.zeros(crop.shape[:2], dtype=np.uint8)

    expanded = _expand_p008_lesion({
        "crop": synthetic_crop,
        "crop_mask": mask,
        "lesion_poly": np.zeros((0, 2), dtype=np.float32),
    }, EmptySegmenter())
    before_xy = np.asarray(np.where(mask > 0))[::-1].mean(axis=1)
    after_xy = np.asarray(np.where(expanded["crop_mask"] > 0))[::-1].mean(axis=1)
    assert expanded["lesion_adjustment"]["area_after"] > expanded["lesion_adjustment"]["area_before"]
    assert float(np.linalg.norm(before_xy - after_xy)) < 0.5
    assert expanded["lesion_adjustment"]["method"] == "centered expanded-box re-segmentation"

    # Record-assisted ticks stay available as review contrast only.
    p019 = _record_assisted_invasion("CASE-019", "not_established")
    assert set(p019["verdicts"].values()) == {"cannot_judge"}
    assert p019["breakthrough_layer"] is None
    p040 = _record_assisted_invasion("CASE-040", "contact")
    assert p040["verdicts"]["serosa"] == "suspected_interrupt"
    assert p040["breakthrough_layer"] == "serosa"
    p008 = _record_assisted_invasion("CASE-008", "contact")
    assert p008["verdicts"] == {
        "mucosa": "suspected_interrupt",
        "muscularis": "continuous",
        "serosa": "continuous",
    }
    assert p008["breakthrough_layer"] == "mucosa"
    assert str(p008["doctor_impression"]).startswith("T1")

    p076_paths = np.zeros((4, 4, 2), dtype=np.float32)
    p076_paths[:, 0, :] = np.asarray([
        [20, 100],
        [70, 130],
        [101, 151],
        [240, 90],
    ], dtype=np.float32)
    assert _curated_gap_station("CASE-076", "mucosa", p076_paths) == 3

    pixel_track = {
        "boundary_responses": np.column_stack([
            np.r_[np.full(24, 20.0), np.full(16, 2.0)],
            np.full(40, 12.0),
            np.full(40, 12.0),
            np.full(40, 12.0),
        ]).astype(np.float32),
        "indices": np.tile(np.asarray([10, 16, 22, 28]), (40, 1)),
        "clear_side": "start",
        "inside_lesion": np.r_[np.zeros(24, dtype=bool), np.ones(16, dtype=bool)],
    }
    pixel_evidence = _layer_pixel_continuity(pixel_track, "mucosa", 22)
    assert pixel_evidence["status"] == "disrupted"
    assert pixel_evidence["break_index"] is not None

    paint_paths = np.zeros((20, 4, 2), dtype=np.float32)
    paint_paths[:, :, 0] = np.arange(5, 25, dtype=np.float32)[:, None]
    paint_paths[:, :, 1] = np.asarray([3, 6, 9, 12], dtype=np.float32)[None, :]
    paint_reliable = np.zeros(20, dtype=bool)
    paint_reliable[:6] = True
    painted = _paint_three_bands(np.zeros((16, 30, 3), dtype=np.uint8), paint_paths, paint_reliable)
    assert int(painted[4, 23].sum()) > 0
    assert int(painted[4, 7].sum()) > int(painted[4, 23].sum())

    full_paths = np.zeros((40, 4, 2), dtype=np.float32)
    full_paths[:, :, 0] = np.arange(40, dtype=np.float32)[:, None]
    full_paths[:, :, 1] = np.asarray([18, 21, 24, 27], dtype=np.float32)[None, :]
    lesion = np.zeros((50, 50), dtype=np.uint8)
    cv2.circle(lesion, (36, 24), 5, 255, -1)
    confidence = np.full(40, 12.0, dtype=np.float32)
    confidence[18:24] = 1.0
    full = _analyze_full_trajectory(
        {"crop_mask": lesion},
        {
            "paths": full_paths,
            "indices": np.tile(np.asarray([10, 18, 26, 34]), (40, 1)),
            "confidence": confidence,
            "boundary_responses": np.full((40, 4), 12.0, dtype=np.float32),
            "threshold": 5.0,
            "inside_lesion": np.r_[np.zeros(30, dtype=bool), np.ones(10, dtype=bool)],
        },
    )
    assert full["full_station_count"] == 40
    assert len(full["paths"]) == 40
    assert full["reliable_station_count"] < 40
    assert full["uncertain_runs"]
    assert not full["reliable_mask"][30:].any()
    assert np.all(full["boundary_reliable_counts"] >= 0)
    full["clear_side"] = "start"
    full["invasion"] = _build_clinical_reasoning("CASE-040", full)
    _assert_single_frame_labels(full["invasion"])
    assert "serosa" not in full["invasion"]["disappearance_indices"]
    assert full["invasion"]["record_verdicts"]["serosa"] == "suspected_interrupt"
    assert "serosa" in full["invasion"]["record_contrast_only_layers"]

    disrupted_track = dict(full)
    disrupted_track["boundary_responses"] = np.column_stack([
        np.r_[np.full(24, 20.0), np.full(16, 2.0)],
        np.full(40, 12.0),
        np.full(40, 12.0),
        np.full(40, 12.0),
    ]).astype(np.float32)
    disrupted_track["inside_lesion"] = np.r_[np.zeros(24, dtype=bool), np.ones(16, dtype=bool)]
    disrupted_track["extrapolated"] = np.zeros(40, dtype=bool)
    disrupted_track["relation"] = "contact"
    disrupted_track["contact_index"] = 30
    disrupted_track["contact_distance_px"] = 0.4
    disrupted_track["reliable_mask"] = np.ones(40, dtype=bool)
    disrupted_invasion = _build_clinical_reasoning("CASE-040", disrupted_track)
    _assert_single_frame_labels(disrupted_invasion)
    assert disrupted_invasion["verdicts"]["mucosa"] == "suspected_interrupt"
    assert disrupted_invasion["layer_pixel_evidence"]["mucosa"]["status"] == "disrupted"

    gated = dict(disrupted_track)
    gated["reliable_mask"] = np.r_[np.ones(24, dtype=bool), np.zeros(16, dtype=bool)]
    gated_invasion = _build_clinical_reasoning("CASE-019", gated)
    _assert_single_frame_labels(gated_invasion)
    assert gated_invasion["verdicts"]["mucosa"] == "cannot_judge"
    assert gated_invasion["layer_pixel_evidence"]["mucosa"]["status"] == "disrupted"

    heading = np.stack(
        [np.linspace(20.0, 200.0, 36), np.full(36, 80.0)],
        axis=1,
    ).astype(np.float32)
    _, n_above = _smooth_wall_stations(
        heading, np.asarray([110.0, 24.0], dtype=np.float32), None, None,
    )
    _, n_below = _smooth_wall_stations(
        heading, np.asarray([110.0, 140.0], dtype=np.float32), None, None,
    )
    assert float(n_above[:, 1].mean()) > 0.0
    assert float(n_below[:, 1].mean()) < 0.0

    bbox_pack = {
        "crop_lumen": np.asarray([40.0, 30.0], dtype=np.float32),
        "cavity": "lumen_bbox",
        "meta": {"case_id": "CASE-008"},
    }
    lumen, lumen_source = _usable_lumen_center(bbox_pack)
    assert lumen is None
    assert lumen_source == "unusable_image_window"
    real_lumen, real_source = _usable_lumen_center({
        "crop_lumen": np.asarray([40.0, 18.0], dtype=np.float32),
        "cavity": "lumen_center",
        "meta": {"case_id": "SYN-WALL"},
    })
    assert real_lumen is not None
    assert real_source == "lumen_center"

    above = _synthetic_wall_pack(lumen_side="above", noise=2.0)
    below = _synthetic_wall_pack(lumen_side="below", noise=2.0)
    tracked_above = track_case(above)
    tracked_below = track_case(below)
    assert tracked_above["cavity_side_source"] == "lumen_center"
    assert tracked_below["cavity_side_source"] == "lumen_center"
    assert float(tracked_above["normals"][:, 1].mean()) > 0.0
    assert float(tracked_below["normals"][:, 1].mean()) < 0.0
    assert np.all(np.diff(tracked_above["smooth_offsets"], axis=1) >= 2.0 - 1.0e-3)
    assert np.all(np.diff(tracked_below["smooth_offsets"], axis=1) >= 2.0 - 1.0e-3)
    above["invasion"] = _build_clinical_reasoning("SYN-WALL", tracked_above)
    _assert_single_frame_labels(above["invasion"])

    curved = _synthetic_wall_pack(lumen_side="above", curved=True, noise=2.0)
    tracked_curve = track_case(curved)
    assert np.all(np.diff(tracked_curve["smooth_offsets"], axis=1) >= 2.0 - 1.0e-3)
    jumps = np.abs(np.diff(tracked_curve["smooth_offsets"], axis=0)).max(axis=1)
    assert float(np.percentile(jumps, 90)) <= 2.5

    occluded_pack = _synthetic_wall_pack(lumen_side="above", occlude=True, noise=2.0)
    tracked_lesion = track_case(occluded_pack)
    inside_mask = _station_inside_lesion(occluded_pack, tracked_lesion["stations"])
    assert int(inside_mask.sum()) >= 4
    assert bool((~tracked_lesion["reliable_mask"][inside_mask]).all())
    tracked_lesion["invasion"] = _build_clinical_reasoning("SYN-WALL", tracked_lesion)
    _assert_single_frame_labels(tracked_lesion["invasion"])
    snap_idx = _offsets_to_indices(tracked_above["offsets"])
    assert snap_idx.shape[1] == 4

    print({
        "phase": "bright-dark-bright",
        "median_boundary_error_px": float(np.median(error)),
        "snap_error_px": snap_error,
        "lesion_center_shift_px": float(np.linalg.norm(before_xy - after_xy)),
        "full_trajectory_stations": full["full_station_count"],
        "reliable_trajectory_stations": full["reliable_station_count"],
        "lumen_normal_above": float(n_above[:, 1].mean()),
        "lumen_normal_below": float(n_below[:, 1].mean()),
        "lesion_dashed_stations": int((~tracked_lesion["reliable_mask"]).sum()),
    })


if __name__ == "__main__":
    main()
