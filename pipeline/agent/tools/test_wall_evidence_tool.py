from pipeline.agent.tools.wall_evidence_tool import bbox_geometry_quality


def test_valid_bbox_quality():
    score, flags = bbox_geometry_quality({"x1": 20, "y1": 20, "x2": 80, "y2": 80}, 100, 100)
    assert score == 1.0
    assert flags == []


def test_invalid_geometry_is_flagged():
    score, flags = bbox_geometry_quality({"x1": -4, "y1": 0, "x2": 4, "y2": 4}, 100, 100)
    assert score < 0.55
    assert "bbox_out_of_bounds" in flags
    assert "bbox_too_small" in flags
