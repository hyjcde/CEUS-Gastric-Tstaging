#!/usr/bin/env python3
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
import yaml
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASE_DIR = (
    PROJECT_ROOT
    / "pipeline"
    / "experiments"
    / "reports"
    / "framelevel_rf_external_by_source"
    / "ext_putian_2024_case_panels_v2"
)
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "segmentation" / "dinov3" / "vitb16_last2blocks_mlp_decoder.yaml"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "pipeline"
    / "experiments"
    / "reports"
    / "framelevel_rf_external_by_source"
    / "ext_putian_2024_dino_token_panels"
)
CLASS_NAMES = ["T1", "T2", "T3", "T4+"]
IMAGENET_MEAN = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32).view(3, 1, 1)
IMAGENET_STD = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32).view(3, 1, 1)
PROB_COLORS = ["#4C78A8", "#F58518", "#54A24B", "#B279A2"]

plt.rcParams.update(
    {
        "font.family": "Times New Roman",
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.labelsize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
    }
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate DINOv3 token heatmap panels for external source cases.")
    parser.add_argument("--case-dir", type=Path, default=DEFAULT_CASE_DIR)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--device", default="cuda:0" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--image-size", type=int, default=512)
    parser.add_argument("--layer-index", type=int, default=11)
    parser.add_argument("--frames-per-case", type=int, default=3)
    parser.add_argument("--max-cases", type=int, default=None)
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return payload


def resolve_path(value: object) -> Path | None:
    if value is None or pd.isna(value) or not str(value).strip():
        return None
    path = Path(str(value))
    if path.exists():
        return path
    if not path.is_absolute():
        candidate = PROJECT_ROOT / path
        if candidate.exists():
            return candidate
    return None


def load_model(config_path: Path, device: torch.device):
    config = load_yaml(config_path)
    paths_cfg = config.get("paths", {})
    model_cfg = config.get("model", {})
    repo = resolve_path(paths_cfg.get("dinov3_repo"))
    ckpt = resolve_path(paths_cfg.get("checkpoint_path"))
    if repo is None or ckpt is None:
        raise FileNotFoundError("Missing DINOv3 repo/checkpoint in config.")
    hub_model = str(model_cfg.get("hub_model", "dinov3_vitb16"))
    model = torch.hub.load(str(repo), hub_model, source="local", weights=str(ckpt))
    return model.to(device).eval(), hub_model


def normalize_map(array: np.ndarray) -> np.ndarray:
    array = np.nan_to_num(array.astype(np.float32))
    lo, hi = np.percentile(array, [1, 99])
    if hi <= lo:
        lo, hi = float(array.min()), float(array.max())
    if hi <= lo:
        return np.zeros_like(array, dtype=np.float32)
    return np.clip((array - lo) / (hi - lo), 0.0, 1.0)


def preprocess_image(path: Path, image_size: int, device: torch.device) -> tuple[torch.Tensor, Image.Image]:
    image = Image.open(path).convert("RGB")
    resized = image.resize((image_size, image_size), Image.BILINEAR)
    arr = np.asarray(resized, dtype=np.float32) / 255.0
    tensor = torch.from_numpy(arr).permute(2, 0, 1).contiguous()
    tensor = (tensor - IMAGENET_MEAN) / IMAGENET_STD
    return tensor.unsqueeze(0).to(device), image


def mask_to_grid(path_value: object, grid_hw: tuple[int, int]) -> np.ndarray | None:
    path = resolve_path(path_value)
    if path is None:
        return None
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return None
    h, w = grid_hw
    small = cv2.resize((mask > 127).astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST).astype(bool)
    return small if small.any() else None


def boundary_grid(mask: np.ndarray | None) -> np.ndarray | None:
    if mask is None:
        return None
    u8 = mask.astype(np.uint8)
    kernel = np.ones((3, 3), dtype=np.uint8)
    ring = (cv2.dilate(u8, kernel, iterations=1) - cv2.erode(u8, kernel, iterations=1)).astype(bool)
    return ring if ring.any() else mask


