# `scripts/` 脚本导航索引

本页按**当前主线阶段与功能**对 `scripts/` 下脚本做分组说明，便于检索；**不替代**各脚本的 `argparse` 说明与实验文档。具体参数、路径与推荐命令行请以：

- `python scripts/<脚本名>.py --help`
- 对应实验或 baseline 文档（例如病灶检测见 `experiments/baselines/detection_baseline_v1/YOLO11_BASELINE_PIPELINE.md`）

为准，避免复制易过期的命令细节。

项目阶段与文档总览见根目录 `README.md`、`REPO_LAYOUT.md`、`docs/ARCHITECTURE.md` 与 `docs/mainline/tstaging_current_mainline.md`。

脚本状态登记见 [script_registry.csv](script_registry.csv)（`current` / `legacy` / `runtime`）。

**内部归位：** [INTERNAL_LAYOUT.md](INTERNAL_LAYOUT.md) · 扩展字段：`owner_workspace`, `move_candidate`, `safe_to_run`, `uses_project_root` · 刷新：`python scripts/build_script_registry.py`

**Legacy 查询：** `grep ',legacy,' scripts/script_registry.csv` 或 `grep '# STATUS: legacy' scripts/*.py`

---

## 1. 病灶检测（YOLO）— Stage 1 主线

**用途说明：** 将 LabelMe 病灶标注转为 YOLO 检测数据集，在固定病例级划分上训练 Ultralytics YOLO11，并对多路测试集做统一评估与报告；为后续 patch 采样、边缘监督等提供检测框基础。

### 1.1 推荐执行顺序（正式入口）

与 `YOLO11_BASELINE_PIPELINE.md` 中列出的主链路一致，建议顺序为：

1. `prepare_yolo_detection_dataset.py` — 按配置串联数据准备（内部会调用 split 冻结与数据集构建）。
2. `freeze_detection_internal_holdout_split.py` — 若需重新生成或理解病例级内部划分时使用（通常已由上层准备脚本覆盖）。
3. `build_yolo_detection_dataset.py` — LabelMe 多边形转 YOLO 框与数据集落盘。
4. `run_yolo_detection_train.py` — 从项目配置启动训练并记录实验目录。
5. `run_yolo_detection_eval.py` — 对固定测试集做评估。
6. `generate_yolo_detection_report.py` — 统一训练曲线与测试集对比报告。
7. `generate_yolo_detection_qc_overlays.py` — 对**已准备**的检测数据集做 QC 叠加图。

**说明：** `yolo_detection_runtime.py` 为训练/评估/report 共用的运行时与工具函数，**一般不作为独立 CLI 入口**，由上述脚本引用。

### 1.2 同组扩展脚本（对照、可视化、独立评估集）

- `generate_yolo_detection_comparison.py`、`generate_yolo_detection_model_comparison.py` — 多实验/多模型检测对比报告。
- `generate_yolo_detection_year_comparison.py` — 内部按年份的对比图表面板。
- `generate_yolo_detection_prediction_visuals.py` — 预测叠加与分组示例面板。
- `prepare_labelme_holdout_eval_set.py` — 从 LabelMe 准备独立 holdout 评估子集（与主 YAML 流程配合时请先对照配置与数据治理约定）。

---

## 2. 分割（U-Net2D / SMS / nnU-Net 相关）— Stage 1

**用途说明：** 构建胃壁/腔道等分割基线数据，训练 SMS 或自包含 PyTorch UNet2D，或对 nnU-Net 等产物做导出与评分；与检测并列，为 ROI 与下游分析提供 mask。

| 脚本 | 备注（来自 argparse / 文件头） |
|------|--------------------------------|
| `freeze_sms_internal_holdout_split.py` | 为 SMS baseline 冻结可复现内部 holdout 划分。 |
| `prepare_sms_gastric_2d_dataset.py` | 为 SMS 分割框架准备 2D 胃超声数据集。 |
| `build_sms_baseline_dataset.py` | 构建正式 SMS baseline 数据集与评估来源。 |
| `run_sms_train.py` | 从项目配置启动 SMS 训练。 |
| `run_sms_inference.py` | SMS 推理与项目侧评估。 |
| `run_unet2d_segmentation_baseline.py` | 自包含 PyTorch UNet2D 训练与评估。 |
| `score_binary_segmentation_folder.py` | 预测二值 mask 与 GT 的评分。 |
| `prepare_nnunet_gastric_lumen_fewshot.py` | 从胃腔 LabelMe 准备 nnU-Net few-shot 数据。 |
| `export_nnunet_prediction_review.py` | 导出 nnU-Net 预测的 bbox CSV 与叠加图供审阅。 |
| `make_segmentation_example_panels.py` | 代表性分割可视化面板。 |

