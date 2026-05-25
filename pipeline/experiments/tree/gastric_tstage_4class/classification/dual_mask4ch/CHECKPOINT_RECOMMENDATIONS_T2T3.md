# Recommended checkpoints (T2/T3 anti-overstaging line, 2026-05)

| Use case | Checkpoint | External T2+T3→T4+ | Ext AUC | Notes |
|----------|------------|---------------------|---------|-------|
| **Deploy / Grad-CAM (recommended)** | `.../t2t3_antioverstage_v3_head_finetune_20260522_200526/best_model.pth` | 18.6% | 0.698 | Best T3 recall 63%; single model |
| Lowest overstaging | `.../t2t3_antioverstage_v2_finetune_20260520_151540/best_model.pth` | 18.0% | 0.705 | More T3→T4+ errors than v3 |
| Max AUC (legacy) | `.../t2t3_antioverstage full_20260423_092301/best_model.pth` | 28.0% | **0.733** | Over-confident T4+ |
| **Ensemble (no retrain)** | 30% baseline + 70% v3 probs | **19.3%** | **0.723** | See `ensemble_t2t3_predictions.py --weight-b 0.7` |

Ensemble outputs: `.../tstaging_4class_dual_v2_mask4ch_clinical22_ensemble_baseline0.3_v3_0.7/eval/`

Compare all: `python pipeline/scripts/compare_t2t3_model_variants.py --split test_external`
