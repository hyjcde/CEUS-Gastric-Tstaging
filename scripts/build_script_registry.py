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
    "preprocess_direct_surgery_datasets.py": ("current", "data_governance"),
    "patient_split.py": ("current", "data_governance"),
    "build_dataset_inventory.py": ("current", "data_governance"),
    "verify_repo_paths.py": ("maintenance", "governance"),
    "check_repo_root.py": ("maintenance", "governance"),
    "build_asset_manifest.py": ("maintenance", "governance"),
    "build_dataset_registry.py": ("maintenance", "governance"),
    "build_script_registry.py": ("maintenance", "governance"),
    "build_experiments_registry.py": ("maintenance", "governance"),
    "repo_paths.py": ("runtime", "governance"),
    "migrate_root_assets.py": ("maintenance", "governance"),
    "migrate_legacy_raw_dirs.py": ("maintenance", "governance"),
    "migrate_data_zips.py": ("maintenance", "governance"),
    "consolidate_compat_links.py": ("maintenance", "governance"),
    "cleanup_migration_backups.py": ("maintenance", "governance"),
    "audit_current_dataset_assets.py": ("maintenance", "governance"),
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
    if name.startswith(("verify_", "check_", "migrate_", "consolidate_", "cleanup_", "audit_")):
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
        rows.append(
            {
                "script": name,
                "status": status,
                "task": task,
                "readme_section": sec_out or sec,
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
            "notes": "generates this file",
        }
    )

    for sh in sorted(SCRIPTS_DIR.glob("*.sh")):
        rows.append(
            {
                "script": sh.name,
                "status": "legacy" if "convert_videos" in sh.name else "utility",
                "task": "shell",
                "readme_section": readme_map.get(sh.name, "7"),
                "notes": "",
            }
        )

    rows.sort(key=lambda r: r["script"])
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["script", "status", "task", "readme_section", "notes"])
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {OUT} ({date.today().isoformat()})")


if __name__ == "__main__":
    main()
