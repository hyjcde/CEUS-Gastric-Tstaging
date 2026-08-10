#!/usr/bin/env python3
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.memory.current_case_memory import CurrentCaseMemory
from agent.memory.feature_extractor import extract_patient_vector
from agent.memory.knowledge_memory import KnowledgeMemory
from agent.memory.session_memory import load_session
from agent.core.repo_paths import PROJECT_ROOT
from agent.tools.classification_tool import ClassificationTool
from agent.tools.clinical_tool import ClinicalTool
from agent.tools.morphology_tool import MorphologyTool
from agent.tools.report_tool import ReportTool
from agent.tools.lumen_detection_tool import LumenDetectionTool
from agent.tools.segmentation_tool import SegmentationTool
from agent.tools.similarity_tool import SimilarityTool
from agent.tools.wall_evidence_tool import WallEvidenceTool
from agent.tools.clinical_vector import (
    clinical_vector_for_classifier,
    normalize_frontend_clinical,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("agent.product.analyze_case")

STAGES = ["T1", "T2", "T3", "T4+"]


def _json_default(obj: Any) -> Any:
    """Keep API/trajectory JSON compact; raw arrays stay in artifact files."""
    if isinstance(obj, np.ndarray):
        return {
            "__type__": "ndarray",
            "shape": list(obj.shape),
            "dtype": str(obj.dtype),
        }
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
PREDICTION_ARTIFACT_ROOT = PROJECT_ROOT / "tmp" / "agent_predictions"


def _stream_enabled() -> bool:
    return os.getenv("AGENT_STREAM_EVENTS") == "1"


def _emit_stream_event(event: str, payload: Dict[str, Any]) -> None:
    if not _stream_enabled():
        return
    sys.stdout.write(
        json.dumps(
            {"event": event, **payload},
            ensure_ascii=False,
            default=_json_default,
        )
        + "\n"
    )
    sys.stdout.flush()


def _load_payload() -> Dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("Missing JSON payload on stdin")
    return json.loads(raw)


def _load_annotation_mask(annotation_path: Optional[str], image_path: Optional[str]) -> Optional[np.ndarray]:
    if not annotation_path or not image_path:
        return None
    annotation_file = Path(annotation_path)
    image_file = Path(image_path)
    if not annotation_file.exists() or not image_file.exists():
        return None

    image = cv2.imread(str(image_file))
    if image is None:
        return None
    height, width = image.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    data = json.loads(annotation_file.read_text(encoding="utf-8"))
    shapes = data.get("shapes", [])
    polygons = [
        np.array(shape.get("points", []), dtype=np.int32)
        for shape in shapes
        if str(shape.get("label", "")).lower() == "tumor" and len(shape.get("points", [])) >= 3
    ]
    if not polygons:
        return None
    cv2.fillPoly(mask, polygons, 255)
    return mask


def _map_location(text: Any) -> int:
    value = str(text or "").strip().lower()
    if any(token in value for token in ["cardia", "fundus", "贲门"]):
        return 0
    if any(token in value for token in ["upper", "上", "fundus"]):
        return 1
    if any(token in value for token in ["body", "胃体"]):
        return 2
    if any(token in value for token in ["antrum", "angle", "pylorus", "胃角", "胃窦", "幽门"]):
        return 3
    return 2


def _map_sex(text: Any) -> int:
    value = str(text or "").strip().lower()
    if value in {"male", "男", "1"}:
        return 1
    return 0


def _map_diff(text: Any) -> int:
    value = str(text or "").strip().lower()
    if "well" in value:
        return 1
    if "moderate" in value and "poor" not in value:
        return 2
    if "poor" in value:
        return 3
    if "undetermined" in value or "unknown" in value:
        return 4
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _map_lauren(text: Any) -> int:
    value = str(text or "").strip().lower()
    if "intestinal" in value:
        return 1
    if "diffuse" in value:
        return 2
    if "mixed" in value:
        return 3
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _build_clinical_kwargs(clinical: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    clinical = clinical or {}
    biomarkers = clinical.get("biomarkers", {}) if isinstance(clinical, dict) else {}
    tumor_size = clinical.get("tumorSize", {}) if isinstance(clinical, dict) else {}

    return {
        "age": clinical.get("age"),
        "sex": _map_sex(clinical.get("sex")),
        "tumor_location": _map_location(clinical.get("location")),
        "tumor_length_cm": tumor_size.get("length"),
        "tumor_thickness_cm": tumor_size.get("thickness"),
        "CEA_value": biomarkers.get("cea"),
        "CEA_status": 1 if biomarkers.get("cea_positive") else 0,
        "CA199_value": biomarkers.get("ca199"),
        "CA199_status": 1 if biomarkers.get("ca199_positive") else 0,
        "differentiation": _map_diff(clinical.get("differentiation")),
        "lauren_type": _map_lauren(clinical.get("lauren")),
    }


def _summarize_similarity(similar_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not similar_cases:
        return {"majority_stage": "unknown", "stage_distribution": {}}
    counts = Counter(case.get("T_stage", "unknown") for case in similar_cases)
    majority_stage = counts.most_common(1)[0][0]
    return {"majority_stage": majority_stage, "stage_distribution": dict(counts)}


def _normalize_similar_stage(stage: Any) -> str:
    raw = str(stage or "unknown").strip()
    if raw in {"T4", "T4a", "T4b", "T4+"}:
        return "T4+"
    if raw in {"T1", "T2", "T3"}:
        return raw
    return raw


def _compute_similarity_vote_weights(similar_cases: List[Dict[str, Any]]) -> Dict[str, float]:
    """Similarity-weighted vote shares for UI (not the final RAG gate)."""
    buckets = {"T1": 0.0, "T2": 0.0, "T3": 0.0, "T4+": 0.0, "unknown": 0.0}
    for case in similar_cases:
        stage = _normalize_similar_stage(case.get("T_stage"))
        weight = max(float(case.get("similarity", 0.0) or 0.0), 0.01)
        key = stage if stage in buckets else "unknown"
        buckets[key] += weight
    total = sum(buckets.values()) or 1.0
    return {key: round(value / total, 4) for key, value in buckets.items() if value > 0}


def _save_lumen_detection_visual(
    image_path: Optional[str],
    lumen_detection: Dict[str, Any],
    artifact_info: Dict[str, Any],
) -> Dict[str, Any]:
    """Draw YOLO lumen bbox on the currently selected frame for the UI step panel."""
    artifacts: Dict[str, Any] = {}
    if not image_path:
        return artifacts

    image = cv2.imread(image_path)
    if image is None:
        return artifacts

    overlay = image.copy()
    bbox = lumen_detection.get("lumen_bbox") if isinstance(lumen_detection.get("lumen_bbox"), dict) else None
    detected = bool(lumen_detection.get("lumen_detected"))
    conf = float(lumen_detection.get("lumen_confidence", 0.0) or 0.0)
    area_ratio = lumen_detection.get("lumen_area_ratio")

    polygon = lumen_detection.get("lumen_polygon")
    if isinstance(polygon, list) and len(polygon) >= 3:
        points = []
        for point in polygon:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            try:
                points.append([float(point[0]), float(point[1])])
            except (TypeError, ValueError):
                continue
        if len(points) >= 3:
            poly = np.asarray(points, dtype=np.float32)
            poly[:, 0] = np.clip(poly[:, 0], 0, image.shape[1] - 1)
            poly[:, 1] = np.clip(poly[:, 1], 0, image.shape[0] - 1)
            cv2.fillPoly(
                overlay,
                [np.round(poly).astype(np.int32)],
                (40, 160, 120),
            )
            overlay = cv2.addWeighted(image, 0.72, overlay, 0.28, 0)
            cv2.polylines(
                overlay,
                [np.round(poly).astype(np.int32)],
                isClosed=True,
                color=(40, 255, 190),
                thickness=3,
                lineType=cv2.LINE_AA,
            )

    if bbox:
        x1 = max(0, int(bbox.get("x1", 0)))
        y1 = max(0, int(bbox.get("y1", 0)))
        x2 = min(image.shape[1], int(bbox.get("x2", image.shape[1])))
        y2 = min(image.shape[0], int(bbox.get("y2", image.shape[0])))
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 210, 255), 3)
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (255, 255, 255), 1)
        label = f"Lumen conf={conf:.2f}"
        if area_ratio is not None:
            label += f" area={float(area_ratio):.3f}"
        cv2.putText(
            overlay,
            label,
            (x1, max(y1 - 10, 26)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.68,
            (0, 210, 255),
            2,
            cv2.LINE_AA,
        )
    elif detected:
        cv2.putText(
            overlay,
            "Lumen detected but bbox missing",
            (12, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 210, 255),
            2,
            cv2.LINE_AA,
        )
    else:
        message = str(lumen_detection.get("error") or "No lumen detected")
        cv2.putText(
            overlay,
            message[:96],
            (12, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (120, 140, 255),
            2,
            cv2.LINE_AA,
        )

    artifact_dir: Path = artifact_info["dir"]
    relative_dir: Path = artifact_info["relative_dir"]
    rel = relative_dir / "lumen_detection_overlay.png"
    cv2.imwrite(str(artifact_dir / "lumen_detection_overlay.png"), overlay)
    artifacts["lumen_detection_overlay_path"] = str(artifact_dir / "lumen_detection_overlay.png")
    artifacts["lumen_detection_overlay_url"] = _artifact_url(rel)
    return artifacts


def _has_report_payload(report_payload: Dict[str, Any]) -> bool:
    keys = [
        "ultrasound_report",
        "ultrasound_findings",
        "ultrasound_impression",
        "endoscopy_report",
        "pathology_report",
    ]
    return any(str(report_payload.get(key, "")).strip() for key in keys)


def _compact_tool_output(result: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    return {key: result.get(key) for key in keys if key in result}


def _append_agent_step(
    steps: List[Dict[str, Any]],
    *,
    step_id: str,
    title: str,
    intent: str,
    decision: str,
    tool_name: Optional[str],
    status: str,
    inputs: Dict[str, Any],
    outputs: Dict[str, Any],
    reasoning: str,
    visual_refs: Optional[Dict[str, Any]] = None,
) -> None:
    step = {
        "order": len(steps) + 1,
        "step_id": step_id,
        "title": title,
        "intent": intent,
        "decision": decision,
        "tool_name": tool_name,
        "status": status,
        "inputs": inputs,
        "outputs": outputs,
        "reasoning": reasoning,
        "visual_refs": visual_refs or {},
    }
    steps.append(step)
    _emit_stream_event("agent_step", {"step": step})


def _artifact_url(relative_path: Path) -> str:
    return "/api/agent/artifacts/" + "/".join(relative_path.parts)


def _prepare_artifact_dir(payload: Dict[str, Any]) -> Dict[str, Any]:
    session_id = str(payload.get("session_id") or "unsaved_session")
    safe_session = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in session_id)
    patient_id = str(payload.get("patient_id") or "unknown")
    safe_patient = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in patient_id)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    relative_dir = Path(safe_session) / f"{safe_patient}_{timestamp}"
    artifact_dir = PREDICTION_ARTIFACT_ROOT / relative_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return {
        "dir": artifact_dir,
        "relative_dir": relative_dir,
        "created_at": timestamp,
    }


def _save_prediction_artifacts(
    *,
    image_path: Optional[str],
    predicted_mask: Optional[np.ndarray],
    segmentation: Dict[str, Any],
    classification: Optional[Dict[str, Any]],
    artifact_info: Dict[str, Any],
) -> Dict[str, Any]:
    artifacts: Dict[str, Any] = {
        "root": str(artifact_info["dir"]),
        "relative_dir": str(artifact_info["relative_dir"]),
        "created_at": artifact_info["created_at"],
    }
    if not image_path:
        return artifacts

    image = cv2.imread(image_path)
    if image is None:
        artifacts["error"] = "Could not read image for prediction artifact export"
        return artifacts

    artifact_dir: Path = artifact_info["dir"]
    relative_dir: Path = artifact_info["relative_dir"]
    height, width = image.shape[:2]

    bbox = segmentation.get("roi_bbox") if isinstance(segmentation, dict) else None
    if isinstance(bbox, dict):
        x1 = max(0, int(bbox.get("x1", 0)))
        y1 = max(0, int(bbox.get("y1", 0)))
        x2 = min(width, int(bbox.get("x2", width)))
        y2 = min(height, int(bbox.get("y2", height)))
        if x2 > x1 and y2 > y1:
            roi = image[y1:y2, x1:x2]
            roi_rel = relative_dir / "predicted_roi.png"
            cv2.imwrite(str(artifact_dir / "predicted_roi.png"), roi)
            artifacts["predicted_roi_path"] = str(artifact_dir / "predicted_roi.png")
            artifacts["predicted_roi_url"] = _artifact_url(roi_rel)

    if predicted_mask is not None:
        mask = predicted_mask.astype(np.uint8)
        if mask.shape[:2] != (height, width):
            mask = cv2.resize(mask, (width, height), interpolation=cv2.INTER_NEAREST)
        mask_rel = relative_dir / "predicted_mask.png"
        cv2.imwrite(str(artifact_dir / "predicted_mask.png"), mask)
        artifacts["predicted_mask_path"] = str(artifact_dir / "predicted_mask.png")
        artifacts["predicted_mask_url"] = _artifact_url(mask_rel)

        overlay = image.copy()
        mask_bin = mask > 127
        color = np.zeros_like(image)
        color[:, :, 1] = 255
        overlay[mask_bin] = cv2.addWeighted(image, 0.35, color, 0.65, 0)[mask_bin]
        if isinstance(bbox, dict):
            x1 = max(0, int(bbox.get("x1", 0)))
            y1 = max(0, int(bbox.get("y1", 0)))
            x2 = min(width, int(bbox.get("x2", width)))
            y2 = min(height, int(bbox.get("y2", height)))
            cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 255), 2)
        cv2.putText(overlay, "Agent predicted mask + ROI", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        overlay_rel = relative_dir / "predicted_overlay.png"
        cv2.imwrite(str(artifact_dir / "predicted_overlay.png"), overlay)
        artifacts["predicted_overlay_path"] = str(artifact_dir / "predicted_overlay.png")
        artifacts["predicted_overlay_url"] = _artifact_url(overlay_rel)

    probabilities = classification.get("probabilities") if isinstance(classification, dict) else None
    if isinstance(probabilities, dict) and probabilities:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            stages = [stage for stage in STAGES if stage in probabilities]
            values = [float(probabilities.get(stage, 0.0)) for stage in stages]
            plt.rcParams["font.family"] = "Times New Roman"
            fig, ax = plt.subplots(figsize=(5, 3), facecolor="black")
            ax.set_facecolor("black")
            bars = ax.bar(stages, values, color=["#38bdf8", "#34d399", "#facc15", "#f87171"])
            ax.set_ylim(0, 1)
            ax.set_ylabel("Probability", color="white")
            ax.set_title("Real T-stage Prediction", color="white", fontweight="bold")
            ax.tick_params(colors="white")
            for spine in ax.spines.values():
                spine.set_color("#475569")
            for bar, value in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width() / 2, value + 0.02, f"{value:.2f}", ha="center", color="white")
            fig.tight_layout()
            prob_rel = relative_dir / "classification_probabilities.png"
            fig.savefig(str(artifact_dir / "classification_probabilities.png"), dpi=160, facecolor=fig.get_facecolor())
            plt.close(fig)
            artifacts["classification_probabilities_path"] = str(artifact_dir / "classification_probabilities.png")
            artifacts["classification_probabilities_url"] = _artifact_url(prob_rel)
        except Exception as exc:
            artifacts["classification_plot_error"] = str(exc)

    return artifacts


