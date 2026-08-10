# 当前执行主线

> **文档版本**：2026-08-09 / 冻结决策 [`asset_freeze_decision_20260809.md`](asset_freeze_decision_20260809.md) / SAM3.1 流程 [`sam31_gastric_lora_training_and_evaluation.md`](sam31_gastric_lora_training_and_evaluation.md) / 数字 SSOT 见 [`MAINLINE_FACTS_v2.md`](MAINLINE_FACTS_v2.md) / 筛图与 ACC80 全链路见 [`screened_dino_full_pipeline_20260529.html`](screened_dino_full_pipeline_20260529.html) / **Phase 0 实现细节**见 [`phase0_acc_boost2_implementation_20260610.html`](phase0_acc_boost2_implementation_20260610.html) / **视频与图像模型现状（2026-06-30）**见 [`video_image_model_status_20260630_zh.md`](video_image_model_status_20260630_zh.md) / **静态到视频研究方案（2026-07-06）**见 [`static_to_cine_tstaging_research_plan_zh.md`](static_to_cine_tstaging_research_plan_zh.md)

## 文档定位

本文档定义 **现在到下一阶段** 默认做什么、不做什么。总逻辑与优先级以 [`gastric_tstaging_project_framework_zh.md`](gastric_tstaging_project_framework_zh.md) 为准。

**一句话**：在 **YOLO / 分割 / ConvNeXt T 分期 / DINO / SAM3.1** 等已有训练结果基础上，**深入理解并选型接入**，构建以 **T 分期为核心输出** 的术前充盈超声 **辅助诊断 Agent**；良恶性作为前置筛查/辅助验证手段进入流程，但最终主表仍以 T 分期为核心。

---

## 0A. 2026-08-09 执行快照（当前）

| 资产 | 冻结选择 | 状态 |
|------|----------|------|
| Agent final T | `tstage_acc_boost2_screened_20260603` | 保留；外部必须并列 held-out 399 |
| Phase 0 严格泛化 T | `tstage_acc_boost2_phase0_20260610` | 分表报告，不替换 Agent final |
| Agent segmentation_primary | UNet ConvNeXt fulldata | 保留 |
| SAM3.1 LoRA run2 | `sam31_gastric_lora_full_components_5epoch_run2` | 8768 已加载；Agent 批量未晋升 |
| Agent 20+20 验收 | `pipeline/experiments/agent_smoke_test/acceptance_clean_20260809/` | **passed, offline** |
| 冻结验证面板 | `pipeline/experiments/reports/gastric_us_agent_frozen_validation_clean_20260809/` | internal ACC 0.70 / external ACC 0.50（full Agent） |
| 全队列冻结审计 | `pipeline/experiments/reports/gastric_us_agent_full_queue_audit_20260809/` | external 379；gated RAG 相对 base ACC +0.005，T2 recall 无提升 |

**冻结验证（验收面板，n=20/20）**

| Cohort | base T-only | full Agent | delta | mean rag_weight |
|--------|------------:|-----------:|------:|----------------:|
| internal | 0.700 | 0.700 | +0.000 | 0.235 |
| external | 0.450 | 0.500 | +0.050 | 0.200 |

解释：这是 Agent 链路验收面板，不是全量 external / Phase 0 主表。T2 recall 在该小样本上仍为 0，继续作为边界问题，不启动新 backbone 竞赛。

**当前最高优先级**

1. 保持 acc_boost2 为 Agent final；Phase 0 仅审计分表。
2. **人机协同主线收口**：同一医生、同一病例的 Round2 AI-assisted 阅片；模型/Agent 结果只作可追溯基础，不替代医生获益证据。
3. SAM3.1 继续作为交互/视频候选；只有更大规模对照后才替换 `segmentation_primary`。

### 0B. 2026-08-10 人机协同收口快照

