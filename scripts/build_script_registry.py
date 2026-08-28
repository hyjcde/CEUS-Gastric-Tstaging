#!/usr/bin/env python3
"""Generate scripts/script_registry.csv for all scripts/*.py (and key shell)."""

from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
README = SCRIPTS_DIR / "README.md"
OUT = SCRIPTS_DIR / "script_registry.csv"

SECTION_MAP = {
    "1": "detection",
    "2": "segmentation",
    "3": "data_governance",
    "4": "analysis",
    "5": "analysis",
    "6": "utility",
    "7": "legacy",
}

# From README §1–6 explicit mentions + maintenance tooling
CURRENT_BY_NAME: dict[str, tuple[str, str]] = {
    "prepare_yolo_detection_dataset.py": ("current", "detection"),
    "freeze_detection_internal_holdout_split.py": ("current", "detection"),
    "build_yolo_detection_dataset.py": ("current", "detection"),
    "run_yolo_detection_train.py": ("current", "detection"),
    "run_yolo_detection_eval.py": ("current", "detection"),
    "generate_yolo_detection_report.py": ("current", "detection"),
    "generate_yolo_detection_qc_overlays.py": ("current", "detection"),
    "yolo_detection_runtime.py": ("runtime", "detection"),
    "freeze_sms_internal_holdout_split.py": ("current", "segmentation"),
    "prepare_sms_gastric_2d_dataset.py": ("current", "segmentation"),
    "build_sms_baseline_dataset.py": ("current", "segmentation"),
    "run_sms_train.py": ("current", "segmentation"),
    "run_sms_inference.py": ("current", "segmentation"),
    "run_unet2d_segmentation_baseline.py": ("current", "segmentation"),
    "score_binary_segmentation_folder.py": ("current", "segmentation"),
    "organize_dataset_clinical_tables.py": ("current", "data_governance"),
    "export_clinical_queue_json.py": ("current", "data_governance"),
    "reconcile_clinical_tables_20260813.py": ("current", "data_governance"),
    "check_clinical_tables_20260814.py": ("current", "data_governance"),
    "audit_clinical_table_media_20260814.py": ("current", "data_governance"),
    "inventory_tnm_nm_labels_20260814.py": ("current", "analysis"),
    "tnm_nm_label_map.py": ("current", "data_governance"),
    "build_tnm_nm_phase0_splits_20260814.py": ("current", "data_governance"),
    "eval_tnm_backend_heads_20260814.py": ("current", "analysis"),
    "probe_tnm_t_proxy_baseline_20260814.py": ("current", "analysis"),
    "run_tnm_frozen_n_probe_20260814.py": ("current", "analysis"),
    "stats_tnm_t_association_20260814.py": ("current", "analysis"),
    "predict_tnm_frozen_heads_20260814.py": ("current", "analysis"),
    "plot_tnm_extended_data_20260814.py": ("current", "visualization"),
    "fit_tnm_regularized_n_head_20260814.py": ("current", "analysis"),
    "viz_static_wall_dash_6cases_20260814.py": ("current", "visualization"),
    "gc_us_wall_dash.py": ("current", "visualization"),
    "preprocess_direct_surgery_datasets.py": ("current", "data_governance"),
    "patient_split.py": ("current", "data_governance"),
    "build_dataset_inventory.py": ("current", "data_governance"),
    "build_dataset_visual_overview.py": ("current", "data_governance"),
    "verify_repo_paths.py": ("maintenance", "governance"),
    "check_repo_root.py": ("maintenance", "governance"),
    "build_asset_manifest.py": ("maintenance", "governance"),
    "build_dataset_registry.py": ("maintenance", "governance"),
    "build_phase0_anatomic_region_splits.py": ("maintenance", "data_governance"),
    "build_script_registry.py": ("maintenance", "governance"),
    "build_experiments_registry.py": ("maintenance", "governance"),
    "repo_paths.py": ("runtime", "governance"),
    "migrate_root_assets.py": ("maintenance", "governance"),
    "migrate_legacy_raw_dirs.py": ("maintenance", "governance"),
    "migrate_data_zips.py": ("maintenance", "governance"),
    "consolidate_compat_links.py": ("maintenance", "governance"),
    "cleanup_migration_backups.py": ("maintenance", "governance"),
    "audit_current_dataset_assets.py": ("maintenance", "governance"),
    "build_workspace_inventory.py": ("maintenance", "governance"),
    "classify_git_status.py": ("maintenance", "governance"),
    "build_experiments_tree_index.py": ("maintenance", "governance"),
    "build_paper_ablation_matrix.py": ("maintenance", "governance"),
    "build_report_index.py": ("maintenance", "governance"),
    "audit_mainline_eval_chain.py": ("maintenance", "governance"),
    "audit_modeling_dataset_contracts.py": ("maintenance", "data_governance"),
    "build_patient_training_view.py": ("current", "data_governance"),
    "build_task_datasets.py": ("current", "data_governance"),
    "build_binary_multicenter_joint_unseen.py": ("current", "data_governance"),
    "run_binary_multicenter_joint_unseen_20260820.py": ("current", "analysis"),
    "score_binary_multicenter_unseen.py": ("current", "analysis"),
    "build_task_datasets_source_inventory.py": ("current", "data_governance"),
    "join_reader_v150_to_task_datasets.py": ("current", "data_governance"),
    "audit_task_datasets.py": ("maintenance", "data_governance"),
    "align_acc_boost2_to_official_freeze.py": ("maintenance", "data_governance"),
    "build_training_media_view.py": ("current", "data_governance"),
    "build_static_images_view.py": ("current", "data_governance"),
    "build_videos_view.py": ("current", "data_governance"),
    "build_real_cine_aligned_view.py": ("current", "data_governance"),
    "freeze_real_cine_training_package.py": ("current", "data_governance"),
    "quarantine_loop_still_videos.py": ("current", "data_governance"),
    "build_model_inventory.py": ("maintenance", "governance"),
    "build_log_index.py": ("maintenance", "governance"),
    "cache_dinov3_roi_green_scalars.py": ("current", "analysis"),
    "probe_dino_green_maps.py": ("current", "analysis"),
    "run_dinov3_framelevel_scalar_train_eval.py": ("current", "analysis"),
    "train_dinov3_anatomic_adapter.py": ("current", "analysis"),
    "freeze_clinical_sam2_loop_contract.py": ("current", "segmentation"),
    "build_clinical_loop_static_manifest.py": ("current", "segmentation"),
    "build_auto_discovery_seed_prompts.py": ("current", "segmentation"),
    "ingest_doctor_mask_corrections.py": ("current", "segmentation"),
    "rank_clinical_loop_review_queue.py": ("current", "segmentation"),
    "probe_medsam2_checkpoint_compat.py": ("current", "segmentation"),
    "run_clinical_loop_static_benchmark.py": ("current", "segmentation"),
    "run_clinical_loop_correction_finetune.py": ("current", "segmentation"),
    "run_clinical_loop_promotion_gate.py": ("current", "segmentation"),
    "collect_clinical_loop_workflow_metrics.py": ("current", "segmentation"),
    "assert_temporal_claims_deferred.py": ("current", "segmentation"),
    "run_medsiglip_gastricus.py": ("current", "analysis"),
    "build_tstaging_maincenter_retrospective.py": ("current", "data_governance"),
    "build_tstaging_threecenter_joint_unseen.py": ("current", "data_governance"),
    "train_t_stage.py": ("current", "analysis"),
    "eval_t_stage.py": ("current", "analysis"),
    "eval_tstage_tent_20260827.py": ("current", "analysis"),
    "freeze_zml_reader_v150_inputs_20260827.py": ("current", "data_governance"),
    "score_zml_reader_v150_frozen_20260827.py": ("current", "analysis"),
    "plot_zml_reader_v150_tent_20260827.py": ("current", "analysis"),
    "plot_zml_reader_v150_doctor_model_agreement_20260827.py": ("current", "analysis"),
    "plot_zml_reader_v150_doctor_model_zh_20260827.py": ("current", "analysis"),
    "tstaging_lab_prepare.py": ("current", "data_governance"),
    "tstaging_lab_verify.py": ("current", "data_governance"),
    "tstaging_lab_train.py": ("current", "analysis"),
    "tstaging_lab_evaluate.py": ("current", "analysis"),
    "tstaging_lab_new_experiment.py": ("current", "analysis"),
    "tstaging_lab_register.py": ("current", "analysis"),
    "tstaging_lab_plot.py": ("current", "analysis"),
    "tstaging_lab_monitor.py": ("current", "analysis"),
    "tstaging_lab_audit_clinical.py": ("current", "data_governance"),
    "tstaging_lab_train_maskroi_clinical.py": ("current", "analysis"),
    "tstaging_lab_evaluate_maskroi_clinical.py": ("current", "analysis"),
    "tstaging_lab_train_roi25.py": ("current", "analysis"),
    "tstaging_lab_evaluate_roi25.py": ("current", "analysis"),
    "tstaging_lab_train_roi50.py": ("current", "analysis"),
    "tstaging_lab_evaluate_roi50.py": ("current", "analysis"),
    "tstaging_lab_train_roi25_mask.py": ("current", "analysis"),
    "tstaging_lab_evaluate_roi25_mask.py": ("current", "analysis"),
    "tstaging_lab_train_deep_side.py": ("current", "analysis"),
    "tstaging_lab_evaluate_deep_side.py": ("current", "analysis"),
    "copy_tstaging_physical_train.py": ("current", "data_governance"),
    "build_tstaging_center_tables.py": ("current", "data_governance"),
    "compare_sam_dino_roi_panel_expand10.py": ("current", "segmentation"),
    "wall_lesion_aware_cluster.py": ("current", "analysis"),
    "pack_wall_layer_fixture_v1.py": ("current", "analysis"),
    "eval_lesion_aware_wall_cluster_v1.py": ("current", "analysis"),
    "render_lesion_aware_wall_cluster_panel.py": ("current", "analysis"),
    "test_wall_lesion_aware_cluster.py": ("current", "analysis"),
}

