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
AGENT_PRIORITY_DIRS = [
    PROJECT_ROOT / "tmp" / "agent_predictions" / "x" / "1451370_20260519T041253Z",
    PROJECT_ROOT / "tmp" / "agent_predictions" / "cursor-real-prediction-verify" / "1451370_20260518T075556Z",
]
AGENT_BATCH_ROOT = PROJECT_ROOT / "tmp" / "agent_predictions" / "agent_batch_smoke"
AGENT_ARTIFACT_FILES = [
    "predicted_overlay.png",
    "predicted_mask.png",
    "predicted_roi.png",
    "classification_probabilities.png",
    "wall_penetration_risk_heatmap.png",
    "real_wall_analysis_panel.png",
    "similar_cases_contact_sheet.png",
    "dino_region_similarity_heatmap.png",
]
MAX_FILE_MB = 4.0
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
    max_mb: float | None = None,
) -> int:
    if not src_dir.is_dir():
        return 0
    n = 0
    for p in sorted(src_dir.glob(pattern)):
        if n >= limit:
            break
        if not p.is_file():
            continue
        if max_mb is not None and p.stat().st_size > max_mb * 1024 * 1024:
            continue
        dest_name = f"{prefix}_{slug(p.stem)}.png"
        copy_pair(p, dest_name, manifest)
        n += 1
    return n


def sync_agent_cases(manifest: list[dict], max_patients: int = 6) -> None:
    seen_patients: set[str] = set()
    dirs: list[Path] = []
    for d in AGENT_PRIORITY_DIRS:
        if d.is_dir() and (d / "predicted_overlay.png").is_file():
            dirs.append(d)
    if AGENT_BATCH_ROOT.is_dir():
        batch = [
            d
            for d in AGENT_BATCH_ROOT.iterdir()
            if d.is_dir() and (d / "predicted_overlay.png").is_file()
        ]
        batch.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        dirs.extend(batch)
    for agent_dir in dirs:
        patient = agent_dir.name.split("_")[0]
        if patient in seen_patients:
            continue
        seen_patients.add(patient)
        if len(seen_patients) > max_patients:
            break
        for fname in AGENT_ARTIFACT_FILES:
            stem = fname.replace(".png", "")
            copy_pair(agent_dir / fname, f"case_agent_{patient}_{stem}.png", manifest)


def sync_gradcam_all(manifest: list[dict]) -> None:
    gradcam_root = MANUSCRIPT / "06_gradcam_4class"
    if not gradcam_root.is_dir():
        return
    for p in sorted(gradcam_root.glob("*.png")):
        copy_pair(p, f"case_gradcam_{slug(p.stem)}.png", manifest)
    for sub in sorted(gradcam_root.iterdir()):
        if not sub.is_dir():
            continue
        copy_dir_samples(sub, f"case_gradcam_{slug(sub.name)}", manifest, limit=4, max_mb=MAX_FILE_MB)


def sync_rf_panels(manifest: list[dict]) -> None:
    rf_base = PIPELINE_REPORTS / "framelevel_rf_external_by_source"
    if not rf_base.is_dir():
        return
    for root in sorted(rf_base.iterdir()):
        if not root.is_dir() or "panel" not in root.name.lower():
            continue
        tag = slug(root.name)
        for sub in sorted(root.iterdir()):
            if sub.is_dir():
                copy_dir_samples(
                    sub,
                    f"case_rf_{tag}_{slug(sub.name)}",
                    manifest,
                    limit=6,
                    max_mb=MAX_FILE_MB,
                )
            elif sub.suffix.lower() == ".png":
                copy_pair(sub, f"case_rf_{tag}_{slug(sub.stem)}.png", manifest)


