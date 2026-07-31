"""Shared ReAct tool execution (legacy loop + LangGraph)."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import numpy as np

from .react_loop import (
    FINISH_ACTION,
    ReActStep,
    _inject_wall_evidence_params,
    _resolve_frame_refs,
)

if TYPE_CHECKING:
    from .case_card import CaseCard
    from ..tools.base import ToolRegistry

logger = logging.getLogger(__name__)


def execute_parsed_action(
    *,
    step_idx: int,
    thought: str,
    action_name: str,
    action_params: Dict[str, Any],
    case_card: "CaseCard",
    registry: "ToolRegistry",
    past_steps: List[ReActStep],
) -> ReActStep:
    """Execute one parsed LLM tool action; shared by legacy ReAct and LangGraph."""
    resolved_params = _resolve_frame_refs(action_params, case_card, past_steps=past_steps)

    if action_name == "clinical_risk" and case_card.clinical:
        clin_d = case_card.clinical.to_dict()
        for k, v in clin_d.items():
            if k not in resolved_params and v is not None:
                resolved_params[k] = v

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
                                suffix=".png", delete=False, prefix="seg_mask_"
                            )
                            Image.fromarray((cached * 255).astype(np.uint8)).save(tmp.name)
                            resolved_params["mask_path"] = tmp.name
                        else:
                            resolved_params.pop("mask_path", None)
                            resolved_params.pop("roi_bbox", None)

    if action_name == "morphology" and "mask_array" not in resolved_params:
        mp = resolved_params.get("mask_path")
        need_cache = mp is None or not (isinstance(mp, str) and os.path.isfile(mp))
        if need_cache:
            from .react_loop import _extract_frame_index

            fidx = resolved_params.get("_frame_index")
            if fidx is None:
                raw_ref = action_params.get("mask_path", action_params.get("image_path"))
                if raw_ref is not None:
                    fidx = _extract_frame_index(raw_ref, len(case_card.frames))
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

    if action_name == "wall_evidence":
        _inject_wall_evidence_params(resolved_params, past_steps, case_card, registry)

    t_tool = time.time()
    clean_params = {k: v for k, v in resolved_params.items() if not k.startswith("_")}
    obs = registry.execute(action_name, **clean_params)
    tool_elapsed = time.time() - t_tool

    return ReActStep(
        step=step_idx,
        thought=thought,
        action_name=action_name,
        action_params=action_params,
        observation=obs,
        elapsed_s=round(tool_elapsed, 3),
    )


def parse_error_step(step_idx: int, thought: str, action_params: Dict[str, Any]) -> ReActStep:
    return ReActStep(
        step=step_idx,
        thought=thought,
        action_name="ERROR",
        action_params=action_params,
        observation={
            "error": "Could not parse your action. Use format: Action: tool_name(param=value)"
        },
    )


def rejected_finish_step(
    step_idx: int, thought: str, action_params: Dict[str, Any]
) -> ReActStep:
    return ReActStep(
        step=step_idx,
        thought=thought,
        action_name="REJECTED_FINISH",
        action_params=action_params,
        observation={"error": "FINISH rejected: no tools called yet"},
    )


def finish_step(step_idx: int, thought: str, action_params: Dict[str, Any]) -> ReActStep:
    return ReActStep(
        step=step_idx,
        thought=thought,
        action_name=FINISH_ACTION,
        action_params=action_params,
        observation={"status": "finished"},
    )
