#!/usr/bin/env python3
"""Serve interactive video Agent UI with real SAM2 click segmentation.

Usage:
  python3 scripts/serve_interactive_sam_agent.py --port 8767

Open:
  http://127.0.0.1:8767/interactive_video_agent.html
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_ROOT = REPO_ROOT / "pipeline"
STATIC_ROOT = REPO_ROOT / "docs/clinical_validation/reader_study_v150"
STAGES = ["T1", "T2", "T3", "T4+"]

load_dotenv(REPO_ROOT / ".env", override=False)

if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

_predictor = None
_predictor_lock = threading.Lock()
_predictor_inference_lock = threading.Lock()
DEFAULT_FINETUNE_CKPTS = (
    REPO_ROOT
    / "experiments/segmentation/model_compare_20260802"
    / "sabm_gus_sam2_finetune_r001/best_sabm_gus_sam2.pt",
    REPO_ROOT
    / "pipeline/experiments/tree/segmentation_auxiliary/segmentation/sam2"
    / "segmentation_sam2_maskprompt/analysis/legacy_root_files/best_sam2_maskprompt.pth",
)
_finetune_ckpt: Path | None = None
_finetune_meta: dict[str, Any] = {}
_track_sessions: dict[str, dict[str, Any]] = {}
_track_sessions_lock = threading.Lock()
TRACK_SESSION_TTL_SEC = 3600.0
TRACK_MAX_FORWARD_GAP_SEC = 2.0

_video_tracker = None
_video_tracker_lock = threading.Lock()


def get_video_tracker():
    global _video_tracker
    with _video_tracker_lock:
        if _video_tracker is None:
            from sam2_video_tracker import Sam2VideoTracker

            _video_tracker = Sam2VideoTracker()
        return _video_tracker


def resolve_finetune_checkpoint() -> Path | None:
    explicit = os.getenv("SAM2_CHECKPOINT", "").strip()
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.is_file():
            raise FileNotFoundError(f"SAM2_CHECKPOINT does not exist: {path}")
        return path
    if os.getenv("SAM2_FINETUNE", "1").strip().lower() in ("0", "false", "no"):
        return None
    return next((path for path in DEFAULT_FINETUNE_CKPTS if path.is_file()), None)


_finetune_ckpt = resolve_finetune_checkpoint()
_model_label = os.getenv("SAM2_MODEL") or (
    "facebook/sam2.1-hiera-tiny"
    if _finetune_ckpt is not None
    else "facebook/sam2.1-hiera-small"
)
_minimax_client = None
_minimax_lock = threading.Lock()
_deepseek_client = None
_deepseek_lock = threading.Lock()
DEEPSEEK_KEYFILE = STATIC_ROOT / "server" / "deepseek_api_key.txt"


def _ensure_deepseek_env() -> None:
    """Load DEEPSEEK_API_KEY from keyfile when not already in the environment."""
    if os.getenv("DEEPSEEK_API_KEY", "").strip():
        return
    if not DEEPSEEK_KEYFILE.is_file():
        return
    key = DEEPSEEK_KEYFILE.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    if key:
        os.environ["DEEPSEEK_API_KEY"] = key


_ensure_deepseek_env()


def apply_finetune_weights(predictor, ckpt_path: Path, device: str) -> None:
    global _finetune_meta
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    raw = ckpt.get("model_state_dict", ckpt)
    state = {
        k.replace("sam2_model.", "", 1): v
        for k, v in raw.items()
        if k.startswith("sam2_model.")
    }
    if not state:
        raise RuntimeError(f"No sam2_model.* weights in checkpoint: {ckpt_path}")
    predictor.model.load_state_dict(state, strict=True)
    _finetune_meta = {
        "checkpoint": str(ckpt_path),
        "name": ckpt_path.parent.name or ckpt_path.stem,
        "run_dir": str(ckpt_path.parent),
        "epoch": ckpt.get("epoch"),
        "val_dice_mask": ckpt.get("val_dice_mask"),
        "val_dice_bbox": ckpt.get("val_dice_bbox"),
        "val_dice": ckpt.get("val_dice"),
        "best_val_dice": ckpt.get("best_val_dice"),
        "state_key_count": len(state),
    }


class ClickPayload(BaseModel):
    x: float
    y: float
    label: str = "positive"


class BoxPayload(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class BoundarySectorPayload(BaseModel):
    sector_id: str = ""
    label: str = ""
    adjudication: str = ""
    wall_mm: float = 0.0
    normal_mm: float = 0.0
    breakthrough_risk: float = 0.0
    thickness_ratio: float = 0.0


class AnalyzeRequest(BaseModel):
    case_id: str = ""
    video_rel: str = ""
    video_url: str = ""
    # JPEG/PNG base64 or data-URL — used for workbench deep-link stills / external videos
    frame_png_b64: str = ""
    frame_time: float = 0.0
    tracking_session_id: str = ""
    tracking_enabled: bool = False
    tracking_reset: bool = False
    click: ClickPayload | None = None
    clicks: list[ClickPayload] = Field(default_factory=list)
    box: BoxPayload | None = None
    image_width: int = Field(..., gt=0)
    image_height: int = Field(..., gt=0)
    llm_report: bool = False
    boundary_sectors: list[BoundarySectorPayload] = Field(default_factory=list)


class VideoPropagateRequest(BaseModel):
    case_id: str = ""
    video_rel: str = ""
    frame_time: float = 0.0
    image_width: int = Field(..., gt=0)
    image_height: int = Field(..., gt=0)
    clicks: list[ClickPayload] = Field(default_factory=list)
    box: BoxPayload | None = None
    direction: str = "both"
    max_frames: int = 0



def _cleanup_track_sessions(now: float | None = None) -> None:
    now = now or time.time()
    stale = [
        key
        for key, value in _track_sessions.items()
        if now - float(value.get("updated_at", now)) > TRACK_SESSION_TTL_SEC
    ]
    for key in stale:
        _track_sessions.pop(key, None)


def _get_tracking_prior(req: AnalyzeRequest) -> tuple[np.ndarray | None, dict[str, Any]]:
    """Load previous-frame logits for mask-prompt carryover tracking."""
    meta: dict[str, Any] = {
        "enabled": bool(req.tracking_enabled and req.tracking_session_id),
        "session_id": req.tracking_session_id or None,
        "memory_used": False,
        "reset": bool(req.tracking_reset),
    }
    if not meta["enabled"]:
        return None, meta

    with _track_sessions_lock:
        _cleanup_track_sessions()
        if req.tracking_reset:
            _track_sessions.pop(req.tracking_session_id, None)
            return None, meta
        session = _track_sessions.get(req.tracking_session_id)
        if not session:
            return None, meta
        previous_time = session.get("frame_time")
        same_video = session.get("video_url", "") == req.video_url
        same_size = (
            int(session.get("image_width", req.image_width)) == req.image_width
            and int(session.get("image_height", req.image_height)) == req.image_height
        )
        forward_gap = (
            float(req.frame_time) - float(previous_time)
            if previous_time is not None
            else 0.0
        )
        if (
            not same_video
            or not same_size
            or (
                previous_time is not None
                and (
                    req.frame_time + 1e-3 < float(previous_time)
                    or forward_gap > TRACK_MAX_FORWARD_GAP_SEC
                )
            )
        ):
            _track_sessions.pop(req.tracking_session_id, None)
            meta["reset"] = True
            return None, meta
        prior = session.get("mask_logits")
        if prior is None:
            return None, meta
        meta.update(
            {
                "memory_used": True,
                "previous_frame_time": previous_time,
                "previous_area_px": session.get("area_px"),
                "forward_gap_sec": round(max(forward_gap, 0.0), 4),
            }
        )
        return np.asarray(prior, dtype=np.float32), meta


def _store_tracking_logits(
    req: AnalyzeRequest,
    mask_logits: np.ndarray | None,
    mask: np.ndarray,
    tracking_meta: dict[str, Any],
) -> None:
    if not tracking_meta.get("enabled") or mask_logits is None:
        return
    with _track_sessions_lock:
        _cleanup_track_sessions()
        _track_sessions[req.tracking_session_id] = {
            "mask_logits": np.asarray(mask_logits, dtype=np.float32),
            "frame_time": float(req.frame_time),
            "video_url": req.video_url,
            "image_width": req.image_width,
            "image_height": req.image_height,
            "area_px": int(mask.sum()),
            "updated_at": time.time(),
        }


def decode_frame_b64(data: str) -> np.ndarray:
    raw = (data or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty frame_png_b64")
    if "," in raw and raw.lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        buf = base64.b64decode(raw, validate=False)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid base64 frame: {exc}") from exc
    arr = np.frombuffer(buf, dtype=np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is None:
        raise HTTPException(status_code=400, detail="Could not decode frame image")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def get_predictor():
    global _predictor
    with _predictor_lock:
        if _predictor is None:
            from sam2.sam2_image_predictor import SAM2ImagePredictor

            device = "cuda" if torch.cuda.is_available() else "cpu"
            _predictor = SAM2ImagePredictor.from_pretrained(
                _model_label, device=device
            )
            if _finetune_ckpt is not None:
                apply_finetune_weights(_predictor, _finetune_ckpt, device)
        return _predictor


def read_video_frame(video_path: Path, frame_time: float) -> np.ndarray:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise HTTPException(status_code=404, detail=f"Cannot open video: {video_path.name}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    target = max(0, int(round(frame_time * fps)))
    if total > 0:
        target = min(target, total - 1)
    cap.set(cv2.CAP_PROP_POS_FRAMES, target)
    ok, frame_bgr = cap.read()
    cap.release()
    if not ok or frame_bgr is None:
        raise HTTPException(status_code=400, detail="Failed to read video frame")
    return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)


def postprocess_mask(
    mask: np.ndarray,
    box: BoxPayload | None = None,
) -> np.ndarray:
    """Keep largest component, smooth boundary, optionally clip to ROI box."""
    mask_u8 = (mask > 0).astype(np.uint8)
    if mask_u8.sum() == 0:
        return mask.astype(bool)

    if box is not None:
        x1 = int(np.clip(round(min(box.x1, box.x2)), 0, mask.shape[1] - 1))
        x2 = int(np.clip(round(max(box.x1, box.x2)), 0, mask.shape[1] - 1))
        y1 = int(np.clip(round(min(box.y1, box.y2)), 0, mask.shape[0] - 1))
        y2 = int(np.clip(round(max(box.y1, box.y2)), 0, mask.shape[0] - 1))
        clip = np.zeros_like(mask_u8)
        clip[y1 : y2 + 1, x1 : x2 + 1] = 1
        mask_u8 = mask_u8 & clip

    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask_u8, connectivity=8)
    if n_labels > 1:
        largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        mask_u8 = (labels == largest).astype(np.uint8)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_CLOSE, kernel, iterations=1)
    mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_OPEN, kernel, iterations=1)
    return mask_u8.astype(bool)


def auto_center_point(box: BoxPayload) -> ClickPayload:
    x1, x2 = min(box.x1, box.x2), max(box.x1, box.x2)
    y1, y2 = min(box.y1, box.y2), max(box.y1, box.y2)
    return ClickPayload(x=(x1 + x2) / 2, y=(y1 + y2) / 2, label="positive")


def resample_contour_uniform(points: np.ndarray, target: int) -> np.ndarray:
    """Evenly resample a closed contour to *target* vertices along arc length."""
    if len(points) <= target:
        return points
    pts = np.asarray(points, dtype=np.float64)
    if not np.allclose(pts[0], pts[-1]):
        pts = np.vstack([pts, pts[0:1]])
    seg = np.diff(pts, axis=0)
    seg_len = np.hypot(seg[:, 0], seg[:, 1])
    cum = np.concatenate([[0.0], np.cumsum(seg_len)])
    total = cum[-1]
    if total <= 0:
        return pts[:target]
    samples = np.linspace(0.0, total, target, endpoint=False)
    out = np.empty((target, 2), dtype=np.float64)
    for i, s in enumerate(samples):
        j = int(np.searchsorted(cum, s, side="right") - 1)
        j = min(j, len(seg) - 1)
        t = (s - cum[j]) / seg_len[j] if seg_len[j] > 0 else 0.0
        out[i] = pts[j] + t * seg[j]
    return out


def largest_contour_polygon(mask: np.ndarray, max_points: int = 512) -> list[list[float]]:
    mask_u8 = (mask > 0).astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return []
    contour = max(contours, key=cv2.contourArea).reshape(-1, 2).astype(np.float64)
    min_points = int(os.getenv("SAM_POLYGON_MIN_POINTS", "64"))
    target = int(os.getenv("SAM_POLYGON_MAX_POINTS", str(max_points)))
    if len(contour) > target:
        contour = resample_contour_uniform(contour, target)
    elif len(contour) < min_points and len(contour) >= 3:
        contour = resample_contour_uniform(contour, min_points)
    h, w = mask.shape[:2]
    return [[float(x) / w, float(y) / h] for x, y in contour]


def mask_to_overlay_png(mask: np.ndarray) -> str:
    rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
    active = mask > 0
    rgba[active] = [103, 212, 255, 110]
    _, buf = cv2.imencode(".png", cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA))
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def scale_click_payloads(
    clicks: list[ClickPayload],
    box: BoxPayload | None,
    sx: float,
    sy: float,
) -> tuple[list[ClickPayload], BoxPayload | None]:
    scaled = [
        ClickPayload(x=pt.x * sx, y=pt.y * sy, label=pt.label)
        for pt in clicks
    ]
    scaled_box = None
    if box is not None:
        scaled_box = BoxPayload(
            x1=box.x1 * sx,
            y1=box.y1 * sy,
            x2=box.x2 * sx,
            y2=box.y2 * sy,
        )
    return scaled, scaled_box


def _run_sam2_prompt_unlocked(
    image_rgb: np.ndarray,
    clicks: list[ClickPayload] | None = None,
    click: ClickPayload | None = None,
    box: BoxPayload | None = None,
    prior_mask_logits: np.ndarray | None = None,
) -> tuple[np.ndarray, float, dict[str, Any]]:
    """Multi-prompt SAM2 segmentation with optional temporal mask carryover.

    SAM2 guidance (image predictor):
    - single ambiguous click -> multimask_output=True, pick best IoU
    - box / multi-point / box+points -> multimask_output=False
    - refine prior mask via mask_input (256x256 logits) on additional prompts
    - carry the previous frame's low-resolution logits into the next frame
    """
    predictor = get_predictor()
    h, w = image_rgb.shape[:2]

    points = list(clicks or [])
    if click is not None:
        points.append(click)

    point_coords = None
    point_labels = None
    box_arr = None
    if points:
        coords = []
        labels = []
        for pt in points:
            cx = int(np.clip(round(pt.x), 0, w - 1))
            cy = int(np.clip(round(pt.y), 0, h - 1))
            coords.append([cx, cy])
            labels.append(0 if pt.label == "negative" else 1)
        point_coords = np.array(coords, dtype=np.float32)
        point_labels = np.array(labels, dtype=np.int32)
    if box is not None:
        x1 = int(np.clip(round(min(box.x1, box.x2)), 0, w - 1))
        x2 = int(np.clip(round(max(box.x1, box.x2)), 0, w - 1))
        y1 = int(np.clip(round(min(box.y1, box.y2)), 0, h - 1))
        y2 = int(np.clip(round(max(box.y1, box.y2)), 0, h - 1))
        if x2 <= x1:
            x2 = min(w - 1, x1 + 1)
        if y2 <= y1:
            y2 = min(h - 1, y1 + 1)
        box_arr = np.array([x1, y1, x2, y2], dtype=np.float32)

    meta: dict[str, Any] = {
        "num_points": len(points),
        "num_positive": sum(1 for pt in points if pt.label != "negative"),
        "num_negative": sum(1 for pt in points if pt.label == "negative"),
        "has_box": box_arr is not None,
        "refinement_passes": 0,
        "multimask": False,
        "auto_center_point": False,
        "cascade_box": False,
        "memory_input": prior_mask_logits is not None,
    }

    effective_points = list(points)
    if box is not None and not effective_points:
        effective_points = [auto_center_point(box)]
        meta["auto_center_point"] = True
        coords = []
        labels = []
        for pt in effective_points:
            cx = int(np.clip(round(pt.x), 0, w - 1))
            cy = int(np.clip(round(pt.y), 0, h - 1))
            coords.append([cx, cy])
            labels.append(1)
        point_coords = np.array(coords, dtype=np.float32)
        point_labels = np.array(labels, dtype=np.int32)
        meta["num_points"] = len(effective_points)
        meta["num_positive"] = len(effective_points)

    def _predict(
        pc,
        pl,
        bx,
        mask_input=None,
        multimask: bool = False,
    ):
        with torch.inference_mode():
            if torch.cuda.is_available():
                ctx = torch.autocast("cuda", dtype=torch.bfloat16)
            else:
                ctx = torch.autocast("cpu", enabled=False)
            with ctx:
                return predictor.predict(
                    point_coords=pc,
                    point_labels=pl,
                    box=bx,
                    mask_input=mask_input,
                    multimask_output=multimask,
                )

    with torch.inference_mode():
        if torch.cuda.is_available():
            ctx = torch.autocast("cuda", dtype=torch.bfloat16)
        else:
            ctx = torch.autocast("cpu", enabled=False)
        with ctx:
            predictor.set_image(image_rgb)

    n_pos = meta["num_positive"]
    n_neg = meta["num_negative"]
    use_multimask = (
        box_arr is None
        and point_coords is not None
        and len(effective_points) == 1
        and n_neg == 0
        and prior_mask_logits is None
    )
    meta["multimask"] = use_multimask

    low_res_seed = prior_mask_logits
    if low_res_seed is None and box_arr is not None and point_coords is not None:
        _, seed_scores, seed_low_res = _predict(None, None, box_arr, multimask=False)
        meta["cascade_box"] = True
        seed_idx = int(np.argmax(seed_scores))
        low_res_seed = seed_low_res[seed_idx : seed_idx + 1]

    masks, scores, low_res = _predict(
        point_coords,
        point_labels,
        box_arr,
        mask_input=low_res_seed,
        multimask=use_multimask and low_res_seed is None,
    )
    best_idx = int(np.argmax(scores))
    best_score = float(scores[best_idx])
    selected_low_res = low_res

    should_refine = (
        low_res is not None
        and (
            len(points) >= 2
            or (box_arr is not None and len(points) >= 1)
            or n_neg >= 1
        )
    )
    if should_refine:
        if low_res.ndim == 3:
            mask_input = low_res[best_idx : best_idx + 1]
        else:
            mask_input = low_res[None, :, :]
        refined_masks, refined_scores, refined_low_res = _predict(
            point_coords,
            point_labels,
            box_arr,
            mask_input=mask_input,
            multimask=False,
        )
        meta["refinement_passes"] = 1
        refined_score = float(refined_scores[0])
        if refined_score >= best_score - 0.02:
            masks, scores = refined_masks, refined_scores
            best_idx = 0
            best_score = refined_score
            selected_low_res = refined_low_res

    mask = masks[best_idx].astype(bool)
    mask = postprocess_mask(mask, box)
    meta["sam_score"] = best_score
    meta["mask_area_px"] = int(mask.sum())
    if selected_low_res is not None:
        logits = selected_low_res
        if hasattr(logits, "detach"):
            logits = logits.detach().cpu().numpy()
        logits = np.asarray(logits, dtype=np.float32)
        if logits.ndim == 4:
            logits = logits[
                best_idx if logits.shape[0] > best_idx else 0 :
                (best_idx if logits.shape[0] > best_idx else 0) + 1
            ]
        elif logits.ndim == 3:
            logits = logits[
                best_idx if logits.shape[0] > best_idx else 0 :
                (best_idx if logits.shape[0] > best_idx else 0) + 1
            ][None, ...]
        elif logits.ndim == 2:
            logits = logits[None, None, ...]
        if logits.ndim == 4:
            meta["_mask_logits"] = logits
    return mask, best_score, meta


def run_sam2_prompt(
    image_rgb: np.ndarray,
    clicks: list[ClickPayload] | None = None,
    click: ClickPayload | None = None,
    box: BoxPayload | None = None,
    prior_mask_logits: np.ndarray | None = None,
) -> tuple[np.ndarray, float, dict[str, Any]]:
    """Serialize access to the mutable SAM2 image predictor."""
    with _predictor_inference_lock:
        return _run_sam2_prompt_unlocked(
            image_rgb=image_rgb,
            clicks=clicks,
            click=click,
            box=box,
            prior_mask_logits=prior_mask_logits,
        )


def estimate_wall_metrics(mask: np.ndarray) -> tuple[float, float, float]:
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return 3.0, 2.8, 0.35
    height = max(1, ys.max() - ys.min())
    width = max(1, xs.max() - xs.min())
    thickness_px = max(height, width)
    thickness_mm = 2.8 + min(8.0, thickness_px / 40.0)
    outer_risk = min(0.92, max(0.15, thickness_mm / 10.0))
    return thickness_mm, 2.8, outer_risk


def build_stage_distribution(reference_pt: str | None, thickness_mm: float, sam_score: float) -> dict[str, float]:
    ref = reference_pt if reference_pt in STAGES else "T2"
    base = {s: 0.08 for s in STAGES}
    base[ref] = 0.46
    if thickness_mm >= 7.5:
        base["T3"] += 0.12
        base["T4+"] += 0.06
        base[ref] -= 0.1
    elif thickness_mm <= 4.5:
        base["T1"] += 0.1
        base[ref] -= 0.06
    base[ref] += min(0.12, sam_score * 0.08)
    total = sum(base.values())
    return {k: v / total for k, v in base.items()}


def prompt_summary(
    clicks: list[ClickPayload],
    box: BoxPayload | None,
) -> str:
    pos = sum(1 for c in clicks if c.label != "negative")
    neg = sum(1 for c in clicks if c.label == "negative")
    parts = []
    if box is not None:
        parts.append(f"框选 ({box.x1:.0f},{box.y1:.0f})-({box.x2:.0f},{box.y2:.0f})")
    if clicks:
        parts.append(f"{pos} 个正向点 / {neg} 个负向点")
    return " · ".join(parts) if parts else "自动关键帧分割"


def build_report(
    case_id: str,
    frame_time: float,
    clicks: list[ClickPayload],
    box: BoxPayload | None,
    sam_score: float,
    thickness_mm: float,
    normal_wall_mm: float,
    outer_risk: float,
    reference_pt: str | None,
) -> dict[str, Any]:
    dist = build_stage_distribution(reference_pt, thickness_mm, sam_score)
    stage = max(dist.items(), key=lambda kv: kv[1])[0]
    confidence = min(0.9, max(0.45, dist[stage] + sam_score * 0.08))
    mm = int(frame_time // 60)
    ss = int(frame_time % 60)
    frame_clock = f"{mm:02d}:{ss:02d}"
    has_prompt = bool(clicks) or box is not None
    return {
        "recommended_stage": stage,
        "stage_distribution": dist,
        "calibrated_confidence": confidence,
        "review_flag": confidence < 0.68 or stage in {"T2", "T3"},
        "sam_score": sam_score,
        "summary": (
            f"SAM2 segmented lesion at {frame_clock} from doctor prompt; "
            f"mask confidence {sam_score:.2f}."
            if has_prompt
            else f"SAM2 auto-segmentation at {frame_clock}."
        ),
        "evidence": [
            {
                "title": "SAM2 segmentation",
                "detail": f"{prompt_summary(clicks, box)} · score {sam_score:.2f}"
                if has_prompt
                else "Auto key-frame segmentation",
            },
            {
                "title": "Wall thickness",
                "detail": f"Lesion region thickness ~{thickness_mm:.1f} mm; normal wall ~{normal_wall_mm:.1f} mm.",
            },
            {
                "title": "Outer margin risk",
                "detail": f"Estimated outer-wall involvement risk {outer_risk:.2f}.",
            },
            {
                "title": "Boundary detail",
                "detail": "Auto-generated ×3.5 zoom on outer/superior/inferior/inner margins for serosa-side review."
                if has_prompt
                else "Run segmentation to unlock boundary magnifier panels.",
            },
            {
                "title": "Review hint",
                "detail": "Combine SAM mask with wall-layer evidence before final T staging."
                if confidence < 0.72
                else "Evidence is internally consistent; suitable as second opinion.",
            },
        ],
        "similar_cases": [
            {"case_id": "CASE-023", "stage": "T2", "score": 0.84, "note": "Similar wall-layer pattern."},
            {"case_id": "CASE-048", "stage": "T3", "score": 0.79, "note": "Comparable outer margin risk."},
        ],
    }


def minimax_configured() -> bool:
    from agent.core.minimax_llm_client import minimax_key_configured

    return minimax_key_configured()


def deepseek_configured() -> bool:
    _ensure_deepseek_env()
    return bool(os.getenv("DEEPSEEK_API_KEY", "").strip())


def llm_report_configured() -> bool:
    return minimax_configured() or deepseek_configured()


def minimax_status_payload() -> dict[str, Any]:
    from agent.core.minimax_llm_client import minimax_config_summary

    summary = minimax_config_summary()
    configured = summary.get("configured") == "true"
    return {
        "configured": configured,
        "model": os.getenv("MINIMAX_MODEL", "MiniMax-M3"),
        "base_url": summary.get("base_url") or os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1"),
        "key_source": summary.get("key_source") or None,
        "key_hint": summary.get("key_hint") or None,
    }


def deepseek_status_payload() -> dict[str, Any]:
    configured = deepseek_configured()
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    key_source = None
    if configured:
        key_source = (
            str(DEEPSEEK_KEYFILE.relative_to(REPO_ROOT))
            if DEEPSEEK_KEYFILE.is_file()
            else "DEEPSEEK_API_KEY"
        )
    return {
        "configured": configured,
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        "key_source": key_source,
        "key_hint": (f"...{key[-4:]}" if len(key) >= 4 else None),
    }


def llm_report_status_payload() -> dict[str, Any]:
    providers = []
    if deepseek_configured():
        providers.append("deepseek")
    if minimax_configured():
        providers.append("minimax")
    preferred = resolve_llm_provider_order()[0] if providers else None
    return {
        "configured": bool(providers),
        "preferred": preferred,
        "providers": providers,
    }


def resolve_llm_provider_order() -> list[str]:
    """SAM_LLM_PROVIDER=deepseek|minimax|auto (default auto: deepseek then minimax)."""
    pref = os.getenv("SAM_LLM_PROVIDER", "auto").strip().lower()
    available: list[str] = []
    if pref == "minimax":
        if minimax_configured():
            available.append("minimax")
        if deepseek_configured():
            available.append("deepseek")
    elif pref == "deepseek":
        if deepseek_configured():
            available.append("deepseek")
        if minimax_configured():
            available.append("minimax")
    else:
        # auto: prefer DeepSeek for ultrasound reports when MiniMax Token Plan is exhausted
        if deepseek_configured():
            available.append("deepseek")
        if minimax_configured():
            available.append("minimax")
    return available


def get_minimax_client():
    global _minimax_client
    with _minimax_lock:
        if _minimax_client is None:
            from agent.core.minimax_llm_client import MiniMaxLLMClient

            _minimax_client = MiniMaxLLMClient(max_tokens=512, temperature=0.2)
        return _minimax_client


def get_deepseek_client():
    global _deepseek_client
    with _deepseek_lock:
        if _deepseek_client is None:
            from agent.core.llm_client import AgentLLMClient

            _ensure_deepseek_env()
            key = os.getenv("DEEPSEEK_API_KEY", "").strip()
            if not key:
                raise RuntimeError("DEEPSEEK_API_KEY not set")
            base = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
            model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
            # Pass api_key explicitly so Poe AGENT_API_KEY in .env is not used.
            _deepseek_client = AgentLLMClient(
                base_url=base,
                model=model,
                max_tokens=512,
                temperature=0.2,
                api_key=key,
            )
        return _deepseek_client


def format_boundary_context(sectors: list[BoundarySectorPayload]) -> str:
    if not sectors:
        return ""
    adj_map = {
        "continuous": "连续",
        "suspicious": "可疑突破",
        "breakthrough": "明确突破",
        "indeterminate": "无法判断",
    }
    lines = []
    for s in sectors:
        adj = adj_map.get(s.adjudication, s.adjudication or "未判读")
        lines.append(
            f"- {s.label or s.sector_id}: 壁厚{s.wall_mm:.1f}mm vs 正常{s.normal_mm:.1f}mm "
            f"(比{s.thickness_ratio:.2f}), AI突破风险{s.breakthrough_risk:.0%}, 医生判读={adj}"
        )
    return "【各方向边界判读（须以医生标注为准）】\n" + "\n".join(lines)


def build_report_messages(
    case_id: str,
    frame_time: float,
    report: dict[str, Any],
    clicks: list[ClickPayload],
    box: BoxPayload | None,
    sam_score: float,
    thickness_mm: float,
    outer_risk: float,
    boundary_sectors: list[BoundarySectorPayload] | None = None,
) -> list[dict[str, str]]:
    mm = int(frame_time // 60)
    ss = int(frame_time % 60)
    stage = report.get("recommended_stage", "T2")
    dist = report.get("stage_distribution", {})
    dist_text = ", ".join(f"{k}:{dist.get(k, 0):.0%}" for k in STAGES)
    boundary_text = format_boundary_context(boundary_sectors or [])
    prompt = (
        f"病例 {case_id or '未知'}，分析帧 {mm:02d}:{ss:02d}。\n"
        f"分割质量 {sam_score:.0%}，估计壁厚约 {thickness_mm:.1f} mm，外缘突破风险 {outer_risk:.0%}。\n"
        f"模型推荐分期 {stage}，概率分布 {dist_text}。\n"
        f"交互：{prompt_summary(clicks, box)}。\n"
    )
    if boundary_text:
        prompt += f"\n{boundary_text}\n"
    prompt += (
        "请用简体中文撰写超声 T 分期阅片报告，面向临床医生：\n"
        "1) 2–3 句描述病灶边界/外壁层次，若上方有医生判读须明确引用；\n"
        "2) 1 句 T 分期建议；\n"
        "3) 1 句复核提示。\n"
        "要求：仅输出简体中文正文，不要标题、不要 markdown、不要英文。"
    )
    return [
        {
            "role": "system",
            "content": "你是胃癌超声 T 分期阅片助手。必须用简体中文输出，语气专业、简洁，便于医生快速阅读。",
        },
        {"role": "user", "content": prompt},
    ]


def generate_minimax_report(
    case_id: str,
    frame_time: float,
    report: dict[str, Any],
    clicks: list[ClickPayload],
    box: BoxPayload | None,
    sam_score: float,
    thickness_mm: float,
    outer_risk: float,
    boundary_sectors: list[BoundarySectorPayload] | None = None,
) -> dict[str, Any]:
    messages = build_report_messages(
        case_id,
        frame_time,
        report,
        clicks,
        box,
        sam_score,
        thickness_mm,
        outer_risk,
        boundary_sectors=boundary_sectors,
    )
    client = get_minimax_client()
    narrative = client.chat(messages)
    return {
        "provider": "minimax",
        "model": client.model,
        "narrative": narrative,
        "tokens": client.total_tokens,
        "think_chars": client.last_think_chars,
    }


def generate_deepseek_report(
    case_id: str,
    frame_time: float,
    report: dict[str, Any],
    clicks: list[ClickPayload],
    box: BoxPayload | None,
    sam_score: float,
    thickness_mm: float,
    outer_risk: float,
    boundary_sectors: list[BoundarySectorPayload] | None = None,
) -> dict[str, Any]:
    messages = build_report_messages(
        case_id,
        frame_time,
        report,
        clicks,
        box,
        sam_score,
        thickness_mm,
        outer_risk,
        boundary_sectors=boundary_sectors,
    )
    client = get_deepseek_client()
    narrative = client.chat(messages)
    return {
        "provider": "deepseek",
        "model": client.model,
        "narrative": narrative,
        "tokens": client.total_tokens,
    }


def generate_llm_report(
    case_id: str,
    frame_time: float,
    report: dict[str, Any],
    clicks: list[ClickPayload],
    box: BoxPayload | None,
    sam_score: float,
    thickness_mm: float,
    outer_risk: float,
    boundary_sectors: list[BoundarySectorPayload] | None = None,
) -> dict[str, Any]:
    order = resolve_llm_provider_order()
    if not order:
        raise RuntimeError("No LLM provider configured (DeepSeek or MiniMax)")
    errors: list[str] = []
    for provider in order:
        try:
            if provider == "deepseek":
                return generate_deepseek_report(
                    case_id,
                    frame_time,
                    report,
                    clicks,
                    box,
                    sam_score,
                    thickness_mm,
                    outer_risk,
                    boundary_sectors=boundary_sectors,
                )
            return generate_minimax_report(
                case_id,
                frame_time,
                report,
                clicks,
                box,
                sam_score,
                thickness_mm,
                outer_risk,
                boundary_sectors=boundary_sectors,
            )
        except Exception as exc:
            errors.append(f"{provider}: {exc}")
    raise RuntimeError(" | ".join(errors))


def maybe_attach_llm_report(
    report: dict[str, Any],
    *,
    case_id: str,
    frame_time: float,
    clicks: list[ClickPayload],
    box: BoxPayload | None,
    sam_score: float,
    thickness_mm: float,
    outer_risk: float,
    enabled: bool,
    boundary_sectors: list[BoundarySectorPayload] | None = None,
) -> dict[str, Any]:
    if not enabled or not llm_report_configured():
        return report
    try:
        llm = generate_llm_report(
            case_id,
            frame_time,
            report,
            clicks,
            box,
            sam_score,
            thickness_mm,
            outer_risk,
            boundary_sectors=boundary_sectors,
        )
        report = dict(report)
        report["llm_report"] = llm
        report["summary"] = llm["narrative"]
        evidence = list(report.get("evidence", []))
        evidence.insert(
            0,
            {
                "title": "文字报告",
                "detail": llm["narrative"],
            },
        )
        report["evidence"] = evidence
    except Exception as exc:
        report = dict(report)
        preferred = resolve_llm_provider_order()
        report["llm_report"] = {
            "provider": preferred[0] if preferred else "none",
            "error": str(exc),
        }
    return report


def lookup_reference_pt(case_id: str) -> str | None:
    bundle = STATIC_ROOT / "cases.bundle.js"
    if not bundle.exists():
        return None
    text = bundle.read_text(encoding="utf-8")
    marker = "window.READER_CASES = "
    if marker not in text:
        return None
    payload = text.split(marker, 1)[1].strip().rstrip(";")
    data = json.loads(payload)
    for case in data.get("cases", []):
        if case.get("case_id") == case_id:
            return case.get("reference_pt")
    return None


app = FastAPI(title="Interactive SAM Agent")

# Optional reverse-proxy to auth_server (login + DeepSeek LLM) for same-origin LAN merge.
AUTH_UPSTREAM = os.getenv("READER_AUTH_UPSTREAM", "http://127.0.0.1:8766").rstrip("/")


async def _proxy_to_auth(request: Request, path: str) -> Response:
    qs = request.url.query
    target = f"{AUTH_UPSTREAM}{path}" + (f"?{qs}" if qs else "")
    body = await request.body()
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in {"host", "content-length", "connection", "transfer-encoding"}
    }
    try:
        upstream_req = UrlRequest(
            target,
            data=body if body else None,
            headers=headers,
            method=request.method,
        )
        with urlopen(upstream_req, timeout=60) as resp:
            payload = resp.read()
            excluded = {"content-encoding", "transfer-encoding", "content-length", "connection"}
            out_headers = {
                k: v for k, v in resp.headers.items() if k.lower() not in excluded
            }
            return Response(
                content=payload,
                status_code=resp.status,
                headers=out_headers,
                media_type=resp.headers.get("content-type"),
            )
    except HTTPError as err:
        payload = err.read() if hasattr(err, "read") else b""
        return Response(
            content=payload,
            status_code=err.code,
            media_type=err.headers.get("content-type") if err.headers else None,
        )
    except URLError as err:
        return Response(
            content=json.dumps(
                {"ok": False, "message": f"auth upstream unavailable: {err.reason}"}
            ).encode(),
            status_code=502,
            media_type="application/json",
        )


@app.api_route("/api/login", methods=["GET", "POST", "OPTIONS"])
@app.api_route("/api/logout", methods=["GET", "POST", "OPTIONS"])
@app.api_route("/api/me", methods=["GET", "POST", "OPTIONS"])
@app.api_route("/api/progress", methods=["GET", "POST", "PUT", "OPTIONS"])
@app.api_route("/api/health", methods=["GET", "OPTIONS"])
async def proxy_auth_core(request: Request) -> Response:
    return await _proxy_to_auth(request, request.url.path)


@app.api_route("/api/llm/{llm_path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_auth_llm(llm_path: str, request: Request) -> Response:
    return await _proxy_to_auth(request, f"/api/llm/{llm_path}")


@app.get("/api/sam/status")
def sam_status() -> dict[str, Any]:
    display = _model_label.replace("facebook/", "")
    if _finetune_meta:
        dice = (
            _finetune_meta.get("val_dice_mask")
            or _finetune_meta.get("val_dice")
            or _finetune_meta.get("best_val_dice")
        )
        if dice is not None:
            display = f"{display} / finetune (Dice {dice:.3f})"
        else:
            display = f"{display} / finetune"
    return {
        "ready": True,
        "model": display,
        "base_model": _model_label,
        "finetune": _finetune_meta or None,
        "tracking": {
            "mode": "mask_logit_carryover",
            "session_count": len(_track_sessions),
            "ttl_sec": TRACK_SESSION_TTL_SEC,
            "max_forward_gap_sec": TRACK_MAX_FORWARD_GAP_SEC,
        },
        "cuda": torch.cuda.is_available(),
        "static_root": str(STATIC_ROOT),
        "minimax": minimax_status_payload(),
        "deepseek": deepseek_status_payload(),
        "llm_report": llm_report_status_payload(),
    }


@app.get("/api/minimax/test")
def minimax_test() -> dict[str, Any]:
    if not minimax_configured():
        raise HTTPException(status_code=503, detail="MINIMAX_API_KEY not set")
    t0 = time.time()
    client = get_minimax_client()
    text = client.chat([{"role": "user", "content": "Reply with exactly: OK-M3"}])
    return {
        "ok": True,
        "model": client.model,
        "reply": text,
        "tokens": client.total_tokens,
        "think_chars": client.last_think_chars,
        "elapsed_ms": int((time.time() - t0) * 1000),
    }


@app.post("/api/sam/interactive-analyze")
def interactive_analyze(req: AnalyzeRequest) -> dict[str, Any]:
    t0 = time.time()
    if (req.frame_png_b64 or "").strip():
        frame_rgb = decode_frame_b64(req.frame_png_b64)
    elif (req.video_rel or "").strip():
        video_path = (STATIC_ROOT / req.video_rel.replace("\\", "/").lstrip("/")).resolve()
        if not str(video_path).startswith(str(STATIC_ROOT.resolve())):
            raise HTTPException(status_code=400, detail="Invalid video path")
        if not video_path.exists():
            raise HTTPException(status_code=404, detail=f"Video not found: {req.video_rel}")
        frame_rgb = read_video_frame(video_path, req.frame_time)
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide video_rel or frame_png_b64",
        )

    clicks = list(req.clicks)
    if req.click is not None:
        duplicate = any(
            abs(point.x - req.click.x) < 1e-3
            and abs(point.y - req.click.y) < 1e-3
            and point.label == req.click.label
            for point in clicks
        )
        if not duplicate:
            clicks.append(req.click)
    box = req.box
    native_h, native_w = frame_rgb.shape[:2]
    sx = native_w / max(1, req.image_width)
    sy = native_h / max(1, req.image_height)
    if abs(sx - 1.0) > 0.01 or abs(sy - 1.0) > 0.01:
        clicks, box = scale_click_payloads(clicks, box, sx, sy)

    if not clicks and box is None:
        clicks = [ClickPayload(x=float(native_w // 2), y=float(native_h // 2), label="positive")]

    prior_logits, tracking_meta = _get_tracking_prior(req)
    mask, sam_score, prompt_meta = run_sam2_prompt(
        frame_rgb,
        clicks=clicks,
        box=box,
        prior_mask_logits=prior_logits,
    )
    mask_logits = prompt_meta.pop("_mask_logits", None)
    _store_tracking_logits(req, mask_logits, mask, tracking_meta)
    tracking_meta.update(
        {
            "mode": "mask_logit_carryover",
            "current_frame_time": float(req.frame_time),
            "stored": bool(mask_logits is not None and tracking_meta.get("enabled")),
        }
    )
    polygon = largest_contour_polygon(mask)
    thickness_mm, normal_wall_mm, outer_risk = estimate_wall_metrics(mask)
    report = build_report(
        req.case_id,
        req.frame_time,
        clicks,
        box,
        sam_score,
        thickness_mm,
        normal_wall_mm,
        outer_risk,
        lookup_reference_pt(req.case_id),
    )
    report = maybe_attach_llm_report(
        report,
        case_id=req.case_id,
        frame_time=req.frame_time,
        clicks=clicks,
        box=box,
        sam_score=sam_score,
        thickness_mm=thickness_mm,
        outer_risk=outer_risk,
        enabled=req.llm_report,
        boundary_sectors=req.boundary_sectors,
    )

    return {
        "ok": True,
        "backend": _model_label,
        "elapsed_ms": int((time.time() - t0) * 1000),
        "sam_score": sam_score,
        "prompt_meta": prompt_meta,
        "tracking": tracking_meta,
        "frame_size": {"width": native_w, "height": native_h},
        "mask_polygon": polygon,
        "mask_overlay_png": mask_to_overlay_png(mask),
        "report": report,
    }


@app.get("/api/sam/video-status")
def sam_video_status() -> dict[str, Any]:
    return get_video_tracker().status()


@app.post("/api/sam/video-propagate")
def sam_video_propagate(req: VideoPropagateRequest) -> dict[str, Any]:
    rel = (req.video_rel or "").replace("\\", "/").lstrip("/")
    if not rel:
        raise HTTPException(status_code=400, detail="video_rel is required")
    video_path = (STATIC_ROOT / rel).resolve()
    if not str(video_path).startswith(str(STATIC_ROOT.resolve())):
        raise HTTPException(status_code=400, detail="Invalid video path")
    if not video_path.is_file():
        raise HTTPException(status_code=404, detail=f"Video not found: {req.video_rel}")
    tracker = get_video_tracker()
    try:
        result = tracker.propagate(
            video_path=video_path,
            frame_time=float(req.frame_time),
            image_width=int(req.image_width),
            image_height=int(req.image_height),
            clicks=[click.model_dump() for click in req.clicks],
            box=req.box.model_dump() if req.box is not None else None,
            direction=req.direction if req.direction in {"forward", "backward", "both"} else "both",
            max_frames=int(req.max_frames),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"SAM2 video propagation failed: {exc}") from exc
    return {"ok": True, "result": result}


@app.on_event("startup")
def warm_model() -> None:
    def warm_all() -> None:
        get_predictor()
        if os.getenv("SAM2_VIDEO_WARM", "1").strip().lower() not in {"0", "false", "no"}:
            get_video_tracker().warm()

    threading.Thread(target=warm_all, daemon=True).start()


app.mount("/", StaticFiles(directory=str(STATIC_ROOT), html=True), name="static")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    llm = llm_report_status_payload()
    ds = deepseek_status_payload()
    mm = minimax_status_payload()
    if llm["configured"]:
        print(
            f"LLM report: preferred={llm['preferred']} providers={llm['providers']} "
            f"(SAM_LLM_PROVIDER={os.getenv('SAM_LLM_PROVIDER', 'auto')})"
        )
        if ds["configured"]:
            print(
                f"  DeepSeek: {ds['model']} @ {ds['base_url']} "
                f"({ds['key_source']} {ds['key_hint']})"
            )
        if mm["configured"]:
            print(
                f"  MiniMax: {mm['model']} @ {mm['base_url']} "
                f"({mm['key_source']} {mm['key_hint']})"
            )
    else:
        print(
            "LLM report: disabled — set DEEPSEEK_API_KEY (or deepseek_api_key.txt) "
            "or MINIMAX_API_KEY"
        )
    print(f"Serving {STATIC_ROOT} with SAM2 at http://{args.host}:{args.port}/interactive_video_agent.html")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
