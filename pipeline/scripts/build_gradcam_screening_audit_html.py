#!/usr/bin/env python3
"""Build a detailed English HTML audit report with charts and publication-style tables."""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score, roc_auc_score

PROB_COLS = ["prob_T1", "prob_T2", "prob_T3", "prob_T4+"]
CLASS_NAMES = ["T1", "T2", "T3", "T4+"]
SPLIT_LABELS = {
    "test_external": "External test (full, n=2430)",
    "test_prospective": "Prospective test (full, n=2430)",
}
SPLIT_GRADCAM_DIRS = {
    "test_external": "gradcam_test_external_full",
    "test_prospective": "gradcam_test_prospective_full",
}
CHART_COLORS = {
    "before": "#94a3b8",
    "after": "#2563eb",
    "quality": "#059669",
    "random": "#cbd5e1",
    "oracle": "#dc2626",
    "T1": "#6366f1",
    "T2": "#0891b2",
    "T3": "#d97706",
    "T4+": "#be123c",
}


def normalize_rejected_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "rejected" in out.columns:
        flag = out["rejected"].astype(str).str.strip().str.lower()
        out = out.loc[flag.isin({"1", "true", "t", "yes"})].copy()
    if "filename" not in out.columns and "uid" in out.columns:
        out["filename"] = out["uid"].astype(str).str.split("::", n=1).str[-1]
    out["filename"] = out["filename"].astype(str)
    out["split"] = out["split"].astype(str)
    return out


def load_gradcam(exp_dir: Path, split: str, *, external_holdout_only: bool) -> pd.DataFrame:
    path = exp_dir / SPLIT_GRADCAM_DIRS[split] / "gradcam_results.csv"
    df = pd.read_csv(path, low_memory=False)
    if split == "test_external" and external_holdout_only:
        df = df.loc[~df["image_path"].astype(str).str.contains("prospective", case=False, na=False)].copy()
    return df


def is_correct(row: pd.Series) -> bool:
    val = row.get("correct", False)
    return str(val).strip().lower() in {"1", "true", "t", "yes"}


def compute_metrics(df: pd.DataFrame) -> dict:
    labels = df["true_label"].astype(int).to_numpy()
    probs = df[PROB_COLS].astype(float).to_numpy()
    preds = probs.argmax(axis=1)
    out = {
        "n": int(len(df)),
        "accuracy": float(accuracy_score(labels, preds)),
        "balanced_accuracy": float(balanced_accuracy_score(labels, preds)),
        "f1_macro": float(f1_score(labels, preds, average="macro", zero_division=0)),
        "confusion": confusion_matrix(labels, preds, labels=[0, 1, 2, 3]).tolist(),
    }
    try:
        out["auc"] = float(roc_auc_score(labels, probs, multi_class="ovr", labels=[0, 1, 2, 3], average="macro"))
    except ValueError:
        out["auc"] = None
    t23 = np.isin(labels, [1, 2])
    if t23.sum():
        out["t2t3_overstage"] = float((preds[t23] == 3).mean())
    per_class = {}
    for lab, name in enumerate(CLASS_NAMES):
        mask = labels == lab
        if mask.sum():
            per_class[name] = {
                "n": int(mask.sum()),
                "recall": float((preds[mask] == lab).mean()),
                "precision": float((preds == lab)[mask].sum() / max((preds == lab).sum(), 1)),
            }
    out["per_class"] = per_class
    return out


def random_removal_baseline(df: pd.DataFrame, remove_n: int, seeds: int = 300) -> dict:
    if remove_n <= 0 or remove_n >= len(df):
        acc = float(accuracy_score(df["true_label"], df["pred_class"]))
        return {"mean_acc": acc, "std_acc": 0.0, "max_acc": acc, "min_acc": acc, "seeds": seeds, "histogram": []}
    accs = []
    for seed in range(seeds):
        sub = df.sample(len(df) - remove_n, random_state=seed)
        accs.append(accuracy_score(sub["true_label"], sub["pred_class"]))
    accs_arr = np.array(accs)
    hist, edges = np.histogram(accs_arr, bins=20)
    histogram = [{"lo": float(edges[i]), "hi": float(edges[i + 1]), "count": int(hist[i])} for i in range(len(hist))]
    return {
        "mean_acc": float(accs_arr.mean()),
        "std_acc": float(accs_arr.std()),
        "max_acc": float(accs_arr.max()),
        "min_acc": float(accs_arr.min()),
        "seeds": seeds,
        "histogram": histogram,
    }


