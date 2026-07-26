# 胃癌 T 分期正式数据集说明

## 文档定位

这份文档描述的是**当前 `dataset/` 目录下仍在使用的正式数据集**，不是历史上那套按患者注册的全量资料库。

当前 T 分期正式口径只包含三部分：

- `dataset/internal/`：协和内部直接手术数据
- `dataset/external/`：外部多中心直接手术数据
- `dataset/tables/`：与当前正式数据集对应的临床表整理层

独立良性/炎症口径已整理到：

- `dataset/gastritis_external/`：从 `胃炎外部测试集.zip` 解码整理，包含完整原始文件、静态图像预处理结果、视频清单和临床表记录。

这意味着：

- 旧文档中的 `patients/`、`metadata/` 和患者级 `patient_info.json` 口径，**已经不适用于当前 `dataset/`**
- 良性/炎症/胃溃疡数据属于 **良恶性分类、炎症分割、负例/筛查或视频泛化任务**，不能直接并入 T1/T2/T3/T4+ 分期 split
- 当前最可靠的统计主口径是：
  - 样本级正式统计：`dataset/internal/manifest.csv`、`dataset/external/manifest.csv`
  - 问题样本统计：`unmatched_files.csv`、`errors.csv`
  - 临床表辅助统计：`dataset/tables/clinical_table_registry.csv`
  - 中心标准命名对照：`dataset/tables/center_name_registry.csv`

## 多中心标准命名对照

项目里同时存在**标准医院名称**（对外汇报、论文 Table 1）和**遗留目录/source 名称**（代码与 manifest 实际读取）。两者不能混用，但可以通过注册表互相映射。

完整机器可读映射见：`dataset/tables/center_name_registry.csv`

### 命名约定

- **folder_name**：`dataset/external/` 下当前使用的物理目录名（已与标准医院名称对齐）。
- **legacy_folder_aliases**：旧目录名，仅用于兼容历史脚本/路径检索。
- **source_prefix**：建模 CSV 中 `source` 字段前缀。
- **读表约定（中心清单）**：
  - `良/恶性`：`有/有` = 有良性 / 有恶性
  - `视频/图片`：`有/有` = 有视频 / 有静态图片

### 全部中心一览

| 标准医院名称 | 遗留目录/source | T 分期 manifest | 建模 split | 帧数（manifest） | 患者（临床表） | 良/恶性（清单） | 视频/图片（清单） | 项目状态 |
| --- | --- | --- | --- | ---: | ---: | --- | --- | --- |
| 福建医科大学附属协和医院 | `internal/` / `int/*` | 是 | train / val / test_external / test_prospective | 10,659 | 1,883 | 有/有 | 有/有 | 已入库 |
| 莆田学院附属医院 | `莆田学院附属医院` / `ext/putian*` | 是 | train / val / test_external | 2,376 | 344 | 有/有 | 有/有 | 已入库 |
| 莆田市第一医院 | `莆田市第一医院` | 是 | test_external | 25 | 8 | 无/有 | 无/有 | 已入库 |
| 福建省肿瘤医院 | `福建省肿瘤医院` / `ext/zhongliu` | 是 | test_external | 436 | 135 | 有/有 | 无/有 | 已入库 |
| 三明市第二医院 | `三明市第二医院` | 是 | test_external | 19 | 4 | 有/有 | 无/有 | 已入库 |
| 福建省德化县医院 | `福建省德化县医院` / `ext/newzip/福建省德化县医院` | newzip | test_external_newzip | 100 | 16 | 有/有 | 有/有 | 已入库 |
| 北京友谊医院 | `北京友谊医院` / `ext/newzip/外省整理` | newzip | test_external_newzip | 124 | 22 | 无/有 | 无/有 | 已入库 |
| 佛山市第一人民医院 | `佛山市第一人民医院` / `ext/newzip/外省整理` | newzip | test_external_newzip | 112 | 31 | 无/有 | 有/有 | 已入库 |
| 中核五〇四医院（胃癌直接手术） | `中核五〇四医院` / `ext/newzip/外省整理/湖北窦` | newzip | test_external_newzip | 216 | 67 | 有/无 | 无/有 | 已入库；原误标「湖北中西医结合医院」 |
| 中核五〇四医院 | `data/窦晓霞中核五〇四医院胃溃疡病例(1)/` | 否 | 独立溃疡任务 | 0 | 0 | 有/有 | 有/有 | 独立任务 |
| 福建省立医院 | — | 否 | — | 0 | 0 | 无/有 | 无/有 | 未入库 |
| 宁德市医院 | — | 否 | — | 0 | 0 | 有/无 | 无/有 | 未入库 |

### 遗留别名对照

| 旧称 | 标准医院名称 |
| --- | --- |
| 协和内部 | 福建医科大学附属协和医院 |
| 莆田学院附属医院 | 莆田学院附属医院 |
| 莆田市第一医院 | 莆田市第一医院 |
| 福建省肿瘤医院 | 福建省肿瘤医院 |
| 三明市第二医院 | 三明市第二医院 |
| 北京友谊医院 | 北京友谊医院 |
| 佛山市第一人民医院 | 佛山市第一人民医院 |
| 湖北中西医结合医院（已废弃） | 中核五〇四医院 |
| 湖北窦 / 外省整理湖北 | 中核五〇四医院 |
| 福建省德化县医院 | 福建省德化县医院 |

### newzip 三省拆分统计

`外省整理.zip` 在物理目录上仍保留 `dataset/external/外省整理/`，但应按医院单独汇报：

| 标准医院名称 | 物理子目录 | manifest 帧数 | 建模 split 帧数 | 建模 patient 数 |
| --- | --- | ---: | ---: | ---: |
| 北京友谊医院 | `北京友谊医院` | 124 | 124 | 22 |
| 佛山市第一人民医院 | `佛山市第一人民医院` | 112 | 67 | 31 |
| 中核五〇四医院 | `中核五〇四医院` | 216 | 216 | 67 |
| 福建省德化县医院 | `福建省德化县医院` | 100 | 88 | 16 |

说明：

- 佛山部分图像有 manifest，但未全部匹配到 pT，因此建模帧数少于 manifest 帧数。
- 当前建模 CSV 的 `source` 仍是 `ext/newzip/外省整理`；按中心拆分时请读取 `center_name_registry.csv`，或检查 `image_path` 中是否包含 `北京` / `广东` / `湖北`。

