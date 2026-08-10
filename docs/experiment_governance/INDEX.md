# 实验治理索引（薄索引）

**入口：** [START_HERE.md](../../START_HERE.md) → [pipeline/experiments/README.md](../../pipeline/experiments/README.md)

| 主题 | 路径 |
|------|------|
| 人读实验入口 | [experiments/README.md](../../experiments/README.md) |
| 实验登记 CSV | [experiments/registry.csv](../../experiments/registry.csv) |
| 大产物说明 | [experiments/LARGE_ARTIFACTS.md](../../experiments/LARGE_ARTIFACTS.md) |
| 机器落盘 | [pipeline/experiments/README.md](../../pipeline/experiments/README.md) |
| T 分期主线 scoreboard | [pipeline/experiments/tables/tstaging_4class_mainline_scoreboard.csv](../../pipeline/experiments/tables/tstaging_4class_mainline_scoreboard.csv) |
| 冻结 baseline | [pipeline/experiments/mainlines/tstaging_4class/baseline_registry.yaml](../../pipeline/experiments/mainlines/tstaging_4class/baseline_registry.yaml) |
| Baseline 证据包 | [experiments/baselines/](../../experiments/baselines/) |
| Tree 浅索引（不搬迁） | [pipeline/experiments/tree_index.csv](../../pipeline/experiments/tree_index.csv) · 生成：`python scripts/build_experiments_tree_index.py` |
| 工作区盘点 | [data/metadata/workspace_inventory.csv](../../data/metadata/workspace_inventory.csv) |
| **论文消融（首选）** | [pipeline/experiments/paper_assets/tstaging_4class/README.md](../../pipeline/experiments/paper_assets/tstaging_4class/README.md) |
| 消融矩阵 | [ablation_matrix.csv](../../pipeline/experiments/paper_assets/tstaging_4class/ablation_matrix.csv) |
| 模型 inventory + 审计 | [model_inventory.csv](../../pipeline/experiments/paper_assets/tstaging_4class/model_inventory.csv) · [inventory_status.json](../../models/inventory_status.json) |
| 报告索引 | [report_index.csv](../../pipeline/experiments/paper_assets/tstaging_4class/report_index.csv) |
| 评估链路审计 | [eval_chain_status.md](../../pipeline/experiments/paper_assets/tstaging_4class/eval_chain_status.md) |
| 配置策略 | [pipeline/configs/TSTAGE_CONFIG_POLICY.md](../../pipeline/configs/TSTAGE_CONFIG_POLICY.md) |
| 日志 index | [log_index.csv](../../pipeline/experiments/paper_assets/tstaging_4class/log_index.csv) |

维护规则：[MAINTENANCE.md](../../MAINTENANCE.md) · [docs/project_governance.md](../project_governance.md)

### 新实验登记（消融对比）

每个 promoted 或 paper-relevant run 必须能对应 `ablation_matrix.csv` 一行：`question`、`changed_factor`、`fixed_factors`、`paper_role`、`run_dir`。生成脚本：`scripts/build_paper_ablation_matrix.py`。
