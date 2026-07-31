#!/usr/bin/env python3
"""
Generate publication-quality figures for the Agent paper.

Figures:
  1. Ablation comparison bar chart (balanced accuracy, F1, T2/T3 confusion)
  2. Confusion matrix comparison (baseline vs agent)
  3. ReAct trace example (step-by-step diagram)
  4. RAG effect on T2/T3 cases

Usage:
  python pipeline/agent/evaluation/generate_figures.py \\
    --summary pipeline/experiments/agent_eval/ablation_summary.json \\
    --output pipeline/experiments/agent_eval/figures/
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent.figures")

# Publication style
plt.rcParams.update({
    "font.size": 11,
    "font.family": "sans-serif",
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 9,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
})

COLORBLIND_PALETTE = [
    "#0072B2",  # blue
    "#E69F00",  # orange
    "#009E73",  # green
    "#D55E00",  # red-orange
    "#CC79A7",  # pink
    "#56B4E9",  # light blue
    "#F0E442",  # yellow
]


def fig_ablation_comparison(summaries: List[Dict], output_dir: Path) -> None:
    """Bar chart comparing ablation conditions."""
    if not summaries:
        logger.warning("No summaries for ablation comparison")
        return

    # Group by split
    splits = sorted(set(s["split"] for s in summaries))

    for split in splits:
        split_data = [s for s in summaries if s["split"] == split]
        if not split_data:
            continue

        methods = [s["ablation"] for s in split_data]
        bal_acc = [s.get("balanced_accuracy", 0) for s in split_data]
        f1 = [s.get("f1_macro", 0) for s in split_data]
        t2t3 = [s.get("t2t3_confusion_rate", 0) for s in split_data]

        x = np.arange(len(methods))
        width = 0.25

        fig, ax = plt.subplots(figsize=(10, 5))
        bars1 = ax.bar(x - width, bal_acc, width, label="Balanced Acc",
                        color=COLORBLIND_PALETTE[0], alpha=0.85)
        bars2 = ax.bar(x, f1, width, label="F1-Macro",
                        color=COLORBLIND_PALETTE[1], alpha=0.85)
        bars3 = ax.bar(x + width, t2t3, width, label="T2/T3 Confusion",
                        color=COLORBLIND_PALETTE[3], alpha=0.85)

        ax.set_xlabel("Method")
        ax.set_ylabel("Score")
        ax.set_title(f"Ablation Comparison — {split}")
        ax.set_xticks(x)
        ax.set_xticklabels(methods, rotation=30, ha="right")
        ax.legend()
        ax.set_ylim(0, 1.05)
        ax.grid(axis="y", alpha=0.3)

        # Add value labels
        for bars in [bars1, bars2, bars3]:
            for bar in bars:
                height = bar.get_height()
                if height > 0:
                    ax.text(bar.get_x() + bar.get_width() / 2., height + 0.01,
                            f"{height:.3f}", ha="center", va="bottom",
                            fontsize=7)

        fig.tight_layout()
        fig.savefig(output_dir / f"ablation_comparison_{split}.pdf")
        fig.savefig(output_dir / f"ablation_comparison_{split}.png")
        plt.close(fig)
        logger.info("Saved ablation_comparison_%s.pdf", split)


def fig_confusion_matrix(summaries: List[Dict], output_dir: Path) -> None:
    """Side-by-side confusion matrices for baseline vs agent."""
    CLASS_NAMES = ["T1", "T2", "T3", "T4+"]

    # Find baseline and agent for the same split
    for split in set(s["split"] for s in summaries):
        baseline = next((s for s in summaries
                          if s["split"] == split
                          and "baseline" in s["ablation"]), None)
        agent = next((s for s in summaries
                       if s["split"] == split
                       and s["ablation"] == "agent_full"), None)

        to_plot = []
        if baseline and "confusion_matrix" in baseline:
            to_plot.append(("Baseline-Avg", baseline))
        if agent and "confusion_matrix" in agent:
            to_plot.append(("Agent-Full", agent))

        if not to_plot:
            continue

        fig, axes = plt.subplots(1, len(to_plot),
                                  figsize=(5 * len(to_plot), 4.5))
        if len(to_plot) == 1:
            axes = [axes]

        for ax, (title, data) in zip(axes, to_plot):
            cm = np.array(data["confusion_matrix"])
            # Normalise by row
            row_sums = cm.sum(axis=1, keepdims=True)
            row_sums[row_sums == 0] = 1
            cm_norm = cm / row_sums

            im = ax.imshow(cm_norm, interpolation="nearest",
                            cmap="Blues", vmin=0, vmax=1)
            ax.set_title(f"{title}\n({split})")
            ax.set_xlabel("Predicted")
            ax.set_ylabel("True")

            ticks = list(range(len(CLASS_NAMES)))
            ax.set_xticks(ticks)
            ax.set_yticks(ticks)
            ax.set_xticklabels(CLASS_NAMES)
            ax.set_yticklabels(CLASS_NAMES)

            # Annotate
            for i in range(cm.shape[0]):
                for j in range(cm.shape[1]):
                    color = "white" if cm_norm[i, j] > 0.5 else "black"
                    ax.text(j, i, f"{cm[i, j]}\n({cm_norm[i, j]:.2f})",
                            ha="center", va="center", color=color,
                            fontsize=8)

        fig.tight_layout()
        fig.savefig(output_dir / f"confusion_matrix_{split}.pdf")
        fig.savefig(output_dir / f"confusion_matrix_{split}.png")
        plt.close(fig)
        logger.info("Saved confusion_matrix_%s.pdf", split)


def fig_react_trace_example(output_dir: Path) -> None:
    """
    Generate a stylised ReAct trace diagram for a sample case.

    This creates a schematic figure showing the step-by-step
    reasoning process of the agent.
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 8)
    ax.axis("off")
    ax.set_title("ReAct Agent Trace Example — T2/T3 Borderline Case",
                  fontsize=13, fontweight="bold", pad=15)

    steps = [
        ("Step 1", "Thought", "Check quality of 3 frames",
         "quality_check", "frame_0: 0.78, frame_1: 0.85, frame_2: 0.42",
         COLORBLIND_PALETTE[0]),
        ("Step 2", "Thought", "Segment usable frames (0, 1)",
         "segment", "mask available, area_ratio: 0.08, 0.12",
         COLORBLIND_PALETTE[1]),
        ("Step 3", "Thought", "Classify with dual-branch model",
         "classify", "T2: 0.38, T3: 0.35, uncertainty: 0.97",
         COLORBLIND_PALETTE[2]),
        ("Step 4", "Thought", "High uncertainty → check morphology",
         "morphology", "irregularity: 0.65, solidity: 0.82",
         COLORBLIND_PALETTE[3]),
        ("Step 5", "Thought", "T2/T3 borderline → retrieve similar cases",
         "retrieve_similar", "similar: 3×T3, 2×T2",
         COLORBLIND_PALETTE[4]),
        ("Step 6", "Thought", "Evidence favours T3 with moderate confidence",
         "FINISH", "predicted=T3, confidence=medium",
         COLORBLIND_PALETTE[5]),
    ]

    y_start = 7.2
    for i, (step, phase, thought, action, obs, color) in enumerate(steps):
        y = y_start - i * 1.15

        # Step label
        ax.text(0.3, y, step, fontsize=9, fontweight="bold", va="center",
                bbox=dict(boxstyle="round,pad=0.2", facecolor=color,
                          alpha=0.3, edgecolor=color))

        # Thought
        ax.text(2.0, y + 0.15, f"[Think] {thought}", fontsize=8, va="center",
                style="italic", color="#555")

        # Action
        ax.text(2.0, y - 0.15, f"-> {action}()", fontsize=8, va="center",
                fontweight="bold", color=color)

        # Observation
        ax.text(6.5, y, f"[Obs] {obs}", fontsize=7.5, va="center",
                color="#333",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="#f0f0f0",
                          edgecolor="#ccc"))

        # Arrow to next step
        if i < len(steps) - 1:
            ax.annotate("", xy=(0.5, y - 0.55), xytext=(0.5, y - 0.35),
                         arrowprops=dict(arrowstyle="->", color="#999", lw=0.8))

    fig.tight_layout()
    fig.savefig(output_dir / "react_trace_example.pdf")
    fig.savefig(output_dir / "react_trace_example.png")
    plt.close(fig)
    logger.info("Saved react_trace_example.pdf")