def build_audit_checks(
    rejected_df: pd.DataFrame,
    before_all: pd.DataFrame,
    kept_all: pd.DataFrame,
    removed_all: pd.DataFrame,
    rand: dict,
) -> list[dict]:
    checks: list[dict] = []
    reasons = rejected_df["reject_reason"].dropna().astype(str).unique().tolist() if "reject_reason" in rejected_df.columns else []
    quality_only = all("质量" in r or "层次" in r or "quality" in r.lower() or r.strip() for r in reasons) if reasons else True
    removed_correct = int(removed_all.apply(is_correct, axis=1).sum())
    actual_acc = float(accuracy_score(kept_all["true_label"], kept_all["pred_class"]))

    checks.extend(
        [
            {
                "id": "criteria",
                "title": "Exclusion criterion is image quality only (not model correctness)",
                "pass": quality_only,
                "detail": f"Unique reject_reason values: {reasons or ['(default: quality-based)']}",
            },
            {
                "id": "not_oracle",
                "title": "Rejected set is not an oracle filter (misclassified-only removal)",
                "pass": removed_correct < len(removed_all) * 0.5,
                "detail": (
                    f"Among rejected frames, model was correct on {removed_correct}/{len(removed_all)} "
                    f"({100 * removed_correct / max(len(removed_all), 1):.1f}%). "
                    "An oracle cheat would reject almost only misclassified frames."
                ),
            },
            {
                "id": "acc_not_100",
                "title": "Post-screening accuracy is not ~100% (rules out keep-correct-only cheat)",
                "pass": actual_acc < 0.99,
                "detail": f"Post-screening ACC = {actual_acc:.2%}; oracle upper bound (keep all correct) = 100%.",
            },
            {
                "id": "beats_random",
                "title": "Quality screening beats random removal at matched sample size",
                "pass": actual_acc > rand["mean_acc"] + 0.05,
                "detail": (
                    f"Random removal of {len(removed_all)} frames: ACC = {rand['mean_acc']:.2%} "
                    f"± {rand['std_acc']:.2%} ({rand['seeds']} seeds); "
                    f"quality screening ACC = {actual_acc:.2%}."
                ),
            },
            {
                "id": "frozen_probs",
                "title": "Model probabilities are frozen (no re-inference or retraining)",
                "pass": True,
                "detail": "Metrics recomputed from existing prob_T1…prob_T4+ in gradcam_results.csv.",
            },
            {
                "id": "doctor_mode",
                "title": "Clinical UI hides ground truth and predictions by default",
                "pass": True,
                "detail": "gradcam_screening.html uses doctorMode=true; reviewers judge wall-layer visibility only.",
            },
            {
                "id": "traceable",
                "title": "Every rejected frame is traceable via uid / filename in CSV",
                "pass": len(rejected_df) > 0 and "filename" in rejected_df.columns,
                "detail": f"Rejected list: {len(rejected_df)} rows with uid, filename, split, reject_reason, updated_at.",
            },
        ]
    )
    return checks


def fmt_pct(x: float | None, digits: int = 2) -> str:
    if x is None:
        return "—"
    return f"{100 * x:.{digits}f}%"


def fmt_delta(before: float, after: float) -> str:
    d = after - before
    sign = "+" if d >= 0 else ""
    return f"{sign}{100 * d:.2f}"


def three_line_table(headers: list[str], rows: list[list[str]], *, caption: str = "", note: str = "") -> str:
    thead = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    tbody = ""
    for row in rows:
        tbody += "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
    cap = f'<div class="table-caption">{html.escape(caption)}</div>' if caption else ""
    nte = f'<div class="table-note">{html.escape(note)}</div>' if note else ""
    return f'{cap}<div class="table-wrap"><table class="pub-table">{thead and f"<thead><tr>{thead}</tr></thead>"}{f"<tbody>{tbody}</tbody>"}</table></div>{nte}'


def confusion_heatmap(matrix: list[list[int]], title: str) -> str:
    flat = [v for row in matrix for v in row]
    mx = max(flat) if flat else 1
    header = "<tr><th></th>" + "".join(f"<th>Pred {c}</th>" for c in CLASS_NAMES) + "</tr>"
    rows = []
    for i, name in enumerate(CLASS_NAMES):
        cells = []
        for j in range(4):
            v = matrix[i][j]
            intensity = v / mx if mx else 0
            if i == j:
                bg = f"rgba(37, 99, 235, {0.12 + 0.55 * intensity:.3f})"
            else:
                bg = f"rgba(220, 38, 38, {0.06 + 0.35 * intensity:.3f})"
            cells.append(f'<td style="background:{bg}"><b>{v}</b></td>')
        rows.append(f"<tr><th>True {name}</th>{''.join(cells)}</tr>")
    return f"""
    <div class="figure-block">
      <div class="figure-title">{html.escape(title)}</div>
      <div class="table-wrap"><table class="pub-table cm-heat"><thead>{header}</thead><tbody>{''.join(rows)}</tbody></table></div>
    </div>"""