def pca_first(feature: torch.Tensor) -> np.ndarray:
    c, h, w = feature.shape
    x = feature.reshape(c, h * w).T
    x = x - x.mean(dim=0, keepdim=True)
    _, _, v = torch.linalg.svd(x, full_matrices=False)
    return normalize_map((x @ v[0]).reshape(h, w).detach().cpu().numpy())


def rainbow_pca_official(feature: torch.Tensor, fg_mask: np.ndarray | None) -> np.ndarray:
    """PCA RGB on foreground patches (dinov3/notebooks/pca.ipynb style)."""
    from sklearn.decomposition import PCA

    c, h, w = feature.shape
    x = feature.detach().float().cpu().numpy().reshape(c, h * w).T
    if fg_mask is not None and fg_mask.any():
        fg = fg_mask.reshape(-1)
        fit_x = x[fg]
        fg_3d = fg_mask.astype(np.float32)
    else:
        fit_x = x
        fg_3d = np.ones((h, w), dtype=np.float32)
    if len(fit_x) < 4:
        return np.zeros((h, w, 3), dtype=np.float32)
    pca = PCA(n_components=3, whiten=True)
    pca.fit(fit_x)
    proj = pca.transform(x).reshape(h, w, 3)
    proj = 1.0 / (1.0 + np.exp(-2.0 * proj))
    proj *= fg_3d[..., None]
    return np.clip(proj, 0.0, 1.0).astype(np.float32)


def lesion_query_index(lesion: np.ndarray | None, h: int, w: int) -> tuple[int, int]:
    """Grid (row, col) for lesion centroid; fallback to center."""
    if lesion is None or not lesion.any():
        return h // 2, w // 2
    ys, xs = np.where(lesion)
    return int(np.round(ys.mean())), int(np.round(xs.mean()))


def cosine_map(tokens: np.ndarray, vector: np.ndarray) -> np.ndarray:
    token_norm = np.linalg.norm(tokens, axis=1)
    vector_norm = float(np.linalg.norm(vector))
    if vector_norm <= 1e-8:
        return np.zeros(len(tokens), dtype=np.float32)
    return (tokens @ vector) / np.maximum(token_norm * vector_norm, 1e-8)


def region_mean(tokens: np.ndarray, mask: np.ndarray | None) -> np.ndarray:
    if mask is None:
        return tokens.mean(axis=0)
    return tokens[mask.reshape(-1)].mean(axis=0)


@torch.no_grad()
def infer_dino_maps(model, image_path: Path, row: pd.Series, image_size: int, layer_index: int, device: torch.device) -> dict[str, np.ndarray]:
    tensor, _ = preprocess_image(image_path, image_size, device)
    feature = model.get_intermediate_layers(tensor, n=[layer_index], reshape=True, norm=True)[0][0]
    c, h, w = feature.shape
    tokens = feature.detach().float().cpu().numpy().reshape(c, h * w).T
    lesion = mask_to_grid(row.get("lesion_pred_mask_path") or row.get("mask_path"), (h, w))
    outer = mask_to_grid(row.get("anatomic_outer_wall_mask_path") or row.get("breakthrough_mask_path"), (h, w))
    inner = mask_to_grid(row.get("anatomic_inner_lumen_mask_path"), (h, w))
    boundary = boundary_grid(lesion)

    lesion_vec = region_mean(tokens, lesion)
    outer_vec = region_mean(tokens, outer)
    inner_vec = region_mean(tokens, inner)
    boundary_vec = region_mean(tokens, boundary)

    token_norm = np.linalg.norm(tokens, axis=1).reshape(h, w)
    lesion_aff = cosine_map(tokens, lesion_vec).reshape(h, w)
    boundary_aff = cosine_map(tokens, boundary_vec).reshape(h, w)
    wall_evidence = (cosine_map(tokens, outer_vec) - cosine_map(tokens, inner_vec)).reshape(h, w)
    boundary_minus_lesion = (boundary_aff - lesion_aff).reshape(h, w)
    pca = pca_first(feature)
    rainbow = rainbow_pca_official(feature, lesion)
    qy, qx = lesion_query_index(lesion, h, w)
    query_vec = tokens[qy * w + qx]
    query_cosine = cosine_map(tokens, query_vec).reshape(h, w)

    def upsample(x: np.ndarray) -> np.ndarray:
        return np.asarray(Image.fromarray((normalize_map(x) * 255).astype(np.uint8)).resize((image_size, image_size), Image.BILINEAR)) / 255.0

    def upsample_rgb(x: np.ndarray) -> np.ndarray:
        u8 = (np.clip(x, 0, 1) * 255).astype(np.uint8)
        return np.asarray(Image.fromarray(u8).resize((image_size, image_size), Image.BILINEAR)) / 255.0

    return {
        "token_norm": upsample(token_norm),
        "pca": upsample(pca),
        "rainbow_pca": upsample_rgb(rainbow),
        "query_cosine": upsample(query_cosine),
        "query_xy_grid": (int(qx), int(qy)),
        "lesion_affinity": upsample(lesion_aff),
        "wall_evidence": upsample(wall_evidence),
        "boundary_minus_lesion": upsample(boundary_minus_lesion),
        "token_grid_h": h,
        "token_grid_w": w,
        "input_size": image_size,
    }


