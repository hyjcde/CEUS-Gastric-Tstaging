#!/usr/bin/env python3
"""
Re-select the reader study subset (n>=150) using the 06-03 frozen primary.

Pool: docs/clinical_validation/reader_study_150/video_screening_pool.csv
  (185 patients: 102 ext + 83 pro, all with video, T-stage distribution
  T1=20, T2=46, T3=53, T4+=66).

Selection policy (relaxed in two steps to hit n>=150):
  1. Strict:   patient-level AI pred == pathology T  AND  max prob >= 0.7
  2. Relaxed:  patient-level AI pred == pathology T  (any confidence)
  3. Lenient:  patient-level majority-vote from frame-level AI  (frame-level
               recall on the patient > 0.5 AND frame-level top class == truth)

Output:
  docs/clinical_validation/reader_study_150/reader_subset_v2.csv
  docs/clinical_validation/reader_study_150/reader_subset_v2_report.txt
  docs/clinical_validation/reader_study_150/reader_subset_v2.json (audit)

Usage:
  python3 scripts/select_reader_study_subset.py --help
  python3 scripts/select_reader_study_subset.py
  python3 scripts/select_reader_study_subset.py --target 150 --strategy strict
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
POOL_CSV = (
    REPO_ROOT
    / "docs/clinical_validation/reader_study_150/video_screening_pool.csv"
)
PRO_PRED = (
    REPO_ROOT
    / "pipeline/experiments/tree/gastric_tstage_4class/classification/dual_convnext"
    / "tstaging_4class_acc_boost2_multitask_screened_eval_20260603_162955"
    / "eval/test_prospective/test_predictions.csv"
)
EXT_PRED = (
    REPO_ROOT
    / "pipeline/experiments/tree/gastric_tstage_4class/classification/dual_convnext"
    / "tstaging_4class_acc_boost2_multitask_screened_eval_20260603_162955"
    / "eval/latest_screened_external_reeval/test_external/test_predictions.csv"
)
OUT_DIR = REPO_ROOT / "docs/clinical_validation/reader_study_150"
DEFAULT_TARGET = 150
DEFAULT_SEED = 20260612


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Re-select reader study subset (n>=150).")
    p.add_argument("--pool-csv", type=Path, default=POOL_CSV)
    p.add_argument("--pro-pred", type=Path, default=PRO_PRED)
    p.add_argument("--ext-pred", type=Path, default=EXT_PRED)
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    p.add_argument("--target", type=int, default=DEFAULT_TARGET,
                   help=f"Minimum subset size (default: {DEFAULT_TARGET})")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--strategy", choices=["strict", "relaxed", "lenient", "auto"],
                   default="auto",
                   help="Selection policy. 'auto' tries strict -> relaxed -> lenient to hit --target.")
    return p.parse_args()


def majority_vote(series: pd.Series) -> int:
    """Return the most common value in `series` (lowest idx on tie)."""
    c = Counter(series.tolist())
    top = max(c.values())
    return min(k for k, v in c.items() if v == top)


def patient_level_metrics(frame_df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-patient: majority_vote pred, max prob, frame-level accuracy, n_frames."""
    g = frame_df.groupby("patient_id")
    rows = []
    for pid, sub in g:
        truth = int(sub["class_label"].mode().iloc[0])
        probs = sub[["prob_c0", "prob_c1", "prob_c2", "prob_c3"]].values
        mean_probs = probs.mean(axis=0)
        majority = int(np.argmax(mean_probs))
        # max prob = peak of the mean prob vector (confidence in majority call)
        max_prob = float(mean_probs[majority])
        # frame-level recall = fraction of frames where frame pred == truth
        frame_correct = float((sub["pred"] == truth).mean())
        rows.append({
            "patient_id": pid,
            "truth": truth,
            "ai_pred": majority,
            "ai_max_prob": max_prob,
            "ai_frame_recall": frame_correct,
            "n_frames": len(sub),
        })
    return pd.DataFrame(rows)


def select_strict(metrics: pd.DataFrame) -> pd.DataFrame:
    """pred == truth AND max_prob >= 0.7"""
    m = metrics[(metrics["ai_pred"] == metrics["truth"]) & (metrics["ai_max_prob"] >= 0.7)]
    return m.assign(strategy="strict")


def select_relaxed(metrics: pd.DataFrame) -> pd.DataFrame:
    """pred == truth, no confidence threshold"""
    m = metrics[metrics["ai_pred"] == metrics["truth"]]
    return m.assign(strategy="relaxed")


