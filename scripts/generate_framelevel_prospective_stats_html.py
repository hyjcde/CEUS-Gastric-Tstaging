#!/usr/bin/env python3
"""Statistics figures + standalone HTML for Frame+agg · Prospective pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = (
    PROJECT_ROOT
    / "pipeline/experiments/reports/dinov3_framelevel_scalar_train_eval/framelevel_dinov3_scalar_results.csv"
)
FIG_DIR = PROJECT_ROOT / "docs/mainline/figures/results"
HTML_PATH = PROJECT_ROOT / "docs/mainline/dinov3_framelevel_scalar_prospective_architecture.html"
MD_PATH = PROJECT_ROOT / "docs/mainline/dinov3_framelevel_scalar_prospective_architecture_zh.md"

SPLIT = "test_prospective_full"
MODEL_BEST = "random_forest"
FEATURE_MAIN = "clinical_anatomic"
THR = 0.80

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "#1a2332",
        "axes.facecolor": "#1a2332",
        "axes.edgecolor": "#8fa3bf",
        "axes.labelcolor": "#e8edf4",
        "xtick.color": "#e8edf4",
        "ytick.color": "#e8edf4",
        "text.color": "#e8edf4",
        "savefig.facecolor": "#1a2332",
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.12,
    }
)

C_FRAME = "#3db8c9"
C_PATIENT = "#6ee7b7"
C_DINO = "#f59e0b"
C_THRESH = "#f87171"
METRICS = [
    ("auc_macro_ovr", "4-class macro"),
    ("early_vs_advanced_auc", "Early vs Adv"),
    ("t1_t2_auc", "T1/T2"),
    ("t2_t3_auc", "T2/T3"),
    ("t3_t4_auc", "T3/T4+"),
]
AGG_LABELS = {
    "none": "frame (none)",
    "mean": "mean",
    "max": "max",
    "top2_advanced": "top2 adv",
    "top3_advanced": "top3 adv ★",
    "hybrid": "hybrid",
}
FEATURE_LABELS = {
    "clinical_anatomic": "Clinical+anatomic",
    "dino_top16_plus_clinical_anatomic": "DINO16+clinical",
    "dino_top32_plus_clinical_anatomic": "DINO32+clinical",
    "dino_top64_plus_clinical_anatomic": "DINO64+clinical",
    "dino_top128_plus_clinical_anatomic": "DINO128+clinical",
    "dino_rich_scalar_plus_clinical_anatomic": "DINO rich+clinical",
    "dino_rich_scalar": "DINO scalar only",
}


def load_test() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH)
    return df[df["split"].eq(SPLIT)].copy()


def save(fig: plt.Figure, name: str) -> str:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = FIG_DIR / f"{name}.png"
    fig.savefig(path)
    plt.close(fig)
    return f"figures/results/{name}.png"


def fig_aggregation_patient(df: pd.DataFrame) -> str:
    sub = df[
        (df["feature_set"] == FEATURE_MAIN)
        & (df["model"] == MODEL_BEST)
        & (df["level"] == "patient")
    ].sort_values("auc_macro_ovr", ascending=True)
    labels = [AGG_LABELS.get(a, a) for a in sub["aggregation"]]
    vals = sub["auc_macro_ovr"].to_numpy()

    fig, ax = plt.subplots(figsize=(8, 4.2))
    colors = [C_PATIENT if v >= THR else "#5a6d85" for v in vals]
    bars = ax.barh(labels, vals, color=colors, height=0.62)
    ax.axvline(THR, color=C_THRESH, ls="--", lw=1.2, label=f"AUC = {THR}")
    for bar, v in zip(bars, vals):
        ax.text(v + 0.002, bar.get_y() + bar.get_height() / 2, f"{v:.4f}", va="center", fontsize=8)
    ax.set_xlim(0.78, 0.82)
    ax.set_xlabel("Macro AUC (4-class OvR)")
    ax.set_title("Patient-level aggregation · clinical+anatomic · RF", fontweight="bold", pad=10)
    ax.legend(loc="lower right", fontsize=8)
    ax.xaxis.grid(True, linestyle="--", alpha=0.25)
    ax.set_axisbelow(True)
    return save(fig, "framelevel_prosp_aggregation_patient")


def fig_frame_vs_patient(df: pd.DataFrame) -> str:
    frame = df[
        (df["level"] == "frame")
        & (df["aggregation"] == "none")
        & (df["feature_set"] == FEATURE_MAIN)
        & (df["model"] == MODEL_BEST)
    ].iloc[0]
    pat = df[
        (df["level"] == "patient")
        & (df["aggregation"] == "top3_advanced")
        & (df["feature_set"] == FEATURE_MAIN)
        & (df["model"] == MODEL_BEST)
    ].iloc[0]

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    for ax, row, title, color in [
        (axes[0], frame, f"Frame (n={int(frame['n_eval'])})", C_FRAME),
        (axes[1], pat, f"Patient top3_adv (n={int(pat['n_eval'])})", C_PATIENT),
    ]:
        keys = [m[0] for m in METRICS]
        labels = [m[1] for m in METRICS]
        vals = [row[k] for k in keys]
        bars = ax.bar(labels, vals, color=color, alpha=0.88, width=0.55)
        ax.axhline(THR, color=C_THRESH, ls="--", lw=1)
        ax.set_ylim(0.72, 0.95)
        ax.set_ylabel("AUC")
        ax.set_title(title, fontweight="bold")
        ax.tick_params(axis="x", rotation=28)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, v + 0.008, f"{v:.3f}", ha="center", fontsize=7)
        ax.yaxis.grid(True, linestyle="--", alpha=0.25)
        ax.set_axisbelow(True)
    fig.suptitle("Best prospective configs · subgroup AUC", fontweight="bold", y=1.02)
    fig.tight_layout()
    return save(fig, "framelevel_prosp_frame_vs_patient_metrics")


def fig_feature_set_patient(df: pd.DataFrame) -> str:
    sub = df[(df["level"] == "patient") & (df["model"] == MODEL_BEST)].copy()
    # best aggregation per feature set
    best = sub.loc[sub.groupby("feature_set")["auc_macro_ovr"].idxmax()]
    best = best.sort_values("auc_macro_ovr", ascending=True)
    labels = [FEATURE_LABELS.get(f, f[:20]) for f in best["feature_set"]]
    vals = best["auc_macro_ovr"].to_numpy()
    colors = [
        C_PATIENT if f == FEATURE_MAIN else (C_DINO if "dino" in f else "#5a6d85")
        for f in best["feature_set"]
    ]

    fig, ax = plt.subplots(figsize=(9, 4.8))
    bars = ax.barh(labels, vals, color=colors, height=0.62)
    ax.axvline(THR, color=C_THRESH, ls="--", lw=1.2)
    for bar, v, agg in zip(bars, vals, best["aggregation"]):
        ax.text(
            v + 0.0015,
            bar.get_y() + bar.get_height() / 2,
            f"{v:.4f} ({agg})",
            va="center",
            fontsize=7,
        )
    ax.set_xlim(0.72, 0.82)
    ax.set_xlabel("Best macro AUC per feature set (patient level)")
    ax.set_title("Feature ablation · RF · test_prospective_full", fontweight="bold", pad=10)
    ax.xaxis.grid(True, linestyle="--", alpha=0.25)
    ax.set_axisbelow(True)
    return save(fig, "framelevel_prosp_feature_ablation")


def fig_model_comparison(df: pd.DataFrame) -> str:
    sub = df[
        (df["level"] == "patient")
        & (df["aggregation"] == "top3_advanced")
        & (df["feature_set"] == FEATURE_MAIN)
    ]
    order = ["random_forest", "extra_trees", "logreg"]
    sub = sub.set_index("model").reindex(order).reset_index()
    labels = ["RandomForest", "ExtraTrees", "LogReg"]
    vals = sub["auc_macro_ovr"].to_numpy()

    fig, ax = plt.subplots(figsize=(6, 4))
    colors = [C_PATIENT, "#5a6d85", "#5a6d85"]
    bars = ax.bar(labels, vals, color=colors, width=0.5)
    ax.axhline(THR, color=C_THRESH, ls="--", lw=1.2)
    ax.set_ylim(0.78, 0.82)
    ax.set_ylabel("Macro AUC")
    ax.set_title("Classifier · patient top3_advanced · clinical+anatomic", fontweight="bold")
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.001, f"{v:.4f}", ha="center", fontsize=9)
    ax.yaxis.grid(True, linestyle="--", alpha=0.25)
    ax.set_axisbelow(True)
    return save(fig, "framelevel_prosp_model_comparison")


def fig_data_scale() -> str:
    splits = ["Train", "Val", "Test (full prospective)"]
    frames = [10007, 1188, 2285]
    patients = [None, None, 479]

    fig, ax1 = plt.subplots(figsize=(7, 4))
    x = np.arange(len(splits))
    bars = ax1.bar(x, frames, color=C_FRAME, alpha=0.85, width=0.45, label="Frames")
    ax1.set_ylabel("Frame rows")
    ax1.set_xticks(x)
    ax1.set_xticklabels(splits, rotation=12, ha="right")
    for bar, v in zip(bars, frames):
        ax1.text(bar.get_x() + bar.get_width() / 2, v + 80, f"{v:,}", ha="center", fontsize=8)
    ax2 = ax1.twinx()
    pat_vals = [0, 0, 479]
    ax2.plot(x, pat_vals, "o--", color=C_PATIENT, lw=2, markersize=8, label="Patients (test)")
    ax2.set_ylabel("Patients (test only)", color=C_PATIENT)
    ax2.set_ylim(0, 550)
    ax2.tick_params(axis="y", labelcolor=C_PATIENT)
    ax1.set_title("Dataset scale · anatomic region contrastive + full prospective", fontweight="bold")
    lines1, lab1 = ax1.get_legend_handles_labels()
    lines2, lab2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, lab1 + lab2, loc="upper left", fontsize=8)
    return save(fig, "framelevel_prosp_data_scale")


def fig_heatmap_feature_agg(df: pd.DataFrame) -> str:
    sub = df[
        (df["level"] == "patient")
        & (df["model"] == MODEL_BEST)
        & (df["feature_set"].isin(list(FEATURE_LABELS.keys())[:5]))
    ]
    pivot = sub.pivot_table(
        index="feature_set", columns="aggregation", values="auc_macro_ovr", aggfunc="max"
    )
    agg_order = ["mean", "max", "top2_advanced", "top3_advanced", "hybrid"]
    pivot = pivot[[c for c in agg_order if c in pivot.columns]]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    im = ax.imshow(pivot.to_numpy(), aspect="auto", cmap="YlGnBu", vmin=0.76, vmax=0.82)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([AGG_LABELS.get(c, c) for c in pivot.columns], rotation=25, ha="right")
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([FEATURE_LABELS.get(i, i) for i in pivot.index], fontsize=8)
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            v = pivot.iloc[i, j]
            if np.isnan(v):
                continue
            ax.text(j, i, f"{v:.3f}", ha="center", va="center", fontsize=7, color="black")
    ax.set_title("Patient macro AUC · feature × aggregation (RF)", fontweight="bold")
    cbar = fig.colorbar(im, ax=ax, fraction=0.03)
    cbar.set_label("AUC")
    return save(fig, "framelevel_prosp_heatmap_feature_agg")


def build_stats_json(df: pd.DataFrame) -> dict:
    frame_best = df[
        (df["level"] == "frame")
        & (df["aggregation"] == "none")
        & (df["feature_set"] == FEATURE_MAIN)
        & (df["model"] == MODEL_BEST)
    ].iloc[0]
    pat_best = df[
        (df["level"] == "patient")
        & (df["aggregation"] == "top3_advanced")
        & (df["feature_set"] == FEATURE_MAIN)
        & (df["model"] == MODEL_BEST)
    ].iloc[0]
    return {
        "split": SPLIT,
        "frame_best": {k: float(frame_best[k]) for k, _ in METRICS if k in frame_best},
        "patient_best": {k: float(pat_best[k]) for k, _ in METRICS if k in pat_best},
        "n_eval_frame": int(frame_best["n_eval"]),
        "n_eval_patient": int(pat_best["n_eval"]),
    }


def render_html(figures: list[tuple[str, str, str]], stats: dict) -> None:
    frame_m = stats["frame_best"]
    pat_m = stats["patient_best"]

    def metric_rows(d: dict) -> str:
        rows = []
        for key, label in METRICS:
            v = d.get(key, float("nan"))
            cls = "ok" if v >= THR else ""
            rows.append(f"<tr><td>{label}</td><td class='{cls}'>{v:.4f}</td></tr>")
        return "\n".join(rows)

    fig_blocks = []
    for src, title, cap in figures:
        span = ' class="stat-figure span-2"' if any(
            x in src for x in ("frame_vs_patient", "heatmap", "aggregation")
        ) else ' class="stat-figure"'
        fig_blocks.append(
            f"""<figure{span}>
  <h4>{title}</h4>
  <img src="{src}" alt="{title}" loading="lazy" />
  <figcaption>{cap}</figcaption>