## 当前目录结构

```text
dataset/
├── DATASET_GUIDE.md
├── README.md
├── internal/
│   ├── manifest.csv
│   ├── unmatched_files.csv
│   ├── errors.csv
│   ├── training_2018_2024/
│   │   ├── 2018/
│   │   ├── 2019/
│   │   ├── 2020_2023/
│   │   └── 2024/
│   └── prospective_2025/
│       └── 2025/
├── external/
│   ├── manifest.csv
│   ├── unmatched_files.csv
│   ├── errors.csv
│   ├── 三明市第二医院/
│   ├── 福建省肿瘤医院/
│   ├── 莆田学院附属医院/          # 莆田学院附属医院
│   ├── 莆田市第一医院/          # 莆田市第一医院
│   ├── 外省整理/                  # newzip；按医院再拆为 北京/广东/湖北窦
│   │   ├── 北京/                  # 北京友谊医院
│   │   ├── 广东/                  # 佛山市第一人民医院
│   │   └── 湖北窦/                # 中核五〇四医院（原误标湖北中西医结合医院）
│   └── 福建省德化县医院/              # 福建省德化县医院
└── tables/
    ├── README.md
    ├── raw/
    ├── by_source/
    ├── center_name_registry.csv   # 标准医院名 ↔ 遗留目录/source 映射
    ├── clinical_table_index.csv
    └── clinical_table_registry.csv
```

## 统计口径说明

为了避免“文件夹里有残留文件，但不一定进入正式实验口径”这种问题，本说明采用两层统计：

1. **正式样本统计**
  使用 `manifest.csv`，表示已经成功进入当前正式数据集的样本。
2. **物理目录统计**
  直接统计 `original/`、`crop_ui/`、`crop_roi/` 下面的文件数，用来说明当前目录里实际放了多少文件。

请注意：

- 做实验、写结果、生成训练 CSV 时，**优先以 `manifest.csv` 为准**
- 看目录整理情况、核对是否有额外残留文件时，再参考物理目录统计

## 正式样本总体统计

以下数字已按当前文件重新统计，最近一次复核时间为 **2026-05-05**。


| 数据块              | 成功样本数 (`manifest.csv`) | 错误样本数 (`errors.csv`) | 匹配成功总数     | 未匹配图像  | 未匹配标注  | 图像候选总数     | 标注候选总数     |
| ---------------- | ---------------------- | -------------------- | ---------- | ------ | ------ | ---------- | ---------- |
| 内部数据 `internal/` | 10,659                 | 6                    | 10,665     | 61     | 49     | 10,726     | 10,714     |
| 外部数据 `external/` | 2,856                  | 2                    | 2,858      | 11     | 5      | 2,869      | 2,863      |
| **总计**           | **13,515**             | **8**                | **13,523** | **72** | **54** | **13,595** | **13,577** |


这里的含义可以这样理解：

- **图像候选总数**：原始图像文件总量
- **标注候选总数**：原始 `nii.gz` 标注总量
- **匹配成功总数**：图像和标注已经成功配对
- **成功样本数**：配对成功后又顺利完成预处理、正式进入数据集
- **错误样本数**：已经配对成功，但在预处理阶段失败

### 多口径总览表

当前项目里同时存在“正式预处理数据”“建模 CSV 数据”“新增外部 review/预处理数据”几种常用口径。它们服务的任务不同，不能直接混用。


| 口径                             | 数据范围                                                                           | 图像/行数                                | 去重图像数   | 病例/患者数                | mask 数                                       | 当前用途                                                 |
| ------------------------------ | ------------------------------------------------------------------------------ | ------------------------------------ | ------- | --------------------- | -------------------------------------------- | ---------------------------------------------------- |
| `dataset/manifest.csv` 正式预处理口径 | `dataset/internal/` + `dataset/external/`                                      | 13,515                               | 13,515  | 未重建正式患者注册表            | 13,515                                       | 分割、ROI、正式物理数据统计                                      |
| T 分期建模 CSV 口径                  | `pipeline/data/tstaging_4class_region_contrastive_full/regions/*_clinical.csv` | 12,851                               | 11,758  | 2,083 个 `patient_id`  | 来自预测 mask / GT `.nii.gz` mask / region patch | 当前 4 类 T 分期训练和评估；已包含新增 zip 中有 pT 标签的 495 行           |
| 新增 zip review/预处理口径            | `data/外省整理.zip` + `data/福建省德化县医院.zip` -> `dataset/external/`                     | 552                                  | 552     | 155 个病例前缀             | 552 个 `.nii.gz`                              | 新外部泛化 review、GT-mask assisted 上限分析、独立 external split |
| 良性炎症分割旧口径                      | `pipeline/data/nnunet_benign_finetune.csv`                                     | 372                                  | 372     | 318 个 `patient`       | LabelMe JSON                                 | 良性炎症区域分割；不是 T 分期                                     |
| 胃溃疡视频良恶性口径                     | `data/窦晓霞中核五〇四医院胃溃疡病例(1)/`                                                     | 76 个病例文件夹 / 158 个视频 / 1,990 个 1fps 帧 | 1,990 帧 | 良性 37 / 恶性 39 个病例文件夹  | 暂无统一 lesion mask                             | 良恶性溃疡视频泛化、筛查和帧级 pipeline review                      |
| 建模 CSV + 新增 zip 全量工作量口径        | 建模 CSV 行 + 新增 zip 未入 split 图像                                                  | 12,908                               | 11,815  | 约 2,083 + 19 个未标注病例前缀 | 混合来源                                         | 估算当前可分析切面总工作量                                        |
| 正式 manifest + 新增 zip 物理口径      | 正式预处理样本 + 新增 zip 图像                                                            | 14,067                               | 14,067  | 暂无统一患者注册              | 14,067                                       | 估算当前磁盘中可用标注图像规模                                      |

### 建模数据 contract 与 external 隔离

T 分期 external 泛化实验必须先确认数据集 contract，而不是只在训练后剔除重叠病例。当前约定如下：

