"""GastricUS MedSigLIP-448 实验包。对照 `GastricUS实验方案.md`。

方案章节 -> 模块:
  2 图像预处理          preprocess.full_frame / expand_roi / assert_processor
  3 冻结 MedSigLIP      encode.load_frozen_encoder / encode_all（缓存 e_full / e_roi）
  4.1 / 4.2 帧内融合    model.ConcatFusion / model.FrameFusion
  4.gate / 4.pair       model.GateFusion / model.PairAttnFusion（对照，非方案原文）
  5.1 / 5.2 / 5.3 聚合  model.MeanViewPool / StatsPool / GatedAttentionPool
  5.mean_u / attn_only  先融合再均值；只要 attention
  6.1 MLP 头            model.PatientHead
  6.2 TabPFN 头         tabpfn_clinical + train --head tabpfn

入口: scripts/run_medsiglip_gastricus.py
默认一次 train = 4.1 concat + 5.3 gated + 6.1 MLP（xlarge）。
更深对照用 --size deep。方案字面宽度用 --size small --no-residual。5.3 维用 --pool-out 64 或 128。
再试融合 / ROI：`--retry-sweep`（gate / pair / mean_u / 15-25 混合，未升格）。
第一阶段边界：`phase1`（McNemar / bootstrap / 分中心 / 层级切点）；`--phase1-seeds` 再训默认和最好格子。
不 import DualBranch / OpenCLIP / DINOv3 / 旧 trainer。
"""
