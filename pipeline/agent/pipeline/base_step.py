"""Base class for deterministic pipeline steps."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..tools.base import ToolRegistry
    from .options import PipelineOptions
    from .state import CasePipelineState, StepRecord


@dataclass
class StepResult:
    observation: Dict[str, Any] = field(default_factory=dict)
    status: str = "completed"  # completed | skipped | failed | partial
    figure_paths: List[str] = field(default_factory=list)
    explanation: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    skip_remaining_vision: bool = False


class BasePipelineStep(ABC):
    step_number: int
    step_id: str
    agent_name: str
    tool_name: Optional[str] = None

    @abstractmethod
    def run(
        self,
        state: "CasePipelineState",
        registry: "ToolRegistry",
        options: "PipelineOptions",
    ) -> StepResult:
        ...

    def render(
        self,
        state: "CasePipelineState",
        result: StepResult,
        options: "PipelineOptions",
    ) -> List[str]:
        """Optional visualization; overridden when viz layer is available."""
        return []

    def execute_with_timing(
        self,
        state: "CasePipelineState",
        registry: "ToolRegistry",
        options: "PipelineOptions",
    ) -> "StepRecord":
        from .state import StepRecord

        t0 = time.time()
        try:
            result = self.run(state, registry, options)
        except Exception as exc:  # noqa: BLE001
            elapsed = time.time() - t0
            record = StepRecord(
                step=self.step_number,
                step_id=self.step_id,
                agent_name=self.agent_name,
                tool_name=self.tool_name,
                status="failed",
                observation={"available": False, "error": f"{type(exc).__name__}: {exc}"},
                elapsed_s=elapsed,
            )
            state.append_step(record)
            raise

        figure_paths = result.figure_paths
        if options.render_figures:
            try:
                rendered = self.render(state, result, options)
                figure_paths = list(dict.fromkeys(figure_paths + rendered))
            except Exception:
                pass

        elapsed = time.time() - t0
        record = StepRecord(
            step=self.step_number,
            step_id=self.step_id,
            agent_name=self.agent_name,
            tool_name=self.tool_name,
            status=result.status,
            observation=result.observation,
            elapsed_s=elapsed,
            figure_paths=figure_paths,
            explanation=result.explanation,
            inputs=result.inputs,
        )
        state.append_step(record)
        return record
