"""Run the auditable LangGraph case pipeline (production)."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..core.repo_paths import PROJECT_ROOT
from ..langgraph.case_pipeline.run import run_langgraph_case_pipeline
from .case_input import CaseInput
from .options import PipelineOptions

logger = logging.getLogger(__name__)

# Legacy deterministic loop kept for reference/tests — production uses LangGraph.
run_case_pipeline = run_langgraph_case_pipeline


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run the LangGraph evidence-and-decision Agent pipeline")
    p.add_argument("--case", required=True, help="Case ID e.g. CASE-001")
    p.add_argument(
        "--input-mode",
        choices=("static", "video"),
        default="static",
    )
    p.add_argument(
        "--cases-path",
        type=Path,
        default=PROJECT_ROOT / "docs/clinical_validation/human_ai_comparison/cases.json",
    )
    p.add_argument("--clip", default="clip_01.mp4")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--device", default=None)
    p.add_argument("--triage-mode", choices=("conditional", "soft", "off"), default="conditional")
    p.add_argument("--skip-t-threshold", type=float, default=0.95)
    p.add_argument("--seg-policy", choices=("auto", "unet", "dino"), default="auto")
    p.add_argument("--no-dino", action="store_true")
    p.add_argument("--no-rag", action="store_true")
    p.add_argument("--no-figures", action="store_true")
    return p.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    args = _parse_args()

    if args.input_mode == "static":
        case_input = CaseInput.from_cases_json(args.cases_path, args.case)
    else:
        case_input = CaseInput.from_reader_study_video(args.case, clip=args.clip)

    options = PipelineOptions(
        device=args.device,
        enable_rag=not args.no_rag,
        enable_dino=not args.no_dino,
        triage_mode=args.triage_mode,
        skip_t_threshold=args.skip_t_threshold,
        seg_policy=args.seg_policy,
        render_figures=not args.no_figures,
    )

    state = run_langgraph_case_pipeline(case_input, args.out, options)
    report = state.final_report or {}
    print(
        f"Done: {args.case} → recommended={report.get('recommended_t_stage')} "
        f"steps={len(state.steps)} out={args.out}"
    )


if __name__ == "__main__":
    main()
