#!/usr/bin/env python3
"""Build a clean two-task catalog under dataset/task_datasets/.

Copies modeling CSVs only. Does not move freeze images or rename hospital folders.
"""
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dataset" / "task_datasets"
T_READY = ROOT / "pipeline/data/tstaging_4class_screened_eval_20260531/alignment_official_20260819"
BINARY = ROOT / "pipeline/data/binary_multicenter_joint_unseen_20261009"
BINARY_LEGACY_SPLITS = OUT / "binary_benign_malignant" / "splits_screened_20260531"

T_SPLITS = [
    ("train", "train_ready.csv", "train"),
    ("val", "val_ready.csv", "val"),
    ("test_prospective", "test_prospective_ready.csv", "test_prospective"),
    ("test_external", "test_external_ready.csv", "test_external"),
]
BIN_SPLITS = [
    ("train", "train.csv", "train"),
    ("val", "val.csv", "val"),
    ("test_prospective", "test_prospective.csv", "test_prospective"),
    ("test_external", "test_external.csv", "test_external"),
]
T_EXCLUDE_SOURCES = ("ext/福建省立医院",)
T_KEEP = [
    "image_path",
    "roi_path",
    "patient_id",
    "label",
    "T_stage",
    "class_label",
    "source",
    "split",
    "alignment_status",
    "recommended_T_stage",
    "table_T",
    "media_sample_id",
]


def relpath(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none"}:
        return ""
    prefix = str(ROOT) + "/"
    if text.startswith(prefix):
        text = text[len(prefix) :]
    return text


def exists_rel(path: str) -> bool:
    if not path:
        return False
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / path
    return p.exists()


def remap_binary_roi(image_path: str, roi_path: str) -> str:
    roi = relpath(roi_path)
    img = relpath(image_path)
    if exists_rel(roi):
        return roi
    if "/crop_ui/images/" in img:
        cand = img.replace("/crop_ui/images/", "/crop_roi/images/")
        if exists_rel(cand):
            return cand
    return roi


def write_t_staging() -> dict:
    dest = OUT / "t_staging" / "splits"
    dest.mkdir(parents=True, exist_ok=True)
    stats = {}
    for split, src_name, split_token in T_SPLITS:
        src = T_READY / src_name
        df = pd.read_csv(src, dtype=str).fillna("")
        keep = [c for c in T_KEEP if c in df.columns]
        out = df[keep].copy()
        out["image_path"] = out["image_path"].map(relpath)
        out["roi_path"] = out["roi_path"].map(relpath)
        out = out[~out["source"].isin(T_EXCLUDE_SOURCES)].reset_index(drop=True)
        out["split"] = split_token
        out["task"] = "t_staging"
        out.to_csv(dest / f"{split}.csv", index=False)
        stats[split] = {
            "rows": int(len(out)),
            "patients": int(out["patient_id"].nunique()),
            "image_exists": int(out["image_path"].map(exists_rel).sum()),
            "roi_exists": int(out["roi_path"].map(exists_rel).sum()),
            "labels": out["label"].value_counts().to_dict() if "label" in out else {},
        }
    return stats


def archive_legacy_binary_splits() -> None:
    current = OUT / "binary_benign_malignant" / "splits" / "train.csv"
    archived = BINARY_LEGACY_SPLITS / "train.csv"
    if archived.exists() or not current.exists():
        return
    BINARY_LEGACY_SPLITS.mkdir(parents=True, exist_ok=True)
    for name in ("train.csv", "val.csv", "test_prospective.csv", "test_external.csv"):
        src = current.parent / name
        if src.exists():
            shutil.copy2(src, BINARY_LEGACY_SPLITS / name)


def write_binary() -> dict:
    archive_legacy_binary_splits()
    dest = OUT / "binary_benign_malignant" / "splits"
    dest.mkdir(parents=True, exist_ok=True)
    stats = {}
    for split, src_name, split_token in BIN_SPLITS:
        src = BINARY / src_name
        df = pd.read_csv(src, dtype=str).fillna("")
        out = pd.DataFrame(
            {
                "image_path": df["image_path"].map(relpath),
                "roi_path": [
                    remap_binary_roi(img, roi)
                    for img, roi in zip(df["image_path"], df["roi_path"])
                ],
                "patient_id": df["patient_id"],
                "raw_patient_id": df.get("raw_patient_id", df["patient_id"]),
                "legacy_patient_id": df.get("legacy_patient_id", ""),
                "label": df["label"],
                "class_name": df["label"].map({"0": "benign", "1": "malignant"}),
                "source": df["source"],
                "cohort": df.get("cohort", ""),
                "T_stage": df.get("T_stage", ""),
                "center_id": df.get("center_id", ""),
                "center_name": df.get("center_name", ""),
                "split_role": df.get("split_role", ""),
                "split": split_token,
                "task": "binary_benign_malignant",
            }
        )
        out.to_csv(dest / f"{split}.csv", index=False)
        stats[split] = {
            "rows": int(len(out)),
            "patients": int(out["patient_id"].nunique()),
            "image_exists": int(out["image_path"].map(exists_rel).sum()),
            "roi_exists": int(out["roi_path"].map(exists_rel).sum()),
            "benign": int((out["label"] == "0").sum()),
            "malignant": int((out["label"] == "1").sum()),
        }
    return stats


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    t_stats = write_t_staging()
    b_stats = write_binary()
    manifest = {
        "created": date.today().isoformat(),
        "root": "dataset/task_datasets",
        "note": "CSV catalog only. Images stay in dataset/internal|external|gastritis_external|inflammation.",
        "tasks": {
            "t_staging": {
                "label": "T1 / T2 / T3 / T4+",
                "contract": "acc_boost2 screened 20260531, paths remapped 20260819; drop Fujian Provincial",
                "splits": t_stats,
                "source_pack": str(T_READY.relative_to(ROOT)),
            },
            "binary_benign_malignant": {
                "label": "0=benign, 1=malignant",
                "contract": "binary_multicenter_joint_unseen_20261009",
                "splits": b_stats,
                "source_pack": str(BINARY.relative_to(ROOT)),
                "legacy_splits": str(BINARY_LEGACY_SPLITS.relative_to(ROOT)),
            },
        },
        "do_not": [
            "Mix benign rows into T1-T4+ training",
            "Move or rename dataset/external hospital folders",
            "Treat this folder as a pixel copy of freeze images",
        ],
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "t_staging" / "inventory.json").write_text(
        json.dumps(manifest["tasks"]["t_staging"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUT / "binary_benign_malignant" / "inventory.json").write_text(
        json.dumps(manifest["tasks"]["binary_benign_malignant"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