def read_image(path_value: object, fallback=(512, 512)) -> Image.Image:
    path = resolve_path(path_value)
    if path is None:
        return Image.new("RGB", fallback, (0, 0, 0))
    return Image.open(path).convert("RGB")


def plot_probs(ax, probs: np.ndarray, title: str) -> None:
    ax.bar(CLASS_NAMES, probs, color=PROB_COLORS)
    ax.set_ylim(0, 1)
    ax.set_title(title)
    ax.tick_params(axis="x", labelrotation=30)
    for idx, value in enumerate(probs):
        ax.text(idx, min(float(value) + 0.03, 0.96), f"{value:.2f}", ha="center", fontsize=8)
    ax.grid(axis="y", alpha=0.2, linestyle="--")


def mark_query_on_axis(ax, maps: dict, image_size: int) -> None:
    """Draw red cross at lesion-centroid query token (scaled to display size)."""
    qx, qy = maps.get("query_xy_grid", (maps["token_grid_w"] // 2, maps["token_grid_h"] // 2))
    h, w = maps["token_grid_h"], maps["token_grid_w"]
    px = (qx + 0.5) / max(w, 1) * image_size
    py = (qy + 0.5) / max(h, 1) * image_size
    ax.plot(px, py, marker="+", markersize=14, markeredgewidth=2.2, color="red")
    ax.plot(px, py, marker="o", markersize=6, markerfacecolor="none", markeredgewidth=1.5, color="red")


def plot_case(model, patient_rows: pd.DataFrame, manifest_row: pd.Series, output_path: Path, args: argparse.Namespace, device: torch.device) -> dict:
    patient_id = str(patient_rows["patient_id"].iloc[0])
    true_label = str(manifest_row["true_label"])
    pred_label = str(manifest_row["pred_label"])
    patient_probs = np.array(json.loads(str(manifest_row["patient_probs"])), dtype=np.float32)
    advanced = patient_rows[[f"prob_{name}" for name in CLASS_NAMES]].to_numpy(dtype=np.float32)[:, 2:].sum(axis=1)
    selected = patient_rows.iloc[np.argsort(advanced)[-min(args.frames_per_case, len(patient_rows)) :][::-1]].copy()
    n = len(selected)
    fig, axes = plt.subplots(nrows=n, ncols=8, figsize=(25, 3.35 * n))
    if n == 1:
        axes = np.array([axes])
    fig.suptitle(
        f"Patient {patient_id} | True: {true_label} | Pred: {pred_label} | "
        f"Patient probabilities: {np.round(patient_probs, 3).tolist()}",
        fontsize=13,
    )
    for row_i, (_, row) in enumerate(selected.iterrows()):
        image_path = resolve_path(row.get("image_path"))
        if image_path is None:
            continue
        original = read_image(image_path)
        overlay = read_image(row.get("anatomic_overlay_path"))
        probs = row[[f"prob_{name}" for name in CLASS_NAMES]].to_numpy(dtype=np.float32)
        maps = infer_dino_maps(model, image_path, row, args.image_size, args.layer_index, device)

        panels = [
            (original, "Original", None),
            (overlay, "Anatomic overlay", None),
            (maps["rainbow_pca"], "Rainbow PCA (official)", None),
            (maps["query_cosine"], "Cosine @ lesion center", "magma"),
            (maps["token_norm"], "DINO token norm", "viridis"),
            (maps["lesion_affinity"], "Lesion region affinity", "magma"),
            (maps["wall_evidence"], "Outer-minus-inner", "coolwarm"),
        ]
        for col_i, (content, title, cmap) in enumerate(panels):
            ax = axes[row_i, col_i]
            if cmap is None and content.ndim == 3:
                ax.imshow(content)
            else:
                ax.imshow(content, cmap=cmap)
            ax.set_title(title)
            ax.axis("off")
            if col_i == 3:
                mark_query_on_axis(ax, maps, maps["input_size"])
        plot_probs(axes[row_i, 7], probs, f"Frame probability\nAdvanced={float(probs[2] + probs[3]):.2f}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(output_path, dpi=170)
    plt.close(fig)
    return {
        "patient_id": patient_id,
        "true_label": true_label,
        "pred_label": pred_label,
        "output_path": str(output_path),
        "frames_shown": int(n),
    }


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    frame_df = pd.read_csv(args.case_dir / "frame_predictions.csv", low_memory=False)
    manifest = pd.read_csv(args.case_dir / "panel_manifest.csv", low_memory=False)
    if args.max_cases is not None:
        manifest = manifest.head(args.max_cases).copy()
    device = torch.device(args.device)
    model, hub_model = load_model(args.config, device)
    rows = []
    for _, manifest_row in manifest.iterrows():
        patient_id = str(manifest_row["patient_id"])
        bucket = str(manifest_row["bucket"])
        patient_rows = frame_df[frame_df["patient_id"].astype(str).eq(patient_id)].copy()
        out = args.output_dir / bucket / f"{patient_id}_{manifest_row['true_label']}_pred_{manifest_row['pred_label']}_dino.png"
        rows.append(plot_case(model, patient_rows, manifest_row, out, args, device))
    out_df = pd.DataFrame(rows)
    out_df.to_csv(args.output_dir / "dino_panel_manifest.csv", index=False)
    summary = {
        "source_case_dir": str(args.case_dir),
        "hub_model": hub_model,
        "layer_index": int(args.layer_index),
        "panel_count": int(len(out_df)),
        "output_dir": str(args.output_dir),
        "maps": [
            "rainbow_pca",
            "query_cosine_lesion_center",
            "token_norm",
            "lesion_affinity",
            "outer_minus_inner_evidence",
        ],
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.output_dir / "README.md").write_text(
        "\n".join(
            [
                "# DINO Token Heatmap Panels",
                "",
                "These are not Grad-CAM panels. They visualize DINOv3 dense token evidence.",
                "",
                "Columns:",
                "",
                "- Original",
                "- Anatomic overlay",
                "- DINO token norm",
                "- DINO PCA-1",
                "- Lesion affinity",
                "- Outer-minus-inner evidence",
                "- Frame probability",
                "",
                "Interpretation:",
                "",
                "- High token norm: DINO salient patch area.",
                "- PCA-1: dominant DINO feature component.",
                "- Lesion affinity: similarity to lesion-region tokens.",
                "- Outer-minus-inner evidence: tokens more similar to outer-wall than inner-control region.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
