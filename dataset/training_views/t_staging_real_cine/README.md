# T 分期 · 真视频（real cine）对齐视图

生成：`python3 scripts/build_real_cine_aligned_view.py --clean`

## 定义

- **只要真视频**：`video_mode=cached`（`videos/` 目录）
- **不要** `loop_still`（静图循环）
- **对齐清楚**：
  - 样本级：`alignment/samples_real_cine.csv`
  - 病人级：`alignment/patients_real_cine.csv`
  - **可监督训练（图+真视频+T病理）**：`patients_aligned_supervised.csv` / `samples_aligned_supervised.csv`
  - 有真视频但缺 T 标签：`patients_real_cine_unlabeled.csv`

## 规模

| 集合 | 数量 |
|------|-----:|
| 真视频样本 | 6234 |
| 有真视频的病人 | 1184 |
| **已对齐可训练**（有 T） | **557 人 / 2731 样本** |
| 真视频但无 T 标签 | 627 人 |

监督病人按桶：`{'external': 231, 'internal': 113, 'prospective': 213}`

## 目录

```text
by_modality/<internal|prospective|external>/<年或医院>/
  images/  videos/  roi_masks/  annotations/  overlays/
by_patient/<cohort>/<bucket>/<patient_id>/
  images/ videos/ roi_masks/ annotations/ overlays/ pathology.json
alignment/*.csv
```

## 训练怎么读

1. 病人列表：`alignment/patients_aligned_supervised.csv`
2. 样本列表：`alignment/samples_aligned_supervised.csv`
3. 划分：**按 patient_id**
4. 视频路径列：`crop_video_path` 或视图内 `view_video`

未标注的 627 名真视频病人不要当 T 分期监督；可另做标注队列。

## 冻结拆分与标注队列

复跑：`python3 scripts/freeze_real_cine_training_package.py`

| 路径 | 用途 |
|------|------|
| `splits/by_eval_role/` | **推荐**汇报/训练角色（已纠正 prospective→test_prospective） |
| `splits/by_legacy_split/` | 与 `patient_media_registry.split` 一致 |
| `by_split/<eval_role>/` | 按角色的病人软链（557） |
| `labeling_queue/` | 627 名真视频无 T |
| `alignment/patients_with_eval_role.csv` | 监督病人 + eval_role |
| `splits/leakage_report.json` | 泄漏检查（pass=True） |

