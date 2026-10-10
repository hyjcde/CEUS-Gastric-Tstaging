# 良恶性数据入口

良恶性数据放在仓库根目录的这个文件夹里，不放进 `dataset/`。`dataset/` 只保留 T 分期。

## 目录说明

- `inflammation/`：良性炎症图像与标注。
- `gastritis_external/`：外部胃炎。原始解码在 `data/raw/gastritis_external_raw_decoded/`，不在这个正式目录里。
- `gastritis_internal_xiehe/`：指到协和炎症裁剪的软链。
- `patients/`：按患者组织的良性病例。
- `clinical_tables/`：良性临床表。
- `metadata/`：良性样本索引和注册表。
- `binary_benign_malignant/`：良恶性划分表。
- `training_views/benign_malignant/`：训练视图。

## 当前口径

- 这里只保留良恶性任务需要的数据，不再混入 T 分期恶性主数据。
- 如果你要做良恶性训练或审计，优先从 `metadata/` 和 `patients/` 开始看。
