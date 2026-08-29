#!/usr/bin/env python3
"""Compare direction-enhanced joint dark-bright-dark tracking on four cases.

This is an offline method probe, not an annotation export and not a cT reader.

  python3 scripts/render_wall_directional_joint_bands.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from render_wall_layer_thin_bands import (  # noqa: E402
    DEFAULT_FIXTURES,
    RoiSegmenter,
    load_meta,
)
from render_wall_pixel_vs_dino_cluster import prepare_crop  # noqa: E402
from wall_ordered_curve_track import _smooth_wall_stations, polygon_centroid  # noqa: E402

DEFAULT_OUT = ROOT / "results/visualizations/error_cases/directional_joint_bands"
OFFSETS = np.arange(-18, 19, dtype=np.float32)
COLORS = {
    "dark1": "#facc15",
    "bright": "#38bdf8",
    "dark2": "#f472b6",
}

plt.rcParams.update({
    "font.family": "Times New Roman",
    "font.size": 10,
    "axes.facecolor": "black",
    "figure.facecolor": "black",
    "savefig.facecolor": "black",
    "text.color": "white",
})


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


def _candidate_states() -> np.ndarray:
    states: list[tuple[int, int, int]] = []
    for bright in range(8, 29):
        for gap1 in range(4, 12):
            for gap2 in range(4, 12):
                dark1 = bright - gap1
                dark2 = bright + gap2
                if dark1 >= 0 and dark2 < len(OFFSETS):
                    states.append((dark1, bright, dark2))
    return np.asarray(states, dtype=np.int16)


def _joint_track(enhanced: np.ndarray, valid: np.ndarray) -> dict:
    """Jointly track three ordered bands with direction and spacing costs."""
    states = _candidate_states()
    station_count = enhanced.shape[0]
    tangent_change = np.abs(
        cv2.Sobel(enhanced, cv2.CV_32F, 0, 1, ksize=3, scale=0.25)
    )
    top_k = min(72, len(states))
    selected: list[np.ndarray] = []
    unary_costs: list[np.ndarray] = []
    local_contrast: list[np.ndarray] = []

    for index in range(station_count):
        d1, bright, d2 = states.T
        v1 = enhanced[index, d1]
        vb = enhanced[index, bright]
        v2 = enhanced[index, d2]
        contrast = np.minimum(vb - v1, vb - v2)
        asymmetry = np.abs((vb - v1) - (vb - v2))
        direction_penalty = (
            tangent_change[index, d1]
            + tangent_change[index, bright]
            + tangent_change[index, d2]
        ) / 3.0
        center_penalty = 0.20 * np.abs(OFFSETS[bright] - 2.0)
        invalid = ~(valid[index, d1] & valid[index, bright] & valid[index, d2])
        score = contrast - 0.12 * asymmetry - 0.12 * direction_penalty - center_penalty
        score[invalid] = -1.0e6
        keep = np.argpartition(score, -top_k)[-top_k:]
        keep = keep[np.argsort(-score[keep])]
        selected.append(keep)
        unary_costs.append(-score[keep])
        local_contrast.append(contrast[keep])

    costs: list[np.ndarray] = []
    backs: list[np.ndarray] = []
    for index, keep in enumerate(selected):
        unary = unary_costs[index]
        if index == 0:
            costs.append(unary)
            backs.append(np.full(len(keep), -1, dtype=np.int16))
            continue
        current = states[keep].astype(np.float32)
        previous = states[selected[index - 1]].astype(np.float32)
        shift = np.abs(previous[:, None, :] - current[None, :, :]).sum(axis=2)
        max_component_shift = np.abs(
            previous[:, None, :] - current[None, :, :]
        ).max(axis=2)
        old_widths = previous[:, 2] - previous[:, 0]
        new_widths = current[:, 2] - current[:, 0]
        width_change = np.abs(old_widths[:, None] - new_widths[None, :])
        transition = costs[-1][:, None] + 4.0 * shift + 1.2 * width_change
        transition[max_component_shift > 2.0] += 1.0e5
        back = np.argmin(transition, axis=0)
        costs.append(unary + transition[back, np.arange(len(keep))])
        backs.append(back.astype(np.int16))

    cursor = int(np.argmin(costs[-1]))
    chosen: list[int] = []
    contrasts: list[float] = []
    for index in range(station_count - 1, -1, -1):
        chosen.append(int(selected[index][cursor]))
        contrasts.append(float(local_contrast[index][cursor]))
        if index:
            cursor = int(backs[index][cursor])
    path = states[np.asarray(chosen[::-1], dtype=np.int32)]
    return {
        "indices": path,
        "offsets": OFFSETS[path],
        "contrast": np.asarray(contrasts[::-1], dtype=np.float32),
    }


def _rolling_median(values: np.ndarray, radius: int = 3) -> np.ndarray:
    return np.asarray([
        np.median(values[max(0, i - radius) : min(len(values), i + radius + 1)])
        for i in range(len(values))
    ], dtype=np.float32)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    padded = np.pad(mask.astype(np.int8), (1, 1))
    changes = np.diff(padded)
    starts = np.where(changes == 1)[0]
    ends = np.where(changes == -1)[0] - 1
    return list(zip(starts.tolist(), ends.tolist()))


def _select_reliable_segment(
    contrast: np.ndarray,
    stations: np.ndarray,
    lesion_mask: np.ndarray,
) -> tuple[slice, float]:
    rolling = _rolling_median(contrast)
    positive = rolling[rolling > 0]
    threshold = 15.0 if not len(positive) else float(np.clip(np.percentile(positive, 35) * 0.55, 12.0, 20.0))
    reliable = rolling >= threshold
    runs = [(start, end) for start, end in _runs(reliable) if end - start + 1 >= 8]
    if not runs:
        best = int(np.argmax(rolling))
        return slice(max(0, best - 4), min(len(rolling), best + 5)), threshold

    if lesion_mask.any():
        outside = (lesion_mask == 0).astype(np.uint8)
        distance = cv2.distanceTransform(outside, cv2.DIST_L2, 3)
        xy = np.rint(stations).astype(np.int32)
        xy[:, 0] = np.clip(xy[:, 0], 0, lesion_mask.shape[1] - 1)
        xy[:, 1] = np.clip(xy[:, 1], 0, lesion_mask.shape[0] - 1)
        station_distance = distance[xy[:, 1], xy[:, 0]]
    else:
        station_distance = np.full(len(stations), 20.0, dtype=np.float32)

    def run_score(run: tuple[int, int]) -> float:
        start, end = run
        length = end - start + 1
        proximity = float(np.min(station_distance[start : end + 1]))
        return length - 0.35 * proximity

    start, end = max(runs, key=run_score)
    return slice(start, end + 1), threshold


def _smooth_offsets(offsets: np.ndarray) -> np.ndarray:
    kernel = np.asarray([1, 4, 6, 4, 1], dtype=np.float32) / 16.0
    result = np.empty_like(offsets, dtype=np.float32)
    for column in range(offsets.shape[1]):
        raw = offsets[:, column]
        smooth = np.convolve(np.pad(raw, (2, 2), mode="edge"), kernel, mode="valid")
        result[:, column] = np.clip(smooth, raw - 1.0, raw + 1.0)
    return result


def track_case(pack: dict) -> dict:
    gray = cv2.cvtColor(pack["crop"], cv2.COLOR_BGR2GRAY)
    wall = np.asarray(pack["wall_crop"], dtype=np.float32)
    raw_lesion = pack.get("lesion_poly")
    lesion = np.asarray(
        raw_lesion if raw_lesion is not None else [],
        dtype=np.float32,
    ).reshape(-1, 2)
    lesion_center = polygon_centroid(lesion)
    deepest = None
    if lesion_center is not None and len(lesion):
        deepest = lesion[int(np.argmax(np.linalg.norm(lesion - lesion_center, axis=1)))]
    stations, normals = _smooth_wall_stations(wall, None, lesion_center, deepest)
    if len(stations) < 12:
        raise ValueError("wall heading has fewer than 12 usable stations")
    steps = np.diff(stations, axis=0)
    arc_length = float(np.linalg.norm(steps, axis=1).sum())
    chord = float(np.linalg.norm(stations[-1] - stations[0]))
    tortuosity = arc_length / max(chord, 1.0)
    unit = steps / np.maximum(np.linalg.norm(steps, axis=1, keepdims=True), 1.0e-6)
    turns = np.degrees(np.arccos(np.clip((unit[:-1] * unit[1:]).sum(axis=1), -1.0, 1.0)))
    max_turn = float(turns.max()) if len(turns) else 0.0
    if tortuosity > 2.5 or max_turn > 60.0:
        return {
            "status": "invalid_heading",
            "stations": stations,
            "tortuosity": tortuosity,
            "max_turn": max_turn,
        }

    strip, _map_x, _map_y = _sample_strip(gray, stations, normals)
    # In the unwrapped wall, rows follow the wall tangent and columns follow
    # the local normal. A long tangent kernel suppresses speckle while keeping
    # narrow across-wall dark/bright transitions.
    enhanced = cv2.GaussianBlur(strip, (3, 9), sigmaX=0.65, sigmaY=1.8)
    valid = strip > 0
    joint = _joint_track(enhanced, valid)
    edge_safe = (
        (joint["indices"][:, 0] >= 2)
        & (joint["indices"][:, 2] <= len(OFFSETS) - 3)
    )
    reliable_contrast = joint["contrast"].copy()
    reliable_contrast[~edge_safe] = -1.0e6
    selection, threshold = _select_reliable_segment(
        reliable_contrast, stations, (pack["crop_mask"] > 0).astype(np.uint8),
    )
    stations = stations[selection]
    normals = normals[selection]
    offsets = joint["offsets"][selection]
    smooth_offsets = _smooth_offsets(offsets)
    paths = stations[:, None, :] + normals[:, None, :] * smooth_offsets[:, :, None]
    return {
        "status": "ok",
        "stations": stations,
        "normals": normals,
        "strip": strip[selection],
        "enhanced": enhanced[selection],
        "offsets": offsets,
        "smooth_offsets": smooth_offsets,
        "paths": paths,
        "contrast": joint["contrast"][selection],
        "threshold": threshold,
    }


def _draw_paths(ax, paths: np.ndarray, linewidth: float) -> None:
    for index, key in enumerate(("dark1", "bright", "dark2")):
        ax.plot(
            paths[:, index, 0],
            paths[:, index, 1],
            color=COLORS[key],
            linewidth=linewidth,
            solid_capstyle="round",
            solid_joinstyle="round",
            zorder=5,
        )


def render_case(pack: dict, track: dict, out_dir: Path) -> Path:
    meta = pack["meta"]
    rgb = cv2.cvtColor(pack["crop"], cv2.COLOR_BGR2RGB)
    context = rgb.copy()
    mask = (pack["crop_mask"] > 0).astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(context, contours, -1, (191, 219, 254), 1, cv2.LINE_AA)

    fig, axes = plt.subplots(1, 2, figsize=(13.0, 5.6), gridspec_kw={"width_ratios": [1.08, 1.0]})
    axes[0].imshow(context, interpolation="nearest")
    if track["status"] == "ok":
        _draw_paths(axes[0], track["paths"], 1.15)
        axes[0].set_title("A  Direction-enhanced joint paths", fontsize=12)
    else:
        wall = np.asarray(pack["wall_crop"], dtype=np.float32)
        axes[0].plot(wall[:, 0], wall[:, 1], color="#fb7185", linewidth=1.0, alpha=0.8)
        axes[0].set_title("A  Rejected wall heading", fontsize=12)
    axes[0].axis("off")

    if track["status"] == "ok":
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
        for index, key in enumerate(("dark1", "bright", "dark2")):
            axes[1].plot(
                station_axis,
                track["smooth_offsets"][:, index],
                color=COLORS[key],
                linewidth=1.2,
                solid_capstyle="round",
            )
        axes[1].set_title("B  Wall-unwrapped source pixels", fontsize=12)
        axes[1].set_xlabel("Wall station")
        axes[1].set_ylabel("Normal offset (px)")
        axes[1].tick_params(colors="#d1d5db", labelsize=8)
    else:
        axes[1].text(
            0.5,
            0.58,
            "Tracking rejected",
            ha="center",
            va="center",
            fontsize=18,
            color="#fda4af",
            transform=axes[1].transAxes,
        )
        axes[1].text(
            0.5,
            0.43,
            f"Heading tortuosity={track['tortuosity']:.2f}\n"
            f"Maximum local turn={track['max_turn']:.1f}°",
            ha="center",
            va="center",
            fontsize=11,
            color="#d1d5db",
            transform=axes[1].transAxes,
        )
        axes[1].set_title("B  Input quality gate", fontsize=12)
        axes[1].axis("off")

    handles = [
        Line2D([0], [0], color=COLORS[key], lw=2, label=label)
        for key, label in (
            ("dark1", "Dark band 1"),
            ("bright", "Bright band"),
            ("dark2", "Dark band 2"),
        )
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=3,
        frameon=False,
        labelcolor="white",
        fontsize=9,
        bbox_to_anchor=(0.5, 0.025),
    )
    median_contrast = (
        float(np.median(track["contrast"]))
        if track["status"] == "ok"
        else float("nan")
    )
    fig.suptitle(
        f"{meta['display_id']}  Direction-aware joint three-band probe",
        fontsize=14,
        y=0.985,
    )
    detail = (
        f"Retained stations={len(track['stations'])}; median minimum contrast={median_contrast:.1f}; "
        f"stop threshold={track['threshold']:.1f}"
        if track["status"] == "ok"
        else "No bands emitted: the stored heading is a self-crossing scribble, not a valid wall trajectory."
    )
    fig.text(0.5, 0.09, detail, ha="center", color="#d1d5db", fontsize=9)
    fig.tight_layout(rect=[0.01, 0.14, 0.99, 0.94])
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{meta['case_id']}_directional_joint_bands.png"
    fig.savefig(dest, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return dest


def render_index(paths: list[Path], out_dir: Path) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(16.0, 10.6))
    for ax, path in zip(axes.flat, paths):
        ax.imshow(plt.imread(path))
        ax.axis("off")
    fig.suptitle("Four-case direction-aware joint three-band probe", fontsize=16, y=0.995)
    fig.tight_layout(pad=0.7)
    dest = out_dir / "wall_directional_joint_bands_4cases.png"
    fig.savefig(dest, dpi=170, bbox_inches="tight")
    plt.close(fig)
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
        track = track_case(pack)
        panel = render_case(pack, track, args.out_dir)
        panels.append(panel)
        summary = {
            "case_id": case_id,
            "display_id": display_id,
            "status": track["status"],
            "panel": str(panel),
        }
        if track["status"] == "ok":
            summary.update({
                "retained_stations": len(track["stations"]),
                "median_contrast": round(float(np.median(track["contrast"])), 2),
            })
        else:
            summary.update({
                "tortuosity": round(float(track["tortuosity"]), 2),
                "max_turn": round(float(track["max_turn"]), 2),
            })
        summaries.append(summary)
    if selector and not summaries:
        raise SystemExit(f"unknown case selector: {args.case}")
    index = render_index(panels, args.out_dir) if len(panels) > 1 else None
    print(json.dumps({"cases": summaries, "index": str(index) if index else None}, indent=2))


if __name__ == "__main__":
    main()
