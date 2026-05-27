#!/usr/bin/env python3
"""Build a standalone offline HTML viewer for Grad-CAM test-set image screening."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DEFAULT_CHUNK_SIZE = 350
SCREENING_DATA_DIR = "screening_data"
SYNC_CSV_NAME = "gradcam_review_sync.csv"
SYNC_JSON_NAME = "gradcam_review_sync.json"
SYNC_CSV_HEADER = (
    "uid,filename,split,true_name,pred_name,correct,stage_gap,viewed,rejected,"
    "reject_reason,note,error_note,annot_true,annot_model,panel,updated_at"
)

HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__PAGE_TITLE__</title>
  <style>
    :root {
      --bg: #000000;
      --glass: rgba(255, 255, 255, 0.05);
      --glass2: rgba(255, 255, 255, 0.08);
      --glass3: rgba(255, 255, 255, 0.11);
      --panel: rgba(255, 255, 255, 0.06);
      --panel2: rgba(255, 255, 255, 0.09);
      --border: rgba(255, 255, 255, 0.12);
      --border-strong: rgba(255, 255, 255, 0.2);
      --text: #f5f5f7;
      --muted: #a1a1aa;
      --ok: #34d399;
      --bad: #f87171;
      --warn: #fbbf24;
      --accent: #7eb8ff;
      --accent2: #a5b4fc;
      --true-color: #22c55e;
      --wrong-color: #ef4444;
      --sidebar-w: 340px;
      --topbar-h: 58px;
      --radius: 14px;
      --radius-lg: 18px;
      --blur: 24px;
      --shadow: 0 8px 32px rgba(0, 0, 0, 0.55);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background:
        radial-gradient(ellipse 70% 50% at 15% -10%, rgba(96, 165, 250, 0.14), transparent 55%),
        radial-gradient(ellipse 55% 45% at 85% 110%, rgba(52, 211, 153, 0.08), transparent 50%),
        var(--bg);
      color: var(--text);
      height: 100vh;
      overflow: hidden;
    }
    .app { display: flex; flex-direction: column; height: 100vh; }
    .topbar {
      height: var(--topbar-h);
      min-height: var(--topbar-h);
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 0 16px;
      background: rgba(0, 0, 0, 0.45);
      backdrop-filter: blur(var(--blur));
      -webkit-backdrop-filter: blur(var(--blur));
      border-bottom: 1px solid var(--border);
      box-shadow: var(--shadow);
      z-index: 100;
    }
    .brand { min-width: 160px; }
    .brand h1 { font-size: 15px; margin: 0; font-weight: 700; letter-spacing: .02em; }
    .brand .sub { color: var(--muted); font-size: 11px; display: none; }
    .dataset-tabs {
      flex: 1;
      display: flex;
      gap: 8px;
      overflow-x: auto;
      padding: 4px 0;
    }
    .dataset-tab {
      flex: 1;
      min-width: 140px;
      max-width: 220px;
      background: var(--glass);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 8px 12px;
      cursor: pointer;
      text-align: left;
      transition: border-color .15s, background .15s;
    }
    .dataset-tab:hover { background: var(--glass2); border-color: var(--border-strong); }
    .dataset-tab.active {
      border-color: rgba(126, 184, 255, 0.55);
      background: rgba(126, 184, 255, 0.12);
      box-shadow: inset 0 0 0 1px rgba(126, 184, 255, 0.2);
    }
    .dataset-tab .tab-title { font-size: 13px; font-weight: 600; display: block; }
    .dataset-tab .tab-meta { font-size: 11px; color: var(--muted); margin-top: 2px; }
    .dataset-tab .tab-bar {
      height: 4px; background: rgba(255, 255, 255, 0.08); border-radius: 99px; margin-top: 6px; overflow: hidden;
    }
    .dataset-tab .tab-bar i {
      display: block; height: 100%; background: linear-gradient(90deg, var(--accent), var(--ok));
      transition: width .3s;
    }
    .topbar-actions { display: flex; gap: 6px; align-items: center; flex-shrink: 0; }
    .topbar-actions button, .seg-btn {
      border: 1px solid var(--border);
      background: var(--glass);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      color: var(--text);
      border-radius: 10px;
      padding: 7px 11px;
      cursor: pointer;
      font-size: 12px;
    }
    .topbar-actions button:hover { background: var(--glass2); border-color: var(--border-strong); }
    .topbar-actions button.active { outline: 1px solid rgba(126, 184, 255, 0.5); background: rgba(126, 184, 255, 0.14); }
    .topbar-progress {
      font-size: 13px;
      font-weight: 700;
      color: var(--ok);
      background: rgba(52,211,153,.12);
      border: 1px solid rgba(52,211,153,.35);
      border-radius: 999px;
      padding: 6px 12px;
      white-space: nowrap;
    }
    .workspace {
      flex: 1;
      display: grid;
      grid-template-columns: var(--sidebar-w) 1fr;
      min-height: 0;
    }
    .workspace.sidebar-collapsed { grid-template-columns: 0 1fr; }
    aside.sidebar {
      background: rgba(0, 0, 0, 0.35);
      backdrop-filter: blur(var(--blur));
      -webkit-backdrop-filter: blur(var(--blur));
      border-right: 1px solid var(--border);
      overflow-y: auto;
      overflow-x: hidden;
      padding: 14px;
      min-width: 0;
    }
    .workspace.sidebar-collapsed aside { padding: 0; border: none; overflow: hidden; }
    main {
      display: flex;
      flex-direction: column;
      min-width: 0;
      min-height: 0;
      background: transparent;
    }
    .section-card {
      background: var(--glass);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 12px 14px;
      margin-bottom: 12px;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06);
    }
    .section-card.highlight {
      border-color: rgba(126, 184, 255, 0.35);
      background: rgba(126, 184, 255, 0.08);
    }
    .section-card h2 {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: .06em;
      color: var(--muted);
      margin: 0 0 8px;
      font-weight: 600;
    }
    label { display: block; font-size: 12px; color: var(--muted); margin: 8px 0 4px; }
    select, input[type="text"], input[type="number"], textarea {
      width: 100%;
      background: rgba(0, 0, 0, 0.35);
      backdrop-filter: blur(8px);
      -webkit-backdrop-filter: blur(8px);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 8px 10px;
      font-size: 13px;
    }
    textarea { min-height: 56px; resize: vertical; }
    .stats {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
    }
    .stat {
      background: var(--glass);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 10px 12px;
    }
    .stat b { display: block; font-size: 20px; font-weight: 700; color: #e2e8f0; }
    .stat span { font-size: 10px; color: var(--muted); }
    .filter-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .filter-chips button {
      font-size: 12px;
      padding: 5px 10px;
      border-radius: 999px;
    }
    .filter-chips button.active {
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 10px 16px;
      border-bottom: 1px solid var(--border);
      background: rgba(0, 0, 0, 0.35);
      backdrop-filter: blur(var(--blur));
      -webkit-backdrop-filter: blur(var(--blur));
      align-items: center;
    }
    button {
      border: 1px solid var(--border);
      background: var(--glass2);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
      color: var(--text);
      border-radius: 10px;
      padding: 8px 12px;
      cursor: pointer;
      font-size: 13px;
      transition: background .15s, border-color .15s;
    }
    button:hover { background: var(--glass3); border-color: var(--border-strong); }
    button.primary { background: rgba(37, 99, 235, 0.55); border-color: rgba(96, 165, 250, 0.5); }
    button.danger { background: rgba(180, 35, 24, 0.55); border-color: rgba(248, 113, 113, 0.45); }
    button.success { background: rgba(6, 118, 71, 0.55); border-color: rgba(52, 211, 153, 0.45); }
    button:disabled { opacity: 0.45; cursor: not-allowed; }
    .viewer {
      flex: 1;
      overflow: auto;
      padding: 12px 16px 20px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .info {
      background: var(--glass);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--border);
      border-radius: var(--radius);
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
      background: var(--glass);
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 8px 10px;
      font-size: 12px;
    }
    .prob b { display: block; font-size: 16px; margin-top: 4px; }
    .prob.active { outline: 2px solid var(--accent); }
    .prob.true-hit { box-shadow: inset 0 0 0 1px var(--ok); }
    .panel-stage {
      position: relative;
      width: 100%;
      max-width: 100%;
      margin: 0 auto;
      background: #000;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-lg);
      overflow: auto;
      min-height: calc(100vh - 240px);
      max-height: calc(100vh - 200px);
      box-shadow: var(--shadow);
    }
    .panel-stage.zoom-fit .panel-img { min-width: 0; width: 100%; }
    .panel-stage.zoom-150 .panel-inner { transform: scale(1.5); transform-origin: top center; }
    .panel-stage.zoom-200 .panel-inner { transform: scale(2); transform-origin: top center; }
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
    .path-error, .load-box {
      padding: 24px;
      line-height: 1.7;
      background: #2a1215;
      border: 1px solid #7f1d1d;
      border-radius: 10px;
      max-width: 900px;
      margin: 24px auto;
    }
    .load-box {
      background: var(--glass);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border-color: var(--border);
      color: var(--text);
    }
    .load-bar {
      height: 8px;
      background: rgba(255, 255, 255, 0.08);
      border-radius: 999px;
      overflow: hidden;
      margin-top: 12px;
    }
    .load-bar > i {
      display: block;
      height: 100%;
      width: 0%;
      background: var(--accent);
      transition: width 0.2s ease;
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
      max-height: 220px;
      overflow-y: auto;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: rgba(0, 0, 0, 0.35);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
    }
    .list-item {
      padding: 8px 10px;
      border-bottom: 1px solid var(--border);
      font-size: 12px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .list-item .dot {
      width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
      background: #475569;
    }
    .list-item .dot.reject { background: var(--warn); }
    .list-item .dot.done { background: var(--ok); }
    .list-item:hover { background: rgba(255, 255, 255, 0.06); }
    .list-item.active { background: rgba(126, 184, 255, 0.14); border-left: 3px solid var(--accent); }
    .list-item.rejected { color: #fcd34d; }
    .hint { font-size: 11px; color: var(--muted); line-height: 1.5; margin-top: 8px; }
    .empty { padding: 36px; text-align: center; color: var(--muted); }
    .hidden { display: none !important; }
    .progress-wrap {
      padding: 8px 14px 0;
      background: var(--panel);
      border-bottom: 1px solid var(--border);
    }
    .progress-label {
      display: flex;
      justify-content: space-between;
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 6px;
    }
    .toolbar-large button {
      font-size: 15px;
      padding: 12px 18px;
      min-width: 110px;
      font-weight: 600;
    }
    .toolbar-large .btn-reject { font-size: 16px; min-width: 120px; }
    .toolbar-large .btn-keep { min-width: 120px; }
    .action-dock {
      display: none;
      position: fixed;
      bottom: 28px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 800;
      gap: 14px;
      padding: 10px 14px;
      background: rgba(0, 0, 0, 0.55);
      border: 1px solid var(--border-strong);
      border-radius: 999px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(var(--blur));
      -webkit-backdrop-filter: blur(var(--blur));
    }
    .action-dock button {
      min-width: 130px;
      font-size: 16px;
      font-weight: 700;
      padding: 14px 22px;
      border-radius: 999px;
    }
    @media (min-width: 900px) {
      .workspace:not(.sidebar-collapsed) .action-dock { display: flex; }
    }
    .sync-steps {
      display: grid;
      gap: 8px;
      margin-bottom: 10px;
    }
    .sync-step {
      display: flex;
      gap: 10px;
      align-items: flex-start;
      font-size: 12px;
      line-height: 1.55;
      padding: 8px 10px;
      background: rgba(255, 255, 255, 0.04);
      border-radius: 10px;
      border: 1px dashed var(--border);
    }
    .sync-step-num {
      flex-shrink: 0;
      width: 22px;
      height: 22px;
      border-radius: 50%;
      background: var(--accent);
      color: #fff;
      font-weight: 700;
      font-size: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .sync-filenames {
      font-size: 11px;
      color: var(--muted);
      margin-top: 4px;
    }
    .sync-filenames code { color: var(--accent); font-size: 11px; }
    .btn-stack { display: flex; flex-direction: column; gap: 8px; }
    .btn-stack button { width: 100%; text-align: left; }
    .merge-hint {
      font-size: 11px;
      color: var(--muted);
      line-height: 1.55;
      margin-top: 8px;
      padding: 8px 10px;
      background: rgba(15,23,42,.5);
      border-radius: 8px;
    }
    .quick-reasons {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      padding: 0 14px 10px;
      background: rgba(0, 0, 0, 0.25);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
    }
    .quick-reasons button {
      font-size: 12px;
      padding: 6px 10px;
    }
    .doctor-banner {
      background: var(--glass);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 10px 14px;
      font-size: 13px;
      line-height: 1.6;
      margin-bottom: 8px;
    }
    .doctor-banner b { color: var(--accent); }
    .info-large {
      font-size: 15px;
      padding: 12px 16px;
    }
    .info-large .filename { font-size: 16px; font-weight: 700; }
    .toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: rgba(0, 0, 0, 0.65);
      backdrop-filter: blur(var(--blur));
      -webkit-backdrop-filter: blur(var(--blur));
      border: 1px solid var(--border-strong);
      color: var(--text);
      padding: 12px 18px;
      border-radius: var(--radius);
      font-size: 14px;
      z-index: 9999;
      opacity: 0;
      transform: translateY(8px);
      transition: opacity 0.2s, transform 0.2s;
      pointer-events: none;
    }
    .toast.show { opacity: 1; transform: translateY(0); }
    .panel-toolbar {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
      margin-bottom: 6px;
    }
    .panel-stage.zoom-fit .panel-img { min-width: 0; width: 100%; }
    .panel-stage.is-fullscreen {
      position: fixed;
      inset: 0;
      z-index: 9000;
      max-width: none;
      max-height: none;
      min-height: 100vh;
      border-radius: 0;
    }
    details.advanced { margin-top: 8px; }
    details.advanced summary {
      cursor: pointer;
      font-size: 12px;
      color: var(--muted);
      user-select: none;
    }
    .mode-toggle { display: none; }
    .modal-overlay {
      position: fixed; inset: 0;
      background: rgba(0, 0, 0, 0.72);
      backdrop-filter: blur(8px);
      -webkit-backdrop-filter: blur(8px);
      z-index: 10000; display: flex; align-items: center; justify-content: center;
      padding: 20px;
    }
    .modal-overlay.hidden { display: none; }
    .modal-box {
      background: rgba(20, 20, 20, 0.75);
      backdrop-filter: blur(var(--blur));
      -webkit-backdrop-filter: blur(var(--blur));
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-lg);
      padding: 20px 24px;
      max-width: 520px;
      width: 100%;
      max-height: 80vh;
      overflow-y: auto;
      box-shadow: var(--shadow);
    }
    .modal-box h2 { margin: 0 0 12px; font-size: 18px; }
    .modal-box kbd {
      background: rgba(255, 255, 255, 0.08); border: 1px solid var(--border);
      border-radius: 6px; padding: 2px 6px; font-size: 12px;
    }
    .modal-box table { width: 100%; font-size: 13px; border-collapse: collapse; }
    .modal-box td { padding: 6px 4px; border-bottom: 1px solid var(--border); }
    .folder-badge {
      display: inline-flex; align-items: center; gap: 6px;
      background: rgba(96,165,250,.12); border: 1px solid rgba(96,165,250,.3);
      color: var(--accent); padding: 4px 10px; border-radius: 999px;
      font-size: 12px; font-weight: 600;
    }
    .main-progress {
      padding: 14px 18px 12px;
      background: rgba(0, 0, 0, 0.35);
      backdrop-filter: blur(var(--blur));
      -webkit-backdrop-filter: blur(var(--blur));
      border-bottom: 1px solid var(--border);
    }
    .progress-hero {
      display: grid;
      grid-template-columns: 88px 1fr;
      gap: 16px;
      align-items: center;
      margin-bottom: 10px;
    }
    .progress-ring {
      width: 88px;
      height: 88px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      background: conic-gradient(var(--ok) calc(var(--pct, 0) * 1%), rgba(255, 255, 255, 0.08) 0);
      position: relative;
      box-shadow: 0 0 0 4px rgba(52,211,153,.15);
    }
    .progress-ring::after {
      content: "";
      position: absolute;
      inset: 10px;
      border-radius: 50%;
      background: rgba(0, 0, 0, 0.85);
    }
    .progress-ring span {
      position: relative;
      z-index: 1;
      font-size: 20px;
      font-weight: 800;
      color: var(--text);
    }
    .hero-metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
    }
    .hero-metric {
      background: var(--glass);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 8px 10px;
      text-align: center;
    }
    .hero-metric b { display: block; font-size: 22px; font-weight: 800; line-height: 1.1; }
    .hero-metric span { font-size: 11px; color: var(--muted); }
    .hero-metric.reject b { color: #fbbf24; }
    .hero-metric.remaining b { color: var(--accent); }
    .progress-label { font-size: 13px; }
    .progress-bar {
      height: 14px;
      background: rgba(255, 255, 255, 0.08);
      border-radius: 999px;
      overflow: hidden;
      margin-bottom: 4px;
      border: 1px solid var(--border);
    }
    .progress-bar > i {
      display: block;
      height: 100%;
      background: linear-gradient(90deg, #2563eb, #3ecf8e);
      transition: width 0.35s ease;
    }
    .save-indicator {
      font-size: 11px;
      color: var(--ok);
      opacity: 0;
      transition: opacity .3s;
    }
    .save-indicator.show { opacity: 1; }
    .patient-row {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .patient-id {
      font-size: 22px;
      font-weight: 700;
      letter-spacing: .04em;
      color: var(--text);
    }
    .stage-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
    .stage-chips button {
      font-size: 11px;
      padding: 4px 10px;
      border-radius: 999px;
    }
    .stage-chips button.active { background: var(--accent2); border-color: var(--accent2); }
    .panel-overlay {
      position: absolute;
      top: 12px;
      right: 12px;
      z-index: 5;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .overlay-badge {
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 700;
      backdrop-filter: blur(6px);
    }
    .overlay-badge.reject { background: rgba(180,35,24,.85); color: #fff; }
    .overlay-badge.keep { background: rgba(6,118,71,.85); color: #fff; }
    .summary-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin: 12px 0;
    }
    .summary-card {
      background: var(--glass);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 12px;
    }
    .summary-card h3 { margin: 0 0 8px; font-size: 14px; }
    .summary-card .num { font-size: 24px; font-weight: 700; }
    .welcome-banner {
      background: rgba(126, 184, 255, 0.1);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid rgba(126, 184, 255, 0.3);
      border-radius: 10px;
      padding: 10px 12px;
      font-size: 12px;
      line-height: 1.6;
      margin-bottom: 10px;
    }
    .sync-status {
      font-size: 11px;
      color: var(--muted);
      line-height: 1.5;
      padding: 8px 10px;
      background: rgba(0, 0, 0, 0.35);
      border-radius: 10px;
      border: 1px solid var(--border);
      margin-bottom: 8px;
    }
    .sync-status.ok { border-color: rgba(52,211,153,.4); color: var(--ok); }
    .sync-status.warn { border-color: rgba(251,191,36,.4); color: var(--warn); }
    @media (max-width: 1100px) {
      .workspace { grid-template-columns: 1fr; }
      .workspace:not(.sidebar-collapsed) aside {
        position: fixed; left: 0; top: var(--topbar-h); bottom: 0;
        width: min(320px, 88vw); z-index: 200; box-shadow: var(--shadow);
      }
      .panel-img { min-width: 0; }
      .dataset-tab { min-width: 120px; }
    }
  </style>
</head>
<body>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <h1>超声图像质量筛图</h1>
        <div class="sub" id="page-subtitle">__PAGE_SUBTITLE__</div>
      </div>
      <nav class="dataset-tabs" id="dataset-tabs" aria-label="数据集切换"></nav>
      <div class="topbar-actions">
        <span class="topbar-progress" id="topbar-progress">总进度 0%</span>
        <span class="save-indicator" id="save-indicator">已保存</span>
        <button id="btn-summary" title="进度总览">总览</button>
        <button id="btn-help" title="快捷键帮助">帮助</button>
        <button id="btn-toggle-sidebar" title="显示/隐藏侧栏">侧栏</button>
      </div>
    </header>
    <div class="workspace" id="workspace">
      <aside class="sidebar" id="sidebar">
        <div class="welcome-banner hidden" id="welcome-banner">
          <button id="btn-dismiss-welcome">知道了</button>
          请打开<strong>本文件夹根目录</strong>的 <code>gradcam_screening.html</code>（不是子文件夹里的旧版）。
          顶部标签可切换「外部测试 / 2025前瞻」，按 <kbd>X</kbd> 剔除、<kbd>K</kbd> 保留。
        </div>
        <div class="section-card highlight" style="order:-2">
          <h2>当前进度</h2>
          <div class="stats">
            <div class="stat"><b id="stat-reviewed-pct">0%</b><span>已浏览</span></div>
            <div class="stat"><b id="stat-reject">0</b><span>已剔除</span></div>
            <div class="stat"><b id="stat-remaining">0</b><span>未浏览</span></div>
            <div class="stat"><b id="stat-idx">0/0</b><span>当前列表</span></div>
          </div>
          <div class="hint" id="scope-hint">切换顶部标签可查看各数据集进度</div>
        </div>
        <div class="section-card" style="order:-1">
          <h2>筛选</h2>
          <div class="filter-chips" id="filter-chips">
            <button data-status="unreviewed" class="active">未浏览</button>
            <button data-status="all">全部</button>
            <button data-status="reject">已剔除</button>
            <button data-status="keep">已保留</button>
          </div>
          <label>T 分期（可选）</label>
          <div class="stage-chips" id="stage-chips">
            <button data-stage="all" class="active">全部</button>
            <button data-stage="T1">T1</button>
            <button data-stage="T2">T2</button>
            <button data-stage="T3">T3</button>
            <button data-stage="T4+">T4+</button>
          </div>
          <label>搜索患者号 / 文件名</label>
          <input id="filter-search" type="text" placeholder="输入后回车跳转">
          <label>跳转到序号（当前列表）</label>
          <input id="jump-index" type="number" min="1" placeholder="例如 1200">
        </div>
        <div class="section-card">
          <h2>剔除原因</h2>
          <select id="reject-reason">
            <option value="图像质量差-胃壁层次不清">胃壁层次不清</option>
            <option value="图像质量差-伪影/遮挡">伪影 / 遮挡</option>
            <option value="图像质量差-其他">其他质量问题</option>
            <option value="暂不确定">暂不确定</option>
          </select>
          <label>备注（可选）</label>
          <textarea id="reject-note" placeholder="可选备注"></textarea>
        </div>
        <details class="advanced">
          <summary>高级筛选（算法组）</summary>
          <select id="filter-split" class="hidden">
            <option value="all">全部</option>
            <option value="test_external">外部测试</option>
            <option value="test_prospective">前瞻测试</option>
          </select>
          <select id="filter-status" class="hidden">
            <option value="unreviewed" selected>未浏览</option>
            <option value="all">全部</option>
            <option value="reject">已标记剔除</option>
            <option value="keep">未剔除</option>
            <option value="wrong">仅分错</option>
            <option value="correct">仅分对</option>
            <option value="cross">跨级误分</option>
            <option value="adjacent">相邻误分</option>
          </select>
          <label>真实 T 分期</label>
          <select id="filter-true">
            <option value="all">全部</option>
            <option value="T1">T1</option>
            <option value="T2">T2</option>
            <option value="T3">T3</option>
            <option value="T4+">T4+</option>
          </select>
        </details>
        <div class="section-card highlight" style="order:-3">
          <h2>恢复 / 同步进度</h2>
          <div class="sync-steps">
            <div class="sync-step">
              <span class="sync-step-num">1</span>
              <div>
                把 CSV 放进<strong>本文件夹</strong>（与 HTML 同级）
                <div class="sync-filenames">推荐文件名：<code>gradcam_rejected.csv</code> · <code>gradcam_review_sync.csv</code></div>
              </div>
            </div>
            <div class="sync-step">
              <span class="sync-step-num">2</span>
              <div>点击下方按钮同步（不会覆盖本机较新记录）</div>
            </div>
          </div>
          <div class="sync-status" id="sync-status">等待同步…</div>
          <div class="btn-stack">
            <button class="primary" id="btn-sync-csv">同步文件夹中的 CSV</button>
            <button id="btn-bind-json">绑定自动保存（筛完后自动写 JSON）</button>
            <button id="btn-export-json">下载 JSON 备份</button>
            <button id="btn-export-reject">下载剔除 CSV 副本</button>
            <button id="btn-clear-storage">清空本地标记</button>
          </div>
          <input type="file" id="csv-file-input" accept=".csv,text/csv" class="hidden">
        </div>
        <div class="section-card">
          <h2>样本列表</h2>
          <div class="list" id="thumb-list"></div>
        </div>
      </aside>
      <main>
        <div class="main-progress">
          <div class="progress-hero">
            <div class="progress-ring" id="progress-ring" style="--pct:0"><span id="hero-pct">0%</span></div>
            <div class="hero-metrics">
              <div class="hero-metric"><b id="hero-reviewed">0</b><span>已浏览</span></div>
              <div class="hero-metric reject"><b id="hero-reject">0</b><span>已剔除</span></div>
              <div class="hero-metric remaining"><b id="hero-remaining">0</b><span>未浏览</span></div>
              <div class="hero-metric"><b id="hero-total">0</b><span>本集总数</span></div>
            </div>
          </div>
          <div class="progress-label">
            <span id="progress-text">加载中…</span>
            <span id="progress-count">0 / 0</span>
          </div>
          <div class="progress-bar"><i id="progress-fill" style="width:0%"></i></div>
        </div>
        <div class="toolbar toolbar-large">
          <button id="btn-first-unreviewed" title="跳到第一张未浏览 (Home)">未浏览</button>
          <button id="btn-prev">上一张</button>
          <button class="danger btn-reject" id="btn-reject">剔除</button>
          <button class="success" id="btn-keep">保留</button>
          <button id="btn-next">下一张</button>
          <button id="btn-undo" title="撤销 (Z)">撤销</button>
          <button id="btn-zoom-out" title="缩小 (-)">−</button>
          <button id="btn-zoom-reset" title="100%">100%</button>
          <button id="btn-zoom-in" title="放大 (+)">+</button>
          <button id="btn-fullscreen" title="全屏 (F)">全屏</button>
        </div>
        <div class="quick-reasons">
          <span style="font-size:12px;color:var(--muted);align-self:center">快选原因：</span>
          <button data-reason="图像质量差-胃壁层次不清">1 层次不清</button>
          <button data-reason="图像质量差-伪影/遮挡">2 伪影遮挡</button>
          <button data-reason="图像质量差-其他">3 其他</button>
        </div>
        <div class="viewer" id="viewer"><div class="load-box">正在加载索引…</div></div>
      </main>
    </div>
  </div>
  <div class="action-dock">
    <button class="danger btn-reject" id="btn-reject-dock">剔除</button>
    <button class="success btn-keep" id="btn-keep-dock">保留</button>
  </div>
  <div class="toast" id="toast"></div>
  <div class="modal-overlay hidden" id="help-modal">
    <div class="modal-box">
      <h2>操作说明</h2>
      <p style="color:var(--muted);font-size:13px;margin:0 0 12px">顶部标签可切换数据集文件夹；默认只筛图像质量。</p>
      <table>
        <tr><td><kbd>→</kbd></td><td>下一张</td></tr>
        <tr><td><kbd>←</kbd></td><td>上一张</td></tr>
        <tr><td><kbd>X</kbd></td><td>标记剔除</td></tr>
        <tr><td><kbd>K</kbd></td><td>标记保留</td></tr>
        <tr><td><kbd>Z</kbd></td><td>撤销剔除</td></tr>
        <tr><td><kbd>F</kbd></td><td>全屏看图</td></tr>
        <tr><td><kbd>Home</kbd></td><td>跳到未浏览</td></tr>
        <tr><td><kbd>1/2/3</kbd></td><td>快选剔除原因</td></tr>
        <tr><td><kbd>+ / −</kbd></td><td>放大 / 缩小</td></tr>
        <tr><td><kbd>[ / ]</kbd></td><td>切换数据集标签</td></tr>
        <tr><td><kbd>C</kbd></td><td>复制患者号</td></tr>
        <tr><td><kbd>?</kbd></td><td>显示本帮助</td></tr>
      </table>
      <button class="primary" id="btn-close-help" style="margin-top:14px;width:100%">知道了</button>
    </div>
  </div>
  <div class="modal-overlay hidden" id="summary-modal">
    <div class="modal-box" style="max-width:640px">
      <h2>筛图进度总览</h2>
      <div class="summary-grid" id="summary-grid"></div>
      <p style="font-size:12px;color:var(--muted);margin:0">数据保存在浏览器本地，换电脑需重新筛或导入 CSV。</p>
      <button class="primary" id="btn-close-summary" style="margin-top:14px;width:100%">关闭</button>
    </div>
  </div>
  <script src="__DATA_PREFIX__manifest.js"></script>
  <script>
    const META = window.__GRADCAM_META__ || {};
    const CHUNK_FILES = window.__GRADCAM_CHUNK_FILES__ || [];
    const DATA_PREFIX = __DATA_PREFIX_JSON__;
    const STORAGE_KEY = "gradcam_screening_" + (META.storage_key || "default");
    const STAGE_ORDER = ["T1", "T2", "T3", "T4+"];
    const SYNC_FILE_NAME = "gradcam_review_sync.csv";
    const SYNC_JSON_NAME = "gradcam_review_sync.json";
    const SYNC_JSON_CANDIDATES = [
      "gradcam_review_sync.json",
    ];
    const SYNC_CSV_CANDIDATES = [
      "gradcam_review_sync.csv",
      "gradcam_rejected.csv",
      "gradcam_review_export.csv",
      "筛图记录.csv",
      "筛图进度.csv",
      "review_sync.csv",
    ];
    const SYNC_ROW_FIELDS = [
      "uid", "filename", "split", "true_name", "pred_name", "correct", "stage_gap",
      "viewed", "rejected", "reject_reason", "note", "error_note",
      "annot_true", "annot_model", "panel", "updated_at",
    ];
    const IDB_NAME = "gradcam_screening_sync_v2";
    const IDB_JSON_HANDLE_KEY = "sync_json_handle";
    const IDB_HANDLE_KEY = "sync_csv_handle";

    let syncJsonHandle = null;
    let syncFileHandle = null;
    let syncWriteTimer = null;
    let syncSourceFile = "";

    let CASES = [];
    let reviews = {};
    let filtered = [];
    let currentIndex = 0;
    let drawMode = "true";
    let drawing = false;
    let dragStart = null;
    let canvas = null;
    let ctx = null;
    let currentItem = null;
    let pathOk = null;
    let saveTimer = null;
    let prefetchImg = null;
    let lastRejectedUid = null;
    let toastTimer = null;
    let activeSplit = "all";
    let zoomLevel = 100;
    let splitPositions = {};
    let sidebarCollapsed = false;

    function showSaveIndicator() {
      const el = document.getElementById("save-indicator");
      if (!el) return;
      el.classList.add("show");
      clearTimeout(showSaveIndicator._t);
      showSaveIndicator._t = setTimeout(() => el.classList.remove("show"), 1200);
    }

    function showSummary(show) {
      const modal = document.getElementById("summary-modal");
      const grid = document.getElementById("summary-grid");
      if (!modal || !grid) return;
      if (show) {
        grid.innerHTML = SPLIT_DEFS.map((def) => {
          const st = splitStats(def.id);
          return `<div class="summary-card">
            <h3>${escHtml(def.label)}</h3>
            <div class="num">${st.pct}%</div>
            <div style="font-size:12px;color:var(--muted);margin-top:4px">
              已浏览 ${st.reviewed}/${st.total}<br>
              剔除 ${st.rejected} · 未浏览 ${st.remaining}
            </div>
            <div class="progress-bar" style="margin-top:8px"><i style="width:${st.pct}%"></i></div>
          </div>`;
        }).join("");
      }
      modal.classList.toggle("hidden", !show);
    }

    function setStageFilter(stage) {
      const sel = document.getElementById("filter-true");
      if (sel) sel.value = stage;
      document.querySelectorAll("#stage-chips button").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.stage === stage);
      });
      currentIndex = 0;
      renderCurrent();
    }

    function copyPatientId() {
      const item = filtered[currentIndex];
      if (!item) return;
      const pid = extractPatientId(item.id);
      navigator.clipboard.writeText(pid).then(
        () => toast("已复制患者号：" + pid),
        () => toast("复制失败，患者号：" + pid)
      );
    }

    function cycleSplit(dir) {
      if (META.mode === "single") return;
      const ids = SPLIT_DEFS.map((d) => d.id);
      const idx = ids.indexOf(activeSplit);
      const next = ids[(idx + dir + ids.length) % ids.length];
      setActiveSplit(next);
    }

    function advanceAfterMark() {
      const status = document.getElementById("filter-status")?.value || "unreviewed";
      if (status === "unreviewed") {
        applyFilters();
        if (currentIndex >= filtered.length) currentIndex = Math.max(0, filtered.length - 1);
        renderCurrent();
        toast(filtered.length ? "已保存" : "本列表已全部浏览完成");
        return;
      }
      goNextUnreviewed();
    }

    function dismissWelcome() {
      document.getElementById("welcome-banner")?.classList.add("hidden");
      try { localStorage.setItem(STORAGE_KEY + "_welcome", "1"); } catch (e) {}
    }

    function maybeShowWelcome() {
      try {
        if (localStorage.getItem(STORAGE_KEY + "_welcome") !== "1") {
          document.getElementById("welcome-banner")?.classList.remove("hidden");
        }
      } catch (e) {}
    }

    const SPLIT_DEFS = [
      { id: "all", label: "全部合集", folder: null },
      { id: "test_external", label: "外部测试", folder: "gradcam_test_external_full" },
      { id: "test_prospective", label: "2025 前瞻", folder: "gradcam_test_prospective_full" },
    ];

    function splitCount(id) {
      if (id === "all") return CASES.length;
      return (META.split_counts && META.split_counts[id]) || CASES.filter((c) => c.split === id).length;
    }

    function scopeCases(split) {
      const s = split || activeSplit;
      if (s === "all") return CASES;
      return CASES.filter((c) => c.split === s);
    }

    function splitStats(split) {
      const items = scopeCases(split);
      const reviewed = items.filter((c) => getReview(c.uid).viewed).length;
      const rejected = items.filter((c) => getReview(c.uid).rejected).length;
      const total = items.length;
      const pct = total ? Math.round((reviewed / total) * 100) : 0;
      return { total, reviewed, rejected, remaining: total - reviewed, pct };
    }

    function renderDatasetTabs() {
      const nav = document.getElementById("dataset-tabs");
      if (!nav) return;
      if (META.mode === "single" && META.fixed_split) {
        nav.classList.add("hidden");
        return;
      }
      nav.innerHTML = SPLIT_DEFS.map((def) => {
        const st = splitStats(def.id);
        const active = def.id === activeSplit ? " active" : "";
        const folderHint = def.folder ? def.folder.replace("gradcam_test_", "").replace("_full", "") : "all";
        return `<button class="dataset-tab${active}" data-split="${def.id}" type="button">
          <span class="tab-title">${escHtml(def.label)}</span>
          <span class="tab-meta">${st.reviewed}/${st.total} 已浏览 · ${st.rejected} 剔除</span>
          <span class="tab-bar"><i style="width:${st.pct}%"></i></span>
        </button>`;
      }).join("");
      nav.querySelectorAll(".dataset-tab").forEach((btn) => {
        btn.onclick = () => setActiveSplit(btn.dataset.split);
      });
    }

    function setActiveSplit(split) {
      if (split === activeSplit) return;
      splitPositions[activeSplit] = currentIndex;
      activeSplit = split;
      const splitEl = document.getElementById("filter-split");
      if (splitEl) splitEl.value = split;
      currentIndex = splitPositions[split] || 0;
      try {
        localStorage.setItem(STORAGE_KEY + "_split", split);
      } catch (e) {}
      renderDatasetTabs();
      renderCurrent();
      toast("已切换到：" + (SPLIT_DEFS.find((d) => d.id === split)?.label || split));
    }

    function loadActiveSplit() {
      try {
        const urlSplit = new URLSearchParams(location.search).get("split");
        if (urlSplit && SPLIT_DEFS.some((d) => d.id === urlSplit)) activeSplit = urlSplit;
        else {
          const v = localStorage.getItem(STORAGE_KEY + "_split");
          if (v && SPLIT_DEFS.some((d) => d.id === v)) activeSplit = v;
        }
        splitPositions = JSON.parse(localStorage.getItem(STORAGE_KEY + "_pos") || "{}");
        sidebarCollapsed = localStorage.getItem(STORAGE_KEY + "_sidebar") === "1";
      } catch (e) {}
    }

    function saveSplitPositions() {
      splitPositions[activeSplit] = currentIndex;
      try {
        localStorage.setItem(STORAGE_KEY + "_pos", JSON.stringify(splitPositions));
        localStorage.setItem(STORAGE_KEY + "_sidebar", sidebarCollapsed ? "1" : "0");
      } catch (e) {}
    }

    function setFilterStatus(status) {
      const sel = document.getElementById("filter-status");
      if (sel) sel.value = status;
      document.querySelectorAll("#filter-chips button").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.status === status);
      });
      currentIndex = 0;
      renderCurrent();
    }

    function setZoom(level) {
      zoomLevel = Math.max(75, Math.min(200, level));
      const stage = document.getElementById("panel-stage");
      if (!stage) return;
      stage.classList.remove("zoom-fit", "zoom-150", "zoom-200");
      if (zoomLevel <= 100) stage.classList.add("zoom-fit");
      else if (zoomLevel <= 150) stage.classList.add("zoom-150");
      else stage.classList.add("zoom-200");
    }

    function toggleSidebar() {
      sidebarCollapsed = !sidebarCollapsed;
      document.getElementById("workspace")?.classList.toggle("sidebar-collapsed", sidebarCollapsed);
      saveSplitPositions();
    }

    function showHelp(show) {
      document.getElementById("help-modal")?.classList.toggle("hidden", !show);
    }

    function goFirstUnreviewed() {
      applyFilters();
      for (let i = 0; i < filtered.length; i++) {
        if (!getReview(filtered[i].uid).viewed) {
          currentIndex = i;
          renderCurrent();
          toast("已跳到第一张未浏览");
          return;
        }
      }
      toast("当前列表已全部浏览");
    }

    function folderLabel(item) {
      if (item.split === "test_external") return "gradcam_test_external_full";
      if (item.split === "test_prospective") return "gradcam_test_prospective_full";
      return item.panel.split("/")[0] || "";
    }

    function toast(msg, ms) {
      const el = document.getElementById("toast");
      if (!el) return;
      el.textContent = msg;
      el.classList.add("show");
      clearTimeout(toastTimer);
      toastTimer = setTimeout(() => el.classList.remove("show"), ms || 1800);
    }

    function extractPatientId(id) {
      const m = String(id).match(/(\d{6,})/);
      return m ? m[1] : id;
    }

    function escHtml(s) {
      return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
    }

    function imgErrorHtml(panel) {
      return `<div class="empty">图片加载失败<br><code>${escHtml(panel)}</code><br>请确认已完整解压，且 HTML 与图片文件夹在同一目录下</div>`;
    }

    function pathErrorHtml(panel) {
      const folder = META.root_folder || "gradcam_test_*_full";
      return `<div class="path-error">
        <h3 style="margin-top:0;">找不到图片，当前 HTML 位置不正确</h3>
        <p>尝试加载：<code>${escHtml(panel)}</code></p>
        <p>请将整个文件夹一起拷贝，双击根目录 <code>gradcam_screening.html</code>。</p>
        <p>目录应含 <code>${escHtml(folder)}</code> 与 <code>screening_data/</code>。</p>
        <p>${escHtml(META.path_help || "")}</p>
      </div>`;
    }

    function showLoading(msg, pct) {
      const viewer = document.getElementById("viewer");
      const width = Math.max(0, Math.min(100, pct || 0));
      viewer.innerHTML = `<div class="load-box">
        <div>${escHtml(msg)}</div>
        <div class="load-bar"><i style="width:${width}%"></i></div>
      </div>`;
    }

    function loadChunkScript(file) {
      return new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.src = DATA_PREFIX + file;
        s.async = true;
        s.onload = () => resolve();
        s.onerror = () => reject(new Error("无法加载 " + file));
        document.head.appendChild(s);
      });
    }

    async function loadAllCases() {
      if (!CHUNK_FILES.length) return [];
      window.__GRADCAM_CHUNKS__ = [];
      let loaded = 0;
      for (const file of CHUNK_FILES) {
        await loadChunkScript(file);
        loaded += 1;
        showLoading(`加载数据分片 ${loaded}/${CHUNK_FILES.length}…`, (loaded / CHUNK_FILES.length) * 100);
      }
      return (window.__GRADCAM_CHUNKS__ || []).flat();
    }

    function initPageMode() {
      if (META.mode === "single" && META.fixed_split) {
        activeSplit = META.fixed_split;
        const splitEl = document.getElementById("filter-split");
        if (splitEl) splitEl.value = META.fixed_split;
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
      probe.src = panelSrc(CASES[0].panel);
    }

    function loadReviews() {
      try {
        let data = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
        if (Object.keys(data).length === 0) {
          for (let i = 0; i < localStorage.length; i++) {
            const k = localStorage.key(i);
            if (k && k.startsWith("gradcam_screening_") && k !== STORAGE_KEY) {
              try {
                const legacy = JSON.parse(localStorage.getItem(k) || "{}");
                if (Object.keys(legacy).length > Object.keys(data).length) data = legacy;
              } catch (e) {}
            }
          }
        }
        return data;
      } catch (e) { return {}; }
    }

    function updateSyncStatus(text, level) {
      const el = document.getElementById("sync-status");
      if (!el) return;
      el.textContent = text;
      el.className = "sync-status" + (level ? " " + level : "");
    }

    function parseCsvLine(line) {
      const out = [];
      let cur = "";
      let inQ = false;
      for (let i = 0; i < line.length; i++) {
        const c = line.charAt(i);
        if (inQ) {
          if (c === '"' && line.charAt(i + 1) === '"') { cur += '"'; i++; }
          else if (c === '"') inQ = false;
          else cur += c;
        } else if (c === '"') inQ = true;
        else if (c === ",") { out.push(cur); cur = ""; }
        else cur += c;
      }
      out.push(cur);
      return out;
    }

    function parseCsv(text) {
      const lines = String(text).replace(/^\ufeff/, "").split(/\r?\n/).filter((l) => l.trim());
      if (!lines.length) return [];
      const header = parseCsvLine(lines[0]).map((h) => h.trim());
      return lines.slice(1).map((line) => {
        const vals = parseCsvLine(line);
        const row = {};
        header.forEach((h, i) => { row[h] = vals[i] ?? ""; });
        return row;
      });
    }

    function resolveUidFromRow(row) {
      if (row.uid) return String(row.uid).trim();
      const split = String(row.split || "").trim();
      const filename = String(row.filename || "").trim();
      if (split && filename) return `${split}::${filename}`;
      if (filename) {
        const hit = CASES.find((c) => c.id === filename || c.uid.endsWith("::" + filename));
        if (hit) return hit.uid;
      }
      return "";
    }

    function reviewTimestamp(rev) {
      return Date.parse((rev && rev.updated_at) || "") || 0;
    }

    function mergeTwoReviews(existing, incoming) {
      const e = { ...defaultReview(), ...existing };
      const n = { ...defaultReview(), ...incoming };
      const te = reviewTimestamp(e);
      const tn = reviewTimestamp(n);
      if (tn > te) return { ...e, ...n, updated_at: n.updated_at || e.updated_at };
      if (te > tn) return e;
      return {
        ...e,
        viewed: e.viewed || n.viewed,
        rejected: e.rejected || n.rejected,
        reason: e.reason || n.reason,
        note: (String(e.note).length >= String(n.note).length) ? e.note : n.note,
        error_note: (String(e.error_note).length >= String(n.error_note).length) ? e.error_note : n.error_note,
        annot_true: ((e.annot_true || []).length >= (n.annot_true || []).length) ? e.annot_true : n.annot_true,
        annot_model: ((e.annot_model || []).length >= (n.annot_model || []).length) ? e.annot_model : n.annot_model,
        updated_at: e.updated_at || n.updated_at || new Date().toISOString(),
      };
    }

    function mergeReviewsFromObject(incomingMap, stats) {
      const st = stats || { added: 0, updated: 0, keptLocal: 0 };
      for (const [uid, rev] of Object.entries(incomingMap || {})) {
        if (!uid || typeof rev !== "object") continue;
        const incoming = { ...defaultReview(), ...rev };
        if (!reviews[uid]) {
          reviews[uid] = incoming;
          st.added += 1;
          continue;
        }
        const before = JSON.stringify(reviews[uid]);
        const merged = mergeTwoReviews(reviews[uid], incoming);
        reviews[uid] = merged;
        if (JSON.stringify(merged) !== before) st.updated += 1;
        else st.keptLocal += 1;
      }
      return st;
    }

    function csvRowToReview(row) {
      const rejected = String(row.rejected || "").trim() === "1";
      const viewedRaw = String(row.viewed || "").trim();
      const viewed = viewedRaw === "1" || rejected || !!String(row.updated_at || "").trim();
      let annot_true = [];
      let annot_model = [];
      try { annot_true = JSON.parse(row.annot_true || "[]"); } catch (e) {}
      try { annot_model = JSON.parse(row.annot_model || "[]"); } catch (e) {}
      return {
        viewed,
        rejected,
        reason: row.reject_reason || "",
        note: row.note || "",
        error_note: row.error_note || "",
        annot_true,
        annot_model,
        updated_at: row.updated_at || new Date().toISOString(),
      };
    }

    function mergeCsvRowsIntoReviews(rows) {
      const incoming = {};
      for (const row of rows) {
        const uid = resolveUidFromRow(row);
        if (!uid) continue;
        incoming[uid] = csvRowToReview(row);
      }
      return mergeReviewsFromObject(incoming);
    }

    function buildSyncPayload() {
      return {
        version: 2,
        storage_key: STORAGE_KEY,
        saved_at: new Date().toISOString(),
        reviews,
      };
    }

    function parseSyncJson(text) {
      const data = JSON.parse(text);
      if (data && data.reviews && typeof data.reviews === "object") return data.reviews;
      if (data && typeof data === "object") return data;
      return {};
    }

    async function loadReviewsFromFolderJson() {
      for (const name of SYNC_JSON_CANDIDATES) {
        try {
          const resp = await fetch(name + "?t=" + Date.now());
          if (!resp.ok) continue;
          const text = await resp.text();
          if (!text.trim()) continue;
          const incoming = parseSyncJson(text);
          const keys = Object.keys(incoming);
          if (!keys.length) continue;
          const stats = mergeReviewsFromObject(incoming);
          syncSourceFile = name;
          try { localStorage.setItem(STORAGE_KEY, JSON.stringify(reviews)); } catch (e) {}
          return { ok: true, file: name, stats, count: keys.length };
        } catch (e) {}
      }
      return { ok: false };
    }

    async function loadReviewsFromFolderCsv() {
      const mergedFiles = [];
      let totalStats = { added: 0, updated: 0, keptLocal: 0 };
      let totalCount = 0;
      for (const name of SYNC_CSV_CANDIDATES) {
        try {
          const resp = await fetch(name + "?t=" + Date.now());
          if (!resp.ok) continue;
          const text = await resp.text();
          const rows = parseCsv(text);
          if (!rows.length) continue;
          const stats = mergeCsvRowsIntoReviews(rows);
          mergedFiles.push(name);
          totalStats.added += stats.added || 0;
          totalStats.updated += stats.updated || 0;
          totalStats.keptLocal += stats.keptLocal || 0;
          totalCount += rows.length;
          syncSourceFile = name;
          try { localStorage.setItem(STORAGE_KEY, JSON.stringify(reviews)); } catch (e) {}
        } catch (e) {}
      }
      if (mergedFiles.length) {
        return {
          ok: true,
          file: mergedFiles.join(" + "),
          stats: totalStats,
          count: totalCount,
        };
      }
      return { ok: false };
    }

    async function loadReviewsFromFolder() {
      const jsonRes = await loadReviewsFromFolderJson();
      if (jsonRes.ok) return jsonRes;
      return loadReviewsFromFolderCsv();
    }

    function formatMergeStats(stats) {
      return `新增 ${stats.added || 0} · 合并 ${stats.updated || 0} · 保留本机较新 ${stats.keptLocal || 0}`;
    }

    function rowsToCsv(rows) {
      const header = SYNC_ROW_FIELDS;
      const body = rows.map((row) => header.map((k) => `"${String(row[k] ?? "").replace(/"/g, '""')}"`).join(","));
      return ["\ufeff" + header.join(",")].concat(body).join("\n");
    }

    function buildSyncRows() {
      return CASES.filter((item) => {
        const rev = getReview(item.uid);
        return rev.viewed || rev.rejected;
      }).map(reviewToRow);
    }

    function openSyncIdb() {
      return new Promise((resolve, reject) => {
        const req = indexedDB.open(IDB_NAME, 1);
        req.onupgradeneeded = () => req.result.createObjectStore("kv");
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });
    }

    async function idbSet(key, value) {
      const db = await openSyncIdb();
      return new Promise((resolve, reject) => {
        const tx = db.transaction("kv", "readwrite");
        tx.objectStore("kv").put(value, key);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
      });
    }

    async function idbGet(key) {
      const db = await openSyncIdb();
      return new Promise((resolve, reject) => {
        const tx = db.transaction("kv", "readonly");
        const req = tx.objectStore("kv").get(key);
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });
    }

    async function restoreSyncFileHandle() {
      if (!("showSaveFilePicker" in window)) return false;
      try {
        const jsonHandle = await idbGet(IDB_JSON_HANDLE_KEY);
        if (jsonHandle) {
          let ok = jsonHandle.queryPermission && await jsonHandle.queryPermission({ mode: "readwrite" }) === "granted";
          if (!ok && jsonHandle.requestPermission) {
            ok = await jsonHandle.requestPermission({ mode: "readwrite" }) === "granted";
          }
          if (ok) { syncJsonHandle = jsonHandle; return true; }
        }
        const csvHandle = await idbGet(IDB_HANDLE_KEY);
        if (csvHandle) {
          let ok = csvHandle.queryPermission && await csvHandle.queryPermission({ mode: "readwrite" }) === "granted";
          if (!ok && csvHandle.requestPermission) {
            ok = await csvHandle.requestPermission({ mode: "readwrite" }) === "granted";
          }
          if (ok) { syncFileHandle = csvHandle; return true; }
        }
      } catch (e) {}
      return false;
    }

    async function writeSyncJsonToFile() {
      if (!syncJsonHandle) return false;
      try {
        const payload = buildSyncPayload();
        const writable = await syncJsonHandle.createWritable();
        await writable.write(JSON.stringify(payload, null, 2));
        await writable.close();
        const n = Object.keys(reviews).filter((k) => getReview(k).viewed || getReview(k).rejected).length;
        updateSyncStatus(`已自动保存 JSON · ${n} 条有效记录`, "ok");
        return true;
      } catch (e) {
        updateSyncStatus("JSON 自动保存失败，请重新绑定", "warn");
        syncJsonHandle = null;
        return false;
      }
    }

    async function writeSyncCsvToFile() {
      if (!syncFileHandle) return false;
      const rows = buildSyncRows();
      const csv = rowsToCsv(rows.length ? rows : []);
      try {
        const writable = await syncFileHandle.createWritable();
        await writable.write(csv);
        await writable.close();
        return true;
      } catch (e) {
        syncFileHandle = null;
        return false;
      }
    }

    function scheduleSyncFileWrite() {
      clearTimeout(syncWriteTimer);
      syncWriteTimer = setTimeout(async () => {
        if (syncJsonHandle) await writeSyncJsonToFile();
        else if (syncFileHandle) await writeSyncCsvToFile();
      }, 400);
    }

    async function bindSyncJsonFile() {
      if (!("showSaveFilePicker" in window)) {
        alert("请使用 Chrome 或 Edge，才能自动保存 JSON 到文件夹。");
        return;
      }
      try {
        syncJsonHandle = await window.showSaveFilePicker({
          suggestedName: SYNC_JSON_NAME,
          types: [{ description: "JSON", accept: { "application/json": [".json"] } }],
        });
        await idbSet(IDB_JSON_HANDLE_KEY, syncJsonHandle);
        await writeSyncJsonToFile();
        toast("已绑定 JSON，每次操作自动保存");
      } catch (e) {
        if (e && e.name !== "AbortError") toast("绑定失败：" + (e.message || e));
      }
    }

    function applyImportedCsvText(text, fileName) {
      const rows = parseCsv(text);
      if (!rows.length) {
        toast("CSV 为空或格式不对");
        return null;
      }
      const stats = mergeCsvRowsIntoReviews(rows);
      syncSourceFile = fileName || "import.csv";
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(reviews)); } catch (e) {}
      updateSyncStatus(`已从 ${syncSourceFile} 同步：${formatMergeStats(stats)}`, "ok");
      toast(`同步完成：${formatMergeStats(stats)}`);
      if (syncJsonHandle || syncFileHandle) scheduleSyncFileWrite();
      renderCurrent();
      return stats;
    }

    async function syncCsvFromFolder(manualPick) {
      updateSyncStatus("正在读取文件夹中的 CSV…", "");
      const csvRes = await loadReviewsFromFolderCsv();
      if (csvRes.ok) {
        updateSyncStatus(`已同步 ${csvRes.file}：${formatMergeStats(csvRes.stats)}`, "ok");
        toast(`已从 ${csvRes.file} 同步进度`);
        renderCurrent();
        if (syncJsonHandle || syncFileHandle) scheduleSyncFileWrite();
        return true;
      }
      if (manualPick !== false) {
        updateSyncStatus("未找到 CSV，请选择文件…", "warn");
        if ("showOpenFilePicker" in window) {
          try {
            const [handle] = await window.showOpenFilePicker({
              multiple: false,
              types: [{ description: "CSV", accept: { "text/csv": [".csv"] } }],
            });
            const file = await handle.getFile();
            applyImportedCsvText(await file.text(), file.name);
            return true;
          } catch (e) {
            if (e && e.name === "AbortError") {
              updateSyncStatus("未选择文件；请把 CSV 放入本文件夹后重试", "warn");
              return false;
            }
          }
        }
        document.getElementById("csv-file-input")?.click();
      } else {
        updateSyncStatus("文件夹内未找到 CSV（请复制 gradcam_rejected.csv 等到本目录）", "warn");
      }
      return false;
    }

    async function importProgressFile() {
      return syncCsvFromFolder(true);
    }

    function downloadJsonBackup() {
      const payload = buildSyncPayload();
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = SYNC_JSON_NAME;
      a.click();
      URL.revokeObjectURL(url);
      toast("已下载 JSON 备份");
    }

    async function bindSyncFile() { return bindSyncJsonFile(); }

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

    function saveReviewsNow() {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(reviews));
      } catch (e) {
        alert("本地保存失败（可能超出浏览器配额）：" + e.message);
      }
      showSaveIndicator();
      if (syncJsonHandle || syncFileHandle) scheduleSyncFileWrite();
      else updateSyncStatus(
        syncSourceFile
          ? `已从 ${syncSourceFile} 读取；绑定 JSON 后可自动写回`
          : "可将历史 JSON/CSV 放入本文件夹，或点「导入历史进度」",
        syncSourceFile ? "" : "warn"
      );
      refreshStats();
      renderList();
    }

    function saveReviews() {
      clearTimeout(saveTimer);
      saveTimer = setTimeout(saveReviewsNow, 250);
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
      const split = document.getElementById("filter-split")?.value || activeSplit;
      const status = document.getElementById("filter-status")?.value || "unreviewed";
      const trueName = document.getElementById("filter-true").value;
      const search = document.getElementById("filter-search").value.trim().toLowerCase();
      filtered = CASES.filter((item) => {
        const rev = getReview(item.uid);
        if (split !== "all" && item.split !== split) return false;
        if (trueName !== "all" && item.true !== trueName) return false;
        if (search && !item.id.toLowerCase().includes(search) && !item.uid.toLowerCase().includes(search)
            && !extractPatientId(item.id).includes(search)) return false;
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
      saveSplitPositions();
    }

    function refreshStats() {
      const scope = scopeCases(activeSplit);
      const globalScope = CASES;
      const rejectCount = scope.filter((c) => getReview(c.uid).rejected).length;
      const reviewedCount = scope.filter((c) => getReview(c.uid).viewed).length;
      const total = scope.length;
      const remaining = total - reviewedCount;
      const pct = total ? Math.round((reviewedCount / total) * 100) : 0;
      const globalReviewed = globalScope.filter((c) => getReview(c.uid).viewed).length;
      const globalTotal = globalScope.length;
      const globalPct = globalTotal ? Math.round((globalReviewed / globalTotal) * 100) : 0;
      const globalReject = globalScope.filter((c) => getReview(c.uid).rejected).length;

      document.getElementById("stat-reviewed-pct").textContent = pct + "%";
      document.getElementById("stat-reject").textContent = rejectCount;
      document.getElementById("stat-remaining").textContent = remaining;
      document.getElementById("stat-idx").textContent = filtered.length ? `${currentIndex + 1}/${filtered.length}` : "0/0";

      const setText = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
      setText("hero-pct", pct + "%");
      setText("hero-reviewed", reviewedCount);
      setText("hero-reject", rejectCount);
      setText("hero-remaining", remaining);
      setText("hero-total", total);
      setText("topbar-progress", `总进度 ${globalPct}%`);

      const ring = document.getElementById("progress-ring");
      if (ring) ring.style.setProperty("--pct", String(pct));

      const fill = document.getElementById("progress-fill");
      const pText = document.getElementById("progress-text");
      const pCount = document.getElementById("progress-count");
      const splitName = SPLIT_DEFS.find((d) => d.id === activeSplit)?.label || "全部";
      const hint = document.getElementById("scope-hint");
      if (fill) fill.style.width = pct + "%";
      if (pText) {
        pText.textContent = remaining > 0
          ? `【${splitName}】已浏览 ${reviewedCount}/${total}，还剩 ${remaining} 张`
          : `【${splitName}】已全部浏览完成`;
      }
      if (pCount) pCount.textContent = `全部 ${globalReviewed}/${globalTotal} · 剔除 ${globalReject}`;
      if (hint) hint.textContent = activeSplit === "all"
        ? `全部合集：已浏览 ${globalReviewed}/${globalTotal}（${globalPct}%）`
        : `${splitName}：${reviewedCount}/${total}（${pct}%）· 全部合集 ${globalPct}%`;
      renderDatasetTabs();
    }

    function splitLabel(split) {
      if (split === "test_external") return "外部";
      if (split === "test_prospective") return "前瞻";
      return split;
    }

    function renderList() {
      const list = document.getElementById("thumb-list");
      const start = Math.max(0, currentIndex - 80);
      const end = Math.min(filtered.length, start + 160);
      const items = filtered.slice(start, end).map((item, offset) => {
        const idx = start + offset;
        const rev = getReview(item.uid);
        const cls = ["list-item", idx === currentIndex ? "active" : "", rev.rejected ? "rejected" : ""].filter(Boolean).join(" ");
        const dotCls = rev.rejected ? "reject" : rev.viewed ? "done" : "";
        return `<div class="${cls}" data-idx="${idx}">
          <span class="dot ${dotCls}"></span>
          <span>#${idx + 1} ${extractPatientId(item.id)}</span>
        </div>`;
      }).join("");
      let head = "";
      if (start > 0) head = `<div class="list-item">… 前 ${start} 条（用搜索或跳转序号）</div>`;
      let tail = "";
      if (end < filtered.length) tail = `<div class="list-item">… 后 ${filtered.length - end} 条</div>`;
      list.innerHTML = head + items + tail;
      list.querySelectorAll(".list-item[data-idx]").forEach((el) => {
        el.addEventListener("click", () => { currentIndex = Number(el.dataset.idx); renderCurrent(); });
      });
    }

    window.__imgErr = imgErrorHtml;

    function panelSrc(panel) {
      return encodeURI(panel).replace(/#/g, "%23");
    }

    function prefetchAdjacent() {
      if (!filtered.length) return;
      const next = filtered[(currentIndex + 1) % filtered.length];
      if (!next) return;
      prefetchImg = new Image();
      prefetchImg.src = panelSrc(next.panel);
    }

    function buildPanelHtml(item, showAnnot) {
      const src = panelSrc(item.panel);
      const err = item.panel.replace(/'/g, "\\'");
      const rev = getReview(item.uid);
      const overlay = rev.rejected
        ? `<span class="overlay-badge reject">已剔除</span>`
        : rev.viewed
          ? `<span class="overlay-badge keep">已浏览</span>`
          : "";
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
          <div class="panel-overlay">${overlay}</div>
          <div class="panel-inner">
            <img class="panel-img" id="panel-img" src="${src}" alt="${escHtml(item.id)}" loading="lazy" decoding="async"
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
        saveReviewsNow();
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
        viewer.innerHTML = `<div class="empty">${CASES.length ? "当前筛选条件下没有样本，可切换「全部」或清空搜索" : "没有可显示的样本"}</div>`;
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
      const infoHtml = `
          <div class="info info-large">
            <div class="filename">#${currentIndex + 1} · ${escHtml(item.id)}</div>
            <span class="tag split">${splitLabel(item.split)}</span>
            <span class="folder-badge">${escHtml(folderLabel(item))}</span>
            <div>真实 <b>${item.true}</b> → 预测 <b>${item.pred}</b></div>
            ${statusTag} ${correctTag}
          </div>
          <div class="probs">${probs}</div>
        `;

      viewer.innerHTML = infoHtml + buildPanelHtml(item, showAnnot);

      const errNote = document.getElementById("error-note");
      if (errNote) {
        errNote.addEventListener("change", () => {
          const r = getReview(item.uid);
          r.error_note = errNote.value.trim();
          r.updated_at = new Date().toISOString();
          reviews[item.uid] = r;
          saveReviewsNow();
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
        saveReviewsNow();
        redrawAnnotations();
      });
      bind("clear-annot", () => {
        if (!confirm("清空当前图的所有标注框？")) return;
        const r = getReview(item.uid);
        r.annot_true = [];
        r.annot_model = [];
        reviews[item.uid] = r;
        saveReviewsNow();
        redrawAnnotations();
      });
      bind("btn-copy-pid", copyPatientId);
      bind("btn-zoom-fit", () => { setZoom(100); });
      bind("btn-zoom-100", () => {
        setZoom(100);
        document.getElementById("panel-stage")?.classList.remove("zoom-fit");
      });
      setupCanvas();
      setZoom(zoomLevel);
      prefetchAdjacent();
    }

    function toggleFullscreen() {
      const stage = document.getElementById("panel-stage");
      if (!stage) return;
      stage.classList.toggle("is-fullscreen");
      if (stage.classList.contains("is-fullscreen")) {
        toast("按 Esc 或再点「全屏」退出");
      }
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
      saveReviewsNow();
    }

    function markReject() {
      const item = filtered[currentIndex];
      if (item) lastRejectedUid = item.uid;
      persistSidebarFields(true);
      advanceAfterMark();
    }
    function markKeep() {
      persistSidebarFields(false);
      advanceAfterMark();
    }

    function undoReject() {
      const uid = lastRejectedUid;
      if (!uid || !reviews[uid] || !reviews[uid].rejected) {
        toast("没有可撤销的剔除");
        return;
      }
      reviews[uid] = { ...getReview(uid), rejected: false, reason: "", updated_at: new Date().toISOString() };
      lastRejectedUid = null;
      saveReviewsNow();
      toast("已撤销剔除");
      renderCurrent();
    }

    function setQuickReason(reason) {
      const sel = document.getElementById("reject-reason");
      if (sel) sel.value = reason;
      toast("已选择：" + reason.replace("图像质量差-", ""));
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
        if (!getReview(filtered[idx].uid).viewed) { currentIndex = idx; renderCurrent(); return; }
      }
      goNext();
    }

    function jumpToIndex() {
      const raw = document.getElementById("jump-index").value;
      const n = parseInt(raw, 10);
      if (!n || n < 1 || !filtered.length) return;
      currentIndex = Math.min(filtered.length - 1, n - 1);
      renderCurrent();
    }

    function searchAndJump() {
      const q = document.getElementById("filter-search").value.trim();
      if (!q) { currentIndex = 0; renderCurrent(); return; }
      applyFilters();
      const exact = filtered.findIndex((item) =>
        item.id.toLowerCase().includes(q.toLowerCase()) || extractPatientId(item.id) === q
      );
      if (exact >= 0) {
        currentIndex = exact;
        renderCurrent();
        toast("已跳转到匹配样本");
      } else {
        currentIndex = 0;
        renderCurrent();
        toast("未找到，显示当前筛选结果");
      }
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
        viewed: rev.viewed ? "1" : "0",
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

    function bindUi() {
      document.getElementById("btn-prev").onclick = goPrev;
      document.getElementById("btn-next").onclick = goNext;
      document.getElementById("btn-reject").onclick = markReject;
      document.getElementById("btn-keep").onclick = markKeep;
      document.getElementById("btn-undo").onclick = undoReject;
      document.getElementById("btn-fullscreen").onclick = toggleFullscreen;
      document.getElementById("btn-summary").onclick = () => showSummary(true);
      document.getElementById("btn-close-summary").onclick = () => showSummary(false);
      document.getElementById("summary-modal").onclick = (e) => {
        if (e.target.id === "summary-modal") showSummary(false);
      };
      document.getElementById("btn-dismiss-welcome").onclick = dismissWelcome;
      document.getElementById("btn-first-unreviewed").onclick = goFirstUnreviewed;
      document.getElementById("btn-toggle-sidebar").onclick = toggleSidebar;
      document.getElementById("btn-help").onclick = () => showHelp(true);
      document.getElementById("btn-close-help").onclick = () => showHelp(false);
      document.getElementById("help-modal").onclick = (e) => {
        if (e.target.id === "help-modal") showHelp(false);
      };
      document.getElementById("btn-zoom-in").onclick = () => { setZoom(zoomLevel + 25); toast("缩放 " + zoomLevel + "%"); };
      document.getElementById("btn-zoom-out").onclick = () => { setZoom(zoomLevel - 25); toast("缩放 " + zoomLevel + "%"); };
      document.getElementById("btn-zoom-reset").onclick = () => { setZoom(100); toast("100%"); };
      document.querySelectorAll(".quick-reasons button[data-reason]").forEach((btn) => {
        btn.onclick = () => setQuickReason(btn.dataset.reason);
      });
      document.querySelectorAll("#filter-chips button").forEach((btn) => {
        btn.onclick = () => setFilterStatus(btn.dataset.status);
      });
      document.querySelectorAll("#stage-chips button").forEach((btn) => {
        btn.onclick = () => setStageFilter(btn.dataset.stage);
      });
      document.getElementById("btn-sync-csv").onclick = () => syncCsvFromFolder(true);
      document.getElementById("csv-file-input")?.addEventListener("change", async (e) => {
        const file = e.target.files && e.target.files[0];
        if (!file) return;
        applyImportedCsvText(await file.text(), file.name);
        e.target.value = "";
      });
      document.getElementById("btn-bind-json").onclick = bindSyncJsonFile;
      document.getElementById("btn-export-json").onclick = downloadJsonBackup;
      document.getElementById("btn-reject-dock").onclick = markReject;
      document.getElementById("btn-keep-dock").onclick = markKeep;
      document.getElementById("btn-export-reject").onclick = () => {
        const rows = CASES.map(reviewToRow).filter((r) => r.rejected === "1");
        if (!rows.length) { alert("暂无剔除样本"); return; }
        downloadCsv("gradcam_rejected.csv", rows);
        toast("已下载剔除 CSV 副本");
      };
      document.getElementById("btn-clear-storage").onclick = () => {
        if (confirm("确定清空所有本地标记？")) {
          localStorage.removeItem(STORAGE_KEY);
          localStorage.removeItem(STORAGE_KEY + "_mode");
          localStorage.removeItem(STORAGE_KEY + "_split");
          localStorage.removeItem(STORAGE_KEY + "_pos");
          reviews = {};
          lastRejectedUid = null;
          splitPositions = {};
          renderCurrent();
          toast("已清空");
        }
      };
      document.getElementById("filter-true").addEventListener("change", () => { currentIndex = 0; renderCurrent(); });
      document.getElementById("filter-search").addEventListener("input", () => { currentIndex = 0; renderCurrent(); });
      document.getElementById("filter-search").addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); searchAndJump(); }
      });
      document.getElementById("jump-index").addEventListener("change", jumpToIndex);
      document.getElementById("jump-index").addEventListener("keydown", (e) => {
        if (e.key === "Enter") jumpToIndex();
      });

      document.addEventListener("keydown", (e) => {
        if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT") return;
        if (!document.getElementById("help-modal")?.classList.contains("hidden") && e.key === "Escape") {
          showHelp(false); return;
        }
        if (document.getElementById("panel-stage")?.classList.contains("is-fullscreen") && e.key === "Escape") {
          document.getElementById("panel-stage").classList.remove("is-fullscreen");
          return;
        }
        if (e.key === "?") { showHelp(true); return; }
        if (e.key.toLowerCase() === "c") copyPatientId();
        if (e.key === "[") cycleSplit(-1);
        if (e.key === "]") cycleSplit(1);
        if (e.key === "ArrowLeft") goPrev();
        if (e.key === "ArrowRight") goNext();
        if (e.key.toLowerCase() === "x") markReject();
        if (e.key.toLowerCase() === "k") markKeep();
        if (e.key.toLowerCase() === "z") undoReject();
        if (e.key.toLowerCase() === "f") toggleFullscreen();
        if (e.key.toLowerCase() === "n") goNextUnreviewed();
        if (e.key === "Home") goFirstUnreviewed();
        if (e.key === "1") setQuickReason("图像质量差-胃壁层次不清");
        if (e.key === "2") setQuickReason("图像质量差-伪影/遮挡");
        if (e.key === "3") setQuickReason("图像质量差-其他");
        if (e.key === "+" || e.key === "=") { setZoom(zoomLevel + 25); toast("缩放 " + zoomLevel + "%"); }
        if (e.key === "-") { setZoom(zoomLevel - 25); toast("缩放 " + zoomLevel + "%"); }
        if (e.key.toLowerCase() === "g") { drawMode = "true"; renderCurrent(); }
        if (e.key.toLowerCase() === "r") { drawMode = "model"; renderCurrent(); }
      });
    }

    async function boot() {
      initPageMode();
      loadActiveSplit();
      bindUi();
      const splitEl = document.getElementById("filter-split");
      if (splitEl) splitEl.value = activeSplit;
      document.getElementById("workspace")?.classList.toggle("sidebar-collapsed", sidebarCollapsed);
      try {
        showLoading("正在加载样本索引…", 5);
        CASES = await loadAllCases();
        reviews = loadReviews();
        const folderRes = await loadReviewsFromFolder();
        const hasHandle = await restoreSyncFileHandle();
        if (folderRes.ok) {
          updateSyncStatus(`已自动同步 ${folderRes.file}：${formatMergeStats(folderRes.stats)}`, "ok");
        } else if (hasHandle) {
          updateSyncStatus("已绑定自动保存；筛图后自动写入 JSON", "ok");
        } else {
          updateSyncStatus("若有历史 CSV，放入本文件夹后点「同步文件夹中的 CSV」", "warn");
        }
        if (syncJsonHandle) await writeSyncJsonToFile();
        else if (syncFileHandle) await writeSyncCsvToFile();
        renderDatasetTabs();
        maybeShowWelcome();
        showLoading(`已加载 ${CASES.length} 条，校验图片路径…`, 100);
        verifyPaths(() => renderCurrent());
      } catch (err) {
        document.getElementById("viewer").innerHTML = `<div class="path-error">
          <h3 style="margin-top:0;">数据加载失败</h3>
          <p>${escHtml(err.message || String(err))}</p>
          <p>请确认已完整拷贝文件夹，且 <code>screening_data/</code> 与 HTML 在同一目录。</p>
        </div>`;
      }
    }

    boot();
  </script>
</body>
</html>
"""


