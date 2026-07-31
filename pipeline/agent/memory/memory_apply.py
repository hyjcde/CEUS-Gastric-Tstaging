"""Apply active memory to evidence report (weights / review priority only)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def apply_memory_to_report(
    report: Dict[str, Any],
    memory_context: Optional[Dict[str, Any]],
    *,
    fusion_mode: str = "soft_prior",
    max_rag_delta: float = 0.08,
) -> Dict[str, Any]:
    """Bias RAG weight and review flags from procedural/governance memory. Does not override classifier."""
    memory_context = memory_context or {}
    if not memory_context.get("memory_applied") or fusion_mode == "off":
        report["memory_applied"] = False
        report.setdefault("active_rules_used", [])
        report.setdefault("governance_trust_labels", {})
        return report

    report = dict(report)
    report["memory_applied"] = True
    report["active_rules_used"] = list(memory_context.get("active_rules_used") or [])
    report["governance_trust_labels"] = dict(memory_context.get("governance_trust_labels") or {})

    supporting: List[str] = list(report.get("supporting_evidence") or [])
    uncertainty: List[str] = list(report.get("uncertainty_flags") or [])

    for rule in memory_context.get("procedural") or []:
        title = rule.get("title") or rule.get("record_id")
        if title:
            supporting.append(f"Active procedural memory: {title}")
        if rule.get("priority") == "high" or "t2_t3_boundary" in (rule.get("target_scenario") or []):
            uncertainty.append(f"Memory review priority elevated: {title}")

    rag_gate = dict(report.get("rag_gate") or {})
    rag_weight = float(rag_gate.get("rag_weight", 0.0))
    delta = 0.0
    for gov in memory_context.get("governance") or []:
        label = str(gov.get("trust_label", "unknown"))
        tool = gov.get("tool_name") or gov.get("backend_id") or "tool"
        if label == "caution":
            delta -= max_rag_delta * 0.5
            uncertainty.append(f"Governance caution for {tool}: reduce auxiliary evidence weight.")
        elif label == "avoid":
            delta -= max_rag_delta
            uncertainty.append(f"Governance avoid for {tool}: suppress auxiliary evidence weight.")
        elif label == "trusted":
            delta += max_rag_delta * 0.25

    if fusion_mode == "soft_prior" and delta != 0.0:
        rag_weight = max(0.0, min(1.0, rag_weight + delta))
        rag_gate["rag_weight"] = round(rag_weight, 4)
        rag_gate["memory_rag_delta"] = round(delta, 4)
        report["rag_gate"] = rag_gate

    episodic = memory_context.get("episodic") or []
    if episodic:
        supporting.append(
            f"Episodic memory: {len(episodic)} similar reviewed cases retrieved."
        )

    report["supporting_evidence"] = supporting
    report["uncertainty_flags"] = uncertainty
    report["memory_context_summary"] = {
        "episodic_count": len(episodic),
        "procedural_count": len(memory_context.get("procedural") or []),
        "governance_count": len(memory_context.get("governance") or []),
        "scenario_tags": memory_context.get("scenario_tags") or [],
    }
    return report
