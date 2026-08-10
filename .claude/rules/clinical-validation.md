---
paths:
  - "docs/clinical_validation/**"
  - "scripts/crop_prospective_reader_videos.py"
  - "scripts/consolidate_2025_raw_patient_videos.py"
  - "scripts/*reader*"
---

# 临床验证 / 阅片包

- 阅片包在 `docs/clinical_validation/`（如 `reader_study_2025_raw/`）；自包含 HTML + crop MP4，勿破坏相对路径
- 不展示/写入患者临床信息、AI 判断、病理分期到阅片界面（见各 README.txt）
- 改 `index.html`、密码逻辑、导出 JSON 格式前与用户确认
- 视频来源：`dataset/internal/manifest.csv`、`dataset/external/manifest.csv`；crop 输出见 `crop_prospective_reader_videos.py` 文件头
- 打包 zip 后更新 README 中的病例数、生成时间、路径说明
