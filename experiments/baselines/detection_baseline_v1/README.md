# detection_baseline_v1

## 目标

建立新的定位基线，固定数据版本、模型版本、ROI 生成规则和验证口径。

## 开始前必须确认

- 数据注册表已完成
- 患者级 split 已固定
- 定位标签来源明确

## 运行后必须落盘

- 配置快照
- 训练日志
- 最优权重说明
- 患者级或病例级结果表
- 内部验证摘要
- 外部验证摘要
- ROI 成功率与 fallback 率

## 当前推荐起点

- 固定 split 已预先生成：`data/splits/detection/yolo11_lesion_holdout_cropui/split_manifest.csv`
- 配置文件：`configs/detection/yolo11/baseline_lesion_holdout_cropui.yaml`
- 数据准备：`python scripts/prepare_yolo_detection_dataset.py --config configs/detection/yolo11/baseline_lesion_holdout_cropui.yaml`
- 训练启动：`python scripts/run_yolo_detection_train.py --config configs/detection/yolo11/baseline_lesion_holdout_cropui.yaml`
- 正式评估：`python scripts/run_yolo_detection_eval.py --config configs/detection/yolo11/baseline_lesion_holdout_cropui.yaml --experiment-dir <实验目录>`
- QC overlay：`python scripts/generate_yolo_detection_qc_overlays.py --dataset-root data/processed/detection/yolo11_lesion_holdout_cropui`
- 详细流程说明：`experiments/baselines/detection_baseline_v1/YOLO11_BASELINE_PIPELINE.md`

## 当前脚本职责

- `scripts/freeze_detection_internal_holdout_split.py`：按疑似患者号冻结 `train / val / internal_test`
- `scripts/build_yolo_detection_dataset.py`：把 `LabelMe polygon` 转成 YOLO 框标注，并导出 `prospective_test`、`external_test`
- `scripts/prepare_yolo_detection_dataset.py`：一键串联 split 和数据导出
- `scripts/run_yolo_detection_train.py`：启动 `YOLOv11` 训练，记录完整训练日志，并接入 `SwanLab`
- `scripts/run_yolo_detection_eval.py`：对 `internal_test`、`prospective_test`、`external_test` 做正式评估并回写实验摘要
- `scripts/generate_yolo_detection_qc_overlays.py`：生成带真值框和病例对应信息的 `qc_overlays`

## SwanLab 记录建议

- 当前默认配置为 `mode: cloud`，会把实验同步到你已登录的 `SwanLab` 账号
- 如果机器无法联网，可以临时把配置改回 `mode: local` 或 `mode: offline`
- `prepare_yolo_detection_dataset.py` 现在默认会复用已有 `split_manifest.csv`，只有显式传 `--force-resplit` 才会重切

## 当前实验目录会额外记录

- `logs/train_stdout.log`
- `logs/train_error_traceback.log`
- `logs/evaluation_stdout.log`
- `logs/evaluation_error_traceback.log`
- `yolo_run_manifest.json`
- `evaluation/evaluation_manifest.json`
- `evaluation/overall_summary.md`
- `qc_overlays_manifest.csv`
