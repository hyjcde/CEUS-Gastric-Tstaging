# Gastric T-staging 论文支撑包

本目录由 `scripts/build_gastric_paper_assets.py` 生成，**单文件 ≤ 1MB**，便于 GitHub 同步与写稿引用。

## 目录

| 子目录 | 内容 |
|--------|------|
| `methods/` | 方法学主文档副本（架构、Agent、DINOv3、T2/T3 指标） |
| `metrics/` | 实验 `experiment_summary.json`、融合指标、checkpoint 推荐 |
| `figures/` | 论文用结果图（AUC、混淆矩阵、Grad-CAM 单病例/预览） |

## 主要模型结果（外部 test）

| 模型 | AUC | T2+T3→T4+ |
|------|-----|-----------|
| baseline mask4ch full | 0.733 | 28.0% |
| antioverstage v2 | 0.705 | 18.0% |
| **antioverstage v3（推荐）** | 0.698 | 18.6% |
| ensemble 30% baseline + 70% v3 | 0.723 | 19.3% |

详见 `metrics/CHECKPOINT_RECOMMENDATIONS_T2T3.md`。

## 复现对比

```bash
python pipeline/scripts/compare_t2t3_model_variants.py --split test_external
python scripts/build_gastric_paper_assets.py   # 重建本目录
```

## 完整文档

仓库内 `docs/mainline/` 含更完整的方法与图表索引；本包为**写 gastric paper 的轻量快照**。