| Contract | 推荐状态 | 目录 | train/val external 策略 | external UID overlap | 用途 |
| --- | --- | --- | --- | --- | --- |
| Screened Phase 0 | **clean / 默认** | `pipeline/data/tstaging_4class_screened_eval_phase0_xiehe_20260610/` | train/val 仅 `int/*`，`ext_rows=0` | 0 | ConvNeXt / L1 / fusion 的合规 external 泛化训练入口 |
| Anatomic Phase 0 | **clean / 默认** | `pipeline/data/tstaging_4class_anatomic_region_contrastive_phase0/regions/` | train/val 仅 `int/*`，`ext_rows=0` | 0 | DINO scalar、DINO anatomic adapter、mask-guided attention 的合规 external 泛化训练入口 |
| Screened 20260531 | legacy audit only | `pipeline/data/tstaging_4class_screened_eval_20260531/` | train/val 含 `ext/*` | 有重叠 | 只用于历史模型追溯和 overlap-corrected audit |
| Anatomic region legacy | legacy audit only | `pipeline/data/tstaging_4class_anatomic_region_contrastive/regions/` | train/val 含 `ext/*` | 有重叠风险 | 只用于重建 Phase 0 或复核旧实验 |

自动审计入口：

```bash
python scripts/audit_modeling_dataset_contracts.py
```

该脚本会输出 `data/metadata/modeling_dataset_contract_audit_YYYYMMDD.{json,csv}`；clean contract 若出现 train/val `ext/*` 行或与 external clinical patient UID 重叠，应直接视为数据集 contract 失败。

2026-06-13 最新审计结果：

| Contract | train/val `ext/*` rows | max external UID overlap | 审计结论 |
| --- | ---: | ---: | --- |
| Screened Phase 0 | 0 | 0 | 通过，允许用于 external 泛化训练 |
| Anatomic Phase 0 | 0 | 0 | 通过，允许用于 DINO / adapter external 泛化训练 |
| Screened 20260531 legacy | 1,477 | 98 | 不通过 clean 标准；仅历史追溯 / overlap-corrected audit |
| Anatomic region legacy | 1,254 | 0 | 不通过 clean 标准；仅用于重建 Phase 0 或复核旧实验 |


### 医生标注监督资产：胃腔与病灶（2026-06-13 复核）

除 `dataset/manifest.csv` 的正式物理样本口径外，项目里还保留了大量可用于监督训练的医生/人工标注。做 DINO/anatomic adapter、检测/分割预训练或 ROI 约束时，优先读取下表中的 **manifest/CSV**，不要直接从零散目录猜路径。

| 标注资产 | 推荐入口 | 原始/来源位置 | 数量口径 | 数量 | 主要字段/产物 | 建议用途 |
| --- | --- | --- | --- | ---: | --- | --- |
| 胃腔检测标注（YOLO） | `data/processed/detection/yolo11_lumen_locator_cropui_combined_plus_zip2/dataset_manifest.json` | `200.zip`、`2024_crop_ui_unlabeled_lumen_for_labelme(1).zip`、`2024_crop_ui_unlabeled_lumen_for_labelme(2).zip`、`data/raw/legacy_lumen/` | 去重后图像 / label | 1,833 | `images/`、`labels/`，class=`lumen` | 胃腔框检测、去全图干扰、DINO ROI 内外侧方向先验 |
| 胃腔检测 split | 同上 | 同上 | train / val 图像 | 1,650 / 183 | train patients 427，val patients 48 | 训练/验证 YOLO lumen locator |
| 胃腔原始 LabelMe zip | `artifacts/raw_imports/incoming/` | `200.zip`、`2024_crop_ui_unlabeled_lumen_for_labelme(1).zip`、`2024_crop_ui_unlabeled_lumen_for_labelme(2).zip` | JSON（逐包） | 197 / 444 / 1,115 | LabelMe JSON + 对应 JPG；`(2)` 包含中文路径修正版 | 追溯新增胃腔标注来源；重建 processed manifest 时使用 |
| 胃腔 legacy LabelMe | `data/raw/legacy_lumen/` | 原 `胃腔/` 兼容口径 | JSON / 图像文件 | 102 / 103 | `.json` 标注；label=`1`；与 `200.zip` 有 25 个重复 sample | 追溯早期胃腔标注来源；正式训练以 processed manifest 为准 |
| 病灶检测标注（YOLO bbox） | `data/processed/detection/yolo11_lesion_holdout_cropui/dataset_manifest.json` | `dataset/internal/**/crop_ui/annotations/`、`dataset/external/**/crop_ui/annotations/` | train / val / internal_test | 6,621 / 795 / 813 | lesion bbox，empty label=0 | 病灶检测、自动 ROI、视频关键帧候选 |
| 病灶检测评估 | 同上 | 前瞻与外部 crop_ui 标注 | prospective / external | 2,430 / 2,856 | lesion bbox | 前瞻/外部检测泛化评估 |
| 病灶分割标注（UNet/SMS） | `data/processed/sms/baseline_2d_unet_holdout_crop_ui/dataset_manifest.json` | `dataset/**/crop_ui/roi_masks/*.png` | training / holdout | 7,376 / 853 | `original_image`、`original_label`、`prepared_image`、`prepared_label` | 病灶 mask 监督、分割预训练、DINO lesion token pooling |
| GT 病灶 crop 上限 | `data/processed/sms/gt_lesion_crop_upper_bound_v1/dataset_manifest.json` | 基于 SMS manifest 的 GT lesion mask/crop | cases / empty mask | 13,515 / 0 | `crop_box`、`gt_lesion_box`、`original_label` | ROI-crop 上限实验；训练 DINO adapter 的 lesion-mask teacher |
| 正式 dataset 病灶 polygon/mask | `dataset/internal/manifest.csv`、`dataset/external/manifest.csv` | `dataset/internal/**/crop_ui/annotations/*.json`、`dataset/external/**/crop_ui/annotations/*.json`、`roi_masks/*.png` | internal + external JSON / mask 物理文件 | 10,659 + 3,104 | LabelMe polygon JSON、ROI mask PNG | 原始病灶勾画追溯；重建 detection/segmentation manifest |
| 壁层/内外侧派生监督（Phase 0 clean） | `pipeline/data/tstaging_4class_anatomic_region_contrastive_phase0/regions/*_clinical.csv` | 由 `pipeline/data/tstaging_4class_anatomic_region_contrastive/regions/` 过滤 `ext/*` train/val 得到 | train / val / external overlap | 7,531 / 836 / 0 UID | `anatomic_inner_lumen_mask_path`、`anatomic_outer_wall_mask_path`、`anatomic_bridge_mask_path`、`direction_outward_angle_deg`、`lumen_box_*` | DINO anatomic adapter、outer-inner / boundary-lesion 对比、T2/T3/T4+ 壁层判别；**external 泛化训练默认入口** |

