from __future__ import annotations

import contextlib
import os
import threading
import time
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np
import torch


class Sam2VideoTracker:
    """SAM 2.1 video-memory propagation with conservative drift gates.

    The interactive image predictor remains the fast click/box path. This class
    is deliberately a separate, serialized predictor so a full-video request
    can use SAM 2.1's native memory bank without corrupting the image session.
    """

    def __init__(self) -> None:
        self.config = os.getenv("SAM2_VIDEO_CONFIG", "configs/sam2.1/sam2.1_hiera_t.yaml")
        project_root = Path(os.getenv("GASTRIC_ROOT", str(Path.cwd())))
        explicit_checkpoint = os.getenv("SAM2_VIDEO_CHECKPOINT", "").strip()
        temporal_candidate = (
            project_root
            / "experiments/prompt_mask_agent/r003_temporal_adapter/full_proxy"
            / "best_sam2_temporal_adapter.pt"
        )
        fallback_checkpoint = os.getenv(
            "SAM2_CHECKPOINT",
            "experiments/segmentation/model_compare_20260802/"
            "sabm_gus_sam2_finetune_r001/best_sabm_gus_sam2.pt",
        )
        checkpoint_raw = explicit_checkpoint or (
            str(temporal_candidate)
            if temporal_candidate.is_file()
            else fallback_checkpoint
        )
        checkpoint = Path(checkpoint_raw)
        if not checkpoint.is_absolute():
            checkpoint = project_root / checkpoint
        self.checkpoint = checkpoint.resolve()
        self.model_id = f"{self.config} + {self.checkpoint.parent.name}"
        self.max_frames_default = int(os.getenv("SAM2_VIDEO_MAX_FRAMES", "1200"))
        self._predictor: Any | None = None
        self._predictor_lock = threading.Lock()
        self._inference_lock = threading.Lock()
        self._loaded_at: float | None = None

    def _get_predictor(self) -> Any:
        with self._predictor_lock:
            if self._predictor is None:
                from sam2.build_sam import build_sam2_video_predictor

                if not self.checkpoint.is_file():
                    raise FileNotFoundError(f"SAM2 video checkpoint does not exist: {self.checkpoint}")
                device = "cuda" if torch.cuda.is_available() else "cpu"
                predictor = build_sam2_video_predictor(
                    self.config,
                    ckpt_path=None,
                    device=device,
                )
                checkpoint = torch.load(self.checkpoint, map_location="cpu", weights_only=False)
                raw = checkpoint.get("model_state_dict", checkpoint)
                if any(key.startswith("feature_adapter.") for key in raw):
                    raise RuntimeError(
                        "Static context-edge adapter checkpoint cannot be loaded by "
                        "SAM2VideoPredictor. Use a decoder-only/video-compatible "
                        "checkpoint until temporal adapter support is implemented."
                    )
                state = {
                    key.replace("sam2_model.", "", 1): value
                    for key, value in raw.items()
                    if key.startswith("sam2_model.")
                }
                if not state:
                    raise RuntimeError(f"No sam2_model.* weights in checkpoint: {self.checkpoint}")
                missing, unexpected = predictor.load_state_dict(state, strict=False)
                if missing or unexpected:
                    raise RuntimeError(
                        f"Fine-tuned SAM2 video weights mismatch: missing={len(missing)} unexpected={len(unexpected)}"
                    )
                self._predictor = predictor.eval()
                self._loaded_at = time.time()
            return self._predictor

    def warm(self) -> None:
        self._get_predictor()

    def status(self) -> dict[str, Any]:
        return {
            "model": self.model_id,
            "checkpoint": str(self.checkpoint),
            "fine_tuned": True,
            "loaded": self._predictor is not None,
            "loaded_at": self._loaded_at,
            "cuda": bool(torch.cuda.is_available()),
            "mode": "sam2_native_video_memory",
            "max_frames": self.max_frames_default,
            "quality_gate": {
                "min_area_ratio": 0.0002,
                "max_area_ratio": 0.72,
                "max_area_change": 3.0,
                "max_centroid_shift": 0.35,
            },
        }

    @staticmethod
    def _mask_array(mask_logits: Any, height: int, width: int) -> np.ndarray:
        if isinstance(mask_logits, torch.Tensor):
            arr = mask_logits.detach().float().cpu().numpy()
        else:
            arr = np.asarray(mask_logits)
        while arr.ndim > 2:
            arr = arr[0]
        if arr.shape != (height, width):
            arr = cv2.resize(arr, (width, height), interpolation=cv2.INTER_LINEAR)
        return arr > 0.0

    @staticmethod
    def _polygon(mask: np.ndarray) -> list[list[float]]:
        mask_u8 = (mask.astype(np.uint8) * 255)
        contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return []
        contour = max(contours, key=cv2.contourArea)
        perimeter = max(float(cv2.arcLength(contour, True)), 1.0)
        approx = cv2.approxPolyDP(contour, max(0.8, perimeter * 0.002), True)
        points = approx.reshape(-1, 2).tolist()
        if len(points) > 256:
            step = max(1, len(points) // 256)
            points = points[::step][:256]
        return [[float(x), float(y)] for x, y in points]

    @staticmethod
    def _stats(mask: np.ndarray, previous: dict[str, Any] | None) -> dict[str, Any]:
        height, width = mask.shape[:2]
        total = max(1, height * width)
        area = int(mask.sum())
        area_ratio = area / total
        ys, xs = np.where(mask)
        if len(xs):
            cx = float(xs.mean())
            cy = float(ys.mean())
            x1, x2 = int(xs.min()), int(xs.max())
            y1, y2 = int(ys.min()), int(ys.max())
        else:
            cx = cy = 0.0
            x1 = y1 = x2 = y2 = 0

        quality_score = 1.0
        reasons: list[str] = []
        if area_ratio < 0.0002:
            reasons.append("area_too_small")
            quality_score *= 0.2
        if area_ratio > 0.72:
            reasons.append("area_too_large")
            quality_score *= 0.2

        area_change = 1.0
        centroid_shift = 0.0
        iou = 1.0
        if previous is not None:
            previous_mask = previous.get("mask")
            if isinstance(previous_mask, np.ndarray) and previous_mask.shape == mask.shape:
                intersection = np.logical_and(mask, previous_mask).sum()
                union = np.logical_or(mask, previous_mask).sum()
                iou = float(intersection / union) if union else 0.0
            previous_area = max(1, int(previous.get("area", 0)))
            area_change = max(area / previous_area, previous_area / max(1, area))
            if area_change > 3.0:
                reasons.append("area_jump")
                quality_score *= max(0.0, 1.0 - min(1.0, (area_change - 3.0) / 3.0))
            diagonal = max(1.0, float((width**2 + height**2) ** 0.5))
            centroid_shift = float(
                ((cx - float(previous.get("cx", cx))) ** 2 + (cy - float(previous.get("cy", cy))) ** 2) ** 0.5
                / diagonal
            )
            if centroid_shift > 0.35:
                reasons.append("centroid_jump")
                quality_score *= max(0.0, 1.0 - min(1.0, (centroid_shift - 0.35) / 0.35))
            if iou < 0.02 and centroid_shift > 0.12:
                reasons.append("mask_discontinuity")
                quality_score *= 0.35

        accepted = not reasons
        return {
            "accepted": accepted,
            "quality_score": round(float(max(0.0, min(1.0, quality_score))), 4),
            "reason": ";".join(reasons) if reasons else "ok",
            "area": area,
            "area_ratio": round(float(area_ratio), 6),
            "area_change": round(float(area_change), 4),
            "centroid": [round(cx, 2), round(cy, 2)],
            "centroid_shift": round(float(centroid_shift), 6),
            "bbox": [x1, y1, x2, y2],
            "mask_iou": round(float(iou), 4),
        }

    @staticmethod
    def _prompt_arrays(
        clicks: Iterable[dict[str, Any]],
        box: dict[str, Any] | None,
        scale_x: float,
        scale_y: float,
    ) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None]:
        points = []
        labels = []
        for click in clicks:
            points.append([float(click.get("x", 0.0)) * scale_x, float(click.get("y", 0.0)) * scale_y])
            labels.append(0 if click.get("label") == "negative" else 1)
        point_array = np.asarray(points, dtype=np.float32) if points else None
        label_array = np.asarray(labels, dtype=np.int32) if labels else None
        box_array = None
        if box:
            box_array = np.asarray(
                [
                    float(box.get("x1", 0.0)) * scale_x,
                    float(box.get("y1", 0.0)) * scale_y,
                    float(box.get("x2", 0.0)) * scale_x,
                    float(box.get("y2", 0.0)) * scale_y,
                ],
                dtype=np.float32,
            )
        return point_array, label_array, box_array

    def _collect_direction(
        self,
        predictor: Any,
        state: dict[str, Any],
        seed_frame_idx: int,
        reverse: bool,
        max_frames: int,
        fps: float,
        output: dict[int, dict[str, Any]],
    ) -> dict[str, Any]:
        previous: dict[str, Any] | None = None
        processed = 0
        stopped_at: int | None = None
        stop_reason = "completed"
        with torch.autocast(
            device_type="cuda",
            dtype=torch.bfloat16,
            enabled=torch.cuda.is_available(),
        ):
            iterator = predictor.propagate_in_video(
                state,
                start_frame_idx=seed_frame_idx,
                max_frame_num_to_track=max_frames,
                reverse=reverse,
            )
            for frame_idx, _obj_ids, mask_logits in iterator:
                mask = self._mask_array(mask_logits, int(state["video_height"]), int(state["video_width"]))
                quality = self._stats(mask, previous)
                processed += 1
                if not quality["accepted"] and frame_idx != seed_frame_idx:
                    stopped_at = int(frame_idx)
                    stop_reason = quality["reason"]
                    break
                previous = {
                    "mask": mask,
                    "area": quality["area"],
                    "cx": quality["centroid"][0],
                    "cy": quality["centroid"][1],
                }
                item = {
                    "frame_index": int(frame_idx),
                    "frame_time": round(float(frame_idx) / max(fps, 1e-6), 4),
                    "direction": "backward" if reverse else "forward",
                    "mask_polygon": self._polygon(mask),
                    **quality,
                }
                existing = output.get(int(frame_idx))
                if existing is None or item["quality_score"] > existing.get("quality_score", 0.0):
                    output[int(frame_idx)] = item
        return {
            "direction": "backward" if reverse else "forward",
            "processed_frames": processed,
            "stopped_at": stopped_at,
            "stop_reason": stop_reason,
        }

    def propagate(
        self,
        video_path: Path,
        frame_time: float,
        image_width: int,
        image_height: int,
        clicks: list[dict[str, Any]],
        box: dict[str, Any] | None,
        direction: str = "both",
        max_frames: int = 0,
    ) -> dict[str, Any]:
        started = time.time()
        if not video_path.is_file():
            raise FileNotFoundError(f"Video not found: {video_path}")
        cap = cv2.VideoCapture(str(video_path))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()
        if frame_count <= 0:
            raise RuntimeError("Could not read video frame count")
        predictor = self._get_predictor()
        limit = max_frames if max_frames > 0 else self.max_frames_default
        limit = min(max(1, limit), frame_count)
        requested_frame = max(0, min(frame_count - 1, int(round(frame_time * fps))))
        results: dict[int, dict[str, Any]] = {}
        direction_reports: list[dict[str, Any]] = []

        with self._inference_lock:
            with torch.autocast(
                device_type="cuda",
                dtype=torch.bfloat16,
                enabled=torch.cuda.is_available(),
            ):
                state = predictor.init_state(
                    str(video_path),
                    offload_video_to_cpu=True,
                    offload_state_to_cpu=True,
                )
                actual_width = int(state["video_width"])
                actual_height = int(state["video_height"])
                point_array, label_array, box_array = self._prompt_arrays(
                    clicks,
                    box,
                    actual_width / max(1, image_width),
                    actual_height / max(1, image_height),
                )
                if point_array is None and box_array is None:
                    point_array = np.asarray([[actual_width / 2.0, actual_height / 2.0]], dtype=np.float32)
                    label_array = np.asarray([1], dtype=np.int32)
                _, _, seed_logits = predictor.add_new_points_or_box(
                    state,
                    frame_idx=requested_frame,
                    obj_id=1,
                    points=point_array,
                    labels=label_array,
                    box=box_array,
                )
                seed_mask = self._mask_array(seed_logits, actual_height, actual_width)
                seed_quality = self._stats(seed_mask, None)
                results[requested_frame] = {
                    "frame_index": requested_frame,
                    "frame_time": round(requested_frame / max(fps, 1e-6), 4),
                    "direction": "seed",
                    "mask_polygon": self._polygon(seed_mask),
                    **seed_quality,
                }
                if direction in ("both", "forward"):
                    direction_reports.append(self._collect_direction(predictor, state, requested_frame, False, limit, fps, results))
                if direction in ("both", "backward"):
                    direction_reports.append(self._collect_direction(predictor, state, requested_frame, True, limit, fps, results))

        frames = [results[index] for index in sorted(results)]
        stopped = [report for report in direction_reports if report.get("stopped_at") is not None]
        return {
            "model": self.model_id,
            "video": str(video_path),
            "fps": round(fps, 4),
            "num_frames": frame_count,
            "seed_frame_index": requested_frame,
            "seed_frame_time": round(requested_frame / max(fps, 1e-6), 4),
            "direction_reports": direction_reports,
            "status": "needs_reanchor" if stopped else "completed",
            "needs_reanchor": bool(stopped),
            "accepted_frames": len(frames),
            "frames": frames,
            "elapsed_ms": int((time.time() - started) * 1000),
        }
