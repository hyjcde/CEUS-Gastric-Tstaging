# 可视化规范

## 统一样式

本项目所有正式可视化默认使用以下规则：

- 背景：黑底
- 字体：`Times New Roman`
- 输出优先格式：`png` 和 `pdf`
- 图像命名使用英文和下划线，避免空格

## 目录划分

可视化结果统一按任务落盘：

- `results/visualizations/detection/`
- `results/visualizations/segmentation/`
- `results/visualizations/tstage/`
- `results/visualizations/error_cases/`
- `results/visualizations/doctor_review/`

## 正式图和调试图分开

- 正式图：用于汇报、论文、医生审阅
- 调试图：用于开发排查，不应与正式图混存

## 每类任务建议保留的图

### 定位

- 检测框叠加图
- ROI 成功与失败对比图
- fallback 案例图

### 分割

- 原图 / GT mask / predicted mask / overlay 四联图
- 内部与外部中心代表病例
- hard case 图册

### T 分期分类

- 混淆矩阵
- 关键错误病例图
- GradCAM 或等价解释图

## 命名建议

建议使用：

`<task>_<split>_<figureType>_<date>`

例如：

- `segmentation_external_overlay_20260407.png`
- `tstage_internal_confusion_matrix_20260407.png`

## 脚本要求

任何正式图都应尽量来自脚本，而不是手工截图。
