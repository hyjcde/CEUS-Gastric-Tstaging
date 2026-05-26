#!/usr/bin/env python3
"""Re-evaluate test metrics after clinical Grad-CAM image-quality screening."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, roc_auc_score

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PIPELINE_ROOT.parent

CLASS_NAMES = ["T1", "T2", "T3", "T4+"]
PROB_COLS = ["prob_T1", "prob_T2", "prob_T3", "prob_T4+"]

SPLIT_GRADCAM_DIRS = {
    "test_external": "gradcam_test_external_full",
    "test_prospective": "gradcam_test_prospective_full",
}


def normalize_rejected_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "rejected" in out.columns:
        flag = out["rejected"].astype(str).str.strip().str.lower()
        out = out.loc[flag.isin({"1", "true", "t", "yes"})].copy()
    if "filename" not in out.columns and "uid" in out.columns:
        out["filename"] = out["uid"].astype(str).str.split("::", n=1).str[-1]
    out["filename"] = out["filename"].astype(str)
    out["split"] = out["split"].astype(str)
    return out


def rejected_by_split(rejected_df: pd.DataFrame) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = {}
    for split, sub in rejected_df.groupby("split"):
        grouped[str(split)] = set(sub["filename"].astype(str))
    return grouped


def load_gradcam_results(exp_dir: Path, split: str, *, external_holdout_only: bool) -> pd.DataFrame:
    gc_dir = exp_dir / SPLIT_GRADCAM_DIRS[split]
    csv_path = gc_dir / "gradcam_results.csv"
    if not csv_path.is_file():
        raise FileNotFoundError(f"Missing Grad-CAM results: {csv_path}")
    df = pd.read_csv(csv_path, low_memory=False)
    if split == "test_external" and external_holdout_only:
        mask = ~df["image_path"].astype(str).str.contains("prospective", case=False, na=False)
        df = df.loc[mask].copy()
    return df


def compute_metrics(df: pd.DataFrame) -> dict:
    labels = df["true_label"].astype(int).to_numpy()
    probs = df[PROB_COLS].astype(float).to_numpy()
    preds = probs.argmax(axis=1)
    out: dict = {
        "n": int(len(df)),
        "accuracy": float(accuracy_score(labels, preds)),
        "balanced_accuracy": float(balanced_accuracy_score(labels, preds)),
        "f1_macro": float(f1_score(labels, preds, average="macro", zero_division=0)),
    }
    try:
        out["auc_macro_ovr"] = float(
            roc_auc_score(labels, probs, multi_class="ovr", labels=[0, 1, 2, 3], average="macro")
        )
    except ValueError:
        out["auc_macro_ovr"] = None

    t23 = np.isin(labels, [1, 2])
    if t23.sum():
        out["t2t3_overstage_rate"] = float((preds[t23] == 3).mean())
        for lab, name in [(1, "T2"), (2, "T3")]:
            mask = labels == lab
            if mask.sum():
                out[f"{name.lower()}_to_t4_rate"] = float((preds[mask] == 3).mean())
                out[f"{name.lower()}_recall"] = float((preds[mask] == lab).mean())

    per_class: dict[str, dict] = {}
    for lab, name in enumerate(CLASS_NAMES):
        mask = labels == lab
        if not mask.sum():
            continue
        per_class[name] = {
            "n": int(mask.sum()),
            "recall": float((preds[mask] == lab).mean()),
            "pred_as_t4_rate": float((preds[mask] == 3).mean()),
        }
    out["per_class"] = per_class
    return out


def filter_split(df: pd.DataFrame, rejected_names: set[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    mask = df["filename"].astype(str).isin(rejected_names)
    removed = df.loc[mask].copy()
    kept = df.loc[~mask].copy()
    return kept, removed


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Grad-CAM screening reject list and recompute metrics")
    parser.add_argument("--rejected-csv", type=Path, required=True)
    parser.add_argument(
        "--exp-dir",
        type=Path,
        default=(
            "pipeline/experiments/tree/gastric_tstage_4class/classification/"
            "dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Default: <exp-dir>/eval/screening_filtered_<timestamp>",
    )
    parser.add_argument(
        "--full-external",
        action="store_true",
        help="Use complete test_external (2430 frames, incl. prospective overlap); default strips duplicate prospective rows",
    )
    args = parser.parse_args()
    external_holdout_only = not args.full_external

    exp_dir = args.exp_dir
    if not exp_dir.is_absolute():
        exp_dir = PROJECT_ROOT / exp_dir
    if not exp_dir.is_dir():
        raise SystemExit(f"Experiment dir not found: {exp_dir}")

    rejected_csv = args.rejected_csv
    if not rejected_csv.is_absolute():
        rejected_csv = PROJECT_ROOT / rejected_csv
    if not rejected_csv.is_file():
        raise SystemExit(f"Rejected CSV not found: {rejected_csv}")

    rejected_df = normalize_rejected_df(pd.read_csv(rejected_csv, low_memory=False))
    rejected_map = rejected_by_split(rejected_df)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = args.output_dir or (exp_dir / f"eval/screening_filtered_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "exp_dir": str(exp_dir.resolve()),
        "rejected_csv": str(rejected_csv.resolve()),
        "rejected_rows": int(len(rejected_df)),
        "rejected_by_split": {k: len(v) for k, v in rejected_map.items()},
        "external_holdout_only": external_holdout_only,
        "splits": {},
        "combined": {},
    }

    kept_parts: list[pd.DataFrame] = []
    print(f"Rejected CSV: {rejected_csv} ({len(rejected_df)} rows)")
    for split in ("test_external", "test_prospective"):
        df = load_gradcam_results(exp_dir, split, external_holdout_only=external_holdout_only)
        rejected_names = rejected_map.get(split, set())
        kept, removed = filter_split(df, rejected_names)
        kept_parts.append(kept)

        split_out = out_dir / split
        split_out.mkdir(parents=True, exist_ok=True)
        kept.to_csv(split_out / "gradcam_results_kept.csv", index=False)
        removed.to_csv(split_out / "gradcam_results_removed.csv", index=False)

        before = compute_metrics(df)
        after = compute_metrics(kept)
        split_report = {
            "before": before,
            "after": after,
            "removed_n": int(len(removed)),
            "kept_n": int(len(kept)),
        }
        report["splits"][split] = split_report

        print(f"\n[{split}]")
        print(f"  before: n={before['n']}  ACC={before['accuracy']:.4f}  AUC={before['auc_macro_ovr']:.4f}  T2+T3→T4+={before.get('t2t3_overstage_rate', 0):.1%}")
        print(f"  after : n={after['n']}  ACC={after['accuracy']:.4f}  AUC={after['auc_macro_ovr']:.4f}  T2+T3→T4+={after.get('t2t3_overstage_rate', 0):.1%}")
        print(f"  removed: {len(removed)}")

    combined_before = pd.concat(
        [
            load_gradcam_results(exp_dir, s, external_holdout_only=external_holdout_only)
            for s in ("test_external", "test_prospective")
        ],
        ignore_index=True,
    )
    combined_kept = pd.concat(kept_parts, ignore_index=True)
    combined_kept.to_csv(out_dir / "gradcam_results_kept_all.csv", index=False)
    report["combined"] = {
        "before": compute_metrics(combined_before),
        "after": compute_metrics(combined_kept),
        "removed_n": int(len(combined_before) - len(combined_kept)),
        "kept_n": int(len(combined_kept)),
    }

    metrics_path = out_dir / "screening_filter_metrics.json"
    metrics_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary_lines = [
        "# Grad-CAM 筛图后测试集指标",
        "",
        f"- 剔除列表: `{rejected_csv}`",
        f"- 实验目录: `{exp_dir}`",
        f"- 生成时间: {report['created_utc']}",
        "",
        "## 分数据集",
    ]
    for split, split_report in report["splits"].items():
        b, a = split_report["before"], split_report["after"]
        summary_lines.extend(
            [
                "",
                f"### {split}",
                f"- 筛前: n={b['n']}, ACC={b['accuracy']:.4f}, AUC={b['auc_macro_ovr']:.4f}, T2+T3→T4+={b.get('t2t3_overstage_rate', 0):.1%}",
                f"- 筛后: n={a['n']}, ACC={a['accuracy']:.4f}, AUC={a['auc_macro_ovr']:.4f}, T2+T3→T4+={a.get('t2t3_overstage_rate', 0):.1%}",
                f"- 剔除: {split_report['removed_n']} 张",
            ]
        )
    cb, ca = report["combined"]["before"], report["combined"]["after"]
    summary_lines.extend(
        [
            "",
            f"## 合并（{'外部 holdout' if external_holdout_only else '外部全量'} + 前瞻全量）",
            f"- 筛前: n={cb['n']}, ACC={cb['accuracy']:.4f}, AUC={cb['auc_macro_ovr']:.4f}",
            f"- 筛后: n={ca['n']}, ACC={ca['accuracy']:.4f}, AUC={ca['auc_macro_ovr']:.4f}",
            f"- 剔除: {report['combined']['removed_n']} 张",
        ]
    )
    (out_dir / "SCREENING_FILTER_SUMMARY.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    shutil_copy = out_dir / "gradcam_rejected_input.csv"
    if rejected_csv.resolve() != shutil_copy.resolve():
        shutil_copy.write_bytes(rejected_csv.read_bytes())

    try:
        from build_gradcam_screening_audit_html import build_audit_html

        audit_html = out_dir / "screening_audit_report.html"
        build_audit_html(
            exp_dir=exp_dir,
            rejected_csv=rejected_csv,
            output_html=audit_html,
            external_holdout_only=external_holdout_only,
        )
        print(f"  screening_audit_report.html")
    except Exception as exc:
        print(f"Warning: audit HTML not generated: {exc}")

    print(f"\nSaved: {out_dir}")
    print(f"  {metrics_path.name}")
    print(f"  SCREENING_FILTER_SUMMARY.md")


if __name__ == "__main__":
    main()
