"""Shared mutable state for the deterministic case pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from .case_input import CaseInput


def sanitize_observation(obs: Dict[str, Any]) -> Dict[str, Any]:
    """Strip non-serializable / bulky fields before writing pipeline_state.json."""
    if not obs:
        return {}
    clean = dict(obs)
    visuals = clean.pop("_visuals", None)
    if visuals:
        clean["_visuals"] = {
            "_note": "arrays omitted from JSON; see step figures",
            "keys": list(visuals.keys()) if isinstance(visuals, dict) else ["<blob>"],
        }
    return clean


def _json_default(obj: Any) -> Any:
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


@dataclass
class StepRecord:
    step: int
    step_id: str
    agent_name: str
    tool_name: Optional[str]
    status: str  # completed | skipped | failed | partial
    observation: Dict[str, Any] = field(default_factory=dict)
    elapsed_s: float = 0.0
    figure_paths: List[str] = field(default_factory=list)
    explanation: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    llm_calls: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "step_id": self.step_id,
            "agent_name": self.agent_name,
            "tool_name": self.tool_name,
            "status": self.status,
            "observation": sanitize_observation(self.observation),
            "elapsed_s": round(self.elapsed_s, 4),
            "figure_paths": self.figure_paths,
            "explanation": self.explanation,
            "inputs": self.inputs,
            "llm_calls": self.llm_calls,
        }


@dataclass
class CasePipelineState:
    case_input: CaseInput
    out_dir: Path
    triage_path: Optional[str] = None  # skip_t | run_t
    gate_decision: Optional[str] = None
    lumen_bbox: Optional[Dict[str, int]] = None
    lesion_mask: Optional[np.ndarray] = None
    lesion_roi_bbox: Optional[Dict[str, int]] = None
    primary_classification: Optional[Dict[str, Any]] = None
    per_frame_classifications: List[Dict[str, Any]] = field(default_factory=list)
    per_frame_binary: List[Dict[str, Any]] = field(default_factory=list)
    steps: List[StepRecord] = field(default_factory=list)
    final_report: Optional[Dict[str, Any]] = None
    memory_context: Optional[Dict[str, Any]] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    @property
    def steps_dir(self) -> Path:
        return self.out_dir / "steps"

    @property
    def figures_dir(self) -> Path:
        return self.out_dir / "figures"

    def append_step(self, record: StepRecord) -> None:
        self.steps.append(record)
        self.steps_dir.mkdir(parents=True, exist_ok=True)
        path = self.steps_dir / f"step-{record.step:02d}-{record.step_id}.json"
        path.write_text(
            json.dumps(record.to_dict(), indent=2, ensure_ascii=False, default=_json_default),
            encoding="utf-8",
        )

    def save_summary(self, *, options: Optional[Dict[str, Any]] = None) -> Path:
        payload = {
            "case_id": self.case_input.case_id,
            "patient_id": self.case_input.patient_id,
            "input_mode": self.case_input.input_mode.value,
            "triage_path": self.triage_path,
            "gate_decision": self.gate_decision,
            "gt_t_stage": self.case_input.gt_t_stage,
            "final_report": self.final_report,
            "created_at": self.created_at,
            "steps": [s.to_dict() for s in self.steps],
        }
        path = self.out_dir / "pipeline_state.json"
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default),
            encoding="utf-8",
        )
        audit = {
            "case_id": self.case_input.case_id,
            "created_at": self.created_at,
            "options": options or {},
            "orchestrator": (options or {}).get("orchestrator", "langgraph_case_pipeline"),
            "agent_calls": [s.to_dict() for s in self.steps],
        }
        audit_path = self.out_dir / "agent_audit.json"
        audit_path.write_text(
            json.dumps(audit, indent=2, ensure_ascii=False, default=_json_default),
            encoding="utf-8",
        )
        try:
            from ..visualization.execution_trace import build_execution_trace

            trace = build_execution_trace([s.to_dict() for s in self.steps])
            (self.out_dir / "execution_trace.json").write_text(
                json.dumps(trace, indent=2, ensure_ascii=False, default=_json_default),
                encoding="utf-8",
            )
        except Exception:
            pass
        return path
