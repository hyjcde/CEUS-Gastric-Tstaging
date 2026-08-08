#!/usr/bin/env python3
"""Shared contour morphology / margin / growth helpers for GC-US T-score features.

Design notes (meeting 2026-07-28 B1 + breast-US / lung-nodule CAD literature):
  - Polygon / pixel staircasing creates high-frequency "毛刺" that is not clinical.
  - Prefer NRL (normalized radial length) signatures, substantial peak counts, and
    mid-band Fourier energy over raw perimeter^2/area.
  - Substantial peaks require relative height vs mean radius (filters annotation noise).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_FRAME_CSVS = [
    "train_clinical.csv",
    "val_clinical.csv",
    "test_prospective_clinical.csv",
    "test_external_clinical.csv",
]

DEFAULT_ANATOMIC_DIR = (
    PROJECT_ROOT
    / "pipeline"
    / "data"
    / "tstaging_4class_anatomic_region_contrastive_phase0"
    / "regions"
)

DEFAULT_MASK_DIRS = [
    PROJECT_ROOT
    / "pipeline"
    / "data"
    / "tstaging_4class_region_contrastive_full"
    / "regions"
    / "lesion_pred_masks",
    PROJECT_ROOT / "pipeline" / "data" / "predicted_masks_v2",
    PROJECT_ROOT / "pipeline" / "data" / "predicted_masks",
]


def build_mask_hash_index(mask_dirs: list[Path] | None = None) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for d in mask_dirs or DEFAULT_MASK_DIRS:
        if not d.exists():
            continue
        for p in d.glob("*.png"):
            h = p.stem.rsplit("_", 1)[-1]
            if len(h) == 8 and all(c in "0123456789abcdef" for c in h.lower()):
                index.setdefault(h.lower(), p)
    return index


def resolve_mask_path(path_str: str, hash_index: dict[str, Path] | None = None) -> Path | None:
    if not path_str or not isinstance(path_str, str):
        return None
    p = Path(path_str)
    if p.exists():
        return p
    if not p.is_absolute():
        alt = (PROJECT_ROOT / path_str).resolve()
        if alt.exists():
            return alt
    if hash_index is None:
        return None
    h = p.stem.rsplit("_", 1)[-1].lower()
    return hash_index.get(h)


def resolve_image_path(path_str: object, project_root: Path | None = None) -> Path | None:
    """Resolve US image path, including external crop_ui filename aliases.

    Anatomic CSVs often store `{hospital}__{stem}.jpg` while disk files are
    `{stem}.jpg` or `sample__{token}.jpg` under the same hospital folder.
    """
    if not path_str or not isinstance(path_str, str):
        return None
    root = project_root or PROJECT_ROOT
    p = Path(path_str)
    if p.exists():
        return p
    if not p.is_absolute():
        alt = (root / path_str).resolve()
        if alt.exists():
            return alt
        p = alt
    if not p.parent.is_dir():
        return None

    parts = p.parts
    hosp = parts[parts.index("external") + 1] if "external" in parts else None
    stem, suf = p.stem, p.suffix
    token = stem.split("__")[-1]
    candidates: list[Path] = []
    if hosp and p.name.startswith(f"{hosp}__"):
        candidates.append(p.parent / p.name[len(hosp) + 2 :])
    if "__" in stem:
        candidates.append(p.parent / f"{stem.split('__', 1)[1]}{suf}")
    candidates.extend(
        [
            p.parent / f"sample__{token}{suf}",
            p.parent / f"{token}{suf}",
        ]
    )
    seen: set[Path] = set()
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        if c.is_file():
            return c
    hits = [
        f
        for f in p.parent.iterdir()
        if f.is_file()
        and f.suffix.lower() == suf.lower()
        and f.stem.split("__")[-1] == token
    ]
    return hits[0] if len(hits) == 1 else None


def load_binary_mask(path: Path) -> np.ndarray | None:
    mask = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return None
    return (mask > 127).astype(np.uint8)


def largest_contour(mask: np.ndarray) -> np.ndarray | None:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    cnt = max(contours, key=cv2.contourArea)
    if cv2.contourArea(cnt) < 10:
        return None
    return cnt[:, 0, :].astype(np.float64)


def resample_closed_contour(contour: np.ndarray, num_points: int = 256) -> np.ndarray:
    closed = np.vstack([contour, contour[:1]])
    diffs = np.diff(closed, axis=0)
    seg = np.sqrt((diffs**2).sum(axis=1))
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(cum[-1])
    if total < 1e-6:
        return np.repeat(contour[:1], num_points, axis=0)
    samples = np.linspace(0.0, total, num_points + 1, dtype=np.float64)[:-1]
    xs = np.interp(samples, cum, closed[:, 0])
    ys = np.interp(samples, cum, closed[:, 1])
    return np.stack([xs, ys], axis=1)


def moving_average_circular(x: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return x.copy()
    w = int(window) | 1  # odd
    pad = w // 2
    xp = np.concatenate([x[-pad:], x, x[:pad]])
    kernel = np.ones(w, dtype=np.float64) / w
    return np.convolve(xp, kernel, mode="valid")


def nrl_signature(contour: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (radial distances, normalized NRL, centroid)."""
    c = contour.mean(axis=0)
    d = np.sqrt(((contour - c) ** 2).sum(axis=1))
    dmax = float(d.max()) if d.size else 0.0
    nrl = d / dmax if dmax > 1e-6 else np.zeros_like(d)
    return d, nrl, c


