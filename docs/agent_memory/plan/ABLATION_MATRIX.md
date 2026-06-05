# ABLATION_MATRIX — 科学消融矩阵设计

> 状态：2026-06-04 撰写
> 目标：把"超过 06-03 mainline (AUC 0.8572/0.8655)" 这件事做成 LDH 投稿级消融
> 原则：每个消融单元**单变量**；每行数字**来自真实 run 目录**

---

## 主线 (06-03 acc_boost2) 已有 vs 待做

| 维度 | 06-03 mainline | 待加 |
|---|---|---|
| Input global | full image + predicted lesion mask (4ch) | + wall_evidence border_delta (5ch) |
| Input local | doctor ROI | + lumen-aware ROI |
| Clinical | 22 维 late-fusion | + morphology 8 维 (29 维) |
| Loss | CE + ordinal + multitask + boundary cost | + DINOv3 contrastive aux loss |
| Backbone | ConvNeXt dual | + DINOv3 ViT-B/16 region token (late fusion) |
| Quality gate | 无 | + lumen_detection confidence gate |
| Multi-agent | 无 | + planner/executor/critic late fusion |

---

## 6 大消融单元（每个是 1 个 run）

### Ablation 1 — Input channel 维度
| Run | 4ch mask | 5ch wall | n_test_pro | AUC | Δ |
|---|---|---|---|---|---|
| 1A baseline (no mask) | × | × | 1659 | ? | ref |
| 1B mainline 06-03 | ✓ | × | 1659 | 0.8655 | ref |
| 1C +wall_evidence 5ch (SDF) | ✓ | ✓ | 1659 | **0.8719** | **+0.0064**（达标 AUC），但 T2 boundary recall 0.1148 ❌（目标 0.93），overstage +0.148，**FAIL** |
| 1D +wall_breakthrough_binary 5ch (P0.2 retry) | ✓ | ✓ | 1659 | TBD | TBD — pending 60-epoch training (T-FU-A2 follow-up). 骨架 (`train_wallaux_5ch.py::verify_only`) 已 no-GPU 端到端跑通 (2026-06-05);Dataset / model build / warm-start conv1 / forward 全部 ✓。见 `MAINLINE_FACTS_v2.md §8.1 Trainer verify 闭环`。 |

- 数据源：06-03 mainline 已有；wall_evidence 仓里有 token 提取
- 复用：`pipeline/agent/tools/wall_evidence_tool.py` 的 output
- 1D 与 1C 的差异：1D 的 5th channel = `breakthrough_area_ratio > 0.3` 的**二值 mask**（uint8 PNG 0/255），代替 1C 的连续 SDF（clip(sdf, 0, 32) / 32 * 255）。消除 SDF 引入的"壁深度连续"误导，让网络直接看到 breakthrough 区是否被 flag。precompute 默认 mode = `1d_breakthrough_binary`；用 `--channel-mode 1c_sdf` 仍可复跑 1C 数字。dataset 接口 100% 不变。

### Ablation 2 — DINOv3 late fusion 维度
| Run | DINOv3 NCA | wall | AUC | Δ |
|---|---|---|---|---|
| 2A mainline 06-03 | × | × | 0.8655 | ref |
| 2B +DINOv3 NCA only | ✓ | × | **目标 ≥ 0.870** | +0.005 |
| 2C +DINOv3 + wall | ✓ | ✓ | **目标 ≥ 0.875** | +0.010 |

- 数据源：`pipeline/agent/memory/adapter_dino_retriever.py` 已有，但需在 1659 train 上**重训 NCA**
- 关键：不重训 NCA = data leakage

### Ablation 3 — Lumen gate 维度
| Run | lumen gate | AUC | patient-level acc | Δ |
|---|---|---|---|---|
| 3A mainline 06-03 | × | 0.8655 | 0.72 | ref |
| 3B +lumen gate ≥ 0.5 | ✓ | ? | **目标 ≥ 0.75** | +0.03 |

