#!/usr/bin/env python3
"""Bridge the official nnInteractive remote client to the gastric workbench.

The bridge keeps one nnInteractive remote session per browser frame. The
workbench sends the doctor-confirmed SAM polygon as an initial mask, then
adds positive or negative points, freehand scribbles, or closed lasso prompts
without changing the existing mask override contract.

This service is intentionally optional. It starts even when the client
package or remote GPU server is unavailable, so the UI can report a clear
configuration error instead of failing during workstation startup.

Usage:
  NN_INTERACTIVE_SERVER_URL=http://gpu-box:1527 \
    NN_INTERACTIVE_API_KEY=... \
    python3 scripts/serve_nninteractive_agent.py --port 8770
"""

from __future__ import annotations

import argparse
import base64
import binascii
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(REPO_ROOT, ".env"), override=False)

REMOTE_SERVER_URL = os.getenv("NN_INTERACTIVE_SERVER_URL", "").strip().rstrip("/")
REMOTE_API_KEY = os.getenv("NN_INTERACTIVE_API_KEY", "").strip() or None
SESSION_TTL_SEC = float(os.getenv("NN_INTERACTIVE_SESSION_TTL_SEC", "1800"))

app = FastAPI(title="Gastric nnInteractive bridge")


class PointPrompt(BaseModel):
    x: float
    y: float
    label: str = "positive"


class ScribblePrompt(BaseModel):
    points: list[PointPrompt] = Field(default_factory=list)
    label: str = "positive"
    width: int = Field(default=8, ge=1, le=128)


class RefineRequest(BaseModel):
    session_id: str = ""
    case_id: str = ""
    frame_time: float = 0.0
    frame_png_b64: str = ""
    image_width: int = Field(..., gt=0)
    image_height: int = Field(..., gt=0)
    initial_mask_polygon: list[list[float]] = Field(default_factory=list)
    points: list[PointPrompt] = Field(default_factory=list)
    scribbles: list[ScribblePrompt] = Field(default_factory=list)
    lassos: list[ScribblePrompt] = Field(default_factory=list)
    reset_session: bool = False


@dataclass
class SessionEntry:
    session: Any
    target_buffer: np.ndarray
    image_shape: tuple[int, int]
    last_seen: float
    initialized: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


_sessions: dict[str, SessionEntry] = {}
_sessions_lock = threading.Lock()


def _load_remote_session() -> Any:
    if not REMOTE_SERVER_URL:
        raise RuntimeError(
            "NN_INTERACTIVE_SERVER_URL is not configured; start the official "
            "nninteractive-server and set its URL first"
        )
    try:
        from nnInteractive.inference.remote import nnInteractiveRemoteInferenceSession
    except Exception as error:
        raise RuntimeError(
            "nninteractive-client is not installed; run pip install nninteractive-client"
        ) from error
    return nnInteractiveRemoteInferenceSession(
        server_url=REMOTE_SERVER_URL,
        api_key=REMOTE_API_KEY,
    )


def _probe_remote_server() -> tuple[bool, str | None]:
    if not REMOTE_SERVER_URL:
        return False, "NN_INTERACTIVE_SERVER_URL is not configured"
    try:
        import httpx

        headers = {"Authorization": f"Bearer {REMOTE_API_KEY}"} if REMOTE_API_KEY else {}
        response = httpx.get(
            f"{REMOTE_SERVER_URL}/healthz",
            headers=headers,
            timeout=3.0,
        )
        if response.is_success:
            return True, None
        return False, f"remote health HTTP {response.status_code}"
    except Exception as error:
        return False, str(error)


def _close_session(entry: SessionEntry | None) -> None:
    if entry is None:
        return
    try:
        entry.session.close()
    except Exception:
        pass


def _cleanup_sessions() -> None:
    cutoff = time.time() - max(60.0, SESSION_TTL_SEC)
    stale: list[SessionEntry] = []
    with _sessions_lock:
        for session_id, entry in list(_sessions.items()):
            if entry.last_seen < cutoff:
                stale.append(_sessions.pop(session_id))
    for entry in stale:
        _close_session(entry)


def _decode_frame(frame_b64: str) -> np.ndarray:
    if not frame_b64:
        raise ValueError("frame_png_b64 is required")
    encoded = frame_b64.split(",", 1)[-1]
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("frame_png_b64 is not valid base64") from error
    decoded = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if decoded is None:
        raise ValueError("frame_png_b64 is not a readable PNG or JPEG")
    if decoded.ndim == 2:
        gray = decoded
    elif decoded.shape[2] == 4:
        gray = cv2.cvtColor(decoded, cv2.COLOR_BGRA2GRAY)
    else:
        gray = cv2.cvtColor(decoded, cv2.COLOR_BGR2GRAY)
    # nnInteractive expects a floating point image channel. Do not normalize
    # intensities here because its preprocessing owns that responsibility.
    return np.asarray(gray, dtype=np.float32)


