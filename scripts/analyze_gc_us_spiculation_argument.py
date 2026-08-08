#!/usr/bin/env python3
"""Argue / upgrade GC-US spiculation estimation with IMAGE evidence (not mask-only).

v2 (image-backed):
  ridge / tip continuity / angular isolation / band texture → evidence[0,1]
  true spicule = geom narrow peak ∩ high evidence
  image-led   = evidence peak without geom peak
  artifact    = raw-only NRL peak OR geom peak with low evidence

Outputs under:
  pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/spiculation_argument/
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.gridspec import GridSpec
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from gc_us_contour_features import (  # noqa: E402
    build_mask_hash_index,
    estimate_spiculation_from_image_mask,
    load_binary_mask,
    largest_contour,
)
from viz_gc_us_margin_pixel_examples import (  # noqa: E402
    STAGE,
    choose_frame,
    crop_roi,
    load_frames,
    local_pixel_scores,
    sample_profiles,
    HALF,
)

OUT_DIR = (
    PROJECT_ROOT
    / "pipeline"
    / "experiments"
    / "reports"
    / "gc_us_tscore_feature_stats_v1"
    / "spiculation_argument"
)


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


def draw_taxonomy(
    image_bgr: np.ndarray,
    pts: np.ndarray,
    tags: list[dict],
    angular: np.ndarray,
) -> np.ndarray:
    """Color contour by angular SNR (image tip isolation); mark peak taxonomy."""
    out = (image_bgr.astype(np.float32) * 0.55).astype(np.uint8)
    try:
        cmap = plt.colormaps["turbo"]
    except Exception:
        from matplotlib import cm

        cmap = cm.get_cmap("turbo")
    # typical ang_mean ~0.5, hot tips ~2–6
    vmin, vmax = 0.2, 2.5
    n = len(pts)
    for i in range(n):
        p0 = tuple(np.round(pts[i]).astype(int))
        p1 = tuple(np.round(pts[(i + 1) % n]).astype(int))
        t = float(np.clip((angular[i] - vmin) / (vmax - vmin), 0, 1)) ** 0.8
        rgba = cmap(t)
        bgr = (int(rgba[2] * 255), int(rgba[1] * 255), int(rgba[0] * 255))
        cv2.line(out, p0, p1, bgr, 4, cv2.LINE_AA)

    colors = {
        "true_spicule_candidate": (0, 0, 255),
        "image_led_spicule": (0, 140, 255),
        "artifact_peak": (255, 255, 255),
        "soft_not_spicule": (0, 165, 255),
        "geom_spicule_weak_pixel": (0, 255, 255),
        "lobule_supported": (255, 0, 255),
        "lobule_or_other": (200, 200, 0),
    }
    for t in tags:
        pt = tuple(np.round(pts[t["index"]]).astype(int))
        col = colors.get(t["kind"], (200, 200, 200))
        if t["kind"] == "artifact_peak":
            cv2.drawMarker(out, pt, col, markerType=cv2.MARKER_TILTED_CROSS, markerSize=16, thickness=2)
        elif t["kind"] in ("true_spicule_candidate", "image_led_spicule"):
            cv2.circle(out, pt, 8, col, 2)
        else:
            cv2.circle(out, pt, 5, col, 2)
    return out


def plot_case(pack: dict, meta: dict, out_path: Path) -> None:
    img, mask = pack["image"], pack["mask"]
    crop_img, crop_mask, _ = crop_roi(img, mask)
    # recompute on crop for clean drawing
    pack_c = estimate_spiculation_from_image_mask(crop_img, crop_mask)
    pts = pack_c["pts"]
    tags = pack_c["tags"]
    ang = pack_c["img_ev"]["angular"]
    profiles = pack_c["img_ev"]["profiles"]
    half = profiles.shape[1] // 2
    colored = draw_taxonomy(crop_img, pts, tags, ang)

    fig = plt.figure(figsize=(13.4, 7.5))
    gs = GridSpec(2, 3, width_ratios=[1.25, 1.0, 1.0], height_ratios=[1.2, 1.0], wspace=0.28, hspace=0.35)

    ax0 = fig.add_subplot(gs[:, 0])
    ax0.imshow(cv2.cvtColor(colored, cv2.COLOR_BGR2RGB))
    ax0.set_title(
        f"{meta['stage']} | pid={meta['patient_id']} | L={meta['length']:.1f}cm\n"
        f"spic_v2={pack_c['spic_index_v2']:.2f}  ang_mean={pack_c['angular_mean']:.2f}  "
        f"true={int(pack_c['n_true_spicule'])}  art={int(pack_c['n_artifact_peak'])}",
        fontsize=11,
    )
    ax0.axis("off")
    ax0.text(
        0.02,
        0.03,
        "contour color = angular SNR (image tip isolation vs neighbors)\n"
        "RED=geom x image   ORANGE=image-led   WHITE X=staircasing/no-support",
        transform=ax0.transAxes,
        fontsize=7.5,
        color="white",
        bbox=dict(facecolor="black", alpha=0.65, edgecolor="none", pad=3),
    )

    ax1 = fig.add_subplot(gs[0, 1], projection="polar")
    theta = np.linspace(0, 2 * np.pi, len(ang), endpoint=False)
    th = np.concatenate([theta, theta[:1]])
    sc = np.concatenate([ang, ang[:1]])
    ax1.plot(th, sc, color="#F2C57C", lw=1.3)
    ax1.fill(th, sc, color="#F2C57C", alpha=0.3)
    ax1.set_ylim(0, max(1.5, float(np.percentile(ang, 99)) * 1.15))
    ax1.set_title("Angular SNR around contour", fontsize=10, pad=12)
    ax1.set_facecolor("black")
    for t in tags:
        if t["kind"] in ("true_spicule_candidate", "image_led_spicule", "artifact_peak"):
            ax1.plot(
                theta[t["index"]],
                ang[t["index"]],
                "ro" if "spicule" in t["kind"] else "wx",
                markersize=6,
            )

    ax2 = fig.add_subplot(gs[0, 2])
    if tags:
        xs = [t.get("angular", 0) for t in tags]
        ys = [t.get("tip_cont", 0) for t in tags]
        cs = []
        for t in tags:
            if t["kind"] == "true_spicule_candidate":
                cs.append("#E45756")
            elif t["kind"] == "image_led_spicule":
                cs.append("#F58518")
            elif t["kind"] == "artifact_peak":
                cs.append("#FFFFFF")
            else:
                cs.append("#4C78A8")
        ax2.scatter(xs, ys, c=cs, s=55, edgecolors="#333", linewidths=0.4)
    ax2.axvline(0.70, color="#888", ls="--", lw=0.8)
    ax2.set_xlabel("angular SNR at peak")
    ax2.set_ylabel("tip score")
    ax2.set_title("Peak gate: angular SNR vs tip", fontsize=10)

    ax3 = fig.add_subplot(gs[1, 1])
    xs = np.arange(-half, half + 1)
    true_idx = [t["index"] for t in tags if t["kind"] in ("true_spicule_candidate", "image_led_spicule")][:5]
    art_idx = [t["index"] for t in tags if t["kind"] == "artifact_peak"][:5]
    for i in art_idx:
        ax3.plot(xs, profiles[i], color="#FFFFFF", alpha=0.65, lw=0.9)
    for i in true_idx:
        ax3.plot(xs, profiles[i], color="#E45756", alpha=0.85, lw=1.2)
    ax3.axvline(0, color="white", ls="--", lw=0.8)
    ax3.set_title("Profiles: white=artifact, red=image-supported tip", fontsize=10)
    ax3.set_xlabel("offset (px; +outside)")
    ax3.set_ylabel("intensity")

    ax4 = fig.add_subplot(gs[1, 2])
    ax4.axis("off")
    counts = pd.Series([t["kind"] for t in tags]).value_counts().to_dict() if tags else {}
    text = (
        f"Image-backed spiculation v2\n"
        f"  spic_index_v2     {pack_c['spic_index_v2']:.3f}\n"
        f"  angular mean/top  {pack_c['angular_mean']:.3f} / {pack_c['angular_top']:.3f}\n"
        f"  hypo_top / snr    {pack_c['hypo_top']:.3f} / {pack_c['snr_top']:.3f}\n"
        f"  true peaks        {int(pack_c['n_true_spicule'])}\n"
        f"    geom-gated      {int(pack_c['n_geom_true'])}\n"
        f"    image-led       {int(pack_c['n_image_led'])}\n"
        f"  artifact peaks    {int(pack_c['n_artifact_peak'])}\n"
        f"  fd_high / vh      {pack_c['fd_high']:.3f} / {pack_c['fd_very_high']:.3f}\n\n"
        f"Counts: {counts}"
    )
    ax4.text(0.02, 0.98, text, va="top", ha="left", fontsize=9, family="monospace", color="white")

    fig.suptitle(
        "Spiculation v2: IMAGE angular SNR on contour gates mask peaks (not mask-only)",
        fontsize=12,
        y=0.995,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=170, bbox_inches="tight")
    plt.close(fig)


def spearman_safe(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 8:
        return float("nan"), float("nan")
    r, p = stats.spearmanr(x[m], y[m])
    return float(r), float(p)


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

    rows = []
    example_cases = []
    for lab in range(4):
        sub = joined[joined["label"] == lab].dropna(subset=["tumor_length_cm"])
        lo, hi = sub["tumor_length_cm"].quantile([0.25, 0.75])
        mid = sub[(sub["tumor_length_cm"] >= lo) & (sub["tumor_length_cm"] <= hi)]
        if mid.empty:
            mid = sub
        probe = mid.sample(n=min(40, len(mid)), random_state=7)
        for _, r in probe.iterrows():
            fr = choose_frame(frames, str(r["patient_id"]), hash_index)
            if fr is None:
                continue
            image = cv2.imread(fr["_image_path"])
            mask = load_binary_mask(Path(fr["_mask_path"]))
            if image is None or mask is None:
                continue
            try:
                pack = estimate_spiculation_from_image_mask(image, mask)
                if pack.get("valid", 0) < 1:
                    continue
                # indistinct confounder (edge softness) — separate clinical sign
                if mask.shape[:2] != image.shape[:2]:
                    mask_r = cv2.resize(mask, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_NEAREST)
                else:
                    mask_r = mask
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                cnt = largest_contour(mask_r)
                if cnt is None:
                    continue
                from gc_us_contour_features import resample_closed_contour

                pts = resample_closed_contour(cnt, 256)
                profiles16 = sample_profiles(gray, pts, HALF)
                indistinct = float(local_pixel_scores(profiles16, HALF)["score"].mean())
            except Exception:
                continue
            morph = pack["morph"]
            row = {
                "patient_id": str(r["patient_id"]),
                "label": int(lab),
                "stage": STAGE[lab],
                "tumor_length_cm": float(r["tumor_length_cm"]),
                "spic_index_v2": pack["spic_index_v2"],
                "n_true_spicule": pack["n_true_spicule"],
                "n_geom_true": pack["n_geom_true"],
                "n_image_led": pack["n_image_led"],
                "n_artifact_peak": pack["n_artifact_peak"],
                "n_geom_spicule": pack["n_geom_spicule"],
                "evidence_mean": pack["evidence_mean"],
                "evidence_p90": pack["evidence_p90"],
                "evidence_top": pack["evidence_top"],
                "evidence_hot_frac": pack["evidence_hot_frac"],
                "angular_mean": pack["angular_mean"],
                "angular_top": pack["angular_top"],
                "hypo_top": pack["hypo_top"],
                "snr_top": pack["snr_top"],
                "tip_top": pack["tip_top"],
                "fd_high": pack["fd_high"],
                "fd_very_high": pack["fd_very_high"],
                "indistinct_mean": indistinct,
                "legacy_irreg": float(morph["morph_legacy_perimeter_area"]),
                "morph_irreg": float(morph["morph_irregularity_index"]),
                "morph_n_spicule_like": float(morph["morph_n_spicule_like"]),
            }
            rows.append(row)
            pack["image"] = image
            pack["mask"] = mask
            example_cases.append((row, pack))

    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "probe_metrics.csv", index=False)

    y = df["label"].to_numpy(float)
    corr_rows = []
    for col in [
        "spic_index_v2",
        "angular_mean",
        "angular_top",
        "hypo_top",
        "snr_top",
        "evidence_top",
        "evidence_p90",
        "evidence_hot_frac",
        "tip_top",
        "n_true_spicule",
        "n_image_led",
        "n_geom_true",
        "n_artifact_peak",
        "n_geom_spicule",
        "fd_high",
        "fd_very_high",
        "indistinct_mean",
        "legacy_irreg",
        "morph_irreg",
        "morph_n_spicule_like",
    ]:
        r, p = spearman_safe(df[col].to_numpy(float), y)
        corr_rows.append({"feature": col, "spearman_vs_T": r, "p": p})
    corr = pd.DataFrame(corr_rows).sort_values("spearman_vs_T", ascending=False)
    corr.to_csv(OUT_DIR / "spearman_vs_tstage.csv", index=False)

    cross = []
    for a, b in [
        ("spic_index_v2", "indistinct_mean"),
        ("spic_index_v2", "legacy_irreg"),
        ("spic_index_v2", "evidence_p90"),
        ("n_true_spicule", "n_geom_spicule"),
        ("n_artifact_peak", "fd_very_high"),
        ("n_image_led", "n_geom_true"),
        ("evidence_p90", "legacy_irreg"),
        ("indistinct_mean", "legacy_irreg"),
    ]:
        r, p = spearman_safe(df[a].to_numpy(float), df[b].to_numpy(float))
        cross.append({"a": a, "b": b, "spearman": r, "p": p})
    cross_df = pd.DataFrame(cross)
    cross_df.to_csv(OUT_DIR / "cross_feature_spearman.csv", index=False)

    stage_sum = (
        df.groupby("stage", sort=False)[
            [
                "spic_index_v2",
                "n_true_spicule",
                "n_image_led",
                "n_artifact_peak",
                "angular_mean",
                "evidence_p90",
                "indistinct_mean",
                "legacy_irreg",
            ]
        ]
        .median()
        .reset_index()
    )
    stage_sum.to_csv(OUT_DIR / "stage_medians.csv", index=False)

    # showcase
    show = []
    if not df.empty:
        show.append(("high_spiculation", df.nlargest(1, "spic_index_v2").iloc[0]["patient_id"]))
        show.append(("high_image_led", df.nlargest(1, "n_image_led").iloc[0]["patient_id"]))
        show.append(("high_artifact_frac", df.nlargest(1, "n_artifact_peak").iloc[0]["patient_id"]))
        tmp = df.copy()
        tmp["gap"] = tmp["indistinct_mean"] - tmp["spic_index_v2"]
        show.append(("soft_not_spicule", tmp.nlargest(1, "gap").iloc[0]["patient_id"]))

    case_map = {r["patient_id"]: (r, p) for r, p in example_cases}
    for tag, pid in show:
        if pid not in case_map:
            continue
        r, pack = case_map[pid]
        plot_case(
            pack,
            {"stage": r["stage"], "patient_id": pid, "length": r["tumor_length_cm"], "tag": tag},
            OUT_DIR / f"case_{tag}_pid{pid}.png",
        )

    fig, axes = plt.subplots(1, 3, figsize=(12.8, 3.8))
    order = ["T1", "T2", "T3", "T4+"]
    for ax, col, title in zip(
        axes,
        ["spic_index_v2", "angular_mean", "indistinct_mean"],
        ["Spiculation index v2 (image)", "Angular SNR mean", "Indistinctness (confounder)"],
    ):
        meds = [df.loc[df["stage"] == s, col].median() if (df["stage"] == s).any() else np.nan for s in order]
        ax.bar(range(4), meds, color=["#4C78A8", "#72B7B2", "#F58518", "#E45756"], edgecolor="white", linewidth=0.4)
        ax.set_xticks(range(4))
        ax.set_xticklabels(order)
        ax.set_title(title)
    fig.suptitle(f"Image-backed spiculation v2 · probe n={len(df)}", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "00_stage_medians.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.8, 4.4))
    corr_plot = corr.sort_values("spearman_vs_T")
    colors = ["#E45756" if (isinstance(v, float) and v < 0) else "#4C78A8" for v in corr_plot["spearman_vs_T"]]
    ax.barh(corr_plot["feature"], corr_plot["spearman_vs_T"], color=colors, edgecolor="white", linewidth=0.3)
    ax.axvline(0, color="white", lw=0.8)
    ax.set_xlabel("Spearman ρ vs ordinal T stage")
    ax.set_title("Image-backed proxies vs T (probe, length-banded)")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "00_spearman_vs_t.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    summary = {
        "n_probe": int(len(df)),
        "frac_any_true": float((df["n_true_spicule"] > 0).mean()) if len(df) else None,
        "frac_any_image_led": float((df["n_image_led"] > 0).mean()) if len(df) else None,
        "frac_any_artifact": float((df["n_artifact_peak"] > 0).mean()) if len(df) else None,
        "median_spic_v2": float(df["spic_index_v2"].median()) if len(df) else None,
        "corr_table": corr.to_dict(orient="records"),
        "cross_table": cross_df.to_dict(orient="records"),
        "stage_medians": stage_sum.to_dict(orient="records"),
        "showcase": show,
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (OUT_DIR / "README.md").write_text(
        "\n".join(
            [
                "# Spiculation argument v2 (image-backed)",
                "",
                "Contour color = fused IMAGE evidence (ridge / tip continuity / angular / band tex).",
                "Mask peaks are gated; image-led peaks allowed when evidence is high without geom peak.",
                "",
                "Look: `00_spearman_vs_t.png`, `case_high_spiculation_*.png`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    print("\n=== spearman vs T ===")
    print(corr.to_string(index=False))
    print("\n=== cross ===")
    print(cross_df.to_string(index=False))
    print("\n=== stage medians ===")
    print(stage_sum.to_string(index=False))


if __name__ == "__main__":
    main()
