# 旧文档迁移对照表

## 当前保留到新项目的旧文档

这些旧文档被复制到 `archive_refs/legacy_selected/`，作为历史参考：

- `MAINLINE_BRIEF.md`
- `T分期数据利用综合方案_20260325.md`
- `LOCATOR_PIPELINE_SUMMARY.md`
- `SEGMENTATION_AND_VISUALIZATION_SUMMARY.md`
- `DATA_INDEX.md`
- `mask_overlay_QC流程_20260325.md`
- `方向性标注试点方案_20260325.md`
- `四分类近期边界与执行护栏_20260325.md`

## 为什么只保留这些

因为它们分别覆盖了下面几类当前仍有直接价值的信息：

- 主线概览
- 数据利用方案
- 定位与分割历史总结
- 数据入口与 QC 经验
- T2/T3 边界相关约束
- 方向性标注这种可能的后续扩展线索

## 暂不迁移的类别

以下内容不进入新项目的默认主线：

- 论文草稿
- 汇报工程
- 会议逐字稿
- 镜像浏览包
- `node_modules`
- 大批历史实验日志和零散报告
- 与胃充盈超声 T 分期不直接相关的专题材料

## 使用方式

- 当前工作默认先看新 `docs/` 里的规范文档。
- 只有需要追溯历史背景时，再看 `archive_refs/legacy_selected/`。
