#!/usr/bin/env python3
"""Two ordered wall interfaces, tracked right to left.

The result is b1 (bright-to-dark) and b2 (dark-to-bright), not three
pixel classes. Does not unlock cT.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from wall_lesion_aware_cluster import (
    as_xy,
    densify_polyline,
    dilate_mask,
    polygon_centroid,
    rasterize_brush,
    _fill_nan_1d,
    _finite_median_filter,
    _sample_normal_profile,
    _smooth1d,
)

SEARCH_PX = 18
NEAR_SEARCH_PX = 24
DILATE_PX = 5
D_MIN = 3
MIN_EDGE = 5.0
TOP_K = 12
LAM_SMOOTH = 5.0
LAM_THICK = 1.4
SMOOTH_SIGMA = 6.0
HEADING_SIGMA_PX = 8.0
STATION_STEP = 2.0
SIDE_BAND_PX = 5.5
PRIOR_SLACK = 5.5
LAM_MISS = 9.0
PREDICT_PX = 18
WRAP_STEPS = 22
FUSE_GRAY_TOL = 18.0
MIN_VALID_STATIONS = 8
HI_CONF = 0.55
LO_CONF = 0.22
MAX_SLOPE = 1.15
MAX_CURV = 0.12

STATUS_ZH = {
    "visible": "可见",
    "obscured": "影像不清",
    "displaced": "受压绕行",
    "interrupted": "局部中断",
    "fused": "与灶融合",
    "missing": "未检出",
}


@dataclass
class Boundary:
    id: str
    name_zh: str
    solid_hi: list[list[float]] = field(default_factory=list)
    solid_lo: list[list[float]] = field(default_factory=list)
    dashed: list[list[float]] = field(default_factory=list)
    band: list[list[float]] = field(default_factory=list)
    wrap: list[list[float]] = field(default_factory=list)
    stop: list[float] | None = None
    n_mean: float | None = None
    n_detected: int = 0
    status: str = "missing"
    note: str = ""


@dataclass
class RegionReadout:
    id: str
    name_zh: str
    status: str
    status_zh: str
    note: str = ""


@dataclass
class CurveTrack:
    status: str
    dilate_px: int
    cavity_side_source: str
    boundaries: list[Boundary] = field(default_factory=list)
    regions: list[RegionReadout] = field(default_factory=list)
    ribbons: list[dict[str, Any]] = field(default_factory=list)
    pixels: dict[str, Any] = field(default_factory=dict)
    skip_reason: str = ""

    @property
    def layers(self) -> list[RegionReadout]:
        return self.regions


def interface_scores(profile: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Bright-to-dark (inner) and dark-to-bright (outer) scores along one normal."""
    sm = _smooth1d(_fill_nan_1d(profile), 2)
    n = int(len(sm))
    inner = np.full((n,), -1.0e6, dtype=np.float32)
    outer = np.full((n,), -1.0e6, dtype=np.float32)
    half = n // 2
    for i in range(5, n - 5):
        left = float(sm[i - 3:i].mean())
        right = float(sm[i:i + 3].mean())
        # Prefer edges near the heading, not the search-window ends.
        w = max(0.45, 1.0 - 0.035 * abs(i - half))
        inner[i] = (left - right) * w
        outer[i] = (right - left) * w
    return inner, outer


def pick_interfaces(profile: np.ndarray) -> tuple[int | None, int | None]:
    inner, outer = interface_scores(profile)
    ii = _top_idx(inner, MIN_EDGE)
    jj = _top_idx(outer, MIN_EDGE)
    best = None
    for i in ii:
        for j in jj:
            if j < i + D_MIN:
                continue
            score = float(inner[i] + outer[j])
            if best is None or score > best[0]:
                best = (score, i, j)
    if best is not None:
        return int(best[1]), int(best[2])
    b1 = int(np.argmax(inner)) if float(inner.max()) >= MIN_EDGE else None
    b2 = int(np.argmax(outer)) if float(outer.max()) >= MIN_EDGE else None
    if b1 is not None and b2 is not None and b2 < b1 + D_MIN:
        return (b1, None) if float(inner[b1]) >= float(outer[b2]) else (None, b2)
    return b1, b2


def pick_ordered_candidates(profile: np.ndarray) -> dict[str, int | None]:
    """Kept for the old peak/valley unit test. Main path uses pick_interfaces."""
    b1, b2 = pick_interfaces(profile)
    mid = None
    if b1 is not None and b2 is not None:
        mid = int(round(0.5 * (b1 + b2)))
    elif b1 is not None:
        mid = min(len(profile) - 1, b1 + 2)
    elif b2 is not None:
        mid = max(0, b2 - 2)
    return {"shallow": b1, "muscularis": mid, "serosa": b2}


def _top_idx(score: np.ndarray, min_score: float) -> list[int]:
    order = np.argsort(-score)
    hits = [int(i) for i in order.tolist() if float(score[int(i)]) >= min_score][:TOP_K]
    if not hits and float(score[int(order[0])]) > 0:
        hits = [int(order[0])]
    return hits


