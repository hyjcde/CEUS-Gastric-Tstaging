#!/usr/bin/env python3
"""Record frames, detect lesion near the yellow wall line, show 3 thin layer bands.

No scatter / profile / contrast charts. Offline only. Does not unlock cT.

  python3 scripts/render_wall_layer_thin_bands.py --help
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

from pack_wall_layer_fixture_v1 import PUBLIC_PULL, load_json, nearest_zml_lesion  # noqa: E402
from wall_lesion_aware_cluster import (  # noqa: E402
    DEFAULT_BRUSH,
    as_xy,
    cluster_brush_band,
    densify_polyline,
    flip_outward,
    rasterize_polygon,
    to_gray,
)

DEFAULT_FIXTURES = ROOT / "pipeline/data/wall_layer_fixtures/v1"
DEFAULT_OUT = ROOT / "pipeline/experiments/reports/lesion_aware_wall_cluster_v1/thin_bands"
VIS_DIR = ROOT / "results/visualizations/error_cases"
LESION_WEIGHTS = (
    ROOT
    / "experiments"
    / "detection"
    / "detection_yolo11l_lesion_holdout_cropui_imgsz960_dataset_v20260409_holdout_cropui_20260409_r001"
    / "ultralytics"
    / "weights"
    / "best.pt"
)

# Thin layer colors: shallow / muscularis / serosa
LAYER_RGB = {
    0: (250, 204, 21),
    1: (56, 189, 248),
    2: (74, 222, 128),
}
LAYER_HEX = {0: "#facc15", 1: "#38bdf8", 2: "#4ade80"}
R_LESION = (34, 211, 238)
I_BOX = (248, 113, 113)
WALL = (250, 204, 21)

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


def load_meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_frame(meta: dict) -> Path:
    frame = Path(str(meta.get("frame_path") or ""))
    if not frame.is_absolute():
        frame = ROOT / frame
    return frame


def wall_normals(wall: np.ndarray, lumen_center, lesion_center) -> tuple[np.ndarray, np.ndarray]:
    wall = densify_polyline(as_xy(wall), 2.0)
    if len(wall) < 2:
        return wall, np.zeros((0, 2), dtype=np.float32)
    tan = np.gradient(wall, axis=0)
    nrm = np.zeros_like(wall)
    mid = wall[len(wall) // 2]
    tan_mid = tan[len(wall) // 2]
    seed = flip_outward(mid, tan_mid, lumen_center, lesion_center, None)
    for i, tvec in enumerate(tan):
        nrm[i] = flip_outward(wall[i], tvec, lumen_center, lesion_center, None)
        if float(np.dot(nrm[i], seed)) < 0:
            nrm[i] = -nrm[i]
    return wall, nrm


def unwrap_band(gray: np.ndarray, wall: np.ndarray, nrm: np.ndarray, half_w: float, along_n: int, across_n: int):
    height, width = gray.shape[:2]
    strip = np.zeros((across_n, along_n), dtype=np.float32)
    xs = np.zeros((across_n, along_n), dtype=np.int32)
    ys = np.zeros((across_n, along_n), dtype=np.int32)
    if len(wall) < 2:
        return strip, xs, ys
    idxs = np.linspace(0, len(wall) - 1, along_n)
    for col, t in enumerate(idxs):
        i = int(round(t))
        p = wall[i]
        n = nrm[i]
        for row in range(across_n):
            across = -half_w + (2.0 * half_w * row) / max(1, across_n - 1)
            x = p[0] + n[0] * across
            y = p[1] + n[1] * across
            xi = int(round(x))
            yi = int(round(y))
            xs[row, col] = xi
            ys[row, col] = yi
            if 0 <= xi < width and 0 <= yi < height:
                strip[row, col] = gray[yi, xi]
    return strip, xs, ys


def labels_on_grid(arm, xs: np.ndarray, ys: np.ndarray, shape) -> np.ndarray:
    labmap = np.full(shape[:2], -1, dtype=np.int32)
    if arm is None or getattr(arm, "status", "") != "ok":
        return np.full(xs.shape, -1, dtype=np.int32)
    px = np.asarray(arm.xs, dtype=np.int32)
    py = np.asarray(arm.ys, dtype=np.int32)
    labs = np.asarray(arm.labels, dtype=np.int32)
    ok = (px >= 0) & (py >= 0) & (px < shape[1]) & (py < shape[0])
    labmap[py[ok], px[ok]] = labs[ok]
    xi = np.clip(xs, 0, shape[1] - 1)
    yi = np.clip(ys, 0, shape[0] - 1)
    return labmap[yi, xi]


def colorize_thin_strip(strip: np.ndarray, labels: np.ndarray) -> np.ndarray:
    gray_u8 = np.clip(strip, 0, 255).astype(np.uint8)
    rgb = np.stack([gray_u8, gray_u8, gray_u8], axis=-1).astype(np.float32)
    for lab, color in LAYER_RGB.items():
        sel = labels == lab
        if not sel.any():
            continue
        tint = np.array(color, dtype=np.float32)
        rgb[sel] = 0.42 * rgb[sel] + 0.58 * tint
    return np.clip(rgb, 0, 255).astype(np.uint8)


def crop_around(rgb: np.ndarray, *point_sets, pad: int = 48) -> tuple[np.ndarray, int, int]:
    pts = [as_xy(item) for item in point_sets if item is not None and len(as_xy(item))]
    if not pts:
        return rgb, 0, 0
    all_pts = np.concatenate(pts, axis=0)
    h, w = rgb.shape[:2]
    x1 = max(0, int(all_pts[:, 0].min()) - pad)
    y1 = max(0, int(all_pts[:, 1].min()) - pad)
    x2 = min(w, int(all_pts[:, 0].max()) + pad)
    y2 = min(h, int(all_pts[:, 1].max()) + pad)
    if x2 - x1 < 40 or y2 - y1 < 40:
        return rgb, 0, 0
    return rgb[y1:y2, x1:x2], x1, y1


def draw_polyline(rgb: np.ndarray, pts, color, width: int = 1) -> None:
    arr = as_xy(pts)
    if len(arr) < 2:
        return
    cv2.polylines(rgb, [np.round(arr).astype(np.int32)], False, color, width, cv2.LINE_AA)


def draw_closed(rgb: np.ndarray, pts, color, width: int = 1) -> None:
    arr = as_xy(pts)
    if len(arr) < 3:
        return
    cv2.polylines(rgb, [np.round(arr).astype(np.int32)], True, color, width, cv2.LINE_AA)


def box_polygon(box: dict | None) -> np.ndarray:
    if not box:
        return np.zeros((0, 2), dtype=np.float32)
    return np.array(
        [
            [box["x1"], box["y1"]],
            [box["x2"], box["y1"]],
            [box["x2"], box["y2"]],
            [box["x1"], box["y2"]],
        ],
        dtype=np.float32,
    )


def pick_box_near_wall(result, wall: np.ndarray) -> dict | None:
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return None
    xyxy = boxes.xyxy.cpu().tolist()
    confs = boxes.conf.cpu().tolist() if getattr(boxes, "conf", None) is not None else [0.0] * len(xyxy)
    wall = as_xy(wall)
    best = None
    best_score = -1.0
    for (x1, y1, x2, y2), conf in zip(xyxy, confs):
        cx, cy = 0.5 * (x1 + x2), 0.5 * (y1 + y2)
        if len(wall):
            dist = float(np.min(np.linalg.norm(wall - np.array([cx, cy], dtype=np.float32), axis=1)))
            inside = int(np.any(
                (wall[:, 0] >= x1) & (wall[:, 0] <= x2) & (wall[:, 1] >= y1) & (wall[:, 1] <= y2)
            ))
        else:
            dist, inside = 1e6, 0
        score = float(conf) * (1.8 if inside else 1.0) / (1.0 + dist / 70.0)
        if score > best_score:
            best_score = score
            best = {
                "x1": float(x1),
                "y1": float(y1),
                "x2": float(x2),
                "y2": float(y2),
                "confidence": float(conf),
                "dist_to_wall": round(dist, 1),
                "hits_wall": bool(inside),
            }
    return best


def detect_lesion_near_wall(image_bgr: np.ndarray, wall: np.ndarray, model) -> dict | None:
    results = model.predict(source=image_bgr, imgsz=960, conf=0.20, verbose=False, save=False)
    if not results:
        return None
    return pick_box_near_wall(results[0], wall)


def load_reader_lesion(meta: dict) -> tuple[np.ndarray, str]:
    lesion = as_xy(meta.get("lesion_polygon"))
    source = str(meta.get("lesion_source") or "")
    if len(lesion) >= 3 and source.startswith(("same_frame", "nearest_kf")):
        return lesion, f"R {source}"
    state = load_json(PUBLIC_PULL / "doctor_case_state.json", [])
    if isinstance(state, dict):
        state = state.get("entries") or []
    if not isinstance(state, list):
        state = []
    near, dt, near_id = nearest_zml_lesion(state, str(meta.get("case_id")), float(meta.get("time_sec") or 0.0))
    if len(near) >= 3:
        return as_xy(near), f"R nearby {near_id} dt={dt:.2f}s"
    return lesion, source or "R none"


def choose_arm(gray, wall, lesion_mask, lumen_center, lesion_poly, cavity, brush: float):
    arms = []
    for method in ("kmeans", "ward"):
        arm = cluster_brush_band(
            gray, wall, lesion_mask,
            brush_radius=brush, k=3, dilate_px=5, exclude_lesion=True, method=method,
            lumen_center=lumen_center, lesion_poly=lesion_poly, cavity_side_source=cavity,
        )
        arms.append(arm)
        if getattr(arm, "bright_dark_bright", False):
            return arm
    ok = [arm for arm in arms if getattr(arm, "status", "") == "ok"]
    return ok[0] if ok else arms[0]


def paint_record(image_bgr, wall, r_lesion, i_box, arm) -> np.ndarray:
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    if i_box:
        x1, y1, x2, y2 = (int(round(i_box[k])) for k in ("x1", "y1", "x2", "y2"))
        cv2.rectangle(rgb, (x1, y1), (x2, y2), I_BOX, 2, cv2.LINE_AA)
    draw_closed(rgb, r_lesion, R_LESION, 2)
    draw_polyline(rgb, wall, WALL, 2)
    if arm is not None and getattr(arm, "status", "") == "ok":
        for name, line in (arm.layer_polylines or {}).items():
            color = {"shallow": LAYER_RGB[0], "muscularis": LAYER_RGB[1], "serosa": LAYER_RGB[2]}.get(name, (255, 255, 255))
            draw_polyline(rgb, line, color, 1)
    crop, _, _ = crop_around(rgb, wall, r_lesion, box_polygon(i_box), pad=56)
    return crop


def render_case(meta: dict, model, out_dir: Path, brush: float) -> dict:
    frame_path = resolve_frame(meta)
    image = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
    if image is None:
        return {"case_id": meta.get("case_id"), "status": "missing_frame"}
    gray = to_gray(image)
    wall = as_xy(meta.get("wall_polygon"))
    lumen = as_xy(meta.get("lumen_polygon"))
    lumen_center = lumen.mean(axis=0) if len(lumen) >= 3 else None
    cavity = str(meta.get("cavity_side_source") or "heuristic")
    r_lesion, r_note = load_reader_lesion(meta)
    i_box = detect_lesion_near_wall(image, wall, model) if model is not None else None
    i_poly = box_polygon(i_box)
    if len(i_poly) >= 3:
        lesion_mask = rasterize_polygon(gray.shape, i_poly)
        lesion_poly = i_poly
        exclude_note = "I box"
    elif len(r_lesion) >= 3:
        lesion_mask = rasterize_polygon(gray.shape, r_lesion)
        lesion_poly = r_lesion
        exclude_note = "R polygon"
    else:
        lesion_mask = np.zeros(gray.shape, dtype=np.uint8)
        lesion_poly = np.zeros((0, 2), dtype=np.float32)
        exclude_note = "none"
    arm = choose_arm(gray, wall, lesion_mask, lumen_center, lesion_poly, cavity, brush)
    wall_n, nrm = wall_normals(wall, lumen_center, lesion_poly.mean(axis=0) if len(lesion_poly) else None)
    half_w = max(6.0, min(14.0, float(brush) * 1.15))
    strip, xs, ys = unwrap_band(gray, wall_n, nrm, half_w, along_n=280, across_n=56)
    labels = labels_on_grid(arm, xs, ys, gray.shape)
    color_strip = colorize_thin_strip(strip, labels)
    # Magnify the thin across-wall axis so the 3 bands are readable.
    mag = cv2.resize(color_strip, (color_strip.shape[1] * 3, color_strip.shape[0] * 10), interpolation=cv2.INTER_NEAREST)
    record = paint_record(image, wall, r_lesion, i_box, arm)

    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.4), gridspec_kw={"width_ratios": [1.15, 1.0]})
    axes[0].imshow(record)
    axes[0].set_title("A. Record, yellow line, R lesion, I box", fontsize=12)
    axes[0].axis("off")
    axes[1].imshow(mag, aspect="auto", interpolation="nearest")
    axes[1].set_title("B. Magnified 3 thin bands inside the yellow line", fontsize=12)
    axes[1].axis("off")
    method = getattr(arm, "method", "")
    pattern = getattr(arm, "pattern", "") or "no pattern"
    i_txt = f"I conf={i_box['confidence']:.2f}" if i_box else "I miss"
    fig.suptitle(
        f"{meta.get('display_id')}  pT {meta.get('pT_ref') or '?'}  "
        f"{i_txt}  exclude={exclude_note}  {method} {pattern}",
        fontsize=14,
        y=0.98,
    )
    fig.text(
        0.5,
        0.02,
        "Yellow line = ZML expected wall. Cyan = reader lesion (R). Red box = YOLO on this frame (I). "
        "Yellow / cyan / green bands = shallow / muscularis / serosa. Not a cT.",
        ha="center",
        fontsize=10,
    )
    fig.tight_layout(rect=[0, 0.05, 1, 0.93])
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{meta.get('case_id')}_thin_bands.png"
    fig.savefig(dest, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return {
        "case_id": meta.get("case_id"),
        "display_id": meta.get("display_id"),
        "status": "ok",
        "panel": str(dest),
        "r_note": r_note,
        "i_detected": bool(i_box),
        "i_box": i_box,
        "exclude_note": exclude_note,
        "method": method,
        "pattern": pattern,
        "bright_dark_bright": bool(getattr(arm, "bright_dark_bright", False)),
        "n_valid": int(getattr(arm, "n_valid", 0) or 0),
    }


def render_index(out_dir: Path, panels: list[Path]) -> Path:
    if not panels:
        return out_dir / "wall_layer_thin_bands_20260829.png"
    fig, axes = plt.subplots(len(panels), 1, figsize=(12.4, 3.6 * len(panels)))
    if len(panels) == 1:
        axes = [axes]
    for ax, path in zip(axes, panels):
        ax.imshow(plt.imread(str(path)))
        ax.set_title(path.name.replace("_thin_bands.png", ""), fontsize=11)
        ax.axis("off")
    fig.suptitle("Record + lesion detect + magnified 3-layer bands", fontsize=14, y=0.995)
    fig.tight_layout()
    dest = out_dir / "index.png"
    fig.savefig(dest, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return dest


def load_yolo(skip: bool):
    if skip:
        return None
    if not LESION_WEIGHTS.is_file():
        print(f"lesion weights missing: {LESION_WEIGHTS}", flush=True)
        return None
    from ultralytics import YOLO

    return YOLO(str(LESION_WEIGHTS))


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect lesion on painted frames, then draw 3 thin wall bands.")
    parser.add_argument("--fixtures", default=str(DEFAULT_FIXTURES))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--brush", type=float, default=10.0)
    parser.add_argument("--skip-detect", action="store_true")
    args = parser.parse_args()
    root = Path(args.fixtures)
    out_dir = Path(args.out)
    model = load_yolo(args.skip_detect)
    rows = []
    panels = []
    for meta_path in sorted(root.glob("CASE-*/meta.json")):
        meta = load_meta(meta_path)
        row = render_case(meta, model, out_dir, max(DEFAULT_BRUSH, float(args.brush)))
        rows.append({k: v for k, v in row.items() if k != "i_box"})
        if row.get("panel"):
            panels.append(Path(row["panel"]))
        print(
            f"{row.get('display_id')} I={row.get('i_detected')} "
            f"exclude={row.get('exclude_note')} {row.get('method')} {row.get('pattern')}",
            flush=True,
        )
    index = render_index(out_dir, panels)
    VIS_DIR.mkdir(parents=True, exist_ok=True)
    sheet = VIS_DIR / "wall_layer_thin_bands_20260829.png"
    if index.exists():
        sheet.write_bytes(index.read_bytes())
    for panel in panels:
        (VIS_DIR / panel.name).write_bytes(panel.read_bytes())
    summary = {
        "created_at": "2026-08-29",
        "note": "Record frames, YOLO near the yellow line, 3 thin magnified bands. No charts. Not a cT.",
        "cases": rows,
        "index": str(index),
        "sheet": str(sheet),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {index}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
