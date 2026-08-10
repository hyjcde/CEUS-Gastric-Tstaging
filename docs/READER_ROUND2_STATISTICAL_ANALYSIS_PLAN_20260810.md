# 第二轮人机协同阅片统计分析计划（SAP）

> 版本：v1.0  
> 日期：2026-08-10  
> 冻结 ID：`reader_round2_freeze_20260810`  
> 状态：预注册分析计划；Round2 数据未到前禁止写临床 uplift 结论  
> 实现脚本：`scripts/analyze_reader_round2_expertise_uplift.py`

## 1. 分析原则

1. 单位：患者级 / 病例级判断；禁止图像级泄漏到医生阅片结论。
2. 配对键：`reader_id + case_id`。
3. 主分析集：14 名 complete-150 且 `baseline_pairable=true`。
4. 资历分层必须在结果揭盲前登记；主分析两层 junior / senior；intermediate 作敏感性。
5. 顺序固定为先无 AI 后 AI-assisted，必须把学习效应与顺序效应列为限制。
6. QA / staging / unknown_reader 事件一律排除。

## 2. 主终点

患者级四分类 T 分期准确率的配对变化：

```text
delta_acc_T = ACC(ai_assisted) - ACC(no_ai)
```

在主分析集上按病例配对；同时报告医生级均值与 95% CI（bootstrap 或混合模型）。

## 3. 关键次终点

| 终点 | 定义 |
|------|------|
| T2/T3 边界错误率 | 真值与最终判断在 {T2,T3} 互换 |
| T3/T4+ 边界错误率 | 真值与最终判断在 {T3,T4+} 互换 |
| 过度 / 低估分期 | 最终序高于 / 低于真值 |
| 良恶性准确率 | 50 例任务单独统计 |
| 报告完整性与事实一致性 | 盲法量表均值；AI draft 与医生最终报告分列 |
| 总时间与报告时间 | `total_case_time_sec`、`doctor_active_reading_sec`、`report_completion_sec`；`ai_wait_sec` 另列 |
| 医生间一致性 / 方差 | 病例级多读者一致率与资历层内方差 |
| AI 纠错率 | Round1 错 → Round2 对 |
| AI 诱导错误率 | Round1 对 → Round2 错 |
| 证据不足谨慎行为 | `insufficient_evidence` / `request_more_evidence` 占比 |

## 4. 资历比较（预注册）

### 4.1 绝对跨越假设

```text
ACC(junior, ai_assisted) - ACC(senior, no_ai)
```

仅当资历分层有效、样本量足够且诱导错误未同步恶化时，才可写“低年资 AI 辅助超过未辅助高年资”；否则改写为探索性。

### 4.2 交互假设

```text
uplift_junior - uplift_senior
即 condition × expertise 交互
```

这是资历获益差异的主检验，不只比较两个绝对均值。

## 5. 统计方法

1. 病例配对：McNemar（二分类正确/错误）或配对混合效应模型（doctor 与 case 随机效应）。
2. 效应量：准确率差、OR、标准化均差；均报 95% CI。
3. 多重比较：主终点一次；关键次终点按族控制或明确 exploratory。
4. 缺失：Doctor_09 / Doctor_13 仅共同完成病例；Doctor_05 缺 Round1 时排除严格配对。
5. 敏感性：extended 16-reader；含 intermediate 三层；早期 100 例 AI-favorable 子集不得并入主表。

## 6. 安全与临床获益门槛

同时满足才可写临床获益：

1. 医生最终判断准确率改善且 CI 不跨过无获益；
2. AI 诱导错误未同步恶化到抵消纠错；
3. `review_required` / 可修改 / 可拒绝路径保持完整；
4. 报告质量未显著下降。

工程验收、离线 Agent 回放、AI 采纳率均不能替代上述门槛。

## 7. 当前可计算内容（Round2 未跑）

脚本可输出：

- Round1 no-AI 医生级 / 病例级准确率与时间；
- 资历登记完备性；
- Round2 uplift / 交互 / 安全终点状态 = `blocked_until_round2_data`。

不得用模型 ACC、Agent 20+20 或早期多读者子集填补主终点。
