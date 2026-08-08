#!/usr/bin/env python3
"""GC-US T-score v2 from feature-pack fields (design Word + exploration).

Aligns with 《胃癌超声T分期GC-US_T评分体系设计方案》:
  size length/thickness, morphology, margin, wall layer, growth, markers.
Uses explored patient-level features from gc_us_tscore_features_v1.

Does NOT overwrite product rubric cutpoints (ccus_t_rubric_v1.4_us).
This is the research scoring path: train-fit imaging bins + soft T bands.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import (
    accuracy_score,
    cohen_kappa_score,
    confusion_matrix,
    roc_auc_score,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACK = (
    PROJECT_ROOT
    / "workstation_mirrors/gc_us_tscore_feature_bundle_20260803"
    / "data/gc_us_tscore_features_v1/feature_pack_v1/patient_features.csv"
)
DEFAULT_OUT = (
    PROJECT_ROOT / "docs/plans/ccus_t_scoring/featurepack_score_v2"
)

STAGE = ["T1", "T2", "T3", "T4+"]
SCHEME = "gc_us_tscore_v2_featurepack"


@dataclass
class DimSpec:
    id: str
    label: str
    max_points: int
    design_note: str


DIMENSIONS = [
    DimSpec("length", "肿瘤长径", 3, "设计方案 ≤30/50/70/>70 mm"),
    DimSpec("thickness", "肿瘤厚径", 3, "设计方案 ≤10/20/30/>30 mm"),
    DimSpec("morphology", "肿瘤形态", 2, "规则0 / 局部不规则1 / 浸润型2"),
    DimSpec("margin", "肿瘤边界", 3, "清晰0 / 部分模糊1 / 毛刺分叶2 / 外侵消失3"),
    DimSpec("wall", "胃壁结构侵犯", 6, "黏膜下0 / 肌层2 / 浆膜下4 / 浆膜5 / 邻近6"),
    DimSpec("growth", "生长方式", 3, "膨胀0 / 局部浸润1 / 明显浸润2 / 跨壁3"),
    DimSpec("marker", "肿瘤标志物", 2, "正常0 / 单项1 / 多项2；本包仅 CEA"),
]


def _finite(x) -> bool:
    return x is not None and np.isfinite(x)


def grade_length_cm(cm: float) -> tuple[int, str]:
    mm = cm * 10.0
    if mm <= 30:
        return 0, f"长径 {mm:.0f} mm ≤30"
    if mm <= 50:
        return 1, f"长径 {mm:.0f} mm ≤50"
    if mm <= 70:
        return 2, f"长径 {mm:.0f} mm ≤70"
    return 3, f"长径 {mm:.0f} mm >70"


def grade_thickness_cm(cm: float) -> tuple[int, str]:
    mm = cm * 10.0
    if mm <= 10:
        return 0, f"厚径 {mm:.0f} mm ≤10"
    if mm <= 20:
        return 1, f"厚径 {mm:.0f} mm ≤20"
    if mm <= 30:
        return 2, f"厚径 {mm:.0f} mm ≤30"
    return 3, f"厚径 {mm:.0f} mm >30"


def grade_marker(cea_binary, cea_value) -> tuple[int | None, str]:
    """Design: 0 normal / 1 single / 2 multiple. Pack has CEA only → 0/1."""
    if _finite(cea_binary):
        g = int(cea_binary > 0.5)
        return g, ("CEA 升高（单项）" if g else "CEA 正常")
    if _finite(cea_value):
        g = 1 if cea_value > 5 else 0
        return g, f"CEA={cea_value:.2g}（{'升高' if g else '正常'}）"
    return None, "标志物缺失"


def _z(series: pd.Series) -> pd.Series:
    mu = series.mean()
    sd = series.std(ddof=0)
    if not np.isfinite(sd) or sd < 1e-9:
        return pd.Series(np.zeros(len(series)), index=series.index)
    return (series - mu) / sd


def fit_imaging_cuts(train: pd.DataFrame) -> dict:
    """Train-only raw-feature quantile cuts (domain-shift friendlier than z-composites)."""

    def q(col: str, qs: list[float]) -> list[float]:
        return [float(np.nanquantile(train[col].astype(float).to_numpy(), qq)) for qq in qs]

    return {
        # morphology 0/1/2: high peak / low circularity / low solidity
        "peak_cuts": q("morph_peak_sharpness_max", [1 / 3, 2 / 3]),
        "circ_cuts": q("morph_circularity", [1 / 3, 2 / 3]),  # lower = worse
        "solid_cuts": q("morph_solidity", [1 / 3, 2 / 3]),
        # margin 0/1/2/3
        "spic_cuts": q("margin_spic_robust", [0.25, 0.50, 0.75]),
        "nrl_cuts": q("morph_nrl_roughness", [0.25, 0.50, 0.75]),
        # wall design ladder 0/2/4/5/6 from serosa + dynamics + depth
        "serosa_cuts": q("wall_serosa_interrupt", [0.35, 0.55, 0.70, 0.85]),
        "dyn_cuts": q("dyn_invasion_agree", [0.35, 0.55, 0.70, 0.85]),
        "depth_cuts": q("wall_depth_frac_p90", [0.35, 0.55, 0.70, 0.85]),
        # growth 0/1/2/3
        "protr_cuts": q("growth_outward_protrusion_ratio__max", [0.30, 0.60, 0.85]),
        "n_train_imaging": int(len(train)),
    }


def _up(value: float, cuts: list[float]) -> int:
    """Higher value → higher grade index 0..len(cuts)."""
    g = 0
    for c in cuts:
        if value > c:
            g += 1
        else:
            break
    return g


def _down(value: float, cuts: list[float]) -> int:
    """Lower value → higher grade index."""
    g = 0
    for c in reversed(cuts):
        if value < c:
            g += 1
        else:
            break
    return g


def grade_imaging(row: pd.Series, cuts: dict) -> dict[str, tuple[int, str] | None]:
    """Return design points for morph/margin/wall/growth or None if missing."""
    out: dict[str, tuple[int, str] | None] = {
        "morphology": None,
        "margin": None,
        "wall": None,
        "growth": None,
    }

    peak, circ, solid = row.get("morph_peak_sharpness_max"), row.get("morph_circularity"), row.get("morph_solidity")
    if _finite(peak) and _finite(circ) and _finite(solid):
        # vote of three oriented grades, clamp to 0–2
        g = int(np.clip(round((_up(float(peak), cuts["peak_cuts"]) + _down(float(circ), cuts["circ_cuts"]) + _down(float(solid), cuts["solid_cuts"])) / 3), 0, 2))
        out["morphology"] = (g, f"形态综合 g={g}（peak={float(peak):.2f}, circ={float(circ):.2f}, solid={float(solid):.2f}）")

    spic, nrl = row.get("margin_spic_robust"), row.get("morph_nrl_roughness")
    if _finite(spic) and _finite(nrl):
        g = int(np.clip(round((_up(float(spic), cuts["spic_cuts"]) + _up(float(nrl), cuts["nrl_cuts"])) / 2), 0, 3))
        out["margin"] = (g, f"边界综合 g={g}（spic={float(spic):.2f}, nrl={float(nrl):.2f}）")

    ser, dyn, dep = row.get("wall_serosa_interrupt"), row.get("dyn_invasion_agree"), row.get("wall_depth_frac_p90")
    if _finite(ser) and _finite(dyn) and _finite(dep):
        # max ladder from three proxies → design points
        idx = max(_up(float(ser), cuts["serosa_cuts"]), _up(float(dyn), cuts["dyn_cuts"]), _up(float(dep), cuts["depth_cuts"]))
        pts = [0, 2, 4, 5, 6][int(np.clip(idx, 0, 4))]
        label = {0: "黏膜/黏膜下倾向", 2: "固有肌层倾向", 4: "浆膜下倾向", 5: "浆膜突破倾向", 6: "邻近侵犯倾向"}[pts]
        out["wall"] = (pts, f"胃壁代理→设计{pts}分（{label}；ser={float(ser):.2f}, dyn={float(dyn):.2f}, depth={float(dep):.2f}）")

    protr = row.get("growth_outward_protrusion_ratio__max")
    if _finite(protr) and _finite(dyn):
        g = int(np.clip(round((_up(float(protr), cuts["protr_cuts"]) + _up(float(dyn), cuts["dyn_cuts"])) / 2), 0, 3))
        # boost if serosa high
        if _finite(ser) and float(ser) > cuts["serosa_cuts"][2]:
            g = min(3, g + 1)
        out["growth"] = (g, f"生长综合 g={g}（protr={float(protr):.3g}, dyn={float(dyn):.2f}）")

    return out


def score_row(row: pd.Series, cuts: dict) -> dict:
    items = []
    included_max = 0
    total = 0

    # length / thickness — design Word absolute points
    if _finite(row.get("tumor_length_cm")):
        g, d = grade_length_cm(float(row["tumor_length_cm"]))
        items.append({"id": "length", "points": g, "max": 3, "detail": d, "status": "included"})
        total += g
        included_max += 3
    else:
        items.append({"id": "length", "points": None, "max": 3, "detail": "长径缺失", "status": "pending"})

    if _finite(row.get("tumor_thickness_cm")):
        g, d = grade_thickness_cm(float(row["tumor_thickness_cm"]))
        items.append({"id": "thickness", "points": g, "max": 3, "detail": d, "status": "included"})
        total += g
        included_max += 3
    else:
        items.append({"id": "thickness", "points": None, "max": 3, "detail": "厚径缺失", "status": "pending"})

    img = grade_imaging(row, cuts)
    for dim, mx in [("morphology", 2), ("margin", 3), ("wall", 6), ("growth", 3)]:
        hit = img[dim]
        if hit is None:
            items.append({"id": dim, "points": None, "max": mx, "detail": f"{dim} 特征缺失", "status": "pending"})
        else:
            g, d = hit
            items.append({"id": dim, "points": int(g), "max": mx, "detail": d, "status": "included"})
            total += int(g)
            included_max += mx

    mg, md = grade_marker(row.get("cea_binary"), row.get("cea_value"))
    if mg is not None:
        items.append({"id": "marker", "points": mg, "max": 2, "detail": md + "（多项升高本包不可评）", "status": "included"})
        total += mg
        included_max += 2
    else:
        items.append({"id": "marker", "points": None, "max": 2, "detail": md, "status": "pending"})

    # location not in pack
    items.append({"id": "location", "points": None, "max": 1, "detail": "部位字段不在 feature pack", "status": "pending"})

    i_norm = float(total / included_max) if included_max > 0 else float("nan")
    n_incl = sum(1 for it in items if it["status"] == "included")
    imaging_complete = all(img[k] is not None for k in ("morphology", "margin", "wall", "growth"))

    # Lean total: exclude wall 0/2/4/5/6 until layer proxy is externally calibrated.
    lean_ids = {"length", "thickness", "morphology", "margin", "growth", "marker"}
    lean_total = 0
    lean_max = 0
    for it in items:
        if it["id"] in lean_ids and it["status"] == "included" and it["points"] is not None:
            lean_total += int(it["points"])
            lean_max += int(it["max"])
    lean_I = float(lean_total / lean_max) if lean_max > 0 else float("nan")

    return {
        "scheme": SCHEME,
        "total": int(total),
        "max_included": int(included_max),
        "I": i_norm,
        "lean_total": int(lean_total),
        "lean_max": int(lean_max),
        "lean_I": lean_I,
        "n_dimensions_included": n_incl,
        "imaging_complete": imaging_complete,
        "items": items,
    }


def map_score_to_stage(score: float, cuts: list[float]) -> int:
    """cuts length 3: score<=c0→0, <=c1→1, <=c2→2, else 3."""
    for i, c in enumerate(cuts):
        if score <= c:
            return i
    return 3


def fit_stage_cuts(scores: np.ndarray, y: np.ndarray) -> list[int]:
    """Brute-force absolute-score cuts maximizing train QWK."""
    smax = int(np.nanmax(scores))
    best = ([-1.0], [0, 1, 3])
    for a in range(0, max(1, smax - 2)):
        for b in range(a + 1, smax - 1):
            for c in range(b + 1, smax):
                pred = np.array([map_score_to_stage(s, [a, b, c]) for s in scores])
                qwk = cohen_kappa_score(y, pred, weights="quadratic")
                if qwk > best[0][0]:
                    best = ([qwk], [a, b, c])
    return best[1]


def fit_I_cuts(I: np.ndarray, y: np.ndarray) -> list[float]:
    """Fit normalized I cuts (like product bands) on train."""
    grid = np.linspace(0.15, 0.90, 31)
    best = (-1.0, [0.34, 0.50, 0.64])
    for a in grid:
        for b in grid:
            if b <= a + 0.04:
                continue
            for c in grid:
                if c <= b + 0.04:
                    continue
                pred = np.array([map_score_to_stage(v, [a, b, c]) for v in I])
                qwk = cohen_kappa_score(y, pred, weights="quadratic")
                if qwk > best[0]:
                    best = (qwk, [float(a), float(b), float(c)])
    return best[1]


def evaluate(df: pd.DataFrame, pred_col: str, score_col: str) -> pd.DataFrame:
    rows = []
    for sp, sub in df.groupby("eval_split"):
        y = sub["label"].astype(int).to_numpy()
        pred = sub[pred_col].astype(int).to_numpy()
        score = sub[score_col].astype(float).to_numpy()
        y3 = (y >= 2).astype(int)
        rows.append(
            {
                "split": sp,
                "n": int(len(sub)),
                "acc_4class": float(accuracy_score(y, pred)),
                "qwk_4class": float(cohen_kappa_score(y, pred, weights="quadratic")),
                "mae": float(np.mean(np.abs(y - pred))),
                "spearman_score_vs_T": float(spearmanr(score, y).correlation),
                "auc_T3plus_score": float(roc_auc_score(y3, score)) if y3.min() != y3.max() else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.pack)
    # imaging complete-case for fitting imaging cuts
    img_cols = [
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
    train = df[df["eval_split"] == "train"].copy()
    train_img = train.dropna(subset=img_cols)
    cuts = fit_imaging_cuts(train_img)

    scored_rows = []
    item_rows = []
    for _, row in df.iterrows():
        sc = score_row(row, cuts)
        scored_rows.append(
            {
                "patient_id": row["patient_id"],
                "label": int(row["label"]),
                "eval_split": row["eval_split"],
                "tumor_length_cm": row.get("tumor_length_cm"),
                "tumor_thickness_cm": row.get("tumor_thickness_cm"),
                "total": sc["total"],
                "max_included": sc["max_included"],
                "I": sc["I"],
                "lean_total": sc["lean_total"],
                "lean_max": sc["lean_max"],
                "lean_I": sc["lean_I"],
                "n_dimensions_included": sc["n_dimensions_included"],
                "imaging_complete": bool(sc["imaging_complete"]),
                **{f"pts_{it['id']}": it["points"] for it in sc["items"]},
            }
        )
        for it in sc["items"]:
            item_rows.append(
                {
                    "patient_id": row["patient_id"],
                    "eval_split": row["eval_split"],
                    "label": int(row["label"]),
                    **it,
                }
            )

    scores = pd.DataFrame(scored_rows)

    # Fit stage mapping on train
    train_scores = scores[scores["eval_split"] == "train"]
    fit_mask = train_scores["imaging_complete"]
    fit_df = train_scores[fit_mask] if fit_mask.sum() >= 200 else train_scores
    abs_cuts = fit_stage_cuts(fit_df["total"].to_numpy(), fit_df["label"].to_numpy())
    i_cuts = fit_I_cuts(fit_df["I"].to_numpy(), fit_df["label"].to_numpy())
    lean_cuts = fit_stage_cuts(fit_df["lean_total"].to_numpy(), fit_df["label"].to_numpy())
    lean_I_cuts = fit_I_cuts(fit_df["lean_I"].to_numpy(), fit_df["label"].to_numpy())

    # size-only baseline (design bins) — always available
    scores["size_only"] = scores["pts_length"].fillna(0).astype(int) + scores["pts_thickness"].fillna(0).astype(int)
    train_scores = scores[scores["eval_split"] == "train"]
    size_cuts = fit_stage_cuts(
        train_scores["size_only"].to_numpy(), train_scores["label"].to_numpy()
    )

    scores["pred_abs"] = scores["total"].map(lambda s: map_score_to_stage(s, abs_cuts))
    scores["pred_I"] = scores["I"].map(lambda v: map_score_to_stage(v, i_cuts) if np.isfinite(v) else -1)
    scores["pred_lean"] = scores["lean_total"].map(lambda s: map_score_to_stage(s, lean_cuts))
    scores["pred_lean_I"] = scores["lean_I"].map(lambda v: map_score_to_stage(v, lean_I_cuts) if np.isfinite(v) else -1)
    scores["pred_size_only"] = scores["size_only"].map(lambda s: map_score_to_stage(s, size_cuts))
    # Recommended hybrid: imaging-complete → lean_I（不含未校准胃壁满分）；else size-only
    scores["pred_hybrid"] = np.where(
        scores["imaging_complete"],
        scores["pred_lean_I"],
        scores["pred_size_only"],
    )
    scores["cT_abs"] = scores["pred_abs"].map(lambda k: STAGE[k] if 0 <= k < 4 else "cTx")
    scores["cT_I"] = scores["pred_I"].map(lambda k: STAGE[k] if 0 <= k < 4 else "cTx")
    scores["cT_lean"] = scores["pred_lean"].map(lambda k: STAGE[k] if 0 <= k < 4 else "cTx")
    scores["cT_hybrid"] = scores["pred_hybrid"].map(lambda k: STAGE[int(k)] if 0 <= int(k) < 4 else "cTx")
    scores["score_for_hybrid"] = np.where(
        scores["imaging_complete"], scores["lean_I"], scores["size_only"] / 6.0
    )

    m_abs = evaluate(scores[scores["pred_abs"] >= 0], "pred_abs", "total")
    m_I = evaluate(scores[scores["pred_I"] >= 0], "pred_I", "I")
    m_lean = evaluate(scores, "pred_lean", "lean_total")
    m_lean_I = evaluate(scores[scores["pred_lean_I"] >= 0], "pred_lean_I", "lean_I")
    m_size = evaluate(scores, "pred_size_only", "size_only")
    m_hyb = evaluate(scores, "pred_hybrid", "score_for_hybrid")
    m_abs["scheme"] = "v2_full_absolute_with_wall"
    m_I["scheme"] = "v2_full_normalized_I_with_wall"
    m_lean["scheme"] = "v2_lean_absolute_no_wall"
    m_lean_I["scheme"] = "v2_lean_normalized_I_no_wall"
    m_size["scheme"] = "size_only_design_bins"
    m_hyb["scheme"] = "v2_hybrid_leanI_or_size"
    metrics = pd.concat([m_abs, m_I, m_lean, m_lean_I, m_size, m_hyb], ignore_index=True)

    # confusion on external for hybrid (recommended) scheme
    ext = scores[scores["eval_split"] == "test_external"]
    cm = confusion_matrix(ext["label"], ext["pred_hybrid"], labels=[0, 1, 2, 3])
    cm_df = pd.DataFrame(cm, index=[f"true_{s}" for s in STAGE], columns=[f"pred_{s}" for s in STAGE])

    # dimension-level association on train
    dim_stats = []
    for dim in ["pts_length", "pts_thickness", "pts_morphology", "pts_margin", "pts_wall", "pts_growth", "pts_marker"]:
        sub = train_scores.dropna(subset=[dim])
        if len(sub) < 30:
            continue
        r, p = spearmanr(sub[dim], sub["label"])
        dim_stats.append({"dimension": dim, "n_train": len(sub), "spearman_rho": r, "p": p, "mean_points": sub[dim].mean()})

    # write artifacts
    scores.to_csv(args.out / "patient_scores.csv", index=False)
    pd.DataFrame(item_rows).to_csv(args.out / "score_items_long.csv", index=False)
    metrics.to_csv(args.out / "metrics_by_split.csv", index=False)
    cm_df.to_csv(args.out / "confusion_external_abs.csv")
    pd.DataFrame(dim_stats).to_csv(args.out / "dimension_train_association.csv", index=False)

    meta = {
        "scheme": SCHEME,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pack": str(args.pack),
        "design_doc": "胃癌超声T分期GC-US_T评分体系设计方案.docx",
        "dimensions": [asdict(d) for d in DIMENSIONS],
        "imaging_cuts": cuts,
        "stage_cuts_absolute": abs_cuts,
        "stage_cuts_I": i_cuts,
        "lean_cuts_absolute": lean_cuts,
        "lean_cuts_I": lean_I_cuts,
        "size_only_cuts": size_cuts,
        "fit_n_train": int(len(fit_df)),
        "recommended_prediction": "pred_hybrid / cT_hybrid",
        "notes": [
            "Wall points are computed for the card but excluded from lean/hybrid staging until externally calibrated.",
            "Location omitted (not in pack). Marker uses CEA only (no CA19-9 → max practical 1).",
            "Hybrid: imaging-complete → lean I (size+morph+margin+growth+CEA); incomplete → size-only.",
            "Product human_assist rubric cutpoints are NOT modified.",
        ],
    }
    (args.out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    # SUMMARY.md
    lines = [
        "# GC-US T-score v2 · feature-pack 实现（对齐设计方案）",
        "",
        f"- Generated: `{meta['generated']}`",
        f"- Scheme: `{SCHEME}`",
        "- Design: 《胃癌超声T分期GC-US_T评分体系设计方案》绝对积分（长径/厚径/形态/边界/胃壁/生长/标志物）",
        "- Imaging bins: train-only z-risk quantiles from explored feature pack",
        f"- Absolute stage cuts (train QWK): score≤{abs_cuts[0]}→T1, ≤{abs_cuts[1]}→T2, ≤{abs_cuts[2]}→T3, else T4+",
        f"- Normalized I cuts: I≤{i_cuts[0]:.2f}→T1, ≤{i_cuts[1]:.2f}→T2, ≤{i_cuts[2]:.2f}→T3, else T4+",
        f"- Size-only cuts: score≤{size_cuts[0]}→T1, ≤{size_cuts[1]}→T2, ≤{size_cuts[2]}→T3, else T4+",
        "- **Recommended**: `cT_hybrid` = imaging-complete ? lean_I (no wall) : size-only",
        "",
        "## Dimension → feature mapping",
        "",
        "| 设计维度 | 分值 | feature-pack 字段 | 是否进 lean/hybrid 分期 |",
        "|---|---:|---|---|",
        "| 长径 | 0–3 | `tumor_length_cm`（设计 mm 档） | 是 |",
        "| 厚径 | 0–3 | `tumor_thickness_cm`（设计 mm 档） | 是 |",
        "| 形态 | 0–2 | peak / circularity / solidity | 是 |",
        "| 边界 | 0–3 | spic + NRL roughness | 是 |",
        "| 胃壁 | 0/2/4/5/6 | serosa / dyn / depth | 卡片展示；分期暂不进 |",
        "| 生长 | 0–3 | protrusion + dyn | 是 |",
        "| 标志物 | 0–2 | CEA only | 是 |",
        "| 部位 | — | pack 无 | 否 |",
        "",
        "## Metrics by split",
        "",
        metrics.to_csv(index=False),
        "",
        "## Train dimension–stage Spearman",
        "",
        pd.DataFrame(dim_stats).to_csv(index=False),
        "",
        "## Readout",
        "",
        "1. 设计方案 Word 的征象积分已接到探索特征包，可批量出分。",
        "2. 胃壁设计档 0/2/4/5/6 会写在分项卡上，但 **lean/hybrid 分期暂不计入**（外部代理未校准）。",
        "3. 缺影像特征时回退设计长径+厚径分档。",
        "4. 产品页 `ccus_t_rubric_v1.4_us` 切点未改；本目录为研究评分线。",
        "5. 下一步：胃壁代理外校、CA19-9/部位、Nomogram、与人机页打通。",
        "",
    ]
    (args.out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({
        "out": str(args.out),
        "n": len(scores),
        "abs_cuts": abs_cuts,
        "I_cuts": i_cuts,
        "metrics_external_hybrid": metrics[(metrics.scheme == "v2_hybrid_leanI_or_size") & (metrics.split == "test_external")].to_dict("records"),
        "metrics_external_lean_I": metrics[(metrics.scheme == "v2_lean_normalized_I_no_wall") & (metrics.split == "test_external")].to_dict("records"),
        "metrics_external_size": metrics[(metrics.scheme == "size_only_design_bins") & (metrics.split == "test_external")].to_dict("records"),
        "imaging_complete_rate": scores.groupby("eval_split")["imaging_complete"].mean().to_dict(),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
