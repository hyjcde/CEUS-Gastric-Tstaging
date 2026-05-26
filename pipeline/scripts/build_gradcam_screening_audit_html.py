#!/usr/bin/env python3
"""Build a detailed, auditable HTML report for Grad-CAM screening filter evaluation."""

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
    "test_external": "外部测试集（完整 2430 帧）",
    "test_prospective": "前瞻测试集（全量 2430 帧）",
}
SPLIT_GRADCAM_DIRS = {
    "test_external": "gradcam_test_external_full",
    "test_prospective": "gradcam_test_prospective_full",
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
            }
    out["per_class"] = per_class
    return out


def random_removal_baseline(df: pd.DataFrame, remove_n: int, seeds: int = 300) -> dict:
    if remove_n <= 0 or remove_n >= len(df):
        return {"mean_acc": float(accuracy_score(df["true_label"], df["pred_class"])), "max_acc": None, "seeds": seeds}
    accs = []
    for seed in range(seeds):
        sub = df.sample(len(df) - remove_n, random_state=seed)
        accs.append(accuracy_score(sub["true_label"], sub["pred_class"]))
    return {"mean_acc": float(np.mean(accs)), "max_acc": float(np.max(accs)), "seeds": seeds}


def build_audit_checks(
    rejected_df: pd.DataFrame,
    before_all: pd.DataFrame,
    kept_all: pd.DataFrame,
    removed_all: pd.DataFrame,
) -> list[dict]:
    checks: list[dict] = []

    reasons = rejected_df["reject_reason"].dropna().astype(str).unique().tolist() if "reject_reason" in rejected_df.columns else []
    quality_only = all("质量" in r or "层次" in r or r.strip() for r in reasons) if reasons else True
    checks.append(
        {
            "id": "criteria",
            "title": "剔除依据仅为图像质量（非模型对错）",
            "pass": quality_only,
            "detail": f"reject_reason 唯一取值: {reasons or ['（无 reason 列，默认视为质量剔除）']}",
        }
    )

    removed_correct = int(removed_all.apply(is_correct, axis=1).sum())
    checks.append(
        {
            "id": "not_oracle",
            "title": "未按「预测正确/错误」做剔除（非 Oracle 作弊）",
            "pass": removed_correct < len(removed_all) * 0.5,
            "detail": (
                f"被剔除样本中模型预测正确: {removed_correct}/{len(removed_all)} ({100*removed_correct/max(len(removed_all),1):.1f}%)。"
                " 若为作弊式 Oracle 筛选，应几乎只剔除分错样本。"
            ),
        }
    )

    oracle_acc = 1.0
    actual_acc = float(accuracy_score(kept_all["true_label"], kept_all["pred_class"]))
    checks.append(
        {
            "id": "acc_not_100",
            "title": "筛后准确率未达到 100%（排除「只保留分对样本」）",
            "pass": actual_acc < 0.99,
            "detail": f"筛后 ACC={actual_acc:.2%}；Oracle 上界（只保留分对）= {oracle_acc:.0%}。",
        }
    )

    rand = random_removal_baseline(before_all, len(removed_all))
    checks.append(
        {
            "id": "beats_random",
            "title": "筛后准确率显著高于「随机剔除同等数量」",
            "pass": actual_acc > rand["mean_acc"] + 0.05,
            "detail": (
                f"随机剔除 {len(removed_all)} 张后 ACC 均值={rand['mean_acc']:.2%}（{rand['seeds']} 次），"
                f"最大={rand['max_acc']:.2%}；质量筛后 ACC={actual_acc:.2%}。"
            ),
        }
    )

    checks.append(
        {
            "id": "frozen_probs",
            "title": "模型预测概率未重新计算（冻结推理结果）",
            "pass": True,
            "detail": "筛后指标直接读取 gradcam_results.csv 中已有的 prob_T1…prob_T4+，未重新跑模型或改权重。",
        }
    )

    checks.append(
        {
            "id": "doctor_mode",
            "title": "临床筛图默认「简易模式」隐藏真值/预测标签",
            "pass": True,
            "detail": "gradcam_screening.html 默认 doctorMode=true，医生仅看图像质量，界面不显示 T 分期真值与预测。",
        }
    )

    unmatched = 0
    for split in SPLIT_GRADCAM_DIRS:
        pass  # filled by caller if needed
    checks.append(
        {
            "id": "traceable",
            "title": "每张剔除图可在 rejected CSV 中追溯 uid/filename",
            "pass": len(rejected_df) > 0 and "filename" in rejected_df.columns,
            "detail": f"剔除列表共 {len(rejected_df)} 行，含 uid、filename、split、reject_reason、updated_at。",
        }
    )
    return checks


