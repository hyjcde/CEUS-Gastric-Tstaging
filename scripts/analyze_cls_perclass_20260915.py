#!/usr/bin/env python3
"""Per-class analysis of T-staging ROI LoRA+MLP models (official / aggressive / gentle)
across val / prospective / external / zml100, with confusion matrices and doctor reference.

Outputs:
  - per-class recall grouped-bar figure (4 panels)
  - patient-level confusion-matrix figure for the gentle run (4 panels)
  - analysis_summary.json with the numbers behind the "why is ACC low" read
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix

ROOT = Path("/data/research/gastric/GastricTstaging")
CLS = ROOT / "pipeline/experiments/reports/dinov3_roi_lora_mlp"
RUNS = {
    "Official": CLS / "phase0_20260828_full",
    "Aggressive": CLS / "us_ssl_v1_20260914",
    "Gentle": CLS / "us_ssl_v2_gentle_20260915",
}
SPLITS = {"Val": "val", "Prospective": "test_prospective", "External": "test_external"}
ZML_DIR = CLS / "zml100_eval_20260915"
OUT = ROOT / "pipeline/experiments/reports/dinov3_roi_lora_mlp/perclass_analysis_20260915"
OUT.mkdir(parents=True, exist_ok=True)

CLASSES = ["T1", "T2", "T3", "T4+"]
PROB_COLS = [f"prob_{c}" for c in CLASSES]
COLORS = {"Official": "#6b7280", "Aggressive": "#d97706", "Gentle": "#2563eb"}


def patient_case_df(frame_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(frame_csv, low_memory=False)
    g = df.groupby("patient_id", sort=False)
    out = g[PROB_COLS].mean()
    out["class_label"] = g["class_label"].first()
    out["pred"] = out[PROB_COLS].to_numpy().argmax(axis=1)
    return out.reset_index()


def per_class(cm: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    recall = np.diag(cm) / np.maximum(cm.sum(axis=1), 1)
    return recall, cm


summary: dict[str, object] = {}

# ---- collect per-model per-split stats -------------------------------------
data: dict[str, dict[str, pd.DataFrame]] = {}
for model_name, run_dir in RUNS.items():
    data[model_name] = {}
    for split_name, split_tag in SPLITS.items():
        case_df = patient_case_df(run_dir / f"{split_tag}_frame_predictions.csv")
        data[model_name][split_name] = case_df
    data[model_name]["ZML100"] = pd.read_csv(ZML_DIR / f"zml100_{model_name.lower()}_case_predictions.csv")

stats: dict[str, dict[str, dict[str, list]]] = {}
for model_name in RUNS:
    stats[model_name] = {}
    for split_name in list(SPLITS) + ["ZML100"]:
        df = data[model_name][split_name]
        cm = confusion_matrix(df["class_label"], df["pred"], labels=[0, 1, 2, 3])
        recall, cm = per_class(cm)
        acc = float((df["class_label"] == df["pred"]).mean())
        err = df[df["class_label"] != df["pred"]]
        adj = float((np.abs(err["class_label"] - err["pred"]) == 1).mean()) if len(err) else 0.0
        stats[model_name][split_name] = {
            "recall": recall.tolist(), "cm": cm.tolist(), "acc": acc,
            "n": int(len(df)), "adjacent_error_share": adj,
            "support": cm.sum(axis=1).tolist(),
        }

# doctor on zml100
zml_summary = json.loads((ZML_DIR / "zml100_summary.json").read_text())
doc = zml_summary["doctor_zml"]
stats["Doctor (zml)"] = {"ZML100": {
    "recall": [doc["per_class_recall"][c] for c in CLASSES],
    "cm": doc["confusion"], "acc": doc["case_acc"], "n": doc["n_cases"],
    "adjacent_error_share": None, "support": np.array(doc["confusion"]).sum(axis=1).tolist(),
}}

summary["stats"] = stats
summary["zml100_all"] = zml_summary

# ---- Fig 1: per-class recall, 4 panels --------------------------------------
panel_splits = ["Val", "Prospective", "External", "ZML100"]
fig, axes = plt.subplots(1, 4, figsize=(13.2, 3.6), sharey=True)
width = 0.26
x = np.arange(4)
for ax, split_name in zip(axes, panel_splits):
    for mi, model_name in enumerate(RUNS):
        r = stats[model_name][split_name]["recall"]
        bars = ax.bar(x + (mi - 1) * width, r, width * 0.9, color=COLORS[model_name],
                      label=model_name, zorder=3)
        for b, v in zip(bars, r):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.2f}", ha="center",
                    va="bottom", fontsize=6.5, color=COLORS[model_name])
    if split_name == "ZML100":
        dr = stats["Doctor (zml)"]["ZML100"]["recall"]
        ax.scatter(x + 1.5 * width, dr, marker="D", s=26, color="black", zorder=5,
                   label="Doctor (zml)")
    accs = " / ".join(f"{stats[m][split_name]['acc']:.2f}" for m in RUNS)
    n = stats["Gentle"][split_name]["n"]
    ax.set_title(f"{split_name} (n={n})\nACC off./agr./gen. = {accs}", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(CLASSES, fontsize=9)
    ax.set_ylim(0, 1.0)
    ax.grid(axis="y", alpha=0.3, zorder=0)
    ax.tick_params(labelsize=8)
axes[0].set_ylabel("Case-level recall", fontsize=9)
handles, labels = axes[0].get_legend_handles_labels()
handles2, labels2 = axes[3].get_legend_handles_labels()
fig.legend(handles + [h for h in handles2 if h not in handles],
           labels + [l for l, h in zip(labels2, handles2) if h not in handles],
           loc="upper center", ncol=4, frameon=False, fontsize=9, bbox_to_anchor=(0.5, 1.08))
pass  # title carried by panel headers
fig.tight_layout()
fig.savefig(OUT / "fig_perclass_recall_4sets.png", dpi=300, bbox_inches="tight")
fig.savefig(OUT / "fig_perclass_recall_4sets.pdf", bbox_inches="tight")
plt.close(fig)

# ---- Fig 2: gentle confusion matrices ---------------------------------------
fig, axes = plt.subplots(1, 4, figsize=(13.2, 3.4))
for ax, split_name in zip(axes, panel_splits):
    cm = np.array(stats["Gentle"][split_name]["cm"], dtype=float)
    cmn = cm / np.maximum(cm.sum(axis=1, keepdims=True), 1)
    im = ax.imshow(cmn, cmap="Blues", vmin=0, vmax=1)
    for i in range(4):
        for j in range(4):
            ax.text(j, i, f"{cmn[i, j]:.2f}\n({int(cm[i, j])})", ha="center", va="center",
                    fontsize=7, color="white" if cmn[i, j] > 0.55 else "black")
    ax.set_xticks(range(4)); ax.set_yticks(range(4))
    ax.set_xticklabels(CLASSES, fontsize=8); ax.set_yticklabels(CLASSES, fontsize=8)
    ax.set_xlabel("Predicted", fontsize=8)
    if ax is axes[0]:
        ax.set_ylabel("True", fontsize=8)
    ax.set_title(f"{split_name} (n={int(cm.sum())})", fontsize=9)
fig.suptitle("Gentle (us_ssl_v2) case-level confusion matrices (row-normalized recall, counts in parentheses)", fontsize=10)
fig.tight_layout(rect=[0, 0, 1, 0.94])
fig.savefig(OUT / "fig_gentle_confusion_4sets.png", dpi=300, bbox_inches="tight")
fig.savefig(OUT / "fig_gentle_confusion_4sets.pdf", bbox_inches="tight")
plt.close(fig)

(OUT / "analysis_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

# ---- console digest ----------------------------------------------------------
print("=== ACC / adjacent-error share ===")
for m in list(RUNS) + ["Doctor (zml)"]:
    for s in panel_splits:
        st = stats[m].get(s)
        if st is None:
            continue
        adj = st["adjacent_error_share"]
        print(f"{m:14s} {s:12s} acc={st['acc']:.3f} n={st['n']:5d} adj_err={adj if adj is None else round(adj, 3)}")
print("\n=== support (true-class counts, patient level) ===")
for s in panel_splits:
    print(f"{s:12s}", dict(zip(CLASSES, stats["Gentle"][s]["support"])))
print("\n=== gentle per-class recall ===")
for s in panel_splits:
    print(f"{s:12s}", dict(zip(CLASSES, [round(v, 3) for v in stats["Gentle"][s]["recall"]])))
print(f"\nfigures + summary -> {OUT}")
