#!/usr/bin/env python3
"""LASSO + SHAP importance for GC-US T-score features, then top 3D triplets.

- Fit on train only (patient-level, T3+ vs T1-T2 and multinomial ordinal proxy).
- Rank features by |LASSO coef|, mean |SHAP|, and univariate Spearman.
- Render Nature-style 3D scatters for the most informative non-redundant triplets.

Outputs:
  pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/lasso_shap_triplets_v1/
  results/visualizations/tstage/imaging_truth_share_white_20260729/46_*.png
"""

from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from scipy import stats
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegressionCV
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PT = (
    PROJECT_ROOT
    / "pipeline/experiments/reports/imaging_truth_tstage_corr_v2"
    / "patient_table_unique_pooled.csv"
)
PACK = PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1/feature_pack_v1/patient_features.csv"
MORPH = PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1/morphology/patient_features_median.csv"
GROWTH = PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1/growth/patient_features_median.csv"
OUT = (
    PROJECT_ROOT
    / "pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/lasso_shap_triplets_v1"
)
SHARE = PROJECT_ROOT / "results/visualizations/tstage/imaging_truth_share_white_20260729"

STAGE = ["T1", "T2", "T3", "T4+"]
COLORS = {0: "#6B9AC4", 1: "#7EB77F", 2: "#E09F3E", 3: "#C86B6B"}

# Candidate pool (clinical size kept; image-size px treated as size proxy)
CANDIDATES = [
    "tumor_length_cm",
    "tumor_thickness_cm",
    "cea_value",
    "ca199_value",
    "seg_irregularity",
    "seg_short_axis_ratio",
    "seg_long_axis_ratio",
    "seg_area_ratio",
    "seg_boundary_clarity",
    "seg_lumen_inside_ratio",
    "breakthrough_max_depth",
    "breakthrough_area_ratio",
    "breakthrough_outward_score",
    "morph_peak_sharpness_max",
    "morph_solidity",
    "morph_circularity",
    "morph_concavity_ratio",
    "morph_nrl_roughness",
    "morph_fd_high_energy",
    "morph_irregularity_index",
    "morph_perimeter_px",
    "morph_area_px",
    "margin_spic_robust",
    "margin_shape_fd_high",
    "margin_bof_high_mean",
    "margin_clear_robust",
    "bt_v2_max_outward_depth",
    "growth_outward_protrusion_ratio__max",
]

SIZE_LIKE = {
    "tumor_length_cm",
    "tumor_thickness_cm",
    "morph_perimeter_px",
    "morph_area_px",
    "seg_area_ratio",
    "anatomic_lesion_area_px",
}

SHORT_LABEL = {
    "tumor_length_cm": "Length (cm)",
    "tumor_thickness_cm": "Thickness (cm)",
    "cea_value": "CEA",
    "ca199_value": "CA19-9",
    "seg_irregularity": "Seg irregularity",
    "seg_short_axis_ratio": "Short-axis ratio",
    "seg_long_axis_ratio": "Long-axis ratio",
    "seg_area_ratio": "Seg area ratio",
    "seg_boundary_clarity": "Boundary clarity",
    "seg_lumen_inside_ratio": "Lumen-inside",
    "breakthrough_max_depth": "BT max depth",
    "breakthrough_area_ratio": "BT area ratio",
    "breakthrough_outward_score": "BT outward",
    "morph_peak_sharpness_max": "Peak sharpness",
    "morph_solidity": "Solidity",
    "morph_circularity": "Circularity",
    "morph_concavity_ratio": "Concavity",
    "morph_nrl_roughness": "NRL roughness",
    "morph_fd_high_energy": "FD high",
    "morph_irregularity_index": "Morph irreg.",
    "morph_perimeter_px": "Perimeter (px)",
    "morph_area_px": "Area (px)",
    "margin_spic_robust": "Spic. index",
    "margin_shape_fd_high": "Margin FD high",
    "margin_bof_high_mean": "BoF high",
    "margin_clear_robust": "Clear margin",
    "bt_v2_max_outward_depth": "BT v2 depth",
    "growth_outward_protrusion_ratio__max": "Protrusion max",
}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    ap.add_argument("--n-triplets", type=int, default=8)
    return ap.parse_args()