| 项 | 状态 |
|----|------|
| 冻结契约 | `docs/READER_ROUND2_FREEZE_CONTRACT_20260810.md` / `data/registry/reader_round2_study_freeze_20260810.json` |
| Round1 无 AI 基线导出 | 已生成；primary 14 医生 mean T ACC ≈ 0.444，BM ≈ 0.501 |
| Round2 医生阅片 | `prepared_not_run`（research 完成行 = 0） |
| 资历登记 | 14 名主分析医生仍为 `pending`；揭盲前必须登记 |
| 报告质量 / 安全 / 时间 schema | 已冻结；模板在 `docs/clinical_validation/reader_round2_exports/` |
| SAP / 证据链 | `docs/READER_ROUND2_STATISTICAL_ANALYSIS_PLAN_20260810.md`；`docs/paper_drafts/human_ai_reader_evidence_chain_20260810.md` |
| 运行时研究契约 | 已接入服务端认证身份、冻结病例顺序、结构化征象和时间事件；正式 research 尚未启动 |
| 临床 uplift 声称 | **blocked**（gate：`round2_gate_status.json`） |
| Autoresearch 结果汇总 | `pipeline/autoresearch/results/latest/RESULTS_SUMMARY.md` |

执行命令见 `docs/READER_ROUND2_EXECUTION_RUNBOOK_20260810.md`。重建汇总：

```bash
python3 scripts/build_autoresearch_results_summary.py
```

---

## 0. 历史快照（2026-06-10）

### 冻结主模型（L1）

| 项 | 值 |
|----|-----|
| Run | `tstaging_4class_acc_boost2_multitask_screened_eval_20260603_162955` |
| 结构 | dual ConvNeXt + mask4ch + clinical22 + ordinal + multitask + boundary cost |
| Config | `pipeline/configs/tstaging_4class_acc_boost2_multitask_screened_eval.yaml` |
| Checkpoint | `pipeline/experiments/tree/.../acc_boost2_.../best_model.pth` |

### 数据 contract

| Split | 目录 | Patient | Frame | 用途 |
|-------|------|---------|-------|------|
| Legacy Train/Val | `pipeline/data/tstaging_4class_screened_eval_20260531` | 1441+167 | 9138+1117 | 历史模型追溯；train/val 含 `ext/*`，不再作为合规 external 泛化训练入口 |
| **Phase 0 train/val** | `…/screened_eval_phase0_xiehe_20260610` | **1219+135** | **7874+904** | **B1 诚实重训（无 ext/\*）** |
| Prospective | 同上 `test_prospective` | **425** | 1659 | tune / 模型选择 |
| External | `…/screened_latest_external_2966_20260529` | **485** | 2458 | **冻结 test，只报告** |

筛图：2966 帧全集 → Grad-CAM reject 508 → 保留 **2458 帧 / 485 patient**。

### Legacy 结果审计（不作为 no-external-train 主结果）

| 指标 | Prospective (425) | External 全 cohort (485) | External **held-out audit** (399) |
|------|-------------------|--------------------------|----------------------------|
| Frame macro AUC | **0.8655** | **0.8572** | — |
| Patient ACC（L1 单模型） | **72.0%** | **62.9%** | **55.6%** |
| Patient ACC（融合 calibrated） | — | 66.6% | **59.4%** |
| T2 recall（frame, L1） | 54.8% | 49.2% | — |

**held-out audit 定义**：legacy external 485 patient 中，**86 个** `clinical_patient_uid` 曾出现在 legacy train 的 `ext/*` 行（帧不重复，但 patient 级有记忆）。全 cohort ACC 会被重叠子集（86 patient，ACC≈100%）抬高；剔除后得到的 59.4% 仍是 contaminated-train 模型的 post-hoc 审计，不是 no-external-train 主泛化结果。

当前合规训练入口应使用 Phase 0：`pipeline/data/tstaging_4class_screened_eval_phase0_xiehe_20260610/`；DINO/anatomic 训练使用 `pipeline/data/tstaging_4class_anatomic_region_contrastive_phase0/regions/`。

