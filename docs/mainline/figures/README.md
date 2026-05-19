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
# 从 manuscript / pipeline reports / tmp agent 同步（约 100+ 张）
python scripts/sync_project_logic_result_figures.py

# 刷新 gastric_tstaging_project_logic_white.html 中的图集 HTML
python scripts/generate_result_figures_html.py
```

清单见 `results/manifest.json`（含每张图的仓库内源路径）。

## 离线打包

```bash
python scripts/package_project_logic_bundle.py --zip
```

输出：`docs/mainline/project_logic_bundle/`（含 `figures/results/`）