def eval_split(source_splits: object) -> str:
    parts = set(str(source_splits).replace(" ", "").split(","))
    if "external" in parts:
        return "test_external"
    if "prospective" in parts and "train" not in parts and "val" not in parts:
        return "test_prospective"
    if "val" in parts:
        return "val"
    if "train" in parts or "prospective" in parts:
        return "train"
    return "other"


def apply_nature() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "pdf.fonttype": 42,
            "svg.fonttype": "none",
            "font.size": 6,
            "axes.facecolor": "white",
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
            "axes.unicode_minus": False,
        }
    )


def load_joined() -> pd.DataFrame:
    pt = pd.read_csv(PT)
    pack = pd.read_csv(PACK)
    morph = pd.read_csv(MORPH)
    growth = pd.read_csv(GROWTH)
    for d in (pt, pack, morph, growth):
        d["patient_id"] = d["patient_id"].astype(str)

    keep_pt = [
        "patient_id",
        "label",
        "source_splits",
        "tumor_length_cm",
        "tumor_thickness_cm",
        "cea_value",
        "ca199_value",
        "seg_irregularity",
        "seg_short_axis_ratio",
        "seg_long_axis_ratio",
        "seg_area_ratio",
        "seg_boundary_clarity",
        "seg_lumen_inside_ratio",
        "breakthrough_max_depth",
        "breakthrough_area_ratio",
        "breakthrough_outward_score",
    ]
    df = pt[keep_pt].copy()
    # morph extras
    morph_cols = [
        c
        for c in (
            "morph_peak_sharpness_max",
            "morph_solidity",
            "morph_circularity",
            "morph_concavity_ratio",
            "morph_nrl_roughness",
            "morph_fd_high_energy",
            "morph_irregularity_index",
            "morph_perimeter_px",
            "morph_area_px",
        )
        if c in morph.columns
    ]
    margin_cols = [
        c
        for c in (
            "margin_spic_robust",
            "margin_shape_fd_high",
            "margin_bof_high_mean",
            "margin_clear_robust",
        )
        if c in pack.columns
    ]
    growth_cols = [
        c
        for c in ("bt_v2_max_outward_depth", "growth_outward_protrusion_ratio__max")
        if c in growth.columns or c in pack.columns
    ]
    df = df.merge(morph[["patient_id"] + morph_cols], on="patient_id", how="left")
    df = df.merge(pack[["patient_id"] + margin_cols], on="patient_id", how="left")
    gsrc = growth if set(growth_cols) <= set(growth.columns) else pack
    df = df.merge(gsrc[["patient_id"] + [c for c in growth_cols if c in gsrc.columns]], on="patient_id", how="left")
    df["label"] = pd.to_numeric(df["label"], errors="coerce")
    df["eval_split"] = df["source_splits"].map(eval_split)
    for c in CANDIDATES:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def univariate_table(df: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    rows = []
    y = df["label"].to_numpy(float)
    yb = (y >= 2).astype(int)
    for f in feats:
        x = df[f].to_numpy(float)
        m = np.isfinite(x) & np.isfinite(y)
        if m.sum() < 30 or np.unique(x[m]).size < 2:
            continue
        rho, p = stats.spearmanr(x[m], y[m])
        try:
            auc = float(roc_auc_score(yb[m], x[m] if rho >= 0 else -x[m]))
        except ValueError:
            auc = float("nan")
        groups = [x[m & (y == k)] for k in range(4) if np.any(m & (y == k))]
        try:
            kw_p = float(stats.kruskal(*groups).pvalue) if len(groups) >= 2 else float("nan")
        except ValueError:
            kw_p = float("nan")
        rows.append(
            {
                "feature": f,
                "n": int(m.sum()),
                "spearman_rho": float(rho),
                "spearman_p": float(p),
                "auc_T3plus_oriented": auc,
                "kruskal_p": kw_p,
                "size_like": int(f in SIZE_LIKE),
            }
        )
    return pd.DataFrame(rows).sort_values("spearman_rho", key=lambda s: s.abs(), ascending=False)


def fit_lasso_shap(train: pd.DataFrame, feats: list[str]) -> tuple[pd.DataFrame, Pipeline]:
    X = train[feats]
    y = (train["label"] >= 2).astype(int).to_numpy()
    pipe = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "clf",
                LogisticRegressionCV(
                    Cs=np.logspace(-3, 2, 20),
                    cv=5,
                    penalty="l1",
                    solver="saga",
                    class_weight="balanced",
                    max_iter=5000,
                    scoring="roc_auc",
                    n_jobs=-1,
                    random_state=0,
                ),
            ),
        ]
    )
    pipe.fit(X, y)
    clf = pipe.named_steps["clf"]
    coef = clf.coef_.ravel()
    # SHAP linear explainer on scaled space
    Xs = pipe.named_steps["scaler"].transform(pipe.named_steps["imputer"].transform(X))
    explainer = shap.LinearExplainer(clf, Xs, feature_perturbation="interventional")
    sv = explainer.shap_values(Xs)
    if isinstance(sv, list):
        sv = sv[1]
    mean_abs = np.mean(np.abs(sv), axis=0)
    out = pd.DataFrame(
        {
            "feature": feats,
            "lasso_coef": coef,
            "lasso_abs_coef": np.abs(coef),
            "shap_mean_abs": mean_abs,
            "selected": (np.abs(coef) > 1e-8).astype(int),
            "best_C": float(clf.C_[0]) if np.ndim(clf.C_) else float(clf.C_),
        }
    ).sort_values("shap_mean_abs", ascending=False)
    return out, pipe


