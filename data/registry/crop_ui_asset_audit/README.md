# crop_ui 图片 / mask / 视频完整性审计

- 时间：2026-07-24T06:39:22Z
- 复跑：`python3 scripts/audit_crop_ui_image_mask_video.py`
- crop_ui 根目录数：22
- 合计 images=16509 videos=13855 overlays=16509 roi_masks=16509 annotations=16509
- 四件套齐全（图+视频+overlay+roi+ann）：13763 / 16509 (83.4%)
- 图有对应视频：13763 (83.4%)
- 孤儿视频（无图匹配）：92（全部在 `dataset/external/{center}/crop_ui/videos`）

## 结论摘要

### T 分期主库（internal + external 医院目录）
各年 `crop_ui` 的 **images / overlays / roi_masks / annotations / videos 一一对应，无缺口**  
（2018–2025 + 外部医院合计 13763 套完整）。

### 视频重复（针对 13855 个 mp4）
- 唯一 basename：**13763**；额外 **92** 份
- 92 组均为 **MD5 内容完全相同** 的副本
- 全部是字面路径 `dataset/external/{center}/crop_ui/videos/`  
  与真实医院目录（中核五〇四 / 德化 / 佛山一）的重复  
- `{center}` 约 **352MB**，疑似模板目录残留；**未自动删除**（需你确认后再清）
- 无硬链接组（同 inode=0）

### 缺口（2746 张图无视频）
全部来自 `dataset/gastritis_external/processed_images/*/crop_ui`  
（胃炎外部：有图+overlay+roi+ann，**无 videos**）。与 T 分期 crop 视频池无关。

## 明细文件
- `per_root_summary.csv` — 各 crop_ui 根计数与覆盖
- `sample_gaps.csv` — 不完整样本（胃炎无视频）
- `video_basename_duplicates.csv` / `video_content_duplicates.csv` — 重复清单

> 本审计只生成登记表，未移动/删除任何大文件。
