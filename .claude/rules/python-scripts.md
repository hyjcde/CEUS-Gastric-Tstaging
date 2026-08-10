---
paths:
  - "scripts/**"
  - "pipeline/**/*.py"
---

# Python 脚本规则

- 新脚本放 `scripts/`，文件头 docstring 说明用途与输入输出路径
- 用 `Path(__file__).resolve().parents[1]` 或 `pipeline/agent/core/repo_paths.py` 解析项目根，勿硬编码 `/media/...`
- 参数用 `argparse`；改 CLI 后提醒用户跑 `--help`
- 登记：更新 `scripts/script_registry.csv`（status: current/legacy/runtime）
- 依赖：`cv2`、`pandas`、`pydicom` 等按现有脚本 import；不随意加新依赖
- 长任务（ffmpeg、批量 crop）先 `--dry-run` 或小样本试跑（若脚本支持）
