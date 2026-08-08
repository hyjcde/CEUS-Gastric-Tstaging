#!/usr/bin/env python3
"""Evaluate whole-lesion vs breakthrough-axis wall features against pathology T.

Also consistency-check vs anatomic breakthrough_max_depth (derived geometry).

Outputs:
  pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/wall_layer_axis/
  results/visualizations/tstage/imaging_truth_share_white_20260729/48_*
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
    compute_wall_axis_features,
    lumen_mask_from_box,
    render_wall_axis_overlay,
)

FEAT = PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1/wall_layer"
PT = (
    PROJECT_ROOT
    / "pipeline/experiments/reports/imaging_truth_tstage_corr_v2"
    / "patient_table_unique_pooled.csv"
)
OUT = PROJECT_ROOT / "pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/wall_layer_axis"
SHARE = PROJECT_ROOT / "results/visualizations/tstage/imaging_truth_share_white_20260729"
STAGE = ["T1", "T2", "T3", "T4+"]
COLORS = {0: "#6B9AC4", 1: "#7EB77F", 2: "#E09F3E", 3: "#C86B6B"}

COMPARE = [
    ("wall_depth_frac_p90", "whole-lesion depth p90"),
    ("wall_layer_score_soft", "whole-lesion soft score"),
    ("wall_serosa_interrupt", "whole-lesion serosa cov."),
    ("wall_axis_depth_frac", "axis depth (breakthrough)"),
    ("wall_axis_depth_frac_sector_p90", "axis sector p90"),
    ("wall_axis_score_soft", "axis soft score"),
    ("wall_axis_serosa_hit", "axis serosa hit"),
    ("wall_axis_overshoot", "axis overshoot"),
    ("breakthrough_max_depth", "anatomic BT max depth"),
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


def assoc(df: pd.DataFrame, feat: str) -> dict:
    sub = df[["label", feat]].dropna()
    sub = sub[np.isfinite(sub[feat])]
    if len(sub) < 30:
        return {"feature": feat, "n": int(len(sub))}
    rho, p = stats.spearmanr(sub["label"], sub[feat])
    groups = [sub.loc[sub["label"] == k, feat].values for k in range(4)]
    groups = [g for g in groups if len(g)]
    try:
        kp = float(stats.kruskal(*groups).pvalue) if len(groups) >= 2 else float("nan")
    except Exception:
        kp = float("nan")
    meds = [float(np.median(sub.loc[sub["label"] == k, feat])) if (sub["label"] == k).any() else float("nan") for k in range(4)]
    return {
        "feature": feat,
        "n": int(len(sub)),
        "spearman_rho": float(rho),
        "spearman_p": float(p),
        "kruskal_p": kp,
        "median_T1": meds[0],
        "median_T2": meds[1],
        "median_T3": meds[2],
        "median_T4+": meds[3],
    }


def resolve_rel(path_str: object) -> Path | None:
    if not path_str or not isinstance(path_str, str) or path_str.lower() == "nan":
        return None
    p = Path(path_str)
    if p.exists():
        return p
    alt = (PROJECT_ROOT / path_str).resolve()
    return alt if alt.exists() else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-examples", type=int, default=3)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    SHARE.mkdir(parents=True, exist_ok=True)
    apply_nature()

    whole_p = pd.read_csv(FEAT / "patient_features_median.csv")
    axis_p = pd.read_csv(FEAT / "patient_features_axis_median.csv")
    pt = pd.read_csv(PT)
    for d in (whole_p, axis_p, pt):
        d["patient_id"] = d["patient_id"].astype(str)

    # breakthrough from frame axis table (median) or patient table if present
    axis_fr = pd.read_csv(FEAT / "frame_features_axis.csv")
    axis_fr["patient_id"] = axis_fr["patient_id"].astype(str)
    bt = (
        axis_fr.groupby("patient_id", as_index=False)["breakthrough_max_depth"]
        .max()
        .rename(columns={"breakthrough_max_depth": "breakthrough_max_depth"})
    )

    df = pt[["patient_id", "label"]].merge(whole_p, on="patient_id", how="inner")
    df = df.merge(axis_p, on="patient_id", how="left", suffixes=("", "_axisdup"))
    df = df.merge(bt, on="patient_id", how="left")
    df["label"] = df["label"].clip(0, 3)

    rows = []
    for feat, _ in COMPARE:
        if feat not in df.columns:
            continue
        rows.append(assoc(df, feat))
    stats_df = pd.DataFrame(rows).sort_values("spearman_p")
    stats_df.to_csv(OUT / "gt_assoc_compare.csv", index=False)

    # Adjacent-stage AUC (axis vs whole depth)
    from sklearn.metrics import roc_auc_score

    auc_rows = []
    for feat in ["wall_depth_frac_p90", "wall_axis_depth_frac", "wall_axis_score_soft", "breakthrough_max_depth"]:
        if feat not in df.columns:
            continue
        for a, b, name in [(0, 1, "T1vsT2"), (1, 2, "T2vsT3"), (2, 3, "T3vsT4"), (0, 3, "T1vsT4"), (0, 2, "T1-2vsT3-4")]:
            if name == "T1-2vsT3-4":
                sub = df[[feat, "label"]].dropna()
                y = (sub["label"] >= 2).astype(int)
                x = sub[feat]
            else:
                sub = df[df["label"].isin([a, b])][[feat, "label"]].dropna()
                y = (sub["label"] == b).astype(int)
                x = sub[feat]
            if y.nunique() < 2 or len(sub) < 40:
                continue
            try:
                auc = float(roc_auc_score(y, x))
            except Exception:
                continue
            auc_rows.append({"feature": feat, "task": name, "auc": auc, "n": int(len(sub))})
    auc_df = pd.DataFrame(auc_rows)
    auc_df.to_csv(OUT / "adjacent_auc_compare.csv", index=False)

    # Violin: whole vs axis depth
    fig, axes = plt.subplots(1, 2, figsize=(5.2, 2.4), dpi=200)
    for ax, feat, title in zip(
        axes,
        ["wall_depth_frac_p90", "wall_axis_depth_frac"],
        ["Whole-lesion depth p90", "Breakthrough-axis depth"],
    ):
        for k in range(4):
            vals = df.loc[df["label"] == k, feat].dropna().values
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
        ax.set_ylabel("depth fraction")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    fig.suptitle(f"Wall depth: whole-lesion vs breakthrough axis (n={len(df)})", y=1.02)
    fig.tight_layout()
    fig.savefig(OUT / "00_whole_vs_axis_by_stage.png", bbox_inches="tight")
    fig.savefig(SHARE / "48_wall_axis_vs_whole_by_stage.png", bbox_inches="tight")
    plt.close(fig)

    # Bar of |rho|
    fig, ax = plt.subplots(figsize=(4.8, 2.6), dpi=200)
    plot_df = stats_df.dropna(subset=["spearman_rho"]).copy()
    plot_df = plot_df.sort_values("spearman_rho")
    colors = ["#C86B6B" if "axis" in r.feature or r.feature.startswith("breakthrough") else "#6B9AC4" for r in plot_df.itertuples()]
    ax.barh(plot_df["feature"], plot_df["spearman_rho"], color=colors, height=0.7)
    ax.axvline(0, color="#333", lw=0.6)
    ax.set_xlabel("Spearman ρ vs pathologic T")
    ax.set_title("GT association: whole (blue) vs axis/BT (red)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "00_rho_compare.png", bbox_inches="tight")
    fig.savefig(SHARE / "48_wall_axis_rho_compare.png", bbox_inches="tight")
    plt.close(fig)

    # Overlay board
    fr = axis_fr[axis_fr["wall_axis_valid"] > 0.5].copy()
    fr["label"] = pd.to_numeric(fr["label"], errors="coerce").clip(0, 3)
    hash_index = build_mask_hash_index()
    panels = []
    for lab in range(4):
        sub = fr[fr["label"] == lab].sort_values("wall_axis_depth_frac", ascending=False)
        # pick mid / high diversity
        picks = []
        if len(sub):
            qs = [0.3, 0.6, 0.9][: args.n_examples]
            for q in qs:
                idx = int(np.clip(round(q * (len(sub) - 1)), 0, len(sub) - 1))
                picks.append(sub.iloc[idx])
        for row in picks:
            img_path = resolve_image_path(row.get("image_path"))
            mask_path = resolve_mask_path(str(row.get("lesion_pred_mask_path", "")), hash_index)
            if img_path is None or mask_path is None:
                continue
            img = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
            mask = load_binary_mask(mask_path)
            if img is None or mask is None:
                continue
            # lumen from anatomic csv path not in axis frame — rebuild box if needed
            # Prefer recompute with angle
            ang = row.get("direction_outward_angle_deg")
            if ang is None or (isinstance(ang, float) and not pd.notna(ang)):
                ang = row.get("anatomic_outward_angle_deg")
            try:
                ang_f = float(ang) if ang is not None and pd.notna(ang) else None
            except Exception:
                ang_f = None
            # Need lumen: load from whole frame table join by image_path
            lumen = None
            outer = None
            # approximate: use lumen box from original anatomic via breakthrough path unavailable —
            # recompute features with lumen from mask SDF shell fallback by reading anatomic again
            # Store lumen path? not in axis csv. Use compute with box zeros fails.
            # Load from frame_features (whole) merge
            panels.append((lab, row, img, mask, ang_f))

    # Reload anatomic for lumen/outer paths
    from extract_gc_us_wall_layer_axis_v1 import load_frames, resolve_rel

    anatomic = load_frames(
        PROJECT_ROOT
        / "pipeline/data/tstaging_4class_anatomic_region_contrastive_phase0/regions"
    )
    anatomic["image_path"] = anatomic["image_path"].astype(str)
    board_rows = []
    for lab, row, img, mask, ang_f in panels[: 4 * args.n_examples]:
        match = anatomic[anatomic["image_path"].astype(str) == str(row.get("image_path"))]
        lumen = outer = None
        if len(match):
            r0 = match.iloc[0]
            lumen = load_binary_mask(resolve_rel(r0.get("anatomic_inner_lumen_mask_path")))
            outer = load_binary_mask(resolve_rel(r0.get("anatomic_outer_wall_mask_path")))
            if lumen is None:
                try:
                    lumen = lumen_mask_from_box(
                        mask.shape,
                        float(r0.get("lumen_box_x1", 0) or 0),
                        float(r0.get("lumen_box_y1", 0) or 0),
                        float(r0.get("lumen_box_x2", 0) or 0),
                        float(r0.get("lumen_box_y2", 0) or 0),
                    )
                except Exception:
                    lumen = None
        if lumen is None:
            continue
        feats = compute_wall_axis_features(mask, lumen, outer, outward_angle_deg=ang_f)
        vis = render_wall_axis_overlay(img, mask, lumen, outer, feats)
        board_rows.append((lab, feats, vis))

    if board_rows:
        n = len(board_rows)
        cols = min(4, n)
        rows_n = int(np.ceil(n / cols))
        fig, axes = plt.subplots(rows_n, cols, figsize=(2.4 * cols, 2.2 * rows_n), dpi=160)
        axes = np.atleast_2d(axes)
        for i, (lab, feats, vis) in enumerate(board_rows):
            r, c = divmod(i, cols)
            ax = axes[r, c]
            ax.imshow(cv2.cvtColor(vis, cv2.COLOR_BGR2RGB))
            ax.set_title(
                f"{STAGE[int(lab)]}  d={feats['wall_axis_depth_frac']:.2f}  s={int(feats['wall_axis_score_soft'])}",
                fontsize=6,
            )
            ax.axis("off")
        for j in range(len(board_rows), rows_n * cols):
            r, c = divmod(j, cols)
            axes[r, c].axis("off")
        fig.suptitle("Breakthrough-axis wall depth (magenta sector, red arrow=extent)", fontsize=8)
        fig.tight_layout()
        fig.savefig(OUT / "00_wall_axis_overlay_board.png", bbox_inches="tight")
        fig.savefig(SHARE / "48_wall_axis_overlay_board.png", bbox_inches="tight")
        plt.close(fig)

    # Literature + verdict markdown
    top = stats_df.head(8).to_dict(orient="records")
    whole_rho = float(stats_df.loc[stats_df.feature == "wall_depth_frac_p90", "spearman_rho"].iloc[0]) if (stats_df.feature == "wall_depth_frac_p90").any() else float("nan")
    axis_rho = float(stats_df.loc[stats_df.feature == "wall_axis_depth_frac", "spearman_rho"].iloc[0]) if (stats_df.feature == "wall_axis_depth_frac").any() else float("nan")
    md = [
        "# Wall-layer axis vs whole-lesion · GT evaluation",
        "",
        "## Verdict",
        "",
        f"- Whole-lesion `wall_depth_frac_p90` vs pathologic T: **ρ={whole_rho:.3f}**",
        f"- Breakthrough-axis `wall_axis_depth_frac` vs pathologic T: **ρ={axis_rho:.3f}**",
        "",
        "Clinical/literature definition of wall staging is **deepest disrupted layer along the invasion path**, not whole-mass SDF statistics.",
        "Axis features follow ContactGeom `penetrationAt` / `deep_idx` and EUS/OCEUS deepest-layer rules.",
        "",
        "## Literature algorithms consulted",
        "",
        "1. **BMC Cancer 2022** — EUS decision algorithm: uT by deepest disrupted layer; uT4a = outer bright line interrupted irregularly.",
        "2. **WJG 2024 OCEUS** (Xu et al.) — TAUS T criteria table: layer continuity / serosa breakthrough with burr·crab-foot at the invasion site.",
        "3. **Frontiers Oncol 2021** — OCEUS U-Net wall ROI + SRAD + Sobel layer edges; thickness **ratios on wall strip**, not lesion blob.",
        "4. **WJGO 2026** — EUS lesion thickness as continuous ≥pT3 predictor (complements categorical uT).",
        "5. **Mocellin 2011** — EUS staging meta-analysis (layer-based T).",
        "6. **In-repo ContactGeom** — `deep_idx` = min remain; `penetrationAt` = extent/local thick along wall→lesion ray near pick.",
        "",
        "## What was wrong in v1 whole-lesion extract",
        "",
        "- Depth = lumen-SDF on **all lesion pixels** / global thickness → lateral bulk contaminates p90.",
        "- Soft score not restricted to breakthrough sector / deepest contact ray.",
        "- Unused `direction_outward_angle_deg` / anatomic outward vector.",
        "",
        "## GT available (no new annotation)",
        "",
        "- **Primary:** patient pathologic T (`label`).",
        "- **Consistency:** `breakthrough_max_depth` (derived lumen-box SDF; same geometric family).",
        "- **Not GT:** anatomic masks, soft scores, reader `deep_idx` (algorithmic).",
        "- Human `visible_layers` in direction annotator: n≈2 — not usable yet.",
        "",
        "## Top associations",
        "",
        "| feature | ρ | p | medians T1→T4+ |",
        "|---|---:|---:|---|",
    ]
    for r in top:
        if "spearman_rho" not in r:
            continue
        md.append(
            f"| `{r['feature']}` | {r['spearman_rho']:+.3f} | {r['spearman_p']:.2e} | "
            f"{r.get('median_T1', float('nan')):.3g}/{r.get('median_T2', float('nan')):.3g}/"
            f"{r.get('median_T3', float('nan')):.3g}/{r.get('median_T4+', float('nan')):.3g} |"
        )
    md += [
        "",
        "## Rebuild",
        "",
        "```bash",
        "python3 scripts/extract_gc_us_wall_layer_axis_v1.py",
        "python3 scripts/eval_gc_us_wall_layer_axis_vs_gt_v1.py",
        "```",
        "",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (OUT / "LITERATURE_ALGORITHMS.md").write_text(
        "\n".join(
            [
                "# Algorithms for gastric wall-layer / invasion depth",
                "",
                "## Clinical rule (EUS / OCEUS)",
                "Stage by the **deepest layer disrupted on the invasion path**.",
                "T4a cues: outer hyperechoic line interrupted (often irregular / spiculated) at the breakthrough site.",
                "",
                "## Computational patterns in papers",
                "",
                "| Paper | Method | Relevance |",
                "|---|---|---|",
                "| BMC Cancer 2022 | Expert EUS visual algorithm (deepest layer) | Label definition for soft score |",
                "| WJG 2024 OCEUS | Layer continuity + serosa breakthrough signs | TAUS-applicable criteria |",
                "| Frontiers 2021 | U-Net wall ROI → SRAD → Sobel 5-layer edges → thickness ratios | Measure on **wall strip**, not mass |",
                "| WJGO thickness model | Continuous EUS thickness → ≥pT3 risk | Continuous depth proxy |",
                "| ContactGeom (repo) | `deep_idx` + `penetrationAt` along wall normal | Implementation template |",
                "",
                "## Recommended measurement (this repo)",
                "1. Find breakthrough axis: anatomic/direction outward angle, else max penetration-ratio ray.",
                "2. Local wall thickness along that ray (lumen→outer).",
                "3. Lesion extent along ray → `depth_frac = extent / thick`.",
                "4. Soft layer/score from depth_frac; serosa_hit if lesion covers outer on that ray.",
                "5. Evaluate vs pathologic T; do not claim L1–L5 pixel GT.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    summary = {
        "n_patients": int(len(df)),
        "whole_rho": whole_rho,
        "axis_rho": axis_rho,
        "top": top[:6],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
