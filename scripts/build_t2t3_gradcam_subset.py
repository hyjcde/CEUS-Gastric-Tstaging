"""Legacy script — prefer README §1–3 mainline. Do not use as default entry."""
# STATUS: legacy

#!/usr/bin/env python3
"""Build CSV subset for T2/T3 boundary Grad-CAM (resolved image paths)."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXP = (
    PROJECT_ROOT
    / "pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch"
    / "tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301"
)
PUTIAN_CROP_IMG = PROJECT_ROOT / "dataset/external/莆田学院附属医院/crop_ui/images"
PUTIAN_IMG = PUTIAN_CROP_IMG  # legacy alias
REGION_DIR = PROJECT_ROOT / "pipeline/data/tstaging_4class_region_contrastive_full/regions"
BOX_COLS = [
    "crop_box_x1",
    "crop_box_y1",
    "crop_box_x2",
    "crop_box_y2",
    "lumen_box_x1",
    "lumen_box_y1",
    "lumen_box_x2",
    "lumen_box_y2",
]


def resolve_image_path(rel: str) -> str | None:
    name = Path(rel).name
    for base in (PROJECT_ROOT, Path("/data/research/gastric/Tstaging")):
        p = base / rel
        if p.is_file() and "crop_ui" in str(p):
            return str(p)
        # Prefer crop_ui over original
        if "/original/" in str(rel).replace("\\", "/"):
            crop_rel = str(rel).replace("/original/images/", "/crop_ui/images/").replace(
                "/original/", "/crop_ui/images/"
            )
            crop_p = base / crop_rel
            if crop_p.is_file():
                return str(crop_p)
        if PUTIAN_CROP_IMG.is_dir():
            crop_p = PUTIAN_CROP_IMG / name
            if crop_p.is_file():
                return str(crop_p)
        if p.is_file():
            return str(p)
    m = re.search(r"pt\d+", name, re.I)
    if m and PUTIAN_CROP_IMG.is_dir():
        hits = sorted(PUTIAN_CROP_IMG.glob(f"*{m.group(0)}*"))
        if hits:
            return str(hits[0])
    return None


def merge_detection_boxes(df: pd.DataFrame) -> pd.DataFrame:
    """Attach lumen/crop boxes (match crop_ui vs original by patient_id + frame index)."""
    if not REGION_DIR.is_dir():
        return df
    tables = []
    for path in sorted(REGION_DIR.glob("*_clinical.csv")):
        header = pd.read_csv(path, nrows=0).columns
        keep = ["patient_id", "image_path"] + [c for c in BOX_COLS if c in header]
        if len(keep) > 2:
            tables.append(pd.read_csv(path, usecols=keep, low_memory=False))
    if not tables:
        return df

    import re

    def pf_key(row: pd.Series) -> tuple[str, int] | None:
        patient = str(row.get("patient_id", "") or "").strip().lower()
        name = Path(str(row.get("image_path", ""))).name
        m = re.search(r"(pt\d+)[^0-9]*(\d+)", name, flags=re.IGNORECASE)
        if m:
            return m.group(1).lower(), int(m.group(2))
        if patient:
            m2 = re.search(r"(\d+)", name)
            if m2:
                return patient, int(m2.group(1))
        return None

    region = pd.concat(tables, ignore_index=True)
    keys = region.apply(pf_key, axis=1)
    region["_pf_patient"] = [k[0] if k else None for k in keys]
    region["_pf_frame"] = [k[1] if k else None for k in keys]
    region = region.dropna(subset=["_pf_patient", "_pf_frame"])
    region = region.drop_duplicates(subset=["_pf_patient", "_pf_frame"], keep="first")

    out = df.copy()
    out_keys = out.apply(
        lambda r: pf_key(pd.Series({"patient_id": r["patient_id"], "image_path": r["resolved_image"]})),
        axis=1,
    )
    out["_pf_patient"] = [k[0] if k else None for k in out_keys]
    out["_pf_frame"] = [k[1] if k else None for k in out_keys]
    add = ["_pf_patient", "_pf_frame"] + [c for c in BOX_COLS if c in region.columns]
    out = out.merge(region[add], on=["_pf_patient", "_pf_frame"], how="left")
    return out.drop(columns=["_pf_patient", "_pf_frame"], errors="ignore")


def main() -> None:
    df = pd.read_csv(EXP / "eval/test_external/test_predictions.csv")
    df["resolved_image"] = df.image_path.map(resolve_image_path)
    df = df[df.resolved_image.notna()]
    df = df[~df["resolved_image"].astype(str).str.contains(".baiduyun.", regex=False)]
    parts = []
    for name, mask in [
        ("err_T2_to_T3", (df.label == 1) & (df.pred == 2)),
        ("err_T3_to_T2", (df.label == 2) & (df.pred == 1)),
        ("ok_T2", (df.label == 1) & (df.pred == 1)),
        ("ok_T3", (df.label == 2) & (df.pred == 2)),
    ]:
        sub = df.loc[mask].head(6).copy()
        if len(sub):
            parts.append(sub.assign(review_group=name))
    out = pd.concat(parts, ignore_index=True)
    out["image_path"] = out["resolved_image"]
    out = merge_detection_boxes(out)
    out = out.drop(columns=["resolved_image"])
    path = EXP / "eval/test_external/t2t3_boundary_gradcam_subset.csv"
    out.to_csv(path, index=False)
    print(f"Wrote {path} ({len(out)} rows)")


if __name__ == "__main__":
    main()
