#!/usr/bin/env python3
"""Report T2/T3 -> T4+ overstaging and extreme confidence on a predictions CSV."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

CLASS_NAMES = ["T1", "T2", "T3", "T4+"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions-csv", type=Path, required=True)
    parser.add_argument("--label-col", default="label")
    parser.add_argument("--pred-col", default="pred")
    parser.add_argument("--prob-t4-col", default="prob_c3")
    args = parser.parse_args()

    df = pd.read_csv(args.predictions_csv, low_memory=False)
    label = df[args.label_col].astype(int)
    pred = df[args.pred_col].astype(int)
    p4 = df[args.prob_t4_col].astype(float)

    print(f"File: {args.predictions_csv}  (n={len(df)})")
    for lab, name in [(1, "T2"), (2, "T3")]:
        m = label == lab
        n = int(m.sum())
        if n == 0:
            continue
        to4 = int((pred[m] == 3).sum())
        hi = int(((pred[m] == 3) & (p4[m] >= 0.99)).sum())
        med_p4 = float(p4[m].median())
        print(
            f"  GT {name}: n={n}  -> T4+: {to4} ({100 * to4 / n:.1f}%)  "
            f"P(T4+)>=0.99 when pred T4+: {hi}  median P(T4+)={med_p4:.3f}"
        )

    t23 = label.isin([1, 2])
    n23 = int(t23.sum())
    to4_all = int(((label.isin([1, 2])) & (pred == 3)).sum())
    print(f"  GT T2+T3 combined -> T4+: {to4_all}/{n23} ({100 * to4_all / max(n23, 1):.1f}%)")
    print(f"  All samples max P(T4+): {p4.max():.6f}")


if __name__ == "__main__":
    main()
