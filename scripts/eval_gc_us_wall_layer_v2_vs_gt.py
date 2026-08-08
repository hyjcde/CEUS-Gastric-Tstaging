#!/usr/bin/env python3
"""Compare wall layer v2 (ContactGeom) vs v1 axis / whole-lesion against pathologic T.

Outputs:
  pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/wall_layer_v2/
  results/visualizations/tstage/imaging_truth_share_white_20260729/49_*
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import roc_auc_score

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
    compute_wall_axis_features_v2,
    lumen_mask_from_box,
    render_wall_axis_v2_overlay,
)
from extract_gc_us_wall_layer_axis_v1 import load_frames, resolve_rel  # noqa: E402

FEAT = PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1/wall_layer"
PT = (
    PROJECT_ROOT
    / "pipeline/experiments/reports/imaging_truth_tstage_corr_v2"
    / "patient_table_unique_pooled.csv"
)
OUT = PROJECT_ROOT / "pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/wall_layer_v2"
SHARE = PROJECT_ROOT / "results/visualizations/tstage/imaging_truth_share_white_20260729"
STAGE = ["T1", "T2", "T3", "T4+"]
COLORS = {0: "#6B9AC4", 1: "#7EB77F", 2: "#E09F3E", 3: "#C86B6B"}

FEATS = [
    "wall_depth_frac_p90",
    "wall_serosa_interrupt",
    "wall_axis_depth_frac",
    "wall_v2_pen_ratio",
    "wall_v2_pen_ratio_sector",
    "wall_v2_score_soft",
    "wall_v2_serosa_proxy",
    "wall_v2_echo_loss",
    "wall_v2_composite",
    "wall_v2_remain_px",
]


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


def resid_rho(df: pd.DataFrame, feat: str, ctrl: str = "tumor_length_cm") -> float:
    sub = df[[feat, ctrl, "label"]].dropna()
    if len(sub) < 40:
        return float("nan")
    x = sub[ctrl].values
    y = sub[feat].values
    # invert remain so higher = deeper
    if feat.endswith("remain_px"):
        y = -y
    A = np.vstack([np.ones(len(x)), x]).T
    resid = y - A @ np.linalg.lstsq(A, y, rcond=None)[0]
    return float(stats.spearmanr(sub["label"], resid).statistic)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    SHARE.mkdir(parents=True, exist_ok=True)
    apply_nature()

    pt = pd.read_csv(PT)
    whole = pd.read_csv(FEAT / "patient_features_median.csv")
    axis = pd.read_csv(FEAT / "patient_features_axis_median.csv")
    v2 = pd.read_csv(FEAT / "patient_features_axis_v2_median.csv")
    for d in (pt, whole, axis, v2):
        d["patient_id"] = d["patient_id"].astype(str)

    df = pt[["patient_id", "label", "tumor_length_cm"]].merge(whole, on="patient_id", how="inner")
    df = df.merge(axis, on="patient_id", how="left", suffixes=("", "_a"))
    df = df.merge(v2, on="patient_id", how="left", suffixes=("", "_v2"))
    df["label"] = df["label"].clip(0, 3)

    rows = []
    for feat in FEATS:
        if feat not in df.columns:
            continue
        sub = df[["label", feat]].dropna()
        y = sub[feat].values
        if feat.endswith("remain_px"):
            y = -y
            rho, p = stats.spearmanr(sub["label"], y)
        else:
            rho, p = stats.spearmanr(sub["label"], sub[feat])
        meds = []
        for k in range(4):
            vals = sub.loc[sub["label"] == k, feat]
            meds.append(float(vals.median()) if len(vals) else float("nan"))
        # AUC T1-2 vs T3-4
        ybin = (sub["label"] >= 2).astype(int)
        score = -sub[feat].values if feat.endswith("remain_px") else sub[feat].values
        try:
            auc = float(roc_auc_score(ybin, score))
        except Exception:
            auc = float("nan")
        rows.append(
            {
                "feature": feat,
                "n": int(len(sub)),
                "spearman_rho": float(rho),
                "spearman_p": float(p),
                "auc_T3plus": auc,
                "resid_rho_length": resid_rho(df, feat),
                "median_T1": meds[0],
                "median_T2": meds[1],
                "median_T3": meds[2],
                "median_T4+": meds[3],
            }
        )
    stats_df = pd.DataFrame(rows).sort_values("spearman_rho", ascending=False, key=lambda s: s.abs())
    stats_df.to_csv(OUT / "compare_v2.csv", index=False)

    # Adjacent AUCs
    auc_rows = []
    for feat in ["wall_depth_frac_p90", "wall_axis_depth_frac", "wall_v2_pen_ratio", "wall_v2_composite", "wall_serosa_interrupt"]:
        if feat not in df.columns:
            continue
        for a, b, name in [(0, 1, "T1vsT2"), (1, 2, "T2vsT3"), (2, 3, "T3vsT4"), (0, 2, "T1-2vsT3-4")]:
            if name == "T1-2vsT3-4":
                sub = df[[feat, "label"]].dropna()
                y = (sub["label"] >= 2).astype(int)
                x = sub[feat]
            else:
                sub = df[df["label"].isin([a, b])][[feat, "label"]].dropna()
                y = (sub["label"] == b).astype(int)
                x = sub[feat]
            if y.nunique() < 2:
                continue
            auc_rows.append({"feature": feat, "task": name, "auc": float(roc_auc_score(y, x)), "n": int(len(sub))})
    pd.DataFrame(auc_rows).to_csv(OUT / "adjacent_auc_v2.csv", index=False)

    # Violin whole vs v2
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.4), dpi=200)
    for ax, feat, title in zip(
        axes,
        ["wall_depth_frac_p90", "wall_axis_depth_frac", "wall_v2_pen_ratio"],
        ["Whole p90", "Axis v1 (lumen)", "v2 ContactGeom pen"],
    ):
        if feat not in df.columns:
            continue
        for k in range(4):
            vals = df.loc[df["label"] == k, feat].dropna().clip(0, 2.5).values
            if len(vals) == 0:
                continue
            parts = ax.violinplot([vals], positions=[k], widths=0.75, showextrema=False, showmedians=True)
            for b in parts["bodies"]:
                b.set_facecolor(COLORS[k])
                b.set_alpha(0.75)
            parts["cmedians"].set_color("#222")
        ax.set_xticks(range(4))
        ax.set_xticklabels(STAGE)
        ax.set_title(title)
        ax.set_ylim(0, 2.2)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    fig.suptitle(f"Wall depth definitions vs pathologic T (n={len(df)})", y=1.02)
    fig.tight_layout()
    fig.savefig(OUT / "00_v2_vs_v1_by_stage.png", bbox_inches="tight")
    fig.savefig(SHARE / "49_wall_v2_vs_v1_by_stage.png", bbox_inches="tight")
    plt.close(fig)

    # Rho bar
    fig, ax = plt.subplots(figsize=(5.0, 2.8), dpi=200)
    plot = stats_df.copy()
    plot["rho_plot"] = plot.apply(
        lambda r: -r["spearman_rho"] if r["feature"].endswith("remain_px") else r["spearman_rho"],
        axis=1,
    )
    # already signed correctly for remain
    plot = plot.sort_values("spearman_rho")
    cols = []
    for f in plot["feature"]:
        if f.startswith("wall_v2"):
            cols.append("#C86B6B")
        elif "axis" in f:
            cols.append("#E09F3E")
        else:
            cols.append("#6B9AC4")
    ax.barh(plot["feature"], plot["spearman_rho"], color=cols, height=0.7)
    ax.axvline(0, color="#333", lw=0.6)
    ax.set_xlabel("Spearman ρ vs pathologic T")
    ax.set_title("blue=whole · orange=axis v1 · red=v2 ContactGeom")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "00_rho_v2.png", bbox_inches="tight")
    fig.savefig(SHARE / "49_wall_v2_rho.png", bbox_inches="tight")
    plt.close(fig)

    # Overlay board
    fr = pd.read_csv(FEAT / "frame_features_axis_v2.csv")
    fr = fr[fr["wall_v2_valid"] > 0.5].copy()
    fr["label"] = pd.to_numeric(fr["label"], errors="coerce").clip(0, 3)
    anatomic = load_frames(
        PROJECT_ROOT / "pipeline/data/tstaging_4class_anatomic_region_contrastive_phase0/regions"
    )
    anatomic["image_path"] = anatomic["image_path"].astype(str)
    hash_index = build_mask_hash_index()
    panels = []
    for lab in range(4):
        sub = fr[fr["label"] == lab].sort_values("wall_v2_pen_ratio")
        if len(sub) < 3:
            continue
        for q in (0.35, 0.65, 0.9):
            panels.append(sub.iloc[int(q * (len(sub) - 1))])
    board = []
    for row in panels:
        img_path = resolve_image_path(row.get("image_path"))
        mask_path = resolve_mask_path(str(row.get("lesion_pred_mask_path", "")), hash_index)
        if img_path is None or mask_path is None:
            continue
        img = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
        mask = load_binary_mask(mask_path)
        match = anatomic[anatomic["image_path"] == str(row.get("image_path"))]
        if img is None or mask is None or not len(match):
            continue
        r0 = match.iloc[0]
        lumen = load_binary_mask(resolve_rel(r0.get("anatomic_inner_lumen_mask_path")))
        outer = load_binary_mask(resolve_rel(r0.get("anatomic_outer_wall_mask_path")))
        if lumen is None:
            lumen = lumen_mask_from_box(
                mask.shape,
                float(r0.get("lumen_box_x1", 0) or 0),
                float(r0.get("lumen_box_y1", 0) or 0),
                float(r0.get("lumen_box_x2", 0) or 0),
                float(r0.get("lumen_box_y2", 0) or 0),
            )
        feats = compute_wall_axis_features_v2(mask, lumen, outer, image_bgr=img)
        vis = render_wall_axis_v2_overlay(img, mask, lumen, outer, feats)
        board.append((int(row["label"]), feats, vis))
        if len(board) >= 12:
            break

    if board:
        cols = 4
        rows_n = int(np.ceil(len(board) / cols))
        fig, axes = plt.subplots(rows_n, cols, figsize=(2.4 * cols, 2.2 * rows_n), dpi=160)
        axes = np.atleast_2d(axes)
        for i, (lab, feats, vis) in enumerate(board):
            r, c = divmod(i, cols)
            ax = axes[r, c]
            ax.imshow(cv2.cvtColor(vis, cv2.COLOR_BGR2RGB))
            ax.set_title(
                f"{STAGE[lab]} pen={feats['wall_v2_pen_ratio']:.2f} s={int(feats['wall_v2_score_soft'])}",
                fontsize=6,
            )
            ax.axis("off")
        for j in range(len(board), rows_n * cols):
            r, c = divmod(j, cols)
            axes[r, c].axis("off")
        fig.suptitle("v2 ContactGeom: orange=outer wall, red arrow=remain to lesion", fontsize=8)
        fig.tight_layout()
        fig.savefig(OUT / "00_v2_overlay_board.png", bbox_inches="tight")
        fig.savefig(SHARE / "49_wall_v2_overlay_board.png", bbox_inches="tight")
        plt.close(fig)

    # SUMMARY
    def get(feat: str, col: str) -> float:
        sub = stats_df[stats_df.feature == feat]
        return float(sub[col].iloc[0]) if len(sub) else float("nan")

    md = [
        "# Wall-layer v2 (ContactGeom) vs prior",
        "",
        "## What changed",
        "",
        "1. Wall reference = **outer-wall contour** (orange), not lumen SDF blob.",
        "2. Local thickness = far non-contact remain P60 (ContactGeom.localWallThickness).",
        "3. `pen_ratio = extent / thick` with overshoot; echo_loss on deep vs healthy ray.",
        "4. `wall_v2_composite` = 0.5·pen + 0.3·serosa_proxy + 0.2·echo_loss.",
        "",
        "## GT metrics (pathologic T, n patients in table)",
        "",
        "| feature | ρ | resid ρ|length | AUC T3+ | medians T1→T4+ |",
        "|---|---:|---:|---:|---|",
    ]
    for _, r in stats_df.iterrows():
        md.append(
            f"| `{r['feature']}` | {r['spearman_rho']:+.3f} | {r['resid_rho_length']:+.3f} | "
            f"{r['auc_T3plus']:.3f} | {r['median_T1']:.3g}/{r['median_T2']:.3g}/"
            f"{r['median_T3']:.3g}/{r['median_T4+']:.3g} |"
        )
    best = stats_df.iloc[0]["feature"] if len(stats_df) else "?"
    md += [
        "",
        f"**Best |ρ| among compared:** `{best}`",
        "",
        "## Practical recommendation",
        "",
        "- Prefer **v2 pen / composite** for interpretable 达层 (definition-correct).",
        "- Keep `wall_serosa_interrupt` if it still wins residual-ρ (coverage signal).",
        "- Do not use lumen-extent axis v1 as primary staging depth.",
        "- Next: SRAD/Sobel layer edges on wall strip (Frontiers 2021) if echo_loss helps.",
        "",
        "## Rebuild",
        "",
        "```bash",
        "python3 scripts/extract_gc_us_wall_layer_axis_v2.py",
        "python3 scripts/eval_gc_us_wall_layer_v2_vs_gt.py",
        "```",
        "",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"n": int(len(df)), "top": stats_df.head(6).to_dict(orient="records")}, indent=2))


if __name__ == "__main__":
    main()
