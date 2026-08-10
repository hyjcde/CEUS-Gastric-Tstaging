# 数据层（data/）

介于 **原始数据** 与 **正式数据集 [dataset/](../dataset/)** 之间：注册表、split、元数据、标注、中间 zip。

| 子目录 | 七类中的位置 | 说明 |
|--------|--------------|------|
| [raw/](raw/) | **原始数据** | 遗留中文目录实体（根 symlink 指向此） |
| [registry/](registry/) | **数据集** | 样本/患者注册表模板 |
| [splits/](splits/) | **数据集** | 冻结 split manifest |
| [processed/](processed/) | **数据集** | 可再生产物（如临床报告特征） |
| [metadata/](metadata/) | 治理 | 资产清单、迁移日志、验证 JSON |
| [annotation/](annotation/) | **数据集** | 方向标注 batch 与输出 |
| [staging_review/](staging_review/) | 导入现场 | 审阅/解压队列（非正式 dataset） |

正式影像与 `manifest.csv` 在 **[../dataset/](../dataset/)**，不在此目录。

内部归位细则：[INTERNAL_LAYOUT.md](INTERNAL_LAYOUT.md) · 工作区盘点：[metadata/workspace_inventory_summary.md](metadata/workspace_inventory_summary.md)

详见 [../REPO_LAYOUT.md](../REPO_LAYOUT.md)。
