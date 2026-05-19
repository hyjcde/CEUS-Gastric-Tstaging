"""
LumenDetectionTool — YOLO-based gastric lumen (stomach cavity) detection.

Used upstream of wall-band analysis and lumen-relative lesion features.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

from .base import BaseTool, ToolParameter
from ..core.repo_paths import PROJECT_ROOT, first_existing_path

logger = logging.getLogger(__name__)

DEFAULT_LUMEN_WEIGHTS = first_existing_path(
    PROJECT_ROOT
    / "experiments"
    / "detection"
    / "detection_yolo11l_lumen_locator_cropui_combined_plus_zip2_20260417_r001"
    / "ultralytics"
    / "weights"
    / "best.pt",
    PROJECT_ROOT / "pipeline" / "experiments" / "yolo_internal_high_iou_v1" / "weights" / "best.pt",
    PROJECT_ROOT
    / "archived"
    / "experiments_yolo"
    / "01_Detection"
    / "20260105_v6_refined_baseline"
    / "weights"
    / "best.pt",
) or (
    PROJECT_ROOT
    / "pipeline"
    / "experiments"
    / "yolo_internal_high_iou_v1"
    / "weights"
    / "best.pt"
)


def select_lumen_box(result: Any) -> Optional[Dict[str, int]]:
    """Pick highest-confidence YOLO box as xyxy dict."""
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return None
    xyxy = boxes.xyxy.cpu().tolist()
    confs = boxes.conf.cpu().tolist() if getattr(boxes, "conf", None) is not None else [0.0] * len(xyxy)
    best_index = max(range(len(xyxy)), key=lambda idx: confs[idx])
    x1, y1, x2, y2 = (int(round(v)) for v in xyxy[best_index])
    return {
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "confidence": float(confs[best_index]),
    }


def lumen_mask_from_bbox(bbox: Dict[str, int], height: int, width: int) -> np.ndarray:
    mask = np.zeros((height, width), dtype=np.uint8)
    x1 = max(0, int(bbox["x1"]))
    y1 = max(0, int(bbox["y1"]))
    x2 = min(width, int(bbox["x2"]))
    y2 = min(height, int(bbox["y2"]))
    if x2 > x1 and y2 > y1:
        mask[y1:y2, x1:x2] = 255
    return mask


class LumenDetectionTool(BaseTool):
    name = "detect_lumen"
    description = (
        "Detect gastric lumen (water-filled cavity) with YOLO. Returns bounding box, "
        "confidence, and lumen area ratio for wall-band and staging context."
    )
    parameters = [
        ToolParameter("image_path", "str", "Absolute path to the ultrasound image"),
        ToolParameter("conf", "float", "YOLO confidence threshold", required=False),
        ToolParameter("imgsz", "int", "YOLO inference size", required=False),
    ]

    def __init__(
        self,
        weights_path: Path = DEFAULT_LUMEN_WEIGHTS,
        conf: float = 0.25,
        imgsz: int = 640,
        device: Optional[str] = None,
    ):
        self._weights_path = Path(weights_path)
        self._conf = conf
        self._imgsz = imgsz
        self._device = device
        self._model = None
        self._load_error: Optional[str] = None

    def _ensure_model(self):
        if self._model is not None:
            return
        if not self._weights_path.exists():
            self._load_error = f"Lumen YOLO weights not found: {self._weights_path}"
            logger.warning(self._load_error)
            return
        try:
            from ultralytics import YOLO

            self._model = YOLO(str(self._weights_path))
        except Exception as exc:
            self._load_error = str(exc)
            logger.warning("LumenDetection model unavailable: %s", exc)

    def _runtime_invocation(self, *, forward_pass: bool) -> Dict[str, Any]:
        return {
            "api_kind": "local_ultralytics_yolo",
            "forward_pass": forward_pass,
            "checkpoint": str(self._weights_path),
            "conf": self._conf,
            "imgsz": self._imgsz,
        }

    def execute(
        self,
        image_path: str,
        conf: Optional[float] = None,
        imgsz: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        img = cv2.imread(image_path)
        if img is None:
            return {
                "available": False,
                "error": "Could not read image",
                "runtime_invocation": self._runtime_invocation(forward_pass=False),
            }

        h, w = img.shape[:2]
        self._ensure_model()
        if self._model is None:
            return {
                "available": False,
                "lumen_detected": False,
                "error": self._load_error or "Lumen YOLO unavailable",
                "image_height": h,
                "image_width": w,
                "runtime_invocation": self._runtime_invocation(forward_pass=False),
            }

        use_conf = float(conf if conf is not None else self._conf)
        use_imgsz = int(imgsz if imgsz is not None else self._imgsz)
        try:
            results = self._model.predict(
                source=image_path,
                imgsz=use_imgsz,
                conf=use_conf,
                verbose=False,
                save=False,
                device=self._device,
            )
            pick = select_lumen_box(results[0])
        except Exception as exc:
            return {
                "available": False,
                "lumen_detected": False,
                "error": str(exc),
                "image_height": h,
                "image_width": w,
                "runtime_invocation": self._runtime_invocation(forward_pass=False),
            }

        if pick is None:
            return {
                "available": True,
                "lumen_detected": False,
                "roi_source": "yolo_no_detection",
                "image_height": h,
                "image_width": w,
                "runtime_invocation": self._runtime_invocation(forward_pass=True),
            }

        bbox = {k: pick[k] for k in ("x1", "y1", "x2", "y2")}
        conf_val = float(pick.get("confidence", 0.0))
        lumen_mask = lumen_mask_from_bbox(bbox, h, w)
        lumen_area = int(np.sum(lumen_mask > 0))
        total = max(h * w, 1)

        return {
            "available": True,
            "lumen_detected": True,
            "roi_source": "yolo_lumen",
            "lumen_bbox": bbox,
            "lumen_confidence": round(conf_val, 4),
            "lumen_area_ratio": round(lumen_area / total, 4),
            "image_height": h,
            "image_width": w,
            "runtime_invocation": self._runtime_invocation(forward_pass=True),
        }