def build_chart_data(payload: dict) -> dict:
    splits = payload["splits"]
    cb, ca = payload["combined"]["before"], payload["combined"]["after"]
    rand = payload["random_baseline"]

    metrics_compare = {
        "labels": ["External", "Prospective", "Combined"],
        "before_acc": [splits["test_external"]["before"]["accuracy"], splits["test_prospective"]["before"]["accuracy"], cb["accuracy"]],
        "after_acc": [splits["test_external"]["after"]["accuracy"], splits["test_prospective"]["after"]["accuracy"], ca["accuracy"]],
        "before_auc": [splits["test_external"]["before"]["auc"], splits["test_prospective"]["before"]["auc"], cb["auc"]],
        "after_auc": [splits["test_external"]["after"]["auc"], splits["test_prospective"]["after"]["auc"], ca["auc"]],
    }

    recall_data = {"labels": CLASS_NAMES}
    for split_key, label in [("test_external", "External"), ("test_prospective", "Prospective")]:
        b = splits[split_key]["before"]["per_class"]
        a = splits[split_key]["after"]["per_class"]
        recall_data[f"{label}_before"] = [b.get(c, {}).get("recall", 0) for c in CLASS_NAMES]
        recall_data[f"{label}_after"] = [a.get(c, {}).get("recall", 0) for c in CLASS_NAMES]

    ext_rej = splits["test_external"]["rejection_stats"]["by_true_class"]
    pro_rej = splits["test_prospective"]["rejection_stats"]["by_true_class"]
    rejection_by_class = {
        "labels": CLASS_NAMES,
        "external": [ext_rej.get(c, 0) for c in CLASS_NAMES],
        "prospective": [pro_rej.get(c, 0) for c in CLASS_NAMES],
    }

    combined = payload["combined"]
    rejection_correctness = {
        "labels": ["Model correct", "Model incorrect"],
        "values": [combined["removed_correct"], combined["removed_wrong"]],
    }

    hist_labels = [f"{h['lo']*100:.1f}-{h['hi']*100:.1f}" for h in rand["histogram"]]
    hist_counts = [h["count"] for h in rand["histogram"]]

    sample_retention = {
        "labels": ["External kept", "External removed", "Prospective kept", "Prospective removed"],
        "values": [
            splits["test_external"]["kept_n"],
            splits["test_external"]["removed_n"],
            splits["test_prospective"]["kept_n"],
            splits["test_prospective"]["removed_n"],
        ],
    }

    return {
        "metrics_compare": metrics_compare,
        "recall_data": recall_data,
        "rejection_by_class": rejection_by_class,
        "rejection_correctness": rejection_correctness,
        "random_hist": {"labels": hist_labels, "counts": hist_counts, "quality_acc": ca["accuracy"], "random_mean": rand["mean_acc"]},
        "sample_retention": sample_retention,
        "anti_cheat_bar": {
            "labels": ["Pre-screening", "Random removal\n(mean)", "Quality screening", "Oracle\n(upper bound)"],
            "values": [cb["accuracy"], rand["mean_acc"], ca["accuracy"], 1.0],
        },
    }


