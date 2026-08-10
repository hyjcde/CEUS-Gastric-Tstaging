"""Auditable pipeline step agents and cross-modal decision support."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from ..tools.base import ToolRegistry
from ..tools.lumen_detection_tool import (
    lumen_bbox_from_mask,
    lumen_geometry_from_bbox,
    lumen_mask_from_polygon,
)
from ..tools.segmentation_tool import SegmentationTool
from ..pipeline.base_step import BasePipelineStep, StepResult
from ..pipeline.case_input import InputMode
from ..pipeline.options import PipelineOptions
from ..pipeline.state import CasePipelineState

logger = logging.getLogger(__name__)


def _norm_clinical(clinical: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(clinical or {})

    def enc_sex(v):
        if v in (None, ""):
            return 0
        if isinstance(v, (int, float)):
            return 1 if int(v) == 1 else 0
        s = str(v).strip().lower()
        if s in ("男", "m", "male", "1"):
            return 1
        return 0

    def enc_loc(v):
        if v is None:
            return 2
        if isinstance(v, (int, float)):
            return int(v) if int(v) in (0, 1, 2, 3) else 2
        s = str(v)
        if "贲门" in s:
            return 0
        if "底" in s:
            return 1
        if "体" in s:
            return 2
        if "窦" in s or "幽门" in s:
            return 3
        return 2

    def enc_diff(v):
        if v is None:
            return 2
        if isinstance(v, (int, float)):
            return int(v) if int(v) in (1, 2, 3, 4) else 2
        s = str(v)
        if "高分化" in s:
            return 1
        if "中分化" in s:
            return 2
        if "低分化" in s:
            return 3
        if "未分化" in s:
            return 4
        return 2

    out["sex"] = enc_sex(out.get("sex"))
    out["tumor_location"] = enc_loc(out.get("tumor_location") or out.get("location"))
    out["differentiation"] = enc_diff(out.get("differentiation"))
    age_raw = out.get("age")
    if age_raw not in (None, ""):
        try:
            out["age"] = float(age_raw)
        except (TypeError, ValueError):
            out["age"] = 0.0
    for key in ("tumor_length_cm", "tumor_thickness_cm", "cea_value", "CEA_value", "ca199_value", "CA199_value"):
        raw = out.get(key)
        if raw in (None, ""):
            continue
        try:
            out[key] = float(raw)
        except (TypeError, ValueError):
            out[key] = 0.0
    return out


def _clinical_features_for_classifier(clinical: Dict[str, Any]) -> Dict[str, Any]:
    c = _norm_clinical(clinical)
    return {
        "age": c.get("age"),
        "sex": c.get("sex"),
        "tumor_location": c.get("tumor_location"),
        "tumor_length_cm": c.get("tumor_length_cm"),
        "tumor_thickness_cm": c.get("tumor_thickness_cm"),
        "differentiation": c.get("differentiation"),
        "CEA_value": c.get("cea_value") or c.get("CEA_value"),
        "CA199_value": c.get("ca199_value") or c.get("CA199_value"),
    }


def _should_skip_vision(state: CasePipelineState) -> bool:
    return state.gate_decision == "skip_t"


_STAGE_NAMES = ("T1", "T2", "T3", "T4+")


def _frame_quality_weight(frame) -> float:
    score = frame.quality_score
    if score is None:
        return 1.0
    return max(0.05, min(float(score), 1.0))


def _frame_metadata(frame) -> Dict[str, Any]:
    return {
        "frame_id": frame.frame_id,
        "frame_index": frame.frame_index,
        "timestamp_sec": frame.timestamp_sec,
        "quality_score": frame.quality_score,
        "image_path": frame.image_path,
    }


def _representative_frame_result(rows: List[Dict[str, Any]], state: CasePipelineState) -> Dict[str, Any]:
    if not rows:
        return {}
    primary_path = state.case_input.primary_frame.image_path
    for row in rows:
        if row.get("image_path") == primary_path:
            return row
    return max(rows, key=lambda row: float(row.get("quality_score") or 0.0))


def _aggregate_binary_frames(
    rows: List[Dict[str, Any]],
    frames,
    threshold: float,
) -> Dict[str, Any]:
    available = [row for row in rows if row.get("available")]
    if not available:
        return rows[0] if rows else {"available": False, "gate_decision": "run_t"}
    frame_by_path = {frame.image_path: frame for frame in frames}
    weighted = [
        (row, _frame_quality_weight(frame_by_path[row.get("image_path")]))
        for row in available
        if row.get("image_path") in frame_by_path
    ]
    if not weighted:
        weighted = [(row, 1.0) for row in available]
    total = sum(weight for _, weight in weighted) or 1.0
    probs = {
        label: round(
            sum(float((row.get("probabilities") or {}).get(label, 0.0)) * weight for row, weight in weighted)
            / total,
            4,
        )
        for label in ("benign", "malignant")
    }
    ordered = sorted(probs.items(), key=lambda pair: pair[1], reverse=True)
    representative = max(weighted, key=lambda pair: pair[1])[0]
    all_skip = all(row.get("gate_decision") == "skip_t" for row, _ in weighted)
    top_label, top_prob = ordered[0]
    gate = "skip_t" if all_skip and top_label == "benign" and top_prob >= threshold else "run_t"
    merged = dict(representative)
    merged.update(
        {
            "probabilities": probs,
            "top1_label": top_label,
            "top1_prob": top_prob,
            "top2_label": ordered[1][0] if len(ordered) > 1 else top_label,
            "top2_prob": ordered[1][1] if len(ordered) > 1 else 0.0,
            "gate_decision": gate,
            "frame_aggregation": "quality_weighted_mean",
            "aggregated_frame_count": len(weighted),
            "frame_weights": [
                {"frame_index": row.get("frame_index"), "weight": round(weight / total, 4)}
                for row, weight in weighted
            ],
        }
    )
    return merged


def _aggregate_tstage_frames(rows: List[Dict[str, Any]], frames) -> Dict[str, Any]:
    available = [row for row in rows if row.get("available") and row.get("probabilities")]
    if not available:
        return rows[0] if rows else {"available": False, "error": "No frame classifications"}
    frame_by_path = {frame.image_path: frame for frame in frames}
    weighted = [
        (row, _frame_quality_weight(frame_by_path[row.get("image_path")]))
        for row in available
        if row.get("image_path") in frame_by_path
    ]
    if not weighted:
        weighted = [(row, 1.0) for row in available]
    total = sum(weight for _, weight in weighted) or 1.0
    probs = {
        stage: round(
            sum(float((row.get("probabilities") or {}).get(stage, 0.0)) * weight for row, weight in weighted)
            / total,
            4,
        )
        for stage in _STAGE_NAMES
    }
    ordered = sorted(probs.items(), key=lambda pair: pair[1], reverse=True)
    representative = max(weighted, key=lambda pair: pair[1])[0]
    top1_stage, top1_prob = ordered[0]
    top2_stage, top2_prob = ordered[1] if len(ordered) > 1 else (top1_stage, 0.0)
    merged = dict(representative)
    merged.update(
        {
            "probabilities": probs,
            "top1_stage": top1_stage,
            "top1_prob": top1_prob,
            "top2_stage": top2_stage,
            "top2_prob": top2_prob,
            "uncertainty": round(1.0 - max(top1_prob - top2_prob, 0.0), 4),
            "frame_aggregation": "quality_weighted_mean",
            "aggregated_frame_count": len(weighted),
            "frame_weights": [
                {"frame_index": row.get("frame_index"), "weight": round(weight / total, 4)}
                for row, weight in weighted
            ],
        }
    )
    return merged


def _get_seg_tool(registry: ToolRegistry) -> SegmentationTool:
    tool = registry.get("segment")
    if not isinstance(tool, SegmentationTool):
        raise TypeError("segment tool is not SegmentationTool")
    return tool


def _resolve_mask_override(image_path: str, options) -> Optional[np.ndarray]:
    """Rasterize Workbench polygon / load mask_path when use_mask_override is set."""
    if not getattr(options, "use_mask_override", False):
        return None

    mask_path = getattr(options, "mask_path", None)
    if mask_path:
        from pathlib import Path

        p = Path(str(mask_path))
        if p.is_file():
            mask = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
            if mask is not None:
                return (mask > 127).astype(np.uint8) * 255

    polygon = getattr(options, "mask_polygon", None)
    if not isinstance(polygon, list) or len(polygon) < 3:
        return None

    image = cv2.imread(str(image_path))
    if image is None:
        return None
    height, width = image.shape[:2]
    pts = []
    for pt in polygon:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            continue
        try:
            pts.append([float(pt[0]), float(pt[1])])
        except (TypeError, ValueError):
            continue
    if len(pts) < 3:
        return None
    arr = np.array(pts, dtype=np.int32)
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [arr], 255)
    if not np.any(mask):
        return None
    return mask


class TriageAgent(BasePipelineStep):
    step_number = 1
    step_id = "triage"
    agent_name = "TriageAgent"
    tool_name = None

    def run(self, state, registry, options):
        ci = state.case_input
        obs = {
            "case_id": ci.case_id,
            "patient_id": ci.patient_id,
            "input_mode": ci.input_mode.value,
            "frame_count": len(ci.frames),
            "gt_t_stage": ci.gt_t_stage,
            "data_source": ci.data_source,
            "clinical_keys": sorted(ci.clinical.keys()),
            "video_path": ci.video_path,
        }
        expl = (
            f"病例 {ci.case_id}（{ci.patient_id}）接入，"
            f"输入模式={ci.input_mode.value}，共 {len(ci.frames)} 帧。"
        )
        return StepResult(observation=obs, explanation=expl, inputs={"case_id": ci.case_id})


class FrameExtractAgent(BasePipelineStep):
    step_number = 2
    step_id = "frame_extract"
    agent_name = "FrameExtractAgent"
    tool_name = None

    def run(self, state, registry, options):
        frames = [
            {
                "frame_id": f.frame_id,
                "frame_index": f.frame_index,
                "timestamp_sec": f.timestamp_sec,
                "quality_score": f.quality_score,
                "image_path": f.image_path,
                "roi_path": f.roi_path,
            }
            for f in state.case_input.frames
        ]
        obs = {
            "available": True,
            "frame_count": len(frames),
            "frames": frames,
            "source": state.case_input.input_mode.value,
        }
        if state.case_input.input_mode == InputMode.VIDEO:
            obs["clip_name"] = state.case_input.clip_name
            obs["video_path"] = state.case_input.video_path
            expl = f"从视频 {state.case_input.clip_name} 抽取 {len(frames)} 个关键帧。"
        else:
            expl = f"加载静态帧 {len(frames)} 张（cases.json / frontend payload）。"
        return StepResult(observation=obs, explanation=expl)


class QualityAgent(BasePipelineStep):
    step_number = 3
    step_id = "quality"
    agent_name = "QualityAgent"
    tool_name = "quality_check"

    def run(self, state, registry, options):
        reports: List[Dict[str, Any]] = []
        for frame in state.case_input.frames:
            obs = registry.execute("quality_check", image_path=frame.image_path)
            reports.append({**obs, **_frame_metadata(frame)})
        primary = _representative_frame_result(reports, state)
        usable_count = sum(1 for report in reports if report.get("usable"))
        total_count = len(reports)
        obs = dict(primary)
        obs.update(
            {
                "primary_frame": primary,
                "per_frame": reports,
                "frame_count": total_count,
                "usable_frame_count": usable_count,
                "quality_aggregation": "per_frame_primary_representative",
                "usable": bool(usable_count),
            }
        )
        if usable_count == 0:
            status = "failed"
        elif usable_count < total_count:
            status = "partial"
        else:
            status = "completed"
        expl = f"{usable_count}/{total_count} 个关键帧通过质量检查；代表帧为 frame_index={primary.get('frame_index', '?')}。"
        return StepResult(
            observation=obs,
            status=status,
            explanation=expl,
            inputs={"image_paths": [frame.image_path for frame in state.case_input.frames]},
        )

    def render(self, state, result, options):
        from ..visualization.artifacts import save_quality_panel

        if result.status == "skipped":
            return []
        out = state.figures_dir / f"step-{self.step_number:02d}-quality.png"
        save_quality_panel(result.observation, state.case_input.primary_image_path, out)
        return [str(out)]


class BinaryGateAgent(BasePipelineStep):
    step_number = 4
    step_id = "binary_gate"
    agent_name = "BinaryGateAgent"
    tool_name = "binary_classify"

    def run(self, state, registry, options):
        if not options.enable_binary or options.triage_mode == "off":
            state.gate_decision = "run_t"
            state.triage_path = "malignant_run_t"
            return StepResult(
                status="skipped",
                observation={"available": False, "reason": "binary gate disabled"},
                explanation="L0 良恶性闸门已关闭（triage_mode=off 或 enable_binary=False）。",
            )

        per_frame: List[Dict[str, Any]] = []
        for frame in state.case_input.frames:
            obs = registry.execute(
                "binary_classify",
                image_path=frame.image_path,
                frame_index=frame.frame_index,
                gate_skip_t_threshold=options.skip_t_threshold,
            )
            per_frame.append({**obs, **_frame_metadata(frame)})

        state.per_frame_binary = per_frame
        primary = _aggregate_binary_frames(
            per_frame,
            state.case_input.frames,
            options.skip_t_threshold,
        )
        gate = primary.get("gate_decision", "run_t")
        if options.triage_mode == "soft":
            gate = "run_t"
        state.gate_decision = gate
        state.triage_path = "benign_skip" if gate == "skip_t" else "malignant_run_t"

        obs = {
            "available": bool(per_frame),
            "primary_frame": primary,
            "representative_frame": _representative_frame_result(per_frame, state),
            "per_frame": per_frame,
            "gate_decision": gate,
            "triage_mode": options.triage_mode,
            "skip_t_threshold": options.skip_t_threshold,
        }
        if options.triage_mode == "soft":
            obs["soft_override"] = "L0 recorded; T-staging chain always runs"
        expl = (
            f"L0 良恶性：质量加权聚合 top1={primary.get('top1_label')} "
            f"p={primary.get('top1_prob')} → gate={gate}。"
        )
        skip_vision = gate == "skip_t" and options.triage_mode != "soft"
        return StepResult(
            observation=obs,
            skip_remaining_vision=skip_vision,
            status="completed" if per_frame else "failed",
        )

    def render(self, state, result, options):
        from ..visualization.step_renderers import save_binary_panel

        primary = (result.observation.get("primary_frame") or {})
        if not primary.get("available"):
            return []
        out = state.figures_dir / f"step-{self.step_number:02d}-binary.png"
        save_binary_panel(primary, state.case_input.primary_image_path, out)
        return [str(out)]


class LumenDetectAgent(BasePipelineStep):
    step_number = 5
    step_id = "lumen_detect"
    agent_name = "LumenDetectAgent"
    tool_name = "detect_lumen"

    def run(self, state, registry, options):
        if _should_skip_vision(state):
            return StepResult(
                status="skipped",
                observation={"skipped": True, "reason": "skip_t gate"},
                explanation="良恶性闸门 skip_t，跳过胃腔检测。",
            )
        path = state.case_input.primary_image_path
        override_bbox = getattr(options, "override_lumen_bbox", None)
        override_polygon = getattr(options, "lumen_override_polygon", None)
        image = cv2.imread(path)
        exact_mask = (
            lumen_mask_from_polygon(
                override_polygon,
                image.shape[0],
                image.shape[1],
            )
            if image is not None
            else None
        )
        if exact_mask is not None:
            mask_bbox = lumen_bbox_from_mask(exact_mask)
            if mask_bbox is not None:
                override_bbox = mask_bbox

        # Doctor-confirmed lumen: skip YOLO cold-path entirely.
        if getattr(options, "use_lumen_override", False) and (
            isinstance(override_bbox, dict) or exact_mask is not None
        ):
            doctor_bbox = {
                "x1": int(round(float(override_bbox["x1"]))),
                "y1": int(round(float(override_bbox["y1"]))),
                "x2": int(round(float(override_bbox["x2"]))),
                "y2": int(round(float(override_bbox["y2"]))),
            }
            state.lumen_bbox = doctor_bbox
            state.lumen_mask = exact_mask
            meta = getattr(options, "lumen_override_meta", None) or {}
            obs = {
                "available": True,
                "lumen_detected": True,
                "lumen_bbox": doctor_bbox,
                "roi_source": "doctor_override",
                "lumen_source": "doctor_override",
                "override_source": getattr(options, "lumen_override_source", "manual"),
                "yolo_lumen_bbox": None,
                "yolo_skipped": True,
                "lumen_polygon": override_polygon,
                "lumen_mask_available": exact_mask is not None,
                "lumen_mask_source": (
                    "confirmed_polygon"
                    if exact_mask is not None
                    else "bbox_proxy"
                ),
                "lumen_confidence": meta.get("lumen_confidence"),
                "lumen_mask_type": meta.get("lumen_mask_type") or (
                    "confirmed_polygon" if exact_mask is not None else "bbox_proxy"
                ),
                "detector_backend_id": meta.get("detector_backend_id"),
                "sam_backend_id": meta.get("sam_backend_id"),
                "sam_score": meta.get("sam_score"),
            }
            if exact_mask is not None:
                obs["lumen_mask_area_ratio"] = round(
                    float(np.count_nonzero(exact_mask)) / float(exact_mask.size or 1),
                    6,
                )
                obs["lumen_area_ratio"] = obs["lumen_mask_area_ratio"]
                obs["lumen_geometry"] = lumen_geometry_from_bbox(
                    doctor_bbox,
                    exact_mask.shape[0],
                    exact_mask.shape[1],
                )
                obs["lumen_direction"] = "not_assessed"
                obs["lumen_direction_source"] = "confirmed_mask_centroid"
                state.figures_dir.mkdir(parents=True, exist_ok=True)
                mask_png = state.figures_dir / "step-05-lumen-mask.png"
                cv2.imwrite(str(mask_png), exact_mask)
                obs["lumen_mask_png"] = str(mask_png)
            elif image is not None:
                obs["lumen_geometry"] = lumen_geometry_from_bbox(
                    doctor_bbox,
                    image.shape[0],
                    image.shape[1],
                )
            expl = (
                f"使用医生确认的胃腔几何（跳过 YOLO）：source={obs.get('override_source')} "
                f"mask={obs.get('lumen_mask_source')} bbox={doctor_bbox}。"
            )
            return StepResult(observation=obs, explanation=expl, inputs={"image_path": path})

        obs = registry.execute("detect_lumen", image_path=path)
        yolo_bbox = dict(obs["lumen_bbox"]) if obs.get("lumen_detected") and obs.get("lumen_bbox") else None
        state.lumen_mask = None
        if yolo_bbox:
            state.lumen_bbox = yolo_bbox
            obs = dict(obs)
            obs["yolo_lumen_bbox"] = yolo_bbox
            obs["lumen_source"] = "yolo"

        expl = (
            f"YOLO 胃腔检测：detected={obs.get('lumen_detected')} "
            f"conf={obs.get('lumen_confidence', 0)}。"
        )
        return StepResult(observation=obs, explanation=expl, inputs={"image_path": path})

    def render(self, state, result, options):
        from ..visualization.step_renderers import save_lumen_overlay

        if result.status == "skipped" or not result.observation.get("lumen_detected"):
            return []
        out = state.figures_dir / f"step-{self.step_number:02d}-lumen.png"
        save_lumen_overlay(state.case_input.primary_image_path, result.observation, out)
        return [str(out)]


class LesionSegAgent(BasePipelineStep):
    step_number = 6
    step_id = "lesion_seg"
    agent_name = "LesionSegAgent"
    tool_name = "segment"

    def run(self, state, registry, options):
        if _should_skip_vision(state):
            return StepResult(
                status="skipped",
                observation={"skipped": True, "reason": "skip_t gate"},
                explanation="跳过病灶分割。",
            )

        path = state.case_input.primary_image_path
        override_mask = _resolve_mask_override(path, options)
        if override_mask is not None:
            state.lesion_mask = override_mask
            roi = getattr(options, "override_roi_bbox", None)
            if not roi:
                ys, xs = np.where(override_mask > 0)
                if ys.size > 0:
                    roi = {
                        "x1": int(xs.min()),
                        "y1": int(ys.min()),
                        "x2": int(xs.max()) + 1,
                        "y2": int(ys.max()) + 1,
                    }
            if roi:
                state.lesion_roi_bbox = dict(roi)
            area = float(np.count_nonzero(override_mask)) / float(override_mask.size or 1)
            obs = {
                "available": True,
                "mask_available": True,
                "roi_source": "doctor_override",
                "roi_bbox": state.lesion_roi_bbox,
                "lesion_area_ratio": area,
                "selection": {
                    "chosen_backend": "doctor_override",
                    "rationale": f"UI mask override ({getattr(options, 'mask_override_source', 'manual')})",
                },
                "override_source": getattr(options, "mask_override_source", "manual"),
                "wall_polygon": getattr(options, "wall_polygon", None),
                "wall_polygon_points": (
                    len(getattr(options, "wall_polygon", None) or [])
                    if getattr(options, "wall_polygon", None)
                    else 0
                ),
            }
            figures_dir = state.figures_dir
            figures_dir.mkdir(parents=True, exist_ok=True)
            override_png = figures_dir / "step-06-override-mask.png"
            cv2.imwrite(str(override_png), override_mask)
            obs["mask_png"] = str(override_png)
            return StepResult(
                observation=obs,
                explanation=(
                    f"使用医生编辑边界覆盖分割 "
                    f"(source={obs['override_source']}, area={area:.4f})."
                ),
                status="completed",
                inputs={
                    "image_path": path,
                    "use_mask_override": True,
                    "override_source": obs["override_source"],
                },
            )

        from ..core.seg_policy import choose_lesion_mask

        unet_obs = registry.execute("segment", image_path=path)
        unet_tool = _get_seg_tool(registry)
        unet_mask = unet_tool.get_cached_mask(path)

        dino_obs: Optional[Dict[str, Any]] = None
        dino_mask = None
        run_dino = options.enable_dino and options.seg_policy in ("auto", "dino")
        if run_dino:
            dino_tool = registry.get("segment_dinov3_candidate")
            if dino_tool is None:
                from ..tools.dinov3_segmentation_tool import DINOv3SegmentationTool

                dino_tool = DINOv3SegmentationTool()
            dino_obs = dino_tool.execute(image_path=path)
            if hasattr(dino_tool, "get_cached_mask"):
                dino_mask = dino_tool.get_cached_mask(path)

        policy = options.seg_policy if run_dino else "unet"
        chosen_mask, _key, obs = choose_lesion_mask(
            unet_obs=unet_obs,
            dino_obs=dino_obs,
            unet_mask=unet_mask,
            dino_mask=dino_mask,
            policy=policy,
        )
        if chosen_mask is not None:
            state.lesion_mask = chosen_mask
        if obs.get("roi_bbox"):
            state.lesion_roi_bbox = dict(obs["roi_bbox"])

        figures_dir = state.figures_dir
        figures_dir.mkdir(parents=True, exist_ok=True)
        if unet_mask is not None:
            unet_png = figures_dir / "step-06-unet-mask.png"
            cv2.imwrite(str(unet_png), unet_mask)
            unet_obs = {**unet_obs, "mask_png": str(unet_png)}
            obs["unet"] = unet_obs
        if dino_mask is not None:
            dino_png = figures_dir / "step-06-dino-mask.png"
            cv2.imwrite(str(dino_png), dino_mask)
            dino_obs = {**(dino_obs or {}), "mask_png": str(dino_png)}
            obs["dinov3"] = dino_obs
        sel = obs.get("selection") or {}
        expl = (
            f"分割 backend={sel.get('chosen_backend', 'unet')}: "
            f"mask={obs.get('mask_available')} area={obs.get('lesion_area_ratio', 0)}. "
            f"{sel.get('rationale', '')}"
        )
        status = "completed" if obs.get("mask_available") else "partial"
        return StepResult(
            observation=obs,
            explanation=expl,
            status=status,
            inputs={"image_path": path, "seg_policy": policy, "enable_dino": options.enable_dino},
        )

    def render(self, state, result, options):
        from ..visualization.step_renderers import save_seg_overlay

        if result.status == "skipped":
            return []
        paths: List[str] = []
        primary = state.figures_dir / f"step-{self.step_number:02d}-seg.png"
        save_seg_overlay(
            state.case_input.primary_image_path,
            state.lesion_mask,
            result.observation,
            primary,
        )
        paths.append(str(primary))
        unet = (result.observation.get("unet") or {})
        if result.observation.get("dinov3", {}).get("available"):
            compare = state.figures_dir / f"step-{self.step_number:02d}-seg-unet-vs-dino.png"
            try:
                from ..visualization.step_renderers import save_dual_seg_compare

                save_dual_seg_compare(
                    state.case_input.primary_image_path,
                    result.observation,
                    compare,
                )
                paths.append(str(compare))
            except Exception:
                pass
        return paths


class MorphologyAgent(BasePipelineStep):
    step_number = 7
    step_id = "morphology"
    agent_name = "MorphologyAgent"
    tool_name = "morphology"

    def run(self, state, registry, options):
        if _should_skip_vision(state):
            return StepResult(status="skipped", observation={"skipped": True}, explanation="跳过形态学。")
        kwargs: Dict[str, Any] = {}
        if state.lesion_mask is not None:
            kwargs["mask_array"] = state.lesion_mask
        obs = registry.execute("morphology", **kwargs)
        expl = (
            f"形态学：irregularity={obs.get('boundary_irregularity', '?')} "
            f"convexity={obs.get('convexity', '?')} "
            f"smoothness={obs.get('smoothness_index', '?')}。"
        )
        return StepResult(observation=obs, explanation=expl)

    def render(self, state, result, options):
        from ..visualization.artifacts import save_morphology_panel

        if result.status == "skipped" or not result.observation.get("valid", True):
            return []
        out = state.figures_dir / f"step-{self.step_number:02d}-morphology.png"
        save_morphology_panel(result.observation, out)
        return [str(out)]


class TStagingAgent(BasePipelineStep):
    step_number = 8
    step_id = "t_staging"
    agent_name = "TStagingAgent"
    tool_name = "classify"

    def run(self, state, registry, options):
        if _should_skip_vision(state):
            return StepResult(status="skipped", observation={"skipped": True}, explanation="跳过 T 分期。")

        clin_feats = _clinical_features_for_classifier(state.case_input.clinical)
        primary_path = state.case_input.primary_frame.image_path
        per_frame: List[Dict[str, Any]] = []
        for frame in state.case_input.frames:
            kwargs: Dict[str, Any] = {
                "image_path": frame.image_path,
                "clinical_features": clin_feats,
                "patient_id": state.case_input.patient_id,
            }
            kwargs.update(
                _classification_roi_kwargs(
                    frame.roi_path,
                    state,
                    options,
                    is_primary=frame.image_path == primary_path,
                )
            )
            if state.lesion_mask is not None and frame.image_path == primary_path:
                kwargs["mask_array"] = state.lesion_mask
            if state.lumen_bbox is not None and frame.image_path == primary_path:
                kwargs["lumen_bbox"] = state.lumen_bbox
            obs = registry.execute("classify", **kwargs)
            per_frame.append({**obs, **_frame_metadata(frame)})

        state.per_frame_classifications = per_frame
        primary = _aggregate_tstage_frames(per_frame, state.case_input.frames)
        state.primary_classification = primary
        expl = (
            f"L1 T 分期（acc_boost2）：质量加权聚合 top1={primary.get('top1_stage')} "
            f"p={primary.get('top1_prob')}，使用 {primary.get('aggregated_frame_count', 0)} 帧。"
        )
        return StepResult(
            observation={
                "primary": primary,
                "representative_frame": _representative_frame_result(per_frame, state),
                "per_frame": per_frame,
            },
            status="completed" if per_frame else "failed",
            explanation=expl,
        )

    def render(self, state, result, options):
        from ..tools.classification_tool import ClassificationTool
        from ..visualization.step_renderers import save_classification_panel

        if result.status == "skipped":
            return []
        primary = result.observation.get("primary") or {}
        # ClassificationTool instance from registry is not stored on state; lazy load
        clf = ClassificationTool()
        out = state.figures_dir / f"step-{self.step_number:02d}-tstage.png"
        save_classification_panel(
            state.case_input.primary_image_path,
            primary,
            clf,
            state.lesion_mask,
            out,
            roi_path=state.case_input.primary_frame.roi_path
            if getattr(options, "roi_mode", "predicted") == "doctor"
            else None,
            roi_bbox=state.lesion_roi_bbox,
            lumen_bbox=state.lumen_bbox,
        )
        return [str(out)]


class WallEvidenceAgent(BasePipelineStep):
    step_number = 9
    step_id = "wall_evidence"
    agent_name = "WallEvidenceAgent"
    tool_name = "wall_evidence"

    def run(self, state, registry, options):
        if _should_skip_vision(state):
            return StepResult(status="skipped", observation={"skipped": True}, explanation="跳过壁层证据。")

        path = state.case_input.primary_image_path
        if (state.lumen_bbox is None and state.lumen_mask is None) or state.lesion_mask is None:
            obs = {
                "available": False,
                "error": "missing lumen geometry or lesion_mask",
                "has_lumen_bbox": state.lumen_bbox is not None,
                "has_lumen_mask": state.lumen_mask is not None,
                "has_lesion_mask": state.lesion_mask is not None,
            }
            return StepResult(
                status="partial",
                observation=obs,
                explanation="壁层证据不可用：缺少 lumen 几何或分割 mask。",
            )

        obs = registry.execute(
            "wall_evidence",
            image_path=path,
            lumen_bbox=state.lumen_bbox,
            lumen_mask=state.lumen_mask,
            lumen_mask_source=(
                _step_obs(state, "lumen_detect").get("lumen_mask_source")
                if state.lumen_mask is not None
                else None
            ),
            lesion_mask=state.lesion_mask,
        )
        expl = f"壁层 SDF：available={obs.get('available')} risk={obs.get('penetration_risk', '?')}。"
        status = "completed" if obs.get("available") else "partial"
        return StepResult(observation=obs, explanation=expl, status=status)

    def render(self, state, result, options):
        from ..visualization.artifacts import save_wall_panel

        if result.status == "skipped" or not result.observation.get("available"):
            return []
        out = state.figures_dir / f"step-{self.step_number:02d}-wall.png"
        saved = save_wall_panel(
            result.observation,
            state.case_input.primary_image_path,
            out,
            lumen_bbox=state.lumen_bbox,
            lumen_mask=state.lumen_mask,
            lesion_mask=state.lesion_mask,
        )
        return [str(saved)] if saved else []


class GcUsSignAgent(BasePipelineStep):
    """Score each structured GC-US sign from clinical and geometry evidence."""

    step_number = 10
    step_id = "gc_us_signs"
    agent_name = "GcUsSignAgent"
    tool_name = "gc_us_signs"

    def run(self, state, registry, options):
        if _should_skip_vision(state):
            return StepResult(status="skipped", observation={"skipped": True}, explanation="跳过 GC-US 征象评分。")

        clinical = state.case_input.clinical or {}
        size = clinical.get("tumorSize") or clinical.get("tumor_size") or {}
        if not isinstance(size, dict):
            size = {}
        biomarkers = clinical.get("biomarkers") or {}
        if not isinstance(biomarkers, dict):
            biomarkers = {}
        length_cm = (
            clinical.get("length_cm")
            or clinical.get("tumor_length_cm")
            or size.get("length")
        )
        thickness_cm = (
            clinical.get("thickness_cm")
            or clinical.get("tumor_thickness_cm")
            or size.get("thickness")
        )
        if length_cm is None and clinical.get("tumor_size_mm") is not None:
            length_cm = float(clinical["tumor_size_mm"]) / 10.0
        if thickness_cm is None and clinical.get("tumor_thickness_mm") is not None:
            thickness_cm = float(clinical["tumor_thickness_mm"]) / 10.0

        cea_value = clinical.get("cea_value") or clinical.get("CEA_value") or biomarkers.get("cea") or clinical.get("cea")
        cea_positive = biomarkers.get("cea_positive")
        if cea_positive is None:
            cea_positive = clinical.get("cea_positive")
        if isinstance(cea_positive, str):
            cea_positive = cea_positive.strip().lower() in {"1", "true", "yes", "阳性", "positive", "+"}

        layer_label = (
            clinical.get("layer_label")
            or clinical.get("wall_layer")
            or clinical.get("layer_structure")
        )
        serosa_text = (
            clinical.get("serosa_text")
            or clinical.get("serosa_status")
            or clinical.get("serosa_change")
        )
        structural_stage = clinical.get("structural_stage")
        wall_polygon = options.wall_polygon if isinstance(options.wall_polygon, list) and len(options.wall_polygon) >= 3 else None
        wall_obs = _step_obs(state, "wall_evidence")
        wall_features = wall_obs.get("wall_features") if wall_obs.get("available") else None
        contact_ratio = (wall_features or {}).get("contact_arc_ratio")
        in_contact = None if contact_ratio is None else float(contact_ratio) >= 0.02
        structural_evidence = (
            "explicit"
            if wall_polygon is not None or layer_label or serosa_text
            else "proxy"
            if wall_obs.get("available")
            else "missing"
        )

        obs = registry.execute(
            "gc_us_signs",
            image_path=state.case_input.primary_image_path,
            lesion_mask=state.lesion_mask,
            lumen_bbox=state.lumen_bbox,
            lumen_mask=state.lumen_mask,
            length_cm=length_cm,
            thickness_cm=thickness_cm,
            cea_positive=cea_positive,
            cea_value=cea_value,
            location=clinical.get("location") or clinical.get("tumor_location"),
            layer_label=layer_label,
            serosa_text=serosa_text,
            structural_evidence=structural_evidence,
            structural_stage=structural_stage,
            in_contact=in_contact,
            wall_polygon=wall_polygon,
            wall_proxy_features=wall_features,
            patient_id=state.case_input.patient_id,
            sample_id=state.case_input.case_id,
            frame_id=state.case_input.primary_frame.frame_id or "",
        )
        obs["input_provenance"] = {
            "lesion_mask": "state.lesion_mask",
            "lumen_bbox": "state.lumen_bbox",
            "lumen_mask": (
                "state.lumen_mask"
                if state.lumen_mask is not None
                else "bbox_proxy"
            ),
            "wall_evidence": "wall_evidence.wall_features" if wall_features else "unavailable",
            "structural_evidence": structural_evidence,
        }
        items = obs.get("items") or []
        explanation = (
            f"GC-US 征象评分：items={len(items)} total={obs.get('total', '?')}/"
            f"{obs.get('max_total', '?')} status={obs.get('status', '?')}，"
            "墙壁代理不直接解锁确定 cT。"
        )
        status = "completed" if obs.get("available") else "partial"
        return StepResult(status=status, observation=obs, explanation=explanation)

    def render(self, state, result, options):
        from ..visualization.artifacts import save_gc_us_sign_panel

        if result.status == "skipped":
            return []
        out = state.figures_dir / f"step-{self.step_number:02d}-gc-us-signs.png"
        saved = save_gc_us_sign_panel(result.observation, out)
        return [str(saved)] if saved else []


class DINOv3Agent(BasePipelineStep):
    step_number = 11
    step_id = "dinov3_seg"
    agent_name = "DINOv3Agent"
    tool_name = "segment_dinov3_candidate"

    def run(self, state, registry, options):
        if not options.enable_dino:
            return StepResult(
                status="skipped",
                observation={"available": False, "reason": "enable_dino=False"},
                explanation="DINOv3 候选分割未启用。",
            )

        path = state.case_input.primary_image_path
        tool = registry.get("segment_dinov3_candidate")
        if tool is None:
            from ..tools.dinov3_segmentation_tool import DINOv3SegmentationTool

            tool = DINOv3SegmentationTool()
            obs = tool.execute(image_path=path)
        else:
            obs = tool.execute(image_path=path)

        expl = f"DINOv3 候选分割：mask={obs.get('mask_available', obs.get('available'))}。"
        return StepResult(observation=obs, explanation=expl)


class DinoSignFusionAgent(BasePipelineStep):
    """Join DINO evidence and structured signs without replacing the T model."""

    step_number = 12
    step_id = "dino_sign_fusion"
    agent_name = "DINOAndSignFusionAgent"
    tool_name = "dino_sign_fusion"

    def run(self, state, registry, options):
        dino = _step_obs(state, "dinov3_seg")
        morphology = _step_obs(state, "morphology")
        wall = _step_obs(state, "wall_evidence")
        gc_signs = _step_obs(state, "gc_us_signs")
        classification = _step_obs(state, "t_staging")
        dino_available = bool(
            dino.get("available") or dino.get("mask_available")
        )
        wall_features = wall.get("wall_features") or {}
        sign_status = {
            "morphology": "available" if morphology.get("valid") else "partial",
            "wall": "available" if wall.get("available") else "partial",
            "lumen": "available" if (state.lumen_bbox or state.lumen_mask is not None) else "missing",
            "gc_us_signs": "available" if gc_signs.get("available") else "partial",
        }
        supporting = []
        uncertainty = []
        if dino_available:
            supporting.append("DINOv3 region evidence is available for this case.")
        else:
            uncertainty.append("DINOv3 evidence is unavailable for this case.")
        if morphology.get("valid"):
            supporting.append(
                "Structured morphology signs are available "
                f"(irregularity={morphology.get('boundary_irregularity', 'n/a')}, "
                f"smoothness={morphology.get('smoothness_index', 'n/a')})."
            )
        else:
            uncertainty.append("Morphology signs are incomplete.")
        if wall.get("available"):
            supporting.append(
                "Wall evidence is available "
                f"(risk={wall.get('penetration_risk', 'unknown')})."
            )
        else:
            uncertainty.append("Wall evidence is proxy-only or unavailable.")
        if not state.lumen_bbox and state.lumen_mask is None:
            uncertainty.append("Lumen geometry is unavailable for sign alignment.")
        if gc_signs.get("available"):
            supporting.append(
                "GC-US sign scorer is available "
                f"(status={gc_signs.get('status', 'unknown')}, "
                f"normalized_i={gc_signs.get('normalized_i', 'unknown')})."
            )
        else:
            uncertainty.append("GC-US sign scorer is unavailable or not assessable.")

        obs = {
            "available": bool(
                dino_available
                or morphology.get("valid")
                or wall.get("available")
                or gc_signs.get("available")
            ),
            "fusion_mode": "evidence_only_probe",
            "model_fusion_available": False,
            "final_t_stage_ownership": "t_staging_step",
            "dino": {
                "available": dino_available,
                "mask_available": bool(dino.get("mask_available")),
                "source": dino.get("source") or dino.get("model"),
            },
            "structured_signs": sign_status,
            "gc_us_signs": {
                "available": bool(gc_signs.get("available")),
                "status": gc_signs.get("status"),
                "normalized_i": gc_signs.get("normalized_i"),
                "ct_stage": gc_signs.get("ct_stage"),
                "confidence": gc_signs.get("confidence"),
            },
            "sign_values": {
                "boundary_irregularity": morphology.get("boundary_irregularity"),
                "smoothness_index": morphology.get("smoothness_index"),
                "roughness_index": morphology.get("roughness_index"),
                "lesion_area_ratio": morphology.get("lesion_area_ratio"),
                "penetration_risk": wall.get("penetration_risk"),
                "fraction_outside_lumen": wall_features.get("fraction_outside_lumen"),
            },
            "classification_context": {
                "top1_stage": classification.get("primary", {}).get("top1_stage")
                if isinstance(classification, dict)
                else None,
            },
            "supporting_evidence": supporting,
            "uncertainty_flags": uncertainty,
            "provenance": {
                "probe": "pipeline/experiments/reports/dino_gc_us_sign_fusion_probe_20260801",
                "feature_source": "cached_workstation_dinov3_region_features",
                "note": "Exploratory evidence fusion; no trained fusion checkpoint is used.",
            },
        }
        status = "completed" if obs["available"] else "partial"
        return StepResult(
            status=status,
            observation=obs,
            explanation=(
                "DINO 与结构化征象已统一为可追溯证据层；"
                "当前不覆盖 T 分期主模型结论。"
            ),
            inputs={"dino_enabled": bool(options.enable_dino)},
        )


class CaseRAGAgent(BasePipelineStep):
    step_number = 13
    step_id = "case_rag"
    agent_name = "CaseRAGAgent"
    tool_name = "retrieve_similar"

    def run(self, state, registry, options):
        if _should_skip_vision(state):
            return StepResult(status="skipped", observation={"skipped": True}, explanation="跳过 Case-RAG。")
        if not options.enable_rag:
            return StepResult(
                status="skipped",
                observation={"available": False, "reason": "enable_rag=False"},
                explanation="Case-RAG 未启用。",
            )

        case_context = _build_rag_case_context(state)
        adapter_feature = _adapter_patient_feature_from_state(state)
        kwargs = {
            "case_context": case_context,
            "patient_id": state.case_input.patient_id,
            "top_k": 5,
        }
        if adapter_feature is not None:
            kwargs["adapter_patient_feature"] = adapter_feature
        obs = registry.execute("retrieve_similar", **kwargs)
        if not isinstance(obs, dict):
            obs = {"available": False, "reason": "retrieve_similar returned non-dict", "similar_cases": []}
        runtime = obs.get("runtime_invocation") or {}
        backend = runtime.get("backend") or ("adapter_dino" if obs.get("available") and adapter_feature else "unknown")
        sd = obs.get("stage_distribution") or {}
        hits = len(obs.get("similar_cases") or [])
        if obs.get("available"):
            expl = f"Case-RAG ({backend}): hits={hits} 分布={sd}。"
        else:
            reason = obs.get("reason") or "unavailable"
            expl = f"Case-RAG unavailable: {reason}."
            obs.setdefault("runtime_invocation", {
                "api_kind": "case_similarity",
                "called": True,
                "backend": backend,
                "available": False,
                "reason": reason,
            })
        return StepResult(observation=obs, explanation=expl)

    def render(self, state, result, options):
        from ..visualization.step_renderers import save_rag_panel

        if result.status == "skipped" or not result.observation.get("available"):
            return []
        out = state.figures_dir / f"step-{self.step_number:02d}-rag.png"
        save_rag_panel(result.observation, out)
        return [str(out)]


class ReportSynthAgent(BasePipelineStep):
    step_number = 14
    step_id = "report_synth"
    agent_name = "ReportSynthAgent"
    tool_name = None

    def run(self, state, registry, options):
        from ..product.analyze_case import _build_rule_based_report

        ci = state.case_input
        seg_obs = _step_obs(state, "lesion_seg")
        lumen_obs = _step_obs(state, "lumen_detect")
        wall_obs = _step_obs(state, "wall_evidence")
        gc_sign_obs = _step_obs(state, "gc_us_signs")
        dino_sign_obs = _step_obs(state, "dino_sign_fusion")
        morph_obs = _step_obs(state, "morphology")
        cls_obs = state.primary_classification or _step_obs(state, "t_staging").get("primary") or {}
        rag_obs = _step_obs(state, "case_rag")

        clinical_obs = registry.execute(
            "clinical_risk",
            **_clinical_kwargs(ci.clinical),
        )
        report_obs = registry.execute(
            "structure_report",
            report_payload=ci.report_text or {},
        )

        similar_cases = rag_obs.get("similar_cases") or []
        contour_context = getattr(options, "contour_context", None) or {}
        if not isinstance(contour_context, dict):
            contour_context = {}
        if not contour_context.get("lumen_mask_type") and getattr(options, "lumen_override_meta", None):
            meta = options.lumen_override_meta or {}
            if meta.get("lumen_mask_type"):
                contour_context = {
                    **contour_context,
                    "lumen_mask_type": meta.get("lumen_mask_type"),
                }
        payload = {
            "patient_id": ci.patient_id,
            "case_token": ci.case_id,
            "data_source": ci.data_source,
            "contour_context": contour_context,
            "use_mask_override": bool(getattr(options, "use_mask_override", False)),
            "mask_override": {
                "mask_polygon": getattr(options, "mask_polygon", None),
                "wall_polygon": getattr(options, "wall_polygon", None),
                "roi_bbox": getattr(options, "override_roi_bbox", None),
                "source": getattr(options, "mask_override_source", "manual"),
            },
            "use_lumen_override": bool(getattr(options, "use_lumen_override", False)),
            "lumen_override": {
                "lumen_bbox": getattr(options, "override_lumen_bbox", None),
                "lumen_polygon": getattr(options, "lumen_override_polygon", None),
                "lumen_mask_type": (getattr(options, "lumen_override_meta", None) or {}).get("lumen_mask_type"),
                "source": getattr(options, "lumen_override_source", "manual"),
            },
        }

        memory_context = state.memory_context
        if options.memory_enabled and options.memory_store_path:
            from ..memory.store.retriever import MemoryRetriever

            memory_context = MemoryRetriever(store_root=options.memory_store_path).load_context(
                patient_id=ci.patient_id,
                cohort=ci.data_source,
                classification=cls_obs,
                backend_ids=["tstage_acc_boost2_screened_20260603"],
                image_path=ci.primary_image_path,
                clinical=ci.clinical,
            )
            state.memory_context = memory_context

        from ..memory.guideline_retriever import retrieve_gastric_guideline

        guideline = retrieve_gastric_guideline({
            "classification": cls_obs,
            "wall_evidence": wall_obs,
            "segmentation": seg_obs,
            "clinical": ci.clinical,
            "report": report_obs,
            "gate_decision": state.gate_decision,
            "triage_path": state.triage_path,
        })
        guideline_knowledge = [
            {
                "source": "; ".join(item.get("citations") or item.get("source_ids") or []),
                "title": item.get("title", "胃癌临床指南"),
                "content": item.get("statement", ""),
            }
            for item in guideline.get("evidence", [])
        ]

        if state.gate_decision == "skip_t" and state.per_frame_binary:
            primary_bin = _step_obs(state, "binary_gate").get("primary_frame") or state.per_frame_binary[0]
            benign_confidence = (
                "high" if primary_bin.get("top1_prob", 0) >= options.skip_t_threshold else "medium"
            )
            fusion = {
                "recommended_t_stage": "benign",
                "assist_display_stage": "benign",
                "confidence": benign_confidence,
                "supporting_evidence": [
                    f"L0 binary gate skip_t: {primary_bin.get('top1_label')} "
                    f"p={primary_bin.get('top1_prob')}",
                ],
                "conflicting_evidence": [],
                "uncertainty_flags": [],
                "triage_path": "benign_skip",
                "contour_diagnosis": {
                    "display_stage": "benign",
                    "diagnosis_status": "benign_skip_t",
                    "diagnosis_summary": (
                        f"L0 良恶性闸门判定良性（{primary_bin.get('top1_label')} "
                        f"p={primary_bin.get('top1_prob')}），跳过 T 分期链；"
                        "良性病变不做 cT 分期。"
                    ),
                },
            }
        else:
            fusion = _build_rule_based_report(
                payload,
                segmentation=seg_obs,
                classification=cls_obs,
                morphology=morph_obs,
                clinical=clinical_obs,
                report_text=report_obs,
                similar_cases=similar_cases,
                knowledge=guideline_knowledge,
                lumen_detection=lumen_obs,
                wall_evidence=wall_obs,
                gc_us_signs=gc_sign_obs,
                memory_context=state.memory_context,
                memory_fusion_mode=options.memory_fusion_mode,
            )
            fusion["triage_path"] = state.triage_path or "malignant_run_t"

        fusion["guideline_evidence"] = guideline.get("evidence", [])
        fusion["management_advice"] = guideline.get("management_advice", [])
        fusion["guideline_sources"] = guideline.get("sources", [])
        fusion["guideline_limitations"] = guideline.get("limitations", [])
        fusion["guideline_status"] = guideline.get("status", "unavailable")

        if dino_sign_obs:
            fusion["dino_sign_fusion"] = dino_sign_obs
        if gc_sign_obs:
            fusion["gc_us_signs"] = gc_sign_obs
        state.final_report = fusion
        obs = {
            "fusion": fusion,
            "clinical_risk": clinical_obs,
            "structure_report": report_obs,
            "recommended_t_stage": fusion.get("recommended_t_stage"),
            "confidence": fusion.get("confidence"),
            "guideline_evidence": fusion.get("guideline_evidence", []),
            "management_advice": fusion.get("management_advice", []),
        }
        expl = (
            f"综合报告：推荐 {fusion.get('recommended_t_stage')} "
            f"置信度={fusion.get('confidence')} triage={fusion.get('triage_path')}；"
            f"指南命中={len(guideline.get('evidence', []))}。"
        )
        return StepResult(observation=obs, explanation=expl)


class ClinicalDecisionAgent(BasePipelineStep):
    """Cross-modal decision support after evidence and report synthesis."""

    step_number = 15
    step_id = "clinical_decision"
    agent_name = "ClinicalDecisionAgent"
    tool_name = "clinical_decision"

    def run(self, state, registry, options):
        report = state.final_report or {}
        wall_obs = _step_obs(state, "wall_evidence")
        observation = registry.execute(
            "clinical_decision",
            clinical=state.case_input.clinical,
            report_text=state.case_input.report_text,
            recommended_stage=report.get("recommended_t_stage"),
            wall_evidence=wall_obs,
        )
        if isinstance(state.final_report, dict):
            state.final_report["clinical_decision"] = observation
        status = observation.get("status", "insufficient_evidence")
        expl = (
            f"临床决策支持：status={status} "
            f"requires_mdt={observation.get('requires_mdt', False)}。"
        )
        return StepResult(
            observation=observation,
            status="completed" if observation.get("available") else "partial",
            explanation=expl,
        )


def _step_obs(state: CasePipelineState, step_id: str) -> Dict[str, Any]:
    for s in state.steps:
        if s.step_id == step_id:
            return s.observation
    return {}


def _classification_roi_kwargs(
    frame_roi_path: Optional[str],
    state: CasePipelineState,
    options,
    *,
    is_primary: bool = True,
) -> Dict[str, Any]:
    """Resolve ROI inputs without applying a primary-frame box to other frames."""
    roi_mode = getattr(options, "roi_mode", "predicted")
    seg_obs = _step_obs(state, "lesion_seg")
    roi_bbox = state.lesion_roi_bbox or seg_obs.get("roi_bbox")
    kwargs: Dict[str, Any] = {}

    if roi_mode == "doctor":
        if frame_roi_path:
            kwargs["roi_path"] = frame_roi_path
    elif roi_mode == "predicted":
        if is_primary and roi_bbox:
            kwargs["roi_bbox"] = dict(roi_bbox)
        elif frame_roi_path:
            kwargs["roi_path"] = frame_roi_path
    else:  # auto
        if is_primary and roi_bbox:
            kwargs["roi_bbox"] = dict(roi_bbox)
        elif frame_roi_path:
            kwargs["roi_path"] = frame_roi_path
    return kwargs

def _clinical_kwargs(clinical: Dict[str, Any]) -> Dict[str, Any]:
    c = _norm_clinical(clinical)
    return {
        "age": c.get("age"),
        "sex": c.get("sex"),
        "tumor_location": c.get("tumor_location"),
        "tumor_length_cm": c.get("tumor_length_cm"),
        "tumor_thickness_cm": c.get("tumor_thickness_cm"),
        "differentiation": c.get("differentiation"),
    }


def _adapter_patient_feature_from_state(state: CasePipelineState) -> Optional[List[float]]:
    """Return cached Adapter-DINO patient feature when present on DINO step outputs."""
    dino_obs = _step_obs(state, "dinov3_seg")
    for key in (
        "adapter_patient_feature",
        "patient_feature",
        "adapter_mean_feature",
        "region_embedding_mean",
    ):
        raw = dino_obs.get(key)
        if isinstance(raw, (list, tuple)) and len(raw) > 0:
            try:
                return [float(x) for x in raw]
            except (TypeError, ValueError):
                continue
    cached = dino_obs.get("cached_features") or {}
    if isinstance(cached, dict):
        raw = cached.get("patient_feature") or cached.get("adapter_patient_feature")
        if isinstance(raw, (list, tuple)) and len(raw) > 0:
            try:
                return [float(x) for x in raw]
            except (TypeError, ValueError):
                return None
    return None


def _build_rag_case_context(state: CasePipelineState) -> Dict[str, Any]:
    """Build SimilarityTool case_context from real tool outputs (no hardcoded morph)."""
    cls_results: List[Dict[str, Any]] = []
    frames = state.per_frame_classifications or []
    if not frames:
        primary = state.primary_classification or _step_obs(state, "t_staging").get("primary") or {}
        if primary:
            frames = [primary]
    for cls in frames:
        p = cls.get("probabilities") or {}
        top1 = float(cls.get("top1_prob", 0) or 0)
        top2 = float(cls.get("top2_prob", 0) or 0)
        if top1 <= 0 and p:
            ordered = sorted((float(v or 0) for v in p.values()), reverse=True)
            top1 = ordered[0] if ordered else 0.0
            top2 = ordered[1] if len(ordered) > 1 else 0.0
        cls_results.append(
            {
                "available": True,
                "probabilities": {
                    "T1": float(p.get("T1", 0) or 0),
                    "T2": float(p.get("T2", 0) or 0),
                    "T3": float(p.get("T3", 0) or 0),
                    "T4+": float(p.get("T4+", 0) or 0),
                },
                "top1_stage": cls.get("top1_stage", "?"),
                "top1_prob": top1,
                "top2_prob": top2,
                "uncertainty": float(cls.get("uncertainty", 0) or 0),
            }
        )

    morph_obs = _step_obs(state, "morphology")
    morph_results: List[Dict[str, Any]] = []
    if morph_obs:
        morph_results.append(
            {
                "valid": bool(morph_obs.get("valid")),
                "convexity": float(morph_obs.get("convexity", 0) or 0),
                "solidity": float(morph_obs.get("solidity", 0) or 0),
                "boundary_irregularity": float(
                    morph_obs.get("boundary_irregularity", morph_obs.get("irregularity", 0)) or 0
                ),
                "compactness": float(morph_obs.get("compactness", 0) or 0),
                "lesion_area_ratio": float(morph_obs.get("lesion_area_ratio", 0) or 0),
            }
        )

    wall_obs = _step_obs(state, "wall_evidence")
    wall_ev: Dict[str, Any] = {
        "available": bool(wall_obs.get("available")),
        "penetration_risk": wall_obs.get("penetration_risk"),
        "wall_features": wall_obs.get("wall_features") or {},
    }

    return {
        "cls_results": cls_results,
        "morph_results": morph_results,
        "clinical_info": _norm_clinical(state.case_input.clinical),
        "wall_evidence": wall_ev,
    }


def get_pipeline_steps() -> List[BasePipelineStep]:
    return [
        TriageAgent(),
        FrameExtractAgent(),
        QualityAgent(),
        BinaryGateAgent(),
        LumenDetectAgent(),
        LesionSegAgent(),
        MorphologyAgent(),
        TStagingAgent(),
        WallEvidenceAgent(),
        GcUsSignAgent(),
        DINOv3Agent(),
        DinoSignFusionAgent(),
        CaseRAGAgent(),
        ReportSynthAgent(),
        ClinicalDecisionAgent(),
    ]
