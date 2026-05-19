# 项目逻辑 HTML 配图

## Poe 方法学示意图（`fig_*.png`）

在仓库根目录配置 `.env` 中的 `POE_API_KEY`，运行：

```bash
python scripts/generate_agent_figures_poe_batch.py --skip-existing
```

## 本地真实结果图（`results/` · 单一目录）

**病例超声示例**（全流程、边界、Grad-CAM、外部验证面板、Agent 推理）与 **汇总指标图**（AUC、混淆矩阵、ROC）均放在：

`docs/mainline/figures/results/`

```bash
# 指标图（scoreboard + eval JSON，与正文 KPI 一致）
python scripts/generate_mainline_metric_figures.py

# 病例图 + 指标图（内部会调用上一命令）
python scripts/sync_project_logic_result_figures.py

# 刷新 HTML 图集片段后嵌入 white.html（或用手动替换 local-results 节）
python scripts/generate_result_figures_html.py

# 导出 PDF（需 google-chrome；图多时 PDF 较大）
python scripts/export_project_logic_pdf.py
```

清单见 `results/manifest.json`（含每张图的仓库内源路径）。

## 离线打包

```bash
python scripts/package_project_logic_bundle.py --zip
```

输出：`docs/mainline/project_logic_bundle/`（含 `figures/results/`）
