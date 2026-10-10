# 良恶性独立工作区

这里是良恶性二分类重训的单独目录，对应 T 分期那边的 `medsiglip/`。  
影像在仓库根目录的 `良恶性/`，这里只放划分表、配置、报告和实验说明。不要把 ZML 阅片 50 例写进训练集。

## 先读

1. [实验方案.md](实验方案.md)
2. [CASES.md](CASES.md) — ZML 50 例对回原文件夹
3. 数据包：`pipeline/data/binary_zmlholdout_clinmask_20260825/`
3. 主线合同仍在 [良恶性/binary_benign_malignant/SPLIT_POLICY.md](../良恶性/binary_benign_malignant/SPLIT_POLICY.md)

## 目录

```text
benign_malignant/
  README.md
  实验方案.md
  pipeline/data/binary_zmlholdout_clinmask_20260825/   划分 CSV（含 age/sex/mask_path）
  pipeline/configs/                                     本轮 yaml
  pipeline/experiments/reports/                         本轮报告
```

重建数据包（在仓库根执行）：

```bash
python3 scripts/build_binary_zmlholdout_clinmask_20260825.py
```

训练：优先医生 `crop_ui/roi_masks`，炎症无膜时用 GrabCut。主指标是 `test_zml` 患者 Acc，阈值 0.5；`test_external` 仍报未见中心 AUC。

```bash
python3 scripts/run_binary_zmlholdout_clinmask_20260825.py --dry-run
python3 scripts/run_binary_zmlholdout_clinmask_20260825.py --gpu 0
```
