"""Standard gastric ultrasound report layout + Agent evidence annex for HTML exports."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .media_refs import img_tag

from .platform_panels import ScanPlatformPanel, render_platform_panel_grid


US_REPORT_CSS = """
.us-doc { max-width: 880px; margin: 0 auto 48px; padding: 28px 32px 36px;
  border: 1px solid var(--line); border-radius: 6px; background: #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
@media (prefers-color-scheme: dark) {
  .us-doc { background: #141412; box-shadow: none; }
}
.us-doc-title { text-align: center; font-size: 22px; letter-spacing: 0.35em; margin: 0 0 18px; font-weight: 700; }
.us-doc-sub { text-align: center; font-size: 13px; color: var(--muted); margin: -8px 0 20px; }
.us-meta-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 24px; font-size: 14px;
  margin-bottom: 18px; padding-bottom: 14px; border-bottom: 2px solid var(--line); }
.us-meta-grid span.label { color: var(--muted); min-width: 5em; display: inline-block; }
.us-section { margin: 18px 0; }
.us-section h3 { font-size: 15px; margin: 0 0 8px; color: var(--fg); border-left: 3px solid var(--accent2);
  padding-left: 8px; font-weight: 700; }
.us-section p, .us-section li { font-size: 15px; line-height: 1.85; margin: 0.35em 0; }
.us-section ol { margin: 0; padding-left: 1.4em; }
.us-impression { background: rgba(15, 76, 92, 0.06); padding: 12px 14px; border-radius: 4px;
  border-left: 4px solid var(--accent2); }
.us-disclaimer { font-size: 12px; color: var(--muted); margin-top: 16px; line-height: 1.6; }
.us-sign { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 24px;
  font-size: 13px; color: var(--muted); padding-top: 12px; border-top: 1px dashed var(--line); }

.agent-flow { display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0 20px; align-items: stretch; }
.agent-flow-step { flex: 1 1 120px; min-width: 108px; max-width: 160px; padding: 8px 10px;
  border: 1px solid var(--line); border-radius: 6px; background: rgba(0,0,0,0.02); font-size: 11.5px; }
.agent-flow-step .num { font-weight: 700; color: var(--accent2); font-size: 12px; }
.agent-flow-step .sid { font-family: monospace; font-size: 10px; color: var(--muted); }
.agent-flow-step .sum { margin-top: 4px; line-height: 1.35; color: var(--fg); }

.hero-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin: 16px 0; }
@media (max-width: 720px) { .hero-grid { grid-template-columns: 1fr; } }
.hero-card { border: 1px solid var(--line); border-radius: 6px; overflow: hidden; background: rgba(0,0,0,0.02); }
.hero-card figcaption { padding: 8px 10px; font-size: 12.5px; background: var(--tag); border-bottom: 1px solid var(--line); }
.hero-card img { width: 100%; max-height: 280px; object-fit: contain; display: block; background: #000; }

.annex details { margin: 10px 0; }
.annex summary { cursor: pointer; font-weight: 600; color: var(--accent2); }
body.report-v2 { max-width: 980px; }
body.report-v2 h2 { scroll-margin-top: 12px; }
img.fig { max-height: 360px; object-fit: contain; width: 100%; background: rgba(0,0,0,0.04); }
img.fig-wide { max-height: 420px; }
.scan-fig { max-height: 240px !important; width: 100%; object-fit: contain; }
"""


def _step_obs(steps: List[Dict[str, Any]], step_id: str) -> Dict[str, Any]:
    for s in steps:
        if str(s.get("step_id")) == step_id:
            return dict(s.get("observation") or {})
    return {}


def compose_ultrasound_report(
    *,
    case_id: str,
    clinical: Dict[str, Any],
    pipeline_state: Dict[str, Any],
    clip_name: str = "",
) -> Dict[str, Any]:
    """Build 超声所见 / 超声提示 text from structured pipeline outputs."""
    steps = pipeline_state.get("steps") or []
    report = pipeline_state.get("final_report") or {}
    gt = clinical.get("pathology_t_stage") or pipeline_state.get("gt_t_stage") or "—"

    lumen = _step_obs(steps, "lumen_detect")
    seg = _step_obs(steps, "lesion_seg")
    morph = _step_obs(steps, "morphology")
    wall = _step_obs(steps, "wall_evidence")
    cls_primary = _step_obs(steps, "t_staging").get("primary") or _step_obs(steps, "t_staging")
    binary = _step_obs(steps, "binary_gate")

    findings: List[str] = []
    findings.append(
        f"检查部位：胃；检查途径：经腹超声；视频来源：{clip_name or '—'}。"
    )

    if lumen.get("lumen_detected"):
        bb = lumen.get("lumen_bbox") or {}
        findings.append(
            f"胃腔/探头视野定位：可见胃腔回声区（检测置信度 {float(lumen.get('lumen_confidence', 0)):.2f}），"
            f"定位框约 ({bb.get('x1', '?')}, {bb.get('y1', '?')})–({bb.get('x2', '?')}, {bb.get('y2', '?')}) px。"
        )
    else:
        findings.append("胃腔自动定位：未稳定检出 lumen 框，以下病灶描述基于全帧分析。")

    area = seg.get("lesion_area_ratio")
    sel = seg.get("selection") or {}
    if seg.get("mask_available") or area:
        len_cm = clinical.get("tumor_length_cm", "—")
        th_cm = clinical.get("tumor_thickness_cm", "—")
        findings.append(
            f"胃壁病灶：可见低回声区，AI 分割面积占比约 {float(area or 0):.2%}；"
            f"临床记录大小约 {len_cm}×{th_cm} cm；"
            f"分割 backend={sel.get('chosen_backend', 'unet')}。"
        )
    else:
        findings.append("胃壁病灶：自动分割 mask 不可用或为空，形态学指标仅供参考。")

    if morph.get("boundary_irregularity") is not None:
        findings.append(
            f"病灶形态：边界不规则度 {float(morph.get('boundary_irregularity', 0)):.2f}，"
            f"凸度 {float(morph.get('convexity', 0)):.2f}，致密性 {float(morph.get('solidity', 0)):.2f}。"
        )

    if wall.get("available"):
        wf = wall.get("wall_features") or {}
        findings.append(
            f"壁层/浆膜面：SDF 壁层证据 penetration_risk={wall.get('penetration_risk', '?')}，"
            f"灶外占比 {float(wf.get('fraction_outside_lumen', 0)):.2%}，"
            f"最大外侵深度约 {float(wf.get('max_outward_depth', 0)):.1f} px。"
        )

    probs = (cls_primary.get("probabilities") or {}) if isinstance(cls_primary, dict) else {}
    if probs:
        prob_str = " / ".join(f"{k} {float(probs.get(k, 0)):.2f}" for k in ("T1", "T2", "T3", "T4+"))
        findings.append(f"AI T 分期概率（L1 分类）：{prob_str}。")

    gate = binary.get("gate_decision") or binary.get("primary_frame", {}).get("gate_decision")
    if gate:
        findings.append(f"L0 良恶性闸门：{gate}（triage_path={pipeline_state.get('triage_path', '—')}）。")

    rec = report.get("recommended_t_stage", "?")
    conf = report.get("confidence", "?")
    impression: List[str] = [
        f"AI 综合推荐 cT 分期：{rec}（置信度 {conf}）。",
        f"病理/参考标准 T 分期（如有）：{gt}。",
    ]
    if report.get("supporting_evidence"):
        impression.append("主要依据：" + "；".join(str(x) for x in report["supporting_evidence"][:3]) + "。")
    if report.get("uncertainty_flags"):
        impression.append("注意：" + "；".join(str(x) for x in report["uncertainty_flags"][:2]) + "。")
    impression.append(
        "本报告由 GastricTstaging Agent 系统自动生成，仅供科研/辅助参考，"
        "不能替代医师签发的正式超声诊断报告。"
    )

    return {
        "findings": findings,
        "impression": impression,
        "recommended_t_stage": rec,
        "confidence": conf,
        "gt_t_stage": gt,
    }


def render_standard_ultrasound_report_html(
    *,
    case_id: str,
    clinical: Dict[str, Any],
    us_text: Dict[str, Any],
    generated_at: Optional[str] = None,
) -> List[str]:
    """Hospital-style 超声检查报告 header block."""
    pid = clinical.get("display_id") or clinical.get("patient_id") or case_id
    sex = clinical.get("sex", "—")
    age = clinical.get("age", "—")
    loc = clinical.get("tumor_location", "—")
    ts = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    lines = [
        '<div class="us-doc" id="us-report">',
        '<div class="us-doc-title">超声检查报告</div>',
        '<div class="us-doc-sub">（AI Agent 辅助生成 · 科研/内部阅片）</div>',
        '<div class="us-meta-grid">',
        f'<div><span class="label">姓名/ID</span> {html.escape(str(pid))}</div>',
        f'<div><span class="label">病例</span> {html.escape(case_id)}</div>',
        f'<div><span class="label">性别</span> {html.escape(str(sex))}</div>',
        f'<div><span class="label">年龄</span> {html.escape(str(age))} 岁</div>',
        f'<div><span class="label">检查部位</span> 胃</div>',
        f'<div><span class="label">病灶部位</span> {html.escape(str(loc))}</div>',
        f'<div><span class="label">检查方法</span> 经腹超声 · 视频 Agent 分析</div>',
        f'<div><span class="label">报告时间</span> {html.escape(ts)} UTC</div>',
        "</div>",
        '<div class="us-section">',
        "<h3>超声所见</h3>",
        "<ol>",
    ]
    for item in us_text.get("findings") or []:
        lines.append(f"<li>{html.escape(str(item))}</li>")
    lines.extend([
        "</ol>",
        "</div>",
        '<div class="us-section us-impression">',
        "<h3>超声提示</h3>",
        "<ol>",
    ])
    for item in us_text.get("impression") or []:
        lines.append(f"<li>{html.escape(str(item))}</li>")
    lines.extend([
        "</ol>",
        "</div>",
        '<p class="us-disclaimer">'
        "免责声明：上述内容为多 Agent 流水线（分割 / 分类 / 壁层证据 / Case-RAG）"
        "自动汇总结果，需经超声科医师结合原始图像及临床资料审核后方能用于临床决策。"
        "</p>",
        '<div class="us-sign">',
        "<div>报告医师：________________（AI 辅助草稿）</div>",
        "<div>审核医师：________________</div>",
        "</div>",
        "</div>",
    ])
    return lines


def render_agent_flow_timeline(steps: List[Dict[str, Any]]) -> List[str]:
    """Compact 12-step Agent pipeline overview."""
    from .full_report import _step_detail

    lines = [
        "<h2>Agent 分析流程</h2>",
        "<p class='meta'>12 步 LangGraph 生产流水线 · 左→右为执行顺序</p>",
        '<div class="agent-flow">',
    ]
    for s in sorted(steps, key=lambda x: int(x.get("step") or 0)):
        n = int(s.get("step") or 0)
        sid = html.escape(str(s.get("step_id", "")))
        status = str(s.get("status", "?"))
        badge_cls = "ok" if status == "completed" else "warn" if status in ("partial", "skipped") else "bad"
        detail = html.escape(_step_detail(s)[:72])
        lines.append(
            f'<div class="agent-flow-step">'
            f'<div class="num">Step {n:02d}</div>'
            f'<div class="sid">{sid}</div>'
            f'<span class="badge {badge_cls}">{html.escape(status)}</span>'
            f'<div class="sum">{detail}</div></div>'
        )
    lines.append("</div>")
    return lines


def render_hero_evidence_grid(
    platform_panels: Dict[str, List[ScanPlatformPanel]],
    *,
    step_figures: Optional[Dict[str, Path]] = None,
    html_path: Path,
) -> List[str]:
    """Key figures for clinical reading: seg overlay, lumen, T-stage, DINO."""
    step_figures = step_figures or {}
    heroes: List[tuple[str, Path, str]] = []

    def _panel_path(step_id: str, key: str) -> Optional[Path]:
        for p in platform_panels.get(step_id) or []:
            if p.key == key and p.image_path.is_file():
                return p.image_path
        return None

    candidates = [
        ("lesion_seg", "predicted_overlay", "病灶分割叠加"),
        ("lumen_detect", "lumen_overlay", "胃腔定位 (YOLO)"),
        ("t_staging", "dino_multimodal", "DINO 多模态 + T 概率"),
        ("t_staging", "classification_probs", "T 分期概率"),
        ("wall_evidence", "real_wall_panel", "壁层 SDF 分析"),
        ("t_staging", None, "L1 Grad-CAM"),  # from step fig
    ]
    for step_id, key, title in candidates:
        path = _panel_path(step_id, key) if key else None
        if path is None and step_id == "t_staging":
            path = step_figures.get("step-08-tstage")
        if path and path.is_file():
            heroes.append((title, path, step_id))

    if not heroes:
        return []

    lines = [
        "<h2>关键影像图</h2>",
        "<p class='meta'>阅片用核心图（固定高度，便于打印）；完整 Agent 图见下方附录。</p>",
        '<div class="hero-grid">',
    ]
    for title, path, sid in heroes[:6]:
        lines.append("<figure class='hero-card'>")
        lines.append(f"<figcaption>{html.escape(title)} · <code>{html.escape(sid)}</code></figcaption>")
        tag = img_tag(html_path, path, css_class="", alt=title)
        if tag:
            lines.append(tag)
        lines.append("</figure>")
    lines.append("</div>")
    return lines
