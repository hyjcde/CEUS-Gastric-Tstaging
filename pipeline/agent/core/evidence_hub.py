"""
EvidenceHub — aggregate multi-frame evidence and generate patient-level reports.

Responsibilities:
  1. Quality-weighted probability averaging across frames
  2. Inter-frame consistency checking
  3. Conflict detection (e.g., one frame says T2, another says T3)
  4. Structured report generation (compatible with AGENT_FRONTEND_REPORT_SCHEMA.json)
"""

from __future__ import annotations

import json
import logging
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .react_loop import AgentResult, ReActStep
from .belief_state import build_case_belief_state

logger = logging.getLogger(__name__)

CLASS_NAMES = ["T1", "T2", "T3", "T4+"]


@dataclass
class FrameEvidence:
    """Evidence collected from one frame."""
    frame_index: int
    quality_score: float = 1.0
    usable: bool = True
    probabilities: Optional[Dict[str, float]] = None
    top1_stage: Optional[str] = None
    uncertainty: float = 1.0
    morphology: Optional[Dict[str, Any]] = None
    roi_source: Optional[str] = None
    mask_available: bool = False


@dataclass
class PatientReport:
    """Structured patient-level report."""
    patient_id: str
    predicted_stage: str
    secondary_candidate: Optional[str] = None
    confidence: str = "medium"
    aggregated_probs: Dict[str, float] = field(default_factory=dict)
    frame_count: int = 0
    usable_frame_count: int = 0
    frame_agreement_rate: float = 0.0
    inter_frame_entropy: float = 0.0
    key_evidence: List[str] = field(default_factory=list)
    conflicting_evidence: List[str] = field(default_factory=list)
    manual_review_recommended: bool = False
    clinical_risk_score: Optional[float] = None
    rag_used: bool = False
    rag_stage_distribution: Dict[str, int] = field(default_factory=dict)
    num_tool_calls: int = 0
    num_react_steps: int = 0
    belief_state: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patient_id": self.patient_id,
            "predicted_stage": self.predicted_stage,
            "secondary_candidate": self.secondary_candidate,
            "confidence": self.confidence,
            "aggregated_probs": self.aggregated_probs,
            "frame_count": self.frame_count,
            "usable_frame_count": self.usable_frame_count,
            "frame_agreement_rate": round(self.frame_agreement_rate, 3),
            "inter_frame_entropy": round(self.inter_frame_entropy, 3),
            "key_evidence": self.key_evidence,
            "conflicting_evidence": self.conflicting_evidence,
            "manual_review_recommended": self.manual_review_recommended,
            "clinical_risk_score": self.clinical_risk_score,
            "rag_used": self.rag_used,
            "rag_stage_distribution": self.rag_stage_distribution,
            "num_tool_calls": self.num_tool_calls,
            "num_react_steps": self.num_react_steps,
            "belief_state": self.belief_state,
        }


