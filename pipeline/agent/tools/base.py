"""
BaseTool abstract class and ToolRegistry for the abdominal ultrasound Agent.

Every perception / retrieval tool inherits from BaseTool and registers
itself via ToolRegistry. The registry produces tool descriptions for
the LLM system prompt and dispatches Action calls to the right tool.
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolParameter:
    """Describes one parameter accepted by a tool."""
    name: str
    type: str           # "str", "int", "float", "bool", "list"
    description: str
    required: bool = True
    default: Any = None


class BaseTool(ABC):
    """
    Abstract base for all agent tools.

    Subclasses must define:
      - name: unique identifier used in Action calls
      - description: one-line summary shown to the LLM
      - parameters: list of ToolParameter
      - execute(**kwargs) -> dict: run the tool and return structured result
    """

    name: str = ""
    description: str = ""
    parameters: List[ToolParameter] = []

    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        """Run the tool. All heavy computation happens here (locally)."""
        ...

    def get_schema(self) -> Dict[str, Any]:
        """Machine-readable schema for this tool."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                }
                for p in self.parameters
            ],
        }

    def get_description_for_llm(self) -> str:
        """Human-readable description suitable for a system prompt."""
        param_lines = []
        for p in self.parameters:
            req = "required" if p.required else "optional"
            param_lines.append(f"    - {p.name} ({p.type}, {req}): {p.description}")
        params_str = "\n".join(param_lines) if param_lines else "    (no parameters)"
        return (
            f"Tool: {self.name}\n"
            f"  Description: {self.description}\n"
            f"  Parameters:\n{params_str}"
        )


class ToolRegistry:
    """
    Central registry that holds all available tools.

    Responsibilities:
      1. Register tools by name
      2. Generate combined tool descriptions for the LLM system prompt
      3. Dispatch Action calls to the correct tool
      4. Record execution traces for analysis
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._traces: List[Dict[str, Any]] = []

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            logger.warning("Overwriting tool '%s'", tool.name)
        self._tools[tool.name] = tool
        logger.info("Registered tool: %s", tool.name)

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    @property
    def tool_names(self) -> List[str]:
        return list(self._tools.keys())

    def get_all_descriptions(self) -> str:
        """Concatenated tool descriptions for the system prompt."""
        return "\n\n".join(
            t.get_description_for_llm() for t in self._tools.values()
        )

    def execute(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """
        Dispatch an Action to the named tool and return its Observation.

        Returns an error dict if the tool is unknown or throws.
        Every observation is enriched with evidence_id / provenance fields.
        """
        from ..multimodal.provenance import ensure_observation_provenance

        tool = self._tools.get(tool_name)
        patient_id = str(kwargs.get("patient_id") or "")
        sample_id = str(kwargs.get("sample_id") or "")
        frame_id = kwargs.get("frame_id")
        time_bucket = kwargs.get("time_bucket")
        source_refs = kwargs.get("source_refs")
        if source_refs is not None and not isinstance(source_refs, list):
            source_refs = [str(source_refs)]

        if tool is None:
            err = {"error": f"Unknown tool: {tool_name}",
                   "available": self.tool_names}
            err = ensure_observation_provenance(
                err,
                tool_name=tool_name,
                patient_id=patient_id,
                sample_id=sample_id,
                frame_id=frame_id,
                time_bucket=time_bucket,
                source_refs=source_refs,
            )
            self._traces.append({"tool": tool_name, "kwargs": kwargs,
                                 "result": err, "status": "error"})
            return err

        t0 = time.time()
        try:
            result = tool.execute(**kwargs)
            elapsed = time.time() - t0
            if not isinstance(result, dict):
                result = {"value": result}
            result = ensure_observation_provenance(
                result,
                tool_name=tool_name,
                patient_id=patient_id,
                sample_id=sample_id,
                frame_id=frame_id,
                time_bucket=time_bucket,
                source_refs=source_refs,
            )
            self._traces.append({
                "tool": tool_name,
                "kwargs": {k: str(v)[:200] for k, v in kwargs.items()},
                "result_keys": list(result.keys()),
                "evidence_id": result.get("evidence_id"),
                "elapsed_s": round(elapsed, 3),
                "status": "ok",
            })
            return result
        except Exception as exc:
            elapsed = time.time() - t0
            err = {"error": f"{type(exc).__name__}: {exc}"}
            err = ensure_observation_provenance(
                err,
                tool_name=tool_name,
                patient_id=patient_id,
                sample_id=sample_id,
                frame_id=frame_id,
                time_bucket=time_bucket,
                source_refs=source_refs,
            )
            self._traces.append({
                "tool": tool_name,
                "kwargs": {k: str(v)[:200] for k, v in kwargs.items()},
                "error": str(exc),
                "evidence_id": err.get("evidence_id"),
                "elapsed_s": round(elapsed, 3),
                "status": "error",
            })
            logger.exception("Tool '%s' failed", tool_name)
            return err

    @property
    def traces(self) -> List[Dict[str, Any]]:
        return list(self._traces)

    def clear_traces(self) -> None:
        self._traces.clear()
