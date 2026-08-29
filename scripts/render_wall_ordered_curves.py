#!/usr/bin/env python3
"""Draw ordered wall curves: solid outside the lesion, dashed if predicted.

  python3 scripts/render_wall_ordered_curves.py --index
  python3 scripts/render_wall_ordered_curves.py --case P040
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
    FATE_HEX,
    LAYER_HEX,
    LAYER_LEGEND,
    LAYER_RGB,
    RoiSegmenter,
    VIS_DIR,
    load_meta,
    overlay_blue,
    wall_strip,
)
from render_wall_pixel_vs_dino_cluster import (  # noqa: E402
    A_SCALE,
    B_SCALE,
    draw_full_brush,
    prepare_crop,
    right_layer_box,
)
from wall_lesion_aware_cluster import DEFAULT_BRUSH, to_gray
from wall_ordered_curve_track import summary, track_ordered_layers

DEFAULT_OUT = ROOT / "pipeline/experiments/reports/lesion_aware_wall_cluster_v1/ordered_curves"

plt.rcParams.update({
    "font.family": "Times New Roman",
    "font.size": 11,
    "axes.facecolor": "black",
    "figure.facecolor": "black",
    "savefig.facecolor": "black",
    "text.color": "white",
    "axes.labelcolor": "white",
    "axes.edgecolor": "#555555",
})

STATUS_EN = {
    "detected": "detected",
    "missing": "missing",
    "fused": "fused",
    "uncertain": "unclear",
    "wrap": "wrap",
}
STATUS_COLOR = {
    "detected": FATE_HEX["intact"],
    "missing": FATE_HEX["lost"],
    "fused": FATE_HEX["fused"],
    "uncertain": FATE_HEX["unclear"],
    "wrap": "#93c5fd",
}


def _draw_curve(panel: np.ndarray, points, sx1: float, sy1: float, scale: float, color, dashed: bool) -> None:
    pts = np.asarray(points or [], dtype=np.float32)
    if len(pts) < 2:
        return
    pts = pts.copy()
    pts[:, 0] = (pts[:, 0] - sx1) * scale
    pts[:, 1] = (pts[:, 1] - sy1) * scale
    xy = np.round(pts).astype(np.int32)
    if dashed:
        for i in range(0, len(xy) - 1, 2):
            cv2.line(panel, tuple(xy[i]), tuple(xy[min(i + 1, len(xy) - 1)]), color, 1, cv2.LINE_AA)
    else:
        cv2.polylines(panel, [xy], False, color, 2, cv2.LINE_AA)


def paint_curves(rgb, track, sx1, sy1, sx2, sy2, scale: int) -> np.ndarray:
    strip = rgb[sy1:sy2, sx1:sx2]
    panel = cv2.resize(
        strip, (strip.shape[1] * scale, strip.shape[0] * scale), interpolation=cv2.INTER_LINEAR,
    )
    if getattr(track, "status", "") != "ok":
        return panel
    for i, layer in enumerate(track.layers):
        color = LAYER_RGB.get(i, (200, 200, 200))
        _draw_curve(panel, layer.solid, sx1, sy1, scale, color, False)
        _draw_curve(panel, layer.wrap, sx1, sy1, scale, color, False)
        _draw_curve(panel, layer.dashed, sx1, sy1, scale, color, True)
    return panel


def render_case(pack: dict, out_dir: Path, brush: float) -> dict:
    meta = pack["meta"]
    crop = pack["crop"]
    gray = to_gray(crop)
    track = track_ordered_layers(
        gray, pack["wall_crop"], pack["crop_mask"],
        lumen_center=pack["crop_lumen"],
        lesion_poly=pack["lesion_poly"],
        dilate_px=5,
        fit_side="right",
    )
    crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    source = overlay_blue(crop_rgb, pack["crop_mask"])
    source = draw_full_brush(source, pack["wall_crop"], brush)
    ax1, ay1, ax2, ay2 = wall_strip(source, pack["wall_crop"], pad=22)
    panel_a = cv2.resize(
        source[ay1:ay2, ax1:ax2],
        ((ax2 - ax1) * A_SCALE, (ay2 - ay1) * A_SCALE),
        interpolation=cv2.INTER_LINEAR,
    )
    bx1, by1, bx2, by2 = right_layer_box(crop_rgb.shape[:2], pack["wall_crop"], pack["lesion_poly"], brush)
    panel_b = paint_curves(
        overlay_blue(crop_rgb.copy(), pack["crop_mask"]),
        track, bx1, by1, bx2, by2, B_SCALE,
    )

    fig, axes = plt.subplots(1, 2, figsize=(16.8, 6.4), gridspec_kw={"width_ratios": [1.0, 1.75]})
    for ax, panel, title in zip(
        axes, (panel_a, panel_b),
        ("A  Source  (heading is a guide)", "B  Ordered curves  (solid detected, dashed predicted)"),
    ):
        ax.imshow(panel)
        ax.set_title(title, fontsize=12)
        ax.axis("off")
    fig.suptitle(
        f"{meta.get('display_id')}  {meta.get('time_sec')}s  pT {meta.get('pT_ref') or '?'}",
        fontsize=13, fontname="Times New Roman", y=0.98,
    )
    handles = [
        Line2D([0], [0], color=LAYER_HEX[lab], lw=2.0, label=en)
        for lab, _key, en in LAYER_LEGEND
    ]
    handles.append(Line2D([0], [0], color="#e5e7eb", lw=1.2, linestyle="--", label="Predicted into lesion"))
    fig.legend(
        handles=handles, loc="lower center", ncol=4, frameon=False,
        labelcolor="white", fontsize=10, bbox_to_anchor=(0.5, 0.02),
        prop={"family": "Times New Roman", "size": 10},
    )
    x = 0.12
    fig.text(0.06, 0.086, "Curve", color="#f8fafc", fontsize=11, fontname="Times New Roman", fontweight="bold")
    for layer in track.layers:
        fig.text(
            x, 0.086, f"{layer.id} {STATUS_EN.get(layer.status, layer.status)}",
            color=STATUS_COLOR.get(layer.status, "#e5e7eb"),
            fontsize=10, fontname="Times New Roman",
        )
        x += 0.18
    fig.tight_layout(rect=[0, 0.12, 1, 0.95])
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{meta.get('case_id')}_ordered_curves.png"
    fig.savefig(dest, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return {
        "case_id": meta.get("case_id"),
        "display_id": meta.get("display_id"),
        "status": track.status,
        "panel": str(dest),
        "mask_source": pack["mask_source"],
        "track": summary(track),
    }


def render_index(out_dir: Path, panels: list[Path]) -> Path:
    fig, axes = plt.subplots(len(panels), 1, figsize=(15.4, 4.0 * max(1, len(panels))))
    if len(panels) == 1:
        axes = [axes]
    for ax, path in zip(axes, panels):
        ax.imshow(plt.imread(str(path)))
        ax.set_title(path.name.replace("_ordered_curves.png", ""), fontsize=11)
        ax.axis("off")
    fig.suptitle("Ordered wall curves", fontsize=14, fontname="Times New Roman", y=0.995)
    fig.tight_layout()
    dest = out_dir / "index.png"
    fig.savefig(dest, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="Render lesion-aware ordered wall curves.")
    parser.add_argument("--fixtures", default=str(DEFAULT_FIXTURES))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--brush", type=float, default=12.0)
    parser.add_argument("--case", action="append", dest="cases")
    parser.add_argument("--index", action="store_true")
    args = parser.parse_args()
    wanted = {str(token).upper().replace("P", "CASE-") if str(token).upper().startswith("P") else str(token).upper() for token in (args.cases or [])}
    wanted = {item if item.startswith("CASE-") else f"CASE-{item}" for item in wanted}
    seg = RoiSegmenter()
    print("ordered-curve track  dilate=5  right flank", flush=True)
    rows = []
    panels = []
    for meta_path in sorted(Path(args.fixtures).glob("CASE-*/meta.json")):
        meta = load_meta(meta_path)
        if wanted and str(meta.get("case_id")) not in wanted:
            continue
        pack = prepare_crop(meta, seg)
        if pack is None:
            rows.append({"case_id": meta.get("case_id"), "status": "missing_frame"})
            continue
        row = render_case(pack, Path(args.out), max(DEFAULT_BRUSH, float(args.brush)))
        rows.append(row)
        if row.get("panel"):
            panels.append(Path(row["panel"]))
        print(f"{row.get('display_id')} {row.get('status')} {row.get('track', {}).get('layers')}", flush=True)
    vis = VIS_DIR
    vis.mkdir(parents=True, exist_ok=True)
    for panel in panels:
        (vis / panel.name).write_bytes(panel.read_bytes())
    index_path = ""
    if args.index and panels:
        index_path = str(render_index(Path(args.out), panels))
        (vis / "wall_ordered_curves_20260829.png").write_bytes(Path(index_path).read_bytes())
    (Path(args.out) / "summary.json").write_text(
        json.dumps(
            {
                "created_at": "2026-08-29",
                "note": "Ordered curves, not pixel classes. Dashed is predicted only. Not a cT.",
                "cases": rows,
                "index": index_path,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote {len(panels)} panel(s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