def write_sync_json_template(bundle_root: Path) -> Path:
    path = bundle_root / SYNC_JSON_NAME
    if not path.exists():
        path.write_text(
            json.dumps({"version": 2, "reviews": {}, "saved_at": ""}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return path


def write_sync_csv_template(bundle_root: Path) -> Path:
    """Create empty sync CSV in bundle root if missing (do not overwrite doctor progress)."""
    path = bundle_root / SYNC_CSV_NAME
    if not path.exists():
        path.write_text("\ufeff" + SYNC_CSV_HEADER + "\n", encoding="utf-8")
    return path


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


def write_chunk_js(chunk_path: Path, cases: list[dict]) -> None:
    payload = json.dumps(cases, ensure_ascii=False, separators=(",", ":"))
    chunk_path.write_text(
        "window.__GRADCAM_CHUNKS__=window.__GRADCAM_CHUNKS__||[];"
        f"window.__GRADCAM_CHUNKS__.push({payload});",
        encoding="utf-8",
    )


def write_manifest_js(
    manifest_path: Path,
    meta: dict,
    chunk_files: list[str],
) -> None:
    meta_json = json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
    files_json = json.dumps(chunk_files, ensure_ascii=False, separators=(",", ":"))
    manifest_path.write_text(
        f"window.__GRADCAM_META__={meta_json};"
        f"window.__GRADCAM_CHUNK_FILES__={files_json};",
        encoding="utf-8",
    )


def write_screening_bundle(
    output_html: Path,
    all_cases: list[dict],
    meta: dict,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> dict:
    """Write HTML + screening_data/*.js chunks (file:// friendly via script tags)."""
    if not all_cases:
        raise SystemExit("No cases with valid panel_path found.")

    bundle_root = output_html.parent.resolve()
    data_dir = bundle_root / SCREENING_DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)

    chunk_files: list[str] = []
    n_chunks = max(1, math.ceil(len(all_cases) / chunk_size))
    for idx in range(n_chunks):
        start = idx * chunk_size
        end = min(len(all_cases), start + chunk_size)
        chunk_name = f"chunk_{idx:03d}.js"
        write_chunk_js(data_dir / chunk_name, all_cases[start:end])
        chunk_files.append(chunk_name)

    meta = {
        **meta,
        "total": len(all_cases),
        "chunk_size": chunk_size,
        "chunk_count": len(chunk_files),
        "data_dir": SCREENING_DATA_DIR,
    }
    write_manifest_js(data_dir / "manifest.js", meta, chunk_files)

    data_prefix = f"{SCREENING_DATA_DIR}/"
    subtitle = meta.get("subtitle") or ""
    html_text = (
        HTML_TEMPLATE.replace("__PAGE_TITLE__", meta.get("title", "GradCAM 测试集筛图"))
        .replace("__PAGE_SUBTITLE__", subtitle)
        .replace("__DATA_PREFIX__", data_prefix)
        .replace("__DATA_PREFIX_JSON__", json.dumps(data_prefix))
    )
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html_text, encoding="utf-8")

    return {
        "html": str(output_html),
        "data_dir": str(data_dir),
        "cases": len(all_cases),
        "chunk_count": len(chunk_files),
        "chunk_size": chunk_size,
        "split_counts": meta.get("split_counts", {}),
    }


def build_unified_html(
    sources: list[dict],
    output_html: Path,
    *,
    title: str = "GradCAM 测试集筛图",
    subtitle: str | None = None,
    storage_key: str = "unified_v8",
    mode: str = "unified",
    fixed_split: str | None = None,
    root_folder: str | None = None,
    path_help: str | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> dict:
    """Build one HTML entry + external data chunks from gradcam_results.csv sources."""
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

    if subtitle is None:
        if mode == "single" and root_folder:
            subtitle = (
                f"双击本 HTML。图片在 <code>{root_folder}/panels/</code>，"
                f"索引在 <code>{SCREENING_DATA_DIR}/</code>。"
            )
        else:
            subtitle = (
                "将整个文件夹拷贝到本地，双击本 HTML。"
                "图片在子文件夹 <code>gradcam_test_*_full/panels/</code>，"
                f"索引在 <code>{SCREENING_DATA_DIR}/</code>。"
            )

    meta = {
        "title": title,
        "subtitle": subtitle,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "split_counts": split_counts,
        "storage_key": storage_key,
        "mode": mode,
        "fixed_split": fixed_split,
        "root_folder": root_folder,
        "path_help": path_help or "",
    }
    return write_screening_bundle(output_html, all_cases, meta, chunk_size=chunk_size)


SPLIT_HTML_SPECS = {
    "test_external": {
        "title": "GradCAM 外部测试筛图",
        "storage_key": "gradcam_screening_test_external_v8",
        "dir_name": "gradcam_test_external_full",
    },
    "test_prospective": {
        "title": "GradCAM 2025前瞻全量筛图",
        "storage_key": "gradcam_screening_test_prospective_2025_full_v8",
        "dir_name": "gradcam_test_prospective_full",
    },
}


def build_split_screening_html(source: dict, output_html: Path, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> dict:
    split = str(source["split"])
    spec = SPLIT_HTML_SPECS.get(split, {})
    root_dir = Path(source.get("root_dir", Path(source["results_csv"]).parent)).resolve()
    return build_unified_html(
        [{**source, "path_prefix": ""}],
        output_html,
        title=spec.get("title", f"GradCAM {split} 筛图"),
        storage_key=spec.get("storage_key", f"{split}_v8"),
        mode="single",
        fixed_split=split,
        root_folder=spec.get("dir_name", root_dir.name),
        path_help="单数据集包：HTML 与 panels/、screening_data/ 在同一文件夹。",
        chunk_size=chunk_size,
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
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="Cases per screening_data chunk")
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

    summary = build_unified_html(sources, output_html, chunk_size=args.chunk_size)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
