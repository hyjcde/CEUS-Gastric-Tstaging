#!/usr/bin/env python3
"""Lesion-aware ordered curve tracking for gastric wall layers.

Clustering can propose bright / dark candidates. This module is the main
path: find thin, ordered, locally parallel ridges / valleys outside the
lesion, then decide missing / fused / wrap. Does not unlock cT.
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
    _finite_median_filter,
    _heading_stations,
    _sample_normal_profile,
    _smooth1d,
)

SEARCH_PX = 18
DILATE_PX = 5
MIN_PROM = 7.0
MIN_SEP = 4
JUMP_PX = 5.5
GAP_FILL = 2
PREDICT_PX = 26
WRAP_STEPS = 16
FUSE_GRAY_TOL = 18.0
MIN_VALID_STATIONS = 8
LAYER_IDS = ("shallow", "muscularis", "serosa")
LAYER_ZH = {"shallow": "浅层", "muscularis": "固有肌层", "serosa": "浆膜层"}
STATUS_ZH = {
    "detected": "检测到",
    "missing": "缺失",
    "fused": "融合",
    "uncertain": "不可判断",
    "wrap": "外侧绕行",
}


@dataclass
class LayerCurve:
    id: str
    name_zh: str
    kind: str
    status: str
    status_zh: str
    solid: list[list[float]] = field(default_factory=list)
    dashed: list[list[float]] = field(default_factory=list)
    wrap: list[list[float]] = field(default_factory=list)
    n_mean: float | None = None
    gray_mean: float | None = None
    n_detected: int = 0
    note: str = ""


@dataclass
class CurveTrack:
    status: str
    dilate_px: int
    cavity_side_source: str
    layers: list[LayerCurve] = field(default_factory=list)
    skip_reason: str = ""


def _extrema(profile: np.ndarray, mode: str) -> list[tuple[int, float, float]]:
    """Local max (bright ridge) or min (dark valley) with a simple prominence."""
    sm = _smooth1d(_fill_nan_1d(profile), 2)
    n = int(len(sm))
    hits: list[tuple[int, float, float]] = []
    for i in range(2, n - 2):
        if mode == "max":
            if not (sm[i] >= sm[i - 1] and sm[i] >= sm[i + 1]):
                continue
            neigh = min(float(sm[max(0, i - 5):i].min()), float(sm[i + 1:min(n, i + 6)].min()))
            prom = float(sm[i] - neigh)
        else:
            if not (sm[i] <= sm[i - 1] and sm[i] <= sm[i + 1]):
                continue
            neigh = max(float(sm[max(0, i - 5):i].max()), float(sm[i + 1:min(n, i + 6)].max()))
            prom = float(neigh - sm[i])
        if prom >= MIN_PROM:
            hits.append((i, float(sm[i]), prom))
    return hits


def _best(cands: list[tuple[int, float, float]], toward: int, brighter: bool) -> tuple[int, float, float] | None:
    if not cands:
        return None
    sign = 1.0 if brighter else -1.0

    def score(item: tuple[int, float, float]) -> float:
        return sign * item[1] + 0.25 * item[2] - 0.12 * abs(item[0] - toward)

    return max(cands, key=score)


def pick_ordered_candidates(profile: np.ndarray) -> dict[str, int | None]:
    """One station: optional upper peak, mid valley, lower peak. Any slot may be empty."""
    half = len(profile) // 2
    peaks = _extrema(profile, "max")
    valleys = _extrema(profile, "min")
    valley = None
    if valleys:
        valley = min(valleys, key=lambda item: abs(item[0] - half) - 0.08 * item[2])
    shallow = None
    serosa = None
    if valley is not None:
        left = [p for p in peaks if p[0] <= valley[0] - MIN_SEP]
        right = [p for p in peaks if p[0] >= valley[0] + MIN_SEP]
        shallow = _best(left, valley[0], True)
        serosa = _best(right, valley[0], True)
    elif peaks:
        strongest = max(peaks, key=lambda item: item[1] + 0.2 * item[2])
        if strongest[0] < half - 1:
            shallow = strongest
        elif strongest[0] > half + 1:
            serosa = strongest
    return {
        "shallow": None if shallow is None else int(shallow[0]),
        "muscularis": None if valley is None else int(valley[0]),
        "serosa": None if serosa is None else int(serosa[0]),
    }


def _series_from_picks(
    picks: list[dict[str, int | None]],
    key: str,
    half: int,
) -> np.ndarray:
    out = np.full((len(picks),), np.nan, dtype=np.float32)
    for i, pick in enumerate(picks):
        idx = pick.get(key)
        if idx is not None:
            out[i] = float(idx) - float(half)
    return out


def _smooth_offset(values: np.ndarray) -> np.ndarray:
    """Keep a layer thin and continuous. Do not invent long missing stretches."""
    out = values.astype(np.float32).copy()
    finite = np.isfinite(out)
    if int(finite.sum()) < 3:
        return out
    med = out.copy()
    work = out.copy()
    work[~finite] = np.nan
    filled = work.copy()
    idx = np.arange(len(work))
    if int(np.isfinite(work).sum()) >= 2:
        good = np.isfinite(work)
        filled[~good] = np.interp(idx[~good], idx[good], work[good])
        med = _finite_median_filter(filled, 7)
        med = _smooth1d(med, 2)
    for i in range(len(out)):
        if np.isfinite(out[i]) and abs(float(out[i]) - float(med[i])) > JUMP_PX:
            out[i] = np.nan
    # Fill only tiny holes so speckle does not become a fake layer.
    finite = np.isfinite(out)
    if int(finite.sum()) >= 2:
        i = 0
        while i < len(out):
            if np.isfinite(out[i]):
                i += 1
                continue
            j = i
            while j < len(out) and not np.isfinite(out[j]):
                j += 1
            left = i > 0 and np.isfinite(out[i - 1])
            right = j < len(out) and np.isfinite(out[j])
            if left and right and (j - i) <= GAP_FILL:
                out[i:j] = np.interp(np.arange(i, j), [i - 1, j], [out[i - 1], out[j]])
            i = j
    return out


def _enforce_order(n0: np.ndarray, n1: np.ndarray, n2: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Layers may not cross. Drop the weaker side if they do."""
    a, b, c = n0.copy(), n1.copy(), n2.copy()
    for i in range(len(a)):
        if np.isfinite(a[i]) and np.isfinite(b[i]) and a[i] > b[i] - 1.0:
            a[i] = np.nan
        if np.isfinite(b[i]) and np.isfinite(c[i]) and b[i] > c[i] - 1.0:
            b[i] = np.nan
        if np.isfinite(a[i]) and np.isfinite(c[i]) and a[i] > c[i] - 2.0:
            a[i] = np.nan
    return a, b, c


