# YOLO11 Detection Baseline Pipeline

## 文档目的

这份文档专门解释当前 `YOLOv11` 病灶检测 baseline 的完整链路，回答 4 个问题：

1. 训练前做了什么准备
2. 训练本体是怎么跑的
3. 输入和输出分别是什么
4. 每次实验应该怎样做到“代码和文档自成一体”

当前对应的主配置文件是：

- `configs/detection/yolo11/baseline_lesion_holdout_cropui.yaml`

当前对应的主脚本是：

- `scripts/prepare_yolo_detection_dataset.py`
- `scripts/freeze_detection_internal_holdout_split.py`
- `scripts/build_yolo_detection_dataset.py`
- `scripts/run_yolo_detection_train.py`
- `scripts/run_yolo_detection_eval.py`
- `scripts/generate_yolo_detection_report.py`
- `scripts/generate_yolo_detection_qc_overlays.py`
- `scripts/yolo_detection_runtime.py`

## 一句话概括当前流程

当前流程可以理解成 3 个阶段：

1. 先把内部训练池按病例级近似规则固定成 `train / val / internal_test`
2. 再把 `LabelMe polygon` 标注转换成 `YOLO detection` 需要的框标注
3. 最后用 `Ultralytics YOLO11` 训练，并对 `internal_test / prospective_test / external_test` 做固定评估

如果把“统一可视化报告”也算进去，更完整的理解是 4 个阶段：

1. 数据准备
2. 模型训练
3. 固定评估
4. 统一报告与可视化

## 训练流程总览

### 阶段 1：准备数据

执行命令：

```bash
python scripts/prepare_yolo_detection_dataset.py --config configs/detection/yolo11/baseline_lesion_holdout_cropui.yaml
```

这个脚本本身不直接做全部工作，而是负责串联两个子步骤：

1. `freeze_detection_internal_holdout_split.py`
2. `build_yolo_detection_dataset.py`

当前 `crop_ui` 对应的内部固定 split 已经预先生成在：

- `data/splits/detection/yolo11_lesion_holdout_cropui/split_manifest.csv`
- `data/splits/detection/yolo11_lesion_holdout_cropui/split_summary.json`

这意味着后面重复准备数据时：

- 默认会直接复用这份 split
- 不会每次重新切分
- 只有显式传 `--force-resplit` 才会重新生成

### 阶段 2：启动训练

执行命令：

```bash
python scripts/run_yolo_detection_train.py --config configs/detection/yolo11/baseline_lesion_holdout_cropui.yaml
```

这个脚本会：

1. 读取项目配置
2. 创建新的实验目录
3. 保存配置快照和训练命令
4. 初始化 `SwanLab`
5. 调用 `Ultralytics YOLO` 开始训练
6. 把训练日志、状态、权重路径和摘要写回实验目录

### 阶段 3：固定评估

执行命令：

```bash
python scripts/run_yolo_detection_eval.py --config configs/detection/yolo11/baseline_lesion_holdout_cropui.yaml --experiment-dir <实验目录>
```

这个脚本会：

1. 读取训练产出的 `best.pt`
2. 固定评估 `internal_test`
3. 固定评估 `prospective_test`
4. 固定评估 `external_test`
5. 保存每套测试源的摘要
6. 汇总成总评估文档
7. 继续把评估结果写入 `SwanLab`

### 阶段 4：统一报告与可视化

执行命令：

```bash
python scripts/generate_yolo_detection_report.py --experiment-dir <实验目录> --config configs/detection/yolo11/baseline_lesion_holdout_cropui.yaml
```

这个脚本会把所有模型统一整理成一个固定模板：

1. 读取 `ultralytics/results.csv`
2. 生成训练过程曲线图
3. 读取 `evaluation/overall_summary.json`
4. 生成 `internal_test / prospective_test / external_test` 的统一对比图
5. 生成标准 Markdown 报告

同时，当前流程已经把它自动接入：

1. 训练脚本结束后会先生成训练曲线报告
2. 评测脚本结束后会补全固定测试集对比图和最终报告

## 方法说明

### 1. 数据视图

当前 baseline 默认使用：

- `crop_ui`

原因是：

- `crop_ui` 去掉了界面边框和一部分无关噪声
- 比 `original` 更利于先建立稳定的检测基线
- 比 `crop_roi` 更安全，因为 `crop_roi` 本身依赖真值 ROI，有信息泄漏风险

### 2. 标注形式

当前原始标注是：

- `LabelMe polygon json`

检测训练需要的是：

- `YOLO bbox txt`

所以当前做法是：

1. 读取每个 `json` 里的病灶多边形点集
2. 取这些点的最小外接矩形
3. 转成 `YOLO` 需要的归一化框格式

这意味着当前 baseline 的核心任务其实是：

- 用多边形病灶标注，训练一个单类别的病灶检测器

### 3. 类别定义

当前配置只有 1 个类别：

- `lesion`

配置里通过 `label_to_class` 指定映射关系：

- `lesion -> lesion`

也就是说：

