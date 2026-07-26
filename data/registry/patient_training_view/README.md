# 病人级训练视图（logical，不搬像素）

生成时间：2026-07-26T16:34:04Z

```bash
python3 scripts/build_patient_training_view.py
```

## 怎么用

| 目标 | 读哪个 |
|------|--------|
| 按病人组织 | `patients.csv` / `patient_bundles.jsonl` |
| 图像/分割训练 | `samples_image_train.csv`（2733 样本 / 557 病人） |
| 视频 cine 训练 | `samples_video_real_cine.csv`（2731 样本 / 557 病人） |
| 已排除 loop | `samples_excluded_loop_still.csv`（0，**不要当视频**） |

硬规则：train/val/test **按 patient_id 划分**；视频只用 `cached`，不用 `loop_still`。

## 规模

- 病人总计：2593
- registry 可训练：1745
- 无临床/T：848
- 仅有 loop_still：0

## 还需要整理

- DONE: quarantine dataset/external/{center} → dataset/_quarantine/external__center_placeholder/
- DONE: real-cine supervised package → dataset/training_views/t_staging_real_cine/
- DONE: exclude loop_still from video training views (samples_excluded_loop_still.csv; no videos_loop links)
- DONE: prospective/internal mislabeled as test_external* → eval_role remap in t_staging_real_cine/splits/
- OPEN: 848 patients lack T/clinical — see t_staging_real_cine/labeling_queue/ for real-cine subset (627)
- OPEN: Rebuild joins for Putian/external into legacy region CSVs (path drift; prefer patient_media_*)
- KEEP: Prefer Phase0 screened contracts for clean image generalization eval
- KEEP: Do not mix gastritis_external into T-stage splits
- KEEP: loop_still is NOT training video — use t_staging_real_cine only

物理文件仍在 `dataset/**/crop_ui/`；本目录只做索引。
