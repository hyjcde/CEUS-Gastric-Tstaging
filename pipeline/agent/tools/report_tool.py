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

_FREE_FLUID_POSITIVE = re.compile(
    r"(腹腔|腹膜腔)?\s*(可见|见|存在|伴有|少量|中量|大量)?\s*(积液|游离液|腹水)"
    r"|腹水",
    re.I,
)
_FREE_FLUID_NEGATIVE = re.compile(
    r"(?:"
    r"(未见|未发现|未探及|无(?:明显)?|未提示|否认)\s*(腹腔|腹膜腔)?\s*(积液|游离液|腹水)"
    r"|(?:积液|游离液|腹水)\s*(未见|未发现|未探及|不存在|阴性)"
    r"|腹腔内未见液性暗区"
    r")",
    re.I,
)
_FREE_FLUID_UNCERTAIN = re.compile(
    r"(少量液性暗区|液性暗区可疑|积液待排|腹水待排|不除外积液)",
    re.I,
)


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


def _mask_negative_fluid_spans(text: str) -> str:
    masked = list(text)
    for match in _FREE_FLUID_NEGATIVE.finditer(text):
        for index in range(match.start(), match.end()):
            masked[index] = " "
    return "".join(masked)


def _extract_free_fluid_evidence(
    sections: Dict[str, str],
    full_text: str,
) -> Dict[str, Any]:
    """Extract fluid evidence without treating absent text as a negative finding."""
    negative_spans = list(_FREE_FLUID_NEGATIVE.finditer(full_text))
    negative_matches = sorted(set(match.group(0) for match in negative_spans))
    # The positive pattern intentionally accepts short forms such as "见游离液".
    # Mask explicit negative spans first so "未见游离液" is not double-counted.
    positive_search_text = _mask_negative_fluid_spans(full_text)
    positive_matches = sorted(set(match.group(0) for match in _FREE_FLUID_POSITIVE.finditer(positive_search_text)))
    uncertain_matches = sorted(set(match.group(0) for match in _FREE_FLUID_UNCERTAIN.finditer(full_text)))
    source_sections = [
        key
        for key, text in sections.items()
        if text and (
            _FREE_FLUID_POSITIVE.search(_mask_negative_fluid_spans(text))
            or _FREE_FLUID_NEGATIVE.search(text)
            or _FREE_FLUID_UNCERTAIN.search(text)
        )
    ]

    if uncertain_matches or (positive_matches and negative_matches):
        status = "uncertain"
    elif positive_matches:
        status = "present"
    elif negative_matches:
        status = "absent"
    else:
        status = "not_assessed"

    return {
        "status": status,
        "matched_terms": (positive_matches + negative_matches + uncertain_matches)[:12],
        "source_sections": source_sections,
        "evidence_role": "text_cue_only",
        "note": (
            "报告文本未提及不等于未见腹腔积液；影像学结论需医生核对。"
            if status == "not_assessed"
            else "腹腔积液状态来自报告文本线索，不能替代增强CT或腹腔镜评估。"
        ),
    }


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
                "fluid_evidence": _extract_free_fluid_evidence(sections, full_text),
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
            "fluid_evidence": _extract_free_fluid_evidence(sections, full_text),
            "text_length": len(full_text),
            "report_source": _clean_text(report_payload.get("report_source")),
            "uncertainty_flags": uncertainty_flags,
        }


