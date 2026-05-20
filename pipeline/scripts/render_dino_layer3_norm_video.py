#!/usr/bin/env python3
"""Render full-FPS DINO layer 3 norm video from an ultrasound clip."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import numpy as np
import torch
from PIL import Image

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PIPELINE_ROOT.parent
for path in (str(PROJECT_ROOT / "scripts"), str(PIPELINE_ROOT / "scripts")):
    if path not in sys.path:
        sys.path.insert(0, path)

import run_dinov3_segmentation as dino_train  # noqa: E402
from build_dino_layer_ppt_grid import DEFAULT_RUN_DIR, feature_norm_map, load_seg_model  # noqa: E402

IMAGENET_MEAN = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32).view(3, 1, 1)
IMAGENET_STD = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32).view(3, 1, 1)

VIRIDIS_LUT = (matplotlib.colormaps["viridis"](np.linspace(0, 1, 256))[:, :3] * 255).astype(np.uint8)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--video-path",
        type=Path,
        default=PROJECT_ROOT / "apps/gastric_scan_next/public/videos/direct_surgery/1048931-1.mp4",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "docs/mainline/figures/results/dino_layer3_norm_video_1048931-1",
    )
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--image-size", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--frame-step", type=int, default=1, help="1 = every frame (full source FPS)")
    parser.add_argument(
        "--layout",
        choices=("norm", "side_by_side", "overlay"),
        default="side_by_side",
    )
    parser.add_argument("--overlay-alpha", type=float, default=0.55)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    return parser.parse_args()


def preprocess_batch(rgbs: list[np.ndarray], image_size: int, device: torch.device) -> torch.Tensor:
    tensors: list[torch.Tensor] = []
    for rgb in rgbs:
        image = Image.fromarray(rgb).convert("RGB")
        resized = image.resize((image_size, image_size), Image.BILINEAR)
        arr = np.asarray(resized, dtype=np.float32) / 255.0
        tensor = torch.from_numpy(arr).permute(2, 0, 1).contiguous()
        tensor = (tensor - IMAGENET_MEAN) / IMAGENET_STD
        tensors.append(tensor)
    return torch.stack(tensors, dim=0).to(device)


def norm_to_rgb(norm: np.ndarray, out_hw: tuple[int, int]) -> np.ndarray:
    u8 = (np.clip(norm, 0.0, 1.0) * 255.0).astype(np.uint8)
    rgb = VIRIDIS_LUT[u8]
    if rgb.shape[:2] != out_hw:
        rgb = np.asarray(Image.fromarray(rgb).resize((out_hw[1], out_hw[0]), Image.BILINEAR))
    return rgb


@torch.no_grad()
def infer_layer3_norm_batch(
    model: torch.nn.Module,
    rgbs: list[np.ndarray],
    image_size: int,
) -> list[np.ndarray]:
    if not rgbs:
        return []
    segmenter = dino_train.unwrap_segmenter(model)
    device = next(model.parameters()).device
    batch = preprocess_batch(rgbs, image_size, device)
    features = segmenter.extract_features(batch)
    if len(features) <= 3:
        raise RuntimeError("Expected fusion layer 3 for DINO layer 3 norm.")
    layer3 = features[3]
    return [feature_norm_map(layer3[i]) for i in range(layer3.shape[0])]


def compose_frame(
    bgr: np.ndarray,
    norm: np.ndarray,
    *,
    layout: str,
    overlay_alpha: float,
) -> np.ndarray:
    h, w = bgr.shape[:2]
    heat_rgb = norm_to_rgb(norm, (h, w))
    heat_bgr = cv2.cvtColor(heat_rgb, cv2.COLOR_RGB2BGR)
    if layout == "norm":
        return heat_bgr
    if layout == "overlay":
        return cv2.addWeighted(bgr, 1.0 - overlay_alpha, heat_bgr, overlay_alpha, 0)
    # side_by_side
    return np.hstack([bgr, heat_bgr])


def open_video(path: Path) -> tuple[cv2.VideoCapture, float, int, int, int]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        raise ValueError(f"No frames in video: {path}")
    return cap, fps, width, height, total


def render_video(args: argparse.Namespace) -> dict:
    video_path = args.video_path if args.video_path.is_absolute() else PROJECT_ROOT / args.video_path
    if not video_path.is_file():
        raise FileNotFoundError(video_path)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = video_path.stem
    out_mp4 = args.output_dir / f"{stem}_dino_layer3_norm_{args.layout}.mp4"

    cap, fps, width, height, total = open_video(video_path)
    out_fps = fps / max(1, args.frame_step)
    out_w = width * 2 if args.layout == "side_by_side" else width
    out_h = height
    writer = cv2.VideoWriter(
        str(out_mp4),
        cv2.VideoWriter_fourcc(*"mp4v"),
        out_fps,
        (out_w, out_h),
    )
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"Cannot open VideoWriter: {out_mp4}")

    device = torch.device(args.device)
    model, image_size, layer_indices = load_seg_model(args.run_dir, device)
    image_size = args.image_size or image_size

    frame_idx = 0
    written = 0
    batch_bgr: list[np.ndarray] = []
    batch_rgb: list[np.ndarray] = []
    t0 = time.perf_counter()

    while True:
        ok, bgr = cap.read()
        if not ok or bgr is None:
            break
        if frame_idx % args.frame_step != 0:
            frame_idx += 1
            continue
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        batch_bgr.append(bgr)
        batch_rgb.append(rgb)
        if len(batch_rgb) >= args.batch_size:
            norms = infer_layer3_norm_batch(model, batch_rgb, image_size)
            for src_bgr, norm in zip(batch_bgr, norms):
                writer.write(compose_frame(src_bgr, norm, layout=args.layout, overlay_alpha=args.overlay_alpha))
                written += 1
            batch_bgr.clear()
            batch_rgb.clear()
            if written % 32 == 0:
                elapsed = time.perf_counter() - t0
                print(f"  {written} frames written ({written / max(elapsed, 1e-6):.1f} fps infer+write)", flush=True)
        frame_idx += 1

    if batch_rgb:
        norms = infer_layer3_norm_batch(model, batch_rgb, image_size)
        for src_bgr, norm in zip(batch_bgr, norms):
            writer.write(compose_frame(src_bgr, norm, layout=args.layout, overlay_alpha=args.overlay_alpha))
            written += 1

    cap.release()
    writer.release()
    elapsed = time.perf_counter() - t0

    summary = {
        "video_path": str(video_path),
        "output_video": str(out_mp4),
        "layout": args.layout,
        "run_dir": str(args.run_dir),
        "layer": "dino_layer3_norm",
        "vit_block": int(layer_indices[3]) if len(layer_indices) > 3 else 11,
        "layer_indices": layer_indices,
        "source_fps": fps,
        "output_fps": out_fps,
        "frame_step": args.frame_step,
        "source_frames": total,
        "written_frames": written,
        "source_size": [width, height],
        "output_size": [out_w, out_h],
        "batch_size": args.batch_size,
        "image_size": image_size,
        "elapsed_sec": round(elapsed, 2),
        "throughput_fps": round(written / max(elapsed, 1e-6), 2),
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    args = parse_args()
    summary = render_video(args)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