def _save_wall_analysis_artifacts(
    *,
    image_path: Optional[str],
    predicted_mask: Optional[np.ndarray],
    segmentation: Dict[str, Any],
    artifact_info: Dict[str, Any],
    reuse_script_wall_panel: bool = False,
    keep_existing_layer_profile: bool = False,
) -> Dict[str, Any]:
    artifacts: Dict[str, Any] = {}
    if not image_path:
        return artifacts

    image = cv2.imread(image_path)
    if image is None:
        return artifacts

    artifact_dir: Path = artifact_info["dir"]
    relative_dir: Path = artifact_info["relative_dir"]
    h, w = image.shape[:2]
    mask = predicted_mask.astype(np.uint8) if predicted_mask is not None else None
    if mask is not None and mask.shape[:2] != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)

    bbox = segmentation.get("roi_bbox") if isinstance(segmentation, dict) else None
    if isinstance(bbox, dict):
        x1 = max(0, int(bbox.get("x1", 0)))
        y1 = max(0, int(bbox.get("y1", 0)))
        x2 = min(w, int(bbox.get("x2", w)))
        y2 = min(h, int(bbox.get("y2", h)))
    else:
        x1, y1, x2, y2 = int(w * 0.2), int(h * 0.2), int(w * 0.8), int(h * 0.8)

    risk = np.zeros((h, w), dtype=np.float32)
    if mask is not None and np.any(mask > 127):
        mask_bin = (mask > 127).astype(np.uint8)
        distance = cv2.distanceTransform(mask_bin, cv2.DIST_L2, 5)
        risk = cv2.GaussianBlur(distance, (0, 0), 11)
    else:
        risk[y1:y2, x1:x2] = 1.0
        risk = cv2.GaussianBlur(risk, (0, 0), 17)
    risk_norm = cv2.normalize(risk, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    heatmap = cv2.applyColorMap(risk_norm, cv2.COLORMAP_INFERNO)
    wall_overlay = cv2.addWeighted(image, 0.48, heatmap, 0.52, 0)
    cv2.rectangle(wall_overlay, (x1, y1), (x2, y2), (0, 255, 255), 2)
    cv2.putText(wall_overlay, "Wall penetration risk proxy", (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
    wall_rel = relative_dir / "wall_penetration_risk_heatmap.png"
    cv2.imwrite(str(artifact_dir / "wall_penetration_risk_heatmap.png"), wall_overlay)
    artifacts["wall_penetration_heatmap_path"] = str(artifact_dir / "wall_penetration_risk_heatmap.png")
    artifacts["wall_penetration_heatmap_url"] = _artifact_url(wall_rel)

    if not keep_existing_layer_profile:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            roi_risk = risk_norm[y1:y2, x1:x2]
            if roi_risk.size:
                profile = roi_risk.mean(axis=0)
            else:
                profile = np.zeros(10, dtype=np.float32)
            if profile.max() > 0:
                profile = profile / profile.max()
            plt.rcParams["font.family"] = "Times New Roman"
            fig, ax = plt.subplots(figsize=(6, 2.8), facecolor="black")
            ax.set_facecolor("black")
            ax.plot(profile, color="#6ee7b7", linewidth=2.4)
            ax.fill_between(np.arange(len(profile)), profile, color="#22d3ee", alpha=0.25)
            ax.set_ylim(0, 1.05)
            ax.set_title("Gastric Wall Layer / Penetration Proxy", color="white", fontweight="bold")
            ax.set_xlabel("ROI horizontal position", color="white")
            ax.set_ylabel("relative wall signal", color="white")
            ax.tick_params(colors="white")
            for spine in ax.spines.values():
                spine.set_color("#475569")
            fig.tight_layout()
            profile_rel = relative_dir / "wall_layer_profile.png"
            fig.savefig(str(artifact_dir / "wall_layer_profile.png"), dpi=160, facecolor=fig.get_facecolor())
            plt.close(fig)
            artifacts["wall_layer_profile_path"] = str(artifact_dir / "wall_layer_profile.png")
            artifacts["wall_layer_profile_url"] = _artifact_url(profile_rel)
        except Exception as exc:
            artifacts["wall_profile_error"] = str(exc)

    if not reuse_script_wall_panel:
        heat_p = artifact_dir / "wall_penetration_risk_heatmap.png"
        prof_p = artifact_dir / "wall_layer_profile.png"
        fb = _compose_wall_panel_fallback(artifact_info, heatmap_path=heat_p, profile_path=prof_p)
        artifacts.update(fb)

    return artifacts


def _persist_wall_evidence_tool_artifacts(
    wall_result: Dict[str, Any],
    artifact_info: Dict[str, Any],
) -> Dict[str, Any]:
    """Write WallEvidenceTool overlays to the case artifact directory."""
    artifacts: Dict[str, Any] = {}
    visuals = wall_result.pop("_visuals", None) if isinstance(wall_result, dict) else None
    if not visuals:
        return artifacts

    artifact_dir: Path = artifact_info["dir"]
    relative_dir: Path = artifact_info["relative_dir"]

    overlay = visuals.get("wall_overlay_bgr")
    if overlay is not None:
        heat_rel = relative_dir / "wall_penetration_risk_heatmap.png"
        cv2.imwrite(str(artifact_dir / "wall_penetration_risk_heatmap.png"), overlay)
        artifacts["wall_penetration_heatmap_path"] = str(artifact_dir / "wall_penetration_risk_heatmap.png")
        artifacts["wall_penetration_heatmap_url"] = _artifact_url(heat_rel)
        panel_rel = relative_dir / "real_wall_analysis_panel.png"
        cv2.imwrite(str(artifact_dir / "real_wall_analysis_panel.png"), overlay)
        artifacts["real_wall_analysis_panel_path"] = str(artifact_dir / "real_wall_analysis_panel.png")
        artifacts["real_wall_analysis_panel_url"] = _artifact_url(panel_rel)
        artifacts["real_wall_analysis_panel_source"] = "live_lumen_signed_distance"
        artifacts["real_wall_analysis_panel_source_script"] = "pipeline/agent/tools/wall_evidence_tool.py"

    profile = visuals.get("wall_profile")
    if profile is not None:
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            plt.rcParams["font.family"] = "Times New Roman"
            fig, ax = plt.subplots(figsize=(6, 2.8), facecolor="black")
            ax.set_facecolor("black")
            ax.plot(profile, color="#6ee7b7", linewidth=2.4)
            ax.fill_between(np.arange(len(profile)), profile, color="#22d3ee", alpha=0.25)
            ax.set_ylim(0, 1.05)
            ax.set_title("Gastric Wall Layer (lumen-relative)", color="white", fontweight="bold")
            ax.set_xlabel("vertical position", color="white")
            ax.set_ylabel("outward depth (norm)", color="white")
            ax.tick_params(colors="white")
            for spine in ax.spines.values():
                spine.set_color("#475569")
            fig.tight_layout()
            profile_rel = relative_dir / "wall_layer_profile.png"
            fig.savefig(str(artifact_dir / "wall_layer_profile.png"), dpi=160, facecolor=fig.get_facecolor())
            plt.close(fig)
            artifacts["wall_layer_profile_path"] = str(artifact_dir / "wall_layer_profile.png")
            artifacts["wall_layer_profile_url"] = _artifact_url(profile_rel)
        except Exception as exc:
            artifacts["wall_profile_error"] = str(exc)

    artifacts["wall_evidence_features"] = wall_result.get("wall_features")
    artifacts["wall_penetration_risk"] = wall_result.get("penetration_risk")
    return artifacts


def _copy_artifact(source: Path, artifact_info: Dict[str, Any], target_name: str) -> Dict[str, str]:
    artifact_dir: Path = artifact_info["dir"]
    relative_dir: Path = artifact_info["relative_dir"]
    target = artifact_dir / target_name
    shutil.copy2(source, target)
    return {
        f"{target_name.rsplit('.', 1)[0]}_path": str(target),
        f"{target_name.rsplit('.', 1)[0]}_url": _artifact_url(relative_dir / target_name),
    }


def _tokens_for_wall_artifact_lookup(payload: Dict[str, Any], image_path: Optional[str]) -> List[str]:
    """Broaden filesystem matching beyond raw patient_id (filenames often use `{id}-{frame}_analysis.png`)."""
    tokens: List[str] = []
    patient_id = str(payload.get("patient_id", "") or "").strip()
    case_token = str(payload.get("case_token", "") or "").strip()

    candidates = [
        patient_id,
        case_token,
        case_token.replace("__", "_"),
        case_token.replace("__", "-"),
        case_token.replace("test_", "").replace("__", "_"),
    ]

    suffix = "__"
    pos = patient_id.find(suffix)
    if pos != -1 and pos + len(suffix) < len(patient_id):
        candidates.append(patient_id[pos + len(suffix) :])

    if "__" in case_token:
        tail = case_token.split("__")[-1].strip()
        if tail:
            candidates.append(tail)

    stem = ""
    ip = Path(image_path) if image_path else None
    if ip:
        stem = ip.stem
        candidates.extend([stem, stem.replace("__", "_"), stem.replace("__", "-")])
        for part in re.split(r"[_\-]+", stem):
            if len(part) >= 4:
                candidates.append(part)
        for m in re.findall(r"\d{4,}", stem):
            candidates.append(m)

    seen: set[str] = set()
    out: List[str] = []
    for tok in candidates:
        t = str(tok).strip()
        if not t or len(t) < 2 or t in seen:
            continue
        seen.add(t)
        out.append(t)
        if "_" in t and not t.endswith("_analysis"):
            if t.split("_")[0] not in seen and len(t.split("_")[0]) >= 4:
                out.append(t.split("_")[0])
                seen.add(t.split("_")[0])
        if "-" in t:
            pref = t.split("-")[0]
            if pref not in seen and len(pref) >= 4:
                out.append(pref)
                seen.add(pref)
    return out


def _compose_wall_panel_fallback(
    artifact_info: Dict[str, Any],
    *,
    heatmap_path: Path,
    profile_path: Optional[Path],
) -> Dict[str, Any]:
    """When no precomputed `*_analysis.png` exists, stack live proxy heatmap + layer profile into one panel."""
    out: Dict[str, Any] = {}
    if not heatmap_path.is_file():
        return out
    heat = cv2.imread(str(heatmap_path))
    if heat is None:
        return out
    prof = cv2.imread(str(profile_path)) if profile_path and profile_path.is_file() else None
    comps = [heat]
    if prof is not None:
        comps.append(prof)

    target_w = max(img.shape[1] for img in comps)

    def _resize_keep_h(img: np.ndarray) -> np.ndarray:
        if img.shape[1] == target_w:
            return img
        scale = target_w / float(img.shape[1])
        nh = max(1, int(round(img.shape[0] * scale)))
        return cv2.resize(img, (target_w, nh), interpolation=cv2.INTER_AREA)

    heat_r = _resize_keep_h(heat)
    stacked = heat_r if prof is None else np.vstack(
        [
            heat_r,
            np.full((14, target_w, 3), (18, 18, 24), dtype=np.uint8),
            _resize_keep_h(prof),
        ]
    )

    artifact_dir: Path = artifact_info["dir"]
    relative_dir: Path = artifact_info["relative_dir"]
    target_name = "real_wall_analysis_panel.png"
    dst = artifact_dir / target_name
    cap = (
        "Wall panel: current image heatmap + profile (live proxy)"
        if prof is not None
        else "Wall panel: current image heatmap only (live proxy)"
    )
    cv2.putText(stacked, cap, (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (220, 220, 235), 1, cv2.LINE_AA)
    cv2.imwrite(str(dst), stacked)
    out["real_wall_analysis_panel_path"] = str(dst)
    out["real_wall_analysis_panel_url"] = _artifact_url(relative_dir / target_name)
    out["real_wall_analysis_panel_source"] = (
        "live_current_image_composite" if prof is not None else "live_current_image_heatmap_only"
    )
    out["real_wall_analysis_panel_source_script"] = ""
    return out


def _save_real_script_artifacts(payload: Dict[str, Any], artifact_info: Dict[str, Any]) -> Dict[str, Any]:
    """Optional reuse of pre-generated DINO visual panels only (not wall analysis)."""
    artifacts: Dict[str, Any] = {}
    patient_id = str(payload.get("patient_id", "")).strip()
    case_token = str(payload.get("case_token", "")).strip()

    dino_panel_dir = PROJECT_ROOT / "pipeline" / "experiments" / "reports" / "gastric_us_multimodal_agent" / "case_visual_panels_v1"
    dino_candidates = [
        dino_panel_dir / f"{case_token}_visual_panel.png",
        dino_panel_dir / f"test_internal_xh_2025__{patient_id}_visual_panel.png",
    ]
    for candidate in dino_candidates:
        if candidate.exists():
            copied = _copy_artifact(candidate, artifact_info, "real_dino_multimodal_visual_panel.png")
            artifacts.update({
                "real_dino_multimodal_panel_source": str(candidate),
                "real_dino_multimodal_panel_source_script": "scripts/generate_clean_agent_case_visual_panels.py",
                "real_dino_multimodal_panel_url": copied["real_dino_multimodal_visual_panel_url"],
                "real_dino_multimodal_panel_path": copied["real_dino_multimodal_visual_panel_path"],
            })
            break

    return artifacts


def _wall_panel_provenance(prediction_artifacts: Dict[str, Any]) -> Dict[str, str]:
    source = str(prediction_artifacts.get("real_wall_analysis_panel_source") or "")
    if source == "live_lumen_signed_distance":
        mode = "live_lumen_sdf"
        decision = "call_live_lumen_signed_distance"
    elif source.startswith("live_current_image"):
        mode = "live_current_image"
        decision = "call_live_current_image_proxy"
    elif source.startswith("composed_proxy"):
        mode = "live_current_image"
        decision = "call_live_current_image_proxy"
    elif prediction_artifacts.get("real_wall_analysis_panel_url"):
        mode = "artifact_only"
        decision = "call_wall_artifact"
    else:
        mode = "unavailable"
        decision = "call_unavailable"
    return {"wall_panel_mode": mode, "wall_panel_decision": decision}


def _merge_wall_visual_artifacts(
    prediction_artifacts: Dict[str, Any],
    wall_artifacts: Dict[str, Any],
    real_script_artifacts: Dict[str, Any],
) -> None:
    """Prefer live wall figures generated from the current image_path over any stale cache."""
    priority = {
        "live_lumen_signed_distance": 3,
        "live_current_image_composite": 2,
        "live_current_image_heatmap_only": 2,
        "composed_proxy_heatmap_plus_profile": 1,
        "composed_proxy_heatmap_only": 1,
    }

    def _score(bucket: Dict[str, Any]) -> int:
        source = str(bucket.get("real_wall_analysis_panel_source") or "")
        return priority.get(source, 0)

    best: Dict[str, Any] = {}
    best_score = -1
    for bucket in (prediction_artifacts, wall_artifacts, real_script_artifacts):
        score = _score(bucket)
        if score > best_score and bucket.get("real_wall_analysis_panel_url"):
            best_score = score
            best = {
                key: value
                for key, value in bucket.items()
                if key.startswith("real_wall") or key.startswith("wall_layer_profile") or key.startswith("wall_penetration")
            }

    if best:
        prediction_artifacts.update(best)


def _save_current_image_dino_feature_panel(
    *,
    image_path: Optional[str],
    prediction_artifacts: Dict[str, Any],
    artifact_info: Dict[str, Any],
) -> Dict[str, Any]:
    """Run the existing DINO token visualization code on the current image."""
    artifacts: Dict[str, Any] = {}
    if not image_path:
        return artifacts
    try:
        import pandas as pd
        import torch
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        scripts_dir = PROJECT_ROOT / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from generate_external_source_dino_token_panels import infer_dino_maps, load_model

        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        config_path = PROJECT_ROOT / "configs" / "segmentation" / "dinov3" / "vitb16_last2blocks_mlp_decoder.yaml"
        model, hub_model = load_model(config_path, device)
        row = pd.Series({
            "image_path": image_path,
            "lesion_pred_mask_path": prediction_artifacts.get("predicted_mask_path"),
            "mask_path": prediction_artifacts.get("predicted_mask_path"),
            "anatomic_outer_wall_mask_path": None,
            "anatomic_inner_lumen_mask_path": None,
        })
        maps = infer_dino_maps(
            model=model,
            image_path=Path(image_path),
            row=row,
            image_size=512,
            layer_index=11,
            device=device,
        )
        token_h = int(maps.get("token_grid_h", 0) or 0)
        token_w = int(maps.get("token_grid_w", 0) or 0)

        image_rgb = cv2.cvtColor(cv2.imread(image_path), cv2.COLOR_BGR2RGB)
        image_rgb = cv2.resize(image_rgb, (512, 512), interpolation=cv2.INTER_AREA)
        overlay_path = prediction_artifacts.get("predicted_overlay_path")
        overlay = cv2.imread(str(overlay_path)) if overlay_path else None
        if overlay is not None:
            overlay = cv2.cvtColor(cv2.resize(overlay, (512, 512), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)

        plt.rcParams["font.family"] = "Times New Roman"
        artifact_dir: Path = artifact_info["dir"]
        relative_dir: Path = artifact_info["relative_dir"]

        def _save_single_dino_map(content, title, cmap, name):
            fig, ax = plt.subplots(figsize=(5, 4.4), facecolor="black")
            ax.set_facecolor("black")
            ax.imshow(content, cmap=cmap)
            ax.set_title(title, color="white", fontsize=11)
            ax.axis("off")
            fig.tight_layout()
            path = artifact_dir / name
            fig.savefig(str(path), dpi=170, facecolor=fig.get_facecolor())
            plt.close(fig)
            return str(path), _artifact_url(relative_dir / name)

        # Single-map DINO panels: green wall evidence + red/blue affinity + red/blue PCA.
        single_specs = []
        if maps.get("wall_evidence") is not None:
            single_specs.append((maps["wall_evidence"], "DINO Wall Evidence", "Greens", "dino_wall_evidence_map.png", "dino_wall_evidence_map"))
        if maps.get("lesion_affinity") is not None:
            single_specs.append((maps["lesion_affinity"], "DINO Lesion Affinity", "RdBu_r", "dino_lesion_affinity_map.png", "dino_lesion_affinity_map"))
        if maps.get("pca") is not None:
            single_specs.append((maps["pca"], "DINO PCA-1", "RdBu_r", "dino_pca_map.png", "dino_pca_map"))
        for content, title, cmap, filename, key in single_specs:
            try:
                path, url = _save_single_dino_map(content, title, cmap, filename)
                artifacts[f"{key}_path"] = path
                artifacts[f"{key}_url"] = url
            except Exception as exc:
                logger.warning("DINO single map %s failed: %s", key, exc)

        # Compact composite kept for the workbench (not the report).
        fig, axes = plt.subplots(1, 4, figsize=(16, 4), facecolor="black")
        axes = axes.reshape(-1)
        panels = [
            (image_rgb, "Current ultrasound", None),
            (overlay if overlay is not None else image_rgb, "Predicted mask overlay", None),
            (maps.get("wall_evidence"), "Wall evidence", "Greens"),
            (maps.get("lesion_affinity"), "Lesion affinity", "RdBu_r"),
        ]
        for ax, (content, title, cmap) in zip(axes, panels):
            ax.set_facecolor("black")
            if content is None:
                ax.axis("off")
                continue
            ax.imshow(content, cmap=cmap)
            ax.set_title(title, color="white", fontsize=10)
            ax.axis("off")
        fig.suptitle("Current-Image DINO Evidence", color="white", fontsize=13, fontweight="bold")
        fig.tight_layout(rect=[0, 0, 1, 0.93])
        output_name = "current_image_dino_feature_panel.png"
        output_path = artifact_dir / output_name
        fig.savefig(str(output_path), dpi=170, facecolor=fig.get_facecolor())
        plt.close(fig)
        artifacts.update({
            "current_image_dino_feature_panel_path": str(output_path),
            "current_image_dino_feature_panel_url": _artifact_url(relative_dir / output_name),
            "current_image_dino_source_script": "scripts/generate_external_source_dino_token_panels.py",
            "current_image_dino_model": str(hub_model),
            "dino_is_real_forward": True,
            "dino_inference_mode": "full_frame_resize",
            "dino_input_size": 512,
            "dino_token_grid": f"{token_h}x{token_w}" if token_h and token_w else "unknown",
            "dino_region_pooling": "predicted_lesion_mask_on_token_grid",
            "dino_note": (
                "Whole ultrasound frame resized to 512x512 and forwarded through DINOv3 once; "
                "heatmaps are token-grid features upsampled. Report uses single maps (wall/affinity/PCA)."
            ),
        })
    except Exception as exc:
        artifacts["current_image_dino_error"] = str(exc)
        logger.warning("Current-image DINO feature visualization unavailable: %s", exc)
    return artifacts


def _patch_agent_step_visual_refs(
    agent_steps: List[Dict[str, Any]],
    step_id_substr: str,
    updates: Dict[str, Any],
) -> None:
    for step in agent_steps:
        if step_id_substr not in str(step.get("step_id", "")):
            continue
        refs = step.setdefault("visual_refs", {})
        if not isinstance(refs, dict):
            continue
        for key, value in updates.items():
            if value:
                refs[key] = value


def _generate_real_dino_multimodal_panel_on_demand(
    *,
    image_path: Optional[str],
    prediction_artifacts: Dict[str, Any],
    classification: Dict[str, Any],
    payload: Dict[str, Any],
    artifact_info: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate the clean-agent multimodal DINO panel when no prebuilt PNG exists on disk."""
    artifacts: Dict[str, Any] = {}
    if not image_path or not Path(image_path).is_file():
        return artifacts
    try:
        import pandas as pd
        import torch
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        scripts_dir = PROJECT_ROOT / "scripts"
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        from generate_external_source_dino_token_panels import infer_dino_maps, load_model, resolve_path
        from generate_clean_agent_case_visual_panels import (
            LABEL_NAMES,
            overlay_masks,
            plot_probs,
            read_image,
        )

        image_size = 512
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        config_path = PROJECT_ROOT / "configs" / "segmentation" / "dinov3" / "vitb16_last2blocks_mlp_decoder.yaml"
        model, hub_model = load_model(config_path, device)

        mask_path = prediction_artifacts.get("predicted_mask_path")
        row = pd.Series(
            {
                "image_path": image_path,
                "lesion_pred_mask_path": mask_path,
                "mask_path": mask_path,
                "anatomic_outer_wall_mask_path": None,
                "anatomic_inner_lumen_mask_path": None,
            }
        )

        image = read_image(image_path, image_size)
        maps = infer_dino_maps(
            model=model,
            image_path=resolve_path(image_path),
            row=row,
            image_size=image_size,
            layer_index=11,
            device=device,
        )

        probs_raw = classification.get("probabilities") or {}
        probs: Dict[str, float] = {}
        for name in LABEL_NAMES:
            raw = probs_raw.get(name, probs_raw.get(name.replace("+", ""), 0.0))
            probs[name] = float(raw or 0.0)

        patient_id = str(payload.get("patient_id", ""))
        top1 = classification.get("top1_stage", "?")

        fig = plt.figure(figsize=(14, 4.2))
        gs = fig.add_gridspec(1, 4, width_ratios=[1.15, 1.15, 1.15, 1.0])
        fig.suptitle(
            f"Real DINO multimodal evidence | {patient_id} | Pred: {top1}",
            fontsize=13,
        )

        ax0 = fig.add_subplot(gs[0, 0])
        ax0.imshow(image)
        ax0.set_title("Ultrasound")
        ax0.axis("off")

        ax1 = fig.add_subplot(gs[0, 1])
        ax1.imshow(overlay_masks(image, row, image_size))
        ax1.set_title("ROI overlay (lesion/wall/lumen)")
        ax1.axis("off")

        ax2 = fig.add_subplot(gs[0, 2])
        ax2.imshow(image)
        ax2.imshow(maps["wall_evidence"], cmap="magma", alpha=0.55)
        ax2.set_title("DINO wall evidence heatmap")
        ax2.axis("off")

        ax3 = fig.add_subplot(gs[0, 3])
        plot_probs(ax3, probs, "T-stage probabilities")

        fig.text(
            0.02,
            0.01,
            "On-demand layout from scripts/generate_clean_agent_case_visual_panels.py",
            fontsize=9,
            va="bottom",
        )
        fig.tight_layout(rect=[0, 0.05, 1, 0.92])

        artifact_dir: Path = artifact_info["dir"]
        relative_dir: Path = artifact_info["relative_dir"]
        output_name = "real_dino_multimodal_visual_panel.png"
        output_path = artifact_dir / output_name
        fig.savefig(str(output_path), dpi=180)
        plt.close(fig)

        artifacts.update(
            {
                "real_dino_multimodal_panel_source": str(output_path),
                "real_dino_multimodal_panel_source_script": (
                    "scripts/generate_clean_agent_case_visual_panels.py (on-demand)"
                ),
                "real_dino_multimodal_panel_path": str(output_path),
                "real_dino_multimodal_panel_url": _artifact_url(relative_dir / output_name),
                "real_dino_multimodal_panel_model": str(hub_model),
            }
        )
        logger.info("Generated on-demand DINO multimodal panel: %s", output_path)
    except Exception as exc:
        artifacts["real_dino_multimodal_panel_error"] = str(exc)
        logger.warning("On-demand DINO multimodal panel unavailable: %s", exc)
    return artifacts


def _external_image_search_roots(data_source: str) -> List[Path]:
    """Map ext/* data_source tags to on-disk external cohort image folders."""
    ds = str(data_source or "").lower().strip()
    base = PROJECT_ROOT / "dataset" / "external"
    folder_names: List[str] = []
    if "putian" in ds:
        folder_names.append("莆田学院附属医院")
    if any(token in ds for token in ("multicenter", "zhongliu", "肿瘤")):
        folder_names.extend(["福建省肿瘤医院", "三明市第二医院"])
    if "dehua" in ds:
        folder_names.append("福建省德化县医院")
    if not folder_names and ds.startswith("ext/"):
        # Generic fallback: search all external hospital folders.
        if base.is_dir():
            folder_names.extend(sorted(p.name for p in base.iterdir() if p.is_dir() and not p.name.endswith(".csv")))

    roots: List[Path] = []
    seen: set[str] = set()
    for name in folder_names:
        for sub in (Path("original") / "images", Path("crop_roi") / "images", Path("original")):
            root = base / name / sub
            key = str(root)
            if key not in seen and root.is_dir():
                seen.add(key)
                roots.append(root)
    return roots


def _search_case_image_in_dir(root: Path, patient_id: str) -> Optional[Path]:
    if not root.is_dir() or not patient_id:
        return None
    pid = patient_id.strip()
    variants = {pid, pid.lstrip("0"), pid.upper(), pid.replace("pty", "pt", 1)}
    if pid.upper().startswith("PT"):
        variants.add(pid[2:].lstrip("0"))
        variants.add(f"pt{pid[2:]}")
    for suffix in ("*.jpg", "*.jpeg", "*.png", "*.Jpg", "*.JPG"):
        for path in sorted(root.glob(suffix)):
            stem = path.stem
            if any(v and len(v) >= 3 and v in stem for v in variants):
                return path
    for variant in sorted(variants, key=len, reverse=True):
        if len(variant) < 3:
            continue
        hits = sorted(root.glob(f"*{variant}*"))
        for path in hits:
            if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                return path
    return None


def _candidate_case_image_paths(case: Dict[str, Any]) -> List[Path]:
    patient_id = str(case.get("patient_id", "")).strip()
    preview = case.get("preview_image_path")
    if preview:
        preview_path = Path(str(preview))
        if preview_path.is_file():
            return [preview_path]

    if not patient_id:
        return []

    data_source = str(case.get("data_source", ""))
    if data_source.lower().startswith("ext/"):
        for root in _external_image_search_roots(data_source):
            hit = _search_case_image_in_dir(root, patient_id)
            if hit is not None:
                return [hit]

    dino_panel_dir = (
        PROJECT_ROOT
        / "pipeline"
        / "experiments"
        / "reports"
        / "gastric_us_multimodal_agent"
        / "case_visual_panels_v1"
    )
    if dino_panel_dir.is_dir():
        panel_hits = sorted(dino_panel_dir.glob(f"*{patient_id}*_visual_panel.png"))
        if panel_hits:
            return panel_hits[:1]

    data_source = str(case.get("data_source", "")).lower()
    cohort_year = str(case.get("cohort_year", "")).strip()
    years: List[str] = []
    for year in ("2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018"):
        if year in data_source or year == cohort_year:
            years.append(year)
    year_match = re.search(r"(20\d{2})", data_source)
    if year_match and year_match.group(1) not in years:
        years.append(year_match.group(1))
    if not years:
        years = ["2025", "2024", "2019", "2018"]

    roots: List[Path] = [
        PROJECT_ROOT / "dataset" / "internal" / "prospective_2025" / "2025" / "original" / "images",
    ]
    for year in years:
        roots.append(PROJECT_ROOT / "dataset" / "internal" / "training_2018_2024" / year / "original" / "images")
        roots.append(PROJECT_ROOT / "dataset" / "internal" / "prospective_2025" / year / "original" / "images")

    pid_variants = {patient_id, patient_id.lstrip("0"), patient_id.upper()}
    if patient_id.upper().startswith("Z"):
        pid_variants.add(patient_id.upper())

    for root in roots:
        if not root.exists():
            continue
        for suffix in ("*.jpg", "*.jpeg", "*.png"):
            for path in root.glob(suffix):
                stem = path.stem
                if any(variant and variant in stem for variant in pid_variants):
                    return [path]
        for variant in pid_variants:
            if len(variant) < 4:
                continue
            nested = sorted(root.rglob(f"*{variant}*"))
            for path in nested:
                if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                    return [path]
    return []


def _render_similar_cases_contact_sheet(
    *,
    artifact_dir: Path,
    relative_dir: Path,
    similar_cases: List[Dict[str, Any]],
) -> Dict[str, str]:
    """Paper-style contact sheet (white background) for similar-case thumbnails."""
    artifacts: Dict[str, str] = {}
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.rcParams["font.family"] = "Times New Roman"
        case_count = max(len(similar_cases[:5]), 1)
        fig, axes = plt.subplots(1, case_count, figsize=(case_count * 2.6, 3.0), facecolor="white")
        if case_count == 1:
            axes = [axes]
        for ax, case in zip(axes, similar_cases[:5] or [{}]):
            ax.set_facecolor("#f1f5f9")
            preview_path = _resolve_similar_case_preview_path(case)
            if preview_path:
                img = cv2.imread(str(preview_path))
                if img is not None:
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    ax.imshow(img)
                else:
                    ax.text(
                        0.5,
                        0.5,
                        "preview\nunreadable",
                        color="#334155",
                        ha="center",
                        va="center",
                        transform=ax.transAxes,
                    )
            else:
                ax.text(
                    0.5,
                    0.5,
                    "image\nnot found",
                    color="#334155",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                )
            stage = _normalize_similar_stage(case.get("T_stage", "unknown"))
            sim = float(case.get("similarity", 0.0))
            rank = case.get("rank", "?")
            title = f"#{rank} {case.get('patient_id', 'case')}\n{stage} | sim {sim:.2f}"
            ax.set_title(title, color="#0f172a", fontsize=9)
            ax.axis("off")
        fig.suptitle(
            "Similar Historical Cases (similarity-weighted vote pool)",
            color="#0f172a",
            fontsize=13,
            fontweight="bold",
        )
        fig.tight_layout()
        sheet_rel = relative_dir / "similar_cases_contact_sheet.png"
        out_path = artifact_dir / "similar_cases_contact_sheet.png"
        fig.savefig(str(out_path), dpi=160, facecolor="white", edgecolor="white")
        plt.close(fig)
        artifacts["similar_cases_contact_sheet_path"] = str(out_path)
        artifacts["similar_cases_contact_sheet_url"] = _artifact_url(sheet_rel)
    except Exception as exc:
        artifacts["similar_cases_contact_sheet_error"] = str(exc)
    return artifacts


def _resolve_similar_case_preview_path(case: Dict[str, Any]) -> Optional[Path]:
    preview_path = case.get("preview_image_path")
    if preview_path:
        path = Path(str(preview_path))
        if path.is_file():
            return path
    candidates = _candidate_case_image_paths(case)
    return candidates[0] if candidates else None


def _attach_similar_case_preview_artifacts(
    similar_cases: List[Dict[str, Any]],
    artifact_info: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Copy per-case preview PNGs into the artifact dir so the UI can show real thumbnails."""
    enriched: List[Dict[str, Any]] = []
    for index, case in enumerate(similar_cases[:5], start=1):
        row = dict(case)
        image_paths = _candidate_case_image_paths(row)
        if image_paths:
            copied = _copy_artifact(image_paths[0], artifact_info, f"similar_case_{index}_preview.png")
            row["preview_image_url"] = copied[f"similar_case_{index}_preview_url"]
            row["preview_image_path"] = copied[f"similar_case_{index}_preview_path"]
        enriched.append(row)
    return enriched


def _save_similarity_visual_artifacts(
    *,
    image_path: Optional[str],
    predicted_mask: Optional[np.ndarray],
    similar_cases: List[Dict[str, Any]],
    artifact_info: Dict[str, Any],
) -> Dict[str, Any]:
    artifacts: Dict[str, Any] = {}
    if not image_path:
        return artifacts

    image = cv2.imread(image_path)
    if image is None:
        return artifacts

    artifact_dir: Path = artifact_info["dir"]
    relative_dir: Path = artifact_info["relative_dir"]
    h, w = image.shape[:2]

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gradient_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=5)
    gradient_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=5)
    saliency = cv2.magnitude(gradient_x, gradient_y)
    if predicted_mask is not None:
        mask = predicted_mask.astype(np.float32)
        if mask.shape[:2] != (h, w):
            mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
        saliency = 0.45 * saliency + 0.55 * cv2.GaussianBlur(mask, (0, 0), 13)
    saliency = cv2.GaussianBlur(saliency, (0, 0), 9)
    saliency = cv2.normalize(saliency, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    heatmap = cv2.applyColorMap(saliency, cv2.COLORMAP_TURBO)
    overlay = cv2.addWeighted(image, 0.45, heatmap, 0.55, 0)
    cv2.putText(overlay, "Region saliency proxy (not remote DINO API)", (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2)
    dino_rel = relative_dir / "dino_region_similarity_heatmap.png"
    cv2.imwrite(str(artifact_dir / "dino_region_similarity_heatmap.png"), overlay)
    artifacts["dino_similarity_heatmap_path"] = str(artifact_dir / "dino_region_similarity_heatmap.png")
    artifacts["dino_similarity_heatmap_url"] = _artifact_url(dino_rel)

    artifacts.update(
        _render_similar_cases_contact_sheet(
            artifact_dir=artifact_dir,
            relative_dir=relative_dir,
            similar_cases=similar_cases,
        )
    )

    return artifacts


def _boundary_stages(stage: str) -> bool:
    return stage in {"T2", "T3", "T4+"}


def _compute_rag_gate(
    classification: Dict[str, Any],
    similar_cases: List[Dict[str, Any]],
    wall_evidence: Dict[str, Any],
) -> Dict[str, Any]:
    """Gate Case-RAG weight on T-boundary uncertainty (plan § B6)."""
    uncertainty = float(classification.get("uncertainty", 1.0)) if classification.get("available") else 1.0
    top1 = str(classification.get("top1_stage", ""))
    top2 = str(classification.get("top2_stage", ""))
    boundary = _boundary_stages(top1) or _boundary_stages(top2)
    gap = float(classification.get("top1_prob", 0.0)) - float(classification.get("top2_prob", 0.0))
    wall_risk = str(wall_evidence.get("penetration_risk", "low"))

    weight = 0.0
    reason = "rag_suppressed_stable_classifier"
    if not similar_cases:
        reason = "no_similar_cases"
    elif boundary and (uncertainty >= 0.35 or gap < 0.12):
        weight = 0.35
        reason = "t_boundary_low_margin"
    elif wall_risk in {"medium", "high"} and boundary:
        weight = 0.25
        reason = "wall_risk_at_t_boundary"
    elif uncertainty >= 0.5:
        weight = 0.15
        reason = "high_classifier_uncertainty"

    return {
        "rag_weight": round(weight, 3),
        "rag_gate_reason": reason,
        "classifier_uncertainty": round(uncertainty, 4),
        "top1_top2_gap": round(gap, 4),
    }


def _collect_conflicting_evidence(
    classification: Dict[str, Any],
    similar_cases: List[Dict[str, Any]],
    wall_evidence: Dict[str, Any],
    morphology: Dict[str, Any],
) -> List[str]:
    conflicts: List[str] = []
    if not classification.get("available"):
        return conflicts

    cls_top = str(classification.get("top1_stage", ""))
    if similar_cases:
        summary = _summarize_similarity(similar_cases)
        majority = str(summary.get("majority_stage", ""))
        majority_key = "T4+" if majority in {"T4a", "T4b", "T4"} else majority
        if majority_key and majority_key != cls_top:
            conflicts.append(
                f"Classifier top-1 {cls_top} disagrees with similar-case majority {majority_key}."
            )

    if wall_evidence.get("available"):
        risk = str(wall_evidence.get("penetration_risk", "low"))
        if risk == "high" and cls_top in {"T1", "T2"}:
            conflicts.append(
                f"Wall penetration risk is high but classifier favors {cls_top}."
            )
        if risk == "low" and cls_top in {"T4+"}:
            conflicts.append(
                f"Wall penetration risk is low but classifier favors {cls_top}."
            )

    if morphology.get("valid"):
        irregularity = float(morphology.get("boundary_irregularity", 0.0))
        if irregularity >= 0.45 and cls_top == "T1":
            conflicts.append(
                f"High boundary irregularity ({irregularity:.2f}) conflicts with T1 prediction."
            )

    return conflicts


def _build_rule_based_report(
    payload: Dict[str, Any],
    segmentation: Dict[str, Any],
    classification: Dict[str, Any],
    morphology: Dict[str, Any],
    clinical: Dict[str, Any],
    report_text: Dict[str, Any],
    similar_cases: List[Dict[str, Any]],
    knowledge: List[Dict[str, str]],
    *,
    lumen_detection: Optional[Dict[str, Any]] = None,
    wall_evidence: Optional[Dict[str, Any]] = None,
    gc_us_signs: Optional[Dict[str, Any]] = None,
    memory_context: Optional[Dict[str, Any]] = None,
    memory_fusion_mode: str = "soft_prior",
) -> Dict[str, Any]:
    lumen_detection = lumen_detection or {}
    wall_evidence = wall_evidence or {}
    gc_us_signs = gc_us_signs or {}
    scores = {stage: 0.0 for stage in STAGES}
    uncertainty_flags: List[str] = []
    supporting_evidence: List[str] = []
    conflicting_evidence: List[str] = []

    classification_probs = classification.get("probabilities", {}) if classification.get("available") else {}
    for stage in STAGES:
        scores[stage] += float(classification_probs.get(stage, 0.0))
    if classification.get("available"):
        supporting_evidence.append(
            f"Classifier top-1 {classification.get('top1_stage')} ({classification.get('top1_prob', 0.0):.2f})."
        )
    else:
        uncertainty_flags.append("Classifier model unavailable; reasoning relies on morphology, clinical context, and similar cases.")

    if morphology.get("valid"):
        irregularity = float(morphology.get("boundary_irregularity", 0.0))
        area_ratio = float(morphology.get("lesion_area_ratio", 0.0))
        if irregularity >= 0.45:
            scores["T3"] += 0.25
            scores["T4+"] += 0.1
        else:
            scores["T1"] += 0.05
            scores["T2"] += 0.15
        if area_ratio >= 0.08:
            scores["T3"] += 0.15
        supporting_evidence.append(
            f"Morphology irregularity {irregularity:.2f}, lesion area ratio {area_ratio:.2f}."
        )
    else:
        uncertainty_flags.append("Morphology evidence is missing because no usable annotation mask was found.")

    clinical_risk = clinical.get("clinical_risk_score")
    if clinical_risk is not None:
        clinical_risk = float(clinical_risk)
        if clinical_risk >= 0.45:
            scores["T3"] += 0.2
            scores["T4+"] += 0.1
        elif clinical_risk >= 0.25:
            scores["T2"] += 0.2
            scores["T3"] += 0.1
        else:
            scores["T1"] += 0.15
            scores["T2"] += 0.1
        supporting_evidence.append(f"Clinical risk score {clinical_risk:.2f}.")

    report_cues = report_text.get("report_cues", []) if report_text.get("available") else []
    if report_cues:
        cue_names = {str(item.get("cue", "")) for item in report_cues}
        if "possible_t3_t4" in cue_names:
            scores["T3"] += 0.15
            scores["T4+"] += 0.10
        if "possible_t1_t2" in cue_names:
            scores["T1"] += 0.08
            scores["T2"] += 0.08
        if "wall_thickening" in cue_names or "ulcer_or_mass" in cue_names:
            scores["T2"] += 0.05
            scores["T3"] += 0.08
        supporting_evidence.append(
            "Report text cues: " + ", ".join(sorted(cue_names))
        )
    else:
        uncertainty_flags.append("No structured ultrasound report cues were available.")

    uncertainty_flags.extend(report_text.get("uncertainty_flags", []))

    if lumen_detection.get("lumen_detected"):
        supporting_evidence.append(
            f"Lumen detected (conf {float(lumen_detection.get('lumen_confidence') or 0.0):.2f})."
        )
    elif lumen_detection.get("available") is False:
        uncertainty_flags.append("Lumen detector unavailable; wall evidence may be proxy-only.")

    contour_context = payload.get("contour_context") if isinstance(payload.get("contour_context"), dict) else {}
    lumen_mask_type = str(
        wall_evidence.get("lumen_mask_type")
        or contour_context.get("lumen_mask_type")
        or ""
    )
    wall_is_proxy = (
        str(wall_evidence.get("evidence_role") or "") == "proxy_geometry"
        or not bool(wall_evidence.get("wall_layer_estimate"))
        or lumen_mask_type in {"bbox_proxy", "missing", ""}
    )
    layer_confirmed = bool(
        contour_context.get("layer_pixel_based")
        and contour_context.get("layer_label")
        and contour_context.get("in_contact") is not False
    )

    if wall_evidence.get("available"):
        wf = wall_evidence.get("wall_features") or {}
        risk = wall_evidence.get("penetration_risk", "low")
        # ContourEvidenceGate: SDF / bbox wall proxy must not alone lift T3/T4+.
        if wall_is_proxy and not layer_confirmed:
            uncertainty_flags.append(
                "ContourEvidenceGate: wall SDF/box geometry is proxy-only; "
                "it cannot alone upgrade the stage to T3/T4+ without confirmed layer/serosa evidence."
            )
            supporting_evidence.append(
                f"Wall geometry proxy ({wall_evidence.get('evidence_source')}): "
                f"penetration_risk={risk}, "
                f"fraction_outside_lumen={float(wf.get('fraction_outside_lumen') or 0.0):.2f} "
                f"(not used as pathological breakthrough)."
            )
        else:
            if risk == "high":
                scores["T3"] += 0.2
                scores["T4+"] += 0.15
            elif risk == "medium":
                scores["T3"] += 0.1
            supporting_evidence.append(
                f"Wall evidence ({wall_evidence.get('evidence_source')}): penetration_risk={risk}, "
                f"fraction_outside_lumen={float(wf.get('fraction_outside_lumen') or 0.0):.2f}."
            )
    else:
        uncertainty_flags.append("Live wall evidence unavailable; using lesion-centered proxy visuals only.")

    if gc_us_signs.get("available"):
        sign_items = gc_us_signs.get("items") or []
        sign_status = gc_us_signs.get("status", "unknown")
        normalized_i = gc_us_signs.get("normalized_i")
        supporting_evidence.append(
            f"GC-US structured sign scorer status={sign_status}, "
            f"items={len(sign_items)}, normalized_i={normalized_i if normalized_i is not None else 'n/a'}."
        )
        if any(str(item.get("status")) == "proxy" for item in sign_items if isinstance(item, dict)):
            uncertainty_flags.append("GC-US sign card includes geometry proxy evidence; physician review remains required.")
    else:
        uncertainty_flags.append("GC-US structured sign scorer was unavailable or not assessable.")

    rag_gate = _compute_rag_gate(classification, similar_cases, wall_evidence)
    rag_weight = float(rag_gate.get("rag_weight", 0.0))

    similarity_summary = _summarize_similarity(similar_cases)
    if similar_cases and rag_weight > 0:
        total = max(len(similar_cases), 1)
        for stage, count in similarity_summary["stage_distribution"].items():
            stage_key = "T4+" if stage in {"T4a", "T4b", "T4"} else stage
            if stage_key in scores:
                scores[stage_key] += rag_weight * (count / total)
        supporting_evidence.append(
            f"Similar cases (RAG weight {rag_weight:.2f}, {rag_gate.get('rag_gate_reason')}): "
            f"majority {similarity_summary['majority_stage']} from {len(similar_cases)} cases."
        )
    elif similar_cases:
        supporting_evidence.append(
            f"Similar cases retrieved ({len(similar_cases)}) but RAG gate weight=0 "
            f"({rag_gate.get('rag_gate_reason')})."
        )
    else:
        uncertainty_flags.append("No similar historical cases were available in case memory.")

    conflicting_evidence = _collect_conflicting_evidence(
        classification, similar_cases, wall_evidence, morphology
    )
    if conflicting_evidence:
        uncertainty_flags.append("Conflicting evidence streams detected; manual review recommended.")

    if not segmentation.get("available") and not segmentation.get("mask_available"):
        uncertainty_flags.append("Segmentation tool unavailable; ROI evidence is weaker.")

    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_stage, top_score = ordered[0]
    second_score = ordered[1][1] if len(ordered) > 1 else 0.0
    gap = top_score - second_score
    confidence = "high" if gap >= 0.35 else "medium" if gap >= 0.18 else "low"

    cls_top = str(classification.get("top1_stage") or "") if classification.get("available") else ""
    lesion_ready = bool(contour_context.get("lesion_confirmed")) or bool(
        (payload.get("mask_override") or {}).get("mask_polygon")
    )
    lumen_ready = lumen_mask_type in {"sam31_polygon", "confirmed_mask"} or bool(
        (payload.get("lumen_override") or {}).get("lumen_polygon")
        or (payload.get("lumen_override") or {}).get("lumen_bbox")
        or lumen_detection.get("lumen_detected")
    )
    # ContourEvidenceGate: definite cT only with confirmed layer/serosa evidence.
    # wall_proxy / incomplete contours / T1–T4+ fusion tops must not become doctor-facing cT.
    if wall_is_proxy or not layer_confirmed:
        diagnosis_status = (
            "contour_ready_layer_indeterminate"
            if (lesion_ready and lumen_ready)
            else "wall_proxy_or_unconfirmed"
        )
        display_stage = "cTx"
        diagnosis_summary = (
            "Assist display stays cTx until physician-confirmed wall-layer / serosa / adjacent-organ "
            f"evidence is available (provisional fusion={top_stage}, classifier={cls_top or 'n/a'}, "
            f"wall_proxy={bool(wall_is_proxy)}, layer_confirmed={bool(layer_confirmed)})."
        )
        uncertainty_flags.append(
            "ContourEvidenceGate: assist_display_stage=cTx; "
            "recommended_t_stage retains fusion/classifier tendency for research review only."
        )
    elif lesion_ready and lumen_ready:
        diagnosis_status = "contour_ready_provisional"
        display_stage = top_stage
        diagnosis_summary = (
            f"Contour-anchored provisional assist stage {top_stage} "
            f"(classifier={cls_top or 'n/a'}; layer/serosa evidence confirmed)."
        )
    else:
        diagnosis_status = "geometry_incomplete"
        display_stage = "cTx"
        diagnosis_summary = (
            "Lesion and/or lumen contours are incomplete; assist display stays cTx "
            f"(provisional fusion={top_stage})."
        )

    contour_diagnosis = {
        "status": diagnosis_status,
        "display_stage": display_stage,
        "provisional_stage": top_stage,
        "classifier_stage": cls_top or None,
        "lesion_confirmed": lesion_ready,
        "lumen_mask_type": lumen_mask_type or (
            "sam31_polygon"
            if (payload.get("lumen_override") or {}).get("lumen_polygon")
            else ("bbox_proxy" if (payload.get("lumen_override") or {}).get("lumen_bbox") else "missing")
        ),
        "wall_is_proxy": wall_is_proxy,
        "layer_confirmed": layer_confirmed,
        "penetration_risk": wall_evidence.get("penetration_risk") if wall_evidence.get("available") else None,
        "fraction_outside_lumen": (wall_evidence.get("wall_features") or {}).get("fraction_outside_lumen")
        if wall_evidence.get("available")
        else None,
        "geometry_relation": contour_context.get("geometry_relation"),
        "prepared_actions": contour_context.get("prepared_actions") or [],
        "summary": diagnosis_summary,
        "gate": "ContourEvidenceGate_v1",
    }

    base_report = {
        "schema_version": "0.3.0",
        "status": "ready",
        "recommended_t_stage": top_stage,
        "assist_display_stage": display_stage,
        "confidence": confidence,
        "reasoning": (
            f"{diagnosis_summary} "
            f"Top evidence: {' '.join(supporting_evidence[:3])}"
        ),
        "supporting_evidence": supporting_evidence,
        "conflicting_evidence": conflicting_evidence,
        "uncertainty_flags": uncertainty_flags,
        "similar_case_summary": similarity_summary,
        "rag_gate": rag_gate,
        "contour_diagnosis": contour_diagnosis,
        "knowledge_highlights": [item.get("title", "") for item in knowledge],
        "tool_status": {
            "lumen_detection": "available" if lumen_detection.get("lumen_detected") else (
                "partial" if lumen_detection.get("available") else "unavailable"
            ),
            "wall_evidence": "available" if wall_evidence.get("available") else "proxy_or_missing",
            "segmentation": "available" if segmentation.get("available") else "fallback",
            "classification": "available" if classification.get("available") else "unavailable",
            "morphology": "available" if morphology.get("valid") else "partial",
            "gc_us_signs": "available" if gc_us_signs.get("available") else "partial",
            "clinical": "available" if clinical.get("factors_available") else "partial",
            "report": "available" if report_text.get("available") else "missing",
            "memory": "available" if similar_cases else "partial",
            "contour_gate": diagnosis_status,
        },
    }
    return _finalize_report_with_memory(base_report, memory_context, fusion_mode=memory_fusion_mode)


def _finalize_report_with_memory(
    report: Dict[str, Any],
    memory_context: Optional[Dict[str, Any]],
    *,
    fusion_mode: str = "soft_prior",
) -> Dict[str, Any]:
    from agent.memory.memory_apply import apply_memory_to_report

    return apply_memory_to_report(report, memory_context, fusion_mode=fusion_mode)


def _maybe_llm_synthesis(base_report: Dict[str, Any], payload: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    from agent.core.llm_client import DEFAULT_BASE_URL, DEFAULT_MODEL

    mode = os.getenv("AGENT_LLM_MODE", "").strip().lower()
    if mode in {"heuristic", "offline", "none"}:
        return base_report, {
            "api_kind": "http_openai_compatible",
            "called": False,
            "status": "skipped",
            "base_url": DEFAULT_BASE_URL,
            "model": DEFAULT_MODEL,
            "skip_reason": "offline_mode",
            "total_tokens": 0,
        }

    assist_flash = mode in {"assist_deepseek", "assist_flash", "synthesis_only"}
    flash_model = (
        os.getenv("ASSIST_LLM_MODEL")
        or os.getenv("DEEPSEEK_MODEL")
        or os.getenv("AGENT_LLM_MODEL")
        or "deepseek-v4-flash"
    )
    flash_base = (
        os.getenv("ASSIST_LLM_BASE_URL")
        or os.getenv("DEEPSEEK_BASE_URL")
        or os.getenv("AGENT_LLM_BASE_URL")
        or DEFAULT_BASE_URL
    )
    active_base = flash_base if assist_flash else DEFAULT_BASE_URL
    active_model = flash_model if assist_flash else DEFAULT_MODEL

    invocation: Dict[str, Any] = {
        "api_kind": "http_openai_compatible",
        "called": False,
        "status": "skipped",
        "base_url": active_base,
        "model": active_model,
        "skip_reason": "missing_api_key",
        "total_tokens": 0,
    }
    if not any(os.getenv(key) for key in (
        "AGENT_API_KEY",
        "VLM_API_KEY",
        "POE_API_KEY",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
    )):
        return base_report, invocation

    prompt = {
        "patient_id": payload.get("patient_id"),
        "data_source": payload.get("data_source"),
        "candidate_report": base_report,
        "instruction": (
            "Rewrite only the narrative reasoning and report quality notes as compact JSON. The deterministic pipeline owns "
            "recommended_t_stage, confidence, supporting_evidence, uncertainty_flags, guideline_evidence, "
            "management_advice, and every numeric measurement; preserve those fields exactly and never change them. "
            "Return {reasoning: string, quality_notes: string[]} only. The reasoning must state what evidence is "
            "actually present and keep unknown or proxy findings explicitly unknown. Quality notes should identify "
            "missing modalities, evidence conflicts, and what the physician should verify. Do not invent missing "
            "tool outputs, treatment regimens, pathology, fluid status, or guideline claims."
        ),
    }
    try:
        from agent.core.llm_client import AgentLLMClient

        llm_kwargs: Dict[str, Any] = {
            "max_tokens": 500,
            "temperature": 0.1,
            "retries": 2,
            "disable_thinking": True,
        }
        if assist_flash:
            llm_kwargs["model"] = flash_model
            llm_kwargs["base_url"] = flash_base
            if os.getenv("DEEPSEEK_API_KEY") and "deepseek" in str(flash_base).lower():
                llm_kwargs["api_key"] = os.getenv("DEEPSEEK_API_KEY")
        llm = AgentLLMClient(**llm_kwargs)
        response = llm.chat([
            {"role": "system", "content": "You are a careful medical AI orchestrator. Return JSON only."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ])
        parsed = json.loads(response)
        merged = dict(base_report)
        locked_stage = base_report.get("recommended_t_stage")
        locked_confidence = base_report.get("confidence")
        if isinstance(parsed.get("reasoning"), str) and parsed["reasoning"].strip():
            merged["llm_reasoning"] = parsed["reasoning"].strip()
        if isinstance(parsed.get("quality_notes"), list):
            merged["llm_quality_notes"] = [
                str(item).strip()
                for item in parsed["quality_notes"]
                if str(item).strip()
            ][:8]
        merged["recommended_t_stage"] = locked_stage
        merged["confidence"] = locked_confidence
        ignored_fields = [
            key for key in parsed
            if key in {"recommended_t_stage", "confidence", "supporting_evidence", "uncertainty_flags"}
        ]
        invocation = {
            "api_kind": "http_openai_compatible",
            "called": True,
            "status": "ok",
            "base_url": getattr(llm, "base_url", active_base) or active_base,
            "model": llm.model,
            "total_tokens": llm.total_tokens,
            "request_prompt": prompt,
            "response_text": response[:8000] if isinstance(response, str) else str(response)[:8000],
            "role": "language_only",
            "assist_mode": mode or "default",
            "locked_fields": ["recommended_t_stage", "confidence", "supporting_evidence", "uncertainty_flags"],
            "ignored_output_fields": ignored_fields,
        }
        logger.info(
            "LLM synthesis API call completed: model=%s tokens=%s mode=%s",
            llm.model,
            llm.total_tokens,
            mode or "default",
        )
        return merged, invocation
    except Exception as exc:
        logger.warning("LLM synthesis fallback triggered: %s", exc)
        invocation = {
            "api_kind": "http_openai_compatible",
            "called": True,
            "status": "error",
            "base_url": active_base,
            "model": active_model,
            "error": str(exc),
            "total_tokens": 0,
            "assist_mode": mode or "default",
        }
        return base_report, invocation


def _build_runtime_verification(
    *,
    payload: Dict[str, Any],
    lumen_detection: Dict[str, Any],
    wall_evidence: Dict[str, Any],
    segmentation: Dict[str, Any],
    classification: Dict[str, Any],
    morphology: Dict[str, Any],
    clinical: Dict[str, Any],
    report_text: Dict[str, Any],
    similar_payload: Dict[str, Any],
    memory_source: str,
    llm_invocation: Dict[str, Any],
    prediction_artifacts: Dict[str, Any],
    dino_feature_artifacts: Dict[str, Any],
    gc_us_signs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Summarize which real APIs/models were invoked for frontend audit."""
    dino_enabled = bool(dino_feature_artifacts.get("enabled", True))
    dino_panel_ready = bool(dino_feature_artifacts.get("current_image_dino_feature_panel_url"))
    invocations: List[Dict[str, Any]] = [
        {
            "component": "nextjs_stream_route",
            "api_kind": "nodejs_spawn_python",
            "called": True,
            "endpoint": payload.get("source_endpoint") or "/api/agent/analyze/stream",
            "script": "pipeline/agent/product/analyze_case.py",
            "status": "ok",
        },
        {
            "component": "lumen_detection",
            **(lumen_detection.get("runtime_invocation") or {}),
            "called": bool((lumen_detection.get("runtime_invocation") or {}).get("forward_pass")),
            "status": "ok" if lumen_detection.get("lumen_detected") else (
                "partial" if lumen_detection.get("available") else "unavailable"
            ),
        },
        {
            "component": "wall_evidence",
            **(wall_evidence.get("runtime_invocation") or {}),
            "called": bool(wall_evidence.get("available")),
            "status": "ok" if wall_evidence.get("available") else wall_evidence.get("evidence_source", "unavailable"),
        },
        {
            "component": "segmentation",
            **(segmentation.get("runtime_invocation") or {}),
            "called": bool((segmentation.get("runtime_invocation") or {}).get("forward_pass")),
            "status": "ok" if segmentation.get("available") else segmentation.get("roi_source", "unavailable"),
        },
        {
            "component": "classification",
            **(classification.get("runtime_invocation") or {}),
            "called": bool((classification.get("runtime_invocation") or {}).get("forward_pass")),
            "status": "ok" if classification.get("available") else "error",
        },
        {
            "component": "morphology",
            "api_kind": "local_numpy_opencv",
            "called": morphology.get("valid") is not None,
            "status": "ok" if morphology.get("valid") else "partial",
        },
        {
            "component": "gc_us_sign_scorer",
            "api_kind": "local_numpy_rule_engine",
            "called": bool(gc_us_signs and gc_us_signs.get("available")),
            "backend_id": (gc_us_signs or {}).get("backend_id", "gc_us_sign_scorer_v1"),
            "status": "ok" if gc_us_signs and gc_us_signs.get("available") else "partial",
        },
        {
            "component": "clinical_rules",
            "api_kind": "local_rule_engine",
            "called": True,
            "status": "ok" if clinical.get("factors_available") else "partial",
        },
        {
            "component": "report_text",
            "api_kind": "local_text_parser",
            "called": True,
            "status": "ok" if report_text.get("available") else "missing",
        },
        {
            "component": "similar_case_retrieval",
            **(similar_payload.get("runtime_invocation") or {
                "api_kind": "current_case_memory" if memory_source == "current_case_memory" else "faiss_vector_search",
                "called": bool(similar_payload.get("similar_cases")),
            }),
            "called": bool(similar_payload.get("similar_cases") or similar_payload.get("available")),
            "memory_source": memory_source,
            "status": "ok" if similar_payload.get("similar_cases") else "partial",
        },
        {
            "component": "dino_feature_panel",
            "api_kind": "local_torch_dino_script",
            "called": dino_panel_ready,
            "source_script": dino_feature_artifacts.get("current_image_dino_source_script"),
            "model": dino_feature_artifacts.get("current_image_dino_model"),
            "status": "ok" if dino_panel_ready else ("skipped" if not dino_enabled else "partial"),
        },
        {
            "component": "llm_report_synthesis",
            **llm_invocation,
        },
    ]

    proxy_visuals = []
    if prediction_artifacts.get("dino_similarity_heatmap_url") and not dino_feature_artifacts.get(
        "current_image_dino_feature_panel_url"
    ):
        proxy_visuals.append("dino_region_similarity_heatmap (gradient proxy, not remote LLM)")
    if str(prediction_artifacts.get("real_wall_analysis_panel_source", "")).startswith(
        ("composed_proxy", "live_current_image")
    ):
        proxy_visuals.append("real_wall_analysis_panel (live current-image proxy)")

    required_components = {"segmentation", "classification", "nextjs_stream_route"}
    if dino_enabled:
        required_components.add("dino_feature_panel")
    failed_required = [
        str(item.get("component"))
        for item in invocations
        if item.get("component") in required_components and not item.get("called")
    ]
    degraded_components = [
        str(item.get("component"))
        for item in invocations
        if item.get("called") and item.get("status") not in {"ok", "completed"}
    ]
    core_called = not failed_required
    integrity_status = "verified" if core_called and not proxy_visuals else ("degraded" if core_called else "failed")

    return {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "session_id": payload.get("session_id"),
        "patient_id": payload.get("patient_id"),
        "all_core_models_called": core_called,
        "integrity_status": integrity_status,
        "required_components": sorted(required_components),
        "failed_required_components": failed_required,
        "degraded_components": degraded_components,
        "llm_api_called": bool(llm_invocation.get("called") and llm_invocation.get("status") == "ok"),
        "invocations": invocations,
        "proxy_visual_notes": proxy_visuals,
    }


def _format_value(value: Any, fallback: str = "未记录") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def _gc_us_field_value(state: Optional[Dict[str, Any]], *path: str, default: Any = None) -> Any:
    node: Any = state
    for key in path:
        if not isinstance(node, dict):
            return default
        node = node.get(key)
    if isinstance(node, dict) and "value" in node:
        node = node.get("value")
    return default if node is None or node == "" else node


def _gc_us_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) and number > 0 else None


def _gc_us_format_number(value: Optional[float]) -> str:
    if value is None:
        return "未评估"
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}".rstrip("0").rstrip(".")


def _gc_us_normalize_stage(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw or re.search(r"T4\s*\+", raw, re.IGNORECASE):
        return None
    matches = sorted(set(f"T{item}" for item in re.findall(r"T([1-4])", raw.upper())))
    return matches[0] if len(matches) == 1 else None


def _gc_us_strip_prefix(value: str, prefixes: tuple[str, ...]) -> str:
    text = str(value or "").strip()
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    return text or "未评估"


def _gc_us_growth_text(value: str) -> str:
    text = str(value or "").strip()
    for suffix in ("生长方式", "生长"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
            break
    return text or "未评估"


def _gc_us_template_report(
    *,
    gc_us_report: Optional[Dict[str, Any]],
    payload: Dict[str, Any],
    clinical_payload: Dict[str, Any],
    report: Dict[str, Any],
    report_text: Dict[str, Any],
    morphology: Dict[str, Any],
    wall_evidence: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the clinician-facing report from the seven-sign GC-US template."""
    state = gc_us_report if isinstance(gc_us_report, dict) else None

    def evidence_refs(*paths: str) -> List[str]:
        refs: List[str] = []
        if not isinstance(state, dict):
            return refs
        signs = state.get("signs") or {}
        for path in paths:
            current: Any = signs
            for key in path.split("."):
                current = current.get(key) if isinstance(current, dict) else None
            if isinstance(current, dict):
                values = current.get("evidence_ref") or []
                refs.extend(str(value) for value in values if value)
        return sorted(set(refs))
    tumor_size = clinical_payload.get("tumorSize", {}) if isinstance(clinical_payload, dict) else {}
    if not isinstance(tumor_size, dict):
        tumor_size = {}

    length = _gc_us_number(_gc_us_field_value(state, "signs", "size", "length"))
    thickness = _gc_us_number(_gc_us_field_value(state, "signs", "size", "thickness"))
    length_unit = _gc_us_field_value(state, "signs", "size", "length", default=None)
    thickness_unit = _gc_us_field_value(state, "signs", "size", "thickness", default=None)
    if isinstance(state, dict):
        signs_state = state.get("signs") or {}
        size_state = signs_state.get("size") if isinstance(signs_state, dict) else {}
        length_field = size_state.get("length") if isinstance(size_state, dict) else {}
        thickness_field = size_state.get("thickness") if isinstance(size_state, dict) else {}
        length_unit = length_field.get("unit") if isinstance(length_field, dict) else None
        thickness_unit = thickness_field.get("unit") if isinstance(thickness_field, dict) else None
    if length is None:
        length = _gc_us_number(tumor_size.get("length"))
        if length is not None:
            length *= 10
        length_unit = "mm"
    if thickness is None:
        thickness = _gc_us_number(tumor_size.get("thickness"))
        if thickness is not None:
            thickness *= 10
        thickness_unit = "mm"

    if length is not None and thickness is not None and length_unit != "px" and thickness_unit != "px":
        size_phrase = (
            f"大小约{_gc_us_format_number(length)}×{_gc_us_format_number(thickness)} mm，"
            f"最大厚度{_gc_us_format_number(thickness)} mm"
        )
    elif length is None and thickness is None:
        size_phrase = "大小及最大厚度未评估"
    else:
        length_text = (
            f"{_gc_us_format_number(length)}像素（非毫米）"
            if length_unit == "px"
            else f"{_gc_us_format_number(length)} mm"
        )
        thickness_text = (
            f"{_gc_us_format_number(thickness)}像素（非毫米）"
            if thickness_unit == "px"
            else f"{_gc_us_format_number(thickness)} mm"
        )
        size_phrase = f"大小约{length_text}×{thickness_text}，最大厚度{thickness_text}"

    clinical_location = clinical_payload.get("location") or clinical_payload.get("site")
    state_clinical = state.get("clinical", {}) if isinstance(state, dict) else {}
    if not isinstance(state_clinical, dict):
        state_clinical = {}
    location = str(state_clinical.get("location") or state_clinical.get("site") or clinical_location or "胃壁").strip()

    morphology_text = str(_gc_us_field_value(state, "signs", "morphology", default="") or "").strip()
    boundary_text = str(_gc_us_field_value(state, "signs", "boundary", default="") or "").strip()
    growth_text = str(_gc_us_field_value(state, "signs", "growth_pattern", default="") or "").strip()
    layer_text = str(_gc_us_field_value(state, "signs", "layer_structure", default="") or "").strip()
    serosa_text = str(_gc_us_field_value(state, "signs", "serosa_change", default="") or "").strip()
    perigastric_text = str(_gc_us_field_value(state, "signs", "perigastric_tissue", default="") or "").strip()
    echo_text = str(_gc_us_field_value(state, "signs", "lesion_echo", default="低回声") or "低回声").strip()

    wall_evidence = wall_evidence or {}
    penetration_risk = str(wall_evidence.get("penetration_risk") or "").lower()
    if not layer_text:
        layer_text = {
            "high": "结构紊乱",
            "medium": "局部受累，结构尚可辨",
            "low": "层次结构清晰",
        }.get(penetration_risk, "未评估")
    if not serosa_text:
        serosa_text = "浆膜面欠光整" if penetration_risk in {"high", "medium"} else (
            "浆膜连续光滑" if penetration_risk == "low" else "未评估"
        )
    if not perigastric_text:
        perigastric_text = "胃周脂肪间隙欠清" if penetration_risk in {"high", "medium"} else (
            "胃周组织未见明显异常改变" if penetration_risk == "low" else "未评估"
        )
    if not boundary_text:
        irregularity = _gc_us_number(morphology.get("boundary_irregularity"))
        if irregularity is not None:
            boundary_text = "边界不规则" if irregularity >= 0.45 else "边界清晰、规则"
        else:
            boundary_text = "未评估"
    if not growth_text:
        growth_text = str(
            state_clinical.get("us_growth_pattern")
            or state_clinical.get("growth_pattern_us")
            or "未评估"
        ).strip()
    if not morphology_text:
        morphology_text = str(
            state_clinical.get("morphology")
            or state_clinical.get("morphology_pattern")
            or "未评估"
        ).strip()

    if morphology_text == "未评估":
        lesion_noun = f"{echo_text}占位性病变"
    else:
        lesion_noun = f"{morphology_text}{echo_text}占位性病变"
    finding = (
        f"{location}见{lesion_noun}，{size_phrase}。"
        f"病灶呈{_gc_us_growth_text(growth_text)}生长方式，"
        f"边界{_gc_us_strip_prefix(boundary_text, ('边界',))}。"
        f"胃壁层次表现为{_gc_us_strip_prefix(layer_text, ('胃壁层次', '层次结构'))}，"
        f"浆膜表现{_gc_us_strip_prefix(serosa_text, ('浆膜面', '浆膜'))}，"
        f"胃周组织{_gc_us_strip_prefix(perigastric_text, ('胃周组织', '胃周'))}。"
    )
    smoothness = _gc_us_number(morphology.get("smoothness_index"))
    roughness = _gc_us_number(morphology.get("roughness_index"))
    expansion = _gc_us_number(morphology.get("outward_expansion_ratio"))
    geometry_cues = []
    if smoothness is not None:
        geometry_cues.append(f"轮廓平滑度{smoothness * 100:.0f}%")
    if roughness is not None:
        geometry_cues.append(f"轮廓粗糙度{roughness * 100:.0f}%")
    if expansion is not None:
        geometry_cues.append(
            f"向外扩张几何代理{expansion * 100:+.0f}%"
        )
    if geometry_cues:
        finding += (
            "当前帧轮廓几何辅助："
            + "，".join(geometry_cues)
            + "；仅作形态与方向参考，不等同于病理浸润或真实生长速度。"
        )

    reference_stage = state.get("reference_stage", {}) if isinstance(state, dict) else {}
    if not isinstance(reference_stage, dict):
        reference_stage = {}
    conflicts = []
    if isinstance(state, dict):
        conflicts = state.get("conflicts") or reference_stage.get("conflicts") or []
    stage = _gc_us_normalize_stage(reference_stage.get("band"))
    if stage is None and not conflicts:
        stage = _gc_us_normalize_stage(reference_stage.get("requested_band"))
    if stage is None and state is None:
        stage = _gc_us_normalize_stage(report.get("recommended_t_stage"))

    conflict_messages = [
        str(item.get("message"))
        for item in conflicts
        if isinstance(item, dict) and item.get("message")
    ]
    fluid_evidence = report_text.get("fluid_evidence") if isinstance(report_text, dict) else {}
    if not isinstance(fluid_evidence, dict):
        fluid_evidence = {}
    fluid_status = str(fluid_evidence.get("status") or "not_assessed").lower()
    fluid_terms = [
        str(item)
        for item in (fluid_evidence.get("matched_terms") or [])
        if str(item).strip()
    ]
    fluid_term_text = "、".join(fluid_terms[:4])
    if fluid_status == "present":
        fluid_line = (
            "文字报告提示腹腔游离液/积液可能存在"
            f"{f'（匹配词：{fluid_term_text}）' if fluid_term_text else ''}；"
            "该结果属于文本线索，需结合原始影像及其他检查确认。"
        )
    elif fluid_status == "absent":
        fluid_line = "文字报告未提示腹腔游离液/积液；这只是报告文本线索阴性，不替代影像判断。"
    elif fluid_status == "uncertain":
        fluid_line = (
            "文字报告对腹腔游离液/积液描述不确定"
            f"{f'（匹配词：{fluid_term_text}）' if fluid_term_text else ''}；建议结合影像复核。"
        )
    else:
        fluid_line = "当前未获得可用于判断腹腔游离液/积液的文字线索。"

    management_advice = report.get("management_advice") or []
    management_lines: List[str] = []
    if isinstance(management_advice, list):
        for item in management_advice[:4]:
            if isinstance(item, dict):
                action = str(item.get("action") or item.get("recommendation") or "").strip()
                basis = [
                    str(value).strip()
                    for value in (item.get("basis") or [])
                    if str(value).strip()
                ]
                if action:
                    basis_text = "；".join(basis[:2])
                    management_lines.append(f"{action}{f'（依据：{basis_text}）' if basis_text else ''}")
            elif str(item).strip():
                management_lines.append(str(item).strip())
    if not management_lines:
        management_lines.append(advice)

    review_lines = []
    if conflict_messages:
        review_lines.extend(f"证据冲突：{item}" for item in conflict_messages[:3])
    review_lines.extend(
        f"不确定性：{str(item)}"
        for item in (report.get("uncertainty_flags") or [])[:3]
        if str(item).strip()
    )
    if not review_lines:
        review_lines.append("当前未记录额外冲突；仍需医生结合原始影像完成最终确认。")

    if stage:
        impression_lines = [
            "综合超声影像征象及AI辅助分析，考虑：",
            f"胃癌可能，超声评估c{stage}期。",
        ]
    else:
        impression_lines = [
            "综合超声影像征象及AI辅助分析，考虑：",
            "胃癌可能，超声评估cTx期，浸润深度倾向尚不确定。",
        ]
    if conflict_messages:
        impression_lines.append("当前存在需要医生复核的征象冲突：" + "；".join(conflict_messages))

    advice = (
        "建议针对冲突征象进行多切面核对，必要时补扫病灶外缘及浆膜区。"
        if conflict_messages
        else "建议结合胃镜活检明确病理性质。"
    )
    patient_id = _format_value(payload.get("patient_id"), "未知")
    sections = [
        {
            "heading": "【检查信息】",
            "lines": [
                f"病例编号：{patient_id}；报告由AI辅助起草，待医生审签。",
            ],
            "evidence_refs": ["case_input:patient_id", "clinical:location", "clinical:tumor_size"],
        },
        {
            "heading": "【超声所见】",
            "lines": [finding],
            "evidence_refs": evidence_refs(
                "size.length",
                "size.thickness",
                "morphology",
                "boundary",
                "growth_pattern",
                "layer_structure",
                "serosa_change",
                "perigastric_tissue",
            ),
        },
        {
            "heading": "【腹腔及相关线索】",
            "lines": [fluid_line],
            "evidence_refs": ["report_text:fluid_evidence"],
        },
        {
            "heading": "【超声印象】",
            "lines": (
                impression_lines[:2]
                + ([f"2. {impression_lines[2]}"] if len(impression_lines) > 2 else [])
                + [f"证据融合置信度：{report.get('confidence') or '未评估'}。"]
            ),
            "evidence_refs": evidence_refs("layer_structure", "serosa_change", "perigastric_tissue"),
        },
        {
            "heading": "【证据冲突与复核重点】",
            "lines": review_lines,
            "evidence_refs": ["report:conflicting_evidence", "report:uncertainty_flags", "doctor_review:required"],
        },
        {
            "heading": "【建议】",
            "lines": [
                *[f"{index}. {line}" for index, line in enumerate(management_lines, start=1)],
                "备注：几何与规则辅助，非病理金标准；最终判断权在医生。",
            ],
            "evidence_refs": ["clinical_decision:recommendation", "doctor_review:required"],
        },
    ]
    full_text_lines: List[str] = []
    for section in sections:
        full_text_lines.extend([section["heading"], *section["lines"], ""])
    full_text = "\n".join(full_text_lines).strip()
    review_required = (
        bool(report.get("uncertainty_flags"))
        or report.get("confidence") == "low"
        or bool(conflict_messages)
        or fluid_status == "uncertain"
    )
    return {
        "title": "胃癌超声标准化辅助诊断报告草稿",
        "generated_by": "gastric-self-evolving-agent",
        "language": "zh",
        "template_id": "gc_us_t_report_template_v1",
        "schema_version": "gc_us_report_signs_v1",
        "sections": sections,
        "full_text": full_text,
        "review_required": review_required,
        "structured_signs": state.get("signs") if isinstance(state, dict) else None,
        "stage": stage or "uncertain",
        "conflicts": conflicts,
    }


def _build_dynamic_report_draft(
    payload: Dict[str, Any],
    clinical_payload: Dict[str, Any],
    report: Dict[str, Any],
    segmentation: Dict[str, Any],
    classification: Dict[str, Any],
    morphology: Dict[str, Any],
    clinical: Dict[str, Any],
    report_text: Dict[str, Any],
    similar_cases: List[Dict[str, Any]],
    wall_evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a clinician-readable draft from the GC-US seven-sign template."""
    return _gc_us_template_report(
        gc_us_report=payload.get("gc_us_report"),
        payload=payload,
        clinical_payload=clinical_payload,
        report=report,
        report_text=report_text,
        morphology=morphology,
        wall_evidence=wall_evidence,
    )


def _report_pack_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _report_pack_metric(
    metric_id: str,
    label: str,
    value: Any,
    *,
    unit: str = "",
    scale: Optional[float] = None,
    note: str = "",
) -> Optional[Dict[str, Any]]:
    number = _report_pack_number(value)
    if number is None:
        return None
    return {
        "id": metric_id,
        "label": label,
        "value": round(number, 4),
        "unit": unit,
        "scale": scale,
        "note": note,
    }


def _build_report_pack(
    *,
    payload: Dict[str, Any],
    report: Dict[str, Any],
    lumen_detection: Optional[Dict[str, Any]] = None,
    segmentation: Dict[str, Any],
    classification: Dict[str, Any],
    morphology: Dict[str, Any],
    clinical: Dict[str, Any],
    report_text: Dict[str, Any],
    similar_cases: List[Dict[str, Any]],
    wall_evidence: Optional[Dict[str, Any]] = None,
    gc_us_signs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build one clinician-facing evidence bundle for all report surfaces.

    The pack is descriptive rather than diagnostic. It lets the workbench show
    the same evidence matrix, charts, uncertainty, and review actions that the
    deterministic report used, instead of asking the UI to reverse-engineer
    scattered tool payloads.
    """
    lumen_detection = lumen_detection or {}
    wall_evidence = wall_evidence or {}
    gc_us_signs = gc_us_signs or {}
    probabilities = classification.get("probabilities") or {}
    if not isinstance(probabilities, dict):
        probabilities = {}

    stage_probability = []
    for stage in STAGES:
        value = _report_pack_number(probabilities.get(stage))
        if value is not None:
            stage_probability.append({
                "stage": stage,
                "value": round(max(0.0, min(1.0, value)), 4),
            })

    ordered_probability = sorted(stage_probability, key=lambda item: item["value"], reverse=True)
    top_gap = (
        ordered_probability[0]["value"] - ordered_probability[1]["value"]
        if len(ordered_probability) > 1
        else None
    )

    boundary_metrics = [
        _report_pack_metric(
            "boundary_irregularity",
            "边界不规则度",
            morphology.get("boundary_irregularity"),
            scale=1.0,
            note="轮廓几何代理，不等同于病理浸润深度",
        ),
        _report_pack_metric(
            "smoothness_index",
            "轮廓平滑度",
            morphology.get("smoothness_index"),
            scale=1.0,
        ),
        _report_pack_metric(
            "roughness_index",
            "轮廓粗糙度",
            morphology.get("roughness_index"),
            scale=1.0,
        ),
        _report_pack_metric(
            "convexity",
            "凸性",
            morphology.get("convexity"),
            scale=1.0,
        ),
        _report_pack_metric(
            "solidity",
            "实心度",
            morphology.get("solidity"),
            scale=1.0,
        ),
        _report_pack_metric(
            "compactness",
            "紧致度",
            morphology.get("compactness"),
            note="受像素尺度影响的形态描述",
        ),
        _report_pack_metric(
            "lesion_area_ratio",
            "病灶面积占比",
            morphology.get("lesion_area_ratio"),
            scale=1.0,
        ),
        _report_pack_metric(
            "aspect_ratio",
            "外接框长宽比",
            morphology.get("aspect_ratio"),
        ),
    ]
    boundary_metrics = [metric for metric in boundary_metrics if metric is not None]

    wall_features = wall_evidence.get("wall_features")
    if not isinstance(wall_features, dict):
        wall_features = {}
    wall_metrics = [
        _report_pack_metric(
            "fraction_outside_lumen",
            "病灶位于胃腔外比例",
            wall_features.get("fraction_outside_lumen"),
            scale=1.0,
            note="胃腔框 SDF 几何代理",
        ),
        _report_pack_metric(
            "fraction_inside_lumen",
            "病灶位于胃腔内比例",
            wall_features.get("fraction_inside_lumen"),
            scale=1.0,
        ),
        _report_pack_metric(
            "contact_arc_ratio",
            "病灶与胃腔接触弧比例",
            wall_features.get("contact_arc_ratio"),
            scale=1.0,
            note="过低时壁层代理不宜解释",
        ),
        _report_pack_metric(
            "max_outward_depth",
            "最大向外距离",
            wall_features.get("max_outward_depth"),
            unit="px",
        ),
        _report_pack_metric(
            "mean_outward_depth",
            "平均向外距离",
            wall_features.get("mean_outward_depth"),
            unit="px",
        ),
        _report_pack_metric(
            "proxy_quality_score",
            "壁层代理质量",
            wall_evidence.get("proxy_quality_score"),
            scale=1.0,
        ),
    ]
    wall_metrics = [metric for metric in wall_metrics if metric is not None]

    fluid_evidence = report_text.get("fluid_evidence")
    if not isinstance(fluid_evidence, dict):
        fluid_evidence = {
            "status": "not_assessed",
            "matched_terms": [],
            "source_sections": [],
            "evidence_role": "text_cue_only",
        }

    raw_core_sign_items = {
        str(item.get("id") or item.get("name")): item
        for item in (gc_us_signs.get("items") or [])
        if isinstance(item, dict) and (item.get("id") or item.get("name"))
    }
    feature_pack = gc_us_signs.get("feature_pack")
    feature_fields = feature_pack.get("fields") if isinstance(feature_pack, dict) else None
    if not isinstance(feature_fields, dict):
        explanation = gc_us_signs.get("explanation")
        feature_fields = explanation.get("fields") if isinstance(explanation, dict) else {}
    if not isinstance(feature_fields, dict):
        feature_fields = {}
    core_sign_specs = [
        ("size_length", "肿瘤长径"),
        ("size_thickness", "肿瘤厚度"),
        ("morphology", "肿瘤形态"),
        ("boundary", "肿瘤边界"),
        ("growth_pattern", "生长方式"),
        ("marker_cea", "CEA"),
        ("wall_structure", "胃壁结构"),
    ]
    core_sign_items = []
    for sign_id, label in core_sign_specs:
        item = raw_core_sign_items.get(sign_id)
        field = feature_fields.get(sign_id)
        if not isinstance(field, dict):
            field = {}
        if item is None and not field:
            core_sign_items.append({
                "id": sign_id,
                "label": label,
                "value": None,
                "status": "not_assessable",
                "confidence": None,
                "evidence_role": "not_assessed",
                "note": "当前证据不足，不能从缺失输入推断该征象。",
            })
            continue
        value = field.get("value")
        if value is None and item is not None:
            value = item.get("value") if item.get("value") is not None else item.get("detail")
        note = field.get("detail") or (item.get("note") if item is not None else None)
        core_sign_items.append({
            "id": sign_id,
            "label": field.get("label") or (item.get("label") if item is not None else label),
            "value": value,
            "status": field.get("status") or (item.get("status") if item is not None else "unknown"),
            "confidence": field.get("confidence") if field.get("confidence") is not None else (
                item.get("confidence") if item is not None else None
            ),
            "unit": field.get("unit") or (item.get("unit") if item is not None else None),
            "evidence_role": field.get("source") or (
                item.get("evidence_role") or item.get("source") if item is not None else "not_assessed"
            ),
            "note": note,
            "points": item.get("points") if item is not None else field.get("grade"),
            "max": item.get("max") if item is not None else field.get("grade_max"),
            "group": item.get("group") if item is not None else None,
        })

    modality_status = [
        {
            "id": "segmentation",
            "label": "病灶分割",
            "status": "available" if segmentation.get("available") or segmentation.get("mask_available") else "fallback",
            "detail": segmentation.get("roi_source") or segmentation.get("error") or "未提供",
        },
        {
            "id": "lumen",
            "label": "胃腔定位",
            "status": "available" if lumen_detection.get("lumen_detected") else (
                "partial" if lumen_detection.get("available") else "missing"
            ),
            "detail": lumen_detection.get("lumen_confidence") or lumen_detection.get("error") or "未提供",
        },
        {
            "id": "wall",
            "label": "壁层几何",
            "status": "available" if wall_evidence.get("available") else "partial",
            "detail": wall_evidence.get("penetration_risk") or wall_evidence.get("error") or "未提供",
        },
        {
            "id": "classification",
            "label": "T 分期分类器",
            "status": "available" if classification.get("available") else "unavailable",
            "detail": classification.get("backend_id") or classification.get("error") or "未提供",
        },
        {
            "id": "morphology",
            "label": "边界和形态",
            "status": "available" if morphology.get("valid") else "partial",
            "detail": morphology.get("evidence_source") or "未提供",
        },
        {
            "id": "gc_us_signs",
            "label": "七项核心征象",
            "status": "available" if gc_us_signs.get("available") else "partial",
            "detail": gc_us_signs.get("status") or "未提供",
        },
        {
            "id": "report",
            "label": "文字报告线索",
            "status": "available" if report_text.get("available") else "missing",
            "detail": ", ".join(report_text.get("sections_available") or []) or "未提供",
        },
        {
            "id": "memory",
            "label": "相似病例记忆",
            "status": "available" if similar_cases else "partial",
            "detail": f"{len(similar_cases)} 例",
        },
    ]
    conflicts = list(report.get("conflicting_evidence") or [])
    uncertainties = list(report.get("uncertainty_flags") or [])
    review_reasons = [str(item) for item in conflicts + uncertainties if item]
    review_required = bool(
        report.get("confidence") == "low"
        or review_reasons
        or wall_evidence.get("penetration_risk") in {"uncertain", "high"}
        or not classification.get("available")
    )
    next_actions = []
    if not segmentation.get("available") and not segmentation.get("mask_available"):
        next_actions.append("确认病灶边界或补充人工 ROI。")
    if not lumen_detection or not lumen_detection.get("lumen_detected"):
        next_actions.append("确认胃腔定位和充盈声窗，再解释壁层几何。")
    if wall_evidence.get("quality_flags"):
        next_actions.append("针对壁层代理质量标记进行多切面复核。")
    if fluid_evidence.get("status") in {"present", "uncertain"}:
        next_actions.append("结合增强 CT 或腹腔镜资料核对腹腔积液和腹膜播散风险。")
    if not next_actions:
        next_actions.append("结合原始影像和临床资料完成医生复核。")

    evidence_matrix = [
        {
            "id": "classifier",
            "domain": "t_staging",
            "label": "T 分期分类器",
            "value": classification.get("top1_stage") or "未输出",
            "confidence": classification.get("top1_prob"),
            "status": "available" if classification.get("available") else "unavailable",
            "source": classification.get("backend_id") or "classification_tool",
            "supports": [f"分类器首选 {classification.get('top1_stage')}"] if classification.get("top1_stage") else [],
            "refutes": [],
        },
        {
            "id": "boundary",
            "domain": "lesion",
            "label": "边界形态",
            "value": morphology.get("boundary_irregularity"),
            "confidence": morphology.get("valid"),
            "status": "available" if morphology.get("valid") else "partial",
            "source": morphology.get("evidence_source") or "lesion_mask_geometry",
            "supports": [],
            "refutes": [],
        },
        {
            "id": "wall",
            "domain": "wall",
            "label": "壁层几何代理",
            "value": wall_evidence.get("penetration_risk") or "未评估",
            "confidence": wall_evidence.get("proxy_quality_score"),
            "status": "available" if wall_evidence.get("available") else "partial",
            "source": wall_evidence.get("evidence_source") or "wall_evidence",
            "supports": [],
            "refutes": [],
        },
        {
            "id": "free_fluid",
            "domain": "extra_gastric",
            "label": "腹腔积液/游离液",
            "value": fluid_evidence.get("status") or "not_assessed",
            "confidence": None,
            "status": "available" if fluid_evidence.get("status") != "not_assessed" else "not_assessed",
            "source": "report_text",
            "supports": fluid_evidence.get("matched_terms") or [],
            "refutes": [],
        },
        {
            "id": "similar_cases",
            "domain": "memory",
            "label": "相似病例分布",
            "value": report.get("similar_case_summary", {}).get("majority_stage") if isinstance(report.get("similar_case_summary"), dict) else "未检索",
            "confidence": None,
            "status": "available" if similar_cases else "partial",
            "source": "case_memory",
            "supports": [],
            "refutes": [],
        },
    ]

    return {
        "schema_version": "doctor_report_pack_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "case": {
            "patient_id": payload.get("patient_id"),
            "case_token": payload.get("case_token"),
            "data_source": payload.get("data_source"),
            "cohort_year": payload.get("cohort_year"),
            "frame_count": payload.get("frame_count"),
        },
        "stage": {
            "recommended_t_stage": report.get("recommended_t_stage"),
            "confidence": report.get("confidence"),
            "top_gap": round(top_gap, 4) if top_gap is not None else None,
            "probabilities": stage_probability,
            "classifier_backend": classification.get("backend_id"),
        },
        "charts": {
            "stage_probability": stage_probability,
            "boundary_geometry": boundary_metrics,
            "wall_geometry": wall_metrics,
            "modality_status": modality_status,
        },
        "core_signs": core_sign_items,
        "fluid_evidence": fluid_evidence,
        "evidence_matrix": evidence_matrix,
        "review": {
            "required": review_required,
            "priority": "high" if review_required and (conflicts or report.get("confidence") == "low") else "routine",
            "reasons": review_reasons[:12],
            "next_actions": next_actions[:8],
        },
        "llm_guardrail": {
            "role": "language_only",
            "stage_owned_by": "deterministic_evidence_fusion",
            "reasoning": report.get("llm_reasoning") or "",
            "quality_notes": report.get("llm_quality_notes") or [],
        },
        "memory_loop": {
            "memory_applied": bool(report.get("memory_applied")),
            "active_rules_used": report.get("active_rules_used") or [],
            "candidate_count": len(report.get("memory_update_candidates") or []),
        },
    }


def _build_memory_update_candidates(
    payload: Dict[str, Any],
    report: Dict[str, Any],
    report_text: Dict[str, Any],
    traces: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    modalities = ["ultrasound_image", "clinical_table", "similar_cases"]
    if payload.get("roi_path"):
        modalities.append("roi")
    if payload.get("annotation_path"):
        modalities.append("mask")
    if report_text.get("available"):
        modalities.append("report_text")

    candidates = [
        {
            "record_type": "case_episode",
            "status": "candidate",
            "patient_id": str(payload.get("patient_id", "")),
            "case_token": str(payload.get("case_token", "")),
            "modalities": modalities,
            "recommended_t_stage": report.get("recommended_t_stage"),
            "confidence": report.get("confidence"),
            "supporting_evidence": report.get("supporting_evidence", [])[:6],
            "uncertainty_flags": report.get("uncertainty_flags", [])[:6],
            "tool_trace_count": len(traces),
        }
    ]

    report_cues = report_text.get("report_cues", [])
    if report_cues:
        candidates.append({
            "record_type": "procedural_rule",
            "status": "candidate",
            "title": "Report cues should be cross-checked against image and morphology evidence",
            "target_scenario": ["report_image_conflict_review", "t_staging_multimodal_review"],
            "evidence": report_cues,
        })

    return candidates


def _write_trajectory(
    payload: Dict[str, Any],
    session_id: str,
    result: Dict[str, Any],
) -> Dict[str, str]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    patient_id = str(payload.get("patient_id", "unknown"))
    trajectory_dir = Path("tmp") / "agent_trajectories" / session_id
    trajectory_dir.mkdir(parents=True, exist_ok=True)
    trajectory_path = trajectory_dir / f"{patient_id}_{timestamp}.json"
    trajectory = {
        "schema_version": "0.1.0",
        "created_at": timestamp,
        "session_id": session_id,
        "patient_id": patient_id,
        "request_summary": {
            "case_token": payload.get("case_token"),
            "data_source": payload.get("data_source"),
            "cohort_year": payload.get("cohort_year"),
            "treatment_type": payload.get("treatment_type"),
            "dataset": payload.get("dataset"),
        },
        "result": result,
    }
    trajectory_path.write_text(
        json.dumps(
            trajectory,
            ensure_ascii=False,
            indent=2,
            default=_json_default,
        ),
        encoding="utf-8",
    )
    return {
        "path": str(trajectory_path),
        "schema_version": "0.1.0",
    }


def _resolve_analysis_frames(payload: Dict[str, Any]) -> List[Dict[str, Optional[str]]]:
    max_frames = int(payload.get("max_frames", 3) or 3)
    frames_in = payload.get("frames")
    if isinstance(frames_in, list) and frames_in:
        plan: List[Dict[str, Optional[str]]] = []
        for item in frames_in[:max_frames]:
            if not isinstance(item, dict):
                continue
            img = item.get("image_path")
            if img and Path(str(img)).exists():
                plan.append({
                    "image_path": str(img),
                    "roi_path": item.get("roi_path"),
                    "annotation_path": item.get("annotation_path"),
                })
        if plan:
            return plan

    image_path = payload.get("image_path")
    if image_path and Path(str(image_path)).exists():
        return [{
            "image_path": str(image_path),
            "roi_path": payload.get("roi_path"),
            "annotation_path": payload.get("annotation_path"),
        }]
    return []


def _aggregate_classifications(classifications: List[Dict[str, Any]]) -> Dict[str, Any]:
    available = [item for item in classifications if item.get("available")]
    if not available:
        return classifications[0] if classifications else {"available": False, "error": "No frame classifications"}
    if len(available) == 1:
        merged = dict(available[0])
        merged["frame_aggregation"] = "single_frame"
        merged["aggregated_frame_count"] = 1
        return merged

    prob_sum = {stage: 0.0 for stage in STAGES}
    for item in available:
        probs = item.get("probabilities") or {}
        for stage in STAGES:
            prob_sum[stage] += float(probs.get(stage, 0.0))
    count = float(len(available))
    averaged = {stage: round(prob_sum[stage] / count, 4) for stage in STAGES}
    ordered = sorted(averaged.items(), key=lambda pair: pair[1], reverse=True)
    top1_stage, top1_prob = ordered[0]
    top2_stage, top2_prob = ordered[1] if len(ordered) > 1 else (top1_stage, 0.0)

    merged = dict(available[0])
    merged.update({
        "available": True,
        "probabilities": averaged,
        "top1_stage": top1_stage,
        "top1_prob": top1_prob,
        "top2_stage": top2_stage,
        "top2_prob": top2_prob,
        "uncertainty": round(1.0 - float(top1_prob - top2_prob), 4),
        "frame_aggregation": "mean_probability",
        "aggregated_frame_count": len(available),
    })
    return merged


def main() -> None:
    payload = _load_payload()
    from agent.product.pipeline_adapter import analyze_via_unified_pipeline

    result = analyze_via_unified_pipeline(payload)
    if _stream_enabled():
        _emit_stream_event("final", {"result": result})
    else:
        sys.stdout.write(
            json.dumps(result, ensure_ascii=False, default=_json_default)
        )


if __name__ == "__main__":
    main()

