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
PREDICTION_ARTIFACT_ROOT = PROJECT_ROOT / "tmp" / "agent_predictions"


def _stream_enabled() -> bool:
    return os.getenv("AGENT_STREAM_EVENTS") == "1"


def _emit_stream_event(event: str, payload: Dict[str, Any]) -> None:
    if not _stream_enabled():
        return
    sys.stdout.write(json.dumps({"event": event, **payload}, ensure_ascii=False) + "\n")
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
        bml_valid = bool(maps.get("boundary_minus_lesion_valid"))
        token_h = int(maps.get("token_grid_h", 0) or 0)
        token_w = int(maps.get("token_grid_w", 0) or 0)

        image_rgb = cv2.cvtColor(cv2.imread(image_path), cv2.COLOR_BGR2RGB)
        image_rgb = cv2.resize(image_rgb, (512, 512), interpolation=cv2.INTER_AREA)
        overlay_path = prediction_artifacts.get("predicted_overlay_path")
        overlay = cv2.imread(str(overlay_path)) if overlay_path else None
        if overlay is not None:
            overlay = cv2.cvtColor(cv2.resize(overlay, (512, 512), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)

        plt.rcParams["font.family"] = "Times New Roman"
        fig, axes = plt.subplots(2, 4, figsize=(16, 7), facecolor="black")
        axes = axes.reshape(-1)
        panels = [
            (image_rgb, "Current ultrasound", None),
            (overlay if overlay is not None else image_rgb, "Predicted mask overlay", None),
            (maps["token_norm"], "DINO token norm", "viridis"),
            (maps["pca"], "DINO PCA-1", "coolwarm"),
            (maps["lesion_affinity"], "Lesion affinity", "magma"),
            (maps["wall_evidence"], "Wall evidence", "coolwarm"),
            (maps["boundary_minus_lesion"], "Boundary minus lesion", "viridis"),
        ]
        for ax, (content, title, cmap) in zip(axes, panels):
            ax.set_facecolor("black")
            ax.imshow(content, cmap=cmap)
            ax.set_title(title, color="white", fontsize=10)
            ax.axis("off")
        if not bml_valid:
            axes[6].clear()
            axes[6].set_facecolor("black")
            axes[6].text(
                0.5,
                0.5,
                "Boundary minus lesion\n(unavailable: lesion mask missing\nor boundary ring empty)",
                ha="center",
                va="center",
                color="#cdb89a",
                fontsize=9,
                wrap=True,
            )
            axes[6].axis("off")
        axes[-1].set_facecolor("black")
        axes[-1].text(
            0.5,
            0.5,
            f"Model: {hub_model}\nSource script:\ngenerate_external_source_dino_token_panels.py",
            ha="center",
            va="center",
            color="white",
            fontsize=10,
        )
        axes[-1].axis("off")
        fig.suptitle("Current-Image DINO Feature Evidence", color="white", fontsize=14, fontweight="bold")
        fig.tight_layout(rect=[0, 0, 1, 0.94])
        artifact_dir: Path = artifact_info["dir"]
        relative_dir: Path = artifact_info["relative_dir"]
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
                "Whole ultrasound frame is resized to 512x512 and forwarded through DINOv3 once; "
                "heatmaps are token-grid features upsampled. This is not ROI patch cropping or sliding-window."
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
    memory_context: Optional[Dict[str, Any]] = None,
    memory_fusion_mode: str = "soft_prior",
) -> Dict[str, Any]:
    lumen_detection = lumen_detection or {}
    wall_evidence = wall_evidence or {}
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
            f"Lumen detected (conf {float(lumen_detection.get('lumen_confidence', 0.0)):.2f})."
        )
    elif lumen_detection.get("available") is False:
        uncertainty_flags.append("Lumen detector unavailable; wall evidence may be proxy-only.")

    if wall_evidence.get("available"):
        wf = wall_evidence.get("wall_features") or {}
        risk = wall_evidence.get("penetration_risk", "low")
        if risk == "high":
            scores["T3"] += 0.2
            scores["T4+"] += 0.15
        elif risk == "medium":
            scores["T3"] += 0.1
        supporting_evidence.append(
            f"Wall evidence ({wall_evidence.get('evidence_source')}): penetration_risk={risk}, "
            f"fraction_outside_lumen={float(wf.get('fraction_outside_lumen', 0.0)):.2f}."
        )
    else:
        uncertainty_flags.append("Live wall evidence unavailable; using lesion-centered proxy visuals only.")

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

    base_report = {
        "schema_version": "0.3.0",
        "status": "ready",
        "recommended_t_stage": top_stage,
        "confidence": confidence,
        "reasoning": (
            f"Recommended {top_stage} based on tool evidence, current clinical risk, and similar-case distribution. "
            f"Top evidence: {' '.join(supporting_evidence[:3])}"
        ),
        "supporting_evidence": supporting_evidence,
        "conflicting_evidence": conflicting_evidence,
        "uncertainty_flags": uncertainty_flags,
        "similar_case_summary": similarity_summary,
        "rag_gate": rag_gate,
        "knowledge_highlights": [item.get("title", "") for item in knowledge],
        "tool_status": {
            "lumen_detection": "available" if lumen_detection.get("lumen_detected") else (
                "partial" if lumen_detection.get("available") else "unavailable"
            ),
            "wall_evidence": "available" if wall_evidence.get("available") else "proxy_or_missing",
            "segmentation": "available" if segmentation.get("available") else "fallback",
            "classification": "available" if classification.get("available") else "unavailable",
            "morphology": "available" if morphology.get("valid") else "partial",
            "clinical": "available" if clinical.get("factors_available") else "partial",
            "report": "available" if report_text.get("available") else "missing",
            "memory": "available" if similar_cases else "partial",
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

    invocation: Dict[str, Any] = {
        "api_kind": "http_openai_compatible",
        "called": False,
        "status": "skipped",
        "base_url": DEFAULT_BASE_URL,
        "model": DEFAULT_MODEL,
        "skip_reason": "missing_api_key",
        "total_tokens": 0,
    }
    if not any(os.getenv(key) for key in ("AGENT_API_KEY", "VLM_API_KEY", "POE_API_KEY", "OPENAI_API_KEY")):
        return base_report, invocation

    prompt = {
        "patient_id": payload.get("patient_id"),
        "data_source": payload.get("data_source"),
        "candidate_report": base_report,
        "instruction": (
            "Refine the candidate medical agent report into compact JSON with keys "
            "recommended_t_stage, confidence, reasoning, supporting_evidence, uncertainty_flags. "
            "Do not invent missing tool outputs."
        ),
    }
    try:
        from agent.core.llm_client import AgentLLMClient

        llm = AgentLLMClient(max_tokens=500, temperature=0.1, retries=2)
        response = llm.chat([
            {"role": "system", "content": "You are a careful medical AI orchestrator. Return JSON only."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ])
        parsed = json.loads(response)
        merged = dict(base_report)
        merged.update({k: v for k, v in parsed.items() if k in {
            "recommended_t_stage", "confidence", "reasoning", "supporting_evidence", "uncertainty_flags"
        }})
        invocation = {
            "api_kind": "http_openai_compatible",
            "called": True,
            "status": "ok",
            "base_url": DEFAULT_BASE_URL,
            "model": llm.model,
            "total_tokens": llm.total_tokens,
            "request_prompt": prompt,
            "response_text": response[:8000] if isinstance(response, str) else str(response)[:8000],
        }
        logger.info(
            "LLM synthesis API call completed: model=%s tokens=%s",
            llm.model,
            llm.total_tokens,
        )
        return merged, invocation
    except Exception as exc:
        logger.warning("LLM synthesis fallback triggered: %s", exc)
        invocation = {
            "api_kind": "http_openai_compatible",
            "called": True,
            "status": "error",
            "base_url": DEFAULT_BASE_URL,
            "model": DEFAULT_MODEL,
            "error": str(exc),
            "total_tokens": 0,
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
) -> Dict[str, Any]:
    """Summarize which real APIs/models were invoked for frontend audit."""
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
            "called": bool(dino_feature_artifacts.get("current_image_dino_feature_panel_url")),
            "source_script": dino_feature_artifacts.get("current_image_dino_source_script"),
            "model": dino_feature_artifacts.get("current_image_dino_model"),
            "status": "ok" if dino_feature_artifacts.get("current_image_dino_feature_panel_url") else "partial",
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

    required_components = {"segmentation", "classification", "dino_feature_panel", "nextjs_stream_route"}
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


def _format_stage_distribution(summary: Dict[str, Any]) -> str:
    distribution = summary.get("stage_distribution", {})
    if not distribution:
        return "未检索到可用相似病例。"
    return "，".join(f"{stage}: {count}" for stage, count in distribution.items())


def _zh_status(value: Any) -> str:
    return {
        "available": "可用",
        "fallback": "备用/降级",
        "partial": "部分可用",
        "missing": "缺失",
        "unavailable": "不可用",
        "unknown": "未知",
    }.get(str(value), _format_value(value, "未知"))


def _zh_confidence(value: Any) -> str:
    return {
        "high": "高",
        "medium": "中等",
        "low": "低",
    }.get(str(value), _format_value(value, "未知"))


def _zh_evidence_line(text: str) -> str:
    replacements = {
        "Classifier top-1": "分类模型首选分期",
        "Clinical risk score": "临床风险评分",
        "Similar cases majority stage": "相似病例多数分期",
        "from": "来自",
        "retrieved cases": "个检索病例",
        "Report text cues": "报告文本线索",
    }
    translated = text
    for source, target in replacements.items():
        translated = translated.replace(source, target)
    return translated


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
) -> Dict[str, Any]:
    """Build a clinician-readable draft from structured evidence only."""
    patient_id = _format_value(payload.get("patient_id"), "未知")
    case_token = _format_value(payload.get("case_token"), "未知")
    tumor_size = clinical_payload.get("tumorSize", {}) if isinstance(clinical_payload, dict) else {}
    biomarkers = clinical_payload.get("biomarkers", {}) if isinstance(clinical_payload, dict) else {}
    report_cues = report_text.get("report_cues", []) if report_text.get("available") else []
    cue_text = "，".join(
        f"{item.get('cue')}({', '.join(item.get('matched_terms', []))})"
        for item in report_cues
    ) or "未提取到明确报告文本线索"

    recommended_stage = report.get("recommended_t_stage", "unknown")
    confidence = report.get("confidence", "unknown")
    confidence_text = _zh_confidence(confidence)
    similar_summary = report.get("similar_case_summary", {})
    review_required = bool(report.get("uncertainty_flags")) or confidence == "low"
    tool_status = report.get("tool_status", {})
    support_lines = [_zh_evidence_line(str(item)) for item in report.get("supporting_evidence", [])[:5]]
    uncertainty_lines = [str(item) for item in report.get("uncertainty_flags", [])[:6]]

    modality_lines = [
        f"图像/ROI：{'可用' if payload.get('image_path') else '缺失'}；ROI {'可用' if payload.get('roi_path') else '缺失'}；标注 {'可用' if payload.get('annotation_path') else '缺失'}。",
        f"分割工具：{_zh_status(tool_status.get('segmentation'))}；形态学工具：{_zh_status(tool_status.get('morphology'))}。",
        f"分类工具：{_zh_status(tool_status.get('classification'))}；临床风险工具：{_zh_status(tool_status.get('clinical'))}；报告文本工具：{_zh_status(tool_status.get('report'))}。",
    ]

    sections = [
        {
            "heading": "一、病例与输入资料",
            "lines": [
                f"病例编号：{patient_id}；病例 token：{case_token}。",
                f"数据来源：{_format_value(payload.get('data_source'))}；队列：{_format_value(payload.get('cohort_year'))}；治疗类型：{_format_value(payload.get('treatment_type'))}。",
                f"基本信息：{_format_value(clinical_payload.get('sex'))}，{_format_value(clinical_payload.get('age'))} 岁；病灶部位：{_format_value(clinical_payload.get('location'))}。",
                f"病灶大小：{_format_value(tumor_size.get('length'))} x {_format_value(tumor_size.get('thickness'))} cm；CEA：{_format_value(biomarkers.get('cea'))}；CA19-9：{_format_value(biomarkers.get('ca199'))}。",
            ],
        },
        {
            "heading": "二、多模态证据摘要",
            "lines": modality_lines + [
                f"分类模型输出：top-1 为 {_format_value(classification.get('top1_stage'))}，概率 {_format_value(classification.get('top1_prob'), 'N/A')}。",
                f"形态学证据：边界不规则度 {_format_value(morphology.get('boundary_irregularity'), 'N/A')}，病灶面积占比 {_format_value(morphology.get('lesion_area_ratio'), 'N/A')}。",
                f"临床风险评分：{_format_value(clinical.get('clinical_risk_score'), 'N/A')}。",
                f"报告文本线索：{cue_text}。",
                f"相似病例：共检索 {len(similar_cases)} 例；分布 {_format_stage_distribution(similar_summary)}。",
            ],
        },
        {
            "heading": "三、Agent 综合判断",
            "lines": [
                f"综合推荐 T 分期：{recommended_stage}；置信度：{confidence_text}。",
                f"综合判断基于分类模型、临床风险、相似病例分布、分割/形态学证据和报告文本线索的交叉校验；当前不建议由单一工具直接决定最终诊断。",
                "主要支持证据：" + ("；".join(support_lines) or "暂无。"),
            ],
        },
        {
            "heading": "四、不确定性与人工复核建议",
            "lines": [
                "不确定性提示：" + ("；".join(uncertainty_lines) or "暂无明显不确定性提示。"),
                "建议：本报告为 Agent 辅助诊断草稿，应由医生结合原始超声图像、完整报告、内镜/病理资料和院内规范复核后签发。",
            ],
        },
    ]

    full_text_lines: List[str] = []
    for section in sections:
        full_text_lines.extend([section["heading"], *section["lines"], ""])
    full_text = "\n".join(full_text_lines).strip()
    return {
        "title": "胃癌超声多模态 Agent 辅助诊断报告草稿",
        "generated_by": "gastric-self-evolving-agent",
        "language": "zh",
        "sections": sections,
        "full_text": full_text,
        "review_required": review_required,
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
    trajectory_path.write_text(json.dumps(trajectory, ensure_ascii=False, indent=2), encoding="utf-8")
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
        sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