def find_substantial_peaks(
    d: np.ndarray,
    min_rel_height: float = 0.08,
    min_sep: int = 8,
) -> list[dict[str, float]]:
    """Peak-find on radial distance; keep peaks taller than min_rel_height * mean(d)."""
    if d.size < 16:
        return []
    mean_d = float(d.mean())
    if mean_d < 1e-6:
        return []
    thr = mean_d * (1.0 + min_rel_height)
    # simple circular local-max
    left = np.roll(d, 1)
    right = np.roll(d, -1)
    is_peak = (d >= left) & (d >= right) & (d >= thr)
    idxs = np.where(is_peak)[0]
    if len(idxs) == 0:
        return []
    # non-maximum suppression by separation
    order = idxs[np.argsort(d[idxs])[::-1]]
    kept: list[int] = []
    for i in order:
        if all(min(abs(i - k), len(d) - abs(i - k)) >= min_sep for k in kept):
            kept.append(int(i))
    peaks = []
    for i in sorted(kept):
        # half-max width (circular)
        half = mean_d + 0.5 * (float(d[i]) - mean_d)
        # walk left/right until below half
        left_w = 0
        j = i
        for _ in range(len(d)):
            j = (j - 1) % len(d)
            left_w += 1
            if d[j] <= half:
                break
        right_w = 0
        j = i
        for _ in range(len(d)):
            j = (j + 1) % len(d)
            right_w += 1
            if d[j] <= half:
                break
        width = left_w + right_w
        height = float(d[i] - mean_d)
        sharpness = height / max(width, 1.0)
        peaks.append(
            {
                "index": float(i),
                "height_rel": height / mean_d,
                "width": float(width),
                "sharpness": float(sharpness),
            }
        )
    return peaks


def fourier_band_energies(nrl: np.ndarray) -> dict[str, float]:
    """Band energies of NRL signature (scale-normalized by total power)."""
    if nrl.size < 8:
        return {
            "fd_low_energy": 0.0,
            "fd_mid_energy": 0.0,
            "fd_high_energy": 0.0,
            "fd_very_high_energy": 0.0,
        }
    # remove DC
    x = nrl - nrl.mean()
    fft = np.fft.rfft(x)
    power = np.abs(fft) ** 2
    # bins: 1-3 low (ellipse), 4-12 mid (lobulation), 13-30 high (fine spicules),
    # rest very-high (annotation noise)
    n = len(power)
    bands = {
        "fd_low_energy": (1, min(4, n)),
        "fd_mid_energy": (4, min(13, n)),
        "fd_high_energy": (13, min(31, n)),
        "fd_very_high_energy": (31, n),
    }
    total = float(power[1:].sum()) + 1e-12
    out = {}
    for name, (a, b) in bands.items():
        out[name] = float(power[a:b].sum() / total) if b > a else 0.0
    return out


