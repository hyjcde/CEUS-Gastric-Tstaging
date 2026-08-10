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
    "save_gc_us_sign_panel",
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
    lumen_mask: Optional[np.ndarray] = None,
    lesion_mask: Optional[np.ndarray] = None,
) -> Optional[Path]:
    """Save SDF heatmap + layer profile from wall_evidence observation."""
    visuals = wall_obs.get("_visuals") or {}
    overlay = visuals.get("wall_overlay_bgr")
    profile = visuals.get("wall_profile")

    if overlay is None and lesion_mask is not None and (lumen_bbox or lumen_mask is not None):
        from ..tools.wall_evidence_tool import render_wall_visuals, signed_distance_from_lumen

        image = cv2.imread(image_path)
        if image is None:
            return None
        h, w = image.shape[:2]
        if lumen_mask is not None:
            lumen_geometry = np.asarray(lumen_mask)
            if lumen_geometry.shape[:2] != (h, w):
                lumen_geometry = cv2.resize(
                    lumen_geometry.astype(np.uint8),
                    (w, h),
                    interpolation=cv2.INTER_NEAREST,
                )
            lumen_geometry = (lumen_geometry > 0).astype(np.uint8) * 255
        else:
            x1, y1, x2, y2 = lumen_bbox["x1"], lumen_bbox["y1"], lumen_bbox["x2"], lumen_bbox["y2"]
            lumen_geometry = np.zeros((h, w), dtype=np.uint8)
            lumen_geometry[y1:y2, x1:x2] = 255
        lesion = (lesion_mask > 127).astype(np.uint8) if lesion_mask is not None else np.zeros((h, w), np.uint8)
        sdf = signed_distance_from_lumen((lumen_geometry > 127).astype(np.uint8))
        visuals = render_wall_visuals(image, lesion, lumen_geometry, sdf, lumen_bbox)
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
        f"Wall SDF / risk={wall_obs.get('penetration_risk', '?')}",
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


def save_gc_us_sign_panel(sign_obs: Dict[str, Any], out_path: Path) -> Optional[Path]:
    """Save the structured sign scorecard beside its directional geometry proxy."""
    explanation = sign_obs.get("explanation") or {}
    geometry_audit = explanation.get("geometry_audit") or {}
    viz = geometry_audit.get("viz") or {}
    contour = np.asarray(viz.get("contour_xy") or [], dtype=np.float32)
    if contour.ndim != 2 or contour.shape[1] < 2:
        contour = np.empty((0, 2), dtype=np.float32)

    items = [
        item for item in (sign_obs.get("items") or [])
        if isinstance(item, dict) and item.get("max") is not None
    ]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.patch.set_facecolor(FIGURE_FACECOLOR)

    ax_geom, ax_score = axes
    if len(contour) >= 3:
        closed = np.vstack([contour[:, :2], contour[0, :2]])
        ax_geom.fill(closed[:, 0], closed[:, 1], color="#d946ef", alpha=0.18)
        ax_geom.plot(closed[:, 0], closed[:, 1], color="#e879f9", linewidth=2)
        lesion_center = np.asarray(viz.get("lesion_center") or [], dtype=np.float32)
        lumen_center = np.asarray(viz.get("lumen_center") or [], dtype=np.float32)
        arrow = np.asarray(viz.get("outward_arrow") or [], dtype=np.float32)
        if lesion_center.size >= 2:
            ax_geom.scatter(lesion_center[0], lesion_center[1], color="#fef08a", s=28, label="lesion center")
        if lumen_center.size >= 2:
            ax_geom.scatter(lumen_center[0], lumen_center[1], color="#67e8f9", s=28, label="lumen center")
        if arrow.size >= 4:
            ax_geom.arrow(
                arrow[0],
                arrow[1],
                arrow[2] - arrow[0],
                arrow[3] - arrow[1],
                color="#bef264",
                width=0.5,
                head_width=4,
                length_includes_head=True,
            )
        ax_geom.invert_yaxis()
        ax_geom.set_aspect("equal", adjustable="box")
        ax_geom.legend(loc="best", fontsize=8, frameon=False)
    else:
        ax_geom.text(0.5, 0.5, "Geometry unavailable", ha="center", va="center", color=TEXT_COLOR)
    ax_geom.set_title("Directional geometry proxy", color=TEXT_COLOR, loc="left")
    ax_geom.set_xticks([])
    ax_geom.set_yticks([])

    if items:
        labels = [str(item.get("id", "sign")) for item in items]
        values = [float(item.get("points") or 0) for item in items]
        maxima = [max(float(item.get("max") or 1), 1.0) for item in items]
        ax_score.barh(labels, maxima, color="#334155", alpha=0.8)
        ax_score.barh(labels, values, color="#a78bfa")
        ax_score.set_xlim(0, max(maxima) * 1.15)
        ax_score.tick_params(axis="y", colors=TEXT_COLOR, labelsize=8)
        ax_score.tick_params(axis="x", colors=TEXT_COLOR, labelsize=8)
    else:
        ax_score.text(0.5, 0.5, "No assessable signs", ha="center", va="center", color=TEXT_COLOR)
    ax_score.set_title(
        f"GC-US sign score, {sign_obs.get('status', 'unknown')}",
        color=TEXT_COLOR,
        loc="left",
    )
    for spine in ax_score.spines.values():
        spine.set_visible(False)

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
