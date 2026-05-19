# Poe 方法学 / 结果图

## 环境变量

在**仓库根目录**复制 `.env.example` 为 `.env`，填入：

```bash
POE_API_KEY=sk-poe-...
```

`.env` 已被 git 忽略，不会提交。脚本会自动 `load_repo_env()`，也可在 shell 中 `export POE_API_KEY=...`。

## 生成

```bash
# 全部（约 15–20 分钟，GPT-Image-2 via Poe Chat API）
python scripts/generate_agent_figures_poe_batch.py

# 仅补缺失
python scripts/generate_agent_figures_poe_batch.py --skip-existing

# 列出任务名
python scripts/generate_agent_figures_poe_batch.py --list
```

## 打包离线 HTML

```bash
python scripts/package_project_logic_bundle.py --zip
```

输出：`docs/mainline/project_logic_bundle/`

## 本地真实结果图

`figures/local/` 存放从论文图集与 `experiments/` 复制的评估图（AUC、混淆矩阵、分割对比等），供 `gastric_tstaging_project_logic_white.html` 的「本地实验与论文结果图」章节引用。

重新同步（从 manuscript export 复制）：

```bash
# 见仓库内 docs/mainline/figures/local/ 或运行维护脚本后打包
python scripts/package_project_logic_bundle.py --zip
```
