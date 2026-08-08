"""Per-step Agent narratives and human-readable output summaries for reports."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from .html_format import (
    format_llm_messages_html,
    format_llm_response_html,
    sanitize_observation_for_html,
    slim_for_html_report,
)
from .media_refs import img_tag
from .platform_panels import ScanPlatformPanel, render_platform_panel_grid


def _json_default(obj: Any) -> Any:
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

STEP_DOCS: Dict[str, Dict[str, str]] = {
    "triage": {
        "agent": "TriageAgent",
        "role": "病例接入与路由",
        "purpose": (
            "读取 case_id、输入模式（video/static）、帧数与 GT 标签，"
            "决定后续 12 步 pipeline 的上下文。不调用深度学习模型。"
        ),
        "tool": "—（元数据 Agent）",
    },
    "frame_extract": {
        "agent": "FrameExtractAgent",
        "role": "视频关键帧抽取",
        "purpose": (
            "对 clip mp4 调用 sample_video：等距采样至多 64 帧，"
            "按 motion+sharpness 选 4 个关键帧，写入临时 jpg 供下游模型读取。"
        ),
        "tool": "sample_video（scripts/generate_video_deep_dive）",
    },
    "quality": {
        "agent": "QualityAgent",
        "role": "首帧质量门控",
        "purpose": "检查 primary 关键帧是否 usable（模糊/过暗/无效 UI），score≥0.3 才继续。",
        "tool": "quality_check",
    },
    "binary_gate": {
        "agent": "BinaryGateAgent",
        "role": "L0 良恶性闸门",
        "purpose": (
            "ConvNeXt-S 二分类：P(benign)≥阈值且 top1=benign 时 gate=skip_t 可跳过 T 链；"
            "triage_mode=soft 时仅记录 L0，始终 run_t。"
        ),
        "tool": "binary_classify",
    },
    "lumen_detect": {
        "agent": "LumenDetectAgent",
        "role": "胃腔 / 探头 UI 定位",
        "purpose": "YOLO11l 检测 lumen bbox，为壁层 SDF 与 ROI 对齐提供几何锚点。",
        "tool": "detect_lumen",
    },
    "lesion_seg": {
        "agent": "LesionSegAgent",
        "role": "病灶分割 · mask 选择",
        "purpose": (
            "并行运行 UNet ConvNeXt-B（生产）与 DINOv3 FM candidate；"
            "seg_policy=auto 时按 area/置信度评分选下游 mask。"
        ),
        "tool": "segment + segment_dinov3_candidate",
    },
    "morphology": {
        "agent": "MorphologyAgent",
        "role": "病灶形态学",
        "purpose": "基于 lesion mask 计算边界不规则度、凸度、致密度等，供 L1 与 RAG 向量。",
        "tool": "morphology",
    },
    "t_staging": {
        "agent": "TStagingAgent",
        "role": "L1 T 分期（4-class + clinical22）",
        "purpose": "Dual ConvNeXt + 临床特征 → T1/T2/T3/T4+ 概率；输出 Grad-CAM 可解释性。",
        "tool": "classify",
    },
    "wall_evidence": {
        "agent": "WallEvidenceAgent",
        "role": "壁层浸润证据（SDF）",
        "purpose": "结合 lumen bbox 与 lesion mask 估计穿透风险 penetration_risk（low/medium/high）。",
        "tool": "wall_evidence",
    },
    "gc_us_signs": {
        "agent": "GcUsSignAgent",
        "role": "核心征象算法链",
        "purpose": "逐项评分长径、厚度、形态、边界、生长方式和胃壁结构，并区分临床、派生和几何代理证据。",
        "tool": "gc_us_signs",
    },
    "dinov3_seg": {
        "agent": "DINOv3Agent",
        "role": "DINOv3 候选分割（独立证据步）",
        "purpose": "与 Step 6 并行记录 FM 分割结果；用于对照与 research 路径，不强制覆盖主 mask。",
        "tool": "segment_dinov3_candidate",
    },
    "case_rag": {
        "agent": "CaseRAGAgent",
        "role": "Case-RAG 相似病例检索",
        "purpose": "FAISS 检索 top-5 相似病例，给出 stage_distribution 作为辅助证据。",
        "tool": "retrieve_similar",
    },
    "report_synth": {
        "agent": "ReportSynthAgent",
        "role": "综合报告合成",
        "purpose": "融合 L0/L1/壁层/RAG/临床风险 → recommended_t_stage、confidence、supporting_evidence。",
        "tool": "structure_report + clinical_risk + 规则融合",
    },
}

STEP_FIGURE_STEMS: Dict[str, List[str]] = {
    "quality": ["step-03-quality"],
    "binary_gate": ["step-04-binary"],
    "lumen_detect": ["step-05-lumen"],
    "lesion_seg": ["step-06-seg", "step-06-seg-unet-vs-dino"],
    "morphology": ["step-07-morphology"],
    "t_staging": ["step-08-tstage"],
    "wall_evidence": ["step-09-wall"],
    "gc_us_signs": ["step-10-gc-us-signs"],
    "dinov3_seg": ["step-06-seg-unet-vs-dino"],
    "case_rag": ["step-13-rag"],
}

# 原 six_panel 六联图对应的 6 个主可视化 Agent（逐步展示）
MAIN_VIS_AGENT_ORDER: List[tuple[str, str]] = [
    ("binary_gate", "L0 良恶性 · BinaryGateAgent"),
    ("lumen_detect", "胃腔检测 · LumenDetectAgent"),
    ("lesion_seg", "病灶分割 · LesionSegAgent"),
    ("morphology", "形态学 · MorphologyAgent"),
    ("t_staging", "L1 T 分期 + DINO + Grad-CAM · TStagingAgent"),
    ("wall_evidence", "壁层浸润 SDF · WallEvidenceAgent"),
    ("gc_us_signs", "核心征象算法链 / GcUsSignAgent"),
    ("dinov3_seg", "DINOv3 FM 分割 · DINOv3Agent"),
    ("case_rag", "Case-RAG · CaseRAGAgent"),
]


def summarize_step_outputs(step: Dict[str, Any]) -> List[str]:
    """Bullet list of key outputs for HTML."""
    sid = step.get("step_id", "")
    obs = step.get("observation") or {}
    bullets: List[str] = []

    if step.get("status") == "skipped" or obs.get("skipped"):
        bullets.append(f"状态：跳过 — {obs.get('reason', step.get('explanation', 'skip_t 或功能关闭'))}")
        return bullets

    if sid == "triage":
        bullets += [
            f"case_id={obs.get('case_id')} · mode={obs.get('input_mode')}",
            f"frame_count={obs.get('frame_count')} · GT={obs.get('gt_t_stage', '—')}",
            f"data_source={obs.get('data_source', '—')}",
        ]
    elif sid == "frame_extract":
        frs = obs.get("frames") or []
        bullets += [
            f"clip={obs.get('clip_name', '?')} · source={obs.get('source', '?')}",
            f"关键帧数={obs.get('frame_count', len(frs))}",
        ]
        for item in frs[:4]:
            if isinstance(item, dict):
                bullets.append(
                    f"  · idx={item.get('frame_index')} path={item.get('image_path', '')}"
                )
            else:
                bullets.append(f"  · {item}")
    elif sid == "quality":
        bullets += [
            f"usable={obs.get('usable')} · quality_score={obs.get('quality_score', '?')}",
        ]
    elif sid == "binary_gate":
        pf = obs.get("primary_frame") or {}
        bullets += [
            f"top1={pf.get('top1_label')} p={pf.get('top1_prob')}",
            f"gate_decision={obs.get('gate_decision')} · triage_mode={obs.get('triage_mode')}",
        ]
        if obs.get("soft_override"):
            bullets.append(str(obs["soft_override"]))
    elif sid == "lumen_detect":
        bullets += [
            f"lumen_detected={obs.get('lumen_detected')} · conf={obs.get('lumen_confidence', 0)}",
            f"bbox={obs.get('lumen_bbox', '—')}",
        ]
    elif sid == "lesion_seg":
        sel = obs.get("selection") or {}
        bullets += [
            f"选用 backend={sel.get('chosen_backend', '?')}",
            f"UNet score={sel.get('unet_score')} · DINO score={sel.get('dinov3_score')}",
            f"mask_available={obs.get('mask_available')} · area_ratio={obs.get('lesion_area_ratio')}",
            f"理由：{sel.get('rationale', '—')}",
        ]
    elif sid == "morphology":
        bullets += [
            f"irregularity={obs.get('boundary_irregularity', '?')}",
            f"convexity={obs.get('convexity', '?')} · solidity={obs.get('solidity', '?')}",
            f"area_ratio={obs.get('area_ratio', '?')}",
        ]
    elif sid == "t_staging":
        primary = obs.get("primary") or obs
        probs = primary.get("probabilities") or {}
        bullets += [
            f"top1={primary.get('top1_stage')} p={primary.get('top1_prob')}",
            f"分布 T1={probs.get('T1', '?')} T2={probs.get('T2', '?')} "
            f"T3={probs.get('T3', '?')} T4+={probs.get('T4+', '?')}",
        ]
    elif sid == "wall_evidence":
        bullets += [
            f"available={obs.get('available')}",
            f"penetration_risk={obs.get('penetration_risk', '?')}",
            f"evidence_source={obs.get('evidence_source', '—')}",
        ]
    elif sid == "dinov3_seg":
        bullets += [
            f"available={obs.get('available')} · mask={obs.get('mask_available', obs.get('available'))}",
            f"area_ratio={obs.get('lesion_area_ratio', '?')} · backend={obs.get('backend_id', '—')}",
        ]
        if obs.get("error"):
            bullets.append(f"error={obs['error']}")
    elif sid == "case_rag":
        hits = obs.get("similar_cases") or []
        bullets += [
            f"hits={len(hits)} · total_in_memory={obs.get('total_in_memory', '?')}",
            f"stage_distribution={obs.get('stage_distribution', {})}",
        ]
        for h in hits[:3]:
            bullets.append(
                f"  #{h.get('rank')} {h.get('patient_id')} T={h.get('T_stage')} sim={h.get('similarity', 0):.3f}"
            )
    elif sid == "report_synth":
        fusion = obs.get("fusion") or {}
        bullets += [
            f"recommended_t_stage={fusion.get('recommended_t_stage') or obs.get('recommended_t_stage')}",
            f"confidence={fusion.get('confidence') or obs.get('confidence')}",
            f"reasoning={str(fusion.get('reasoning', ''))[:200]}",
        ]
        ev = fusion.get("supporting_evidence") or obs.get("supporting_evidence") or []
        for e in ev[:5]:
            bullets.append(f"  · {e}")
    else:
        if step.get("explanation"):
            bullets.append(str(step["explanation"]))

    if step.get("inputs"):
        bullets.append(f"inputs: {json.dumps(step['inputs'], ensure_ascii=False)[:240]}")
    return bullets


def _runtime_invocation_bullets(step: Dict[str, Any]) -> List[str]:
    from .execution_trace import _collect_runtime_blocks

    lines: List[str] = []
    for block in _collect_runtime_blocks(step):
        ri = block.get("runtime_invocation") or {}
        if not ri:
            continue
        label = block.get("label", "?")
        fp = ri.get("forward_pass")
        ck = ri.get("checkpoint") or ri.get("encoder") or ri.get("global_backbone") or "—"
        lines.append(
            f"【{label}】api={ri.get('api_kind')} forward_pass={fp} "
            f"device={ri.get('device', '—')} ck={Path(str(ck)).name if ck != '—' else '—'}"
        )
        outs = block.get("outputs") or {}
        if outs.get("top1_stage"):
            lines.append(f"  → top1={outs.get('top1_stage')} p={outs.get('top1_prob')}")
        elif outs.get("top1_label"):
            lines.append(f"  → {outs.get('top1_label')} p={outs.get('top1_prob')} gate={outs.get('gate_decision')}")
        elif outs.get("lumen_detected") is not None:
            lines.append(
                f"  → lumen_detected={outs.get('lumen_detected')} conf={outs.get('lumen_confidence')} "
                f"bbox={outs.get('lumen_bbox')}"
            )
        elif outs.get("lesion_area_ratio") is not None:
            lines.append(f"  → mask={outs.get('mask_available')} area={outs.get('lesion_area_ratio')}")
    return lines


def _render_agent_llm_block(step: Dict[str, Any], llm_record: Optional[Dict[str, Any]]) -> List[str]:
    """Per-agent LLM calls from LangGraph pipeline (plan + interpret)."""
    sid = step.get("step_id", "")
    llm_calls = step.get("llm_calls") or []
    lines = ["<p><b>LLM 调用</b></p>"]

    if llm_calls:
        lines.append(f"<p>本步共 <b>{len(llm_calls)}</b> 次 LLM 调用（plan + interpret）：</p>")
        for i, call in enumerate(llm_calls, 1):
            phase = html.escape(str(call.get("phase", "?")))
            model = html.escape(str(call.get("model", "?")))
            provider = html.escape(str(call.get("provider", "?")))
            status = html.escape(str(call.get("status", "?")))
            lines.append(
                f"<details class='llm-call'><summary>#{i} · {phase} · {provider}/{model} · {status}</summary>"
            )
            if call.get("messages"):
                lines.append("<h4>请求 messages</h4>")
                lines.append(format_llm_messages_html(call["messages"]))
            if call.get("response_text"):
                lines.append("<h4>LLM 返回</h4>")
                lines.append(format_llm_response_html(str(call["response_text"])))
            if call.get("error"):
                lines.append(f"<p class='meta'>error: {html.escape(str(call['error']))}</p>")
            lines.append("</details>")
        return lines

    if sid == "report_synth" and llm_record and llm_record.get("called"):
        lines.append(
            f"<p class='meta'>全局润色：model={html.escape(str(llm_record.get('model', '?')))} "
            f"status={html.escape(str(llm_record.get('status', '?')))}</p>"
        )
        return lines

    lines.append(
        "<p><span class='badge muted'>无 LLM 记录</span> "
        "（旧 deterministic run 或未写入 llm_calls）</p>"
    )
    return lines


def _render_agent_model_io_block(step: Dict[str, Any]) -> List[str]:
    """Model/tool inputs and outputs for one agent step."""
    from .execution_trace import _collect_runtime_blocks

    lines: List[str] = []
    if step.get("inputs"):
        lines.append("<h4>Agent 输入 (inputs)</h4>")
        lines.append(
            f"<pre>{html.escape(json.dumps(step['inputs'], indent=2, ensure_ascii=False, default=_json_default))}</pre>"
        )

    model_bullets = _runtime_invocation_bullets(step)
    if model_bullets:
        lines.append("<h4>模型推理 (runtime_invocation)</h4><ul>")
        for b in model_bullets:
            lines.append(f"<li>{html.escape(b)}</li>")
        lines.append("</ul>")

    obs = step.get("observation") or {}
    if obs:
        lines.append("<h4>Agent 输出 (observation 摘要)</h4><ul>")
        for b in summarize_step_outputs(step):
            lines.append(f"<li>{html.escape(b)}</li>")
        lines.append("</ul>")
        lines.append("<details><summary>完整 observation JSON</summary>")
        lines.append(
            f"<pre>{html.escape(json.dumps(sanitize_observation_for_html(obs), indent=2, ensure_ascii=False, default=_json_default))}</pre>"
        )
        lines.append("</details>")

    blocks = _collect_runtime_blocks(step)
    for block in blocks:
        ri = block.get("runtime_invocation") or {}
        if ri:
            lines.append(
                f"<details><summary>runtime_invocation · {html.escape(str(block.get('label', '?')))}</summary>"
            )
            lines.append(
                f"<pre>{html.escape(json.dumps(ri, indent=2, ensure_ascii=False, default=_json_default))}</pre>"
            )
            outs = block.get("outputs") or {}
            if outs:
                lines.append("<h4>模型输出摘要</h4>")
                lines.append(
                    f"<pre>{html.escape(json.dumps(outs, indent=2, ensure_ascii=False, default=_json_default))}</pre>"
                )
            lines.append("</details>")
    return lines


def render_per_agent_main_visual_sections(
    steps: List[Dict[str, Any]],
    step_figures: Dict[str, Path],
    *,
    llm_record: Optional[Dict[str, Any]] = None,
    six_panel_path: Optional[Path] = None,
    platform_panels: Optional[Dict[str, List[ScanPlatformPanel]]] = None,
    platform_meta: Optional[Dict[str, Any]] = None,
    html_path: Path,
) -> List[str]:
    """
    Section 6: one card per main-visual Agent (aligned with gastric_scan_next workbench).
    """
    by_id = {str(s.get("step_id")): s for s in steps}
    color_map = {
        "binary_gate": "#2c6e3e", "lumen_detect": "#7ad2d4", "lesion_seg": "#d68b6c",
        "morphology": "#7a8a1f", "t_staging": "#8a5a00", "wall_evidence": "#5a1010",
        "dinov3_seg": "#3a7a8a", "case_rag": "#0f4c5c",
    }
    platform_panels = platform_panels or {}
    platform_meta = platform_meta or {}

    lines = [
        '<div class="annex">',
        "<h2>附录 A · Agent 证据链（Scan 平台同款可视化）</h2>",
        "<p class='meta'>与 gastric_scan_next AgentWorkbench 逐步 VisualFrame 对齐；"
        "默认折叠逐步 LLM / JSON，展开查看详情。</p>",
    ]
    if platform_meta.get("dino_token_grid"):
        lines.append(
            f"<p class='meta'>DINO：model={html.escape(str(platform_meta.get('current_image_dino_model', '?')))} · "
            f"token={html.escape(str(platform_meta.get('dino_token_grid')))}</p>"
        )

    for sid, title in MAIN_VIS_AGENT_ORDER:
        step = by_id.get(sid)
        if not step:
            continue
        color = color_map.get(sid, "#7a2e0f")
        step_n = int(step.get("step") or 0)
        status = html.escape(str(step.get("status", "?")))
        elapsed = float(step.get("elapsed_s", 0))
        bullets = summarize_step_outputs(step)
        summary = " · ".join(bullets[:3]) if bullets else "—"

        lines.append(
            f'<details class="agent-section" id="main-vis-{sid}" '
            f'style="border-left:4px solid {color}">'
        )
        lines.append(
            f"<summary><b>Step {step_n:02d}</b> · {html.escape(title)} "
            f"· {status} · {elapsed:.1f}s — {html.escape(summary[:100])}</summary>"
        )

        scan_panels = platform_panels.get(sid) or []
        if scan_panels:
            lines.extend(render_platform_panel_grid(scan_panels, html_path))

        for stem in STEP_FIGURE_STEMS.get(sid, []):
            fig_path = step_figures.get(stem)
            if fig_path and fig_path.is_file():
                tag = img_tag(html_path, fig_path, css_class="fig scan-fig", alt=stem)
                if tag:
                    lines.append(tag)

        lines.append("<details><summary>LLM / 模型 I/O</summary>")
        lines.extend(_render_agent_llm_block(step, llm_record))
        lines.extend(_render_agent_model_io_block(step))
        lines.append("</details></details>")

    if six_panel_path and six_panel_path.is_file():
        lines.append(
            "<details><summary>六联缩略图（legacy composite）</summary>"
        )
        tag = img_tag(html_path, six_panel_path, css_class="fig scan-fig", alt="6panel")
        if tag:
            lines.append(tag)
        lines.append("</details>")
    lines.append("</div>")
    return lines


def render_step_narrative_sections(
    steps: List[Dict[str, Any]],
    step_figures: Dict[str, Path],
    *,
    llm_record: Optional[Dict[str, Any]] = None,
    html_path: Optional[Path] = None,
) -> List[str]:
    """Rich HTML: one section per Agent with role, outputs, figures, JSON."""
    lines = [
        '<div class="annex">',
        "<h2>附录 B · 十二步 Agent 逐步记录</h2>",
        "<p class='meta'>完整 12 步职责说明与 JSON；默认折叠。</p>",
    ]
    for step in sorted(steps, key=lambda s: int(s.get("step") or 0)):
        sid = str(step.get("step_id", ""))
        doc = STEP_DOCS.get(sid, {})
        color_map = {
            "triage": "#5a4a8a", "frame_extract": "#0f4c5c", "quality": "#4a3b6b",
            "binary_gate": "#2c6e3e", "lumen_detect": "#7ad2d4", "lesion_seg": "#d68b6c",
            "morphology": "#7a8a1f", "t_staging": "#8a5a00", "wall_evidence": "#5a1010",
            "dinov3_seg": "#3a7a8a", "case_rag": "#0f4c5c", "report_synth": "#7a2e0f",
        }
        color = color_map.get(sid, "#7a2e0f")
        step_n = int(step.get("step") or 0)
        agent = html.escape(doc.get("agent") or step.get("agent_name", "?"))
        status = html.escape(str(step.get("status", "?")))
        elapsed = float(step.get("elapsed_s", 0))

        lines.append(
            f'<details class="agent-section" id="step-{step_n:02d}" '
            f'style="border-left:4px solid {color}">'
        )
        lines.append(
            f"<summary><b>Step {step_n:02d}</b> · {agent} · {status} · {elapsed:.1f}s</summary>"
        )
        if doc.get("role"):
            lines.append(f"<p><b>职责</b>：{html.escape(doc['role'])}</p>")
        if doc.get("purpose"):
            lines.append(f"<p>{html.escape(doc['purpose'])}</p>")

        bullets = summarize_step_outputs(step)
        if bullets:
            lines.append("<ul>")
            for b in bullets:
                lines.append(f"<li>{html.escape(b)}</li>")
            lines.append("</ul>")

        expl = step.get("explanation")
        if expl:
            lines.append(f"<p class='meta'>{html.escape(str(expl))}</p>")

        lines.append("<details><summary>LLM / JSON</summary>")
        lines.extend(_render_agent_llm_block(step, llm_record))
        lines.append("<details><summary>observation JSON</summary>")
        lines.append(
            f"<pre>{html.escape(json.dumps(sanitize_observation_for_html(step.get('observation') or {}), indent=2, ensure_ascii=False, default=_json_default))}</pre>"
        )
        lines.append("</details></details></details>")

    lines.append("</div>")
    return lines
