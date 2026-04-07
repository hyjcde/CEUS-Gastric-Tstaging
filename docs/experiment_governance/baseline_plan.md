# 基线实验路线图

## 原则

现在的基线不是为了追求“最花哨”，而是为了建立后续一切对照的起点。

## 第一阶段基线

### 1. 定位 baseline

至少固定以下内容：

- 数据版本
- 检测模型版本
- 评价指标
- ROI 生成方式
- fallback 规则

### 2. 分割 baseline

至少固定以下内容：

- 数据版本
- 分割模型版本
- loss 与训练策略
- 内部验证与外部验证
- predicted mask 导出规则

## 第二阶段基线

### 3. T 分期分类 baseline

只有当前两个条件满足时，才进入默认主线：

- 定位 baseline 已经稳定
- 分割 baseline 已经稳定

## 当前推荐顺序

1. 先做 `detection_baseline_v1`
2. 再做 `segmentation_baseline_v1`
3. 再评估是否进入 `tstage_baseline_v1`

对应的实验入口目录已经预留在：

- `experiments/baselines/detection_baseline_v1/`
- `experiments/baselines/segmentation_baseline_v1/`
- `experiments/baselines/tstage_baseline_v1/`
