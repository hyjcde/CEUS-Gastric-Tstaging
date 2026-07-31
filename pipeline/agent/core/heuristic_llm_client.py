"""
Heuristic LLM client for the abdominal ultrasound Agent.

Provides a deterministic, rule-based "LLM" that emits the same
``Thought: ... Action: tool(...)`` text format that ``react_loop.parse_llm_output``
expects, but without calling any external API.

This is the **policy layer** of the Agent — it makes tool-selection
decisions visible, auditable, and reproducible. When ``AGENT_API_KEY``
becomes available the real ``AgentLLMClient`` can be swapped in
without touching the ReAct loop or the tool implementations.

Two-stage clinical workflow (2026-06-10):
  1. ``binary_classify`` on the first frame — gate_decision either
     ``skip_t`` (high-conf benign) or ``run_t`` (continue with L1)
  2. ``detect_lumen`` → ``segment`` → ``morphology`` → ``classify`` →
     ``wall_evidence`` → ``clinical_risk`` → ``retrieve_similar`` →
     ``structure_report`` → ``FINISH``

The policy can be overridden at construction time. ``observation_history``
is the only input the policy inspects, which makes the policy easy
to diff in the trajectory JSON.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


FINISH = "FINISH"


def _observation_text(messages: List[Dict[str, str]]) -> str:
    """Concatenate the most recent observation block from the message list."""
    for msg in reversed(messages):
        if msg.get("role") == "user" and "Observation" in msg.get("content", ""):
            return msg["content"]
    return ""


def _last_observation_dict(obs_text: str) -> Dict[str, Any]:
    """Parse the most recent JSON observation from an Observation block."""
    if not obs_text:
        return {}
    # The loop writes observations in the form:
    #   "Step N: tool_name → { ...json... }"
    # We look for the last balanced JSON object.
    candidates: List[str] = []
    depth = 0
    start = -1
    for i, ch in enumerate(obs_text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                candidates.append(obs_text[start:i + 1])
                start = -1
    for blob in reversed(candidates):
        try:
            return json.loads(blob)
        except json.JSONDecodeError:
            continue
    return {}


def _steps_completed(obs_text: str) -> List[str]:
    """Return the ordered list of tool names whose observations appear in obs_text."""
    pattern = re.compile(r"Step\s+\d+:\s+(\w+)\s+→")
    return pattern.findall(obs_text)


def _emit(text: str) -> str:
    """Wrap a Thought/Action payload in the format the parser expects."""
    return text.strip() + "\n"


class HeuristicLLMClient:
    """
    Deterministic LLM substitute that drives the ReAct loop with explicit
    policy decisions. Quacks like ``AgentLLMClient``.

    The policy is a small **state machine** indexed by ``_step_count`` — it
    does not rely on parsing the conversation history. This makes the
    decisions stable even when ``react_loop`` truncates the observation
    window to the last 6 entries.

    Two-stage clinical workflow (2026-06-10):
      Step 1: binary_classify
      Step 2: gate decision (skip_t or run_t)
      skip_t branch: structure_report → FINISH (3 steps)
      run_t branch:  detect_lumen → segment → morphology → classify
                    → wall_evidence → clinical_risk → retrieve_similar
                    → structure_report → FINISH (10 steps)
    """

    def __init__(self,
                 triage_mode: str = "conditional",
                 skip_t_threshold: float = 0.95,
                 max_steps: int = 12):
        if triage_mode not in ("conditional", "soft", "off"):
            raise ValueError(f"unknown triage_mode: {triage_mode}")
        self.triage_mode = triage_mode
        self.skip_t_threshold = float(skip_t_threshold)
        self.max_steps = int(max_steps)
        self._total_tokens = 0
        self._step_count = 0
        self._policy_log: List[Dict[str, Any]] = []
        self._gate_decision: Optional[str] = None  # set after step 1
        self._binary_top1_label: Optional[str] = None
        self._binary_top1_prob: Optional[float] = None
        self._classify_obs: Optional[Dict[str, Any]] = None

    # ── interface that matches AgentLLMClient ─────────────────────────
    def chat(self, messages: List[Dict[str, str]]) -> str:
        """Return the next Thought/Action payload."""
        obs_text = _observation_text(messages)
        last_obs = _last_observation_dict(obs_text)
        self._absorb_observation(last_obs)

        if self._step_count >= self.max_steps:
            self._record("max_steps_reached", obs_text, last_obs)
            return _emit(self._finish_text(last_obs, reason="max_steps_reached"))

        # Step 1: gate.
        if self._step_count == 0:
            self._step_count += 1
            action = (
                f"binary_classify(image_path=0, "
                f"gate_skip_t_threshold={self.skip_t_threshold})"
            )
            self._record("first_step", obs_text, last_obs, action=action)
            return _emit(
                "Thought: Two-stage triage policy: every case starts with the "
                "L0 binary gate so high-confidence benign cases short-circuit "
                "the more expensive T-staging chain.\n\n"
                f"Action: {action}"
            )

        # Step 2: read the gate result, set _gate_decision.
        if self._step_count == 1 and self._gate_decision is None:
            self._step_count += 1
            if self.triage_mode == "off":
                self._gate_decision = "run_t"
            elif self.triage_mode == "soft":
                self._gate_decision = "run_t"
            else:  # conditional
                if (last_obs.get("gate_decision") == "skip_t"
                        and (last_obs.get("top1_label") or "").lower() == "benign"):
                    self._gate_decision = "skip_t"
                else:
                    self._gate_decision = "run_t"
            self._record(
                f"gate:{self._gate_decision}",
                obs_text, last_obs,
                action=("structure_report(...)"
                        if self._gate_decision == "skip_t"
                        else "detect_lumen(image_path=0)"),
            )
            if self._gate_decision == "skip_t":
                top1 = self._binary_top1_label
                prob = self._binary_top1_prob
                return _emit(
                    f"Thought: Binary returned top1={top1} with P={prob} ≥ "
                    f"{self.skip_t_threshold}. Gate decision = skip_t. "
                    "Bypass the T-staging chain to save time and avoid "
                    "false T overcalls from inflammatory change.\n\n"
                    "Action: structure_report(report_payload={\"triage_path\":\"benign_skip\"})"
                )
            top1 = self._binary_top1_label
            prob = self._binary_top1_prob
            return _emit(
                f"Thought: Binary returned top1={top1} with P={prob} "
                f"(gate={last_obs.get('gate_decision')}). Gate decision = "
                "run_t — the L1 T-staging chain must run.\n\n"
                "Action: detect_lumen(image_path=0)"
            )

        # Step 3+: state-machine on _step_count.
        self._step_count += 1
        if self._gate_decision == "skip_t":
            # skip_t branch is binary → structure_report → FINISH.
            if self._step_count == 3:
                return _emit(
                    "Thought: All skip_t evidence collected. Issuing FINISH.\n\n"
                    + self._format_finish_action(
                        triage_path="benign_skip",
                        predicted="benign",
                        secondary="n/a",
                        confidence=self._confidence_from_binary(),
                        key=[
                            f"binary_classify: top1={self._binary_top1_label}",
                            f"binary_classify: P={self._binary_top1_prob}",
                            f"gate_decision=skip_t (threshold={self._skip_t_threshold()})",
                        ],
                        conflicting=[],
                    )
                )
            # fall through to max_steps guard
            return _emit(self._finish_text(last_obs, reason="skip_t_finish"))

        # run_t branch: step 3 onward is a fixed chain.
        run_t_chain = [
            (3,  "segment(image_path=0)",
                 "Predict the lesion mask — feeds both morphology and wall_evidence."),
            (4,  "morphology(image_path=0)",
                 "Compute shape/edge features from the predicted mask."),
            (5,  "classify(image_path=0)",
                 "Run the L1 T 4-class ConvNeXt on the first frame."),
            (6,  "wall_evidence(image_path=0)",
                 "Score wall penetration from lumen SDF + lesion mask."),
            (7,  "clinical_risk()",
                 "Cross-check with whitelisted clinical features; auto-injected."),
            (8,  "retrieve_similar(top_k=5, patient_id=__SELF__)",
                 "FAISS Case-RAG; auto-builds query vector from classify+morphology."),
            (9,  "structure_report(report_payload={\"triage_path\":\"malignant_run_t\"})",
                 "Compose a structured Chinese report from all evidence."),
            (10, None,  # FINISH
                 "All evidence collected. Issuing FINISH."),
        ]
        for step_n, action, why in run_t_chain:
            if self._step_count != step_n:
                continue
            if action is None:
                self._record(f"finish:run_t_step{step_n}", obs_text, last_obs)
                return _emit(self._finish_text(last_obs, reason="chain_complete"))
            self._record(f"chain:{action.split('(')[0]}", obs_text, last_obs, action=action)
            return _emit(f"Thought: {why}\n\nAction: {action}")

        # Should not reach here, but if max_steps > 10 in run_t, FINISH.
        return _emit(self._finish_text(last_obs, reason="fallthrough"))

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def policy_log(self) -> List[Dict[str, Any]]:
        return list(self._policy_log)

    # ── internals ─────────────────────────────────────────────────────
    def _absorb_observation(self, last_obs: Dict[str, Any]) -> None:
        """Stash observation fields we care about for the FINISH payload."""
        if not last_obs:
            return
        if "top1_label" in last_obs and last_obs.get("model_task") == "binary_gastritis":
            self._binary_top1_label = last_obs.get("top1_label")
            self._binary_top1_prob = last_obs.get("top1_prob")
        if "top1_stage" in last_obs and "uncertainty" in last_obs:
            self._classify_obs = last_obs

    def _skip_t_threshold(self) -> float:
        return float(self.skip_t_threshold)

    def _finish_text(self, last_obs: Dict[str, Any], *, reason: str) -> str:
        if self._gate_decision == "skip_t":
            key = [
                f"binary_classify: top1={self._binary_top1_label}",
                f"binary_classify: P={self._binary_top1_prob}",
                f"gate_decision=skip_t (threshold={self._skip_t_threshold()})",
            ]
            return self._format_finish_action(
                triage_path="benign_skip",
                predicted="benign",
                secondary="n/a",
                confidence=self._confidence_from_binary(),
                key=key,
                conflicting=[],
            )
        # run_t branch
        cls_obs = self._classify_obs or last_obs or {}
        predicted = cls_obs.get("top1_stage", "T3")
        secondary = cls_obs.get("top2_stage", "T2")
        confidence = self._confidence_from_classify(cls_obs)
        key = [
            f"classify: top1={predicted} (p={cls_obs.get('top1_prob')})",
            f"classify: top2={secondary} (p={cls_obs.get('top2_prob')})",
            f"classify: uncertainty={cls_obs.get('uncertainty')}",
        ]
        return self._format_finish_action(
            triage_path="malignant_run_t",
            predicted=predicted,
            secondary=secondary,
            confidence=confidence,
            key=key,
            conflicting=[],
        )

    def _format_finish_action(self, *, triage_path: str, predicted: str,
                              secondary: str, confidence: str,
                              key: List[str], conflicting: List[str]) -> str:
        key_with_triage = key + [f"triage_path={triage_path}"]
        key_json = json.dumps(key_with_triage, ensure_ascii=False)
        conflicting_json = json.dumps(conflicting, ensure_ascii=False)
        manual = "true" if confidence == "low" else "false"
        return (
            f"Action: FINISH("
            f"predicted_stage={predicted}, "
            f"secondary_candidate={secondary}, "
            f"confidence={confidence}, "
            f"key_evidence={key_json}, "
            f"conflicting_evidence={conflicting_json}, "
            f"manual_review_recommended={manual})"
        )

    def _confidence_from_binary(self) -> str:
        p = self._binary_top1_prob
        if p is None:
            return "low"
        if p >= 0.97:
            return "high"
        if p >= 0.85:
            return "medium"
        return "low"

    @staticmethod
    def _confidence_from_classify(obs: Dict[str, Any]) -> str:
        u = obs.get("uncertainty")
        p = obs.get("top1_prob")
        if u is None and p is None:
            return "low"
        if u is not None and u > 0.9:
            return "low"
        if p is not None and p >= 0.55 and (u is None or u < 0.7):
            return "high"
        if p is not None and p >= 0.4:
            return "medium"
        return "low"

    def _record(self, rule: str, obs_text: str,
                last_obs: Dict[str, Any], action: str = "") -> None:
        self._policy_log.append({
            "rule": rule,
            "step": self._step_count,
            "last_observation_keys": sorted(list((last_obs or {}).keys()))[:10],
            "emitted_action": action,
        })


# Alias for clarity: "Heuristic Agent" — i.e. the deterministic policy agent.
HeuristicAgentClient = HeuristicLLMClient
