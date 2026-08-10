import cv2
import numpy as np

from pipeline.agent.tools.lumen_detection_tool import (
    lumen_bbox_from_mask,
    lumen_mask_from_polygon,
)
from pipeline.agent.tools.wall_evidence_tool import WallEvidenceTool, bbox_geometry_quality


def test_valid_bbox_quality():
    score, flags = bbox_geometry_quality({"x1": 20, "y1": 20, "x2": 80, "y2": 80}, 100, 100)
    assert score == 1.0
    assert flags == []


def test_invalid_geometry_is_flagged():
    score, flags = bbox_geometry_quality({"x1": -4, "y1": 0, "x2": 4, "y2": 4}, 100, 100)
    assert score < 0.55
    assert "bbox_out_of_bounds" in flags
    assert "bbox_too_small" in flags


def test_lumen_polygon_rasterization_preserves_geometry():
    mask = lumen_mask_from_polygon(
        [[10.0, 10.0], [40.0, 12.0], [35.0, 36.0], [12.0, 32.0]],
        height=50,
        width=60,
    )
    assert mask is not None
    assert mask.dtype == np.uint8
    assert lumen_bbox_from_mask(mask) == {"x1": 10, "y1": 10, "x2": 41, "y2": 37}


def test_confirmed_lumen_mask_replaces_rectangle_proxy(tmp_path):
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    image_path = tmp_path / "frame.png"
    assert cv2.imwrite(str(image_path), image)

    lumen = np.zeros((120, 160), dtype=np.uint8)
    cv2.ellipse(lumen, (55, 60), (28, 18), 0, 0, 360, 1, -1)
    lesion = np.zeros((120, 160), dtype=np.uint8)
    cv2.ellipse(lesion, (92, 60), (18, 12), 0, 0, 360, 255, -1)

    result = WallEvidenceTool().execute(
        image_path=str(image_path),
        lumen_bbox={"x1": 20, "y1": 35, "x2": 90, "y2": 85},
        lumen_mask=lumen,
        lumen_mask_source="confirmed_polygon",
        lesion_mask=lesion,
    )

    assert result["available"] is True
    assert result["evidence_source"] == "confirmed_lumen_mask_signed_distance"
    assert result["lumen_geometry_source"] == "confirmed_polygon"
    assert result["lumen_mask_type"] == "confirmed_mask"
    assert result["wall_features"]["lumen_area_px"] == float(np.count_nonzero(lumen))
