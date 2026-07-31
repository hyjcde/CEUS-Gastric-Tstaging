"""HTML report from pipeline state (reads pre-rendered PNGs)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..pipeline.state import CasePipelineState

# Re-export rich renderer as the default single-case HTML path.
from .full_report import render_pipeline_html_report

__all__ = ["render_pipeline_html_report"]
