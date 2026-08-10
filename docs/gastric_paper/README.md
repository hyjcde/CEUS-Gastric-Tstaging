# Gastric T-staging 论文写作入口

写 **4-class 主线** 论文时，按下列顺序查 SSOT（不要从 `experiments/tree/` 盲搜）。

## 1. 实验与消融

| 用途 | 路径 |
|------|------|
| **总入口** | [pipeline/experiments/paper_assets/tstaging_4class/README.md](../../pipeline/experiments/paper_assets/tstaging_4class/README.md) |
| 消融矩阵 | [ablation_matrix.csv](../../pipeline/experiments/paper_assets/tstaging_4class/ablation_matrix.csv) |
| 主线指标 | [tstaging_4class_mainline_scoreboard.csv](../../pipeline/experiments/tables/tstaging_4class_mainline_scoreboard.csv) |
| 链路审计 | [eval_chain_status.md](../../pipeline/experiments/paper_assets/tstaging_4class/eval_chain_status.md) |

## 2. 数据

| 用途 | 路径 |
|------|------|
| Split 指针 | [data/registry/SPLIT_POINTERS.md](../../data/registry/SPLIT_POINTERS.md) |
| 数据集登记 | [data/registry/dataset_registry.csv](../../data/registry/dataset_registry.csv) |

## 3. 配置与模型

| 用途 | 路径 |
|------|------|
| T 分期配置策略 | [pipeline/configs/TSTAGE_CONFIG_POLICY.md](../../pipeline/configs/TSTAGE_CONFIG_POLICY.md) |
| 模型 inventory | [model_inventory.csv](../../pipeline/experiments/paper_assets/tstaging_4class/model_inventory.csv) |
| 审计摘要 | [models/inventory_status.json](../../models/inventory_status.json) |

## 4. 报告与图表

| 用途 | 路径 |
|------|------|
| 报告索引 | [report_index.csv](../../pipeline/experiments/paper_assets/tstaging_4class/report_index.csv) |
| 图表指针 | [figure_table_index.csv](../../pipeline/experiments/paper_assets/tstaging_4class/figure_table_index.csv) |

## 5. 本目录轻量快照

| 子目录 | 内容 |
|--------|------|
| `methods/` | 方法学副本 |
| `metrics/` | 指标与 checkpoint 推荐 |
| `figures/` | 结果图（≤1MB，便于同步） |

重建快照：

```bash
python scripts/build_gastric_paper_assets.py
python scripts/build_paper_ablation_matrix.py
python scripts/build_model_inventory.py
python scripts/build_report_index.py
python scripts/audit_mainline_eval_chain.py
```

## 治理

- [docs/experiment_governance/INDEX.md](../experiment_governance/INDEX.md)
- 完整方法文档：[docs/mainline/](../mainline/)
