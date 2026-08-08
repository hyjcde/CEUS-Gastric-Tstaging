#!/usr/bin/env python3
"""GC-US margin pilot v2: local pixel scores + color contour (readable differences).

Key idea: averaging all normal profiles washes out spicules.
Instead, score EVERY contour point with pixel evidence, then:
  - paint the contour blue→red by local roughness/indistinctness
  - polar plot of local score around the lesion
  - mark mask-only peaks (geometry peak but pixel-smooth = artifact)
  - stage board: 8 ROI crops with the same color scale

Rebuild:
  python3 scripts/viz_gc_us_margin_pixel_examples.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import cm
from matplotlib.colors import Normalize
from matplotlib.gridspec import GridSpec

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from gc_us_contour_features import (  # noqa: E402
    DEFAULT_ANATOMIC_DIR,
    DEFAULT_FRAME_CSVS,
    build_mask_hash_index,
    compute_morphology_features,
    find_substantial_peaks,
    largest_contour,
    load_binary_mask,
    moving_average_circular,
    nrl_signature,
    resample_closed_contour,
    resolve_mask_path,
)

OUT_DIR = (
    PROJECT_ROOT
    / "pipeline"
    / "experiments"
    / "reports"
    / "gc_us_tscore_feature_stats_v1"
    / "margin_pixel_pilot"
)
STAGE = {0: "T1", 1: "T2", 2: "T3", 3: "T4+"}
HALF = 16  # normal half-width in px


def apply_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "Times New Roman",
            "font.size": 9,
            "axes.facecolor": "black",
            "figure.facecolor": "black",
            "savefig.facecolor": "black",
            "text.color": "white",
            "axes.labelcolor": "white",
            "axes.edgecolor": "#555555",
            "xtick.color": "white",
            "ytick.color": "white",
            "axes.titlecolor": "white",
            "grid.color": "#333333",
        }
    )


def load_frames() -> pd.DataFrame:
    parts = []
    for name in DEFAULT_FRAME_CSVS:
        p = DEFAULT_ANATOMIC_DIR / name
        if p.exists():
            df = pd.read_csv(p)
            df["split_file"] = name
            parts.append(df)
    return pd.concat(parts, ignore_index=True)


def resolve_image(path_str: object) -> Path | None:
    if not path_str or not isinstance(path_str, str):
        return None
    p = Path(path_str)
    if p.exists():
        return p
    alt = (PROJECT_ROOT / path_str).resolve()
    return alt if alt.exists() else None


def contour_normals(pts: np.ndarray) -> np.ndarray:
    tang = np.roll(pts, -1, axis=0) - np.roll(pts, 1, axis=0)
    nrm = np.stack([-tang[:, 1], tang[:, 0]], axis=1)
    nlen = np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-6
    nrm = nrm / nlen
    c = pts.mean(axis=0)
    if ((pts - c) * nrm).sum(axis=1).mean() < 0:
        nrm = -nrm
    return nrm


def sample_profiles(gray: np.ndarray, pts: np.ndarray, half: int = HALF) -> np.ndarray:
    normals = contour_normals(pts)
    h, w = gray.shape
    offsets = np.arange(-half, half + 1, dtype=np.float64)
    out = np.zeros((len(pts), len(offsets)), dtype=np.float64)
    for i, (p, n) in enumerate(zip(pts, normals)):
        xs = np.clip(np.round(p[0] + offsets * n[0]).astype(int), 0, w - 1)
        ys = np.clip(np.round(p[1] + offsets * n[1]).astype(int), 0, h - 1)
        out[i] = gray[ys, xs]
    return out


def local_pixel_scores(profiles: np.ndarray, half: int = HALF) -> dict[str, np.ndarray]:
    """Per-contour-point pixel scores with ABSOLUTE scales (comparable across cases).

    High score = indistinct / soft margin (clinically closer to '毛糙/浸润感').

    Note: raw outer-profile HF ('ripple') is mostly US speckle and does NOT discriminate;
    the dominant absolute signal is edge contrast (jump × sharpness), with a small
    circumferential irregularity term so local arcs can still turn red/blue.
    """
    mid = half
    n = profiles.shape[0]
    jump = np.zeros(n)
    sharp = np.zeros(n)
    spoke = np.zeros(n)
    for i in range(n):
        pr = profiles[i].astype(np.float64)
        inside = pr[mid - 5 : mid].mean()
        outside = pr[mid + 1 : mid + 5].mean()
        jump[i] = abs(outside - inside)
        win = pr[mid - 3 : mid + 4]
        sharp[i] = float(np.max(np.abs(np.gradient(win))))
        outer = pr[mid + 1 :]
        x = np.arange(len(outer), dtype=np.float64)
        a, b = np.linalg.lstsq(np.vstack([x, np.ones_like(x)]).T, outer, rcond=None)[0]
        resid = outer - (a * x + b)
        spoke[i] = float(np.mean(np.clip(resid, 0.0, None)))

    jump_hf = np.abs(jump - moving_average_circular(jump, 21))
    # Clear edge ≈ high jump AND high local gradient; invert for rough/indistinct.
    clear = np.tanh(jump / 70.0) * np.tanh(sharp / 14.0)
    indistinct = 1.0 - clear
    circ = np.tanh(jump_hf / 20.0)
    spoke_n = np.tanh(spoke / 10.0)
    score = np.clip(0.75 * indistinct + 0.15 * circ + 0.10 * spoke_n, 0.0, 1.0)
    return {
        "jump": jump,
        "sharp": sharp,
        "spoke": spoke,
        "jump_hf": jump_hf,
        "clear": clear,
        "score": score,
    }


def crop_roi(image: np.ndarray, mask: np.ndarray, pad_ratio: float = 0.45, min_pad: int = 28):
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return image, mask, (0, 0)
    x1, x2 = int(xs.min()), int(xs.max())
    y1, y2 = int(ys.min()), int(ys.max())
    bw, bh = x2 - x1 + 1, y2 - y1 + 1
    pad = max(min_pad, int(max(bw, bh) * pad_ratio))
    H, W = mask.shape[:2]
    xa, xb = max(0, x1 - pad), min(W, x2 + pad + 1)
    ya, yb = max(0, y1 - pad), min(H, y2 + pad + 1)
    return image[ya:yb, xa:xb].copy(), mask[ya:yb, xa:xb].copy(), (xa, ya)


def colorize_contour(
    image_bgr: np.ndarray,
    pts: np.ndarray,
    scores: np.ndarray,
    vmin: float,
    vmax: float,
    thickness: int = 5,
) -> np.ndarray:
    """Draw contour segments colored by ABSOLUTE local score (global vmin/vmax)."""
    # Darken base so turbo blue/red pops against US gray.
    out = (image_bgr.astype(np.float32) * 0.55).astype(np.uint8)
    try:
        cmap = plt.colormaps["turbo"]
    except Exception:
        cmap = cm.get_cmap("turbo")
    s = moving_average_circular(scores, 7)
    denom = max(vmax - vmin, 1e-6)
    n = len(pts)
    # Gamma < 1 stretches mid-high scores toward red for readability.
    for i in range(n):
        p0 = tuple(np.round(pts[i]).astype(int))
        p1 = tuple(np.round(pts[(i + 1) % n]).astype(int))
        t = float(np.clip((s[i] - vmin) / denom, 0, 1)) ** 0.75
        rgba = cmap(t)
        bgr = (int(rgba[2] * 255), int(rgba[1] * 255), int(rgba[0] * 255))
        cv2.line(out, p0, p1, bgr, thickness, cv2.LINE_AA)
        # outer glow for visibility
        cv2.line(out, p0, p1, bgr, max(1, thickness - 2), cv2.LINE_AA)
    return out


def mark_artifact_peaks(
    image_bgr: np.ndarray,
    pts: np.ndarray,
    d_s: np.ndarray,
    local_score: np.ndarray,
) -> tuple[np.ndarray, list[dict]]:
    """Geometry peak + low local pixel score → white X (artifact). High both → magenta."""
    peaks = find_substantial_peaks(d_s, min_rel_height=0.08, min_sep=8)
    out = image_bgr.copy()
    tags = []
    score_med = float(np.median(local_score))
    for p in peaks:
        i = int(p["index"])
        # neighborhood pixel score
        nb = local_score[max(0, i - 4) : i + 5]
        loc = float(nb.mean()) if len(nb) else 0.0
        pt = tuple(np.round(pts[i]).astype(int))
        if loc < score_med * 0.85:
            # artifact-like
            cv2.drawMarker(out, pt, (255, 255, 255), markerType=cv2.MARKER_TILTED_CROSS, markerSize=14, thickness=2)
            tags.append({"index": i, "kind": "artifact", "local_score": loc, "height_rel": p["height_rel"]})
        else:
            cv2.circle(out, pt, 6, (255, 0, 255), 2)
            tags.append({"index": i, "kind": "supported", "local_score": loc, "height_rel": p["height_rel"]})
    return out, tags


def pick_examples_by_pixel(
    joined: pd.DataFrame,
    frames: pd.DataFrame,
    hash_index: dict,
    per_stage_probe: int = 36,
) -> pd.DataFrame:
    """Probe mid-length patients, score by PIXEL, pick clearest vs roughest per stage."""
    rows = []
    for lab in range(4):
        sub = joined[joined["label"] == lab].dropna(subset=["tumor_length_cm"])
        if sub.empty:
            continue
        lo, hi = sub["tumor_length_cm"].quantile([0.25, 0.75])
        mid = sub[(sub["tumor_length_cm"] >= lo) & (sub["tumor_length_cm"] <= hi)]
        if len(mid) < 6:
            mid = sub
        take_n = min(per_stage_probe, len(mid))
        probe = mid.sample(n=take_n, random_state=42) if len(mid) > take_n else mid
        scored = []
        for _, r in probe.iterrows():
            fr = choose_frame(frames, str(r["patient_id"]), hash_index)
            if fr is None:
                continue
            image = cv2.imread(fr["_image_path"])
            mask = load_binary_mask(Path(fr["_mask_path"]))
            if image is None or mask is None:
                continue
            try:
                case = analyze_case(image, mask)
            except Exception:
                continue
            scored.append(
                {
                    **r.to_dict(),
                    "px_score_mean": case["summary"]["px_score_mean"],
                    "px_rough_frac": case["summary"]["px_rough_frac"],
                    "px_score_p90": case["summary"]["px_score_p90"],
                    "_case": case,
                    "_image_path": fr["_image_path"],
                    "_mask_path": fr["_mask_path"],
                }
            )
        if len(scored) < 2:
            continue
        sdf = pd.DataFrame(scored)
        low = sdf.nsmallest(1, "px_score_mean").iloc[0]
        high = sdf.nlargest(1, "px_score_mean").iloc[0]
        for tag, rec in [("clear_pixel", low), ("rough_pixel", high)]:
            d = rec.to_dict()
            d["arm"] = tag
            rows.append(d)
        print(f"[pick] {STAGE[lab]} probed={len(scored)} clear={low['patient_id']}({low['px_score_mean']:.3f}) rough={high['patient_id']}({high['px_score_mean']:.3f})")
    return pd.DataFrame(rows)


def choose_frame(frames: pd.DataFrame, patient_id: str, hash_index: dict) -> pd.Series | None:
    cand = frames[frames["patient_id"].astype(str) == str(patient_id)]
    best, best_area = None, -1
    for _, row in cand.iterrows():
        mp = resolve_mask_path(str(row.get("lesion_pred_mask_path", "")), hash_index)
        ip = resolve_image(row.get("image_path"))
        if mp is None or ip is None:
            continue
        mask = load_binary_mask(mp)
        if mask is None:
            continue
        area = int(mask.sum())
        if area > best_area:
            best_area = area
            best = row.copy()
            best["_mask_path"] = str(mp)
            best["_image_path"] = str(ip)
    return best


def analyze_case(image_bgr: np.ndarray, mask: np.ndarray) -> dict:
    if mask.shape[:2] != image_bgr.shape[:2]:
        mask = cv2.resize(mask, (image_bgr.shape[1], image_bgr.shape[0]), interpolation=cv2.INTER_NEAREST)
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    cnt = largest_contour(mask)
    if cnt is None:
        raise ValueError("empty contour")
    pts = resample_closed_contour(cnt, 256)
    profiles = sample_profiles(gray, pts, HALF)
    local = local_pixel_scores(profiles, HALF)
    morph = compute_morphology_features(mask)
    d, _, _ = nrl_signature(pts)
    d_s = moving_average_circular(d, 7)
    score = local["score"]
    # summary stats
    summary = {
        "px_score_mean": float(score.mean()),
        "px_score_p90": float(np.percentile(score, 90)),
        "px_rough_frac": float(np.mean(score > 0.45)),
        "px_jump_mean": float(local["jump"].mean()),
        "px_sharp_mean": float(local["sharp"].mean()),
        "px_spoke_mean": float(local["spoke"].mean()),
        "morph_irregularity_index": morph["morph_irregularity_index"],
        "morph_n_substantial_peaks": morph["morph_n_substantial_peaks"],
        "morph_n_spicule_like": morph["morph_n_spicule_like"],
    }
    return {
        "pts": pts,
        "d_s": d_s,
        "profiles": profiles,
        "local": local,
        "morph": morph,
        "summary": summary,
        "mask": mask,
        "image": image_bgr,
    }


def plot_case(case: dict, meta: dict, out_path: Path, vmin: float, vmax: float) -> dict:
    img, mask = case["image"], case["mask"]
    crop_img, crop_mask, (ox, oy) = crop_roi(img, mask)
    # remap pts into crop
    pts = case["pts"] - np.array([ox, oy], dtype=np.float64)
    # recompute on crop for clean drawing (same algorithm)
    gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
    cnt = largest_contour(crop_mask)
    assert cnt is not None
    pts = resample_closed_contour(cnt, 256)
    profiles = sample_profiles(gray, pts, HALF)
    local = local_pixel_scores(profiles, HALF)
    d, _, _ = nrl_signature(pts)
    d_s = moving_average_circular(d, 7)
    score = local["score"]

    colored = colorize_contour(crop_img, pts, score, vmin=vmin, vmax=vmax, thickness=4)
    colored, tags = mark_artifact_peaks(colored, pts, d_s, score)
    n_art = sum(1 for t in tags if t["kind"] == "artifact")
    n_sup = sum(1 for t in tags if t["kind"] == "supported")

    # shared color scale
    norm = Normalize(vmin=vmin, vmax=vmax)

    fig = plt.figure(figsize=(12.8, 7.6))
    gs = GridSpec(2, 3, width_ratios=[1.2, 1.0, 1.0], height_ratios=[1.15, 1.0], wspace=0.28, hspace=0.35)

    # --- main colored contour ---
    ax0 = fig.add_subplot(gs[:, 0])
    ax0.imshow(cv2.cvtColor(colored, cv2.COLOR_BGR2RGB))
    ax0.set_title(
        f"{meta['stage']} | {meta['arm']} | pid={meta['patient_id']} | L={meta['length']:.1f}cm",
        fontsize=12,
    )
    ax0.axis("off")
    ax0.text(
        0.02,
        0.03,
        "contour color = local PIXEL score (blue=smooth/clear, red=rough/indistinct)\n"
        "white X = mask peak WITHOUT pixel support (artifact)   magenta O = peak WITH support",
        transform=ax0.transAxes,
        fontsize=7.5,
        color="white",
        bbox=dict(facecolor="black", alpha=0.65, edgecolor="none", pad=3),
    )
    sm = cm.ScalarMappable(norm=norm, cmap="turbo")
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax0, fraction=0.046, pad=0.02)
    cbar.set_label("local pixel rough/indistinct score", fontsize=8)

    # --- polar local score ---
    ax1 = fig.add_subplot(gs[0, 1], projection="polar")
    theta = np.linspace(0, 2 * np.pi, len(score), endpoint=False)
    # close loop
    th = np.concatenate([theta, theta[:1]])
    sc = np.concatenate([score, score[:1]])
    ax1.plot(th, sc, color="#F2C57C", lw=1.4)
    ax1.fill(th, sc, color="#F2C57C", alpha=0.35)
    ax1.set_ylim(0, max(vmax * 1.05, float(np.percentile(score, 99)) * 1.1, 0.3))
    ax1.set_title("Local pixel score (absolute)", fontsize=10, pad=12)
    ax1.set_facecolor("black")
    ax1.tick_params(colors="white", labelsize=7)
    for t in tags:
        ax1.plot(theta[t["index"]], score[t["index"]], "wx" if t["kind"] == "artifact" else "mo", markersize=7)

    # --- sorted score curve + thresholds ---
    ax2 = fig.add_subplot(gs[0, 2])
    order = np.argsort(score)
    ax2.plot(score[order], color="#6BAED6", lw=1.5)
    thr = 0.45
    ax2.axhline(thr, color="#E45756", ls="--", lw=1.0, label=f"rough thr={thr}")
    ax2.axhline(float(np.median(score)), color="#AAAAAA", ls=":", lw=0.9, label="median")
    ax2.fill_between(
        np.arange(len(score)),
        thr,
        score[order],
        where=score[order] > thr,
        color="#E45756",
        alpha=0.25,
        interpolate=True,
    )
    ax2.set_title(f"Score distribution  rough_frac={np.mean(score > thr):.0%}", fontsize=10)
    ax2.set_xlabel("contour points (sorted)")
    ax2.set_ylabel("local score (absolute)")
    ax2.legend(fontsize=7, framealpha=0.2)
    ax2.set_ylim(0, max(0.95, vmax * 1.15))

    # --- top-k worst local profiles (pixel evidence of roughness) ---
    ax3 = fig.add_subplot(gs[1, 1])
    worst = np.argsort(score)[-8:]
    best = np.argsort(score)[:8]
    xs = np.arange(-HALF, HALF + 1)
    for i in best:
        ax3.plot(xs, profiles[i], color="#4C78A8", alpha=0.35, lw=0.9)
    for i in worst:
        ax3.plot(xs, profiles[i], color="#E45756", alpha=0.55, lw=1.0)
    ax3.axvline(0, color="white", ls="--", lw=0.8)
    ax3.set_title("Normal profiles: blue=smoothest 8, red=roughest 8", fontsize=10)
    ax3.set_xlabel("offset (px; +outside)")
    ax3.set_ylabel("intensity")

    # --- metrics text ---
    ax4 = fig.add_subplot(gs[1, 2])
    ax4.axis("off")
    s = case["summary"]
    # recompute summary from crop locals for display consistency
    thr = 0.45
    rough_frac = float(np.mean(score > thr))
    s_disp = {
        "px_score_mean": float(score.mean()),
        "px_score_p90": float(np.percentile(score, 90)),
        "px_rough_frac": rough_frac,
        "px_jump_mean": float(local["jump"].mean()),
        "px_sharp_mean": float(local["sharp"].mean()),
        "mask_peaks": case["summary"]["morph_n_substantial_peaks"],
        "mask_irreg": case["summary"]["morph_irregularity_index"],
        "peaks_artifact": n_art,
        "peaks_supported": n_sup,
    }
    # verdict from pixel-first rule (calibrated to clear≈0.20 / rough≈0.60)
    if s_disp["px_score_mean"] >= 0.48 or rough_frac >= 0.45:
        verdict = "PIXEL: rough / indistinct margin"
        vcolor = "#E45756"
    elif s_disp["px_score_mean"] <= 0.32 and rough_frac <= 0.20:
        verdict = "PIXEL: mostly clear / sharp"
        vcolor = "#54A24B"
    else:
        verdict = "PIXEL: mixed"
        vcolor = "#F58518"
    if n_art >= 2 and s_disp["mask_irreg"] >= 0.35:
        verdict += "  |  mask spikes look artifactual"

    text = (
        f"Verdict\n{verdict}\n\n"
        f"Pixel (primary)\n"
        f"  mean score     {s_disp['px_score_mean']:.3f}\n"
        f"  p90 score      {s_disp['px_score_p90']:.3f}\n"
        f"  rough fraction {s_disp['px_rough_frac']:.0%}\n"
        f"  mean jump      {s_disp['px_jump_mean']:.1f}\n"
        f"  mean sharp     {s_disp['px_sharp_mean']:.1f}\n\n"
        f"Mask (secondary)\n"
        f"  irreg index    {s_disp['mask_irreg']:.3f}\n"
        f"  peaks          {s_disp['mask_peaks']:.0f}\n"
        f"  supported      {s_disp['peaks_supported']}\n"
        f"  artifact-like  {s_disp['peaks_artifact']}\n"
    )
    ax4.text(0.04, 0.96, text, va="top", ha="left", fontsize=9.5, family="monospace", color="white")
    ax4.text(0.04, 0.08, "How to read: RED contour arcs = real candidate spicules/infiltrate\nWHITE X = ignore (mask-only jaggedness)", fontsize=8, color="#CCCCCC", va="bottom")
    # colored verdict bar
    ax4.add_patch(
        plt.Rectangle((0.02, 0.88), 0.96, 0.08, transform=ax4.transAxes, color=vcolor, alpha=0.35, clip_on=False)
    )

    fig.suptitle("GC-US margin v2 · local PIXEL score on contour (not average profile)", fontsize=13, y=0.995)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=170, bbox_inches="tight")
    plt.close(fig)

    s_disp["verdict"] = verdict
    s_disp["n_artifact_peaks"] = n_art
    s_disp["n_supported_peaks"] = n_sup
    # save ROI colored for board
    roi_path = out_path.with_name(out_path.stem + "_roi.png")
    cv2.imwrite(str(roi_path), colored)
    s_disp["roi_png"] = str(roi_path)
    return s_disp


def plot_stage_board(rows: list[dict], out_path: Path) -> None:
    """2x4 board: CLEAR (top) vs ROUGH (bottom) for each T stage — pixel-picked extremes."""
    fig, axes = plt.subplots(2, 4, figsize=(15.2, 8.0))
    by_stage: dict[int, dict[str, dict]] = {}
    for r in rows:
        by_stage.setdefault(int(r["label"]), {})
        key = "clear" if "clear" in r["arm"] else "rough"
        by_stage[int(r["label"])][key] = r

    for col, lab in enumerate(range(4)):
        for row_i, key in enumerate(("clear", "rough")):
            ax = axes[row_i, col]
            r = by_stage.get(lab, {}).get(key)
            if r is None:
                ax.axis("off")
                continue
            img = cv2.imread(r["roi_png"])
            if img is None:
                ax.axis("off")
                continue
            ax.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
            tag = "CLEAR" if key == "clear" else "ROUGH"
            color = "#54A24B" if key == "clear" else "#E45756"
            ax.set_title(
                f"{STAGE[lab]} · {tag}\nmean={r['px_score_mean']:.2f}  rough={r['px_rough_frac']:.0%}",
                fontsize=10,
                color=color,
                fontweight="bold",
            )
            ax.axis("off")
            for spine in ax.spines.values():
                spine.set_visible(True)
                spine.set_color(color)
                spine.set_linewidth(2.5)
    axes[0, 0].set_ylabel("CLEAR (low pixel score)", fontsize=11, color="#54A24B")
    axes[1, 0].set_ylabel("ROUGH (high pixel score)", fontsize=11, color="#E45756")
    fig.suptitle(
        "Pixel-picked extremes · BLUE contour = clear/smooth edge · RED = rough/indistinct\n"
        "Top vs bottom within a column should differ; if both look red, score contrast failed",
        fontsize=12,
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_metric_bars(metrics: pd.DataFrame, out_path: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
    for ax, col, title in zip(
        axes,
        ["px_score_mean", "px_rough_frac", "px_score_p90"],
        ["Mean local pixel score", "Fraction rough (>0.45)", "P90 local pixel score"],
    ):
        for _, r in metrics.iterrows():
            x = r["label"] + (-0.15 if "clear" in r["arm"] else 0.15)
            ax.bar(
                x,
                r[col],
                width=0.28,
                color="#4C78A8" if "clear" in r["arm"] else "#E45756",
                edgecolor="white",
                linewidth=0.5,
            )
        ax.set_xticks(range(4))
        ax.set_xticklabels([STAGE[i] for i in range(4)])
        ax.set_title(title)
        ax.set_ylim(0, max(1.0, float(metrics[col].max()) * 1.15))
    axes[0].bar([], [], color="#4C78A8", label="clear (low pixel score)")
    axes[0].bar([], [], color="#E45756", label="rough (high pixel score)")
    axes[0].legend(fontsize=7, framealpha=0.25)
    fig.suptitle("Pixel-first metrics · cases picked as clear vs rough extremes", fontsize=12)
    fig.tight_layout()
    fig.savefig(out_path, dpi=170, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    apply_style()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pt = pd.read_csv(
        PROJECT_ROOT
        / "pipeline/experiments/reports/imaging_truth_tstage_corr_v2/patient_table_unique_pooled.csv"
    )
    morph_p = pd.read_csv(
        PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1/morphology/patient_features_median.csv"
    )
    pt["patient_id"] = pt["patient_id"].astype(str)
    morph_p["patient_id"] = morph_p["patient_id"].astype(str)
    joined = pt.merge(morph_p, on="patient_id", how="inner")

    frames = load_frames()
    hash_index = build_mask_hash_index()
    examples = pick_examples_by_pixel(joined, frames, hash_index, per_stage_probe=48)
    # drop heavy objects before csv
    examples.drop(columns=["_case"], errors="ignore").to_csv(OUT_DIR / "selected_patients.csv", index=False)

    cases = []
    for _, ex in examples.iterrows():
        case = ex["_case"]
        cases.append(
            {
                "case": case,
                "meta": {
                    "stage": STAGE[int(ex["label"])],
                    "arm": ex["arm"],
                    "patient_id": str(ex["patient_id"]),
                    "length": float(ex.get("tumor_length_cm", np.nan)),
                    "label": int(ex["label"]),
                },
            }
        )

    # Fixed absolute color scale matched to clear≈0.20 / rough≈0.60 extremes.
    vmin, vmax = 0.18, 0.65

    rows = []
    panels = []
    for item in cases:
        out_png = OUT_DIR / f"case_{item['meta']['stage']}_{item['meta']['arm']}_pid{item['meta']['patient_id']}.png"
        disp = plot_case(item["case"], item["meta"], out_png, vmin, vmax)
        row = {
            **item["meta"],
            **{k: disp[k] for k in disp if k != "verdict"},
            "verdict": disp["verdict"],
            "png": str(out_png),
            "roi_png": disp["roi_png"],
        }
        rows.append(row)
        panels.append(str(out_png))

    metrics = pd.DataFrame(rows)
    metrics.to_csv(OUT_DIR / "example_metrics.csv", index=False)
    if not metrics.empty:
        plot_stage_board(rows, OUT_DIR / "00_stage_board_color_contour.png")
        plot_metric_bars(metrics, OUT_DIR / "00_metrics_by_stage.png")

    readme = [
        "# Margin pixel pilot v2",
        "",
        "**Look first:** `00_stage_board_color_contour.png`",
        "Blue contour arcs = clear/smooth edge; red = rough/indistinct (absolute pixel score).",
        "Each stage shows CLEAR vs ROUGH extremes picked by pixel score (not mask jaggedness).",
        "",
        "## Score (v3)",
        "`clear = tanh(jump/70) * tanh(sharp/14)`",
        "`score = 0.75*(1-clear) + 0.15*circ_jump_hf + 0.10*spoke`",
        "",
        "Outer-profile HF/ripple was dropped (US speckle, no discrimination).",
        "",
        "Rebuild: `python3 scripts/viz_gc_us_margin_pixel_examples.py`",
        "",
    ]
    for _, r in metrics.iterrows():
        readme.append(
            f"- {r['stage']} / {r['arm']} / {r['patient_id']}: mean={r['px_score_mean']:.3f} "
            f"rough={r['px_rough_frac']:.0%} · {r['verdict']}"
        )
    (OUT_DIR / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")
    print(json.dumps({"n": len(metrics), "out": str(OUT_DIR), "panels": panels}, indent=2))
    if not metrics.empty:
        cols = ["stage", "arm", "patient_id", "px_score_mean", "px_rough_frac", "px_score_p90", "n_artifact_peaks", "verdict"]
        print(metrics[cols].to_string(index=False))


if __name__ == "__main__":
    main()
