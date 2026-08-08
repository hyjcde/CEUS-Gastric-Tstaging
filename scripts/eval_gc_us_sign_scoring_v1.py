#!/usr/bin/env python3
"""Patient-level research validation for GC-US sign scoring.

Reuses feature-pack v2 train-only cuts on the fixed patient-level split and
reports soft-band accuracy, T1/T2 overstaging, coverage, and growth-proxy
weak-label consistency.

Does NOT rewrite product rubric cutpoints (ccus_t_rubric_v1.4_us).
Wall/growth proxies remain research/card-only until clinical gate clears.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.gc_us_tscore_featurepack_v2 import (  # noqa: E402
    STAGE,
    fit_I_cuts,
    fit_imaging_cuts,
    fit_stage_cuts,
    map_score_to_stage,
    score_row,
)
from pipeline.agent.signs.schema import RUBRIC_ID, SCHEMA_VERSION  # noqa: E402

DEFAULT_PACK_LOCAL = (
    PROJECT_ROOT / "pipeline/data/gc_us_tscore_features_v1/feature_pack_v1/patient_features.csv"
)
DEFAULT_OUT_LOCAL = PROJECT_ROOT / "docs/plans/ccus_t_scoring/sign_scoring_validation_v1"

IMG_COLS = [
    "morph_peak_sharpness_max",
    "morph_circularity",
    "morph_solidity",
    "margin_spic_robust",
    "morph_nrl_roughness",
    "margin_shape_solidity",
    "wall_serosa_interrupt",
    "dyn_invasion_agree",
    "wall_depth_frac_p90",
    "wall_v2_remain_px",
    "growth_outward_protrusion_ratio__max",
]


def label_to_name(k: int) -> str:
    return STAGE[int(k)] if 0 <= int(k) < 4 else "cTx"


def overstage_rate(y_true: np.ndarray, y_pred: np.ndarray, true_k: int, min_pred_k: int) -> dict:
    mask = y_true == true_k
    n = int(mask.sum())
    if n == 0:
        return {"n": 0, "rate": None}
    rate = float((y_pred[mask] >= min_pred_k).mean())
    return {"n": n, "rate": rate}


def adjacent_acc(y_true: np.ndarray, y_pred: np.ndarray, a: int, b: int) -> dict:
    mask = np.isin(y_true, [a, b]) & np.isin(y_pred, [a, b])
    n = int(mask.sum())
    if n == 0:
        return {"n": 0, "acc": None}
    return {"n": n, "acc": float((y_true[mask] == y_pred[mask]).mean())}


def coverage_flags(row: pd.Series) -> dict:
    present = {
        "length": np.isfinite(row.get("tumor_length_cm", np.nan)),
        "thickness": np.isfinite(row.get("tumor_thickness_cm", np.nan)),
        "cea": np.isfinite(row.get("cea_binary", np.nan)) or np.isfinite(row.get("cea_value", np.nan)),
        "morphology": all(
            np.isfinite(row.get(c, np.nan))
            for c in ("morph_peak_sharpness_max", "morph_circularity", "morph_solidity")
        ),
        "margin": all(
            np.isfinite(row.get(c, np.nan)) for c in ("margin_spic_robust", "morph_nrl_roughness")
        ),
        "wall_proxy": all(
            np.isfinite(row.get(c, np.nan))
            for c in ("wall_serosa_interrupt", "dyn_invasion_agree", "wall_depth_frac_p90")
        ),
        "growth_proxy": np.isfinite(row.get("growth_outward_protrusion_ratio__max", np.nan))
        or np.isfinite(row.get("growth_outward_protrusion_ratio", np.nan)),
        "continuity_proxy": np.isfinite(row.get("bt_v2_max_outward_depth__frac_high", np.nan))
        or np.isfinite(row.get("dyn_invasion_agree", np.nan))
        or np.isfinite(row.get("morph_peak_sharpness_max__frac_high", np.nan)),
    }
    return {
        **{f"cov_{k}": int(v) for k, v in present.items()},
        "wall_proxy_present": int(present["wall_proxy"]),
        "growth_proxy_present": int(present["growth_proxy"]),
        "continuity_proxy_present": int(present["continuity_proxy"]),
    }


def growth_weak_label_report(df: pd.DataFrame) -> dict:
    from scipy.stats import spearmanr

    col = "growth_outward_protrusion_ratio__max"
    if col not in df.columns:
        return {"available": False, "note": "growth proxy column missing"}
    sub = df.dropna(subset=[col, "label"]).copy()
    if len(sub) < 20:
        return {"available": False, "n": int(len(sub)), "note": "too few"}
    rho, p = spearmanr(sub[col].astype(float), sub["label"].astype(int))
    return {
        "available": True,
        "n": int(len(sub)),
        "coverage": float(len(sub) / max(len(df), 1)),
        "spearman_rho_vs_path_T": float(rho),
        "p_value": float(p),
        "note": "weak_label_only_not_imaging_growth_truth",
    }


def evaluate_scheme(df: pd.DataFrame, pred_col: str, score_col: str) -> pd.DataFrame:
    rows = []
    for split, sub in df.groupby("eval_split"):
        yt = sub["label"].to_numpy(dtype=int)
        yp = sub[pred_col].to_numpy(dtype=int)
        valid = yp >= 0
        if valid.sum() == 0:
            continue
        yt_v, yp_v = yt[valid], yp[valid]
        over_t1 = overstage_rate(yt_v, yp_v, 0, 1)
        rows.append(
            {
                "split": split,
                "scheme": pred_col,
                "score_col": score_col,
                "n": int(valid.sum()),
                "soft_band_acc": float(accuracy_score(yt_v, yp_v)),
                "overstage_T1_to_T2plus": over_t1["rate"],
                "overstage_T1_to_T2plus_n": over_t1["n"],
                "adj_T2_T3_acc": adjacent_acc(yt_v, yp_v, 1, 2)["acc"],
                "adj_T3_T4_acc": adjacent_acc(yt_v, yp_v, 2, 3)["acc"],
                "coverage_imaging_complete": float(sub["imaging_complete"].mean()),
                "coverage_growth_proxy": float(sub["growth_proxy_present"].mean()),
                "coverage_wall_proxy": float(sub["wall_proxy_present"].mean()),
                "coverage_continuity_proxy": float(sub["continuity_proxy_present"].mean()),
                "mean_lean_I": float(pd.to_numeric(sub["lean_I"], errors="coerce").mean()),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pack", type=Path, default=DEFAULT_PACK_LOCAL)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT_LOCAL)
    ap.add_argument(
        "--also-run-featurepack-v2",
        action="store_true",
        help="Also write canonical featurepack_score_v2 into --out/featurepack_v2",
    )
    args = ap.parse_args()
    if not args.pack.exists():
        raise SystemExit(f"feature pack not found: {args.pack}")

    df = pd.read_csv(args.pack)
    if "eval_split" not in df.columns:
        raise SystemExit("eval_split required (patient-level split)")

    train = df[df["eval_split"] == "train"].copy()
    train_img = train.dropna(subset=[c for c in IMG_COLS if c in train.columns])
    cuts = fit_imaging_cuts(train_img if len(train_img) >= 50 else train)

    scored_rows = []
    for _, row in df.iterrows():
        sc = score_row(row, cuts)
        cov = coverage_flags(row)
        item_map = {it["id"]: it for it in sc["items"]}
        scored_rows.append(
            {
                "patient_id": row["patient_id"],
                "label": int(row["label"]),
                "label_name": label_to_name(int(row["label"])),
                "eval_split": row["eval_split"],
                "total": sc["total"],
                "max_included": sc["max_included"],
                "I": sc["I"],
                "lean_total": sc["lean_total"],
                "lean_max": sc["lean_max"],
                "lean_I": sc["lean_I"],
                "imaging_complete": bool(sc["imaging_complete"]),
                "pts_length": item_map.get("length", {}).get("points"),
                "pts_thickness": item_map.get("thickness", {}).get("points"),
                "pts_morphology": item_map.get("morphology", {}).get("points"),
                "pts_margin": item_map.get("margin", {}).get("points"),
                "pts_wall": item_map.get("wall", {}).get("points"),
                "pts_growth": item_map.get("growth", {}).get("points"),
                "pts_marker": item_map.get("marker", {}).get("points"),
                "growth_status": "proxy" if cov["growth_proxy_present"] else "missing",
                "wall_status": "proxy" if cov["wall_proxy_present"] else "missing",
                "continuity_status": "proxy" if cov["continuity_proxy_present"] else "missing",
                "product_ct_unlocked": False,
                "product_rubric_id": RUBRIC_ID,
                "schema_version": SCHEMA_VERSION,
                **cov,
            }
        )

    scores = pd.DataFrame(scored_rows)

    # Train-only stage mapping (research). Never write these into product rubric.
    train_scores = scores[scores["eval_split"] == "train"].copy()
    fit_mask = train_scores["imaging_complete"]
    fit_df = train_scores[fit_mask] if int(fit_mask.sum()) >= 200 else train_scores
    lean_I_cuts = fit_I_cuts(fit_df["lean_I"].to_numpy(), fit_df["label"].to_numpy())
    lean_cuts = fit_stage_cuts(fit_df["lean_total"].to_numpy(), fit_df["label"].to_numpy())
    scores["size_only"] = scores["pts_length"].fillna(0).astype(int) + scores["pts_thickness"].fillna(0).astype(int)
    train_scores = scores[scores["eval_split"] == "train"].copy()
    size_cuts = fit_stage_cuts(
        train_scores["size_only"].to_numpy(), train_scores["label"].to_numpy()
    )

    scores["pred_lean_I"] = scores["lean_I"].map(
        lambda v: map_score_to_stage(v, lean_I_cuts) if np.isfinite(v) else -1
    )
    scores["pred_lean"] = scores["lean_total"].map(lambda s: map_score_to_stage(s, lean_cuts))
    scores["pred_size_only"] = scores["size_only"].map(lambda s: map_score_to_stage(s, size_cuts))
    scores["pred_hybrid"] = np.where(
        scores["imaging_complete"],
        scores["pred_lean_I"],
        scores["pred_size_only"],
    )
    for col in ("pred_lean_I", "pred_lean", "pred_size_only", "pred_hybrid"):
        scores[col.replace("pred_", "band_")] = scores[col].map(
            lambda k: label_to_name(int(k)) if int(k) >= 0 else "cTx"
        )

    args.out.mkdir(parents=True, exist_ok=True)
    scores.to_csv(args.out / "patient_scores_sign_validation.csv", index=False)

    metrics = pd.concat(
        [
            evaluate_scheme(scores, "pred_lean_I", "lean_I"),
            evaluate_scheme(scores, "pred_lean", "lean_total"),
            evaluate_scheme(scores, "pred_size_only", "size_only"),
            evaluate_scheme(scores, "pred_hybrid", "lean_I_or_size"),
        ],
        ignore_index=True,
    )
    metrics.to_csv(args.out / "metrics_by_split.csv", index=False)

    growth_report = growth_weak_label_report(df)
    (args.out / "growth_weak_label_report.json").write_text(
        json.dumps(growth_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    ext = scores[scores["eval_split"] == "test_external"]
    cm = confusion_matrix(ext["label"], ext["pred_hybrid"], labels=[0, 1, 2, 3])
    cm_df = pd.DataFrame(
        cm,
        index=[f"true_{s}" for s in STAGE],
        columns=[f"pred_{s}" for s in STAGE],
    )
    cm_df.to_csv(args.out / "confusion_external_hybrid.csv")

    summary = {
        "product_rubric_id": RUBRIC_ID,
        "schema_version": SCHEMA_VERSION,
        "cutpoints_frozen": True,
        "note": (
            "Research validation only. Do not upgrade product I cutpoints until "
            "docs/plans/ccus_t_scoring/rubric_v1.4_gate.md clinical gate clears."
        ),
        "wall_proxy_in_definite_ct": False,
        "growth_proxy_as_imaging_truth": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pack": str(args.pack),
        "n_patients": int(len(scores)),
        "splits": scores["eval_split"].value_counts().to_dict(),
        "train_only_cuts": {
            "lean_I_cuts": lean_I_cuts,
            "lean_absolute_cuts": lean_cuts,
            "size_only_cuts": size_cuts,
        },
        "metrics_external_hybrid": metrics[
            (metrics.scheme == "pred_hybrid") & (metrics.split == "test_external")
        ].to_dict("records"),
        "metrics_external_lean_I": metrics[
            (metrics.scheme == "pred_lean_I") & (metrics.split == "test_external")
        ].to_dict("records"),
        "metrics_external_size": metrics[
            (metrics.scheme == "pred_size_only") & (metrics.split == "test_external")
        ].to_dict("records"),
        "growth_weak_label": growth_report,
    }
    (args.out / "validation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    try:
        metrics_md = metrics.to_markdown(index=False)
    except Exception:
        metrics_md = metrics.to_string(index=False)

    readme = "\n".join(
        [
            "# GC-US sign scoring validation (patient-level)",
            "",
            f"- Generated: `{summary['generated_at']}`",
            f"- Product rubric (frozen): `{RUBRIC_ID}`",
            f"- Schema: `{SCHEMA_VERSION}`",
            f"- Pack: `{args.pack}`",
            f"- Patients: **{len(scores)}**",
            "",
            "## Rules",
            "",
            "- Patient-level split only; no external cutpoint tuning.",
            "- Wall proxy coverage is reported; never unlocks product definite cT.",
            "- Growth/continuity proxies are geometric; weak pathology labels are not imaging truth.",
            "- Product cutpoints remain gated by `rubric_v1.4_gate.md`.",
            "",
            "## Metrics by split",
            "",
            metrics_md,
            "",
            "## Growth weak-label report",
            "",
            "```json",
            json.dumps(growth_report, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )
    (args.out / "README.md").write_text(readme, encoding="utf-8")

    if args.also_run_featurepack_v2:
        import subprocess

        v2_out = args.out / "featurepack_v2"
        subprocess.check_call(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts/gc_us_tscore_featurepack_v2.py"),
                "--pack",
                str(args.pack),
                "--out",
                str(v2_out),
            ]
        )

    print(f"Wrote validation to {args.out}")
    print(json.dumps(summary["metrics_external_hybrid"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
