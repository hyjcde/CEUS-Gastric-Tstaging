#!/usr/bin/env python3
"""Unit tests for GC-US direction-normalized sign scoring."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.agent.signs.direction_growth import (  # noqa: E402
    aggregate_multiframe_features,
    compute_direction_growth_features,
    continuous_arc_metrics,
)
from pipeline.agent.signs.scorer import build_sign_feature_pack, score_gc_us_signs  # noqa: E402
from pipeline.agent.signs.wall_gate import (  # noqa: E402
    assess_structural_gate,
    compute_wall_continuity_features,
    structural_stage_from_explicit_signs,
)


def _ellipse_mask(h=160, w=200, cy=80, cx=120, ry=28, rx=40) -> np.ndarray:
    yy, xx = np.ogrid[:h, :w]
    m = (((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2) <= 1.0
    return m.astype(np.uint8)


def _outward_bump_mask() -> np.ndarray:
    """Lesion with an outward (rightward) protrusion relative to left lumen."""
    m = _ellipse_mask()
    # Add a bump on the right (away from lumen at left).
    yy, xx = np.ogrid[:160, :200]
    bump = (((yy - 80) / 10) ** 2 + ((xx - 165) / 18) ** 2) <= 1.0
    return np.clip(m + bump.astype(np.uint8), 0, 1).astype(np.uint8)


class TestContinuousArc(unittest.TestCase):
    def test_full_and_empty(self):
        full = continuous_arc_metrics(np.ones(20, dtype=bool))
        self.assertEqual(full["longest_arc_frac"], 1.0)
        empty = continuous_arc_metrics(np.zeros(20, dtype=bool))
        self.assertEqual(empty["longest_arc_frac"], 0.0)

    def test_wrap_around_run(self):
        flags = np.zeros(20, dtype=bool)
        flags[-3:] = True
        flags[:4] = True
        metrics = continuous_arc_metrics(flags)
        self.assertAlmostEqual(metrics["longest_arc_frac"], 7 / 20, places=5)


class TestDirectionGrowth(unittest.TestCase):
    def test_outward_sector_and_proxy_status(self):
        lesion = _outward_bump_mask()
        lumen_bbox = {"x1": 10, "y1": 40, "x2": 70, "y2": 120}
        feat = compute_direction_growth_features(lesion, lumen_bbox=lumen_bbox)
        self.assertTrue(feat["available"])
        self.assertEqual(feat["direction_source"], "lumen_bbox_center")
        self.assertFalse(feat["used_fallback"])
        self.assertIn(feat["status"], {"proxy", "not_assessable"})
        self.assertGreater(feat["sector_frac"]["outward_facing"], 0.05)
        self.assertIn("longest_arc_frac", feat["continuity"])
        self.assertEqual(
            feat["continuity"]["semantic"],
            "spatial_sign_continuity_not_tumor_growth_rate",
        )

    def test_missing_direction_fallback_not_assessable(self):
        lesion = _ellipse_mask()
        feat = compute_direction_growth_features(lesion, lumen_bbox=None)
        self.assertTrue(feat["used_fallback"])
        self.assertEqual(feat["status"], "not_assessable")

    def test_confirmed_lumen_mask_controls_direction_and_contact(self):
        lesion = _outward_bump_mask()
        lumen = np.zeros((160, 200), dtype=np.uint8)
        cv2.ellipse(lumen, (42, 80), (40, 28), 0, 0, 360, 1, -1)
        feat = compute_direction_growth_features(
            lesion,
            lumen_bbox={"x1": 5, "y1": 35, "x2": 70, "y2": 125},
            lumen_mask=lumen,
        )
        self.assertEqual(feat["direction_source"], "lumen_mask_centroid")
        self.assertIn("lumen_mask_geometry", feat["quality_flags"])
        self.assertGreater(feat["contact_arc_ratio"], 0.0)


class TestWallGate(unittest.TestCase):
    def test_proxy_does_not_unlock(self):
        lesion = _ellipse_mask()
        wall = compute_wall_continuity_features(
            lesion_mask=lesion,
            lumen_bbox={"x1": 10, "y1": 40, "x2": 70, "y2": 120},
        )
        self.assertEqual(wall["evidence_kind"], "proxy")
        gate = assess_structural_gate(
            structural_evidence="proxy",
            structural_stage="cT3",
            in_contact=True,
            wall=wall,
        )
        self.assertFalse(gate["unlock_definite_ct"])
        self.assertEqual(gate["structural_stage"], "cTx")

    def test_explicit_serosa_unlocks(self):
        stage = structural_stage_from_explicit_signs(None, "浆膜连续性中断")
        self.assertEqual(stage, "cT4a")
        gate = assess_structural_gate(
            structural_evidence="explicit",
            structural_stage=stage,
            in_contact=True,
            serosa_text="浆膜连续性中断",
        )
        self.assertTrue(gate["unlock_definite_ct"])
        self.assertEqual(gate["structural_stage"], "cT4a")

    def test_explicit_wall_polygon_path(self):
        lesion = _ellipse_mask()
        # Wall arc to the left of lesion (toward lumen).
        poly = [[40, 50], [90, 45], [95, 115], [40, 120]]
        wall = compute_wall_continuity_features(
            lesion_mask=lesion,
            wall_polygon=poly,
            image_shape=(160, 200),
        )
        self.assertEqual(wall["evidence_kind"], "explicit")
        self.assertEqual(wall["status"], "explicit")


class TestProductScorer(unittest.TestCase):
    def test_clinical_only_soft_score(self):
        pack = build_sign_feature_pack(
            length_cm=5.8,
            thickness_cm=1.8,
            cea_positive=True,
            location="胃窦",
        )
        scored = score_gc_us_signs(pack)
        self.assertEqual(scored["ct_stage"], "cTx")
        self.assertEqual(scored["status"], "uncertain")
        ids = {it["id"] for it in scored["items"]}
        self.assertIn("size_length", ids)
        self.assertIn("size_thickness", ids)
        self.assertIn("marker_cea", ids)
        self.assertIn("wall_layer_not_explicitly_confirmed", scored["uncertainty_reasons"])

    def test_proxy_geometry_does_not_set_definite_ct(self):
        lesion = _outward_bump_mask()
        scored = score_gc_us_signs(
            None,
            lesion_mask=lesion,
            lumen_bbox={"x1": 10, "y1": 40, "x2": 70, "y2": 120},
            length_cm=4.0,
            thickness_cm=1.5,
            structural_evidence="proxy",
            structural_stage="cT3",
        )
        self.assertEqual(scored["ct_stage"], "cTx")
        self.assertFalse(scored["structural_gate"]["unlock_definite_ct"])

    def test_explicit_gate_supported(self):
        scored = score_gc_us_signs(
            None,
            length_cm=4.0,
            thickness_cm=1.5,
            structural_evidence="explicit",
            structural_stage="cT2",
            layer_label="固有肌层",
            in_contact=True,
        )
        self.assertEqual(scored["status"], "supported")
        self.assertEqual(scored["ct_stage"], "cT2")

    def test_multiframe_requires_tracking(self):
        frames = [
            {
                "available": True,
                "status": "proxy",
                "tracked": False,
                "growth_proxy": {"transmural_proxy": 0.6, "continuous_outward_arc_frac": 0.2, "outward_protrusion_ratio": 0.2},
                "continuity": {"longest_arc_frac": 0.2, "high_frac": 0.1},
            },
            {
                "available": True,
                "status": "proxy",
                "tracked": True,
                "growth_proxy": {"transmural_proxy": 0.5, "continuous_outward_arc_frac": 0.22, "outward_protrusion_ratio": 0.18},
                "continuity": {"longest_arc_frac": 0.22, "high_frac": 0.12},
            },
        ]
        agg = aggregate_multiframe_features(frames, require_tracked=True)
        self.assertEqual(agg["n_frames_usable"], 1)
        self.assertEqual(agg["status"], "proxy")


if __name__ == "__main__":
    unittest.main()
