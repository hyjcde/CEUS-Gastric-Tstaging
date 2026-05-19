#!/usr/bin/env python3
"""
Smoke test: run the full abdominal ultrasound Agent ReAct loop on a few patients.

Tests that all components (CaseCard loading, tool execution, LLM
communication, evidence aggregation) work end-to-end.

Usage:
  # Full end-to-end with LLM (requires AGENT_API_KEY or VLM_API_KEY)
  python pipeline/agent/smoke_test.py --mode full --n 3

  # Local-only: test tools without LLM (no API key needed)
  python pipeline/agent/smoke_test.py --mode tools-only --n 5

  # Dry run: test CaseCard loading and tool registration only
  python pipeline/agent/smoke_test.py --mode dry-run
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.core.repo_paths import PROJECT_ROOT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agent.smoke_test")

def build_registry(device=None, enable_rag=False):
    """Register all tools."""
    import torch
    from agent.tools.base import ToolRegistry
    from agent.tools.quality_tool import QualityTool
    from agent.tools.segmentation_tool import SegmentationTool
    from agent.tools.classification_tool import ClassificationTool
    from agent.tools.morphology_tool import MorphologyTool
    from agent.tools.clinical_tool import ClinicalTool
    from agent.tools.similarity_tool import SimilarityTool

    if device is None:
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    registry = ToolRegistry()
    registry.register(QualityTool())
    registry.register(SegmentationTool(device=device))
    registry.register(ClassificationTool(device=device))
    registry.register(MorphologyTool())
    registry.register(ClinicalTool())
    if enable_rag:
        registry.register(SimilarityTool())

    return registry


def load_test_cases(n: int = 5):
    """Load a few CaseCards from the prospective test set."""
    from agent.core.case_card import load_case_cards_from_csv

    csv_path = PROJECT_ROOT / "pipeline" / "data" / "tstaging_4class" / "test_prospective.csv"
    all_cards = load_case_cards_from_csv(csv_path)

    # Pick diverse T-stages
    by_stage = {}
    for card in all_cards:
        stage = card.gt_T_stage or "unknown"
        if stage not in by_stage:
            by_stage[stage] = card

    selected = list(by_stage.values())[:n]
    if len(selected) < n:
        for card in all_cards:
            if card not in selected:
                selected.append(card)
            if len(selected) >= n:
                break

    return selected


def test_dry_run():
    """Test CaseCard loading and tool registration (no GPU/LLM needed)."""
    print("\n=== DRY RUN: CaseCard + Tool Registration ===\n")

    from agent.core.case_card import load_case_cards_from_csv
    csv_path = PROJECT_ROOT / "pipeline" / "data" / "tstaging_4class" / "test_prospective.csv"
    cards = load_case_cards_from_csv(csv_path)
    print(f"Loaded {len(cards)} CaseCards")

    for card in cards[:3]:
        ctx = card.to_agent_context()
        print(f"  Patient {card.patient_id}: {card.num_frames} frames, "
              f"GT={card.gt_T_stage}, context_keys={list(ctx.keys())}")

    # Test registry (no models loaded)
    from agent.tools.base import ToolRegistry
    from agent.tools.quality_tool import QualityTool
    from agent.tools.clinical_tool import ClinicalTool
    registry = ToolRegistry()
    registry.register(QualityTool())
    registry.register(ClinicalTool())
    print(f"\nRegistered tools: {registry.tool_names}")
    print(f"\nTool descriptions:\n{registry.get_all_descriptions()[:500]}...")

    print("\n[OK] Dry run passed.\n")


def test_tools_only(n: int = 3):
    """Test all tools locally without LLM."""
    print(f"\n=== TOOLS-ONLY: Testing {n} patients ===\n")

    cards = load_test_cases(n)
    registry = build_registry()

    for card in cards:
        print(f"\n--- Patient {card.patient_id} (GT: {card.gt_T_stage}) ---")
        for i, frame in enumerate(card.frames[:2]):
            print(f"  Frame {i}: {Path(frame.image_path).name}")

            # Quality
            q = registry.execute("quality_check", image_path=frame.image_path)
            print(f"    Quality: score={q.get('quality_score')}, usable={q.get('usable')}")

            # Segmentation
            seg = registry.execute("segment", image_path=frame.image_path)
            print(f"    Segment: mask={seg.get('mask_available')}, "
                  f"source={seg.get('roi_source')}, area={seg.get('lesion_area_ratio')}")

            # Classification
            cls_kwargs = {"image_path": frame.image_path}
            if frame.predicted_mask_path:
                cls_kwargs["mask_path"] = frame.predicted_mask_path
            if frame.roi_path:
                cls_kwargs["roi_path"] = frame.roi_path
            elif seg.get("roi_bbox"):
                cls_kwargs["roi_bbox"] = seg["roi_bbox"]

            cls = registry.execute("classify", **cls_kwargs)
            print(f"    Classify: top1={cls.get('top1_stage')} "
                  f"({cls.get('top1_prob')}), uncertainty={cls.get('uncertainty')}")

            # Morphology (use predicted mask if available)
            if frame.predicted_mask_path:
                morph = registry.execute("morphology",
                                         mask_path=frame.predicted_mask_path)
                print(f"    Morphology: convexity={morph.get('convexity')}, "
                      f"irregularity={morph.get('boundary_irregularity')}")

        # Clinical
        if card.clinical and card.clinical.has_any():
            clin = registry.execute("clinical_risk", **card.clinical.to_dict())
            print(f"  Clinical: risk={clin.get('clinical_risk_score')}, "
                  f"factors={clin.get('risk_factors')}")

    print(f"\nTool traces: {len(registry.traces)} calls total")
    print("\n[OK] Tools-only test passed.\n")


def test_full(n: int = 3):
    """Full end-to-end test with LLM."""
    print(f"\n=== FULL E2E: Testing {n} patients with LLM ===\n")

    from agent.core.llm_client import AgentLLMClient
    from agent.core.react_loop import run_react_loop
    from agent.core.evidence_hub import EvidenceHub

    cards = load_test_cases(n)
    registry = build_registry(enable_rag=False)
    llm = AgentLLMClient()

    results = []
    for card in cards:
        print(f"\n{'='*60}")
        print(f"Patient {card.patient_id} | GT: {card.gt_T_stage} | "
              f"Frames: {card.num_frames}")
        print(f"{'='*60}")

        result = run_react_loop(card, registry, llm, verbose=True)

        hub = EvidenceHub()
        report = hub.aggregate(result, card.num_frames)

        print(f"\n  Predicted: {report.predicted_stage} "
              f"(confidence: {report.confidence})")
        print(f"  Secondary: {report.secondary_candidate}")
        print(f"  Steps: {report.num_react_steps}, "
              f"Tool calls: {report.num_tool_calls}")
        print(f"  Agreement: {report.frame_agreement_rate:.2f}")
        if report.conflicting_evidence:
            print(f"  Conflicts: {report.conflicting_evidence}")
        print(f"  Manual review: {report.manual_review_recommended}")

        # T4a/T4b → T4+ normalisation for correctness check
        _STAGE_MAP = {"T4a": "T4+", "T4b": "T4+", "T4": "T4+"}
        gt_norm = _STAGE_MAP.get(card.gt_T_stage, card.gt_T_stage)
        pred_norm = _STAGE_MAP.get(report.predicted_stage, report.predicted_stage)
        correct = (pred_norm == gt_norm)
        print(f"  Correct: {'YES' if correct else 'NO'}")

        results.append({
            "patient_id": card.patient_id,
            "gt": card.gt_T_stage,
            "predicted": report.predicted_stage,
            "correct": correct,
            "confidence": report.confidence,
            "steps": report.num_react_steps,
        })

    # Summary
    print(f"\n{'='*60}")
    print("SMOKE TEST SUMMARY")
    print(f"{'='*60}")
    n_correct = sum(1 for r in results if r["correct"])
    print(f"Correct: {n_correct}/{len(results)}")
    for r in results:
        mark = "OK" if r["correct"] else "WRONG"
        print(f"  [{mark}] {r['patient_id']}: GT={r['gt']} → "
              f"Pred={r['predicted']} (conf={r['confidence']}, "
              f"steps={r['steps']})")

    # Save traces
    output_dir = PROJECT_ROOT / "pipeline" / "experiments" / "agent_smoke_test"
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "smoke_test_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_dir}")
    print("\n[OK] Full E2E smoke test completed.\n")


def main():
    parser = argparse.ArgumentParser(description="abdominal ultrasound Agent smoke test")
    parser.add_argument("--mode", choices=["dry-run", "tools-only", "full"],
                        default="dry-run")
    parser.add_argument("--n", type=int, default=3,
                        help="Number of patients to test")
    parser.add_argument("--gpu", type=str, default="0")
    args = parser.parse_args()

    import os
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", args.gpu)

    if args.mode == "dry-run":
        test_dry_run()
    elif args.mode == "tools-only":
        test_tools_only(args.n)
    elif args.mode == "full":
        test_full(args.n)


if __name__ == "__main__":
    main()
