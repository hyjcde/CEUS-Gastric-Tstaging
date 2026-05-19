#!/usr/bin/env python3
"""Sync curated result/case figures into docs/mainline/figures/results/ (single folder).

Sources: manuscript export, pipeline experiment reports, tmp agent predictions.

  python scripts/sync_project_logic_result_figures.py
  python scripts/sync_project_logic_result_figures.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT = PROJECT_ROOT / "docs" / "mainline" / "figures" / "results"
MANUSCRIPT = (
    PROJECT_ROOT
    / "docs copy"
    / "export_text_media_20260408"
    / "media_and_large_files"
    / "manuscript"
    / "figures"
)
PIPELINE_REPORTS = PROJECT_ROOT / "pipeline" / "experiments" / "reports"
AGENT_CASE_DIRS = [
    PROJECT_ROOT / "tmp" / "agent_predictions" / "x" / "1451370_20260519T041253Z",
    PROJECT_ROOT / "tmp" / "agent_predictions" / "agent_batch_smoke" / "1166650_20260519T100101Z",
]
SEG_REPORT = (
    PROJECT_ROOT
    / "experiments"
    / "segmentation"
    / "dinov3_vitb16_last2blocks_mlp_refine_boundary005_640_long_20260514_174620"
    / "report"
)


def slug(name: str, max_len: int = 80) -> str:
    s = re.sub(r"[^\w.\-]+", "_", name, flags=re.UNICODE)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:max_len] if len(s) > max_len else s


def copy_pair(src: Path, dest_name: str, manifest: list[dict]) -> None:
    if not src.is_file():
        return
    dest = OUT / dest_name
    shutil.copy2(src, dest)
    manifest.append(
        {
            "file": dest_name,
            "source": str(src.relative_to(PROJECT_ROOT)),
            "bytes": src.stat().st_size,
        }
    )


def pick_first_existing(parent: Path, names: list[str]) -> Path | None:
    for n in names:
        p = parent / n
        if p.is_file():
            return p
    return None


def copy_dir_samples(
    src_dir: Path,
    prefix: str,
    manifest: list[dict],
    limit: int = 99,
    pattern: str = "*.png",
) -> int:
    if not src_dir.is_dir():
        return 0
    n = 0
    for p in sorted(src_dir.glob(pattern))[:limit]:
        if not p.is_file():
            continue
        dest_name = f"{prefix}_{slug(p.stem)}.png"
        copy_pair(p, dest_name, manifest)
        n += 1
    return n


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if OUT.exists() and not args.dry_run:
        shutil.rmtree(OUT)
    if not args.dry_run:
        OUT.mkdir(parents=True)

    manifest: list[dict] = []

    # --- metrics: generated from scoreboard + eval JSON (not manuscript) ---
    if not args.dry_run:
        import subprocess

        gen = PROJECT_ROOT / "scripts" / "generate_mainline_metric_figures.py"
        if gen.is_file():
            subprocess.run([sys.executable, str(gen)], check=True, cwd=PROJECT_ROOT)
        for png in sorted(OUT.glob("metric_*.png")):
            manifest.append(
                {
                    "file": png.name,
                    "source": "scripts/generate_mainline_metric_figures.py",
                    "bytes": png.stat().st_size,
                }
            )

    # --- pipeline full cases (T1–T4+) ---
    copy_dir_samples(MANUSCRIPT / "10_pipeline_cases", "case_pipeline", manifest, limit=12)

    # --- boundary morphology: 2 per T stage prefix ---
    boundary_dir = MANUSCRIPT / "07_boundary_morphology"
    if boundary_dir.is_dir():
        for stage in ("T1_", "T2_", "T3_", "T4"):
            matches = sorted(boundary_dir.glob(f"{stage}*.png"))[:2]
            for p in matches:
                copy_pair(p, f"case_boundary_{slug(p.stem)}.png", manifest)

    # --- gradcam 4-class: correct + error samples ---
    gradcam_root = MANUSCRIPT / "06_gradcam_4class"
    for sub in (
        "T1_misclassified_as_T2",
        "T2_correct",
        "T3_correct",
        "T3_misclassified_as_T4+",
        "T4p_correct",
        "T4p_misclassified_as_T3",
    ):
        d = gradcam_root / sub
        if d.is_dir():
            for p in sorted(d.glob("*.png"))[:2]:
                copy_pair(p, f"case_gradcam_{slug(sub)}_{slug(p.stem)}.png", manifest)
    for p in sorted(gradcam_root.glob("pair*.png"))[:6]:
        copy_pair(p, f"case_gradcam_{slug(p.stem)}.png", manifest)
    overview = gradcam_root / "00_overview_gradcam.png"
    copy_pair(overview, "case_gradcam_overview.png", manifest)

    # --- fusion VLM demo ---
    copy_pair(
        MANUSCRIPT / "14_fusion_vlm" / "demo_Surgery_2025_7M_1000937 (1).png",
        "case_fusion_vlm_demo.png",
        manifest,
    )
    copy_pair(
        MANUSCRIPT / "14_fusion_vlm" / "fusion_comparison.png",
        "case_fusion_vlm_comparison.png",
        manifest,
    )

    # --- segmentation ---
    seg_jobs = [
        (MANUSCRIPT / "03_segmentation_sam2" / "sam2_eval_comparison.png", "seg_sam2_eval.png"),
        (MANUSCRIPT / "03_segmentation_sam2" / "cascade_eval_comparison.png", "seg_cascade_eval.png"),
        (MANUSCRIPT / "03_segmentation_sam2" / "compare_prospective.png", "seg_compare_prospective.png"),
        (MANUSCRIPT / "03_segmentation_sam2" / "mask_prompt_comparison.png", "seg_mask_prompt.png"),
        (MANUSCRIPT / "11_roi_comparison" / "roi_comparison_gt_vs_predicted.png", "seg_roi_gt_vs_pred.png"),
        (MANUSCRIPT / "fig2_segmentation_comparison.png", "seg_multicenter_comparison.png"),
    ]
    for src, dest in seg_jobs:
        if not args.dry_run:
            copy_pair(src, dest, manifest)
        elif src.is_file():
            manifest.append({"file": dest, "source": str(src.relative_to(PROJECT_ROOT))})

    if SEG_REPORT.is_dir():
        for name in ("evaluation_summary.png", "training_curves.png"):
            copy_pair(SEG_REPORT / name, f"seg_dinov3_{name.replace('.png', '')}.png", manifest)

    # --- pipeline RF case panels (lesion focus, external) ---
    rf_roots = [
        PIPELINE_REPORTS
        / "framelevel_rf_external_by_source"
        / "ext_putian_2024_lesion_focus_panels",
        PIPELINE_REPORTS
        / "framelevel_rf_external_by_source"
        / "ext_zhongliu_case_panels_v2",
        PIPELINE_REPORTS
        / "framelevel_rf_external_by_source"
        / "ext_multicenter_case_panels_v2",
    ]
    for root in rf_roots:
        if not root.is_dir():
            continue
        tag = slug(root.name)
        for sub in ("correct_high_conf", "errors_high_conf", "t2_t3_boundary"):
            d = root / sub
            copy_dir_samples(d, f"case_rf_{tag}_{sub}", manifest, limit=4)

    # --- dehua gradcam smoke overlays ---
    dehua = (
        PIPELINE_REPORTS
        / "zip_pipeline_review_gradcam_smoke_20260505"
        / "dehua_gradcam_smoke"
    )
    copy_pair(dehua / "summary_contact_sheet.png", "case_pipeline_dehua_contact_sheet.png", manifest)
    copy_dir_samples(dehua / "case_overlays", "case_pipeline_dehua_overlay", manifest, limit=4)

    # --- agent single-case artifacts ---
    agent_dir = next((d for d in AGENT_CASE_DIRS if d.is_dir()), None)
    if agent_dir:
        patient = agent_dir.name.split("_")[0]
        agent_files = [
            "predicted_overlay.png",
            "predicted_mask.png",
            "predicted_roi.png",
            "classification_probabilities.png",
            "wall_penetration_risk_heatmap.png",
            "wall_layer_profile.png",
            "real_wall_analysis_panel.png",
            "current_image_dino_feature_panel.png",
            "dino_region_similarity_heatmap.png",
            "similar_cases_contact_sheet.png",
            "real_dino_multimodal_visual_panel.png",
        ]
        for fname in agent_files:
            src = agent_dir / fname
            stem = fname.replace(".png", "")
            copy_pair(src, f"case_agent_{patient}_{stem}.png", manifest)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(OUT.relative_to(PROJECT_ROOT)),
        "count": len(manifest),
        "files": manifest,
    }

    if args.dry_run:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    (OUT / "manifest.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Synced {len(manifest)} figures -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