---

## 3. 数据治理、临床表与格式转换

**用途说明：** 整理多来源临床表、患者级划分、原始队列预处理与批量裁剪/转换，使数据边界与命名与 `docs/data_governance/` 一致后再进入训练。

| 脚本 | 备注 |
|------|------|
| `organize_dataset_clinical_tables.py` | 将各来源 Excel 临床表整理到 `dataset/tables/` 结构。 |
| `build_patient_media_registry.py` | 从 manifest + 视频索引生成 `data/registry/patient_media_*.csv` 患者级图片/视频注册表。 |
| `build_patient_training_view.py` | 病人级训练 CSV/缺口清单 → `data/registry/patient_training_view/`。 |
| `build_training_media_view.py` | 按任务/模态软链视图 → `dataset/training_views/`（含 loop）。 |
| `build_dataset_detail_html.py` | 固定数据登记的详细 HTML，包含胃腔手动标注、胃炎外部、胃癌视频、胃炎视频和子集可视化 → `dataset/dataset_detail_20260803.html`。 |
| `build_dataset_inventory.py` | 数据集盘点 JSON + inventory HTML。 |
| `build_dataset_visual_overview.py` | **图文总览**（三视图样例置顶）→ `dataset/index.html` + `figures/gallery/`。 |
| `build_static_images_view.py` | 静态图数据集包（默认真实拷贝 original/crop_ui/crop_roi + Excel）→ `dataset/static_images/{internal,external}/`；`--audit-only` 查中心/年份/表格齐全。 |
| `rebuild_safe_crop_ui_review.py` | 非破坏性安全 CROP UI 审阅包：保留超声区域、遮挡周边个人信息，并生成各队列 HTML 对照页。 |
| `build_videos_view.py` | 视频数据集包（真实拷贝 crop_ui + 前瞻 raw）→ `dataset/videos/{internal,external}/`。 |
| `build_gastritis_video_previews.py` | 为胃炎视频测试集生成浏览器兼容的代表性 MP4 预览，不修改 raw 视频。 |
| `build_real_cine_aligned_view.py` | **仅真视频**对齐视图 → `dataset/training_views/t_staging_real_cine/`（监督表 + by_patient）。 |
| `quarantine_loop_still_videos.py` | 历史 `loop_still` 清理脚本；当前静态循环媒体已删除，不再作为可用视频入口。 |
| `freeze_real_cine_training_package.py` | 冻结 eval_role 拆分、泄漏检查、标注队列、`by_split/` 软链。 |
| `export_patient_media_splits.py` | 导出 `pipeline/data/patient_media_tstaging_v1/*_clinical.csv`（含视频列）。 |
| `verify_patient_split_leakage.py` | 检查患者级 split 是否跨 train/val/test 泄漏。 |
| `audit_modeling_dataset_contracts.py` | 审计正式建模数据 contract，确认 clean train/val 无 `ext/*` 且不与 external test 患者重叠。 |
| `build_phase0_anatomic_region_splits.py` | 从 anatomic region CSV 重建 Phase 0 no-external train/val，供 DINO scalar / adapter / mask-guided attention 使用。 |
| `build_dataset_registry.py` | 生成 `data/registry/dataset_registry.csv` 等基础登记。 |
| `build_image_video_pair_index.py` | 构建 manifest 样本与 raw/crop 视频的配对索引。 |
| `build_video_assets_registry.py` | 扫描并登记原始/裁剪视频资产。 |
| `run_full_video_preprocess.py` | 批量生成 `dataset/**/crop_ui/videos`（含静帧 loop 回退）。 |
| `crop_prospective_reader_videos.py` | 前瞻/多中心视频裁剪与 `video_crop_report_*.csv` 生成。 |
| `merge_clinical_features.py` | 临床特征合并（常与概念提取流水线配合）。 |
| `convert_clinical_data.py`、`convert_clinical_data_2019.py`、`convert_clinical_data_2019_nac.py`、`convert_clinical_data_2024.py`、`convert_clinical_data_2024_nac.py` | 各队列/年份临床数据转换入口。 |
| `patient_split.py` | 胃癌数据集患者级划分。 |
| `preprocess_direct_surgery_datasets.py` | 直接手术队列预处理（脚本体量较大，使用前务必读 `--help` 与数据约定）。 |
| `convert_data.py` | 通用/遗留数据转换入口，需结合仓库内实际路径使用。 |
| `batch_convert.py`、`batch_crop.py`、`crop_tool.py`、`crop_year_dataset.py` | 批量转换与裁剪工具；`crop_year_dataset.py` 面向遗留队列与固定 ROI 管线。 |
| `cleanup_nii_only_images.py` | 清理仅含 NIfTI 等遗留图像目录。 |
| `link_videos.py` | 视频链接或路径整理类辅助。 |
| `prepare_frontend_dataset.py` | 前端/演示用数据集准备（非训练默认入口）。 |