- 只要 `LabelMe` 里的形状标签是 `lesion`
- 就会被转换成类别 `0`

### 4. split 策略

当前内部训练池来自：

- `dataset/internal/training_2018_2024`

切分目标是：

- `train`
- `val`
- `internal_test`

当前脚本不是按图片随机切，而是先尝试从样本名末尾推断“病例号”，再按病例分组切分。

默认规则是：

- 使用正则 `^(.*?)[-_]\d+$`

它的直观含义是：

- 如果样本名最后一段像 `0024261-10`
- 就把最后的帧号 `-10` 去掉
- 把 `0024261` 当作病例级近似 ID

这一步的目的，是尽量避免：

- 同一个病例的不同图像同时进入训练和测试

### 5. 模型和训练方式

当前默认模型是：

- `yolo11n.pt`

这表示：

- 不是从零训练
- 而是从官方预训练权重开始微调

默认训练任务是：

- `detect`

默认核心训练参数包括：

- `imgsz: 640`
- `epochs: 100`
- `batch: 16`
- `patience: 30`
- `optimizer: auto`
- `deterministic: true`
- `seed: 666`

数据增强主要沿用了 `Ultralytics YOLO` 常见的检测增强：

- 色彩扰动
- 平移
- 缩放
- 左右翻转
- `mosaic`

### 6. 评估方式

训练完成后，当前固定评估 3 套数据：

1. `internal_test`
2. `prospective_test`
3. `external_test`

评估时读取的核心指标是：

- `mAP50-95`
- `mAP50`
- `mAP75`
- `precision`
- `recall`

如果是多类别任务，还会记录每类的 `mAP50-95`。  
当前因为只有 `lesion` 一个类别，所以每类结果和总体结果基本一致。

## 输入是什么

可以把当前链路的输入分成 4 层。

### 第 1 层：项目配置输入

主配置文件：

- `configs/detection/yolo11/baseline_lesion_holdout_cropui.yaml`

它控制的内容包括：

- 数据路径
- 数据视图
- 类别定义
- split 参数
- 训练参数
- 评估参数
- `SwanLab` 参数

### 第 2 层：原始训练数据输入

内部训练池：

- `dataset/internal/training_2018_2024/*/crop_ui/images`
- `dataset/internal/training_2018_2024/*/crop_ui/annotations`

前瞻测试：

- `dataset/internal/prospective_2025/2025/crop_ui/images`
- `dataset/internal/prospective_2025/2025/crop_ui/annotations`

外部测试：

- `dataset/external/*/crop_ui/images`
- `dataset/external/*/crop_ui/annotations`

### 第 3 层：split 输入

`freeze_detection_internal_holdout_split.py` 的输入是：

- 内部训练池图像
- 内部训练池标注
- 视图类型
- 病例号推断规则
- split 比例和随机种子

### 第 4 层：训练输入

真正喂给 `YOLO` 的不是原始 `LabelMe` 数据，而是已经整理好的标准数据集：

- `data/processed/detection/yolo11_lesion_holdout_cropui/dataset.yaml`

这个目录下会有：

- `images/train`
- `images/val`
- `images/internal_test`
- `labels/train`
- `labels/val`
- `labels/internal_test`

## 输出是什么

当前输出也可以分成 4 层。

### 第 1 层：split 输出

目录：

- `data/splits/detection/yolo11_lesion_holdout_cropui/`

主要文件：

- `split_manifest.csv`
- `split_summary.json`

作用是：

- 固定这次内部切分
- 说明每个样本属于哪个 split
- 记录每年、每个 split 的样本和病例统计

### 第 2 层：YOLO 数据集输出

目录：

- `data/processed/detection/yolo11_lesion_holdout_cropui/`

主要文件：

- `dataset.yaml`
- `dataset_manifest.json`
- `exports_manifest.csv`
- `prepare_manifest.json`

作用是：

- 形成真正可训练的 `YOLO` 数据集
- 记录图像与标注转换关系
- 记录各 split 的图像数、框数、空标签数

同时还会生成评估源：

- `eval_sources/prospective_test/`
- `eval_sources/external_test/`

各自也有：

- `dataset.yaml`
- `manifest.csv`

如果需要做人工 QC 或病例回查，还可以额外生成：

- `qc_overlays/train/`
- `qc_overlays/val/`
- `qc_overlays/internal_test/`
- `eval_sources/prospective_test/qc_overlays/test/`
- `eval_sources/external_test/qc_overlays/test/`

对应的总清单文件是：

- `qc_overlays_manifest.csv`

这份清单会把下面这些信息重新连起来：

- `patient_id`
- `sample_id`
- `export_id`
- `target_image`
- `target_label`
- `overlay_path`

### 第 3 层：训练输出

目录：

- `experiments/detection/<exp_name>/`

主要文件：

- `project_config_snapshot.yaml`
- `train_args_snapshot.yaml`
- `train_command.sh`
- `README.md`
- `yolo_run_manifest.json`
- `logs/train_stdout.log`
- `logs/train_error_traceback.log`
- `train_summary.json`
- `ultralytics/weights/best.pt`
- `ultralytics/weights/last.pt`
- `ultralytics/results.csv`
- `ultralytics/args.yaml`

