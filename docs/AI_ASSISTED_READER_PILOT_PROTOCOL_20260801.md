# 第二轮 AI 辅助医生阅片协议

> 版本：v1.1  
> 建立日期：2026-08-01  
> 更新日期：2026-08-10  
> 当前状态：`ready_for_round2` / 执行状态 `prepared_not_run`  
> 第一轮审计：[`READER_STUDY_ROUND1_SERVER_AUDIT_20260801.md`](READER_STUDY_ROUND1_SERVER_AUDIT_20260801.md)  
> 第二轮配对清单：`data/registry/reader_round2_ai_assisted_manifest.csv`  
> 配对清单脚本：`scripts/build_reader_round2_manifest.py`  
> 冻结契约：[`READER_ROUND2_FREEZE_CONTRACT_20260810.md`](READER_ROUND2_FREEZE_CONTRACT_20260810.md)  
> 终点与报告质量：[`READER_ROUND2_ENDPOINTS_AND_REPORT_QUALITY_20260810.md`](READER_ROUND2_ENDPOINTS_AND_REPORT_QUALITY_20260810.md)  
> 执行 runbook：[`READER_ROUND2_EXECUTION_RUNBOOK_20260810.md`](READER_ROUND2_EXECUTION_RUNBOOK_20260810.md)  
> SAP：[`READER_ROUND2_STATISTICAL_ANALYSIS_PLAN_20260810.md`](READER_ROUND2_STATISTICAL_ANALYSIS_PLAN_20260810.md)

## 1. 目的

在第一轮独立阅片的基础上，使用同一病例和同一批医生进行第二轮 AI 辅助阅片，比较每位医生、每个病例的判断变化、时间变化和安全行为。

## 2. 病例设计

第一轮病例全部保留：

```text
任务一：良恶性 50 例
任务二：T 分期 100 例
合计：150 例

第二轮计划：每位第一轮医生重新完成同一病例 bundle 的 AI 辅助阅片。
```

病例来自现有 `reader_study_v150` bundle，均有视频。参考标签只进入安全分析清单；临床阅片 API 已隐藏 `reference_pt` 和 `reference_lesion_nature`，不返回给浏览器。

## 3. 医生范围

第一轮服务器记录中实际有结果的医生：

```text
Doctor_01, Doctor_02, Doctor_03, Doctor_04,
Doctor_06, Doctor_07, Doctor_08, Doctor_09,
Doctor_10, Doctor_11, Doctor_12, Doctor_13,
Doctor_14, Doctor_15, Doctor_16, Doctor_17
```

当前未找到 `Doctor_05/progress.json`，所以：

- 第二轮可先按 16 位有第一轮记录的医生启动；
- `Doctor_05` 只有找回第一轮记录后才纳入严格配对分析；
- Doctor_09 和 Doctor_13 的第一轮存在未完成病例，第二轮清单保留全部 150 例，但结果表必须标记 `baseline_pairable=false`。

## 4. 第二轮设计

第一轮已经提供 `no_ai` 基线，第二轮只新增 `ai_assisted`：

- `no_ai`：第一轮服务器已有的独立阅片记录；
- `ai_assisted`：第二轮在 Next 工作台中使用 SAM、结构化征象、AI 建议和证据链。

为减少记忆和顺序影响：

- 第一轮和第二轮之间设置洗脱期；
- 第二轮病例顺序重新随机化；
- 但保留 `doctor_id + case_id` 配对键；
- 不覆盖第一轮 JSON，第二轮使用独立的 session 和事件日志；
- 分析时优先使用第一轮已完成的 2,312 条病例记录作为 paired baseline。

正式执行前必须冻结：

- 医生匿名 ID；
- 病例顺序；
- 软件版本；
- 模型版本；
- manifest 版本；
- 洗脱期；
- 是否允许重新查看视频。

## 5. 每例记录内容

### 医生判断

- 良恶性判断；
- 初始 T 分期；
- 最终 T 分期；
- 置信度；
- 主要依据；
- 是否请求补充证据；
- 是否建议进一步检查。

### AI 条件额外记录

- AI 推荐分期；
- AI 良恶性概率；
- 关键帧、ROI、mask 和结构化征象；
- 医生采纳、修改、拒绝或认为证据不足；
- 修改前后值；
- 修改原因；
- AI 错误诱导是否发生。

### 时间和质量

- session 开始/结束；
- 视频和帧查看时间；
- AI 请求耗时；
- 总阅读时间；
- 报告完成时间；
- 图像质量和证据不足原因。

## 6. 主要终点

### 性能

- 患者级良恶性准确率、敏感度、特异度、F1；
- 患者级四分类准确率、macro-F1、balanced accuracy；
- T2/T3 边界错误率；
- 医生间一致性；
- 有 AI 与无 AI 的配对差异。

### 效率

- 每例总阅读时间；
- 生成最终报告所需时间；
- AI 介入后减少或增加的操作时间。

### 安全

- AI 错误诱导率；
- 医生拒绝不可靠建议的比例；
- 证据不足时是否避免强制分期；
- AI 建议与医生最终判断冲突的病例类型。

### 解释性

- 采纳率；
- 修改率；
- 拒绝率；
- 需要补充证据比例；
- 报告中引用结构化征象的比例。

## 7. 统计原则

- 患者是主要独立单位，不能把视频帧当作独立病例；
- 医生和患者都作为随机/分层因素；
- 使用配对比较，不用独立样本检验替代；
- 小样本结果报告点估计和置信区间，不夸大显著性；
- 良恶性和 T 分期分开分析；
- T2/T3 单独报告，不用总体准确率掩盖边界失败；
- AI 建议错误和医生错误分别标记，不能混成一个错误率。
- 主要比较使用第一轮和第二轮同一 `doctor_id + case_id` 的配对记录；
- `baseline_pairable=false` 的病例不进入配对准确率变化，但可进入第二轮单轮描述；
- 医生作为读者层级，病例作为患者层级，不能只汇报所有帧的总体准确率。

## 8. 数据输出

Next 审计事件保存到工作站：

```text
apps/gastric_scan_next/data/reader_audit_events.jsonl
```

事件类型：

- `session_start`
- `session_end`
- `ai_suggestion`
- `report_generated`
- `doctor_action`
- `frame_viewed`
- `error`

分析脚本：

```text
scripts/analyze_reader_audit_events.py
```

它会生成病例级、医生级和安全事件统计模板；当前第一轮分析已有独立结果，
第二轮 JSONL 仍等待实际 AI 辅助阅片后填充。

正式分析前，将 JSONL 转换为：

```text
reader_case_level.csv
reader_doctor_level.csv
reader_ai_action_level.csv
reader_safety_events.csv
```

## 9. 当前限制

第一轮结果已经存在并完成 Mac 归档；第二轮 AI 辅助阅片尚未开始，因此当前不能报告 AI 对医生性能、效率或安全性的改善。

只有完成同一批医生的第二轮阅片并检查事件完整性后，第二轮状态才能改为 `completed`。
