"""LangGraph nodes — one per pipeline Agent with plan/interpret LLM calls."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List

from ...pipeline.base_step import BasePipelineStep
from ...pipeline.state import StepRecord
from ...steps.pipeline_steps import get_pipeline_steps
from .context import PipelineContext
from .step_llm import build_step_messages, summarize_observation


def make_step_node(step: BasePipelineStep, ctx: PipelineContext) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """Factory: LangGraph node for one BasePipelineStep + dual LLM trace."""

    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        step_llm_calls: List[Dict[str, Any]] = []
        t0 = time.time()

        if ctx.should_skip_vision_step(step.step_id):
            record = StepRecord(
                step=step.step_number,
                step_id=step.step_id,
                agent_name=step.agent_name,
                tool_name=step.tool_name,
                status="skipped",
                observation={"skipped": True, "reason": "skip_t gate"},
                elapsed_s=time.time() - t0,
                explanation=f"因 L0 skip_t 跳过 {step.agent_name}。",
                llm_calls=[],
            )
            ctx.pipeline_state.append_step(record)
            return {"skip_vision": True, "last_step_id": step.step_id}

        ci = ctx.pipeline_state.case_input
        inputs_summary = {
            "gate_decision": ctx.pipeline_state.gate_decision,
            "triage_path": ctx.pipeline_state.triage_path,
            "frame_count": len(ci.frames),
            "input_mode": ci.input_mode.value,
        }

        plan_msgs = build_step_messages(
            step_id=step.step_id,
            agent_name=step.agent_name,
            phase="plan",
            case_id=ci.case_id,
            patient_id=ci.patient_id,
            inputs_summary=inputs_summary,
            prior_steps=ctx.prior_step_labels(),
        )
        plan_resp = ctx.llm.traced_chat(
            step_id=step.step_id,
            agent_name=step.agent_name,
            phase="plan",
            messages=plan_msgs,
        )
        step_llm_calls.append(ctx.llm_trace[-1].to_dict())

        record = step.execute_with_timing(ctx.pipeline_state, ctx.registry, ctx.options)

        obs_summary = summarize_observation(record.observation)
        interpret_msgs = build_step_messages(
            step_id=step.step_id,
            agent_name=step.agent_name,
            phase="interpret",
            case_id=ci.case_id,
            patient_id=ci.patient_id,
            inputs_summary=inputs_summary,
            observation_summary=obs_summary,
            prior_steps=ctx.prior_step_labels(),
        )
        interpret_resp = ctx.llm.traced_chat(
            step_id=step.step_id,
            agent_name=step.agent_name,
            phase="interpret",
            messages=interpret_msgs,
        )
        step_llm_calls.append(ctx.llm_trace[-1].to_dict())

        record.llm_calls = step_llm_calls
        record.explanation = (
            f"{record.explanation or ''}\n"
            f"LLM plan: {plan_resp[:200]}\n"
            f"LLM interpret: {interpret_resp[:200]}"
        ).strip()
        _rewrite_last_step(ctx, record)

        if ctx.options.emit_stream and ctx.stream_callback:
            ctx.stream_callback(
                "step_complete",
                {
                    "step": record.step_id,
                    "status": record.status,
                    "observation": record.observation,
                    "llm_calls": step_llm_calls,
                },
            )

        skip_vision = (
            record.step_id == "binary_gate"
            and ctx.pipeline_state.gate_decision == "skip_t"
            and ctx.options.triage_mode != "soft"
        )
        return {
            "skip_vision": skip_vision,
            "last_step_id": step.step_id,
            "llm_call_count": len(ctx.llm_trace),
        }

    return node


def _rewrite_last_step(ctx: PipelineContext, record: StepRecord) -> None:
    """Update last appended step with llm_calls + enriched explanation."""
    steps = ctx.pipeline_state.steps
    if not steps:
        return
    steps[-1] = record
    import json

    from ...pipeline.state import _json_default

    path = ctx.pipeline_state.steps_dir / f"step-{record.step:02d}-{record.step_id}.json"
    path.write_text(
        json.dumps(record.to_dict(), indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )


def all_step_nodes(ctx: PipelineContext) -> List[tuple[str, Callable]]:
    return [(s.step_id, make_step_node(s, ctx)) for s in get_pipeline_steps()]