def select_lenient(metrics: pd.DataFrame) -> pd.DataFrame:
    """frame-level recall > 0.5 AND frame-level top class == truth"""
    m = metrics[(metrics["ai_frame_recall"] > 0.5) & (metrics["ai_pred"] == metrics["truth"])]
    return m.assign(strategy="lenient")


def balance_per_tstage(df: pd.DataFrame, target: int, rng: np.random.Generator) -> pd.DataFrame:
    """Try to balance T-stage representation. If a class is short, take all of it;
    for over-represented classes, sample down. If still short, fill with the
    most under-represented class first, then any leftover.
    """
    counts = df["truth"].value_counts().to_dict()
    n_classes = 4
    # ideal per-class = target / n_classes, but cap at available
    per_class_ideal = target // n_classes
    chosen = []
    for c in [0, 1, 2, 3]:
        n_avail = counts.get(c, 0)
        n_take = min(n_avail, per_class_ideal)
        sub = df[df["truth"] == c]
        if n_take < n_avail:
            sub = sub.sample(n=n_take, random_state=int(rng.integers(0, 2**31 - 1)))
        chosen.append(sub)
    out = pd.concat(chosen, ignore_index=True)
    if len(out) < target:
        # top up: classes with surplus, take the highest confidence first
        already = set(out["patient_id"])
        remaining = df[~df["patient_id"].isin(already)].sort_values("ai_max_prob", ascending=False)
        n_more = target - len(out)
        out = pd.concat([out, remaining.head(n_more)], ignore_index=True)
    return out


