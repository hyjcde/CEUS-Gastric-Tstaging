#!/usr/bin/env python3
"""Build one self-contained navigation page for the GC-US T-score results.

The page keeps figures as relative local assets, so it can be opened directly
from the repository without a web server.  It summarizes the full-split model
comparison, the latest LASSO screen, complete-case sensitivity, and all latest
3D stage and KMeans views.  Older report summaries are linked as an audit trail.
"""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = (
    PROJECT_ROOT
    / "pipeline/experiments/reports/gc_us_tscore_feature_stats_v1"
)
PACK_META = (
    PROJECT_ROOT
    / "pipeline/data/gc_us_tscore_features_v1/feature_pack_v1/meta.json"
)
FULL_SPLIT = REPORT_ROOT / "full_split_v1"
LASSO = REPORT_ROOT / "lasso_latest_v1"
DEFAULT_OUT = REPORT_ROOT / "index_en.html"

SPLIT_LABELS = {
    "train": "Train",
    "val": "Validation",
    "test_prospective": "Prospective",
    "test_external": "External",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def fmt_value(value: object, column: str = "") -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "-"
    if pd.isna(value):
        return "-"
    if isinstance(value, (np.integer, int)) and not isinstance(value, bool):
        return str(int(value))
    if isinstance(value, (np.floating, float)):
        value = float(value)
        lower = column.lower()
        if any(token in lower for token in ("p", "q")) and 0 < abs(value) < 0.01:
            return f"{value:.2e}"
        if any(
            token in lower
            for token in (
                "auc",
                "qwk",
                "acc",
                "rho",
                "nmi",
                "ari",
                "coverage",
                "stability",
                "silhouette",
                "ratio",
            )
        ):
            return f"{value:.3f}"
        if abs(value) >= 100:
            return f"{value:.1f}"
        return f"{value:.3f}"
    return str(value)


def label_column(column: str) -> str:
    labels = {
        "model": "Model",
        "split": "Split",
        "n": "N",
        "auc_T3plus": "T3+ AUC",
        "auc_T3plus_oriented": "T3+ AUC",
        "auc_4class_ovr_macro": "4-class OvR AUC",
        "qwk_4class": "4-class QWK",
        "acc_4class": "4-class accuracy",
        "auc_T1vsT2": "T1 vs T2 AUC",
        "auc_T2vsT3": "T2 vs T3 AUC",
        "auc_T3vsT4": "T3 vs T4+ AUC",
        "mean_heldout": "Mean held-out",
        "feature": "Feature",
        "feature_group": "Group",
        "lasso_coef": "L1 coefficient",
        "stability_freq": "Bootstrap stability",
        "spearman_rho": "Spearman rho",
        "spearman_q": "Spearman q",
        "kruskal_q": "Kruskal q",
        "train_coverage": "Train coverage",
        "triplet_id": "Triplet",
        "labels": "Axes",
        "n_all": "N",
        "n_train": "Train N",
        "best_view_elev": "Elevation",
        "best_view_azim": "Azimuth",
        "train_kmeans_ari": "Train KMeans ARI",
        "test_prospective_kmeans_ari": "Prospective KMeans ARI",
        "test_external_kmeans_ari": "External KMeans ARI",
        "train_kmeans_nmi": "Train KMeans NMI",
        "test_prospective_kmeans_nmi": "Prospective KMeans NMI",
        "test_external_kmeans_nmi": "External KMeans NMI",
        "train_stage_silhouette_3d": "Train stage silhouette",
    }
    if column in labels:
        return labels[column]
    return column.replace("_", " ")


def table_html(
    frame: pd.DataFrame,
    columns: list[str] | None = None,
    table_id: str | None = None,
    max_rows: int | None = None,
) -> str:
    if frame.empty:
        return '<p class="muted">No rows available.</p>'
    data = frame.copy()
    if columns:
        data = data[[c for c in columns if c in data.columns]]
    if max_rows is not None:
        data = data.head(max_rows)
    attr = f' id="{esc(table_id)}"' if table_id else ""
    out = [f'<div class="table-wrap"><table{attr}><thead><tr>']
    for column in data.columns:
        out.append(f"<th>{esc(label_column(column))}</th>")
    out.append("</tr></thead><tbody>")
    for _, row in data.iterrows():
        out.append("<tr>")
        for column in data.columns:
            value = row[column]
            cls = ""
            if isinstance(value, (float, np.floating)) and np.isfinite(value):
                if value < 0:
                    cls = ' class="negative"'
                elif value >= 0.8:
                    cls = ' class="positive"'
            out.append(f"<td{cls}>{esc(fmt_value(value, column))}</td>")
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def read_csv(relative: str) -> pd.DataFrame:
    return pd.read_csv(REPORT_ROOT / relative)


def metric_card(title: str, value: str, note: str) -> str:
    return (
        '<div class="metric-card">'
        f'<div class="metric-title">{esc(title)}</div>'
        f'<div class="metric-value">{esc(value)}</div>'
        f'<div class="metric-note">{esc(note)}</div>'
        "</div>"
    )


def image_panel(
    relative_image: str,
    title: str,
    caption: str,
    relative_vector: str | None = None,
) -> str:
    image = esc(relative_image)
    link = esc(relative_vector or relative_image)
    return (
        '<figure class="figure-card">'
        f'<a href="{link}" target="_blank" rel="noopener">'
        f'<img loading="lazy" src="{image}" alt="{esc(title)}"/>'
        "</a>"
        f"<figcaption><strong>{esc(title)}</strong><br/>{esc(caption)}</figcaption>"
        "</figure>"
    )


def build_html() -> str:
    auc = read_csv("full_split_v1/pivot_auc_T3plus.csv")
    qwk = read_csv("full_split_v1/pivot_qwk_4class.csv")
    macro = read_csv("full_split_v1/pivot_auc_4class_ovr_macro.csv")
    detail = read_csv("full_split_v1/metrics_by_split.csv")
    lasso_metrics = read_csv("lasso_latest_v1/lasso_auc_by_split.csv")
    common_metrics = read_csv("lasso_latest_v1/lasso_auc_common_complete_case.csv")
    significance = read_csv("lasso_latest_v1/feature_significance.csv")
    triplets = read_csv("lasso_latest_v1/triplet_cluster_metrics.csv")
    with PACK_META.open(encoding="utf-8") as f:
        pack_meta = json.load(f)

    kitchen_auc = auc.loc[auc["model"] == "kitchen"].iloc[0]
    short_qwk = qwk.loc[qwk["model"] == "length+short_axis"].iloc[0]
    lasso_full = lasso_metrics.set_index("split")
    lasso_cc = common_metrics.set_index("split")
    selected = significance[significance["selected"] == 1].sort_values(
        "lasso_abs_coef", ascending=False
    )
    zeroed = significance[significance["selected"] == 0].sort_values(
        ["spearman_q", "kruskal_q"], ascending=True
    )

    cards = "".join(
        [
            metric_card(
                "Best full-split T3+ model",
                f"{kitchen_auc['mean_heldout']:.3f}",
                "Kitchen, mean held-out AUC",
            ),
            metric_card(
                "Best full-split 4-class QWK",
                f"{short_qwk['mean_heldout']:.3f}",
                "Length plus short-axis ratio",
            ),
            metric_card(
                "Latest LASSO terms",
                str(int(len(selected))),
                "Nonzero terms from 37 screened features",
            ),
            metric_card(
                "Latest 3D triplets",
                str(int(len(triplets))),
                "Stage view plus KMeans view per triplet",
            ),
        ]
    )

    auc_table = table_html(
        auc,
        ["model", "train", "val", "test_prospective", "test_external", "mean_heldout"],
        "aucTable",
    )
    qwk_table = table_html(
        qwk,
        ["model", "train", "val", "test_prospective", "test_external", "mean_heldout"],
        "qwkTable",
    )
    macro_table = table_html(
        macro,
        ["model", "train", "val", "test_prospective", "test_external", "mean_heldout"],
    )
    detail_columns = [
        "model",
        "split",
        "n",
        "auc_T3plus",
        "qwk_4class",
        "auc_4class_ovr_macro",
        "auc_T1vsT2",
        "auc_T2vsT3",
        "auc_T3vsT4",
    ]
    detail_table = table_html(detail, detail_columns, "detailTable")
    lasso_table = table_html(
        selected,
        [
            "feature",
            "feature_group",
            "lasso_coef",
            "stability_freq",
            "spearman_rho",
            "spearman_q",
            "kruskal_q",
            "train_coverage",
        ],
        "lassoTable",
    )
    zeroed_table = table_html(
        zeroed.head(12),
        [
            "feature",
            "feature_group",
            "lasso_coef",
            "stability_freq",
            "spearman_rho",
            "spearman_q",
            "train_coverage",
        ],
    )
    lasso_metric_table = table_html(
        lasso_metrics,
        ["split", "n", "auc_T3plus"],
    )
    common_metric_table = table_html(
        common_metrics,
        ["split", "n", "auc_T3plus"],
    )
    triplet_columns = [
        "triplet_id",
        "labels",
        "n_all",
        "n_train",
        "best_view_elev",
        "best_view_azim",
        "train_kmeans_ari",
        "test_prospective_kmeans_ari",
        "test_external_kmeans_ari",
        "train_stage_silhouette_3d",
    ]
    triplet_table = table_html(triplets, triplet_columns, "tripletTable")

    report_links = []
    for summary in sorted(REPORT_ROOT.glob("*/SUMMARY.md")):
        folder = summary.parent.name
        report_links.append(
            f'<li><a href="{esc(folder + "/SUMMARY.md")}" target="_blank">'
            f"{esc(folder)}</a></li>"
        )
    report_links_html = "".join(report_links)

    figure_cards = []
    for _, row in triplets.iterrows():
        triplet_id = str(row["triplet_id"])
        labels = str(row["labels"])
        stage_png = f"lasso_latest_v1/{triplet_id}_stage.png"
        stage_svg = f"lasso_latest_v1/{triplet_id}_stage.svg"
        km_png = f"lasso_latest_v1/{triplet_id}_kmeans.png"
        km_svg = f"lasso_latest_v1/{triplet_id}_kmeans.svg"
        figure_cards.append(
            '<div class="triplet-block">'
            f"<h3>{esc(triplet_id)}</h3>"
            f'<p class="muted">{esc(labels)}. '
            f"Train N={int(row['n_train'])}, all available N={int(row['n_all'])}. "
            f"External KMeans ARI={float(row['test_external_kmeans_ari']):.3f}.</p>"
            '<div class="figure-grid">'
            + image_panel(
                stage_png,
                f"{triplet_id}, pathology stage",
                "Colors are T1 to T4+. The black path joins stage medians.",
                stage_svg,
            )
            + image_panel(
                km_png,
                f"{triplet_id}, train-fitted KMeans",
                "Four clusters fit on train and assigned to every split.",
                km_svg,
            )
            + "</div></div>"
        )

    split_counts = pack_meta.get("n_by_split", {})
    count_text = ", ".join(
        f"{SPLIT_LABELS.get(k, k)} {int(v)}" for k, v in split_counts.items()
    )
    generated = utc_now()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>GC-US T-score results summary</title>
<style>
:root {{
  --ink:#202124; --muted:#5f6368; --line:#d9dee5; --paper:#ffffff;
  --canvas:#f4f6f8; --blue:#587fa3; --red:#c66b6b; --green:#6f9e88;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--canvas); color:var(--ink);
  font-family:Arial,Helvetica,sans-serif; line-height:1.45; }}
header {{ position:sticky; top:0; z-index:5; background:rgba(255,255,255,.97);
  border-bottom:1px solid var(--line); padding:18px max(22px, calc((100vw - 1440px)/2)); }}
h1 {{ margin:0 0 4px; font-size:25px; letter-spacing:-.02em; }}
h2 {{ margin:0 0 10px; font-size:19px; }}
h3 {{ margin:0 0 5px; font-size:15px; }}
p {{ margin:7px 0; }}
.subtitle,.muted {{ color:var(--muted); font-size:12px; }}
nav {{ display:flex; gap:14px; flex-wrap:wrap; margin-top:12px; font-size:12px; }}
a {{ color:#245b86; text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
main {{ max-width:1440px; margin:0 auto; padding:20px 22px 60px; }}
section {{ background:var(--paper); border:1px solid var(--line); padding:18px;
  margin-bottom:16px; }}
.cards {{ display:grid; grid-template-columns:repeat(4,minmax(150px,1fr)); gap:10px; }}
.metric-card {{ border-left:4px solid var(--blue); background:#f8fafb; padding:12px; }}
.metric-title {{ color:var(--muted); font-size:11px; }}
.metric-value {{ font-size:25px; font-weight:700; margin:4px 0; }}
.metric-note {{ color:var(--muted); font-size:11px; }}
.grid-3 {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }}
.grid-2 {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
.figure-card {{ margin:0; border:1px solid var(--line); background:#fff; padding:7px; }}
.figure-card img {{ display:block; width:100%; height:auto; background:#fff; }}
figcaption {{ padding:7px 3px 2px; color:var(--muted); font-size:11px; }}
figcaption strong {{ color:var(--ink); font-size:12px; }}
.table-wrap {{ overflow:auto; max-height:600px; border:1px solid var(--line); }}
table {{ width:100%; border-collapse:collapse; font-size:11px; white-space:nowrap; }}
th {{ position:sticky; top:0; background:#eef2f5; text-align:left; font-weight:700; }}
th,td {{ padding:7px 8px; border-bottom:1px solid #edf0f2; }}
tr:hover {{ background:#f7fafc; }}
.positive {{ color:#176b45; }}
.negative {{ color:#a33b43; }}
.callout {{ border-left:4px solid var(--green); background:#f4faf6; padding:11px 13px;
  font-size:13px; }}
.warning {{ border-left-color:var(--red); background:#fff7f7; }}
.links {{ columns:3; padding-left:20px; font-size:12px; }}
.triplet-block {{ border-top:1px solid var(--line); padding-top:15px; margin-top:16px; }}
.search {{ width:100%; max-width:420px; padding:8px 10px; border:1px solid var(--line);
  margin:6px 0 10px; font-size:12px; }}
details {{ margin-top:12px; }}
summary {{ cursor:pointer; font-weight:700; font-size:13px; }}
code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.92em; }}
@media (max-width:900px) {{
  .cards,.grid-3,.grid-2 {{ grid-template-columns:1fr; }}
  .links {{ columns:1; }}
  header {{ position:static; }}
}}
</style>
</head>
<body>
<header>
  <h1>GC-US T-score, complete results summary</h1>
  <div class="subtitle">Latest feature pack, full-split evaluation, LASSO screening, and 3D cluster views. Generated {esc(generated)}.</div>
  <nav>
    <a href="#overview">Overview</a>
    <a href="#full-split">Full split</a>
    <a href="#lasso">LASSO</a>
    <a href="#triplets">3D triplets</a>
    <a href="index.html">中文版</a>
    <a href="#reports">Report index</a>
  </nav>
</header>
<main>
<section id="overview">
  <h2>Overview</h2>
  <div class="cards">{cards}</div>
  <div class="callout" style="margin-top:14px">
    <strong>Current interpretation:</strong> size and geometry remain the strongest
    signals. Dynamic invasion agreement and serosal interruption add stable screening
    evidence, but the 3D distributions are continuous gradients rather than four
    clean unsupervised clusters.
  </div>
  <p class="subtitle">Pack cohort: {esc(count_text)}. The rebuilt pack contains
  {int(pack_meta.get("n_patients", 0))} patients and removes duplicate growth fields
  created by overlapping source merges.</p>
</section>

<section id="full-split">
  <h2>Full-split model evaluation</h2>
  <p>Models are fit on train only. The common complete-case cohort is used so the
  comparison across feature sets has the same patient population. Train values are
  in-sample; validation, prospective, and external values are held out.</p>
  <div class="grid-3">
    {image_panel("full_split_v1/00_auc_T3plus_all_splits.png", "T3+ AUC across splits", "Binary T3+ discrimination.")}
    {image_panel("full_split_v1/00_qwk_4class_all_splits.png", "Four-class QWK across splits", "Ordinal agreement for T1 to T4+.")}
    {image_panel("full_split_v1/00_adjacent_auc_by_split.png", "Adjacent-stage AUC", "T1 vs T2, T2 vs T3, and T3 vs T4+.")}
  </div>
  <h3 style="margin-top:18px">T3+ AUC</h3>
  {auc_table}
  <h3 style="margin-top:18px">Four-class QWK</h3>
  {qwk_table}
  <details>
    <summary>Four-class OvR AUC</summary>
    {macro_table}
  </details>
  <details>
    <summary>All selected model by split metrics</summary>
    {detail_table}
  </details>
</section>

<section id="lasso">
  <h2>Latest feature LASSO and stability screen</h2>
  <div class="grid-2">
    {image_panel("lasso_latest_v1/00_lasso_coefficients_top18.png", "Nonzero LASSO coefficients", "Positive coefficients are red, negative coefficients are blue.", "lasso_latest_v1/00_lasso_coefficients_top18.pdf")}
    <div>
      <div class="callout warning">
        LASSO coefficients are selection weights, not p values. Spearman and Kruskal
        q values are univariate train-only tests with Benjamini-Hochberg adjustment.
        Bootstrap stability is selection frequency across 80 resamples.
      </div>
      <p class="muted">Full-row evaluation uses median imputation fit on train. The
      complete-case comparison below uses the same anchor cohort as kitchen and
      pack-core.</p>
      <h3>Full-row LASSO AUC</h3>
      {lasso_metric_table}
      <h3>Common complete-case LASSO AUC</h3>
      {common_metric_table}
    </div>
  </div>
  <h3 style="margin-top:18px">Nonzero LASSO terms</h3>
  <input class="search" placeholder="Filter features" oninput="filterTable('lassoTable', this.value)"/>
  {lasso_table}
  <details>
    <summary>Strong univariate signals zeroed by LASSO</summary>
    <p class="muted">These features remain associated alone but were redundant with
    correlated terms in the multivariable L1 fit.</p>
    {zeroed_table}
  </details>
</section>

<section id="triplets">
  <h2>3D stage and KMeans triplets</h2>
  <p>Each triplet has two views. The stage view uses pathology T1 to T4+ colors and
  connects stage medians. The KMeans view fits four clusters on train only and
  assigns the remaining splits. Camera selection uses train labels only for visual
  readability, not for model validation.</p>
  <div class="callout warning">
    External KMeans ARI is near zero across these triplets. These figures support
    visual evidence review and feature redundancy analysis, not a claim of four
    biologically distinct clusters.
  </div>
  <h3 style="margin-top:18px">Triplet metrics</h3>
  {triplet_table}
  {''.join(figure_cards)}
</section>

<section id="reports">
  <h2>Report index and raw assets</h2>
  <p class="muted">The links below preserve the detailed report trail generated by
  each feature family and evaluation stage.</p>
  <ul class="links">{report_links_html}</ul>
  <p>
    <a href="full_split_v1/SUMMARY.md" target="_blank">Full-split report</a> |
    <a href="lasso_latest_v1/SUMMARY.md" target="_blank">Latest LASSO report</a> |
    <a href="../../../data/gc_us_tscore_features_v1/feature_pack_v1/FEATURE_PACK.md" target="_blank">Feature pack documentation</a> |
    <a href="../../../../scripts/analyze_gc_us_tscore_latest_lasso_3d_v1.py" target="_blank">Rebuild LASSO and 3D script</a>
  </p>
</section>
</main>
<script>
function filterTable(id, query) {{
  const q = query.toLowerCase();
  const table = document.getElementById(id);
  if (!table) return;
  for (const row of table.tBodies[0].rows) {{
    row.style.display = row.innerText.toLowerCase().includes(q) ? "" : "none";
  }}
}}
</script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build_html(), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "bytes": args.out.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
