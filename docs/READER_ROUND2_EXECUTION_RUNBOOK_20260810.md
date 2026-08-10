# 第二轮 AI 辅助阅片执行 Runbook

> 冻结 ID：`reader_round2_freeze_20260810`  
> 日期：2026-08-10  
> 当前执行状态：`prepared_not_run`  
> 契约：[`READER_ROUND2_FREEZE_CONTRACT_20260810.md`](READER_ROUND2_FREEZE_CONTRACT_20260810.md)  
> 导出目录：[`clinical_validation/reader_round2_exports/`](clinical_validation/reader_round2_exports/)

## 1. 本 todo 完成边界

本仓库可完成的工程闭环：

1. 冻结契约、病例顺序、资历登记模板；
2. 报告质量 / 时间分解 / 安全终点 schema；
3. 可审计导出脚手架与 Round1 基线表；
4. research 事件过滤与完成门控脚本；
5. 统计分析计划与 uplift 分析脚本（Round2 为空时输出 blocked）。

**不能在本 todo 内伪造**：真实医生 AI-assisted 阅片结果。在 `round2_completed_rows == 0` 时，任何准确率提升、资历跨越或报告改善表述都必须标记为 `not_estimable`。

## 2. Go / No-Go

| 检查项 | 通过条件 | 当前 |
|--------|----------|------|
| Freeze JSON | `reader_round2_study_freeze_20260810.json` 存在且 hash 一致 | pass |
| Manifest | 2400 planned / 2312 pairable | pass |
| Case order | 2400 行，seed `20260810` | pass |
| Expertise registry | 14 名主分析医生 `registration_status=registered` | **fail**（全部 pending） |
| Washout | 距该医生 Round1 最后保存 >= 14 天 | 启动前人工确认 |
| Auth binding | 事件含 `authenticated_reader_id`，`environment=research` | 启动前确认 |
| Pathology hidden | API 不返回 `reference_pt` / nature | 已有协议；启动前回归 |
| Export dry-run | `export_status.json` 生成 | pass |
| Research events | `analyze_reader_audit_events.py --environment research` 有完成病例 | **fail**（0 events） |

结论：允许继续工程与分析脚手架；**禁止**宣称 Round2 临床结果已完成。

## 3. 正式启动前命令

```bash
# 1) 资历登记完成后重新校验分层
python3 scripts/build_reader_round2_freeze_tables.py

# 2) 门控（expertise 未齐 / Round2 未开始应 exit non-zero 或 status=blocked）
python3 scripts/validate_reader_round2_gate.py

# 3) 研究环境必须由认证反向代理注入身份和签名
export READER_AUTH_PROXY_SECRET='<server-side-secret>'
# Browser URL must include: ?environment=research

# 4) 导出 Round1 基线与配对骨架
python3 scripts/export_reader_round2_paired_tables.py

# 5) 过滤 research 事件（启动后）
python3 scripts/analyze_reader_audit_events.py --environment research

# 6) 填入 Round2 后再导出配对 uplift
python3 scripts/export_reader_round2_paired_tables.py \
  --round2-case-csv docs/clinical_validation/reader_round2_exports/reader_case_level_from_audit.csv

# 7) 资历交互与安全分析
python3 scripts/analyze_reader_round2_expertise_uplift.py
```

## 4. 阅片操作要点

1. 仅使用认证会话中的 `Doctor_XX`；禁止 URL 改 ID。
2. 服务端按认证医生应用 `reader_round2_case_order_20260810.csv` 的 `presentation_index`，前端不能自行重排。
3. AI 只提供推荐、证据与 `review_required` 报告草稿；医生必须可修改 / 拒绝 / 标记证据不足。
4. 先记录医生初始判断，再提交最终判断；每例同时保存病灶范围、胃壁受侵深度、浆膜改变、生长方式、AI 建议、动作、修改原因和证据 ID。
5. 时间字段拆分：总时间、主动阅片、AI 等待、报告完成。
6. QA / staging 事件不得混入 research 分析。

## 5. 主分析集

- Primary：14 名 complete-150 医生、仅 `baseline_pairable=true` 病例。
- Extended：16 名有 Round1 记录（含 Doctor_09 / Doctor_13 的共同完成子集）。
- Doctor_05：找回 Round1 前不进入严格配对。
- 良恶性 50 与 T 分期 100 分开统计；早期 AI-favorable 100 例只能作敏感性材料。

## 6. 完成后归档

完成后更新：

1. `data/registry/reader_round2_study_freeze_20260810.json` 的 `execution_status` → `completed`（或新 freeze）；
2. `docs/clinical_validation/reader_round2_exports/export_status.json`；
3. `docs/PROJECT_CHANGELOG.md`；
4. 论文证据链中的 Round2 区块从 blocked 改为 estimated。

当前 dry-run 归档日期：2026-08-10；`round2_completed_rows=0`。