注意：

- 表中的 `dataset/**/crop_ui/annotations` 与 `roi_masks` 是医生病灶勾画的物理追溯口径；进入训练时应使用 `data/processed/detection/` 或 `data/processed/sms/` 的 manifest，避免重复文件和残留文件影响统计。
- 胃腔本次复核的独立原始来源为 3 个 zip + `data/raw/legacy_lumen/`；`_compat/胃腔` 是兼容入口，不作为新增来源计数。四个来源原始 JSON 合计 1,858 个，去重后进入稳定检测入口 1,833 个。
- 胃腔标注数量小于病灶标注，但对 **去除全图背景/标尺干扰** 和 **判断病灶相对胃腔的内外侧方向** 很关键。
- `pipeline/data/tstaging_4class_anatomic_region_contrastive/regions/*_clinical.csv` 是 legacy anatomic 入口，train/val 含 `ext/*` 行；只用于追溯或重建，不再作为 external 泛化训练入口。正式 DINO adapter / mask-guided attention 训练使用 `pipeline/data/tstaging_4class_anatomic_region_contrastive_phase0/regions/`，由 `scripts/build_phase0_anatomic_region_splits.py` 生成，train/val 的 `ext_rows=0`。

### 胃腔/病灶标注使用计划

1. **短期：DINO ROI 约束与复检**
   - 用 `yolo11_lumen_locator_cropui_combined_plus_zip2` 的胃腔框去掉全图标尺、体表图标和远场背景。
   - 用 SMS/GT lesion mask 构建 `lesion`、`boundary ring`、`outer-side`、`inner/lumen-side` 四类区域。
   - 对 DINO token map 只做 ROI 内复检，避免全图 `token_norm` 高亮区被无关组织稀释。

2. **中期：DINO anatomic adapter**
   - 以 `gt_lesion_crop_upper_bound_v1` 的 `original_label` / `crop_box` 作为 lesion teacher。
   - 以 `anatomic_inner_lumen_masks`、`anatomic_outer_wall_masks`、`anatomic_bridge_masks` 和 `direction_outward_angle_deg` 作为胃腔-外壁-突破方向 teacher。
   - 冻结 DINO backbone，训练轻量 decoder / adapter 同时预测 lesion、inner lumen、outer wall、bridge/breakthrough 与 T stage。

3. **长期：病例级视频聚合**
   - 对视频关键帧先跑 lumen + lesion 检测，只保留可解释 ROI。
   - 用 adapter 输出的 `outer-side risk`、`boundary-minus-lesion`、`bridge probability` 选择 top-k 帧。
   - 病例级聚合时以患者为单位划分 train/val/test，禁止图像级泄漏。

### 良性数据现状

良性数据目前不属于 T 分期主任务，因为 T 分期标签只适用于胃癌病例。它们应该作为独立任务或辅助数据使用：


| 良性/溃疡数据      | 当前位置                                       | 样本规模                                                                   | 标注/标签                                      | 建议用途                               |
| ------------ | ------------------------------------------ | ---------------------------------------------------------------------- | ------------------------------------------ | ---------------------------------- |
| yan 系列良性炎症分割 | `pipeline/data/nnunet_benign_finetune.csv` | 372 张图像，318 个 `patient`；train / val / test = 296 / 38 / 38             | LabelMe JSON 炎症区域标注，`has_lesion=True`      | 良性炎症/溃疡区域分割、分割预训练、良性负例可视化          |
| ptyz 良性候选    | 旧训练记录中提到 `ptyz`                            | 98 例 / 431 张                                                           | 当时未纳入训练，标注状态待复核                            | 后续扩充良性分割数据                         |
| 胃溃疡视频数据      | `data/窦晓霞中核五〇四医院胃溃疡病例(1)/`                 | 良性 37 个病例文件夹、32 个视频、1fps 抽帧 452 帧；恶性 39 个病例文件夹、126 个视频、1fps 抽帧 1,538 帧 | 目录级良/恶性标签；暂未整理成统一 lesion mask 或 T-stage 标签 | 良恶性视频分类、pipeline 泛化 review、良性对照帧抽样 |


因此，新增外部 T 分期 split 仍然只包含胃癌 pT 标签病例；良性样本后续应单独做 `benign_vs_malignant` 或 `benign_inflammation_segmentation` split，不能写成 T1/T2/T3/T4+。

## 当前 T 分期建模 CSV 口径统计（2026-05-05 更新）

上面的 `manifest.csv` 是 `dataset/` 目录的正式预处理口径；当前 4 类 T 分期训练和评估实际主要读取的是：

- `pipeline/data/tstaging_4class_region_contrastive_full/regions/train_clinical.csv`
- `pipeline/data/tstaging_4class_region_contrastive_full/regions/val_clinical.csv`
- `pipeline/data/tstaging_4class_region_contrastive_full/regions/test_external_clinical.csv`
- `pipeline/data/tstaging_4class_region_contrastive_full/regions/test_external_newzip_clinical.csv`
- `pipeline/data/tstaging_4class_region_contrastive_full/regions/test_prospective_clinical.csv`

这组 CSV 已经包含模型训练需要的图像路径、ROI 路径、预测 lesion mask、region patch、临床 22 维特征、`patient_id`、`source`、`label` 和 `T_stage`。因此做训练汇报、AUC 统计和复现实验时，应同时说明使用的是 `**dataset/manifest.csv` 物理数据口径**，还是 `**pipeline/data/.../regions/*_clinical.csv` 建模口径**。

### 建模 CSV 总体规模


| 统计项                           | 数量     |
| ----------------------------- | ------ |
| CSV 行数（含不同 split 中可能重复出现的样本行） | 12,851 |
| 去重后 `image_path` 数            | 11,758 |
| 去重后 `sample_id` 数             | 11,758 |
| 去重后 `patient_id` 数            | 2,083  |
| 重复行数（CSV 行数 - 去重 image_path）  | 1,093  |


这里的重复行不是文件损坏，而是建模 CSV 层面为了不同训练/测试视图保留了若干重复样本行。因此：

- 训练循环、DataLoader、epoch 样本量按 **CSV 行数** 理解
- 真实图像规模和病例规模按 **去重 image_path / patient_id** 理解
- 前瞻集如果同时出现在 `test_external` 和 `test_prospective`，汇报前瞻结果时以 `test_prospective_clinical.csv` 为准

