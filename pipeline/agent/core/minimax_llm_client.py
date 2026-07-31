"""
MiniMax M3 LLM client for the abdominal ultrasound Agent.

Wraps the MiniMax-M3 chat-completions endpoint (OpenAI-compatible) and
adapts the response so the existing ReAct parser can consume it.

Key adaptations vs ``AgentLLMClient``:
  1. Default base_url is ``https://api.minimaxi.com/v1`` (configurable
     via ``MINIMAX_BASE_URL`` env var).
  2. Default model is ``MiniMax-M3`` (configurable via
     ``MINIMAX_MODEL`` env var).
  3. Strips ``<think>...</think>`` reasoning blocks that MiniMax models
     emit before the final answer. The parser expects the canonical
     ``Thought: ...`` / ``Action: tool(...)`` format.
  4. Tracks the raw and stripped token counts so trace JSON can show
     how much reasoning the model produced.

Configuration env vars (override defaults at runtime):
  - ``MINIMAX_API_KEY``  : API key (required)
  - ``MINIMAX_BASE_URL`` : default ``https://api.minimaxi.com/v1``
  - ``MINIMAX_MODEL``    : default ``MiniMax-M3``

Usage:
  >>> from agent.core.minimax_llm_client import MiniMaxLLMClient
  >>> client = MiniMaxLLMClient()
  >>> text = client.chat(messages)
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Dict, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


DEFAULT_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
DEFAULT_MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-M3")
DEFAULT_MAX_TOKENS = 2048
DEFAULT_TEMPERATURE = 0.1

# MiniMax-only env vars — do NOT fall back to POE/OPENAI keys (causes 401 on CN API).
_KEY_ENV_VARS = (
    "MINIMAX_API_KEY",
    "MINIMAX_CN_API_KEY",
    "MINIMAX_CODE_PLAN_KEY",
    "MINIMAX_CODING_API_KEY",
    "MINIMAX_OAUTH_TOKEN",
)

_CN_BASE_URL = "https://api.minimaxi.com/v1"
_GLOBAL_BASE_URL = "https://api.minimax.io/v1"


def _normalize_api_key(raw: str) -> str:
    key = (raw or "").strip().strip('"').strip("'")
    if not key or key.lower().startswith("your-"):
        return ""
    return key


def resolve_minimax_api_key() -> tuple[str, str]:
    """Return (api_key, source_env_var) or raise RuntimeError."""
    for var in _KEY_ENV_VARS:
        val = _normalize_api_key(os.getenv(var, ""))
        if val:
            return val, var
    raise RuntimeError(
        "Missing MiniMax API key. Set MINIMAX_API_KEY or MINIMAX_CN_API_KEY "
        f"(repo .env or export). Accepted vars: {', '.join(_KEY_ENV_VARS)}"
    )


def resolve_minimax_base_url(api_key: str) -> str:
    explicit = os.getenv("MINIMAX_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    # Coding-plan / CN keys (sk-cp-*) must use api.minimaxi.com, not api.minimax.io.
    if api_key.startswith("sk-cp-"):
        return _CN_BASE_URL
    return os.getenv("MINIMAX_CN_BASE_URL", _CN_BASE_URL).rstrip("/") or _CN_BASE_URL


def minimax_key_configured() -> bool:
    try:
        resolve_minimax_api_key()
        return True
    except RuntimeError:
        return False


def minimax_config_summary() -> dict[str, str]:
    try:
        key, source = resolve_minimax_api_key()
    except RuntimeError:
        return {"configured": "false", "key_source": "", "key_hint": ""}
    hint = key[:7] + "…" + key[-4:] if len(key) > 14 else "(short key)"
    return {
        "configured": "true",
        "key_source": source,
        "key_hint": hint,
        "base_url": resolve_minimax_base_url(key),
    }


def _resolve_api_key() -> str:
    return resolve_minimax_api_key()[0]


# Strip a top-level <think>...</think> block (non-greedy, DOTALL).
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think_block(text: str) -> str:
    """Remove the model's <think>...</think> reasoning wrapper.

    MiniMax-M3 emits a CoT block before the final answer. We strip it so
    downstream parsers see only the canonical ``Thought: ... / Action: ...``
    format. The stripped text is preserved separately for debugging.
    """
    if "<think>" not in text:
        return text
    return _THINK_RE.sub("", text).strip()


class MiniMaxLLMClient:
    """OpenAI-compatible client for MiniMax-M3 (and friends)."""

    def __init__(self,
                 base_url: Optional[str] = None,
                 model: Optional[str] = None,
                 api_key: Optional[str] = None,
                 max_tokens: int = DEFAULT_MAX_TOKENS,
                 temperature: float = DEFAULT_TEMPERATURE,
                 retries: int = 3,
                 strip_think: bool = True):
        resolved_key = api_key or _resolve_api_key()
        self._client = OpenAI(
            api_key=resolved_key,
            base_url=base_url or resolve_minimax_base_url(resolved_key),
        )
        self.model = model or DEFAULT_MODEL
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.retries = retries
        self.strip_think = strip_think
        self._total_tokens = 0
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._last_raw_text = ""
        self._last_stripped_text = ""
        self._last_think_chars = 0

    # ── interface matching AgentLLMClient ───────────────────────────
    def chat(self, messages: List[Dict[str, str]]) -> str:
        """Send a list of messages and return the assistant's text reply.

        Strips any ``<think>...</think>`` reasoning block the model may
        emit so the output is in the canonical format that
        ``react_loop.parse_llm_output`` expects.
        """
        last_error: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                )
                text = self._extract_text(response)
                self._absorb_usage(response)
                if self.strip_think:
                    self._last_raw_text = text
                    stripped = _strip_think_block(text)
                    self._last_think_chars = len(text) - len(stripped)
                    self._last_stripped_text = stripped
                    return stripped
                self._last_raw_text = text
                self._last_stripped_text = text
                return text
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                err_s = str(exc).lower()
                # Rate-limit / quota exhaustion will not recover within a case run.
                if any(tok in err_s for tok in ("rate_limit", "429", "2056", "用量上限")):
                    logger.warning("MiniMax rate-limited; fail fast without retry: %s", exc)
                    break
                if attempt < self.retries:
                    sleep_s = 1.5 * attempt
                    logger.warning(
                        "MiniMax call attempt %d/%d failed (%s), retrying in %.1fs",
                        attempt, self.retries, exc, sleep_s,
                    )
                    time.sleep(sleep_s)
        raise RuntimeError(
            f"MiniMax call failed after {self.retries} attempts: {last_error}"
        )

    @staticmethod
    def _extract_text(response) -> str:
        content = response.choices[0].message.content
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif hasattr(item, "text"):
                    parts.append(item.text)
            return "\n".join(p for p in parts if p).strip()
        return str(content).strip()

    def _absorb_usage(self, response) -> None:
        usage = getattr(response, "usage", None)
        if not usage:
            return
        self._total_tokens += getattr(usage, "total_tokens", 0) or 0
        self._total_prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
        self._total_completion_tokens += getattr(usage, "completion_tokens", 0) or 0

    # ── observability ───────────────────────────────────────────────
    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def total_prompt_tokens(self) -> int:
        return self._total_prompt_tokens

    @property
    def total_completion_tokens(self) -> int:
        return self._total_completion_tokens

    @property
    def last_think_chars(self) -> int:
        return self._last_think_chars

    @property
    def last_raw_text(self) -> str:
        return self._last_raw_text