重算命令与产物见 `pipeline/experiments/reports/gastric_us_multimodal_agent/screened_external_disjoint_v1/README.md`。

#### held-out 每类 recall（399 patient，patient 级 hybrid 聚合）

| 模型 | T1 | T2 | T3 | T4+ |
|------|-----|-----|-----|-----|
| acc_boost2 | 52.3% | **11.3%** | 46.2% | 75.7% |
| fused_calibrated | 53.8% | **13.2%** | 55.8% | 77.4% |

held-out 混淆矩阵（fused_calibrated，行=真值 T1–T4+）：

```text
        pred   T1   T2   T3  T4+
true T1        35    6   13   11
     T2        10    7   21   15
     T3         8    3   58   35
     T4+        5    4   31  137
```

#### held-out 分中心 patient ACC（399 子集）

| Source | n | acc_boost2 | fused_calibrated | 备注 |
|--------|---|------------|------------------|------|
| ext/putian | 145 | 54.5% | 56.6% | 最大 held-out 子集 |
| ext/福建省立医院 | 24 | **95.8%** | **95.8%** | 域偏移正向 |
| ext/zhongliu | 82 | 81.7% | 82.9% | T4+ recall 高、T1–T3 低 |
| ext/中核五〇四医院 | 67 | 32.8% | 41.8% | T2 recall &lt;9% |
| ext/北京友谊医院 | 22 | 31.8% | 45.5% | T2 recall 0% |
| ext/佛山市第一人民医院 | 31 | 29.0% | 35.5% | 最低 ACC 之一 |
| ext/福建省德化县医院 | 16 | 56.3% | 56.3% | n 小 |
| ext/putian2 | 8 | 37.5% | 37.5% | n 小 |
| ext/sanming | 4 | 75.0% | 75.0% | n 极小 |

**解读**：单 cohort ACC 掩盖 **10–66 pp** 的分中心差距；汇报必须带分中心或至少 worst-center 行。

### Phase 0 诚实重训（B1）

| 口径 | Run | External patient ACC | 说明 |
|------|-----|----------------------|------|
| doctor_roi（参考上限） | `…_225852` | **46.4%** | 非部署一致；local 用医生 ROI |
| **predicted_roi（部署一致）** | **完成** `…_predroi_20260615_100801` | **47.1%** patient / AUC 0.668 | overlap=0；vs doctor_roi 46.4% |

实现细节：[`phase0_acc_boost2_implementation_20260610.html`](phase0_acc_boost2_implementation_20260610.html) §部署一致 ROI。

### 当前最高优先级阻塞项

1. **T checkpoint 口径已定（2026-08-09）**：Agent final 保留 acc_boost2（06-03）；Phase 0 `225852` 仅作严格泛化审计分表
2. **T2 边界**：验收面板与 Phase 0 external 均显示 T2 recall 偏低；停止在 prospective 上堆 fusion 网格追 80% ACC
3. **SAM3.1 晋升门槛**：交互服务已上线，Agent `segmentation_primary` 仍为 UNet，待更大规模对照后再切换
4. **prospective leak**：legacy train 仍含 `int/prospective` 与 test_prospective 重叠（见 Phase 0 HTML §3）

---

## 1. 为什么主线变了

| 过去默认表述 | 当前共识 |
|--------------|----------|
| 先良恶性边缘监督，再考虑 T | **T 分期最重要**；良恶性先做、但不最重要 |
| 继续扩四分类 backbone | 四分类已有 scoreboard 优胜路线，**少训多选** |
| Stage 1 第一优先级 | Stage 1 资产 **已有**；瓶颈在 **Agent 整合与 T 边界** |
| RAG 暂缓 | Case-RAG **纳入** Agent，但服从 T 主线与门控 |

