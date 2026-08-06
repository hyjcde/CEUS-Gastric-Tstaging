"""Deterministic active-evidence policy over a :class:`CaseBeliefState`.

The policy is intentionally explicit and replayable. It does not modify model
weights or staging thresholds; it only ranks the next evidence-gathering
action. A learned policy can later implement the same interface and be
evaluated against this baseline.
"""

from __future__ import annotations

from typing import List

from .belief_state import ActionCandidate, CaseBeliefState


class ActiveEvidencePolicy:
    """Rank evidence actions by uncertainty, conflict and missingness."""

    policy_id = "active_evidence_policy_rules_v1"

    def propose(self, belief: CaseBeliefState) -> List[ActionCandidate]:
        missing = set(belief.missing_evidence)
        actions: List[ActionCandidate] = []

        if belief.conflicts:
            actions.append(
                ActionCandidate(
                    action_id="policy_inspect_conflict",
                    action_type="inspect_conflict_frame",
                    reason="Conflicting evidence must be localized before a provisional decision.",
                    expected_information_gain=0.95,
                    required_evidence=["conflict_localization"],
                )
            )

        if "frame_level_provenance" in missing:
            actions.append(
                ActionCandidate(
                    action_id="policy_inspect_next_frame",
                    action_type="inspect_next_frame",
                    reason="The decision cannot be replayed without frame-level provenance.",
                    expected_information_gain=0.86,
                    required_evidence=["frame_level_provenance"],
                )
            )

        if "wall_layer_evidence" in missing:
            actions.append(
                ActionCandidate(
                    action_id="policy_wall_layer_annotation",
                    action_type="request_wall_layer_annotation",
                    reason=(
                        "The current wall result is a proxy geometry signal; "
                        "request explicit wall-layer/serosal annotation instead "
                        "of treating it as layer truth."
                    ),
                    expected_information_gain=0.84,
                    required_evidence=["explicit_wall_layer_evidence"],
                )
            )

        if "wall_proxy_geometry" in missing:
            actions.append(
                ActionCandidate(
                    action_id="policy_wall_proxy",
                    action_type="run_wall_evidence",
                    reason="Run the lumen-relative proxy to localize the wall region before annotation.",
                    expected_information_gain=0.62,
                    required_evidence=["wall_proxy_geometry"],
                )
            )

        if "dino_shadow_evidence" in missing:
            actions.append(
                ActionCandidate(
                    action_id="policy_dino_shadow",
                    action_type="run_dino_shadow_evidence",
                    reason="DINO is shadow evidence; run it to test agreement with the primary mask and signs.",
                    expected_information_gain=0.52,
                    required_evidence=["dino_shadow_evidence"],
                )
            )

        actions.append(
            ActionCandidate(
                action_id="policy_doctor_review",
                action_type="request_doctor_confirmation",
                reason="The output is decision support and requires physician confirmation.",
                expected_information_gain=0.9 if belief.conflicts else 0.35,
                required_evidence=["doctor_final_decision"],
            )
        )

        unique = {item.action_id: item for item in actions}
        return sorted(
            unique.values(),
            key=lambda item: item.expected_information_gain,
            reverse=True,
        )

    def choose(self, belief: CaseBeliefState) -> ActionCandidate | None:
        candidates = self.propose(belief)
        if not candidates:
            return None
        selected = candidates[0]
        selected.status = "selected"
        return selected
