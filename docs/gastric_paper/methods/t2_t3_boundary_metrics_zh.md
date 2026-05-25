# T2 / T3 边界表现（冻结主线 · mask4ch + clinical22）

实验：`tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301`  
配置：ConvNeXt 双分支 + 预测 mask 第四通道 + 22 维临床，**Agent 默认冻结线**（外部 AUC **0.7326**，前瞻 **0.7455**）。

> 说明：scoreboard 上 **region-aware** 外部宏 AUC 更高（**0.7480**），但 T3 recall 极低、大量 T3 被判成 T2，**不适合作为 T2/T3 边界主模型**。下文指标均指冻结 mask4ch 线。

## 帧级（eval JSON · 混淆矩阵）

| 指标 | 外部 `test_external` | 前瞻 `test_prospective` |
|------|---------------------|-------------------------|
| 四分类宏 AUC | **0.7326** | **0.7455** |
| T2 recall | **20.4%** (43/211) | **9.4%** (3/32) |
| T3 recall | **51.4%** (471/916) | **63.0%** (63/100) |
| T2→T3 误分率（真 T2） | **42.2%** | **28.1%** |
| T3→T2 误分率（真 T3） | **11.0%** | **3.0%** |
| T2/T3 相邻互换占 T2+T3 池 | **16.9%** | **9.1%** |
| 单类 AUC（T2 / T3） | 0.646 / 0.663 | 0.671 / 0.710 |

### 解读（临床可读）

1. **T2 最难**：外部 T2 recall 仅约 **20%**，近半数真 T2 被抬到 **T3**（42%），是主线最大短板。
2. **T3 相对好于 T2**：T3 recall 外部约 **51%**，但仍有约 **11%** 被压回 T2。
3. **前瞻集**：T2 样本少（n=32），T2 recall 更低；T3 recall **63%** 略好于外部。
4. **四分类准确率低 ≠ T2/T3 完全失败**：大量误差进入 T1 / T4+；边界分析应单独看 T2、T3 行/列。

## Grad-CAM（最佳可用主线模型 · mask4ch 四通道）

已为 T2/T3 典型病例生成 Grad-CAM（外部验证子集，每类 6 例）：

- 输出目录：`pipeline/experiments/.../gradcam_t2t3_boundary_external/`
- 组图示例：`docs/mainline/figures/results/t2t3_gradcam_panel_*.png`
- 旧版简图：`docs/mainline/figures/results/t2t3_gradcam_*.png`（若存在）
- 误分例：双 CAM（预测类 + 真值类）；正确例：预测类 CAM
- **检测框约束（默认开启）**：热力图只在 **胃腔检测框 `lumen_box` ∪ 病灶/crop 框 ∪ 预测 mask 外接框** 的并集内显示。
- **组图（默认 `--layout panel`）**：**4×3 等大**；crop_ui + GT + DINOv3 分割 + 双 YOLO；Grad-CAM 默认只在 **病灶 ∪ 病灶–胃腔间壁带** 显示（`--cam-focus lesion_wall`），**不含胃腔积液内部**；`--cam-focus lesion` 仅病灶。输出：`gradcam_*/panels/<T>/<status>/*_panel.png`。

重新生成：

```bash
# 1) 构建子集 CSV（解析外部图路径 + 合并 lumen/crop 检测框）
python scripts/build_t2t3_gradcam_subset.py

# 2) Grad-CAM（默认：框内热力图；加 --no-det-box-mask 可看全图 CAM）
CUDA_VISIBLE_DEVICES=0 python pipeline/scripts/run_4class_gradcam.py \
  --exp-dir pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301 \
  --input-csv pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301/eval/test_external/t2t3_boundary_gradcam_subset.csv \
  --output-dir pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301/gradcam_t2t3_boundary_external
```

## 与 DINO T2/T3 expert 对照（参考）

`dinov3_classification_auc_summary.csv` 中 **T2/T3 expert** 在验证集 patient 级 **t2_t3_auc ≈ 0.81**，但该路与当前 Agent 冻结四分类主线 **未完全对齐**，仅作边界专项参考，不替代主表。
