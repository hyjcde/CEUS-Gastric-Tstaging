#!/usr/bin/env python3
"""Warm DINOv3 lesion segmentation for the Next workbench / public edge.

Loads DINOv3SegmentationTool once at startup so /api/agent/lesion-segmentation
does not pay Python + backbone cold-start on every public box.

Usage:
  python3 scripts/serve_dino_segmentation.py --host 127.0.0.1 --port 8773
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_ROOT = REPO_ROOT / "pipeline"
if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

_tool = None
_tool_lock = threading.Lock()
_infer_lock = threading.Lock()
_load_error: Optional[str] = None
_loaded_at: Optional[float] = None


class SegmentRequest(BaseModel):
    frame_png_b64: str = Field(..., description="JPEG/PNG base64 frame (data-URL prefix allowed)")
    model: Optional[str] = "dinov3"
    threshold: Optional[float] = 0.5
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    box: Optional[dict[str, float]] = None
    clicks: Optional[list[dict[str, Any]]] = None
    include_overlay: Optional[bool] = False


def decode_frame(value: str) -> np.ndarray:
    raw = str(value or "")
    if "," in raw and raw.split(",", 1)[0].lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    image = cv2.imdecode(np.frombuffer(base64.b64decode(raw), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Could not decode frame image")
    return image


def soft_box(box: Any, width: int, height: int) -> Optional[tuple[int, int, int, int]]:
    if not isinstance(box, dict):
        return None
    x1 = int(np.clip(round(min(float(box.get("x1", 0)), float(box.get("x2", 0)))), 0, width - 1))
    x2 = int(np.clip(round(max(float(box.get("x1", 0)), float(box.get("x2", 0)))), 0, width - 1))
    y1 = int(np.clip(round(min(float(box.get("y1", 0)), float(box.get("y2", 0)))), 0, height - 1))
    y2 = int(np.clip(round(max(float(box.get("y1", 0)), float(box.get("y2", 0)))), 0, height - 1))
    ratio = min(max(float(os.getenv("DINO_BOX_PADDING_RATIO", "0.08")), 0.0), 0.25)
    pad_x = max(4, int(round((x2 - x1) * ratio)))
    pad_y = max(4, int(round((y2 - y1) * ratio)))
    return (
        max(0, x1 - pad_x),
        min(width - 1, x2 + pad_x),
        max(0, y1 - pad_y),
        min(height - 1, y2 + pad_y),
    )


def apply_prompt_gate(mask: np.ndarray, box: Any, clicks: Any) -> np.ndarray:
    height, width = mask.shape[:2]
    clipped = mask.astype(np.uint8)
    expanded = soft_box(box, width, height)
    if expanded is not None:
        x1, x2, y1, y2 = expanded
        gate = np.zeros_like(clipped)
        gate[y1 : y2 + 1, x1 : x2 + 1] = 1
        clipped = clipped & gate

    click_list = clicks if isinstance(clicks, list) else []
    positive = [
        item for item in click_list
        if str(item.get("label", "positive")).lower() != "negative"
    ]
    negative = [
        item for item in click_list
        if str(item.get("label", "positive")).lower() == "negative"
    ]
    chosen: set[int] = set()
    if positive and clipped.any():
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(clipped, connectivity=8)
        del stats, centroids
        ys, xs = np.where(clipped > 0)
        for point in positive:
            px = float(point.get("x", 0))
            py = float(point.get("y", 0))
            ix = int(np.clip(round(px), 0, width - 1))
            iy = int(np.clip(round(py), 0, height - 1))
            label = int(labels[iy, ix])
            if label == 0 and len(xs):
                nearest = int(np.argmin((xs - ix) ** 2 + (ys - iy) ** 2))
                label = int(labels[ys[nearest], xs[nearest]])
            if label > 0:
                chosen.add(label)
        if chosen:
            clipped = np.isin(labels, list(chosen)).astype(np.uint8)

    if negative:
        radius = max(5, int(round(min(width, height) * 0.025)))
        for point in negative:
            ix = int(np.clip(round(float(point.get("x", 0))), 0, width - 1))
            iy = int(np.clip(round(float(point.get("y", 0))), 0, height - 1))
            cv2.circle(clipped, (ix, iy), radius, 0, -1)
    if clipped.any():
        count, labels, stats, _ = cv2.connectedComponentsWithStats(clipped, connectivity=8)
        largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA])) if count > 1 else 1
        candidate_labels = chosen or {largest}
        largest_area = int(stats[largest, cv2.CC_STAT_AREA]) if count > 1 else int(clipped.sum())
        min_area = max(16, int(largest_area * 0.08))
        keep = {
            label for label in candidate_labels
            if 0 < label < count and int(stats[label, cv2.CC_STAT_AREA]) >= min_area
        }
        if not keep:
            keep = {largest}
        clipped = np.isin(labels, list(keep)).astype(np.uint8)
    return clipped.astype(bool)


def polygon_from_mask(mask: np.ndarray) -> list[list[float]]:
    contours, _ = cv2.findContours((mask.astype(np.uint8) * 255), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return []
    contour = max(contours, key=cv2.contourArea).reshape(-1, 2)
    height, width = mask.shape[:2]
    if len(contour) > 2048:
        contour = cv2.approxPolyDP(contour.astype(np.float32), 0.5, True).reshape(-1, 2)
    return [[round(float(x) / width, 6), round(float(y) / height, 6)] for x, y in contour]


def overlay_data_url(image: np.ndarray, mask: np.ndarray, polygon: list[list[float]]) -> str:
    overlay = image.copy()
    if mask.any():
        color = np.zeros_like(overlay)
        color[:, :] = (80, 205, 105)
        alpha = 0.46
        active = mask > 0
        overlay[active] = (overlay[active] * (1.0 - alpha) + color[active] * alpha).astype(np.uint8)
    if len(polygon) >= 3:
        height, width = image.shape[:2]
        points = np.array([[round(x * width), round(y * height)] for x, y in polygon], dtype=np.int32)
        cv2.polylines(overlay, [points], True, (80, 245, 120), 2, cv2.LINE_AA)
    ok, encoded = cv2.imencode(".png", overlay)
    if not ok:
        return ""
    return "data:image/png;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")


def ensure_tool():
    global _tool, _load_error, _loaded_at
    with _tool_lock:
        if _tool is not None:
            return _tool
        from agent.tools.dinov3_segmentation_tool import DINOv3SegmentationTool

        tool = DINOv3SegmentationTool()
        tool._ensure_model()
        if tool._model is None:
            _load_error = tool._load_error or "DINOv3 segmentation unavailable"
            raise RuntimeError(_load_error)
        _tool = tool
        _loaded_at = time.time()
        _load_error = None
        return _tool


def build_app() -> FastAPI:
    app = FastAPI(title="Gastric DINO lesion segmentation", version="1.0.0")

    @app.on_event("startup")
    def _warmup() -> None:
        def _warm() -> None:
            try:
                tool = ensure_tool()
                probe = np.zeros((512, 512, 3), dtype=np.uint8)
                tool.execute_array(probe, threshold=0.5)
            except Exception:
                pass

        threading.Thread(target=_warm, daemon=True, name="dino-seg-warm").start()

    @app.get("/api/dino-seg/status")
    def status() -> dict[str, Any]:
        ready = _tool is not None and getattr(_tool, "_model", None) is not None
        return {
            "ok": True,
            "available": ready,
            "ready": ready,
            "warm": ready,
            "service": "dino_segmentation",
            "port": int(os.getenv("DINO_SEG_PORT", "8773")),
            "loaded_at": _loaded_at,
            "error": _load_error,
            "backend_id": getattr(_tool, "backend_id", None) if _tool else None,
        }

    @app.post("/api/dino-seg/segment")
    def segment(body: SegmentRequest) -> dict[str, Any]:
        started = time.time()
        try:
            image = decode_frame(body.frame_png_b64)
        except Exception as exc:
            return {
                "ok": False,
                "available": False,
                "mask_available": False,
                "error": str(exc),
                "elapsed_ms": int((time.time() - started) * 1000),
            }

        try:
            tool = ensure_tool()
        except Exception as exc:
            return {
                "ok": False,
                "available": False,
                "mask_available": False,
                "error": str(exc),
                "elapsed_ms": int((time.time() - started) * 1000),
                "backend_id": "dinov3_warm_service",
            }

        height, width = image.shape[:2]
        threshold = float(body.threshold if body.threshold is not None else 0.5)
        with _infer_lock:
            result = tool.execute_array(image, threshold=threshold)
            mask = tool.get_cached_mask("__array__")
        if mask is None:
            mask = np.zeros((height, width), dtype=np.uint8)
        binary = apply_prompt_gate(mask > 127, body.box, body.clicks)
        polygon = polygon_from_mask(binary)
        foreground = int(binary.sum())
        payload: dict[str, Any] = {
            "ok": True,
            "available": bool(result.get("available")),
            "mask_available": bool(polygon),
            "model": "dinov3",
            "backend_id": result.get("backend_id") or "dinov3_warm_service",
            "roi_source": result.get("roi_source") or "model_prediction",
            "roi_bbox": result.get("roi_bbox"),
            "lesion_area_ratio": round(foreground / max(height * width, 1), 6),
            "image_width": width,
            "image_height": height,
            "mask_polygon": polygon,
            "validation_summary": result.get("validation_summary"),
            "prompt": {"box": body.box, "click_count": len(body.clicks or [])},
            "elapsed_ms": int((time.time() - started) * 1000),
            "error": result.get("error"),
            "warm_service": True,
        }
        if body.include_overlay:
            payload["mask_overlay_png"] = overlay_data_url(image, binary, polygon)
        return payload

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Warm DINOv3 lesion segmentation service")
    parser.add_argument("--host", default=os.getenv("DINO_SEG_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("DINO_SEG_PORT", "8773")))
    args = parser.parse_args()
    uvicorn.run(build_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
