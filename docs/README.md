# 文档与会议（GitHub 同步区）

本目录是仓库内文档集中区：会议转写、产品计划、反馈表、文献清单。
**不包含** 影像数据、视频、账号、API 密钥、大批量 PDF 原文。

## 目录

| 路径 | 内容 |
|------|------|
| [meetings/](./meetings/) | 全部会议转写与纪要索引 |
| [plans/](./plans/) | 人机互助计划、进度核对、需求说明书、七步互助稿 |
| [plans/ccus_t_scoring/](./plans/ccus_t_scoring/) | **CCUS-T 征象积分**：算法说明 + [`batch_eval_v0.md`](./plans/ccus_t_scoring/batch_eval_v0.md) 批量验证 + 医生试用表 |
| [plans/人机互助_进度核对_2026-07-26.md](./plans/人机互助_进度核对_2026-07-26.md) | 进度核对（当前 **P0.14**） |
| [feedback/](./feedback/) | 医生反馈表、待办 |
| [literature/](./literature/) | 文献索引（bib/ris/README，不含 PDF） |
| [当前主线_20260517.md](./当前主线_20260517.md) | 研究主线说明（历史） |
| [export_text_only_20260408/](./export_text_only_20260408/) | 更早导出的文字归档 |

本地草稿目录 `讨论/` 可继续用；定稿请同步到本 `docs/` 再提交。

## 三端资产与备份

- [`ARCHIVE_RECONCILIATION_20260731.md`](./ARCHIVE_RECONCILIATION_20260731.md)：Mac、工作站和百度网盘对账记录
- [`ASSET_LIFECYCLE_REGISTRY_20260731.csv`](./ASSET_LIFECYCLE_REGISTRY_20260731.csv)：三端资产、主工作副本和备份状态
- [`DATA_LINEAGE_MANIFEST_20260731.md`](./DATA_LINEAGE_MANIFEST_20260731.md)：四层数据流水线、患者级 manifest 和多重备份要求
- [`DATASET_AUDIT_LUMEN_AND_ULCER_20260731.md`](./DATASET_AUDIT_LUMEN_AND_ULCER_20260731.md)：胃腔标注、胃腔检测和良恶性/溃疡数据盘点
- [`plans/PROJECT_DATA_ORGANIZATION_SCHEME_20260731.md`](./plans/PROJECT_DATA_ORGANIZATION_SCHEME_20260731.md)：Mac、工作站和百度网盘的数据组织方案
- [`NETDISK_REORGANIZATION_LOG_20260731.md`](./NETDISK_REORGANIZATION_LOG_20260731.md)：百度网盘本轮目录归类和移动记录
- [`ZIP_ARCHIVE_AND_LOCAL_GAP_AUDIT_20260731.md`](./ZIP_ARCHIVE_AND_LOCAL_GAP_AUDIT_20260731.md)：压缩包统一归档与 Mac 缺口核对
- [`GASTRITIS_EXTERNAL_DATA_RECONCILIATION_20260801.md`](./GASTRITIS_EXTERNAL_DATA_RECONCILIATION_20260801.md)：胃炎外部测试集在网盘、工作站和 Mac 的专项核对
- [`MASTER_COHORT_MANIFEST_20260801.md`](./MASTER_COHORT_MANIFEST_20260801.md)：患者级主队列清单的生成、命名空间和核验状态
- [`EXPERIMENT_AUDIT_20260801.md`](./EXPERIMENT_AUDIT_20260801.md)：T 分期和良恶性二分类关键实验的可复现性与公平性审计
- [`BINARY_MAINLINE_EXECUTION_20260802.md`](./BINARY_MAINLINE_EXECUTION_20260802.md)：良恶性二分类历史结果归档、clean 候选数据和主线执行状态
- [`STRUCTURED_EVIDENCE_PROTOCOL_20260801.md`](./STRUCTURED_EVIDENCE_PROTOCOL_20260801.md)：胃腔、病灶/胃壁、良恶性和 T 分期的证据来源与不确定性协议
- [`NEXT_AI_ASSISTED_AUDIT_IMPLEMENTATION_20260801.md`](./NEXT_AI_ASSISTED_AUDIT_IMPLEMENTATION_20260801.md)：Next AI 辅助阅片的 session、AI 建议和医生动作审计实现
- [`AI_ASSISTED_READER_PILOT_PROTOCOL_20260801.md`](./AI_ASSISTED_READER_PILOT_PROTOCOL_20260801.md)：小规模 AI 辅助医生阅片验证协议和病例分层
- [`READER_STUDY_ROUND1_SERVER_AUDIT_20260801.md`](./READER_STUDY_ROUND1_SERVER_AUDIT_20260801.md)：第一轮服务器医生阅片记录、完成度和逐病例基线审计
- [`READER_SYSTEM_ORGANIZATION_20260801.md`](./READER_SYSTEM_ORGANIZATION_20260801.md)：账号、医生、第一轮记录和第二轮系统的统一整理入口
- [`RESULT_FREEZE_MANIFEST_20260801.md`](./RESULT_FREEZE_MANIFEST_20260801.md)：论文与关键结果的来源、权重和冻结门槛
- [`DOCUMENT_MEDIA_REVIEW_20260802.md`](./DOCUMENT_MEDIA_REVIEW_20260802.md)：本地图片、Word、PDF 的版本、内容和版式核对
- [`DINO_GC_US_SIGN_FUSION_PROBE_20260801.md`](./DINO_GC_US_SIGN_FUSION_PROBE_20260801.md)：DINOv3 与结构化 GC-US/胃壁征象融合探针
- [`SEGMENTATION_MODEL_COMPARISON_20260802.md`](./SEGMENTATION_MODEL_COMPARISON_20260802.md)：UNet、SAM2、EfficientSAM3 的患者级交互分割对照与 replay 阻断记录
- [`G17_MORPHOLOGY_TRIAD_AUDIT_20260803.md`](./G17_MORPHOLOGY_TRIAD_AUDIT_20260803.md)：peak sharpness、solidity、robust spiculation 的公式核对与 v2 重算
- [`SAM_DINO_FUSION_PROBE_20260803.md`](./SAM_DINO_FUSION_PROBE_20260803.md)：新 SAM2 与 DINOv3 的 mask 融合探针及门控结果
- [`WORKSTATION_FILE_TREE_20260803.md`](./WORKSTATION_FILE_TREE_20260803.md)：工作站根目录、关键数据树和折叠数量统计
- [`AGENT_BACKEND_E2E_SMOKE_20260801.md`](./AGENT_BACKEND_E2E_SMOKE_20260801.md)：工作站 Agent 到 Next API 的端到端后端验证
- [`LAN_FULL_STACK_ACCEPTANCE_20260801.md`](./LAN_FULL_STACK_ACCEPTANCE_20260801.md)：工作站局域网三服务和功能验收结果
- [`AGENT_NEXT_RUNTIME_VERSION_20260801.md`](./AGENT_NEXT_RUNTIME_VERSION_20260801.md)：Agent/Next/LAN 当前运行版本、模型 hash 和回滚入口
- [`CLEANUP_CONFIRMATION_CHECKLIST_20260731.md`](./CLEANUP_CONFIRMATION_CHECKLIST_20260731.md)：删除、上传、恢复和清理确认条件
- [`memory/`](./memory/)：当前上下文、检索索引、已确认决策和工作记录

