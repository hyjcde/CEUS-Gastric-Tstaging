"""Shared, auditable case belief state for the gastric ultrasound Agent.

This module is deliberately model-agnostic. Tools produce observations; this
state keeps competing hypotheses, provenance, conflicts, missing evidence and
the actions that led to the current belief. It is the bridge between a
reproducible workflow and a research Agent that can choose what to inspect
next.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional


BELIEF_SCHEMA_VERSION = "case_belief_state_v1"
STAGES = ("T1", "T2", "T3", "T4+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return str(value)


def make_evidence_id(
    case_id: str,
    source_type: str,
    feature: str,
    value: Any,
    frame_index: Optional[int] = None,
    timestamp_sec: Optional[float] = None,
) -> str:
    """Create a stable ID so evidence can be replayed and cited."""
    canonical = json.dumps(
        {
            "case_id": case_id,
            "source_type": source_type,
            "feature": feature,
            "value": _json_safe(value),
            "frame_index": frame_index,
            "timestamp_sec": timestamp_sec,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]
    return f"ev_{digest}"


@dataclass
class EvidenceNode:
    evidence_id: str
    case_id: str
    domain: str
    feature: str
    value: Any
    status: str
    source_type: str
    source_ref: str
    supports: List[str] = field(default_factory=list)
    refutes: List[str] = field(default_factory=list)
    confidence: Optional[float] = None
    quality_score: Optional[float] = None
    frame_index: Optional[int] = None
    timestamp_sec: Optional[float] = None
    model_version: Optional[str] = None
    rule_version: Optional[str] = None
    created_at: str = field(default_factory=_now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass
class HypothesisState:
    hypothesis_id: str
    label: str
    probability: Optional[float]
    status: str = "open"
    supporting_evidence: List[str] = field(default_factory=list)
    refuting_evidence: List[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass
class ActionCandidate:
    action_id: str
    action_type: str
    reason: str
    expected_information_gain: float
    status: str = "candidate"
    target_frame_index: Optional[int] = None
    target_timestamp_sec: Optional[float] = None
    required_evidence: List[str] = field(default_factory=list)
    selected_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass
class CaseBeliefState:
    schema_version: str
    run_id: str
    case_id: str
    patient_id: str
    hypotheses: List[HypothesisState] = field(default_factory=list)
    evidence: List[EvidenceNode] = field(default_factory=list)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    action_trace: List[ActionCandidate] = field(default_factory=list)
    next_actions: List[ActionCandidate] = field(default_factory=list)
    stop_reason: Optional[str] = None
    updated_at: str = field(default_factory=_now)

    def add_evidence(self, node: EvidenceNode) -> None:
        if not any(item.evidence_id == node.evidence_id for item in self.evidence):
            self.evidence.append(node)
            self.updated_at = _now()

    def add_conflict(self, code: str, message: str, evidence_ids: Iterable[str] = ()) -> None:
        item = {
            "code": code,
            "message": message,
            "evidence_ids": list(evidence_ids),
            "severity": "medium",
        }
        if not any(existing.get("code") == code and existing.get("message") == message for existing in self.conflicts):
            self.conflicts.append(item)
            self.updated_at = _now()

    def record_action(self, action: ActionCandidate) -> None:
        self.action_trace.append(action)
        self.updated_at = _now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "case_id": self.case_id,
            "patient_id": self.patient_id,
            "hypotheses": [item.to_dict() for item in self.hypotheses],
            "evidence": [item.to_dict() for item in self.evidence],
            "conflicts": _json_safe(self.conflicts),
            "missing_evidence": list(self.missing_evidence),
            "action_trace": [item.to_dict() for item in self.action_trace],
            "next_actions": [item.to_dict() for item in self.next_actions],
            "stop_reason": self.stop_reason,
            "updated_at": self.updated_at,
        }


def _frame_index(step: Any) -> Optional[int]:
    params = (
        getattr(step, "action_params", None)
        or getattr(step, "inputs", None)
        or {}
    )
    for key in ("frame_index", "_frame_index"):
        value = params.get(key)
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            continue
    image_path = params.get("image_path")
    if isinstance(image_path, int):
        return image_path
    if isinstance(image_path, str) and image_path.isdigit():
        return int(image_path)
    return None


def _append_observation_evidence(
    belief: CaseBeliefState,
    step: Any,
    observation: Dict[str, Any],
) -> None:
    action_name = str(
        getattr(step, "action_name", None)
        or getattr(step, "step_id", None)
        or "unknown"
    )
    frame_index = _frame_index(step)
    source_ref = f"agent_step:{action_name}"
    frame_suffix = f":frame_{frame_index}" if frame_index is not None else ""

    def add(
        domain: str,
        feature: str,
        value: Any,
        *,
        supports: Optional[List[str]] = None,
        refutes: Optional[List[str]] = None,
        confidence: Optional[float] = None,
        status: str = "observed",
        metadata: Optional[Dict[str, Any]] = None,
        frame_index_override: Optional[int] = None,
    ) -> None:
        node_frame_index = (
            frame_index_override if frame_index_override is not None else frame_index
        )
        evidence_id = make_evidence_id(
            belief.case_id,
            action_name,
            feature,
            value,
            frame_index=node_frame_index,
        )
        belief.add_evidence(
            EvidenceNode(
                evidence_id=evidence_id,
                case_id=belief.case_id,
                domain=domain,
                feature=feature,
                value=_json_safe(value),
                status=status,
                source_type=action_name,
                source_ref=f"{source_ref}{frame_suffix}",
                supports=supports or [],
                refutes=refutes or [],
                confidence=confidence,
                quality_score=observation.get("quality_score"),
                frame_index=node_frame_index,
                timestamp_sec=observation.get("timestamp_sec"),
                model_version=observation.get("backend_id") or observation.get("model"),
                rule_version=observation.get("rule_version"),
                metadata=metadata or {},
            )
        )

    probabilities = observation.get("probabilities")
    if not isinstance(probabilities, dict) and isinstance(observation.get("primary"), dict):
        probabilities = observation["primary"].get("probabilities")
    if not isinstance(probabilities, dict) and isinstance(observation.get("primary_frame"), dict):
        probabilities = observation["primary_frame"].get("probabilities")
    if isinstance(probabilities, dict):
        for stage in STAGES:
            if stage in probabilities:
                probability = float(probabilities[stage])
                add(
                    "staging",
                    f"p_{stage}",
                    probability,
                    supports=[f"stage:{stage}"] if probability >= 0.5 else [],
                    confidence=probability,
                    metadata={"probability_type": "model"},
                )

    if action_name in {"binary_classify", "binary_gate"}:
        binary_probs = observation.get("probabilities")
        if not isinstance(binary_probs, dict) and isinstance(observation.get("primary_frame"), dict):
            binary_probs = observation["primary_frame"].get("probabilities")
        if isinstance(binary_probs, dict):
            for label in ("benign", "malignant"):
                if label in binary_probs:
                    probability = float(binary_probs[label])
                    add(
                        "malignancy",
                        f"p_{label}",
                        probability,
                        supports=[f"diagnosis:{label}"] if probability >= 0.5 else [],
                        confidence=probability,
                    )
        if observation.get("gate_decision"):
            add("routing", "triage_path", observation.get("gate_decision"))

    for feature, domain in (
        ("top1_stage", "staging"),
        ("penetration_risk", "wall"),
        ("boundary_irregularity", "morphology"),
        ("clinical_risk_score", "clinical"),
        ("report_cues", "report"),
        ("recommendation_status", "decision"),
    ):
        if observation.get(feature) is not None:
            metadata = None
            if feature == "penetration_risk":
                metadata = {
                    "proxy_only": observation.get("evidence_role")
                    in {"proxy_geometry", "proxy_geometry_unavailable"}
                    or observation.get("wall_layer_estimate") is False
                }
            add(domain, feature, observation.get(feature), metadata=metadata)

    for feature in ("wall_layer", "wall_layer_estimate_value", "layer_structure"):
        if observation.get(feature) is not None:
            add(
                "wall",
                feature,
                observation.get(feature),
                metadata={"explicit_layer": True, "proxy_only": False},
            )

    frame_rows = observation.get("frames") or observation.get("per_frame")
    if isinstance(frame_rows, list):
        for row in frame_rows[:16]:
            if not isinstance(row, dict):
                continue
            frame_value = {
                key: row.get(key)
                for key in ("frame_id", "frame_index", "timestamp_sec", "quality_score", "image_path")
                if row.get(key) is not None
            }
            if frame_value:
                add(
                    "media",
                    "frame_provenance",
                    frame_value,
                    frame_index_override=row.get("frame_index"),
                    metadata={"frame_level": True},
                )

    if action_name in {"dino_sign_fusion", "dinov3_seg"}:
        dino_payload = observation.get("dino")
        if not isinstance(dino_payload, dict):
            dino_payload = {}
        add(
            "dino",
            "availability",
            observation.get("available", dino_payload.get("available")),
            metadata={"shadow_evidence": True},
        )
        for key in ("structured_signs", "sign_values", "uncertainty_flags"):
            if observation.get(key) is not None:
                add("dino", key, observation.get(key), metadata={"shadow_evidence": True})


def build_case_belief_state(
    *,
    case_id: str,
    patient_id: str,
    steps: Iterable[Any],
    frame_count: int = 0,
    run_id: str = "unknown_run",
    final_report: Optional[Dict[str, Any]] = None,
) -> CaseBeliefState:
    """Build a belief snapshot from any ReAct/pipeline step trace."""
    belief = CaseBeliefState(
        schema_version=BELIEF_SCHEMA_VERSION,
        run_id=run_id,
        case_id=case_id,
        patient_id=patient_id,
    )
    stage_probs: Dict[str, float] = {}
    malignancy_probs: Dict[str, float] = {}
    confidence_values: List[float] = []

    for step in steps:
        observation = getattr(step, "observation", None)
        if not isinstance(observation, dict):
            continue
        _append_observation_evidence(belief, step, observation)
        action_name = str(getattr(step, "action_name", "unknown"))
        thought = str(
            getattr(step, "thought", None)
            or getattr(step, "explanation", None)
            or ""
        )
        belief.record_action(
            ActionCandidate(
                action_id=f"act_{len(belief.action_trace) + 1:03d}",
                action_type=action_name,
                reason=thought[:500],
                expected_information_gain=0.0,
                status="completed" if "error" not in observation else "failed",
                target_frame_index=_frame_index(step),
                selected_at=_now(),
            )
        )
        probabilities = observation.get("probabilities")
        if not isinstance(probabilities, dict) and isinstance(observation.get("primary"), dict):
            probabilities = observation["primary"].get("probabilities")
        if not isinstance(probabilities, dict) and isinstance(observation.get("primary_frame"), dict):
            probabilities = observation["primary_frame"].get("probabilities")
        if isinstance(probabilities, dict):
            if action_name in {"binary_classify", "binary_gate"}:
                malignancy_probs.update(
                    {key: float(value) for key, value in probabilities.items() if key in {"benign", "malignant"}}
                )
            else:
                stage_probs.update(
                    {key: float(value) for key, value in probabilities.items() if key in STAGES}
                )
        if observation.get("uncertainty") is not None:
            try:
                confidence_values.append(float(observation["uncertainty"]))
            except (TypeError, ValueError):
                pass

    if malignancy_probs:
        for label in ("benign", "malignant"):
            probability = malignancy_probs.get(label)
            belief.hypotheses.append(
                HypothesisState(
                    hypothesis_id=f"diagnosis:{label}",
                    label=label,
                    probability=round(probability, 4) if probability is not None else None,
                    reason="Quality-weighted binary screening evidence.",
                )
            )
    for stage in STAGES:
        probability = stage_probs.get(stage)
        belief.hypotheses.append(
            HypothesisState(
                hypothesis_id=f"stage:{stage}",
                label=stage,
                probability=round(probability, 4) if probability is not None else None,
                reason="T-stage classification evidence.",
            )
        )

    if not stage_probs:
        belief.missing_evidence.append("t_stage_probability")
    if not malignancy_probs:
        belief.missing_evidence.append("malignancy_probability")
    if frame_count > 0 and not any(node.frame_index is not None for node in belief.evidence):
        belief.missing_evidence.append("frame_level_provenance")
    if not any(node.domain == "dino" for node in belief.evidence):
        belief.missing_evidence.append("dino_shadow_evidence")
    wall_nodes = [node for node in belief.evidence if node.domain == "wall"]
    if not wall_nodes:
        belief.missing_evidence.append("wall_proxy_geometry")
        belief.missing_evidence.append("wall_layer_evidence")
    elif not any(
        node.metadata.get("explicit_layer") is True
        and node.metadata.get("proxy_only") is not True
        for node in wall_nodes
    ):
        belief.missing_evidence.append("wall_layer_evidence")

    final_report = final_report or {}
    for conflict in final_report.get("conflicting_evidence", []) or []:
        belief.add_conflict("reported_conflict", str(conflict))
    if final_report.get("manual_review_recommended"):
        belief.add_conflict(
            "manual_review_required",
            "The current evidence is insufficient or internally inconsistent; physician review is required.",
        )

    uncertainty = max(confidence_values) if confidence_values else 1.0
    if belief.conflicts or uncertainty >= 0.9 or belief.missing_evidence:
        belief.next_actions = [
            ActionCandidate(
                action_id="next_review_frame",
                action_type="inspect_next_frame",
                reason="Resolve uncertainty or fill missing frame-level evidence.",
                expected_information_gain=0.7,
                required_evidence=["frame_level_provenance"],
            ),
            ActionCandidate(
                action_id="next_dino_region",
                action_type="run_dino_shadow_evidence",
                reason="Check whether DINO region evidence agrees with the primary mask and seven signs.",
                expected_information_gain=0.4,
                required_evidence=["dino_shadow_evidence"],
            ),
            ActionCandidate(
                action_id="next_doctor_review",
                action_type="request_doctor_confirmation",
                reason="Do not force a conclusion while conflicts or missing evidence remain.",
                expected_information_gain=0.9,
                required_evidence=["doctor_final_decision"],
            ),
        ]
    else:
        belief.stop_reason = "Evidence sufficient for a provisional physician-review recommendation."

    return belief
