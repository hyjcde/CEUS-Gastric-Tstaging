#!/usr/bin/env python3
"""Compute pathology-stage association metrics for L01–L12 triplets.

KMeans ARI is retained only as a negative control. Primary readout is stage
association: Spearman vs ordinal T, T3+ AUC / 4-class QWK by split, and
adjacent-stage AUCs. Fit always uses train only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import cohen_kappa_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACK = PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1/feature_pack_v1/patient_features.csv"
CLUSTER = (
    PROJECT_ROOT
    / "pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/lasso_latest_v1/triplet_cluster_metrics.csv"
)
OUT = (
    PROJECT_ROOT
    / "pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/lasso_latest_v1/triplet_stage_metrics.csv"
)

FEATURE_ZH = {
    "seg_short_axis_ratio": "短轴比",
    "tumor_length_cm": "长径 (cm)",
    "tumor_thickness_cm": "厚径 (cm)",
    "dyn_invasion_agree": "动态侵犯一致度",
    "wall_serosa_interrupt": "浆膜中断代理",
    "wall_v2_pen_ratio_sector": "扇区穿透比",
    "bt_v2_max_outward_depth__max": "最大帧突破深度 (px)",
    "growth_outward_protrusion_ratio__max": "最大帧外凸比",
    "morph_peak_sharpness_max": "峰锐度",
    "margin_spic_robust": "毛刺指数",
    "wall_v2_composite": "ContactGeom 综合分",
}

TRIPLETS = [
    ("L01_shortaxis_length_dynamics", ("seg_short_axis_ratio", "tumor_length_cm", "dyn_invasion_agree")),
    ("L02_shortaxis_length_serosa", ("seg_short_axis_ratio", "tumor_length_cm", "wall_serosa_interrupt")),
    ("L03_shortaxis_length_contactgeom", ("seg_short_axis_ratio", "tumor_length_cm", "wall_v2_pen_ratio_sector")),
    ("L04_shortaxis_length_breakthrough", ("seg_short_axis_ratio", "tumor_length_cm", "bt_v2_max_outward_depth__max")),
    ("L05_shortaxis_length_protrusion", ("seg_short_axis_ratio", "tumor_length_cm", "growth_outward_protrusion_ratio__max")),
    ("L06_size_dynamics", ("tumor_length_cm", "tumor_thickness_cm", "dyn_invasion_agree")),
    ("L07_size_serosa", ("tumor_length_cm", "tumor_thickness_cm", "wall_serosa_interrupt")),
    ("L08_size_contactgeom", ("tumor_length_cm", "tumor_thickness_cm", "wall_v2_pen_ratio_sector")),
    ("L09_morph_margin_dynamics", ("morph_peak_sharpness_max", "margin_spic_robust", "dyn_invasion_agree")),
    ("L10_wall_dynamics_breakthrough", ("wall_serosa_interrupt", "dyn_invasion_agree", "bt_v2_max_outward_depth__max")),
    ("L11_shortaxis_wall_dynamics", ("seg_short_axis_ratio", "wall_serosa_interrupt", "dyn_invasion_agree")),
    ("L12_morph_wall_dynamics", ("morph_peak_sharpness_max", "wall_v2_composite", "dyn_invasion_agree")),
]


def _pipe_bin() -> Pipeline:
    return Pipeline(
        [
            ("imp", SimpleImputer(strategy="median")),
            ("sc", StandardScaler()),
            ("clf", LogisticRegression(max_iter=4000, class_weight="balanced")),
        ]
    )


def _pipe_multi() -> Pipeline:
    return Pipeline(
        [
            ("imp", SimpleImputer(strategy="median")),
            ("sc", StandardScaler()),
            ("clf", LogisticRegression(max_iter=4000, class_weight="balanced")),
        ]
    )


def _auc(y_true, score) -> float:
    y = np.asarray(y_true)
    if len(np.unique(y)) < 2:
        return float("nan")
    return float(roc_auc_score(y, score))


def evaluate_triplet(df: pd.DataFrame, feats: tuple[str, str, str]) -> dict:
    sub = df.dropna(subset=list(feats) + ["label", "eval_split"]).copy()
    sub["ord"] = sub["label"].astype(int)
    sub["y3"] = (sub["ord"] >= 2).astype(int)
    train = sub[sub["eval_split"] == "train"]

    rhos = {}
    medians = {}
    for f in feats:
        r, _ = spearmanr(sub[f], sub["ord"])
        rhos[f] = float(r)
        medians[f] = [float(sub.loc[sub["ord"] == k, f].median()) for k in range(4)]

    pipe = _pipe_bin()
    pipe.fit(train[list(feats)], train["y3"])
    auc = {}
    for sp, ss in sub.groupby("eval_split"):
        auc[sp] = _auc(ss["y3"], pipe.predict_proba(ss[list(feats)])[:, 1])

    # length-only baseline on same complete-case cohort when available
    auc_length = {}
    if "tumor_length_cm" in sub.columns and sub["tumor_length_cm"].notna().all():
        pipe_l = _pipe_bin()
        pipe_l.fit(train[["tumor_length_cm"]], train["y3"])
        for sp, ss in sub.groupby("eval_split"):
            auc_length[sp] = _auc(ss["y3"], pipe_l.predict_proba(ss[["tumor_length_cm"]])[:, 1])

    pipe4 = _pipe_multi()
    pipe4.fit(train[list(feats)], train["ord"])
    qwk = {}
    for sp, ss in sub.groupby("eval_split"):
        pred = pipe4.predict(ss[list(feats)])
        qwk[sp] = float(cohen_kappa_score(ss["ord"], pred, weights="quadratic"))

    adj_all = {}
    adj_ext = {}
    for a, b, name in [(0, 1, "T1vsT2"), (1, 2, "T2vsT3"), (2, 3, "T3vsT4")]:
        tr = train[train["ord"].isin([a, b])]
        if tr["ord"].nunique() < 2:
            continue
        p2 = _pipe_bin()
        p2.fit(tr[list(feats)], (tr["ord"] == b).astype(int))
        ss = sub[sub["ord"].isin([a, b])]
        adj_all[name] = _auc((ss["ord"] == b).astype(int), p2.predict_proba(ss[list(feats)])[:, 1])
        se = ss[ss["eval_split"] == "test_external"]
        if len(se) >= 15 and se["ord"].nunique() == 2:
            adj_ext[name] = _auc((se["ord"] == b).astype(int), p2.predict_proba(se[list(feats)])[:, 1])

    has_length = any(f == "tumor_length_cm" for f in feats)
    family = (
        "含临床长径"
        if has_length
        else ("纯影像几何+壁/动态" if "seg_short_axis_ratio" in feats or "morph_peak_sharpness_max" in feats else "壁/动态观察")
    )

    return {
        "n_all": int(len(sub)),
        "n_train": int(len(train)),
        "labels_zh": " / ".join(FEATURE_ZH.get(f, f) for f in feats),
        "family": family,
        "has_clinical_length": int(has_length),
        "rho_f1": rhos[feats[0]],
        "rho_f2": rhos[feats[1]],
        "rho_f3": rhos[feats[2]],
        "median_f1_T1": medians[feats[0]][0],
        "median_f1_T2": medians[feats[0]][1],
        "median_f1_T3": medians[feats[0]][2],
        "median_f1_T4": medians[feats[0]][3],
        "median_f2_T1": medians[feats[1]][0],
        "median_f2_T2": medians[feats[1]][1],
        "median_f2_T3": medians[feats[1]][2],
        "median_f2_T4": medians[feats[1]][3],
        "median_f3_T1": medians[feats[2]][0],
        "median_f3_T2": medians[feats[2]][1],
        "median_f3_T3": medians[feats[2]][2],
        "median_f3_T4": medians[feats[2]][3],
        "auc_T3plus_train": auc.get("train", float("nan")),
        "auc_T3plus_val": auc.get("val", float("nan")),
        "auc_T3plus_prospective": auc.get("test_prospective", float("nan")),
        "auc_T3plus_external": auc.get("test_external", float("nan")),
        "auc_length_external": auc_length.get("test_external", float("nan")),
        "delta_ext_vs_length": (
            auc.get("test_external", float("nan")) - auc_length.get("test_external", float("nan"))
            if auc_length
            else float("nan")
        ),
        "qwk_4class_train": qwk.get("train", float("nan")),
        "qwk_4class_val": qwk.get("val", float("nan")),
        "qwk_4class_prospective": qwk.get("test_prospective", float("nan")),
        "qwk_4class_external": qwk.get("test_external", float("nan")),
        "auc_T1vsT2_all": adj_all.get("T1vsT2", float("nan")),
        "auc_T2vsT3_all": adj_all.get("T2vsT3", float("nan")),
        "auc_T3vsT4_all": adj_all.get("T3vsT4", float("nan")),
        "auc_T1vsT2_external": adj_ext.get("T1vsT2", float("nan")),
        "auc_T2vsT3_external": adj_ext.get("T2vsT3", float("nan")),
        "auc_T3vsT4_external": adj_ext.get("T3vsT4", float("nan")),
    }


def narrative(row: pd.Series) -> str:
    """Chinese staging-focused caption for one triplet."""
    axes = str(row["labels_zh"])
    med = (
        f"中位数 T1→T4+：轴1 {row['median_f1_T1']:.3g}/{row['median_f1_T2']:.3g}/"
        f"{row['median_f1_T3']:.3g}/{row['median_f1_T4']:.3g}；"
        f"轴2 {row['median_f2_T1']:.3g}/{row['median_f2_T2']:.3g}/"
        f"{row['median_f2_T3']:.3g}/{row['median_f2_T4']:.3g}；"
        f"轴3 {row['median_f3_T1']:.3g}/{row['median_f3_T2']:.3g}/"
        f"{row['median_f3_T3']:.3g}/{row['median_f3_T4']:.3g}。"
    )
    rho = (
        f"与病理序贯 T 的 Spearman ρ={row['rho_f1']:.3f}/"
        f"{row['rho_f2']:.3f}/{row['rho_f3']:.3f}。"
    )
    auc = (
        f"三特征 logistic（仅训练集拟合）T3+ AUC：训练 {row['auc_T3plus_train']:.3f}，"
        f"验证 {row['auc_T3plus_val']:.3f}，前瞻 {row['auc_T3plus_prospective']:.3f}，"
        f"外部 {row['auc_T3plus_external']:.3f}。"
    )
    qwk = (
        f"四分类 QWK：验证 {row['qwk_4class_val']:.3f}，"
        f"前瞻 {row['qwk_4class_prospective']:.3f}，外部 {row['qwk_4class_external']:.3f}。"
    )
    adj = (
        f"相邻期 AUC（全体可用 / 外部）：T1–T2 {row['auc_T1vsT2_all']:.3f}/"
        f"{row['auc_T1vsT2_external']:.3f}，T2–T3 {row['auc_T2vsT3_all']:.3f}/"
        f"{row['auc_T2vsT3_external']:.3f}，T3–T4+ {row['auc_T3vsT4_all']:.3f}/"
        f"{row['auc_T3vsT4_external']:.3f}。"
    )
    kmeans = (
        f"无监督 KMeans 仅作对照：外部 ARI={row['test_external_kmeans_ari']:.3f}"
        f"（接近 0 表示聚类不能复现分期，不应按 cluster 解读）。"
    )

    tid = str(row["triplet_id"])
    if tid == "L11_shortaxis_wall_dynamics":
        head = (
            "L11 是「不含临床长径」的影像提分期三元组：短轴比（病灶负荷几何）× "
            "浆膜中断软代理 × 多帧动态侵犯一致度。看图请以病理 T 着色为主——"
            "黑线连接各期中位点，可见三轴中位数随 T1→T4+ 同步抬升，说明存在连续分期梯度；"
            "散点重叠仍大，故更适合作为补充证据，而不是单独四分类器。"
        )
        vs_len = (
            f"同一完整病例上，仅长径的外部 T3+ AUC≈{row['auc_length_external']:.3f}，"
            f"而 L11 三特征外部仅 {row['auc_T3plus_external']:.3f}"
            f"（Δ={row['delta_ext_vs_length']:.3f}），说明缺了临床大小后，"
            "壁/动态通道不足以扛起 T3+ 主判别；其价值在于提供与大小部分正交的壁层与动态信息，"
            "尤其相邻期里 T2–T3 外部 AUC≈"
            f"{row['auc_T2vsT3_external']:.3f} 相对更好。"
        )
        return " ".join([head, f"轴：{axes}。", med, rho, auc, qwk, adj, vs_len, kmeans])

    if row["has_clinical_length"]:
        head = (
            f"{tid} 含临床长径，属于「大小主轴 + 影像补充」提分期组合。"
            "分期图应优先看病理着色与中位轨迹；若外部 T3+ AUC 接近长径基线，"
            "说明第三轴主要是修饰而非替代大小。"
        )
        vs_len = (
            f"同队列长径基线外部 AUC≈{row['auc_length_external']:.3f}，"
            f"本三元组外部 AUC={row['auc_T3plus_external']:.3f}"
            f"（Δ={row['delta_ext_vs_length']:+.3f}）。"
        )
    else:
        head = (
            f"{tid} 不含临床长径，属于纯影像提分期探针。"
            "重点看病理 T 着色下的梯度与相邻期可分性；外部 T3+ / QWK 若明显弱于含长径组合，"
            "说明这些轴更适合做补充征象，而不是独立分期器。"
        )
        vs_len = (
            f"同队列长径基线外部 AUC≈{row['auc_length_external']:.3f}，"
            f"本三元组外部 AUC={row['auc_T3plus_external']:.3f}"
            f"（Δ={row['delta_ext_vs_length']:+.3f}）。"
        )

    return " ".join([head, f"轴：{axes}。", med, rho, auc, qwk, adj, vs_len, kmeans])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    df = pd.read_csv(PACK)
    cluster = pd.read_csv(CLUSTER).set_index("triplet_id")
    rows = []
    for tid, feats in TRIPLETS:
        stats = evaluate_triplet(df, feats)
        crow = cluster.loc[tid]
        row = {
            "triplet_id": tid,
            "f1": feats[0],
            "f2": feats[1],
            "f3": feats[2],
            "labels": crow["labels"],
            **stats,
            "test_external_kmeans_ari": float(crow["test_external_kmeans_ari"]),
            "train_kmeans_ari": float(crow["train_kmeans_ari"]),
            "test_prospective_kmeans_ari": float(crow["test_prospective_kmeans_ari"]),
            "train_stage_silhouette_3d": float(crow["train_stage_silhouette_3d"]),
            "best_view_elev": float(crow["best_view_elev"]),
            "best_view_azim": float(crow["best_view_azim"]),
        }
        rows.append(row)

    out_df = pd.DataFrame(rows)
    out_df["narrative_zh"] = out_df.apply(narrative, axis=1)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.out, index=False)

    # compact summary for humans
    summary = args.out.with_name("triplet_stage_metrics_SUMMARY.md")
    lines = [
        "# Triplet stage-association metrics (primary) vs KMeans (control)",
        "",
        "Fit rule: logistic / multinomial on **train only**. Colors in 3D figures are pathology T stages.",
        "",
        "| triplet | family | T3+ AUC ext | Δ vs length | QWK ext | T2/T3 AUC ext | KMeans ARI ext |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for _, r in out_df.iterrows():
        lines.append(
            f"| `{r['triplet_id']}` | {r['family']} | {r['auc_T3plus_external']:.3f} | "
            f"{r['delta_ext_vs_length']:+.3f} | {r['qwk_4class_external']:.3f} | "
            f"{r['auc_T2vsT3_external']:.3f} | {r['test_external_kmeans_ari']:.3f} |"
        )
    lines += [
        "",
        "## Readout",
        "",
        "- Prefer pathology-stage panels and the metrics above; KMeans ARI≈0 means unsupervised clusters do not recover T stage.",
        "- Combinations **with clinical length** carry most T3+ discrimination; wall/dynamics triplets without length are supplementary.",
        "- L11 shows a clear T1→T4+ median trajectory on all three axes, but external T3+ AUC remains far below length-only.",
        "",
    ]
    summary.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "summary": str(summary), "n": len(out_df)}, indent=2))


if __name__ == "__main__":
    main()
