#!/usr/bin/env python3
"""
Build Xiehe-only train manifest for Agent / frozen validation (Phase 0).

Removes rows whose ``source`` starts with ``ext/`` from train.csv so external
centers are not mixed into internal training manifests used for agent eval.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "pipeline" / "data" / "tstaging_4class"
OUT_DIR = DATA_DIR / "splits" / "xiehe_single_center_v1"


def _filter_internal(df: pd.DataFrame) -> pd.DataFrame:
    if "source" not in df.columns:
        return df
    mask = ~df["source"].astype(str).str.startswith("ext/")
    return df.loc[mask].copy()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Xiehe-only CSV splits for Agent eval")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict = {"inputs": {}, "outputs": {}}

    for stem in ("train", "val"):
        src = args.data_dir / f"{stem}.csv"
        if not src.exists():
            continue
        df = pd.read_csv(src, low_memory=False)
        filtered = _filter_internal(df)
        out_path = args.out_dir / f"{stem}_internal_only.csv"
        filtered.to_csv(out_path, index=False)
        summary["inputs"][stem] = {
            "rows": int(len(df)),
            "patients": int(df["patient_id"].nunique()) if "patient_id" in df.columns else 0,
        }
        summary["outputs"][stem] = {
            "path": str(out_path.relative_to(PROJECT_ROOT)),
            "rows": int(len(filtered)),
            "patients": int(filtered["patient_id"].nunique()) if "patient_id" in filtered.columns else 0,
            "removed_rows": int(len(df) - len(filtered)),
        }

    ext_train = pd.read_csv(args.data_dir / "train.csv", low_memory=False)
    ext_rows = ext_train[ext_train["source"].astype(str).str.startswith("ext/")]
    ext_out = args.out_dir / "train_external_holdout_from_legacy_train.csv"
    ext_rows.to_csv(ext_out, index=False)
    summary["outputs"]["external_holdout"] = {
        "path": str(ext_out.relative_to(PROJECT_ROOT)),
        "rows": int(len(ext_rows)),
        "patients": int(ext_rows["patient_id"].nunique()),
    }

    manifest_path = args.out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote manifests under {args.out_dir}")


if __name__ == "__main__":
    main()
