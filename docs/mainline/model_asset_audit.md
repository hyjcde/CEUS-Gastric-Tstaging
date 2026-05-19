# 模型资产审计（Agent 选型）

> **目的**：在仓库内已训练模型中，锁定 Agent 应使用的 T 分期 / 分割 / YOLO 等 checkpoint，避免 `ClassificationTool` 继续指向过期的 `20260302` 小样本 run。  
> **机器可读注册表**：[`pipeline/agent/config/agent_backend_registry.yaml`](../../pipeline/agent/config/agent_backend_registry.yaml)  
> **治理源**：[`baseline_registry.yaml`](../../pipeline/experiments/mainlines/tstaging_4class/baseline_registry.yaml)、[`tstaging_4class_mainline_scoreboard.csv`](../../pipeline/experiments/tables/tstaging_4class_mainline_scoreboard.csv)

---

## 1. 怎么理解「最好」

本项目对 T 分期有 **两条指标**，不能单看一个数字：

| 指标 | 临床/产品含义 | 当前谁最强 |
|------|----------------|------------|
| **test_prospective_auc** | 协和 2025 前瞻集（最接近上线） | **mask4ch + clinical22 冻结线 0.7455** |
| **test_external_auc** | 莆田等外部泛化 | **region-aware 0.7480**（未 promote） |

**治理规则**（`baseline_registry.yaml`）：promote 需 **prospective 不劣于当前冻结基线**，且 external 不能明显塌陷。因此：

- Agent **最终 T 结论** → 用 **已 Promote 的 mask4ch 全量 run（20260423）**
- Agent **外部泛化辅助证据** → 可挂载 **region-aware（20260426）**，权重为 0 直到 contrastive 推理适配器完成
- **不要用** 仅 external 更高但 prospective 明显更差的模型单独定稿

---

## 2. T 分期 4-class（主结果表）

来源：`tstaging_4class_mainline_scoreboard.csv`（全量数据 + clinical 22D）。

| stage_id | external AUC | prospective AUC | 决策 | Agent 角色 |
|----------|-------------|-----------------|------|------------|
| `structure_mask4ch_clinical22` | **0.7326** | **0.7455** | **Promote（冻结）** | **primary — 最终 T** |
| `deploy_predicted_roi_mask4ch_clinical22` | 0.7438 | 0.6683 | KeepForReference | deploy fallback（无医生 ROI 时） |
| `breakthrough_regionaware_clinical22` | **0.7480** | 0.6857 | KeepForReference | external 辅助证据 |
| `baseline_locked` (ROI+clinical) | 0.7276 | 0.6968 | Promote（旧 primary） | 已被 mask4ch 取代 |
| `deploy_predicted_roi_clinical22` | 0.7153 | 0.6553 | Stop | 不接入 |
| `wall_aux_mask4ch_clinical22` | 0.7248 | 0.7228 | Stop | 不接入 |

### 2.1 冻结主线（Agent 应立即使用）

| 字段 | 值 |
|------|-----|
| backend_id | `tstage_mask4ch_clinical22_frozen_20260423` |
| run_dir | `pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301` |
| checkpoint | `.../best_model.pth`（约 1.1GB，已核验存在） |
| config | `pipeline/configs/tstaging_4class_dual_v2_mask4ch_clinical22_full.yaml` |
| model_type | `dual_branch` → `ClassificationTool` **已支持** |

### 2.2 external 最强（辅助，Phase B 接推理）

| 字段 | 值 |
|------|-----|
| backend_id | `tstage_regionaware_clinical22_20260426` |
| run_dir | `.../tstaging_4class_regionaware_clinical22_full_20260426_090539` |
| checkpoint | `.../best_model.pth`（已核验存在） |
| model_type | `contrastive_dual` → **需新推理适配器**（`run_contrastive.py` 训练的 head，不是当前 `DualBranchClassifier`） |

### 2.3 代码现状 vs 目标

| 位置 | 之前 | 现在（Phase A） |
|------|------|-----------------|
| `classification_tool.py` DEFAULT | `tstaging_4class_dual_v2_mask4ch_20260302_201944`（常缺失） | → **20260423 冻结 run** |
| `model_tool_backends.yaml` | 仍标 legacy 20260302 为 classification | 以 `agent_backend_registry.yaml` 为准 |
| `analyze_case.py` | `ClassificationTool()` 无参 | 继承新默认目录 |

### 2.4 优化线 / 研究面板（不进 Agent 默认定稿）

来自 `experiments_master_v2.csv` 与 `model_tool_backends.yaml`：

| 实验 | ext AUC | pro AUC | 说明 |
|------|---------|---------|------|
| boxguided wall contrastive 20260506 | 0.7067 | **0.7908** | 前瞻强、外部弱 → 仅 T2/T3 研究面板 |
| multiframe_convnext AUC85 20260426 | 0.7364 | 0.7206 | 患者级 MIL 候选，未接产品路径 |
| medaux / boundary / predmask_attn 等 | 见 master | 见 master | 未超过冻结线，不 promote |

---

## 3. 分割（lesion mask → T 的 4th channel）

| backend_id | 路径 | Agent | 备注 |
|------------|------|-------|------|
| `lesion_segmentation_unet_fulldata_convnext_base` | `.../segmentation_fulldata/checkpoints/best_model.pth` | **SegmentationTool 默认** | fulldata ConvNeXt-Base UNet |
| `lesion_segmentation_dinov3_vitb16_last2blocks_candidate_20260512` | `experiments/segmentation/segmentation_dinov3_.../best.pt` | DINOv3SegmentationTool | external Dice +0.038 vs UNet；前瞻接近 |
| nnU-Net（训练主线） | `nnUNet` Dataset001 等 | 离线产 predicted mask | Agent 未直接加载 nnU-Net |

**结论**：在线 Agent 继续 **UNet fulldata**；DINOv3 作 **candidate / T2-T3 复核**，待患者级 T 面板后再 promote。

---

## 4. 胃腔 YOLO

| backend_id | checkpoint | 状态 |
|------------|------------|------|
| `yolo_internal_high_iou_v1` | `pipeline/experiments/yolo_internal_high_iou_v1/weights/best.pt` | 已训练；**analyze_case 未接 LumenDetectionTool** |
| v6 refined baseline | `archived/experiments_yolo/01_Detection/20260105_v6_refined_baseline/weights/best.pt` | 微调起点 |

**结论**：Phase B+ 增加 `LumenDetectionTool`，默认权重 `yolo_internal_high_iou_v1`。

---

## 5. Phase A / B 行动项

| 阶段 | 任务 | 状态 |
|------|------|------|
| **A** | 本文 + `agent_backend_registry.yaml` | ✅ |
| **A** | `ClassificationTool` 默认 → 20260423 冻结 checkpoint | ✅ |
| **B** | 实现 `ContrastiveTStagingTool` → region-aware 进 `tool_evidence` | 待做 |
| **B** | `analyze_case` 从 registry 读 backend_id，写入 `runtime_verification` | 待做 |
| **B** | 无医生 ROI 时 fallback `predroi_mask4ch` | 待做 |
| **B+** | YOLO lumen tool | 待做 |

---

## 6. 相关文档

- [`gastric_tstaging_project_framework_zh.md`](gastric_tstaging_project_framework_zh.md) §2.2  
- [`tstaging_current_mainline.md`](tstaging_current_mainline.md) Phase A/B  
- [`pipeline/agent/configs/model_tool_backends.yaml`](../../pipeline/agent/configs/model_tool_backends.yaml)（研究/ caution 后端）
