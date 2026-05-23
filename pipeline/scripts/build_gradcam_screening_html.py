#!/usr/bin/env python3
"""Build a standalone offline HTML viewer for Grad-CAM test-set image screening."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GradCAM 测试集筛图 — __SPLIT__</title>
  <style>
    :root {
      --bg: #0f1419;
      --panel: #1a2332;
      --border: #2d3a4d;
      --text: #e8eef5;
      --muted: #8fa3b8;
      --ok: #3ecf8e;
      --bad: #ff6b6b;
      --warn: #f0b429;
      --accent: #5b9cf5;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--text);
      height: 100vh;
      overflow: hidden;
    }
    .layout {
      display: grid;
      grid-template-columns: 280px 1fr;
      height: 100vh;
    }
    aside {
      background: var(--panel);
      border-right: 1px solid var(--border);
      padding: 16px;
      overflow-y: auto;
    }
    main {
      display: flex;
      flex-direction: column;
      min-width: 0;
      height: 100vh;
    }
    h1 { font-size: 18px; margin: 0 0 4px; }
    .sub { color: var(--muted); font-size: 12px; line-height: 1.5; margin-bottom: 14px; }
    label { display: block; font-size: 12px; color: var(--muted); margin: 10px 0 4px; }
    select, input[type="text"], textarea {
      width: 100%;
      background: #0d1218;
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 13px;
    }
    textarea { min-height: 72px; resize: vertical; }
    .stats {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin: 12px 0;
    }
    .stat {
      background: #0d1218;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px 10px;
    }
    .stat b { display: block; font-size: 18px; }
    .stat span { font-size: 11px; color: var(--muted); }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 12px 16px;
      border-bottom: 1px solid var(--border);
      background: var(--panel);
      align-items: center;
    }
    button {
      border: 1px solid var(--border);
      background: #243044;
      color: var(--text);
      border-radius: 8px;
      padding: 8px 14px;
      cursor: pointer;
      font-size: 13px;
    }
    button:hover { background: #2f3f57; }
    button.primary { background: #2563eb; border-color: #2563eb; }
    button.danger { background: #b42318; border-color: #b42318; }
    button.success { background: #067647; border-color: #067647; }
    button:disabled { opacity: 0.45; cursor: not-allowed; }
    .viewer {
      flex: 1;
      overflow: auto;
      padding: 12px 16px 20px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 12px;
    }
    .info {
      width: min(100%, 1400px);
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px 16px;
      display: flex;
      flex-wrap: wrap;
      gap: 12px 24px;
      font-size: 14px;
    }
    .info .tag {
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
    }
    .tag.ok { background: rgba(62, 207, 142, 0.15); color: var(--ok); }
    .tag.bad { background: rgba(255, 107, 107, 0.15); color: var(--bad); }
    .tag.reject { background: rgba(240, 180, 41, 0.15); color: var(--warn); }
    .panel-wrap {
      width: min(100%, 1400px);
      background: #000;
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
    }
    .panel-wrap img {
      display: block;
      width: 100%;
      height: auto;
    }
    .probs {
      width: min(100%, 1400px);
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 8px;
    }
    .prob {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 12px;
    }
    .prob b { display: block; font-size: 16px; margin-top: 4px; }
    .prob.active { outline: 2px solid var(--accent); }
    .list {
      margin-top: 12px;
      max-height: 220px;
      overflow-y: auto;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #0d1218;
    }
    .list-item {
      padding: 8px 10px;
      border-bottom: 1px solid var(--border);
      font-size: 12px;
      cursor: pointer;
    }
    .list-item:hover { background: #182030; }
    .list-item.active { background: #1f2d44; }
    .list-item.rejected { color: var(--warn); }
    .hint { font-size: 11px; color: var(--muted); line-height: 1.5; margin-top: 10px; }
    .empty {
      padding: 40px;
      text-align: center;
      color: var(--muted);
    }
    @media (max-width: 960px) {
      .layout { grid-template-columns: 1fr; }
      aside { max-height: 40vh; }
    }
  </style>
</head>
<body>
  <div class="layout">
    <aside>
      <h1>GradCAM 筛图</h1>
      <div class="sub">解压 zip 后双击本 HTML 即可使用。标记会保存在浏览器本地，可随时导出 CSV。</div>
      <div class="stats">
        <div class="stat"><b id="stat-total">0</b><span>当前列表</span></div>
        <div class="stat"><b id="stat-reject">0</b><span>已标记剔除</span></div>
        <div class="stat"><b id="stat-reviewed">0</b><span>已浏览</span></div>
        <div class="stat"><b id="stat-idx">0/0</b><span>当前位置</span></div>
      </div>
      <label>筛选</label>
      <select id="filter-status">
        <option value="all">全部</option>
        <option value="unreviewed">未浏览</option>
        <option value="reject">已标记剔除</option>
        <option value="keep">未剔除</option>
        <option value="wrong">仅分错</option>
        <option value="correct">仅分对</option>
      </select>
      <label>真实 T 分期</label>
      <select id="filter-true">
        <option value="all">全部</option>
        <option value="T1">T1</option>
        <option value="T2">T2</option>
        <option value="T3">T3</option>
        <option value="T4+">T4+</option>
      </select>
      <label>搜索文件名</label>
      <input id="filter-search" type="text" placeholder="例如 1001916">
      <label>剔除原因（可选）</label>
      <select id="reject-reason">
        <option value="图像质量差-胃壁层次不清">图像质量差-胃壁层次不清</option>
        <option value="图像质量差-伪影/遮挡">图像质量差-伪影/遮挡</option>
        <option value="图像质量差-其他">图像质量差-其他</option>
        <option value="暂不确定">暂不确定</option>
      </select>
      <label>备注</label>
      <textarea id="reject-note" placeholder="可选备注"></textarea>
      <div class="hint">
        快捷键：← → 切换；X 标记剔除；K 取消剔除；N 下一张未浏览
      </div>
      <div style="margin-top:12px; display:flex; flex-direction:column; gap:8px;">
        <button class="primary" id="btn-export">导出剔除列表 CSV</button>
        <button id="btn-clear-storage">清空本地标记</button>
      </div>
      <div class="list" id="thumb-list"></div>
    </aside>
    <main>
      <div class="toolbar">
        <button id="btn-prev">← 上一张</button>
        <button id="btn-next">下一张 →</button>
        <button id="btn-next-unreviewed">下一张未浏览</button>
        <button class="danger" id="btn-reject">标记剔除 (X)</button>
        <button class="success" id="btn-keep">保留 / 取消剔除 (K)</button>
      </div>
      <div class="viewer" id="viewer">
        <div class="empty">加载中…</div>
      </div>
    </main>
  </div>
  <script id="cases-data" type="application/json">__CASES_JSON__</script>
  <script>
    const META = __META_JSON__;
    const CASES = JSON.parse(document.getElementById("cases-data").textContent);
    const STORAGE_KEY = "gradcam_screening_" + META.storage_key;

    let reviews = loadReviews();
    let filtered = [];
    let currentIndex = 0;

    function loadReviews() {
      try {
        return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
      } catch (e) {
        return {};
      }
    }

    function saveReviews() {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(reviews));
      refreshStats();
      renderList();
    }

    function getReview(id) {
      return reviews[id] || { viewed: false, rejected: false, reason: "", note: "", updated_at: "" };
    }

    function applyFilters() {
      const status = document.getElementById("filter-status").value;
      const trueName = document.getElementById("filter-true").value;
      const search = document.getElementById("filter-search").value.trim().toLowerCase();
      filtered = CASES.filter((item) => {
        const rev = getReview(item.id);
        if (trueName !== "all" && item.true !== trueName) return false;
        if (search && !item.id.toLowerCase().includes(search)) return false;
        if (status === "reject" && !rev.rejected) return false;
        if (status === "keep" && rev.rejected) return false;
        if (status === "unreviewed" && rev.viewed) return false;
        if (status === "wrong" && item.correct) return false;
        if (status === "correct" && !item.correct) return false;
        return true;
      });
      if (currentIndex >= filtered.length) currentIndex = Math.max(0, filtered.length - 1);
    }

    function refreshStats() {
      const rejectCount = CASES.filter((c) => getReview(c.id).rejected).length;
      const reviewedCount = CASES.filter((c) => getReview(c.id).viewed).length;
      document.getElementById("stat-total").textContent = filtered.length;
      document.getElementById("stat-reject").textContent = rejectCount;
      document.getElementById("stat-reviewed").textContent = reviewedCount;
      document.getElementById("stat-idx").textContent = filtered.length
        ? (currentIndex + 1) + "/" + filtered.length
        : "0/0";
    }

    function renderList() {
      const list = document.getElementById("thumb-list");
      const current = filtered[currentIndex];
      list.innerHTML = filtered.slice(0, 200).map((item, idx) => {
        const rev = getReview(item.id);
        const cls = [
          "list-item",
          idx === currentIndex ? "active" : "",
          rev.rejected ? "rejected" : "",
        ].filter(Boolean).join(" ");
        return `<div class="${cls}" data-idx="${idx}">${item.id} | ${item.true}→${item.pred}${rev.rejected ? " [剔除]" : ""}</div>`;
      }).join("");
      if (filtered.length > 200) {
        list.innerHTML += `<div class="list-item">… 还有 ${filtered.length - 200} 条，请用筛选或搜索</div>`;
      }
      list.querySelectorAll(".list-item[data-idx]").forEach((el) => {
        el.addEventListener("click", () => {
          currentIndex = Number(el.dataset.idx);
          renderCurrent();
        });
      });
    }

    function renderCurrent() {
      applyFilters();
      refreshStats();
      renderList();
      const viewer = document.getElementById("viewer");
      const item = filtered[currentIndex];
      if (!item) {
        viewer.innerHTML = `<div class="empty">没有符合筛选条件的样本</div>`;
        return;
      }
      const rev = getReview(item.id);
      rev.viewed = true;
      reviews[item.id] = rev;
      saveReviews();

      document.getElementById("reject-note").value = rev.note || "";
      if (rev.reason) document.getElementById("reject-reason").value = rev.reason;

      const statusTag = rev.rejected
        ? `<span class="tag reject">已标记剔除</span>`
        : `<span class="tag ok">保留</span>`;
      const correctTag = item.correct
        ? `<span class="tag ok">预测正确</span>`
        : `<span class="tag bad">预测错误</span>`;

      const probs = ["T1", "T2", "T3", "T4+"].map((name) => {
        const val = (item.probs && item.probs[name]) ? item.probs[name] : 0;
        const active = name === item.pred ? " active" : "";
        return `<div class="prob${active}"><span>${name}</span><b>${(val * 100).toFixed(1)}%</b></div>`;
      }).join("");

      viewer.innerHTML = `
        <div class="info">
          <div><b>${item.id}</b></div>
          <div>真实: <b>${item.true}</b></div>
          <div>预测: <b>${item.pred}</b></div>
          <div>${statusTag} ${correctTag}</div>
          <div style="color:var(--muted); font-size:12px;">数据集: ${META.split}</div>
        </div>
        <div class="probs">${probs}</div>
        <div class="panel-wrap">
          <img src="${item.panel}" alt="${item.id}" onerror="this.parentElement.innerHTML='<div class=\\'empty\\'>找不到图片: ${item.panel}</div>'">
        </div>
      `;
    }

    function markReject() {
      const item = filtered[currentIndex];
      if (!item) return;
      reviews[item.id] = {
        viewed: true,
        rejected: true,
        reason: document.getElementById("reject-reason").value,
        note: document.getElementById("reject-note").value.trim(),
        updated_at: new Date().toISOString(),
      };
      saveReviews();
      goNext();
    }

    function markKeep() {
      const item = filtered[currentIndex];
      if (!item) return;
      reviews[item.id] = {
        viewed: true,
        rejected: false,
        reason: "",
        note: document.getElementById("reject-note").value.trim(),
        updated_at: new Date().toISOString(),
      };
      saveReviews();
      renderCurrent();
    }

    function goPrev() {
      if (!filtered.length) return;
      currentIndex = (currentIndex - 1 + filtered.length) % filtered.length;
      renderCurrent();
    }

    function goNext() {
      if (!filtered.length) return;
      currentIndex = (currentIndex + 1) % filtered.length;
      renderCurrent();
    }

    function goNextUnreviewed() {
      if (!filtered.length) return;
      for (let step = 1; step <= filtered.length; step++) {
        const idx = (currentIndex + step) % filtered.length;
        if (!getReview(filtered[idx].id).viewed) {
          currentIndex = idx;
          renderCurrent();
          return;
        }
      }
      goNext();
    }

    function exportCsv() {
      const rows = [["filename", "true_name", "pred_name", "correct", "rejected", "reason", "note", "panel", "updated_at"]];
      CASES.forEach((item) => {
        const rev = getReview(item.id);
        if (!rev.rejected) return;
        rows.push([
          item.id,
          item.true,
          item.pred,
          item.correct ? "1" : "0",
          "1",
          rev.reason || "",
          rev.note || "",
          item.panel,
          rev.updated_at || "",
        ]);
      });
      const csv = rows.map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(",")).join("\n");
      const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = META.split + "_rejected.csv";
      a.click();
      URL.revokeObjectURL(url);
    }

    document.getElementById("btn-prev").addEventListener("click", goPrev);
    document.getElementById("btn-next").addEventListener("click", goNext);
    document.getElementById("btn-next-unreviewed").addEventListener("click", goNextUnreviewed);
    document.getElementById("btn-reject").addEventListener("click", markReject);
    document.getElementById("btn-keep").addEventListener("click", markKeep);
    document.getElementById("btn-export").addEventListener("click", exportCsv);
    document.getElementById("btn-clear-storage").addEventListener("click", () => {
      if (confirm("确定清空本数据集的所有本地标记吗？")) {
        localStorage.removeItem(STORAGE_KEY);
        reviews = {};
        renderCurrent();
      }
    });
    ["filter-status", "filter-true"].forEach((id) => {
      document.getElementById(id).addEventListener("change", () => { currentIndex = 0; renderCurrent(); });
    });
    document.getElementById("filter-search").addEventListener("input", () => { currentIndex = 0; renderCurrent(); });

    document.addEventListener("keydown", (e) => {
      if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT") return;
      if (e.key === "ArrowLeft") goPrev();
      if (e.key === "ArrowRight") goNext();
      if (e.key.toLowerCase() === "x") markReject();
      if (e.key.toLowerCase() === "k") markKeep();
      if (e.key.toLowerCase() === "n") goNextUnreviewed();
    });

    renderCurrent();
  </script>
</body>
</html>
"""


