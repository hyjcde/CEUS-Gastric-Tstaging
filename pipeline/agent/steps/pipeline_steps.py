"""Twelve deterministic pipeline step agents."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from ..tools.base import ToolRegistry
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
                "frame_index": f.frame_index,
                "frame_id": f.frame_id,
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
        path = state.case_input.primary_image_path
        obs = registry.execute("quality_check", image_path=path)
        usable = obs.get("usable", obs.get("quality_score", 0) >= 0.3)
        expl = f"首帧质量检查：usable={usable}，score={obs.get('quality_score', '?')}。"
        return StepResult(observation=obs, explanation=expl, inputs={"image_path": path})

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
        for fr in state.case_input.frames:
            obs = registry.execute(
                "binary_classify",
                image_path=fr.image_path,
                frame_index=fr.frame_index,
                gate_skip_t_threshold=options.skip_t_threshold,
            )
            per_frame.append(obs)

        state.per_frame_binary = per_frame
        primary = per_frame[0]
        gate = primary.get("gate_decision", "run_t")
        if options.triage_mode == "soft":
            gate = "run_t"
        state.gate_decision = gate
        state.triage_path = "benign_skip" if gate == "skip_t" else "malignant_run_t"

        obs = {
            "available": True,
            "primary_frame": primary,
            "per_frame": per_frame,
            "gate_decision": gate,
            "triage_mode": options.triage_mode,
            "skip_t_threshold": options.skip_t_threshold,
        }
        if options.triage_mode == "soft":
            obs["soft_override"] = "L0 recorded; T-staging chain always runs"
        expl = (
            f"L0 良恶性：首帧 {primary.get('top1_label')} p={primary.get('top1_prob')} "
            f"→ gate={gate}。"
        )
        skip_vision = gate == "skip_t" and options.triage_mode != "soft"
        return StepResult(
            observation=obs,
            explanation=expl,
            skip_remaining_vision=skip_vision,
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
        obs = registry.execute("detect_lumen", image_path=path)
        if obs.get("lumen_detected") and obs.get("lumen_bbox"):
            state.lumen_bbox = dict(obs["lumen_bbox"])
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
            f"convexity={obs.get('convexity', '?')}。"
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
        per_frame: List[Dict[str, Any]] = []
        for fr in state.case_input.frames:
            kwargs: Dict[str, Any] = {
                "image_path": fr.image_path,
                "clinical_features": clin_feats,
                "patient_id": state.case_input.patient_id,
            }
            kwargs.update(_classification_roi_kwargs(fr.roi_path, state, options))
            if state.lesion_mask is not None and fr.frame_index == 0:
                kwargs["mask_array"] = state.lesion_mask
            if state.lumen_bbox is not None:
                kwargs["lumen_bbox"] = state.lumen_bbox
            obs = registry.execute("classify", **kwargs)
            per_frame.append({**obs, "frame_index": fr.frame_index, "image_path": fr.image_path})

        state.per_frame_classifications = per_frame
        primary = per_frame[0]
        state.primary_classification = primary
        expl = (
            f"L1 T 分期（acc_boost2）：首帧 top1={primary.get('top1_stage')} "
            f"p={primary.get('top1_prob')}。"
        )
        return StepResult(
            observation={"primary": primary, "per_frame": per_frame},
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
        if state.lumen_bbox is None or state.lesion_mask is None:
            obs = {
                "available": False,
                "error": "missing lumen_bbox or lesion_mask",
                "has_lumen_bbox": state.lumen_bbox is not None,
                "has_lesion_mask": state.lesion_mask is not None,
            }
            return StepResult(
                status="partial",
                observation=obs,
                explanation="壁层证据不可用：缺少 lumen bbox 或分割 mask。",
            )

        obs = registry.execute(
            "wall_evidence",
            image_path=path,
            lumen_bbox=state.lumen_bbox,
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
            lesion_mask=state.lesion_mask,
        )
        return [str(saved)] if saved else []


class DINOv3Agent(BasePipelineStep):
    step_number = 10
    step_id = "dinov3_seg"
    agent_name = "DINOv3Agent"
    tool_name = "segment_dinov3_candidate"

    def run(self, state, registry, options):
        if _should_skip_vision(state):
            return StepResult(status="skipped", observation={"skipped": True}, explanation="跳过 DINOv3。")
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


class CaseRAGAgent(BasePipelineStep):
    step_number = 11
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
        obs = registry.execute(
            "retrieve_similar",
            case_context=case_context,
            patient_id=state.case_input.patient_id,
            top_k=5,
        )
        sd = obs.get("stage_distribution") or {}
        expl = f"FAISS Case-RAG：hits={len(obs.get('similar_cases', []))} 分布={sd}。"
        return StepResult(observation=obs, explanation=expl)

    def render(self, state, result, options):
        from ..visualization.step_renderers import save_rag_panel

        if result.status == "skipped" or not result.observation.get("available"):
            return []
        out = state.figures_dir / f"step-{self.step_number:02d}-rag.png"
        save_rag_panel(result.observation, out)
        return [str(out)]


class ReportSynthAgent(BasePipelineStep):
    step_number = 12
    step_id = "report_synth"
    agent_name = "ReportSynthAgent"
    tool_name = None

    def run(self, state, registry, options):
        from ..product.analyze_case import _build_rule_based_report

        ci = state.case_input
        seg_obs = _step_obs(state, "lesion_seg")
        lumen_obs = _step_obs(state, "lumen_detect")
        wall_obs = _step_obs(state, "wall_evidence")
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
        payload = {
            "patient_id": ci.patient_id,
            "case_token": ci.case_id,
            "data_source": ci.data_source,
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

        if state.gate_decision == "skip_t" and state.per_frame_binary:
            primary_bin = state.per_frame_binary[0]
            fusion = {
                "recommended_t_stage": "benign",
                "confidence": "high" if primary_bin.get("top1_prob", 0) >= options.skip_t_threshold else "medium",
                "supporting_evidence": [
                    f"L0 binary gate skip_t: {primary_bin.get('top1_label')} "
                    f"p={primary_bin.get('top1_prob')}",
                ],
                "conflicting_evidence": [],
                "uncertainty_flags": [],
                "triage_path": "benign_skip",
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
                knowledge=[],
                lumen_detection=lumen_obs,
                wall_evidence=wall_obs,
                memory_context=state.memory_context,
                memory_fusion_mode=options.memory_fusion_mode,
            )
            fusion["triage_path"] = state.triage_path or "malignant_run_t"

        state.final_report = fusion
        obs = {
            "fusion": fusion,
            "clinical_risk": clinical_obs,
            "structure_report": report_obs,
            "recommended_t_stage": fusion.get("recommended_t_stage"),
            "confidence": fusion.get("confidence"),
        }
        expl = (
            f"综合报告：推荐 {fusion.get('recommended_t_stage')} "
            f"置信度={fusion.get('confidence')} triage={fusion.get('triage_path')}。"
        )
        return StepResult(observation=obs, explanation=expl)


def _step_obs(state: CasePipelineState, step_id: str) -> Dict[str, Any]:
    for s in state.steps:
        if s.step_id == step_id:
            return s.observation
    return {}


def _classification_roi_kwargs(
    frame_roi_path: Optional[str],
    state: CasePipelineState,
    options,
) -> Dict[str, Any]:
    """Resolve local-branch ROI for ClassificationTool (deploy-consistent default)."""
    roi_mode = getattr(options, "roi_mode", "predicted")
    seg_obs = _step_obs(state, "lesion_seg")
    roi_bbox = state.lesion_roi_bbox or seg_obs.get("roi_bbox")
    kwargs: Dict[str, Any] = {}

    if roi_mode == "doctor":
        if frame_roi_path:
            kwargs["roi_path"] = frame_roi_path
    elif roi_mode == "predicted":
        if roi_bbox:
            kwargs["roi_bbox"] = dict(roi_bbox)
    else:  # auto
        if roi_bbox:
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


def _build_rag_case_context(state: CasePipelineState) -> Dict[str, Any]:
    from ..memory.multimodal_case_vector import extract_multimodal_case_vector

    cls_results = []
    morph_results = []
    for cls in state.per_frame_classifications or [{}]:
        p = cls.get("probabilities") or {}
        cls_results.append(
            {
                "T1": float(p.get("T1", 0)),
                "T2": float(p.get("T2", 0)),
                "T3": float(p.get("T3", 0)),
                "T4+": float(p.get("T4+", 0)),
                "top1_stage": cls.get("top1_stage", "?"),
                "uncertainty": float(cls.get("uncertainty", 0)),
            }
        )
        morph_results.append(
            {
                "convexity": 0.85,
                "solidity": 0.85,
                "irregularity": 0.5,
                "compactness": 0.7,
            }
        )

    wall_obs = _step_obs(state, "wall_evidence")
    wf = wall_obs.get("wall_features") or {} if wall_obs.get("available") else {}
    pr_raw = wall_obs.get("penetration_risk", 0) if wall_obs.get("available") else 0
    if isinstance(pr_raw, str):
        pr_map = {"low": 0.2, "medium": 0.5, "high": 0.85}
        pr_val = pr_map.get(pr_raw.lower(), 0.0)
    else:
        pr_val = float(pr_raw or 0)
    wall_ev = {
        "penetration_risk": pr_val,
        "thickness_cm": float(wf.get("thickness_cm", 0) or 0),
        "irregularity_score": float(wf.get("irregularity_score", 0) or 0),
    }

    bundle = extract_multimodal_case_vector(
        cls_results=cls_results,
        morph_results=morph_results,
        clinical_info=_norm_clinical(state.case_input.clinical),
        wall_evidence=wall_ev,
    )
    return {
        "query_vector": bundle.legacy.tolist() if hasattr(bundle.legacy, "tolist") else list(bundle.legacy),
        "penetration_risk": wall_obs.get("penetration_risk"),
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
        DINOv3Agent(),
        CaseRAGAgent(),
        ReportSynthAgent(),
    ]