项目阶段判断：**从「模型竞赛」进入「系统整合」**（见总框架 §2）。

---

## 2. 当前只回答的 5 个问题

1. **Agent 默认用哪条 T 分期 checkpoint？** → **acc_boost2**（06-03 L1；见 §0）
2. **分割 / 胃腔 / wall 证据如何进工具链？**（可信度与 fallback；P0.2 wall 5ch 已 FAIL）
3. **Case-RAG 在什么 T 边界场景加权？**（T2/T3、T3/T4+；external ACC 46%，不替代 base T）
4. **冻结验证前 split 是否 patient-disjoint？** → **否**；train 含 ext/putian 等，与 external 重叠 87 patient → **B1 必做**
5. **论文主表报哪个 ACC？** → **held-out 399 patient** + 全 cohort 485 作 sensitivity；禁止只报 66.6% 而不披露重叠

---

## 3. 任务优先级（执行时不可颠倒）

```text
P0  T 分期（四分类）患者级输出与外部验证
P1  辅助诊断 Agent（工具链 + 证据融合 + 工作台）
P2  T-centric Case-RAG + 门控
P3  良恶性 / 边缘监督（先良恶性、再 T 四分类；资源从属）
P4  新 backbone 训练（需书面理由）
```

---

## 4. 当前主线：三阶段

### 阶段 A — 资产审计（读懂已有结果）

**目标**：不新增大训练，先形成「模型选型表」。

必读：

- `pipeline/experiments/tables/tstaging_4class_mainline_scoreboard.csv`
- `pipeline/experiments/reports/tstaging_4class_mainline_summary.md`
- `pipeline/experiments/mainlines/tstaging_4class/baseline_registry.yaml`
- `pipeline/experiments/reports/gastric_us_agent_scientific_benchmark/scientific_summary.md`

待建交付（建议）：

- `docs/mainline/model_asset_audit.md` — 每条能力：checkpoint、AUC、部署 realism、是否接 Agent
- `pipeline/agent/config/agent_backend_registry.yaml` — Agent 默认 T / seg / YOLO backend
- [`tstaging_classifier_architecture_zh.md`](tstaging_classifier_architecture_zh.md) — 双分支 / patch / 相似病例是否进分类 forward

**阶段 A 完成标准**：团队能口头说出「Agent 默认 T 模型是 acc_boost2、prospective AUC 0.87、external held-out patient ACC ~56%、何时 fallback」。

### 阶段 A+ — 模型与融合资产（2026-05~06 已产出）

| 资产 | 路径 | 状态 | 备注 |
|------|------|------|------|
| L1 主模型 | `…/acc_boost2_20260603_162955` | **冻结** | external AUC 0.8572 |
| 早期融合 baseline | `latest_external_2966_screened_acc80_attempt_v1` | 完成 | 61.86%（held-out ~55.6%） |
| 多分支 boost 融合 | `screened_4class_acc_boost_v1` | 完成 | 66.6% / held-out 59.4% |
| DINO scalar + Case-RAG | `screened_dino_full_pipeline_20260529.html` | 完成 | 未进主融合 |
| ACC80 overnight | `screened_acc80_video_20260601_011334` | 完成 | 未达 80%；video MIL 已补跑 |
| 探索：wall 5ch | `P0_2_WALLAUX_5CH_RESULTS.md` | **FAIL** | over-stage 翻倍 |
| 探索：DINO late fusion | — | **未做** | P0.1 TBD |

---

### 阶段 B — Agent 整合（当前工程重心）

**默认 T backend（待写入 registry）**：

```yaml
# pipeline/agent/config/agent_backend_registry.yaml（待建）
t_staging:
  default_run: tstaging_4class_acc_boost2_multitask_screened_eval_20260603_162955
  checkpoint: pipeline/experiments/tree/.../best_model.pth
  input: mask4ch + clinical22
  report_metrics:
    prospective_patient_acc: 0.72
    external_patient_acc_all: 0.629
    external_patient_acc_held_out: 0.556
```

