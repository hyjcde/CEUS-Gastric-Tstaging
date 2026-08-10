# GastricTstaging 仓库维护说明

本文档定义本仓库的长期整理与迁移规则。整理计划见 Cursor 计划「安全分步仓库整理」；**请勿直接删除实体数据**，除非下文「允许删除」一节明确允许。

## 正式入口（SSOT）

| 用途 | 路径 |
|------|------|
| **第一次打开** | [START_HERE.md](START_HERE.md) |
| 项目总览 | [README.md](README.md) |
| **七类资产地图** | [REPO_LAYOUT.md](REPO_LAYOUT.md) |
| 系统架构 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 文档导航 | [docs/README.md](docs/README.md) |
| 文档全索引 | [docs/DOCUMENT_MAP.md](docs/DOCUMENT_MAP.md) |
| 数据口径 | [dataset/DATASET_GUIDE.md](dataset/DATASET_GUIDE.md) |
| 脚本索引 | [scripts/README.md](scripts/README.md) |
| 脚本登记 | [scripts/script_registry.csv](scripts/script_registry.csv) |
| 实验登记 | [experiments/registry.csv](experiments/registry.csv) |
| 大产物说明 | [experiments/LARGE_ARTIFACTS.md](experiments/LARGE_ARTIFACTS.md) |
| 资产清单 | [data/metadata/asset_manifest.csv](data/metadata/asset_manifest.csv) |
| 路径迁移日志 | [data/metadata/path_migration_log.csv](data/metadata/path_migration_log.csv) |
| 治理执行口径 | [docs/project_governance.md](docs/project_governance.md) |
| 数据注册表 | [data/registry/dataset_registry.csv](data/registry/dataset_registry.csv) |

## 环境变量

- `GASTRIC_ROOT` / `GASTRIC_TSTAGING_ROOT` / `GASTRIC_PROJECT_ROOT`：仓库根（见 [pipeline/agent/core/repo_paths.py](pipeline/agent/core/repo_paths.py)）
- `DIRECTION_ANNOTATOR_DATA_ROOT`：方向标注工具数据根（见 [apps/direction_annotator/src/lib/dataRoot.ts](apps/direction_annotator/src/lib/dataRoot.ts)）

## 迁移安全规则（Phase 0–7）

1. **先登记，后移动**：每次移动写入 [data/metadata/path_migration_log.csv](data/metadata/path_migration_log.csv)。
2. **先 symlink，后删**：原路径保留符号链接至少 2 周；验证通过后再考虑移除链接（不删实体）。
3. **不搬大实验树**：`experiments/`、`pipeline/experiments/` 仅索引，不整体搬迁。
4. **不 rename** `dataset/external/` 下医院目录名（与 `dataset/tables/center_name_registry.csv` 绑定）。
5. **Git**：只提交治理文档、registry、小脚本；不批量提交影像与 GB 级产物。
6. **论文聚合入口**：根目录 `paper/` 只聚合原稿、笔记、DOI 索引和已有文献摘要，不复制大体积全文。

## 验证（每阶段必跑）

```bash
python scripts/check_repo_root.py
python scripts/verify_repo_paths.py
python scripts/build_asset_manifest.py
```

可选刷新登记：

```bash
python scripts/build_dataset_registry.py
python scripts/build_script_registry.py
python scripts/build_experiments_registry.py
python scripts/build_workspace_inventory.py
python scripts/classify_git_status.py
python scripts/build_paper_ablation_matrix.py
python scripts/build_model_inventory.py
python scripts/build_log_index.py
```

结果写入 `data/metadata/verify_YYYYMMDD.json` 与 `root_check_YYYYMMDD.json`。全部 `pass` 后再进入下一阶段。

## 根目录守门

仅允许：4 个入口 md、`apps/`…`scripts/` 共 12 个工作目录、根目录 `paper/` 论文聚合工作区、`_compat/`、以及 `.env` / `.gitignore` / `.git` / `.vscode`。其它根目录项只报告不自动删除（`scripts/check_repo_root.py`）。

## 新增资产检查清单

| 新增 | 必须先做 |
|------|----------|
| 文档 | 判 Tier A/B/C；实验报告 → `pipeline/experiments/reports/<name>/` |
| 论文材料 | 进入根目录 `paper/`；原稿和笔记保留 SSOT 链接 |
| 数据 | 写入 `data/registry/` + `asset_manifest`，再进 `dataset/` |
| 权重 | `artifacts/model_weights/` + 更新 `experiments/registry.csv` |
| 实验 run | `experiments/registry.csv` + run 目录 README |
| 脚本 | 更新 `scripts/script_registry.csv`（status 不可留空） |
| 根目录文件 | **禁止**（除 4 个 md 更新） |

## 回滚原则

1. 旧路径写入 `path_migration_log.csv`
2. 可能被引用的旧路径保留 `_compat/` symlink
3. 运行 `check_repo_root.py` + `verify_repo_paths.py`
4. 失败时只回滚 symlink/小文件，**不删**数据实体

## 允许删除（极少数）

- 与 `data/raw/` 内容完全一致的 `.bak_YYYYMMDD` 备份目录（验证后、且 migration log 已标记 `verified=yes`）
- 错误的 symlink（实体仍在目标路径）

**禁止删除**：`dataset/` 影像、`pipeline/experiments/tree/` 权重、未验证的原始中文目录实体。

## 阶段 Gate 摘要

| 阶段 | 内容 | Gate |
|------|------|------|
| 0 | 盘点 | `asset_manifest.csv` 覆盖根目录一级项 |
| 1 | `.gitignore` + registry 初版 | README 链到本文档 |
| 2 | 根目录小文件 + symlink | `verify_repo_paths.py` pass |
| 3 | 中文目录 → `data/raw/legacy_*` | symlink 可读 + manifest 抽样 pass |
| 4 | `docs copy` → `archive/docs_legacy/` | 入口文档已更新 |
| 5 | `script_registry` + legacy 标记 | 主线脚本 status=current |
| 6 | 实验 registry，不搬 800GB | 可查主 baseline `run_dir` |
| 7 | App/Agent 路径登记 | 路径文件存在 |
| 8 | 清理 `.bak`（已完成 2026-05-29） | `cleanup_migration_backups.py` |

## 刷新资产清单

```bash
python scripts/build_asset_manifest.py
```
