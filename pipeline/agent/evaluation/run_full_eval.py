#!/usr/bin/env python3
"""
Full Agent evaluation with comprehensive logging.

Runs the LLM-based agent on every patient in test_prospective.csv,
saving detailed per-patient ReAct traces, tool observations, and
an aggregate summary report.

Usage:
  POE_API_KEY="..." python pipeline/agent/evaluation/run_full_eval.py
  POE_API_KEY="..." python pipeline/agent/evaluation/run_full_eval.py --split test_external
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.core.repo_paths import PROJECT_ROOT

STAGE_NORM = {"T4a": "T4+", "T4b": "T4+", "T4": "T4+"}


def setup_logging(log_dir: Path) -> logging.Logger:
    """Configure dual logging: file (DEBUG) + console (INFO)."""
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"eval_{ts}.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # File handler — captures everything
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    # Console handler — INFO+ only
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    root.addHandler(fh)
    root.addHandler(ch)

    logger = logging.getLogger("agent.full_eval")
    logger.info("Log file: %s", log_file)
    return logger


def save_react_trace(patient_id: str, agent_result, report, card,
                     traces_dir: Path):
    """Save a single patient's full ReAct trace as JSON."""
    gt_norm = STAGE_NORM.get(card.gt_T_stage, card.gt_T_stage)
    pred_norm = STAGE_NORM.get(report.predicted_stage, report.predicted_stage)

    trace = {
        "patient_id": patient_id,
        "gt_T_stage": card.gt_T_stage,
        "gt_normalised": gt_norm,
        "num_frames": card.num_frames,
        "data_source": card.data_source,
        "clinical_available": card.clinical is not None and card.clinical.has_any(),
        "clinical_context": (card.clinical.to_agent_dict()
                             if card.clinical and card.clinical.has_any()
                             else None),
        "prediction": {
            "predicted_stage": report.predicted_stage,
            "predicted_normalised": pred_norm,
            "secondary_candidate": report.secondary_candidate,
            "confidence": report.confidence,
            "correct": pred_norm == gt_norm,
            "manual_review_recommended": report.manual_review_recommended,
        },
        "aggregated_probs": report.aggregated_probs,
        "evidence": {
            "key_evidence": report.key_evidence,
            "conflicting_evidence": report.conflicting_evidence,
            "frame_agreement_rate": report.frame_agreement_rate,
            "rag_used": report.rag_used,
        },
        "react_steps": [],
        "agent_meta": {
            "num_react_steps": report.num_react_steps,
            "num_tool_calls": report.num_tool_calls,
            "total_tokens": agent_result.total_tokens,
            "total_time_s": round(agent_result.total_time_s, 2),
        },
    }

    for step in agent_result.steps:
        trace["react_steps"].append({
            "step": step.step,
            "thought": step.thought,
            "action": step.action_name,
            "params": _sanitise(step.action_params),
            "observation": _sanitise(step.observation),
            "elapsed_s": step.elapsed_s,
        })

    out_file = traces_dir / f"patient_{patient_id}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(trace, f, indent=2, ensure_ascii=False, default=str)


