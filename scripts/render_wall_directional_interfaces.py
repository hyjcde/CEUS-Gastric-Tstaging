#!/usr/bin/env python3
"""Track four wall interfaces and render the three intervening pixel bands.

This offline probe uses a clean P008 local-axis fallback because its stored
heading is a self-crossing scribble. Outputs require clinical review.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from render_wall_directional_joint_bands import (  # noqa: E402
    _rolling_median,
    _runs,
    _smooth_offsets,
)
from render_wall_layer_thin_bands import DEFAULT_FIXTURES, RoiSegmenter, load_meta  # noqa: E402
from render_wall_pixel_vs_dino_cluster import prepare_crop  # noqa: E402
from wall_ordered_curve_track import (  # noqa: E402
    _predict_band,
    _smooth_wall_stations,
    polygon_centroid,
)

CURATION = ROOT / "pipeline/data/wall_layer_fixtures/v1/curated_lines_v1.json"
DEFAULT_OUT = ROOT / "results/visualizations/error_cases/directional_interfaces"
OFFSETS = np.arange(-24, 25, dtype=np.float32)
BOUNDARY_COLORS = ("#fde047", "#38bdf8", "#f472b6", "#4ade80")
BAND_COLORS = (
    np.asarray((250, 204, 21), dtype=np.float32),
    np.asarray((56, 189, 248), dtype=np.float32),
    np.asarray((244, 114, 182), dtype=np.float32),
)
LAYER_LABELS = {
    "mucosa": "Mucosa",
    "muscularis": "Muscularis",
    "serosa": "Serosa",
}
LAYER_BOUNDARY_INDEX = {
    "mucosa": 0,
    "muscularis": 2,
    "serosa": 3,
}
LAYER_BAND_INDEX = {
    "mucosa": 0,
    "muscularis": 1,
    "serosa": 2,
}
VERDICT_LABELS = {
    "continuous": "continuous",
    "suspected_interrupt": "suspected interruption",
    "cannot_judge": "cannot judge",
}

plt.rcParams.update({
    "font.family": "Times New Roman",
    "font.size": 10,
    "axes.facecolor": "black",
    "figure.facecolor": "black",
    "savefig.facecolor": "black",
    "text.color": "white",
})


def _heading_metrics(points: np.ndarray) -> tuple[float, float]:
    steps = np.diff(points, axis=0)
    arc = float(np.linalg.norm(steps, axis=1).sum())
    chord = float(np.linalg.norm(points[-1] - points[0]))
    unit = steps / np.maximum(np.linalg.norm(steps, axis=1, keepdims=True), 1.0e-6)
    turns = np.degrees(np.arccos(np.clip((unit[:-1] * unit[1:]).sum(axis=1), -1.0, 1.0)))
    return arc / max(chord, 1.0), float(turns.max()) if len(turns) else 0.0


def _sample_strip(
    gray: np.ndarray,
    stations: np.ndarray,
    normals: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    map_x = stations[:, 0, None] + normals[:, 0, None] * OFFSETS[None, :]
    map_y = stations[:, 1, None] + normals[:, 1, None] * OFFSETS[None, :]
    strip = cv2.remap(
        gray,
        map_x.astype(np.float32),
        map_y.astype(np.float32),
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    valid = (
        (map_x >= 0)
        & (map_x <= gray.shape[1] - 1)
        & (map_y >= 0)
        & (map_y <= gray.shape[0] - 1)
    )
    return strip.astype(np.float32), map_x, map_y


def _usable_lumen_center(pack: dict) -> tuple[np.ndarray | None, str]:
    """Accept a lumen center only when it is anatomy, not an image-window box."""
    cavity = str(pack.get("cavity") or pack.get("meta", {}).get("cavity_side_source") or "")
    lumen = pack.get("crop_lumen")
    case_id = str(pack.get("meta", {}).get("case_id") or "").upper()
    if lumen is None:
        return None, "heuristic"
    lumen = np.asarray(lumen, dtype=np.float32).reshape(-1)
    if lumen.size < 2 or not np.isfinite(lumen).all():
        return None, "heuristic"
    if cavity == "lumen_bbox" or case_id == "CASE-008":
        return None, "unusable_image_window"
    return lumen[:2], "lumen_center"


def _outside_lesion_axis(
    pack: dict,
    wall: np.ndarray,
    lesion_center: np.ndarray | None,
    deepest: np.ndarray | None,
) -> np.ndarray:
    """Keep the main heading arc that stays outside the dilated lesion."""
    stations, _normals = _smooth_wall_stations(wall, None, lesion_center, deepest)
    mask = pack.get("crop_mask")
    if mask is None or not np.asarray(mask).any() or len(stations) < 8:
        return wall
    dilated = cv2.dilate(
        (np.asarray(mask) > 0).astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)),
    )
    height, width = dilated.shape
    keep = [
        point
        for point in stations
        if 0 <= int(round(float(point[1]))) < height
        and 0 <= int(round(float(point[0]))) < width
        and dilated[int(round(float(point[1]))), int(round(float(point[0])))] == 0
    ]
    if len(keep) < 8:
        return wall
    return np.asarray(keep, dtype=np.float32)


def _wall_axis(pack: dict) -> tuple[np.ndarray, np.ndarray, str, str]:
    lesion = np.asarray(pack.get("lesion_poly", []), dtype=np.float32).reshape(-1, 2)
    lesion_center = polygon_centroid(lesion)
    deepest = None
    if lesion_center is not None and len(lesion):
        deepest = lesion[int(np.argmax(np.linalg.norm(lesion - lesion_center, axis=1)))]
    wall = np.asarray(pack["wall_crop"], dtype=np.float32)
    lumen, lumen_source = _usable_lumen_center(pack)
    stations, normals = _smooth_wall_stations(wall, lumen, lesion_center, deepest)
    tortuosity, max_turn = _heading_metrics(stations)
    source = "stored heading"
    if tortuosity > 2.5 or max_turn > 60.0:
        fallback = _outside_lesion_axis(pack, wall, lesion_center, deepest)
        stations, normals = _smooth_wall_stations(
            fallback, lumen, lesion_center, deepest,
        )
        source = "outside-lesion heading fallback"
    return stations, normals, source, lumen_source


def _seeded_grabcut(roi: np.ndarray, seed: np.ndarray) -> np.ndarray:
    """Re-segment an expanded ROI while preserving the original lesion as hard foreground."""
    labels = np.full(seed.shape, cv2.GC_PR_BGD, dtype=np.uint8)
    labels[[0, -1], :] = cv2.GC_BGD
    labels[:, [0, -1]] = cv2.GC_BGD
    probable = cv2.dilate(
        seed.astype(np.uint8),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 11)),
    ) > 0
    labels[probable] = cv2.GC_PR_FGD
    labels[seed] = cv2.GC_FGD
    bg_model = np.zeros((1, 65), dtype=np.float64)
    fg_model = np.zeros((1, 65), dtype=np.float64)
    cv2.grabCut(
        roi,
        labels,
        None,
        bg_model,
        fg_model,
        6,
        cv2.GC_INIT_WITH_MASK,
    )
    return np.isin(labels, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8)


def _expand_p008_lesion(pack: dict, segmenter: RoiSegmenter) -> dict:
    """Expand a centered box around P008 and re-run pixel segmentation inside it."""
    original = (pack["crop_mask"] > 0).astype(np.uint8)
    ys, xs = np.where(original > 0)
    if not len(xs):
        return pack
    before_center = np.asarray((xs.mean(), ys.mean()), dtype=np.float32)
    original_box = (
        int(xs.min()),
        int(ys.min()),
        int(xs.max()) + 1,
        int(ys.max()) + 1,
    )
    lesion_w = original_box[2] - original_box[0]
    lesion_h = original_box[3] - original_box[1]
    roi_w = max(72, int(np.ceil(lesion_w * 2.4)))
    roi_h = max(48, int(np.ceil(lesion_h * 3.0)))
    crop_h, crop_w = original.shape
    x1 = max(0, int(round(before_center[0] - roi_w / 2)))
    y1 = max(0, int(round(before_center[1] - roi_h / 2)))
    x2 = min(crop_w, x1 + roi_w)
    y2 = min(crop_h, y1 + roi_h)
    x1 = max(0, x2 - roi_w)
    y1 = max(0, y2 - roi_h)
    expanded_box = (x1, y1, x2, y2)
    roi = pack["crop"][y1:y2, x1:x2]
    seed = original[y1:y2, x1:x2] > 0

    model_mask = (segmenter.segment_crop(roi) > 0).astype(np.uint8)
    model_overlap = int((model_mask > 0)[seed].sum()) if model_mask.size else 0
    model_area = int(model_mask.sum())
    minimum_overlap = max(20, int(original.sum() * 0.20))
    if model_area > int(original.sum() * 1.05) and model_overlap >= minimum_overlap:
        resegmented = model_mask
        backend = f"{segmenter.kind} expanded-ROI re-segmentation"
    else:
        resegmented = _seeded_grabcut(roi, seed)
        backend = "seeded GrabCut expanded-ROI fallback"

    full = np.zeros_like(original)
    full[y1:y2, x1:x2] = resegmented
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(full, connectivity=8)
    if n_labels <= 1:
        return pack
    overlaps = [
        int(((labels == index) & (original > 0)).sum())
        for index in range(1, n_labels)
    ]
    selected = 1 + int(np.argmax(overlaps))
    selected_mask = np.where(labels == selected, 255, 0).astype(np.uint8)
    contours, _ = cv2.findContours(
        selected_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_NONE,
    )
    if not contours:
        return pack
    contour = max(contours, key=cv2.contourArea)
    after_y, after_x = np.where(selected_mask > 0)
    after_center = np.asarray((after_x.mean(), after_y.mean()), dtype=np.float32)
    adjusted = dict(pack)
    adjusted["crop_mask"] = selected_mask
    adjusted["lesion_poly"] = contour[:, 0, :].astype(np.float32)
    adjusted["mask_source"] = backend
    adjusted["lesion_adjustment"] = {
        "method": "centered expanded-box re-segmentation",
        "backend": backend,
        "original_box_xyxy": list(original_box),
        "expanded_box_xyxy": list(expanded_box),
        "box_width_scale": float((x2 - x1) / max(1, lesion_w)),
        "box_height_scale": float((y2 - y1) / max(1, lesion_h)),
        "area_before": int(original.sum()),
        "area_after": int((selected_mask > 0).sum()),
        "center_shift_px": float(np.linalg.norm(before_center - after_center)),
    }
    return adjusted


def _record_assisted_invasion(case_id: str, relation: str) -> dict:
    curation = json.loads(CURATION.read_text(encoding="utf-8"))
    if case_id not in curation.get("cases", {}):
        empty = {layer_id: "cannot_judge" for layer_id in LAYER_LABELS}
        return {
            "verdicts": dict(empty),
            "record_verdicts": dict(empty),
            "breakthrough_layer": None,
            "single_frame": True,
            "source": "no stored layer ticks",
            "doctor_impression": None,
        }
    case_record = curation["cases"][case_id]
    layers = case_record["layers"]
    verdicts: dict[str, str] = {}
    for layer_id in ("mucosa", "muscularis", "serosa"):
        raw = str(layers[layer_id]["verdict"])
        verdicts[layer_id] = "suspected_interrupt" if raw == "interrupted" else raw
    record_verdicts = dict(verdicts)
    if relation == "not_established":
        verdicts = {
            "mucosa": "cannot_judge",
            "muscularis": "cannot_judge",
            "serosa": "cannot_judge",
        }
    suspected = [
        layer_id for layer_id, verdict in verdicts.items()
        if verdict == "suspected_interrupt"
    ]
    breakthrough_layer = suspected[-1] if suspected else None
    return {
        "verdicts": verdicts,
        "record_verdicts": record_verdicts,
        "breakthrough_layer": breakthrough_layer,
        "single_frame": True,
        "source": "stored layer ticks plus current contact geometry",
        "doctor_impression": case_record.get("doctor_impression"),
    }


def _curated_gap_station(case_id: str, layer_id: str, paths: np.ndarray) -> int | None:
    curation = json.loads(CURATION.read_text(encoding="utf-8"))
    layer = curation["cases"][case_id]["layers"][layer_id]
    boundary = LAYER_BOUNDARY_INDEX[layer_id]
    if layer.get("analysis_focus"):
        focus = np.asarray(layer["analysis_focus"], dtype=np.float32)
        return int(np.argmin(np.linalg.norm(paths[:, boundary, :] - focus[None, :], axis=1)))
    segments = layer["segments"]
    if len(segments) < 2:
        return None
    left = np.asarray(segments[0][-1], dtype=np.float32)
    right = np.asarray(segments[1][0], dtype=np.float32)
    gap = 0.5 * (left + right)
    return int(np.argmin(np.linalg.norm(paths[:, boundary, :] - gap[None, :], axis=1)))


def _layer_pixel_continuity(
    track: dict,
    layer_id: str,
    seed: int,
) -> dict:
    """Compare a layer's normal-side gradient with its lesion-side continuation."""
    boundary = LAYER_BOUNDARY_INDEX[layer_id]
    response = _rolling_median(
        np.asarray(track["boundary_responses"][:, boundary], dtype=np.float32),
        radius=2,
    )
    span = max(6, len(response) // 5)
    reference = response[:span] if track["clear_side"] == "start" else response[-span:]
    reference_strength = float(np.median(reference))
    search_span = max(14, len(response) // 7)
    if track["clear_side"] == "start":
        search_start = max(0, seed - 3)
        search_stop = min(len(response), seed + search_span)
        order = range(search_start, search_stop)
    else:
        search_start = max(0, seed - search_span)
        search_stop = min(len(response), seed + 4)
        order = range(search_stop - 1, search_start - 1, -1)
    low_threshold = max(2.5, reference_strength * 0.40)
    contact_or_inside = None
    if "inside_lesion" in track:
        contact_or_inside = np.asarray(track["inside_lesion"], dtype=bool)
    if "boundary_distance" in track:
        touching = np.asarray(track["boundary_distance"][:, boundary]) <= 1.0
        contact_or_inside = (
            touching if contact_or_inside is None else (contact_or_inside | touching)
        )
    break_index: int | None = None
    ordered = list(order)
    for cursor in range(max(0, len(ordered) - 2)):
        run = ordered[cursor:cursor + 3]
        if len(run) != 3 or not all(response[index] < low_threshold for index in run):
            continue
        if contact_or_inside is not None and not any(contact_or_inside[index] for index in run):
            continue
        break_index = int(run[0])
        break
    if break_index is None:
        local_start = max(0, seed - 3)
        local_stop = min(len(response), seed + 4)
        local_strength = float(np.median(response[local_start:local_stop]))
    else:
        local_start = max(0, break_index - 1)
        local_stop = min(len(response), break_index + 3)
        local_strength = float(np.median(response[local_start:local_stop]))
    ratio = local_strength / max(reference_strength, 1.0e-6)
    widths = np.diff(np.asarray(track["indices"], dtype=np.float32), axis=1)[
        :, LAYER_BAND_INDEX[layer_id]
    ]
    width_reference = widths[:span] if track["clear_side"] == "start" else widths[-span:]
    reference_width = float(np.median(width_reference))
    local_width = float(np.median(widths[local_start:local_stop]))
    width_ratio = local_width / max(reference_width, 1.0e-6)
    status = (
        "disrupted"
        if reference_strength >= 10.0 and break_index is not None and ratio < 0.5
        else "continuous"
        if reference_strength >= 10.0 and ratio >= 0.65
        else "unclear"
    )
    return {
        "status": status,
        "reference_strength": reference_strength,
        "local_strength": local_strength,
        "strength_ratio": ratio,
        "reference_width_px": reference_width,
        "local_width_px": local_width,
        "width_ratio": width_ratio,
        "seed_index": int(seed),
        "break_index": break_index,
        "threshold": low_threshold,
    }


def _layer_contact_intervals(track: dict, layer_id: str) -> list[tuple[int, int]]:
    boundary = LAYER_BOUNDARY_INDEX[layer_id]
    return _runs(np.asarray(track["boundary_distance"][:, boundary]) <= 1.0)


def _layer_contact_seed(track: dict, layer_id: str) -> int:
    intervals = _layer_contact_intervals(track, layer_id)
    if not intervals:
        boundary = LAYER_BOUNDARY_INDEX[layer_id]
        return int(np.argmin(track["boundary_distance"][:, boundary]))
    contact = int(track.get("contact_index", intervals[0][0]))
    containing = next(
        ((start, stop) for start, stop in intervals if start <= contact <= stop),
        None,
    )
    start, stop = containing if containing is not None else min(
        intervals,
        key=lambda item: min(abs(item[0] - contact), abs(item[1] - contact)),
    )
    return int(start if track["clear_side"] == "start" else stop)


def _build_clinical_reasoning(case_id: str, track: dict) -> dict:
    """Pixel-first layer readout. Stored ticks stay review-only contrast."""
    record = _record_assisted_invasion(case_id, track["relation"])
    reliable = np.asarray(track["reliable_mask"], dtype=bool)
    contact = int(track["contact_index"])
    span = max(4, len(reliable) // 5)
    reference_slice = slice(0, span) if track["clear_side"] == "start" else slice(-span, None)
    contact_slice = slice(max(0, contact - 3), min(len(reliable), contact + 4))
    reference_fraction = float(reliable[reference_slice].mean()) if len(reliable) else 0.0
    contact_fraction = float(reliable[contact_slice].mean()) if len(reliable) else 0.0
    reference_status = "established" if reference_fraction >= 0.5 else "limited"
    contact_visibility = (
        "visible"
        if contact_fraction >= 0.6
        else "partly_visible"
        if contact_fraction >= 0.25
        else "unseen"
    )
    analysis_gate = (
        track["relation"] == "not_established"
        or reference_status == "limited"
        or contact_visibility == "unseen"
    )
    candidate_disappearance_indices: dict[str, int] = {}
    layer_pixel_evidence: dict[str, dict] = {}
    layer_contact_intervals: dict[str, list[tuple[int, int]]] = {}
    for layer_id in LAYER_LABELS:
        layer_contact_intervals[layer_id] = _layer_contact_intervals(track, layer_id)
        seed = _layer_contact_seed(track, layer_id)
        pixel = _layer_pixel_continuity(track, layer_id, seed)
        if pixel["status"] == "disrupted":
            pixel["mechanism"] = "gradient_loss"
        elif pixel["width_ratio"] >= 1.5 or pixel["width_ratio"] <= 0.67:
            pixel["mechanism"] = "interface_replacement_or_width_distortion"
        elif pixel["status"] == "continuous":
            pixel["mechanism"] = "pixel_supported_continuous"
        else:
            pixel["mechanism"] = "insufficient_pixel_evidence"
        try:
            pixel["record_contrast_seed"] = _curated_gap_station(
                case_id, layer_id, track["paths"],
            )
        except (KeyError, TypeError, IndexError):
            pixel["record_contrast_seed"] = None
        layer_pixel_evidence[layer_id] = pixel
        if pixel["status"] == "disrupted" and pixel["break_index"] is not None:
            candidate_disappearance_indices[layer_id] = int(pixel["break_index"])

    verdicts = {layer_id: "cannot_judge" for layer_id in LAYER_LABELS}
    pixel_supported_layers = [
        layer_id
        for layer_id, evidence in layer_pixel_evidence.items()
        if evidence["status"] == "disrupted"
    ]
    if not analysis_gate:
        for layer_id, evidence in layer_pixel_evidence.items():
            if evidence["status"] == "disrupted":
                verdicts[layer_id] = "suspected_interrupt"
            elif evidence["status"] == "continuous":
                verdicts[layer_id] = "continuous"
    disappearance_indices = {
        layer_id: candidate_disappearance_indices[layer_id]
        for layer_id in pixel_supported_layers
        if layer_id in candidate_disappearance_indices and verdicts[layer_id] == "suspected_interrupt"
    }
    record_contrast_only_layers = [
        layer_id
        for layer_id, verdict in record["record_verdicts"].items()
        if verdict == "suspected_interrupt" and verdicts[layer_id] != "suspected_interrupt"
    ]
    suspected = [
        layer_id for layer_id, verdict in verdicts.items()
        if verdict == "suspected_interrupt"
    ]
    breakthrough_layer = suspected[-1] if suspected else None

    steps = [
        (
            f"Normal-wall reference: {reference_status} "
            f"({reference_fraction * 100:.0f}% reliable stations on the clear side)."
        ),
        (
            f"Trace toward lesion: {int(reliable.sum())}/{len(reliable)} stations retain "
            "the four-interface gradient pattern; lesion-interior spans stay dashed."
        ),
        (
            f"Lesion relation: {track['relation']} at {track['contact_distance_px']:.1f} px; "
            f"contact-zone visibility is {contact_visibility}."
        ),
    ]
    if track["relation"] == "not_established" and not disappearance_indices:
        steps.append(
            "Invasion conclusion: cannot judge because this frame does not establish wall-lesion contact."
        )
    elif reference_status == "limited" and not disappearance_indices:
        steps.append(
            "Invasion conclusion: cannot judge because a stable normal-wall reference is not established."
        )
    elif contact_visibility == "unseen" and not disappearance_indices:
        steps.append(
            "Invasion conclusion: cannot judge because the contact zone does not retain analyzable interfaces."
        )
        if pixel_supported_layers:
            names = ", ".join(LAYER_LABELS[layer_id] for layer_id in pixel_supported_layers)
            steps.append(
                f"Pixel drop at contact entry for {names} is kept as evidence only; "
                "it does not unlock a single-frame interruption while the contact zone is unseen."
            )
    elif disappearance_indices:
        names = ", ".join(LAYER_LABELS[layer_id] for layer_id in disappearance_indices)
        steps.append(
            f"Layer-loss screen: pixel continuity falls below 40% of the normal-side reference "
            f"for {names}; single-frame wording remains suspected interruption."
        )
    else:
        steps.append(
            "Layer-loss screen: no layer is assigned a single-frame interruption; continuity still requires adjacent-frame review."
        )
    if record_contrast_only_layers:
        names = ", ".join(LAYER_LABELS[layer_id] for layer_id in record_contrast_only_layers)
        steps.append(
            f"Record contrast: stored ticks mark {names}, but current pixels do not support a break; "
            "the curated gap is review-only and is not used as the live breakthrough seed."
        )
    steps.append("Safety cap: this visualization does not determine cT.")
    return {
        "verdicts": verdicts,
        "record_verdicts": record["record_verdicts"],
        "breakthrough_layer": breakthrough_layer,
        "single_frame": True,
        "source": "pixel continuity on the current frame",
        "doctor_impression": record.get("doctor_impression"),
        "reference_status": reference_status,
        "reference_reliable_fraction": reference_fraction,
        "contact_visibility": contact_visibility,
        "contact_reliable_fraction": contact_fraction,
        "layer_pixel_evidence": layer_pixel_evidence,
        "layer_contact_intervals": layer_contact_intervals,
        "candidate_disappearance_indices": candidate_disappearance_indices,
        "disappearance_indices": disappearance_indices,
        "record_contrast_only_layers": record_contrast_only_layers,
        "reasoning_steps": steps,
    }


def _analyze_full_trajectory(pack: dict, track: dict) -> dict:
    """Keep the full tracked axis and label observed, uncertain, and contact zones."""
    mask = (pack["crop_mask"] > 0).astype(np.uint8)
    distance = cv2.distanceTransform((mask == 0).astype(np.uint8), cv2.DIST_L2, 3)
    paths = track["paths"]
    xy = np.rint(paths).astype(np.int32)
    xy[:, :, 0] = np.clip(xy[:, :, 0], 0, mask.shape[1] - 1)
    xy[:, :, 1] = np.clip(xy[:, :, 1], 0, mask.shape[0] - 1)
    boundary_distance = distance[xy[:, :, 1], xy[:, :, 0]]
    station_distance = boundary_distance.min(axis=1)
    contact = int(np.argmin(station_distance))
    clear_is_start = bool(station_distance[0] >= station_distance[-1])
    boundary = int(np.argmin(boundary_distance[contact]))
    contact_xy = paths[contact, boundary].astype(np.float32)
    minimum_distance = float(station_distance[contact])
    relation = (
        "contact"
        if minimum_distance <= 1.0
        else "near_contact"
        if minimum_distance <= 6.0
        else "not_established"
    )
    rolling = _rolling_median(track["confidence"], radius=3)
    indices = track["indices"]
    edge_safe = (indices[:, 0] >= 2) & (indices[:, 3] <= len(OFFSETS) - 3)
    inside = np.asarray(
        track.get("inside_lesion", np.zeros(len(paths), dtype=bool)),
        dtype=bool,
    )
    if len(inside) != len(paths):
        inside = np.zeros(len(paths), dtype=bool)
    reliable = (rolling >= float(track["threshold"])) & edge_safe & (~inside)
    boundary_rolling = np.stack([
        _rolling_median(track["boundary_responses"][:, boundary], radius=3)
        for boundary in range(4)
    ], axis=1)
    boundary_thresholds = np.zeros(4, dtype=np.float32)
    boundary_reliable = np.zeros_like(boundary_rolling, dtype=bool)
    for boundary in range(4):
        positive = boundary_rolling[:, boundary][boundary_rolling[:, boundary] > 0]
        boundary_thresholds[boundary] = (
            4.0
            if not len(positive)
            else float(np.clip(np.percentile(positive, 35) * 0.55, 3.0, 8.0))
        )
        boundary_edge_safe = (
            (indices[:, boundary] >= 2)
            & (indices[:, boundary] <= len(OFFSETS) - 3)
        )
        boundary_reliable[:, boundary] = (
            boundary_rolling[:, boundary] >= boundary_thresholds[boundary]
        ) & boundary_edge_safe & (~inside)
    contact_radius = max(2, min(6, len(paths) // 12))
    contact_zone = np.abs(np.arange(len(paths)) - contact) <= contact_radius
    uncertain_runs = [
        {"start": int(start), "stop": int(stop)}
        for start, stop in _runs(~reliable)
        if stop - start + 1 >= 3
    ]
    analyzed = dict(track)
    analyzed.update({
        "contact_index": contact,
        "contact_xy": contact_xy,
        "boundary_distance": boundary_distance,
        "contact_distance_px": minimum_distance,
        "relation": relation,
        "clear_side": "start" if clear_is_start else "end",
        "full_station_count": len(paths),
        "rolling_confidence": rolling,
        "reliable_mask": reliable,
        "boundary_rolling_confidence": boundary_rolling,
        "boundary_reliable_mask": boundary_reliable,
        "boundary_thresholds": boundary_thresholds,
        "boundary_reliable_counts": boundary_reliable.sum(axis=0).astype(int),
        "contact_zone": contact_zone,
        "reliable_station_count": int(reliable.sum()),
        "uncertain_runs": uncertain_runs,
        "inside_lesion": inside,
    })
    return analyzed


def _interface_states() -> np.ndarray:
    states: list[tuple[int, int, int, int]] = []
    for edge1 in range(1, len(OFFSETS) - 10):
        for gap1 in range(3, 9):
            edge2 = edge1 + gap1
            for gap2 in range(3, 9):
                edge3 = edge2 + gap2
                for gap3 in range(3, 9):
                    edge4 = edge3 + gap3
                    if edge4 < len(OFFSETS) - 1:
                        center = 0.5 * (OFFSETS[edge1] + OFFSETS[edge4])
                        if abs(center) <= 9.0:
                            states.append((edge1, edge2, edge3, edge4))
    return np.asarray(states, dtype=np.int16)


def _select_phase_and_prior(
    enhanced: np.ndarray,
    states: np.ndarray,
    phase_lock: int | None = None,
) -> tuple[int, np.ndarray]:
    median_profile = np.median(enhanced, axis=0)
    gradient = cv2.Sobel(
        median_profile.reshape(1, -1),
        cv2.CV_32F,
        1,
        0,
        ksize=3,
        scale=0.25,
    ).reshape(-1)
    phases = (phase_lock,) if phase_lock in (1, -1) else (1, -1)
    best: tuple[float, int, np.ndarray] | None = None
    for phase in phases:
        signed = np.asarray((phase, -phase, phase, -phase), dtype=np.float32)
        responses = gradient[states]
        score = (responses * signed[None, :]).sum(axis=1)
        score -= 0.10 * np.abs(OFFSETS[states].mean(axis=1))
        index = int(np.argmax(score))
        candidate = (float(score[index]), phase, states[index])
        if best is None or candidate[0] > best[0]:
            best = candidate
    assert best is not None
    return best[1], best[2]


def _track_interfaces(
    enhanced: np.ndarray,
    valid: np.ndarray,
    phase_lock: int | None = None,
) -> dict:
    states_all = _interface_states()
    phase, prior = _select_phase_and_prior(enhanced, states_all, phase_lock=phase_lock)
    near_prior = np.max(np.abs(states_all - prior[None, :]), axis=1) <= 5
    states = states_all[near_prior]
    signed = np.asarray((phase, -phase, phase, -phase), dtype=np.float32)
    gradient = cv2.Sobel(enhanced, cv2.CV_32F, 1, 0, ksize=3, scale=0.25)
    top_k = min(80, len(states))
    selected: list[np.ndarray] = []
    unary_costs: list[np.ndarray] = []
    strengths: list[np.ndarray] = []

    for station in range(len(enhanced)):
        responses = gradient[station, states] * signed[None, :]
        strength = responses.min(axis=1)
        score = responses.sum(axis=1) + 1.8 * strength
        score -= 0.35 * np.abs(states - prior[None, :]).sum(axis=1)
        state_valid = valid[station, states].all(axis=1)
        score[~state_valid] = -1.0e6
        keep = np.argpartition(score, -top_k)[-top_k:]
        keep = keep[np.argsort(-score[keep])]
        selected.append(keep)
        unary_costs.append(-score[keep])
        strengths.append(strength[keep])

    costs: list[np.ndarray] = []
    backs: list[np.ndarray] = []
    for station, keep in enumerate(selected):
        unary = unary_costs[station]
        if station == 0:
            costs.append(unary)
            backs.append(np.full(len(keep), -1, dtype=np.int16))
            continue
        current = states[keep].astype(np.float32)
        previous = states[selected[station - 1]].astype(np.float32)
        delta = np.abs(previous[:, None, :] - current[None, :, :])
        transition = costs[-1][:, None] + 3.5 * delta.sum(axis=2)
        transition[delta.max(axis=2) > 2.0] += 1.0e5
        if station >= 2:
            prev_prev = states[selected[station - 2]].astype(np.float32)
            pred_idx = np.clip(backs[station - 1], 0, len(prev_prev) - 1)
            second = np.abs(
                current[None, :, :]
                - 2.0 * previous[:, None, :]
                + prev_prev[pred_idx][:, None, :]
            )
            transition = transition + 0.85 * second.sum(axis=2)
        back = np.argmin(transition, axis=0)
        costs.append(unary + transition[back, np.arange(len(keep))])
        backs.append(back.astype(np.int16))

    cursor = int(np.argmin(costs[-1]))
    chosen: list[int] = []
    confidence: list[float] = []
    for station in range(len(enhanced) - 1, -1, -1):
        chosen.append(int(selected[station][cursor]))
        confidence.append(float(strengths[station][cursor]))
        if station:
            cursor = int(backs[station][cursor])
    indices = states[np.asarray(chosen[::-1], dtype=np.int32)]
    boundary_responses = (
        gradient[np.arange(len(indices))[:, None], indices] * signed[None, :]
    )
    return {
        "indices": indices,
        "offsets": OFFSETS[indices],
        "confidence": np.asarray(confidence[::-1], dtype=np.float32),
        "boundary_responses": boundary_responses.astype(np.float32),
        "phase": phase,
        "prior_offsets": OFFSETS[prior],
        "gradient": gradient,
        "signed": signed,
    }


def _offsets_to_indices(offsets: np.ndarray) -> np.ndarray:
    return np.argmin(
        np.abs(OFFSETS[None, None, :] - np.asarray(offsets, dtype=np.float32)[:, :, None]),
        axis=2,
    ).astype(np.int32)


def _enforce_offset_order(offsets: np.ndarray) -> np.ndarray:
    ordered = np.asarray(offsets, dtype=np.float32).copy()
    for station in range(len(ordered)):
        for boundary in range(1, 4):
            ordered[station, boundary] = float(np.clip(
                ordered[station, boundary],
                ordered[station, boundary - 1] + 2.0,
                ordered[station, boundary - 1] + 10.0,
            ))
    return ordered


def _snap_offsets_to_gradient(
    offsets: np.ndarray,
    gradient: np.ndarray,
    signed: np.ndarray,
    radius: int = 2,
) -> np.ndarray:
    """Nudge each edge to a same-sign local Sobel peak without breaking order."""
    snapped = np.asarray(offsets, dtype=np.float32).copy()
    n_off = len(OFFSETS)
    for station in range(len(snapped)):
        candidate = snapped[station].copy()
        for boundary in range(4):
            center = int(np.argmin(np.abs(OFFSETS - offsets[station, boundary])))
            low = max(1, center - radius)
            high = min(n_off - 1, center + radius + 1)
            signed_g = gradient[station, low:high] * float(signed[boundary])
            if signed_g.size == 0:
                continue
            candidate[boundary] = OFFSETS[low + int(np.argmax(signed_g))]
        candidate = _enforce_offset_order(candidate.reshape(1, 4))[0]
        spacing = np.diff(candidate)
        if not np.all(spacing >= 2.0 - 1.0e-3) or not np.all(spacing <= 10.0 + 1.0e-3):
            continue
        if abs(float(candidate.mean())) > 9.0:
            continue
        snapped[station] = candidate
    return snapped


def _constrained_extrapolate_offsets(seed: np.ndarray, count: int) -> np.ndarray:
    """Limited-curvature, limited-width continuation used inside the lesion."""
    if count <= 0:
        return np.zeros((0, 4), dtype=np.float32)
    seed = np.asarray(seed, dtype=np.float32)
    current = seed[-1].copy()
    if len(seed) >= 2:
        slope = np.clip(seed[-1] - seed[-2], -0.8, 0.8)
    else:
        slope = np.zeros(4, dtype=np.float32)
    out = np.empty((count, 4), dtype=np.float32)
    for index in range(count):
        current = current + slope
        current = _enforce_offset_order(current.reshape(1, 4))[0]
        mean = float(current.mean())
        if abs(mean) > 9.0:
            current = current - np.sign(mean) * (abs(mean) - 9.0)
            current = _enforce_offset_order(current.reshape(1, 4))[0]
        out[index] = current
        slope *= 0.90
    return out


def _nearest_outside_offsets(offsets: np.ndarray, inside: np.ndarray) -> np.ndarray:
    """Hold the last learned layer depths when probing inside the lesion."""
    held = np.asarray(offsets, dtype=np.float32).copy()
    outside = np.where(~np.asarray(inside, dtype=bool))[0]
    if len(outside) == 0:
        return held
    for index in np.where(inside)[0]:
        nearest = int(outside[np.argmin(np.abs(outside - index))])
        held[index] = offsets[nearest]
    return held


def _station_inside_lesion(
    pack: dict,
    stations: np.ndarray,
    dilate: int = 7,
) -> np.ndarray:
    mask = pack.get("crop_mask")
    if mask is None:
        return np.zeros(len(stations), dtype=bool)
    mask_u8 = (np.asarray(mask) > 0).astype(np.uint8)
    if not mask_u8.any():
        return np.zeros(len(stations), dtype=bool)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate, dilate))
    dilated = cv2.dilate(mask_u8, kernel)
    inside = np.zeros(len(stations), dtype=bool)
    height, width = dilated.shape
    for index, point in enumerate(stations):
        x_i = int(round(float(point[0])))
        y_i = int(round(float(point[1])))
        if 0 <= y_i < height and 0 <= x_i < width:
            inside[index] = dilated[y_i, x_i] > 0
    return inside


def _blend_predict_band_offsets(
    stations: np.ndarray,
    normals: np.ndarray,
    offsets: np.ndarray,
    inside: np.ndarray,
    lesion_mask: np.ndarray,
    lesion_center: np.ndarray | None,
) -> np.ndarray:
    """Pull interior stations halfway toward the clipped-curvature forecast."""
    blended = offsets.copy()
    if lesion_mask is None or not np.any(lesion_mask) or not inside.any():
        return blended
    for boundary in range(4):
        column = np.full(len(stations), np.nan, dtype=np.float32)
        column[~inside] = offsets[~inside, boundary]
        dashed, _ring, _stop = _predict_band(
            stations, normals, column, lesion_mask, lesion_center,
        )
        if len(dashed) < 2:
            continue
        for index in np.where(inside)[0]:
            delta = dashed - stations[index]
            nearest = int(np.argmin(np.linalg.norm(delta, axis=1)))
            predicted = float(np.dot(delta[nearest], normals[index]))
            blended[index, boundary] = 0.5 * (offsets[index, boundary] + predicted)
    return _enforce_offset_order(blended)


def _track_interfaces_with_lesion(
    enhanced: np.ndarray,
    valid: np.ndarray,
    inside: np.ndarray,
    stations: np.ndarray | None = None,
    normals: np.ndarray | None = None,
    lesion_mask: np.ndarray | None = None,
    lesion_center: np.ndarray | None = None,
) -> dict:
    inside = np.asarray(inside, dtype=bool)
    count = len(enhanced)
    if count == 0:
        raise ValueError("empty unwrapped strip")
    if not inside.any() or inside.all() or int((~inside).sum()) < 6:
        track = _track_interfaces(enhanced, valid)
        track["inside_lesion"] = inside
        track["extrapolated"] = np.zeros(count, dtype=bool)
        return track

    runs = _runs(inside)
    start, stop = max(runs, key=lambda item: item[1] - item[0])
    left = slice(0, start)
    mid_count = stop - start + 1
    right = slice(stop + 1, count)
    left_track = (
        _track_interfaces(enhanced[left], valid[left])
        if left.stop - left.start >= 6
        else None
    )
    right_track = (
        _track_interfaces(
            enhanced[right],
            valid[right],
            phase_lock=None if left_track is None else int(left_track["phase"]),
        )
        if right.stop - right.start >= 6
        else None
    )
    if left_track is None and right_track is None:
        track = _track_interfaces(enhanced, valid)
        track["inside_lesion"] = inside
        track["extrapolated"] = np.zeros(count, dtype=bool)
        return track

    if left_track is not None and right_track is not None:
        if float(np.median(left_track["confidence"])) >= float(np.median(right_track["confidence"])):
            phase = int(left_track["phase"])
            prior = left_track["prior_offsets"]
        else:
            phase = int(right_track["phase"])
            prior = right_track["prior_offsets"]
    elif left_track is not None:
        phase = int(left_track["phase"])
        prior = left_track["prior_offsets"]
    else:
        phase = int(right_track["phase"])
        prior = right_track["prior_offsets"]

    offsets = np.zeros((count, 4), dtype=np.float32)
    confidence = np.zeros(count, dtype=np.float32)
    extrapolated = np.zeros(count, dtype=bool)
    if left_track is not None:
        offsets[left] = left_track["offsets"]
        confidence[left] = left_track["confidence"]
    if right_track is not None:
        offsets[right] = right_track["offsets"]
        confidence[right] = right_track["confidence"]
    if left_track is not None and right_track is not None:
        left_ext = _constrained_extrapolate_offsets(left_track["offsets"], mid_count)
        right_ext = _constrained_extrapolate_offsets(
            right_track["offsets"][::-1], mid_count,
        )[::-1]
        alpha = np.linspace(0.0, 1.0, mid_count, dtype=np.float32)[:, None]
        mid = _enforce_offset_order((1.0 - alpha) * left_ext + alpha * right_ext)
        seed_conf = min(
            float(np.median(left_track["confidence"])),
            float(np.median(right_track["confidence"])),
        )
    elif left_track is not None:
        mid = _constrained_extrapolate_offsets(left_track["offsets"], mid_count)
        seed_conf = float(np.median(left_track["confidence"]))
    else:
        mid = _constrained_extrapolate_offsets(
            right_track["offsets"][::-1], mid_count,
        )[::-1]
        seed_conf = float(np.median(right_track["confidence"]))
    offsets[start:stop + 1] = mid
    confidence[start:stop + 1] = 0.25 * seed_conf
    extrapolated[start:stop + 1] = True
    if left_track is None and start > 0:
        offsets[:start] = _constrained_extrapolate_offsets(
            offsets[start:stop + 1][::-1], start,
        )[::-1]
        confidence[:start] = 0.20 * seed_conf
        extrapolated[:start] = True
    if right_track is None and stop + 1 < count:
        offsets[stop + 1:] = _constrained_extrapolate_offsets(
            offsets[start:stop + 1], count - stop - 1,
        )
        confidence[stop + 1:] = 0.20 * seed_conf
        extrapolated[stop + 1:] = True
    if stations is not None and normals is not None and lesion_mask is not None:
        offsets = _blend_predict_band_offsets(
            stations, normals, offsets, inside, lesion_mask, lesion_center,
        )
    signed = np.asarray((phase, -phase, phase, -phase), dtype=np.float32)
    gradient = cv2.Sobel(enhanced, cv2.CV_32F, 1, 0, ksize=3, scale=0.25)
    indices = _offsets_to_indices(offsets)
    boundary_responses = gradient[np.arange(count)[:, None], indices] * signed[None, :]
    return {
        "indices": indices,
        "offsets": offsets,
        "confidence": confidence,
        "boundary_responses": boundary_responses.astype(np.float32),
        "phase": phase,
        "prior_offsets": prior,
        "gradient": gradient,
        "signed": signed,
        "inside_lesion": inside,
        "extrapolated": extrapolated,
    }


def _reliable_slice(track: dict) -> tuple[slice, float]:
    rolling = _rolling_median(track["confidence"], radius=3)
    positive = rolling[rolling > 0]
    threshold = 4.0 if not len(positive) else float(
        np.clip(np.percentile(positive, 35) * 0.55, 3.0, 8.0)
    )
    indices = track["indices"]
    edge_safe = (indices[:, 0] >= 2) & (indices[:, 3] <= len(OFFSETS) - 3)
    inside = np.asarray(
        track.get("inside_lesion", np.zeros(len(rolling), dtype=bool)),
        dtype=bool,
    )
    if len(inside) != len(rolling):
        inside = np.zeros(len(rolling), dtype=bool)
    reliable = (rolling >= threshold) & edge_safe & (~inside)
    runs = [(start, end) for start, end in _runs(reliable) if end - start + 1 >= 8]
    if not runs:
        best = int(np.argmax(rolling))
        return slice(max(0, best - 4), min(len(rolling), best + 5)), threshold
    start, end = max(runs, key=lambda item: item[1] - item[0])
    return slice(start, end + 1), threshold


def track_case(pack: dict) -> dict:
    gray = cv2.cvtColor(pack["crop"], cv2.COLOR_BGR2GRAY)
    stations, normals, heading_source, cavity_side_source = _wall_axis(pack)
    strip, _map_x, _map_y = _sample_strip(gray, stations, normals)
    enhanced = cv2.GaussianBlur(strip, (3, 9), sigmaX=0.65, sigmaY=1.8)
    inside = _station_inside_lesion(pack, stations)
    lesion = np.asarray(pack.get("lesion_poly", []), dtype=np.float32).reshape(-1, 2)
    lesion_center = polygon_centroid(lesion)
    lesion_mask = (np.asarray(pack.get("crop_mask", np.zeros(gray.shape[:2]))) > 0).astype(np.uint8)
    track = _track_interfaces_with_lesion(
        enhanced,
        strip > 0,
        inside,
        stations=stations,
        normals=normals,
        lesion_mask=lesion_mask,
        lesion_center=lesion_center,
    )
    signed = track["signed"]
    gradient = track["gradient"]
    snapped = _snap_offsets_to_gradient(track["offsets"], gradient, signed)
    snapped = _enforce_offset_order(snapped)
    indices = _offsets_to_indices(snapped)
    _selection, threshold = _reliable_slice({
        **track,
        "offsets": snapped,
        "indices": indices,
        "inside_lesion": inside,
    })
    smooth_offsets = _enforce_offset_order(_smooth_offsets(snapped))
    paths = stations[:, None, :] + normals[:, None, :] * smooth_offsets[:, :, None]
    display_indices = _offsets_to_indices(smooth_offsets)
    probe_offsets = _nearest_outside_offsets(snapped, inside)
    probe_indices = _offsets_to_indices(probe_offsets)
    boundary_responses = (
        gradient[np.arange(len(probe_indices))[:, None], probe_indices] * signed[None, :]
    )
    result = {
        "stations": stations,
        "normals": normals,
        "strip": strip,
        "indices": display_indices,
        "offsets": snapped,
        "smooth_offsets": smooth_offsets,
        "paths": paths,
        "confidence": track["confidence"],
        "boundary_responses": boundary_responses.astype(np.float32),
        "threshold": threshold,
        "phase": track["phase"],
        "heading_source": heading_source,
        "cavity_side_source": cavity_side_source,
        "inside_lesion": inside,
        "extrapolated": track.get("extrapolated", np.zeros(len(stations), dtype=bool)),
    }
    return _analyze_full_trajectory(pack, result)


def _paint_band_polygon(
    overlay: np.ndarray,
    paths: np.ndarray,
    band: int,
    alpha: float,
) -> None:
    if len(paths) < 2:
        return
    polygon = np.vstack([
        paths[:, band, :],
        paths[::-1, band + 1, :],
    ])
    polygon = np.rint(polygon).astype(np.int32)
    mask = np.zeros(overlay.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [polygon], 255, lineType=cv2.LINE_AA)
    take = mask > 0
    overlay[take] = (1.0 - alpha) * overlay[take] + alpha * BAND_COLORS[band]


def _paint_three_bands(
    rgb: np.ndarray,
    paths: np.ndarray,
    reliable: np.ndarray,
    boundary_reliable: np.ndarray | None = None,
) -> np.ndarray:
    overlay = rgb.astype(np.float32).copy()
    for band in range(3):
        # Keep the cluster visible over the complete physician trajectory.
        # Reliability is communicated by opacity and solid/dashed boundaries.
        _paint_band_polygon(overlay, paths, band, 0.11)
        band_reliable = (
            reliable
            if boundary_reliable is None
            else boundary_reliable[:, band] & boundary_reliable[:, band + 1]
        )
        for start, stop in _runs(band_reliable):
            if stop - start + 1 >= 2:
                _paint_band_polygon(overlay, paths[start:stop + 1], band, 0.18)
    return np.clip(overlay, 0, 255).astype(np.uint8)


def _draw_interfaces(
    ax,
    paths: np.ndarray,
    reliable: np.ndarray,
    linewidth: float,
) -> None:
    for boundary in range(4):
        ax.plot(
            paths[:, boundary, 0],
            paths[:, boundary, 1],
            color=BOUNDARY_COLORS[boundary],
            linewidth=max(0.65, linewidth * 0.72),
            linestyle=(0, (3, 3)),
            alpha=0.52,
            solid_capstyle="round",
            solid_joinstyle="round",
            zorder=5,
        )
        boundary_reliable = reliable if reliable.ndim == 1 else reliable[:, boundary]
        for start, stop in _runs(boundary_reliable):
            if stop - start + 1 < 2:
                continue
            segment = paths[start:stop + 1, boundary, :]
            ax.plot(
                segment[:, 0],
                segment[:, 1],
                color=BOUNDARY_COLORS[boundary],
                linewidth=linewidth,
                solid_capstyle="round",
                solid_joinstyle="round",
                zorder=6,
            )


def render_case(pack: dict, track: dict, out_dir: Path) -> Path:
    meta = pack["meta"]
    rgb = cv2.cvtColor(pack["crop"], cv2.COLOR_BGR2RGB)
    reliable = np.asarray(track["reliable_mask"], dtype=bool)
    boundary_reliable = np.asarray(track["boundary_reliable_mask"], dtype=bool)
    panel = _paint_three_bands(rgb, track["paths"], reliable, boundary_reliable)
    mask = (pack["crop_mask"] > 0).astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(panel, contours, -1, (191, 219, 254), 1, cv2.LINE_AA)
    adjustment = pack.get("lesion_adjustment")
    if adjustment:
        ox1, oy1, ox2, oy2 = adjustment["original_box_xyxy"]
        ex1, ey1, ex2, ey2 = adjustment["expanded_box_xyxy"]
        cv2.rectangle(panel, (ex1, ey1), (ex2 - 1, ey2 - 1), (96, 165, 250), 1, cv2.LINE_AA)
        cv2.rectangle(panel, (ox1, oy1), (ox2 - 1, oy2 - 1), (250, 204, 21), 1, cv2.LINE_AA)

    fig, axes = plt.subplots(1, 2, figsize=(14.2, 7.1), gridspec_kw={"width_ratios": [1.12, 1.0]})
    axes[0].imshow(panel, interpolation="nearest")
    _draw_interfaces(axes[0], track["paths"], boundary_reliable, 1.15)
    contact_xy = np.asarray(track["contact_xy"], dtype=np.float32)
    breakthrough_layer = track["invasion"]["breakthrough_layer"]
    annotation_xy = contact_xy
    if breakthrough_layer:
        station = track["invasion"]["disappearance_indices"][breakthrough_layer]
        boundary = LAYER_BOUNDARY_INDEX[breakthrough_layer]
        annotation_xy = np.asarray(track["paths"][station, boundary], dtype=np.float32)
        pixel = track["invasion"]["layer_pixel_evidence"].get(breakthrough_layer, {})
        annotation = (
            f"Pixel-supported\nsuspected {LAYER_LABELS[breakthrough_layer].lower()} interruption"
            if pixel.get("status") == "disrupted"
            else f"Suspected {LAYER_LABELS[breakthrough_layer].lower()} interruption"
        )
        annotation_color = "#f87171"
    elif all(
        verdict == "cannot_judge"
        for verdict in track["invasion"]["verdicts"].values()
    ):
        annotation = "Wall-layer invasion: cannot judge"
        annotation_color = "#d1d5db"
    else:
        annotation = "No single-frame interruption assigned"
        annotation_color = "#86efac"
    axes[0].scatter(
        [contact_xy[0]],
        [contact_xy[1]],
        s=28,
        facecolors="none",
        edgecolors="#93c5fd",
        linewidths=1.2,
        zorder=8,
    )
    axes[0].annotate(
        "Lesion contact",
        xy=(float(contact_xy[0]), float(contact_xy[1])),
        xytext=(7, -12),
        textcoords="offset points",
        color="#bfdbfe",
        fontsize=7.5,
        zorder=9,
    )
    axes[0].annotate(
        annotation,
        xy=(float(annotation_xy[0]), float(annotation_xy[1])),
        xytext=(18, -35),
        textcoords="offset points",
        color=annotation_color,
        fontsize=9.0,
        fontweight="bold",
        bbox={
            "boxstyle": "round,pad=0.35",
            "facecolor": "#450a0a" if breakthrough_layer else "#111827",
            "edgecolor": annotation_color,
            "alpha": 0.92,
        },
        arrowprops={"arrowstyle": "-|>", "color": annotation_color, "lw": 1.6},
        zorder=12,
    )
    if breakthrough_layer:
        breakthrough_station = track["invasion"]["disappearance_indices"][breakthrough_layer]
        breakthrough_boundary = LAYER_BOUNDARY_INDEX[breakthrough_layer]
        contact_intervals = track["invasion"]["layer_contact_intervals"].get(
            breakthrough_layer,
            [],
        )
        matching_interval = next(
            (
                (start, stop)
                for start, stop in contact_intervals
                if start <= breakthrough_station <= stop
            ),
            None,
        )
        if matching_interval:
            contact_start, contact_stop = matching_interval
            contact_segment = track["paths"][
                contact_start:contact_stop + 1,
                breakthrough_boundary,
                :,
            ]
            axes[0].plot(
                contact_segment[:, 0],
                contact_segment[:, 1],
                color="#fb923c",
                linewidth=5.2,
                alpha=0.30,
                solid_capstyle="round",
                zorder=8,
            )
        break_radius = max(5, min(8, len(track["paths"]) // 15))
        break_start = max(0, breakthrough_station - break_radius)
        break_stop = min(len(track["paths"]) - 1, breakthrough_station + break_radius)
        break_segment = track["paths"][
            break_start:break_stop + 1,
            breakthrough_boundary,
            :,
        ]
        axes[0].plot(
            break_segment[:, 0],
            break_segment[:, 1],
            color="#ef4444",
            linewidth=4.2,
            alpha=0.62,
            solid_capstyle="round",
            zorder=9,
        )
        axes[0].scatter(
            [annotation_xy[0]],
            [annotation_xy[1]],
            s=260,
            facecolors="#ef4444",
            edgecolors="none",
            alpha=0.22,
            zorder=9,
        )
        axes[0].scatter(
            [annotation_xy[0]],
            [annotation_xy[1]],
            s=135,
            facecolors="none",
            edgecolors="#fecaca",
            linewidths=2.0,
            zorder=10,
        )
        axes[0].scatter(
            [annotation_xy[0]],
            [annotation_xy[1]],
            marker="x",
            s=72,
            color="#ffffff",
            linewidths=2.2,
            zorder=11,
        )
        axes[0].text(
            0.98,
            0.04,
            f"SUSPECTED LAYER BREAK\n{LAYER_LABELS[breakthrough_layer].upper()}",
            transform=axes[0].transAxes,
            ha="right",
            va="bottom",
            color="#ffffff",
            fontsize=9,
            fontweight="bold",
            bbox={
                "boxstyle": "round,pad=0.45",
                "facecolor": "#991b1b",
                "edgecolor": "#fecaca",
                "linewidth": 1.4,
                "alpha": 0.94,
            },
            zorder=12,
        )
    clear_index = 0 if track["clear_side"] == "start" else len(track["paths"]) - 1
    clear_xy = track["paths"][clear_index].mean(axis=0)
    axes[0].scatter(
        [clear_xy[0]],
        [clear_xy[1]],
        s=24,
        facecolors="none",
        edgecolors="#86efac",
        linewidths=1.1,
        zorder=8,
    )
    axes[0].annotate(
        "Normal-wall reference",
        xy=(float(clear_xy[0]), float(clear_xy[1])),
        xytext=(8, 13),
        textcoords="offset points",
        color="#86efac",
        fontsize=8,
        arrowprops={"arrowstyle": "-", "color": "#86efac", "lw": 0.8},
        zorder=9,
    )
    for order, (layer_id, station) in enumerate(
        track["invasion"]["disappearance_indices"].items()
    ):
        if layer_id == breakthrough_layer:
            continue
        boundary = LAYER_BOUNDARY_INDEX[layer_id]
        point = track["paths"][station, boundary]
        axes[0].scatter(
            [point[0]],
            [point[1]],
            marker="x",
            s=34,
            color="#fb7185",
            linewidths=1.4,
            zorder=10,
        )
        axes[0].annotate(
            f"{LAYER_LABELS[layer_id]} loss",
            xy=(float(point[0]), float(point[1])),
            xytext=(9, 18 + order * 13),
            textcoords="offset points",
            color="#fda4af",
            fontsize=8,
            arrowprops={"arrowstyle": "->", "color": "#fda4af", "lw": 0.8},
            zorder=10,
        )
    withheld = {
        layer_id: station
        for layer_id, station in track["invasion"]["candidate_disappearance_indices"].items()
        if layer_id not in track["invasion"]["disappearance_indices"]
    }
    for order, (layer_id, station) in enumerate(withheld.items()):
        boundary = LAYER_BOUNDARY_INDEX[layer_id]
        point = track["paths"][station, boundary]
        axes[0].scatter(
            [point[0]],
            [point[1]],
            marker="+",
            s=34,
            color="#fbbf24",
            linewidths=1.4,
            zorder=10,
        )
        axes[0].annotate(
            f"Pixel drop, cannot judge ({LAYER_LABELS[layer_id].lower()})",
            xy=(float(point[0]), float(point[1])),
            xytext=(9, 18 + order * 13),
            textcoords="offset points",
            color="#fde68a",
            fontsize=8,
            arrowprops={"arrowstyle": "->", "color": "#fde68a", "lw": 0.8},
            zorder=10,
        )
    axes[0].set_title("A  Full wall trajectory and layer-loss sites", fontsize=12)
    axes[0].axis("off")

    axes[1].imshow(
        track["strip"].T,
        cmap="gray",
        vmin=0,
        vmax=255,
        aspect="auto",
        interpolation="nearest",
        extent=(0, len(track["strip"]) - 1, OFFSETS[-1], OFFSETS[0]),
    )
    station_axis = np.arange(len(track["strip"]))
    for start, stop in _runs(~reliable):
        axes[1].axvspan(start, stop, color="#ef4444", alpha=0.10, linewidth=0)
    axes[1].axvline(
        track["contact_index"],
        color="#f87171",
        linewidth=1.0,
        linestyle=(0, (3, 2)),
        alpha=0.9,
    )
    if breakthrough_layer:
        breakthrough_station = track["invasion"]["disappearance_indices"][breakthrough_layer]
        boundary = LAYER_BOUNDARY_INDEX[breakthrough_layer]
        contact_intervals = track["invasion"]["layer_contact_intervals"].get(
            breakthrough_layer,
            [],
        )
        matching_interval = next(
            (
                (start, stop)
                for start, stop in contact_intervals
                if start <= breakthrough_station <= stop
            ),
            None,
        )
        if matching_interval:
            axes[1].axvspan(
                matching_interval[0],
                matching_interval[1],
                color="#f97316",
                alpha=0.10,
                linewidth=0,
                zorder=1,
            )
        break_radius = max(5, min(8, len(track["strip"]) // 15))
        axes[1].axvspan(
            max(0, breakthrough_station - break_radius),
            min(len(track["strip"]) - 1, breakthrough_station + break_radius),
            color="#dc2626",
            alpha=0.28,
            linewidth=0,
            zorder=2,
        )
        axes[1].annotate(
            "Suspected break",
            xy=(breakthrough_station, track["smooth_offsets"][breakthrough_station, boundary]),
            xytext=(8, -28),
            textcoords="offset points",
            color="#fecaca",
            fontsize=8,
            fontweight="bold",
            arrowprops={"arrowstyle": "-|>", "color": "#f87171", "lw": 1.2},
            zorder=8,
        )
    for boundary in range(4):
        axes[1].plot(
            station_axis,
            track["smooth_offsets"][:, boundary],
            color=BOUNDARY_COLORS[boundary],
            linewidth=1.1,
            solid_capstyle="round",
        )
    axes[1].set_title("B  Unwrapped interfaces, shaded where uncertain", fontsize=12)
    axes[1].set_xlabel("Wall station")
    axes[1].set_ylabel("Normal offset (px)")
    axes[1].tick_params(colors="#d1d5db", labelsize=8)

    handles = [
        Line2D([0], [0], color=color, lw=2, label=f"Boundary {index + 1}")
        for index, color in enumerate(BOUNDARY_COLORS)
    ]
    handles.extend([
        Patch(facecolor="#64748b", alpha=0.32, label="Full-path cluster"),
        Line2D([0], [0], color="#fb923c", lw=4, alpha=0.5, label="Layer-lesion contact span"),
        Line2D([0], [0], color="#e5e7eb", lw=1.4, label="Observed solid trajectory"),
        Line2D([0], [0], color="#e5e7eb", lw=1.0, linestyle=(0, (3, 3)), alpha=0.55, label="Uncertain dashed continuation"),
    ])
    if adjustment:
        handles.extend([
            Line2D([0], [0], color="#60a5fa", lw=1.5, label="Expanded re-segmentation ROI"),
            Line2D([0], [0], color="#facc15", lw=1.5, label="Original lesion box"),
        ])
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=7,
        frameon=False,
        labelcolor="white",
        fontsize=9,
        bbox_to_anchor=(0.5, 0.018),
    )
    pattern = "bright-dark-bright" if track["phase"] > 0 else "dark-bright-dark"
    verdict_text = "    ".join(
        f"{LAYER_LABELS[layer_id]}: {VERDICT_LABELS.get(verdict, verdict)}"
        for layer_id, verdict in track["invasion"]["verdicts"].items()
    )
    fig.suptitle(
        f"{meta['display_id']}  Joint interface tracking",
        fontsize=14,
        y=0.985,
    )
    fig.text(
        0.5,
        0.165,
        f"{track['heading_source']}; cavity={track.get('cavity_side_source', 'heuristic')}; "
        f"{pattern}; full stations={len(track['stations'])}; "
        f"joint-supported={track['reliable_station_count']} "
        f"({track['reliable_station_count'] / max(1, len(track['stations'])) * 100:.0f}%); "
        f"per-interface={'/'.join(str(int(value)) for value in track['boundary_reliable_counts'])}; "
        f"contact distance={track['contact_distance_px']:.1f} px",
        ha="center",
        color="#d1d5db",
        fontsize=9,
    )
    fig.text(
        0.5,
        0.125,
        verdict_text,
        ha="center",
        color="#e5e7eb",
        fontsize=8.5,
    )
    reasoning_line = track["invasion"]["reasoning_steps"][3]
    if track["invasion"].get("doctor_impression"):
        reasoning_line += f"  Physician impression: {track['invasion']['doctor_impression']}."
    fig.text(
        0.5,
        0.087,
        reasoning_line,
        ha="center",
        color="#cbd5e1",
        fontsize=8.2,
    )
    fig.tight_layout(rect=[0.01, 0.21, 0.99, 0.94])
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{meta['case_id']}_directional_interfaces.png"
    fig.savefig(dest, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return dest


def render_index(paths: list[Path], out_dir: Path) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(16.0, 10.6))
    for ax, path in zip(axes.flat, paths):
        ax.imshow(plt.imread(path))
        ax.axis("off")
    fig.suptitle("Four-case pixel-aligned wall-interface probe", fontsize=16, y=0.995)
    fig.tight_layout(pad=0.7)
    dest = out_dir / "wall_directional_interfaces_4cases.png"
    fig.savefig(dest, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return dest


def render_html_summary(summaries: list[dict], index: Path, out_dir: Path) -> Path:
    case_sections = []
    for item in summaries:
        lesion_note = ""
        adjustment = item.get("lesion_adjustment")
        if adjustment:
            lesion_note = (
                f"<li><strong>P008 centered-box re-segmentation:</strong> "
                f"{html.escape(str(adjustment['backend']))}; box "
                f"{adjustment['original_box_xyxy']} to {adjustment['expanded_box_xyxy']}; "
                f"mask {adjustment['area_before']} to {adjustment['area_after']} pixels; "
                f"center shift {adjustment['center_shift_px']:.2f} px</li>"
            )
        invasion = item["invasion"]
        breakthrough_layer = invasion.get("breakthrough_layer")
        all_unresolved = all(
            verdict == "cannot_judge"
            for verdict in invasion["verdicts"].values()
        )
        breakthrough = (
            f"Suspected {LAYER_LABELS[breakthrough_layer].lower()} interruption"
            if breakthrough_layer
            else "Cannot judge"
            if all_unresolved
            else "No single-frame interruption assigned"
        )
        layer_rows = "".join(
            f"<li><strong>{LAYER_LABELS[layer_id]}:</strong> "
            f"{VERDICT_LABELS.get(verdict, verdict)}</li>"
            for layer_id, verdict in invasion["verdicts"].items()
        )
        reasoning_rows = "".join(
            f"<li>{html.escape(step)}</li>"
            for step in invasion["reasoning_steps"]
        )
        pixel_rows = "".join(
            f"<li><strong>{LAYER_LABELS[layer_id]} pixel continuity:</strong> "
            f"normal-side gradient {evidence['reference_strength']:.2f}, "
            f"lesion-side local gradient {evidence['local_strength']:.2f}, "
            f"ratio {evidence['strength_ratio'] * 100:.0f}%, "
            f"width {evidence['reference_width_px']:.1f} to "
            f"{evidence['local_width_px']:.1f} px, "
            f"{html.escape(evidence['status'])}, "
            f"{html.escape(evidence['mechanism'])}</li>"
            for layer_id, evidence in invasion["layer_pixel_evidence"].items()
        )
        candidate_layers = ", ".join(
            LAYER_LABELS[layer_id]
            for layer_id in invasion["candidate_disappearance_indices"]
        ) or "none"
        record_contrast = ", ".join(
            LAYER_LABELS[layer_id]
            for layer_id in invasion.get("record_contrast_only_layers", [])
        ) or "none"
        doctor_note = (
            f"<li><strong>Physician impression:</strong> "
            f"{html.escape(str(invasion['doctor_impression']))}</li>"
            if invasion.get("doctor_impression")
            else ""
        )
        case_sections.append(
            f"""
            <article class="case">
              <div>
                <p class="eyebrow">{html.escape(item['display_id'])}</p>
                <h3>{html.escape(item['pattern'])}</h3>
                <ul>
                  <li><strong>Heading:</strong> {html.escape(item['heading_source'])}</li>
                  <li><strong>Cavity side:</strong> {html.escape(str(item.get('cavity_side_source') or 'heuristic'))}</li>
                  <li><strong>Full trajectory:</strong> {item['retained_stations']} stations</li>
                  <li><strong>Pixel-supported trajectory:</strong> {item['reliable_stations']} stations
                  ({item['reliable_fraction'] * 100:.0f}%)</li>
                  <li><strong>Per-interface supported stations:</strong>
                  {' / '.join(str(value) for value in item['boundary_reliable_counts'])}</li>
                  <li><strong>Uncertain spans:</strong> {len(item['uncertain_runs'])}</li>
                  <li><strong>Median edge confidence:</strong> {item['median_edge_confidence']:.2f}</li>
                  <li><strong>Wall-lesion relation:</strong> {html.escape(item['relation'])},
                  distance {item['contact_distance_px']:.2f} px</li>
                  <li><strong>Single-frame label:</strong> {html.escape(breakthrough)}</li>
                  {doctor_note}
                  <li><strong>Pixel-supported break candidates:</strong> {html.escape(candidate_layers)}</li>
                  <li><strong>Record contrast, review only:</strong> {html.escape(record_contrast)}</li>
                  {pixel_rows}
                  {layer_rows}
                  {lesion_note}
                </ul>
                <details class="reasoning" open>
                  <summary>Clinical reasoning sequence</summary>
                  <ol>{reasoning_rows}</ol>
                </details>
              </div>
              <figure>
                <img src="{html.escape(Path(item['panel']).name)}" alt="{html.escape(item['display_id'])} interface result">
                <figcaption>Four tracked interfaces and three intervening bands.</figcaption>
              </figure>
            </article>
            """
        )
    p008_adjustment = next(
        (item["lesion_adjustment"] for item in summaries if item.get("lesion_adjustment")),
        None,
    )
    if p008_adjustment:
        p008_section = (
            "<h2>P008病灶修正</h2>"
            "<p class=\"warning\">当前病灶紧框为 "
            f"<code>{html.escape(str(p008_adjustment['original_box_xyxy']))}</code>。"
            "算法以该病灶像素质心为中心，将框外扩到 "
            f"<code>{html.escape(str(p008_adjustment['expanded_box_xyxy']))}</code>，"
            f"宽高分别扩大 {p008_adjustment['box_width_scale']:.2f} 和 "
            f"{p008_adjustment['box_height_scale']:.2f} 倍，再在扩张框原始像素内重新分割。"
            f"本次后端为 {html.escape(str(p008_adjustment['backend']))}；"
            f"面积由 {p008_adjustment['area_before']} 变为 "
            f"{p008_adjustment['area_after']} 像素，质心移动 "
            f"{p008_adjustment['center_shift_px']:.2f} px。"
            "蓝框表示扩张重分割ROI，黄框表示修正前病灶紧框。"
            "输出仍是离线复核结果，不覆盖原始临床标注。</p>"
        )
    else:
        p008_section = ""
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Gastric wall interface tracking summary</title>
  <style>
    :root {{ color-scheme: dark; --bg:#080b10; --panel:#111722; --line:#293241; --text:#eef2f7; --muted:#9ba7b6; --accent:#38bdf8; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font:15px/1.65 Arial, "Noto Sans SC", sans-serif; }}
    main {{ width:min(1180px, 94vw); margin:0 auto; padding:48px 0 72px; }}
    h1 {{ font:600 34px/1.2 Georgia, serif; margin:8px 0 16px; }}
    h2 {{ margin:44px 0 16px; font-size:22px; }}
    h3 {{ margin:2px 0 10px; font-size:19px; }}
    p {{ color:var(--muted); max-width:860px; }}
    .eyebrow {{ color:var(--accent); letter-spacing:.12em; text-transform:uppercase; margin:0; font-size:12px; }}
    .hero {{ border-bottom:1px solid var(--line); padding-bottom:32px; }}
    .status {{ display:inline-block; border:1px solid var(--line); padding:6px 10px; color:var(--text); }}
    .pipeline {{ display:grid; grid-template-columns:repeat(3,1fr); gap:1px; background:var(--line); border:1px solid var(--line); }}
    .step {{ background:var(--panel); padding:20px; }}
    .step strong {{ display:block; margin-bottom:6px; }}
    .case {{ display:grid; grid-template-columns:280px 1fr; gap:24px; align-items:center; border-top:1px solid var(--line); padding:26px 0; }}
    ul {{ padding-left:18px; color:var(--muted); }}
    strong {{ color:var(--text); }}
    figure {{ margin:0; }}
    img {{ width:100%; height:auto; display:block; border:1px solid var(--line); }}
    figcaption {{ color:var(--muted); font-size:12px; margin-top:8px; }}
    .overview {{ margin:22px 0 8px; }}
    .warning {{ border-left:3px solid var(--accent); padding:2px 0 2px 16px; }}
    .reasoning {{ margin-top:14px; border-left:2px solid #475569; padding-left:12px; color:var(--muted); }}
    .reasoning summary {{ cursor:pointer; color:var(--text); font-weight:600; }}
    .reasoning ol {{ padding-left:18px; font-size:13px; }}
    .formula-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
    .formula {{ background:#0b111a; border:1px solid var(--line); padding:14px 16px; overflow:auto; }}
    .formula strong {{ display:block; color:#bae6fd; margin-bottom:7px; }}
    .math {{ color:#f8fafc; font:14px/1.7 "Times New Roman", serif; white-space:nowrap; }}
    .formula p {{ margin:6px 0 0; font-size:13px; }}
    pre {{ margin:12px 0; padding:16px; overflow:auto; background:#05080d; border:1px solid var(--line); color:#dbeafe; font:12px/1.6 "SFMono-Regular",Consolas,monospace; }}
    table {{ width:100%; border-collapse:collapse; margin:12px 0 20px; color:var(--muted); }}
    th,td {{ border:1px solid var(--line); padding:9px 11px; text-align:left; vertical-align:top; }}
    th {{ color:var(--text); background:#0b111a; }}
    .code-note {{ font-size:13px; color:var(--muted); }}
    code {{ color:#bae6fd; }}
    @media (max-width:800px) {{ .pipeline,.formula-grid {{ grid-template-columns:1fr; }} .case {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
<main>
  <section class="hero">
    <p class="eyebrow">Offline method report, 2026-08-30</p>
    <h1>胃壁四界面联合追踪</h1>
    <p>当前胃壁分层不是端到端深度学习：它使用医生走行先验、方向展开、各向异性滤波和联合动态规划，在源像素上寻找四个交替灰度跃迁界面，并将界面之间显示为三条带。病灶修正是独立前置步骤：以现有病灶为中心外扩矩形框，在扩张ROI内重新执行像素分割。</p>
    <span class="status">Clinical review draft, not pixel ground truth, not cT</span>
  </section>

  <h2>算法流程</h2>
  <section class="pipeline">
    <div class="step"><strong>1. Lesion re-segmentation</strong>以当前病灶为中心，把紧框扩成更大的矩形ROI，在新框内重新分割，而不是直接膨胀旧掩膜。</div>
    <div class="step"><strong>2. Input quality gate</strong>检查走行线曲折度和局部转角。无效涂画不会直接进入追踪。</div>
    <div class="step"><strong>3. Clean local axis</strong>自交或过度曲折的走行改用灶外主弧，不用人工三条线的均值当解剖轴。有可用胃腔时法向背离胃腔，不再强制翻到图像下方。</div>
    <div class="step"><strong>4. Wall unwrapping</strong>沿走行切线采样，将弯曲胃壁展开成“走行位置 x 法向深度”。</div>
    <div class="step"><strong>5. Directional filtering</strong>沿胃壁方向平滑散斑，尽量保留法向上的亮暗跃迁。</div>
    <div class="step"><strong>6. Joint interface search</strong>仅在灶外学习联合动态规划，加上轻量二阶平滑；追踪后再做局部梯度贴边，并保持界面顺序与2-10 px间距。</div>
    <div class="step"><strong>7. Full-trajectory clustering</strong>三条聚类带完整覆盖医生画线走行；可靠段提高填色强度，低置信段保留淡色而不截断。</div>
    <div class="step"><strong>8. Visibility zoning</strong>像素支持充分的轨迹画实线；低置信、贴窗边或无法确认的延续画虚线，并在展开图中标红。</div>
    <div class="step"><strong>9. Layer disappearance screen</strong>灶内只画受限虚线外推。断点只看像素：正常侧参考足够强，进入接触区后连续多站掉到40%以下，才标疑似中断。记录中的 curated gap 仅作对照。</div>
    <div class="step"><strong>10. Restricted invasion readout</strong>疑似突破处沿对应界面高亮局部红色区段，并用红色光晕、白色叉号、箭头标签和展开图红色窗口同步定位。单帧只允许疑似中断或无法判断，不确认突破。</div>
  </section>

  <h2>逐步输入、处理、输出与失败处理</h2>
  <table>
    <thead><tr><th>Stage</th><th>Input</th><th>Processing</th><th>Output / failure policy</th></tr></thead>
    <tbody>
      <tr><td>病灶定位</td><td>当前病灶掩膜</td><td>求非零像素紧框及质心</td><td>无有效像素则不修正，保留原掩膜</td></tr>
      <tr><td>中心外扩框</td><td>紧框宽高和质心</td><td>质心固定；宽至少72 px或原宽2.4倍，高至少48 px或原高3倍；裁剪到图像边界</td><td>得到expanded ROI；图中蓝框显示</td></tr>
      <tr><td>ROI重新分割</td><td>扩张ROI原始像素</td><td>优先运行当前分割器；仅接受面积增大且与原病灶重叠充分的分量</td><td>模型结果不合格时转入像素级GraphCut，不使用形态学膨胀作为最终病灶</td></tr>
      <tr><td>GraphCut回退</td><td>扩张ROI、原病灶种子</td><td>原病灶为确定前景，邻域为可能前景，ROI边缘为确定背景，迭代6次</td><td>选取与原病灶重叠最大的连通分量；无分量则保留原掩膜</td></tr>
      <tr><td>走行质量门</td><td>医生胃壁画线</td><td>计算弧长/弦长曲折度及最大局部转角</td><td>异常走行改用灶外主弧，不用 curated 三线均值</td></tr>
      <tr><td>等距站位</td><td>有效走行轴</td><td>平滑并按弧长重采样，计算每站切向与法向</td><td>生成站位 <code>s_i</code>、法向 <code>n_i</code></td></tr>
      <tr><td>胃壁展开</td><td>原图、站位、法向</td><td>每站在法向-24至24 px双线性采样</td><td>得到49像素深度的直条带和有效采样掩膜</td></tr>
      <tr><td>方向增强</td><td>展开条带</td><td>走行方向强平滑、法向轻平滑，并计算法向Sobel梯度</td><td>抑制散斑但保留层间亮暗跃迁</td></tr>
      <tr><td>相位与先验</td><td>中位灰度剖面</td><td>比较两种梯度符号，自动选bright-dark-bright或dark-bright-dark</td><td>得到四界面初始先验；没有固定灰度相位假设</td></tr>
      <tr><td>联合动态规划</td><td>四界面候选状态</td><td>联合图像得分、间距约束、先验偏差和相邻站位移代价</td><td>Viterbi回溯一条全局有序四界面路径，禁止界面交叉</td></tr>
      <tr><td>可靠性分区</td><td>每站四界面梯度</td><td>联合门取最弱界面响应；显示门再对四条边分别作7站中位滤波和边界检查</td><td>临床判断继续使用严格联合门；每条边按自身像素证据独立延长实线</td></tr>
      <tr><td>病灶接触</td><td>重分割病灶、四界面</td><td>距离变换求界面到病灶的最近站位</td><td>输出contact、near contact或not established</td></tr>
      <tr><td>逐层像素连续性</td><td>正常侧20%梯度、疑似断点邻域</td><td>比较同一界面正常参考与病灶侧连续3站的响应</td><td>强参考下降至40%以下才保留该层疑似中断</td></tr>
      <tr><td>安全输出</td><td>接触、可见度、逐层证据</td><td>依次执行正常参考、接触可见、层消失和单帧安全门</td><td>只输出continuous、suspected interruption或cannot judge，不自动确定cT</td></tr>
    </tbody>
  </table>

  <h2>核心数学定义</h2>
  <p>下式对应当前代码，而不是概念性占位符。走行方向记为站位索引 <code>i</code>，胃壁法向偏移记为 <code>o</code>，四个有序界面记为 <code>e1...e4</code>。</p>
  <section class="formula-grid">
    <div class="formula">
      <strong>L1. 病灶中心外扩框</strong>
      <div class="math">c<sub>0</sub>=mean{{(x,y):M<sub>0</sub>(x,y)=1}}</div>
      <div class="math">W<sub>1</sub>=max(72,2.4W<sub>0</sub>), &nbsp; H<sub>1</sub>=max(48,3.0H<sub>0</sub>)</div>
      <p>扩张框始终以当前病灶像素质心为中心，再裁剪到图像边界；不是对旧掩膜轮廓作固定核膨胀。</p>
    </div>
    <div class="formula">
      <strong>L2. 扩张ROI重新分割</strong>
      <div class="math">M<sub>1</sub>=Segment(I|B<sub>1</sub>), &nbsp; component*=argmax<sub>C</sub>|C&cap;M<sub>0</sub>|</div>
      <div class="math">E(L)=&Sigma;<sub>p</sub>D<sub>p</sub>(L<sub>p</sub>)+&lambda;&Sigma;<sub>(p,q)</sub>V<sub>pq</sub>[L<sub>p</sub>&ne;L<sub>q</sub>]</div>
      <p>模型候选必须比原掩膜大且保持足够重叠；否则在同一扩张框内用原病灶作硬前景种子执行GraphCut，并选择与原病灶重叠最大的分量。</p>
    </div>
    <div class="formula">
      <strong>1. 沿胃壁展开</strong>
      <div class="math">I<sub>strip</sub>(i,o) = I(s<sub>i</sub> + o n<sub>i</sub>), &nbsp; o &isin; [-24,24] px</div>
      <p><code>s_i</code>是平滑后的走行站位，<code>n_i</code>是单位法向。弯曲胃壁因此转换为“站位 x 法向深度”的矩形条带。</p>
    </div>
    <div class="formula">
      <strong>2. 方向滤波</strong>
      <div class="math">I&#771; = G(&sigma;<sub>station</sub>=1.8, &sigma;<sub>normal</sub>=0.65) * I<sub>strip</sub></div>
      <p>沿胃壁方向更强地抑制散斑，法向只轻度平滑，以保留亮暗层界。</p>
    </div>
    <div class="formula">
      <strong>3. 四界面状态空间</strong>
      <div class="math">q<sub>i</sub>=(e<sub>i1</sub>,e<sub>i2</sub>,e<sub>i3</sub>,e<sub>i4</sub>)</div>
      <div class="math">3 &le; e<sub>i,k+1</sub>-e<sub>ik</sub> &le; 8, &nbsp; |mean(o<sub>e</sub>)| &le; 9 px</div>
      <p>顺序和层宽在生成候选时已被硬约束，因此四条线不会互相穿越。</p>
    </div>
    <div class="formula">
      <strong>4. 交替梯度响应</strong>
      <div class="math">r<sub>ik</sub>(q)=p(-1)<sup>k</sup>&part;I&#771;(i,e<sub>ik</sub>)/&part;o, &nbsp; p &isin; {{-1,+1}}</div>
      <p><code>p</code>自动选择 bright-dark-bright 或 dark-bright-dark 相位。</p>
    </div>
    <div class="formula">
      <strong>5. 单站图像得分</strong>
      <div class="math">S<sub>i</sub>(q)=&Sigma;<sub>k</sub>r<sub>ik</sub> + 1.8 min<sub>k</sub>r<sub>ik</sub> - 0.35 &Sigma;<sub>k</sub>|e<sub>ik</sub>-e<sub>k</sub><sup>prior</sup>|</div>
      <p>不仅要求总梯度强，还要求四条边里最弱的一条不能太差，并对偏离稳健先验的状态施加小惩罚。</p>
    </div>
    <div class="formula">
      <strong>6. 动态规划能量</strong>
      <div class="math">E(q<sub>1:N</sub>)=-&Sigma;<sub>i</sub>S<sub>i</sub>(q<sub>i</sub>)+&Sigma;<sub>i&gt;1</sub>T(q<sub>i-1</sub>,q<sub>i</sub>)</div>
      <div class="math">T=3.5&Sigma;<sub>k</sub>|e<sub>ik</sub>-e<sub>i-1,k</sub>|+10<sup>5</sup>1[max<sub>k</sub>|&Delta;e<sub>ik</sub>|&gt;2]</div>
      <p>Viterbi回溯得到全局最低能量路径；相邻站任一界面跳动超过2 px会被近似禁止。</p>
    </div>
    <div class="formula">
      <strong>7. 可靠性门控</strong>
      <div class="math">c<sub>i</sub>=min<sub>k</sub>r<sub>ik</sub>, &nbsp; &theta;=clip(0.55 P<sub>35</sub>(c&gt;0),3,8)</div>
      <div class="math">reliable<sub>i</sub>=[median<sub>7</sub>(c<sub>i</sub>)&ge;&theta;] &and; edge-safe</div>
      <div class="math">reliable<sub>ik</sub>=[median<sub>7</sub>(r<sub>ik</sub>)&ge;&theta;<sub>k</sub>] &and; edge-safe<sub>ik</sub></div>
      <p><code>reliable_i</code>是四条边同时成立的严格联合门，用于接触可见度和临床安全门；
      <code>reliable_ik</code>只控制第k条界面的实线显示，因此一条弱边不会截短其余三条有像素支持的边。</p>
    </div>
    <div class="formula">
      <strong>8. 显示平滑与像素约束</strong>
      <div class="math">o&#770;<sub>ik</sub>=clip(([1,4,6,4,1]/16)*o<sub>ik</sub>, o<sub>ik</sub>-1, o<sub>ik</sub>+1)</div>
      <div class="math">x<sub>ik</sub>=s<sub>i</sub>+o&#770;<sub>ik</sub>n<sub>i</sub></div>
      <p>平滑只用于显示，每条界面相对动态规划原路径最多移动1 px。</p>
    </div>
    <div class="formula">
      <strong>9. 病灶接触</strong>
      <div class="math">d<sub>i</sub>=min<sub>k</sub>D<sub>M</sub>(x<sub>ik</sub>), &nbsp; i*=argmin<sub>i</sub>d<sub>i</sub></div>
      <p><code>D_M</code>是病灶外距离变换。<code>d≤1 px</code>为接触，<code>1&lt;d≤6 px</code>为近接触，否则未建立接触。</p>
    </div>
    <div class="formula">
      <strong>10. 单帧临床门</strong>
      <div class="math">judgeable = contact &and; normal-reference &and; contact-visible</div>
      <p>正常侧前20%站位可靠率至少50%；接触点前后3站可靠率至少25%。任一门失败，默认逐层结论为 cannot judge。</p>
    </div>
    <div class="formula">
      <strong>11. 逐层像素连续性补充门</strong>
      <div class="math">R<sub>l</sub>=median(r<sub>il</sub>, i&isin;normal 20%), &nbsp; &rho;<sub>l</sub>=L<sub>l</sub>/R<sub>l</sub></div>
      <div class="math">pixel-break<sub>l</sub>=[R<sub>l</sub>&ge;10] &and; [L<sub>l</sub>&lt;0.4R<sub>l</sub> for 3 stations]</div>
      <p>即使四界面联合门偏低，只要某一层在左侧有强而连续的像素梯度参考，并在病灶侧突出部连续3站降至40%以下，该层仍保留“疑似中断”；其余层不跟随推断。</p>
    </div>
    <div class="formula">
      <strong>12. 逐界面病灶接触区间</strong>
      <div class="math">C<sub>l</sub>={{i:D<sub>M</sub>(x<sub>i,k(l)</sub>)&le;1 px}}</div>
      <p>分别计算黏膜、肌层和浆膜对应界面的连续接触区间。最终层标记使用本层接触入口，不再借用其他界面的全局最近点。</p>
    </div>
    <div class="formula">
      <strong>13. 层宽形变机制</strong>
      <div class="math">w<sub>il</sub>=e<sub>i,k+1</sub>-e<sub>ik</sub>, &nbsp; A<sub>l</sub>=w<sub>local,l</sub>/w<sub>normal,l</sub></div>
      <p>梯度消失支持pixel loss；梯度仍强但层宽显著收缩或扩张时，只标为可能的界面替代、融合或形变，不能写成已经证明的像素断裂。</p>
    </div>
  </section>

  <h2>核心实现代码</h2>
  <p class="code-note">以下片段直接对应 <code>scripts/render_wall_directional_interfaces.py</code> 的当前实现，省略了绘图和输入输出包装。</p>
  <h3>以当前病灶为中心外扩框并重新分割</h3>
  <pre><code>before_center = np.asarray((xs.mean(), ys.mean()), dtype=np.float32)
roi_w = max(72, int(np.ceil(lesion_w * 2.4)))
roi_h = max(48, int(np.ceil(lesion_h * 3.0)))
x1 = round(before_center[0] - roi_w / 2)
y1 = round(before_center[1] - roi_h / 2)
roi = crop[y1:y1 + roi_h, x1:x1 + roi_w]

model_mask = (segmenter.segment_crop(roi) &gt; 0).astype(np.uint8)
model_overlap = int((model_mask &gt; 0)[seed].sum())
minimum_overlap = max(20, int(original.sum() * 0.20))
if model_mask.sum() &gt; original.sum() * 1.05 and model_overlap &gt;= minimum_overlap:
    resegmented = model_mask
else:
    resegmented = _seeded_grabcut(roi, seed)

# Keep the component connected to the original lesion seed.
overlaps = [int(((labels == i) &amp; (original &gt; 0)).sum())
            for i in range(1, n_labels)]
selected = 1 + int(np.argmax(overlaps))</code></pre>

  <h3>沿法向采样和方向增强</h3>
  <pre><code>map_x = stations[:, 0, None] + normals[:, 0, None] * OFFSETS[None, :]
map_y = stations[:, 1, None] + normals[:, 1, None] * OFFSETS[None, :]
strip = cv2.remap(gray, map_x.astype(np.float32), map_y.astype(np.float32),
                  interpolation=cv2.INTER_LINEAR,
                  borderMode=cv2.BORDER_CONSTANT, borderValue=0)
enhanced = cv2.GaussianBlur(strip, (3, 9), sigmaX=0.65, sigmaY=1.8)</code></pre>

  <h3>四界面联合得分和Viterbi转移</h3>
  <pre><code>signed = np.asarray((phase, -phase, phase, -phase), dtype=np.float32)
responses = gradient[station, states] * signed[None, :]
strength = responses.min(axis=1)
score = responses.sum(axis=1) + 1.8 * strength
score -= 0.35 * np.abs(states - prior[None, :]).sum(axis=1)

delta = np.abs(previous[:, None, :] - current[None, :, :])
transition = costs[-1][:, None] + 3.5 * delta.sum(axis=2)
transition[delta.max(axis=2) &gt; 2.0] += 1.0e5</code></pre>

  <h3>置信度、完整轨迹和虚实线划分</h3>
  <pre><code>rolling = rolling_median(confidence, radius=3)
positive = rolling[rolling &gt; 0]
threshold = (4.0 if not len(positive)
             else np.clip(np.percentile(positive, 35) * 0.55, 3.0, 8.0))
edge_safe = (indices[:, 0] &gt;= 2) &amp; (indices[:, 3] &lt;= len(OFFSETS) - 3)
reliable = (rolling &gt;= threshold) &amp; edge_safe

# Each boundary also receives an independent display mask.
for boundary in range(4):
    boundary_rolling[:, boundary] = rolling_median(
        boundary_responses[:, boundary], radius=3)
    boundary_reliable[:, boundary] = (
        boundary_rolling[:, boundary] &gt;= boundary_thresholds[boundary]
    ) &amp; boundary_edge_safe[:, boundary]

# Keep every station. Only the rendering style changes.
full_paths = stations[:, None, :] + normals[:, None, :] * smooth_offsets[:, :, None]</code></pre>

  <h3>完整走行聚类填色</h3>
  <pre><code># Every physician-guided station receives a low-opacity cluster.
paint_band_polygon(overlay, full_paths, band, alpha=0.11)

# A band is strengthened where both adjacent interfaces are supported.
band_reliable = boundary_reliable[:, band] &amp; boundary_reliable[:, band + 1]
for start, stop in runs(band_reliable):
    paint_band_polygon(overlay, full_paths[start:stop + 1], band, alpha=0.18)</code></pre>

  <h3>医生式逐层判断门</h3>
  <pre><code>reference_status = "established" if reference_fraction &gt;= 0.5 else "limited"
contact_visibility = ("visible" if contact_fraction &gt;= 0.6
                      else "partly_visible" if contact_fraction &gt;= 0.25
                      else "unseen")
analysis_gate = (relation == "not_established"
                 or reference_status == "limited"
                 or contact_visibility == "unseen")
if analysis_gate:
    verdicts = dict.fromkeys(("mucosa", "muscularis", "serosa"),
                             "cannot_judge")

# A strong layer-specific normal reference can rescue only that layer.
if reference_strength &gt;= 10.0 and break_run &gt;= 3 and local_strength &lt; 0.4 * reference_strength:
    verdicts[layer_id] = "suspected_interrupt"</code></pre>

  <h2>参数与代码入口</h2>
  <table>
    <thead><tr><th>Parameter / function</th><th>Current value</th><th>Role</th></tr></thead>
    <tbody>
      <tr><td><code>_expand_p008_lesion</code></td><td>width max(72, 2.4x); height max(48, 3.0x)</td><td>以当前病灶质心为中心外扩框，并在新ROI内重新分割</td></tr>
      <tr><td><code>_seeded_grabcut</code></td><td>6 iterations; hard foreground seed</td><td>模型扩框重分割不合格时的像素级回退</td></tr>
      <tr><td><code>OFFSETS</code></td><td>-24...24 px</td><td>每个站位的法向搜索范围</td></tr>
      <tr><td><code>_interface_states</code></td><td>3...8 px spacing</td><td>四界面有序候选及层宽约束</td></tr>
      <tr><td><code>_track_interfaces</code></td><td>top-k = 80</td><td>保留每站最高分候选并执行联合动态规划</td></tr>
      <tr><td><code>_smooth_offsets</code></td><td>kernel [1,4,6,4,1]/16; max shift 1 px</td><td>仅平滑显示轨迹</td></tr>
      <tr><td><code>_analyze_full_trajectory</code></td><td>contact 1 px; near contact 6 px</td><td>保留完整轨迹并划分可靠、低置信和接触区</td></tr>
      <tr><td><code>_build_clinical_reasoning</code></td><td>normal 50%; contact 25% / 60%</td><td>正常参考、接触可见度、逐层消失和安全门</td></tr>
      <tr><td><code>render_case</code></td><td>per-interface solid path; break radius 5...8 stations</td><td>逐界面延长像素支持线，并在源图和展开条带上高亮疑似突破区段</td></tr>
    </tbody>
  </table>

  {p008_section}

  <h2>突破分析如何融合到test-time判断</h2>
  <p class="warning"><strong>当前状态：</strong>本报告中的最终疑似突破层仍部分参考
  <code>curated_lines_v1.json</code>内的层间断记录或医生印象，因此只能用于方法验证和可视化，
  不能直接作为test-time模型输入。正式推理必须切断这些记录，只保留当次图像、模型病灶分割、
  当次胃壁画线和自动提取的像素连续性证据。</p>

  <h3>1. Test-time数据边界与泄漏防火墙</h3>
  <table>
    <thead><tr><th>Signal</th><th>Test-time可用性</th><th>处理原则</th></tr></thead>
    <tbody>
      <tr><td>当次超声图像</td><td>可用</td><td>所有灰度、梯度和纹理证据必须来自当前输入</td></tr>
      <tr><td>模型病灶分割</td><td>可用</td><td>必须是当次推理输出；不得使用GT病灶掩膜</td></tr>
      <tr><td>医生当次胃壁画线</td><td>交互模式可用</td><td>只作空间和方向先验，不直接代表连续或突破</td></tr>
      <tr><td>自动四界面路径</td><td>可用</td><td>保留原像素响应、可靠性、接触距离和不确定区间</td></tr>
      <tr><td>保存的间断点、层verdict</td><td>禁止</td><td>当前仅用于回顾性核对；正式推理必须由自动扫描替代</td></tr>
      <tr><td>医生T1等印象、病理pT</td><td>禁止</td><td>只能作为训练标签或独立评估终点，不能进入输入特征</td></tr>
    </tbody>
  </table>

  <h3>2. 自动突破候选，不读取人工间断点</h3>
  <div class="formula-grid">
    <div class="formula">
      <strong>T1. 正常侧逐层参考</strong>
      <div class="math">R<sub>l</sub>=median{{r<sub>il</sub>:i&isin;normal-side, reliable<sub>i</sub>=1}}</div>
      <p>对黏膜、肌层、浆膜分别建立参考，不能用四条边的总体置信度替代某一层的连续性。</p>
    </div>
    <div class="formula">
      <strong>T2. 全轨迹自动断点扫描</strong>
      <div class="math">D<sub>l</sub>(j)=clip(1-L<sub>l</sub>(j)/R<sub>l</sub>,0,1) P<sub>l</sub>(j) exp(-d<sub>j</sub>/&tau;)</div>
      <div class="math">j*<sub>l</sub>=argmax<sub>j&isin;normal&rarr;lesion</sub>D<sub>l</sub>(j)</div>
      <p><code>L_l(j)</code>是候选点附近的局部中位梯度，<code>P_l</code>是低响应持续长度，
      <code>d_j</code>是到病灶的距离。候选点完全由当前像素产生。</p>
    </div>
    <div class="formula">
      <strong>T3. 证据质量</strong>
      <div class="math">q=(q<sub>axis</sub>q<sub>seg</sub>q<sub>ref</sub>q<sub>contact</sub>)<sup>1/4</sup></div>
      <p>走行异常、病灶分割不稳、缺少正常壁参考或没有接触时，质量乘积会主动压低突破证据。</p>
    </div>
    <div class="formula">
      <strong>T4. 逐层突破证据</strong>
      <div class="math">b<sub>l</sub>=q D<sub>l</sub>(j*<sub>l</sub>)</div>
      <p>输出连续值而不是直接给分期；建议同时输出候选站位、参考强度、局部强度、持续长度和不确定性。</p>
    </div>
  </div>

  <h3>3. 建议的test-time特征向量</h3>
  <pre><code>evidence = [
    axis_quality,
    lesion_segmentation_quality,
    normal_reference_quality,
    contact_visibility,
    contact_distance_px,
    reliable_fraction,
    uncertain_fraction,
    mucosa_break_score,
    muscularis_break_score,
    serosa_break_score,
    mucosa_break_position_normalized,
    muscularis_break_position_normalized,
    serosa_break_position_normalized,
]</code></pre>
  <p>其中质量、距离和不确定性必须与突破分数一起进入融合层。只传三个
  <code>break_score</code>会让低质量图像产生过度自信。</p>

  <h3>4. 与基础T分期模型的推荐融合</h3>
  <div class="formula-grid">
    <div class="formula">
      <strong>T5. 冻结基础模型后的序数校准</strong>
      <div class="math">a'<sub>k</sub>=a<sub>k</sub><sup>base</sup>+&beta;<sub>k</sub><sup>T</sup>e, &nbsp; k=1,2,3</div>
      <div class="math">P(T&ge;k|x,e)=sigmoid(a'<sub>k</sub>)</div>
      <p>对“至少达到某深度”的累积概率做校准，比手写“黏膜断=T1、浆膜断=T4”更稳健。
      <code>&beta;</code>只能在患者级训练/验证集上学习。</p>
    </div>
    <div class="formula">
      <strong>T6. 质量门控融合</strong>
      <div class="math">a'<sub>k</sub>=a<sub>k</sub><sup>base</sup>+g(q)&beta;<sub>k</sub><sup>T</sup>e<sub>break</sub></div>
      <div class="math">g(q)=0 if q&lt;q<sub>low</sub>; &nbsp; g(q)&isin;(0,1) otherwise</div>
      <p>低质量时完全退回基础模型；中等质量只作有限校准；高质量才允许突破证据完整参与。</p>
    </div>
  </div>

  <h3>5. 无泄漏test-time伪代码</h3>
  <pre><code>base_logits = stage_model(image)
lesion_mask, seg_quality = lesion_model(image, lesion_box)
interfaces = track_wall_interfaces(image, wall_stroke)

# Scan every layer on current pixels. No curated gap or physician verdict.
break_evidence = auto_scan_layer_breaks(
    interfaces=interfaces,
    lesion_mask=lesion_mask,
    normal_side=interfaces.clear_side,
)
features = build_quality_aware_features(interfaces, lesion_mask, break_evidence)

if features.quality &lt; frozen_abstention_threshold:
    final_logits = base_logits
    wall_output = "cannot_judge"
else:
    final_logits = ordinal_calibrator(base_logits, features)
    wall_output = break_evidence.single_frame_label

return calibrated_stage_probabilities(final_logits), wall_output, features.audit_trail</code></pre>

  <h3>6. 上线前验证顺序</h3>
  <ol>
    <li><strong>Shadow mode：</strong>先只记录自动突破特征，不改变现有模型结论。</li>
    <li><strong>患者级OOF特征：</strong>用训练折外预测生成基础logit和突破特征，避免校准器看到训练内预测。</li>
    <li><strong>消融实验：</strong>比较基础模型、基础模型加接触特征、基础模型加逐层突破、完整质量门控融合。</li>
    <li><strong>冻结阈值：</strong>在独立验证集确定质量门和弃权阈值，测试集只评估一次。</li>
    <li><strong>评价指标：</strong>除accuracy外报告macro-F1、weighted kappa、分层敏感度、校准误差和弃权后的覆盖率。</li>
    <li><strong>视频扩展：</strong>若有连续帧，先对突破分数作时序一致性聚合，再进入融合层；单帧闪断不得升级为确定突破。</li>
  </ol>

  <h2>四例结果</h2>
  <figure class="overview">
    <img src="{html.escape(index.name)}" alt="Four-case wall interface comparison">
    <figcaption>Four-case comparison of pixel-aligned wall interfaces.</figcaption>
  </figure>
  {''.join(case_sections)}

  <h2>当前结论与限制</h2>
  <ul>
    <li>图中现在显示完整走行轨迹。实线是当前像素支持的界面，虚线是低置信延续，不能被解释为胃壁仍然连续。</li>
    <li>绿色标记是正常胃壁参考侧；蓝色空心点是病灶最近接触点；红色光晕、白色叉号和红框共同标记疑似层消失位置。</li>
    <li>P008按医生修正记录为胃壁整体较完整、第一层异常；T1是医生判断，不是本算法自动输出的确定cT。</li>
    <li>P076以左侧连续胃壁作为正常像素参考，沿走行追踪至右侧突出部；右侧黏膜界面梯度持续下降的位置标记为疑似中断。</li>
    <li>P019若当前帧没有建立稳定正常壁参考或可分析接触区，即使存储记录存在层间断，也不升级为突破。</li>
    <li>边缘置信度只说明灰度跃迁强度，不能自动证明对应黏膜、固有肌层或浆膜。</li>
    <li>后续如引入AI，优先训练原分辨率边界网络或视频时序模型，不直接使用低分辨率通用特征替代像素边界。</li>
  </ul>
</main>
</body>
</html>
"""
    dest = out_dir / "wall_interface_algorithm_summary.html"
    dest.write_text(document, encoding="utf-8")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="", help="Case ID or display ID")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    selector = args.case.strip().upper()
    segmenter = RoiSegmenter()
    panels: list[Path] = []
    summaries: list[dict] = []
    for meta_path in sorted(Path(DEFAULT_FIXTURES).glob("CASE-*/meta.json")):
        meta = load_meta(meta_path)
        case_id = str(meta["case_id"]).upper()
        display_id = str(meta["display_id"]).upper()
        if selector and selector not in {case_id, display_id}:
            continue
        pack = prepare_crop(meta, segmenter)
        if case_id == "CASE-008":
            pack = _expand_p008_lesion(pack, segmenter)
        track = track_case(pack)
        track["invasion"] = _build_clinical_reasoning(case_id, track)
        panel = render_case(pack, track, args.out_dir)
        panels.append(panel)
        summary = {
            "case_id": case_id,
            "display_id": display_id,
            "heading_source": track["heading_source"],
            "cavity_side_source": track.get("cavity_side_source"),
            "pattern": "bright-dark-bright" if track["phase"] > 0 else "dark-bright-dark",
            "retained_stations": len(track["stations"]),
            "reliable_stations": track["reliable_station_count"],
            "reliable_fraction": round(
                track["reliable_station_count"] / max(1, len(track["stations"])),
                3,
            ),
            "boundary_reliable_counts": [
                int(value) for value in track["boundary_reliable_counts"]
            ],
            "uncertain_runs": track["uncertain_runs"],
            "median_edge_confidence": round(float(np.median(track["confidence"])), 2),
            "relation": track["relation"],
            "contact_distance_px": round(float(track["contact_distance_px"]), 2),
            "invasion": track["invasion"],
            "panel": str(panel),
        }
        if pack.get("lesion_adjustment"):
            summary["lesion_adjustment"] = pack["lesion_adjustment"]
        summaries.append(summary)
    if selector and not summaries:
        raise SystemExit(f"unknown case selector: {args.case}")
    index = render_index(panels, args.out_dir) if len(panels) > 1 else None
    html_path = render_html_summary(summaries, index, args.out_dir) if index is not None else None
    print(json.dumps({
        "cases": summaries,
        "index": str(index) if index else None,
        "html": str(html_path) if html_path else None,
    }, indent=2))


if __name__ == "__main__":
    main()
