# 仓库资产布局（七类分明）

本文件是 **「什么东西放哪里」** 的权威地图。系统逻辑见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)；路径迁移见 [MAINTENANCE.md](MAINTENANCE.md)。

| 类别 | 一句话 | 主目录 | 是否进 Git |
|------|--------|--------|------------|
| **1. 原始数据** | 未治理的 zip、遗留中文目录、视频抽帧 | `data/raw/`、`artifacts/raw_imports/` | 否（manifest 进 Git） |
| **2. 数据集** | 正式预处理影像 + manifest + 建模 CSV | `dataset/`、`pipeline/data/`、`data/registry/` | 仅清单与说明 |
| **3. 实验记录** | run 产物、报告、scoreboard | `experiments/`、`pipeline/experiments/` | 仅 README/registry/小表 |
| **4. 文档** | 规范、主线、论文 | `docs/`、`archive/docs_legacy/` | 是（不含大体积 figures） |
| **5. 代码脚本** | CLI、训练框架、配置 | `scripts/`、`pipeline/`、`configs/` | 是 |
| **6. 平台** | Next.js / Electron 应用 | `apps/` | 是（不含 node_modules） |
| **7. 模型** | 权重与 checkpoint 索引 | `artifacts/model_weights/`、`pipeline/experiments/tree/` | 否（registry 进 Git） |

根目录只保留：**START_HERE、README、REPO_LAYOUT、MAINTENANCE** + **12 个工作目录** + **`paper/` 论文聚合工作区** + **`_compat/`**（旧路径 symlink，非正式入口）。

打开仓库请读 [START_HERE.md](START_HERE.md)。

---

## 1. 原始数据（Raw）

**用途**：追溯用；不直接进入训练，除非写入 registry。

| 路径 | 内容 |
|------|------|
| [data/raw/README.md](data/raw/README.md) | 遗留目录说明 |
| `data/raw/legacy_gastric_staging/` | 原 `胃癌分期/` |
| `data/raw/legacy_external_direct_surgery/` | 原 `胃癌直接手术外部测试集/` |
| `data/raw/legacy_lumen/` | 原 `胃腔/` |
| `data/raw/legacy_wall_viz/` | 原 `胃壁区域可视化方向/` |
| [artifacts/raw_imports/incoming/](artifacts/raw_imports/incoming/) | 根目录迁入的 zip |
| [artifacts/video_frames/](artifacts/video_frames/) | 原 `frames_1fps/` |
| `data/外省整理.zip` 等 | 待解压的中间 zip（见 data/） |

根目录 **symlink**（兼容旧脚本）：`胃癌分期` → `data/raw/legacy_gastric_staging` 等。

---

## 2. 数据集（Dataset）

**用途**：实验与 Agent 的正式数据口径。

| 路径 | 内容 |
|------|------|
| [dataset/](dataset/) | `internal/`、`external/`、`tables/`、`manifest.csv` |
| [dataset/DATASET_GUIDE.md](dataset/DATASET_GUIDE.md) | **数据 SSOT** |
| [data/registry/](data/registry/) | 注册表模板与正式表 |
| [data/splits/](data/splits/) | 冻结 split manifest |
| [data/annotation/](data/annotation/) | 方向标注 batch 与输出 |
| [pipeline/data/](pipeline/data/) | T 分期等 `*_clinical.csv`、特征缓存 |

---

## 3. 实验记录（Experiments）

**用途**：证据包、报告、可复现指标；大文件在磁盘，索引在 CSV。

| 路径 | 内容 |
|------|------|
| [experiments/](experiments/) | baseline 入口、`registry.csv` |
| [experiments/LARGE_ARTIFACTS.md](experiments/LARGE_ARTIFACTS.md) | 大体量说明 |
| [pipeline/experiments/reports/](pipeline/experiments/reports/) | 按主题的报告 |
| [pipeline/experiments/tables/](pipeline/experiments/tables/) | scoreboard 等 |
| [pipeline/experiments/tree/](pipeline/experiments/tree/) | 单次 run（~数百 GB） |
| [artifacts/results/](artifacts/results/) | 原 `results/` 分析产出 |
| [artifacts/reports/](artifacts/reports/) | 零散 CSV/导出 |

---

## 4. 文档（Docs）

| 路径 | 内容 |
|------|------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统架构 |
| [docs/README.md](docs/README.md) | 文档导航 |
| [docs/DOCUMENT_MAP.md](docs/DOCUMENT_MAP.md) | 全文档索引 |
| [docs/mainline/](docs/mainline/) | 当前主线 |
| [docs/paper/](docs/paper/) | 论文材料（原根 `paper/`） |
| [paper/](paper/) | 原稿、笔记和重点文献的统一聚合入口 |
| [archive/docs_legacy/docs_copy/](archive/docs_legacy/docs_copy/) | 原 `docs copy/` |

---

## 5. 代码与脚本（Code）

| 路径 | 内容 |
|------|------|
| [scripts/](scripts/) | 数据、训练、评估、出图 CLI |
| [scripts/script_registry.csv](scripts/script_registry.csv) | 脚本状态登记 |
| [pipeline/](pipeline/) | `lib/`、`run_experiment.py`、Agent |
| [configs/](configs/) | 正式实验 YAML（新实验优先） |
| [pipeline/configs/](pipeline/configs/) | 历史运行配置 |

---

## 6. 平台（Platform）

| 路径 | 内容 |
|------|------|
| [apps/README.md](apps/README.md) | 启动说明 |
| [apps/gastric_scan_next/](apps/gastric_scan_next/) | 病例浏览 + Agent 工作台 |
| [apps/direction_annotator/](apps/direction_annotator/) | 突破方向标注 |

环境变量：`GASTRIC_ROOT`、`DIRECTION_ANNOTATOR_DATA_ROOT`。

---

## 7. 模型（Models）

| 路径 | 内容 |
|------|------|
| [models/README.md](models/README.md) | 权重索引入口 |
| [artifacts/model_weights/](artifacts/model_weights/) | YOLO 等根目录权重 |
| [pipeline/experiments/mainlines/tstaging_4class/baseline_registry.yaml](pipeline/experiments/mainlines/tstaging_4class/baseline_registry.yaml) | T 分期冻结 checkpoint |
| [external/](external/README.md) | nnU-Net 等第三方本地依赖（gitignore） |

---

## 其他（归档 / 临时）

| 路径 | 类别 |
|------|------|
| [archive/](archive/) | 历史数据快照、第三方、`.bak` 可在此登记后删除 |
| [artifacts/tmp/](artifacts/tmp/) | 原根 `tmp/`（可选迁入） |
| `*.bak_YYYYMMDD` | 迁移备份，验证后可删 |

---

## 验证

```bash
python scripts/verify_repo_paths.py
python scripts/build_asset_manifest.py
```
