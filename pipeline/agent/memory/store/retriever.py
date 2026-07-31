"""Three-layer memory retrieval: episodic, procedural, governance."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from ..case_similarity import weighted_block_similarity
from ..feature_extractor import extract_patient_vector
from .jsonl_store import JsonlMemoryStore, StoreEntry
from .paths import resolve_store_paths


def _infer_scenario_tags(
    classification: Optional[Dict[str, Any]] = None,
    cohort: Optional[str] = None,
) -> List[str]:
    tags = ["t_staging_multimodal_review"]
    if cohort:
        tags.append(f"cohort:{cohort}")
    cls = classification or {}
    top1 = str(cls.get("top1_stage") or cls.get("recommended_t_stage") or "")
    probs = cls.get("probabilities") or {}
    t2 = float(probs.get("T2", 0.0))
    t3 = float(probs.get("T3", 0.0))
    if top1 in {"T2", "T3"} or abs(t2 - t3) < 0.12:
        tags.append("t2_t3_boundary")
    if top1 in {"T4+", "T4", "T4a", "T4b"}:
        tags.append("t4_boundary")
    return tags


def _entry_summary(entry: StoreEntry) -> Dict[str, Any]:
    record = entry.record
    record_type = record.get("record_type")
    base = {
        "record_id": record.get("record_id"),
        "record_type": record_type,
        "status": entry.status,
        "quality_score": entry.quality_score,
        "support_count": entry.support_count,
        "rule_signature": entry.rule_signature,
        "patient_id": entry.patient_id,
    }
    if record_type == "case_episode":
        ce = record.get("case_episode") or {}
        ar = ce.get("agent_report") or {}
        base.update({
            "recommended_t_stage": ar.get("recommended_t_stage"),
            "confidence": ar.get("confidence"),
            "cohort": ce.get("cohort"),
            "similarity": ce.get("_retrieval_similarity"),
        })
    elif record_type == "procedural_rule":
        pr = record.get("procedural_rule") or {}
        base.update({
            "title": pr.get("title"),
            "rule_text": pr.get("rule_text"),
            "target_scenario": pr.get("target_scenario"),
            "priority": pr.get("priority"),
        })
    elif record_type == "tool_governance":
        tg = record.get("tool_governance") or {}
        base.update({
            "tool_name": tg.get("tool_name"),
            "backend_id": tg.get("backend_id"),
            "trust_label": tg.get("trust_label"),
            "scenario": tg.get("scenario"),
            "rationale": tg.get("rationale"),
        })
    return base


class MemoryRetriever:
    def __init__(self, store: Optional[JsonlMemoryStore] = None, store_root: Optional[str] = None):
        self.store = store or JsonlMemoryStore(store_root=store_root)

    def load_context(
        self,
        *,
        patient_id: str,
        cohort: Optional[str] = None,
        classification: Optional[Dict[str, Any]] = None,
        backend_ids: Optional[Sequence[str]] = None,
        image_path: Optional[str] = None,
        clinical: Optional[Dict[str, Any]] = None,
        top_k_episodes: int = 5,
        top_k_rules: int = 8,
    ) -> Dict[str, Any]:
        scenario_tags = _infer_scenario_tags(classification, cohort)
        backend_ids = list(backend_ids or [])

        all_data = self.store.load_all()
        episodic = self._retrieve_episodic(
            all_data["episodes"],
            patient_id=patient_id,
            image_path=image_path,
            clinical=clinical,
            classification=classification,
            top_k=top_k_episodes,
        )
        procedural = self._retrieve_procedural(all_data["procedural_rules"], scenario_tags, top_k_rules)
        governance = self._retrieve_governance(all_data["tool_governance"], backend_ids, scenario_tags)

        return {
            "memory_applied": bool(episodic or procedural or governance),
            "scenario_tags": scenario_tags,
            "episodic": episodic,
            "procedural": procedural,
            "governance": governance,
            "active_rules_used": [r.get("title") or r.get("record_id") for r in procedural],
            "governance_trust_labels": {
                g.get("backend_id", g.get("tool_name", "unknown")): g.get("trust_label", "unknown")
                for g in governance
            },
        }

    def _retrieve_episodic(
        self,
        entries: List[StoreEntry],
        *,
        patient_id: str,
        image_path: Optional[str],
        clinical: Optional[Dict[str, Any]],
        classification: Optional[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        active = [e for e in entries if e.status == "active" and e.patient_id != patient_id]
        if not active:
            return []

        query_vec: Optional[np.ndarray] = None
        boundary_boost = False
        if image_path:
            try:
                query_vec = extract_patient_vector(image_path=image_path, clinical=clinical or {})
                probs = (classification or {}).get("probabilities") or {}
                boundary_boost = abs(float(probs.get("T2", 0)) - float(probs.get("T3", 0))) < 0.12
            except Exception:
                query_vec = None

        scored: List[tuple[float, StoreEntry]] = []
        for entry in active:
            ce = entry.record.get("case_episode") or {}
            sim = 0.0
            if query_vec is not None and ce.get("_episode_vector"):
                mem_vec = np.asarray(ce["_episode_vector"], dtype=np.float32)
                sim, _ = weighted_block_similarity(query_vec, mem_vec, boundary_boost=boundary_boost)
            elif ce.get("cohort"):
                sim = 0.35
            scored.append((sim * (0.5 + 0.5 * entry.quality_score), entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        out: List[Dict[str, Any]] = []
        for sim, entry in scored[:top_k]:
            summary = _entry_summary(entry)
            summary["similarity"] = round(sim, 4)
            out.append(summary)
        return out

    def _retrieve_procedural(
        self,
        entries: List[StoreEntry],
        scenario_tags: List[str],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        tag_set = set(scenario_tags)
        matched: List[tuple[float, StoreEntry]] = []
        for entry in entries:
            if entry.status != "active":
                continue
            pr = entry.record.get("procedural_rule") or {}
            targets = set(str(x) for x in (pr.get("target_scenario") or []))
            overlap = len(tag_set & targets)
            if not overlap and "t_staging_multimodal_review" not in targets:
                continue
            priority_boost = {"high": 0.15, "medium": 0.08, "low": 0.0}.get(str(pr.get("priority", "medium")), 0.08)
            score = overlap * 0.25 + entry.quality_score + priority_boost
            matched.append((score, entry))
        matched.sort(key=lambda x: x[0], reverse=True)
        return [_entry_summary(entry) for _, entry in matched[:top_k]]

    def _retrieve_governance(
        self,
        entries: List[StoreEntry],
        backend_ids: Sequence[str],
        scenario_tags: List[str],
    ) -> List[Dict[str, Any]]:
        tag_set = set(scenario_tags)
        backend_set = set(backend_ids)
        matched: List[tuple[float, StoreEntry]] = []
        for entry in entries:
            if entry.status != "active":
                continue
            tg = entry.record.get("tool_governance") or {}
            bid = str(tg.get("backend_id", ""))
            scenarios = set(str(x) for x in (tg.get("scenario") or []))
            if backend_set and bid and bid not in backend_set:
                continue
            if scenarios and not (tag_set & scenarios):
                continue
            helpful = int(tg.get("n_helpful") or 0)
            harmful = int(tg.get("n_harmful") or 0)
            score = entry.quality_score + 0.05 * helpful - 0.08 * harmful
            matched.append((score, entry))
        matched.sort(key=lambda x: x[0], reverse=True)
        return [_entry_summary(entry) for _, entry in matched[:12]]


def load_memory_context(store_root: Optional[str], **kwargs: Any) -> Dict[str, Any]:
    if not store_root:
        return {
            "memory_applied": False,
            "scenario_tags": [],
            "episodic": [],
            "procedural": [],
            "governance": [],
            "active_rules_used": [],
            "governance_trust_labels": {},
        }
    return MemoryRetriever(store_root=store_root).load_context(**kwargs)
