"""Per-step LLM for LangGraph case pipeline with full request/response tracing."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

import numpy as np

logger = logging.getLogger(__name__)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

STEP_DOCS: Dict[str, str] = {
    "triage": "病例接入：确认 case_id、输入模式、帧数与 GT。",
    "frame_extract": "视频关键帧：sample_video 选 4 帧供下游模型。",
    "quality": "质量门控：首帧 usable / quality_score。",
    "binary_gate": "L0 良恶性闸门：ConvNeXt-S 二分类，决定 skip_t 或 run_t。",
    "lumen_detect": "胃腔检测：YOLO11l lumen bbox。",
    "lesion_seg": "病灶分割：UNet + DINO auto 选 mask。",
    "morphology": "形态学：mask 几何特征。",
    "t_staging": "L1 T 分期：Dual ConvNeXt + Grad-CAM。",
    "wall_evidence": "壁层 SDF 穿透风险。",
    "dinov3_seg": "DINOv3 FM 分割对照。",
    "dino_sign_fusion": "DINOv3 表征与结构化 GC-US/胃壁征象证据融合。",
    "case_rag": "Case-RAG FAISS 相似病例。",
    "report_synth": "规则融合 + structure_report → 最终 T 推荐。",
}


class ChatLLM(Protocol):
    total_tokens: int

    def chat(self, messages: List[Dict[str, str]]) -> str: ...


@dataclass
class LLMCallRecord:
    step_id: str
    agent_name: str
    phase: str  # plan | interpret
    model: str
    provider: str
    messages: List[Dict[str, str]]
    response_text: str
    total_tokens: int = 0
    elapsed_s: float = 0.0
    status: str = "ok"
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "agent_name": self.agent_name,
            "phase": self.phase,
            "model": self.model,
            "provider": self.provider,
            "messages": self.messages,
            "response_text": self.response_text,
            "total_tokens": self.total_tokens,
            "elapsed_s": round(self.elapsed_s, 4),
            "status": self.status,
            "error": self.error,
        }


class TracingLLM:
    """Wrap any ChatLLM and append records to trace list."""

    def __init__(self, inner: ChatLLM, *, provider: str, model: str, trace: List[LLMCallRecord]):
        self._inner = inner
        self.provider = provider
        self.model = model
        self._trace = trace
        self._total_tokens = 0

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    def chat(self, messages: List[Dict[str, str]]) -> str:
        return self._inner.chat(messages)

    def traced_chat(
        self,
        *,
        step_id: str,
        agent_name: str,
        phase: str,
        messages: List[Dict[str, str]],
    ) -> str:
        t0 = time.time()
        status = "ok"
        error: Optional[str] = None
        response = ""
        try:
            response = self._inner.chat(messages)
            tok = getattr(self._inner, "total_tokens", 0)
            self._total_tokens = max(self._total_tokens, int(tok or 0))
        except Exception as exc:  # noqa: BLE001
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            response = f"[LLM error] {error}"
            logger.warning("Step LLM %s/%s failed: %s", step_id, phase, exc)

        rec = LLMCallRecord(
            step_id=step_id,
            agent_name=agent_name,
            phase=phase,
            model=self.model,
            provider=self.provider,
            messages=[dict(m) for m in messages],
            response_text=response,
            total_tokens=int(getattr(self._inner, "total_tokens", 0) or 0),
            elapsed_s=time.time() - t0,
            status=status,
            error=error,
        )
        self._trace.append(rec)
        return response


class StepNarrativeLLM:
    """Offline LLM: template narratives when no API key (always traceable)."""

    provider = "step_narrative_heuristic"
    model = "template-v1"
    total_tokens = 0

    def chat(self, messages: List[Dict[str, str]]) -> str:
        user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        try:
            payload = json.loads(user)
        except json.JSONDecodeError:
            payload = {"raw": user[:500]}
        step_id = str(payload.get("step_id", "?"))
        phase = str(payload.get("phase", "plan"))
        agent = str(payload.get("agent_name", step_id))
        if phase == "plan":
            return (
                f"【{agent} / 计划】{STEP_DOCS.get(step_id, '执行本步工具链。')}\n"
                f"输入摘要：{json.dumps(payload.get('inputs_summary', {}), ensure_ascii=False)[:400]}"
            )
        obs = payload.get("observation_summary") or {}
        return (
            f"【{agent} / 解读】status={payload.get('status', '?')} / "
            f"{json.dumps(obs, ensure_ascii=False)[:600]}"
        )


def resolve_pipeline_llm() -> tuple[ChatLLM, str, str]:
    """Default remains heuristic / API. Local Qwen is opt-in only."""
    mode = os.getenv("AGENT_LLM_MODE", "").strip().lower()
    # Assist fast path: keep per-step narratives local; final synthesis may still call DeepSeek.
    if mode in {
        "heuristic",
        "offline",
        "none",
        "assist_deepseek",
        "assist_flash",
        "synthesis_only",
    }:
        return StepNarrativeLLM(), "step_narrative_heuristic", StepNarrativeLLM.model

    if mode in {"local_qwen", "qwen_local", "local_mllm"}:
        from ...local_llm.qwen_tool_agent import build_local_tool_agent

        agent = build_local_tool_agent(smoke=os.getenv("LOCAL_QWEN_SMOKE", "0") in {"1", "true", "True"})
        return agent, agent.provider, agent.model

    if mode == "deepseek":
        from ...core.llm_client import AgentLLMClient

        client = AgentLLMClient(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL") or None,
            model=os.getenv("DEEPSEEK_MODEL") or os.getenv("AGENT_LLM_MODEL") or "deepseek-v4-flash",
            max_tokens=800,
            temperature=0.15,
            retries=2,
        )
        return client, "deepseek", client.model

    if os.getenv("MINIMAX_API_KEY") or os.getenv("MINIMAX_CN_API_KEY"):
        from ...core.minimax_llm_client import MiniMaxLLMClient

        c = MiniMaxLLMClient()
        return c, "minimax", c.model

    if any(os.getenv(k) for k in ("AGENT_API_KEY", "VLM_API_KEY", "POE_API_KEY", "OPENAI_API_KEY")):
        from ...core.llm_client import AgentLLMClient

        c = AgentLLMClient(max_tokens=800, temperature=0.15, retries=2)
        return c, "openai_compatible", c.model

    return StepNarrativeLLM(), "step_narrative_heuristic", StepNarrativeLLM.model


def build_step_messages(
    *,
    step_id: str,
    agent_name: str,
    phase: str,
    case_id: str,
    patient_id: str,
    inputs_summary: Dict[str, Any],
    observation_summary: Optional[Dict[str, Any]] = None,
    prior_steps: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    system = (
        f"You are {agent_name} in a gastric ultrasound T-staging agent pipeline. "
        f"Step: {step_id}. {STEP_DOCS.get(step_id, '')} "
        "Respond in concise Chinese (2-4 sentences). Do not invent tool outputs."
    )
    payload: Dict[str, Any] = {
        "step_id": step_id,
        "agent_name": agent_name,
        "phase": phase,
        "case_id": case_id,
        "patient_id": patient_id,
        "inputs_summary": inputs_summary,
        "prior_steps": (prior_steps or [])[-4:],
    }
    if phase == "interpret":
        payload["observation_summary"] = observation_summary or {}
        payload["status"] = (observation_summary or {}).get("status", "completed")
    user_json = json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default)
    if len(user_json) > 6000:
        user_json = user_json[:6000] + "\n…[truncated for context limit]"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_json},
    ]


def summarize_observation(obs: Dict[str, Any], max_keys: int = 8) -> Dict[str, Any]:
    """Compact observation for LLM context (avoid MiniMax context overflow)."""
    if not obs:
        return {}
    skip_keys = {"mask_array", "heatmap", "grad_cam", "runtime_invocation", "figure_paths", "_visuals"}
    slim = {k: v for k, v in obs.items() if k not in skip_keys}
    raw = json.loads(json.dumps(slim, default=_json_default, ensure_ascii=False))
    out: Dict[str, Any] = {}
    for k, v in list(raw.items())[:max_keys]:
        if isinstance(v, dict):
            out[k] = {sk: sv for sk, sv in list(v.items())[:4]}
        elif isinstance(v, list):
            if len(v) > 4:
                out[k] = v[:4]
            else:
                out[k] = v
        elif isinstance(v, str) and len(v) > 200:
            out[k] = v[:200] + "…"
        else:
            out[k] = v
    return out
