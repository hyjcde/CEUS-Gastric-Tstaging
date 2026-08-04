from .clinical_decision_tool import ClinicalDecisionTool


def test_ct_and_ultrasound_conflict_requests_mdt_review():
    result = ClinicalDecisionTool().execute(
        report_text={"ct_report": "未见明确浆膜侵犯"},
        recommended_stage="T3",
    )

    assert result["status"] == "mdt_review"
    assert result["requires_mdt"] is True
    assert result["conflicts"][0]["code"] == "us_high_stage_ct_no_serosal_invasion"


def test_missing_cross_modal_data_is_explicit():
    result = ClinicalDecisionTool().execute(recommended_stage="T2")

    assert result["status"] == "provisional_support"
    assert "ct_report" in result["missing_modalities"]
    assert "endoscopy_report" in result["missing_modalities"]
    assert result["requires_doctor_review"] is True
