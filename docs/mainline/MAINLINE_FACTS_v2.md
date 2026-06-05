# MAINLINE_FACTS_v2 — 主线证据 L1 入口（2026-06-04 升级）

> 状态：v2 (2026-06-04 14:00 CST)，所有数字直接从 `test_results.json` / `experiment_index_v2.csv` re-read 后写入，未做外推。
> 配套：`docs/LAYERS.md`（4 层定义）· `docs/paper_governance/PAPER_INDEX.md`（SSOT 入口）· `docs/mainline/experiment_index_v2.csv`（211 行 L1/L2/L3 索引）
> 数据 contract 未变（见 §1）。v2 相比 v1 主要差异：①加入「6 版本对比表」（§6）②明确标注 P0.1/P0.2/P0.3 三条探索线状态（§7–§9）③诚实列出 per-center 短板（§5）。

---

## 1. 数据 contract（与 v1 一致，未变）

| 名称 | 来源 | n_patients | n_frames | 用途 |
|---|---|---|---|---|
| Internal prospective 2025 | `pipeline/data/tstaging_4class_screened_eval_20260531` (int/prospective split) | 425 | 1659 | 内部前瞻 test set |
| External multi-center (screened 2966) | `pipeline/data/tstaging_4class_screened_latest_external_2966_20260529` | 485 | 2458 | 外部多中心冻结 test set |
| Train + val | 同上 (screened 2026-05-31) | — | — | 训练、验证、模型选择 |

- **4-split**：train / val / prospective / external，**patient-level** 互斥
- **不动**：`SPLIT_POINTERS.md`、外部 9 中心 cohort 列表

## 2. 主线主结果（final model freeze 2026-06-03）

**Run**: `tstaging_4class_acc_boost2_multitask_screened_eval_20260603_162955`
**架构**: dual ConvNeXt + 22 维临床特征 + ordinal + multitask + boundary cost
**来源 SSOT**:
- `eval/test_prospective/test_results.json`
- `eval/latest_screened_external_reeval/test_external/test_results.json`

### Test external (latest screened 2966, 9 sites, n_frames=2458)

| Metric | Value |
|---|---|
| macro AUC | **0.8572** |
| Accuracy | 0.6880 |
| balanced accuracy | 0.6454 |
| macro F1 | 0.6522 |
| T1 recall (c0) | 0.6334 |
| T2 recall (c1) | **0.4922** |
| T3 recall (c2) | 0.6940 |
| T4+ recall (c3) | 0.7621 |
| per-class AUC | T1 0.8896 / T2 0.8173 / T3 0.8425 / T4 0.8794 |
| Patient-level acc | 0.6289 (n=485) |
| Patient-level b-acc | 0.5697 |
| T2→T3 over-stage rate | 0.1914 |

### Test prospective (internal, screened, n_frames=1659, n_patients=425)

| Metric | Value |
|---|---|
| macro AUC | **0.8655** |
| Frame accuracy | 0.7215 |
| balanced accuracy | 0.6886 |
| macro F1 | 0.6695 |
| T1 recall (c0) | 0.7981 |
| T2 recall (c1) | 0.5481 |
| T3 recall (c2) | 0.6720 |
| T4+ recall (c3) | 0.7362 |
| per-class AUC | T1 0.9323 / T2 0.7805 / T3 0.8502 / T4 0.8988 |
| Patient-level acc | **0.7200** (n=425) |
| Patient-level b-acc | 0.6804 |
| T2/T3 over-stage rate | 0.1608 |

> 已 cross-check 6 个数字 vs v1 MAINLINE_FACTS.md：全部一致。rounding 走 4 位有效。

## 3. Baseline（frozen primary 2026-04-23）

**Run**: `tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301`
**架构**: dual ConvNeXt + 22 维临床特征（无 ordinal / multitask / boundary cost）
**注意**: 它的 test_prospective (n=253) **不是 06-03 mainline 的 test_prospective (n=1659)**——0 image_path overlap