**目标**：`analyze_case.py` 输出可信的 **T 分期 + 证据链**。

| 序号 | 工作项 |
|------|--------|
| B1 | Phase 0 split：train 剔除 `ext/*` 及与 external 重叠 UID（见下 §4.1） |
| B2 | `ClassificationTool` 默认 acc_boost2 checkpoint（registry 已更新 2026-06-10） |
| B3 | SegmentationTool 固定 nnU-Net / DINO 默认与低 Dice fallback |
| B4 | Wall-band / breakthrough 特征进入证据（对接 region-aware 资产） |
| B5 | SimilarityTool 升级：DINO 或 adapter 区域向量 + T 标签检索 |
| B6 | RAGGate：仅 T2/T3、T3/T4+ 边界与低 entropy 时加权 |
| B7 | 前端 Agent Workbench 与真实 JSON 对齐 |

**阶段 B 完成标准**：选 20 例内部 + 20 例外部，Agent JSON 中 T 概率来自真实 checkpoint，且有 supporting/conflicting/uncertainty 字段。

#### §4.1 B1 Phase 0 split 执行清单

目标：train **不含**任何 `ext/*` 行；external test patient UID 与 train **零重叠**。

| 步骤 | 状态 | 动作 | 产物 |
|------|------|------|------|
| 1 | **已完成** | `build_screened_phase0_xiehe_only_splits.py` | `pipeline/data/tstaging_4class_screened_eval_phase0_xiehe_20260610/` |
| 2 | **已完成** | overlap 审计 | `overlap_clinical_patient_uids=0`（见 `phase0_manifest.json`） |
| 3 | **已完成** | Phase 0 训练 config | `pipeline/configs/tstaging_4class_acc_boost2_multitask_screened_eval_phase0.yaml` |
| 4 | **已完成** | `run_experiment.py`（3 段续训，主 run `225852`） | `…/phase0_20260610_225852/best_model.pth` |
| 5 | **已完成** | `run_phase0_post_train_eval.py` | `eval/phase0_external/`、`phase0_eval_summary.json` |
| 6 | **已完成** | disjoint 脚本验证 | overlap=0；held-out = 全 external（456 patient） |

```bash
python pipeline/scripts/build_screened_phase0_xiehe_only_splits.py

# 重训（GPU 就绪后）:
bash pipeline/scripts/run_phase0_acc_boost2_retrain.sh
# 或手动: CUDA_VISIBLE_DEVICES=1 python pipeline/run_experiment.py \
#   --config pipeline/configs/tstaging_4class_acc_boost2_multitask_screened_eval_phase0.yaml --gpu 0
```

**主 run（2026-06-11 完成）**：
- 目录：`pipeline/experiments/tree/.../tstaging_4class_acc_boost2_multitask_screened_eval_phase0_20260610_225852`
- 日志：`pipeline/experiments/overnight_runs/phase0_acc_boost2_20260610/final_eval.log`
- manifest：`pipeline/experiments/overnight_runs/phase0_acc_boost2_20260610/manifest.json`
- 代码地图：[`phase0_acc_boost2_implementation_20260610.html`](phase0_acc_boost2_implementation_20260610.html)

**验收**：`overlap_clinical_patient_uids == 0`；external patient ACC **46.4%** 为严格泛化主结果（无需再报 399 vs 485 双轨）。

### 阶段 C — 冻结验证与论文

**目标**：证明 **Full Agent > base T-only**，且外部不降太多。

- 跑 `gastric_us_agent_scientific_benchmark` 全矩阵；
- 内部 test + 2025 prospective + Tier-1/2/3 外部；
- 主表以 **T 分期** 为主，良恶性为辅；
- M14 后禁止用外部调参再测。

