"""Multi-panel composite figures for pipeline reports."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

from .gradcam import compute_gradcam_overlay
from .theme import FIGURE_DPI, FIGURE_FACECOLOR, STAGE_COLORS, TEXT_COLOR

if TYPE_CHECKING:
    from ..pipeline.state import CasePipelineState


def _step_obs(state: "CasePipelineState", step_id: str) -> Dict[str, Any]:
    for s in state.steps:
        if s.step_id == step_id:
            return s.observation
    return {}


def _panel_frame(ax, title: str) -> None:
    ax.set_title(title, color=TEXT_COLOR, fontsize=10, loc="left", pad=6)
    ax.set_xticks([])
    ax.set_yticks([])


def render_six_panel(
    state: "CasePipelineState",
    out_path: Path,
    *,
    clf_tool: Optional[Any] = None,
) -> Path:
    """2×3 primary visualization (lumen / seg / L0 / L1+Grad-CAM / wall / RAG)."""
    ci = state.case_input
    image_path = ci.primary_image_path
    img_bgr = cv2.imread(image_path)
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w = img_rgb.shape[:2]

    lumen_obs = _step_obs(state, "lumen_detect")
    seg_obs = _step_obs(state, "lesion_seg")
    binary_obs = (_step_obs(state, "binary_gate").get("primary_frame") or {})
    cls_obs = state.primary_classification or _step_obs(state, "t_staging").get("primary") or {}
    wall_obs = _step_obs(state, "wall_evidence")
    rag_obs = _step_obs(state, "case_rag")

    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.patch.set_facecolor(FIGURE_FACECOLOR)
    fig.suptitle(
        f"{ci.case_id} · patient {ci.patient_id} · GT {ci.gt_t_stage or '?'}",
        color=TEXT_COLOR,
        fontsize=15,
        y=0.98,
    )

    axes[0, 0].imshow(img_rgb)
    _panel_frame(axes[0, 0], f"A · Original ({w}×{h})")

    axes[0, 1].imshow(img_rgb)
    bb = lumen_obs.get("lumen_bbox")
    if bb:
        axes[0, 1].add_patch(
            mpatches.Rectangle(
                (bb["x1"], bb["y1"]),
                bb["x2"] - bb["x1"],
                bb["y2"] - bb["y1"],
                fill=False,
                edgecolor="#7ad2d4",
                linewidth=2.4,
            )
        )
    _panel_frame(axes[0, 1], f"B · Lumen YOLO conf={lumen_obs.get('lumen_confidence', 0)}")

    overlay = img_rgb.copy()
    if state.lesion_mask is not None and state.lesion_mask.any():
        m = (state.lesion_mask > 127).astype(np.uint8)
        for c in range(3):
            overlay[..., c] = np.where(
                m > 0,
                (0.55 * overlay[..., c] + 0.45 * np.array([220, 90, 30])[c]).astype(np.uint8),
                overlay[..., c],
            )
    axes[0, 2].imshow(overlay)
    _panel_frame(axes[0, 2], f"C · UNet seg area={seg_obs.get('lesion_area_ratio', 0)}")

    axes[1, 0].imshow(img_rgb)
    probs = binary_obs.get("probabilities") or {}
    y0 = 16
    for i, (lab, v) in enumerate(probs.items()):
        c = STAGE_COLORS.get(str(lab).lower(), "#999")
        axes[1, 0].add_patch(mpatches.Rectangle((8, y0 + i * 26), float(v) * 120, 18, facecolor=c))
        axes[1, 0].text(8 + 120 * float(v) + 4, y0 + i * 26 + 9, f"{lab} {float(v):.3f}", color=TEXT_COLOR, fontsize=9)
    _panel_frame(axes[1, 0], f"D · L0 gate → {binary_obs.get('gate_decision', '?')}")

    gradcam = None
    if clf_tool is not None:
        gradcam = compute_gradcam_overlay(
            clf_tool,
            Path(image_path),
            state.lesion_mask,
            roi_path=ci.primary_frame.roi_path,
            lumen_bbox=bb if bb else None,
        )
    axes[1, 1].imshow(gradcam if gradcam is not None else img_rgb)
    cp = cls_obs.get("probabilities") or {}
    axes[1, 1].text(
        8, 20,
        " · ".join(f"{k}={float(cp.get(k, 0)):.2f}" for k in ("T1", "T2", "T3", "T4+")),
        color=TEXT_COLOR,
        fontsize=9,
    )
    _panel_frame(axes[1, 1], f"E · L1 → {cls_obs.get('top1_stage')} p={cls_obs.get('top1_prob')}")

    visuals = wall_obs.get("_visuals") or {}
    wall_img = visuals.get("wall_overlay_bgr")
    if wall_img is not None:
        if isinstance(wall_img, list):
            wall_img = np.array(wall_img, dtype=np.uint8)
        axes[1, 2].imshow(cv2.cvtColor(wall_img, cv2.COLOR_BGR2RGB))
    else:
        axes[1, 2].imshow(img_rgb)
    _panel_frame(axes[1, 2], f"F · Wall risk={wall_obs.get('penetration_risk', '?')}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=FIGURE_DPI, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)

    rag_path = out_path.with_name(out_path.stem + "_rag.png")
    if rag_obs.get("similar_cases"):
        from .step_renderers import save_rag_panel

        save_rag_panel(rag_obs, rag_path)

    return out_path
