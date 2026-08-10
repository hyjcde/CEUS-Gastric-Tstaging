"""Per-step figure rendering for the deterministic pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

from .gradcam import compute_gradcam_overlay
from .theme import FIGURE_DPI, FIGURE_FACECOLOR, STAGE_COLORS, TEXT_COLOR


def save_lumen_overlay(image_path: str, lumen_obs: Dict[str, Any], out_path: Path) -> Path:
    img = cv2.imread(image_path)
    overlay = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    fig, ax = plt.subplots(figsize=(8, 6))
    fig.patch.set_facecolor(FIGURE_FACECOLOR)
    ax.imshow(overlay)
    mask_path = lumen_obs.get("lumen_mask_png")
    if mask_path:
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask is not None and mask.shape[:2] == img.shape[:2]:
            rgba = np.zeros((*mask.shape, 4), dtype=np.float32)
            rgba[..., 0] = 0.15
            rgba[..., 1] = 0.85
            rgba[..., 2] = 0.75
            rgba[..., 3] = (mask > 127).astype(np.float32) * 0.24
            ax.imshow(rgba)
    polygon = lumen_obs.get("lumen_polygon")
    if isinstance(polygon, list) and len(polygon) >= 3:
        points = np.asarray(polygon, dtype=np.float32)
        if points.ndim == 2 and points.shape[1] >= 2:
            closed = np.vstack([points[:, :2], points[0, :2]])
            ax.plot(closed[:, 0], closed[:, 1], color="#48f3c2", linewidth=2.2)
    bb = lumen_obs.get("lumen_bbox")
    if bb:
        ax.add_patch(
            mpatches.Rectangle(
                (bb["x1"], bb["y1"]),
                bb["x2"] - bb["x1"],
                bb["y2"] - bb["y1"],
                fill=False,
                edgecolor="#7ad2d4",
                linewidth=2.4,
            )
        )
    ax.set_title(
        f"Lumen {lumen_obs.get('lumen_mask_type', 'bbox_proxy')} "
        f"conf={lumen_obs.get('lumen_confidence', 0)}",
        color=TEXT_COLOR,
        loc="left",
    )
    ax.set_xticks([])
    ax.set_yticks([])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=FIGURE_DPI, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return out_path


def save_seg_overlay(
    image_path: str,
    mask_array: Optional[np.ndarray],
    seg_obs: Dict[str, Any],
    out_path: Path,
) -> Path:
    img_rgb = cv2.cvtColor(cv2.imread(image_path), cv2.COLOR_BGR2RGB)
    overlay = img_rgb.copy()
    if mask_array is not None and mask_array.any():
        m = (mask_array > 127).astype(np.uint8)
        for c in range(3):
            overlay[..., c] = np.where(
                m > 0,
                (0.55 * overlay[..., c] + 0.45 * np.array([220, 90, 30])[c]).astype(np.uint8),
                overlay[..., c],
            )
    fig, ax = plt.subplots(figsize=(8, 6))
    fig.patch.set_facecolor(FIGURE_FACECOLOR)
    ax.imshow(overlay)
    ax.set_title(
        f"UNet seg area={seg_obs.get('lesion_area_ratio', 0)}",
        color=TEXT_COLOR,
        loc="left",
    )
    ax.set_xticks([])
    ax.set_yticks([])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=FIGURE_DPI, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return out_path


def save_dual_seg_compare(
    image_path: str,
    seg_obs: Dict[str, Any],
    out_path: Path,
) -> Path:
    """Side-by-side UNet vs DINOv3 masks with selection annotation."""
    img_rgb = cv2.cvtColor(cv2.imread(image_path), cv2.COLOR_BGR2RGB)
    sel = seg_obs.get("selection") or {}
    chosen = sel.get("chosen_backend", "?")

    def _overlay(mask_path: Optional[str], tint: tuple[int, int, int]) -> np.ndarray:
        base = img_rgb.copy()
        if not mask_path:
            return base
        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if mask is None or not mask.any():
            return base
        m = (mask > 127).astype(np.uint8)
        for c in range(3):
            base[..., c] = np.where(
                m > 0,
                (0.55 * base[..., c] + 0.45 * tint[c]).astype(np.uint8),
                base[..., c],
            )
        return base

    unet = seg_obs.get("unet") or {}
    dino = seg_obs.get("dinov3") or {}
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.patch.set_facecolor(FIGURE_FACECOLOR)
    panels = [
        (axes[0], _overlay(unet.get("mask_png"), (220, 90, 30)), "UNet ConvNeXt-B", unet, "unet_score"),
        (axes[1], _overlay(dino.get("mask_png"), (90, 180, 220)), "DINOv3 FM candidate", dino, "dinov3_score"),
    ]
    for ax, img, title, sub, score_key in panels:
        ax.imshow(img)
        ax.set_title(
            f"{title} · area={sub.get('lesion_area_ratio', '?')} · score={sel.get(score_key, '?')}",
            color=TEXT_COLOR,
            fontsize=10,
            loc="left",
        )
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(
        f"Lesion seg compare · chosen={chosen} · {sel.get('rationale', '')}",
        color=TEXT_COLOR,
        fontsize=11,
        y=0.98,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=FIGURE_DPI, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return out_path


def save_classification_panel(
    image_path: str,
    classify_obs: Dict[str, Any],
    clf_tool: Any,
    mask_array: Optional[np.ndarray],
    out_path: Path,
    *,
    roi_path: Optional[str] = None,
    roi_bbox: Optional[Dict[str, int]] = None,
    lumen_bbox: Optional[Dict[str, int]] = None,
) -> Path:
    img_rgb = cv2.cvtColor(cv2.imread(image_path), cv2.COLOR_BGR2RGB)
    gradcam = compute_gradcam_overlay(
        clf_tool,
        Path(image_path),
        mask_array,
        roi_path=roi_path,
        roi_bbox=roi_bbox,
        lumen_bbox=lumen_bbox,
    )
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.patch.set_facecolor(FIGURE_FACECOLOR)
    axes[0].imshow(img_rgb)
    if lumen_bbox:
        bb = lumen_bbox
        axes[0].add_patch(
            mpatches.Rectangle(
                (bb["x1"], bb["y1"]),
                bb["x2"] - bb["x1"],
                bb["y2"] - bb["y1"],
                fill=False,
                edgecolor="#7ad2d4",
                linewidth=2.0,
            )
        )
    axes[0].set_title("Original + lumen ROI", color=TEXT_COLOR)
    if gradcam is not None:
        axes[1].imshow(gradcam)
    else:
        axes[1].imshow(img_rgb)
    probs = classify_obs.get("probabilities") or {}
    labels = ["T1", "T2", "T3", "T4+"]
    y0 = 16
    for i, lab in enumerate(labels):
        v = float(probs.get(lab, 0))
        axes[1].add_patch(
            mpatches.Rectangle((8, y0 + i * 22), v * 120, 16, facecolor=STAGE_COLORS[lab])
        )
        axes[1].text(8 + 120 * v + 4, y0 + i * 22 + 8, f"{lab} {v:.2f}", color=TEXT_COLOR, fontsize=9)
    axes[1].set_title(
        f"L1 local Grad-CAM → {classify_obs.get('top1_stage')} p={classify_obs.get('top1_prob')}",
        color=TEXT_COLOR,
    )
    for ax in axes:
        ax.set_xticks([])
        ax.set_yticks([])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=FIGURE_DPI, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return out_path


def save_rag_panel(rag_obs: Dict[str, Any], out_path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor(FIGURE_FACECOLOR)
    hits = rag_obs.get("similar_cases") or []
    if hits:
        labels = [f"#{h['rank']} {h['patient_id']} ({h['T_stage']})" for h in hits]
        sims = [h["similarity"] for h in hits]
        colors = [STAGE_COLORS.get(h["T_stage"], "#999") for h in hits]
        y_pos = np.arange(len(labels))
        ax.barh(y_pos, sims, color=colors)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, color=TEXT_COLOR)
        ax.invert_yaxis()
    ax.set_title("Case-RAG top-5", color=TEXT_COLOR)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=FIGURE_DPI, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return out_path


def save_binary_panel(binary_obs: Dict[str, Any], image_path: str, out_path: Path) -> Path:
    img_rgb = cv2.cvtColor(cv2.imread(image_path), cv2.COLOR_BGR2RGB)
    fig, ax = plt.subplots(figsize=(8, 5))
    fig.patch.set_facecolor(FIGURE_FACECOLOR)
    ax.imshow(img_rgb)
    probs = binary_obs.get("probabilities") or {}
    y0 = 20
    for i, (lab, v) in enumerate(probs.items()):
        c = STAGE_COLORS.get(str(lab).lower(), "#999")
        ax.add_patch(mpatches.Rectangle((10, y0 + i * 24), float(v) * 100, 18, facecolor=c))
        ax.text(10 + 100 * float(v) + 6, y0 + i * 24 + 9, f"{lab} {float(v):.3f}", color=TEXT_COLOR)
    ax.text(
        10,
        img_rgb.shape[0] - 20,
        f"gate → {binary_obs.get('gate_decision', '?')}",
        color="#9dd0a4" if binary_obs.get("gate_decision") == "skip_t" else "#e09090",
        fontsize=12,
    )
    ax.set_xticks([])
    ax.set_yticks([])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=FIGURE_DPI, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return out_path
