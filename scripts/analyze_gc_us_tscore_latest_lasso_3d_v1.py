#!/usr/bin/env python3
"""Latest GC-US T-score LASSO screening and 3D cluster visualizations.

The model is fit on the training split only.  The L1 coefficients are used for
screening, while univariate Spearman/Kruskal tests and bootstrap selection
frequency provide complementary evidence.  The 3D figures are exploratory:
pathology-stage colors show supervised separation, and a separate KMeans view
shows whether four unsupervised clusters reproduce the stage labels.

Outputs:
  pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/lasso_latest_v1/
  results/visualizations/tstage/imaging_truth_share_white_20260729/53_*.png
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from mpl_toolkits.mplot3d import proj3d
from scipy.stats import kruskal, spearmanr
from sklearn.cluster import KMeans
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, LogisticRegressionCV
from sklearn.metrics import (
    adjusted_rand_score,
    normalized_mutual_info_score,
    roc_auc_score,
    silhouette_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACK = PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1/feature_pack_v1/patient_features.csv"
META = PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1/feature_pack_v1/meta.json"
OUT = PROJECT_ROOT / "pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/lasso_latest_v1"
SHARE = PROJECT_ROOT / "results/visualizations/tstage/imaging_truth_share_white_20260729"

SPLITS = ["train", "val", "test_prospective", "test_external"]
STAGE = ["T1", "T2", "T3", "T4+"]
STAGE_COLORS = {0: "#6B9AC4", 1: "#7EB77F", 2: "#E09F3E", 3: "#C86B6B"}
CLUSTER_COLORS = {0: "#5B7FA3", 1: "#6C9B88", 2: "#C4865A", 3: "#8C78A8"}
COMMON_CASE_FEATURES = [
    "tumor_length_cm",
    "tumor_thickness_cm",
    "cea_binary",
    "seg_short_axis_ratio",
    "wall_serosa_interrupt",
    "dyn_invasion_agree",
    "margin_spic_robust__frac_high",
    "bt_v2_max_outward_depth__max",
    "morph_peak_sharpness_max",
    "morph_solidity",
    "margin_spic_robust",
    "wall_fuse_serosa_remain",
]

FEATURE_LABELS = {
    "tumor_length_cm": "Length (cm)",
    "tumor_thickness_cm": "Thickness (cm)",
    "size_max_diameter_cm": "Max diameter (cm)",
    "size_thickness_length_ratio": "Thickness / length",
    "cea_value": "CEA",
    "cea_binary": "CEA elevated",
    "seg_short_axis_ratio": "Short-axis ratio",
    "seg_irregularity": "Seg irregularity",
    "morph_peak_sharpness_max": "Peak sharpness",
    "morph_solidity": "Solidity",
    "morph_circularity": "Circularity",
    "morph_concavity_ratio": "Concavity ratio",
    "morph_nrl_roughness": "NRL roughness",
    "morph_perimeter_px": "Perimeter (px)",
    "morph_area_px": "Area (px)",
    "margin_spic_robust": "Spiculation index",
    "margin_shape_solidity": "Margin solidity",
    "margin_shape_fd_high": "Margin FD high-band",
    "margin_bof_high_mean": "BoF high-band",
    "margin_clear_robust": "Margin clarity",
    "dyn_invasion_agree": "Dynamic invasion agreement",
    "morph_peak_sharpness_max__frac_high": "Peak high-frame fraction",
    "margin_spic_robust__frac_high": "Spiculation high-frame fraction",
    "bt_v2_max_outward_depth__frac_high": "Breakthrough high-frame fraction",
    "wall_v2_remain_px__frac_low": "Low-remain frame fraction",
    "wall_serosa_interrupt__frac_high": "Serosal interruption fraction",
    "wall_serosa_interrupt": "Serosal interruption",
    "wall_depth_frac_p90": "Wall depth fraction P90",
    "wall_v2_pen_ratio_sector": "Sectoral wall penetration ratio",
    "wall_v2_composite": "ContactGeom composite",
    "wall_v2_remain_px": "Remaining wall distance (px)",
    "wall_v2_serosa_proxy": "Serosal proxy (px)",
    "wall_fuse_serosa_remain": "Fused serosa/remain score",
    "bt_v2_max_outward_depth": "Breakthrough outward depth (px)",
    "bt_v2_max_outward_depth__max": "Max-frame breakthrough depth (px)",
    "growth_outward_protrusion_ratio": "Outward protrusion ratio",
    "growth_outward_protrusion_ratio__max": "Max-frame protrusion ratio",
}

# These are deliberately family-balanced.  The first group tests the strongest
# short-axis signal with newer evidence families; the latter groups test whether
# wall and dynamic features form a coherent imaging phenotype without size.
TRIPLET_CANDIDATES = [
    (
        "L01_shortaxis_length_dynamics",
        ("seg_short_axis_ratio", "tumor_length_cm", "dyn_invasion_agree"),
        "Short-axis + length + multi-frame invasion agreement",
    ),
    (
        "L02_shortaxis_length_serosa",
        ("seg_short_axis_ratio", "tumor_length_cm", "wall_serosa_interrupt"),
        "Short-axis + length + serosal interruption",
    ),
    (
        "L03_shortaxis_length_contactgeom",
        ("seg_short_axis_ratio", "tumor_length_cm", "wall_v2_pen_ratio_sector"),
        "Short-axis + length + ContactGeom sectoral penetration",
    ),
    (
        "L04_shortaxis_length_breakthrough",
        ("seg_short_axis_ratio", "tumor_length_cm", "bt_v2_max_outward_depth__max"),
        "Short-axis + length + max-frame breakthrough depth",
    ),
    (
        "L05_shortaxis_length_protrusion",
        ("seg_short_axis_ratio", "tumor_length_cm", "growth_outward_protrusion_ratio__max"),
        "Short-axis + length + max-frame outward protrusion",
    ),
    (
        "L06_size_dynamics",
        ("tumor_length_cm", "tumor_thickness_cm", "dyn_invasion_agree"),
        "Clinical size + multi-frame invasion agreement",
    ),
    (
        "L07_size_serosa",
        ("tumor_length_cm", "tumor_thickness_cm", "wall_serosa_interrupt"),
        "Clinical size + serosal interruption",
    ),
    (
        "L08_size_contactgeom",
        ("tumor_length_cm", "tumor_thickness_cm", "wall_v2_pen_ratio_sector"),
        "Clinical size + ContactGeom sectoral penetration",
    ),
    (
        "L09_morph_margin_dynamics",
        ("morph_peak_sharpness_max", "margin_spic_robust", "dyn_invasion_agree"),
        "Morphology + margin + multi-frame dynamics",
    ),
    (
        "L10_wall_dynamics_breakthrough",
        ("wall_serosa_interrupt", "dyn_invasion_agree", "bt_v2_max_outward_depth__max"),
        "Wall evidence + dynamics + breakthrough watch feature",
    ),
    (
        "L11_shortaxis_wall_dynamics",
        ("seg_short_axis_ratio", "wall_serosa_interrupt", "dyn_invasion_agree"),
        "Short-axis + wall evidence + dynamics",
    ),
    (
        "L12_morph_wall_dynamics",
        ("morph_peak_sharpness_max", "wall_v2_composite", "dyn_invasion_agree"),
        "Peak sharpness + ContactGeom + dynamics",
    ),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def pick_font() -> str:
    cache = PROJECT_ROOT / "results/visualizations/tstage/_font_cache/NotoSerifCJKsc-Regular.ttf"
    if cache.exists():
        font_manager.fontManager.addfont(str(cache))
        return font_manager.FontProperties(fname=str(cache)).get_name()
    return "DejaVu Serif"


def apply_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.size": 6,
            "axes.labelsize": 6,
            "axes.titlesize": 7,
            "xtick.labelsize": 5,
            "ytick.labelsize": 5,
            "legend.fontsize": 5,
            "axes.linewidth": 0.6,
            "lines.linewidth": 0.8,
            "axes.facecolor": "white",
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
            "text.color": "#111111",
            "axes.labelcolor": "#111111",
            "xtick.color": "#111111",
            "ytick.color": "#111111",
            "axes.edgecolor": "#333333",
            "grid.color": "#E6E6E6",
            "axes.unicode_minus": False,
        }
    )


def bh_fdr(p_values: pd.Series) -> pd.Series:
    """Benjamini-Hochberg q values while preserving the original index."""
    p = pd.to_numeric(p_values, errors="coerce").to_numpy(float)
    q = np.full(len(p), np.nan, dtype=float)
    valid = np.isfinite(p)
    if not valid.any():
        return pd.Series(q, index=p_values.index)
    idx = np.flatnonzero(valid)
    order = idx[np.argsort(p[idx])]
    ranked = p[order]
    values = ranked * len(ranked) / np.arange(1, len(ranked) + 1)
    values = np.minimum.accumulate(values[::-1])[::-1]
    q[order] = np.clip(values, 0.0, 1.0)
    return pd.Series(q, index=p_values.index)


def load_data() -> tuple[pd.DataFrame, list[str], dict[str, str]]:
    df = pd.read_csv(PACK)
    with META.open(encoding="utf-8") as f:
        meta = json.load(f)
    groups = meta.get("keep", {})
    features: list[str] = []
    feature_group: dict[str, str] = {}
    for group, cols in groups.items():
        for feature in cols:
            if feature in df.columns and feature not in features:
                features.append(feature)
                feature_group[feature] = group
    df["label"] = pd.to_numeric(df["label"], errors="coerce")
    df["eval_split"] = df["eval_split"].astype(str)
    for feature in features:
        df[feature] = pd.to_numeric(df[feature], errors="coerce")
    df = df[df["eval_split"].isin(SPLITS) & df["label"].between(0, 3)].copy()
    return df.reset_index(drop=True), features, feature_group


def fit_lasso(
    df: pd.DataFrame, features: list[str], n_bootstrap: int
) -> tuple[Pipeline, pd.DataFrame, list[str]]:
    train = df[df["eval_split"] == "train"].copy()
    coverage = train[features].notna().mean()
    usable = [
        f
        for f in features
        if coverage[f] >= 0.60 and train[f].nunique(dropna=True) >= 2
    ]
    X = train[usable]
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
                    l1_ratios=[1.0],
                    solver="liblinear",
                    class_weight="balanced",
                    max_iter=3000,
                    scoring="roc_auc",
                    random_state=0,
                    use_legacy_attributes=True,
                ),
            ),
        ]
    )
    pipe.fit(X, y)
    clf = pipe.named_steps["clf"]
    coef = clf.coef_.ravel()
    best_c = float(np.ravel(clf.C_)[0])
    Xs = pipe.named_steps["scaler"].transform(pipe.named_steps["imputer"].transform(X))

    # Bootstrap stability at the CV-selected penalty.  This is a selection
    # frequency, not a p value.
    rng = np.random.default_rng(0)
    selected = np.zeros((n_bootstrap, len(usable)), dtype=bool)
    signs = np.zeros((n_bootstrap, len(usable)), dtype=float)
    for b in range(selected.shape[0]):
        idx = rng.integers(0, len(y), size=len(y))
        model = LogisticRegression(
            C=best_c,
            l1_ratio=1.0,
            solver="liblinear",
            class_weight="balanced",
            max_iter=3000,
            random_state=b,
        )
        model.fit(Xs[idx], y[idx])
        bcoef = model.coef_.ravel()
        selected[b] = np.abs(bcoef) > 1e-8
        signs[b] = bcoef

    rows = []
    for i, feature in enumerate(usable):
        sub = train[["label", feature]].dropna()
        values = sub[feature].to_numpy(float)
        labels = sub["label"].astype(int).to_numpy()
        rho, rho_p = spearmanr(values, labels)
        groups = [values[labels == k] for k in range(4) if np.sum(labels == k) >= 2]
        try:
            kw_p = float(kruskal(*groups).pvalue) if len(groups) >= 2 else float("nan")
        except ValueError:
            kw_p = float("nan")
        y_bin = (labels >= 2).astype(int)
        try:
            auc = float(roc_auc_score(y_bin, values))
            orientation = 1.0 if auc >= 0.5 else -1.0
            auc_oriented = max(auc, 1.0 - auc)
        except ValueError:
            orientation = float("nan")
            auc_oriented = float("nan")
        rows.append(
            {
                "feature": feature,
                "lasso_coef": float(coef[i]),
                "lasso_abs_coef": float(abs(coef[i])),
                "selected": int(abs(coef[i]) > 1e-8),
                "best_C": best_c,
                "n_train": int(len(sub)),
                "train_coverage": float(coverage[feature]),
                "missing_rate_train": float(1.0 - coverage[feature]),
                "stability_freq": float(selected[:, i].mean()),
                "positive_freq": float(np.mean(signs[:, i] > 1e-8)),
                "negative_freq": float(np.mean(signs[:, i] < -1e-8)),
                "spearman_rho": float(rho),
                "spearman_p": float(rho_p),
                "spearman_q": float("nan"),
                "kruskal_p": kw_p,
                "kruskal_q": float("nan"),
                "auc_T3plus_oriented": auc_oriented,
                "auc_orientation_high": orientation,
            }
        )
    imp = pd.DataFrame(rows)
    imp["spearman_q"] = bh_fdr(imp["spearman_p"])
    imp["kruskal_q"] = bh_fdr(imp["kruskal_p"])
    imp["rank_stability"] = imp["stability_freq"].rank(ascending=False, method="min")
    imp["rank_lasso"] = imp["lasso_abs_coef"].rank(ascending=False, method="min")
    imp["rank_univariate"] = imp["spearman_rho"].abs().rank(ascending=False, method="min")
    imp["rank_mean"] = imp[["rank_stability", "rank_lasso", "rank_univariate"]].mean(axis=1)
    return pipe, imp.sort_values(["rank_mean", "feature"]).reset_index(drop=True), usable


def evaluate_lasso(pipe: Pipeline, df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    rows = []
    for split in SPLITS:
        sub = df[df["eval_split"] == split].copy()
        y = (sub["label"] >= 2).astype(int).to_numpy()
        if len(np.unique(y)) < 2:
            auc = float("nan")
        else:
            prob = pipe.predict_proba(sub[features])[:, 1]
            auc = float(roc_auc_score(y, prob))
        rows.append({"split": split, "n": int(len(sub)), "auc_T3plus": auc})
    return pd.DataFrame(rows)


def evaluate_common_complete_case(
    pipe: Pipeline, df: pd.DataFrame, features: list[str]
) -> pd.DataFrame:
    anchor = [f for f in COMMON_CASE_FEATURES if f in df.columns]
    cohort = df.dropna(subset=anchor).copy()
    rows = []
    for split in SPLITS:
        sub = cohort[cohort["eval_split"] == split].copy()
        y = (sub["label"] >= 2).astype(int).to_numpy()
        if len(np.unique(y)) < 2:
            auc = float("nan")
        else:
            auc = float(roc_auc_score(y, pipe.predict_proba(sub[features])[:, 1]))
        rows.append(
            {
                "split": split,
                "n": int(len(sub)),
                "auc_T3plus": auc,
                "anchor": "kitchen union pack_core",
            }
        )
    return pd.DataFrame(rows)


def projection_xy(ax: object, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    px, py, _ = proj3d.proj_transform(x, y, z, ax.get_proj())
    return np.column_stack([px, py])


def separation_score(xy: np.ndarray, labels: np.ndarray) -> float:
    levels = np.unique(labels)
    if len(levels) < 2 or len(xy) < 20:
        return -np.inf
    scaled = StandardScaler().fit_transform(xy)
    medians = []
    within = []
    for level in levels:
        part = scaled[labels == level]
        if len(part) < 3:
            return -np.inf
        med = np.median(part, axis=0)
        medians.append(med)
        within.append(np.mean(np.sum((part - med) ** 2, axis=1)))
    path = float(np.sum(np.linalg.norm(np.diff(np.asarray(medians), axis=0), axis=1)))
    denom = math.sqrt(float(np.mean(within)) + 1e-9)
    try:
        sil = float(
            silhouette_score(
                scaled,
                labels,
                sample_size=min(800, len(scaled)),
                random_state=0,
            )
        )
    except ValueError:
        sil = 0.0
    return path / denom + 1.5 * sil


def set_limits(ax: object, arrays: list[np.ndarray]) -> None:
    for setter, values in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), arrays):
        values = values[np.isfinite(values)]
        lo = float(np.quantile(values, 0.005))
        hi = float(np.quantile(values, 0.995))
        if math.isclose(lo, hi):
            pad = max(abs(lo) * 0.05, 1e-3)
            lo -= pad
            hi += pad
        pad = 0.06 * (hi - lo)
        setter(lo - pad, hi + pad)


def best_view(train_sub: pd.DataFrame, features: tuple[str, str, str]) -> dict[str, float]:
    values = train_sub[list(features)].to_numpy(float)
    labels = train_sub["label"].astype(int).to_numpy()
    fig = plt.figure(figsize=(3.5, 3.2))
    ax = fig.add_subplot(111, projection="3d")
    set_limits(ax, [values[:, 0], values[:, 1], values[:, 2]])
    best = {"score": -np.inf, "elev": 22.0, "azim": -55.0}
    for elev in range(10, 55, 4):
        for azim in range(-180, 180, 8):
            ax.view_init(elev=elev, azim=azim)
            score = separation_score(
                projection_xy(ax, values[:, 0], values[:, 1], values[:, 2]), labels
            )
            if score > best["score"]:
                best = {"score": float(score), "elev": float(elev), "azim": float(azim)}
    plt.close(fig)
    return best


def cluster_metrics(df: pd.DataFrame, features: tuple[str, str, str]) -> dict[str, float]:
    train = df[df["eval_split"] == "train"].dropna(subset=list(features)).copy()
    if len(train) < 80:
        return {}
    scaler = StandardScaler().fit(train[list(features)])
    km = KMeans(n_clusters=4, n_init=30, random_state=0)
    train_z = scaler.transform(train[list(features)])
    train_cluster = km.fit_predict(train_z)
    metrics: dict[str, float] = {}
    for split in SPLITS:
        sub = df[df["eval_split"] == split].dropna(subset=list(features)).copy()
        if len(sub) < 15:
            continue
        pred = km.predict(scaler.transform(sub[list(features)]))
        truth = sub["label"].astype(int).to_numpy()
        if len(np.unique(truth)) >= 2:
            metrics[f"{split}_kmeans_ari"] = float(adjusted_rand_score(truth, pred))
            metrics[f"{split}_kmeans_nmi"] = float(
                normalized_mutual_info_score(truth, pred)
            )
    if len(np.unique(train["label"])) >= 2:
        metrics["train_stage_silhouette_3d"] = float(
            silhouette_score(train_z, train["label"].astype(int), sample_size=min(1000, len(train)), random_state=0)
        )
    metrics["train_kmeans_silhouette_3d"] = float(silhouette_score(train_z, train_cluster))
    return metrics


def plot_3d(
    sub: pd.DataFrame,
    features: tuple[str, str, str],
    title: str,
    stem: Path,
    elev: float,
    azim: float,
    mode: str,
    cluster_model: tuple[StandardScaler, KMeans] | None = None,
) -> None:
    values = sub[list(features)].to_numpy(float)
    labels = sub["label"].astype(int).to_numpy()
    fig = plt.figure(figsize=(5.2, 4.0), dpi=300)
    ax = fig.add_axes([0.02, 0.18, 0.72, 0.76], projection="3d")
    set_limits(ax, [values[:, 0], values[:, 1], values[:, 2]])

    if mode == "stage":
        colors = STAGE_COLORS
        groups = [(k, labels == k, STAGE[k]) for k in range(4)]
        marker_labels = [STAGE[k] for k in range(4)]
    else:
        if cluster_model is None:
            raise ValueError("cluster_model is required for cluster mode")
        scaler, km = cluster_model
        cluster_labels = km.predict(scaler.transform(sub[list(features)]))
        colors = CLUSTER_COLORS
        groups = [
            (k, cluster_labels == k, f"Cluster {k + 1}")
            for k in range(4)
        ]
        marker_labels = [f"Cluster {k + 1}" for k in range(4)]

    handles = []
    for key, mask, group_label in groups:
        handle = ax.scatter(
            values[mask, 0],
            values[mask, 1],
            values[mask, 2],
            s=4,
            alpha=0.24,
            c=colors[key],
            edgecolors="none",
            depthshade=False,
            label=f"{group_label} (n={int(mask.sum())})",
        )
        handles.append(handle)

    if mode == "stage":
        medians = []
        valid_keys = []
        for k in range(4):
            mask = labels == k
            if mask.any():
                medians.append(np.median(values[mask], axis=0))
                valid_keys.append(k)
        if medians:
            medians_arr = np.asarray(medians)
            ax.plot(
                medians_arr[:, 0],
                medians_arr[:, 1],
                medians_arr[:, 2],
                color="#222222",
                linewidth=1.0,
                zorder=4,
            )
            for med, k in zip(medians_arr, valid_keys):
                ax.scatter(
                    [med[0]],
                    [med[1]],
                    [med[2]],
                    s=42,
                    c=STAGE_COLORS[k],
                    edgecolors="white",
                    linewidths=0.9,
                    marker="D",
                    depthshade=False,
                    zorder=6,
                )
    else:
        scaler, km = cluster_model
        centers = scaler.inverse_transform(km.cluster_centers_)
        ax.scatter(
            centers[:, 0],
            centers[:, 1],
            centers[:, 2],
            s=70,
            c=[CLUSTER_COLORS[k] for k in range(4)],
            edgecolors="black",
            linewidths=0.7,
            marker="X",
            depthshade=False,
            zorder=8,
        )

    ax.view_init(elev=elev, azim=azim)
    ax.xaxis.pane.fill = False
    ax.yaxis.pane.fill = False
    ax.zaxis.pane.fill = False
    ax.xaxis.pane.set_edgecolor("#CCCCCC")
    ax.yaxis.pane.set_edgecolor("#CCCCCC")
    ax.zaxis.pane.set_edgecolor("#CCCCCC")
    ax.grid(True, linestyle="-", linewidth=0.25, alpha=0.45)
    ax.tick_params(axis="both", which="major", labelsize=5.5, pad=2, length=1.5, width=0.35)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_zlabel("")
    ax.set_title(f"{title}  N={len(sub)}", fontsize=7, pad=2)

    leg_ax = fig.add_axes([0.76, 0.35, 0.22, 0.40])
    leg_ax.axis("off")
    leg_ax.legend(
        handles,
        [h.get_label() for h in handles],
        loc="center left",
        fontsize=5.3,
        frameon=False,
        markerscale=2.2,
        handletextpad=0.4,
        labelspacing=0.45,
    )

    key_ax = fig.add_axes([0.06, 0.02, 0.88, 0.12])
    key_ax.axis("off")
    key_ax.text(0.0, 0.72, "Axes", fontsize=6, fontweight="bold", transform=key_ax.transAxes, va="center")
    axis_text = "X  " + FEATURE_LABELS.get(features[0], features[0])
    axis_text += "      Y  " + FEATURE_LABELS.get(features[1], features[1])
    axis_text += "      Z  " + FEATURE_LABELS.get(features[2], features[2])
    key_ax.text(0.0, 0.28, axis_text, fontsize=5.8, transform=key_ax.transAxes, va="center")

    stem.parent.mkdir(parents=True, exist_ok=True)
    for ext, dpi in (("png", 600), ("pdf", None), ("svg", None)):
        kwargs = {"facecolor": "white", "pad_inches": 0.04}
        if dpi:
            kwargs["dpi"] = dpi
        fig.savefig(stem.with_suffix(f".{ext}"), **kwargs)
    plt.close(fig)


def save_significance_fig(imp: pd.DataFrame, out: Path) -> None:
    selected = imp[imp["selected"] == 1].sort_values(
        "lasso_abs_coef", ascending=False
    )
    top = selected.head(18)
    fig, ax = plt.subplots(figsize=(4.2, 4.2), dpi=300)
    y = np.arange(len(top))
    colors = ["#C86B6B" if c > 0 else "#6B9AC4" for c in top["lasso_coef"]]
    ax.barh(y, top["lasso_coef"], color=colors, height=0.68)
    ax.axvline(0, color="#333333", linewidth=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels([FEATURE_LABELS.get(f, f) for f in top["feature"]], fontsize=5.5)
    ax.set_xlabel("L1 coefficient, standardized feature", fontsize=6)
    ax.set_title("Latest feature pack, LASSO screening", fontsize=7)
    ax.tick_params(axis="x", labelsize=5)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "00_lasso_coefficients_top18.png", dpi=600, facecolor="white")
    fig.savefig(out / "00_lasso_coefficients_top18.pdf", facecolor="white")
    fig.savefig(SHARE / "53_lasso_latest_coefficients_top18.png", dpi=600, facecolor="white")
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    ap.add_argument("--share-dir", type=Path, default=SHARE)
    ap.add_argument("--n-bootstrap", type=int, default=80)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    global SHARE
    SHARE = args.share_dir
    args.out_dir.mkdir(parents=True, exist_ok=True)
    SHARE.mkdir(parents=True, exist_ok=True)
    apply_style()

    df, features, feature_group = load_data()
    pipe, imp, model_features = fit_lasso(df, features, args.n_bootstrap)
    # Keep the exact pre-sort feature order used during fitting for prediction.
    usable = model_features
    metrics = evaluate_lasso(pipe, df, usable)
    common_metrics = evaluate_common_complete_case(pipe, df, usable)
    imp["feature_group"] = imp["feature"].map(feature_group).fillna("unknown")
    imp.to_csv(args.out_dir / "feature_significance.csv", index=False)
    metrics.to_csv(args.out_dir / "lasso_auc_by_split.csv", index=False)
    common_metrics.to_csv(args.out_dir / "lasso_auc_common_complete_case.csv", index=False)
    save_significance_fig(imp, args.out_dir)

    train = df[df["eval_split"] == "train"]
    triplet_rows = []
    missing_triplets = []
    for triplet_id, triplet, rationale in TRIPLET_CANDIDATES:
        if not all(f in df.columns for f in triplet):
            missing_triplets.append({"id": triplet_id, "reason": "missing feature column"})
            continue
        sub = df.dropna(subset=list(triplet)).copy()
        if len(sub) < 80 or sub["label"].nunique() < 3:
            missing_triplets.append({"id": triplet_id, "reason": f"usable N={len(sub)}"})
            continue
        train_sub = train.dropna(subset=list(triplet)).copy()
        if len(train_sub) < 80 or train_sub["label"].nunique() < 3:
            missing_triplets.append({"id": triplet_id, "reason": f"train N={len(train_sub)}"})
            continue
        camera = best_view(train_sub, triplet)
        km_scaler = StandardScaler().fit(train_sub[list(triplet)])
        km = KMeans(n_clusters=4, n_init=30, random_state=0).fit(
            km_scaler.transform(train_sub[list(triplet)])
        )
        km_model = (km_scaler, km)
        stage_stem = args.out_dir / f"{triplet_id}_stage"
        cluster_stem = args.out_dir / f"{triplet_id}_kmeans"
        plot_3d(
            sub,
            triplet,
            f"{triplet_id} pathology-stage separation",
            stage_stem,
            camera["elev"],
            camera["azim"],
            "stage",
        )
        plot_3d(
            sub,
            triplet,
            f"{triplet_id} unsupervised four-cluster view",
            cluster_stem,
            camera["elev"],
            camera["azim"],
            "cluster",
            km_model,
        )
        share_stage = SHARE / f"53_{triplet_id}_stage_bestview.png"
        share_cluster = SHARE / f"53_{triplet_id}_kmeans_bestview.png"
        shutil.copyfile(stage_stem.with_suffix(".png"), share_stage)
        shutil.copyfile(cluster_stem.with_suffix(".png"), share_cluster)
        cluster_result = cluster_metrics(df, triplet)
        row = {
            "triplet_id": triplet_id,
            "f1": triplet[0],
            "f2": triplet[1],
            "f3": triplet[2],
            "labels": " / ".join(FEATURE_LABELS.get(f, f) for f in triplet),
            "rationale": rationale,
            "n_all": int(len(sub)),
            "n_train": int(len(train_sub)),
            "best_view_elev": camera["elev"],
            "best_view_azim": camera["azim"],
            "train_projection_separation": camera["score"],
            "share_stage_png": share_stage.name,
            "share_kmeans_png": share_cluster.name,
        }
        row.update(cluster_result)
        triplet_rows.append(row)
        print(
            f"[ok] {triplet_id} N={len(sub)} train={len(train_sub)} "
            f"view=({camera['elev']:.0f},{camera['azim']:.0f})"
        )

    triplets = pd.DataFrame(triplet_rows)
    triplets.to_csv(args.out_dir / "triplet_cluster_metrics.csv", index=False)
    pd.DataFrame(missing_triplets).to_csv(args.out_dir / "triplets_skipped.csv", index=False)

    selected_top = imp[imp["selected"] == 1].sort_values(
        "lasso_abs_coef", ascending=False
    ).head(18)
    univariate_top = imp.sort_values(
        ["spearman_q", "kruskal_q"], ascending=True
    ).head(12)
    lines = [
        "# Latest GC-US T-score LASSO and 3D cluster analysis",
        "",
        f"- Generated: `{utc_now()}`",
        "- Source: `pipeline/data/gc_us_tscore_features_v1/feature_pack_v1/patient_features.csv`",
        "- Fit rule: L1 logistic regression on train only, T3+ versus T1-T2; median imputation and standardization are fit on train.",
        "- Evaluation: train, val, prospective, and external; holdout is not used in this report.",
        "",
        "## Important interpretation rule",
        "",
        "LASSO coefficients are selection weights, not p values. Bootstrap selection frequency is stability evidence. Spearman and Kruskal values are univariate train-only tests and their q values are Benjamini-Hochberg adjusted across the screened features.",
        "",
        "## LASSO AUC",
        "",
        "| split | N | T3+ AUC |",
        "|---|---:|---:|",
    ]
    for _, row in metrics.iterrows():
        lines.append(f"| {row['split']} | {int(row['n'])} | {row['auc_T3plus']:.3f} |")
    lines += [
        "",
        "## LASSO AUC on common complete-case cohort",
        "",
        "The same LASSO pipeline is evaluated on the complete-case cohort used by the kitchen and pack-core comparison. This separates feature coverage loss from model generalization.",
        "",
        "| split | N | T3+ AUC |",
        "|---|---:|---:|",
    ]
    for _, row in common_metrics.iterrows():
        lines.append(
            f"| {row['split']} | {int(row['n'])} | {row['auc_T3plus']:.3f} |"
        )
    lines += [
        "",
        "## Nonzero LASSO terms",
        "",
        "| feature | group | L1 coef | stability | Spearman rho | Spearman q | Kruskal q | coverage |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in selected_top.iterrows():
        lines.append(
            f"| `{row['feature']}` | {row['feature_group']} | "
            f"{row['lasso_coef']:+.3f} | {row['stability_freq']:.2f} | "
            f"{row['spearman_rho']:+.3f} | {row['spearman_q']:.2e} | "
            f"{row['kruskal_q']:.2e} | {row['train_coverage']:.2f} |"
        )
    lines += [
        "",
        "## Strong univariate signals zeroed by LASSO",
        "",
        "These features remain associated with stage on their own but were redundant with correlated terms in the multivariable L1 fit.",
        "",
        "| feature | group | L1 coef | stability | Spearman rho | Spearman q | coverage |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for _, row in univariate_top.iterrows():
        if int(row["selected"]) == 1:
            continue
        lines.append(
            f"| `{row['feature']}` | {row['feature_group']} | "
            f"{row['lasso_coef']:+.3f} | {row['stability_freq']:.2f} | "
            f"{row['spearman_rho']:+.3f} | {row['spearman_q']:.2e} | "
            f"{row['train_coverage']:.2f} |"
        )
    lines += [
        "",
        "## 3D triplets",
        "",
        "Stage figures use pathology T1 to T4+ colors and a stage-median path. KMeans figures fit four clusters on train only, then assign all splits. Camera search uses train labels only and is for visual separation, not model validation.",
        "",
        "| ID | axes | N | train N | view | train ARI | prospective ARI | external ARI |",
        "|---|---|---:|---:|---|---:|---:|---:|",
    ]
    for _, row in triplets.iterrows():
        lines.append(
            f"| `{row['triplet_id']}` | {row['labels']} | {int(row['n_all'])} | "
            f"{int(row['n_train'])} | {row['best_view_elev']:.0f}/{row['best_view_azim']:.0f} | "
            f"{row.get('train_kmeans_ari', float('nan')):.3f} | "
            f"{row.get('test_prospective_kmeans_ari', float('nan')):.3f} | "
            f"{row.get('test_external_kmeans_ari', float('nan')):.3f} |"
        )
    lines += [
        "",
        "## Readout",
        "",
        "- Treat short-axis ratio and length as size/geometry signals, not independent biological mechanisms.",
        "- A wall or breakthrough feature is useful only if it remains stable after checking coverage and external KMeans or stage separation.",
        "- The KMeans panels are descriptive. They do not establish a new T-score or replace patient-level external validation.",
        "",
        "Rebuild: `python3 scripts/analyze_gc_us_tscore_latest_lasso_3d_v1.py`",
        "",
    ]
    (args.out_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    meta = {
        "generated": utc_now(),
        "n": int(len(df)),
        "n_by_split": df["eval_split"].value_counts().to_dict(),
        "features": features,
        "usable_features": usable,
        "metrics": metrics.to_dict(orient="records"),
        "common_complete_case_metrics": common_metrics.to_dict(orient="records"),
        "triplets": triplet_rows,
        "triplets_skipped": missing_triplets,
    }
    (args.out_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False, allow_nan=True),
        encoding="utf-8",
    )
    print(json.dumps({"out": str(args.out_dir), "n_triplets": len(triplet_rows)}, indent=2))


if __name__ == "__main__":
    main()
