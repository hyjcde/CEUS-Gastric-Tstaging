# 胃充盈超声 T 分期项目

这是胃充盈超声 T 分期项目的当前主工作区。

这个版本不再沿用旧 `Tstaging` 里“文档、实验、结果、脚本混在一起”的方式，而是按主线管理：

1. 数据治理
2. 定位与分割
3. T 分期分类
4. 内部/外部验证
5. 可视化与报告

## 项目定位

这个仓库当前关注的是一条更收敛的研究工程主线：

- 先把数据边界、数据治理和病例级划分定清楚
- 先把病灶检测与分割这些 Stage 1 基础资产做稳
- 再决定哪些信号适合进入后续的 T 分期分类
- 所有正式结论优先看当前主线文档，不以历史汇报稿或旧实验流水账为准

如果你只想快速理解“这个仓库现在在做什么”，建议优先读：

1. `docs/README.md`
2. `docs/mainline/tstaging_current_mainline.md`
3. `dataset/DATASET_GUIDE.md`
4. `scripts/README.md`

## 先看哪里

- 当前正式文档入口：`docs/README.md`
- 当前正式文档树：`docs/`
- 数据治理规范：`docs/data_governance/`
- 实验治理规范：`docs/experiment_governance/`
- 基线实验入口：`experiments/baselines/`
- 旧 `Tstaging` 迁移材料：`docs/archive_refs/tstaging_migration/`
- 旧 T 分期实验证据：`experiments/archive_tstaging/`

`docs copy/` 只作为历史整理、汇总复盘和人工总结层使用，不是当前默认阅读入口。

## 仓库结构速览
- `docs/`：当前主线文档、治理规范、验证与可视化规范
- `dataset/`：当前正式数据集目录和数据说明
- `scripts/`：按阶段整理的脚本索引与执行入口
- `experiments/baselines/`：当前默认 baseline 的入口目录
- `experiments/archive_tstaging/`：旧 T 分期实验的结果证据与归档材料
- `docs/archive_refs/`：迁移过来的历史摘要、映射和参考文档
- `docs copy/`：历史整理层、人工汇总层和导出副本存放区

## 这次迁移保留了什么

- 从旧 `Tstaging` 迁入了 T 分期主线相关文档、论文导出稿和实验结果证据。
- 迁入内容统一放在 `archive_refs/tstaging_migration/` 与 `experiments/archive_tstaging/`，只作为历史参考和审计材料。
- 旧 `dataset/` 没有迁入这里；新的 T 分期数据将继续在当前工作区按新规则补建。

## 当前默认工作顺序

当前默认不是一开始就扩大量分类对照，而是按下面顺序推进：

1. 先确认数据边界、来源命名、split 和 QC 规则
2. 先固定病灶检测 baseline
3. 再固定分割 baseline 和 ROI 相关资产
4. 在证据链足够稳定后，再推进 T 分期分类或相关方法验证
5. 所有正式结果都按内部/外部、病例级和可复现实验目录组织

具体规范和细节分别看：

- 数据治理：`docs/data_governance/`
- 实验治理：`docs/experiment_governance/`
- 验证协议：`docs/evaluation/validation_protocol.md`
- 出图规范：`docs/visualization/visualization_standard.md`

## 当前默认原则

- 先把数据边界、命名、split 和 QC 定死，再开始训练。
- 先把定位模型和分割模型训练扎实，再让 Stage 2 的 T 分期分类接上来。
- 所有正式验证都按患者级组织，避免图像级泄漏。
- 所有正式图统一黑底、`Times New Roman` 字体。

## 阅读与使用建议

- 想看当前正式口径：从 `docs/README.md` 开始
- 想看当前真正主线：读 `docs/mainline/tstaging_current_mainline.md`
- 想核对数据范围：读 `dataset/DATASET_GUIDE.md`
- 想找脚本入口：读 `scripts/README.md`
- 想看当前 baseline：看 `experiments/baselines/`
- 想查历史判断或旧证据：去 `docs/archive_refs/` 和 `experiments/archive_tstaging/`

## 说明

这个仓库里保留了不少历史材料，是为了追溯、审计和复盘，不是为了让当前主线重新变成多入口并行状态。

默认规则只有一条：当前怎么做，以 `docs/`、`dataset/`、`scripts/` 和当前 baseline 目录中的正式说明为准。
