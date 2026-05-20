#!/usr/bin/env python3
"""Build PPT-ready 8-column grid: same layout as Grad-CAM grid, DINO layer rows."""

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
import pandas as pd
import torch
from PIL import Image

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PIPELINE_ROOT.parent
PIPELINE_SCRIPTS = Path(__file__).resolve().parent
REPO_SCRIPTS = PROJECT_ROOT / "scripts"
for path in (str(REPO_SCRIPTS), str(PIPELINE_SCRIPTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

import run_dinov3_segmentation as dino_train  # noqa: E402
from build_gradcam_ppt_grid import find_ppt_assets, letterbox_cell, load_rgb, merge_gradcam_preds  # noqa: E402

IMAGENET_MEAN = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32).view(3, 1, 1)
IMAGENET_STD = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32).view(3, 1, 1)

DEFAULT_RUN_DIR = (
    PROJECT_ROOT
    / "experiments"
    / "segmentation"
    / "dinov3_vitb16_last2blocks_mlp_decoder_cropui_20260512_full_r001"
)

# Same 5-row footprint as t2t3_gradcam_ppt_grid_8x5_multicenter.png; row labels differ.
ROW_SPECS = [
    ("original", "Original\n(crop_ui)", None),
    ("pred_lesion", "Pred lesion\n(DINOv3 seg)", None),
    ("dino_layer1_norm", "DINO layer 1 norm\n(ViT block 5)", "viridis"),
    ("dino_layer2_norm", "DINO layer 2 norm\n(ViT block 8)", "viridis"),
    ("dino_last_pca", "Last token PCA-1\n(ViT block 11)", "coolwarm"),
]

ROW_LABELS = {key: label for key, label, _ in ROW_SPECS}


def normalize_map(array: np.ndarray) -> np.ndarray:
    array = np.nan_to_num(array.astype(np.float32))
    lo, hi = np.percentile(array, [1, 99])
    if hi <= lo:
        lo, hi = float(array.min()), float(array.max())
    if hi <= lo:
        return np.zeros_like(array, dtype=np.float32)
    return np.clip((array - lo) / (hi - lo), 0.0, 1.0)


def pca_first_component(feature: torch.Tensor) -> np.ndarray:
    c, h, w = feature.shape
    x = feature.reshape(c, h * w).T
    x = x - x.mean(dim=0, keepdim=True)
    _, _, v = torch.linalg.svd(x, full_matrices=False)
    comp = (x @ v[0]).reshape(h, w)
    return normalize_map(comp.detach().float().cpu().numpy())


def feature_norm_map(feature: torch.Tensor) -> np.ndarray:
    norm = torch.linalg.vector_norm(feature, ord=2, dim=0)
    return normalize_map(norm.detach().float().cpu().numpy())


def cmap_to_rgb(values: np.ndarray, cmap_name: str) -> np.ndarray:
    cmap = plt.get_cmap(cmap_name)
    rgba = cmap(values)
    return (rgba[..., :3] * 255).astype(np.uint8)


def load_seg_model(run_dir: Path, device: torch.device) -> tuple[torch.nn.Module, int, list[int]]:
    manifest = json.loads((run_dir / "dinov3_run_manifest.json").read_text(encoding="utf-8"))
    config_path = Path(manifest["config_path"])
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    config = dino_train.load_yaml(config_path)
    checkpoint_path = Path(manifest["best_checkpoint"])
    if not checkpoint_path.is_absolute():
        checkpoint_path = PROJECT_ROOT / checkpoint_path
    model = dino_train.build_dinov3_model(config.get("model", {}), config.get("paths", {})).to(device)
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    image_size = int(config.get("model", {}).get("input_size", config.get("train", {}).get("image_size", 512)))
    layer_indices = list(config.get("model", {}).get("decoder", {}).get("layer_indices", [2, 5, 8, 11]))
    return model, image_size, layer_indices


def preprocess(path: Path, image_size: int, device: torch.device) -> torch.Tensor:
    image = Image.open(path).convert("RGB")
    resized = image.resize((image_size, image_size), Image.BILINEAR)
    arr = np.asarray(resized, dtype=np.float32) / 255.0
    tensor = torch.from_numpy(arr).permute(2, 0, 1).contiguous()
    tensor = (tensor - IMAGENET_MEAN) / IMAGENET_STD
    return tensor.unsqueeze(0).to(device)


