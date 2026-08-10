# 第二轮 AI 辅助阅片冻结契约

> 冻结 ID：`reader_round2_freeze_20260810`  
> 日期：2026-08-10  
> 执行状态：`prepared_not_run`（契约已冻结，医生正式阅片未开始）  
> 机器可读：[`data/registry/reader_round2_study_freeze_20260810.json`](../data/registry/reader_round2_study_freeze_20260810.json)  
> 协议基础：[`AI_ASSISTED_READER_PILOT_PROTOCOL_20260801.md`](AI_ASSISTED_READER_PILOT_PROTOCOL_20260801.md)

## 1. 冻结目的

在启动同一医生、同一病例的第二轮 AI 辅助阅片前，锁定：

1. 医生身份绑定规则；
2. 软件 / 模型 / 规则 / prompt / manifest 版本；
3. 病例呈现顺序与洗脱期；
4. 事件命名空间与 QA 排除；
5. 资历字段与揭盲前分层规则。

未完成上述登记前，不得开始正式 Round2 research 事件。

## 2. 配对范围

| 集合 | 定义 | 用途 |
|------|------|------|
| Primary complete-150 | 14 名 Round1 完成 150/150 且全部 `baseline_pairable=true` 的医生 | 主分析 |
| Extended 16-reader | 含 Doctor_09（64 pairable）与 Doctor_13（148 pairable） | 扩展描述 / 敏感性 |
| Doctor_05 | Round1 记录缺失 | 找回前禁止进入严格配对 |

Manifest：

```text
data/registry/reader_round2_ai_assisted_manifest.csv
sha256: cd19511afe73fa4bf9447802b324b0558b5997c08a664d062b8d0d3163643f76
planned_rows: 2400
baseline_pairable_rows: 2312
```

## 3. 身份绑定

- `reader_id` 必须来自服务器认证会话，禁止 URL 参数或前端临时字符串。
- research 事件缺少 `authenticated_reader_id` 时，服务端应拒绝写入或强制标记 `environment=non_research`。
- 匿名研究 ID 与真实身份的映射只保存在受控账号表；公开分析只使用 `Doctor_XX`。
- 资历登记表：`data/registry/reader_expertise_registry_20260810.csv`（当前全部 `registration_status=pending`）。

## 4. 资历分层（揭盲前预设）

主分析只用两层，避免 16 人被过度切分：

| 主层 | 规则 |
|------|------|
| junior | 住院医师 / 医师 / 规培，或 `gi_us_years < 7` |
| senior | 主任 / 副主任，或主治且 `gi_us_years >= 10`，或 `gi_us_years >= 10` |

敏感性层：

| 层 | 规则 |
|----|------|
| intermediate | 主治且 `7 <= gi_us_years < 10`，或无法归入 junior/senior 的已登记读者 |

规则实现：`scripts/build_reader_round2_freeze_tables.py::assign_expertise_tier`。

必填字段（阅片前）：`title`、`gi_us_years`、`center`、`hospital_level`、`annual_case_volume`。

早期 100 例子集的 4 名有 profile 读者另存于 `reader_early_subset_profiles_20260810.csv`，**不得**自动映射为 Round1 `Doctor_XX`。

## 5. 病例顺序与洗脱

- Seed：`20260810`
- 方法：每位医生独立 Fisher–Yates 打乱 150 例
- 产物：`data/registry/reader_round2_case_order_20260810.csv`
- 洗脱：距该医生 Round1 最后保存至少 14 天
- Round2 可再次观看视频；禁止显示病理参考与 Round1 答案

## 6. 版本字段（每个事件必填）

```text
freeze_id
software_version
agent_version
model_version
rule_version
prompt_version
manifest_version
environment          # qa | staging | research | production
authenticated_reader_id
```

Backend 冻结口径：

- Agent final T：`tstage_acc_boost2_screened_20260603`
- Phase 0：仅审计分表，不替换 Agent final
- 分割主后端：UNet ConvNeXt fulldata
- SAM3.1：交互候选，未升为 Agent primary

详见 `docs/mainline/asset_freeze_decision_20260809.md` 与 `pipeline/agent/config/agent_backend_registry.yaml`。

实现门槛：

- `environment=research` 的病例队列、Agent 请求和审计事件必须经过认证反向代理身份；
- 服务端只接受 `x-authenticated-reader-id` 与对应 HMAC 签名，不接受 URL 或浏览器 body 中的 `reader_id` 作为研究身份；
- 研究队列由服务端按 `reader_round2_case_order_20260810.csv` 的 `presentation_index` 应用当前认证医生的冻结顺序；
- 每个研究事件必须在顶层写入 `authenticated_reader_id`、freeze、软件、Agent、模型、规则、prompt、manifest 和 environment 字段；
- 每例医生动作必须尽量记录病灶范围、胃壁受侵深度、浆膜改变、生长方式、证据 ID 和时间分解。

## 7. 事件命名空间

| environment | 允许用途 | 可否进入正式统计 |
|-------------|---------|------------------|
| qa | 浏览器 smoke / 开发 | 否 |
| staging | 干跑、培训演示 | 否 |
| research | 认证医生 Round2 | 是（过滤 exclusion 后） |
| production | 非本研究服务 | 否 |

强制排除：[`reader_audit_exclusions_20260801.md`](READER_AUDIT_QA_EXCLUSION_20260801.md) 中的 102 条 QA 事件及后续同规则事件。

## 8. 可见 / 隐藏信息

Round2 可见：视频、关键帧、SAM/ROI 交互、结构化征象、GC-US/壁层提示、AI 推荐、支持/冲突/不确定性证据、`review_required` 报告草稿。

Round2 隐藏：`reference_pt`、`reference_lesion_nature`、Round1 医生答案、原始病理报告。

## 9. 启动门槛清单

启动正式医生 Round2 前必须全部打勾：

- [ ] 14 名 primary 医生完成资历登记且 `expertise_tier_primary != pending`
- [ ] 认证绑定通过，测试账号无法写入 `environment=research`
- [ ] case order CSV 已由服务端分发给阅片系统并校验 seed
- [ ] research UI/API：初始判断前不暴露 AI，最终 `doctor_action` 无初始判断被拒绝
- [ ] `smoke_reader_round2_research_contract.py` 离线通过；可选 live 签名请求通过
- [ ] washout >= 14 天已核对
- [ ] freeze JSON / backend registry / exclusion list hash 已写入开跑记录
- [ ] 导出脚本 `scripts/export_reader_round2_paired_tables.py` dry-run 通过

## 10. 重建命令

```bash
# Rebuild templates/order only when intentionally regenerating a freeze.
# Existing artifacts are skipped unless --force is passed.
python3 scripts/build_reader_round2_freeze_tables.py

# Import filled expertise without rewriting case-order hashes:
python3 scripts/import_reader_expertise_registry.py --input /path/to/filled_expertise.csv
```