def eval_pipe(pipe: Pipeline, df: pd.DataFrame, feats: list[str]) -> dict[str, float]:
    scores = {}
    for sp in ["train", "val", "test_prospective", "test_external"]:
        sub = df[df["eval_split"] == sp]
        if len(sub) < 15:
            continue
        y = (sub["label"] >= 2).astype(int).to_numpy()
        if len(np.unique(y)) < 2:
            scores[sp] = float("nan")
            continue
        p = pipe.predict_proba(sub[feats])[:, 1]
        scores[sp] = float(roc_auc_score(y, p))
    return scores


def triplet_score(df: pd.DataFrame, feats: tuple[str, str, str], importance: pd.DataFrame) -> dict:
    """Combined importance + multivariate AUC (train) + redundancy penalty."""
    sub = df[df["eval_split"] == "train"][list(feats) + ["label"]].dropna()
    if len(sub) < 80:
        return {"ok": False}
    y = (sub["label"] >= 2).astype(int).to_numpy()
    pipe = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "clf",
                LogisticRegressionCV(
                    Cs=np.logspace(-2, 2, 12),
                    cv=3,
                    penalty="l2",
                    solver="lbfgs",
                    class_weight="balanced",
                    max_iter=2000,
                    scoring="roc_auc",
                    random_state=0,
                ),
            ),
        ]
    )
    pipe.fit(sub[list(feats)], y)
    auc_tr = float(roc_auc_score(y, pipe.predict_proba(sub[list(feats)])[:, 1]))
    # held-out mean AUC
    aucs = []
    for sp in ["val", "test_prospective", "test_external"]:
        te = df[df["eval_split"] == sp][list(feats) + ["label"]].dropna()
        if len(te) < 20 or te["label"].nunique() < 2:
            continue
        yte = (te["label"] >= 2).astype(int).to_numpy()
        if len(np.unique(yte)) < 2:
            continue
        aucs.append(float(roc_auc_score(yte, pipe.predict_proba(te[list(feats)])[:, 1])))
    auc_ho = float(np.mean(aucs)) if aucs else float("nan")
    imp = importance.set_index("feature")
    shap_sum = float(imp.loc[list(feats), "shap_mean_abs"].sum())
    n_size = sum(f in SIZE_LIKE for f in feats)
    # pairwise |corr| redundancy
    corr = sub[list(feats)].corr(method="spearman").abs()
    red = float((corr.values[np.triu_indices(3, 1)]).mean())
    score = shap_sum * 0.35 + auc_tr * 0.25 + (0 if np.isnan(auc_ho) else auc_ho) * 0.35 - 0.15 * red - 0.08 * n_size
    return {
        "ok": True,
        "f1": feats[0],
        "f2": feats[1],
        "f3": feats[2],
        "shap_sum": shap_sum,
        "auc_train": auc_tr,
        "auc_heldout_mean": auc_ho,
        "mean_abs_spearman": red,
        "n_size_like": n_size,
        "score": float(score),
        "n_train": int(len(sub)),
    }


