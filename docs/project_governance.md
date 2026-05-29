# 项目治理（执行口径）

**不是日常入口。** 新人请读 [START_HERE.md](../START_HERE.md)。本文档供维护者与 Agent 执行整理计划时对照。

## 七类资产

见 [REPO_LAYOUT.md](../REPO_LAYOUT.md)。

## 禁止

- 不移动 `dataset/**` 影像本体
- 不移动 `pipeline/experiments/tree/`
- 不 `git add .`
- 根目录禁止新增实体文件（除 4 个入口 md 更新）

## 每阶段验收

```bash
python scripts/check_repo_root.py
python scripts/verify_repo_paths.py
python scripts/build_asset_manifest.py
```

## Git 提交顺序（4 批）

1. `governance` — 入口文档、MAINTENANCE、`.gitignore`
2. `registries` — `data/registry/`、`data/metadata/`、`experiments/registry.csv`
3. `tooling` — `check_repo_root.py`、`build_*registry*`、`verify_repo_paths.py`
4. `path-fixes` — apps/pipeline/scripts 路径修复

永不提交：`artifacts/`、影像树、权重、`pipeline/experiments/tree/`。

## 新增资产检查清单

| 新增内容 | 必须先做 |
|----------|----------|
| 文档 | 判 Tier A/B/C；实验报告 → `pipeline/experiments/reports/<name>/` |
| 数据 | 写入 registry + manifest，再进 `dataset/` |
| 权重 | `artifacts/model_weights/` + `experiments/registry.csv` |
| 实验 run | `experiments/registry.csv` + run 目录 README |
| 脚本 | 更新 `scripts/script_registry.csv` |

## 回滚

见 [MAINTENANCE.md](../MAINTENANCE.md) 迁移规则；失败只删错误 symlink，不删数据实体。
