# NEXT_STEPS_AUTORESEARCH — 完整下一步清单（按优先级）

> 状态：2026-06-04 撰写；**2026-08-10 人机协同收口汇总已并入 `pipeline/autoresearch/results/`**  
> 目标：① 超过 06-03 mainline (AUC 0.8572 ext / 0.8655 pro) ② 多 agent 协同 ③ 整理主线 ④ **可审计人机协同临床获益**  
> 当前 SOTA 数字：`docs/mainline/MAINLINE_FACTS_v2.md` + `docs/mainline/asset_freeze_decision_20260809.md`  
> **结果汇总 SSOT**：`pipeline/autoresearch/results/latest/RESULTS_SUMMARY.md`（重建：`python3 scripts/build_autoresearch_results_summary.py`）  
> 所有仓内已存在资产（无需新建）：`pipeline/agent/` 下 11 tool + 7 memory module + analyze_case.py 2798 行

---

## ✅ 2026-08-10 已汇总进 autoresearch results（不要重复当“未做”）

| 项 | 状态 | 汇总值 |
|----|------|--------|
| Model foundation | reportable | acc_boost2 final；Phase 0 pred-ROI ~0.471 分表 |
| Agent 20+20 offline | foundation_only | internal 0.70 / external 0.50 |
| Offline v150 AI | sensitivity_only | BM 0.66 / T 0.57 |
| Round1 no-AI 医生基线 | reportable | primary 14：T 0.4436 / BM 0.5014 |
| Round2 freeze + exports + SAP | scaffold | `prepared_not_run`；gate blocked |
| Clinical AI-assisted uplift | **blocked** | completed_rows=0；expertise registered=0 |

入口：

```text
pipeline/autoresearch/results/latest/RESULTS_SUMMARY.md
pipeline/autoresearch/results/latest/RESULTS_SUMMARY.json
pipeline/autoresearch/results/trial_ledger.csv
```

---

## 🔴 P0 — 立即可做（1-3 天，可能直接出论文级新结果）

### P0.1 把 DINOv3 region token 真接到 06-03 mainline 决策层
- **为什么**：仓里 `pipeline/agent/memory/adapter_dino_retriever.py` 已有 DINOv3 + NCA 降维 + faiss 索引；`analyze_case.py` 已经在用；但 mainline 06-03 分类器**没有用** DINOv3 拼接向量作 late fusion
- **要做**：
  1. 写 `pipeline/mainline/late_fusion/dinov3_late_fusion.py`：把 `adapter_dino_retriever.py` 的 128-d NCA vector 与 mainline ConvNeXt logits concat，过一个 2 层 MLP
  2. 训一个 `tstaging_4class_mainline_dinov3late_202606XX_HHMMSS`（warm start from 06-03 mainline）
  3. 在 test_prospective (n=1659) + test_external (n=2458) 重评
- **预期**：patient-level acc 从 0.72 → 0.76-0.78（之前 session 估计）
- **风险**：DINOv3 在 06-03 1659 screened split 上**没有训过** retriever，需要先 retrain NCA on 1659 train 集
- **SSOT**：新 run 必须**沿用 06-03 mainline 的同一 4-split csv**——`pipeline/data/tstaging_4class_screened_eval_20260531/`
- **完成定义**：test_external macro AUC ≥ 0.866 且 prospective ≥ 0.870（**超过 06-03**）

### P0.2 围墙 (wall) evidence 嵌入 mainline
- **为什么**：仓里有 `wall_evidence_tool.py` + 4 个 wall 跑过的 run（最好的是 `wall_evidence_residual_fusion_preserve_cross_attention` 0.73 pro / 0.70 ext）。这些 run **没有** 用 06-03 screened 1659 split，**是过拟合老 253 split 的**
- **要做**：
  1. 把 wall_evidence 输出的 "border_delta_tokens" 作为第 5 通道（mask 之外）拼进 global branch
  2. 或作为 cross-attention 额外 key
  3. 训一个 `tstaging_4class_mainline_wallaux_202606XX_HHMMSS`
- **预期**：T2/T3 boundary recall +0.05-0.10（wall 是 T2 vs T3 的关键证据）
- **完成定义**：T2/T3 boundary subset T2 recall ≥ 0.93（当前 0.90）

### P0.3 Lumen detection 作为前置 quality gate
- **为什么**：仓里 `lumen_detection_tool.py` 已实现，但 mainline 流程**没**把"lumen 没找到"的帧过滤掉
- **要做**：
  1. 在 mainline 推理前加 lumen gate：lumen_conf < 0.5 的帧标 `low_quality`，不参与 patient-level voting
  2. 对比 with-gate vs without-gate 的 patient-level 数字
- **预期**：patient-level b-acc +0.02-0.04（去掉 5-10% 噪声帧）
- **风险**：gate 阈值需在 val 集上调，不能在 test 上调

---

## 🟢 P0-H — 人机协同 Round2（临床主结论解锁，与模型 P0 并行）

