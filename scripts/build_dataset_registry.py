#!/usr/bin/env python3
"""Build read-only data/registry/*.csv from manifests and clinical tables."""

from __future__ import annotations

import csv
import sys
from collections import Counter

csv.field_size_limit(min(sys.maxsize, 10_000_000))
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_DIR = PROJECT_ROOT / "data/registry"
CLINICAL = PROJECT_ROOT / "dataset/tables/clinical_table_registry.csv"
CENTER = PROJECT_ROOT / "dataset/tables/center_name_registry.csv"
INTERNAL_MANIFEST = PROJECT_ROOT / "dataset/internal/manifest.csv"
EXTERNAL_MANIFEST = PROJECT_ROOT / "dataset/external/manifest.csv"

SPLIT_FILES = {
    "train": "pipeline/data/tstaging_4class_region_contrastive_full/regions/train_clinical.csv",
    "val": "pipeline/data/tstaging_4class_region_contrastive_full/regions/val_clinical.csv",
    "test_external": "pipeline/data/tstaging_4class_region_contrastive_full/regions/test_external_clinical.csv",
    "test_external_newzip": "pipeline/data/tstaging_4class_region_contrastive_full/regions/test_external_newzip_clinical.csv",
    "test_prospective": "pipeline/data/tstaging_4class_region_contrastive_full/regions/test_prospective_clinical.csv",
}


def count_csv_rows(path: Path) -> int:
    if not path.exists():
        return -1
    with path.open(encoding="utf-8-sig") as f:
        return sum(1 for _ in csv.DictReader(f)) - 0


def build_dataset_registry() -> None:
    rows: list[dict[str, str]] = []
    today = date.today().isoformat()

    rows.append(
        {
            "dataset_id": "tstage_4class_mainline",
            "version": "2026-05",
            "role": "current_training",
            "physical_root": "dataset/internal,dataset/external",
            "modeling_splits_root": "pipeline/data/tstaging_4class_region_contrastive_full/regions/",
            "manifest_paths": "dataset/internal/manifest.csv;dataset/external/manifest.csv",
            "clinical_registry": "dataset/tables/clinical_table_registry.csv",
            "status": "current",
            "notes": "Formal T-stage 4-class; see dataset/DATASET_GUIDE.md",
            "updated_at": today,
        }
    )

    for split, rel in SPLIT_FILES.items():
        p = PROJECT_ROOT / rel
        rows.append(
            {
                "dataset_id": f"tstage_split_{split}",
                "version": "2026-05",
                "role": "modeling_split",
                "physical_root": rel,
                "modeling_splits_root": rel,
                "manifest_paths": "",
                "clinical_registry": "",
                "status": "current" if p.exists() else "missing",
                "notes": f"row_count={count_csv_rows(p)}",
                "updated_at": today,
            }
        )

    if CENTER.exists():
        with CENTER.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                rows.append(
                    {
                        "dataset_id": f"center_{row.get('folder_name', '')}",
                        "version": "2026-05",
                        "role": "center_mapping",
                        "physical_root": f"dataset/external/{row.get('folder_name', '')}",
                        "modeling_splits_root": row.get("modeling_split", ""),
                        "manifest_paths": row.get("manifest_included", ""),
                        "clinical_registry": "dataset/tables/center_name_registry.csv",
                        "status": "current",
                        "notes": row.get("standard_hospital_name", ""),
                        "updated_at": today,
                    }
                )

    out = REGISTRY_DIR / "dataset_registry.csv"
    fieldnames = [
        "dataset_id",
        "version",
        "role",
        "physical_root",
        "modeling_splits_root",
        "manifest_paths",
        "clinical_registry",
        "status",
        "notes",
        "updated_at",
    ]
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {out}")


def build_patient_registry_sample() -> None:
    """Summarize patient_id counts per split from modeling CSVs."""
    out = REGISTRY_DIR / "patient_registry.csv"
    rows: list[dict[str, str]] = []
    for split, rel in SPLIT_FILES.items():
        p = PROJECT_ROOT / rel
        if not p.exists():
            continue
        patients: set[str] = set()
        with p.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                pid = (row.get("patient_id") or row.get("PatientID") or "").strip()
                if pid:
                    patients.add(pid)
        rows.append(
            {
                "split": split,
                "patient_count": str(len(patients)),
                "csv_path": rel,
                "updated_at": date.today().isoformat(),
            }
        )
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["split", "patient_count", "csv_path", "updated_at"])
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {out}")


def build_data_sources_inventory() -> None:
    out = PROJECT_ROOT / "data/metadata/data_sources_inventory.csv"
    rows: list[dict[str, str]] = []
    today = date.today().isoformat()

    zip_candidates = list((PROJECT_ROOT / "data").glob("*.zip")) + list(
        (PROJECT_ROOT / "artifacts/raw_imports").rglob("*.zip")
    )
    seen: set[str] = set()
    for zp in sorted(zip_candidates, key=lambda p: str(p)):
        key = str(zp.relative_to(PROJECT_ROOT))
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "source_id": zp.stem,
                "path": key,
                "kind": "zip_import",
                "size_mb": f"{zp.stat().st_size / (1024 * 1024):.1f}",
                "status": "registered",
                "notes": "raw import; not training manifest",
                "updated_at": today,
            }
        )

    if CLINICAL.exists():
        cohorts: Counter[str] = Counter()
        with CLINICAL.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                cohorts[row.get("cohort", "unknown")] += 1
        for cohort, n in sorted(cohorts.items()):
            rows.append(
                {
                    "source_id": f"clinical_{cohort}",
                    "path": "dataset/tables/clinical_table_registry.csv",
                    "kind": "clinical_table",
                    "size_mb": "",
                    "status": "current",
                    "notes": f"rows={n}",
                    "updated_at": today,
                }
            )

    fieldnames = ["source_id", "path", "kind", "size_mb", "status", "notes", "updated_at"]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {out}")


def main() -> None:
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    build_dataset_registry()
    build_patient_registry_sample()
    build_data_sources_inventory()


if __name__ == "__main__":
    main()
