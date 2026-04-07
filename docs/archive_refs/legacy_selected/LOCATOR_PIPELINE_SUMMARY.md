# 定位器与候选框总账

> 更新日期：2026-03-19
> 定位：这份文档专门汇总项目里所有“先定位、再裁 ROI、再分类”的相关实验与脚本，重点是把历史上分散的 detector / locator / bbox / ROI proposal 记录统一到一张表里。

---

## 为什么要单独整理定位器

当前项目已经非常明确地证明了一件事：**分类成功率不是只靠分类器本身就能解决的**。  
只要上游定位不稳，ROI 会退化为 center crop，分类输入就会失真，最终影响 T 分期判断。

因此，定位器不能继续只作为“某个辅助实验”来看，而应该单独统计：

- 它能不能稳定找到病灶
- 它生成的 ROI 能不能进入分类链路
- 它是否真的提高了最终分类成功率

---

## 项目里真实存在的定位器路线

### 1. YOLO / YOLO11 / 项目 v9 系列

仓库里没有找到官方意义上的 `YOLOv9` 独立实现；这里的 `v9` 更像项目版本名。  
定位器主线实际上包含的是 YOLO11、RT-DETR、以及一些统一化的 locator 变体。

相关脚本：

- `scripts/01_data_prep/prepare_v9_super_grand_yolo.py`
- `scripts/01_data_prep/create_yolo_dataset_v2.py`
- `scripts/01_data_prep/convert_crop_json_to_yolo.py`
- `scripts/01_data_prep/prepare_yolo_combined.py`
- `scripts/01_data_prep/prepare_yolo_detection_data.py`
- `scripts/02_training/train_yolo11.py`
- `scripts/02_training/train_yolo11_domain_robust.py`
- `scripts/02_training/train_v9_grand_yolo_overnight.py`
- `scripts/02_training/train_v9_grand_rtdetr_overnight.py`
- `scripts/02_training/train_v13_ultimate_robust_locator.py`
- `scripts/03_evaluation/benchmark_yolo_vs_rtdetr.py`
- `scripts/03_evaluation/benchmark_full_pipeline_yolo_vs_rtdetr.py`
- `scripts/utils/compare_localization_methods.py`
- `scripts/utils/compare_localization_v2.py`

### 2. 分割驱动的 bbox 提议器

这条路线不是直接做检测框，而是先做分割，再从 mask 中提取 bbox 或 ROI。

相关脚本：

- `scripts/utils/coarse_to_fine_tstaging.py`
- `scripts/utils/two_stage_roi_pipeline.py`
- `scripts/utils/meddino_multi_roi_pipeline.py`
- `scripts/utils/meddino_end2end_pipeline.py`
- `pipeline/scripts/build_predicted_roi_dataset.py`
- `pipeline/scripts/predict_roi_from_segmentation.py`
- `pipeline/scripts/analyze_predicted_roi_fallback.py`

---

## 现成的定位器结果

| 实验名 | 位置 | 关键指标 |
|:---|:---|:---|
| `v9_grand_overnight_training` | `archived/experiments_yolo/01_Detection/v9_grand_overnight_training/` | Precision 81.2%，Recall 76.8%，mAP50 78.5%，mAP50-95 52.3% |
| `v7_unified_localization_finetune` | `archived/runs_backup/detect/v7_unified_localization_finetune/` | Precision 81.282%，Recall 71.654%，mAP50 78.55%，mAP50-95 43.639% |
| `v7_unified_localization` | `archived/runs_backup/detect/v7_unified_localization/` | Precision 59.216%，Recall 56.401%，mAP50 59.002%，mAP50-95 29.499% |
| `multiclass_v4_localization` | `archived/experiments_yolo/01_Detection/YOLO11_MultiClass_Results/multiclass_v4_localization/` | Precision 88.509%，Recall 27.009%，mAP50 34.784%，mAP50-95 24.732% |
| `leviathan_locator` | `archived/experiments_yolo/05_Integrated/V19_Leviathan_Sovereign_20260106_0117/checkpoints/localization/leviathan_locator/` | Precision 65.638%，Recall 57.584%，mAP50 54.33%，mAP50-95 35.835% |