def rel_panel_path(panel_path: object, root_dir: Path) -> str | None:
    if panel_path is None or (isinstance(panel_path, float) and pd.isna(panel_path)):
        return None
    raw = str(panel_path).strip()
    if not raw:
        return None
    path = Path(raw)
    if path.is_file():
        try:
            return path.relative_to(root_dir.resolve()).as_posix()
        except ValueError:
            pass
    root_name = root_dir.name
    marker = f"{root_name}/"
    if marker in raw.replace("\\", "/"):
        idx = raw.replace("\\", "/").index(marker)
        return raw.replace("\\", "/")[idx + len(marker) :]
    marker2 = "panels/"
    if marker2 in raw.replace("\\", "/"):
        idx = raw.replace("\\", "/").index(marker2)
        return raw.replace("\\", "/")[idx:]
    if path.name.endswith("_panel.png"):
        return f"panels/{path.name}"
    return path.name


def row_to_case(row: pd.Series, root_dir: Path) -> dict | None:
    panel = rel_panel_path(row.get("panel_path"), root_dir)
    if not panel:
        return None
    filename = str(row.get("filename") or Path(panel).stem.replace("_panel", ""))
    probs = {}
    for name in ("T1", "T2", "T3", "T4+"):
        col = f"prob_{name.replace('+', '+')}"
        if col in row and pd.notna(row[col]):
            probs[name] = float(row[col])
    correct_raw = row.get("correct", False)
    correct = str(correct_raw).strip().lower() in {"1", "true", "t", "yes"}
    return {
        "id": filename,
        "panel": panel,
        "true": str(row.get("true_name", "")),
        "pred": str(row.get("pred_name", "")),
        "correct": correct,
        "probs": probs,
    }


