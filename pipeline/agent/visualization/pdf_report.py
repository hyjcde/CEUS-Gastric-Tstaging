"""PDF report assembled from pre-rendered pipeline state (no model re-run)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..pipeline.state import CasePipelineState


def render_pipeline_pdf_report(state: "CasePipelineState", out_path: Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    ci = state.case_input
    report = state.final_report or {}

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=1.2 * cm,
        rightMargin=1.2 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.0 * cm,
        title=f"Agent Pipeline · {ci.case_id}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title",
        parent=styles["Title"],
        fontName="STSong-Light",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0f4c5c"),
    )
    h2 = ParagraphStyle(
        "h2",
        parent=styles["Heading2"],
        fontName="STSong-Light",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#7a2e0f"),
        spaceBefore=6,
        spaceAfter=4,
    )
    body = ParagraphStyle(
        "body",
        parent=styles["BodyText"],
        fontName="STSong-Light",
        fontSize=9,
        leading=12,
    )

    story = [
        Paragraph(f"Agent 完整流程报告 · {ci.case_id}", title_style),
        Spacer(1, 0.3 * cm),
        Paragraph(
            f"patient={ci.patient_id} · mode={ci.input_mode.value} · "
            f"GT={ci.gt_t_stage or '?'}",
            body,
        ),
        Spacer(1, 0.4 * cm),
        Paragraph(
            f"<b>推荐 T 分期</b>：{report.get('recommended_t_stage', '?')} · "
            f"置信度={report.get('confidence', '?')} · "
            f"triage={report.get('triage_path', state.triage_path)}",
            body,
        ),
    ]
    for ev in (report.get("supporting_evidence") or [])[:6]:
        story.append(Paragraph(f"• {ev}", body))

    story.append(PageBreak())
    story.append(Paragraph("逐步结果", h2))

    usable_w = A4[0] - 2.4 * cm
    for step in state.steps:
        story.append(
            Paragraph(
                f"Step {step.step:02d} · {step.agent_name} "
                f"({step.status}, {step.elapsed_s:.2f}s)",
                h2,
            )
        )
        if step.explanation:
            story.append(Paragraph(step.explanation, body))
        for fig in step.figure_paths:
            fp = Path(fig)
            if fp.exists():
                story.append(Image(str(fp), width=usable_w, height=usable_w * 0.55))
                story.append(Spacer(1, 0.2 * cm))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.build(story)
    return out_path
