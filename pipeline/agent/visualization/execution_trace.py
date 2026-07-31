"""Extract and render agent execution + model + LLM invocation records for reports."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .html_format import format_llm_messages_html, format_llm_response_html


# Steps that invoke DL models (tool_name → display name)
MODEL_STEP_IDS = {
    "quality": ("quality_check", "质量门控"),
    "binary_gate": ("binary_classify", "L0 良恶性 ConvNeXt-S"),
    "lumen_detect": ("detect_lumen", "胃腔检测 YOLO11l"),
    "lesion_seg": ("segment", "病灶分割 UNet + DINOv3"),
    "morphology": ("morphology", "形态学（mask 几何）"),
    "t_staging": ("classify", "L1 T 分期 Dual ConvNeXt"),
    "wall_evidence": ("wall_evidence", "壁层 SDF 几何"),
    "dinov3_seg": ("segment_dinov3_candidate", "DINOv3 分割（独立步）"),
    "case_rag": ("retrieve_similar", "Case-RAG FAISS"),
}


def _short_path(p: Any, max_len: int = 72) -> str:
    if not p:
        return "—"
    s = str(p)
    if len(s) <= max_len:
        return s
    return "…" + s[-(max_len - 1) :]


def _collect_runtime_blocks(step: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pull runtime_invocation dicts from observation (top-level or nested)."""
    obs = step.get("observation") or {}
    blocks: List[Dict[str, Any]] = []
    sid = step.get("step_id", "")

    if sid == "lesion_seg":
        for key, label in (("unet", "UNet ConvNeXt-B"), ("dinov3", "DINOv3 ViT candidate")):
            sub = obs.get(key) or {}
            ri = sub.get("runtime_invocation")
            if ri or sub.get("available"):
                blocks.append({
                    "label": label,
                    "runtime_invocation": ri or {},
                    "outputs": {
                        "mask_available": sub.get("mask_available"),
                        "lesion_area_ratio": sub.get("lesion_area_ratio"),
                        "backend_id": sub.get("backend_id"),
                    },
                })
        return blocks

    if sid == "t_staging":
        primary = obs.get("primary") or obs
        ri = primary.get("runtime_invocation")
        if ri:
            blocks.append({
                "label": "L1 classify primary frame",
                "runtime_invocation": ri,
                "outputs": {
                    "top1_stage": primary.get("top1_stage"),
                    "top1_prob": primary.get("top1_prob"),
                    "probabilities": primary.get("probabilities"),
                },
            })
        return blocks

    if sid == "binary_gate":
        pf = obs.get("primary_frame") or {}
        ri = pf.get("runtime_invocation")
        if ri or pf.get("available"):
            blocks.append({
                "label": "L0 binary primary frame",
                "runtime_invocation": ri or {},
                "outputs": {
                    "top1_label": pf.get("top1_label"),
                    "top1_prob": pf.get("top1_prob"),
                    "gate_decision": pf.get("gate_decision"),
                },
            })
        return blocks

    ri = obs.get("runtime_invocation")
    if ri or step.get("tool_name"):
        out_keys = (
            "lumen_detected", "lumen_confidence", "lumen_bbox", "lumen_area_ratio",
            "available", "penetration_risk", "mask_available", "lesion_area_ratio",
        )
        outputs = {k: obs.get(k) for k in out_keys if k in obs}
        blocks.append({
            "label": step.get("tool_name") or sid,
            "runtime_invocation": ri or {},
            "outputs": outputs,
        })
    return blocks


def build_execution_trace(steps: List[Dict[str, Any]], *, pipeline_mode: str = "deterministic_12_step") -> Dict[str, Any]:
    """Structured trace: agent steps + model forward passes."""
    agent_executions: List[Dict[str, Any]] = []
    model_invocations: List[Dict[str, Any]] = []

    for step in sorted(steps, key=lambda s: int(s.get("step") or 0)):
        sid = step.get("step_id", "")
        agent_executions.append({
            "step": step.get("step"),
            "step_id": sid,
            "agent_name": step.get("agent_name"),
            "tool_name": step.get("tool_name"),
            "status": step.get("status"),
            "elapsed_s": step.get("elapsed_s"),
            "inputs": step.get("inputs"),
            "explanation": step.get("explanation"),
            "observation": step.get("observation"),
            "figure_paths": step.get("figure_paths"),
        })

        for block in _collect_runtime_blocks(step):
            ri = block.get("runtime_invocation") or {}
            model_invocations.append({
                "step": step.get("step"),
                "step_id": sid,
                "agent_name": step.get("agent_name"),
                "model_label": block.get("label"),
                "tool_name": step.get("tool_name"),
                "api_kind": ri.get("api_kind"),
                "forward_pass": ri.get("forward_pass"),
                "checkpoint": ri.get("checkpoint"),
                "encoder": ri.get("encoder") or ri.get("global_backbone"),
                "device": ri.get("device"),
                "conf": ri.get("conf"),
                "imgsz": ri.get("imgsz"),
                "outputs_summary": block.get("outputs"),
            })

    return {
        "pipeline_mode": pipeline_mode,
        "pipeline_mode_note": (
            "本报告为 deterministic 12-step pipeline：Agent 按固定顺序调用工具，"
            "不使用 ReAct LLM 逐步调度。ReAct + LLM 逐步决策见 run_e2e_react_demo / analyze_case 产品路径。"
        ),
        "agent_executions": agent_executions,
        "model_invocations": model_invocations,
    }


