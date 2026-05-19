# 当前执行主线

## 文档定位

本文档定义 **现在到下一阶段** 默认做什么、不做什么。总逻辑与优先级以 [`gastric_tstaging_project_framework_zh.md`](gastric_tstaging_project_framework_zh.md) 为准。

**一句话**：在 **YOLO / 分割 / ConvNeXt T 分期 / DINO** 等已有训练结果基础上，**深入理解并选型接入**，构建以 **T 分期为核心输出** 的术前充盈超声 **辅助诊断 Agent**；良恶性与边缘监督是 **辅助验证手段**，不是项目终局。

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

## 2. 当前只回答的 4 个问题

1. **Agent 默认用哪条 T 分期 checkpoint？**（查 scoreboard / baseline_registry）
2. **分割 / 胃腔 / wall 证据如何进工具链？**（可信度与 fallback）
3. **Case-RAG 在什么 T 边界场景加权？**（冲突与不确定性，不替代 base T）
4. **冻结验证前 split 是否协和-only？**（移出 train 中外部患者）

---

## 3. 任务优先级（执行时不可颠倒）

```text
P0  T 分期（四分类）患者级输出与外部验证
P1  辅助诊断 Agent（工具链 + 证据融合 + 工作台）
P2  T-centric Case-RAG + 门控
P3  良恶性 / 边缘监督（方法验证，资源从属）
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

**阶段 A 完成标准**：团队能口头说出「Agent 默认 T 模型是哪条、external/prospective AUC 多少、何时 fallback」。

### 阶段 B — Agent 整合（当前工程重心）

**目标**：`analyze_case.py` 输出可信的 **T 分期 + 证据链**。

| 序号 | 工作项 |
|------|--------|
| B1 | Phase 0 split：协和-only train，外部仅 external test |
| B2 | `ClassificationTool` 接入 scoreboard 选定 T checkpoint（非 placeholder） |
| B3 | SegmentationTool 固定 nnU-Net / DINO 默认与低 Dice fallback |
| B4 | Wall-band / breakthrough 特征进入证据（对接 region-aware 资产） |
| B5 | SimilarityTool 升级：DINO 或 adapter 区域向量 + T 标签检索 |
| B6 | RAGGate：仅 T2/T3、T3/T4+ 边界与低 entropy 时加权 |
| B7 | 前端 Agent Workbench 与真实 JSON 对齐 |

**阶段 B 完成标准**：选 20 例内部 + 20 例外部，Agent JSON 中 T 概率来自真实 checkpoint，且有 supporting/conflicting/uncertainty 字段。

### 阶段 C — 冻结验证与论文

**目标**：证明 **Full Agent > base T-only**，且外部不降太多。

- 跑 `gastric_us_agent_scientific_benchmark` 全矩阵；
- 内部 test + 2025 prospective + Tier-1/2/3 外部；
- 主表以 **T 分期** 为主，良恶性为辅；
- M14 后禁止用外部调参再测。

详见 [`gastric_us_agent_scientific_validation_and_case_rag_plan_zh.md`](gastric_us_agent_scientific_validation_and_case_rag_plan_zh.md)。

---

## 5. 良恶性与边缘监督：保留但从属

**仍可做**（服务 P0 T 分期，不单独抢资源）：

- 病灶 **core / boundary / far-negative** patch 规则与质检；
- 良恶性 baseline vs 对比学习：**验证是否减少 shortcut**；
- 若良恶性上注意力与外部 AUC 改善，再 **迁移到 T2/T3 patch**。

**不单独作为成功标准**：良恶性 AUC 不能替代 T 分期主表。

---

## 6. T2/T3 收口（贯穿 B、C）

四分类 **不继续无边界扩实验**，但 **必须持续做**：

1. T2→T3 误分病例：GradCAM / ROI / wall 特征 / 分割 Dice 联合看；
2. 按 source、年份、ROI 失败分层；
3. 对比 GT ROI vs 预测 ROI vs region-aware 线；
4. 将结论写入 Case-RAG hard negative 与 Agent 规则记忆。

---

## 7. 当前暂缓

- 大规模换 backbone 四分类；
- 与 T Agent 无关的 VLM 主线；
- 未接 T backend 的孤立 RAG demo；
- 在外部数据训练后仍称「独立外部验证」；
- 让医生大规模补复杂突破 mask（除非 T2/T3 试点证明必要）。

---

## 8. 新想法准入三问

1. 是否帮助 **提高或解释 T 分期**（尤其 T2/T3、T3/T4+）？
2. 是否帮助 **Agent 整合已有模型资产**（而不是重复训练同类模型）？
3. 是否能在 **冻结 split** 下报告可复现指标？

三问皆否 → 不进当前优先级。

---

## 9. 相关文档

| 文档 | 用途 |
|------|------|
| [`gastric_tstaging_project_framework_zh.md`](gastric_tstaging_project_framework_zh.md) | 总框架、资产地图、架构 |
| [`gastric_us_agent_clinical_workflow_model_inventory_dino_memory.md`](gastric_us_agent_clinical_workflow_model_inventory_dino_memory.md) | 工具与模型清单 |
| [`gastric_us_agent_scientific_validation_and_case_rag_plan_zh.md`](gastric_us_agent_scientific_validation_and_case_rag_plan_zh.md) | 验证与 RAG 细则 |
| `pipeline/experiments/mainlines/tstaging_4class/` | T 分期主线注册表 |