def _polygon_to_mask(
    polygon: list[list[float]],
    height: int,
    width: int,
) -> np.ndarray | None:
    if len(polygon) < 3:
        return None
    points = np.asarray(polygon, dtype=np.float32).reshape(-1, 2)
    points[:, 0] = np.clip(points[:, 0], 0, max(width - 1, 0))
    points[:, 1] = np.clip(points[:, 1], 0, max(height - 1, 0))
    mask = np.zeros((height, width, 1), dtype=np.uint8)
    cv2.fillPoly(mask[:, :, 0], [np.round(points).astype(np.int32)], 1)
    return mask


def _stroke_array(
    prompt: ScribblePrompt,
    height: int,
    width: int,
    *,
    closed: bool,
) -> tuple[np.ndarray, list[list[int]]] | None:
    if len(prompt.points) < 2:
        return None
    points = np.asarray([[item.x, item.y] for item in prompt.points], dtype=np.float32)
    points[:, 0] = np.clip(points[:, 0], 0, max(width - 1, 0))
    points[:, 1] = np.clip(points[:, 1], 0, max(height - 1, 0))
    x1 = max(0, int(np.floor(points[:, 0].min())) - prompt.width)
    y1 = max(0, int(np.floor(points[:, 1].min())) - prompt.width)
    x2 = min(width, int(np.ceil(points[:, 0].max())) + prompt.width + 1)
    y2 = min(height, int(np.ceil(points[:, 1].max())) + prompt.width + 1)
    if x2 <= x1 or y2 <= y1:
        return None
    crop = np.zeros((y2 - y1, x2 - x1, 1), dtype=np.uint8)
    local = np.round(points - np.asarray([x1, y1], dtype=np.float32)).astype(np.int32)
    cv2.polylines(
        crop[:, :, 0],
        [local.reshape(-1, 1, 2)],
        isClosed=closed,
        color=1,
        thickness=max(1, int(prompt.width)),
    )
    # The session uses image-axis order: height, width, depth.
    bbox = [[y1, y2], [x1, x2], [0, 1]]
    return crop, bbox


def _scribble_array(
    prompt: ScribblePrompt,
    height: int,
    width: int,
) -> tuple[np.ndarray, list[list[int]]] | None:
    return _stroke_array(prompt, height, width, closed=False)


def _lasso_array(
    prompt: ScribblePrompt,
    height: int,
    width: int,
) -> tuple[np.ndarray, list[list[int]]] | None:
    return _stroke_array(prompt, height, width, closed=True)


def _mask_to_polygon(target: np.ndarray) -> tuple[list[list[float]], float]:
    squeezed = np.asarray(target)
    if squeezed.ndim == 3:
        if squeezed.shape[-1] == 1:
            squeezed = squeezed[:, :, 0]
        elif squeezed.shape[0] == 1:
            squeezed = squeezed[0]
        else:
            squeezed = np.max(squeezed, axis=-1)
    mask = (squeezed > 0).astype(np.uint8)
    height, width = mask.shape[:2]
    area_ratio = float(np.count_nonzero(mask) / max(1, height * width))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return [], area_ratio
    contour = max(contours, key=cv2.contourArea)
    perimeter = cv2.arcLength(contour, True)
    epsilon = max(0.75, perimeter * 0.002)
    simplified = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
    if len(simplified) < 3:
        simplified = contour.reshape(-1, 2)
    polygon = [
        [round(float(point[0]), 2), round(float(point[1]), 2)]
        for point in simplified
    ]
    return polygon, area_ratio


def _get_or_create_session(
    session_id: str,
    image: np.ndarray,
    reset: bool,
) -> tuple[str, SessionEntry]:
    _cleanup_sessions()
    safe_id = (session_id or "").strip()[:180] or f"nn_{uuid.uuid4().hex}"
    height, width = image.shape
    with _sessions_lock:
        previous = _sessions.pop(safe_id, None) if reset else _sessions.get(safe_id)
    if reset:
        _close_session(previous)
    if previous is not None and previous.image_shape == (height, width):
        previous.last_seen = time.time()
        return safe_id, previous
    _close_session(previous)
    session = _load_remote_session()
    # The official API uses a channel-first four-dimensional image and a
    # three-dimensional target buffer. The final dimension is one 2D slice.
    image_4d = image[:, :, None][None, ...]
    target = np.zeros((height, width, 1), dtype=np.uint8)
    session.set_image(image_4d)
    session.set_target_buffer(target)
    entry = SessionEntry(
        session=session,
        target_buffer=target,
        image_shape=(height, width),
        last_seen=time.time(),
    )
    with _sessions_lock:
        _sessions[safe_id] = entry
    return safe_id, entry


