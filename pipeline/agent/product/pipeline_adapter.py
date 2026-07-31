"""Map unified pipeline output to the frontend Agent API contract."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from ..pipeline.case_input import CaseInput
from ..pipeline.options import PipelineOptions
from ..pipeline.run_case import run_case_pipeline
from ..pipeline.state import CasePipelineState, StepRecord
from ..memory.knowledge_memory import KnowledgeMemory
from ..memory.session_memory import load_session
from ..memory.store.paths import resolve_store_paths
from ..memory.evolver import write_candidates_from_analysis, write_episode_from_analysis
from ..tools.clinical_vector import normalize_frontend_clinical

# Re-use product helpers (artifact URLs, report builders, session I/O).
from . import analyze_case as ac


def _step_obs(state: CasePipelineState, step_id: str) -> Dict[str, Any]:
    for s in state.steps:
        if s.step_id == step_id:
            return s.observation
    return {}


def _pipeline_step_to_agent_step(record: StepRecord, order: int) -> Dict[str, Any]:
    titles = {
        "triage": "病例接入与资料盘点",
        "frame_extract": "帧抽取与关键帧选择",
        "quality": "图像质量检查",
        "binary_gate": "L0 良恶性闸门",
        "lumen_detect": "胃腔检测（YOLO）",
        "lesion_seg": "定位/分割模型调用",
        "morphology": "形态学特征提取",
        "t_staging": "T 分期 4-class 分类",
        "wall_evidence": "壁层侵犯证据（SDF）",
        "dinov3_seg": "DINOv3 候选分割",
        "case_rag": "Case-RAG 相似病例检索",
        "report_synth": "多证据综合推理",
    }
    visual_refs: Dict[str, Any] = {}
    for fig in record.figure_paths:
        p = Path(fig)
        key = p.stem.replace("-", "_") + "_url"
        rel = p.relative_to(ac.PREDICTION_ARTIFACT_ROOT) if str(p).startswith(str(ac.PREDICTION_ARTIFACT_ROOT)) else p.name
        if isinstance(rel, Path):
            visual_refs[key] = ac._artifact_url(rel)
        else:
            visual_refs["figure_url"] = str(fig)

    return {
        "order": order,
        "step_id": record.step_id,
        "title": titles.get(record.step_id, record.agent_name),
        "intent": f"Pipeline step {record.step_id}",
        "decision": "call" if record.status == "completed" else record.status,
        "tool_name": record.tool_name or record.agent_name,
        "status": record.status if record.status != "completed" else "completed",
        "inputs": record.inputs,
        "outputs": ac._compact_tool_output(
            record.observation,
            list(record.observation.keys())[:24],
        ),
        "reasoning": record.explanation,
        "visual_refs": visual_refs,
    }


def _copy_figure_to_artifacts(src: Path, artifact_dir: Path, relative_dir: Path, name: str) -> Dict[str, str]:
    if not src.exists():
        return {}
    dest = artifact_dir / name
    shutil.copy2(src, dest)
    rel = relative_dir / name
    return {
        f"{Path(name).stem}_path": str(dest),
        f"{Path(name).stem}_url": ac._artifact_url(rel),
    }


def _build_prediction_artifacts_from_pipeline(
    state: CasePipelineState,
    payload: Dict[str, Any],
    artifact_info: Dict[str, Any],
) -> Dict[str, Any]:
    artifact_dir: Path = artifact_info["dir"]
    relative_dir: Path = artifact_info["relative_dir"]
    image_path = state.case_input.primary_image_path

    artifacts: Dict[str, Any] = {
        "root": str(artifact_dir),
        "relative_dir": str(relative_dir),
        "created_at": artifact_info["created_at"],
    }

    seg_obs = _step_obs(state, "lesion_seg")
    cls_obs = state.primary_classification or _step_obs(state, "t_staging").get("primary") or {}
    lumen_obs = _step_obs(state, "lumen_detect")

    mask_artifacts = ac._save_prediction_artifacts(
        image_path=image_path,
        predicted_mask=state.lesion_mask,
        segmentation=seg_obs,
        classification=cls_obs or None,
        artifact_info=artifact_info,
    )
    artifacts.update(mask_artifacts)

    if lumen_obs.get("lumen_detected"):
        lumen_art = ac._save_lumen_detection_visual(image_path, lumen_obs, artifact_info)
        artifacts.update(lumen_art)

    wall_obs = _step_obs(state, "wall_evidence")
    if wall_obs.get("available"):
        live_wall = ac._persist_wall_evidence_tool_artifacts(dict(wall_obs), artifact_info)
        artifacts.update(live_wall)

    wall_art = ac._save_wall_analysis_artifacts(
        image_path=image_path,
        predicted_mask=state.lesion_mask,
        segmentation=seg_obs,
        artifact_info=artifact_info,
        reuse_script_wall_panel=bool(artifacts.get("real_wall_analysis_panel_url")),
        keep_existing_layer_profile=bool(artifacts.get("wall_layer_profile_url")),
    )
    artifacts.update(wall_art)

    for record in state.steps:
        for fig in record.figure_paths:
            src = Path(fig)
            art = _copy_figure_to_artifacts(
                src,
                artifact_dir,
                relative_dir,
                f"pipeline_{record.step_id}_{src.name}",
            )
            artifacts.update(art)

    return artifacts


def _resolve_memory_options(payload: Dict[str, Any]) -> tuple[bool, Optional[str], str]:
    enabled = bool(payload.get("memory_enabled"))
    if os.getenv("AGENT_MEMORY_ENABLED", "").lower() in {"1", "true", "yes"}:
        enabled = True
    store_path = payload.get("memory_store") or payload.get("memory_store_path")
    if not store_path and enabled:
        store_path = str(resolve_store_paths(run_id="default").root)
    fusion_mode = str(payload.get("memory_fusion_mode") or os.getenv("AGENT_MEMORY_FUSION_MODE", "soft_prior"))
    return enabled, store_path, fusion_mode


def analyze_via_unified_pipeline(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run the 12-step pipeline and map results to the Workbench JSON contract."""
    clinical_payload_raw = payload.get("clinical") or {}
    clinical_payload = normalize_frontend_clinical(clinical_payload_raw)
    report_payload = payload.get("report_text") or {}

    memory_enabled, memory_store_path, memory_fusion_mode = _resolve_memory_options(payload)
    payload["memory_context"] = payload.get("memory_context")

    case_input = CaseInput.from_frontend_payload(payload)
    artifact_info = ac._prepare_artifact_dir(payload)
    pipeline_out = artifact_info["dir"] / "pipeline"
    pipeline_out.mkdir(parents=True, exist_ok=True)

    stream_cb = None
    if ac._stream_enabled():
        stream_cb = lambda event, pl: ac._emit_stream_event(event, pl)

    mask_override = payload.get("mask_override") if payload.get("use_mask_override") else None
    override_polygon = None
    override_wall = None
    override_roi = None
    override_path = None
    override_source = "manual"
    if isinstance(mask_override, dict):
        override_polygon = mask_override.get("mask_polygon")
        override_wall = mask_override.get("wall_polygon")
        override_roi = mask_override.get("roi_bbox")
        override_path = mask_override.get("mask_path")
        override_source = str(mask_override.get("source") or "manual")

    roi_mode = str(payload.get("roi_mode") or "predicted")
    if roi_mode not in ("predicted", "doctor", "auto"):
        roi_mode = "predicted"

    options = PipelineOptions(
        enable_binary=os.getenv("AGENT_TRIAGE_MODE", "conditional") != "off",
        enable_rag=True,
        enable_dino=os.getenv("AGENT_ENABLE_DINO", "1") == "1",
        triage_mode=os.getenv("AGENT_TRIAGE_MODE", "conditional"),
        render_figures=True,
        emit_stream=ac._stream_enabled(),
        stream_callback=stream_cb,
        memory_enabled=memory_enabled,
        memory_store_path=memory_store_path,
        memory_fusion_mode=memory_fusion_mode,
        roi_mode=roi_mode,
        use_mask_override=bool(payload.get("use_mask_override") and (override_polygon or override_path)),
        mask_polygon=list(override_polygon) if isinstance(override_polygon, list) else None,
        wall_polygon=list(override_wall) if isinstance(override_wall, list) else None,
        mask_path=str(override_path) if override_path else None,
        override_roi_bbox=dict(override_roi) if isinstance(override_roi, dict) else None,
        mask_override_source=override_source,
    )

    state = run_case_pipeline(case_input, pipeline_out, options)

    image_path = case_input.primary_image_path
    frame_plan = [
        {"image_path": f.image_path, "roi_path": f.roi_path}
        for f in case_input.frames
    ]

    lumen_detection = _step_obs(state, "lumen_detect")
    wall_evidence = _step_obs(state, "wall_evidence")
    segmentation = _step_obs(state, "lesion_seg")
    classification = state.primary_classification or _step_obs(state, "t_staging").get("primary") or {}
    if state.per_frame_classifications:
        classification = dict(classification)
        classification.setdefault("frame_aggregation", "mean_probability")
        classification.setdefault("aggregated_frame_count", len(state.per_frame_classifications))
    morphology = _step_obs(state, "morphology")
    synth = _step_obs(state, "report_synth")
    clinical = synth.get("clinical_risk") or {}
    report_text = synth.get("structure_report") or {}
    similar_cases = _step_obs(state, "case_rag").get("similar_cases") or []

    prediction_artifacts = _build_prediction_artifacts_from_pipeline(state, payload, artifact_info)
    real_script_artifacts = ac._save_real_script_artifacts(payload, artifact_info)
    prediction_artifacts.update(real_script_artifacts)

    traces: List[Dict[str, Any]] = []
    for record in state.steps:
        if record.tool_name:
            traces.append({"tool": record.tool_name, "result": record.observation})

    agent_steps: List[Dict[str, Any]] = []
    for idx, record in enumerate(state.steps, start=1):
        step = _pipeline_step_to_agent_step(record, idx)
        agent_steps.append(step)
        if ac._stream_enabled():
            ac._emit_stream_event("agent_step", {"step": step})

    knowledge_query = " ".join([
        str(payload.get("data_source", "")),
        str(clinical_payload_raw.get("location", "")),
        str(payload.get("patient_id", "")),
    ])
    knowledge_memory = KnowledgeMemory.build()
    knowledge = knowledge_memory.search(knowledge_query, top_k=3)

    report = dict(state.final_report or synth.get("fusion") or {})
    report, llm_invocation = ac._maybe_llm_synthesis(report, payload)
    report["dynamic_report_draft"] = ac._build_dynamic_report_draft(
        payload=payload,
        clinical_payload=clinical_payload_raw,
        report=report,
        segmentation=segmentation,
        classification=classification,
        morphology=morphology,
        clinical=clinical,
        report_text=report_text,
        similar_cases=similar_cases,
    )
    report["memory_update_candidates"] = ac._build_memory_update_candidates(
        payload=payload,
        report=report,
        report_text=report_text,
        traces=traces,
    )

    memory_store_ref: Optional[Dict[str, Any]] = None
    if memory_enabled and memory_store_path:
        from ..memory.store.jsonl_store import JsonlMemoryStore

        store = JsonlMemoryStore(store_root=memory_store_path)
        episode_vector = None
        try:
            from ..memory.feature_extractor import extract_patient_vector

            vec = extract_patient_vector(image_path=image_path, clinical=clinical_payload_raw)
            episode_vector = np.asarray(vec, dtype=np.float32).tolist()
        except Exception:
            episode_vector = None
        write_episode_from_analysis(store, payload, report, episode_vector=episode_vector)
        raw_candidates = list(report["memory_update_candidates"])
        written = write_candidates_from_analysis(
            store,
            raw_candidates,
            str(payload.get("patient_id", "")),
        )
        if written:
            enriched: List[Dict[str, Any]] = []
            for raw, entry in zip(raw_candidates, written):
                enriched.append({
                    **raw,
                    "record_id": entry.record.get("record_id"),
                    "status": entry.status,
                    "rule_signature": entry.rule_signature,
                })
            for entry in written[len(raw_candidates):]:
                enriched.append({
                    "record_id": entry.record.get("record_id"),
                    "record_type": entry.record.get("record_type"),
                    "status": entry.status,
                    "title": (entry.record.get("procedural_rule") or {}).get("title"),
                    "rule_signature": entry.rule_signature,
                })
            report["memory_update_candidates"] = enriched
        memory_store_ref = {"path": str(store.paths.root), "run_id": store.paths.root.name}
        report.setdefault("memory_applied", bool(state.memory_context and state.memory_context.get("memory_applied")))
        report.setdefault("active_rules_used", (state.memory_context or {}).get("active_rules_used", []))
        report.setdefault(
            "governance_trust_labels",
            (state.memory_context or {}).get("governance_trust_labels", {}),
        )

    session = load_session(payload.get("session_id"))
    session_entry = {
        "timestamp": session.updated_at,
        "patient_id": str(payload.get("patient_id", "")),
        "recommended_t_stage": report.get("recommended_t_stage"),
        "confidence": report.get("confidence"),
        "tool_trace_count": len(traces),
    }
    session.append_analysis(session_entry)
    session.save()

    similar_payload = _step_obs(state, "case_rag")
    runtime_verification = ac._build_runtime_verification(
        payload=payload,
        lumen_detection=lumen_detection,
        wall_evidence=wall_evidence,
        segmentation=segmentation,
        classification=classification,
        morphology=morphology,
        clinical=clinical,
        report_text=report_text,
        similar_payload=similar_payload,
        memory_source="pipeline",
        llm_invocation=llm_invocation,
        prediction_artifacts=prediction_artifacts,
        dino_feature_artifacts={},
    )

    if ac._stream_enabled():
        ac._emit_stream_event("runtime_verification", {"verification": runtime_verification})

    result = {
        "session_id": session.session_id,
        "session_memory": {
            "session_id": session.session_id,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "patient_ids": session.patient_ids,
            "analysis_count": len(session.analyses),
        },
        "frame_evidence": {
            "frame_count": len(frame_plan),
            "primary_image_path": image_path,
            "aggregation": classification.get("frame_aggregation", "single_frame"),
            "aggregated_frame_count": classification.get("aggregated_frame_count", 1),
        },
        "tool_evidence": {
            "lumen_detection": lumen_detection,
            "wall_evidence": wall_evidence if wall_evidence.get("available") else {
                k: wall_evidence.get(k)
                for k in ("available", "evidence_source", "error")
            },
            "segmentation": segmentation,
            "classification": classification,
            "morphology": morphology,
            "clinical": clinical,
            "report": report_text,
        },
        "similar_cases": similar_cases,
        "knowledge_context": knowledge,
        "report": report,
        "agent_steps": agent_steps,
        "prediction_artifacts": prediction_artifacts,
        "runtime_verification": runtime_verification,
        "traces": traces,
        "pipeline_state_path": str(pipeline_out / "pipeline_state.json"),
        "memory_context": state.memory_context or {},
        "memory_store_ref": memory_store_ref,
    }
    result["trajectory_ref"] = ac._write_trajectory(payload, session.session_id, result)
    return result
