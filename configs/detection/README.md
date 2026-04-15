# detection configs

这里保存定位模型的配置模板和冻结配置。

当前已补充：

- `yolo11/baseline_lesion_holdout_cropui.yaml`：基于 `dataset/internal/training_2018_2024` 的病灶检测定位基线配置

配套脚本：

- `scripts/prepare_yolo_detection_dataset.py`：按配置一键冻结 split 并导出 YOLO 数据集
- `scripts/run_yolo_detection_train.py`：按配置启动 YOLO 训练、接入 `SwanLab`，并生成完整训练日志
- `scripts/run_yolo_detection_eval.py`：按配置对固定测试集做评估并生成摘要