def plot_triplet(df: pd.DataFrame, feats: tuple[str, str, str], title: str, stem: Path) -> int:
    cols = list(feats) + ["label"]
    sub = df[cols].dropna().copy()
    sub["label"] = sub["label"].astype(int)
    if len(sub) < 50:
        return 0
    apply_nature()
    fig = plt.figure(figsize=(5.2, 4.0), dpi=300)
    ax = fig.add_axes([0.02, 0.18, 0.72, 0.76], projection="3d")
    lab = sub["label"].to_numpy()
    xx, yy, zz = [sub[f].to_numpy(float) for f in feats]
    handles = []
    for k in range(4):
        m = lab == k
        h = ax.scatter(
            xx[m],
            yy[m],
            zz[m],
            s=4,
            alpha=0.22,
            c=COLORS[k],
            edgecolors="none",
            depthshade=False,
            label=f"{STAGE[k]} (n={int(m.sum())})",
        )
        handles.append(h)
    med = np.array([[np.median(sub.loc[lab == k, f]) for f in feats] for k in range(4)])
    ax.plot(med[:, 0], med[:, 1], med[:, 2], color="#222222", lw=1.0, zorder=4)
    for k in range(4):
        ax.scatter(
            [med[k, 0]],
            [med[k, 1]],
            [med[k, 2]],
            s=42,
            c=COLORS[k],
            edgecolors="white",
            linewidths=0.9,
            marker="D",
            depthshade=False,
            zorder=6,
        )
    ax.view_init(elev=18, azim=125)
    for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
        pane.fill = False
        pane.set_edgecolor("#CCCCCC")
    ax.grid(True, lw=0.25, alpha=0.45)
    ax.tick_params(labelsize=5.5, pad=2, length=1.5, width=0.35)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_zlabel("")
    ax.set_title(f"{title}  N={len(sub)}", fontsize=7, pad=2)

    leg_ax = fig.add_axes([0.76, 0.35, 0.22, 0.40])
    leg_ax.axis("off")
    leg_ax.legend(handles, [h.get_label() for h in handles], loc="center left", fontsize=6, frameon=False, markerscale=2.2)

    key = fig.add_axes([0.06, 0.02, 0.88, 0.12])
    key.axis("off")
    key.text(0.0, 0.72, "Axes", fontsize=6, fontweight="bold", transform=key.transAxes, va="center")
    key.text(
        0.0,
        0.28,
        f"X  {SHORT_LABEL.get(feats[0], feats[0])}      "
        f"Y  {SHORT_LABEL.get(feats[1], feats[1])}      "
        f"Z  {SHORT_LABEL.get(feats[2], feats[2])}",
        fontsize=6.5,
        transform=key.transAxes,
        va="center",
    )
    stem.parent.mkdir(parents=True, exist_ok=True)
    for ext, dpi in (("png", 600), ("pdf", None)):
        kw = {"facecolor": "white", "pad_inches": 0.04}
        if dpi:
            kw["dpi"] = dpi
        fig.savefig(stem.with_suffix(f".{ext}"), **kw)
    plt.close(fig)
    return int(len(sub))


