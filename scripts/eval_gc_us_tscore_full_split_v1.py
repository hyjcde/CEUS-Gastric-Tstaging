#!/usr/bin/env python3
"""Full-split T-score model eval: train + all tests, T3+ and 4-class.

Fits on train only; scores every split including train (in-sample) and
val / test_prospective / test_external.

Metrics per model × split:
  - auc_T3plus, acc_T3plus
  - auc_4class_ovr_macro, acc_4class, qwk_4class
  - auc_T1vsT2, auc_T2vsT3, auc_T3vsT4 (pairwise on subset)
  - spearman(score_T3plus, label)

Outputs:
  pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/full_split_v1/
  results/visualizations/tstage/imaging_truth_share_white_20260729/52_*
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    cohen_kappa_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "pipeline/data/gc_us_tscore_features_v1/feature_pack_v1/patient_features.csv"
OUT = ROOT / "pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/full_split_v1"
SHARE = ROOT / "results/visualizations/tstage/imaging_truth_share_white_20260729"
SPLITS = ["train", "val", "test_prospective", "test_external"]
STAGE = ["T1", "T2", "T3", "T4+"]

MODELS: dict[str, list[str]] = {
    "length": ["tumor_length_cm"],
    "size_max": ["size_max_diameter_cm"],
    "length+thick": ["tumor_length_cm", "tumor_thickness_cm"],
    "length+cea": ["tumor_length_cm", "cea_binary"],
    "length+short_axis": ["tumor_length_cm", "seg_short_axis_ratio"],
    "length+dyn": ["tumor_length_cm", "dyn_invasion_agree"],
    "length+serosa": ["tumor_length_cm", "wall_serosa_interrupt"],
    "length+thick+cea": ["tumor_length_cm", "tumor_thickness_cm", "cea_binary"],
    "length+serosa+dyn": ["tumor_length_cm", "wall_serosa_interrupt", "dyn_invasion_agree"],
    "morph_margin+length": [
        "tumor_length_cm",
        "morph_peak_sharpness_max",
        "morph_solidity",
        "margin_spic_robust",
    ],
    "kitchen": [
        "tumor_length_cm",
        "tumor_thickness_cm",
        "cea_binary",
        "seg_short_axis_ratio",
        "wall_serosa_interrupt",
        "dyn_invasion_agree",
        "margin_spic_robust__frac_high",
        "bt_v2_max_outward_depth__max",
    ],
    "pack_core+length": [
        "tumor_length_cm",
        "morph_peak_sharpness_max",
        "morph_solidity",
        "margin_spic_robust",
        "wall_serosa_interrupt",
        "wall_fuse_serosa_remain",
        "dyn_invasion_agree",
        "seg_short_axis_ratio",
    ],
}


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


def make_clf() -> Pipeline:
    return Pipeline(
        [
            ("sc", StandardScaler()),
            (
                "clf",
                LogisticRegression(
                    max_iter=3000,
                    class_weight="balanced",
                    C=1.0,
                ),
            ),
        ]
    )


def auc_binary(y: np.ndarray, score: np.ndarray) -> float:
    if len(np.unique(y)) < 2:
        return float("nan")
    return float(roc_auc_score(y, score))


def auc_ovr_macro(y: np.ndarray, proba: np.ndarray, classes: list) -> float:
    from sklearn.preprocessing import label_binarize

    Y = label_binarize(y, classes=classes)
    if Y.shape[1] == 1:
        return float("nan")
    aucs = []
    for i in range(len(classes)):
        if Y[:, i].sum() == 0 or Y[:, i].sum() == len(Y):
            continue
        aucs.append(roc_auc_score(Y[:, i], proba[:, i]))
    return float(np.mean(aucs)) if aucs else float("nan")


def pairwise_auc(y: np.ndarray, score: np.ndarray, a: int, b: int) -> float:
    m = np.isin(y, [a, b])
    if m.sum() < 20:
        return float("nan")
    yy = (y[m] == b).astype(int)
    if len(np.unique(yy)) < 2:
        return float("nan")
    return float(roc_auc_score(yy, score[m]))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    SHARE.mkdir(parents=True, exist_ok=True)
    apply_nature()

    df = pd.read_csv(PACK)
    df["patient_id"] = df["patient_id"].astype(str)
    df["label"] = pd.to_numeric(df["label"], errors="coerce").clip(0, 3)
    df = df[df["eval_split"].isin(SPLITS) & df["label"].notna()].copy()
    df["y_t3plus"] = (df["label"] >= 2).astype(int)

    # resolve models to available columns
    models = {}
    for name, feats in MODELS.items():
        use = [f for f in feats if f in df.columns]
        if use:
            models[name] = use

    # Common complete-case cohort (kitchen ∪ pack_core) so train/test N match across models
    anchor_feats = []
    for key in ("kitchen", "pack_core+length"):
        if key in models:
            anchor_feats.extend(models[key])
    anchor_feats = list(dict.fromkeys(anchor_feats + ["label", "tumor_length_cm"]))
    anchor_feats = [f for f in anchor_feats if f in df.columns]
    cohort = df.dropna(subset=anchor_feats).copy()
    n_by_split = cohort["eval_split"].value_counts().to_dict()

    train = cohort[cohort["eval_split"] == "train"]
    rows = []
    pred_frames = []

    for model_name, feats in models.items():
        tr = train.dropna(subset=feats + ["label"])
        if len(tr) < 80:
            continue
        Xtr = tr[feats]
        ytr_bin = tr["y_t3plus"].to_numpy()
        ytr_mc = tr["label"].astype(int).to_numpy()

        pipe_bin = make_clf()
        pipe_mc = make_clf()
        pipe_bin.fit(Xtr, ytr_bin)
        pipe_mc.fit(Xtr, ytr_mc)
        classes = sorted(pipe_mc.named_steps["clf"].classes_.tolist())

        for split in SPLITS:
            sub = cohort[cohort["eval_split"] == split].dropna(subset=feats + ["label"])
            if len(sub) < 15:
                continue
            X = sub[feats]
            y_bin = sub["y_t3plus"].to_numpy()
            y_mc = sub["label"].astype(int).to_numpy()
            score = pipe_bin.predict_proba(X)[:, 1]
            pred_bin = pipe_bin.predict(X)
            proba_mc = pipe_mc.predict_proba(X)
            pred_mc = pipe_mc.predict(X)

            rows.append(
                {
                    "model": model_name,
                    "n_features": len(feats),
                    "split": split,
                    "n": int(len(sub)),
                    "auc_T3plus": auc_binary(y_bin, score),
                    "acc_T3plus": float(accuracy_score(y_bin, pred_bin)),
                    "auc_4class_ovr_macro": auc_ovr_macro(y_mc, proba_mc, classes),
                    "acc_4class": float(accuracy_score(y_mc, pred_mc)),
                    "qwk_4class": float(cohen_kappa_score(y_mc, pred_mc, weights="quadratic")),
                    "auc_T1vsT2": pairwise_auc(y_mc, score, 0, 1),
                    "auc_T2vsT3": pairwise_auc(y_mc, score, 1, 2),
                    "auc_T3vsT4": pairwise_auc(y_mc, score, 2, 3),
                    "spearman_score_vs_T": float(
                        pd.Series(score).corr(pd.Series(y_mc), method="spearman")
                    ),
                    "feats": ",".join(feats),
                }
            )
            pred_frames.append(
                pd.DataFrame(
                    {
                        "patient_id": sub["patient_id"].to_numpy(),
                        "eval_split": split,
                        "label": y_mc,
                        "model": model_name,
                        "score_T3plus": score,
                        "pred_T3plus": pred_bin,
                        "pred_4class": pred_mc,
                    }
                )
            )

    res = pd.DataFrame(rows)
    res.to_csv(OUT / "metrics_by_split.csv", index=False)
    if pred_frames:
        pd.concat(pred_frames, ignore_index=True).to_csv(OUT / "predictions.csv", index=False)

    # pivots
    for metric in ["auc_T3plus", "qwk_4class", "auc_4class_ovr_macro", "acc_4class"]:
        piv = res.pivot(index="model", columns="split", values=metric)
        piv = piv.reindex(columns=[c for c in SPLITS if c in piv.columns])
        if set(["val", "test_prospective", "test_external"]).issubset(piv.columns):
            piv["mean_heldout"] = piv[["val", "test_prospective", "test_external"]].mean(axis=1)
            piv = piv.sort_values("mean_heldout", ascending=False)
        piv.to_csv(OUT / f"pivot_{metric}.csv")

    # focus models for plots
    focus = [
        m
        for m in [
            "length",
            "length+cea",
            "length+short_axis",
            "length+dyn",
            "length+serosa",
            "kitchen",
            "pack_core+length",
            "morph_margin+length",
        ]
        if m in res.model.unique()
    ]
    if not focus:
        focus = sorted(res.model.unique())[:8]

    # Figure: T3+ AUC all splits including train
    fig, ax = plt.subplots(figsize=(6.2, 3.2), dpi=200)
    x = np.arange(len(focus))
    width = 0.2
    for i, sp in enumerate(SPLITS):
        vals = []
        for m in focus:
            sub = res[(res.model == m) & (res.split == sp)]
            vals.append(float(sub.auc_T3plus.iloc[0]) if len(sub) else np.nan)
        ax.bar(x + (i - 1.5) * width, vals, width=width, label=sp)
    ax.set_xticks(x)
    ax.set_xticklabels(focus, rotation=25, ha="right")
    ax.set_ylabel("AUC T3+")
    ax.set_ylim(0.5, 1.0)
    ax.legend(frameon=False, fontsize=5, ncol=4)
    ax.set_title("T3+ AUC by split (train = in-sample; others = held-out)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "00_auc_T3plus_all_splits.png", bbox_inches="tight")
    fig.savefig(SHARE / "52_tscore_auc_T3plus_all_splits.png", bbox_inches="tight")
    plt.close(fig)

    # Figure: QWK 4-class all splits
    fig, ax = plt.subplots(figsize=(6.2, 3.2), dpi=200)
    for i, sp in enumerate(SPLITS):
        vals = []
        for m in focus:
            sub = res[(res.model == m) & (res.split == sp)]
            vals.append(float(sub.qwk_4class.iloc[0]) if len(sub) else np.nan)
        ax.bar(x + (i - 1.5) * width, vals, width=width, label=sp)
    ax.set_xticks(x)
    ax.set_xticklabels(focus, rotation=25, ha="right")
    ax.set_ylabel("QWK (4-class)")
    ax.set_ylim(0.0, 1.0)
    ax.legend(frameon=False, fontsize=5, ncol=4)
    ax.set_title("4-class quadratic weighted κ by split")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "00_qwk_4class_all_splits.png", bbox_inches="tight")
    fig.savefig(SHARE / "52_tscore_qwk_4class_all_splits.png", bbox_inches="tight")
    plt.close(fig)

    # Figure: adjacent AUCs for kitchen / length on each split
    adj_models = [m for m in ["length", "kitchen", "pack_core+length"] if m in focus]
    if adj_models:
        fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.4), dpi=200)
        tasks = [("auc_T1vsT2", "T1 vs T2"), ("auc_T2vsT3", "T2 vs T3"), ("auc_T3vsT4", "T3 vs T4+")]
        for ax, (col, title) in zip(axes, tasks):
            xx = np.arange(len(SPLITS))
            w = 0.25
            for i, m in enumerate(adj_models):
                vals = []
                for sp in SPLITS:
                    sub = res[(res.model == m) & (res.split == sp)]
                    vals.append(float(sub[col].iloc[0]) if len(sub) else np.nan)
                ax.bar(xx + (i - 1) * w, vals, width=w, label=m)
            ax.set_xticks(xx)
            ax.set_xticklabels(["train", "val", "prosp", "ext"], fontsize=5)
            ax.set_ylim(0.4, 1.0)
            ax.axhline(0.5, color="#aaa", lw=0.5, ls="--")
            ax.set_title(title)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
        axes[0].legend(frameon=False, fontsize=4)
        fig.suptitle("Adjacent-stage AUC (binary score from T3+ head)", y=1.02)
        fig.tight_layout()
        fig.savefig(OUT / "00_adjacent_auc_by_split.png", bbox_inches="tight")
        fig.savefig(SHARE / "52_tscore_adjacent_auc_by_split.png", bbox_inches="tight")
        plt.close(fig)

    # SUMMARY tables
    piv_t3 = pd.read_csv(OUT / "pivot_auc_T3plus.csv", index_col=0)
    piv_qwk = pd.read_csv(OUT / "pivot_qwk_4class.csv", index_col=0)

    md = [
        "# Full-split T-score evaluation (train + all tests)",
        "",
        f"Pack: `{PACK.relative_to(ROOT)}`",
        f"Complete-case N by split (anchor=kitchen∪pack_core): {n_by_split}",
        "",
        "Fit on **train** only. Same patient cohort for all models (drop rows missing kitchen/pack features).",
        "Metrics on train (in-sample) and val / prospective / external.",
        "",
        "## AUC T3+ (binary)",
        "",
        piv_t3.round(3).to_markdown(),
        "",
        "## QWK 4-class (ordinal agreement)",
        "",
        piv_qwk.round(3).to_markdown(),
        "",
        "## Per-split detail (selected models)",
        "",
    ]
    for m in focus:
        md.append(f"### `{m}`")
        md.append("")
        sub = res[res.model == m][
            [
                "split",
                "n",
                "auc_T3plus",
                "qwk_4class",
                "auc_4class_ovr_macro",
                "acc_4class",
                "auc_T1vsT2",
                "auc_T2vsT3",
                "auc_T3vsT4",
            ]
        ].copy()
        md.append(sub.round(3).to_markdown(index=False))
        md.append("")

    md += [
        "## Rebuild",
        "",
        "```bash",
        "python3 scripts/build_gc_us_tscore_feature_pack_v1.py",
        "python3 scripts/eval_gc_us_tscore_full_split_v1.py",
        "```",
        "",
        "Figures: `52_tscore_*_all_splits.png`",
        "",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    # print compact
    print("N by split:", n_by_split)
    print("\n=== AUC T3+ ===")
    print(piv_t3.round(3).to_string())
    print("\n=== QWK 4-class ===")
    print(piv_qwk.round(3).to_string())
    print("\n=== kitchen all metrics ===")
    if "kitchen" in res.model.values:
        print(
            res[res.model == "kitchen"][
                [
                    "split",
                    "n",
                    "auc_T3plus",
                    "qwk_4class",
                    "auc_4class_ovr_macro",
                    "acc_4class",
                    "auc_T1vsT2",
                    "auc_T2vsT3",
                    "auc_T3vsT4",
                ]
            ]
            .round(3)
            .to_string(index=False)
        )
    print(json.dumps({"models": list(models.keys()), "out": str(OUT)}, indent=2))


if __name__ == "__main__":
    main()
