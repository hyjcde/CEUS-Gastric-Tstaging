# 数据集（Dataset）

这里只放 T 分期，而且是已经能按病人放进训练或测试的正式数据。原始视频、还没有标签的裁剪、良恶性、检测和分割都不在这里。

总图见 [../REPO_LAYOUT.md](../REPO_LAYOUT.md)。更早的计数和预处理说明见 [DATASET_GUIDE.md](DATASET_GUIDE.md)。

## 顶层

| 路径 | 内容 |
|------|------|
| `train/` | 协和 2018-2024 回顾，冻结名单 1062 人 |
| `val/` | 同一回顾队列的固定验证，128 人。合同文件里叫 dev |
| `test/prospective/` | 前瞻，协和 2025，425 人 |
| `test/external/` | 外部，9 家医院，485 人 |
| `patient_clinical_master.csv` | 三份队列共用的临床总表 |
| `tables/` | 中心名、覆盖率和还没有拆进队列的表 |
| `task_datasets/t_staging/` | 冻结划分 CSV，不复制影像 |

划分用 `task_datasets/t_staging/wadi_research_freeze_v20260827/`。不要用旧的 `task_datasets/t_staging/splits/train.csv`，那张表把前瞻和莆田混进了 train。不从 1062/128 里再切一份内部 test。

年份目录里的图原来混着 train 和 val，已经按冻结文件名拆开。不在这两份名单里的 2018-2024 文件在 `data/processed/tstaging_outside_freeze/`，没有放进 train 或 val。

## 旧路径

冻结 CSV 里的路径没有改。下面这些名字还在，是软链：

- `internal/training_2018_2024/` 里的文件指到 `train/` 或 `val/`
- `internal/prospective_2025` 指到 `test/prospective`
- `external/<医院>` 指到 `test/external/<医院>`
- `videos/` 里的前瞻和外院视频指到 `test/` 下面
- `training_views` 指到 `task_datasets/t_staging/training_views`

`inflammation`、`gastritis_external`、`patients`、`clinical_tables` 也是软链，实体在仓库根目录的 `良恶性/`。胃炎原始解码在 `data/raw/gastritis_external_raw_decoded/`。

## 不在本目录的数据

- 原始视频：`data/raw/videos_raw/`。2026 年裁剪在 `良恶性/internal_2026/`，和胃炎放在一起，不进前瞻。`data/raw/internal_2026` 只是软链。
- 重裁剪和半成品：`data/processed/`
- 胃腔检测和分割视图：`data/detection_seg/`
- 重复副本和隔离：`archive/dataset_copies/`、`archive/dataset_quarantine/`
- 生成的说明页：`docs/dataset/`
