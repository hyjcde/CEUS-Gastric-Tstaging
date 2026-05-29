# 模型资产（Models）

本目录是**索引入口**，权重实体在 `artifacts/model_weights/` 与 `pipeline/experiments/tree/`。

## 快速查找

| 任务 | 登记位置 |
|------|----------|
| T 分期四分类（冻结） | [pipeline/experiments/mainlines/tstaging_4class/baseline_registry.yaml](../pipeline/experiments/mainlines/tstaging_4class/baseline_registry.yaml) |
| 分数与对比 | [pipeline/experiments/tables/tstaging_4class_mainline_scoreboard.csv](../pipeline/experiments/tables/tstaging_4class_mainline_scoreboard.csv) |
| 实验 run 目录 | [experiments/registry.csv](../experiments/registry.csv) |
| YOLO 预训练 | `artifacts/model_weights/yolo/yolo11*.pt`（根目录 symlink） |
| 检测/分割 baseline | [experiments/baselines/](../experiments/baselines/) |
| nnU-Net 等本地包 | `external/`（gitignore） |

## Agent 后端登记（SSOT）

机器可读：[pipeline/agent/config/agent_backend_registry.yaml](../pipeline/agent/config/agent_backend_registry.yaml)

人类可读契约：[docs/mainline/agent_api_contract.md](../docs/mainline/agent_api_contract.md)

计划/工具配置：[pipeline/agent/configs/model_tool_backends.yaml](../pipeline/agent/configs/model_tool_backends.yaml)

## 规则

- 新 checkpoint 必须在 run 目录写 `README.md` 并更新 `experiments/registry.csv`
- 不要把 `.pt`/`.pth` 提交到 Git

详见 [../REPO_LAYOUT.md](../REPO_LAYOUT.md) §7。
