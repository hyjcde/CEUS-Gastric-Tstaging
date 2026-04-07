# 数据索引

这是 `dataset/` 的快速入口页。数据边界和正式口径请以 [`../dataset/DATASET_GUIDE.md`](../dataset/DATASET_GUIDE.md) 为准。

## 当前权威文件

- 元数据总入口：[`../dataset/metadata/INDEX.md`](../dataset/metadata/INDEX.md)
- 数据总说明：[`../dataset/DATASET_GUIDE.md`](../dataset/DATASET_GUIDE.md)
- 活动批次清单：[`../dataset/metadata/active_batch_manifest.json`](../dataset/metadata/active_batch_manifest.json)
- 批次刷新报告：[`../dataset/metadata/registry_refresh_report.md`](../dataset/metadata/registry_refresh_report.md)
- 批次注册总表：[`../dataset/metadata/batch_registry.csv`](../dataset/metadata/batch_registry.csv)
- 注册对齐审计：[`../dataset/metadata/registry_alignment_audit/summary.csv`](../dataset/metadata/registry_alignment_audit/summary.csv)
- ROI 一致性报告：[`../dataset/metadata/roi_consistency_report.md`](../dataset/metadata/roi_consistency_report.md)

## 推荐工作流

1. 先看 `DATASET_GUIDE.md`，确认这批数据是否已经进入正式口径。
2. 再看 `active_batch_manifest.json`，确认哪些批次可以直接进入训练或测试。
3. 如有新批次或新 ROI，先跑预检脚本：

```bash
python pipeline/scripts/project_governance_preflight.py
```

4. 如果结果仍显示 `partial` 或 `physical_only`，先补注册和对齐，再进入正式实验。

## 这些内容默认只作参考

- `dataset/metadata/backup_old/`
- 任何旧版或镜像版索引文件
- 只包含历史快照而未同步到当前主文档的统计材料
