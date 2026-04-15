# SMS configs

这里保存 `SLab-Medical-Segmentation` 在当前项目中的配置模板。

当前默认模板：

- `base_2d_unet.yaml`：2D 二值分割 baseline，首个默认模型是 `unet_2d`

## 配置字段说明

### `paths`

- `sms_root`：上游 SMS 框架所在目录，当前默认是 `third_party/sms`
- `prepared_dataset_root`：整理后的 SMS 数据目录
- `experiment_root`：正式实验证据包输出根目录

### `experiment`

- `task_name`：实验主任务名，默认 `segmentation`
- `model_alias`：写入实验名的简写
- `data_version`：数据版本标签
- `run_id`：同一天内的重复实验编号

### `train`

- 这里的字段会被 `scripts/run_sms_train.py` 组装成 SMS 的训练命令
- `image_size` 不直接通过 SMS CLI 传递，而是写入运行时配置，让 `dataset/dsa.py` 读取

### `inference`

- `save_probability`：是否保留 SMS 的概率图
- `calculate_sms_metrics`：是否同时启用 SMS 自带 metrics 统计

## 推荐流程

1. 先运行 `scripts/prepare_sms_gastric_2d_dataset.py` 准备数据
2. 再运行 `scripts/run_sms_train.py --config configs/segmentation/sms/base_2d_unet.yaml`
3. 训练完成后运行 `scripts/run_sms_inference.py`

如果你要比较多个模型，建议复制 `base_2d_unet.yaml`，只改：

- `experiment.model_alias`
- `experiment.data_version`
- `experiment.run_id`
- `train.model_name`
