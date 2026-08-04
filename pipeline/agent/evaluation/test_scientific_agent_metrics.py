from .scientific_agent_metrics import (
    action_efficiency,
    brier_score,
    conflict_detection_rate,
    evidence_completeness,
    expected_calibration_error,
    frame_agreement_rate,
    summarize_agent_runs,
)


def test_calibration_metrics_are_bounded_and_reproducible():
    y_true = [1, 1, 0, 0]
    probs = [0.9, 0.8, 0.2, 0.1]

    assert round(brier_score(y_true, probs), 4) == 0.025
    assert 0 <= expected_calibration_error(y_true, probs) <= 1


def test_temporal_and_conflict_metrics():
    assert frame_agreement_rate(["T2", "T2", "T3"]) == 2 / 3
    assert conflict_detection_rate([True, False, False], [True, True, False]) == 0.5


def test_belief_completeness_and_action_efficiency():
    belief = {
        "evidence": [
            {"domain": "malignancy", "status": "observed"},
            {"domain": "staging", "status": "observed"},
            {"domain": "dino", "status": "observed"},
            {"domain": "clinical_decision", "status": "observed"},
        ],
        "action_trace": [
            {"status": "selected", "expected_information_gain": 0.8},
            {"status": "completed", "expected_information_gain": 0.2},
        ],
    }
    assert evidence_completeness(belief) == 1.0
    assert action_efficiency(belief["action_trace"], ["ev_1"]) == 0.8
    assert summarize_agent_runs([{"belief_state": belief, "frame_stages": ["T2", "T2"]}])["run_count"] == 1