| Metric | test_external (n=2430) | test_prospective (n=253) |
|---|---|---|
| macro AUC | 0.7326 | 0.7455 |
| Accuracy | 0.5078 | 0.5336 |
| balanced accuracy | 0.4424 | 0.4825 |
| T2 recall (4-class) | 0.2038 (c1 recall) | 0.0938 (3/32) |
| T2→T3 off-stage | 0.3277 (latest_dataset 20260529) | 0.2812 (9/32) |

## 4. 主线相对基线的提升（跨 split 谨慎归因）

| Metric | Baseline 04-23 | Mainline 06-03 | Delta | 备注 |
|---|---|---|---|---|
| test_external macro AUC | 0.7326 | **0.8572** | +0.1246 | 同 cohort（多中心） |
| test_prospective macro AUC | 0.7455 (n=253) | **0.8655** (n=1659) | +0.1200 | **不同 cohort**：0 image_path overlap，delta 含 screening contract + cohort size 变化 |
| test_prospective T2 recall (4-class) | 0.094 | 0.548 | +0.454 | 同 caveat（cohort 改变） |
| test_prospective T2→T3 over-stage | 0.281 (9/32) | 0.161 (166/1031) | -0.120 | 04-23 T2 总数极小（n=32），稳定性差 |

> **caveat**: 不能把 +0.1246 / +0.1200 直接归因于「模型家族升级」。test_external 两个 run 共享外部 cohort；test_prospective 两个 run 处于不同 prospective split。建议论文里只把 test_external delta 当 primary improvement，test_prospective delta 当 secondary / screening impact。

## 5. T2/T3 边界专项

详见 `t2_t3_boundary_metrics_zh.md` + `docs/agent_memory/figures/figure3_t2t3_boundary.png`

| Run | held-out cohort | T2 recall (4-class) | T2/T3 boundary subset T2 recall |
|---|---|---|---|
| 04-23 baseline | prospective 253 | 0.0938 (3/32) | 0.25 (3/12) |
| 06-03 mainline | prospective 1659 | 0.5481 | 0.90 (57/63) |

**caveat（保持 v1 原文，未变）**: 两个 held-out cohort 不是同一份 prospective split（0 image_path overlap），所以 T2 recall 提升是「model family 改变带来的提升」+「screening contract + cohort size 改变带来的影响」二者之和，不能完全归因。

## 6. 6 版本对比表（从 experiment_index_v2.csv 读出，2026-06-04）

> 选取原则：6 个有代表性的 L1/L2/L3 节点，覆盖「基线 → 临床特征 → lumen/mt → mask4ch → 06-02 → 06-03 mainline」六个时间切片。所有数字从 `docs/mainline/experiment_index_v2.csv` 读出，源 JSON 路径见末尾备注。

| # | Run (short) | Decision | test_prospective AUC | test_external AUC | pro T2 recall | ext T2 recall |
|---|---|---|---|---|---|---|
| 1 | doctor-ROI v2 (early, 2026-03-19) | L3 | 0.6225 (n=253) | 0.6312 (n=2430) | 0.1250 | 0.4787 |
| 2 | clinical22 only (2026-04-22) | L2 | 0.6968 (n=253) | 0.7276 (n=2430) | 0.0938 | 0.4408 |
| 3 | lumen+lesion features (2026-04-16) | L3 | 0.5968 (n=253) | 0.6142 (n=2430) | 1.0000 | 0.9242 |
| 4 | histeq+screened (2026-05-31) | L2 | 0.6779 (n=1659) | 0.6246 (n=2458) | 0.0000 | 0.0972 |
| 5 | acc-boost 06-02 (2026-06-02) | L1 | 0.8616 (n=1659) | 0.8566 (n=2458) | 0.5288 | 0.4953 |
| 6 | mainline 06-03 | **L1** | **0.8655** (n=1659) | **0.8572** (n=2458) | **0.5481** | **0.4922** |