def _station_valid(
    pts: np.ndarray,
    blocked: np.ndarray,
    fit_side: str,
    lesion_poly: np.ndarray | None = None,
) -> np.ndarray:
    height, width = blocked.shape[:2]
    ok = np.ones((len(pts),), dtype=bool)
    xs = pts[:, 0]
    side = str(fit_side or "all").strip().lower()
    if side == "right" and len(pts):
        cut = float(np.quantile(xs, 0.50))
        if lesion_poly is not None and len(lesion_poly) >= 3:
            lesion_right = float(np.percentile(lesion_poly[:, 0], 88))
            if float(xs.min()) < lesion_right < float(xs.max()):
                cut = lesion_right + 2.0
        cand = xs >= cut
        if int(cand.sum()) >= MIN_VALID_STATIONS:
            ok &= cand
        else:
            ok &= xs >= float(np.quantile(xs, 0.55))
    elif side == "left" and len(pts):
        ok &= xs <= float(np.quantile(xs, 0.45))
    for i, (x, y) in enumerate(pts.tolist()):
        xi, yi = int(round(x)), int(round(y))
        if xi < 0 or yi < 0 or xi >= width or yi >= height or blocked[yi, xi] > 0:
            ok[i] = False
    return ok


def _xy(pts: np.ndarray, normals: np.ndarray, offsets: np.ndarray) -> np.ndarray:
    out = np.full((len(pts), 2), np.nan, dtype=np.float32)
    ok = np.isfinite(offsets)
    out[ok] = pts[ok] + normals[ok] * offsets[ok, None]
    return out


def _finite(xy: np.ndarray) -> np.ndarray:
    return xy[np.isfinite(xy).all(axis=1)]