---

## 4. T2/T3 与胃壁—腔关系：可视化与分析

**用途说明：** 支撑主线中文档所述「T2/T3 错误分析与证据链」：病灶—胃壁—胃腔空间关系、条带/局部放大、穿透与接触等探索性图与统计；出图风格需符合项目可视化规范（如黑底、Times New Roman，见 `docs/visualization/visualization_standard.md`）。

包含但不限于：`analyze_wall_penetration.py`、`analyze_wall_strip_statistics.py`、`generate_contact_focus_analysis.py`、`generate_contact_focus_visualization.py`、`generate_curved_wall_band_overlay.py`、`generate_edge_zoom_clustering.py`、`generate_gastric_lumen_dual_overlays.py`、`generate_local_zoom_group.py`、`generate_overlay_overview.py`、`generate_single_case_wall_strip_figure.py`、`generate_t2_t3_local_examples.py`、`generate_wall_neighborhood_examples.py`、`export_wall_proxy_from_lumen.py`、`visualize_wall_strip_examples.py`、`visualize_local_junction_continuity.py`、`visualize_wall_layer_profiles.py`、`visualize_overlays.py`、`regenerate_overlays.py`、`regenerate_overlays_from_json.py`。

影像真相 × T 分期 / T-score 草案：`analyze_imaging_truth_tstage_corr.py`（v2）、`analyze_imaging_truth_tstage_corr_v3.py`、`analyze_imaging_truth_paper_metrics.py`、`build_imaging_truth_charts_zh.py`、`draft_tscore_discrete_bins_v1.py`（A4/B6 离散分档 → 总分切点）。

GC-US 轮廓 T-score 特征（morphology / margin / growth）：`gc_us_contour_features.py`（共享库）、`extract_gc_us_morphology_features_v1.py`、`extract_gc_us_margin_features_v1.py`、`extract_gc_us_growth_features_v1.py`、`analyze_gc_us_feature_batch_stats.py`、`eval_gc_us_margin_split_discrimination.py`、`build_gc_us_tscore_feature_pack_v1.py`、`eval_gc_us_tscore_feature_pack_models_v1.py`、`plot_gc_us_tscore_feature_triplets_3d.py`、`analyze_gc_us_feature_lasso_shap_triplets_v1.py`、`analyze_gc_us_tscore_latest_lasso_3d_v1.py`、`build_gc_us_tscore_results_html_v1.py`、`build_gc_us_tscore_results_html_zh_v1.py`（最新 feature pack 的 LASSO 稳定性、显著性筛查、3D 分群图、中文特征计算字典与汇总 HTML → `pipeline/data/gc_us_tscore_features_v1/feature_pack_v1/`）。

产品侧方向归一化征象评分（`ccus_t_rubric_v1.4_us`，不改产品切点）：`pipeline/agent/signs/`（schema / direction_growth / wall_gate / scorer）、`pipeline/agent/tools/gc_us_sign_tool.py`、研究校准 `gc_us_tscore_featurepack_v2.py`、患者级验证 `eval_gc_us_sign_scoring_v1.py`（输出 `docs/plans/ccus_t_scoring/sign_scoring_validation_v1/`）。

结果汇总默认入口为 `pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/index.html`，英文版为同目录的 `index_en.html`。

**注意：** 部分脚本内写死了本机字体或目录（例如 `generate_overlay_overview.py` 使用 macOS 字体路径），换环境运行前需自行核对路径。

---

## 5. 可解释性与病理概念

**用途说明：** 基于图像物理特征或临床概念做可解释分析或概念抽取，用于对照主线中的 GradCAM/注意力讨论；多版本并存反映历史迭代，**默认优先阅读最新版本与 `docs/` 中的实验约定**。

