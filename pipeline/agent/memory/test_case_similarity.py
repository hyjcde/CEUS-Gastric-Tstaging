"""Unit tests for medical block-weighted case similarity."""

import numpy as np

from agent.memory.case_similarity import weighted_block_similarity
from agent.memory.multimodal_case_vector import VECTOR_DIM, extract_multimodal_case_vector


def test_wall_block_dominates_t2t3_boundary():
    base_cls = {"probabilities": {"T1": 0.1, "T2": 0.35, "T3": 0.45, "T4+": 0.1}, "uncertainty": 0.4}
    wall_high = {
        "available": True,
        "penetration_risk": "high",
        "wall_features": {
            "max_outward_depth": 60.0,
            "mean_outward_depth": 30.0,
            "fraction_outside_lumen": 0.8,
            "contact_arc_ratio": 0.5,
            "lesion_area_px": 1000.0,
            "lumen_area_px": 5000.0,
            "fraction_inside_lumen": 0.1,
        },
    }
    wall_low = dict(wall_high)
    wall_low["penetration_risk"] = "low"
    wall_low["wall_features"] = dict(wall_high["wall_features"])
    wall_low["wall_features"]["max_outward_depth"] = 5.0
    wall_low["wall_features"]["fraction_outside_lumen"] = 0.1

    q = extract_multimodal_case_vector([base_cls], [], wall_evidence=wall_high).extended
    mem_match = extract_multimodal_case_vector([base_cls], [], wall_evidence=wall_high).extended
    mem_mismatch = extract_multimodal_case_vector([base_cls], [], wall_evidence=wall_low).extended

    sim_match, _ = weighted_block_similarity(q, mem_match, boundary_boost=True)
    sim_mismatch, _ = weighted_block_similarity(q, mem_mismatch, boundary_boost=True)
    assert sim_match > sim_mismatch
    assert 0.0 <= sim_match <= 1.0
    assert q.shape[0] == VECTOR_DIM


if __name__ == "__main__":
    test_wall_block_dominates_t2t3_boundary()
    print("ok")
