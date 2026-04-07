# 分割与可视化总账

> 更新日期：2026-03-19
> 这份文档把项目里已经做过的分割、定位、可视化和 MedDINOv3 / SAM / MedSAM 相关材料统一整理起来，目标不是再发散新实验，而是先把现成结果归档清楚，再对照主线判断下一步要补什么。

---

## 这份文档要解决什么

当前项目里已经有很多现成资产：

- 分割模型已经跑过多轮
- 定位器已经做过多种版本
- MedDINOv3 有完整工作区和评估结果
- SAM2 / SAM3 / MedSAM 都有探索痕迹
- 可视化脚本和医生审阅材料也已经积累不少

但这些材料分散在不同目录里，如果不先统一整理，就很容易出现“做了很多，但很难回头复盘”的问题。  
这份总账的目标就是把这些资产按主线重新归类，方便后面继续做统一统计。

---

## 一、分割主线资产

### 1.1 主分割模型

当前主线里，分割不是辅助项，而是 Stage 1。

代表性资产：

- `pipeline/experiments/segmentation/`
- `pipeline/experiments/segmentation_strict/`
- `pipeline/experiments/segmentation_sam2/`
- `pipeline/experiments/segmentation_sam2_maskprompt/`
- `pipeline/experiments/segmentation_sam3/`
- `pipeline/experiments/segmentation_dinov2/`
- `scripts/02_training/train_stomach_segmentation.py`
- `scripts/02_training/train_stomach_segmentation_patient_level.py`
- `scripts/02_training/train_v8_segmentation.py`
- `scripts/02_training/finetune_nnunet_benign.py`

### 1.2 关键分割结果

| 路线 | 结果摘要 | 当前理解 |
|:---|:---|:---|
| `segmentation/comprehensive_eval` | 内部平均 Dice 约 0.65 | 说明传统分割基线能用，但外部泛化不足 |
| `segmentation_strict/test_results.json` | 前瞻 Dice 约 0.713，putian_2024 Dice 约 0.433 | 更稳，但外部仍明显退化 |
| `segmentation_sam2/cascade_eval_results.json` | GT prompt 条件下 Dice 很高，cascade 在外部略优于纯 UNet | 证明 SAM2 本身可用，但自动 prompt 还不稳 |
| `segmentation_sam3/sam3_zeroshot_results.json` | zero-shot 基本为 0 | 说明文本零样本不适合当前任务 |
| `segmentation_dinov2/training_history.csv` | val_dice 约 0.63 | 仍属探索，不是主线结论 |

### 1.3 predicted masks

当前用于分类输入的 `predicted_masks` 仍然是重要资产：

- 位置：`pipeline/data/predicted_masks/`
- 当前数量：约 12,193 张
- 来源：UNet+ConvNeXt-Tiny (smp)
- 作用：
  - 作为 `mask4ch` 第 4 通道
  - 作为 predicted ROI 的来源

---

## 二、定位器与候选框资产

定位器已经单独整理到：

- `docs/LOCATOR_PIPELINE_SUMMARY.md`

这里不重复展开全部细节，只保留和分割最相关的结论：

1. 定位器不是为了单纯刷检测指标，而是为了把病灶更稳定地送进后续分类。
2. `YOLO / YOLO11 / RT-DETR` 和分割驱动的 bbox 提议器，都是“先定位、再裁 ROI”的路线。
3. 对分类成功率最关键的是 Recall 和 ROI 成功率，不是单纯的 mAP。

---

## 三、MedDINOv3 工作区

### 3.1 这个工作区里已经有什么

`MedDINOv3_Workspace/` 不是一个空壳，它已经包含完整的分割与评估资产：

- `MedDINOv3_Workspace/README.md`
- `MedDINOv3_Workspace/VALIDATION_SUMMARY.md`
- `MedDINOv3_Workspace/MedDINOv3/`
- `MedDINOv3_Workspace/fullimage_evaluation_results/evaluation_results.json`
- `MedDINOv3_Workspace/segmentation_evaluation/evaluation_results.json`
- `MedDINOv3_Workspace/end2end_evaluation/end2end_results.json`
- `MedDINOv3_Workspace/nnunet_fullimage_eval/nnunet_fullimage_results.json`
- `MedDINOv3_Workspace/segmentation_twostage/results_summary.json`
- `MedDINOv3_Workspace/segmentation_fullimage_results/results_summary.json`
- `MedDINOv3_Workspace/segmentation_fullimage_v2/results_summary.json`
- `MedDINOv3_Workspace/roi_segmentation_fixedcrop/results_summary.json`

### 3.2 当前应如何理解它

MedDINOv3 在主线里更像是 **Stage 1 分割组件**，不是分类主模型。

它的价值主要有三点：

- 作为分割 backbone / segmentation head 的实验来源
- 作为两阶段推理链中的定位与精修组件
- 作为可视化和 demo 的承载工作区

