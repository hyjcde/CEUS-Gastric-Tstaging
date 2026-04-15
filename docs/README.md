# 文档总入口

这套文档的目标不是“尽量多”，而是让后续实验始终沿着同一条主线推进。

当前默认阅读入口只有这一页；`docs copy/`、历史迁移材料和实验结果目录都不是当前主线入口。

## 推荐阅读顺序

1. `mainline/project_scope.md`
2. `mainline/tstaging_current_mainline.md`
3. `mainline/research_mainline.md`
4. `data_governance/data_registry_spec.md`
5. `data_governance/data_split_policy.md`
6. `data_governance/data_qc_policy.md`
7. `experiment_governance/experiment_structure.md`
8. `experiment_governance/baseline_plan.md`
9. `evaluation/validation_protocol.md`
10. `visualization/visualization_standard.md`

如果只想快速知道“现在到底做什么”，先看：

- `mainline/tstaging_current_mainline.md`

## Current

这些页面定义当前默认口径，优先级最高：

- `mainline/`：项目范围、阶段定义、当前主线
- `data_governance/`：数据注册、split、QC 和版本边界
- `experiment_governance/`：实验命名、落盘结构、基线顺序
- `evaluation/`：内部/外部验证、病例级评估、错误分析规范
- `visualization/`：出图规范、目录规则、医生审阅材料要求

数据目录本身的正式说明不在 `docs/` 内，而在：

- `../dataset/DATASET_GUIDE.md`

做实验、写统计和核对数据边界时，应优先以 `dataset/DATASET_GUIDE.md`、`manifest.csv` 和当前治理文档为准，而不是旧索引页。

## Operations

这些页面帮助你把主线文档落到脚本、目录和实验执行上：

- `../scripts/README.md`：脚本索引与推荐使用顺序
- `../experiments/baselines/`：当前 baseline 入口目录
- `experiment_governance/baseline_plan.md`：默认基线推进顺序

旧 `Tstaging` 迁移后保留的实验结果证据在：

- `archive_refs/tstaging_migration/`
- `../experiments/archive_tstaging/`

这些目录用于核对历史证据，不替代当前主线规范。

## Archive

以下内容只作为历史参考，不作为当前默认入口：

- `archive_refs/legacy_selected/`
- `archive_refs/legacy_doc_map.md`
- `archive_refs/tstaging_migration/`
- `../docs copy/`

如果你是第一次进入仓库，建议不要从这些位置开始读。

## 这套文档解决什么问题

- 防止实验从一开始又散成多个并行分叉。
- 防止旧结果、旧脚本、旧结论和新主线混在一起。
- 让数据、实验、验证、可视化从一开始就有统一口径。