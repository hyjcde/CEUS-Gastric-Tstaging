# 真视频无 T 标签 · 标注队列

生成：2026-07-26T17:17:55Z

- 总病人：**360**（有 `video_mode=cached`，缺可用 T）
- 按队列优先级：{'P2_external': 58, 'P1_prospective': 297, 'P0_internal': 5}
- 按队列/中心：`by_hospital/`
- 总表：`patients.csv`

**不要**把这些人直接并进监督训练。标完 T 后重跑：

```bash
python3 scripts/build_patient_media_registry.py
python3 scripts/build_real_cine_aligned_view.py --clean
python3 scripts/freeze_real_cine_training_package.py
```
