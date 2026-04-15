# detection

这里存放正式的定位模型实验。

每个实验应回答：

- 检测效果如何
- ROI 是否稳定生成
- 是否改善了后续链路

当前推荐先从 `detection_baseline_v1` 对应的 `YOLOv11` 配置起步：

- `configs/detection/yolo11/baseline_lesion_holdout_cropui.yaml`

推荐执行顺序：

- 先准备数据：`python scripts/prepare_yolo_detection_dataset.py --config configs/detection/yolo11/baseline_lesion_holdout_cropui.yaml`
- 再训练：`python scripts/run_yolo_detection_train.py --config configs/detection/yolo11/baseline_lesion_holdout_cropui.yaml`
- 最后评估：`python scripts/run_yolo_detection_eval.py --config configs/detection/yolo11/baseline_lesion_holdout_cropui.yaml --experiment-dir <实验目录>`
