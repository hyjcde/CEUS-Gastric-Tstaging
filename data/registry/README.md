# 数据注册表说明

本目录保存进入正式实验前必须维护的表格。

## 机器可读登记（由脚本生成）

```bash
python scripts/build_dataset_registry.py
```

产出：

- `dataset_registry.csv` — 数据集与 split 角色
- `patient_registry.csv` — 各 split 的 `patient_id` 计数
- `data/metadata/data_sources_inventory.csv` — zip / 临床表来源清单

## Split 指针（冻结）

见 [SPLIT_POINTERS.md](SPLIT_POINTERS.md)。

## 模板（参考）

- `dataset_registry_template.csv`
- `split_manifest_template.csv`
