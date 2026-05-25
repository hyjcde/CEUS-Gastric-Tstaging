#!/usr/bin/env python3
"""Compare T2/T3->T4+ overstaging and headline metrics across model checkpoints."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

VARIANTS = [
    ("baseline_full", "pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301"),
    ("antioverstage_v1", "pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_t2t3_antioverstage_finetune_20260520_143727"),
    ("antioverstage_v2", "pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_t2t3_antioverstage_v2_finetune_20260520_151540"),
    ("antioverstage_v3", "pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_t2t3_antioverstage_v3_head_finetune_20260522_200526"),
    ("antioverstage_v4", "pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_t2t3_antioverstage_v4_multitask_20260523_191522"),
]


def overstaging_row(pred_csv: Path) -> dict:
    df = pd.read_csv(pred_csv, low_memory=False)
    label = df["label"].astype(int)
    pred = df["pred"].astype(int)
    p4 = df["prob_c3"].astype(float)
    rows = {}
    for lab, name in [(1, "T2"), (2, "T3")]:
        m = label == lab
        n = int(m.sum())
        to4 = int((pred[m] == 3).sum())
        rows[f"{name}_to_T4pct"] = 100.0 * to4 / max(n, 1)
    t23 = label.isin([1, 2])
    rows["T23_to_T4pct"] = 100.0 * int(((t23) & (pred == 3)).sum()) / max(int(t23.sum()), 1)
    rows["max_P_T4"] = float(p4.max())
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="test_external", choices=["test_external", "test_prospective"])
    parser.add_argument("--extra", nargs="*", default=[], help="name=exp_dir pairs")
    args = parser.parse_args()

    variants = list(VARIANTS)
    for item in args.extra:
        name, path = item.split("=", 1)
        variants.append((name, path))

    records = []
    for name, exp_dir in variants:
        exp = Path(exp_dir)
        pred = exp / "eval" / args.split / "test_predictions.csv"
        res = exp / "eval" / args.split / "test_results.json"
        if not pred.is_file():
            continue
        row = {"model": name, **overstaging_row(pred)}
        if res.is_file():
            r = json.loads(res.read_text(encoding="utf-8"))
            row["auc"] = r.get("auc")
            row["acc"] = r.get("accuracy")
            row["bal_acc"] = r.get("balanced_accuracy")
        records.append(row)

    if not records:
        print("No predictions found.")
        return

    out = pd.DataFrame(records)
    print(f"\n=== {args.split} ===\n")
    print(out.to_string(index=False, float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    main()
