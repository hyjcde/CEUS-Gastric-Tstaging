#!/usr/bin/env python3
"""Lesion-aware gastric-wall echo clustering (offline M0).

Cluster only normal-wall pixels after subtracting a dilated lesion mask.
Does not unlock cT. Does not call DINO.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import cv2
import numpy as np

MIN_VALID_PIXELS = 40
MIN_FLANK_ARC_PX = 12.0
DEPTH_WEIGHT = 0.60
# Gray stays primary. A small across term only keeps the two bright
# echoes on opposite sides of the dark band, so they stay parallel.
SENSITIVE_ACROSS = 0.15
# Prefer thin exclusive bands along the heading. Feature distance only
# nudges the two cuts; it cannot jump a pixel over a neighboring strip.
STRIP_MIN_COL = 8
STRIP_SMOOTH = 9
GRAY_SEARCH_PAD = 12
GRAY_CUT_PAD = 12
GRAY_CUT_MIN_SCORE = 4.0
ACROSS_SEARCH_PX = 36
ALONG_AVG = 9
MIN_GRAD = 5.0
MIN_CUT_SEP = 5
LABEL_PAD_PX = 16
JOIN_RAY_PX = 28.0
JOIN_END_PX = 16.0
JOIN_MAX_GAP = 42.0
JOIN_MAX_TURN_DEG = 22.0
SPLIT_ALONG = 8.0
SPLIT_XY_PX = 40.0
MIN_ACROSS_SEP = 0.28
MIN_STRIP_GAP = 0.32
ALONG_SMOOTH_SIGMA = 8.0
ACROSS_OUTLIER = 0.18
DEFAULT_BRUSH = 8.0
FATE_ZH = {
    "present": "还在",
    "vanished": "消失",
    "fused": "融合",
    "uncertain": "无法判断",
}
LAYER_NAMES_3 = ("shallow", "muscularis", "serosa")
LAYER_NAMES_ZH = {
    "shallow": "浅层",
    "muscularis": "固有肌层",
    "serosa": "浆膜层",
    "inner": "内侧",
    "outer": "外侧",
    "dark": "暗",
    "mid": "中",
    "bright": "亮",
}
INSUFFICIENT = "insufficient_normal_wall"


def as_xy(points: Any) -> np.ndarray:
    if points is None:
        return np.zeros((0, 2), dtype=np.float32)
    if isinstance(points, np.ndarray):
        if points.size == 0:
            return np.zeros((0, 2), dtype=np.float32)
        arr = np.asarray(points, dtype=np.float32)
        if arr.ndim == 2 and arr.shape[1] >= 2:
            return arr[:, :2].copy()
    rows = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            rows.append([float(point[0]), float(point[1])])
        except (TypeError, ValueError):
            continue
    if not rows:
        return np.zeros((0, 2), dtype=np.float32)
    return np.asarray(rows, dtype=np.float32)


def polygon_centroid(points: np.ndarray) -> np.ndarray | None:
    if len(points) < 1:
        return None
    return points.mean(axis=0)


def rasterize_polygon(shape: tuple[int, int], polygon: Any, box: dict | None = None) -> np.ndarray:
    height, width = shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    pts = as_xy(polygon)
    if len(pts) >= 3:
        if float(pts.max()) <= 1.5:
            pts = pts * np.array([width, height], dtype=np.float32)
        cv2.fillPoly(mask, [np.round(pts).astype(np.int32)], 255)
    elif box:
        try:
            x1, y1 = int(round(float(box["x1"]))), int(round(float(box["y1"])))
            x2, y2 = int(round(float(box["x2"]))), int(round(float(box["y2"])))
            cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)
        except (KeyError, TypeError, ValueError):
            pass
    return mask


def dilate_mask(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return mask.copy()
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    return cv2.dilate(mask, kernel)


def densify_polyline(points: np.ndarray, step: float = 1.4) -> np.ndarray:
    if len(points) < 2:
        return points.copy()
    out = [points[0]]
    for start, end in zip(points[:-1], points[1:]):
        delta = end - start
        length = float(np.hypot(delta[0], delta[1]))
        if length < 1e-6:
            continue
        n_step = max(1, int(np.ceil(length / step)))
        for index in range(1, n_step + 1):
            out.append(start + delta * (index / n_step))
    return np.asarray(out, dtype=np.float32)


def arc_length(points: np.ndarray) -> float:
    if len(points) < 2:
        return 0.0
    return float(np.sum(np.linalg.norm(np.diff(points, axis=0), axis=1)))


def closest_on_poly(point: np.ndarray, poly: np.ndarray) -> tuple[np.ndarray, int, float, np.ndarray]:
    best_pt = poly[0]
    best_idx = 0
    best_d2 = 1e18
    best_tan = np.array([1.0, 0.0], dtype=np.float32)
    for index in range(len(poly) - 1):
        a = poly[index]
        b = poly[index + 1]
        ab = b - a
        denom = float(np.dot(ab, ab)) + 1e-8
        t = float(np.clip(np.dot(point - a, ab) / denom, 0.0, 1.0))
        proj = a + t * ab
        d2 = float(np.dot(point - proj, point - proj))
        if d2 < best_d2:
            best_d2 = d2
            best_pt = proj
            best_idx = index
            best_tan = ab
    tan_n = float(np.hypot(best_tan[0], best_tan[1])) or 1.0
    return best_pt, best_idx, float(np.sqrt(best_d2)), (best_tan / tan_n).astype(np.float32)


def flip_outward(
    origin: np.ndarray,
    tangent: np.ndarray,
    lumen_center: np.ndarray | None,
    lesion_center: np.ndarray | None,
    deepest: np.ndarray | None,
) -> np.ndarray:
    normal = np.array([-tangent[1], tangent[0]], dtype=np.float32)
    hint = None
    if lumen_center is not None:
        hint = origin - lumen_center
    elif deepest is not None and lesion_center is not None:
        hint = deepest - lesion_center
    elif lesion_center is not None:
        hint = origin - lesion_center
    if hint is not None and float(np.dot(normal, hint)) < 0:
        normal = -normal
    nlen = float(np.hypot(normal[0], normal[1])) or 1.0
    return (normal / nlen).astype(np.float32)


def rasterize_brush(shape: tuple[int, int], polyline: np.ndarray, radius: float) -> np.ndarray:
    height, width = shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    if len(polyline) < 2:
        return mask
    thick = max(1, int(round(2.0 * radius + 1.0)))
    cv2.polylines(mask, [np.round(polyline).astype(np.int32)], False, 255, thick, cv2.LINE_AA)
    return mask


def split_flank_segments(
    polyline: np.ndarray,
    lesion_dilated: np.ndarray,
) -> list[dict[str, Any]]:
    height, width = lesion_dilated.shape[:2]
    inside = []
    for point in polyline:
        x = int(round(float(point[0])))
        y = int(round(float(point[1])))
        hit = 0 <= x < width and 0 <= y < height and lesion_dilated[y, x] > 0
        inside.append(hit)
    if not inside:
        return []
    first_in = next((i for i, flag in enumerate(inside) if flag), None)
    last_in = next((i for i, flag in enumerate(reversed(inside)) if flag), None)
    if first_in is None:
        return [{
            "side": "full",
            "points": polyline.tolist(),
            "arc_px": round(arc_length(polyline), 2),
        }]
    last_in = len(inside) - 1 - last_in
    segments = []
    left = polyline[:first_in]
    right = polyline[last_in + 1:]
    if len(left) >= 2:
        segments.append({
            "side": "left",
            "points": left.tolist(),
            "arc_px": round(arc_length(left), 2),
        })
    if len(right) >= 2:
        segments.append({
            "side": "right",
            "points": right.tolist(),
            "arc_px": round(arc_length(right), 2),
        })
    return segments


def sample_band_pixels(
    gray: np.ndarray,
    brush_mask: np.ndarray,
    polyline: np.ndarray,
    brush_radius: float,
    lumen_center: np.ndarray | None,
    lesion_center: np.ndarray | None,
    deepest: np.ndarray | None,
) -> dict[str, np.ndarray]:
    ys, xs = np.where(brush_mask > 0)
    if len(xs) == 0 or len(polyline) < 2:
        empty = np.zeros((0,), dtype=np.float32)
        return {
            "xs": empty.astype(np.int32),
            "ys": empty.astype(np.int32),
            "gray": empty,
            "across": empty,
            "along_idx": empty.astype(np.int32),
        }
    pts = np.stack([xs.astype(np.float32), ys.astype(np.float32)], axis=1)
    best_d2 = np.full((len(pts),), 1e18, dtype=np.float32)
    best_proj = np.zeros_like(pts)
    best_tan = np.zeros_like(pts)
    best_idx = np.zeros((len(pts),), dtype=np.int32)
    for index, (a, b) in enumerate(zip(polyline[:-1], polyline[1:])):
        ab = b - a
        denom = float(np.dot(ab, ab)) + 1e-8
        t = np.clip(((pts - a) @ ab) / denom, 0.0, 1.0)
        proj = a[None, :] + t[:, None] * ab[None, :]
        d2 = ((pts - proj) ** 2).sum(axis=1)
        better = d2 < best_d2
        best_d2[better] = d2[better]
        best_proj[better] = proj[better]
        best_tan[better] = ab
        best_idx[better] = index
    tan_n = np.maximum(np.hypot(best_tan[:, 0], best_tan[:, 1]), 1e-6)
    tangent = best_tan / tan_n[:, None]
    normals = np.stack([-tangent[:, 1], tangent[:, 0]], axis=1)
    if lumen_center is not None:
        hint = best_proj - lumen_center
    elif deepest is not None and lesion_center is not None:
        hint = np.broadcast_to((deepest - lesion_center).astype(np.float32), normals.shape)
    elif lesion_center is not None:
        hint = best_proj - lesion_center
    else:
        hint = None
    if hint is not None:
        flip = np.sum(normals * hint, axis=1) < 0
        normals[flip] *= -1
    signed = np.sum((pts - best_proj) * normals, axis=1)
    return {
        "xs": xs.astype(np.int32),
        "ys": ys.astype(np.int32),
        "gray": gray[ys, xs].astype(np.float32),
        "across": (signed / max(1e-3, brush_radius)).astype(np.float32),
        "along_idx": best_idx,
    }


CLUSTER_METHODS = (
    "kmeans",
    "gmm",
    "ward",
    "fcm",
    "kmeans1d_gray",
    "kmeans1d_across",
)


def kmeans_features(features: np.ndarray, k: int, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    if len(features) < k:
        labels = np.zeros((len(features),), dtype=np.int32)
        centers = features.copy() if len(features) else np.zeros((0, features.shape[1]), dtype=np.float32)
        return labels, centers
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 60, 0.2)
    _compact, labels, centers = cv2.kmeans(
        features.astype(np.float32),
        k,
        None,
        criteria,
        8,
        cv2.KMEANS_PP_CENTERS,
    )
    return labels.reshape(-1).astype(np.int32), centers.astype(np.float32)


def _centers_from_labels(features: np.ndarray, labels: np.ndarray, k: int) -> np.ndarray:
    dim = features.shape[1] if features.ndim == 2 else 1
    centers = np.zeros((k, dim), dtype=np.float32)
    for lab in range(k):
        sel = labels == lab
        if sel.any():
            centers[lab] = features[sel].mean(axis=0)
        else:
            centers[lab] = features.mean(axis=0)
    return centers


def gmm_features(features: np.ndarray, k: int, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    if len(features) < k:
        return kmeans_features(features, k, seed)
    try:
        from sklearn.mixture import GaussianMixture
    except ImportError:
        return kmeans_features(features, k, seed)
    model = GaussianMixture(
        n_components=k,
        covariance_type="diag",
        random_state=seed,
        n_init=4,
        max_iter=120,
        reg_covar=1e-4,
    )
    labels = model.fit_predict(features.astype(np.float64)).astype(np.int32)
    return labels, model.means_.astype(np.float32)


def ward_features(features: np.ndarray, k: int, seed: int = 7, max_fit: int = 1600) -> tuple[np.ndarray, np.ndarray]:
    if len(features) < k:
        return kmeans_features(features, k, seed)
    try:
        from sklearn.cluster import AgglomerativeClustering
    except ImportError:
        return kmeans_features(features, k, seed)
    if len(features) > max_fit:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(features), max_fit, replace=False)
        sub = features[idx]
        sub_lab = AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(sub)
        centers = _centers_from_labels(sub, sub_lab.astype(np.int32), k)
        d2 = ((features[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        return d2.argmin(axis=1).astype(np.int32), centers
    labels = AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(features)
    labels = labels.astype(np.int32)
    return labels, _centers_from_labels(features, labels, k)


def fcm_features(features: np.ndarray, k: int, seed: int = 7, m: float = 2.0, n_iter: int = 35) -> tuple[np.ndarray, np.ndarray]:
    if len(features) < k:
        return kmeans_features(features, k, seed)
    rng = np.random.default_rng(seed)
    u = rng.random((len(features), k)).astype(np.float64)
    u /= np.maximum(u.sum(axis=1, keepdims=True), 1e-8)
    feat = features.astype(np.float64)
    centers = np.zeros((k, feat.shape[1]), dtype=np.float64)
    for _ in range(n_iter):
        um = u ** m
        centers = (um.T @ feat) / np.maximum(um.sum(axis=0)[:, None], 1e-8)
        dist = np.linalg.norm(feat[:, None, :] - centers[None, :, :], axis=2)
        dist = np.maximum(dist, 1e-8)
        inv = dist ** (-2.0 / (m - 1.0))
        u = inv / np.maximum(inv.sum(axis=1, keepdims=True), 1e-8)
    labels = u.argmax(axis=1).astype(np.int32)
    return labels, centers.astype(np.float32)


def cluster_features(features: np.ndarray, k: int, method: str = "kmeans", seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    name = str(method or "kmeans").strip().lower()
    if name == "gmm":
        return gmm_features(features, k, seed)
    if name == "ward":
        return ward_features(features, k, seed)
    if name == "fcm":
        return fcm_features(features, k, seed)
    return kmeans_features(features, k, seed)


def features_for_method(samples: dict[str, np.ndarray], method: str) -> np.ndarray:
    gray = samples["gray"] / 255.0
    across = samples["across"] * DEPTH_WEIGHT
    name = str(method or "kmeans").strip().lower()
    if name == "kmeans1d_gray":
        return gray.reshape(-1, 1).astype(np.float32)
    if name == "kmeans1d_across":
        return across.reshape(-1, 1).astype(np.float32)
    return np.stack([gray, across], axis=1).astype(np.float32)


def majority_vote_sparse(xs: np.ndarray, ys: np.ndarray, labels: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    if len(labels) == 0:
        return labels
    grid = np.full(shape, -1, dtype=np.int32)
    grid[ys, xs] = labels
    next_labels = labels.copy()
    height, width = shape
    for i, (x, y) in enumerate(zip(xs.tolist(), ys.tolist())):
        tally: dict[int, int] = {}
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                xx, yy = x + dx, y + dy
                if xx < 0 or yy < 0 or xx >= width or yy >= height:
                    continue
                lab = int(grid[yy, xx])
                if lab < 0:
                    continue
                tally[lab] = tally.get(lab, 0) + 1
        if tally:
            next_labels[i] = max(tally, key=tally.get)
    return next_labels


def filter_small_components(
    xs: np.ndarray,
    ys: np.ndarray,
    labels: np.ndarray,
    shape: tuple[int, int],
    min_area: int = 8,
) -> np.ndarray:
    if len(labels) == 0:
        return labels
    cleaned = labels.copy()
    height, width = shape
    for lab in np.unique(labels):
        canvas = np.zeros(shape, dtype=np.uint8)
        sel = labels == lab
        canvas[ys[sel], xs[sel]] = 255
        n_cc, cc, stats, _ = cv2.connectedComponentsWithStats(canvas, 8)
        for cid in range(1, n_cc):
            if int(stats[cid, cv2.CC_STAT_AREA]) >= min_area:
                continue
            ys_c, xs_c = np.where(cc == cid)
            for x, y in zip(xs_c.tolist(), ys_c.tolist()):
                tally: dict[int, int] = {}
                for dy in (-2, -1, 0, 1, 2):
                    for dx in (-2, -1, 0, 1, 2):
                        xx, yy = x + dx, y + dy
                        if 0 <= xx < width and 0 <= yy < height:
                            hit = np.where((xs == xx) & (ys == yy))[0]
                            if len(hit) and int(cleaned[hit[0]]) != int(lab):
                                other = int(cleaned[hit[0]])
                                tally[other] = tally.get(other, 0) + 1
                if tally:
                    idx = np.where((xs == x) & (ys == y))[0]
                    if len(idx):
                        cleaned[idx[0]] = max(tally, key=tally.get)
    return cleaned


@dataclass
class ClusterArm:
    name: str
    status: str
    k: int
    method: str
    n_pixels: int
    n_valid: int
    dilate_px: int
    cavity_side_source: str
    pattern: str
    bright_dark_bright: bool
    skip_reason: str = ""
    classes: list[dict[str, Any]] = field(default_factory=list)
    flanks: list[dict[str, Any]] = field(default_factory=list)
    xs: list[int] = field(default_factory=list)
    ys: list[int] = field(default_factory=list)
    labels: list[int] = field(default_factory=list)
    layer_polylines: dict[str, list[list[float]]] = field(default_factory=dict)
    fates: list[dict[str, Any]] = field(default_factory=list)
    interfaces: list[list[list[float]]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("xs", None)
        data.pop("ys", None)
        data.pop("labels", None)
        slim_if = []
        for item in data.get("interfaces") or []:
            pts = item.get("points") if isinstance(item, dict) else item
            pts = pts or []
            step = max(1, len(pts) // 24)
            slim_if.append({"edge": item.get("edge", 0) if isinstance(item, dict) else 0, "points": pts[::step][:30]})
        data["interfaces"] = slim_if
        slim = []
        for seg in data.get("flanks") or []:
            pts = seg.get("points") or []
            step = max(1, len(pts) // 16)
            slim.append({
                "side": seg.get("side"),
                "arc_px": seg.get("arc_px"),
                "n_points": len(pts),
                "points": pts[::step][:20],
            })
        data["flanks"] = slim
        return data


def kmeans_gray_sensitive(values: np.ndarray, k: int, n_iter: int = 28) -> tuple[np.ndarray, np.ndarray]:
    """Split gray values from percentile seeds so dark and bright do not collapse."""
    vals = np.asarray(values, dtype=np.float32).reshape(-1)
    if len(vals) < k:
        labels = np.zeros((len(vals),), dtype=np.int32)
        centers = vals.copy() if len(vals) else np.zeros((0,), dtype=np.float32)
        return labels, centers
    qs = np.quantile(vals, np.linspace(0.12, 0.88, k)).astype(np.float32)
    centers = qs.copy()
    labels = np.zeros((len(vals),), dtype=np.int32)
    for _ in range(n_iter):
        dist = np.abs(vals[:, None] - centers[None, :])
        labels = dist.argmin(axis=1).astype(np.int32)
        for lab in range(k):
            sel = labels == lab
            if sel.any():
                centers[lab] = float(vals[sel].mean())
    return labels, centers


def assign_from_across_profile(
    samples: dict[str, np.ndarray],
    keep: np.ndarray,
    fit: np.ndarray,
    assign_lesion: bool,
) -> np.ndarray | None:
    """Thin bright-dark-bright from the right-side gray profile across the heading."""
    gray = samples["gray"].astype(np.float32)
    across = samples["across"].astype(np.float32)
    if int(fit.sum()) < MIN_VALID_PIXELS:
        return None
    edges = np.linspace(-1.05, 1.05, 29)
    mids = 0.5 * (edges[:-1] + edges[1:])
    prof = np.full((len(mids),), np.nan, dtype=np.float32)
    dark_p = np.full((len(mids),), np.nan, dtype=np.float32)
    for i, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        sel = fit & (across >= lo) & (across < hi)
        if int(sel.sum()) >= 3:
            prof[i] = float(gray[sel].mean())
            dark_p[i] = float(np.percentile(gray[sel], 15))
    ok = np.isfinite(prof)
    if int(ok.sum()) < 7:
        return None
    idx = np.arange(len(prof))
    prof = np.interp(idx, idx[ok], prof[ok]).astype(np.float32)
    dark_p = np.interp(idx, idx[np.isfinite(dark_p)], dark_p[np.isfinite(dark_p)]).astype(np.float32)
    # Thin hypoechoic belts show up in the 15th percentile, not the mean.
    lo_i, hi_i = 4, len(dark_p) - 4
    dips = [
        i for i in range(lo_i, hi_i)
        if dark_p[i] <= dark_p[i - 1] and dark_p[i] <= dark_p[i + 1]
    ]
    valley = int(min(dips, key=lambda i: float(dark_p[i]))) if dips else lo_i + int(np.argmin(dark_p[lo_i:hi_i]))
    left = int(np.argmax(prof[: valley + 1]))
    right = valley + int(np.argmax(prof[valley:]))
    if right <= valley or left >= valley:
        return None
    if float(prof[left]) < float(prof[valley]) + 6.0 and float(prof[right]) < float(prof[valley]) + 6.0:
        return None
    cut_l = 0.5 * (float(mids[left]) + float(mids[valley]))
    cut_r = 0.5 * (float(mids[valley]) + float(mids[right]))
    mid_g = 0.5 * (float(prof[valley]) + float(max(prof[left], prof[right])))
    dark_thr = float(dark_p[valley]) + 10.0
    valley_ac = float(mids[valley])
    pred = np.where(across < cut_l, 0, np.where(across > cut_r, 2, 1)).astype(np.int32)
    pred = np.where((gray < mid_g) & (across >= cut_l) & (across <= cut_r), 1, pred)
    pred = np.where((gray >= mid_g) & (across < cut_l), 0, pred)
    pred = np.where((gray >= mid_g) & (across > cut_r), 2, pred)
    pred = np.where((gray <= dark_thr) & (across >= cut_l) & (across <= cut_r), 1, pred)
    pred = np.where((np.abs(across) > 0.90) & (gray < mid_g), -1, pred)
    # Muscularis is the middle dark strip. It must not pass the serosa.
    pred = np.where((pred == 1) & (across > cut_r), 2, pred)
    labels_all = np.full(len(gray), -1, dtype=np.int32)
    keep_lab = keep & (pred >= 0)
    labels_all[keep_lab] = pred[keep_lab]
    if assign_lesion:
        labels_all[~keep] = pred[~keep]
    return labels_all


def pin_thin_hypoechoic(
    samples: dict[str, np.ndarray],
    keep: np.ndarray,
    fit: np.ndarray,
    labels: np.ndarray,
) -> np.ndarray:
    """Put the darkest thin echo back on muscularis after the walk drifts."""
    gray = samples["gray"].astype(np.float32)
    across = samples["across"].astype(np.float32)
    if int(fit.sum()) < MIN_VALID_PIXELS:
        return labels
    interior = np.abs(across) <= 0.88
    if int((fit & interior).sum()) < MIN_VALID_PIXELS:
        return labels
    dark_cut = float(np.percentile(gray[fit & interior], 22))
    dark_fit = fit & interior & (gray <= dark_cut)
    if int(dark_fit.sum()) < 8:
        return labels
    valley_ac = float(np.median(across[dark_fit]))
    dark_thr = float(np.percentile(gray[dark_fit], 80))
    pin = keep & (gray <= dark_thr) & (np.abs(across - valley_ac) <= 0.22)
    out = labels.copy()
    out[pin] = 1
    return enforce_strip_order(samples, keep, fit, out)


def enforce_strip_order(
    samples: dict[str, np.ndarray],
    keep: np.ndarray,
    fit: np.ndarray,
    labels: np.ndarray,
) -> np.ndarray:
    """Keep three separate strips: inner bright, mid dark, outer bright."""
    gray = samples["gray"].astype(np.float32)
    across = samples["across"].astype(np.float32)
    out = labels.copy()
    seed = fit & (out >= 0)
    if int((seed & (out == 2)).sum()) < 8 or int((seed & (out == 1)).sum()) < 8:
        return out
    ser_in = float(np.percentile(across[seed & (out == 2)], 20))
    mus_g = float(np.median(gray[seed & (out == 1)]))
    ser_g = float(np.median(gray[seed & (out == 2)]))
    mid_g = 0.5 * (mus_g + ser_g)
    past = keep & (out == 1) & (across >= ser_in)
    out[past & (gray >= mid_g)] = 2
    out[past & (gray < mid_g)] = -1
    if int((seed & (out == 0)).sum()) >= 8:
        sha_out = float(np.percentile(across[seed & (out == 0)], 80))
        cross = keep & (out == 0) & (across >= sha_out)
        out[cross & (gray < mid_g)] = 1
        out[cross & (gray >= mid_g) & (across >= ser_in)] = 2
    xs = samples["xs"]
    if int((seed & (out == 2)).sum()) >= 8:
        ser_xmax = float(xs[seed & (out == 2)].max())
        stick = keep & (out == 1) & (xs > ser_xmax + 1.5)
        out[stick] = -1
    return out


def assign_walk_until_lesion(
    samples: dict[str, np.ndarray],
    keep: np.ndarray,
    fit: np.ndarray,
    assign_lesion: bool,
) -> np.ndarray | None:
    """Cluster by gray, walk from the right, stop only at lesion pixels."""
    seeded = assign_from_across_profile(samples, keep, fit, assign_lesion=False)
    gray = samples["gray"].astype(np.float32)
    across = samples["across"].astype(np.float32)
    along = samples["along_idx"]
    xs = samples["xs"]
    labels_all = np.full(len(gray), -1, dtype=np.int32)
    if seeded is None:
        return None
    seed = fit & (seeded >= 0) & (np.abs(across) <= 0.88)
    if int(seed.sum()) < MIN_VALID_PIXELS:
        return None
    g_live = np.array([
        float(gray[seed & (seeded == lab)].mean()) if np.any(seed & (seeded == lab)) else 0.0
        for lab in range(3)
    ], dtype=np.float32)
    a_live = np.array([
        float(across[seed & (seeded == lab)].mean()) if np.any(seed & (seeded == lab)) else 0.0
        for lab in range(3)
    ], dtype=np.float32)
    stations = np.unique(along)
    order = sorted(
        stations.tolist(),
        key=lambda st: -float(xs[along == st].mean()) if np.any(along == st) else 0.0,
    )
    for st in order:
        pix = (along == st) & keep
        if int(pix.sum()) < 2:
            continue
        dist = (
            np.abs(gray[pix, None] / 255.0 - g_live[None, :] / 255.0)
            + SENSITIVE_ACROSS * np.abs(across[pix, None] - a_live[None, :])
        )
        lab = dist.argmin(axis=1).astype(np.int32)
        # Do not let muscularis walk past the live serosa across.
        if np.isfinite(a_live[2]):
            past = (lab == 1) & (across[pix] >= a_live[2] - 0.04)
            lab = np.where(past & (gray[pix] >= 0.5 * (g_live[1] + g_live[2])), 2, lab)
            lab = np.where(past & (gray[pix] < 0.5 * (g_live[1] + g_live[2])), -1, lab)
        labels_all[pix] = lab
        for i in range(3):
            sel = lab == i
            if int(sel.sum()) >= 2:
                g_live[i] = 0.88 * g_live[i] + 0.12 * float(gray[pix][sel].mean())
                if i != 1:
                    a_live[i] = 0.88 * a_live[i] + 0.12 * float(across[pix][sel].mean())
    labels_all = pin_thin_hypoechoic(samples, keep, fit, labels_all)
    if assign_lesion:
        rest = ~keep
        if rest.any():
            dist = (
                np.abs(gray[rest, None] / 255.0 - g_live[None, :] / 255.0)
                + SENSITIVE_ACROSS * np.abs(across[rest, None] - a_live[None, :])
            )
            labels_all[rest] = dist.argmin(axis=1).astype(np.int32)
    if int((labels_all[keep] >= 0).sum()) < MIN_VALID_PIXELS:
        return seeded
    return labels_all


def assign_sensitive_layers(
    samples: dict[str, np.ndarray],
    keep: np.ndarray,
    fit: np.ndarray,
    k: int,
    assign_lesion: bool,
    shape: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Gray-first layers. Two brights sit on opposite sides of the dark band."""
    gray = samples["gray"].astype(np.float32)
    across = samples["across"].astype(np.float32)
    labels_all = np.full(len(gray), -1, dtype=np.int32)
    if int(fit.sum()) < MIN_VALID_PIXELS or k < 2:
        return labels_all, labels_all[keep]
    if k == 3:
        walked = assign_walk_until_lesion(samples, keep, fit, assign_lesion)
        if walked is not None:
            return walked, walked[keep]
        profile = assign_from_across_profile(samples, keep, fit, assign_lesion)
        if profile is not None:
            return profile, profile[keep]
        lab2, centers2 = kmeans_gray_sensitive(gray[fit], 2)
        if float(centers2[0]) > float(centers2[1]):
            lab2 = 1 - lab2
            centers2 = centers2[::-1]
        dark_g = float(centers2[0])
        bright_g = float(centers2[1])
        if (bright_g - dark_g) >= 10.0 and np.any(lab2 == 0):
            dark_ac = float(across[fit][lab2 == 0].mean())
            mid_g = 0.5 * (dark_g + bright_g)
            is_dark = gray <= (mid_g - 5.0)
            is_bright = gray >= (mid_g + 5.0)
            pred = np.where(
                is_dark,
                1,
                np.where(is_bright, np.where(across < dark_ac, 0, 2), np.where(np.abs(across - dark_ac) < 0.22, 1, np.where(across < dark_ac, 0, 2))),
            ).astype(np.int32)
            labels_all[keep] = pred[keep]
            if assign_lesion:
                labels_all[~keep] = pred[~keep]
            sel = labels_all >= 0
            if sel.any():
                cleaned = filter_small_components(
                    samples["xs"][sel], samples["ys"][sel], labels_all[sel], shape, min_area=4,
                )
                labels_all[sel] = cleaned
            return labels_all, labels_all[keep]
    seed_lab, _ = kmeans_gray_sensitive(gray[fit], k)
    order = np.argsort([
        float(across[fit][seed_lab == lab].mean()) if np.any(seed_lab == lab) else 0.0
        for lab in range(k)
    ])
    remap = {int(old): int(new) for new, old in enumerate(order.tolist())}
    seed_lab = np.array([remap[int(lab)] for lab in seed_lab], dtype=np.int32)
    g_c = np.array([
        float(gray[fit][seed_lab == lab].mean()) if np.any(seed_lab == lab) else 0.0
        for lab in range(k)
    ], dtype=np.float32)
    a_c = np.array([
        float(across[fit][seed_lab == lab].mean()) if np.any(seed_lab == lab) else 0.0
        for lab in range(k)
    ], dtype=np.float32)
    dist = np.abs(gray[:, None] / 255.0 - g_c[None, :] / 255.0) + SENSITIVE_ACROSS * np.abs(across[:, None] - a_c[None, :])
    pred = dist.argmin(axis=1).astype(np.int32)
    labels_all[keep] = pred[keep]
    if assign_lesion:
        labels_all[~keep] = pred[~keep]
    sel = labels_all >= 0
    if sel.any():
        cleaned = filter_small_components(
            samples["xs"][sel], samples["ys"][sel], labels_all[sel], shape, min_area=4,
        )
        labels_all[sel] = cleaned
    return labels_all, labels_all[keep]