def fig_ablation_table_latex(summaries: List[Dict], output_dir: Path) -> None:
    """Generate a LaTeX table for the ablation results."""
    if not summaries:
        return

    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Ablation study results. BalAcc = balanced accuracy, "
        r"F1 = macro F1-score, T2/T3 = T2/T3 confusion rate.}",
        r"\label{tab:ablation}",
        r"\begin{tabular}{lccccc}",
        r"\toprule",
        r"Method & Split & BalAcc & F1 & T2/T3 Conf. & N \\",
        r"\midrule",
    ]

    for s in summaries:
        name = s["ablation"].replace("_", r"\_")
        split = s["split"].replace("_", r"\_")
        ba = f"{s.get('balanced_accuracy', 0):.4f}"
        f1 = f"{s.get('f1_macro', 0):.4f}"
        t2t3 = f"{s.get('t2t3_confusion_rate', 0):.4f}"
        n = str(s.get("n_patients", 0))
        lines.append(f"{name} & {split} & {ba} & {f1} & {t2t3} & {n} \\\\")

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])

    with open(output_dir / "ablation_table.tex", "w") as f:
        f.write("\n".join(lines))
    logger.info("Saved ablation_table.tex")


def main():
    parser = argparse.ArgumentParser(description="Generate agent figures")
    parser.add_argument("--summary", type=str,
                        default="pipeline/experiments/agent_eval/ablation_summary.json")
    parser.add_argument("--output", type=str,
                        default="pipeline/experiments/agent_eval/figures/")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = Path(args.summary)
    summaries = []
    if summary_path.exists():
        with open(summary_path) as f:
            summaries = json.load(f)
    else:
        logger.warning("Summary file not found: %s", summary_path)

    if summaries:
        fig_ablation_comparison(summaries, output_dir)
        fig_confusion_matrix(summaries, output_dir)
        fig_ablation_table_latex(summaries, output_dir)

    # Always generate the trace example (it's schematic)
    fig_react_trace_example(output_dir)

    logger.info("All figures saved to %s", output_dir)


if __name__ == "__main__":
    main()
