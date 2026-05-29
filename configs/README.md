# 配置（Configs）

**新正式实验** 的 YAML 优先放在本目录，按任务分子目录：

- `detection/` — YOLO
- `segmentation/` — SMS、UNet、DINO 等
- `tstage/` — T 分期
- `joint/` — 联合审查配置

## 与 pipeline/configs 的关系

| 位置 | 用途 |
|------|------|
| **本目录 `configs/`** | 项目级、可复现的正式配置（SSOT） |
| **`pipeline/configs/`** | 历史运行与框架内置配置（参考） |

每次正式 run 必须在实验目录保存 **`config_snapshot.yaml`**（见 [docs/experiment_governance/experiment_structure.md](../docs/experiment_governance/experiment_structure.md)）。

详见 [../REPO_LAYOUT.md](../REPO_LAYOUT.md) §5。