LEGACY_PATTERNS = (
    r"^process_",
    r"^prepare_student_dataset",
    r"^convert_data\.py$",
    r"^batch_convert",
    r"^batch_crop",
    r"^crop_year_dataset",
    r"^convert_videos",
)

HARDCODED_ROOT = re.compile(r"/data/research/gastric/GastricTstaging")


def parse_readme_sections() -> dict[str, str]:
    """Map script filename -> readme section number."""
    if not README.exists():
        return {}
    text = README.read_text(encoding="utf-8")
    section = ""
    mapping: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^##\s+(\d+)\.", line)
        if m:
            section = m.group(1)
            continue
        for name in re.findall(r"`([a-zA-Z0-9_]+\.py)`", line):
            if section:
                mapping[name] = section
    return mapping


def infer_status(name: str, path: Path, readme_sec: str) -> tuple[str, str, str]:
    if name in CURRENT_BY_NAME:
        st, task = CURRENT_BY_NAME[name]
        return st, task, readme_sec or ""

    if any(re.search(p, name) for p in LEGACY_PATTERNS):
        return "legacy", SECTION_MAP.get(readme_sec, "legacy"), readme_sec

    if readme_sec == "7":
        return "legacy", "legacy", readme_sec

    body = ""
    try:
        body = path.read_text(encoding="utf-8", errors="ignore")[:8000]
    except OSError:
        pass
    if "STATUS: legacy" in body or "# legacy" in body.lower():
        return "legacy", SECTION_MAP.get(readme_sec, "legacy"), readme_sec

    if name.startswith("build_") and "registry" in name:
        return "maintenance", "governance", readme_sec
    if name.startswith(("verify_", "check_", "migrate_", "consolidate_", "cleanup_", "audit_", "align_")):
        return "maintenance", "governance", readme_sec

    if HARDCODED_ROOT.search(body) and "repo_paths" not in body:
        return "legacy", SECTION_MAP.get(readme_sec, "unknown"), readme_sec

    if readme_sec in ("4", "5"):
        return "analysis", SECTION_MAP.get(readme_sec, "analysis"), readme_sec
    if readme_sec == "6":
        return "utility", "utility", readme_sec
    if readme_sec in ("1", "2", "3"):
        return "unknown", SECTION_MAP.get(readme_sec, "unknown"), readme_sec

    if "import" in body and 'if __name__ == "__main__"' not in body:
        return "runtime", "module", readme_sec

    return "unknown", "unknown", readme_sec


