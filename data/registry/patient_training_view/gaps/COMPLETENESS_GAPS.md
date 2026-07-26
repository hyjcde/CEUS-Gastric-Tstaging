# 齐全性检查报告（真视频主线）

生成：2026-07-26T16:24:48Z

审计脚本结果：媒体/软链/监督对齐 **19/20 PASS**；唯一“FAIL”为多 canonical_key（实为系列命名，非缺文件）。

## 总览

| 层级 | 状态 | 说明 |
|------|------|------|
| 真视频监督媒体 | **齐** | 557 人 / 2731 样本，图+crop视频+roi+ann+overlay |
| 真视频全量媒体 | **齐** | 6234 cached，软链断链 0 |
| 病理/T 标签 | **未齐** | 627 真视频无 T；全库 848 无 T/临床 |
| raw 源视频 | **部分齐** | 监督样本 1297 raw+crop / 1434 仅 crop |
| 良恶性视频 | **未齐** | 2746 图 vs 259 视频 |
| split | **可用** | `splits/by_eval_role/` 泄漏 PASS |

## 逐项

| ID | 层 | 状态 | 项 | 数量/说明 |
|----|----|------|----|-----------|
| M1 | media | OK | 真视频监督集 图/视频/roi/ann/overlay | 557人 / 2731样本 全齐，断链0 |
| M2 | media | OK | 全部 cached 样本 (6234) by_modality 软链 | 6234×5 全齐 |
| M3 | media | PARTIAL | 监督真视频缺 raw 源（仅 crop_only） | 280 人仅有 crop；样本级 crop_only=1434/2731 |
| M4 | media | GAP | 良恶性/胃炎 有图无视频 | 图 2746 / 视频 259；sample_gaps=2746 |
| L1 | label | GAP | 真视频无 T（标注队列） | 627 人 / 3503 样本（媒体齐） |
| L2 | label | GAP | 全库无 T/临床 | 848 人（含真视频≈627 + 其余 loop/无可用） |
| L3 | label | INFO | T4+ 粗标签（未分 T4a/T4b） | 50 人监督集 |
| L4 | label | EXCLUDED | 可训练但仅有 loop_still（无真 cine） | 1188 人；**视频视图已排除**；见 `samples_excluded_loop_still.csv` |
| S1 | split | OK | eval_role 病人级泄漏 | PASS（已 remap prospective/internal 错位） |
| S2 | split | INFO | 外部医院在 train/val（福建省肿瘤医院遗留） | 41 人 |
| S3 | split | INFO | val 较小 | 28 人 / 146 样本 |
| Q1 | quality | INFO | 同一 patient_id 多个 canonical_key（DICOM1/2 系列） | 113 人（监督真视频仅 4）；非缺文件 |
| Q2 | quality | GAP | registry real_video_count 与 sample video_mode 不一致 | 2 人（例：标成 real 实际 loop_still） |
| Q3 | quality | OK | {center} 重复模板目录 | 已 quarantine，live 路径不存在 |


## 建议优先级

1. **P0 用现成监督集训练视频模型**：`t_staging_real_cine/splits/by_eval_role/{train,val}`（不要等齐 raw / 627 标注）。
2. **P1 标注队列**：`t_staging_real_cine/labeling_queue/`（627；协和+莆田学院占大头）。
3. **P2 修 registry 视频计数漂移**：`gaps/registry_video_mode_mismatch.csv`（2）。
4. **P3** 可选：补 raw、细拆 T4+、良恶性补视频——不影响当前真视频 T 分期监督训练。

## 已齐、可直接用

- `dataset/training_views/t_staging_real_cine/alignment/samples_aligned_supervised.csv`
- `.../splits/by_eval_role/` + `by_split/`
- `data/registry/patient_training_view/samples_video_real_cine.csv`（2731，与上表一致）

## 相关 CSV

- `gaps/supervised_real_cine_crop_only_no_raw.csv` — 监督真视频缺 raw 源（仅 crop_only）
- `data/registry/crop_ui_asset_audit/sample_gaps.csv` — 良恶性/胃炎 有图无视频
- `dataset/training_views/t_staging_real_cine/labeling_queue/patients.csv` — 真视频无 T（标注队列）
- `gaps/patients_no_t_stage.csv` — 全库无 T/临床
- `gaps/supervised_t4plus_coarse_label.csv` — T4+ 粗标签（未分 T4a/T4b）
- `gaps/patients_usable_only_loop_still.csv` — 可训练但仅有 loop_still（无真 cine）
- `gaps/patients_multiple_canonical_keys_annotated.csv` — 同一 patient_id 多个 canonical_key（DICOM1/2 系列）
- `gaps/registry_video_mode_mismatch.csv` — registry real_video_count 与 sample video_mode 不一致
