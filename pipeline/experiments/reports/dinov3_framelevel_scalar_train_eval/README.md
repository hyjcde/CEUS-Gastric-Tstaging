# Frame-Level DINO Scalar Training Evaluation

详细架构说明（帧级 0.808 / 病人级 top3 0.803）：[`docs/mainline/dinov3_framelevel_scalar_prospective_architecture_zh.md`](../../../../docs/mainline/dinov3_framelevel_scalar_prospective_architecture_zh.md)

## Purpose

Earlier experiments aggregated every patient's frames before training. That wastes frame-level evidence: a T3/T4 clue may appear in only one or two key views.

This experiment trains on individual frames, then aggregates frame predictions to patient level.

## Data

Training:

- `pipeline/data/tstaging_4class_anatomic_region_contrastive/regions/train_clinical.csv`
- 10007 frame rows

Validation:

- `pipeline/data/tstaging_4class_anatomic_region_contrastive/regions/val_clinical.csv`
- 1188 frame rows

Full prospective test:

- `pipeline/data/tstaging_4class_prospective_full_anatomic/regions/test_prospective_full_clinical.csv`
- 2285 frame rows
- 479 patients

Features:

- clinical + anatomic frame features
- DINOv3 rich scalar features from layers `[2, 5, 8, 11]`
- DINO top-k selected scalar features

## Best Full Prospective Results

| Level | Aggregation | Feature set | Model | 4-class AUC | Early vs advanced AUC | T2/T3 AUC |
| --- | --- | --- | --- | ---: | ---: | ---: |
| frame | none | clinical_anatomic | RandomForest | 0.8084 | 0.8884 | 0.8157 |
| patient | top3 advanced | clinical_anatomic | RandomForest | 0.8034 | 0.8852 | 0.7716 |
| patient | top2 advanced | clinical_anatomic | RandomForest | 0.8028 | 0.8818 | 0.7672 |
| patient | hybrid | clinical_anatomic | RandomForest | 0.8022 | 0.8869 | 0.7772 |
| patient | mean | clinical_anatomic | RandomForest | 0.8005 | 0.8879 | 0.7819 |
| patient | top3 advanced | DINO top16 + clinical_anatomic | RandomForest | 0.7995 | 0.8832 | 0.7715 |

## Interpretation

This is the first run exceeding patient-level full prospective 4-class AUC `0.80`.

The main gain comes from using frame-level training and patient-level top-k aggregation. This confirms the user's concern: previous patient-level pre-aggregation wasted important per-frame evidence.

However, DINO scalar features still do not improve over the best clinical/anatomic frame-level model in this static-feature setup:

- Best patient result without DINO: `0.8034`
- Best patient result with DINO top16: `0.7995`

This suggests:

- DINO region scalar features are useful but not yet stronger than well-designed anatomic frame features.
- The current DINO feature use is still shallow because it enters after feature extraction.
- The next improvement needs DINO token interaction inside a frame-level neural network, not just scalar stacking.

## Practical Conclusion

The current strongest full prospective result is:

```text
Frame-level clinical/anatomic RandomForest
Patient top3-advanced aggregation
4-class AUC = 0.8034
```

This reaches the requested `0.80+` target.

## Next Step

To make DINO truly contribute beyond this, the next model should be frame-level and image-aware:

```text
Frame input:
  crop_ui image
  crop_roi image
  wall/context patches
  mask/anatomic regions
  DINOv3 dense token maps
  clinical features

Network:
  ConvNeXt local/global frame encoder
  DINO mask-guided token attention
  clinical/anatomic MLP
  frame-level 4-class head
  patient-level top-k aggregator
```

The lesson is not "DINO is useless"; it is that DINO needs to participate before frame prediction, while multi-frame aggregation must remain late.