### 按 split 统计


| Split                | 图像行数       | patient_id 数 | T1        | T2        | T3        | T4+       |
| -------------------- | ---------- | ------------ | --------- | --------- | --------- | --------- |
| train                | 8,783      | 1,405        | 1,510     | 1,037     | 3,136     | 3,100     |
| val                  | 1,041      | 161          | 206       | 83        | 350       | 402       |
| test_external        | 2,298      | 381          | 421       | 184       | 893       | 800       |
| test_external_newzip | 495        | 136          | 63        | 106       | 157       | 169       |
| test_prospective     | 234        | 46           | 39        | 31        | 100       | 64        |
| **合计（CSV 行数）**       | **12,851** | **2,083**    | **2,239** | **1,441** | **4,636** | **4,535** |


### 按内外部大类统计


| 大类                                                                | CSV 行数 | 去重图像数 | patient_id 数 | T1    | T2  | T3    | T4+   |
| ----------------------------------------------------------------- | ------ | ----- | ------------ | ----- | --- | ----- | ----- |
| 内部训练/验证/holdout（`int/2018`、`int/2019`、`int/2020_2023`、`int/2024`） | 8,235  | 7,379 | 1,297        | 1,401 | 875 | 2,941 | 3,018 |
| 内部前瞻池（`int/prospective`，非单独 prospective split 的行）                 | 1,212  | 1,209 | 213          | 254   | 132 | 369   | 457   |
| 外部多中心（`ext/`*）                                                    | 3,170  | 3,170 | 573          | 545   | 403 | 1,226 | 996   |
| 前瞻评估视图（`test_prospective`）                                        | 234    | 234   | 46           | 39    | 31  | 100   | 64    |


### 按 source 统计


| source                  | 图像行数  | patient_id 数 | 所在 split                                       | T1  | T2  | T3    | T4+   |
| ----------------------- | ----- | ------------ | ---------------------------------------------- | --- | --- | ----- | ----- |
| `int/2018`              | 3,355 | 497          | train / val / test_external                    | 550 | 337 | 1,308 | 1,160 |
| `int/2019`              | 2,464 | 507          | train / val / test_external                    | 447 | 372 | 913   | 732   |
| `int/2020_2023`         | 164   | 16           | train / val / test_external                    | 7   | 13  | 80    | 64    |
| `int/2024`              | 2,252 | 277          | train / val / test_external                    | 397 | 153 | 640   | 1,062 |
| `int/prospective`       | 1,446 | 213          | train / val / test_external / test_prospective | 293 | 163 | 469   | 521   |
| `ext/multicenter`       | 124   | 45           | train / val / test_external                    | 0   | 0   | 0     | 124   |
| `ext/putian`            | 1,103 | 165          | train / val / test_external                    | 260 | 130 | 426   | 287   |
| `ext/putian_2024`       | 434   | 53           | test_external                                  | 54  | 56  | 203   | 121   |
| `ext/putian_2024_new`   | 350   | 38           | train / val / test_external                    | 23  | 60  | 212   | 55    |
| `ext/putian_2025_07_09` | 435   | 82           | test_external                                  | 138 | 39  | 156   | 102   |
| `ext/zhongliu`          | 229   | 54           | test_external                                  | 7   | 12  | 72    | 138   |
| `ext/newzip/外省整理`       | 407   | 120          | test_external_newzip                           | 57  | 97  | 128   | 125   |
| `ext/newzip/福建省德化县医院`     | 88    | 16           | test_external_newzip                           | 6   | 9   | 29    | 44    |


### 新增 zip 数据（已预处理并建立独立 external split）

2026-05-05 额外解压并跑了可视化复核的两个压缩包：

- `data/外省整理.zip`
- `data/福建省德化县医院.zip`

它们目前属于 **新增外部 review / upper-bound 候选数据**，已经有 `.nii.gz` mask，可用于 GT-mask assisted review、分割泛化性评估和后续外部扩展实验。2026-05-05 已追加完成一轮与正式数据一致的预处理，并把 Excel 中能匹配到 pT 标签的图像写入独立 split：

- 预处理脚本：`scripts/preprocess_new_external_zip_datasets.py`
- 预处理输出：`dataset/external/外省整理/`、`dataset/external/福建省德化县医院/`
- 汇总 manifest：`dataset/external/new_external_zip_manifest.csv`
- 新增建模 split：`pipeline/data/tstaging_4class_region_contrastive_full/regions/test_external_newzip_clinical.csv`


| 新增数据源  | 图像数     | 估算病例前缀数 | `.nii.gz` mask 数 | 已匹配 pT 图像数 | 已匹配病例数  | 当前状态                                           |
| ------ | ------- | ------- | ---------------- | ---------- | ------- | ---------------------------------------------- |
| 外省整理   | 452     | 137     | 452              | 407        | 120     | 已解压、全量跑 review、完成预处理、进入 `test_external_newzip` |
| 福建省德化县医院 | 100     | 18      | 100              | 88         | 16      | 已解压、全量跑 review、完成预处理、进入 `test_external_newzip` |
| **合计** | **552** | **155** | **552**          | **495**    | **136** | 57 张暂未匹配 Excel pT，先保留在 manifest，不进入建模 split    |


### 新增 zip 全量 review 统计

这张表来自 `pipeline/experiments/reports/zip_pipeline_review_20260505/combined_summary.csv`。其中 `Pred-vs-GT IoU` 是当前分割模型输出 mask 与 zip 自带 `.nii.gz` mask 的重叠度；`Pred vs GT-assisted 一致数` 是“使用预测 mask/ROI 分期”和“使用 GT mask/ROI 辅助分期”的 top-1 分期是否一致。


| 新增数据源  | 图像数     | Mean Pred-vs-GT IoU | Median Pred-vs-GT IoU | Pred vs GT-assisted 一致数 | 预测分期分布                    | GT-assisted 分期分布           |
| ------ | ------- | ------------------- | --------------------- | ----------------------- | ------------------------- | -------------------------- |
| 外省整理   | 452     | 0.117               | 0.048                 | 137 / 452               | T2: 218, T3: 53, T4+: 181 | T2: 179, T3: 134, T4+: 139 |
| 福建省德化县医院 | 100     | 0.256               | 0.152                 | 39 / 100                | T2: 39, T3: 31, T4+: 30   | T2: 27, T3: 37, T4+: 36    |
| **合计** | **552** | **0.142**           | **0.060**             | **176 / 552**           | -                         | -                          |


