#!/usr/bin/env python3
"""
Bootstrap 2000-replicate patient-level 95% CI for the 06-03 acc_boost2 frozen primary.

Inputs (defaults point at the 06-03 run; override with --pro-csv / --ext-csv):
  pipeline/experiments/tree/gastric_tstage_4class/classification/dual_convnext/
    tstaging_4class_acc_boost2_multitask_screened_eval_20260603_162955/eval/
      test_prospective/test_predictions.csv
      latest_screened_external_reeval/test_external/test_predictions.csv

Outputs (defaults):
  docs/paper_drafts/tex_v2_ldh/tab_ci_bootstrap.csv         (markdown table for paper)
  pipeline/experiments/tree/.../eval/bootstrap_ci_2000.json (raw values for audit)

Patient-level disjoint resampling with replacement; configurable via --n-boot.
Frame-level predictions are aggregated to patient level by majority vote.
All metrics computed on the resampled patient set (frame-level for confusion,
patient-level for accuracy). 8 metrics x 2 cohorts (16 columns).

Usage:
  python3 scripts/bootstrap_tstaging_ci.py --help
  python3 scripts/bootstrap_tstaging_ci.py
  python3 scripts/bootstrap_tstaging_ci.py --n-boot 5000
  python3 scripts/bootstrap_tstaging_ci.py --pro-csv <path> --ext-csv <path>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRO_CSV = (
    REPO_ROOT
    / "pipeline/experiments/tree/gastric_tstage_4class/classification/dual_convnext"
    / "tstaging_4class_acc_boost2_multitask_screened_eval_20260603_162955"
    / "eval/test_prospective/test_predictions.csv"
)
DEFAULT_EXT_CSV = (
    REPO_ROOT
    / "pipeline/experiments/tree/gastric_tstage_4class/classification/dual_convnext"
    / "tstaging_4class_acc_boost2_multitask_screened_eval_20260603_162955"
    / "eval/latest_screened_external_reeval/test_external/test_predictions.csv"
)
DEFAULT_OUT_TAB = REPO_ROOT / "docs/paper_drafts/tex_v2_ldh/tab_ci_bootstrap.csv"
DEFAULT_OUT_AUDIT = (
    REPO_ROOT
    / "pipeline/experiments/tree/gastric_tstage_4class/classification/dual_convnext"
    / "tstaging_4class_acc_boost2_multitask_screened_eval_20260603_162955"
    / "eval/bootstrap_ci_2000.json"
)
DEFAULT_N_BOOT = 2000
DEFAULT_SEED = 20260610
CLASS_NAMES = ["T1", "T2", "T3", "T4+"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Patient-level bootstrap 95% CI for the 06-03 frozen primary."
    )
    p.add_argument("--pro-csv", type=Path, default=DEFAULT_PRO_CSV,
                   help=f"Prospective test_predictions.csv (default: {DEFAULT_PRO_CSV.name})")
    p.add_argument("--ext-csv", type=Path, default=DEFAULT_EXT_CSV,
                   help=f"External test_predictions.csv (default: {DEFAULT_EXT_CSV.name})")
    p.add_argument("--out-tab", type=Path, default=DEFAULT_OUT_TAB,
                   help="Output markdown table path")
    p.add_argument("--out-audit", type=Path, default=DEFAULT_OUT_AUDIT,
                   help="Output raw audit JSON path")
    p.add_argument("--n-boot", type=int, default=DEFAULT_N_BOOT,
                   help=f"Bootstrap replicates (default: {DEFAULT_N_BOOT})")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED,
                   help=f"Random seed (default: {DEFAULT_SEED})")
    return p.parse_args(argv)


def aggregate_patient_majority(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate frame-level predictions to patient-level via majority vote.

    For each patient: pred_patient = mode(pred per frame). On tie, the
    lowest class index wins (stable for >2 frame patients). Returns one row
    per patient with truth and pred in 0..3 (T1, T2, T3, T4+ where 3
    aggregates T4a and T4b per class_label).
    """
    rows = []
    for pid, sub in df.groupby("patient_id"):
        truth = int(sub["class_label"].mode().iloc[0])
        votes = sub["pred"].value_counts()
        max_count = votes.max()
        tied = int(votes[votes == max_count].index.min())
        rows.append({"patient_id": pid, "truth": truth, "pred": tied})
    return pd.DataFrame(rows)


def metrics_from_patients(pat: pd.DataFrame, frame_df: pd.DataFrame) -> dict:
    """Compute the 8 metrics from a patient set (and original frame df for confusion)."""
    n = len(pat)
    acc = (pat["truth"] == pat["pred"]).mean() if n else 0.0
    recs = []
    for c in range(4):
        sub = pat[pat["truth"] == c]
        recs.append((sub["pred"] == c).mean() if len(sub) else np.nan)
    bacc = float(np.nanmean(recs))
    pat_ids = set(pat["patient_id"])
    fsub = frame_df[frame_df["patient_id"].isin(pat_ids)]
    frame_recs = []
    for c in range(4):
        sub = fsub[fsub["class_label"] == c]
        frame_recs.append((sub["pred"] == c).mean() if len(sub) else np.nan)
    try:
        from sklearn.metrics import roc_auc_score

        y_true = fsub["class_label"].values
        probs = fsub[["prob_c0", "prob_c1", "prob_c2", "prob_c3"]].values
        macro_auc = roc_auc_score(
            y_true, probs, multi_class="ovr", average="macro", labels=[0, 1, 2, 3]
        )
    except Exception:
        macro_auc = np.nan
    t2_truth = fsub[fsub["class_label"] == 1]
    t2t3_over = float((t2_truth["pred"] == 2).mean()) if len(t2_truth) else np.nan
    return {
        "macro_auc": float(macro_auc) if macro_auc == macro_auc else np.nan,
        "bacc": bacc,
        "t1_recall": float(frame_recs[0]) if frame_recs[0] == frame_recs[0] else np.nan,
        "t2_recall": float(frame_recs[1]) if frame_recs[1] == frame_recs[1] else np.nan,
        "t3_recall": float(frame_recs[2]) if frame_recs[2] == frame_recs[2] else np.nan,
        "t4_recall": float(frame_recs[3]) if frame_recs[3] == frame_recs[3] else np.nan,
        "t2t3_overstage": t2t3_over,
        "patient_acc": acc,
    }


