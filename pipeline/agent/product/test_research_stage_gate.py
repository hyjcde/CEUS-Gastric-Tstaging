import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.product.analyze_case import (
    _build_rule_based_report,
    _cap_research_stage,
    _contour_context_without_wall_draft,
    _doctor_provided_lumen,
    _guard_display_stage,
    _has_explicit_late_stage_evidence,
    _wall_draft_from_contour,
)


def test_cap_research_stage_keeps_t2():
    stage, flags = _cap_research_stage([("T2", 0.9), ("T3", 0.2), ("T4+", 0.1)], explicit_late=False)
    assert stage == "T2"
    assert flags == []


def test_cap_research_stage_demotes_t4_without_explicit_late():
    stage, flags = _cap_research_stage(
        [("T4+", 0.8), ("T1", 0.3), ("T3", 0.2)],
        explicit_late=False,
        classifier_top2="T3",
    )
    assert stage == "T3"
    assert any("top-2 T3" in item for item in flags)


def test_cap_research_stage_uses_fusion_when_top2_missing():
    stage, flags = _cap_research_stage([("T4+", 0.8), ("T2", 0.4), ("T3", 0.1)], explicit_late=False)
    assert stage == "T2"
    assert any("ResearchGate" in item and "T2" in item for item in flags)


def test_cap_research_stage_keeps_t4_with_explicit_late():
    stage, flags = _cap_research_stage([("T4+", 0.8), ("T3", 0.4)], explicit_late=True)
    assert stage == "T4+"
    assert flags == []


def test_cap_research_stage_t4_only_defaults_t3():
    stage, flags = _cap_research_stage([("T4+", 0.8)], explicit_late=False)
    assert stage == "T3"
    assert any("display T3" in item for item in flags)


def test_guard_display_stage_empty_defaults_t2():
    assert _guard_display_stage(
        "",
        wall_is_proxy=True,
        layer_confirmed=False,
        explicit_late=False,
    ) == "T2"


def test_rule_report_does_not_recommend_t4_on_proxy_wall():
    report = _build_rule_based_report(
        payload={"mask_override": {"mask_polygon": [[0, 0], [1, 0], [0, 1]]}},
        classification={
            "available": True,
            "top1_stage": "T4+",
            "top1_prob": 0.79,
            "top2_stage": "T3",
            "top2_prob": 0.15,
            "probabilities": {"T1": 0.02, "T2": 0.04, "T3": 0.15, "T4+": 0.79},
        },
        morphology={"valid": True, "boundary_irregularity": 0.2, "lesion_area_ratio": 0.04},
        clinical={},
        report_text={},
        similar_cases=[{"T_stage": "T4+"}, {"T_stage": "T4+"}, {"T_stage": "T3"}],
        knowledge=[],
        segmentation={"available": True, "mask_available": True},
        lumen_detection={"available": True, "lumen_detected": True, "lumen_confidence": 0.8},
        wall_evidence={
            "available": True,
            "evidence_role": "proxy_geometry",
            "evidence_source": "sdf_proxy",
            "penetration_risk": "high",
            "lumen_mask_type": "bbox_proxy",
            "wall_features": {"fraction_outside_lumen": 0.2},
        },
    )
    assert report["recommended_t_stage"] == "T3"
    assert report["assist_display_stage"] == "T3"
    assert report["contour_diagnosis"]["provisional_stage"] == "T4+"
    assert report["contour_diagnosis"]["lumen_optional"] is True
    assert report["contour_diagnosis"]["status"] == "contour_ready_lumen_optional"
    assert any("ResearchGate" in item for item in report.get("uncertainty_flags") or [])
    assert any("similar-case votes were not added to T3/T4+" in item for item in report.get("uncertainty_flags") or [])


def test_doctor_provided_lumen_ignores_yolo_proxy():
    assert _doctor_provided_lumen({}, {"lumen_mask_type": "missing", "lumen_optional": True}) is False
    assert _doctor_provided_lumen({}, {"lumen_mask_type": "bbox_proxy"}) is False
    assert _doctor_provided_lumen(
        {"lumen_override": {"lumen_bbox": {"x1": 1, "y1": 1, "x2": 8, "y2": 8}}},
        {"lumen_mask_type": "bbox_proxy"},
    ) is True
    assert _doctor_provided_lumen(
        {"lumen_override": {"lumen_polygon": [[0, 0], [4, 0], [2, 3]]}},
        {},
    ) is True
    assert _doctor_provided_lumen({}, {"lumen_mask_type": "sam31_polygon"}) is True


def test_wall_draft_does_not_unlock_explicit_late():
    ctx = {
        "lesion_confirmed": True,
        "wall_note": "按 1 层画：两端亮、中间暗，提示浆膜中断。请医生放大核对，不自动改分期。",
        "wall_interrupts": [{"layer": 5, "nameZh": "浆膜", "interrupted": True}],
        "wall_target_layers": 1,
        "adjacent_lock": "t3_t4",
    }
    assert _has_explicit_late_stage_evidence(ctx) is True
    assert _has_explicit_late_stage_evidence(_contour_context_without_wall_draft(ctx)) is False
    draft = _wall_draft_from_contour(ctx)
    assert draft is not None
    assert draft["not_definite_ct"] is True
    assert "浆膜" in draft["serosa_text"]
    assert "浆膜预期走行线" in draft["layer_text"]
    assert "更支持 T4" in draft["fusion_text"]


