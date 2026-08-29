#!/usr/bin/env python3
"""Same-grid pixel cluster vs DINO token cluster on the four wall fixtures.

Paints the actual labeled brush pixels. Not parallel offsets. Not a cT.

  python3 scripts/render_wall_pixel_vs_dino_cluster.py --help
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

from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from render_wall_layer_thin_bands import (  # noqa: E402
    DEFAULT_FIXTURES,
    FATE_HEX,
    LAYER_HEX,
    LAYER_LEGEND,
    LAYER_RGB,
    RoiSegmenter,
    VIS_DIR,
    draw_heading,
    fate_rows,
    keep_largest,
    lesion_dt_sec,
    load_meta,
    mask_to_polygon,
    overlay_blue,
    polygon_mask,
    redraw_lesion_on_frame,
    resolve_frame,
    tight_roi,
    wall_strip,
)
from wall_lesion_aware_cluster import (  # noqa: E402
    DEFAULT_BRUSH,
    as_xy,
    cluster_brush_band,
    to_gray,
)

DEFAULT_OUT = ROOT / "pipeline/experiments/reports/lesion_aware_wall_cluster_v1/pixel_vs_dino"
DINO_REPO = ROOT / "external/dinov3/dinov3"
DINO_CKPT = ROOT / "external/dinov3/weights/dinov3_vitb16_pretrain_lvd1689m-73cec8be.pth"
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
DINO_SIZE = 512
DINO_LAYERS = (5, 8)
PCA_DIM = 16
PIXEL_BLEND = 0.055
EDGE_RGB = {
    0: (255, 214, 32),
    1: (244, 63, 94),
    2: (16, 185, 129),
}

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


def letterbox_rgb(rgb: np.ndarray, size: int) -> tuple[np.ndarray, float, int, int]:
    h, w = rgb.shape[:2]
    scale = min(size / max(w, 1), size / max(h, 1))
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    resized = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.zeros((size, size, 3), dtype=np.uint8)
    ox = (size - nw) // 2
    oy = (size - nh) // 2
    canvas[oy : oy + nh, ox : ox + nw] = resized
    return canvas, float(scale), ox, oy


def bilinear_tokens(feat: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    channels, grid_h, grid_w = feat.shape
    fx = np.clip(xs, 0.0, grid_w - 1.001)
    fy = np.clip(ys, 0.0, grid_h - 1.001)
    x0 = np.floor(fx).astype(np.int32)
    y0 = np.floor(fy).astype(np.int32)
    x1 = np.minimum(x0 + 1, grid_w - 1)
    y1 = np.minimum(y0 + 1, grid_h - 1)
    wx = (fx - x0).astype(np.float32)
    wy = (fy - y0).astype(np.float32)
    v00 = feat[:, y0, x0]
    v01 = feat[:, y0, x1]
    v10 = feat[:, y1, x0]
    v11 = feat[:, y1, x1]
    top = v00 * (1.0 - wx) + v01 * wx
    bot = v10 * (1.0 - wx) + v11 * wx
    return ((1.0 - wy) * top + wy * bot).T.astype(np.float32)


class CorridorDino:
    """Frozen official LVD tokens on a wall-corridor letterbox. Not the ROI LoRA seg head."""

    def __init__(self, layers: tuple[int, ...] = DINO_LAYERS, size: int = DINO_SIZE) -> None:
        import torch

        if not DINO_CKPT.is_file():
            raise FileNotFoundError(f"missing official DINOv3 weights: {DINO_CKPT}")
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = torch.hub.load(str(DINO_REPO), "dinov3_vitb16", source="local", weights=str(DINO_CKPT))
        self.torch = torch
        self.model = model.to(device).eval()
        self.device = device
        self.layers = list(layers)
        self.size = size

    def features_at_pixels(self, crop_bgr: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> dict:
        torch = self.torch
        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        boxed, scale, ox, oy = letterbox_rgb(rgb, self.size)
        arr = (boxed.astype(np.float32) / 255.0 - IMAGENET_MEAN) / IMAGENET_STD
        tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to(self.device)
        with torch.no_grad():
            outputs = self.model.get_intermediate_layers(
                tensor, n=self.layers, reshape=True, norm=True,
            )
        maps = [item[0].detach().float().cpu().numpy() for item in outputs]
        stacked = np.concatenate(maps, axis=0)
        lx = np.asarray(xs, dtype=np.float32) * scale + ox
        ly = np.asarray(ys, dtype=np.float32) * scale + oy
        grid_h, grid_w = stacked.shape[1], stacked.shape[2]
        tx = (lx / float(self.size)) * grid_w - 0.5
        ty = (ly / float(self.size)) * grid_h - 0.5
        tokens = bilinear_tokens(stacked, tx, ty)
        token_px = float(self.size / max(grid_w, 1) / max(scale, 1e-6))
        return {"tokens": tokens, "token_px": token_px, "scale": scale, "layers": list(self.layers)}


def pca_reduce(tokens: np.ndarray, fit: np.ndarray, dim: int = PCA_DIM) -> tuple[np.ndarray, float]:
    from sklearn.decomposition import PCA

    if len(tokens) == 0:
        return tokens.astype(np.float32), 0.0
    use = fit if int(fit.sum()) >= 8 else np.ones(len(tokens), dtype=bool)
    n_comp = max(1, min(int(dim), int(use.sum()) - 1, tokens.shape[1]))
    pca = PCA(n_components=n_comp, random_state=7)
    pca.fit(tokens[use])
    out = pca.transform(tokens).astype(np.float32)
    mu = out[use].mean(axis=0)
    sd = out[use].std(axis=0)
    out = (out - mu) / np.maximum(sd, 1e-6)
    explained = float(np.sum(pca.explained_variance_ratio_)) if n_comp else 0.0
    return out, explained


def overlay_cluster_pixels(rgb: np.ndarray, xs, ys, labels, scale: float = 1.0) -> np.ndarray:
    """Very faint strip wash. The gray image must stay readable."""
    out = rgb.astype(np.float32)
    xs = np.asarray(xs, dtype=np.float32)
    ys = np.asarray(ys, dtype=np.float32)
    labels = np.asarray(labels, dtype=np.int32)
    h, w = out.shape[:2]
    cover = np.zeros((h, w), dtype=np.float32)
    wash = np.zeros((h, w, 3), dtype=np.float32)
    radius = max(1, int(round(0.7 * scale)))
    for lab, color in LAYER_RGB.items():
        layer = np.zeros((h, w), dtype=np.uint8)
        for x, y, lab_i in zip(xs.tolist(), ys.tolist(), labels.tolist()):
            if int(lab_i) != lab:
                continue
            ix = int(round(float(x)))
            iy = int(round(float(y)))
            if 0 <= ix < w and 0 <= iy < h:
                cv2.circle(layer, (ix, iy), radius, 255, -1, cv2.LINE_AA)
        sel = layer > 0
        wash[sel] = np.array(color, dtype=np.float32)
        cover[sel] = 1.0
    alpha = (cover * PIXEL_BLEND)[..., None]
    painted = (1.0 - alpha) * out + alpha * wash
    return np.clip(painted, 0, 255).astype(np.uint8)


def overlay_gray_glow(rgb: np.ndarray, gray: np.ndarray, xs, ys, scale: float) -> np.ndarray:
    """Faint highlight on real gray transitions inside the brush."""
    if gray.ndim != 2 or gray.shape[:2] != rgb.shape[:2]:
        return rgb
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    brush = np.zeros(gray.shape, dtype=np.uint8)
    radius = max(1, int(round(1.1 * scale)))
    for x, y in zip(np.asarray(xs).tolist(), np.asarray(ys).tolist()):
        ix, iy = int(round(float(x))), int(round(float(y)))
        if 0 <= ix < gray.shape[1] and 0 <= iy < gray.shape[0]:
            cv2.circle(brush, (ix, iy), radius, 255, -1)
    if not brush.any():
        return rgb
    local = mag[brush > 0]
    thr = float(np.percentile(local, 72)) if len(local) else 20.0
    glow = np.clip((mag - thr) / max(12.0, float(np.percentile(local, 96) - thr)), 0.0, 1.0)
    glow[brush == 0] = 0.0
    alpha = (0.16 * glow)[..., None]
    tint = np.array([248, 250, 252], dtype=np.float32)
    out = (1.0 - alpha) * rgb.astype(np.float32) + alpha * tint
    return np.clip(out, 0, 255).astype(np.uint8)


def draw_interface_lines(rgb: np.ndarray, interfaces, sx1: float, sy1: float, scale: float) -> np.ndarray:
    """Very thin edges sitting on bright-to-dark gray boundaries."""
    out = rgb.copy()
    thick = 1
    for item in interfaces or []:
        pts = np.asarray(item.get("points") or [], dtype=np.float32)
        if len(pts) < 2:
            continue
        pts[:, 0] = (pts[:, 0] - sx1) * scale
        pts[:, 1] = (pts[:, 1] - sy1) * scale
        color = EDGE_RGB.get(int(item.get("edge", 0)), EDGE_RGB[0])
        cv2.polylines(out, [np.round(pts).astype(np.int32)], False, color, thick, cv2.LINE_AA)
    return out


def choose_arm(gray, wall, lesion_mask, lumen_center, lesion_poly, cavity, brush, extra=None, method="kmeans1d_gray"):
    return cluster_brush_band(
        gray, wall, lesion_mask,
        brush_radius=brush, k=3, dilate_px=0, exclude_lesion=True,
        method=method,
        lumen_center=lumen_center, lesion_poly=lesion_poly, cavity_side_source=cavity,
        fit_side="right", assign_lesion=False, sensitive=False,
        extra_features=extra, prefer_strips=True,
    )


def prepare_crop(meta: dict, seg: RoiSegmenter):
    image = cv2.imread(str(resolve_frame(meta)), cv2.IMREAD_COLOR)
    if image is None:
        return None
    wall_full = as_xy(meta.get("wall_polygon"))
    lumen = as_xy(meta.get("lumen_polygon"))
    lumen_center = lumen.mean(axis=0) if len(lumen) >= 3 else None
    cavity = str(meta.get("cavity_side_source") or "heuristic")
    doctor_poly = as_xy(meta.get("lesion_polygon"))
    source = str(meta.get("lesion_source") or "")
    dt = lesion_dt_sec(source)
    redraw = bool(source.startswith("redrawn_")) or (
        len(doctor_poly) >= 3 and (source == "same_frame" or (dt is not None and dt > 0.30))
    )
    crop, x1, y1, x2, y2 = tight_roi(image, wall_full, str(meta.get("case_id")), doctor_poly)
    if redraw and len(doctor_poly) >= 3:
        full_mask, redrawn = redraw_lesion_on_frame(image, doctor_poly, seg)
        if len(redrawn) >= 3:
            doctor_poly = redrawn
            crop, x1, y1, x2, y2 = tight_roi(image, wall_full, str(meta.get("case_id")), doctor_poly)
            crop_mask = full_mask[y1:y2, x1:x2].copy()
            lesion_poly = doctor_poly - np.array([x1, y1], dtype=np.float32)
            mask_source = "redrawn_on_frame"
        else:
            full_mask = polygon_mask(image.shape[:2], doctor_poly)
            crop_mask = full_mask[y1:y2, x1:x2].copy()
            lesion_poly = doctor_poly - np.array([x1, y1], dtype=np.float32)
            mask_source = "doctor_polygon"
    elif len(doctor_poly) >= 3:
        full_mask = polygon_mask(image.shape[:2], doctor_poly)
        crop_mask = full_mask[y1:y2, x1:x2].copy()
        lesion_poly = doctor_poly - np.array([x1, y1], dtype=np.float32)
        mask_source = "doctor_polygon"
    else:
        crop_mask = keep_largest(seg.segment_crop(crop))
        full_mask = np.zeros(image.shape[:2], dtype=np.uint8)
        full_mask[y1:y2, x1:x2] = crop_mask
        lesion_poly = mask_to_polygon(full_mask)
        mask_source = f"model_{seg.kind}"
    wall_crop = wall_full.copy()
    if len(wall_crop):
        wall_crop[:, 0] -= x1
        wall_crop[:, 1] -= y1
    crop_lumen = None
    if lumen_center is not None:
        crop_lumen = lumen_center - np.array([x1, y1], dtype=np.float32)
    return {
        "crop": crop,
        "crop_mask": crop_mask,
        "wall_crop": wall_crop,
        "lesion_poly": lesion_poly,
        "crop_lumen": crop_lumen,
        "cavity": cavity,
        "mask_source": mask_source,
        "meta": meta,
    }


def paint_arm(rgb, gray, arm, sx1, sy1, sx2, sy2, scale: int):
    strip = rgb[sy1:sy2, sx1:sx2]
    panel = cv2.resize(
        strip, (strip.shape[1] * scale, strip.shape[0] * scale), interpolation=cv2.INTER_LINEAR,
    )
    if arm is None or getattr(arm, "status", "") != "ok":
        return panel
    xs = (np.asarray(arm.xs, dtype=np.float32) - sx1) * scale
    ys = (np.asarray(arm.ys, dtype=np.float32) - sy1) * scale
    gray_hi = cv2.resize(
        gray[sy1:sy2, sx1:sx2],
        (panel.shape[1], panel.shape[0]),
        interpolation=cv2.INTER_LINEAR,
    )
    panel = overlay_cluster_pixels(panel, xs, ys, arm.labels, scale=float(scale))
    panel = overlay_gray_glow(panel, gray_hi, xs, ys, scale=float(scale))
    return draw_interface_lines(panel, getattr(arm, "interfaces", None), sx1, sy1, float(scale))


def render_case(pack: dict, dino: CorridorDino, out_dir: Path, brush: float) -> dict:
    meta = pack["meta"]
    crop = pack["crop"]
    crop_mask = pack["crop_mask"]
    wall_crop = pack["wall_crop"]
    gray = to_gray(crop)
    common = dict(
        gray=gray,
        wall=wall_crop,
        lesion_mask=crop_mask,
        lumen_center=pack["crop_lumen"],
        lesion_poly=pack["lesion_poly"],
        cavity=pack["cavity"],
        brush=brush,
    )
    pixel = choose_arm(**common, method="kmeans1d_gray")
    token_info = {"token_px": None, "explained": None, "layers": list(DINO_LAYERS)}
    dino_arm = None
    if pixel.status == "ok" and dino is not None:
        xs = np.asarray(pixel.xs, dtype=np.float32)
        ys = np.asarray(pixel.ys, dtype=np.float32)
        sampled = dino.features_at_pixels(crop, xs, ys)
        keep = np.asarray(pixel.labels, dtype=np.int32) >= 0
        # Fit PCA on the same right-side seed the gray k-means used.
        xs_i = xs.astype(np.int32)
        if keep.any():
            cut = float(np.quantile(xs_i[keep], 0.42))
            fit = keep & (xs_i >= cut)
            if int(fit.sum()) < 40:
                fit = keep
        else:
            fit = keep
        feat, explained = pca_reduce(sampled["tokens"], fit, PCA_DIM)
        dino_arm = choose_arm(**common, extra=feat, method="kmeans")
        token_info = {
            "token_px": round(float(sampled["token_px"]), 2),
            "explained": round(explained, 3),
            "layers": sampled["layers"],
        }

    crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    source = overlay_blue(crop_rgb, crop_mask)
    source = draw_heading(source, wall_crop, crop_mask)
    sx1, sy1, sx2, sy2 = wall_strip(source, wall_crop, pad=20)
    scale = 4
    panel_a = cv2.resize(
        source[sy1:sy2, sx1:sx2],
        ((sx2 - sx1) * scale, (sy2 - sy1) * scale),
        interpolation=cv2.INTER_LINEAR,
    )
    panel_b = paint_arm(overlay_blue(crop_rgb.copy(), crop_mask), gray, pixel, sx1, sy1, sx2, sy2, scale)
    panel_c = paint_arm(overlay_blue(crop_rgb.copy(), crop_mask), gray, dino_arm, sx1, sy1, sx2, sy2, scale)

    fig, axes = plt.subplots(1, 3, figsize=(16.4, 5.6))
    titles = (
        "A  Source",
        "B  Pixel  (gray edges)",
        "C  DINO  (cuts on gray edges)",
    )
    for ax, panel, title in zip(axes, (panel_a, panel_b, panel_c), titles):
        ax.imshow(panel)
        ax.set_title(title, fontsize=12)
        ax.axis("off")
    token_note = ""
    if token_info.get("token_px") is not None:
        token_note = f"    token {token_info['token_px']} px    PCA {token_info['explained']}"
    fig.suptitle(
        f"{meta.get('display_id')}  {meta.get('time_sec')}s  pT {meta.get('pT_ref') or '?'}{token_note}",
        fontsize=13,
        fontname="Times New Roman",
        y=0.98,
    )
    handles = [Patch(facecolor=LAYER_HEX[lab], edgecolor="#6b7280", label=en, alpha=0.35) for lab, _key, en in LAYER_LEGEND]
    handles.append(Line2D([0], [0], color="#fde047", lw=1.2, label="Bright / dark edge"))
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=3,
        frameon=False,
        labelcolor="white",
        fontsize=10,
        bbox_to_anchor=(0.5, 0.02),
        prop={"family": "Times New Roman", "size": 10},
    )
    plates = (
        ("Pixel", fate_rows(list(getattr(pixel, "fates", None) or []))),
        ("DINO", fate_rows(list(getattr(dino_arm, "fates", None) or []))),
    )
    x0 = 0.08
    for name, plate in plates:
        fig.text(x0, 0.086, name, color="#f8fafc", fontsize=11, fontname="Times New Roman", fontweight="bold")
        x = x0 + 0.07
        for _lab, en, status in plate:
            fig.text(
                x, 0.086, f"{en} {status}",
                color=FATE_HEX.get(status, "#e5e7eb"),
                fontsize=10, fontname="Times New Roman",
            )
            x += 0.13
        x0 = 0.54
    fig.tight_layout(rect=[0, 0.12, 1, 0.95])
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{meta.get('case_id')}_pixel_vs_dino.png"
    fig.savefig(dest, dpi=170, bbox_inches="tight")
    plt.close(fig)
    return {
        "case_id": meta.get("case_id"),
        "display_id": meta.get("display_id"),
        "status": "ok",
        "panel": str(dest),
        "mask_source": pack["mask_source"],
        "pixel_status": getattr(pixel, "status", ""),
        "pixel_pattern": getattr(pixel, "pattern", ""),
        "dino_status": getattr(dino_arm, "status", "") if dino_arm is not None else "skipped",
        "dino_pattern": getattr(dino_arm, "pattern", "") if dino_arm is not None else "",
        "token_px": token_info.get("token_px"),
        "pca_explained": token_info.get("explained"),
        "backbone": "lvd1689m",
        "layers": token_info.get("layers"),
        "pixel_fates": list(getattr(pixel, "fates", None) or []),
        "dino_fates": list(getattr(dino_arm, "fates", None) or []) if dino_arm is not None else [],
    }


def render_index(out_dir: Path, panels: list[Path]) -> Path:
    fig, axes = plt.subplots(len(panels), 1, figsize=(15.4, 4.0 * max(1, len(panels))))
    if len(panels) == 1:
        axes = [axes]
    for ax, path in zip(axes, panels):
        ax.imshow(plt.imread(str(path)))
        ax.set_title(path.name.replace("_pixel_vs_dino.png", ""), fontsize=11)
        ax.axis("off")
    fig.suptitle("Pixel cluster vs DINO cluster", fontsize=14, fontname="Times New Roman", y=0.995)
    fig.tight_layout()
    dest = out_dir / "index.png"
    fig.savefig(dest, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare gray pixel clustering with DINO token clustering.")
    parser.add_argument("--fixtures", default=str(DEFAULT_FIXTURES))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--brush", type=float, default=12.0)
    parser.add_argument("--case", action="append", dest="cases")
    parser.add_argument("--index", action="store_true")
    args = parser.parse_args()
    wanted = {str(token).upper().replace("P", "CASE-") if str(token).upper().startswith("P") else str(token).upper() for token in (args.cases or [])}
    wanted = {item if item.startswith("CASE-") else f"CASE-{item}" for item in wanted}
    seg = RoiSegmenter()
    dino = CorridorDino()
    print(f"segmenter={seg.kind}  dino=lvd1689m layers={list(DINO_LAYERS)}", flush=True)
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
        row = render_case(pack, dino, Path(args.out), max(DEFAULT_BRUSH, float(args.brush)))
        rows.append(row)
        if row.get("panel"):
            panels.append(Path(row["panel"]))
        print(
            f"{row.get('display_id')} pixel={row.get('pixel_pattern')} "
            f"dino={row.get('dino_pattern')} token_px={row.get('token_px')}",
            flush=True,
        )
    vis = VIS_DIR
    vis.mkdir(parents=True, exist_ok=True)
    for panel in panels:
        (vis / panel.name).write_bytes(panel.read_bytes())
    index_path = ""
    if args.index and panels:
        index_path = str(render_index(Path(args.out), panels))
        (vis / "wall_pixel_vs_dino_20260829.png").write_bytes(Path(index_path).read_bytes())
    (Path(args.out) / "summary.json").write_text(
        json.dumps(
            {
                "created_at": "2026-08-29",
                "backbone": "lvd1689m",
                "layers": list(DINO_LAYERS),
                "note": "Very faint wash plus thin lines on real gray bright/dark edges. Not a cT.",
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
