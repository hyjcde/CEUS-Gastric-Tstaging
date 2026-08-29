#!/usr/bin/env python3
"""Render record-assisted, manually curated wall-layer lines for four fixtures.

The line coordinates are review drafts, not pixel ground truth. Stored layer
ticks control the displayed verdicts; no pT label is used to place a line.

  python3 scripts/render_wall_curated_layers.py --index
  python3 scripts/render_wall_curated_layers.py --case P040
  python3 scripts/render_wall_curated_layers.py --p040-pixels
  python3 scripts/render_wall_curated_layers.py --validate-only
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
    overlay_blue,
)
from render_wall_pixel_vs_dino_cluster import prepare_crop  # noqa: E402

CURATION = ROOT / "pipeline/data/wall_layer_fixtures/v1/curated_lines_v1.json"
DEFAULT_OUT = ROOT / "results/visualizations/error_cases"

LAYER_STYLE = {
    "mucosa": {"color": "#facc15", "label": "Mucosal-side line"},
    "muscularis": {"color": "#f472b6", "label": "Muscularis line"},
    "serosa": {"color": "#4ade80", "label": "Serosal line"},
}
VERDICT_LABEL = {
    "continuous": "continuous",
    "interrupted": "interrupted",
    "suspected_interrupt": "suspected interrupt",
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


def chaikin(points: list[list[float]], rounds: int = 4) -> np.ndarray:
    """Corner-cut a control polygon without overshooting source coordinates."""
    pts = np.asarray(points, dtype=np.float32)
    if len(pts) < 3:
        return pts
    for _ in range(rounds):
        left = 0.75 * pts[:-1] + 0.25 * pts[1:]
        right = 0.25 * pts[:-1] + 0.75 * pts[1:]
        dense = np.empty((2 * len(left), 2), dtype=np.float32)
        dense[0::2] = left
        dense[1::2] = right
        pts = np.vstack([pts[0], dense, pts[-1]])
    return pts


def validate_case(case_id: str, spec: dict, crop_shape: tuple[int, int]) -> None:
    expected = tuple(int(v) for v in spec["crop_shape"])
    if tuple(crop_shape) != expected:
        raise ValueError(f"{case_id}: crop shape {crop_shape} != curated shape {expected}")
    for layer_id in LAYER_STYLE:
        layer = spec["layers"].get(layer_id)
        if not layer or not layer.get("segments"):
            raise ValueError(f"{case_id}: missing {layer_id} segments")
        for segment in layer["segments"]:
            points = np.asarray(segment, dtype=np.float32)
            if len(points) < 2:
                raise ValueError(f"{case_id}: {layer_id} segment has fewer than two points")
            if (
                (points[:, 0] < 0).any()
                or (points[:, 0] >= crop_shape[1]).any()
                or (points[:, 1] < 0).any()
                or (points[:, 1] >= crop_shape[0]).any()
            ):
                raise ValueError(f"{case_id}: {layer_id} point lies outside the crop")


def draw_layer(ax, layer_id: str, layer: dict) -> None:
    style = LAYER_STYLE[layer_id]
    segments = layer["segments"]
    verdict = layer["verdict"]
    for segment in segments:
        curve = chaikin(segment)
        linestyle = "--" if verdict == "cannot_judge" else "-"
        ax.plot(
            curve[:, 0],
            curve[:, 1],
            color=style["color"],
            linewidth=2.1,
            linestyle=linestyle,
            solid_capstyle="round",
            dash_capstyle="round",
            zorder=5,
        )
    if verdict in {"interrupted", "suspected_interrupt"} and len(segments) > 1:
        for left, right in zip(segments[:-1], segments[1:]):
            bridge = chaikin([left[-1], right[0]], rounds=0)
            ax.plot(
                bridge[:, 0],
                bridge[:, 1],
                color=style["color"],
                linewidth=1.5,
                linestyle=(0, (3, 3)),
                alpha=0.75,
                zorder=4,
            )


def _track_gray_path(
    gray: np.ndarray,
    xs: np.ndarray,
    lows: np.ndarray,
    highs: np.ndarray,
    prior: np.ndarray,
    *,
    bright: bool,
    smooth_weight: float = 5.0,
) -> np.ndarray:
    """Track one raw-pixel path with a first-order continuity penalty."""
    candidates = [
        np.arange(
            max(0, int(np.floor(lo))),
            min(gray.shape[0] - 1, int(np.ceil(hi))) + 1,
        )
        for lo, hi in zip(lows, highs)
    ]
    costs: list[np.ndarray] = []
    backs: list[np.ndarray] = []
    for index, ys in enumerate(candidates):
        raw = gray[ys, xs[index]].astype(np.float32)
        observation = -raw if bright else raw
        observation = 20.0 * (observation - observation.min()) / (np.ptp(observation) + 1e-6)
        unary = observation + 0.35 * np.abs(ys - prior[index])
        if index == 0:
            costs.append(unary)
            backs.append(np.full(len(ys), -1, dtype=np.int32))
            continue
        previous = candidates[index - 1]
        transition = costs[-1][:, None] + smooth_weight * np.abs(previous[:, None] - ys[None, :])
        back = np.argmin(transition, axis=0)
        costs.append(unary + transition[back, np.arange(len(ys))])
        backs.append(back.astype(np.int32))
    cursor = int(np.argmin(costs[-1]))
    path: list[int] = []
    for index in range(len(xs) - 1, -1, -1):
        path.append(int(candidates[index][cursor]))
        if index:
            cursor = int(backs[index][cursor])
    return np.asarray(path[::-1], dtype=np.int32)


def track_p040_pixel_bands(pack: dict) -> dict:
    """Track the visible dark-bright-dark sequence into the lesion margin."""
    gray = cv2.cvtColor(pack["crop"], cv2.COLOR_BGR2GRAY)
    # Suppress isolated speckle extrema, but keep the 1 px output coordinates.
    gray_work = cv2.GaussianBlur(gray, (3, 3), 0.8)
    wall = np.asarray(pack["wall_crop"], dtype=np.float32)
    lesion = np.asarray(pack["lesion_poly"], dtype=np.float32)
    lesion_right = int(np.ceil(float(lesion[:, 0].max()))) + 1
    start_x = max(
        int(np.ceil(float(wall[:, 0].min()))) + 3,
        lesion_right - 90,
    )
    stop_x = int(np.floor(float(wall[:, 0].max())))
    xs = np.arange(start_x, stop_x + 1, dtype=np.int32)
    heading_y = np.asarray(
        [
            np.median(wall[np.abs(wall[:, 0] - x) <= 2.0, 1])
            for x in xs
        ],
        dtype=np.float32,
    )
    if not np.isfinite(heading_y).all():
        raise ValueError("P040 heading does not cover the right-side pixel corridor")

    bright_y = _track_gray_path(
        gray_work, xs, heading_y - 3, heading_y + 8, heading_y + 3, bright=True,
    )
    dark1_y = _track_gray_path(
        gray_work, xs, bright_y - 12, bright_y - 4, bright_y - 7, bright=False,
    )
    dark2_y = _track_gray_path(
        gray_work, xs, bright_y + 5, bright_y + 15, bright_y + 9, bright=False,
    )

    dark1_gray = gray[dark1_y, xs].astype(np.float32)
    bright_gray = gray[bright_y, xs].astype(np.float32)
    dark2_gray = gray[dark2_y, xs].astype(np.float32)
    smooth_dark1 = gray_work[dark1_y, xs].astype(np.float32)
    smooth_bright = gray_work[bright_y, xs].astype(np.float32)
    smooth_dark2 = gray_work[dark2_y, xs].astype(np.float32)
    contrast = np.minimum(smooth_bright - smooth_dark1, smooth_bright - smooth_dark2)
    rolling_contrast = np.asarray(
        [
            np.median(contrast[max(0, index - 2) : min(len(xs), index + 3)])
            for index in range(len(xs))
        ],
        dtype=np.float32,
    )
    anchor = int(np.argmin(np.abs(xs - lesion_right)))
    left = anchor
    while left > 0 and rolling_contrast[left - 1] >= 15.0:
        left -= 1
    right = anchor
    while right + 1 < len(xs) and rolling_contrast[right + 1] >= 15.0:
        right += 1
    selection = slice(left, right + 1)

    def smooth_for_display(path: np.ndarray) -> np.ndarray:
        kernel = np.asarray([1, 4, 6, 4, 1], dtype=np.float32) / 16.0
        padded = np.pad(path.astype(np.float32), (2, 2), mode="edge")
        smooth = np.convolve(padded, kernel, mode="valid")
        return np.clip(smooth, path - 1.0, path + 1.0)

    return {
        "xs": xs[selection],
        "dark1_y": dark1_y[selection],
        "bright_y": bright_y[selection],
        "dark2_y": dark2_y[selection],
        "dark1_smooth": smooth_for_display(dark1_y[selection]),
        "bright_smooth": smooth_for_display(bright_y[selection]),
        "dark2_smooth": smooth_for_display(dark2_y[selection]),
        "dark1_gray": dark1_gray[selection],
        "bright_gray": bright_gray[selection],
        "dark2_gray": dark2_gray[selection],
        "contrast": contrast[selection],
    }


def _paint_tracked_bands(rgb: np.ndarray, track: dict) -> np.ndarray:
    overlay = rgb.astype(np.float32).copy()
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray_work = cv2.GaussianBlur(gray, (3, 3), 0.8)
    masks = {
        "dark1_y": np.zeros(rgb.shape[:2], dtype=bool),
        "bright_y": np.zeros(rgb.shape[:2], dtype=bool),
        "dark2_y": np.zeros(rgb.shape[:2], dtype=bool),
    }
    for x, y1, y2, y3 in zip(
        track["xs"], track["dark1_y"], track["bright_y"], track["dark2_y"],
    ):
        split12 = int(np.floor((y1 + y2) / 2.0))
        split23 = int(np.floor((y2 + y3) / 2.0))
        dark1_limit = 0.5 * (float(gray_work[y1, x]) + float(gray_work[y2, x]))
        bright_limit = 0.5 * (
            float(gray_work[y2, x])
            + max(float(gray_work[y1, x]), float(gray_work[y3, x]))
        )
        lower_end = min(rgb.shape[0] - 1, int(y3) + 12)
        lower_peak_y = int(y3) + int(np.argmax(gray_work[int(y3) : lower_end + 1, x]))
        dark2_limit = 0.5 * (
            float(gray_work[y3, x]) + float(gray_work[lower_peak_y, x])
        )

        dark1_top = int(y1)
        while dark1_top > max(0, int(y1) - 7) and gray_work[dark1_top - 1, x] <= dark1_limit:
            dark1_top -= 1
        dark1_bottom = int(y1)
        while dark1_bottom < split12 and gray_work[dark1_bottom + 1, x] <= dark1_limit:
            dark1_bottom += 1

        bright_top = int(y2)
        while bright_top > split12 and gray_work[bright_top - 1, x] >= bright_limit:
            bright_top -= 1
        bright_bottom = int(y2)
        while bright_bottom < split23 and gray_work[bright_bottom + 1, x] >= bright_limit:
            bright_bottom += 1

        dark2_top = int(y3)
        while dark2_top > split23 and gray_work[dark2_top - 1, x] <= dark2_limit:
            dark2_top -= 1
        dark2_bottom = int(y3)
        while dark2_bottom < lower_peak_y and gray_work[dark2_bottom + 1, x] <= dark2_limit:
            dark2_bottom += 1

        masks["dark1_y"][dark1_top : dark1_bottom + 1, x] = True
        masks["bright_y"][bright_top : bright_bottom + 1, x] = True
        masks["dark2_y"][dark2_top : dark2_bottom + 1, x] = True
    colors = {
        "dark1_y": np.asarray((250, 204, 21), dtype=np.float32),
        "bright_y": np.asarray((56, 189, 248), dtype=np.float32),
        "dark2_y": np.asarray((244, 114, 182), dtype=np.float32),
    }
    for key, mask in masks.items():
        overlay[mask] = 0.82 * overlay[mask] + 0.18 * colors[key]
    return np.clip(overlay, 0, 255).astype(np.uint8)


def render_p040_pixel_bands(pack: dict, out_dir: Path) -> Path:
    """Render full context plus nearest-neighbor pixel zoom for P040."""
    track = track_p040_pixel_bands(pack)
    raw = cv2.cvtColor(pack["crop"], cv2.COLOR_BGR2RGB)
    panel = _paint_tracked_bands(raw, track)
    contour_mask = (pack["crop_mask"] > 0).astype(np.uint8) * 255
    contours, _ = cv2.findContours(contour_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    context = panel.copy()
    cv2.drawContours(context, contours, -1, (191, 219, 254), 1, cv2.LINE_AA)

    xs = track["xs"]
    y_min = int(min(track["dark1_y"].min() - 8, track["bright_y"].min() - 8))
    y_max = int(max(track["dark2_y"].max() + 8, track["bright_y"].max() + 8))
    x_min = max(0, int(xs.min()) - 12)
    x_max = min(raw.shape[1] - 1, int(xs.max()) + 12)
    cv2.rectangle(context, (x_min, y_min), (x_max, y_max), (255, 255, 255), 1, cv2.LINE_AA)

    fig, axes = plt.subplots(1, 2, figsize=(13.0, 5.2), gridspec_kw={"width_ratios": [1.15, 1.0]})
    axes[0].imshow(context, interpolation="nearest")
    axes[0].set_title("A  P040 full context with tracked bands", fontsize=12)
    axes[0].axis("off")
    axes[1].imshow(panel, interpolation="nearest")
    axes[1].set_xlim(x_min, x_max)
    axes[1].set_ylim(y_max, y_min)
    axes[1].set_title("B  Pixel-aligned dark-bright-dark bands", fontsize=12)
    colors = {"dark1_y": "#facc15", "bright_y": "#38bdf8", "dark2_y": "#f472b6"}
    labels = {"dark1_y": "Dark band 1", "bright_y": "Bright band", "dark2_y": "Dark band 2"}
    smooth_keys = {
        "dark1_y": "dark1_smooth",
        "bright_y": "bright_smooth",
        "dark2_y": "dark2_smooth",
    }
    for key in ("dark1_y", "bright_y", "dark2_y"):
        for ax, linewidth in ((axes[0], 0.8), (axes[1], 1.15)):
            ax.plot(
                xs,
                track[smooth_keys[key]],
                color=colors[key],
                linewidth=linewidth,
                solid_capstyle="round",
                solid_joinstyle="round",
                label=labels[key],
            )
    axes[1].axis("off")
    handles = [
        Line2D([0], [0], color=colors[key], lw=2.0, label=labels[key])
        for key in ("dark1_y", "bright_y", "dark2_y")
    ]
    fig.legend(
        handles=handles, loc="lower center", ncol=3, frameon=False,
        labelcolor="white", fontsize=9, bbox_to_anchor=(0.5, 0.045),
    )
    medians = (
        float(np.median(track["dark1_gray"])),
        float(np.median(track["bright_gray"])),
        float(np.median(track["dark2_gray"])),
    )
    fig.text(
        0.5, 0.105,
        f"Tracked x={int(xs.min())}-{int(xs.max())} px; median gray={medians[0]:.0f}, {medians[1]:.0f}, {medians[2]:.0f}",
        ha="center", color="#d1d5db", fontsize=9,
    )
    fig.suptitle("P040 wall bands tracked from clear wall into lesion margin", fontsize=14, y=0.98)
    fig.tight_layout(rect=[0.01, 0.14, 0.99, 0.93])
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "CASE-040_pixel_aligned_bands_v4.png"
    fig.savefig(dest, dpi=240, bbox_inches="tight")
    plt.close(fig)
    return dest


def render_case(pack: dict, spec: dict, out_dir: Path) -> Path:
    meta = pack["meta"]
    crop_rgb = cv2.cvtColor(pack["crop"], cv2.COLOR_BGR2RGB)
    panel = (
        overlay_blue(crop_rgb, pack["crop_mask"])
        if len(meta.get("lesion_polygon") or []) >= 3
        else crop_rgb
    )
    validate_case(str(meta["case_id"]), spec, panel.shape[:2])

    fig, ax = plt.subplots(figsize=(8.2, 5.6))
    ax.imshow(panel, interpolation="nearest")
    for layer_id, layer in spec["layers"].items():
        draw_layer(ax, layer_id, layer)
    ax.set_xlim(0, panel.shape[1] - 1)
    ax.set_ylim(panel.shape[0] - 1, 0)
    ax.axis("off")
    ax.set_title(
        f"{meta['display_id']}  Record-assisted wall-layer line curation",
        fontsize=13,
        pad=9,
    )

    legend = [
        Line2D([0], [0], color=style["color"], lw=2.2, label=style["label"])
        for style in LAYER_STYLE.values()
    ]
    legend.append(
        Line2D([0], [0], color="#d1d5db", lw=1.4, linestyle="--", label="Expected path / unobserved gap")
    )
    fig.legend(
        handles=legend,
        loc="lower center",
        ncol=4,
        frameon=False,
        labelcolor="white",
        fontsize=8.5,
        bbox_to_anchor=(0.5, 0.045),
    )
    verdicts = "    ".join(
        f"{LAYER_STYLE[layer_id]['label']}: {VERDICT_LABEL.get(layer['verdict'], layer['verdict'])}"
        for layer_id, layer in spec["layers"].items()
    )
    fig.text(0.5, 0.125, verdicts, ha="center", color="#e5e7eb", fontsize=9)
    fig.text(
        0.5,
        0.012,
        "Record-assisted draft; line placement requires clinical review and does not determine cT.",
        ha="center",
        color="#9ca3af",
        fontsize=8.5,
    )
    fig.tight_layout(rect=[0.015, 0.17, 0.985, 0.94])
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{meta['case_id']}_curated_layers.png"
    fig.savefig(dest, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return dest


def render_index(paths: list[Path], out_dir: Path) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(14.0, 10.2))
    for ax, path in zip(axes.flat, paths):
        ax.imshow(plt.imread(path))
        ax.axis("off")
    fig.suptitle("Four-case record-assisted wall-layer line curation", fontsize=15, y=0.995)
    fig.tight_layout(pad=0.7)
    dest = out_dir / "wall_curated_layers_v1_20260829.png"
    fig.savefig(dest, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="", help="Case ID or display ID, for example CASE-040 or P040")
    parser.add_argument("--index", action="store_true", help="Also render the four-case contact sheet")
    parser.add_argument("--p040-pixels", action="store_true", help="Track and render P040 dark-bright-dark source-pixel bands")
    parser.add_argument("--validate-only", action="store_true", help="Validate crop coordinates without rendering")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    curation = json.loads(CURATION.read_text(encoding="utf-8"))
    selector = args.case.strip().upper()
    segmenter = RoiSegmenter()
    paths: list[Path] = []
    summaries: list[dict] = []
    for meta_path in sorted(Path(DEFAULT_FIXTURES).glob("CASE-*/meta.json")):
        meta = load_meta(meta_path)
        case_id = str(meta["case_id"]).upper()
        display_id = str(meta["display_id"]).upper()
        if selector and selector not in {case_id, display_id}:
            continue
        pack = prepare_crop(meta, segmenter)
        if args.p040_pixels:
            if case_id != "CASE-040":
                continue
            path = render_p040_pixel_bands(pack, args.out_dir)
            summaries.append({"case_id": case_id, "display_id": display_id, "panel": str(path)})
            paths.append(path)
            continue
        spec = curation["cases"][case_id]
        validate_case(case_id, spec, tuple(pack["crop"].shape[:2]))
        path = None if args.validate_only else render_case(pack, spec, args.out_dir)
        if path is not None:
            paths.append(path)
        summaries.append({
            "case_id": case_id,
            "display_id": display_id,
            "verdicts": {
                layer_id: layer["verdict"] for layer_id, layer in spec["layers"].items()
            },
            "panel": str(path) if path else None,
        })
    if selector and not summaries:
        raise SystemExit(f"unknown case selector: {args.case}")
    index_path = render_index(paths, args.out_dir) if args.index and len(paths) > 1 else None
    print(json.dumps({"cases": summaries, "index": str(index_path) if index_path else None}, indent=2))


if __name__ == "__main__":
    main()