### 结果怎么理解

- **高 Recall 的定位器更适合做 ROI 提议器**，因为漏检会直接把后面的分类输入搞坏。
- **高 Precision 但低 Recall** 的定位器，不适合单独承担病灶定位主线。
- **目前最关键的不是哪一个名字最好看，而是它能不能稳定转成分类提升**。

---

## 定位器如何接到分类

当前项目里，定位器主要有三种接法：

1. **检测框直接裁 ROI**  
   用 detector 先找框，再裁出局部图，送给分类器。

2. **分割 mask 转 bbox / ROI**  
   先分割，再把 mask 变成 bbox 或 ROI，用于后续分类。

3. **多 ROI / 多候选框融合**  
   先提多个候选框，再做 ROI 特征融合，避免单个框漏掉关键信息。

对应的完整流程，已经在这些脚本里出现过：

- `scripts/utils/coarse_to_fine_tstaging.py`
- `scripts/utils/two_stage_roi_pipeline.py`
- `scripts/utils/meddino_multi_roi_pipeline.py`
- `scripts/utils/classification_focused_pipeline.py`

---

## 和分类成功率的关系

定位器最终不是为了“自己分数高”，而是为了让分类更稳。

当前可以明确看到的链路是：

- 定位失败 → ROI 退化成 center crop
- ROI 退化 → 分类输入丢失病灶信息
- 分类输入变差 → 外部 AUC / T2 识别进一步下降

所以后面整理实验时，不能只统计 detector 的 mAP，要同时统计：

- ROI 成功率
- center crop fallback 率
- 分类 AUC 变化
- T2/T3 混淆变化

---

## 建议的下一步统计口径

为了避免“做了很多实验，但最后像白做了一样”，建议把定位器总账统一成下面这几类：

| 类别 | 需要统计的内容 |
|:---|:---|
| 检测器本身 | Precision、Recall、mAP50、mAP50-95 |
| ROI 生成 | predicted ROI 成功率、fallback 率 |
| 分类影响 | 前瞻 AUC、外部 AUC、T2 recall |
| 数据来源 | internal / prospective / external / putian_2024 / multicenter |
| 代码入口 | 训练脚本、评估脚本、归档结果目录 |

---

## 当前结论

1. 项目里确实有一条完整的定位器历史，不是零散的零星脚本。
2. 真正最值得继续整理的，不是“有没有 detector”，而是“detector 如何影响分类成功率”。
3. `YOLOv9` 这次更像项目版本名，不是官方 YOLOv9 架构。
4. 下一步最应该做的是把所有 locator / ROI proposal / detector / bbox 结果统一统计成一张表，再接分类结果一起看。

---

## 关联文档

- [`MAINLINE.md`](../MAINLINE.md)
- [`MAINLINE_BRIEF.md`](MAINLINE_BRIEF.md)
- [`CURRENT_PROJECT_FRAMEWORK_AND_MASTER_PLAN.md`](CURRENT_PROJECT_FRAMEWORK_AND_MASTER_PLAN.md)
- [`PIPELINE_EXPERIMENT_RECORDS.md`](PIPELINE_EXPERIMENT_RECORDS.md)
- [`EXPERIMENT_INDEX.md`](EXPERIMENT_INDEX.md)
- [`archived_reports/07_YOLO实验总索引.md`](archived_reports/07_YOLO实验总索引.md)
- [`archived_reports/08_两阶段分割优化报告.md`](archived_reports/08_两阶段分割优化报告.md)
- [`reports/Coarse_to_Fine_Report.md`](reports/Coarse_to_Fine_Report.md)