- `explainable_features.py`、`explainable_features_v2.py`、`explainable_features_v3.py`、`explainable_features_v4.py` — 可解释特征提取与可视化（v4 文件头注明为改进的边界/梯度等分析）。
- `extract_pathology_concepts.py` — 从 Excel 抽取病理概念特征。
- `check_concept_quality.py` — 对抽取概念做抽查质检。
- `update_concepts_pipeline.py` — 串联抽取与合并的小脚本，**内部写死输入 Excel 文件名**，使用前需改路径或仅作参考。

---

## 6. Prompt-Mask 交互分割（胃壁感知）

**用途说明：** 静态 Dice 门控 + 同协议 real-cine 视频比较，决定训练 SAM2 adapter、SAM3 adapter 或双模型分工。协议与产物见 `docs/prompt_mask_agent/`、`experiments/prompt_mask_agent/`。

| 脚本 | 备注 |
|------|------|
| `freeze_prompt_mask_static_protocol.py` | 冻结静态评估、算力与数据 contract |
| `freeze_prompt_mask_baselines.py` | 固化 SABM / UNet / DINO / IBIS 基线指针 |
| `run_prompt_mask_static_eval.py` | 六类 prompt 的 patient-level 离线评估 |
| `run_prompt_mask_ibis_baseline.py` | 同 SAM backend 的 IBIS-like greedy click baseline |
| `run_sam2_static_prompt_adapter_finetune.py` | r001/r002 静态 multi-prompt adapter（含 consistency loss） |
| `run_interactive_unet_finetune.py` | 不依赖 SAM3 的 RITM-style 交互 UNet，对照正负 click、当前 mask 和 box |
| `run_dino_guided_prompt_policy.py` | DINOv3 / wall evidence 候选与小型 PromptPolicy |
| `run_sam3_concept_candidate_probe.py` | UltraSAM3/SAM3 concept candidate 合同（非主 mask） |
| `run_prompt_mask_video_benchmark.py` | SAM2 vs SAM3 real-cine 同协议视频 benchmark 脚手架 |
| `run_sam2_native_video_canary.py` | 真实 `SAM2VideoPredictor` external cine canary |
| `run_prompt_policy_sft.py` | GT error trajectory SFT + 可验证奖励项 |
| `run_static_promotion_gate.py` | 静态 promotion gate |
| `run_sam2_tracking_canary.py` | mask-logit carryover 视频 canary 与 deployment manifest |
| `choose_prompt_mask_training_route.py` | 写出 `model_route_decision.json`（旧入口） |
| `freeze_clean_adapter_static_candidates.py` | Clean Adapter：冻结 performance / replay-safe 静态候选 |
| `run_clean_dino_prompt_policy.py` | Clean DINOv3 胃壁 evidence + development-only PromptPolicy |
| `build_dense_cine_annotation_subset.py` | prospective dense-cine 标注子集与 QA 门禁 |
| `run_real_temporal_adapter_gate.py` | 真实相邻帧 temporal 训练门禁（拒绝 photometric 终证） |
| `run_dino_guided_reprompt_ab.py` | fixed box+point vs DINO re-prompt 视频对照 |
| `freeze_clean_adapter_route_decision.py` | Clean Adapter 路线冻结（不切换线上默认） |
| `prompt_mask/` | 协议、prompt、metrics、rewards、policy 共享库 |

### 6.1 Clinical SAM2 loop（自动发现 + 医生纠正）

静态 `crop_ui` mask 为首批强监督；MedSAM2 仅作兼容探针与受控对照；视频只报稳定性，不宣称 temporal Dice。

| 脚本 | 备注 |
|------|------|
| `freeze_clinical_sam2_loop_contract.py` | 冻结患者级 split、纠正 schema、frozen test cohort |
| `build_clinical_loop_static_manifest.py` | 版本化静态训练 manifest（含纠正合约字段） |
| `build_auto_discovery_seed_prompts.py` | YOLO/GT-box 自动发现种子 + abstention |
| `ingest_doctor_mask_corrections.py` | `mask_overrides.json` → QA-gated pending/approved + mask PNG |
| `rank_clinical_loop_review_queue.py` | 下一批评阅队列（患者/年份分层） |
| `probe_medsam2_checkpoint_compat.py` | MedSAM2 权重兼容性探针（不下载） |
| `run_clinical_loop_static_benchmark.py` | SAM2.1 / MedSAM2 / PEFT 候选对照矩阵，`--mode pilot --execute` 可真实跑小规模对照 |
| `run_clinical_loop_correction_finetune.py` | 纠正感知静态 adapter 课程与训练入口 |
| `run_clinical_loop_promotion_gate.py` | 冻结 holdout + 流程指标 promotion（不改线上默认） |
| `collect_clinical_loop_workflow_metrics.py` | 从 reader audit 汇总 workflow metrics |
| `assert_temporal_claims_deferred.py` | 未过 dense cine QA 前禁止 temporal Dice 宣称 |