- **为什么**：论文主叙事已收口为同医生同病例 no-AI → AI-assisted；模型数字不能替代医生最终获益
- **要做**：
  1. 完成 `reader_expertise_registry_20260810.csv` 揭盲前登记
  2. 按 freeze 启动 research Round2
  3. 重新导出配对表并通过 `validate_reader_round2_gate.py`
  4. `python3 scripts/build_autoresearch_results_summary.py` 刷新 `clinical_claims_allowed=true`
- **完成定义**：gate 通过 + uplift SUMMARY 中 Round2 uplift 不再是 `blocked_until_round2_data`
- **禁止**：用 offline v150 AI 或 Agent 20+20 填补 Results-C

---

## 🟠 P1 — 重要（3-7 天，扩展主线叙事）

### P1.1 autoresearch 主循环（**真正缺的训练式 loop**）
- **当前**：仓里 `analyze_case.py` 是**单 case agent**——给一个 patient，输出报告。它不选 module、不调参、不比较
- **已补（2026-08-10）**：`pipeline/autoresearch/results/` 可汇总模型基础 + Round1/Round2 门控证据；这是**结果账本**，不是训练 proposer 主循环
- **要做**（新建 `pipeline/autoresearch/main_loop.py`）：
  ```
  for trial in range(N):
      1. proposer agent: 从 module bank (4-12 个可选 module) 采样一种组合 + 超参
      2. trainer: 跑 1 个 epoch quick-train from mainline 06-03 warm start
      3. evaluator: 在 val (held-out 200 patients) 上算 macro AUC
      4. memory: 把 (config, val_AUC) 写进 case_memory + faiss index
      5. reflector agent: 分析最近 10 次 trial 失败模式，emit 新 module / 调 lr / 加 cost
      6. record best_so_far; continue
  ```
- **依赖**：
  - `pipeline/agent/memory/case_memory.py` 已能用 → 用于存 trial history
  - `pipeline/agent/memory/faiss_index.py` 已能用 → 用于按 config embedding 找相似历史 trial
  - `pipeline/agent/memory/adapter_dino_retriever.py` 已能用 → 用于 trial embedding
- **风险**：autoresearch 容易跑飞，需要**严格 budget**（max 30 trial，max 2 epoch/trial）
- **不破坏主结果**：autoresearch 跑在 `warmstart_from=06-03_mainline`，不动原始 06-03 run

### P1.2 4-6 个 module 的 late fusion
- **候选 module bank**（每个都已经在仓里有 prototype）：
  - M1: ConvNeXt logits（mainline 06-03）— 必须
  - M2: DINOv3 NCA vector — 仓里有
  - M3: wall_evidence border_delta — 仓里有
  - M4: lumen detection conf — 仓里有
  - M5: clinical-22 raw — 已在 mainline
  - M6: lesion mask Dice — 仓里有 segdino
  - M7: ROI offset distance — 需要新建
- **要做**：
  1. 写 `pipeline/mainline/late_fusion/module_bank.py`：每个 module 暴露 `embed(case) -> vector`
  2. 写 `pipeline/mainline/late_fusion/learned_fusion.py`：在 val 上学 6 个 module 的 attention 权重
  3. 写 `pipeline/mainline/late_fusion/run_ablation.py`：扫每种 module 子集，记录 AUC
- **预期**：开 ablation 就能在 paper 里写"module bank ablations"，LDH reviewer 会喜欢

### P1.3 clinical 22 维升级到 30+ 维
- **为什么**：仓里 22 维是固定 schema，可能漏了"lumen 横截面积""wall thickness""tumor 增强模式"等连续特征
- **要做**：
  1. 从 `analyze_case.py` 的 `morphology_tool` + `wall_evidence_tool` 输出抽 8-12 个**新连续特征**
  2. 加进 `pipeline/clinical/feature_spec_v2.yaml`
  3. 训 mainline + extra-clin-8 验证 lift

---

## 🟡 P2 — 整理主线（与提升并行）

### P2.1 docs/mainline/EXPERIMENT_INDEX_v2.md（**今天必须做**）
- 把 30+ 个 run 按 4 维分类：
  - 维度 1: architecture (mask4ch / dino_fusion / wall_evidence / region_contrastive / boxguided / acc_boost2)
  - 维度 2: train split (old_253 / screened_1659)
  - 维度 3: held-out cohort (test_prospective_253 / test_prospective_1659 / test_external_2966)
  - 维度 4: 是否带 multitask / ordinal / boundary_cost / DINOv3 / wall_aux
- 每一格：1 行 = 1 个 run 目录 + 1 行 metric

### P2.2 docs/mainline/INTEGRATION_ROADMAP.md
- 画一张"主线演进时间线"（2026-02 → 2026-06）—— 哪些是 L1 frozen，哪些是 L2 explore