def move_candidate(status: str, task: str) -> str:
    if status == "current":
        return "scripts/current"
    if status == "maintenance":
        return "scripts/maintenance"
    if status in ("analysis", "utility"):
        return "scripts/analysis"
    if status == "legacy":
        return "scripts/legacy"
    if status == "runtime":
        return "scripts/runtime"
    return "needs_review"


def safe_to_run(status: str, uses_root: bool, name: str) -> str:
    if status == "legacy":
        return "no"
    if status == "unknown":
        return "review"
    if status == "current" and uses_root:
        return "yes"
    if status == "current" and not uses_root:
        return "review_paths"
    if status == "maintenance":
        return "yes"
    if status == "runtime":
        return "import_only"
    if status == "analysis":
        return "review_env"
    return "review"


def uses_project_root(path: Path) -> bool:
    try:
        body = path.read_text(encoding="utf-8", errors="ignore")[:12000]
    except OSError:
        return False
    if "repo_paths" in body and "PROJECT_ROOT" in body:
        return True
    if HARDCODED_ROOT.search(body):
        return False
    if "Path(__file__).resolve().parents[1]" in body:
        return True
    return False


def main() -> None:
    readme_map = parse_readme_sections()
    rows: list[dict[str, str]] = []

    py_files = sorted(SCRIPTS_DIR.glob("*.py"), key=lambda p: p.name)
    for path in py_files:
        name = path.name
        if name == "build_script_registry.py":
            continue  # avoid self-reference noise; still add below
        sec = readme_map.get(name, "")
        status, task, sec_out = infer_status(name, path, sec)
        notes = ""
        if status == "legacy":
            notes = "hardcoded paths or README §7"
        elif status == "unknown":
            notes = "needs manual review"
        upr = uses_project_root(path)
        rows.append(
            {
                "script": name,
                "status": status,
                "task": task,
                "readme_section": sec_out or sec,
                "owner_workspace": "scripts",
                "move_candidate": move_candidate(status, task),
                "safe_to_run": safe_to_run(status, upr, name),
                "uses_project_root": str(upr).lower(),
                "notes": notes,
            }
        )

    # include self
    rows.append(
        {
            "script": "build_script_registry.py",
            "status": "maintenance",
            "task": "governance",
            "readme_section": "",
            "owner_workspace": "scripts",
            "move_candidate": "scripts/maintenance",
            "safe_to_run": "yes",
            "uses_project_root": "true",
            "notes": "generates this file",
        }
    )

    for sh in sorted(SCRIPTS_DIR.glob("*.sh")):
        st = "legacy" if "convert_videos" in sh.name else "utility"
        rows.append(
            {
                "script": sh.name,
                "status": st,
                "task": "shell",
                "readme_section": readme_map.get(sh.name, "7"),
                "owner_workspace": "scripts",
                "move_candidate": move_candidate(st, "shell"),
                "safe_to_run": "no" if st == "legacy" else "review",
                "uses_project_root": "false",
                "notes": "",
            }
        )

    rows.sort(key=lambda r: r["script"])
    fieldnames = [
        "script",
        "status",
        "task",
        "readme_section",
        "owner_workspace",
        "move_candidate",
        "safe_to_run",
        "uses_project_root",
        "notes",
    ]
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {OUT} ({date.today().isoformat()})")


if __name__ == "__main__":
    main()
