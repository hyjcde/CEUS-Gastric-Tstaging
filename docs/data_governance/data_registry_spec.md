# 数据注册规范

## 目的

所有可以进入实验的数据，必须先进入注册表。没有进入注册表的数据，不应直接进入训练或测试。

## 最低必填字段

每条记录至少包含以下字段：

- `sample_id`：样本唯一标识
- `patient_id`：患者唯一标识
- `case_id`：病例或检查级标识
- `center`：中心来源
- `year`：年份
- `exam_type`：检查类型
- `task_role`：用于定位、分割、分类中的哪一条线
- `image_path`：图像路径
- `mask_path`：mask 路径，没有则留空
- `roi_path`：ROI 路径，没有则留空
- `label_tstage`：T 分期标签
- `label_source`：标签来源
- `qc_status`：QC 状态
- `split`：train / val / internal_test / external_test / holdout
- `data_version`：数据版本号
- `notes`：补充说明

## 注册原则

- `patient_id` 是患者级切分和去重的核心字段。
- 同一患者不得跨训练和测试集合。
- 同一图像如果经过重命名、裁剪或格式变换，仍需能追溯回原始样本。
- 一切临时样本都必须显式标记为临时，不能混进正式口径。

## 版本管理

建议数据版本使用：

`dataset_vYYYYMMDD`

例如：

- `dataset_v20260407`
- `dataset_v20260420`

每次版本变化都要记录：

- 新增了哪些批次
- 删除了哪些异常样本
- 哪些标签被修订
- 哪些 split 被重建

## 模板文件

- `data/registry/dataset_registry_template.csv`
- `data/splits/split_manifest_template.csv`
