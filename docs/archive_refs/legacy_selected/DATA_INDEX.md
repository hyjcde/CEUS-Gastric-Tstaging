# 数据索引

这是历史归档区保留的数据索引页，不是当前 `dataset/` 的正式入口。

当前数据边界和正式口径请以 [`../../../dataset/DATASET_GUIDE.md`](../../../dataset/DATASET_GUIDE.md) 为准。

## 当前正式入口

- 数据总说明：[`../../../dataset/DATASET_GUIDE.md`](../../../dataset/DATASET_GUIDE.md)
- 临床表说明：[`../../../dataset/tables/README.md`](../../../dataset/tables/README.md)
- 脚本索引：[`../../../scripts/README.md`](../../../scripts/README.md)

## 推荐工作流

1. 先看 `DATASET_GUIDE.md`，确认这批数据是否已经进入正式口径。
2. 再根据 `manifest.csv`、`errors.csv` 和临床表索引确认当前可用范围。
3. 如需核对当前治理脚本或预检流程，先看 `scripts/README.md`，再运行相关脚本：

```bash
python pipeline/scripts/project_governance_preflight.py
```

4. 如果结果仍显示 `partial` 或 `physical_only`，先补齐当前正式数据治理链路，再进入实验。

## 为什么这页不再列旧 metadata 入口

- 当前仓库的正式 `dataset/` 已不再沿用旧 `metadata/` 口径。
- 本页早期提到的 `dataset/metadata/*` 路径在当前仓库中并不是现行权威入口。
- 这页保留的意义主要是帮助理解旧资料如何迁移到现在的 `dataset/` 结构。

## 这些内容默认只作参考

- 旧 `metadata` 口径、镜像版索引和历史统计快照
- 任何旧版或镜像版索引文件
- 只包含历史快照而未同步到当前主文档的统计材料