def bootstrap_cohort(df: pd.DataFrame, n_boot: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    patient_ids = df["patient_id"].unique()
    pat_df_full = aggregate_patient_majority(df)
    pat_lookup = {pid: pat_df_full[pat_df_full["patient_id"] == pid].iloc[0] for pid in patient_ids}
    rows = []
    for _ in range(n_boot):
        sampled = rng.choice(patient_ids, size=len(patient_ids), replace=True)
        pat = pd.DataFrame([pat_lookup[pid] for pid in sampled])
        rows.append(metrics_from_patients(pat, df))
    return {k: np.array([r[k] for r in rows]) for k in rows[0].keys()}


def main() -> int:
    args = parse_args()
    if not args.pro_csv.exists() or not args.ext_csv.exists():
        print(f"missing csv: PRO={args.pro_csv.exists()} EXT={args.ext_csv.exists()}", file=sys.stderr)
        return 1
    print(f"loading {args.pro_csv.name} + {args.ext_csv.name} ...")
    df_pro = pd.read_csv(args.pro_csv)
    df_ext = pd.read_csv(args.ext_csv)
    print(
        f"  pro frames={len(df_pro)} patients={df_pro['patient_id'].nunique()}  "
        f"ext frames={len(df_ext)} patients={df_ext['patient_id'].nunique()}"
    )
    print(f"running {args.n_boot} patient-level bootstrap replicates per cohort ...")
    boot_pro = bootstrap_cohort(df_pro, args.n_boot, seed=args.seed + 1)
    boot_ext = bootstrap_cohort(df_ext, args.n_boot, seed=args.seed + 2)

    pt_pro = metrics_from_patients(aggregate_patient_majority(df_pro), df_pro)
    pt_ext = metrics_from_patients(aggregate_patient_majority(df_ext), df_ext)

    METRIC_ORDER = [
        "macro_auc", "bacc", "patient_acc",
        "t1_recall", "t2_recall", "t3_recall", "t4_recall", "t2t3_overstage",
    ]
    METRIC_LABEL = {
        "macro_auc": "macro-AUC (frame-level OVR)",
        "bacc": "balanced accuracy (patient-level)",
        "patient_acc": "patient-level accuracy (majority vote)",
        "t1_recall": "T1 recall (frame-level)",
        "t2_recall": "T2 recall (frame-level)",
        "t3_recall": "T3 recall (frame-level)",
        "t4_recall": "T4+ recall (frame-level)",
        "t2t3_overstage": "T2→T3 over-stage (4-class, frame-level)",
    }

    lines = [
        "| metric | pro point | pro 2.5% | pro 50% | pro 97.5% | ext point | ext 2.5% | ext 50% | ext 97.5% |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    audit = {
        "n_boot": args.n_boot,
        "seed": args.seed,
        "pro": {"n_frames": len(df_pro), "n_patients": int(df_pro["patient_id"].nunique())},
        "ext": {"n_frames": len(df_ext), "n_patients": int(df_ext["patient_id"].nunique())},
        "metrics": {},
    }
    for m in METRIC_ORDER:
        p = boot_pro[m]
        e = boot_ext[m]
        lo_p, med_p, hi_p = np.nanpercentile(p, [2.5, 50, 97.5])
        lo_e, med_e, hi_e = np.nanpercentile(e, [2.5, 50, 97.5])
        lines.append(
            f"| {METRIC_LABEL[m]} | {pt_pro[m]:.4f} | {lo_p:.4f} | {med_p:.4f} | {hi_p:.4f} | "
            f"{pt_ext[m]:.4f} | {lo_e:.4f} | {med_e:.4f} | {hi_e:.4f} |"
        )
        audit["metrics"][m] = {
            "pro_point": pt_pro[m],
            "pro_ci": [float(lo_p), float(hi_p)],
            "pro_median": float(med_p),
            "ext_point": pt_ext[m],
            "ext_ci": [float(lo_e), float(hi_e)],
            "ext_median": float(med_e),
        }
    args.out_tab.parent.mkdir(parents=True, exist_ok=True)
    args.out_tab.write_text("\n".join(lines) + "\n", encoding="utf-8")
    args.out_audit.parent.mkdir(parents=True, exist_ok=True)
    args.out_audit.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n=== tab:ci 8-metric x 2-cohort bootstrap 95% CI ===")
    print("\n".join(lines))
    print(f"\nwritten: {args.out_tab}")
    print(f"audit:   {args.out_audit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
