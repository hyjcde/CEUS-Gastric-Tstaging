"""
Agent-specific evaluation metrics beyond standard classification metrics.

Standard metrics (AUC, balanced accuracy, F1) are computed alongside
Agent-specific metrics:
  - Average tool calls per patient
  - Average ReAct steps
  - RAG trigger rate
  - RAG correction rate
  - Manual review recommendation rate
  - T2/T3 confusion rate
  - Cross-stage error rate
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

CLASS_NAMES = ["T1", "T2", "T3", "T4+"]
STAGE_TO_LABEL = {"T1": 0, "T2": 1, "T3": 2, "T4+": 3,
                   "T4a": 3, "T4b": 3, "T4": 3}


def compute_classification_metrics(
    predictions: List[str],
    ground_truths: List[str],
    pred_probs: Optional[List[Dict[str, float]]] = None,
) -> Dict[str, Any]:
    """Compute standard classification metrics at patient level."""
    from sklearn.metrics import (
        balanced_accuracy_score, f1_score, confusion_matrix,
        classification_report,
    )

    # Map stages to labels
    y_true = [STAGE_TO_LABEL.get(gt, -1) for gt in ground_truths]
    y_pred = [STAGE_TO_LABEL.get(p, -1) for p in predictions]

    # Filter out unknown
    valid = [(t, p) for t, p in zip(y_true, y_pred) if t >= 0 and p >= 0]
    if not valid:
        return {"error": "No valid predictions"}

    y_true_f, y_pred_f = zip(*valid)
    y_true_f = list(y_true_f)
    y_pred_f = list(y_pred_f)

    bal_acc = balanced_accuracy_score(y_true_f, y_pred_f)
    f1_macro = f1_score(y_true_f, y_pred_f, average="macro", zero_division=0)
    f1_weighted = f1_score(y_true_f, y_pred_f, average="weighted", zero_division=0)

    cm = confusion_matrix(y_true_f, y_pred_f,
                           labels=list(range(len(CLASS_NAMES))))

    # Per-class recall
    per_class = {}
    for i, name in enumerate(CLASS_NAMES):
        total = int(cm[i].sum())
        correct = int(cm[i, i]) if i < cm.shape[0] and i < cm.shape[1] else 0
        recall = correct / total if total > 0 else 0.0
        per_class[f"recall_{name}"] = round(recall, 4)
        per_class[f"count_{name}"] = total

    # T2-T3 confusion rate
    t2_total = int(cm[1].sum()) if cm.shape[0] > 1 else 0
    t3_total = int(cm[2].sum()) if cm.shape[0] > 2 else 0
    t2_as_t3 = int(cm[1, 2]) if cm.shape[0] > 1 and cm.shape[1] > 2 else 0
    t3_as_t2 = int(cm[2, 1]) if cm.shape[0] > 2 and cm.shape[1] > 1 else 0
    t2t3_confusion = (t2_as_t3 + t3_as_t2) / max(t2_total + t3_total, 1)

    # Cross-stage error (2+ stages apart)
    cross_errors = 0
    total_errors = 0
    for t, p in zip(y_true_f, y_pred_f):
        if t != p:
            total_errors += 1
            if abs(t - p) >= 2:
                cross_errors += 1
    cross_stage_rate = cross_errors / max(len(y_true_f), 1)

    # AUC (if probabilities available)
    auc = None
    if pred_probs:
        try:
            from sklearn.metrics import roc_auc_score
            prob_matrix = np.zeros((len(valid), len(CLASS_NAMES)))
            for i, (_, _) in enumerate(valid):
                if i < len(pred_probs) and pred_probs[i]:
                    for j, name in enumerate(CLASS_NAMES):
                        prob_matrix[i, j] = pred_probs[i].get(name, 0.0)
                else:
                    prob_matrix[i, y_pred_f[i]] = 1.0

            auc = roc_auc_score(y_true_f, prob_matrix,
                                 multi_class="ovr", average="macro")
            auc = round(auc, 4)
        except Exception as e:
            logger.warning("AUC computation failed: %s", e)

    return {
        "balanced_accuracy": round(bal_acc, 4),
        "f1_macro": round(f1_macro, 4),
        "f1_weighted": round(f1_weighted, 4),
        "accuracy": round(sum(1 for t, p in zip(y_true_f, y_pred_f)
                               if t == p) / len(y_true_f), 4),
        "auc": auc,
        "t2t3_confusion_rate": round(t2t3_confusion, 4),
        "cross_stage_error_rate": round(cross_stage_rate, 4),
        "confusion_matrix": cm.tolist(),
        **per_class,
        "n_patients": len(y_true_f),
    }


def compute_agent_metrics(
    reports: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute Agent-specific operational metrics."""
    if not reports:
        return {}

    n = len(reports)

    # Tool calls and steps
    tool_calls = [r.get("num_tool_calls", 0) for r in reports]
    react_steps = [r.get("num_react_steps", 0) for r in reports]

    # RAG metrics
    rag_used = [r.get("rag_used", False) for r in reports]
    rag_trigger_rate = sum(rag_used) / n

    # Manual review
    review_flags = [r.get("manual_review_recommended", False) for r in reports]
    review_rate = sum(review_flags) / n

    # Confidence distribution
    conf_dist = Counter(r.get("confidence", "unknown") for r in reports)

    # Conflict rate
    conflict_count = sum(1 for r in reports
                          if r.get("conflicting_evidence"))
    conflict_rate = conflict_count / n

    return {
        "avg_tool_calls": round(np.mean(tool_calls), 2),
        "avg_react_steps": round(np.mean(react_steps), 2),
        "rag_trigger_rate": round(rag_trigger_rate, 4),
        "manual_review_rate": round(review_rate, 4),
        "conflict_rate": round(conflict_rate, 4),
        "confidence_distribution": dict(conf_dist),
        "n_patients": n,
    }