def test_wall_draft_quotes_thinning_and_local_echo():
    ctx = {
        "lesion_confirmed": True,
        "wall_target_layers": 3,
        "wall_interrupts": [{"layer": 4, "nameZh": "固有肌层", "interrupted": False}],
        "wall_ticks": [
            {"layer": 1, "nameZh": "黏膜浅层", "status": "thinned"},
            {"layer": 4, "nameZh": "固有肌层", "status": "thinned"},
        ],
        "echo_pattern": "亮暗相间",
        "peri_lesion_roi": {"x1": 10, "y1": 10, "x2": 80, "y2": 60},
        "wall_note": "提示浆膜中断",
    }
    assert _has_explicit_late_stage_evidence(_contour_context_without_wall_draft(ctx)) is False
    draft = _wall_draft_from_contour(ctx)
    assert draft is not None
    assert "黏膜浅层变薄" in draft["layer_text"]
    assert "固有肌层变薄" in draft["layer_text"]
    assert "亮暗相间" in draft["echo_text"]
    assert "灶周矩形" in draft["roi_note"]
    assert draft["not_definite_ct"] is True


def test_wall_draft_quotes_dual_deepest_windows():
    ctx = {
        "lesion_confirmed": True,
        "auto_anchors": "ok",
        "deepest_disagree": True,
        "echo_doctor_pattern": "亮-暗-中",
        "echo_ai_pattern": "暗-亮-暗",
        "analysis_focus_points": [[40, 80]],
        "ai_deepest_region": {"center": [120, 80], "radius": 12},
    }
    assert _has_explicit_late_stage_evidence(_contour_context_without_wall_draft(ctx)) is False
    draft = _wall_draft_from_contour(ctx)
    assert draft is not None
    assert "自动锚点草稿" in draft["layer_text"]
    assert "两处都作为分析窗口" in draft["layer_text"]
    assert "医生最深区回声" in draft["echo_text"]
    assert "AI 候选区回声" in draft["echo_text"]
    assert draft["not_definite_ct"] is True


def test_wall_cluster_fates_enter_staging_draft_without_unlocking_t4():
    ctx = {
        "lesion_confirmed": True,
        "wall_target_layers": 2,
        "adjacent_lock": "t2_t3",
        "wall_fates": [
            {"id": "mucosa", "nameZh": "黏膜", "verdict": "continuous", "labelZh": "黏膜连续"},
            {"id": "muscularis", "nameZh": "固有肌层", "verdict": "fused", "labelZh": "固有肌与灶融合"},
            {"id": "serosa", "nameZh": "浆膜", "verdict": "displaced", "labelZh": "浆膜受压绕行"},
        ],
        "echo_cluster": {"available": True, "pattern": "bright-dark-bright", "offsets": [-7, -1, 6], "means": [154, 80, 143]},
        "remain_px": 12,
        "wall_note": "提示浆膜中断",
    }
    assert _has_explicit_late_stage_evidence(ctx) is True
    assert _has_explicit_late_stage_evidence(_contour_context_without_wall_draft(ctx)) is False
    draft = _wall_draft_from_contour(ctx)
    assert draft is not None
    assert draft["not_definite_ct"] is True
    assert "固有肌与灶融合" in draft["layer_text"]
    assert "更支持 T3" in draft["fusion_text"]
    assert "亮-暗-亮" in draft["echo_text"]
    assert "不定 cT" in draft["fusion_text"]


def test_rule_report_keeps_t3_when_wall_draft_says_serosa_interrupted():
    report = _build_rule_based_report(
        payload={
            "mask_override": {"mask_polygon": [[0, 0], [1, 0], [0, 1]]},
            "contour_context": {
                "lesion_confirmed": True,
                "lumen_mask_type": "bbox_proxy",
                "wall_note": "提示浆膜中断",
                "wall_interrupts": [{"layer": 5, "nameZh": "浆膜", "interrupted": True}],
                "wall_target_layers": 1,
                "keyframe_interrupts": [
                    {"timeSec": 1.1, "interrupts": [{"layer": 5, "interrupted": True}]},
                    {"timeSec": 1.4, "interrupts": [{"layer": 5, "interrupted": False}]},
                ],
            },
        },
        classification={
            "available": True,
            "top1_stage": "T4+",
            "top1_prob": 0.79,
            "top2_stage": "T3",
            "top2_prob": 0.15,
            "probabilities": {"T1": 0.02, "T2": 0.04, "T3": 0.15, "T4+": 0.79},
        },
        morphology={"valid": True, "boundary_irregularity": 0.2, "lesion_area_ratio": 0.04},
        clinical={},
        report_text={},
        similar_cases=[],
        knowledge=[],
        segmentation={"available": True, "mask_available": True},
        lumen_detection={"available": True, "lumen_detected": True, "lumen_confidence": 0.8},
        wall_evidence={
            "available": True,
            "evidence_role": "proxy_geometry",
            "evidence_source": "sdf_proxy",
            "penetration_risk": "high",
            "lumen_mask_type": "bbox_proxy",
            "wall_features": {"fraction_outside_lumen": 0.2},
        },
    )
    assert report["recommended_t_stage"] == "T3"
    assert report["assist_display_stage"] == "T3"
    evidence = " ".join(report.get("supporting_evidence") or [])
    assert "不定 cT" in evidence
    assert "伪像" in evidence
    assert report["contour_diagnosis"]["wall_draft"]["not_definite_ct"] is True