作用是：

- 保存这次实验到底用了什么配置
- 保存这次训练是怎么启动的
- 保存训练过程日志
- 保存权重和训练指标
- 保存运行状态是成功、失败还是 dry-run

### 第 4 层：评估输出

目录：

- `experiments/detection/<exp_name>/evaluation/`

主要文件：

- `evaluation_manifest.json`
- `overall_summary.json`
- `overall_summary.md`
- `internal_test/summary.json`
- `prospective_test/summary.json`
- `external_test/summary.json`
- `logs/evaluation_stdout.log`
- `logs/evaluation_error_traceback.log`

作用是：

- 固定保存这次权重在 3 套测试源上的评估结果
- 汇总成一个总摘要，避免只看某一套测试结果

### 第 5 层：统一报告输出

目录：

- `experiments/detection/<exp_name>/report/`

主要文件：

- `report/YOLO_DETECTION_REPORT.md`
- `report/report_manifest.json`
- `report/visualizations/training_curves.png`
- `report/visualizations/evaluation_summary.png`

作用是：

- 把所有模型的训练过程图统一成同一套风格
- 把 `internal_test / prospective_test / external_test` 的结果统一成同一套对比图
- 给每次实验一个固定的人读入口，方便后续做模型横向对照

## SwanLab 在当前流程里记录什么

当前 `SwanLab` 的作用不是替代实验目录，而是额外提供：

- 训练过程中的 epoch 级指标记录
- 最终训练摘要
- 各测试源评估摘要
- 配置和实验元信息统一展示

当前默认模式是：

- `cloud`

含义是：

- 训练和评估会同步到当前已经登录的 `SwanLab` 账号
- 同时实验目录里仍然保留本地日志和摘要文件

如果你希望同步到云端，可以：

1. 先执行 `swanlab login`
2. 把配置里的 `mode` 改成 `cloud`

## 当前流程里“输入 -> 处理 -> 输出”的直观理解

可以把它想成一条流水线：

1. 原始超声图像 + `LabelMe` 病灶多边形
2. 按病例切分成 `train / val / internal_test`
3. 多边形转最小外接框
4. 整理成 `YOLO` 标准数据集
5. 用 `YOLO11n` 训练
6. 产出最佳权重
7. 用最佳权重评估内部、前瞻、外部测试
8. 把训练日志、评估摘要和 `SwanLab` 记录全部落盘

## 当前方法的优点

- 简单直接，适合做第一版检测基线
- `crop_ui` 视图比原图更稳定
- 用预训练 `YOLO11n`，启动成本低
- 已经把正式评估拆成固定入口
- 训练与评估日志都开始统一落盘

## 当前方法的边界

当前这条链路依然有几个需要记住的边界：

- 病例级切分目前仍然是“按文件名规则推断”，不是正式患者注册表驱动
- 当前是单类别检测，不区分更细的病灶类型
- 当前评估是检测指标层面，还没有接通 ROI 成功率和 fallback 率
- 当前代码虽然已经比之前更完整，但“代码本体”仍然在 `scripts/` 下，不在每个实验目录里单独复制一份

## 为什么说每次实验最好“代码和文档自成一体”

如果一个实验只留下权重和截图，后面会很难回答这些问题：

- 当时用的是哪版配置
- 当时用的是哪版脚本逻辑
- 当时为什么这么切分
- 结果异常时该去看哪个日志

所以我建议每个正式实验至少都要包含下面这些东西：

1. 配置快照
2. 训练命令
3. 评估命令
4. 训练日志
5. 评估日志
6. 运行状态清单
7. 总结文档

## 当前推荐的“自成一体”最小清单

对于每个正式实验目录，建议至少保留：

- `README.md`
- `project_config_snapshot.yaml`
- `train_args_snapshot.yaml`
- `train_command.sh`
- `yolo_run_manifest.json`
- `logs/train_stdout.log`
- `logs/train_error_traceback.log`
- `evaluation/evaluation_manifest.json`
- `evaluation/overall_summary.md`
- `logs/evaluation_stdout.log`
- `logs/evaluation_error_traceback.log`
- `report/YOLO_DETECTION_REPORT.md`
- `report/report_manifest.json`
- `report/visualizations/training_curves.png`

如果后面要做得更彻底，我建议再补两类东西：

- `qc_overlays_manifest.csv` 和一套 `qc_overlays/`
- 脚本版本快照
- 一份专门说明本次实验目标、改动点、预期和已知问题的实验说明文档

## 建议的下一步

如果目标是把这条 baseline 进一步做成完全正式版本，建议按这个顺序继续补：

1. 把 ROI 生成和 fallback 规则接到检测输出后面
2. 把 ROI 成功率写进 `evaluation/overall_summary.md`
3. 给每次正式实验自动保存一份“脚本快照清单”或 git commit 信息
4. 如果后面存在多版模型对照，再补一份统一的实验对比总表
