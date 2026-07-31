"""
Scan-platform-aligned agent visual panels for HTML reports.

Reuses artifact generators from ``analyze_case.py`` so HTML §6 matches
``apps/gastric_scan_next`` AgentWorkbenchPanel layouts (DINO, overlay, wall, …).
"""

from __future__ import annotations

import base64
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from ..core.repo_paths import PROJECT_ROOT

logger = logging.getLogger(__name__)


@dataclass
class ScanPlatformPanel:
    key: str
    title: str
    subtitle: str
    image_path: Path
    meta: Optional[Dict[str, Any]] = None


def _resolve_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_file():
        return p
    candidate = PROJECT_ROOT / p
    if candidate.is_file():
        return candidate
    return p


def _resolve_panel_image(path: Path) -> Optional[Path]:
    p = _resolve_path(path)
    return p if p.is_file() else None


def _step_obs(steps: List[Dict[str, Any]], step_id: str) -> Dict[str, Any]:
    for s in steps:
        if str(s.get("step_id")) == step_id:
            return dict(s.get("observation") or {})
    return {}


def _load_mask_from_seg(seg_obs: Dict[str, Any]) -> Optional[np.ndarray]:
    mask_path = seg_obs.get("mask_png")
    if not mask_path:
        unet = seg_obs.get("unet") or {}
        mask_path = unet.get("mask_png")
    if not mask_path:
        return None
    p = _resolve_path(str(mask_path))
    if not p.is_file():
        return None
    mask = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
    return mask


def _segmentation_dict(seg_obs: Dict[str, Any]) -> Dict[str, Any]:
    roi_bbox = seg_obs.get("roi_bbox")
    if not roi_bbox:
        roi_bbox = (seg_obs.get("unet") or {}).get("roi_bbox")
    return {
        "roi_bbox": roi_bbox,
        "roi_source": seg_obs.get("roi_source", "predicted"),
        "mask_available": seg_obs.get("mask_available"),
        "lesion_area_ratio": seg_obs.get("lesion_area_ratio"),
        "image_height": seg_obs.get("image_height"),
        "image_width": seg_obs.get("image_width"),
    }


def _panel_from_artifact(
    artifacts: Dict[str, Any],
    path_key: str,
    *,
    panel_key: str,
    title: str,
    subtitle: str,
) -> Optional[ScanPlatformPanel]:
    path = artifacts.get(path_key)
    if not path:
        return None
    img = _resolve_panel_image(Path(str(path)))
    if img is None:
        return None
    return ScanPlatformPanel(panel_key, title, subtitle, img)


