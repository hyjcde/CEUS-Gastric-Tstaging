#!/usr/bin/env python3
"""
Agent evaluation main script — run ablation experiments on test sets.

Usage:
  # Run full agent on prospective + external test sets
  python pipeline/agent/evaluation/run_agent_eval.py \\
    --ablation agent_full \\
    --splits test_prospective,test_external

  # Run all ablation configs
  python pipeline/agent/evaluation/run_agent_eval.py --ablation all

  # Baselines only (no LLM needed)
  python pipeline/agent/evaluation/run_agent_eval.py \\
    --ablation baseline_single,baseline_avg

  # Custom output
  python pipeline/agent/evaluation/run_agent_eval.py \\
    --ablation agent_full \\
    --output pipeline/experiments/agent_eval/
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.core.repo_paths import PROJECT_ROOT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agent.eval")

CLASS_NAMES = ["T1", "T2", "T3", "T4+"]
STAGE_TO_LABEL = {"T1": 0, "T2": 1, "T3": 2, "T4+": 3,
                   "T4a": 3, "T4b": 3, "T4": 3}


def run_baseline(cards, ablation_name, registry):
    """Run baseline methods (no LLM)."""
    from agent.evaluation.baselines import run_baselines_for_patient
    from agent.tools.quality_tool import QualityTool

    results = []
    for card in cards:
        # Run classification on each frame
        cls_results = []
        quality_scores = []
        for frame in card.frames:
            cls_kwargs = {"image_path": frame.image_path}
            if frame.predicted_mask_path:
                cls_kwargs["mask_path"] = frame.predicted_mask_path
            if frame.roi_path:
                cls_kwargs["roi_path"] = frame.roi_path

            cls_out = registry.execute("classify", **cls_kwargs)
            cls_results.append(cls_out)

            q_out = registry.execute("quality_check",
                                      image_path=frame.image_path)
            quality_scores.append(q_out.get("quality_score", 1.0))

        baselines = run_baselines_for_patient(cls_results, quality_scores)

        method_key = ablation_name  # "baseline_single" or "baseline_avg"
        result = baselines.get(method_key, baselines.get("baseline_avg", {}))

        results.append({
            "patient_id": card.patient_id,
            "gt_T_stage": card.gt_T_stage,
            "predicted_stage": result.get("predicted_stage"),
            "method": method_key,
            "num_frames": card.num_frames,
            "aggregated_probs": result.get("averaged_probs"),
        })

    return results


def run_rule_based(cards, registry):
    """
    Agent-Full-NoLLM: all tools, but fixed rule-based scheduling.

    Fixed pipeline: quality → segment → classify → morphology → clinical → RAG
    Final decision: quality-weighted average probabilities.
    """
    from agent.evaluation.baselines import baseline_average
    from agent.memory.feature_extractor import extract_patient_vector

    results = []
    for card in cards:
        cls_results = []
        morph_results = []
        quality_scores = []

        for frame in card.frames:
            q_out = registry.execute("quality_check",
                                      image_path=frame.image_path)
            quality_scores.append(q_out.get("quality_score", 1.0))
            if not q_out.get("usable", True):
                continue

            seg_out = registry.execute("segment",
                                        image_path=frame.image_path)

            cls_kwargs = {"image_path": frame.image_path}
            if frame.predicted_mask_path:
                cls_kwargs["mask_path"] = frame.predicted_mask_path
            if frame.roi_path:
                cls_kwargs["roi_path"] = frame.roi_path
            elif seg_out.get("roi_bbox"):
                cls_kwargs["roi_bbox"] = seg_out["roi_bbox"]

            cls_out = registry.execute("classify", **cls_kwargs)
            cls_results.append(cls_out)

            if frame.predicted_mask_path:
                morph_out = registry.execute("morphology",
                                              mask_path=frame.predicted_mask_path)
                morph_results.append(morph_out)

        # Clinical
        clinical_out = None
        if card.clinical and card.clinical.has_any():
            clinical_out = registry.execute("clinical_risk",
                                             **card.clinical.to_dict())

        # RAG (if index available)
        rag_out = None
        if cls_results:
            clin_dict = card.clinical.to_dict() if card.clinical else None
            vec = extract_patient_vector(cls_results, morph_results, clin_dict)
            rag_out = registry.execute("retrieve_similar",
                                        query_vector=vec.tolist())

        # Decision: quality-weighted average
        avg = baseline_average(cls_results, quality_scores,
                                use_quality_weights=True)

        results.append({
            "patient_id": card.patient_id,
            "gt_T_stage": card.gt_T_stage,
            "predicted_stage": avg.get("predicted_stage"),
            "method": "agent_full_nollm",
            "num_frames": card.num_frames,
            "aggregated_probs": avg.get("averaged_probs"),
            "rag_used": rag_out is not None and rag_out.get("available", False),
        })

    return results


def run_agent(cards, ablation_cfg, registry, llm):
    """Run the full LLM-based agent."""
    from agent.core.react_loop import run_react_loop
    from agent.core.evidence_hub import EvidenceHub

    results = []
    for i, card in enumerate(cards):
        logger.info("Agent processing patient %d/%d: %s (GT: %s)",
                      i + 1, len(cards), card.patient_id, card.gt_T_stage)

        agent_result = run_react_loop(
            card, registry, llm,
            max_steps=ablation_cfg.max_steps,
            verbose=False,
        )

        hub = EvidenceHub()
        report = hub.aggregate(agent_result, card.num_frames)

        results.append({
            "patient_id": card.patient_id,
            "gt_T_stage": card.gt_T_stage,
            "predicted_stage": report.predicted_stage,
            "method": ablation_cfg.name,
            "confidence": report.confidence,
            "num_frames": card.num_frames,
            "num_react_steps": report.num_react_steps,
            "num_tool_calls": report.num_tool_calls,
            "rag_used": report.rag_used,
            "manual_review_recommended": report.manual_review_recommended,
            "aggregated_probs": report.aggregated_probs,
            "conflicting_evidence": report.conflicting_evidence,
        })

    return results


def evaluate_split(split_name, ablation_name, ablation_cfg,
                   registry, llm, output_dir):
    """Evaluate one ablation config on one data split."""
    from agent.core.case_card import load_case_cards_from_csv
    from agent.evaluation.metrics import (
        compute_classification_metrics, compute_agent_metrics)

    csv_path = (PROJECT_ROOT / "pipeline" / "data" / "tstaging_4class"
                / f"{split_name}.csv")
    if not csv_path.exists():
        logger.warning("CSV not found: %s, skipping", csv_path)
        return None

    cards = load_case_cards_from_csv(csv_path)
    logger.info("Loaded %d patients from %s", len(cards), split_name)

    t0 = time.time()

    # Choose execution path
    if not ablation_cfg.use_llm:
        if ablation_name in ("baseline_single", "baseline_avg"):
            results = run_baseline(cards, ablation_name, registry)
        else:
            results = run_rule_based(cards, registry)
    else:
        results = run_agent(cards, ablation_cfg, registry, llm)

    elapsed = time.time() - t0

    # Compute metrics
    predictions = [r["predicted_stage"] or "unknown" for r in results]
    ground_truths = [r["gt_T_stage"] or "unknown" for r in results]
    pred_probs = [r.get("aggregated_probs") for r in results]

    cls_metrics = compute_classification_metrics(
        predictions, ground_truths, pred_probs)
    agent_metrics = compute_agent_metrics(results) if ablation_cfg.use_llm else {}

    # Save results
    split_dir = output_dir / ablation_name / split_name
    split_dir.mkdir(parents=True, exist_ok=True)

    with open(split_dir / "patient_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    summary = {
        "ablation": ablation_name,
        "split": split_name,
        "elapsed_s": round(elapsed, 1),
        **cls_metrics,
        **agent_metrics,
    }
    with open(split_dir / "test_results.json", "w") as f:
        json.dump(summary, f, indent=2)

    logger.info("%s/%s: BalAcc=%.4f F1=%.4f T2T3-Conf=%.4f (%.1fs)",
                 ablation_name, split_name,
                 cls_metrics.get("balanced_accuracy", 0),
                 cls_metrics.get("f1_macro", 0),
                 cls_metrics.get("t2t3_confusion_rate", 0),
                 elapsed)

    return summary


def main():
    parser = argparse.ArgumentParser(description="abdominal ultrasound Agent evaluation")
    parser.add_argument("--ablation", type=str, default="agent_full",
                        help="Comma-separated ablation names, or 'all'")
    parser.add_argument("--splits", type=str,
                        default="test_prospective,test_external",
                        help="Comma-separated split names")
    parser.add_argument("--output", type=str,
                        default="pipeline/experiments/agent_eval/")
    parser.add_argument("--gpu", type=str, default="0")
    args = parser.parse_args()

    os.environ.setdefault("CUDA_VISIBLE_DEVICES", args.gpu)

    from agent.evaluation.ablation import (
        ABLATION_CONFIGS, get_ablation_config, list_ablation_configs)
    from agent.smoke_test import build_registry

    import torch
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    output_dir = PROJECT_ROOT / args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parse ablation configs
    if args.ablation == "all":
        ablation_names = list_ablation_configs()
    else:
        ablation_names = [s.strip() for s in args.ablation.split(",")]

    split_names = [s.strip() for s in args.splits.split(",")]

    # Build registry with all tools
    needs_rag = any(get_ablation_config(a).use_rag for a in ablation_names)
    registry = build_registry(device=device, enable_rag=needs_rag)

    # LLM client (only needed for LLM-based ablations)
    llm = None
    needs_llm = any(get_ablation_config(a).use_llm for a in ablation_names)
    if needs_llm:
        try:
            from agent.core.llm_client import AgentLLMClient
            llm = AgentLLMClient()
        except Exception as e:
            logger.warning("Could not create LLM client: %s. "
                            "LLM-based ablations will be skipped.", e)

    # Run experiments
    all_summaries = []
    for ablation_name in ablation_names:
        cfg = get_ablation_config(ablation_name)
        logger.info("\n%s\nAblation: %s — %s\n%s",
                     "=" * 60, cfg.name, cfg.description, "=" * 60)

        if cfg.use_llm and llm is None:
            logger.warning("Skipping %s (no LLM client)", ablation_name)
            continue

        for split_name in split_names:
            summary = evaluate_split(
                split_name, ablation_name, cfg, registry, llm, output_dir)
            if summary:
                all_summaries.append(summary)

    # Write ablation summary
    if all_summaries:
        with open(output_dir / "ablation_summary.json", "w") as f:
            json.dump(all_summaries, f, indent=2)

        # Print comparison table
        print(f"\n{'='*80}")
        print("ABLATION SUMMARY")
        print(f"{'='*80}")
        print(f"{'Method':<25s} {'Split':<20s} {'BalAcc':>8s} {'F1':>8s} "
              f"{'T2T3Conf':>8s} {'N':>5s}")
        print("-" * 80)
        for s in all_summaries:
            print(f"{s['ablation']:<25s} {s['split']:<20s} "
                  f"{s.get('balanced_accuracy', 0):8.4f} "
                  f"{s.get('f1_macro', 0):8.4f} "
                  f"{s.get('t2t3_confusion_rate', 0):8.4f} "
                  f"{s.get('n_patients', 0):5d}")

        logger.info("Results saved to %s", output_dir)


if __name__ == "__main__":
    main()
