"""Patient-level T-stage scores: exact ACC, adjacent ACC, QWK, per-center."""

from __future__ import annotations

from collections import defaultdict

import numpy as np
from sklearn.metrics import cohen_kappa_score, confusion_matrix, roc_auc_score

from .constants import CENTER_BY_SOURCE, CLASS_NAMES, N_CLASSES


def center_of(source: str) -> str:
    return CENTER_BY_SOURCE.get(str(source), str(source))


def score_arrays(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    y = np.asarray(y, dtype=int)
    pred = np.asarray(pred, dtype=int)
    n = int(len(y))
    if n == 0:
        return {
            "n": 0,
            "acc": 0.0,
            "adj_acc": 0.0,
            "off2": 0.0,
            "qwk": 0.0,
            "serosa_acc": 0.0,
            "t34_swap": 0.0,
            "macro_recall": 0.0,
            "t2_recall": 0.0,
            **{f"recall_{name}": 0.0 for name in CLASS_NAMES},
        }
    delta = np.abs(y - pred)
    recalls = []
    out: dict[str, float] = {
        "n": n,
        "acc": float(np.mean(y == pred)),
        "adj_acc": float(np.mean(delta <= 1)),
        "off2": float(np.mean(delta >= 2)),
        "qwk": float(cohen_kappa_score(y, pred, weights="quadratic")) if n > 1 else 0.0,
        "serosa_acc": float(np.mean((y >= 3) == (pred >= 3))),
        "t34_swap": float(np.mean(((y == 2) & (pred == 3)) | ((y == 3) & (pred == 2)))),
    }
    for cls, name in enumerate(CLASS_NAMES):
        mask = y == cls
        rec = float(np.mean(pred[mask] == cls)) if mask.any() else 0.0
        out[f"recall_{name}"] = rec
        out[f"n_{name}"] = int(mask.sum())
        recalls.append(rec)
    out["macro_recall"] = float(np.mean(recalls))
    out["t2_recall"] = out["recall_T2"]
    return out


def confusion(y: np.ndarray, pred: np.ndarray) -> list[list[int]]:
    return confusion_matrix(y, pred, labels=list(range(N_CLASSES))).astype(int).tolist()


def per_center(y: np.ndarray, pred: np.ndarray, sources: list[str]) -> list[dict[str, object]]:
    buckets: dict[str, list[int]] = defaultdict(list)
    for i, src in enumerate(sources):
        buckets[center_of(src)].append(i)
    rows = []
    for center in sorted(buckets):
        idx = np.asarray(buckets[center], dtype=int)
        row = score_arrays(y[idx], pred[idx])
        row["center"] = center
        rows.append(row)
    return rows


def score_binary(y: np.ndarray, pred: np.ndarray, logit: np.ndarray | None = None) -> dict[str, float]:
    y = np.asarray(y, dtype=int)
    pred = np.asarray(pred, dtype=int)
    n = int(len(y))
    pos = y == 1
    neg = y == 0
    rec_pos = float(np.mean(pred[pos] == 1)) if pos.any() else 0.0
    rec_neg = float(np.mean(pred[neg] == 0)) if neg.any() else 0.0
    out: dict[str, float] = {
        "n": n,
        "n_pos": int(pos.sum()),
        "n_neg": int(neg.sum()),
        "acc": float(np.mean(y == pred)) if n else 0.0,
        "recall_pos": rec_pos,
        "recall_neg": rec_neg,
        "balanced_acc": float(0.5 * (rec_pos + rec_neg)),
        "prev_true": float(np.mean(y)) if n else 0.0,
        "prev_pred": float(np.mean(pred)) if n else 0.0,
        "auc": 0.0,
    }
    if logit is not None and n > 1 and pos.any() and neg.any():
        out["auc"] = float(roc_auc_score(y, np.asarray(logit, dtype=float)))
    return out


def mcnemar_exact(y: np.ndarray, pred_a: np.ndarray, pred_b: np.ndarray) -> dict[str, float]:
    y = np.asarray(y, dtype=int)
    a_ok = np.asarray(pred_a, dtype=int) == y
    b_ok = np.asarray(pred_b, dtype=int) == y
    n01 = int(np.sum(a_ok & ~b_ok))
    n10 = int(np.sum(~a_ok & b_ok))
    n_disc = n01 + n10
    p_value = 1.0
    if n_disc > 0:
        from scipy.stats import binomtest

        p_value = float(binomtest(n01, n_disc, 0.5, alternative="two-sided").pvalue)
    return {
        "n": int(len(y)),
        "n_a_right_b_wrong": n01,
        "n_a_wrong_b_right": n10,
        "n_discordant": n_disc,
        "p_exact": p_value,
        "acc_a": float(np.mean(a_ok)) if len(y) else 0.0,
        "acc_b": float(np.mean(b_ok)) if len(y) else 0.0,
    }


def md_confusion(matrix: list[list[int]]) -> list[str]:
    header = "| true \\ pred | " + " | ".join(CLASS_NAMES) + " |"
    sep = "|---|" + "---|" * N_CLASSES
    lines = [header, sep]
    for i, name in enumerate(CLASS_NAMES):
        cells = " | ".join(str(matrix[i][j]) for j in range(N_CLASSES))
        lines.append(f"| {name} | {cells} |")
    return lines
