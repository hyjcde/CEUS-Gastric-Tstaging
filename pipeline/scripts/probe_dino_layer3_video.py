#!/usr/bin/env python3
"""Sample frames from ultrasound videos and render DINO layer 3 norm (grid row 6)."""

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
import torch
from PIL import Image

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PIPELINE_ROOT.parent
REPO_SCRIPTS = PROJECT_ROOT / "scripts"
PIPELINE_SCRIPTS = Path(__file__).resolve().parent
for path in (str(REPO_SCRIPTS), str(PIPELINE_SCRIPTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from build_dino_layer_ppt_grid import (  # noqa: E402
    DEFAULT_RUN_DIR,
    cmap_to_rgb,
    feature_norm_map,
    load_seg_model,
)

IMAGENET_MEAN = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32).view(3, 1, 1)
IMAGENET_STD = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32).view(3, 1, 1)

DEFAULT_VIDEOS = [
    ("1408594 T3", PROJECT_ROOT / "apps/gastric_scan_next/public/videos/direct_surgery/1048931-1.mp4"),
    ("1379039 T4a", PROJECT_ROOT / "apps/gastric_scan_next/public/videos/direct_surgery/1255929-1.mp4"),
    ("1391229 T4b", PROJECT_ROOT / "apps/gastric_scan_next/public/videos/direct_surgery/1107460.mp4"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "docs/mainline/figures/results/dino_layer3_norm_video_probe_3cases.png",
    )
    parser.add_argument("--frames-per-video", type=int, default=6)
    parser.add_argument("--image-size", type=int, default=512)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--video", action="append", default=[], help="label|path (repeatable)")
    return parser.parse_args()


def resolve_videos(args: argparse.Namespace) -> list[tuple[str, Path]]:
    if args.video:
        out: list[tuple[str, Path]] = []
        for item in args.video:
            label, _, path_str = item.partition("|")
            out.append((label.strip() or Path(path_str).stem, Path(path_str.strip())))
        return out
    return DEFAULT_VIDEOS


def sample_video_frames(video_path: Path, count: int) -> list[tuple[np.ndarray, float, int]]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    if total <= 0:
        cap.release()
        raise ValueError(f"No frames in video: {video_path}")
    indices = np.linspace(0, total - 1, min(count, total), dtype=int)
    frames: list[tuple[np.ndarray, float, int]] = []
    for idx in indices.tolist():
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, bgr = cap.read()
        if not ok or bgr is None:
            continue
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        frames.append((rgb, idx / fps, int(idx)))
    cap.release()
    if not frames:
        raise ValueError(f"Could not decode frames: {video_path}")
    return frames


def preprocess_rgb(rgb: np.ndarray, image_size: int, device: torch.device) -> torch.Tensor:
    image = Image.fromarray(rgb).convert("RGB")
    resized = image.resize((image_size, image_size), Image.BILINEAR)
    arr = np.asarray(resized, dtype=np.float32) / 255.0
    tensor = torch.from_numpy(arr).permute(2, 0, 1).contiguous()
    tensor = (tensor - IMAGENET_MEAN) / IMAGENET_STD
    return tensor.unsqueeze(0).to(device)


@torch.no_grad()
def infer_layer3_norm(model, rgb: np.ndarray, image_size: int) -> np.ndarray:
    import run_dinov3_segmentation as dino_train

    segmenter = dino_train.unwrap_segmenter(model)
    device = next(model.parameters()).device
    tensor = preprocess_rgb(rgb, image_size, device)
    features = segmenter.extract_features(tensor)
    if len(features) <= 3:
        raise RuntimeError("Expected at least 4 fusion layers for layer 3 norm.")
    return feature_norm_map(features[3][0])


def render_panel_grid(
    cases: list[dict],
    output_path: Path,
    *,
    dpi: int = 180,
) -> None:
    n_videos = len(cases)
    n_frames = max(len(case["frames"]) for case in cases)
    fig, axes = plt.subplots(
        n_videos,
        n_frames,
        figsize=(2.4 * n_frames, 2.2 * n_videos),
        squeeze=False,
    )
    fig.suptitle(
        "DINO layer 3 norm (ViT block 11) — video frame probe",
        fontsize=14,
        fontweight="bold",
    )
    for row_i, case in enumerate(cases):
        for col_i in range(n_frames):
            ax = axes[row_i, col_i]
            if col_i >= len(case["frames"]):
                ax.axis("off")
                continue
            rgb, layer3, t_sec, frame_idx = case["frames"][col_i]
            heat = cmap_to_rgb(layer3, "viridis")
            ax.imshow(heat)
            ax.set_title(f"t={t_sec:.1f}s  f={frame_idx}", fontsize=8)
            ax.axis("off")
        axes[row_i, 0].set_ylabel(
            case["label"],
            fontsize=10,
            rotation=0,
            labelpad=42,
            va="center",
        )
    fig.tight_layout(rect=[0.06, 0, 1, 0.96])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def render_compare_grid(
    cases: list[dict],
    output_path: Path,
    *,
    dpi: int = 160,
) -> None:
    """Original + layer3 norm stacked per cell."""
    n_videos = len(cases)
    n_frames = max(len(case["frames"]) for case in cases)
    fig, axes = plt.subplots(
        n_videos * 2,
        n_frames,
        figsize=(2.5 * n_frames, 2.0 * n_videos * 2),
        squeeze=False,
    )
    fig.suptitle(
        "Video probe: Original (crop) vs DINO layer 3 norm (ViT block 11)",
        fontsize=14,
        fontweight="bold",
    )
    for row_i, case in enumerate(cases):
        for col_i in range(n_frames):
            if col_i >= len(case["frames"]):
                axes[row_i * 2, col_i].axis("off")
                axes[row_i * 2 + 1, col_i].axis("off")
                continue
            rgb, layer3, t_sec, frame_idx = case["frames"][col_i]
            heat = cmap_to_rgb(layer3, "viridis")
            axes[row_i * 2, col_i].imshow(rgb)
            axes[row_i * 2, col_i].set_title(f"t={t_sec:.1f}s", fontsize=7)
            axes[row_i * 2, col_i].axis("off")
            axes[row_i * 2 + 1, col_i].imshow(heat)
            axes[row_i * 2 + 1, col_i].axis("off")
        axes[row_i * 2, 0].set_ylabel(
            f"{case['label']}\noriginal",
            fontsize=9,
            rotation=0,
            labelpad=48,
            va="center",
        )
        axes[row_i * 2 + 1, 0].set_ylabel("L3 norm", fontsize=9, rotation=0, labelpad=48, va="center")
    fig.tight_layout(rect=[0.07, 0, 1, 0.96])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    videos = resolve_videos(args)
    device = torch.device(args.device)
    model, image_size, layer_indices = load_seg_model(args.run_dir, device)
    image_size = args.image_size or image_size

    cases: list[dict] = []
    for label, video_path in videos:
        if not video_path.is_file():
            raise FileNotFoundError(video_path)
        sampled = sample_video_frames(video_path, args.frames_per_video)
        frame_rows = []
        for rgb, t_sec, frame_idx in sampled:
            layer3 = infer_layer3_norm(model, rgb, image_size)
            frame_rows.append((rgb, layer3, t_sec, frame_idx))
        cases.append({"label": label, "video_path": str(video_path), "frames": frame_rows})

    out_main = args.output
    out_compare = out_main.with_name(out_main.stem + "_compare" + out_main.suffix)
    render_panel_grid(cases, out_main)
    render_compare_grid(cases, out_compare)

    summary = {
        "run_dir": str(args.run_dir),
        "layer_indices": layer_indices,
        "row_type": "dino_layer3_norm (grid row 6)",
        "outputs": {"layer3_only": str(out_main), "original_vs_layer3": str(out_compare)},
        "cases": [
            {
                "label": case["label"],
                "video_path": case["video_path"],
                "frame_times_sec": [float(f[2]) for f in case["frames"]],
                "frame_indices": [int(f[3]) for f in case["frames"]],
            }
            for case in cases
        ],
    }
    out_main.with_suffix(".json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
