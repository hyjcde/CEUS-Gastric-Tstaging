# tstage_baseline_v1

## 目标

在 Stage 1 输入稳定后，再建立新的 T 分期分类 baseline。

## 启动条件

- 定位 baseline 已完成
- 分割 baseline 已完成
- 进入分类的输入形式已固定

## 冻结 run 指针

见 [run_pointer.txt](run_pointer.txt) → `pipeline/experiments/tree/.../tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301`

登记：[experiments/registry.csv](../../registry.csv) 行 `tstage_baseline_v1` / `structure_mask4ch_clinical22`。

## 运行后必须落盘

- 配置快照
- 训练日志
- 患者级预测表
- 混淆矩阵
- 各分期召回率
- 内部/外部验证摘要