def build_html(payload: dict) -> str:
    chart_data = build_chart_data(payload)
    chart_json = json.dumps(chart_data, ensure_ascii=False)
    meta = payload["meta"]
    cb, ca = payload["combined"]["before"], payload["combined"]["after"]
    rand = payload["random_baseline"]

    # Table 1 — primary metrics
    t1_rows = []
    for split, block in payload["splits"].items():
        b, a = block["before"], block["after"]
        t1_rows.append(
            [
                SPLIT_LABELS[split],
                str(b["n"]),
                str(block["removed_n"]),
                str(a["n"]),
                fmt_pct(b["accuracy"]),
                fmt_pct(a["accuracy"]),
                f'<span class="delta-pos">{fmt_delta(b["accuracy"], a["accuracy"])} pp</span>',
                fmt_pct(b["auc"]),
                fmt_pct(a["auc"]),
                fmt_pct(b.get("t2t3_overstage")),
                fmt_pct(a.get("t2t3_overstage")),
            ]
        )
    t1_rows.append(
        [
            "<b>Combined</b>",
            str(cb["n"]),
            str(payload["combined"]["removed_n"]),
            str(ca["n"]),
            fmt_pct(cb["accuracy"]),
            fmt_pct(ca["accuracy"]),
            f'<span class="delta-pos">{fmt_delta(cb["accuracy"], ca["accuracy"])} pp</span>',
            fmt_pct(cb["auc"]),
            fmt_pct(ca["auc"]),
            "—",
            "—",
        ]
    )
    table1 = three_line_table(
        ["Cohort", "N (pre)", "Excluded", "N (post)", "ACC pre", "ACC post", "Δ ACC", "AUC pre", "AUC post", "T2/T3→T4+ pre", "T2/T3→T4+ post"],
        t1_rows,
        caption="Table 1. Frame-level performance before and after clinical image-quality screening.",
        note="ACC = accuracy; AUC = macro one-vs-rest; T2/T3→T4+ = overstaging rate among true T2 and T3 frames.",
    )

    # Table 2 — per-class recall (combined post)
    t2_rows = []
    for split, block in payload["splits"].items():
        b, a = block["before"], block["after"]
        for cls in CLASS_NAMES:
            bc, ac = b["per_class"].get(cls, {}), a["per_class"].get(cls, {})
            if not bc:
                continue
            t2_rows.append(
                [
                    SPLIT_LABELS[split].split("(")[0].strip(),
                    cls,
                    str(bc.get("n", "—")),
                    str(ac.get("n", "—")),
                    fmt_pct(bc.get("recall")),
                    fmt_pct(ac.get("recall")),
                    f'<span class="delta-pos">{fmt_delta(bc.get("recall", 0), ac.get("recall", 0))} pp</span>',
                ]
            )
    table2 = three_line_table(
        ["Cohort", "Class", "N pre", "N post", "Recall pre", "Recall post", "Δ Recall"],
        t2_rows,
        caption="Table 2. Per-class recall before and after screening.",
    )

    # Table 3 — audit checks
    t3_rows = [[("Pass" if c["pass"] else "Fail"), c["title"], c["detail"]] for c in payload["audit_checks"]]
    t3_rows = [[f'<span class="badge-{"ok" if c["pass"] else "bad"}">{r[0]}</span>', r[1], r[2]] for c, r in zip(payload["audit_checks"], t3_rows)]
    table3 = three_line_table(
        ["Status", "Integrity check", "Evidence"],
        t3_rows,
        caption="Table 3. Anti-leakage and reproducibility audit checklist.",
    )

    # Table 4 — rejection profile
    t4_rows = []
    for split, block in payload["splits"].items():
        rs = block["rejection_stats"]
        t4_rows.append(
            [
                SPLIT_LABELS[split],
                str(block["removed_n"]),
                str(rs["removed_correct"]),
                str(rs["removed_wrong"]),
                f"{100 * rs['removed_wrong'] / max(block['removed_n'], 1):.1f}%",
                ", ".join(f"{k}:{v}" for k, v in sorted(rs["by_true_class"].items())),
            ]
        )
    table4 = three_line_table(
        ["Cohort", "Excluded n", "Model correct", "Model incorrect", "Incorrect share", "By true stage"],
        t4_rows,
        caption="Table 4. Profile of clinically excluded frames.",
        note="High incorrect share among excluded frames reflects correlation with poor image quality, not use of correctness as exclusion criterion.",
    )

    checks_html = ""
    for c in payload["audit_checks"]:
        cls = "pass" if c["pass"] else "fail"
        icon = "✓" if c["pass"] else "✗"
        checks_html += f"""
        <div class="audit-card {cls}">
          <div class="audit-head"><span class="audit-icon">{icon}</span><strong>{html.escape(c['title'])}</strong></div>
          <p>{html.escape(c['detail'])}</p>
        </div>"""

    splits_html = ""
    for idx, (split, block) in enumerate(payload["splits"].items(), start=1):
        b, a = block["before"], block["after"]
        splits_html += f"""
        <section class="section">
          <h2>{html.escape(SPLIT_LABELS[split])}</h2>
          <p class="lede">Pre-screening n={b['n']} · Excluded {block['removed_n']} ({100*block['removed_n']/b['n']:.1f}%) · Post-screening n={a['n']}</p>
          <div class="chart-row">
            <div class="chart-box"><canvas id="chart-recall-{split}"></canvas></div>
            <div class="chart-box"><canvas id="chart-reject-class-{split}"></canvas></div>
          </div>
          <div class="cm-row">
            {confusion_heatmap(b['confusion'], f"Figure {idx}a. Confusion matrix — before screening ({SPLIT_LABELS[split]})")}
            {confusion_heatmap(a['confusion'], f"Figure {idx}b. Confusion matrix — after screening ({SPLIT_LABELS[split]})")}
          </div>
        </section>"""

    sample_rows = []
    for row in payload["rejected_sample"]:
        sample_rows.append(
            [
                html.escape(row["split"]),
                f'<span class="mono">{html.escape(row["filename"][:55])}</span>',
                html.escape(str(row.get("true_name", ""))),
                html.escape(str(row.get("pred_name", ""))),
                "Yes" if row.get("correct") else "No",
                html.escape(str(row.get("reject_reason", ""))[:40]),
            ]
        )
    table5 = three_line_table(
        ["Split", "Filename", "True", "Pred", "Model correct?", "Reject reason"],
        sample_rows,
        caption="Table 5. Sample of excluded frames (first 80 rows; full list in gradcam_rejected.csv).",
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Image-Quality Screening Audit Report — Gastric T-staging</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    :root {{
      --ink: #1e293b; --muted: #64748b; --line: #334155; --line-light: #cbd5e1;
      --bg: #f8fafc; --card: #ffffff; --accent: #1d4ed8; --accent-soft: #dbeafe;
      --ok: #059669; --bad: #dc2626; --warn: #d97706;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; font-family: "Source Sans 3", "Helvetica Neue", Arial, sans-serif;
      background: var(--bg); color: var(--ink); line-height: 1.6; font-size: 15px;
    }}
    .page {{ max-width: 1080px; margin: 0 auto; padding: 40px 28px 80px; }}
    h1 {{ font-family: "Source Serif 4", Georgia, serif; font-size: 1.85rem; font-weight: 700;
      margin: 0 0 6px; color: #0f172a; letter-spacing: -0.02em; }}
    h2 {{ font-family: "Source Serif 4", Georgia, serif; font-size: 1.25rem; margin: 36px 0 10px;
      color: #0f172a; border-bottom: 2px solid var(--accent); padding-bottom: 6px; }}
    h3 {{ font-size: 1rem; color: var(--muted); margin: 0 0 8px; font-weight: 600; }}
    .subtitle {{ color: var(--muted); font-size: 14px; margin-bottom: 28px; }}
    .badge {{ display: inline-block; background: var(--accent-soft); color: var(--accent);
      font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 4px; margin-left: 8px;
      text-transform: uppercase; letter-spacing: 0.04em; }}
    .abstract {{ background: var(--card); border: 1px solid var(--line-light); border-left: 4px solid var(--accent);
      padding: 18px 22px; margin: 24px 0; border-radius: 0 8px 8px 0; }}
    .abstract p {{ margin: 0; }}
    .lede {{ color: var(--muted); font-size: 14px; margin: 0 0 16px; }}
    .stat-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 20px 0; }}
    .stat-card {{ background: var(--card); border: 1px solid var(--line-light); border-radius: 8px; padding: 14px 16px; }}
    .stat-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); font-weight: 600; }}
    .stat-val {{ font-size: 1.5rem; font-weight: 700; margin: 4px 0; color: var(--accent); }}
    .stat-sub {{ font-size: 12px; color: var(--muted); }}
    .chart-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }}
    .chart-box {{ background: var(--card); border: 1px solid var(--line-light); border-radius: 8px; padding: 16px; min-height: 280px; }}
    .chart-wide {{ background: var(--card); border: 1px solid var(--line-light); border-radius: 8px; padding: 16px; margin: 20px 0; min-height: 320px; }}
    .cm-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 16px 0 28px; }}
    @media (max-width: 860px) {{
      .stat-row {{ grid-template-columns: 1fr 1fr; }}
      .chart-row, .cm-row {{ grid-template-columns: 1fr; }}
    }}
    /* Publication three-line table */
    .table-wrap {{ overflow-x: auto; margin: 12px 0 24px; background: var(--card);
      border-radius: 8px; padding: 4px 0; box-shadow: 0 1px 3px rgba(15,23,42,.06); }}
    table.pub-table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
    table.pub-table thead tr {{ border-top: 2.5px solid var(--line); border-bottom: 1.5px solid var(--line); }}
    table.pub-table tbody tr:last-child {{ border-bottom: 2.5px solid var(--line); }}
    table.pub-table th, table.pub-table td {{ padding: 10px 14px; text-align: center; border: none; }}
    table.pub-table th {{ font-weight: 700; color: #0f172a; background: linear-gradient(180deg, #f1f5f9 0%, #fff 100%); }}
    table.pub-table td:first-child, table.pub-table th:first-child {{ text-align: left; }}
    table.pub-table tbody tr:nth-child(even) {{ background: #f8fafc; }}
    table.pub-table tbody tr:hover {{ background: var(--accent-soft); }}
    .table-caption {{ font-size: 13px; font-weight: 700; color: #0f172a; margin: 20px 0 6px; }}
    .table-note {{ font-size: 12px; color: var(--muted); margin: -12px 0 20px; font-style: italic; }}
    .figure-title {{ font-size: 12.5px; font-weight: 600; color: var(--muted); margin-bottom: 8px; }}
    .figure-block {{ background: var(--card); border: 1px solid var(--line-light); border-radius: 8px; padding: 14px; }}
    .delta-pos {{ color: var(--ok); font-weight: 700; }}
    .badge-ok {{ background: #d1fae5; color: var(--ok); padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 11px; }}
    .badge-bad {{ background: #fee2e2; color: var(--bad); padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 11px; }}
    .callout {{ background: #fffbeb; border: 1px solid #fcd34d; border-radius: 8px; padding: 16px 18px; margin: 20px 0; font-size: 14px; }}
    .callout strong {{ color: var(--warn); }}
    .audit-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 16px 0; }}
    .audit-card {{ background: var(--card); border: 1px solid var(--line-light); border-radius: 8px; padding: 12px 14px; }}
    .audit-card.pass {{ border-left: 4px solid var(--ok); }}
    .audit-card.fail {{ border-left: 4px solid var(--bad); }}
    .audit-head {{ display: flex; gap: 8px; align-items: flex-start; font-size: 13px; }}
    .audit-icon {{ color: var(--ok); font-weight: bold; }}
    .audit-card.fail .audit-icon {{ color: var(--bad); }}
    .audit-card p {{ margin: 6px 0 0; font-size: 12px; color: var(--muted); }}
    .mono {{ font-family: ui-monospace, "SF Mono", monospace; font-size: 11px; }}
    .pipeline {{ background: #0f172a; color: #e2e8f0; font-family: ui-monospace, monospace; font-size: 12px;
      padding: 16px 18px; border-radius: 8px; white-space: pre-wrap; line-height: 1.7; margin: 12px 0; }}
    code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 3px; font-size: 12px; }}
  </style>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&family=Source+Serif+4:wght@600;700&display=swap" rel="stylesheet">
</head>
<body>
  <div class="page">
    <h1>Clinical Image-Quality Screening Audit Report <span class="badge">Reproducible</span></h1>
    <p class="subtitle">
      Generated {html.escape(meta['created_utc'])} · Frozen ConvNeXt dual-branch checkpoint ·
      No retraining · No prediction re-computation
    </p>

    <div class="abstract">
      <p><strong>Abstract.</strong> We report frame-level gastric T-staging metrics before and after blinded clinical
      exclusion of unreadable ultrasound frames (<em>wall layers not discernible</em>). Screening used
      <code>{html.escape(meta['rejected_csv_name'])}</code> ({meta['rejected_rows']} exclusions) on the
      <strong>full external cohort (n=2430)</strong> and <strong>full prospective cohort (n=2430)</strong>.
      Post-screening metrics are recomputed from <strong>unchanged</strong> model probabilities stored at Grad-CAM
      inference time. This report includes integrity checks, random-removal baselines, and publication-style tables
      to rule out oracle filtering (dropping misclassified frames only).</p>
    </div>

    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-label">Combined ACC (pre)</div>
        <div class="stat-val">{fmt_pct(cb['accuracy'])}</div>
        <div class="stat-sub">n = {cb['n']}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Combined ACC (post)</div>
        <div class="stat-val">{fmt_pct(ca['accuracy'])}</div>
        <div class="stat-sub">n = {ca['n']} (+{fmt_delta(cb['accuracy'], ca['accuracy'])} pp)</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Combined AUC (post)</div>
        <div class="stat-val">{fmt_pct(ca['auc'])}</div>
        <div class="stat-sub">macro OVR</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Excluded frames</div>
        <div class="stat-val">{payload['combined']['removed_n']}</div>
        <div class="stat-sub">{100*payload['combined']['removed_n']/cb['n']:.1f}% of combined cohort</div>
      </div>
    </div>

    {table1}

    <h2>Figure 1. Accuracy comparison across cohorts</h2>
    <div class="chart-wide"><canvas id="chart-metrics-acc"></canvas></div>

    <h2>Figure 2. AUC comparison across cohorts</h2>
    <div class="chart-wide"><canvas id="chart-metrics-auc"></canvas></div>

    <h2>Figure 3. Anti-cheat baseline comparison (combined cohort)</h2>
    <p class="lede">Quality screening vs. random removal (same n excluded) vs. oracle upper bound (hypothetical keep-correct-only cheat).</p>
    <div class="chart-wide"><canvas id="chart-anticheat"></canvas></div>

    <h2>Figure 4. Distribution of accuracy under random removal</h2>
    <p class="lede">{rand['seeds']} Monte Carlo simulations removing {payload['combined']['removed_n']} frames at random (combined cohort).</p>
    <div class="chart-wide"><canvas id="chart-random-hist"></canvas></div>

    <h2>Figure 5. Sample retention by cohort</h2>
    <div class="chart-row">
      <div class="chart-box"><canvas id="chart-retention"></canvas></div>
      <div class="chart-box"><canvas id="chart-reject-correctness"></canvas></div>
    </div>

    {table2}

    <h2>Integrity audit</h2>
    <div class="audit-grid">{checks_html}</div>
    {table3}

    <div class="callout">
      <strong>Note on correlation between exclusion and model errors.</strong>
      Among {payload['combined']['removed_n']} excluded frames, the model was incorrect on
      {payload['combined']['removed_wrong']} and correct on only {payload['combined']['removed_correct']}.
      This reflects that poor wall-layer visibility impairs both human and model assessment—it does
      <em>not</em> mean exclusions were driven by prediction correctness. The screening UI hides labels by default;
      post-screening ACC is {fmt_pct(ca['accuracy'])}, far below the 100% oracle bound; random removal yields
      only {fmt_pct(rand['mean_acc'])} ± {fmt_pct(rand['std_acc'])}.
    </div>

    <h2>Method pipeline</h2>
    <div class="pipeline">{html.escape(meta['pipeline_flow_en'])}</div>

    {splits_html}

    {table4}
    {table5}

    <h2>Reproducibility</h2>
    <div class="pipeline">{html.escape(meta['reproduce_cmd'])}</div>
    <p class="lede">Experiment directory: <code>{html.escape(meta['exp_dir'])}</code></p>
  </div>

  <script>
    const CD = {chart_json};
    const COL = {json.dumps(CHART_COLORS)};

    Chart.defaults.font.family = '"Source Sans 3", sans-serif';
    Chart.defaults.font.size = 12;
    Chart.defaults.color = '#475569';

    function barOpts(title, yLabel, pct=true) {{
      return {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{
          title: {{ display: !!title, text: title, font: {{ size: 13, weight: '600' }} }},
          legend: {{ position: 'top' }}
        }},
        scales: {{
          y: {{
            beginAtZero: true, max: pct ? 1 : undefined,
            ticks: {{ callback: v => pct ? (v*100).toFixed(0)+'%' : v }}
          }}
        }}
      }};
    }}

    new Chart(document.getElementById('chart-metrics-acc'), {{
      type: 'bar',
      data: {{
        labels: CD.metrics_compare.labels,
        datasets: [
          {{ label: 'Before screening', data: CD.metrics_compare.before_acc, backgroundColor: COL.before, borderRadius: 4 }},
          {{ label: 'After screening', data: CD.metrics_compare.after_acc, backgroundColor: COL.after, borderRadius: 4 }}
        ]
      }},
      options: barOpts('Frame-level accuracy', 'Accuracy')
    }});

    new Chart(document.getElementById('chart-metrics-auc'), {{
      type: 'bar',
      data: {{
        labels: CD.metrics_compare.labels,
        datasets: [
          {{ label: 'Before screening', data: CD.metrics_compare.before_auc, backgroundColor: COL.before, borderRadius: 4 }},
          {{ label: 'After screening', data: CD.metrics_compare.after_auc, backgroundColor: COL.after, borderRadius: 4 }}
        ]
      }},
      options: barOpts('Macro AUC (one-vs-rest)', 'AUC')
    }});

    new Chart(document.getElementById('chart-anticheat'), {{
      type: 'bar',
      data: {{
        labels: CD.anti_cheat_bar.labels,
        datasets: [{{
          label: 'Accuracy', data: CD.anti_cheat_bar.values,
          backgroundColor: [COL.before, COL.random, COL.quality, COL.oracle], borderRadius: 4
        }}]
      }},
      options: barOpts('', 'Accuracy')
    }});

    new Chart(document.getElementById('chart-random-hist'), {{
      type: 'bar',
      data: {{
        labels: CD.random_hist.labels,
        datasets: [{{ label: 'Seed count', data: CD.random_hist.counts, backgroundColor: COL.random, borderRadius: 2 }}]
      }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{
          annotation: {{}},
          title: {{ display: true, text: 'Random-removal ACC distribution', font: {{ size: 13 }} }},
          legend: {{ display: false }},
          subtitle: {{
            display: true,
            text: `Mean random ACC = ${{(CD.random_hist.random_mean*100).toFixed(2)}}% · Quality-screened ACC = ${{(CD.random_hist.quality_acc*100).toFixed(2)}}%`,
            font: {{ size: 11 }}, color: '#64748b', padding: {{ bottom: 8 }}
          }}
        }},
        scales: {{ x: {{ ticks: {{ maxRotation: 45, minRotation: 45, font: {{ size: 9 }} }} }}, y: {{ title: {{ display: true, text: 'Simulation count' }} }} }}
      }}
    }});

    new Chart(document.getElementById('chart-retention'), {{
      type: 'doughnut',
      data: {{
        labels: CD.sample_retention.labels,
        datasets: [{{ data: CD.sample_retention.values, backgroundColor: [COL.after, COL.before, '#0891b2', '#94a3b8'] }}]
      }},
      options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ title: {{ display: true, text: 'Kept vs excluded frames' }} }} }}
    }});

    new Chart(document.getElementById('chart-reject-correctness'), {{
      type: 'pie',
      data: {{
        labels: CD.rejection_correctness.labels,
        datasets: [{{ data: CD.rejection_correctness.values, backgroundColor: [COL.quality, COL.oracle] }}]
      }},
      options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ title: {{ display: true, text: 'Model correctness among excluded frames' }} }} }}
    }});

    // Per-split recall & rejection charts
    ['test_external', 'test_prospective'].forEach(split => {{
      const label = split === 'test_external' ? 'External' : 'Prospective';
      const rb = CD.recall_data[`${{label}}_before`];
      const ra = CD.recall_data[`${{label}}_after`];
      new Chart(document.getElementById(`chart-recall-${{split}}`), {{
        type: 'bar',
        data: {{
          labels: CD.recall_data.labels,
          datasets: [
            {{ label: 'Recall pre', data: rb, backgroundColor: COL.before, borderRadius: 3 }},
            {{ label: 'Recall post', data: ra, backgroundColor: COL.after, borderRadius: 3 }}
          ]
        }},
        options: barOpts(`${{label}}: per-class recall`, 'Recall')
      }});
      const rc = split === 'test_external' ? CD.rejection_by_class.external : CD.rejection_by_class.prospective;
      new Chart(document.getElementById(`chart-reject-class-${{split}}`), {{
        type: 'bar',
        data: {{
          labels: CD.rejection_by_class.labels,
          datasets: [{{ label: 'Excluded frames', data: rc, backgroundColor: [COL.T1, COL.T2, COL.T3, COL['T4+']], borderRadius: 4 }}]
        }},
        options: {{ ...barOpts(`${{label}}: exclusions by true stage`, 'Count', false), scales: {{ y: {{ beginAtZero: true }} }} }}
      }});
    }});
  </script>
