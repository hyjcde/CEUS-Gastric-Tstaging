"""
ReAct main loop: Thought → Action → Observation cycle.

Orchestrates the LLM and ToolRegistry to reason over a CaseCard,
producing a final T-staging decision with supporting evidence.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .case_card import CaseCard
from .belief_state import build_case_belief_state
from .llm_client import AgentLLMClient
from .prompts import SYSTEM_PROMPT, INITIAL_USER_PROMPT, USER_TURN_TEMPLATE
from ..tools.base import ToolRegistry

logger = logging.getLogger(__name__)

MAX_STEPS = 8
FINISH_ACTION = "FINISH"


@dataclass
class ReActStep:
    """One step in the ReAct trace."""
    step: int
    thought: str
    action_name: str
    action_params: Dict[str, Any]
    observation: Dict[str, Any]
    elapsed_s: float = 0.0


@dataclass
class AgentResult:
    """Final output of the Agent for one patient."""
    patient_id: str
    predicted_stage: Optional[str] = None
    secondary_candidate: Optional[str] = None
    confidence: Optional[str] = None          # "high" | "medium" | "low"
    key_evidence: List[str] = field(default_factory=list)
    conflicting_evidence: List[str] = field(default_factory=list)
    manual_review_recommended: bool = False
    steps: List[ReActStep] = field(default_factory=list)
    total_tokens: int = 0
    total_time_s: float = 0.0
    raw_finish: str = ""
    belief_state: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patient_id": self.patient_id,
            "predicted_stage": self.predicted_stage,
            "secondary_candidate": self.secondary_candidate,
            "confidence": self.confidence,
            "key_evidence": self.key_evidence,
            "conflicting_evidence": self.conflicting_evidence,
            "manual_review_recommended": self.manual_review_recommended,
            "num_steps": len(self.steps),
            "total_tokens": self.total_tokens,
            "total_time_s": round(self.total_time_s, 2),
            "belief_state": self.belief_state,
        }


# ── Action parser ────────────────────────────────────────────────────

_ACTION_RE = re.compile(
    r"Action:\s*(\w+)\((.*)?\)\s*$",
    re.DOTALL | re.MULTILINE,
)

_FINISH_RE = re.compile(
    r"Action:\s*FINISH\((.*)\)\s*$",
    re.DOTALL | re.MULTILINE,
)

_THOUGHT_RE = re.compile(
    r"Thought:\s*(.*?)(?=\nAction:|\Z)",
    re.DOTALL,
)


def _parse_kv_args(raw: str) -> Dict[str, Any]:
    """Parse key=value arguments from an action call string."""
    params: Dict[str, Any] = {}
    if not raw or not raw.strip():
        return params

    # Handle list arguments like key_evidence=[...]
    # Split by comma, but respect brackets
    depth = 0
    current = ""
    parts = []
    for ch in raw:
        if ch in "([{":
            depth += 1
            current += ch
        elif ch in ")]}":
            depth -= 1
            current += ch
        elif ch == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())

    for part in parts:
        if "=" not in part:
            continue
        key, _, val = part.partition("=")
        key = key.strip()
        val = val.strip()

        # Try to parse as Python literal
        if val.lower() in ("true", "false"):
            params[key] = val.lower() == "true"
        elif val.startswith("[") and val.endswith("]"):
            try:
                # Simple list parse
                inner = val[1:-1]
                items = [s.strip().strip("'\"") for s in inner.split(",") if s.strip()]
                params[key] = items
            except Exception:
                params[key] = val
        elif val.startswith("{") and val.endswith("}"):
            try:
                params[key] = json.loads(val)
            except Exception:
                params[key] = val
        else:
            # Strip quotes
            val = val.strip("'\"")
            # Try numeric
            try:
                if "." in val:
                    params[key] = float(val)
                else:
                    params[key] = int(val)
            except (ValueError, TypeError):
                params[key] = val

    return params


def parse_llm_output(text: str) -> Tuple[str, str, Dict[str, Any]]:
    """
    Parse LLM output into (thought, action_name, action_params).

    When the LLM emits multiple Action lines in one response, we take
    the FIRST Action — this prevents premature FINISH when the model
    accidentally generates a full multi-step plan in a single turn.

    Returns ("", "ERROR", {}) if parsing fails.
    """
    # Extract thought (first one)
    thought_match = _THOUGHT_RE.search(text)
    thought = thought_match.group(1).strip() if thought_match else ""

    # Collect ALL Action: lines in order of appearance
    _ANY_ACTION_RE = re.compile(
        r"Action:\s*(\w+)\((.*)?\)\s*$", re.MULTILINE)
    all_actions = list(_ANY_ACTION_RE.finditer(text))

    if not all_actions:
        logger.warning("Could not parse action from LLM output:\n%s",
                        text[:500])
        return thought, "ERROR", {"raw": text[:300]}

    # Take the FIRST action, not the last
    first = all_actions[0]
    name = first.group(1)
    raw_params = first.group(2) or ""

    if name == "FINISH":
        params = _parse_kv_args(raw_params)
        return thought, FINISH_ACTION, params

    params = _parse_kv_args(raw_params)
    return thought, name, params


# ── Main loop ────────────────────────────────────────────────────────

def build_system_prompt(registry: ToolRegistry, max_steps: int = MAX_STEPS) -> str:
    return SYSTEM_PROMPT.format(
        tool_descriptions=registry.get_all_descriptions(),
        max_steps=max_steps,
    )


def run_react_loop(
    case_card: CaseCard,
    registry: ToolRegistry,
    llm: AgentLLMClient,
    max_steps: int = MAX_STEPS,
    verbose: bool = False,
) -> AgentResult:
    """
    Execute the full ReAct loop for one patient.

    1. Build system prompt with tool descriptions
    2. Send initial context
    3. Loop: LLM → parse → execute tool → append observation
    4. Stop on FINISH or max_steps
    """
    t0 = time.time()
    result = AgentResult(patient_id=case_card.patient_id)

    system_msg = build_system_prompt(registry, max_steps)
    patient_ctx = json.dumps(case_card.to_agent_context(), indent=2)

    # Frame paths are local references for tool calls, not sent to LLM
    frame_paths = [f.image_path for f in case_card.frames]
    frame_meta = [
        {"frame_index": i, "has_roi": f.roi_path is not None,
         "has_mask": f.predicted_mask_path is not None}
        for i, f in enumerate(case_card.frames)
    ]

    # Augment patient context with frame availability info
    ctx_for_llm = json.loads(patient_ctx)
    ctx_for_llm["frames_available"] = frame_meta
    patient_ctx = json.dumps(ctx_for_llm, indent=2)

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": INITIAL_USER_PROMPT.format(
            patient_context=patient_ctx,
            num_frames=case_card.num_frames,
        )},
    ]

    observation_history: List[str] = []

    for step_idx in range(1, max_steps + 1):
        # Get LLM response
        llm_text = llm.chat(messages)

        if verbose:
            logger.info("=== Step %d ===\n%s", step_idx, llm_text)

        thought, action_name, action_params = parse_llm_output(llm_text)

        # Handle FINISH — reject if no tools have been called yet
        if action_name == FINISH_ACTION:
            has_tool_obs = any(
                s.action_name not in (FINISH_ACTION, "ERROR")
                for s in result.steps
            )
            if not has_tool_obs:
                logger.warning(
                    "FINISH rejected at step %d — no tool observations yet. "
                    "Forcing re-try.", step_idx)
                messages.append({"role": "assistant", "content": llm_text})
                messages.append({"role": "user", "content":
                    "You cannot FINISH before calling any tools. "
                    "Please start with segment(image_path=0) "
                    "to segment the first frame."})
                result.steps.append(ReActStep(
                    step=step_idx, thought=thought,
                    action_name="REJECTED_FINISH",
                    action_params=action_params,
                    observation={"error": "FINISH rejected: no tools called yet"},
                ))
                continue

            result.predicted_stage = action_params.get("predicted_stage")
            result.secondary_candidate = action_params.get("secondary_candidate")
            result.confidence = action_params.get("confidence", "medium")
            result.key_evidence = action_params.get("key_evidence", [])
            result.conflicting_evidence = action_params.get("conflicting_evidence", [])
            result.manual_review_recommended = action_params.get(
                "manual_review_recommended", False)
            result.raw_finish = llm_text
            result.steps.append(ReActStep(
                step=step_idx, thought=thought,
                action_name=FINISH_ACTION, action_params=action_params,
                observation={"status": "finished"},
            ))
            break

        # Handle parse error
        if action_name == "ERROR":
            obs = {"error": "Could not parse your action. Use format: "
                   "Action: tool_name(param=value)"}
            observation_history.append(
                f"Step {step_idx}: [PARSE ERROR] {obs['error']}")
            messages.append({"role": "assistant", "content": llm_text})
            messages.append({"role": "user", "content":
                f"Observation: {json.dumps(obs)}\n\n"
                "Please try again with correct format."})
            result.steps.append(ReActStep(
                step=step_idx, thought=thought,
                action_name="ERROR", action_params=action_params,
                observation=obs,
            ))
            continue

        # Resolve frame references in params
        resolved_params = _resolve_frame_refs(
            action_params, case_card, past_steps=result.steps)

        # For clinical_risk: auto-inject CaseCard clinical fields so the
        # LLM only needs to call clinical_risk() without spelling out every
        # parameter — the tool gets the full clinical context automatically.
        if action_name == "clinical_risk" and case_card.clinical:
            clin_d = case_card.clinical.to_dict()
            for k, v in clin_d.items():
                if k not in resolved_params and v is not None:
                    resolved_params[k] = v

        # For classify: fix fabricated mask_path by checking file existence
        if action_name == "classify" and "mask_path" in resolved_params:
            mp = resolved_params["mask_path"]
            if mp is not None and not os.path.isfile(str(mp)):
                fidx = resolved_params.get("_frame_index", 0)
                if 0 <= fidx < len(case_card.frames):
                    real_mask = case_card.frames[fidx].predicted_mask_path
                    if real_mask and os.path.isfile(str(real_mask)):
                        resolved_params["mask_path"] = real_mask
                    else:
                        seg_tool = registry.get("segment")
                        if seg_tool and hasattr(seg_tool, "get_cached_mask"):
                            img_path = case_card.frames[fidx].image_path
                            cached = seg_tool.get_cached_mask(img_path)
                            if cached is not None:
                                import tempfile
                                from PIL import Image
                                tmp = tempfile.NamedTemporaryFile(
                                    suffix=".png", delete=False, prefix="seg_mask_")
                                Image.fromarray((cached * 255).astype(np.uint8)).save(
                                    tmp.name)
                                resolved_params["mask_path"] = tmp.name
                                logger.debug("Saved cached mask to %s for classify",
                                             tmp.name)
                            else:
                                resolved_params.pop("mask_path", None)
                                resolved_params.pop("roi_bbox", None)

        # For morphology: try to supply mask from seg cache if missing/invalid
        if action_name == "morphology" and "mask_array" not in resolved_params:
            mp = resolved_params.get("mask_path")
            need_cache = (mp is None
                          or not (isinstance(mp, str) and os.path.isfile(mp)))
            if need_cache:
                fidx = resolved_params.get("_frame_index")
                if fidx is None:
                    raw_ref = action_params.get("mask_path",
                                                action_params.get("image_path"))
                    if raw_ref is not None:
                        fidx = _extract_frame_index(raw_ref,
                                                    len(case_card.frames))
                if fidx is None:
                    fidx = 0
                if 0 <= fidx < len(case_card.frames):
                    img_path = case_card.frames[fidx].image_path
                    seg_tool = registry.get("segment")
                    if seg_tool and hasattr(seg_tool, "get_cached_mask"):
                        cached = seg_tool.get_cached_mask(img_path)
                        if cached is not None:
                            resolved_params.pop("mask_path", None)
                            resolved_params["mask_array"] = cached
                            logger.debug("Injected cached mask for frame %d "
                                         "into morphology call", fidx)

        # For wall_evidence: inject lumen_bbox + lesion_mask from prior steps
        if action_name == "wall_evidence":
            _inject_wall_evidence_params(
                resolved_params, result.steps, case_card, registry)

        # Execute tool
        t_tool = time.time()
        _clean_params = {k: v for k, v in resolved_params.items()
                         if not k.startswith("_")}
        obs = registry.execute(action_name, **_clean_params)
        tool_elapsed = time.time() - t_tool

        step = ReActStep(
            step=step_idx, thought=thought,
            action_name=action_name, action_params=action_params,
            observation=obs, elapsed_s=round(tool_elapsed, 3),
        )
        result.steps.append(step)

        # Build observation string for conversation
        obs_str = json.dumps(obs, indent=2, default=str)
        obs_entry = f"Step {step_idx}: {action_name} → {obs_str}"
        observation_history.append(obs_entry)

        # Append to conversation
        messages.append({"role": "assistant", "content": llm_text})
        messages.append({"role": "user", "content":
            USER_TURN_TEMPLATE.format(
                patient_context=patient_ctx,
                observation_history="\n\n".join(observation_history[-6:]),
            )
        })
    else:
        # Exhausted max steps without FINISH — force a decision
        result.confidence = "low"
        result.manual_review_recommended = True
        if not result.predicted_stage:
            result.predicted_stage = _infer_from_observations(result.steps)

    result.total_tokens = llm.total_tokens
    result.total_time_s = time.time() - t0
    result.belief_state = build_case_belief_state(
        case_id=case_card.patient_id,
        patient_id=case_card.patient_id,
        steps=result.steps,
        frame_count=case_card.num_frames,
        run_id=f"react_{case_card.patient_id}_{int(t0)}",
        final_report=result.to_dict(),
    ).to_dict()

    return result


def _inject_wall_evidence_params(
    resolved_params: Dict[str, Any],
    past_steps: List["ReActStep"],
    case_card: CaseCard,
    registry: ToolRegistry,
) -> None:
    """Pass lumen bbox and lesion mask from prior detect_lumen/segment steps."""
    if "image_path" not in resolved_params:
        fidx = resolved_params.get("_frame_index", 0)
        if 0 <= fidx < len(case_card.frames):
            resolved_params["image_path"] = case_card.frames[fidx].image_path

    if "lumen_bbox" not in resolved_params:
        for step in reversed(past_steps):
            if step.action_name == "detect_lumen" and step.observation.get("lumen_bbox"):
                resolved_params["lumen_bbox"] = dict(step.observation["lumen_bbox"])
                break

    if "lesion_mask" not in resolved_params:
        fidx = resolved_params.get("_frame_index", 0)
        if fidx is None:
            fidx = 0
        if 0 <= fidx < len(case_card.frames):
            img_path = case_card.frames[fidx].image_path
            seg_tool = registry.get("segment")
            if seg_tool and hasattr(seg_tool, "get_cached_mask"):
                cached = seg_tool.get_cached_mask(img_path)
                if cached is not None:
                    resolved_params["lesion_mask"] = cached
                    return
        for step in reversed(past_steps):
            if step.action_name == "segment" and step.observation.get("mask_available"):
                fidx2 = resolved_params.get("_frame_index", 0) or 0
                if 0 <= fidx2 < len(case_card.frames):
                    img_path = case_card.frames[fidx2].image_path
                    seg_tool = registry.get("segment")
                    if seg_tool and hasattr(seg_tool, "get_cached_mask"):
                        cached = seg_tool.get_cached_mask(img_path)
                        if cached is not None:
                            resolved_params["lesion_mask"] = cached
                break


def _extract_frame_index(val: Any, n_frames: int) -> Optional[int]:
    """
    Try to extract a valid frame index from a value the LLM provided.

    Handles: int, "0", "frame_0", "/data/patient_123/frame_2.png", etc.
    """
    if isinstance(val, int):
        if 0 <= val < n_frames:
            return val
        return None
    if not isinstance(val, str):
        return None

    # Pure digit
    stripped = val.strip().strip("'\"")
    if stripped.isdigit():
        idx = int(stripped)
        return idx if 0 <= idx < n_frames else None

    # Try to extract a trailing integer from patterns like "frame_2" or
    # "/data/patient_123/frame_0.png"
    import re
    m = re.search(r'(?:frame[_\s]*)(\d+)', stripped, re.IGNORECASE)
    if m:
        idx = int(m.group(1))
        return idx if 0 <= idx < n_frames else None

    # Last resort: any standalone single digit in the string
    digits = re.findall(r'\b(\d)\b', stripped)
    if len(digits) == 1:
        idx = int(digits[0])
        return idx if 0 <= idx < n_frames else None

    return None


def _resolve_frame_refs(params: Dict[str, Any],
                        case_card: CaseCard,
                        past_steps: Optional[List[ReActStep]] = None,
                        ) -> Dict[str, Any]:
    """
    Resolve frame_index references to actual file paths for tool execution.

    The LLM references frames by index; we map those to real paths locally.
    For retrieve_similar, auto-builds query_vector from past observations.
    """
    resolved = dict(params)
    n = len(case_card.frames)

    # Resolve image_path
    if "image_path" in resolved:
        idx = _extract_frame_index(resolved["image_path"], n)
        if idx is not None:
            frame = case_card.frames[idx]
            resolved["image_path"] = frame.image_path
            resolved["_frame_index"] = idx
            if "mask_path" not in resolved and frame.predicted_mask_path:
                resolved["mask_path"] = frame.predicted_mask_path
            if "roi_path" not in resolved and frame.roi_path:
                resolved["roi_path"] = frame.roi_path
        else:
            # If it's not an existing file, try to resolve as-is
            import os
            if not os.path.isfile(str(resolved["image_path"])):
                # Default to frame 0 if we can't resolve
                if n > 0:
                    frame = case_card.frames[0]
                    resolved["image_path"] = frame.image_path
                    resolved["_frame_index"] = 0
                    if "mask_path" not in resolved and frame.predicted_mask_path:
                        resolved["mask_path"] = frame.predicted_mask_path
                    if "roi_path" not in resolved and frame.roi_path:
                        resolved["roi_path"] = frame.roi_path

    # Resolve mask_path
    if "mask_path" in resolved:
        idx = _extract_frame_index(resolved["mask_path"], n)
        if idx is not None:
            resolved["mask_path"] = case_card.frames[idx].predicted_mask_path

    # Auto-build query_vector for retrieve_similar from past observations
    if ("query_vector" not in resolved or not resolved["query_vector"]) and past_steps:
        vec = _build_query_vector_from_steps(past_steps, case_card)
        if vec is not None:
            resolved["query_vector"] = vec.tolist()

    return resolved


def _build_query_vector_from_steps(
    steps: List[ReActStep],
    case_card: CaseCard,
) -> Optional["np.ndarray"]:
    """Build a 17-dim query vector from accumulated ReAct observations."""
    try:
        from ..memory.feature_extractor import extract_patient_vector
    except ImportError:
        return None

    cls_results = [s.observation for s in steps
                    if s.action_name == "classify" and "probabilities" in s.observation]
    morph_results = [s.observation for s in steps
                      if s.action_name == "morphology" and s.observation.get("valid")]

    if not cls_results:
        return None

    clin_dict = case_card.clinical.to_dict() if case_card.clinical else None
    return extract_patient_vector(cls_results, morph_results, clin_dict)


def _infer_from_observations(steps: List[ReActStep]) -> Optional[str]:
    """
    Last-resort inference when LLM didn't produce FINISH.

    Looks through tool observations for classification results and
    picks the most common top1_stage.
    """
    stage_votes: Dict[str, int] = {}
    for step in steps:
        if step.action_name == "classify":
            obs = step.observation
            stage = obs.get("top1_stage")
            if stage:
                stage_votes[stage] = stage_votes.get(stage, 0) + 1

    if stage_votes:
        return max(stage_votes, key=stage_votes.get)
    return None