详见 [`gastric_us_agent_scientific_validation_and_case_rag_plan_zh.md`](gastric_us_agent_scientific_validation_and_case_rag_plan_zh.md)。

---

## 5. 良恶性与四分类：执行顺序与 ACC80 现状

当前主线执行顺序：

```text
输入超声帧/病例
  -> 良恶性二分类（benign vs malignant）
  -> 若判为或疑似恶性，再进入 T1/T2/T3/T4+ 四分类（acc_boost2 或 Agent 融合）
  -> Agent 汇总良恶性置信度、T 分期概率、证据链与不确定性
```

### 良恶性（P3，从属）

| 口径 | Patient AUC | 说明 |
|------|-------------|------|
| 历史主测试集 binary | 0.99–1.00 | 不可与当前 external 混谈 |
| Screened external 2966 | **0.755** | image-only 过夜；需 dual/interaction 重跑 |

入口：`pipeline/scripts/run_screened_binary_then_4class_20260531.sh`

### 四分类 ACC80 尝试（已跑完，未达标）

| 路线 | External patient ACC（485） | Held-out（399） | 结论 |
|------|----------------------------|-----------------|------|
| L1 acc_boost2 单模型 | 63.3% | **55.6%** | 当前最强单模型 |
| fused_calibrated 融合 | 66.6% | **59.4%** | post-hoc；prospective 多阶段选参 |
| overnight multitask_boundary | 58.1% | — | frame AUC 0.80 |
| 目标 | 80% | — | **未达**；T2 patient recall ~31% |

**ACC80 脚本**（历史长跑入口，默认 config 已过时，四分类应改用 acc_boost 家族）：

```bash
GPUS=0,1 PARALLEL=2 MAX_HOURS=12 ENABLE_VIDEO_MIL=0 \
  bash pipeline/scripts/run_screened_acc80_video_overnight_20260601.sh

python pipeline/scripts/boost_screened_4class_patient_acc.py \
  --output-dir pipeline/experiments/reports/gastric_us_multimodal_agent/screened_4class_acc_boost_v1
```

**不单独作为成功标准**：良恶性 AUC 不能替代 T 分期主表；**禁止**在 external 标签上继续调 fusion 追 80%。

---

## 6. T2/T3 收口（贯穿 B、C）

四分类 **不继续无边界扩 backbone 实验**（06-03 L1 已饱和：#5→#6 ext AUC +0.0006），但 **必须持续做**：

1. T2→T3 误分：GradCAM / ROI / wall / 分割 Dice 联合看；
2. 按 **source、held-out vs overlap、ROI 失败** 分层（held-out 下佛山/北京 ACC ~30%，福建省立 ~96%）；
3. GT ROI vs 预测 ROI vs region-aware；
4. Case-RAG hard negative 与 Agent 规则记忆。

**论文/reporting 最低字段**：patient ACC、balanced ACC、macro AUC、**每类 recall**、**held-out ACC**、分中心 patient ACC。

---

## 7. 方法学红线（汇报时必须遵守）