### P2.3 docs/mainline/RESULT_CLEANUP.md
- 对 11 个 wall/dinov3 run（已扫的真实数字），明确**保留 / 升级 / 归档**决策
- 已扫结果摘要：
  - `tstaging_4class_anatomic_region_contrastive_meddinov3_outer_lumen_clinical22_full_20260504`: ext 0.6467 → 归档
  - `tstaging_4class_gastric_wall_evidence_net_border_delta_tokens_from_prospective_recovery_best_20260506`: ext 0.6679 → 归档
  - `tstaging_4class_gastric_wall_evidence_residual_fusion_longrun_20260516`: ext 0.7248 → 归档
  - `tstaging_4class_gastric_wall_evidence_residual_fusion_preserve_cross_attention_20260510`: ext 0.6997 → 归档
  - `tstaging_4class_boxguided_wall_region_contrastive_clinical22_deep_auc85_all_mechanisms_from_balanced_best_20260506`: ext 0.7013 → 归档
  - `tstaging_4class_boxguided_wall_region_contrastive_clinical22_prospective_auc_retention_external_recovery_from_refinement_best_20260506`: pro 0.7908 ext 0.5682 → 归档（**过拟合 prospective**）
  - `tstaging_4class_boxguided_wall_region_contrastive_clinical22_full_20260505`: 待查
  - `tstaging_4class_auc85_gt_wall_ordinal_boundary_teacher_clinical22_20260505`: 待查
  - `tstaging_4class_dual_v2_mask4ch_wallaux_clinical22_full_20260426`: 待查
  - `tstaging_4class_anatomic_region_contrastive_clinical22_border_20260428`: 待查
- **判断标准**：AUC < mainline - 0.05 → 归档；AUC 在 mainline ± 0.05 → 探索；AUC > mainline + 0.01 → 升级

### P2.4 把 06-03 mainline + P0/P1 结果一起组成 **L1 完整证据链**
- 写 `docs/mainline/MAINLINE_FACTS_v2.md` —— 包含 mainline + DINOv3 late fusion + wall evidence + lumen gate + multi-agent late fusion 5 个版本的对比

---

## 🟢 P3 — 投 LDH 之前必须做（不在这次主线提升里，但相关）

### P3.1 bootstrap 95% CI 脚本
- 给所有 mainline metric 加 95% CI（per-class recall、macro AUC、patient-level acc）
- 写在 `pipeline/mainline/eval/bootstrap_ci.py`，跑完结果并入 Table 2

### P3.2 Figure 1（external centers montage 投稿版）
- 已有 3 张 montage PNG，合并成 1 张投稿用
- 风格切换 B（白底 TNR）——LDH 正文 figure 一般是白底

### P3.3 Supp S6（50 例高置信错分 Grad-CAM panel）
- 数字已在 `docs/mainline/error_panel.md`；图待画

### P3.4 英文版 v2
- v1 中文已 22 KB；LDH 要英文 v2

---

## 📅 时间线

| Day | 任务 | 完成定义 |
|---|---|---|
| 今天 | P0.1 脚本骨架 + P2.1 实验索引 + P2.3 11 个 run 决策 | 脚本可跑、索引可读、决策落地 |
| +1 | P0.1 跑完 + P0.2 脚本骨架 + P2.2 时间线 | test_external AUC ≥ 0.866 |
| +2 | P0.2 跑完 + P0.3 脚本骨架 | T2/T3 boundary recall ≥ 0.93 |
| +3 | P0.3 跑完 + P1.1 autoresearch 骨架 | 5 module 都已接进 mainline |
| +4 | P1.1 autoresearch 第 1 轮 trial | 至少 1 个新组合 > mainline |
| +5 | P1.2 module bank ablations | ablation 矩阵完整 |
| +6 | P1.3 临床 30 维 + P2.4 写完整 MAINLINE_FACTS_v2 | 5 版本对比表 |
| +7 | P3.1 / P3.2 / P3.3 收尾 | paper-ready |

---

## ⚠️ 必须诚实承认的现状

1. **matplotlib / sklearn / numpy 在当前 Python 不可用**——所有图都得 stdlib SVG → ImageMagick
2. **autoresearch 框架需要新建**——仓里只有 single-case agent
3. **11 个 wall/dinov3 run 全部 < 06-03 mainline 数字**——所以"超过"是真的难，必须用 late fusion + 数据集筛选
4. **没有 DINOv3 在 1659 screened split 上训的 NCA**——必须先 retrain adapter，否则是 data leakage
5. **多 agent 协同的"主 agent + 辅助 agent"合同还没建**——`analyze_case.py` 现在是 single agent main loop，需要拆成 planner / executor / critic 三 agent

---

## 立即建议（今天下午）

1. **先做 P2.1（实验索引 v2）+ P2.3（11 个 run 决策）**—— 1-2 小时能出，不依赖 GPU
2. **同时 P0.1 写脚本骨架**—— 2-3 小时能出
3. **GPU 跑 P0.1 / P0.2 / P0.3 各 1 个 run** —— 12-24 小时
4. **明天看结果**，决定 P1 autoresearch 是不是值得做

---

**这个清单的 4 个姐妹文档**：
- `ABLATION_MATRIX.md` — 科学消融矩阵设计
- `MULTI_AGENT_CONTRACT.md` — 多 agent 协同合同
- `EXPERIMENT_INDEX_v2.md` — 干净版实验索引
- `RESULT_CLEANUP.md` — 11 个 run 的去留决策