def _viterbi_two_edges(
    profiles: list[np.ndarray],
    half: int,
    near: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Right-to-left joint path. Index 0 is the rightmost valid station."""
    t_count = len(profiles)
    n1 = np.full((t_count,), np.nan, dtype=np.float32)
    n2 = np.full((t_count,), np.nan, dtype=np.float32)
    c1 = np.zeros((t_count,), dtype=np.float32)
    c2 = np.zeros((t_count,), dtype=np.float32)
    if t_count == 0:
        return n1, n2, c1, c2

    cands: list[list[tuple[int, int]]] = []
    inn_all = []
    out_all = []
    for t, profile in enumerate(profiles):
        floor = 3.5 if near[t] else MIN_EDGE
        inn, out = interface_scores(profile)
        inn_all.append(inn)
        out_all.append(out)
        ii = _top_idx(inn, floor) + [-1]
        jj = _top_idx(out, floor) + [-1]
        pairs = []
        for i in ii:
            for j in jj:
                if i >= 0 and j >= 0 and j < i + D_MIN:
                    continue
                pairs.append((i, j))
        cands.append(pairs or [(-1, -1)])

    prev: list[list[int]] = []
    best: list[np.ndarray] = []
    for t in range(t_count):
        states = cands[t]
        cost = np.full((len(states),), 1.0e9, dtype=np.float32)
        back = np.full((len(states),), -1, dtype=np.int32)
        inn, out = inn_all[t], out_all[t]
        for k, (i, j) in enumerate(states):
            img = 0.0
            miss = 0.0
            if i >= 0:
                img -= float(inn[i])
            else:
                miss += LAM_MISS if float(inn.max()) >= MIN_EDGE else 0.4
            if j >= 0:
                img -= float(out[j])
            else:
                miss += LAM_MISS if float(out.max()) >= MIN_EDGE else 0.4
            if t == 0:
                cost[k] = img + miss
                continue
            for p, (pi, pj) in enumerate(cands[t - 1]):
                sm = 0.0
                th = 0.0
                if i >= 0 and pi >= 0:
                    sm += (i - pi) ** 2
                if j >= 0 and pj >= 0:
                    sm += (j - pj) ** 2
                if i >= 0 and j >= 0 and pi >= 0 and pj >= 0:
                    th += ((j - i) - (pj - pi)) ** 2
                tot = float(best[t - 1][p] + img + miss + LAM_SMOOTH * sm + LAM_THICK * th)
                if tot < cost[k]:
                    cost[k] = tot
                    back[k] = p
        best.append(cost)
        prev.append(back)

    k = int(np.argmin(best[-1]))
    path = [(-1, -1)] * t_count
    for t in range(t_count - 1, -1, -1):
        path[t] = cands[t][k]
        k = int(prev[t][k]) if t > 0 and prev[t][k] >= 0 else 0
    for t, (i, j) in enumerate(path):
        inn, out = inn_all[t], out_all[t]
        peak_i = max(float(inn.max()), 1.0)
        peak_j = max(float(out.max()), 1.0)
        if i >= 0:
            n1[t] = float(i - half)
            c1[t] = float(np.clip(inn[i] / peak_i, 0.0, 1.0))
        if j >= 0:
            n2[t] = float(j - half)
            c2[t] = float(np.clip(out[j] / peak_j, 0.0, 1.0))
    return n1, n2, c1, c2


def _arc_length(pts: np.ndarray) -> np.ndarray:
    if len(pts) == 0:
        return np.zeros((0,), dtype=np.float32)
    step = np.sqrt(((pts[1:] - pts[:-1]) ** 2).sum(axis=1))
    return np.concatenate([[0.0], np.cumsum(step)]).astype(np.float32)


def _resample_polyline(pts: np.ndarray, step: float = STATION_STEP) -> np.ndarray:
    pts = np.asarray(pts, dtype=np.float32)
    if len(pts) < 2:
        return pts.copy()
    s = _arc_length(pts)
    if float(s[-1]) < step:
        return pts.copy()
    q = np.arange(0.0, float(s[-1]) + 0.5 * step, step, dtype=np.float32)
    return np.stack([np.interp(q, s, pts[:, 0]), np.interp(q, s, pts[:, 1])], axis=1).astype(np.float32)


def _smooth_heading(pts: np.ndarray, sigma_px: float = HEADING_SIGMA_PX) -> np.ndarray:
    """Lightly round the doctor stroke without walking off the wall pixels."""
    raw = _resample_polyline(densify_polyline(as_xy(pts), 2.0), 2.0)
    if len(raw) < 6:
        return raw
    sig = max(2.2, float(sigma_px) / 2.0)
    xs = _gauss1d(raw[:, 0], sig)
    ys = _gauss1d(raw[:, 1], sig)
    return _resample_polyline(np.stack([xs, ys], axis=1), STATION_STEP)


def _smooth_wall_stations(
    polyline: np.ndarray,
    lumen_center: np.ndarray | None,
    lesion_center: np.ndarray | None,
    deepest: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Stations and one consistent outward normal from the smoothed heading."""
    pts = _smooth_heading(polyline)
    if len(pts) < 2:
        empty = np.zeros((0, 2), dtype=np.float32)
        return empty, empty
    tangents = np.zeros_like(pts)
    if len(pts) >= 3:
        tangents[1:-1] = pts[2:] - pts[:-2]
        tangents[0] = pts[1] - pts[0]
        tangents[-1] = pts[-1] - pts[-2]
    else:
        tangents[0] = pts[-1] - pts[0]
        tangents[-1] = tangents[0]
    tan_n = np.maximum(np.hypot(tangents[:, 0], tangents[:, 1]), 1e-6)
    tangent = tangents / tan_n[:, None]
    normals = np.stack([-tangent[:, 1], tangent[:, 0]], axis=1)
    if lumen_center is not None:
        hint = pts - np.asarray(lumen_center, dtype=np.float32).reshape(1, 2)
    elif deepest is not None and lesion_center is not None:
        hint = np.broadcast_to(
            (np.asarray(deepest) - np.asarray(lesion_center)).astype(np.float32),
            normals.shape,
        )
    elif lesion_center is not None:
        hint = pts - np.asarray(lesion_center, dtype=np.float32).reshape(1, 2)
    else:
        hint = None
    if hint is not None:
        votes = np.sum(normals * hint, axis=1) < 0
        if int(votes.sum()) > 0.5 * len(votes):
            normals = -normals
    if len(normals) and float(normals[:, 1].mean()) < 0:
        normals = -normals
    return pts.astype(np.float32), normals.astype(np.float32)


def _median_band_priors(profiles: list[np.ndarray], half: int) -> tuple[float, float, float, float, tuple[float, float, float]]:
    """One gray reading for the whole right-hand wall: bright / dark / bright."""
    if not profiles:
        return -2.0, 4.0, -2.0 - SIDE_BAND_PX, 4.0 + SIDE_BAND_PX, (180.0, 50.0, 180.0)
    med = np.nanmedian(np.stack(profiles, axis=0), axis=0)
    sm = _smooth1d(_fill_nan_1d(med), 3)
    b1, b2 = pick_interfaces(sm)
    if b1 is None and b2 is None:
        core = sm[5:-5] if len(sm) > 12 else sm
        valley = int(np.argmin(core)) + (5 if len(sm) > 12 else 0)
        b1 = max(5, valley - 4)
        b2 = min(len(sm) - 6, valley + 4)
    elif b1 is None:
        b1 = max(5, int(b2) - 6)
    elif b2 is None:
        b2 = min(len(sm) - 6, int(b1) + 6)
    if int(b2) < int(b1) + D_MIN:
        b2 = min(len(sm) - 2, int(b1) + max(D_MIN, 6))
    n1 = float(b1 - half)
    n2 = float(b2 - half)
    valley = float(np.min(sm[int(b1): int(b2) + 1])) if int(b2) > int(b1) else float(sm[int(b1)])
    inner_slice = sm[: max(1, int(b1))]
    outer_slice = sm[int(b2): min(len(sm), int(b2) + 10)]
    inner_peak_i = int(np.argmax(inner_slice)) if len(inner_slice) else 0
    outer_peak_i = int(b2) + int(np.argmax(outer_slice)) if len(outer_slice) else int(b2)
    inner_peak = float(sm[inner_peak_i])
    outer_peak = float(sm[min(outer_peak_i, len(sm) - 1)])
    thr_in = valley + 0.40 * max(8.0, inner_peak - valley)
    thr_out = valley + 0.40 * max(8.0, outer_peak - valley)
    lo = inner_peak_i
    for i in range(inner_peak_i, max(-1, inner_peak_i - 4), -1):
        if float(sm[i]) < thr_in:
            break
        lo = i
    hi = outer_peak_i
    for i in range(outer_peak_i, min(len(sm), outer_peak_i + 5)):
        if float(sm[i]) < thr_out:
            break
        hi = i
    muc_lo = min(float(lo - half), n1 - 2.5)
    ser_hi = max(float(hi - half), n2 + 2.5)
    return n1, n2, muc_lo, ser_hi, (inner_peak, valley, outer_peak)


def _pull_to_prior(values: np.ndarray, prior: float, keep: np.ndarray, slack: float = PRIOR_SLACK) -> np.ndarray:
    out = values.astype(np.float32).copy()
    ok = keep & np.isfinite(out)
    out[ok] = np.clip(out[ok], prior - slack, prior + slack)
    missing = keep & ~np.isfinite(out)
    out[missing] = prior
    return out


def _gauss1d(values: np.ndarray, sigma: float) -> np.ndarray:
    if len(values) < 3:
        return values.astype(np.float32)
    rad = max(2, int(np.ceil(3.0 * sigma)))
    x = np.arange(-rad, rad + 1, dtype=np.float32)
    ker = np.exp(-0.5 * (x / max(0.8, sigma)) ** 2)
    ker = ker / ker.sum()
    pad = np.pad(values.astype(np.float32), rad, mode="edge")
    return np.convolve(pad, ker, mode="valid")


def _reject_offset_outliers(values: np.ndarray, keep: np.ndarray, max_dev: float = 6.5) -> np.ndarray:
    out = values.astype(np.float32).copy()
    ok = keep & np.isfinite(out)
    if int(ok.sum()) < 5:
        return out
    med = float(np.median(out[ok]))
    mad = float(np.median(np.abs(out[ok] - med))) + 1.0
    out[ok & (np.abs(out - med) > max(max_dev, 3.5 * mad))] = np.nan
    return out


def _natural_offset(values: np.ndarray, arc: np.ndarray, keep: np.ndarray) -> np.ndarray:
    return _slow_offset(values, arc, keep)


def _slow_offset(values: np.ndarray, arc: np.ndarray, keep: np.ndarray, sigma: float = SMOOTH_SIGMA) -> np.ndarray:
    """Kill single-pixel jumps, but stay on the local gray edge."""
    out = np.full(values.shape, np.nan, dtype=np.float32)
    raw = _reject_offset_outliers(values, keep, max_dev=5.5)
    ok = keep & np.isfinite(raw)
    if int(ok.sum()) < 5:
        return values.astype(np.float32)
    s = arc[ok]
    y = raw[ok].astype(np.float32)
    order = np.argsort(s)
    s = s[order]
    y = y[order]
    win = min(11, (max(5, len(y) // 4) * 2 + 1))
    y = _finite_median_filter(y, win)
    y = _gauss1d(y, max(3.5, float(sigma)))
    out[keep] = np.interp(arc[keep], s, y)
    return out


def _label_corridor_pixels(
    gray: np.ndarray,
    pts: np.ndarray,
    normals: np.ndarray,
    n1: np.ndarray,
    n2: np.ndarray,
    muc_lo: np.ndarray,
    ser_hi: np.ndarray,
    blocked: np.ndarray,
    valid: np.ndarray,
    gray_centers: tuple[float, float, float] | None = None,
) -> dict[str, Any]:
    """Paint the actual corridor pixels that sit between the two gray edges."""
    empty = {
        "xs": np.zeros((0,), dtype=np.int32),
        "ys": np.zeros((0,), dtype=np.int32),
        "labels": np.zeros((0,), dtype=np.int32),
    }
    ok = valid & np.isfinite(n1) & np.isfinite(n2) & np.isfinite(muc_lo) & np.isfinite(ser_hi)
    if int(ok.sum()) < 3:
        return empty
    rad = float(np.nanmax(np.maximum(np.abs(muc_lo[ok]), np.abs(ser_hi[ok])))) + 1.5
    brush = rasterize_brush(gray.shape[:2], pts[ok], max(3.0, rad))
    if blocked is not None:
        brush[blocked > 0] = 0
    ys, xs = np.where(brush > 0)
    if len(xs) == 0:
        return empty
    pix = np.stack([xs.astype(np.float32), ys.astype(np.float32)], axis=1)
    sta = pts[ok]
    # Chunk the distance search so a long heading stays cheap.
    nearest = np.zeros((len(pix),), dtype=np.int32)
    best = np.full((len(pix),), 1.0e18, dtype=np.float32)
    chunk = 80
    for start in range(0, len(sta), chunk):
        block = sta[start:start + chunk]
        d2 = ((pix[:, None, :] - block[None, :, :]) ** 2).sum(axis=2)
        local = d2.argmin(axis=1).astype(np.int32)
        dist = d2[np.arange(len(pix)), local]
        take = dist < best
        best[take] = dist[take]
        nearest[take] = local[take] + start
    idx = np.where(ok)[0][nearest]
    rel = pix - pts[idx]
    nrm = (rel * normals[idx]).sum(axis=1)
    keep = (nrm >= muc_lo[idx]) & (nrm <= ser_hi[idx])
    if int(keep.sum()) < 8:
        return empty
    lab = np.full((int(keep.sum()),), 1, dtype=np.int32)
    n_use = nrm[keep]
    i_use = idx[keep]
    lab[n_use < n1[i_use]] = 0
    lab[n_use >= n2[i_use]] = 2
    xs_k = xs[keep].astype(np.int32)
    ys_k = ys[keep].astype(np.int32)
    if gray_centers is not None and len(xs_k):
        g0, g1, g2 = [float(v) for v in gray_centers]
        g = gray[ys_k, xs_k].astype(np.float32)
        centers = np.array([g0, g1, g2], dtype=np.float32)
        dist = np.abs(g[:, None] - centers[None, :])
        nearest = dist.argmin(axis=1).astype(np.int32)
        own = dist[np.arange(len(lab)), lab]
        stay = (nearest == lab) | ((own - dist.min(axis=1)) < 10.0)
        xs_k, ys_k, lab = xs_k[stay], ys_k[stay], lab[stay]
    return {
        "xs": xs_k,
        "ys": ys_k,
        "labels": lab,
    }


def _dense_from_stations(station_xy: np.ndarray, keep: np.ndarray, step: float = 1.0) -> np.ndarray:
    ok = keep & np.isfinite(station_xy).all(axis=1)
    if int(ok.sum()) < 2:
        return np.zeros((0, 2), dtype=np.float32)
    p = station_xy[ok]
    s = _arc_length(p)
    if float(s[-1]) < 2.0:
        return p.astype(np.float32)
    q = np.arange(0.0, float(s[-1]) + 0.5 * step, step, dtype=np.float32)
    return np.stack([np.interp(q, s, p[:, 0]), np.interp(q, s, p[:, 1])], axis=1).astype(np.float32)


def _ribbon_from_xy(top: np.ndarray, bot: np.ndarray, keep: np.ndarray) -> list[list[float]]:
    ok = keep & np.isfinite(top).all(axis=1) & np.isfinite(bot).all(axis=1)
    if int(ok.sum()) < 3:
        return []
    a = _dense_from_stations(top, ok)
    b = _dense_from_stations(bot, ok)
    if len(a) < 3 or len(b) < 3:
        return []
    return np.vstack([a, b[::-1]]).tolist()


def _dense_curve(pts: np.ndarray, normals: np.ndarray, offsets: np.ndarray, step: float = 1.0) -> np.ndarray:
    ok = np.isfinite(offsets)
    if int(ok.sum()) < 2:
        return np.zeros((0, 2), dtype=np.float32)
    p, nrm, off = pts[ok], normals[ok], offsets[ok]
    s = _arc_length(p)
    if float(s[-1]) < 2.0:
        return p + nrm * off[:, None]
    q = np.arange(0.0, float(s[-1]) + 0.5 * step, step, dtype=np.float32)
    px = np.interp(q, s, p[:, 0])
    py = np.interp(q, s, p[:, 1])
    nx = np.interp(q, s, nrm[:, 0])
    ny = np.interp(q, s, nrm[:, 1])
    nn = np.maximum(np.hypot(nx, ny), 1e-6)
    no = np.interp(q, s, off)
    return np.stack([px + (nx / nn) * no, py + (ny / nn) * no], axis=1).astype(np.float32)


def _ribbon(pts: np.ndarray, normals: np.ndarray, lo: np.ndarray, hi: np.ndarray, keep: np.ndarray) -> list[list[float]]:
    ok = keep & np.isfinite(lo) & np.isfinite(hi) & (hi >= lo + 0.8)
    idx = np.where(ok)[0]
    if len(idx) < 3:
        return []
    top = pts[idx] + normals[idx] * lo[idx, None]
    bot = pts[idx] + normals[idx] * hi[idx, None]
    return np.vstack([top, bot[::-1]]).astype(np.float32).tolist()


def _split_conf(xy: np.ndarray, conf: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    hi = xy.copy()
    lo = xy.copy()
    hi[conf < HI_CONF] = np.nan
    lo[(conf < LO_CONF) | (conf >= HI_CONF)] = np.nan
    return _finite(hi), _finite(lo)


def _local_motion(values: np.ndarray) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if len(finite) < 3:
        return 0.0, 0.0
    tail = finite[-6:]
    d1 = float(np.mean(np.diff(tail)))
    d2 = float(np.mean(np.diff(np.diff(tail)))) if len(tail) >= 4 else 0.0
    d1 = float(np.clip(d1, -MAX_SLOPE, MAX_SLOPE))
    d2 = float(np.clip(d2, -MAX_CURV, MAX_CURV))
    return d1, d2


def _predict_band(
    pts: np.ndarray,
    normals: np.ndarray,
    offsets: np.ndarray,
    blocked: np.ndarray,
    lesion_center: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray, list[float] | None]:
    """Short clipped-curvature forecast with a widening uncertainty band."""
    ok = np.isfinite(offsets)
    if int(ok.sum()) < 3:
        empty = np.zeros((0, 2), dtype=np.float32)
        return empty, empty, None
    hit = np.where(ok)[0]
    if lesion_center is not None:
        last = int(hit[np.argmin(np.linalg.norm(pts[hit] - lesion_center.reshape(1, 2), axis=1))])
    else:
        last = int(hit[np.argmin(pts[hit, 0])])
    direction = -1 if last <= float(hit.mean()) else 1
    start = pts[last] + normals[last] * float(offsets[last])
    along = offsets[hit] if direction > 0 else offsets[hit[::-1]]
    slope, curv = _local_motion(along)
    height, width = blocked.shape[:2]
    dashed = []
    ring = []
    entered = False
    stop = None
    for step in range(1, PREDICT_PX + 1):
        idx = int(np.clip(last + direction * step, 0, len(pts) - 1))
        dn = slope * step + 0.5 * curv * step * step
        nrm = normals[idx]
        center = pts[idx] + nrm * (float(offsets[last]) + dn)
        x, y = int(round(float(center[0]))), int(round(float(center[1])))
        if x < 0 or y < 0 or x >= width or y >= height:
            break
        inside = bool(blocked[y, x] > 0)
        if inside:
            entered = True
        elif entered:
            break
        half_w = 1.4 + 0.32 * step
        dashed.append([float(center[0]), float(center[1])])
        ring.append((center + nrm * half_w).tolist())
        stop = [float(center[0]), float(center[1])]
    if not dashed:
        empty = np.zeros((0, 2), dtype=np.float32)
        return empty, empty, None
    minus_pts = []
    for step in range(len(dashed), 0, -1):
        idx = int(np.clip(last + direction * step, 0, len(pts) - 1))
        nrm = normals[idx]
        center = np.asarray(dashed[step - 1], dtype=np.float32)
        half_w = 1.4 + 0.32 * step
        minus_pts.append((center - nrm * half_w).tolist())
    return (
        np.asarray(dashed, dtype=np.float32),
        np.asarray(ring + minus_pts, dtype=np.float32),
        stop,
    )


def _wrap_outer(
    start: np.ndarray,
    lesion_mask: np.ndarray,
    outer: np.ndarray,
    gray: np.ndarray,
    seed_gray: float | None,
) -> tuple[np.ndarray, bool]:
    contours, _ = cv2.findContours(lesion_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return np.zeros((0, 2), dtype=np.float32), False
    ring = max(contours, key=cv2.contourArea).reshape(-1, 2).astype(np.float32)
    if len(ring) < 8:
        return np.zeros((0, 2), dtype=np.float32), False
    nearest = int(np.argmin(((ring - start.reshape(1, 2)) ** 2).sum(axis=1)))
    nxt = ring[(nearest + 1) % len(ring)]
    prv = ring[(nearest - 1) % len(ring)]
    step = 1 if float(np.dot(nxt - ring[nearest], outer)) >= float(np.dot(prv - ring[nearest], outer)) else -1
    path, grays = [], []
    height, width = gray.shape[:2]
    for k in range(1, WRAP_STEPS + 1):
        q = ring[(nearest + step * k) % len(ring)]
        x, y = int(round(float(q[0]))), int(round(float(q[1])))
        if 0 <= x < width and 0 <= y < height:
            path.append([float(q[0]), float(q[1])])
            grays.append(float(gray[y, x]))
    if len(grays) < 6 or seed_gray is None:
        return np.zeros((0, 2), dtype=np.float32), False
    ok = float(np.mean(grays)) >= float(seed_gray) - 28.0
    return (np.asarray(path, dtype=np.float32) if ok else np.zeros((0, 2), dtype=np.float32)), ok


def _gray_between(gray: np.ndarray, a: np.ndarray, b: np.ndarray) -> float | None:
    if len(a) == 0 or len(b) == 0:
        return None
    n = min(len(a), len(b), 12)
    vals = []
    height, width = gray.shape[:2]
    for p, q in zip(a[-n:], b[-n:]):
        mid = 0.5 * (np.asarray(p) + np.asarray(q))
        x, y = int(round(float(mid[0]))), int(round(float(mid[1])))
        if 0 <= x < width and 0 <= y < height:
            vals.append(float(gray[y, x]))
    return None if not vals else float(np.mean(vals))


def _gray_at(gray: np.ndarray, xy: np.ndarray) -> float | None:
    if len(xy) == 0:
        return None
    height, width = gray.shape[:2]
    vals = []
    for x, y in xy.tolist():
        xi, yi = int(round(x)), int(round(y))
        if 0 <= xi < width and 0 <= yi < height:
            vals.append(float(gray[yi, xi]))
    return None if not vals else float(np.mean(vals))


def _region(name: str, zh: str, status: str, note: str = "") -> RegionReadout:
    return RegionReadout(id=name, name_zh=zh, status=status, status_zh=STATUS_ZH.get(status, status), note=note)


def track_ordered_layers(
    gray: np.ndarray,
    wall: np.ndarray,
    lesion_mask: np.ndarray,
    *,
    lumen_center: np.ndarray | None = None,
    lesion_poly: np.ndarray | None = None,
    dilate_px: int = DILATE_PX,
    search_px: int = SEARCH_PX,
    fit_side: str = "right",
) -> CurveTrack:
    """Track two ordered interfaces from the clear right flank toward the lesion."""
    wall = densify_polyline(as_xy(wall), 3.0)
    lesion = as_xy(lesion_poly) if lesion_poly is not None else np.zeros((0, 2), dtype=np.float32)
    lesion_center = polygon_centroid(lesion)
    deepest = None
    if len(lesion) >= 2 and lesion_center is not None:
        deepest = lesion[int(np.argmax(np.linalg.norm(lesion - lesion_center, axis=1)))]
    blocked = dilate_mask(lesion_mask, int(dilate_px))
    pts, normals = _smooth_wall_stations(wall, lumen_center, lesion_center, deepest)
    cavity = "lumen" if lumen_center is not None else "heuristic"
    if len(pts) < MIN_VALID_STATIONS:
        return CurveTrack(status="insufficient_normal_wall", dilate_px=dilate_px, cavity_side_source=cavity, skip_reason="short_heading")
    valid = _station_valid(pts, blocked, fit_side, lesion)
    if int(valid.sum()) < MIN_VALID_STATIONS:
        valid = _station_valid(pts, blocked, "all", lesion)
    if int(valid.sum()) < MIN_VALID_STATIONS:
        return CurveTrack(status="insufficient_normal_wall", dilate_px=dilate_px, cavity_side_source=cavity, skip_reason="no_flank")

    use = np.where(valid)[0]
    # Rightmost station first, then walk left toward the lesion.
    use = use[np.argsort(-pts[use, 0])]
    near = np.zeros((len(use),), dtype=bool)
    near[int(0.70 * len(use)):] = True
    half = int(search_px)
    profiles = [
        _sample_normal_profile(gray, pts[idx], normals[idx], half, blocked)
        for idx in use.tolist()
    ]
    off1, off2, conf1, conf2 = _viterbi_two_edges(profiles, half, near)
    n1_prior, n2_prior, muc_lo0, ser_hi0, gray_centers = _median_band_priors(profiles, half)

    # Map the right-to-left series back onto heading stations.
    n1 = np.full((len(pts),), np.nan, dtype=np.float32)
    n2 = np.full((len(pts),), np.nan, dtype=np.float32)
    c1 = np.zeros((len(pts),), dtype=np.float32)
    c2 = np.zeros((len(pts),), dtype=np.float32)
    for t, idx in enumerate(use.tolist()):
        n1[idx] = off1[t]
        n2[idx] = off2[t]
        c1[idx] = conf1[t]
        c2[idx] = conf2[t]
        if near[t]:
            c1[idx] *= 0.72
            c2[idx] *= 0.72
    arc = _arc_length(pts)
    # Fill gaps with the gray prior, but do not pin every station to one offset.
    n1 = _pull_to_prior(n1, n1_prior, valid)
    n2 = _pull_to_prior(n2, n2_prior, valid)
    n1 = _slow_offset(n1, arc, valid)
    n2 = _slow_offset(n2, arc, valid)
    both = valid & np.isfinite(n1) & np.isfinite(n2)
    if int(both.sum()) >= 5:
        thick = np.full(len(n1), np.nan, dtype=np.float32)
        thick[both] = n2[both] - n1[both]
        thick = _slow_offset(thick, arc, both, sigma=4.5)
        med = float(np.nanmedian(thick))
        if not np.isfinite(med):
            med = max(3.0, n2_prior - n1_prior)
        lo_t, hi_t = max(2.8, 0.60 * med), min(16.0, 1.55 * med)
        thick = np.clip(thick, lo_t, hi_t)
        n2[valid] = n1[valid] + thick[valid]
    flip = valid & np.isfinite(n1) & np.isfinite(n2) & (n2 < n1 + 2.5)
    n2[flip] = n1[flip] + max(3.0, n2_prior - n1_prior)

    muc_lo = np.full(len(pts), muc_lo0, dtype=np.float32)
    ser_hi = np.full(len(pts), ser_hi0, dtype=np.float32)
    ok_in = valid & np.isfinite(n1)
    ok_out = valid & np.isfinite(n2)
    muc_lo[ok_in] = np.clip(np.minimum(muc_lo[ok_in], n1[ok_in] - 2.5), -float(half) + 0.5, n1[ok_in] - 2.0)
    ser_hi[ok_out] = np.clip(np.maximum(ser_hi[ok_out], n2[ok_out] + 2.5), n2[ok_out] + 2.0, float(half) - 0.5)
    st1 = _xy(pts, normals, n1)
    st2 = _xy(pts, normals, n2)
    st_in = _xy(pts, normals, muc_lo)
    st_out = _xy(pts, normals, ser_hi)
    xy1 = _dense_from_stations(st1, valid)
    xy2 = _dense_from_stations(st2, valid)
    hi1, lo1 = xy1, np.zeros((0, 2), dtype=np.float32)
    hi2, lo2 = xy2, np.zeros((0, 2), dtype=np.float32)
    ribbons = [
        {"id": "mucosa", "points": _ribbon_from_xy(st_in, st1, valid), "mean_gray": None},
        {"id": "muscularis", "points": _ribbon_from_xy(st1, st2, valid), "mean_gray": None},
        {"id": "serosa", "points": _ribbon_from_xy(st2, st_out, valid), "mean_gray": None},
    ]
    pixels = _label_corridor_pixels(
        gray, pts, normals, n1, n2, muc_lo, ser_hi, blocked, valid, gray_centers,
    )
    lab_of = {"mucosa": 0, "muscularis": 1, "serosa": 2}
    xs_p = np.asarray(pixels.get("xs", []), dtype=np.int32)
    ys_p = np.asarray(pixels.get("ys", []), dtype=np.int32)
    labs_p = np.asarray(pixels.get("labels", []), dtype=np.int32)
    for item in ribbons:
        lab = lab_of.get(str(item["id"]), -1)
        sel = labs_p == lab
        if int(sel.sum()) >= 8:
            item["mean_gray"] = float(gray[ys_p[sel], xs_p[sel]].mean())
        else:
            poly = np.asarray(item["points"], dtype=np.float32)
            if len(poly) >= 6:
                item["mean_gray"] = _gray_at(gray, poly[:: max(1, len(poly) // 24)])
    dash1, band1, stop1 = _predict_band(pts, normals, n1, blocked, lesion_center)
    dash2, band2, stop2 = _predict_band(pts, normals, n2, blocked, lesion_center)

    solid2 = _finite(xy2)
    wrap_xy = np.zeros((0, 2), dtype=np.float32)
    wrapped = False
    seed_g = _gray_at(gray, solid2)
    if len(solid2) >= 2:
        start = solid2[-1] if float(solid2[-1, 0]) <= float(solid2[0, 0]) else solid2[0]
        nid = int(np.argmin(((pts - start.reshape(1, 2)) ** 2).sum(axis=1)))
        wrap_xy, wrapped = _wrap_outer(start, blocked, normals[nid], gray, seed_g)
        if len(wrap_xy) >= 6:
            wrap_xy = _smooth_heading(wrap_xy, sigma_px=10.0)

    mid_g = _gray_between(gray, _finite(xy1), _finite(xy2))
    lesion_g = float(gray[lesion_mask > 0].mean()) if int((lesion_mask > 0).sum()) >= 20 else None
    fused = bool(mid_g is not None and lesion_g is not None and abs(mid_g - lesion_g) <= FUSE_GRAY_TOL)

    def _bound_status(solid_n: int, wrapped_flag: bool) -> tuple[str, str]:
        if wrapped_flag:
            return "displaced", "outer echo follows the lesion rim"
        if solid_n >= 6:
            return "visible", ""
        if solid_n > 0:
            return "obscured", "short or weak edge"
        return "missing", ""

    s1, note1 = _bound_status(len(hi1) + len(lo1), False)
    s2, note2 = _bound_status(len(hi2) + len(lo2), wrapped)
    inner = Boundary(
        id="inner", name_zh="上层-肌层界面",
        solid_hi=hi1.tolist(), solid_lo=lo1.tolist(),
        dashed=dash1.tolist(), band=band1.tolist(),
        stop=stop1, n_mean=None if not np.isfinite(n1).any() else round(float(np.nanmean(n1)), 2),
        n_detected=int(np.isfinite(n1).sum()), status=s1, note=note1,
    )
    outer = Boundary(
        id="outer", name_zh="肌层-外层界面",
        solid_hi=hi2.tolist(), solid_lo=lo2.tolist(),
        dashed=dash2.tolist(), band=band2.tolist(), wrap=wrap_xy.tolist(),
        stop=stop2, n_mean=None if not np.isfinite(n2).any() else round(float(np.nanmean(n2)), 2),
        n_detected=int(np.isfinite(n2).sum()), status=s2, note=note2,
    )

    if fused:
        musc = _region("muscularis", "固有肌层", "fused", "mid-band gray meets the lesion")
    elif inner.n_detected >= 6 and outer.n_detected >= 6:
        musc = _region("muscularis", "固有肌层", "visible")
    elif inner.n_detected + outer.n_detected > 0:
        musc = _region("muscularis", "固有肌层", "obscured")
    else:
        musc = _region("muscularis", "固有肌层", "missing")
    muc = _region("mucosa", "黏膜复合层", "visible" if inner.n_detected >= 6 else ("obscured" if inner.n_detected else "missing"))
    if wrapped:
        ser = _region("serosa", "浆膜侧", "displaced", "outer line continues around the lesion")
    elif outer.n_detected >= 6:
        ser = _region("serosa", "浆膜侧", "visible")
    elif outer.n_detected:
        ser = _region("serosa", "浆膜侧", "obscured")
    else:
        ser = _region("serosa", "浆膜侧", "missing")
    # A missing image line is not serosal invasion and is not a cT.

    return CurveTrack(
        status="ok",
        dilate_px=dilate_px,
        cavity_side_source=cavity,
        boundaries=[inner, outer],
        regions=[muc, musc, ser],
        ribbons=ribbons,
        pixels=pixels,
    )


def summary(track: CurveTrack) -> dict[str, Any]:
    return {
        "status": track.status,
        "skip_reason": track.skip_reason,
        "dilate_px": track.dilate_px,
        "cavity_side_source": track.cavity_side_source,
        "boundaries": [
            {
                "id": item.id,
                "status": item.status,
                "n_detected": item.n_detected,
                "n_mean": item.n_mean,
                "note": item.note,
            }
            for item in track.boundaries
        ],
        "regions": [
            {"id": item.id, "status": item.status, "note": item.note}
            for item in track.regions
        ],
    }
