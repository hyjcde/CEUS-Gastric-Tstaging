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
    _fill_nan_1d,
    _heading_stations,
    _sample_normal_profile,
    _smooth1d,
)

SEARCH_PX = 18
NEAR_SEARCH_PX = 24
DILATE_PX = 5
D_MIN = 3
MIN_EDGE = 5.0
TOP_K = 12
LAM_SMOOTH = 0.28
LAM_THICK = 0.22
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


def _station_valid(pts: np.ndarray, blocked: np.ndarray, fit_side: str) -> np.ndarray:
    height, width = blocked.shape[:2]
    ok = np.ones((len(pts),), dtype=bool)
    xs = pts[:, 0]
    side = str(fit_side or "all").strip().lower()
    if side == "right" and len(pts):
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


def _light_smooth(values: np.ndarray) -> np.ndarray:
    """Mild 1D smooth. Not a global polynomial."""
    out = values.astype(np.float32).copy()
    ok = np.isfinite(out)
    if int(ok.sum()) < 5:
        return out
    idx = np.arange(len(out))
    filled = out.copy()
    filled[~ok] = np.interp(idx[~ok], idx[ok], out[ok])
    sm = _smooth1d(filled, 2)
    out[ok] = sm[ok]
    return out


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
    pts, normals = _heading_stations(wall, lumen_center, lesion_center, deepest)
    cavity = "lumen" if lumen_center is not None else "heuristic"
    if len(pts) < MIN_VALID_STATIONS:
        return CurveTrack(status="insufficient_normal_wall", dilate_px=dilate_px, cavity_side_source=cavity, skip_reason="short_heading")
    valid = _station_valid(pts, blocked, fit_side)
    if int(valid.sum()) < MIN_VALID_STATIONS:
        valid = _station_valid(pts, blocked, "all")
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
    n1 = _light_smooth(n1)
    n2 = _light_smooth(n2)
    both = np.isfinite(n1) & np.isfinite(n2)
    n2[both] = np.maximum(n2[both], n1[both] + float(D_MIN))

    xy1 = _xy(pts, normals, n1)
    xy2 = _xy(pts, normals, n2)
    hi1, lo1 = _split_conf(xy1, c1)
    hi2, lo2 = _split_conf(xy2, c2)
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
