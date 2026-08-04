"""LangGraph case pipeline runtime context (shared across nodes)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ...pipeline.options import PipelineOptions
from ...pipeline.state import CasePipelineState, StepRecord
from ...tools.base import ToolRegistry
from .step_llm import LLMCallRecord, TracingLLM


@dataclass
class PipelineContext:
    pipeline_state: CasePipelineState
    registry: ToolRegistry
    options: PipelineOptions
    llm: TracingLLM
    llm_trace: List[LLMCallRecord] = field(default_factory=list)
    stream_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None

    def prior_step_labels(self) -> List[str]:
        return [
            f"{s.step_id}:{s.status}"
            for s in self.pipeline_state.steps
        ]

    def should_skip_vision_step(self, step_id: str) -> bool:
        if step_id in (
            "triage",
            "frame_extract",
            "quality",
            "binary_gate",
            "report_synth",
            "clinical_decision",
            "dinov3_seg",
            "dino_sign_fusion",
        ):
            return False
        if self.options.triage_mode == "soft":
            return False
        return self.pipeline_state.gate_decision == "skip_t"