**关键观察（re-read 数据后写出）**:
- **#1 vs #2**: 加入 clinical22 后 AUC 提升 ~0.07，confirm 临床先验稳定有效
- **#2 vs #4**: 把 histeq+screened 接上后，pro 上 AUC 反而下降到 0.6779（n=1659 cohort 改变 + screening 协议引入的 domain shift），说明 histeq 单独不够
- **#3 lumen 残差特征**: 在小 n=253 上 T2 recall=1.0（极小样本虚高），但 AUC 0.5968 说明该特征对其他类严重伤害，**不入选主线**
- **#4 → #5**: 跨越 06-02 之前的 1 天完成从 0.6779 → 0.8616 的 +0.18 大幅跳升，对应 `tstaging_4class_dual_v2_histeq_screened_eval_20260531` → `tstaging_4class_acc_boost_multitask_screened_eval_20260602` 的家族升级（masked-4ch + acc-boost 训练策略 + multitask + boundary cost）
- **#5 → #6**: 在 #5 基础上 +0.0039 (pro) / +0.0006 (ext) 微改进，确认 acc-boost2 + boundary cost 的边际收益已饱和
- **#6 ext T2 recall 0.4922** 实际略低于 #5 0.4953（−0.0031），不是单调上升，说明 06-03 主要改进在边界/整体平衡上，T2 单点 recall 已基本稳定

> **诚实 caveat**: 表格中 #1–#3 的 pro split 仍是 n=253（pre-screening），#4–#6 是 n=1659（post-screening）。跨组不能直接对比。论文里建议把 #1–#3 视为「历史基线参照」，把 #4–#6 视为「06-03 mainline 家族谱系」。

源 JSON 路径（来自 v2 CSV 的 `run_name` 字段）：
- #1: `classification/dual_convnext/baseline_doctor_roi_v2_20260319_202106`
- #2: `classification/dual_convnext/tstaging_4class_dual_v2_clinical22_full_run1_20260422_212705`
- #3: `classification/dual_convnext/tstaging_4class_dual_v2_multitask_lumen_lesion_features_20260416_161710`
- #4: `classification/dual_convnext/tstaging_4class_dual_v2_histeq_screened_eval_20260531_121710`
- #5: `classification/dual_convnext/tstaging_4class_acc_boost_multitask_screened_eval_20260602_202847`
- #6: `classification/dual_convnext/tstaging_4class_acc_boost2_multitask_screened_eval_20260603_162955`

## 7. P0.1 — DINOv3 late fusion 状态（TBD / 未完成）

**任务依赖**: T_dinov3 (P0.1)。板上**未创建**该任务卡（grep 0 命中）；仓内**未找到** DINOv3 late-fusion 子目录或 patient-level JSON。

**仅有的相关 eval（不构成 late fusion）**:
- `contrastive/contrastive_dual_eva02/tstaging_4class_anatomic_region_contrastive_meddinov3_outer_lumen_clinical22_full_20260504_115833`
  - pro (n=232): AUC 0.6054 / acc 0.2328 / b_acc 0.2797 / T2 recall 0.0000
  - ext (n=2231): AUC 0.6467 / acc 0.3716 / b_acc 0.3757 / T2 recall 0.0894
- **Decision: L2, 不入选**。是 medDINOv3 + EVA02 的对比学习预训练，**不是 06-03 mainline 的 late fusion**。

**MAINLINE_FACTS_v2 在该 section 的处理**: 不写数字。下一版升级前应先建子任务 `P0.1-T1: DINOv3 late fusion 训练` 并产出 JSON。**截止 2026-06-04 14:00，本节保持「TBD - 未完成」标记**。

## 8. P0.2 — wall evidence 5ch 状态（脚本骨架就位 / 训练未跑）

