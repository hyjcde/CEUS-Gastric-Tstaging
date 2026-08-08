#!/usr/bin/env python3
"""Deepest-frame wall aggregation + length-controlled split models.

Clinical T is decided by the deepest invasion site; patient median dilutes it.
Compares median / p10-remain / min-remain aggregations and fuse+length logistics.

Outputs:
  pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/wall_layer_v2_deepest/
  results/visualizations/tstage/imaging_truth_share_white_20260729/50_*
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
FEAT = ROOT / "pipeline/data/gc_us_tscore_features_v1/wall_layer"
PT = (
    ROOT
    / "pipeline/experiments/reports/imaging_truth_tstage_corr_v2"
    / "patient_table_unique_pooled.csv"
)
OUT = ROOT / "pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/wall_layer_v2_deepest"
SHARE = ROOT / "results/visualizations/tstage/imaging_truth_share_white_20260729"

COLS_MIN = ["wall_v2_remain_px"]
COLS_MAX = [
    "wall_v2_pen_ratio",
    "wall_v2_pen_ratio_sector",
    "wall_v2_composite",
    "wall_v2_serosa_proxy",
    "wall_v2_overshoot",
    "wall_v2_echo_loss",
    "wall_v2_score_soft",
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


def make_agg(fr: pd.DataFrame, how: str) -> pd.DataFrame:
    if how == "median":
        a = fr.groupby("patient_id")[COLS_MIN + COLS_MAX].median().reset_index()
    elif how == "p90":
        a = (
            fr.groupby("patient_id")[COLS_MAX]
            .quantile(0.9)
            .join(fr.groupby("patient_id")[COLS_MIN].quantile(0.1))
            .reset_index()
        )
    elif how == "max":
        a = (
            fr.groupby("patient_id")[COLS_MAX]
            .max()
            .join(fr.groupby("patient_id")[COLS_MIN].min())
            .reset_index()
        )
    else:
        raise ValueError(how)
    return a.rename(columns={c: f"{c}__{how}" for c in COLS_MIN + COLS_MAX})


def score_of(feat: str, series: pd.Series) -> np.ndarray:
    s = series.astype(float).to_numpy()
    return -s if "remain_px" in feat else s


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    SHARE.mkdir(parents=True, exist_ok=True)
    apply_nature()

    pt = pd.read_csv(PT)
    pt["patient_id"] = pt["patient_id"].astype(str)
    pt["label"] = pt["label"].clip(0, 3)
    pt["eval_split"] = pt["source_splits"].map(eval_split)

    fr = pd.read_csv(FEAT / "frame_features_axis_v2.csv")
    fr["patient_id"] = fr["patient_id"].astype(str)
    fr = fr[fr["wall_v2_valid"] > 0.5].copy()
    wh = pd.read_csv(FEAT / "patient_features_median.csv")
    wh["patient_id"] = wh["patient_id"].astype(str)

    base = pt[["patient_id", "label", "tumor_length_cm", "eval_split"]].merge(
        wh[["patient_id", "wall_serosa_interrupt", "wall_depth_frac_p90"]],
        on="patient_id",
        how="inner",
    )
    for h in ["median", "p90", "max"]:
        base = base.merge(make_agg(fr, h), on="patient_id", how="left")

    for h in ["median", "p90", "max"]:
        rem = base[f"wall_v2_remain_px__{h}"].astype(float)
        ser = base["wall_serosa_interrupt"].astype(float)
        comp = base[f"wall_v2_composite__{h}"].astype(float)
        base[f"fuse_serosa_remain__{h}"] = 0.5 * ser.rank(pct=True) + 0.5 * (-rem).rank(pct=True)
        base[f"fuse3__{h}"] = (
            0.40 * ser.rank(pct=True) + 0.35 * (-rem).rank(pct=True) + 0.25 * comp.rank(pct=True)
        )

    cand: list[str] = []
    for h in ["median", "p90", "max"]:
        cand += [
            f"wall_v2_remain_px__{h}",
            f"wall_v2_pen_ratio__{h}",
            f"wall_v2_pen_ratio_sector__{h}",
            f"wall_v2_composite__{h}",
            f"fuse_serosa_remain__{h}",
            f"fuse3__{h}",
        ]
    cand += ["wall_serosa_interrupt", "wall_depth_frac_p90", "tumor_length_cm"]

    rows = []
    for feat in cand:
        cols = ["label", feat] if feat == "tumor_length_cm" else ["label", feat, "tumor_length_cm"]
        sub = base.loc[:, ~base.columns.duplicated()][cols].dropna()
        y = score_of(feat, sub[feat])
        rho, p = stats.spearmanr(sub["label"].to_numpy(), y)
        auc = float(roc_auc_score((sub["label"] >= 2).astype(int).to_numpy(), y))
        if feat == "tumor_length_cm":
            rrho = float(rho)
        else:
            A = np.vstack([np.ones(len(sub)), sub["tumor_length_cm"].to_numpy()]).T
            resid = y - A @ np.linalg.lstsq(A, y, rcond=None)[0]
            rrho = float(stats.spearmanr(sub["label"].to_numpy(), resid).statistic)
        meds = [float(sub.loc[sub["label"] == k, feat].median()) for k in range(4)]
        rows.append(
            {
                "feature": feat,
                "n": int(len(sub)),
                "rho": float(rho),
                "p": float(p),
                "auc_T3": auc,
                "resid_rho": rrho,
                "med_T1": meds[0],
                "med_T2": meds[1],
                "med_T3": meds[2],
                "med_T4": meds[3],
            }
        )
    uni = pd.DataFrame(rows).sort_values("rho", ascending=False)
    uni.to_csv(OUT / "agg_univariate.csv", index=False)

    def fit_auc(train: pd.DataFrame, test: pd.DataFrame, feats: list[str]):
        need = list(dict.fromkeys(feats + ["label", "tumor_length_cm"]))
        tr = train.dropna(subset=need).copy()
        te = test.dropna(subset=need).copy()
        if len(tr) < 80 or len(te) < 30:
            return None
        ytr = (tr["label"] >= 2).astype(int).to_numpy()
        yte = (te["label"] >= 2).astype(int).to_numpy()
        if len(np.unique(ytr)) < 2 or len(np.unique(yte)) < 2:
            return None
        Xtr = np.column_stack([score_of(f, tr[f]) for f in feats])
        Xte = np.column_stack([score_of(f, te[f]) for f in feats])
        sc = StandardScaler()
        Xtr = sc.fit_transform(Xtr)
        Xte = sc.transform(Xte)
        clf = LogisticRegression(max_iter=2000, class_weight="balanced", C=1.0)
        clf.fit(Xtr, ytr)
        proba = clf.predict_proba(Xte)[:, 1]
        return float(roc_auc_score(yte, proba)), int(len(te)), dict(zip(feats, clf.coef_[0].tolist()))

    train = base[base["eval_split"] == "train"]
    specs = {
        "length_only": ["tumor_length_cm"],
        "serosa+length": ["wall_serosa_interrupt", "tumor_length_cm"],
        "whole_depth+length": ["wall_depth_frac_p90", "tumor_length_cm"],
        "v2_remain_med+length": ["wall_v2_remain_px__median", "tumor_length_cm"],
        "v2_remain_max+length": ["wall_v2_remain_px__max", "tumor_length_cm"],
        "v2_remain_p10+length": ["wall_v2_remain_px__p90", "tumor_length_cm"],
        "fuse_med+length": ["fuse_serosa_remain__median", "tumor_length_cm"],
        "fuse_max+length": ["fuse_serosa_remain__max", "tumor_length_cm"],
        "fuse3_max+length": ["fuse3__max", "tumor_length_cm"],
        "serosa+remain_max+length": [
            "wall_serosa_interrupt",
            "wall_v2_remain_px__max",
            "tumor_length_cm",
        ],
        "serosa+composite_max+length": [
            "wall_serosa_interrupt",
            "wall_v2_composite__max",
            "tumor_length_cm",
        ],
        "kitchen_max+length": [
            "wall_serosa_interrupt",
            "wall_v2_remain_px__max",
            "wall_v2_composite__max",
            "wall_depth_frac_p90",
            "tumor_length_cm",
        ],
    }

    model_rows = []
    coefs_train: dict = {}
    for name, feats in specs.items():
        out_tr = fit_auc(train, train, feats)
        if out_tr:
            model_rows.append({"model": name, "split": "train", "auc": out_tr[0], "n": out_tr[1]})
            coefs_train[name] = out_tr[2]
        for split in ["val", "test_prospective", "test_external"]:
            te = base[base["eval_split"] == split]
            out = fit_auc(train, te, feats)
            if out is None:
                continue
            model_rows.append({"model": name, "split": split, "auc": out[0], "n": out[1]})
    models = pd.DataFrame(model_rows)
    models.to_csv(OUT / "split_models_T3plus.csv", index=False)
    piv = models.pivot(index="model", columns="split", values="auc")
    held = [c for c in ["val", "test_prospective", "test_external"] if c in piv.columns]
    piv["mean_heldout"] = piv[held].mean(axis=1)
    piv = piv.sort_values("mean_heldout", ascending=False)
    piv.to_csv(OUT / "split_models_T3plus_pivot.csv")
    (OUT / "train_coefs.json").write_text(json.dumps(coefs_train, indent=2), encoding="utf-8")

    # plots
    fig, ax = plt.subplots(figsize=(5.4, 3.2), dpi=200)
    show = uni[
        uni.feature.str.contains(
            "remain_px|pen_ratio__|composite__|fuse_serosa|serosa_interrupt|depth_frac|length"
        )
    ].copy()
    show = show.sort_values("rho")
    colors = []
    for f in show.feature:
        if "fuse" in f:
            colors.append("#C86B6B")
        elif "v2" in f:
            colors.append("#E09F3E")
        elif "length" in f:
            colors.append("#888888")
        else:
            colors.append("#6B9AC4")
    ax.barh(show.feature, show.rho, color=colors, height=0.7)
    ax.axvline(0, color="#333", lw=0.5)
    ax.set_xlabel("Spearman ρ vs pathologic T")
    ax.set_title("Deepest-frame agg (orange) · fuse (red) · whole/serosa (blue)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "00_agg_rho.png", bbox_inches="tight")
    fig.savefig(SHARE / "50_wall_deepest_agg_rho.png", bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.8, 3.4), dpi=200)
    order = piv.index.tolist()
    x = np.arange(len(order))
    width = 0.22
    for i, sp in enumerate(["val", "test_prospective", "test_external"]):
        if sp not in piv.columns:
            continue
        ax.bar(x + (i - 1) * width, piv[sp].values, width=width, label=sp)
    ax.axhline(0.5, color="#aaa", lw=0.5, ls="--")
    ax.set_xticks(x)
    ax.set_xticklabels(order, rotation=32, ha="right")
    ax.set_ylabel("AUC T3+")
    ax.set_ylim(0.45, 1.0)
    ax.legend(frameon=False, fontsize=5, loc="lower right")
    ax.set_title("Train→held-out wall models (with length)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "00_split_auc.png", bbox_inches="tight")
    fig.savefig(SHARE / "50_wall_deepest_split_auc.png", bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(5.2, 2.4), dpi=200)
    colors_s = {0: "#6B9AC4", 1: "#7EB77F", 2: "#E09F3E", 3: "#C86B6B"}
    for ax, feat, title in zip(
        axes,
        ["wall_v2_remain_px__median", "wall_v2_remain_px__max"],
        ["Remain median", "Remain deepest (min frames)"],
    ):
        for k in range(4):
            vals = base.loc[base["label"] == k, feat].dropna().to_numpy()
            parts = ax.violinplot([vals], positions=[k], widths=0.75, showextrema=False, showmedians=True)
            for b in parts["bodies"]:
                b.set_facecolor(colors_s[k])
                b.set_alpha(0.75)
            parts["cmedians"].set_color("#222")
        ax.set_xticks(range(4))
        ax.set_xticklabels(["T1", "T2", "T3", "T4+"])
        ax.set_title(title)
        ax.set_ylabel("remain px ↓ deeper")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    fig.suptitle(f"Deepest-frame remain vs stage (n={len(base)})", y=1.02)
    fig.tight_layout()
    fig.savefig(OUT / "00_remain_median_vs_max.png", bbox_inches="tight")
    fig.savefig(SHARE / "50_wall_remain_median_vs_max.png", bbox_inches="tight")
    plt.close(fig)

    def get_rho(feat: str) -> float:
        s = uni[uni.feature == feat]
        return float(s.rho.iloc[0]) if len(s) else float("nan")

    md = [
        "# Wall-layer deepest-frame aggregation + split models",
        "",
        "## Thinking",
        "",
        "Clinical T is decided by the **deepest** invasion site. Patient **median** remain/pen dilutes that frame.",
        "Test: aggregate with **min remain / max pen / P10 remain**, fuse with serosa, fit train logistic → held-out AUC under length control.",
        "",
        "## Univariate top",
        "",
        "| feature | ρ | residρ‖len | AUC T3+ | medians T1→T4 |",
        "|---|---:|---:|---:|---|",
    ]
    for _, r in uni.head(14).iterrows():
        md.append(
            f"| `{r.feature}` | {r.rho:+.3f} | {r.resid_rho:+.3f} | {r.auc_T3:.3f} | "
            f"{r.med_T1:.3g}/{r.med_T2:.3g}/{r.med_T3:.3g}/{r.med_T4:.3g} |"
        )
    md += [
        "",
        "## Held-out AUC T3+ (train→*)",
        "",
        piv.round(3).to_markdown(),
        "",
        f"**Best mean held-out:** `{piv.index[0]}`",
        "",
        "## Key deltas",
        "",
        f"- Remain median ρ={get_rho('wall_v2_remain_px__median'):+.3f} → deepest ρ={get_rho('wall_v2_remain_px__max'):+.3f}",
        f"- Fuse median ρ={get_rho('fuse_serosa_remain__median'):+.3f} → fuse deepest ρ={get_rho('fuse_serosa_remain__max'):+.3f}",
    ]
    if "length_only" in piv.index:
        md.append(f"- Length-only mean held-out={piv.loc['length_only', 'mean_heldout']:.3f}")
    md += ["", "## Verdict", ""]
    if "test_external" in piv.columns:
        ext_len = float(piv.loc["length_only", "test_external"]) if "length_only" in piv.index else float("nan")
        best_ext_name = piv["test_external"].idxmax()
        md.append(
            f"- External: length-only AUC={ext_len:.3f}; best=`{best_ext_name}` AUC={float(piv['test_external'].max()):.3f}."
        )
    if "test_prospective" in piv.columns:
        pr_len = float(piv.loc["length_only", "test_prospective"]) if "length_only" in piv.index else float("nan")
        pr_name = piv["test_prospective"].idxmax()
        md.append(
            f"- Prospective: length-only AUC={pr_len:.3f}; best=`{pr_name}` AUC={float(piv['test_prospective'].max()):.3f}."
        )
    md += [
        "",
        "## Practical",
        "",
        "- Staging feature: **`wall_v2_remain_px__max`** (min over frames) + `wall_serosa_interrupt` + length.",
        "- Soft layer display can stay median; scorecard should use deepest.",
        "",
        "```bash",
        "python3 scripts/eval_gc_us_wall_layer_deepest_agg_v1.py",
        "```",
        "",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    keep = [
        c
        for c in base.columns
        if c.endswith(("__max", "__p90", "__median"))
        or c.startswith("fuse")
        or c
        in [
            "patient_id",
            "label",
            "tumor_length_cm",
            "eval_split",
            "wall_serosa_interrupt",
            "wall_depth_frac_p90",
        ]
    ]
    base[keep].to_csv(OUT / "patient_wall_deepest.csv", index=False)

    print(uni.head(16).to_string(index=False))
    print()
    print(piv.round(3).to_string())
    print("n_by_split", base["eval_split"].value_counts().to_dict())


if __name__ == "__main__":
    main()