def _xy_from_offset(pts: np.ndarray, normals: np.ndarray, offsets: np.ndarray) -> np.ndarray:
    xy = np.full((len(pts), 2), np.nan, dtype=np.float32)
    ok = np.isfinite(offsets)
    xy[ok] = pts[ok] + normals[ok] * offsets[ok, None]
    return xy


def _polyline_finite(xy: np.ndarray) -> np.ndarray:
    ok = np.isfinite(xy).all(axis=1)
    return xy[ok]


def _facing_tangent(solid: np.ndarray, lesion_center: np.ndarray | None) -> tuple[np.ndarray, np.ndarray]:
    if len(solid) < 2:
        empty = np.zeros((2,), dtype=np.float32)
        return solid[-1] if len(solid) else empty, empty
    if lesion_center is None:
        start, tan = solid[-1], solid[-1] - solid[-2]
    elif float(np.linalg.norm(solid[0] - lesion_center)) <= float(np.linalg.norm(solid[-1] - lesion_center)):
        start, tan = solid[0], solid[0] - solid[1]
    else:
        start, tan = solid[-1], solid[-1] - solid[-2]
    nrm = float(np.linalg.norm(tan))
    if nrm < 1e-6:
        return start, np.zeros((2,), dtype=np.float32)
    return start.astype(np.float32), (tan / nrm).astype(np.float32)


