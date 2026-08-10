# GastricTstaging — Claude Code 项目说明

医学影像 T 分期研究仓库。改代码前先读 [START_HERE.md](START_HERE.md) 和 [REPO_LAYOUT.md](REPO_LAYOUT.md)。

## 入口（SSOT）

| 目标 | 路径 |
|------|------|
| 第一次打开 | `START_HERE.md` |
| 七类资产地图 | `REPO_LAYOUT.md` |
| 系统架构 | `docs/ARCHITECTURE.md` |
| 当前主线 | `docs/mainline/tstaging_current_mainline.md` |
| 数据口径 | `dataset/DATASET_GUIDE.md` |
| 脚本索引 | `scripts/README.md` |
| 训练/实验 | `pipeline/README.md`、`configs/` |
| 维护规则 | `MAINTENANCE.md` |

不要从根目录乱点 `archive/`、`_compat/`、中文遗留目录；正式口径以 `docs/`、`dataset/`、`scripts/` 为准。

## 环境

- Python 3，脚本多用 `python3 scripts/<name>.py --help` 查参数
- 仓库根：`GASTRIC_ROOT` / `GASTRIC_TSTAGING_ROOT` / `GASTRIC_PROJECT_ROOT`
- 方向标注：`DIRECTION_ANNOTATOR_DATA_ROOT`
- 前端：`apps/gastric_scan_next/`、`apps/direction_annotator/`

## 工作原则

1. **病例级划分**：验证必须患者级，禁止图像级泄漏
2. **先登记后移动**：路径变更写 `data/metadata/path_migration_log.csv`
3. **不删大产物**：`artifacts/`、`pipeline/experiments/tree/`、`2025_Patient_Videos/` 等勿 `rm`；删除需用户确认
4. **不 rename** `dataset/external/` 下医院目录名
5. **Git**：只提交文档/registry/小脚本；不批量提交影像、权重、zip
6. **临床/阅片包**：`docs/clinical_validation/` 含脱敏阅片材料；改前确认，不写入患者标识

## 改完必跑（按改动范围选）

```bash
python scripts/check_repo_root.py
python scripts/verify_repo_paths.py
```

涉及 registry / 脚本登记时：

```bash
python scripts/build_script_registry.py
python scripts/build_asset_manifest.py
```

## 常见任务

- **YOLO 检测 baseline**：见 `scripts/README.md` §1 与 `experiments/baselines/detection_baseline_v1/`
- **阅片包 / crop 视频**：`scripts/crop_prospective_reader_videos.py`、`scripts/consolidate_2025_raw_patient_videos.py` → `docs/clinical_validation/`
- **出图**：黑底、`Times New Roman`，见 `docs/visualization/visualization_standard.md`

## 对 Claude 的期望

- 探索大仓库时用 Explore subagent，避免主对话塞满 grep 结果
- 新脚本更新 `scripts/script_registry.csv`；新实验更新 `experiments/registry.csv`
- 最小 diff；不重构无关代码；不主动 commit
- 路径/命令以 `--help` 和 SSOT 文档为准，不猜过期命令
