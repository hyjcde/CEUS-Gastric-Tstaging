# apps/ 内部归位规则

每个子目录应是**可独立启动的产品**，不混放仓库级实验产物。

**论文主线评估**（消融、scoreboard、checkpoint）以 [pipeline/experiments/paper_assets/tstaging_4class/](../pipeline/experiments/paper_assets/tstaging_4class/) 为准；`apps/` 内 demo 数据与 UI 导出 **不** 进入 `ablation_matrix.csv`，除非显式登记为 supplementary。

## direction_annotator

- 源码：`src/`、`main.js`
- 数据根：环境变量 / 自动发现 `data/annotation/`
- 说明：`使用说明.txt`、`.env.example`

## tstage_reader_study

- 用途：reader study 阅片包（论文 Appendix S10 主工具）
- 启动：`./start.sh` 或 `start.bat`，访问 `http://127.0.0.1:8765/?reader=ID&pass=1|2`
- 资产：150 cases from `docs/clinical_validation/reader_study_150/reader_subset_v2.csv`
- 视频：fall-back 至 `data/raw/qualified_reader_videos/` + `data/raw/legacy_external_direct_surgery/` 等

## gastric_scan_next

| 应在此 | 不应在此 |
|--------|----------|
| `app/`、`components/`、`lib/`、`public/` | `*_SUMMARY.md`、`*_ROADMAP.md`（→ `docs/apps/gastric_scan_next/`） |
| `package.json`、`next.config.ts` | 大批量临床 JSON（→ `fixtures/` 或 `data/registry`） |
| `scripts/dev_server.sh` 等运维脚本 | 与 T 分期训练重复的 pipeline 脚本 |

Demo/演示数据：`fixtures/`（若仅为 UI demo）。

## 登记

应用侧数据路径变更需同步 [../apps/direction_annotator/src/lib/dataRoot.ts](../direction_annotator/src/lib/dataRoot.ts) 与 [../MAINTENANCE.md](../MAINTENANCE.md)。
