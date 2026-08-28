#!/usr/bin/env python3
"""Compare traditional clusterers on ZML wall-lab fixtures.

Same exclude-lesion rule as v1. Methods: k-means, GMM, Ward, FCM,
1D gray k-means, 1D depth k-means. Does not unlock cT. Does not call DINO.

  python3 scripts/eval_lesion_aware_wall_cluster_trad.py --help
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from render_lesion_aware_wall_cluster_panel import (  # noqa: E402
    _crop,
    _overlay_lesion,
    _paint_cluster,
)
from wall_lesion_aware_cluster import (  # noqa: E402
    CLUSTER_METHODS,
    as_xy,
    cluster_brush_band,
    rasterize_polygon,
    to_gray,
)

DEFAULT_FIXTURES = ROOT / "pipeline/data/wall_layer_fixtures/v1"
DEFAULT_OUT = ROOT / "pipeline/experiments/reports/lesion_aware_wall_cluster_trad"
DILATE_PX = 5
K = 3

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


def load_meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_frame(meta: dict) -> Path:
    frame = Path(str(meta.get("frame_path") or ""))
    if not frame.is_absolute():
        frame = ROOT / frame
    return frame


def contrast_from_classes(classes: list[dict]) -> float:
    if len(classes) < 3:
        return 0.0
    grays = [float(item.get("mean_gray") or 0.0) for item in classes[:3]]
    return round(grays[0] + grays[2] - 2.0 * grays[1], 2)


def run_case(meta: dict) -> dict:
    frame_path = resolve_frame(meta)
    image = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
    if image is None:
        return {
            "case_id": meta.get("case_id"),
            "display_id": meta.get("display_id"),
            "status": "missing_frame",
            "skip_reason": "missing_frame",
        }
    gray = to_gray(image)
    lesion = as_xy(meta.get("lesion_polygon"))
    wall = as_xy(meta.get("wall_polygon"))
    lumen = as_xy(meta.get("lumen_polygon"))
    lesion_mask = rasterize_polygon(gray.shape, lesion)
    brush = float(meta.get("brush_radius") or 8)
    lumen_center = lumen.mean(axis=0) if len(lumen) >= 3 else None
    cavity = str(meta.get("cavity_side_source") or "heuristic")
    methods = {}
    for method in CLUSTER_METHODS:
        methods[method] = cluster_brush_band(
            gray, wall, lesion_mask,
            brush_radius=brush, k=K, dilate_px=DILATE_PX, exclude_lesion=True,
            method=method, lumen_center=lumen_center, lesion_poly=lesion,
            cavity_side_source=cavity,
        )
    payload = {
        "case_id": meta.get("case_id"),
        "display_id": meta.get("display_id"),
        "pT_ref": meta.get("pT_ref"),
        "site": meta.get("site"),
        "time_sec": meta.get("time_sec"),
        "wall_source": meta.get("wall_source"),
        "lesion_source": meta.get("lesion_source"),
        "brush_radius": brush,
        "dilate_px": DILATE_PX,
        "status": "ok",
        "methods": {
            key: {
                **arm.summary(),
                "contrast": contrast_from_classes(arm.classes),
            }
            for key, arm in methods.items()
        },
        "bright_dark_bright": {key: arm.bright_dark_bright for key, arm in methods.items()},
        "contrast": {key: contrast_from_classes(arm.classes) for key, arm in methods.items()},
        "_arms": methods,
        "_image": image,
        "_lesion": lesion,
        "_wall": wall,
        "_lesion_mask": lesion_mask,
    }
    return payload


def render_case(out_dir: Path, summary: dict, image, lesion, wall, lesion_mask, arms: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    context = _overlay_lesion(rgb, lesion_mask)
    if len(wall) >= 2:
        cv2.polylines(context, [np.round(wall).astype(np.int32)], False, (250, 204, 21), 2, cv2.LINE_AA)
    cols = [context]
    titles = ["A. Frame, line, lesion"]
    labels = [
        ("kmeans", "B. k-means"),
        ("gmm", "C. GMM"),
        ("ward", "D. Ward"),
        ("fcm", "E. FCM"),
        ("kmeans1d_gray", "F. 1D gray"),
    ]
    for key, title in labels:
        arm = arms.get(key)
        cols.append(_paint_cluster(_overlay_lesion(rgb, lesion_mask), arm))
        tag = getattr(arm, "pattern", "") if arm else ""
        titles.append(f"{title}, {tag or 'no pattern'}")
    fig, axes = plt.subplots(1, len(cols), figsize=(22, 4.8))
    for ax, img, title in zip(axes, cols, titles):
        ax.imshow(_crop(img, lesion, wall))
        ax.set_title(title, fontsize=10)
        ax.axis("off")
    fig.suptitle(
        f"{summary.get('display_id')}  pT {summary.get('pT_ref') or '?'}  "
        f"exclude d={DILATE_PX}, traditional clusterers",
        fontsize=14,
        color="white",
        y=0.98,
    )
    fig.text(
        0.5,
        0.02,
        "Yellow=shallow, blue=muscularis, green=serosa. Fit only outside the lesion. Not a cT.",
        ha="center",
        fontsize=10,
    )
    fig.tight_layout(rect=[0, 0.05, 1, 0.93])
    path = out_dir / f"{summary.get('case_id')}_trad.png"
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


def render_index(out_dir: Path, panels: list[Path]) -> Path:
    if not panels:
        return out_dir / "index.png"
    fig, axes = plt.subplots(len(panels), 1, figsize=(14, 3.1 * len(panels)))
    if len(panels) == 1:
        axes = [axes]
    for ax, path in zip(axes, panels):
        ax.imshow(plt.imread(str(path)))
        ax.set_title(path.name, fontsize=10)
        ax.axis("off")
    fig.suptitle("Traditional wall clusterers, fixture v1, exclude d=5", fontsize=14, y=0.995)
    fig.tight_layout()
    dest = out_dir / "index.png"
    fig.savefig(dest, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return dest


def write_table(out_dir: Path, rows: list[dict]) -> None:
    path = out_dir / "method_comparison.csv"
    fields = [
        "display_id", "case_id", "pT_ref", "method", "status",
        "bright_dark_bright", "contrast", "pattern",
        "shallow_gray", "muscularis_gray", "serosa_gray", "n_valid",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            methods = row.get("methods") or {}
            for method in CLUSTER_METHODS:
                arm = methods.get(method) or {}
                classes = arm.get("classes") or []
                grays = [item.get("mean_gray") for item in classes]
                writer.writerow({
                    "display_id": row.get("display_id"),
                    "case_id": row.get("case_id"),
                    "pT_ref": row.get("pT_ref"),
                    "method": method,
                    "status": arm.get("status") or row.get("status"),
                    "bright_dark_bright": arm.get("bright_dark_bright"),
                    "contrast": arm.get("contrast"),
                    "pattern": arm.get("pattern"),
                    "shallow_gray": grays[0] if len(grays) > 0 else "",
                    "muscularis_gray": grays[1] if len(grays) > 1 else "",
                    "serosa_gray": grays[2] if len(grays) > 2 else "",
                    "n_valid": arm.get("n_valid"),
                })


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare traditional wall clusterers on fixtures.")
    parser.add_argument("--fixtures", default=str(DEFAULT_FIXTURES))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--no-render", action="store_true")
    args = parser.parse_args()
    fixture_root = Path(args.fixtures)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "per_case").mkdir(exist_ok=True)
    metas = sorted(fixture_root.glob("CASE-*/meta.json"))
    if not metas:
        print(f"no fixtures in {fixture_root}", flush=True)
        return 2
    summaries = []
    rendered = []
    for meta_path in metas:
        meta = load_meta(meta_path)
        result = run_case(meta)
        arms = result.pop("_arms", None)
        image = result.pop("_image", None)
        lesion = result.pop("_lesion", None)
        wall = result.pop("_wall", None)
        lesion_mask = result.pop("_lesion_mask", None)
        (out_dir / "per_case" / f"{result['case_id']}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        summaries.append(result)
        if not args.no_render and arms and image is not None:
            rendered.append(render_case(out_dir / "panels", result, image, lesion, wall, lesion_mask, arms))
        hits = result.get("bright_dark_bright") or {}
        print(
            f"{result.get('display_id')} "
            + " ".join(f"{key}={hits.get(key)}" for key in CLUSTER_METHODS),
            flush=True,
        )
    write_table(out_dir, summaries)
    if rendered:
        render_index(out_dir / "panels", rendered)
    summary = {
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_cases": len(summaries),
        "methods": list(CLUSTER_METHODS),
        "dilate_px": DILATE_PX,
        "cases": summaries,
        "note": (
            "Traditional clusterers on ZML wall-lab fixtures. "
            "Fit only outside dilated lesion. Not a cT. Not DINO."
        ),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "README.md").write_text(
        "# lesion_aware_wall_cluster_trad\n\n"
        "Exclude-lesion d=5, k=3. Methods: k-means, GMM, Ward, FCM, "
        "1D gray k-means, 1D depth k-means. Contrast is "
        "shallow + serosa - 2 x muscularis. Not a doctor score.\n",
        encoding="utf-8",
    )
    print(f"wrote {out_dir / 'summary.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
