# 第二轮终点、报告质量与安全记录

> 版本：v1.0  
> 日期：2026-08-10  
> 冻结契约：[`READER_ROUND2_FREEZE_CONTRACT_20260810.md`](READER_ROUND2_FREEZE_CONTRACT_20260810.md)  
> Schema：
> - [`schemas/reader_round2_case_record_v1.json`](schemas/reader_round2_case_record_v1.json)
> - [`schemas/reader_report_quality_score_v1.json`](schemas/reader_report_quality_score_v1.json)
> - [`schemas/reader_time_decomposition_v1.json`](schemas/reader_time_decomposition_v1.json)

## 1. 每例最小记录

同一 `reader_id + case_id` 必须能重建：

```text
doctor_initial_judgment
AI_recommendation
doctor_action (accept / modify / reject / request_more_evidence / insufficient_evidence)
doctor_final_judgment
modify_reason
evidence_ids
version fields (freeze_id, software/agent/model/rule/prompt/manifest)
time decomposition
```

模型建议、医生最终判断和病理参考字段相互独立，禁止共用一个字段。

结构化 T 分期证据至少保留：

```text
lesion_extent
wall_invasion_depth
serosal_breakthrough
growth_pattern
```

这些字段可以来自医生修正后的 GC-US 报告状态，也可以来自 AI 建议，但必须记录
`source`、`status` 和 `evidence_ref`，不能把模型代理值直接写成病理确认值。

## 2. 时间分解

| 字段 | 含义 | 可否当医生工作负荷 |
|------|------|--------------------|
| `total_case_time_sec` | 打开病例到最终提交 | 可用作总流程时间 |
| `doctor_active_reading_sec` | 视频/帧/ROI 主动交互 | 是 |
| `ai_wait_sec` | Agent/SAM/报告生成等待 | 否，单独报告 |
| `report_completion_sec` | 草稿出现到最终确认 | 报告效率终点 |

禁止把 Agent ~111 秒等待直接写成“医生节省/增加的工作时间”。主效率终点优先报告 `doctor_active_reading_sec` 与 `report_completion_sec`，并并列 `ai_wait_sec`。

## 3. 报告质量评分

AI draft 与医生最终报告分开评分。量表 1–5：

1. completeness  
2. facticity  
3. key_tstage_evidence  
4. conflict_uncertainty_expression  
5. traceability  
6. clinical_usability  

要求：

- 至少两名独立评分者；
- 评分者对 `condition`（no_ai / ai_assisted）尽量盲法；
- 报告评分者一致性（加权 κ 或 ICC）；
- `overall_usable` 二值结论单独保存。

模板导出目录：

```text
docs/clinical_validation/reader_round2_exports/report_quality_scores_template.csv
```

## 4. 安全终点定义

| 终点 | 定义 |
|------|------|
| AI 纠错 | Round1 最终错误，且 Round2 最终正确 |
| AI 诱导错误 | Round1 最终正确，且 Round2 最终错误 |
| 边界错误 T2/T3 | 真值与最终判断在 {T2,T3} 间互换 |
| 边界错误 T3/T4+ | 真值与最终判断在 {T3,T4+} 间互换 |
| 过度分期 | 最终判断序高于真值 |
| 低估分期 | 最终判断序低于真值 |
| 证据不足行为 | `doctor_action=insufficient_evidence` 或 `request_more_evidence`，且未强制给出高置信分期 |

安全分析必须同时报告纠错与诱导错误；只报纠错不算完整安全证据。

## 5. 导出表

分析前由 `scripts/export_reader_round2_paired_tables.py` 生成：

```text
reader_case_level.csv
reader_doctor_level.csv
reader_ai_action_level.csv
reader_safety_events.csv
reader_time_decomposition.csv
report_quality_scores.csv
```

QA / staging 事件必须先按 exclusion manifest 过滤。

## 6. 与主终点的关系

主终点仍是患者级四分类 T 分期最终正确率的配对变化。  
报告质量、效率、一致性、安全均为关键次终点，不得用采纳率或报告流畅度替代主终点。
