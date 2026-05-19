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
PUTIAN_IMG = PROJECT_ROOT / "dataset/external/莆田学院附属医院/original/images"


def resolve_image_path(rel: str) -> str | None:
    for base in (PROJECT_ROOT, Path("/data/research/gastric/Tstaging")):
        p = base / rel
        if p.is_file():
            return str(p)
    name = Path(rel).name
    m = re.search(r"pt\d+", name, re.I)
    if m and PUTIAN_IMG.is_dir():
        hits = sorted(PUTIAN_IMG.glob(f"*{m.group(0)}*"))
        if hits:
            return str(hits[0])
    return None


def main() -> None:
    df = pd.read_csv(EXP / "eval/test_external/test_predictions.csv")
    df["resolved_image"] = df.image_path.map(resolve_image_path)
    df = df[df.resolved_image.notna()]
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
    out = out.drop(columns=["resolved_image"])
    path = EXP / "eval/test_external/t2t3_boundary_gradcam_subset.csv"
    out.to_csv(path, index=False)
    print(f"Wrote {path} ({len(out)} rows)")


if __name__ == "__main__":
    main()