def _extrapolate_dashed(
    solid: np.ndarray,
    lesion_mask: np.ndarray,
    lesion_center: np.ndarray | None,
) -> np.ndarray:
    """Predict a short dashed path toward the lesion. Never jump to the other flank."""
    if len(solid) < 2:
        return np.zeros((0, 2), dtype=np.float32)
    start, tan = _facing_tangent(solid, lesion_center)
    if float(np.linalg.norm(tan)) < 1e-6:
        return np.zeros((0, 2), dtype=np.float32)
    height, width = lesion_mask.shape[:2]
    dashed: list[list[float]] = []
    entered = False
    point = start.copy()
    for _ in range(int(PREDICT_PX)):
        point = point + tan
        x, y = int(round(float(point[0]))), int(round(float(point[1])))
        if x < 0 or y < 0 or x >= width or y >= height:
            break
        inside = bool(lesion_mask[y, x] > 0)
        if inside:
            entered = True
            dashed.append([float(point[0]), float(point[1])])
            continue
        if entered:
            # Left the lesion on the far side: stop. Do not reconnect.
            break
        if lesion_center is not None:
            dashed.append([float(point[0]), float(point[1])])
    return np.asarray(dashed, dtype=np.float32) if dashed else np.zeros((0, 2), dtype=np.float32)


