"""LangGraph production case pipeline entry."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from ...core.registry_factory import build_default_registry
from ...pipeline.case_input import CaseInput
from ...pipeline.options import PipelineOptions
from ...pipeline.state import CasePipelineState, _json_default
from .context import PipelineContext
from .graph import build_case_pipeline_graph
from .step_llm import TracingLLM, resolve_pipeline_llm

logger = logging.getLogger(__name__)


def run_langgraph_case_pipeline(
    case_input: CaseInput,
    out_dir: Path,
    options: Optional[PipelineOptions] = None,
) -> CasePipelineState:
    """
    Production pipeline via LangGraph: 15 Agent nodes, each with plan+interpret LLM trace.
    """
    options = options or PipelineOptions()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "steps").mkdir(parents=True, exist_ok=True)
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)

    if options.triage_mode == "off":
        options.enable_binary = False

    registry = build_default_registry(
        device=options.device,
        enable_rag=options.enable_rag,
        enable_binary=options.enable_binary,
        enable_dino=options.enable_dino,
    )

    inner_llm, provider, model = resolve_pipeline_llm()
    llm_trace: list = []
    tracing_llm = TracingLLM(inner_llm, provider=provider, model=model, trace=llm_trace)

    state = CasePipelineState(case_input=case_input, out_dir=out_dir)
    manifest = {
        "case_id": case_input.case_id,
        "patient_id": case_input.patient_id,
        "orchestrator": "langgraph_case_pipeline",
        "llm_provider": provider,
        "llm_model": model,
        "tools": registry.tool_names,
        "options": {
            "enable_binary": options.enable_binary,
            "enable_rag": options.enable_rag,
            "enable_dino": options.enable_dino,
            "triage_mode": options.triage_mode,
            "skip_t_threshold": options.skip_t_threshold,
            "seg_policy": options.seg_policy,
            "memory_enabled": options.memory_enabled,
            "memory_store_path": options.memory_store_path,
            "memory_fusion_mode": options.memory_fusion_mode,
        },
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    ctx = PipelineContext(
        pipeline_state=state,
        registry=registry,
        options=options,
        llm=tracing_llm,
        llm_trace=llm_trace,
        stream_callback=options.stream_callback if options.emit_stream else None,
    )

    if options.memory_enabled and options.memory_store_path:
        from ...memory.store.retriever import MemoryRetriever

        retriever = MemoryRetriever(store_root=options.memory_store_path)
        state.memory_context = retriever.load_context(
            patient_id=case_input.patient_id,
            cohort=case_input.data_source,
            backend_ids=["tstage_acc_boost2_screened_20260603"],
            image_path=case_input.primary_image_path,
            clinical=case_input.clinical,
        )

    graph = build_case_pipeline_graph(ctx)
    graph.invoke({"skip_vision": False, "last_step_id": "", "llm_call_count": 0})

    _write_llm_trace(out_dir, llm_trace, provider, model)

    state.save_summary(
        options={
            "enable_binary": options.enable_binary,
            "enable_rag": options.enable_rag,
            "enable_dino": options.enable_dino,
            "triage_mode": options.triage_mode,
            "skip_t_threshold": options.skip_t_threshold,
            "seg_policy": options.seg_policy,
            "orchestrator": "langgraph_case_pipeline",
            "llm_provider": provider,
            "llm_model": model,
        }
    )

    if options.render_figures:
        try:
            from ...tools.classification_tool import ClassificationTool
            from ...visualization.panels import render_six_panel

            clf = ClassificationTool()
            six_path = state.figures_dir / f"{state.case_input.case_id}_6panel.png"
            render_six_panel(state, six_path, clf_tool=clf)
        except Exception:
            logger.debug("6-panel render skipped", exc_info=True)

    logger.info(
        "LangGraph pipeline done: case=%s steps=%d llm_calls=%d provider=%s",
        case_input.case_id,
        len(state.steps),
        len(llm_trace),
        provider,
    )
    return state


def _write_llm_trace(out_dir: Path, trace: list, provider: str, model: str) -> None:
    payload = {
        "orchestrator": "langgraph_case_pipeline",
        "provider": provider,
        "model": model,
        "total_calls": len(trace),
        "calls": [t.to_dict() for t in trace],
    }
    (out_dir / "llm_trace.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )
