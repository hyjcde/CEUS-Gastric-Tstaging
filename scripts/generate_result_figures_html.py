#!/usr/bin/env python3
"""Emit HTML figure-gallery blocks from figures/results/manifest.json."""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS = PROJECT_ROOT / "docs" / "mainline" / "figures" / "results"
MANIFEST = RESULTS / "manifest.json"

SECTIONS = [
    ("case_agent_", "Agent 在线推理 · 多患者产物（overlay / mask / wall / RAG）"),
    ("case_multimodal_agent_", "Agent 多模态病例面板（pipeline reports）"),
    ("case_regionaware_", "Region-aware / 对比学习 · Grad-CAM 病例"),
    ("case_error_wall_", "误诊 / 胃壁证据 · 错误分析面板"),
    ("case_regionaware_err_", "Region-aware · 错误步审查"),
    ("case_rf_", "外部验证 · 帧级分类面板（莆田 / 肿瘤 / 多中心等）"),
    ("case_pipeline_", "超声病例 · 全流程管线示意（T1–T4+）"),
    ("case_boundary_", "超声病例 · 胃壁边界与浸润（按 T 分期）"),
    ("case_gradcam_", "超声病例 · 四分类 Grad-CAM（正确 / 漏诊 / 误诊）"),
    ("case_t2analysis_", "T2 专项 · 边界与误诊分析"),
    ("case_dinov3_unetpp_", "DINOv3 + UNet++ 分割病例面板"),
    ("case_fusion_", "多模态融合 / VLM 示意"),
    ("case_review_", "医生复核 · 标注与 Grad-CAM 质控"),
    ("case_overlay_", "多中心 Overlay 蒙太奇（外部）"),
    ("study_", "研究总览 · 方向性与形态学统计图"),
    ("seg_", "分割 · ROI · nnU-Net / SAM2 多中心对比"),
    ("metric_", "汇总指标 · scoreboard AUC / 混淆矩阵（eval JSON）"),
]


def caption_from_name(fname: str) -> str:
    stem = fname.replace(".png", "")
    if stem.startswith("case_agent_"):
        rest = stem.replace("case_agent_", "", 1)
        parts = rest.split("_", 1)
        if len(parts) == 2:
            return f"Agent 患者{parts[0]} · {parts[1].replace('_', ' ')}"
        return "Agent · " + rest.replace("_", " ")
    if stem.startswith("case_pipeline_"):
        return "全流程 · " + stem.replace("case_pipeline_", "").replace("_", " ")
    if stem.startswith("case_boundary_"):
        return "胃壁边界 · " + stem.replace("case_boundary_", "").replace("_", " ")
    if stem.startswith("case_gradcam_"):
        return "Grad-CAM · " + stem.replace("case_gradcam_", "").replace("_", " ")
    if stem.startswith("case_rf_"):
        return "外部验证 · " + stem.replace("case_rf_", "").replace("_", " ")
    if stem.startswith("metric_"):
        labels = {
            "metric_auc_comparison": "scoreboard 四分类 AUC（外部/前瞻）",
            "metric_comprehensive_panel": "冻结线四宫格：AUC / val 曲线 / 混淆矩阵",
            "metric_recall_heatmap": "各主线 per-class Recall 热力图",
            "metric_per_class_recall_curves": "冻结线逐类 Recall 柱状图",
            "metric_confusion_dual": "冻结线 外部+前瞻 混淆矩阵",
            "metric_cm_external": "冻结线 · 外部混淆矩阵",
            "metric_cm_prospective": "冻结线 · 前瞻混淆矩阵",
            "metric_directional_rose": "方向性玫瑰图（T2/T3 证据）",
        }
        return labels.get(stem, "指标 · " + stem.replace("metric_", "").replace("_", " "))
    if stem.startswith("seg_"):
        return "分割 · " + stem.replace("seg_", "").replace("_", " ")
    return stem.replace("_", " ")


def main() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    files = sorted(f["file"] for f in data["files"])
    used: set[str] = set()
    parts: list[str] = []

    for prefix, title in SECTIONS:
        group = [f for f in files if f.startswith(prefix)]
        if not group:
            continue
        used.update(group)
        parts.append(f'        <h3>{title}</h3>')
        parts.append('        <div class="figure-gallery">')
        for fname in group:
            cap = caption_from_name(fname)
            span = ' class="span-2"' if any(
                x in fname for x in ("comprehensive", "contact_sheet", "comparison", "overview", "panel")
            ) else ""
            parts.append(f"          <figure{span}>")
            parts.append(f'            <img src="figures/results/{fname}" alt="{cap}" loading="lazy" decoding="async" />')
            parts.append(f"            <figcaption>{cap}</figcaption>")
            parts.append("          </figure>")
        parts.append("        </div>")

    leftover = [f for f in files if f not in used]
    if leftover:
        parts.append("        <h3>其他</h3>")
        parts.append('        <div class="figure-gallery">')
        for fname in leftover:
            cap = caption_from_name(fname)
            parts.append("          <figure>")
            parts.append(f'            <img src="figures/results/{fname}" alt="{cap}" loading="lazy" />')
            parts.append(f"            <figcaption>{cap}</figcaption>")
            parts.append("          </figure>")
        parts.append("        </div>".replace("motion", "motion"))

    out = PROJECT_ROOT / "docs" / "mainline" / "figures" / "results" / "_gallery_body.html"
    # fix div closing in leftover block
    text = "\n".join(parts).replace("</div>", "</div>").replace("<motion ", "<div ")
    out.write_text(text + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(files)} images)")


if __name__ == "__main__":
    main()
