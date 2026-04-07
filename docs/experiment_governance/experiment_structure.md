# 实验结构与命名规范

## 实验目录应该放什么

每个正式实验目录都应该是“证据包”，至少包含：

- 配置快照
- 数据版本标识
- 训练日志
- 最优权重说明
- 患者级结果表
- 内部验证结果
- 外部验证结果
- README 简述

## 推荐命名方式

建议格式：

`<task>_<model>_<dataVersion>_<date>_<runid>`

例如：

- `detection_yolo11_dataset_v20260407_20260407_r001`
- `segmentation_unet_dataset_v20260407_20260407_r001`
- `tstage_dualbranch_dataset_v20260420_20260422_r001`

## task 取值建议

- `detection`
- `segmentation`
- `tstage`
- `analysis`
- `qc`

## 每次实验必须回答的 3 个问题

1. 用的是哪版数据
2. 用的是哪份配置
3. 相比哪个 baseline 有什么变化

## 不允许的做法

- 直接把结果散落到根目录
- 只保留截图，不保留患者级结果表
- 改了配置却不保存配置快照
- 只看验证集结果，不做固定测试集验证