class EvidenceHub:
    """
    Aggregates evidence from ReAct steps into a patient-level report.
    """

    def __init__(self):
        self._frame_evidence: Dict[int, FrameEvidence] = {}
        self._clinical_result: Optional[Dict[str, Any]] = None
        self._rag_result: Optional[Dict[str, Any]] = None

    def ingest_steps(self, steps: List[ReActStep], num_frames: int) -> None:
        """Parse tool observations from ReAct steps into structured evidence."""
        # Initialise frame slots
        for i in range(num_frames):
            if i not in self._frame_evidence:
                self._frame_evidence[i] = FrameEvidence(frame_index=i)

        for step in steps:
            obs = step.observation
            if not obs or "error" in obs:
                continue

            params = step.action_params
            frame_idx = self._resolve_frame_index(params)

            if step.action_name == "quality_check" and frame_idx is not None:
                fe = self._frame_evidence.setdefault(
                    frame_idx, FrameEvidence(frame_index=frame_idx))
                fe.quality_score = obs.get("quality_score", 1.0)
                fe.usable = obs.get("usable", True)

            elif step.action_name == "segment" and frame_idx is not None:
                fe = self._frame_evidence.setdefault(
                    frame_idx, FrameEvidence(frame_index=frame_idx))
                fe.mask_available = obs.get("mask_available", False)
                fe.roi_source = obs.get("roi_source", "unknown")

            elif step.action_name == "classify" and frame_idx is not None:
                fe = self._frame_evidence.setdefault(
                    frame_idx, FrameEvidence(frame_index=frame_idx))
                fe.probabilities = obs.get("probabilities")
                fe.top1_stage = obs.get("top1_stage")
                fe.uncertainty = obs.get("uncertainty", 1.0)

            elif step.action_name == "morphology" and frame_idx is not None:
                fe = self._frame_evidence.setdefault(
                    frame_idx, FrameEvidence(frame_index=frame_idx))
                fe.morphology = obs

            elif step.action_name == "clinical_risk":
                self._clinical_result = obs

            elif step.action_name == "retrieve_similar":
                self._rag_result = obs

    def _resolve_frame_index(self, params: Dict[str, Any]) -> Optional[int]:
        """Try to determine which frame a tool call refers to."""
        if "frame_index" in params:
            try:
                return int(params["frame_index"])
            except (ValueError, TypeError):
                pass
        # Heuristic: look at image_path for frame index
        img_path = params.get("image_path", "")
        if isinstance(img_path, int):
            return img_path
        if isinstance(img_path, str) and img_path.isdigit():
            return int(img_path)
        return None

    def aggregate(self, agent_result: AgentResult,
                  num_frames: int) -> PatientReport:
        """
        Produce a patient-level report by aggregating all frame evidence.
        """
        self.ingest_steps(agent_result.steps, num_frames)

        frames = list(self._frame_evidence.values())
        usable_frames = [f for f in frames if f.usable]

        # Quality-weighted probability averaging
        agg_probs = self._weighted_average_probs(usable_frames)

        # Inter-frame agreement
        stage_votes = [f.top1_stage for f in usable_frames if f.top1_stage]
        agreement_rate = self._agreement_rate(stage_votes)
        entropy = self._stage_entropy(stage_votes)

        # Conflicts
        conflicts = self._detect_conflicts(usable_frames)

        # Determine final stage from agent or aggregation
        predicted = agent_result.predicted_stage
        if not predicted and agg_probs:
            predicted = max(agg_probs, key=agg_probs.get)

        secondary = agent_result.secondary_candidate
        if not secondary and agg_probs:
            sorted_stages = sorted(agg_probs.items(), key=lambda x: -x[1])
            if len(sorted_stages) >= 2:
                secondary = sorted_stages[1][0]

        # Confidence
        confidence = agent_result.confidence or "medium"
        if agreement_rate < 0.5 or entropy > 1.0:
            confidence = "low"

        report = PatientReport(
            patient_id=agent_result.patient_id,
            predicted_stage=predicted or "unknown",
            secondary_candidate=secondary,
            confidence=confidence,
            aggregated_probs=agg_probs,
            frame_count=num_frames,
            usable_frame_count=len(usable_frames),
            frame_agreement_rate=agreement_rate,
            inter_frame_entropy=entropy,
            key_evidence=agent_result.key_evidence,
            conflicting_evidence=agent_result.conflicting_evidence + conflicts,
            manual_review_recommended=(
                agent_result.manual_review_recommended
                or confidence == "low"
                or len(conflicts) > 0
            ),
            clinical_risk_score=(
                self._clinical_result.get("clinical_risk_score")
                if self._clinical_result else None
            ),
            rag_used=self._rag_result is not None,
            rag_stage_distribution=(
                self._rag_result.get("stage_distribution", {})
                if self._rag_result else {}
            ),
            num_tool_calls=sum(
                1 for s in agent_result.steps
                if s.action_name not in ("FINISH", "ERROR")
            ),
            num_react_steps=len(agent_result.steps),
        )
        report.belief_state = build_case_belief_state(
            case_id=agent_result.patient_id,
            patient_id=agent_result.patient_id,
            steps=agent_result.steps,
            frame_count=num_frames,
            run_id=f"react_{agent_result.patient_id}",
            final_report=agent_result.to_dict(),
        ).to_dict()
        return report

    @staticmethod
    def _weighted_average_probs(
        frames: List[FrameEvidence],
    ) -> Dict[str, float]:
        """Quality-weighted average of per-frame classification probabilities."""
        if not frames:
            return {}

        weights = []
        prob_arrays = []
        for f in frames:
            if f.probabilities:
                weights.append(f.quality_score)
                prob_arrays.append(f.probabilities)

        if not prob_arrays:
            return {}

        total_w = sum(weights) or 1.0
        agg: Dict[str, float] = {}
        for stage in CLASS_NAMES:
            agg[stage] = round(
                sum(w * p.get(stage, 0) for w, p in zip(weights, prob_arrays))
                / total_w,
                4,
            )
        return agg

    @staticmethod
    def _agreement_rate(votes: List[str]) -> float:
        if not votes:
            return 0.0
        counter = Counter(votes)
        most_common_count = counter.most_common(1)[0][1]
        return most_common_count / len(votes)

    @staticmethod
    def _stage_entropy(votes: List[str]) -> float:
        if not votes:
            return 0.0
        counter = Counter(votes)
        total = len(votes)
        entropy = 0.0
        for count in counter.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)
        return entropy

    @staticmethod
    def _detect_conflicts(frames: List[FrameEvidence]) -> List[str]:
        """Detect inter-frame prediction conflicts."""
        conflicts = []
        stages = [(f.frame_index, f.top1_stage)
                   for f in frames if f.top1_stage]
        if len(stages) < 2:
            return conflicts

        unique = set(s for _, s in stages)
        if len(unique) > 1:
            detail = ", ".join(f"frame_{i}={s}" for i, s in stages)
            conflicts.append(f"Inter-frame disagreement: {detail}")

        # T2/T3 specific conflict
        t2t3 = [s for _, s in stages if s in ("T2", "T3")]
        if "T2" in t2t3 and "T3" in t2t3:
            conflicts.append("T2/T3 boundary conflict across frames")

        return conflicts
