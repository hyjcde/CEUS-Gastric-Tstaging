"""
LLM client for the abdominal ultrasound Agent's ReAct loop.

Reuses the OpenAI-compatible client from pipeline/scripts/vlm/remote_client.py
but adapts it for text-only ReAct interactions (no images sent to the LLM).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Dict, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = os.getenv(
    "AGENT_LLM_BASE_URL",
    os.getenv("VLM_API_BASE_URL", "https://api.poe.com/v1"),
)
DEFAULT_MODEL = os.getenv(
    "AGENT_LLM_MODEL",
    os.getenv("VLM_MODEL", "DeepSeek-V4-Flash-EL"),
)
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.1


def _resolve_api_key(base_url: Optional[str] = None) -> str:
    provider_url = (base_url or "").lower()
    key_vars = (
        (
            "DEEPSEEK_API_KEY",
            "AGENT_API_KEY",
            "VLM_API_KEY",
            "POE_API_KEY",
            "OPENAI_API_KEY",
        )
        if "deepseek" in provider_url
        else (
            "AGENT_API_KEY",
            "VLM_API_KEY",
            "POE_API_KEY",
            "OPENAI_API_KEY",
            "DEEPSEEK_API_KEY",
        )
    )
    for var in key_vars:
        key = os.getenv(var)
        if key:
            return key
    raise RuntimeError(
        "Missing API key. Set AGENT_API_KEY, VLM_API_KEY, POE_API_KEY, "
        "OPENAI_API_KEY, or DEEPSEEK_API_KEY."
    )


class AgentLLMClient:
    """
    Text-only LLM client for the ReAct agent.

    Key differences from remote_client.chat_with_image:
      - Never sends images (privacy: LLM only sees structured tool output)
      - Maintains conversation history for multi-turn ReAct
      - Configurable retry with exponential backoff
    """

    def __init__(self,
                 base_url: Optional[str] = None,
                 model: Optional[str] = None,
                 max_tokens: int = DEFAULT_MAX_TOKENS,
                 temperature: float = DEFAULT_TEMPERATURE,
                 retries: int = 3,
                 api_key: Optional[str] = None,
                 disable_thinking: bool = False):
        resolved_base_url = base_url or DEFAULT_BASE_URL
        self._client = OpenAI(
            api_key=api_key or _resolve_api_key(resolved_base_url),
            base_url=resolved_base_url,
        )
        self._base_url = resolved_base_url
        self.model = model or DEFAULT_MODEL
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.retries = retries
        self.disable_thinking = disable_thinking
        self._total_tokens = 0

    def chat(self, messages: List[Dict[str, str]]) -> str:
        """
        Send a list of messages and return the assistant's text reply.

        messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
        """
        last_error = None
        for attempt in range(1, self.retries + 1):
            try:
                request_kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                }
                if self.disable_thinking and "deepseek" in self._base_url.lower():
                    request_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
                response = self._client.chat.completions.create(
                    **request_kwargs,
                )
                text = self._extract_text(response)

                usage = getattr(response, "usage", None)
                if usage:
                    self._total_tokens += getattr(usage, "total_tokens", 0)

                return text
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    sleep_s = 2.0 * attempt
                    logger.warning(
                        "LLM call attempt %d/%d failed (%s), retrying in %.1fs",
                        attempt, self.retries, exc, sleep_s,
                    )
                    time.sleep(sleep_s)

        raise RuntimeError(f"LLM call failed after {self.retries} attempts: {last_error}")

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

    @property
    def total_tokens(self) -> int:
        return self._total_tokens
