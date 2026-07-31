"""LangGraph ReAct entry — returns same AgentResult as legacy run_react_loop."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from ..core.case_card import CaseCard
from ..core.react_loop import AgentResult, ReActStep, _infer_from_observations
from ..tools.base import ToolRegistry
from .graph import build_react_graph, initial_state_for_case
from .nodes import ChatLLM

logger = logging.getLogger(__name__)


def _steps_from_raw(raw_steps: List[Dict[str, Any]]) -> List[ReActStep]:
    return [
        ReActStep(
            step=int(s.get("step", 0)),
            thought=str(s.get("thought", "")),
            action_name=str(s.get("action_name", "")),
            action_params=dict(s.get("action_params") or {}),
            observation=dict(s.get("observation") or {}),
            elapsed_s=float(s.get("elapsed_s", 0)),
        )
        for s in raw_steps
    ]


def run_langgraph_react_loop(
    case_card: CaseCard,
    registry: ToolRegistry,
    llm: ChatLLM,
    max_steps: int = 8,
    verbose: bool = False,
) -> AgentResult:
    """
    Execute ReAct via LangGraph StateGraph.

    Drop-in alternative to ``run_react_loop`` with identical AgentResult contract.
    """
    t0 = time.time()
    graph = build_react_graph(
        case_card=case_card,
        registry=registry,
        llm=llm,
        max_steps=max_steps,
        verbose=verbose,
    )
    init = initial_state_for_case(case_card, registry, max_steps)
    final = graph.invoke(init)

    result = AgentResult(patient_id=case_card.patient_id)
    result.steps = _steps_from_raw(final.get("steps") or [])
    result.predicted_stage = final.get("predicted_stage")
    result.secondary_candidate = final.get("secondary_candidate")
    result.confidence = final.get("confidence")
    result.key_evidence = list(final.get("key_evidence") or [])
    result.conflicting_evidence = list(final.get("conflicting_evidence") or [])
    result.manual_review_recommended = bool(final.get("manual_review_recommended"))
    result.raw_finish = str(final.get("raw_finish") or "")

    if not final.get("finished"):
        result.confidence = result.confidence or "low"
        result.manual_review_recommended = True
        if not result.predicted_stage:
            result.predicted_stage = _infer_from_observations(result.steps)

    result.total_tokens = getattr(llm, "total_tokens", 0)
    result.total_time_s = time.time() - t0
    return result
