"""GcUsSignTool — direction-aware GC-US sign features + product soft score."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

import cv2
import numpy as np

from ..signs.scorer import build_sign_feature_pack, score_gc_us_signs
from .base import BaseTool, ToolParameter

logger = logging.getLogger(__name__)

SIGN_MODEL_METADATA = {
    "backend_id": "gc_us_sign_scorer_v1",
    "trust_label": "caution",
    "algorithm": "direction_normalized_geometry_and_clinical_rules",
    "model_family": "deterministic_evidence_scorer",
    "network_backends": {
        "lesion_mask": "segmentation_primary",
        "lumen_geometry": "lumen_detection_primary",
        "wall_evidence": "wall_evidence_lumen_sdf_v1",
    },
}


class GcUsSignTool(BaseTool):
    name = "gc_us_signs"
    description = (
        "Extract direction-normalized GC-US morphology/boundary/growth/continuity "
        "features from a lesion mask and lumen geometry, combine with clinical "
        "length/thickness/CEA/location, and emit an auditable soft scorecard. "
        "Proxy wall evidence never unlocks definite cT."
    )
    parameters = [
        ToolParameter("image_path", "str", "Absolute path to ultrasound image", required=False),
        ToolParameter("lesion_mask", "ndarray", "Binary lesion mask (H,W)", required=False),
        ToolParameter("lumen_bbox", "dict", "Lumen bounding box {x1,y1,x2,y2}", required=False),
        ToolParameter("length_cm", "float", "Clinical lesion length in cm", required=False),
        ToolParameter("thickness_cm", "float", "Clinical lesion thickness in cm", required=False),
        ToolParameter("cea_positive", "bool", "CEA positive flag", required=False),
        ToolParameter("cea_value", "float", "CEA numeric value", required=False),
        ToolParameter("location", "str", "Clinical tumor location", required=False),
        ToolParameter("layer_label", "str", "Explicit wall layer label", required=False),
        ToolParameter("serosa_text", "str", "Explicit serosa description", required=False),
        ToolParameter(
            "structural_evidence",
            "str",
            "explicit | proxy | missing",
            required=False,
            default="missing",
        ),
        ToolParameter("structural_stage", "str", "Requested structural cT if explicit", required=False),
        ToolParameter("in_contact", "bool", "Lesion-wall contact flag", required=False),
        ToolParameter("wall_polygon", "list", "Doctor wall polygon [[x,y],...]", required=False),
        ToolParameter("patient_id", "str", "Patient id for audit", required=False, default=""),
        ToolParameter("sample_id", "str", "Sample id for audit", required=False, default=""),
        ToolParameter("frame_id", "str", "Frame id for audit", required=False, default=""),
    ]

    def execute(
        self,
        image_path: Optional[str] = None,
        lesion_mask: Optional[np.ndarray] = None,
        lumen_bbox: Optional[Dict[str, int]] = None,
        length_cm: Optional[float] = None,
        thickness_cm: Optional[float] = None,
        cea_positive: Optional[bool] = None,
        cea_value: Optional[float] = None,
        location: Optional[str] = None,
        layer_label: Optional[str] = None,
        serosa_text: Optional[str] = None,
        structural_evidence: str = "missing",
        structural_stage: Optional[str] = None,
        in_contact: Optional[bool] = None,
        wall_polygon: Optional[Sequence[Sequence[float]]] = None,
        wall_mask: Optional[np.ndarray] = None,
        wall_proxy_features: Optional[Dict[str, Any]] = None,
        patient_id: str = "",
        sample_id: str = "",
        frame_id: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        if lesion_mask is None and image_path:
            # Allow mask-only workflows; image is optional for overlays later.
            image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            if image is None:
                return {
                    "available": False,
                    "error": "Could not read image and lesion_mask missing",
                    "status": "not_assessable",
                }

        if lesion_mask is None:
            # Clinical-only soft score still useful.
            pack = build_sign_feature_pack(
                length_cm=length_cm,
                thickness_cm=thickness_cm,
                cea_positive=cea_positive,
                cea_value=cea_value,
                location=location,
                layer_label=layer_label,
                serosa_text=serosa_text,
                structural_evidence=structural_evidence,
                structural_stage=structural_stage,
                in_contact=in_contact,
                patient_id=patient_id,
                sample_id=sample_id,
                frame_id=frame_id,
            )
            scored = {**SIGN_MODEL_METADATA, **score_gc_us_signs(pack)}
            scored["available"] = bool(scored.get("items"))
            scored["evidence_role"] = "clinical_soft_score"
            return scored

        lesion = np.asarray(lesion_mask)
        if lesion.dtype != np.uint8:
            lesion = lesion.astype(np.uint8)
        if lesion.max() > 1:
            lesion = (lesion > 127).astype(np.uint8)

        pack = build_sign_feature_pack(
            lesion_mask=lesion,
            lumen_bbox=lumen_bbox,
            length_cm=length_cm,
            thickness_cm=thickness_cm,
            cea_positive=cea_positive,
            cea_value=cea_value,
            location=location,
            wall_mask=wall_mask,
            wall_polygon=wall_polygon,
            layer_label=layer_label,
            serosa_text=serosa_text,
            structural_evidence=structural_evidence,
            structural_stage=structural_stage,
            in_contact=in_contact,
            wall_proxy_features=wall_proxy_features,
            patient_id=patient_id,
            sample_id=sample_id,
            frame_id=frame_id,
        )
        scored = {**SIGN_MODEL_METADATA, **score_gc_us_signs(pack)}
        scored["available"] = True
        scored["evidence_role"] = "product_soft_score_with_geometry_proxy"
        scored["risk_semantics"] = "proxy_geometry_not_pathological_layer_truth"
        return scored
