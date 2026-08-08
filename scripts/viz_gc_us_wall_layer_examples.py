#!/usr/bin/env python3
"""Visualize GC-US wall-layer proxies and stage association.

Outputs:
  pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/wall_layer/
  results/visualizations/tstage/imaging_truth_share_white_20260729/47_*
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from gc_us_contour_features import (  # noqa: E402
    build_mask_hash_index,
    load_binary_mask,
    resolve_image_path,
    resolve_mask_path,
)
from gc_us_wall_layer_features import (  # noqa: E402
    compute_wall_layer_features,
    lumen_mask_from_box,
    render_wall_layer_overlay,
)

FEAT = PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1/wall_layer"
PT = (
    PROJECT_ROOT
    / "pipeline/experiments/reports/imaging_truth_tstage_corr_v2"
    / "patient_table_unique_pooled.csv"
)
OUT = PROJECT_ROOT / "pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/wall_layer"
SHARE = PROJECT_ROOT / "results/visualizations/tstage/imaging_truth_share_white_20260729"
STAGE = ["T1", "T2", "T3", "T4+"]
COLORS = {0: "#6B9AC4", 1: "#7EB77F", 2: "#E09F3E", 3: "#C86B6B"}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-examples", type=int, default=3)
    return ap.parse_args()


def apply_nature() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": 6,
            "pdf.fonttype": 42,
            "axes.facecolor": "white",
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def eval_split(s: object) -> str:
    parts = set(str(s).replace(" ", "").split(","))
    if "external" in parts:
        return "test_external"
    if "prospective" in parts and "train" not in parts and "val" not in parts:
        return "test_prospective"
    if "val" in parts:
        return "val"
    if "train" in parts or "prospective" in parts:
        return "train"
    return "other"


def resolve_rel(path_str: object) -> Path | None:
    if not path_str or not isinstance(path_str, str) or str(path_str).lower() == "nan":
        return None
    p = Path(path_str)
    if p.exists():
        return p
    alt = (PROJECT_ROOT / path_str).resolve()
    return alt if alt.exists() else None


def main() -> None:
    args = parse_args()
    apply_nature()
    OUT.mkdir(parents=True, exist_ok=True)
    SHARE.mkdir(parents=True, exist_ok=True)

    pat = pd.read_csv(FEAT / "patient_features_median.csv")
    pt = pd.read_csv(PT)
    pat["patient_id"] = pat["patient_id"].astype(str)
    pt["patient_id"] = pt["patient_id"].astype(str)
    df = pat.merge(pt[["patient_id", "label", "source_splits", "tumor_length_cm"]], on="patient_id", how="inner")
    df["label"] = pd.to_numeric(df["label"], errors="coerce")
    df["eval_split"] = df["source_splits"].map(eval_split)
    df = df[df["wall_valid"] > 0.5].dropna(subset=["label"])

    # association table
    feats = [
        "wall_depth_frac_p90",
        "wall_layer_score_soft",
        "wall_mp_band_frac",
        "wall_outer_band_frac",
        "wall_serosa_interrupt",
        "wall_layer_disruption",
        "wall_contact_arc_ratio",
    ]
    rows = []
    y = df["label"].to_numpy(float)
    for f in feats:
        x = pd.to_numeric(df[f], errors="coerce").to_numpy(float)
        m = np.isfinite(x) & np.isfinite(y)
        rho, p = stats.spearmanr(x[m], y[m])
        groups = [x[m & (y == k)] for k in range(4) if np.any(m & (y == k))]
        try:
            kw = float(stats.kruskal(*groups).pvalue)
        except ValueError:
            kw = float("nan")
        meds = [float(np.median(x[m & (y == k)])) if np.any(m & (y == k)) else float("nan") for k in range(4)]
        rows.append(
            {
                "feature": f,
                "n": int(m.sum()),
                "spearman_rho": float(rho),
                "spearman_p": float(p),
                "kruskal_p": kw,
                "median_T1": meds[0],
                "median_T2": meds[1],
                "median_T3": meds[2],
                "median_T4+": meds[3],
            }
        )
    stats_df = pd.DataFrame(rows).sort_values("spearman_rho", key=lambda s: s.abs(), ascending=False)
    stats_df.to_csv(OUT / "feature_stats.csv", index=False)

    # violin / strip for depth_p90 and soft score
    fig, axes = plt.subplots(1, 2, figsize=(6.2, 2.8))
    for ax, f, title in zip(
        axes,
        ["wall_depth_frac_p90", "wall_layer_score_soft"],
        ["Wall depth fraction (p90)", "Soft wall-layer score (0/2/4/5)"],
    ):
        data = [df.loc[df.label == k, f].dropna().to_numpy() for k in range(4)]
        parts = ax.violinplot(data, positions=range(4), showmeans=False, showmedians=True, widths=0.8)
        for b in parts["bodies"]:
            b.set_facecolor("#6B9AC4")
            b.set_alpha(0.55)
        for k in range(4):
            ax.scatter(
                np.full(len(data[k]), k) + np.random.default_rng(0).uniform(-0.08, 0.08, len(data[k])),
                data[k],
                s=2,
                c=COLORS[k],
                alpha=0.25,
                linewidths=0,
            )
        ax.set_xticks(range(4))
        ax.set_xticklabels(STAGE)
        ax.set_title(title, fontsize=7)
        ax.tick_params(labelsize=5.5)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
    fig.suptitle(f"Wall-layer proxies vs pathologic T  (n={len(df)})", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "00_wall_depth_score_by_stage.png", dpi=300)
    fig.savefig(SHARE / "47_wall_layer_depth_score_by_stage.png", dpi=300)
    plt.close(fig)

    # example board: one per stage
    frame = pd.read_csv(FEAT / "frame_features.csv")
    frame["patient_id"] = frame["patient_id"].astype(str)
    frame = frame[frame["wall_valid"] > 0.5]
    # join anatomic paths again from clinical? use image/mask from frame + re-read anatomic for lumen/outer
    # For viz, recompute overlay from frame paths by reloading anatomic CSV join
    from gc_us_contour_features import DEFAULT_ANATOMIC_DIR, DEFAULT_FRAME_CSVS

    parts = []
    for name in DEFAULT_FRAME_CSVS:
        p = DEFAULT_ANATOMIC_DIR / name
        if p.exists():
            d = pd.read_csv(p)
            d["split_file"] = name
            parts.append(d)
    anat = pd.concat(parts, ignore_index=True)
    anat["patient_id"] = anat["patient_id"].astype(str)
    # pick frames: for each stage, top wall_depth_frac_p90 among valid
    hash_index = build_mask_hash_index()
    picks = []
    for k in range(4):
        sub = frame[pd.to_numeric(frame["label"], errors="coerce") == k].copy()
        if sub.empty:
            continue
        sub = sub.sort_values("wall_depth_frac_p90", ascending=False).head(args.n_examples)
        picks.append(sub)
    pick_df = pd.concat(picks, ignore_index=True) if picks else frame.head(8)

    overlays = []
    titles = []
    for _, r in pick_df.iterrows():
        # match anatomic row by image_path
        hit = anat[anat["image_path"].astype(str) == str(r["image_path"])]
        if hit.empty:
            hit = anat[anat["patient_id"] == str(r["patient_id"])].head(1)
        if hit.empty:
            continue
        a = hit.iloc[0]
        img_p = resolve_image_path(a.get("image_path"))
        mask_p = resolve_mask_path(str(a.get("lesion_pred_mask_path", "")), hash_index)
        lumen_p = resolve_rel(a.get("anatomic_inner_lumen_mask_path"))
        outer_p = resolve_rel(a.get("anatomic_outer_wall_mask_path"))
        if img_p is None or mask_p is None:
            continue
        img = cv2.imread(str(img_p), cv2.IMREAD_COLOR)
        mask = load_binary_mask(mask_p)
        lumen = load_binary_mask(lumen_p) if lumen_p else None
        if lumen is None:
            lumen = lumen_mask_from_box(
                mask.shape,
                float(a.get("lumen_box_x1", 0) or 0),
                float(a.get("lumen_box_y1", 0) or 0),
                float(a.get("lumen_box_x2", 0) or 0),
                float(a.get("lumen_box_y2", 0) or 0),
            )
        outer = load_binary_mask(outer_p) if outer_p else None
        feats = compute_wall_layer_features(img, mask, lumen, outer)
        ov = render_wall_layer_overlay(img, mask, lumen, outer, feats)
        overlays.append(cv2.cvtColor(ov, cv2.COLOR_BGR2RGB))
        lab = int(float(r.get("label", 0)))
        titles.append(f"{STAGE[lab]}  d90={feats['wall_depth_frac_p90']:.2f}  score={int(feats['wall_layer_score_soft'])}")

    if overlays:
        n = len(overlays)
        cols = min(4, n)
        rows_n = int(np.ceil(n / cols))
        fig, axes = plt.subplots(rows_n, cols, figsize=(2.4 * cols, 2.2 * rows_n))
        axes = np.atleast_2d(axes)
        for i in range(rows_n * cols):
            ax = axes[i // cols, i % cols]
            ax.axis("off")
            if i < n:
                ax.imshow(overlays[i])
                ax.set_title(titles[i], fontsize=5.5)
        fig.suptitle(
            "Wall-layer overlay  (green=inner, yellow=MP band, red=outer/serosa side)",
            fontsize=7,
        )
        fig.tight_layout()
        fig.savefig(OUT / "00_wall_layer_overlay_board.png", dpi=220)
        fig.savefig(SHARE / "47_wall_layer_overlay_board.png", dpi=220)
        plt.close(fig)

    # literature + summary md
    lit = """# Wall-layer proxies · literature basis

