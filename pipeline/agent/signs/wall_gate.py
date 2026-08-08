"""Wall continuity evidence and explicit structural staging gate.

Only explicit doctor wall annotations / trusted wall masks unlock definite cT.
YOLO lumen bbox + SDF remains ``wall_proxy`` and must not map to cT1–cT4b.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .schema import FeatureField


def _as_bin(mask: Optional[np.ndarray]) -> Optional[np.ndarray]:
    if mask is None:
        return None
    m = np.asarray(mask)
    if m.dtype != np.uint8:
        m = m.astype(np.uint8)
    if m.max() > 1:
        m = (m > 127).astype(np.uint8)
    return m


def _poly_to_mask(poly: Sequence[Sequence[float]], h: int, w: int) -> Optional[np.ndarray]:
    if poly is None or len(poly) < 3:
        return None
    pts = np.asarray(poly, dtype=np.float32)
    if pts.ndim != 2 or pts.shape[1] != 2:
        return None
    canvas = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(canvas, [np.round(pts).astype(np.int32)], 1)
    return canvas


def compute_wall_continuity_features(
    *,
    lesion_mask: Optional[np.ndarray] = None,
    wall_mask: Optional[np.ndarray] = None,
    wall_polygon: Optional[Sequence[Sequence[float]]] = None,
    wall_points: Optional[Sequence[Sequence[float]]] = None,
    layer_labels_along_arc: Optional[Sequence[Any]] = None,
    serosa_clear_flags: Optional[Sequence[bool]] = None,
    fat_interface_clarity: Optional[Sequence[float]] = None,
    image_shape: Optional[Tuple[int, int]] = None,
    lumen_bbox: Optional[Dict[str, Any]] = None,
    wall_proxy_features: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute wall continuity metrics with explicit vs proxy provenance."""
    result: Dict[str, Any] = {
        "available": False,
        "evidence_kind": "missing",
        "status": "missing",
        "layer_visibility_rate": None,
        "longest_interrupt_frac": None,
        "serosa_interrupt_frac": None,
        "continuous_interrupt_length": None,
        "outer_fat_clarity_mean": None,
        "contact_arc_samples": 0,
        "quality_flags": [],
        "proxy": {},
        "notes": [],
    }

    lesion = _as_bin(lesion_mask)
    if image_shape is None and lesion is not None:
        image_shape = lesion.shape[:2]
    h, w = (image_shape or (0, 0))[0], (image_shape or (0, 0))[1]

    explicit_mask = _as_bin(wall_mask)
    if explicit_mask is None and wall_polygon is not None and h > 0 and w > 0:
        explicit_mask = _poly_to_mask(wall_polygon, h, w)
    if explicit_mask is None and wall_points is not None and h > 0 and w > 0:
        explicit_mask = _poly_to_mask(wall_points, h, w)

    if explicit_mask is not None and lesion is not None:
        # Lesion-facing wall arc: wall pixels near dilated lesion.
        lesion_d = cv2.dilate(lesion, np.ones((9, 9), np.uint8), iterations=1)
        facing = (explicit_mask > 0) & (lesion_d > 0)
        n_face = int(facing.sum())
        result["contact_arc_samples"] = n_face
        if n_face < 20:
            result["quality_flags"].append("lesion_facing_wall_arc_too_short")
            result["evidence_kind"] = "explicit_weak"
            result["status"] = "not_assessable"
            result["notes"].append("显式胃壁弧过短，不进入确定 cT")
            return result

        # If ordered layer labels are provided, use them; else derive continuity from mask gaps.
        if layer_labels_along_arc is not None and len(layer_labels_along_arc) > 0:
            labels = [str(x).strip() if x is not None else "" for x in layer_labels_along_arc]
            visible = np.asarray([bool(x) and x.lower() not in {"", "na", "unknown", "不可辨"} for x in labels])
            interrupt = ~visible
            result["layer_visibility_rate"] = float(visible.mean())
            result["longest_interrupt_frac"] = _longest_true_frac(interrupt)
            result["continuous_interrupt_length"] = float(_longest_true_run(interrupt))
        else:
            # Mask-based interrupt proxy along facing arc boundary.
            wall_edge = cv2.Canny(explicit_mask * 255, 50, 150) > 0
            facing_edge = wall_edge & (lesion_d > 0)
            # Sample edge points and look for gaps via morphological opening residual.
            opened = cv2.morphologyEx(explicit_mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
            gaps = (explicit_mask > 0) & (opened == 0)
            gap_on_arc = gaps & facing
            result["layer_visibility_rate"] = float(1.0 - gap_on_arc.sum() / max(n_face, 1))
            # Approximate interrupt fraction on facing pixels.
            result["longest_interrupt_frac"] = float(gap_on_arc.sum() / max(n_face, 1))
            result["continuous_interrupt_length"] = float(gap_on_arc.sum())
            result["contact_arc_samples"] = int(facing_edge.sum()) or n_face

        if serosa_clear_flags is not None and len(serosa_clear_flags) > 0:
            disrupted = np.asarray([not bool(x) for x in serosa_clear_flags], dtype=bool)
            result["serosa_interrupt_frac"] = float(disrupted.mean())
            result["longest_interrupt_frac"] = max(
                float(result["longest_interrupt_frac"] or 0.0),
                _longest_true_frac(disrupted),
            )
        if fat_interface_clarity is not None and len(fat_interface_clarity) > 0:
            vals = np.asarray([float(x) for x in fat_interface_clarity if x is not None], dtype=np.float64)
            if vals.size:
                result["outer_fat_clarity_mean"] = float(vals.mean())

        result["available"] = True
        result["evidence_kind"] = "explicit"
        result["status"] = "explicit"
        result["notes"].append("显式胃壁/层次证据可用于结构门禁")
        return result

    # Proxy path: lumen bbox SDF style features, never unlocks definite cT.
    proxy = dict(wall_proxy_features or {})
    if lumen_bbox is not None and lesion is not None and not proxy:
        proxy = _proxy_from_lumen_bbox(lesion, lumen_bbox)
    if proxy:
        result["available"] = True
        result["evidence_kind"] = "proxy"
        result["status"] = "proxy"
        result["proxy"] = proxy
        result["layer_visibility_rate"] = None
        result["serosa_interrupt_frac"] = float(proxy.get("serosa_interrupt_proxy", 0.0))
        result["longest_interrupt_frac"] = float(proxy.get("interrupt_proxy", 0.0))
        result["continuous_interrupt_length"] = float(proxy.get("max_outward_depth", 0.0))
        result["outer_fat_clarity_mean"] = None
        result["contact_arc_samples"] = int(proxy.get("contact_arc_px", 0))
        result["notes"].append("wall_proxy_only_not_pathological_layer_truth")
        result["quality_flags"].append("proxy_wall_not_for_definite_ct")
        return result

    result["notes"].append("无胃壁显式证据且无可用代理")
    return result


def grade_wall_structure(wall: Dict[str, Any]) -> FeatureField:
    """Grade wall structure for the card. Proxy grades stay status=proxy."""
    kind = wall.get("evidence_kind") or wall.get("status") or "missing"
    if kind in ("missing",) or wall.get("status") == "missing":
        return FeatureField(
            id="wall_structure",
            label="胃壁结构",
            grade=None,
            grade_max=6,
            status="missing",
            source="missing",
            detail="胃壁结构证据缺失",
        )
    if wall.get("status") == "not_assessable" or kind == "explicit_weak":
        return FeatureField(
            id="wall_structure",
            label="胃壁结构",
            grade=None,
            grade_max=6,
            status="not_assessable",
            source="explicit_weak",
            detail="胃壁弧过短或质量不足，不可评",
            extras={"wall": wall},
        )

    if kind == "explicit":
        vis = wall.get("layer_visibility_rate")
        serosa_i = wall.get("serosa_interrupt_frac") or 0.0
        longest_i = wall.get("longest_interrupt_frac") or 0.0
        fat = wall.get("outer_fat_clarity_mean")
        # Map continuity to soft grades; definite cT still needs structuralStage text.
        if serosa_i >= 0.35 or longest_i >= 0.35:
            grade, detail = 5, "浆膜连续性中断倾向（显式）"
        elif longest_i >= 0.20 or (vis is not None and vis < 0.7):
            grade, detail = 4, "层次中断/浆膜下受累倾向（显式）"
        elif longest_i >= 0.08:
            grade, detail = 2, "肌层受累倾向（显式）"
        else:
            grade, detail = 0, "层次大体连续（显式）"
        if fat is not None and fat < 0.35 and grade < 5:
            grade = max(grade, 4)
            detail += "; 外侧脂肪界面欠清"
        return FeatureField(
            id="wall_structure",
            label="胃壁结构",
            value=detail,
            grade=grade,
            grade_max=6,
            status="explicit",
            source="doctor_or_trusted_wall",
            confidence=0.8,
            detail=detail,
            evidence_refs=["wall.explicit"],
            extras={"wall": wall},
        )

    # proxy
    proxy = wall.get("proxy") or {}
    frac_out = float(proxy.get("fraction_outside_lumen", 0.0))
    depth = float(proxy.get("max_outward_depth", 0.0))
    if frac_out >= 0.5 or depth >= 15:
        grade, detail = 5, "外凸深/突破代理高（仅卡片，不入确定 cT）"
    elif frac_out >= 0.2 or depth >= 8:
        grade, detail = 4, "外凸中等代理（仅卡片）"
    elif frac_out >= 0.08 or depth >= 4:
        grade, detail = 2, "浅外凸代理（仅卡片）"
    else:
        grade, detail = 0, "外凸代理低（仅卡片）"
    return FeatureField(
        id="wall_structure",
        label="胃壁结构",
        value=detail,
        grade=grade,
        grade_max=6,
        status="proxy",
        source="lumen_bbox_sdf_proxy",
        confidence=0.35,
        detail=detail,
        evidence_refs=["wall.proxy"],
        extras={"wall": wall},
    )


def assess_structural_gate(
    *,
    structural_evidence: str = "missing",
    structural_stage: Optional[str] = None,
    in_contact: Optional[bool] = None,
    layer_label: Optional[str] = None,
    serosa_text: Optional[str] = None,
    wall: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Explicit structural evidence gate for definite cT output.

    Returns gate decision used by product scorer / frontend.
    """
    wall = wall or {}
    evidence = (structural_evidence or "missing").lower()
    if evidence not in {"explicit", "proxy", "missing"}:
        evidence = "missing"

    # Upgrade to explicit only when wall pack says explicit AND caller agrees.
    if wall.get("evidence_kind") == "explicit" and evidence == "missing":
        evidence = "explicit"
    if wall.get("evidence_kind") == "proxy" and evidence == "missing":
        evidence = "proxy"

    stage = structural_stage or structural_stage_from_explicit_signs(layer_label, serosa_text)
    reasons: List[str] = []
    if evidence != "explicit":
        reasons.append("wall_layer_not_explicitly_confirmed")
    if in_contact is False:
        reasons.append("lesion_wall_contact_not_reliable")
    if evidence == "explicit" and wall.get("status") == "not_assessable":
        reasons.append("explicit_wall_arc_not_assessable")
    if stage in (None, "", "cTx"):
        reasons.append("structural_stage_unresolved")

    unlock = (
        evidence == "explicit"
        and in_contact is not False
        and stage not in (None, "", "cTx")
        and "explicit_wall_arc_not_assessable" not in reasons
    )
    return {
        "structural_evidence": evidence if evidence != "missing" else (wall.get("evidence_kind") or "missing"),
        "structural_stage": stage if unlock else "cTx",
        "requested_stage": stage,
        "unlock_definite_ct": bool(unlock),
        "in_contact": in_contact,
        "reasons": reasons,
        "note": (
            "显式结构证据确认，允许输出确定 cT"
            if unlock
            else "缺少经确认的胃壁层次/浆膜证据，仅展示软评分，不输出确定 cT"
        ),
    }


def structural_stage_from_explicit_signs(
    layer_label: Optional[str] = None,
    serosa_text: Optional[str] = None,
) -> Optional[str]:
    layer = f"{layer_label or ''} {serosa_text or ''}"
    if not layer.strip():
        return None
    import re

    if re.search(r"邻近器官|器官侵犯|adjacent\s+organ|T4b", layer, re.I):
        return "cT4b"
    if re.search(r"浆膜.*(中断|破坏|受侵)|serosa.*(disrupt|breach|involv)", layer, re.I):
        return "cT4a"
    if re.search(r"浆膜下|subserosa", layer, re.I):
        return "cT3"
    if re.search(r"固有肌层|肌层结构|muscularis|proper\s+muscle", layer, re.I):
        return "cT2"
    if re.search(r"黏膜|粘膜|mucosa|submucosa", layer, re.I):
        return "cT1"
    # Ambiguous L5 / serosa without disruption language → unresolved
    if re.search(r"L5|浆膜|serosa", layer, re.I):
        return None
    # Common 5-layer EUS: L1/L2 mucosa-related, L3 submucosa → cT1; L4 MP → cT2.
    if re.search(r"L4", layer, re.I):
        return "cT2"
    if re.search(r"L3", layer, re.I):
        return "cT1"
    if re.search(r"L2|L1", layer, re.I):
        return "cT1"
    return None


def _proxy_from_lumen_bbox(lesion: np.ndarray, lumen_bbox: Dict[str, Any]) -> Dict[str, float]:
    h, w = lesion.shape[:2]
    try:
        x1, y1, x2, y2 = [int(round(float(lumen_bbox[k]))) for k in ("x1", "y1", "x2", "y2")]
    except (KeyError, TypeError, ValueError):
        return {}
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w - 1, x2), min(h - 1, y2)
    lumen = np.zeros_like(lesion)
    lumen[y1 : y2 + 1, x1 : x2 + 1] = 1
    # Signed distance approx via distance transforms
    from scipy import ndimage

    dist_out = ndimage.distance_transform_edt(lumen == 0)
    dist_in = ndimage.distance_transform_edt(lumen > 0)
    sdf = dist_out - dist_in
    depths = sdf[lesion > 0]
    if depths.size == 0:
        return {
            "fraction_outside_lumen": 0.0,
            "max_outward_depth": 0.0,
            "contact_arc_px": 0.0,
            "interrupt_proxy": 0.0,
            "serosa_interrupt_proxy": 0.0,
        }
    outward = depths[depths > 0]
    frac_out = float((depths > 0).sum()) / float(depths.size)
    max_depth = float(depths.max())
    lumen_edge = cv2.Canny(lumen * 255, 50, 150) > 0
    lesion_d = cv2.dilate(lesion, np.ones((7, 7), np.uint8), iterations=1)
    contact = int((lumen_edge & (lesion_d > 0)).sum())
    interrupt_proxy = min(1.0, frac_out)
    serosa_proxy = min(1.0, 0.5 * frac_out + 0.5 * min(max_depth / 20.0, 1.0))
    return {
        "fraction_outside_lumen": frac_out,
        "max_outward_depth": max_depth,
        "mean_outward_depth": float(outward.mean()) if outward.size else 0.0,
        "contact_arc_px": float(contact),
        "interrupt_proxy": interrupt_proxy,
        "serosa_interrupt_proxy": serosa_proxy,
    }


def _longest_true_run(flags: np.ndarray) -> int:
    f = np.asarray(flags, dtype=bool)
    if f.size == 0:
        return 0
    if f.all():
        return int(f.size)
    if not f.any():
        return 0
    start = int(np.where(~f)[0][0])
    rotated = np.concatenate([f[start:], f[:start]])
    best = cur = 0
    for v in rotated:
        if v:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return int(best)


def _longest_true_frac(flags: np.ndarray) -> float:
    f = np.asarray(flags, dtype=bool)
    if f.size == 0:
        return 0.0
    return float(_longest_true_run(f)) / float(f.size)
