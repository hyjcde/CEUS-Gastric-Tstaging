#!/usr/bin/env python3
"""
T2/T3 focused analysis and case-level visualisation.

Generates:
  1. T2/T3 boundary case analysis (which cases flipped, why)
  2. Per-patient ReAct trace summary
  3. Error analysis (what types of errors the agent makes)

Usage:
  python pipeline/agent/evaluation/analysis.py \\
    --results pipeline/experiments/agent_eval/agent_full/test_prospective/patient_results.json
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent.core.repo_paths import PROJECT_ROOT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agent.analysis")

STAGE_TO_LABEL = {"T1": 0, "T2": 1, "T3": 2, "T4+": 3,
                   "T4a": 3, "T4b": 3, "T4": 3}


def analyse_t2t3_boundary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Focused analysis on T2/T3 boundary cases.
    """
    t2t3_cases = [r for r in results
                   if r.get("gt_T_stage") in ("T2", "T3")]

    if not t2t3_cases:
        return {"n_t2t3": 0, "message": "No T2/T3 cases found"}

    n_total = len(t2t3_cases)
    n_correct = sum(1 for r in t2t3_cases
                     if STAGE_TO_LABEL.get(r.get("predicted_stage", ""), -1)
                     == STAGE_TO_LABEL.get(r.get("gt_T_stage", ""), -2))

    # Cases where T2 predicted as T3 or vice versa
    t2_as_t3 = [r for r in t2t3_cases
                 if r.get("gt_T_stage") == "T2"
                 and STAGE_TO_LABEL.get(r.get("predicted_stage", ""), -1) == 2]
    t3_as_t2 = [r for r in t2t3_cases
                 if r.get("gt_T_stage") == "T3"
                 and STAGE_TO_LABEL.get(r.get("predicted_stage", ""), -1) == 1]

    # Cases where RAG helped
    rag_cases = [r for r in t2t3_cases if r.get("rag_used", False)]
    rag_correct = sum(
        1 for r in rag_cases
        if STAGE_TO_LABEL.get(r.get("predicted_stage", ""), -1)
        == STAGE_TO_LABEL.get(r.get("gt_T_stage", ""), -2)
    )

    # Confidence distribution for T2/T3
    conf_dist = {}
    for r in t2t3_cases:
        conf = r.get("confidence", "unknown")
        conf_dist[conf] = conf_dist.get(conf, 0) + 1

    # Manual review flags
    review_count = sum(1 for r in t2t3_cases
                        if r.get("manual_review_recommended", False))

    return {
        "n_t2t3": n_total,
        "n_correct": n_correct,
        "accuracy": round(n_correct / n_total, 4) if n_total > 0 else 0,
        "n_t2_as_t3": len(t2_as_t3),
        "n_t3_as_t2": len(t3_as_t2),
        "t2_as_t3_patients": [r["patient_id"] for r in t2_as_t3],
        "t3_as_t2_patients": [r["patient_id"] for r in t3_as_t2],
        "rag_used_count": len(rag_cases),
        "rag_correct": rag_correct,
        "confidence_distribution": conf_dist,
        "manual_review_count": review_count,
    }


def analyse_errors(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Categorise prediction errors.
    """
    errors = {
        "adjacent": [],       # 1 stage off (e.g., T2→T3)
        "cross_stage": [],    # 2+ stages off (e.g., T1→T3)
        "understaging": [],   # predicted lower than GT
        "overstaging": [],    # predicted higher than GT
    }

    for r in results:
        gt = STAGE_TO_LABEL.get(r.get("gt_T_stage", ""), -1)
        pred = STAGE_TO_LABEL.get(r.get("predicted_stage", ""), -1)
        if gt < 0 or pred < 0 or gt == pred:
            continue

        error_info = {
            "patient_id": r["patient_id"],
            "gt": r["gt_T_stage"],
            "predicted": r["predicted_stage"],
            "confidence": r.get("confidence"),
            "rag_used": r.get("rag_used", False),
        }

        diff = abs(gt - pred)
        if diff == 1:
            errors["adjacent"].append(error_info)
        else:
            errors["cross_stage"].append(error_info)

        if pred < gt:
            errors["understaging"].append(error_info)
        else:
            errors["overstaging"].append(error_info)

    return {
        "total_errors": len(errors["adjacent"]) + len(errors["cross_stage"]),
        "adjacent_errors": len(errors["adjacent"]),
        "cross_stage_errors": len(errors["cross_stage"]),
        "understaging": len(errors["understaging"]),
        "overstaging": len(errors["overstaging"]),
        "details": errors,
    }


def generate_case_summaries(results: List[Dict[str, Any]],
                            output_dir: Path) -> None:
    """Write per-case markdown summaries for interesting cases."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for r in results:
        gt = r.get("gt_T_stage", "unknown")
        pred = r.get("predicted_stage", "unknown")
        correct = (STAGE_TO_LABEL.get(gt, -1) == STAGE_TO_LABEL.get(pred, -2))

        # Only write summaries for borderline or incorrect cases
        is_borderline = gt in ("T2", "T3")
        if correct and not is_borderline:
            continue

        pid = r["patient_id"]
        md = f"# Case {pid}\n\n"
        md += f"- **GT Stage**: {gt}\n"
        md += f"- **Predicted**: {pred}\n"
        md += f"- **Correct**: {'Yes' if correct else 'No'}\n"
        md += f"- **Confidence**: {r.get('confidence', 'unknown')}\n"
        md += f"- **Frames**: {r.get('num_frames', 'N/A')}\n"
        md += f"- **ReAct Steps**: {r.get('num_react_steps', 'N/A')}\n"
        md += f"- **Tool Calls**: {r.get('num_tool_calls', 'N/A')}\n"
        md += f"- **RAG Used**: {r.get('rag_used', False)}\n"
        md += f"- **Manual Review**: {r.get('manual_review_recommended', False)}\n"

        if r.get("conflicting_evidence"):
            md += f"\n## Conflicts\n"
            for c in r["conflicting_evidence"]:
                md += f"- {c}\n"

        if r.get("aggregated_probs"):
            md += f"\n## Aggregated Probabilities\n"
            md += f"```json\n{json.dumps(r['aggregated_probs'], indent=2)}\n```\n"

        with open(output_dir / f"case_{pid}.md", "w") as f:
            f.write(md)

    logger.info("Case summaries written to %s", output_dir)


def main():
    parser = argparse.ArgumentParser(description="T2/T3 analysis")
    parser.add_argument("--results", type=str, required=True,
                        help="Path to patient_results.json")
    parser.add_argument("--output", type=str, default=None,
                        help="Output directory (default: alongside results)")
    args = parser.parse_args()

    results_path = Path(args.results)
    with open(results_path) as f:
        results = json.load(f)

    output_dir = Path(args.output) if args.output else results_path.parent / "analysis"

    # T2/T3 boundary analysis
    t2t3 = analyse_t2t3_boundary(results)
    print("\n=== T2/T3 Boundary Analysis ===")
    print(json.dumps(t2t3, indent=2))

    # Error analysis
    errors = analyse_errors(results)
    print("\n=== Error Analysis ===")
    print(json.dumps({k: v for k, v in errors.items() if k != "details"},
                      indent=2))

    # Save
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "t2t3_analysis.json", "w") as f:
        json.dump(t2t3, f, indent=2)
    with open(output_dir / "error_analysis.json", "w") as f:
        json.dump(errors, f, indent=2, default=str)

    # Case summaries
    generate_case_summaries(results, output_dir / "cases")

    print(f"\nAnalysis saved to {output_dir}")


if __name__ == "__main__":
    main()
