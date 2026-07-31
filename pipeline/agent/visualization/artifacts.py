"""Per-step artifact figure writers (lumen overlay, mask, prob bars, wall heatmap)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .step_renderers import (
    save_binary_panel,
    save_classification_panel,
    save_lumen_overlay,
    save_rag_panel,
    save_seg_overlay,
)
from .theme import FIGURE_DPI, FIGURE_FACECOLOR, TEXT_COLOR

__all__ = [
    "save_binary_panel",
    "save_classification_panel",
    "save_lumen_overlay",
    "save_morphology_panel",
    "save_quality_panel",
    "save_rag_panel",
    "save_seg_overlay",
    "save_wall_panel",
]


def save_wall_panel(
    wall_obs: Dict[str, Any],
    image_path: str,
    out_path: Path,
    *,
    lumen_bbox: Optional[Dict[str, int]] = None,
    lesion_mask: Optional[np.ndarray] = None,
) -> Optional[Path]:
    """Save SDF heatmap + layer profile from wall_evidence observation."""
    visuals = wall_obs.get("_visuals") or {}
    overlay = visuals.get("wall_overlay_bgr")
    profile = visuals.get("wall_profile")

    if overlay is None and lesion_mask is not None and lumen_bbox:
        from ..tools.wall_evidence_tool import render_wall_visuals, signed_distance_from_lumen

        image = cv2.imread(image_path)
        if image is None:
            return None
        h, w = image.shape[:2]
        x1, y1, x2, y2 = lumen_bbox["x1"], lumen_bbox["y1"], lumen_bbox["x2"], lumen_bbox["y2"]
        lumen_mask = np.zeros((h, w), dtype=np.uint8)
        lumen_mask[y1:y2, x1:x2] = 255
        lesion = (lesion_mask > 127).astype(np.uint8) if lesion_mask is not None else np.zeros((h, w), np.uint8)
        sdf = signed_distance_from_lumen((lumen_mask > 127).astype(np.uint8))
        visuals = render_wall_visuals(image, lesion, lumen_mask, sdf, lumen_bbox)
        overlay = visuals.get("wall_overlay_bgr")
        profile = visuals.get("wall_profile")

    if overlay is None:
        return None
    if isinstance(overlay, list):
        overlay = np.array(overlay, dtype=np.uint8)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.patch.set_facecolor(FIGURE_FACECOLOR)
    axes[0].imshow(cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB))
    axes[0].set_title(
        f"Wall SDF · risk={wall_obs.get('penetration_risk', '?')}",
        color=TEXT_COLOR,
        loc="left",
    )
    if profile is not None:
        prof = np.array(profile, dtype=np.float32).flatten()
        axes[1].plot(prof, color="#6ee7b7", linewidth=2)
        axes[1].fill_between(np.arange(len(prof)), prof, alpha=0.25, color="#22d3ee")
    axes[1].set_title("Layer profile", color=TEXT_COLOR, loc="left")
    for ax in axes:
        ax.set_xticks([])
        ax.set_yticks([])
    fig.savefig(out_path, dpi=FIGURE_DPI, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return out_path


def save_morphology_panel(morph_obs: Dict[str, Any], out_path: Path) -> Path:
    metrics: Dict[str, float] = {}
    for key in ("convexity", "solidity", "irregularity", "compactness", "boundary_irregularity"):
        val = morph_obs.get(key)
        if val is not None:
            metrics[key.replace("boundary_", "")] = float(val)
    fig, ax = plt.subplots(figsize=(8, 4))
    fig.patch.set_facecolor(FIGURE_FACECOLOR)
    if metrics:
        labels = list(metrics.keys())
        vals = list(metrics.values())
        ax.barh(labels, vals, color="#3b7dd8")
        ax.set_xlim(0, 1.05)
    ax.set_title("Morphology metrics", color=TEXT_COLOR, loc="left")
    ax.tick_params(colors=TEXT_COLOR)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=FIGURE_DPI, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return out_path


def save_quality_panel(quality_obs: Dict[str, Any], image_path: str, out_path: Path) -> Path:
    img_rgb = cv2.cvtColor(cv2.imread(image_path), cv2.COLOR_BGR2RGB)
    score = float(quality_obs.get("quality_score", quality_obs.get("score", 0)))
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    fig.patch.set_facecolor(FIGURE_FACECOLOR)
    axes[0].imshow(img_rgb)
    axes[0].set_title("Primary frame", color=TEXT_COLOR)
    axes[1].barh(["quality"], [score], color="#2c6e3e" if score >= 0.5 else "#c98a2b")
    axes[1].set_xlim(0, 1)
    axes[1].set_title(f"Quality score={score:.2f}", color=TEXT_COLOR)
    for ax in axes:
        ax.set_xticks([])
        ax.set_yticks([])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=FIGURE_DPI, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return out_path
