# 资产冻结决策（2026-08-09）

> 机器可读入口：[`pipeline/agent/config/agent_backend_registry.yaml`](../../pipeline/agent/config/agent_backend_registry.yaml)  
> 分割门控证据：[`artifacts/sam31_training/sam31_gastric_lora_full_components_5epoch_run2/evaluation/static_video_promotion_decision.json`](../../artifacts/sam31_training/sam31_gastric_lora_full_components_5epoch_run2/evaluation/static_video_promotion_decision.json)

本文锁定当前 Agent 与论文汇报口径，避免把 SAM3.1 Dice 提升直接表述为 T 分期增益，也避免混报 legacy / Phase 0 两条 T 线。

## 1. 决策摘要

| 资产 | 冻结选择 | 角色 | 说明 |
|------|----------|------|------|
| T 分期主后端 | `tstage_acc_boost2_screened_20260603` | Agent final T | prospective 优先的生产主线；外部必须并列 held-out 399 |
| T 分期严格泛化线 | `tstage_acc_boost2_phase0_20260610` | paper / audit only | 无 `ext/*` 训练；与主线分表报告，禁止混报 |
| 分割生产主后端 | UNet ConvNeXt fulldata | Agent `segmentation_primary` | 暂不静默替换 |
| SAM3.1 LoRA run2 | `sam31_gastric_lora_full_components_5epoch_run2` | interactive / research candidate | 8768 工作台已加载；Agent 批量链路需验收后再晋升 |

## 2. SAM3.1 冻结点

- Checkpoint: `artifacts/sam31_training/sam31_gastric_lora_full_components_5epoch_run2/best_lora_weights.pt`
- Topology: 383 LoRA modules, 766 adapter keys, strict load
- Service: `http://127.0.0.1:8768` (`sam3.1_image_detector_lora`, `lora_loaded=true`)
- Protocol: `frozen_registry_static_sam31_oracle_box_v1`
- Patient mean Dice: external 0.8544, internal holdout 0.8636, prospective 0.8816
- Empty prediction rate: 0 on all three frozen cohorts
- Video canary: 94/94 frames, 2 re-anchors, native multiplex memory disabled

**晋升规则**：只有在 Agent 链路对 UNet vs SAM3.1 的受控对照不劣、且 20+20 病例 JSON 证据链完整后，才允许把 `segmentation_primary` 切到 SAM3.1。Dice 提升本身不构成 T 分期改善证据。

## 3. T checkpoint 口径

### 3.1 生产主线（保留）

- backend_id: `tstage_acc_boost2_screened_20260603`
- checkpoint: `pipeline/experiments/tree/gastric_tstage_4class/classification/dual_convnext/tstaging_4class_acc_boost2_multitask_screened_eval_20260603_162955/best_model.pth`
- Prospective patient ACC: 0.720
- External patient ACC all 485: 0.629
- External patient ACC held-out 399: 0.556

### 3.2 Phase 0 严格泛化线（分表）

- backend_id: `tstage_acc_boost2_phase0_20260610`
- checkpoint: `pipeline/experiments/tree/gastric_tstage_4class/classification/dual_convnext/tstaging_4class_acc_boost2_multitask_screened_eval_phase0_20260610_225852/best_model.pth`
- Train: Phase 0 xiehe-only, overlap_clinical_patient_uids=0
- External patient ACC（严格泛化）: 约 46.4% doctor_roi / 47.1% predicted_roi

**禁止**：把 Phase 0 ACC 与 legacy 485/399 数字放在同一主表格而不标注训练口径。

## 4. 方法学红线（继续有效）

1. 验证必须患者级，禁止图像级泄漏。
2. SAM3.1 训练不得纳入 holdout / prospective / external。
3. 不在 external 标签上继续调 fusion / calibration。
4. 禁止只报 485 全 cohort ACC；legacy 线必须并列 held-out 399。
5. 无 dense cine 真值时不报告 temporal Dice。
6. 分割 Dice / Boundary F1 / HD95 提升不得直接写成 T 分期改善。

## 5. 下一步验收门槛

1. `analyze_case` 真实调用分割、T、wall、多帧聚合、Case-RAG gate。
2. JSON 含 supporting / conflicting / uncertainty。
3. 20 internal + 20 external 病例验收。
4. 再决定是否把 SAM3.1 升为 `segmentation_primary`。

## 6. 2026-08-09 验收结果

- Clean offline acceptance report: `pipeline/experiments/agent_smoke_test/acceptance_clean_20260809/acceptance_report.json`
- Result: **passed** (`internal_20_seg_cls`, `external_20_seg_cls`, `evidence_fields_complete`, SAM3.1 service ready but not promoted)
- Clean frozen validation: `pipeline/experiments/reports/gastric_us_agent_frozen_validation_clean_20260809/`
  - internal n=20: base 0.700 / full Agent 0.700
  - external n=20: base 0.450 / full Agent 0.500 (`+0.050`)
- Interpretation: small-panel evidence only; T2 recall remains 0 on this panel; do not promote SAM3.1 to Agent primary yet.

## 7. Full-queue frozen audit

- Report: `pipeline/experiments/reports/gastric_us_agent_full_queue_audit_20260809/SUMMARY.md`
- Source: frozen prediction files only; no external label tuning or model selection
- Coverage: val 151, test 479, external 379 patients
- External gated RAG versus base: ACC 0.623 versus 0.617; T2 recall unchanged at 0.152
- Strict Phase 0 disjoint external: 456 patients, ACC 0.443, T2 recall 0.060, train/external UID overlap 0
