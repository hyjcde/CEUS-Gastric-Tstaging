# Figure build manifest

This directory holds the LaTeX figures for `gastric_tstaging_paper_v2.tex`.

## Files

| File | Type | Resolution | Source |
|---|---|---|---|
| `figure1_montage_centers.png` | composite (1 col × 3 rows) | 948 × 3744 | `docs/dataset/{external_centers,external_crop_roi,internal_crop_roi}_montage.png` |
| `figure2_mainline_roc.png` | symlink → `docs/agent_memory/figures/figure2_mainline_roc.png` | 2000 × 1125 | existing |
| `figure3_t2t3_boundary.png` | symlink → `docs/agent_memory/figures/figure3_t2t3_boundary.png` | 2062 × 968 | existing |
| `figure4_ablation_panel.png` | composite (2 × 2) | 2496 × 2096 | `metric_comprehensive_panel.png` (a) + 3 placeholder tiles (b/c/d) for next pipeline iteration |
| `figure5_gradcam_representative.png` | composite (1 col × 5 rows with caption strips) | 1132 × 7019 | 5 gradcam panels (a)–(e) from `docs/gastric_paper/figures/t2t3_gradcam_*.png` |
| `figure6_confusion_panel.png` | static (1840 × 770) | 1840 × 770 | existing |

## Build scripts

All 3 composite scripts are under `_build/`:

- `_build/make_figure1.sh` — 1×3 montage, 24 px gap, 900 px panel width
- `_build/make_figure4.sh` — 2×2 ablation panel; only panel (a) is populated; b/c/d are placeholders
- `_build/make_figure5.sh` — 1×5 gradcam stack with 110 px caption strip per panel

Run from repo root: `bash docs/paper_drafts/tex_v2_ldh/figures/_build/make_figureN.sh`

## Known gaps (next pipeline iteration)

1. **Fig 4 panels b/c/d** are placeholder tiles. The task body asked for "metric_comprehensive_panel + 3 张 ablation (input / loss / fusion)" but the 3 separate ablation PNGs are not on disk. The placeholders carry the axis label and a "Pending" note pointing to the expected next-iteration output path. Swap them in once the ablation runs ship.
2. **pdflatex compile-test** could not be performed (not installed in this env). Run `pdflatex gastric_tstaging_paper_v2.tex` twice locally to verify refs and table widths.

## LaTeX audit (`/tmp/audit_tex.py`)

- Brace balance: OK
- Environment balance: OK (5 table envs, 6 figure envs, 11 captions)
- Cites: 13 distinct keys, 20 bibitems (7 forward refs — intentional)
- Labels: 19 labels, 13 \ref's; 8 unreferenced (5 are appendix labels referenced by `Appendix~S1` shorthand; not a compile error)
- TBD markers: 32 (all inside the ablation table, intentional)
- Result: **PASS** (no ERRORs)
