# Grad-CAM 筛图后测试集指标

- 剔除列表: `/home/hyj/Desktop/gradcam_rejected.csv`
- 实验目录: `/data/research/gastric/GastricTstaging/pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301`
- 生成时间: 2026-05-26T07:48:23.345357+00:00

## 分数据集

### test_external
- 筛前: n=2430, ACC=0.4798, AUC=0.7146, T2+T3→T4+=54.8%
- 筛后: n=1782, ACC=0.6476, AUC=0.7822, T2+T3→T4+=42.7%
- 剔除: 648 张

### test_prospective
- 筛前: n=2430, ACC=0.5531, AUC=0.7761, T2+T3→T4+=55.7%
- 筛后: n=1723, ACC=0.7783, AUC=0.8799, T2+T3→T4+=35.5%
- 剔除: 707 张

## 合并（外部全量 + 前瞻全量）
- 筛前: n=4860, ACC=0.5165, AUC=0.7459
- 筛后: n=3505, ACC=0.7118, AUC=0.8324
- 剔除: 1355 张
