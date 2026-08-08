#!/usr/bin/env python3
"""Pack clinical cohort features for GC-US T-score (size / markers / seg geometry).

No image I/O — joins imaging-truth patient table (+ optional report NLP via master).

Writes:
  pipeline/data/gc_us_tscore_features_v1/clinical/
    patient_features.csv
    meta.json
    CLINICAL_FEATURES.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PT = (
    PROJECT_ROOT
    / "pipeline/experiments/reports/imaging_truth_tstage_corr_v2"
    / "patient_table_unique_pooled.csv"
)
MASTER = PROJECT_ROOT / "dataset/tables/patient_clinical_master.csv"
REPORT = PROJECT_ROOT / "data/processed/clinical_reports/patient_report_features_preop.csv"
DEEP = PROJECT_ROOT / "data/processed/clinical_reports/deep_report_cues_v1/patient_deep_report_cues.csv"
OUT = PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1/clinical"

CLINICAL_COLS = [
    "tumor_length_cm",
    "tumor_thickness_cm",
    "cea_value",
    "cea_binary",
    "ca199_value",
    "ca199_binary",
    "tumor_location",
    "tumor_location_name",
    "seg_short_axis_ratio",
    "seg_long_axis_ratio",
    "seg_area_ratio",
    "seg_irregularity",
    "seg_boundary_clarity",
]

REPORT_COLS = [
    "report_wall_thickening",
    "report_wall_irregularity",
    "report_ulcer_or_mass",
    "report_possible_t3_t4",
    "report_adjacent_invasion",
    "report_lymph_node_suspicious",
    "report_metastasis_or_peritoneal",
    "ultrasound_report_available",
]

DEEP_COLS = [
    "serosa_suspect",
    "adjacent_invasion",
    "layer_unclear",
    "wall_irregular",
    "wall_thickening_focal",
    "wall_thickening_diffuse",
    "report_advanced_evidence_score",
    "report_early_evidence_score",
    "deep_report_available",
]


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    pt = pd.read_csv(PT)
    pt["patient_id"] = pt["patient_id"].astype(str)
    keep = ["patient_id", "label"] + [c for c in CLINICAL_COLS if c in pt.columns]
    df = pt[keep].copy()

    # thickness / length ratio (design: size domain)
    if "tumor_length_cm" in df.columns and "tumor_thickness_cm" in df.columns:
        df["size_thickness_length_ratio"] = df["tumor_thickness_cm"] / df["tumor_length_cm"].clip(lower=0.1)
        df["size_max_diameter_cm"] = df[["tumor_length_cm", "tumor_thickness_cm"]].max(axis=1)

    n_report = 0
    if MASTER.exists() and REPORT.exists():
        master = pd.read_csv(MASTER)
        master["patient_id_norm"] = master["patient_id_norm"].astype(str)
        master["patient_uid"] = master["patient_uid"].astype(str)
        rep = pd.read_csv(REPORT)
        rep["clinical_patient_uid"] = rep["clinical_patient_uid"].astype(str)
        bridge = master[["patient_uid", "patient_id_norm"]].drop_duplicates("patient_uid")
        rjoin = rep.merge(bridge, left_on="clinical_patient_uid", right_on="patient_uid", how="inner")
        rcols = [c for c in REPORT_COLS if c in rjoin.columns]
        rjoin = rjoin[["patient_id_norm"] + rcols].drop_duplicates("patient_id_norm")
        rjoin = rjoin.rename(columns={"patient_id_norm": "patient_id"})
        df = df.merge(rjoin, on="patient_id", how="left")
        n_report = int(df[rcols[0]].notna().sum()) if rcols else 0

        if DEEP.exists():
            deep = pd.read_csv(DEEP)
            deep["clinical_patient_uid"] = deep["clinical_patient_uid"].astype(str)
            djoin = deep.merge(bridge, left_on="clinical_patient_uid", right_on="patient_uid", how="inner")
            dcols = [c for c in DEEP_COLS if c in djoin.columns]
            djoin = djoin[["patient_id_norm"] + dcols].drop_duplicates("patient_id_norm")
            djoin = djoin.rename(columns={"patient_id_norm": "patient_id"})
            # prefix deep-only to avoid adjacent_invasion clash with report
            rename = {c: f"deep_{c}" if c in df.columns else c for c in dcols}
            djoin = djoin.rename(columns=rename)
            df = df.merge(djoin, on="patient_id", how="left")

    df.to_csv(out / "patient_features.csv", index=False)
    meta = {
        "n_patients": int(len(df)),
        "n_with_report_flags": n_report,
        "clinical_cols": [c for c in CLINICAL_COLS if c in df.columns],
        "derived": [c for c in df.columns if c.startswith("size_")],
        "report_cols": [c for c in df.columns if c.startswith("report_") or c in REPORT_COLS],
        "deep_cols": [c for c in df.columns if c.startswith("deep_") or c in DEEP_COLS],
        "source_pt": str(PT.relative_to(PROJECT_ROOT)),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    md = [
        "# Clinical cohort features for T-score",
        "",
        "Size / markers / seg geometry from imaging-truth patient table;",
        "optional preop report NLP via `patient_clinical_master.patient_uid`.",
        "",
        f"- Patients: **{len(df)}**",
        f"- With report flags: **{n_report}**",
        "",
        "## Rebuild",
        "",
        "```bash",
        "python3 scripts/extract_gc_us_clinical_cohort_features_v1.py",
        "```",
        "",
    ]
    (out / "CLINICAL_FEATURES.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
