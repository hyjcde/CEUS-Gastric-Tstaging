# 文档入口

仓库总入口：**[../START_HERE.md](../START_HERE.md)**。文档很多时，**只认下面一条路径**，避免在 `mainline/`、`references/` 里迷路。

## 三步阅读（推荐）

| 步骤 | 文档 | 用时 |
|------|------|------|
| 1 | **[ARCHITECTURE.md](ARCHITECTURE.md)** — 系统分层、目录地图、数据流、文档 Tier A/B/C | ~15 分钟 |
| 2 | **[mainline/gastric_tstaging_project_framework_zh.md](mainline/gastric_tstaging_project_framework_zh.md)** — 临床目标、P0 T 分期、已有模型资产 | ~30 分钟 |
| 3 | **[mainline/tstaging_current_mainline.md](mainline/tstaging_current_mainline.md)** — 当前在做什么（阶段 A/B/C） | ~10 分钟 |

可视化：浏览器打开 [mainline/gastric_tstaging_project_logic.html](mainline/gastric_tstaging_project_logic.html)。

## 按角色跳转

| 你要做的事 | 去读 |
|------------|------|
| 核对数据、split、多中心 | [../dataset/DATASET_GUIDE.md](../dataset/DATASET_GUIDE.md) + [data_governance/data_split_policy.md](data_governance/data_split_policy.md) |
| 跑检测/分割/T 分期实验 | [../scripts/README.md](../scripts/README.md) + [experiment_governance/experiment_structure.md](experiment_governance/experiment_structure.md) |
| 开发 Agent / 前端工作台 | [mainline/agent_api_contract.md](mainline/agent_api_contract.md) + [../apps/README.md](../apps/README.md) |
| 查某次实验结论 | [../experiments/registry.csv](../experiments/registry.csv) + `pipeline/experiments/reports/` |
| 维护仓库路径 | [../MAINTENANCE.md](../MAINTENANCE.md) |
| 查全部文档清单 | [DOCUMENT_MAP.md](DOCUMENT_MAP.md) |

## 不要从这里开始

- `docs copy/` → 实体在 `archive/docs_legacy/docs_copy/`（根 symlink 兼容），非当前 SSOT
- `references/dinov3/`、`references/segdino/` — 阶段性笔记
- `archive_refs/` — 旧 Tstaging 迁移材料
- `mainline/figures/results/` — 出图产物

## 治理规范（需要时打开）

- [data_governance/](data_governance/) — 注册表、split、QC
- [experiment_governance/](experiment_governance/) — 实验命名与 baseline 顺序
- [evaluation/validation_protocol.md](evaluation/validation_protocol.md) — 验证协议
- [visualization/visualization_standard.md](visualization/visualization_standard.md) — 出图规范
