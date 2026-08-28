# SAM3.1 vs DINOv3 full vs DINOv3 ROI, plus ROI x1.10

Date: 2026-08-28. Research only. Does not replace UNet `segmentation_primary` or public Assist.

Script: `scripts/compare_sam_dino_roi_panel_expand10.py`.

## What this is

Same-style black / Times contact sheets for the three published segmentation rows, then a new **ROI expanded 10%** score on external and prospective.

`x1.10` means the method's **current box** is scaled so final width and height are 1.10 times the current box (center-preserving, clipped to the image). This is the SAM `expand_box` scale, not another `margin_ratio` on the longer side.

| Method | Published prompt | +10% prompt | Dice canvas |
|--------|------------------|-------------|-------------|
| SAM3.1 full-component LoRA run2 | oracle GT box | oracle box x1.10 | full image, patient-mean (registry) |
| DINOv3 last-2 adapter 20260511 | no box | n/a (auto). Extra: Dice **inside** GT box x1.10 | crop_ui full image (SMS) |
| DINOv3 ROI LoRA m025 | GT crop already cut (margin 0.25 / 16) | that crop box x1.10 | letterbox 512 |

Do not write "0.855 beat 0.854". Queues, prompts, and canvases differ.

## Published (unchanged)

| Method | External Dice | Prospective Dice |
|--------|---------------|------------------|
| SAM3.1 run2, oracle box, patient-mean | 0.854 (461 patients / 2812 images) | 0.882 (46 patients / 234 images) |
| DINOv3 full, no box, image-mean | 0.682 (2856 images) | 0.714 (2430 images) |
| DINOv3 ROI m025, image-mean | 0.855 (2856 images) | 0.887 (2430 images) |

Recomputed ROI m025 in this run: external 0.8548, prospective 0.8873. Matches the training manifest.

## ROI x1.10 (this run)

| Method | External | Prospective |
|--------|----------|-------------|
| DINOv3 ROI m025 crop x1.10, image-mean | 0.831 (2856 / 479 patients) | 0.863 (2430 / 502 patients) |
| DINOv3 ROI m025 crop x1.10, patient-mean | 0.823 | 0.859 |
| DINOv3 full, Dice inside GT box x1.10, image-mean | 0.746 | 0.786 |
| SAM3.1 run2, oracle box x1.10, patient-mean | 0.860 (461 patients / 2812 images) | 0.881 (46 patients / 234 images) |
| SAM3.1 run2, oracle box x1.10, image-mean | 0.864 | 0.880 |

ROI +10% **drops** Dice versus the published tight crop (external 0.855 → 0.831, prospective 0.887 → 0.863). The model was trained on m025 crops; a looser window is a distribution shift. A few worst cases recover when the crop was clipping the lesion (see external panel row 2).

SAM oracle x1.10 is nearly flat to slightly up (external patient-mean 0.854 → 0.860, prospective 0.882 → 0.881). A 10% larger box still contains the lesion; SAM can refine. This is milder than the existing 1.2 / 1.5 / 2.0 robustness sweep, which hurt.

DINOv3 full inside GT x1.10 is **not** a new automatic model. The pred is unchanged; only the scoring window shrinks to the expanded GT box, so Dice rises (external 0.682 → 0.746) because background false positives outside the box are ignored.

## Panels

Black background, Times New Roman / Liberation, PNG + PDF.

- `results/visualizations/segmentation/sam_dino_roi_compare_external_eval_20260828.png`
- `results/visualizations/segmentation/sam_dino_roi_compare_prospective_eval_20260828.png`

Columns: crop_ui + boxes (yellow GT, red m025, cyan x1.10), GT, SAM oracle, DINO full auto, DINO ROI m025, DINO ROI x1.10.

Rows: worst / median / best by **ROI m025 Dice**, two patients per bucket.

SAM overlays on the panel use the SMS crop_ui image and an oracle box (not the registry +10% score).

## Reproduce

```bash
python3 scripts/compare_sam_dino_roi_panel_expand10.py --device cuda:0
```

SAM x1.10 needs `http://127.0.0.1:8768` with run2 LoRA loaded. `--skip-sam-full` skips the registry sweep.
