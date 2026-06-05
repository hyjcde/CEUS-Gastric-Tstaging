# wallaux_5ch — 5th input channel (wall evidence) precompute

P0.2 of the gastric T-staging mainline ablation matrix (row 1C, plus
1D retry of P0.2-FU-A).
Converts 4ch (RGB + lesion_mask) inputs into 5ch by appending a
per-pixel wall-evidence map as the 5th channel.

## 1C vs 1D — 两条 5ch 编码（重要）

| | 1C (failed 2026-06-04) | 1D (P0.2-FU-A retry, default) |
|---|---|---|
| 5th channel 物理含义 | per-pixel signed distance from lumen (continuous depth proxy) | per-image breakthrough flag (binary, 0/255) |
| 计算 | `clip(sdf, 0, 32) / 32 * 255` | `1 if (outward_sdf_pixels ∩ lesion) / lesion > 0.3 else 0` |
| uint8 PNG 值域 | 0..255 (连续, 越远离 lumen 越亮) | 0 / 255 (二值) |
| 失败归因 | c3 logit 被 SDF 连续梯度拉高 → T2/T3→T4+ overstage 翻倍 (0.161→0.309) | 待 60-epoch 训练验证 (T-FU-A2) |
| 报告 | `docs/mainline/P0_2_WALLAUX_5CH_RESULTS.md` | TBD（§8.1 pending） |
| precompute 默认 mode | `--channel-mode 1c_sdf` | `--channel-mode 1d_breakthrough_binary`（默认） |

**关键点**: `wallaux_5ch_dataset.py` 读 uint8 PNG 然后 `/255`，所以 1D 的 {0, 255} 二值 PNG 与 1C 的 0..255 连续 PNG 走**完全相同的 5ch 路径**。Trainer 的 `global_in_channels = 5` 和 `wall_init_strategy = "rgb_mean"` 都不需要改。

## Channel value semantics

### 1C (legacy, `--channel-mode 1c_sdf`)

| Region                                       | Value          |
|----------------------------------------------|----------------|
| Background (outside lesion_mask)             | 0 (dark)       |
| Inside lesion AND inside lumen (sdf < 0)     | 0 (dark)       |
| Inside lesion AND outside lumen (sdf ≥ 0)    | clip(sdf, 0, 32) / 32 * 255 (brighter at outer wall) |

The 32 px cap is the normalisation constant from ABLATION_MATRIX.md row 1C.

### 1D (default, `--channel-mode 1d_breakthrough_binary`)

| Region                                       | Value          |
|----------------------------------------------|----------------|
| Background (outside lesion_mask)             | 0              |
| Inside lesion AND breakthrough_ratio ≤ 0.3   | 0              |
| Inside lesion AND breakthrough_ratio > 0.3   | 255            |

`breakthrough_ratio = (sdf > 0 pixels within lesion) / (lesion pixels)`,
是 per-image 单值（不是 per-pixel 阈值化），由
`wall_evidence_tool.breakthrough_mask(lesion, sdf, threshold=0.3)` 计算。

## Files

- `precompute_wall_channel.py` — CLI script. Reads each split's CSV,
  for each row reads image + lesion mask + lumen bbox, computes the
  wall-evidence channel via `wall_evidence_tool.signed_distance_from_lumen`
  + `wall_evidence_tool.breakthrough_mask` (1D) or just the SDF rescale
  (1C), writes a uint8 PNG per row to `<out>/<split>/<sample_id>_wall.png`.

## Usage

```bash
# 1D retry (P0.2-FU-A, DEFAULT since 2026-06-04):
python -m pipeline.mainline.wallaux_5ch.precompute_wall_channel --all

# 1C legacy (failed 2026-06-04) — for diff-comparison:
python -m pipeline.mainline.wallaux_5ch.precompute_wall_channel --all --channel-mode 1c_sdf

# one split at a time (1D by default)
python -m pipeline.mainline.wallaux_5ch.precompute_wall_channel --split train

# small smoke test
python -m pipeline.mainline.wallaux_5ch.precompute_wall_channel --split train --limit 20

# also write a montage SVG (8 random samples per split)
python -m pipeline.mainline.wallaux_5ch.precompute_wall_channel --split val --montage
```

The default `--channel-mode` is `1d_breakthrough_binary`. To reproduce
the 1C failed run, pass `--channel-mode 1c_sdf` explicitly.

## Inputs (per row, in priority order)

1. `image_path` (str, required) — column index depends on the split:
   - train, val, test_external: column 1
   - test_prospective: column 2 (CSV leads with sample_id)
2. `lesion_pred_mask_path` (str, optional) — used as `lesion` source if
   present. For test_prospective this is column 5. For train/val, this
   column is empty, so the script falls back to either the `mask_path`
   column (if any) or whole-image processing.
3. `roi_path` (str, optional) — used as a fallback lumen bbox source.
4. `lumen_bbox` (str, optional, format `x1,y1,x2,y2` or JSON) — explicit
   fallback. None of the current CSVs carry this.

## Lumen bbox fallback chain

If no explicit lumen bbox is available:

1. `forced_output_roi.csv` match by sample_id (test_prospective only —
   stale snapshot from 2026-03-22, only 253/1659 match)