**当前进度**:
- ✅ T1 (`t_d5a3ee78`): wall_5ch 5-文件脚本骨架就位 — `wall_5ch_input.py` / `train_wall_5ch.py` / `eval_wall_5ch.py` / `merge_wall_manifest.py` / `README.md`
- ✅ precompute 子任务 (`t_e01d97f0`): `pipeline/mainline/wallaux_5ch/precompute_wall_channel.py` + manifest merge + README 已 ship
- ✅ 训练 (`t_5fa7efdc`): `pipeline/mainline/wallaux_5ch/train_wallaux_5ch.py` + `wallaux_5ch_dataset.py` + `run_wallaux_5ch.py` shipped
- ✅ 60-epoch warm start (`t_78bdad73`): best epoch=41, val_acc=0.4655, train_size=9138
- ✅ eval (`t_0f4c8731` + `t_d91e8530`): VERDICT.json = **fail**; report at `docs/mainline/P0_2_WALLAUX_5CH_RESULTS.md`
- **数字** (re-read 2026-06-04 18:27):
  - test_prospective (n=1659): AUC 0.8719 / acc 0.7372 / b-acc 0.6703 / T2 recall 0.5000 / T2 boundary recall 0.1148 / overstage 0.309 / patient-level acc 0.7059
  - test_external (n=2458): AUC 0.8475 / acc 0.6859 / b-acc 0.6351 / T2 boundary recall 0.1684 / overstage 0.2226 / patient-level acc 0.6330
  - Δ vs 06-03: pro AUC **+0.0064** ✅, ext AUC **-0.0097** ❌, T2 boundary recall **-0.0397** ❌, overstage **+0.1482** ❌
  - **Verdict = FAIL**: pro AUC 过线 0.870（0.8719）但 T2 boundary recall 远未达 0.93（0.1148），且 overstage 翻倍
  - **失败模式**: 5th wall channel 帮网络"敢"向 T4+ 预测，c3 recall +0.08 但 T2/T3→T4+ overstage 翻倍，**方向错了**
  - **Next**: 走 fail 分支选项 A（改 5ch 来源为 breakthrough_area_ratio > 0.3 二值 mask 替代 SDF），由 `t_d91e8530` spawn 的 follow-up task 执行

**仅有的相关 eval（不构成 wall_5ch 训练后评估）**:
- `classification/dual_mask4ch/tstaging_4class_dual_v2_mask4ch_wallaux_clinical22_full_20260426_100201` (L2)
  - pro (n=234, pre-screening split): AUC 0.7228 / acc 0.4017 / b_acc 0.4292 / T2 recall 0.1290
  - ext (n=2298, pre-screening split): AUC 0.7248 / acc 0.4169 / b_acc 0.4188 / T2 recall 0.4511
- **Decision: L2, 不入选**。该 run 在 pre-screening split（pro 234 / ext 2298），与 06-03 mainline 的 screened split（pro 1659 / ext 2458）**不可对比**。同时未走 5ch 输入。

**MAINLINE_FACTS_v2 在该 section 的处理**: 不写 PASS。**当前已 FAIL**（2026-06-04）。完整数字与失败归因见 `docs/mainline/P0_2_WALLAUX_5CH_RESULTS.md`。PASS 条件 (T0 卡定义): T2 boundary recall ≥ 0.93 且 test_prospective AUC ≥ mainline + 0.005（0.8705）必须**同时**满足；当前 1C 行 pro AUC 达标但 T2 boundary recall 仅 0.1148，verdict = fail。ABLATION_MATRIX.md Ablation 1 表 1C 行 + 数字汇总表 1C 行已同步。

### 8.1 P0.2-FU-A 1D retry (binary breakthrough mask) — pending

**触发**: 1C fail 后，决策树 fail 分支选项 A（见 `P0_2_WALLAUX_5CH_RESULTS.md` §9）—把 5th channel 从连续 SDF 改成 `breakthrough_area_ratio > 0.3` 的**二值 mask**。理由：1C 的 SDF 引入"壁深度连续"误导，c3 logit 被梯度拉高，导致 T2/T3→T4+ overstage 翻倍 (0.161→0.309)。二值 mask 是单调的，要么 breakthrough 要么不，**网络无法内插"一点点突破"**。

