#!/usr/bin/env python3
"""Diagnostic panels: cavity side, gray-vs-depth, method contrast.

Black / Times. Offline only. Does not unlock cT.

  python3 scripts/render_wall_cluster_diagnostics.py --help
"""
from __future__ import annotations

import argparse
import csv
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

from wall_lesion_aware_cluster import (  # noqa: E402
    as_xy,
    densify_polyline,
    dilate_mask,
    flip_outward,
    polygon_centroid,
    rasterize_brush,
    rasterize_polygon,
    sample_band_pixels,
    to_gray,
)

DEFAULT_FIXTURES = ROOT / "pipeline/data/wall_layer_fixtures/v1"
DEFAULT_COMPARE = ROOT / "pipeline/experiments/reports/lesion_aware_wall_cluster_trad/method_comparison.csv"
DEFAULT_OUT = ROOT / "pipeline/experiments/reports/lesion_aware_wall_cluster_trad/diagnostics"
DILATE_PX = 5

plt.rcParams.update({
    "font.family": "Times New Roman",
    "font.size": 11,
    "axes.facecolor": "black",
    "figure.facecolor": "black",
    "savefig.facecolor": "black",
    "text.color": "white",
    "axes.labelcolor": "white",
    "axes.edgecolor": "#666666",
    "xtick.color": "white",
    "ytick.color": "white",
})


def load_meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_frame(meta: dict) -> Path:
    frame = Path(str(meta.get("frame_path") or ""))
    return frame if frame.is_absolute() else ROOT / frame


def lumen_center_of(meta: dict) -> tuple[np.ndarray | None, str]:
    poly = as_xy(meta.get("lumen_polygon"))
    if len(poly) >= 3:
        return poly.mean(axis=0), "lumen_polygon"
    box = meta.get("lumen_bbox") or {}
    if isinstance(box, dict) and {"x1", "y1", "x2", "y2"} <= set(box):
        cx = 0.5 * (float(box["x1"]) + float(box["x2"]))
        cy = 0.5 * (float(box["y1"]) + float(box["y2"]))
        return np.array([cx, cy], dtype=np.float32), "lumen_bbox"
    return None, "heuristic"


