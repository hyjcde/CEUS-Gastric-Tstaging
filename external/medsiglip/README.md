# MedSigLIP 独立工作区

这里是从仓库主线复制出来的干净目录，专门用来从头想、改、训 MedSigLIP-448 GastricUS。  
实体在 `external/medsiglip/`。仓库根上的 `medsiglip/` 是指到这里的兼容链接。原仓库里的主线代码和数据没有并进来，两边互不影响。

把这个文件夹当成新的项目根。`constants.py` 的 `ROOT` 指向这里，不要设回上层仓库。仓库根通过 `MAIN_ROOT` 找到。

## 先读

1. [GastricUS实验方案.md](GastricUS实验方案.md) — 方案原文
2. [GastricUS实验方案_各节实现与结果.md](GastricUS实验方案_各节实现与结果.md) — 各节要求对照持有集数字
3. [GastricUS实验方案_第1节方法实现.md](GastricUS实验方案_第1节方法实现.md) — 第 1 节总路线的具体落地
4. [pipeline/medsiglip_gastricus/README.md](pipeline/medsiglip_gastricus/README.md) — 命令和默认超参
5. [pipeline/medsiglip_gastricus/PLAN_MAPPING.md](pipeline/medsiglip_gastricus/PLAN_MAPPING.md) — 方案逐条 vs 代码
6. [pipeline/medsiglip_gastricus/DATA_AUDIT.md](pipeline/medsiglip_gastricus/DATA_AUDIT.md) — 数据合同
7. [pipeline/medsiglip_gastricus/EXPERIMENT_RECORD.md](pipeline/medsiglip_gastricus/EXPERIMENT_RECORD.md) — 已跑过的数字
8. [docs/mainline/clinical_11_field_pack.md](docs/mainline/clinical_11_field_pack.md) — 临床 11 项

旧实验总账在 [pipeline/experiments/reports/gastricus_ledger/MASTER.md](pipeline/experiments/reports/gastricus_ledger/MASTER.md)。账本里混有 Dual ConvNeXt 行，那条线不在本文件夹。

## 目录

```text
medsiglip/
  GastricUS实验方案.md
  pipeline/medsiglip_gastricus/          训练包（改这里）
  scripts/run_medsiglip_gastricus.py     主入口
  dataset/task_datasets/.../v20260821/  干净四份 CSV
  dataset/internal|external/**/crop_ui  全图、mask、overlay
  dataset/internal|external/**/crop_roi 官方裁好的 ROI（images + roi_masks + overlays + annotations）
  google/medsiglip-448                   官方名入口（与下一行同一份权重）
  artifacts/model_weights/medsiglip-448 冻结 ViT，encode 实际读取这里（约 3.3G）
  pipeline/data/medsiglip448_...        已算好的 1152-d 缓存（约 2.2G）
  pipeline/experiments/reports/         新实验写到这里
```

复制清单：[COPY_MANIFEST.json](COPY_MANIFEST.json)。刷新拷贝：`python3 scripts/refresh_workspace_copy.py`（会覆盖本目录里已改过的代码，先备份）。  
打包代码和结果（含上级账本）：`python3 scripts/pack_gastricus_code_and_results.py`，默认 `~/Desktop/GastricUS_code_and_results_<date>/`。

## 开训

在本目录执行，不要在仓库根执行。

```bash
cd /data/research/gastric/GastricTstaging/medsiglip

# 默认头：读 20% 缓存，不再加载 ViT，不再读图
python3 scripts/run_medsiglip_gastricus.py train --device cuda:0

# TabPFN 临床头
python3 scripts/run_medsiglip_gastricus.py train --device cuda:0 --head tabpfn --tabpfn-device cpu

# 方案 4.x / 5.x / 6.x 完整网格（10 组，不覆盖旧报告）
python3 scripts/run_medsiglip_gastricus.py train --device cuda:0 --plan-sweep --tabpfn-device cpu

# 再试：15/25 ROI、混合 ROI、gate/pair、mean_u、mid 头
python3 scripts/run_medsiglip_gastricus.py train --device cuda:0 --retry-sweep --tabpfn-device cpu

# Phase 1 边界审计（读已有预测）
python3 scripts/run_medsiglip_gastricus.py phase1
python3 scripts/run_medsiglip_gastricus.py phase1 --phase1-seeds --device cuda:0 --tabpfn-device cpu
python3 scripts/run_medsiglip_gastricus.py aiv2 --device cuda:0 --tabpfn-device cpu

# 重编码（才会读图和 3.3G 权重）
python3 scripts/run_medsiglip_gastricus.py encode --device cuda:0

# T 分期 LoRA（完整脚本：多边形全图 + 现成 crop_roi，last-2 / r=8）
python3 scripts/train_tstaging_lora.py --device cuda:0
```

默认：`--fusion concat --pool gated --size xlarge --head mlp --lock acc --expand 0.20`。更深头：`--size deep`。  
新报告落在 `pipeline/experiments/reports/`，不会覆盖仓库主线那批旧 run。

## 数据合同

| 角色 | 文件 | 行 | 患者 |
|------|------|---:|-----:|
| 训练 | `dataset/task_datasets/t_staging/maincenter_retrospective_v20260821/splits/train.csv` | 6044 | 1062 |
| 验证 | `.../val.csv` | 733 | 128 |
| 前瞻（只评估） | `.../test_prospective.csv` | 1659 | 425 |
| 外部（只评估） | `.../test_external.csv` | 2458 | 485 |

Full 图是 freeze `crop_ui`。本工作区的 `crop_ui` 已与主线整树对齐（图、mask、overlay、标注），不再只留干净表用到的子集。训练、编码、20% 缓存仍只读上面四份 CSV，多出来的 freeze 帧在盘上但不进当前训练。默认编码仍按 `crop_ui/roi_masks` 现算 bbox 再外扩 20%，不用官方 `crop_roi` 当主输入。`crop_roi` 也已整树拷好。不要用 20260531 的 `t_staging/splits`，也不要用 Phase 0 的 `train_clinical.csv` 当训练集。

## 故意没拷

| 没拷 | 原因 | 原位置 |
|------|------|--------|
| 约 14G 旧 checkpoint / 预测 CSV | 从头想不必带着；含患者级输出 | `pipeline/experiments/reports/medsiglip_gastricus_*` |
| Dual ConvNeXt yaml 和 `scripts/run_gastricus_*.py` | 另一条线 | 仓库 `pipeline/configs/`、`scripts/` |
| `original/`、视频 | 本包不用 | `dataset/` |
| 过期缓存 `full_roi_expand20_v1` | 不要当主缓存 | 同上特征目录 |

## 和仓库主线的关系

- 这是副本。改这里的 `.py` 不会改 `pipeline/medsiglip_gastricus/`。
- 主线入口仍是仓库根的 `scripts/run_medsiglip_gastricus.py`。
- 大文件不进 Git。需要同步回主线时，只拷代码和文档，不要整树搬影像。