def main() -> int:
    args = parse_args()
    rng = np.random.default_rng(args.seed)

    pool = pd.read_csv(args.pool_csv)
    pro_pred = pd.read_csv(args.pro_pred)
    ext_pred = pd.read_csv(args.ext_pred)
    metrics_pro = patient_level_metrics(pro_pred)
    metrics_ext = patient_level_metrics(ext_pred)
    metrics = pd.concat([metrics_pro, metrics_ext], ignore_index=True)
    metrics["patient_id"] = metrics["patient_id"].astype(str)
    pool["patient_id"] = pool["patient_id"].astype(str)
    metrics = metrics.drop_duplicates(subset="patient_id", keep="first")

    annotated = pool.merge(metrics, on="patient_id", how="left")
    tmap = {"T1": 0, "T2": 1, "T3": 2, "T4+": 3, "T4a": 3, "T4b": 3}
    annotated["truth"] = annotated["pathology_t_stage"].map(tmap)

    # Two-arm design: AI-clean (Arm A) + AI-uncertain (Arm B)
    # Arm A: lenient selection (frame-level majority == truth AND frame recall > 0.5)
    arm_a = select_lenient(annotated).copy()
    arm_a = arm_a.assign(arm="A_ai_clean")
    # Arm B: AI incorrect or low confidence (max_prob < 0.5)
    arm_b_pool = annotated[~annotated["patient_id"].isin(arm_a["patient_id"])]
    arm_b = arm_b_pool[arm_b_pool["ai_max_prob"] < 0.5].copy()
    if len(arm_b) < (args.target - len(arm_a)):
        # top up Arm B with AI-wrong cases by lowest max_prob
        rest = arm_b_pool[~arm_b_pool["patient_id"].isin(arm_b["patient_id"])]
        rest = rest.sort_values("ai_max_prob", ascending=True)
        n_more = (args.target - len(arm_a)) - len(arm_b)
        arm_b = pd.concat([arm_b, rest.head(n_more)], ignore_index=True)
    arm_b = arm_b.head(args.target - len(arm_a)).assign(arm="B_ai_uncertain")
    arm_b = arm_b.assign(strategy="uncertain_low_conf")

    chosen = pd.concat([arm_a, arm_b], ignore_index=True)
    if len(chosen) > args.target + 20:
        # Trim over-represented T4+ in either arm
        chosen = chosen.groupby("arm", group_keys=False).apply(
            lambda d: d.sort_values("ai_max_prob", ascending=(d.name == "A_ai_clean"))
                     .head(int(args.target / 2) + 10)
        )
    chosen = chosen.reset_index(drop=True)
    chosen = chosen.assign(
        case_id=[f"CASE-{i+1:03d}" for i in range(len(chosen))],
        display_id=[f"P{i+1:03d}" for i in range(len(chosen))],
    )

    out_cols = [
        "case_id", "display_id", "arm", "patient_id", "cohort", "source",
        "pathology_t_stage", "video_count", "video_tokens", "sample_video_stems",
        "truth", "ai_pred", "ai_max_prob", "ai_frame_recall", "n_frames",
        "strategy",
    ]
    for c in out_cols:
        if c not in chosen.columns:
            chosen[c] = ""
    out_df = chosen[out_cols].copy()
    out_df["ai_correct"] = (out_df["ai_pred"] == out_df["truth"]).astype(str)
    out_df["ai_max_prob"] = pd.to_numeric(out_df["ai_max_prob"], errors="coerce").round(4)
    out_df["ai_frame_recall"] = pd.to_numeric(out_df["ai_frame_recall"], errors="coerce").round(4)
    out_df = out_df.sort_values(["arm", "case_id"]).reset_index(drop=True)
    # re-number case_id across the merged set
    out_df["case_id"] = [f"CASE-{i+1:03d}" for i in range(len(out_df))]
    out_df["display_id"] = [f"P{i+1:03d}" for i in range(len(out_df))]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = args.out_dir / "reader_subset_v2.csv"
    out_df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    arm_a_size = int((out_df["arm"] == "A_ai_clean").sum())
    arm_b_size = int((out_df["arm"] == "B_ai_uncertain").sum())
    audit = {
        "design": "two_arm",
        "arm_a_label": "AI-clean (frame-level majority == truth, frame recall > 0.5)",
        "arm_b_label": "AI-uncertain (max_prob < 0.5 or AI wrong, balanced against A)",
        "arm_a_size": arm_a_size,
        "arm_b_size": arm_b_size,
        "total": int(len(out_df)),
        "pool_size": int(len(pool)),
        "t_stage_distribution": {k: int(v) for k, v in out_df["pathology_t_stage"].value_counts().items()},
        "ai_accuracy_arm_a": float(
            (out_df[out_df["arm"] == "A_ai_clean"]["ai_pred"]
             == out_df[out_df["arm"] == "A_ai_clean"]["truth"]).mean()
        ),
        "ai_accuracy_arm_b": float(
            (out_df[out_df["arm"] == "B_ai_uncertain"]["ai_pred"]
             == out_df[out_df["arm"] == "B_ai_uncertain"]["truth"]).mean()
        ),
        "ai_overall_subset": float((out_df["ai_pred"] == out_df["truth"]).mean()),
        "ai_mean_max_prob": float(pd.to_numeric(out_df["ai_max_prob"], errors="coerce").mean()),
        "cohort_split": out_df["cohort"].value_counts().to_dict(),
        "t_stage_by_arm": {
            "A": out_df[out_df["arm"] == "A_ai_clean"]["pathology_t_stage"].value_counts().to_dict(),
            "B": out_df[out_df["arm"] == "B_ai_uncertain"]["pathology_t_stage"].value_counts().to_dict(),
        },
    }
    audit_json = args.out_dir / "reader_subset_v2.json"
    audit_json.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    report = args.out_dir / "reader_subset_v2_report.txt"
    report.write_text(
        f"Reader study subset v2 (06-03 frozen primary, 2-arm design)\n"
        f"  pool: {audit['pool_size']} patients with video\n"
        f"  Arm A (AI-clean):     {arm_a_size} cases (AI acc {audit['ai_accuracy_arm_a']:.4f})\n"
        f"  Arm B (AI-uncertain): {arm_b_size} cases (AI acc {audit['ai_accuracy_arm_b']:.4f})\n"
        f"  Total: {audit['total']} cases (>= target {args.target})\n"
        f"  AI mean max prob: {audit['ai_mean_max_prob']:.4f}\n"
        f"  T-stage distribution (overall): {audit['t_stage_distribution']}\n"
        f"  T-stage by arm: A={audit['t_stage_by_arm']['A']}  B={audit['t_stage_by_arm']['B']}\n"
        f"  Cohort split: {audit['cohort_split']}\n",
        encoding="utf-8",
    )

    print("=== reader study subset v2 (2-arm) ===")
    print(f"  pool: {audit['pool_size']} patients")
    print(f"  Arm A (AI-clean):     {arm_a_size} cases (AI acc {audit['ai_accuracy_arm_a']:.4f})")
    print(f"  Arm B (AI-uncertain): {arm_b_size} cases (AI acc {audit['ai_accuracy_arm_b']:.4f})")
    print(f"  Total: {audit['total']} (target >= {args.target})")
    print(f"  AI mean max prob: {audit['ai_mean_max_prob']:.4f}")
    print(f"  T-stage overall: {audit['t_stage_distribution']}")
    print(f"  T-stage by arm: A={audit['t_stage_by_arm']['A']}  B={audit['t_stage_by_arm']['B']}")
    print(f"  Cohort split: {audit['cohort_split']}")
    print()
    print("=== per-arm per-T stage ===")
    print(out_df.groupby(["arm", "pathology_t_stage"]).size().to_string())
    print()
    print(f"written: {out_csv}")
    print(f"audit:   {audit_json}")
    print(f"report:  {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
