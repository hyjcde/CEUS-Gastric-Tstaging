"""Unit checks for explicit wall-layer → cT mapping."""

from pipeline.agent.signs.wall_gate import assess_structural_gate, structural_stage_from_explicit_signs


def test_l3_maps_to_ct1_not_ct2():
    assert structural_stage_from_explicit_signs("L3") == "cT1"


def test_l4_maps_to_ct2():
    assert structural_stage_from_explicit_signs("L4") == "cT2"


def test_l1_l2_map_to_ct1():
    assert structural_stage_from_explicit_signs("L1") == "cT1"
    assert structural_stage_from_explicit_signs("L2") == "cT1"


def test_l5_without_disruption_stays_unresolved():
    assert structural_stage_from_explicit_signs("L5") is None
    assert structural_stage_from_explicit_signs("浆膜") is None


def test_proxy_cannot_unlock_definite_ct():
    gate = assess_structural_gate(
        structural_evidence="proxy",
        structural_stage="cT3",
        in_contact=True,
        layer_label="L4",
    )
    assert gate["unlock_definite_ct"] is False
    assert gate["structural_stage"] == "cTx"


def test_explicit_l4_can_unlock_ct2():
    gate = assess_structural_gate(
        structural_evidence="explicit",
        structural_stage=None,
        in_contact=True,
        layer_label="L4",
        wall={"evidence_kind": "explicit", "status": "explicit"},
    )
    assert gate["unlock_definite_ct"] is True
    assert gate["structural_stage"] == "cT2"
