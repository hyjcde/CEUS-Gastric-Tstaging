#!/usr/bin/env python3
"""Ensemble two model prediction CSVs (same rows) and report T-staging metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score


def load_probs(df: pd.DataFrame) -> np.ndarray:
    cols = [f"prob_c{i}" for i in range(4)]
    if all(c in df.columns for c in cols):
        return df[cols].astype(float).to_numpy()
    cols = ["prob_T1", "prob_T2", "prob_T3", "prob_T4+"]
    return df[cols].astype(float).to_numpy()


def evaluate(labels: np.ndarray, probs: np.ndarray) -> dict:
    preds = probs.argmax(axis=1)
    out = {
        "accuracy": float(accuracy_score(labels, preds)),
        "f1_macro": float(f1_score(labels, preds, average="macro", zero_division=0)),
    }
    try:
        out["auc"] = float(
            roc_auc_score(labels, probs, multi_class="ovr", labels=[0, 1, 2, 3], average="macro")
        )
    except Exception:
        out["auc"] = 0.0
    t23 = np.isin(labels, [1, 2])
    if t23.sum():
        out["t2t3_overstage_rate"] = float((preds[t23] == 3).mean())
        for lab, name in [(1, "T2"), (2, "T3")]:
            m = labels == lab
            out[f"{name}_to_T4_rate"] = float((preds[m] == 3).mean()) if m.sum() else 0.0
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-a", type=Path, required=True, help="Higher-AUC / baseline CSV")
    parser.add_argument("--csv-b", type=Path, required=True, help="Anti-overstage CSV (e.g. v3)")
    parser.add_argument("--weight-b", type=float, default=0.65, help="Weight for csv-b (csv-a gets 1-w)")
    parser.add_argument("--output-csv", type=Path, default=None)
    args = parser.parse_args()

    key = "image_path"
    a = pd.read_csv(args.csv_a, low_memory=False).sort_values(key).reset_index(drop=True)
    b = pd.read_csv(args.csv_b, low_memory=False).sort_values(key).reset_index(drop=True)
    if len(a) != len(b):
        raise SystemExit(f"Row count mismatch: {len(a)} vs {len(b)}")
    if not (a[key].astype(str).values == b[key].astype(str).values).all():
        raise SystemExit("image_path rows differ after sort — check CSV pair")

    w_b = float(args.weight_b)
    w_a = 1.0 - w_b
    probs = w_a * load_probs(a) + w_b * load_probs(b)
    probs = probs / probs.sum(axis=1, keepdims=True)
    labels = a["label"].astype(int).to_numpy()
    preds = probs.argmax(axis=1)

    metrics = evaluate(labels, probs)
    print(f"Ensemble: w_a={w_a:.2f} ({args.csv_a.name}) + w_b={w_b:.2f} ({args.csv_b.name})")
    for k, v in metrics.items():
        print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")

    if args.output_csv:
        out = a.copy()
        for i in range(4):
            out[f"prob_c{i}"] = probs[:, i]
        out["pred"] = preds
        out["pred_class"] = preds
        args.output_csv.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(args.output_csv, index=False)
        sidecar = args.output_csv.with_suffix(".metrics.json")
        sidecar.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        print(f"Saved: {args.output_csv}")


if __name__ == "__main__":
    main()