def sync_report_panels(manifest: list[dict]) -> None:
    panel_dirs = [
        (PIPELINE_REPORTS / "tstaging4_regionaware_true_gradcam_single_20260504" / "panels", "case_regionaware_pros", 10),
        (
            PIPELINE_REPORTS / "tstaging4_regionaware_true_gradcam_single_external_20260504" / "panels",
            "case_regionaware_ext",
            10,
        ),
        (PIPELINE_REPORTS / "tstaging4_error_wall_review_20260426_gradcam" / "panels", "case_error_wall", 12),
        (PIPELINE_REPORTS / "tstaging4_regionaware_error_step_review_20260504" / "panels", "case_regionaware_err", 10),
        (PIPELINE_REPORTS / "gastric_us_multimodal_agent" / "case_visual_panels_v1", "case_multimodal_agent", 8),
        (PIPELINE_REPORTS / "dinov3_unetpp_case_panel", "case_dinov3_unetpp", 12),
    ]
    for src_dir, prefix, limit in panel_dirs:
        copy_dir_samples(src_dir, prefix, manifest, limit=limit, max_mb=MAX_FILE_MB)


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

    # --- boundary morphology: up to 4 per T stage ---
    boundary_dir = MANUSCRIPT / "07_boundary_morphology"
    if boundary_dir.is_dir():
        for stage in ("T1_", "T2_", "T3_", "T4"):
            for p in sorted(boundary_dir.glob(f"{stage}*.png"))[:4]:
                copy_pair(p, f"case_boundary_{slug(p.stem)}.png", manifest)

    sync_gradcam_all(manifest)

    # --- T2 专项分析 ---
    copy_dir_samples(MANUSCRIPT / "13_t2_analysis", "case_t2analysis", manifest, limit=8, max_mb=MAX_FILE_MB)

    # --- 研究总览图（manuscript 主图，非旧指标曲线） ---
    for src_name, dest in (
        ("fig1_study_overview.png", "study_overview.png"),
        ("fig7_morphology_boxplots.png", "study_morphology_boxplots.png"),
        ("fig8b_directional_t2t3.png", "study_directional_t2t3.png"),
        ("fig8_directional_rose.png", "study_directional_rose.png"),
        ("sfig3_t2_misclassification.png", "study_t2_misclassification.png"),
        ("sfig4_boundary_sensitivity.png", "study_boundary_sensitivity.png"),
    ):
        copy_pair(MANUSCRIPT / src_name, dest, manifest)

    # --- 医生复核 / 质控示意（控制单图体积） ---
    copy_dir_samples(
        MANUSCRIPT / "09_doctor_review",
        "case_review",
        manifest,
        limit=14,
        max_mb=MAX_FILE_MB,
    )

    # --- 外部中心 overlay 页（跳过 >4MB 的 internal 大图） ---
    copy_dir_samples(
        MANUSCRIPT / "12_overlay_montage",
        "case_overlay",
        manifest,
        limit=6,
        max_mb=MAX_FILE_MB,
    )

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

    # --- segmentation SAM2 + nnU-Net ---
    seg_jobs = [
        (MANUSCRIPT / "03_segmentation_sam2" / "sam2_eval_comparison.png", "seg_sam2_eval.png"),
        (MANUSCRIPT / "03_segmentation_sam2" / "cascade_eval_comparison.png", "seg_cascade_eval.png"),
        (MANUSCRIPT / "03_segmentation_sam2" / "compare_prospective.png", "seg_compare_prospective.png"),
        (MANUSCRIPT / "03_segmentation_sam2" / "compare_multicenter.png", "seg_compare_multicenter.png"),
        (MANUSCRIPT / "03_segmentation_sam2" / "compare_int_2024.png", "seg_compare_int_2024.png"),
        (MANUSCRIPT / "03_segmentation_sam2" / "mask_prompt_comparison.png", "seg_mask_prompt.png"),
        (MANUSCRIPT / "03_segmentation_sam2" / "training_curves.png", "seg_sam2_training_curves.png"),
        (MANUSCRIPT / "11_roi_comparison" / "roi_comparison_gt_vs_predicted.png", "seg_roi_gt_vs_pred.png"),
        (MANUSCRIPT / "fig2_segmentation_comparison.png", "seg_multicenter_comparison.png"),
        (MANUSCRIPT / "02_segmentation_nnunet" / "nnunet_main_comparison.png", "seg_nnunet_main.png"),
        (MANUSCRIPT / "02_segmentation_nnunet" / "summary_all_datasets.png", "seg_nnunet_summary.png"),
    ]
    for src, dest in seg_jobs:
        if not args.dry_run:
            copy_pair(src, dest, manifest)
        elif src.is_file():
            manifest.append({"file": dest, "source": str(src.relative_to(PROJECT_ROOT))})
    copy_dir_samples(
        MANUSCRIPT / "02_segmentation_nnunet",
        "seg_nnunet_compare",
        manifest,
        limit=6,
        pattern="compare_*.png",
        max_mb=MAX_FILE_MB,
    )
    copy_dir_samples(
        MANUSCRIPT / "03_segmentation_sam2",
        "seg_sam2_compare",
        manifest,
        limit=8,
        pattern="compare_*.png",
        max_mb=MAX_FILE_MB,
    )

    if SEG_REPORT.is_dir():
        for name in ("evaluation_summary.png", "training_curves.png"):
            copy_pair(SEG_REPORT / name, f"seg_dinov3_{name.replace('.png', '')}.png", manifest)

    sync_rf_panels(manifest)
    sync_report_panels(manifest)

    # --- dehua gradcam smoke overlays ---
    dehua = (
        PIPELINE_REPORTS
        / "zip_pipeline_review_gradcam_smoke_20260505"
        / "dehua_gradcam_smoke"
    )
    copy_pair(dehua / "summary_contact_sheet.png", "case_pipeline_dehua_contact_sheet.png", manifest)
    copy_dir_samples(dehua / "case_overlays", "case_pipeline_dehua_overlay", manifest, limit=8, max_mb=MAX_FILE_MB)
    copy_dir_samples(dehua / "gt_roi_crops", "case_pipeline_dehua_gt_roi", manifest, limit=4, max_mb=MAX_FILE_MB)

    sync_agent_cases(manifest, max_patients=6)

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
