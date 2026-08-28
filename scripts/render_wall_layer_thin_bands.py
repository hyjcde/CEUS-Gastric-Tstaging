#!/usr/bin/env python3
"""Tight ROI lesion segmentation, then magnify peri-lesion wall layers.

Crop a small ROI around the yellow wall line (P008 drops the empty top).
Segment the whole lesion on that ROI. Overlay the mask in blue. Zoom the
peri-lesion wall and split three thin layers. No charts. Not a cT.

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
sys.path.insert(0, str(ROOT / "pipeline"))

from wall_lesion_aware_cluster import (  # noqa: E402
    DEFAULT_BRUSH,
    as_xy,
    cluster_brush_band,
    densify_polyline,
    to_gray,
)

DEFAULT_FIXTURES = ROOT / "pipeline/data/wall_layer_fixtures/v1"
DEFAULT_OUT = ROOT / "pipeline/experiments/reports/lesion_aware_wall_cluster_v1/thin_bands"
VIS_DIR = ROOT / "results/visualizations/error_cases"
DINO_CFG = ROOT / "configs/segmentation/dinov3/vitb16_roi_lora_mlp_512_m025.yaml"
DINO_CKPT = (
    ROOT
    / "experiments/segmentation/dinov3_vitb16_roi_lora_mlp_512_m025_20260828_full/checkpoints/best.pt"
)

LESION_BLUE = (191, 219, 254)
LAYER_RGB = {
    0: (254, 240, 158),
    1: (254, 215, 170),
    2: (187, 247, 208),
}
WALL = (254, 240, 180)
LAYER_BLEND = 0.18
LESION_BLEND = 0.14

# Tight pads. P008 lesion sits on the lower wall; drop the empty upper sector.
CROP_HINT = {
    "CASE-008": {"pad": 22, "pad_up": 16, "max_h": 170, "drop_above_wall": 18},
    "CASE-019": {"pad": 32, "pad_up": 40, "max_h": 280},
    "CASE-040": {"pad": 28, "pad_up": 72, "max_h": 250},
    "CASE-076": {"pad": 30, "pad_up": 40, "max_h": 280},
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


def load_meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_frame(meta: dict) -> Path:
    frame = Path(str(meta.get("frame_path") or ""))
    return frame if frame.is_absolute() else ROOT / frame


def keep_largest(mask: np.ndarray) -> np.ndarray:
    binary = (mask > 0).astype(np.uint8)
    n_lab, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if n_lab <= 1:
        return (binary * 255).astype(np.uint8)
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return np.where(labels == idx, 255, 0).astype(np.uint8)


def mask_to_polygon(mask: np.ndarray) -> np.ndarray:
    contours, _ = cv2.findContours((mask > 0).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return np.zeros((0, 2), dtype=np.float32)
    pts = max(contours, key=cv2.contourArea)[:, 0, :]
    return pts.astype(np.float32)


def tight_roi(image: np.ndarray, wall: np.ndarray, case_id: str) -> tuple[np.ndarray, int, int, int, int]:
    h, w = image.shape[:2]
    hint = CROP_HINT.get(case_id, {"pad": 28})
    pad = int(hint.get("pad", 28))
    pad_up = int(hint.get("pad_up", pad))
    wall = as_xy(wall)
    if len(wall) < 2:
        return image, 0, 0, w, h
    x1 = max(0, int(np.floor(wall[:, 0].min()) - pad))
    x2 = min(w, int(np.ceil(wall[:, 0].max()) + pad))
    y1 = max(0, int(np.floor(wall[:, 1].min()) - pad_up))
    y2 = min(h, int(np.ceil(wall[:, 1].max()) + pad))
    drop = hint.get("drop_above_wall")
    if drop is not None:
        y1 = max(y1, int(np.floor(wall[:, 1].min()) - int(drop)))
    max_h = hint.get("max_h")
    if max_h and (y2 - y1) > int(max_h):
        mid = 0.5 * (y1 + y2)
        y1 = max(0, int(mid - int(max_h) / 2))
        y2 = min(h, y1 + int(max_h))
    if x2 - x1 < 48 or y2 - y1 < 40:
        return image, 0, 0, w, h
    return image[y1:y2, x1:x2].copy(), x1, y1, x2, y2


def overlay_blue(rgb: np.ndarray, mask: np.ndarray, alpha: float = LESION_BLEND) -> np.ndarray:
    out = rgb.astype(np.float32)
    sel = mask > 0
    if sel.any():
        tint = np.array(LESION_BLUE, dtype=np.float32)
        out[sel] = (1.0 - alpha) * out[sel] + alpha * tint
        contours, _ = cv2.findContours(sel.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(out, contours, -1, LESION_BLUE, 1, cv2.LINE_AA)
    return np.clip(out, 0, 255).astype(np.uint8)


def overlay_layers(rgb: np.ndarray, xs, ys, labels) -> np.ndarray:
    out = rgb.astype(np.float32)
    xs = np.asarray(xs, dtype=np.int32)
    ys = np.asarray(ys, dtype=np.int32)
    labels = np.asarray(labels, dtype=np.int32)
    h, w = out.shape[:2]
    ok = (xs >= 0) & (ys >= 0) & (xs < w) & (ys < h) & (labels >= 0)
    for lab, color in LAYER_RGB.items():
        sel = ok & (labels == lab)
        if not sel.any():
            continue
        out[ys[sel], xs[sel]] = (1.0 - LAYER_BLEND) * out[ys[sel], xs[sel]] + LAYER_BLEND * np.array(color, dtype=np.float32)
    return np.clip(out, 0, 255).astype(np.uint8)


def wall_strip(rgb: np.ndarray, wall: np.ndarray, pad: int = 22) -> tuple[int, int, int, int]:
    """Keep the full painted stroke, including the right-hand start."""
    h, w = rgb.shape[:2]
    wall = as_xy(wall)
    if len(wall) < 2:
        return 0, 0, w, h
    y1 = max(0, int(np.floor(wall[:, 1].min()) - pad))
    y2 = min(h, int(np.ceil(wall[:, 1].max()) + pad))
    if y2 - y1 < 36:
        mid = 0.5 * (y1 + y2)
        y1 = max(0, int(mid - 18))
        y2 = min(h, y1 + 36)
    return 0, y1, w, y2


def peri_zoom(rgb: np.ndarray, wall: np.ndarray, lesion_mask: np.ndarray, scale: int = 5) -> np.ndarray:
    h, w = rgb.shape[:2]
    pts = [as_xy(wall)]
    ys, xs = np.where(lesion_mask > 0)
    if len(xs):
        pts.append(np.stack([xs, ys], axis=1).astype(np.float32))
    all_pts = np.concatenate([p for p in pts if len(p)], axis=0)
    pad = 16
    x1 = max(0, int(all_pts[:, 0].min()) - pad)
    y1 = max(0, int(all_pts[:, 1].min()) - pad)
    x2 = min(w, int(all_pts[:, 0].max()) + pad)
    y2 = min(h, int(all_pts[:, 1].max()) + pad)
    # Prefer a window around the lesion if it exists, so the wall layers sit next to the blue mass.
    if len(xs) >= 20:
        lx1, lx2 = int(xs.min()), int(xs.max())
        ly1, ly2 = int(ys.min()), int(ys.max())
        x1 = max(0, min(x1, lx1 - 20))
        y1 = max(0, min(y1, ly1 - 20))
        x2 = min(w, max(x2, lx2 + 20))
        y2 = min(h, max(y2, ly2 + 20))
        # Cap so the zoom stays on the peri-lesion wall, not the whole stroke.
        cx, cy = int(xs.mean()), int(ys.mean())
        win = 90
        x1, x2 = max(0, cx - win), min(w, cx + win)
        y1, y2 = max(0, cy - win), min(h, cy + win)
    crop = rgb[y1:y2, x1:x2]
    if crop.size == 0:
        return rgb
    return cv2.resize(crop, (crop.shape[1] * scale, crop.shape[0] * scale), interpolation=cv2.INTER_CUBIC)


class RoiSegmenter:
    def __init__(self) -> None:
        self.kind = "none"
        self.dino = None
        self.dino_size = 512
        self.unet = None
        self._try_dino()
        if self.dino is None:
            self._try_unet()

    def _try_dino(self) -> None:
        if not DINO_CFG.is_file() or not DINO_CKPT.is_file():
            return
        try:
            import torch
            from PIL import Image
            from train_dinov3_roi_lora_seg import (
                IMAGENET_MEAN,
                IMAGENET_STD,
                letterbox_pair,
                load_model,
                load_yaml,
                upsample_logits,
            )

            device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
            config = load_yaml(DINO_CFG)
            model, _ = load_model(config, device)
            ckpt = torch.load(DINO_CKPT, map_location="cpu", weights_only=False)
            model.load_state_dict(ckpt["model_state_dict"])
            model.eval()
            self.dino = {
                "model": model,
                "device": device,
                "size": int(config.get("model", {}).get("input_size", 512)),
                "letterbox_pair": letterbox_pair,
                "upsample": upsample_logits,
                "mean": IMAGENET_MEAN,
                "std": IMAGENET_STD,
                "Image": Image,
                "torch": torch,
            }
            self.kind = "dino_roi_lora_m025"
        except Exception as exc:
            print(f"DINO ROI unavailable: {exc}", flush=True)
            self.dino = None

    def _try_unet(self) -> None:
        try:
            from agent.tools.segmentation_tool import SegmentationTool, _predict_mask

            tool = SegmentationTool()
            tool._ensure_model()
            if tool._model is None:
                return
            self.unet = (tool, _predict_mask)
            self.kind = "unet_crop"
        except Exception as exc:
            print(f"UNet unavailable: {exc}", flush=True)

    def segment_crop(self, crop_bgr: np.ndarray) -> np.ndarray:
        dino = np.zeros(crop_bgr.shape[:2], dtype=np.uint8)
        unet = np.zeros(crop_bgr.shape[:2], dtype=np.uint8)
        if self.dino is not None:
            dino = keep_largest(self._dino_mask(crop_bgr))
        if self.unet is None:
            self._try_unet()
        if self.unet is not None:
            tool, predict = self.unet
            unet = keep_largest(predict(tool._model, crop_bgr, tool._device))
        picked, name = self._pick_mask(dino, unet, crop_bgr)
        if name:
            self.kind = name
        return picked

    def _pick_mask(self, dino: np.ndarray, unet: np.ndarray, crop_bgr: np.ndarray) -> tuple[np.ndarray, str]:
        crop_area = int(crop_bgr.shape[0] * crop_bgr.shape[1])
        cands = []
        for name, mask in (("dino_roi_lora_m025", dino), ("unet_crop", unet)):
            area = int((mask > 0).sum())
            if 80 <= area <= int(0.55 * crop_area):
                cands.append((area, mask, name))
        if not cands:
            da, ua = int((dino > 0).sum()), int((unet > 0).sum())
            return (dino if da >= ua else unet), ("dino_roi_lora_m025" if da >= ua else "unet_crop")
        cands.sort(key=lambda item: item[0], reverse=True)
        return cands[0][1], cands[0][2]

    def _dino_mask(self, crop_bgr: np.ndarray) -> np.ndarray:
        pack = self.dino
        torch = pack["torch"]
        Image = pack["Image"]
        size = pack["size"]
        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        dummy = Image.new("L", pil.size)
        boxed_i, _ = pack["letterbox_pair"](pil, dummy, size)
        arr = (np.asarray(boxed_i, dtype=np.float32) / 255.0 - pack["mean"]) / pack["std"]
        tensor = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).to(pack["device"])
        with torch.no_grad():
            logits = pack["upsample"](pack["model"](tensor), (size, size))
            pred = (torch.sigmoid(logits)[0, 0].cpu().numpy() >= 0.5).astype(np.uint8)
        h, w = crop_bgr.shape[:2]
        scale = min(size / max(w, 1), size / max(h, 1))
        nw = max(1, int(round(w * scale)))
        nh = max(1, int(round(h * scale)))
        ox = (size - nw) // 2
        oy = (size - nh) // 2
        inner = pred[oy : oy + nh, ox : ox + nw]
        return cv2.resize(inner, (w, h), interpolation=cv2.INTER_NEAREST) * 255


def choose_arm(
    gray,
    wall,
    lesion_mask,
    lumen_center,
    lesion_poly,
    cavity,
    brush: float,
    method: str = "kmeans1d_gray",
    fit_side: str = "right",
    assign_lesion: bool = False,
):
    return cluster_brush_band(
        gray, wall, lesion_mask,
        brush_radius=brush, k=3, dilate_px=5, exclude_lesion=True, method=method,
        lumen_center=lumen_center, lesion_poly=lesion_poly, cavity_side_source=cavity,
        fit_side=fit_side, assign_lesion=assign_lesion,
    )


def render_case(meta: dict, seg: RoiSegmenter, out_dir: Path, brush: float) -> dict:
    image = cv2.imread(str(resolve_frame(meta)), cv2.IMREAD_COLOR)
    if image is None:
        return {"case_id": meta.get("case_id"), "status": "missing_frame"}
    wall_full = as_xy(meta.get("wall_polygon"))
    lumen = as_xy(meta.get("lumen_polygon"))
    lumen_center = lumen.mean(axis=0) if len(lumen) >= 3 else None
    cavity = str(meta.get("cavity_side_source") or "heuristic")
    crop, x1, y1, x2, y2 = tight_roi(image, wall_full, str(meta.get("case_id")))
    crop_mask = seg.segment_crop(crop)
    full_mask = np.zeros(image.shape[:2], dtype=np.uint8)
    full_mask[y1:y2, x1:x2] = crop_mask
    lesion_poly = mask_to_polygon(full_mask)
    wall_crop = wall_full.copy()
    if len(wall_crop):
        wall_crop[:, 0] -= x1
        wall_crop[:, 1] -= y1
    crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    crop_lumen = None
    if lumen_center is not None:
        crop_lumen = lumen_center - np.array([x1, y1], dtype=np.float32)
    # Fit gray clusters on the full painted stroke. The line starts on the right.
    arm = choose_arm(
        to_gray(crop), wall_crop, crop_mask, crop_lumen, lesion_poly, cavity, brush,
        method="kmeans1d_gray", fit_side="right", assign_lesion=False,
    )

    panel_a = overlay_blue(crop_rgb, crop_mask)
    if len(wall_crop) >= 2:
        cv2.polylines(panel_a, [np.round(wall_crop).astype(np.int32)], False, WALL, 1, cv2.LINE_AA)

    labeled = overlay_blue(crop_rgb.copy(), crop_mask)
    if arm is not None and getattr(arm, "status", "") == "ok":
        labeled = overlay_layers(labeled, arm.xs, arm.ys, arm.labels)
    if len(wall_crop) >= 2:
        cv2.polylines(labeled, [np.round(wall_crop).astype(np.int32)], False, WALL, 1, cv2.LINE_AA)
    sx1, sy1, sx2, sy2 = wall_strip(labeled, wall_crop, pad=20)
    strip = labeled[sy1:sy2, sx1:sx2]
    panel_b = cv2.resize(
        strip,
        (strip.shape[1] * 4, strip.shape[0] * 4),
        interpolation=cv2.INTER_NEAREST,
    )

    time_sec = meta.get("time_sec")
    kf = str(meta.get("zml_keyframe_id") or "")
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 5.4), gridspec_kw={"width_ratios": [1.0, 1.35]})
    axes[0].imshow(panel_a)
    axes[0].set_title(f"A. {time_sec}s painted frame, yellow = ZML wall", fontsize=11)
    axes[0].axis("off")
    axes[1].imshow(panel_b)
    axes[1].set_title("B. Gray k-means from the right; gap = interrupt", fontsize=11)
    axes[1].axis("off")
    area = int((crop_mask > 0).sum())
    fig.suptitle(
        f"{meta.get('display_id')}  {time_sec}s  {kf}  pT {meta.get('pT_ref') or '?'}  "
        f"{seg.kind}  {getattr(arm, 'method', '')} {getattr(arm, 'pattern', '') or ''}",
        fontsize=12,
        y=0.98,
    )
    fig.text(
        0.5,
        0.02,
        f"This is the {time_sec}s cine frame where the expected wall was painted "
        f"({int(meta.get('zml_wall_bands') or 0) or 3} bands, {kf or 'keyframe'}). "
        "Pale colors = gray clusters fit on the right start of the line. "
        "Blue mask pixels stay unlabeled, so the layers interrupt. Not a cT.",
        ha="center",
        fontsize=9,
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
        "seg": seg.kind,
        "mask_px": area,
        "roi": [x1, y1, x2, y2],
        "time_sec": meta.get("time_sec"),
        "zml_keyframe_id": meta.get("zml_keyframe_id"),
        "method": getattr(arm, "method", ""),
        "pattern": getattr(arm, "pattern", ""),
        "fit_side": "right",
        "assign_lesion": False,
        "bright_dark_bright": bool(getattr(arm, "bright_dark_bright", False)),
    }


def render_index(out_dir: Path, panels: list[Path]) -> Path:
    fig, axes = plt.subplots(len(panels), 1, figsize=(12.2, 3.7 * max(1, len(panels))))
    if len(panels) == 1:
        axes = [axes]
    for ax, path in zip(axes, panels):
        ax.imshow(plt.imread(str(path)))
        ax.set_title(path.name.replace("_thin_bands.png", ""), fontsize=11)
        ax.axis("off")
    fig.suptitle("ROI lesion mask + magnified peri-lesion wall layers", fontsize=14, y=0.995)
    fig.tight_layout()
    dest = out_dir / "index.png"
    fig.savefig(dest, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="Segment lesion on a tight wall ROI, then magnify peri-lesion layers.")
    parser.add_argument("--fixtures", default=str(DEFAULT_FIXTURES))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--brush", type=float, default=12.0)
    parser.add_argument("--case", action="append", dest="cases", help="P040 or CASE-040. Repeatable. Default: all.")
    parser.add_argument("--index", action="store_true", help="Also write a 4-case contact sheet.")
    args = parser.parse_args()
    wanted = {str(token).upper().replace("P", "CASE-") if str(token).upper().startswith("P") else str(token).upper() for token in (args.cases or [])}
    wanted = {item if item.startswith("CASE-") else f"CASE-{item}" for item in wanted}
    seg = RoiSegmenter()
    print(f"segmenter={seg.kind}", flush=True)
    rows = []
    panels = []
    for meta_path in sorted(Path(args.fixtures).glob("CASE-*/meta.json")):
        meta = load_meta(meta_path)
        if wanted and str(meta.get("case_id")) not in wanted:
            continue
        row = render_case(meta, seg, Path(args.out), max(DEFAULT_BRUSH, float(args.brush)))
        rows.append(row)
        if row.get("panel"):
            panels.append(Path(row["panel"]))
        print(
            f"{row.get('display_id')} roi={row.get('roi')} mask_px={row.get('mask_px')} "
            f"{row.get('method')} {row.get('pattern')}",
            flush=True,
        )
    VIS_DIR.mkdir(parents=True, exist_ok=True)
    for panel in panels:
        (VIS_DIR / panel.name).write_bytes(panel.read_bytes())
    index_path = ""
    if args.index and panels:
        index_path = str(render_index(Path(args.out), panels))
    (Path(args.out) / "summary.json").write_text(
        json.dumps({"created_at": "2026-08-29", "segmenter": seg.kind, "cases": rows, "index": index_path}, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {len(panels)} panel(s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
