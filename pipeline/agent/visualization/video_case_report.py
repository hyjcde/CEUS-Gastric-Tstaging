"""CASE-001 video-centric HTML: external media refs, frame pick, FM/MedSAM-family seg."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .execution_trace import (
    render_agent_execution_table,
    render_execution_mode_notice,
    render_llm_section,
    render_model_invocation_table,
)
from .full_report import FULL_REPORT_CSS, _badge, _step_detail, render_agent_trace_sections
from .media_refs import ensure_assets_dir, img_tag, rel_href, stage_file, video_tag
from .step_narratives import (
    render_per_agent_main_visual_sections,
    render_step_narrative_sections,
)
from .ultrasound_report import (
    compose_ultrasound_report,
    render_agent_flow_timeline,
    render_hero_evidence_grid,
    render_standard_ultrasound_report_html,
)


@dataclass
class VideoReportAssets:
    case_id: str
    clip_path: Path
    clip_relpath: str
    video_meta: Dict[str, Any]
    sampled_frames: List[Any]
    key_frame_paths: List[Path]
    figures: Dict[str, Path]  # name -> png path on disk
    clinical: Dict[str, Any]
    pipeline_state: Optional[Dict[str, Any]] = None
    agent_audit: Optional[Dict[str, Any]] = None
    pipeline_options: Optional[Dict[str, Any]] = None
    step_figures: Optional[Dict[str, Path]] = None  # stem -> png path
    execution_trace: Optional[Dict[str, Any]] = None
    llm_record: Optional[Dict[str, Any]] = None
    llm_trace: Optional[Dict[str, Any]] = None
    preprocess_mode: str = "reader_study"
    preprocess_sample_id: Optional[str] = None
    platform_panels: Optional[Dict[str, Any]] = None
    platform_meta: Optional[Dict[str, Any]] = None
    pipeline_dir: Optional[Path] = None


def _clip_asset_suffix(clip_name: str) -> str:
    """clip_01.mp4 → 01"""
    stem = Path(clip_name).stem  # clip_01
    if stem.startswith("clip_"):
        return stem.replace("clip_", "")
    return "01"


def _save_matplotlib_fig(fig, out_path: Path, *, dpi: int = 140) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=dpi, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return out_path


def render_video_preprocess_panel(
    primary_frame_path: Path,
    case_dir: Path,
    clip_name: str = "clip_01.mp4",
    *,
    reader_sync_index: Optional[int] = None,
    prospective_sync: Optional[Path] = None,
    prospective_overlay: Optional[Path] = None,
    prospective_roi: Optional[Path] = None,
    prospective_sample_id: Optional[str] = None,
    out_path: Optional[Path] = None,
) -> Path:
    """
    Preprocess visualization aligned with pipeline primary key frame.

    Panel ① = agent primary key frame (from this clip).
    Panels ②–④ = reader pack sync/ui/roi, or prospective crop_ui 标注链路（②③④ 同源）。
    """
    img_bgr = cv2.imread(str(primary_frame_path))
    if img_bgr is None:
        raise FileNotFoundError(f"Primary key frame not readable: {primary_frame_path}")

    panels: List[Tuple[str, np.ndarray, str]] = [
        (
            f"① Pipeline 主关键帧\n{primary_frame_path.name}",
            cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB),
            "从 clip 按 motion+sharpness 选取 · 下游模型输入",
        ),
    ]

    if prospective_sync and prospective_sync.exists():
        sid = prospective_sample_id or prospective_sync.stem
        sync_img = cv2.imread(str(prospective_sync))
        if sync_img is not None:
            panels.append((
                f"② 标注静帧\n{prospective_sync.name}",
                cv2.cvtColor(sync_img, cv2.COLOR_BGR2RGB),
                f"crop_ui 标注关键帧 · {sid}",
            ))
        if prospective_overlay and prospective_overlay.exists():
            ov = cv2.imread(str(prospective_overlay))
            if ov is not None:
                panels.append((
                    f"③ 病灶 overlay\n{prospective_overlay.name}",
                    cv2.cvtColor(ov, cv2.COLOR_BGR2RGB),
                    "与 ② 同帧 · polygon 标注叠加",
                ))
        if prospective_roi and prospective_roi.exists():
            roi = cv2.imread(str(prospective_roi))
            if roi is not None:
                panels.append((
                    f"④ ROI 裁切\n{prospective_roi.name}",
                    cv2.cvtColor(roi, cv2.COLOR_BGR2RGB),
                    "与 ② 同帧 · crop_roi 病灶裁切",
                ))
    else:
        suffix = (
            f"{reader_sync_index:02d}"
            if reader_sync_index is not None
            else _clip_asset_suffix(clip_name)
        )
        sync_p = case_dir / f"sync_{suffix}.jpg"
        ui_p = case_dir / f"ui_{suffix}.jpg"
        roi_p = case_dir / f"roi_{suffix}.jpg"
        if sync_p.exists():
            panels.append((
                f"② sync_{suffix}.jpg (reader)",
                cv2.cvtColor(cv2.imread(str(sync_p)), cv2.COLOR_BGR2RGB),
                "阅片包同步静帧 · 与 clip 配对",
            ))
        if ui_p.exists():
            panels.append((
                f"③ ui_{suffix}.jpg (reader)",
                cv2.cvtColor(cv2.imread(str(ui_p)), cv2.COLOR_BGR2RGB),
                "reader UI 全幅选框",
            ))
        if roi_p.exists():
            panels.append((
                f"④ roi_{suffix}.jpg (reader)",
                cv2.cvtColor(cv2.imread(str(roi_p)), cv2.COLOR_BGR2RGB),
                "reader 病灶 ROI 裁切",
            ))

    fig, axes = plt.subplots(1, len(panels), figsize=(5.5 * len(panels), 6.2))
    if len(panels) == 1:
        axes = [axes]
    fig.patch.set_facecolor("#0e0e0c")
    for ax, (title, img, caption) in zip(axes, panels):
        ax.imshow(img)
        h, w = img.shape[:2]
        ax.set_title(f"{title}\n{w}×{h}", color="#e8e6df", fontsize=10, loc="left")
        ax.text(0.02, 0.02, caption, transform=ax.transAxes, color="#cdb89a", fontsize=8, va="bottom")
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color("#3a3a32")
    fig.suptitle(
        f"关键帧 + Reader 预处理 · {clip_name} · ① 与 Agent 同源",
        color="#e8e6df",
        fontsize=13,
        y=0.99,
    )
    plt.tight_layout(rect=(0, 0, 1, 0.94))
    if out_path is None:
        raise ValueError("out_path required for preprocess panel PNG")
    return _save_matplotlib_fig(fig, out_path, dpi=140)


def render_key_frames_grid(
    key_frame_paths: List[Path],
    key_labels: List[str],
    *,
    out_path: Path,
) -> Path:
    """4-up grid of pipeline key frames."""
    n = len(key_frame_paths)
    fig, axes = plt.subplots(1, n, figsize=(4.5 * n, 4.5))
    if n == 1:
        axes = [axes]
    fig.patch.set_facecolor("#0e0e0c")
    for ax, path, label in zip(axes, key_frame_paths, key_labels):
        img = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
        ax.imshow(img)
        ax.set_title(label, color="#e8e6df", fontsize=9, loc="left")
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle("Pipeline 4 关键帧（与 Step 2 FrameExtractAgent 一致）", color="#e8e6df", fontsize=12)
    plt.tight_layout()
    return _save_matplotlib_fig(fig, out_path, dpi=130)


def stage_report_video(clip_path: Path, assets_dir: Path) -> Path:
    """Copy/link source mp4 into report assets (avoid base64 embed)."""
    dest = assets_dir / "video" / clip_path.name
    return stage_file(clip_path, dest, copy=True)


def render_fm_seg_on_keyframes(
    key_frame_paths: List[Path],
    key_labels: List[str],
    seg_tool: Any,
    dino_tool: Any,
    *,
    out_path: Path,
) -> Path:
    """UNet vs DINOv3 (MedSAM-family FM) overlay grid on video key frames."""
    n = len(key_frame_paths)
    fig, axes = plt.subplots(n, 2, figsize=(12, 3.8 * n))
    fig.patch.set_facecolor("#0e0e0c")
    if n == 1:
        axes = np.array([axes])
    for row, (path, label) in enumerate(zip(key_frame_paths, key_labels)):
        img_bgr = cv2.imread(str(path))
        if img_bgr is None:
            continue
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        # UNet
        seg_obs = seg_tool.execute(image_path=str(path))
        unet_overlay = img_rgb.copy()
        mask = None
        if hasattr(seg_tool, "get_cached_mask"):
            mask = seg_tool.get_cached_mask(str(path))
        if mask is not None and mask.any():
            m = (mask > 127).astype(np.uint8)
            for c in range(3):
                unet_overlay[..., c] = np.where(
                    m > 0,
                    (0.55 * unet_overlay[..., c] + 0.45 * np.array([220, 90, 30])[c]).astype(np.uint8),
                    unet_overlay[..., c],
                )
        axes[row, 0].imshow(unet_overlay)
        axes[row, 0].set_title(
            f"{label} · UNet ConvNeXt-B · area={seg_obs.get('lesion_area_ratio', 0)}",
            color="#e8e6df",
            fontsize=10,
            loc="left",
        )
        # DINOv3 / FM candidate
        dino_overlay = img_rgb.copy()
        try:
            dino_obs = dino_tool.execute(image_path=str(path))
            dino_mask = dino_obs.get("_mask_array")
            if dino_mask is None and hasattr(dino_tool, "get_cached_mask"):
                dino_mask = dino_tool.get_cached_mask(str(path))
            if dino_mask is not None and np.asarray(dino_mask).any():
                m = (np.asarray(dino_mask) > 127).astype(np.uint8)
                for c in range(3):
                    dino_overlay[..., c] = np.where(
                        m > 0,
                        (0.55 * dino_overlay[..., c] + 0.45 * np.array([90, 180, 220])[c]).astype(np.uint8),
                        dino_overlay[..., c],
                    )
            subtitle = f"DINOv3 FM · mask={dino_obs.get('mask_available', False)}"
        except Exception as exc:
            subtitle = f"DINOv3 unavailable: {exc}"
        axes[row, 1].imshow(dino_overlay)
        axes[row, 1].set_title(f"{label} · {subtitle}", color="#e8e6df", fontsize=10, loc="left")
        for ax in axes[row]:
            ax.set_xticks([])
            ax.set_yticks([])
    fig.suptitle(
        "MedSAM / Foundation Model 视频关键帧分割 · UNet vs DINOv3 candidate",
        color="#e8e6df",
        fontsize=13,
        y=0.995,
    )
    plt.tight_layout(rect=(0, 0, 1, 0.97))
    return _save_matplotlib_fig(fig, out_path, dpi=140)


def render_case_video_html(assets: VideoReportAssets, out_path: Path) -> Path:
    ci = assets.clinical
    ps = assets.pipeline_state or {}
    report = ps.get("final_report") or {}
    steps = ps.get("steps") or []
    vm = assets.video_meta
    clip_name = Path(assets.clip_relpath).name

    us_text = compose_ultrasound_report(
        case_id=assets.case_id,
        clinical=ci,
        pipeline_state=ps,
        clip_name=clip_name,
    )

    assets_dir = ensure_assets_dir(out_path)
    staged_video = stage_report_video(assets.clip_path, assets_dir)

    lines = [
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>",
        f"<title>{html.escape(assets.case_id)} · 超声 Agent 报告</title>",
        "<meta name='viewport' content='width=device-width,initial-scale=1' />",
        f"<style>{FULL_REPORT_CSS}</style></head>",
        "<body class='report-v2'>",
        f"<h1>{html.escape(assets.case_id)} · 胃癌超声 Agent 分析报告</h1>",
        f"<p class='meta'>{html.escape(clip_name)} · "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · "
        f"病理参考 {html.escape(str(us_text.get('gt_t_stage', '?')))} · "
        f"AI 推荐 <b>{html.escape(str(us_text.get('recommended_t_stage', '?')))}</b> "
        f"({html.escape(str(us_text.get('confidence', '?')))})</p>",
    ]

    # ── 1. Standard ultrasound report (clinical-facing) ──
    lines.extend(
        render_standard_ultrasound_report_html(
            case_id=assets.case_id,
            clinical=ci,
            us_text=us_text,
        )
    )

    # ── 2. Agent flow ──
    lines.extend(render_agent_flow_timeline(steps))

    # ── 3. Key images (controlled size) ──
    lines.extend(
        render_hero_evidence_grid(
            assets.platform_panels or {},
            step_figures=assets.step_figures,
            html_path=out_path,
        )
    )

    # ── 4. Video & preprocessing (collapsed) ──
    lines.extend([
        '<div class="annex">',
        "<details open><summary><h2 style='display:inline;margin:0'>检查资料 · 视频与关键帧</h2></summary>",
        f"<p class='meta'>{vm['n_frames']} frames · {vm['fps']:.1f} fps · "
        f"{vm['width']}×{vm['height']} · {vm['duration_s']} s · "
        f"源文件 <code>{html.escape(rel_href(out_path, assets.clip_path))}</code></p>",
        video_tag(out_path, staged_video),
    ])
    for fig_key, css in (
        ("key_frames_grid", "fig scan-fig"),
        ("preprocess", "fig scan-fig"),
    ):
        path = assets.figures.get(fig_key)
        if path and path.is_file():
            lines.append(img_tag(out_path, path, css_class=css, alt=fig_key))
    lines.append("</details>")

    lines.append("<details><summary><h2 style='display:inline;margin:0'>多帧分割对照 (UNet vs DINO)</h2></summary>")
    for fig_key, css in (
        ("seg_compare", "fig scan-fig"),
        ("medsam_grid", "fig fig-wide"),
    ):
        path = assets.figures.get(fig_key)
        if path and path.is_file():
            lines.append(img_tag(out_path, path, css_class=css, alt=fig_key))
    lines.append("</details></div>")

    # ── 5. Agent evidence annex ──
    if assets.platform_panels or assets.step_figures:
        lines.extend(
            render_per_agent_main_visual_sections(
                steps,
                assets.step_figures or {},
                llm_record=assets.llm_record,
                six_panel_path=assets.figures.get("six_panel"),
                platform_panels=assets.platform_panels,
                platform_meta=assets.platform_meta,
                html_path=out_path,
            )
        )

    lines.extend(
        render_step_narrative_sections(
            steps,
            assets.step_figures or {},
            llm_record=assets.llm_record,
            html_path=out_path,
        )
    )

    # ── 6. Technical annex (collapsed) ──
    lines.append('<div class="annex">')
    lines.append("<details><summary><h2 style='display:inline;margin:0'>附录 C · 模型调用与 Pipeline 汇总</h2></summary>")
    lines.extend(render_execution_mode_notice())
    trace = assets.execution_trace or {}
    if trace:
        lines.extend(render_model_invocation_table(trace))
        lines.extend(render_agent_execution_table(trace))
    if report:
        lines.append(
            f"<p>综合结论：<b>{html.escape(str(report.get('recommended_t_stage', '?')))}</b> "
            f"（{html.escape(str(report.get('confidence', '?')))}）</p>"
        )
        if report.get("supporting_evidence"):
            lines.append("<ul>")
            for ev in report["supporting_evidence"]:
                lines.append(f"<li>{html.escape(str(ev))}</li>")
            lines.append("</ul>")
    lines.append("<table><tr><th>#</th><th>Step</th><th>Status</th><th>Detail</th><th>s</th></tr>")
    for s in steps:
        lines.append(
            f"<tr><td>{s.get('step', '?')}</td>"
            f"<td><code>{html.escape(str(s.get('step_id', '')))}</code></td>"
            f"<td>{_badge(str(s.get('status', '?')))}</td>"
            f"<td>{html.escape(_step_detail(s))}</td>"
            f"<td class='num'>{float(s.get('elapsed_s', 0)):.2f}</td></tr>"
        )
    lines.append("</table></details>")

    lines.append("<details><summary><h2 style='display:inline;margin:0'>附录 D · LLM 全量 trace</h2></summary>")
    lines.extend(render_llm_section(assets.llm_record, assets.llm_trace))
    lines.append("</details>")

    audit_steps = (assets.agent_audit or {}).get("agent_calls") or steps
    lines.append("<details><summary><h2 style='display:inline;margin:0'>附录 E · Agent JSON 归档</h2></summary>")
    lines.extend(render_agent_trace_sections(audit_steps, html_path=out_path))
    lines.append("</details></div>")

    lines.append(
        '<p class="footer">GastricTstaging · unified LangGraph pipeline · standard ultrasound layout v2</p>'
    )
    lines.append("</body></html>")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
