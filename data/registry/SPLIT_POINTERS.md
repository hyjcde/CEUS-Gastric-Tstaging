# 正式建模 Split 指针（冻结）

训练与评估**只读**下列 CSV，勿扫描 `data/raw/`：

| Split | 路径 |
|-------|------|
| train | `pipeline/data/tstaging_4class_region_contrastive_full/regions/train_clinical.csv` |
| val | `pipeline/data/tstaging_4class_region_contrastive_full/regions/val_clinical.csv` |
| test_external | `pipeline/data/tstaging_4class_region_contrastive_full/regions/test_external_clinical.csv` |
| test_external_newzip | `pipeline/data/tstaging_4class_region_contrastive_full/regions/test_external_newzip_clinical.csv` |
| test_prospective | `pipeline/data/tstaging_4class_region_contrastive_full/regions/test_prospective_clinical.csv` |

物理影像口径：`dataset/internal/manifest.csv`、`dataset/external/manifest.csv`。

新实验 README 必须写明 `data_version` + 上表 split 路径。详见 [dataset/DATASET_GUIDE.md](../../dataset/DATASET_GUIDE.md)。
