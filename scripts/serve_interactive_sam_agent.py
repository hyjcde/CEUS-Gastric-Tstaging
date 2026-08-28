#!/usr/bin/env python3
"""Serve the SAM2 inference API used by the Next workbench.

Usage:
  python3 scripts/serve_interactive_sam_agent.py --host 127.0.0.1 --port 8767

The legacy HTML frontend is disabled by default. Set SERVE_LEGACY_HTML=1 only
for an explicitly isolated compatibility run.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import re
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
from urllib.parse import parse_qs, urlparse
from urllib.request import Request as UrlRequest, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_ROOT = REPO_ROOT / "pipeline"
STATIC_ROOT = REPO_ROOT / "docs/clinical_validation/reader_study_v150"
SERVE_LEGACY_HTML = os.getenv("SERVE_LEGACY_HTML", "").strip().lower() in {"1", "true", "yes", "on"}
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
_feature_adapter: torch.nn.Module | None = None
_track_sessions: dict[str, dict[str, Any]] = {}
_track_sessions_lock = threading.Lock()
TRACK_SESSION_TTL_SEC = 3600.0
TRACK_MAX_FORWARD_GAP_SEC = 2.0

_video_tracker = None
_video_tracker_lock = threading.Lock()
_dino_model = None
_dino_model_id = ""
_dino_model_lock = threading.Lock()

DINO_CONFIG_PATH = REPO_ROOT / "configs/segmentation/dinov3/vitb16_last2blocks_mlp_decoder.yaml"
DINO_REPO_PATH = REPO_ROOT / "external/dinov3/dinov3"
DINO_CHECKPOINT_PATH = REPO_ROOT / "external/dinov3/weights/dinov3_vitb16_pretrain_lvd1689m-73cec8be.pth"
DINO_IMAGE_SIZE = 512
DINO_MEAN = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)
DINO_STD = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)
DINO_DEFAULT_LAYERS = (2, 5, 8, 11)


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


def _attach_feature_adapter(predictor: Any, adapter: torch.nn.Module) -> None:
    """Apply a trained static feature adapter to image-predictor embeddings."""

    original_set_image = predictor.set_image

    def set_image_with_adapter(image: np.ndarray) -> None:
        original_set_image(image)
        features = predictor._features
        levels = list(features["high_res_feats"]) + [features["image_embed"]]
        with torch.inference_mode():
            adapted = adapter(levels)
        predictor._features = {
            "image_embed": adapted[-1],
            "high_res_feats": adapted[:-1],
        }

    predictor.set_image = set_image_with_adapter


def apply_finetune_weights(predictor, ckpt_path: Path, device: str) -> None:
    global _finetune_meta, _feature_adapter
    ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    raw = ckpt.get("model_state_dict", ckpt)
    state = {
        k.replace("sam2_model.", "", 1): v
        for k, v in raw.items()
        if k.startswith("sam2_model.")
    }
    adapter_state = {
        k.replace("feature_adapter.", "", 1): v
        for k, v in raw.items()
        if k.startswith("feature_adapter.")
    }
    adaptation_mode = ckpt.get("adaptation_mode") or (
        "context_edge" if adapter_state else "decoder_only"
    )
    if not state:
        raise RuntimeError(f"No sam2_model.* weights in checkpoint: {ckpt_path}")
    predictor.model.load_state_dict(state, strict=True)
    _feature_adapter = None
    if adapter_state:
        from prompt_mask.sam2_adapters import MultiScaleContextEdgeAdapter

        bottleneck_value = ckpt.get("adapter_bottleneck")
        if bottleneck_value is None:
            down_weight = adapter_state.get("adapters.0.down.weight")
            bottleneck_value = (
                int(down_weight.shape[0])
                if hasattr(down_weight, "shape") and len(down_weight.shape) >= 1
                else 32
            )
        bottleneck = int(bottleneck_value)
        adapter = MultiScaleContextEdgeAdapter(
            (32, 64, 256),
            bottleneck=bottleneck,
        ).to(device)
        missing, unexpected = adapter.load_state_dict(adapter_state, strict=True)
        if missing or unexpected:
            raise RuntimeError(
                "Feature adapter checkpoint mismatch: "
                f"missing={len(missing)} unexpected={len(unexpected)}"
            )
        adapter.eval()
        _feature_adapter = adapter
        _attach_feature_adapter(predictor, adapter)
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
        "adaptation_mode": adaptation_mode,
        "adapter_bottleneck": (
            int(bottleneck_value) if adapter_state else ckpt.get("adapter_bottleneck")
        ),
        "feature_adapter_loaded": bool(adapter_state),
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
    gc_us_report: dict[str, Any] | None = None
    # Overlay PNGs are large (~MB) and can fail browser fetch ("Load failed").
    # Contour UIs only need mask_polygon; opt in for raster preview.
    include_overlay: bool = False


class VideoPropagateRequest(BaseModel):
    case_id: str = ""
    video_rel: str = ""
    video_url: str = ""
    frame_time: float = 0.0
    image_width: int = Field(..., gt=0)
    image_height: int = Field(..., gt=0)
    clicks: list[ClickPayload] = Field(default_factory=list)
    box: BoxPayload | None = None
    direction: str = "both"
    max_frames: int = 0


class DinoRoiBBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class DinoFeaturesRequest(BaseModel):
    case_id: str = ""
    frame_time: float = 0.0
    frame_png_b64: str = ""
    image_width: int = Field(..., gt=0)
    image_height: int = Field(..., gt=0)
    lesion_polygon: list[list[float]] = Field(default_factory=list)
    wall_polygon: list[list[float]] = Field(default_factory=list)
    roi_bbox: DinoRoiBBox | None = None
    layer_index: int = 11
    layer_indices: list[int] = Field(default_factory=list)


def dino_assets_status() -> dict[str, Any]:
    return {
        "available": bool(DINO_CONFIG_PATH.is_file() and DINO_REPO_PATH.is_dir() and DINO_CHECKPOINT_PATH.is_file()),
        "loaded": _dino_model is not None,
        "model": _dino_model_id or "dinov3_vitb16",
        "config": str(DINO_CONFIG_PATH),
        "checkpoint": str(DINO_CHECKPOINT_PATH),
        "input_size": DINO_IMAGE_SIZE,
        "feature_dim": 4608,
    }


def get_dino_model() -> tuple[Any, str]:
    global _dino_model, _dino_model_id
    with _dino_model_lock:
        if _dino_model is None:
            if not dino_assets_status()["available"]:
                raise FileNotFoundError("DINOv3 repo, config, or checkpoint is unavailable")
            import yaml

            config = yaml.safe_load(DINO_CONFIG_PATH.read_text(encoding="utf-8")) or {}
            hub_model = str(config.get("model", {}).get("hub_model", "dinov3_vitb16"))
            device = "cuda" if torch.cuda.is_available() else "cpu"
            _dino_model = torch.hub.load(
                str(DINO_REPO_PATH),
                hub_model,
                source="local",
                weights=str(DINO_CHECKPOINT_PATH),
            ).to(device).eval()
            _dino_model_id = hub_model
        return _dino_model, _dino_model_id


def polygon_to_grid(
    polygon: list[list[float]],
    image_width: int,
    image_height: int,
    grid_height: int,
    grid_width: int,
) -> np.ndarray | None:
    if len(polygon) < 3:
        return None
    points = np.asarray(polygon, dtype=np.float32).reshape(-1, 1, 2)
    points[:, 0, 0] = np.clip(points[:, 0, 0], 0, max(image_width - 1, 0))
    points[:, 0, 1] = np.clip(points[:, 0, 1], 0, max(image_height - 1, 0))
    mask = np.zeros((image_height, image_width), dtype=np.uint8)
    cv2.fillPoly(mask, [np.round(points).astype(np.int32)], 1)
    return cv2.resize(mask, (grid_width, grid_height), interpolation=cv2.INTER_NEAREST).astype(bool)


def dino_pool(tokens: np.ndarray, mask: np.ndarray | None) -> np.ndarray:
    if mask is None or not mask.any():
        return tokens.mean(axis=0)
    return tokens[mask.reshape(-1)].mean(axis=0)


def dino_cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom > 1e-8 else 0.0


def dino_cosine_map(tokens: np.ndarray, vector: np.ndarray) -> np.ndarray:
    token_norm = np.linalg.norm(tokens, axis=1)
    vector_norm = float(np.linalg.norm(vector))
    if vector_norm <= 1e-8:
        return np.zeros(tokens.shape[0], dtype=np.float32)
    return (tokens @ vector / np.maximum(token_norm * vector_norm, 1e-8)).astype(np.float32)


def _encode_png_bgr(image_bgr: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".png", image_bgr)
    if not ok:
        return ""
    return f"data:image/png;base64,{base64.b64encode(encoded.tobytes()).decode('ascii')}"


def resolve_dino_roi_box(
    req: DinoFeaturesRequest,
    image_width: int,
    image_height: int,
    margin: int = 48,
) -> tuple[int, int, int, int] | None:
    if req.roi_bbox is not None:
        x1, y1, x2, y2 = (
            float(req.roi_bbox.x1),
            float(req.roi_bbox.y1),
            float(req.roi_bbox.x2),
            float(req.roi_bbox.y2),
        )
    else:
        points: list[list[float]] = []
        points.extend(req.lesion_polygon or [])
        points.extend(req.wall_polygon or [])
        if len(points) < 3:
            return None
        xs = [float(pt[0]) for pt in points if len(pt) >= 2]
        ys = [float(pt[1]) for pt in points if len(pt) >= 2]
        if not xs or not ys:
            return None
        x1, y1, x2, y2 = min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin
    left = int(max(0, min(image_width - 2, math.floor(x1))))
    top = int(max(0, min(image_height - 2, math.floor(y1))))
    right = int(max(left + 8, min(image_width, math.ceil(x2))))
    bottom = int(max(top + 8, min(image_height, math.ceil(y2))))
    if right - left < 8 or bottom - top < 8:
        return None
    return left, top, right, bottom


def crop_overlay_png(data_url: str, box: tuple[int, int, int, int] | None) -> str:
    if not data_url or box is None or "," not in data_url:
        return ""
    raw = np.frombuffer(base64.b64decode(data_url.split(",", 1)[1]), dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if image is None:
        return ""
    x1, y1, x2, y2 = box
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return ""
    return _encode_png_bgr(crop)


def dino_overlay_png(image_rgb: np.ndarray, feature_map: np.ndarray, cmap: int) -> str:
    h, w = image_rgb.shape[:2]
    normalized = cv2.normalize(feature_map, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    heatmap = cv2.applyColorMap(cv2.resize(normalized, (w, h), interpolation=cv2.INTER_CUBIC), cmap)
    image_bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
    overlay = cv2.addWeighted(image_bgr, 0.48, heatmap, 0.52, 0)
    return _encode_png_bgr(overlay)


def build_dino_layer_result(
    image_rgb: np.ndarray,
    feature_map: np.ndarray,
    layer_index: int,
    model_id: str,
    lesion: np.ndarray | None,
    wall: np.ndarray | None,
    boundary: np.ndarray | None,
    roi_box: tuple[int, int, int, int] | None = None,
) -> dict[str, Any]:
    channels, grid_height, grid_width = feature_map.shape
    tokens = feature_map.reshape(channels, grid_height * grid_width).T
    pooled = {
        "global": dino_pool(tokens, None),
        "lesion": dino_pool(tokens, lesion),
        "wall": dino_pool(tokens, wall),
        "boundary": dino_pool(tokens, boundary),
    }
    vectors = [
        pooled["global"],
        pooled["lesion"],
        pooled["wall"],
        pooled["boundary"],
        pooled["wall"] - pooled["lesion"],
        pooled["boundary"] - pooled["lesion"],
    ]
    names = [
        "global",
        "lesion",
        "wall",
        "boundary",
        "wall_minus_lesion",
        "boundary_minus_lesion",
    ]
    feature_vector = np.concatenate(vectors).astype(np.float32)
    lesion_affinity = dino_cosine_map(tokens, pooled["lesion"]).reshape(grid_height, grid_width)
    wall_evidence = (
        dino_cosine_map(tokens, pooled["wall"])
        - dino_cosine_map(tokens, pooled["lesion"])
    ).reshape(grid_height, grid_width)
    payload = {
        "available": True,
        "model": model_id,
        "layer_index": int(layer_index),
        "input_size": DINO_IMAGE_SIZE,
        "token_grid": [grid_height, grid_width],
        "feature_dim": int(feature_vector.size),
        "feature_names": [f"{name}_{index}" for name in names for index in range(channels)],
        "feature_vector": np.round(feature_vector, 6).tolist(),
        "vector_stats": {
            "mean": float(feature_vector.mean()),
            "std": float(feature_vector.std()),
            "l2_norm": float(np.linalg.norm(feature_vector)),
        },
        "scalars": {
            "cos_wall_lesion": dino_cosine(pooled["wall"], pooled["lesion"]),
            "cos_boundary_lesion": dino_cosine(pooled["boundary"], pooled["lesion"]),
            "lesion_token_fraction": float(0.0 if lesion is None else lesion.mean()),
            "wall_token_fraction": float(0.0 if wall is None else wall.mean()),
            "boundary_token_fraction": float(0.0 if boundary is None else boundary.mean()),
        },
        "feature_overlay_png": dino_overlay_png(image_rgb, lesion_affinity, cv2.COLORMAP_MAGMA),
        "wall_evidence_overlay_png": dino_overlay_png(image_rgb, wall_evidence, cv2.COLORMAP_TURBO),
    }
    payload["roi_feature_overlay_png"] = crop_overlay_png(payload["feature_overlay_png"], roi_box)
    payload["roi_wall_evidence_overlay_png"] = crop_overlay_png(payload["wall_evidence_overlay_png"], roi_box)
    if roi_box is not None:
        payload["roi_box"] = {"x1": roi_box[0], "y1": roi_box[1], "x2": roi_box[2], "y2": roi_box[3]}
    return payload


def extract_dino_features(req: DinoFeaturesRequest) -> dict[str, Any]:
    image_rgb = decode_frame_b64(req.frame_png_b64)
    actual_height, actual_width = image_rgb.shape[:2]
    model, hub_model = get_dino_model()
    requested_layers = req.layer_indices or list(DINO_DEFAULT_LAYERS)
    requested_layers = sorted({
        int(layer)
        for layer in requested_layers
        if 0 <= int(layer) <= 11
    })
    if not requested_layers:
        requested_layers = [11]
    image_resized = cv2.resize(image_rgb, (DINO_IMAGE_SIZE, DINO_IMAGE_SIZE), interpolation=cv2.INTER_LINEAR)
    tensor = torch.from_numpy(
        ((image_resized.astype(np.float32) / 255.0 - DINO_MEAN) / DINO_STD)
    ).permute(2, 0, 1).unsqueeze(0).contiguous()
    device = next(model.parameters()).device
    with torch.no_grad():
        outputs = model.get_intermediate_layers(
            tensor.to(device=device, dtype=torch.float32),
            n=requested_layers,
            reshape=True,
            norm=True,
        )
    first_feature_map = outputs[0][0].detach().float().cpu().numpy()
    _, grid_height, grid_width = first_feature_map.shape
    roi_box = resolve_dino_roi_box(req, actual_width, actual_height)
    lesion = polygon_to_grid(req.lesion_polygon, actual_width, actual_height, grid_height, grid_width)
    wall = polygon_to_grid(req.wall_polygon, actual_width, actual_height, grid_height, grid_width)
    boundary = None
    if lesion is not None and lesion.any():
        dilated = cv2.dilate(lesion.astype(np.uint8), np.ones((3, 3), np.uint8))
        eroded = cv2.erode(lesion.astype(np.uint8), np.ones((3, 3), np.uint8))
        boundary = (dilated > eroded).astype(bool)
    layers = [
        build_dino_layer_result(
            image_rgb=image_rgb,
            feature_map=layer_output[0].detach().float().cpu().numpy(),
            layer_index=layer_index,
            model_id=hub_model,
            lesion=lesion,
            wall=wall,
            boundary=boundary,
            roi_box=roi_box,
        )
        for layer_index, layer_output in zip(requested_layers, outputs)
    ]
    primary = next(
        (layer for layer in layers if layer["layer_index"] == int(req.layer_index)),
        layers[-1],
    )
    return {
        **primary,
        "case_id": req.case_id,
        "frame_time": float(req.frame_time),
        "layer_indices": requested_layers,
        "roi_box": (
            {"x1": roi_box[0], "y1": roi_box[1], "x2": roi_box[2], "y2": roi_box[3]}
            if roi_box is not None
            else None
        ),
        "layers": layers,
    }

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


VIDEO_ALLOWED_ROOTS = (
    STATIC_ROOT.resolve(),
    (REPO_ROOT / "apps/gastric_scan_next/public/videos").resolve(),
    (REPO_ROOT / "dataset/internal/prospective_2025/2025/crop_ui/videos").resolve(),
    (REPO_ROOT / "dataset/external").resolve(),
    (REPO_ROOT / "data/raw/qualified_reader_videos").resolve(),
    (REPO_ROOT / "data/raw/patient_videos_2025").resolve(),
    (REPO_ROOT / "data/raw/legacy_external_direct_surgery").resolve(),
    (REPO_ROOT / "data/raw/legacy_gastric_staging").resolve(),
)


def _is_allowed_video_path(candidate: Path) -> bool:
    resolved = candidate.resolve()
    return any(
        resolved == root or str(resolved).startswith(f"{root}{os.sep}")
        for root in VIDEO_ALLOWED_ROOTS
    )


def resolve_video_reference(video_rel: str, video_url: str) -> Path | None:
    """Resolve reader-relative or Next stream URLs within audited video roots."""
    references: list[str] = []
    if video_rel.strip():
        references.append(video_rel.strip())
    if video_url.strip():
        parsed = urlparse(video_url.strip())
        references.extend(parse_qs(parsed.query).get("rel", []))
        if parsed.scheme in {"", "file"} and parsed.path:
            references.append(parsed.path)

    seen: set[str] = set()
    for reference in references:
        rel = reference.replace("\\", "/").lstrip("/")
        if not rel or ".." in Path(rel).parts or rel in seen:
            continue
        seen.add(rel)
        candidates = (
            STATIC_ROOT / rel,
            REPO_ROOT / rel,
        )
        for candidate in candidates:
            if candidate.is_file() and _is_allowed_video_path(candidate):
                return candidate.resolve()
    return None


def postprocess_mask(
    mask: np.ndarray,
    box: BoxPayload | None = None,
) -> np.ndarray:
    """Keep largest component, smooth boundary, and softly clip to the ROI box."""
    mask_u8 = (mask > 0).astype(np.uint8)
    if mask_u8.sum() == 0:
        return mask.astype(bool)

    if box is not None:
        x1 = int(np.clip(round(min(box.x1, box.x2)), 0, mask.shape[1] - 1))
        x2 = int(np.clip(round(max(box.x1, box.x2)), 0, mask.shape[1] - 1))
        y1 = int(np.clip(round(min(box.y1, box.y2)), 0, mask.shape[0] - 1))
        y2 = int(np.clip(round(max(box.y1, box.y2)), 0, mask.shape[0] - 1))
        try:
            padding_ratio = min(max(float(os.getenv("SAM_BOX_PADDING_RATIO", "0.08")), 0.0), 0.25)
        except ValueError:
            padding_ratio = 0.08
        pad_x = max(4, int(round((x2 - x1) * padding_ratio)))
        pad_y = max(4, int(round((y2 - y1) * padding_ratio)))
        x1 = max(0, x1 - pad_x)
        x2 = min(mask.shape[1] - 1, x2 + pad_x)
        y1 = max(0, y1 - pad_y)
        y2 = min(mask.shape[0] - 1, y2 + pad_y)
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


def largest_contour_polygon(mask: np.ndarray, max_points: int = 2048) -> list[list[float]]:
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
    """Build a non-pathology stage tendency without using the reference answer."""
    base = {s: 0.25 for s in STAGES}
    if thickness_mm >= 7.5:
        base["T1"] -= 0.10
        base["T2"] -= 0.08
        base["T3"] += 0.12
        base["T4+"] += 0.06
    elif thickness_mm <= 4.5:
        base["T1"] += 0.12
        base["T2"] += 0.05
        base["T3"] -= 0.08
        base["T4+"] -= 0.09
    # SAM confidence changes concentration, not the clinical stage prior.
    concentration = min(0.08, max(0.0, sam_score - 0.5) * 0.12)
    stage = max(base, key=base.get)
    base[stage] += concentration
    total = sum(max(0.01, value) for value in base.values())
    return {key: max(0.01, value) / total for key, value in base.items()}


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


def _sign_field(value: Any, status: str = "unevaluated", source: str = "not_available", evidence_ref: list[str] | None = None) -> dict[str, Any]:
    return {
        "value": value,
        "status": status,
        "source": source,
        "confidence": None,
        "raw_value": value,
        "evidence_ref": evidence_ref or [],
    }


GC_US_TEMPLATE_ID = "gc_us_t_report_template_v1"
GC_US_SCHEMA_VERSION = "gc_us_report_signs_v1"
GC_US_SOURCE_DOC = "GC_US_T报告模板_20260803.docx"


def _template_path_value(state: dict[str, Any] | None, *path: str, default: Any = None) -> Any:
    node: Any = state
    for key in path:
        if not isinstance(node, dict):
            return default
        node = node.get(key)
    if isinstance(node, dict) and "value" in node:
        node = node.get("value")
    return default if node is None or node == "" else node


def _template_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _template_number_text(value: float | None) -> str:
    if value is None:
        return "未评估"
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}".rstrip("0").rstrip(".")


def _template_stage(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw or "T4+" in raw.upper():
        return None
    stages = sorted(set(f"T{item}" for item in re.findall(r"T([1-4])", raw.upper())))
    return stages[0] if len(stages) == 1 else None


def _template_strip(value: Any, prefixes: tuple[str, ...]) -> str:
    text = str(value or "").strip()
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    return text or "未评估"


def _template_growth(value: Any) -> str:
    text = str(value or "").strip()
    for suffix in ("生长方式", "生长"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
            break
    return text or "未评估"


def _template_put_field(
    signs: dict[str, Any],
    key: str,
    value: Any,
    *,
    status: str = "suggested",
    source: str = "live_contour",
    evidence_ref: list[str] | None = None,
) -> None:
    current = signs.get(key)
    if isinstance(current, dict) and current.get("value") not in (None, ""):
        return
    if isinstance(current, dict):
        signs[key] = {
            **current,
            "value": value,
            "raw_value": value,
            "status": status,
            "source": source,
            "evidence_ref": current.get("evidence_ref") or evidence_ref or [],
        }
    else:
        signs[key] = _sign_field(value, status, source, evidence_ref)


def _estimate_lesion_length_mm(mask: np.ndarray) -> float | None:
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    extent_px = max(float(xs.max() - xs.min()), float(ys.max() - ys.min()))
    return round(extent_px / 40.0, 1) if extent_px > 1 else None


def _build_gc_us_template_report(
    *,
    case_id: str,
    frame_time: float,
    clicks: list[ClickPayload],
    box: BoxPayload | None,
    sam_score: float,
    thickness_mm: float,
    outer_risk: float,
    raw_stage: str,
    conflicts: list[dict[str, Any]],
    gc_us_report: dict[str, Any] | None,
    lesion_length_mm: float | None,
) -> dict[str, Any]:
    state = gc_us_report if isinstance(gc_us_report, dict) else None
    incoming_signs = state.get("signs") if isinstance(state, dict) else {}
    signs = dict(incoming_signs) if isinstance(incoming_signs, dict) else {}
    size = signs.get("size")
    size = dict(size) if isinstance(size, dict) else {}
    signs["size"] = size

    length_field = size.get("length") if isinstance(size.get("length"), dict) else {}
    thickness_field = size.get("thickness") if isinstance(size.get("thickness"), dict) else {}
    length = _template_number(length_field.get("value"))
    thickness = _template_number(thickness_field.get("value"))
    length_unit = length_field.get("unit")
    thickness_unit = thickness_field.get("unit")
    if lesion_length_mm is not None and (
        length is None
        or (length_unit == "px" and length_field.get("status") != "doctor_edited")
    ):
        length = lesion_length_mm
        length_unit = "mm"
        size["length"] = _sign_field(length, "suggested", "live_contour", ["mask.length_mm_proxy"])
        size["length"]["unit"] = "mm"
        size["length"]["note"] = "由当前帧轮廓几何辅助估测，不等同于病理测量"
    if thickness is None or (thickness_unit == "px" and thickness_field.get("status") != "doctor_edited"):
        thickness = thickness_mm
        thickness_unit = "mm"
        size["thickness"] = _sign_field(thickness, "suggested", "live_contour", ["mask.thickness_mm"])
        size["thickness"]["unit"] = "mm"
    if length is not None and thickness is not None and length_unit != "px" and thickness_unit != "px":
        size_phrase = (
            f"大小约{_template_number_text(length)}×{_template_number_text(thickness)} mm，"
            f"最大厚度{_template_number_text(thickness)} mm"
        )
    elif length is None and thickness is None:
        size_phrase = "大小及最大厚度未评估"
    else:
        length_text = f"{_template_number_text(length)}像素（非毫米）" if length_unit == "px" else f"{_template_number_text(length)} mm"
        thickness_text = f"{_template_number_text(thickness)}像素（非毫米）" if thickness_unit == "px" else f"{_template_number_text(thickness)} mm"
        size_phrase = f"大小约{length_text}×{thickness_text}，最大厚度{thickness_text}"

    _template_put_field(signs, "lesion_echo", "低回声", evidence_ref=["template.default_echo"])
    _template_put_field(signs, "layer_structure", "未评估", source="not_available", evidence_ref=["layer.multiplanar_review_required"])
    _template_put_field(signs, "morphology", "未评估", source="not_available", evidence_ref=["morphology.not_available"])
    _template_put_field(signs, "boundary", "未评估", source="not_available", evidence_ref=["boundary.not_available"])
    _template_put_field(signs, "growth_pattern", "未评估", source="not_available", evidence_ref=["growth.not_available"])
    _template_put_field(signs, "serosa_change", "未评估", source="not_available", evidence_ref=["serosa.multiplanar_review_required"])
    _template_put_field(signs, "perigastric_tissue", "未评估", source="not_available", evidence_ref=["perigastric.multiplanar_review_required"])

    morphology = str(_template_path_value({"signs": signs}, "signs", "morphology", default="未评估"))
    echo = str(_template_path_value({"signs": signs}, "signs", "lesion_echo", default="低回声"))
    boundary = str(_template_path_value({"signs": signs}, "signs", "boundary", default="未评估"))
    growth = str(_template_path_value({"signs": signs}, "signs", "growth_pattern", default="未评估"))
    layer = str(_template_path_value({"signs": signs}, "signs", "layer_structure", default="未评估"))
    serosa = str(_template_path_value({"signs": signs}, "signs", "serosa_change", default="未评估"))
    perigastric = str(_template_path_value({"signs": signs}, "signs", "perigastric_tissue", default="未评估"))
    lesion_noun = f"{morphology}{echo}占位性病变" if morphology != "未评估" else f"{echo}占位性病变"
    location = "胃壁"
    clinical = state.get("clinical") if isinstance(state, dict) else {}
    if isinstance(clinical, dict):
        location = str(clinical.get("location") or clinical.get("site") or location).strip()
    finding = (
        f"{location}见{lesion_noun}，{size_phrase}。"
        f"病灶呈{_template_growth(growth)}生长方式，边界{_template_strip(boundary, ('边界',))}。"
        f"胃壁层次表现为{_template_strip(layer, ('胃壁层次', '层次结构'))}，"
        f"浆膜表现{_template_strip(serosa, ('浆膜面', '浆膜'))}，"
        f"胃周组织{_template_strip(perigastric, ('胃周组织', '胃周'))}。"
    )

    reference = state.get("reference_stage") if isinstance(state, dict) else {}
    reference = reference if isinstance(reference, dict) else {}
    requested = _template_stage(reference.get("band"))
    if requested is None and not conflicts:
        requested = _template_stage(reference.get("requested_band"))
    if requested is None and not conflicts:
        requested = _template_stage(raw_stage)
    final_stage = requested if requested and not conflicts else None
    conflict_messages = [str(item.get("message")) for item in conflicts if item.get("message")]
    stage_line = (
        f"胃癌可能，超声评估c{final_stage}期。"
        if final_stage
        else "胃癌可能，超声评估cTx期，浸润深度倾向尚不确定。"
    )
    prose_lines = [
        "【超声所见】",
        finding,
        "",
        "【超声印象】",
        "综合超声影像征象及AI辅助分析，考虑：",
        stage_line,
    ]
    if conflict_messages:
        prose_lines.append("当前存在需要医生复核的征象冲突：" + "；".join(conflict_messages))
    prose_lines.extend([
        "",
        "【建议】",
        "1. 建议针对冲突征象进行多切面核对，必要时补扫病灶外缘及浆膜区。"
        if conflict_messages
        else "1. 建议结合胃镜活检明确病理性质。",
        "备注：几何与规则辅助，非病理金标准；最终判断权在医生。",
    ])
    prose = "\n".join(prose_lines)
    state_report = state.get("report") if isinstance(state, dict) else {}
    state_report = state_report if isinstance(state_report, dict) else {}
    reference_stage = {
        "band": final_stage or "uncertain",
        "requested_band": requested or _template_stage(raw_stage) or "uncertain",
        "raw": reference.get("raw") or raw_stage,
        "source": reference.get("source") or "product_score",
        "conflicts": conflicts,
    }
    structured = {
        "schema_version": GC_US_SCHEMA_VERSION,
        "template_id": GC_US_TEMPLATE_ID,
        "source_doc": GC_US_SOURCE_DOC,
        "case_id": case_id or None,
        "frame_id": f"{case_id}:{frame_time:.3f}",
        "frame_time": frame_time,
        "clinical": clinical if isinstance(clinical, dict) else {},
        "signs": signs,
        "reference_stage": reference_stage,
        "report": {"prose": prose, "source": "template", "doctor_edited": bool(state_report.get("doctor_edited"))},
        "conflicts": conflicts,
    }
    return {
        "template_id": GC_US_TEMPLATE_ID,
        "schema_version": GC_US_SCHEMA_VERSION,
        "source_doc": GC_US_SOURCE_DOC,
        "template_prose": prose,
        "structured": structured,
        "stage": final_stage or "uncertain",
        "signs": signs,
        "reference_stage": reference_stage,
    }


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
    gc_us_report: dict[str, Any] | None = None,
    lesion_length_mm: float | None = None,
) -> dict[str, Any]:
    # reference_pt is intentionally ignored: pathology/reference labels must
    # never influence an AI suggestion shown during the reader study.
    dist = build_stage_distribution(None, thickness_mm, sam_score)
    raw_stage = max(dist.items(), key=lambda kv: kv[1])[0]
    conflicts: list[dict[str, Any]] = []
    if thickness_mm >= 7.5 and raw_stage in {"T1", "T2"}:
        conflicts.append({
            "code": "thickness_vs_low_stage",
            "severity": "high",
            "fields": ["size.thickness", "reference_stage"],
            "message": f"最大厚度约 {thickness_mm:.1f} mm，但当前低分期倾向为 {raw_stage}，不能直接采纳低分期建议。",
        })
    if outer_risk >= 0.75 and raw_stage in {"T1", "T2"}:
        conflicts.append({
            "code": "outer_risk_vs_low_stage",
            "severity": "high",
            "fields": ["serosa_change", "reference_stage"],
            "message": f"外缘风险约 {outer_risk:.0%}，与 {raw_stage} 低分期建议冲突，需多切面复核浆膜及胃周组织。",
        })
    if isinstance(gc_us_report, dict):
        state_reference = gc_us_report.get("reference_stage")
        state_conflicts = gc_us_report.get("conflicts")
        if not isinstance(state_conflicts, list) and isinstance(state_reference, dict):
            state_conflicts = state_reference.get("conflicts")
        for item in state_conflicts or []:
            if not isinstance(item, dict):
                continue
            code = item.get("code")
            if code and any(existing.get("code") == code for existing in conflicts):
                continue
            conflicts.append(item)
    template = _build_gc_us_template_report(
        case_id=case_id,
        frame_time=frame_time,
        clicks=clicks,
        box=box,
        sam_score=sam_score,
        thickness_mm=thickness_mm,
        outer_risk=outer_risk,
        raw_stage=raw_stage,
        conflicts=conflicts,
        gc_us_report=gc_us_report,
        lesion_length_mm=lesion_length_mm,
    )
    recommendation_status = "conflict" if conflicts else "suggested"
    recommended_stage = template["stage"]
    confidence = min(0.9, max(0.45, dist[raw_stage] + sam_score * 0.08))
    if conflicts:
        confidence = min(confidence, 0.55)
    summary = template["template_prose"]
    signs = template["signs"]
    return {
        "recommended_stage": recommended_stage,
        "stage_distribution": dist,
        "calibrated_confidence": confidence,
        "recommendation_status": recommendation_status,
        "review_flag": bool(conflicts) or confidence < 0.68,
        "conflicts": conflicts,
        "reference_stage": template["reference_stage"],
        "signs": signs,
        "template_id": template["template_id"],
        "schema_version": template["schema_version"],
        "source_doc": template["source_doc"],
        "template_prose": template["template_prose"],
        "structured": template["structured"],
        "sam_score": sam_score,
        "summary": summary,
        "evidence": [
            {"title": "交互分割", "detail": f"{prompt_summary(clicks, box)} · score {sam_score:.2f}", "status": "suggested", "source": "live_contour"},
            {"title": "肿瘤厚度", "detail": f"最大厚度约 {thickness_mm:.1f} mm；该值为辅助估测，需医生复核。", "status": "suggested", "source": "live_contour"},
            {"title": "胃壁层次结构", "detail": "当前帧未完成多切面层次评估，不能据此断言肌层或浆膜中断。", "status": "unevaluated", "source": "not_available"},
            {"title": "浆膜/外缘风险", "detail": f"外缘风险约 {outer_risk:.0%}；不能单独作为浆膜突破确诊。", "status": "conflict" if outer_risk >= 0.75 else "suggested", "source": "pixel_proxy"},
            {"title": "边界与生长方式", "detail": "当前帧未完成结构化征象确认。", "status": "unevaluated", "source": "not_available"},
            {"title": "胃周组织", "detail": "当前帧未评估胃周脂肪间隙。", "status": "unevaluated", "source": "not_available"},
            {"title": "阶段建议", "detail": "不确定/需复核" if conflicts else f"倾向 {raw_stage}，仅作参考", "status": recommendation_status, "source": "rule_assist"},
        ],
        "similar_cases": [],
        "toolchain": [{"id": "sam2_finetuned", "title": "胃超声微调分割", "detail": "仅提供当前帧 mask，不替代医生连续视频判断。", "status": "ok"}],
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
    if report.get("template_prose"):
        prompt += f"\n【七项征象标准化草稿】\n{report['template_prose']}\n"
    prompt += (
        "请用简体中文撰写超声 T 分期阅片报告，面向临床医生：\n"
        "1) 严格保留七项征象事实和医生修正值；\n"
        "2) 使用【超声所见】【超声印象】【建议】标题，并保留“综合超声影像征象及AI辅助分析，考虑：”与胃癌可能、cT评估句；\n"
        "3) 证据不足或冲突时输出 cTx，不得把 T4+ 或混合分期强行改成单一分期。\n"
        "要求：仅输出简体中文正文，不要新增测量、部位或确定性外侵结论。"
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
        report["summary"] = report.get("template_prose") or llm["narrative"]
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
        "dino": dino_assets_status(),
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
    lesion_length_mm = _estimate_lesion_length_mm(mask)
    report = build_report(
        req.case_id,
        req.frame_time,
        clicks,
        box,
        sam_score,
        thickness_mm,
        normal_wall_mm,
        outer_risk,
        None,
        gc_us_report=req.gc_us_report,
        lesion_length_mm=lesion_length_mm,
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
        "mask_overlay_png": mask_to_overlay_png(mask) if req.include_overlay else None,
        "report": report,
    }


@app.get("/api/sam/video-status")
def sam_video_status() -> dict[str, Any]:
    return get_video_tracker().status()


@app.get("/api/sam/dino-status")
def sam_dino_status() -> dict[str, Any]:
    return dino_assets_status()


@app.post("/api/sam/dino-features")
def sam_dino_features(req: DinoFeaturesRequest) -> dict[str, Any]:
    started = time.time()
    try:
        result = extract_dino_features(req)
        result["elapsed_ms"] = int((time.time() - started) * 1000)
        return {"ok": True, "result": result}
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "available": False,
            "error": f"DINO feature extraction failed: {exc}",
            "elapsed_ms": int((time.time() - started) * 1000),
        }


@app.post("/api/sam/video-propagate")
def sam_video_propagate(req: VideoPropagateRequest) -> dict[str, Any]:
    video_path = resolve_video_reference(req.video_rel, req.video_url)
    if video_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"Video not found or not allowlisted: {req.video_rel or req.video_url}",
        )
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


if SERVE_LEGACY_HTML:
    app.mount("/", StaticFiles(directory=str(STATIC_ROOT), html=True), name="static")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        default=os.getenv("SAM_HOST", "127.0.0.1"),
        help="Bind address, defaulting to SAM_HOST or 127.0.0.1",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("SAM_PORT", "8767")),
        help="Inference service port, defaulting to SAM_PORT or 8767",
    )
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
    print(f"Serving SAM2 API at http://{args.host}:{args.port}/api/sam/status")
    if SERVE_LEGACY_HTML:
        print(f"Legacy HTML frontend enabled from {STATIC_ROOT}")
    else:
        print("Legacy HTML frontend disabled; use the Next workbench")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
