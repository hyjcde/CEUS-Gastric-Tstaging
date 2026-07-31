"""LangGraph node factories for ReAct."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Protocol

from ..core.case_card import CaseCard
from ..core.prompts import INITIAL_USER_PROMPT, USER_TURN_TEMPLATE
from ..core.react_loop import (
    FINISH_ACTION,
    ReActStep,
    build_system_prompt,
    parse_llm_output,
)
from ..core.tool_executor import (
    execute_parsed_action,
    finish_step,
    parse_error_step,
    rejected_finish_step,
)
from ..tools.base import ToolRegistry
from .state import ReActGraphState

logger = logging.getLogger(__name__)


class ChatLLM(Protocol):
    def chat(self, messages: List[Dict[str, str]]) -> str: ...


def _merge_messages(
    existing: List[Dict[str, str]], new_msgs: List[Dict[str, str]]
) -> List[Dict[str, str]]:
    out = list(existing or [])
    out.extend(new_msgs)
    return out


def _to_chat_messages(messages: List[Any]) -> List[Dict[str, str]]:
    """Normalize LangGraph/LangChain message objects to OpenAI-style dicts."""
    out: List[Dict[str, str]] = []
    for m in messages or []:
        if isinstance(m, dict):
            out.append({"role": str(m.get("role", "user")), "content": str(m.get("content", ""))})
            continue
        role = getattr(m, "type", None) or getattr(m, "role", None)
        content = getattr(m, "content", "")
        if role in ("human", "user"):
            out.append({"role": "user", "content": str(content)})
        elif role in ("ai", "assistant"):
            out.append({"role": "assistant", "content": str(content)})
        elif role == "system":
            out.append({"role": "system", "content": str(content)})
        else:
            out.append({"role": "user", "content": str(content)})
    return out


def _steps_from_state(state: ReActGraphState) -> List[ReActStep]:
    out: List[ReActStep] = []
    for raw in state.get("steps") or []:
        out.append(
            ReActStep(
                step=int(raw.get("step", 0)),
                thought=str(raw.get("thought", "")),
                action_name=str(raw.get("action_name", "")),
                action_params=dict(raw.get("action_params") or {}),
                observation=dict(raw.get("observation") or {}),
                elapsed_s=float(raw.get("elapsed_s", 0)),
            )
        )
    return out


def _append_step(state: ReActGraphState, step: ReActStep) -> List[Dict[str, Any]]:
    steps = list(state.get("steps") or [])
    steps.append(
        {
            "step": step.step,
            "thought": step.thought,
            "action_name": step.action_name,
            "action_params": step.action_params,
            "observation": step.observation,
            "elapsed_s": step.elapsed_s,
        }
    )
    return steps


def make_llm_node(
    *,
    llm: ChatLLM,
    registry: ToolRegistry,
    max_steps: int,
    verbose: bool = False,
) -> Callable[[ReActGraphState], Dict[str, Any]]:
    def llm_node(state: ReActGraphState) -> Dict[str, Any]:
        step_idx = int(state.get("step_idx") or 0) + 1
        messages = _to_chat_messages(state.get("messages") or [])

        llm_text = llm.chat(messages)
        if verbose:
            logger.info("=== LangGraph step %d ===\n%s", step_idx, llm_text)

        thought, action_name, action_params = parse_llm_output(llm_text)
        return {
            "step_idx": step_idx,
            "last_llm_text": llm_text,
            "last_thought": thought,
            "last_action": action_name,
            "finish_params": action_params if action_name == FINISH_ACTION else action_params,
            "reject_finish": False,
            "messages": _merge_messages(messages, [{"role": "assistant", "content": llm_text}]),
        }

    return llm_node


def make_route_node(
    *,
    case_card: CaseCard,
    registry: ToolRegistry,
    max_steps: int,
) -> Callable[[ReActGraphState], Dict[str, Any]]:
    """Apply FINISH / ERROR / tool routing side-effects after LLM turn."""

    def route_node(state: ReActGraphState) -> Dict[str, Any]:
        step_idx = int(state.get("step_idx") or 0)
        thought = state.get("last_thought") or ""
        action_name = state.get("last_action") or "ERROR"
        action_params = dict(state.get("finish_params") or {})
        llm_text = state.get("last_llm_text") or ""
        patient_ctx = state.get("patient_ctx") or ""
        past = _steps_from_state(state)
        observation_history = list(state.get("observation_history") or [])
        updates: Dict[str, Any] = {}

        if action_name == FINISH_ACTION:
            has_tool_obs = any(
                s.action_name not in (FINISH_ACTION, "ERROR", "REJECTED_FINISH") for s in past
            )
            if not has_tool_obs:
                step = rejected_finish_step(step_idx, thought, action_params)
                updates["steps"] = _append_step(state, step)
                updates["reject_finish"] = True
                base_msgs = _to_chat_messages(state.get("messages") or [])
                updates["messages"] = _merge_messages(
                    base_msgs,
                    [{
                        "role": "user",
                        "content": (
                            "You cannot FINISH before calling any tools. "
                            "Please start with segment(image_path=0) to segment the first frame."
                        ),
                    }],
                )
                return updates

            updates["finished"] = True
            updates["predicted_stage"] = action_params.get("predicted_stage")
            updates["secondary_candidate"] = action_params.get("secondary_candidate")
            updates["confidence"] = action_params.get("confidence", "medium")
            updates["key_evidence"] = action_params.get("key_evidence", [])
            updates["conflicting_evidence"] = action_params.get("conflicting_evidence", [])
            updates["manual_review_recommended"] = action_params.get(
                "manual_review_recommended", False
            )
            updates["raw_finish"] = llm_text
            updates["steps"] = _append_step(
                state, finish_step(step_idx, thought, action_params)
            )
            return updates

        if action_name == "ERROR":
            step = parse_error_step(step_idx, thought, action_params)
            obs = step.observation
            observation_history.append(f"Step {step_idx}: [PARSE ERROR] {obs.get('error', '')}")
            updates["steps"] = _append_step(state, step)
            updates["observation_history"] = observation_history
            base_msgs = _to_chat_messages(state.get("messages") or [])
            updates["messages"] = _merge_messages(
                base_msgs,
                [{
                    "role": "user",
                    "content": (
                        f"Observation: {json.dumps(obs)}\n\n"
                        "Please try again with correct format."
                    ),
                }],
            )
            return updates

        step = execute_parsed_action(
            step_idx=step_idx,
            thought=thought,
            action_name=action_name,
            action_params=action_params,
            case_card=case_card,
            registry=registry,
            past_steps=past,
        )
        obs_str = json.dumps(step.observation, indent=2, default=str)
        observation_history.append(f"Step {step_idx}: {action_name} → {obs_str}")
        updates["steps"] = _append_step(state, step)
        updates["observation_history"] = observation_history
        base_msgs = _to_chat_messages(state.get("messages") or [])
        updates["messages"] = _merge_messages(
            base_msgs,
            [{
                "role": "user",
                "content": USER_TURN_TEMPLATE.format(
                    patient_context=patient_ctx,
                    observation_history="\n\n".join(observation_history[-6:]),
                ),
            }],
        )
        return updates

    return route_node


def route_after_llm(state: ReActGraphState) -> str:
    """Conditional edge: finish, retry LLM, or stop at max steps."""
    if state.get("finished"):
        return "end"
    step_idx = int(state.get("step_idx") or 0)
    max_steps = int(state.get("max_steps") or 8)
    if step_idx >= max_steps:
        return "end"
    if state.get("reject_finish"):
        return "llm"
    action = state.get("last_action") or ""
    if action == FINISH_ACTION:
        return "end"
    return "llm"


def build_initial_state(case_card: CaseCard, registry: ToolRegistry, max_steps: int) -> ReActGraphState:
    patient_ctx = json.dumps(case_card.to_agent_context(), indent=2)
    ctx_for_llm = json.loads(patient_ctx)
    frame_meta = [
        {
            "frame_index": i,
            "has_roi": f.roi_path is not None,
            "has_mask": f.predicted_mask_path is not None,
        }
        for i, f in enumerate(case_card.frames)
    ]
    ctx_for_llm["frames_available"] = frame_meta
    patient_ctx = json.dumps(ctx_for_llm, indent=2)

    system_msg = build_system_prompt(registry, max_steps)
    messages = [
        {"role": "system", "content": system_msg},
        {
            "role": "user",
            "content": INITIAL_USER_PROMPT.format(
                patient_context=patient_ctx,
                num_frames=case_card.num_frames,
            ),
        },
    ]
    return ReActGraphState(
        messages=messages,
        steps=[],
        step_idx=0,
        max_steps=max_steps,
        finished=False,
        patient_ctx=patient_ctx,
        observation_history=[],
        key_evidence=[],
        conflicting_evidence=[],
        manual_review_recommended=False,
    )
