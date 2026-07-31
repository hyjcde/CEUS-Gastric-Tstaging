"""LangGraph ReAct state schema."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class ReActGraphState(TypedDict, total=False):
    """Mutable state passed between LangGraph nodes."""

    messages: List[Dict[str, str]]
    steps: List[Dict[str, Any]]
    step_idx: int
    max_steps: int
    finished: bool
    patient_ctx: str
    observation_history: List[str]
    last_llm_text: str
    last_thought: str
    last_action: str
    finish_params: Dict[str, Any]
    reject_finish: bool
    predicted_stage: Optional[str]
    secondary_candidate: Optional[str]
    confidence: Optional[str]
    key_evidence: List[str]
    conflicting_evidence: List[str]
    manual_review_recommended: bool
    raw_finish: str