| 红线 | 说明 |
|------|------|
| 禁止只报 485 全 cohort ACC | 必须并列 **399 held-out** |
| 禁止称「完全 no-leak external」 | train 含 ext/*；87 patient 重叠 |
| 禁止在 external 上调 fusion/calibration | 只能在 prospective（425）选参 |
| 禁止混 pre/post screening prospective | n=253 vs n=1659 不可比 |
| 禁止把 frame AUC 当 patient ACC | 两列分开 |
| 禁止把 multimodal（clinical22）当纯影像 | 主表需标注 input 模态 |
| 禁止无上限 fusion 搜索后只报最佳 | 多阶段选参 → 乐观偏差；需 frozen protocol |

---

## 8. 当前暂缓

- 大规模换 backbone 四分类（acc_boost2 已饱和）；
- 在 prospective 上继续堆 fusion/calibration 网格追 80% ACC；
- 与 T Agent 无关的 VLM 主线；
- 未接 T backend 的孤立 RAG demo；
- 在外部数据训练后仍称「独立 external 验证」而不报 held-out；
- 让医生大规模补复杂突破 mask（除非 T2/T3 试点证明必要）。

---

## 9. 新想法准入三问

1. 是否帮助 **提高或解释 T 分期**（尤其 T2/T3、T3/T4+）？
2. 是否帮助 **Agent 整合已有模型资产**（而不是重复训练同类模型）？
3. 是否能在 **冻结 split** 下报告可复现指标（含 held-out external）？

三问皆否 → 不进当前优先级。

---

## 10. 关键脚本与产物索引

| 脚本 | 用途 |
|------|------|
| `report_screened_external_patient_disjoint_metrics.py` | held-out / overlap / 分中心 patient 指标 |
| `boost_screened_4class_patient_acc.py` | 多分支融合 → `screened_4class_acc_boost_v1` |
| `run_screened_acc80_video_overnight_20260601.sh` | ACC80 过夜训练 launcher |
| `evaluate_acc80_overnight_runs.py` | 过夜 run 选型 + external 导出 |
| `run_screened_4class_acc_boost_20260602.sh` | acc_boost1/2 训练入口 |
| `train_screened_stack_fusion.py` | 早期 stack 融合（61.86%） |
| `discover_screened_external_best_acc.py` | 分支 discovery / 候选扫描 |
| `build_screened_phase0_xiehe_only_splits.py` | Phase 0 internal-only train/val（B1） |
| `build_screened_test_splits.py` | Grad-CAM 筛图 test CSV 构建 |
| `audit_latest_external_screened_csv.py` | external CSV 审计 |

| 产物目录 | 内容 |
|----------|------|
| `…/screened_4class_acc_boost_v1/` | 融合 CSV、calibration、branch preds |
| `…/screened_external_disjoint_v1/` | held-out 重估 JSON/CSV + README |
| `…/screened_acc80_video_20260601_011334/` | 过夜训练 manifest + eval |
| `…/acc_boost2_20260603_162955/` | **冻结 L1** checkpoint + eval |
| `…/screened_eval_phase0_xiehe_20260610/` | **Phase 0 split**（overlap=0） |
| `…/phase0_20260610_225852/` | **Phase 0 主 checkpoint** + eval |

---

## 11. 相关文档

| 文档 | 用途 |
|------|------|
| [`MAINLINE_FACTS_v2.md`](MAINLINE_FACTS_v2.md) | 数字 SSOT、6 版本对比、P0.x 探索线 |
| [`screened_dino_full_pipeline_20260529.html`](screened_dino_full_pipeline_20260529.html) | 筛图审计、DINO、ACC80、方法学限制 |
| [`phase0_acc_boost2_implementation_20260610.html`](phase0_acc_boost2_implementation_20260610.html) | Phase 0 架构、代码路径、产物索引 |
| [`external_heldout_patient_acc_594_explained.md`](external_heldout_patient_acc_594_explained.md) | 59.4% vs 46.4% 审计叙事 |
| [`gastric_tstaging_project_framework_zh.md`](gastric_tstaging_project_framework_zh.md) | 总框架、资产地图 |
| [`gastric_us_agent_clinical_workflow_model_inventory_dino_memory.md`](gastric_us_agent_clinical_workflow_model_inventory_dino_memory.md) | Agent 工具与模型清单 |
| [`gastric_us_agent_scientific_validation_and_case_rag_plan_zh.md`](gastric_us_agent_scientific_validation_and_case_rag_plan_zh.md) | 冻结验证与 RAG |
| [`P0_2_WALLAUX_5CH_RESULTS.md`](P0_2_WALLAUX_5CH_RESULTS.md) | wall 5ch FAIL 归因 |
| `pipeline/experiments/mainlines/tstaging_4class/` | T 分期主线注册表 |
