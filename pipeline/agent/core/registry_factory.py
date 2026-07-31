"""
Default ToolRegistry factory for the abdominal ultrasound Agent.

This module is the single place to wire up which tools are available to
the ReAct loop. It supersedes the per-script ``build_registry`` helpers
that lived in smoke_test.py and run_agent_batch.py — those helpers are
kept for backward compatibility but should defer to ``build_default_registry``.

Two-stage clinical workflow (2026-06-10):
  - binary_classify runs first as a gate (L0)
  - L1 T-staging + wall + clinical + RAG run when binary gate is not skip_t
  - FINISH emits ``triage_path`` so the trajectory is auditable
"""

from __future__ import annotations

import logging
from typing import Optional

from .repo_paths import PROJECT_ROOT

logger = logging.getLogger(__name__)


# Canonical tool name → registration order. Order matters because the
# ToolRegistry returns descriptions in insertion order to the LLM prompt.
_DEFAULT_TOOL_NAMES = [
    "quality_check",           # 0. QualityTool
    "binary_classify",         # 1. BinaryClassificationTool (gate, optional)
    "detect_lumen",            # 2. LumenDetectionTool
    "wall_evidence",           # 3. WallEvidenceTool
    "segment",                 # 4. SegmentationTool
    "classify",                # 5. ClassificationTool (L1 T 4-class)
    "morphology",              # 6. MorphologyTool
    "clinical_risk",           # 7. ClinicalTool
    "structure_report",        # 8. ReportTool
    "retrieve_similar",        # 9. SimilarityTool (RAG, optional)
]


def build_default_registry(
    device: Optional[str] = None,
    *,
    enable_rag: bool = True,
    enable_binary: bool = True,
    enable_dino: bool = False,
) -> "ToolRegistry":  # noqa: F821
    """
    Build the standard registry used by the ReAct loop.

    Args:
      device: torch device string ('cuda', 'cuda:0', 'cpu'). Default: auto-detect.
      enable_rag: include SimilarityTool (FAISS). Disable for environments
        without a built case index.
      enable_binary: include BinaryClassificationTool (L0 benign-vs-malignant).
        Set to False to reproduce pre-binary mainline behaviour.

    Returns:
      ToolRegistry with all enabled tools registered.
    """
    import torch

    from ..tools.base import ToolRegistry
    from ..tools.classification_tool import ClassificationTool
    from ..tools.clinical_tool import ClinicalTool
    from ..tools.lumen_detection_tool import LumenDetectionTool
    from ..tools.morphology_tool import MorphologyTool
    from ..tools.quality_tool import QualityTool
    from ..tools.report_tool import ReportTool
    from ..tools.segmentation_tool import SegmentationTool
    from ..tools.similarity_tool import SimilarityTool
    from ..tools.wall_evidence_tool import WallEvidenceTool

    if enable_binary:
        from ..tools.binary_classification_tool import BinaryClassificationTool

    if device is None:
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    device_str = str(device)

    registry = ToolRegistry()
    registry.register(QualityTool())

    if enable_binary:
        registry.register(BinaryClassificationTool(device=device_str))

    registry.register(LumenDetectionTool(device=device_str))
    registry.register(WallEvidenceTool())
    registry.register(SegmentationTool(device=device))
    registry.register(ClassificationTool(device=device))
    registry.register(MorphologyTool())
    registry.register(ClinicalTool())
    registry.register(ReportTool())
    if enable_rag:
        registry.register(SimilarityTool())

    if enable_dino:
        from ..tools.dinov3_segmentation_tool import DINOv3SegmentationTool

        registry.register(DINOv3SegmentationTool(device=device_str))

    logger.info(
        "build_default_registry: %d tools, device=%s, binary=%s, rag=%s, dino=%s",
        len(registry.tool_names), device_str, enable_binary, enable_rag, enable_dino,
    )
    return registry


def list_default_tool_names(enable_binary: bool = True, enable_rag: bool = True):
    """Return the ordered list of tools this factory would register."""
    out = list(_DEFAULT_TOOL_NAMES)
    if not enable_binary:
        out = [t for t in out if t != "binary_classify"]
    if not enable_rag:
        out = [t for t in out if t != "retrieve_similar"]
    return out