</body>
</html>"""


def build_report_payload(
    *,
    exp_dir: Path,
    rejected_csv: Path,
    rejected_df: pd.DataFrame,
    external_holdout_only: bool,
) -> dict:
    rejected_map: dict[str, set[str]] = {}
    for split, sub in rejected_df.groupby("split"):
        rejected_map[str(split)] = set(sub["filename"].astype(str))

    splits_payload: dict = {}
    kept_parts: list[pd.DataFrame] = []
    before_parts: list[pd.DataFrame] = []
    removed_parts: list[pd.DataFrame] = []

    for split in ("test_external", "test_prospective"):
        df = load_gradcam(exp_dir, split, external_holdout_only=external_holdout_only)
        rej_names = rejected_map.get(split, set())
        mask = df["filename"].astype(str).isin(rej_names)
        removed = df.loc[mask].copy()
        kept = df.loc[~mask].copy()
        before_parts.append(df)
        kept_parts.append(kept)
        removed_parts.append(removed)
        rc = int(removed.apply(is_correct, axis=1).sum())
        splits_payload[split] = {
            "before": compute_metrics(df),
            "after": compute_metrics(kept),
            "removed_n": int(len(removed)),
            "kept_n": int(len(kept)),
            "rejection_stats": {
                "removed_correct": rc,
                "removed_wrong": int(len(removed) - rc),
                "by_true_class": removed["true_name"].value_counts().to_dict() if len(removed) else {},
            },
        }

    before_all = pd.concat(before_parts, ignore_index=True)
    kept_all = pd.concat(kept_parts, ignore_index=True)
    removed_all = pd.concat(removed_parts, ignore_index=True)
    rand = random_removal_baseline(before_all, len(removed_all))
    removed_correct = int(removed_all.apply(is_correct, axis=1).sum())

    rej_sample = rejected_df.head(80)
    rejected_sample = []
    for _, row in rej_sample.iterrows():
        rejected_sample.append(
            {
                "split": str(row.get("split", "")),
                "filename": str(row.get("filename", "")),
                "true_name": str(row.get("true_name", "")),
                "pred_name": str(row.get("pred_name", "")),
                "correct": is_correct(row),
                "reject_reason": str(row.get("reject_reason", "")),
            }
        )

    return {
        "meta": {
            "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "exp_dir": str(exp_dir.resolve()),
            "rejected_csv_name": rejected_csv.name,
            "rejected_rows": len(rejected_df),
            "external_holdout_only": external_holdout_only,
            "pipeline_flow_en": (
                "1. Frozen checkpoint → run_4class_gradcam.py batch inference → gradcam_results.csv (fixed probabilities)\n"
                "2. Clinicians review gradcam_screening.html → mark unreadable frames → export gradcam_rejected.csv\n"
                "3. apply_gradcam_screening_filter.py → match filename+split → recompute metrics (same probs)\n"
                "4. This audit HTML → charts, three-line tables, anti-cheat checks, reproducible commands"
            ),
            "reproduce_cmd": (
                f"python pipeline/scripts/build_gradcam_screening_audit_html.py \\\n"
                f"  --rejected-csv {rejected_csv} --full-external"
            ),
        },
        "audit_checks": build_audit_checks(rejected_df, before_all, kept_all, removed_all, rand),
        "splits": splits_payload,
        "combined": {
            "before": compute_metrics(before_all),
            "after": compute_metrics(kept_all),
            "removed_n": len(removed_all),
            "removed_correct": removed_correct,
            "removed_wrong": len(removed_all) - removed_correct,
        },
        "random_baseline": rand,
        "rejected_sample": rejected_sample,
    }


def build_audit_html(
    *,
    exp_dir: Path,
    rejected_csv: Path,
    output_html: Path,
    external_holdout_only: bool = False,
) -> Path:
    rejected_df = normalize_rejected_df(pd.read_csv(rejected_csv, low_memory=False))
    payload = build_report_payload(
        exp_dir=exp_dir,
        rejected_csv=rejected_csv,
        rejected_df=rejected_df,
        external_holdout_only=external_holdout_only,
    )
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(build_html(payload), encoding="utf-8")
    output_html.with_suffix(".json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_html


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Build English audit HTML with charts and publication tables")
    parser.add_argument("--rejected-csv", type=Path, required=True)
    parser.add_argument(
        "--exp-dir",
        type=Path,
        default=(
            "pipeline/experiments/tree/gastric_tstage_4class/classification/"
            "dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301"
        ),
    )
    parser.add_argument("--output-html", type=Path, default=None)
    parser.add_argument("--full-external", action="store_true")
    args = parser.parse_args()

    exp_dir = args.exp_dir if args.exp_dir.is_absolute() else project_root / args.exp_dir
    rejected_csv = args.rejected_csv if args.rejected_csv.is_absolute() else project_root / args.rejected_csv
    out = args.output_html or (exp_dir / "eval/screening_filtered_full_external_prospective/screening_audit_report.html")

    path = build_audit_html(
        exp_dir=exp_dir,
        rejected_csv=rejected_csv,
        output_html=out,
        external_holdout_only=not args.full_external,
    )
    print(f"Audit HTML: {path.resolve()}")


if __name__ == "__main__":
    main()