def _wrap_along_lesion(
    start: np.ndarray,
    lesion_mask: np.ndarray,
    outer: np.ndarray,
    gray: np.ndarray,
    seed_gray: float | None,
) -> tuple[np.ndarray, bool]:
    """See whether a bright outer layer continues along the lesion rim."""
    contours, _ = cv2.findContours(lesion_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return np.zeros((0, 2), dtype=np.float32), False
    ring = max(contours, key=cv2.contourArea).reshape(-1, 2).astype(np.float32)
    if len(ring) < 8:
        return np.zeros((0, 2), dtype=np.float32), False
    nearest = int(np.argmin(((ring - start.reshape(1, 2)) ** 2).sum(axis=1)))
    step = 1
    nxt = ring[(nearest + 1) % len(ring)]
    prv = ring[(nearest - 1) % len(ring)]
    if float(np.dot(nxt - ring[nearest], outer)) < float(np.dot(prv - ring[nearest], outer)):
        step = -1
    path = []
    grays = []
    height, width = gray.shape[:2]
    for k in range(1, WRAP_STEPS + 1):
        q = ring[(nearest + step * k) % len(ring)]
        x, y = int(round(float(q[0]))), int(round(float(q[1])))
        if 0 <= x < width and 0 <= y < height:
            path.append([float(q[0]), float(q[1])])
            grays.append(float(gray[y, x]))
    if len(grays) < 6 or seed_gray is None:
        return np.zeros((0, 2), dtype=np.float32), False
    bright = float(np.mean(grays)) >= float(seed_gray) - 25.0
    return (np.asarray(path, dtype=np.float32) if bright else np.zeros((0, 2), dtype=np.float32)), bright


def _station_valid(pts: np.ndarray, blocked: np.ndarray, fit_side: str) -> np.ndarray:
    height, width = blocked.shape[:2]
    ok = np.ones((len(pts),), dtype=bool)
    xs = pts[:, 0]
    side = str(fit_side or "all").strip().lower()
    if side == "right" and len(pts):
        cut = float(np.quantile(xs, 0.55))
        ok &= xs >= cut
    elif side == "left" and len(pts):
        cut = float(np.quantile(xs, 0.45))
        ok &= xs <= cut
    for i, (x, y) in enumerate(pts.tolist()):
        xi, yi = int(round(x)), int(round(y))
        if xi < 0 or yi < 0 or xi >= width or yi >= height or blocked[yi, xi] > 0:
            ok[i] = False
    return ok


def _gray_at(gray: np.ndarray, xy: np.ndarray) -> float | None:
    if len(xy) == 0:
        return None
    height, width = gray.shape[:2]
    vals = []
    for x, y in xy.tolist():
        xi, yi = int(round(x)), int(round(y))
        if 0 <= xi < width and 0 <= yi < height:
            vals.append(float(gray[yi, xi]))
    if not vals:
        return None
    return float(np.mean(vals))


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
    """Track up to three ordered wall curves outside a dilated lesion."""
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

    half = int(search_px)
    picks: list[dict[str, int | None]] = []
    for i in range(len(pts)):
        if not valid[i]:
            picks.append({"shallow": None, "muscularis": None, "serosa": None})
            continue
        profile = _sample_normal_profile(gray, pts[i], normals[i], half, blocked)
        picks.append(pick_ordered_candidates(profile))

    n0 = _smooth_offset(_series_from_picks(picks, "shallow", half))
    n1 = _smooth_offset(_series_from_picks(picks, "muscularis", half))
    n2 = _smooth_offset(_series_from_picks(picks, "serosa", half))
    n0, n1, n2 = _enforce_order(n0, n1, n2)
    offsets = {"shallow": n0, "muscularis": n1, "serosa": n2}
    kinds = {"shallow": "bright", "muscularis": "dark", "serosa": "bright"}
    lesion_gray = float(gray[lesion_mask > 0].mean()) if int((lesion_mask > 0).sum()) >= 20 else None

    layers: list[LayerCurve] = []
    for name in LAYER_IDS:
        xy = _xy_from_offset(pts, normals, offsets[name])
        # Keep detections only on valid (non-lesion) stations.
        xy[~valid] = np.nan
        solid = _polyline_finite(xy)
        dashed = _extrapolate_dashed(solid, blocked, lesion_center)
        wrap_xy = np.zeros((0, 2), dtype=np.float32)
        wrapped = False
        gmean = _gray_at(gray, solid)
        n_mean = float(np.nanmean(offsets[name])) if np.isfinite(offsets[name]).any() else None
        status = "missing"
        note = ""
        if len(solid) >= 4:
            status = "detected"
            if name == "muscularis" and lesion_gray is not None and gmean is not None:
                if abs(gmean - lesion_gray) <= FUSE_GRAY_TOL:
                    status = "fused"
                    note = "dark band meets lesion gray"
            if name == "serosa" and len(solid) >= 2:
                start, _tan = _facing_tangent(solid, lesion_center)
                outer = normals[int(np.argmin(((pts - start.reshape(1, 2)) ** 2).sum(axis=1)))]
                wrap_xy, wrapped = _wrap_along_lesion(start, blocked, outer, gray, gmean)
                if wrapped:
                    status = "wrap"
                    note = "bright rim continues outside lesion"
        elif len(solid) > 0:
            status = "uncertain"
            note = "too short to trust"
        layers.append(LayerCurve(
            id=name,
            name_zh=LAYER_ZH[name],
            kind=kinds[name],
            status=status,
            status_zh=STATUS_ZH[status],
            solid=solid.tolist(),
            dashed=dashed.tolist(),
            wrap=wrap_xy.tolist(),
            n_mean=None if n_mean is None else round(float(n_mean), 2),
            gray_mean=None if gmean is None else round(float(gmean), 1),
            n_detected=int(len(solid)),
            note=note,
        ))
    return CurveTrack(status="ok", dilate_px=dilate_px, cavity_side_source=cavity, layers=layers)


def summary(track: CurveTrack) -> dict[str, Any]:
    return {
        "status": track.status,
        "skip_reason": track.skip_reason,
        "dilate_px": track.dilate_px,
        "cavity_side_source": track.cavity_side_source,
        "layers": [
            {
                "id": layer.id,
                "status": layer.status,
                "n_detected": layer.n_detected,
                "n_mean": layer.n_mean,
                "gray_mean": layer.gray_mean,
                "note": layer.note,
            }
            for layer in track.layers
        ],
    }
