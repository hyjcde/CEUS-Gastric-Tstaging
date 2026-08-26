"""GUS-Mask2Stage: mask-guided trans-boundary evidence + multi-keyframe ordinal T-stage.

Core inputs are doctor keyframes and a confirmed lesion mask. Clinical fields,
similar-case labels, and the doctor's first impression are not used by the
visual model. Tabular foundation models are a locked-OOF second stage only.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
import timm
from PIL import Image
from torch.utils.data import Dataset

from lib.datasets import _resolve_repo_path
from lib.transforms import IMAGENET_MEAN, IMAGENET_STD

CLASS_NAMES = ("T1", "T2", "T3", "T4+")
RADIAL_OFFSETS = (-0.35, -0.25, -0.15, -0.05, 0.0, 0.10, 0.20, 0.35, 0.50)
GEOM_DIM = 12
MIN_MASK_AREA = 8
GEOM_NAMES = (
    "area_ratio",
    "peri_diag",
    "circularity",
    "eccentricity",
    "solidity",
    "convexity",
    "major_diag",
    "minor_diag",
    "rotated_extent",
    "radial_cv",
    "radial_spread",
    "centroid_offset",
)
REGION_TAU = 0.06
PREOP18 = [
    "age_norm",
    "age_missing",
    "sex_norm",
    "sex_missing",
    "tumor_length_cm_norm",
    "tumor_length_cm_missing",
    "tumor_thickness_cm_norm",
    "tumor_thickness_cm_missing",
    "tumor_location_norm",
    "tumor_location_missing",
    "cea_value_norm",
    "cea_value_missing",
    "cea_binary_norm",
    "cea_binary_missing",
    "ca199_value_norm",
    "ca199_value_missing",
    "ca199_binary_norm",
    "ca199_binary_missing",
]
BACKBONE_CANDIDATES = (
    "convnextv2_tiny.fcmae_ft_in22k_in1k",
    "convnextv2_tiny",
    "convnext_tiny.fb_in22k_ft_in1k",
)


def resolve_backbone_name(requested: str | None = None) -> str:
    names = []
    if requested:
        names.append(requested)
    names.extend(BACKBONE_CANDIDATES)
    seen = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        try:
            timm.create_model(name, pretrained=False, num_classes=0)
            return name
        except Exception:
            continue
    raise RuntimeError("No ConvNeXt Tiny backbone is available in this timm install.")


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def legacy_coral_to_probs(logits: torch.Tensor) -> torch.Tensor:
    """Match ClassificationTool / live mask-pool CORAL decode (clamp then renormalize)."""
    cum = torch.sigmoid(logits.float())
    ones = torch.ones(logits.size(0), 1, device=logits.device, dtype=cum.dtype)
    zeros = torch.zeros(logits.size(0), 1, device=logits.device, dtype=cum.dtype)
    padded = torch.cat([ones, cum, zeros], dim=1)
    probs = (padded[:, :-1] - padded[:, 1:]).clamp_min(0)
    return probs / probs.sum(dim=1, keepdim=True).clamp_min(1e-8)


def coral_logits_to_probs(logits: torch.Tensor) -> torch.Tensor:
    """Rank-consistent CORAL used by GUS O1: monotone q then 4-class simplex."""
    cum = torch.sigmoid(logits.float())
    q1, q2, q3 = cum[:, 0], cum[:, 1], cum[:, 2]
    q2 = torch.minimum(q1, q2)
    q3 = torch.minimum(q2, q3)
    return cumulative_to_class_probs(torch.stack([q1, q2, q3], dim=1))


def labels_to_cumulative(y: torch.Tensor) -> torch.Tensor:
    """y in {0,1,2,3} -> (B, 3) indicators T>=T2, T>=T3, T>=T4+."""
    y = y.long().view(-1, 1)
    return torch.cat([(y > 0).float(), (y > 1).float(), (y > 2).float()], dim=1)


def cumulative_to_class_probs(q: torch.Tensor) -> torch.Tensor:
    q1, q2, q3 = q.unbind(dim=1)
    p1 = 1.0 - q1
    p2 = q1 - q2
    p3 = q2 - q3
    p4 = q3
    return torch.stack([p1, p2, p3, p4], dim=1).clamp_min(0)


def expected_rank(probs: torch.Tensor) -> torch.Tensor:
    ranks = torch.arange(probs.size(-1), device=probs.device, dtype=probs.dtype)
    return (probs * ranks).sum(dim=-1)


def topk_lme(values: torch.Tensor, valid: torch.Tensor, k: int, tau: float) -> torch.Tensor:
    """Soft top-k log-mean-exp. values (B, N), valid (B, N)."""
    fill = torch.finfo(values.dtype).min / 4
    masked = values.masked_fill(~valid, fill)
    kk = max(1, min(int(k), values.size(1)))
    topv, topi = torch.topk(masked, k=kk, dim=1)
    top_valid = valid.gather(1, topi)
    safe = torch.where(top_valid, topv / tau, torch.zeros_like(topv))
    # If a slot is invalid, drop it from the mean by using a count of valids.
    count = top_valid.float().sum(dim=1).clamp_min(1.0)
    # log(mean exp) over valid top slots only
    maxv = safe.masked_fill(~top_valid, fill).max(dim=1).values
    maxv = torch.where(top_valid.any(dim=1), maxv, torch.zeros_like(maxv))
    exp = torch.exp(safe - maxv.unsqueeze(1)) * top_valid.float()
    out = tau * (maxv + torch.log((exp.sum(dim=1) / count).clamp_min(1e-8)))
    fallback = (values * valid.float()).sum(dim=1) / valid.float().sum(dim=1).clamp_min(1.0)
    return torch.where(valid.any(dim=1), out, fallback)


# ---------------------------------------------------------------------------
# Mask geometry
# ---------------------------------------------------------------------------

def _largest_component(mask: np.ndarray, close: bool = True) -> np.ndarray:
    binary = (mask > 0.5).astype(np.uint8)
    if int(binary.sum()) == 0:
        return binary
    num, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if num <= 1:
        out = binary
    else:
        best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        out = (labels == best).astype(np.uint8)
    if close:
        out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    return out


def signed_distance(mask: np.ndarray) -> tuple[np.ndarray, float]:
    binary = _largest_component(mask)
    area = float(binary.sum())
    radius = max(math.sqrt(area / math.pi), 1.0)
    if area < 4:
        return np.ones(binary.shape, dtype=np.float32) * radius, radius
    inside = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    outside = cv2.distanceTransform(1 - binary, cv2.DIST_L2, 5)
    sdf = outside.astype(np.float32) - inside.astype(np.float32)
    return sdf, radius


def normalized_sdf(mask: np.ndarray) -> np.ndarray:
    """Signed distance divided by equivalent radius. Outside is positive."""
    sdf, radius = signed_distance(mask)
    return (sdf / radius).astype(np.float32)


def sigmoid_region_weights_from_d(d: torch.Tensor, tau: float = REGION_TAU) -> torch.Tensor:
    """Core / Inner / Outer / Perilesion from d=sdf/R. No force-sum-to-one.

    Far background (d > 0.50) stays near zero on every band.
    d: (N, 1, H, W) or (1, H, W)
    """
    if d.dim() == 3:
        d = d.unsqueeze(0)
    core = torch.sigmoid((-0.15 - d) / tau)
    inner = torch.sigmoid((d + 0.15) / tau) * torch.sigmoid((-d) / tau)
    outer = torch.sigmoid(d / tau) * torch.sigmoid((0.15 - d) / tau)
    peri = torch.sigmoid((d - 0.15) / tau) * torch.sigmoid((0.50 - d) / tau)
    return torch.cat([core, inner, outer, peri], dim=1)


def soft_region_weights(mask: np.ndarray, tau: float = REGION_TAU) -> np.ndarray:
    d = torch.from_numpy(normalized_sdf(mask)).unsqueeze(0).unsqueeze(0)
    return sigmoid_region_weights_from_d(d, tau=tau)[0].numpy()


def mask_geometry(mask: np.ndarray) -> tuple[np.ndarray, float]:
    """12-D shape features from the clean full-image mask.

    Computed on the original confirmed mask, not a context crop or letterbox.
    Ratios use contour area so solidity / circularity stay in [0, 1].
    Returns (feat, valid) where valid is 0 if the mask is too small.
    """
    eps = 1e-6
    binary = _largest_component(mask, close=False)
    h, w = binary.shape
    feat = np.zeros(GEOM_DIM, dtype=np.float32)
    if int(binary.sum()) < 16:
        return feat, 0.0

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return feat, 0.0
    cnt = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(cnt))
    perimeter = float(cv2.arcLength(cnt, True))
    if area <= eps or perimeter <= eps:
        return feat, 0.0

    hull = cv2.convexHull(cnt)
    hull_area = max(float(cv2.contourArea(hull)), eps)
    hull_perimeter = max(float(cv2.arcLength(hull, True)), eps)

    ys, xs = np.nonzero(binary)
    xy = np.column_stack([xs, ys]).astype(np.float64)
    cov = np.cov(xy, rowvar=False)
    if cov.ndim < 2:
        return feat, 0.0
    cov = cov + eps * np.eye(2)
    eig = np.sort(np.linalg.eigvalsh(cov))[::-1]
    lambda_major = max(float(eig[0]), eps)
    lambda_minor = max(float(eig[1]), 0.0)
    major_axis = 4.0 * math.sqrt(lambda_major)
    minor_axis = 4.0 * math.sqrt(lambda_minor)
    eccentricity = math.sqrt(max(1.0 - lambda_minor / lambda_major, 0.0))

    rect = cv2.minAreaRect(cnt)
    rect_center = np.asarray(rect[0], dtype=np.float64)
    rw, rh = rect[1]
    rect_area = max(float(rw * rh), eps)

    centroid = xy.mean(axis=0)
    contour_xy = cnt[:, 0, :].astype(np.float64)
    radial = np.linalg.norm(contour_xy - centroid[None, :], axis=1)
    radial_mean = max(float(radial.mean()), eps)
    radial_cv = float(radial.std() / radial_mean)
    q10, q50, q90 = np.percentile(radial, [10, 50, 90])
    radial_spread = float((q90 - q10) / max(float(q50), eps))

    equivalent_radius = math.sqrt(area / math.pi)
    centroid_offset = float(np.linalg.norm(centroid - rect_center) / max(equivalent_radius, eps))
    diagonal = max(math.hypot(h, w), 1.0)

    feat[:] = [
        area / float(h * w),
        perimeter / diagonal,
        float(np.clip(4.0 * math.pi * area / (perimeter * perimeter), 0.0, 1.0)),
        float(eccentricity),
        float(np.clip(area / hull_area, 0.0, 1.0)),
        float(np.clip(hull_perimeter / perimeter, 0.0, 1.0)),
        major_axis / diagonal,
        minor_axis / diagonal,
        float(np.clip(area / rect_area, 0.0, 1.0)),
        radial_cv,
        radial_spread,
        centroid_offset,
    ]
    return feat, 1.0


def standardize_geom(feat: np.ndarray, mean: np.ndarray | None, std: np.ndarray | None) -> np.ndarray:
    if mean is None or std is None:
        return feat.astype(np.float32)
    z = (feat.astype(np.float32) - np.asarray(mean, dtype=np.float32)) / np.maximum(
        np.asarray(std, dtype=np.float32), 1e-6
    )
    return np.clip(z, -5.0, 5.0).astype(np.float32)


def compute_geom_stats(csv_path: str | Path, max_rows: int = 0) -> tuple[np.ndarray, np.ndarray, int]:
    """Train-fold geom mean/std from original confirmed masks, before any crop or aug."""
    df = pd.read_csv(csv_path)
    if max_rows > 0:
        df = df.head(int(max_rows))
    feats = []
    for _, row in df.iterrows():
        path = _resolve_repo_path(row.get("mask_path", ""))
        if path is None:
            continue
        try:
            arr = np.array(Image.open(path).convert("L"), dtype=np.float32)
        except (OSError, ValueError):
            continue
        if arr.max() > 1.0:
            arr = arr / 255.0
        feat, valid = mask_geometry(arr)
        if valid > 0.5:
            feats.append(feat)
    if not feats:
        return np.zeros(GEOM_DIM, np.float32), np.ones(GEOM_DIM, np.float32), 0
    stacked = np.stack(feats, axis=0)
    return stacked.mean(axis=0).astype(np.float32), stacked.std(axis=0).astype(np.float32), int(len(stacked))


def geom_sanity_check() -> dict[str, float]:
    """Synthetic circle vs ellipse: circularity high, eccentricity rises."""
    circle = np.zeros((256, 256), np.uint8)
    cv2.circle(circle, (128, 128), 40, 1, -1)
    feat_c, ok_c = mask_geometry(circle.astype(np.float32))
    ellipse = np.zeros((256, 256), np.uint8)
    cv2.ellipse(ellipse, (128, 128), (80, 20), 0, 0, 360, 1, -1)
    feat_e, ok_e = mask_geometry(ellipse.astype(np.float32))
    if ok_c < 0.5 or ok_e < 0.5:
        raise RuntimeError("geom_sanity_check: empty synthetic mask")
    if not (0.0 <= float(feat_c[2]) <= 1.0 and 0.0 <= float(feat_e[2]) <= 1.0):
        raise RuntimeError("geom_sanity_check: circularity outside [0, 1]")
    if float(feat_c[2]) < 0.85:
        raise RuntimeError(f"geom_sanity_check: circle circularity too low {feat_c[2]:.3f}")
    if float(feat_e[3]) <= float(feat_c[3]):
        raise RuntimeError("geom_sanity_check: ellipse should be more eccentric")
    return {
        "circle_circularity": float(feat_c[2]),
        "circle_eccentricity": float(feat_c[3]),
        "ellipse_circularity": float(feat_e[2]),
        "ellipse_eccentricity": float(feat_e[3]),
    }


def _resample_contour(points: np.ndarray, n: int) -> np.ndarray:
    pts = points.reshape(-1, 2).astype(np.float32)
    if len(pts) < 2:
        return np.repeat(pts[:1], n, axis=0) if len(pts) else np.zeros((n, 2), np.float32)
    closed = np.vstack([pts, pts[:1]])
    seg = np.linalg.norm(closed[1:] - closed[:-1], axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(cum[-1])
    if total < 1e-3:
        return np.repeat(pts[:1], n, axis=0)
    targets = np.linspace(0.0, total, n, endpoint=False)
    out = np.zeros((n, 2), dtype=np.float32)
    out[:, 0] = np.interp(targets, cum, closed[:, 0])
    out[:, 1] = np.interp(targets, cum, closed[:, 1])
    return out


def radial_sample_xy(mask: np.ndarray, n_points: int = 24) -> tuple[np.ndarray, np.ndarray]:
    """Return (P, S, 2) coords in [-1, 1] and a (P,) validity mask."""
    h, w = mask.shape
    binary = _largest_component(mask)
    xy = np.zeros((n_points, len(RADIAL_OFFSETS), 2), dtype=np.float32)
    valid = np.zeros((n_points,), dtype=np.float32)
    if float(binary.sum()) < 8:
        return xy, valid
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return xy, valid
    cnt = max(contours, key=cv2.contourArea)
    pts = _resample_contour(cnt, n_points)
    sdf, radius = signed_distance(binary)
    gy, gx = np.gradient(sdf)
    for i, (x, y) in enumerate(pts):
        xi = int(np.clip(round(x), 0, w - 1))
        yi = int(np.clip(round(y), 0, h - 1))
        nx, ny = float(gx[yi, xi]), float(gy[yi, xi])
        norm = math.hypot(nx, ny) + 1e-6
        nx, ny = nx / norm, ny / norm
        ok = True
        for j, off in enumerate(RADIAL_OFFSETS):
            px = x + off * radius * nx
            py = y + off * radius * ny
            if not (0 <= px < w and 0 <= py < h):
                px = float(np.clip(px, 0, w - 1))
                py = float(np.clip(py, 0, h - 1))
                ok = ok and abs(off) < 0.2
            xy[i, j, 0] = 2.0 * px / max(w - 1, 1) - 1.0
            xy[i, j, 1] = 2.0 * py / max(h - 1, 1) - 1.0
        valid[i] = 1.0 if ok else 0.0
    return xy, valid


def perturb_mask(mask: np.ndarray, level: str = "light") -> np.ndarray:
    binary = _largest_component(mask)
    if binary.sum() < 8:
        return binary.astype(np.float32)
    sdf, radius = signed_distance(binary)
    if level == "heavy":
        k = int(np.clip(round(0.12 * radius), 1, 15))
    else:
        k = int(np.clip(round(0.05 * radius), 1, 7))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
    op = random.choice(["dilate", "erode", "close", "open", "shift"])
    if op == "dilate":
        out = cv2.dilate(binary, kernel)
    elif op == "erode":
        out = cv2.erode(binary, kernel)
        if out.sum() < 8:
            out = binary
    elif op == "close":
        out = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    elif op == "open":
        out = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        if out.sum() < 8:
            out = binary
    else:
        dx = random.randint(-max(k, 1), max(k, 1))
        dy = random.randint(-max(k, 1), max(k, 1))
        m = np.float32([[1, 0, dx], [0, 1, dy]])
        out = cv2.warpAffine(binary, m, (binary.shape[1], binary.shape[0]), flags=cv2.INTER_NEAREST)
    if random.random() < 0.35:
        ys, xs = np.where(out > 0)
        if len(xs) > 10:
            jitter = np.zeros_like(out, dtype=np.uint8)
            for x, y in zip(xs[:: max(1, len(xs) // 40)], ys[:: max(1, len(ys) // 40)]):
                cv2.circle(jitter, (int(x), int(y)), 1, 1, -1)
            if random.random() < 0.5:
                out = np.clip(out + jitter, 0, 1)
            else:
                out = np.clip(out - jitter, 0, 1)
                if out.sum() < 8:
                    out = binary
    return out.astype(np.float32)


def context_crop(image: Image.Image, mask: Image.Image, expand: float = 0.45) -> tuple[Image.Image, Image.Image]:
    arr = np.array(mask.convert("L"))
    ys, xs = np.where(arr > 127)
    if len(xs) == 0:
        return image, mask
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    bw, bh = x1 - x0, y1 - y0
    pad_x = int(round(bw * expand))
    pad_y = int(round(bh * expand))
    x0 = max(0, x0 - pad_x)
    y0 = max(0, y0 - pad_y)
    x1 = min(image.width, x1 + pad_x)
    y1 = min(image.height, y1 + pad_y)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return image, mask
    return image.crop((x0, y0, x1, y1)), mask.crop((x0, y0, x1, y1))


def _photo_aug(image: Image.Image) -> Image.Image:
    arr = np.array(image).astype(np.float32)
    if random.random() < 0.7:
        gamma = random.uniform(0.85, 1.15)
        arr = 255.0 * np.clip(arr / 255.0, 1e-6, 1.0) ** gamma
    if random.random() < 0.5:
        arr = arr * random.uniform(0.85, 1.15)
    if random.random() < 0.25:
        noise = np.random.randn(*arr.shape).astype(np.float32) * random.uniform(2.0, 8.0)
        arr = arr + noise
    if random.random() < 0.15:
        k = random.choice([3, 5])
        arr = cv2.GaussianBlur(arr, (k, k), 0)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _geo_aug(image: Image.Image, mask: Image.Image) -> tuple[Image.Image, Image.Image]:
    if random.random() < 0.5:
        image = image.transpose(Image.FLIP_LEFT_RIGHT)
        mask = mask.transpose(Image.FLIP_LEFT_RIGHT)
    angle = random.uniform(-12.0, 12.0)
    image = image.rotate(angle, resample=Image.BILINEAR, fillcolor=(0, 0, 0))
    mask = mask.rotate(angle, resample=Image.NEAREST, fillcolor=0)
    if random.random() < 0.4:
        scale = random.uniform(0.9, 1.08)
        nw, nh = max(8, int(image.width * scale)), max(8, int(image.height * scale))
        image = image.resize((nw, nh), Image.BILINEAR)
        mask = mask.resize((nw, nh), Image.NEAREST)
        if scale < 1.0:
            canvas_i = Image.new("RGB", (int(nw / scale), int(nh / scale)), (0, 0, 0))
            canvas_m = Image.new("L", canvas_i.size, 0)
            ox = (canvas_i.width - nw) // 2
            oy = (canvas_i.height - nh) // 2
            canvas_i.paste(image, (ox, oy))
            canvas_m.paste(mask, (ox, oy))
            image, mask = canvas_i, canvas_m
        else:
            left = (nw - image.width) // 2 if False else (nw - int(nw / scale)) // 2
            # After upscale, center-crop back toward original aspect box.
            cw, ch = max(8, int(nw / scale)), max(8, int(nh / scale))
            left = max(0, (nw - cw) // 2)
            top = max(0, (nh - ch) // 2)
            image = image.crop((left, top, left + cw, top + ch))
            mask = mask.crop((left, top, left + cw, top + ch))
    return image, mask


def letterbox_pair(image: Image.Image, mask: Image.Image, size: int) -> tuple[Image.Image, Image.Image]:
    """Keep aspect ratio, pad to a square. Mask uses nearest, RGB bilinear."""
    w, h = image.size
    scale = min(size / max(w, 1), size / max(h, 1))
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    image = image.resize((nw, nh), Image.BILINEAR)
    mask = mask.resize((nw, nh), Image.NEAREST)
    canvas_i = Image.new("RGB", (size, size), (0, 0, 0))
    canvas_m = Image.new("L", (size, size), 0)
    ox = (size - nw) // 2
    oy = (size - nh) // 2
    canvas_i.paste(image, (ox, oy))
    canvas_m.paste(mask, (ox, oy))
    return canvas_i, canvas_m


def _to_tensor_rgb(image: Image.Image) -> torch.Tensor:
    arr = np.array(image.convert("RGB"), dtype=np.float32) / 255.0
    ten = torch.from_numpy(arr).permute(2, 0, 1)
    mean = torch.tensor(IMAGENET_MEAN).view(3, 1, 1)
    std = torch.tensor(IMAGENET_STD).view(3, 1, 1)
    return (ten - mean) / std


def _to_tensor_mask(mask: Image.Image) -> torch.Tensor:
    arr = np.array(mask.convert("L"), dtype=np.float32)
    if arr.max() > 1.0:
        arr = arr / 255.0
    return torch.from_numpy((arr > 0.5).astype(np.float32)).unsqueeze(0)


def _to_tensor_sdf(mask_np: np.ndarray) -> torch.Tensor:
    if float((mask_np > 0.5).sum()) < MIN_MASK_AREA:
        return torch.zeros(1, mask_np.shape[0], mask_np.shape[1], dtype=torch.float32)
    return torch.from_numpy(normalized_sdf(mask_np)).unsqueeze(0)


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

def choose_bag_size(n_avail: int, is_train: bool, max_frames: int) -> int:
    cap = min(int(max_frames), int(n_avail))
    if cap <= 1:
        return cap
    if not is_train:
        return cap
    roll = random.random()
    if roll < 0.50:
        lo, hi = 2, 4
    elif roll < 0.80:
        lo, hi = 5, 6
    else:
        lo, hi = 7, 10
    lo = min(lo, cap)
    hi = min(hi, cap)
    if hi < lo:
        return cap
    return random.randint(lo, hi)


class PatientBagGUSDataset(Dataset):
    """One item = one patient bag of crop_ui frames + lesion masks."""

    def __init__(
        self,
        csv_path,
        max_frames: int = 10,
        image_size: int = 384,
        context_size: int = 384,
        n_points: int = 24,
        is_train: bool = False,
        context_expand: float = 0.45,
        mask_perturb: bool = True,
        return_alt_mask: bool = True,
        geom_mean: np.ndarray | None = None,
        geom_std: np.ndarray | None = None,
        drop_invalid_geom: bool = False,
    ):
        self.df = pd.read_csv(csv_path)
        self.max_frames = int(max_frames)
        self.image_size = int(image_size)
        self.context_size = int(context_size)
        self.n_points = int(n_points)
        self.is_train = bool(is_train)
        self.context_expand = float(context_expand)
        self.mask_perturb = bool(mask_perturb) and self.is_train
        self.return_alt_mask = bool(return_alt_mask) and self.is_train
        self.geom_mean = None if geom_mean is None else np.asarray(geom_mean, dtype=np.float32)
        self.geom_std = None if geom_std is None else np.asarray(geom_std, dtype=np.float32)
        self.drop_invalid_geom = bool(drop_invalid_geom)
        pid_col = "patient_id_unique" if "patient_id_unique" in self.df.columns else "patient_id"
        grouped = self.df.groupby(pid_col, sort=False)
        self.patients = list(grouped.groups.keys())
        self.patient_rows = {pid: grouped.get_group(pid).reset_index(drop=True) for pid in self.patients}
        self.label_conflicts: list[str] = []
        self.patient_labels = {}
        for pid, grp in grouped:
            nuniq = int(grp["label"].nunique())
            if nuniq != 1:
                self.label_conflicts.append(str(pid))
            self.patient_labels[pid] = int(grp["label"].mode().iloc[0])
        if self.label_conflicts:
            print(
                f"[gus] {len(self.label_conflicts)} patients have mixed labels; using mode. "
                f"ids={self.label_conflicts[:8]}",
                flush=True,
            )
        self._area_cache: dict[str, float] = {}

    def __len__(self) -> int:
        return len(self.patients)

    def _mask_area_ratio(self, row) -> float:
        key = str(row.get("mask_path", ""))
        if key in self._area_cache:
            return self._area_cache[key]
        path = _resolve_repo_path(key)
        area = 0.0
        if path is not None:
            try:
                arr = np.array(Image.open(path).convert("L"))
                area = float((arr > 127).mean())
            except Exception:
                area = 0.0
        self._area_cache[key] = area
        return area

    def _load_pair(self, row) -> tuple[Image.Image | None, Image.Image | None, bool, bool]:
        img_path = _resolve_repo_path(row.get("image_path", ""))
        mask_path = _resolve_repo_path(row.get("mask_path", ""))
        image = None
        mask = None
        image_ok = False
        mask_ok = False
        if img_path is not None:
            try:
                image = Image.open(img_path).convert("RGB")
                image_ok = True
            except Exception as exc:
                print(f"[gus] image read failed {img_path}: {exc}", flush=True)
        if mask_path is not None and image is not None:
            try:
                mask = Image.open(mask_path).convert("L")
                if mask.size != image.size:
                    mask = mask.resize(image.size, Image.NEAREST)
                mask_ok = True
            except Exception as exc:
                print(f"[gus] mask read failed {mask_path}: {exc}", flush=True)
        return image, mask, image_ok, mask_ok

    def _views_from_mask(self, image: Image.Image, mask: Image.Image) -> dict[str, Any]:
        ctx_i, ctx_m = context_crop(image, mask, expand=self.context_expand)
        full_i, full_m = letterbox_pair(image, mask, self.image_size)
        ctx_i, ctx_m = letterbox_pair(ctx_i, ctx_m, self.context_size)
        full_np = np.array(full_m, dtype=np.float32)
        ctx_np = np.array(ctx_m, dtype=np.float32)
        if full_np.max() > 1.0:
            full_np = full_np / 255.0
        if ctx_np.max() > 1.0:
            ctx_np = ctx_np / 255.0
        full_bin = (full_np > 0.5).astype(np.float32)
        ctx_bin = (ctx_np > 0.5).astype(np.float32)
        radial_xy, radial_valid = radial_sample_xy(ctx_bin, self.n_points)
        return {
            "full_rgb": _to_tensor_rgb(full_i),
            "ctx_rgb": _to_tensor_rgb(ctx_i),
            "full_mask": torch.from_numpy(full_bin).unsqueeze(0),
            "ctx_mask": torch.from_numpy(ctx_bin).unsqueeze(0),
            "full_sdf": _to_tensor_sdf(full_bin),
            "ctx_sdf": _to_tensor_sdf(ctx_bin),
            "radial_xy": torch.from_numpy(radial_xy),
            "radial_valid": torch.from_numpy(radial_valid),
            "area": torch.tensor(float(full_bin.sum()), dtype=torch.float32),
        }

    def _prepare_frame(self, row) -> dict[str, Any] | None:
        image, mask, image_ok, mask_ok = self._load_pair(row)
        if not image_ok or not mask_ok or image is None or mask is None:
            return None
        orig_np = np.array(mask.convert("L"), dtype=np.float32)
        if orig_np.max() > 1.0:
            orig_np = orig_np / 255.0
        if float((orig_np > 0.5).sum()) < MIN_MASK_AREA:
            return None
        geom_np, geom_ok = mask_geometry(orig_np)
        if self.drop_invalid_geom and geom_ok < 0.5:
            return None
        geom_np = standardize_geom(geom_np, self.geom_mean, self.geom_std)
        if self.is_train:
            image, mask = _geo_aug(image, mask)
            image = _photo_aug(image)
        clean_np = np.array(mask, dtype=np.float32)
        if clean_np.max() > 1.0:
            clean_np = clean_np / 255.0
        clean_np = (clean_np > 0.5).astype(np.float32)
        if float(clean_np.sum()) < MIN_MASK_AREA:
            return None
        train_np = clean_np
        if self.mask_perturb:
            roll = random.random()
            if roll < 0.20:
                train_np = perturb_mask(clean_np, "light")
            elif roll < 0.30:
                train_np = perturb_mask(clean_np, "heavy")
        train_mask = Image.fromarray((train_np > 0.5).astype(np.uint8) * 255)
        out = self._views_from_mask(image, train_mask)
        out["geom"] = torch.from_numpy(geom_np)
        out["geom_valid"] = torch.tensor(bool(geom_ok > 0.5))
        out["star"] = torch.tensor(float(row.get("deepest_invasion", 0) or 0), dtype=torch.float32)
        out["frame_valid"] = torch.tensor(True)
        if self.return_alt_mask:
            alt_np = perturb_mask(clean_np, "light")
            alt_mask = Image.fromarray((alt_np > 0.5).astype(np.uint8) * 255)
            alt = self._views_from_mask(image, alt_mask)
            out["alt_full_mask"] = alt["full_mask"]
            out["alt_ctx_mask"] = alt["ctx_mask"]
            out["alt_full_sdf"] = alt["full_sdf"]
            out["alt_ctx_sdf"] = alt["ctx_sdf"]
            out["alt_radial_xy"] = alt["radial_xy"]
            out["alt_radial_valid"] = alt["radial_valid"]
        return out

    def _select_rows(self, rows: pd.DataFrame) -> pd.DataFrame:
        work = rows
        if "keyframe_selected" in work.columns:
            flag = work["keyframe_selected"].astype(str).str.lower().isin({"1", "true", "yes"})
            if bool(flag.any()):
                work = work.loc[flag]
        n = len(work)
        k = choose_bag_size(n, self.is_train, self.max_frames)
        if n <= k:
            chosen = work
            if "keyframe_order" in chosen.columns:
                chosen = chosen.sort_values("keyframe_order")
            elif not self.is_train:
                if "deepest_invasion" in chosen.columns:
                    chosen = chosen.sort_values(["deepest_invasion", "image_path"], ascending=[False, True])
                else:
                    chosen = chosen.sort_values("image_path")
            return chosen.reset_index(drop=True)
        if self.is_train:
            areas = np.array([self._mask_area_ratio(row) for _, row in work.iterrows()], dtype=np.float64)
            order = np.argsort(areas)[::-1]
            if random.random() < 0.5:
                pick = list(order[: max(1, k // 2)])
                rest = [i for i in range(n) if i not in pick]
                random.shuffle(rest)
                pick.extend(rest[: k - len(pick)])
            else:
                pick = list(np.random.choice(n, size=k, replace=False))
            return work.iloc[sorted(pick)].reset_index(drop=True)
        if "keyframe_order" in work.columns:
            return work.sort_values("keyframe_order").iloc[:k].reset_index(drop=True)
        areas = np.array([self._mask_area_ratio(row) for _, row in work.iterrows()], dtype=np.float64)
        top = work.iloc[np.argsort(areas)[::-1][:k]]
        if "deepest_invasion" in work.columns:
            star = work[work["deepest_invasion"].fillna(0).astype(float) > 0]
            if len(star):
                top = pd.concat([star, top], axis=0).drop_duplicates().iloc[:k]
        return top.sort_values("image_path").reset_index(drop=True)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        pid = self.patients[idx]
        rows = self._select_rows(self.patient_rows[pid])
        bag = []
        for _, row in rows.iterrows():
            item = self._prepare_frame(row)
            if item is not None:
                bag.append(item)
        pad = self.max_frames
        k = len(bag)

        def _stack(key, fill):
            items = [b[key] for b in bag] if bag else []
            while len(items) < pad:
                items.append(fill)
            return torch.stack(items, dim=0)

        zero_rgb = torch.zeros(3, self.image_size, self.image_size)
        zero_mask = torch.zeros(1, self.image_size, self.image_size)
        zero_ctx = torch.zeros(3, self.context_size, self.context_size)
        zero_cmask = torch.zeros(1, self.context_size, self.context_size)
        zero_xy = torch.zeros(self.n_points, len(RADIAL_OFFSETS), 2)
        zero_pv = torch.zeros(self.n_points)
        valid = torch.zeros(pad, dtype=torch.bool)
        valid[:k] = True
        out = {
            "full_rgb": _stack("full_rgb", zero_rgb),
            "ctx_rgb": _stack("ctx_rgb", zero_ctx),
            "full_mask": _stack("full_mask", zero_mask),
            "ctx_mask": _stack("ctx_mask", zero_cmask),
            "full_sdf": _stack("full_sdf", zero_mask),
            "ctx_sdf": _stack("ctx_sdf", zero_cmask),
            "geom": _stack("geom", torch.zeros(GEOM_DIM)),
            "geom_valid": _stack("geom_valid", torch.tensor(False)),
            "radial_xy": _stack("radial_xy", zero_xy),
            "radial_valid": _stack("radial_valid", zero_pv),
            "star": _stack("star", torch.tensor(0.0)),
            "area": _stack("area", torch.tensor(0.0)),
            "valid": valid,
            "label": torch.tensor(self.patient_labels[pid], dtype=torch.long),
            "patient_id": str(pid),
            "n_frames": torch.tensor(k, dtype=torch.long),
        }
        if self.return_alt_mask:
            out["alt_full_mask"] = _stack("alt_full_mask", zero_mask) if bag and "alt_full_mask" in bag[0] else _stack("full_mask", zero_mask)
            out["alt_ctx_mask"] = _stack("alt_ctx_mask", zero_cmask) if bag and "alt_ctx_mask" in bag[0] else _stack("ctx_mask", zero_cmask)
            out["alt_full_sdf"] = _stack("alt_full_sdf", zero_mask) if bag and "alt_full_sdf" in bag[0] else _stack("full_sdf", zero_mask)
            out["alt_ctx_sdf"] = _stack("alt_ctx_sdf", zero_cmask) if bag and "alt_ctx_sdf" in bag[0] else _stack("ctx_sdf", zero_cmask)
            out["alt_radial_xy"] = _stack("alt_radial_xy", zero_xy) if bag and "alt_radial_xy" in bag[0] else _stack("radial_xy", zero_xy)
            out["alt_radial_valid"] = _stack("alt_radial_valid", zero_pv) if bag and "alt_radial_valid" in bag[0] else _stack("radial_valid", zero_pv)
        return out


def gus_collate(batch: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    keys = [k for k in batch[0].keys() if k != "patient_id"]
    for key in keys:
        out[key] = torch.stack([b[key] for b in batch], dim=0)
    out["patient_id"] = [b["patient_id"] for b in batch]
    return out


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class SharedConvNeXt(nn.Module):
    def __init__(self, backbone_name: str, pretrained: bool, drop_path: float, in_chans: int = 3):
        super().__init__()
        kwargs = {
            "pretrained": pretrained,
            "features_only": True,
            "out_indices": (1, 2, 3),
            "in_chans": in_chans,
        }
        if drop_path:
            kwargs["drop_path_rate"] = float(drop_path)
        try:
            self.backbone = timm.create_model(backbone_name, **kwargs)
        except TypeError:
            kwargs.pop("drop_path_rate", None)
            self.backbone = timm.create_model(backbone_name, **kwargs)
        self.channels = [int(c) for c in self.backbone.feature_info.channels()]

    def forward(self, x: torch.Tensor) -> list[torch.Tensor]:
        return list(self.backbone(x))

    def freeze_stages(self, mode: str) -> None:
        """mode: early | mid | none"""
        for p in self.parameters():
            p.requires_grad = True
        if mode == "none":
            return
        # timm ConvNeXt: stem + stages
        stem = getattr(self.backbone, "stem", None)
        stages = getattr(self.backbone, "stages", None)
        if stem is None or stages is None:
            # freeze first half of named parameters
            named = list(self.named_parameters())
            cut = max(1, len(named) // 2)
            for i, (_, p) in enumerate(named):
                p.requires_grad = i >= cut
            return
        for p in stem.parameters():
            p.requires_grad = False
        n_freeze = 2 if mode == "early" else 1
        for i, stage in enumerate(stages):
            trainable = i >= n_freeze
            for p in stage.parameters():
                p.requires_grad = trainable


class TokenProj(nn.Module):
    def __init__(self, in_dim: int, token_dim: int):
        super().__init__()
        self.proj = nn.Sequential(nn.LayerNorm(in_dim), nn.Linear(in_dim, token_dim), nn.GELU())

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.proj(x)


def masked_mean(feat: torch.Tensor, weight: torch.Tensor) -> torch.Tensor:
    w = weight.clamp_min(0)
    denom = w.sum(dim=(-2, -1), keepdim=True).clamp_min(1e-6)
    return (feat * w).sum(dim=(-2, -1)) / denom.squeeze(-1).squeeze(-1)


class RadialEncoder(nn.Module):
    def __init__(self, in_dim: int, token_dim: int, n_steps: int):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(in_dim, token_dim, kernel_size=3, padding=1),
            nn.GELU(),
            nn.Conv1d(token_dim, token_dim, kernel_size=3, padding=1),
            nn.GELU(),
        )
        self.out = nn.Linear(token_dim * n_steps, token_dim)

    def forward(self, feat_map: torch.Tensor, xy: torch.Tensor) -> torch.Tensor:
        """feat_map (N,C,H,W), xy (N,P,S,2) in [-1,1] -> (N,P,D)."""
        n, p, s, _ = xy.shape
        grid = xy.view(n, p * s, 1, 2)
        sampled = F.grid_sample(feat_map, grid, mode="bilinear", padding_mode="border", align_corners=True)
        sampled = sampled.squeeze(-1).transpose(1, 2).reshape(n * p, sampled.size(1), s)
        hidden = self.conv(sampled)
        flat = hidden.reshape(n * p, -1)
        return self.out(flat).view(n, p, -1)


class GUSMask2Stage(nn.Module):
    """Shared ConvNeXt + region/radial evidence + threshold-specific bag fusion."""

    def __init__(
        self,
        backbone_name: str = "convnextv2_tiny.fcmae_ft_in22k_in1k",
        pretrained: bool = True,
        token_dim: int = 192,
        n_points: int = 24,
        n_steps: int = 9,
        top_m: int = 4,
        top_k: int = 2,
        tau_b: float = 0.5,
        tau_f: float = 0.5,
        dropout: float = 0.1,
        drop_path: float = 0.1,
        variant: str = "M4",
        aggregation: str = "A4",
        ordinal: str = "O3",
        use_star: bool = False,
        star_beta: float = 0.15,
        in_chans: int = 3,
    ):
        super().__init__()
        self.variant = variant
        self.aggregation = aggregation
        self.ordinal = ordinal
        self.use_star = bool(use_star)
        self.star_beta = float(star_beta)
        self.token_dim = int(token_dim)
        self.n_points = int(n_points)
        self.top_m = int(top_m)
        self.top_k = int(top_k)
        self.tau_b = float(tau_b)
        self.tau_f = float(tau_f)
        self.use_image = variant != "M5"
        self.use_context = variant in {"M2", "M3", "M4", "M6"}
        self.use_regions = variant in {"M3", "M4", "M6"}
        self.use_radial = variant in {"M4", "M6"}
        self.use_geom = variant in {"M4", "M5"}
        self.use_mask4 = variant == "M1"
        enc_ch = 4 if self.use_mask4 else in_chans
        if self.use_image:
            self.encoder = SharedConvNeXt(backbone_name, pretrained, drop_path, in_chans=enc_ch)
            c2, c3, c4 = self.encoder.channels
            self.proj_c2 = TokenProj(c2, token_dim)
            self.proj_c3 = TokenProj(c3, token_dim)
            self.proj_c4 = TokenProj(c4, token_dim)
            self.radial = RadialEncoder(c2, token_dim, n_steps) if self.use_radial else None
        else:
            self.encoder = None
            self.proj_c2 = self.proj_c3 = self.proj_c4 = None
            self.radial = None
        self.geom_mlp = None
        if self.use_geom:
            self.geom_mlp = nn.Sequential(
                nn.Linear(GEOM_DIM, token_dim),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(token_dim, token_dim),
            )
        # 0 CLS, 1 full, 2 ctx, 3-6 regions, 7 geom, 8 radial
        self.token_type = nn.Embedding(9, token_dim)
        self.cls_token = nn.Parameter(torch.zeros(1, 1, token_dim))
        enc_layer = nn.TransformerEncoderLayer(
            d_model=token_dim,
            nhead=4,
            dim_feedforward=token_dim * 4,
            dropout=dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.evidence = nn.TransformerEncoder(enc_layer, num_layers=2)
        self.frame_heads = nn.ModuleList([nn.Linear(token_dim, 1) for _ in range(3)])
        self.boundary_heads = nn.ModuleList([nn.Sequential(
            nn.Linear(token_dim * 2, token_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(token_dim, 1),
        ) for _ in range(3)])
        self.attn_frame = nn.Linear(token_dim, 3)
        self.softmax_head = nn.Linear(token_dim, 4)
        self.coral_score = nn.Linear(token_dim, 1)
        self.coral_thresholds = nn.Parameter(torch.tensor([-0.5, 0.0, 0.5]))
        self.indep_head = nn.Linear(token_dim, 3)
        self.bottleneck = nn.Linear(token_dim, 32)
        self.use_encoded_radial = True
        nn.init.trunc_normal_(self.cls_token, std=0.02)
        nn.init.trunc_normal_(self.token_type.weight, std=0.02)

    def _encode_view(
        self,
        rgb: torch.Tensor,
        mask: torch.Tensor | None,
        sdf: torch.Tensor | None,
    ) -> dict[str, torch.Tensor]:
        x = rgb
        if self.use_mask4:
            if mask is None:
                mask = torch.zeros(rgb.size(0), 1, rgb.size(2), rgb.size(3), device=rgb.device, dtype=rgb.dtype)
            x = torch.cat([rgb, mask], dim=1)
        feats = self.encoder(x)
        c2, c3, c4 = feats
        gap = self.proj_c4(c4.mean(dim=(-2, -1)))
        regions = []
        if self.use_regions and sdf is not None:
            weights = sigmoid_region_weights_from_d(
                F.interpolate(sdf, size=c2.shape[-2:], mode="bilinear", align_corners=False)
            )
            for band in range(4):
                pooled = []
                for feat, proj in zip((c2, c3, c4), (self.proj_c2, self.proj_c3, self.proj_c4)):
                    w = F.interpolate(weights[:, band : band + 1], size=feat.shape[-2:], mode="bilinear", align_corners=False)
                    empty = w.flatten(1).sum(dim=1, keepdim=True) < 1e-4
                    tok = proj(masked_mean(feat, w))
                    gap_s = proj(feat.mean(dim=(-2, -1)))
                    tok = torch.where(empty, gap_s, tok)
                    pooled.append(tok)
                regions.append(torch.stack(pooled, dim=0).mean(dim=0))
        return {"gap": gap, "c2": c2, "regions": regions}

    def encode_frames(
        self,
        full_rgb: torch.Tensor,
        ctx_rgb: torch.Tensor,
        full_mask: torch.Tensor,
        ctx_mask: torch.Tensor,
        geom: torch.Tensor,
        radial_xy: torch.Tensor,
        radial_valid: torch.Tensor,
        full_sdf: torch.Tensor | None = None,
        ctx_sdf: torch.Tensor | None = None,
        geom_valid: torch.Tensor | None = None,
    ) -> dict[str, torch.Tensor]:
        n, k = full_rgb.shape[:2]
        dim = self.token_dim
        device = full_rgb.device
        if geom_valid is None:
            gvalid = torch.ones(n, k, dtype=torch.bool, device=device)
        else:
            gvalid = geom_valid.bool()
        if not self.use_image:
            frame = self.geom_mlp(geom)
            frame = frame + self.token_type.weight[7].view(1, 1, -1)
            frame = frame * gvalid.unsqueeze(-1).to(dtype=frame.dtype)
            return {
                "frame_token": frame,
                "radial_token": frame.unsqueeze(2).expand(-1, -1, self.n_points, -1),
                "core_full": frame,
                "core_ctx": frame,
            }

        flat_full = full_rgb.view(n * k, *full_rgb.shape[2:])
        flat_fmask = full_mask.view(n * k, *full_mask.shape[2:])
        flat_fsdf = full_sdf.view(n * k, *full_sdf.shape[2:]) if full_sdf is not None else None
        enc_full = self._encode_view(flat_full, flat_fmask, flat_fsdf)
        if self.use_context:
            flat_ctx = ctx_rgb.view(n * k, *ctx_rgb.shape[2:])
            flat_cmask = ctx_mask.view(n * k, *ctx_mask.shape[2:])
            flat_csdf = ctx_sdf.view(n * k, *ctx_sdf.shape[2:]) if ctx_sdf is not None else None
            enc_ctx = self._encode_view(flat_ctx, flat_cmask, flat_csdf)
        else:
            enc_ctx = enc_full

        tokens = [self.cls_token.expand(n * k, -1, -1)]
        type_ids = [torch.zeros(n * k, 1, dtype=torch.long, device=device)]
        tokens.append(enc_full["gap"].unsqueeze(1))
        type_ids.append(torch.full((n * k, 1), 1, dtype=torch.long, device=device))
        if self.use_context:
            tokens.append(enc_ctx["gap"].unsqueeze(1))
            type_ids.append(torch.full((n * k, 1), 2, dtype=torch.long, device=device))
        if self.use_regions:
            src = enc_ctx["regions"] if self.use_context and enc_ctx["regions"] else enc_full["regions"]
            tokens.extend([r.unsqueeze(1) for r in src])
            type_ids.extend([
                torch.full((n * k, 1), tid, dtype=torch.long, device=device)
                for tid in (3, 4, 5, 6)[: len(src)]
            ])
        geom_idx = None
        if self.use_geom and self.geom_mlp is not None:
            geom_idx = sum(t.size(1) for t in tokens)
            tokens.append(self.geom_mlp(geom.view(n * k, -1)).unsqueeze(1))
            type_ids.append(torch.full((n * k, 1), 7, dtype=torch.long, device=device))
        rad_start = None
        if self.use_radial and self.radial is not None:
            xy = radial_xy.view(n * k, self.n_points, -1, 2)
            rad = self.radial(enc_ctx["c2"], xy)
            rad_start = sum(t.size(1) for t in tokens)
            tokens.append(rad)
            type_ids.append(torch.full((n * k, self.n_points), 8, dtype=torch.long, device=device))
            radial_raw = rad
        else:
            radial_raw = torch.zeros(n * k, self.n_points, dim, device=device)
        seq = torch.cat(tokens, dim=1) + self.token_type(torch.cat(type_ids, dim=1))
        key_pad = torch.zeros(n * k, seq.size(1), dtype=torch.bool, device=device)
        if geom_idx is not None:
            key_pad[:, geom_idx] = ~gvalid.view(n * k)
        if rad_start is not None:
            key_pad[:, rad_start: rad_start + self.n_points] = ~(radial_valid.view(n * k, self.n_points) > 0.5)
        encoded = self.evidence(seq, src_key_padding_mask=key_pad)
        frame = encoded[:, 0]
        if self.use_encoded_radial and rad_start is not None:
            radial_token = encoded[:, rad_start: rad_start + self.n_points]
        else:
            radial_token = radial_raw
        core_full = enc_full["regions"][0] if enc_full["regions"] else enc_full["gap"]
        core_ctx = enc_ctx["regions"][0] if enc_ctx["regions"] else enc_ctx["gap"]
        return {
            "frame_token": frame.view(n, k, dim),
            "radial_token": radial_token.view(n, k, self.n_points, dim),
            "core_full": core_full.view(n, k, dim),
            "core_ctx": core_ctx.view(n, k, dim),
        }

    def _frame_evidence(
        self,
        frame_token: torch.Tensor,
        radial_token: torch.Tensor,
        radial_valid: torch.Tensor,
        valid: torch.Tensor,
    ) -> torch.Tensor:
        """Return (N, K, 3) threshold evidence."""
        n, k, _ = frame_token.shape
        u = []
        for t, (fh, bh) in enumerate(zip(self.frame_heads, self.boundary_heads)):
            base = fh(frame_token).squeeze(-1)
            if self.use_radial:
                ctx = frame_token.unsqueeze(2).expand(-1, -1, self.n_points, -1)
                e = bh(torch.cat([radial_token, ctx], dim=-1)).squeeze(-1)
                e = e.view(n * k, self.n_points)
                rv = (radial_valid > 0.5).view(n * k, self.n_points)
                local = topk_lme(e, rv, self.top_m, self.tau_b).view(n, k)
                score = 0.5 * (base + local)
            else:
                score = base
            score = score.masked_fill(~valid, torch.finfo(score.dtype).min / 4)
            u.append(score)
        return torch.stack(u, dim=-1)

    def _aggregate(self, u: torch.Tensor, frame_token: torch.Tensor, valid: torch.Tensor, star: torch.Tensor) -> torch.Tensor:
        """u (N,K,3) -> z (N,3)."""
        n, k, _ = u.shape
        if self.aggregation == "A0":
            # first valid frame
            idx = valid.float().argmax(dim=1)
            return u[torch.arange(n, device=u.device), idx]
        if self.aggregation == "A1":
            w = valid.float().unsqueeze(-1)
            return (u.masked_fill(~valid.unsqueeze(-1), 0) * w).sum(dim=1) / w.sum(dim=1).clamp_min(1.0)
        if self.aggregation == "A2":
            a = torch.sigmoid(u)
            q = torch.stack([a[:, :, 0], a[:, :, 0] * a[:, :, 1], a[:, :, 0] * a[:, :, 1] * a[:, :, 2]], dim=-1)
            probs = torch.stack([1 - q[:, :, 0], q[:, :, 0] - q[:, :, 1], q[:, :, 1] - q[:, :, 2], q[:, :, 2]], dim=-1).clamp_min(0)
            rank = expected_rank(probs)
            rank = rank.masked_fill(~valid, torch.finfo(rank.dtype).min / 4)
            idx = rank.argmax(dim=1)
            return u[torch.arange(n, device=u.device), idx]
        if self.aggregation == "A3":
            logits = self.attn_frame(frame_token)
            logits = logits.masked_fill(~valid.unsqueeze(-1), torch.finfo(logits.dtype).min / 4)
            attn = torch.softmax(logits, dim=1)
            return (attn * u).sum(dim=1)
        z = []
        bias = self.star_beta * star if (self.use_star and self.aggregation == "A5") else 0.0
        for t in range(3):
            val = u[:, :, t] + (bias if torch.is_tensor(bias) else 0.0)
            z.append(topk_lme(val, valid, self.top_k, self.tau_f))
        return torch.stack(z, dim=-1)

    def _patient_token(self, frame_token: torch.Tensor, u: torch.Tensor, valid: torch.Tensor, star: torch.Tensor) -> torch.Tensor:
        """Pool frame tokens with the same A0-A5 rule used for z."""
        n, k, _ = frame_token.shape
        fill = torch.finfo(frame_token.dtype).min / 4
        if self.aggregation == "A0":
            idx = valid.float().argmax(dim=1)
            return frame_token[torch.arange(n, device=frame_token.device), idx]
        if self.aggregation == "A2":
            a = torch.sigmoid(u)
            q = torch.stack([a[:, :, 0], a[:, :, 0] * a[:, :, 1], a[:, :, 0] * a[:, :, 1] * a[:, :, 2]], dim=-1)
            probs = torch.stack([1 - q[:, :, 0], q[:, :, 0] - q[:, :, 1], q[:, :, 1] - q[:, :, 2], q[:, :, 2]], dim=-1).clamp_min(0)
            rank = expected_rank(probs).masked_fill(~valid, fill)
            idx = rank.argmax(dim=1)
            return frame_token[torch.arange(n, device=frame_token.device), idx]
        if self.aggregation == "A3":
            logits = self.attn_frame(frame_token).mean(dim=-1)
            logits = logits.masked_fill(~valid, fill)
            w = torch.softmax(logits, dim=1)
            return (w.unsqueeze(-1) * frame_token).sum(dim=1)
        if self.aggregation in {"A4", "A5"}:
            score = u.mean(dim=-1)
            if self.use_star and self.aggregation == "A5":
                score = score + self.star_beta * star
            score = score.masked_fill(~valid, fill)
            w = torch.softmax(score / max(self.tau_f, 1e-4), dim=1)
            return (w.unsqueeze(-1) * frame_token).sum(dim=1)
        w = valid.float()
        return (frame_token * w.unsqueeze(-1)).sum(dim=1) / w.sum(dim=1, keepdim=True).clamp_min(1.0)

    def _coral_logits(self, token: torch.Tensor) -> torch.Tensor:
        score = self.coral_score(token)
        theta = torch.cumsum(F.softplus(self.coral_thresholds), dim=0)
        return score - theta.view(1, -1)

    def _decode(self, z: torch.Tensor, patient_token: torch.Tensor) -> dict[str, torch.Tensor]:
        if self.ordinal == "O0":
            logits = self.softmax_head(patient_token)
            probs = torch.softmax(logits, dim=1)
            q = torch.stack([probs[:, 1:].sum(1), probs[:, 2:].sum(1), probs[:, 3:].sum(1)], dim=1)
            return {"logits": logits, "probs": probs, "q": q, "a": q}
        if self.ordinal == "O1":
            logits = self._coral_logits(patient_token)
            probs = coral_logits_to_probs(logits)
            q = torch.stack([probs[:, 1:].sum(1), probs[:, 2:].sum(1), probs[:, 3:].sum(1)], dim=1)
            return {"logits": logits, "probs": probs, "q": q, "a": torch.sigmoid(logits)}
        if self.ordinal == "O2":
            logits = self.indep_head(patient_token)
            q = torch.sigmoid(logits)
            q = torch.stack([
                q[:, 0],
                torch.minimum(q[:, 0], q[:, 1]),
                torch.minimum(torch.minimum(q[:, 0], q[:, 1]), q[:, 2]),
            ], dim=1)
            probs = cumulative_to_class_probs(q)
            return {"logits": logits, "probs": probs, "q": q, "a": torch.sigmoid(logits)}
        a = torch.sigmoid(z)
        q = torch.stack([a[:, 0], a[:, 0] * a[:, 1], a[:, 0] * a[:, 1] * a[:, 2]], dim=1)
        probs = cumulative_to_class_probs(q)
        return {"logits": z, "probs": probs, "q": q, "a": a}

    def forward(self, batch: dict[str, torch.Tensor], use_alt_mask: bool = False) -> dict[str, torch.Tensor]:
        alt = use_alt_mask
        full_mask = batch["alt_full_mask"] if alt and "alt_full_mask" in batch else batch["full_mask"]
        ctx_mask = batch["alt_ctx_mask"] if alt and "alt_ctx_mask" in batch else batch["ctx_mask"]
        full_sdf = batch["alt_full_sdf"] if alt and "alt_full_sdf" in batch else batch.get("full_sdf")
        ctx_sdf = batch["alt_ctx_sdf"] if alt and "alt_ctx_sdf" in batch else batch.get("ctx_sdf")
        radial_xy = batch["alt_radial_xy"] if alt and "alt_radial_xy" in batch else batch["radial_xy"]
        radial_valid = batch["alt_radial_valid"] if alt and "alt_radial_valid" in batch else batch["radial_valid"]
        geom = batch["geom"]
        geom_valid = batch.get("geom_valid")
        enc = self.encode_frames(
            batch["full_rgb"],
            batch["ctx_rgb"],
            full_mask,
            ctx_mask,
            geom,
            radial_xy,
            radial_valid,
            full_sdf=full_sdf,
            ctx_sdf=ctx_sdf,
            geom_valid=geom_valid,
        )
        u = self._frame_evidence(enc["frame_token"], enc["radial_token"], radial_valid, batch["valid"])
        z = self._aggregate(u, enc["frame_token"], batch["valid"], batch["star"])
        patient_token = self._patient_token(enc["frame_token"], u, batch["valid"], batch["star"])
        dec = self._decode(z, patient_token)
        dec.update({
            "frame_evidence": u,
            "z": z,
            "core_full": enc["core_full"],
            "core_ctx": enc["core_ctx"],
            "patient_token": patient_token,
            "bottleneck": self.bottleneck(patient_token),
            "frame_token": enc["frame_token"],
        })
        return dec

    def set_unfreeze(self, epoch: int) -> str:
        if self.encoder is None:
            return "none"
        if epoch <= 10:
            self.encoder.freeze_stages("early")
            return "early"
        if epoch <= 40:
            self.encoder.freeze_stages("mid")
            return "mid"
        self.encoder.freeze_stages("none")
        return "none"


def build_gus_model(cfg: dict, device: torch.device | None = None) -> GUSMask2Stage:
    name = resolve_backbone_name(cfg.get("backbone") or cfg.get("backbone_name"))
    model = GUSMask2Stage(
        backbone_name=name,
        pretrained=bool(cfg.get("pretrained", True)),
        token_dim=int(cfg.get("token_dim", 192)),
        n_points=int(cfg.get("n_points", 24)),
        n_steps=len(RADIAL_OFFSETS),
        top_m=int(cfg.get("top_m", 4)),
        top_k=int(cfg.get("top_k", 2)),
        tau_b=float(cfg.get("tau_b", 0.5)),
        tau_f=float(cfg.get("tau_f", 0.5)),
        dropout=float(cfg.get("dropout", 0.1)),
        drop_path=float(cfg.get("drop_path_rate", 0.1)),
        variant=str(cfg.get("variant", "M4")),
        aggregation=str(cfg.get("aggregation", "A4")),
        ordinal=str(cfg.get("ordinal", "O3")),
        use_star=bool(cfg.get("use_star", False)),
        star_beta=float(cfg.get("star_beta", 0.15)),
    )
    if device is not None:
        model = model.to(device)
    return model


# ---------------------------------------------------------------------------
# Losses and metrics
# ---------------------------------------------------------------------------

def fold_ordinal_pn_weights(labels: np.ndarray, cap: float = 3.0) -> torch.Tensor:
    """Fixed (3, 2) pos/neg weights from the full training fold, not the mini-batch."""
    y = np.asarray(labels, dtype=int)
    n = max(len(y), 1)
    rows = []
    for thr in (0, 1, 2):
        pos = float((y > thr).sum())
        neg = float(n - pos)
        w_pos = min(cap, n / (2.0 * max(pos, 1.0)))
        w_neg = min(cap, n / (2.0 * max(neg, 1.0)))
        rows.append([w_pos, w_neg])
    return torch.tensor(rows, dtype=torch.float32)


def gus_loss(
    out: dict[str, torch.Tensor],
    y: torch.Tensor,
    cfg: dict,
    out_alt: dict[str, torch.Tensor] | None = None,
    valid: torch.Tensor | None = None,
) -> dict[str, torch.Tensor]:
    target = labels_to_cumulative(y)
    pn = cfg.get("ordinal_pn_weights")
    if pn is None:
        pn = fold_ordinal_pn_weights(y.detach().cpu().numpy())
    if not torch.is_tensor(pn):
        pn = torch.tensor(pn, dtype=torch.float32)
    # AMP forbids float16 BCE; keep the ordinal loss in fp32.
    q = out["q"].float()
    tgt = target.float()
    pn = pn.to(device=q.device, dtype=torch.float32)
    sample_w = tgt * pn[:, 0].view(1, 3) + (1.0 - tgt) * pn[:, 1].view(1, 3)
    if cfg.get("ordinal") == "O0":
        L_ord = F.cross_entropy(out["logits"].float(), y)
    elif cfg.get("ordinal") == "O1":
        raw = F.binary_cross_entropy_with_logits(out["logits"].float(), tgt, reduction="none")
        L_ord = (raw * sample_w).mean()
    else:
        q = q.clamp(1e-6, 1.0 - 1e-6)
        raw = -(tgt * torch.log(q) + (1.0 - tgt) * torch.log(1.0 - q))
        L_ord = (raw * sample_w).mean()
    L_mask = out["q"].new_zeros(())
    if out_alt is not None and float(cfg.get("lambda_mask_cons", 0.0)) > 0:
        p = out["probs"].clamp(1e-6, 1)
        q = out_alt["probs"].clamp(1e-6, 1)
        kl_pq = (p * (p.log() - q.log())).sum(dim=1)
        kl_qp = (q * (q.log() - p.log())).sum(dim=1)
        L_mask = 0.5 * (kl_pq + kl_qp).mean()
    L_view = out["q"].new_zeros(())
    if float(cfg.get("lambda_view_cons", 0.0)) > 0:
        a = F.normalize(out["core_full"], dim=-1)
        b = F.normalize(out["core_ctx"], dim=-1)
        per = 1.0 - (a * b).sum(dim=-1)
        if valid is not None:
            L_view = (per * valid.float()).sum() / valid.float().sum().clamp_min(1.0)
        else:
            L_view = per.mean()
    total = L_ord + float(cfg.get("lambda_mask_cons", 0.15)) * L_mask + float(cfg.get("lambda_view_cons", 0.05)) * L_view
    return {"loss": total, "ord": L_ord.detach(), "mask": L_mask.detach(), "view": L_view.detach()}


def quadratic_weighted_kappa(y_true: np.ndarray, y_pred: np.ndarray, n_classes: int = 4) -> float:
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)
    o = np.zeros((n_classes, n_classes), dtype=np.float64)
    for t, p in zip(y_true, y_pred):
        if 0 <= t < n_classes and 0 <= p < n_classes:
            o[t, p] += 1
    if o.sum() == 0:
        return 0.0
    hist_t = o.sum(axis=1)
    hist_p = o.sum(axis=0)
    e = np.outer(hist_t, hist_p) / o.sum()
    w = np.zeros((n_classes, n_classes), dtype=np.float64)
    for i in range(n_classes):
        for j in range(n_classes):
            w[i, j] = ((i - j) ** 2) / ((n_classes - 1) ** 2)
    den = (w * e).sum()
    if den <= 0:
        return 0.0
    return float(1.0 - (w * o).sum() / den)


def expected_calibration_error(probs: np.ndarray, y: np.ndarray, n_bins: int = 15) -> float:
    conf = probs.max(axis=1)
    pred = probs.argmax(axis=1)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        m = (conf > bins[i]) & (conf <= bins[i + 1])
        if m.sum() == 0:
            continue
        acc = float((pred[m] == y[m]).mean())
        ece += (m.mean()) * abs(acc - float(conf[m].mean()))
    return float(ece)


def score_predictions(y: np.ndarray, probs: np.ndarray) -> dict[str, Any]:
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, precision_score, roc_auc_score

    pred = probs.argmax(axis=1)
    rec = []
    prec = []
    f1c = []
    for c in range(4):
        mask = y == c
        rec.append(float((pred[mask] == c).mean()) if mask.any() else 0.0)
    prec = precision_score(y, pred, average=None, labels=[0, 1, 2, 3], zero_division=0)
    f1c = f1_score(y, pred, average=None, labels=[0, 1, 2, 3], zero_division=0)
    q_true = np.stack([(y > 0).astype(np.float64), (y > 1).astype(np.float64), (y > 2).astype(np.float64)], axis=1)
    q_pred = np.stack([probs[:, 1:].sum(1), probs[:, 2:].sum(1), probs[:, 3:].sum(1)], axis=1)
    auroc = []
    for k in range(3):
        if q_true[:, k].min() == q_true[:, k].max():
            auroc.append(float("nan"))
        else:
            auroc.append(float(roc_auc_score(q_true[:, k], q_pred[:, k])))
    onehot = np.eye(4)[y]
    brier = float(((probs - onehot) ** 2).sum(axis=1).mean())
    return {
        "n": int(len(y)),
        "accuracy": float(accuracy_score(y, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "macro_f1": float(f1_score(y, pred, average="macro", labels=[0, 1, 2, 3], zero_division=0)),
        "qwk": quadratic_weighted_kappa(y, pred),
        "recall_t1": rec[0],
        "recall_t2": rec[1],
        "recall_t3": rec[2],
        "recall_t4": rec[3],
        "precision_t1": float(prec[0]),
        "precision_t2": float(prec[1]),
        "precision_t3": float(prec[2]),
        "precision_t4": float(prec[3]),
        "f1_t1": float(f1c[0]),
        "f1_t2": float(f1c[1]),
        "f1_t3": float(f1c[2]),
        "f1_t4": float(f1c[3]),
        "auroc_t2plus": auroc[0],
        "auroc_t3plus": auroc[1],
        "auroc_t4plus": auroc[2],
        "ordinal_mae": float(np.mean(np.abs(pred - y))),
        "adjacent_error": float(np.mean(np.abs(pred - y) == 1)),
        "severe_error": float(np.mean(np.abs(pred - y) >= 2)),
        "ece": expected_calibration_error(probs, y),
        "brier": brier,
        "confusion": np.histogram2d(y, pred, bins=np.arange(5) - 0.5)[0].astype(int).tolist(),
    }


def reaggregate_frame_probs(frame_df: pd.DataFrame, mode: str, k: int = 2, tau: float = 0.5) -> pd.DataFrame:
    """Patient-level table from per-frame 4-class probabilities."""
    rows = []
    for pid, grp in frame_df.groupby("patient_id"):
        p = grp[["p_t1", "p_t2", "p_t3", "p_t4"]].to_numpy()
        y = int(grp["y_true"].iloc[0])
        q = np.stack([p[:, 1:].sum(1), p[:, 2:].sum(1), p[:, 3:].sum(1)], axis=1)
        if mode in {"B0", "A0"}:
            probs = p[0]
        elif mode in {"B1a", "B1-star", "star"}:
            if "deepest_invasion" in grp.columns and float(grp["deepest_invasion"].fillna(0).max()) > 0:
                idx = int(grp["deepest_invasion"].fillna(0).to_numpy().argmax())
            elif "area" in grp.columns:
                idx = int(grp["area"].to_numpy().argmax())
            else:
                idx = 0
            probs = p[idx]
        elif mode in {"B1b", "B1-area", "largest", "B1"}:
            idx = int(grp["area"].to_numpy().argmax()) if "area" in grp.columns else 0
            probs = p[idx]
        elif mode in {"B1c", "B1-rank", "A2", "max_rank", "B4"}:
            idx = int((p @ np.arange(4)).argmax())
            probs = p[idx]
        elif mode in {"B2", "A1", "mean"}:
            probs = p.mean(axis=0)
        elif mode in {"B3-max"}:
            qhat = q.max(axis=0)
            q1, q2, q3 = float(qhat[0]), float(min(qhat[0], qhat[1])), float(min(qhat[0], qhat[1], qhat[2]))
            probs = np.array([1 - q1, q1 - q2, q2 - q3, q3], dtype=np.float64)
            probs = np.clip(probs, 0, None)
            probs = probs / max(probs.sum(), 1e-8)
        else:
            qhat = []
            for t in range(3):
                vals = np.sort(q[:, t])[-min(k, len(q)) :]
                qhat.append(float(vals.mean()))
            q1, q2, q3 = qhat
            q2 = min(q1, q2)
            q3 = min(q2, q3)
            probs = np.array([1 - q1, q1 - q2, q2 - q3, q3], dtype=np.float64)
            probs = np.clip(probs, 0, None)
            probs = probs / max(probs.sum(), 1e-8)
        rows.append({
            "patient_id": str(pid),
            "y_true": y,
            "y_pred": int(probs.argmax()),
            "p_t1": float(probs[0]),
            "p_t2": float(probs[1]),
            "p_t3": float(probs[2]),
            "p_t4": float(probs[3]),
            "n_frames": int(len(grp)),
            "aggregation": mode,
        })
    return pd.DataFrame(rows)


def move_batch(batch: dict[str, Any], device: torch.device) -> dict[str, Any]:
    out = {}
    for k, v in batch.items():
        out[k] = v.to(device, non_blocking=True) if torch.is_tensor(v) else v
    return out


def param_groups(model: GUSMask2Stage, cfg: dict) -> list[dict]:
    new_lr = float(cfg.get("new_lr", 2e-4))
    late_lr = float(cfg.get("late_lr", 2e-5))
    early_lr = float(cfg.get("early_lr", 5e-6))
    early, late, head = [], [], []
    for name, p in model.named_parameters():
        if name.startswith("encoder."):
            if any(s in name for s in (".stages.0", ".stages.1", ".stem")):
                early.append(p)
            else:
                late.append(p)
        else:
            head.append(p)
    groups = [{"params": head, "lr": new_lr}]
    if late:
        groups.append({"params": late, "lr": late_lr})
    if early:
        groups.append({"params": early, "lr": early_lr})
    return groups


@dataclass
class RunPaths:
    report: Path
    name: str = "gus_mask2stage_20260826"
    extra: dict = field(default_factory=dict)