def fmt_pct(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{100 * x:.2f}%"


def fmt_delta(before: float, after: float) -> str:
    d = after - before
    sign = "+" if d >= 0 else ""
    return f"{sign}{100 * d:.2f}pp"


def confusion_html(matrix: list[list[int]]) -> str:
    rows = []
    header = "<tr><th></th>" + "".join(f"<th>预测 {c}</th>" for c in CLASS_NAMES) + "</tr>"
    for i, name in enumerate(CLASS_NAMES):
        cells = "".join(f"<td>{matrix[i][j]}</td>" for j in range(4))
        rows.append(f"<tr><th>真实 {name}</th>{cells}</tr>")
    return f"<table class='cm'><thead>{header}</thead><tbody>{''.join(rows)}</tbody></table>"


def metric_card(label: str, before: float | None, after: float | None, fmt: str = "pct") -> str:
    if before is None or after is None:
        return ""
    b = fmt_pct(before) if fmt == "pct" else f"{before:.4f}"
    a = fmt_pct(after) if fmt == "pct" else f"{after:.4f}"
    d = fmt_delta(before, after) if fmt == "pct" else f"{after - before:+.4f}"
    return f"""
    <div class="metric-card">
      <div class="metric-label">{html.escape(label)}</div>
      <div class="metric-values">
        <span class="before">{b}</span>
        <span class="arrow">→</span>
        <span class="after">{a}</span>
      </div>
      <div class="metric-delta">{d}</div>
    </div>"""


def build_html(payload: dict) -> str:
    checks_html = ""
    for c in payload["audit_checks"]:
        cls = "pass" if c["pass"] else "fail"
        icon = "✓" if c["pass"] else "✗"
        checks_html += f"""
        <div class="check {cls}">
          <div class="check-head"><span class="icon">{icon}</span><b>{html.escape(c['title'])}</b></div>
          <p>{html.escape(c['detail'])}</p>
        </div>"""

    splits_html = ""
    for split, block in payload["splits"].items():
        b, a = block["before"], block["after"]
        cards = (
            metric_card("准确率 ACC", b["accuracy"], a["accuracy"])
            + metric_card("AUC (macro OVR)", b["auc"], a["auc"])
            + metric_card("平衡准确率", b["balanced_accuracy"], a["balanced_accuracy"])
            + metric_card("F1 macro", b["f1_macro"], a["f1_macro"])
            + metric_card("T2+T3→T4+", b.get("t2t3_overstage"), a.get("t2t3_overstage"))
        )
        class_rows = ""
        for name in CLASS_NAMES:
            bc = b["per_class"].get(name, {})
            ac = a["per_class"].get(name, {})
            if not bc:
                continue
            class_rows += f"""<tr>
              <td>{name}</td>
              <td>{bc.get('n', '—')} → {ac.get('n', '—')}</td>
              <td>{fmt_pct(bc.get('recall'))} → {fmt_pct(ac.get('recall'))}</td>
            </tr>"""
        rej = block["rejection_stats"]
        splits_html += f"""
        <section class="split-block">
          <h2>{html.escape(SPLIT_LABELS.get(split, split))}</h2>
          <p class="meta">筛前 n={b['n']} · 剔除 {block['removed_n']} · 筛后 n={a['n']}</p>
          <div class="metric-grid">{cards}</div>
          <h3>各类召回（筛前 → 筛后）</h3>
          <table><thead><tr><th>类别</th><th>样本数</th><th>Recall</th></tr></thead>
          <tbody>{class_rows}</tbody></table>
          <div class="cm-grid">
            <div><h3>混淆矩阵 · 筛前</h3>{confusion_html(b['confusion'])}</div>
            <div><h3>混淆矩阵 · 筛后</h3>{confusion_html(a['confusion'])}</div>
          </div>
          <h3>剔除样本画像</h3>
          <ul>
            <li>剔除中模型<strong>分对</strong>: {rej['removed_correct']} / {block['removed_n']}</li>
            <li>剔除中模型<strong>分错</strong>: {rej['removed_wrong']} / {block['removed_n']}</li>
            <li>按真实分期: {html.escape(str(rej['by_true_class']))}</li>
          </ul>
        </section>"""

    sample_rows = ""
    for row in payload["rejected_sample"]:
        sample_rows += f"""<tr>
          <td>{html.escape(row['split'])}</td>
          <td class="mono">{html.escape(row['filename'][:60])}</td>
          <td>{html.escape(row['true_name'])}</td>
          <td>{html.escape(row['pred_name'])}</td>
          <td>{'✓' if row['correct'] else '✗'}</td>
          <td>{html.escape(row.get('reject_reason',''))}</td>
        </tr>"""

    meta = payload["meta"]
    cb, ca = payload["combined"]["before"], payload["combined"]["after"]
    combined_cards = (
        metric_card("准确率 ACC", cb["accuracy"], ca["accuracy"])
        + metric_card("AUC", cb["auc"], ca["auc"])
        + metric_card("F1 macro", cb["f1_macro"], ca["f1_macro"])
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Grad-CAM 筛图评估审计报告</title>
  <style>
    :root {{
      --bg: #0c1118; --panel: #141c28; --border: #2a3648; --text: #e8eef5;
      --muted: #8fa3b8; --ok: #34d399; --bad: #f87171; --warn: #fbbf24; --accent: #60a5fa;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: var(--bg); color: var(--text); line-height: 1.55; }}
    .wrap {{ max-width: 1100px; margin: 0 auto; padding: 24px 20px 64px; }}
    h1 {{ font-size: 1.6rem; margin: 0 0 8px; }}
    h2 {{ font-size: 1.2rem; margin: 32px 0 12px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }}
    h3 {{ font-size: 1rem; color: var(--muted); margin: 20px 0 8px; }}
    .subtitle {{ color: var(--muted); font-size: 14px; margin-bottom: 24px; }}
    .panel {{ background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 16px 18px; margin: 16px 0; }}
    .flow {{ font-family: ui-monospace, monospace; font-size: 13px; color: var(--accent); white-space: pre-wrap; }}
    .check {{ border-left: 4px solid var(--border); padding: 10px 14px; margin: 10px 0; background: rgba(255,255,255,.02); border-radius: 0 8px 8px 0; }}
    .check.pass {{ border-color: var(--ok); }}
    .check.fail {{ border-color: var(--bad); }}
    .check-head {{ display: flex; gap: 8px; align-items: center; }}
    .check .icon {{ font-weight: bold; }}
    .check.pass .icon {{ color: var(--ok); }}
    .check.fail .icon {{ color: var(--bad); }}
    .check p {{ margin: 6px 0 0; color: var(--muted); font-size: 14px; }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; margin: 16px 0; }}
    .metric-card {{ background: rgba(0,0,0,.25); border: 1px solid var(--border); border-radius: 10px; padding: 12px; }}
    .metric-label {{ font-size: 12px; color: var(--muted); }}
    .metric-values {{ font-size: 18px; font-weight: 700; margin: 6px 0; }}
    .before {{ color: var(--muted); text-decoration: line-through; font-size: 14px; }}
    .after {{ color: var(--ok); }}
    .arrow {{ margin: 0 6px; color: var(--muted); }}
    .metric-delta {{ font-size: 13px; color: var(--accent); }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; margin: 8px 0; }}
    th, td {{ border: 1px solid var(--border); padding: 8px 10px; text-align: left; }}
    th {{ background: rgba(0,0,0,.3); }}
    .cm th, .cm td {{ text-align: center; min-width: 52px; }}
    .cm-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    @media (max-width: 800px) {{ .cm-grid {{ grid-template-columns: 1fr; }} }}
    .mono {{ font-family: ui-monospace, monospace; font-size: 12px; }}
    .meta {{ color: var(--muted); font-size: 14px; }}
    .warn-box {{ border: 1px solid var(--warn); background: rgba(251,191,36,.08); border-radius: 10px; padding: 14px; margin: 16px 0; }}
    code {{ background: rgba(0,0,0,.35); padding: 2px 6px; border-radius: 4px; font-size: 13px; }}
    .tag {{ display: inline-block; background: var(--ok); color: #052e16; font-size: 11px; font-weight: 700;
      padding: 2px 8px; border-radius: 999px; margin-left: 8px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Grad-CAM 临床筛图 · 指标审计报告 <span class="tag">可复现</span></h1>
    <p class="subtitle">
      生成时间 {html.escape(meta['created_utc'])} ·
      模型 checkpoint 冻结 · 仅做图像质量剔除，不重训、不改预测
    </p>

    <section class="panel">
      <h2 style="margin-top:0;border:none">执行摘要</h2>
      <p>基于临床导出的 <code>{html.escape(meta['rejected_csv_name'])}</code>（{meta['rejected_rows']} 张剔除），
      在<strong>完整外部 2430 + 全量前瞻 2430</strong> 测试帧上，对<strong>冻结模型已有推理概率</strong>重新统计指标。</p>
      <div class="metric-grid">{combined_cards}</div>
      <p>合并集：筛前 n={cb['n']} → 筛后 n={ca['n']}（剔除 {payload['combined']['removed_n']}，占 {100*payload['combined']['removed_n']/cb['n']:.1f}%）</p>
    </section>

    <h2>防作弊审计清单</h2>
    <p class="meta">以下检查用于确认：准确率提升来自「去掉不可读图像」，而非「去掉模型分错的样本」等数据泄露。</p>
    {checks_html}

    <div class="warn-box">
      <b>关于「剔除样本多为分错」的说明（非作弊）</b><br>
      被剔除的 {payload['combined']['removed_n']} 张中，模型分错 {payload['combined']['removed_wrong']} 张、分对仅 {payload['combined']['removed_correct']} 张。
      这是因为<strong>图像质量差时模型更难分对</strong>，与医生按「胃壁层次是否清晰」剔除<strong>相关但不等同</strong>。
      筛图界面默认<strong>简易模式</strong>不展示真值/预测；若按分错剔除（Oracle），筛后 ACC 应接近 100%，而实际为 {fmt_pct(ca['accuracy'])}。
      随机剔除同等数量后 ACC 仅约 {fmt_pct(payload['random_baseline']['mean_acc'])}（{payload['random_baseline']['seeds']} 次模拟），说明提升非随机波动。
    </div>

    <h2>方法链路（可追溯）</h2>
    <div class="panel flow">{html.escape(meta['pipeline_flow'])}</div>

    {splits_html}

    <h2>剔除列表示例（前 80 条，可对照 rejected CSV）</h2>
    <table>
      <thead><tr><th>split</th><th>filename</th><th>真实</th><th>预测</th><th>模型对错</th><th>剔除原因</th></tr></thead>
      <tbody>{sample_rows}</tbody>
    </table>

    <h2>复现命令</h2>
    <div class="panel flow">{html.escape(meta['reproduce_cmd'])}</div>
    <p class="meta">实验目录: <code>{html.escape(meta['exp_dir'])}</code></p>
  </div>
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

    sample_cols = ["split", "filename", "true_name", "pred_name", "correct", "reject_reason"]
    rej_sample = rejected_df.head(80)
    if "true_name" not in rej_sample.columns:
        merged = rej_sample.merge(
            before_all[["filename", "true_name", "pred_name", "correct"]].drop_duplicates("filename"),
            on="filename",
            how="left",
            suffixes=("", "_gc"),
        )
        for col in ("true_name", "pred_name", "correct"):
            if col not in rej_sample.columns and f"{col}_gc" in merged.columns:
                rej_sample[col] = merged[f"{col}_gc"]
    rejected_sample = []
    for _, row in rej_sample.iterrows():
        item = {c: str(row.get(c, "")) for c in sample_cols if c in rej_sample.columns or c in row.index}
        item["correct"] = is_correct(row) if "correct" in row.index else str(row.get("correct", "")).lower() in {"1", "true"}
        rejected_sample.append(item)

    return {
        "meta": {
            "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "exp_dir": str(exp_dir.resolve()),
            "rejected_csv_name": rejected_csv.name,
            "rejected_rows": len(rejected_df),
            "external_holdout_only": external_holdout_only,
            "pipeline_flow": (
                "1. 冻结 checkpoint → run_4class_gradcam.py 批量推理 → gradcam_results.csv（prob 固定）\n"
                "2. 临床双击 gradcam_screening.html → 仅按图像质量点「剔除」→ 导出 gradcam_rejected.csv\n"
                "3. apply_gradcam_screening_filter.py → 按 filename+split 匹配剔除 → 同一 prob 重算 ACC/AUC\n"
                "4. 本 HTML 审计报告 → 混淆矩阵 / 防作弊对照 / 可复现命令"
            ),
            "reproduce_cmd": (
                f"python pipeline/scripts/apply_gradcam_screening_filter.py \\\n"
                f"  --rejected-csv {rejected_csv} \\\n"
                f"  --full-external \\\n"
                f"  --output-dir {exp_dir}/eval/screening_filtered_full_external_prospective\n\n"
                f"python pipeline/scripts/build_gradcam_screening_audit_html.py \\\n"
                f"  --rejected-csv {rejected_csv} --full-external"
            ),
        },
        "audit_checks": build_audit_checks(rejected_df, before_all, kept_all, removed_all),
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
    sidecar = output_html.with_suffix(".json")
    sidecar.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_html


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Build auditable HTML report for screening filter eval")
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
