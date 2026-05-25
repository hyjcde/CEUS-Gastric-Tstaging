#!/usr/bin/env python3
"""Pick one T2/T3 (or best-available) case per data source for PPT Grad-CAM grid."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from run_4class_gradcam import resolve_crop_ui_path  # noqa: E402

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PIPELINE_ROOT.parent
EXP = (
    PROJECT_ROOT
    / "pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch"
    / "tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301"
)

EXTERNAL_HOSPITAL_ALIASES = {
    "putian": "莆田学院附属医院",
    "putian_2024": "莆田学院附属医院",
    "putian_2024_new": "莆田学院附属医院",
    "putian_2025_07_09": "莆田学院附属医院",
    "zhongliu": "福建省肿瘤医院",
    "multicenter": "福建省肿瘤医院",
}

SOURCE_SPECS: list[tuple[str, str, str, str]] = [
    ("ext/putian", "putian", "Putian (legacy)", "test_external"),
    ("ext/putian_2024", "putian_2024", "Putian 2024", "test_external"),
    ("ext/putian_2024_new", "putian_2024_new", "Putian 2024 new", "test_external"),
    ("ext/putian_2025_07_09", "putian_2025", "Putian 2025", "test_external"),
    ("ext/zhongliu", "fujian_tumor", "Fujian tumor center", "test_external"),
    ("ext/multicenter", "multicenter", "Multicenter ext (T4+ only)", "test_external"),
    ("int/2018", "internal_val", "Internal validation (2018)", "val"),
    ("int/prospective", "prospective", "Prospective 2025", "prospective"),
]


def _score_boundary(row: pd.Series) -> float:
    """Higher = more interesting T2/T3 boundary case."""
    label = int(row["label"])
    pred_raw = row.get("pred", label)
    pred = int(pred_raw) if pd.notna(pred_raw) else label
    p2 = float(row.get("prob_c1", row.get("prob_T2", 0.0)))
    p3 = float(row.get("prob_c2", row.get("prob_T3", 0.0)))
    err = 1.0 if label != pred else 0.0
    close = 1.0 - abs(p2 - p3)
    t23 = 1.0 if label in (1, 2) else 0.0
    return err * 2.0 + close * t23 + t23


def load_pool(split_name: str) -> pd.DataFrame:
    if split_name == "test_external":
        return pd.read_csv(EXP / "eval/test_external/test_predictions.csv", low_memory=False)
    if split_name == "prospective":
        return pd.read_csv(EXP / "eval/test_prospective/test_predictions.csv", low_memory=False)
    if split_name == "val":
        val_path = PIPELINE_ROOT / "data/tstaging_4class/val.csv"
        df = pd.read_csv(val_path, low_memory=False)
        if "pred" not in df.columns:
            ext = pd.read_csv(EXP / "eval/test_external/test_predictions.csv", low_memory=False)
            key = ["image_path", "patient_id"]
            pred_cols = [c for c in ext.columns if c.startswith("prob_") or c in ("pred", "pred_class")]
            merge_cols = key + [c for c in pred_cols if c in ext.columns]
            df = df.merge(ext[merge_cols].drop_duplicates(subset=key), on=key, how="left")
            if "pred_class" in df.columns and "pred" not in df.columns:
                df["pred"] = df["pred_class"]
        return df
    raise ValueError(split_name)


def resolve_abs_image_path(rel: str, source: str = "") -> str | None:
    name = Path(str(rel)).name
    if source.startswith("int/"):
        year_map = {
            "int/2018": "2018",
            "int/2019": "2019",
            "int/2024": "2024",
            "int/2020_2023": "2020_2023",
        }
        if source in year_map:
            y = year_map[source]
            base = PROJECT_ROOT / "dataset/internal/training_2018_2024" / y / "crop_ui/images"
            if base.is_dir():
                hits = sorted(base.glob(f"*{name}*")) or sorted(base.glob(f"*{Path(name).stem}*"))
                if hits:
                    return str(hits[0])
        if source == "int/prospective":
            base = PROJECT_ROOT / "dataset/internal/prospective_2025/2025/crop_ui/images"
            if base.is_dir():
                hits = sorted(base.glob(f"*{name}*"))
                if hits:
                    return str(hits[0])
    resolved = resolve_crop_ui_path(rel)
    if resolved is not None and resolved.is_file() and "crop_ui" in str(resolved):
        return str(resolved)
    if source.startswith("ext/"):
        key = source.split("/", 1)[-1]
        hospital = EXTERNAL_HOSPITAL_ALIASES.get(key)
        if hospital:
            crop_dir = PROJECT_ROOT / "dataset/external" / hospital / "crop_ui/images"
            cand = crop_dir / name
            if cand.is_file():
                return str(cand)
            import re

            m = re.search(r"(pt\d+)[^0-9]*(\d+)", name, re.I)
            if m and crop_dir.is_dir():
                pat = f"*{m.group(1).lower()}*{m.group(2)}*"
                hits = sorted(crop_dir.glob(pat))
                if hits:
                    return str(hits[0])
            m2 = re.search(r"(\d+)\s*-\s*(\d+)", name)
            if m2 and crop_dir.is_dir():
                hits = sorted(crop_dir.glob(f"*{m2.group(1)}*{m2.group(2)}*"))
                if hits:
                    return str(hits[0])
    if source == "ext/multicenter":
        mc_dir = PROJECT_ROOT / "dataset/external/multicenter/images"
        if mc_dir.is_file() or mc_dir.is_dir():
            cand = mc_dir / name if (mc_dir / name).is_file() else None
            if cand:
                return str(cand)
        for base in (
            PROJECT_ROOT / "dataset/external/multicenter/crop_ui/images",
            PROJECT_ROOT / "dataset/external/福建省肿瘤医院/crop_ui/images",
        ):
            if base.is_dir():
                hits = sorted(base.glob(f"*{Path(name).stem.replace(' ', '*')}*"))
                if hits:
                    return str(hits[0])
    p = PROJECT_ROOT / str(rel).replace("\\", "/")
    if p.is_file():
        return str(p.resolve())
    return None


def pick_one(df: pd.DataFrame, source: str, prefer_t23: bool = True) -> pd.Series | None:
    sub = df[df["source"] == source].copy()
    if sub.empty:
        return None
    if prefer_t23:
        t23 = sub[sub["label"].isin([1, 2])]
        if len(t23):
            sub = t23
    sub = sub.copy()

    def _resolve_row(row: pd.Series) -> str | None:
        path = resolve_abs_image_path(row["image_path"], source)
        if path:
            return path
        pid = str(row.get("patient_id", "") or "").strip()
        if not pid:
            return None
        if source.startswith("int/"):
            year_map = {
                "int/2018": "2018",
                "int/2019": "2019",
                "int/2024": "2024",
                "int/2020_2023": "2020_2023",
            }
            if source in year_map:
                base = PROJECT_ROOT / "dataset/internal/training_2018_2024" / year_map[source] / "crop_ui/images"
                hits = sorted(base.glob(f"*{pid}*")) if base.is_dir() else []
                return str(hits[0]) if hits else None
            if source == "int/prospective":
                base = PROJECT_ROOT / "dataset/internal/prospective_2025/2025/crop_ui/images"
                hits = sorted(base.glob(f"*{pid}*")) if base.is_dir() else []
                return str(hits[0]) if hits else None
        return None

    sub["_resolved"] = sub.apply(_resolve_row, axis=1)
    sub = sub[sub["_resolved"].notna()]
    if sub.empty:
        return None
    sub["_score"] = sub.apply(_score_boundary, axis=1)
    sub = sub.sort_values("_score", ascending=False)
    return sub.iloc[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=PIPELINE_ROOT / "data/tstaging_4class/eval/t2t3_ppt_grid_8sources.csv",
    )
    args = parser.parse_args()

    rows = []
    for source, key, display, split_name in SOURCE_SPECS:
        pool = load_pool(split_name)
        prefer_t23 = source != "ext/multicenter"
        row = pick_one(pool, source, prefer_t23=prefer_t23)
        if row is None:
            print(f"SKIP (no rows): {source}")
            continue
        img = str(row["_resolved"])
        pred_val = row.get("pred")
        pred_int = int(pred_val) if pd.notna(pred_val) else int(row["label"])
        out = {
            "image_path": img,
            "roi_path": str(row.get("roi_path", "")),
            "patient_id": row.get("patient_id", ""),
            "label": int(row["label"]),
            "T_stage": row.get("T_stage", ""),
            "class_label": int(row["label"]),
            "source": source,
            "split": split_name,
            "pred": pred_int,
            "dataset_key": key,
            "dataset_display": display,
            "review_group": "err_T2T3" if int(row["label"]) != pred_int else "ok_T2T3",
        }
        for c in [f"prob_c{i}" for i in range(4)] + ["prob_T1", "prob_T2", "prob_T3", "prob_T4+"]:
            if c in row.index:
                out[c] = row[c]
        rows.append(out)
        gt = ["T1", "T2", "T3", "T4+"][int(row["label"])]
        pr = ["T1", "T2", "T3", "T4+"][pred_int]
        print(f"OK {display}: GT {gt} pred {pr} | {Path(img).name}")

    out_df = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.output, index=False)
    print(f"Wrote {len(out_df)} cases -> {args.output}")


if __name__ == "__main__":
    main()
