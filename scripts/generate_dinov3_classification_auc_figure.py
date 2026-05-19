#!/usr/bin/env python3
"""Summarize DINOv3 classification / scalar-pipeline AUC and plot comparison figures.

Outputs:
  docs/mainline/figures/results/dinov3_classification_auc_summary.png
  docs/mainline/figures/results/dinov3_classification_auc_ge08.png
  pipeline/experiments/reports/dinov3_classification_auc_summary.csv
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS = PROJECT_ROOT / "pipeline" / "experiments" / "reports"
OUT_DIR = PROJECT_ROOT / "docs" / "mainline" / "figures" / "results"
OUT_CSV = REPORTS / "dinov3_classification_auc_summary.csv"

AUC_THRESHOLD = 0.80
METRIC_COLS = [
    ("auc_macro_ovr", "4-class macro"),
    ("early_vs_advanced_auc", "Early vs Adv"),
    ("t1_t2_auc", "T1/T2"),
    ("t2_t3_auc", "T2/T3"),
    ("t3_t4_auc", "T3/T4+"),
]

COHORT_LABEL = {
    "test_prospective_full": "Prospective full",
    "test_external": "External",
    "test_external_clinical": "External",
    "test_prospective": "Prospective",
    "val": "Validation",
    "test": "Test",
}

# framelevel external eval CSV still uses split=test_prospective_full in rows
REPORT_COHORT_OVERRIDE = {
    "dinov3_framelevel_scalar_external_eval": "External",
    "dinov3_framelevel_scalar_train_eval": "Prospective full",
    "dinov3_framelevel_scalar_train_eval_rerun_20260516_check": "Prospective full",
}

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.08,
    }
)

C_4CLASS = "#2166AC"
C_EARLY = "#4DAC26"
C_T2T3 = "#F4A582"
C_T3T4 = "#9970AB"
C_PERCLASS = ["#1b9e77", "#d95f02", "#7570b3", "#e7298a"]


def short_report(name: str) -> str:
    mapping = {
        "dinov3_framelevel_scalar_train_eval": "Frame+agg · Prospective",
        "dinov3_framelevel_scalar_external_eval": "Frame+agg · External",
        "dinov3_framelevel_scalar_train_eval_rerun_20260516_check": "Frame · Prospective (rerun)",
        "dinov3_rich_scalar_trainset_eval_topk": "Rich scalar · Prospective",
        "dinov3_trainset_feature_eval": "Compact scalar · Prospective",
        "dinov3_trainset_feature_eval_anatomic_schema": "Anatomic schema · Prospective",
        "dinov3_feature_combined_internal_prospective_v2": "Feature combo v2",
        "dinov3_feature_combined_internal_prospective": "Feature combo v1",
        "dinov3_t2t3_expert_calibrated_continue_20260518_152542_topk24_128": "T2/T3 expert",
        "dinov3_t2t3_expert_calibrated_eval_final_trainval": "T2/T3 expert (final)",
        "dinov3_v1_roi_classification_eval": "E2E · DINO mask ROI",
        "dinov3_v1_post_t035_area0005_close3_roi_classification_eval": "E2E · postproc mask",
        "dinov3_mask_gated_fusion_internal_prospective": "Mask-gated fusion",
    }
    return mapping.get(name, name.replace("dinov3_", "").replace("_", " ")[:28])


def short_feature(fs: str) -> str:
    fs = fs.replace("_", " ")
    if fs == "clinical anatomic":
        return "Clinical+anatomic"
    if "dino top16" in fs:
        return "DINO16+clinical"
    if "dino top32" in fs:
        return "DINO32+clinical"
    if "dino scalar plus clinical" in fs:
        return "DINO scalar+clinical"
    if "dino rich" in fs:
        return "DINO rich+clinical"
    return fs[:22]


def is_per_class_row(r: dict) -> bool:
    agg = str(r.get("aggregation", ""))
    return agg.startswith("OvR T") or r.get("metric_kind", "").startswith("T")


def load_csv_rows(path: Path, report: str) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            row = {
                "report": report,
                "report_short": short_report(report),
                "source_file": path.name,
                "level": r.get("level", "patient"),
                "aggregation": r.get("aggregation", "—"),
                "feature_set": r.get("feature_set", ""),
                "feature_short": short_feature(r.get("feature_set", "").replace("_", " ")),
                "model": r.get("model", ""),
                "split": r.get("split", ""),
                "cohort": REPORT_COHORT_OVERRIDE.get(
                    report,
                    COHORT_LABEL.get(r.get("split", ""), r.get("split", "")),
                ),
            }
            for col, _ in METRIC_COLS:
                if col in r and r[col]:
                    row[col] = float(r[col])
            rows.append(row)
    return rows


def load_roi_json(report_dir: Path, report: str) -> list[dict]:
    rows: list[dict] = []
    for split_dir in ("test_external", "test_prospective"):
        p = report_dir / split_dir / "test_results.json"
        if not p.is_file():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        cohort = "External" if "external" in split_dir else "Prospective"
        base = {
            "report": report,
            "report_short": short_report(report),
            "source_file": p.name,
            "level": "image",
            "aggregation": "ConvNeXt+wall",
            "feature_set": "dinov3_v1_roi_mask",
            "feature_short": "DINO mask ROI",
            "model": "end2end_classifier",
            "split": split_dir,
            "cohort": cohort,
            "auc_macro_ovr": float(data["auc"]),
        }
        for i in range(4):
            key = f"auc_c{i}"
            if key in data:
                base[key] = float(data[key])
        if "patient_level" in data:
            pl = data["patient_level"]
            rows.append(
                {
                    **base,
                    "level": "patient",
                    "aggregation": "majority",
                    "auc_macro_ovr": float(pl.get("auc", data["auc"])),
                }
            )
        rows.append(base)
        for i in range(4):
            key = f"auc_c{i}"
            if key in data:
                rows.append(
                    {
                        **base,
                        "level": "image",
                        "aggregation": f"OvR T{i+1}",
                        "auc_macro_ovr": float(data[key]),
                        "metric_kind": f"T{i+1} OvR",
                    }
                )
    return rows


def load_t2t3_summary(path: Path, report: str) -> list[dict]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict] = []
    best = data.get("best_by_val", {})
    for split_key, split_label in (("test", "Test"), ("val", "Validation")):
        block = best.get(split_key)
        if not block:
            continue
        row = {
            "report": report,
            "report_short": short_report(report),
            "source_file": path.name,
            "level": "patient",
            "aggregation": f"{block.get('kind', '')} α={block.get('alpha', '')}",
            "feature_set": "clinical_anatomic+dino_expert",
            "feature_short": "临床+T2/T3 expert",
            "model": f"{block.get('base_model', '')}+{block.get('expert_model', '')}",
            "split": split_key,
            "cohort": split_label,
        }
        for col, _ in METRIC_COLS:
            if col in block:
                row[col] = float(block[col])
        rows.append(row)
    return rows


def collect_all_rows() -> list[dict]:
    rows: list[dict] = []
    csv_names = (
        "framelevel_dinov3_scalar_results.csv",
        "rich_scalar_trainset_results.csv",
        "train_val_test_dinov3_feature_results.csv",
        "patient_level_dinov3_feature_cv_results.csv",
        "t2t3_expert_calibrated_results.csv",
    )
    for report_dir in sorted(REPORTS.glob("dinov3_*")):
        if not report_dir.is_dir():
            continue
        report = report_dir.name
        for name in csv_names:
            p = report_dir / name
            if p.is_file():
                rows.extend(load_csv_rows(p, report))
        summary = report_dir / "summary.json"
        if "roi_classification" in report:
            rows.extend(load_roi_json(report_dir, report))
        elif "t2t3_expert" in report and summary.is_file():
            rows.extend(load_t2t3_summary(summary, report))

    # Dedupe: keep best auc_macro per report×cohort×level for overview
    return rows


def row_label(r: dict) -> str:
    agg = r.get("aggregation", "—")
    if agg in ("—", "none"):
        agg = "frame" if r.get("level") == "frame" else agg
    parts = [r["report_short"], r["cohort"], r.get("level", ""), agg, r.get("feature_short", "")]
    return " · ".join(p for p in parts if p and p != "—")


def best_per_report(rows: list[dict], cohort: str | None = None) -> list[dict]:
    """Best 4-class macro per report (patient-level preferred)."""
    filtered = [r for r in rows if "auc_macro_ovr" in r and not is_per_class_row(r)]
    if cohort:
        filtered = [r for r in filtered if r.get("cohort") == cohort]
    by_report: dict[str, list[dict]] = {}
    for r in filtered:
        by_report.setdefault(r["report"], []).append(r)

    best_rows: list[dict] = []
    for report, group in by_report.items():
        group.sort(
            key=lambda x: (
                0 if x.get("level") == "patient" else 1,
                -x.get("auc_macro_ovr", 0),
            )
        )
        best_rows.append(group[0])
    best_rows.sort(key=lambda x: -x.get("auc_macro_ovr", 0))
    return best_rows


def rows_with_any_ge_threshold(rows: list[dict], thr: float = AUC_THRESHOLD) -> list[dict]:
    """Configs where macro 4-class or key binary AUC reaches threshold (exclude per-class OvR rows)."""
    out: list[dict] = []
    key_metrics = ["auc_macro_ovr", "early_vs_advanced_auc", "t2_t3_auc", "t3_t4_auc"]
    for r in rows:
        if is_per_class_row(r):
            continue
        vals = {k: r[k] for k in key_metrics if k in r and r[k] >= thr}
        if not vals:
            continue
        rr = dict(r)
        rr["_ge_metrics"] = vals
        out.append(rr)
    out.sort(key=lambda x: (-x.get("auc_macro_ovr", 0), -max(x["_ge_metrics"].values())))
    return out


def write_summary_csv(rows: list[dict], path: Path) -> None:
    fieldnames = [
        "report",
        "report_short",
        "cohort",
        "level",
        "aggregation",
        "feature_set",
        "model",
        "split",
        "auc_macro_ovr",
        "early_vs_advanced_auc",
        "t1_t2_auc",
        "t2_t3_auc",
        "t3_t4_auc",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda x: (-x.get("auc_macro_ovr", 0), x["report"])):
            w.writerow(r)


def fig_best_4class_overview(rows: list[dict]) -> None:
    """Grouped bars: best 4-class AUC per pipeline, prospective vs external."""
    pro = best_per_report(rows, "Prospective full")
    ext = best_per_report(rows, "External")

    # merge by report_short
    names = sorted({r["report_short"] for r in pro + ext}, key=str)
    pro_map = {r["report_short"]: r.get("auc_macro_ovr", np.nan) for r in pro}
    ext_map = {r["report_short"]: r.get("auc_macro_ovr", np.nan) for r in ext}

    # only pipelines with at least one split
    names = [n for n in names if not (np.isnan(pro_map.get(n, np.nan)) and np.isnan(ext_map.get(n, np.nan)))]
    # focus on scalar / frame pipelines + roi
    focus = [
        n
        for n in names
        if any(
            k in n
            for k in ("Frame", "Rich", "Compact", "Anatomic", "Feature", "T2/T3", "E2E", "Mask")
        )
    ]
    if not focus:
        focus = names[:12]

    x = np.arange(len(focus))
    w = 0.36
    pro_vals = [pro_map.get(n, np.nan) for n in focus]
    ext_vals = [ext_map.get(n, np.nan) for n in focus]

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(x - w / 2, pro_vals, w, label="Prospective full (best)", color=C_4CLASS, alpha=0.9)
    ax.bar(x + w / 2, ext_vals, w, label="External (best)", color="#D6604D", alpha=0.9)
    ax.axhline(AUC_THRESHOLD, color="#333", ls="--", lw=1, label=f"AUC = {AUC_THRESHOLD}")

    for bars, vals in zip(ax.containers, [pro_vals, ext_vals]):
        for bar, v in zip(bars, vals):
            if np.isnan(v):
                continue
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                v + 0.005,
                f"{v:.3f}",
                ha="center",
                va="bottom",
                fontsize=7,
                fontweight="bold" if v >= AUC_THRESHOLD else "normal",
            )

    ax.set_xticks(x)
    ax.set_xticklabels(focus, rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("Macro AUC (one-vs-rest, 4-class)")
    ax.set_ylim(0.68, 0.86)
    ax.set_title("DINOv3 classification pipelines · best 4-class macro AUC per run", fontweight="bold")
    ax.legend(loc="lower right", fontsize=8)
    ax.yaxis.grid(True, linestyle="--", alpha=0.35)
    ax.set_axisbelow(True)
    fig.savefig(OUT_DIR / "dinov3_classification_auc_summary.png")
    plt.close(fig)


def fig_ge08_heatmap(ge_rows: list[dict]) -> None:
    """Heatmap of metric×config pairs with any AUC ≥ 0.80 (top 24 unique pipelines)."""
    # Prefer 4-class macro ≥ threshold, then subgroup AUC
    macro = [r for r in ge_rows if r.get("auc_macro_ovr", 0) >= AUC_THRESHOLD]
    rest = [r for r in ge_rows if r not in macro]
    ge_rows = (macro + rest)[:24]
    if not ge_rows:
        return

    metric_names = [m[1] for m in METRIC_COLS]
    mat = np.full((len(ge_rows), len(METRIC_COLS)), np.nan)
    labels: list[str] = []
    for i, r in enumerate(ge_rows):
        labels.append(row_label(r)[:55])
        for j, (col, _) in enumerate(METRIC_COLS):
            if col in r:
                mat[i, j] = r[col]

    fig_h = max(4.5, 0.32 * len(ge_rows))
    fig, ax = plt.subplots(figsize=(10, fig_h))
    im = ax.imshow(mat, aspect="auto", cmap="YlGnBu", vmin=0.75, vmax=0.95)
    ax.set_xticks(range(len(METRIC_COLS)))
    ax.set_xticklabels(metric_names, rotation=30, ha="right")
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=7)
    ax.axhline(-0.5, color="white", lw=2)

    for i in range(len(ge_rows)):
        for j, (col, _) in enumerate(METRIC_COLS):
            v = mat[i, j]
            if np.isnan(v):
                continue
            color = "white" if v > 0.88 else "black"
            weight = "bold" if v >= AUC_THRESHOLD else "normal"
            ax.text(j, i, f"{v:.3f}", ha="center", va="center", color=color, fontsize=7, fontweight=weight)

    ax.set_title(f"DINOv3 classification · configs with AUC ≥ {AUC_THRESHOLD}", fontweight="bold")
    cbar = fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02)
    cbar.set_label("AUC")
    fig.savefig(OUT_DIR / "dinov3_classification_auc_ge08.png")
    plt.close(fig)


def fig_multi_metric_bars(ge_rows: list[dict]) -> None:
    """Horizontal grouped bars for top configs with 4-class ≥ 0.80 or best early/T2T3."""
    # pick unique top configs
    seen: set[str] = set()
    picked: list[dict] = []
    for r in ge_rows:
        key = (r["report"], r.get("cohort"), r.get("feature_set"), r.get("aggregation"))
        if key in seen:
            continue
        seen.add(key)
        if r.get("auc_macro_ovr", 0) >= AUC_THRESHOLD or r.get("early_vs_advanced_auc", 0) >= 0.86:
            picked.append(r)
        if len(picked) >= 10:
            break

    if not picked:
        return

    labels = [row_label(r)[:48] for r in picked]
    y = np.arange(len(labels))
    h = 0.18
    offsets = [-1.5, -0.5, 0.5, 1.5]
    colors = [C_4CLASS, C_EARLY, C_T2T3, C_T3T4]
    keys = ["auc_macro_ovr", "early_vs_advanced_auc", "t2_t3_auc", "t3_t4_auc"]
    titles = ["4-class", "Early/Adv", "T2/T3", "T3/T4+"]

    fig, ax = plt.subplots(figsize=(11, max(4, 0.45 * len(labels))))
    for off, col, color, title in zip(offsets, keys, colors, titles):
        vals = [r.get(col, np.nan) for r in picked]
        bars = ax.barh(y + off * h, vals, height=h, label=title, color=color, alpha=0.88)
        for bar, v in zip(bars, vals):
            if np.isnan(v):
                continue
            ax.text(v + 0.003, bar.get_y() + bar.get_height() / 2, f"{v:.3f}", va="center", fontsize=6)

    ax.axvline(AUC_THRESHOLD, color="#333", ls="--", lw=1)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("AUC")
    ax.set_xlim(0.72, 0.96)
    ax.set_title("DINOv3 classification · primary & subgroup AUC (≥ 0.80)", fontweight="bold")
    ax.legend(loc="lower right", ncol=2, fontsize=8)
    ax.xaxis.grid(True, linestyle="--", alpha=0.35)
    ax.set_axisbelow(True)
    fig.savefig(OUT_DIR / "dinov3_classification_auc_multimetric.png")
    plt.close(fig)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = collect_all_rows()
    write_summary_csv(rows, OUT_CSV)

    ge_rows = rows_with_any_ge_threshold(rows)
    fig_best_4class_overview(rows)
    fig_ge08_heatmap(ge_rows)
    fig_multi_metric_bars(ge_rows)

    print(f"Wrote {len(rows)} metric rows -> {OUT_CSV}")
    print(f"Configs with any AUC >= {AUC_THRESHOLD}: {len(ge_rows)}")
    print(f"Figures -> {OUT_DIR}/dinov3_classification_auc_*.png")

    # Console summary
    print("\n=== 4-class macro AUC >= 0.80 (excl. per-class OvR) ===")
    for r in sorted(
        [
            x
            for x in rows
            if x.get("auc_macro_ovr", 0) >= AUC_THRESHOLD and not is_per_class_row(x)
        ],
        key=lambda x: -x["auc_macro_ovr"],
    )[:15]:
        print(
            f"  {r.get('auc_macro_ovr', 0):.4f}  [{r['cohort']}] {row_label(r)}"
        )


if __name__ == "__main__":
    main()