def render_execution_mode_notice() -> List[str]:
    return [
        "<h2>0. 执行模式说明</h2>",
        "<p>本报告使用 <b>LangGraph 12-step case pipeline</b>（<code>run_langgraph_case_pipeline</code>）："
        "每个 Agent 为独立图节点，执行前/后各一次 LLM（plan + interpret），再调用 CV/RAG 工具。</p>",
        "<ul>",
        "<li><b>Agent + LLM</b>：§6–§7 每步含完整 LLM messages 与返回；汇总见 §10 "
        "<code>llm_trace.json</code></li>",
        "<li><b>LLM 后端</b>：MiniMax（<code>MINIMAX_API_KEY</code>）→ OpenAI 兼容 API → "
        "离线 step narrative 模板（无 Key 时仍可跑通并记录）</li>",
        "<li><b>ReAct 逐步调度</b>：<code>run_e2e_react_demo --orchestrator langgraph</code> "
        "为另一条 LangGraph ReAct 图</li>",
        "</ul>",
    ]


def render_model_invocation_table(trace: Dict[str, Any]) -> List[str]:
    invocations = trace.get("model_invocations") or []
    lines = [
        "<h2>8. 模型推理调用记录</h2>",
        "<p>从各步 <code>observation.runtime_invocation</code> 提取的<b>真实 forward pass</b>。"
        "forward_pass=true 表示该 checkpoint 在本例上完成了推理。</p>",
        "<table><tr><th>Step</th><th>Agent</th><th>模型</th><th>forward</th>"
        "<th>api_kind</th><th>checkpoint / encoder</th><th>关键输出</th></tr>",
    ]
    if not invocations:
        lines.append("<tr><td colspan='7'>无 runtime_invocation 记录</td></tr>")
    for inv in invocations:
        ck = inv.get("checkpoint") or inv.get("encoder") or "—"
        out = inv.get("outputs_summary") or {}
        out_str = json.dumps(out, ensure_ascii=False)
        if len(out_str) > 120:
            out_str = out_str[:117] + "…"
        fp = inv.get("forward_pass")
        fp_badge = (
            "<span class='badge ok'>true</span>"
            if fp is True
            else ("<span class='badge warn'>false</span>" if fp is False else "—")
        )
        lines.append(
            f"<tr><td>{inv.get('step')}</td>"
            f"<td><code>{html.escape(str(inv.get('step_id', '')))}</code></td>"
            f"<td>{html.escape(str(inv.get('model_label', '')))}</td>"
            f"<td>{fp_badge}</td>"
            f"<td>{html.escape(str(inv.get('api_kind', '—')))}</td>"
            f"<td><code>{html.escape(_short_path(ck, 56))}</code></td>"
            f"<td><code>{html.escape(out_str)}</code></td></tr>"
        )
    lines.append("</table>")

    lumen = next((i for i in invocations if i.get("step_id") == "lumen_detect"), None)
    if lumen:
        lines.append(
            f"<p><b>胃腔检测已调用</b>：Step {lumen.get('step')} "
            f"forward_pass={lumen.get('forward_pass')} · "
            f"conf 阈值见 observation · checkpoint="
            f"<code>{html.escape(_short_path(lumen.get('checkpoint'), 80))}</code></p>"
        )
    elif any(s.get("step_id") == "lumen_detect" and s.get("status") == "skipped" for s in trace.get("agent_executions", [])):
        lines.append(
            "<p class='meta'><b>胃腔检测未执行</b>：Step 5 被 skip_t 跳过。"
            "使用 <code>--triage-mode soft</code> 可强制跑完整链。</p>"
        )
    return lines


