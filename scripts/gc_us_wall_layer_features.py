#!/usr/bin/env python3
"""GC-US wall-layer feature library (literature-grounded proxies).

EUS five-layer model (classic; e.g. Botet/Aibe/Kimmey tradition, Mocellin 2011
meta-analysis; recent reviews PMC12385178):
  L1 hyper interface / mucosa, L2 hypo deep mucosa, L3 hyper submucosa,
  L4 hypo muscularis propria (MP), L5 hyper subserosa–serosa.

Clinical T mapping used as *soft ordinal proxy* (not pixel-wise histology GT):
  T1  ~ layers 1–3 (inner wall)
  T2  ~ layer 4 (MP)
  T3  ~ subserosa (deep outer, border still relatively smooth)
  T4a ~ serosal interruption (outer bright line interrupted)
  T4b ~ adjacent organ (out of scope here)

Transabdominal US often cannot resolve all five layers (project meeting notes).
This module therefore estimates:
  1) relative invasion depth within an estimated wall band (lumen→outer),
  2) echo-profile disruption vs adjacent "healthier" wall,
  3) serosal-side interruption proxy from outer-wall contact.

Do NOT feed raw continuous SDF as a ConvNet channel (P0.2 wall-5ch FAIL).
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from scipy import ndimage

# Soft T-score wall-item scores from design doc §六 (adjacent-organ=6 omitted)
SCORE_MUCOSA_SM = 0
SCORE_MP = 2
SCORE_SUBSEROSA = 4
SCORE_SEROSA = 5


def signed_distance_from_mask(mask_bin: np.ndarray) -> np.ndarray:
    """Positive outside mask, negative inside."""
    dist_out = ndimage.distance_transform_edt(mask_bin == 0)
    dist_in = ndimage.distance_transform_edt(mask_bin > 0)
    return dist_out - dist_in


def lumen_mask_from_box(
    shape_hw: tuple[int, int],
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> np.ndarray:
    h, w = shape_hw
    m = np.zeros((h, w), dtype=np.uint8)
    xa, xb = int(np.clip(min(x1, x2), 0, w - 1)), int(np.clip(max(x1, x2), 0, w - 1))
    ya, yb = int(np.clip(min(y1, y2), 0, h - 1)), int(np.clip(max(y1, y2), 0, h - 1))
    if xb > xa and yb > ya:
        m[ya : yb + 1, xa : xb + 1] = 1
    return m


def _largest_contour(mask_bin: np.ndarray) -> np.ndarray | None:
    cnts, _ = cv2.findContours(mask_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < 20:
        return None
    return c[:, 0, :].astype(np.float64)


def _resample_contour(contour: np.ndarray, n: int = 128) -> np.ndarray:
    closed = np.vstack([contour, contour[:1]])
    seg = np.sqrt(((np.diff(closed, axis=0)) ** 2).sum(axis=1))
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(cum[-1])
    if total < 1e-6:
        return np.repeat(contour[:1], n, axis=0)
    samples = np.linspace(0.0, total, n, endpoint=False)
    xs = np.interp(samples, cum, closed[:, 0])
    ys = np.interp(samples, cum, closed[:, 1])
    return np.stack([xs, ys], axis=1)


def _outward_normals(pts: np.ndarray, lumen_centroid: np.ndarray) -> np.ndarray:
    """Normals pointing away from lumen centroid."""
    tang = np.roll(pts, -1, axis=0) - np.roll(pts, 1, axis=0)
    nrm = np.stack([-tang[:, 1], tang[:, 0]], axis=1)
    nlen = np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-8
    nrm = nrm / nlen
    # flip so that normal points away from lumen center
    mid = pts - lumen_centroid[None, :]
    flip = (nrm * mid).sum(axis=1) < 0
    nrm[flip] *= -1
    return nrm


def _sample_profile(
    gray: np.ndarray,
    origin: np.ndarray,
    normal: np.ndarray,
    t_min: int,
    t_max: int,
) -> np.ndarray:
    h, w = gray.shape
    ts = np.arange(t_min, t_max + 1, dtype=np.float64)
    xs = origin[0] + normal[0] * ts
    ys = origin[1] + normal[1] * ts
    vals = np.zeros_like(ts)
    for i, (x, y) in enumerate(zip(xs, ys)):
        xi, yi = int(round(x)), int(round(y))
        if 0 <= xi < w and 0 <= yi < h:
            vals[i] = float(gray[yi, xi])
        else:
            vals[i] = np.nan
    # fill nan with local median
    if np.isnan(vals).any():
        med = np.nanmedian(vals)
        vals = np.where(np.isnan(vals), med if np.isfinite(med) else 0.0, vals)
    return vals


def _count_transitions(profile: np.ndarray, smooth: int = 5) -> float:
    if profile.size < 8:
        return 0.0
    k = np.ones(smooth, dtype=np.float64) / smooth
    sm = np.convolve(profile, k, mode="same")
    g = np.abs(np.gradient(sm))
    # peaks above adaptive threshold
    thr = float(np.percentile(g, 70))
    peaks = 0
    for i in range(1, len(g) - 1):
        if g[i] >= thr and g[i] >= g[i - 1] and g[i] >= g[i + 1]:
            peaks += 1
    return float(peaks)


def depth_frac_to_wall_score(depth_frac: float) -> float:
    """Map relative depth to design-doc wall scores (0/2/4/5).

    Cutpoints are relative to estimated lumen→outer thickness after the
    P75/P80 wall-thickness estimator. Empirically these track pathologic T
    on unique_pooled (ρ≈0.34 for patient median depth→score).
    """
    d = float(depth_frac)
    if d < 0.55:
        return float(SCORE_MUCOSA_SM)
    if d < 0.70:
        return float(SCORE_MP)
    if d < 0.85:
        return float(SCORE_SUBSEROSA)
    return float(SCORE_SEROSA)


def compute_wall_layer_features(
    image_bgr: np.ndarray | None,
    lesion_mask: np.ndarray,
    lumen_mask: np.ndarray,
    outer_wall_mask: np.ndarray | None = None,
) -> dict[str, Any]:
    empty = {
        "wall_valid": 0.0,
        "wall_thick_px_p50": 0.0,
        "wall_depth_frac_p50": 0.0,
        "wall_depth_frac_p90": 0.0,
        "wall_depth_frac_max": 0.0,
        "wall_layer_score_soft": 0.0,
        "wall_mp_band_frac": 0.0,
        "wall_outer_band_frac": 0.0,
        "wall_serosa_interrupt": 0.0,
        "wall_echo_transitions_lesion": 0.0,
        "wall_echo_transitions_healthy": 0.0,
        "wall_layer_disruption": 0.0,
        "wall_contact_arc_ratio": 0.0,
        "wall_has_outer_mask": 0.0,
    }
    if lesion_mask is None or lumen_mask is None:
        return empty
    lesion = (lesion_mask > 127).astype(np.uint8) if lesion_mask.dtype != np.uint8 or lesion_mask.max() > 1 else (lesion_mask > 0).astype(np.uint8)
    lumen = (lumen_mask > 127).astype(np.uint8) if lumen_mask.dtype != np.uint8 or lumen_mask.max() > 1 else (lumen_mask > 0).astype(np.uint8)
    if lesion.shape != lumen.shape:
        lumen = cv2.resize(lumen, (lesion.shape[1], lesion.shape[0]), interpolation=cv2.INTER_NEAREST)
    if lesion.sum() < 30 or lumen.sum() < 30:
        return empty

    outer = None
    if outer_wall_mask is not None:
        outer = (outer_wall_mask > 127).astype(np.uint8) if outer_wall_mask.max() > 1 else (outer_wall_mask > 0).astype(np.uint8)
        if outer.shape != lesion.shape:
            outer = cv2.resize(outer, (lesion.shape[1], lesion.shape[0]), interpolation=cv2.INTER_NEAREST)

    sdf = signed_distance_from_mask(lumen)
    lesion_d = sdf[lesion > 0]
    if lesion_d.size == 0:
        return empty

    # Estimate wall thickness: median SDF on outer-wall band if available,
    # else percentile of positive SDF near lumen boundary in a control ring.
    if outer is not None and outer.sum() > 50:
        thick_samples = sdf[(outer > 0) & (sdf > 0)]
        # P75 of outer-wall SDF ≈ lumen→serosa distance (more stable than median)
        wall_thick = float(np.percentile(thick_samples, 75)) if thick_samples.size else 0.0
        has_outer = 1.0
    else:
        # fallback: distance at ~P80 of lumen-adjacent positive SDF shell
        shell = (sdf > 2) & (sdf < 60) & (lesion == 0)
        thick_samples = sdf[shell]
        wall_thick = float(np.percentile(thick_samples, 80)) if thick_samples.size > 50 else 30.0
        has_outer = 0.0
    wall_thick = float(np.clip(wall_thick, 10.0, 140.0))

    depth_frac = np.clip(lesion_d / wall_thick, -1.0, 2.0)
    depth_pos = depth_frac[depth_frac > 0]
    if depth_pos.size == 0:
        d50 = d90 = dmax = 0.0
    else:
        d50 = float(np.median(depth_pos))
        d90 = float(np.percentile(depth_pos, 90))
        dmax = float(depth_pos.max())

    # Band occupancy (literature: MP ~ mid wall; outer ~ subserosa/serosa)
    mp_band = ((depth_frac >= 0.40) & (depth_frac < 0.70) & (lesion_d > 0)).sum()
    outer_band = ((depth_frac >= 0.70) & (lesion_d > 0)).sum()
    n_out = max(int((lesion_d > 0).sum()), 1)
    mp_frac = float(mp_band) / float(n_out)
    outer_frac = float(outer_band) / float(n_out)

    # Serosa interrupt proxy (BMC Cancer 2022: outer bright line interrupted).
    # Prefer fraction of outer-wall band covered by lesion (positive w/ T stage),
    # not lesion∩outer / lesion (shrinks for bulky advanced tumors).
    # depth_frac is 1D over lesion pixels (same length as lesion_d).
    if outer is not None and outer.sum() > 0:
        dil_outer = cv2.dilate(outer, np.ones((5, 5), np.uint8), iterations=1)
        serosa = float((lesion & dil_outer).sum()) / float(max(int(dil_outer.sum()), 1))
    else:
        serosa = float(np.mean(depth_frac >= 1.15)) if depth_frac.size else 0.0

    # Contact arc on lumen boundary
    lumen_edge = cv2.Canny(lumen * 255, 50, 150) > 0
    lesion_dilt = cv2.dilate(lesion, np.ones((7, 7), np.uint8), iterations=1)
    contact = float((lumen_edge & (lesion_dilt > 0)).sum()) / float(max(int(lumen_edge.sum()), 1))

    # Echo profiles along lumen contour normals
    echo_les = echo_hlt = disruption = 0.0
    if image_bgr is not None:
        if image_bgr.ndim == 3:
            gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY).astype(np.float64)
        else:
            gray = image_bgr.astype(np.float64)
        if gray.shape != lesion.shape:
            gray = cv2.resize(gray, (lesion.shape[1], lesion.shape[0]), interpolation=cv2.INTER_AREA)
        cnt = _largest_contour(lumen)
        if cnt is not None:
            pts = _resample_contour(cnt, 96)
            lc = lumen.nonzero()
            centroid = np.array([np.mean(lc[1]), np.mean(lc[0])], dtype=np.float64)
            normals = _outward_normals(pts, centroid)
            # lesion distance for each contour point
            lesion_dt = ndimage.distance_transform_edt(lesion == 0)
            les_profiles = []
            hlt_profiles = []
            for p, n in zip(pts, normals):
                dist_l = float(lesion_dt[int(np.clip(round(p[1]), 0, lesion.shape[0] - 1)), int(np.clip(round(p[0]), 0, lesion.shape[1] - 1))])
                prof = _sample_profile(gray, p, n, t_min=-6, t_max=int(min(50, wall_thick * 1.4)))
                if dist_l <= 10:
                    les_profiles.append(prof)
                elif dist_l >= 25:
                    hlt_profiles.append(prof)
            if les_profiles:
                echo_les = float(np.mean([_count_transitions(p) for p in les_profiles]))
            if hlt_profiles:
                echo_hlt = float(np.mean([_count_transitions(p) for p in hlt_profiles[:40]]))
                ref = np.mean(np.stack(hlt_profiles[:40], axis=0), axis=0)
                if les_profiles:
                    corrs = []
                    for p in les_profiles[:40]:
                        if p.std() < 1e-6 or ref.std() < 1e-6:
                            continue
                        corrs.append(float(np.corrcoef(p, ref)[0, 1]))
                    if corrs:
                        disruption = float(np.clip(1.0 - np.nanmean(corrs), 0.0, 1.0))

    score = depth_frac_to_wall_score(d90)
    # Only bump when both outer-wall coverage and outer-band occupancy are high
    # (loose serosa thresholds alone saturate almost all frames at score 5).
    if serosa >= 0.28 and outer_frac >= 0.15 and score < SCORE_SEROSA:
        score = float(SCORE_SEROSA)

    return {
        "wall_valid": 1.0,
        "wall_thick_px_p50": wall_thick,
        "wall_depth_frac_p50": d50,
        "wall_depth_frac_p90": d90,
        "wall_depth_frac_max": dmax,
        "wall_layer_score_soft": score,
        "wall_mp_band_frac": mp_frac,
        "wall_outer_band_frac": outer_frac,
        "wall_serosa_interrupt": float(serosa),
        "wall_echo_transitions_lesion": echo_les,
        "wall_echo_transitions_healthy": echo_hlt,
        "wall_layer_disruption": disruption,
        "wall_contact_arc_ratio": contact,
        "wall_has_outer_mask": has_outer,
    }


def _ray_extent_and_thick(
    lesion: np.ndarray,
    outer: np.ndarray | None,
    origin: np.ndarray,
    normal: np.ndarray,
    t_max: int,
    fallback_thick: float,
) -> tuple[float, float, float]:
    """Along lumen→serosa ray: lesion extent, local thickness, remain gap.

    ContactGeom-style:
      remain = first gap after leaving lesion (or dist to nearest lesion if no hit)
      thick  = distance to outer mask along ray, else fallback
      extent = max projection of lesion occupancy along ray
    """
    h, w = lesion.shape
    hit_lesion = False
    extent = 0.0
    thick = 0.0
    first_lesion = None
    last_lesion = None
    for t in range(0, t_max + 1):
        x = int(round(origin[0] + normal[0] * t))
        y = int(round(origin[1] + normal[1] * t))
        if not (0 <= x < w and 0 <= y < h):
            break
        if outer is not None and outer[y, x] > 0 and thick <= 0:
            thick = float(t)
        if lesion[y, x] > 0:
            hit_lesion = True
            if first_lesion is None:
                first_lesion = float(t)
            last_lesion = float(t)
            extent = float(t)
    if thick <= 1.0:
        thick = float(fallback_thick)
    # remain: wall channel left beyond deepest lesion along ray
    if hit_lesion and last_lesion is not None:
        remain = max(0.0, thick - last_lesion)
        # If lesion starts away from lumen, occupied wall span is last-first
        if first_lesion is not None and first_lesion > 2:
            extent = max(extent, last_lesion)  # from lumen origin still
    else:
        remain = thick
        extent = 0.0
    return float(extent), float(thick), float(remain)


def compute_wall_axis_features(
    lesion_mask: np.ndarray,
    lumen_mask: np.ndarray,
    outer_wall_mask: np.ndarray | None = None,
    outward_angle_deg: float | None = None,
    n_contour: int = 96,
    sector_half: int = 8,
) -> dict[str, Any]:
    """Wall-layer proxies **along the breakthrough / deepest-contact axis**.

    Aligns with:
      - ContactGeom.penetrationAt / deep_idx (apps/.../contact_geometry.js)
      - EUS/OCEUS staging: deepest disrupted layer on the invasion path
        (BMC Cancer 2022; WJG 2024 OCEUS table)
      - Frontiers 2021 OCEUS: layer ratios measured on wall ROI, not whole mass

    Not histologic L1–L5 GT. Uses pathology T only as ordinal evaluation target.
    """
    empty = {
        "wall_axis_valid": 0.0,
        "wall_axis_depth_frac": 0.0,
        "wall_axis_depth_frac_sector_p90": 0.0,
        "wall_axis_score_soft": 0.0,
        "wall_axis_remain_frac": 0.0,
        "wall_axis_thick_px": 0.0,
        "wall_axis_extent_px": 0.0,
        "wall_axis_overshoot": 0.0,
        "wall_axis_serosa_hit": 0.0,
        "wall_axis_contact_ratio": 0.0,
        "wall_axis_deep_idx_norm": 0.0,
        "wall_axis_angle_deg": 0.0,
        "wall_axis_used_csv_angle": 0.0,
    }
    if lesion_mask is None or lumen_mask is None:
        return empty
    lesion = (lesion_mask > 0).astype(np.uint8)
    lumen = (lumen_mask > 0).astype(np.uint8)
    if lesion.shape != lumen.shape:
        lumen = cv2.resize(lumen, (lesion.shape[1], lesion.shape[0]), interpolation=cv2.INTER_NEAREST)
    if lesion.sum() < 30 or lumen.sum() < 30:
        return empty
    outer = None
    if outer_wall_mask is not None:
        outer = (outer_wall_mask > 0).astype(np.uint8)
        if outer.shape != lesion.shape:
            outer = cv2.resize(outer, (lesion.shape[1], lesion.shape[0]), interpolation=cv2.INTER_NEAREST)

    cnt = _largest_contour(lumen)
    if cnt is None:
        return empty
    pts = _resample_contour(cnt, n_contour)
    lc = lumen.nonzero()
    centroid = np.array([np.mean(lc[1]), np.mean(lc[0])], dtype=np.float64)
    normals = _outward_normals(pts, centroid)

    # Global thickness prior (same estimator family as whole-lesion features)
    sdf = signed_distance_from_mask(lumen)
    if outer is not None and outer.sum() > 50:
        thick_samples = sdf[(outer > 0) & (sdf > 0)]
        fallback_thick = float(np.percentile(thick_samples, 75)) if thick_samples.size else 30.0
    else:
        shell = (sdf > 2) & (sdf < 60) & (lesion == 0)
        thick_samples = sdf[shell]
        fallback_thick = float(np.percentile(thick_samples, 80)) if thick_samples.size > 50 else 30.0
    fallback_thick = float(np.clip(fallback_thick, 10.0, 140.0))
    t_max = int(min(160, fallback_thick * 2.2))

    extents = np.zeros(n_contour, dtype=np.float64)
    thicks = np.zeros(n_contour, dtype=np.float64)
    remains = np.zeros(n_contour, dtype=np.float64)
    ratios = np.zeros(n_contour, dtype=np.float64)
    for i, (p, n) in enumerate(zip(pts, normals)):
        ext, th, rem = _ray_extent_and_thick(lesion, outer, p, n, t_max, fallback_thick)
        extents[i] = ext
        thicks[i] = max(th, 8.0)  # avoid near-zero local thick → absurd ratios
        remains[i] = rem
        ratios[i] = float(np.clip(ext / max(thicks[i], 1e-6), 0.0, 2.5))

    # deep_idx: ContactGeom uses min remain (closest wall→lesion). Here we use
    # max penetration ratio among rays that actually hit the lesion; fallback
    # to max extent.
    hit = extents > 1.0
    if hit.any():
        deep_idx = int(np.argmax(np.where(hit, ratios, -1.0)))
    else:
        deep_idx = int(np.argmin(remains))

    used_csv = 0.0
    if outward_angle_deg is not None and np.isfinite(outward_angle_deg):
        # Center sector on anatomic outward angle (lumen→lesion / breakthrough)
        ang = np.deg2rad(float(outward_angle_deg))
        target = np.array([np.cos(ang), np.sin(ang)], dtype=np.float64)
        dots = normals @ target
        deep_idx = int(np.argmax(dots))
        used_csv = 1.0

    # Sector around breakthrough axis
    idxs = [(deep_idx + k) % n_contour for k in range(-sector_half, sector_half + 1)]
    sec_ratios = ratios[idxs]
    sec_hit = extents[idxs] > 1.0
    if sec_hit.any():
        axis_ratio = float(np.max(sec_ratios[sec_hit]))
        axis_p90 = float(np.percentile(sec_ratios[sec_hit], 90))
    else:
        axis_ratio = float(ratios[deep_idx])
        axis_p90 = axis_ratio

    thick_d = float(thicks[deep_idx])
    ext_d = float(extents[deep_idx])
    rem_d = float(remains[deep_idx])
    overshoot = max(0.0, ext_d - thick_d) / max(thick_d, 1e-6)
    remain_frac = rem_d / max(thick_d, 1e-6)

    # Serosa hit on axis: ray reaches/covers outer while lesion still present
    serosa_hit = 0.0
    if outer is not None and outer.sum() > 0:
        p = pts[deep_idx]
        n = normals[deep_idx]
        for t in range(0, t_max + 1):
            x = int(round(p[0] + n[0] * t))
            y = int(round(p[1] + n[1] * t))
            if not (0 <= x < lesion.shape[1] and 0 <= y < lesion.shape[0]):
                break
            if outer[y, x] > 0 and lesion[y, x] > 0:
                serosa_hit = 1.0
                break
            if outer[y, x] > 0 and ext_d >= t * 0.95:
                serosa_hit = 1.0
                break
    else:
        serosa_hit = 1.0 if axis_ratio >= 0.95 else 0.0

    contact_thr = max(8.0, float(np.min(remains)) * 2.5 + 4.0)
    contact_ratio = float(np.mean(remains <= contact_thr))

    score = depth_frac_to_wall_score(axis_ratio)
    if (serosa_hit >= 0.5 or overshoot >= 0.05) and axis_ratio >= 0.70:
        score = float(SCORE_SEROSA)

    ang_deep = float(np.degrees(np.arctan2(normals[deep_idx, 1], normals[deep_idx, 0])))

    return {
        "wall_axis_valid": 1.0,
        "wall_axis_depth_frac": float(axis_ratio),
        "wall_axis_depth_frac_sector_p90": float(axis_p90),
        "wall_axis_score_soft": float(score),
        "wall_axis_remain_frac": float(np.clip(remain_frac, 0.0, 2.0)),
        "wall_axis_thick_px": thick_d,
        "wall_axis_extent_px": ext_d,
        "wall_axis_overshoot": float(overshoot),
        "wall_axis_serosa_hit": float(serosa_hit),
        "wall_axis_contact_ratio": contact_ratio,
        "wall_axis_deep_idx_norm": float(deep_idx) / float(n_contour),
        "wall_axis_angle_deg": ang_deep,
        "wall_axis_used_csv_angle": used_csv,
        # extras for viz (not aggregated as primary features)
        "_axis_pts": pts,
        "_axis_normals": normals,
        "_axis_deep_idx": deep_idx,
        "_axis_sector_idxs": idxs,
        "_axis_ratios": ratios,
    }


def render_wall_axis_overlay(
    image_bgr: np.ndarray,
    lesion_mask: np.ndarray,
    lumen_mask: np.ndarray,
    outer_wall_mask: np.ndarray | None,
    feats: dict[str, Any],
) -> np.ndarray:
    """Overlay breakthrough-axis ray + sector (magenta) and penetration readout."""
    img = image_bgr.copy()
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    lesion = (lesion_mask > 0).astype(np.uint8)
    lumen = (lumen_mask > 0).astype(np.uint8)
    if lesion.shape[:2] != img.shape[:2]:
        lesion = cv2.resize(lesion, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
        lumen = cv2.resize(lumen, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
    outer = None
    if outer_wall_mask is not None:
        outer = (outer_wall_mask > 0).astype(np.uint8)
        if outer.shape[:2] != img.shape[:2]:
            outer = cv2.resize(outer, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)

    # Recompute geometry for drawing if cache missing
    axis = feats if "_axis_pts" in feats else compute_wall_axis_features(lesion, lumen, outer)
    color = img.astype(np.float32)
    color[lumen > 0] = 0.6 * color[lumen > 0] + 0.4 * np.array([0, 140, 255])
    if outer is not None:
        color[outer > 0] = 0.7 * color[outer > 0] + 0.3 * np.array([255, 180, 80])
    color[lesion > 0] = 0.55 * color[lesion > 0] + 0.45 * np.array([80, 220, 80])
    out = np.clip(color, 0, 255).astype(np.uint8)

    pts = axis.get("_axis_pts")
    normals = axis.get("_axis_normals")
    deep = int(axis.get("_axis_deep_idx", 0))
    sector = axis.get("_axis_sector_idxs") or [deep]
    if pts is not None and normals is not None:
        thick = max(float(axis.get("wall_axis_thick_px", 30.0)), 8.0)
        for i in sector:
            p = pts[i]
            n = normals[i]
            p0 = (int(round(p[0])), int(round(p[1])))
            p1 = (int(round(p[0] + n[0] * thick)), int(round(p[1] + n[1] * thick)))
            cv2.line(out, p0, p1, (180, 80, 255), 1, cv2.LINE_AA)
        p = pts[deep]
        n = normals[deep]
        ext = max(float(axis.get("wall_axis_extent_px", thick)), 4.0)
        p0 = (int(round(p[0])), int(round(p[1])))
        p1 = (int(round(p[0] + n[0] * ext)), int(round(p[1] + n[1] * ext)))
        p2 = (int(round(p[0] + n[0] * thick)), int(round(p[1] + n[1] * thick)))
        cv2.arrowedLine(out, p0, p1, (0, 0, 255), 2, tipLength=0.12)
        cv2.circle(out, p2, 4, (255, 255, 255), -1, cv2.LINE_AA)
    ratio = float(axis.get("wall_axis_depth_frac", 0.0))
    score = int(axis.get("wall_axis_score_soft", 0))
    cv2.putText(
        out,
        f"axis_depth={ratio:.2f}  score={score}",
        (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return out


def render_wall_layer_overlay(
    image_bgr: np.ndarray,
    lesion_mask: np.ndarray,
    lumen_mask: np.ndarray,
    outer_wall_mask: np.ndarray | None,
    feats: dict[str, Any],
) -> np.ndarray:
    """RGB overlay: lumen(orange), outer wall(blue), lesion by depth band."""
    img = image_bgr.copy()
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    lesion = (lesion_mask > 0).astype(np.uint8)
    lumen = (lumen_mask > 0).astype(np.uint8)
    if lesion.shape[:2] != img.shape[:2]:
        lesion = cv2.resize(lesion, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
        lumen = cv2.resize(lumen, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
    sdf = signed_distance_from_mask(lumen)
    thick = max(float(feats.get("wall_thick_px_p50", 25.0)), 8.0)
    depth = np.clip(sdf / thick, 0, 1.5)
    color = img.astype(np.float32)
    # lumen tint
    color[lumen > 0] = 0.55 * color[lumen > 0] + 0.45 * np.array([0, 140, 255])
    if outer_wall_mask is not None:
        outer = (outer_wall_mask > 0).astype(np.uint8)
        if outer.shape[:2] != img.shape[:2]:
            outer = cv2.resize(outer, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
        color[outer > 0] = 0.65 * color[outer > 0] + 0.35 * np.array([255, 180, 80])
    # lesion bands
    m = lesion > 0
    d = depth[m]
    band = np.zeros((m.sum(), 3), dtype=np.float32)
    # inner / MP / outer → green / yellow / red
    band[:] = np.array([80, 220, 80], dtype=np.float32)
    band[d >= 0.40] = np.array([0, 220, 255], dtype=np.float32)
    band[d >= 0.70] = np.array([60, 60, 255], dtype=np.float32)
    color[m] = 0.45 * color[m] + 0.55 * band
    out = np.clip(color, 0, 255).astype(np.uint8)
    score = int(feats.get("wall_layer_score_soft", 0))
    d90 = float(feats.get("wall_depth_frac_p90", 0))
    cv2.putText(
        out,
        f"wall_score={score}  depth_p90={d90:.2f}",
        (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return out


def _nearest_lesion_dists(wall_pts: np.ndarray, lesion: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """ContactGeom wall_dists / wall_dirs / wall_lesion_pts from outer (or lumen) contour."""
    from scipy.spatial import cKDTree

    ys, xs = np.where(lesion > 0)
    n = len(wall_pts)
    if ys.size == 0:
        return np.full(n, 1e6), np.zeros((n, 2)), np.zeros((n, 2))
    les_xy = np.stack([xs.astype(np.float64), ys.astype(np.float64)], axis=1)
    if len(les_xy) > 8000:
        rng = np.random.default_rng(0)
        les_xy = les_xy[rng.choice(len(les_xy), 8000, replace=False)]
    tree = cKDTree(les_xy)
    dists, idxs = tree.query(wall_pts, k=1)
    nearest = les_xy[idxs]
    vec = nearest - wall_pts
    nrm = np.linalg.norm(vec, axis=1, keepdims=True) + 1e-8
    dirs = vec / nrm
    return dists.astype(np.float64), dirs.astype(np.float64), nearest.astype(np.float64)


def _local_wall_thickness_contactgeom(
    wall_dists: np.ndarray,
    contact_idx: set[int],
    i: int,
    half: int = 18,
) -> float:
    """Port of ContactGeom.localWallThickness (far remain P60 / P75)."""
    n = len(wall_dists)
    samples = []
    for k in range(-half, half + 1):
        j = (i + k) % n
        if j in contact_idx:
            continue
        d = float(wall_dists[j])
        if d > 1.5:
            samples.append(d)
    samples.sort()
    if len(samples) >= 3:
        local = samples[int(0.6 * (len(samples) - 1))]
    else:
        far = [float(wall_dists[j]) for j in range(n) if j not in contact_idx and wall_dists[j] > 1]
        far.sort()
        local = far[int(0.75 * (len(far) - 1))] if far else float(max(wall_dists.max(), 12.0))
    remain = max(0.0, float(wall_dists[i]))
    return float(max(local, remain, 4.0))


def _echo_transitions_on_ray(
    gray: np.ndarray,
    origin: np.ndarray,
    direction: np.ndarray,
    length_px: float,
    n_samples: int = 48,
) -> float:
    if length_px < 4:
        return 0.0
    h, w = gray.shape
    ts = np.linspace(0.0, length_px, n_samples)
    vals = []
    for t in ts:
        x = int(round(origin[0] + direction[0] * t))
        y = int(round(origin[1] + direction[1] * t))
        if 0 <= x < w and 0 <= y < h:
            vals.append(float(gray[y, x]))
    if len(vals) < 8:
        return 0.0
    return _count_transitions(np.asarray(vals, dtype=np.float64))


def compute_wall_axis_features_v2(
    lesion_mask: np.ndarray,
    lumen_mask: np.ndarray,
    outer_wall_mask: np.ndarray | None = None,
    image_bgr: np.ndarray | None = None,
    n_contour: int = 96,
) -> dict[str, Any]:
    """ContactGeom-faithful penetration via **synthetic serosa** points.

    Phase-0 `anatomic_outer_wall` is a lesion-adjacent half-ring, not a true
    serosa polyline — using its contour makes remain≈0 and pen saturate.
    Instead:
      1) lumen contour + outward normals
      2) local/global wall thickness from healthy shell / outer SDF
      3) synthetic serosa = lumen_pt + n̂ · thick
      4) remain = distance(serosa → lesion); pen = (thick − remain) / thick
    Matches ContactGeom orange-wall remain semantics without needing drawn walls.
    """
    empty = {
        "wall_v2_valid": 0.0,
        "wall_v2_pen_ratio": 0.0,
        "wall_v2_pen_ratio_sector": 0.0,
        "wall_v2_score_soft": 0.0,
        "wall_v2_remain_px": 0.0,
        "wall_v2_thick_px": 0.0,
        "wall_v2_overshoot": 0.0,
        "wall_v2_contact_ratio": 0.0,
        "wall_v2_min_remain_px": 0.0,
        "wall_v2_echo_trans_deep": 0.0,
        "wall_v2_echo_trans_healthy": 0.0,
        "wall_v2_echo_loss": 0.0,
        "wall_v2_serosa_proxy": 0.0,
        "wall_v2_composite": 0.0,
        "wall_v2_used_outer": 0.0,
    }
    if lesion_mask is None or lumen_mask is None:
        return empty
    lesion = (lesion_mask > 0).astype(np.uint8)
    lumen = (lumen_mask > 0).astype(np.uint8)
    if lesion.shape != lumen.shape:
        lumen = cv2.resize(lumen, (lesion.shape[1], lesion.shape[0]), interpolation=cv2.INTER_NEAREST)
    if lesion.sum() < 30 or lumen.sum() < 30:
        return empty

    outer = None
    used_outer = 0.0
    if outer_wall_mask is not None:
        outer = (outer_wall_mask > 0).astype(np.uint8)
        if outer.shape != lesion.shape:
            outer = cv2.resize(outer, (lesion.shape[1], lesion.shape[0]), interpolation=cv2.INTER_NEAREST)
        if outer.sum() > 50:
            used_outer = 1.0

    cnt = _largest_contour(lumen)
    if cnt is None:
        return empty
    lumen_pts = _resample_contour(cnt, n_contour)
    lc = lumen.nonzero()
    centroid = np.array([np.mean(lc[1]), np.mean(lc[0])], dtype=np.float64)
    normals = _outward_normals(lumen_pts, centroid)  # lumen → serosa

    sdf = signed_distance_from_mask(lumen)
    if used_outer > 0.5:
        thick_samples = sdf[(outer > 0) & (sdf > 0)]
        thick_global = float(np.percentile(thick_samples, 75)) if thick_samples.size else 30.0
    else:
        shell = (sdf > 2) & (sdf < 60) & (lesion == 0)
        thick_samples = sdf[shell]
        thick_global = float(np.percentile(thick_samples, 80)) if thick_samples.size > 50 else 30.0
    thick_global = float(np.clip(thick_global, 12.0, 120.0))

    # Per-ray thickness: distance lumen→outer along normal, else global
    thicks = np.full(n_contour, thick_global, dtype=np.float64)
    h, w = lesion.shape
    for i, (p, n) in enumerate(zip(lumen_pts, normals)):
        if used_outer < 0.5:
            continue
        hit = 0.0
        for t in range(4, int(thick_global * 1.8) + 1):
            x = int(round(p[0] + n[0] * t))
            y = int(round(p[1] + n[1] * t))
            if not (0 <= x < w and 0 <= y < h):
                break
            if outer[y, x] > 0:
                hit = float(t)
                break
        if hit >= 8.0:
            thicks[i] = hit

    # Synthetic serosa points + inward dirs (serosa → lesion / lumen)
    serosa_pts = lumen_pts + normals * thicks[:, None]
    dirs_in = -normals
    dists, _, _ = _nearest_lesion_dists(serosa_pts, lesion)
    # Also clamp remain by sampling along inward normal (more stable than NN)
    remains = dists.copy()
    for i, (p, d, th) in enumerate(zip(serosa_pts, dirs_in, thicks)):
        rem_ray = th
        for t in range(0, int(th) + 3):
            x = int(round(p[0] + d[0] * t))
            y = int(round(p[1] + d[1] * t))
            if not (0 <= x < w and 0 <= y < h):
                break
            if lesion[y, x] > 0:
                rem_ray = float(t)
                break
        remains[i] = min(float(dists[i]), rem_ray)

    thr = max(6.0, float(np.min(remains)) * 2.5 + 4.0)
    contact_idx = {i for i, d in enumerate(remains) if d <= thr}
    deep = int(np.argmin(remains))
    contact_ratio = float(len(contact_idx) / n_contour)

    # Local thick from far remains (ContactGeom) — these ≈ intact wall thickness
    thick = _local_wall_thickness_contactgeom(remains, contact_idx, deep)
    # Blend with ray thick at deep
    thick = float(0.5 * thick + 0.5 * thicks[deep])
    thick = float(np.clip(max(thick, remains[deep], 8.0), 8.0, 140.0))

    remain = max(0.0, float(remains[deep]))
    extent = max(0.0, thick - remain)
    # Mild overshoot only if lesion sits beyond serosa point along outward normal
    overshoot = 0.0
    p_s = serosa_pts[deep]
    n_out = normals[deep]
    ys, xs = np.where(lesion > 0)
    if ys.size:
        step = max(1, ys.size // 2500)
        projs = (xs[::step].astype(np.float64) - p_s[0]) * n_out[0] + (
            ys[::step].astype(np.float64) - p_s[1]
        ) * n_out[1]
        beyond = float(max(0.0, projs.max()))
        if beyond > 1.0:
            overshoot = beyond / max(thick, 1e-6)
            extent = max(extent, thick + beyond)
    pen = float(np.clip(extent / max(thick, 1e-6), 0.0, 1.8))

    sector = [(deep + k) % n_contour for k in range(-8, 9)]
    sec_pens = []
    for i in sector:
        th_i = float(np.clip(max(_local_wall_thickness_contactgeom(remains, contact_idx, i), thicks[i], 8.0), 8, 140))
        rem_i = max(0.0, float(remains[i]))
        sec_pens.append(float(np.clip((th_i - rem_i) / max(th_i, 1e-6), 0.0, 1.8)))
    pen_sector = float(np.percentile(sec_pens, 90)) if sec_pens else pen

    serosa_proxy = float(
        np.clip(
            0.50 * (1.0 - np.clip(remain / max(thick, 1e-6), 0, 1))
            + 0.30 * min(overshoot, 1.0)
            + 0.20 * min(pen, 1.0),
            0,
            1,
        )
    )

    echo_deep = echo_hlt = echo_loss = 0.0
    if image_bgr is not None:
        if image_bgr.ndim == 3:
            gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY).astype(np.float64)
        else:
            gray = image_bgr.astype(np.float64)
        if gray.shape != lesion.shape:
            gray = cv2.resize(gray, (lesion.shape[1], lesion.shape[0]), interpolation=cv2.INTER_AREA)
        # Sample along serosa → lumen (inward) through wall channel
        echo_deep = _echo_transitions_on_ray(gray, serosa_pts[deep], dirs_in[deep], max(remain, thick * 0.6), 56)
        non_c = [i for i in range(n_contour) if i not in contact_idx]
        if non_c:
            healthy_i = max(non_c, key=lambda i: float(remains[i]))
            echo_hlt = _echo_transitions_on_ray(
                gray, serosa_pts[healthy_i], dirs_in[healthy_i], max(float(remains[healthy_i]), thick * 0.6), 56
            )
            if echo_hlt > 0.5:
                echo_loss = float(np.clip(1.0 - echo_deep / echo_hlt, 0.0, 1.0))

    # Soft score from remain fraction (more stable than pen, which often >0.85)
    occ = float(np.clip(1.0 - remain / max(thick, 1e-6), 0.0, 1.5))
    if occ < 0.45:
        score = float(SCORE_MUCOSA_SM)
    elif occ < 0.70:
        score = float(SCORE_MP)
    elif occ < 0.90:
        score = float(SCORE_SUBSEROSA)
    else:
        score = float(SCORE_SEROSA)
    if (remain <= 4.0 and occ >= 0.85) or overshoot >= 0.10:
        score = float(SCORE_SEROSA)

    composite = float(
        np.clip(0.45 * min(pen, 1.2) / 1.2 + 0.35 * serosa_proxy + 0.20 * echo_loss, 0, 1)
    )

    return {
        "wall_v2_valid": 1.0,
        "wall_v2_pen_ratio": pen,
        "wall_v2_pen_ratio_sector": pen_sector,
        "wall_v2_score_soft": float(score),
        "wall_v2_remain_px": remain,
        "wall_v2_thick_px": float(thick),
        "wall_v2_overshoot": float(np.clip(overshoot, 0, 2)),
        "wall_v2_contact_ratio": contact_ratio,
        "wall_v2_min_remain_px": float(np.min(remains)),
        "wall_v2_echo_trans_deep": float(echo_deep),
        "wall_v2_echo_trans_healthy": float(echo_hlt),
        "wall_v2_echo_loss": float(echo_loss),
        "wall_v2_serosa_proxy": serosa_proxy,
        "wall_v2_composite": composite,
        "wall_v2_used_outer": used_outer,
        "_v2_pts": serosa_pts,
        "_v2_dirs": dirs_in,
        "_v2_deep": deep,
        "_v2_dists": remains,
        "_v2_wall_src": "synthetic_serosa",
    }


def render_wall_axis_v2_overlay(
    image_bgr: np.ndarray,
    lesion_mask: np.ndarray,
    lumen_mask: np.ndarray,
    outer_wall_mask: np.ndarray | None,
    feats: dict[str, Any],
) -> np.ndarray:
    """Overlay ContactGeom-style remain arrow on outer/lumen wall."""
    img = image_bgr.copy()
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    lesion = (lesion_mask > 0).astype(np.uint8)
    lumen = (lumen_mask > 0).astype(np.uint8)
    if lesion.shape[:2] != img.shape[:2]:
        lesion = cv2.resize(lesion, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
        lumen = cv2.resize(lumen, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
    outer = None
    if outer_wall_mask is not None:
        outer = (outer_wall_mask > 0).astype(np.uint8)
        if outer.shape[:2] != img.shape[:2]:
            outer = cv2.resize(outer, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
    axis = feats if "_v2_pts" in feats else compute_wall_axis_features_v2(lesion, lumen, outer, image_bgr)
    color = img.astype(np.float32)
    color[lumen > 0] = 0.65 * color[lumen > 0] + 0.35 * np.array([0, 140, 255])
    if outer is not None:
        color[outer > 0] = 0.55 * color[outer > 0] + 0.45 * np.array([40, 160, 255])
    color[lesion > 0] = 0.55 * color[lesion > 0] + 0.45 * np.array([80, 220, 80])
    out = np.clip(color, 0, 255).astype(np.uint8)
    pts = axis.get("_v2_pts")
    dirs = axis.get("_v2_dirs")
    deep = int(axis.get("_v2_deep", 0))
    if pts is not None and dirs is not None:
        remain = float(axis.get("wall_v2_remain_px", 10))
        thick = float(axis.get("wall_v2_thick_px", 20))
        p0 = (int(round(pts[deep, 0])), int(round(pts[deep, 1])))
        p1 = (
            int(round(pts[deep, 0] + dirs[deep, 0] * remain)),
            int(round(pts[deep, 1] + dirs[deep, 1] * remain)),
        )
        p2 = (
            int(round(pts[deep, 0] + dirs[deep, 0] * thick)),
            int(round(pts[deep, 1] + dirs[deep, 1] * thick)),
        )
        cv2.arrowedLine(out, p0, p1, (0, 0, 255), 2, tipLength=0.15)
        cv2.circle(out, p2, 4, (255, 255, 255), -1)
        cv2.circle(out, p0, 5, (0, 165, 255), -1)
    pen = float(axis.get("wall_v2_pen_ratio", 0))
    score = int(axis.get("wall_v2_score_soft", 0))
    cv2.putText(
        out,
        f"v2_pen={pen:.2f} score={score} rem={float(axis.get('wall_v2_remain_px', 0)):.0f}px",
        (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return out
