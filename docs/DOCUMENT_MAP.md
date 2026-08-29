# 文档索引（按用途分类）

配合 [ARCHITECTURE.md](ARCHITECTURE.md) 使用。标 **A** = Tier A 必读，**B** = 按角色阅读，**C** = 归档参考。

## mainline/（当前主线）

| 文件 | 层级 | 说明 |
|------|------|------|
| gastric_tstaging_project_framework_zh.md | **A** | 项目总框架 |
| gastric_tstaging_project_logic.html | **A** | 可视化总览 |
| tstaging_current_mainline.md | **A** | 当前执行主线 |
| clinical_11_field_pack.md | **A** | 11 项临床字段（禁止再叫 22） |
| agent_api_contract.md | **A** | Agent API 契约 |
| model_asset_audit.md | B | 模型选型表（持续更新） |
| tstaging_classifier_architecture_zh.md | B | 分类网络结构 |
| gastric_us_agent_clinical_workflow_model_inventory_dino_memory.md | B | Agent 工具与模型清单 |
| gastric_us_agent_scientific_validation_and_case_rag_plan_zh.md | B | 验证与 Case-RAG 计划 |
| gastric_us_agent_methodology_architecture_spec_zh.md | B | 方法学架构图说明 |
| gastric_us_agent_current_flow_and_poe_architecture.md | B | 当前流程与 Poe 图 |
| multimodal_evidence_agent_self_evolution_mainline.md | B | 大课题主线 |
| self_evolving_multimodal_agent_platform_blueprint.md | B | 平台蓝图 |
| agent_runtime_openclaw_hermes_integration.md | B | 运行时集成 |
| agent_platform_rollout.md | B |  rollout 计划 |
| project_scope.md | B | 范围（可被 framework 覆盖） |
| research_mainline.md | B | 研究叙事 |
| t2_t3_boundary_metrics_zh.md | B | T2/T3 指标 |
| tstagenet_s1_lumen_detector_v1_20260420.md | B | 胃腔检测方案 |
| tstaging_pipeline_first_blueprint_20260420.md | B | 早期 pipeline 蓝图 |
| screened_latest_eval_20260528.html | C | 单次评估页 |
| figures/** | C | 出图产物（实体在 `artifacts/docs_exports/mainline_figures/`） |
| project_logic_white/** | C | 离线白底 bundle |
| *.txt (poe prompts) | C | 图生成 prompt 存档 |

## 治理规范

| 文件 | 层级 |
|------|------|
| data_governance/INDEX.md | **A** | 薄索引 → registry / split |
| experiment_governance/INDEX.md | **A** | 薄索引 → experiments/registry |
| data_governance/data_registry_spec.md | **A** |
| data_governance/data_split_policy.md | **A** |
| data_governance/data_qc_policy.md | B |
| experiment_governance/experiment_structure.md | **A** |
| experiment_governance/baseline_plan.md | B |
| evaluation/validation_protocol.md | **A** |
| visualization/visualization_standard.md | B |

## 仓库外联文档

| 文件 | 层级 |
|------|------|
| ../README.md | **A** |
| ../MAINTENANCE.md | **A** |
| ../dataset/DATASET_GUIDE.md | **A** |
| ../scripts/README.md | **A** |
| ../experiments/registry.csv | B |
| ../experiments/LARGE_ARTIFACTS.md | B |

## references/（历史实验笔记，非 SSOT）

| 目录 | 层级 | 说明 |
|------|------|------|
| references/dinov3/ | C | 202605 DINO 分割/分类探索 |
| references/segdino/ | C | SegDINO / clean agent 系列 |

## technical/

| 文件 | 层级 | 说明 |
|------|------|------|
| technical/COLLABORATOR_ACCESS.md | B | 工作站协作者 SSH 与原始数据 ACL |
| technical/COMPUTE_LINKAGE.md | B | Mac / 工作站 / 公网算力联动 |
| technical/WALL_PIXEL_BRUSH_LAYERING.md | B | 当前画笔像素分层：输入输出、走廊、三等分贴标签；不定 cT |

## product/

| 文件 | 层级 | 说明 |
|------|------|------|
| product/公网RAG相似病例与指南解释说明.md | B | 公网医生站现网 RAG：相似病例、证据对照、指南解释、隧道与叠加 |
| product/公网RAG验收与安全后续.md | B | RAG 安全、盲法、版本漂移与临床验收后续（P0 起） |
| product/医生阅片流程图.drawio | B | 现网医生阅片全流程（draw.io）：登录到保存报告；第 2 页为 T 分期与 Assist/RAG 加细 |
| meetings/2026-08-28_浆膜预期走行线协议.md | B | 医生画预期走行线、AI 独立判连续；训练无胃壁标注时的评估交互 |
| plans/DINO_WALL_LAYER_EMBEDDING_20260828.md | B | 研究：走廊内 DINO token 读胃壁层次特征；灰度聚类对照；不进 Assist |

## 其他 docs 子目录

| 目录 | 层级 | 说明 |
|------|------|------|
| archive_refs/ | C | 旧 Tstaging 迁移 |
| agent_memory/ | C | Agent 记忆约定与草案 |
| github_agent_docs/ | C | Hermes/OpenClaw 笔记 |
| gastric_paper/ | B | 论文导出资产 |
| dataset/ | B | 外部集统计表/图（非影像数据） |
| output/ | C | 生成物 |

## 明确不是文档入口

| 路径 | 说明 |
|------|------|
| `docs copy/` | 历史合并稿，见 archive |
| `apps/gastric_scan_next/*_SUMMARY.md` | 前端开发笔记 |
| `pipeline/experiments/reports/` | 实验报告（按实验名进入） |
