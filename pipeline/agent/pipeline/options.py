"""Pipeline runtime options."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class PipelineOptions:
    device: Optional[str] = None
    enable_binary: bool = True
    enable_rag: bool = True
    enable_dino: bool = True
    triage_mode: str = "conditional"  # conditional | force | off
    skip_t_threshold: float = 0.95
    seg_policy: str = "auto"  # auto | unet | dino
    roi_mode: str = "predicted"  # predicted | doctor | auto — local branch ROI source for classify
    render_figures: bool = True
    emit_stream: bool = False
    stream_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
    memory_enabled: bool = False
    memory_store_path: Optional[str] = None
    memory_fusion_mode: str = "soft_prior"  # off | soft_prior
    # Workbench interactive boundary override → skip model seg when use_mask_override.
    use_mask_override: bool = False
    mask_polygon: Optional[List[Any]] = None
    wall_polygon: Optional[List[Any]] = None
    mask_path: Optional[str] = None
    override_roi_bbox: Optional[Dict[str, int]] = None
    mask_override_source: str = "manual"
    # Doctor-confirmed gastric lumen box (workbench) → prefer over YOLO for wall geometry.
    use_lumen_override: bool = False
    override_lumen_bbox: Optional[Dict[str, int]] = None
    lumen_override_source: str = "manual"
    lumen_override_polygon: Optional[List[Any]] = None
    lumen_override_meta: Optional[Dict[str, Any]] = None
    # Contour-anchored diagnosis context from the reader UI (lesion+lumen ready).
    contour_context: Optional[Dict[str, Any]] = None
    # reader Assist fast path: contour_anchored_fast | full | None
    assist_profile: Optional[str] = None