def main() -> None:
    args = parse_args()
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    SHARE.mkdir(parents=True, exist_ok=True)
    apply_nature()

    df = load_joined()
    df = df[df["eval_split"].isin(["train", "val", "test_prospective", "test_external"])].copy()
    feats = [f for f in CANDIDATES if f in df.columns]
    # require >=60% coverage on train
    train = df[df["eval_split"] == "train"]
    cov = {f: float(train[f].notna().mean()) for f in feats}
    feats = [f for f in feats if cov[f] >= 0.6]
    print(json.dumps({"n_features": len(feats), "coverage_min": 0.6}, indent=2))

    uni = univariate_table(df, feats)
    uni.to_csv(out / "univariate_significance.csv", index=False)

    imp, pipe = fit_lasso_shap(train, feats)
    imp = imp.merge(uni, on="feature", how="left")
    # composite rank
    imp["rank_shap"] = imp["shap_mean_abs"].rank(ascending=False)
    imp["rank_lasso"] = imp["lasso_abs_coef"].rank(ascending=False)
    imp["rank_rho"] = imp["spearman_rho"].abs().rank(ascending=False)
    imp["rank_mean"] = imp[["rank_shap", "rank_lasso", "rank_rho"]].mean(axis=1)
    imp = imp.sort_values("rank_mean")
    imp.to_csv(out / "feature_importance_lasso_shap.csv", index=False)

    aucs = eval_pipe(pipe, df, feats)
    (out / "lasso_auc_by_split.json").write_text(json.dumps(aucs, indent=2), encoding="utf-8")

    # SHAP summary bar
    top = imp.head(15)
    fig, ax = plt.subplots(figsize=(3.6, 3.8))
    ax.barh(top["feature"][::-1], top["shap_mean_abs"][::-1], color="#4C78A8", height=0.7)
    ax.set_xlabel("mean |SHAP| (train, T3+ LASSO)", fontsize=6)
    ax.set_title("Feature importance", fontsize=7)
    ax.tick_params(labelsize=5.5)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "00_shap_mean_abs_top15.png", dpi=300, facecolor="white")
    fig.savefig(SHARE / "46_feature_importance_shap_lasso_top15.png", dpi=300, facecolor="white")
    plt.close(fig)

    # LASSO coef signed
    sel = imp[imp["selected"] == 1].sort_values("lasso_coef")
    fig, ax = plt.subplots(figsize=(3.6, max(2.2, 0.22 * len(sel) + 0.8)))
    colors = ["#C86B6B" if v > 0 else "#6B9AC4" for v in sel["lasso_coef"]]
    ax.barh(sel["feature"], sel["lasso_coef"], color=colors, height=0.7)
    ax.axvline(0, color="#444", lw=0.6)
    ax.set_xlabel("LASSO coefficient (scaled)", fontsize=6)
    ax.set_title(f"LASSO selected (C={imp['best_C'].iloc[0]:.3g})", fontsize=7)
    ax.tick_params(labelsize=5.5)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "00_lasso_selected_coefs.png", dpi=300, facecolor="white")
    fig.savefig(SHARE / "46_lasso_selected_coefs.png", dpi=300, facecolor="white")
    plt.close(fig)

    # Propose triplets from top features (prefer diversity)
    top_feats = imp.sort_values("rank_mean")["feature"].tolist()
    # seed pool: top 12 by rank + always include length/thickness/peak/spic if present
    pool = []
    for f in top_feats:
        if f not in pool:
            pool.append(f)
        if len(pool) >= 12:
            break
    for must in (
        "tumor_length_cm",
        "tumor_thickness_cm",
        "morph_peak_sharpness_max",
        "margin_spic_robust",
        "cea_value",
    ):
        if must in feats and must not in pool:
            pool.append(must)

    cand_rows = []
    for comb in combinations(pool, 3):
        # skip three size-like
        if sum(f in SIZE_LIKE for f in comb) >= 3:
            continue
        r = triplet_score(df, comb, imp)
        if r.get("ok"):
            cand_rows.append(r)
    trips = pd.DataFrame(cand_rows).sort_values("score", ascending=False)
    trips.to_csv(out / "triplet_candidates_scored.csv", index=False)

    # Also force a few clinically meaningful templates if high scoring enough
    forced = [
        ("tumor_length_cm", "tumor_thickness_cm", "morph_peak_sharpness_max"),
        ("tumor_length_cm", "tumor_thickness_cm", "margin_spic_robust"),
        ("tumor_length_cm", "tumor_thickness_cm", "cea_value"),
        ("morph_peak_sharpness_max", "morph_solidity", "margin_spic_robust"),
        ("tumor_length_cm", "cea_value", "morph_peak_sharpness_max"),
        ("tumor_length_cm", "seg_irregularity", "morph_peak_sharpness_max"),
        ("morph_peak_sharpness_max", "morph_circularity", "seg_irregularity"),
        ("bt_v2_max_outward_depth", "morph_peak_sharpness_max", "tumor_length_cm"),
    ]
    chosen = []
    seen = set()
    for row in trips.itertuples(index=False):
        key = tuple(sorted([row.f1, row.f2, row.f3]))
        if key in seen:
            continue
        seen.add(key)
        chosen.append((row.f1, row.f2, row.f3, row.score, row.auc_heldout_mean, row.shap_sum))
        if len(chosen) >= args.n_triplets:
            break
    for ft in forced:
        key = tuple(sorted(ft))
        if key in seen:
            continue
        if not all(f in feats for f in ft):
            continue
        r = triplet_score(df, ft, imp)
        if r.get("ok"):
            seen.add(key)
            chosen.append((ft[0], ft[1], ft[2], r["score"], r["auc_heldout_mean"], r["shap_sum"]))

    plot_rows = []
    for i, (f1, f2, f3, score, auc_ho, shap_sum) in enumerate(chosen[: args.n_triplets + 4], start=1):
        tid = f"T{i:02d}_{f1.split('_')[-1][:8]}_{f2.split('_')[-1][:8]}_{f3.split('_')[-1][:8]}"
        title = f"T{i:02d}"
        stem = out / f"triplet_{tid}"
        n = plot_triplet(df, (f1, f2, f3), title, stem)
        share_png = f"46_triplet_{tid}_altview.png"
        if stem.with_suffix(".png").exists():
            (SHARE / share_png).write_bytes(stem.with_suffix(".png").read_bytes())
        plot_rows.append(
            {
                "triplet_id": tid,
                "f1": f1,
                "f2": f2,
                "f3": f3,
                "labels": " / ".join(SHORT_LABEL.get(f, f) for f in (f1, f2, f3)),
                "score": score,
                "auc_heldout_mean": auc_ho,
                "shap_sum": shap_sum,
                "n": n,
                "share_png": share_png,
            }
        )
        print(f"[ok] {tid} n={n} score={score:.3f} auc_ho={auc_ho:.3f}")

    plot_tab = pd.DataFrame(plot_rows)
    plot_tab.to_csv(out / "plotted_triplets.csv", index=False)

    # Markdown summary
    lines = [
        "# LASSO + SHAP feature significance and 3D triplets",
        "",
        f"- Train LASSO-L1 logistic (T3+), 5-fold CV; SHAP LinearExplainer on train.",
        f"- LASSO AUC by split: `{json.dumps(aucs)}`",
        "",
        "## Top features (mean rank of SHAP / |LASSO| / |Spearman|)",
        "",
        "| feature | SHAP | LASSO coef | ρ | Kruskal p | size? |",
        "|---|---:|---:|---:|---:|:---:|",
    ]
    for _, r in imp.head(18).iterrows():
        lines.append(
            f"| `{r['feature']}` | {r['shap_mean_abs']:.4f} | {r['lasso_coef']:+.3f} | "
            f"{r['spearman_rho']:+.3f} | {r['kruskal_p']:.2e} | {int(r['size_like'])} |"
        )
    lines += [
        "",
        "## Plotted triplets (standard altview)",
        "",
        "| ID | Axes | score | held-out AUC | SHAP sum | N |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for _, r in plot_tab.iterrows():
        lines.append(
            f"| `{r['triplet_id']}` | {r['labels']} | {r['score']:.3f} | "
            f"{r['auc_heldout_mean']:.3f} | {r['shap_sum']:.3f} | {int(r['n'])} |"
        )
    lines += [
        "",
        "## Readout",
        "",
        "- Prefer triplets with high held-out AUC and not all size-like.",
        "- Morphology (peak sharpness / solidity) should appear if it adds beyond length.",
        "",
        "Rebuild: `python3 scripts/analyze_gc_us_feature_lasso_shap_triplets_v1.py`",
        "",
    ]
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "meta.json").write_text(
        json.dumps({"aucs": aucs, "n_features": len(feats), "triplets": plot_rows}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"out": str(out), "aucs": aucs, "n_triplets": len(plot_rows)}, indent=2))


if __name__ == "__main__":
    main()
