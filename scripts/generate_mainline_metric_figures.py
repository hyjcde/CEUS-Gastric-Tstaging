#!/usr/bin/env python3
"""Generate metric figures from mainline scoreboard + eval JSON (not manuscript exports).

Outputs to docs/mainline/figures/results/metric_*.png

  python scripts/generate_mainline_metric_figures.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT = PROJECT_ROOT / "docs" / "mainline" / "figures" / "results"
SCOREBOARD = PROJECT_ROOT / "pipeline" / "experiments" / "tables" / "tstaging_4class_mainline_scoreboard.csv"
TREE = PROJECT_ROOT / "pipeline" / "experiments" / "tree" / "gastric_tstage_4class"
BASELINE_REGISTRY = PROJECT_ROOT / "pipeline" / "experiments" / "mainlines" / "tstaging_4class" / "baseline_registry.yaml"

STAGE_EXPERIMENT = {
    "baseline_locked": "tstaging_4class_dual_v2_clinical22_full",
    "deploy_predicted_roi_clinical22": "tstaging_4class_dual_v2_predroi_clinical22_full",
    "structure_mask4ch_clinical22": "tstaging_4class_dual_v2_mask4ch_clinical22_full",
    "deploy_predicted_roi_mask4ch_clinical22": "tstaging_4class_dual_v2_predroi_mask4ch_clinical22_full",
    "breakthrough_regionaware_clinical22": "tstaging_4class_regionaware_clinical22_full",
    "wall_aux_mask4ch_clinical22": "tstaging_4class_dual_v2_mask4ch_wallaux_clinical22_full",
}

SHORT_LABEL = {
    "baseline_locked": "Baseline\nROI+Clinical",
    "deploy_predicted_roi_clinical22": "Pred ROI\n+Clinical",
    "structure_mask4ch_clinical22": "Mask4ch\n+Clinical ★",
    "deploy_predicted_roi_mask4ch_clinical22": "Pred ROI\n+Mask+Clinical",
    "breakthrough_regionaware_clinical22": "Region-aware\n+Clinical",
    "wall_aux_mask4ch_clinical22": "Mask4ch\n+Wall aux",
}

C_PROS = "#2166AC"
C_EXT = "#D6604D"
C_FROZEN = "#047857"
CLASSES = ["T1", "T2", "T3", "T4+"]

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.08,
    }
)


def load_scoreboard() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with SCOREBOARD.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("status") == "completed" and row.get("external_auc"):
                rows.append(row)
    return rows


def find_run_dir(experiment_name: str) -> Path | None:
    candidates: list[Path] = []
    if not TREE.is_dir():
        return None
    for p in TREE.rglob(f"{experiment_name}_*"):
        if p.is_dir() and (p / "eval" / "test_external" / "test_results.json").is_file():
            candidates.append(p)
    if not candidates:
        return None
    return max(candidates, key=lambda x: x.stat().st_mtime)


def load_eval(run_dir: Path, split: str) -> dict | None:
    path = run_dir / "eval" / split / "test_results.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def plot_confusion(ax, cm: np.ndarray, title: str) -> None:
    row_sum = cm.sum(axis=1, keepdims=True)
    row_sum[row_sum == 0] = 1
    norm = cm / row_sum
    im = ax.imshow(norm, vmin=0, vmax=1, cmap="Blues")
    ax.set_xticks(range(4))
    ax.set_yticks(range(4))
    ax.set_xticklabels(CLASSES)
    ax.set_yticklabels(CLASSES)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title(title, fontweight="bold", fontsize=9)
    for i in range(4):
        for j in range(4):
            v = norm[i, j]
            ax.text(
                j,
                i,
                f"{v:.2f}",
                ha="center",
                va="center",
                color="white" if v > 0.55 else "black",
                fontsize=7,
            )
    return im


def fig_auc_comparison(rows: list[dict]) -> None:
    labels, ext, pro, frozen_idx = [], [], [], None
    for i, row in enumerate(rows):
        sid = row["stage_id"]
        labels.append(SHORT_LABEL.get(sid, row["display_name"][:18]))
        ext.append(float(row["external_auc"]))
        pro.append(float(row["prospective_auc"]))
        if sid == "structure_mask4ch_clinical22":
            frozen_idx = i

    x = np.arange(len(labels))
    w = 0.36
    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.bar(x - w / 2, pro, w, label="Prospective (2025)", color=C_PROS, alpha=0.9)
    ax.bar(x + w / 2, ext, w, label="External (multi-center)", color=C_EXT, alpha=0.9)
    for bars, vals in zip(ax.containers, [pro, ext]):
        for bar, v in zip(bars, vals):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                v + 0.004,
                f"{v:.4f}",
                ha="center",
                va="bottom",
                fontsize=7,
                rotation=0,
            )
    if frozen_idx is not None:
        ax.axvspan(frozen_idx - 0.5, frozen_idx + 0.5, color=C_FROZEN, alpha=0.12, zorder=0)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Macro AUC (one-vs-rest)")
    ax.set_ylim(0.62, 0.78)
    ax.set_title("T-staging 4-class · Mainline scoreboard (full data + clinical 22D)", fontweight="bold")
    ax.legend(loc="upper left", fontsize=8)
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    fig.savefig(OUT / "metric_auc_comparison.png")
    plt.close(fig)


def fig_recall_heatmap(rows: list[dict]) -> None:
    labels, ext_r, pro_r = [], [], []
    for row in rows:
        sid = row["stage_id"]
        exp = STAGE_EXPERIMENT.get(sid)
        if not exp:
            continue
        run = find_run_dir(exp)
        if not run:
            continue
        re = load_eval(run, "test_external")
        rp = load_eval(run, "test_prospective")
        if not re or not rp:
            continue
        labels.append(SHORT_LABEL.get(sid, sid).replace("\n", " "))
        ext_r.append([re[f"recall_c{i}"] for i in range(4)])
        pro_r.append([rp[f"recall_c{i}"] for i in range(4)])
    if not labels:
        return

    fig, axes = plt.subplots(1, 2, figsize=(10, max(3.5, 0.35 * len(labels))))
    for ax, data, title in [
        (axes[0], np.array(pro_r), "Prospective"),
        (axes[1], np.array(ext_r), "External"),
    ]:
        im = ax.imshow(data, vmin=0, vmax=1, cmap="RdYlGn")
        ax.set_xticks(range(4))
        ax.set_xticklabels(CLASSES)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels, fontsize=8)
        ax.set_title(title, fontweight="bold")
        for i in range(len(labels)):
            for j in range(4):
                v = data[i, j]
                ax.text(
                    j,
                    i,
                    f"{v:.2f}",
                    ha="center",
                    va="center",
                    color="white" if v > 0.6 or v < 0.2 else "black",
                    fontsize=7,
                )
    fig.colorbar(im, ax=axes, shrink=0.6, label="Per-class recall")
    fig.suptitle("Per-class recall · eval JSON", fontweight="bold", y=1.02)
    fig.savefig(OUT / "metric_recall_heatmap.png")
    plt.close(fig)


def fig_comprehensive_panel(rows: list[dict], frozen_run: Path) -> None:
    fig = plt.figure(figsize=(12, 9))
    gs = GridSpec(2, 2, figure=fig, hspace=0.35, wspace=0.28)

    # (0,0) AUC bars — top 5 by external AUC
    ax0 = fig.add_subplot(gs[0, 0])
    sorted_rows = sorted(rows, key=lambda r: float(r["external_auc"]), reverse=True)[:5]
    labels = [SHORT_LABEL.get(r["stage_id"], r["stage_id"][:12]).replace("\n", " ") for r in sorted_rows]
    ext = [float(r["external_auc"]) for r in sorted_rows]
    pro = [float(r["prospective_auc"]) for r in sorted_rows]
    x = np.arange(len(labels))
    w = 0.35
    ax0.bar(x - w / 2, pro, w, color=C_PROS, label="Prospective")
    ax0.bar(x + w / 2, ext, w, color=C_EXT, label="External")
    ax0.set_xticks(x)
    ax0.set_xticklabels(labels, fontsize=7, rotation=15, ha="right")
    ax0.set_ylim(0.62, 0.78)
    ax0.set_ylabel("AUC")
    ax0.set_title("A) Mainline AUC (scoreboard)", fontweight="bold", loc="left")
    ax0.legend(fontsize=7)

    # (0,1) Training val AUC — frozen run
    ax1 = fig.add_subplot(gs[0, 1])
    hist_path = frozen_run / "training_history.csv"
    if hist_path.is_file():
        import pandas as pd

        hist = pd.read_csv(hist_path)
        ax1.plot(hist["epoch"], hist["val_auc"], color=C_FROZEN, lw=2, label="val AUC")
        best_i = hist["val_auc"].idxmax()
        ax1.scatter(
            [hist.loc[best_i, "epoch"]],
            [hist.loc[best_i, "val_auc"]],
            color=C_FROZEN,
            s=40,
            zorder=5,
        )
        ax1.set_xlabel("Epoch")
        ax1.set_ylabel("Validation AUC")
        ax1.set_title("B) Frozen line training (mask4ch+clinical)", fontweight="bold", loc="left")
        ax1.legend(fontsize=7)
        ax1.grid(True, alpha=0.3)
    else:
        ax1.text(0.5, 0.5, "No training_history.csv", ha="center", va="center")
        ax1.set_axis_off()

    # (1,0)(1,1) Confusion — frozen eval JSON
    re = load_eval(frozen_run, "test_external")
    rp = load_eval(frozen_run, "test_prospective")
    ax2 = fig.add_subplot(gs[1, 0])
    ax3 = fig.add_subplot(gs[1, 1])
    if re and "confusion_matrix" in re:
        plot_confusion(ax2, np.array(re["confusion_matrix"]), "C) External · row-normalized CM")
    if rp and "confusion_matrix" in rp:
        plot_confusion(ax3, np.array(rp["confusion_matrix"]), "D) Prospective · row-normalized CM")

    fig.suptitle(
        "Frozen Agent default: mask4ch + clinical22 (structure_mask4ch_clinical22)",
        fontsize=11,
        fontweight="bold",
        y=0.98,
    )
    fig.savefig(OUT / "metric_comprehensive_panel.png")
    plt.close(fig)


def fig_per_class_recall_curves(frozen_run: Path) -> None:
    """Bar chart: per-class recall external vs prospective for frozen line."""
    re = load_eval(frozen_run, "test_external")
    rp = load_eval(frozen_run, "test_prospective")
    if not re or not rp:
        return
    ext = [re[f"recall_c{i}"] for i in range(4)]
    pro = [rp[f"recall_c{i}"] for i in range(4)]
    x = np.arange(4)
    w = 0.35
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(x - w / 2, pro, w, label="Prospective", color=C_PROS)
    ax.bar(x + w / 2, ext, w, label="External", color=C_EXT)
    ax.set_xticks(x)
    ax.set_xticklabels(CLASSES)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Recall")
    ax.set_title("Per-class recall · frozen mask4ch+clinical22", fontweight="bold")
    ax.legend()
    for bars, vals in zip(ax.containers, [pro, ext]):
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, v + 0.02, f"{v:.2f}", ha="center", fontsize=8)
    fig.savefig(OUT / "metric_per_class_recall_curves.png")
    plt.close(fig)


def fig_confusion_dual(frozen_run: Path) -> None:
    re = load_eval(frozen_run, "test_external")
    rp = load_eval(frozen_run, "test_prospective")
    if not re or not rp:
        return
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.8))
    plot_confusion(axes[0], np.array(re["confusion_matrix"]), "External")
    plot_confusion(axes[1], np.array(rp["confusion_matrix"]), "Prospective")
    fig.suptitle("Confusion matrices · frozen line", fontweight="bold")
    fig.savefig(OUT / "metric_confusion_dual.png")
    plt.close(fig)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_scoreboard()
    frozen_run = find_run_dir(STAGE_EXPERIMENT["structure_mask4ch_clinical22"])
    if frozen_run is None:
        raise SystemExit("Frozen run dir not found for mask4ch+clinical22")

    fig_auc_comparison(rows)
    fig_recall_heatmap(rows)
    fig_comprehensive_panel(rows, frozen_run)
    fig_per_class_recall_curves(frozen_run)
    fig_confusion_dual(frozen_run)

    # Small CM-only exports used in HTML
    for split, name in [("test_external", "metric_cm_external.png"), ("test_prospective", "metric_cm_prospective.png")]:
        ev = load_eval(frozen_run, split)
        if not ev:
            continue
        fig, ax = plt.subplots(figsize=(3.5, 3.2))
        plot_confusion(ax, np.array(ev["confusion_matrix"]), split.replace("test_", ""))
        fig.savefig(OUT / name)
        plt.close(fig)

    meta = {
        "frozen_run": str(frozen_run.relative_to(PROJECT_ROOT)),
        "scoreboard_rows": len(rows),
        "source": "pipeline scoreboard + eval/test_results.json",
    }
    (OUT / "metric_figures_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote metric figures to {OUT} (frozen: {frozen_run.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