def build_cases_df(df: pd.DataFrame, root_dir: Path) -> list[dict]:
    cases: list[dict] = []
    for _, row in df.iterrows():
        case = row_to_case(row, root_dir)
        if case is not None:
            cases.append(case)
    return cases


def build_html(
    results_csv: Path,
    output_html: Path,
    split: str,
    root_dir: Path | None = None,
) -> dict:
    root_dir = (root_dir or results_csv.parent).resolve()
    df = pd.read_csv(results_csv, low_memory=False)
    cases = build_cases_df(df, root_dir)
    if not cases:
        raise SystemExit(f"No cases with valid panel_path found in {results_csv}")

    meta = {
        "split": split,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "total": len(cases),
        "storage_key": split,
    }
    html_text = (
        HTML_TEMPLATE.replace("__SPLIT__", split)
        .replace("__CASES_JSON__", json.dumps(cases, ensure_ascii=False))
        .replace("__META_JSON__", json.dumps(meta, ensure_ascii=False))
    )
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html_text, encoding="utf-8")
    return {
        "html": str(output_html),
        "split": split,
        "cases": len(cases),
        "results_rows": int(len(df)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build offline Grad-CAM screening HTML")
    parser.add_argument(
        "--results-csv",
        type=Path,
        required=True,
        help="Path to gradcam_results.csv (inside unpacked zip root)",
    )
    parser.add_argument(
        "--output-html",
        type=Path,
        default=None,
        help="Output HTML path (default: same dir as csv, gradcam_screening.html)",
    )
    parser.add_argument(
        "--split",
        type=str,
        default="test_set",
        help="Split label shown in UI and export filename",
    )
    parser.add_argument(
        "--root-dir",
        type=Path,
        default=None,
        help="Root directory for resolving relative panel paths (default: csv parent)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_html = args.output_html or (args.results_csv.parent / "gradcam_screening.html")
    summary = build_html(args.results_csv, output_html, args.split, args.root_dir)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