从这张表可以看出，两个新增 zip 的主要问题不是“没有标注”，而是当前预测分割与 `.nii.gz` 标注差距较大。尤其外省整理的 median IoU 只有 `0.048`，说明很多切面上预测 ROI 与人工 mask 对不上；因此后续如果要并入训练，应优先走 GT-mask upper-bound 或重新适配分割模型，而不是直接把预测 mask 当可靠输入。

### 新增 zip Excel 标签整理结果

Excel 里的 pT 编码已统一映射到 4 类 T 分期：`1 -> T1`，`2 -> T2`，`3 -> T3`，`4/5 -> T4+`。能够匹配到 pT 的样本已经进入 `test_external_newzip_clinical.csv`。


| 新增 split source     | 图像行数    | patient_id 数 | T1     | T2      | T3      | T4+     |
| ------------------- | ------- | ------------ | ------ | ------- | ------- | ------- |
| `ext/newzip/外省整理`   | 407     | 120          | 57     | 97      | 128     | 125     |
| `ext/newzip/福建省德化县医院` | 88      | 16           | 6      | 9       | 29      | 44      |
| **合计**              | **495** | **136**      | **63** | **106** | **157** | **169** |


相关复核输出：

- `pipeline/experiments/reports/zip_pipeline_review_20260505/combined_contact_sheet.png`
- `pipeline/experiments/reports/zip_pipeline_review_20260505/combined_summary.csv`
- `pipeline/experiments/reports/zip_pipeline_review_20260505/zip_pipeline_review_report.md`

如果把建模 CSV 行数和新增 zip 图像简单相加，当前可分析图像/切面条目约为：


| 口径                                  | 数量         |
| ----------------------------------- | ---------- |
| 建模 CSV 行数（已含新增 zip 有 pT 标签 495 行）   | 12,851     |
| 新增 zip 暂未入 split 图像数                | 57         |
| **合计条目数**                           | **12,908** |
| 建模 CSV 去重图像数 + 新增 zip 暂未入 split 图像数 | **11,815** |


需要注意：`12,908` 是“建模行 + 新增 zip 未入 split 图像”的工作量口径，不等同于最终去重患者数。新增 zip 目前按文件名前缀建立 `patient_id`，已经具备独立外部评估 split；如果后续要混入训练集，还需要先确认中心分层、病例级抽样和 `.nii.gz` mask 的 GT/预测 mask 使用策略。

## 内部数据详细统计

内部正式数据分成两块：

- `training_2018_2024/`：内部训练主池
- `prospective_2025/`：2025 前瞻测试池

### 按年份统计的正式样本数

以下统计来自 `dataset/internal/manifest.csv`。


| 内部分组      | 正式样本数      | 占内部正式样本比例   |
| --------- | ---------- | ----------- |
| 2018      | 3,638      | 34.13%      |
| 2019      | 2,856      | 26.79%      |
| 2020_2023 | 199        | 1.87%       |
| 2024      | 1,539      | 14.44%      |
| 2025      | 2,427      | 22.77%      |
| **合计**    | **10,659** | **100.00%** |


从这个分布可以直接看出：

- `2018` 和 `2019` 仍然是内部主力
- `2025` 规模已经很大，但它是**前瞻池**，不建议直接混进内部训练池
- `2020_2023` 样本明显偏少，做单独年份分析时波动会比较大

### 按视图统计的物理文件数

以下统计是直接数目录里的文件，不等同于正式样本数。

#### 内部 `2018`


| 视图         | images | annotations | roi_masks | overlays |
| ---------- | ------ | ----------- | --------- | -------- |
| `original` | 3,714  | 3,644       | 3,650     | 3,645    |
| `crop_ui`  | 3,647  | 3,653       | 3,661     | 3,644    |
| `crop_roi` | 3,644  | 3,662       | 3,666     | 3,642    |


#### 内部 `2019`


| 视图         | images | annotations | roi_masks | overlays |
| ---------- | ------ | ----------- | --------- | -------- |
| `original` | 2,867  | 2,869       | 2,917     | 2,931    |
| `crop_ui`  | 3,240  | 3,098       | 3,070     | 3,024    |
| `crop_roi` | 2,933  | 2,995       | 3,466     | 3,177    |


#### 内部 `2020_2023`


| 视图         | images | annotations | roi_masks | overlays |
| ---------- | ------ | ----------- | --------- | -------- |
| `original` | 303    | 264         | 355       | 257      |
| `crop_ui`  | 289    | 301         | 341       | 332      |
| `crop_roi` | 293    | 306         | 293       | 292      |


#### 内部 `2024`


| 视图         | images | annotations | roi_masks | overlays |
| ---------- | ------ | ----------- | --------- | -------- |
| `original` | 1,542  | 1,550       | 1,542     | 1,562    |
| `crop_ui`  | 1,562  | 1,542       | 1,542     | 1,541    |
| `crop_roi` | 1,542  | 1,541       | 1,542     | 1,541    |


#### 内部 `2025`


| 视图         | images | annotations | roi_masks | overlays |
| ---------- | ------ | ----------- | --------- | -------- |
| `original` | 2,524  | 2,434       | 2,431     | 2,434    |
| `crop_ui`  | 2,441  | 2,463       | 2,433     | 2,437    |
| `crop_roi` | 2,433  | 2,432       | 2,441     | 2,450    |


### 内部问题样本统计

#### 未匹配文件

`dataset/internal/unmatched_files.csv` 共 **110** 条：

- 图像未匹配：61
- 标注未匹配：49

按年份拆分：


| 年份     | 未匹配总数   | 图像未匹配  | 标注未匹配  |
| ------ | ------- | ------ | ------ |
| 2018   | 28      | 20     | 8      |
| 2019   | 70      | 35     | 35     |
| 2024   | 12      | 6      | 6      |
| **合计** | **110** | **61** | **49** |


#### 预处理错误样本

`dataset/internal/errors.csv` 共 **6** 条，全部错误类型都是：

- `Mask is empty, cannot compute ROI crop.`

按年份拆分：


| 年份        | 错误样本数 |
| --------- | ----- |
| 2018      | 1     |
| 2020_2023 | 1     |
| 2025      | 4     |
| **合计**    | **6** |


## 外部数据详细统计

外部正式数据按中心组织，默认作为独立外部测试集。

### 按中心统计的正式样本数

