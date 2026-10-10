# 从这里开始

打开本仓库时**只看这一页**。其它 1000+ 文档与 symlink 不要从根目录逐个猜。

## 你要做什么？→ 去哪个目录

| 目标 | 唯一入口 |
|------|----------|
| 理解系统怎么组成 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 查「文件该放哪」 | [REPO_LAYOUT.md](REPO_LAYOUT.md) |
| 读临床主线 / 当前在做什么 | [docs/mainline/gastric_tstaging_project_framework_zh.md](docs/mainline/gastric_tstaging_project_framework_zh.md) → [tstaging_current_mainline.md](docs/mainline/tstaging_current_mainline.md) |
| 查数据口径与 manifest | [dataset/DATASET_GUIDE.md](dataset/DATASET_GUIDE.md) |
| 拿 T 分期 / 良恶性建模表 | [dataset/task_datasets/README.md](dataset/task_datasets/README.md) |
| 跑检测 / 分割 / 预处理脚本 | [scripts/README.md](scripts/README.md) |
| 训练 T 分期 / 跑实验 | [pipeline/README.md](pipeline/README.md) + [configs/](configs/) |
| 干净对比 T 分期模型 | [tstaging_lab/README.md](tstaging_lab/README.md) |
| 从头想 MedSigLIP 训练 | [external/medsiglip/README.md](external/medsiglip/README.md)（根上 `medsiglip/` 是兼容链接） |
| 从头训良恶性 | [benign_malignant/README.md](benign_malignant/README.md) |
| 查实验与 checkpoint | [experiments/registry.csv](experiments/registry.csv) + [models/README.md](models/README.md) |
| 开 Web 工作台 / 标注工具 | [apps/README.md](apps/README.md) |
| 整理论文、原稿和重点文献 | [paper/README.md](paper/README.md) |
| 维护仓库路径 | [MAINTENANCE.md](MAINTENANCE.md) |
| 治理执行口径（维护者） | [docs/project_governance.md](docs/project_governance.md) |

## 根目录只有这些「工作区」

```text
apps/          平台（Next.js）
archive/       历史归档（只读）
artifacts/     大文件：zip、权重、results（不进 Git）
configs/       正式实验配置
data/          注册表、raw、metadata
dataset/       正式数据集（训练以此为准）
docs/          文档（规范 + 主线）
experiments/   实验记录入口
external/      第三方本地依赖，以及 MedSigLIP 副本 external/medsiglip/
models/        模型索引（实体在 artifacts / pipeline）
paper/         论文原稿、笔记和重点文献聚合入口
pipeline/      训练框架 + Agent
scripts/       CLI 脚本
tstaging/      physical T-staging pack (train / val / prospective / external)
tstaging_lab/  T 分期实验台：锁定数据/评测，一实验一卡片，总账在 ledger.csv
benign_malignant/ 良恶性重训工作区（划分 CSV / 配置 / 报告）
runtime/       阅片运行态（医生操作与病例草稿；不要再堆整份快照）
_compat/       旧路径兼容 symlink（勿当正式入口）
```

**不要**从根目录乱点：`docs copy`、中文目录名、`.zip`、`yolo11*.pt` 等已收到 `_compat/` 或 `artifacts/`。

## 文档太多怎么办

1. 只读 Tier A（约 10 篇）：见 [docs/ARCHITECTURE.md §5](docs/ARCHITECTURE.md)
2. 查全表：[docs/DOCUMENT_MAP.md](docs/DOCUMENT_MAP.md)
3. 单次实验报告：进 `pipeline/experiments/reports/<实验名>/`

## 一键自检

```bash
python scripts/verify_repo_paths.py
```