**当前进度** (re-read 2026-06-04 18:55):
- ✅ 子任务 `t_391cc50b` (P0.2-FU-A) — precompute 改造 + 文档同步
  - `pipeline/agent/tools/wall_evidence_tool.py`: 新增 `breakthrough_mask(lesion, sdf, threshold=0.3)`，返回 uint8 {0, 1}，per-image 二值（不是 per-pixel 阈值化）
  - `pipeline/mainline/wallaux_5ch/precompute_wall_channel.py`: `_compute_wall_channel` 改用 `breakthrough_mask`；新增 `--channel-mode {1d_breakthrough_binary, 1c_sdf}` flag，默认 1D；MANIFEST 增加 `channel_mode` 字段
  - 单元测试 5 条 (形状 / 全 breakthrough / 全 inside / 空 lesion / 形状不匹配 raise) 全过
  - `pipeline/mainline/wallaux_5ch/wallaux_5ch_dataset.py`: **不动**（uint8 PNG /255 自动支持 {0, 255} 二值）
  - `train_wallaux_5ch.py` / `wallaux5ch_warm_start`: **不动**（`global_in_channels = 5` 不变，`wall_init_strategy = "rgb_mean"` 不变）
  - `config_p02_5ch.json`: **不动**（除 5ch signal source 注释外 — 这里是只改 precompute 层，训练 config 复用 1C 的；后续 1D 训练 task 决定是否另起新 config）
  - ABLATION_MATRIX.md: Ablation 1 表 + 数字汇总表各加一行 1D，全部 TBD
  - README.md: 加 1D vs 1C 差异段落
- ⏸ 60-epoch 训练 (T-FU-A2 follow-up) — **不在本卡**，需要 GPU
- ⏸ eval + 写入 1D 数字 — 跟随 T-FU-A2

**1D 数字**: TBD（等 T-FU-A2 60-epoch 训练完成 + eval）。
- 预期通过条件: pro AUC ≥ 0.8705 且 T2 boundary recall ≥ 0.93（与 1C PASS 条件同）
- 失败兜底: 若 1D 也 fail → 进 fail 分支选项 B (改 warm-start 策略) 或选项 C (放弃 P0.2 整条 A 路径, 跳到 P0.1 DINOv3 late fusion)

**已知风险** (precompute smoke test 2026-06-04 18:44 发现):
- 当 `_build_lumen_bbox` 走到 `center_30pct` fallback (整图中心 30% = ~312×225 px on 1037×748) 时，lumen bbox 经常**完全包住** lesion → lesion 像素 sdf<0 → breakthrough_ratio=0 → 1D mask 全 0。1C (连续 SDF) 不受影响（仍有非零距离值），1D 把信号退化成 0-bit。
- 解决路径不在本 precompute 卡范围内 (body 写明只改 5ch 编码一行/一段)。T-FU-A2 训练后若发现 1D 等价 5ch≈0 通道,应回到 `_build_lumen_bbox` 改 fallback (例如让 `center_30pct` 强制跟 lesion 中心 30% 对齐) 或回到 1C warm-start 策略。
- 单元测试 5 条 (synthetic lesion + lumen) 全过,确认 `breakthrough_mask` 函数本身无 bug;问题是 precompute 的**输入** lumen bbox 链对 1D 不友好。

**SSOT**:
- 新函数: `pipeline/agent/tools/wall_evidence_tool.py::breakthrough_mask`
- 改动: `pipeline/mainline/wallaux_5ch/precompute_wall_channel.py` (channel_mode 参数)
- 矩阵同步: `docs/agent_memory/plan/ABLATION_MATRIX.md` (Ablation 1 + 数字汇总表)
- 本节同步: `docs/mainline/MAINLINE_FACTS_v2.md` (§8.1)

**Trainer verify 闭环 (2026-06-05, no-GPU, no-training)**:

跑 `python -m pipeline.mainline.wallaux_5ch.train_wallaux_5ch --verify` 验证 5ch 数据接入 + model build + warm-start conv1 + forward 全链路。`verify_only` 用的是 dataset 真实 `__getitem__` 输出,**没有**走任何 mock 路径。

