#!/usr/bin/env python3
"""Join GC-US feature patient tables to unique_pooled and run imaging-truth style stats.

Outputs under:
  pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/<batch>/

Usage:
  python3 scripts/analyze_gc_us_feature_batch_stats.py --batch morphology
  python3 scripts/analyze_gc_us_feature_batch_stats.py --batch margin
  python3 scripts/analyze_gc_us_feature_batch_stats.py --batch growth
  python3 scripts/analyze_gc_us_feature_batch_stats.py --batch all
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATIENT = (
    PROJECT_ROOT
    / "pipeline"
    / "experiments"
    / "reports"
    / "imaging_truth_tstage_corr_v2"
    / "patient_table_unique_pooled.csv"
)
FEATURE_ROOT = PROJECT_ROOT / "pipeline" / "data" / "gc_us_tscore_features_v1"
REPORT_ROOT = PROJECT_ROOT / "pipeline" / "experiments" / "reports" / "gc_us_tscore_feature_stats_v1"

BATCH_PREFIX = {
    "morphology": "morph_",
    "margin": "margin_",
    "growth": ("growth_", "bt_v2_"),
}

LABEL_NAMES = {0: "T1", 1: "T2", 2: "T3", 3: "T4+"}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--batch", choices=["morphology", "margin", "growth", "all"], default="all")
    ap.add_argument("--patient-table", type=Path, default=DEFAULT_PATIENT)
    ap.add_argument("--n-boot", type=int, default=500)
    return ap.parse_args()


def to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def valid(df: pd.DataFrame, col: str) -> pd.Series:
    v = to_num(df[col])
    return v.notna() & np.isfinite(v)


def spearman_boot(x: np.ndarray, y: np.ndarray, n_boot: int = 500, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    rho, p = stats.spearmanr(x, y)
    boots = []
    n = len(x)
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        r, _ = stats.spearmanr(x[idx], y[idx])
        if np.isfinite(r):
            boots.append(r)
    lo, hi = np.percentile(boots, [2.5, 97.5]) if boots else (np.nan, np.nan)
    return {
        "spearman_rho": float(rho),
        "spearman_p": float(p),
        "ci_low": float(lo),
        "ci_high": float(hi),
        "n": int(n),
    }


def partial_spearman_length(df: pd.DataFrame, feature: str) -> dict:
    mask = valid(df, feature) & valid(df, "tumor_length_cm") & df["label"].notna()
    sub = df.loc[mask, [feature, "label", "tumor_length_cm"]].copy()
    for c in sub.columns:
        sub[c] = to_num(sub[c])
    n = len(sub)
    out = {"n_partial_length": n, "partial_rho_length": np.nan, "partial_p_length": np.nan}
    if n < 30 or sub[feature].nunique() < 2:
        return out
    ranks = sub.rank(method="average")
    y = ranks["label"].to_numpy()
    x = ranks[feature].to_numpy()
    Z = np.column_stack([np.ones(n), ranks["tumor_length_cm"].to_numpy()])
    bx, *_ = np.linalg.lstsq(Z, x, rcond=None)
    by, *_ = np.linalg.lstsq(Z, y, rcond=None)
    rx = x - Z @ bx
    ry = y - Z @ by
    if np.std(rx) < 1e-12 or np.std(ry) < 1e-12:
        return out
    rho, p = stats.pearsonr(rx, ry)
    out["partial_rho_length"] = float(rho)
    out["partial_p_length"] = float(p)
    return out


def median_by_stage(df: pd.DataFrame, feature: str) -> dict:
    mask = valid(df, feature) & df["label"].notna()
    sub = df.loc[mask]
    meds = []
    for lab in range(4):
        vals = to_num(sub.loc[to_num(sub["label"]) == lab, feature]).dropna()
        meds.append(float(vals.median()) if len(vals) else np.nan)
    diffs = [meds[i + 1] - meds[i] for i in range(3) if pd.notna(meds[i]) and pd.notna(meds[i + 1])]
    mono = bool(diffs) and (all(d >= -1e-12 for d in diffs) or all(d <= 1e-12 for d in diffs))
    return {
        "median_T1": meds[0],
        "median_T2": meds[1],
        "median_T3": meds[2],
        "median_T4+": meds[3],
        "monotonic": mono,
    }


def adjacent_auc(df: pd.DataFrame, feature: str) -> float:
    mask = valid(df, feature) & df["label"].notna()
    sub = df.loc[mask, [feature, "label"]].copy()
    sub[feature] = to_num(sub[feature])
    sub["label"] = to_num(sub["label"]).astype(int)
    aucs = []
    for a, b in [(0, 1), (1, 2), (2, 3)]:
        part = sub[sub["label"].isin([a, b])]
        xa = part.loc[part["label"] == a, feature].to_numpy()
        xb = part.loc[part["label"] == b, feature].to_numpy()
        if len(xa) < 5 or len(xb) < 5:
            continue
        y = np.concatenate([np.zeros(len(xa)), np.ones(len(xb))])
        s = np.concatenate([xa, xb])
        u = stats.mannwhitneyu(s[y == 1], s[y == 0], alternative="two-sided").statistic
        aucs.append(float(u / (len(xa) * len(xb))))
    return float(np.mean(aucs)) if aucs else float("nan")


def decide_candidacy(row: dict) -> str:
    rho = abs(row.get("spearman_rho", np.nan))
    partial = abs(row["partial_rho_length"]) if pd.notna(row.get("partial_rho_length")) else None
    mono = bool(row.get("monotonic", False))
    mean_auc = row.get("mean_adj_auc", np.nan)
    feat = row["feature"]
    if feat.startswith("bt_v2_") or feat.startswith("growth_"):
        if pd.isna(rho) or rho < 0.15:
            return "redesign"
    if feat.endswith("_very_high_energy") or feat.endswith("legacy_perimeter_area"):
        return "drop"  # noise / control only
    if pd.notna(rho) and rho >= 0.4 and mono and (pd.isna(mean_auc) or mean_auc >= 0.55):
        if partial is not None and partial < 0.1:
            return "enter_low_redundant"
        return "enter_high"
    if pd.notna(rho) and rho >= 0.15 and mono:
        return "enter_low"
    if pd.notna(rho) and rho >= 0.15 and not mono:
        return "review_formula"
    return "drop"


def feature_cols_for_batch(patient_feat: pd.DataFrame, batch: str) -> list[str]:
    pref = BATCH_PREFIX[batch]
    cols = []
    for c in patient_feat.columns:
        if c in {"patient_id", "n_frames"} or c.endswith("__max") or c.endswith("__p90"):
            continue
        if isinstance(pref, tuple):
            if any(c.startswith(p) for p in pref):
                cols.append(c)
        elif c.startswith(pref):
            cols.append(c)
    # for growth, also evaluate max-agg redesign columns of key BT fields
    if batch == "growth":
        for base in [
            "bt_v2_max_outward_depth",
            "bt_v2_fraction_outside_lumen",
            "bt_v2_breakthrough_flag",
            "growth_outward_protrusion_ratio",
        ]:
            for suf in ("__max", "__p90"):
                c = f"{base}{suf}"
                if c in patient_feat.columns and c not in cols:
                    cols.append(c)
    return cols


def analyze_batch(batch: str, base: pd.DataFrame, n_boot: int) -> Path:
    feat_path = FEATURE_ROOT / batch / "patient_features_median.csv"
    if not feat_path.exists():
        raise FileNotFoundError(feat_path)
    feats = pd.read_csv(feat_path)
    feats["patient_id"] = feats["patient_id"].astype(str)
    work = base.copy()
    work["patient_id"] = work["patient_id"].astype(str)
    # prefer joining on patient_id; also try uid tail
    merged = work.merge(feats, on="patient_id", how="left", suffixes=("", "_feat"))
    if merged.filter(regex=r"^morph_|^margin_|^growth_|^bt_v2_").notna().any().sum() < 3:
        work["uid_tail"] = work["clinical_patient_uid"].astype(str).str.split("::").str[-1]
        merged = work.merge(feats, left_on="uid_tail", right_on="patient_id", how="left", suffixes=("", "_feat"))

    cols = feature_cols_for_batch(feats, batch)
    # drop validity flags from association (always ~1)
    cols = [c for c in cols if not c.endswith("_valid")]

    rows = []
    for feat in cols:
        if feat not in merged.columns:
            continue
        mask = valid(merged, feat) & merged["label"].notna()
        sub_x = to_num(merged.loc[mask, feat]).to_numpy()
        sub_y = to_num(merged.loc[mask, "label"]).to_numpy()
        if len(sub_x) < 30:
            continue
        sp = spearman_boot(sub_x, sub_y, n_boot=n_boot)
        part = partial_spearman_length(merged, feat)
        med = median_by_stage(merged, feat)
        auc = adjacent_auc(merged, feat)
        row = {
            "feature": feat,
            "coverage_n": int(mask.sum()),
            "coverage_frac": float(mask.mean()),
            **sp,
            **part,
            **med,
            "mean_adj_auc": auc,
        }
        # collinearity with legacy seg_irregularity if present
        if "seg_irregularity" in merged.columns and valid(merged, "seg_irregularity").sum() > 30:
            m2 = mask & valid(merged, "seg_irregularity")
            if m2.sum() > 30:
                r, p = stats.spearmanr(
                    to_num(merged.loc[m2, feat]),
                    to_num(merged.loc[m2, "seg_irregularity"]),
                )
                row["rho_vs_seg_irregularity"] = float(r)
                row["p_vs_seg_irregularity"] = float(p)
            else:
                row["rho_vs_seg_irregularity"] = np.nan
                row["p_vs_seg_irregularity"] = np.nan
        else:
            row["rho_vs_seg_irregularity"] = np.nan
            row["p_vs_seg_irregularity"] = np.nan
        row["candidacy"] = decide_candidacy(row)
        rows.append(row)

    out = REPORT_ROOT / batch
    out.mkdir(parents=True, exist_ok=True)
    cand = pd.DataFrame(rows).sort_values("spearman_rho", key=lambda s: s.abs(), ascending=False)
    cand.to_csv(out / "candidacy.csv", index=False)
    cand.to_csv(out / "feature_stats.csv", index=False)
    merged_path = out / "patient_table_joined.csv"
    keep = [
        c
        for c in merged.columns
        if c
        in {
            "clinical_patient_uid",
            "patient_id",
            "label",
            "t_stage_name",
            "tumor_length_cm",
            "tumor_thickness_cm",
            "seg_irregularity",
            "n_frames",
        }
        or c.startswith("morph_")
        or c.startswith("margin_")
        or c.startswith("growth_")
        or c.startswith("bt_v2_")
    ]
    merged[keep].to_csv(merged_path, index=False)

    lines = [
        f"# GC-US feature stats · {batch}",
        "",
        f"- Base: `{DEFAULT_PATIENT}`",
        f"- Features: `{feat_path}`",
        f"- Joined patients with any feature: "
        f"{int(merged.filter(regex='^morph_|^margin_|^growth_|^bt_v2_').notna().any(axis=1).sum())}",
        "",
        "## Candidacy",
        "",
        "| feature | n | ρ [CI] | partial\\|length | medians T1→T4+ | mono | adjAUC | vs seg_irreg | candidacy |",
        "|---|---:|---:|---:|---|:---:|---:|---:|---|",
    ]
    for _, r in cand.iterrows():
        ci = f"{r['spearman_rho']:.3f} [{r['ci_low']:.3f},{r['ci_high']:.3f}]"
        pr = f"{r['partial_rho_length']:.3f}" if pd.notna(r["partial_rho_length"]) else "—"
        meds = (
            f"{r['median_T1']:.3g} / {r['median_T2']:.3g} / "
            f"{r['median_T3']:.3g} / {r['median_T4+']:.3g}"
        )
        vs = f"{r['rho_vs_seg_irregularity']:.3f}" if pd.notna(r.get("rho_vs_seg_irregularity")) else "—"
        auc = f"{r['mean_adj_auc']:.3f}" if pd.notna(r["mean_adj_auc"]) else "—"
        lines.append(
            f"| `{r['feature']}` | {int(r['n'])} | {ci} | {pr} | {meds} | "
            f"{'Y' if r['monotonic'] else 'N'} | {auc} | {vs} | **{r['candidacy']}** |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "- Morphology uses NRL substantial peaks + mid/high Fourier (very-high band treated as annotation noise).",
        "- Growth: prefer `bt_v2_*__max` / `__p90` over median (breakthrough redesign).",
        "- `morph_legacy_perimeter_area` is a control (old P²/A); expected candidacy=drop.",
        "",
    ]
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    meta = {
        "batch": batch,
        "n_features": int(len(cand)),
        "candidacy_counts": cand["candidacy"].value_counts().to_dict() if len(cand) else {},
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"[ok] {batch}: {meta}")
    return out


def main() -> None:
    args = parse_args()
    base = pd.read_csv(args.patient_table)
    batches = ["morphology", "margin", "growth"] if args.batch == "all" else [args.batch]
    for b in batches:
        analyze_batch(b, base, args.n_boot)


if __name__ == "__main__":
    main()
