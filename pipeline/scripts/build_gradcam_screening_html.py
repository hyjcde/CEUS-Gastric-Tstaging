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
  <title>__PAGE_TITLE__</title>
  <style>
    :root {
      --bg: #0b1017;
      --panel: #151d2b;
      --border: #2a364a;
      --text: #edf2f7;
      --muted: #8fa3b8;
      --ok: #3ecf8e;
      --bad: #ff6b6b;
      --warn: #f0b429;
      --accent: #5b9cf5;
      --true-color: #22c55e;
      --wrong-color: #ef4444;
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
      grid-template-columns: 300px 1fr;
      height: 100vh;
    }
    aside {
      background: var(--panel);
      border-right: 1px solid var(--border);
      padding: 14px;
      overflow-y: auto;
    }
    main {
      display: flex;
      flex-direction: column;
      min-width: 0;
      height: 100vh;
    }
    h1 { font-size: 17px; margin: 0 0 4px; }
    .sub { color: var(--muted); font-size: 12px; line-height: 1.5; margin-bottom: 12px; }
    label { display: block; font-size: 12px; color: var(--muted); margin: 10px 0 4px; }
    select, input[type="text"], textarea {
      width: 100%;
      background: #0a0f15;
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 13px;
    }
    textarea { min-height: 64px; resize: vertical; }
    .stats {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin: 10px 0;
    }
    .stat {
      background: #0a0f15;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px 10px;
    }
    .stat b { display: block; font-size: 17px; }
    .stat span { font-size: 11px; color: var(--muted); }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 10px 14px;
      border-bottom: 1px solid var(--border);
      background: var(--panel);
      align-items: center;
    }
    button, .seg-btn {
      border: 1px solid var(--border);
      background: #243044;
      color: var(--text);
      border-radius: 8px;
      padding: 8px 12px;
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
      padding: 10px 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .info {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 10px 14px;
      display: flex;
      flex-wrap: wrap;
      gap: 10px 20px;
      font-size: 13px;
      align-items: center;
    }
    .tag {
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
    }
    .tag.ok { background: rgba(62, 207, 142, 0.15); color: var(--ok); }
    .tag.bad { background: rgba(255, 107, 107, 0.15); color: var(--bad); }
    .tag.reject { background: rgba(240, 180, 41, 0.15); color: var(--warn); }
    .tag.split { background: rgba(91, 156, 245, 0.15); color: var(--accent); }
    .probs {
      display: grid;
      grid-template-columns: repeat(4, minmax(80px, 1fr));
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
    .prob.true-hit { box-shadow: inset 0 0 0 1px var(--ok); }
    .panel-stage {
      position: relative;
      width: 100%;
      max-width: 1680px;
      margin: 0 auto;
      background: #000;
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: auto;
      min-height: calc(100vh - 280px);
      max-height: calc(100vh - 220px);
    }
    .panel-img {
      display: block;
      width: 100%;
      height: auto;
      min-width: 720px;
    }
    .panel-stage canvas.draw-layer {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      cursor: crosshair;
      pointer-events: auto;
    }
    .panel-inner {
      position: relative;
      width: 100%;
      line-height: 0;
    }
    .path-error {
      padding: 24px;
      line-height: 1.7;
      color: #ffb4b4;
      background: #2a1215;
      border: 1px solid #7f1d1d;
      border-radius: 10px;
      max-width: 900px;
      margin: 24px auto;
    }
    .path-error code { color: #fbbf24; }
    .annotate-head {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin: 8px 0;
    }
    .legend { font-size: 12px; color: var(--muted); }
    .legend .g { color: var(--true-color); }
    .legend .r { color: var(--wrong-color); }
    .list {
      margin-top: 10px;
      max-height: 180px;
      overflow-y: auto;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #0a0f15;
    }
    .list-item {
      padding: 7px 9px;
      border-bottom: 1px solid var(--border);
      font-size: 11px;
      cursor: pointer;
    }
    .list-item:hover { background: #182030; }
    .list-item.active { background: #1f2d44; }
    .list-item.rejected { color: var(--warn); }
    .hint { font-size: 11px; color: var(--muted); line-height: 1.5; margin-top: 8px; }
    .empty { padding: 36px; text-align: center; color: var(--muted); }
    .hidden { display: none !important; }
    @media (max-width: 1100px) {
      .layout { grid-template-columns: 1fr; }
      aside { max-height: 38vh; }
      .panel-img { min-width: 0; }
    }
  </style>
</head>
<body>
  <div class="layout">
    <aside>
      <h1>__PAGE_TITLE__</h1>
      <div class="sub" id="page-subtitle">__PAGE_SUBTITLE__</div>
      <div class="stats">
        <div class="stat"><b id="stat-total">0</b><span>当前列表</span></div>
        <div class="stat"><b id="stat-reject">0</b><span>已剔除</span></div>
        <div class="stat"><b id="stat-reviewed">0</b><span>已浏览</span></div>
        <div class="stat"><b id="stat-idx">0/0</b><span>当前位置</span></div>
      </div>
      <label id="split-filter-label">数据集</label>
      <select id="filter-split">
        <option value="all">全部</option>
        <option value="test_external">外部测试</option>
        <option value="test_prospective">前瞻测试</option>
      </select>
      <label>筛选状态</label>
      <select id="filter-status">
        <option value="all">全部</option>
        <option value="unreviewed">未浏览</option>
        <option value="reject">已标记剔除</option>
        <option value="keep">未剔除</option>
        <option value="wrong">仅分错</option>
        <option value="correct">仅分对</option>
        <option value="cross">跨级误分 (|ΔT|&gt;1)</option>
        <option value="adjacent">相邻误分 (|ΔT|=1)</option>
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
      <label>剔除原因</label>
      <select id="reject-reason">
        <option value="图像质量差-胃壁层次不清">图像质量差-胃壁层次不清</option>
        <option value="图像质量差-伪影/遮挡">图像质量差-伪影/遮挡</option>
        <option value="图像质量差-其他">图像质量差-其他</option>
        <option value="暂不确定">暂不确定</option>
      </select>
      <label>备注</label>
      <textarea id="reject-note" placeholder="可选备注"></textarea>
      <div class="hint">快捷键：← → 切换；X 剔除；K 保留；N 下一张未浏览；G 画真实病灶；R 画模型看错区域</div>
      <div style="margin-top:10px; display:flex; flex-direction:column; gap:8px;">
        <button class="primary" id="btn-export-reject">导出剔除 CSV</button>
        <button id="btn-export-all">导出全部评审 CSV</button>
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
        <button class="success" id="btn-keep">保留 (K)</button>
      </div>
      <div class="viewer" id="viewer"><div class="empty">加载中…</div></div>
    </main>
  </div>
  <script id="cases-data" type="application/json">__CASES_JSON__</script>
  <script>
    const META = __META_JSON__;
    const CASES = JSON.parse(document.getElementById("cases-data").textContent);
    const STORAGE_KEY = "gradcam_screening_" + META.storage_key;
    const STAGE_ORDER = ["T1", "T2", "T3", "T4+"];

    let reviews = loadReviews();
    let filtered = [];
    let currentIndex = 0;
    let drawMode = "true";
    let drawing = false;
    let dragStart = null;
    let canvas = null;
    let ctx = null;
    let currentItem = null;
    let pathOk = null;

    function escHtml(s) {
      return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
    }

    function imgErrorHtml(panel) {
      return `<div class="empty">图片加载失败<br><code>${escHtml(panel)}</code><br>请确认 HTML 与 gradcam_test_external_full、gradcam_test_prospective_full 在同一文件夹</div>`;
    }

    function pathErrorHtml(panel) {
      const folder = META.root_folder || "gradcam_test_*_full";
      return `<div class="path-error">
        <h3 style="margin-top:0;">找不到图片，当前 HTML 位置不正确</h3>
        <p>尝试加载：<code>${escHtml(panel)}</code></p>
        <p>请把 <code>gradcam_screening.html</code> 放在 <code>${escHtml(folder)}</code> 文件夹内，与 <code>panels/</code> 同级。</p>
        <p>${escHtml(META.path_help || "")}</p>
        <p>若仍不行，请用 Chrome 打开；或用命令在该目录启动本地服务：<code>python3 -m http.server 8765</code></p>
      </div>`;
    }

    function initPageMode() {
      if (META.mode === "single" && META.fixed_split) {
        const splitEl = document.getElementById("filter-split");
        splitEl.value = META.fixed_split;
        splitEl.disabled = true;
        document.getElementById("split-filter-label")?.classList.add("hidden");
        splitEl.classList.add("hidden");
      }
    }

    function verifyPaths(done) {
      if (pathOk === true) { done(); return; }
      if (!CASES.length) {
        document.getElementById("viewer").innerHTML = `<div class="empty">没有可显示的样本</div>`;
        return;
      }
      const probe = new Image();
      probe.onload = () => { pathOk = true; done(); };
      probe.onerror = () => {
        pathOk = false;
        document.getElementById("viewer").innerHTML = pathErrorHtml(CASES[0].panel);
      };
      probe.src = CASES[0].panel;
    }

    function loadReviews() {
      try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"); }
      catch (e) { return {}; }
    }

    function defaultReview() {
      return {
        viewed: false,
        rejected: false,
        reason: "",
        note: "",
        error_note: "",
        annot_true: [],
        annot_model: [],
        updated_at: "",
      };
    }

    function getReview(id) {
      return { ...defaultReview(), ...(reviews[id] || {}) };
    }

    function saveReviews() {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(reviews));
      refreshStats();
      renderList();
    }

    function stageIndex(name) {
      const i = STAGE_ORDER.indexOf(name);
      return i >= 0 ? i : -1;
    }

    function stageGap(item) {
      const a = stageIndex(item.true);
      const b = stageIndex(item.pred);
      if (a < 0 || b < 0) return 99;
      return Math.abs(a - b);
    }

    function applyFilters() {
      const split = document.getElementById("filter-split").value;
      const status = document.getElementById("filter-status").value;
      const trueName = document.getElementById("filter-true").value;
      const search = document.getElementById("filter-search").value.trim().toLowerCase();
      filtered = CASES.filter((item) => {
        const rev = getReview(item.uid);
        if (split !== "all" && item.split !== split) return false;
        if (trueName !== "all" && item.true !== trueName) return false;
        if (search && !item.id.toLowerCase().includes(search) && !item.uid.toLowerCase().includes(search)) return false;
        if (status === "reject" && !rev.rejected) return false;
        if (status === "keep" && rev.rejected) return false;
        if (status === "unreviewed" && rev.viewed) return false;
        if (status === "wrong" && item.correct) return false;
        if (status === "correct" && !item.correct) return false;
        if (status === "cross" && (item.correct || stageGap(item) <= 1)) return false;
        if (status === "adjacent" && (item.correct || stageGap(item) !== 1)) return false;
        return true;
      });
      if (currentIndex >= filtered.length) currentIndex = Math.max(0, filtered.length - 1);
    }

    function refreshStats() {
      const rejectCount = CASES.filter((c) => getReview(c.uid).rejected).length;
      const reviewedCount = CASES.filter((c) => getReview(c.uid).viewed).length;
      document.getElementById("stat-total").textContent = filtered.length;
      document.getElementById("stat-reject").textContent = rejectCount;
      document.getElementById("stat-reviewed").textContent = reviewedCount;
      document.getElementById("stat-idx").textContent = filtered.length ? `${currentIndex + 1}/${filtered.length}` : "0/0";
    }

    function splitLabel(split) {
      if (split === "test_external") return "外部";
      if (split === "test_prospective") return "前瞻";
      return split;
    }

    function renderList() {
      const list = document.getElementById("thumb-list");
      list.innerHTML = filtered.slice(0, 200).map((item, idx) => {
        const rev = getReview(item.uid);
        const cls = ["list-item", idx === currentIndex ? "active" : "", rev.rejected ? "rejected" : ""].filter(Boolean).join(" ");
        return `<div class="${cls}" data-idx="${idx}">[${splitLabel(item.split)}] ${item.id} | ${item.true}→${item.pred}${rev.rejected ? " [剔除]" : ""}</div>`;
      }).join("");
      if (filtered.length > 200) {
        list.innerHTML += `<div class="list-item">… 还有 ${filtered.length - 200} 条</div>`;
      }
      list.querySelectorAll(".list-item[data-idx]").forEach((el) => {
        el.addEventListener("click", () => { currentIndex = Number(el.dataset.idx); renderCurrent(); });
      });
    }

    window.__imgErr = imgErrorHtml;

    function panelSrc(panel) {
      return encodeURI(panel).replace(/#/g, "%23");
    }

    function buildPanelHtml(item, showAnnot) {
      const src = panelSrc(item.panel);
      const err = item.panel.replace(/'/g, "\\'");
      return `
        ${showAnnot ? `
        <div class="annotate-head">
          <b>误分标注（可选，直接在下方大图上画框）</b>
          <button id="draw-true" class="${drawMode === "true" ? "primary" : ""}">画真实病灶 (G)</button>
          <button id="draw-model" class="${drawMode === "model" ? "primary" : ""}">画模型看错区域 (R)</button>
          <button id="undo-annot">撤销上一框</button>
          <button id="clear-annot">清空标注</button>
          <span class="legend"><span class="g">绿色=真实病灶</span> · <span class="r">红色=模型看错</span></span>
        </div>` : ""}
        <div class="panel-stage" id="panel-stage">
          <div class="panel-inner">
            <img class="panel-img" id="panel-img" src="${src}" alt="${escHtml(item.id)}"
              onerror="document.getElementById('panel-stage').innerHTML=window.__imgErr('${err}')">
            ${showAnnot ? `<canvas id="annot-canvas" class="draw-layer"></canvas>` : ""}
          </div>
        </div>
        ${showAnnot ? `<label style="margin-top:8px;display:block;">误分原因备注</label><textarea id="error-note">${escHtml(getReview(item.uid).error_note || "")}</textarea>` : ""}
      `;
    }

    function setupCanvas() {
      canvas = document.getElementById("annot-canvas");
      if (!canvas) return;
      const box = document.querySelector("#panel-stage .panel-inner") || document.getElementById("panel-stage");
      const resize = () => {
        const rect = box.getBoundingClientRect();
        canvas.width = Math.max(1, Math.floor(rect.width));
        canvas.height = Math.max(1, Math.floor(rect.height));
        canvas.style.width = rect.width + "px";
        canvas.style.height = rect.height + "px";
        redrawAnnotations();
      };
      const img = document.getElementById("panel-img");
      if (img && !img.complete) img.onload = resize;
      resize();
      window.onresize = resize;

      canvas.onmousedown = (e) => {
        if (!currentItem) return;
        drawing = true;
        dragStart = canvasPoint(e);
      };
      canvas.onmousemove = (e) => {
        if (!drawing || !dragStart) return;
        redrawAnnotations();
        const p = canvasPoint(e);
        ctx.save();
        ctx.strokeStyle = drawMode === "true" ? "#22c55e" : "#ef4444";
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 4]);
        ctx.strokeRect(dragStart.x, dragStart.y, p.x - dragStart.x, p.y - dragStart.y);
        ctx.restore();
      };
      canvas.onmouseup = (e) => {
        if (!drawing || !dragStart || !currentItem) return;
        drawing = false;
        const p = canvasPoint(e);
        const rect = normalizeRect(dragStart, p);
        if (rect.w < 0.01 || rect.h < 0.01) { dragStart = null; redrawAnnotations(); return; }
        const rev = getReview(currentItem.uid);
        const target = drawMode === "true" ? "annot_true" : "annot_model";
        rev[target] = [...(rev[target] || []), rect];
        rev.viewed = true;
        rev.updated_at = new Date().toISOString();
        reviews[currentItem.uid] = rev;
        saveReviews();
        dragStart = null;
        redrawAnnotations();
      };
    }

    function canvasPoint(e) {
      const rect = canvas.getBoundingClientRect();
      return {
        x: (e.clientX - rect.left) * (canvas.width / rect.width),
        y: (e.clientY - rect.top) * (canvas.height / rect.height),
      };
    }

    function normalizeRect(a, b) {
      const x1 = Math.min(a.x, b.x) / canvas.width;
      const y1 = Math.min(a.y, b.y) / canvas.height;
      const x2 = Math.max(a.x, b.x) / canvas.width;
      const y2 = Math.max(a.y, b.y) / canvas.height;
      return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
    }

    function redrawAnnotations() {
      if (!canvas) return;
      ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (!currentItem) return;
      const rev = getReview(currentItem.uid);
      (rev.annot_true || []).forEach((r) => drawRect(r, "#22c55e", "真实"));
      (rev.annot_model || []).forEach((r) => drawRect(r, "#ef4444", "看错"));
    }

    function drawRect(r, color, label) {
      const x = r.x * canvas.width;
      const y = r.y * canvas.height;
      const w = r.w * canvas.width;
      const h = r.h * canvas.height;
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, w, h);
      ctx.fillStyle = color;
      ctx.font = "12px sans-serif";
      ctx.fillText(label, x + 4, y + 14);
    }

    function renderCurrent() {
      applyFilters();
      refreshStats();
      renderList();
      const viewer = document.getElementById("viewer");
      const item = filtered[currentIndex];
      currentItem = item || null;
      if (!item) {
        viewer.innerHTML = `<div class="empty">没有符合筛选条件的样本</div>`;
        return;
      }
      const rev = getReview(item.uid);
      rev.viewed = true;
      reviews[item.uid] = rev;
      saveReviews();

      document.getElementById("reject-note").value = rev.note || "";
      if (rev.reason) document.getElementById("reject-reason").value = rev.reason;

      const gap = stageGap(item);
      const gapText = item.correct ? "—" : (gap > 1 ? `跨级 Δ=${gap}` : "相邻误分");
      const statusTag = rev.rejected ? `<span class="tag reject">已剔除</span>` : `<span class="tag ok">保留</span>`;
      const correctTag = item.correct ? `<span class="tag ok">预测正确</span>` : `<span class="tag bad">预测错误 · ${gapText}</span>`;

      const probs = STAGE_ORDER.map((name) => {
        const val = (item.probs && item.probs[name]) ? item.probs[name] : 0;
        const classes = ["prob"];
        if (name === item.pred) classes.push("active");
        if (name === item.true) classes.push("true-hit");
        return `<div class="${classes.join(" ")}"><span>${name}</span><b>${(val * 100).toFixed(1)}%</b></div>`;
      }).join("");

      const showAnnot = !item.correct && !rev.rejected;
      viewer.innerHTML = `
        <div class="info">
          <div><b>${item.id}</b></div>
          <span class="tag split">${splitLabel(item.split)}</span>
          <div>真实 <b>${item.true}</b> → 预测 <b>${item.pred}</b></div>
          ${statusTag} ${correctTag}
        </div>
        <div class="probs">${probs}</div>
        ${buildPanelHtml(item, showAnnot)}
      `;

      const errNote = document.getElementById("error-note");
      if (errNote) {
        errNote.addEventListener("change", () => {
          const r = getReview(item.uid);
          r.error_note = errNote.value.trim();
          r.updated_at = new Date().toISOString();
          reviews[item.uid] = r;
          saveReviews();
        });
      }
      const bind = (id, fn) => { const el = document.getElementById(id); if (el) el.onclick = fn; };
      bind("draw-true", () => { drawMode = "true"; renderCurrent(); });
      bind("draw-model", () => { drawMode = "model"; renderCurrent(); });
      bind("undo-annot", () => {
        const r = getReview(item.uid);
        const key = drawMode === "true" ? "annot_true" : "annot_model";
        r[key] = (r[key] || []).slice(0, -1);
        reviews[item.uid] = r;
        saveReviews();
        redrawAnnotations();
      });
      bind("clear-annot", () => {
        if (!confirm("清空当前图的所有标注框？")) return;
        const r = getReview(item.uid);
        r.annot_true = [];
        r.annot_model = [];
        reviews[item.uid] = r;
        saveReviews();
        redrawAnnotations();
      });
      setupCanvas();
    }

    function persistSidebarFields(rejected) {
      const item = filtered[currentIndex];
      if (!item) return;
      reviews[item.uid] = {
        ...getReview(item.uid),
        viewed: true,
        rejected,
        reason: rejected ? document.getElementById("reject-reason").value : "",
        note: document.getElementById("reject-note").value.trim(),
        error_note: (document.getElementById("error-note") || {}).value?.trim?.() || getReview(item.uid).error_note || "",
        updated_at: new Date().toISOString(),
      };
      saveReviews();
    }

    function markReject() { persistSidebarFields(true); goNext(); }
    function markKeep() { persistSidebarFields(false); renderCurrent(); }

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
        if (!getReview(filtered[idx].uid).viewed) { currentIndex = idx; renderCurrent(); return; }
      }
      goNext();
    }

    function reviewToRow(item) {
      const rev = getReview(item.uid);
      return {
        uid: item.uid,
        filename: item.id,
        split: item.split,
        true_name: item.true,
        pred_name: item.pred,
        correct: item.correct ? "1" : "0",
        stage_gap: item.correct ? "0" : String(stageGap(item)),
        rejected: rev.rejected ? "1" : "0",
        reject_reason: rev.reason || "",
        note: rev.note || "",
        error_note: rev.error_note || "",
        annot_true: JSON.stringify(rev.annot_true || []),
        annot_model: JSON.stringify(rev.annot_model || []),
        panel: item.panel,
        updated_at: rev.updated_at || "",
      };
    }

    function downloadCsv(filename, rows) {
      const header = Object.keys(rows[0] || {});
      const body = rows.map((row) => header.map((k) => `"${String(row[k] ?? "").replace(/"/g, '""')}"`).join(","));
      const csv = ["\ufeff" + header.join(",")].concat(body).join("\n");
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    }

    document.getElementById("btn-prev").onclick = goPrev;
    document.getElementById("btn-next").onclick = goNext;
    document.getElementById("btn-next-unreviewed").onclick = goNextUnreviewed;
    document.getElementById("btn-reject").onclick = markReject;
    document.getElementById("btn-keep").onclick = markKeep;
    document.getElementById("btn-export-reject").onclick = () => {
      const rows = CASES.map(reviewToRow).filter((r) => r.rejected === "1");
      if (!rows.length) { alert("暂无剔除样本"); return; }
      downloadCsv("gradcam_rejected.csv", rows);
    };
    document.getElementById("btn-export-all").onclick = () => {
      const rows = CASES.map(reviewToRow).filter((r) => r.rejected === "1" || r.error_note || r.annot_true !== "[]" || r.annot_model !== "[]");
      downloadCsv("gradcam_review_export.csv", rows.length ? rows : CASES.map(reviewToRow));
    };
    document.getElementById("btn-clear-storage").onclick = () => {
      if (confirm("确定清空所有本地标记？")) { localStorage.removeItem(STORAGE_KEY); reviews = {}; renderCurrent(); }
    };
    ["filter-split", "filter-status", "filter-true"].forEach((id) => {
      document.getElementById(id).addEventListener("change", () => { currentIndex = 0; renderCurrent(); });
    });
    document.getElementById("filter-search").addEventListener("input", () => { currentIndex = 0; renderCurrent(); });

    document.addEventListener("keydown", (e) => {
      if (e.target.tagName === "TEXTAREA" || (e.target.tagName === "INPUT" && e.target.id === "filter-search")) return;
      if (e.key === "ArrowLeft") goPrev();
      if (e.key === "ArrowRight") goNext();
      if (e.key.toLowerCase() === "x") markReject();
      if (e.key.toLowerCase() === "k") markKeep();
      if (e.key.toLowerCase() === "n") goNextUnreviewed();
      if (e.key.toLowerCase() === "g") { drawMode = "true"; renderCurrent(); }
      if (e.key.toLowerCase() === "r") { drawMode = "model"; renderCurrent(); }
    });

    initPageMode();
    verifyPaths(() => renderCurrent());
  </script>
</body>
</html>
"""


def rel_asset_path(asset_path: object, root_dir: Path) -> str | None:
    if asset_path is None or (isinstance(asset_path, float) and pd.isna(asset_path)):
        return None
    raw = str(asset_path).strip()
    if not raw:
        return None
    path = Path(raw)
    if path.is_file():
        try:
            return path.relative_to(root_dir.resolve()).as_posix()
        except ValueError:
            pass
    normalized = raw.replace("\\", "/")
    root_name = root_dir.name
    marker = f"{root_name}/"
    if marker in normalized:
        return normalized.split(marker, 1)[1]
    if normalized.startswith("panels/"):
        return normalized
    return path.name


def row_to_case(row: pd.Series, root_dir: Path, split: str, path_prefix: str) -> dict | None:
    panel_abs = row.get("panel_path")
    panel = rel_asset_path(panel_abs, root_dir)
    if not panel:
        return None
    if path_prefix:
        panel = f"{path_prefix.rstrip('/')}/{panel}"

    filename = str(row.get("filename") or Path(str(panel_abs)).stem.replace("_panel", ""))
    probs: dict[str, float] = {}
    for name in ("T1", "T2", "T3", "T4+"):
        col = f"prob_{name}"
        if col in row and pd.notna(row[col]):
            probs[name] = float(row[col])

    correct_raw = row.get("correct", False)
    correct = str(correct_raw).strip().lower() in {"1", "true", "t", "yes"}
    uid = f"{split}::{filename}"
    return {
        "uid": uid,
        "id": filename,
        "split": split,
        "panel": panel,
        "true": str(row.get("true_name", "")),
        "pred": str(row.get("pred_name", "")),
        "correct": correct,
        "probs": probs,
    }


def build_cases_from_csv(
    results_csv: Path,
    split: str,
    root_dir: Path | None = None,
    path_prefix: str = "",
    *,
    external_holdout_only: bool = False,
) -> list[dict]:
    root = (root_dir or results_csv.parent).resolve()
    df = pd.read_csv(results_csv, low_memory=False)
    if split == "test_external" and external_holdout_only:
        mask = ~df["image_path"].astype(str).str.contains("prospective", case=False, na=False)
        df = df.loc[mask].copy()
    cases: list[dict] = []
    for _, row in df.iterrows():
        case = row_to_case(row, root, split, path_prefix)
        if case is not None:
            cases.append(case)
    return cases


def build_unified_html(
    sources: list[dict],
    output_html: Path,
    *,
    title: str = "GradCAM 测试集筛图",
    subtitle: str | None = None,
    storage_key: str = "unified_v2",
    mode: str = "unified",
    fixed_split: str | None = None,
    root_folder: str | None = None,
    path_help: str | None = None,
) -> dict:
    """Build one HTML from one or more gradcam_results.csv sources."""
    all_cases: list[dict] = []
    split_counts: dict[str, int] = {}
    for src in sources:
        csv_path = Path(src["results_csv"]).resolve()
        split = str(src["split"])
        root_dir = Path(src.get("root_dir", csv_path.parent)).resolve()
        prefix = str(src.get("path_prefix", ""))
        cases = build_cases_from_csv(
            csv_path,
            split,
            root_dir,
            prefix,
            external_holdout_only=bool(src.get("external_holdout_only", False)),
        )
        all_cases.extend(cases)
        split_counts[split] = len(cases)

    if not all_cases:
        raise SystemExit("No cases with valid panel_path found in any source CSV.")

    if subtitle is None:
        if mode == "single" and root_folder:
            subtitle = (
                f"将本 HTML 放在 <code>{root_folder}</code> 文件夹内（与 <code>panels/</code> 同级），双击打开。"
            )
        else:
            subtitle = (
                "将本 HTML 与 <code>gradcam_test_external_full</code>、"
                "<code>gradcam_test_prospective_full</code> 放在<strong>同一文件夹</strong>下，双击打开。"
            )

    meta = {
        "title": title,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "total": len(all_cases),
        "split_counts": split_counts,
        "storage_key": storage_key,
        "mode": mode,
        "fixed_split": fixed_split,
        "root_folder": root_folder,
        "path_help": path_help or "",
    }
    html_text = (
        HTML_TEMPLATE.replace("__PAGE_TITLE__", title)
        .replace("__PAGE_SUBTITLE__", subtitle)
        .replace("__CASES_JSON__", json.dumps(all_cases, ensure_ascii=False))
        .replace("__META_JSON__", json.dumps(meta, ensure_ascii=False))
    )
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html_text, encoding="utf-8")
    return {
        "html": str(output_html),
        "cases": len(all_cases),
        "split_counts": split_counts,
    }


SPLIT_HTML_SPECS = {
    "test_external": {
        "title": "GradCAM 外部测试筛图",
        "storage_key": "gradcam_screening_test_external_v2",
        "dir_name": "gradcam_test_external_full",
    },
    "test_prospective": {
        "title": "GradCAM 2025前瞻全量筛图",
        "storage_key": "gradcam_screening_test_prospective_2025_full_v1",
        "dir_name": "gradcam_test_prospective_full",
    },
}


def build_split_screening_html(source: dict, output_html: Path) -> dict:
    split = str(source["split"])
    spec = SPLIT_HTML_SPECS.get(split, {})
    root_dir = Path(source.get("root_dir", Path(source["results_csv"]).parent)).resolve()
    return build_unified_html(
        [{**source, "path_prefix": ""}],
        output_html,
        title=spec.get("title", f"GradCAM {split} 筛图"),
        storage_key=spec.get("storage_key", f"{split}_v2"),
        mode="single",
        fixed_split=split,
        root_folder=spec.get("dir_name", root_dir.name),
        path_help="单数据集 HTML 的标注与统一版分开保存，互不影响。",
    )


def build_html(
    results_csv: Path,
    output_html: Path,
    split: str,
    root_dir: Path | None = None,
) -> dict:
    """Backward-compatible single-split builder."""
    root = (root_dir or results_csv.parent).resolve()
    return build_split_screening_html(
        {"results_csv": results_csv, "split": split, "root_dir": root},
        output_html,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build offline Grad-CAM screening HTML")
    parser.add_argument("--results-csv", type=Path, action="append", help="gradcam_results.csv (repeatable)")
    parser.add_argument("--split", type=str, action="append", help="Split label aligned with --results-csv")
    parser.add_argument("--root-dir", type=Path, action="append", help="Optional root dir per CSV")
    parser.add_argument("--path-prefix", type=str, action="append", help="Relative path prefix in HTML, default root dir name")
    parser.add_argument(
        "--output-html",
        type=Path,
        default=None,
        help="Output HTML path (default: gradcam_screening.html beside first csv or --pack-root)",
    )
    parser.add_argument("--pack-root", type=Path, default=None, help="Write unified HTML to pack_root/gradcam_screening.html")
    parser.add_argument(
        "--exp-dir",
        type=Path,
        default=None,
        help="Experiment dir: auto-load external + prospective gradcam outputs",
    )
    return parser.parse_args()


def default_sources_from_exp(exp_dir: Path) -> list[dict]:
    specs = [
        ("test_external", "gradcam_test_external_full"),
        ("test_prospective", "gradcam_test_prospective_full"),
    ]
    sources: list[dict] = []
    for split, dirname in specs:
        root = exp_dir / dirname
        csv_path = root / "gradcam_results.csv"
        if csv_path.is_file():
            sources.append(
                {
                    "results_csv": csv_path,
                    "split": split,
                    "root_dir": root,
                    "path_prefix": dirname,
                }
            )
    return sources


def main() -> None:
    args = parse_args()
    sources: list[dict] = []

    if args.exp_dir is not None:
        sources = default_sources_from_exp(args.exp_dir.resolve())
    elif args.results_csv:
        splits = args.split or ["test_set"] * len(args.results_csv)
        roots = args.root_dir or [None] * len(args.results_csv)
        prefixes = args.path_prefix or [None] * len(args.results_csv)
        if len(splits) != len(args.results_csv):
            raise SystemExit("--split count must match --results-csv count")
        for csv_path, split, root, prefix in zip(args.results_csv, splits, roots, prefixes):
            root_dir = root or csv_path.parent
            sources.append(
                {
                    "results_csv": csv_path,
                    "split": split,
                    "root_dir": root_dir,
                    "path_prefix": prefix or root_dir.name,
                }
            )
    else:
        raise SystemExit("Provide --exp-dir or at least one --results-csv")

    if args.output_html is not None:
        output_html = args.output_html
    elif args.pack_root is not None:
        output_html = args.pack_root / "gradcam_screening.html"
    elif sources:
        output_html = Path(sources[0]["results_csv"]).parent.parent / "gradcam_test_sets_pack" / "gradcam_screening.html"
    else:
        raise SystemExit("Cannot infer output HTML path")

    summary = build_unified_html(sources, output_html)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