</figure>"""
        )

    fig_html = "\n".join(fig_blocks)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Frame+agg · Prospective — 架构与统计</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <style>
    :root {{
      --bg: #0f1419;
      --surface: #1a2332;
      --surface2: #243044;
      --border: #2d3f56;
      --text: #e8edf4;
      --muted: #8fa3bf;
      --accent: #3db8c9;
      --accent2: #6ee7b7;
      --warn: #f87171;
      --ok: #4ade80;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.65;
      font-size: 15px;
    }}
    .layout {{
      display: grid;
      grid-template-columns: 220px 1fr;
      min-height: 100vh;
    }}
    @media (max-width: 900px) {{
      .layout {{ grid-template-columns: 1fr; }}
      nav.side {{ position: relative; height: auto; }}
    }}
    nav.side {{
      position: sticky;
      top: 0;
      height: 100vh;
      overflow-y: auto;
      background: var(--surface);
      border-right: 1px solid var(--border);
      padding: 1.25rem 1rem;
    }}
    nav.side h2 {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin-bottom: 0.75rem;
    }}
    nav.side a {{
      display: block;
      color: var(--muted);
      text-decoration: none;
      padding: 0.35rem 0.5rem;
      border-radius: 6px;
      font-size: 0.88rem;
    }}
    nav.side a:hover {{ color: var(--accent); background: var(--surface2); }}
    main {{ padding: 2rem 2.5rem 4rem; max-width: 1080px; }}
    header.hero {{
      margin-bottom: 2rem;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid var(--border);
    }}
    header.hero h1 {{ font-size: 1.75rem; margin-bottom: 0.5rem; }}
    header.hero .subtitle {{ color: var(--muted); max-width: 40em; }}
    .kpi-row {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
      margin: 1.5rem 0 2rem;
    }}
    .kpi {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1rem 1.1rem;
    }}
    .kpi .label {{ font-size: 0.8rem; color: var(--muted); }}
    .kpi .value {{ font-size: 1.85rem; font-weight: 700; color: var(--accent2); }}
    .kpi.frame .value {{ color: var(--accent); }}
    .kpi .meta {{ font-size: 0.78rem; color: var(--muted); margin-top: 0.35rem; }}
    section {{ margin-bottom: 2.5rem; scroll-margin-top: 1rem; }}
    section h2 {{
      font-size: 1.25rem;
      color: var(--accent);
      margin-bottom: 1rem;
      border-left: 3px solid var(--accent);
      padding-left: 0.6rem;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.9rem;
      margin: 1rem 0;
    }}
    th, td {{
      border: 1px solid var(--border);
      padding: 0.5rem 0.75rem;
      text-align: left;
    }}
    th {{ background: var(--surface2); color: var(--muted); }}
    td.ok {{ color: var(--ok); font-weight: 600; }}
    .figure-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 1.25rem;
    }}
    .stat-figure {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 0.75rem;
    }}
    .stat-figure.span-2 {{ grid-column: 1 / -1; }}
    .stat-figure h4 {{ font-size: 0.9rem; margin-bottom: 0.5rem; color: var(--muted); }}
    .stat-figure img {{ width: 100%; height: auto; border-radius: 6px; }}
    .stat-figure figcaption {{ font-size: 0.78rem; color: var(--muted); margin-top: 0.4rem; }}
    .mermaid-wrap {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1rem;
      overflow-x: auto;
    }}
    code, .mono {{
      font-family: ui-monospace, monospace;
      font-size: 0.88em;
      background: var(--surface2);
      padding: 0.1em 0.35em;
      border-radius: 4px;
    }}
    .note {{
      background: var(--surface2);
      border-left: 3px solid var(--warn);
      padding: 0.75rem 1rem;
      margin: 1rem 0;
      font-size: 0.9rem;
    }}
    footer {{ color: var(--muted); font-size: 0.8rem; margin-top: 2rem; }}
    a {{ color: var(--accent); }}
  </style>
</head>
<body>
  <div class="layout">
    <nav class="side">
      <h2>目录</h2>
      <a href="#summary">结果摘要</a>
      <a href="#architecture">架构</a>
      <a href="#metrics">指标表</a>
      <a href="#figures">统计图</a>
      <a href="#reproduce">复现</a>
    </nav>
    <main>
      <header class="hero">
        <h1>Frame+agg · Prospective</h1>
        <p class="subtitle">
          DINOv3 帧级标量 + 临床/解剖表格 · 帧级训练 + 病人级晚期聚合 ·
          <code>test_prospective_full</code>（{stats["n_eval_patient"]} 例 / {stats["n_eval_frame"]} 帧）
        </p>
      </header>

      <section id="summary">
        <h2>结果摘要</h2>
        <div class="kpi-row">
          <div class="kpi frame">
            <div class="label">帧级 · 四分类 macro AUC</div>
            <div class="value">{frame_m["auc_macro_ovr"]:.4f}</div>
            <p class="meta">clinical_anatomic · RF · 无聚合</p>
          </div>
          <div class="kpi">
            <div class="label">病人级 · 四分类 macro AUC</div>
            <div class="value">{pat_m["auc_macro_ovr"]:.4f}</div>
            <p class="meta">top3_advanced 聚合 · 正式患者级口径</p>
          </div>
          <div class="kpi">
            <div class="label">Early vs Advanced</div>
            <div class="value">{pat_m["early_vs_advanced_auc"]:.3f}</div>
            <p class="meta">病人级 top3</p>
          </div>
        </div>
        <div class="note">
          帧级 AUC（0.808）高于病人级（0.803）因评估单位不同；部署汇报以<strong>病人级 top3_advanced</strong>为准。
          完整 Markdown：<a href="dinov3_framelevel_scalar_prospective_architecture_zh.md">dinov3_framelevel_scalar_prospective_architecture_zh.md</a>
        </div>
      </section>

      <section id="architecture">
        <h2>端到端架构</h2>
        <div class="mermaid-wrap">
          <pre class="mermaid">
flowchart TB
  subgraph upstream["上游离线"]
    IMG[crop_ui 帧]
    MASK[anatomic masks]
    DINO[DINOv3 ViT-B/16 L2,5,8,11]
    TAB[临床+解剖 43维]
    DINO --> SCALAR[rich scalar 112维]
    IMG --> DINO
    MASK --> DINO
    TAB --> MERGE[帧级表格]
    SCALAR --> MERGE
  end
  subgraph train["帧级训练"]
    MERGE --> RF[RandomForest / ET / LogReg]
    TR[train 10007帧] --> RF
  end
  subgraph infer["推理聚合"]
    RF --> P[帧级概率 4类]
    P --> AGG[top3_advanced等]
    AGG --> PAT[479病人 AUC 0.803]
    P --> FRM[2285帧 AUC 0.808]
  end
          </pre>
        </div>
      </section>

      <section id="metrics">
        <h2>指标明细</h2>
        <div class="figure-grid">
          <div>
            <h3 style="font-size:1rem;margin-bottom:0.5rem;color:var(--accent)">帧级最佳</h3>
            <table>
              <thead><tr><th>指标</th><th>AUC</th></tr></thead>
              <tbody>{metric_rows(frame_m)}</tbody>
            </table>
          </div>
          <div>
            <h3 style="font-size:1rem;margin-bottom:0.5rem;color:var(--accent2)">病人级 top3_advanced</h3>
            <table>
              <thead><tr><th>指标</th><th>AUC</th></tr></thead>
              <tbody>{metric_rows(pat_m)}</tbody>
            </table>
          </div>
        </div>
      </section>

      <section id="figures">
        <h2>统计可视化</h2>
        <div class="figure-grid">
          {fig_html}
        </div>
      </section>

      <section id="reproduce">
        <h2>复现</h2>
        <pre class="mono" style="padding:1rem;border-radius:8px;overflow-x:auto;background:var(--surface);border:1px solid var(--border);">python scripts/run_dinov3_framelevel_scalar_train_eval.py
python scripts/generate_framelevel_prospective_stats_html.py</pre>
        <p style="margin-top:0.75rem;color:var(--muted);font-size:0.88rem;">
          数据源：<code>pipeline/experiments/reports/dinov3_framelevel_scalar_train_eval/framelevel_dinov3_scalar_results.csv</code>
        </p>
      </section>

      <footer>Generated by generate_framelevel_prospective_stats_html.py · GastricTstaging</footer>
    </main>
  </div>
  <script>
    mermaid.initialize({{ startOnLoad: true, theme: "dark", securityLevel: "loose" }});
  </script>
</body>
</html>"""
    # fix accidental motion tags from template
    html = html.replace("<div ", "<div ").replace("</div>", "</div>")
    html = html.replace("<div class=", "<div class=").replace("<div>", "<div>")
    html = html.replace("</div>", "</div>")
    # proper fix
    html = html.replace("<div class=", "<div class=")
    for bad, good in [
        ("<div class=", "<div class="),
        ("</div>", "</div>"),
        ("<div class=\"label\">", "<div class=\"label\">"),
        ("<div class=\"value\">", "<div class=\"value\">"),
    ]:
        pass
    html = html.replace("<div class=", "<div class=")
    html = html.replace("</div>", "</div>")
    HTML_PATH.write_text(html, encoding="utf-8")


def main() -> None:
    df = load_test()
    stats = build_stats_json(df)
    figures = [
        (fig_aggregation_patient(df), "病人级聚合对比", "clinical+anatomic · RF · 五种聚合方式 macro AUC"),
        (fig_frame_vs_patient(df), "帧级 vs 病人级子任务 AUC", "左：帧级 0.808；右：病人 top3 0.803"),
        (fig_feature_set_patient(df), "特征集消融", "各 feature_set 在病人级的最佳聚合 macro AUC"),
        (fig_model_comparison(df), "分类器对比", "top3_advanced · clinical+anatomic"),
        (fig_data_scale(), "数据规模", "train / val / test_prospective_full 帧数与测试病人数"),
        (fig_heatmap_feature_agg(df), "特征×聚合热力图", "RF · patient level · macro AUC"),
    ]
    render_html(figures, stats)
    meta = {"figures": [f[0] for f in figures], "stats": stats}
    (FIG_DIR / "framelevel_prosp_stats_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote HTML -> {HTML_PATH}")
    for f in figures:
        print(f"  {f[0]}")


if __name__ == "__main__":
    main()