def binned_profile(across: np.ndarray, gray: np.ndarray, n_bins: int = 11) -> tuple[np.ndarray, np.ndarray]:
    if len(across) < 8:
        return np.zeros(0), np.zeros(0)
    lo, hi = np.percentile(across, [5, 95])
    edges = np.linspace(lo, hi, n_bins + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    means = []
    for a, b in zip(edges[:-1], edges[1:]):
        sel = (across >= a) & (across < b)
        means.append(float(gray[sel].mean()) if sel.any() else np.nan)
    return centers, np.asarray(means, dtype=np.float32)


def profile_is_bdb(means: np.ndarray) -> bool:
    vals = means[np.isfinite(means)]
    if len(vals) < 5:
        return False
    mid = len(vals) // 2
    left = float(np.nanmean(vals[:max(1, mid - 1)]))
    center = float(np.nanmean(vals[mid - 1:mid + 2]))
    right = float(np.nanmean(vals[mid + 1:]))
    return left > center + 4 and right > center + 4


def paint_anatomy(image_bgr: np.ndarray, wall: np.ndarray, lesion, lumen_c, samples, keep) -> np.ndarray:
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    if lesion is not None and len(lesion) >= 3:
        overlay = rgb.copy()
        mask = rasterize_polygon(rgb.shape[:2], lesion)
        overlay[mask > 0] = (0.65 * overlay[mask > 0] + 0.35 * np.array([220, 38, 38])).astype(np.uint8)
        rgb = overlay
    if len(wall) >= 2:
        cv2.polylines(rgb, [np.round(wall).astype(np.int32)], False, (250, 204, 21), 2, cv2.LINE_AA)
    if lumen_c is not None:
        cv2.circle(rgb, (int(lumen_c[0]), int(lumen_c[1])), 7, (56, 189, 248), -1)
        cv2.circle(rgb, (int(lumen_c[0]), int(lumen_c[1])), 10, (255, 255, 255), 1)
    if len(wall) >= 3:
        step = max(1, len(wall) // 10)
        lesion_c = polygon_centroid(as_xy(lesion)) if lesion is not None and len(lesion) >= 3 else None
        for i in range(0, len(wall) - 1, step):
            a, b = wall[i], wall[min(len(wall) - 1, i + 1)]
            tan = b - a
            origin = 0.5 * (a + b)
            normal = flip_outward(origin, tan, lumen_c, lesion_c, None) * 22.0
            end = (int(origin[0] + normal[0]), int(origin[1] + normal[1]))
            cv2.arrowedLine(rgb, (int(origin[0]), int(origin[1])), end, (74, 222, 128), 2, tipLength=0.35)
    return rgb


def crop_around(rgb: np.ndarray, wall, lesion, pad: int = 48) -> np.ndarray:
    pts = []
    if len(wall):
        pts.append(wall)
    if lesion is not None and len(lesion):
        pts.append(np.asarray(lesion, dtype=np.float32))
    if not pts:
        return rgb
    all_pts = np.concatenate(pts, axis=0)
    h, w = rgb.shape[:2]
    x1 = max(0, int(all_pts[:, 0].min()) - pad)
    y1 = max(0, int(all_pts[:, 1].min()) - pad)
    x2 = min(w, int(all_pts[:, 0].max()) + pad)
    y2 = min(h, int(all_pts[:, 1].max()) + pad)
    return rgb[y1:y2, x1:x2]


def load_contrast(path: Path) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            case = str(row.get("display_id") or "")
            method = str(row.get("method") or "")
            try:
                val = float(row.get("contrast") or 0)
            except ValueError:
                val = 0.0
            out.setdefault(case, {})[method] = val
    return out


def render_case(meta: dict, out_dir: Path, contrast_map: dict) -> dict:
    image = cv2.imread(str(resolve_frame(meta)), cv2.IMREAD_COLOR)
    if image is None:
        return {"display_id": meta.get("display_id"), "status": "missing_frame"}
    gray = to_gray(image)
    wall = densify_polyline(as_xy(meta.get("wall_polygon")), 3.0)
    lesion = as_xy(meta.get("lesion_polygon"))
    lesion_mask = rasterize_polygon(gray.shape, lesion)
    lesion_d = dilate_mask(lesion_mask, DILATE_PX)
    lumen_c, lumen_src = lumen_center_of(meta)
    lesion_c = polygon_centroid(lesion) if len(lesion) >= 3 else None
    deepest = None
    if len(lesion) >= 2 and lesion_c is not None:
        deepest = lesion[int(np.argmax(np.linalg.norm(lesion - lesion_c, axis=1)))]
    brush = float(meta.get("brush_radius") or 8)
    brush_mask = rasterize_brush(gray.shape, wall, brush)
    samples = sample_band_pixels(gray, brush_mask, wall, brush, lumen_c, lesion_c, deepest)
    keep = lesion_d[samples["ys"], samples["xs"]] == 0 if len(samples["xs"]) else np.zeros(0, dtype=bool)
    anatomy = crop_around(paint_anatomy(image, wall, lesion, lumen_c, samples, keep), wall, lesion)

    across_k = samples["across"][keep] if keep.any() else np.zeros(0)
    gray_k = samples["gray"][keep] if keep.any() else np.zeros(0)
    across_x = samples["across"][~keep] if (~keep).any() else np.zeros(0)
    gray_x = samples["gray"][~keep] if (~keep).any() else np.zeros(0)
    xc, yc = binned_profile(across_k, gray_k)
    xf, yf = binned_profile(-across_k, gray_k)
    bdb = profile_is_bdb(yc)
    bdb_flip = profile_is_bdb(yf)

    fig, axes = plt.subplots(1, 4, figsize=(18.5, 4.8))
    axes[0].imshow(anatomy)
    axes[0].set_title("A. Line, lesion, outward arrows", fontsize=10)
    axes[0].axis("off")

    axes[1].scatter(across_x, gray_x, s=4, c="#f87171", alpha=0.25, label="lesion / dropped")
    axes[1].scatter(across_k, gray_k, s=4, c="#facc15", alpha=0.35, label="kept flanks")
    axes[1].set_xlabel("across (cavity -, serosa +)")
    axes[1].set_ylabel("gray")
    axes[1].set_title("B. Gray vs depth", fontsize=10)
    axes[1].legend(fontsize=8, loc="best", labelcolor="white", facecolor="#111")
    axes[1].set_ylim(0, 255)

    axes[2].plot(xc, yc, color="#facc15", lw=2.2, label=f"current  BDB={bdb}")
    axes[2].plot(xf, yf, color="#38bdf8", lw=2.0, ls="--", label=f"flipped  BDB={bdb_flip}")
    axes[2].axvline(0, color="#555", lw=1)
    axes[2].set_xlabel("across")
    axes[2].set_ylabel("mean gray")
    axes[2].set_title("C. Across profile, current vs flipped", fontsize=10)
    axes[2].legend(fontsize=8, loc="best", labelcolor="white", facecolor="#111")
    axes[2].set_ylim(0, 255)

    methods = ["kmeans", "gmm", "ward", "fcm", "kmeans1d_gray", "kmeans1d_across"]
    vals = [float((contrast_map.get(str(meta.get("display_id"))) or {}).get(name, 0.0)) for name in methods]
    colors = ["#4ade80" if v > 8 else "#f87171" for v in vals]
    axes[3].bar(range(len(methods)), vals, color=colors)
    axes[3].axhline(0, color="#888", lw=1)
    axes[3].set_xticks(range(len(methods)))
    axes[3].set_xticklabels(["kmeans", "GMM", "Ward", "FCM", "1D gray", "1D depth"], rotation=25, ha="right")
    axes[3].set_ylabel("contrast (shallow+serosa-2x mid)")
    axes[3].set_title("D. Method contrast", fontsize=10)

    fig.suptitle(
        f"{meta.get('display_id')}  pT {meta.get('pT_ref') or '?'}  "
        f"cavity={lumen_src}  lesion={meta.get('lesion_source') or '-'}  "
        f"kept={int(keep.sum())}",
        fontsize=13,
        color="white",
        y=0.98,
    )
    fig.text(
        0.5,
        0.015,
        "Yellow arrows / +across = current serosa side. Cyan dashed = flip cavity side. Not a cT.",
        ha="center",
        fontsize=10,
    )
    fig.tight_layout(rect=[0, 0.05, 1, 0.93])
    dest = out_dir / f"{meta.get('case_id')}_diag.png"
    fig.savefig(dest, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return {
        "display_id": meta.get("display_id"),
        "case_id": meta.get("case_id"),
        "pT_ref": meta.get("pT_ref"),
        "cavity_source": lumen_src,
        "n_kept": int(keep.sum()),
        "n_dropped": int((~keep).sum()) if len(keep) else 0,
        "profile_bdb": bdb,
        "profile_bdb_flipped": bdb_flip,
        "panel": str(dest.relative_to(ROOT)),
        "status": "ok",
    }


def render_index(out_dir: Path, rows: list[dict]) -> Path:
    panels = [ROOT / row["panel"] for row in rows if row.get("panel")]
    if not panels:
        return out_dir / "index.png"
    fig, axes = plt.subplots(len(panels), 1, figsize=(15, 3.15 * len(panels)))
    if len(panels) == 1:
        axes = [axes]
    for ax, path, row in zip(axes, panels, rows):
        ax.imshow(plt.imread(str(path)))
        ax.set_title(
            f"{row.get('display_id')}  cavity={row.get('cavity_source')}  "
            f"profile BDB={row.get('profile_bdb')}  flipped={row.get('profile_bdb_flipped')}",
            fontsize=10,
        )
        ax.axis("off")
    fig.suptitle("Wall cluster diagnostics: cavity side and gray-vs-depth", fontsize=14, y=0.995)
    fig.tight_layout()
    dest = out_dir / "index.png"
    fig.savefig(dest, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="Render wall-cluster cavity-side diagnostics.")
    parser.add_argument("--fixtures", default=str(DEFAULT_FIXTURES))
    parser.add_argument("--compare", default=str(DEFAULT_COMPARE))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    contrast_map = load_contrast(Path(args.compare))
    rows = []
    for meta_path in sorted(Path(args.fixtures).glob("CASE-*/meta.json")):
        row = render_case(load_meta(meta_path), out_dir, contrast_map)
        rows.append(row)
        print(
            f"{row.get('display_id')} cavity={row.get('cavity_source')} "
            f"bdb={row.get('profile_bdb')} flip={row.get('profile_bdb_flipped')} "
            f"kept={row.get('n_kept')}",
            flush=True,
        )
    render_index(out_dir, [row for row in rows if row.get("status") == "ok"])
    (out_dir / "summary.json").write_text(json.dumps({"cases": rows}, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {out_dir / 'index.png'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
