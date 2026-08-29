#!/usr/bin/env python3
"""Track four wall interfaces and render the three intervening pixel bands.

This offline probe uses a clean P008 local-axis fallback because its stored
heading is a self-crossing scribble. Outputs require clinical review.
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

from render_wall_directional_joint_bands import (  # noqa: E402
    _rolling_median,
    _runs,
    _smooth_offsets,
)
from render_wall_layer_thin_bands import DEFAULT_FIXTURES, RoiSegmenter, load_meta  # noqa: E402
from render_wall_pixel_vs_dino_cluster import prepare_crop  # noqa: E402
from wall_ordered_curve_track import _smooth_wall_stations, polygon_centroid  # noqa: E402

CURATION = ROOT / "pipeline/data/wall_layer_fixtures/v1/curated_lines_v1.json"
DEFAULT_OUT = ROOT / "results/visualizations/error_cases/directional_interfaces"
OFFSETS = np.arange(-24, 25, dtype=np.float32)
BOUNDARY_COLORS = ("#fde047", "#38bdf8", "#f472b6", "#4ade80")
BAND_COLORS = (
    np.asarray((250, 204, 21), dtype=np.float32),
    np.asarray((56, 189, 248), dtype=np.float32),
    np.asarray((244, 114, 182), dtype=np.float32),
)

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


def _fallback_axis(case_id: str) -> np.ndarray:
    curation = json.loads(CURATION.read_text(encoding="utf-8"))
    layers = curation["cases"][case_id]["layers"]
    controls = [
        np.asarray(layers[key]["segments"][0], dtype=np.float32)
        for key in ("mucosa", "muscularis", "serosa")
    ]
    return np.mean(np.stack(controls), axis=0).astype(np.float32)


def _wall_axis(pack: dict) -> tuple[np.ndarray, np.ndarray, str]:
    lesion = np.asarray(pack["lesion_poly"], dtype=np.float32).reshape(-1, 2)
    lesion_center = polygon_centroid(lesion)
    deepest = None
    if lesion_center is not None and len(lesion):
        deepest = lesion[int(np.argmax(np.linalg.norm(lesion - lesion_center, axis=1)))]
    wall = np.asarray(pack["wall_crop"], dtype=np.float32)
    stations, normals = _smooth_wall_stations(wall, None, lesion_center, deepest)
    tortuosity, max_turn = _heading_metrics(stations)
    source = "stored heading"
    if tortuosity > 2.5 or max_turn > 60.0:
        case_id = str(pack["meta"]["case_id"])
        stations, normals = _smooth_wall_stations(
            _fallback_axis(case_id), None, lesion_center, deepest,
        )
        source = "clean local-axis fallback"
    return stations, normals, source


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


def _select_phase_and_prior(enhanced: np.ndarray, states: np.ndarray) -> tuple[int, np.ndarray]:
    median_profile = np.median(enhanced, axis=0)
    gradient = cv2.Sobel(
        median_profile.reshape(1, -1),
        cv2.CV_32F,
        1,
        0,
        ksize=3,
        scale=0.25,
    ).reshape(-1)
    best: tuple[float, int, np.ndarray] | None = None
    for phase in (1, -1):
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


def _track_interfaces(enhanced: np.ndarray, valid: np.ndarray) -> dict:
    states_all = _interface_states()
    phase, prior = _select_phase_and_prior(enhanced, states_all)
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
    return {
        "indices": indices,
        "offsets": OFFSETS[indices],
        "confidence": np.asarray(confidence[::-1], dtype=np.float32),
        "phase": phase,
        "prior_offsets": OFFSETS[prior],
    }


def _reliable_slice(track: dict) -> tuple[slice, float]:
    rolling = _rolling_median(track["confidence"], radius=3)
    positive = rolling[rolling > 0]
    threshold = 4.0 if not len(positive) else float(
        np.clip(np.percentile(positive, 35) * 0.55, 3.0, 8.0)
    )
    indices = track["indices"]
    edge_safe = (indices[:, 0] >= 2) & (indices[:, 3] <= len(OFFSETS) - 3)
    reliable = (rolling >= threshold) & edge_safe
    runs = [(start, end) for start, end in _runs(reliable) if end - start + 1 >= 8]
    if not runs:
        best = int(np.argmax(rolling))
        return slice(max(0, best - 4), min(len(rolling), best + 5)), threshold
    start, end = max(runs, key=lambda item: item[1] - item[0])
    return slice(start, end + 1), threshold


def track_case(pack: dict) -> dict:
    gray = cv2.cvtColor(pack["crop"], cv2.COLOR_BGR2GRAY)
    stations, normals, heading_source = _wall_axis(pack)
    strip, _map_x, _map_y = _sample_strip(gray, stations, normals)
    enhanced = cv2.GaussianBlur(strip, (3, 9), sigmaX=0.65, sigmaY=1.8)
    track = _track_interfaces(enhanced, strip > 0)
    selection, threshold = _reliable_slice(track)
    stations = stations[selection]
    normals = normals[selection]
    offsets = track["offsets"][selection]
    smooth_offsets = _smooth_offsets(offsets)
    paths = stations[:, None, :] + normals[:, None, :] * smooth_offsets[:, :, None]
    return {
        "stations": stations,
        "strip": strip[selection],
        "offsets": offsets,
        "smooth_offsets": smooth_offsets,
        "paths": paths,
        "confidence": track["confidence"][selection],
        "threshold": threshold,
        "phase": track["phase"],
        "heading_source": heading_source,
    }


def _paint_three_bands(rgb: np.ndarray, paths: np.ndarray) -> np.ndarray:
    overlay = rgb.astype(np.float32).copy()
    for band in range(3):
        polygon = np.vstack([
            paths[:, band, :],
            paths[::-1, band + 1, :],
        ])
        polygon = np.rint(polygon).astype(np.int32)
        mask = np.zeros(rgb.shape[:2], dtype=np.uint8)
        cv2.fillPoly(mask, [polygon], 255, lineType=cv2.LINE_AA)
        take = mask > 0
        overlay[take] = 0.86 * overlay[take] + 0.14 * BAND_COLORS[band]
    return np.clip(overlay, 0, 255).astype(np.uint8)


def _draw_interfaces(ax, paths: np.ndarray, linewidth: float) -> None:
    for boundary in range(4):
        ax.plot(
            paths[:, boundary, 0],
            paths[:, boundary, 1],
            color=BOUNDARY_COLORS[boundary],
            linewidth=linewidth,
            solid_capstyle="round",
            solid_joinstyle="round",
            zorder=6,
        )


def render_case(pack: dict, track: dict, out_dir: Path) -> Path:
    meta = pack["meta"]
    rgb = cv2.cvtColor(pack["crop"], cv2.COLOR_BGR2RGB)
    panel = _paint_three_bands(rgb, track["paths"])
    mask = (pack["crop_mask"] > 0).astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(panel, contours, -1, (191, 219, 254), 1, cv2.LINE_AA)

    fig, axes = plt.subplots(1, 2, figsize=(13.0, 5.6), gridspec_kw={"width_ratios": [1.08, 1.0]})
    axes[0].imshow(panel, interpolation="nearest")
    _draw_interfaces(axes[0], track["paths"], 1.0)
    axes[0].set_title("A  Four pixel-aligned interfaces", fontsize=12)
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
    for boundary in range(4):
        axes[1].plot(
            station_axis,
            track["smooth_offsets"][:, boundary],
            color=BOUNDARY_COLORS[boundary],
            linewidth=1.1,
            solid_capstyle="round",
        )
    axes[1].set_title("B  Magnified wall-normal boundaries", fontsize=12)
    axes[1].set_xlabel("Wall station")
    axes[1].set_ylabel("Normal offset (px)")
    axes[1].tick_params(colors="#d1d5db", labelsize=8)

    handles = [
        Line2D([0], [0], color=color, lw=2, label=f"Boundary {index + 1}")
        for index, color in enumerate(BOUNDARY_COLORS)
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=4,
        frameon=False,
        labelcolor="white",
        fontsize=9,
        bbox_to_anchor=(0.5, 0.025),
    )
    pattern = "bright-dark-bright" if track["phase"] > 0 else "dark-bright-dark"
    fig.suptitle(
        f"{meta['display_id']}  Joint interface tracking",
        fontsize=14,
        y=0.985,
    )
    fig.text(
        0.5,
        0.09,
        f"{track['heading_source']}; {pattern}; retained stations={len(track['stations'])}; "
        f"median edge confidence={np.median(track['confidence']):.1f}",
        ha="center",
        color="#d1d5db",
        fontsize=9,
    )
    fig.tight_layout(rect=[0.01, 0.14, 0.99, 0.94])
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
        summaries.append({
            "case_id": case_id,
            "display_id": display_id,
            "heading_source": track["heading_source"],
            "pattern": "bright-dark-bright" if track["phase"] > 0 else "dark-bright-dark",
            "retained_stations": len(track["stations"]),
            "median_edge_confidence": round(float(np.median(track["confidence"])), 2),
            "panel": str(panel),
        })
    if selector and not summaries:
        raise SystemExit(f"unknown case selector: {args.case}")
    index = render_index(panels, args.out_dir) if len(panels) > 1 else None
    print(json.dumps({"cases": summaries, "index": str(index) if index else None}, indent=2))


if __name__ == "__main__":
    main()
