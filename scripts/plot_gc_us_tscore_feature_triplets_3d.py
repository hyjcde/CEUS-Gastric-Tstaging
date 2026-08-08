#!/usr/bin/env python3
"""3D triplets for GC-US T-score morph/margin features (G3 style).

Joins feature_pack_v1 with unique_pooled clinical size/CEA, then plots
Length x Thickness x {feature} scatters (plus a pure morph triad).

Style matches scripts/plot_imaging_truth_triplet_3d.py (white share pack).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from plot_imaging_truth_triplet_3d import (  # noqa: E402
    SHARE,
    apply_style,
    pick_font,
    plot_interactive,
    plot_static,
    select_triplet,
    to_num,
)

PT = (
    PROJECT_ROOT
    / "pipeline/experiments/reports/imaging_truth_tstage_corr_v2"
    / "patient_table_unique_pooled.csv"
)
PACK = PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1/feature_pack_v1/patient_features.csv"
OUT = PROJECT_ROOT / "pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/triplets_3d"
FIG = PROJECT_ROOT / "results/visualizations/tstage/gc_us_tscore_triplets_3d_20260729"

TRIPLETS = [
    {
        "id": "G13_size_peak_sharpness",
        "title": "G13 Size + peak sharpness",
        "features": ("tumor_length_cm", "tumor_thickness_cm", "morph_peak_sharpness_max"),
        "labels": ("Length (cm)", "Thickness (cm)", "Peak sharpness"),
        "rationale": "大小主项 + 跨 split 最稳形态特征 morph_peak_sharpness_max",
        "tier": "tscore_v1",
        "share_png": "39_triplet_G13_length_thickness_peak_sharpness_3d.png",
        "share_html": "39_triplet_G13_length_thickness_peak_sharpness_3d_interactive.html",
    },
    {
        "id": "G14_size_spic_robust",
        "title": "G14 Size + spic_robust",
        "features": ("tumor_length_cm", "tumor_thickness_cm", "margin_spic_robust"),
        "labels": ("Length (cm)", "Thickness (cm)", "Spiculation robust"),
        "rationale": "大小主项 + margin_spic_robust (前瞻强, external 弱)",
        "tier": "tscore_v1",
        "share_png": "40_triplet_G14_length_thickness_spic_robust_3d.png",
        "share_html": "40_triplet_G14_length_thickness_spic_robust_3d_interactive.html",
    },
    {
        "id": "G15_size_solidity",
        "title": "G15 Size + solidity",
        "features": ("tumor_length_cm", "tumor_thickness_cm", "morph_solidity"),
        "labels": ("Length (cm)", "Thickness (cm)", "Solidity"),
        "rationale": "大小主项 + morph_solidity (越低越不规则)",
        "tier": "tscore_v1",
        "share_png": "41_triplet_G15_length_thickness_solidity_3d.png",
        "share_html": "41_triplet_G15_length_thickness_solidity_3d_interactive.html",
    },
    {
        "id": "G16_cea_peak_sharpness",
        "title": "G16 Length + CEA + peak sharpness",
        "features": ("tumor_length_cm", "cea_value", "morph_peak_sharpness_max"),
        "labels": ("Length (cm)", "CEA", "Peak sharpness"),
        "rationale": "G3 的 CEA 轴换成与 peak sharpness 同框 (长度仍保留)",
        "tier": "tscore_v1",
        "share_png": "42_triplet_G16_length_cea_peak_sharpness_3d.png",
        "share_html": "42_triplet_G16_length_cea_peak_sharpness_3d_interactive.html",
    },
    {
        "id": "G17_morph_triad",
        "title": "G17 Morph triad (no clinical size)",
        "features": (
            "morph_peak_sharpness_max",
            "morph_solidity",
            "margin_spic_robust",
        ),
        "labels": ("Peak sharpness", "Solidity", "Spiculation robust"),
        "rationale": "纯形态/毛刺三元组 (不含临床长径厚度)",
        "tier": "tscore_v1",
        "share_png": "43_triplet_G17_peak_solidity_spic_3d.png",
        "share_html": "43_triplet_G17_peak_solidity_spic_3d_interactive.html",
    },
    {
        "id": "G18_thickness_cea_peak",
        "title": "G18 Thickness + CEA + peak sharpness",
        "features": ("tumor_thickness_cm", "cea_value", "morph_peak_sharpness_max"),
        "labels": ("Thickness (cm)", "CEA", "Peak sharpness"),
        "rationale": "G3 另两轴 (厚度, CEA) + peak sharpness",
        "tier": "tscore_v1",
        "share_png": "44_triplet_G18_thickness_cea_peak_sharpness_3d.png",
        "share_html": "44_triplet_G18_thickness_cea_peak_sharpness_3d_interactive.html",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def select_triplet_ext(df: pd.DataFrame, feats: tuple[str, str, str]) -> pd.DataFrame:
    """Extend select_triplet filters for morph_/margin_ columns."""
    sub = select_triplet(df, feats)
    # morph/margin already kept if finite via select_triplet's generic path;
    # ensure positive peak sharpness where relevant
    a, b, c = feats
    for col, name in [("x", a), ("y", b), ("z", c)]:
        if name.startswith("morph_") or name.startswith("margin_"):
            sub = sub[sub[col].notna()].copy()
    return sub.reset_index(drop=True)


def load_joined() -> pd.DataFrame:
    pt = pd.read_csv(PT)
    pack = pd.read_csv(PACK)
    pt["patient_id"] = pt["patient_id"].astype(str)
    pack["patient_id"] = pack["patient_id"].astype(str)
    cols = [
        "patient_id",
        "label",
        "tumor_length_cm",
        "tumor_thickness_cm",
        "cea_value",
        "seg_irregularity",
    ]
    # cea may already be in pack? not in feature pack — from pt
    for c in cols:
        if c not in pt.columns and c != "patient_id":
            raise KeyError(c)
    feat_cols = [
        "morph_peak_sharpness_max",
        "morph_solidity",
        "morph_circularity",
        "margin_spic_robust",
        "margin_shape_solidity",
        "margin_shape_fd_high",
    ]
    df = pt[cols].merge(pack[["patient_id"] + feat_cols], on="patient_id", how="inner")
    for c in feat_cols + ["tumor_length_cm", "tumor_thickness_cm", "cea_value", "label"]:
        df[c] = to_num(df[c])
    return df


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    ap.add_argument("--fig-dir", type=Path, default=FIG)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    out, fig_dir = args.out_dir, args.fig_dir
    out.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)
    SHARE.mkdir(parents=True, exist_ok=True)
    apply_style(pick_font())

    df = load_joined()
    rows = []
    for g in TRIPLETS:
        sub = select_triplet_ext(df, g["features"])
        stem = fig_dir / g["id"]
        plot_static(sub, g, stem)
        html = out / f"{g['id']}_interactive.html"
        plot_interactive(sub, g, html)
        v1 = Path(str(stem) + "_view1.png")
        v2 = Path(str(stem) + "_view2.png")
        if v1.exists():
            (SHARE / g["share_png"]).write_bytes(v1.read_bytes())
            (out / v1.name).write_bytes(v1.read_bytes())
        if v2.exists():
            alt = g["share_png"].replace(".png", "_altview.png")
            (SHARE / alt).write_bytes(v2.read_bytes())
            (out / v2.name).write_bytes(v2.read_bytes())
        (SHARE / g["share_html"]).write_bytes(html.read_bytes())
        for suf in (".png", ".pdf"):
            for tag in ("_view1", "_view2"):
                p = Path(str(stem) + tag).with_suffix(suf)
                if p.exists():
                    (out / p.name).write_bytes(p.read_bytes())
        rows.append(
            {
                "group_id": g["id"],
                "title": g["title"],
                "tier": g["tier"],
                "f1": g["features"][0],
                "f2": g["features"][1],
                "f3": g["features"][2],
                "n": int(len(sub)),
                "rationale": g["rationale"],
                "share_png": g["share_png"],
                "share_html": g["share_html"],
            }
        )
        print(f"[ok] {g['id']} N={len(sub)}")

    tab = pd.DataFrame(rows)
    tab.to_csv(out / "triplet_groups.csv", index=False)
    lines = [
        "# GC-US T-score feature 3D triplets",
        "",
        f"- Generated: `{utc_now()}`",
        f"- Join: unique_pooled x feature_pack_v1",
        "",
        "| ID | Features | N | Rationale |",
        "|---|---|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['group_id']}` | `{r['f1']}`, `{r['f2']}`, `{r['f3']}` | {r['n']} | {r['rationale']} |"
        )
    lines += [
        "",
        "## Share copies",
        "",
        "- `results/visualizations/tstage/imaging_truth_share_white_20260729/39`–`44_*.png`",
        "",
        "Primary comparison to G3: `39_triplet_G13_..._altview.png` (Length / Thickness / Peak sharpness).",
        "",
        "Rebuild: `python3 scripts/plot_gc_us_tscore_feature_triplets_3d.py`",
        "",
    ]
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "meta.json").write_text(
        json.dumps({"generated": utc_now(), "groups": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # append share README rows
    readme = SHARE / "README.md"
    if readme.exists():
        t = readme.read_text(encoding="utf-8")
        extras = [
            "| `39_triplet_G13_length_thickness_peak_sharpness_3d.png` | 三元组G13：长径 x 厚度 x peak sharpness |",
            "| `40_triplet_G14_length_thickness_spic_robust_3d.png` | 三元组G14：长径 x 厚度 x spic_robust |",
            "| `41_triplet_G15_length_thickness_solidity_3d.png` | 三元组G15：长径 x 厚度 x solidity |",
            "| `42_triplet_G16_length_cea_peak_sharpness_3d.png` | 三元组G16：长径 x CEA x peak sharpness |",
            "| `43_triplet_G17_peak_solidity_spic_3d.png` | 三元组G17：peak x solidity x spic_robust |",
            "| `44_triplet_G18_thickness_cea_peak_sharpness_3d.png` | 三元组G18：厚度 x CEA x peak sharpness |",
        ]
        for line in extras:
            key = line.split("`")[1]
            if key not in t:
                t = t.rstrip() + "\n" + line
        readme.write_text(t.rstrip() + "\n", encoding="utf-8")

    print(json.dumps({"out": str(out), "share": str(SHARE), "n_groups": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
