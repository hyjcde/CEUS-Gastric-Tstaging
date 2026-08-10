"""
WallEvidenceTool — lumen-relative wall penetration evidence from lesion + lumen geometry.

Ported from scripts/analyze_wall_penetration.py (signed distance from lumen).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np
from scipy import ndimage

from .base import BaseTool, ToolParameter
from .lumen_detection_tool import lumen_bbox_from_mask, lumen_mask_from_bbox

logger = logging.getLogger(__name__)


def signed_distance_from_lumen(lumen_mask: np.ndarray) -> np.ndarray:
    """Positive = outside lumen (wall); negative = inside lumen."""
    dist_outside = ndimage.distance_transform_edt(lumen_mask == 0)
    dist_inside = ndimage.distance_transform_edt(lumen_mask > 0)
    return dist_outside - dist_inside


def breakthrough_mask(
    lesion_mask: np.ndarray,
    sdf: np.ndarray,
    threshold: float = 0.3,
) -> np.ndarray:
    """Per-lesion breakthrough mask: 1 where the lesion pixel is far enough
    from the lumen to look "broken through" the wall layers.

    Definition (mirrors ``compute_wall_features.fraction_outside_lumen``):
      breakthrough = (lesion > 0) & (sdf > 0)
      breakthrough_area_ratio = sum(breakthrough) / sum(lesion > 0)
      breakthrough_mask = breakthrough_area_ratio > threshold  (i.e. > 30%
      of the lesion sits outside the lumen)

    Returns a uint8 array {0, 1} of the SAME shape as ``lesion_mask``.
    Background (outside lesion) is always 0; only lesion pixels can be 1.

    Notes
    -----
    - This is a per-IMAGE binary feature: either the whole lesion is
      classified as "breakthrough" (all lesion pixels -> 1) or it is not
      (all lesion pixels -> 0).  The threshold is on the *ratio* of
      outward-extension pixels within the lesion, not on a per-pixel
      SDF value.
    - P0.2-FU-A (1D retry) writes this mask as the 5th channel, replacing
      the 1C SDF channel.  The dataset (wallaux_5ch_dataset.py) only
      reads uint8 PNGs and divides by 255, so it works unchanged for
      {0, 255} PNGs as well as for the {0, 1} int8 intermediate.
    """
    if lesion_mask is None or sdf is None:
        return np.zeros_like(lesion_mask, dtype=np.uint8) if lesion_mask is not None else np.zeros((0, 0), dtype=np.uint8)
    if lesion_mask.shape != sdf.shape:
        raise ValueError(
            f"breakthrough_mask: lesion_mask.shape={lesion_mask.shape} "
            f"!= sdf.shape={sdf.shape}"
        )
    lesion_bin = (lesion_mask > 127).astype(np.uint8)
    if lesion_bin.sum() == 0:
        return np.zeros_like(lesion_bin, dtype=np.uint8)
    outward = (sdf > 0).astype(np.uint8)
    # Per-image ratio:  fraction of lesion pixels that lie OUTSIDE the lumen.
    ratio = float((outward & lesion_bin).sum()) / float(lesion_bin.sum())
    mask = np.zeros_like(lesion_bin, dtype=np.uint8)
    if ratio > threshold:
        mask[lesion_bin > 0] = 1
    return mask


def compute_wall_features(
    lesion_mask: np.ndarray,
    lumen_mask: np.ndarray,
    sdf: np.ndarray,
) -> Dict[str, float]:
    lesion_bin = (lesion_mask > 127).astype(np.uint8)
    lumen_bin = (lumen_mask > 127).astype(np.uint8)
    lesion_depths = sdf[lesion_bin > 0]
    if lesion_depths.size == 0:
        return {
            "lesion_area_px": 0.0,
            "lumen_area_px": float(lumen_bin.sum()),
            "max_outward_depth": 0.0,
            "mean_outward_depth": 0.0,
            "fraction_outside_lumen": 0.0,
            "fraction_inside_lumen": 0.0,
            "contact_arc_ratio": 0.0,
        }

    outward = lesion_depths[lesion_depths > 0]
    lumen_boundary = cv2.Canny(lumen_bin * 255, 50, 150) > 0
    lesion_dilated = cv2.dilate(lesion_bin, np.ones((7, 7), np.uint8), iterations=1)
    contact = lumen_boundary & (lesion_dilated > 0)
    lumen_perimeter = max(int(lumen_boundary.sum()), 1)

    return {
        "lesion_area_px": float(lesion_bin.sum()),
        "lumen_area_px": float(lumen_bin.sum()),
        "max_outward_depth": float(lesion_depths.max()),
        "mean_outward_depth": float(outward.mean()) if outward.size else 0.0,
        "fraction_outside_lumen": float((lesion_depths > 0).sum()) / float(lesion_depths.size),
        "fraction_inside_lumen": float((lesion_depths < 0).sum()) / float(lesion_depths.size),
        "contact_arc_ratio": float(contact.sum()) / float(lumen_perimeter),
    }


def bbox_geometry_quality(
    lumen_bbox: Dict[str, int],
    image_height: int,
    image_width: int,
) -> tuple[float, list[str]]:
    """Score whether a lumen bbox is usable for a geometry-only proxy."""
    flags: list[str] = []
    try:
        x1 = float(lumen_bbox["x1"])
        y1 = float(lumen_bbox["y1"])
        x2 = float(lumen_bbox["x2"])
        y2 = float(lumen_bbox["y2"])
    except (KeyError, TypeError, ValueError):
        return 0.0, ["invalid_bbox_coordinates"]

    width = x2 - x1
    height = y2 - y1
    if width <= 0 or height <= 0:
        return 0.0, ["non_positive_bbox_area"]

    score = 1.0
    if x1 < 0 or y1 < 0 or x2 > image_width or y2 > image_height:
        score -= 0.25
        flags.append("bbox_out_of_bounds")
    area_ratio = (width * height) / max(float(image_height * image_width), 1.0)
    if area_ratio < 0.02:
        score -= 0.30
        flags.append("bbox_too_small")
    elif area_ratio > 0.85:
        score -= 0.35
        flags.append("bbox_too_large")
    if width < 16 or height < 16:
        score -= 0.20
        flags.append("bbox_low_resolution")
    return max(0.0, min(1.0, score)), flags


def render_wall_visuals(
    image_bgr: np.ndarray,
    lesion_mask: Optional[np.ndarray],
    lumen_mask: np.ndarray,
    sdf: np.ndarray,
    lumen_bbox: Optional[Dict[str, int]],
) -> Dict[str, Any]:
    """Build heatmap overlay and horizontal wall-depth profile for UI."""
    h, w = image_bgr.shape[:2]
    sdf_pos = np.clip(sdf, 0, None)
    if sdf_pos.max() > 0:
        risk_norm = cv2.normalize(sdf_pos, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    else:
        risk_norm = np.zeros((h, w), dtype=np.uint8)

    heatmap = cv2.applyColorMap(risk_norm, cv2.COLORMAP_INFERNO)
    overlay = cv2.addWeighted(image_bgr, 0.48, heatmap, 0.52, 0)
    if lumen_bbox:
        cv2.rectangle(
            overlay,
            (lumen_bbox["x1"], lumen_bbox["y1"]),
            (lumen_bbox["x2"], lumen_bbox["y2"]),
            (255, 180, 0),
            2,
        )
    cv2.putText(
        overlay,
        "Wall evidence (lumen SDF)",
        (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
    )

    profile: Optional[np.ndarray] = None
    if lumen_bbox:
        x1, x2 = lumen_bbox["x1"], lumen_bbox["x2"]
        strip = sdf_pos[:, max(0, x1) : min(w, x2)]
        if strip.size:
            profile = strip.mean(axis=1)
    if profile is None or profile.size == 0:
        profile = sdf_pos.mean(axis=1)
    if profile.max() > 0:
        profile = profile / profile.max()

    return {
        "wall_overlay_bgr": overlay,
        "wall_profile": profile.astype(np.float32),
        "risk_norm": risk_norm,
    }


class WallEvidenceTool(BaseTool):
    name = "wall_evidence"
    description = (
        "Compute proxy gastric wall penetration evidence from a lesion mask and "
        "lumen geometry. A confirmed lumen mask is preferred over the detector box. "
        "This is not a pathological wall-layer estimate."
    )
    parameters = [
        ToolParameter("image_path", "str", "Absolute path to ultrasound image"),
        ToolParameter("lumen_bbox", "dict", "Lumen bounding box {x1,y1,x2,y2}", required=False),
        ToolParameter("lumen_mask", "ndarray", "Confirmed lumen mask (H,W)", required=False),
        ToolParameter("lesion_mask", "ndarray", "Binary lesion mask (H,W)", required=False),
    ]

    def execute(
        self,
        image_path: str,
        lumen_bbox: Optional[Dict[str, int]] = None,
        lumen_mask: Optional[np.ndarray] = None,
        lesion_mask: Optional[np.ndarray] = None,
        lumen_mask_source: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        image = cv2.imread(image_path)
        if image is None:
            return {
                "available": False,
                "error": "Could not read image",
                "evidence_role": "proxy_geometry_unavailable",
            }

        h, w = image.shape[:2]
        if lumen_bbox is None and lumen_mask is None:
            return {
                "available": False,
                "evidence_source": "missing_lumen",
                "evidence_role": "proxy_geometry_unavailable",
                "error": "lumen_bbox or lumen_mask required for wall evidence",
                "image_height": h,
                "image_width": w,
            }

        if lesion_mask is None:
            return {
                "available": False,
                "evidence_source": "missing_lesion_mask",
                "evidence_role": "proxy_geometry_unavailable",
                "error": "lesion_mask required for wall evidence",
                "image_height": h,
                "image_width": w,
            }

        exact_lumen_mask = None
        if lumen_mask is not None:
            exact_lumen_mask = np.asarray(lumen_mask)
            if exact_lumen_mask.ndim == 3:
                exact_lumen_mask = exact_lumen_mask[..., 0]
            if exact_lumen_mask.shape[:2] != (h, w):
                exact_lumen_mask = cv2.resize(
                    exact_lumen_mask.astype(np.uint8),
                    (w, h),
                    interpolation=cv2.INTER_NEAREST,
                )
            exact_lumen_mask = (exact_lumen_mask > 0).astype(np.uint8) * 255
            if not np.any(exact_lumen_mask):
                exact_lumen_mask = None
            else:
                mask_bbox = lumen_bbox_from_mask(exact_lumen_mask)
                if mask_bbox is not None:
                    lumen_bbox = mask_bbox

        if lumen_bbox is None:
            return {
                "available": False,
                "evidence_source": "invalid_lumen_geometry",
                "evidence_role": "proxy_geometry_unavailable",
                "error": "Lumen mask and bbox are both invalid",
                "image_height": h,
                "image_width": w,
            }

        bbox_quality, quality_flags = bbox_geometry_quality(lumen_bbox, h, w)
        lesion = lesion_mask.astype(np.uint8)
        if lesion.shape[:2] != (h, w):
            lesion = cv2.resize(lesion, (w, h), interpolation=cv2.INTER_NEAREST)
        if lesion.max() <= 1:
            lesion = lesion * 255

        geometry_mask = (
            exact_lumen_mask
            if exact_lumen_mask is not None
            else lumen_mask_from_bbox(lumen_bbox, h, w)
        )
        if not np.any(geometry_mask > 0):
            return {
                "available": False,
                "evidence_source": "empty_lumen_mask",
                "evidence_role": "proxy_geometry_unavailable",
                "error": "Invalid lumen bbox",
                "image_height": h,
                "image_width": w,
            }

        sdf = signed_distance_from_lumen((geometry_mask > 127).astype(np.uint8))
        features = compute_wall_features(lesion, geometry_mask, sdf)
        visuals = render_wall_visuals(image, lesion, geometry_mask, sdf, lumen_bbox)

        contact_arc_ratio = float(features.get("contact_arc_ratio", 0.0))
        proxy_quality = bbox_quality
        if contact_arc_ratio <= 0.01:
            proxy_quality = min(proxy_quality, 0.35)
            quality_flags.append("lesion_not_contacting_lumen_boundary")
        elif contact_arc_ratio < 0.03:
            proxy_quality = min(proxy_quality, 0.55)
            quality_flags.append("weak_lesion_lumen_contact")

        penetration_risk = "low"
        frac_out = features.get("fraction_outside_lumen", 0.0)
        if proxy_quality < 0.55:
            penetration_risk = "uncertain"
        elif frac_out >= 0.5 or features.get("max_outward_depth", 0.0) >= 15:
            penetration_risk = "high"
        elif frac_out >= 0.2 or features.get("max_outward_depth", 0.0) >= 8:
            penetration_risk = "medium"

        return {
            "available": True,
            "evidence_source": (
                "confirmed_lumen_mask_signed_distance"
                if exact_lumen_mask is not None
                else "lumen_bbox_proxy_signed_distance"
            ),
            "evidence_role": "proxy_geometry",
            "penetration_risk": penetration_risk,
            "risk_semantics": "proxy_only_not_pathological_layer_truth",
            "wall_layer_estimate": False,
            "proxy_quality_score": round(float(proxy_quality), 4),
            "quality_flags": sorted(set(quality_flags)),
            "threshold_units": "pixels_and_fraction",
            "risk_thresholds": {
                "medium_fraction_outside_lumen": 0.2,
                "high_fraction_outside_lumen": 0.5,
                "medium_max_outward_depth_px": 8.0,
                "high_max_outward_depth_px": 15.0,
            },
            "wall_features": {k: round(v, 4) if isinstance(v, float) else v for k, v in features.items()},
            "lumen_bbox": lumen_bbox,
            "lumen_geometry_source": (
                lumen_mask_source or "confirmed_lumen_mask"
                if exact_lumen_mask is not None
                else "yolo_bbox_proxy"
            ),
            "lumen_mask_type": "confirmed_mask" if exact_lumen_mask is not None else "bbox_proxy",
            "image_height": h,
            "image_width": w,
            "runtime_invocation": {
                "api_kind": "local_numpy_scipy_wall_analysis",
                "forward_pass": True,
                "method": (
                    "signed_distance_from_confirmed_lumen_mask"
                    if exact_lumen_mask is not None
                    else "signed_distance_from_yolo_bbox_proxy"
                ),
            },
            "_visuals": visuals,
        }