## Classic EUS five-layer model
- Layers 1–2: mucosa (interface + deep mucosa)
- Layer 3: submucosa (hyperechoic)
- Layer 4: muscularis propria (hypoechoic)
- Layer 5: subserosa–serosa (hyperechoic)

Key references:
- Botet / early EUS gastric staging (Gut 1991-era five-layer description)
- Mocellin et al., EUS for staging gastric cancer meta-analysis (2011)
- Recent review: Endoscopic Ultrasound in Gastric Cancer (PMC12385178)
- Early GC EUS algorithm (BMC Cancer 2022): uT1a–uT4b by deepest disrupted layer;
  uT4a = outer bright line interrupted irregularly

## Transabdominal US caveat
Oral-contrast TAUS papers (Zhong 2025; Wu 2023; Xu 2024 DCEUS) report T3–T4
features (serosal interruption, loss of layered structure, wall thickening) but
**do not reliably resolve all five EUS layers**. Project meetings (2026-07-14/28)
likewise: no histologic layer GT; do not use wall stratification as sole supervision.

## This implementation
Soft proxies only (not pixel histology):
1. Relative depth = lumen-SDF / estimated wall thickness (outer mask or shell)
2. Soft score 0/2/4/5 from depth p90 (+ serosa interrupt bump)
3. Echo-profile disruption vs adjacent healthier wall
4. Outer-band / MP-band occupancy

P0.2 lesson: do **not** inject raw SDF as ConvNet channel.
"""
    (OUT / "LITERATURE.md").write_text(lit, encoding="utf-8")

    lines = [
        "# Wall-layer feature stats",
        "",
        f"- Patients with valid wall features: **{len(df)}**",
        "",
        "| feature | n | ρ | p | Kruskal p | medians T1→T4+ |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for _, r in stats_df.iterrows():
        med = "/".join(f"{r[f'median_{STAGE[k]}']:.3g}" for k in range(4))
        lines.append(
            f"| `{r['feature']}` | {int(r['n'])} | {r['spearman_rho']:+.3f} | "
            f"{r['spearman_p']:.2e} | {r['kruskal_p']:.2e} | {med} |"
        )
    lines += [
        "",
        "Figures: `00_wall_depth_score_by_stage.png`, `00_wall_layer_overlay_board.png`",
        "Share: `47_wall_layer_*.png`",
        "",
        "See `LITERATURE.md` for EUS five-layer grounding.",
        "",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"n": len(df), "top": stats_df.head(5).to_dict(orient="records")}, indent=2))


if __name__ == "__main__":
    main()
