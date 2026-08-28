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
DEFAULT_BRUSH = 8.0
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

    def summary(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("xs", None)
        data.pop("ys", None)
        data.pop("labels", None)
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


def layer_centers(xs: np.ndarray, ys: np.ndarray, labels: np.ndarray, names: tuple[str, ...]) -> dict[str, list[list[float]]]:
    out: dict[str, list[list[float]]] = {}
    for lab, name in enumerate(names):
        sel = labels == lab
        if int(sel.sum()) < 4:
            out[name] = []
            continue
        pts = np.stack([xs[sel].astype(np.float32), ys[sel].astype(np.float32)], axis=1)
        order = np.argsort(pts[:, 0] * 0.7 + pts[:, 1] * 0.3)
        pts = pts[order]
        bins = max(6, min(40, len(pts) // 8))
        edges = np.linspace(0, len(pts), bins + 1).astype(int)
        line = []
        for a, b in zip(edges[:-1], edges[1:]):
            chunk = pts[a:b]
            if len(chunk):
                line.append([float(chunk[:, 0].mean()), float(chunk[:, 1].mean())])
        out[name] = line
    return out


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
) -> ClusterArm:
    method = str(method or "kmeans").strip().lower()
    name = f"{'exclude' if exclude_lesion else 'full'}_{method}_k{k}_d{dilate_px}"
    wall = densify_polyline(as_xy(wall), 3.0)
    lesion_pts = as_xy(lesion_poly) if lesion_poly is not None else np.zeros((0, 2), dtype=np.float32)
    lesion_center = polygon_centroid(lesion_pts)
    deepest = None
    if len(lesion_pts) >= 2 and lesion_center is not None:
        deepest = lesion_pts[int(np.argmax(np.linalg.norm(lesion_pts - lesion_center, axis=1)))]
    if lumen_center is not None:
        cavity_side_source = "lumen"
    brush = rasterize_brush(gray.shape, wall, brush_radius)
    lesion_d = dilate_mask(lesion_mask, dilate_px) if exclude_lesion else np.zeros_like(lesion_mask)
    valid_mask = brush.copy()
    if exclude_lesion:
        valid_mask[lesion_d > 0] = 0
    flanks = split_flank_segments(wall, lesion_d if exclude_lesion else np.zeros_like(lesion_mask))
    samples = sample_band_pixels(gray, brush, wall, brush_radius, lumen_center, lesion_center, deepest)
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

    feat_all = features_for_method(samples, method)
    feat_fit = feat_all[keep]
    labels_fit, centers = cluster_features(feat_fit, k, method)
    order = np.argsort([float(samples["across"][keep][labels_fit == lab].mean()) if np.any(labels_fit == lab) else 0.0 for lab in range(k)])
    remap = {int(old): int(new) for new, old in enumerate(order.tolist())}
    labels_fit = np.array([remap[int(lab)] for lab in labels_fit], dtype=np.int32)
    labels_fit = majority_vote_sparse(samples["xs"][keep], samples["ys"][keep], labels_fit, gray.shape)

    # Assign every brush pixel from the flank-fitted centers (query cells do not refit).
    labels_all = np.full(len(samples["xs"]), -1, dtype=np.int32)
    labels_all[keep] = labels_fit
    if len(centers) >= k:
        ordered_centers = centers[order]
        rest = ~keep
        if rest.any():
            d2 = ((feat_all[rest, None, :] - ordered_centers[None, :, :]) ** 2).sum(axis=2)
            labels_all[rest] = np.argmin(d2, axis=1).astype(np.int32)

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
    if k >= 3 and len(gray_means) >= 3:
        bdb = gray_means[0] > gray_means[1] and gray_means[2] > gray_means[1]
    pattern = "-".join(names)
    if bdb:
        pattern = "bright-dark-bright"

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
        layer_polylines=layer_centers(samples["xs"][keep], samples["ys"][keep], labels_fit, names),
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