### 3.3 典型结论

- `fullimage_evaluation_results/evaluation_results.json` 的 Dice 很高，说明 full-image 分割方向有能力
- `segmentation_twostage/results_summary.json` 表明两阶段策略可行
- `end2end_evaluation/end2end_results.json` 则更接近真实链路，但 ROI Dice 仍不够稳

---

## 四、SAM2 / SAM3 / MedSAM

### 4.1 SAM2

SAM2 是目前最值得保留讨论的候选路线之一，但它的关键不是“能不能跑”，而是**怎么给它一个足够好的 prompt**。

相关资产：

- `pipeline/experiments/segmentation_sam2/`
- `pipeline/experiments/segmentation_sam2_maskprompt/`
- `scripts/utils/generate_medsam_masks.py`（与 prompt / mask 相关的流程相邻）

当前理解：

- `SAM2 GT-bbox prompt` 可以作为上限参考
- `SAM2 cascade` 说明“UNet 先粗定位，再交给 SAM2 精修”是可行的
- 但自动 prompt 的质量仍是核心瓶颈

### 4.2 SAM3

SAM3 目前更像一个已经验证过的失败方向：

- `segmentation_sam3/sam3_zeroshot_results.json`
- 文本 zero-shot 在当前超声任务上几乎没有有效分割

结论：

- 可以保留为历史探索记录
- 不建议继续作为主推进方向

### 4.3 MedSAM

MedSAM 相关材料主要是历史尝试：

- `scripts/utils/download_medsam.py`
- `scripts/utils/generate_medsam_masks.py`
- `scripts/utils/generate_medsam_masks_v2.py`
- `docs/archived_reports/09_进展报告_VLP时期.md`

当前理解：

- 它属于探索过的分割/提示方案
- 现在更适合放在归档里，不作为主线推进

---

## 五、可视化资产

### 5.1 主要可视化脚本

可视化脚本已经很多，主要集中在：

- `scripts/04_visualization/results/`
- `scripts/04_visualization/publication/`

常见类型包括：

- 分割对比图
- GradCAM
- ROI vs mask 对比
- hard case 图册
- 医生审阅图册
- 论文/汇报图

### 5.2 当前最像“可视化总入口”的地方

按当前结构来看，最值得作为可视化总入口的文档是：

- `docs/figures_summary_20260228_0303/README.md`
- `docs/reporting_assets_20260318/README_INDEX.md`

这两个位置比零散脚本更适合做总目录。

### 5.3 医生审阅与解释材料

这类材料应该单独归入“审计”和“证据链”：

- `results/doctor_review/README.md`
- `results/doctor_review/index.html`
- `results/doctor_blind_test/README.md`
- `docs/meeting_summary_20260305/DOCTOR_VALIDATION_ATLAS.md`
- `docs/CONVEXITY_GT_VS_SEG_STATUS.md`
- `docs/FAIR_MIXED_ROI_TEST_20260316.md`

---

## 六、这些资产如何对应主线

| 资产类型 | 归属主线 | 作用 |
|:---|:---|:---|
| 分割模型 | Stage 1 分割 | 定位病灶、生成 mask / bbox |
| 定位器 | Stage 1a 定位 | 提供更稳的候选框和 ROI |
| MedDINOv3 | Stage 1 分割 | 分割 backbone / demo / 评估工作区 |
| SAM2 | Stage 1 分割 | 候选分割器、prompt 驱动精修 |
| SAM3 | 历史探索 | 已证明显著不适合当前任务 |
| MedSAM | 历史探索 | 已尝试，归档保留 |
| 可视化 | 证据链 / 审计 | 帮助复核、汇报和医生审阅 |

---

## 七、下一步应该怎么整理

建议按这个顺序继续：

1. 先把分割和定位器总账对齐，确认每条路线的“实验名 → 脚本 → 结果目录 → 指标”。
2. 再把 MedDINOv3 / SAM2 / MedSAM / 可视化 统一挂到主线里，区分“主线”“候选”“归档”。
3. 最后把这些资产和分类总账联动起来，看哪条前置路线真的提高了分类成功率。

---

## 八、关联文档

- [`MAINLINE.md`](../MAINLINE.md)
- [`LOCATOR_PIPELINE_SUMMARY.md`](LOCATOR_PIPELINE_SUMMARY.md)
- [`PIPELINE_EXPERIMENT_RECORDS.md`](PIPELINE_EXPERIMENT_RECORDS.md)
- [`INDEX.md`](INDEX.md)
- [`CURRENT_PROJECT_FRAMEWORK_AND_MASTER_PLAN.md`](CURRENT_PROJECT_FRAMEWORK_AND_MASTER_PLAN.md)
- [`figures_summary_20260228_0303/README.md`](figures_summary_20260228_0303/README.md)
- [`reporting_assets_20260318/README_INDEX.md`](reporting_assets_20260318/README_INDEX.md)