def _sanitise(obj):
    """Make an object JSON-serialisable."""
    if isinstance(obj, dict):
        return {k: _sanitise(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitise(v) for v in obj]
    if isinstance(obj, float):
        if obj != obj:  # NaN
            return None
        return round(obj, 6) if abs(obj) < 1e10 else str(obj)
    return obj


def main():
    parser = argparse.ArgumentParser(description="Full Agent evaluation with logging")
    parser.add_argument("--split", type=str, default="test_prospective",
                        help="Which CSV split to evaluate")
    parser.add_argument("--gpu", type=str, default="0")
    parser.add_argument("--max-steps", type=int, default=8)
    args = parser.parse_args()

    os.environ.setdefault("CUDA_VISIBLE_DEVICES", args.gpu)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = PROJECT_ROOT / "pipeline" / "experiments" / f"agent_full_eval_{ts}"
    traces_dir = run_dir / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(run_dir)
    logger.info("=" * 70)
    logger.info("abdominal ultrasound Agent Full Evaluation")
    logger.info("Split: %s | Max steps: %d | Run dir: %s",
                args.split, args.max_steps, run_dir)
    logger.info("=" * 70)

    # -- Load models and tools --
    import torch
    from agent.core.case_card import load_case_cards_from_csv
    from agent.core.llm_client import AgentLLMClient
    from agent.core.react_loop import run_react_loop
    from agent.core.evidence_hub import EvidenceHub
    from agent.core.registry_factory import build_default_registry

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    logger.info("Device: %s", device)

    registry = build_default_registry(device=device, enable_rag=False)
    llm = AgentLLMClient()
    logger.info("LLM model: %s | base_url: %s", llm.model, llm._client.base_url)

    csv_path = (PROJECT_ROOT / "pipeline" / "data" / "tstaging_4class"
                / f"{args.split}.csv")
    cards = load_case_cards_from_csv(csv_path)
    logger.info("Loaded %d patients from %s", len(cards), csv_path.name)

    # -- Run evaluation --
    results = []
    stage_counts = {"correct": 0, "wrong": 0, "adjacent": 0}
    STAGE_ORDER = {"T1": 0, "T2": 1, "T3": 2, "T4+": 3}

    t_global = time.time()
    for i, card in enumerate(cards):
        logger.info("-" * 60)
        logger.info("[%d/%d] Patient %s | GT: %s | Frames: %d",
                    i + 1, len(cards), card.patient_id,
                    card.gt_T_stage, card.num_frames)

        t0 = time.time()
        try:
            agent_result = run_react_loop(
                card, registry, llm,
                max_steps=args.max_steps,
                verbose=True,
            )
        except Exception as e:
            logger.error("Agent failed for patient %s: %s", card.patient_id, e)
            results.append({
                "patient_id": card.patient_id,
                "gt_T_stage": card.gt_T_stage,
                "predicted_stage": "ERROR",
                "correct": False,
                "error": str(e),
            })
            continue

        hub = EvidenceHub()
        report = hub.aggregate(agent_result, card.num_frames)
        elapsed = time.time() - t0

        gt_norm = STAGE_NORM.get(card.gt_T_stage, card.gt_T_stage)
        pred_norm = STAGE_NORM.get(report.predicted_stage, report.predicted_stage)
        correct = pred_norm == gt_norm

        # Check adjacency
        gt_ord = STAGE_ORDER.get(gt_norm, -1)
        pred_ord = STAGE_ORDER.get(pred_norm, -1)
        adjacent = (not correct) and abs(gt_ord - pred_ord) == 1

        if correct:
            stage_counts["correct"] += 1
        elif adjacent:
            stage_counts["adjacent"] += 1
        else:
            stage_counts["wrong"] += 1

        mark = "OK" if correct else ("ADJ" if adjacent else "WRONG")
        logger.info("[%s] Patient %s: GT=%s -> Pred=%s (conf=%s, steps=%d, %.1fs)",
                    mark, card.patient_id, card.gt_T_stage,
                    report.predicted_stage, report.confidence,
                    report.num_react_steps, elapsed)

        # Save full trace
        save_react_trace(card.patient_id, agent_result, report, card, traces_dir)

        result_entry = {
            "patient_id": card.patient_id,
            "gt_T_stage": card.gt_T_stage,
            "gt_normalised": gt_norm,
            "predicted_stage": report.predicted_stage,
            "predicted_normalised": pred_norm,
            "correct": correct,
            "adjacent_error": adjacent,
            "secondary_candidate": report.secondary_candidate,
            "confidence": report.confidence,
            "num_react_steps": report.num_react_steps,
            "num_tool_calls": report.num_tool_calls,
            "manual_review_recommended": report.manual_review_recommended,
            "frame_agreement_rate": report.frame_agreement_rate,
            "rag_used": report.rag_used,
            "aggregated_probs": report.aggregated_probs,
            "conflicting_evidence": report.conflicting_evidence,
            "total_tokens": agent_result.total_tokens,
            "elapsed_s": round(elapsed, 2),
        }
        results.append(result_entry)

        # Running accuracy
        done = i + 1
        running_acc = stage_counts["correct"] / done
        logger.info("Running: %d/%d correct (%.1f%%), %d adjacent, %d wrong",
                    stage_counts["correct"], done, running_acc * 100,
                    stage_counts["adjacent"], stage_counts["wrong"])

    total_elapsed = time.time() - t_global

    # -- Compute final metrics --
    from agent.evaluation.metrics import compute_classification_metrics

    predictions = [r.get("predicted_stage", "unknown") for r in results]
    ground_truths = [r.get("gt_T_stage", "unknown") for r in results]
    pred_probs = [r.get("aggregated_probs") for r in results]

    cls_metrics = compute_classification_metrics(predictions, ground_truths, pred_probs)

    # -- Save all results --
    with open(run_dir / "patient_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    summary = {
        "split": args.split,
        "n_patients": len(results),
        "timestamp": ts,
        "total_elapsed_s": round(total_elapsed, 1),
        "avg_time_per_patient_s": round(total_elapsed / max(len(results), 1), 1),
        "model": llm.model,
        "max_steps": args.max_steps,
        "exact_match": {
            "correct": stage_counts["correct"],
            "adjacent": stage_counts["adjacent"],
            "wrong": stage_counts["wrong"],
            "accuracy": round(stage_counts["correct"] / max(len(results), 1), 4),
            "accuracy_with_adjacent": round(
                (stage_counts["correct"] + stage_counts["adjacent"])
                / max(len(results), 1), 4),
        },
        "classification_metrics": cls_metrics,
        "agent_meta": {
            "avg_steps": round(sum(r.get("num_react_steps", 0) for r in results)
                               / max(len(results), 1), 2),
            "avg_tool_calls": round(sum(r.get("num_tool_calls", 0) for r in results)
                                    / max(len(results), 1), 2),
            "total_tokens": sum(r.get("total_tokens", 0) for r in results),
            "manual_review_rate": round(
                sum(1 for r in results if r.get("manual_review_recommended"))
                / max(len(results), 1), 4),
        },
    }

    with open(run_dir / "eval_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # -- Print final report --
    logger.info("=" * 70)
    logger.info("EVALUATION COMPLETE")
    logger.info("=" * 70)
    logger.info("Split: %s | Patients: %d | Total time: %.1fs",
                args.split, len(results), total_elapsed)
    logger.info("")
    logger.info("ACCURACY:")
    logger.info("  Exact match:   %d/%d (%.1f%%)",
                stage_counts["correct"], len(results),
                stage_counts["correct"] / max(len(results), 1) * 100)
    logger.info("  Adjacent err:  %d/%d",
                stage_counts["adjacent"], len(results))
    logger.info("  Gross error:   %d/%d",
                stage_counts["wrong"], len(results))
    logger.info("")
    logger.info("CLASSIFICATION METRICS:")
    logger.info("  Balanced Accuracy: %.4f",
                cls_metrics.get("balanced_accuracy", 0))
    logger.info("  F1 (macro):        %.4f",
                cls_metrics.get("f1_macro", 0))
    logger.info("  T2/T3 confusion:   %.4f",
                cls_metrics.get("t2t3_confusion_rate", 0))
    logger.info("")
    logger.info("AGENT STATS:")
    logger.info("  Avg steps/patient: %.1f", summary["agent_meta"]["avg_steps"])
    logger.info("  Avg tool calls:    %.1f", summary["agent_meta"]["avg_tool_calls"])
    logger.info("  Manual review %%:   %.1f%%",
                summary["agent_meta"]["manual_review_rate"] * 100)
    logger.info("")

    # Per-class breakdown
    from collections import Counter
    gt_dist = Counter(r["gt_normalised"] for r in results if "gt_normalised" in r)
    correct_per_class = Counter()
    for r in results:
        if r.get("correct"):
            correct_per_class[r["gt_normalised"]] += 1

    logger.info("PER-CLASS ACCURACY:")
    for stage in ["T1", "T2", "T3", "T4+"]:
        n = gt_dist.get(stage, 0)
        c = correct_per_class.get(stage, 0)
        acc = c / n * 100 if n > 0 else 0
        logger.info("  %s: %d/%d (%.1f%%)", stage, c, n, acc)

    logger.info("")
    logger.info("All results saved to: %s", run_dir)
    logger.info("Per-patient traces in: %s/", traces_dir)

    # Print one-line per patient to console
    print(f"\n{'='*80}")
    print("PATIENT-LEVEL RESULTS")
    print(f"{'='*80}")
    print(f"{'PID':<12} {'GT':<6} {'Pred':<6} {'2nd':<6} "
          f"{'Conf':<8} {'Steps':>5} {'Time':>6} {'Result'}")
    print("-" * 80)
    for r in results:
        mark = ("OK" if r["correct"]
                else ("ADJ" if r.get("adjacent_error") else "WRONG"))
        print(f"{r['patient_id']:<12} {r['gt_T_stage']:<6} "
              f"{r.get('predicted_stage','?'):<6} "
              f"{r.get('secondary_candidate',''):<6} "
              f"{r.get('confidence',''):<8} "
              f"{r.get('num_react_steps',0):>5} "
              f"{r.get('elapsed_s',0):>6.1f}s "
              f"{mark}")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
