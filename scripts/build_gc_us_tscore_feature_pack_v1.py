#!/usr/bin/env python3
"""Build patient-level GC-US T-score feature pack v1 for modeling.

Joins morphology / margin / growth medians with unique_pooled labels + splits.
Keeps only features that survived split discrimination (see
pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/split_discrimination_v1/).

Outputs:
  pipeline/data/gc_us_tscore_features_v1/feature_pack_v1/
    patient_features.csv
    FEATURE_PACK.md
    meta.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PT = (
    PROJECT_ROOT
    / "pipeline/experiments/reports/imaging_truth_tstage_corr_v2/patient_table_unique_pooled.csv"
)
FEAT_ROOT = PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1"
OUT = FEAT_ROOT / "feature_pack_v1"

# Cross-split keepers + useful controls. Size kept as covariates only.
KEEP = {
    "core": [
        "morph_peak_sharpness_max",
        "morph_solidity",
        "morph_circularity",
        "morph_concavity_ratio",
        "morph_nrl_roughness",
        "margin_spic_robust",
        "margin_shape_solidity",
        "margin_shape_fd_high",
    ],
    "wall_layer": [
        "wall_serosa_interrupt",
        "wall_depth_frac_p90",
        "wall_v2_pen_ratio_sector",
        "wall_v2_composite",
        "wall_v2_remain_px",
        "wall_v2_serosa_proxy",
        "wall_fuse_serosa_remain",
    ],
    "size_covariates": [
        "morph_perimeter_px",
        "morph_area_px",
        "tumor_length_cm",
        "tumor_thickness_cm",
        "size_max_diameter_cm",
        "size_thickness_length_ratio",
    ],
    "markers": [
        "cea_binary",
        "cea_value",
    ],
    "seg_geometry": [
        "seg_short_axis_ratio",
    ],
    "dynamics": [
        "dyn_invasion_agree",
        "morph_peak_sharpness_max__frac_high",
        "margin_spic_robust__frac_high",
        "bt_v2_max_outward_depth__frac_high",
        "wall_v2_remain_px__frac_low",
        "wall_serosa_interrupt__frac_high",
    ],
    "controls": [
        "seg_irregularity",
    ],
    "growth_watch": [
        "bt_v2_max_outward_depth",
        "bt_v2_max_outward_depth__max",
        "growth_outward_protrusion_ratio",
        "growth_outward_protrusion_ratio__max",
    ],
    "image_channels_weak": [
        "margin_bof_high_mean",
        "margin_clear_robust",
    ],
}


def eval_split(source_splits: object) -> str:
    parts = set(str(source_splits).replace(" ", "").split(","))
    if "external" in parts:
        return "test_external"
    if "prospective" in parts and "train" not in parts and "val" not in parts:
        return "test_prospective"
    if "val" in parts:
        return "val"
    if "holdout" in parts:
        return "holdout"
    if "train" in parts or "prospective" in parts:
        return "train"
    return "other"


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
    base = pt[
        [
            "patient_id",
            "label",
            "tumor_length_cm",
            "source_splits",
            "seg_irregularity",
        ]
    ].copy()
    base["eval_split"] = base["source_splits"].map(eval_split)

    morph = pd.read_csv(FEAT_ROOT / "morphology/patient_features_median.csv")
    margin = pd.read_csv(FEAT_ROOT / "margin/patient_features_median.csv")
    growth = pd.read_csv(FEAT_ROOT / "growth/patient_features_median.csv")
    wall = pd.read_csv(FEAT_ROOT / "wall_layer/patient_features_median.csv")
    wall_v2 = pd.read_csv(FEAT_ROOT / "wall_layer/patient_features_axis_v2_median.csv")
    clinical = pd.read_csv(FEAT_ROOT / "clinical/patient_features.csv")
    dynamics = pd.read_csv(FEAT_ROOT / "dynamics/patient_features.csv")
    for df in (morph, margin, growth, wall, wall_v2, clinical, dynamics):
        df["patient_id"] = df["patient_id"].astype(str)
    # Fuse: serosa coverage + ContactGeom remain (rank-average; higher=deeper)
    wjoin = wall[["patient_id", "wall_serosa_interrupt"]].merge(
        wall_v2[["patient_id", "wall_v2_remain_px", "wall_v2_composite", "wall_v2_pen_ratio_sector", "wall_v2_serosa_proxy"]],
        on="patient_id",
        how="outer",
    )
    r_ser = wjoin["wall_serosa_interrupt"].rank(pct=True)
    r_rem = (-wjoin["wall_v2_remain_px"]).rank(pct=True)
    wjoin["wall_fuse_serosa_remain"] = 0.5 * r_ser + 0.5 * r_rem
    wall = wall.merge(
        wjoin[
            [
                "patient_id",
                "wall_v2_remain_px",
                "wall_v2_composite",
                "wall_v2_pen_ratio_sector",
                "wall_v2_serosa_proxy",
                "wall_fuse_serosa_remain",
            ]
        ],
        on="patient_id",
        how="left",
    )

    want = []
    for group, cols in KEEP.items():
        if group == "size_covariates":
            want.extend([c for c in cols if c != "tumor_length_cm"])
        elif group == "controls":
            continue
        else:
            want.extend(cols)

    # Keep each source family isolated.  Searching every source with the full
    # `want` list would merge the same growth max fields from both growth and
    # dynamics, producing pandas `_x` / `_y` duplicates.
    morph_want = KEEP["core"] + ["morph_perimeter_px", "morph_area_px"]
    margin_want = [
        "margin_spic_robust",
        "margin_shape_solidity",
        "margin_shape_fd_high",
        *KEEP["image_channels_weak"],
    ]
    growth_want = KEEP["growth_watch"]
    wall_want = KEEP["wall_layer"]
    clinical_want = [
        "tumor_thickness_cm",
        "size_max_diameter_cm",
        "size_thickness_length_ratio",
        *KEEP["markers"],
        *KEEP["seg_geometry"],
    ]
    dynamics_want = KEEP["dynamics"]

    morph_cols = [c for c in morph_want if c in morph.columns]
    margin_cols = [c for c in margin_want if c in margin.columns]
    growth_cols = [c for c in growth_want if c in growth.columns]
    wall_cols = [c for c in wall_want if c in wall.columns]
    clin_cols = [c for c in clinical_want if c in clinical.columns]
    dyn_cols = [c for c in dynamics_want if c in dynamics.columns]

    df = base.merge(morph[["patient_id"] + morph_cols], on="patient_id", how="left")
    df = df.merge(margin[["patient_id"] + margin_cols], on="patient_id", how="left")
    df = df.merge(growth[["patient_id"] + growth_cols], on="patient_id", how="left")
    df = df.merge(wall[["patient_id"] + wall_cols], on="patient_id", how="left")
    if clin_cols:
        df = df.merge(clinical[["patient_id"] + clin_cols], on="patient_id", how="left")
    if dyn_cols:
        df = df.merge(dynamics[["patient_id"] + dyn_cols], on="patient_id", how="left")

    feat_cols = (
        morph_cols
        + margin_cols
        + growth_cols
        + wall_cols
        + clin_cols
        + dyn_cols
        + ["seg_irregularity", "tumor_length_cm"]
    )
    feat_cols = list(dict.fromkeys([c for c in feat_cols if c in df.columns]))
    df["n_features_present"] = df[feat_cols].notna().sum(axis=1)
    df = df[df["n_features_present"] >= 3].copy()
    df.to_csv(out / "patient_features.csv", index=False)

    md = [
        "# GC-US T-score feature pack v1",
        "",
        "Built from split discrimination after external image-path fix;",
        "extended with clinical size/markers, wall v2, and multi-frame dynamics.",
        "",
        "## Groups",
        "",
        "### core (recommended for modeling)",
        "",
        *[f"- `{c}`" for c in KEEP["core"]],
        "",
        "### wall_layer (EUS five-layer soft proxies; not histologic GT)",
        "",
        *[f"- `{c}`" for c in KEEP["wall_layer"]],
        "",
        "### size_covariates (control length/size; do not treat as spiculation)",
        "",
        *[f"- `{c}`" for c in KEEP["size_covariates"]],
        "",
        "### markers",
        "",
        *[f"- `{c}`" for c in KEEP["markers"]],
        "",
        "### seg_geometry",
        "",
        *[f"- `{c}`" for c in KEEP["seg_geometry"]],
        "",
        "### dynamics (multi-frame frac_high / agree)",
        "",
        *[f"- `{c}`" for c in KEEP["dynamics"]],
        "",
        "### controls",
        "",
        *[f"- `{c}`" for c in KEEP["controls"]],
        "",
        "### growth_watch (domain-sensitive; prosp may flip)",
        "",
        *[f"- `{c}`" for c in KEEP["growth_watch"]],
        "",
        "### image_channels_weak (kept for ablation only)",
        "",
        *[f"- `{c}`" for c in KEEP["image_channels_weak"]],
        "",
        "## Split counts",
        "",
    ]
    vc = df["eval_split"].value_counts()
    for k, v in vc.items():
        md.append(f"- **{k}**: {int(v)}")
    md += [
        "",
        "## Rebuild",
        "",
        "```bash",
        "python3 scripts/build_gc_us_tscore_feature_pack_v1.py",
        "```",
        "",
        "Evidence: `pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/split_discrimination_v1/`",
        "",
    ]
    (out / "FEATURE_PACK.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    meta = {
        "n_patients": int(len(df)),
        "n_by_split": {str(k): int(v) for k, v in vc.items()},
        "keep": KEEP,
        "feature_cols": feat_cols,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
