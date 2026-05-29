# 大型实验产物说明

`experiments/` 与 `pipeline/experiments/` 合计约 **800GB+**，**不提交 Git**，也不整体搬迁。

## 分工

| 目录 | 用途 |
|------|------|
| [experiments/](../experiments/) | 人类可读的 baseline 与证据包入口 |
| [pipeline/experiments/](../pipeline/experiments/) | 训练框架自动落盘、`tree/`、`reports/`、`tables/` |
| [experiments/registry.csv](registry.csv) | 从 registry 查 `run_dir`，勿在 tree 里盲目搜索 |

## 正式结论看哪里

- T 分期主线：[pipeline/experiments/reports/tstaging_4class_mainline_summary.md](../pipeline/experiments/reports/tstaging_4class_mainline_summary.md)
- 分数表：[pipeline/experiments/tables/tstaging_4class_mainline_scoreboard.csv](../pipeline/experiments/tables/tstaging_4class_mainline_scoreboard.csv)
- 冻结 baseline：[pipeline/experiments/mainlines/tstaging_4class/baseline_registry.yaml](../pipeline/experiments/mainlines/tstaging_4class/baseline_registry.yaml)

## 新增 run 规则

每个正式 run 在 `experiments/registry.csv` 登记，并在 run 目录保留 `README.md` + 配置快照 + 患者级结果表。详见 [docs/experiment_governance/experiment_structure.md](../docs/experiment_governance/experiment_structure.md)。