2. ROI image bbox — if `roi_path` is a separate (smaller) crop, the
   whole ROI is treated as the lumen proxy. If the lesion mask is
   available, the bbox is positioned to overlap with the lesion
   centroid (30 % of lesion bbox, centered on centroid).
3. Otsu dark-spot detection — the lumen is the largest anechoic blob.
4. Center 30 % of the image (last-resort heuristic).

## Output

`<out_root>/<split>/<sample_id>_wall.png` — uint8 single-channel PNG,
same height/width as the source image.

`<out_root>/MANIFEST.json` — per-split ok/missing counts, missing
reasons, lesion/lumen source histograms, total elapsed time. Written
on every CLI invocation, so back-to-back `--split X` runs overwrite
the manifest. If you process splits in series, re-aggregate with
`<repo>/scripts/merge_wall_manifest.py` (or just re-run `--all`).

`<out_root>/montage_<split>.svg` — optional 8-sample visual check,
self-contained (PNGs inlined as base64 data URIs). Open in any
browser to verify wall-evidence structure.

## SSOT (used by downstream training T2)

- Output dir: `pipeline/data/tstaging_4class_screened_eval_20260531/wall_channel/`
- Splits: `train`, `val`, `test_prospective`, `test_external`
- Per-row filename: `<sample_id>_wall.png` (sample_id == image_path stem)

## Trainer integration (T-FU-A2)

The 60-epoch training of the 5ch warm-start from the 06-03 acc_boost2
parent is wrapped in `train_wallaux_5ch.py`. It does NOT contain a real
training loop (intentional — `run_experiment.py` is the SSOT for all
100+ experiments in the tree); it only provides:

- `build_model(cfg)` — 5ch `DualBranchClassifier` (global_in_channels=5,
  all other hparams inherited from 06-03 acc_boost2)
- `build_dataset(cfg, split)` — 5ch `WallAux5chDataset` over the
  `wall_channel/` PNGs
- `warm_start_conv1_from_4ch(model_5ch, parent_4ch_ckpt)` — copy
  parent 4ch conv1 weights into 5ch conv1; the new 5th channel is
  initialised by `parent_conv1[:, :3, :, :].mean(dim=1, keepdim=True)`
  (≈ zero contribution at init, gradient-learnable). Strategy
  `wall_init_strategy = "rgb_mean"` is fixed in `config_p02_5ch.json`.
- `verify_only(cfg)` — **no-GPU** smoke test that builds dataset +
  model + warm-start and runs a single forward pass.

### Verify (no GPU, no training)

```bash
# full smoke test (build dataset, build 5ch model, warm-start conv1, forward)
python -m pipeline.mainline.wallaux_5ch.train_wallaux_5ch \
    --config pipeline/mainline/wallaux_5ch/config_p02_5ch.json \
    --verify
```

Expected output (last lines):
```
[verify] sample.global_image shape = (5, 384, 384)
[verify] sample.local_image  shape = (3, 224, 224)
[verify] sample.clinical shape = (22,)
[verify] Smoke forward pass (CPU)...
[verify] logits shape = (1, 4)
[verify] Warm-starting 5ch conv1 from 4ch parent...
[verify]   parent_conv1_key: g_backbone.stem.0.weight
[verify]   new_conv1_key: g_backbone.stem.0
[verify]   parent_shape: [128, 4, 4, 4]
[verify]   new_shape: [128, 5, 4, 4]
[verify]   status: ok_5ch_mean_init
[verify] ALL CHECKS PASSED
```

### Pre-flight dataset/model key contract (SSOT)

`WallAux5chDataset.__getitem__` (and its parent `DualInputDataset`)
return a dict whose keys are:
- `global_image`  — `FloatTensor [4→5, H, W]` (we append wall as 5th)
- `local_image`   — `FloatTensor [3, H, W]`
- `label`         — `int`
- `clinical`      — `FloatTensor [22,]`  *(only when `clinical_cols` is set)*

The forward kwarg names that the 5ch model accepts (per
`eval_wallaux_5ch.py:113-118`, which has been end-to-end verified):
`global_image=`, `local_image=`, `clinical=`. **Do not** use the short
forms `global=`, `local=` — they are not model kwarg names.

### One-shot warm-start artefact (no training)

```bash
# build the warm-started 5ch state dict and write to disk, no GPU needed
python -m pipeline.mainline.wallaux_5ch.train_wallaux_5ch \
    --config pipeline/mainline/wallaux_5ch/config_p02_5ch.json \
    --warm-start \
    --out-ckpt <path>/warmstart_5ch.pth
```

### What train_wallaux_5ch.py does NOT do (left to run_experiment.py)

- the 60-epoch training loop
- per-centre b-acc evaluation
- reporting to `ABLATION_MATRIX.md` and `MAINLINE_FACTS_v2.md`
- hard-negative mining
- final `best_model.pth` save

The actual T-FU-A2 training will be launched by
`pipeline/mainline/wallaux_5ch/run_wallaux_5ch.py` (the harness) which
imports `train_wallaux_5ch.py` for the model+dataset+warm-start and
`run_experiment.py` for the loop. `output_dir` in `config_p02_5ch.json`
is currently a `_PLACEHOLDER` and must be replaced with a real
timestamped run id at launch time.
