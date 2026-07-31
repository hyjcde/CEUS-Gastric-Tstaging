"""Compile 12-step LangGraph case pipeline."""

from __future__ import annotations

from typing import Any, Dict

from langgraph.graph import END, StateGraph

from .context import PipelineContext
from .nodes import all_step_nodes


class CaseGraphState(Dict[str, Any]):
    """Lightweight graph state; heavy CasePipelineState lives in PipelineContext."""

    skip_vision: bool
    last_step_id: str
    llm_call_count: int


def build_case_pipeline_graph(ctx: PipelineContext):
    """
    Linear 12-node graph: triage → … → report_synth.

    Each node: LLM plan → tool/agent run → LLM interpret → trace.
    """
    workflow: StateGraph = StateGraph(dict)
    nodes = all_step_nodes(ctx)
    step_ids = [sid for sid, _ in nodes]

    for step_id, fn in nodes:
        workflow.add_node(step_id, fn)

    if not step_ids:
        raise RuntimeError("No pipeline steps registered")

    workflow.set_entry_point(step_ids[0])
    for i in range(len(step_ids) - 1):
        workflow.add_edge(step_ids[i], step_ids[i + 1])
    workflow.add_edge(step_ids[-1], END)

    return workflow.compile()
