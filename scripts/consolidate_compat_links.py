#!/usr/bin/env python3
"""Move root compatibility symlinks into _compat/ for a cleaner repo root."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPAT = PROJECT_ROOT / "_compat"
MIGRATION_LOG = PROJECT_ROOT / "data" / "metadata" / "path_migration_log.csv"

# name -> target relative to PROJECT_ROOT
LINKS: dict[str, str] = {
    "direction_annotation_batch.json": "data/annotation/batches/direction_annotation_batch.json",
    "direction_annotations": "data/annotation/outputs/direction_annotations",
    "gradcam_rejected (2).csv": "artifacts/reports/gradcam_rejected.csv",
    "yolo11n.pt": "artifacts/model_weights/yolo/yolo11n.pt",
    "yolo11s.pt": "artifacts/model_weights/yolo/yolo11s.pt",
    "yolo11m.pt": "artifacts/model_weights/yolo/yolo11m.pt",
    "yolo11l.pt": "artifacts/model_weights/yolo/yolo11l.pt",
    "docs copy": "archive/docs_legacy/docs_copy",
    "frames_1fps": "artifacts/video_frames/frames_1fps",
    "results": "artifacts/results",
    "output": "artifacts/output",
    "tmp": "artifacts/tmp",
    "paper": "docs/paper",
    "胃癌分期": "data/raw/legacy_gastric_staging",
    "胃癌直接手术外部测试集": "data/raw/legacy_external_direct_surgery",
    "胃腔": "data/raw/legacy_lumen",
    "胃壁区域可视化方向": "data/raw/legacy_wall_viz",
    "200.zip": "artifacts/raw_imports/incoming/200.zip",
    "2024_crop_ui_unlabeled_lumen_for_labelme(1).zip": "artifacts/raw_imports/incoming/2024_crop_ui_unlabeled_lumen_for_labelme(1).zip",
    "2024_crop_ui_unlabeled_lumen_for_labelme(2).zip": "artifacts/raw_imports/incoming/2024_crop_ui_unlabeled_lumen_for_labelme(2).zip",
    "外部测试集炎症视频.zip": "artifacts/raw_imports/incoming/外部测试集炎症视频.zip",
    "外部测试集胃癌视频.zip": "artifacts/raw_imports/incoming/外部测试集胃癌视频.zip",
    "胃癌直接手术外部测试集(1).zip": "artifacts/raw_imports/incoming/胃癌直接手术外部测试集(1).zip",
    "协和直接手术视频.zip": "artifacts/raw_imports/incoming/协和直接手术视频.zip",
    "合格视频.zip": "artifacts/raw_imports/incoming/合格视频.zip",
    "胃炎外部测试集.zip": "artifacts/raw_imports/incoming/胃炎外部测试集.zip",
    "2025_Patient_Videos": "data/raw/patient_videos_2025",
    "临床资料_前瞻外部分析_20260609": "data/staging_review/clinical_prospective_20260609",
    "人机对比结果": "docs/clinical_validation/human_ai_comparison",
}

KEEP_AT_ROOT = {
    "README.md",
    "START_HERE.md",
    "REPO_LAYOUT.md",
    "MAINTENANCE.md",
    ".env",
    ".env.example",
    ".gitignore",
    ".git",
    ".vscode",
    "apps",
    "archive",
    "artifacts",
    "configs",
    "data",
    "dataset",
    "docs",
    "experiments",
    "external",
    "models",
    "pipeline",
    "scripts",
    "_compat",
}


def append_log(old_path: str, new_path: str, action: str) -> None:
    with MIGRATION_LOG.open("a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([old_path, new_path, action, date.today().isoformat(), "yes", "consolidate_compat"])


def ensure_compat_link(name: str, target_rel: str) -> None:
    COMPAT.mkdir(exist_ok=True)
    target = (PROJECT_ROOT / target_rel).resolve()
    if not target.exists() and not target.is_symlink():
        print(f"warn: target missing for {name}: {target}")

    compat_link = COMPAT / name
    if compat_link.exists() or compat_link.is_symlink():
        if compat_link.is_symlink() and compat_link.resolve() == target:
            pass
        else:
            compat_link.unlink()
            compat_link.symlink_to(Path(target_rel))
    else:
        compat_link.symlink_to(Path(target_rel))

    root_link = PROJECT_ROOT / name
    if root_link.is_symlink() or (root_link.exists() and name not in KEEP_AT_ROOT):
        if root_link.is_symlink() or root_link.is_file():
            root_link.unlink()
        elif root_link.is_dir() and name not in LINKS:
            pass
        append_log(name, f"_compat/{name}", "mv_symlink_to_compat")


def main() -> None:
    for name, target_rel in sorted(LINKS.items()):
        ensure_compat_link(name, target_rel)
    print(f"Consolidated {len(LINKS)} links under {COMPAT}/")
    print("Root should now show only 12 workspace dirs + _compat + 4 entry markdown files.")


if __name__ == "__main__":
    main()