def compute_morphology_features(mask: np.ndarray, num_points: int = 256) -> dict[str, Any]:
    """NRL + substantial-peak + Fourier morphology pack (morph_*)."""
    empty = {
        "morph_valid": 0.0,
        "morph_area_px": 0.0,
        "morph_perimeter_px": 0.0,
        "morph_circularity": 0.0,
        "morph_solidity": 0.0,
        "morph_convexity": 0.0,
        "morph_concavity_ratio": 0.0,
        "morph_aspect_ratio": 1.0,
        "morph_nrl_std": 0.0,
        "morph_nrl_entropy": 0.0,
        "morph_nrl_zero_crossing": 0.0,
        "morph_nrl_roughness": 0.0,
        "morph_nrl_area_ratio": 0.0,
        "morph_n_substantial_peaks": 0.0,
        "morph_n_spicule_like": 0.0,
        "morph_n_lobule_like": 0.0,
        "morph_peak_sharpness_max": 0.0,
        "morph_peak_height_rel_max": 0.0,
        "morph_fd_low_energy": 0.0,
        "morph_fd_mid_energy": 0.0,
        "morph_fd_high_energy": 0.0,
        "morph_fd_very_high_energy": 0.0,
        "morph_irregularity_index": 0.0,
        "morph_legacy_perimeter_area": 0.0,
    }
    mask_bin = (mask > 0).astype(np.uint8) if mask.dtype != np.uint8 else mask
    if mask_bin.max() > 1:
        mask_bin = (mask_bin > 127).astype(np.uint8)
    contour = largest_contour(mask_bin)
    if contour is None:
        return empty

    cnt_i = np.round(contour).astype(np.int32)
    area = float(cv2.contourArea(cnt_i))
    peri = float(cv2.arcLength(cnt_i, True))
    if area < 10 or peri < 1:
        return empty
    hull = cv2.convexHull(cnt_i)
    hull_area = float(cv2.contourArea(hull))
    hull_peri = float(cv2.arcLength(hull, True))
    circularity = 4.0 * math.pi * area / max(peri * peri, 1e-6)
    solidity = area / max(hull_area, 1e-6)
    convexity = hull_peri / max(peri, 1e-6)
    concavity = max(hull_area - area, 0.0) / max(hull_area, 1e-6)
    x, y, w, h = cv2.boundingRect(cnt_i)
    aspect = float(w) / float(h) if h > 0 else 1.0
    legacy = float(np.log1p((peri * peri) / (area + 1e-6)))

    resampled = resample_closed_contour(contour, num_points)
    d_raw, nrl_raw, _ = nrl_signature(resampled)
    # light circular MA: ~2.3% of perimeter wavelength (window=7 on 256)
    d_s = moving_average_circular(d_raw, 7)
    nrl_s = d_s / max(float(d_s.max()), 1e-6)

    mean_d = float(d_s.mean())
    nrl_std = float(nrl_s.std())
    # entropy of NRL histogram
    hist, _ = np.histogram(nrl_s, bins=16, range=(0.0, 1.0), density=True)
    hist = hist / (hist.sum() + 1e-12)
    nrl_entropy = float(-(hist * np.log2(hist + 1e-12)).sum())
    # zero crossings of demeaned NRL
    demean = nrl_s - nrl_s.mean()
    zc = np.sum((demean * np.roll(demean, -1)) < 0)
    # contour roughness on NRL (sum |Δ| / N)
    nrl_rough = float(np.mean(np.abs(np.diff(nrl_s, append=nrl_s[0]))))
    # area ratio outside mean radius
    outside = np.maximum(d_s - mean_d, 0.0)
    nrl_area_ratio = float(outside.sum() / (d_s.sum() + 1e-12))

    peaks = find_substantial_peaks(d_s, min_rel_height=0.08, min_sep=max(6, num_points // 32))
    # classify: spicule-like if sharpness high and width narrow; else lobule-like
    n_spic = 0
    n_lob = 0
    for p in peaks:
        # width in points; on 256 pts, width<=18 (~7% perimeter) and sharpness high → spicule
        if p["width"] <= 18 and p["sharpness"] >= 0.15:
            n_spic += 1
        else:
            n_lob += 1
    sharp_max = max((p["sharpness"] for p in peaks), default=0.0)
    hrel_max = max((p["height_rel"] for p in peaks), default=0.0)

    bands = fourier_band_energies(nrl_s)
    # composite irregularity: mid+high FD + substantial peaks + concavity (very-high excluded)
    irreg = (
        0.35 * bands["fd_mid_energy"]
        + 0.25 * bands["fd_high_energy"]
        + 0.20 * min(len(peaks) / 6.0, 1.0)
        + 0.20 * min(concavity / 0.25, 1.0)
    )

    return {
        "morph_valid": 1.0,
        "morph_area_px": area,
        "morph_perimeter_px": peri,
        "morph_circularity": float(min(circularity, 2.0)),
        "morph_solidity": float(solidity),
        "morph_convexity": float(convexity),
        "morph_concavity_ratio": float(concavity),
        "morph_aspect_ratio": float(aspect),
        "morph_nrl_std": nrl_std,
        "morph_nrl_entropy": nrl_entropy,
        "morph_nrl_zero_crossing": float(zc),
        "morph_nrl_roughness": nrl_rough,
        "morph_nrl_area_ratio": nrl_area_ratio,
        "morph_n_substantial_peaks": float(len(peaks)),
        "morph_n_spicule_like": float(n_spic),
        "morph_n_lobule_like": float(n_lob),
        "morph_peak_sharpness_max": float(sharp_max),
        "morph_peak_height_rel_max": float(hrel_max),
        "morph_fd_low_energy": bands["fd_low_energy"],
        "morph_fd_mid_energy": bands["fd_mid_energy"],
        "morph_fd_high_energy": bands["fd_high_energy"],
        "morph_fd_very_high_energy": bands["fd_very_high_energy"],
        "morph_irregularity_index": float(irreg),
        "morph_legacy_perimeter_area": legacy,
    }


def contour_outward_normals(pts: np.ndarray) -> np.ndarray:
    """Unit outward normals for a closed resampled contour."""
    tang = np.roll(pts, -1, axis=0) - np.roll(pts, 1, axis=0)
    nrm = np.stack([-tang[:, 1], tang[:, 0]], axis=1)
    nlen = np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-6
    nrm = nrm / nlen
    c = pts.mean(axis=0)
    if ((pts - c) * nrm).sum(axis=1).mean() < 0:
        nrm = -nrm
    return nrm


def sample_normal_profiles(
    gray: np.ndarray,
    pts: np.ndarray,
    half: int = 24,
) -> np.ndarray:
    """Intensity profiles along outward normals; shape (N, 2*half+1), mid=boundary."""
    normals = contour_outward_normals(pts)
    h, w = gray.shape[:2]
    offsets = np.arange(-half, half + 1, dtype=np.float64)
    out = np.zeros((len(pts), len(offsets)), dtype=np.float64)
    g = gray.astype(np.float64)
    for i, (p, n) in enumerate(zip(pts, normals)):
        xs = np.clip(np.round(p[0] + offsets * n[0]).astype(int), 0, w - 1)
        ys = np.clip(np.round(p[1] + offsets * n[1]).astype(int), 0, h - 1)
        out[i] = g[ys, xs]
    return out


def compute_spicule_image_evidence(
    gray: np.ndarray,
    mask: np.ndarray,
    pts: np.ndarray,
    half: int = 24,
) -> dict[str, np.ndarray]:
    """Per-contour-point IMAGE evidence of spiculation (not mask shape).

    Absolute US intensities saturate (speckle). Use SNR + within-contour z-scores:
      ridge_snr — |near - far| / far_std
      tip_len   — how far outward intensity stays lesion-like (esp. hypo tongue)
      angular   — ridge_snr minus neighboring rays (isolated tip)
      evidence  — fused [0,1] from within-case z(angular) and z(tip_len)
    """
    profiles = sample_normal_profiles(gray, pts, half=half)
    mid = half
    n = profiles.shape[0]
    ridge_snr = np.zeros(n)
    tip_len = np.zeros(n)
    tip_hypo = np.zeros(n)
    band_tex = np.zeros(n)
    jump = np.zeros(n)
    ridge_raw = np.zeros(n)

    mask_bin = (mask > 0).astype(np.uint8)
    if mask_bin.shape[:2] != gray.shape[:2]:
        mask_bin = cv2.resize(mask_bin, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_NEAREST)
    g = gray.astype(np.float64)
    blur = cv2.GaussianBlur(g, (0, 0), 2.0)
    var_map = cv2.GaussianBlur((g - blur) ** 2, (0, 0), 2.0)

    for i in range(n):
        pr = profiles[i]
        inside = float(pr[mid - 6 : mid].mean())
        near = pr[mid + 1 : mid + 9]
        far = pr[mid + 12 : mid + half + 1] if half >= 16 else pr[mid + 6 :]
        far_med = float(np.median(far)) if len(far) else float(near.mean())
        far_std = float(np.std(far) + 8.0)  # floor avoids tiny-std blow-up
        near_dev = float(np.max(np.abs(near - far_med)))
        ridge_raw[i] = near_dev
        ridge_snr[i] = near_dev / far_std
        jump[i] = abs(float(near[:4].mean()) - inside)

        # Tip length: consecutive outward samples closer to inside than to far field
        tlen = 0
        for k in range(1, half + 1):
            v = float(pr[mid + k])
            if abs(v - inside) <= abs(v - far_med) * 0.95:
                tlen = k
            else:
                break
        tip_len[i] = float(tlen) / float(half)
        # Hypo tongue bonus: dark lesion with dark near-outer vs bright far
        if inside + 8.0 < far_med:
            tip_hypo[i] = float(max(0.0, (far_med - float(near.mean())) / far_std))

        x, y = int(round(pts[i, 0])), int(round(pts[i, 1]))
        x0, x1 = max(0, x - 4), min(g.shape[1], x + 5)
        y0, y1 = max(0, y - 4), min(g.shape[0], y + 5)
        band_tex[i] = float(var_map[y0:y1, x0:x1].mean())

    ridge_s = moving_average_circular(ridge_snr, 5)
    angular = ridge_snr - 0.5 * (np.roll(ridge_s, 4) + np.roll(ridge_s, -4))
    angular = np.maximum(angular, 0.0)
    tip_score = tip_len + 0.35 * np.tanh(tip_hypo)

    def _z01(x: np.ndarray) -> np.ndarray:
        mu, sd = float(x.mean()), float(x.std() + 1e-6)
        z = (x - mu) / sd
        # map z to [0,1]: z=0→0.35, z=1.5→~0.75, z>=2.5→~0.95
        return np.clip(1.0 / (1.0 + np.exp(-(z - 0.6) * 1.6)), 0.0, 1.0)

    evidence = np.clip(0.55 * _z01(angular) + 0.35 * _z01(tip_score) + 0.10 * _z01(ridge_snr), 0.0, 1.0)
    return {
        "profiles": profiles,
        "ridge": ridge_raw,
        "ridge_snr": ridge_snr,
        "tip_cont": tip_score,  # alias for callers
        "tip_len": tip_len,
        "tip_hypo": tip_hypo,
        "angular": angular,
        "band_tex": band_tex,
        "jump": jump,
        "evidence": evidence,
    }


def estimate_spiculation_from_image_mask(
    image_bgr: np.ndarray,
    mask: np.ndarray,
    num_points: int = 256,
    half: int = 24,
) -> dict[str, Any]:
    """Full spiculation pack: geometry peaks gated/boosted by IMAGE evidence.

    Peak taxonomy:
      true_spicule_candidate — smooth NRL narrow peak ∩ high image evidence
      image_led_spicule      — high image-evidence peak without strong geom peak
      artifact_peak          — raw-only NRL peak (staircasing) or geom∩low evidence
      soft_not_spicule       — geom peak + soft edge + low evidence
      lobule_supported       — wide geom peak with image support
    """
    if mask.shape[:2] != image_bgr.shape[:2]:
        mask = cv2.resize(mask, (image_bgr.shape[1], image_bgr.shape[0]), interpolation=cv2.INTER_NEAREST)
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if image_bgr.ndim == 3 else image_bgr
    cnt = largest_contour(mask)
    if cnt is None:
        return {"valid": 0.0, "spic_index_v2": 0.0, "tags": [], "evidence_mean": 0.0}
    pts = resample_closed_contour(cnt, num_points)
    img_ev = compute_spicule_image_evidence(gray, mask, pts, half=half)
    evid = img_ev["evidence"]
    morph = compute_morphology_features(mask, num_points=num_points)

    d, _, _ = nrl_signature(pts)
    d_s = moving_average_circular(d, 7)
    peaks_s = find_substantial_peaks(d_s, min_rel_height=0.08, min_sep=max(6, num_points // 32))
    peaks_raw = find_substantial_peaks(d, min_rel_height=0.06, min_sep=6)
    smooth_idxs = {int(p["index"]) for p in peaks_s}

    # Image-led peaks: ABSOLUTE angular SNR local maxima (no within-case percentile)
    ang_s = moving_average_circular(img_ev["angular"], 5)
    ev_s = moving_average_circular(evid, 7)
    ev_peaks: list[dict[str, float]] = []
    thr_ang = 1.20  # absolute; typical mean ~0.5, hot tips >=1.2
    left, right = np.roll(ang_s, 1), np.roll(ang_s, -1)
    cand = np.where((ang_s >= left) & (ang_s >= right) & (ang_s >= thr_ang))[0]
    for i in cand[np.argsort(ang_s[cand])[::-1]]:
        ii = int(i)
        if len(ev_peaks) >= 5:
            break
        if all(min(abs(ii - int(p["index"])), num_points - abs(ii - int(p["index"]))) >= 12 for p in ev_peaks):
            ev_peaks.append(
                {
                    "index": float(ii),
                    "height_rel": float(ang_s[ii]),
                    "width": 8.0,
                    "sharpness": float(ang_s[ii]),
                }
            )

    def _nb_mean(arr: np.ndarray, i: int, w: int = 3) -> float:
        sl = slice(max(0, i - w), min(num_points, i + w + 1))
        return float(arr[sl].mean())

    tags: list[dict[str, Any]] = []
    claimed = set()

    for p in peaks_s:
        i = int(p["index"])
        claimed.add(i)
        e = _nb_mean(evid, i)
        ridge = _nb_mean(img_ev["ridge"], i)
        tip = _nb_mean(img_ev["tip_cont"], i)
        ang = _nb_mean(img_ev["angular"], i)
        jmp = _nb_mean(img_ev["jump"], i)
        is_spicule_geom = p["width"] <= 18 and p["sharpness"] >= 0.15
        # Cross-case comparable gate: angular SNR isolation (strongest image signal)
        pixel_ok = (ang >= 0.70) or (ang >= 0.40 and tip >= 0.30)
        softish = jmp < 35.0 and ang < 0.35
        if is_spicule_geom and pixel_ok:
            kind = "true_spicule_candidate"
        elif is_spicule_geom and ang < 0.25 and e < 0.45:
            kind = "artifact_peak"  # geom spike without image support
        elif is_spicule_geom and softish:
            kind = "soft_not_spicule"
        elif is_spicule_geom:
            kind = "geom_spicule_weak_pixel"
        elif pixel_ok:
            kind = "lobule_supported"
        else:
            kind = "lobule_or_other"
        tags.append(
            {
                "index": i,
                "kind": kind,
                "height_rel": float(p["height_rel"]),
                "width": float(p["width"]),
                "sharpness": float(p["sharpness"]),
                "evidence": e,
                "ridge": ridge,
                "tip_cont": tip,
                "angular": ang,
                "jump": jmp,
                "is_spicule_geom": bool(is_spicule_geom),
                "pixel_supported": bool(pixel_ok),
                "raw_only": False,
                "source": "geom",
            }
        )

    # raw-only staircasing
    for p in peaks_raw:
        i = int(p["index"])
        if any(min(abs(i - j), num_points - abs(i - j)) <= 4 for j in smooth_idxs):
            continue
        e = _nb_mean(evid, i)
        tags.append(
            {
                "index": i,
                "kind": "artifact_peak",
                "height_rel": float(p["height_rel"]),
                "width": float(p["width"]),
                "sharpness": float(p["sharpness"]),
                "evidence": e,
                "ridge": _nb_mean(img_ev["ridge"], i),
                "tip_cont": _nb_mean(img_ev["tip_cont"], i),
                "angular": _nb_mean(img_ev["angular"], i),
                "jump": _nb_mean(img_ev["jump"], i),
                "is_spicule_geom": False,
                "pixel_supported": False,
                "raw_only": True,
                "source": "raw",
            }
        )
        claimed.add(i)

    # image-led: evidence peak not near a claimed geom peak
    for p in ev_peaks:
        i = int(p["index"])
        if any(min(abs(i - j), num_points - abs(i - j)) <= 6 for j in claimed):
            continue
        ang_i = float(ang_s[i])
        if ang_i < 1.20:
            continue
        tags.append(
            {
                "index": i,
                "kind": "image_led_spicule",
                "height_rel": float(max(d_s[i] / (d_s.mean() + 1e-6) - 1.0, 0.0)),
                "width": 8.0,
                "sharpness": ang_i,
                "evidence": float(ev_s[i]),
                "ridge": _nb_mean(img_ev["ridge"], i),
                "tip_cont": _nb_mean(img_ev["tip_cont"], i),
                "angular": ang_i,
                "jump": _nb_mean(img_ev["jump"], i),
                "is_spicule_geom": False,
                "pixel_supported": True,
                "raw_only": False,
                "source": "image",
            }
        )

    true_peaks = [t for t in tags if t["kind"] in ("true_spicule_candidate", "image_led_spicule")]
    art_peaks = [t for t in tags if t["kind"] == "artifact_peak"]
    n_true = len(true_peaks)
    strength = float(sum(max(t.get("angular", 0.0), 0.0) * max(t["height_rel"], 0.05) for t in true_peaks))
    top_k = max(3, int(0.05 * len(evid)))
    ang = img_ev["angular"]
    ang_mean = float(ang.mean())
    ang_top = float(np.mean(np.sort(ang)[-top_k:]))
    hypo = img_ev["tip_hypo"]
    hypo_top = float(np.mean(np.sort(hypo)[-top_k:]))
    snr = img_ev["ridge_snr"]
    snr_top = float(np.mean(np.sort(snr)[-top_k:]))
    tip = img_ev["tip_cont"]
    tip_top = float(np.mean(np.sort(tip)[-top_k:]))
    evid_top = float(np.mean(np.sort(evid)[-top_k:]))
    evid_p90 = float(np.percentile(evid, 90))
    evid_hot = float(np.mean(ang >= 1.20))
    fd_high = float(morph.get("morph_fd_high_energy", 0.0))
    fd_mid = float(morph.get("morph_fd_mid_energy", 0.0))
    fd_vh = float(morph.get("morph_fd_very_high_energy", 0.0))

    # Blend: fine-shape Fourier (mask, denoised) + image angular SNR + sparse tips
    spic_index_v2 = float(
        np.clip(
            0.30 * min(fd_high / 0.20, 1.0)
            + 0.30 * np.tanh(ang_mean / 0.65)
            + 0.15 * np.tanh(ang_top / 5.0)
            + 0.10 * np.tanh(hypo_top / 4.0)
            + 0.10 * min(n_true / 3.0, 1.0)
            + 0.05 * min(evid_hot / 0.08, 1.0),
            0,
            1,
        )
    )
    return {
        "valid": 1.0,
        "pts": pts,
        "d_s": d_s,
        "img_ev": img_ev,
        "morph": morph,
        "tags": tags,
        "spic_index_v2": spic_index_v2,
        "n_true_spicule": float(n_true),
        "n_image_led": float(sum(1 for t in tags if t["kind"] == "image_led_spicule")),
        "n_geom_true": float(sum(1 for t in tags if t["kind"] == "true_spicule_candidate")),
        "n_artifact_peak": float(len(art_peaks)),
        "n_geom_spicule": float(sum(1 for t in tags if t.get("is_spicule_geom"))),
        "true_peak_strength": strength,
        "evidence_mean": float(evid.mean()),
        "evidence_p90": evid_p90,
        "evidence_top": evid_top,
        "evidence_hot_frac": evid_hot,
        "angular_mean": ang_mean,
        "angular_top": ang_top,
        "hypo_top": hypo_top,
        "snr_top": snr_top,
        "tip_top": tip_top,
        "fd_high": fd_high,
        "fd_mid": fd_mid,
        "fd_very_high": fd_vh,
    }


def _soft_boundary_bands(
    mask_bin: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, tuple[float, float]]:
    """Erode/dilate soft bands so features tolerate ~few-px mask error.

    Returns (band, inner_rim, outer_rim, r_eq, (cx, cy)).
    """
    area = float(mask_bin.sum())
    r_eq = float(math.sqrt(max(area, 1.0) / math.pi))
    # band half-width ~4% of radius, clamped 3–10 px (absorbs staircasing / seg error)
    hw = int(np.clip(round(0.04 * r_eq), 3, 10))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * hw + 1, 2 * hw + 1))
    er = cv2.erode(mask_bin, k, iterations=1)
    di = cv2.dilate(mask_bin, k, iterations=1)
    band = ((di > 0) & (er == 0)).astype(np.uint8)
    inner = ((mask_bin > 0) & (er == 0)).astype(np.uint8)
    outer = ((di > 0) & (mask_bin == 0)).astype(np.uint8)
    m = cv2.moments(mask_bin, binaryImage=True)
    if m["m00"] < 1e-6:
        ys, xs = np.where(mask_bin > 0)
        cx, cy = float(xs.mean()), float(ys.mean())
    else:
        cx, cy = float(m["m10"] / m["m00"]), float(m["m01"] / m["m00"])
    return band, inner, outer, r_eq, (cx, cy)


def compute_circular_bof_features(
    gray: np.ndarray,
    cx: float,
    cy: float,
    r_eq: float,
    scales: tuple[float, ...] = (0.90, 1.05, 1.20, 1.35),
    n_theta: int = 128,
) -> dict[str, float]:
    """Ciompi-style circular intensity spectra (2D Bag-of-Frequencies lite).

    Circles are centered on mask centroid with radii ∝ equivalent radius — does NOT
    walk the (imprecise) contour, so small boundary shifts barely change the signal.
    """
    h, w = gray.shape[:2]
    g = gray.astype(np.float64)
    high_energies = []
    mid_energies = []
    peakiness = []
    for s in scales:
        rr = max(4.0, s * r_eq)
        theta = np.linspace(0.0, 2.0 * math.pi, n_theta, endpoint=False)
        xs = np.clip(np.round(cx + rr * np.cos(theta)).astype(int), 0, w - 1)
        ys = np.clip(np.round(cy + rr * np.sin(theta)).astype(int), 0, h - 1)
        sig = g[ys, xs]
        sig = sig - sig.mean()
        spec = np.abs(np.fft.rfft(sig)) ** 2
        total = float(spec[1:].sum()) + 1e-12
        # bins on rfft index: 1-3 low, 4-12 mid (lobulation-like), 13+ high (fine spokes)
        n = len(spec)
        mid = float(spec[4 : min(13, n)].sum() / total)
        high = float(spec[13:n].sum() / total) if n > 13 else 0.0
        mid_energies.append(mid)
        high_energies.append(high)
        # peakiness: max side-lobe vs mean (spicule-like periodic spikes)
        if n > 4:
            side = spec[2:]
            peakiness.append(float(side.max() / (side.mean() + 1e-12)))
        else:
            peakiness.append(0.0)
    return {
        "margin_bof_high_mean": float(np.mean(high_energies)),
        "margin_bof_mid_mean": float(np.mean(mid_energies)),
        "margin_bof_peakiness": float(np.mean(peakiness)),
        "margin_bof_high_maxscale": float(np.max(high_energies)),
    }


def compute_nrg_and_band_features(
    gray: np.ndarray,
    band: np.ndarray,
    inner: np.ndarray,
    outer: np.ndarray,
    cx: float,
    cy: float,
) -> dict[str, float]:
    """NRG (radial gradient coherence) + MI/MC on soft bands (mask-error tolerant)."""
    g = gray.astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx * gx + gy * gy) + 1e-6
    ys, xs = np.where(band > 0)
    if len(xs) < 20:
        return {
            "margin_nrg_mean": 0.0,
            "margin_mi_band": 0.0,
            "margin_contrast_soft": 0.0,
            "margin_band_grad_mean": 0.0,
        }
    # unit radial (outward from centroid)
    rx = xs.astype(np.float32) - cx
    ry = ys.astype(np.float32) - cy
    rlen = np.sqrt(rx * rx + ry * ry) + 1e-6
    rx /= rlen
    ry /= rlen
    # NRG: cos angle between gradient and radial (signed outward preference via |·|)
    nrg = (gx[ys, xs] * rx + gy[ys, xs] * ry) / mag[ys, xs]
    nrg_mean = float(np.mean(np.clip(nrg, -1, 1)))
    # MI: mean gradient magnitude in band (lower → more indistinct), normalize by global
    mi = float(mag[ys, xs].mean())
    mi_norm = float(mi / (float(np.percentile(mag, 90)) + 1e-6))
    # MC soft: inner rim mean intensity − outer rim mean (Tan-style, band-tolerant)
    if inner.sum() > 10 and outer.sum() > 10:
        mc = float(g[inner > 0].mean() - g[outer > 0].mean())
    else:
        mc = 0.0
    return {
        "margin_nrg_mean": nrg_mean,
        "margin_mi_band": mi_norm,
        "margin_contrast_soft": mc,
        "margin_band_grad_mean": mi,
    }


def compute_robust_shape_features(mask_bin: np.ndarray, num_points: int = 256) -> dict[str, float]:
    """Shape channel with HEAVY NRL smoothing — ignores pixel-level staircasing.

    Selected (literature-aligned, mask-imprecision aware):
      solidity / overlap (convex) — coarse irregularity
      NRL entropy/std after strong MA — not raw roughness
      needle_like (FFT low/high ratio, BMC/Zhang style)
      fd_mid / fd_high — lobulation vs fine (very-high discarded)
    """
    empty = {
        "margin_shape_solidity": 0.0,
        "margin_shape_overlap": 0.0,
        "margin_shape_nrl_entropy": 0.0,
        "margin_shape_nrl_std": 0.0,
        "margin_shape_needle_like": 0.0,
        "margin_shape_fd_mid": 0.0,
        "margin_shape_fd_high": 0.0,
        "margin_shape_lobulation": 0.0,
    }
    contour = largest_contour(mask_bin)
    if contour is None:
        return empty
    cnt_i = np.round(contour).astype(np.int32)
    area = float(cv2.contourArea(cnt_i))
    if area < 10:
        return empty
    hull = cv2.convexHull(cnt_i)
    hull_area = float(cv2.contourArea(hull))
    solidity = area / max(hull_area, 1e-6)
    overlap = solidity  # area/hull
    pts = resample_closed_contour(contour, num_points)
    d, _, _ = nrl_signature(pts)
    # strong circular MA (~6% perimeter) kills staircasing spikes
    d_s = moving_average_circular(d, 15)
    nrl = d_s / max(float(d_s.max()), 1e-6)
    nrl_std = float(nrl.std())
    hist, _ = np.histogram(nrl, bins=16, range=(0.0, 1.0), density=True)
    hist = hist / (hist.sum() + 1e-12)
    nrl_entropy = float(-(hist * np.log2(hist + 1e-12)).sum())
    bands = fourier_band_energies(nrl)
    # BMC-style needle-like: low-ω energy / high-ω energy on rFFT of demeaned NRL
    x = nrl - nrl.mean()
    spec = np.abs(np.fft.rfft(x)) ** 2
    n = len(spec)
    # map BMC ω∈[0,π/4]≈ low indices, (π/4,π]≈ higher
    low = float(spec[1 : max(2, n // 4)].sum()) + 1e-12
    high = float(spec[max(2, n // 4) :].sum()) + 1e-12
    needle = float(np.clip(high / low, 0.0, 5.0) / 5.0)  # invert BMC MS so high=spicule-like
    # lobulation: extrema on heavily smoothed NRL (BMC ML idea)
    d_lob = moving_average_circular(d, 21)
    left, right = np.roll(d_lob, 1), np.roll(d_lob, -1)
    n_ext = int(np.sum((d_lob >= left) & (d_lob >= right)) + np.sum((d_lob <= left) & (d_lob <= right)))
    lobulation = float(min(n_ext / 12.0, 1.0))
    return {
        "margin_shape_solidity": float(solidity),
        "margin_shape_overlap": float(overlap),
        "margin_shape_nrl_entropy": nrl_entropy,
        "margin_shape_nrl_std": nrl_std,
        "margin_shape_needle_like": needle,
        "margin_shape_fd_mid": float(bands["fd_mid_energy"]),
        "margin_shape_fd_high": float(bands["fd_high_energy"]),
        "margin_shape_lobulation": lobulation,
    }


def compute_robust_margin_features(image_bgr: np.ndarray | None, mask: np.ndarray) -> dict[str, Any]:
    """Selected margin/morph pack robust to non-pixel-accurate masks.

    Primary (image, soft-band / circles):
      BoF high/mid/peakiness, NRG, MI, soft margin contrast
    Secondary (shape, heavy-smoothed NRL):
      solidity, NRL entropy/std, needle_like, fd_mid/high, lobulation
    Composites:
      margin_spic_robust  — spiculation candidacy
      margin_clear_robust — clear/sharp margin candidacy
    """
    empty = {
        "margin_valid": 0.0,
        "margin_bof_high_mean": 0.0,
        "margin_bof_mid_mean": 0.0,
        "margin_bof_peakiness": 0.0,
        "margin_bof_high_maxscale": 0.0,
        "margin_nrg_mean": 0.0,
        "margin_mi_band": 0.0,
        "margin_contrast_soft": 0.0,
        "margin_band_grad_mean": 0.0,
        "margin_shape_solidity": 0.0,
        "margin_shape_overlap": 0.0,
        "margin_shape_nrl_entropy": 0.0,
        "margin_shape_nrl_std": 0.0,
        "margin_shape_needle_like": 0.0,
        "margin_shape_fd_mid": 0.0,
        "margin_shape_fd_high": 0.0,
        "margin_shape_lobulation": 0.0,
        "margin_spic_robust": 0.0,
        "margin_clear_robust": 0.0,
        "margin_band_halfwidth_px": 0.0,
    }
    mask_bin = (mask > 0).astype(np.uint8) if mask.dtype != np.uint8 else mask
    if mask_bin.max() > 1:
        mask_bin = (mask_bin > 127).astype(np.uint8)
    if mask_bin.sum() < 10:
        return empty
    band, inner, outer, r_eq, (cx, cy) = _soft_boundary_bands(mask_bin)
    hw = int(np.clip(round(0.04 * r_eq), 3, 10))
    shape = compute_robust_shape_features(mask_bin)
    if image_bgr is None:
        bof = {k: 0.0 for k in ("margin_bof_high_mean", "margin_bof_mid_mean", "margin_bof_peakiness", "margin_bof_high_maxscale")}
        band_f = {
            "margin_nrg_mean": 0.0,
            "margin_mi_band": 0.0,
            "margin_contrast_soft": 0.0,
            "margin_band_grad_mean": 0.0,
        }
    else:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if image_bgr.ndim == 3 else image_bgr
        if gray.shape[:2] != mask_bin.shape[:2]:
            mask_bin = cv2.resize(mask_bin, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_NEAREST)
            band, inner, outer, r_eq, (cx, cy) = _soft_boundary_bands(mask_bin)
            hw = int(np.clip(round(0.04 * r_eq), 3, 10))
            shape = compute_robust_shape_features(mask_bin)
        bof = compute_circular_bof_features(gray, cx, cy, r_eq)
        band_f = compute_nrg_and_band_features(gray, band, inner, outer, cx, cy)

    # Spiculation / irregularity candidacy (mask-imprecision aware):
    #   heavy-smoothed fd_high + low solidity are most stable & T-linked in probes;
    #   BoF/needle are image/shape auxiliaries (not contour peak counts).
    spic = float(
        np.clip(
            0.35 * min(shape["margin_shape_fd_high"] / 0.20, 1.0)
            + 0.25 * float(np.clip(1.0 - shape["margin_shape_solidity"], 0, 1))
            + 0.20 * np.tanh(bof["margin_bof_high_mean"] / 0.25)
            + 0.10 * shape["margin_shape_needle_like"]
            + 0.10 * np.tanh(bof["margin_bof_peakiness"] / 8.0),
            0,
            1,
        )
    )
    # Clear margin: high NRG + high |contrast| + high MI (sharp band gradient)
    clear = float(
        np.clip(
            0.45 * np.clip((band_f["margin_nrg_mean"] + 1.0) / 2.0, 0, 1)
            + 0.30 * np.tanh(abs(band_f["margin_contrast_soft"]) / 25.0)
            + 0.25 * np.tanh(band_f["margin_mi_band"] / 0.6),
            0,
            1,
        )
    )
    return {
        "margin_valid": 1.0,
        **bof,
        **band_f,
        **shape,
        "margin_spic_robust": spic,
        "margin_clear_robust": clear,
        "margin_band_halfwidth_px": float(hw),
    }


def compute_margin_features(image_bgr: np.ndarray | None, mask: np.ndarray) -> dict[str, Any]:
    """Selected margin features (mask-imprecision aware).

    Primary: compute_robust_margin_features (BoF + NRG/MI/MC + heavy-smoothed shape).
    Legacy aliases kept for older CSVs/readers.
    """
    robust = compute_robust_margin_features(image_bgr, mask)
    if robust.get("margin_valid", 0) < 1:
        return {
            "margin_valid": 0.0,
            "margin_gradient_mean": 0.0,
            "margin_gradient_p25": 0.0,
            "margin_gradient_p75": 0.0,
            "margin_gradient_contrast": 0.0,
            "margin_curvature_p90": 0.0,
            "margin_peak_density": 0.0,
            "margin_weak_segment_ratio": 0.0,
            "margin_spicule_score": 0.0,
            "margin_spic_index_v2": 0.0,
            "margin_n_true_spicule": 0.0,
            "margin_n_image_led_spicule": 0.0,
            "margin_evidence_p90": 0.0,
            "margin_n_artifact_peak": 0.0,
            **{k: 0.0 for k in robust},
        }
    # Legacy aliases → robust quantities (do not re-walk imprecise contour for scoring)
    return {
        **robust,
        "margin_gradient_mean": float(robust["margin_band_grad_mean"]),
        "margin_gradient_p25": 0.0,
        "margin_gradient_p75": 0.0,
        "margin_gradient_contrast": float(abs(robust["margin_contrast_soft"])),
        "margin_curvature_p90": float(robust["margin_shape_nrl_std"]),
        "margin_peak_density": float(robust["margin_shape_lobulation"]),
        "margin_weak_segment_ratio": float(np.clip(1.0 - robust["margin_clear_robust"], 0, 1)),
        "margin_spicule_score": float(robust["margin_spic_robust"]),
        "margin_spic_index_v2": float(robust["margin_spic_robust"]),
        "margin_n_true_spicule": 0.0,
        "margin_n_image_led_spicule": 0.0,
        "margin_evidence_p90": float(robust["margin_bof_high_mean"]),
        "margin_n_artifact_peak": 0.0,
    }


def lumen_mask_from_box(
    h: int,
    w: int,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> np.ndarray | None:
    if not (np.isfinite([x1, y1, x2, y2]).all()):
        return None
    xa, xb = int(round(min(x1, x2))), int(round(max(x1, x2)))
    ya, yb = int(round(min(y1, y2))), int(round(max(y1, y2)))
    xa = max(0, xa)
    ya = max(0, ya)
    xb = min(w, xb)
    yb = min(h, yb)
    if xb <= xa or yb <= ya:
        return None
    m = np.zeros((h, w), dtype=np.uint8)
    m[ya:yb, xa:xb] = 255
    return m


def compute_growth_features(
    mask: np.ndarray,
    lumen_mask: np.ndarray | None,
) -> dict[str, Any]:
    """SDF-based breakthrough / growth proxies (growth_* / bt_v2_*)."""
    from scipy import ndimage

    empty = {
        "growth_valid": 0.0,
        "bt_v2_max_outward_depth": 0.0,
        "bt_v2_mean_outward_depth": 0.0,
        "bt_v2_fraction_outside_lumen": 0.0,
        "bt_v2_fraction_inside_lumen": 0.0,
        "bt_v2_contact_arc_ratio": 0.0,
        "bt_v2_breakthrough_flag": 0.0,
        "growth_outward_protrusion_ratio": 0.0,
    }
    mask_bin = (mask > 0).astype(np.uint8) if mask.dtype != np.uint8 else mask
    if mask_bin.max() > 1:
        mask_bin = (mask_bin > 127).astype(np.uint8)
    if mask_bin.sum() < 10 or lumen_mask is None:
        return empty
    lumen_bin = (lumen_mask > 127).astype(np.uint8)
    if lumen_bin.sum() < 10:
        return empty

    dist_out = ndimage.distance_transform_edt(lumen_bin == 0)
    dist_in = ndimage.distance_transform_edt(lumen_bin > 0)
    sdf = dist_out - dist_in
    depths = sdf[mask_bin > 0]
    if depths.size == 0:
        return empty
    outward = depths[depths > 0]
    frac_out = float((depths > 0).sum() / depths.size)
    frac_in = float((depths < 0).sum() / depths.size)
    max_out = float(depths.max())
    mean_out = float(outward.mean()) if outward.size else 0.0

    lumen_boundary = cv2.Canny(lumen_bin * 255, 50, 150) > 0
    lesion_dilated = cv2.dilate(mask_bin, np.ones((7, 7), np.uint8), iterations=1)
    contact = lumen_boundary & (lesion_dilated > 0)
    peri = max(int(lumen_boundary.sum()), 1)
    contact_ratio = float(contact.sum() / peri)
    bt_flag = 1.0 if frac_out > 0.3 else 0.0

    # outward protrusion vs smooth radial baseline of lesion itself
    contour = largest_contour(mask_bin)
    protr = 0.0
    if contour is not None:
        rs = resample_closed_contour(contour, 256)
        d, _, _ = nrl_signature(rs)
        d_s = moving_average_circular(d, 11)  # smoother baseline
        protr = float(np.mean(np.maximum(d - d_s, 0.0) / (d_s.mean() + 1e-6)))

    return {
        "growth_valid": 1.0,
        "bt_v2_max_outward_depth": max_out,
        "bt_v2_mean_outward_depth": mean_out,
        "bt_v2_fraction_outside_lumen": frac_out,
        "bt_v2_fraction_inside_lumen": frac_in,
        "bt_v2_contact_arc_ratio": contact_ratio,
        "bt_v2_breakthrough_flag": bt_flag,
        "growth_outward_protrusion_ratio": protr,
    }


def aggregate_patient_features(
    frame_df,
    feature_cols: list[str],
    id_col: str = "patient_id",
) -> Any:
    import pandas as pd

    work = frame_df.copy()
    work[id_col] = work[id_col].astype(str)
    med = work.groupby(id_col, as_index=False)[feature_cols].median(numeric_only=True)
    mx = work.groupby(id_col, as_index=False)[feature_cols].max(numeric_only=True)
    mx = mx.rename(columns={c: f"{c}__max" for c in feature_cols})
    p90 = work.groupby(id_col, as_index=False)[feature_cols].quantile(0.9)
    p90 = p90.rename(columns={c: f"{c}__p90" for c in feature_cols})
    out = med.merge(mx, on=id_col, how="left").merge(p90, on=id_col, how="left")
    n = work.groupby(id_col).size().rename("n_frames").reset_index()
    return out.merge(n, on=id_col, how="left")
