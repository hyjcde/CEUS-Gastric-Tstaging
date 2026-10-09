#!/usr/bin/env python3
"""Build a patient-level binary split: multi-center joint train, unseen-center test.

Does not copy or move freeze / gastritis / inflammation images.

Seen centers (train/val, both labels where available):
  internal_xh, external_putian1, external_cnnc_504

Held out:
  test_prospective = 协和 2025 malignant + 协和 2025 benign (yan*) + 协和 2026 benign
                     + 莆田 inflammation 2025/2025_putian/2026_putian
  test_external    = centers never used in train/val

Revision 20261009 (contract binary_multicenter_joint_unseen_20261009):
  - yan* benign stills (raw id starts with "yan", source benign/inflammation/*) belong to 协和
    (confirmed by the user 2026-10-09; clinical data_source=inflammation, not inflammation_putian).
    ptyz* stills stay 莆田.
  - Adds 协和 2026 benign (dataset/inflammation/2026_xiehe, manifest review=0 and matched to clinical).
    2026 malignant (SSL cohort 胃癌-内部直接手术2026) is NOT added: no pT label in any table.
  - The 20260820 pack is kept unchanged for reproducing older training configs.

Rebuild:
  python3 scripts/build_binary_multicenter_joint_unseen.py
  python3 scripts/build_task_datasets.py
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LEGACY_SPLITS = ROOT / "dataset/task_datasets/binary_benign_malignant/splits_screened_20260531"
FALLBACK_SPLITS = ROOT / "dataset/task_datasets/binary_benign_malignant/splits"
BENIGN_REGISTRY = ROOT / "dataset/metadata/benign_master_registry.csv"
PACK = ROOT / "pipeline/data/binary_multicenter_joint_unseen_20261009"
XIEHE_2026_DIR = ROOT / "dataset/inflammation/2026_xiehe"
XIEHE_2026_SOURCE = "benign/inflammation/2026_xiehe"

CONTRACT = "binary_multicenter_joint_unseen_20261009"
SEED = 20260820
VAL_FRAC = 0.15

SEEN_CENTERS = ("internal_xh", "external_putian1", "external_cnnc_504")
# Dropped from every split. Images stay on disk under dataset/external/福建省立医院.
EXCLUDE_CENTERS = ("external_fujian_provincial",)

CENTER_NAMES = {
    "internal_xh": "福建医科大学附属协和医院",
    "external_putian1": "莆田学院附属医院",
    "external_putian2": "莆田市第一医院",
    "external_tumor": "福建省肿瘤医院",
    "external_sanming": "三明市第二医院",
    "external_dehua": "福建省德化县医院",
    "external_beijing_friendship": "北京友谊医院",
    "external_foshan_first": "佛山市第一人民医院",
    "external_cnnc_504": "中核五〇四医院",
    "external_fujian_provincial": "福建省立医院",
    "external_ningde": "宁德市医院",
}

SOURCE_TO_CENTER = {
    "malignant/int/2018": "internal_xh",
    "malignant/int/2019": "internal_xh",
    "malignant/int/2020_2023": "internal_xh",
    "malignant/int/2024": "internal_xh",
    "malignant/int/prospective": "internal_xh",
    "malignant/ext/putian": "external_putian1",
    "malignant/ext/putian_2024_new": "external_putian1",
    "malignant/ext/putian2": "external_putian2",
    "malignant/ext/multicenter": "external_tumor",
    "malignant/ext/zhongliu": "external_tumor",
    "malignant/ext/sanming": "external_sanming",
    "malignant/ext/中核五〇四医院": "external_cnnc_504",
    "malignant/ext/福建省立医院": "external_fujian_provincial",
    "malignant/ext/北京友谊医院": "external_beijing_friendship",
    "malignant/ext/福建省德化县医院": "external_dehua",
    "malignant/ext/佛山市第一人民医院": "external_foshan_first",
    "benign/inflammation/2018": "external_putian1",
    "benign/inflammation/2019": "external_putian1",
    "benign/inflammation/2020": "external_putian1",
    "benign/inflammation/2021": "external_putian1",
    "benign/inflammation/2022": "external_putian1",
    "benign/inflammation/2023": "external_putian1",
    "benign/inflammation/2024": "external_putian1",
    "benign/inflammation/2025": "external_putian1",
    "benign/inflammation/2025_putian": "external_putian1",
    "benign/inflammation/2026_putian": "external_putian1",
    XIEHE_2026_SOURCE: "internal_xh",
    "benign/inflammation/putian_2020": "external_putian1",
    "benign/gastritis_external/莆田学院附属医院": "external_putian1",
    "benign/gastritis_external/福建省肿瘤医院": "external_tumor",
    "benign/gastritis_external/三明市第二医院": "external_sanming",
    "benign/gastritis_external/中核五〇四医院": "external_cnnc_504",
    "benign/gastritis_external/福建省德化县医院": "external_dehua",
    "benign/gastritis_external/宁德市医院": "external_ningde",
}

TEMPORAL_SOURCES = {
    "malignant/int/prospective",
    "benign/inflammation/2025",
    "benign/inflammation/2025_putian",
    "benign/inflammation/2026_putian",
    XIEHE_2026_SOURCE,
}

OUT_COLS = [
    "image_path",
    "roi_path",
    "patient_id",
    "raw_patient_id",
    "legacy_patient_id",
    "label",
    "class_name",
    "source",
    "cohort",
    "T_stage",
    "center_id",
    "center_name",
    "split_role",
    "split",
    "task",
]


def relpath(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none"}:
        return ""
    prefix = str(ROOT) + "/"
    if text.startswith(prefix):
        text = text[len(prefix) :]
    return text


def abspath(value: object) -> str:
    text = relpath(value)
    if not text:
        return ""
    return str((ROOT / text).resolve())


def exists_rel(path: str) -> bool:
    if not path:
        return False
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / path
    return p.exists()


def normalize_raw_patient_id(raw: object) -> str:
    """Group multi-frame stills of one person.

    Fixes leaked extensions (ptyz340.jpg), trailing punctuation (1561-, 1560_,
    1509 -), and a single letter series suffix (ptyz429b -> ptyz429).
    """
    text = str(raw or "").strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return ""
    text = re.sub(r"\.(jpg|jpeg|png|bmp|nii(\.gz)?)$", "", text, flags=re.I)
    text = re.sub(r"\s+", "", text)
    text = text.strip("-_")
    if not text:
        return ""
    if re.fullmatch(r"\d+", text):
        return text.lstrip("0") or "0"
    match = re.fullmatch(r"([A-Za-z]+)(\d+)([A-Za-z]*)", text)
    if match:
        prefix, digits, extra = match.groups()
        digits = digits.lstrip("0") or "0"
        return f"{prefix.lower()}{digits}"
    return text.lower()


def remap_roi(image_path: str, roi_path: str) -> str:
    roi = relpath(roi_path)
    img = relpath(image_path)
    if exists_rel(roi):
        return roi
    if "/crop_ui/images/" in img:
        cand = img.replace("/crop_ui/images/", "/crop_roi/images/")
        if exists_rel(cand):
            return cand
    return roi


def annotate(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["source"] = out["source"].astype(str)
    unknown = sorted(set(out["source"]) - set(SOURCE_TO_CENTER))
    if unknown:
        raise SystemExit(f"Unmapped binary sources: {unknown}")
    out["center_id"] = out["source"].map(SOURCE_TO_CENTER)
    out["legacy_patient_id"] = out["patient_id"].astype(str)
    out["raw_patient_id"] = out["raw_patient_id"].map(normalize_raw_patient_id)
    empty = out["raw_patient_id"].eq("")
    if empty.any():
        raise SystemExit(f"Empty raw_patient_id after normalize: {int(empty.sum())}")
    # yan* benign stills are 协和 (user-confirmed 2026-10-09); ptyz* stay 莆田.
    is_yan = out["source"].str.startswith("benign/inflammation/") & out["raw_patient_id"].str.startswith("yan")
    out.loc[is_yan, "center_id"] = "internal_xh"
    out["center_name"] = out["center_id"].map(CENTER_NAMES)
    missing = out["center_name"].isna()
    if missing.any():
        raise SystemExit(f"Unmapped center_id: {sorted(out.loc[missing, 'center_id'].unique())}")
    out["patient_id"] = out["center_id"] + "::" + out["raw_patient_id"]
    return out


def dedupe_images(df: pd.DataFrame) -> pd.DataFrame:
    """One row per image_path. Prefer a real ROI, then a stable source name."""
    out = df.copy()
    out["_roi_ok"] = out["roi_path"].map(exists_rel).astype(int)
    out["_src_rank"] = out["source"].map(lambda s: 0 if "putian_2024_new" in s or s.endswith("/multicenter") else 1)
    out = out.sort_values(
        ["image_path", "_roi_ok", "_src_rank", "source"],
        ascending=[True, False, False, True],
    )
    out = out.drop_duplicates("image_path", keep="first")
    return out.drop(columns=["_roi_ok", "_src_rank"]).reset_index(drop=True)


def load_legacy_universe() -> pd.DataFrame:
    src = LEGACY_SPLITS if (LEGACY_SPLITS / "train.csv").exists() else FALLBACK_SPLITS
    frames = []
    for name in ("train", "val", "test_prospective", "test_external"):
        path = src / f"{name}.csv"
        df = pd.read_csv(path, dtype=str).fillna("")
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def unused_inflammation_rows(used_paths: set[str]) -> pd.DataFrame:
    reg = pd.read_csv(BENIGN_REGISTRY, dtype=str).fillna("")
    reg["image_path"] = reg["image_path"].map(relpath)
    extra = reg[~reg["image_path"].isin(used_paths)].copy()
    extra = extra[extra["image_path"].map(exists_rel)].copy()
    if extra.empty:
        return extra
    extra["roi_path"] = [
        remap_roi(img, roi) for img, roi in zip(extra["image_path"], extra["roi_path"])
    ]
    extra["raw_patient_id"] = extra["patient_id"].astype(str)
    extra["patient_id"] = extra.apply(
        lambda row: f"inflammation/{row['subset']}::{row['raw_patient_id']}",
        axis=1,
    )
    extra["label"] = "0"
    extra["class_name"] = "benign"
    extra["source"] = "benign/inflammation/" + extra["subset"].astype(str)
    extra["cohort"] = "inflammation/" + extra["subset"].astype(str)
    extra["T_stage"] = ""
    extra["split"] = ""
    extra["task"] = "binary_benign_malignant"
    return extra[
        [
            "image_path",
            "roi_path",
            "patient_id",
            "raw_patient_id",
            "label",
            "class_name",
            "source",
            "cohort",
            "T_stage",
            "split",
            "task",
        ]
    ]


def xiehe_2026_benign_rows() -> pd.DataFrame:
    """Clean 协和 2026 benign stills: manifest review=0, not unmatched, matched to a clinical exam.

    Patient key is 住院号; when 住院号 is blank the name is used. Flagged exams (review=1,
    e.g. 恶变/瘤变 impressions) are excluded from the clean benign set.
    """
    mf = pd.read_csv(XIEHE_2026_DIR / "manifest.csv", dtype=str, keep_default_na=False)
    cl = pd.read_csv(XIEHE_2026_DIR / "clinical.csv", dtype=str, keep_default_na=False)
    clean = mf[(mf["review"] == "0") & ~mf["exam"].str.startswith("unmatched")].copy()
    cl = cl[["检查号", "住院号", "姓名"]].drop_duplicates("检查号")
    clean = clean.merge(cl, left_on="exam", right_on="检查号", how="inner")
    if clean.empty:
        raise SystemExit("No clean 2026 协和 benign rows matched to clinical")
    hosp = clean["住院号"].str.strip()
    name = clean["姓名"].str.strip()
    clean["raw_patient_id"] = [
        f"xh2026_{h}" if h else f"xh2026_name_{n}" for h, n in zip(hosp, name)
    ]
    rows = pd.DataFrame(
        {
            "image_path": "dataset/inflammation/2026_xiehe/images/" + clean["image"],
            "roi_path": "dataset/inflammation/2026_xiehe/roi/" + clean["image"],
            "patient_id": clean["raw_patient_id"],
            "raw_patient_id": clean["raw_patient_id"],
            "label": "0",
            "class_name": "benign",
            "source": XIEHE_2026_SOURCE,
            "cohort": "inflammation/2026_xiehe",
            "T_stage": "",
            "split": "",
            "task": "binary_benign_malignant",
        }
    )
    rows["roi_path"] = [
        r if exists_rel(r) else "" for r in rows["roi_path"]
    ]
    return rows[rows["image_path"].map(exists_rel)].reset_index(drop=True)


def assign_seen_split(seen: pd.DataFrame, seed: int, val_frac: float) -> pd.Series:
    patients = (
        seen.groupby("patient_id", as_index=False)
        .agg(center_id=("center_id", "first"), label=("label", "first"))
    )
    rng = np.random.RandomState(seed)
    val_ids: set[str] = set()
    for _, grp in patients.groupby(["center_id", "label"], sort=True):
        ids = grp["patient_id"].tolist()
        rng.shuffle(ids)
        n = len(ids)
        if n >= 7:
            n_val = max(1, int(round(n * val_frac)))
        elif n >= 5:
            n_val = 1
        else:
            n_val = 0
        val_ids.update(ids[:n_val])
    return seen["patient_id"].map(lambda pid: "val" if pid in val_ids else "train")


def summarize(df: pd.DataFrame) -> dict:
    by_center: dict[str, dict] = {}
    for center, g in df.groupby("center_id"):
        by_center[str(center)] = {
            "center_name": str(g["center_name"].iloc[0]),
            "rows": int(len(g)),
            "patients": int(g["patient_id"].nunique()),
            "benign": int((g["label"] == "0").sum()),
            "malignant": int((g["label"] == "1").sum()),
        }
    return {
        "rows": int(len(df)),
        "patients": int(df["patient_id"].nunique()),
        "benign": int((df["label"] == "0").sum()),
        "malignant": int((df["label"] == "1").sum()),
        "centers": by_center,
        "sources": {str(k): int(v) for k, v in df["source"].value_counts().items()},
    }


def leak_counts(assigned: pd.DataFrame) -> dict[str, int]:
    patients = {
        split: set(assigned.loc[assigned["split"] == split, "patient_id"])
        for split in ("train", "val", "test_prospective", "test_external")
    }
    return {
        "train_val": len(patients["train"] & patients["val"]),
        "train_prospective": len(patients["train"] & patients["test_prospective"]),
        "train_external": len(patients["train"] & patients["test_external"]),
        "val_prospective": len(patients["val"] & patients["test_prospective"]),
        "val_external": len(patients["val"] & patients["test_external"]),
        "prospective_external": len(patients["test_prospective"] & patients["test_external"]),
    }


def write_split(df: pd.DataFrame, dest: Path, absolute: bool) -> None:
    out = df[OUT_COLS].copy()
    if absolute:
        out["image_path"] = out["image_path"].map(abspath)
        out["roi_path"] = out["roi_path"].map(abspath)
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(dest, index=False)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--val-frac", type=float, default=VAL_FRAC)
    p.add_argument(
        "--seen-centers",
        default=",".join(SEEN_CENTERS),
        help="Comma-separated center_id list for joint train/val",
    )
    p.add_argument("--skip-unused-inflammation", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    seen_centers = tuple(c.strip() for c in args.seen_centers.split(",") if c.strip())
    universe = load_legacy_universe()
    universe["image_path"] = universe["image_path"].map(relpath)
    universe["roi_path"] = [
        remap_roi(img, roi) for img, roi in zip(universe["image_path"], universe["roi_path"])
    ]
    added = 0
    if not args.skip_unused_inflammation:
        extra = unused_inflammation_rows(set(universe["image_path"]))
        added = len(extra)
        if added:
            universe = pd.concat([universe, extra], ignore_index=True)
    xh26 = xiehe_2026_benign_rows()
    xh26_added = len(xh26)
    universe = pd.concat([universe, xh26], ignore_index=True)

    universe = universe[universe["image_path"].map(exists_rel)].reset_index(drop=True)
    universe = annotate(universe)
    universe = universe[~universe["center_id"].isin(EXCLUDE_CENTERS)].reset_index(drop=True)
    universe = dedupe_images(universe)
    universe["task"] = "binary_benign_malignant"
    universe["class_name"] = universe["label"].map({"0": "benign", "1": "malignant"})
    mixed_label = universe.groupby("patient_id")["label"].nunique()
    if (mixed_label > 1).any():
        raise SystemExit(f"Patients with both labels: {int((mixed_label > 1).sum())}")

    temporal_patients = set(
        universe.loc[universe["source"].isin(TEMPORAL_SOURCES), "patient_id"]
    )
    temporal = universe["patient_id"].isin(temporal_patients)
    seen_mask = universe["center_id"].isin(seen_centers) & ~temporal
    unseen_mask = ~universe["center_id"].isin(seen_centers) & ~temporal

    leftover = ~(temporal | seen_mask | unseen_mask)
    if leftover.any():
        raise SystemExit(f"Unassigned rows: {int(leftover.sum())}")

    seen = universe.loc[seen_mask].copy()
    seen["split"] = assign_seen_split(seen, seed=args.seed, val_frac=args.val_frac)
    seen["split_role"] = "seen_joint"

    prosp = universe.loc[temporal].copy()
    prosp["split"] = "test_prospective"
    prosp["split_role"] = "temporal_holdout"

    unseen = universe.loc[unseen_mask].copy()
    unseen["split"] = "test_external"
    unseen["split_role"] = "unseen_center"

    assigned = pd.concat([seen, prosp, unseen], ignore_index=True)
    leaks = leak_counts(assigned)
    if any(leaks.values()):
        raise SystemExit(f"Patient leak after reassignment: {leaks}")
    path_dups = int(assigned["image_path"].duplicated().sum())
    if path_dups:
        raise SystemExit(f"Duplicate image_path rows remain: {path_dups}")

    train_centers = set(assigned.loc[assigned["split"].isin(["train", "val"]), "center_id"])
    unseen_centers = set(assigned.loc[assigned["split"] == "test_external", "center_id"])
    if train_centers & unseen_centers:
        raise SystemExit(f"Center leak train/val vs unseen: {train_centers & unseen_centers}")

    PACK.mkdir(parents=True, exist_ok=True)
    split_stats = {}
    for split in ("train", "val", "test_prospective", "test_external"):
        part = assigned.loc[assigned["split"] == split].copy()
        write_split(part, PACK / f"{split}.csv", absolute=True)
        split_stats[split] = summarize(part)

    summary = {
        "created": date.today().isoformat(),
        "contract": CONTRACT,
        "seed": args.seed,
        "val_frac": args.val_frac,
        "seen_centers": list(seen_centers),
        "excluded_centers": list(EXCLUDE_CENTERS),
        "unseen_centers": sorted(unseen_centers),
        "temporal_sources": sorted(TEMPORAL_SOURCES),
        "unused_inflammation_added": added,
        "xiehe_2026_benign_added": xh26_added,
        "unique_image_paths": int(assigned["image_path"].nunique()),
        "patients": int(assigned["patient_id"].nunique()),
        "frames_per_patient": {
            "mean": float(assigned.groupby("patient_id").size().mean()),
            "median": float(assigned.groupby("patient_id").size().median()),
            "max": int(assigned.groupby("patient_id").size().max()),
            "singletons": int((assigned.groupby("patient_id").size() == 1).sum()),
        },
        "patient_leak": leaks,
        "splits": split_stats,
        "notes": [
            "ptyz* inflammation stills are Putian (registry hospital=putian). yan* inflammation stills are 协和 (user-confirmed 2026-10-09).",
            "Xiehe 2026 benign (dataset/inflammation/2026_xiehe, clean manifest rows) is temporal holdout with test_prospective.",
            "Xiehe 2026 malignant (SSL cohort 胃癌-内部直接手术2026) is not added: no pT label available.",
            "Putian gastritis_external rows enter train/val so seen-center benign is not inflammation-only.",
            "CNNC 504 is the third seen center so train benign is not Putian-only.",
            "test_external is unseen-center only. Do not treat test_prospective as unseen-center.",
            "Fujian Provincial Hospital is excluded from this contract. Disk folder is unchanged.",
        ],
        "out_dir": str(PACK.relative_to(ROOT)),
    }
    (PACK / "dataset_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
