# 文档总入口

这套文档的目标不是“尽量多”，而是让后续实验始终沿着同一条主线推进。

## 推荐阅读顺序

1. `mainline/project_scope.md`
2. `mainline/research_mainline.md`
3. `data_governance/data_registry_spec.md`
4. `data_governance/data_split_policy.md`
5. `experiment_governance/experiment_structure.md`
6. `evaluation/validation_protocol.md`
7. `visualization/visualization_standard.md`

## 文档分区

- `mainline/`：项目目标、阶段定义、主线流程
- `data_governance/`：数据注册、split、QC、版本管理
- `experiment_governance/`：实验命名、落盘结构、基线与对照规则
- `evaluation/`：内部/外部验证、病例级评估、错误分析规范
- `visualization/`：出图规范、目录规则、医生审阅材料要求
- `archive_refs/`：旧项目中仍值得保留的摘要和参考文档

## 这套文档解决什么问题

- 防止实验从一开始又散成多个并行分叉。
- 防止旧结果、旧脚本、旧结论和新主线混在一起。
- 让数据、实验、验证、可视化从一开始就有统一口径。

## 历史文档处理方式

旧项目里只保留少量与当前主线直接相关的文档，放在：

- `archive_refs/legacy_selected/`
- `archive_refs/legacy_doc_map.md`

这些文件用于查历史，不作为当前默认入口。
