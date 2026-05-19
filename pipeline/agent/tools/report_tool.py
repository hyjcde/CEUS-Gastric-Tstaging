"""
ReportTool — structures ultrasound/endoscopy/pathology report text.

This tool is intentionally lightweight and deterministic. It does not diagnose
from free text alone; it extracts report cues so the Agent can compare them with
image-model, morphology, clinical, and memory evidence.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .base import BaseTool, ToolParameter


_DEPTH_PATTERNS = [
    ("possible_t1_t2", re.compile(r"(黏膜|粘膜|黏膜下|粘膜下|浅表|早期|局限)", re.I)),
    ("possible_t3_t4", re.compile(r"(浆膜|突破|外侵|侵犯周围|邻近脏器|全层|深肌层)", re.I)),
    ("wall_thickening", re.compile(r"(胃壁增厚|壁增厚|增厚|低回声|层次.*不清|结构.*紊乱)", re.I)),
    ("ulcer_or_mass", re.compile(r"(溃疡|肿块|隆起|凹陷|占位|不规则)", re.I)),
]


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _collect_sections(report_payload: Dict[str, Any]) -> Dict[str, str]:
    keys = [
        "ultrasound_report",
        "ultrasound_findings",
        "ultrasound_impression",
        "endoscopy_report",
        "pathology_report",
    ]
    return {key: _clean_text(report_payload.get(key)) for key in keys}


class ReportTool(BaseTool):
    name = "structure_report"
    description = (
        "Structure ultrasound/endoscopy/pathology report text into report cues. "
        "Use as supporting evidence only; do not infer final T stage from text alone."
    )
    parameters = [
        ToolParameter("report_payload", "dict", "Report text payload from frontend patient.report"),
    ]

    def execute(self, report_payload: Dict[str, Any] | None = None, **kwargs) -> Dict[str, Any]:
        report_payload = report_payload or {}
        sections = _collect_sections(report_payload)
        full_text = " ".join(text for text in sections.values() if text)
        available_sections = [key for key, text in sections.items() if text]

        if not full_text:
            return {
                "available": False,
                "backend_id": "deterministic_report_cue_extractor_20260507",
                "trust_label": "caution",
                "sections_available": [],
                "report_cues": [],
                "uncertainty_flags": ["No report text was attached to this case."],
            }

        cues: List[Dict[str, str]] = []
        for cue_name, pattern in _DEPTH_PATTERNS:
            matches = sorted(set(match.group(0) for match in pattern.finditer(full_text)))
            if matches:
                cues.append({
                    "cue": cue_name,
                    "matched_terms": matches[:8],
                })

        uncertainty_flags = []
        if "pathology_report" in available_sections:
            uncertainty_flags.append("Pathology text may contain post-operative truth; keep it separate from pre-operative inference.")
        if "ultrasound_report" not in available_sections and "ultrasound_findings" not in available_sections:
            uncertainty_flags.append("No dedicated ultrasound report section was found.")

        return {
            "available": True,
            "backend_id": "deterministic_report_cue_extractor_20260507",
            "trust_label": "caution",
            "sections_available": available_sections,
            "report_cues": cues,
            "text_length": len(full_text),
            "report_source": _clean_text(report_payload.get("report_source")),
            "uncertainty_flags": uncertainty_flags,
        }