def _run_interactions(entry: SessionEntry, payload: RefineRequest, image: np.ndarray) -> None:
    height, width = image.shape
    initial = _polygon_to_mask(payload.initial_mask_polygon, height, width)
    if initial is not None:
        has_prompts = bool(payload.points or payload.scribbles or payload.lassos)
        entry.session.add_initial_seg_interaction(
            initial,
            run_prediction=not has_prompts,
        )
        entry.initialized = True
        if not has_prompts:
            return
    elif payload.reset_session:
        entry.session.reset_interactions()
        entry.initialized = False

    for point in payload.points:
        x = min(max(int(round(point.x)), 0), max(width - 1, 0))
        y = min(max(int(round(point.y)), 0), max(height - 1, 0))
        entry.session.add_point_interaction(
            (y, x, 0),
            include_interaction=point.label.lower() not in {"negative", "background", "neg"},
            run_prediction=False,
        )

    for scribble in payload.scribbles:
        prepared = _scribble_array(scribble, height, width)
        if prepared is None:
            continue
        crop, bbox = prepared
        entry.session.add_scribble_interaction(
            crop,
            include_interaction=scribble.label.lower() not in {"negative", "background", "neg"},
            interaction_bbox=bbox,
            run_prediction=False,
        )

    for lasso in payload.lassos:
        prepared = _lasso_array(lasso, height, width)
        if prepared is None:
            continue
        crop, bbox = prepared
        entry.session.add_lasso_interaction(
            crop,
            include_interaction=lasso.label.lower() not in {"negative", "background", "neg"},
            interaction_bbox=bbox,
            run_prediction=False,
        )

    if payload.points or payload.scribbles or payload.lassos:
        entry.session._predict()


@app.get("/api/nninteractive/status")
def status() -> dict[str, Any]:
    try:
        import nnInteractive  # noqa: F401

        client_available = True
    except Exception:
        client_available = False
    remote_available, remote_error = _probe_remote_server() if client_available else (
        False,
        "nninteractive-client is not installed",
    )
    return {
        "available": bool(client_available and remote_available),
        "client_available": client_available,
        "configured": bool(REMOTE_SERVER_URL),
        "remote_available": remote_available,
        "remote_error": remote_error,
        "server_url": REMOTE_SERVER_URL or None,
        "model": "nnInteractive_v1.0",
        "mode": "remote",
        "supports": ["initial_mask", "positive_negative_points", "scribbles", "lassos"],
    }


@app.post("/api/nninteractive/refine")
def refine(payload: RefineRequest) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        image = _decode_frame(payload.frame_png_b64)
        if image.shape != (payload.image_height, payload.image_width):
            raise ValueError(
                "Decoded frame dimensions do not match the request: "
                f"{image.shape[1]}x{image.shape[0]} vs "
                f"{payload.image_width}x{payload.image_height}"
            )
        session_id, entry = _get_or_create_session(
            payload.session_id,
            image,
            payload.reset_session,
        )
        with _sessions_lock:
            entry.last_seen = time.time()
        with entry.lock:
            _run_interactions(entry, payload, image)
            polygon, area_ratio = _mask_to_polygon(entry.target_buffer)
        return {
            "ok": True,
            "available": True,
            "session_id": session_id,
            "mask_polygon": polygon,
            "lesion_area_ratio": area_ratio,
            "backend_id": "nninteractive_remote_v1",
            "model": "nnInteractive_v1.0",
            "prompt_meta": {
                "initial_mask": bool(payload.initial_mask_polygon),
                "point_count": len(payload.points),
                "scribble_count": len(payload.scribbles),
                "lasso_count": len(payload.lassos),
                "license": getattr(entry.session, "license", None),
            },
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except Exception as error:
        return {
            "ok": False,
            "available": bool(REMOTE_SERVER_URL),
            "error": str(error),
            "hint": (
                "Start nninteractive-server on a GPU host, install "
                "nninteractive-client, and set NN_INTERACTIVE_SERVER_URL."
            ),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.getenv("NNINTERACTIVE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("NNINTERACTIVE_PORT", "8770")))
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
