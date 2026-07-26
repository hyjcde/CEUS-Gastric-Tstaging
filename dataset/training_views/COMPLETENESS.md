# 数据齐全性检查

检查时间：2026-07-27（loop_still 已隔离）

## 结论

| 项 | 状态 |
|----|------|
| **loop_still crop MP4** | **已隔离 7527** → `dataset/_quarantine/loop_still/` |
| T 分期图 / mask / ann / overlay | 仍保留（含原 loop 对应静图） |
| `videos_real`（cached） | **6234** |
| **真视频监督** | **557 人 / 2731 样本** |
| registry `loop_still_samples` | **0** |

```bash
python3 scripts/quarantine_loop_still_videos.py   # 已执行
python3 scripts/build_patient_media_registry.py
python3 scripts/build_real_cine_aligned_view.py --clean
python3 scripts/freeze_real_cine_training_package.py
```

缺口明细：`data/registry/patient_training_view/gaps/COMPLETENESS_GAPS.md`
HTML：`docs/mainline/real_cine_data_inventory.html`