- ✅ 修了一个 latent key bug: 原 `verify_only` 假设 sample key 是 `'global'` / `'local'` / `'clinical'`,但 `DualInputDataset.__getitem__` (line 1147-1155) 实际返回 `global_image` / `local_image` / `label`,`clinical` 是条件返回。原 verify 从未跑过所以没暴露 —— `eval_wallaux_5ch.py:113-118` 走的是对的 key (它跑过 end-to-end)。`train_wallaux_5ch.py:243-299` 已修正。
- ✅ 修了一个 forward kwarg 不匹配: 原 `model(global_x=, local_x=, clinical=)` 用的不是 model 的 kwarg 签名。`eval_wallaux_5ch.py` 用的 `model(global_image=, local_image=, clinical=)` 是 end-to-end 验证过的正确签名,verify 已同步。
- ✅ 闭环实际数字 (CPU, batch=1):
  - `sample.global_image.shape = (5, 384, 384)` — 5ch 拼成功 (1D 0/255 PNG 与 1C 0..255 PNG 走同一 dataset 路径)
  - `sample.local_image.shape  = (3, 224, 224)` — ROI 分支不变
  - `sample.clinical.shape    = (22,)`     — 22 维临床向量
  - `model params = 142,171,783` (5ch 多了 (128, 1, 4, 4) = 2048 参数,占比 ~0.001%)
  - `logits.shape = (1, 4)` — 5ch input → 4-class output
  - `warm_start`: parent `[128, 4, 4, 4]` → new `[128, 5, 4, 4]`, 5th 通道 = `parent[:, :3, :, :].mean(dim=1, keepdim=True)` (= 0 贡献, gradient-learnable) ✓

也就是说:**P0.2→1B→1C 验证链从 precompute → dataset → model build → warm-start → forward 已经全部走通;唯一缺的是 60-epoch 训练本体 (T-FU-A2) 跟随之的 eval 数字**。后者卡 GPU。

**§8.1 SSOT 追加**:
- Verify 脚本: `pipeline/mainline/wallaux_5ch/train_wallaux_5ch.py::verify_only` (no-GPU, no-training)
- Verify 命令: `python -m pipeline.mainline.wallaux_5ch.train_wallaux_5ch --config pipeline/mainline/wallaux_5ch/config_p02_5ch.json --verify`
- 训练 key 合同 (SSOT): dataset 返回 `global_image`/`local_image`/`label`/`clinical`(可选);model forward 用 `global_image=`/`local_image=`/`clinical=` kwarg
- README 新增 "Trainer integration (T-FU-A2)" 段 (`pipeline/mainline/wallaux_5ch/README.md`)
- 已知未变项: 1D 数字仍 TBD (`ABLATION_MATRIX.md` 1D 行 + 数字汇总表 1D 行),等 T-FU-A2 GPU 训后回填

## 9. P0.3 — lumen gate 状态（仅有弱 pre-screening 试跑，未入选）

**当前进度**:
- 板上**未创建** P0.3 任务卡
- 仓内仅有 pre-screening split 上的弱 run（见下）

**仅有的相关 eval**:
- `classification/dual_convnext/tstaging_4class_dual_v2_multitask_lumen_lesion_features_20260416_161710` (L3)
  - pro (n=253): AUC 0.5968 / acc 0.2530 / b_acc 0.3488 / T2 recall 1.0000（n_T2 极小，统计不稳）
  - ext (n=2430): AUC 0.6142 / acc 0.1634 / b_acc 0.2917 / T2 recall 0.9242
- **Decision: L3, 不入选**。在 4-class 总体 AUC 上远低于 06-03 mainline (0.8572)，T2 recall 虚高是 n_T2 太小（n=24 in pro 253）的统计现象，不是模型真的学到了。

**MAINLINE_FACTS_v2 在该 section 的处理**: 不写数字。在 06-04 阶段 lumen gate 暂无 evidence。下一版升级前应先建子任务 `P0.3-T1: lumen gate (anatomy-aware attention) on screened 1659` 并产出 JSON。

## 10. 跨中心 per-source（test_external，保持 v1 原文 + 补充 n_frames 来源）

来源: `06-03 mainline/eval/latest_screened_external_reeval/test_external/test_results.json` 的 `per_source` 字段

| Center | n_frames | acc | b_acc |
|---|---|---|---|
| ext/putian | 1390 | 0.7137 | 0.7060 |
| ext/putian2 | 25 | 0.5600 | 0.4438 |
| ext/sanming | 19 | 0.7368 | 0.4583 |
| ext/zhongliu | 313 | 0.8978 | 0.4100 |
| ext/中核五〇四医院 | 216 | 0.3426 | 0.3602 |
| ext/佛山市第一人民医院 | 67 | 0.3433 | 0.2889 |
| ext/北京友谊医院 | 124 | 0.3790 | 0.2633 |
| ext/福建省德化县医院 | 88 | 0.4545 | 0.2772 |
| ext/福建省立医院 | 216 | 0.9537 | 0.9841 |

