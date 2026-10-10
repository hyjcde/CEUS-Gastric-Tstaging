# 两类任务数据集入口

2026-08-19 新建。这里只放**建模 CSV 和说明**，不拷贝、不移动 freeze 影像。

| 任务 | 目录 | 标签 | 不要做什么 |
|------|------|------|------------|
| T 分期 | `t_staging/wadi_research_freeze_v20260827/`（75% 目标主研究冻结）；`t_staging/maincenter_retrospective_v20260821/`（协和单中心对照）；`t_staging/threecenter_joint_unseen_v20260826/`（协和 + 莆田学院 + 中核） | `0/1/2/3` = T1 / T2 / T3 / T4+ | 现有 2025 / external 只作 audit，不作模型选择；不要用上一层 `t_staging/splits/`（20260531，train 含外院）；不要把良性行加进来 |
| 良恶性 | `../../良恶性/binary_benign_malignant/` | `0` = 良性/炎症，`1` = 胃癌 | 不要把这里的良性当成 T 分期负例直接并表；当前合同是多中心联合训练 + 未见中心测试，见该目录 `SPLIT_POLICY.md` |

物理影像仍在：

- T 分期：`dataset/train/`、`dataset/val/`、`dataset/test/prospective/`、`dataset/test/external/`。旧的 `dataset/internal/`、`dataset/external/` 是软链
- 良恶性影像：仓库根目录 `良恶性/`。`dataset/gastritis_external/` 和 `dataset/inflammation/` 是指过去的软链

重建：

```bash
python3 scripts/build_binary_multicenter_joint_unseen.py
python3 scripts/build_task_datasets.py
python3 scripts/build_tstaging_maincenter_retrospective.py
python3 scripts/build_tstaging_threecenter_joint_unseen.py
python3 scripts/build_tstaging_wadi_research_freeze_20260827.py
```

`training_views/` 仍是按中心的软链视图，给 DataLoader 扫目录用。**写训练表、对路径、对标签，先读本目录。**

标签完整性：见 [INTEGRITY.md](INTEGRITY.md)。复核：`python3 scripts/audit_task_datasets.py`  
原始层对照：见 [SOURCE_INVENTORY.md](SOURCE_INVENTORY.md)。重建：`python3 scripts/build_task_datasets_source_inventory.py`  
阅片 150 / 50 对照：见 [READER_V150_JOIN.md](READER_V150_JOIN.md)。逐例总表（原临床/原视频/原图）：`reader_v150_catalog.csv`。重建：`python3 scripts/join_reader_v150_to_task_datasets.py`  
含医院号、原视频路径和 200 例字段的受限溯源表只放在 `data/staging_review/reader_v150_source_crosswalk/`，不进入本建模目录或 Git。  
公网/本地 sidecar 原文和现网标注：`docs/clinical_validation/reader_study_v150/origin_snapshots/`
