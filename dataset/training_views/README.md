# 训练媒体视图（软链，不拷贝原片）

生成时间：2026-07-26T16:33:38Z

```bash
python3 scripts/build_training_media_view.py
# 重建前清空：
python3 scripts/build_training_media_view.py --clean
```

## 设计（在已有 crop_ui 之上）

原数据已经按中心/年份整理在 `dataset/**/crop_ui/`。  
本视图只做 **训练友好入口**：

1. **任务分开**
   - `t_staging/`：恶性胃癌 T 分期（有图 / 视频 / mask / 病理分期标签）
   - `benign_malignant/`：良恶性/胃炎外部（与 T 分期拆开，禁止混进 T1–T4+）
2. **内外部 × 年份/中心**
   - T 分期：`internal/2018|2019|2020_2023|2024`、`prospective/2025`、`external/<医院>`
   - 良恶性：`external/<医院>`
3. **模态分目录（方便 DataLoader）**
   - `images/` · `videos_real/`（**仅真 cine**）· `roi_masks/` · `annotations/` · `overlays/`
   - **默认不链 `videos_loop`**（`loop_still` 静图循环已排除；需要时加 `--include-loop`）
4. **按病人**
   - `t_staging/by_patient/<cohort>/<bucket>/<patient_key>/…` + `pathology.json`（`videos/` 仅真 cine）
5. **病理/标签表**
   - `t_staging/pathology/labels_by_patient.csv`
   - `t_staging/pathology/patients_image_video_pathology.csv`（图+可用临床）
   - `benign_malignant/pathology/clinical_records.csv`

## 推荐训练读法

| 任务 | 模态目录 | 标签 |
|------|----------|------|
| T 分期图像 | `t_staging/by_modality/**/images` + `roi_masks` | `pathology/labels_by_sample.csv` |
| T 分期视频 | **`t_staging_real_cine/`** 或 `t_staging/**/videos_real` | 仅 `video_mode=cached` |
| 按病人 batch | `t_staging/by_patient/...` / `t_staging_real_cine/by_patient/...` | `pathology.json` |
| 良恶性 | `benign_malignant/by_modality/external/<医院>/` | `pathology/labels_by_patient.csv` |

硬规则：split 必须按 **patient_id**；**不要用 loop_still**。

## 库存摘要

```json
{
  "created_at": "2026-07-26T16:33:38Z",
  "out": "dataset/training_views",
  "exclude_loop_still_video": true,
  "t_staging": {
    "task": "t_staging",
    "samples_linked": 13763,
    "patients_in_registry": 2593,
    "patients_with_media_links": 2593,
    "patients_image_video_pathology": 1745,
    "exclude_loop_still_video": true,
    "skipped_loop_still_video": 0,
    "link_counts": {
      "link_images": 13763,
      "link_roi_masks": 13763,
      "link_annotations": 13763,
      "link_videos_real": 6234,
      "link_overlays": 13763,
      "patient_links": 47525,
      "link_videos_other": 2
    },
    "miss_counts": {}
  },
  "benign_malignant": {
    "task": "benign_malignant",
    "centers": [
      "三明市第二医院",
      "中核五〇四医院",
      "宁德市医院",
      "福建省德化县医院",
      "福建省肿瘤医院",
      "莆田学院附属医院"
    ],
    "stats": {
      "link_images": 2746,
      "link_roi_masks": 2746,
      "link_annotations": 2746,
      "link_overlays": 2746,
      "link_videos": 259
    },
    "note": "Separated from t_staging; gastritis/inflammation, not T1–T4+"
  },
  "source": {
    "t_staging_media": "dataset/**/crop_ui + data/registry/patient_media_*.csv",
    "benign_malignant": "dataset/gastritis_external"
  }
}
```

物理 SSOT 仍是 `dataset/internal|external|gastritis_external`；本目录可随时 `--clean` 重建。