> 总 n_frames 校验: 1390+25+19+313+216+67+124+88+216 = 2458 ✅（与 SSOT 2458 一致）

**诚实读法（保持 v1）**:
- 头部 center（putian / zhongliu / 福建省立医院）acc > 0.7，符合预期
- 中部 center（北京友谊、佛山一院、中核五〇四、德化）b-acc 严重下降（< 0.4），说明这些 center 的图像分布 / 标注分布与训练集差异显著
- **必须在论文 Discussion 中诚实承认**，不能只挑好的报

## 11. 已通过的 L1 单元（与 v1 一致）

- mask4ch 输入：✅ 06-03 mainline 包含
- clinical-22：✅ 06-03 mainline 包含
- ordinal + multitask：✅ 06-03 mainline 包含
- boundary cost：✅ 06-03 mainline 包含

## 12. 未确认 / 探索中（v2 升级）

- **DINOv3 late fusion (§7)**: TBD - 任务未创建，patient-level JSON 不存在
- **wall evidence 5ch (§8)**: **FAIL 2026-06-04** — pro AUC 达标 0.8719，但 T2 boundary recall 退化到 0.1148（远未达 0.93），overstage 翻倍。详见 `docs/mainline/P0_2_WALLAUX_5CH_RESULTS.md`
- **lumen gate (§9)**: TBD - 任务未创建，仅有 pre-screening L3 弱 run
- **Multiframe ConvNeXt**: 06-01 试跑 AUC 0.6359（远低于单帧 mainline 0.8655），**放弃**（保持 v1）
- **Contrastive region-aware warmstart (medDINOv3)**: 06-01 试跑 AUC 0.7074（弱），**不入选**（保持 v1）

## 13. 与 v1 的差异小结（便于 review）

| 维度 | v1 (2026-06-04 08:30) | v2 (本版) |
|---|---|---|
| 6 版本对比表 | 缺失 | 已在 §6 加入，从 v2 CSV 读出 |
| P0.1 DINOv3 | 仅一句「需要从 late fusion 子目录确认」 | §7 明确 TBD + 解释为何现有 run 不构成 late fusion |
| P0.2 wall_5ch | 未提及 | §8 明确脚本骨架就位 / 训练 blocked / PASS 条件未触发 |
| P0.3 lumen gate | 未提及 | §9 明确仅有 L3 弱 run，n_T2 太小导致 T2 recall 虚高 |
| 数据来源 | 单 run JSON | 同时引用 v2 CSV（211 行索引）+ 单 run JSON |
| 数字 rounding | 3 位 | 4 位（与 JSON 精度对齐） |
| per_source 总和校验 | 缺 | 已在 §10 给出 2458 校验和 |

---

**Provenance（re-read 确认清单）**:
- ✅ 06-03 mainline test_prospective 数字来自 `…/20260603_162955/eval/test_prospective/test_results.json`（re-read 2026-06-04 14:00）
- ✅ 06-03 mainline test_external 数字来自 `…/20260603_162955/eval/latest_screened_external_reeval/test_external/test_results.json`（re-read 2026-06-04 14:00）
- ✅ 04-23 baseline test_prospective 数字来自 `…/20260423_092301/eval/test_prospective/test_results.json`（re-read 2026-06-04 14:00）
- ✅ 04-23 baseline test_external 数字来自 `…/20260423_092301/eval/test_external/test_results.json`（re-read 2026-06-04 14:00）
- ✅ 6 版本对比表 6 行数字来自 `docs/mainline/experiment_index_v2.csv`（re-read 2026-06-04 14:00），CSV 由 T2 (t_292c7669) ship
- ⏸ P0.1/P0.3 数字：保持 TBD，不写任何数字
- ✅ P0.2 wallaux_5ch 数字：来自 `…/20260604_161258/eval/VERDICT.json` + `COMPARISON_VS_06_03.json` + `_06_03_baseline_recomputed.json` + `test_prospective_t4/test_results.json` + `test_external/test_results.json`（re-read 2026-06-04 18:27，由 T4 子任务 t_0f4c8731 写入）
