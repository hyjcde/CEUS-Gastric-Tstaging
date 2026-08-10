# 人机协同主文证据链（主文 / 补充材料）

> 日期：2026-08-10  
> 冻结：`reader_round2_freeze_20260810`  
> 定位：可审计的人机协同 T 分期工作流；不是纯 Agent 架构展示  
> 状态：模型与 Round1 基线可写；AI-assisted 医生获益 **blocked**

## 1. 叙事优先级

| 层级 | 内容 | 是否可进入主结论 |
|------|------|------------------|
| A. 临床人机协同 | 同医生同病例 no-AI → AI-assisted 配对变化 | Round2 完成后 |
| B. 资历交互 | 低年资 uplift vs 高年资；低年资+AI vs 高年资无AI | 分层登记 + Round2 后 |
| C. 报告 / 效率 / 一致 / 安全 | 盲法报告分、时间分解、κ/方差、纠错与诱导错误 | Round2 + 评分完成后 |
| D. 系统基础 | Agent final `acc_boost2`、20+20 验收、审计轨迹 | 可写，不得替代 A–C |
| E. 严格泛化审计 | Phase 0 predicted-ROI external | 补充 / 分表，不与 D 混成一个数字 |

禁止用模型单一高分（例如内部面板 ACC）替代医生最终获益。

## 2. 建议图表结构

### Fig 1 — 工作流与审计边界

病例进入 → 冻结系统版本 → AI 推荐 / 证据 / `review_required` 草稿 → 医生修改或拒绝 → 最终判断与事件日志。

证据：

- `docs/READER_ROUND2_FREEZE_CONTRACT_20260810.md`
- `docs/AGENT_NEXT_RUNTIME_VERSION_20260801.md`
- `docs/mainline/asset_freeze_decision_20260809.md`

### Table 1 — 队列、医生与版本

病例 150（BM 50 + T 100）、医生完成度、资历登记、freeze / manifest / 软件版本。

证据：

- `data/registry/reader_round2_ai_assisted_manifest.summary.json`
- `data/registry/reader_expertise_registry_20260810.csv`
- `data/registry/reader_round2_study_freeze_20260810.json`

### Table 2 — Round1 无 AI 基线（按资历）

当前可先报整体；资历列在登记完成后填充。

当前 dry-run（primary 14 医生均值，2026-08-10 导出）：

| 指标 | 值 |
|------|-----|
| Mean BM ACC | ~0.504 |
| Mean T ACC | ~0.444 |
| Mean reading time | doctor-level 见 `round1_doctor_level.csv` |

证据：`docs/clinical_validation/reader_round2_exports/round1_doctor_level.csv`

### Fig 2 / Table 3 — 配对 uplift 与资历跨越

同医生同病例 delta ACC；重点：`junior+AI` 是否跨过 `senior no-AI`，以及 `condition × expertise` 交互。

当前状态：`not_estimable`（`expertise_uplift_summary.json`）。

### Table 4 / Fig 3 — 报告质量、效率、一致性、安全

报告量表、时间分解、医生间变异、AI 纠错 / 诱导错误。

当前状态：模板已就绪，分数与 Round2 事件为空。

### 补充材料 — 模型与 Agent

- Agent final T：`acc_boost2` screened 06-03  
- Phase 0 external predicted-ROI：严格泛化审计线，分表  
- 20+20 offline acceptance：工程验收  
- Full-queue gated RAG：非显著全队列增益，不作主获益  
- SAM3.1：交互候选，非 Agent primary

## 3. 用语边界

| 可用 | 不可用（证据未齐前） |
|------|----------------------|
| clinician-in-the-loop | self-improving |
| review_required / editable assistance | AI replaces senior readers |
| prepared_not_run Round2 | AI-assisted clinical uplift achieved |
| model foundation / audit | single ACC number as clinical benefit |

## 4. 证据门槛清单

写 AI-assisted clinical results 前必须全部通过：

1. [ ] 事件完整性（research namespace，QA 排除）
2. [ ] 身份绑定（authenticated_reader_id）
3. [ ] 病理隐藏
4. [ ] 版本冻结字段齐全
5. [ ] 导出审计（paired tables + gate JSON）
6. [ ] 资历分层揭盲前登记
7. [ ] 报告评分双人一致性
8. [ ] 安全终点同时报告纠错与诱导错误

当前门控文件：

```text
docs/clinical_validation/reader_round2_exports/round2_gate_status.json
docs/clinical_validation/reader_round2_exports/expertise_uplift_summary.json
docs/clinical_validation/reader_round2_exports/export_status.json
pipeline/autoresearch/results/latest/RESULTS_SUMMARY.md
```

## 5. 与参考论文叙事的对齐方式

参考 Nature Communications 类“低年资 + AI 可接近/超过高年资无辅助”叙事时：

1. AI 推荐是中间变量，医生最终判断是终点；
2. 报告质量与效率是并列终点，不是装饰；
3. 必须保留可修改、可拒绝、可追溯；
4. 本项目额外强调超声 T 分期边界（T2/T3、T3/T4+）与病理隐藏审计。

在本项目 Round2 完成前，只可写“研究设计对齐”，不可写“已复现临床获益”。
