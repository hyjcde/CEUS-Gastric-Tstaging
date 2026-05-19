"""
QualityTool — rule-based image quality assessment for abdominal ultrasound frames.

Evaluates brightness, contrast, and sharpness to determine whether a
frame is usable for downstream classification. No trained model is
needed; the metrics are simple image statistics that correlate with
ultrasound image quality.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import cv2
import numpy as np

from .base import BaseTool, ToolParameter

logger = logging.getLogger(__name__)

# Thresholds — tuned conservatively so most abdominal ultrasound frames pass.
# A frame should only be rejected if truly uninterpretable.
BRIGHTNESS_LOW = 15
BRIGHTNESS_HIGH = 240
CONTRAST_LOW = 15
SHARPNESS_LOW = 5.0


class QualityTool(BaseTool):
    name = "quality_check"
    description = (
        "Assess ultrasound frame quality (brightness, contrast, sharpness). "
        "Returns a quality score (0-1), artifact flag, and usability verdict."
    )
    parameters = [
        ToolParameter("image_path", "str",
                       "Absolute path to the ultrasound image file"),
    ]

    def execute(self, image_path: str, **kwargs) -> Dict[str, Any]:
        img = cv2.imread(image_path)
        if img is None:
            return {
                "quality_score": 0.0,
                "brightness": 0.0,
                "contrast": 0.0,
                "sharpness": 0.0,
                "artifact_flag": True,
                "usable": False,
                "reason": "Image could not be loaded",
            }

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        brightness = float(np.mean(gray))
        contrast = float(np.std(gray))

        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        sharpness = float(np.var(laplacian))
        # Normalise sharpness to a 0–1 range (empirical cap at 2000)
        sharpness_norm = min(sharpness / 2000.0, 1.0)

        # Brightness score: penalise too dark or too bright
        if brightness < BRIGHTNESS_LOW:
            bright_score = brightness / BRIGHTNESS_LOW
        elif brightness > BRIGHTNESS_HIGH:
            bright_score = max(0, 1.0 - (brightness - BRIGHTNESS_HIGH) / 35.0)
        else:
            bright_score = 1.0

        # Contrast score: penalise very low contrast
        contrast_score = min(contrast / 60.0, 1.0)

        # Artifact heuristic: only flag if image is almost entirely black
        black_ratio = float(np.sum(gray < 10)) / (h * w)
        artifact_flag = black_ratio > 0.85

        quality_score = round(
            0.3 * bright_score + 0.3 * contrast_score + 0.4 * sharpness_norm,
            3,
        )

        usable = (quality_score >= 0.15
                   and not artifact_flag
                   and contrast > CONTRAST_LOW
                   and sharpness > SHARPNESS_LOW)

        return {
            "quality_score": quality_score,
            "brightness": round(brightness, 1),
            "contrast": round(contrast, 1),
            "sharpness": round(sharpness, 1),
            "artifact_flag": artifact_flag,
            "usable": usable,
        }
