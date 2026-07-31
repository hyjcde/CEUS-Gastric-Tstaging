"""HTML formatting helpers for LLM trace blocks in agent reports."""

from __future__ import annotations

import html
import json
import re
from typing import Any, Dict, List

_HTML_OMIT_KEYS = frozenset({
    "_visuals",
    "wall_overlay_bgr",
    "wall_profile",
    "risk_norm",
    "mask_array",
    "heatmap",
    "grad_cam",
    "runtime_invocation",
    "figure_paths",
})

_HTML_MAX_STR = 800
_HTML_MAX_LIST = 24
_HTML_MAX_DEPTH = 8


def slim_for_html_report(obj: Any, *, depth: int = 0) -> Any:
    """Drop bulky arrays / nested blobs before embedding JSON in HTML."""
    if depth > _HTML_MAX_DEPTH:
        return "…"
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            if k in _HTML_OMIT_KEYS:
                out[k] = "<omitted>"
                continue
            out[k] = slim_for_html_report(v, depth=depth + 1)
        return out
    if isinstance(obj, list):
        if len(obj) > _HTML_MAX_LIST:
            head = [slim_for_html_report(v, depth=depth + 1) for v in obj[:_HTML_MAX_LIST]]
            head.append(f"…[{len(obj) - _HTML_MAX_LIST} more items omitted]")
            return head
        if obj and isinstance(obj[0], (int, float)) and len(obj) > 64:
            return f"<array len={len(obj)} min={min(obj):.4g} max={max(obj):.4g}>"
        return [slim_for_html_report(v, depth=depth + 1) for v in obj]
    if isinstance(obj, str) and len(obj) > _HTML_MAX_STR:
        return obj[:_HTML_MAX_STR] + "…"
    return obj


def sanitize_observation_for_html(obs: Dict[str, Any]) -> Dict[str, Any]:
    """Observation JSON safe for HTML <pre> blocks."""
    if not obs:
        return {}
    return slim_for_html_report(dict(obs))


def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text.strip())


def format_llm_response_html(text: str) -> str:
    """Render LLM narrative (Markdown-lite) as prose paragraphs, not monospace pre."""
    text = _collapse_blank_lines(str(text or ""))
    if not text:
        return "<p class='meta'>（空响应）</p>"

    parts: List[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        # Single newlines within paragraph → soft break
        para = html.escape(para)
        para = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", para)
        para = para.replace("\n", "<br/>")
        parts.append(f'<p class="llm-prose">{para}</p>')
    return "\n".join(parts)


def _format_message_content(role: str, content: str) -> str:
    content = content or ""
    if role == "user" and content.lstrip().startswith("{"):
        try:
            payload = slim_for_html_report(json.loads(content))
            pretty = json.dumps(payload, indent=2, ensure_ascii=False)
            return f'<pre class="llm-json">{html.escape(pretty)}</pre>'
        except json.JSONDecodeError:
            pass
    escaped = html.escape(_collapse_blank_lines(content))
    escaped = escaped.replace("\n", "<br/>")
    return f'<p class="llm-prose llm-system">{escaped}</p>'


def format_llm_messages_html(messages: List[Dict[str, Any]]) -> str:
    """Pretty-print chat messages without escaped \\n inside JSON strings."""
    if not messages:
        return "<p class='meta'>（无 messages）</p>"

    blocks: List[str] = ['<div class="llm-messages">']
    for i, msg in enumerate(messages, 1):
        role = html.escape(str(msg.get("role", "?")))
        content = str(msg.get("content", ""))
        blocks.append(f'<div class="llm-msg"><div class="llm-msg-head">#{i} · {role}</div>')
        blocks.append(_format_message_content(str(msg.get("role", "")), content))
        blocks.append("</div>")
    blocks.append("</div>")
    return "\n".join(blocks)


LLM_REPORT_CSS = """
.llm-messages { margin: 8px 0 12px; }
.llm-msg { margin-bottom: 12px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 4px; background: rgba(0,0,0,0.02); }
.llm-msg-head { font-size: 12px; color: var(--muted); margin-bottom: 6px; font-family: monospace; }
.llm-prose { margin: 0.35em 0; line-height: 1.65; white-space: normal; word-break: break-word; }
.llm-prose.llm-system { font-size: 14px; }
.llm-json { margin: 0; max-height: 320px; overflow: auto; font-size: 12px; line-height: 1.45; white-space: pre; }
pre.llm-json { white-space: pre; }
details.llm-call > summary { cursor: pointer; font-weight: 600; margin: 8px 0; }
details.llm-call { margin: 10px 0; padding: 0 4px; }
"""
