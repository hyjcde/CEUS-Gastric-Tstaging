"""
MorphologyTool — extract shape and boundary features from a lesion mask.

Computes convexity, solidity, boundary irregularity, compactness, smoothness,
and lesion area ratio. These morphological biomarkers provide additional
evidence for T-stage differentiation, especially at the T2/T3 boundary
where shape irregularity correlates with deeper invasion.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, Optional

import cv2
import numpy as np

from .base import BaseTool, ToolParameter

logger = logging.getLogger(__name__)


def compute_morphology(mask: np.ndarray) -> Dict[str, Any]:
    """
    Compute morphological features from a binary mask.

    Features:
      - convexity: convex_hull_perimeter / actual_perimeter (1 = perfectly convex)
      - solidity: area / convex_hull_area
      - boundary_irregularity: 1 - (4*pi*area / perimeter^2)  (0 = perfect circle)
      - compactness: sqrt(area) / perimeter
      - smoothness_index: weighted circularity and solidity, higher = smoother
      - roughness_index: 1 - smoothness_index
      - lesion_area_ratio: lesion_pixels / total_pixels
      - aspect_ratio: bounding box width / height
    """
    mask_bin = (mask > 127).astype(np.uint8)
    total_pixels = mask.shape[0] * mask.shape[1]
    lesion_pixels = int(np.sum(mask_bin))

    if lesion_pixels < 10:
        return {
            "convexity": 0.0,
            "solidity": 0.0,
            "boundary_irregularity": 0.0,
            "compactness": 0.0,
            "smoothness_index": 0.0,
            "roughness_index": 1.0,
            "lesion_area_ratio": 0.0,
            "aspect_ratio": 1.0,
            "valid": False,
        }

    contours, _ = cv2.findContours(mask_bin, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return {
            "convexity": 0.0, "solidity": 0.0,
            "boundary_irregularity": 0.0, "compactness": 0.0,
            "smoothness_index": 0.0, "roughness_index": 1.0,
            "lesion_area_ratio": 0.0, "aspect_ratio": 1.0, "valid": False,
        }

    # Use the largest contour
    cnt = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(cnt)
    perimeter = cv2.arcLength(cnt, True)

    if area < 5 or perimeter < 1:
        return {
            "convexity": 0.0, "solidity": 0.0,
            "boundary_irregularity": 0.0, "compactness": 0.0,
            "smoothness_index": 0.0, "roughness_index": 1.0,
            "lesion_area_ratio": 0.0, "aspect_ratio": 1.0, "valid": False,
        }

    hull = cv2.convexHull(cnt)
    hull_area = cv2.contourArea(hull)
    hull_perimeter = cv2.arcLength(hull, True)

    convexity = hull_perimeter / perimeter if perimeter > 0 else 0
    solidity = area / hull_area if hull_area > 0 else 0

    # Circularity-based irregularity
    circularity = (4 * math.pi * area) / (perimeter ** 2) if perimeter > 0 else 0
    boundary_irregularity = 1.0 - min(circularity, 1.0)
    smoothness_index = max(
        0.0,
        min(1.0, 0.65 * min(circularity, 1.0) + 0.35 * solidity),
    )

    compactness = math.sqrt(area) / perimeter if perimeter > 0 else 0

    x, y, w, h = cv2.boundingRect(cnt)
    aspect_ratio = w / h if h > 0 else 1.0

    lesion_area_ratio = lesion_pixels / total_pixels if total_pixels > 0 else 0

    return {
        "convexity": round(convexity, 4),
        "solidity": round(solidity, 4),
        "boundary_irregularity": round(boundary_irregularity, 4),
        "compactness": round(compactness, 4),
        "smoothness_index": round(smoothness_index, 4),
        "roughness_index": round(1.0 - smoothness_index, 4),
        "lesion_area_ratio": round(lesion_area_ratio, 4),
        "aspect_ratio": round(aspect_ratio, 3),
        "valid": True,
    }


class MorphologyTool(BaseTool):
    name = "morphology"
    description = (
        "Extract mask-derived shape descriptors (convexity, solidity, boundary "
        "irregularity, compactness, smoothness). These are exploratory evidence features, "
        "not direct measurements of pathological invasion depth."
    )
    parameters = [
        ToolParameter("mask_path", "str",
                       "Path to binary mask image (PNG, 0/255)",
                       required=False),
        ToolParameter("mask_array", "ndarray",
                       "Direct numpy mask array (used internally)",
                       required=False),
    ]

    def execute(self, mask_path: Optional[str] = None,
                mask_array: Optional[np.ndarray] = None,
                **kwargs) -> Dict[str, Any]:
        def annotate(result: Dict[str, Any]) -> Dict[str, Any]:
            result.update(
                {
                    "evidence_source": "lesion_mask_geometry",
                    "evidence_role": "derived_shape_descriptor",
                    "clinical_interpretation": "not_independently_diagnostic",
                }
            )
            return result

        if mask_array is not None:
            return annotate(compute_morphology(mask_array))

        if mask_path:
            mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
            if mask is None:
                return annotate({"error": "Could not read mask", "valid": False})
            return annotate(compute_morphology(mask))

        return annotate({"error": "No mask_path or mask_array provided", "valid": False})