def layer_centers(
    xs: np.ndarray,
    ys: np.ndarray,
    labels: np.ndarray,
    names: tuple[str, ...],
    along: np.ndarray | None = None,
    skip: np.ndarray | None = None,
) -> dict[str, list[list[float]]]:
    out: dict[str, list[list[float]]] = {}
    for lab, name in enumerate(names):
        sel = labels == lab
        if skip is not None:
            sel = sel & ~skip
        if int(sel.sum()) < 4:
            out[name] = []
            continue
        if along is None:
            pts = np.stack([xs[sel].astype(np.float32), ys[sel].astype(np.float32)], axis=1)
            order = np.argsort(pts[:, 0] * 0.7 + pts[:, 1] * 0.3)
            pts = pts[order]
            bins = max(6, min(48, len(pts) // 6))
            edges = np.linspace(0, len(pts), bins + 1).astype(int)
            line = []
            for a, b in zip(edges[:-1], edges[1:]):
                chunk = pts[a:b]
                if len(chunk) >= 2:
                    line.append([float(chunk[:, 0].mean()), float(chunk[:, 1].mean())])
            out[name] = line
            continue
        line = []
        started = False
        gap = 0
        for st in np.unique(along):
            hit = sel & (along == st)
            if int(hit.sum()) >= 2:
                line.append([float(xs[hit].mean()), float(ys[hit].mean())])
                started = True
                gap = 0
            elif started:
                gap += 1
                if gap >= 2:
                    break
        out[name] = line
    return out


def walk_layer_fate(
    samples: dict[str, np.ndarray],
    labels: np.ndarray,
    keep: np.ndarray,
    fit: np.ndarray,
    lesion_mask: np.ndarray,
    names: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Compare right-seed layers with the ring just outside the lesion."""
    gray = samples["gray"]
    xs = samples["xs"]
    ys = samples["ys"]
    height, width = lesion_mask.shape[:2]
    approach = dilate_mask(lesion_mask, 16)
    core = dilate_mask(lesion_mask, 5)
    ring = np.zeros((len(xs),), dtype=bool)
    for i, (x, y) in enumerate(zip(xs.tolist(), ys.tolist())):
        if 0 <= x < width and 0 <= y < height and approach[y, x] > 0 and core[y, x] == 0:
            ring[i] = True
    seed = fit & (labels >= 0)
    peri = ring & keep & (labels >= 0)
    seed_n, seed_g, peri_n, peri_g = [], [], [], []
    for lab in range(len(names)):
        s = seed & (labels == lab)
        p = peri & (labels == lab)
        seed_n.append(int(s.sum()))
        peri_n.append(int(p.sum()))
        seed_g.append(float(gray[s].mean()) if s.any() else float("nan"))
        peri_g.append(float(gray[p].mean()) if p.any() else float("nan"))
    inside = ~keep
    inside_n = [0] * len(names)
    if int(inside.sum()) >= 20 and all(n >= 8 for n in seed_n):
        centers = np.array(seed_g, dtype=np.float32)
        pred_in = np.abs(gray[inside, None] - centers[None, :]).argmin(axis=1)
        for lab in range(len(names)):
            inside_n[lab] = int((pred_in == lab).sum())
        total_in = float(max(1, int(inside.sum())))
        dominant = int(np.argmax(inside_n))
        if inside_n[dominant] / total_in >= 0.70:
            fates = []
            for lab, name in enumerate(names):
                status = "fused" if lab == dominant else "vanished"
                fates.append({
                    "id": name,
                    "name_zh": LAYER_NAMES_ZH.get(name, name),
                    "status": status,
                    "status_zh": FATE_ZH[status],
                    "fuse_with": "dark-mass" if status == "fused" else "",
                    "seed_gray": round(seed_g[lab], 1),
                    "peri_gray": None if peri_g[lab] != peri_g[lab] else round(peri_g[lab], 1),
                    "seed_count": seed_n[lab],
                    "peri_count": peri_n[lab],
                    "inside_count": inside_n[lab],
                })
            return fates
        fates = []
        for lab, name in enumerate(names):
            status = "vanished" if inside_n[lab] / total_in < 0.12 else "present"
            fates.append({
                "id": name,
                "name_zh": LAYER_NAMES_ZH.get(name, name),
                "status": status,
                "status_zh": FATE_ZH[status],
                "fuse_with": "",
                "seed_gray": round(seed_g[lab], 1),
                "peri_gray": None if peri_g[lab] != peri_g[lab] else round(peri_g[lab], 1),
                "seed_count": seed_n[lab],
                "peri_count": peri_n[lab],
                "inside_count": inside_n[lab],
            })
        return fates
    fates = []
    for lab, name in enumerate(names):
        status = "present"
        fuse_with = ""
        if seed_n[lab] < 8:
            status = "uncertain"
        elif peri_n[lab] < max(6, int(0.18 * seed_n[lab])):
            status = "vanished"
        else:
            for other in (lab - 1, lab + 1):
                if other < 0 or other >= len(names):
                    continue
                if seed_n[other] < 8 or peri_n[other] < 6:
                    continue
                d0 = abs(seed_g[lab] - seed_g[other])
                d1 = abs(peri_g[lab] - peri_g[other])
                if d0 >= 12.0 and d1 < max(8.0, 0.40 * d0):
                    status = "fused"
                    fuse_with = names[other]
                    break
        fates.append({
            "id": name,
            "name_zh": LAYER_NAMES_ZH.get(name, name),
            "status": status,
            "status_zh": FATE_ZH[status],
            "fuse_with": fuse_with,
            "seed_gray": None if seed_g[lab] != seed_g[lab] else round(seed_g[lab], 1),
            "peri_gray": None if peri_g[lab] != peri_g[lab] else round(peri_g[lab], 1),
            "seed_count": seed_n[lab],
            "peri_count": peri_n[lab],
            "inside_count": inside_n[lab],
        })
    return fates


def _smooth1d(values: np.ndarray, radius: int = 2) -> np.ndarray:
    if len(values) < 3:
        return values.astype(np.float32)
    kernel = np.arange(1, 2 * radius + 2, dtype=np.float32)
    kernel = np.minimum(kernel, kernel[::-1])
    kernel /= float(kernel.sum())
    return np.convolve(np.pad(values.astype(np.float32), (radius, radius), mode="edge"), kernel, mode="valid")


def cuts_from_labels(across: np.ndarray, labels: np.ndarray, keep: np.ndarray) -> list[float]:
    cuts = []
    for left, right in ((0, 1), (1, 2)):
        a = keep & (labels == left)
        b = keep & (labels == right)
        if int(a.sum()) < 6 or int(b.sum()) < 6:
            continue
        cuts.append(0.5 * (float(np.median(across[a])) + float(np.median(across[b]))))
    return cuts


def _column_gray_peaks(xs, ys, gray, across, pix: np.ndarray) -> list[dict[str, float]]:
    if int(pix.sum()) < 5:
        return []
    order = np.argsort(across[pix])
    ac = across[pix][order]
    gg = gray[pix][order]
    xx = xs[pix][order].astype(np.float32)
    yy = ys[pix][order].astype(np.float32)
    if float(ac[-1] - ac[0]) < 0.12:
        return []
    grid = np.linspace(float(ac[0]), float(ac[-1]), max(18, int(round(24.0 * (ac[-1] - ac[0])))))
    g_i = np.interp(grid, ac, gg)
    x_i = np.interp(grid, ac, xx)
    y_i = np.interp(grid, ac, yy)
    smooth = _smooth1d(g_i, 2)
    grad = np.gradient(smooth)
    mag = np.abs(grad)
    peaks = []
    for i in range(2, len(mag) - 2):
        if mag[i] >= mag[i - 1] and mag[i] >= mag[i + 1] and mag[i] >= 5.0:
            peaks.append({
                "across": float(grid[i]),
                "mag": float(mag[i]),
                "grad": float(grad[i]),
                "x": float(x_i[i]),
                "y": float(y_i[i]),
            })
    return peaks


def _poly_tangent(pts: np.ndarray, at_start: bool) -> np.ndarray:
    pts = np.asarray(pts, dtype=np.float32)
    if len(pts) < 2:
        return np.array([1.0, 0.0], dtype=np.float32)
    span = min(8, len(pts) - 1)
    if at_start:
        delta = pts[0] - pts[span]
    else:
        delta = pts[-1] - pts[-1 - span]
    leng = float(np.hypot(delta[0], delta[1])) or 1.0
    return (delta / leng).astype(np.float32)


def _angle_deg(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.degrees(np.arccos(float(np.clip(np.dot(a, b), -1.0, 1.0)))))


def _hermite_bridge(p0: np.ndarray, t0: np.ndarray, p1: np.ndarray, t1: np.ndarray) -> list[list[float]]:
    """Short, almost-straight bridge. Full-gap tangents overshoot and look too bent."""
    gap = float(np.hypot(*(p1 - p0)))
    handle = 0.22 * gap
    m0 = t0 * handle
    m1 = t1 * handle
    count = max(2, int(round(gap / 4.0)))
    out = []
    for t in np.linspace(0.0, 1.0, count + 2)[1:-1]:
        t2 = t * t
        t3 = t2 * t
        point = (
            (2 * t3 - 3 * t2 + 1) * p0
            + (t3 - 2 * t2 + t) * m0
            + (-2 * t3 + 3 * t2) * p1
            + (t3 - t2) * m1
        )
        out.append([float(point[0]), float(point[1])])
    return out


def smooth_open_poly(pts: np.ndarray, sigma: float = 3.2) -> np.ndarray:
    pts = np.asarray(pts, dtype=np.float32)
    if len(pts) < 4 or sigma <= 0:
        return pts
    pts = densify_polyline(pts, 1.6)
    radius = max(1, int(round(sigma * 2.4)))
    kernel = np.exp(-0.5 * (np.arange(-radius, radius + 1, dtype=np.float32) / sigma) ** 2)
    kernel /= float(kernel.sum())
    xs = np.convolve(np.pad(pts[:, 0], (radius, radius), mode="edge"), kernel, mode="valid")
    ys = np.convolve(np.pad(pts[:, 1], (radius, radius), mode="edge"), kernel, mode="valid")
    return np.stack([xs, ys], axis=1).astype(np.float32)


def smooth_by_along(pts: np.ndarray, along: np.ndarray | None = None, sigma: float = ALONG_SMOOTH_SIGMA) -> np.ndarray:
    """Smooth x(along), y(along). Arc-length smooth cannot kill a sawtooth."""
    pts = np.asarray(pts, dtype=np.float32)[:, :2]
    if len(pts) < 4 or sigma <= 0:
        return pts
    if along is None:
        along = np.arange(len(pts), dtype=np.float32)
    else:
        along = np.asarray(along, dtype=np.float32).reshape(-1)
        if len(along) != len(pts):
            along = np.arange(len(pts), dtype=np.float32)
    order = np.argsort(along)
    along = along[order]
    pts = pts[order]
    span = float(along[-1] - along[0])
    n_grid = max(len(pts), int(round(span)) + 1, 8)
    grid = np.linspace(float(along[0]), float(along[-1]), n_grid)
    xs = np.interp(grid, along, pts[:, 0])
    ys = np.interp(grid, along, pts[:, 1])
    radius = max(1, int(round(sigma * 2.4)))
    kernel = np.exp(-0.5 * (np.arange(-radius, radius + 1, dtype=np.float32) / sigma) ** 2)
    kernel /= float(kernel.sum())
    xs = np.convolve(np.pad(xs, (radius, radius), mode="edge"), kernel, mode="valid")
    ys = np.convolve(np.pad(ys, (radius, radius), mode="edge"), kernel, mode="valid")
    out = np.stack([xs, ys], axis=1).astype(np.float32)
    out[0] = pts[0]
    out[-1] = pts[-1]
    return out


def gentle_curve(pts: np.ndarray, along: np.ndarray | None = None) -> np.ndarray:
    """Low-order curve vs heading: keep the wall arc, drop sawtooth hooks."""
    pts = np.asarray(pts, dtype=np.float32)[:, :2]
    if len(pts) < 4:
        return pts
    if along is None or len(np.asarray(along).reshape(-1)) != len(pts):
        along = np.arange(len(pts), dtype=np.float32)
    else:
        along = np.asarray(along, dtype=np.float32).reshape(-1)
    order = np.argsort(along)
    along = along[order]
    pts = pts[order]
    t = along - float(along.mean())
    span = float(along[-1] - along[0])
    degree = 1 if span < 12.0 or len(pts) < 8 else 2
    try:
        px = np.polyfit(t, pts[:, 0], degree)
        py = np.polyfit(t, pts[:, 1], degree)
    except (np.linalg.LinAlgError, ValueError):
        return smooth_by_along(pts, along)
    n_grid = max(len(pts), int(round(float(np.hypot(*(pts[-1] - pts[0]))))), 8)
    grid = np.linspace(float(t[0]), float(t[-1]), n_grid)
    return np.stack([np.polyval(px, grid), np.polyval(py, grid)], axis=1).astype(np.float32)


def reject_sharp_turns(pts: np.ndarray, max_deg: float = 30.0) -> np.ndarray:
    pts = np.asarray(pts, dtype=np.float32)
    if len(pts) < 3:
        return pts
    kept = [pts[0]]
    for i in range(1, len(pts) - 1):
        incoming = pts[i] - kept[-1]
        outgoing = pts[i + 1] - pts[i]
        if float(np.hypot(*incoming)) < 0.4 or float(np.hypot(*outgoing)) < 0.4:
            continue
        a = incoming / max(float(np.hypot(*incoming)), 1e-6)
        b = outgoing / max(float(np.hypot(*outgoing)), 1e-6)
        if _angle_deg(a, b) <= max_deg:
            kept.append(pts[i])
    kept.append(pts[-1])
    return np.asarray(kept, dtype=np.float32)


def try_join_runs(left: np.ndarray, right: np.ndarray) -> np.ndarray | None:
    """Join left's end to right's start if the two ends keep a mild heading."""
    left = np.asarray(left, dtype=np.float32)
    right = np.asarray(right, dtype=np.float32)
    if len(left) < 2 or len(right) < 2:
        return None
    t_left = _poly_tangent(left, False)
    t_right_out = _poly_tangent(right, True)
    t_right = -t_right_out
    p0 = left[-1]
    p1 = right[0]
    gap_vec = p1 - p0
    dist = float(np.hypot(gap_vec[0], gap_vec[1]))
    if dist <= 1.6:
        return np.vstack([left, right[1:]])
    if dist > JOIN_MAX_GAP:
        return None
    chord = gap_vec / dist
    turn_l = _angle_deg(t_left, chord)
    turn_r = _angle_deg(chord, t_right)
    overall_l = left[-1] - left[0]
    overall_r = right[-1] - right[0]
    ol_n = float(np.hypot(*overall_l))
    or_n = float(np.hypot(*overall_r))
    mild_strip = (
        ol_n > 12.0
        and or_n > 12.0
        and _angle_deg(overall_l / ol_n, chord) <= 24.0
        and _angle_deg(chord, overall_r / or_n) <= 24.0
        and dist <= 22.0
    )
    if turn_l > JOIN_MAX_TURN_DEG or turn_r > JOIN_MAX_TURN_DEG:
        if not mild_strip:
            return None
    if _angle_deg(t_left, t_right) > JOIN_MAX_TURN_DEG + 8.0 and not mild_strip:
        return None
    ray = p0 + t_left * JOIN_RAY_PX
    other_ray = p1 + t_right_out * JOIN_RAY_PX
    along = float(np.dot(p1 - p0, t_left))
    closest = p0 + t_left * float(np.clip(along, 0.0, JOIN_RAY_PX + 8.0))
    near = min(
        float(np.hypot(*(ray - p1))),
        float(np.hypot(*(other_ray - p0))),
        float(np.hypot(*(closest - p1))),
    )
    if near > JOIN_END_PX and (turn_l > 16.0 or turn_r > 16.0):
        return None
    if turn_l <= 14.0 and turn_r <= 14.0:
        mid = np.linspace(p0, p1, max(3, int(round(dist / 4.0))))[1:-1]
    else:
        bridge = _hermite_bridge(p0, t_left, p1, t_right)
        mid = np.asarray(bridge, dtype=np.float32) if bridge else np.zeros((0, 2), dtype=np.float32)
    if len(mid):
        return np.vstack([left, mid, right])
    return np.vstack([left, right])


def stitch_interface_runs(runs: list[list[list[float]]]) -> list[list[list[float]]]:
    """Extrapolate each end along its tangent and interpolate if another end is close."""
    polys = [np.asarray(run, dtype=np.float32) for run in runs if len(run) >= 2]
    changed = True
    while changed and len(polys) > 1:
        changed = False
        best = None
        for i, one in enumerate(polys):
            for j, two in enumerate(polys):
                if i == j:
                    continue
                variants = (
                    (one, two),
                    (one, two[::-1]),
                    (one[::-1], two),
                    (one[::-1], two[::-1]),
                )
                for left, right in variants:
                    joined = try_join_runs(left, right)
                    if joined is None:
                        continue
                    dist = float(np.hypot(*(left[-1] - right[0])))
                    if best is None or dist < best[0]:
                        best = (dist, i, j, joined)
        if best is None:
            break
        _dist, i, j, joined = best
        polys = [poly for idx, poly in enumerate(polys) if idx not in {i, j}]
        polys.append(joined)
        changed = True
    out = []
    for poly in polys:
        if len(poly) < 4:
            continue
        curve = gentle_curve(poly)
        if len(curve) < 4:
            continue
        step = np.hypot(np.diff(curve[:, 0]), np.diff(curve[:, 1]))
        if float(step.sum()) < 16.0:
            continue
        out.append(curve.tolist())
    return out


def reject_across_outliers(
    xy: np.ndarray,
    along: np.ndarray,
    across: np.ndarray | None,
    win: int = 11,
    max_dev: float = ACROSS_OUTLIER,
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    """Drop sudden across spikes. A local hook toward the mass should not bend the strip."""
    if across is None or len(xy) < 5:
        return xy, along, across
    med = _finite_median_filter(np.asarray(across, dtype=np.float32), win)
    keep = np.abs(np.asarray(across, dtype=np.float32) - med) <= max_dev
    if int(keep.sum()) < 4:
        return xy, along, across
    next_ac = np.asarray(across, dtype=np.float32)[keep]
    return xy[keep], along[keep], next_ac


def _split_interface_runs(points: list[list[float]]) -> list[list[list[float]]]:
    """Split only on real heading gaps, then smooth each fragment vs along-index."""
    if len(points) < 3:
        return []
    arr = np.asarray(points, dtype=np.float32)
    xy = arr[:, :2].copy()
    along = arr[:, 3] if arr.shape[1] >= 4 else np.arange(len(arr), dtype=np.float32)
    across = arr[:, 2] if arr.shape[1] >= 3 else None
    order = np.argsort(along)
    xy = xy[order]
    along = np.asarray(along, dtype=np.float32)[order]
    if across is not None:
        across = np.asarray(across, dtype=np.float32)[order]
    xy, along, across = reject_across_outliers(xy, along, across)
    for axis in (0, 1):
        xy[:, axis] = _finite_median_filter(xy[:, axis], 7)
    if across is not None:
        across = _finite_median_filter(across, 7)
    starts = [0]
    for i in range(1, len(xy)):
        da = float(along[i] - along[i - 1])
        dxy = float(np.hypot(*(xy[i] - xy[i - 1])))
        if da > SPLIT_ALONG or dxy > SPLIT_XY_PX:
            starts.append(i)
    starts.append(len(xy))
    cleaned: list[list[list[float]]] = []
    for a, b in zip(starts[:-1], starts[1:]):
        if b - a < 3:
            continue
        sm = gentle_curve(xy[a:b], along[a:b])
        if len(sm) >= 4:
            cleaned.append(sm.tolist())
    return stitch_interface_runs(cleaned)


def trace_gray_interfaces(
    samples: dict[str, np.ndarray],
    keep: np.ndarray,
    prefer_across: list[float] | None = None,
) -> list[dict[str, Any]]:
    """Thin bright/dark gray boundaries along the heading, snapped to real gradients."""
    xs = samples["xs"]
    ys = samples["ys"]
    gray = samples["gray"]
    across = samples["across"]
    along = samples["along_idx"]
    seeds = [float(v) for v in (prefer_across or []) if np.isfinite(v)]
    raw: list[list[list[float]]] = [[], []] if len(seeds) < 2 else [[] for _ in seeds]
    if not raw:
        raw = [[], []]
    for along_id, pix in _along_windows(along, keep, radius=2, min_pix=5):
        peaks = _column_gray_peaks(xs, ys, gray, across, pix)
        if not peaks:
            continue
        if seeds:
            used: set[int] = set()
            taken_ac: list[float] = []
            for slot, seed in enumerate(seeds[: len(raw)]):
                cand = []
                for i, p in enumerate(peaks):
                    if i in used or abs(p["across"] - seed) > 0.38:
                        continue
                    if any(abs(p["across"] - ac) < MIN_ACROSS_SEP for ac in taken_ac):
                        continue
                    cand.append((abs(p["across"] - seed), i, p))
                if not cand:
                    continue
                _d, idx, peak = min(cand, key=lambda item: item[0])
                used.add(idx)
                taken_ac.append(peak["across"])
                raw[slot].append([peak["x"], peak["y"], peak["across"], along_id])
            continue
        falling = [p for p in peaks if p["grad"] < 0]
        rising = [p for p in peaks if p["grad"] > 0]
        if falling:
            fall = max(falling, key=lambda p: p["mag"])
            raw[0].append([fall["x"], fall["y"], fall["across"], along_id])
            rising = [p for p in rising if p["across"] > fall["across"] + MIN_ACROSS_SEP]
        if rising:
            rise = max(rising, key=lambda p: p["mag"])
            raw[1].append([rise["x"], rise["y"], rise["across"], along_id])
    out = []
    for edge, pts in enumerate(raw):
        for run in _split_interface_runs(pts):
            out.append({"edge": edge, "points": run})
    return out


def _along_windows(
    along: np.ndarray,
    keep: np.ndarray,
    radius: int = 2,
    min_pix: int = 5,
) -> list[tuple[float, np.ndarray]]:
    """One heading station at a time, with a small neighbor window for a stable 1D profile."""
    stations = np.unique(along[keep]) if keep.any() else np.array([], dtype=np.int32)
    out: list[tuple[float, np.ndarray]] = []
    for i, st in enumerate(stations.tolist()):
        lo = max(0, i - radius)
        hi = min(len(stations), i + radius + 1)
        pix = keep & np.isin(along, stations[lo:hi])
        if int(pix.sum()) < min_pix:
            continue
        out.append((float(st), pix))
    return out


def merge_along_columns(along: np.ndarray, keep: np.ndarray, min_pix: int = STRIP_MIN_COL) -> list[np.ndarray]:
    stations = np.unique(along[keep]) if keep.any() else np.unique(along)
    groups: list[list[int]] = []
    current: list[int] = []
    count = 0
    for st in stations.tolist():
        n = int(((along == st) & keep).sum())
        current.append(int(st))
        count += n
        if count >= min_pix:
            groups.append(current)
            current = []
            count = 0
    if current:
        if groups:
            groups[-1].extend(current)
        else:
            groups.append(current)
    return [np.asarray(g, dtype=np.int32) for g in groups]


def _finite_median_filter(values: np.ndarray, win: int) -> np.ndarray:
    out = values.copy()
    ok = np.isfinite(out)
    if int(ok.sum()) == 0:
        return out
    idx = np.arange(len(out))
    filled = np.interp(idx, idx[ok], out[ok])
    radius = max(1, win // 2)
    smooth = filled.copy()
    for i in range(len(filled)):
        lo = max(0, i - radius)
        hi = min(len(filled), i + radius + 1)
        smooth[i] = float(np.median(filled[lo:hi]))
    return smooth.astype(np.float32)


def _feature_axis(feat: np.ndarray, across: np.ndarray) -> np.ndarray:
    feat = np.asarray(feat, dtype=np.float32)
    if feat.ndim == 1 or feat.shape[1] == 1:
        return feat.reshape(-1)
    inner = across <= np.quantile(across, 0.35)
    outer = across >= np.quantile(across, 0.65)
    if int(inner.sum()) < 8 or int(outer.sum()) < 8:
        return feat[:, 0]
    axis = feat[outer].mean(axis=0) - feat[inner].mean(axis=0)
    norm = float(np.linalg.norm(axis)) or 1.0
    return (feat @ (axis / norm)).astype(np.float32)


def refine_across_cut(across: np.ndarray, values: np.ndarray, seed: float, max_shift: float = 0.16) -> float:
    best = float(seed)
    best_score = -1.0
    for trial in np.linspace(seed - max_shift, seed + max_shift, 13):
        left = values[across < trial]
        right = values[across >= trial]
        if len(left) < 4 or len(right) < 4:
            continue
        score = abs(float(left.mean()) - float(right.mean()))
        if score > best_score:
            best_score = score
            best = float(trial)
    return best


def _pad_cut_span(
    i: int,
    j: int,
    n: int,
    pad: int = GRAY_CUT_PAD,
    sm: np.ndarray | None = None,
) -> tuple[int, int]:
    """Grow the middle only while gray still looks like the mid band, up to pad px."""
    i = int(i)
    j = int(j)
    if sm is None or j <= i:
        grow = min(int(pad), max(0, i - 2), max(0, n - 2 - j))
        return max(2, i - grow), min(n - 2, j + grow)
    mid_mu = float(sm[i:j].mean())
    left_mu = float(sm[:i].mean()) if i > 0 else mid_mu
    right_mu = float(sm[j:].mean()) if j < n else mid_mu
    gap_l = max(3.0, abs(mid_mu - left_mu) * 0.35)
    gap_r = max(3.0, abs(mid_mu - right_mu) * 0.35)
    start, end = i, j
    while start > 2 and (i - start) < pad and abs(float(sm[start - 1]) - mid_mu) <= gap_l:
        start -= 1
    while end < n - 2 and (end - j) < pad and abs(float(sm[end]) - mid_mu) <= gap_r:
        end += 1
    return start, end


def _default_tertile(n: int, overlap: tuple[int, int] | None) -> tuple[int, int]:
    if overlap is None:
        return max(1, n // 3), min(n - 1, max(2, 2 * n // 3))
    lo, hi = int(overlap[0]), int(overlap[1])
    span = max(3, hi - lo)
    return lo + span // 3, lo + max(span // 3 + 1, 2 * span // 3)


def _best_gray_splits(
    gray: np.ndarray,
    overlap: tuple[int, int] | None = None,
) -> tuple[float, float, tuple[int, int] | None, tuple[int, int] | None]:
    """Score every pair of cuts: dark-bright-dark versus bright-dark-bright."""
    sm = _smooth1d(np.asarray(gray, dtype=np.float32), 1)
    n = int(len(sm))
    best_dbd = -1.0e9
    best_bdb = -1.0e9
    dbd_ij: tuple[int, int] | None = None
    bdb_ij: tuple[int, int] | None = None
    lo, hi = (0, n) if overlap is None else (int(overlap[0]), int(overlap[1]))

    def _ov(a0: int, a1: int) -> int:
        return max(0, min(a1, hi) - max(a0, lo))

    for i in range(2, n - 3):
        for j in range(i + 2, n - 1):
            if overlap is not None and (_ov(0, i) < 2 or _ov(i, j) < 2 or _ov(j, n) < 2):
                continue
            if overlap is None:
                left = float(sm[:i].mean())
                mid = float(sm[i:j].mean())
                right = float(sm[j:].mean())
            else:
                left_g = sm[lo:min(i, hi)]
                mid_g = sm[max(i, lo):min(j, hi)]
                right_g = sm[max(j, lo):hi]
                if len(left_g) < 1 or len(mid_g) < 2 or len(right_g) < 1:
                    continue
                left = float(left_g.mean())
                mid = float(mid_g.mean())
                right = float(right_g.mean())
            width_term = 1.0 + 0.08 * min(float(j - i), 12.0)
            dbd = (mid - 0.5 * (left + right)) * width_term
            bdb = (0.5 * (left + right) - mid) * width_term
            if dbd > best_dbd:
                best_dbd = dbd
                dbd_ij = (i, j)
            if bdb > best_bdb:
                best_bdb = bdb
                bdb_ij = (i, j)
    return best_dbd, best_bdb, dbd_ij, bdb_ij


def _band_cuts_1d(
    gray: np.ndarray,
    prefer: str | None = None,
    overlap: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """Split one column on the strongest gray contrast that overlaps the wall."""
    n = int(len(gray))
    tertile = _default_tertile(n, overlap)
    if n < 8:
        return tertile
    best_dbd, best_bdb, dbd_ij, bdb_ij = _best_gray_splits(gray, overlap)
    if prefer == "dbd":
        score, pick = best_dbd, dbd_ij
    elif prefer == "bdb":
        score, pick = best_bdb, bdb_ij
    else:
        dbd_w = float(dbd_ij[1] - dbd_ij[0]) if dbd_ij else 1.0
        bdb_w = float(bdb_ij[1] - bdb_ij[0]) if bdb_ij else 1.0
        if dbd_ij is not None and (bdb_ij is None or (best_dbd * dbd_w) >= (best_bdb * bdb_w)):
            score, pick = best_dbd, dbd_ij
        else:
            score, pick = best_bdb, bdb_ij
    if pick is None or score < GRAY_CUT_MIN_SCORE:
        return tertile
    sm = _smooth1d(np.asarray(gray, dtype=np.float32), 1)
    i, j = _pad_cut_span(int(pick[0]), int(pick[1]), n, sm=sm)
    if j <= i + 1:
        return tertile
    return i, j


def _column_pattern_vote(
    gray: np.ndarray,
    overlap: tuple[int, int] | None = None,
) -> str | None:
    if int(len(gray)) < 8:
        return None
    best_dbd, best_bdb, dbd_ij, bdb_ij = _best_gray_splits(gray, overlap)
    if dbd_ij is None and bdb_ij is None:
        return None
    if best_dbd < GRAY_CUT_MIN_SCORE and best_bdb < GRAY_CUT_MIN_SCORE:
        return None
    dbd_w = float(dbd_ij[1] - dbd_ij[0]) if dbd_ij else 1.0
    bdb_w = float(bdb_ij[1] - bdb_ij[0]) if bdb_ij else 1.0
    return "dbd" if (best_dbd * dbd_w) >= (best_bdb * bdb_w) else "bdb"


def _column_search_profile(
    image: np.ndarray,
    x: int,
    y_min: int,
    y_max: int,
    search_pad: int = GRAY_SEARCH_PAD,
    blocked: np.ndarray | None = None,
) -> tuple[np.ndarray, int, int, int]:
    """Gray column around the brush, plus about 12 px above and below."""
    height, width = int(image.shape[0]), int(image.shape[1])
    x = int(np.clip(x, 0, width - 1))
    y0 = max(0, int(y_min) - int(search_pad))
    y1 = min(height - 1, int(y_max) + int(search_pad))
    profile = np.asarray(image[y0:y1 + 1, x], dtype=np.float32).reshape(-1)
    if blocked is not None and blocked.shape[:2] == image.shape[:2]:
        hit = np.asarray(blocked[y0:y1 + 1, x]) > 0
        if bool(hit.any()) and bool((~hit).any()):
            good = np.where(~hit)[0]
            bad = np.where(hit)[0]
            nearest = good[np.abs(bad[:, None] - good[None, :]).argmin(axis=1)]
            profile = profile.copy()
            profile[bad] = profile[nearest]
    brush_lo = int(y_min) - y0
    brush_hi = int(y_max) - y0 + 1
    brush_lo = max(0, brush_lo)
    brush_hi = min(len(profile), max(brush_lo + 2, brush_hi))
    brush = profile[brush_lo:brush_hi]
    if len(brush) >= 3:
        med = float(np.median(brush))
        near = np.abs(profile - med) <= 32.0
        near[brush_lo:brush_hi] = True
        start = 0
        while start < brush_lo and not bool(near[start]):
            start += 1
        end = len(profile) - 1
        while end >= brush_hi and not bool(near[end]):
            end -= 1
        if start > 0 or end < len(profile) - 1:
            profile = profile[start:end + 1]
            y0 += start
            brush_lo -= start
            brush_hi -= start
    return profile, y0, brush_lo, brush_hi


def _fill_nan_1d(values: np.ndarray) -> np.ndarray:
    out = np.asarray(values, dtype=np.float32).copy()
    good = np.isfinite(out)
    if int(good.sum()) == 0:
        return np.zeros_like(out)
    if bool(good.all()):
        return out
    idx = np.arange(len(out))
    out[~good] = np.interp(idx[~good], idx[good], out[good])
    return out


def _heading_stations(
    polyline: np.ndarray,
    lumen_center: np.ndarray | None,
    lesion_center: np.ndarray | None,
    deepest: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Densified heading points and unit normals (same flip as sample_band_pixels)."""
    poly = densify_polyline(as_xy(polyline), 3.0)
    if len(poly) < 2:
        empty = np.zeros((0, 2), dtype=np.float32)
        return empty, empty
    tangents = np.zeros_like(poly)
    tangents[:-1] = poly[1:] - poly[:-1]
    tangents[-1] = tangents[-2]
    tan_n = np.maximum(np.hypot(tangents[:, 0], tangents[:, 1]), 1e-6)
    tangent = tangents / tan_n[:, None]
    normals = np.stack([-tangent[:, 1], tangent[:, 0]], axis=1)
    if lumen_center is not None:
        hint = poly - np.asarray(lumen_center, dtype=np.float32).reshape(1, 2)
    elif deepest is not None and lesion_center is not None:
        hint = np.broadcast_to(
            (np.asarray(deepest) - np.asarray(lesion_center)).astype(np.float32),
            normals.shape,
        )
    elif lesion_center is not None:
        hint = poly - np.asarray(lesion_center, dtype=np.float32).reshape(1, 2)
    else:
        hint = None
    if hint is not None:
        flip = np.sum(normals * hint, axis=1) < 0
        normals[flip] *= -1
    # +across goes down the image so label 0 stays on top.
    if len(normals) and float(normals[:, 1].mean()) < 0:
        normals = -normals
    return poly.astype(np.float32), normals.astype(np.float32)


def _sample_normal_profile(
    image: np.ndarray,
    origin: np.ndarray,
    normal: np.ndarray,
    half: int,
    blocked: np.ndarray | None = None,
) -> np.ndarray:
    height, width = int(image.shape[0]), int(image.shape[1])
    vals = np.full((2 * int(half) + 1,), np.nan, dtype=np.float32)
    for i, dist in enumerate(range(-int(half), int(half) + 1)):
        point = origin + normal * float(dist)
        x = int(round(float(point[0])))
        y = int(round(float(point[1])))
        if 0 <= x < width and 0 <= y < height:
            if blocked is not None and blocked[y, x] > 0:
                continue
            vals[i] = float(image[y, x])
    return _fill_nan_1d(vals)


def _gradient_two_cuts(
    profile: np.ndarray,
    prefer: str | None = None,
    overlap: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """Snap two cuts to the strongest gray jumps on one normal profile."""
    sm = _smooth1d(_fill_nan_1d(profile), 2)
    n = int(len(sm))
    tertile = _default_tertile(n, overlap)
    if n < 10:
        return tertile
    grad = np.abs(np.diff(sm))
    cands: list[tuple[float, int]] = []
    for i in range(2, n - 3):
        if grad[i] >= grad[i - 1] and grad[i] >= grad[i + 1] and grad[i] >= MIN_GRAD:
            cands.append((float(grad[i]), i + 1))
    lo, hi = (0, n) if overlap is None else (int(overlap[0]), int(overlap[1]))

    def _ov(a0: int, a1: int) -> int:
        return max(0, min(a1, hi) - max(a0, lo))

    if len(cands) < 2:
        return _band_cuts_1d(sm, prefer=prefer, overlap=overlap)
    best: tuple[float, int, int] | None = None
    for a in range(len(cands)):
        for b in range(a + 1, len(cands)):
            i, j = cands[a][1], cands[b][1]
            if i > j:
                i, j = j, i
            if j - i < MIN_CUT_SEP:
                continue
            if overlap is not None and (_ov(0, i) < 2 or _ov(i, j) < 2 or _ov(j, n) < 2):
                continue
            left = float(sm[max(lo, 0):max(lo + 1, min(i, hi))].mean()) if overlap is not None else float(sm[:i].mean())
            mid = float(sm[max(i, lo):min(j, hi)].mean()) if overlap is not None else float(sm[i:j].mean())
            right = float(sm[max(j, lo):hi].mean()) if overlap is not None else float(sm[j:].mean())
            dbd = mid - 0.5 * (left + right)
            bdb = 0.5 * (left + right) - mid
            if prefer == "dbd":
                score = dbd
            elif prefer == "bdb":
                score = bdb
            else:
                score = max(dbd, bdb)
            score = score + 0.20 * (cands[a][0] + cands[b][0])
            if best is None or score > best[0]:
                best = (score, i, j)
    if best is None or best[0] < GRAY_CUT_MIN_SCORE:
        return _band_cuts_1d(sm, prefer=prefer, overlap=overlap)
    return int(best[1]), int(best[2])


def assign_across_gray_bands(
    samples: dict[str, np.ndarray],
    keep: np.ndarray,
    assign_lesion: bool,
    k: int,
    image: np.ndarray,
    wall: np.ndarray,
    brush_radius: float,
    blocked: np.ndarray | None = None,
    lumen_center: np.ndarray | None = None,
    lesion_center: np.ndarray | None = None,
    deepest: np.ndarray | None = None,
) -> np.ndarray:
    """Split the brush on gray jumps along the heading normal.

    The eye sees layers parallel to the heading. Image-y columns cut those
    stripes at an angle and miss the obvious bright / dark bands.
    """
    xs = samples["xs"]
    ys = samples["ys"]
    labels = np.full((len(xs),), -1, dtype=np.int32)
    if int(keep.sum()) < MIN_VALID_PIXELS or k < 2:
        return labels
    pts, normals = _heading_stations(wall, lumen_center, lesion_center, deepest)
    if len(pts) < 3:
        return labels
    half = int(ACROSS_SEARCH_PX)
    rows = np.stack([
        _sample_normal_profile(image, pts[i], normals[i], half, blocked)
        for i in range(len(pts))
    ])
    win = max(3, int(ALONG_AVG))
    avg = np.zeros_like(rows)
    for i in range(len(pts)):
        lo = max(0, i - win // 2)
        hi = min(len(pts), i + win // 2 + 1)
        avg[i] = np.mean(rows[lo:hi], axis=0)
    radius = max(1.0, float(brush_radius))
    overlap = (max(0, half - int(round(radius))), min(2 * half + 1, half + int(round(radius)) + 1))
    vote_sel = np.where(pts[:, 0] >= float(np.quantile(pts[:, 0], 0.55)))[0]
    if len(vote_sel) < 5:
        vote_sel = np.arange(len(pts))

    def _mid_side(row: np.ndarray, pref: str) -> float:
        gi, gj = _gradient_two_cuts(row, prefer=pref, overlap=overlap)
        lo, hi = overlap
        if gi < lo + 2 or gj > hi - 2:
            return -1.0
        mid = float(row[gi:max(gi + 1, gj)].mean())
        sides = 0.5 * (float(row[:gi].mean()) + float(row[gj:].mean()))
        return (mid - sides) if pref == "dbd" else (sides - mid)

    dbd_c = float(np.mean([_mid_side(avg[i], "dbd") for i in vote_sel.tolist()]))
    bdb_c = float(np.mean([_mid_side(avg[i], "bdb") for i in vote_sel.tolist()]))
    prefer = "dbd" if dbd_c >= bdb_c else "bdb"
    raw1 = []
    raw2 = []
    for row in avg:
        if k == 2:
            i, j = max(1, len(row) // 2), len(row)
        else:
            i, j = _gradient_two_cuts(row, prefer=prefer, overlap=overlap)
        raw1.append(float(i - half))
        raw2.append(float(max(i, j - 1) - half))
    sm1 = _finite_median_filter(np.asarray(raw1, dtype=np.float32), STRIP_SMOOTH)
    sm2 = _finite_median_filter(np.asarray(raw2, dtype=np.float32), STRIP_SMOOTH)
    sm1 = _smooth1d(sm1, 2)
    sm2 = _smooth1d(sm2, 2)
    for i in range(len(sm2)):
        if sm2[i] <= sm1[i] + 1.0:
            sm2[i] = sm1[i] + 1.5
    paint = keep
    core_sel = keep & (np.abs(samples["across"]) <= 0.50)
    if int(core_sel.sum()) >= 12:
        floor = float(np.percentile(samples["gray"][core_sel], 12)) - 14.0
        paint = keep & (samples["gray"] >= floor)
    pix = np.stack([xs.astype(np.float32), ys.astype(np.float32)], axis=1)
    d2 = ((pix[:, None, :] - pts[None, :, :]) ** 2).sum(axis=2)
    nearest = np.argmin(d2, axis=1)
    signed = np.sum((pix - pts[nearest]) * normals[nearest], axis=1)
    for i in np.where(paint)[0].tolist():
        a1 = float(sm1[int(nearest[i])])
        a2 = float(sm2[int(nearest[i])])
        si = float(signed[i])
        if k == 2:
            labels[i] = 0 if si < a1 else 1
        elif si < a1:
            labels[i] = 0
        elif si > a2:
            labels[i] = 2
        else:
            labels[i] = 1
    if assign_lesion:
        for i in np.where(~keep)[0].tolist():
            a1 = float(sm1[int(nearest[i])])
            a2 = float(sm2[int(nearest[i])])
            si = float(signed[i])
            labels[i] = 0 if si < a1 else (2 if si > a2 else 1)
    return labels


def assign_natural_y_bands(
    samples: dict[str, np.ndarray],
    keep: np.ndarray,
    assign_lesion: bool,
    k: int,
    image: np.ndarray | None = None,
    blocked: np.ndarray | None = None,
    wall: np.ndarray | None = None,
    brush_radius: float = DEFAULT_BRUSH,
    lumen_center: np.ndarray | None = None,
    lesion_center: np.ndarray | None = None,
    deepest: np.ndarray | None = None,
) -> np.ndarray:
    """Split brush pixels into three exclusive bands along wall thickness."""
    if image is not None and wall is not None and len(np.asarray(wall)) >= 2:
        return assign_across_gray_bands(
            samples, keep, assign_lesion, k, image, wall, brush_radius,
            blocked=blocked, lumen_center=lumen_center,
            lesion_center=lesion_center, deepest=deepest,
        )
    xs = samples["xs"]
    ys = samples["ys"]
    gray = samples["gray"].astype(np.float32)
    labels = np.full((len(xs),), -1, dtype=np.int32)
    if int(keep.sum()) < MIN_VALID_PIXELS or k < 2:
        return labels
    across = samples["across"]
    core = keep & (np.abs(across) <= 0.92)
    if int(core.sum()) < MIN_VALID_PIXELS:
        core = keep
    stations = np.unique(xs[core])
    cols: list[tuple[int, np.ndarray, np.ndarray, int, int, int]] = []
    votes: list[str] = []
    for x in stations.tolist():
        pix = np.where(core & (xs == x))[0]
        if len(pix) < 4:
            continue
        idx = pix[np.argsort(ys[pix])]
        y_min = int(ys[idx[0]])
        y_max = int(ys[idx[-1]])
        profile = gray[idx].astype(np.float32)
        y0 = y_min
        cols.append((int(x), idx, profile, y0, y_min, y_max))
        kind = _column_pattern_vote(profile)
        if kind:
            votes.append(kind)
    prefer = None
    if votes:
        prefer = "dbd" if votes.count("dbd") >= votes.count("bdb") else "bdb"
    raw1 = []
    raw2 = []
    used = []
    for _col_i, (x, idx, profile, y0, y_min, y_max) in enumerate(cols):
        if k == 2:
            i = max(1, len(profile) // 2)
            j = len(profile)
        else:
            i, j = _band_cuts_1d(profile, prefer=prefer)
        y1 = float(ys[idx[i]]) if i < len(idx) else float(ys[idx[-1]])
        y2 = float(ys[idx[min(j, len(idx) - 1)]])
        if y2 <= y1 + 0.6:
            y2 = y1 + 1.0
        raw1.append(y1)
        raw2.append(y2)
        used.append(int(x))
    if len(used) < 3:
        return labels
    sm1 = _finite_median_filter(np.asarray(raw1, dtype=np.float32), STRIP_SMOOTH)
    sm2 = _finite_median_filter(np.asarray(raw2, dtype=np.float32), STRIP_SMOOTH)
    sm1 = _smooth1d(sm1, 2)
    sm2 = _smooth1d(sm2, 2)
    for i in range(len(sm2)):
        if sm2[i] <= sm1[i] + 0.8:
            sm2[i] = sm1[i] + 1.0
    y1_at = np.interp(stations.astype(np.float32), np.asarray(used, dtype=np.float32), sm1)
    y2_at = np.interp(stations.astype(np.float32), np.asarray(used, dtype=np.float32), sm2)
    by_x = {int(x): (float(a), float(b)) for x, a, b in zip(stations.tolist(), y1_at.tolist(), y2_at.tolist())}
    for i in np.where(core)[0].tolist():
        cuts = by_x.get(int(xs[i]))
        if cuts is None:
            continue
        y1, y2 = cuts
        yi = float(ys[i])
        if k == 2:
            labels[i] = 0 if yi < y1 else 1
        elif yi < y1:
            labels[i] = 0
        elif yi > y2:
            labels[i] = 2
        else:
            labels[i] = 1
    if assign_lesion:
        for i in np.where(~keep)[0].tolist():
            cuts = by_x.get(int(xs[i]))
            if cuts is None:
                continue
            y1, y2 = cuts
            yi = float(ys[i])
            labels[i] = 0 if yi < y1 else (2 if yi > y2 else 1)
    return labels


def interfaces_from_y_bands(
    samples: dict[str, np.ndarray],
    labels: np.ndarray,
    keep: np.ndarray,
) -> list[dict[str, Any]]:
    """Thin edges where the three y-bands meet. Yellow and green cannot cross."""
    xs = samples["xs"]
    ys = samples["ys"]
    labels = np.asarray(labels, dtype=np.int32)
    raw: list[list[list[float]]] = [[], []]
    for x in np.unique(xs[keep]).tolist():
        pix = keep & (xs == x) & (labels >= 0)
        if int(pix.sum()) < 4:
            continue
        order = np.argsort(ys[pix])
        labs = labels[pix][order]
        yy = ys[pix][order].astype(np.float32)
        xx = xs[pix][order].astype(np.float32)
        for edge, left, right in ((0, 0, 1), (1, 1, 2)):
            hit = np.where((labs[:-1] == left) & (labs[1:] == right))[0]
            if len(hit) == 0:
                continue
            i = int(hit[0])
            raw[edge].append([
                float(xx[i]),
                0.5 * (float(yy[i]) + float(yy[i + 1])),
                0.0,
                float(x),
            ])
    out = []
    for edge, pts in enumerate(raw):
        for run in _split_interface_runs(pts):
            out.append({"edge": edge, "points": run})
    return out


def assign_strip_layers(
    samples: dict[str, np.ndarray],
    keep: np.ndarray,
    fit: np.ndarray,
    features: np.ndarray,
    k: int,
    assign_lesion: bool,
    image: np.ndarray | None = None,
    blocked: np.ndarray | None = None,
    wall: np.ndarray | None = None,
    brush_radius: float = DEFAULT_BRUSH,
    lumen_center: np.ndarray | None = None,
    lesion_center: np.ndarray | None = None,
    deepest: np.ndarray | None = None,
) -> np.ndarray:
    """Three exclusive bands along wall thickness."""
    del fit, features
    return assign_natural_y_bands(
        samples, keep, assign_lesion, k, image=image, blocked=blocked,
        wall=wall, brush_radius=brush_radius, lumen_center=lumen_center,
        lesion_center=lesion_center, deepest=deepest,
    )


def cluster_brush_band(
    gray: np.ndarray,
    wall: np.ndarray,
    lesion_mask: np.ndarray,
    *,
    brush_radius: float = DEFAULT_BRUSH,
    k: int = 3,
    dilate_px: int = 0,
    exclude_lesion: bool = True,
    method: str = "kmeans",
    lumen_center: np.ndarray | None = None,
    lesion_poly: np.ndarray | None = None,
    cavity_side_source: str = "heuristic",
    fit_side: str = "all",
    assign_lesion: bool = True,
    sensitive: bool = False,
    extra_features: np.ndarray | None = None,
    prefer_strips: bool = False,
    label_pad_px: float | None = None,
) -> ClusterArm:
    method = str(method or "kmeans").strip().lower()
    fit_side = str(fit_side or "all").strip().lower()
    if extra_features is not None:
        sensitive = False
        if method in {"kmeans", "kmeans1d_gray", "kmeans1d_across"}:
            method = "dino_pca"
    if prefer_strips:
        sensitive = False
    name = f"{'exclude' if exclude_lesion else 'full'}_{method}_k{k}_d{dilate_px}_{fit_side}"
    if sensitive:
        name += "_sensitive"
    if prefer_strips:
        name += "_strips"
    wall = densify_polyline(as_xy(wall), 3.0)
    lesion_pts = as_xy(lesion_poly) if lesion_poly is not None else np.zeros((0, 2), dtype=np.float32)
    lesion_center = polygon_centroid(lesion_pts)
    deepest = None
    if len(lesion_pts) >= 2 and lesion_center is not None:
        deepest = lesion_pts[int(np.argmax(np.linalg.norm(lesion_pts - lesion_center, axis=1)))]
    if lumen_center is not None:
        cavity_side_source = "lumen"
    if label_pad_px is None:
        label_pad_px = 0.0
    sample_radius = float(brush_radius) + float(label_pad_px)
    brush = rasterize_brush(gray.shape, wall, sample_radius)
    lesion_d = dilate_mask(lesion_mask, dilate_px) if exclude_lesion else np.zeros_like(lesion_mask)
    valid_mask = brush.copy()
    if exclude_lesion:
        valid_mask[lesion_d > 0] = 0
    flanks = split_flank_segments(wall, lesion_d if exclude_lesion else np.zeros_like(lesion_mask))
    samples = sample_band_pixels(gray, brush, wall, sample_radius, lumen_center, lesion_center, deepest)
    if exclude_lesion:
        keep = lesion_d[samples["ys"], samples["xs"]] == 0
    else:
        keep = np.ones(len(samples["xs"]), dtype=bool)
    n_valid = int(keep.sum())
    max_arc = max((float(seg["arc_px"]) for seg in flanks), default=0.0)
    if n_valid < MIN_VALID_PIXELS or (exclude_lesion and max_arc < MIN_FLANK_ARC_PX):
        return ClusterArm(
            name=name,
            status=INSUFFICIENT,
            k=k,
            method=method,
            n_pixels=int(len(samples["xs"])),
            n_valid=n_valid,
            dilate_px=dilate_px,
            cavity_side_source=cavity_side_source,
            pattern="",
            bright_dark_bright=False,
            skip_reason=INSUFFICIENT,
            flanks=flanks,
        )

    if extra_features is not None:
        feat_all = np.asarray(extra_features, dtype=np.float32)
        if feat_all.ndim == 1:
            feat_all = feat_all.reshape(-1, 1)
        if len(feat_all) != len(samples["xs"]):
            raise ValueError("extra_features length must match sampled brush pixels")
        cluster_method = "kmeans" if method == "dino_pca" else method
    else:
        feat_all = features_for_method(samples, method)
        cluster_method = method
    fit = keep.copy()
    if fit_side in {"right", "left"} and keep.any():
        xs_keep = samples["xs"][keep].astype(np.float32)
        cut = float(np.quantile(xs_keep, 0.42 if fit_side == "right" else 0.58))
        if fit_side == "right":
            fit = keep & (samples["xs"] >= cut)
        else:
            fit = keep & (samples["xs"] <= cut)
        if int(fit.sum()) < MIN_VALID_PIXELS:
            fit = keep
    if prefer_strips and k >= 2:
        labels_all = assign_strip_layers(
            samples, keep, fit, feat_all, k, assign_lesion,
            image=gray, blocked=lesion_d if exclude_lesion else None,
            wall=wall, brush_radius=sample_radius, lumen_center=lumen_center,
            lesion_center=lesion_center, deepest=deepest,
        )
        labels_fit = labels_all[keep]
    elif sensitive:
        labels_all, labels_fit = assign_sensitive_layers(
            samples, keep, fit, k, assign_lesion, gray.shape,
        )
    else:
        feat_fit = feat_all[fit]
        labels_seed, centers = cluster_features(feat_fit, k, cluster_method)
        order = np.argsort([
            float(samples["across"][fit][labels_seed == lab].mean()) if np.any(labels_seed == lab) else 0.0
            for lab in range(k)
        ])
        remap = {int(old): int(new) for new, old in enumerate(order.tolist())}
        labels_seed = np.array([remap[int(lab)] for lab in labels_seed], dtype=np.int32)
        labels_seed = majority_vote_sparse(samples["xs"][fit], samples["ys"][fit], labels_seed, gray.shape)

        # Fit on the seed side only. Other normal-wall pixels follow those gray centers.
        # Lesion pixels stay unlabeled when assign_lesion is false, so the bands interrupt.
        labels_all = np.full(len(samples["xs"]), -1, dtype=np.int32)
        labels_all[fit] = labels_seed
        if len(centers) >= k:
            ordered_centers = centers[order]
            follow = keep & ~fit
            if follow.any():
                d2 = ((feat_all[follow, None, :] - ordered_centers[None, :, :]) ** 2).sum(axis=2)
                labels_all[follow] = np.argmin(d2, axis=1).astype(np.int32)
            rest = ~keep
            if assign_lesion and rest.any():
                d2 = ((feat_all[rest, None, :] - ordered_centers[None, :, :]) ** 2).sum(axis=2)
                labels_all[rest] = np.argmin(d2, axis=1).astype(np.int32)
        labels_fit = labels_all[keep]

    if k >= 3:
        names = LAYER_NAMES_3
    elif k == 2:
        names = ("inner", "outer")
    else:
        names = ("mid",)

    classes = []
    gray_means = []
    for lab, lname in enumerate(names):
        sel = labels_fit == lab
        gmean = float(samples["gray"][keep][sel].mean()) if sel.any() else 0.0
        gray_means.append(gmean)
        classes.append({
            "id": lname,
            "name_zh": LAYER_NAMES_ZH[lname],
            "mean_gray": round(gmean, 2),
            "mean_across": round(float(samples["across"][keep][sel].mean()) if sel.any() else 0.0, 3),
            "count": int(sel.sum()),
        })
    bdb = False
    dbd = False
    if k >= 3 and len(gray_means) >= 3:
        bdb = gray_means[0] > gray_means[1] and gray_means[2] > gray_means[1]
        dbd = gray_means[1] > gray_means[0] and gray_means[1] > gray_means[2]
    pattern = "-".join(names)
    if bdb:
        pattern = "bright-dark-bright"
    elif dbd:
        pattern = "dark-bright-dark"

    skip = ~keep if (not assign_lesion) else None
    fates = walk_layer_fate(samples, labels_all, keep, fit, lesion_d if exclude_lesion else lesion_mask, names)
    ridges = layer_centers(
        samples["xs"], samples["ys"], labels_all, names,
        along=samples["along_idx"], skip=skip,
    )
    keep_lab = keep & (labels_all >= 0)
    if prefer_strips:
        interfaces = interfaces_from_y_bands(samples, labels_all, keep)
    else:
        prefer = cuts_from_labels(samples["across"], labels_all, keep_lab)
        interfaces = trace_gray_interfaces(samples, keep, prefer_across=prefer or None)

    return ClusterArm(
        name=name,
        status="ok",
        k=k,
        method=method,
        n_pixels=int(len(samples["xs"])),
        n_valid=n_valid,
        dilate_px=dilate_px,
        cavity_side_source=cavity_side_source,
        pattern=pattern,
        bright_dark_bright=bdb,
        classes=classes,
        flanks=flanks,
        xs=samples["xs"].tolist(),
        ys=samples["ys"].tolist(),
        labels=labels_all.tolist(),
        layer_polylines=ridges,
        fates=fates,
        interfaces=interfaces,
    )


def kmeans1d(values: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    vals = values.reshape(-1, 1).astype(np.float32)
    labels, centers = kmeans_features(vals, k)
    return labels, centers.reshape(-1)


def deepest_invasion_point(
    lesion: np.ndarray,
    lumen: np.ndarray | None,
    wall: np.ndarray,
) -> np.ndarray | None:
    origin = polygon_centroid(lumen) if lumen is not None and len(lumen) else polygon_centroid(lesion)
    if len(lesion) >= 3 and origin is not None:
        deep = lesion[int(np.argmax(np.linalg.norm(lesion - origin, axis=1)))]
        if len(wall) >= 2:
            closest, _, _, _ = closest_on_poly(deep, wall)
            return closest
        return deep
    if len(wall) >= 4:
        return wall[min(len(wall) - 1, int(len(wall) * 0.82))]
    return None


def clarify_deepest_echo(
    gray: np.ndarray,
    lesion: np.ndarray,
    lumen: np.ndarray | None,
    wall: np.ndarray,
    brush_radius: float = DEFAULT_BRUSH,
) -> dict[str, Any]:
    """Port of workbench clarifyDeepestEcho: 56 x 28, labels by brightness."""
    wall = densify_polyline(as_xy(wall), 1.4)
    lesion = as_xy(lesion)
    lumen = as_xy(lumen) if lumen is not None else np.zeros((0, 2), dtype=np.float32)
    origin = deepest_invasion_point(lesion, lumen if len(lumen) else None, wall)
    if origin is None:
        return {"available": False, "note": "no deepest point"}
    if len(wall) >= 2:
        closest, idx, _, _ = closest_on_poly(origin, wall)
        a = wall[max(0, idx - 1)]
        b = wall[min(len(wall) - 1, idx + 1)]
        origin = closest
    else:
        a = origin
        b = origin + np.array([1.0, 0.0], dtype=np.float32)
    tan = b - a
    tlen = float(np.hypot(tan[0], tan[1])) or 1.0
    tan = tan / tlen
    normal = np.array([-tan[1], tan[0]], dtype=np.float32)
    lumen_center = polygon_centroid(lumen) if len(lumen) else polygon_centroid(lesion)
    if lumen_center is not None and float(np.dot(origin - lumen_center, normal)) < 0:
        normal = -normal
    brush = max(3.0, min(22.0, float(brush_radius) or 8.0))
    across_half = max(3.2, min(brush * 0.48, 8.5))
    along_half = 22.0
    along_count, across_count = 56, 28
    values = []
    coords = []
    height, width = gray.shape[:2]
    for row in range(across_count):
        across = -across_half + (2 * across_half * row) / max(1, across_count - 1)
        for col in range(along_count):
            along = -along_half + (2 * along_half * col) / max(1, along_count - 1)
            x = origin[0] + tan[0] * along + normal[0] * across
            y = origin[1] + tan[1] * along + normal[1] * across
            xi, yi = int(round(x)), int(round(y))
            val = float(gray[yi, xi]) if 0 <= xi < width and 0 <= yi < height else 0.0
            values.append(val)
            coords.append((xi, yi, val))
    values_np = np.asarray(values, dtype=np.float32)
    usable = values_np[values_np > 0]
    if usable.size < 40:
        return {"available": False, "note": "too few deepest-band pixels", "origin": origin.tolist()}
    k = 2 if (usable.size < 24 or float(usable.max() - usable.min()) < 28) else 3
    labels, means = kmeans1d(values_np, k)
    order = np.argsort(means)
    tone_names = ("dark", "mid", "bright") if k >= 3 else (("dark", "bright") if k == 2 else ("mid",))
    remap = {int(old): tone_names[min(rank, len(tone_names) - 1)] for rank, old in enumerate(order.tolist())}
    named = [remap[int(lab)] for lab in labels.tolist()]
    classes = []
    for name in tone_names:
        hits = [values[i] for i, lab in enumerate(named) if lab == name]
        if hits:
            classes.append({"id": name, "name_zh": LAYER_NAMES_ZH[name], "mean_gray": round(float(np.mean(hits)), 2), "count": len(hits)})
    return {
        "available": True,
        "origin": [float(origin[0]), float(origin[1])],
        "k": k,
        "along_px": 44.0,
        "across_px": round(across_half * 2, 1),
        "classes": classes,
        "pattern": "-".join(c["id"] for c in classes),
        "named": named,
        "coords": coords,
        "crop_w": along_count,
        "crop_h": across_count,
        "note": "live M0: 56x28 at deepest point, labels by brightness",
    }


def provisional_wall_from_lesion(lesion: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Temporary expected line: lesion major axis, shifted toward the deep face, extended past both flanks."""
    pts = as_xy(lesion)
    height, width = shape[:2]
    if len(pts) < 3:
        return pts
    center = pts.mean(axis=0)
    centered = pts - center
    _u, _s, vt = np.linalg.svd(centered, full_matrices=False)
    axis = vt[0].astype(np.float32)
    proj = centered @ axis
    tmin, tmax = float(proj.min()), float(proj.max())
    pad = max(40.0, 0.55 * (tmax - tmin))
    deep = pts[int(np.argmax(np.linalg.norm(centered, axis=1)))]
    outer = deep - center
    olen = float(np.hypot(outer[0], outer[1])) or 1.0
    outer = outer / olen
    half_w = float(np.std(centered @ np.array([-axis[1], axis[0]], dtype=np.float32)))
    origin = center + outer * max(4.0, half_w * 0.35)
    ts = np.linspace(tmin - pad, tmax + pad, 90, dtype=np.float32)
    line = origin[None, :] + ts[:, None] * axis[None, :]
    line[:, 0] = np.clip(line[:, 0], 1, width - 2)
    line[:, 1] = np.clip(line[:, 1], 1, height - 2)
    return line.astype(np.float32)


def to_gray(image_bgr: np.ndarray) -> np.ndarray:
    if image_bgr.ndim == 2:
        return image_bgr.astype(np.float32)
    return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