## 当前大纲与主研究计划

[`LATEST_PROJECT_OUTLINE_20260802.md`](./LATEST_PROJECT_OUTLINE_20260802.md)
是 2026-08-02 的跨研究、数据、实验、系统、阅片和归档总览，负责说明当前唯一执行顺序。

[`MAIN_RESEARCH_PLAN_NATURE_AI_ASSISTED_READING_20260731.md`](./MAIN_RESEARCH_PLAN_NATURE_AI_ASSISTED_READING_20260731.md)
是当前研究、代码、数据结果和 Overleaf 论文之间的总协调文档。

轻量项目导航入口：
[`PROJECT_NAVIGATION_INDEX.md`](./PROJECT_NAVIGATION_INDEX.md)。
它只记录入口、索引和查找顺序，不复制原始数据或实验产物。

最新工作站只读盘点：
[`WORKSTATION_ASSET_AUDIT_20260731.md`](./WORKSTATION_ASSET_AUDIT_20260731.md)。

T 分期实验候选索引：
[`EXPERIMENT_CANDIDATE_INDEX_20260731.md`](./EXPERIMENT_CANDIDATE_INDEX_20260731.md)。

当前项目状态：
[`CURRENT_PROJECT_STATUS_20260731.md`](./CURRENT_PROJECT_STATUS_20260731.md)。

四分类主线实验卡：
[`EXPERIMENT_CARDS_TSTAGING_MAINLINE_20260731.md`](./EXPERIMENT_CARDS_TSTAGING_MAINLINE_20260731.md)。

Mac 资产冻结地图：
[`MAC_ASSET_AUDIT_20260731.md`](./MAC_ASSET_AUDIT_20260731.md)。

Mac 一级资产 registry：
[`MAC_ASSET_REGISTRY_20260731.csv`](./MAC_ASSET_REGISTRY_20260731.csv)。

Mac 结果与可视化索引：
[`MAC_RESULTS_INDEX_20260731.md`](./MAC_RESULTS_INDEX_20260731.md)。

当前阶段已结束独立人机对比，下一阶段是由 Next 工作台承载的
**AI 辅助医生阅片与前瞻性工作流验证**。
