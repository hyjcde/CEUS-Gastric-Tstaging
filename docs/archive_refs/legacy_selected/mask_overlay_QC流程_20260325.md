# Mask / Overlay QC 流程

> 更新日期：2026-03-25
> 用途：把 `mask/overlay` 的排查从“知道有问题”变成“有清单、有优先级、有修复动作”。

## 当前为什么要先做这件事

目前已经确认至少存在以下风险：

- `overlay` 位置不对
- 良性 `inflammation` 批次中存在旧版命名和旧版 overlay 风格
- `annotation` 可能缺失、空形状或历史修复不一致
- 2025 相关数据和部分良性来源需要优先人工复核

如果继续把这些样本直接送进训练或解释性分析，容易把数据问题误判成模型问题。

## 现在固定采用的 QC 工作流

## 第一步：先自动建清单

新增脚本：

```bash
python pipeline/scripts/build_mask_overlay_qc_manifest.py
```

默认会扫描：

- `dataset/inflammation`
- `dataset/internal`
- `dataset/external`

并输出：

- `pipeline/experiments/qc/mask_overlay_qc_manifest.csv`
- `pipeline/experiments/qc/mask_overlay_qc_summary.md`

## 第二步：按优先级人工复核

脚本会给每个样本分一个优先级：

- `P0`：缺 annotation 或 annotation 元数据严重异常
- `P1`：缺 overlay、空 shapes、2025 高优先级批次
- `P2`：良性来源重点复核、命名/overlay 风格不一致
- `P3`：常规抽查

人工复核时，只需要按 CSV 回填下面几列：

- `manual_qc_status`
- `manual_issue_type`
- `manual_fix_priority`
- `manual_notes`

## 第三步：把问题分成 4 类

建议人工复核后，把问题统一归到这 4 类：

1. `index_or_name_issue`
2. `annotation_regen_needed`
3. `overlay_regen_needed`
4. `no_issue`

这样后面才方便批量修。

## 第四步：优先修哪些批次

当前默认优先顺序：

1. `inflammation/2025`
2. `inflammation` 中 `yan` / `ptyz` 来源
3. 会议里已经反复提到的错样、疑似错位样本
4. 后续错误分析里出现频率最高的病例

## 现有可复用的修复脚本

仓库里已经有历史修复脚本，不需要从零开始：

- `scripts/01_data_prep/fix_inflammation_annotations.py`
- `scripts/01_data_prep/fix_overlays_and_annotations.py`
- `scripts/01_data_prep/fix_internal_annotations.py`

建议流程是：

1. 先靠 manifest 找到问题编号
2. 再决定调用哪类修复脚本
3. 修完后重新跑 manifest

## 建议的每周节奏

### 周内

- 先跑一版 manifest
- 从 `P0/P1` 中抽样人工复核
- 回填问题类型

### 周末前

- 汇总待修复编号
- 统一决定哪些可以批量重建 annotation / overlay
- 修复后再跑一版 manifest 对照

## 和模型分析怎么配合

QC 不应孤立做。它应该和下面两类分析联动：

1. `GradCAM` 看起来离病灶很近，但 IoU 很差的样本
2. `T2/T3` 或良恶性错误分析里反复出现的病例

也就是说，优先检查“模型看起来像对，但指标像错”的样本。

## 建议保留的最终产出

这条线至少应形成 3 个稳定产出：

1. 一份最新版 `mask_overlay_qc_manifest.csv`
2. 一份高优先级问题编号表
3. 一份“已修复 / 待修复 / 暂不处理”的状态页

## 推荐命令

```bash
python pipeline/scripts/build_mask_overlay_qc_manifest.py
```

如需只扫良性数据，可手动指定：

```bash
python pipeline/scripts/build_mask_overlay_qc_manifest.py \
  --dataset-roots dataset/inflammation
```

## 关联文档

- `docs/meeting_summary_20260305/DATA_DEVICE_ROI_QC_AUDIT.md`
- `docs/会议总结_黄逸君_20260324_两次会议.md`
- `pipeline/scripts/build_mask_overlay_qc_manifest.py`
