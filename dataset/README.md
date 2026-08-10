# 数据集（Dataset）

**七类资产中的正式数据集层**，总地图见 [../REPO_LAYOUT.md](../REPO_LAYOUT.md) §2。原始遗留数据在 [../data/raw/](../data/raw/)（根目录 `胃癌分期` 等为 symlink）。

**交互式说明页（图文并茂）**：[`index.html`](index.html)（`python scripts/build_dataset_inventory.py`）

**机器可读盘点**：[`inventory/index.html`](inventory/index.html) · [`inventory/dataset_inventory.json`](inventory/dataset_inventory.json）

本目录保存当前项目已经整理好的正式数据集，重点服务于胃充盈超声 T 分期相关的分割、定位和后续分类实验。

**先打开这个总览页（含每组三视图样例图）**：[`index.html`](index.html)  
重建：`python3 scripts/build_dataset_visual_overview.py`

## 目录怎么读（整理后）

| 路径 | 角色 |
|------|------|
| `internal/` | 正式内部 SSOT（按年份 + 前瞻） |
| `external/` | 正式外部 **仅 9 家医院** + `statistics/` |
| `static_images/` | 内外部静态图**真实拷贝包** + 配套 Excel |
| `videos/` | 内外部视频**真实拷贝包**（crop_ui + 前瞻 raw） |
| `tables/` | 临床表 / 中心注册表 |
| `training_views/` | 训练软链视图（图+真 cine） |
| `figures/gallery/` | 总览页缩略图 |
| `_quarantine/` | 遗留别名、冒烟残留（**非正式数据**） |
| `inflammation/` · `gastritis_external/` | 良性/胃炎独立队列（非 T1–T4+ 主 split） |

遗留别名 `putian*` / `multicenter` 已迁入 `_quarantine/external_legacy_aliases/`。

当前 T 分期正式数据集只看两块：

- `internal/`：协和内部直接手术数据
- `external/`：外部多中心直接手术数据
- `tables/`：从原始目录整理出来的对应临床表格资产
- `static_images/`：**静态图数据集包**（**真实拷贝**；按 internal/external 分类；含 `original`/`crop_ui`/`crop_roi` + 配套 Excel）。重建：`python3 scripts/build_static_images_view.py --clean`；完整性：`… --audit-only`

另有两套独立良性/炎症数据，不属于 T1/T2/T3/T4+ 分期 split：

- `inflammation/`：从旧 `良恶性` 工作区迁入的良性炎症图像、LabelMe 标注、ROI 和 overlay；配套索引在 `metadata/`，患者目录在 `patients/`，临床表在 `clinical_tables/`。
- `gastritis_external/`：从根目录 `胃炎外部测试集.zip` 整理的外部胃炎/良性数据，包含完整原始解码文件、静态图像预处理结果、视频清单和临床表记录；外部胃炎口径以这个 zip 重新生成的结果为准。

`external_legacy_abs_paths_20260408/` 只是历史整理残留目录，不属于当前正式归档口径，不作为数据集说明对象，也不建议在训练、统计或汇报中引用。

## 数据集定位

这批数据不是最原始压缩包，而是已经经过统一预处理后的任务数据。

原始来源路径用于追溯（symlink 仍指向 `data/raw/legacy_gastric_staging/`）：

- 内部原始来源：`胃癌分期/协和内部数据集/直接手术`
- 外部原始来源：`胃癌分期/外部测试集/胃癌直接手术外部测试集`

当前正式预处理脚本为：

- `scripts/preprocess_direct_surgery_datasets.py`

## 正式数据结构

### `internal/`

内部数据按实验角色拆成两部分：

- `training_2018_2024/`
- `prospective_2025/`

其中：

- `training_2018_2024/` 表示内部训练主池
- `prospective_2025/` 表示前瞻测试池

`training_2018_2024/` 再按年份分层：

- `2018/`
- `2019/`
- `2020_2023/`
- `2024/`

`prospective_2025/` 当前包含：

- `2025/`

### `external/`

外部数据按中心分层（标准名称见 `tables/center_name_registry.csv`）：

- `三明市第二医院/` → 三明市第二医院
- `福建省肿瘤医院/` → 福建省肿瘤医院
- `莆田学院附属医院/` → 莆田学院附属医院
- `莆田市第一医院/` → 莆田市第一医院
- `外省整理/{北京,广东,湖北窦}/` → 北京友谊 / 佛山一院 / **中核五〇四医院**（zip 内「湖北窦」为打包标签，非湖北省中西医结合医院）
- `福建省德化县医院/` → 福建省德化县医院

这部分默认作为独立外部测试集。

## 单个分组的内容

每个内部年份目录或外部中心目录下，都有三套视图：

- `original/`
- `crop_ui/`
- `crop_roi/`

含义如下：

- `original/`：原始视野导出结果
- `crop_ui/`：去除界面边框、保留主要成像区域后的视图
- `crop_roi/`：根据真值 mask 紧框裁切的 ROI 视图

每套视图下面通常包含：

- `images/`
- `annotations/`
- `roi_masks/`
- `overlays/`

可以把这四类内容理解成：

- `images/`：训练或浏览时直接看的图像
- `annotations/`：可回读的标注文件
- `roi_masks/`：二值 mask
- `overlays/`：用于人工 QC 的叠加图

## 数据规模概览

以下统计基于当前正式预处理结果。

### 内部数据总体

- 图像候选：`10726`
- 标注候选：`10714`
- 匹配成功：`10665`
- 成功产出样本：`10659`
- 错误样本：`6`
- 未匹配图像：`61`
- 未匹配标注：`49`

### 内部数据分布

按 `original/images` 统计：

- `2018`：`3638`，约占内部正式样本 `34.13%`
- `2019`：`2853`，约占内部正式样本 `26.77%`
- `2020_2023`：`199`，约占内部正式样本 `1.87%`
- `2024`：`1539`，约占内部正式样本 `14.44%`
- `2025`：`2430`，约占内部正式样本 `22.80%`

从分布上看，内部数据主要集中在 `2018`、`2019` 和 `2025`，其中 `2020_2023` 明显偏少。

这意味着：

- 如果做内部训练，年份分布本身是不均衡的
- 如果做按年份分层评估，`2020_2023` 的统计波动会更大
- `2025` 更适合保留为独立前瞻测试，而不是混入训练

### 外部数据总体

- 图像候选：`2869`
- 标注候选：`2863`
- 匹配成功：`2858`
- 成功产出样本：`2856`
- 错误样本：`2`
- 未匹配图像：`11`
- 未匹配标注：`5`

### 外部数据分布

按 `original/images` 统计：

- `三明市第二医院`：`19`，约占外部正式样本 `0.67%`
- `福建省肿瘤医院`：`436`，约占外部正式样本 `15.27%`
- `莆田学院附属医院`：`2376`，约占外部正式样本 `83.19%`
- `莆田市第一医院`：`25`，约占外部正式样本 `0.88%`

从分布上看，外部数据高度集中在 `莆田学院附属医院`，其它 3 个中心的样本量明显较少。

这意味着：

- 外部总体结果很容易被 `莆田1` 主导
- 汇报外部测试时，建议同时给出“总体结果”和“按中心分层结果”
- 对 `三明` 和 `莆田2` 这类小中心，单独指标可能不稳定，需要结合样本量解释

## 清单文件说明

`internal/` 和 `external/` 根目录下都带有 3 份关键清单：

- `manifest.csv`
- `unmatched_files.csv`
- `errors.csv`

它们分别表示：

- `manifest.csv`：正式进入当前数据集的样本主清单
- `unmatched_files.csv`：图像和标注没有成功匹配的文件
- `errors.csv`：已经匹配成功，但在预处理阶段失败的样本

`gastritis_external/` 另带有独立清单：

- `manifest.csv`：成功完成胃炎静态图像预处理的样本
- `raw_manifest.csv`：zip 内全部原始文件的解码后路径
- `video_manifest.csv`：原始视频资产清单
- `clinical_records.csv`：从 Excel 表格抽取的病例级字段

## 患者级图片+视频管理

`dataset/` 仍是物理样本层；患者级索引不在本目录复制大文件，而是登记在：

- `data/registry/patient_media_sample_index.csv`
- `data/registry/patient_media_registry.csv`

训练导出（含视频列）位于 `pipeline/data/patient_media_tstaging_v1/`。构建命令：

```bash
python scripts/build_patient_media_registry.py
python scripts/export_patient_media_splits.py
```

详细字段与视频语义见 [DATASET_GUIDE.md](DATASET_GUIDE.md) 的「患者级图片+视频注册表」章节。

## 良性/胃炎组图

良性/胃炎代表性组图由以下脚本生成：

- `scripts/generate_gastritis_montages.py`

输出位置：

- `figures/inflammation_benign_montage.png`：迁入的旧良性炎症数据，按年份和莆田批次展示。
- `figures/gastritis_external_crop_ui_overlay_montage.png`：从根目录 `胃炎外部测试集.zip` 重新生成的外部胃炎数据，按中心展示。

## 临床表格资产

当前 `dataset/tables/` 已经开始承接从 `胃癌分期/` 原始目录回收的对应临床表格。

这一层的目标不是直接替代正式注册表，而是先把原始表格整理到和当前数据集同一口径下，避免后续继续到原始目录里反复翻找。

当前包含：

- 原始 Excel 副本
- 按来源拆开的 CSV
- 统一汇总表 `clinical_table_registry.csv`
- 表格索引 `clinical_table_index.csv`
- 中心标准命名对照 `center_name_registry.csv`

这一步特别适合承接：

- 患者级注册表构建
- T 分期标签映射
- 按年份和中心的患者统计
- 后续 split 审核

## 当前数据质量信号

从当前结果看，整体预处理成功率较高，但仍有少量问题样本。

主要问题类型包括：

- 空 mask，无法生成 ROI 紧框
- 图像与标注命名不一致，导致配对失败
- 个别外部中心存在命名异常或特殊字符

这些问题不会影响已经成功产出的主体数据，但会影响最终统计口径和后续患者级注册。

## 训练使用建议

如果目标是做 Stage 1 分割或定位，当前建议优先使用：

- 训练输入：`internal/training_2018_2024/*/crop_ui/`
- 前瞻测试：`internal/prospective_2025/2025/crop_ui/`
- 外部测试：`external/*/crop_ui/`

原因是：

- `crop_ui/` 去掉了界面噪声，更接近稳定训练输入
- `crop_roi/` 依赖真值 mask 紧框裁剪，直接用于 Stage 1 分割会有信息泄漏风险
- `original/` 可以保留作对照、复核或可视化，但不一定是最稳的第一版训练输入

如果目标是胃炎/良性炎症区域分割或良恶性辅助任务，旧训练口径可从 `inflammation/` 和 `metadata/benign_master_registry.csv` 开始；外部测试口径可从 `gastritis_external/processed_images/*/crop_ui/` 读取图像和 mask，并用 `gastritis_external/manifest.csv`、`clinical_records.csv` 做病例级追溯。

## 当前还缺的正式资产

虽然数据已经完成预处理，但要进入正式实验，仍建议继续补齐：

- 患者级 split 清单
- 数据注册表
- QC 状态总表
- T 分期标签映射表
- 按中心和年份的患者级统计表

## 一句话总结

当前 `dataset/` 的正式口径可以概括为：

- 内部数据按年份组织，并单独保留 `2025` 前瞻测试
- 外部数据按中心组织，并默认作为独立外部测试
- 旧良性炎症数据已迁入 `inflammation/`，胃炎外部数据已整理为 `gastritis_external/`，二者作为良性/炎症独立任务数据，不混入 T 分期
- 三套视图中，`crop_ui/` 最适合作为第一版训练输入
- T 分期文档中的“数据分布”应以 `internal/` 和 `external/` 为准，不包含历史残留目录