@torch.no_grad()
def infer_dino_row_maps(
    model: torch.nn.Module,
    image_path: Path,
    image_size: int,
    layer_indices: list[int],
) -> dict[str, np.ndarray]:
    segmenter = dino_train.unwrap_segmenter(model)
    tensor = preprocess(image_path, image_size, next(model.parameters()).device)
    features = segmenter.extract_features(tensor)
    maps: dict[str, np.ndarray] = {}
    if len(features) > 1:
        maps["dino_layer1_norm"] = feature_norm_map(features[1][0])
    if len(features) > 2:
        maps["dino_layer2_norm"] = feature_norm_map(features[2][0])
    if features:
        maps["dino_last_pca"] = pca_first_component(features[-1][0])
    maps["_layer_indices"] = np.array(layer_indices, dtype=np.int32)
    return maps


def render_dino_rows(
    maps: dict[str, np.ndarray],
    image_size: int,
) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    for key, _, cmap_name in ROW_SPECS:
        if cmap_name is None or key not in maps:
            continue
        values = maps[key]
        rgb = cmap_to_rgb(values, cmap_name)
        rgb = np.asarray(Image.fromarray(rgb).resize((image_size, image_size), Image.BILINEAR))
        out[key] = rgb
    return out


def build_dino_grid(
    df: pd.DataFrame,
    gradcam_dir: Path,
    run_dir: Path,
    output_path: Path,
    cache_dir: Path | None,
    *,
    cell_w: int = 480,
    cell_h: int = 300,
    header_h: int = 88,
    label_w: int = 248,
    dpi: int = 200,
    title_font_size: int = 26,
    header_font_size: int = 19,
    row_label_font_size: int = 22,
    title_text: str | None = None,
    device: str = "cuda" if torch.cuda.is_available() else "cpu",
) -> None:
    from build_gradcam_ppt_grid import (  # noqa: E402
        _load_font,
        _text_size,
        column_title_lines,
        draw_multiline_in_box,
    )
    from PIL import ImageDraw

    df = merge_gradcam_preds(df, gradcam_dir)
    n = len(df)
    row_keys = [spec[0] for spec in ROW_SPECS]
    n_rows = len(row_keys)

    torch_device = torch.device(device)
    model, image_size, layer_indices = load_seg_model(run_dir, torch_device)
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)

    title_h = 52
    canvas_w = label_w + n * cell_w
    canvas_h = title_h + header_h + n_rows * cell_h
    canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    if title_text is None:
        blocks = ", ".join(str(i) for i in layer_indices)
        title_text = f"SegDINO multi-layer tokens: crop_ui → seg → layer norms (blocks {blocks})"
    title_font = _load_font(title_font_size, bold=True)
    tw, th = _text_size(draw, title_text, title_font)
    draw.text(
        (label_w + max(0, (n * cell_w - tw) // 2), (title_h - th) // 2),
        title_text,
        font=title_font,
        fill=(0, 0, 0),
        stroke_width=1,
        stroke_fill=(255, 255, 255),
    )

    placeholder = np.full((cell_h, cell_w, 3), 235, dtype=np.uint8)
    y0 = title_h + header_h

    for col, (_, row) in enumerate(df.iterrows()):
        img_path = Path(str(row["image_path"]))
        if not img_path.is_file():
            img_path = PROJECT_ROOT / img_path
        true_label = int(row["label"])
        pred = int(row.get("pred", true_label))
        assets = find_ppt_assets(gradcam_dir, str(row["image_path"]), true_label, pred)
        fallback_orig = load_rgb(img_path)

        dino_rgb: dict[str, np.ndarray] = {}
        cache_stem = img_path.stem
        if cache_dir is not None:
            hit = True
            for key in ("dino_layer1_norm", "dino_layer2_norm", "dino_last_pca"):
                cache_path = cache_dir / f"{cache_stem}_{key}.png"
                if cache_path.is_file():
                    dino_rgb[key] = np.array(Image.open(cache_path).convert("RGB"))
                else:
                    hit = False
            if not hit:
                dino_rgb = {}
        if not dino_rgb and img_path.is_file():
            raw_maps = infer_dino_row_maps(model, img_path, image_size, layer_indices)
            dino_rgb = render_dino_rows(raw_maps, image_size)
            if cache_dir is not None:
                for key, arr in dino_rgb.items():
                    Image.fromarray(arr).save(cache_dir / f"{cache_stem}_{key}.png")

        x_col = label_w + col * cell_w
        header_img = Image.new("RGB", (cell_w, header_h), (255, 255, 255))
        hdraw = ImageDraw.Draw(header_img)
        draw_multiline_in_box(
            hdraw,
            column_title_lines(row),
            (0, 0, cell_w, header_h),
            header_font_size,
            align="center",
            valign="center",
        )
        canvas.paste(header_img, (x_col, title_h))

        for r, key in enumerate(row_keys):
            y_cell = y0 + r * cell_h
            cell_img = None
            if key in dino_rgb:
                cell_img = dino_rgb[key]
            else:
                path = assets.get(key)
                cell_img = load_rgb(path)
            if cell_img is None:
                if key == "original" and fallback_orig is not None:
                    cell_img = fallback_orig
                else:
                    cell_img = placeholder
            cell = letterbox_cell(cell_img, cell_w, cell_h)
            canvas.paste(Image.fromarray(cell), (x_col, y_cell))

    for r, key in enumerate(row_keys):
        y_cell = y0 + r * cell_h
        label_img = Image.new("RGB", (label_w, cell_h), (255, 255, 255))
        ldraw = ImageDraw.Draw(label_img)
        draw_multiline_in_box(
            ldraw,
            ROW_LABELS[key].split("\n"),
            (0, 0, label_w, cell_h),
            row_label_font_size,
            align="right",
            valign="center",
        )
        canvas.paste(label_img, (0, y_cell))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, dpi=(dpi, dpi))
    print(f"Saved: {output_path} ({canvas.size[0]}x{canvas.size[1]})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build DINO layer PPT grid (8 sources, 5 rows)")
    parser.add_argument(
        "--cases-csv",
        type=Path,
        default=PIPELINE_ROOT / "data/tstaging_4class/eval/t2t3_ppt_grid_8sources.csv",
    )
    parser.add_argument(
        "--gradcam-dir",
        type=Path,
        default=PIPELINE_ROOT
        / "experiments/tree/gastric_tstage_4class/classification/dual_mask4ch"
        / "tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301"
        / "gradcam_t2t3_ppt_grid_8sources",
    )
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "docs/mainline/figures/results/t2t3_dino_layer_ppt_grid_8x5_multicenter.png",
    )
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--cell-w", type=int, default=480)
    parser.add_argument("--cell-h", type=int, default=300)
    parser.add_argument("--label-w", type=int, default=248)
    parser.add_argument("--header-h", type=int, default=88)
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--row-label-font", type=int, default=22)
    parser.add_argument("--header-font", type=int, default=19)
    parser.add_argument("--title-font", type=int, default=26)
    parser.add_argument("--title", type=str, default=None)
    parser.add_argument("--device", type=str, default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    df = pd.read_csv(args.cases_csv)
    if "pred" not in df.columns and "pred_class" in df.columns:
        df["pred"] = df["pred_class"]

    build_dino_grid(
        df,
        args.gradcam_dir,
        args.run_dir,
        args.output,
        args.cache_dir,
        cell_w=args.cell_w,
        cell_h=args.cell_h,
        header_h=args.header_h,
        label_w=args.label_w,
        dpi=args.dpi,
        title_font_size=args.title_font,
        header_font_size=args.header_font,
        row_label_font_size=args.row_label_font,
        title_text=args.title,
        device=args.device,
    )

    meta = {
        "cases_csv": str(args.cases_csv),
        "gradcam_dir": str(args.gradcam_dir),
        "seg_run_dir": str(args.run_dir),
        "output": str(args.output),
        "datasets": df["dataset_display"].astype(str).tolist() if "dataset_display" in df.columns else [],
        "row_keys": [spec[0] for spec in ROW_SPECS],
        "row_labels": [spec[1] for spec in ROW_SPECS],
        "font": "Times New Roman Bold",
    }
    args.output.with_suffix(".json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