def render_llm_section(llm_record: Optional[Dict[str, Any]], llm_trace: Optional[Dict[str, Any]] = None) -> List[str]:
    lines = [
        "<h2>10. LLM 全量调用记录</h2>",
        "<p>LangGraph 生产 pipeline：每个 Agent 节点 <b>plan</b>（执行前）与 "
        "<b>interpret</b>（执行后）各 1 次 LLM；全部写入 "
        "<code>llm_trace.json</code>。下方为完整请求/返回。</p>",
    ]

    if llm_trace and llm_trace.get("calls"):
        lines.append(
            f"<p>Provider: <code>{html.escape(str(llm_trace.get('provider', '?')))}</code> · "
            f"Model: <code>{html.escape(str(llm_trace.get('model', '?')))}</code> · "
            f"Total calls: <b>{llm_trace.get('total_calls', len(llm_trace.get('calls', [])))}</b></p>"
        )
        for i, call in enumerate(llm_trace["calls"], 1):
            sid = html.escape(str(call.get("step_id", "?")))
            phase = html.escape(str(call.get("phase", "?")))
            agent = html.escape(str(call.get("agent_name", "?")))
            lines.append(
                f"<details class='llm-call'><summary>#{i} Step {sid} · {agent} · {phase} · "
                f"{html.escape(str(call.get('status', '?')))}</summary>"
            )
            if call.get("messages"):
                lines.append("<h4>输入 messages</h4>")
                lines.append(format_llm_messages_html(call["messages"]))
            if call.get("response_text"):
                lines.append("<h4>LLM 输出</h4>")
                lines.append(format_llm_response_html(str(call["response_text"])))
            if call.get("error"):
                lines.append(f"<p class='meta'>error: {html.escape(str(call['error']))}</p>")
            lines.append("</details>")
    else:
        lines.append("<p class='meta'>无 llm_trace.json — 请用 LangGraph pipeline 重跑。</p>")

    lines.append("<h3>可选：全局报告润色 (_maybe_llm_synthesis)</h3>")
    if not llm_record:
        lines.append("<p class='meta'>未运行 LLM 润色。</p>")
        return lines

    called = llm_record.get("called")
    status = llm_record.get("status", "?")
    lines.append("<table>")
    for key in (
        "called", "status", "api_kind", "model", "base_url",
        "total_tokens", "skip_reason", "error",
    ):
        if key in llm_record and llm_record[key] not in (None, ""):
            val = llm_record[key]
            lines.append(
                f"<tr><th>{html.escape(key)}</th><td>{html.escape(str(val))}</td></tr>"
            )
    lines.append("</table>")

    if llm_record.get("request_prompt"):
        lines.append("<h3>LLM 请求 prompt</h3>")
        if isinstance(llm_record["request_prompt"], list):
            lines.append(format_llm_messages_html(llm_record["request_prompt"]))
        else:
            lines.append(
                f"<pre class='llm-json'>{html.escape(json.dumps(llm_record['request_prompt'], indent=2, ensure_ascii=False))}</pre>"
            )
    if llm_record.get("response_text"):
        lines.append("<h3>LLM 返回</h3>")
        lines.append(format_llm_response_html(str(llm_record["response_text"])))

    if not called:
        lines.append(
            f"<p>LLM 未调用：{html.escape(str(llm_record.get('skip_reason', 'unknown')))}。"
            "设置 <code>AGENT_API_KEY</code> / <code>VLM_API_KEY</code> 后重建报告可启用。</p>"
        )
    elif status == "ok":
        lines.append("<p>LLM 润色已成功合并到报告结论（若与规则融合字段冲突以 LLM JSON 为准）。</p>")
    return lines


def render_agent_execution_table(trace: Dict[str, Any]) -> List[str]:
    """Compact agent execution log table."""
    rows = trace.get("agent_executions") or []
    lines = [
        "<h2>9. Agent 逐步执行记录</h2>",
        "<table><tr><th>#</th><th>Agent</th><th>Tool</th><th>Status</th>"
        "<th>耗时(s)</th><th>说明</th><th>inputs</th></tr>",
    ]
    for r in rows:
        inp = json.dumps(r.get("inputs") or {}, ensure_ascii=False)
        if len(inp) > 80:
            inp = inp[:77] + "…"
        expl = str(r.get("explanation") or "")[:100]
        lines.append(
            f"<tr><td>{r.get('step')}</td>"
            f"<td>{html.escape(str(r.get('agent_name', '')))}</td>"
            f"<td><code>{html.escape(str(r.get('tool_name') or '—'))}</code></td>"
            f"<td>{html.escape(str(r.get('status', '')))}</td>"
            f"<td class='num'>{float(r.get('elapsed_s') or 0):.2f}</td>"
            f"<td>{html.escape(expl)}</td>"
            f"<td><code>{html.escape(inp)}</code></td></tr>"
        )
    lines.append("</table>")
    return lines
