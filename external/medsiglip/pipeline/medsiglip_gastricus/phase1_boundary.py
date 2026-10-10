"""Phase 1 boundary audit: McNemar, bootstrap, per-center, hierarchical cuts, error patterns.

Reads existing patient-level prediction CSVs. The written report has no patient IDs.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from .constants import (
    CLASS_NAMES,
    LARGECLF_REPORT_DIR,
    PHASE1_REPORT_DIR,
    PHASE1_SEED_REPORT_DIR,
    PLAN_COMPLETE_REPORT_DIR,
    ROOT,
)
from .metrics import confusion, mcnemar_exact, md_confusion, score_arrays
from .train import _jsonable, train

SPLITS = ("test_prospective", "test_external")
N_BOOT = 2000
BOOT_SEED = 20260821

HIERARCHY = (
    ("t1_vs_t2plus", 1, "T1 vs T2+", "是否超过黏膜/黏膜下"),
    ("early_vs_advanced", 2, "T1-T2 vs T3+", "是否穿过固有肌层"),
    ("not_t4_vs_t4", 3, "T1-T3 vs T4+", "是否浆膜/邻器官侵犯"),
)

PARENT_REPORTS = ROOT.parent / "pipeline/experiments/reports"


def _run_catalog() -> list[dict[str, object]]:
    rows = [
        {
            "name": "default",
            "label": "默认 4.1 x 5.3 x 6.1",
            "path": PLAN_COMPLETE_REPORT_DIR / "mlp_concat_gated",
        },
        {
            "name": "best",
            "label": "网格最好 5.1 x 6.2",
            "path": PLAN_COMPLETE_REPORT_DIR / "tabpfn_concat_mean",
        },
        {
            "name": "default_retrain",
            "label": "默认同结构再训",
            "path": LARGECLF_REPORT_DIR / "mlp_xlarge_gated",
        },
        {
            "name": "best_retrain",
            "label": "5.1 x 6.2 再训",
            "path": LARGECLF_REPORT_DIR / "tabpfn_xlarge_mean",
        },
        {
            "name": "opt_default",
            "label": "08-21 默认头",
            "path": PARENT_REPORTS / "medsiglip_gastricus_opt_xlarge_20260821/mlp_concat_gated",
        },
        {
            "name": "clinical_only",
            "label": "临床-only TabPFN",
            "path": PARENT_REPORTS / "medsiglip_gastricus_plan_literal_20260822/tabpfn_clinical_only",
        },
        {
            "name": "preop",
            "label": "术前临床（去 Lauren/分化）",
            "path": PARENT_REPORTS / "medsiglip_gastricus_preop_20260822/mlp_concat_gated",
        },
        {
            "name": "time192",
            "label": "TIME-192",
            "path": PARENT_REPORTS / "medsiglip_gastricus_plan_literal_20260822/xlarge_concat_gated_time192",
        },
        {
            "name": "expand15",
            "label": "ROI 15% 默认头",
            "path": PARENT_REPORTS / "medsiglip_gastricus_expand15_20260822/mlp_concat_gated",
        },
    ]
    seed_root = PHASE1_SEED_REPORT_DIR
    if seed_root.is_dir():
        for child in sorted(seed_root.iterdir()):
            if child.is_dir() and (child / "test_prospective_predictions.csv").is_file():
                rows.append({"name": child.name, "label": child.name, "path": child})
    return [row for row in rows if (Path(row["path"]) / "test_prospective_predictions.csv").is_file()]


def _load_pred(run_dir: Path, split: str) -> pd.DataFrame:
    path = run_dir / f"{split}_predictions.csv"
    table = pd.read_csv(path)
    table["patient_id"] = table["patient_id"].astype(str)
    table["y"] = table["y"].astype(int)
    table["pred"] = table["pred"].astype(int)
    table["center"] = table["center"].astype(str)
    return table[["patient_id", "center", "y", "pred"]].sort_values("patient_id").reset_index(drop=True)


def _binary_scores(y: np.ndarray, pred: np.ndarray, thresh: int) -> dict[str, float]:
    y_bin = (np.asarray(y, dtype=int) >= thresh).astype(int)
    pred_bin = (np.asarray(pred, dtype=int) >= thresh).astype(int)
    n = int(len(y_bin))
    pos = y_bin == 1
    neg = y_bin == 0
    rec_pos = float(np.mean(pred_bin[pos] == 1)) if pos.any() else 0.0
    rec_neg = float(np.mean(pred_bin[neg] == 0)) if neg.any() else 0.0
    majority = float(max(np.mean(y_bin), 1.0 - np.mean(y_bin))) if n else 0.0
    return {
        "n": n,
        "n_pos": int(pos.sum()),
        "n_neg": int(neg.sum()),
        "acc": float(np.mean(y_bin == pred_bin)) if n else 0.0,
        "recall_pos": rec_pos,
        "recall_neg": rec_neg,
        "balanced_acc": float(0.5 * (rec_pos + rec_neg)),
        "majority": majority,
        "prev_true": float(np.mean(y_bin)) if n else 0.0,
    }


def _error_pattern(y: np.ndarray, pred: np.ndarray) -> dict[str, object]:
    y = np.asarray(y, dtype=int)
    pred = np.asarray(pred, dtype=int)
    out: dict[str, object] = {"confusion": confusion(y, pred)}
    for cls, name in enumerate(CLASS_NAMES):
        mask = y == cls
        dest = Counter(int(v) for v in pred[mask].tolist())
        out[f"true_{name}_to"] = {CLASS_NAMES[k]: int(dest.get(k, 0)) for k in range(4)}
        out[f"true_{name}_n"] = int(mask.sum())
        out[f"true_{name}_off2"] = int(np.sum(mask & (np.abs(y - pred) >= 2)))
    out["t3_to_t4"] = int(np.sum((y == 2) & (pred == 3)))
    out["t4_to_t3"] = int(np.sum((y == 3) & (pred == 2)))
    out["t2_to_t1"] = int(np.sum((y == 1) & (pred == 0)))
    out["t2_to_t3plus"] = int(np.sum((y == 1) & (pred >= 2)))
    return out


def _bootstrap(y: np.ndarray, pred: np.ndarray, n_boot: int = N_BOOT, seed: int = BOOT_SEED) -> dict[str, object]:
    y = np.asarray(y, dtype=int)
    pred = np.asarray(pred, dtype=int)
    n = int(len(y))
    rng = np.random.default_rng(seed)
    acc = np.empty(n_boot, dtype=float)
    t2 = np.empty(n_boot, dtype=float)
    t3 = np.empty(n_boot, dtype=float)
    early = np.empty(n_boot, dtype=float)
    t4 = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        yi, pi = y[idx], pred[idx]
        acc[i] = float(np.mean(yi == pi))
        m2 = yi == 1
        t2[i] = float(np.mean(pi[m2] == 1)) if m2.any() else 0.0
        m3 = yi == 2
        t3[i] = float(np.mean(pi[m3] == 2)) if m3.any() else 0.0
        early[i] = float(np.mean((yi >= 2) == (pi >= 2)))
        t4[i] = float(np.mean((yi >= 3) == (pi >= 3)))

    def _ci(arr: np.ndarray) -> dict[str, float]:
        return {
            "mean": float(np.mean(arr)),
            "lo": float(np.percentile(arr, 2.5)),
            "hi": float(np.percentile(arr, 97.5)),
        }

    return {
        "n_boot": n_boot,
        "acc": _ci(acc),
        "recall_T2": _ci(t2),
        "recall_T3": _ci(t3),
        "early_vs_advanced": _ci(early),
        "not_t4_vs_t4": _ci(t4),
    }


def _per_center(table: pd.DataFrame) -> list[dict[str, object]]:
    rows = []
    for center, part in table.groupby("center", sort=True):
        y = part["y"].to_numpy()
        pred = part["pred"].to_numpy()
        row = score_arrays(y, pred)
        row["center"] = str(center)
        row["hierarchy"] = {key: _binary_scores(y, pred, thresh) for key, thresh, _, _ in HIERARCHY}
        row["error"] = _error_pattern(y, pred)
        rows.append(row)
    return rows


def _align(a: pd.DataFrame, b: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    merged = a.merge(b, on="patient_id", suffixes=("_a", "_b"))
    if len(merged) == 0:
        return None
    if not np.array_equal(merged["y_a"].to_numpy(), merged["y_b"].to_numpy()):
        raise ValueError("aligned patient labels disagree")
    return (
        merged["y_a"].to_numpy(dtype=int),
        merged["pred_a"].to_numpy(dtype=int),
        merged["pred_b"].to_numpy(dtype=int),
    )


def _score_run(run_dir: Path) -> dict[str, object]:
    out: dict[str, object] = {}
    for split in SPLITS:
        table = _load_pred(run_dir, split)
        y = table["y"].to_numpy()
        pred = table["pred"].to_numpy()
        block = score_arrays(y, pred)
        block["hierarchy"] = {key: _binary_scores(y, pred, thresh) for key, thresh, _, _ in HIERARCHY}
        block["error"] = _error_pattern(y, pred)
        block["bootstrap"] = _bootstrap(y, pred)
        block["per_center"] = _per_center(table)
        block["confusion"] = confusion(y, pred)
        out[split] = block
    return out


def _pairs() -> list[tuple[str, str]]:
    return [
        ("default", "best"),
        ("default", "default_retrain"),
        ("best", "best_retrain"),
        ("default", "clinical_only"),
        ("default", "preop"),
        ("default", "time192"),
        ("default", "expand15"),
        ("opt_default", "default"),
    ]


def _fmt(x: float, digits: int = 4) -> str:
    return f"{x:.{digits}f}"


def _write_report(catalog: list[dict[str, object]], scores: dict[str, dict], paired: dict[str, dict]) -> str:
    lines = [
        "# Phase 1 问题边界（2026-08-25）",
        "",
        "用已落盘的患者级预测 CSV：McNemar、bootstrap、分中心、层级切点、T2/T3 去向。",
        "报告不含患者标识。0.75 四类门槛不改。层级数字只作并列，不升格 CLI。",
        "",
        f"bootstrap：患者有放回 {N_BOOT} 次，种子 {BOOT_SEED}，区间是 2.5 / 97.5 分位。",
        "",
        "## 模型",
        "",
        "| 简称 | 设置 | 前瞻精确 | 外部精确 | 前瞻 T2 / T3 | 外部 T2 / T3 |",
        "|------|------|--------:|--------:|-------------:|-------------:|",
    ]
    for row in catalog:
        name = str(row["name"])
        sc = scores[name]
        p, e = sc["test_prospective"], sc["test_external"]
        lines.append(
            f"| {name} | {row['label']} | {_fmt(p['acc'])} | {_fmt(e['acc'])} | "
            f"{_fmt(p['recall_T2'], 3)} / {_fmt(p['recall_T3'], 3)} | "
            f"{_fmt(e['recall_T2'], 3)} / {_fmt(e['recall_T3'], 3)} |"
        )
    lines += ["", "## 四类精确 ACC bootstrap", ""]
    lines += [
        "| 模型 | 前瞻 ACC [95%] | 外部 ACC [95%] | 前瞻 T2 [95%] | 前瞻 T3 [95%] |",
        "|------|----------------:|----------------:|--------------:|--------------:|",
    ]
    for name in ("default", "best", "clinical_only", "preop", "time192"):
        if name not in scores:
            continue
        p, e = scores[name]["test_prospective"], scores[name]["test_external"]
        lines.append(
            f"| {name} | {_fmt(p['bootstrap']['acc']['mean'])} "
            f"[{_fmt(p['bootstrap']['acc']['lo'])}, {_fmt(p['bootstrap']['acc']['hi'])}] | "
            f"{_fmt(e['bootstrap']['acc']['mean'])} "
            f"[{_fmt(e['bootstrap']['acc']['lo'])}, {_fmt(e['bootstrap']['acc']['hi'])}] | "
            f"{_fmt(p['bootstrap']['recall_T2']['mean'], 3)} "
            f"[{_fmt(p['bootstrap']['recall_T2']['lo'], 3)}, {_fmt(p['bootstrap']['recall_T2']['hi'], 3)}] | "
            f"{_fmt(p['bootstrap']['recall_T3']['mean'], 3)} "
            f"[{_fmt(p['bootstrap']['recall_T3']['lo'], 3)}, {_fmt(p['bootstrap']['recall_T3']['hi'], 3)}] |"
        )

    lines += ["", "## McNemar（配对精确对错）", ""]
    lines += [
        "| 对照 | split | acc A | acc B | A对B错 | A错B对 | p |",
        "|------|-------|------:|------:|------:|------:|--:|",
    ]
    for key, block in paired.items():
        a_name, b_name, split = key.split("|")
        lines.append(
            f"| {a_name} vs {b_name} | {split} | {_fmt(block['acc_a'])} | {_fmt(block['acc_b'])} | "
            f"{int(block['n_a_right_b_wrong'])} | {int(block['n_a_wrong_b_right'])} | {_fmt(block['p_exact'], 4)} |"
        )

    lines += ["", "## 层级切点（由四类预测塌缩，不是新训的二分类头）", ""]
    for key, _thresh, title, why in HIERARCHY:
        lines += [f"### {title}", "", why, ""]
        lines += [
            "| 模型 | 前瞻 ACC | 前瞻 bal | 前瞻 多数类 | 外部 ACC | 外部 bal | 外部 多数类 |",
            "|------|--------:|--------:|-----------:|--------:|--------:|-----------:|",
        ]
        for name in ("default", "best", "clinical_only", "preop"):
            if name not in scores:
                continue
            p = scores[name]["test_prospective"]["hierarchy"][key]
            e = scores[name]["test_external"]["hierarchy"][key]
            lines.append(
                f"| {name} | {_fmt(p['acc'])} | {_fmt(p['balanced_acc'])} | {_fmt(p['majority'])} | "
                f"{_fmt(e['acc'])} | {_fmt(e['balanced_acc'])} | {_fmt(e['majority'])} |"
            )
        lines.append("")

    lines += ["## 外部按中心（默认 vs 最好）", ""]
    if "default" in scores and "best" in scores:
        lines += [
            "| 中心 | n | 默认 ACC | 最好 ACC | 默认 T2 召回 | 最好 T2 召回 | 默认 T3 召回 | 最好 T3 召回 |",
            "|------|--:|--------:|--------:|------------:|------------:|------------:|------------:|",
        ]
        default_c = {r["center"]: r for r in scores["default"]["test_external"]["per_center"]}
        best_c = {r["center"]: r for r in scores["best"]["test_external"]["per_center"]}
        for center in sorted(set(default_c) | set(best_c)):
            d = default_c.get(center, {})
            b = best_c.get(center, {})
            n = int(d.get("n") or b.get("n") or 0)
            lines.append(
                f"| {center} | {n} | {_fmt(float(d.get('acc', 0)))} | {_fmt(float(b.get('acc', 0)))} | "
                f"{_fmt(float(d.get('recall_T2', 0)), 3)} | {_fmt(float(b.get('recall_T2', 0)), 3)} | "
                f"{_fmt(float(d.get('recall_T3', 0)), 3)} | {_fmt(float(b.get('recall_T3', 0)), 3)} |"
            )

    lines += ["", "## T2 / T3 去向（人数，不含 ID）", ""]
    for name in ("default", "best"):
        if name not in scores:
            continue
        lines.append(f"### {name}")
        lines.append("")
        for split, title in (("test_prospective", "前瞻"), ("test_external", "外部")):
            err = scores[name][split]["error"]
            lines.append(f"**{title}**")
            lines.append("")
            lines.extend(md_confusion(err["confusion"]))
            lines.append("")
            t2 = err["true_T2_to"]
            t3 = err["true_T3_to"]
            lines.append(
                f"T2 {err['true_T2_n']} 人：→T1 {t2['T1']}，→T2 {t2['T2']}，→T3 {t2['T3']}，→T4+ {t2['T4+']}；"
                f"其中跳两级 {err['true_T2_off2']}。"
            )
            lines.append(
                f"T3 {err['true_T3_n']} 人：→T1 {t3['T1']}，→T2 {t3['T2']}，→T3 {t3['T3']}，→T4+ {t3['T4+']}；"
                f"T3→T4+ {err['t3_to_t4']}，T4+→T3 {err['t4_to_t3']}。"
            )
            lines.append("")

    seed_mlp = [name for name in scores if name.startswith("mlp_concat_gated_s")]
    seed_tab = [name for name in scores if name.startswith("tabpfn_concat_mean_s")]
    if seed_mlp or seed_tab:
        lines += ["## 多种子（额外种子，不覆盖 20260821 网格）", ""]
        lines += [
            "TabPFN 临床 4 类概率缓存按文件存在即复用，多种子只改融合头初始化。",
            "",
            "| 族 | 成员 | 前瞻 mean [min, max] | 外部 mean [min, max] |",
            "|----|------|---------------------:|---------------------:|",
        ]

        def _span(names: list[str], split: str) -> str:
            vals = [float(scores[n][split]["acc"]) for n in names]
            return f"{sum(vals) / len(vals):.4f} [{min(vals):.4f}, {max(vals):.4f}]"

        if "default" in scores and seed_mlp:
            mlp_all = ["default", *seed_mlp]
            lines.append(
                f"| 默认 MLP | 原格子 + {len(seed_mlp)} 种子 | {_span(mlp_all, 'test_prospective')} | {_span(mlp_all, 'test_external')} |"
            )
        if "best" in scores and seed_tab:
            tab_all = ["best", *seed_tab]
            lines.append(
                f"| 5.1 x 6.2 | 原格子 + {len(seed_tab)} 种子 | {_span(tab_all, 'test_prospective')} | {_span(tab_all, 'test_external')} |"
            )
        lines += ["", "| run | 前瞻 | 外部 | 前瞻 T2 / T3 |", "|-----|-----:|-----:|-------------:|"]
        for name in (*seed_mlp, *seed_tab):
            p, e = scores[name]["test_prospective"], scores[name]["test_external"]
            lines.append(
                f"| {name} | {_fmt(p['acc'])} | {_fmt(e['acc'])} | {_fmt(p['recall_T2'], 3)} / {_fmt(p['recall_T3'], 3)} |"
            )
        lines.append("")

    lines += [
        "## 能说 / 不能说",
        "",
        "- 能说：默认和网格最好的差，可以做配对检验；外部 ACC 会被大中心拉着走；层级切点比四类好做，但仍不是 0.75 四类。",
        "- 不能说：已经到 0.75。5.1 x 6.2 可以改 CLI 默认。层级 ACC 高就是分期做成了。0.6424 / 0.5856 是多种子稳定上限。",
        "",
    ]
    return "\n".join(lines) + "\n"


def run_phase1_audit(dest: Path | None = None) -> dict[str, object]:
    dest = dest or PHASE1_REPORT_DIR
    dest.mkdir(parents=True, exist_ok=True)
    catalog = _run_catalog()
    tables: dict[str, dict[str, pd.DataFrame]] = {}
    scores: dict[str, dict] = {}
    for row in catalog:
        name = str(row["name"])
        path = Path(row["path"])
        tables[name] = {split: _load_pred(path, split) for split in SPLITS}
        scores[name] = _score_run(path)

    paired: dict[str, dict] = {}
    names = {row["name"] for row in catalog}
    for a_name, b_name in _pairs():
        if a_name not in names or b_name not in names:
            continue
        for split in SPLITS:
            aligned = _align(tables[a_name][split], tables[b_name][split])
            if aligned is None:
                continue
            y, pred_a, pred_b = aligned
            paired[f"{a_name}|{b_name}|{split}"] = mcnemar_exact(y, pred_a, pred_b)

    payload = {
        "catalog": [{"name": r["name"], "label": r["label"], "path": str(r["path"])} for r in catalog],
        "scores": scores,
        "mcnemar": paired,
        "n_boot": N_BOOT,
    }
    (dest / "phase1.json").write_text(json.dumps(_jsonable(payload), indent=2), encoding="utf-8")
    text = _write_report(catalog, scores, paired)
    (dest / "COMPARE.md").write_text(text, encoding="utf-8")
    (dest / "SUMMARY.md").write_text(text, encoding="utf-8")
    return {
        "report": str(dest),
        "n_models": len(catalog),
        "n_mcnemar": len(paired),
        "default_vs_best": {
            split: paired.get(f"default|best|{split}", {})
            for split in SPLITS
        },
    }


def train_phase1_seeds(
    device: str = "cuda:0",
    tabpfn_device: str = "cpu",
    seeds: tuple[int, ...] = (20260825, 20260826, 20260827),
    epochs: int = 80,
    batch_size: int = 16,
    lr: float = 2e-4,
) -> dict[str, object]:
    """Retrain default and best cells on extra seeds. Does not overwrite the 20260821 grid."""
    dest_root = PHASE1_SEED_REPORT_DIR
    dest_root.mkdir(parents=True, exist_ok=True)
    jobs = (
        {"tag": "mlp_concat_gated", "head": "mlp", "fusion": "concat", "pool": "gated"},
        {"tag": "tabpfn_concat_mean", "head": "tabpfn", "fusion": "concat", "pool": "mean_views"},
    )
    summaries = []
    for seed in seeds:
        for job in jobs:
            name = f"{job['tag']}_s{seed}"
            print(f"phase1-seed {name}", flush=True)
            result = train(
                device=device,
                epochs=epochs,
                batch_size=batch_size,
                lr=lr,
                head=str(job["head"]),
                tabpfn_device=tabpfn_device,
                fusion=str(job["fusion"]),
                pool=str(job["pool"]),
                size="xlarge",
                lock="acc",
                ordinal_weight=0.5,
                seed=int(seed),
                report_dir=dest_root / name,
                run_name=name,
            )
            ev = result["eval"]
            summaries.append(
                {
                    "name": name,
                    "seed": int(seed),
                    "prospective": float(ev["test_prospective"]["acc"]),
                    "external": float(ev["test_external"]["acc"]),
                    "t2_prospective": float(ev["test_prospective"]["recall_T2"]),
                    "t3_prospective": float(ev["test_prospective"]["recall_T3"]),
                }
            )
    audit = run_phase1_audit()
    (dest_root / "SEED_COMPARE.md").write_text(
        "# Phase 1 extra seeds\n\n"
        + "| run | seed | 前瞻 | 外部 | 前瞻 T2 | 前瞻 T3 |\n"
        + "|-----|-----:|-----:|-----:|--------:|--------:|\n"
        + "".join(
            f"| {r['name']} | {r['seed']} | {r['prospective']:.4f} | {r['external']:.4f} | "
            f"{r['t2_prospective']:.3f} | {r['t3_prospective']:.3f} |\n"
            for r in summaries
        ),
        encoding="utf-8",
    )
    return {"seeds": summaries, "audit": audit}
