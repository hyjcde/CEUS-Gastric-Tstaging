from types import SimpleNamespace

from .active_policy import ActiveEvidencePolicy
from .belief_state import build_case_belief_state


def test_belief_state_preserves_frame_provenance_and_policy_actions():
    steps = [
        SimpleNamespace(
            step_id="t_staging",
            inputs={"frame_index": 2},
            observation={
                "primary": {
                    "probabilities": {"T1": 0.08, "T2": 0.2, "T3": 0.62, "T4+": 0.1},
                    "top1_stage": "T3",
                },
            },
            explanation="T3 is provisional.",
        ),
        SimpleNamespace(
            step_id="dino_sign_fusion",
            inputs={"frame_index": 2},
            observation={
                "available": True,
                "structured_signs": {"wall": "medium"},
                "uncertainty_flags": [],
            },
            explanation="DINO shadow evidence agrees with wall evidence.",
        ),
    ]

    state = build_case_belief_state(
        case_id="BM-001",
        patient_id="BM-001",
        steps=steps,
        frame_count=3,
        run_id="test-run",
        final_report={"manual_review_recommended": True},
    )

    assert state.schema_version == "case_belief_state_v1"
    assert any(item.feature == "p_T3" for item in state.evidence)
    assert any(item.frame_index == 2 for item in state.evidence)
    assert "dino_shadow_evidence" not in state.missing_evidence
    assert state.conflicts
    assert state.next_actions
    assert ActiveEvidencePolicy().choose(state).action_type == "inspect_conflict_frame"
