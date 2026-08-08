#!/usr/bin/env python3
"""Evaluate margin-feature discrimination overall and on held-out test splits.

Splits from patient_table_unique_pooled.source_splits:
  train / val / test_prospective / test_external

Outputs:
  pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/margin_split_eval/
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PATIENT = (
    PROJECT_ROOT
    / "pipeline/experiments/reports/imaging_truth_tstage_corr_v2/patient_table_unique_pooled.csv"
)
FEAT = PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1/margin/patient_features_median.csv"
OUT = (
    PROJECT_ROOT
    / "pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/margin_split_eval"
)

STAGE = {0: "T1", 1: "T2", 2: "T3", 3: "T4+"}
FOCUS = [
    "margin_spic_robust",
    "margin_shape_fd_high",
    "margin_shape_solidity",
    "margin_shape_lobulation",
    "margin_bof_high_mean",
    "margin_nrg_mean",
    "margin_clear_robust",
    "margin_mi_band",
    "seg_irregularity",  # baseline control
]


def eval_split(source_splits: object) -> str:
    parts = set(str(source_splits).replace(" ", "").split(","))
    if "external" in parts:
        return "test_external"
    if "prospective" in parts and "train" not in parts and "val" not in parts:
        return "test_prospective"
    if "val" in parts:
        return "val"
    if "holdout" in parts:
        return "holdout"
    if "train" in parts or "prospective" in parts:
        return "train"
    return "other"


def spearman(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    if len(x) < 8 or np.unique(x).size < 2 or np.unique(y).size < 2:
        return float("nan"), float("nan")
    r, p = stats.spearmanr(x, y)
    return float(r), float(p)


def partial_spearman_length(df: pd.DataFrame, feature: str) -> tuple[float, float, int]:
    sub = df[[feature, "label", "tumor_length_cm"]].dropna()
    sub = sub[np.isfinite(sub).all(axis=1)]
    n = len(sub)
    if n < 30 or sub[feature].nunique() < 2:
        return float("nan"), float("nan"), n
    ranks = sub.rank(method="average")
    y = ranks["label"].to_numpy()
    x = ranks[feature].to_numpy()
    Z = np.column_stack([np.ones(n), ranks["tumor_length_cm"].to_numpy()])
    bx, *_ = np.linalg.lstsq(Z, x, rcond=None)
    by, *_ = np.linalg.lstsq(Z, y, rcond=None)
    rx = x - Z @ bx
    ry = y - Z @ by
    if np.std(rx) < 1e-12 or np.std(ry) < 1e-12:
        return float("nan"), float("nan"), n
    r, p = stats.spearmanr(rx, ry)
    return float(r), float(p), n


def auc_binary(score: np.ndarray, y: np.ndarray) -> float:
    """Mann–Whitney AUC for binary y in {0,1}."""
    s0 = score[y == 0]
    s1 = score[y == 1]
    if len(s0) < 3 or len(s1) < 3:
        return float("nan")
    # AUC = P(score1 > score0) + 0.5 P(equal)
    # via rank: (mean_rank_pos - (npos+1)/2) / nneg
    n1, n0 = len(s1), len(s0)
    ranks = stats.rankdata(np.concatenate([s1, s0]))
    r1 = ranks[:n1].sum()
    return float((r1 - n1 * (n1 + 1) / 2.0) / (n1 * n0))


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


def main() -> None:
    apply_style()
    OUT.mkdir(parents=True, exist_ok=True)

    pt = pd.read_csv(PATIENT)
    feat = pd.read_csv(FEAT)
    pt["patient_id"] = pt["patient_id"].astype(str)
    feat["patient_id"] = feat["patient_id"].astype(str)
    df = feat.merge(
        pt[
            [
                "patient_id",
                "label",
                "tumor_length_cm",
                "source_splits",
                "seg_irregularity",
            ]
        ],
        on="patient_id",
        how="inner",
        suffixes=("", "_pt"),
    )
    if "label_pt" in df.columns:
        df["label"] = df["label"].fillna(df["label_pt"])
    df["label"] = pd.to_numeric(df["label"], errors="coerce")
    df["tumor_length_cm"] = pd.to_numeric(df["tumor_length_cm"], errors="coerce")
    df["eval_split"] = df["source_splits"].map(eval_split)
    df = df[df["eval_split"].isin(["train", "val", "test_prospective", "test_external"])].copy()
    df.to_csv(OUT / "patient_joined_with_split.csv", index=False)

    splits = ["train", "val", "test_prospective", "test_external", "ALL"]
    rows = []
    for split in splits:
        sub = df if split == "ALL" else df[df["eval_split"] == split]
        n = len(sub)
        n_lab = sub["label"].value_counts().sort_index().to_dict()
        for feat_name in FOCUS:
            if feat_name not in sub.columns:
                continue
            x = pd.to_numeric(sub[feat_name], errors="coerce")
            m = x.notna() & np.isfinite(x) & sub["label"].notna()
            xx = x[m].to_numpy(float)
            yy = sub.loc[m, "label"].to_numpy(float)
            rho, p = spearman(xx, yy)
            pr, pp, n_p = partial_spearman_length(sub.loc[m], feat_name)
            # Kruskal across 4 stages
            groups = [xx[yy == k] for k in range(4) if np.any(yy == k)]
            try:
                if (
                    len(groups) >= 2
                    and all(len(g) >= 2 for g in groups)
                    and np.unique(xx).size >= 2
                ):
                    kw_h, kw_p = stats.kruskal(*groups)
                else:
                    kw_h, kw_p = float("nan"), float("nan")
            except ValueError:
                kw_h, kw_p = float("nan"), float("nan")
            # binary AUCs (higher score → higher T for spic/fd; invert solidity)
            score = xx.copy()
            if "solidity" in feat_name or feat_name in ("margin_nrg_mean", "margin_clear_robust", "margin_mi_band"):
                score = -score  # lower solidity / lower clear → higher T often
            y_ea = (yy >= 2).astype(int)  # T3+ vs T1-2
            y_23 = yy[(yy == 1) | (yy == 2)]
            s_23 = score[(yy == 1) | (yy == 2)]
            y_23b = (y_23 == 2).astype(int)
            auc_ea = auc_binary(score, y_ea)
            auc_23 = auc_binary(s_23, y_23b) if len(y_23b) else float("nan")
            meds = {STAGE[k]: float(np.median(xx[yy == k])) if np.any(yy == k) else float("nan") for k in range(4)}
            rows.append(
                {
                    "split": split,
                    "feature": feat_name,
                    "n": int(m.sum()),
                    "n_T1": int(n_lab.get(0, 0)),
                    "n_T2": int(n_lab.get(1, 0)),
                    "n_T3": int(n_lab.get(2, 0)),
                    "n_T4+": int(n_lab.get(3, 0)),
                    "spearman_rho": rho,
                    "spearman_p": p,
                    "partial_rho_length": pr,
                    "partial_p_length": pp,
                    "kruskal_H": float(kw_h),
                    "kruskal_p": float(kw_p),
                    "auc_T3plus_vs_early": auc_ea,
                    "auc_T3_vs_T2": auc_23,
                    "median_T1": meds["T1"],
                    "median_T2": meds["T2"],
                    "median_T3": meds["T3"],
                    "median_T4+": meds["T4+"],
                }
            )

    res = pd.DataFrame(rows)
    res.to_csv(OUT / "discrimination_by_split.csv", index=False)

    # --- plots ---
    key_feats = [
        "margin_spic_robust",
        "margin_shape_fd_high",
        "margin_shape_solidity",
        "margin_bof_high_mean",
        "margin_clear_robust",
        "seg_irregularity",
    ]
    split_order = ["train", "val", "test_prospective", "test_external"]
    colors = {
        "train": "#4C78A8",
        "val": "#72B7B2",
        "test_prospective": "#F58518",
        "test_external": "#E45756",
    }

    # Forest of Spearman by split
    fig, ax = plt.subplots(figsize=(10.5, 5.2))
    y_pos = []
    y_labels = []
    ypos = 0
    for feat_name in key_feats:
        for sp in split_order:
            r = res[(res["feature"] == feat_name) & (res["split"] == sp)]
            if r.empty:
                continue
            rho = float(r.iloc[0]["spearman_rho"])
            n = int(r.iloc[0]["n"])
            ax.scatter([rho], [ypos], color=colors[sp], s=40, zorder=3)
            ax.plot([0, rho], [ypos, ypos], color=colors[sp], lw=1.2, alpha=0.8)
            y_labels.append(f"{feat_name.replace('margin_', '')} · {sp} (n={n})")
            y_pos.append(ypos)
            ypos += 1
        ypos += 0.6  # gap between features
    ax.axvline(0, color="#888", lw=0.8)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(y_labels, fontsize=7)
    ax.set_xlabel("Spearman ρ vs ordinal T stage")
    ax.set_title("Margin features · discrimination by split (ρ→T)")
    ax.set_xlim(-0.45, 0.45)
    for sp, c in colors.items():
        ax.scatter([], [], color=c, label=sp)
    ax.legend(fontsize=7, framealpha=0.25, loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT / "00_spearman_by_split.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    # Stage median trends for spic_robust / fd_high / solidity on each split
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.8), sharey=False)
    for ax, feat_name, title, invert in zip(
        axes,
        ["margin_spic_robust", "margin_shape_fd_high", "margin_shape_solidity"],
        ["spic_robust (↑ worse)", "fd_high (↑ worse)", "solidity (↓ worse)"],
        [False, False, True],
    ):
        for sp in split_order:
            r = res[(res["feature"] == feat_name) & (res["split"] == sp)]
            if r.empty:
                continue
            meds = [float(r.iloc[0][f"median_{STAGE[k]}"]) for k in range(4)]
            ax.plot(range(4), meds, "o-", color=colors[sp], label=f"{sp} n={int(r.iloc[0]['n'])}", lw=1.3, ms=5)
        ax.set_xticks(range(4))
        ax.set_xticklabels(["T1", "T2", "T3", "T4+"])
        ax.set_title(title)
        if invert:
            ax.invert_yaxis()
    axes[0].legend(fontsize=6, framealpha=0.25)
    fig.suptitle("Stage medians by split", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "00_stage_medians_by_split.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    # AUC bars T3+ vs early
    fig, ax = plt.subplots(figsize=(9.5, 4.0))
    width = 0.18
    x0 = np.arange(len(key_feats))
    for i, sp in enumerate(split_order):
        vals = []
        for feat_name in key_feats:
            r = res[(res["feature"] == feat_name) & (res["split"] == sp)]
            vals.append(float(r.iloc[0]["auc_T3plus_vs_early"]) if not r.empty else np.nan)
        ax.bar(x0 + (i - 1.5) * width, vals, width=width, color=colors[sp], label=sp, edgecolor="white", linewidth=0.3)
    ax.axhline(0.5, color="#888", ls="--", lw=0.8)
    ax.set_xticks(x0)
    ax.set_xticklabels([f.replace("margin_", "").replace("seg_", "seg_") for f in key_feats], rotation=25, ha="right")
    ax.set_ylim(0.35, 0.75)
    ax.set_ylabel("AUC (T3+ vs T1–T2)")
    ax.set_title("Binary discrimination by split")
    ax.legend(fontsize=7, framealpha=0.25, ncol=2)
    fig.tight_layout()
    fig.savefig(OUT / "00_auc_t3plus_by_split.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    # Summary markdown
    lines = [
        "# Margin feature discrimination by split",
        "",
        "Eval split from `source_splits` in unique_pooled patient table.",
        "",
        "## Cohort sizes (joined with margin features)",
        "",
    ]
    for sp in split_order:
        sub = df[df["eval_split"] == sp]
        vc = sub["label"].value_counts().sort_index()
        lines.append(
            f"- **{sp}**: n={len(sub)} · "
            + ", ".join(f"{STAGE[k]}={int(vc.get(k, 0))}" for k in range(4))
        )
    lines += ["", "## Key metrics", ""]
    show = res[res["feature"].isin(key_feats) & res["split"].isin(split_order + ["ALL"])].copy()
    show = show.sort_values(["feature", "split"])
    lines.append(
        "| feature | split | n | ρ | partialρ\\|L | AUC T3+ | AUC T2/T3 | medians T1→T4+ |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---|")
    for _, r in show.iterrows():
        med = "/".join(
            f"{r[f'median_{STAGE[k]}']:.3g}" if np.isfinite(r[f"median_{STAGE[k]}"]) else "—"
            for k in range(4)
        )
        lines.append(
            f"| `{r['feature']}` | {r['split']} | {int(r['n'])} | "
            f"{r['spearman_rho']:.3f} | {r['partial_rho_length']:.3f} | "
            f"{r['auc_T3plus_vs_early']:.3f} | {r['auc_T3_vs_T2']:.3f} | {med} |"
        )
    lines += [
        "",
        "## Figures",
        "- `00_spearman_by_split.png`",
        "- `00_stage_medians_by_split.png`",
        "- `00_auc_t3plus_by_split.png`",
        "",
        "Rebuild: `python3 scripts/eval_gc_us_margin_split_discrimination.py`",
        "",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # compact JSON for canvas
    summary = {
        "n_by_split": {sp: int((df["eval_split"] == sp).sum()) for sp in split_order},
        "label_by_split": {
            sp: df[df["eval_split"] == sp]["label"].value_counts().sort_index().astype(int).to_dict()
            for sp in split_order
        },
        "rows": show.to_dict(orient="records"),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps({"out": str(OUT), "n_by_split": summary["n_by_split"]}, indent=2))
    # print focus table
    cols = [
        "feature",
        "split",
        "n",
        "spearman_rho",
        "partial_rho_length",
        "auc_T3plus_vs_early",
        "auc_T3_vs_T2",
    ]
    print(show[cols].to_string(index=False))


if __name__ == "__main__":
    main()