以下统计来自 `dataset/external/manifest.csv`。


| 外部中心（遗留目录名） | 标准医院名称 | 正式样本数 | 占外部正式样本比例 |
| --- | --- | ---: | ---: |
| 莆田学院附属医院 | 莆田学院附属医院 | 2,376 | 83.19% |
| 福建省肿瘤医院 | 福建省肿瘤医院 | 436 | 15.27% |
| 莆田市第一医院 | 莆田市第一医院 | 25 | 0.88% |
| 三明市第二医院 | 三明市第二医院 | 19 | 0.67% |
| **正式 manifest 小计** | | **2,856** | **100.00%** |

newzip 追加中心（不在 `dataset/external/manifest.csv` 主清单内，而在 `new_external_zip_manifest.csv`）：

| 物理子目录 | 标准医院名称 | 帧数 |
| --- | --- | ---: |
| 北京友谊医院 | 北京友谊医院 | 124 |
| 佛山市第一人民医院 | 佛山市第一人民医院 | 112 |
| 中核五〇四医院 | 中核五〇四医院 | 216 |
| 福建省德化县医院 | 福建省德化县医院 | 100 |


这个分布非常不均衡，汇报外部结果时建议同时给：

- 外部总体结果
- 按中心分层结果

不然总体指标会被 **莆田学院附属医院**（遗留目录 `莆田学院附属医院`）明显主导。

### 按视图统计的物理文件数

#### 三明市第二医院


| 视图         | images | annotations | roi_masks | overlays |
| ---------- | ------ | ----------- | --------- | -------- |
| `original` | 19     | 19          | 19        | 19       |
| `crop_ui`  | 19     | 19          | 19        | 19       |
| `crop_roi` | 19     | 19          | 19        | 19       |


#### 福建省肿瘤医院


| 视图         | images | annotations | roi_masks | overlays |
| ---------- | ------ | ----------- | --------- | -------- |
| `original` | 441    | 436         | 436       | 436      |
| `crop_ui`  | 438    | 436         | 440       | 436      |
| `crop_roi` | 436    | 436         | 444       | 437      |


#### 莆田学院附属医院


| 视图         | images | annotations | roi_masks | overlays |
| ---------- | ------ | ----------- | --------- | -------- |
| `original` | 2,455  | 2,445       | 2,474     | 2,589    |
| `crop_ui`  | 2,376  | 2,384       | 2,393     | 2,395    |
| `crop_roi` | 2,387  | 2,530       | 2,377     | 2,408    |


#### 莆田市第一医院


| 视图         | images | annotations | roi_masks | overlays |
| ---------- | ------ | ----------- | --------- | -------- |
| `original` | 25     | 25          | 25        | 25       |
| `crop_ui`  | 25     | 25          | 25        | 25       |
| `crop_roi` | 25     | 25          | 25        | 25       |


### 外部问题样本统计

#### 未匹配文件

`dataset/external/unmatched_files.csv` 共 **16** 条：

- 图像未匹配：11
- 标注未匹配：5

按中心拆分：


| 中心        | 未匹配总数  | 图像未匹配  | 标注未匹配 |
| --------- | ------ | ------ | ----- |
| 福建省肿瘤医院  | 11     | 6      | 5     |
| 莆田学院附属医院 | 5      | 5      | 0     |
| **合计**    | **16** | **11** | **5** |


#### 预处理错误样本

`dataset/external/errors.csv` 共 **2** 条，全部位于 `莆田学院附属医院`，错误类型同样是：

- `Mask is empty, cannot compute ROI crop.`

## 临床表整理层统计

`dataset/tables/` 不是最终患者级注册表，而是**原始临床表整理层**。它的作用是把不同年份、不同中心的表格统一收集到一个位置，方便后续继续做患者级注册、标签映射和分层统计。

### 表格文件结构

当前 `tables/by_source/` 下共有 **10** 个拆分 CSV：

- `internal_2018_direct_surgery__sheet1.csv`
- `internal_2019_direct_surgery__sheet1.csv`
- `internal_2020_2023_direct_surgery__sheet1.csv`
- `internal_2024_direct_surgery__sheet1.csv`
- `internal_2025_direct_surgery__sheet1.csv`
- `external_putian1_direct_surgery__sheet1.csv`
- `external_putian2_direct_surgery__sheet1.csv`
- `external_sanming_direct_surgery__sheet1.csv`
- `external_tumor_hospital_direct_surgery__sheet1.csv`
- `external_tumor_hospital_direct_surgery__sheet2.csv`

### `clinical_table_registry.csv` 总体统计


| 维度                          | 行数    | 去重后 `record_key_raw` 数 |
| --------------------------- | ----- | ---------------------- |
| 全部临床表记录                     | 2,506 | 2,373                  |
| 内部训练 `internal_training`    | 1,395 | 1,390                  |
| 内部前瞻 `internal_prospective` | 492   | 491                    |
| 外部测试 `external_test`        | 619   | 492                    |


### 按中心统计的临床表记录


| 中心        | 行数    | 去重后 `record_key_raw` 数 |
| --------- | ----- | ---------------------- |
| 协和内部      | 1,887 | 1,881                  |
| 福建省肿瘤医院  | 263   | 136                    |
| 莆田学院附属医院 | 344   | 344                    |
| 莆田市第一医院 | 8     | 8                      |
| 三明市第二医院  | 4     | 4                      |


### 按年份统计的临床表记录


| 年份组       | 行数  | 去重后 `record_key_raw` 数 |
| --------- | --- | ---------------------- |
| 2018      | 565 | 563                    |
| 2019      | 514 | 514                    |
| 2020_2023 | 24  | 24                     |
| 2024      | 292 | 291                    |
| 2025      | 492 | 491                    |
| external  | 619 | 492                    |


### 关于“病人数”的说明

这里必须特别说明一个容易误解的点：

- 当前 `dataset/` 已经**没有**旧版那种正式患者级注册目录
- 因此本目录下“病人数”不能再像旧文档那样直接从 `patient_info.json` 精确统计
- `clinical_table_registry.csv` 里的 `record_key_raw` 去重数，只能看作**临床表层面的病例键数量**
- 它可以辅助理解规模，但**不能直接当作最终实验口径的患者数**

如果后面要恢复患者级统计，优先读取 `data/registry/patient_media_registry.csv`，不要重新扫描 `dataset/` 物理目录。

## 患者级图片+视频注册表（2026-06-13）

