#!/usr/bin/env python3
"""Patient-level models on GC-US T-score feature pack v1.

Train on `train`, evaluate on val / test_prospective / test_external.
Ablations isolate length/size leakage vs shape/margin signal.

Outputs:
  pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/feature_pack_models_v1/
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    cohen_kappa_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACK = PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1/feature_pack_v1/patient_features.csv"
OUT = (
    PROJECT_ROOT
    / "pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/feature_pack_models_v1"
)

SPLITS = ["train", "val", "test_prospective", "test_external"]

MODELS: dict[str, list[str]] = {
    "A_length_only": ["tumor_length_cm"],
    "B_size_only": ["tumor_length_cm", "morph_perimeter_px", "morph_area_px"],
    "C_shape_core": [
        "morph_peak_sharpness_max",
        "morph_solidity",
        "morph_circularity",
        "morph_concavity_ratio",
        "morph_nrl_roughness",
    ],
    "D_shape_plus_length": [
        "tumor_length_cm",
        "morph_peak_sharpness_max",
        "morph_solidity",
        "morph_circularity",
        "morph_concavity_ratio",
        "morph_nrl_roughness",
    ],
    "E_margin_core": [
        "margin_spic_robust",
        "margin_shape_solidity",
        "margin_shape_fd_high",
    ],
    "F_shape_margin": [
        "morph_peak_sharpness_max",
        "morph_solidity",
        "morph_circularity",
        "morph_concavity_ratio",
        "morph_nrl_roughness",
        "margin_spic_robust",
        "margin_shape_solidity",
        "margin_shape_fd_high",
    ],
    "G_shape_margin_length": [
        "tumor_length_cm",
        "morph_peak_sharpness_max",
        "morph_solidity",
        "morph_circularity",
        "morph_concavity_ratio",
        "morph_nrl_roughness",
        "margin_spic_robust",
        "margin_shape_solidity",
        "margin_shape_fd_high",
    ],
    "H_pack_full": [
        "tumor_length_cm",
        "morph_perimeter_px",
        "morph_area_px",
        "morph_peak_sharpness_max",
        "morph_solidity",
        "morph_circularity",
        "morph_concavity_ratio",
        "morph_nrl_roughness",
        "margin_spic_robust",
        "margin_shape_solidity",
        "margin_shape_fd_high",
        "margin_bof_high_mean",
        "margin_clear_robust",
        "bt_v2_max_outward_depth",
        "growth_outward_protrusion_ratio__max",
        "seg_irregularity",
    ],
    "I_seg_irregularity": ["seg_irregularity"],
    "J_seg_plus_length": ["tumor_length_cm", "seg_irregularity"],
}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pack", type=Path, default=PACK)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    return ap.parse_args()


def make_clf() -> Pipeline:
    clf = LogisticRegression(
        max_iter=2000,
        class_weight="balanced",
        solver="lbfgs",
    )
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("clf", clf),
        ]
    )


def auc_binary(y_true: np.ndarray, score: np.ndarray) -> float:
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(roc_auc_score(y_true, score))


def auc_ovr_macro(y_true: np.ndarray, proba: np.ndarray, labels: list[int]) -> float:
    if len(np.unique(y_true)) < 2:
        return float("nan")
    try:
        return float(
            roc_auc_score(y_true, proba, multi_class="ovr", average="macro", labels=labels)
        )
    except ValueError:
        return float("nan")


def apply_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
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
    args = parse_args()
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    apply_style()

    df = pd.read_csv(args.pack)
    df["patient_id"] = df["patient_id"].astype(str)
    df["label"] = pd.to_numeric(df["label"], errors="coerce")
    df = df[df["eval_split"].isin(SPLITS) & df["label"].notna()].copy()
    df["y_t3plus"] = (df["label"] >= 2).astype(int)

    train = df[df["eval_split"] == "train"]
    rows = []
    coef_rows = []
    pred_frames = []

    for model_name, feats in MODELS.items():
        Xtr = train[feats]
        ytr_bin = train["y_t3plus"].to_numpy()
        ytr_mc = train["label"].astype(int).to_numpy()

        pipe_bin = make_clf()
        pipe_mc = make_clf()
        pipe_bin.fit(Xtr, ytr_bin)
        pipe_mc.fit(Xtr, ytr_mc)

        # coefficients (binary, scaled space)
        clf = pipe_bin.named_steps["clf"]
        for f, c in zip(feats, clf.coef_.ravel()):
            coef_rows.append({"model": model_name, "feature": f, "coef_binary_T3plus": float(c)})

        for split in SPLITS:
            sub = df[df["eval_split"] == split]
            X = sub[feats]
            y_bin = sub["y_t3plus"].to_numpy()
            y_mc = sub["label"].astype(int).to_numpy()
            score = pipe_bin.predict_proba(X)[:, 1]
            pred_bin = pipe_bin.predict(X)
            proba_mc = pipe_mc.predict_proba(X)
            pred_mc = pipe_mc.predict(X)
            labels = sorted(pipe_mc.named_steps["clf"].classes_.tolist())

            rows.append(
                {
                    "model": model_name,
                    "n_features": len(feats),
                    "split": split,
                    "n": int(len(sub)),
                    "auc_T3plus": auc_binary(y_bin, score),
                    "acc_T3plus": float(accuracy_score(y_bin, pred_bin)),
                    "auc_multiclass_ovr_macro": auc_ovr_macro(y_mc, proba_mc, labels),
                    "acc_4class": float(accuracy_score(y_mc, pred_mc)),
                    "qwk_4class": float(
                        cohen_kappa_score(y_mc, pred_mc, weights="quadratic")
                    ),
                    "spearman_score_vs_T": float(
                        pd.Series(score).corr(pd.Series(y_mc), method="spearman")
                    ),
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
    coef = pd.DataFrame(coef_rows)
    preds = pd.concat(pred_frames, ignore_index=True)
    res.to_csv(out / "metrics_by_split.csv", index=False)
    coef.to_csv(out / "coefficients_binary.csv", index=False)
    preds.to_csv(out / "predictions.csv", index=False)

    # pivot for summary
    pivot = res.pivot(index="model", columns="split", values="auc_T3plus")
    pivot = pivot.reindex(columns=SPLITS)
    pivot.to_csv(out / "auc_T3plus_pivot.csv")

    # plot AUC heatmap-like bars for key models
    key = [
        "A_length_only",
        "B_size_only",
        "C_shape_core",
        "D_shape_plus_length",
        "F_shape_margin",
        "G_shape_margin_length",
        "H_pack_full",
        "I_seg_irregularity",
        "J_seg_plus_length",
    ]
    colors = {
        "train": "#4C78A8",
        "val": "#72B7B2",
        "test_prospective": "#F58518",
        "test_external": "#E45756",
    }
    fig, ax = plt.subplots(figsize=(11, 4.6))
    x0 = np.arange(len(key))
    width = 0.18
    for i, sp in enumerate(SPLITS):
        vals = [
            float(res[(res.model == m) & (res.split == sp)]["auc_T3plus"].iloc[0]) for m in key
        ]
        ax.bar(
            x0 + (i - 1.5) * width,
            vals,
            width=width,
            color=colors[sp],
            label=sp,
            edgecolor="white",
            linewidth=0.3,
        )
    ax.axhline(0.5, color="#888", ls="--", lw=0.8)
    ax.set_xticks(x0)
    ax.set_xticklabels(key, rotation=28, ha="right")
    ax.set_ylim(0.4, 0.9)
    ax.set_ylabel("AUC (T3+ vs T1–T2)")
    ax.set_title("Feature-pack models · train-fit, evaluate by split")
    ax.legend(fontsize=7, framealpha=0.25, ncol=4, loc="lower right")
    fig.tight_layout()
    fig.savefig(out / "00_auc_t3plus_by_model_split.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    # QWK bars for shape±length
    key2 = ["A_length_only", "C_shape_core", "D_shape_plus_length", "G_shape_margin_length", "H_pack_full", "J_seg_plus_length"]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    x0 = np.arange(len(key2))
    for i, sp in enumerate(SPLITS):
        vals = [
            float(res[(res.model == m) & (res.split == sp)]["qwk_4class"].iloc[0]) for m in key2
        ]
        ax.bar(
            x0 + (i - 1.5) * width,
            vals,
            width=width,
            color=colors[sp],
            label=sp,
            edgecolor="white",
            linewidth=0.3,
        )
    ax.set_xticks(x0)
    ax.set_xticklabels(key2, rotation=25, ha="right")
    ax.set_ylabel("Quadratic weighted κ (4-class)")
    ax.set_title("Ordinal agreement by split")
    ax.legend(fontsize=7, framealpha=0.25, ncol=4)
    fig.tight_layout()
    fig.savefig(out / "00_qwk_by_model_split.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    # delta vs length-only on held-out
    lines = [
        "# Feature pack v1 · patient-level models",
        "",
        "Classifier: balanced logistic regression (median impute + z-score fitted on **train only**).",
        "Tasks: binary T3+ vs T1–T2; multinomial 4-class.",
        "",
        "## AUC T3+ by split",
        "",
        "| model | train | val | prosp | external | Δext vs length |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    base_ext = float(
        res[(res.model == "A_length_only") & (res.split == "test_external")]["auc_T3plus"].iloc[0]
    )
    for m in MODELS:
        cells = []
        for sp in SPLITS:
            v = float(res[(res.model == m) & (res.split == sp)]["auc_T3plus"].iloc[0])
            cells.append(f"{v:.3f}")
        ext = float(
            res[(res.model == m) & (res.split == "test_external")]["auc_T3plus"].iloc[0]
        )
        lines.append(f"| `{m}` | " + " | ".join(cells) + f" | {ext - base_ext:+.3f} |")

    lines += [
        "",
        "## QWK 4-class (selected)",
        "",
        "| model | train | val | prosp | external |",
        "|---|---:|---:|---:|---:|",
    ]
    for m in key2:
        cells = [
            f"{float(res[(res.model == m) & (res.split == sp)]['qwk_4class'].iloc[0]):.3f}"
            for sp in SPLITS
        ]
        lines.append(f"| `{m}` | " + " | ".join(cells) + " |")

    # interpret
    best_ext = res[res.split == "test_external"].sort_values("auc_T3plus", ascending=False).iloc[0]
    best_prosp = (
        res[res.split == "test_prospective"].sort_values("auc_T3plus", ascending=False).iloc[0]
    )
    shape_ext = float(
        res[(res.model == "C_shape_core") & (res.split == "test_external")]["auc_T3plus"].iloc[0]
    )
    shape_len_ext = float(
        res[(res.model == "D_shape_plus_length") & (res.split == "test_external")][
            "auc_T3plus"
        ].iloc[0]
    )
    lines += [
        "",
        "## Readout",
        "",
        f"- Best external AUC: `{best_ext['model']}` = {best_ext['auc_T3plus']:.3f}",
        f"- Best prospective AUC: `{best_prosp['model']}` = {best_prosp['auc_T3plus']:.3f}",
        f"- Shape-only external AUC = {shape_ext:.3f}; shape+length = {shape_len_ext:.3f}; "
        f"length-only = {base_ext:.3f}",
        f"- Shape incremental over length on external: {shape_len_ext - base_ext:+.3f}",
        "",
        "Figures: `00_auc_t3plus_by_model_split.png`, `00_qwk_by_model_split.png`",
        "",
        "Rebuild: `python3 scripts/eval_gc_us_tscore_feature_pack_models_v1.py`",
        "",
    ]
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = {
        "n_by_split": df["eval_split"].value_counts().astype(int).to_dict(),
        "best_external": best_ext.to_dict(),
        "best_prospective": best_prosp.to_dict(),
        "auc_pivot": pivot.reset_index().to_dict(orient="records"),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    print(res[res.model.isin(key)][["model", "split", "auc_T3plus", "qwk_4class"]].to_string(index=False))


if __name__ == "__main__":
    main()
