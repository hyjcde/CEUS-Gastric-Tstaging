"""Build the main-center retrospective T-staging modeling tables.

Train and val are Xiehe 2018-2024 only. Prospective and external stay held-out.
Does not copy images. Does not reuse the leaked 20260531 task_datasets/t_staging/splits.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from .constants import (
    CATEGORICAL_ALLOWED,
    CLINICAL_FIELDS,
    CONTINUOUS_FIELDS,
    DATASET_DIR,
    MAX_CODE,
    PHASE0_DIR,
    RETROSPECTIVE_SOURCES,
    ROLE_BY_SPLIT,
    ROOT,
    SPLIT_FILES,
    T_STAGE_TO_LABEL,
)
from .resolve_frames import INTERNAL_CROP_UI, _index_crop_ui, resolve_row


def _repo_rel(path: str) -> str:
    if not path:
        return ""
    raw = Path(path)
    try:
        return raw.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return raw.as_posix()


def _sanitize_value(field: str, raw: object, missing_flag: object) -> tuple[float | int, int]:
    value = pd.to_numeric(raw, errors="coerce")
    flagged_present = int(missing_flag) == 0
    if not flagged_present or pd.isna(value):
        return (-1.0 if field in CONTINUOUS_FIELDS else -1), 1
    if field in CATEGORICAL_ALLOWED:
        code = int(value)
        if code in CATEGORICAL_ALLOWED[field]:
            return code, 0
        return -1, 1
    number = float(value)
    if not np.isfinite(number) or number == -1:
        return -1.0, 1
    if field in {"age", "tumor_length_cm", "tumor_thickness_cm"} and number <= 0:
        return -1.0, 1
    return number, 0


def _majority_t_stage(values: pd.Series) -> str:
    counts = Counter(str(item) for item in values.tolist())
    top = max(counts.values())
    tied = [name for name, count in counts.items() if count == top]
    if len(tied) == 1:
        return tied[0]
    return max(tied, key=lambda name: T_STAGE_TO_LABEL.get(name, -1))


def _apply_majority_t(table: pd.DataFrame) -> pd.DataFrame:
    out = table.copy()
    out["label_raw"] = out["label"].astype(int)
    out["T_stage_raw"] = out["T_stage"].astype(str)
    out["t_label_conflict"] = 0
    rewritten = []
    for _, group in out.groupby("patient_id", sort=False):
        majority = _majority_t_stage(group["T_stage_raw"])
        label = T_STAGE_TO_LABEL[majority]
        part = group.copy()
        conflict = int((part["T_stage_raw"] != majority).any())
        part["T_stage"] = majority
        part["label"] = label
        part["class_label"] = label
        part["t_label_conflict"] = conflict
        rewritten.append(part)
    return pd.concat(rewritten, ignore_index=True)


def _compute_norm_stats(train: pd.DataFrame) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for field in CONTINUOUS_FIELDS:
        present = train[train[f"{field}_missing"] == 0][field]
        values = pd.to_numeric(present, errors="coerce").dropna()
        mean = float(values.mean()) if len(values) else 0.0
        std = float(values.std()) if len(values) else 1.0
        stats[field] = {"mean": mean, "std": std if std > 0 else 1.0}
    for field, max_code in MAX_CODE.items():
        stats[field] = {"max_code": float(max_code)}
    return stats


def _apply_norms(table: pd.DataFrame, stats: dict[str, dict[str, float]]) -> pd.DataFrame:
    out = table.copy()
    packed: list[list[float]] = []
    for row in out.to_dict("records"):
        vector: list[float] = []
        for field in CLINICAL_FIELDS:
            missing = int(row[f"{field}_missing"])
            if missing:
                vector.extend([0.0, 1.0])
                continue
            raw = float(row[field])
            if field in CONTINUOUS_FIELDS:
                norm = (raw - stats[field]["mean"]) / stats[field]["std"]
            else:
                norm = raw / max(stats[field]["max_code"], 1.0)
            vector.extend([float(norm), 0.0])
        packed.append(vector)
    norms = np.asarray(packed, dtype=np.float64)
    for i, field in enumerate(CLINICAL_FIELDS):
        out[f"{field}_norm"] = norms[:, 2 * i]
    out["clinical_22"] = [json.dumps([float(x) for x in row]) for row in packed]
    return out


def _load_phase0_resolved(split: str, indexes: dict[str, dict[str, Path]]) -> pd.DataFrame:
    source_name = {
        "train": "train_clinical.csv",
        "val": "val_clinical.csv",
        "test_prospective": "test_prospective_clinical.csv",
        "test_external": "test_external_clinical.csv",
    }[split]
    raw = pd.read_csv(PHASE0_DIR / source_name, low_memory=False)
    records = []
    for row in raw.to_dict("records"):
        series = pd.Series(row)
        resolved = resolve_row(series, indexes)
        keep = {
            "source": resolved["source"],
            "patient_id": str(resolved["patient_id"]),
            "label": int(resolved["label"]),
            "T_stage": str(resolved["T_stage"]),
            "legacy_image_path": resolved["legacy_image_path"],
            "crop_ui_path": resolved["crop_ui_path"],
            "mask_path": resolved["mask_path"],
            "resolve_status": resolved["resolve_status"],
            "clinical_match_status": row.get("clinical_match_status", ""),
        }
        for field in CLINICAL_FIELDS:
            keep[field] = row.get(field)
            keep[f"{field}_missing"] = row.get(f"{field}_missing", 1)
        records.append(keep)
    return pd.DataFrame(records)


def _clean_split(table: pd.DataFrame, split: str) -> pd.DataFrame:
    usable = table[(table["crop_ui_path"] != "") & (table["mask_path"] != "")].copy()
    if split in {"train", "val"}:
        usable = usable[usable["source"].astype(str).isin(RETROSPECTIVE_SOURCES)].copy()
    usable["crop_ui_path"] = usable["crop_ui_path"].map(_repo_rel)
    usable["mask_path"] = usable["mask_path"].map(_repo_rel)
    usable = usable.drop_duplicates(subset=["crop_ui_path"], keep="first").reset_index(drop=True)
    usable = _apply_majority_t(usable)
    for field in CLINICAL_FIELDS:
        cleaned = usable.apply(lambda row, name=field: _sanitize_value(name, row[name], row[f"{name}_missing"]), axis=1)
        usable[field] = [item[0] for item in cleaned]
        usable[f"{field}_missing"] = [item[1] for item in cleaned]
    usable["split"] = split
    usable["role"] = ROLE_BY_SPLIT[split]
    usable["task"] = "t_staging"
    usable["image_path"] = usable["crop_ui_path"]
    return usable


def _assert_clean(tables: dict[str, pd.DataFrame]) -> dict[str, object]:
    train_ids = set(tables["train"]["patient_id"].astype(str))
    val_ids = set(tables["val"]["patient_id"].astype(str))
    prosp_ids = set(tables["test_prospective"]["patient_id"].astype(str))
    ext_ids = set(tables["test_external"]["patient_id"].astype(str))
    train_val_sources = sorted(set(tables["train"]["source"]).union(tables["val"]["source"]))
    checks = {
        "train_val_sources": train_val_sources,
        "train_val_has_prospective_source": any(src == "int/prospective" for src in train_val_sources),
        "train_val_has_external_source": any(str(src).startswith("ext/") for src in train_val_sources),
        "train_val_patient_overlap": len(train_ids & val_ids),
        "train_prospective_patient_overlap": len(train_ids & prosp_ids),
        "val_prospective_patient_overlap": len(val_ids & prosp_ids),
        "train_external_patient_overlap": len(train_ids & ext_ids),
        "val_external_patient_overlap": len(val_ids & ext_ids),
        "prospective_external_patient_overlap": len(prosp_ids & ext_ids),
    }
    failures = []
    if checks["train_val_has_prospective_source"] or checks["train_val_has_external_source"]:
        failures.append("train/val still contain prospective or external sources")
    for key in (
        "train_val_patient_overlap",
        "train_prospective_patient_overlap",
        "val_prospective_patient_overlap",
        "train_external_patient_overlap",
        "val_external_patient_overlap",
        "prospective_external_patient_overlap",
    ):
        if checks[key]:
            failures.append(f"{key}={checks[key]}")
    if set(train_val_sources) - set(RETROSPECTIVE_SOURCES):
        failures.append(f"unexpected sources {set(train_val_sources) - set(RETROSPECTIVE_SOURCES)}")
    if failures:
        raise RuntimeError("clean dataset contract failed: " + "; ".join(failures))
    return checks


def _split_inventory(table: pd.DataFrame) -> dict[str, object]:
    labels = table["label"].value_counts().sort_index().to_dict()
    return {
        "role": table["role"].iloc[0] if len(table) else "",
        "rows": int(len(table)),
        "patients": int(table["patient_id"].nunique()),
        "sources": table["source"].value_counts().to_dict(),
        "labels": {str(k): int(v) for k, v in labels.items()},
        "t_conflict_patients": int(table.groupby("patient_id")["t_label_conflict"].max().sum()),
        "image_exists": int(sum((ROOT / path).is_file() for path in table["image_path"])),
        "mask_exists": int(sum((ROOT / path).is_file() for path in table["mask_path"])),
    }


def build_tables() -> tuple[dict[str, pd.DataFrame], dict[str, dict[str, float]]]:
    indexes = {src: _index_crop_ui(path) for src, path in INTERNAL_CROP_UI.items()}
    cleaned: dict[str, pd.DataFrame] = {}
    for split in SPLIT_FILES:
        cleaned[split] = _clean_split(_load_phase0_resolved(split, indexes), split)
    stats = _compute_norm_stats(cleaned["train"])
    for split, table in cleaned.items():
        cleaned[split] = _apply_norms(table, stats)
    _assert_clean(cleaned)
    return cleaned, stats


def write_dataset(out_dir: Path = DATASET_DIR) -> dict[str, object]:
    tables, stats = build_tables()
    split_dir = out_dir / "splits"
    split_dir.mkdir(parents=True, exist_ok=True)
    inventory_splits = {}
    for split, table in tables.items():
        table.to_csv(out_dir / SPLIT_FILES[split], index=False)
        inventory_splits[split] = _split_inventory(table)
    (out_dir / "clinical_norm_stats.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "roles.json").write_text(
        json.dumps(ROLE_BY_SPLIT, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    checks = _assert_clean(tables)
    inventory = {
        "label": "T1 / T2 / T3 / T4+",
        "contract": "maincenter_retrospective_v20260821",
        "train_val": "Xiehe retrospective 2018-2024 only",
        "held_out": "prospective 2025 and external multicenter",
        "source_pack": str(PHASE0_DIR.relative_to(ROOT)),
        "roles": ROLE_BY_SPLIT,
        "leak_checks": checks,
        "splits": inventory_splits,
    }
    (out_dir / "inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return inventory
