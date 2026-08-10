# 配置（Configs）

**新正式实验** 的 YAML 优先放在本目录，按任务分子目录：

- `detection/` — YOLO
- `segmentation/` — SMS、UNet、DINO 等
- `tstage/` — T 分期
- `joint/` — 联合审查配置

## 与 pipeline/configs 的关系

| 位置 | 用途 |
|------|------|
| **本目录 `configs/`** | 检测/分割/联合任务 + **新实验优先落点** |
| **`pipeline/configs/`** | **当前 T 分期 4-class 主线 SSOT**（scoreboard / frozen baseline 引用） |

详见 [../pipeline/configs/TSTAGE_CONFIG_POLICY.md](../pipeline/configs/TSTAGE_CONFIG_POLICY.md)。

新 T 分期 run：可复制 `pipeline/configs/` 中主线 YAML 到 `configs/tstage/` 并登记 `ablation_matrix.csv`，或继续在 `pipeline/configs/` 运行并更新 registry。

每次正式 run 必须在实验目录保存 **`config_snapshot.yaml`**（见 [docs/experiment_governance/experiment_structure.md](../docs/experiment_governance/experiment_structure.md)）。

详见 [../REPO_LAYOUT.md](../REPO_LAYOUT.md) §5。
