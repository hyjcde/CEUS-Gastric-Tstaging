# Figures for Lancet Digital Health submission

Place final figures here (PDF or high-resolution TIFF per journal artwork guidelines).

## Suggested figure set

| Figure | Content | Source in project |
|--------|---------|-------------------|
| Fig 1 | Study flow (cohorts, splits, pipeline stages) | `docs/mainline/research_mainline.md` |
| Fig 2 | Example oral contrast-enhanced US with five-layer schematic and ROI | Clinical consensus refs in `docs/archive_refs/` |
| Fig 3 | Pipeline diagram: localisation → segmentation → classification | Stage 1/2 mainline |
| Fig 4 | Patient-level ROC / calibration by split | `results/internal_validation/`, `results/external_validation/` |
| Fig 5 | Confusion matrices (prospective vs external) | Experiment outputs |
| Fig 6 | Grad-CAM vs border alignment (T2/T3 error atlas) | `results/visualizations/error_cases/` |

Formal visualisation style: black background, Times New Roman (`docs/visualization/visualization_standard.md`).
