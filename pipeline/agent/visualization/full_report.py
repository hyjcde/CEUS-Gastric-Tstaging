"""Rich HTML reports: single-case and multi-case batch (reads pipeline cache only)."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from ..pipeline.state import CasePipelineState

import numpy as np

from .html_format import sanitize_observation_for_html, slim_for_html_report
from .media_refs import img_tag


def _json_default(obj: Any) -> Any:
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


FULL_REPORT_CSS = """
:root { --bg:#fafaf7; --fg:#1a1a1a; --muted:#5a5a5a; --line:#d6d3cc;
        --accent:#7a2e0f; --accent2:#0f4c5c; --ok:#2c6e3e; --warn:#8a5a00; --bad:#8a1c1c;
        --codebg:#f1efe9; --tag:#efe9dc; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0e0e0c; --fg:#e8e6df; --muted:#9a958a; --line:#2a2a26;
          --accent:#d68b6c; --accent2:#7ad2d4; --codebg:#1c1c18; --tag:#1f1d18; }
}
* { box-sizing: border-box; }
html, body { background: var(--bg); color: var(--fg); }
body {
  font-family: "Times New Roman", "Source Han Serif SC", "Noto Serif CJK SC", serif;
  max-width: 1200px; margin: 0 auto; padding: 32px 36px 96px;
  line-height: 1.7; font-size: 15.5px;
}
h1 { font-size: 30px; margin: 0 0 4px; }
h2 { font-size: 22px; margin: 36px 0 10px; padding-top: 12px; border-top: 1px solid var(--line); }
h3 { font-size: 17.5px; margin: 22px 0 8px; color: var(--accent2); }
small, .meta { color: var(--muted); font-size: 12.5px; }
a { color: var(--accent); text-decoration: none; border-bottom: 1px dotted var(--accent); }
table { width:100%; border-collapse: collapse; margin: 8px 0 16px; font-size: 14px; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { background: var(--tag); font-weight: 600; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
code, pre { font-family: "JetBrains Mono", "SFMono-Regular", "Consolas", monospace; font-size: 13px; line-height: 1.5; }
code { background: var(--codebg); padding: 1px 5px; border-radius: 3px; }
pre { background: var(--codebg); padding: 12px 14px; border-radius: 4px; overflow-x: auto; border-left: 3px solid var(--accent2); white-space: pre-wrap; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 12px; font-family: monospace; }
.badge.ok { background:#d6e9d8; color:var(--ok); border:1px solid #b6d4bb; }
.badge.warn { background:#f1e3d2; color:var(--warn); border:1px solid #d8c39e; }
.badge.bad { background:#f1d4d4; color:var(--bad); border:1px solid #d8a6a6; }
.badge.muted { background:#ece9df; color:var(--muted); border:1px solid #d6d3cc; }
.agent-section { margin: 24px 0; padding: 16px 18px; border-left: 4px solid var(--accent);
  background: rgba(122, 46, 15, 0.04); border-radius: 0 4px 4px 0; }
.agent-section h3 { margin-top: 0; }
img.fig { width: 100%; display: block; margin: 12px 0; border: 1px solid var(--line); border-radius: 3px; }
.footer { margin-top: 40px; padding-top: 12px; border-top: 1px solid var(--line); color: var(--muted); font-size: 12.5px; }
"""

SCAN_PLATFORM_CSS = """
    scan-panel-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin: 14px 0 20px; }
@media (max-width: 640px) {
  .scan-panel-grid { grid-template-columns: 1fr; }
}
.scan-panel { margin: 0; padding: 10px 12px; border: 1px solid var(--line); border-radius: 6px; background: rgba(0,0,0,0.02); }
.scan-panel figcaption { margin-bottom: 8px; font-size: 13px; line-height: 1.45; }
.scan-fig { margin: 0; max-height: 420px; object-fit: contain; }
.scan-panel-meta { margin: 8px 0 0; padding-left: 18px; font-size: 11.5px; color: var(--muted); }
"""

from .html_format import LLM_REPORT_CSS
from .ultrasound_report import US_REPORT_CSS

FULL_REPORT_CSS = FULL_REPORT_CSS + LLM_REPORT_CSS + SCAN_PLATFORM_CSS + US_REPORT_CSS

STEP_COLORS = {
    "triage": "#5a4a8a",
    "frame_extract": "#0f4c5c",
    "quality": "#4a3b6b",
    "binary_gate": "#2c6e3e",
    "lumen_detect": "#7ad2d4",
    "lesion_seg": "#d68b6c",
    "morphology": "#7a8a1f",
    "t_staging": "#8a5a00",
    "wall_evidence": "#5a1010",
    "dinov3_seg": "#3a7a8a",
    "case_rag": "#0f4c5c",
    "report_synth": "#7a2e0f",
}


def _figure_img(path: Path, html_path: Path, css_class: str = "fig") -> str:
    return img_tag(html_path, path, css_class=css_class, alt=path.name)


def _badge(status: str) -> str:
    if status in ("completed", "ok"):
        return f'<span class="badge ok">{html.escape(status)}</span>'
    if status in ("skipped", "partial"):
        return f'<span class="badge warn">{html.escape(status)}</span>'
    if status in ("failed", "unavailable"):
        return f'<span class="badge bad">{html.escape(status)}</span>'
    return f'<span class="badge muted">{html.escape(status)}</span>'


def render_agent_trace_sections(
    steps: List[Dict[str, Any]],
    *,
    html_path: Optional[Path] = None,
) -> List[str]:
    """Expandable HTML blocks with full agent inputs/outputs per step."""

    def _jd(obj: Any) -> str:
        return json.dumps(obj, indent=2, ensure_ascii=False, default=_json_default)

    lines = [
        "<h2>Agent 调用全记录</h2>",
        "<p class='meta'>每步 Agent 的 inputs、observation、explanation 与 figure 路径完整保留 "
        "（来源 <code>agent_audit.json</code> / <code>pipeline_state.json</code>）。</p>",
    ]
    for s in steps:
        sid = str(s.get("step_id", ""))
        color = STEP_COLORS.get(sid, "#7a2e0f")
        agent = html.escape(str(s.get("agent_name", "?")))
        status = str(s.get("status", "?"))
        lines.append(
            f'<details class="agent-trace" style="border-left:4px solid {color};'
            f'margin:12px 0;padding:8px 14px;background:rgba(122,46,15,0.04);border-radius:0 4px 4px 0">'
        )
        step_n = int(s.get("step") or 0)
        lines.append(
            f"<summary><b>Step {step_n:02d}</b> · {agent} · "
            f"{_badge(status)} · {float(s.get('elapsed_s', 0)):.2f}s · "
            f"<code>{html.escape(sid)}</code></summary>"
        )
        if s.get("explanation"):
            lines.append(f"<p>{html.escape(str(s['explanation']))}</p>")
        if s.get("tool_name"):
            lines.append(f"<p class='meta'>tool: <code>{html.escape(str(s['tool_name']))}</code></p>")
        if s.get("inputs"):
            lines.append("<h4>Inputs</h4>")
            lines.append(
                f"<pre>{html.escape(json.dumps(slim_for_html_report(s['inputs']), indent=2, ensure_ascii=False, default=_json_default))}</pre>"
            )
        lines.append("<h4>Observation</h4>")
        lines.append(
            f"<pre>{html.escape(json.dumps(sanitize_observation_for_html(s.get('observation') or {}), indent=2, ensure_ascii=False, default=_json_default))}</pre>"
        )
        for fig in s.get("figure_paths") or []:
            fp = Path(fig)
            if html_path is not None and fp.is_file():
                lines.append(_figure_img(fp, html_path))
            elif fp.is_file():
                lines.append(f"<p class='meta'>figure: <code>{html.escape(str(fp))}</code></p>")
        lines.append("</details>")
    return lines


def _step_detail(step: Dict[str, Any]) -> str:
    obs = step.get("observation") or {}
    sid = step.get("step_id", "")
    if sid == "wall_evidence":
        if obs.get("available"):
            return f"SDF risk={obs.get('penetration_risk', '?')}"
        return obs.get("error", "unavailable")
    if sid == "case_rag":
        if obs.get("available") is False:
            return obs.get("reason", "skipped")
        hits = obs.get("similar_cases") or []
        sd = obs.get("stage_distribution") or {}
        return f"hits={len(hits)} dist={sd}"
    if sid == "binary_gate":
        pf = obs.get("primary_frame") or obs
        return f"gate={pf.get('gate_decision', '?')} top1={pf.get('top1_label', '?')}"
    if sid == "t_staging":
        primary = obs.get("primary") or obs
        return f"{primary.get('top1_stage', '?')} p={primary.get('top1_prob', '?')}"
    if sid == "lumen_detect":
        return f"detected={obs.get('lumen_detected')} conf={obs.get('lumen_confidence', 0)}"
    if sid == "lesion_seg":
        sel = obs.get("selection") or {}
        if sel:
            return (
                f"chosen={sel.get('chosen_backend')} unet={sel.get('unet_score')} "
                f"dino={sel.get('dinov3_score')} area={obs.get('lesion_area_ratio', 0)}"
            )
        return f"mask={obs.get('mask_available')} area={obs.get('lesion_area_ratio', 0)}"
    if step.get("explanation"):
        return str(step["explanation"])[:120]
    return str(obs)[:100]


def render_pipeline_html_report(state: "CasePipelineState", out_path: Path) -> Path:
    """Single-case HTML from pipeline state + pre-rendered figures."""
    ci = state.case_input
    report = state.final_report or {}
    run_dir = state.out_dir
    six_panel = run_dir / "figures" / f"{ci.case_id}_6panel.png"

    lines = [
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>",
        f"<title>{ci.case_id} · Agent 完整流程报告</title>",
        f"<meta name='viewport' content='width=device-width,initial-scale=1' />",
        f"<style>{FULL_REPORT_CSS}</style></head><body>",
        "<header>",
        f"<h1>Agent 完整流程报告 · {html.escape(ci.case_id)}</h1>",
        f"<p class='meta'>patient={html.escape(ci.patient_id)} · mode={ci.input_mode.value} · "
        f"GT={html.escape(str(ci.gt_t_stage or '?'))} · "
        f"generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>",
        "</header>",
        "<h2>综合结论</h2>",
        "<table class='kvtable'>",
        f"<tr><th>推荐 T 分期</th><td><b>{html.escape(str(report.get('recommended_t_stage', '?')))}</b></td></tr>",
        f"<tr><th>置信度</th><td>{html.escape(str(report.get('confidence', '?')))}</td></tr>",
        f"<tr><th>Triage 路径</th><td>{html.escape(str(report.get('triage_path', state.triage_path or '?')))}</td></tr>",
        "</table>",
    ]
    if report.get("supporting_evidence"):
        lines.append("<ul>")
        for ev in report["supporting_evidence"][:8]:
            lines.append(f"<li>{html.escape(str(ev))}</li>")
        lines.append("</ul>")

    if six_panel.exists():
        lines.append("<h2>六联图（Lumen / Seg / L0 / L1+Grad-CAM / Wall / RAG）</h2>")
        lines.append(_figure_img(six_panel, out_path))

    lines.append("<h2>12 步逐步结果</h2>")
    for step in state.steps:
        color = STEP_COLORS.get(step.step_id, "#7a2e0f")
        lines.append(f'<section class="agent-section" style="border-left-color:{color};">')
        lines.append(
            f"<h3>Step {step.step:02d} · {html.escape(step.agent_name)} "
            f"{_badge(step.status)} · {step.elapsed_s:.2f}s</h3>"
        )
        if step.explanation:
            lines.append(f"<p>{html.escape(step.explanation)}</p>")
        lines.append(f"<p class='meta'><code>{html.escape(step.step_id)}</code> · {_step_detail(step.to_dict())}</p>")
        for fig in step.figure_paths:
            fp = Path(fig)
            if fp.is_file():
                lines.append(_figure_img(fp, out_path))
        lines.append("</section>")

    lines.append(
        f'<p class="footer">GastricTstaging unified pipeline · run_dir={html.escape(str(run_dir))}</p>'
    )
    lines.append("</body></html>")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def render_batch_full_report(
    run_root: Path,
    out_path: Path,
    *,
    title: Optional[str] = None,
) -> Path:
    """Multi-case consolidated HTML from batch pipeline runs (no model re-run)."""
    cases: List[Dict[str, Any]] = []
    for child in sorted(run_root.iterdir()):
        summary = child / "pipeline_state.json"
        if not summary.exists():
            continue
        doc = json.loads(summary.read_text(encoding="utf-8"))
        report = doc.get("final_report") or {}
        gt = doc.get("gt_t_stage")
        pred = report.get("recommended_t_stage")
        steps = doc.get("steps") or []
        wall = next((s for s in steps if s.get("step_id") == "wall_evidence"), {})
        rag = next((s for s in steps if s.get("step_id") == "case_rag"), {})
        total_s = sum(float(s.get("elapsed_s", 0)) for s in steps)
        cases.append(
            {
                "case_id": doc.get("case_id"),
                "patient_id": doc.get("patient_id"),
                "gt": gt,
                "pred": pred,
                "match": gt == pred if gt and pred else None,
                "triage": report.get("triage_path") or doc.get("triage_path"),
                "elapsed_s": round(total_s, 2),
                "wall_ok": (wall.get("observation") or {}).get("available"),
                "rag_ok": (rag.get("observation") or {}).get("available"),
                "run_dir": child,
                "steps": steps,
                "report": report,
            }
        )

    title = title or f"Agent 完整流程 · {run_root.name}"
    lines = [
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>",
        f"<title>{html.escape(title)}</title>",
        f"<meta name='viewport' content='width=device-width,initial-scale=1' />",
        f"<style>{FULL_REPORT_CSS}</style></head><body>",
        f"<h1>{html.escape(title)}</h1>",
        f"<p class='meta'>cases={len(cases)} · source={html.escape(str(run_root))} · "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>",
        "<h2>汇总表</h2>",
        "<table><tr><th>Case</th><th>GT</th><th>Pred</th><th>Match</th>"
        "<th>Triage</th><th>Wall</th><th>RAG</th><th>耗时(s)</th><th>单例报告</th></tr>",
    ]
    for c in cases:
        match = "✓" if c["match"] is True else ("✗" if c["match"] is False else "?")
        wall = "✓" if c["wall_ok"] else "—"
        rag = "✓" if c["rag_ok"] else "—"
        rel = f"{c['case_id']}/report.html"
        lines.append(
            f"<tr><td>{html.escape(c['case_id'] or '')}</td>"
            f"<td>{html.escape(str(c.get('gt') or '?'))}</td>"
            f"<td>{html.escape(str(c.get('pred') or '?'))}</td>"
            f"<td>{match}</td>"
            f"<td>{html.escape(str(c.get('triage') or '?'))}</td>"
            f"<td>{wall}</td><td>{rag}</td>"
            f"<td class='num'>{c['elapsed_s']}</td>"
            f"<td><a href='{html.escape(rel)}'>report</a></td></tr>"
        )
    lines.append("</table>")

    for c in cases:
        run_dir: Path = c["run_dir"]
        case_id = c["case_id"]
        six_panel = run_dir / "figures" / f"{case_id}_6panel.png"
        lines.append(f"<h2 id='{case_id}'>{html.escape(case_id)} · patient {html.escape(str(c.get('patient_id', '')))}</h2>")
        lines.append(
            f"<p>GT <b>{html.escape(str(c.get('gt') or '?'))}</b> → "
            f"Pred <b>{html.escape(str(c.get('pred') or '?'))}</b> · "
            f"triage={html.escape(str(c.get('triage') or '?'))}</p>"
        )
        if six_panel.exists():
            lines.append(_figure_img(six_panel, out_path))
        lines.append("<table><tr><th>#</th><th>Step</th><th>Status</th><th>Detail</th><th>s</th></tr>")
        for s in c["steps"]:
            lines.append(
                f"<tr><td>{s.get('step', '?')}</td>"
                f"<td><code>{html.escape(str(s.get('step_id', '')))}</code></td>"
                f"<td>{_badge(str(s.get('status', '?')))}</td>"
                f"<td>{html.escape(_step_detail(s))}</td>"
                f"<td class='num'>{float(s.get('elapsed_s', 0)):.2f}</td></tr>"
            )
        lines.append("</table>")

    lines.append('<p class="footer">Unified 12-step pipeline · models run once · reports read pipeline_state.json</p>')
    lines.append("</body></html>")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