def build_report_draft(
    *,
    patient_id: str,
    sample_id: str,
    clinical_concepts: Dict[str, Any],
    observations: List[Dict[str, Any]] | None = None,
    model_version: str = "report_draft_rules_20260805",
) -> Dict[str, Any]:
    """Render evidence-bound report_draft_v1 from clinical_concept_v1 only."""
    from ..multimodal.constants import RULE_VERSION
    from ..multimodal.provenance import new_evidence_id

    observations = observations or []
    concepts = (clinical_concepts or {}).get("concepts") or {}
    known_eids = []
    for field in concepts.values():
        if isinstance(field, dict):
            known_eids.extend(list(field.get("evidence_ids") or []))
    for obs in observations:
        if obs.get("evidence_id"):
            known_eids.append(str(obs["evidence_id"]))
    if not known_eids:
        known_eids = ["ev_placeholder_missing"]

    def _sentence(text: str, concept_key: str | None = None) -> Dict[str, Any]:
        eids: List[str] = []
        if concept_key and isinstance(concepts.get(concept_key), dict):
            eids = list(concepts[concept_key].get("evidence_ids") or [])
        if not eids:
            eids = [known_eids[0]]
        out: Dict[str, Any] = {"text": text, "evidence_ids": eids}
        if concept_key:
            out["concept_keys"] = [concept_key]
        return out

    visibility = (concepts.get("lesion_visibility") or {}).get("value", "unknown")
    location = (concepts.get("lesion_location") or {}).get("value", "unknown")
    size = (concepts.get("lesion_size") or {}).get("value") or {}
    wall = (concepts.get("wall_relation") or {}).get("value", "unknown")
    serosa = (concepts.get("serosal_interface") or {}).get("value", "uncertain")
    quality = (concepts.get("image_quality") or {}).get("value", "unknown")
    uncertainty = (concepts.get("uncertainty") or {}).get("value", "none")

    imaging = [
        _sentence(f"病灶可见性评估为 {visibility}。", "lesion_visibility"),
        _sentence(f"病灶位置概念为 {location}。", "lesion_location"),
    ]
    measurements = []
    long_cm = size.get("long_cm") if isinstance(size, dict) else None
    short_cm = size.get("short_cm") if isinstance(size, dict) else None
    if long_cm is not None or short_cm is not None:
        measurements.append(
            _sentence(
                f"结构化测量：长径 {long_cm} cm，厚度 {short_cm} cm。",
                "lesion_size",
            )
        )
    else:
        measurements.append(_sentence("结构化尺寸证据不足。", "lesion_size"))

    wall_serosa = [
        _sentence(f"胃壁关系概念为 {wall}。", "wall_relation"),
        _sentence(f"浆膜界面概念为 {serosa}。", "serosal_interface"),
    ]
    supporting = [
        _sentence(f"图像质量概念为 {quality}。", "image_quality"),
    ]
    conflicting: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    if uncertainty and uncertainty != "none":
        conflicting.append(_sentence(f"不确定性标记：{uncertainty}。", "uncertainty"))
    if visibility in {"unclear", "not_visible", "unknown"}:
        missing.append(_sentence("缺少稳定的病灶可视证据。", "lesion_visibility"))

    ai_suggestion = [
        _sentence(
            "AI 建议仅基于已绑定证据的概念层；最终分期与报告结论需医生确认。",
            "uncertainty",
        )
    ]
    risks = [
        _sentence(
            "禁止将病理后验或无法追溯的推断写入影像观察。",
            "uncertainty",
        )
    ]

    draft = {
        "schema_version": "report_draft_v1",
        "patient_id": patient_id,
        "sample_id": sample_id,
        "sections": {
            "imaging_observations": imaging,
            "structured_measurements": measurements,
            "wall_serosa_evidence": wall_serosa,
            "supporting_evidence": supporting,
            "conflicting_evidence": conflicting,
            "missing_evidence": missing,
            "ai_suggestion": ai_suggestion,
            "risks": risks,
        },
        "doctor_final": {
            "text": "",
            "author": "doctor",
            "locked": True,
        },
        "rule_version": RULE_VERSION,
        "model_version": model_version,
    }
    return draft


class ReportDraftTool(BaseTool):
    name = "report_draft"
    description = (
        "Build report_draft_v1 from clinical_concept_v1 with evidence_id provenance. "
        "Never overwrites doctor_final."
    )
    parameters = [
        ToolParameter("patient_id", "str", "Anonymous patient id"),
        ToolParameter("sample_id", "str", "Sample id"),
        ToolParameter("clinical_concepts", "dict", "clinical_concept_v1 object"),
        ToolParameter("observations", "list", "Optional provenanced observations", required=False, default=[]),
    ]

    def execute(
        self,
        patient_id: str = "",
        sample_id: str = "",
        clinical_concepts: Dict[str, Any] | None = None,
        observations: List[Dict[str, Any]] | None = None,
        **kwargs,
    ) -> Dict[str, Any]:
        draft = build_report_draft(
            patient_id=str(patient_id),
            sample_id=str(sample_id),
            clinical_concepts=clinical_concepts or {},
            observations=observations or [],
        )
        from ..multimodal.provenance import new_evidence_id

        eid = new_evidence_id("report_draft", patient_id=patient_id, sample_id=sample_id)
        return {
            "available": True,
            "backend_id": "report_draft_v1_rules_20260805",
            "trust_label": "supporting",
            "report_draft": draft,
            "evidence_id": eid,
            "status": "ok",
        }
