"""Compile LangGraph ReAct workflow."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from ..core.case_card import CaseCard
from ..tools.base import ToolRegistry
from .nodes import ChatLLM, build_initial_state, make_llm_node, make_route_node, route_after_llm
from .state import ReActGraphState


def build_react_graph(
    *,
    case_card: CaseCard,
    registry: ToolRegistry,
    llm: ChatLLM,
    max_steps: int = 8,
    verbose: bool = False,
):
    """
    LangGraph ReAct: llm → apply (tool/FINISH/ERROR) → llm … until FINISH or max_steps.

    Graph:
      START → llm → apply → (llm | END)
    """
    workflow: StateGraph = StateGraph(ReActGraphState)
    workflow.add_node("llm", make_llm_node(llm=llm, registry=registry, max_steps=max_steps, verbose=verbose))
    workflow.add_node("apply", make_route_node(case_card=case_card, registry=registry, max_steps=max_steps))

    workflow.set_entry_point("llm")
    workflow.add_edge("llm", "apply")
    workflow.add_conditional_edges(
        "apply",
        route_after_llm,
        {"llm": "llm", "end": END},
    )
    return workflow.compile()


def initial_state_for_case(
    case_card: CaseCard,
    registry: ToolRegistry,
    max_steps: int,
) -> ReActGraphState:
    return build_initial_state(case_card, registry, max_steps)
