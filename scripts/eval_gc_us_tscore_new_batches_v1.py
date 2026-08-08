#!/usr/bin/env python3
"""Evaluate clinical + dynamics (+ report) batches vs pathologic T.

Outputs:
  pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/new_batches_v1/
  results/visualizations/tstage/imaging_truth_share_white_20260729/51_*
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
FEAT = ROOT / "pipeline/data/gc_us_tscore_features_v1"
PT = (
    ROOT
    / "pipeline/experiments/reports/imaging_truth_tstage_corr_v2"
    / "patient_table_unique_pooled.csv"
)
OUT = ROOT / "pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/new_batches_v1"
SHARE = ROOT / "results/visualizations/tstage/imaging_truth_share_white_20260729"

CANDIDATES = [
    # clinical / size / markers
    "tumor_length_cm",
    "tumor_thickness_cm",
    "size_thickness_length_ratio",
    "size_max_diameter_cm",
    "cea_value",
    "cea_binary",
    "ca199_value",
    "ca199_binary",
    "seg_short_axis_ratio",
    # report (sparse)
    "report_adjacent_invasion",
    "report_possible_t3_t4",
    "report_wall_irregularity",
    "serosa_suspect",
    "adjacent_invasion",
    "layer_unclear",
    "report_advanced_evidence_score",
    # dynamics
    "dyn_invasion_agree",
    "dyn_n_frames",
    "morph_peak_sharpness_max__frac_high",
    "morph_peak_sharpness_max__std",
    "morph_solidity__frac_low",
    "margin_spic_robust__frac_high",
    "margin_spic_robust__std",
    "bt_v2_max_outward_depth__frac_high",
    "bt_v2_max_outward_depth__max",
    "growth_outward_protrusion_ratio__frac_high",
    "wall_depth_frac_p90__frac_high",
    "wall_serosa_interrupt__frac_high",
    "wall_v2_remain_px__frac_low",
    "wall_v2_remain_px__med",
    # baselines already known
    "wall_serosa_interrupt",
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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    SHARE.mkdir(parents=True, exist_ok=True)
    apply_nature()

    pt = pd.read_csv(PT)
    pt["patient_id"] = pt["patient_id"].astype(str)
    pt["label"] = pt["label"].clip(0, 3)
    pt["eval_split"] = pt["source_splits"].map(eval_split)

    clin = pd.read_csv(FEAT / "clinical/patient_features.csv")
    dyn = pd.read_csv(FEAT / "dynamics/patient_features.csv")
    wall = pd.read_csv(FEAT / "wall_layer/patient_features_median.csv")
    for d in (clin, dyn, wall):
        d["patient_id"] = d["patient_id"].astype(str)

    # avoid duplicate clinical cols from pt
    clin_extra = [c for c in clin.columns if c not in ("patient_id", "label") and c not in pt.columns]
    # wall serosa baseline
    base = pt[["patient_id", "label", "eval_split"]].copy()
    # clinical file is SSOT for size/markers/report (avoids duplicate column names)
    clin_keep = [
        c
        for c in clin.columns
        if c != "label"
        and (
            c
            in {
                "patient_id",
                "tumor_length_cm",
                "tumor_thickness_cm",
                "cea_value",
                "cea_binary",
                "ca199_value",
                "ca199_binary",
                "size_thickness_length_ratio",
                "size_max_diameter_cm",
                "seg_short_axis_ratio",
                "serosa_suspect",
                "adjacent_invasion",
                "layer_unclear",
                "report_advanced_evidence_score",
                "deep_report_available",
            }
            or c.startswith("report_")
        )
    ]
    base = base.merge(clin[clin_keep], on="patient_id", how="left")
    rep_cols = [c for c in clin_keep if c.startswith("report_") or c in ("serosa_suspect", "adjacent_invasion", "layer_unclear")]
    dyn_cols = [c for c in dyn.columns if c != "patient_id"]
    base = base.merge(dyn[["patient_id"] + dyn_cols], on="patient_id", how="left")
    if "wall_serosa_interrupt" in wall.columns:
        base = base.merge(wall[["patient_id", "wall_serosa_interrupt"]], on="patient_id", how="left")
    base = base.loc[:, ~base.columns.duplicated()]

    def col1(df: pd.DataFrame, name: str) -> pd.Series:
        s = df[name]
        return s.iloc[:, 0] if isinstance(s, pd.DataFrame) else s

    rows = []
    for feat in CANDIDATES:
        if feat not in base.columns:
            continue
        cols = ["label", feat] if feat == "tumor_length_cm" else ["label", feat, "tumor_length_cm"]
        sub = base.loc[:, ~base.columns.duplicated()][cols].copy()
        # if still duplicated names from fancy index, collapse
        sub = sub.loc[:, ~sub.columns.duplicated()]
        sub = sub.dropna()
        if len(sub) < 40:
            continue
        lab = col1(sub, "label").to_numpy(dtype=float).ravel()
        y = col1(sub, feat).to_numpy(dtype=float).ravel()
        if lab.shape[0] != y.shape[0]:
            continue
        rho_p = stats.spearmanr(lab, y)
        rho = float(np.asarray(rho_p.statistic).ravel()[0])
        p = float(np.asarray(rho_p.pvalue).ravel()[0])
        try:
            auc = float(roc_auc_score((lab >= 2).astype(int), y))
        except Exception:
            auc = float("nan")
        if feat == "tumor_length_cm":
            rrho = float(rho)
        else:
            length = col1(sub, "tumor_length_cm").to_numpy(dtype=float).ravel()
            A = np.vstack([np.ones(len(length)), length]).T
            resid = y - A @ np.linalg.lstsq(A, y, rcond=None)[0]
            rrho = float(np.asarray(stats.spearmanr(lab, resid).statistic).ravel()[0])
        feat_s = col1(sub, feat)
        meds = [float(feat_s[lab == k].median()) for k in range(4)]
        rows.append(
            {
                "feature": feat,
                "n": int(len(sub)),
                "coverage": float(len(sub) / len(base)),
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
    uni = pd.DataFrame(rows).sort_values("rho", key=lambda s: s.abs(), ascending=False)
    uni.to_csv(OUT / "univariate.csv", index=False)

    # split models
    def fit(train, test, feats):
        need = list(dict.fromkeys(feats + ["label"]))
        tr = train.dropna(subset=need)
        te = test.dropna(subset=need)
        if len(tr) < 80 or len(te) < 25:
            return None
        ytr = (tr.label >= 2).astype(int).to_numpy()
        yte = (te.label >= 2).astype(int).to_numpy()
        if len(np.unique(ytr)) < 2 or len(np.unique(yte)) < 2:
            return None
        Xtr = tr[feats].astype(float).to_numpy()
        Xte = te[feats].astype(float).to_numpy()
        sc = StandardScaler()
        Xtr = sc.fit_transform(Xtr)
        Xte = sc.transform(Xte)
        clf = LogisticRegression(max_iter=2000, class_weight="balanced")
        clf.fit(Xtr, ytr)
        return float(roc_auc_score(yte, clf.predict_proba(Xte)[:, 1])), len(te)

    # Fair compare with prior wall/morph packs: require imaging dynamics present
    imaged = base[base["dyn_invasion_agree"].notna()].copy() if "dyn_invasion_agree" in base.columns else base
    train = imaged[imaged.eval_split == "train"]
    specs = {
        "length": ["tumor_length_cm"],
        "length+thick": ["tumor_length_cm", "tumor_thickness_cm"],
        "size_max": ["size_max_diameter_cm"],
        "length+cea": ["tumor_length_cm", "cea_binary"],
        "length+thick+cea": ["tumor_length_cm", "tumor_thickness_cm", "cea_binary"],
        "length+short_axis": ["tumor_length_cm", "seg_short_axis_ratio"],
        "length+dyn_agree": ["tumor_length_cm", "dyn_invasion_agree"],
        "length+serosa": ["tumor_length_cm", "wall_serosa_interrupt"],
        "length+serosa+dyn": ["tumor_length_cm", "wall_serosa_interrupt", "dyn_invasion_agree"],
        "length+thick+serosa+cea": [
            "tumor_length_cm",
            "tumor_thickness_cm",
            "wall_serosa_interrupt",
            "cea_binary",
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
    }
    # drop specs with missing cols
    specs = {k: [f for f in v if f in base.columns] for k, v in specs.items()}
    specs = {k: v for k, v in specs.items() if v}

    mrows = []
    for name, feats in specs.items():
        for sp in ["train", "val", "test_prospective", "test_external"]:
            te = imaged[imaged.eval_split == sp] if sp != "train" else train
            out = fit(train, te, feats)
            if out is None:
                continue
            mrows.append({"model": name, "split": sp, "auc": out[0], "n": out[1], "feats": ",".join(feats)})
    models = pd.DataFrame(mrows)
    models.to_csv(OUT / "split_models.csv", index=False)
    piv = models.pivot(index="model", columns="split", values="auc")
    held = [c for c in ["val", "test_prospective", "test_external"] if c in piv.columns]
    piv["mean_heldout"] = piv[held].mean(axis=1)
    piv = piv.sort_values("mean_heldout", ascending=False)
    piv.to_csv(OUT / "split_models_pivot.csv")

    # plots
    fig, ax = plt.subplots(figsize=(5.6, 3.6), dpi=200)
    show = uni.head(22).sort_values("rho")
    cols = []
    for f in show.feature:
        if f.startswith(("tumor_", "size_", "cea", "ca199", "seg_")):
            cols.append("#6B9AC4")
        elif f.startswith("report_") or f in ("serosa_suspect", "adjacent_invasion", "layer_unclear"):
            cols.append("#7EB77F")
        elif "dyn_" in f or "__frac" in f or "__std" in f or "__max" in f or "__med" in f:
            cols.append("#E09F3E")
        else:
            cols.append("#C86B6B")
    ax.barh(show.feature, show.rho, color=cols, height=0.7)
    ax.axvline(0, color="#333", lw=0.5)
    ax.set_xlabel("Spearman ρ vs pathologic T")
    ax.set_title("New batches: clinical (blue) · report (green) · dynamics (orange)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "00_new_batches_rho.png", bbox_inches="tight")
    fig.savefig(SHARE / "51_tscore_new_batches_rho.png", bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.8, 3.2), dpi=200)
    order = piv.index.tolist()
    x = np.arange(len(order))
    width = 0.22
    for i, sp in enumerate(["val", "test_prospective", "test_external"]):
        if sp not in piv.columns:
            continue
        ax.bar(x + (i - 1) * width, piv[sp].values, width=width, label=sp)
    ax.set_xticks(x)
    ax.set_xticklabels(order, rotation=28, ha="right")
    ax.set_ylabel("AUC T3+")
    ax.set_ylim(0.5, 1.0)
    ax.legend(frameon=False, fontsize=5)
    ax.set_title("Train→held-out: clinical + dynamics packs")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "00_new_batches_split_auc.png", bbox_inches="tight")
    fig.savefig(SHARE / "51_tscore_new_batches_split_auc.png", bbox_inches="tight")
    plt.close(fig)

    md = [
        "# T-score new feature batches (clinical + dynamics + report)",
        "",
        "## Batches",
        "",
        "1. **Clinical**: thickness, CEA/CA199, seg_short_axis, size ratios",
        "2. **Dynamics**: multi-frame frac_high / std / dyn_invasion_agree",
        "3. **Report NLP**: preop flags via clinical master (sparse coverage)",
        "",
        "## Univariate (top |ρ|)",
        "",
        "| feature | n | cov | ρ | residρ‖len | AUC T3+ |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for _, r in uni.head(18).iterrows():
        md.append(
            f"| `{r.feature}` | {int(r.n)} | {r.coverage:.0%} | {r.rho:+.3f} | {r.resid_rho:+.3f} | {r.auc_T3:.3f} |"
        )
    md += [
        "",
        "## Held-out AUC T3+",
        "",
        piv.round(3).to_markdown(),
        "",
        f"**Best mean held-out:** `{piv.index[0]}`",
        "",
        "## Rebuild",
        "",
        "```bash",
        "python3 scripts/extract_gc_us_clinical_cohort_features_v1.py",
        "python3 scripts/extract_gc_us_multiframe_dynamics_v1.py",
        "python3 scripts/eval_gc_us_tscore_new_batches_v1.py",
        "python3 scripts/build_gc_us_tscore_feature_pack_v1.py",
        "```",
        "",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(uni.head(20).to_string(index=False))
    print()
    print(piv.round(3).to_string())
    print(json.dumps({"n": len(base), "n_report": int(base[rep_cols[0]].notna().sum()) if rep_cols else 0}, indent=2))


if __name__ == "__main__":
    main()
