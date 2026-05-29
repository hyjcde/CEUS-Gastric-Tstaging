# 实验记录（Experiments）

人类可读的实验入口；大体量 run 在 [pipeline/experiments/](../pipeline/experiments/)，见 [LARGE_ARTIFACTS.md](LARGE_ARTIFACTS.md)。

## 索引

- [registry.csv](registry.csv) — 实验 ID → run_dir / 配置 / 状态
- [../pipeline/experiments/tables/tstaging_4class_mainline_scoreboard.csv](../pipeline/experiments/tables/tstaging_4class_mainline_scoreboard.csv) — T 分期主表

## 分区

| 目录 | 任务 |
|------|------|
| [baselines/](baselines/) | 检测 / 分割 / T 分期基线入口 |
| [detection/](detection/) | YOLO 等 |
| [segmentation/](segmentation/) | 分割实验 |
| [tstage_classification/](tstage_classification/) | T 分期 |
| [archive_tstaging/](archive_tstaging/) | 旧 Tstaging 证据 |

分析图表等产出在 [../artifacts/results/](../artifacts/results/)。

详见 [../REPO_LAYOUT.md](../REPO_LAYOUT.md) §3。
