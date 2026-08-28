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

工作台「自动找病灶」走暖启动 YOLO 框（`scripts/serve_lumen_detection.py` 的 `/api/lesion/detect`，与胃腔 YOLO 同进程 `:8771`），再交给暖启动 SAM 3.1 LoRA 出轮廓。框选里选 DINO 时走暖启动 `scripts/serve_dino_segmentation.py`（`:8773`），不要再为每次框选 spawn DINOv3。

Assist 分类走暖启动 `scripts/serve_reader_analyze.py`（`:8772`），进程内留着良恶性 Dual ConvNeXt 和 T 分期权重。不要再为每次点分析 spawn 冷启动 Python。DINO 画的 mask 和 SAM 画的 mask 同一条辅助分析路径，不替换 Dual 四分类权重。

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
| `compare_sam_dino_roi_panel_expand10.py` | SAM3.1 / DINOv3 全图 / ROI LoRA 拼图，并评 ROI 外扩 10%。 |

---

## 3. 数据治理、临床表与格式转换

**用途说明：** 整理多来源临床表、患者级划分、原始队列预处理与批量裁剪/转换，使数据边界与命名与 `docs/data_governance/` 一致后再进入训练。

| 脚本 | 备注 |
|------|------|
| `organize_dataset_clinical_tables.py` | 将各来源 Excel 临床表整理到 `dataset/tables/` 结构。 |
| `export_clinical_queue_json.py` | 按工作台队列把 `by_source` CSV 解析成 `dataset/tables/by_queue/*.json`，不拼总表。 |
| `run_gastric_next_dev.sh` | 局域网 `:3000` 用 `next dev` 热重载；`:3300` 仍走 standalone。 |
| `reconcile_clinical_tables_20260813.py` | A9 对账：等临床新表落入 `dataset/tables/incoming_clinical_20260813/` 后再跑；无表时只写 registry 快照，不改主表。 |
| `check_clinical_tables_20260814.py` | 08-14 临床重发表 ↔ `patient_master_manifest`；默认同跑媒体完整性。`--skip-llm` / `--skip-media`。 |
| `audit_clinical_table_media_20260814.py` | 按表统计静图/视频；不完整 ID 在 `/data/research/gastric` 全工作站补搜。 |
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
| `align_acc_boost2_to_official_freeze.py` | 把 acc_boost2 `20260531` 表对齐到 freeze `crop_ui`/`crop_roi` 和临床表；产出 overlay，不改产品包。 |
| `build_binary_multicenter_joint_unseen.py` | 良恶性：多中心联合 train/val + 未见中心 `test_external`，写出 `pipeline/data/binary_multicenter_joint_unseen_20260820/`。 |
| `run_binary_multicenter_joint_unseen_20260820.py` | 按该包规模训 ConvNeXt-S（患者级采样 K=5，约 259 step/epoch），再跑未见中心评分。 |
| `build_binary_noshortcut_ab_20260824.py` | 从 20260820 包派生 A（去掉协和）/ B（协和恶性降采样）二分划分。 |
| `run_binary_noshortcut_ab_20260824.py` | 复训 ConvNeXt-B 384 良恶性头；主数字仍是未见中心患者 AUC。 |
| `build_binary_box_mask_pack_20260825.py` | 在 B 包上按医生框 GrabCut 出形状 mask，良恶同一协议。 |
| `build_binary_zmlholdout_clinmask_20260825.py` | 良恶性工作区：B 包 + age/sex，去掉 ZML 重叠患者，写出 `test_zml`。 |
| `run_binary_zmlholdout_clinmask_20260825.py` | Dual + mask4ch + age/sex；先 `--dry-run`。 |
| `run_binary_box_mask_dual_20260825.py` | 双分支：全图+mask4ch / 医生 ROI；学框和形态。 |
| `run_gus_mask2stage_20260826.py` | GUS-Mask2Stage：官方 1062/128/425/485 患者袋。`--train --run-id NAME` 写入 `reports/.../runs/NAME/`；`--resume` 续训。先 `--plan` / `--preflight` / `--smoke`。 |
| `train_t_stage.py` | WADI 简化主线：患者多帧图像 → ResNet18 → 有效帧均值池化 → T1/T2/T3/T4+。固定 development 1062/128，不开放 audit、mask 或临床输入，无早停。默认 K=6、30 epochs；先用 `--device cpu --no-pretrained --dry-run --num-workers 0`，训练用 `--gpu 0 --run-id NAME`。 |
| `eval_t_stage.py` | 冻结 ResNet18 均值池化 checkpoint 的 WADI 描述性审计：患者级 temporal / external ACC、balanced ACC、QWK、各类 recall 与外部逐中心指标。结果不得回流调参。 |
| `tstaging_lab_prepare.py` | 重建 `tstaging_lab/` 三资产物理包和锁定 WADI manifests。 |
| `tstaging_lab_verify.py` | 检查患者数、泄漏、三资产配对，以及 image-only 和 mask/ROI/clinical 两套 lock。 |
| `tstaging_lab_train.py` | 锁定协议训练，只换 `--model-id`。 |
| `tstaging_lab_evaluate.py` | 对冻结 checkpoint 做 dev / prospective / external / unseen 描述性评测。 |
| `tstaging_lab_new_experiment.py` | 从模板新建实验卡片并写入 draft 总账行。 |
| `tstaging_lab_register.py` | 按状态机登记或关闭一次 run。关闭必须填写 disposition。 |
| `tstaging_lab_plot.py` | 从已有 run 的 history / predictions 重绘正式图和 debug 图。 |
| `tstaging_lab_monitor.py` | 只读环境变量的 SwanLab sidecar；默认 disabled。 |
| `tstaging_lab_audit_clinical.py` | 核对 WADI 患者的 clinical-11 覆盖，写出 sidecar。 |
| `tstaging_lab_train_maskroi_clinical.py` | 原 WADI 数据直接训练全图 + mask 形状 + 25% 外扩 ROI + clinical-11 的 ConvNeXt 四分类。 |
| `tstaging_lab_evaluate_maskroi_clinical.py` | 对匹配的四输入 ConvNeXt checkpoint 做验证集和描述性审计。 |
| `tstaging_lab_train_roi25.py` | 只训练 mask 外接框四周各外扩 25% 的 ROI，ConvNeXt-Tiny 四分类。 |
| `tstaging_lab_evaluate_roi25.py` | 对 ROI-only checkpoint 做验证集和描述性审计。 |
| `tstaging_lab_train_roi50.py` | 只训练 mask 外接框四周各外扩 50% 的 ROI，ConvNeXt-Tiny 四分类。 |
| `tstaging_lab_evaluate_roi50.py` | 对 50% ROI-only checkpoint 做验证集和描述性审计。 |
| `tstaging_lab_train_roi25_mask.py` | 训练 25% ROI RGB 加上同一外扩框的二值 mask。 |
| `tstaging_lab_evaluate_roi25_mask.py` | 对 ROI-plus-aligned-mask checkpoint 做验证集和描述性审计。 |
| `tstaging_lab_train_deep_side.py` | 用胃腔框裁深侧残壁带，ConvNeXt-Tiny 四分类。没有框的帧不用。 |
| `tstaging_lab_evaluate_deep_side.py` | 对深侧 checkpoint 做有胃腔框子集上的验证集和描述性审计。 |
| `train_tstage_ordinal_setmil_20260827.py` | Mask + clinical Ordinal Set-MIL：ConvNeXt-Tiny mask 引导空间池化 + 无位置患者 Set Transformer + train-only 标准化的原始临床 11 项 + 分类/有序双头。不读取 `clinical_22`、`*_norm`、区域/SDF/几何缓存；固定 1062/128，无 audit 入口、无早停。支持 `--resume RUN/last.pth`，先跑 `--dry-run`。 |
| `eval_tstage_tent_20260827.py` | 对已训好的 checkpoint 做官方 [DequanWang/tent](https://github.com/DequanWang/tent) 在线 test-time adaptation，不是训练。默认 continual、steps=1、Adam `1e-3`，只更新 normalization affine。ConvNeXt 无 BN 时改更新 LayerNorm。非 dev 必须 `--allow-non-dev`。 |
| `freeze_zml_reader_v150_inputs_20260827.py` | 从完整 zml dump 冻结阅片 150 的医生关键帧、多边形栅格 mask、以及 mask 外扩 25% ROI。不 seek 进 live runtime。 |
| `score_zml_reader_v150_frozen_20260827.py` | 读冻结包评分：T 走现网 L3 和 maskroi25，BM 走 Dual。关闭 Tent，不再现场抽帧。 |
| `plot_zml_reader_v150_tent_20260827.py` | 在冻结 150 例上对 source 与官方 episodic Tent（steps=2）对比，并画出 maskroi 训练曲线和结果图。不是训练。 |
| `plot_zml_reader_v150_doctor_model_agreement_20260827.py` | 按操作医生统计终诊同意/反对模型（最后一次 Accept AI 或按我的判断保存），并与当时展示 AI、冻结 L3/MaskROI/Dual 和金标准对账出图。 |
| `plot_zml_reader_v150_doctor_model_zh_20260827.py` | 医生终诊 vs 模型的精简莫兰迪图，中英各一套：召回、逐例色带、同意/反对、四格。不画 150 张单例图。 |
| `diagnose_gus_o3_decode_20260826.py` | 对 epoch-12 `best_M4_A4_O3` 做 O3 解码尸检：argmax / 0.5 穿越 / 期望分期，以及帧级 Top-K 重合。不训练。 |
| `score_binary_multicenter_unseen.py` | 从实验目录读 `test_predictions.csv`，报患者级 / 中心级指标（主数字用阈值 0.5）。 |
| `build_task_datasets.py` | 重建 `dataset/task_datasets/`：T 分期与良恶性两类建模 CSV。 |
| `audit_task_datasets.py` | 检查 `dataset/task_datasets/` 标签域、字段空值、混标和 split 泄漏。 |
| `build_task_datasets_source_inventory.py` | 对照 freeze / 炎症原图 / 胃炎 raw_decoded，写出 `source_inventory.json`。 |
| `join_reader_v150_to_task_datasets.py` | 把阅片 100 T + 50 良恶性对到 `task_datasets` 和 freeze / 胃炎原图。 |
| `audit_reader_cohort_overlap_20260826.py` | 阅片 150 与官方 train / val 128 / 前瞻 425 / 外部 485 的患者级重叠，以及本轮 case-state。 |
| `build_reader_clip_patient_map.py` | 阅片 150 对 zip / 盘上原视频 / 200 例总表 → 受控目录 `data/staging_review/reader_v150_source_crosswalk/`（含医院号，不进 Git）。 |
| `tnm_nm_label_map.py` | A11 共享库：把病理 pN/pM 归一成 N0/N+、M0/M1；`0.0` 不当空值。 |
| `build_tnm_nm_phase0_splits_20260814.py` | A11：把 N/M 弱标签挂到 Phase 0 `*_clinical.csv`；不训练、不进医生评分。 |
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

包含但不限于：`analyze_wall_penetration.py`、`analyze_wall_strip_statistics.py`、`eval_static_breakthrough_preop_v1.py`（静图术前突破：胃腔+病灶轮廓算 MDAR，病理只作验证）、`eval_outer_wall_continuity_v1.py`（相邻回声外缘 AEOW + 连续性）、`gc_us_outer_wall_continuity.py`、`generate_contact_focus_analysis.py`、`generate_contact_focus_visualization.py`、`generate_curved_wall_band_overlay.py`、`generate_edge_zoom_clustering.py`、`generate_gastric_lumen_dual_overlays.py`、`generate_local_zoom_group.py`、`generate_overlay_overview.py`、`generate_single_case_wall_strip_figure.py`、`generate_t2_t3_local_examples.py`、`generate_wall_neighborhood_examples.py`、`export_wall_proxy_from_lumen.py`、`visualize_wall_strip_examples.py`、`visualize_local_junction_continuity.py`、`visualize_wall_layer_profiles.py`、`visualize_overlays.py`、`regenerate_overlays.py`、`regenerate_overlays_from_json.py`。

病灶感知分层离线 A/B（先排除病灶再聚亮-暗-亮，不定 cT）：`wall_lesion_aware_cluster.py`、`pack_wall_layer_fixture_v1.py`、`eval_lesion_aware_wall_cluster_v1.py`、`eval_lesion_aware_wall_cluster_trad.py`、`render_lesion_aware_wall_cluster_panel.py`、`test_wall_lesion_aware_cluster.py`。传统对照：k-means / GMM / Ward / FCM / 一维灰度 / 一维法向。pack 默认读公网 ZML 走行线并按画线时间抽帧。计划见 `docs/plans/LESION_AWARE_WALL_CLUSTER_20260828.md`。

影像真相 × T 分期 / T-score 草案：`analyze_imaging_truth_tstage_corr.py`（v2）、`analyze_imaging_truth_tstage_corr_v3.py`、`analyze_imaging_truth_paper_metrics.py`、`build_imaging_truth_charts_zh.py`、`draft_tscore_discrete_bins_v1.py`（A4/B6 离散分档 → 总分切点）。

GC-US 轮廓 T-score 特征（morphology / margin / growth）：`gc_us_contour_features.py`（共享库）、`extract_gc_us_morphology_features_v1.py`、`extract_gc_us_margin_features_v1.py`、`extract_gc_us_growth_features_v1.py`、`analyze_gc_us_feature_batch_stats.py`、`eval_gc_us_margin_split_discrimination.py`、`build_gc_us_tscore_feature_pack_v1.py`、`build_gc_us_tscore_coverage_manifest_v1.py`、`build_gc_us_tscore_anatomic_coverage_tables_v1.py`、`predict_gc_us_external_lesion_masks_coverage_v1.py`（补外部/前瞻轮廓覆盖）、`eval_gc_us_tscore_feature_pack_models_v1.py`、`train_gc_us_tscore_shallow_ordinal_v1.py`（浅层序数打分头：ACC / adjacent ACC / PLCC / QWK）、`viz_gc_us_boundary_spicule_assoc_20260815.py`（像素门控毛刺 vs T，出图+关联门禁）、`build_gc_us_spicule_reviewer_html_20260815.py`（毛刺审稿板 HTML，失败优先）、`build_gc_us_tscore_algorithm_html_20260815.py`（当前合理算法的详细说明 HTML）、`run_tabfm_image_score_head_20260815.py`（冻结 ConvNeXt image PCA + featurepack 医生评分列，TabFM 换 MLP concat 头并出 importance）、`run_tabfm_image_score_head_opt_20260816.py`（同类冻结表：TabFM 类别均衡 context / val bias / ExtraTrees blend / 500-epoch FT）、`run_tabfm_feature_ensemble_20260816.py`（尺寸+图像PCA+轮廓特征；树/Boosting/FT/TabFM/OOF stacking）、`run_tabfm_dual_expert_20260816.py`（冻结图像专家 + TabFM 表格专家 + 门控融合，不把 ImageNet PCA 塞进 TabFM）、`run_tabfm_hierarchical_20260816.py`（TabFM 做 T3+ 门控，ExtraTrees 做 T1/T2 与 T3/T4）、`extract_acc_boost2_image_features_20260816.py`（冻结 Phase 0 DualBranch，导出无 clinical concat 的 512 维图像特征）、`run_tabfm_boost2_image_score_head_20260816.py`（主模型 512 维 PCA + 医生评分列，TabFM 换 MLP concat 头并出 permutation importance）、`run_tabfm_full_feature_retest_20260820.py`（全表重测：acc_boost2 PCA + clinical-11 + 医生分 + 轮廓/胃壁，对齐 DualBranch concat）、`run_maskroi_clin10_retrain_20260820.py`（收窄输入重训 DualBranch：mask+ROI+原图融合，临床 10 项、无 Lauren、无缺失旗标）、`run_tabpfn25_maskroi_clin10_20260820.py`（TabPFN-2.5 ICL 头：冻结 mask+ROI 512 维 PCA + clinical-10，不用 Google TabFM）、`run_tabpfn25_raw512_optimize_20260820.py`（去掉 PCA-16，原始 512 维 + Real-TabPFN-2.5，对照 ExtraTrees / 线性头）、`run_maskroi_tabpfnclin_retrain_20260820.py`（TIME 口径重训 DualBranch：图像 mask+ROI，临床改为 TabPFN-2.5 对 clinical-10 的 4 维 OOF 概率）、`run_tabpfn25_fusion_acc80_20260820.py`（目标 ACC 0.80：Lauren 回 TabPFN，冻结 512 维 + clinical-11 融合）、`run_maskroi_clin11_tabpfn_freeze_20260820.py`（冻住 acc_boost2 图像，只训 clinical-11+TabPFN 头）、`run_tabpfn25_gated_t34_20260820.py`（验证集锁定 DualBranch+TabPFN 门控，另加 clinical-11 的 T3/T4 二分类专家）、`run_time_tabpfn_engine_20260820.py`（按 TIME 论文实现整网：冻结 TabPFN-2.5 取 192 维嵌入，冻结 DualBranch 512 维图像，Cat/Sum/Max/DAFT + 线性头）、`run_time_cat_dualbranch_20260820.py`（官方 `tabpfn-extensions.TabPFNEmbedding` K-fold 192 维，TIME-Cat 补丁进 DualBranch，Phase-0 头零填充保 ACC）、`run_typed_expert_tstage_20260816.py`（冻结 512 维按帧 MIL + 尺寸/胃壁/临床/征象分族专家 + 缺失门控；先测帧 oracle 与全表上限）、`run_dual_transformer_tabfm_20260816.py`（帧 Transformer + 缺失感知 FT-Transformer + 冻结 TabFM ICL 先验 + 融合 Transformer）、`plot_gc_us_tscore_feature_triplets_3d.py`、`analyze_gc_us_feature_lasso_shap_triplets_v1.py`、`analyze_gc_us_tscore_latest_lasso_3d_v1.py`、`build_gc_us_tscore_results_html_v1.py`、`build_gc_us_tscore_results_html_zh_v1.py`（最新 feature pack 的 LASSO 稳定性、显著性筛查、3D 分群图、中文特征计算字典与汇总 HTML → `pipeline/data/gc_us_tscore_features_v1/feature_pack_v1/`）。

产品侧方向归一化征象评分（`ccus_t_rubric_v1.4_us`，不改产品切点）：`pipeline/agent/signs/`（schema / direction_growth / wall_gate / scorer）、`pipeline/agent/tools/gc_us_sign_tool.py`、研究校准 `gc_us_tscore_featurepack_v2.py`、患者级验证 `eval_gc_us_sign_scoring_v1.py`（输出 `docs/plans/ccus_t_scoring/sign_scoring_validation_v1/`）。

结果汇总默认入口为 `pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/index.html`，英文版为同目录的 `index_en.html`。

**注意：** 部分脚本内写死了本机字体或目录（例如 `generate_overlay_overview.py` 使用 macOS 字体路径），换环境运行前需自行核对路径。

---

### 4.1 TIME / TabPFN-2.5 / BETA

- `run_beta_m025_phase0.py` — Official ICML 2025 BETA (`external/BETA`) on frozen m025 DINOv3 CLS+GAP (PCA-64) plus Phase-0 clin-11. Research only. Do not replace Assist or TabPFN-2.5. Report: `pipeline/experiments/reports/beta_m025_phase0_20260828/`.

- `run_time_cat_dualbranch_20260820.py` — TIME ([arXiv:2506.00813](https://arxiv.org/abs/2506.00813)): official `TabPFNEmbedding` 192-D OOF tokens plus DualBranch image. `--fusion daft` loads the gastric-pretrained image encoder and trains DAFT. Reuse embeddings with `--reuse-embeddings`. Score external with `--score-external` and an absolute `--exp` path. Architecture: `pipeline/experiments/reports/time_loop_20260820/architecture.html`.
- `run_time_gate_experts_20260820.py` — Train-OOF lock of frozen image linear vs TabPFN-2.5 class probabilities. Train tokens leak; do not use as a lock. Analysis: `pipeline/experiments/reports/time_loop_20260820/ANALYSIS.md`.
- `run_time_ood_gate_20260820.py` — Train Mahalanobis p95 OOD gate: in-domain image, OOD TabPFN. No eval labels.
- `run_time_entropy_router_20260820.py` — After TIME-DAFT DualBranch NaN/wash: pre-registered 0.5 mix, entropy mix, uncertain switch, train-only TabPFN trust. Do not retune on prospective. Report: `pipeline/experiments/reports/time_entropy_router_20260820/`.
- `run_time_t34_geometry_20260820.py` — T3 vs T4+ specialist on mask geometry plus clinical size; train excludes all eval IDs. Hard replace and one-way thickness rule both stay below mix 0.701. Report: `pipeline/experiments/reports/time_t34_geometry_20260820/`.
- `run_time_frame_agg_20260820.py` — Pre-registered DualBranch frame mean / inv-entropy / low-H half / max-conf, then 0.5 TabPFN. Mean stays default. Report: `pipeline/experiments/reports/time_frame_agg_20260820/`. Current architecture: `pipeline/experiments/reports/time_loop_20260820/architecture.html`.
- `run_multiframe_maskshape_nomiss_20260821.py` — From-scratch ImageNet DualBranch + mask ConvNeXt-Small, clinical-11 norms, no missing flags, K=4 bag, NRL aux. Requires `prepare_multiframe_scratch_20260821.py` (drops official 425/485 from train). Ledger: `pipeline/experiments/reports/multiframe_maskshape_nomiss_20260821/DETAILS.html`.
- `prepare_multiframe_scratch_20260821.py` — Clean train/val, complete official 425 / 485 eval pack.

## 5. 可解释性与病理概念

**用途说明：** 基于图像物理特征或临床概念做可解释分析或概念抽取，用于对照主线中的 GradCAM/注意力讨论；多版本并存反映历史迭代，**默认优先阅读最新版本与 `docs/` 中的实验约定**。

- `explainable_features.py`、`explainable_features_v2.py`、`explainable_features_v3.py`、`explainable_features_v4.py` — 可解释特征提取与可视化（v4 文件头注明为改进的边界/梯度等分析）。
- `extract_pathology_concepts.py` — 从 Excel 抽取病理概念特征。
- `inventory_tnm_nm_labels_20260814.py` — A11：盘点 Next 临床 JSON 的 pN/pM 覆盖；不训练、不进医生评分。
- `eval_tnm_backend_heads_20260814.py` — A11：训练结束后收集 `nm_metrics.json` 到 `artifacts/`；不进医生评分。
- `probe_tnm_t_proxy_baseline_20260814.py` — A11：无 GPU。用病理 T 预测 N/M，作为 n_head 必须超过的空模型。
- `run_tnm_frozen_n_probe_20260814.py` — A11 stage 1：冻 Phase 0 DualBranch，导出融合特征，线性探 N/M；不更新 backbone。2026-08-14 闸门未过（val fused 0.791 < T-proxy 0.839），不要启动联合训练。
- `stats_tnm_t_association_20260814.py` — A11：患者级病理 T 与 N+/M1 的率、Wilson 区间、卡方/趋势/OR；不训练、不进医生评分。
- `predict_tnm_frozen_heads_20260814.py` — A11：冻 Phase 0 特征上拟合 N/M 逻辑回归，写出患者级预测；不更新 backbone、不进医生评分。
- `plot_tnm_extended_data_20260814.py` — A11：Extended Data 阴性对照图（N+ 随 T、冻头 vs T-proxy、同一 T 内 AUC）。
- `fit_tnm_regularized_n_head_20260814.py` — A11：冻 Phase 0 特征上按 val N AUC 选正则逻辑回归（fused+clin）；不更新 backbone、不进医生评分。
- `viz_static_wall_dash_6cases_20260814.py` — 静图远端外壁虚线（AEOW 邻壁实线 + 接触弧虚线）；只报 remain/相交，不报 T。`gc_us_wall_dash.py` 是几何库。
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
| `run_sam31_native_video_canary.py` | 真实 SAM3.1 multiplex `propagate_in_video` cine canary |
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

## 6.2 历史相似病例参考（视觉 Embedding 检索）

不是诊断 RAG，不改模型概率。自有 DualBranch 分类头前特征 + FAISS。

| 脚本 | 备注 |
|------|------|
| `extract_visual_similar_case_embeddings.py` | 提取全图 / 病灶 / 融合 Embedding，建 train-only 索引 |
| `retrieve_visual_similar_cases.py` | 病例级检索 CLI（排除同患者） |
| `precompute_visual_similar_neighbors.py` | 预计算 Top-5，供公网 Next 本地秒回，不走 Python spawn |
| `refine_visual_similar_index.py` | 记忆库 PCA 白化 + 多视图拼接 + kNN |
| `eval_visual_similar_retrieval.py` | 同患者 R@5 / 分期纯度等论文诊断，不是临床结论 |
| `test_similar_case_cards.py` | 公网卡片契约：5 张、预览在、病理隐藏、短号不塌缩 |
| `precompute_similar_case_overlays.py` | 历史 ROI 框，归一化后叠在相似病例预览上 |

产物：`pipeline/agent/memory/visual_similar_v1/`。说明见 `pipeline/similar_cases/README.md`。

---

## 7. 辅助工具与运维

**用途说明：** 与核心训练无直接耦合的实验室或排障工具。

- `start_gastric_workstation.sh` — 工作站桌面一键启动：Next `:3000` + SAM2 / SAM3.1 / nnInteractive / 暖启动 YOLO / Assist 分类 `:8772` / 鉴权。`install-desktop` 写入桌面「启动胃超工作站」；`start` / `stop` / `status`。已装 user systemd 时走 `gastric-workstation.target`，并补起 `:8766`。
- `build_public_shell.sh` — 打包公网站轻量启动器。产出 `apps/public_shell/dist/胃超阅片-macos.zip`。Linux 打启动器；Mac 上有 `swiftc` 时带上 WKWebView。说明见 `apps/public_shell/README.md`。
- `build_public_electron.sh` — 打包接公网站的 Electron 窗口（约 100 MB，不装本地模型）。产出 `胃超阅片-electron-windows.zip` / `胃超阅片-electron-macos.zip`，并复制到 Next `public/desktop`。不要把 zip 提交进 git。
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


## MedSigLIP-448 GastricUS（2026-08-21）

全新训练入口，不加载 DualBranch / OpenCLIP / DINOv3 / TabPFN 旧权重。

- `build_tstaging_maincenter_retrospective.py` — 主中心回顾训练/验证 + 前瞻/外部四份建模表
- `build_tstaging_threecenter_joint_unseen.py` — 协和 + 莆田学院 + 中核联合训练，其余外院只评估；不改协和单中心包
- `copy_tstaging_physical_train.py` — copy screened splits into `tstaging/`
- `supplement_tstaging_physical.py` — copy leftover freeze stills so the pack matches official manifests
- `build_tstaging_center_tables.py` — per-center original/cleaned tables and `tstaging/COVERAGE.md`
- `run_medsiglip_gastricus.py` — `prepare` / `encode` / `train` / `ensemble` / `--unfreeze-lora` / `--plan-literal-sweep` / `--clinical preop`
- `run_medsiglip_gastricus_longrun.py` — 解冻最后 16 层 + xxlarge 头 + 冻结 TabPFN TIME-192/四类 OOF；新文件夹，不改默认 CLI
- `sync_gastricus_ledger.py` — copy every MedSigLIP GastricUS SUMMARY into `pipeline/experiments/reports/gastricus_ledger/`
- `pack_gastricus_experiments.py` — refresh the ledger (SUMMARY + logs + master MD) and copy the pack to `~/Desktop` (no weights, no prediction CSVs)
- 说明：`pipeline/medsiglip_gastricus/README.md`；数据：`dataset/task_datasets/t_staging/maincenter_retrospective_v20260821/`
- 从头想训练：把工作目录切到 [`medsiglip/`](../medsiglip/README.md)，在那里跑上面的命令。那是副本，改了不影响主线。

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
9. `discretize_viewing_traces.py --smoke` — 工作台阅片轨迹离散成 inspect 动作（trace2skill）

产物目录：`docs/clinical_validation/reader_round2_exports/`；总汇总：`pipeline/autoresearch/results/latest/`。正式 `research` 事件还要求 Next 服务配置 `READER_AUTH_PROXY_SECRET`，由认证反向代理注入 `x-authenticated-reader-id` 和 HMAC 签名。