def build_scan_platform_panels(
    *,
    pipeline_state: Dict[str, Any],
    primary_image_path: str,
    out_dir: Path,
    patient_id: str,
    force_refresh: bool = False,
) -> Tuple[Dict[str, List[ScanPlatformPanel]], Dict[str, Any]]:
    """
    Build platform-style PNG panels; return panels grouped by pipeline step_id.

    Cached under ``out_dir``; set ``force_refresh=True`` to regenerate.
    """
    steps = pipeline_state.get("steps") or []
    out_dir.mkdir(parents=True, exist_ok=True)
    marker = out_dir / ".platform_panels_ok"
    if marker.exists() and not force_refresh:
        return _load_cached_panels(out_dir, steps)

    from agent.product.analyze_case import (
        _generate_real_dino_multimodal_panel_on_demand,
        _persist_wall_evidence_tool_artifacts,
        _save_current_image_dino_feature_panel,
        _save_lumen_detection_visual,
        _save_prediction_artifacts,
        _save_similarity_visual_artifacts,
        _save_wall_analysis_artifacts,
    )

    image_path = str(_resolve_path(primary_image_path))
    artifact_info = {
        "dir": out_dir,
        "relative_dir": Path("platform"),
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    seg_obs = _step_obs(steps, "lesion_seg")
    lumen_obs = _step_obs(steps, "lumen_detect")
    cls_obs = _step_obs(steps, "t_staging").get("primary") or _step_obs(steps, "t_staging")
    wall_obs = _step_obs(steps, "wall_evidence")
    rag_obs = _step_obs(steps, "case_rag")

    mask = _load_mask_from_seg(seg_obs)
    segmentation = _segmentation_dict(seg_obs)

    pred_art: Dict[str, Any] = {}
    wall_art: Dict[str, Any] = {}
    lumen_art: Dict[str, Any] = {}
    dino_art: Dict[str, Any] = {}
    rag_art: Dict[str, Any] = {}

    try:
        lumen_art = _save_lumen_detection_visual(image_path, lumen_obs, artifact_info)
    except Exception as exc:
        logger.warning("Lumen platform panel failed: %s", exc)

    try:
        pred_art = _save_prediction_artifacts(
            image_path=image_path,
            predicted_mask=mask,
            segmentation=segmentation,
            classification=cls_obs if isinstance(cls_obs, dict) else None,
            artifact_info=artifact_info,
        )
        wall_art = _save_wall_analysis_artifacts(
            image_path=image_path,
            predicted_mask=mask,
            segmentation=segmentation,
            artifact_info=artifact_info,
        )
    except Exception as exc:
        logger.warning("Seg/wall platform panels failed: %s", exc)

    try:
        wall_copy = dict(wall_obs)
        visuals = wall_copy.get("_visuals")
        if isinstance(visuals, dict):
            overlay = visuals.get("wall_overlay_bgr")
            if isinstance(overlay, list):
                visuals["wall_overlay_bgr"] = np.array(overlay, dtype=np.uint8)
        wall_live = _persist_wall_evidence_tool_artifacts(wall_copy, artifact_info)
        wall_art.update(wall_live)
    except Exception as exc:
        logger.warning("Wall evidence platform panels failed: %s", exc)

    try:
        dino_art = _save_current_image_dino_feature_panel(
            image_path=image_path,
            prediction_artifacts=pred_art,
            artifact_info=artifact_info,
        )
        dino_multi = _generate_real_dino_multimodal_panel_on_demand(
            image_path=image_path,
            prediction_artifacts=pred_art,
            classification=cls_obs if isinstance(cls_obs, dict) else {},
            payload={"patient_id": patient_id},
            artifact_info=artifact_info,
        )
        dino_art.update(dino_multi)
    except Exception as exc:
        logger.warning("DINO platform panels failed: %s", exc)

    try:
        hits = rag_obs.get("similar_cases") or []
        rag_art = _save_similarity_visual_artifacts(
            image_path=image_path,
            predicted_mask=mask,
            similar_cases=hits,
            artifact_info=artifact_info,
        )
    except Exception as exc:
        logger.warning("RAG platform panels failed: %s", exc)

    panels_by_step = _group_panels(
        lumen_art=lumen_art,
        pred_art=pred_art,
        wall_art=wall_art,
        dino_art=dino_art,
        rag_art=rag_art,
    )
    meta = {k: v for k, v in dino_art.items() if not k.endswith("_path")}

    _write_panel_index(out_dir, panels_by_step, meta)
    marker.write_text("ok", encoding="utf-8")
    return panels_by_step, meta


def _group_panels(
    *,
    lumen_art: Dict[str, Any],
    pred_art: Dict[str, Any],
    wall_art: Dict[str, Any],
    dino_art: Dict[str, Any],
    rag_art: Dict[str, Any],
) -> Dict[str, List[ScanPlatformPanel]]:
    out: Dict[str, List[ScanPlatformPanel]] = {}

    def add(step_id: str, panel: Optional[ScanPlatformPanel]) -> None:
        if panel is None:
            return
        out.setdefault(step_id, []).append(panel)

    add(
        "lumen_detect",
        _panel_from_artifact(
            lumen_art,
            "lumen_detection_overlay_path",
            panel_key="lumen_overlay",
            title="YOLO 胃腔检测叠加",
            subtitle="与 Scan 平台 lumen_detection_overlay 一致",
        ),
    )

    for step_id in ("lesion_seg",):
        add(
            step_id,
            _panel_from_artifact(
                pred_art,
                "predicted_overlay_path",
                panel_key="predicted_overlay",
                title="预测分割叠加图",
                subtitle="model-generated overlay · mask + ROI 框",
            ),
        )
        add(
            step_id,
            _panel_from_artifact(
                pred_art,
                "predicted_mask_path",
                panel_key="predicted_mask",
                title="预测 mask",
                subtitle="binary model mask",
            ),
        )
        add(
            step_id,
            _panel_from_artifact(
                pred_art,
                "predicted_roi_path",
                panel_key="predicted_roi",
                title="预测 ROI 裁剪",
                subtitle="病灶 ROI crop（分类 local 分支输入）",
            ),
        )
        add(
            step_id,
            _panel_from_artifact(
                wall_art,
                "wall_penetration_heatmap_path",
                panel_key="wall_penetration_proxy",
                title="胃壁穿透风险热力图",
                subtitle="由预测 mask / ROI 生成的风险代理图",
            ),
        )

    for step_id in ("morphology", "wall_evidence"):
        add(
            step_id,
            _panel_from_artifact(
                wall_art,
                "real_wall_analysis_panel_path",
                panel_key="real_wall_panel",
                title="真实胃壁分析面板",
                subtitle="lumen SDF / mask 驱动 · 与 Scan 平台一致",
            ),
        )
        add(
            step_id,
            _panel_from_artifact(
                wall_art,
                "wall_penetration_heatmap_path",
                panel_key="wall_heatmap",
                title="胃壁穿透风险热力图",
                subtitle="mask-driven risk proxy",
            ),
        )
        add(
            step_id,
            _panel_from_artifact(
                wall_art,
                "wall_layer_profile_path",
                panel_key="wall_profile",
                title="胃壁层剖面",
                subtitle="沿 ROI / lumen 的相对壁层信号",
            ),
        )

    dino_feature = _panel_from_artifact(
        dino_art,
        "current_image_dino_feature_panel_path",
        panel_key="dino_feature",
        title="当前图像真实 DINO 特征面板",
        subtitle=(
            f"真 DINOv3 前向 · token {dino_art.get('dino_token_grid', '?')} · "
            f"size {dino_art.get('dino_input_size', 512)}"
        ),
    )
    if dino_feature:
        dino_feature.meta = {
            k: dino_art.get(k)
            for k in (
                "current_image_dino_model",
                "dino_inference_mode",
                "dino_input_size",
                "dino_token_grid",
                "dino_region_pooling",
                "dino_note",
                "current_image_dino_error",
            )
            if dino_art.get(k) not in (None, "")
        }

    dino_multi = _panel_from_artifact(
        dino_art,
        "real_dino_multimodal_panel_path",
        panel_key="dino_multimodal",
        title="真实 DINO 多模态证据面板",
        subtitle="Ultrasound + ROI overlay + DINO wall heatmap + T 概率",
    )

    add("t_staging", dino_multi)
    add("t_staging", dino_feature)
    add(
        "t_staging",
        _panel_from_artifact(
            pred_art,
            "classification_probabilities_path",
            panel_key="classification_probs",
            title="分类概率图",
            subtitle="Real T-stage prediction bar chart",
        ),
    )
    add("dinov3_seg", dino_feature)
    add("dinov3_seg", dino_multi)

    add(
        "case_rag",
        _panel_from_artifact(
            rag_art,
            "dino_similarity_heatmap_path",
            panel_key="saliency_proxy",
            title="当前帧区域显著性（Sobel proxy · 非 DINO API）",
            subtitle="Case-RAG 步骤辅助可视化",
        ),
    )
    add(
        "case_rag",
        _panel_from_artifact(
            rag_art,
            "similar_cases_contact_sheet_path",
            panel_key="contact_sheet",
            title="相似病例 contact sheet",
            subtitle="top-K 相似病例缩略图",
        ),
    )

    return out


def _write_panel_index(
    out_dir: Path,
    panels: Dict[str, List[ScanPlatformPanel]],
    meta: Dict[str, Any],
) -> None:
    import json

    index: Dict[str, Any] = {"meta": meta, "steps": {}}
    for step_id, plist in panels.items():
        index["steps"][step_id] = [
            {"key": p.key, "title": p.title, "subtitle": p.subtitle, "meta": p.meta or {}}
            for p in plist
        ]
        for p in plist:
            dest = out_dir / f"{step_id}__{p.key}.png"
            if not dest.exists() or dest.stat().st_size != p.image_path.stat().st_size:
                shutil.copy2(p.image_path, dest)
            p.image_path = dest
    (out_dir / "platform_index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _load_cached_panels(
    out_dir: Path,
    steps: List[Dict[str, Any]],
) -> Tuple[Dict[str, List[ScanPlatformPanel]], Dict[str, Any]]:
    import json

    index_path = out_dir / "platform_index.json"
    if not index_path.exists():
        return {}, {}
    index = json.loads(index_path.read_text(encoding="utf-8"))
    meta = index.get("meta") or {}
    out: Dict[str, List[ScanPlatformPanel]] = {}
    for step_id, entries in (index.get("steps") or {}).items():
        plist: List[ScanPlatformPanel] = []
        for ent in entries:
            png_path = out_dir / f"{step_id}__{ent['key']}.png"
            if not png_path.is_file():
                legacy_b64 = out_dir / f"{step_id}__{ent['key']}.png.b64"
                if legacy_b64.is_file():
                    png_path.write_bytes(base64.b64decode(legacy_b64.read_text(encoding="utf-8")))
            if not png_path.is_file():
                continue
            plist.append(
                ScanPlatformPanel(
                    ent["key"],
                    ent["title"],
                    ent.get("subtitle", ""),
                    png_path,
                    meta=ent.get("meta"),
                )
            )
        if plist:
            out[step_id] = plist
    return out, meta


def render_platform_panel_grid(
    panels: List[ScanPlatformPanel],
    html_path: Path,
) -> List[str]:
    """HTML grid matching Scan workbench multi-VisualFrame layout."""
    from .media_refs import img_tag

    if not panels:
        return []
    lines = ['<div class="scan-panel-grid">']
    for p in panels:
        lines.append('<figure class="scan-panel">')
        lines.append(f'<figcaption><b>{_esc(p.title)}</b><br/>'
                     f'<span class="meta">{_esc(p.subtitle)}</span></figcaption>')
        tag = img_tag(html_path, p.image_path, css_class="fig scan-fig", alt=p.key)
        if tag:
            lines.append(tag)
        if p.meta:
            lines.append('<ul class="scan-panel-meta">')
            for k, v in p.meta.items():
                lines.append(f"<li><code>{_esc(k)}</code>: {_esc(str(v))}</li>")
            lines.append("</ul>")
        lines.append("</figure>")
    lines.append("</div>")
    return lines


def _esc(text: str) -> str:
    import html

    return html.escape(text)