`dataset/` 继续保存物理样本；患者级图片/视频管理入口已经补到 `data/registry/` 与 `pipeline/data/patient_media_tstaging_v1/`。

### 三层口径

| 层级 | 路径 | 粒度 | 用途 |
| --- | --- | --- | --- |
| 物理样本层 | `dataset/internal/manifest.csv`、`dataset/external/manifest.csv` | 单张图像/切面 | 预处理、分割、ROI、物理文件统计 |
| 患者注册层 | `data/registry/patient_media_registry.csv`、`patient_media_sample_index.csv` | 患者 / 样本 | 病例管理、图片+视频聚合、覆盖率审计 |
| 训练导出层 | `pipeline/data/patient_media_tstaging_v1/*_clinical.csv` | 样本（带患者字段） | 模型训练与评估；兼容现有 T 分期 pipeline（含 loop） |
| 真视频对齐层 | `dataset/training_views/t_staging_real_cine/` | 病人 / 样本（仅 `cached`） | **视频 T 分期推荐入口**：监督表 + `splits/by_eval_role/` + 标注队列 |

真视频训练读法（2026-07）：

```bash
python3 scripts/build_real_cine_aligned_view.py --clean
python3 scripts/freeze_real_cine_training_package.py
```

- 监督病人/样本：`t_staging_real_cine/alignment/patients_aligned_supervised.csv`（557 / 2731）
- 汇报拆分：`t_staging_real_cine/splits/by_eval_role/`（prospective 误落 `test_external` 已纠正为 `test_prospective`）
- 无 T 真视频队列：`t_staging_real_cine/labeling_queue/`
- 图像泛化评测仍优先 Phase0 screened contracts，不要用本视图替代

### 核心 registry

- `data/registry/patient_media_sample_index.csv`：每个 manifest 样本一行，连接图像路径、crop 视频、raw 视频、split、T 分期与质量标记。
- `data/registry/patient_media_registry.csv`：每个 `patient_id` 一行，汇总该患者的图像数、视频数、真实视频数、loop 视频数、split 与临床可用性。
- `data/registry/patient_media_registry_summary.json`：构建统计与患者级 split 泄漏检查结果。
- `data/registry/patient_split_leakage_report.json`：独立的 split 泄漏审计报告。

### 视频语义

| 字段/模式 | 含义 |
| --- | --- |
| `video_mode=cached` | 由真实 cine/源视频转换得到的 crop MP4 |
| `video_mode=loop_still` | 由静态截图生成的循环 MP4，不是真实录像 |
| `video_match_status=raw+crop` | 同时找到源视频与 crop 视频 |
| `video_match_status=crop_only` | 只有 crop MP4，未匹配到源视频 |

训练视频模型时，**只使用 `cached`（真 cine）**。全部 `loop_still` crop MP4（7527）已于 2026-07-27 隔离至 `dataset/_quarantine/loop_still/`（见 `path_migration_log.csv`），活跃 `crop_ui/videos` 中不再保留。

### 构建与导出

```bash
python scripts/build_patient_media_registry.py
python scripts/export_patient_media_splits.py
python scripts/verify_patient_split_leakage.py
```

当前复核规模（2026-06-13）：

| 指标 | 数量 |
| --- | ---: |
| 样本索引行数 | 13,763 |
| 患者注册行数 | 2,593 |
| 已链接训练 CSV 的样本 | 9,436 |
| 真实视频样本 | 6,237 |
| 静帧 loop 样本 | 7,527 |
| 患者级 split 冲突 | 0 |

### 训练读取约定

- 做 **T 分期图像训练/评估**：继续优先读 `pipeline/data/tstaging_4class_region_contrastive_full/regions/*_clinical.csv`。
- 做 **患者管理、视频覆盖审计、病例级聚合**：读 `data/registry/patient_media_*.csv`。
- 做 **带视频列的训练导出**：读 `pipeline/data/patient_media_tstaging_v1/*_clinical.csv`；新增列为 `crop_video_path`、`raw_video_path`、`video_mode`、`video_match_status`、`patient_media_count`。

一个患者可以对应多张图像和多个视频；**split 必须按 `patient_id` 分配**，禁止同一患者跨 `train/val/test`。

## 命名与文件格式说明

### 内部数据

内部数据同时存在多种原始格式：

- `.jpg`
- `.dcm`
- 极少量 `.bmp`

其中 `manifest.csv` 统计得到：


| 扩展名    | 样本数   |
| ------ | ----- |
| `.jpg` | 5,615 |
| `.dcm` | 5,043 |
| `.bmp` | 1     |


### 外部数据

外部数据以图像文件为主，也包含部分 DICOM：


| 扩展名    | 样本数   |
| ------ | ----- |
| `.jpg` | 2,656 |
| `.dcm` | 200   |


### 命名提醒

外部数据里中心名本身就是重要分组键，使用时建议始终保留完整路径，不要只保留纯文件名。原因很简单：

- 同名文件在不同中心下可能代表完全不同的样本
- 仅用 basename 建索引，后面很容易把不同中心的数据混在一起

## 当前最适合的训练输入

如果目标还是做当前这版胃癌分割 / 定位 / 后续分类实验，建议优先使用：

- 内部训练：`dataset/internal/training_2018_2024/*/crop_ui/`
- 内部前瞻测试：`dataset/internal/prospective_2025/2025/crop_ui/`
- 外部测试：`dataset/external/*/crop_ui/`

原因是：

- `crop_ui/` 去掉了界面边框，比 `original/` 更稳定
- `crop_roi/` 是依赖真值 mask 紧框裁切得到的，不适合直接当第一阶段输入，否则会有信息泄漏风险
- `original/` 更适合做复核、可视化和对照实验

## 建议的后续整理方向

当前 `dataset/` 已经可以支撑图像级实验，但如果后面想把数据说明做得更完整，下一步最值得补的是：

1. 正式患者级注册表
2. T 分期映射表
3. 患者级 split 清单
4. 统一的 QC / 可用性状态表
5. 患者级和中心级的最终统计脚本

## 一句话总结

当前 `dataset/` 的正式口径，已经从旧版“患者级全量资料库”切换为“图像级直接手术正式数据集”：

- 内部按年份组织，并单独保留 `2025` 前瞻池
- 外部按中心组织，默认作为外部测试
- 正式统计以 `manifest.csv` 为准
- 临床表目前只是整理层，不是最终患者注册表

