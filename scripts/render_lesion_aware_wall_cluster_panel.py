#!/usr/bin/env python3
"""Black / Times contact sheet for lesion-aware wall clustering.

  python3 scripts/render_lesion_aware_wall_cluster_panel.py --help
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from wall_lesion_aware_cluster import LAYER_NAMES_3, as_xy, rasterize_polygon  # noqa: E402

LAYER_RGB = {
    "shallow": (250, 204, 21),
    "muscularis": (56, 189, 248),
    "serosa": (74, 222, 128),
    "inner": (250, 204, 21),
    "outer": (74, 222, 128),
    "dark": (40, 40, 40),
    "mid": (128, 128, 128),
    "bright": (220, 220, 220),
}
LESION_RGBA = (220, 38, 38, 90)
DELETED = (248, 113, 113)
KEPT = (250, 204, 21)

plt.rcParams.update({
    "font.family": "Times New Roman",
    "font.size": 11,
    "axes.facecolor": "black",
    "figure.facecolor": "black",
    "savefig.facecolor": "black",
    "text.color": "white",
    "axes.labelcolor": "white",
    "axes.edgecolor": "#555555",
    "xtick.color": "white",
    "ytick.color": "white",
})


def _overlay_lesion(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = rgb.copy()
    tint = np.zeros_like(out)
    tint[..., 0] = LESION_RGBA[0]
    tint[..., 1] = LESION_RGBA[1]
    tint[..., 2] = LESION_RGBA[2]
    sel = mask > 0
    out[sel] = np.clip(0.65 * out[sel] + 0.35 * tint[sel], 0, 255).astype(np.uint8)
    return out


def _paint_cluster(rgb: np.ndarray, arm, names=LAYER_NAMES_3) -> np.ndarray:
    out = rgb.copy()
    if not arm or getattr(arm, "status", "") != "ok":
        return out
    xs = np.asarray(arm.xs, dtype=np.int32)
    ys = np.asarray(arm.ys, dtype=np.int32)
    labels = np.asarray(arm.labels, dtype=np.int32)
    if len(xs) == 0:
        return out
    for lab, name in enumerate(names):
        color = LAYER_RGB.get(name, (200, 200, 200))
        sel = labels == lab
        if not sel.any():
            continue
        out[ys[sel], xs[sel]] = (
            0.45 * out[ys[sel], xs[sel]] + 0.55 * np.array(color, dtype=np.float32)
        ).astype(np.uint8)
    for name, line in (arm.layer_polylines or {}).items():
        pts = as_xy(line)
        if len(pts) < 2:
            continue
        color = LAYER_RGB.get(name, (255, 255, 255))
        cv2.polylines(out, [np.round(pts).astype(np.int32)], False, color[::-1], 2, cv2.LINE_AA)
    return out


def _paint_truncate(rgb: np.ndarray, wall, lesion_mask, brush: float) -> np.ndarray:
    out = rgb.copy()
    if len(wall) < 2:
        return out
    thick = max(2, int(round(brush)))
    deleted = rasterize_polygon(out.shape[:2], [])
    deleted = np.zeros(out.shape[:2], dtype=np.uint8)
    cv2.polylines(deleted, [np.round(wall).astype(np.int32)], False, 255, thick, cv2.LINE_AA)
    kept = deleted.copy()
    kept[lesion_mask > 0] = 0
    gone = deleted.copy()
    gone[lesion_mask == 0] = 0
    out[gone > 0] = (0.35 * out[gone > 0] + 0.65 * np.array(DELETED)).astype(np.uint8)
    out[kept > 0] = (0.35 * out[kept > 0] + 0.65 * np.array(KEPT)).astype(np.uint8)
    return out


def _crop(rgb: np.ndarray, lesion, wall, pad: int = 36) -> np.ndarray:
    pts = []
    if lesion is not None and len(lesion):
        pts.append(lesion)
    if wall is not None and len(wall):
        pts.append(wall)
    if not pts:
        return rgb
    all_pts = np.concatenate(pts, axis=0)
    h, w = rgb.shape[:2]
    x1 = max(0, int(all_pts[:, 0].min()) - pad)
    y1 = max(0, int(all_pts[:, 1].min()) - pad)
    x2 = min(w, int(all_pts[:, 0].max()) + pad)
    y2 = min(h, int(all_pts[:, 1].max()) + pad)
    if x2 - x1 < 40 or y2 - y1 < 40:
        return rgb
    return rgb[y1:y2, x1:x2]


def render_case(out_dir: Path, summary: dict, image_bgr, lesion, wall, lesion_mask, arms) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    brush = float(summary.get("brush_radius") or 8)
    full = arms.get("full")
    exclude = arms.get("d5") or arms.get("d0")
    live = arms.get("live") or {}

    col0 = _overlay_lesion(rgb, lesion_mask)
    if len(wall) >= 2:
        cv2.polylines(col0, [np.round(wall).astype(np.int32)], False, (250, 204, 21), 2, cv2.LINE_AA)
    col1 = _paint_truncate(_overlay_lesion(rgb, lesion_mask), wall, lesion_mask, brush)
    col2 = _paint_cluster(_overlay_lesion(rgb, lesion_mask), full)
    col3 = _paint_cluster(_overlay_lesion(rgb, lesion_mask), exclude)

    fig, axes = plt.subplots(1, 4, figsize=(18, 5.2))
    titles = [
        "A. Frame, full expected line, lesion",
        "B. Deleted (lesion) vs kept flanks",
        f"C. Full-brush k=3, {getattr(full, 'pattern', '') or 'no pattern'}",
        f"D. Exclude lesion d=5, {getattr(exclude, 'pattern', '') or 'no pattern'}",
    ]
    for ax, img, title in zip(axes, (col0, col1, col2, col3), titles):
        ax.imshow(_crop(img, lesion, wall))
        ax.set_title(title, fontsize=11)
        ax.axis("off")
    live_note = live.get("pattern") or live.get("note") or "live M0 unavailable"
    fig.suptitle(
        f"{summary.get('display_id')}  pT {summary.get('pT_ref') or '?'}  "
        f"wall={summary.get('wall_source')}  live M0: {live_note}",
        fontsize=14,
        color="white",
        y=0.98,
    )
    fig.text(
        0.5,
        0.02,
        "Yellow=shallow, blue=muscularis, green=serosa. Red wash=lesion. "
        "Exclude-lesion pixels fit the centers; lesion cells are query only. Not a cT.",
        ha="center",
        fontsize=10,
    )
    fig.tight_layout(rect=[0, 0.05, 1, 0.93])
    path = out_dir / f"{summary.get('case_id')}_ab.png"
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


def render_index(out_dir: Path, panels: list[Path]) -> Path:
    if not panels:
        return out_dir / "index.png"
    fig, axes = plt.subplots(len(panels), 1, figsize=(12, 3.2 * len(panels)))
    if len(panels) == 1:
        axes = [axes]
    for ax, path in zip(axes, panels):
        img = plt.imread(str(path))
        ax.imshow(img)
        ax.set_title(path.name, fontsize=10)
        ax.axis("off")
    fig.suptitle("Lesion-aware wall cluster A/B, fixture v1", fontsize=14, y=0.995)
    fig.tight_layout()
    dest = out_dir / "index.png"
    fig.savefig(dest, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="Render lesion-aware wall cluster panels.")
    parser.add_argument("--summary", default=str(ROOT / "pipeline/experiments/reports/lesion_aware_wall_cluster_v1/summary.json"))
    args = parser.parse_args()
    print("Use eval_lesion_aware_wall_cluster_v1.py --render to build panels from fixtures.", flush=True)
    print(f"summary expected at {args.summary}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
