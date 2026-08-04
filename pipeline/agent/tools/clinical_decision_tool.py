"""Cross-modal clinical decision support.

This is a conservative reasoning tool, not a treatment recommender. It
explicitly surfaces missing modalities and conflicts such as ultrasound cT3
versus CT without clear serosal invasion, which should trigger physician/MDT
review instead of an automatic downgrade.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .base import BaseTool, ToolParameter


_NEGATIVE_SEROSA = re.compile(
    r"(未见|未发现|没有|无|not\s+seen|no\s+(?:clear\s+)?evidence|without)"
    r".{0,30}(浆膜|外侵|serosa|serosal|extra[-\s]?gastric)",
    re.I,
)
_POSITIVE_SEROSA = re.compile(
    r"(浆膜侵犯|浆膜受侵|浆膜面中断|外侵|serosal\s+invasion|serosal\s+breach|"
    r"extra[-\s]?gastric\s+extension)",
    re.I,
)
_ENDOSCOPY_MALIGNANT = re.compile(
    r"(恶性|癌|malignan|ulcerated\s+mass|irregular\s+mass)",
    re.I,
)


def _text(payload: Dict[str, Any], *keys: str) -> str:
    values: List[str] = []
    for key in keys:
        value = payload.get(key)
        if value:
            values.append(str(value).strip())
    return "\n".join(values)


class ClinicalDecisionTool(BaseTool):
    name = "clinical_decision"
    description = (
        "Compare structured clinical context and cross-modal reports, surface "
        "conflicts or missing evidence, and produce a physician-facing MDT "
        "decision-support recommendation. Never outputs an automatic treatment plan."
    )
    parameters = [
        ToolParameter("clinical", "dict", "Structured patient clinical fields", required=False),
        ToolParameter("report_text", "dict", "Ultrasound, CT, endoscopy and pathology report fields", required=False),
        ToolParameter("recommended_stage", "str", "Current provisional ultrasound stage", required=False),
        ToolParameter("wall_evidence", "dict", "Wall evidence proxy", required=False),
    ]

    def execute(
        self,
        clinical: Dict[str, Any] | None = None,
        report_text: Dict[str, Any] | None = None,
        recommended_stage: str | None = None,
        wall_evidence: Dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        clinical = clinical or {}
        report_text = report_text or {}
        wall_evidence = wall_evidence or {}
        ultrasound = _text(
            report_text,
            "ultrasound_report",
            "ultrasound_findings",
            "ultrasound_impression",
        )
        ct = _text(report_text, "ct_report", "ct_findings", "ct_impression", "enhanced_ct_report")
        endoscopy = _text(report_text, "endoscopy_report", "gastroscopy_report")
        pathology = _text(report_text, "pathology_report")
        stage = str(recommended_stage or "").strip()
        high_stage = stage in {"T3", "T4", "T4+"} or stage.lower().startswith("ct3")
        low_stage = stage in {"T1", "T2"} or stage.lower().startswith(("ct1", "ct2"))

        conflicts: List[Dict[str, Any]] = []
        evidence: List[Dict[str, Any]] = []
        if ultrasound:
            evidence.append({"source": "ultrasound", "summary": "Ultrasound report attached"})
        if ct:
            evidence.append({"source": "ct", "summary": "CT report attached"})
        if endoscopy:
            evidence.append({"source": "endoscopy", "summary": "Endoscopy report attached"})
        if pathology:
            evidence.append({
                "source": "pathology",
                "summary": "Pathology text attached for retrospective review only",
                "role": "posterior_reference",
            })

        if high_stage and ct and _NEGATIVE_SEROSA.search(ct):
            conflicts.append({
                "code": "us_high_stage_ct_no_serosal_invasion",
                "severity": "high",
                "modalities": ["ultrasound", "ct"],
                "message": "Ultrasound suggests cT3 or higher, while CT does not describe clear serosal/extra-gastric invasion.",
            })
        if low_stage and ct and _POSITIVE_SEROSA.search(ct):
            conflicts.append({
                "code": "us_low_stage_ct_serosal_invasion",
                "severity": "high",
                "modalities": ["ultrasound", "ct"],
                "message": "CT describes serosal or extra-gastric invasion despite a low ultrasound stage suggestion.",
            })
        if endoscopy and _ENDOSCOPY_MALIGNANT.search(endoscopy):
            evidence.append({
                "source": "endoscopy",
                "summary": "Endoscopy contains malignant-appearing lesion terms",
            })

        missing_modalities = [
            name for name, value in (
                ("ct_report", ct),
                ("endoscopy_report", endoscopy),
            ) if not value
        ]
        wall_risk = str(wall_evidence.get("penetration_risk") or "").lower()
        if wall_risk == "high":
            evidence.append({
                "source": "wall_evidence",
                "summary": "Wall proxy reports high penetration risk",
                "role": "proxy_only",
            })

        if conflicts:
            status = "mdt_review"
            recommendation = (
                "跨模态证据存在冲突，建议 MDT 讨论，并结合增强 CT、胃镜/超声内镜及多切面超声复核；"
                "不得仅依据单一 cT 结果确定治疗方案。"
            )
        elif not stage:
            status = "insufficient_evidence"
            recommendation = "当前缺少可用的超声分期倾向，建议补充多切面影像和临床资料后再讨论。"
        else:
            status = "provisional_support"
            recommendation = (
                f"当前超声暂倾向 {stage}；结合临床、CT、胃镜和病理信息进行医生复核，"
                "必要时提交 MDT 讨论。"
            )

        return {
            "available": True,
            "status": status,
            "requires_mdt": bool(conflicts) or high_stage,
            "provisional_stage": stage or "uncertain",
            "recommendation": recommendation,
            "conflicts": conflicts,
            "missing_modalities": missing_modalities,
            "evidence": evidence,
            "clinical_context": {
                "age": clinical.get("age"),
                "location": clinical.get("location"),
                "tumor_size": clinical.get("tumorSize"),
                "biomarkers": clinical.get("biomarkers"),
            },
            "pathology_role": "posterior_reference" if pathology else "not_attached",
            "decision_source": "clinical_decision_rules_v1",
            "requires_doctor_review": True,
        }
