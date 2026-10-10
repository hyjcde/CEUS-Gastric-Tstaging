# 良恶性数据入口

良恶性数据放在仓库根目录的这个文件夹里，不放进 `dataset/`。`dataset/` 只保留 T 分期。

## 目录说明

- `inflammation/`：良性炎症图像与标注。协和 2026 胃炎静图在 `inflammation/2026_xiehe/`，临床表是 `clinical_tables/胃炎.xls`（99 次检查）。
- `internal_2026/`：2026 年界面裁剪。和胃炎放在一起，不进 T 分期前瞻。`data/raw/internal_2026` 是指到这里的软链。
- `gastritis_external/`：外部胃炎。原始解码在 `data/raw/gastritis_external_raw_decoded/`，不在这个正式目录里。
- `gastritis_internal_xiehe/`：指到协和炎症裁剪的软链。
- `patients/`：按患者组织的良性病例。
- `clinical_tables/`：良性临床表。
- `metadata/`：良性样本索引和注册表。
- `binary_benign_malignant/`：良恶性划分表。
- `training_views/benign_malignant/`：训练视图。
- `experiments/`：良恶性重训的配置、划分包和报告。仓库根目录的 `benign_malignant` 指到这里。

## 当前口径

- 这里只保留良恶性任务需要的数据和实验，不再混入 T 分期恶性主数据。
- 如果你要做良恶性训练或审计，优先从 `metadata/`、`patients/` 和 `experiments/` 开始看。
- 仓库外有一份同样的副本：`/data/research/gastric/良恶性_副本_20261010`。T 分期训练仍只用 `dataset/train`、`dataset/val`、`dataset/test`。
