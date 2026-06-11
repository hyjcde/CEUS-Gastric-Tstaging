#!/usr/bin/env python3
"""
Make the screening funnel figure for the LDH manuscript.

Reads counts from the screened contract summaries + raw source CSVs:
  - pipeline/data/tstaging_4class_screened_latest_20260528/screened_build_summary.json
  - pipeline/data/tstaging_4class_screened_latest_external_2966_20260529/test_external_with_reject_flag.csv
  - pipeline/data/tstaging_4class_prospective_full/test_prospective_full.csv
  - pipeline/data/tstaging_4class_screened_eval_20260531/dataset_summary.json

Writes:
  docs/paper_drafts/tex_v2_ldh/figures/figure_screening_funnel.png
  docs/paper_drafts/tex_v2_ldh/figures/figure_screening_funnel.csv  (audit numbers)
  docs/paper_drafts/tex_v2_ldh/tab_screening_funnel.csv             (markdown table)

Per python-scripts rule: argparse + Path(__file__).parents[1] + no hardcoded media.
Uses matplotlib (already in env, used by other scripts).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCREEN_SUMMARY = (
    REPO_ROOT
    / "pipeline/data/tstaging_4class_screened_latest_20260528/screened_build_summary.json"
)
DEFAULT_EXT_CSV = (
    REPO_ROOT
    / "pipeline/data/tstaging_4class_screened_latest_external_2966_20260529/test_external_with_reject_flag.csv"
)
DEFAULT_PRO_CSV = (
    REPO_ROOT / "pipeline/data/tstaging_4class_prospective_full/test_prospective_full.csv"
)
DEFAULT_EVAL_SUMMARY = (
    REPO_ROOT / "pipeline/data/tstaging_4class_screened_eval_20260531/dataset_summary.json"
)
DEFAULT_OUT_PNG = (
    REPO_ROOT
    / "docs/paper_drafts/tex_v2_ldh/figures/figure_screening_funnel.png"
)
DEFAULT_OUT_CSV = (
    REPO_ROOT
    / "docs/paper_drafts/tex_v2_ldh/figures/figure_screening_funnel.csv"
)
DEFAULT_OUT_TAB = (
    REPO_ROOT
    / "docs/paper_drafts/tex_v2_ldh/tab_screening_funnel.csv"
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build the screening funnel figure.")
    p.add_argument("--screen-summary", type=Path, default=DEFAULT_SCREEN_SUMMARY)
    p.add_argument("--ext-csv", type=Path, default=DEFAULT_EXT_CSV)
    p.add_argument("--pro-csv", type=Path, default=DEFAULT_PRO_CSV)
    p.add_argument("--eval-summary", type=Path, default=DEFAULT_EVAL_SUMMARY)
    p.add_argument("--out-png", type=Path, default=DEFAULT_OUT_PNG)
    p.add_argument("--out-csv", type=Path, default=DEFAULT_OUT_CSV)
    p.add_argument("--out-tab", type=Path, default=DEFAULT_OUT_TAB)
    return p.parse_args()


def compute_funnel(
    screen_summary: dict, ext_df: pd.DataFrame, pro_df: pd.DataFrame, eval_summary: dict
) -> pd.DataFrame:
    """Build the funnel as a tidy DataFrame."""
    sp = screen_summary["splits"]
    # external: 2966 raw from test_external_with_reject_flag
    ext_raw_frames = len(ext_df)
    ext_raw_patients = ext_df["patient_id"].nunique()
    # latest_reject_mapped == True means REJECTED (508); False means KEPT (2458)
    ext_keep_frames = int((ext_df["latest_reject_mapped"] == False).sum())  # noqa: E712
    ext_keep_patients = ext_df.loc[ext_df["latest_reject_mapped"] == False, "patient_id"].nunique()
    # prospective: 2430 raw
    pro_raw_frames = len(pro_df)
    pro_raw_patients = pro_df["patient_id"].nunique()
    pro_keep_frames = sp["test_prospective"]["after"]
    pro_keep_patients = 425  # from tstaging_4class_screened_eval_20260531
    # splits from eval
    train = eval_summary["tstaging_4class_screened_eval"]["train"]
    val = eval_summary["tstaging_4class_screened_eval"]["val"]
    test_pro = eval_summary["tstaging_4class_screened_eval"]["test_prospective"]
    test_ext = eval_summary["tstaging_4class_screened_eval"]["test_external"]
    rows = [
        # 1. raw test cohorts (pre-screening)
        {"stage": "Raw enrolled\n(test cohorts)", "cohort": "test_external", "frames": ext_raw_frames, "patients": ext_raw_patients, "step": "0. Raw enrolled"},
        {"stage": "Raw enrolled\n(test cohorts)", "cohort": "test_prospective", "frames": pro_raw_frames, "patients": pro_raw_patients, "step": "0. Raw enrolled"},
        # 2. post-screening
        {"stage": "Screened\n(2026-05-31 contract)", "cohort": "test_external", "frames": ext_keep_frames, "patients": ext_keep_patients, "step": "1. After screening"},
        {"stage": "Screened\n(2026-05-31 contract)", "cohort": "test_prospective", "frames": pro_keep_frames, "patients": pro_keep_patients, "step": "1. After screening"},
        # 3. final splits — train/val come from the same screening contract (not test cohorts)
        {"stage": "Final split", "cohort": "train", "frames": train["rows"], "patients": train["patients"], "step": "2. Final split"},
        {"stage": "Final split", "cohort": "val", "frames": val["rows"], "patients": val["patients"], "step": "2. Final split"},
        {"stage": "Final split", "cohort": "test_prospective", "frames": test_pro["rows"], "patients": test_pro["patients"], "step": "2. Final split"},
        {"stage": "Final split", "cohort": "test_external", "frames": test_ext["rows"], "patients": test_ext["patients"], "step": "2. Final split"},
    ]
    return pd.DataFrame(rows)


def make_figure(funnel: pd.DataFrame, out_png: Path) -> None:
    """Horizontal funnel-style bar chart with 3 stage columns."""
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 5.0), sharey=True, gridspec_kw={"width_ratios": [1, 1, 2]})
    palette = {
        "test_external": "#1f4e79",
        "test_prospective": "#c0504d",
        "train": "#9bbb59",
        "val": "#7f7f7f",
    }
    titles = [
        "0. Raw enrolled (test cohorts)",
        "1. After 2026-05-31 screening",
        "2. Final patient-level disjoint split",
    ]
    cohort_orders = [
        ["test_external", "test_prospective"],
        ["test_external", "test_prospective"],
        ["train", "val", "test_prospective", "test_external"],
    ]
    for ax, stage, cohorts, title in zip(axes, ["0", "1", "2"], cohort_orders, titles):
        sub = funnel[funnel["step"].str.startswith(stage)]
        sub = sub[sub["cohort"].isin(cohorts)]
        # ensure order
        sub = sub.set_index("cohort").reindex(cohorts).reset_index()
        bars = ax.barh(
            sub["cohort"],
            sub["frames"],
            color=[palette[c] for c in sub["cohort"]],
            edgecolor="black",
            linewidth=0.4,
        )
        for bar, f, p in zip(bars, sub["frames"], sub["patients"]):
            ax.text(
                bar.get_width() + max(funnel["frames"]) * 0.012,
                bar.get_y() + bar.get_height() / 2,
                f"{int(f):,} frames\n({int(p):,} pts)",
                va="center",
                ha="left",
                fontsize=9,
            )
        ax.set_title(title, fontsize=10.5, fontweight="bold")
        ax.set_xlim(0, max(funnel["frames"]) * 1.32)
        ax.invert_yaxis()
        ax.grid(axis="x", linestyle=":", alpha=0.4)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    axes[0].set_ylabel("Cohort")
    fig.suptitle(
        "Screening funnel for the GastricTstaging-screened-2026.05 contract\n"
        "(17.1% of external frames and 31.7% of prospective frames removed by "
        "non-diagnostic-lumen / out-of-plane / duplicate-acquisition rules)",
        fontsize=11,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=200, bbox_inches="tight")
    plt.close(fig)


def make_table(funnel: pd.DataFrame) -> str:
    """Markdown table for paper."""
    f = funnel.copy()
    f["frames_str"] = f["frames"].map(lambda x: f"{int(x):,}")
    f["patients_str"] = f["patients"].map(lambda x: f"{int(x):,}")
    # pivot: step x cohort
    pivot = f.pivot_table(
        index="step", columns="cohort", values=["frames_str", "patients_str"], aggfunc="first"
    )
    # flatten columns
    pivot.columns = [f"{m}_{c}" for m, c in pivot.columns]
    pivot = pivot.reset_index()
    lines = [
        "| step | external frames | external pts | prospective frames | prospective pts | train frames | train pts | val frames | val pts |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for _, row in pivot.iterrows():
        lines.append(
            f"| {row['step']} | "
            f"{row.get('frames_str_test_external', '—')} | {row.get('patients_str_test_external', '—')} | "
            f"{row.get('frames_str_test_prospective', '—')} | {row.get('patients_str_test_prospective', '—')} | "
            f"{row.get('frames_str_train', '—')} | {row.get('patients_str_train', '—')} | "
            f"{row.get('frames_str_val', '—')} | {row.get('patients_str_val', '—')} |"
        )
    # add drop-rate row
    ext_drop = f"{int(funnel.iloc[0]['frames'] - funnel.iloc[2]['frames']):,} ({((funnel.iloc[0]['frames'] - funnel.iloc[2]['frames']) / funnel.iloc[0]['frames'] * 100):.1f}%)"
    pro_drop = f"{int(funnel.iloc[1]['frames'] - funnel.iloc[3]['frames']):,} ({((funnel.iloc[1]['frames'] - funnel.iloc[3]['frames']) / funnel.iloc[1]['frames'] * 100):.1f}%)"
    lines.append(
        f"| drop (raw → screened) | {ext_drop} | — | {pro_drop} | — | — | — | — | — |"
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    screen_summary = json.loads(args.screen_summary.read_text())
    ext_df = pd.read_csv(args.ext_csv)
    pro_df = pd.read_csv(args.pro_csv)
    eval_summary = json.loads(args.eval_summary.read_text())
    funnel = compute_funnel(screen_summary, ext_df, pro_df, eval_summary)
    make_figure(funnel, args.out_png)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    funnel.to_csv(args.out_csv, index=False)
    tab = make_table(funnel)
    args.out_tab.write_text(tab, encoding="utf-8")
    print("=== screening funnel ===")
    print(funnel.to_string(index=False))
    print(f"\nwritten: {args.out_png}")
    print(f"audit:   {args.out_csv}")
    print(f"table:   {args.out_tab}")
    print()
    print("=== table markdown ===")
    print(tab)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