- 数据源：`pipeline/agent/tools/lumen_detection_tool.py` 已有
- 阈值在 val 集上调，不在 test

### Ablation 4 — Clinical 维度 (22 → 30+)
| Run | 22 维 | 30 维 | AUC | Δ |
|---|---|---|---|---|
| 4A mainline 06-03 | ✓ | × | 0.8655 | ref |
| 4B +morphology 8 | ✓ | ✓ | **目标 ≥ 0.868** | +0.003 |

- 数据源：从 `morphology_tool` + `wall_evidence_tool` 抽 8 个连续特征

### Ablation 5 — Loss 维度
| Run | loss 组合 | AUC | Δ |
|---|---|---|---|
| 5A CE only | 0.7455 (老 baseline) | ref |
| 5B +ordinal | ? | +0.05 |
| 5C +multitask | ? | +0.03 |
| 5D +boundary cost | ? | +0.05 |
| 5E +DINOv3 contrastive aux | ? | **目标 +0.01** |

- 仓里 ablation_matrix.csv 已有 5A-5D 数字
- 5E 需要新建（把 DINOv3 patch feature 加到 aux loss）

### Ablation 6 — Multi-agent late fusion 维度
| Run | 1 agent | 6 agent (planner/executor/critic/retriever/visualizer/synthesizer) | AUC | Δ |
|---|---|---|---|---|
| 6A mainline 06-03 | ✓ | × | 0.8655 | ref |
| **6B multi-agent late fusion** | × | ✓ | **目标 ≥ 0.875** | +0.010 |

- 数据源：autoresearch 跑出 best config
- 6 module 各自的 vector 拼接，attention 权重在 val 上学

---

## 数字汇总表（投 LDH Table 3）

| Run | external AUC | pro AUC | T2 recall (boundary) | T3 recall (boundary) | patient-level pro acc |
|---|---|---|---|---|---|
| 1A (no mask) | TBD | TBD | TBD | TBD | TBD |
| 1B mainline 06-03 | **0.8572** | **0.8655** | 0.90 | 0.94 | 0.72 |
| 1C +wall (P0.2 wallaux_5ch) | 0.8475 | 0.8719 | 0.1148 (pro) / 0.1684 (ext) | TBD | 0.7059 |
| 1D +wall_breakthrough_binary (P0.2 retry) | TBD | TBD | TBD | TBD | TBD |
| 2B +DINOv3 | TBD | TBD | TBD | TBD | TBD |
| 2C +DINOv3+wall | TBD | TBD | TBD | TBD | TBD |
| 3B +lumen gate | TBD | TBD | TBD | TBD | TBD |
| 4B +30 维 | TBD | TBD | TBD | TBD | TBD |
| 5E +DINOv3 aux | TBD | TBD | TBD | TBD | TBD |
| 6B multi-agent | TBD | TBD | TBD | TBD | TBD |

> 期望最终：**1B + 2C + 3B + 4B + 6B** 联合 → test_external ≥ 0.880, test_prospective ≥ 0.885

---

## 实验设计原则

1. **单变量**：每行只动 1 个 module
2. **共享起点**：所有 ablation **从 06-03 mainline checkpoint warm start**
3. **共享 held-out**：所有 ablation 用**同一份** 1659 prospective + 2458 external
4. **共享 seed**：所有 ablation 用同一 random seed (20260503)
5. **真实数字**：每个 run 目录都有 `eval_summary.json` / `test_results.json`，**不靠记忆**
6. **bootstrap 95% CI**：每个数字报 CI（per-class recall + macro AUC）

---

## 投 LDH 时怎么写

- **Table 3**（正文）：本表的 1B / 2C / 3B / 4B / 6B 5 行
- **Supp S1**：完整 ablation 矩阵（所有 1A-6B 数字）
- **正文 §3.2**：4-6 个 module 各自贡献 0.005-0.015 AUC 的讨论
- **Discussion §4.4**：为什么 lumen gate 和 wall evidence 在 T2/T3 上作用最显著
