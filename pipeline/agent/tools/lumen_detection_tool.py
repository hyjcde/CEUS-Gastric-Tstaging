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
    """Create a rectangular proxy mask; this is not a lumen segmentation mask."""
    mask = np.zeros((height, width), dtype=np.uint8)
    x1 = max(0, int(bbox["x1"]))
    y1 = max(0, int(bbox["y1"]))
    x2 = min(width, int(bbox["x2"]))
    y2 = min(height, int(bbox["y2"]))
    if x2 > x1 and y2 > y1:
        mask[y1:y2, x1:x2] = 255
    return mask


def lumen_geometry_from_bbox(bbox: Dict[str, int], height: int, width: int) -> Dict[str, float]:
    """Return auditable box geometry without inferring a clinical direction."""
    box_width = max(0, int(bbox["x2"]) - int(bbox["x1"]))
    box_height = max(0, int(bbox["y2"]) - int(bbox["y1"]))
    image_area = max(int(height) * int(width), 1)
    return {
        "bbox_width_px": float(box_width),
        "bbox_height_px": float(box_height),
        "bbox_aspect_ratio": round(box_width / max(box_height, 1), 4),
        "bbox_center_x_norm": round(((int(bbox["x1"]) + int(bbox["x2"])) / 2) / max(width, 1), 4),
        "bbox_center_y_norm": round(((int(bbox["y1"]) + int(bbox["y2"])) / 2) / max(height, 1), 4),
        "bbox_area_ratio": round((box_width * box_height) / image_area, 4),
    }


class LumenDetectionTool(BaseTool):
    name = "detect_lumen"
    description = (
        "Detect gastric lumen (water-filled cavity) with YOLO. Returns a bounding box, "
        "proxy-mask geometry, confidence, and explicit direction status for staging context."
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
                "lumen_direction": "not_assessable",
                "lumen_direction_source": "image_unavailable",
                "runtime_invocation": self._runtime_invocation(forward_pass=False),
            }

        h, w = img.shape[:2]
        self._ensure_model()
        if self._model is None:
            return {
                "available": False,
                "lumen_detected": False,
                "error": self._load_error or "Lumen YOLO unavailable",
                "lumen_direction": "not_assessable",
                "lumen_direction_source": "model_unavailable",
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
                "lumen_direction": "not_assessable",
                "lumen_direction_source": "inference_error",
                "image_height": h,
                "image_width": w,
                "runtime_invocation": self._runtime_invocation(forward_pass=False),
            }

        if pick is None:
            return {
                "available": True,
                "lumen_detected": False,
                "roi_source": "yolo_no_detection",
                "lumen_direction": "not_assessable",
                "lumen_direction_source": "no_bbox",
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
            "lumen_mask_type": "bbox_proxy",
            "lumen_confidence": round(conf_val, 4),
            "lumen_area_ratio": round(lumen_area / total, 4),
            "lumen_geometry": lumen_geometry_from_bbox(bbox, h, w),
            "lumen_direction": "not_assessed",
            "lumen_direction_source": "yolo_bbox_only",
            "image_height": h,
            "image_width": w,
            "runtime_invocation": self._runtime_invocation(forward_pass=True),
        }