产物根目录：`experiments/clinical_sam2_loop/`；说明见 `docs/plans/clinical_sam2_loop/`。

`run_sam2_static_prompt_adapter_finetune.py --adaptation-mode context_edge`
implements the PEFT candidate with a frozen image encoder and trainable
multi-scale context-edge depthwise-dilated adapters. `decoder_only` remains
the compatibility default; `full_finetune` is an upper-bound experiment.

全量训练默认 `CUDA_VISIBLE_DEVICES=1`，保留 GPU0 给 `:8767`。

---

## 7. 辅助工具与运维

**用途说明：** 与核心训练无直接耦合的实验室或排障工具。

- `generate_gpu_schedule.py` — 生成 GPU 预约 Excel；说明见同目录 `README_GPU_SCHEDULE.md`（该文档含已验证的调用方式）。
- `inspect_excel.py` — Excel 结构探查。
- `check_sex_col.py` — 临床表性别列等快速检查。

---

## 8. 历史、一次性或与旧环境强绑定的脚本（新人慎作默认入口）

**用途说明：** 下列脚本多含**硬编码绝对路径、旧项目根目录或非本仓库数据布局**，适合审计、迁移或一次性批处理，**不应**在未通读代码与改路径的情况下直接当作当前主线步骤。

| 类型 | 脚本 |
|------|------|
| 旧队列 `process_*` / `process_project` | `process_project.py`、`process_2019_data.py`、`process_2019_project.py`、`process_2019_nac_project.py`、`process_2024_project.py`、`process_2024_nac_project.py` 等 |
| 学生示例子集（硬编码路径） | `prepare_student_dataset.py`、`prepare_student_dataset_v2.py` |
| 视频批量转换（硬编码路径） | `convert_videos.sh` |

若需沿用其中逻辑，建议复制思路到新配置驱动脚本或在新实验目录下重写入口，并走数据治理与实验治理文档中的评审流程。

---

## 8.5 本地多模态 Tool-Controller Agent（离线自进化）

文档入口：`docs/plans/local_multimodal_agent/README.md`。

| 脚本 | 作用 |
|------|------|
| `build_multimodal_agent_dataset.py` | 脱敏 + 患者级 split freeze + cine inventory SSOT |
| `build_agent_traces.py` | 分层 instruction / trajectory / clinical_text |
| `run_multimodal_agent_smoke.py` | JSON 动作 + concept + report 冒烟验收 |
| `run_local_mllm_sft.py` | GPU1 QLoRA SFT（仅 candidate，默认 `--smoke` 只写 records） |
| `run_evolution_replay.py` | baseline/candidate 回放与安全门禁 |

---

## 9. 非脚本文件说明

- `README_GPU_SCHEDULE.md`：`generate_gpu_schedule.py` 的配套说明。
- `extracted_pathology_concepts.json`：概念抽取的示例/中间产物数据，**不是**可执行脚本。
- `visualization_samples.png`：示例图片资源。


## 人机协同 Round2 导出与分析（2026-08-10）

正式阅片协议与冻结契约见 `docs/READER_ROUND2_EXECUTION_RUNBOOK_20260810.md`。常用入口：

1. `build_reader_round2_freeze_tables.py` — 资历模板与病例顺序（已存在 freeze 时需 `--force`）
2. `import_reader_expertise_registry.py` — 导入已填写资历，不改 case-order hash
3. `export_reader_round2_paired_tables.py` — Round1 基线与配对骨架
4. `analyze_reader_audit_events.py --environment research` — research 事件过滤与 completed 病例导出
5. `validate_reader_round2_gate.py` — 临床声称门控（脚手架可用 `--allow-prepared`）
6. `analyze_reader_round2_expertise_uplift.py` — 资历交互 / 安全终点（Round2 空时 blocked）
7. `smoke_reader_round2_research_contract.py` — HMAC / 完成判定离线冒烟
8. `build_autoresearch_results_summary.py` — 汇总进 `pipeline/autoresearch/results/latest/`

产物目录：`docs/clinical_validation/reader_round2_exports/`；总汇总：`pipeline/autoresearch/results/latest/`。正式 `research` 事件还要求 Next 服务配置 `READER_AUTH_PROXY_SECRET`，由认证反向代理注入 `x-authenticated-reader-id` 和 HMAC 签名。
