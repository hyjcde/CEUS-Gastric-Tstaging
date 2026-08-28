# Project Changelog

This file records material project changes, their validation, and deployment state. Do not add patient identifiers, credentials, tokens, private URLs, or sensitive clinical data.

## 2026-08-29, Thin 3-layer bands on painted frames

- Scope: `scripts/render_wall_layer_thin_bands.py`. Panels `pipeline/experiments/reports/lesion_aware_wall_cluster_v1/thin_bands/`. Sheet `results/visualizations/error_cases/wall_layer_thin_bands_20260829.png`.
- Reason: The four ZML lines already sit on record frames that have lesions on both reader (R) and inference (I). Need a doctor-facing figure: detect the mass on the painted frame, then magnify three thin dark-bright bands inside the yellow corridor. No scatter or contrast charts.
- Key changes: YOLO runs on the painted cine frame and prefers the box nearest the yellow line. That I box excludes lesion pixels from k-means / Ward. Figure is record + yellow line + R contour + I box + an unwrapped, 10x-tall 3-color strip. Does not unlock cT. Does not change the public workbench.
- Validation: All four frames got an I box. P019 exclude-I formed bright-dark-bright on k-means. P008 / P040 / P076 still show three depth-ordered bands.
- Deployment: none (offline figure).
- Follow-up: Same-frame doctor lesion on P019 / P076 would replace the nearby-R overlay. Do not start DINO corridor yet.

## 2026-08-29, Wall-cluster cavity-side diagnostics

- Scope: `scripts/render_wall_cluster_diagnostics.py`. Panels `pipeline/experiments/reports/lesion_aware_wall_cluster_trad/diagnostics/`.
- Reason: P008 and P076 failed every traditional clusterer. Need to see cavity direction and gray-vs-depth, not only cluster color overlays.
- Key changes: Per-case 4-up: anatomy with outward arrows, kept vs dropped scatter, current vs flipped across-profile, method contrast bars. P040 shows a real dark mid-band. P076 keeps the mass because there is no same-frame lesion. Does not unlock cT.
- Validation: Script wrote four case panels plus index. Profile BDB only on P040.
- Deployment: none (offline figure).
- Follow-up: Same-frame lesion on P076 before more clusterers.

## 2026-08-29, Traditional clusterers on ZML wall fixtures

- Scope: `scripts/wall_lesion_aware_cluster.py`, `eval_lesion_aware_wall_cluster_trad.py`, `test_wall_lesion_aware_cluster.py`. Report `pipeline/experiments/reports/lesion_aware_wall_cluster_trad/`. Plan `docs/plans/LESION_AWARE_WALL_CLUSTER_20260828.md`.
- Reason: k-means on gray plus depth only recovered bright-dark-bright on P040. Need to see if GMM, Ward, FCM, or 1D k-means do better on the same exclude-lesion pixels before DINO.
- Key changes: Cluster fit now takes a method. Still fits only outside the dilated lesion, then labels query pixels by nearest center. Methods: k-means, GMM, Ward, FCM, 1D gray, 1D depth. No public workbench change.
- Validation: Synthetic exclude recovers bright-dark-bright for k-means, GMM, Ward, FCM. On ZML fixtures, P040 is bright-dark-bright on all six. P019 only on Ward. P008 and P076 on none.
- Deployment: none (offline probe).
- Follow-up: Inspect cavity-side and line placement on P008 / P076 before adding DINO. Keep Ward as a second seed next to k-means.

## 2026-08-29, Local wall-lab 4-case queue

- Scope: `lib/cohort.ts`, `app/api/patients/route.ts`, `PatientList.tsx`, `QueueTreeSelect.tsx`, `SettingsContext.tsx`, `app/page.tsx`, `lib/reader/queue-access-server.ts`.
- Reason: Iterate wall-layer experiments on P008 / P019 / P040 / P076 without scrolling the public 150.
- Key changes: New queue `reader:local_wall4`. LAN picker shows 本地壁层实验, 4例. Order is T1, T2, T3, T4. URL `?queue=reader:local_wall4`. Public `NEXT_PUBLIC_READER_ONLY` and tunneled public requests get 404. Does not change the scored 150 list. Does not unlock cT.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. Local `/api/patients?queue=reader:local_wall4` returns the four cases.
- Deployment: none. Local `next dev` / LAN :3000 only. Do not deploy this picker to the public doctor site.
- Follow-up: Keep the public 150 default.

## 2026-08-29, Rematch wall fixtures to public ZML strokes

- Scope: `scripts/pack_wall_layer_fixture_v1.py`, `scripts/eval_lesion_aware_wall_cluster_v1.py`. Fixtures `pipeline/data/wall_layer_fixtures/v1/`. Report `pipeline/experiments/reports/lesion_aware_wall_cluster_v1/`. Plan `docs/plans/LESION_AWARE_WALL_CLUSTER_20260828.md`.
- Reason: The first bag used old frozen times and a provisional lesion-axis line. ZML painted real expected lines on the public workbench on 2026-08-28 evening. Clustering must sit on those strokes and those cine times.
- Key changes: Pack reads the public `zml` draft. Frame is extracted at the paint time. Lesion pairs only on the same keyframe or within 0.30 s. P008 wall lives in `mask_overrides`. P019 / P076 stay wall-only because the saved lesion is 4.47 s / 0.55 s away. P040 pairs 1.85 s wall with 1.95 s lesion. Pixel readout ticks are stored as workbench hints, not doctor cT. No public UI change.
- Validation: `python3 scripts/test_wall_lesion_aware_cluster.py`. Re-pack and eval. P040 exclude d=5 formed bright-dark-bright; the full brush did not. P008 same-frame exclude did not. P019 / P076 exclude equals the full brush.
- Deployment: none (offline probe).
- Follow-up: Same-frame lesion on P019 / P076 before claiming exclude-lesion there. Do not start DINO corridor until gray clustering is stable on these ZML lines.

## 2026-08-28, Lesion-aware wall cluster offline A/B

- Scope: `scripts/wall_lesion_aware_cluster.py`, `pack_wall_layer_fixture_v1.py`, `eval_lesion_aware_wall_cluster_v1.py`, `render_lesion_aware_wall_cluster_panel.py`, `test_wall_lesion_aware_cluster.py`. Plan `docs/plans/LESION_AWARE_WALL_CLUSTER_20260828.md`. Fixtures `pipeline/data/wall_layer_fixtures/v1/`. Report `pipeline/experiments/reports/lesion_aware_wall_cluster_v1/`.
- Reason: A doctor expected line may cross the mass. Clustering the full brush or the live 56x28 deepest window lets hypoechoic tumor pixels pull the dark-layer center. Normal-wall layers must be fit outside a dilated lesion mask.
- Key changes: Pack four reader v150 frames (P008/P019/P040/P076) with zml lesion polygons. No saved doctor wall line, so pack writes a provisional lesion-axis stroke and labels `wall_source`. Same-frame arms: live M0, full-brush k=3, exclude-lesion k=3 at dilate 0/3/5/10. Clusters sort by normal depth, not brightness. Does not unlock cT, does not change the public workbench, does not call DINO.
- Validation: `python3 scripts/test_wall_lesion_aware_cluster.py` recovers bright-dark-bright after exclusion on a synthetic strip. Eval wrote per-case JSON and A/B panels. On provisional lines, exclude d=5 formed bright-dark-bright on P019 and P076; the full brush did not. P008 and P040 did not form stable three layers on either arm.
- Deployment: none (offline probe).
- Follow-up: Harvest real `wallPolygon` from the workbench, then re-pack. Do not report agreement until then. Spline extension and four-state continuity wait.

## 2026-08-28, SAM vs DINO contact sheets and ROI x1.10 Dice

- Scope: `scripts/compare_sam_dino_roi_panel_expand10.py`. Report `pipeline/experiments/reports/sam_dino_roi_expand10_20260828/`. Panels under `results/visualizations/segmentation/sam_dino_roi_compare_{external,prospective}_eval_20260828.png`.
- Reason: Need the same black / Times mosaic for SAM3.1 oracle, DINOv3 full-image last-2, and DINOv3 ROI m025, plus an external / prospective score when the current ROI box is scaled by 1.10.
- Key changes: x1.10 is width/height scale on the method's current box (SAM oracle box, DINO m025 crop). DINO ROI Dice stays on letterbox 512. SAM stays on the frozen registry, full image, patient-mean. DINOv3 full also reports Dice inside GT box x1.10; that is a scoring window, not a new model. Not deployable. Do not replace Assist.
- Validation: Recomputed ROI m025 matches 0.855 / 0.887. ROI x1.10 image-mean: external 0.831 (n=2856), prospective 0.863 (n=2430). SAM oracle x1.10 patient-mean: external 0.860 (461 patients / 2812 images), prospective 0.881 (46 / 234). Zero SAM errors. Panels: worst / median / best, two patients each.
- Deployment: none (research figures only).
- Follow-up: Do not rank 0.855 against 0.854. A 10% looser DINO crop drops Dice; SAM 1.10 is nearly flat.

## 2026-08-28, Public workbench: Detailed per-layer wall dock

- Scope: `WallFeatureAnalysisCard.tsx`, `lib/human-assist/wall-layer-medical.ts`, `app/page.tsx`, `lib/reader/layout.ts`. Public Next required.
- Reason: The wall-layer dock only showed a short headline, a tiny profile, and offset buttons. Doctors asked for magnified reading and medical notes on each band, especially serosa.
- Key changes: The dock now has a corridor zoom, a labeled echo profile, and five expandable layer cards (mucosa through serosa) with a local zoom plus echo / look-for / staging notes. Serosa adds the current-frame continuity sentence. Offset still only moves the geometric edge. Does not unlock cT or change Assist.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. Public smoke after deploy.
- Deployment: public Next BUILD `3RRUyNi8v_qYdWxaRYXqg`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: None.

## 2026-08-28, Public workbench: DINO box uses the same path as SAM 3.1

- Scope: `InteractiveSegPanel.tsx`, `app/api/agent/lesion-segmentation/route.ts`, `scripts/serve_dino_segmentation.py`. Public Next required.
- Reason: Choosing DINO made 框选病灶 look dead. The box went through a different busy path, the public edge did not forward DINO to the workstation, and the reply carried a huge overlay PNG. Dragging the box also rebuilt the whole panel on every pointer move.
- Key changes: Box commit always uses the SAM apply path; only the endpoint changes for DINO. Public `/api/agent/lesion-segmentation` now proxies first, same as SAM, and drops `mask_overlay_png` unless asked. Box drag paints the last cine frame plus the rectangle on animation frames, with no React setState. Assist stays the frozen Dual after either mask. Auto-find DINO stays full-image.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. Python compile of the warm DINO service. Public smoke after deploy.
- Deployment: public Next BUILD `NvCWwvhRp6cV8MtVX2v9y`. Smoke: `public_root=200`, `public_clinical=200`. Restarted `gastric-dino-segmentation` so the warm service skips the overlay by default. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: None.

## 2026-08-28, Case open: drop the opening-video veil

- Scope: `InteractiveSegPanel.tsx`, `app/api/reader/media/poster/route.ts`. Public Next required.
- Reason: "正在打开视频" covered the cine until `canplay`. The poster route also tried ffmpeg when a sidecar was missing, which made public case open feel much slower.
- Key changes: No opening overlay or copy. Poster serves only a ready JPEG. Case switch sets the next URL once and does not `load()` twice.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. Public smoke after deploy.
- Deployment: public Next BUILD `eCAC02ZYSzcdOm5ZQwTHX`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.

## 2026-08-28, Case open: first-frame poster, no blank black pane

- Scope: `InteractiveSegPanel.tsx`, `lib/reader/media-url.ts`, `app/api/reader/media/poster/route.ts`. Public Next required.
- Reason: Switching cases unloaded the previous video before the next clip had a decoded frame. Reader v150 cases have no still `image_url`, so the pane stayed black until a large MP4 became playable.
- Key changes: Keep the next video URL on case switch. Show a first-frame poster (`/api/reader/media/poster`). Do not call `video.load()` on an empty src.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. Public smoke after deploy.
- Deployment: public Next BUILD `LMx_BkaiXYTrnb5p-4379`. Smoke: `public_root=200`, `public_clinical=200`. Synced 171 first-frame `*.poster.jpg` into Aliyun reader media. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Cases with `moov` at the end of the MP4 still take longer to become scrubbable; the poster only covers the first paint.

## 2026-08-28, Public workbench: Keyframe select shows only that frame's mask

- Scope: `InteractiveSegPanel.tsx`. Public Next required.
- Reason: Opening a keyframe kept the previous frame's lesion/lumen/wall in live refs, so another frame's mask flashed on the new picture. Tracking overlays within 0.12s could also leak onto a keyframe.
- Key changes: Apply only the selected keyframe's stored contours before seeking. Leaving a keyframe by scrub or arrow-step clears the live overlay. A new keyframe starts empty. Display hides contours unless the cine frame matches the open keyframe. Does not unlock cT or change Assist.
- Validation: `npx tsc --noEmit`. Public smoke after deploy.
- Deployment: public Next BUILD `a0q-0XL1kNHPFpNVDySGj`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: None.

## 2026-08-28, Public workbench: Keep the cine picture while scrubbing

- Scope: `InteractiveSegPanel.tsx`. Public Next required.
- Reason: Dragging the progress bar hid the overlay canvas and let the native video go black on seek. Waiting also put the "opening video" veil on top.
- Key changes: Scrub keeps the last decoded frame on the canvas. Seeking no longer hides that canvas or flips `videoFrameReady` after the first frame. `seeked` paints the new frame. Does not unlock cT or change Assist.
- Validation: `npx tsc --noEmit`. Public smoke after deploy.
- Deployment: public Next BUILD `4Ei3Ui0DuM03hE-zC2GG_`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: None.

## 2026-08-28, Public workbench: Box lesion stays on the current frame

- Scope: `InteractiveSegPanel.tsx`. Public Next required.
- Reason: Tapping 框选病灶 was seeking to a nearby existing keyframe. Doctors need the current cine frame marked as a new keyframe, then they draw the box there.
- Key changes: Arming the box no longer writes `video.currentTime` to another keyframe. Same cine frame reuses that strip item. A different frame adds a new idle keyframe and clears leftover contours from the previous frame. Does not unlock cT or change Assist.
- Validation: `npx tsc --noEmit`. Public smoke after deploy.
- Deployment: public Next BUILD `bX3npdqB_6mUNxSrwj33N`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Space-to-mark still uses the 0.12s duplicate window; only the box tool was changed.

## 2026-08-28, Public workbench: ROI DINO layers in a collapsible dialog

- Scope: `DinoRoiLayerDialog.tsx`, `InteractiveSegPanel.tsx`, `app/api/agent/dino/features/route.ts`, `scripts/serve_interactive_sam_agent.py`. Public Next required.
- Reason: The previous ROI DINO strip sat in the already crowded bottom dock and felt slow. Doctors asked for an openable, collapsible dialog instead.
- Key changes: `ROI DINO层` now opens a modal. Esc, 收起, or a click on the dim overlay closes it. Compact sidecar path skips full-frame PNGs and giant feature vectors, returns small ROI JPEGs, and uses a 512-pixel capture. Same-frame results are cached. Opening the 150-case workbench warms the DINO weights. Draft only; does not unlock cT or change Assist.
- Validation: `npx tsc --noEmit`; Python compile of the SAM helper; public smoke after deploy.
- Deployment: public Next BUILD `nr-eaZ1QJ3qV7PKHntkwO`. Smoke: `public_root=200`, `public_clinical=200`. Restarted `gastric-sam-agent` with DINO already loaded. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: This is still feature inspection, not wall-layer clustering.

## 2026-08-28, Public Assist: DINO box-lesion masker, warm-loaded

- Scope: `InteractiveSegPanel.tsx`, `app/api/agent/lesion-segmentation/route.ts`, `scripts/serve_dino_segmentation.py`, `scripts/systemd/gastric-dino-segmentation.service`, workstation start/install units, `COMPUTE_LINKAGE.md`. Public Next required.
- Reason: The previous public picker isolated DINO from Assist. Doctors need DINO segmentation on the public workbench with no product difference from SAM except the model inside 框选病灶, and the first box must not wait for a cold Python load.
- Key changes: SAM 3.1 / DINO sit inside the box-lesion control. Either mask feeds the same contour-anchored Assist. Dual four-class weights stay frozen. A warm `:8773` process keeps DINOv3 loaded; the Next route prefers that service and only spawns Python if it is down. Opening the workbench pings SAM, DINO seg, and DINO features.
- Validation: `npx tsc --noEmit`; Python compile of the warm service; public smoke after deploy.
- Deployment: public Next BUILD `VgqaovnRzrwukefNe560R`. Smoke: `public_root=200`, `public_clinical=200`. Workstation `gastric-dino-segmentation.service` on `:8773` ready; `:3300` restarted with `DINO_SEG_UPSTREAM`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`; stop the DINO unit to fall back to spawn.
- Follow-up: Do not hot-swap Dual Assist numbers to DINO MLP / TabPFN / BETA unless explicitly asked.

## 2026-08-28, Workbench button: ROI DINO layers on the current frame

- Scope: `InteractiveSegPanel.tsx`, `lib/dino-roi-preview.ts`, `DiagnosisPanel.tsx`, `scripts/serve_interactive_sam_agent.py`. Public Next required.
- Reason: Doctors need to inspect DINOv3 layers 2 / 5 / 8 / 11 near the current-frame lesion/wall ROI. The old region-feature button was hidden on the 150-case rail.
- Key changes: Amber tool `ROI DINO层` after deepest-echo. Sends peri-lesion `roi_bbox` with the existing `/api/agent/dino/features` call. Sidecar crops each layer overlay to that ROI. Dock shows L2/L5/L8/L11 affinity and wall-vs-lesion maps. Draft only; does not unlock cT or change Assist weights.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. Python compile of the SAM helper. Public smoke after deploy.
- Deployment: public Next BUILD `wFmDnSVyPOOyh3q5RhfyJ`. Smoke: `public_root=200`, `public_clinical=200`. Restarted `gastric-sam-agent` for ROI crops. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: This is feature inspection, not wall-layer clustering. Clustering on the same grid is still the research plan.

## 2026-08-28, Public lesion mask picker: SAM 3.1 or DINO

- Scope: `InteractiveSegPanel.tsx`. Public Next required.
- Reason: DINO embedding / wall-layer / Gate C stay research and must not enter frozen Assist. Doctors still need to pick which masker draws the lesion.
- Key changes: The 150-case rail has SAM 3.1 / DINO. A box uses that masker. DINO auto-find is full-image, not an oracle box. Assist still uses the current contour and frozen four-class weights.
- Validation: `npx tsc --noEmit`. Next production build during deploy.
- Deployment: public Next BUILD `e--32grgYSnpGJKCaSXQd`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Do not write DINO ROI Dice as catching SAM; those queues and crops are not aligned.

## 2026-08-28, Plan: DINO wall-layer features bound to the live workbench

- Scope: `docs/plans/DINO_WALL_LAYER_EMBEDDING_20260828.md` (rewritten to reuse public workbench objects).
- Reason: The live root-page workbench already has the serosal trajectory, 1/2/3 interface chips, visibility, anchors, focus points, gray M0 clarify, four-way interrupt chips, keyframe propagate, and classify-only Assist. The gap is that `wall_polygon` is saved but not sent, and the corridor still clusters gray only.
- Key changes: Workbench objects only set the corridor and k. Actual layers must come from clustering gray pixels or DINO tokens on the same 56 x 28 grid, ordered by wall-normal depth, then written back to `wallLayerBands`. Parallel offsets are not layers. M2 template match is only an interrupt helper.
- Validation: Read `InteractiveSegPanel`, `ReaderStudyQueuePanel`, `page.tsx` mask_override, and `_analyze_classify_only`. No new run.
- Deployment: none (docs only).
- Follow-up: Gate 0 on real `doctor_keyframes` lines; then Gate 1 M2 panels.

## 2026-08-28, Gate C DINO mask pooling plus TabPFN-2.5 and BETA

- Scope: `scripts/run_dino_gatec_tab_beta_20260828.py`. Report `pipeline/experiments/reports/dino_gatec_tab_beta_20260828/`.
- Reason: Continue-LoRA overfit and BETA on CLS+GAP stayed below Dual. Next logical step is mask-aligned lesion/peri pooling, then the same table to Logistic/MLP, TabPFN-2.5, and BETA. Mix with frozen clin-11 is val-locked, not prospective-scanned.
- Key changes: crop_ui + mask cropped together (0.25 / 16). Coverage-weighted CLS / GAP / lesion / peri (3072-d). No extra PCA. Do not replace Assist.
- Validation: training started.
- Deployment: none.
- Follow-up: Compare prospective ACC/AUC to frozen MLP 0.541 / Dual 0.678 / mix w=0.3 0.704.

## 2026-08-28, Mix w=0.3 AUC and Dual vs DINO encoding note

- Scope: `docs/references/dinov3/mix_w03_vs_dino_encoding_20260828.md`. Pointers in dinov3 I/O, TabPFN plan, BETA README, references index.
- Reason: Need one place for mix w=0.3 AUC on every split, and to stop mixing Dual 512-d cross-attention with DINO CLS+GAP.
- Key changes: Recomputed 4-class macro OVR AUC from fusion/gated prediction CSVs. Mix w=0.3: val 0.550 / 0.737 (n=140), prospective 0.704 / 0.845 (n=425), external 0.478 / 0.710 (n=456). Dual encoding is GAP plus ROI-query cross-attention to 512-d. DINO encoding is CLS+GAP 1536-d. Mix is late probability fusion, not TabPFN on 512-d.
- Validation: Checked against `tabpfn25_fusion_acc80_20260820` metrics.csv ACC 0.7035 and gated `H_mix_w0.3_ref`.
- Deployment: none.
- Follow-up: Do not promote. Do not describe mix as PCA or as eating Dual 512-d inside TabPFN.

## 2026-08-28, Continue m025 ROI LoRA on T-stage with full-coverage ROI

- Scope: `scripts/train_dinov3_roi_lora_mlp.py` (`--continue-lora`, `--full-coverage-roi`). Report dir `pipeline/experiments/reports/dinov3_roi_lora_mlp/phase0_m025_continue_fullcov_20260828/`.
- Reason: Frozen m025 plus BETA/TabPFN cannot rescue a segmentation embedding. Next gate is to keep m025 LoRA and train T-stage on every labeled patient (mask box or CSV crop when official crop_roi is missing).
- Key changes: Shared `load_roi_rgb` / `row_has_roi`. `--continue-lora` injects LoRA, loads m025 `lora_A/B`, trains LoRA + last-block LayerNorms + MLP. Head lr 1e-4, LoRA lr 5e-5.
- Validation: Early stop epoch 9. Best val patient AUC 0.675 at epoch 4. Train/val/test frames 7874 / 904 / 1659 (val n=140). Prospective ACC 0.522 AUC 0.727 (n=425). External ACC 0.445 AUC 0.697 (n=485). Below first class LoRA 0.567 and frozen MLP 0.541. Train loss fell 1.12 to 0.08 (overfit). Do not promote.
- Deployment: none.
- Follow-up: Do not retry BETA. Next image gate is mask-token pooling (Gate C), not a higher LoRA lr.

## 2026-08-28, BETA full table no PCA and fill missing ROI

- Scope: `scripts/run_beta_m025_phase0.py`. New report `pipeline/experiments/reports/beta_m025_phase0_fulltab_20260828/`.
- Reason: Train coverage was 1064 because official `crop_roi` lookup dropped CSV crops. User asked to include every patient (mask box or existing crop) and not PCA-compress before BETA.
- Key changes: Full 1536-d CLS+GAP plus clin-11 (1547 columns). Missing `crop_roi` uses official crop_ui mask box (0.25 / 16) or the Phase-0 image crop. BETA encoder still maps to ~100-d internally.
- Validation: Train/val/test patients 1234 / 140 / 425 (full Phase-0 labeled rows). Features 1547-d. Best val log-loss epoch 2. Prospective ACC 0.485 AUC 0.780 (n=425). External ACC 0.474 AUC 0.748 (n=485). Better than PCA-512 prosp ACC 0.438; still below Dual 0.678 and mix 0.704. Do not promote.
- Deployment: none.
- Follow-up: Do not replace Assist. Author Drive data still not downloaded.

## 2026-08-28, Run official BETA on frozen m025 embeddings

- Scope: `scripts/run_beta_m025_phase0.py`, Phase-0 patient-mean CLS+GAP, `external/BETA` (unchanged), report under `pipeline/experiments/reports/beta_m025_phase0_20260828/`.
- Reason: User asked to run the on-disk ICML 2025 BETA code against this DINOv3 line, not to swap public Assist.
- Key changes: Wrapper exports frozen m025 embeddings from official `crop_roi`, train-only PCA-512, concat clin-11 (523 columns, Dual-512 plus clinical layout), writes BETA numpy splits, calls official `BetaMethod`. TabPFN-2.5 remains the tabular mainline. Official v1 TabPFN ckpt placed under `external/BETA/model/models/models_diff/` (gitignored).
- Validation: Official BetaMethod, PCA-512 + clin-11 (523-d). Train/val/test patients 1064 / 128 / 425. Best val log-loss epoch 1. Prospective ACC 0.438 AUC 0.740 (n=425). External ACC 0.482 AUC 0.757 (n=485). Below frozen MLP prosp ACC 0.541 and TabPFN-2.5 mix 0.704. Do not promote.
- Deployment: none. No Next / Assist / UNet change.
- Follow-up: Do not replace Assist. Author Drive benchmark data still not downloaded. Encoder selected by log-loss (patience 50), not ACC.

## 2026-08-28, Local BETA / TabPFN Unleashed paper and code

- Scope: `docs/references/beta/`, `docs/references/related_literature/articles/arxiv2025_beta_tabpfn_unleashed*`, `external/BETA` (gitignored clone), pointer in `docs/references/README.md` and the DINOv3 TabPFN plan.
- Reason: Need the ICML 2025 high-dimensional TabPFN adaptation paper and official code on disk.
- Key changes: arXiv `2502.02527` PDF (24 pages). Git clone `LAMDA-Tabular/BETA` at `441e374`. Filed in Zotero `GastricTstaging-review` as `3ZGUVU8N`. No inference or product change.
- Validation: PDF magic `%PDF-1.5`; clone `git log -1` matches upstream.
- Deployment: none.
- Follow-up: Author benchmark data on Google Drive not downloaded. Do not swap public Assist / TabPFN-2.5 for BETA without a gated experiment.

## 2026-08-28, Hide video filename and similar-case essays

- Scope: `ReaderStudyQueuePanel.tsx`, `InteractiveSegPanel.tsx`, `SimilarCaseReferencePanel.tsx`, `AssistLoopStrip.tsx`. Public Next required.
- Reason: The right rail showed the mp4 name and a paragraph about same-type / hard-counter cases before Assist, which doctors do not need.
- Key changes: Video filenames stay off the call panel and footer. Similar-case copy waits until Assist returns cases. Group titles stay; the essays do not. Frozen Assist weights unchanged.
- Validation: `npx tsc --noEmit`. Next production build during deploy.
- Deployment: public Next BUILD `pDtcQGwNmS5sjpi7-KtkK`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: None.

## 2026-08-28, Slim the reader footer status chips

- Scope: `InteractiveSegPanel.tsx`. Public Next required.
- Reason: 病灶待框选, 胃腔可选, and the keyframe-restore line sat in extra footer rows and ate cine space.
- Key changes: Those chips are gone in the 150-case reader. Restoring keyframes is silent. The remaining footer is shorter. Frozen Assist weights unchanged.
- Validation: `npx tsc --noEmit`. Next production build during deploy.
- Deployment: public Next BUILD `FpNbD3gQ3IdFd-LOBkZRn`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: None.

## 2026-08-28, Drop paint essays and slim the wall dock

- Scope: `wall-prompt.ts`, `WallFeatureAnalysisCard.tsx`, `InteractiveSegPanel.tsx`, `ReaderStudyQueuePanel.tsx`, `DoctorTutorialModal.tsx`. Public Next required.
- Reason: The expected-line paragraph and the wall dock repeated the same labels, so doctors had to scan past copy to see the chart.
- Key changes: Live hints are just the line name. The paint banner keeps chips only. The wall dock is one verdict line, remain, a bare echo plot, and the local cut. Frozen Assist weights unchanged.
- Validation: `npx tsc --noEmit`; `npx tsx scripts/test_wall_prompt.mjs`. Next production build during deploy.
- Deployment: public Next BUILD `LazcPq2IxnLkTIHoPObBc`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: None.

## 2026-08-28, Cine scrub bar stays smooth while dragging

- Scope: `CineScrubBar.tsx`, `InteractiveSegPanel.tsx`, `globals.css`. Public Next required.
- Reason: Dragging the ~20–30s cine bar felt sticky. Each pointer sample recorded ops, sought the video, and redrew the overlay canvas.
- Key changes: Pointer-to-time mapping is unchanged. The bar and clock update immediately. Video seek is throttled while dragging and snapped once on release. Overlay canvas and React keyframe state wait until pointer up. Start/end scrub events still record; per-move `cine_scrub` does not. Frozen Assist weights unchanged.
- Validation: `npx tsc --noEmit`. Next production build during deploy.
- Deployment: public Next BUILD `JeJde67_wIRB_DIdqofGu`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Wheel and arrow keys still step one frame.

## 2026-08-28, BM gold shows malignant when T is absent

- Scope: `five-class.ts`, `cases-server.ts`. Public Next required.
- Reason: All 25 malignant BM cases have nature only, no pT. The gold reader treated malignant as missing, so BM048 showed 无病理真值.
- Key changes: Nature-only gold is 良性 / 恶性. If a T label exists it still wins. BM048 / BM048 compact ids both resolve. Frozen Assist weights unchanged.
- Validation: `npx tsc --noEmit`; `npx tsx scripts/test_five_class.mjs`; lookup BM-048 / BM048 / BM-001.
- Deployment: public Next BUILD `ueuAugX5eNew-qKzEg-BY`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: None.

## 2026-08-28, Queue stats use the full 150 and both tasks

- Scope: `StatisticsPanel.tsx`, `queue-review-stats.ts`, `PatientList.tsx`, `page.tsx`. Public Next required.
- Reason: Cohort stats used only the first loaded page (80) and the current task, so 50 BM + 100 T looked like 80 cases, Assist stayed 0, and T-stage bars were missing.
- Key changes: Stats fetch the full queue and all case-states. Progress is overall plus 良恶性 / T 分期. Both doctor-call charts are shown. Assist counts a real run, accept/modify activity, or saved judgment. New analyzes write `assist_run`. Frozen Assist weights unchanged.
- Validation: `npx tsc --noEmit`; `npx tsx scripts/test_queue_review_stats.mjs`. Next production build during deploy.
- Deployment: public Next BUILD `vENJ4LukTsepJ1Vt9Jg7c`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Historical Assist=0 cases stay 0 until they re-run Assist or the activity log already has accept/modify.

## 2026-08-28, Show AI call after analyze

- Scope: `ReaderStudyQueuePanel.tsx`, `ReaderDoctorFirstBar.tsx`, `assist-display-stage.ts`. Public Next required.
- Reason: After Assist finished, the giant AI call showed English Unavailable and 0% because the reader treated the classifier stub as the answer. The title also carried a long parenthetical.
- Key changes: Title is now  AI 判断 . Unavailable / 0% stubs are ignored; the panel reads a real frozen four-class label, then the report display stage. Missing confidence says 置信度未返回 instead of 0%. Frozen Assist weights unchanged.
- Validation: `npx tsc --noEmit`; `npx tsx scripts/test_read_assist_stage.mjs`. Next production build during deploy.
- Deployment: public Next BUILD `RNp8BYeG-nJlKS5zonwuI`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: If a new analyze still has no T1–T4, check the sidecar classifier log; this change only fixes display.

## 2026-08-28, Wall guides stay on the current frame

- Scope: `InteractiveSegPanel.tsx`. Public Next required.
- Reason: Assist sat on the same toolbar row as wall tools. Wall drawings followed the doctor when they scrubbed away. There was no explicit clear or save for the expected-serosa line, and propagate-to-keyframes was still offered.
- Key changes: Assist is on a second toolbar row. The wall propagate button is hidden; auto-propagate no longer copies wall. Wall polygon, bands, paint, focus, and echo overlays hide off the open keyframe, same as the lesion. New 保存胃壁 / 清除胃壁 write or clear only the current keyframe. Frozen Assist weights unchanged.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. Next production build during deploy.
- Deployment: public Next BUILD `ycfXZNSNxuPHmNzN-YdkY`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Restore propagate later if doctors ask. Cine-bar lesion propagate is still there.

## 2026-08-28, Hide paint memo; drop interface caption

- Scope: `ReaderStudyQueuePanel.tsx`, `InteractiveSegPanel.tsx`. Public Next required.
- Reason: The 7-step paint memo was always on the right rail and crowded the call panel. The toolbar caption restated the interface rule in the way.
- Key changes: Memo is a small 备忘 button that opens a compact dialog. The toolbar no longer shows the interface-vs-depth caption. Frozen Assist weights unchanged.
- Validation: Next production build during deploy.
- Deployment: public Next BUILD `EfiZb-lXG6KLcASMjarLx`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: None.

## 2026-08-28, frozen m025 embedding into T-stage MLP

- Scope: research only. Plug m025 ROI LoRA backbone into Phase-0 4-class MLP. No public Next.
- Reason: user asked to connect the new embeddings to MLP. Previous T-stage run trained LoRA+head from 20260511 and overfit by epoch 1.
- Key changes: `scripts/train_dinov3_roi_lora_mlp.py --frozen-embedding` injects LoRA first, loads m025 `backbone.*` including `lora_A/B`, freezes them, trains CLS+GAP MLP only.
- Validation: pending full Phase-0 run `pipeline/experiments/reports/dinov3_roi_lora_mlp/phase0_m025_frozen_20260828`.
- Deployment: skipped. Official `crop_roi` is GT box, not predicted-mask 1.25x.
- Follow-up: fill patient ACC/AUC; do not promote over acc_boost2.

## 2026-08-28, DINOv3 ROI LoRA tighter crop 0.25 finished

- Scope: research only. `dinov3_vitb16_roi_lora_mlp_512_m025_20260828_full` early-stopped epoch 31; best epoch 23.
- Results (ROI letterbox 512, GT-box margin 0.25/16): val 0.8684 (n=754); holdout 0.8665 (n=853); external 0.8548 (n=2856); prospective 0.8873 (n=2430). Above v1 0.75/32 (0.820 / 0.823 / 0.814 / 0.848) but crops are tighter, not a fair architecture gain.
- Validation: trainer finished; `dinov3_run_manifest.json` matches stdout.
- Deployment: skipped. Still GT-box upper bound. Do not replace UNet.
- Follow-up: none for this run.

## 2026-08-28, DINOv3 ROI LoRA tighter crop 0.25

- Scope: research only. Rebuild GT lesion-crop with `margin_ratio=0.25`, `min_margin=16`, then same last-4 LoRA + Dice trainer.
- Reason: v1 0.75/32 crops left too much context; user asked to test the tighter 0.25 setting shown on the external-6 compare panel.
- Key changes: `data/processed/sms/gt_lesion_crop_upper_bound_v2_m025` (v1 kept), `configs/segmentation/dinov3/vitb16_roi_lora_mlp_512_m025.yaml`. Run: `dinov3_vitb16_roi_lora_mlp_512_m025_20260828_full`.
- Validation: pending prepare + full train. Compare to v1 LoRA holdout/ext/prosp 0.823 / 0.814 / 0.848.
- Deployment: skipped. Still GT-box upper bound, not deployable.
- Follow-up: fill Dice when the run ends.

## 2026-08-28, DINOv3 ROI LoRA seg finished

- Scope: research only. `dinov3_vitb16_roi_lora_mlp_512_20260828_full` early-stopped epoch 30; best epoch 22.
- Reason: fill locked Dice into the I/O note and registry after the full run ended.
- Results (ROI letterbox 512, GT-box crops): val 0.8195 (n=754); holdout 0.8225 (n=853); external 0.8144 (n=2856); prospective 0.8482 (n=2430). Above frozen GT-crop 20260515 (0.800 / 0.790 / 0.830).
- Validation: trainer exit 0; `dinov3_run_manifest.json` and report README match stdout.
- Deployment: skipped. Not deployable (GT boxes). Do not replace UNet.
- Follow-up: none for this run.

## 2026-08-28, DINOv3 ROI LoRA I/O: letterbox and LoRA

- Scope: docs only. Front sections in `docs/references/dinov3/roi_lora_io_20260828.md`.
- Reason: val mosaics look square; need to record that disk crops stay native size and only `letterbox_pair` pads to 512, plus how the in-house `LoRALinear` is injected.
- Validation: checked against `letterbox_pair` / `inject_lora` / `LoRALinear` and `vitb16_roi_lora_mlp_512.yaml`.
- Deployment: skipped.
- Follow-up: unchanged; wait for holdout / external / prospective Dice.

## 2026-08-28, DINOv3 ROI LoRA I/O note

- Scope: docs only. `docs/references/dinov3/roi_lora_io_20260828.md` lists every input and output for the ROI LoRA seg run and the earlier T-stage mix-up.
- Reason: the two runs share "ROI LoRA" in the name but one is CE classification and one is Dice segmentation.
- Validation: paths and counts checked against `gt_lesion_crop_upper_bound_v1/dataset_manifest.json` (13515) and the live trainer/config.
- Deployment: skipped.
- Follow-up: fill final holdout/external/prospective Dice into the note when the 20260828_full run ends.

## 2026-08-28, DINOv3 ROI LoRA segmentation (Dice)

- Scope: rebuild ROI segmentation trainer. Research only. No public Next.
- Reason: The 16:00 run was T-stage classification on Phase-0 `crop_roi` (7874 frames, CE, ~5 min). User asked for ROI LoRA segmentation and Dice. Old `run_dinov3_segmentation.py` trainer is gone.
- Key changes: `scripts/train_dinov3_roi_lora_seg.py`, `configs/segmentation/dinov3/vitb16_roi_lora_mlp_512.yaml`. Data: `data/processed/sms/gt_lesion_crop_upper_bound_v1` (7376 train crops from crop_ui + roi_masks, GT box expand). Init 20260511 backbone. Last-4 LoRA r=8 + MLP decoder. Loss 0.5 Dice + 0.5 BCE.
- Validation: smoke 24/12, 1 epoch, val Dice 0.56, exit 0.
- Deployment: skipped. Full run: `experiments/segmentation/dinov3_vitb16_roi_lora_mlp_512_20260828_full/`. Compare to frozen GT-crop Dice 0.80/0.79/0.83. Not deployable (GT boxes).
- Follow-up: wait for holdout / external / prospective Dice. Do not promote over UNet fulldata.

## 2026-08-28, DINOv3 ROI LoRA + MLP training

- Scope: research T-stage trainer only. No public Next / Agent / UNet change.
- Reason: Skip BETA. Train a ROI DINOv3 with LoRA and a two-layer MLP on the existing full-frame segmentation checkpoint.
- Key changes: `scripts/train_dinov3_roi_lora_mlp.py`. Phase-0 CSVs; official `crop_roi` remap (legacy `roi_path` is missing on disk). Init `20260511` last-2 adapter. Last 4 blocks LoRA r=8 on qkv/proj. Letterbox 512, no stretch.
- Validation: smoke 16/8/8 then full Phase-0. Early-stop epoch 6; best val patient AUC 0.727 at epoch 1. Locked tests: prosp n=425 ACC 0.567 / AUC 0.763; ext n=485 ACC 0.433 / AUC 0.709. Below acc_boost2 prosp ACC 0.678.
- Deployment: skipped (training). Report: `pipeline/experiments/reports/dinov3_roi_lora_mlp/phase0_20260828_full/`.
- Follow-up: LoRA overfit after epoch 1. Next useful step is frozen-backbone Linear/MLP on the same ROI, not more epochs. Do not promote.

## 2026-08-28, DINOv3 ROI then TabPFN plan

- Scope: research plan only. Maps the proposed full-image → ROI → LoRA → mask pooling → BETA sequence onto repo assets.
- Reason: BETA is not implemented; the existing DINOv3 checkpoint is a segmentation backbone; Phase-0 splits and TabPFN-2.5 already exist.
- Key changes: `docs/references/dinov3/roi_lora_tabpfn_plan_20260828.md`. Tabular ICL is TabPFN-2.5. First gate is frozen Linear on crop_ui vs ROI 1.0/1.25/1.5.
- Validation: cross-checked against the 2026-08-28 DINOv3 inventory, Phase-0 split contract, and `tabpfn25_fusion_acc80_20260820` (prospective mix ACC 0.704).
- Deployment: skipped (docs only).
- Follow-up: do not start LoRA, 512-d compression, and TabPFN in one run. Do not replace public Assist.

## 2026-08-28, DINOv3 experiment inventory

- Scope: docs-only inventory of embedding, segmentation, and MLP/tabular DINOv3 runs. No product, Agent, or public Next change.
- Reason: experiment trees are split across `experiments/segmentation/` and `pipeline/experiments/reports/`; registry only lists the anatomic adapter.
- Key changes: `docs/references/dinov3/experiment_inventory_20260828.md` records training view (`crop_ui` full frame, not lesion ROI), Dice/AUC, smoke vs full, and promotion status.
- Validation: numbers checked against `evaluation/overall_summary.md` and report `README.md` / `summary.json`.
- Deployment: skipped (docs only).
- Follow-up: do not promote DINOv3 over UNet fulldata from this inventory.

## 2026-08-28, Doctor T is not a model input

- Scope: Assist gate, headline, coarse anatomic screen, analyze research gate, wall-prompt, tutorial. Public Next required. Analyze Python wall-draft wording.
- Reason: Requiring T1–T4 before Assist, then rewriting the headline from an adjacent-pair lock, made the model look like it was echoing the doctor.
- Key changes: Assist runs after a lesion box. Giant AI call is the frozen four-class only. Coarse screen is clear-shallow / clear-outer / unclear, not a T call, and is not a core-model input. Doctor T stays as an independent record for later comparison. Adjacent lock no longer rewrites the headline. Analyze no longer requires initial_judgment. Frozen Assist weights unchanged. Wall draft still does not unlock definite cT.
- Validation: `npx tsx scripts/test_wall_prompt.mjs`, `test_adjacent_stage_lock.mjs`, `test_wall_layer_interrupt.mjs` in `apps/gastric_scan_next`. `npx tsc --noEmit` exit 0.
- Deployment: public Next BUILD `yK43mhwQm7TUVvAyai61K`. Smoke: `public_root=200`, `public_clinical=200`, `public_harmony=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Doctor-prior fusion is a later experiment. Do not use the same doctor's T as both input and gold.

## 2026-08-28, Expected serosal trajectory prompt

- Scope: reader wall paint, adjacent lock copy, tutorial, T-staging memo, `wall-prompt.ts`, interrupt verdicts. Public Next required.
- Reason: Training has lesion masks and T labels but no wall labels. The doctor line must be an anatomical prior, not a continuity answer. Abstract 1/2/3 layer chips invited circular T4 painting.
- Key changes: Toolbar is Serosa / MP / Shallow. Paint is one expected trajectory through the suspicion zone; doctors are told not to stop at a suspected break. Analysis-focus clicks (max 3) are look-here points, not breach marks. Visibility is clear / blurry / not seen. Verdicts are continuous / suspected / interrupted / cannot judge. Not seen is not interruption. Frozen Assist weights unchanged. Wall draft still does not unlock definite cT. Protocol: `docs/meetings/2026-08-28_浆膜预期走行线协议.md`.
- Validation: `npx tsx scripts/test_wall_prompt.mjs`, `test_wall_layer_interrupt.mjs`, `test_adjacent_stage_lock.mjs` in `apps/gastric_scan_next`. `npx tsc --noEmit` exit 0.
- Deployment: public Next BUILD `A7HodMzeT4ph7rUqOMj6Y`. Smoke: `public_root=200`, `public_clinical=200`, `public_harmony=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Do not merge these strokes into the same 150-case train. Path-level test-time reasoning and a later fusion head stay on a separate development set.

## 2026-08-28, Assist-loop demo page

- Scope: public Next `/loop-demo` (browser URL `/workbench/loop-demo`), Header entry, live critic/EXP/rank cues on the 150-case rail.
- Reason: The retrieve / critic / one-repair / candidate-memory loop was already live but invisible. Need a scripted T2/T3 case that shows locked probabilities, a thin critic, REF-E5 rising 5 to 2, and an EXP candidate that does not enter the neighbor table.
- Key changes: `AssistLoopDemo` auto-plays DEMO-T2T3. `EvidenceFusionReport` prints critic adequacy. Accept/modify shows an EXP receipt. Similar-case refine shows rank moves. Public proxy allows `/loop-demo` after the `/workbench` strip.
- Validation: LAN Playwright: critic, REF-E5 5→2, EXP-DEMO-T2T3, candidate. Public `/workbench/loop-demo` 200, HTML BUILD matches. `public_root` / `public_clinical` 200. Live rail note shows critic sufficient / skip when evidence is enough.
- Deployment: `bash scripts/deploy_public_next.sh` BUILD `KCJDHFNc-SldKmdyJ9u5U`. Hard-refresh http://47.106.33.102 then open 闭环演示. Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: EXP rows stay `candidate`. Do not call this self-evolving. Do not rebuild the neighbor table from the demo.

## 2026-08-28, Gold labels for zml, admin, and test

- Scope: `gold-reveal-access.ts`, `/api/patients/gold`, patients list, `CaseGoldReveal`, workbench header and case list. Public Next required.
- Reason: zml, admin, and test need to see pathology gold on every reader case. The public video workbench had hidden the gold control.
- Key changes: Those three accounts see gold on the current case and as a list chip. Other accounts get 403 on the gold API and no label in the case list. Frozen Assist weights unchanged. Wall draft still does not unlock definite cT.
- Validation: `npx tsx scripts/test_gold_reveal_access.mjs` in `apps/gastric_scan_next`.
- Deployment: public Next BUILD `GdOG31ww6_mKfFgI39PNh`. Smoke: `public_root=200`, `public_clinical=200`, `public_harmony=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Do not use gold to filter similar cases.

## 2026-08-28, Doctor reader flowchart (draw.io)

- Scope: `docs/product/医生阅片流程图.drawio`, pointers in `DOCUMENT_MAP.md`, `docs/apps/gastric_scan_next/README.md`, and `apps/gastric_scan_next/README.md`.
- Reason: Need one product-facing picture of the live public reader path, not the old HTML pack or research Agent workbench.
- Key changes: Two-page draw.io. Page 1 is login through save-and-next and report confirm. Page 2 is adjacent-stage lock, wall draft, Assist headline, similar cases, guideline note, and evidence contrast. Steps follow `DoctorTutorialModal.tsx` and `ReaderStudyQueuePanel.tsx`.
- Validation: XML well-formed, no middle-dot, two diagrams present.
- Deployment: None. Docs only.

## 2026-08-28, Pointer-mapped cine scrub bar

- Scope: `CineScrubBar.tsx`, `cine-time.ts`, `InteractiveSegPanel.tsx`, `globals.css`. Public Next required.
- Reason: The native range slider jumped and lagged the pointer. Doctors still could not drag to the frame they wanted.
- Key changes: Thick track and a large thumb. Pointer X maps straight to time, so the bar moves with the hand. Video seek is coalesced to the next frame. Wheel / arrows still step one cine frame. Frozen Assist weights unchanged.
- Validation: `npx tsx scripts/test_cine_time.mjs` in `apps/gastric_scan_next`.
- Deployment: public Next BUILD `n1A9AvUfihKjuiAuv1V0E`. Smoke: `public_root=200`, `public_clinical=200`, `public_harmony=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Doctor still accepts W4 tomorrow evening.

## 2026-08-28, ROI expanded 50% and ConvNeXt-Small on that crop

- Scope: train locked `roi50_only_v1` as `convnext_tiny_roi50` / `roi50_v1`, and add `convnext_small_roi50` / `small_v1` as the backbone comparison.
- Reason: deep-side crops did not beat ROI25. Next one-factor is a wider lesion ROI, then a larger network on the same crop.
- Validation: Tiny `roi50_v1` and Small `small_v1` both best validation exact ACC 0.5938 at epoch 5 (T2 recall 0), tied with ROI25. Tiny prospective 0.4565, Small 0.4424. Both overfit to train about 0.99.
- Deployment: None. Research training only.

## 2026-08-28, Workbench fullscreen; light launcher starts fullscreen

- Scope: `Header.tsx`, profile copy, Mac/Windows light launchers. Public Next required.
- Reason: Electron is a second Chromium and feels slower. Doctors asked whether the frontend is frozen, and whether the browser can go fullscreen.
- Key changes: Header has a Fullscreen button. Light launchers pass `--start-fullscreen`. Electron still only loads the live public URL; it does not bundle Next. Frozen Assist weights unchanged.
- Validation: Next production build during deploy.
- Deployment: public Next BUILD `EG6JP8zYPoaHKmCqk5hV9`. Smoke: `public_root=200`, `public_clinical=200`, `public_harmony=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Prefer the light launcher or Chrome/Edge when speed matters.

## 2026-08-28, Frame-step seek for the cine bar

- Scope: `cine-time.ts`, `InteractiveSegPanel.tsx`, tutorial and T-staging memo. Public Next required.
- Reason: The 8-27 todo W4 still said the seek bar jumped too far. A short range slider cannot land on one frame by drag alone.
- Key changes: Wheel or arrow keys step one cine frame. Pause snaps to the nearest frame. Drag stays coarse. Frozen Assist weights unchanged.
- Validation: `npx tsx scripts/test_cine_time.mjs` in `apps/gastric_scan_next`.
- Deployment: public Next BUILD `9Ar0vz8wTsSXgo1EExwi3`. Smoke: `public_root=200`, `public_clinical=200`, `public_harmony=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Doctor still accepts W1–W6 tomorrow evening.

## 2026-08-28, Harmony live window shell

- Scope: `apps/public_shell/harmony/`, `scripts/build_public_shell.sh`, Header / profile / tutorial download links. Public Next required.
- Reason: The Harmony pack has to be a window shell of the public site. A static frontend copy would miss later Next updates.
- Key changes: Zip ships `shell.html` (iframe + 硬刷新) and an ArkTS WebView project that only loads http://47.106.33.102 . No Next build inside the zip. Avatar menu and profile offer the download. This machine cannot sign a HAP.
- Validation: `bash scripts/build_public_shell.sh` then `apps/public_shell/scripts/test_public_shell.sh`. Zip asserts live URL, 硬刷新, and no `.next`.
- Deployment: public Next BUILD `Czsa2ZvuNMlDZsF8vhNBl`. Smoke: `public_root=200`, `public_clinical=200`, `public_desktop_mac=200`, `public_harmony=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Signed HAP still needs DevEco on a machine with Huawei credentials.

## 2026-08-28, Stop inventing wall layers after boxing

- Scope: `InteractiveSegPanel.tsx`, `wall-extension.ts`, `wall-pixel-extend.ts`. Public Next required.
- Reason: The meeting replaced「自动延长分层」with 1/2/3 and painting from adjacent wall. Boxing a lesion still auto-joined a 3-layer wall through the mass, and the old button remained.
- Key changes: Lesion auto-seg no longer paints a wall. One-click join needs two flanks or an already painted wall. The Auto-extend button is gone. Copy tells doctors to start on adjacent visible wall. Frozen Assist weights unchanged. Wall draft still does not unlock definite cT.
- Validation: `npx tsc --noEmit` exit 0. `test_wall_extension.mjs` including `canAutoJoinWall`.
- Deployment: public Next BUILD `Uyq0rHPPX8yVefw7LWp1y`. Smoke: `public_root=200`, `public_clinical=200`, `public_desktop_mac=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Doctor tries tomorrow evening.

## 2026-08-28, Wall report names thinning and local echo

- Scope: `analyze_case_lib.py`, `InteractiveSegPanel.tsx`, `assist-judgment-prose.ts`. Public Next required so the request carries `wall_ticks`; analyze already tunnels here.
- Reason: The transcript asked the draft report to name 黏膜浅层变薄, 固有肌变薄, blur, and peri-lesion ROI. Interrupt-only sentences still omitted those ticks.
- Key changes: Painted-layer ticks and deepest-band echo go into contour context, judgment signs, and the report side channel. Peri-lesion ROI is quoted as local, not a full-frame crop of the frozen classifier. Wall ticks stay stripped from the late-stage gate. Frozen Assist weights unchanged. Wall draft still does not unlock definite cT. P1 one-pager is `docs/meetings/2026-08-27_论文叙事一页.md`.
- Validation: `npx tsc --noEmit` exit 0. `test_adjacent_stage_lock.mjs` and `test_research_stage_gate.py` ok, including thinning / local-echo draft.
- Deployment: public Next BUILD `I88_6iqAIlaLbOGxuP-WC`. Smoke: `public_root=200`, `public_clinical=200`, `public_desktop_mac=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Doctor tries tomorrow evening. Harmony, painted-wall retrieve, and merging new walls into the same 150-case train stay later.

## 2026-08-28, Guideline text follows the lock headline

- Scope: `assist_judgment.py`, `evidence_fusion.py`, `ReaderStudyQueuePanel.tsx`, `assist-judgment-prose.ts`, `DoctorTutorialModal.tsx`. Public Next required; analyze already tunnels here.
- Reason: After a T1/T2 or T3/T4 lock the giant AI call was already in-pair, but guideline explanation and evidence fusion still lectured from frozen four-class T4 and T4-seeded serosa signs.
- Key changes: `original_top1` is the lock headline. Frozen four-class goes as `frozen_top1` contrast only. Wall draft fills `layer_structure` / `serosa_change`; a frozen T4 serosa seed is dropped after a non-T4 lock. Guideline retrieval uses the headline, not T4. Tutorial says lock and paint wall first. Frozen Assist weights unchanged. Wall draft still does not unlock definite cT.
- Validation: `npx tsc --noEmit` exit 0. `test_adjacent_stage_lock.mjs`, `test_evidence_fusion.mjs`, `test_llm_info.py` AssistJudgmentLockTest ok.
- Deployment: public Next BUILD `xcO1OxE54mP6JMDVgvXga`. Smoke: `public_root=200`, `public_clinical=200`, `public_desktop_mac=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Doctor tries tomorrow evening. Harmony, painted-wall retrieve, and merging new walls into the same 150-case train stay later.

## 2026-08-28, Wall draft is report-only, not a T4 unlock

- Scope: `analyze_case_lib.py`, `InteractiveSegPanel.tsx`, `ReaderStudyQueuePanel.tsx`. Public Next required for the request payload; analyze already tunnels here.
- Reason: Painting a wall wrote「浆膜中断」into contour_context. The late-stage gate treated that as definite serosa breach and could keep fusion at T4. The report also ignored multi-frame interrupt.
- Key changes: Wall draft fields are stripped before the late-stage gate. Report and supporting evidence now quote 1/2/3 layers, interrupt chips, and keyframe continuity as a side channel. Frozen four-class probabilities unchanged. Assist copy asks for lock and wall first, but does not block a four-class run.
- Validation: `npx tsc --noEmit` exit 0. `test_research_stage_gate.py` including wall-draft-does-not-unlock-explicit-late.
- Deployment: public Next BUILD `7g_FyvSq4MgaBE78MQX7n`. Smoke: `public_root=200`, `public_clinical=200`, `public_desktop_mac=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Wall draft still does not unlock definite cT.

## 2026-08-28, Sculpt wall bands, recheck after propagate, real cine fps

- Scope: `InteractiveSegPanel.tsx`, `cine-time.ts`, `wall-layer-interrupt.ts`, `doctor-keyframes.ts`, `keyframe-propagate.ts`. Public Next required.
- Reason: The transcript still needed doctor-scale edits on imaginary layers, interrupt re-check on every copied keyframe without opening each one, and frame numbers from the real cine rate instead of a hard 25 fps.
- Key changes: Imaginary layer curves can be dragged after zoom; the new line re-samples interrupt. Propagate shifts those curves and seeks each dest frame to re-check on that frame's pixels. Progress and keyframe labels snap fps to 15/20/24/25/30 after a few decoded frames. P3 one-pager is in `docs/meetings/2026-08-27_博后分工一页.md`. Frozen Assist weights unchanged. Wall draft still does not unlock definite cT.
- Validation: `npx tsc --noEmit` exit 0. `test_cine_time.mjs`, `test_wall_layer_interrupt.mjs`, `test_doctor_keyframes.mjs`, `test_adjacent_stage_lock.mjs` ok.
- Deployment: public Next BUILD `yGONsjzUps1CzzuvZW_Mi`. Smoke: `public_root=200`, `public_clinical=200`, `public_desktop_mac=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Harmony still later. Native Apple-silicon Electron zip still later.

## 2026-08-28, Adjacent lock is the Assist headline

- Scope: `ReaderStudyQueuePanel.tsx`, `InteractiveSegPanel.tsx`, `assist-judgment-prose.ts`, `wall-layer-interrupt.ts`, `mask-override.ts`. Public Next required.
- Reason: After a T1/T2 or T3/T4 lock the giant AI call still showed frozen four-class T4. Bright-dark-bright also missed dim TAUS serosa. The analyze payload still sent a tight lesion box instead of peri-lesion ROI.
- Key changes: Locked pair becomes the headline and the Accept target; frozen four-class stays as a small contrast. Interrupt is relative, not an absolute white threshold. Assist gets peri-lesion ROI plus extra-lesion / wall context; frozen weights unchanged. Opening a propagated keyframe re-samples that frame. Judgment prose names wall interrupts and the lock. Right-rail chips can flip 中断 / 连续 and keep the doctor override.
- Validation: `npx tsc --noEmit` exit 0. `npx tsx scripts/test_wall_layer_interrupt.mjs` and `test_adjacent_stage_lock.mjs` ok (dim serosa interrupt, lock prose, peri-lesion ROI).
- Deployment: public Next BUILD `daqGJ4dFzGnq114g3zJdC`. Smoke: `public_root=200`, `public_clinical=200`, `public_desktop_mac=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Frozen four-class weights stay. Wall draft still does not unlock definite cT.

## 2026-08-28, Electron shell of the public workbench

- Scope: `apps/public_shell/electron/`, `scripts/build_public_electron.sh`, Header / profile / tutorial download links. Public Next required.
- Reason: The 19 KB launcher felt too small. Doctors asked for a real desktop window that still only opens the public site.
- Key changes: Electron window loads http://47.106.33.102. No local model, no credentials in the pack. Avatar menu downloads the Electron zip (about 100 MB). Profile page keeps the light launcher as a second option. Menu has reload / hard reload. Frozen Assist weights unchanged.
- Validation: `npx tsc --noEmit` exit 0. `bash apps/public_shell/scripts/test_public_electron.sh` ok. Windows zip about 112 MB, Mac zip about 102 MB (Intel; Apple silicon uses Rosetta).
- Deployment: public Next BUILD `Sf1DJHpzYcCihyyk6bKl1`. Smoke: `public_root=200`, Electron zips 200 (Windows 117972687 B, Mac 107334838 B). Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Harmony still later. Apple silicon native zip can be packed on a Mac if Rosetta is a problem.

## 2026-08-28, Persist adjacent lock; hide TENT on T-staging

- Scope: `doctor-case-state-store.ts`, `adjacent-stage-lock.ts`, `InteractiveSegPanel.tsx`, `ReaderStudyQueuePanel.tsx`. Public Next required.
- Reason: Refreshing mid-case dropped the adjacent-pair lock and 1/2/3 chip. The T-staging rail still showed a TENT before/after line, which fights the meeting decision that TENT is a research control, not the doctor path.
- Key changes: Case state stores `adjacent_lock` and `wall_target_layers` and restores them on reopen. Overlay and evidence-rail locks stay in sync. T-staging Assist card no longer shows the TENT adaptation line. Frozen Assist numbers unchanged. Wall draft still does not unlock definite cT.
- Validation: `npx tsc --noEmit` exit 0. `npx tsx scripts/test_adjacent_stage_lock.mjs` ok.
- Deployment: public Next BUILD `eU2RV7VoCNNx3gL0gXfUA`. Smoke: `public_root=200`, `public_clinical=200`, `public_desktop_mac=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Doctor tries tomorrow evening. Harmony installer and merging new walls into the same 150-case train stay later.

## 2026-08-28, Trial-night wall workflow polish

- Scope: `InteractiveSegPanel.tsx`, `ReaderStudyQueuePanel.tsx`, `DoctorTutorialModal.tsx`. Public Next required.
- Reason: Tomorrow-night trial would hit Space marking extra keyframes, a redraw that kept the old box, 1/2/3 that did not recompute, lock overwriting a painted layer count, and interrupt copy only under the video.
- Key changes: Space pauses first and marks only when already paused. Play/Pause snaps the current frame. Box lesion replaces; 再框一灶 keeps the previous (teal); 去掉上一灶 drops the last extra. Changing 1/2/3 recomputes the draft. Adjacent lock no longer overwrites a painted layer count. Right-rail 胃壁草稿 shows 中断 / 连续 chips. Tutorial and 7-step memo say Assist stays gray until T1–T4+ is tapped. Frozen Assist weights unchanged. Wall draft still does not unlock definite cT.
- Validation: `npx tsc --noEmit` exit 0.
- Deployment: public Next BUILD `VHJhRajrbCz9iw-3L45r-`. Smoke: `public_root=200`, `public_clinical=200`, `public_desktop_mac=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Doctor tries the 7-step paint tomorrow evening. Harmony installer, painted-wall retrieve, and merging new walls into the same 150-case train stay later.

## 2026-08-28, Public download for the desktop shell

- Scope: `Header.tsx`, `DoctorTutorialModal.tsx`, `profile/page.tsx`, `proxy.ts`, `public/desktop/`, `build_public_shell.sh`. Public Next required.
- Reason: The Mac/Windows shell is only useful if doctors can fetch it from the live site instead of a side-channel zip.
- Key changes: Avatar menu and profile page link to `/desktop/gastric-reader-macos.zip` and `...-windows.zip`. Tutorial adds an optional desktop-shell step. Public reader proxy allows `/desktop/`. Pack script copies the zips into Next `public/desktop`. Still a thin public-site icon; no local model.
- Validation: `npx tsc --noEmit` exit 0. `bash apps/public_shell/scripts/test_public_shell.sh` ok.
- Deployment: public Next BUILD `9aB1OmVMcUj4JuUAzAm8D`. Auth edge `auth_server.mjs` now allows `/desktop/`. Smoke: `public_root=200`, `public_clinical=200`, `public_mac=200` (18880 B), `public_win=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*` and `auth_server.mjs.bak_desktop_20260828`.
- Follow-up: Harmony still later. Native WKWebView still needs one `swiftc` run on a Mac.

## 2026-08-27, Tiny Mac/Windows shell of the public workbench

- Scope: `apps/public_shell/`, `scripts/build_public_shell.sh`. No public Next change.
- Reason: Meeting B3 asked for an installer. The product is already the public site, so the package is a desktop icon only.
- Key changes: Mac zip is `胃超阅片.app` (about 19 KB). It opens Chrome/Edge `--app` of the public workbench, or Safari if neither is installed. On a Mac with `swiftc`, the same script compiles a WKWebView binary into the app. Windows gets a one-file `.cmd`. No Electron, no local model, no credentials.
- Validation: `bash apps/public_shell/scripts/test_public_shell.sh` ok. Zip stays under 400 KB.
- Deployment: none. Send `apps/public_shell/dist/胃超阅片-macos.zip`. First launch: right-click Open. Hard-refresh after a site update.
- Follow-up: Harmony still later. A nicer native window needs one run of the same script on a Mac with Xcode CLT.

## 2026-08-27, Tomorrow-trial 7-step memo and admin multi-reader overlap

- Scope: `DoctorTutorialModal.tsx`, `ReaderStudyQueuePanel.tsx`, `InteractiveSegPanel.tsx`, `lib/ops/types.ts`, `lib/ops/multi-reader-overlap.ts`, `/admin/ops`, `/api/admin/ops-stats`. Public Next required.
- Reason: Evening reader meeting leftover P2: doctors need the 7-step wall workflow in the live UI for tomorrow night; multi-reader stats belong in admin only, not as a clinical voting gold standard.
- Key changes: Tutorial adds adjacent-pair / 1-2-3 layers and paint-from-adjacent-normal-wall. Keyframe copy prefers 2–3 frames. T-staging rail shows a collapsible 试画备忘. Overlay and evidence rail log `adjacent_lock`. `/admin/ops` lists cases where two or more accounts recorded a final stage, with caption 后台对照，不是临床投票金标准. Assist weights unchanged. Wall draft still does not unlock definite cT. No voting UI on the doctor workbench.
- Validation: `npx tsc --noEmit` exit 0. `npx tsx scripts/test_multi_reader_overlap.mjs`, `test_adjacent_stage_lock.mjs` ok.
- Deployment: public Next BUILD `J9V48JigFPFlWEgdVU76t`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Doctor tries the 7-step paint tomorrow evening. Windows/Harmony installers, painted-wall retrieve, and merging new walls into the same 150-case train set stay later.

## 2026-08-27, T-staging similar cases default to peritumoral channel, no fake wall index

- Scope: `similar-case-public.ts`, `similar-case-neighbors.ts`, similar-case search route, `SimilarCaseReferencePanel.tsx`, `ReaderStudyQueuePanel.tsx`. Public Next required.
- Reason: Doctors said morphology neighbors do not help T-staging. The gallery still has no painted gastric wall, so retrieval must not pretend to search by layer interruption or true stage.
- Key changes: T-staging defaults to the existing `context` (瘤周层次) visual channel. Copy states the gallery has no doctor-drawn wall and cannot filter by interruption or gold T. If this case already has a wall draft, a side note says it was not used to rank neighbors. Assist weights and neighbor embeddings unchanged.
- Validation: `npx tsc --noEmit` exit 0. `npx tsx scripts/test_similar_case_public.mjs` ok.
- Deployment: public Next BUILD `ZDDZkmj_vOf_mey3_pBgR`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: A real wall-index retrieve still needs a separate painted-wall corpus, not this 150-case gallery.

## 2026-08-27, Deepest-band echo clustering, not full-image super-resolution

- Scope: `wall-echo-clarify.ts`, `InteractiveSegPanel.tsx`, `adjacent-stage-lock.ts`. Public Next required.
- Reason: Evening reader meeting A3: T-staging looks at the deepest-invasion strip vs remaining wall. Full-image sharpening invents structure. Cluster bright / mid / dark regions on a band narrower than the painted stroke.
- Key changes: After wall paint or join, cluster echo on a ~44 x 10 px strip at the deepest lesion-wall point. Magenta outline plus 原图 / 三档 inset. Toolbar 最深窄带回声 zooms that box. Pattern (e.g. 亮-暗-亮) feeds the wall draft side-channel and Assist `contour_context` only. Frozen T weights unchanged. Draft only; does not unlock definite cT.
- Validation: `npx tsc --noEmit` exit 0. `npx tsx scripts/test_wall_echo_clarify.mjs`, `test_adjacent_stage_lock.mjs`, `test_wall_layer_interrupt.mjs` ok.
- Deployment: public Next BUILD `fRuOfnlNR-_HfOq4T-HKf`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Doctor tries the narrow-band view tomorrow evening. No neural super-res model was named in the meeting.

## 2026-08-27, Adjacent-stage lock, wall side-channel, 2-plus keyframe hint

- Scope: `adjacent-stage-lock.ts`, `InteractiveSegPanel.tsx`, `ReaderStudyQueuePanel.tsx`, `DoctorKeyframeStrip.tsx`. Public Next required.
- Reason: Evening reader meeting P1: doctors want to lock T1/T2, T2/T3, or T3/T4 so Assist cannot jump to a far stage; wall interruption is a side channel; T-staging should use 2–3 frames.
- Key changes: Overlay and evidence rail share T1/T2, T2/T3, T3/T4 lock chips. Selecting a pair sets wall layers 3/2/1. After Assist, a side card renormalizes frozen T probs inside the pair only; if four-class top-1 is outside the lock, it warns (the T1/T2 vs T4 case). Frozen 4-class numbers stay on screen and Assist weights are unchanged. Wall ticks/interrupts and multi-frame serosa continuity are shown as draft copy and appended to the local report template. One-keyframe strip/toolbar hint asks for 1–2 more frames. Assist capture may carry `adjacent_lock` / wall interrupt in `contour_context` for later LLM, not for the classifier.
- Validation: `npx tsc --noEmit` exit 0. `npx tsx scripts/test_adjacent_stage_lock.mjs`, `test_wall_layer_interrupt.mjs`, `test_wall_layer_trace.mjs` ok.
- Deployment: public Next BUILD `HgmGakBlQV3Mqz5mGJ_h4`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Local echo clustering (A3) still later. Do not unlock definite cT from wall draft. Do not hot-swap frozen Assist weights during Reader v150.

## 2026-08-27, Doctor 1/2/3 wall layers, interruption, ms seek, extra lesions

- Scope: `InteractiveSegPanel.tsx`, `DoctorKeyframeStrip.tsx`, `wall-layer-interrupt.ts`, `wall-layer-trace.ts`, `wall-layer-breach.ts`, `cine-time.ts`, `doctor-keyframes.ts`. Public Next required.
- Reason: Evening reader meeting: T-staging needs remaining wall layers chosen by the doctor, bright-dark-bright interruption, millisecond/frame seek, and more than one lesion box. Assist numbers stay locked.
- Key changes: Toolbar 1/2/3 (1=serosa, 2=MP+serosa, 3=shallow+MP+serosa). Paint and auto-extend use that count. Longitudinal bright-dark-bright marks 中断/连续 on the draft chips. Cine bar is `m:ss.mmm / frame` at 25 fps estimate, slider step 0.001. A second box keeps the previous lesion (teal). Draft only; does not unlock definite cT.
- Validation: `npx tsc --noEmit` exit 0. `npx tsx scripts/test_wall_layer_interrupt.mjs`, `test_wall_layer_trace.mjs`, `test_wall_pixel_extend.mjs`, `test_wall_extension.mjs` ok.
- Deployment: public Next BUILD `fxx7e4RePpdrHyvo0CaVh`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Doctor tries tomorrow evening. Adjacent-stage 2-class lock and feeding wall into the frozen classifier stay later.

## 2026-08-27, Clearer echo profile and wheel-zoom on the current frame

- Scope: `WallFeatureAnalysisCard.tsx`, `InteractiveSegPanel.tsx`. Public Next required.
- Reason: 回声，病灶到浆膜 was a tiny unlabeled strip. Doctors also needed to scroll-zoom the frozen frame.
- Key changes: Echo chart is taller, labeled mucosa to serosa, with lesion / bright / dark / serosa-peak marks. Wheel zooms the current frame toward the cursor (1-8x). Shift-drag or middle-drag pans. Double-click or 退出放大 resets. Wall-paint and lumen-sculpt wheels still change brush size. Assist numbers stay locked.
- Validation: `npx tsc --noEmit` exit 0.
- Deployment: public Next BUILD `3fFw3gcSZGKwspixNucnh`. Smoke: `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: None.

## 2026-08-27, Paint-span layer cluster, walk along lesion, imagine after vanish

- Scope: `wall-layer-trace.ts`, `wall-layer-breach.ts`, `InteractiveSegPanel.tsx`. Public Next required.
- Reason: Doctors paint the visible normal wall. The five layers are thin. At the breach the wall may thicken or disappear. The tool must first count layers in the painted ribbon, then continue each layer along the lesion until it vanishes, then complete an imaginary wall and show mucosa-to-serosa status.
- Key changes: Wall brush (3-22 px, wheel or slider) wraps the painted ribbon. Echo clustering on that ribbon yields 2-5 layers, named from mucosa outward. Each layer is walked along the lesion mask; inside-mass or lost echo marks vanish, then a dashed imaginary parallel continues. Banner ticks show 黏膜浅层 to 浆膜 as 还在 / 变薄 / 消失 / 假想 / 未分出. Assist numbers stay locked.
- Validation: `npx tsc --noEmit` exit 0. `npx tsx scripts/test_wall_layer_trace.mjs` ok (5 painted layers on a synthetic stripe). Existing wall-pixel-extend / wall-extension tests still pass.
- Deployment: Public Next BUILD `7B420svzYpRZySi9_b9ix`. Smoke `public_root` / `public_clinical` 200. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Draft ticks do not unlock definite cT.

## 2026-08-27, Thin silky wall layers hug the lesion strip

- Scope: `wall-polyline.ts`, `wall-pixel-extend.ts`, `wall-extension.ts`, `wall-layer-breach.ts`, `WallFeatureAnalysisCard.tsx`, `contact_geometry.js`, `interactive_layer_bridge.js`. Public Next required.
- Reason: 假想分层 and 局部切面 sat too far from the lesion. The curves used too few points and showed sharp corners.
- Key changes: Join follows the lesion contour on a few-pixel strip, not a far circular ray. Forced 3-layer bands are hairline parallels of that strip, typically 400-1200 points, Chaikin-smoothed. Local-cut SVG crops to the lesion face and draws from the lesion outward, even when echo edges are imaginary. Vendor cache `?v=20260827hug`. Assist numbers stay locked.
- Validation: `npx tsc --noEmit` exit 0. `npx tsx scripts/test_wall_pixel_extend.mjs` and `test_wall_extension.mjs` ok (dense join, median lesion distance about 2.5 px).
- Deployment: Public Next BUILD `sEZ4_PSDT_15zy6AOaXgc`. Smoke `public_root` / `public_clinical` 200. `gastric-next-public` (`:3300`) was inactive and not restarted. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Draft 3-layer bands do not unlock definite cT.

## 2026-08-27, Bilingual Morandi doctor-model figures

- Scope: `scripts/plot_zml_reader_v150_doctor_model_zh_20260827.py` now writes the same five slim figures in Chinese and English.
- Reason: the user asked for both language versions of the preferred Morandi pack.
- Key changes: Shared geometry and colors. Chinese stays in `figures/zh_morandi/`. English is in `figures/en_morandi/` with Times New Roman / DejaVu Serif. Share zip is `zml_reader_v150_doctor_model_bilingual_20260827.zip` (`figures/zh/`, `figures/en/`, tables). Still no L3 / MaskROI / Dual rows, no 150-case gallery, no patient identifiers.
- Validation: script writes 10 PNG/PDF pairs (5 per language) from the frozen ZML 150 recount.
- Deployment: None. Research pack only.

## 2026-08-27, Wall join along lesion, forced 3 layers, hide refine rail

- Scope: `wall-pixel-extend.ts`, `wall-extension.ts`, `wall-layer-breach.ts`, `InteractiveSegPanel.tsx`. Public Next required.
- Reason: After paint, the wall grew into a yellow dashed 360-degree ring. Lesion refine buttons also popped open as soon as a box existed.
- Key changes: Painted wall stays as the visible span. Only the lesion-facing gap is joined along the pixel ridge / lumen arc. No yellow dashed explosion. Neighborhood is always force-clustered into 3 layers hugging that join, even when contrast is flat. 拖点精修 / 正负点 / 涂改 stay under 更多工具. Assist numbers stay locked. Not a five-layer GT.
- Validation: `npx tsc --noEmit` exit 0. `npx tsx scripts/test_wall_pixel_extend.mjs` and `test_wall_extension.mjs` ok.
- Deployment: Public Next BUILD `wg76Sq0-nN86LVpOE-mOR`. Smoke `public_root` / `public_clinical` 200. Workstation `:3300` on the same standalone. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`; standalone bak `.next/standalone.bak_20260827_200009_pre_wall_join3`.
- Follow-up: Draft 3-layer bands do not unlock definite cT.

## 2026-08-27, Pause on keyframe, lumen, and wall

- Scope: `InteractiveSegPanel.tsx` cine / keyframe / 框选胃腔 / 胃壁. Public Next required.
- Reason: Space used to mark while the video kept playing. Doctors need to freeze the frame they just chose, then stay on that frame when they pick another keyframe or arm lumen / wall tools.
- Key changes: Space and 「标记此帧」 pause first, then mark, and stay on that frame. Clicking another keyframe seeks and stays paused on it. 框选胃腔, 画胃壁, 点两侧, and 自动延长分层 also pause on the current frame and bind it as the open keyframe. Right-rail 「胃壁」 sits with 「框选胃腔」; the top bar has 画胃壁 / 自动延长分层 / 点两侧接 / 传到关键帧 / 壁层. Assist numbers stay locked.
- Validation: `npx tsc --noEmit` exit 0. Localhost workbench: Space while playing paused at t=6.19s and marked that frame; clicking 2.4s stayed paused at 2.37s with that contour; 胃壁 while playing paused and armed paint. Test keyframes removed.
- Deployment: Public Next BUILD `lcYf6JlIcJ1l9jlAYM7b6`. Smoke `public_root` / `public_clinical` 200. Workstation `:3300` on the same standalone. `gastric-next.service` (`:3000` next dev) was not restarted. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`; standalone bak `.next/standalone.bak_20260827_195512_pre_pause_kf`.
- Follow-up: Draft walls still do not unlock definite cT.

## 2026-08-27, Paint wall, pixel grow, layer draft, keyframe copy

- Scope: `lib/wall-pixel-extend.ts`, `lib/wall-layer-breach.ts`, `InteractiveSegPanel`, doctor keyframes / propagate.
- Reason: Doctors can see a complete wall on the flanks and want to paint that segment, then have the system follow actual pixels past the lesion, estimate how many layers are involved, and copy that class to other keyframes.
- Key changes: 「画胃壁」 is a hold-to-paint stroke. On release the visible ridge is grown around the lesion. Five-layer draft uses remain / thickness (黏膜浅层 to 浆膜). Colored inward bands show the draft layers. Wall polygon and layer class copy to other keyframes by flow or contour. Assist numbers stay locked. Not a five-layer GT campaign.
- Validation: `npx tsc --noEmit` exit 0. `npx tsx scripts/test_wall_pixel_extend.mjs` and `test_wall_extension.mjs` ok. Localhost workbench still opens without a password.
- Deployment: Public Next BUILD `zwWVDPZhFmxgvsbghGg_v`. Smoke `public_root` / `public_clinical` 200. Workstation `:3300` on the same standalone. `gastric-next.service` (`:3000` next dev) was not restarted. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`; standalone bak `.next/standalone.bak_*_pre_wall_paint`.
- Follow-up: Draft layers do not unlock definite cT. Doctor still ticks 层次 / 浆膜.

## 2026-08-27, Localhost no-password plus doctor wall flanks

- Scope: `LoginGate.tsx`, `DoctorAccountModal.tsx`, account GET, `local-access.ts`, `wall-extension.ts`, `InteractiveSegPanel.tsx`.
- Reason: Doctors need to mark the two visible wall flanks themselves, then edit the imagined span. Localhost was still showing the public password form.
- Key changes: `http://127.0.0.1` / `localhost` auto-enters as the last-seen or first reader, no password. Other LAN hosts keep the identity picker, still no password. Public host stays password-only. 「延长胃壁」 now asks the doctor to click both visible flanks; a second button press or 「自动接」 joins without clicks. Dashed span remains draggable. Assist numbers unchanged.
- Validation: `npx tsc --noEmit` exit 0. `npx tsx scripts/test_wall_extension.mjs` ok, including doctor-flank marks. Localhost account GET is `authenticated: true`, `local_access: true`. Fake public Host stays `authenticated: false`. Browser on `http://127.0.0.1:3000/` opened the workbench as AD with no password field; 「延长胃壁」 entered pick mode and 「自动接」 completed. Public account GET without cookie stays unauthenticated.
- Deployment: Public Next BUILD `XF2ZTA-8gDMZuU3phI22L`. Smoke `public_root` / `public_clinical` 200. Workstation `:3300` on the same standalone. `gastric-next.service` (`:3000` next dev) was not restarted. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`; standalone bak `.next/standalone.bak_20260827_193439_pre_wall_auth`.
- Follow-up: Draft walls still do not unlock definite cT. Do not weaken public login.

## 2026-08-27, Wall extension through the lesion sector

- Scope: local workbench first (`InteractiveSegPanel`), `lib/wall-extension.ts`. Public Next if the same rail is live.
- Reason: Doctors can see the wall on both flanks but must imagine how far it continues through the mass. After box-lesion auto-seg, extend that visible wall along the invasion axis.
- Key changes: 「延长胃壁」 joins the two visible shoulders through the breach. With a lumen it uses a constant-radius arc around the cavity; without lumen it joins the flanks. Dashed amber is the uncertain span. Auto-runs after keyframe / SAM lesion if no wall exists yet. Doctor drag clears the draft flag. Assist probabilities unchanged. Not a five-layer GT.
- Validation: `npx tsc --noEmit` exit 0. `npx tsx scripts/test_wall_extension.mjs` ok. Public smoke `public_root` / `public_clinical` 200; public HTML includes this BUILD.
- Deployment: Public Next BUILD `lFGuOEbnsCX5UNHZqNPLf`. Workstation `:3300` on the same standalone. `gastric-next.service` (`:3000` next dev) was not restarted. Hard-refresh http://47.106.33.102 . LAN workbench also has the source via `:3000`. Rollback: Aliyun `.next-public-deploy-dist.bak_*`; standalone bak `.next/standalone.bak_20260827_192717_pre_wall_ext`.
- Follow-up: A lumen still makes the arc stabler. Do not treat the dashed span as accepted wall for `wall_gate`. Logged-in box-then-extend click-through was not run here.

## 2026-08-27, Public reader BioMedAgent-style assist loop

- Scope: public 150-case rail now auto-runs guideline note + evidence contrast after Assist. A structured critic may trigger one similar-case refine, then contrast runs once more. Tent vs frozen is shown only when top-1 flips. Accept/modify writes an EXP candidate JSONL. Public `proxy.ts` now admits assist-judgment, evidence-fusion, llm, and experience APIs.
- Reason: map Bu et al. (Nat Biomed Eng 2026) retrieve/explore/critic/repair onto the workbench without opening LangGraph or rewriting Assist probabilities.
- Validation: `npm run test:evidence-fusion` (critic: no cases / T-boundary unmarked / useful marks). Python `build_evidence_critic` matches. Assist numbers stay locked; refine max = 1. Logged-in LAN workbench (`:3000`) box-then-Assist on a study case: 分类 / 指南 / 相似例 / 对照 all done; 再检索 skipped because critic did not recommend repair. Public HTML BUILD later became `lFGuOEbnsCX5UNHZqNPLf` (wall extension) and still ships the loop copy.
- Deployment: `bash scripts/deploy_public_next.sh` BUILD `gBh6t0zo_kCnslhwgwoH4` (prior `ye96VB0D8yeGwB2oBnBUd`). Restarted `gastric-next-public.service` so proxied LLM-info and experience routes pick up the new worker. Hard-refresh http://47.106.33.102. A later patch clears the restore skip when Assist runs again.
- Follow-up: EXP rows stay `candidate`. Do not rebuild the neighbor table from them. Do not call this self-evolving.

## 2026-08-27, Continuous gastric-wall delineation plan

- Scope: methodology / product plan only. No public Next, no Assist change.
- Reason: Lesion and lumen segmentation still leave the remaining wall imaginary. T-stage on TAUS is decided on the wall opposite the lumen.
- Key changes: New `docs/plans/GASTRIC_WALL_DELINEATION_TOOL_20260827.md`. V0 is a third rail object (outer-wall polyline / wall band) on the existing workbench, drafted from lumen + ContactGeom, saved as `wall_polygon`. Not a five-layer GT campaign. Draft walls do not unlock definite cT.
- Validation: Docs only. Confirmed public simple rail has lesion + lumen only; research `InteractiveSegPanel` already stores `wall_polygon`.
- Deployment: None.
- Follow-up: Implement V0 on the public rail only after the user asks. Do not start a wall UNet or 5-layer labels this round.

## 2026-08-28, Worst-frame aggregation on the deep-side crop

- Scope: add experiment `convnext_tiny_deepside_worst` on `deep_side_v1`. Only the patient aggregation changes: mean of frame features to the frame with the highest expected T class.
- Reason: mean pooling mixes shallow and deep planes and encourages memorizing the patient. The clinical call is the worst remaining-wall plane.
- Validation: `worst_v1` best validation exact ACC 0.5242 at epoch 27 (T2 recall 0.09). Prospective 197 ACC 0.5381, T2 recall 0. Below mean-pool Tiny 0.5484 / 0.5584. Train still reached 0.95.
- Deployment: None. Research training only.

## 2026-08-27, ConvNeXt-Small deep-side backbone

- Scope: add experiment `convnext_small_deepside` on the same `deep_side_v1` crop. Only the backbone changes: Tiny to Small.
- Reason: Tiny may lack capacity to read remaining-wall thickness on the lumen-directed crop.
- Validation: Small `small_v1` best validation exact ACC 0.5403 at epoch 20 (T2 recall 0), below Tiny 0.5484 and ROI25 0.5938. Train reached about 0.99. Audit: validation 124 ACC 0.5403; prospective 197 ACC 0.5076, T2 recall 0.
- Deployment: None. Research training only.

## 2026-08-27, Lumen-directed deep-side crop protocol

- Scope: add `deep_side_v1` and experiment `convnext_tiny_deepside`. The crop is the deep tumor half plus outward remaining wall, using a lumen box to define direction.
- Reason: T-stage on filled transabdominal US is decided on the wall opposite the lumen. Training may drop frames without a box; inference can take a doctor-drawn lumen box.
- Coverage of the joined sidecar: train 1051/1062 patients, validation 124/128, prospective 197/425. External stems do not match, so external audit is skipped.
- Frames whose lumen and lesion centers are closer than 1 pixel are dropped. That removed 2 training frames and no patients. `deepside_v1` failed on this case and stays on disk; the comparable run is `deepside_v2`.
- Validation: Tiny `deepside_v2` best validation exact ACC 0.5484 at epoch 3 (T2 recall 0). That is below ROI25 0.5938. Train reached about 0.999 by epoch 26. Audit on lumen-available patients: validation 124 ACC 0.5484; prospective 197 ACC 0.5584, T2 recall 0. External skipped.
- Deployment: None. Research training only.

## 2026-08-27, Slim Chinese Morandi doctor-model figures

- Scope: replace the large white English gallery with five Chinese key figures in a Morandi palette: recall by gold, case label strip, agree strip, accept/modify by gold, and four-way by gold.
- Reason: the previous pack had too many images, bright colors, and English captions. The user asked for Morandi colors, clearer Chinese figures, and only the useful summaries.
- Validation: 5 PNG/PDF pairs under `figures/zh_morandi/`. Pack `zml_reader_v150_doctor_model_zh_20260827.zip` now also prints Accept AI versus reserved-opinion counts on the recall, strip, and button figures. No patient identifiers. No 150-case gallery.
- Deployment: None.
- Follow-up: use this pack for sharing. Keep the older English/black sets as archive.

## 2026-08-27, White doctor-model figures plus per-case charts

- Scope: redraw the doctor-final versus model recount on a white background, add a case scoreboard / label tracks / confidence-by-button panels, and write one chart for each of the 150 zml cases.
- Reason: the previous pack was black-background summaries only. The user asked for white figures, more detail, and a statistical chart per case.
- Validation: 150/150 case PNGs; white pack `zml_reader_v150_doctor_model_agreement_white_20260827.zip` is 14 MB and contains the summaries plus `cases/`. No hospital IDs.
- Deployment: None. Research pack only.
- Follow-up: keep official black figures in `figures/official/` for the repo style; use `figures/white/` for this share pack.

## 2026-08-27, Detailed doctor-model visuals and agreement pack

- Scope: add per-gold, distance, four-way-by-class, case-strip, and gold-confusion figures for doctor final versus model, then zip a share pack without patient identifiers.
- Reason: the first recount was aggregate only. The user asked for a full visual recount and a downloadable pack.
- Validation: zml 150 per-class and distance tables match the case rows. Pack `zml_reader_v150_doctor_model_agreement_20260827.zip` is 2.4 MB, 65 files, no hospital IDs.
- Deployment: None. Research pack only.
- Follow-up: do not retune on this overlapping reader set.

## 2026-08-27, Doctor-final agree/disagree with the model on frozen ZML 150

- Scope: recount every completed reader-v150 final by operating doctor, then plot accept/modify, label match, and four-way versus gold.
- Reason: SUMMARY only had doctor Acc versus gold. The workbench records Accept AI versus Save my call, and the frozen scores already have doctor_final versus L3 / MaskROI / Dual.
- Cohort: complete dump `zml_rereview_20260826_232057`. Primary totals are zml 150. admin has 6 completed smoke cases, listed separately. jmr / why / wzw have no completed v150 finals.
- Validation: zml explicit Accept AI 88/150 (T 56/100, BM 32/50). Label agree with shown AI 56/100 T and 31/50 BM; with frozen L3 61/100; with Dual 30/50. Figures under `pipeline/experiments/reports/zml_reader_v150_frozen_20260827/figures/official/doctor_*`.
- Deployment: None. Research recount only. No Next change.
- Follow-up: do not mix admin smoke cases into the 150 totals. Do not retune on this overlapping reader set.

## 2026-08-27, Official episodic Tent on frozen ZML 150 plus training figures

- Scope: add official episodic Tent to the frozen reader pack for MaskROI-25 only, and plot training plus source/Tent results. Assist wrapper now avoids BatchNorm batch-stat updates when the case batch is 1.
- Reason: Tent is test-time adaptation, not training. Official BN Tent is invalid on a single reader frame. MaskROI-25 uses LayerNorm/GroupNorm, so affine Tent can run per case and reset.
- Protocol: frozen keyframe + mask + ROI-25; episodic, steps=2, Adam `lr=1e-3`; L3 and Dual stay source-only.
- Validation: MaskROI-25 source and Tent Acc/QWK both 0.430 / 0.291; 0 of 100 hard labels flipped; mean absolute top-1 probability shift 0.092. Training last Acc 0.999 versus best validation 0.625 versus ZML 0.430. Figures under `pipeline/experiments/reports/zml_reader_v150_frozen_20260827/figures/official/`.
- Deployment: restart `gastric-reader-analyze.service` so Assist uses `force_batch_stats=False` and restored BN buffers. No Next rebuild.
- Follow-up: do not promote Tent. Do not search Tent hyperparameters on this overlapping reader set.

## 2026-08-27, Freeze ZML reader v150 keyframe/mask/ROI-25 and score

- Scope: lock the complete zml 150 doctor keyframes to disk, derive ROI from each mask, and score those frozen files. Research only; no public Next change.
- Reason: live workstation case-state was stale (11 T + 50 BM). T had no on-disk keyframe/mask/ROI pack, so models were still seeking video at test time.
- Inputs: complete dump `runtime/gastric_scan_next/backups/zml_rereview_20260826_232057/doctor_case_state.json`. One usable polygon keyframe per case (deepest, then refined, then time). Mask is the rasterized doctor polygon. ROI expands each side of the exclusive mask box by 25%, matching `maskroi25_clinical_v1`.
- Pack: `pipeline/data/zml_reader_v150_frozen_20260827/` with 150/150 images, masks, ROI-25 crops, `frames.csv`, and `LOCK.json`. Scoring reads this pack only.
- Validation: freeze exported T 100 + BM 50 with zero skips. Source inference (Tent off) on the locked files: T L3 Acc 0.530 / adjacent 0.810; maskroi `lesionrgb_v1` Acc 0.430 / adjacent 0.820; doctor Acc 0.530. BM Dual Acc 0.680 (34/50); doctor Acc 0.760 (38/50). maskroi clinical-11 matched 85/100 T cases; unmatched cases used an all-missing vector.
- Deployment: None. Descriptive reader-set numbers only. T 100 overlaps official prospective and external cases and must not be used to retune.
- Follow-up: keep scoring on the locked pack. Do not seek reader videos again for this test.

## 2026-08-27, ROI-25 plus aligned mask protocol

- Scope: add `roi25_mask_v1` and experiment `convnext_tiny_roi25_mask`. The only added input is a binary mask cropped from the same 25% expanded box as the ROI RGB.
- Reason: T-stage is about how the annotated tumor sits against remaining gastric wall. A full-canvas mask loses that registration after resize.
- Isolation: new protocol and run directory. Existing `roi25_v1` / `lesionrgb_v1` artifacts are not overwritten.
- Deployment: None. Research training only.

## 2026-08-27, ROI-50-only ConvNeXt-Tiny protocol

- Scope: add `roi50_only_v1` and experiment `convnext_tiny_roi50`. Same ROI-only ConvNeXt-Tiny path as `roi25_only_v1`, but the box is expanded 50% on every side.
- Reason: the 25% ROI covers about 37% of the full crop and never hit the image border in a 200-frame sample. A wider band tests whether extra gastric-wall context helps.
- Geometry: `pad = round(lesion_side x 0.50)`, then clamp. The same 200-frame sample had 46/200 edge clamps; mean ROI covered about 48% of the full crop.
- Deployment: None. Research training only.

## 2026-08-27, ROI-25-only ConvNeXt-Tiny protocol

- Scope: add `roi25_only_v1` and experiment `convnext_tiny_roi25`. The model sees only the lesion box expanded by 25% on every side.
- Reason: the five-input ConvNeXt overfit quickly. This run tests whether the local ROI already carries the T-stage signal.
- Geometry: `pad_x = round(lesion_width x 0.25)`, `pad_y = round(lesion_height x 0.25)`, then clamp. A 200-frame train sample had 0 edge clamps; mean ROI covered about 35% of the full crop.
- Deployment: None. Research training only.

## 2026-08-27, Call the 128-patient split the validation set

- Scope: user-facing labels in `tstaging_lab/` now say 验证集 / validation set instead of dev. File names such as `dev.csv` stay unchanged so the running Small job and existing manifests are not moved.
- Reason: the 128-patient split is the ordinary validation set used to pick checkpoints. WADI is only the frozen patient list, not a separate training system.
- Deployment: None. Research labels only. The current `small_v1` process still prints the old `dev` wording until it exits.

## 2026-08-27, ConvNeXt-Small mask/ROI/clinical backbone comparison

- Scope: add `convnext_small_maskroi25_clinical` as a separate backbone-only experiment under the existing `maskroi25_clinical_v1` input and split contract.
- Reason: test whether the shared ConvNeXt-Tiny visual encoder is capacity-limited without changing whole image, mask shape, masked-lesion RGB, 25% ROI, clinical-11, frame pooling, or training settings.
- Implementation: added an isolated ConvNeXt-Small model/card, per-experiment protocol lock support, and `--experiment-id` selection to the existing train/evaluate CLIs. No segmentation, handcrafted features, audit feedback, or public product code was added.
- Validation: pretrained ConvNeXt-Small weights downloaded to the external Torch cache; multimodal GPU dry-run passed with full/ROI/lesion tensors `[2,6,3,224,224]`, mask `[2,6,1,224,224]`, clinical `[2,22]`, and logits `[2,4]`. A full `small_v1` run started on GPU 1.
- Deployment: None. Research training only.
- Follow-up: select only by the locked dev cohort. Prospective and external cohorts remain descriptive audits after the checkpoint is frozen.

## 2026-08-27, Official GitHub Tent test-time adaptation

- Scope: replace the previous custom entropy loop with the [DequanWang/tent](https://github.com/DequanWang/tent) API. Research evaluator plus live Assist wrapper. No public Next UI change.
- Reason: Tent is online test-time adaptation of a finished source checkpoint, not a training recipe. The previous evaluator adapted then ran a second forward; that is not the GitHub `forward_and_adapt` contract.
- Implementation: `pipeline/lib/tent.py` ports `configure_model`, `collect_params`, `Tent`, and Adam `lr=1e-3`. ConvNeXt has no BatchNorm, so LayerNorm / GroupNorm affine parameters are collected. Dropout / DropPath stay off. `eval_tstage_tent_20260827.py` defaults to continual, `steps=1`. Assist stays episodic and restores source weights after each case.
- Validation: official self-check confirmed `steps=1` returns pre-update logits and only LayerNorm affine is trainable. Wrapper self-check restored shared weights. CPU 2-patient smoke passed. Official continual eval on frozen dev 128 wrote `tent_github_dev_continual.json`: source ACC / QWK 0.5391 / 0.6382 versus Tent 0.4688 / 0.4802; entropy fell 0.8064 to 0.7273. Not promoted.
- Deployment: restart `gastric-reader-analyze.service` so Assist imports the official wrapper. No Aliyun Next rebuild. Rollback: `GASTRIC_TENT=0` or revert `pipeline/lib/tent.py` and `pipeline/lib/tent_adapt.py`.
- Follow-up: do not tune Tent on 425 / 485. Keep source inference as the reported number unless a frozen protocol later beats source on the development set.

## 2026-08-27, Direct ConvNeXt mask/ROI/clinical classification protocol

- Scope: replace the planned segmentation-dataset scaffold in `tstaging_lab/` with one patient-level classification protocol on the existing WADI manifests, then launch the first locked run.
- Reason: keep the experiment explicit and reproducible: whole `crop_ui` image, existing lesion-mask shape, normalized image pixels inside that mask, lesion-mask bounding-box ROI expanded by 25% on every side, and the existing clinical-11 values with missing indicators.
- Model: one shared ImageNet ConvNeXt-Tiny encodes the whole image, ROI, and masked-lesion RGB; a small CNN encodes the binary mask; a two-layer MLP encodes the 22-wide clinical value/missingness vector; valid frame features are averaged before a four-class T-stage head. Masked-lesion RGB exposes lesion interior pixels and the natural mask edge. No separate boundary ring, perilesional statistic/loss, segmentation model, SDF, morphology scalar, radial/region feature, or cached embedding is used.
- Data boundary: optimization remains WADI train 1,062 and selection remains dev 128. Prospective/external cohorts remain descriptive audit. The protocol requires an existing lesion mask and clinical row at inference and is therefore annotation-assisted. Lauren type and differentiation may be pathology-derived, so this is not a purely preoperative deployment claim.
- Records: added `maskroi25_clinical_v1`, experiment card `convnext_maskroi25_clinical`, dedicated train/evaluate CLIs, an independent lock, and a module-by-module `METHOD.md`. Removed the unused segmentation scaffold and its script/registry entries.
- Validation: actual WADI data built `full [1,6,3,224,224]`, `ROI [1,6,3,224,224]`, `mask [1,6,1,224,224]`, `lesion RGB [1,6,3,224,224]`, and `clinical [1,22]`; CPU ConvNeXt forward/backward dry-run produced `[1,4]` logits without a saved run. Python compile passed; 36 lab tests passed; 1,062/128/425/485/205 counts and both protocol locks passed. All 10,894 WADI masks exist, are non-empty, and have binary 0/255 extrema.
- Run: `lesionrgb_v1` started on GPU 0 with the locked 30-epoch schedule. The ledger is `running`; startup acquired GPU memory and wrote config, clinical normalization statistics, protocol lock, and `train.log`. No development or audit result exists yet.
- Repository checks: all canonical path checks and sampled manifest paths passed. The aggregate command remains non-zero only because root hygiene reports 16 pre-existing unexpected directories, unrelated to this change.
- Deployment: None. Research code only; no public Next or inference-service change.
- Commit: not created in this turn because no Git commit was requested; changes remain in the working tree.
- Follow-up: run formal training only after reviewing the annotation-assisted and pathology-field limitations. Select by dev exact accuracy only.

## 2026-08-27, Repository root loose-file cleanup

- Scope: move 18 loose root files into the meeting archive, GastricUS implementation package, clinical validation templates, restricted staging review, and local artifact quarantine. Update generators and references so the files do not return to the root.
- Reason: the repository root mixed canonical documents with report and weight duplicates, meeting downloads, macOS resource forks, and restricted reader crosswalks.
- Safety: no file was deleted. Exact duplicates and AppleDouble metadata were retained under `artifacts/tmp/root_cleanup_20260827/`; the differing clinical workbook copy was retained separately under an ignored review folder. Restricted reader tables are now under `data/staging_review/reader_v150_source_crosswalk/` and excluded from Git.
- Key changes: the GastricUS plan now lives beside `pipeline/medsiglip_gastricus/`; report generation no longer copies outputs to the repository root; the reader crosswalk builder writes only to its controlled staging directory; meeting and report-template indexes point to canonical locations.
- Validation: all 18 logged migrations have no remaining old file and an existing destination; modified Python files compile; the reader crosswalk rebuild completed with 150 reader rows and wrote only to the new directory; the asset manifest and script registry were refreshed; canonical path verification has zero failed checks. Root hygiene now reports zero unexpected files and zero discouraged assets, while 16 pre-existing directories remain for a separate risk-reviewed pass.
- Deployment: None. No public Next, reader UI, request payload, or inference path changed.
- Rollback: use the 2026-08-27 rows in `data/metadata/path_migration_log.csv`; move retained files back and restore the previous generator constants.
- Follow-up: review active runtime, worktree, cache, result, temporary, and human-AI comparison directories separately before any directory migration.

## 2026-08-27, T-staging lab experiment ledger

- Scope: expand `tstaging_lab/` into one-experiment-one-directory management. Research only; no public Next change.
- Reason: keep data, trainer, metrics, and evaluation locked while making runs, figures, and SwanLab reusable. Clinical-11 was checked before later fusion work.
- Data: WADI 1,062 / 128 / 425 / 485 patients match `maincenter_retrospective_v20260821`. Clinical-11 is a sidecar only. It is not complete: train 1058/1062 matched, 138/1062 have all 11 fields; prospective length/thickness about 57%/61%; 2019 marker values are absent; 2024 has no CA19-9 binary; 29 Fujian Cancer Hospital IDs do not match.
- Experiment layer: cards under `experiments/`, `ledger.csv` state machine, run directories refuse overwrite, official/debug figures, and an env-only SwanLab sidecar. `resnet18_meanpool/lab_v1` is closed as `do_not_promote`.
- Validation: compile, pytest, lab verify, clinical sidecar write, plot from `lab_v1`, ledger parse, repo path check.
- Deployment: None.
- Follow-up: do not join clinical columns into image-only v1. Do not retune from audit scores.

## 2026-08-27, Isolated T-staging model lab

- Scope: new root workspace `tstaging_lab/`. Research training only; no public Next change.
- Reason: keep data, training, and evaluation fixed so later experiments only add a model file.
- Data: copied the WADI v20260827 contract; rebuilt a 13,763-sample three-asset pack as crop_ui image, 0/255 binary mask, and crop_roi image under train/dev/prospective/external centers. Loaders read only the 10,894-row WADI manifests; the extra 2,869 frames are listed in `data/integrity/excluded_physical_rows.csv`.
- Protocol: image-only v1 uses crop_ui bags of 6 frames, weighted CE, AdamW, 30 epochs, and locked hashes in `protocols/image_only_v1/LOCK.json`. Mask and crop_roi stay on disk but do not enter this protocol.
- First model: `models/resnet18_meanpool.py`. CPU dry-run passed on 1,062 / 128. GPU 1 run `lab_v1` finished 30/30. Best dev ACC 0.5156 at epoch 9. Audit: prospective 0.5624, external 0.3918, unseen 0.4829.
- Validation: 16 pytest tests passed; prepare reported exact 13,763 / 10,894 / 2,869 counts; verify checked patient leaks and 400 masks; lock written.
- Deployment: None.
- Follow-up: add later models only under `tstaging_lab/models/`. Do not edit locked core files or use audit scores to retune v1.

## 2026-08-27, WADI image-only ResNet18 mean-pool baseline

- Scope: align `scripts/train_t_stage.py` to the frozen WADI primary development contract and launch `r18_mean_wadi_v1` on GPU 1. Training only; no public Next change.
- Reason: retain one reproducible baseline without GUS ablations, masks, clinical variables, aggregation comparisons, or audit-cohort access.
- Data and model contract: default inputs are `development/train_maincenter_1062.csv` and `development/dev_maincenter_128.csv`; patient overlap and expected counts are enforced. Each patient contributes up to K randomly sampled training frames or deterministic development frames; ResNet18 frame features are averaged over valid frames before weighted four-class cross-entropy.
- Training behavior: fixed full epoch schedule without early stopping; ImageNet initialization, class weights, label smoothing, validation ACC/QWK/per-class recall, last checkpoint and best-development-ACC checkpoint. A CPU/no-pretrained dry-run is available and custom split counts require explicit opt-in.
- Validation: Python compile and CLI help passed; the full frozen contract loaded exactly 1,062 train / 128 dev patients with no overlap; CPU forward/backward dry-run passed with image bags `[2,2,3,64,64]` and logits `[2,4]`; script registry refreshed. Repository path checks retained their pre-existing root-hygiene findings noted below.
- Run result: `r18_mean_wadi_v1` completed 30/30 epochs on GPU 1 without OOM. Best dev ACC was 0.5078 at epoch 14; final epoch ACC was 0.4766. It loaded 1,062 train / 128 dev patients and wrote artifacts to `pipeline/experiments/reports/tstage_resnet18_meanpool_wadi_20260827/runs/r18_mean_wadi_v1/`.
- Descriptive audit: after architecture selection, `eval_t_stage.py` evaluated the frozen best checkpoint once. Temporal 2025 n=425: ACC 0.4776, balanced ACC 0.3817, QWK 0.4494. External n=485: ACC 0.4392, balanced ACC 0.3771, QWK 0.3739. Predictions and center summaries are under `r18_mean_wadi_v1/audit_eval/`. These numbers are audit-only and must not drive further model choices.
- Regularized follow-up: after the baseline showed train ACC 0.965 versus final dev ACC 0.477, added opt-in partial-backbone training, stronger image augmentation, dropout control, and cosine LR without changing baseline defaults. CPU forward/backward dry-run passed. Started `r18_mean_wadi_reg_v1` for 60 epochs on GPU 1 with only `layer4` trainable, strong augmentation, dropout 0.5, and cosine LR; audit cohorts remain unavailable during tuning.
- Deployment: None. Training-only.
- Rollback: revert the trainer and registry/documentation entries; the prior completed `tstage_resnet18_meanpool_20260826` run remains unchanged.
- Follow-up: select only on the fixed 128-patient development cohort. Do not use temporal or external audit results to revise this baseline.

## 2026-08-27, Doctor-facing RAG retrieval trace

- Scope: public workbench similar-case panel, 循证 panel, reader v150 and year-queue. Public Next required.
- Reason: Doctors could not naturally see how RAG retrieved cases or guideline clauses. The trace sat behind LLM assist-judgment prose, or only in researcher docks.
- Key changes: 循证 title is now 循证（检索轨迹）. After Assist, the panel sits under the locked AI number, not inside the LLM draft. Each clause shows why it was retrieved (current T, keyword match, or always-on guardrail). Similar-case cards show 本次怎么检索到的 (visual neighbor table, channel, count, refine). LLM source chips scroll to the matching clause. Assist probabilities unchanged.
- Validation: `npx tsc --noEmit` exit 0. `npx tsx scripts/test_similar_case_public.mjs` ok. `:3300` `POST /api/reader/guideline-trace` for T3 returns 6 cards, query.inferred_cT=T3, first why `按当前 T3 取出`, 3 local sources. Neighbor search returns `retrieval_trace.corpus=visual_similar_neighbors_v2`, n_shown=5. Public smoke `public_root` / `public_clinical` 200; public HTML includes this BUILD.
- Deployment: Public Next BUILD `TEoplYbRdRH5Ck6iWuvMv`. Workstation `:3300` (`gastric-next-public`) on the same standalone. `gastric-next.service` (`:3000`) was not restarted. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`; workstation standalone bak `.next/standalone.bak_20260827_105749_pre_rag_trace`.
- Follow-up: Logged-in doctor click-through was not run here (public login required). After hard-refresh, confirm 本次怎么检索到的 is visible without waiting for LLM.

## 2026-08-27, TENT evaluator and mask-clinical training launch

- Scope: new `scripts/eval_tstage_tent_20260827.py` and background run `maskclin_setmil_tentbase_v1`; training/evaluation only, no public Next change.
- Reason: measure whether entropy-minimization test-time adaptation improves the fixed mask + clinical Ordinal Set-MIL without introducing precomputed features.
- TENT contract: source versus TENT is compared on dev 128 by default. ConvNeXt uses LayerNorm, so adaptation updates normalization affine parameters only; episodic mode resets for every batch. Non-dev evaluation requires an explicit override. PyPI `tent==0.0.3` was rejected because it is an unrelated GitHub automation package.
- Training: GPU 0, 60 fixed epochs, batch 2, accumulation 4, max 12 frames, 256 px, AMP, no early stopping. Output under `pipeline/experiments/reports/tstage_maskclin_ordinal_setmil_20260827/runs/maskclin_setmil_tentbase_v1/`. The first background process was externally aborted after epoch 2; checkpoint resume support was added and validated through epoch 3, then the run continued from epoch 4.
- Validation: realistic CUDA forward/backward smoke passed before launch with RGB, mask, clinical, categorical and ordinal tensors at production dimensions. End-to-end source/TENT CPU smoke passed and adapted 17,900 normalization-affine parameters. Resume restored model, optimizer, scheduler and scaler; epoch 3 completed successfully. Best through epoch 3 was dev QWK 0.606 at epoch 2.
- Deployment: None.
- Result: training completed 60/60. Best dev QWK was 0.638 at epoch 45; best dev ACC was 0.594 at epoch 41; final train ACC 0.950 showed substantial overfitting. On the best-QWK checkpoint, one-step episodic TENT changed ACC 0.5391 to 0.5469 and balanced ACC 0.4815 to 0.4876, but QWK fell 0.6382 to 0.6307, MAE and T2 recall were unchanged. This TENT preset is not promoted.
- Documentation: added the detailed Chinese report `pipeline/experiments/reports/tstage_maskclin_ordinal_setmil_20260827/DETAILED_METHOD_AND_RESULTS_ZH.md` and English companion `FULL_METHOD_AND_RESULTS.md`, covering frozen membership, input-policy deviation, preprocessing, architecture, objectives, resume procedure, key metrics, confusion matrices, TENT method, limitations, reproduction commands, and next-step priorities.
- Follow-up: do not tune TENT steps or LR on 425 / 485. Address overfitting and T2 supervision inside train/dev before any audit run.

## 2026-08-27, Mask + clinical Ordinal Set-MIL trainer

- Scope: new `scripts/train_tstage_ordinal_setmil_20260827.py`; training script only, no model run and no public Next change.
- Reason: prepare a new end-to-end T-stage architecture using lesion mask and raw clinical variables, but no handcrafted geometry or precomputed features.
- Architecture: ConvNeXt-Tiny feature maps feed learned global, mask-region, and strongest-response pooling; patient frames enter a position-free Set Transformer; 11 raw clinical values plus missingness are standardized from train only and fused by a learned gate; categorical and monotonic ordinal heads are trained jointly with consistency loss.
- Data contract: defaults to the official main-center rows and verifies exact membership against frozen train 1,062 / dev 128. Input loading keeps only image, mask, raw clinical/missingness and target columns; it discards `clinical_22`, every `*_norm`, region patches, SDF and geometry caches. No prospective/external audit CLI is exposed.
- Training behavior: full fixed epoch schedule without early stopping; patient bags, deterministic dev frame sampling, AMP, gradient accumulation with correct tail rescaling, separate backbone/head learning rates, class/ordinal weighting, and best-ACC / best-QWK checkpoints.
- Validation: Python compile and IDE lint passed; full 1,062 / 128 membership, all image/mask paths and train-only clinical statistics passed; CPU forward/backward dry-run passed with RGB `[B,F,3,H,W]`, mask `[B,F,1,H,W]`, clinical `[B,22]`, class `[B,4]` and ordinal `[B,3]`. No full training started.
- Deployment: None.
- Follow-up: this is a manual-mask and clinical-assisted research model. Confirm which clinical fields are available preoperatively before any deployment claim; do not inspect 425 / 485 during architecture selection.

## 2026-08-27, WADI T-stage clean development and audit freeze

- Scope: new `wadi_research_freeze_v20260827` task pack and reproducible builder. Training/evaluation governance only; no public Next change.
- Reason: lock the data contract before pursuing 75% exact accuracy. Existing prospective 425 and external 485 are patient-disjoint from development but have already been repeatedly inspected, so they are now explicitly audit-only rather than described as untouched tests.
- Data roles: primary clean baseline is fixed main-center train 1,062 / dev 128; secondary three-center domain-adaptation is train 1,300 / dev 170; temporal audit 425; full external audit 485; unseen-center audit 205. Sensitivity cohorts are temporal 273 / 228 and external 399 / 374 after sequential legacy-train and reader exclusions. A genuinely untouched final test remains pending new post-freeze or new-center cases.
- Leakage controls: T-stage inference input is image only; manual masks are explicitly renamed `gt_lesion_mask_path` and limited to training supervision; any mask-dependent route requires training-patient OOF predicted masks. Clinical/postoperative fields are removed; all train-dev-audit patient overlaps required by each route are 0; image and mask paths complete; source and generated outputs frozen with SHA-256.
- Validation: builder completed; all generated rows have image and mask files; strict train-dev-audit patient overlaps are all zero; generated SHA-256 verification passed; Python compile and lints passed. `audit_task_datasets.py` passed but continued to warn about the separate legacy parent pack. Repository-path checks found 0 missing canonical paths, but returned nonzero because the pre-existing root-hygiene audit lists 39 unexpected entries and 1 discouraged entry.
- Deployment: None. Dataset/training-only.
- Rollback: remove the new versioned freeze directory and builder; prior `maincenter_retrospective_v20260821` and `threecenter_joint_unseen_v20260826` packs are unchanged.
- Follow-up: model selection must use the fixed 128-patient dev only. The 118 image-linked, no-indexed-exposure candidates remain quarantine because exposure completeness is unprovable and T2 count is only 7. Collect and independently seal the future confirmatory cohort before claiming untouched 75% validation.

## 2026-08-26, ResNet18 mean-pool T-stage baseline

- Scope: new trainer `scripts/train_t_stage.py` and report dir `pipeline/experiments/reports/tstage_resnet18_meanpool_20260826/`. Training only. No public Next.
- Reason: strip GUS ablations and run one patient-level line: multi-frame crop_ui, ResNet18, mean pool, T1/T2/T3/T4+ CE. Official 1062/128 split. No early stop.
- Validation: official 1062/128 loaded; no train/val leak. `r18_mean_p0` finished 40/40 on GPU 0. Best val acc 0.5391 at epoch 15.
- Deployment: None.
- Follow-up: do not promote. Locked prospective/external not scored.

## 2026-08-27, GUS m4a4o3_p0 locked-split eval

- Scope: `--eval` of `runs/m4a4o3_p0/best_qwk.pth` (epoch 40) on val 128, prospective 425, external 485. No public Next.
- Reason: First complete locked look after P0 training stopped at late-unfreeze OOM.
- Key numbers (argmax): val QWK 0.654; prospective QWK 0.610 ACC 0.541; external QWK 0.420 ACC 0.505. T2 recall 0.27 / 0.12 / 0.15. Ranking AUROC stays higher than 4-class argmax.
- Validation: complete n on all three splits.
- Deployment: None.
- Follow-up: Late-unfreeze resume still needs a memory fix. Do not retune decode on these locked tables.

## 2026-08-26, GUS P0 fresh train without early stop

- Scope: trainer CLI only. `--early-stopping 0` disables patience stop; default YAML stays 12. New background run `m4a4o3_p0` on GPU 1.
- Reason: Restart after P0 with a full 80-epoch schedule. Do not cut mid/late unfreeze because val QWK plateaus.
- Validation: CLI override; old `m4a4o3_from_ep12` stopped; new nohup job started.
- Deployment: None.

## 2026-08-26, GUS-Mask2Stage P0 training-correctness fixes

- Scope: `pipeline/lib/gus_mask2stage.py`, `scripts/run_gus_mask2stage_20260826.py`, YAML. Training / eval only. No public Next.
- Reason: Static review found alt-mask crop mismatch, leftover grad-accum, `deepest_invasion` leakage, mixed patient IDs, empty-bag loss, and Phase 1/3 score overwrite.
- Key changes: Alt consistency now reuses the primary context crop box. Epoch-end flush of leftover accumulation, scaled by `accum / remainder`. Frame select is keyframe / mask area only. A5 star requires `allow_invasion_oracle`. Patient key is `patient_id_unique` or `source::patient_id`. Empty eval bags raise; train drops empty patients. Phase matrix tags use run-id. Preflight checks all split pairs and pack sizes. `--eval` / `--phase2` require `--run-id` or `--ckpt`. Incomplete locked n fails unless `--limit-eval`.
- Validation: `--preflight` plus a crop-box / patient-key unit check. In-flight `m4a4o3_from_ep12` was not stopped.
- Deployment: None.
- Follow-up: New formal train needs a new `--run-id`. Phase 4 path / true train OOF / geom-cache fingerprint / full ckpt architecture restore remain P1.

## 2026-08-26, BioMedAgent-aligned controlled EvoAssist plan

- Scope: methodology SSOT only. No public Next, no Assist change.
- Reason: Bu et al., Nat Biomed Eng 2026 (DOI 10.1038/s41551-026-01634-6) is the method paper for tool-aware multi-agent orchestration, interactive exploration, memory retrieval, and cross-task evolution. The live workbench must stay a controlled clinical assist system, not an online self-modifying agent.
- Key changes: New `docs/plans/BIOMEDAGENT_CONTROLLED_EVOASSIST_20260826.md` maps five memories and six evolution layers onto current files. `SELF_EVOLVING_RETRIEVAL` and `DUAL_TIMESCALE_EVOASSIST` now point at that plan. Corpus key `biomedagent2026` registered; local PDF already on disk.
- Validation: Docs only. Live Assist remains L3 plus Dual BM. RAG output still cannot become Tent-LN labels. Unreviewed experience still cannot enter production memory.
- Deployment: None.
- Follow-up: Keep collecting `rag_evaluations.jsonl`. Write EXP units offline with `release_status=candidate`. Do not ship eight autonomous agents.

## 2026-08-26, 循证 local AJCC / NCCN copies

- Scope: guideline panel copy, local source files, public Next. Public Next required.
- Reason: The panel was labeled 寻证. Doctors need 循证, and they need to see where AJCC / NCCN live, with a local copy that opens without the official site.
- Key changes: Title is now 循证（指南出处）. The panel lists 指南在哪里 for AJCC 8th Stomach (local PDF), NCCN patient 2026 (local PDF), and NCCN Gastric 3.2026 (local clause HTML; full clinical text stays on nccn.org). Clause chips say 出自 / 本机. `GET /api/reader/guideline-source` serves the local files. Assist probabilities unchanged.
- Validation: `npx tsc --noEmit` exit 0. `:3300` guideline-trace returns 3 library sources, all `local_available`. Source API returns AJCC PDF, NCCN patient PDF, and NCCN clinical HTML. Public smoke `public_root` / `public_clinical` 200; public HTML includes this BUILD.
- Deployment: Public Next BUILD `kGkKHRdc5Ip3aa7EGZyyD`. Workstation `:3300` (`gastric-next-public`) on the same standalone. `gastric-next.service` (`:3000`) was not restarted. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.

## 2026-08-26, Fix public historical-queue 401 for jmr

- Scope: `lib/reader/local-access.ts`, `queue-access-server.ts`, `/api/patients`.
- Reason: Public `jmr` (and other whitelist accounts) could open the queue tree, but switching to a year / external / benign queue toasted `surgery 队列请求失败（HTTP 401）`. Aliyun already admitted the session, then tunneled to workstation `:3300`. That READER_ONLY standalone checked the queue gate before the `x-agent-upstream-admit` bypass, and the public session file is not on the workstation.
- Key changes: Shared `isTrustedPublicUpstream`. Local tunnel requests with the admit header skip the public-queue gate and the later session-store check. Public hosts still require a real login plus the whitelist.
- Validation: `npx tsc --noEmit`. `npx tsx scripts/test_public_upstream_admit.mjs`. Live `:3300` `internal:2018` surgery is 200 (`total=3638`) with admit headers; same URL without admit stays 401. Public smoke `public_root` / `public_clinical` 200.
- Deployment: Public Next BUILD `pXlph4oBU6UDwWueH183Q`. Smoke `public_root` / `public_clinical` 200. Workstation `:3300` (`gastric-next-public`) restarted on the same standalone. Previous standalone kept as `.next/standalone.bak_20260826_224732_pre_queue_admit`. `gastric-next.service` (`:3000`) was not restarted. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*` plus that standalone bak.
- Follow-up: Evaluation sessions remain locked to the reader-study queue. Commit not created because a commit was not requested.

## 2026-08-26, Guideline traces and detailed RAG ratings

- Scope: public workbench similar-case panel, guideline RAG display, case-state / evaluation log. Public Next required.
- Reason: Doctors asked for Feature-embedding similar cases plus traceability: show the specific AJCC / NCCN clause and a source link, not only LLM prose. Public also needed to persist detailed ratings of that RAG, including year-queue T / BM, not only reader v150.
- Key changes: New 寻证 panel lists retrieved guideline cards with publisher, version, and official URLs. Local `/api/reader/guideline-trace` serves the locked corpus on the edge. Assist-judgment still explains, but cards and URLs stay locked. Similar-case marks now write from the panel itself. Session ratings cover 有帮助 / 没帮助 / 不确定 / 有误导, judgment effect, and a note. Events append to `rag_evaluations.jsonl` and case-state. Assist probabilities unchanged.
- Validation: `npx tsc --noEmit` exit 0. Python retrieve for T3 returns 6 cards and AJCC / NCCN URLs. `:3300` `POST /api/reader/guideline-trace` 200 with 6 cards and 3 http citations. Public smoke `public_root` / `public_clinical` 200; public HTML includes this BUILD.
- Deployment: Public Next BUILD `ZdVq1pVh4DWDBx1VNDqnN`. Smoke `public_root` / `public_clinical` 200. Workstation `:3300` (`gastric-next-public`) on the same standalone. `gastric-next.service` (`:3000`) was not restarted. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.

## 2026-08-26, Score acc_boost2 on ZML T keyframes

- Scope: `scripts/score_zml_tstage_accboost2_20260826.py`, report under `pipeline/experiments/reports/zml_tstage_accboost2_20260826/`.
- Reason: User asked to take the official 72% T model and score it on current doctor T-staging keyframes and records.
- Key changes: Pulled public zml CASE-* state (23 completed, one refined polygon each). Ran acc_boost2 and live L3 on those frames. Assist unchanged.
- Validation: 23/23 frames scored. vs zip `reference_pt`: acc_boost2 9/23, L3 14/23, doctor 12/23. vs catalog `src_pT`: 10/23 / 14/23 / 12/23. No similar-case marks on these 23.
- Deployment: None. Do not swap `:8772` to acc_boost2 on this evidence.
- Follow-up: Finish the remaining T 100 before claiming a reader Acc. Keep L3 as the live T head until a video-keyframe model beats it on this pack.

## 2026-08-26, T-stage RAG, benign memory, session refine

- Scope: similar-case index, search, T/BM workbench, Tent-LN left as-is. Public Next required.
- Reason: Doctors only saw always-on RAG on the benign browse queue. BM queries could not retrieve benign history because memory was T-train malignant only. The dual-timescale plan needs a real T panel plus a session-level retrieval loop that does not change Assist numbers.
- Key changes: T year-queue shows the similar-case panel in the right rail. Memory appends train-benign frames (PCA not refit). BM packs live in `by_hash_nature` and sort by nature; T packs stay on T bands. Letterful IDs no longer collapse onto short-digit cancer hashes. Cards add reason chips and「根据反馈继续查找」(channel-pool rerank, not a new encoder). Named `PILOT_READER_V1_TENT_PREF` plus this retrieval slice. Assist probabilities unchanged.
- Validation: `npx tsc --noEmit` exit 0. `PYTHONPATH=pipeline python3 pipeline/similar_cases/test_retrieve.py` ok. Neighbor table: T CASE-042 available; BM-010 nature pack returns 3 benign + 2 malignant. Public smoke `public_root` / `public_clinical` 200; public HTML includes this BUILD.
- Deployment: Public Next BUILD `UCZxcpmb3D7Ga7-KuTvCL`. Smoke `public_root` / `public_clinical` 200. Workstation `:3300` (`gastric-next-public`) on the same standalone. `gastric-next.service` (`:3000`) was not restarted. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`. Index rollback: `runtime/gastric_scan_next/backups/visual_similar_v1_20260826_221828`.

## 2026-08-26, Tent-LN Assist and preference rerank

- Scope: live Assist `:8772`, similar-case search, case-state snapshot. Public Next required for the rerank copy.
- Reason: Ship the requested test-time adaptation and doctor-mark retrieval update. Classic BN TENT does not apply to ConvNeXt; retrieval must not use pathology labels or change Assist probabilities.
- Key changes: Assist runs 2-step LayerNorm entropy min per case, then restores cached weights. Frozen probabilities are stored beside adapted ones. Similar-case lists add a λ=0.05 useful/unlike bias from `doctor_case_state` (`similar_case_preference_v1.json`). Named `PILOT_READER_V1_TENT_PREF`. This starts a new pilot slice; V0 freeze files stay.
- Validation: CPU Tent-LN restore self-check; preference snapshot rebuild from current case-state. `:8772` status `ready` with `tent.method=tent_ln`.
- Deployment: Public Next BUILD `-CconCgYFwHoYK5TMvhS6`. Smoke `public_root` 200. `gastric-reader-analyze` (`:8772`) restarted with `GASTRIC_TENT=1`. Workstation `:3300` on the same standalone. `gastric-next.service` (`:3000`) was not restarted. Hard-refresh http://47.106.33.102 . Rollback: `GASTRIC_TENT=0` plus Aliyun `.next-public-deploy-dist.bak_*`.

## 2026-08-26, Pilot freeze and O3-first execution plan

- Scope: meeting note, execution plan, overlap audit, live-weight manifest. No public UI change.
- Reason: 2026-08-26 discussion mixed live Assist, O3 autopsy, 150 vs 100, TENT, and self-evolving. Those need a frozen pilot name and a patient-level overlap check before more training or narrative claims.
- Key changes: Named `PILOT_READER_V0_20260826`. Recorded live L3 T-stage and Dual BM hashes; O3 is research-only. Reader v150 T arm overlaps official prospective 425 (70 cases) and external 485 (20 cases); official val 128 is 0. Current doctor rounds stay a pilot. Priority is ordinal decode, then ensemble, then TENT or retrieval updates.
- Validation: `python3 scripts/audit_reader_cohort_overlap_20260826.py`. Runtime JSON/JSONL copied under `runtime/gastric_scan_next/backups/`.
- Deployment: None. Public BUILD remains `QrgZkl_XhsjPkvqhi2BIs`. Do not hot-swap Assist during the live T arm.

## 2026-08-26, Queue statistics use review progress

- Scope: `StatisticsPanel`, workbench statistics modal.
- Reason: The old panel ran CBM rules on the whole queue and showed average confidence, high-risk, T4, and N-stage. Those numbers were not the current reader workflow and often stayed at zero.
- Key changes: Stats now join the current queue with this account's `/api/reader/case-state`. Cards show queue size, done / in progress / not started, Assist runs, useful similar-case marks, and saved masks. The bar chart is review status plus the doctor's own T or nature calls. No gold labels, no CBM confidence, no invented metastasis rate.
- Validation: `next build` after Recharts tooltip typing fix. Public smoke `public_root` / `public_clinical` 200.
- Deployment: Public Next BUILD `QrgZkl_XhsjPkvqhi2BIs`. Smoke `public_root` / `public_clinical` 200. Workstation `:3300` (`gastric-next-public`) restarted on the same standalone. `gastric-next.service` (`:3000`) was not restarted. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.

## 2026-08-26, Drop similar-case pathology collapse

- Scope: `SimilarCaseReferencePanel` card footer.
- Reason: After revealing historical pathology, the「收起病理」control was unnecessary.
- Key changes: Reveal stays one-way. Pathology text remains; the collapse button is gone.
- Validation: Lint clean on the panel. Public smoke `public_root` / `public_clinical` 200.
- Deployment: Public Next BUILD `wdtEHBfEe_kF1icdrfHTV`. Smoke `public_root` / `public_clinical` 200; public HTML comment matches. Workstation `:3300` restarted on the same standalone. `gastric-next.service` (`:3000`) was not restarted. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.

## 2026-08-26, Similar-case channel scores and prominent doctor marks

- Scope: `SimilarCaseReferencePanel`, `SimilarCaseInspectViewer`.
- Reason: The inspect rail hid「有对照价值 / 不太像」under clinical facts, and a single「视觉接近」bar did not say whether the lesion, wall, or whole image matched.
- Key changes: Doctor mark is a highlighted「你的判断」block at the top of the inspect rail and on each card. Scores split into 病灶形态, 瘤周层次, 全图外观, and 综合. Still relative retrieval scores, not diagnostic probabilities.
- Validation: Lint clean on the touched files. Public smoke `public_root` / `public_clinical` 200.
- Deployment: Public Next BUILD `HlV4RBExBjq6H_8XqXRiG`. Smoke `public_root` / `public_clinical` 200; public HTML comment matches. Workstation `:3300` (`gastric-next-public`) restarted on the same standalone. `gastric-next.service` (`:3000`) was not restarted. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.

## 2026-08-26, GUS trainer resume and run directories

- Scope: `scripts/run_gus_mask2stage_20260826.py`, `pipeline/lib/gus_mask2stage.py`, config YAML. Training only.
- Reason: The epoch-12 abort could not resume, and a restart would overwrite `best_*.pth` with QWK 0.
- Key changes: Immutable `runs/<run_id>/` with atomic `last.pth` / `best_qwk.pth`. Full resume stores model, EMA, optimizer, scheduler, scaler, RNG, history, and unfreeze phase. Old shared `best_M4_A4_O3.pth` is not written. Each epoch logs pred counts, threshold rates, and diagnostic 0.5-crossing metrics; selection stays argmax QWK.
- Validation: `--help` and import of `monitor_patient_outputs` on the epoch-12 val table. No new training run in this change.
- Deployment: None.

## 2026-08-26, GUS O3 epoch-12 decode autopsy

- Scope: `scripts/diagnose_gus_o3_decode_20260826.py`, reports under `pipeline/experiments/reports/gus_mask2stage_20260826/`. Training analysis only.
- Reason: Epoch 12 never predicted T2/T3 while T2+/T3+/T4+ AUROC were 0.831 / 0.855 / 0.766. Need to locate the collapse before changing the network.
- Key changes: Dump a/q/class probs, compare argmax vs 0.5 threshold-crossing vs expected-stage, and re-forward frames. Finding: collapse is in product-to-argmax (already at frame level). Same `q` with 0.5 crossings yields pred counts 36/9/29/54 and QWK 0.609 on this 128-person val (diagnostic only). A4 top-1 overlap is 59–75%, not the main cause. Loss is unmasked BCE on cumulative `q`, not risk-set BCE on `a`.
- Validation: Script exit 0 on GPU 1 against `best_M4_A4_O3.pth`. Metrics match the epoch-12 history table.
- Deployment: None. Prospective 425 and external 485 stay locked. Public Assist unchanged.

## 2026-08-26, RAG evaluation DTO strip and score wording

- Scope: similar-case search sanitizer, reader card labels, RAG product/acceptance docs.
- Reason: Evaluation JSON still returned same-label / counter roles, so hiding the titles in the UI was not enough. Score bars also read like a diagnosis percent.
- Key changes: Search sanitizes evaluation payloads (no `support_cases` / `counter_cases` / `evidence_role`, no unrevealed pathology). Detects `environment=research` from the body or Referer. Cards say「视觉接近」and「不是诊断概率」. Product note clarifies cache-miss is cached-vector retrieve, not live MedSigLIP. Acceptance follow-up lists remaining HTTPS, signed image access, and server-forced blinding.
- Validation: `npx tsx scripts/test_similar_case_public.mjs` passed. `npx tsc --noEmit` exit 0. Live `:3300` search: daily still returns 3 support + 2 counter; `environment=research` strips `support_cases` / `counter_cases` / `evidence_role` / unrevealed pathology, and `score_note` includes 不是诊断概率.
- Deployment: Public Next BUILD `rjUf1z2Zj1gjlRBE_t5a6`. Smoke `public_root` / `public_clinical` 200; public HTML comment matches. Workstation `:3300` (`gastric-next-public`) restarted on the same standalone. `gastric-next.service` (`:3000`) was not restarted. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.

## 2026-08-26, Public RAG product note

- Scope: `docs/product/公网RAG相似病例与指南解释说明.md`, `docs/DOCUMENT_MAP.md`.
- Reason: Collect live similar-case retrieve, overlay v3, in-place inspect, evidence fusion, guideline explanation, and the Aliyun-to-`:3300` tunnel in one doctor-facing note.
- Key changes: About 5000 Chinese characters. Marks the visual-neighbor path as the public station, and the Agent 28-d memory as research-only. No product code change.
- Validation: Cross-checked against `retrieve.py`, `assist_judgment.py`, `evidence_fusion.py`, overlay v3, and `agent-upstream.ts`.
- Deployment: Docs only. Public BUILD unchanged (`jhY79fUmc_jd5_T5S7K1z`).

## 2026-08-26, Shared mask history and in-place RAG inspect toolbar

- Scope: mask-overrides history API, InteractiveSegPanel history list, SimilarCase inspect viewer.
- Reason: Doctors could only see their own complete-mask versions, and RAG cards still offered a workbench jump.
- Key changes: History lists every account's saved versions for the case, labeled by account. Delete stays owner-only. RAG open stays in place and uses the same viewer toolbar as other queues: original, overlay, split, detection box, peritumoral, ROI, measure, gain.
- Validation: Lint clean on the touched files. Public smoke `public_root` / `public_clinical` 200.
- Deployment: Public Next BUILD `jhY79fUmc_jd5_T5S7K1z`. Smoke `public_root` / `public_clinical` 200; public HTML comment matches. Workstation `:3300` (`gastric-next-public`) restarted on the same standalone. `gastric-next.service` (`:3000`) was not restarted. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Current working mask is still per-account so one doctor does not overwrite another.

## 2026-08-26, GUS-Mask2Stage ordinal loss is AMP-safe

- Scope: `pipeline/lib/gus_mask2stage.py` `gus_loss`. Training only.
- Reason: First `--train` step crashed because `binary_cross_entropy` on `q` is blocked under autocast.
- Key changes: O2/O3 use fp32 manual BCE on probabilities. O0/O1 also compute in fp32.
- Validation: Restart default M4/A4/O3 on GPU 1.
- Deployment: None.

## 2026-08-26, GUS-Mask2Stage geom from the clean full mask

- Scope: `pipeline/lib/gus_mask2stage.py`, `scripts/run_gus_mask2stage_20260826.py`, `pipeline/configs/tstaging_4class_gus_mask2stage_20260826.yaml`. Training only.
- Reason: The previous 24-D geom was computed after context crop and square letterbox, so several channels mainly encoded the crop rule (center near 0.5, margin near 0.237, aspect near 1). Circularity, 1-circularity, and compactness were the same variable. Area mixed pixel counts with contour area.
- Key changes: 12-D geom is now extracted from the original confirmed full-image mask before flip, rotation, scale, mask jitter, or context crop. Features are relative area, perimeter/diagonal, clipped circularity, eccentricity, solidity, convexity, major/minor axis over diagonal, rotated extent, radial CV, radial spread, and centroid offset. Train-fold z-score is cached and reused on val/test. `geom_valid` masks the geom token. Token type embeddings distinguish CLS, views, regions, geom, and radial. M6 omits the geom token. M5 drops frames with invalid geom.
- Validation: Synthetic circle/ellipse sanity check plus `--smoke --gpu 1`.
- Deployment: None. Public Assist and Next are unchanged.
- Follow-up: Geom stays auxiliary. Keep M5 and M6 as shortcut checks. Physical mm sizes need DICOM spacing and are not added here.

## 2026-08-26, GUS-Mask2Stage training entry (image + mask + keyframes)

- Scope: `pipeline/lib/gus_mask2stage.py`, `pipeline/configs/tstaging_4class_gus_mask2stage_20260826.yaml`, `scripts/run_gus_mask2stage_20260826.py`, `pipeline/run_experiment.py` model_type hook.
- Reason: Live Assist still aggregates as single-frame, and the current T head only uses mask as a 4th channel / three-region pool. Need a patient-bag model that matches the doctor workflow: 1-10 keyframes and a confirmed lesion mask, without clinical fields or similar-case votes.
- Key changes: Shared ConvNeXt Tiny encoder, full/context views, signed-distance Core/Inner/Outer/Perilesion pool, trans-boundary radial tokens, threshold-specific Top-K fusion, conditional ordinal T1/T2/T3/T4+. Runner covers plan, preflight, smoke, phase0 re-aggregation of the live mask-pool CORAL checkpoint, train/eval, and later M/A/O/tabular matrices.
- Validation: `--plan` / `--preflight` / `--smoke` on the official maincenter_retrospective_v20260821 pack. Prospective 425 and external 485 stay locked.
- Deployment: Training-only. Public Assist and Next are unchanged. Do not swap the live L3 checkpoint until phase0 and the new val QWK are reviewed.
- Follow-up: Run `--phase0` on val first. Train default M4/A4/O3 only after smoke. TabPFN stays optional phase4.

## 2026-08-26, GUS-Mask2Stage P0/P1 review fixes

- Scope: `pipeline/lib/gus_mask2stage.py`, `scripts/run_gus_mask2stage_20260826.py`. Training only.
- Reason: The first prototype had a broken GPU distance field, treated empty masks as valid frames, let O0/O1/O2 bypass A0-A5, used batch-level class weights, and froze parameters out of the optimizer.
- Key changes: OpenCV signed distance is computed in the dataset; soft Core/Inner/Outer/Perilesion bands use sigmoid intervals and do not force a partition of the whole image. Bad or empty frames are dropped. All ordinal heads read A-aggregated patient tokens; O1 is a shared-score plus monotone-threshold CORAL. Fold-level pos/neg weights, letterbox resize, full+context geometry, clean vs light-alt masks, valid-masked bottleneck/view loss, and B1a/B1b/B1c phase0 modes.
- Validation: `python3 -m py_compile` plus `--smoke --gpu 1` after the patch.
- Deployment: None. Public Assist unchanged.
- Follow-up: Visualize 100 region overlays before training M3/M4. Do not start the full M0-M6 matrix until `--phase0` on val is reviewed.

## 2026-08-26, T-staging LoRA uses official crop_roi

- Scope: `medsiglip/pipeline/medsiglip_gastricus/unfreeze.py`, `preprocess.py`. Training only. Four-class T-staging, not BM.
- Reason: Official `crop_roi` already exists for every row in `maincenter_retrospective_v20260821`. Previous LoRA recomputed a 20% mask box. The BM LoRA that was started by mistake was stopped.
- Key changes: Full view paints the `crop_ui` mask polygon. ROI is the official `crop_roi` image, with `crop_roi/roi_masks` painted when present. Frozen T-staging encode and its 20% cache stay on the plan 2.2 box.
- Validation: T-staging train/val/prospective/external official ROI coverage is 6044 / 733 / 1659 / 2458. `test_bm_sign_pack.py` still covers official ROI load.
- Deployment: None. Public Assist unchanged.
- Follow-up: Report dir `medsiglip/pipeline/experiments/reports/medsiglip_gastricus_unfreeze_lora_20260826/`. GPU1 already holds `gus_mask2stage` plus public SAM, so this run stays on GPU0 with bag batch 4 and 4 dataloader workers to use the leftover 13 GB. Do not promote until prospective and external exact ACC are in.

## 2026-08-26, Complete masks autosave without the save button

- Scope: `InteractiveSegPanel.tsx` reader video toolbar.
- Reason: Doctors still had to tap「保存完整遮罩」after the lesion (and lumen) contour was ready.
- Key changes: Reader queue autosaves the complete mask after SAM / box / refine / workflow. The manual button is a status chip. Video tracking frames are not saved one-by-one.
- Validation: Typecheck after `LumenOverride.lumen_polygon` fix. Public smoke `public_root` / `public_clinical` 200.
- Deployment: Public Next BUILD `ZJ7ac_9hnssTIi4ZDq6u8`. Workstation `:3300` restarted on the same standalone. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: History panel still lists versions. Assist probabilities unchanged.

## 2026-08-26, Historical similar-case inspect reuses queue viewer tools

- Scope: `SimilarCaseInspectViewer.tsx`, `SimilarCaseReferencePanel.tsx`.
- Reason: Opening a card such as REF-D9FCE172 (entire-stomach site, patient closeness 0.82, historical lesion polygon) still used a slim modal. Doctors need the same black queue tools to inspect the historical mark.
- Key changes: Full-screen black inspect. Same overlay and tool chips as the other-queue viewer: outline, peritumoral ring, ROI zoom, measure, gain/contrast, reset, sibling-plane filmstrip. Clinical facts stay on the right rail. Pathology and workbench jump unchanged.
- Validation: Overlay table `similar_case_overlays_v3` (12895 cases, polygons capped at 128 vertices). Workstation `:3300` now serves that table so public retrieve no longer hydrates the old 36-point outlines. `tsc --noEmit` clean. Public smoke `public_root` / `public_clinical` 200.
- Deployment: Public Next BUILD `y0_nuSTGERw4cEW1frfSw`. Overlay v3 copied onto Aliyun `data/` and workstation `:3300` standalone; `gastric-next-public` restarted. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`; restore standalone overlay to v2 if needed.

## 2026-08-26, Shorten public Next stop so deploy 503s do not last 90s

- Scope: `scripts/deploy_public_next.sh`, Aliyun `gastric-next.service.d/stop-timeout.conf`, `docs/technical/GITHUB_ACTIONS_DEPLOY.md`.
- Reason: Today's 15:12 swap left Aliyun `:3000` down for ~90s (SIGTERM hang, then SIGKILL). Auth edge returned `Next workbench upstream unavailable` while `:80` stayed up.
- Key changes: Cap stop at 8s, SIGKILL if the unit is still active, wait for `:3000` before smoke. Drop-in applied on Aliyun without restarting the live workbench.
- Validation: Public `/` and `/workbench/` 200, BUILD `jVBf_R7NYB4PgdhokaX4f`, `gastric-next` / tunnel `18768` / SAM health all reachable. `systemctl show gastric-next -p TimeoutStopUSec` is 8s after daemon-reload.
- Deployment: No Next rebuild. Live BUILD unchanged. Hard-refresh http://47.106.33.102 if a doctor still sees the 503 JSON. Rollback: remove `stop-timeout.conf` and `systemctl daemon-reload`.

## 2026-08-26, Assist judgment shows LLM guideline explanation and references

- Scope: assist-judgment API, `assist_judgment.py`, reader right-rail template card.
- Reason: The accept/decline template only restated signs. Doctors need an LLM note that cites AJCC / NCCN cards under the same block, without changing Assist probabilities.
- Key changes: After Assist, the template stays. A guideline explanation and reference list appear below it. Badge shows LLM vs local template. Public edge tunnels `/api/reader/assist-judgment` to the workstation. No invented papers.
- Validation: Template validator. Typecheck. Live LLM generate returned `source=llm` with AJCC 8th and NCCN Gastric 3.2026 citations. Incomplete half-sentences are dropped.
- Deployment: Public Next BUILD `jVBf_R7NYB4PgdhokaX4f`. Smoke `public_root` / `public_clinical` 200. Workstation `:3300` restarted on the same standalone so the public tunnel can run the LLM. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Literature library stays out of the doctor station. This is explanation, not a second diagnosis.

## 2026-08-26, Public all-queue browse for jmr, why, test, admin, zml

- Scope: `apps/gastric_scan_next/lib/reader/queue-access.ts`, `queue-access-server.ts`.
- Reason: These five public accounts need the full workbench queue tree. Other doctors should stay on the reader-study queue.
- Key changes: `PUBLIC_QUEUE_BROWSERS` is now admin, jmr, why, test, zml (plus admin aliases). UI and API 403 `public_queue_restricted` both follow this list.
- Validation: whitelist unit check. Public deploy smoke `public_root` / `public_clinical` 200.
- Deployment: Public Next BUILD `kFwojWumw7gwYdogxMKog`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: Evaluation sessions remain locked to the reader-study queue.

## 2026-08-26, Evidence-fusion report visible as six glass sections

- Scope: `EvidenceFusionReport`, `ReaderStudyQueuePanel`, similar-case panel chrome, `/api/reader/evidence-fusion` `maxDuration`.
- Reason: Doctors needed to see an LLM contrast report, not a raw pre block that silently stayed on the local template.
- Key changes: Clicking「基于已选病例做证据对照」first paints a local six-section draft, then swaps in the validated LLM report. Badge shows LLM / template. Right-rail cards use black frosted glass. Original Assist probabilities stay locked.
- Validation: `npx tsc --noEmit`. `npm run test:evidence-fusion`. Live LLM generate returned `source=llm`, six sections, original T3 50% unchanged.
- Deployment: Public Next BUILD `4we1xZRyB2aWnMnHLBykH`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: This remains evidence contrast, not a second staging model.

## 2026-08-26, Interactive evidence-fusion MVP (original probs unchanged)

- Scope: `apps/gastric_scan_next` reader right panel, `/api/reader/evidence-fusion`, case-state feedback fields, `pipeline/agent/product/llm_info/evidence_fusion.py`.
- Reason: Doctors need a traceable support / oppose / conflict paragraph from selected similar cases and structured signs, without turning the system into an LLM re-stager.
- Key changes: Persist `similar_case_feedback` and `evidence_fusion` on case-state (refresh restores marks). Structured evidence cards hide unrevealed pathology; evaluation sessions strip 同型/反例 roles. New button「基于已选病例做证据对照」and six-section prose titled「证据对照（不改上方分期概率）」. Template fallback when LLM fails. Assist probabilities are copied verbatim and validated; no `revised_probability` / adjusted risk.
- Validation: `npx tsc --noEmit`. `npm run test:evidence-fusion`. Python CLI template smoke (`run_llm_info_task.py --task evidence_fusion`). Public deploy smoke `public_root` / `public_clinical` 200.
- Deployment: Public Next BUILD `ewDdw7wbe5fGjy6TeJOeN`. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*`.
- Follow-up: This is evidence contrast, not a second staging model. MedSigLIP baselines, useful-case reranker training, and interactive T-stage filters stay offline / phase 2.

## 2026-08-26, Add Assist JSON and model configs to the function spec

- Scope: `docs/product/胃充盈超声智能诊断系统_软件功能说明书.docx` V1.2.
- Reason: The middle chapters needed complete request/response JSON and the live classifier config.json fields, not only prose.
- Key changes: Added 6.7.4/6.7.5 analyze JSON, 7.2 service registry JSON, 7.3.1/7.3.2 Dual ConvNeXt and mask-pool CORAL configs, 7.4.1 similar-case search JSON. Numbers and paths copied from current tools.
- Validation: Regenerated DOCX and rendered pages covering the new JSON blocks.
- Deployment: Docs only.

## 2026-08-26, Expand Assist chapters in the function spec

- Scope: `docs/product/胃充盈超声智能诊断系统_软件功能说明书.docx` V1.1, `scripts/write_reader_workbench_spec_docx.py`.
- Reason: Assist needed the layered story: own-model classify, template prose for accept or decline, own-model embeddings for lesion and full-image neighbors, doctor marks useful cases, RAG popup remains planned.
- Key changes: Sections 6.7-6.10 and 7.3-7.5 now name five layers, gate copy, request steps, report-template paragraphs, Dual ConvNeXt embedding channels (lesion 0.50), and the planned post-Assist picker. No product UI change.
- Validation: Regenerated DOCX. Rendered new Assist pages. No middle-dot characters.
- Deployment: Docs only.

## 2026-08-26, Doctor workbench software function specification

- Scope: `docs/product/胃充盈超声智能诊断系统_软件功能说明书.docx`, `scripts/write_reader_workbench_spec_docx.py`.
- Reason: Doctors and coordinators needed one formal spec of the current reading flow, every visible control, and the models behind Assist.
- Key changes: V1.0 spec in 黑体 headings and 仿宋 body. Covers login, 150-case path, two-round contract, contour tools, classify-only Assist, accept or decline prose, contrastive similar cases, and service ports. Public login page checked live. Inner screens checked against current Next and pipeline source. No product UI change.
- Validation: Regenerated DOCX (仿宋 / 黑体 eastAsia). Rendered 21 pages and reviewed layout. No middle-dot characters.
- Deployment: Docs only. No public Next rebuild.
- Follow-up: Tutorial step 8 still uses older button wording; the spec records the current right-panel labels.

## 2026-08-26, Pin T-stage classifier on CUDA in the warm Assist worker

- Scope: `scripts/serve_reader_analyze.py` on `:8772`.
- Reason: Assist already kept the 1.1 GB binary Dual ConvNeXt resident. The T-stage mask-pool weights were loaded at startup but not pinned or CUDA-warmed, so the first T-staging click still paid graph compile.
- Key changes: Keep process-level refs to both tools. Refuse to go ready unless both models sit on CUDA. Run a dummy T-stage forward (and a best-effort binary forward) during warmup. Status now reports `tstage_device`, `tstage_warm_ms`, and CUDA allocated/reserved MB.
- Validation: Restart `gastric-reader-analyze.service`. Status: `binary_device=cuda:0`, `tstage_device=cuda:0`, dummy binary 2005 ms, dummy T-stage 937 ms, reserved about 738 MB PyTorch / 1172 MiB nvidia-smi. Same dummy T-staging frame on `:8772`: first infer 642 ms, second 33 ms.
- Deployment: Workstation user systemd only. Public Next still tunnels analyze to `:3300` then `:8772`. No Aliyun UI rebuild. Do not expose `:8772`. Rollback: `systemctl --user restart gastric-reader-analyze.service` onto the previous script.
- Follow-up: None.

## 2026-08-26, Contrastive similar-case retrieval

- Scope: `pipeline/similar_cases/retrieve.py`, neighbor table v2, `SimilarCaseReferencePanel`, public Next neighbor JSON.
- Reason: Innovation 2. Flat Top-5 often returned only the same T-stage. Doctors need same-label neighbors and visually close, pathologically different hard counters.
- Key changes: After patient-prototype ranking, keep 3 same-label cards and 2 different-label cards above the 0.06 floor. Cards carry `evidence_role`. Workbench shows 同型对照 / 困难反例. Evaluation keeps a flat list so the current-case label is not leaked. Assist probabilities are unchanged. No majority vote.
- Validation: 7 retrieve unit tests. `scripts/test_similar_case_cards.py` on CASE-001 (3 T1 support, 2 T3/T4b counters, pathology hidden). Neighbor table v2: 1948 hashes, 1940 combined packs have both buckets. `npx tsc --noEmit`.
- Deployment: Public Next BUILD `O9843SpL9k8cTf7CofiJg`. Neighbor JSON rsynced. Smoke `public_root` / `public_clinical` 200. Hard-refresh http://47.106.33.102 . Rollback: Aliyun `.next-public-deploy-dist.bak_*` plus previous neighbor JSON.
- Follow-up: Benign/malignant counters need a nature-labeled memory; the current index is T-staging malignant only.

## 2026-08-26, Warm Assist classify worker on :8772

- Scope: `scripts/serve_reader_analyze.py`, `pipeline/agent/product/analyze_cli.py` / `analyze_case.py` split, Next reader analyze route, user systemd.
- Reason: Admin public Assist waited 8-26 s. Trajectory showed classify-only plus one 100 KB frame; the 1.1 GB Dual ConvNeXt was reloaded on every spawn.
- Key changes: Persistent `:8772` worker keeps binary and T-stage weights in GPU memory. `analyze_case.py` spawned by `:3300` is now a thin sidecar client with local fallback. Next prefers `READER_ANALYZE_UPSTREAM`. Assist probabilities unchanged. Do not expose `:8772` on the public internet.
- Validation: 18 product tests passed. Sidecar ready in 8.8 s warmup, RSS about 1.0 G. Same BM-041 frame: first warm infer 3.4 s, second 29 ms. Thin `analyze_case.py` hop to the sidecar 70 ms. Yesterday cold public clicks were 8-26 s.
- Deployment: Workstation `gastric-reader-analyze.service` only. Public Next still tunnels analyze to `:3300`; no Aliyun UI rebuild. Rollback: `systemctl --user stop gastric-reader-analyze.service` (CLI falls back to cold spawn).
- Follow-up: Rebuild `:3300` standalone later so Next can HTTP the sidecar without the thin Python hop.

## 2026-08-26, BM-001 still zip-only after machine-fingerprint search

- Scope: `benign_malignant/CASES.md`, `dataset/task_datasets/READER_V150_JOIN.md`, `阅片150_原始对照总表` note, `scripts/build_reader_clip_patient_map.py`.
- Reason: User asked to find the hospital-side original for BM-001 (`良恶性鉴别/良性/1.avi`).
- Key changes: Clip is 800x600 msvideo1, 9.518 s, 324 frames, overlay WC / V9-2 / 34Hz / 6.1cm, no burned-in id. Same Philips Chinese overlay family as Dehua `dh122`, but not that clip. No unique size or first-frame hit in gastritis 144, Dehua stills to dh64, registry, or incoming zips. Do not assign hbyz1 or dh01.
- Validation: Zip CRC/MD5; ffprobe; ahash vs unused Dehua 800x600 and 34Hz clips (nearest 63+); incoming zip member size scan.
- Deployment: Docs and lists only.

## 2026-08-26, Template-based assist judgment for doctor accept or decline

- Scope: `ReaderStudyQueuePanel`, `lib/reader/assist-judgment-prose.ts`, public Next.
- Reason: After Assist, doctors only saw a stage or nature chip. They asked for an explainable paragraph on the existing report template, then decide whether to accept it.
- Key changes: The right panel now writes a short 超声所见 / 超声提示 (or BM 超声描述 / 超声提示) from the current box and assist signs. Save buttons are 接受这段判断并下一例 and 不接受，按我的判断保存. The paragraph is logged with the doctor action. Similar cases do not vote. Assist probabilities unchanged.
- Validation: `npx tsc --noEmit` during public build.
- Deployment: Public Next BUILD `V_lDnQ1qqSqDwlsq_kkwt`. Smoke `public_root` / `public_clinical` 200. Hard-refresh http://47.106.33.102 after swap.

## 2026-08-26, Historical similar-case cards draw lesion polygons

- Scope: overlay precompute, similar-case panel, public Next overlay JSON.
- Reason: Historical cards only showed a rectangle. Doctors asked to see the previous case lesion polygon, same thin teal stroke as the current boxing line.
- Key changes: Overlay table now stores a simplified official annotation or mask contour, aligned onto the preview image. Cards and the drawer draw that polygon; the old box is only a fallback when no polygon exists. Assist probabilities unchanged.
- Validation: Overlay table 12396 / 12895 frames have polygons. `python3 scripts/test_similar_case_cards.py` (4 of 5 CASE-001 cards have a polygon). `npx tsc --noEmit`.
- Deployment: Public Next BUILD `TJQFbtUr8KkaaE-iEzr3q`. Overlay JSON rsynced. Smoke `public_root` / `public_clinical` 200. Hard-refresh http://47.106.33.102 after swap.

## 2026-08-26, Reader clip to 200-case patient map at repo root

- Scope: `reader_clip_to_patient_200.csv`, `reader_clip_to_patient_200.md`, `screen200_not_in_reader150.csv`, `scripts/build_reader_clip_patient_map.py`.
- Reason: Need one list of every reader clip, the exact source video, and whether that hospital id is in the 200-case screening table.
- Key changes: BM rows point at `良恶性鉴别.zip`. T rows point at `T分期100例.zip`. Master table `阅片150_原始对照总表.csv` / `.xlsx` (150 rows plus 200-case leftover sheet). BM-035 locked to `7207986-4.wmv`. 43 reader rows / 38 patients overlap the 200-case table. No names.
- Validation: 50 unique BM zip members, 100 unique T zip members. 150 reader clips exist. 149 source videos on disk (BM-001 zip-only).
- Deployment: Docs and lists only.

## 2026-08-26, BM-034 / BM-035 origin clip mapping

- Scope: `benign_malignant/CASES.md`, `zml50_origin.csv`.
- Reason: Reader clips still show machine UI. Origin tables pointed BM-035 at the same 24 s clip as BM-040.
- Key changes: Zip filesize plus duration plus first-frame check. BM-034 = `恶性/9.wmv` = `6391382-4.wmv` (38.28 s). BM-035 = `恶性/10.wmv` = `7207986-4.wmv` (4.80 s). BM-040 stays `恶性/15.wmv` = `7207986-11.wmv`. No folder named 杨百例; source is the Zhuo BM zip plus Foshan legacy videos. Reader `clip_01.mp4` is a remux, not `crop_ui`.
- Validation: Zip byte sizes match the two WMVs. Clip durations match. First frames of BM-035 match `-4`, not `-11`.
- Deployment: Docs and origin CSV only. Public reader clips unchanged.

## 2026-08-26, Patient-level similar-case ranking and quieter UI

- Scope: `pipeline/similar_cases/retrieve.py`, neighbor rebuild, SimilarCaseReferencePanel, workbench chip.
- Reason: Cards were ranking and scoring single frames, so a 0.24 lesion bar still appeared as a reference. The drawer said 匿名, and the 收起辅助分析 chip was noise.
- Key changes: Each historical patient is one prototype (mean of that patient's frames) compared with the query patient's prototype. Only patients above the closeness floor are listed. The card shows one 病人接近 bar. Drawer says 参考病例. The 收起辅助分析 chip is removed. Assist probabilities unchanged.
- Validation: `npx tsc --noEmit`. `PYTHONPATH=pipeline python3 pipeline/similar_cases/test_retrieve.py`. `python3 scripts/test_similar_case_cards.py`. Neighbors rebuilt, 1948 hashes.
- Deployment: Public Next BUILD `SNPAu3Im2jU1zqeWIx6Qp`. Neighbor table rsynced. Smoke `public_root` / `public_clinical` 200. Hard-refresh http://47.106.33.102 after swap.

## 2026-08-26, Similar-case cards show one frame, current mask, and non-negative closeness

- Scope: Similar-case panel, neighbor hydrate, retrieve case grouping, public Next.
- Reason: Extra thumbnails labeled as same-case frames were other scan planes, and sometimes a different dataset ID that only shared a digit hash. Raw whitened cosine can be negative, which looked like a calculation error. Doctors also needed the current lesion mark next to the historical box.
- Key changes: List cards show only the closest historical frame and say it is another patient. Extra planes stay in the drawer as 同病人其它切面, filtered to the exact same patient_id. The current boxed mask is drawn in teal at the top. Scores map to 0–1 relative closeness so negatives are not shown. Assist probabilities unchanged.
- Validation: `npx tsc --noEmit`. `PYTHONPATH=pipeline python3 pipeline/similar_cases/test_retrieve.py`. `python3 scripts/test_similar_case_cards.py`.
- Deployment: Public Next BUILD `bvPB72tFZ6H4CkxYLR1_K`. Smoke `public_root` / `public_clinical` 200. Hard-refresh http://47.106.33.102 after swap.

## 2026-08-26, Hide similar-case exam-year chips

- Scope: `SimilarCaseReferencePanel`.
- Reason: Year plus 内部/外部检查 is not useful on the card and looks like a style label.
- Key changes: Removed that chip from the list and the drawer. Site, scores, and the historical lesion outline stay.
- Validation: `npx tsc --noEmit` during public build.
- Deployment: Public Next BUILD `mrTCUh7_4lRH5WGKtvH_d`. Hard-refresh http://47.106.33.102 after swap.

## 2026-08-26, Similar cases wait for Assist and show historical lesion outlines

- Scope: Reader similar-case panel, DiagnosisPanel gating, overlay precompute, public deploy copy of overlay JSON.
- Reason: Doctors wanted retrieval only when analysis starts, clearer exam labels instead of scan-style wording, and the historical lesion mark drawn like the current thin boxing line.
- Key changes: Panel fetches only after Assist is running or finished. Cards say year plus 内部/外部检查, and `病灶在…`. A 1px teal box from the historical ROI is overlaid on each preview. Pathology stays hidden. Assist probabilities unchanged.
- Validation: Overlay table covers 12892 / 12895 frames; CASE-001 extras all have boxes. `npx tsc --noEmit`. `python3 scripts/test_similar_case_cards.py`.
- Deployment: Public Next BUILD `ittzVOQhg3NL-Uj-MZ5ws`. Overlay JSON rsynced. Hard-refresh http://47.106.33.102 after swap.

## 2026-08-26, Three-center T-staging split aligned with binary seen hospitals

- Scope: `dataset/task_datasets/t_staging/threecenter_joint_unseen_v20260826/`, `scripts/build_tstaging_threecenter_joint_unseen.py`, DATASET_GUIDE / task_datasets pointers.
- Reason: Xiehe must stay in T-staging train. Putian College and CNNC 504 already sit in binary train and have both labels; keeping them only in T external left the two tasks on different hospital sets.
- Key changes: New T contract trains Xiehe retrospective plus Putian and CNNC. Xiehe train/val patients are frozen from `maincenter_retrospective_v20260821`. Tumor hospital and the other externals stay unseen. Binary split is unchanged. The Xiehe-only T pack is not rewritten.
- Validation: Rebuild script leak checks (no patient overlap across splits; no prospective rows in train/val; Putian/CNNC absent from T external). Inventory written next to the CSVs.
- Deployment: Docs and CSVs only. No Next or public analyze change. No rollback of the Xiehe-only pack.
- Follow-up: Train T on this pack only after an explicit run request. Do not point MedSigLIP defaults at it yet.

## 2026-08-26, Enrich similar-case cards and fix short-ID hash collapse

- Scope: `pipeline/similar_cases/ids.py`, metadata hashes, neighbor rebuild, `SimilarCaseReferencePanel`, search hydrate, `DiagnosisPanel` scroll.
- Reason: Short hospital IDs under 4 digits all hashed to the same bucket, so the first card mixed hundreds of patients. Doctors also asked for more case content on the multi-frame cards.
- Key changes: Hash short IDs by their own digits. Rebuild `neighbors.json` (1948 hashes). Cards now show scan style, same-case frames, anonymized age/sex/size/site, lesion vs full-image meters, and a visual match hint. Pathology stays hidden. Assist probabilities unchanged.
- Validation: `PYTHONPATH=pipeline python3 pipeline/similar_cases/test_retrieve.py`; `python3 scripts/test_similar_case_cards.py` (5 distinct cards, previews present, pathology hidden). CASE-001 combined no longer returns a collapsed mega-case. Five of five cards match a clinical table row. `npx tsc --noEmit`.
- Deployment: Public Next BUILD `vprZEwffVcJKi55PEBXTD`. Neighbor table rsynced. Hard-refresh http://47.106.33.102 after swap.

## 2026-08-26, Similar-case multi-frame cards with style and dual scores

- Scope: `SimilarCaseReferencePanel`, `public_case_card` cohort field.
- Reason: Doctors need to see scan style plus lesion vs full-image similarity, and the older multi-frame contact cards, so they can decide whether a retrieved case is worth using. This is still retrieval, not an LLM re-diagnosis.
- Key changes: Contact strip of Top 5; each card shows scan-style chip, main plus same-case extra frames, lesion/full-image meters, and 有对照价值 / 不太像. Pathology stays behind 查看病理结果.
- Validation: `npx tsc --noEmit`. CASE-001 neighbor cards carry year, source group, extra frames, and both scores.
- Deployment: Public Next BUILD `ZckGypEkg5Z7sBG0gXZoA`. Hard-refresh http://47.106.33.102 after swap.

## 2026-08-26, Similar-case GeM, PCA-whitening, and reciprocal rerank

- Scope: `pipeline/similar_cases/` encode/whiten/retrieve, `scripts/refine_visual_similar_index.py`, `scripts/eval_visual_similar_retrieval.py`, neighbor precompute, similar-case panel consistency line.
- Reason: Classification GAP embeddings cluster by T-stage and make almost every pair look similar. Instance-retrieval papers use GeM, train-only PCA-whitening, multi-view concat, and k-reciprocal rerank instead of a second diagnostic model.
- Key changes: Three crops still go through the global backbone, now with GeM (p=3). PCA-whitening is fit on the train memory only (256-d per view, 512-d concat `multiview`). Combined score adds cross-view consistency, average query expansion, and k-reciprocal Jaccard. Pathology stays hidden; Assist probabilities are unchanged.
- Validation: `test_retrieve.py` / `test_crops.py` pass. Same-patient R@5 is 0.77 on multiview vs 0.66 on lesion. Foreign-case T-stage purity is lowest on lesion (0.33), so ranking is not just label collapse. CASE-001 combined returns 5 cards. `npx tsc --noEmit`.
- Deployment: Public Next BUILD `fs6dZ3XNiFVlJg-zwcmOQ`. Neighbor table rsynced. Smoke `public_root` / `public_clinical` 200. Hard-refresh http://47.106.33.102 .

## 2026-08-26, Similar-case retrieval uses three global-backbone crops

- Scope: `pipeline/similar_cases/` encode/crops/retrieve, extract + neighbor precompute, `SimilarCaseReferencePanel` sort tabs.
- Reason: DualBranch local-branch tokens had collapsed (pairwise cosine ~0.9998), so v1 could not rank by lesion ROI. The original plan was three views through one encoder: full image, tight ROI, context ROI.
- Key changes: All three embeddings now come from the global backbone. Tight crop expands the lesion box by 8%, context by 40%. Combined score is `0.20 x global + 0.45 x lesion + 0.35 x context`. Case score is `0.65 x best frame + 0.35 x top-3 mean`, with light MMR. UI default is 综合相似, with 病灶 / 周围组织 / 全图 switches. Still retrieval only; Assist probabilities unchanged.
- Validation: Lesion pairwise cosine mean 0.40 (was 0.9998). `test_retrieve.py` / `test_crops.py` pass. CASE-001 combined returns 5 cards with differentiated scores. `npx tsc --noEmit`.
- Deployment: Public Next BUILD `3tDZ0JSJfIKouZ-QaO9I5`. Neighbor table rsynced. Smoke `public_root` / `public_clinical` 200. Hard-refresh http://47.106.33.102 .

## 2026-08-26, Similar-case retrieval no longer waits on Assist

- Scope: `pipeline/similar_cases/retrieve.py`, `scripts/precompute_visual_similar_neighbors.py`, Next `/api/reader/similar-cases/search`, `SimilarCaseReferencePanel`, `ReaderStudyQueuePanel`, `DiagnosisPanel`.
- Reason: Doctors saw similar cases only after Assist finished and thought retrieval itself took 10+ seconds. CLI and FAISS search are about 0.3s. The wait was Assist (DualBranch / SAM) plus a Python spawn on the public tunnel.
- Key changes: Precompute Top-5 neighbors to `neighbors.json` (alias map, not duplicated packs). Public search reads that JSON first and does not spawn Python or wait for Assist. Pathology stays hidden until 查看结果. The similar-case panel mounts after the initial call, above the Assist button. This is still retrieval, not a second diagnosis model.
- Validation: `PYTHONPATH=pipeline python3 pipeline/similar_cases/test_retrieve.py`; CASE-001 fused lookup returns 5 cards; `npx tsc --noEmit`.
- Deployment: Public Next BUILD `3LXRN0vGfmx6gsONLk9Na`. Smoke `public_root` / `public_clinical` 200. Neighbor table rsynced to public `data/`. Hard-refresh http://47.106.33.102 .
- Follow-up: Preview JPEGs still come through the workstation tunnel. Do not rank by lesion-only. Do not let similar cases rewrite Assist probabilities.

## 2026-08-25, Fix 401 on public other-queue patient lists

- Scope: `lib/agent-upstream.ts`, `/api/patients`.
- Reason: Admin/zml other-queue lists are proxied to workstation `:3300`. The public session token is not in the workstation store, so surgery and NAC both returned 401.
- Key changes: Proxied requests send `x-agent-upstream-admit`. Workstation admits local tunnel requests that already carry a public session header.
- Validation: `npx tsc --noEmit` after the edit.
- Deployment: Workstation `:3300` `dICx8nqzLDrL_TOLD5bB9` (surgery/NAC local 200 with a public session header). Public Next BUILD `OXBL5y8jU08Zkk3n9pli4`. Smoke `public_root` / `public_clinical` 200. Hard-refresh http://47.106.33.102 .

## 2026-08-25, Public queue tree limited to admin and zml

- Scope: `lib/reader/queue-access.ts`, PatientList, similar-case open-in-workbench, `/api/patients` / images / videos.
- Reason: Public doctors should stay on the reader-study queue. Only admin and zml may browse other queues on the public site.
- Key changes: Public UI hides `QueueTreeSelect` unless the signed-in account is admin or zml. Evaluation (`environment=research`) stays locked. API returns 403 `public_queue_restricted` before the workstation proxy. Regular doctors can still open anonymized similar-case drawers, but cannot jump queues.
- Validation: `npx tsc --noEmit`.
- Deployment: Public Next BUILD `rhyfeFrQocu84z3XpWtsY`. Smoke `public_root` / `public_clinical` 200. Hard-refresh http://47.106.33.102 .
- Follow-up: LAN `:3000` is unchanged and still shows all queues.

## 2026-08-25, Public queues, anonymized similar-case clinical, Assist-time retrieval

- Scope: public workbench queues, `ClinicalHistoryCard`, `DiagnosisPanel`, `SimilarCaseReferencePanel`, `/api/reader/similar-cases/profile`, `/api/patients` clinical attach, public-to-workstation proxy for patients/images/videos.
- Reason: Public doctors need every queue. Evaluation (`environment=research`) stays locked on the reader-study queue. During Assist, historical similar cases should appear on the right with anonymized age, site, and labs so the doctor can open a reference case and compare. This is still retrieval, not a second diagnosis model.
- Key changes: `NEXT_PUBLIC_READER_ONLY` no longer hides the queue tree. Research sessions stay on `reader:reader_v150`. Non-evaluation queues attach clinical history (age, sex, size, site, CEA, CA19-9). Similar-case cards open an anonymized drawer; pathology stays behind 查看结果. Evaluation cannot jump queues from a reference case. Public Next proxies other-queue media to workstation `:3300`.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. Retrieve public card still omits hospital IDs. Clinical table lookup covers the visual-memory rows that have a queue match.
- Deployment: Public Next BUILD `0Y0F1xpvvYDrQcVInAa6x`. Workstation `:3300` standalone `b1k9j1yVrFBndzaNWqYQc` (`gastric-next-public` restarted). Local profile/patients 200 with anonymized age/CEA and no hospital ID on the card. Smoke `public_root` / `public_clinical` 200. Hard-refresh http://47.106.33.102 .
- Follow-up: Do not rank by lesion-only until that embedding is fixed. Do not show cosine as a percentage. Do not let similar cases rewrite Assist T-stage probabilities. Commit not created because a commit was not requested.

## 2026-08-25, Historical similar-case reference (visual embeddings)

- Scope: `pipeline/similar_cases/`, `scripts/extract_visual_similar_case_embeddings.py`, `scripts/retrieve_visual_similar_cases.py`, Next `/api/reader/similar-cases/search` and `/image`, `SimilarCaseReferencePanel` on the reader queue and T-staging evidence rail.
- Reason: Restore similar-case support as embedding retrieval of historical reference cases, not a second diagnostic RAG. Assist probabilities stay unchanged.
- Key changes: Phase-0 acc_boost2 DualBranch image-only embeddings; train-only FAISS memory (7874 frames, 830 cases); query cache includes val/prospective/external; same-patient exclusion and case-level max aggregation; scores shown as cosine values, not percentages; pathology hidden until 查看结果; no LLM diagnosis text. Local-branch tokens collapsed (pairwise cosine ~1.0), so v1 ranks by fused then full-image, not lesion-only.
- Validation: `PYTHONPATH=pipeline python3 pipeline/similar_cases/test_retrieve.py`; retrieve smoke on a mapped reader case; `npx tsc --noEmit` pass.
- Deployment: Public Next BUILD `auOFck--hYxDSiFvBlQl_`. Workstation `:3300` standalone restarted (`2PN-XZtBMvOfVA25K57CP`) so the public tunnel can search the local index. Smoke `public_root` / `public_clinical` 200; local search/image 200. Hard-refresh http://47.106.33.102 .
- Follow-up: Doctor blind rating of Top 5 (fused vs full-image vs later MedSigLIP). Do not turn this into a vote that rewrites T-stage probabilities. Commit not created because a commit was not requested.

## 2026-08-25, LLM info / report isolation for Round2 main study

- Scope: `docs/clinical_validation/llm_info_v1/`, `pipeline/agent/product/llm_info/`, `apps/gastric_scan_next/lib/llm-info/`, reader compare/final-judgment UI, `/api/reader/llm/report`, Assist analyze route, `analyze_case._maybe_llm_synthesis`, Round2 export columns, `study-contract` rule/prompt versions.
- Reason: Keep LLM from becoming a second diagnosis model. Decision-front shows vision probabilities + rule compare only; report text runs after doctor final judgment and must not receive AI probabilities.
- Key changes: Frozen contracts; deterministic consistency rules; DoctorAiComparePanel + FinalJudgmentPanel (four-tier reference, confidence 1–5); isolated report API with template fallback + forbidden-phrase/schema gates; legacy `llm_reasoning` stripped from doctor-visible Assist; evidence summary API gated off; 100-case offline replay gate passed; shadow report drafts audited by default.
- Validation: `python3 -m unittest agent.product.llm_info.test_llm_info`; `scripts/llm_info/offline_replay_gate.py --n 100 --shadow` → `pass_gate=true`.
- Deployment: Public Next via `bash scripts/deploy_public_next.sh` BUILD `s0CNKc_XN6Vw4JTbZpUD5`. Smoke `public_clinical` 200; hard-refresh http://47.106.33.102 .
- Follow-up: Set `NEXT_PUBLIC_LLM_INFO_SHADOW_MODE=0` only after shadow latency/hallucination review. Do not enable evidence-summary free text in main-study UI.

## 2026-08-25, BM-sign pack and GastricUS BM train

- Scope: `medsiglip/pipeline/medsiglip_gastricus/bm_sign_pack.py`, `prepare_bm.py`, `encode_bm.py`, `train_bm.py`; Assist payload `bm_report` in Next analyze and `BinaryClassificationTool`.
- Reason: Benign report ticks (site, max diameter, max thickness, ulcer, wall layers) were form-only. Clinical-11 does not take ulcer or wall, and its location codebook is 4 codes, not 9 sites.
- Key changes: New 5-field BM-sign pack, encoded as 10 numbers. Assist now sends the filled form. Current Dual weights still ignore it (`bm_sign_used=false`). GastricUS BM encode/train started on the joint-unseen BM split (image + clinical-11 + BM-sign5, 2-class). Do not impute ulcer/wall from the gold label.
- Validation: `PYTHONPATH=pipeline python3 -m medsiglip_gastricus.test_bm_sign_pack`. Prepare wrote four resolved CSVs. Train fill: size on most malignant rows; 9-site 199 and ulcer 219 (benign US text only); wall layers 0.
- Deployment: Public Next BUILD `-KDcu9argNULJTkIkIjk5`. Smoke `public_root` / `public_clinical` 200. Dual logits unchanged until the GastricUS BM head is scored and pointed at Assist. Hard-refresh http://47.106.33.102 .
- Follow-up: Wait for `logs/bm_gastricus_20260825.log`. Promote Assist only after unseen-center patient AUC/Acc. Doctors should fill the five fields before Assist if they want those ticks in the next head.

## 2026-08-25, GastricUS training-log and result figures

- Scope: `medsiglip/scripts/plot_gastricus_training_results.py`, `medsiglip/results/visualizations/tstage/`, pointer in the results note.
- Reason: Need one place to see train curves, lock epochs, held-out ACC/T2, confusion, seed scatter, AI-v2 OOF vs held-out, and the 10-cell grid.
- Key changes: Plot from existing `metrics.json` history and eval. Black background, Times New Roman. CLI and models unchanged.
- Validation: Script exit 0. Eight png/pdf pairs plus FIGURES.md. Numbers match the 20260825 reports.
- Deployment: Local figures only. No Next rebuild.
- Follow-up: Rebuild with the same script after E4.

## 2026-08-25, Prefer doctor roi_masks in the BM ZML-holdout pack

- Scope: `scripts/build_binary_zmlholdout_clinmask_20260825.py`, pack under `benign_malignant/`.
- Reason: Dual trained on GrabCut then tested on ZML doctor polygons. Need the same doctor-mask protocol at train time where `crop_ui/roi_masks` exist.
- Key changes: Prefer full-frame doctor masks; inflammation rows without them keep box GrabCut. `mask_source` records the choice. Start Dual + mask + age/sex train after rebuild.
- Validation: Doctor masks match image size. Train still has a mask on every row. ZML leak checks stay zero.
- Deployment: Local train only. Assist unchanged until `test_zml` Acc @0.5 is scored.
- Follow-up: Score `test_zml` and `test_external` after `binary_zmlholdout_clinmask_dual_20260825_20260825_212949` finishes. Do not promote Assist until those numbers are in.

## 2026-08-25, AI-v2 Situation A OOF stackers (E1-E3)

- Scope: `medsiglip/pipeline/medsiglip_gastricus/aiv2_stack.py`, CLI `aiv2`, `GastricUS_AIv2训练方案.md`, results note.
- Reason: Need a T2-safe ensemble without training on prospective/external or picking a lucky seed.
- Key changes: 5-fold patient OOF on train 1062 for default, best, and clinical-only. Fit mean / simplex / L2 logit stackers on OOF only. Lock rule prefers T2 recall >= 0.20, then ACC. Picked e3. Held-out after lock: 0.6165 / 0.5381, T2 0.176 / 0.209. CLI unchanged.
- Validation: OOF oracle default vs clinical-only = 0.707. e1 three-member held-out ACC 0.6471 is not selectable (OOF T2 0.096). No patient IDs in the report.
- Deployment: Docs and local reports only. No Next rebuild.
- Follow-up: E4 residual late fusion with threshold and distance losses. Do not reopen 1152-d fusion sweeps.

## 2026-08-25, Phase 1 GastricUS boundary audit

- Scope: `medsiglip/pipeline/medsiglip_gastricus/phase1_boundary.py`, CLI `phase1`, report `medsiglip_gastricus_phase1_boundary_20260825/`, results note.
- Reason: Need McNemar, bootstrap, per-center, and hierarchical cuts before changing the default or opening another fusion sweep.
- Key changes: Audit existing prediction CSVs. Default vs 5.1 x 6.2: prospective p = 0.084, external p = 0.008. External gain is mostly putian_college (213). T2 recall on the best cell stays near 0. Hierarchical T1 vs T2+ is already about 0.84-0.87. CLI default unchanged. Extra-seed retrain started (`--phase1-seeds`).
- Validation: 9 models, 16 McNemar pairs, 2000-patient bootstrap. Counts match the plan-complete prediction CSVs. No patient IDs in the report.
- Deployment: Docs and local reports only. No Next rebuild.
- Follow-up: Extra seeds finished. Default MLP mean 0.5876 / 0.5005; 5.1 x 6.2 mean 0.6182 / 0.5428. The 0.6424 / 0.5856 cell is the 20260821 upper end, not a stable ceiling. Next is token-level representation, not another 1152-d width sweep.

## 2026-08-25, Add GastricUS bottleneck and next-step ledger

- Scope: `medsiglip/GastricUS实验方案_各节实现与结果.md`.
- Reason: Need one place that separates evidenced bottlenecks from inference, and that does not re-open width / ROI / crude-spatial sweeps.
- Key changes: Add 瓶颈（8 evidenced, 5 inferred）, 下一步 eight priorities, a three-stage order, and an overall judgment. Record that spatial 2304-d and layers4 means already failed, so the open item is token-level region interaction. 0.6424 / 0.5856 stays a candidate baseline pending McNemar and multi-seed.
- Validation: Numbers copy the same COMPARE / EXPERIMENT_RECORD cells as the rest of the note. No new training.
- Deployment: Docs only. No Next rebuild.
- Follow-up: First stage is stability and error audit, not another xlarge width sweep.

## 2026-08-25, Expand GastricUS ledger with background, data, goals

- Scope: `medsiglip/GastricUS实验方案_各节实现与结果.md`.
- Reason: The consolidated note still opened at metrics. Need the clinical problem, why this workspace exists, the 0.75 bar, and the full data makeup in the same file.
- Key changes: Add 问题背景 (CCUS T staging, T2/T3, Dual leak, why freeze MedSigLIP), 研究目标 (0.75 vs human-read 75.5%, success/fail rules), and 数据构成 (2100 patients / 10894 frames, year and 9-center tables, crop_ui extras, full 11-field missing, Phase 0 delta). Later section numbers unchanged.
- Validation: Patient/frame/T counts match `inventory.json` and EXPERIMENT_RECORD §1. Clinical missing matches that record. Liang 2024 75.5% is the cited human-read reference, not a model score.
- Deployment: Docs only. No Next rebuild.
- Follow-up: Keep this file as the results SSOT when new waves land.

## 2026-08-25, Expand GastricUS section-results note into one ledger

- Scope: `medsiglip/GastricUS实验方案_各节实现与结果.md`.
- Reason: Plan results, data contract, grids, retry sweep, and can/cannot-say claims lived in several MDs. Need one complete note.
- Key changes: One file now holds sections 1-6, split/clinical contract, default hyperparams, 10-cell grid, historical waves, plan-literal, 2026-08-25 retry, confusion matrices for default and best cells, and command list. Numbers still copied from SUMMARY / COMPARE.
- Validation: Counts match `plan_complete_20260825/COMPARE.md`, `retry_20260825/COMPARE.md`, and EXPERIMENT_RECORD patient tables.
- Deployment: Docs only. No Next rebuild.
- Follow-up: Keep this file as the results SSOT when new waves land.

## 2026-08-25, MedSigLIP retry sweep: new fusion, pool, ROI mixes

- Scope: `medsiglip/pipeline/medsiglip_gastricus/model.py` (`gate`, `pair`, `mean_u`, `attn_only`, `mid`), `mix_expand.py`, `train.train_retry_sweep`, report `medsiglip_gastricus_retry_20260825/`.
- Reason: Bigger frozen heads already failed. Need other axes: 15/25% with the winning 5.1 x 6.2 cell, mixed ROI tokens, and lighter structure changes.
- Key changes: Per-frame view gate and two-token attention; mean-of-fused-u and attention-only pooling; mid-size 2-layer frame transformer (~20M). New caches average or area-pick 15/20/25 ROI tokens. CLI default unchanged.
- Validation: 12 runs, frozen cache. Best new cell is TabPFN mean on 25% ROI (0.6353 / 0.5649), below the 20% 5.1 x 6.2 cell (0.6424 / 0.5856). Gate/pair/mid did not beat default gated MLP on both ends.
- Deployment: Local workspace only. No Next rebuild.
- Follow-up: Do not promote. Frozen 1152-d plus head/ROI remix is not a path to 0.75.

## 2026-08-25, Pack GastricUS code plus parent and workspace results

- Scope: `medsiglip/scripts/pack_gastricus_code_and_results.py`; desktop folder `GastricUS_code_and_results_20260825`.
- Reason: Need one offline pack with the current plan-aligned code, the 2026-08-25 workspace waves, and the parent-repo ledger that already held Dual and earlier MedSigLIP runs.
- Key changes: Packer copies workspace package + parent package/scripts/yaml, slim workspace reports (no `.pt` / prediction CSV), and the existing parent `gastricus_ledger`. Index maps plan sections 1-6 to files.
- Validation: Dest has 12 docs, 31 workspace code files, 71 parent files, 34 workspace result files, 809 ledger files. Zip 2.3 MB. No checkpoints or prediction CSVs.
- Deployment: Desktop pack only. No Next rebuild.
- Follow-up: Re-run the packer after new waves. Default dest is `~/Desktop/GastricUS_code_and_results_<date>/`.

## 2026-08-25, MedSigLIP plan section-by-section results note

- Scope: `medsiglip/GastricUS实验方案_各节实现与结果.md`; pointers from `GastricUS实验方案.md` and the section-1 methods MD.
- Reason: Need one note that maps plan sections 1-6 to what was implemented and the held-out exact ACC already on disk.
- Key changes: New summary only. No train, encode, or CLI default change.
- Validation: Numbers copied from `plan_complete_20260825/COMPARE.md`, expand 15/25, plan-literal, and largeclf reports.
- Deployment: Docs only. No Next rebuild.
- Follow-up: Default stays xlarge concat + gated + MLP. Best grid cell remains 5.1 x 6.2 (0.6424 / 0.5856). Target 0.75 not reached.

## 2026-08-25, Open benign_malignant workspace and ZML-holdout pack

- Scope: `benign_malignant/`, `scripts/build_binary_zmlholdout_clinmask_20260825.py`, `scripts/run_binary_zmlholdout_clinmask_20260825.py`.
- Reason: Retrain BM with mask and age/sex. Need a folder like `medsiglip/`, and a pack that does not train on the ZML 50-case reader set.
- Key changes: Workspace holds README, plan, yaml, and CSVs. Pack copies B box+mask rows, joins age/sex, drops train/val patients that overlap ZML, adds `test_zml`. Images stay in `dataset/`.
- Validation: Leak checks all zero. Train 5046/1021, val 915/183, test_zml 52/50. Train clinical complete 0.950. Missing image/mask 0. Runner `--dry-run` pending.
- Deployment: Local data only. Do not start train in this step. Assist unchanged.
- Follow-up: Train Dual + mask4ch + age/sex when asked. Claim is `test_zml` patient Acc @0.5; still report `test_external` AUC.

## 2026-08-25, MedSigLIP wide classifier vs TabPFN on frozen cache

- Scope: `medsiglip/pipeline/medsiglip_gastricus/model.py` (`wideclf`), `train.train_largeclf_compare`, report `medsiglip_gastricus_largeclf_tabpfn_20260825/`.
- Reason: Test whether a larger 6.1 MLP head can beat TabPFN without unfreezing MedSigLIP.
- Key changes: `wideclf` keeps 4.1/5.3 xlarge widths and widens only the patient MLP (about 25.4M). Four-run compare: xlarge MLP, wideclf MLP, gated TabPFN, mean-view TabPFN.
- Validation: Same 20% cache. Held-out exact ACC: mean TabPFN 0.6424 / 0.5856; xlarge MLP 0.5812 / 0.5381; wideclf 0.5106 / 0.5093; gated TabPFN 0.5529 / 0.4495. Do not promote wideclf.
- Deployment: Local workspace only. No Next rebuild.
- Follow-up: Bigger frozen-head MLPs are not a path to 0.75. CLI default stays xlarge MLP.

## 2026-08-25, MedSigLIP plan section 2/3 preprocess and encode

- Scope: `medsiglip/pipeline/medsiglip_gastricus/preprocess.py`, `encode.py`, section-1 methods MD, plan §2/§3 pointers.
- Reason: Plan sections 2 and 3 (official 448 processor, mask-bbox ROI, frozen 1152 cache) lived only as helpers inside `encode.py`. Need a plan-aligned preprocess module and a hard freeze / processor contract.
- Key changes: New `preprocess.py` owns full-frame RGB, mask bbox, expand/pad, and `assert_processor`. `encode.load_frozen_encoder` sets `eval` plus `requires_grad_(False)`, checks 1152-d, and logs failed rows. `--mask-bbox largest` is available but cannot overwrite the 20% all-nonzero cache.
- Validation: Dummy bbox and processor-contract checks. Existing 20% npz unchanged.
- Deployment: Local workspace only. No Next rebuild.
- Follow-up: Do not re-encode the default cache unless a new dest is intended.

## 2026-08-25, MedSigLIP default head is deep residual + frame transformer

- Scope: `medsiglip/pipeline/medsiglip_gastricus/model.py`, `train.py`, `scripts/run_medsiglip_gastricus.py`.
- Reason: The frozen-cache MLP (xlarge, about 12M) was too thin for the 0.75 exact-ACC target. Need more downstream capacity without changing the four CSVs or the 20% encode cache.
- Key changes: New `--size deep` is the default. Concat fusion stacks two extra 1024 residual blocks. Gated pool first runs a 4-layer 8-head frame transformer, then 8-head gated + mean + max to 1024-d. Patient head is a residual 2048/1024/512 MLP. Reports go to `medsiglip_gastricus_deep_20260825/`. Plan-sweep stays on xlarge so the 10-cell grid is not overwritten.
- Validation: Dummy forward ok (101,112,844 params). Train locked epoch 49, val exact ACC 0.5547. Held-out: prospective 0.4682 / external 0.4763, worse than xlarge 0.5976 / 0.5216. CLI default stays xlarge.
- Deployment: Local workspace only. No Next rebuild.
- Follow-up: Do not promote deep. Extra MLP / transformer width on frozen 1152-d overfits the n=128 val lock and does not reach 0.75.

## 2026-08-25, MedSigLIP workspace crop_ui matches mainline trees

- Scope: `medsiglip/dataset/**/crop_ui`, `medsiglip/scripts/refresh_workspace_copy.py`, `medsiglip/COPY_MANIFEST.json`.
- Reason: The scratch copy only kept freeze frames listed in the four clean CSVs. Mainline `crop_ui` trees were larger (2018 +548, 2019 +621, 2020_2023 +49, 2024 +234, 2025 +771). Need the trees complete without changing the training contract.
- Key changes: Rsynced full mainline `crop_ui` (images, masks, overlays, annotations) into the workspace. Refresh now copies whole `**/crop_ui` trees instead of CSV-used files only. Four clean CSVs, 20% encode cache, and train/eval paths are unchanged.
- Validation: Internal image counts now match mainline (3638 / 2853 / 199 / 1539 / 2430). External `crop_ui` file counts match. `train.csv` / `val.csv` / `test_prospective.csv` / `test_external.csv` byte-equal to mainline (6044 / 733 / 1659 / 2458). Extra internal frames on disk: 2223, none added to the modeling tables.
- Deployment: Local workspace only. No Next rebuild.
- Follow-up: Do not rebuild `maincenter_retrospective_v20260821` just to include unused freeze frames.

## 2026-08-25, Export ZML public records to a BM keyframe test pack

- Scope: `scripts/export_zml_reader_testset.py`, pack `pipeline/data/binary_zml_reader_20260825/`.
- Reason: Public ZML finished BM-001..050. Need the remote case-state, masks, and keyframe polygons on the workstation as a labeled test set with video frames and overlays.
- Key changes: One script rsyncs Aliyun runtime (ops, case_state, mask/lumen), merges ZML rows into `runtime/gastric_scan_next/`, seeks each keyframe in `clip_01.mp4`, writes image/mask/overlay/ROI plus `test.csv`.
- Validation: 50/50 BM cases, 52 frames (one case has 3 keyframes), gold 25 benign / 25 malignant, no missing BM ids. Overlay spot-check BM-001 and BM-034.
- Deployment: Local pack only. Do not train on this split; it is a reader holdout.
- Follow-up: Score Dual boxmask and 101708 on `test.csv` if a same-frame Assist comparison is needed.

## 2026-08-25, BM Assist uses Dual + mask4ch

- Scope: `pipeline/agent/tools/binary_classification_tool.py`, `pipeline_adapter.py`, `agent_backend_registry.yaml`.
- Reason: Public zml BM Assist was a 3-channel crop (or full frame before 11:39). Doctors had SAM masks; the head ignored the shape channel. Dual boxmask weights were trained and sitting unused.
- Key changes: L0 now loads `binary_noshortcut_b_boxmask_dual_20260825` first. Global is full RGB + lesion mask as channel 4; local is the doctor/SAM box. Classify-only also forwards clinical-11 and `patient_id`. These Dual weights have `clinical_dim=0`, so clinical does not enter logits. GastricUS MedSigLIP + clinical-11 stays T-staging, not a BM substitute.
- Validation: `python3 -m agent.tools.test_binary_classification_tool` and `python3 -m agent.product.test_classify_only_adapter` from `pipeline/`. Dummy Dual forward with a mask reports `used_mask_channel=true`, `clinical_used=false`.
- Deployment: Analyze is spawned from this repo on each Assist click. No Next rebuild. Next public Assist click uses Dual + mask4ch.
- Follow-up: A GastricUS-style BM head (frozen MedSigLIP full+ROI + clinical-11) is a new train, not a product switch. Do not point BM Assist at the 4-class T GastricUS checkpoint.

## 2026-08-25, BM box+mask dual finished; unseen AUC 0.774

- Scope: pack `pipeline/data/binary_box_mask_20260825`, run `binary_noshortcut_b_boxmask_dual_20260825_20260825_115508`, `scripts/score_binary_multicenter_unseen.py`.
- Reason: Live BM ignored the doctor box and had no shape channel. A/B full-frame retrains missed official AUC 0.733.
- Key changes: GrabCut masks on the B pack (9763, ok_rate 1.0). Dual: local doctor ROI, global full+mask4ch. Official unseen patient @0.5: AUC 0.774, Acc 0.678, Sens 0.562, Spec 0.770.
- Validation: Same 404-patient `test_external` as 101708. Beats baseline AUC/Acc/Sens. Prospective remains a center lock. Tumor / Foshan still weak.
- Deployment: Product Assist still uses cropped 101708. Dual weights are not live (tool is 3ch single-branch).
- Follow-up: Wire dual + mask4ch into `BinaryClassificationTool` before any product switch.

## 2026-08-25, MedSigLIP workspace exposes google/medsiglip-448

- Scope: `medsiglip/google/medsiglip-448`, refresh script hardlink.
- Reason: Official Google weights were only under `artifacts/model_weights/medsiglip-448/`. Need the Hugging Face id path visible in the scratch workspace.
- Key changes: Hard-linked the same 3.3G `model.safetensors` (3513309984 bytes) to `google/medsiglip-448/`. Encode still reads `WEIGHT_DIR`.
- Validation: Same inode as the artifacts copy; `config.json` is `SiglipModel`.
- Deployment: Local workspace only. No Next rebuild.
- Follow-up: None.

## 2026-08-25, MedSigLIP section-1 methods add key code

- Scope: `medsiglip/GastricUS实验方案_第1节方法实现.md`.
- Reason: The methods note needed the live encode / fusion / bag / head snippets next to each flowchart box.
- Key changes: Added current-file citations for `expand_roi`, `encode_images`, `ConcatFusion` / `FrameFusion`, `MeanViewPool`, `GatedAttentionPool`, `_image`, `PatientBagDataset`, `clinical22_to_nan11`, `PatientHead`, ordinal loss, and CLI defaults.
- Validation: Line ranges match the files as of this edit.
- Deployment: Docs only. No Next rebuild.
- Follow-up: None.

## 2026-08-25, MedSigLIP section-1 methods write-up

- Scope: `medsiglip/GastricUS实验方案_第1节方法实现.md`; links from `medsiglip/README.md`, `GastricUS实验方案.md`, `PLAN_MAPPING.md`.
- Reason: Need a concrete methods note for plan section 1 (dual view, frozen MedSigLIP, fusion, bag pool, clinical, MLP / TabPFN) with tensor shapes, defaults, and the 10-cell grid numbers.
- Key changes: Wrote the implementation of the section-1 flowchart from the live encode / model / train / TabPFN code and `plan_complete_20260825/COMPARE.md`.
- Validation: Counts match the clean four-way split and COMPARE.md. No patient identifiers.
- Deployment: Docs only. No Next rebuild.
- Follow-up: None.

## 2026-08-25, MedSigLIP experiment scripts annotated against the plan

- Scope: `medsiglip/scripts/run_medsiglip_gastricus.py`, `medsiglip/pipeline/medsiglip_gastricus/{__init__,constants,encode,model,train,tabpfn_clinical,resolve_frames}.py`.
- Reason: Need the experiment scripts to cite `GastricUS实验方案.md` sections 2-6 so flags and modules map one-to-one.
- Key changes: File headers, class/function docstrings, and CLI help now name plan 2/3 encode, 4.1/4.2 fusion, 5.1-5.3 pool, 6.1/6.2 heads. Extras are marked as not in the plan. No behavior change.
- Validation: `python3 -c` import of `train` / `GastricUSFromScratch` / `encode` and CLI `--help`.
- Deployment: Local workspace only. No Next rebuild.
- Follow-up: None.

## 2026-08-25, MedSigLIP plan grid aligned and complete train started

- Scope: `medsiglip/pipeline/medsiglip_gastricus/{train,model,constants}.py`, `medsiglip/scripts/run_medsiglip_gastricus.py`, `PLAN_MAPPING.md`.
- Reason: CLI default was concat / 2e-4, but `train()` and the model class defaulted to interact / 3e-4. `--plan-sweep` silently downgraded xlarge to large and only ran 4 of the plan cells.
- Key changes: Defaults now match (4.1 concat, lr 2e-4). `--plan-sweep` trains the 10 unique plan cells (5.1 skips fusion; 4.1/4.2 x 5.2/5.3 x 6.1/6.2) under the current contract and writes `medsiglip_gastricus_plan_complete_20260825/`.
- Validation: CLI `--help` and import check. 10-cell sweep finished in 6.4 min. Best held-out: `tabpfn_concat_mean` prosp 0.6424 / ext 0.5856. Default `mlp_concat_gated` 0.5976 / 0.5216. All four stats cells collapsed (QWK = 0).
- Deployment: Local workspace only. No Next rebuild.
- Follow-up: McNemar before promoting 5.1 x 6.2. Do not overwrite 20260821 plan/large reports.

## 2026-08-25, MedSigLIP workspace copies official crop_roi

- Scope: `medsiglip/dataset/**/crop_roi`, `medsiglip/scripts/refresh_workspace_copy.py`.
- Reason: The scratch workspace had freeze `crop_ui` only. Official lesion crops (`crop_roi/images`, `roi_masks`, `overlays`, `annotations`) were missing for browsing and alternative ROI training.
- Key changes: Rsynced 14 `crop_roi` trees, 55052 files (9 external hospitals + Xiehe 2018-2025). Default encode still computes ROI from `crop_ui` mask bbox.
- Validation: Dehua `crop_roi` image, mask, and overlay for `图片__dhwa1-1` exist.
- Deployment: Local workspace only. No Next rebuild.
- Follow-up: None.

## 2026-08-25, MedSigLIP workspace also copies crop_ui overlays

- Scope: `medsiglip/dataset/**/crop_ui/overlays`, `medsiglip/scripts/refresh_workspace_copy.py`.
- Reason: The first copy only had images and `roi_masks`. External and internal `crop_ui` also have green-contour overlay JPGs used for browsing.
- Key changes: Rsynced 14 overlay dirs, 13763 files (9 external hospitals + Xiehe 2018-2025). Refresh script now copies overlays with the rest of the workspace.
- Validation: Dehua sample `图片__dhwa1-1_overlay.jpg` exists; overlay file counts match the source dirs.
- Deployment: Local workspace only. No Next rebuild.
- Follow-up: None.

## 2026-08-25, MedSigLIP scratch workspace at repo root

- Scope: new `medsiglip/` copy of the frozen MedSigLIP-448 GastricUS pack; `START_HERE.md`, `REPO_LAYOUT.md`, `scripts/check_repo_root.py`, `.gitignore`.
- Reason: Need a clean folder to rethink training without editing the live package or mixing Dual ConvNeXt files.
- Key changes: Copied code, clean four-way CSVs, used `crop_ui` images/masks (21788 files, 0 missing), 1152-d caches, and `medsiglip-448` weights. Did not copy ~14G old report checkpoints or Dual yaml/scripts. `ROOT` inside the copy points at `medsiglip/`.
- Validation: Workspace import resolves `ROOT`, dataset, weights, default cache, and a sample frame/mask. CLI `--help` works after escaping `%` in argparse help. `check_repo_root.py` lists `medsiglip` as an allowed root dir.
- Deployment: Local workspace only. No Next rebuild. Analyze path unchanged.
- Follow-up: Train from `cd medsiglip && python3 scripts/run_medsiglip_gastricus.py train --device cuda:0`. Copy code back to `pipeline/medsiglip_gastricus/` only if a change should become the mainline.

## 2026-08-25, BM Assist uses doctor box; start box+mask dual retrain

- Scope: `binary_classification_tool.py`, `pipeline_adapter.py`, `scripts/build_binary_box_mask_pack_20260825.py`, dual config `binary_noshortcut_b_boxmask_dual_20260825.yaml`.
- Reason: Live BM head ate the full frame and ignored the doctor box. A/B full-frame retrains did not beat unseen AUC 0.733. Tumor shape was not in the input.
- Key changes: Classify-only now crops the current 3-channel head to the doctor box or SAM mask. New pack generates GrabCut masks with the same protocol for both labels. Dual-branch retrain: global full+mask4ch, local doctor ROI.
- Validation: A/B already scored (AUC 0.702 / 0.722). Box+mask pack: 9763 masks, `ok_rate` 1.0, doctor-box match mean 0.994, missing_mask=0, no patient leak. Dual train started `binary_noshortcut_b_boxmask_dual_20260825_20260825_115508`. Scores pending.
- Deployment: Analyze Python is live on the next Assist click (crop). Dual weights are not product yet. No Next rebuild required for the crop path.
- Follow-up: After dual `test_external` patient AUC vs 0.733, decide whether to replace the 101708 single-branch head.

## 2026-08-25, Public test account and LAN evaluation login

- Scope: `docs/clinical_validation/reader_study_v150/users.json`, `LoginGate.tsx`, `app/page.tsx`, `app/api/patients/route.ts`, `Header.tsx`, `PatientList.tsx`, `apps/README.md`.
- Reason: Public needed a dedicated test reader. LAN evaluation still used a no-password identity picker and showed extra research chrome / clinical history that public hides.
- Key changes: Added reader `test`. LAN and public now share the password login page. On the reader-study queue, LAN hides clinical history and uses the same evaluation chrome as public. Queue switcher stays available so research queues still work.
- Validation: Local password verify for `test`; `npx tsc --noEmit` in `apps/gastric_scan_next`. Public smoke after deploy.
- Deployment: Synced `users.json` to Aliyun reader edge and restarted `gastric-reader`. Public BUILD `8jol8sXETeorrEyURL_Zb` via `bash scripts/deploy_public_next.sh`. Smoke `public_root=200`, `public_clinical=200`. Hard-refresh http://47.106.33.102 and LAN `:3000`.
- Follow-up: Sign in with the new test reader on both sites and confirm ops land on that account.

## 2026-08-25, Desktop one-click workstation start

- Scope: `scripts/start_gastric_workstation.sh`, desktop launcher on the workstation, `apps/README.md`, `apps/gastric_scan_next/README.md`, `scripts/README.md`.
- Reason: Frontend Next and GPU backends were split across systemd, `dev_all.sh`, and `run_lan_merged_system.sh`. Operators needed one desktop icon that brings the full LAN stack up.
- Key changes: One script starts Next `:3000`, auth `:8766`, SAM2 `:8767`, SAM3.1 `:8768`, nnInteractive `:1527`/`:8770`, and warm YOLO `:8771`. Prefers `gastric-workstation.target` when installed. `install-desktop` writes a trusted GNOME launcher. `stop` leaves public compute `:3300` running unless `--stop-public`.
- Validation: `bash -n` on the script; `install-desktop` wrote the launcher; `start --no-browser` health-checked the LAN ports.
- Deployment: Local workstation launcher only. No public Next rebuild.
- Follow-up: Double-click 启动胃超工作站 on the desktop. If GNOME says untrusted, right-click Allow Launching.

## 2026-08-25, Restore public ops and boot-start public compute

- Scope: `scripts/reconcile_public_ops_pending.py`, `scripts/install_gastric_user_services.sh`, `scripts/systemd/gastric-sam-agent.service`, `scripts/systemd/gastric-ops-reconcile.service`, `scripts/systemd/gastric-ops-reconcile.timer`, `scripts/aliyun_sam_tunnel.service`, `apps/README.md`.
- Reason: After the workstation reboot, public dual-write leftover events stayed in Aliyun pending, case-state never landed on the GPU box, and a reinstall of user units could drop SAM2 / lumen / the reverse tunnel.
- Key changes: Idempotent pull-and-merge of public ops, audit, viewing, case-state, and case-order; daily jsonl backfill; linger install now covers SAM2, lumen, `:3300`, the Aliyun tunnel, and a 90s-after-boot reconcile timer.
- Validation: First reconcile appended 153 leftover ops (151 zml), restored public case-state (47 zml cases, 46 completed) and case-order, backfilled daily shards, and emptied Aliyun pending. User units stay enabled with linger; local SAM / `:3300` / public root all 200.
- Deployment: Workstation user systemd only. No public Next rebuild.
- Follow-up: Open `/admin/ops` as admin and confirm the restored public session timeline.

## 2026-08-24, Start BM anti-shortcut A/B retrains

- Scope: `scripts/build_binary_noshortcut_ab_20260824.py`, `scripts/run_binary_noshortcut_ab_20260824.py`, two YAML configs, pack `pipeline/data/binary_noshortcut_ab_20260824/`.
- Reason: Current BM train locks Xiehe to malignant and other seen centers to most of the benign cases. Unseen-center AUC 0.733 and the 50-case workbench pack both look like a center shortcut.
- Key changes: A drops Xiehe from train/val. B keeps Xiehe malignant but downsamples to Putian malignant patient n. Same `test_external` / `test_prospective` as 20260820. ConvNeXt-B 384, 80 epochs, early stop 12.
- Validation: Builder leak check and missing-image count must be 0 before launch.
- Deployment: Offline train only. Do not switch the live Assist head until unseen-center scores are in.
- Follow-up: Compare A/B patient AUC / Sens on `test_external` to 0.733 / 0.438. Then decide whether to replace the product checkpoint.

## 2026-08-24, Switch BM Assist to ConvNeXt-B 384

- Scope: `pipeline/agent/tools/binary_classification_tool.py`, `pipeline/agent/config/agent_backend_registry.yaml`.
- Reason: Workbench BM-001..050 Assist was using clean_audit ConvNeXt-S, which predicted benign on every mid-frame (Acc 0.50, Sens 0.00). Doctors were seeing almost all-benign AI calls.
- Key changes: Product binary gate now loads `binary_multicenter_joint_unseen_20260820_20260820_101708` (ConvNeXt-B 384). Same 50-case mid-frame score: Acc 0.72, Sens 0.56, Spec 0.88, AUC 0.78. Official unseen-center patient AUC remains 0.733 (n=404).
- Validation: Local mid-frame sweep of BM-001..050 with both checkpoints; tool smoke import reports the 101708 backend.
- Deployment: Analyze is spawned from the repo on each Assist click (public tunnels to workstation `:3300`). No Next rebuild. Next Assist click uses the new weights.
- Follow-up: Still misses some malignant BM cases. Do not treat this as a frozen paper model. MedSigLIP "binary" runs are T4+ / T3-T4, not 良恶性.

## 2026-08-24, Full doctor operation logging

- Scope: `app/api/reader/operations/route.ts`, `doctor-case-state-store.ts`, `lib/ops/types.ts`, `InteractiveSegPanel.tsx`, `useOperationRecorder.ts`, `ReaderStudyQueuePanel.tsx`, `app/page.tsx`, `ReaderWorkbench.tsx`, `app/admin/ops/page.tsx`, `DoctorHistoryPanel.tsx`, `app/api/reader/history/[historyId]/route.ts`.
- Reason: Many workbench clicks only hit viewing-trace or case-state; public ops often proxy-only. Need timestamped rows in the ops store and case History for ~10-20 doctors.
- Key changes: Public operations POST dual-writes local jsonl then proxies; `MAX_ACTIVITY` 2000; cine/zoom/freeze/layer also `recordDoctorOp`; keyframe select/delete, deepest toggle, sign edit, stage override, report/tutorial opens; admin ops event-type filter plus `recorded_at` / action / `video_t`; History detail merges ops into case timelines.
- Validation: `npx tsc --noEmit`. Deploy smoke `public_root=200`, `public_clinical=200`.
- Deployment: Public BUILD `wX_NxGhcYIKd04itCRUit` via `bash scripts/deploy_public_next.sh`. Hard-refresh http://47.106.33.102 .
- Follow-up: Spot-check one doctor session in `/admin/ops` and History after play/pause, deepest, delete keyframe, Assist.

## 2026-08-24, Enable Save my call without retapping

- Scope: `ReaderStudyQueuePanel.tsx`, `DoctorTutorialModal.tsx`.
- Reason: After Assist, Save my call and next stayed gray until the doctor retapped a stage, even when the first call was already selected.
- Key changes: Enable the button whenever an initial call exists; save the highlighted first call, not only a post-AI retap.
- Validation: `npx tsc --noEmit`. Deploy smoke `public_root=200`, `public_clinical=200`.
- Deployment: Public BUILD `ppG7HWak4pGIYPd0FXnxF` via `bash scripts/deploy_public_next.sh`. Hard-refresh http://47.106.33.102 .

## 2026-08-24, Plan-section fusion audit and missing 4 x 5 cross cells

- Scope: `pipeline/medsiglip_gastricus/PLAN_MAPPING.md` section 5.4 and section 9; two small frozen-head trains under `medsiglip_gastricus_plan_cross_20260824/`.
- Reason: Multi-frame fusion in the plan is bag pooling (5.1 / 5.2 / 5.3), not Dual K-frame softmax mean. The original plan sweep skipped concat+stats and interact+mean.
- Validation: Existing cells copied from SUMMARY.md. New cells write new folders only.
- Deployment: Offline. No public Next deploy.

## 2026-08-24, GastricUS plan-vs-result report finished past 10k Chinese characters

- Scope: `pipeline/experiments/reports/gastricus_ledger/GastricUS_训练过程与结果报告_20260824.md`, matching Word copies at repo root, ledger, and Desktop; `scripts/finish_gastricus_plan_report.py`.
- Reason: The plan-section report had to cover sections 1-6 with method, key code, and SUMMARY exact ACC, plus extra experiments and a synthesis, and the body had to exceed 10,000 Chinese characters.
- Validation: `re.findall(r'[\u4e00-\u9fff]')` on the saved Markdown and Word body; required headings 1-11 present.
- Deployment: Offline training report only. No public Next deploy.
- Follow-up: Held-out exact ACC target 0.75 / 0.75 is unchanged and still unmet.

## 2026-08-23, Top-bar doctor tutorial popup

- Scope: `DoctorTutorialModal.tsx`, `Header.tsx`, `ReaderWorkbench.tsx`.
- Reason: Doctors need a visible, step-by-step walkthrough of the full reading loop, not only a static help page.
- Key changes: Tutorial button in the top bar opens a popup with 10 steps (login, pick case, first call, box lesion, keyframes, Assist, review, save, report, history/phone). Next/Back and dots per step.
- Validation: `npx tsc --noEmit`. Deploy smoke `public_root=200`, `public_clinical=200`.
- Deployment: Public BUILD `hO4HvXj-l4ML0Xuu0InzX` via `bash scripts/deploy_public_next.sh`. Hard-refresh http://47.106.33.102 .

## 2026-08-23, Assist gating, editable first call, unrated labels, deepest toggle

- Scope: `ReaderStudyQueuePanel.tsx`, `InteractiveSegPanel.tsx`, `PatientList.tsx`, `DoctorKeyframeStrip.tsx`, `doctor-keyframes.ts`, `app/page.tsx`, `ReaderWorkbench.tsx`, `ReaderHelpModal.tsx`.
- Reason: Assist was clickable before the doctor knew what to do; first call could not be changed after tap; unrated cases/signs had no label; deepest-invasion star could not be cleared.
- Key changes: Assist stays gray with a 1-2-3 checklist until judgment + lesion box; first call can be retapped before or after AI; feature fields and case list show 未评估/未评; star toggles deepest invasion off.
- Validation: `npx tsc --noEmit`. Deploy smoke `public_root=200`, `public_clinical=200`.
- Deployment: Public BUILD `Bg1HUPfRypWWnODDqRVC4` via `bash scripts/deploy_public_next.sh`. Hard-refresh http://47.106.33.102 .

## 2026-08-23, Fix mobile sidebar reopen after judgment

- Scope: `app/page.tsx`, `ReaderStudyQueuePanel.tsx`, `MobilePaneNav.tsx`, `globals.css`, `ReaderWorkbench.tsx`.
- Reason: After tapping a stage/nature on phone, cases/evidence sheets would not stay open: an unstable judgment callback re-ran restore and closed panes, and an AI-result effect kept forcing the evidence sheet.
- Key changes: Judgment callback uses `source` (user/restore/reset) and a ref so restore does not fight bottom nav; remove force-open-evidence effect; exclusive Assist open; higher nav/sheet z-index + `inert`/visibility on closed sheets; next-case uses `selectPatient`.
- Validation: `npx tsc --noEmit`. Deploy smoke `public_root=200`, `public_clinical=200`.
- Deployment: Public BUILD `XHeSJkN1FMPDuZeVElDWA` via `bash scripts/deploy_public_next.sh`. Hard-refresh http://47.106.33.102 .

## 2026-08-23, Admin seeded history and resume highlight

- Scope: public `doctor_case_state` for admin; `ReaderStudyQueuePanel.tsx` restore prefers final judgment for button highlight.
- Reason: Doctor testing needs ready-made history; reopening a case must show the previously selected stage/nature highlighted.
- Validation: Seeded 8 admin cases; restore API 8/8; history list/detail OK. Deploy smoke 200.
- Deployment: Public BUILD `nGkhQuKOvAIFzBW9jwjZ7`. Hard-refresh http://47.106.33.102 .

## 2026-08-23, Doctor judgment highlight and full reading history

- Scope: `ReaderStudyQueuePanel.tsx`, `DoctorHistoryPanel.tsx`, `doctor-case-state-store.ts`, `api/reader/case-state`, `api/reader/history`, `InteractiveSegPanel.tsx`.
- Reason: Selected doctor judgments were too faint; public history list was empty because ops/audit are tunnelled away while resume state lives on-node.
- Key changes: Strong selected-stage highlight (amber fill + ring + check). Case-state activity log for judgments, keyframes, mask saves. History API merges case-state cards and detail timelines.
- Validation: `npx tsc --noEmit`. Public history returns case cards with judgment/keyframe traces. Deploy smoke 200.
- Deployment: Public BUILD `6WZIlhPiS9AiT89MI25d-` via `bash scripts/deploy_public_next.sh`. Hard-refresh http://47.106.33.102 .

## 2026-08-23, Fix public case-state local store (no agent proxy)

- Scope: `apps/gastric_scan_next/app/api/reader/case-state/route.ts`.
- Reason: Stability test found public `/api/reader/case-state` returned HTML 404 because `shouldProxyOps()` forwarded to `NEXT_AGENT_UPSTREAM`, which does not serve this path.
- Key changes: Serve judgments and keyframes on the public node runtime store only; keep ops-ingest as alternate auth, do not proxy.
- Validation: Public API suite 17/17 (order stable 5x, PUT/GET restore stage+keyframes, auth 401, foreign account rejected).
- Deployment: Public BUILD `l4gKVnNiE7BvVDX6R3Drj` via `bash scripts/deploy_public_next.sh`. Hard-refresh http://47.106.33.102 .

## 2026-08-23, Reader mark-frame, edit after AI, resume, shuffle

- Scope: `apps/gastric_scan_next/components/InteractiveSegPanel.tsx`, `ReaderStudyQueuePanel.tsx`, `PatientList.tsx`, `lib/reader/round2-order.ts`, `lib/reader/doctor-case-state-store.ts`, `app/api/reader/case-state/route.ts`, `app/api/patients/route.ts`, `proxy.ts`.
- Reason: Doctors need a visible keyframe mark after pause/scrub, a clear accept/modify-and-next loop after AI, resume of judgments and drawings by account+case, and a shuffled case order that is not CASE-numeric or T-stage-blocked.
- Key changes: Cine bar「标记此帧」and Space on range scrubber; Accept AI / Save my call and next; `/api/reader/case-state` persist/restore; list Done/Partial badges; keep API order; freeze CSV when present else stable per-account shuffle on disk.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. Deploy smoke `public_root=200`, `public_clinical=200`.
- Deployment: Public BUILD `iY0uRTQqn8Q71qPGhsAeT` via `bash scripts/deploy_public_next.sh`. Hard-refresh http://47.106.33.102 .
- Follow-up: Confirm with a doctor account that scrub-mark, modify-save, resume, and non-blocked T order behave as expected.

## 2026-08-23, Queue hist_eq+TabPFN-4 Dual and auto-harvest watcher

- Scope: `scripts/watch_gastricus_dual_finish.py`, `scripts/postprocess_gastricus_dual.py`, `pipeline/configs/tstaging_4class_acc_boost2_gastricus_histeq_tabpfn4_20260823.yaml`.
- Reason: Live Duals have no held-out SUMMARY yet. After they finish, eval val, harvest, fuse, stack, and T3/T4 recal must go to new folders. Next queued Duals are 12-frame hist_eq then hist_eq+TabPFN-4.
- Validation: Watcher does not kill GPU PIDs. Launch only if a card has 12 GB free.
- Deployment: Offline only. No public Next deploy.

## 2026-08-23, Dual frame aggregation and all-Dual linear stack

- Scope: `scripts/run_gastricus_frame_agg.py`, `scripts/run_gastricus_stack_alldual.py`.
- Reason: Existing Dual eval already averages all frames. Search confidence / top-k aggregation, and an L2 linear stack of frozen plus hist_eq / t2boost Dual.
- Key changes: Frame agg val-locked top3 Dual-only 0.5694 / 0.5340. All-Dual linear C=0.3: 0.6188 / 0.5732. Neither pair is 0.75.
- Validation: On-disk SUMMARYs only. Do not promote val or train ACC.
- Deployment: Offline only. No public Next deploy.

## 2026-08-23, T1/T2 rescue and T1/T2/T3 cascade

- Scope: `scripts/run_gastricus_early_recal.py`, `scripts/run_gastricus_t123.py`, `pipeline/configs/tstaging_4class_acc_boost2_gastricus_frames12_20260823.yaml`.
- Reason: T3/T4 recal left T2 recall at 0.088 / 0.284. Try thickness-gated early-stage rules and a frozen 3-class head on non-T4+ bags.
- Key changes: early recal val-locked to `none` (same 0.6329 / 0.5897). T1/T2/T3 cascade val-locked to keep the recal base (same pair). 12-frame Dual queued for the next free GPU.
- Validation: On-disk SUMMARYs only. Do not promote 3-class val ACC.
- Deployment: Offline only. No public Next deploy.
- Follow-up: Finish Dual TabPFN-4 and hist_eq+T2; harvest into new folders.

## 2026-08-23, TabPFN mix, binary graft, T3/T4 recal, hist_eq+T2 Dual

- Scope: `scripts/run_gastricus_tabpfn_mix.py`, `scripts/run_gastricus_binary_graft.py`, `scripts/run_gastricus_t34_recal.py`, `pipeline/configs/tstaging_4class_acc_boost2_gastricus_histeq_t2_20260823.yaml`.
- Reason: Frozen and Dual fusion still sit at 0.6329 / 0.5814. Try patient-level TabPFN mix, hard binary grafts, and a T3/T4+ score blend; start hist_eq plus T2 Dual on the free GPU.
- Key changes: TabPFN mix 0.5976 / 0.5216 (val lock preferred Dual+clinical, overfit). Binary graft 0.6094 / 0.5299. T3/T4 recal 0.6329 / 0.5897 (new best external). hist_eq+T2 Dual training on cuda:0.
- Validation: On-disk SUMMARYs only. Do not promote val ACC or train ACC.
- Deployment: Offline only. No public Next deploy.
- Follow-up: Finish Dual TabPFN-4 (cuda:1) and hist_eq+T2 (cuda:0); harvest into new folders.

## 2026-08-23, Sweep Dual late-fusion partners

- Scope: `scripts/run_gastricus_fusion_stack_mix.py`, extra fusion report folders, `gastricus_stack_dual2_20260823`.
- Reason: hist_eq fusion lifted prospective to 0.6329. Check whether other official-split Duals or a second Dual in the stack beat that.
- Key changes: t2boost fusion 0.6259 / 0.5443. Official / expand15 / lockbal fusion all worse. Two-Dual stack 0.6141 / 0.5732. Disagreement mix locked to stack (0.6165 / 0.5814). Best pair unchanged.
- Validation: On-disk SUMMARYs only. Do not promote val ACC.
- Deployment: Offline only. No public Next deploy.
- Follow-up: Dual TabPFN-4 still training.

## 2026-08-23, Dual hist_eq late fusion and softmax stack

- Scope: `scripts/eval_gastricus_dualconv_splits.py`, `scripts/ensemble_gastricus_dualconv_frozen.py`, `scripts/run_gastricus_stack_dual.py`.
- Reason: Fusion was blocked on missing Dual val CSVs. After val eval, mix Dual hist_eq with frozen votes; then stack frozen softmax with Dual.
- Key changes: Fusion prospective 0.6329 / external 0.5753 (new best prospective). Stack+Dual 0.6165 / 0.5814 (new best external). Neither pair is 0.75.
- Validation: On-disk SUMMARYs and ledger sync (83+ runs).
- Deployment: Offline only. No public Next deploy.
- Follow-up: Dual TabPFN-4 still training on cuda:1. Do not promote these numbers.

## 2026-08-23, Dual val eval so late fusion can lock on val

- Scope: `scripts/eval_gastricus_dualconv_splits.py`, `scripts/harvest_gastricus_dualconv.py`.
- Reason: Dual trainer only wrote held-out CSVs. Fusion needs val predictions to lock mix weight.
- Key changes: Eval an existing Dual checkpoint onto `eval/val/test_predictions.csv` without retraining. Harvest now fuses the hist_eq tree when val exists.
- Validation: hist_eq val eval, then `ensemble_gastricus_dualconv_frozen.py`.
- Deployment: Offline train / eval only. No public Next deploy.
- Follow-up: Read fusion SUMMARY only. Do not promote unless both held-out exact ACC are 0.75.

## 2026-08-23, Pack GastricUS experiments without weights

- Scope: `scripts/write_gastricus_zh_report.py`, `scripts/pack_gastricus_experiments.py`, ledger `主报告.md`.
- Reason: Desktop pack must include Dual ConvNeXt markdown and logs, and open with a Chinese executive report. Weights and prediction CSVs stay out.
- Key changes: Chinese report now collects `gastricus_*` SUMMARYs. Pack copies official-split Dual `training.log` from the experiment tree. New `主报告.md` is the reading entry.
- Validation: `python3 scripts/pack_gastricus_experiments.py`.
- Deployment: Offline docs / desktop pack only. No public Next deploy.
- Follow-up: Dual TabPFN-4 still training; harvest it when both held-out CSVs exist.

## 2026-08-23, Long-run clin22 T2-cost harvest

- Scope: `pipeline/experiments/reports/medsiglip_gastricus_longrun_tabpfn_20260823/full16_xxlarge_clin22_t2cost/`.
- Reason: Resume of last-16 xxlarge plus clinical 22 plus T2 off2 0.4 finished (early stop epoch 24, lock epoch 8).
- Key changes: Patient exact ACC prospective 0.5012 / external 0.4825. Held-out T2 recall 0 / 0. Better than TabPFN-196 (0.4847 / 0.4041), still below frozen votes 0.6188 / 0.5794. Not 0.75.
- Validation: On-disk SUMMARY plus `sync_gastricus_ledger.py`.
- Deployment: Offline train only. No public Next deploy.
- Follow-up: Dual TabPFN-4 on cuda:1. Do not re-run this folder.

## 2026-08-23, Dual T2-boost harvest on the official split

- Scope: `pipeline/experiments/reports/gastricus_dualconv_t2boost_20260823/`, ledger 81 runs.
- Reason: T2-weighted Dual ConvNeXt finished on the clean GastricUS split; numbers go into the ledger only.
- Key changes: Patient exact ACC prospective 0.5859 / external 0.5134. T2 recall 0.0882 / 0.1343. Hist_eq Dual remains the best Dual (0.5835 / 0.5381). Votes remain the ledger best (0.6188 / 0.5794). Not 0.75.
- Validation: `scripts/harvest_gastricus_dualconv.py --all` then `sync_gastricus_ledger.py`. Fusion still skipped: Dual trainer does not write val prediction CSVs.
- Deployment: Offline train only. No public Next deploy.
- Follow-up: Dual TabPFN-4 on cuda:1. cuda:0 continues clin22 T2-cost resume.

## 2026-08-23, Admin ops log is a full timestamped event stream

- Scope: `lib/ops/store.ts`, `/api/admin/ops-stats`, `/admin/ops`, workbench `page.tsx`, `ReaderStudyQueuePanel`.
- Reason: Admin could only see aggregated doctor/case/decision tables. The raw stream existed on disk but was not shown, some clinical actions were not copied into the ops file, and events were not stamped on server receive.
- Key changes: Every persisted ops event now keeps client time (`recorded_at`, `t_client_ms`) and `server_received_at`. Files append to current, monthly, and daily JSONL. Admin page shows the full event log and can export CSV/JSONL. Workbench also records case select, assist start/result/fail, report open, mobile pane, and initial judgment.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`.
- Deployment: Public Next BUILD `qKD3Qws0g4XdrzOvoS3bw` on [47.106.33.102](http://47.106.33.102) (previous `nKcqceTQSz-4iL4zqrMGJ`).
- Follow-up: Hard refresh `/admin/ops`. Logs stay on the workstation under `runtime/gastric_scan_next/` (append-only, not overwritten).

## 2026-08-23, Phone can finish the full reader loop without changing desktop

- Scope: `app/page.tsx`, `ReaderStudyQueuePanel`, report previews, `DoctorReportStudio`, `MobilePaneNav` labels, `use-mobile-layout.ts`, `globals.css`.
- Reason: On a phone the three desktop columns were split into sheets, but the flow still required the doctor to hunt for judgment, boxing, Assist, and the Word-width report. Desktop layout must stay as-is.
- Key changes: Phones only auto-switch Cases → Your call → Viewer after judgment → Result after Assist. Evidence tab label is 判断 then 结果. Formal report uses a full-bleed readable page under 768px (print still A4). Close / Assist / select targets are larger. Desktop three-column workbench and 794px Word page are unchanged.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. Public smoke `public_root` / `public_clinical` 200.
- Deployment: Public Next BUILD `nKcqceTQSz-4iL4zqrMGJ` on [47.106.33.102](http://47.106.33.102) (previous `cEbqNnBdBHt6blmAtLVAR`).
- Follow-up: Hard refresh on the phone. Rollback: Aliyun Next `.next-public-deploy-dist.bak_*` from this stamp.

## 2026-08-23, Thinner contour beads so the lesion edge stays visible

- Scope: `contour-edit.ts`, `InteractiveSegPanel.tsx`, `ReaderViewer.tsx`.
- Reason: The control beads along the lesion contour were dense and filled, so they covered the ultrasound edge. Doctors could not see the margin or drag it cleanly.
- Key changes: Beads are now hollow hairline rings, fewer on small lesions (spacing about 52 image pixels, cap 16), and the dark halo around the contour is thinner. Grab distance stays large so the tools remain easy to catch.
- Validation: TypeScript diagnostics on the touched Next files.
- Deployment: Public Next BUILD `cEbqNnBdBHt6blmAtLVAR` on [47.106.33.102](http://47.106.33.102) (previous `Cbmj9wbhdLL0kXCXYlhmM`).
- Follow-up: Hard refresh. Rollback: Aliyun Next `.next-public-deploy-dist.bak_*` from this stamp.

## 2026-08-23, Benign formal report uses BM template; sex and age from original tables

- Scope: `BmTemplateReportPreview`, `DoctorReportStudio`, `us-clinical-server.ts`, `reader_v150_clinical.json` / `.js`.
- Reason: Opening the formal report on a BM case still used the T-staging wall-layer Word layout. Sex and age were hardcoded empty even though `reader_v150_catalog.csv` and the original clinical tables have them for 148/150 cases. The reader-study HTML already expected `clinical.age` / `clinical.sex`.
- Key changes: BM queue reports now render the official benign-malignant template (site, diameters, ulcer, wall layers, surface, peristalsis, stenosis, retention, CDFI, nodes, ascites, impression). Header still shows accession, sex, age. Sidecar now carries age/sex from the catalog join. BM-001 remains unmatched in the original tables, so those two header fields stay blank there.
- Validation: TypeScript diagnostics on the touched Next files.
- Deployment: Public Next BUILD `Cbmj9wbhdLL0kXCXYlhmM` on [47.106.33.102](http://47.106.33.102) (previous `ItHWvBBV4-Foc3Ykjw-Z_`).
- Follow-up: Hard refresh. Rollback: Aliyun Next `.next-public-deploy-dist.bak_*` from this stamp.

## 2026-08-23, Assist: T-stage analysis, benign fill-in, hide unpredicted signs

- Scope: `ReaderStudyQueuePanel`, `BmEvidencePanel`, `assist-report-overlay.ts`, `pipeline_adapter.py` classify-only, `app/page.tsx`.
- Reason: After Assist, T-staging needed the same analysis card. Benign cases should use the previous BM report fill-ins. Wall layers and perigastric tissue are not model-predictable for malignancy, so they should not appear.
- Key changes: T-staging shows T plus four editable signs (morphology, boundary, growth, serosa). BM benign shows site, diameters, ulcer, and wall-layer fill-ins. BM malignant also runs T-stage and shows that result; wall layers and perigastric stay hidden. BM benign still skips the T-stage checkpoint.
- Validation: `python3 pipeline/agent/product/test_classify_only_adapter.py`. TypeScript diagnostics on the touched Next files.
- Deployment: Public Next BUILD `ItHWvBBV4-Foc3Ykjw-Z_` on [47.106.33.102](http://47.106.33.102) (previous `VgVEdk7vUPJm9tFP4INfq`). Workstation Python is live via the analyze tunnel.
- Follow-up: Hard refresh the public browser. Rollback: Aliyun Next `.next-public-deploy-dist.bak_*` from this stamp.

## 2026-08-23, BM assist skips T-stage load

- Scope: `pipeline_adapter.py` classify-only, `binary_classification_tool.py` process cache.
- Reason: Reader Assist felt slow because each click spawned Python and loaded both the L0 binary ConvNeXt and the L3 T-stage checkpoint. The binary forward itself is milliseconds.
- Key changes: `study_mode=benign_malignancy` now runs only the image-level binary head. Headline and confidence come from that head. T-stage weights stay unloaded. Classify-only no longer writes prediction artifacts. Binary weights cache inside one process.
- Validation: `python3 pipeline/agent/product/test_classify_only_adapter.py`.
- Deployment: Workstation Python only; public analyze already tunnels here. Public Next unchanged.
- Follow-up: A warm classify worker is still needed for true one-second Assist; each request still starts a new Python process.

## 2026-08-23, Show AI stage, confidence, and editable signs

- Scope: `ReaderStudyQueuePanel`, `assist-report-overlay.ts`, `app/page.tsx`.
- Reason: After the right rail was simplified, Assist still ran but the panel no longer showed the model call. The old system report was a geometry/text draft, not the classify-only stage.
- Key changes: After Assist, show stage or nature plus confidence, then six predicted signs the doctor can edit. Keep AI / Modify both write audit and ops against the logged-in account. Overlay the classify result onto the assist report so the headline is no longer empty.
- Validation: TypeScript diagnostics on the touched Next files. Public smoke after swap: root 200, clinical 200.
- Deployment: Public Next BUILD `VgVEdk7vUPJm9tFP4INfq` on [47.106.33.102](http://47.106.33.102) (previous `Gy9gNNccrJ7Qv-ZDHYUyH`).
- Follow-up: Hard refresh the public browser. Rollback: Aliyun Next `.next-public-deploy-dist.bak_*` from this stamp.

## 2026-08-22, Hide BM report form; box-as-keyframe

- Scope: `app/page.tsx`, `ReaderStudyQueuePanel`, `InteractiveSegPanel`, help copy.
- Reason: The right panel was dominated by 良恶性鉴别报告 chips (site, diameters, ulcer, wall layers). Doctors want a short read loop: own call, Assist, then open the report after reading. Mark-this-frame was an extra step before boxing.
- Key changes: Hide the BM / GC-US form on the evidence rail. Doctor judgment stays at the top; Assist is a single button; a large Review and confirm report button sits at the bottom. Boxing a lesion marks the current frame as the keyframe. The Mark this frame button is removed from the public reader video chrome.
- Validation: TypeScript diagnostics on the touched Next files. Public smoke after swap: root 200, clinical 200.
- Deployment: Public Next BUILD `Gy9gNNccrJ7Qv-ZDHYUyH` on [47.106.33.102](http://47.106.33.102) (previous `TyyX61IiallYONozmPmn9`).
- Follow-up: Hard refresh the public browser. Structured report fields remain in the post-read report workspace. Rollback: Aliyun Next `.next-public-deploy-dist.bak_*` from this stamp.

## 2026-08-23, Harvest all Dual GastricUS prefixes and chain the GPU queue

- Scope: `scripts/harvest_gastricus_dualconv.py --all`, `scripts/watch_gastricus_next_gpu.sh`.
- Reason: Harvest only looked at the official Dual tree, so lockbal / hist_eq / 15% would not write a SUMMARY. The first watcher could also relaunch lockbal every minute after that job exited.
- Key changes: One report folder per Dual prefix. Official fusion still writes only from the official tree. Watcher order after official held-out CSVs: lockbal, then hist_eq, then 15% ROI. Does not kill live trains.
- Validation: Do not promote unless both held-out exact ACC are 0.75.
- Deployment: Offline. Public Next unchanged.

## 2026-08-23, Queue Dual ConvNeXt 15% ROI on the official split

- Scope: `scripts/export_gastricus_dualconv_split.py --expand 0.15`, config `tstaging_4class_acc_boost2_gastricus_expand15_20260823.yaml`, report `gastricus_dualconv_expand15_20260823/`.
- Reason: Frozen 15% ROI had the best single-model prospective exact ACC (0.6165). Official split CSVs have no doctor-box columns, so Dual still uses mask-bbox. The 15% crops go to a new data_dir.
- Key changes: New folder only. Does not overwrite the 20% Dual table or the live official run.
- Validation: Do not promote unless both held-out exact ACC are 0.75.
- Deployment: Offline. Public Next unchanged.

## 2026-08-23, Auto-queue next GPU jobs after live GastricUS trains

- Scope: `scripts/watch_gastricus_next_gpu.sh`, longrun `COMPARE.md`.
- Reason: TabPFN-196 unfreeze epoch 2 val exact ACC fell 0.4609 → 0.4297 and T2 recall stayed 0. Dual ConvNeXt val patient ACC is climbing (0.4922 at epoch 6). GPU slots should start the next designed folders instead of idling.
- Key changes: Watcher harvests, then launches lockbal Dual on cuda:1 after the official Dual writes held-out CSVs, and `--clinical raw --t2-off2-weight 0.4` on cuda:0 after the 196-d job exits. Does not kill or overwrite live runs.
- Validation: Do not promote unless both held-out exact ACC are 0.75.
- Deployment: Offline. Public Next unchanged.

## 2026-08-23, Dual ConvNeXt lock patient balanced ACC and every-epoch history

- Scope: `pipeline/lib/trainer.py` `log_every_epoch` plus incremental `training_history.csv`; config `tstaging_4class_acc_boost2_gastricus_lockbal_20260823.yaml`; harvest reads the CSV when present.
- Reason: The live official Dual run only prints BEST or every 5th epoch, so epoch 4 looked missing. Exact patient ACC lock on val n=128 picked epoch 3 (0.4141) while epoch 5 had higher AUC and less T2/T3-to-T4+ overstaging. Acc_boost locked balanced metrics.
- Key changes: Default Dual still locks exact patient ACC. The queued lockbal run writes a new folder. Live process is unchanged (already loaded).
- Validation: Held-out exact ACC from SUMMARY only. Do not promote the lock metric.
- Deployment: Offline. Public Next unchanged.

## 2026-08-23, Long-run T2 off2 switch and Dual T2-boost queue

- Scope: `longrun.py` `--t2-off2-weight`, `scripts/harvest_gastricus_longrun.py`, `scripts/harvest_gastricus_dualconv.py` now calls late fusion, config `tstaging_4class_acc_boost2_gastricus_t2boost_20260823.yaml`.
- Reason: Live unfreeze epoch 1 has T2 recall 0. TabPFN-196 may be collapsing to T3. The next unfreeze should keep clinical 22 and add the existing T2-to-T1/T4+ penalty. Dual ConvNeXt is also overstaging T2/T3 toward T4+ on val.
- Key changes: Default long-run loss is unchanged (`--t2-off2-weight 0`). `--clinical raw --t2-off2-weight 0.4` writes `full16_xxlarge_clin22_t2cost/`. Harvest writes fusion SUMMARY when both held-out CSVs exist.
- Validation: Do not promote unless both held-out exact ACC are 0.75.
- Deployment: Offline. Public Next unchanged.

## 2026-08-23, Queue hist_eq / TabPFN-4 Dual ConvNeXt and widen the ledger

- Scope: `pipeline/configs/tstaging_4class_acc_boost2_gastricus_histeq_20260823.yaml`, `tstaging_4class_acc_boost2_gastricus_tabpfn4_20260823.yaml`, `scripts/export_gastricus_dualconv_tabpfn4.py`, `scripts/ensemble_gastricus_dualconv_frozen.py`, `scripts/sync_gastricus_ledger.py`.
- Reason: Both GPUs are busy. Frozen 1152-d is still 0.6188 / 0.5794. The next Dual ConvNeXt knobs after the live official run are hist_eq (acc_boost #4) and frozen TabPFN 4-class OOF as extra clinical columns, then late fusion with existing frozen votes.
- Key changes: New configs and a new TabPFN-4 CSV folder. Ledger now also copies `gastricus_*` waves and in-progress HISTORY / PROGRESS / QUEUED files. Originals are not moved or deleted.
- Validation: Do not promote unless both held-out exact ACC are 0.75. Live Dual ConvNeXt val patient ACC is not a held-out number.
- Deployment: Offline. Public Next unchanged.

## 2026-08-23, Dual ConvNeXt on official GastricUS split

- Scope: `scripts/export_gastricus_dualconv_split.py`, `pipeline/configs/tstaging_4class_acc_boost2_gastricus_official_20260823.yaml`, report `gastricus_dualconv_official_20260823/`.
- Reason: Frozen MedSigLIP 1152-d is stuck near 0.62 / 0.58. The 2026-06 jump used trainable Dual ConvNeXt plus mask as a 4th channel. That recipe had not been trained on `maincenter_retrospective_v20260821`.
- Key changes: New data_dir and config only. No leaked acc_boost2 warm-start. No ext in train. Default MedSigLIP CLI unchanged.
- Validation: Held-out exact ACC from the new SUMMARY only. Do not promote unless both are 0.75.
- Deployment: Offline. Public Next unchanged.

## 2026-08-23, Frozen plan 6.2 TabPFN TIME plus 4-class OOF

- Scope: `--head tabpfn_both` in `train.py` / `run_medsiglip_gastricus.py`. Report `medsiglip_gastricus_tabpfn_both_20260823/`.
- Reason: The long-run unfreeze already concatenates TIME-192 and 4-class OOF. The frozen-encoder control of that 196-d clinical expert was missing. Default remains `--head mlp --size xlarge`.
- Key changes: New head only. Image tokens still never enter TabPFN. Writes a new folder.
- Validation: Train on the official 20% cache. Do not promote unless both held-out exact ACC are 0.75.
- Deployment: Offline. Public Next unchanged.

## 2026-08-23, Long-run unfreeze + xxlarge + frozen TabPFN

- Scope: `scripts/run_medsiglip_gastricus_longrun.py`, `pipeline/medsiglip_gastricus/longrun.py`, `model.py` size `xxlarge`. Report `medsiglip_gastricus_longrun_tabpfn_20260823/`.
- Reason: Frozen-head sweeps stalled at 0.62 / 0.58. The written plan's next scale is a trainable encoder plus route 6.2 TabPFN clinical expert. Last-8 full FT at 2e-5 drifted; this run uses last-16, encoder lr 5e-6, 8 frames, and frozen TIME-192 plus 4-class OOF (196-d). Image tokens never enter TabPFN.
- Key changes: Complete script writes `train.log` / `last.pt` / `command.json`, supports `--resume`, default 48 epochs. `run_medsiglip_gastricus.py` defaults unchanged. 20% black cache and default xlarge report not overwritten.
- Validation: Train writes a new folder. Do not promote unless both held-out exact ACC are 0.75.
- Deployment: Offline. Public Next unchanged.
- Follow-up: If 24 GB OOMs, rerun `--last-n 12 --max-frames 6`. Resume with `--resume`.

## 2026-08-23, Ensemble v4 of lock-macro TIME with 15% heads

- Scope: `ensemble.py` `MEMBERS_V4`; report `medsiglip_gastricus_ensemble4_20260822/`. CLI `ensemble` still writes v1.
- Reason: Lock-macro TIME recovered T2; 15% TIME still has the best single-model external exact ACC. Vote on existing CSVs only.
- Validation: New folder. Do not promote unless both held-out exact ACC are 0.75.
- Deployment: Offline. Public Next unchanged.

## 2026-08-23, Lock val macro-recall on default 20% cache

- Scope: CLI `--lock macro` now writes `medsiglip_gastricus_lockmacro_20260822/` instead of the default 20260821 folder.
- Reason: Val n=128 lock on exact ACC can drop T2. Acc_boost locked balanced metrics. New folder only; `--lock acc` default unchanged.
- Validation: Train writes the new folder. Do not promote unless both held-out exact ACC are 0.75.
- Deployment: Offline. Public Next unchanged.

## 2026-08-22, T2 off2 cost and lesion-only third view

- Scope: `pipeline/medsiglip_gastricus/train.py` (`t2_off2_loss`), `mask_cut.py`, CLI `--t2-off2-weight` / `--mask-cut`.
- Reason: Acc_boost's +0.18 frame AUC used a T2-to-T1/T4+ cost and a pixel-aligned mask in the image. Those two pieces were not yet a GastricUS switch. Overlay third view already failed; this cut zeros background instead.
- Key changes: Default weight stays 0. New reports `t2cost_20260822` and `maskcut_20260822`. New cache `..._maskcut`. 20% black cache and CLI default recipe unchanged.
- Validation: Encodes and trains write new folders only. Held-out exact ACC still required on both splits before any promote.
- Deployment: Offline train/eval only. Public Next unchanged.
- Follow-up: Read SUMMARY.md. Do not overwrite existing reports.

## 2026-08-22, Compare GastricUS exact ACC with how acc_boost jumped

- Scope: `pipeline/medsiglip_gastricus/BACKBONE_VS_PLAN.md` §2.16; `scripts/write_gastricus_zh_report.py`; ledger `NEXT.md` / `README.md`.
- Reason: The pad / frozen-head sweep stalled at 0.62 / 0.58. Readers were mixing product acc_boost2 patient ACC 0.72 / 0.63 with the clean GastricUS exact-ACC contract.
- Key changes: Wrote how acc_boost actually moved (end-to-end Dual ConvNeXt, mask as 4th channel, doctor ROI, multitask / asymmetric cost, leaked `20260531` train) versus GastricUS real lifts (concat-mean, xlarge gated, TIME-192, 15% ROI, votes). Honest Phase 0 external 0.46 is the comparable Dual ConvNeXt line, not the product 0.63.
- Validation: Regenerated `gastricus_ledger/中文报告.md`. No training or public UI change.
- Deployment: Docs and report generator only. Public Next unchanged.
- Follow-up: Do not promote either line. Target remains both held-out exact ACC 0.75.

## 2026-08-22, Always sync public Next after product code changes

- Scope: `.cursor/rules/public-deploy-sync.mdc`, `CLAUDE.md`, `project-records-and-commits.mdc`.
- Reason: Doctors use 47.106.33.102. LAN next dev is not the public site; UI work was finishing without a public swap until asked.
- Key changes: Standing rule: after Next / reader / auth-edge / public sidecar changes, run `bash scripts/deploy_public_next.sh` before handoff, record BUILD, tell users to hard-refresh.
- Validation: Rule file present; deploy command unchanged (`scripts/deploy_public_next.sh`).
- Deployment: Docs and Cursor rule only. Live BUILD remains `TyyX61IiallYONozmPmn9` until the next product change.
- Follow-up: Skip only for docs-only or training/eval-only work that does not ship to the public path.

## 2026-08-22, Reader doctor-first judgment bar

- Scope: `ReaderDoctorFirstBar`, `ReaderEvidencePanel`, `ReaderToolbar`, `ReaderWorkbench`, help copy.
- Reason: Doctors need a short loop: own call first, then fast AI, then accept or keep their call. The evidence panel was dominated by Generate report / Assist opinion empty states.
- Key changes: The evidence panel now starts with large 良性/恶性 (or T1–T4+) buttons, then AI analysis, then accept/reject. Generate report moved under More. Full report is a small text link.
- Validation: TypeScript diagnostics on the touched reader files. Public smoke after swap: root 200, clinical 200.
- Deployment: Public Next BUILD `TyyX61IiallYONozmPmn9` on [47.106.33.102](http://47.106.33.102) (previous `VOD-953qq6Q9K_aLRbZ7Q`).
- Follow-up: Hard refresh the public browser. Rollback: Aliyun Next `.next-public-deploy-dist.bak_*` from this stamp.

## 2026-08-22, Reader T-stage is classify-only

- Scope: `pipeline/agent/product/pipeline_adapter.py`, `analyze_case.py` wall-mask helper, reader analyze route LLM env.
- Reason: Reader / workbench Assist was still running the 15-step LangGraph agent, 30 heuristic LLM traces, binary classifier load, and wall artifacts. That was slow and crashed in `cv2.distanceTransform` after the pipeline finished.
- Key changes: Default fast profiles (`contour_anchored_fast`, `fast`, `classify_only`, `no_agent`, reader payloads) now call the binary head plus the T-stage classifier. LangGraph, wall, DINO, RAG, and remote LLM are skipped. The 良/恶性 card reads `binary_gate` first and no longer treats T-stage top-1 as malignancy probability. `distanceTransform` now squeezes the mask to a contiguous 2D uint8 array.
- Validation: `python3 pipeline/agent/product/test_classify_only_adapter.py`. Next request uses the new Python path without a Next rebuild.
- Deployment: Workstation Python only. Public Next still forwards the same payload. Optional Next rebuild if the route env change should also land on `:3300` standalone.
- Follow-up: Pass `assist_profile=full` only when the full agent is intentionally needed.

## 2026-08-22, Public analyze keeps session across tunnel

- Scope: `lib/agent-upstream.ts`, public edge cookie accept, workstation proxy analyze path.
- Reason: Public analyze is forwarded to workstation `:3300` via `NEXT_AGENT_UPSTREAM`. The tunnel request dropped the doctor session, so workstation returned `请重新登录` after the doctor had already signed in.
- Key changes: Forward session headers on the Agent tunnel and inject a fallback token after public auth. Edge also accepts a raw Next cookie. Reader workbench analyze sends auth headers.
- Validation: Public cookie-only analyze is no longer 401. With a lesion polygon it returns `400` missing frame, not `请重新登录`.
- Deployment: Auth snapshot `20260822_231550`. Public Next BUILD `VOD-953qq6Q9K_aLRbZ7Q`. Workstation BUILD `7KO-xztEnHr7lamgp2aR0` on `:3300`.
- Follow-up: Hard refresh. Rollback: Aliyun auth `*.bak_20260822_231550`; Next previous BUILD `sG7KQ68DT79LRoK2bY2-K`.

## 2026-08-22, Analyze uses Next login token

- Scope: public edge `auth_server.mjs`; Next fetch session headers.
- Reason: Doctors were already signed in on Next but analyze got `请重新登录`. The edge treated skip-auto-login or a missing edge cookie as logged out, and ignored the Next session token header.
- Key changes: Edge proxies analyze when a Next cookie or `x-doctor-session-token` is present. Skip-auto-login no longer blocks authenticated APIs. The client does not send skip when a token exists.
- Validation: `node --check` auth snapshot. After swap: public root 200; LAN `:3000` 200; `:3300` contract 200.
- Deployment: Auth snapshot `20260822_231010`. Public Next BUILD `sG7KQ68DT79LRoK2bY2-K` (previous `5wou4s26tqRft5zQOfyZM`). Workstation BUILD `0RXzoPUNcnsLM0u_90MHS` on `:3300`.
- Follow-up: Hard refresh. Rollback: Aliyun auth `*.bak_20260822_231010`; Next previous BUILD `5wou4s26tqRft5zQOfyZM`.

## 2026-08-22, Shorten expired-login prompt

- Scope: Next login-error / LoginGate; public edge 401 JSON; proxy auth 401.
- Reason: Analyze 401 showed a long Chinese sentence about lesions. Any 401 was treated as expired login.
- Key changes: Prompt is now `请重新登录`. Only `auth_required` / expired-login payloads use that copy.
- Validation: `node --check` auth snapshot. After swap: public root 200; LAN `:3000` 200; `:3300` contract 200.
- Deployment: Auth snapshot `20260822_230523`. Public Next BUILD `5wou4s26tqRft5zQOfyZM` (previous `3SmkM5ctWQZu8KHifbHPu`). Workstation BUILD `yGXy42LECklNw5nt6wTod` on `:3300`.
- Follow-up: Hard refresh. Rollback: Aliyun auth `*.bak_20260822_230523`; Next previous BUILD `3SmkM5ctWQZu8KHifbHPu`.

## 2026-08-22, Public login uses Next only

- Scope: Aliyun auth edge; Next LoginGate / DoctorAccountModal; logout stay-on-page.
- Reason: Doctors were hitting a separate HTML login that asked for an optional account and advertised a 180-day cookie. Public sign-in should be one Next password form.
- Key changes: Unauthenticated workbench HTML goes to Next. `/workbench_login.html` redirects to `/`. Public login is password-only. The 180-day copy is removed.
- Validation: `node --check` on the Aliyun auth snapshot; `npx tsc --noEmit`. After swap: `/workbench_login.html` 302 to `/`; public root 200; LAN `:3000` 200; `:3300` contract 200.
- Deployment: Auth snapshot `20260822_230137` + `gastric-reader` restart. Public Next BUILD `3SmkM5ctWQZu8KHifbHPu` (previous `dSlP6Z-0eUAbSRDwcLNs_`). Workstation BUILD `iM9WxdOIiInT_KspveA4S` on `:3300` (previous `WaTYsETzaPaM8t8eh2S8O`).
- Follow-up: Hard refresh public browsers. Rollback: Aliyun auth `*.bak_20260822_230137`; Next previous BUILD `dSlP6Z-0eUAbSRDwcLNs_`.

## 2026-08-22, Logout clears both public sessions

- Scope: public edge `auth_server.mjs` / `workbench_login.html`; Next account GET/POST, LoginGate, doctor session client.
- Reason: Sign-out only cleared the Next cookie. The edge `reader_session` stayed valid, so the next account GET reminted a doctor session and the workbench looked still logged in.
- Key changes: Logout now clears `gastric_doctor_session` and `reader_session`. Edge `/api/logout` clears both. Skip-auto-login blocks inherit and remint. Explicit logout returns to the login page (public) or identity picker (LAN) instead of the expiry overlay.
- Validation: `node --check` on the Aliyun auth snapshot; `node apps/gastric_scan_next/scripts/test_session_cookie.mjs`; `npx tsc --noEmit`. After swap: public login 200, root 302, `/api/logout` 200; LAN `:3000` 200; `:3300` contract 200.
- Deployment: Auth snapshot `20260822_225723` + `gastric-reader` restart. Public Next BUILD `dSlP6Z-0eUAbSRDwcLNs_` (previous `vo-ueXW6ZbdwsDQdCCqSt`). Workstation BUILD `WaTYsETzaPaM8t8eh2S8O` on `:3300` (previous `mPCc7tCt3Kqj8C0i-Zuiw`).
- Follow-up: Hard refresh public browsers once. Rollback: Aliyun auth `*.bak_20260822_225723`; Next previous BUILD `vo-ueXW6ZbdwsDQdCCqSt`.

## 2026-08-22, Deploy public login keep-alive and richer admin stats

- Scope: Aliyun auth edge + public Next; workstation `:3000` / `:3300`; `/admin/ops`.
- Reason: Doctors need a one-login public workbench that does not fail mid-analysis, and admin needs public login / analyze / decision counts in one place.
- Key changes: Public audit events now ingest to the workstation. Login success/fail is recorded. Heartbeat writes active and wall seconds. Admin summary cards add sign-in, analyze, decided, LAN/public.
- Validation: `npx tsc --noEmit`; session cookie test. After swap: Aliyun login 200, account JSON 200, clinical 200; LAN `:3000` 200; `:3300` contract 200; tunnel `18768` contract 200.
- Deployment: Auth snapshot `20260822_224920` + `gastric-reader` restart. Public Next BUILD `vo-ueXW6ZbdwsDQdCCqSt` (previous `n4tUUkqvhbbuEp7hX96G1`). Workstation BUILD `mPCc7tCt3Kqj8C0i-Zuiw` on `:3300` (previous `e31aN8Vuwz1reInNxzyLr`). Imported 9700 Aliyun audit lines into `runtime/gastric_scan_next/reader_audit_events_public.jsonl`.
- Follow-up: Hard refresh public browsers. Rollback: Aliyun auth `*.bak_20260822_224920`; Next `.next-public-deploy-dist.bak_*` from this stamp.

## 2026-08-22, Public Next login stays alive during analysis

- Scope: public edge `auth_server.mjs` / `workbench_login.html`; Next doctor session cookie, session store, LoginGate, fetch patch.
- Reason: Doctors sometimes saw English `Login failed` after a valid password, and analyze died with 401 when the edge `reader_session` expired while the Next cookie was still good.
- Key changes: Edge accepts a still-valid Next session cookie, slides `reader_session`, default 180 days. Login page remembers the account and continues even if Next mint lags. Next cookies carry `aid` so a lost session file can be restored. Session JSON writes are locked. Same-origin `/api` 401s refresh once and retry. Login overlay does not unmount the workbench.
- Validation: `node apps/gastric_scan_next/scripts/test_session_cookie.mjs`; `node --check` on the Aliyun auth snapshot; `npx tsc --noEmit` in `apps/gastric_scan_next`.
- Deployment: Swap Aliyun `auth_server.mjs` and `workbench_login.html`, restart `gastric-reader`, then rebuild / swap public Next. Workstation Next can take the same client build.
- Follow-up: Hard refresh public browsers once. Rollback: restore the previous Aliyun auth snapshot and the previous Next standalone.

## 2026-08-22, GastricUS TabPFN xlarge, pad modes, T2 error

- Scope: `--pad reflect|edge|mean`; `--head tabpfn` on default concat-gated writes `medsiglip_gastricus_tabpfn_xlarge_20260822/` (does not overwrite 20260821); `t2_error.py` / `t2-error`.
- Reason: Confirm TabPFN on the current default head; black square-pad was the only fill; T2 recall is the unstable class.
- Key changes: New pad caches. CLI default remains black / 20% / mlp. Expand 15/20/25 reports are not overwritten.
- Validation: TabPFN xlarge prosp 0.6071 / ext 0.5031, T2 recall 0. T2 write-up is on disk. Pad-reflect encode pending.
- Deployment: Opt-in flags only.
- Follow-up: Train pad-reflect after encode. Do not re-run 15/20/25 MLP.

## 2026-08-22, GastricUS mask-overlay third view

- Scope: `mask_view.py`, CLI `--mask-view`; cache `maincenter_retrospective_v20260821_maskview/`; report `medsiglip_gastricus_maskview_20260822/`.
- Reason: The plan lists lesion masks as an input. Geometry scalars did not help. Encode a highlighted overlay through frozen MedSigLIP and concat to the 20% tokens.
- Key changes: `e_full = [full20, mask]`, `e_roi = [roi20, mask]`, 2304-d. New cache. CLI default unchanged.
- Validation: Pending held-out SUMMARY.
- Deployment: Opt-in flag only.
- Follow-up: Train concat-gated MLP and TIME-192 after encode.

## 2026-08-22, GastricUS softmax stack and mask geometry

- Scope: `stack.py`, CLI `stack`; `mask_geom.py`, `--mask-geom`. Reports `medsiglip_gastricus_stack_20260822/` and `medsiglip_gastricus_maskgeom_20260822/`.
- Reason: Hard-label votes peaked at 0.6188 / 0.5794. The plan lists lesion masks as an input; they were only used for ROI boxes.
- Key changes: Softmax stack of existing frozen heads (new folder). 10-d mask geometry sidecar, not written into embedding npz. CLI train default unchanged. `ensemble` still writes the first vote folder.
- Validation: Stack `val_mix` prosp 0.6165 / ext 0.5794. Mask-geom MLP 0.5365 / 0.4990; TIME-192 0.5976 / 0.5010. None is 0.75.
- Deployment: Opt-in command / flag only.
- Follow-up: Report both held-out exact ACCs. Do not promote without 0.75 on both.

## 2026-08-22, GastricUS ensemble3 vote

- Scope: `ensemble.py` `MEMBERS_V3`; report `medsiglip_gastricus_ensemble3_20260822/`.
- Reason: Prior votes omitted the best external head (15% TIME-192).
- Key changes: New folder. Members are default gated, 15% TIME, layers4 TIME, 20% TIME. Does not overwrite ensemble or ensemble2. CLI `ensemble` still writes the first vote folder.
- Validation: `t3_rescue` prosp 0.6071 / ext 0.5794. Not 0.75.
- Deployment: Opt-in Python call only.
- Follow-up: Soft / logit stack is unused. Do not re-run the same hard-vote members.

## 2026-08-22, GastricUS multi-expand 15/20/25 tokens

- Scope: `multi_expand.py`, CLI `--multi-expand`; cache `maincenter_retrospective_v20260821_multi1525/`; report `medsiglip_gastricus_multi1525_20260822/`.
- Reason: 15% and 20% single-ROI heads are complementary on prospective vs external. Concatenate existing frozen tokens instead of another encoder unfreeze.
- Key changes: `e_full = [full20, roi15]`, `e_roi = [roi20, roi25]`, 2304-d per view. Does not overwrite 15/20/25 caches. CLI default unchanged.
- Validation: `mlp_concat_gated` prosp 0.5553 / ext 0.4804; TIME-192 0.5812 / 0.5464. Neither is 0.75.
- Deployment: Opt-in flag only.
- Follow-up: Train concat-gated and TIME-192 on the merged cache.

## 2026-08-22, GastricUS Chinese experiment report

- Scope: `scripts/write_gastricus_zh_report.py`; `gastricus_ledger/中文报告.md` and `中文/逐次/`; pack `阅读说明.md` now starts there.
- Reason: Need one Chinese report that states every training setting and includes every train log, without weights.
- Key changes: Generator copies SUMMARY numbers, spec, epoch tables, full `train.log`, and cleaned console logs. Checkpoints and prediction CSVs stay out. Pack no longer overwrites existing `NEXT.md` / `IN_PROGRESS.md`.
- Validation: Scripted generation from on-disk reports only.
- Deployment: Ledger + Desktop pack. CLI train default unchanged.
- Follow-up: Re-run the writer after any new SUMMARY.

## 2026-08-22, GastricUS ensemble2 with layers TIME-192

- Scope: `ensemble.py` `MEMBERS_V2` / `ENSEMBLE2_REPORT_DIR`. Old `ensemble_20260822/` is not overwritten.
- Reason: layers4 + TIME-192 has held-out exact ACC 0.6118 / 0.5773 and T3 recall 0.536 / 0.423. Add it to a new vote.
- Validation: Val locked `majority_fallback_default`. Held-out exact ACC 0.6024 / 0.5505. Below layers-TIME single head 0.6118 / 0.5773 and below the first vote 0.6188 / 0.5443. Not 0.75.
- Deployment: New folder only. CLI `ensemble` still writes the original vote.
- Follow-up: Do not promote without both held-out exact ACCs.

## 2026-08-22, GastricUS last-4 layer tokens

- Scope: `pipeline/medsiglip_gastricus/layers.py`, CLI `--layers`; cache `maincenter_retrospective_v20260821_layers4/`; report `medsiglip_gastricus_layers4_20260822/`.
- Reason: Spatial lesion/context means did not lift held-out exact ACC. The unused visual axis is intermediate encoder tokens, not another 1152-d width sweep.
- Key changes: Concat official 1152-d global pool with last-4 vision-layer patch means (5760-d per view). New cache and report folders. Does not overwrite the 20% or spatial caches. CLI default unchanged.
- Validation: Encode completed (5760-d, four splits; 20% cache intact). concat-gated held-out exact ACC 0.5788 / 0.5464. Not 0.75. Do not promote.
- Deployment: Opt-in `--layers` on encode/train only.
- Follow-up: Encode when cuda:0 is free, then train concat-gated xlarge on the new cache.

## 2026-08-22, GastricUS preoperative clinical switch

- Scope: `--clinical preop` in `run_medsiglip_gastricus.py` / `train.py`; report `medsiglip_gastricus_preop_20260822/`.
- Reason: Lauren and differentiation may be postoperative. The plan still needed a preoperative-only clinical control on the frozen 1152-d cache.
- Key changes: Force those two fields to missing (norm=0, missing=1). Keep the 22-d layout. New report folder. CLI default stays `raw`.
- Validation: Pending held-out SUMMARY. Do not promote without prospective and external exact ACC.
- Deployment: CLI flag only. Default train path unchanged.
- Follow-up: Compare to default gated 0.5976 / 0.5216 and clinical-only 0.5176 / 0.5649. TIME-192 preop cache is a separate file and does not overwrite `tabpfn_clin11_time192.npz`.

## 2026-08-22, GastricUS plan-experiment pack for Desktop

- Scope: `scripts/pack_gastricus_experiments.py`, `pipeline/experiments/reports/gastricus_ledger/` (MASTER, logs, 阅读说明).
- Reason: Keep every plan-driven GastricUS SUMMARY and train log in one folder, then copy that pack to the Desktop without moving originals.
- Key changes: Pack copies markdown, logs, slim metrics, and plan snapshots only. Checkpoints and prediction CSVs (patient IDs) stay in the original report folders. MASTER now includes the plan-item map and a val-ACC digest of every train log.
- Validation: Scripted pack; no new held-out number. Target remains 0.75 exact ACC on prospective and external.
- Deployment: Desktop folder + zip. Repo originals unchanged. CLI default unchanged.
- Follow-up: Re-run the pack after freeze-head LoRA finishes and after `eval-unfreeze`.

## 2026-08-22, GastricUS ledger, label-vote, LoRA last-4

- Scope: `pipeline/experiments/reports/gastricus_ledger/`, `scripts/sync_gastricus_ledger.py`, `pipeline/medsiglip_gastricus/ensemble.py`, `unfreeze.py`, CLI `ensemble` / `--unfreeze-lora`.
- Reason: Keep every GastricUS SUMMARY in one folder. Frozen 1152-d heads sit near 0.62 / 0.58 exact ACC. The unused plan axis is the encoder. Target remains 0.75 exact ACC on both held-out splits.
- Key changes: Ledger copies markdown only; originals stay. Label-vote locks the rule on val. LoRA last 4 vision blocks, same concat-gated head, raw crop_ui, max 6 frames. CLI default unchanged.
- Validation: Ledger copied 33 SUMMARY files. Label-vote `t3_rescue` prosp exact ACC 0.6188 / ext 0.5443. LoRA smoke: 5.4 GB, 13.3M trainable, 5-frame bag on cuda:0. LoRA held-out ACC is pending `medsiglip_gastricus_unfreeze_lora_20260822/`.
- Deployment: Report folders and CLI flags only. Do not promote LoRA or vote without both held-out exact ACCs and McNemar.
- Follow-up: Finish LoRA train. If it misses 0.75, last-4 full FT (`--unfreeze-full`) or `--spatial`. Refresh the ledger after each run.

## 2026-08-22, GastricUS spatial tokens and full last-N FT

- Scope: `spatial.py`, `--spatial`, `--unfreeze-full`, warm-head LoRA on cuda:1.
- Reason: Frozen global 1152-d is the visual ceiling. Cold LoRA relearns the head. Need a warm head, a spatial patch cache, and a full last-N path.
- Key changes: ROI-masked 32x32 patch means concatenated to 2304-d. Full fine-tune last N vision layers without LoRA. Mask grid stretched to 448 then 32 to match the processor.
- Validation: Spatial CPU smoke, 2 frames, lesion L2 0.98, dim 2304. Warm-head epoch 1 val exact ACC 0.5625 (default gated val 0.5391). No held-out yet.
- Deployment: CLI flags only. Default train path unchanged.
- Follow-up: Full spatial encode when a GPU frees. Do not promote warm-head on val n=128.

## 2026-08-22, GastricUS plan-literal leftovers

- Scope: encode `--expand`, `--frame-sample`, `--pool-out`, `--head tabpfn_time`, `--plan-literal-sweep`; report `pipeline/experiments/reports/medsiglip_gastricus_plan_literal_20260822/`.
- Reason: The written plan still lacked ROI 15/25 switches, 64/128 gated dim, frame sampling, clinical-only TabPFN, and TIME-192. PLAN_MAPPING was still describing the first-train default.
- Key changes: Reuse full-frame vectors when re-encoding ROI expand. Clinical-only TabPFN is an independent 4-class baseline. TIME-192 uses official TabPFNEmbedding. Docs rewritten in PLAN_MAPPING / BACKBONE §2.14.
- Validation: Same 20% frozen cache. Clinical-only ext ACC 0.5649. TIME-192 prosp 0.6000 / ext 0.5711. McNemar vs default: prosp p = 1.00, ext p = 0.032. T2 recall 0.059 / 0.030. CLI default unchanged.
- Deployment: Report and CLI flags only. Expand 15/25 caches and heads are now on disk.
- Follow-up: Closed. 15/20/25 McNemar all p > 0.13. TIME-192 external p = 0.032 vs default; do not change the CLI default.

## 2026-08-22, GastricUS serosa binary, T3/T4 subset, and McNemar

- Scope: `pipeline/medsiglip_gastricus/binary.py`, dataset task filter, `--binary-sweep`, report `pipeline/experiments/reports/medsiglip_gastricus_binary_20260822/`.
- Reason: Pair-mass loss only flipped T3/T4 bias. Need a dedicated serosa head, a T3-vs-T4+ subset head, a 4-class cascade, and paired McNemar on the existing checkpoints.
- Key changes: 2-class concat heads for T4+ vs rest and T3 vs T4+. Cascade replaces T3/T4+ from the default 4-class gated checkpoint. Exact McNemar on prospective/external prediction CSVs.
- Validation: Same frozen cache, 115.56 s on cuda:0. Oracle T3/T4 mean prosp ACC 0.737 (majority 0.623), ext 0.612 (majority 0.615). Default 4-class on that subset is 0.616. Cascade prosp ACC 0.565. McNemar default vs pair-loss p = 0.0895. Do not promote.
- Deployment: Report-only. CLI default unchanged. Encoder still frozen.
- Follow-up: Reader study or unfreeze the last MedSigLIP block. Downstream heads on the frozen 1152-d tokens are exhausted.

## 2026-08-22, GastricUS T3/T4 lever training

- Scope: `pipeline/medsiglip_gastricus/` train/model/metrics, `scripts/run_medsiglip_gastricus.py`, report `pipeline/experiments/reports/medsiglip_gastricus_t34_20260822/`.
- Reason: Width and expected-rank SmoothL1 left T3→T4+ as the main error. Need cost ordinal, T3/T4 pair-mass penalty, a serosa auxiliary head, and QWK lock on the same frozen cache.
- Key changes: `--ordinal-mode cost`, `--t34-weight`, `--aux-serosa-weight`, `--lock qwk|macro`, `--t34-sweep`. Five xlarge concat runs. CLI default stays concat + gated + lock exact ACC.
- Validation: Same 1062/128/425/485 cache, 196.92 s on cuda:0. Pair-loss prosp ACC 0.548 / T3 0.580, ext ACC 0.538 / T3 0.577. QWK lock ext ACC 0.435 (majority T4+ baseline). Stacking all three levers is worse. Do not promote.
- Deployment: Report-only. Encoder still frozen.
- Follow-up: Reader study or unfreeze the last MedSigLIP block. Do not retune 4-class loss weights as the next width-like search.

## 2026-08-21, admin decision stats and workstation plus public deploy

- Scope: `/admin/ops`, `/api/admin/ops-stats`, `lib/ops/store.ts`, workstation standalone, Aliyun reader-only Next.
- Reason: Accept/reject must be visible in the admin backend, and both the workstation and public site need the new physician-then-AI-then-accept flow.
- Key changes: Admin now merges ops JSONL with audit decision events. Doctor table adds Initial / Accept / Modify / Reject / Decided. Case table adds Physician / AI / Final / Decision. New accept-reject log and decision CSV. Deployed the workbench panel with the stats page.
- Validation: `npx tsc --noEmit`. Workstation `:3000/` 200, `:3300/api/agent/contract` 200, `/admin/ops` 200. Aliyun `gastric-next` active, next3000 200, edge login 200, public root 302, clinical 200.
- Deployment: Workstation BUILD `e31aN8Vuwz1reInNxzyLr` (previous `ycTKpeFl_q36RLx0P9azL`), backup `.next-standalone.bak_20260821_202157_pre_decision_admin`. Aliyun reader-only BUILD `n4tUUkqvhbbuEp7hX96G1` (previous `pApRFA1HX4eGMcJ_Jo7GA`) via `scripts/deploy_public_next.sh`.
- Follow-up: Hard refresh LAN and the public site. Login as admin and open `/admin/ops` to confirm the new columns.

## 2026-08-21, record physician accept/reject of AI judgment

- Scope: workbench decision panel, reader audit/ops event types, reader study accept path, `scripts/analyze_reader_audit_events.py`.
- Reason: Mask edits were logged, but whether the physician accepted the AI T-stage was not a first-class event. Everyday workbench also lacked doctor-first then AI then accept.
- Key changes: Right-panel 3-step trace (physician judgment, AI judgment, accept/modify/reject). New audit/ops types `ai_decision_accept` / `modify` / `reject` / `more_evidence` plus `stage_override`. Regular workbench now audits sign/stage edits, not only `reader_v150`. Agent panel waits until the physician judgment is recorded.
- Validation: `npx tsc --noEmit` passed in `apps/gastric_scan_next`. Existing `doctor_action` events remain for compatibility.
- Deployment: Source landed first; workstation and public BUILD ids are in the deploy entry above.
- Follow-up: Closed by the admin-stats deploy on the same day.

## 2026-08-21, expert reading of GastricUS results

- Scope: `BACKBONE_VS_PLAN.md` §2.7–2.11, `EXPERIMENT_RECORD.md` §6.
- Reason: Score tables alone invite over-reading 0.598 and 0.87 adjacent ACC. Need prevalence, majority baselines, sampling error on the 0.019 gap, and why gated eats T3.
- Key changes: Prospective T4+ prior 43.5% vs train 29.9%. Gated predicts T4+ for 62.1% of prospective cases. Majority T4+ baseline 0.435. Always-T3 adjacent baseline 0.779. The 0.019 gated-vs-mean gap is within SE. Next levers ranked: reader study, T3/T4 head, unfreeze encoder.
- Validation: Counts from patient_bags and the concat-gated confusion matrix. No new training. No number in the reports changed.
- Deployment: Docs only.
- Follow-up: McNemar on the two checkpoints if a promotion decision is needed.

## 2026-08-21, GastricUS full experiment record

- Scope: `pipeline/medsiglip_gastricus/EXPERIMENT_RECORD.md` and `pipeline/experiments/reports/medsiglip_gastricus_opt_xlarge_20260821/logs/`.
- Reason: The backbone-vs-plan note was too short for data counts, module widths, five-round specs, confusion matrices, and epoch logs.
- Key changes: Record the clean 1062/128/425/485 contract, MedSigLIP cache shapes, fusion/pool/head presets, loss and lock, all five rounds, current concat-gated tables, and exported histories/console log.
- Validation: Counts from `inventory.json`, split CSVs, `encode_summary.json`, and each `metrics.json`. No new training. No patient names.
- Deployment: Docs and report logs only.
- Follow-up: None.

## 2026-08-21, GastricUS backbone vs plan summary

- Scope: `pipeline/medsiglip_gastricus/BACKBONE_VS_PLAN.md`, README / PLAN_MAPPING links.
- Reason: The first draft listed alignment first and dumped scores late. Need a results-forward note: what the numbers support, T3/T4+ as the main error, and why width and clinical do not lift both held-out sets.
- Key changes: Lead with the current default and the 0.598 vs 0.579 / 0.522 vs 0.542 trade-off. Add analysis of fusion, pool, lock metric, clinical ablation, and per-center mix. Compact the plan checklist. Academic-humanizer pass: shorter sentences, every claim tied to a report number, no promotion.
- Validation: Numbers copied from the four COMPARE / SUMMARY reports. No new training. No number changed.
- Deployment: Docs only.
- Follow-up: Refresh PLAN_MAPPING stale sections when that file is next edited.

## 2026-08-21, optimize GastricUS then train xlarge heads

- Scope: `pipeline/medsiglip_gastricus/model.py`, `train.py`, `scripts/run_medsiglip_gastricus.py`, report `pipeline/experiments/reports/medsiglip_gastricus_opt_xlarge_20260821/`.
- Reason: The last width bump locked adjacent ACC and compressed plan 5.1 to 128-d. Need ordinal loss, exact-ACC lock, raw 2304-d means, residual fusion, and the missing concat+gated cell, then a larger head.
- Key changes: `--size xlarge` (11–34M). Residual fusion. Plan 5.1 stays 2304-d unless `--pool-proj`. Loss = balanced CE + 0.5 expected-rank SmoothL1. Lock = val exact ACC. `--clinical none` image-only. `--opt-sweep` trains concat-mean, concat-gated, interact-gated, image-only.
- Validation: Four runs on the same frozen cache, early stop 61 / 57 / 31 / 49. Best `mlp_concat_gated` prosp ACC 0.598 / adj 0.868, ext 0.522 / 0.819. Beats small concat-mean exact ACC 0.579 / 0.542. Image-only prosp 0.560. Interact 34M still worse. Gated T3 recall stays low.
- Deployment: Report-only. CLI default is now concat + gated + xlarge. Do not promote.
- Follow-up: Encoder is still frozen. Next lever is unfreeze or a different visual token, not another MLP width.

## 2026-08-21, larger GastricUS head and longer cosine training

- Scope: `pipeline/medsiglip_gastricus/model.py`, `train.py`, report `pipeline/experiments/reports/medsiglip_gastricus_large_20260821/`.
- Reason: The first heads were 0.13-5.3M and stopped after 40 flat epochs. Need a wider MLP and a proper schedule.
- Key changes: `--size large` (concat 4.6M, gated 13.2M) with LayerNorm. Default 80 epochs, 8-epoch warmup, cosine decay, label smoothing, grad clip, patience-20. Skip the collapsed stats pool.
- Validation: Early stop at 28 / 35 / 50. Best large gated MLP: prosp ACC 0.520 / adj 0.868, ext 0.520 / 0.852. Does not beat small concat-mean exact ACC 0.579 / 0.542.
- Deployment: Report-only. Default CLI is now large.
- Follow-up: Capacity is not the main bottleneck; next lever is the frozen tokens or the ordinal loss, not another width bump.

## 2026-08-21, GastricUS plan variants with adjacent and per-center scores

- Scope: `pipeline/medsiglip_gastricus/` fusion/pool variants, `metrics.py`, report `pipeline/experiments/reports/medsiglip_gastricus_plan_20260821/`.
- Reason: Plan 4.1 / 5.1 / 5.2 were missing. Training reports needed adjacent T-stage scores and hospital-level ACC.
- Key changes: Concat fusion, mean-view pool, stats pool. Balanced class weights. Lock on val adjacent ACC. Write confusion, QWK, off-by-2, and per-center tables.
- Validation: Four runs on the same frozen cache. `mlp_concat_mean` prosp/ext ACC 0.579 / 0.542, adj 0.833 / 0.835. `tabpfn_interact_gated` adj 0.887 / 0.876. Stats pool collapsed. Small external centers remain noisy.
- Deployment: Report-only. Do not promote.
- Follow-up: Drop or restabilize stats pooling.

## 2026-08-21, box auto-seg uses SAM3.1 only

- Scope: `apps/gastric_scan_next/components/InteractiveSegPanel.tsx`, `apps/gastric_scan_next/lib/reader/doctor-keyframe-preseg.ts`.
- Reason: Frozen Dice favors SAM3.1 LoRA over SAM2 r004 on the same prospective 46-patient box protocol (0.8816 vs 0.8788). Doctor box auto-seg had been routed to SAM2 for latency.
- Key changes: Box, candidate, and keyframe preseg now call SAM3.1 once. SAM2 is not used on the doctor prompt path.
- Validation: `npx tsc --noEmit`. Workstation `:3000` 200, `:3300` contract 200. Aliyun Next 200, login 200, clinical 200.
- Deployment: Workstation BUILD `ycTKpeFl_q36RLx0P9azL` (previous `Zy7gG2dEzEmTabwjmoIj2`), backup `.next-standalone.bak_20260821_190452_pre_sam31dice`. Aliyun reader-only BUILD `pApRFA1HX4eGMcJ_Jo7GA` (previous `E-VAjGZuvCYS5aFn6Lk0i`).
- Follow-up: Hard refresh LAN and the public site.

## 2026-08-21, drop box quality gate and cascade

- Scope: `apps/gastric_scan_next/components/InteractiveSegPanel.tsx`, `apps/gastric_scan_next/lib/reader/doctor-keyframe-preseg.ts`.
- Reason: Doctor box auto-seg was slow because it tried SAM2, then SAM3.1, then the lesion endpoint, and leftover quality / oversize gates still discarded masks.
- Key changes: Box auto-seg now makes one SAM2 call. Area, box-IoU, and oversize gates are off for doctor prompts. Keyframe preseg takes the first valid SAM2 polygon instead of scoring a four-backend cascade.
- Validation: `npx tsc --noEmit`. Workstation `:3000` 200, `:3300` contract 200. Aliyun Next 200, login 200, clinical 200.
- Deployment: Workstation BUILD `Zy7gG2dEzEmTabwjmoIj2` (previous `ZCyYr6Rh6R1HV4Dz4AjQE`), backup `.next-standalone.bak_20260821_180655_pre_fastbox`. Aliyun reader-only BUILD `E-VAjGZuvCYS5aFn6Lk0i` (previous `aOSveiLkqu0rQ8p0-Bx-S`).
- Follow-up: Hard refresh LAN and the public site.

## 2026-08-21, GastricUS route B TabPFN clinical head

- Scope: `pipeline/medsiglip_gastricus/tabpfn_clinical.py`, `train.py --head tabpfn`, report `pipeline/experiments/reports/medsiglip_gastricus_tabpfn_20260821/`.
- Reason: The plan's second head is `[z_image, TabPFN(clinical)] → MLP`. Route A only used raw clinical-22.
- Key changes: Fit TabPFN-2.5 on clinical-11 with NaN missing flags. Train uses 5-fold OOF probabilities. Image 1152-d tokens never enter TabPFN. Fusion and attention stay the same as route A.
- Validation: Best val epoch 26, ACC 0.570, T2 recall 0.273. Prospective ACC 0.478. External ACC 0.480. Versus route A: lower ACC, higher T2 recall.
- Deployment: Report-only. Do not promote.
- Follow-up: Optional 192-d TabPFN embedding variant if a TIME-style token is wanted.

## 2026-08-21, keep doctor box masks and drop boxing toast

- Scope: `apps/gastric_scan_next/components/InteractiveSegPanel.tsx`.
- Reason: Box auto-seg often showed 「自动分割未成功」because a quality gate discarded the SAM polygon, and 「正在框选病灶」covered the ultrasound.
- Key changes: Doctor box prompts no longer go through the preseg quality gate. Polygon coordinates use `scalePolyToFull`. If SAM still fails, the drawn box stays as the contour. The on-canvas 「正在框选病灶」card and button label change are gone.
- Validation: `npx tsc --noEmit`. Workstation `:3000` 200, `:3300` contract 200. Aliyun Next 200, login 200, clinical 200.
- Deployment: Workstation BUILD `ZCyYr6Rh6R1HV4Dz4AjQE` (previous `zSYPIOMWh-g1ZjkuNlQIK`). Aliyun reader-only BUILD `aOSveiLkqu0rQ8p0-Bx-S` (previous `9abKzlw7_L72Dt0ZVGJmz`).
- Follow-up: Hard refresh LAN and the public site.

## 2026-08-21, box-draw cursor stays visible

- Scope: `apps/gastric_scan_next/components/InteractiveSegPanel.tsx`.
- Reason: After arming 「框选病灶」, the pointer vanished over the ultrasound. The custom SVG cursor was double-encoded (`%23` run through `encodeURIComponent`), so Chromium loaded an empty cursor.
- Key changes: Box-lesion and box-lumen use the system `crosshair`, which always stays visible.
- Validation: `npx tsc --noEmit`. Workstation `:3000` 200, `:3300` contract 200. Aliyun Next 200, login page 200, public root 302, clinical 200.
- Deployment: Workstation BUILD `zSYPIOMWh-g1ZjkuNlQIK` (previous `DIAp02-UsJIS_S3OoIrhG`), backup `.next-standalone.bak_20260821_175257_pre_cursor`. Aliyun reader-only BUILD `9abKzlw7_L72Dt0ZVGJmz` (previous `4R1o3rlE8SCkv3FELcyIM`) via `scripts/deploy_public_next.sh`.
- Follow-up: Hard refresh LAN and the public site.

## 2026-08-21, workstation deploy for box-lesion UI

- Scope: `apps/gastric_scan_next/.next/standalone`, `gastric-next.service`, `gastric-next-public.service`.
- Reason: Ship the box-button overlay fix, remove the on-canvas geometry card, and use thinner dimmer contours.
- Key changes: Rebuilt Next standalone. Previous pack kept at `.next-standalone.bak_20260821_174844_pre_box_ui`.
- Validation: `npx tsc --noEmit`. `:3000` 200, `:3300` contract 200. Muted stroke `94, 184, 196` present in the new chunk.
- Deployment: Workstation BUILD `DIAp02-UsJIS_S3OoIrhG` on `:3000` / `:3300` (previous `TMyHqJk2Yh6hcCuHiPBIZ`). Restarted `gastric-next` and `gastric-next-public` only. No Aliyun swap.
- Follow-up: Hard refresh the workbench. Roll back by restoring the bak directory and restarting the two units.

## 2026-08-21, thinner and dimmer lesion contours

- Scope: `apps/gastric_scan_next/components/InteractiveSegPanel.tsx`.
- Reason: The lesion outline was too thick and too bright, so the ultrasound mass was hard to see.
- Key changes: Contour stroke is 1 px and muted teal. Lumen and wall strokes are also dimmed. The extra dark halo is 1.6 px instead of 4.5 px.
- Validation: Constants and redraw pass updated; lints clean on the panel file.
- Deployment: Workstation `:3000` hot reload.
- Follow-up: None.

## 2026-08-21, remove on-canvas lumen-lesion geometry card

- Scope: `apps/gastric_scan_next/components/InteractiveSegPanel.tsx`.
- Reason: After boxing a lesion, the smoothness / outward-expansion / editing-logic card covered the ultrasound and was not useful during reading.
- Key changes: Remove the floating geometry card from the canvas. Geometry is still computed for zoom and analysis; it is no longer drawn over the lesion.
- Validation: Overlay block removed; typecheck of the Next app.
- Deployment: Workstation `:3000` hot reload.
- Follow-up: None.

## 2026-08-21, Box lesion button click was covered by the top tool strip

- Scope: `apps/gastric_scan_next/components/InteractiveSegPanel.tsx`.
- Reason: Clicking 「框选病灶」often did nothing. The top “Mark frame / Assist” strip was full-width, `pointer-events-auto`, and z-index 180, sitting on top of the right-rail button (z-index 140).
- Key changes: Only the actual top buttons capture clicks. The lesion rail is z-index 220. Clicking 「框选病灶」always lights the button; keyframe open/create is best-effort and no longer blocks arming.
- Validation: Typecheck of the Next app.
- Deployment: Workstation `:3000` hot reload. Public `:3300` still needs a standalone rebuild for the same fix.
- Follow-up: Rebuild `:3300` when public readers should use this interaction.

## 2026-08-21, lesion box draw no longer drops pointer events

- Scope: `apps/gastric_scan_next/components/InteractiveSegPanel.tsx`.
- Reason: 「框选病灶」often did nothing after the button lit up. Letterbox clicks returned null, an existing mask or nnInteractive stole the drag, opening a nearby keyframe disarmed the button, and in-flight SAM disabled the control.
- Key changes: Armed box-lesion starts a new rectangle immediately, including from the black bars. Auto-open keyframe cannot turn the button off. The button stays clickable during segmentation. Drag updates clamp to the image.
- Validation: Typecheck of the Next app. LAN `:3000` is `next dev` and picks this up on refresh.
- Deployment: Workstation `:3000` hot reload. Public `:3300` still needs a standalone rebuild if that edge should get the same fix.
- Follow-up: Rebuild `:3300` when public readers should use this interaction.

## 2026-08-21, first MedSigLIP-448 GastricUS training run

- Scope: `pipeline/medsiglip_gastricus/train.py`, report `pipeline/experiments/reports/medsiglip_gastricus_20260821/`.
- Reason: Cached frame embeddings were ready. The first train hung because `np.load` re-decompressed the zip on every frame.
- Key changes: Load each npz array once, then bag by patient. Train 40 epochs on frozen 1152-d embeddings plus clinical-22 MLP. No DualBranch / TabPFN checkpoint.
- Validation: Best val epoch 28, ACC 0.5859, T2 recall 0.0909. Prospective ACC 0.4941. External ACC 0.4784. Patient counts 1062 / 128 / 425 / 485.
- Deployment: Report-only. Encoder stays frozen. Do not promote this run.
- Follow-up: Class-balanced loss or T2-aware sampling if the next run should fix the T2 collapse.

## 2026-08-21, tstaging physical pack matches freeze inventory

- Scope: `tstaging/` images and masks, split CSVs, `COMPLETE.md`, `COVERAGE.md`, `scripts/supplement_tstaging_physical.py`.
- Reason: The screened pack was 10894 pairs. Official internal + external manifests are 13763 image-mask pairs.
- Key changes: Copy the remaining 2869 freeze stills into the same English folders. Extra CSV rows marked `supplement=1`. New retrospective patients go to train; existing val patients stay in val. 2025 stays in prospective. External stays under the hospital center. Do not invent T labels.
- Validation: 13763 unique stems; every row has image and mask; train/val/prospective/external patient overlap is zero; year and center folder counts match freeze `crop_ui`.
- Deployment: jpg/png remain gitignored. Modeling still uses `maincenter_retrospective_v20260821`. Rebuild leftover stills with the supplement script; do not run the screened copy script alone afterward.
- Follow-up: None for the physical copy.

## 2026-08-21, tstaging complete-inventory note

- Scope: `tstaging/COMPLETE.md`.
- Reason: 2100/10894 is the screened pack. Official T-staging stills are the internal + external manifests.
- Key changes: Record should-have stills: Xiehe 2018-2024 8229 (train/val), Xiehe 2025 2430 (prospective), 9 external hospitals 3104. Total 13763. Current pack is short 2869.
- Validation: Counts from `dataset/internal/manifest.csv`, `dataset/external/manifest.csv`, and on-disk `crop_ui`.
- Deployment: Docs only.
- Follow-up: Done in the physical-pack supplement entry above.

## 2026-08-21, tstaging coverage and per-center tables

- Scope: `tstaging/COVERAGE.md`, `tstaging/centers/*/original.csv`, `tstaging/centers/*/cleaned.csv`, `tstaging/gaps.csv`, `scripts/build_tstaging_center_tables.py`.
- Reason: Need a patient-level check against clinical master and Phase 0, plus per-center original vs cleaned tables.
- Key changes: 14 centers. Coverage lists totals, T-stage, freeze vs Phase 0 vs cleaned. No patient names.
- Validation: Cleaned pack 2100 patients / 10894 frames. Imaging drops: 15 Xiehe 2018 unmapped, 10 Xiehe 2025 train-only leak. Clinical-only patients stay in original.csv.
- Deployment: Tables and markdown only. Rebuild with the new script.
- Follow-up: None.

## 2026-08-21, Physical val / prospective / external by center

- Scope: `tstaging/val/`, `tstaging/prospective/`, `tstaging/external/`, matching `*.csv` files.
- Reason: Evaluation frames should sit in the same physical pack, grouped by Xiehe year or external hospital.
- Key changes: Copy paired images and masks. Val uses `2018` / `2019` / `2020_2023` / `2024`. Prospective uses `2025`. External uses English center slugs. CSV adds a `center` column.
- Validation: val 733/128, prospective 1659/425, external 2458/485; every row has image and mask on disk.
- Deployment: jpg/png gitignored. Rebuild with `scripts/copy_tstaging_physical_train.py`.
- Follow-up: None for the physical copy.

## 2026-08-21, English tstaging/train with paired masks and CSV

- Scope: `tstaging/train/`, `tstaging/train.csv`, `scripts/copy_tstaging_physical_train.py`.
- Reason: Physical pack should use English names; each image needs a same-stem mask; CSV paths must match the files.
- Key changes: Folders are `train` / `val` / `prospective` / `external`. Masks live in `masks/`. `train.csv` leads with `image_path` and `mask_path`.
- Validation: 6044/6044 image-mask pairs exist; file stems match; `image_exists` and `mask_exists` are 1.
- Deployment: jpg/png remain gitignored. README and CSV can be committed.
- Follow-up: Copy val / prospective / external in the same English layout when requested.

## 2026-08-21, Physical tstaging/ train copy at repo root

- Scope: `tstaging/训练/`, `scripts/copy_tstaging_physical_train.py`. Allowed in `check_repo_root.py`.
- Reason: Browse train frames in one folder named `tstaging`, without dated subpacks.
- Key changes: Copy Xiehe retrospective train `crop_ui` jpg and `roi_masks` png into `训练/2018|2019|2020_2023|2024`. Write `训练/manifest.csv`. Leave 验证 / 前瞻 / 外部 empty.
- Validation: Copy script checks source files exist; post-copy counts must match 6044 frames.
- Deployment: Images are local copies and gitignored. Source freeze files are not moved.
- Follow-up: Copy val / prospective / external when requested.

## 2026-08-21, Main-center retrospective T-staging dataset

- Scope: `dataset/task_datasets/t_staging/maincenter_retrospective_v20260821/`, `scripts/build_tstaging_maincenter_retrospective.py`, MedSigLIP constants now read this pack.
- Reason: Train must be Xiehe retrospective only. Phase 0 train/val still mixed `int/prospective`; `t_staging/splits` is the leaked 20260531 pack.
- Key changes: Four-way tables 训练/验证/前瞻/外部. Drop prospective from train/val, dedup freeze `crop_ui`, majority T, force clinical `-1` to missing, recompute train-only z-scores.
- Validation: Leak checks all zero. Train 6044/1062, val 733/128, prospective 1659/425, external 2458/485. All images and masks exist.
- Deployment: Modeling CSVs only; images stay in freeze `crop_ui`. Rebuild with the new script.
- Follow-up: Encode and train MedSigLIP against this pack after weight SHA256 passes.

## 2026-08-21, Phase 0 clinical-11 audit

- Scope: `pipeline/medsiglip_gastricus/DATA_AUDIT.md` section 4; note in `PLAN_MAPPING.md`.
- Reason: Labels are not only T-stage. The 11-field pack must be checked for match, missing-flag contract, codebook, within-patient stability, and marker self-consistency.
- Key changes: Recorded unmatched cohorts, the `_missing=0` plus value `-1` contract bug, 2019/2024 systematic marker gaps, and encode-time repair guidance.
- Validation: Read-only counts on Phase 0 `*_clinical.csv`. No training change.
- Deployment: Docs only.
- Follow-up: Treat sentinel `-1` as missing at encode time before the clinical head sees it.

## 2026-08-21, MedSigLIP GastricUS plan-to-code mapping

- Scope: `pipeline/medsiglip_gastricus/PLAN_MAPPING.md`.
- Reason: Trace `# GastricUS实验方案.md` onto the from-scratch package, including what is implemented and what is not.
- Key changes: Section-by-section mapping for preprocess, frozen encode, fusion, pooling, and MLP/TabPFN heads.
- Validation: Documentation only; no training change.
- Deployment: Local docs. Linked from `pipeline/medsiglip_gastricus/README.md`.
- Follow-up: Fill TabPFN and B0/B1/A0 variants if that ablation is requested.

## 2026-08-21, From-scratch MedSigLIP-448 GastricUS trainer

- Scope: new package `pipeline/medsiglip_gastricus/` and `scripts/run_medsiglip_gastricus.py`.
- Reason: GastricUS plan needs a frozen MedSigLIP-448 encoder plus new fusion / attention / clinical heads. Old DualBranch and TabPFN scripts are not reused.
- Key changes: Phase 0 path resolver to freeze `crop_ui` and mask; 20% ROI expand; embedding cache; patient-level train from random init.
- Validation: `prepare` coverage and encoder smoke after weight SHA256 check. Training starts only after `model.safetensors` verifies.
- Deployment: local scripts only. Weights live in `artifacts/model_weights/medsiglip-448/`.
- Follow-up: finish weight download, encode all Phase 0 splits, then train.

## 2026-08-21, NAC queue no longer double-counts surgery stills

- Scope: workbench patient list and `/api/patients` NAC path.
- Reason: Internal queues added surgery `total` plus NAC `total`. NAC reused the same still folders and could resolve to surgery clinical JSON (`_ultimate`).
- Key changes: NAC reads only `clinical_data_<year>_nac.json` (2019, 2024). Only stills whose PID is in that file are listed. Header is loaded cases / true frame total.
- Validation: Disk crop_ui stills 10,659. NAC matched stills 4 (2019) + 59 (2024). Internal-all total should be 10,722, not 21,318.
- Deployment: Source-only; `:3000` is `next dev`.
- Follow-up: Refresh the LAN workbench. Most NAC table rows still have no stills in the surgery crop tree.

## 2026-08-21, Chinese site labels on the clinical card

- Scope: historical evidence drawer clinical card.
- Reason: Sidecar locations like Cardia/Fundus stayed English. The fact grid was cramped and truncated.
- Key changes: Decode English/codebook sites to 贲门 / 胃底 and similar. Prefer the queue table site. Card shows site, pTNM chips, and report blocks as separate sections.
- Validation: Source-only; `:3000` is `next dev`.
- Deployment: No standalone rebuild.
- Follow-up: Refresh the LAN workbench.

## 2026-08-21, Readable clinical card; hide CBM on history

- Scope: historical evidence drawer.
- Reason: CBM sliders were placeholders. The table dump showed codebook headers and raw 0/1/2 codes.
- Key changes: Hide ConceptReasoning on historical queues. Clinical card decodes site, pTNM, Lauren, markers, and shows gold as T2 / I.
- Validation: Source-only; `:3000` is `next dev`.
- Deployment: No standalone rebuild.
- Follow-up: Refresh the LAN workbench.

## 2026-08-21, Fix LoginGate hydration text

- Scope: `apps/gastric_scan_next/components/LoginGate.tsx`.
- Reason: SSR had no `window`, so the splash said public login check; the browser on `127.0.0.1` said LAN opening.
- Key changes: First paint uses one host-agnostic line. LAN vs public is decided after mount.
- Validation: Source-only; `:3000` is `next dev`.
- Deployment: No standalone rebuild. `:3300` / Aliyun unchanged.
- Follow-up: Hard refresh if the overlay is still up.

## 2026-08-21, LAN :3000 uses Next hot reload

- Scope: `gastric-next.service` on the workstation, `scripts/run_gastric_next_dev.sh`.
- Reason: `127.0.0.1:3000` was the standalone production pack, so source edits never appeared until a full rebuild.
- Key changes: `:3000` now runs `next dev`. Saving a file Fast-Refreshs the page. `:3300` stays standalone.
- Validation: `systemctl --user is-active gastric-next.service` is active; `curl` `:3000/` after first compile.
- Deployment: Installed user unit from `scripts/systemd/gastric-next.service`. Restarted `gastric-next` only. No Aliyun swap.
- Follow-up: Hard refresh once after the first compile. Rollback: restore the previous production `ExecStart` on standalone `server.js`.

## 2026-08-21, Unify historical queues: gold, keyframes; hide GIST

- Scope: workbench queue picker, patient list, gold lookup, CBM load copy.
- Reason: Historical cases already have pathology gold and curated stills. GIST should not appear. CBM defaults (Ki67 45, CPS 5) were shown as loaded IHC.
- Key changes: Hide GIST from the picker. Historical stills are `case_keyframe`. Gold comes from the per-queue table. CBM says placeholders unless table IHC is present.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`.
- Deployment: Source ready; live standalone not rebuilt in this step unless a later entry records a BUILD id.
- Follow-up: Rebuild `:3000` / `:3300` to see the picker and gold chip.

## 2026-08-21, Per-queue clinical JSON for LAN history

- Scope: `dataset/tables/by_queue/`, `scripts/export_clinical_queue_json.py`, LAN workbench evidence panel.
- Reason: Historical queues needed original-table reports and numeric fields. Loading the 186MB combined registry at runtime is the wrong shape.
- Key changes: Each workbench queue gets its own JSON from `by_source` CSVs. Empty/unnamed columns and name fields are dropped. `/api/patients` loads only the current queue file on LAN. Evidence panel shows the original-table card.
- Validation: `python3 scripts/export_clinical_queue_json.py`. `node apps/gastric_scan_next/scripts/test_clinical_history.mjs`. `npx tsc --noEmit` in `apps/gastric_scan_next`.
- Deployment: Source ready; workstation standalone not rebuilt in this step unless a later entry records a BUILD id.
- Follow-up: Rebuild `:3000` / `:3300` to show the card. Reader-v150 stays on the blinded sidecar. NAC is still the existing year JSON, not `by_source`.

## 2026-08-21, Fix clipped case sidebar; BM list from 001

- Scope: workbench left case list layout and reader-v150 sort.
- Reason: The 13rem sidebar was narrower than the queue picker, so the header clipped and the canvas sat over the list. Benign cases were sorted by clinical fields, not BM-001.
- Key changes: Wider list (15rem), queue picker fits the column, no duplicate queue label, sidebar above the canvas. Reader-v150 groups and auto-select sort by BM-/CASE- number.
- Validation: `npx tsc --noEmit`. `:3000` 200, `:3300` contract 200.
- Deployment: Workstation BUILD `TMyHqJk2Yh6hcCuHiPBIZ` on `:3000` / `:3300` (previous `BqAIlk9MQo20Hvb3I-Sfc`). Restarted `gastric-next` and `gastric-next-public` only. No Aliyun swap.
- Follow-up: Hard refresh. Benign tab should open at BM-001. Rollback: `.next-standalone.bak_*_pre_sidebar_bm001`.

## 2026-08-21, Drop demo stills from the 150-case sidebar

- Scope: `apps/gastric_scan_next` patient list and `/api/patients` demo-still attach.
- Reason: The workbench sidebar opened with `1191583` demo stills labeled not scored. The first visible case should be the first scored Round-1 case.
- Key changes: `shouldAttachPublicDemoStills` is always off. The list no longer merges `demo_stills`, and demo cases are filtered out of grouping and auto-select.
- Validation: `node --experimental-strip-types scripts/test_public_demo_stills.mjs`. `npx tsc --noEmit`. `:3000` 200, `:3300` contract 200.
- Deployment: Workstation BUILD `BqAIlk9MQo20Hvb3I-Sfc` on `:3000` / `:3300` (previous `EvkyvQnNoj0ILQ-IcUkor`). Restarted `gastric-next` and `gastric-next-public` only. No Aliyun swap.
- Follow-up: Hard refresh the workbench. Rollback: `.next-standalone.bak_*_pre_drop_demo`.

## 2026-08-21, Hide overlay chips; box lesion auto-marks keyframe

- Scope: `apps/gastric_scan_next` main workbench overlays, Header sync chip, 150-case video box tool.
- Reason: Assist hub, reader/layer write-back, and unsynced-ops sat on the image. The live `:3000` standalone still served the old overlays. Clicking Box lesion in the 150-case queue did nothing unless a keyframe was already open.
- Key changes: Stop rendering `AssistHub` and `ReaderAgentResultCard`. Hide the Header `未同步` chip. Box lesion now pauses the video, opens a nearby keyframe or marks the current frame, then arms the box so a drag works immediately.
- Validation: `npx tsc --noEmit`. `node --experimental-strip-types scripts/test_doctor_keyframes.mjs`. `:3000` 200, `:3300` contract 200. Live HTML/chunks no longer contain the overlay copy.
- Deployment: Workstation BUILD `EvkyvQnNoj0ILQ-IcUkor` on `:3000` / `:3300` (previous `z2pgrHN_tENd9a6AU74x2`). Restarted `gastric-next` and `gastric-next-public` only. No Aliyun swap.
- Follow-up: Hard refresh the workstation. Rollback is a rebuild of the previous source; the in-`.next` standalone backup was removed by `cleanDistDir`.

## 2026-08-21, Drop BM template notice; lesion-first assist; box idle

- Scope: `BmEvidencePanel`, assist progress copy, simple-video / reader box idle state.
- Reason: The BM panel still advertised the docx template vs T-staging wall report. Assist progress listed T-staging before lesion signs. Box lesion looked armed on load, and the live workstation/public builds still had the old rail.
- Key changes: Removed that notice. Assist steps analyze the lesion first, then assign T stage. Box lesion stays idle (no cyan, no focus ring) until clicked. Auto-arm after keyframe preseg failure is off.
- Validation: `npx tsc --noEmit`. Workstation `:3000` 200, `:3300` contract 200. Aliyun `gastric-next` active, next3000 200, edge login 200, public clinical 200.
- Deployment: Workstation BUILD `z2pgrHN_tENd9a6AU74x2` on `:3000` / `:3300` (previous `7qX6PT62-5Vg36BxSPFaH`). Aliyun READER_ONLY BUILD `4R1o3rlE8SCkv3FELcyIM` (previous `ljx6qQ75EhTxw3VG6xH8w`).
- Follow-up: Hard refresh both workstation and public. Rollback: workstation `.next/standalone.bak_*_pre_box_idle`; Aliyun `.next-public-deploy-dist.bak_*` plus `server.js.bak_*`, then restart `gastric-next`.

## 2026-08-21, Fix Login required after a successful sign-in

- Scope: `apps/gastric_scan_next` doctor session resolve, session cookie, LoginGate client, `proxy.ts`. Aliyun auth snapshot adds `/api/viewing-trace` and `/api/admin` prefixes.
- Reason: After login the UI could stay signed in while `/api/reader/cases` and other routes returned `Login required`. The fetch patch sent a stale `x-doctor-session-token` from localStorage, and that header won over a valid HttpOnly cookie. A second login also deleted the first browser's token.
- Key changes: Try every candidate token (header, signed cookie, legacy hex cookie) and use the first that is still in the store. Keep multiple sessions per account. Accept unsigned hex cookies when a signing secret is set. If `/api/reader/account` says not authenticated, drop the stale client token.
- Validation: Before the swap, stale `x-doctor-session-token` plus a valid cookie returned 401 `Login required`. After BUILD `7qX6PT62-5Vg36BxSPFaH`, the same request is 200 (`count=150`), as are unsigned hex cookies and cookie-only calls. `node scripts/test_session_cookie.mjs`.
- Deployment: Workstation BUILD `7qX6PT62-5Vg36BxSPFaH` on `:3000` / `:3300` (previous `standalone.bak_20260821_*_pre_login_required`). Restarted `gastric-next` and `gastric-next-public` only. Public Aliyun still needs a reader-only swap plus live `auth_server.mjs` prefix update.
- Follow-up: Hard refresh once so localStorage picks up the live token.

## 2026-08-21, Arm-to-box, whole-lesion drag, no keyframe re-seg

- Scope: `apps/gastric_scan_next` simple-video box tools, cursor, keyframe mark, lumen auto-seg.
- Reason: Dragging could start a lesion box without clicking the button. After a mask existed, the next drag still redrew a box and re-ran SAM. Marking a keyframe also auto-segmented. Lumen box had no drag cursor and no auto-seg.
- Key changes: `lesionBoxArmed` — only an armed 「框选病灶」 starts a box; the button lights up as 「正在框选」. After a mask, drag moves the whole lesion (polygon or padded bbox). Mark this frame / Space only stores a keyframe. Boxing lumen uses a dashed-box cursor and auto-segments on release.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`.
- Deployment: none yet. Hard refresh after the next workstation / public Next rebuild.
- Follow-up: Rebuild `:3000` / `:3300` (and public Next if this build is promoted).

## 2026-08-21, Reader tool rail: lesion column first, lumen secondary

- Scope: `apps/gastric_scan_next` simple-video right tool rail and lumen-box hit handling.
- Reason: The rail mixed lesion and lumen tools in one tall stack. Lumen boxing felt unresponsive because leftover/YOLO boxes covering the frame stole the first drag as a move, and the long rail covered the image.
- Key changes: Lesion box is the primary column. Refine tools (handles, +/- points, paint, boundary) appear only after a lesion mask exists. Lumen box stays as a secondary button; detect/paint move under More. Clicking Box lumen starts a fresh draw. Corner grab area is larger. Help copy updated.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`.
- Deployment: none yet. Hard refresh after the next workstation / public Next rebuild.
- Follow-up: Rebuild `:3000` / `:3300` (and public Next if this build is promoted) so doctors see the shorter rail.

## 2026-08-21, Multi-frame mask-shape retrain script (no missing flags)

- Scope: new patient-bag recipe and launcher. Does not change the locked 0.5 mix.
- Reason: Phase-0 used 22-D clinical (11 norms + missing flags), single-frame DualBranch, and mask as RGB channel 4. Need a retrain that drops missing flags, packs K frames, and learns mask silhouette / NRL irregularity as its own stream.
- Key changes: `pipeline/lib/multiframe_maskshape.py`, `pipeline/configs/tstaging_4class_multiframe_maskshape_nomiss_phase0_20260821.yaml`, `scripts/run_multiframe_maskshape_nomiss_20260821.py`. Image DualBranch is Phase-0 RGB, frozen. Mask is 1-ch CNN + NRL aux. Clinical-11 norms only.
- Validation: `--plan` coverage write-up. Training not launched.
- Deployment: none. Do not replace the 0.701 mix until scored on official 425 / 485.
- Follow-up: run `--smoke` then `--train --gpu 1` only after reviewing the plan. Do not `--unfreeze-image`.

## 2026-08-21, Larger mask ConvNeXt-Small and 60-epoch schedule

- Scope: multi-frame mask-shape retrain capacity. Image DualBranch stays frozen.
- Reason: The first mask stream was a 4-layer CNN and 24 epochs. Need more capacity on the silhouette / NRL path.
- Key changes: Mask encoder is `convnext_small.in12k_ft_in1k` at 384, mask repeated to 3ch. `mask_dim` 256, `shape_dim` 64, clinical hidden 128. Epochs 60, early-stop 16, cosine after 3-epoch warmup, lr 3e-5. Image Base still frozen.
- Validation: smoke then train; not a replacement for the locked 0.5 mix until 425 / 485 scores exist.
- Deployment: none.
- Follow-up: Do not `--unfreeze-image`.

## 2026-08-21, From-scratch pack: clean train, complete 425/485

- Scope: stop Phase-0 warm-start; rebuild data; train ImageNet DualBranch + mask stream.
- Reason: Previous job loaded gastric Phase-0. Old train leaked 152 official prospective IDs via `int/prospective`.
- Key changes: `scripts/prepare_multiframe_scratch_20260821.py` writes `pipeline/data/tstaging_4class_multiframe_scratch_20260821/`. Train/val keep `int/2018-2024` only. Eval is official 425 / 485. Model init is ImageNet, no gastric ckpt. K=4, 60 epochs. Ledger: `DETAILS.html` and `audit.json`.
- Validation: prepare gate must PASS before train.
- Deployment: none. Not a replacement for any locked mix until scored.
- Follow-up: train on GPU 1 after gate pass.

## 2026-08-20, Enrich lumen-optional Assist and verify

- Scope: Assist geometry helper, reader/stream gates, `analyze_case.py` contour status, evidence/report copy.
- Reason: After dropping the lumen 422, lesion-only runs still looked incomplete and YOLO bbox proxies were treated as a doctor-drawn lumen.
- Key changes: Shared lesion-only gate. Doctor lumen is box/contour only; YOLO proxy no longer flips `lumen_ready`. Status `contour_ready_lumen_optional`. Evidence cards and the report panel note when lumen was skipped.
- Validation: `pytest pipeline/agent/product/test_research_stage_gate.py` (8 passed). Live `:3000` login `select_local_identity`, no-lesion analyze 422, lesion-only analyze 200 with `lumen_optional` and display T1. `npm run build`.
- Deployment: Workstation BUILD `pnlnVqwWRJ9_KxWCVyQyE` on `:3000` / `:3300` (previous `_UijTqtsS805T00WrbXl3`). Restarted `gastric-next` and `gastric-next-public` only. No Aliyun swap.
- Follow-up: Hard refresh. Wall SDF remains weaker without a doctor lumen.

## 2026-08-20, Assist no longer requires lumen

- Scope: `apps/gastric_scan_next` Assist geometry gate (reader analyze, agent stream, Agent workbench).
- Reason: Doctors asked to run assist with only a lesion contour. Lumen was a hard 422 and blocked the Agent launcher.
- Key changes: Lesion polygon remains required. Lumen box/contour is optional and still used when present. Report layer fallback no longer says to draw the lumen first.
- Validation: `npm run build`, then `curl` `:3000/` and `:3300/api/agent/contract`.
- Deployment: Workstation BUILD `_UijTqtsS805T00WrbXl3` on `:3000` / `:3300` (previous `P3gBvxpXag-hY7cEx5Zug`). Restarted `gastric-next` and `gastric-next-public` only. No Aliyun swap.
- Follow-up: Hard refresh. Wall-layer SDF proxies stay weaker without lumen; that is expected.

## 2026-08-20, GitHub Actions auto-deploy for public Next

- Scope: `.github/workflows/deploy-public-next.yml`, `scripts/deploy_public_next.sh`, `docs/technical/GITHUB_ACTIONS_DEPLOY.md`, `.gitignore` (`secrets/`, reader-only dist dirs).
- Reason: Keep Aliyun public Next in sync with GitHub without manual rsync after each UI change.
- Key changes: Push/manual workflow builds `NEXT_PUBLIC_READER_ONLY=1`, rsyncs atomically to `/var/www/gastric-next`, restarts `gastric-next`. Requires Actions secrets `ALIYUN_SSH_*` (deploy-only key).
- Validation: Script `--help` path and workflow YAML added; live deploy depends on secrets + first Actions run.
- Deployment: Docs only until Secrets are set and workflow is run; does not rotate ops/session secrets.
- Follow-up: Set GitHub Secrets; optional self-hosted runner for LAN `:3000`/`:3300`.

## 2026-08-20, Public Next rebuild: one-login inherit + ops bridge

- Scope: `apps/gastric_scan_next` session cookie secret file support; ops GET ingest auth; `proxy.ts` ingest bypass; Aliyun `/var/www/gastric-next` READER_ONLY swap; workstation `:3000`/`:3300`; shared `GASTRIC_OPS_INGEST_SECRET`; edge `READER_SESSION_DAYS=180`.
- Reason: Live public UI was still `ktn9E` without edge-session inherit or mobile 401 grace. Ops GET through the tunnel always 401'd: ingest auth was only on POST, the secret was unset, and middleware blocked ingest before the route.
- Key changes: Deployed READER_ONLY BUILD `iCTTDbk6dWpL5dmS7leqd` on Aliyun (previous `*.bak_20260820_1623`). Workstation BUILD `P3gBvxpXag-hY7cEx5Zug` on `:3000`/`:3300`. `doctorSessionSecret()` reads `READER_SESSION_SECRET_FILE`. Ops GET accepts signed ingest. Proxy allows ops/history/ops-stats when `x-ops-ingest` + account headers are present. Same ops secret on Aliyun Next and workstation `:3300`.
- Validation: Edge login → account inherit `authenticated=true`; `/api/patients` 200; `/api/reader/operations` 200 `via=ingest`; cases 200; `/clinical/task1.html` 200.
- Deployment: Aliyun atomic swap + `gastric-next` / `gastric-reader` restart; workstation user services restarted. Hard refresh public browsers.
- Follow-up: Keep ops secret only in systemd drop-ins; rotate if hosts are rebuilt from scratch.

## 2026-08-20, Fix public login loop on Aliyun root workbench

- Scope: Aliyun `auth_server.mjs`, `workbench_login.html` (live + `server/aliyun_live/` snapshot).
- Reason: After password login, unauthenticated `/_next` and `/api/*` were 302'd to `workbench_login.html`, so the app bounced back to the login page. Doctor token was also not written to localStorage.
- Key changes: Public proxy for `/_next` and bootstrap APIs; other APIs return JSON 401 instead of login HTML; login page stores `gastric_doctor_session_token` and ignores `next=/api/...`.
- Validation: `/_next/static/chunks/*.js` 200 without cookie; `/api/reader/account` JSON without cookie; dual-login e2e keeps `GET /` on Next HTML and `authenticated:true`.
- Deployment: Live on `47.106.33.102`; `systemctl restart gastric-reader`. Hard refresh the login page.
- Follow-up: Redeploy newer Next READER_ONLY with GET session inherit + mobile 401 grace.

## 2026-08-20, Fix mobile login loop

- Scope: `apps/gastric_scan_next` doctor session client, cookie flags, LoginGate stay-signed-in.
- Reason: Phones bounced back to the identity picker after picking an account. Any 401 (ops, viewing-trace, patients) cleared the new session; LAN HTTP cookies could be marked Secure and dropped.
- Key changes: Keep the session token in memory if localStorage is blocked. Do not wipe the account on a flaky refresh. 401s must re-check `/api/reader/account` before logout. Ignore ops/trace 401s and a short post-login grace window. LAN cookies are never Secure. Phone header title is no longer a full-page Home tap.
- Validation: `npm run build`, then `curl` `:3000/` and `:3300/api/agent/contract`.
- Deployment: Workstation BUILD `irw7sJVF-Bagos_wnrnDL` on `:3000` / `:3300` (previous `RjYt3Ns88S39uC-gHF0et`). Restarted `gastric-next` and `gastric-next-public` only. No Aliyun swap.
- Follow-up: Hard refresh on the phone, pick the account once.

## 2026-08-20, Mobile workbench usage polish

- Scope: `apps/gastric_scan_next` phone chrome only. Desktop 3-column layout is unchanged.
- Reason: First mobile drawer still hid the case name, blocked the cine with helper chips, and made LAN account picking / video scrub awkward on a phone.
- Key changes: Header and bottom Viewer tab show the current case. LAN identity list is searchable. Overlay assist / write-back cards stay hidden below 768px. Cine bar gets larger play, step, mark, and slider thumbs; helper copy and status chips hide on phone. Landscape short screens hide the top bar. Sheets use momentum scroll.
- Validation: `npm run build`, then `curl` `:3000/` and `:3300/api/agent/contract`. Desktop selectors (`md+`, `workbench-desktop-toggle`) were not restyled.
- Deployment: Workstation BUILD `RjYt3Ns88S39uC-gHF0et` on `:3000` / `:3300` (previous `W48EqNdjceTftyeDMTBGd`). Restarted `gastric-next` and `gastric-next-public` only. No Aliyun swap.
- Follow-up: Hard refresh on phone. Contour edit remains better on desktop.

## 2026-08-20, Current TIME architecture HTML and frame-agg compare

- Scope: `pipeline/experiments/reports/time_loop_20260820/architecture.html`; `scripts/run_time_frame_agg_20260820.py`.
- Reason: The kept system is two frozen experts plus a pre-registered 0.5 probability mix, not DualBranch TIME training. Need one HTML that states that, and a locked frame-aggregation compare.
- Key changes: Rewrote the architecture page around the kept mix (prospective 0.701). Compared DualBranch frame mean / inv-entropy / low-H half / max-conf, each mixed 0.5 with TabPFN. Mean stays the default. DualBranch-mean mix is 0.704 / 0.532 and does not replace the linear mix 0.701 / 0.538.
- Validation: Frame script scored official 425 / 485 IDs against existing DualBranch frame CSVs. No prospective threshold search.
- Deployment: Offline report. Open `architecture.html` locally.
- Follow-up: Frame-content 12x12 invasion on the frames the mix already uses. Do not resweep entropy aggregation.

## 2026-08-20, TIME T3/T4 geometry specialist (negative)

- Scope: `scripts/run_time_t34_geometry_20260820.py`, report `pipeline/experiments/reports/time_t34_geometry_20260820/`.
- Reason: Remaining two-expert unique wins sit on T3 vs T4+. Need a specialist that does not use leaked 512-D tokens and does not val-lock.
- Key changes: Trained logistic T3/T4 on 701 honest train patients (Phase-0 train minus all eval IDs) using mask morphology plus clinical size, optional wall covariates. Applied only when frozen image and TabPFN disagree on T3/T4. Added a train-locked one-way T4-to-T3 thickness rule.
- Validation: Prospective mix 0.701 vs geom 0.682 vs oneway 0.682. Disagreement subset n=95: mix 0.516, specialist 0.45-0.47. External size-only 0.551 vs mix 0.538; do not lock on that.
- Deployment: Offline TIME experiment only. Keep pre-registered 0.5 mix as the baseline.
- Follow-up: Frame-level aggregation or 12x12 invasion pooling. Do not train another patient-median T3/T4 table.

## 2026-08-20, TIME training path: stop DualBranch unfreeze

- Scope: TIME-DAFT DualBranch score; `scripts/run_time_entropy_router_20260820.py`; `pipeline/experiments/reports/time_loop_20260820/ANALYSIS.md`.
- Reason: Identity-start DAFT DualBranch washed the gastric image encoder (prospective 0.579 vs frozen image 0.687) and NaN-ed after unfreeze. Need a locked exploration path that does not train another fusion.
- Key changes: Recorded DAFT 0.579 / 0.501. Ran pre-registered 0.5 mix, entropy mix, uncertain switch, and train-only TabPFN-trust on the official 425 / 485 split. Equal mix remains 0.701 / 0.538. Entropy family stays below mix and catches only 5 of 61 TabPFN-only wins. Next train is a T3 vs T4+ geometry specialist, applied only when both experts land on {T3, T4+}.
- Validation: Router script scored image linear 0.687 and TabPFN 0.588 on n=425; mix 0.701. No prospective threshold search.
- Deployment: Offline TIME experiment only. Do not launch another DualBranch TIME unfreeze.
- Follow-up: T3/T4 geometry specialist on train T3/T4 labels; do not val-lock.

## 2026-08-20, Harden lesion auto-segmentation quality

- Scope: `apps/gastric_scan_next/lib/reader/doctor-keyframe-preseg.ts`, `InteractiveSegPanel` box / keyframe / find-lesion paths.
- Reason: Keyframe pre-seg captured at 768 JPEG and only SAM3.1; box release in simple video mode used a single weak path, so masks often washed or missed the box.
- Key changes: Capture at 1024 / JPEG 0.92. Cascade SAM2 interactive → SAM3.1 → static / DINOv3 with area and box-agreement scoring. Simple-mode box auto-seg tries the same cascade before lesion-endpoint fallback. Reject oversized or box-mismatched masks.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. Manual: mark keyframe, confirm contour; redraw box and confirm auto-seg follows the box.
- Deployment: Rebuild workstation `:3000` / `:3300` (and Aliyun Next if public readers use auto-seg).
- Follow-up: Tune area / IoU thresholds on real reader cases if false rejects appear.

## 2026-08-20, Public root is workbench; clinical study under /clinical/

- Scope: Aliyun `47.106.33.102` `auth_server.mjs`, `workbench_login.html`, `gastric-next` session inherit env. Repo snapshot under `docs/clinical_validation/reader_study_v150/server/aliyun_live/`.
- Reason: Public `/` served the old task1 阅片包 and returned 401 JSON; doctors could not reach the workbench. Edge login also did not mint a Next doctor session on the live READER_ONLY build.
- Key changes: `/` and `/workbench/` proxy Next. Legacy HTML moved to `/clinical/` with redirects from `/task1.html` etc. Login page does edge `/api/login` then Next `password_login`. Next gets `READER_USERS_FILE` / `READER_SESSION_SECRET_FILE` pointing at gastric-reader. `/api/reader/account` POST allowed without edge cookie for bootstrap.
- Validation: `curl -sI http://47.106.33.102/` → 302 login; `/task1.html` → `/clinical/task1.html` 200; `/clinical/reader_core.js` 200; password_login reaches Next (`invalid password` for bad secret).
- Deployment: Live on Aliyun. Backups `auth_server.mjs.bak_20260820_160430`, `workbench_login.html.bak_*`. Restarted `gastric-reader` and `gastric-next`.
- Follow-up: Rebuild/rsync a newer Next READER_ONLY bundle with GET inherit; hard-refresh after login.

## 2026-08-20, TIME DualBranch architecture HTML

- Scope: `pipeline/experiments/reports/time_loop_20260820/architecture.html` and `architecture_diagram.html`.
- Reason: Need a repo-local figure of our TIME DualBranch (512-D Dual ConvNeXt + frozen 192-D TabPFN-2.5 + Cat/Sum/Max/1D-DAFT), not a recap of the paper ResNet figure.
- Key changes: Side-nav HTML with tensor sizes, fusion equations, freeze schedule, and an unused-block list. 16:9 grayscale SVG for slides.
- Validation: Checked against `DualBranchClassifier._time_fuse` and the DAFT Phase-0 yaml (`time_tab_dim: 192`, `clinical_dim: 0`, `linear_head: true`).
- Deployment: Offline report only. Open the HTML locally.
- Follow-up: TIME-DAFT DualBranch was still training when this page was written; numbers stay in `ANALYSIS.md`.

## 2026-08-20, Full account operation log and admin doctor/case stats

- Scope: `apps/gastric_scan_next` auth, ops JSONL, history timeline, `/admin/ops`, reader simple-mode box auto-segment and more tools.
- Reason: LAN could use the workbench anonymously; public sometimes needed two logins; box-select on `reader_v150` video did not auto-segment; ops were split across audit/history/viewing-trace without a doctor/case admin view.
- Key changes: LAN identity picker (no password); public remains one account+password form and can inherit edge `reader_session`. Empty `accountId` auth bypass removed. Unified `doctor_operation_events*.jsonl` under runtime with `/api/reader/operations` and admin `/api/admin/ops-stats` (admin only). Public edge can forward ops via `NEXT_AGENT_UPSTREAM` + `GASTRIC_OPS_INGEST_SECRET`. History detail merges audit+ops into a human-readable timeline. Simple video mode auto-runs SAM after lesion box; tool rail adds +/- points, contour edit, refine, lumen detect, polygon.
- Validation: Static review of auth/ops routes and InteractiveSegPanel box path. Run `python3 scripts/check_repo_root.py` and `python3 scripts/verify_repo_paths.py` after deploy. Manual: LAN pick identity, box lesion, open History and `/admin/ops` as admin.
- Deployment: Rebuild workstation `:3000` and `:3300`; atomic Aliyun `/var/www/gastric-next` with same ops secret and tunnel `18768→3300`. Set `GASTRIC_OPS_INGEST_SECRET` on both sides for public ingest.
- Follow-up: Optional pending-queue drain job on workstation; deeper annotate grid-click instrumentation.

## 2026-08-20, Deploy mobile workbench; keep desktop 3-column

- Scope: `apps/gastric_scan_next` mobile chrome; `lib/ops/store.ts` type fix so production build can finish.
- Reason: Phone/LAN access needed a real mobile layout. Desktop 3-column must stay as-is. Previous Next build failed on `access_channel` typing.
- Key changes: Desktop (`md`+) keeps the original sidebars, rail, header, and page padding. Below 768px: Cases / Viewer / Evidence sheets, bottom nav, Done bars, horizontal tool rail, full-screen LAN identity picker. Ops stats now type `access_channel` as `lan` / `public` / `mixed`.
- Validation: `npm run build` succeeded. `curl` `:3000/` and `:3300/api/agent/contract` both 200 after restart.
- Deployment: Workstation BUILD `W48EqNdjceTftyeDMTBGd` on `:3000` / `:3300` (previous `o0reg1WfuxUoVOGanQZOQ`). Restarted `gastric-next` and `gastric-next-public` only. No Aliyun swap.
- Follow-up: Hard refresh on phone. Precise contour work is still better on desktop.

## 2026-08-20, Score aborted binary retrain (no Fujian Provincial)

- Scope: 101708 job stopped at epoch 270; scored best EMA (epoch 175) on the current pack.
- Reason: Cursor wrapper aborted the 500-epoch launch. `best_model.pth` was already saved. Need the unseen-center number without 省立.
- Key changes: Wrote missing `config.json`. `evaluate_experiment.py --eval-mode all` then official scorer. Official `test_external` patient metrics at 0.5: AUC 0.733, Acc 0.629, Sens 0.438, Spec 0.779, n=404. Frame AUC 0.726. Prospective patient Acc/AUC 1.0 is still seen-center.
- Validation: Eval used 1,440 / 404 unseen rows; no 省立. Manifest refresh failed on a relative path; predictions were already written.
- Deployment: Run dir `.../binary_multicenter_joint_unseen_20260820_20260820_101708`. Report `pipeline/experiments/reports/binary_multicenter_joint_unseen_20260820/SUMMARY.md`. Do not promote.
- Follow-up: Failures still concentrate on Tumor / Friendship / Foshan. Do not restart 500 epochs unless a new recipe is ready.

## 2026-08-20, Train-OOF TIME expert gate

- Scope: `scripts/run_time_gate_experts_20260820.py`, report `pipeline/experiments/reports/time_gate_experts_20260820/`.
- Reason: Frozen TIME Cat/DAFT copies the image linear head. Val n=140 cannot lock fusion (image T2 recall 0). TabPFN class probabilities are the external expert; image is the prospective expert.
- Key changes: 5-fold OOF image linear on frozen 512-D. Lock soft-mix, confidence route, and E_T-confidence gate on train OOF only. Score prospective and external once. DualBranch TIME-DAFT keeps training in parallel.
- Validation: Train-OOF image linear leaked (train ACC 0.94) and used a 266-patient prospective subset. Discard as a lock. Honest 425-patient analysis is in `pipeline/experiments/reports/time_loop_20260820/ANALYSIS.md`.
- Deployment: Offline TIME experiment only.
- Follow-up: Two-expert oracle is 0.831 prospective / 0.691 external. Pre-registered equal mix is 0.701 / 0.538. Finish TIME-DAFT DualBranch.

## 2026-08-20, TIME-DAFT DualBranch with gastric image encoder

- Scope: DualBranch TIME fusion (Cat/Sum/Max/DAFT), `pipeline/configs/tstaging_4class_time_daft_phase0_20260820.yaml`, launcher `--fusion daft`.
- Reason: ImageNet TIME-Cat collapsed to prospective ACC 0.494. TIME needs a domain image encoder and a fusion that can start as identity on E_I, then let TabPFN modulate it.
- Key changes: DAFT/Sum/Max project both tokens to 512-D. DAFT affine and tabular projection start at zero. Load gastric-pretrained DualBranch backbone plus fusion. Freeze those, train TIME plus linear head with weighted CE, then unfreeze the image encoder after 8 epochs.
- Validation: Frozen 512 plus official 192-D linear sweep: prospective image 0.687, TIME-Cat 0.682, TIME-DAFT 0.675. External TabPFN-embed linear 0.526 beats image 0.485. DualBranch TIME-DAFT is training on GPU 1 (epoch 1 val PatAcc 0.504 after loading gastric image weights).
- Deployment: Offline TIME experiment only.
- Follow-up: Score prospective and external after the DAFT run.

## 2026-08-20, TIME-Cat as a standalone paper run

- Scope: DualBranch TIME path, `pipeline/configs/tstaging_4class_time_cat_phase0_20260820.yaml`, `scripts/run_time_cat_dualbranch_20260820.py`.
- Reason: User asked to drop acc_boost2 as a constraint. The previous TIME-Cat job warm-started Phase-0 and concatenated 22-d clinical plus 192-D E_T.
- Key changes: Clinical tensor is TabPFN-2.5 E_T only (`clinical_dim=0`, `time_tab_dim=192`). No Phase-0 checkpoint. Fusion is TIME-Cat. Head is linear softmax. Loss is CE. Image starts from ImageNet DualBranch.
- Validation: Early-stop epoch 24, best val PatAcc 0.571. Prospective n=425 ACC 0.494 / bacc 0.353. External n=485 ACC 0.427 / bacc 0.317. Far from target 0.80. T2 recall on prospective is 2.9%.
- Deployment: Offline TIME experiment only.
- Follow-up: ImageNet DualBranch plus a linear head is too weak as the TIME vision encoder. Next options are a stronger gastric-pretrained image token, or TIME-Sum / DAFT on the same official 192-D embeddings.

## 2026-08-20, Harden official TIME-Cat DualBranch scripts

- Scope: `scripts/run_time_cat_dualbranch_20260820.py`, `pipeline/lib/models.py` DualBranch TIME aux prefix, `pipeline/run_experiment.py` weight pad.
- Reason: First TIME-Cat warm-start padded the main head (576 to 768) but skipped aux first layers because both in/out changed. DataFrame column insert also fragmented the 192-D dump.
- Key changes: Aux heads read the Phase-0 576-D prefix only. Pad logic can grow both axes. Launcher writes embeddings with `pd.concat`, saves npz, fills missing E_T with 0, puts runtime YAML in the data pack, and can `--score-external` / `--write-report` / `--reuse-embeddings`.
- Validation: Current freeze-head run is still in progress on GPU 1; do not promote.
- Deployment: Offline. Agent `acc_boost2` stays default.
- Follow-up: After the running job ends, score prospective/external and compare with Phase-0 0.678 and the 0.704 mix.

## 2026-08-20, Implement TIME paper network: TabPFN embeddings + frozen image

- Scope: `scripts/run_time_tabpfn_engine_20260820.py`; report `pipeline/experiments/reports/time_tabpfn_engine_20260820/`. Paper: arXiv:2506.00813.
- Reason: Prior runs used TabPFN 4-d class probabilities. TIME uses frozen TabPFN encoder embeddings (192-D), frozen vision tokens, Cat/Sum/Max/DAFT, and a linear head.
- Key changes: Clinical-11 with NaN for missing fields. TabPFN-2.5 `get_embeddings`, train OOF query tokens. Image is frozen Phase-0 DualBranch 512-D. Val picks fusion; prosp/ext scored once.
- Validation: Val locked TIME-Max. Prospective n=425 ACC 0.668 / bacc 0.580, below Phase-0 DualBranch 0.678 and the 0.704 mix. TIME-Cat 0.678. Image-only linear 0.680. External n=485 locked 0.487; TIME-Sum 0.499. Not 0.80. Do not promote.
- Deployment: Offline. Agent `acc_boost2` stays default.
- Follow-up: Embedding fusion did not beat DualBranch logits. The 0.704 mix remains the best number in this series.

## 2026-08-20, Val-locked DualBranch + TabPFN gate and T3/T4 specialist

- Scope: `scripts/run_tabpfn25_gated_t34_20260820.py`; Phase-0 val inference `eval/phase0_val/`; report `pipeline/experiments/reports/tabpfn25_gated_t34_20260820/`.
- Reason: Scalar mix 0.704 was selected on prospective labels. Need a val-locked gate plus a clinical T3/T4 specialist. No backbone retrain, no 512-D into TabPFN.
- Key changes: Score Phase-0 DualBranch on val (n=140). Tune mix/entropy gate, then T3/T4 TabPFN specialist, then T1 override, all on val ACC. Lock and score prospective/external once.
- Validation: Val DualBranch ACC 0.471, so lock picked `w_tabpfn=0.7` plus TabPFN T3/T4 soft-margin 0.10. Prospective n=425 ACC 0.668 / bacc 0.597, worse than Phase-0 0.678 and the 0.704 mix. External n=456 ACC 0.561 / bacc 0.511, near the old w=0.7 mix. Not 0.80. Do not promote.
- Deployment: Offline. Agent `acc_boost2` stays default.
- Follow-up: Val is not exchangeable with prospective for fusion weights. Either-expert oracle is still 0.821, so the remaining gap is expert selection, not a 0.70 ceiling.

## 2026-08-20, Push toward patient ACC 0.80: Lauren TabPFN + frozen DualBranch fusion

- Scope: `scripts/run_tabpfn25_fusion_acc80_20260820.py`, `scripts/run_maskroi_clin11_tabpfn_freeze_20260820.py`, config `pipeline/configs/tstaging_4class_maskroi_clin11_tabpfn_freeze_20260820.yaml`.
- Reason: Fine-tuning destroyed Phase-0 image (early-stop epoch 2). A 0.6/0.4 mix of frozen acc_boost2 and TabPFN clinical-10 already reached prospective ACC 0.706. External TabPFN alone 0.561 beats DualBranch 0.464. User asked to continue toward 0.80.
- Key changes: Lauren back into TabPFN (clinical-11). ResidualMLP on frozen 512-D + clinical-11 + TabPFN 4-d. DualBranch retrain keeps backbone frozen for all 40 epochs; clinical is Phase-0 11-field encoding plus TabPFN 4-d.
- Validation: Fusion mix prosp ACC 0.704. Frozen-head DualBranch early-stop epoch 21; prosp n=425 ACC 0.649 / bacc 0.596; ext n=485 ACC 0.445 / bacc 0.347. Worse than Phase-0 prosp 0.678 and the 0.704 mix. Not 0.80. Do not promote.
- Deployment: Offline. Agent `acc_boost2` stays default.
- Follow-up: Read mix grids and MLP / freeze-head scores. Adjacent errors are mostly T3/T4 and T1 overstage.

## 2026-08-20, Retrain DualBranch TIME-style: image + TabPFN-2.5 clinical token

- Scope: `pipeline/configs/tstaging_4class_maskroi_tabpfnclin_phase0_20260820.yaml`, `scripts/run_maskroi_tabpfnclin_retrain_20260820.py`, pack `pipeline/data/tstaging_4class_maskroi_tabpfnclin_phase0_20260820/`.
- Reason: Dumping 512-D DualBranch tokens into TabPFN is the wrong modality split (TabPFN-2.5 / TIME). The raw-512 CPU job was stopped. Clinical-10 DualBranch already lost to Phase-0.
- Key changes: TabPFN-2.5 sees only clinical-10. Train uses 5-fold patient OOF 4-d probabilities. DualBranch warm-starts Phase-0 image/fusion; new 4-d clinical MLP. Same mask+ROI image contract.
- Validation: OOF pack complete. Early-stop epoch 14. Prospective n=425 patient ACC 0.666 / bacc 0.605 vs Phase-0 0.678 / 0.618. External n=485 patient ACC 0.458 / bacc 0.355 vs Phase-0 0.443 / 0.347 (n=456). Do not promote.
- Deployment: Offline. Agent `acc_boost2` stays default.
- Follow-up: Read Phase-0 external patient ACC/bacc.

## 2026-08-20, Diagnose TabPFN-2.5 vs ExtraTrees collapse; rerun on raw 512-D

- Scope: diagnosis `pipeline/experiments/reports/tabpfn25_maskroi_clin10_20260820/DIAGNOSIS.md`; script `scripts/run_tabpfn25_raw512_optimize_20260820.py`.
- Reason: Prospective ACC 0.673 vs 0.673 was not two models tying. Label agreement 0.932 and T2 probability correlation 0.951. Train PCA PC0 already isolates T2 (mean -36). TabPFN-2.5 never saw the raw 512-D tokens it is designed for (up to 2,000 features).
- Key changes: Drop PCA-16. Fit default and Real-TabPFN-2.5 on raw 512 + clinical-10, with categorical indices. Same-table ExtraTrees and L2 logistic readout. DualBranch MLP kept as reference.
- Validation: Running on CPU so GPU 0/1 jobs stay up. Do not promote until prospective / external scores and head-agreement are read.
- Deployment: Offline. Agent `acc_boost2` stays default.
- Follow-up: If TabPFN and ExtraTrees still agree above ~0.90 on 512-D, the frozen embedding is already linearly saturated and the head is not the bottleneck.

## 2026-08-20, TabPFN-2.5 head on mask+ROI image + clinical-10

- Scope: `scripts/run_tabpfn25_maskroi_clin10_20260820.py`; report `pipeline/experiments/reports/tabpfn25_maskroi_clin10_20260820/`. Paper: arXiv:2511.08667.
- Reason: User replaced Google TabFM with Prior Labs TabPFN-2.5 on the narrow table (frozen DualBranch image PCA + 10 clinical norms; no Lauren, missing flags, doctor scores, contour, or wall).
- Key changes: Pin TabPFN-2.5 via `create_default_for_version(V2_5)`. Fit all train patients as ICL context. ExtraTrees and frozen DualBranch MLP kept as same-row references. Weights cached from public HF `Prior-Labs/tabpfn_2_5`. License is research/internal evaluation only.
- Validation: Prospective n=425 TabPFN-2.5 ACC 0.673 / bacc 0.602 vs DualBranch 0.678 / 0.618 and ExtraTrees 0.673 / 0.605. External TabPFN-2.5 ACC 0.489 vs ExtraTrees 0.509. T2 recall stays 0.06 on external. Do not promote.
- Deployment: Offline report. Agent `acc_boost2` stays default.
- Follow-up: After DualBranch clin10 retrain ends, optionally swap its image tokens into this head.

## 2026-08-20, DualBranch retrain: mask+ROI image, clinical-10, no Lauren

- Scope: `pipeline/configs/tstaging_4class_maskroi_clin10_phase0_20260820.yaml`, `scripts/run_maskroi_clin10_retrain_20260820.py`, note `pipeline/experiments/reports/maskroi_clin10_phase0_20260820/INPUT.md`.
- Reason: TabFM full-table (62 cols) was the wrong input. User asked to drop extra scores/contour/wall, drop Lauren and missing flags, and retrain on mask + matching ROI with original-image fusion as the reference branch.
- Key changes: DualBranch mask4ch global + ROI local, cross-attention. Clinical is 10 norms only. Warm-start Phase-0 acc_boost2; new 10-d clinical MLP. Backbone frozen 8 epochs, then low-LR unfreeze.
- Validation: Train finished, early stop epoch 33. Prospective n=425 patient ACC 0.654 / bacc 0.590 vs Phase-0 DualBranch 0.678 / 0.618. External n=485 patient ACC 0.419 / bacc 0.330 vs Phase-0 0.443 / 0.347 (n=456). Eval wrapper exited 1 after scores were written (relative-path manifest). Do not promote.
- Deployment: Offline retrain. Agent `acc_boost2` stays default.
- Follow-up: Read external patient ACC/bacc. Do not swap TabPFN onto these weaker tokens unless external also improves.

## 2026-08-20, TabFM full-feature retest (image + clinical-11 + scores)

- Scope: `scripts/run_tabfm_full_feature_retest_20260820.py`; report `pipeline/experiments/reports/tabfm_full_feature_retest_20260820/`; figures `results/visualizations/tstage/tabfm_full_feature_retest_20260820/`.
- Reason: Earlier TabFM heads omitted Phase-0 clinical-11 or omitted image columns, so they were not a fair concat comparison. User asked to retest with the full table.
- Key changes: Frozen acc_boost2 PCA-16 plus clinical-11 (with missing flags), doctor scores, contour, and wall. Same-table ExtraTrees / HistGB / ResidualMLP. DualBranch MLP kept as frozen reference. TabFM ICL, 80/class context, GPU 1.
- Validation: Prospective n=425 TabFM full ACC 0.649 / bacc 0.596 vs DualBranch 0.678 / 0.618 and ExtraTrees image+clinical 0.689 / 0.614. External TabFM full ACC 0.472 vs ExtraTrees 0.522. Permutation: image PCA 0.122, clinical 0.008. Encoder not updated.
- Deployment: Offline report only. Do not replace Agent `acc_boost2`.
- Follow-up: No further TabFM-as-main-head runs unless the image tokens themselves change.

## 2026-08-20, Retrain binary ConvNeXt-B without Fujian Provincial

- Scope: same YAML and launcher; new GPU 0 job on the rebuilt pack.
- Reason: `test_external` no longer includes 省立 (24 patients / 216 malignant frames). The 011854 score (n=428) is not the current claim.
- Key changes: Relaunch ConvNeXt-B 384, batch 32, 500 epochs, early stop 501. Train/val unchanged. Unseen test is 1,440 frames / 404 patients (792 benign / 648 malignant).
- Validation: `--dry-run` passed; leak 0; no 省立 in any split; images on disk.
- Deployment: New tree `.../binary_multicenter_joint_unseen_20260820_20260820_101708`. Old 011854 dir kept. Launch: `python3 scripts/run_binary_multicenter_joint_unseen_20260820.py --gpu 0`.
- Follow-up: After the job ends, official score is unseen-center patient AUC at 0.5 on the new `test_external`. Do not promote on val AUC.

## 2026-08-20, Drop Fujian Provincial from modeling catalogs

- Scope: binary and T-staging CSVs under `dataset/task_datasets/`; binary trainer pack; builders.
- Reason: User asked to remove 省立 from the current modeling tables. That center is malignant-only (24 patients / 216 frames) and was only in `test_external`.
- Key changes: `EXCLUDE_CENTERS` in `build_binary_multicenter_joint_unseen.py`; `T_EXCLUDE_SOURCES` in `build_task_datasets.py`. Rebuild overwrote catalogs. Disk folder `dataset/external/福建省立医院` and the 20260531 T-staging product pack were not deleted.
- Validation: Rebuild exit 0. No 省立 rows in current splits. Binary leak 0. `audit_task_datasets.py` pass. Binary unseen now 1,440 frames / 404 patients (792 benign / 648 malignant). T-staging `test_external` 2,242 frames / 461 patients.
- Deployment: Same contract name `binary_multicenter_joint_unseen_20260820`. Old 011854 unseen score (n=428) includes 省立 and is not comparable without a re-score.
- Follow-up: Re-score the existing binary run on the new `test_external` if that number is still the claim. Re-run `join_reader_v150_to_task_datasets.py` only if reader-join split labels must match.

## 2026-08-20, Finish 500-epoch binary ConvNeXt-B; score unseen centers

- Scope: 011854 run completed; official scorer wrote `center_patient_scores.json`; registry set to done; short SUMMARY written.
- Reason: Need the unseen-center claim, not seen-center val AUC.
- Key changes: Best EMA at epoch 75. Official `test_external` patient metrics at 0.5: AUC 0.675, Acc 0.584, Sens 0.351, Spec 0.792, n=428. Frame AUC 0.758. Prospective patient Acc/AUC 1.0 is seen-center time holdout only. Failures concentrate on Tumor, Beijing Friendship, and Foshan malignant cases.
- Validation: Launcher exit 0. Wall clock 01:18-09:13 (about 7 h 55 min). Leak guard passed at start. Do not promote.
- Deployment: Run dir `.../binary_multicenter_joint_unseen_20260820_20260820_011854`. Report `pipeline/experiments/reports/binary_multicenter_joint_unseen_20260820/SUMMARY.md`.
- Follow-up: Domain-shift analysis on Tumor / Friendship / Foshan before any next train.

## 2026-08-20, Restart binary train for a >=8 hour wall clock

- Scope: binary YAML and a new GPU 0 job. Short 80-epoch run stopped.
- Reason: At ~70 s/epoch, 80 epochs plus early stop 16 finishes in well under 8 h. Val AUC already 0.97 by epoch 2, so patience 16 would stop around 20-30 min.
- Key changes: 500 epochs, warmup 15, early_stop 501 (effectively off). Regularizers unchanged. Best EMA ckpt still saved each improvement. Expected wall clock about 9-11 h.
- Validation: Stopped 011448. Relaunched on GPU 0. Log shows `Training: 500 epochs`, warmup 15, leak_guard pass. Epoch 1 started without OOM.
- Deployment: New tree `.../binary_multicenter_joint_unseen_20260820_20260820_011854`. Old 011448 dir kept.
- Follow-up: Score unseen centers after the 500-epoch job ends. Do not promote on val AUC.

## 2026-08-20, Start long ConvNeXt-B 384 binary train on one 4090

- Scope: binary train YAML and launcher; one GPU job.
- Reason: ConvNeXt-S 224 / batch 48 underused a 24 GB 4090. User asked for GPU-matched model scale, many epochs, and overfit control.
- Key changes: `convnext_base.fb_in22k_ft_in1k_384`, 384 px, batch 32, 80 epochs, early stop 16 on val AUC. Regularizers: dropout 0.5, weight decay 0.05, mixup 0.2, label smooth 0.1, EMA, cosine + 4-epoch warmup. Val is still seen-center, so unseen `test_external` remains the claim.
- Validation: `--dry-run` before launch. Watch first steps for OOM; drop batch to 16 if needed.
- Deployment: `python3 scripts/run_binary_multicenter_joint_unseen_20260820.py --gpu 0`
- Follow-up: Review unseen-center patient AUC. Do not promote on val AUC alone.

## 2026-08-20, Merge multi-frame patient ID variants in binary pack

- Scope: `build_binary_multicenter_joint_unseen.py` raw-id normalize; rebuilt CSVs and inventory numbers.
- Reason: Multi-frame stills of one person were counted as two patients when the source id had a trailing dash/underscore, `.jpg`, or a letter series (`1561` vs `1561-`, `ptyz340.jpg`, `ptyz429b`).
- Key changes: Normalize raw ids before `center_id::raw`. Tumor unseen patients 161 to 150. Whole-person split assignment kept (ptyz429 all 19 frames now in prospective).
- Validation: Inflammation 1,692 / gastritis 2,746 frames still match source tables. Audit patient and path leak 0. Unique patients 3,249.
- Deployment: Modeling tables and trainer pack overwritten. No GPU run.
- Follow-up: Train with the updated pack.

## 2026-08-20, Binary multicenter training scripts sized to the new pack

- Scope: ConvNeXt-S train launcher, center-level scorer, YAML, ImageDataset `patient_id` for val patient metrics. No training run in this change.
- Reason: The new pack has 1,862 train patients and a 2:1 malignant/benign patient ratio. Batch, epoch length, and early stop need to match PatientSampler K=5 (about 12,420 frames / 259 steps per epoch).
- Key changes: `scripts/run_binary_multicenter_joint_unseen_20260820.py`, `scripts/score_binary_multicenter_unseen.py`, `pipeline/scripts/run_binary_multicenter_joint_unseen_20260820.sh`. Config: batch 48, 30 epochs, early stop 8, leak guard on both holdouts. Official score is patient-level AUC at 0.5 on `test_external`.
- Validation: `--dry-run` preflight (images on disk, patient leak 0). No GPU job started.
- Deployment: Launch with `--gpu 0` or `1`. Two RTX 4090 D are on the machine.
- Follow-up: Run the train job. Do not promote until unseen-center patient AUC and per-center tables are reviewed.

## 2026-08-20, Binary split: multi-center joint train, unseen-center test

- Scope: benign/malignant modeling tables, builder, trainer config. Images not moved.
- Reason: The 20260531 screened binary split reused T-staging train (Putian and tumor already in train) and leaked 151 prospective plus 41 Putian patients into test. That table cannot support an unseen-center claim.
- Key changes: New contract `binary_multicenter_joint_unseen_20260820`. Train/val = Xiehe 2018-2024 + Putian College + CNNC 504, patient-level 85/15. `test_external` = remaining hospitals only. Patient keys are `center_id::raw_id` so Putian gastritis and inflammation `ptyz*` IDs stay together. Duplicate leaked image paths dropped. Old CSVs copied to `splits_screened_20260531/`.
- Validation: Builder rejects patient, center, and image-path leaks. `audit_task_datasets.py` reports binary leak 0 / 0 / 0. Images all on disk.
- Deployment: Catalog `dataset/task_datasets/binary_benign_malignant/splits/`; pack `pipeline/data/binary_multicenter_joint_unseen_20260820/`; config `pipeline/configs/binary_multicenter_joint_unseen_20260820.yaml`. No training run in this change.
- Follow-up: Train ConvNeXt-S on the new pack. Re-run `join_reader_v150_to_task_datasets.py` if reader-join split labels must match the new contract.

## 2026-08-19, Recover original public sidecars, label roles, redeploy

- Scope: reader v150 clinical sidecar on public HTML, public Next, and local SSOT; `origin_snapshots/`; sidecar builder header.
- Reason: Round-1 public pack already had the 150 videos. The live clinical files were the old ones (HTML 27 matched, Next 95 matched, all BM unmatched on Next).
- Key changes: Download and keep the live originals. Stamp `deployment.role` (`public_html` / `public_next` / `local_ssot`). Upload the 148-matched rebuild. Leave `task1.html` blinded. Keep server-side `.bak` copies. Write a case-level public/local status CSV without hospital ids.
- Validation: Live HTML sidecar reports 148 matched, 1 id_only, 1 unmatched. Public Next service restarted and is active. Local snapshots match the uploaded bytes.
- Deployment: Public HTML `demo_assets/reader_v150_clinical.js` and public Next `data/reader_v150_clinical.json` updated. Agent cache query set to `20260819-clinical-sidecar`. Full pack rsync was not run.
- Follow-up: One pack-only BM case still has no hospital id. Do not pull the public pack back over the local tree.

## 2026-08-19, Rebuild reader sidecar so local and public BM cases match round-1 pack

- Scope: `build_reader_v150_clinical_sidecar_20260818.py`, Next `reader_v150_clinical.json`, HTML `reader_v150_clinical.js`.
- Reason: Round-1 pack already has the 50 BM videos. Local/public clinical sidecar was still 2026-08-18 and missed later BM/T joins.
- Key changes: Prefer `case_to_patient.csv` as the id source. Map gastritis/polyp text to site "胃". Rebuild sidecar for Next and the round-1 agent. Case map ids unchanged.
- Validation: Sidecar matched 148, id_only 1 (BM-007, no source-table row), unmatched 1 (BM-001). T 100 all have ids. Benign sites 24/25.
- Deployment: Local JSON/JS updated. Public Next needs a redeploy. Do not pull the Aliyun HTML pack back over this tree.
- Follow-up: BM-001 still has no hospital id.

## 2026-08-19, Reader v150 catalog aligned to original clinical and media

- Scope: `join_reader_v150_to_task_datasets.py`, `reader_v150_catalog.csv`, `READER_V150_JOIN.md`.
- Reason: Confirm the five MD5 T matches and make the summary table carry original clinical, video, and still fields.
- Key changes: Re-check the five clips against 2025 contrast-agent and qualified copies (duration, frame count, raw-frame MD5). Parse TNM strings so historical T fills. Add Z0 aliases for 6-8 digit ids. Write a 150-row catalog with source table, pathology, diagnosis, original video/still paths. No names.
- Validation: Five T pairs match again. Catalog: 149 videos, 148 clinical rows, 141 stills. Only BM-001 has no original media.
- Deployment: Report and catalog only. Sidecar JSON not rebuilt.
- Follow-up: BM-001 remains pack-only.

## 2026-08-19, Match five anonymous MD5 T clips via qualified 2025 videos

- Scope: `case_to_patient.csv`, `join_reader_v150_to_task_datasets.py` (Z0 alias), `READER_V150_JOIN.md`, join CSV/JSON.
- Reason: Continue searching the six unmatched reader cases. The five T clips are hash-named copies, not hospital ids.
- Key changes: Join each clip to the 2025 contrast-agent video of the same duration, frame count, and raw-frame MD5 at 0 s and 1 s. Record the five hospital ids. CASE-008 is a second clip of the same patient already in the BM pack. BM-001 still unmatched.
- Validation: All five pairs match on duration, frame count, 1280x960, and raw RGB MD5 at two timestamps. Zip folder T agrees with modeling T and the 200-case screening table.
- Deployment: Map CSV and join report only. Reader sidecar JSON not rebuilt.
- Follow-up: BM-001 (800x600, 9.5 s, no burned-in id) is the last unmatched case.

## 2026-08-19, Revisit prior match records; drop MD5 fragment IDs

- Scope: `case_to_patient.csv`, sidecar `extract_ids`, `join_reader_v150_to_task_datasets.py`, `READER_V150_JOIN.md`.
- Reason: Continue matching against the Aug 15/18 records. Five T clips were marked exact_id from hex fragments.
- Key changes: Skip 20+ hex stems in `extract_ids`. Clear CASE-008/042–045 fake ids (`bbf0`, `cd2`, `dd1`, `11448`, `bc247`). Keep Aug 15 CASE-008 guess `129041` as clue only; it is not in the patient master.
- Validation: BM-001 still unmatched in every prior record. Coverage stays 144/150.
- Deployment: Map CSV only. Sidecar JSON not rebuilt.
- Follow-up: Do not promote hash-sliced guesses.

## 2026-08-19, Benign reader join: 24 found, BM-001 stays anonymous

- Scope: `join_reader_v150_to_task_datasets.py`, `reader_v150_benign_crosswalk.csv`, `READER_V150_JOIN.md`.
- Reason: User asked to keep checking benign cases; seven Dehua clips and BM-001 still looked missing.
- Key changes: Treat Zhuo `良性/N.avi` as pack order, not hospital id. Record gastritis video path, stills, clinical, and CNNC ulcer-folder copies. Document that Dehua stills stop at dh64 and that `德化(1).xlsx` skips dh56.
- Validation: 24/25 benign have on-disk gastritis video. BM-001 (800x600 msvideo1, 9.5 s) has no size, first-frame, or aHash hit in gastritis, ulcer folders, or source zips. Do not assign hbyz1 or dh01.
- Deployment: Report only. Do not invent a patient id for BM-001.
- Follow-up: Five MD5 T clips still unmatched.

## 2026-08-19, Resolve v150 labels via old numbering history

- Scope: `join_reader_v150_to_task_datasets.py`, `reader_v150_numbering_crosswalk.csv`, `READER_V150_JOIN.md`.
- Reason: v150 CASE ids are Zhuo zip order, not reader_study_150 / 100-subset ids. Zip folder T looked like label errors.
- Key changes: Join old selected_cases, 100-subset, and 200-case screening table by patient_id. Record zip folder vs old CASE folder.
- Validation: Historical pathology vs modeling agree 58/58. Zhuo folder T vs history disagree 32. 62 zip folders still use old CASE-xxx names. Six anonymous clips unresolved.
- Deployment: Report only. Do not rewrite Zhuo reference_pt or product labels.
- Follow-up: MD5 T1/19 and T3/35-38 plus BM-001 still have no hospital id.

## 2026-08-19, Continue reader v150 join (videos and T labels)

- Scope: `scripts/join_reader_v150_to_task_datasets.py`, `READER_V150_JOIN.md`, `reader_v150_join.csv`.
- Reason: Seven Dehua BM cases had videos but no stills; T hash cases and label clashes were unchecked.
- Key changes: Count gastritis `video_manifest` as original. Compare reader `reference_pt` with modeling 4-class T.
- Validation: 144 / 150 now hit modeling or original. Benign 24/25 have gastritis video. T label agree 55/85. Five MD5 T clips and BM-001 remain unmatched. 10 T cases are 2025 freeze-only.
- Deployment: Report only.
- Follow-up: Human review of the 30 T disagreements. Do not treat Zhuo `reference_pt` as pathology.

## 2026-08-19, Join reader v150 100+50 to task datasets

- Scope: `scripts/join_reader_v150_to_task_datasets.py`, `dataset/task_datasets/READER_V150_JOIN.md`, `reader_v150_join.csv`.
- Reason: Map the 150-case reader pack (100 T + 50 BM) onto the new T-staging / binary catalogs and freeze originals.
- Key changes: Case-to-patient join with gastritis `patient_key` and freeze `sample_id`. Z0 prefix recovers 204624 / 204794.
- Validation: 137 / 150 hit modeling or original. T 95/100 in freeze (85 in screened CSV). Benign 17/25 in gastritis stills. Malignant 25/25 in freeze.
- Deployment: Report only.
- Follow-up: 5 T hash-stem IDs and 8 Dehua-video-only benign cases remain unmatched to stills.

## 2026-08-19, Inventory originals against task datasets

- Scope: `scripts/build_task_datasets_source_inventory.py`, `dataset/task_datasets/SOURCE_INVENTORY.md`, `source_inventory.json`.
- Reason: Modeling CSVs needed a live join to freeze originals, inflammation `images/`, and gastritis `raw_decoded`.
- Key changes: Count original / processed / modeled layers for T-staging, inflammation, and gastritis. Do not add the three lines.
- Validation: Freeze T 13,763 matches on-disk original/crop_ui/crop_roi. Official T rows 13,504 all have originals. Inflammation disk 1,693 / model 1,468. Gastritis raw 2,758 / processed 2,746 / all modeled rows join raw `image_source`.
- Deployment: Report only.
- Follow-up: 224 inflammation registry test rows unused. 12 gastritis raw files not processed (11 `.Jpg`, 1 bmp).

## 2026-08-19, Audit task-dataset label completeness

- Scope: `scripts/audit_task_datasets.py`, `dataset/task_datasets/INTEGRITY.md`, `integrity.json`.
- Reason: Confirm T-staging and binary CSVs have complete, consistent labels after the catalog was created.
- Key changes: Audit required fields, label domains, T-stage mapping, patient mix, path leaks, and cross-task agreement.
- Validation: Labels complete. T `label` equals `class_label` and mapped `T_stage`. Binary `class_name` matches `label`. No T-staging path marked benign. Images all on disk. Warnings: 14 mixed-T patients, train/test patient overlap, 868 T ROI gaps, 8 empty binary ROI paths.
- Deployment: Report only. Split CSVs unchanged.
- Follow-up: Review stray T1 rows and remap collisions before training on unique official paths.

## 2026-08-19, Add clean two-task dataset catalog

- Scope: `dataset/task_datasets/`, `scripts/build_task_datasets.py`, `dataset/DATASET_GUIDE.md`.
- Reason: T-staging and benign/malignant CSVs were scattered across pipeline packs and training views.
- Key changes: New catalog with `t_staging/` and `binary_benign_malignant/` split CSVs only. Images stay in freeze / gastritis / inflammation trees. T-staging paths use the 20260819 official remap.
- Validation: Builder writes `manifest.json`. T-staging 14,372 rows, all images on disk, ROI 13,504. Binary 17,698 rows, all images on disk, ROI 17,690 after crop_roi remap.
- Deployment: Documentation pointer only. acc_boost2 weights unchanged.
- Follow-up: T-staging train/val still include quarantine and leftover-legacy rows; do not treat those as freeze samples.

## 2026-08-19, Align acc_boost2 pack to freeze images and clinical tables

- Scope: `scripts/align_acc_boost2_to_official_freeze.py`; overlay under `pipeline/data/tstaging_4class_screened_eval_20260531/alignment_official_20260819/`.
- Reason: Product train/val CSVs still use legacy `dataset/internal/train/` and deleted `putian/` paths. Need a join to freeze `crop_ui` / `crop_roi` and `dataset/tables/clinical_table_registry.csv` without rewriting the weight contract.
- Key changes: Official-only remap (does not accept a still-existing legacy path). Ready CSVs rewrite `image_path` / `roi_path` when freeze files exist. Quarantine holds old Putian frames not in freeze. Recommended T fixes mark 14 mixed-T stray T1 frames.
- Validation: 14,372 frames resolved (official 13,504, quarantine 583, leftover legacy 285, unmatched 0). Official rows have crop_roi + annotation + mask. Media four-class agreement 12,700 / 2 differ. Table T agreement 11,258 / 64 differ.
- Deployment: Overlay only. Product `20260531` CSVs and acc_boost2 weights are unchanged.
- Follow-up: Human review of `recommended_t_fixes.csv` (2024 stray T1 and eight 2018/prospective table clashes). Do not treat quarantine Putian as freeze samples.

## 2026-08-19, Reader flow is mark keyframe then draw box

- Scope: `InteractiveSegPanel.tsx`, `DoctorKeyframeStrip.tsx`, `ReaderHelpModal.tsx`.
- Reason: Auto-detect can mark the wrong lesion. Doctors asked to drop segmentation first and keep the cine path shorter.
- Key changes: `reader_v150` no longer runs pre-seg, YOLO detect, SAM after a box, or optical-flow propagate. Pause, mark a keyframe (or Space), then draw the lesion box on that frame. Assist uses the doctor box as a polygon. Lumen box stays optional and manual. Lesion and lumen paint add/erase sit on the main right rail, not under More.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. LAN `/` 200, `:3300` contract 200. Aliyun loopback `/` 200, `/reader` 307, first-round list 200 (`total=150`), viewing-trace 200.
- Deployment: Workstation BUILD `o0reg1WfuxUoVOGanQZOQ` on `:3000` / `:3300`. Aliyun READER_ONLY BUILD `ktn9E_P7fD9DleshNbEBS`; previous `*.bak_20260819_1523`.
- Follow-up: Hard refresh after login. Non-reader SAM workbench is unchanged. Rollback is Aliyun `server.js.bak_20260819_1523` plus `.next-public-deploy-dist.bak_20260819_1523`, then restart `gastric-next`.

## 2026-08-18, Match malignant BM reader clips to surgery videos

- Scope: `scripts/build_reader_v150_clinical_sidecar_20260818.py`, `reader_v150_clinical.json` / `.js`, `case_to_patient.csv`.
- Reason: BM-026..050 stayed unmatched because size search only looked at the gastritis store. The Zhuo malignant clips are copies of Xiehe / Foshan / Dehua cancer videos, not gastritis AVI.
- Key changes: Search surgery and qualified-reader trees; accept a unique hospital stem even when several clips share a byte size; one remux uses first-frame plus near-size. Fill ultrasound-accompanying site / size / CEA / CA19-9 for those malignant BM cases. BM-001..025 still hide CEA / CA19-9.
- Validation: Script self-check (CASE-001 token 1279829). Sidecar matched 140 / id-only 9. BM ids 49/50 (benign 24, malignant 25). BM site 45, size 28, thickness 31. Malignant CEA 22. T-stage still 100/100 with ids.
- Deployment: Sidecar files updated on disk. Restart Next `:3000` / `:3300`, then hard refresh.
- Follow-up: BM-001 is still unmatched. The zip AVI is 800x600 msvideo1, 9.5 s, and is not in the current gastritis or surgery video stores. Four matched benign IDs still have no site/size in the source tables.

## 2026-08-18, Assist shows real T-stage, steps, and report site

- Scope: `assist-display-stage.ts`, `AssistResultCards`, `AssistAnalysisModal`, `InteractiveSegPanel.tsx`, `gc-us-report-template.ts`, `page.tsx`.
- Reason: After Assist, AI 分期 stayed on 待医生判断 even with 87% classifier confidence. The modal only said wait. The report left `病灶位于［］` empty.
- Key changes: The AI card reads classifier / fusion stage (unguarded T4 shows as T3). The modal lists five live steps. Report site is mapped from the ultrasound table onto 贲门 / 胃底 / 胃体 / 胃角 / 胃窦 / 幽门.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`.
- Deployment: Restart Next `:3000` / `:3300`, hard refresh, run Assist again.
- Follow-up: None.

## 2026-08-18, Keep Assist T-stage on the evidence panel

- Scope: `mergeFreshEvidence` / `pickReferenceStage`, `page.tsx` imaging-assist merge, `analyze_case.py` display fallback.
- Reason: After Assist wrote T1–T3, the live contour refresh rebuilt the report as `uncertain` and wiped the chips / AI stage.
- Key changes: A concrete model or doctor stage is not replaced by an empty contour update. Backend never returns an empty display stage (T4-only → T3, no scores → T2). T4+ normalizes to T3 on the panel.
- Validation: `python3 pipeline/agent/product/test_research_stage_gate.py`. `npx tsc --noEmit` in `apps/gastric_scan_next`.
- Deployment: Restart Next `:3000` / `:3300`, hard refresh, run Assist again.
- Follow-up: None.

## 2026-08-18, Assist analysis modal glass style

- Scope: `AssistAnalysisModal.tsx`, `globals.css`, `InteractiveSegPanel.tsx` progress copy.
- Reason: The running modal looked like a solid box and told readers the playhead would stay put.
- Key changes: Frosted-glass overlay and card aligned with the workbench (dark veil, cyan accent, white/10 chrome). Copy now only describes multi-frame assessment and post-analysis edits.
- Validation: Visual check after Next reload. `npx tsc --noEmit` in `apps/gastric_scan_next`.
- Deployment: Restart Next `:3000` / `:3300`, then hard refresh and run Assist.
- Follow-up: None.

## 2026-08-18, Assist results always show concrete values

- Scope: `assist-display-stage.ts`, `GcUsEvidencePanel.tsx`, `BmEvidencePanel.tsx`, `gc-us-report-template.ts`, `analyze_case.py` display gate.
- Reason: After Assist, stage / signs / nature / report still fell back to 待医生判断 or 未评估 whenever wall evidence was proxy or T4 was gated.
- Key changes: After a result exists, AI stage, nature, and six signs always show a concrete class. Unguarded T4 displays as T3. Model-filled stage and serosa are enough to generate the report. Clinical table blanks stay table blanks.
- Validation: `python3 pipeline/agent/product/test_research_stage_gate.py`. `npx tsc --noEmit` in `apps/gastric_scan_next`.
- Deployment: Restart Next `:3000` / `:3300`, then hard refresh and run Assist again.
- Follow-up: Sign classes remain stage-mapped until the multi-task head is wired.

## 2026-08-18, Return fusion T-stage to the Assist UI

- Scope: `analyze_case.py` display gate, `assist-display-stage.ts`, `page.tsx` reader stage wiring.
- Reason: After Assist, AI 分期 stayed on 待医生判断. The backend emptied `assist_display_stage` whenever wall geometry was a bbox/SDF proxy, and the frontend then preferred raw classifier T4+ and hid it.
- Key changes: Publish the T4-capped fusion T1–T3 as `assist_display_stage` even on proxy wall. Frontend shows that stage; unguarded T4 stays hidden. Remove the invented T2 fallback.
- Validation: `python3 pipeline/agent/product/test_research_stage_gate.py` (proxy-wall case now expects display T3). `npx tsc --noEmit` in `apps/gastric_scan_next`.
- Deployment: Restart Next `:3000` / `:3300` so the TS pack reloads. Python Agent is live on the next analyze call. Hard refresh after login.
- Follow-up: T4 still needs explicit serosa / organ evidence. Sign classes remain stage-mapped until the multi-task head is wired.

## 2026-08-18, Recover BM reader clinical site and size

- Scope: `scripts/build_reader_v150_clinical_sidecar_20260818.py`, `reader_v150_clinical.json` / `.js`, `case_to_patient.csv`.
- Reason: Reader v150 BM-001..050 all showed empty 病灶部位 / 肿瘤长径 / 肿瘤厚度. The Zhuo zip only has numbered clips, but 24/25 benign files match unique byte sizes in the external gastritis video store.
- Key changes: Size-match those unique benign clips, then fill ultrasound-accompanying site and parsed length/thickness from the gastritis clinical tables. CEA / CA19-9 stay hidden on BM-001..025. Malignant BM-026..050 stay unmatched.
- Validation: Script self-check (CASE-001 token 1279829). Sidecar matched 115 / id-only 9 / schema 1.1. BM site 20, BM size 13, BM thickness 13. T-stage still 100/100 with ids; 95 matched clinical; 79 CEA / CA19-9.
- Deployment: Sidecar files updated on disk. Next `/api/reader/cases` caches the pack in process; restart `:3000` / `:3300` then hard refresh to see BM fields.
- Follow-up: BM-001 has no unique size hit. Four matched benign cases have no site/size in the source tables. Malignant BM clips are still numbered only.

## 2026-08-18, Stop calling the clinical pack 22

- Scope: Living docs, paper drafts, current yaml `clinical_type`, architecture figure copy, and `clinical_master_utils.py` constants. SSOT `docs/mainline/clinical_11_field_pack.md`.
- Reason: The pack is 11 fields. The number 22 is only the encoded width (norm + missing). Calling it 22 clinical variables was wrong.
- Validation: Current configs use `clinical_type: true_clinical_11d` and `clinical_n_fields: 11`. `clinical_dim: 22` remains the MLP input width. Historical run dirs, yaml filenames, and stage ids that contain `clinical22` were not renamed.
- Deployment: No Agent switch. Old `true_clinical_22d` is a legacy alias only.
- Follow-up: New prose and figures should say clinical-11 / 11-field pack.

## 2026-08-18, Clinical-only 4-class floor on the official sidecar

- Scope: patient-level LogReg / HGB / RF on the 11-field clinical pack, no image. Report `pipeline/experiments/reports/clinical_only_tstage_4class_20260818/SUMMARY.md`.
- Reason: Check whether T-stage ACC 0.80 is already available from tables alone on the same split as the Swin runs.
- Validation: Prospective 425, best ACC 0.532 (RF, full 11-field). Without size 0.506. Size-only 0.527. Majority T3 0.264. Not 0.80.
- Deployment: Not promoted. Do not switch Agent.
- Follow-up: 0.80 is not the clinical-only ceiling on this sidecar.

## 2026-08-18, Swin Mask-Set v3 first run finished

- Scope: v3 train on GPU1, `swin_mask_set_v3_phase0_20260818_20260818_132407`.
- Reason: Test mask-gated attention, mask-local crop, stage-1 margin, and mean plus soft-advanced pooling.
- Validation: Early stop epoch 46. Best val balanced Acc 0.470 (epoch 32). Prospective 425: ACC 0.504, balanced ACC 0.467, T2 recall 0.500 but T1 recall 0.309. Worse ACC than v1 0.581. ~107 min.
- Deployment: Not promoted. Do not switch Agent / `:8767` / `:8768`.
- Follow-up: T2 aux pulled T1 into T2. Do not stack more heads without fixing that.

## 2026-08-18, Unified right tool rail with four-character labels

- Scope: `InteractiveSegPanel.tsx`, `globals.css`.
- Reason: The workbench split lesion tools on the left and lumen tools on the bottom-right, with colloquial 2-character labels and a separate magnifier cluster.
- Key changes: One right-side rail. Visible buttons are 框选病灶, 检测胃腔, and 更多工具. Magnifier, region zoom, refine, and remaining tools sit in a single More list. Labels are four-character standard terms. No 病灶 / 胃腔 section headers.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. LAN `/` 200, `:3300` contract 200. Aliyun loopback `/` 200, `/reader` 307, viewing-trace 200.
- Deployment: Workstation BUILD `DJgIHzEC34jChZfFOFmmV` on `:3000` / `:3300`. Aliyun READER_ONLY BUILD `2AVouXkhskHN2SsSKiOiB`; previous `*.bak_20260818_1252`.
- Follow-up: Hard refresh after login. Rollback is Aliyun `server.js.bak_20260818_1252` plus `.next-public-deploy-dist.bak_20260818_1252`, then restart `gastric-next`.

## 2026-08-18, Assist modal stays on frame and writes concrete signs

- Scope: `InteractiveSegPanel.tsx`, `AssistAnalysisModal.tsx`, `assist-sign-defaults.ts`, `GcUsEvidencePanel.tsx`, `app/page.tsx`, `gc-us-report-template.ts`.
- Reason: Assist sought the visible video across keyframes. The panel then stayed on 未评估 or L-layer / proxy labels, so doctors could not edit a real multi-task prediction before generating the report.
- Key changes: Clicking 辅助分析 opens a centered 「正在辅助分析中」 modal immediately. The playhead stays put; keyframe stills come from the current frame, thumbs, or a hidden video element. After the multi-frame run, morphology, margin, growth, serosa, wall layers, and perigastric tissue are written as concrete dropdown classes (stage defaults if the model is empty). Doctors can then edit and generate the report.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. LAN `/` 200, `:3300` contract 200. Aliyun loopback `/` 200, `/reader` 307, viewing-trace 200.
- Deployment: Workstation BUILD `yAXostIRlx5r4WaF0dqLO` on `:3000` / `:3300`. Aliyun READER_ONLY BUILD `w6HYkcexXkQv4fY-ExlzV`; previous `*.bak_20260818_1249`.
- Follow-up: Hard refresh after login. These sign classes are mock / stage-mapped until the multi-task head is wired. Unguarded T4 remains hidden. Analysis still uses workstation `acc_boost2`. Rollback is Aliyun `server.js.bak_20260818_1249` plus `.next-public-deploy-dist.bak_20260818_1249`, then restart `gastric-next`.

## 2026-08-18, Match reader clinical tables and move auxiliary data below signs

- Scope: `scripts/build_reader_v150_clinical_sidecar_20260818.py`, `reader_v150_clinical.json`, `case_to_patient.csv`, `GcUsEvidencePanel.tsx`, `BmEvidencePanel.tsx`, `DoctorReportStudio.tsx`.
- Reason: Most v150 cases still showed empty site / size / CEA / CA19-9. Benign BM cases were never tested for CEA / CA19-9, but empty cells were shown as 阴性/未测. Auxiliary data sat above the sign ticks.
- Key changes: Rebuild the sidecar from Zhuo `T分期100例.zip` plus the screening / hospital clinical tables (no names or pathology in the published sidecar). T-stage 100/100 now have a patient key; 95 have ultrasound-accompanying fields; 79 have CEA and CA19-9 numbers. BM-001..025 hide CEA / CA19-9. Auxiliary data moves below the sign block. Empty markers are omitted instead of shown as negative.
- Validation: Script self-check (CASE-001 token 1279829). `npx tsc --noEmit` in `apps/gastric_scan_next`. LAN `/` 200, `:3300` contract 200. Aliyun loopback `/` 200, `/reader` 307, viewing-trace 200. Sidecar matched 95 / schema 1.1.
- Deployment: Workstation BUILD `ysqHHgT65aHlRhVuBJDH0` on `:3000` / `:3300`. Aliyun READER_ONLY BUILD `z0CWfp1IUZri5V3k5RFqT`; previous `*.bak_20260818_1240`.
- Follow-up: BM-001..050 remain unmatched; `良恶性鉴别.zip` only has numbered clips (1.avi / 13(1).avi) with no hospital id. Hard refresh after login. Rollback is Aliyun `server.js.bak_20260818_1240` plus `.next-public-deploy-dist.bak_20260818_1240`, then restart `gastric-next`.

## 2026-08-18, Centered larger assist cards, hide certainty before analysis

- Scope: `AssistResultCards` in `ReaderEvidencePanel.tsx`.
- Reason: Before Assist, 良/恶性 showed 待分析 plus 把握不足, left-aligned and still small.
- Key changes: Title and value are centered and larger. Certainty / percent render only after an assist result exists.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. LAN `/` 200, `:3300` contract 200. Aliyun loopback `/` 200, `/reader` 307, viewing-trace 200.
- Deployment: Workstation BUILD `TYw1zQgslX5GCcM2kMH1f` on `:3000` / `:3300`. Aliyun READER_ONLY BUILD `rfcBHFk2yP24PoYbcpZR4`; previous `*.bak_20260818_1221`.
- Follow-up: Hard refresh after login. Rollback is Aliyun `server.js.bak_20260818_1221` plus `.next-public-deploy-dist.bak_20260818_1221`, then restart `gastric-next`.

## 2026-08-18, Formal Union-Hospital ultrasound report page

- Scope: `TemplateReportEditor.tsx`, `DoctorReportStudio.tsx`.
- Reason: The generated report still read as a template draft (AI review block, disclaimer footer). Doctors asked for a real ultrasound-report look with hospital letterhead and key-frame images on top.
- Key changes: Formal page uses 福建医科大学附属协和医院 / 超声科 / 胃充盈超声 AI 辅助报告, accession/sex/age/exam fields, key-frame figures at the top (English captions), then 超声所见 / 超声提示. Removes AI-assist review, implementation notes, and the template disclaimer. Side rail still holds analysis visualizations.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. LAN `/` 200, `:3300` contract 200. Aliyun loopback `/` 200, `/reader` 307, viewing-trace 200.
- Deployment: Workstation BUILD `LD1zL5Ddqv4tF_NCIIa9W` on `:3000` / `:3300`. Aliyun READER_ONLY BUILD `g-wkhqeoni56Pr3Xhw1j6`; previous `*.bak_20260818_1219`.
- Follow-up: Hard refresh after login. Rollback is Aliyun `server.js.bak_20260818_1219` plus `.next-public-deploy-dist.bak_20260818_1219`, then restart `gastric-next`.

## 2026-08-18, Swin Mask-Set v2 architecture and train start

- Scope: `pipeline/lib/mask_set_swin.py`, `pipeline/configs/tstaging_4class_swin_mask_set_v2_phase0_20260818.yaml`, `run_experiment.py`, `evaluate_experiment.py`.
- Reason: v1 Tiny last-stage 12x12 lost T2 margin evidence (prospective T2 recall 0.206). Scale the encoder and redesign region / set / aux paths before the second run.
- Key changes: Swin-Base ~95M; stages 2+3 (24x24 + 12x12); explicit margin token into `aux_t1t2`; early/late and T3/T4 aux; mix in embedding space. Same sidecar, no clinical, no Agent switch.
- Validation: GPU1 smoke, 95M params, AMP backward, peak ~2.4 GB for one 6-frame bag. Train launched on GPU1.
- Deployment: Not promoted. Do not switch Agent / `:8767` / `:8768`.
- Follow-up: Compare vs v1 0.581 and same-sidecar Dual 0.678. Stratify by N.

## 2026-08-18, Generated report uses the Word template page

- Scope: `DoctorReportStudio.tsx`, `TemplateReportEditor.tsx`.
- Reason: The generated-report pane had been flattened to plain text. Doctors need the same Word layout as 《胃充盈超声报告模板》: A4 page, Times New Roman / SimSun, checkbox tokens, underline blanks.
- Key changes: The left pane now renders `TemplateReportPreview` (white Word page on a black workspace). Key images stay out of the Word page (`omitImages`) and remain in the right-hand visualization rail.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. LAN `/` 200, `:3300` contract 200. Aliyun loopback `/` 200, `/reader` 307, viewing-trace 200.
- Deployment: Workstation BUILD `BKMJrlcmgiLEriedz3UiM` on `:3000` / `:3300`. Aliyun READER_ONLY BUILD `Dldy1jHrHvDYlPrVn1hOE`; previous `*.bak_20260818_1206`.
- Follow-up: Hard refresh after login. Rollback is Aliyun `server.js.bak_20260818_1206` plus `.next-public-deploy-dist.bak_20260818_1206`, then restart `gastric-next`.

## 2026-08-18, Black report text, visualizations in the interface rail

- Scope: `DoctorReportStudio.tsx`, `app/page.tsx`.
- Reason: After generate-report, images sat inside the report body and the overlay was still slate-gray. Doctors asked for a black report page, text-only report, and more visualizations on the interface.
- Key changes: The generated-report overlay is black. The left pane is Times New Roman report text only. Wall / DINO / overlay / current-frame images move to a right-hand visualization rail with English captions and click-to-enlarge. They are not written into the report body.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. LAN `/` 200, `:3300` contract 200. Aliyun loopback `/` 200, `/reader` 307, viewing-trace 200.
- Deployment: Workstation BUILD `fIt-YfZLHzHDwflUKz2x_` on `:3000` / `:3300`. Aliyun READER_ONLY BUILD `Orrs8RLuCVZ5OGSCj-bQ-`; previous `*.bak_20260818_1138`.
- Follow-up: Hard refresh after login. Rollback is Aliyun `server.js.bak_20260818_1138` plus `.next-public-deploy-dist.bak_20260818_1138`, then restart `gastric-next`.

## 2026-08-18, Swin Mask-Set T-stage first run finished

- Scope: `pipeline/lib/mask_set_swin.py`, `PatientMaskBagDataset`, trainer / `run_experiment` / `evaluate_experiment`, config `tstaging_4class_swin_mask_set_phase0_20260817.yaml`.
- Reason: From-scratch variable-N set network instead of per-frame acc_boost2 plus hybrid pooling. No 11-field clinical.
- Key changes: Swin-Tiny @ 384, native-res mask regions, class-query PMA, length dropout, isolated batch keys. Official crop_ui sidecar.
- Validation: Early stop epoch 35. Best val balanced Acc 0.547 (epoch 23). Prospective 425: ACC 0.581, balanced ACC 0.478, T2 recall 0.206. N=1 ACC 0.371 vs N>6 0.717. No train/val collapse. Below same-sidecar Dual lesion-region ACC 0.678.
- Deployment: Not promoted. Do not switch Agent / `:8767` / `:8768`.
- Follow-up: T2 is the failure mode. External remains report-only. Report: `pipeline/experiments/reports/swin_mask_set_phase0_20260817/SUMMARY.md`.

## 2026-08-18, Stay on frame, show assist, generate-then-view report

- Scope: `InteractiveSegPanel.tsx`, `ReaderEvidencePanel.tsx`, `GcUsEvidencePanel.tsx`, `DoctorReportStudio.tsx`, `app/page.tsx`, `lib/reader/assist-display-stage.ts`, `lib/reader/layout.ts`.
- Reason: After Assist, the video jumped away from the current frame; the evidence drawer stayed on 「待医生判断 / 未评估」 because gated stage hid the classifier and the sign panel did not ingest the parent assist state. Generate-report still opened an editable studio.
- Key changes: Assist captures keyframes then seeks back to the original time and does not autoplay. Doctor-facing stage uses `getAssistOpinionStage` (gated first, then classifier / hypothesis T1-T3). Assist writes suggested wall signs and dispatches them into the evidence panel. Evidence drawer is `clamp(18rem, 24vw, 24rem)`. 「生成报告」 freezes a finalized snapshot; the overlay is read-only. Edits stay in the side panel before generate.
- Validation: `node scripts/test_assist_display_stage.mjs`; `npx tsc --noEmit` in `apps/gastric_scan_next`. LAN `/` 200, `:3300` contract 200. Aliyun loopback `/` 200, `/reader` 307, viewing-trace 200.
- Deployment: Workstation BUILD `t0JzY5N--g0ZK4jV7JzAE` on `:3000` / `:3300`. Aliyun READER_ONLY BUILD `p3Q0MYVQTx3RiI_EGbJXI`; previous `*.bak_20260818_1134`.
- Follow-up: Hard refresh after login. Unguarded T4 remains hidden. Rollback is Aliyun `server.js.bak_20260818_1134` plus `.next-public-deploy-dist.bak_20260818_1134`, then restart `gastric-next`.

## 2026-08-18, Task-specific assist and published US clinical fields

- Scope: `AssistResultCards`, `ReaderEvidencePanel`, `GcUsEvidencePanel`, `us-clinical-server.ts`, `data/reader_v150_clinical.json`.
- Reason: BM queue still showed AI T-stage; T-staging still asked for benign/malignant. Site and length showed empty even though the published reader sidecar already has ultrasound fields for matched cases.
- Key changes: BM shows nature only; T-staging shows AI stage only and no longer requires a nature judgment. Clinical site/length/thickness/CEA/CA19-9 now load from the case-level sidecar first, then hospital-table fallback. Location tokens such as 贲门/胃体 are used only when the table has no site.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. LAN `/` 200, `:3300` contract 200. Aliyun loopback `/` 200, `/reader` 307, viewing-trace 200.
- Deployment: Workstation BUILD `DA2wdeoo0zfs_0cJenOCX` on `:3000` / `:3300`. Aliyun READER_ONLY BUILD `vNsQLuA9wvtHQ31mCurZL`; previous `*.bak_20260818_1055`.
- Follow-up: Hard refresh after login. Unmatched BM cases still have no published site/length. Rollback is Aliyun `server.js.bak_20260818_1055` plus `.next-public-deploy-dist.bak_20260818_1055`, then restart `gastric-next`. Expert BM form still pending.

## 2026-08-18, Unified assist result card and hidden gold

- Scope: `AssistResultCards`, `CaseGoldReveal`, `InteractiveSegPanel.tsx`.
- Reason: AI stage and benign/malignant used two different cards, and the gold block showed the implementation note 「默认隐藏，点开后显示在辅助意见旁边」 as visible copy.
- Key changes: One panel, two equal columns, same type scale. Gold is a 「查看真值」 control in that panel header; the value appears there only after click. Toolbar gold is hidden in the simple video workbench so it is not duplicated.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`. LAN `/` 200, `:3300` contract 200. Aliyun loopback `/` 200, `/reader` 307, viewing-trace 200.
- Deployment: Workstation BUILD `AgKFR5RpbI8iDBesV3eJ2` on `:3000` / `:3300`. Aliyun READER_ONLY BUILD `6iuN_TmdBm8WE-fK3KkzF`; previous `*.bak_20260818_0928`.
- Follow-up: Hard refresh after login. Rollback is Aliyun `server.js.bak_20260818_0928` plus `.next-public-deploy-dist.bak_20260818_0928`, then restart `gastric-next`. Expert BM form still pending.

## 2026-08-17, Public AI-stage cards, narrower evidence, no old decision chrome

- Scope: `lib/reader/layout.ts`, `AssistResultCards`; workstation `:3000` / `:3300`; Aliyun `/var/www/gastric-next` reader-only bundle.
- Reason: 0817 leftover items 1, 4, and 6. Public still served the 8/16 UI (no large AI-stage cards). Widening the evidence drawer squeezed the ultrasound frame. The old clinical-decision / tendency block was already deleted on LAN and only remained on the stale public bundle.
- Key changes: Evidence width is back to Wave 1 (`clamp(14rem, 18vw, 18rem)`); large stage text wraps. Public reader-only build now includes the 0817 cards and no longer ships the deleted decision chrome. Classification still runs on the workstation Agent (`acc_boost2`); no separate clinical-decision weight was redeployed.
- Validation: `npx tsc --noEmit`. LAN `/` 200, `:3300` contract 200, tunnel active. Aliyun loopback `/` 200, `/reader` 307, first-round list `total=150`, viewing-trace 200. Public client chunks contain 「AI 分期 / 待分析 / 把握不足」 and not 「临床决策建议 / 分析倾向」.
- Deployment: Workstation BUILD `u652m1GdZEJ9STUw0y6of` (previous `standalone.bak_20260817_2357`). Aliyun READER_ONLY BUILD `pB0hJZ3WDtbSarRLBRI6q`; previous `*.bak_20260817_2359`. Hard refresh after login.
- Follow-up: Rollback is Aliyun `server.js.bak_20260817_2359` plus `.next-public-deploy-dist.bak_20260817_2359`, then restart `gastric-next`. Expert BM form is still pending.

## 2026-08-17, Reader: larger AI-stage cards and section-10 toolbar

- Scope: `AssistResultCards`, `lib/reader/layout.ts`, `InteractiveSegPanel.tsx`, `ReaderToolbar.tsx`, `ReaderHelpModal.tsx`, `app/page.tsx`.
- Reason: Doctors said AI stage / Pending / Low certainty were still too small, and the toolbar still mixed two draw modes plus too many primary buttons.
- Key changes: Stage and nature cards use large type for the title, the pending/stage value, and the certainty band (把握不足). Evidence drawer is wider. Primary draw mode is drag-points only; paint add/erase sit under More. Magnifier and zoom ROI sit top-right; lumen extras sit bottom-right. On-canvas hint is 「框选病灶 → 精调」.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`.
- Deployment: Local Next only. Hard refresh after rebuild.
- Follow-up: Public deploy, clinical-decision model, and the expert BM form stay blocked.

## 2026-08-17, Reader Wave 5 leftover: keyframe-only assist, hide remaining full-clip track

- Scope: `InteractiveSegPanel.tsx`, `app/api/reader/agent/analyze/route.ts`.
- Reason: Wave 5 hid the primary full-clip track button, but the secondary rail still started whole-clip precompute, and analyze still accepted `assist_profile=full`.
- Key changes: Secondary 「视频跟踪」is hidden. Reader analyze coerces `full` to `contour_anchored_fast`. Workbench analysis always sends the keyframe-fast profile. `precomputeVideoTracking` remains in code but has no UI entry.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`.
- Deployment: Local Next only. Hard refresh after rebuild.
- Follow-up: Public deploy, clinical-decision model, and the expert BM form stay blocked. Toolbar §10.3 (keep only one draw mode) is still open if doctors want it.

## 2026-08-17, Reader Wave 6a: split BM and T-stage evidence panels

- Scope: `BmEvidencePanel.tsx`, `app/page.tsx`, `ReaderReportPanel.tsx`, `ReaderWorkbench.tsx`.
- Reason: 0817 todo section 9.1-9.3. Benign/malignant and T-stage use different signs; they should not share one form.
- Key changes: BM mode shows size (read-only from the US report), layer-structure clarity, and mucosal thickening (mild / moderate / severe). T-stage mode keeps the existing core-sign panel. The expert guideline form (9.4) is still pending.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`.
- Deployment: Local Next only. Hard refresh after rebuild.
- Follow-up: Public deploy, clinical-decision model, and the expert BM form stay blocked.

## 2026-08-17, Reader Wave 5: report CTA, deepest keyframe, no full-clip track

- Scope: doctor keyframes, evidence drawer, Reader toolbar, InteractiveSegPanel, report accept flow.
- Reason: 0817 todo sections 11-12. Doctors needed a visible generate/confirm report path, a deepest-invasion keyframe, and no full-clip track.
- Key changes: Evidence header is 「确认完整报告」. Generate report is a large sticky CTA. Structured fields list site, length/thickness, wall layers, morphology, boundary, growth, serosa, outer contour, and surrounding tissue. Accept/adopt now includes a final benign/malignant choice. Keyframe strip stars the deepest-invasion frame; analysis prefers it and still fuses other keyframes via `target_times_sec`. Full-clip track buttons are hidden. Confirm edit is ring-highlighted.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`; `node --experimental-strip-types scripts/test_doctor_keyframes.mjs`.
- Deployment: Local Next only. Hard refresh after rebuild.
- Follow-up: Wave 6 of `待办清单_0817.md` stays blocked (public deploy, decision model, expert BM form).

## 2026-08-17, Reader Wave 4: evidence panel delete and one core-sign block

- Scope: `ReaderEvidencePanel.tsx`, `GcUsEvidencePanel.tsx`, `GcUsSignModelMap.tsx`, `ReaderReportPanel.tsx`, `GcUsImagingReportCard.tsx`, `app/page.tsx`.
- Reason: 0817 todo sections 6-8. The evidence drawer repeated T-stage grasp, clinical labs, process traces, and soft scores.
- Key changes: Top cards are AI T-stage plus confidence, then benign/malignant plus percent. Pathology gold stays via `CaseGoldReveal`. Clinical site / length / thickness / CEA / CA19-9 appear once inside core signs and are read-only from the US report. Morphology, boundary, growth, serosa, and perigastric stay editable; wall layers sit at the end. Score details open from a question-mark control. Direction geometry, backend/trust rows, and the old 12 deleted blocks are gone from the doctor panel.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`.
- Deployment: Local Next only. Hard refresh after rebuild.
- Follow-up: Wave 5 of `待办清单_0817.md` (report CTA, deepest keyframe, drop full-clip track).

## 2026-08-17, Reader Wave 3: local contour edit and a shorter toolbar

- Scope: `contour-edit.ts`, `ReaderViewer.tsx`, `ReaderToolbar.tsx`, `ReaderWorkbench.tsx`, `InteractiveSegPanel.tsx`.
- Reason: 0817 todo sections 3 and 10. Doctors needed more handles, a local drag, whole-box move, undo, and fewer primary buttons.
- Key changes: Visible handles match the 28 control points. Soft-drag sigma is 14 so one point does not pull the whole ring. Interior drag translates the contour. Alt-click inserts a point; Delete removes one. Reader undo covers contour edits. Primary tools are box / drag / add / erase / redraw / undo / confirm. 「出轮廓」 is now 「分割」.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`.
- Deployment: Local Next only. Hard refresh after rebuild.
- Follow-up: Wave 4 of `待办清单_0817.md` (evidence panel delete and rebuild).

## 2026-08-17, Reader Wave 2: keep lumen polygon and stop keyframe drag offset

- Scope: `doctor-keyframe-preseg.ts`, `ReaderWorkbench.tsx`, `InteractiveSegPanel.tsx`.
- Reason: 0817 todo section 4. Pre-seg already returned a lumen polygon but Reader discarded it and rebuilt a 32-point box. Scrubbing after opening a keyframe left the old overlay on a new frame (shape right, position wrong).
- Key changes: Persist `lumenPolygon` on the keyframe. Prefer that polygon over a box proxy. `scalePolyToFull` no longer upscales coords that are already full-frame. Leaving a keyframe by scrub persists contours and clears the live overlay.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`.
- Deployment: Local Next only. Hard refresh after rebuild.
- Follow-up: Wave 3 of `待办清单_0817.md` (contour edit tools and toolbar).

## 2026-08-17, Reader Wave 1: image-first layout and contour-only masks

- Scope: `apps/gastric_scan_next` Reader workbench and main `/` / `/workbench` canvas. Layout constants in `lib/reader/layout.ts`.
- Reason: 0817 todo sections 1-2. The ultrasound frame should dominate; filled masks were covering the lesion.
- Key changes: Narrower case / report / evidence chrome. Lesion and lumen draw stroke only (no fill). PNG overlay alpha capped at 0.12. ReaderViewer redraws on container resize so contours stay aligned after the layout change.
- Validation: Typecheck of the Next app. Visual check: open a case, confirm outlines only and that the canvas still letterboxes with `object-contain`.
- Deployment: Local Next only. Hard refresh after rebuild. Do not change SAM services.
- Follow-up: Wave 2 of `待办清单_0817.md` (keyframe lumen polygon + drag offset).

## 2026-08-17, SAM2 full-parameter finetune on current segmentation split

- Scope: `scripts/run_sam2_static_prompt_adapter_finetune.py --adaptation-mode full_finetune`; run dir `experiments/prompt_mask_agent/r004_patient_disjoint_static/full_finetune_20260817/`.
- Reason: Measure the unfrozen-encoder upper bound on `prompt_mask_patient_disjoint_v1` against r004 PEFT and the current SAM3.1 LoRA.
- Key changes: 4-epoch full finetune on GPU1 from SABM-GUS-SAM2; best epoch 2; 320-patient holdout plus prospective 46 / external 84 cine-static evals. Online SAM services unchanged.
- Validation: Replay dice gap -0.0025 (candidate). Holdout box Dice 0.8455 vs r004 0.8147. Prospective box Dice 0.8788 vs SAM3.1 LoRA 0.8816 (same 46 patients, different frame aggregation).
- Deployment: Not promoted. `:8767` stays SAM2 interactive; `:8768` stays SAM3.1 LoRA.
- Follow-up: Same-protocol SAM3.1 eval on the 320-patient holdout if a ranking claim is needed.

## 2026-08-17, why SSH accepts a password

- Scope: `scripts/setup_collaborator_access.sh`; sshd `Match User why`; `docs/technical/COLLABORATOR_ACCESS.md`.
- Reason: Collaborator login should allow a password, not only a private key.
- Key changes: Unlock the Unix password. sshd now accepts publickey or password. Password file stays in the owner `~/.secrets/` directory.
- Validation: Password SSH to localhost as `why` returns the account name. ACL verify still passes.
- Deployment: Workstation sshd reload. Do not put the password in git or chat.
- Follow-up: Send the password off-repo.

## 2026-08-17, why can read processed images, not originals

- Scope: `scripts/setup_collaborator_access.sh`; `docs/technical/COLLABORATOR_ACCESS.md`; ACL refresh for `why`.
- Reason: Viewing originals without allowing a full-folder copy is not possible on POSIX SSH. Processed crops are enough for algorithm work.
- Key changes: Cleared the blanket deny on `dataset/` and `data/`. Named deny now targets `original/`, `raw_patient_videos/`, raw trees, and clinical tables. `crop_ui/`, `crop_roi/`, `data/processed/`, and training views are readable.
- Validation: `sudo bash scripts/setup_collaborator_access.sh --verify --user why` checks crop_ui/crop_roi readable and original/raw denied.
- Deployment: Workstation ACL only. Re-run `--apply` after adding a new `original/` directory.
- Follow-up: None.

## 2026-08-17, SSH account why with raw-data ACL

- Scope: Linux user `why`; `scripts/setup_collaborator_access.sh`; `docs/technical/COLLABORATOR_ACCESS.md`; sshd `Match User why`.
- Reason: Collaborator needs to read experiment results and edit algorithms without opening original images, videos, or clinical source tables.
- Key changes: Public-key SSH only, no sudo, no forwarding. Named ACL denies `dataset/`, `data/`, `pipeline/data/`, raw artifact media, reader-study media, and sibling project trees. Write ACL on `scripts/`, `configs/`, and selected `pipeline/` code paths. Personal workspace under `_collab_workspaces/why/`.
- Validation: `sudo bash scripts/setup_collaborator_access.sh --verify --user why` checks read on reports, write on `scripts/`, and deny on raw/clinical paths.
- Deployment: Workstation only. First-login key stays in the owner `~/.secrets/` directory, not in git. Reload sshd after apply.
- Follow-up: Send the key off-repo. If they provide their own pubkey, replace `authorized_keys`. Re-run the setup script when a new raw-data directory is added.

## 2026-08-17, Manual account input and Chinese/English login aliases

- Scope: `reader-users.ts`, `LoginGate`, `DoctorAccountModal`, public `auth_server.mjs`.
- Reason: Account chips were extra friction. Chinese display names such as 管理员 / 医生1 should also accept the English usernames.
- Key changes: Login fields are typed by hand. Username matching accepts username, display name, reader label, `admin`/`管理员`, and `Doctor_01`/`医生1` style aliases.
- Validation: Next password login with `管理员` and `admin` both bind `admin`. `医生1` binds `Doctor_01`.
- Deployment: Workstation BUILD `rK5BFs0vAfzSpOUOIxijF`. Aliyun `auth_server.mjs` patched (previous `auth_server.mjs.bak_20260817_1237`).
- Follow-up: Hard refresh on LAN and public login pages.

## 2026-08-17, Account switch uses username plus password

- Scope: account API, `LoginGate`, `DoctorAccountModal`, header user menu.
- Reason: Password-only switch was easy to mix up after adding `admin` / `jmr` / `why` / `wzw`. Local logout also bounced back to admin, so the sign-out item was misleading.
- Key changes: Login accepts username plus password. The switcher lists reader identities. Local header hides sign-out and keeps switch-account.
- Validation: Username plus matching password logs in as that account. Mismatched username is 401. Local account GET without a cookie stays `admin`.
- Deployment: Workstation BUILD `3KF_5ugkdeVgTnRdfHowl` on `:3000` / `:3300`.
- Follow-up: Hard refresh on the LAN bookmark.

## 2026-08-17, Local workstation defaults to admin

- Scope: local auto-login, account GET, workstation sessions.
- Reason: LAN should open as `admin` even after a previous logout or leftover `zml` cookie.
- Key changes: Local account GET always binds the auto-login account when no session exists. Cleared workstation sessions. Auto-login password file stays on `admin`.
- Validation: `127.0.0.1:3000/api/reader/account` without a cookie returns `account_id=admin`.
- Deployment: Workstation BUILD `jtju8q-C8JaJHKStXCowX` on `:3000` / `:3300`.
- Follow-up: Hard refresh on the LAN bookmark.

## 2026-08-17, Add admin, jmr, why, wzw reader accounts

- Scope: `docs/clinical_validation/reader_study_v150/users.json`; workstation local auto-login pointer.
- Reason: Need an administrator identity plus three additional named accounts.
- Key changes: Added `admin` (管理员), `jmr`, `why`, and `wzw` with scrypt hashes. Previous `users.json` kept as timestamped `.bak_*`. Workstation local auto-login now binds `admin`.
- Validation: Workstation Next password login returns each new `account_id`. Aliyun `/api/login` and Aliyun Next `/api/reader/account` also accept the four accounts.
- Deployment: Merged the four accounts into Aliyun `/var/www/gastric-reader/users.json` (previous `users.json.bak_20260817_1026`, kept `hyj`). Copied the same file to Aliyun Next data. No service restart.
- Follow-up: On the LAN workbench, sign out once and refresh to pick up `admin`. Public login uses the same passwords. Give the three named accounts their passwords off-repo. Passwords were regenerated without hyphens.

## 2026-08-16, Next local identity plus public API session

- Scope: `client-doctor-session.ts` fetch patch, `LoginGate`, `DoctorAccountContext`.
- Reason: Local should open without a password but still bind the workstation account. Public assist and other `/api` calls must send the session; expired public sessions should return to the login page.
- Key changes: Same-origin `/api` fetches attach the session cookie and header. Local gate waits for silent auto-login, then enters the workbench. Public 401 (except account login) clears the client session.
- Validation: Localhost account GET stays `local_access: true` and auto-binds. Local `/api/patients` is 200. Public-style host `/api/patients` without a cookie stays 401.
- Deployment: Workstation BUILD `z3V5oQlhkBWKLBASzR1PE` on `:3000` / `:3300`.
- Follow-up: Hard refresh on LAN and public bookmarks.

## 2026-08-16, Local and LAN skip Next login again

- Scope: `LoginGate`, `proxy.ts`, `require-app-auth`, account GET auto-login, `lib/reader/local-access.ts`.
- Reason: Workstation LAN should open the workbench without a password. Public hosts still need login.
- Key changes: Loopback, RFC1918, and `LAN_FIXED_IP` skip the login page and API login check. Local account GET can auto-bind the workstation reader password again. Public sign-in still uses the 180-day cookie.
- Validation: Localhost account GET is `local_access: true` and auto-binds. Local `/api/patients` and `/api/agent/sam-interactive` without a cookie are 200. Public-style host stays `local_access: false`; `/api/patients` is 401 without a session.
- Deployment: Workstation BUILD `j5hJK-ttAbtytOIo1PYMg` on `:3000` / `:3300` (previous `standalone.bak_20260816_2249`).
- Follow-up: Hard refresh on the LAN bookmark.

## 2026-08-16, Next login required on LAN and public, long-lived session

- Scope: `apps/gastric_scan_next` login gate, doctor session cookie, API auth; public `auth_server.mjs` session default.
- Reason: Workstation LAN previously auto-logged in. Public already had a login gate, but the Next session was only 30 days in localStorage. Both entry points should require a password, then stay signed in for a long time in the same browser.
- Key changes: Removed GET auto-login. Full-page password gate. HttpOnly session cookie for 180 days with sliding renewal. Proxy blocks APIs without a session. Patient, case, media, and gold routes also check the session. Public auth cookie default is now 180 days.
- Validation: Cookie sign/verify smoke. Unauthenticated `/api/patients` is 401. Account GET without a cookie stays `authenticated: false` (no auto-login). Password login sets an HttpOnly cookie with Max-Age 180 days; the same cookie then loads `/api/patients` as 200. `:3000` home 200; `:3300` `/api/agent/contract` 200.
- Deployment: Workstation BUILD `qyeiplJohrEBpakuy-j7Z` on `:3000` / `:3300` (previous `standalone.bak_20260816_2113`). Public Aliyun still needs this Next build plus `auth_server.mjs` reload if that host should also keep the 180-day edge cookie.
- Follow-up: Hard refresh after login. Existing doctor session tokens remain valid until they expire or slide forward.

## 2026-08-16, Architecture PPT (6 slides, fewer boxes)

- Scope: 16:9 deck `pipeline/experiments/reports/lesion_region_retrain_phase0_20260816/Tstaging_architecture_16x9.pptx` (source `ppt_arch/build_deck.js`). Six slides: title, four encoder parts, image encoder, Clinical11, lesion two paths, status.
- Reason: The single 16:9 architecture figure had too many small boxes for a talk. Split by topic and keep 2-4 large blocks per slide.
- Validation: PptxGenJS overlap/bounds checks clean. Per-slide preview PNGs in `ppt_arch/rendered/`.
- Deployment: Offline slides only. Agent unchanged. Native384 still untrained.
- Follow-up: Train `tstaging_4class_lesion_region_native384_phase0_20260816.yaml` on the no-leak sidecar. Do not promote unless prospective patient ACC ≥ 0.85.

## 2026-08-16, Native-384 lesion-region residual and architecture note

- Scope: `DualBranchLesionRegionClassifier` now builds core/margin/exterior on the native mask then area-pools to 12x12 (`lesion_region_native`). Config `pipeline/configs/tstaging_4class_lesion_region_native384_phase0_20260816.yaml`. Write-up `pipeline/experiments/reports/lesion_region_retrain_phase0_20260816/NETWORK_ARCHITECTURE.md`.
- Reason: The FAIL run morph-ed on 12x12 with k=3, which collapses small lesions and washed the parent Dual ConvNeXt after only 3 frozen epochs.
- Validation: Synthetic disk (r=28 on 384): 12x12 k=3 has core∩margin = 2 cells and margin mass 12; native k=21 then area-pool has fractional masses core 0.65 / margin 4.36 / exterior 2.62. `lesion_region_native: false` keeps the old path.
- Deployment: Code and config only. Not trained yet. Agent unchanged.
- Follow-up: Train the native384 yaml on the same no-leak sidecar. Do not promote unless prospective patient ACC ≥ 0.85.

## 2026-08-16, Architecture figure: Clinical11 encoding and lesion-derived routing

- Scope: `pipeline/experiments/reports/lesion_region_retrain_phase0_20260816/architecture_diagram.html` and section 7.4–7.5 of `architecture_io.html`.
- Reason: The previous figure only said Clinical11. Need the per-field encoding (z-score vs code/max_code, missing flags) and how mask-derived morph / margin / wall proxies / sign points are routed (4ch vs FT vs TabFM).
- Validation: Encoding matches `clinical_master_utils.py` (`_apply_feature_contract`) and yaml `clinical_cols`. Lesion-derived groups match the typed-expert / featurepack routing used by the patient head.
- Deployment: Offline documentation. Agent unchanged.
- Follow-up: Figure is now 16:9 (1920×1080) with box-edge orthogonal arrows. PPT file: `pipeline/experiments/reports/lesion_region_retrain_phase0_20260816/architecture_diagram_16x9.png`.

## 2026-08-16, Frame-attention + TabFM max head and architecture SVG

- Scope: `scripts/run_frame_attn_tabfm_max_20260816.py`; report `pipeline/experiments/reports/frame_attn_tabfm_max_20260816/`; standalone figure `pipeline/experiments/reports/lesion_region_retrain_phase0_20260816/architecture_diagram.html`.
- Reason: Push patient ACC on frozen acc_boost2 512-D with gated-attention MIL, FT-Transformer, and frozen TabFM; replace the ASCII graph with one detailed SVG.
- Validation: TabFM loaded. Prospective n=425: fuse ACC 0.675 / balanced 0.610; image-only 0.668; MLP 0.645; oracle 0.788. Did not beat earlier Frame TF + TabFM 0.692 (n=413). External fuse 0.439.
- Deployment: Offline. Agent unchanged. Do not promote.
- Follow-up: Ceiling is still best-frame 0.79. Next capacity stays on deployable frame selection, not another unfreeze or TabFM-as-main-head.

## 2026-08-16, Lesion-region architecture HTML after FAIL

- Scope: rewrite `pipeline/experiments/reports/lesion_region_retrain_phase0_20260816/architecture_io.html` with I/O, this-run curves, and ranked next steps.
- Reason: The 60-epoch run finished at prospective patient ACC 0.678. The old HTML still said "not trained".
- Validation: Numbers from `training_history.csv` and `eval/test_prospective/test_results.json`. Sidecar counts rechecked (train 6921 / val 867 / T2 val 55).
- Deployment: Offline documentation. Agent unchanged.
- Follow-up: P0 is a frozen parent eval on the same no-leak official crop_ui sidecar. Do not start another unfreeze until that ceiling is measured.

## 2026-08-16, Lesion-region retrain finished (FAIL 0.85)

- Scope: 60-epoch DualBranch lesion-region run `tstaging_4class_lesion_region_retrain_phase0_20260816_20260816_150112` on official crop_ui sidecar, GPU 0.
- Reason: Unfreeze backbone plus core/margin/exterior pooling; no prospective leak in train/val.
- Validation: leak_guard pass. Early-stop epoch 48. Best val PatAcc 0.5606. Prospective 425-patient ACC 0.6776 (frame 0.6854, AUC 0.8211). Below 0.85 and below leaked acc_boost2 0.72.
- Deployment: Offline. Agent acc_boost2 unchanged.
- Follow-up: Do not promote. External held-out not scored in this job.

## 2026-08-16, Layer-wise LR and stronger margin head

- Scope: `DualBranchLesionRegionClassifier.margin_head` is now `ClassificationHead`; trainer param groups `backbone` / `head` / `region`; warmup scales each group; EMA vs raw uses the configured early-stop metric; optional `freeze_backbone_epochs`.
- Reason: A bare Linear margin head and one LR for the whole net would either stall the new modules or wash out the Phase 0 backbone.
- Validation: Import/forward smoke. Group LRs log at fit start. Not trained yet.
- Deployment: Offline. Agent unchanged.
- Follow-up: 60-epoch run still waits for go-ahead.

## 2026-08-16, Leak guard and pretrain fixes for lesion-region

- Scope: `pipeline/lib/leak_guard.py`; `run_experiment.py` enforces it; sidecar drops all `int/prospective` from train/val; val 4ch aug off; `_evaluate` now has frame balanced ACC and patient ACC; region gate init -4; mask resize nearest.
- Reason: Phase 0 train still contains prospective patients. A 0.85 gate is meaningless if that leak can come back. Val was also getting strong random 4ch aug, and early-stop ignored `balanced_accuracy`.
- Validation: Sidecar train 6921 / val 867, overlap 0. Guard passes on sidecar; on frozen Phase 0 it drops 953+37 then passes; with filtering off it raises. Model eval returns `(B,4)`, gate bias -4.
- Deployment: Offline. Do not start 60 epochs until asked. Agent unchanged.
- Follow-up: Train with the current yaml. Holdout remains `test_prospective` only.

## 2026-08-16, Lesion-region architecture I/O HTML

- Scope: `pipeline/experiments/reports/lesion_region_retrain_phase0_20260816/architecture_io.html`.
- Reason: Document the current DualBranchLesionRegionClassifier inputs, feature sizes, region pooling, outputs, and loss before any 60-epoch run.
- Validation: Cross-checked against `models.py`, `trainer.py`, `datasets.py`, and the 20260816 yaml / sidecar counts.
- Deployment: Offline documentation. Model not trained, Agent unchanged.
- Follow-up: Keep the HTML in sync if the class or sidecar policy changes.

## 2026-08-16, Official crop_ui sidecar for lesion-region retrain

- Scope: `pipeline/scripts/build_lesion_region_official_cropui_sidecar_20260816.py`; sidecar `pipeline/data/tstaging_4class_lesion_region_official_cropui_phase0_20260816/`; config `data_dir` retargeted. Frozen Phase 0 CSVs unchanged.
- Reason: Train/val CSV paths do not carry lesion masks or doctor ROI. Official GT masks match `crop_ui`, not the older Phase 0 RGB size. Phase 0 train also overlaps prospective patients.
- Key changes: Join via `patient_media_sample_index` suffix; 2019 queue to `DICOM{queue}`; 2024 keep `1-`/`2-` official prefix; if the freeze has no that frame, use Phase 0 RGB + UNet predicted mask/ROI; drop prospective-overlapping train/val patients.
- Validation: train 6961 (6785 GT + 176 UNet) / val 869 (821 + 48); only leak rows dropped; all three assets exist; 80/80 sampled image-mask sizes match; train/val vs prospective patient overlap 0.
- Deployment: Offline sidecar. Do not start the 60-epoch run until asked. Do not replace Agent acc_boost2.
- Follow-up: Train only after user go-ahead. Early-stop metric is still frame-level, not prospective patient ACC.

## 2026-08-16, Lesion-region DualBranch retrain (unfrozen)

- Scope: `DualBranchLesionRegionClassifier` in `pipeline/lib/models.py`; `pipeline/configs/tstaging_4class_lesion_region_retrain_phase0_20260816.yaml`; trainer optional `lambda_margin`.
- Reason: Spatial GT at train time is lesion only. Frozen heads cannot teach wall invasion. Retrain Dual ConvNeXt so the lesion mask pools core/margin/exterior on the feature map.
- Key changes: Warm-start Phase 0 acc_boost2; unfreeze backbones; gated residual from lesion-region tokens; margin-only CE. No lumen-derived wall band as label. Target is prospective patient ACC 0.85.
- Validation: Forward/load smoke only at commit time. Full train not yet a promotion candidate.
- Deployment: Offline. Do not replace Agent acc_boost2 until prospective patient ACC >= 0.85.
- Follow-up: Run `pipeline/run_experiment.py --config pipeline/configs/tstaging_4class_lesion_region_retrain_phase0_20260816.yaml`. External remains report-only.

## 2026-08-16, Dual Transformer + TabFM neural head

- Scope: `scripts/run_dual_transformer_tabfm_20260816.py`, report `pipeline/experiments/reports/dual_transformer_tabfm_20260816/`.
- Reason: Typed experts were small MLPs. The head should be a real neural net with a TabFM-level table tower.
- Key changes: Frame Transformer on frozen 512-D; missing-aware FT-Transformer on typed table cells; frozen TabFM ICL prior on size+wall; fusion Transformer over the three tokens; aux CE on image and table heads.
- Validation: Prospective n=413 ACC 0.692 / balanced ACC 0.630 (vs MLP experts 0.690 / 0.615 and DualBranch 0.678 / 0.618). Val ACC 0.547. External ACC 0.430. TabFM loaded.
- Deployment: Offline. Encoder and TabFM weights frozen. Do not replace Agent acc_boost2.
- Follow-up: Put remaining capacity into frame selection inside the image Transformer to move toward the 0.79 / 0.84 oracle.

## 2026-08-16, FrameGate-TypedExperts architecture

- Scope: `scripts/run_typed_expert_tstage_20260816.py`, report `pipeline/experiments/reports/typed_expert_tstage_20260816/`.
- Reason: A 0.9 ACC target cannot be reached by dumping all columns into one table head. Need frame-level MIL plus typed table experts with missingness gates.
- Key changes: Measured ceilings (unrestricted ExtraTrees train ACC 1.0 vs val 0.50; best-frame oracle val 0.84 / prospective 0.79 / external 0.68). Trained frozen-encoder attention/MIL + size/wall/clinical/sign experts.
- Validation: Attention+gate prospective ACC 0.690 (n=413) vs frame-mean 0.664 and original DualBranch patient 0.678. Val 0.53 vs oracle 0.84. External stays near 0.43; external oracle is 0.68.
- Deployment: Offline architecture probe. Do not replace Agent acc_boost2.
- Follow-up: Stage 2 frame-usability head to approach the oracle. Stage 3 unfreeze fusion only if Stage 2 moves val toward 0.84.

## 2026-08-16, TabFM head on frozen acc_boost2 image + doctor scores

- Scope: `scripts/extract_acc_boost2_image_features_20260816.py`, `scripts/run_tabfm_boost2_image_score_head_20260816.py`, report `pipeline/experiments/reports/tabfm_boost2_image_score_head_20260816/`, features `pipeline/data/acc_boost2_image_only_512_phase0_20260816/`.
- Reason: Replace the DualBranch MLP concat head with a table head. Image columns must come from the main acc_boost2 encoder (512-D cross-attention, clinical concat off), not ImageNet ConvNeXt. Encoder stays frozen.
- Key changes: Exported patient-mean 512-D on Phase 0 splits. PCA-16 fit on train only. TabFM and ExtraTrees on image PCA plus doctor scores. Permutation importance at feature and group level.
- Validation: External n=456. ExtraTrees image+scores ACC 0.482 / balanced ACC 0.431 vs frozen MLP head ACC 0.443 / 0.347. TabFM image+scores ACC 0.445; group importance shows TabFM uses acc_boost2 image PCs (0.107). Prospective imaging scores are sparse; image-only ExtraTrees ACC 0.563 vs MLP 0.583.
- Deployment: Offline probe only. Do not replace Agent acc_boost2. Next train step is a learned 512 to 8-16 map with the encoder still frozen.
- Follow-up: Stage 1 table-head training; keep scores detached; do not put clinical11 back into DualBranch.

## 2026-08-16, Neighborhood drag and faster brush paint

- Scope: `contour-edit.ts`, `ReaderViewer.tsx`, `InteractiveSegPanel.tsx`, `ReaderWorkbench.tsx`.
- Reason: Hard-pin drag only moved one vertex. Brush felt sticky because the reader reset the canvas every frame and paint preview stamped every stroke point.
- Key changes: Drag again soft-deforms a neighborhood around the grabbed handle. Brush paints add/subtract with a single stroke preview and commits on pointer up. Reader canvas size is set only when it changes.
- Validation: `test_contour_edit.mjs`, `test_mask_paint.mjs`. LAN `:3000` 200, `:3300` contract 200. Aliyun loopback `/` 200, `/reader` 307, first-round list 200, `/api/viewing-trace/events` 200.
- Deployment: Workstation BUILD `RXhDx5yo4kWQl-29eAMA3` on `:3000` / `:3300`. Aliyun READER_ONLY BUILD `V0dYEsIvkpWhraaSaGb-D`; previous kept as `*.bak_20260816_1404`.
- Follow-up: Hard refresh after login. Shift+brush subtracts. Wheel changes brush size.

## 2026-08-16, Small handles and hard-pin follow-hand drag

- Scope: `contour-edit.ts`, `ReaderViewer.tsx`, `InteractiveSegPanel.tsx`.
- Reason: Soft-deform grabbed a nearby dense vertex instead of the drawn handle, so the circle under the cursor did not follow. Solid 3.5-11 px handles also covered the boundary the doctor needs to judge.
- Key changes: Grab the visible control handle and pin that vertex to the cursor. Reader drag updates a live ref and commits on pointer up (no per-move React state). Handles are small translucent circles (about 2-3.6 px). Hit target stays larger than the drawn radius.
- Validation: `test_contour_edit.mjs`. LAN `:3000` 200, `:3300` contract 200. Aliyun loopback `/` 200, `/reader` 307, first-round list 200, `/api/viewing-trace/events` 200.
- Deployment: Workstation BUILD `_369EYZ1WvT6f0oPmCJF1` on `:3000` / `:3300`. Aliyun READER_ONLY BUILD `pXnosnPKcQm2CSmViPd8N`; previous kept as `*.bak_20260816_1353`.
- Follow-up: Hard refresh after login. Rollback is `server.js.bak_20260816_1353` plus `.next-public-deploy-dist.bak_20260816_1353`, then restart `gastric-next`.

## 2026-08-16, Aliyun reader-only UI for soft-follow drag and paint

- Scope: Aliyun `/var/www/gastric-next` reader-only bundle. Workstation `:3000` / `:3300` unchanged (`LxxTjAWhTS2wGkUD8MxjE`).
- Reason: Doctors see the Aliyun UI, not the workstation standalone. Soft-follow drag, lift-to-commit paint, and doctor-op audit were only on LAN until this swap.
- Key changes: Built `NEXT_PUBLIC_READER_ONLY=1 NEXT_DIST_DIR=.next-public-deploy-dist` (BUILD `5LfoZ-rLsCwD1qb_kyCzk`). Atomic swap of `.next-public-deploy-dist` and `server.js`. Previous kept as `*.bak_20260816_1026`. `.next` still points at the dist.
- Validation: Aliyun loopback `/` 200, `/reader` 307, first-round list 200 (`total=150`, 2 demo stills), `/api/viewing-trace/events` 200. Workstation `:3000` 200, `:3300` contract 200, compute tunnel active.
- Deployment: Aliyun `gastric-next` restarted after the swap. Hard refresh after login.
- Follow-up: Rollback is `server.js.bak_20260816_1026` plus `.next-public-deploy-dist.bak_20260816_1026`, then restart `gastric-next`.

## 2026-08-16, Soft-follow contour drag and lift-to-commit paint

- Scope: `contour-edit.ts`, `InteractiveSegPanel.tsx`.
- Reason: Drag still felt sticky because 拖胃腔/拖点 used hard single-vertex moves, and paint rasterized the mask on every pointer move. Undo also dropped the lumen.
- Key changes: Drag always soft-deforms a neighborhood and never inserts a spike vertex. Paint only commits on pointer up, with a live stamp preview. Lesion gets the same 涂增/涂减. Undo restores lesion, wall, and lumen.
- Validation: `test_contour_edit.mjs`, `test_mask_paint.mjs`. `:3000` 200, `:3300` contract 200.
- Deployment: Shared standalone BUILD `LxxTjAWhTS2wGkUD8MxjE`; restarted `:3000` / `:3300` together. Hard refresh if an old tab shows `Failed to load chunk`.
- Follow-up: None.

## 2026-08-16, Hierarchical TabFM early/late gate

- Scope: `scripts/run_tabfm_hierarchical_20260816.py`; report `pipeline/experiments/reports/tabfm_hierarchical_20260816/`.
- Reason: TabFM ICL is cell-level; sequence length is rows x columns. Prior 4-class runs had high T3+ AUC and weak T2. Test TabFM as P(T3+) on a short size table, with ExtraTrees T1/T2 and T3/T4 specialists.
- Key changes: Size-only 4-class TabFM; binary T3+ TabFM; soft and val-tuned hard hierarchy; optional mix of TabFM and Phase-0 acc_boost2 T3+ as the gate.
- Validation: External n=456. ExtraTrees size-only balanced ACC 0.464 beats TabFM 4-class 0.441 and soft hierarchy 0.442. Hard gate overfits (T2 recall 0.07). Prospective TabFM ACC 0.516 is T4-heavy (balanced ACC 0.356).
- Deployment: Offline only. Do not replace Agent `acc_boost2`. TabFM is a short-table T3+ scorer, not the 4-class product head.
- Follow-up: Keep ExtraTrees/FT as the table decision rule; keep acc_boost2 as the image expert.

## 2026-08-16, Dual-expert T-staging: frozen image + TabFM table

- Scope: `scripts/run_tabfm_dual_expert_20260816.py`; report `pipeline/experiments/reports/tabfm_dual_expert_20260816/`; figures `results/visualizations/tstage/tabfm_dual_expert_20260816/`.
- Reason: Stop stuffing ImageNet ConvNeXt PCA into TabFM. Treat TabFM as a table expert and fuse it with a frozen neural image expert.
- Key changes: DINOv3 layer-11 region scalars as a cheap image probe; Phase-0 acc_boost2 patient probabilities as the frozen DualBranch expert; TabFM / ExtraTrees on doctor scores + contour + safe clinical only; val-tuned DINO+TabFM mix; 0.5 and entropy gates for acc_boost2+TabFM.
- Validation: External n=268 table ExtraTrees balanced ACC 0.514, TabFM 0.486, DINO 0.418, Phase-0 acc_boost2 0.332. Entropy-gate ACC 0.537. Prospective 0.5 mix ACC 0.602 / balanced ACC 0.497 vs acc_boost2 0.583 / 0.462.
- Deployment: Offline report only. Does not replace Agent `acc_boost2`.
- Follow-up: Export acc_boost2 image-only 512-D fused features so the image expert does not also consume clinical11.

## 2026-08-16, Multi-model heads on size + image PCA + contour features

- Scope: `scripts/run_tabfm_feature_ensemble_20260816.py`; report `pipeline/experiments/reports/tabfm_feature_ensemble_20260816/`; figures `results/visualizations/tstage/tabfm_feature_ensemble_20260816/`.
- Reason: Continue tabular-head tuning without locking to TabFM; add morphology / margin / spiculation columns that complement size scores.
- Key changes: Join 8 contour columns (coverage ~0.94). Compare ExtraTrees, HistGB, LightGBM, XGBoost, LogReg, FT-Transformer, balanced-context TabFM, and train-OOF stacking on size+image, size+contour, and size+image+contour. Image encoder stays frozen.
- Validation: External n=268. FT on size+image+contour: ACC 0.612, balanced ACC 0.568, QWK 0.758 (contour lift vs size+image FT 0.470). TabFM is better without contour (0.547 vs 0.517). Stack+TabFM 0.552. Prospective still weak.
- Deployment: Offline report only. Does not replace Agent `acc_boost2`.
- Follow-up: Keep feature-specific models. Do not dump contour columns into TabFM. Next gain is still a T-staging image encoder.

## 2026-08-16, Follow-hand contour drag, adjustable paint, doctor-op audit

- Scope: `InteractiveSegPanel.tsx`, viewing-trace types/discretize/dock.
- Reason: Lesion/lumen drag lagged because draw read React state while move wrote refs; paint size was fixed; doctors did not want point-click or nnInteractive; every doctor action must be logged.
- Key changes: Draw and hit-test use live refs; pointer-down no longer setStates the contour; rAF-coalesced drag with clamped pointer; paint radius 6-48 via slider/wheel; removed 点选 and nnInteractive rails; `recordDoctorOp` writes viewing-trace plus mask-audit with `source: doctor`.
- Validation: `test_mask_paint.mjs`. Next build succeeded. `:3000` 200, `:3300` contract 200.
- Deployment: Shared standalone BUILD `B1siMehp5Jy0wmFepsQBU`; restarted `:3000` / `:3300` together. Hard refresh if an old tab shows `Failed to load chunk`.
- Follow-up: Confirm drag follows the pointer on a live keyframe; confirm paint/drag/tool/keyframe events appear in viewing-trace dock.

## 2026-08-16, Local LabelMe/Slicer lumen sculpt tools

- Scope: `lib/human-assist/mask-paint.ts`, `InteractiveSegPanel.tsx`.
- Reason: Lumen refine only had box drag and an nnInteractive submenu. Doctors asked for LabelMe/Slicer point and paint add/subtract.
- Key changes: Always-visible lumen tools: point +, point -, paint +, paint -, polygon. Local mask stamp/stroke, no model call. nnInteractive refine stays as optional AI assist.
- Validation: `test_mask_paint.mjs`. `:3000` 200, `:3300` contract 200.
- Deployment: Shared standalone BUILD `P0dV1apAEb3A1cIrqVuHg`; restarted `:3000` / `:3300` together. Hard refresh if an old tab shows `Failed to load chunk`.
- Follow-up: None.

## 2026-08-16, Keep keyframes full-frame and allow 10 marks

- Scope: `doctor-keyframes.ts`, `InteractiveSegPanel.tsx`, analyze route.
- Reason: Opening a keyframe auto-zoomed to the serosa ROI; doctors asked to stay on the full frame and mark up to 10 frames.
- Key changes: Opening a keyframe no longer sets `viewFocusBox`. Mark/analyze cap is 10. Manual Zoom ROI remains available.
- Validation: `test_doctor_keyframes.mjs`. `:3000` 200, `:3300` contract 200.
- Deployment: Shared standalone BUILD `Tbr6ZW2H-oalPK-R0ftt6`; restarted `:3000` / `:3300` together. Hard refresh if an old tab shows `Failed to load chunk`.
- Follow-up: None.

## 2026-08-16, Analyze doctor keyframes with per-frame masks

- Scope: `doctor-keyframes.ts`, `InteractiveSegPanel.tsx`, `ReaderWorkbench.tsx`, analyze route, `case_input.py`, `pipeline_steps.py`.
- Reason: Product analyze still sent only the open keyframe, so quality-weighted fusion never ran. Remaining-wall bonuses stay off.
- Key changes: Collect up to 4 doctor keyframes that already have lesion + lumen. Each frame carries its own contour. Fast profile no longer drops extra keyframes. Classify uses that frame's mask/ROI, then `quality_weighted_mean` (refined 1.0, propagated 0.85, preseg 0.7).
- Validation: `test_doctor_keyframes.mjs`; `test_multiframe_keyframe_input.py`; `test_research_stage_gate.py` (8 passed). `:3000` 200, `:3300` contract 200.
- Deployment: Shared standalone BUILD `60xRMkCRWT91VEHNGs56C`; restarted `:3000` / `:3300` together. Python classify path is live on the next analyze.
- Follow-up: Compare CASE-015/024/029 single-frame vs 2-4 keyframe fusion after a doctor marks multiple frames. Do not treat this as proven ACC gain until that check.

## 2026-08-16, TabFM balanced-context optimization on frozen image + scores

- Scope: `scripts/run_tabfm_image_score_head_opt_20260816.py`; report `pipeline/experiments/reports/tabfm_image_score_head_opt_20260816/`; figures `results/visualizations/tstage/tabfm_image_score_head_opt_20260816/`.
- Reason: Official TabFM v1.0.0 never predicted T2 (external recall 0) and ignored image PCA under random 256-row context.
- Key changes: Class-balanced in-context table (80 patients per T class), val-tuned class bias, ExtraTrees blend, compact size+8PC features, FT/MLP 500 epochs / patience 80. Image encoder stays frozen.
- Validation: External complete-case n=268. Balanced-context TabFM: ACC 0.515, balanced ACC 0.547, QWK 0.681, AUC(T3+) 0.935, T2 recall 0.54 (was 0.00). Beats ExtraTrees 0.510 and this-seed FT 0.528. Val bias / blend overfit val and lost external. Prospective still weak (FT 0.372, TabFM 0.331).
- Deployment: Offline report only. Does not replace Agent `acc_boost2`.
- Follow-up: Do not promote. Next lever is still a T-staging image encoder, not more TabFM calibration.

## 2026-08-16, Restore original round contour drag handles

- Scope: `InteractiveSegPanel.tsx`, `ReaderViewer.tsx`.
- Reason: 8/10 made handles tiny, semi-transparent pinpoints (and square lumen corners). Doctors asked to keep the original round drag points.
- Key changes: Restore direction_demo handle radius (`7.5/√scale`, 3.5–11), solid cyan/orange/fuchsia fill, white 1.5 stroke, gold when active. Lumen box corners are circles again. Edit hit targets and control-point counts are unchanged.
- Validation: Build succeeded. `:3000` 200, `:3300` contract 200. Handle radius string present in standalone chunk.
- Deployment: Shared standalone BUILD `LlZWg8aFx56B003UIGb-r`; restarted `:3000` / `:3300` together. Hard refresh if an old tab shows `Failed to load chunk`.
- Follow-up: None.

## 2026-08-15, Cap research T4+ without explicit serosa evidence

- Scope: `pipeline/agent/product/analyze_case.py`; lumen preseg prompt in `doctor-keyframe-preseg.ts`.
- Reason: After the display gate, research `recommended_t_stage` could still keep frozen ConvNeXt T4+ (CASE-029 0.79) and RAG could add to T3/T4+ on proxy wall.
- Key changes: `ResearchGate` drops T4+ from recommended unless serosa/adjacent-organ text is explicit, falling back to classifier top-2 among T1–T3. Similar-case votes no longer increment T3/T4+ while wall/serosa is proxy. Keyframe lumen prompt is `anechoic gastric cavity` (needs Next rebuild).
- Validation: `test_research_stage_gate.py` 5 passed. Live analyze: 015 T3, 024 T2, 029 recommended T3 (classifier still T4+). Doctor-visible stage empty; P6 scorer pass.
- Deployment: Python Agent is live on the next analyze call. Lumen prompt is source-only until `:3000` / `:3300` rebuild.
- Follow-up: 015/029 research tendency is still late vs pathology. Next lever remains remaining outer-wall / multi-keyframe, not more geometry bonuses.

## 2026-08-15, Backend retest after keyframe-flow deploy

- Scope: Agent unit tests, P2 empty-propagate, P5 audit probes, P6 three-case analyze on `:3000`.
- Reason: `/tmp` SAM contours were gone; need a live check on the rebuilt standalone, and persist contours under `p6_artifacts`.
- Key changes: Gate script prefers `p6_artifacts` and skips empty lumen overrides. Lumen prompt that worked tonight is `anechoic gastric cavity`.
- Validation: 30 Agent tests pass; keyframe/display-stage tests pass; empty `target_times_sec` 400; research audit 401; staging audit 200. Analyze HTTP 200 for CASE-015/024/029; doctor-visible stage empty; P6 scorer pass. Research top-1: 015 T3 0.69, 024 T2 0.99, 029 T4+ 0.79.
- Deployment: No new rebuild. Contours now live in `docs/plans/ws_round2_20260815/p6_artifacts/*_sam_*.json`.
- Follow-up: CASE-029 research flip (T3 earlier, T4+ now) is still the frozen classifier; do not put it on the doctor card.

## 2026-08-16, Official TabFM v1.0.0 on frozen image + doctor-score table

- Scope: `scripts/run_tabfm_image_score_head_20260815.py` (no `--skip-tabfm`); report `pipeline/experiments/reports/tabfm_image_score_head_20260815/`; figures `results/visualizations/tstage/tabfm_image_score_head_20260815/`.
- Reason: Finish head F after the 6.56 GB classification checkpoint finished downloading.
- Key changes: Local checkpoint at `GIST/.hf_cache/tabfm_local` (SHA256 `928cb350…2085`). TabFM v1.0.0 in-context, 8 estimators, max 256 context rows, `cuda:0`. No image-encoder retrain. Weights are non-commercial academic license.
- Validation: External complete-case n=268, `image_plus_score`: TabFM ACC 0.534 / balanced ACC 0.481 / QWK 0.647 / AUC(T3+) 0.929 / T2 recall 0.00. ExtraTrees still leads balanced ACC (0.497). TabFM never predicts T2; permutation importance is size_scores 0.213 and image_pca ~0.
- Deployment: Offline report only. Does not replace Agent `acc_boost2`.
- Follow-up: Do not promote TabFM. If a later pass needs a single table vs the 500-epoch FT (balanced ACC 0.556), re-run with `--mlp-epochs 500 --mlp-patience 80`; TabFM numbers will stay the same.

## 2026-08-15, Frozen image + doctor-score tabular heads (TabFM pending)

- Scope: `scripts/run_tabfm_image_score_head_20260815.py`; report `pipeline/experiments/reports/tabfm_image_score_head_20260815/`; figures `results/visualizations/tstage/tabfm_image_score_head_20260815/`.
- Reason: Replace the MLP concat classification head with a tabular model on frozen columns, without retraining the image encoder.
- Key changes: Patient-mean ImageNet ConvNeXt embeddings, train-only PCA (32-D), joined to featurepack v2 doctor scores. Compared ResidualMLP concat, ExtraTrees, HistGB, in-repo FT-Transformer, and `cT_hybrid`. Official Google TabFM v1.0.0 (6.56 GB, non-commercial) is installed as a library; checkpoint download is still running, so head F was skipped this pass.
- Validation: Continued training (500 epochs, patience 80). External complete-case n=268: FT-Transformer balanced acc 0.556 (was 0.476), ExtraTrees 0.497, HistGB 0.485, ResidualMLP 0.377. Size-score group dominates permutation importance.
- Deployment: Offline report only. Does not replace Agent `acc_boost2`. Re-run without `--skip-tabfm` after the TabFM safetensors file is complete.
- Follow-up: Done 2026-08-16; see the TabFM v1.0.0 entry above.

## 2026-08-15, Keyframe-to-keyframe flow propagate and open-only overlay

- Scope: SAM3.1 `video-propagate` keyframe path; Next InteractiveSegPanel / ReaderWorkbench / doctor keyframe strip.
- Reason: Doctors were re-editing the same lesion on every keyframe, and pre-seg overlays appeared while the cine was still playing.
- Key changes: When `target_times_sec` is set, SAM3.1 walks Farneback flow + SAM box memory only to those frames (seed contour preferred). UI auto-propagates to later unrefined keyframes after the first refined frame, or via 「传到其他关键帧」. Overlays persist on the keyframe record but draw only when that keyframe is opened (paused and on time). Full-clip track stays under 「更多」.
- Validation: `test_doctor_keyframes.mjs` covers open-gate, later-unrefined, and apply-hits. Declared empty `target_times_sec` is 400 on SAM3.1 and the Next proxy (no silent full-clip).
- Deployment: Restarted `gastric-sam31.service`. Rebuilt shared standalone BUILD `d-S1aP9SdCSogQJz3BEa2` and restarted `:3000` / `:3300` together. Did not rsync Aliyun.
- Validation (API, CASE-015 clip_01): seed t=2.0s → targets 3.5s / 5.0s returned `propagation_mode=keyframe_optical_flow`, accepted_frames=2 (not the 161-frame clip). Same through `:3000/api/agent/video/propagate`. Empty `target_times_sec` is 400.
- Follow-up: Old browser tabs can still show a stale-chunk error until hard refresh (`?v=BUILD` recovered the workbench). Full doctor refine-then-propagate still needs a hand click. Do not treat copy-contour fallback as optical flow in audit write-ups.

## 2026-08-15, Fix 0-1 contour rasterization so analyze sees a real lesion

- Scope: Agent mask/lumen rasterizers, T-staging L0 triage, clinical-decision text, fusion late-stage lifts.
- Reason: SAM / UI contours are unit-square. `int(0.45)` collapsed lesion and lumen to a 2x2 crop, so classify ran on noise. T-staging requests without `cohort_phase` also let L0 skip to benign. Size/irregularity heuristics could still add T3/T4 when wall evidence was proxy-only.
- Key changes: `polygon_to_pixel_points` scales 0-1 (and source-size mismatch) before `fillPoly`; reject 2x2 ROI boxes; `study_mode=t_staging` / `reader_v150` forces soft triage; clinical decision uses `assist_display_stage`; morphology/clinical/report cues cannot upgrade T3/T4 without confirmed wall/serosa.
- Validation: wall/clinical-decision/sign tests pass; three-case analyze HTTP 200. After the fix, lesion area ratio is about 0.03 (was 1e-6). CASE-024 classifier T2 0.98; CASE-015 still T3 0.48; CASE-029 T3 0.60 (no longer L0 benign skip). P6 doctor-visible stage remains empty.
- Deployment: Python Agent is live on the next analyze call. Next `study_mode` field in the analyze route still needs a `:3000` / `:3300` rebuild to appear in standalone; backend replay already sends `cohort_phase=reader_v150`.
- Follow-up: Remaining error is the frozen ConvNeXt overstaging early cases, not the display gate. Next accuracy lever is remaining outer-wall / multi-keyframe evidence, not more geometry bonuses.

## 2026-08-15, Round-2 backend gate retest and recommendation filter

- Scope: `assist-display-stage.ts` doctor-facing recommendation / benign_skip hide; local analyze replay for CASE-015 / 024 / 029; propagate and audit probes.
- Reason: Live analyze still wrote "暂倾向 T3 / T4+ / benign" under clinical decision while the stage card was empty. CASE-029 also flipped between T4+ and L0 benign on the same mid-frame.
- Key changes: `doctorSafeRecommendation` drops stage-claim prose when display stage is empty; `benign_skip_t` is not a doctor-facing stage. Scripts: `scripts/run_round2_backend_gate_20260815.py`, `apps/gastric_scan_next/scripts/score_p6_analyze_json.mjs`.
- Validation: `test_assist_display_stage.mjs` pass; three-case analyze HTTP 200; scorer pass; empty `target_times_sec` 400; research audit 401; staging audit 200.
- Deployment: Source only. LAN `:3000` standalone not rebuilt in this step, so the running UI can still show raw recommendation text until the next rebuild.
- Follow-up: Rebuild `:3000` and `:3300` together if this filter should be live; UI hand-click of CASE-029 / 024 still open.

## 2026-08-15, Stop stale Next HTML after rebuild (Mac client exception)

- Scope: `apps/gastric_scan_next/next.config.ts`, `app/global-error.tsx`; LAN `:3000` and public `:3300`.
- Reason: After today's BUILD_ID change, Mac browsers kept old HTML/RSC and failed JS chunks. Next showed `Application error: a client-side exception has occurred while loading 10.13.199.162`.
- Key changes: HTML/RSC `Cache-Control: no-store`; global-error asks for a hard refresh. Restarted both Next units on BUILD `1vkUyD1nEI2-nBTMjhM9z`.
- Validation: LAN `/` 200 with `no-store`; sample chunk 200; `:3300` `/` 200.
- Deployment: Workstation only. Mac should hard-refresh `http://10.13.199.162:3000/`.

## 2026-08-15, Fix public :3300 after shared-standalone rebuild

- Scope: workstation `gastric-next-public.service` (`:3300`). Same standalone dir as LAN `:3000`.
- Reason: Today's LAN-only restart left the 8/14 public process on overwritten files. Static chunks 404; Next logged `Invariant: Expected clientReferenceManifest to be defined`.
- Key changes: Restarted `gastric-next-public.service` so `:3300` loads BUILD `p01HHrOViW_MINr4DixYl`. Did not rsync Aliyun reader-only UI.
- Validation: `:3300` `/` 200, `/api/agent/contract` 200, sample `/_next/static/chunks/*.js` 200 (was 404).
- Deployment: Public compute edge now matches LAN standalone. Hard refresh if a tab still caches the old manifest.
- Follow-up: Future rebuilds must restart both `:3000` and `:3300`, or use separate standalone dirs.

## 2026-08-15, LAN Next redeploy of P1–P5 (no public update)

- Scope: `apps/gastric_scan_next` production standalone on workstation `:3000`; systemd drop-in `gastric-next.service.d/round2-freeze.conf`; docs under `docs/plans/ws_round2_20260815/`.
- Reason: Put today's Reader gates on the LAN workbench without touching the public edge worker.
- Key changes: `npm run build`, copy `.next/static` into standalone, restart `gastric-next.service` only. Did not restart `gastric-next-public.service` (`:3300`).
- Validation: LAN `/` HTTP 200; empty `target_times_sec` → 400; staging audit walk persisted P5 fields; research audit correctly 401 without proxy identity.
- Deployment: LAN only. Public process still running on the previous in-memory build.
- Follow-up: UI hand-check of CASE-015/024/029 after login; do not invite experts until the section-7 checklist is complete.

## 2026-08-15, Round-2 P6 early-case display gate (CASE-015/024/029)

- Scope: `docs/plans/ws_round2_20260815/P6_gate_log.md`, `docs/plans/ws_round2_20260815/p6_artifacts/`.
- Reason: Open-reading hard gate: early pathology cases must not show doctor-facing T4.
- Key changes: Mid-frame SAM3.1 + reader analyze on three gate cases; doctor-visible stage empty on all three (CASE-029 research tendency T4+ suppressed). Not a full UI keyframe hand-click; production Next not yet redeployed with today's P1–P5.
- Validation: Analyze HTTP 200 for all three; `assist_display_stage` null; no forbidden contour phrases; `test_assist_display_stage.mjs` still passes.
- Deployment: Gate log only; do not invite experts until UI redeploy + checklist complete.
- Follow-up: Rebuild/redeploy Next with P1–P5, then one research UI hand-check of the same three cases.

## 2026-08-15, Round-2 offline track T0/T1/T2 + D1/D2/D3

- Scope: `docs/plans/ws_round2_20260815/` (T0 freeze, D1 map, D2 status, D3 gaps); `scripts/build_reader_v150_case_to_patient_20260815.py`; `scripts/run_tabfm_vs_mlp_20260815.py`; report dir `pipeline/experiments/reports/tabfm_vs_mlp_20260815/`.
- Reason: Freeze featurepack columns without supervised-v1 `model_selection.json`, map reader v150 cases to patients without guessing, compare cT_hybrid vs RF/ExtraTrees/LogReg vs HistGB on the same patient table.
- Key changes: No TabFM (not installed); no image-encoder retrain; clinical/anatomic join recorded but C/D features degraded to featurepack-only due to low train coverage; head E (frame MLP) skipped; D2 not run (no 150-case frozen replay).
- Validation: Both scripts executed successfully; outputs include `SUMMARY.md`, `metrics_by_split.csv`, `importance.csv`, `predictions.csv`, `confusion_external.csv`, `case_to_patient.csv`.
- Deployment: Analysis artifacts only; no git commit per request.
- Follow-up: Raise D1 path coverage for `clip_01` cases; run D2 only after frozen keyframe weights + mapped patients exist.

## 2026-08-15, Round-2 Reader product track P1–P5

- Scope: `apps/gastric_scan_next` Reader path (`ReaderWorkbench`, `ReaderToolbar`, `ReaderHelpModal`, `ReaderReportPanel`, `ReaderEvidencePanel`, `sam-client`, video propagate API, `lib/reader/active-time.ts`).
- Reason: Second-round pre-open product gates: demote full-clip track, keyframe-to-keyframe propagate, doctor-facing copy, report timing, research audit metrics.
- Key changes: Full-clip track labeled slow/optional under More; main-path “传到其他关键帧”; `target_times_sec` on propagate API (empty → 400); report gated on doctor T + serosa ticks with stale hint; `based_on_uncorrected_mask` marking; research active-time / keyframe / confidence audit fields. Did not overwrite human_assist_v2/v3 HTML.
- Validation: `node scripts/test_doctor_keyframes.mjs`, `node scripts/test_assist_display_stage.mjs`, `npx tsc --noEmit`.
- Deployment: App code only; no commit per request.
- Follow-up: Optional video-propagate path for keyframe targets still unused (copy-contour is the primary path). ReaderStudyQueuePanel metrics naming (`doctor_active_reading_sec`) not unified with Workbench (`doctor_active_sec`).

## 2026-08-15, T-score algorithm HTML white lesion figures

- Scope: `scripts/build_gc_us_tscore_algorithm_html_20260815.py`; page `results/visualizations/tstage/tscore_algorithms_20260815/`.
- Reason: The first catalog used black abstract schematics. The smoothness formulas need a real-lesion pair, and the HTML pack needs to be openable on the Mac.
- Key changes: White-background Times figures. Figure S compares a smoother versus a more irregular held-out mask and renders \(R\), \(S\), and \(C\). Figures 1-5 use real crops for NRL, the soft band, lumen-box growth, wall v2 remain, and an outward-normal profile. No patient IDs on the page.
- Validation: Rebuilds HTML and PNGs only. Does not rescore the pack or change lean inputs.
- Deployment: Analysis only. Zip sent to the Mac via Tailscale file copy, not a full-repo sync.
- Follow-up: If `spic_index_v2` or AEOW later enter the pack, update this page from the same script.

## 2026-08-15, T-score algorithm catalog HTML

- Scope: `scripts/build_gc_us_tscore_algorithm_html_20260815.py`; page `results/visualizations/tstage/tscore_algorithms_20260815/index.html`.
- Reason: The current pack mixes clinical size, mask shape, borrowed CAD, and wall proxies. The formulas need one place that states what each algorithm actually computes.
- Key changes: Detailed write-up of NRL primitives, morphology, soft-band NRG, lumen SDF growth, wall depth / v2 remain, multi-frame frac_high, the shallow ordinal head, and pixel-gated spiculation. Borrowed BoF / needle-like / spic_robust are labeled as weaker constructs. Product rubric cuts are not rewritten.
- Validation: Rebuilds schematic figures and HTML only. Does not rescore the pack or change lean inputs.
- Deployment: Analysis only. Open the HTML locally.
- Follow-up: If `spic_index_v2` or AEOW later enter the pack, update this page from the same script.

## 2026-08-15, Spiculation reviewer PDFs completed

- Scope: five title-checked PDFs under `docs/references/related_literature/articles/`; status in `spiculation_reviewer_refs_20260815.md` and `REVIEW_CORPUS.md`.
- Reason: PMC raw PDF URLs and Unpaywall publisher blobs had returned captcha pages or the wrong papers.
- Key changes: Opened article HTML first, then fetched the PDF in the same browser session. Zhang 2021 DOI `10.21037/gs-21-328` is the Inception V3 / ABUS paper; needle-like FFT is in the methods, not the title.
- Validation: `pdftotext` page 1 matched the expected title words for all five files. Files were not taken from Unpaywall `rcastoragev2` blobs.
- Deployment: Analysis only. Zotero collection `GastricTstaging-review`, tag `spiculation-reviewer`.
- Follow-up: Do not re-fetch these five from raw PMC PDF URLs. Cite them only for what they measured.

## 2026-08-15, Spiculation reviewer literature set

- Scope: `docs/references/related_literature/spiculation_reviewer_refs_20260815.md`; new keys in `fetch_review_corpus.py`; reviewer HTML section 7.
- Reason: The current spiculation score borrows lung-CT / mammography / ABUS CAD. Gastric US/EUS papers define a different object: outer-wall or serosal-line irregularity.
- Key changes: Split the reading list into gastric outer-edge papers versus borrowed CAD. Do not cite Ciompi/Kilday/Zhang as gastric T-stage evidence.
- Validation: Title-checked PDFs now on disk for Han, Qiu, Oncol Lett, BMC Cancer, Ciompi, Huang, Kilday, Rangayyan. IEEE needs the Crossref `arnumber` (Ciompi 6960901, Huang 1256432). Unpaywall publisher blobs for WJG/WJGS returned the wrong papers and were deleted. The remaining five were filled in the following changelog entry.
- Deployment: Analysis only. Zotero collection `GastricTstaging-review`, tag `spiculation-reviewer`.
- Follow-up: Download remaining WJG/IEEE PDFs on campus if needed. Do not treat the list as a related-work draft.

## 2026-08-15, Spiculation reviewer HTML (failure-first)

- Scope: `scripts/build_gc_us_spicule_reviewer_html_20260815.py`; page `results/visualizations/tstage/spicule_reviewer_20260815/review.html`.
- Reason: The pixel-gated index and the pack robust score are different objects; image-evidence and true-count terms do not carry the T signal. A paper-style gallery would overclaim.
- Key changes: Internal reviewer board with US and method objections, the association numbers that fail (T3+ AUC 0.52, evidence rho 0.04), and eight held-out-first cases chosen by score extremes rather than appearance.
- Validation: Rebuilds from the 2026-08-15 patient table. Does not rescore the cohort or change the product rubric.
- Deployment: Analysis only. Open the HTML locally.
- Follow-up: Do not treat this page as clinical validation. Next bar is a spiculation reader label, serosal-side scoring, and test-retest, not another Spearman.

## 2026-08-15, Pixel-gated boundary spiculation vs T

- Scope: `scripts/viz_gc_us_boundary_spicule_assoc_20260815.py`; figures `results/visualizations/tstage/boundary_spicule_assoc_20260815/`; report `pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/boundary_spicule_assoc_20260815/`.
- Reason: Check whether lesion-margin spiculation, gated by outward-normal pixel evidence rather than mask staircasing, associates with pathologic T after contour coverage.
- Key changes: One largest-mask frame per pack patient (n=2049). Contour color is angular SNR. Red circle = pixel-supported spicule; white X = artifact. Association table plus a later-training gate (overall |rho|>=0.15, same sign on train, held-out |rho|>=0.10, partial vs length keeps sign).
- Validation: `spic_index_v2` rho=0.189 (ext 0.204, prosp 0.156, partial 0.189), gate ENTER. Pack features `margin_spic_robust` (0.262) and `margin_shape_solidity` (-0.267) also ENTER. Artifact-peak count is unrelated (rho=-0.012).
- Deployment: Analysis only. Does not change the product rubric or retrain the shallow head yet.
- Follow-up: Add `spic_index_v2` / smoothness as a lean-head candidate on the next rescore; keep wall proxies out.

## 2026-08-14, Fill T-score contour coverage then rescore

- Scope: `scripts/build_gc_us_tscore_coverage_manifest_v1.py`, `scripts/build_gc_us_tscore_anatomic_coverage_tables_v1.py`, `scripts/predict_gc_us_external_lesion_masks_coverage_v1.py`; staging `pipeline/data/gc_us_tscore_features_v1/anatomic_coverage_v1/`; masks `lesion_pred_masks_coverage_v1/`; report `shallow_ordinal_v1_post_coverage/`.
- Reason: Shallow heads were diluted by missing contours (prospective 83%, external 63%), not by network depth.
- Key changes: Prospective switched to `prospective_full` (254/254 masks). External kept Phase0 masks and filled 1594/1661 pending frames with frozen UNet ConvNeXt fulldata (empty-mask rate 4.0%, gate pass). Morph coverage: prospective 42→254, external 170→452. Holdout still excluded. Lean still excludes wall proxies.
- Validation: Post-coverage `hybrid_ridge` prospective PLCC 0.041→0.199; external lean QWK no longer collapsed (ridge_lean 0.415→0.468). `ridge_size` remains strongest full-external ACC/QWK (0.480 / 0.522).
- Deployment: Analysis only. Does not change product rubric or L1 acc_boost2.
- Follow-up: Optional lumen boxes for growth/wall on the new external frames. Do not select models on external.

## 2026-08-14, Shallow ordinal T-score head on frozen features

- Scope: `scripts/train_gc_us_tscore_shallow_ordinal_v1.py`; report `pipeline/experiments/reports/gc_us_tscore_feature_stats_v1/shallow_ordinal_v1/`.
- Reason: Map existing patient-level size / lean features into a continuous T-score, then cut to T1-T4+, instead of another four-class softmax.
- Key changes: Train-only fit of Ridge, balanced logistic, and a 16-unit MLP. Val selects the head. Wall proxies stay out. Imaging-missing cases fall back to length / thickness / CEA. Main table is ACC, adjacent ACC, PLCC, and quadratic weighted kappa.
- Validation: Uses the frozen feature-pack splits (train / val / prospective / external / holdout). Does not retune on external.
- Deployment: Analysis only. Does not change the product rubric or the L1 acc_boost2 checkpoint.
- Follow-up: Coverage fill landed the same day (`shallow_ordinal_v1_post_coverage`). Keep size-only as the full-cohort external main report; lean/hybrid as contour-aware secondary.

## 2026-08-14, Static distal-wall dashed line (no T)

- Scope: `scripts/gc_us_wall_dash.py`, `scripts/viz_static_wall_dash_6cases_20260814.py`, `results/visualizations/tstage/static_wall_dash_6cases_20260814/`.
- Reason: Doctors asked to continue the outer wall from farther away and see where it meets the lesion. Auto T from remain already failed; this pack only shows the line.
- Key changes: Search the layered wall on the four sides of the lesion; prefer the side above (near the probe). Do not treat the lumen blob as the wall. Dash that ridge across the lesion. Review HTML can redraw. Remain and intersect only. No T.
- Validation: Regenerates the same six pedagogical stills. Open `review.html` locally.
- Deployment: Analysis only. Not wired into Round-2 doctor scoring.
- Follow-up: Collect ticks on these six plus more stills where the distal wall is visible. Do not emit T from the line.

## 2026-08-14, Dual-readout min/max remain on the six cases

- Scope: `scripts/viz_cine_min_remain_6cases_20260814.py`, `results/visualizations/tstage/cine_min_remain_6cases_20260814/`.
- Reason: A single still missed T3 when residual wall was still visible; blindly taking min remain overstaged T1.
- Key changes: Score all valid stills per case. Patient lean uses intact max-remain and nadir min-remain plus length. Native SAM3.1 cine hit GPU OOM; optical-flow frames almost never passed the AEOW gate.
- Validation: Single-still 3/6, dual-readout 4/6. Case E flips T1→T3 correctly. Case A stays T1. Hard T2 cases B and C still overstage.
- Deployment: Analysis only.
- Follow-up: Free GPU and re-track one clip per case with scaled seed boxes; do not use min-remain alone.

## 2026-08-14, Six-case static lesion-assist plate

- Scope: `scripts/viz_static_lesion_assist_6cases_20260814.py`, `results/visualizations/tstage/static_lesion_assist_6cases_20260814/`.
- Reason: Need a doctor-checkable T lean on existing lesion + lumen, not a four-class softmax and not a synthetic-serosa 70-140 px stick.
- Key changes: Pick six stills (T1 / typical T2 / hard T2 / typical T3 / hard T3 / T4+). Adjacent thickness is the 8-48 px echo band next to the lesion. Remain is residual wall at deepest contact. Lean is T1 / T2 / T3+; geometry never emits T4.
- Validation: Plate 3/6 match on this pedagogical set. Case A and typical T3 / T4+ work. Hard T2 (remain ~1 px) and hard T3 (remain still 17 px) show the still is often not the nadir frame.
- Deployment: Analysis only. No product gate change.
- Follow-up: Same two calipers on the cine frame with minimum remain, then re-score T2 vs T3.

## 2026-08-14, Open cases on the workbench, not /reader

- Scope: `buildReaderAppUrl`, `proxy.ts`, Header / AssistHub / ReaderAgentResultCard, `/reader` page, public auth login entry.
- Reason: Opening a case jumped to `/reader`. Physicians should stay on the main workbench.
- Key changes: Open links now use `/?case_id=` on LAN and `/workbench/?case_id=` on the public mount. `/reader` redirects to the workbench and keeps the case id. Login default is `/workbench/`, not `/workbench/reader`. Button copy says 打开工作台.
- Validation: `node --experimental-strip-types scripts/test_workbench_url.mjs`. LAN `:3000` `/` 200, `/reader` 307 to `/?case_id=`. Aliyun auth `/workbench/reader` 302 to `/workbench/`. First-round `total=150`. Compute tunnel contract 200.
- Deployment: Workstation BUILD `ILMjZ4s2xODKqnI4S-y2d` on `:3000` / `:3300` (previous `standalone.bak_20260814_1308`). Aliyun READER_ONLY BUILD `ZrCLhq70_0f0Ry7Q1Xgla` (previous `server.js.bak_20260814_1308`). Public auth backups `workbench_login.html.bak_20260814_1305` and `auth_server.mjs.bak_20260814_1305`. Hard refresh after login.
- Follow-up: Clinical click-through.

## 2026-08-14, Show gold next to assist 5-class

- Scope: `CaseGoldReveal`, cine toolbar, `ReaderEvidencePanel`, header, GC-US panel.
- Reason: The first gold control sat in a truncated subtitle, so physicians could not see it. They asked to show gold next to the assist label.
- Key changes: Gold button sits on the case-title row. Assist 5-class card has a sibling pathology-gold card. Header control moved to the right cluster. Still closed until 查看真值.
- Validation: LAN `:3000` `/` `/reader` gold 200. Aliyun loopback `/` `/reader` gold 200. Compute tunnel contract 200.
- Deployment: Workstation BUILD `FnuDmbQLVw6BTtm5rF8h5` on `:3000` / `:3300` (previous `standalone.bak_20260814_1212`). Aliyun READER_ONLY BUILD `mGOwd63mH2NO4_AUO_6hB` (previous `server.js.bak_20260814_1212`). Hard refresh after login.
- Follow-up: Clinical click-through.

## 2026-08-14, Assist 5-class and hidden gold reveal

- Scope: Next workbench assist display, doctor ticks, patient/reader APIs. Branch `assist-keyframe-workflow-20260814`.
- Reason: AI assist should show Benign + T1-T4. Every case needs an openable pathology gold that stays closed until the physician clicks.
- Key changes: Assist card uses gated 5-class (benign from the malignancy head; T still gated; unguarded T4 stays hidden). Doctor ticks add 良性. Case list and first payload do not include the gold value. `GET /api/patients/gold` returns it on demand. Header, cine toolbar, report studio, and `/reader` show 查看真值.
- Validation: `node --experimental-strip-types` tests for five-class, assist-display-stage, public demo stills, and gc-us template. LAN `:3000` / `:3300` `/` `/reader` `/api/agent/contract` 200. Gold endpoint returns the label only on demand; first-round list has `gold_available` and no gold value. Aliyun loopback `/` `/reader` 200; first-round `total=150` with 2 demo stills. Compute tunnel contract 200.
- Deployment: Workstation BUILD `sJE9f4bcTTdNDpkfhZjvY` on `:3000` / `:3300` (previous `standalone.bak_20260814_1205`). Aliyun READER_ONLY BUILD `Gggmq82wGy9KNoyaJPPM4` in `.next-public-deploy-dist` (previous `server.js.bak_20260814_1205`). Hard refresh after login.
- Follow-up: Clinical click-through; leftover A9 IDs; Australian accounts.

## 2026-08-14, Demote primary find/track buttons; zoom serosa on keyframe

- Scope: `InteractiveSegPanel`. Branch `assist-keyframe-workflow-20260814`.
- Reason: 8/13 十二-B: do not force Find lesion / Detect lumen / Track video as primary buttons. Open a keyframe, then refine and zoom the serosa band.
- Key changes: Public cine first screen is Play/Pause, Mark this frame, and Assist. Workflow and full-video track sit under secondary tools. Assist stays off until a lesion contour exists. Opening a ready keyframe opens refine tools and zooms the overlap/ROI. Play clears the zoom so cine stays native.
- Validation: LAN `:3000` / `:3300` `/` `/reader` `/api/agent/contract` 200. Aliyun loopback `/` `/reader` 200; first-round `total=150` with 2 demo stills. Compute tunnel contract 200.
- Deployment: Workstation BUILD `Ry5S7EAsSCLqk1bM92OJY` on `:3000` / `:3300` (previous `standalone.bak_20260814_1105`). Aliyun READER_ONLY BUILD `pQwP4dAtnbb_VMxO3Jx_a` in `.next-public-deploy-dist` (previous `server.js.bak_20260814_1105`). Hard refresh after login.
- Follow-up: Clinical click-through; leftover A9 IDs; Australian accounts.

## 2026-08-14, Clinical-table media completeness (A9)

- Scope: `scripts/audit_clinical_table_media_20260814.py`, hook in `scripts/check_clinical_tables_20260814.py`. Outputs under `data/clinical_tables_check_20260814/outputs/`.
- Reason: 08-13 A9 asked to reconcile the new clinical tables against workstation stills and videos; unmatched IDs should be searched on the full workstation.
- Key changes: Deterministic ID match plus still/video counts. Coded IDs keep their letter prefix. Incomplete IDs are searched under `/data/research/gastric` (sibling trees included; experiment/artifact trees pruned).
- Validation: `python3 scripts/audit_clinical_table_media_20260814.py --reuse-scan`. 504 gastritis 165/165 stills; Ningde 43/45 stills; no Hubei table. Report: `outputs/COMPLETENESS_REPORT.md`.
- Deployment: None. Does not change `dataset/tables/` master tables.
- Follow-up: Full-pack sheet check (36 sheets). 47 still-missing IDs confirmed. Report: `outputs/FULL_CHECK_REPORT.md`.

## 2026-08-14, Keyframe auto-find lesion; smoother cine

- Scope: `doctor-keyframe-preseg.ts`, `InteractiveSegPanel`, `DoctorKeyframeStrip`. Branch `assist-keyframe-workflow-20260814`.
- Reason: Marking a keyframe must auto-find the lesion, not only wait for a box. Autoplay also made cine stutter because the workbench re-rendered on every clock tick.
- Key changes: Background pre-seg runs YOLO lesion find and lumen detect in parallel, then SAM31 lesion + lumen. Playback no longer writes React time state or redraws an empty canvas. Overlay loop starts only after contours exist.
- Validation: LAN `:3000` / `:3300` `/` `/reader` `/api/agent/contract` 200. Aliyun loopback `/` `/reader` 200; first-round `total=150` with 2 demo stills. Compute tunnel contract 200.
- Deployment: Workstation BUILD `ks5d1_dDOhZ2xtjglvjG9` on `:3000` / `:3300` (previous `standalone.bak_20260814_0955`). Aliyun READER_ONLY BUILD `-B93yAElG9PlArWJxjvkP` in `.next-public-deploy-dist` (previous `server.js.bak_20260814_0955`). Hard refresh after login.
- Follow-up: Clinical click-through; incoming tables; Australian accounts.

## 2026-08-14, Raise backend N without touching the T backbone

- Scope: freeze-cascade MLP `n_head`, then val-selected regularized logistic on frozen fused features plus clinical covariates. No doctor UI. No Results claim.
- Reason: Joint unfrozen prospective N AUC 0.803 / acc 0.693 was below the T-proxy oracle 0.832 / 0.817.
- Key changes: `tstaging_tnm_frozen_cascade_n_20260814.yaml`; `scripts/fit_tnm_regularized_n_head_20260814.py` selects C and feature set on val N AUC among fused-containing models.
- Validation: Cascade MLP prospective N AUC 0.811 / acc 0.729. Regularized fused+clin C=0.01: val AUC 0.842, prospective AUC 0.824 / acc 0.757. Still below pathologic T oracle. T patient acc stayed 0.673.
- Deployment: None.
- Follow-up: Keep N off Results and off doctor scoring.

## 2026-08-14, Frozen cascade N head to raise backend N

- Scope: freeze Phase 0 DualBranch; train only `n_head` on detached fused features plus T logits. No doctor UI. No M head.
- Reason: Joint unfrozen run had prospective N AUC 0.803, below T-proxy 0.834, and slightly cut T2 recall.
- Key changes: `n_head_use_t_logits`, `n_head_detach`, `freeze_except_nm_heads`, early-stop on val N AUC, class-weighted N loss, val Youden threshold at test.
- Validation: Run `tstaging_tnm_frozen_cascade_n_20260814_172331`, 7 epochs. Prospective N AUC 0.811 / acc 0.729.
- Deployment: None.
- Follow-up: Prefer the regularized frozen logistic over this MLP.

## 2026-08-14, Launch backend-only N/M joint training (A11)

- Scope: `pipeline/run_experiment.py` with `tstaging_tnm_backend_only_phase0.yaml`. No doctor UI.
- Reason: User asked to start the joint run after the frozen probe failed the gate.
- Key changes: Warm-start Phase 0 DualBranch; new `n_head` / `m_head` (16 missing keys expected). GPU 1. 30 epochs, lambda_n 0.15, lambda_m 0.10.
- Validation: Finished epoch 19 (best 7). Prospective N AUC 0.803 vs T-proxy 0.834 and frozen head 0.826. M acc 0.523. Patient T acc 0.678 (same as Phase 0); frame T2 recall 0.46 vs Phase 0 0.50.
- Deployment: None. Do not wire N/M into Round-2 scoring.
- Follow-up: Keep N/M off Results and off the doctor UI.

## 2026-08-14, N/M negative-control Extended Data in the T paper

- Scope: Overleaf methods / discussion / extended data, plus `scripts/plot_tnm_extended_data_20260814.py`. No doctor UI.
- Reason: Put the T--N association and failed frozen N probe in the manuscript as a limitation, not as an AI endpoint.
- Key changes: Cohort N/M table. Three-panel figure (N+ by T, T vs frozen head, within-T AUC). Methods state pN/pM are descriptive only. Discussion item 7.
- Validation: Figure rebuilt from association CSV and prediction JSON. Numbers match val N AUC 0.836 vs 0.791.
- Deployment: None. Figure files also sit under `artifacts/visualizations/tnm_backend_only_20260814/`.
- Follow-up: Do not add n_head numbers to Results. Do not launch joint DualBranch training.

## 2026-08-14, Frozen-head N/M patient predictions (A11)

- Scope: `scripts/predict_tnm_frozen_heads_20260814.py`. No doctor UI. Backbone stays frozen.
- Reason: Produce patient-level N/M scores from already-exported Phase 0 embeddings, after the association table.
- Key changes: Train-only logistic heads on fused features and T logits. Writes predictions and within-T AUCs.
- Validation: Val N fused AUC 0.791 / acc 0.744 vs pathologic T 0.836 / 0.845. Prospective 0.826 vs 0.834. Within-T1 val AUC 0.55. M val sensitivity 0.27 on 11 positives.
- Deployment: None. Predictions stay in artifacts. Do not launch joint DualBranch training.
- Follow-up: Keep N/M off the T paper Results.

## 2026-08-14, Patient-level T vs N/M association stats (A11)

- Scope: `scripts/stats_tnm_t_association_20260814.py`. No doctor UI. No training.
- Reason: Quantify how strongly pathologic T already explains N+ / M1 before any joint head.
- Key changes: Wilson CIs, chi-square, Cochran-Armitage trend, unadjusted OR vs T1. Pooled train+val+prospective labeled patients.
- Validation: 1,511 pN patients; N+ 18.1% in T1 to 97.9% in T4b; chi-square p=1.3e-115; T-score N AUC 0.828. M1 101/1,546, 64 of them T4b.
- Deployment: None.
- Follow-up: Use as Extended Data cohort / biology table. Do not launch joint TNM training.

## 2026-08-14, Frozen Phase 0 N probe (A11 stage 1)

- Scope: `scripts/run_tnm_frozen_n_probe_20260814.py`. No doctor UI. Backbone stays frozen.
- Reason: Check whether primary-lesion embeddings add N signal beyond pathologic T and frozen T logits before any joint update.
- Key changes: Validation-transform embedding export from Phase 0 DualBranch. Linear probes on fused features, T logits, and T-residual features. Gate: val N AUC must beat T-proxy by 0.03.
- Validation: GPU 0 export 7874 / 904 / 1659 frames, ckpt missing=0. Gate failed: val T-proxy N AUC 0.839 vs fused 0.791 (delta -0.048). Residual fused after T logits 0.529. Prospective fused 0.826 vs T-proxy 0.832.
- Deployment: None. Do not launch `run_tnm_backend_only_phase0.sh`.
- Follow-up: Keep N/M off DualBranch and off Round-2 scoring. If N is still wanted later, need node-level or CT/LN evidence, not primary-lesion joint training.

## 2026-08-14, Hold naive TNM joint training; require T-proxy gate

- Scope: A11 training plan only. No doctor UI. No GPU run.
- Reason: Pathologic T already predicts N (AUC 0.82) and M (AUC 0.81). A shared DualBranch plus fixed 0.15/0.10 heads would mostly relearn T and could hurt the T backbone via rare M1/T4b cases.
- Key changes: T-proxy baseline script. YAML warning to freeze-probe N first. Architecture note: cascade N on detached T logits; Kendall weights only if residual N beats the proxy; do not backprop M.
- Validation: `python3 scripts/probe_tnm_t_proxy_baseline_20260814.py`.
- Deployment: None.
- Follow-up: Frozen-backbone N probe code if the user wants the next script.

## 2026-08-14, Prepare backend-only N/M training scripts (A11)

- Scope: Phase 0 label join, DualBranch `n_head`/`m_head`, trainer aux loss, runnable YAML and launcher. No doctor UI.
- Reason: 8/13 A11: run TNM in the background; doctors cannot score N/M from primary-lesion video. Inventory existed; training path did not.
- Key changes: Normalize pN/pM to N0/N+ and M0/M1 (`ignore=-1`). Fix inventory dropping numeric 0. Join labels onto Phase 0 clinical CSVs. Warm-start YAML from Phase 0 T checkpoint with low-weight N/M heads.
- Validation: `python3 scripts/build_tnm_nm_phase0_splits_20260814.py --dry-run`; `python3 scripts/inventory_tnm_nm_labels_20260814.py`; `python3 scripts/build_tnm_nm_phase0_splits_20260814.py`; script `--help`. Training not started.
- Deployment: None. Results stay in `artifacts/` / experiment `nm_metrics.json`.
- Follow-up: Launch `bash pipeline/scripts/run_tnm_backend_only_phase0.sh` when a GPU is free. Keep N/M off Round-2 scoring.

## 2026-08-14, Public cine autoplay then doctor keyframe

- Scope: `InteractiveSegPanel`, `DoctorKeyframeStrip`, `ReaderWorkbench`. Branch `assist-keyframe-workflow-20260814`.
- Reason: Public doctors still saw a still-first / box-first workbench. 8/13 minutes: play the video first, pause with buttons, mark a keyframe, then background lumen+lesion pre-seg.
- Key changes: Case video autoplays muted. Play/Pause stay on buttons; Space still marks a keyframe without pausing. Added a visible Mark this frame control. Copy no longer asks to box the lesion first.
- Validation: LAN `:3000` / `:3300` `/` `/reader` `/api/agent/contract` 200. Aliyun loopback `/` `/reader` 200; first-round `total=150` with 2 demo stills.
- Deployment: Workstation BUILD `NGy4RA1v2cq0T3zPgZ1_X` on `:3000` / `:3300` (previous `standalone.bak_20260814_0942`). Aliyun READER_ONLY BUILD `Zfh9Ppr393OUYR4J1zCe3` in `.next-public-deploy-dist` (previous `server.js.bak_20260814_0942`). Hard refresh after login.
- Follow-up: Clinical click-through; incoming tables; Australian accounts.

## 2026-08-14, Morning confirm of gated-T Next bundles

- Scope: Re-swap the already-built workstation standalone and Aliyun reader-only dist. No source change.
- Reason: Confirm both edges still serve last night's gated-T / report-shrink pack after overnight.
- Key changes: Copied BUILD_ID into workstation standalone. Re-rsynced Aliyun `.next-public-deploy-dist` and `server.js`. Restarted `gastric-next` / `gastric-next-public` on the workstation and `gastric-next` on Aliyun. Previous Aliyun `server.js` kept as `server.js.bak_20260814_0929`.
- Validation: LAN `:3000` / `:3300` `/` `/reader` `/api/agent/contract` 200. Aliyun loopback `/` `/reader` 200; first-round `total=150` with 2 demo stills; demo PNG `image/png`. Compute tunnel `18768` contract 200.
- Deployment: Workstation BUILD `6G0EMGpSSfs3zJiN9h_vS`. Aliyun BUILD `txHjSumzFeQ4OPLCmAjD1`. Hard refresh after login.
- Follow-up: Clinical click-through; incoming tables; Australian accounts.

## 2026-08-14, Gate the workbench T number; stop report defaults

- Scope: `AgentWorkbenchPanel`, `TemplateReportEditor`. Branch `assist-keyframe-workflow-20260814`.
- Reason: The `/` synthesis card still preferred raw `assist_display_stage` and showed fusion tendency next to it. Report preview defaulted empty T to T1 and English growth to locally infiltrative.
- Key changes: Big T uses only the gated display. Fusion tendency is off the doctor cards. Report preview no longer invents T or growth. Five-layer / gross type / N/M sit behind the full boss template.
- Validation: `node apps/gastric_scan_next/scripts/test_assist_display_stage.mjs`; `node apps/gastric_scan_next/scripts/test_gc_us_report_template.mjs`. LAN `/` `/reader` `/api/agent/contract` 200. Aliyun loopback `/` `/reader` 200; first-round `total=150` with 2 demo stills.
- Deployment: Workstation BUILD `6G0EMGpSSfs3zJiN9h_vS` on `:3000` / `:3300` (previous `standalone.bak_20260814_0142`). Aliyun READER_ONLY BUILD `txHjSumzFeQ4OPLCmAjD1` in `.next-public-deploy-dist` (previous `server.js.bak_20260814_0143`; live ui2 kept). Hard refresh after login.
- Follow-up: Clinical click-through; incoming tables; Australian accounts.

## 2026-08-14, Hide leftover T2/T3 and growth phrases from the doctor card

- Scope: `ReaderEvidencePanel`, `GcUsEvidencePanel`, `assist-display-stage.ts`. Branch `assist-keyframe-workflow-20260814`.
- Reason: Item 3 gated the stage, but the assist card still showed classifier T4, growth/morphology, and a T2/T3 lean built from those phrases.
- Key changes: Primary card stays T, certainty, length, thickness, serosa. Contour summary drops 8/13 geometry phrases. T2/T3 and geometry scores sit behind Review details. Evidence panel no longer lists morphology or growth; wall/perigastric are optional.
- Validation: `node apps/gastric_scan_next/scripts/test_assist_display_stage.mjs`. LAN `/` `/reader` `/api/agent/contract` 200. Aliyun loopback `/` `/reader` 200; first-round `total=150` with 2 demo stills.
- Deployment: Workstation BUILD `kIBIhiR7X8UD_8eRABpmJ` on `:3000` / `:3300` (previous standalone `standalone.bak_20260814_0136`). Aliyun READER_ONLY BUILD `k0DmhgisxWBknoNGfwmYi` in `.next-public-deploy-dist-ui2` (previous `*.bak_20260814_0137`). Hard refresh after login.
- Follow-up: Clinical click-through on early frames; incoming tables; Australian accounts.

## 2026-08-14, Contract Round-2 acceptance to the 8/13 shrink

- Scope: meeting acceptance note plus the 8/13 T4 replay in `test_assist_display_stage.mjs`.
- Reason: The 8/6 seven-sign gate is a broken link. Product already hides unguarded T3/T4 and geometry phrases; scoring docs still pointed at the old seven-sign list.
- Key changes: Write `docs/meetings/2026-08-14_第二轮验收范围收缩.md`. Replay the live miss (early lesion, 局部浸润 / 浆膜欠光整 / T4) so doctor-facing stage stays empty. Point the 8/13 minutes and meetings index at the new note.
- Validation: `node apps/gastric_scan_next/scripts/test_assist_display_stage.mjs`.
- Deployment: None. Clinical click-through this week still required.
- Follow-up: Incoming clinical tables; Australian accounts; boss call on five-class vs two-task.

## 2026-08-14, Aliyun public Next swap for demo stills and sidebars

- Scope: Aliyun `/var/www/gastric-next` reader-only bundle. Branch `assist-keyframe-workflow-20260814`.
- Reason: Workstation `:3000/:3300` already had A10/A12, but doctors see the Aliyun UI, not the workstation standalone.
- Key changes: Built `NEXT_PUBLIC_READER_ONLY=1 NEXT_DIST_DIR=.next-public-deploy-dist` (BUILD `tDCuEjyLRj_US31EMFKmV`). Backed up previous `server.js` / dist as `*.bak_20260814_0132`. Restored the `.next` → `.next-public-deploy-dist` symlink. Copied two de-identified demo stills into the public reader media root. Restarted `gastric-next`.
- Validation: Aliyun loopback `/` and `/reader` return 200. First-round `/api/patients` keeps `total=150` and attaches 2 `demo_stills` with no pathology. Demo PNG is `image/png`.
- Deployment: Public UI is on the new reader-only build. Hard refresh after login. Rollback: restore `server.js.bak_20260814_0132`, point `.next` at `.next-public-deploy-dist.bak_20260814_0132`, restart `gastric-next`.
- Follow-up: A13 Australian accounts still wait for a named identity session.

## 2026-08-14, Workstation Next rebuild for demo stills and sidebars

- Scope: `apps/gastric_scan_next` production standalone on the workstation. Branch `assist-keyframe-workflow-20260814`.
- Reason: A10/A12 source was done, but `:3000` / `:3300` still served the 2026-08-13 standalone.
- Key changes: Isolated build `NEXT_DIST_DIR=.next-assist-20260814` (BUILD `raSSdYbGanRyEFENeA5uw`). Previous standalone kept as `.next/standalone.bak_20260814_0126`. Copied `static` into the new standalone and restarted `gastric-next` / `gastric-next-public`.
- Validation: Both ports return `demo_stills` (2 frames) on the first-round queue while `total` stays 150. Demo still PNG is `image/png`. `/`, `/reader`, and `/api/agent/contract` return 200.
- Deployment: LAN `:3000` and public-edge `:3300` are on the new build. Hard refresh required. Aliyun host bundle was not swapped. Rollback: stop both units, restore `.next/standalone.bak_20260814_0126` to `.next/standalone`, start both units.
- Follow-up: A13 Australian accounts; Aliyun reader-only bundle if the cloud host still serves its own Next dist.

## 2026-08-14, Reader sidebars collapse; history keeps 20 (item 6 / A12)

- Scope: `apps/gastric_scan_next` `/reader` sidebars and history drawer. Branch `assist-keyframe-workflow-20260814`.
- Reason: 8/13 A12: redo sidebars after analysis guards; keep the middle canvas and history; left/right must collapse.
- Key changes: Case library and report columns collapse like the workbench. Case list has search and task-type tags only (no pathology). History drawer still opens from the header and shows the last 20 sessions.
- Validation: Typecheck the touched Reader files if the workspace compiler is available. Manual: `/reader` collapse both sides, search a case id, open History and confirm 20 rows.
- Deployment: Same standalone rebuild as A10. Do not overwrite `human_assist_v2.html`.
- Follow-up: A11 heads not trained; A13 Australian accounts; public rebuild.

## 2026-08-14, Inventory pN/pM labels only (item 6 / A11)

- Scope: `scripts/inventory_tnm_nm_labels_20260814.py` and the backend TNM stub yaml.
- Reason: 8/13 A11: run TNM yourself; do not put N/M into doctor scoring.
- Key changes: Count pathology pN/pM already present in Next clinical JSON. Write a coverage snapshot. No training, no doctor UI fields.
- Validation: `python3 scripts/inventory_tnm_nm_labels_20260814.py`.
- Deployment: None.
- Follow-up: Train `n_head` / `m_head` later against this inventory if needed.

## 2026-08-14, Public demo stills on the reader queue (item 6 / A10)

- Scope: `apps/gastric_scan_next` workbench (`/`) patient list and `/api/patients`. Branch `assist-keyframe-workflow-20260814`.
- Reason: 8/13 A10: a LAN still-only case could not be opened on the public reader-only edge, so the shared screen skipped it.
- Key changes: Two de-identified stills already in the reader media root are attached as `demo_stills` on the first-round queue. They stay out of scoring totals and research freeze order. No pathology is attached. The media route now serves PNG/JPEG with the correct content type. The sidebar pins them as demo stills.
- Validation: `node apps/gastric_scan_next/scripts/test_public_demo_stills.mjs`.
- Deployment: LAN `:3000` and public `:3300` both use `.next/standalone`. Rebuild and restart those units before sharing the deep link. Do not overwrite `human_assist_v2.html`.
- Follow-up: A11 N/M heads still wait for labels; A12 full sidebar redo; A13 Australian accounts; public rebuild.

## 2026-08-14, Clinical-table reconcile stays waiting (item 5 / A9)

- Scope: `scripts/reconcile_clinical_tables_20260813.py`, `scripts/README.md`, A9 meeting note.
- Reason: 8/13 A9: do not treat meeting ASR counts as source data. The incoming folder still has no clinical tables.
- Key changes: Re-ran the snapshot. README / `.gitkeep` no longer count as incoming tables (`status` stays `waiting_for_clinical_tables`). Script is listed in `scripts/README.md` section 3. Legacy registry refresh report remains 2026-03-25.
- Validation: `python3 scripts/reconcile_clinical_tables_20260813.py` prints `waiting_for_clinical_tables` and `incoming_files: []`.
- Deployment: None. Drop CSVs/XLSX into `dataset/tables/incoming_clinical_20260813/` then re-run.
- Follow-up: Refresh main registries only after clinical re-send.

## 2026-08-14, Delay report draft until physician ticks (item 4)

- Scope: `apps/gastric_scan_next` workbench (`/`) and `/reader`. Branch `assist-keyframe-workflow-20260814`.
- Reason: 8/13 A6: the report was already editable, but prose was auto-filled as soon as contours or Assist ran. Doctors want ticks first, then generate.
- Key changes: Template prose stays empty until the physician ticks T stage and serosa (continuous / unclear / interrupted) and clicks Generate report. After that the draft stays editable. No silent 膨胀型 / 浆膜看不清 prefill. Export and sign-off wait for a generated draft.
- Validation: `node apps/gastric_scan_next/scripts/test_gc_us_report_template.mjs`. Manual: analyze a case, open the report studio, confirm the preview is empty, tick T and serosa, click Generate, then edit the draft.
- Deployment: Next LAN `:3000` / `/reader` on this branch. Do not overwrite `human_assist_v2.html`. Commit when requested.
- Follow-up: Item 5 waits for clinical tables.

## 2026-08-14, Analysis shrink and anti-overclaim (item 3)

- Scope: `apps/gastric_scan_next` workbench (`/`) and `/reader`; `pipeline/agent/product/analyze_case.py`. Branch `assist-keyframe-workflow-20260814`.
- Reason: 8/13 A4/A5/A7/A8: missing wall/serosa evidence still surfaced silent T3, geometry words such as 局部浸润 / 浆膜欠光整, and unguarded T4 on early lesions.
- Key changes: Doctor-facing stage is empty until wall/serosa is confirmed; T4 needs explicit serosa disruption or organ invasion; confidence is high/medium/low, not a statistical interval; primary card is T, certainty, length, thickness, and serosa (continuous / unclear / interrupted). Geometry scores stay review-only. Report templates no longer prefill T3, five-layer maps, or growth from an empty stage.
- Validation: `node apps/gastric_scan_next/scripts/test_gc_us_tscore.mjs`; `node apps/gastric_scan_next/scripts/test_gc_us_report_template.mjs`; `node apps/gastric_scan_next/scripts/test_assist_display_stage.mjs`; `python3 -m pytest pipeline/agent/signs/test_wall_gate.py -q`.
- Deployment: Next LAN `:3000` / `/reader` on this branch. Do not overwrite `human_assist_v2.html`. Commit when requested.
- Follow-up: Item 4 delay draft prefill; item 5 wait for clinical tables.

## 2026-08-14, Traditional refine tools (item 2)

- Scope: `apps/gastric_scan_next` workbench (`/`) and `/reader`. Branch `assist-keyframe-workflow-20260814`.
- Reason: 8/13 A3: doctors want drag-any-point, brush, and LabelMe-style polygon on both lesion and lumen; scribble / nnInteractive stay secondary.
- Key changes: Shared `pickOrInsertOnContour`; main workbench and reader can drag any point on the line, brush-nudge the boundary, and redraw with a polygon; lumen uses the same tools (box-only edit is secondary). Handles stay sparse and small so they do not cover small lesions.
- Validation: `node apps/gastric_scan_next/scripts/test_contour_edit.mjs`. Manual: open a keyframe, drag mid-edge, brush, close a polygon, switch to lumen and drag.
- Deployment: Next LAN `:3000` / `/reader` on this branch. Do not overwrite `human_assist_v2.html`. Commit when requested.
- Follow-up: Item 3 analysis guards (no invented T3 / serosa wording).

## 2026-08-14, Finish keyframe-workflow shell (item 1)

- Scope: `apps/gastric_scan_next` workbench (`/`) and `/reader`. Branch `assist-keyframe-workflow-20260814`.
- Reason: Item 1 still sought the live video during pre-seg (playback stuttered), analysis was not bound to the active doctor keyframe, and the result area lacked the uncorrected-contour note.
- Key changes: Capture the still at Space-mark time and pre-seg without seeking; concurrent marks no longer cancel earlier jobs; Assist / Analyze require the active doctor keyframe; show "基于未校正轮廓" until the doctor edits that frame. Tracking stays secondary. Static HTML demos untouched.
- Validation: Typecheck the touched Next files if the workspace compiler is available. Manual: Space x4 while playing, strip shows 4 thumbs, click thumb 2 loads the box, analyze shows the uncorrected note.
- Deployment: Next LAN `:3000` / `/reader` on this branch. Do not overwrite `human_assist_v2.html`. Commit when requested.
- Follow-up: Item 2 refine tools (drag / brush / polygon); then item 3 analysis guards.

## 2026-08-13, Round-2 keyframe workflow and analysis guards

- Scope: `apps/gastric_scan_next` reader/workbench; `pipeline/agent/signs` + `analyze_case.py`; meeting docs and reconcile stub.
- Reason: 8/13 clinical review: Space must mark keyframes (not play/pause); full-video track is secondary; invented late-stage wording (局部浸润 / 浆膜欠光整 / silent T3) misled early lesions.
- Key changes: Doctor keyframe strip + background pre-seg; drag/brush/polygon as primary refine; demote tracking/nnInteractive; stop geometry proxy and report defaults from inventing T3/N0/M0/ascites/growth labels; A9 reconcile script waiting for clinical tables; A10–A13 notes and TNM backend stub.
- Validation: `python3 scripts/reconcile_clinical_tables_20260813.py`; `python3 -m pytest pipeline/agent/signs/test_wall_gate.py -q` (run after edit). Manual UI: Space marks up to 5 keyframes without stopping playback.
- Deployment: Next LAN `:3000` / `/reader`; do not overwrite static `human_assist_v2.html`. Commit when requested.
- Follow-up: clinical tables into `dataset/tables/incoming_clinical_20260813/`; public stills for LAN demo case; N/M labels before real TNM training.

## 2026-08-13, Enrich GTstage draft on the Phase 0 predicted-ROI contract

- Scope: Overleaf Agent paper on canonical project `6a66e7b9c3112820b756b0f2`.
- Reason: Results still mixed doctor-ROI frame T2 recall, a legacy centre range, and a three-reader placeholder. The auditable primary is 456-patient predicted ROI.
- Key changes: Primary external $n=456$, ACC 47.1\%, AUC 0.668, T2 recall 9.0\%, confusion and $n\geq20$ centres. Retrieval reported on a separate 379-patient audit (non-significant, T2 unchanged). Reader protocol: 150 video cases, 14 completed unaided reviews, AI-assisted round not run. Cine pack model scores added without reader uplift. No author lines. LDH 0.86 remains a different contract.
- Validation: `olcli push` and pdfLaTeX compile on the canonical project.
- Deployment: Canonical Overleaf only.
- Follow-up: Commit not requested.

## 2026-08-13, Enrich Overleaf intro around detection--staging unification

- Scope: Overleaf Agent paper intro and abstract on canonical project `6a66e7b9c3112820b756b0f2`.
- Reason: The lead-in needed a higher-level clinical argument: reunite detection and preoperative depth in one physician-participating water-filling CEUS path, with operator interaction as evidence formation rather than an optional UI.
- Key changes: Expanded untitled introduction (~1,200 words). Abstract reframed around successive judgements, triage-then-stage cascade, and not-assessable outputs. Honest Phase~0 / reader / continuous-scan numbers unchanged. GRAPE remains only light adjacent CT context in the intro.
- Validation: `olcli push` and clean pdfLaTeX compile on the canonical project.
- Deployment: Canonical Overleaf only.
- Follow-up: Commit not requested.

## 2026-08-13, Align GRAPE length and remove all author lines

- Scope: Overleaf Agent paper on canonical project `6a66e7b9c3112820b756b0f2`.
- Reason: Page 1 still named authors; main-text word count was about half of GRAPE (intro+results+discussion), while three small tables occupied a results page. GRAPE puts tables in Extended Data and starts the untitled lead-in on page 2.
- Key changes: No author, affiliation, correspondence, acknowledgement, or contribution lines. Title page is title plus abstract only. Intro / Results / Discussion expanded to GRAPE paragraph rhythm without new endpoints. Tables moved to Extended Data. Honest numbers unchanged.
- Validation: `olcli push` and pdfLaTeX compile on the canonical project.
- Deployment: Canonical Overleaf only.
- Follow-up: Commit not requested.

## 2026-08-13, Hide TBA authors and match GRAPE section order

- Scope: Overleaf Agent paper `docs/paper_drafts/overleaf/gastric_evidence_agent/` on canonical project `6a66e7b9c3112820b756b0f2`.
- Reason: The official `sn-jnl` wrapper printed `Authors TBA1*` / affiliation / corresponding email. GRAPE (Nat Med 2025) hides the author block on page 1 and uses untitled lead-in, Results (model / internal-external / reader / real-world), Discussion, Online content, then Methods with trial / imaging / model / metrics / reader / statistics, then reporting, data, code, and end notes.
- Key changes: No `\author`/`\affil`/`\email`/`\keywords`. Subtitle is the GRAPE line ``A list of authors and their affiliations appears at the end of the paper''. Unnumbered heads. Honest cine heading remains a still-to-video deployment domain, not a 78k opportunistic screen. Numbers unchanged.
- Validation: `olcli push` and clean pdfLaTeX compile on the canonical project.
- Deployment: Canonical Overleaf only.
- Follow-up: Restore the author block only when the list is confirmed. Commit not requested.

## 2026-08-13, Migrate Overleaf manuscript to official sn-jnl

- Scope: `docs/paper_drafts/overleaf/gastric_evidence_agent/` on canonical Overleaf `6a66e7b9c3112820b756b0f2`.
- Reason: Homemade two-column Nature chrome is not a submission class. Nature Portfolio / eJP expect the Springer Nature authoring template (`sn-jnl` v3.1, December 2024) compiled with pdfLaTeX.
- Key changes: `\documentclass[pdflatex,sn-nature]{sn-jnl}`; BibTeX + `sn-nature.bst` instead of biblatex/biber; `xeCJK` and Chinese abstract dropped from the compiled PDF (source kept in `sections/abstract_zh.tex`). Content, Phase 0 predicted-ROI patient ACC 47.1%, and blank reader/real-world panels unchanged. LDH paper not merged.
- Validation: `olcli push` then `olcli compile` on the canonical project after switching the Overleaf compiler to pdfLaTeX.
- Deployment: Canonical Overleaf only. Duplicate project remains emptied.
- Follow-up: Flatten to one `.tex` before eJP upload. Fig 2 ROC panels remain black-background drafts. Commit not requested.

## 2026-08-13, Align Overleaf layout to Nature Medicine / GRAPE chrome

- Scope: `docs/paper_drafts/overleaf/gastric_evidence_agent/main.tex` and section files.
- Reason: After the GRAPE skeleton rewrite, the compiled PDF still looked like a generic `article` class: centred title, full-width bilingual abstract, numbered 1/1.1 headings, bracket citations, A4, no journal header.
- Key changes: 210 x 279 mm page; `nature medicine` + red rule + Article header; title left; dates left / abstract right on page 1; no authors on page 1; Chinese abstract moved to the back; unnumbered sans-serif Results/Methods heads; superscript blue citations; `Fig. N |` captions without double bold; footer in Nature blue.
- Validation: `olcli compile` on canonical Overleaf after push; visual check of page 1 against GRAPE page 1.
- Deployment: Canonical Overleaf `6a66e7b9c3112820b756b0f2`. Duplicate project remains emptied.
- Follow-up: Fig 2 ROC panels are still black-background drafts. Commit not requested.

## 2026-08-13, Restyle Overleaf manuscript on GRAPE / Nature Medicine

- Scope: `docs/paper_drafts/overleaf/gastric_evidence_agent/` (canonical Overleaf `6a66e7b9c3112820b756b0f2`). Duplicate project `6a66e7ba6777c6d4cec65e0a` emptied.
- Reason: Two identically named Overleaf projects held the same paper. The live draft still used a Lancet-style methods-first article class, unlike GRAPE (Nat Med 2025).
- Key changes: Unstructured abstract; untitled lead-in; Results before Methods; no research-in-context box; `Fig. N |` captions; two-column layout; three-phase locate-then-stage narrative. Honest Phase 0 patient ACC 47.1% unchanged. Reader and consecutive-cohort numbers still not invented.
- Validation: `olcli compile` on the canonical project after push.
- Deployment: Canonical Overleaf only. Delete the duplicate project in the Overleaf dashboard (olcli cannot delete projects).
- Follow-up: Commit not created because a commit was not requested. GitHub mirror not pushed.

## 2026-08-13, Unify Agent/LDH GRAPE citations and Overleaf via olcli

- Scope: Overleaf Agent paper `docs/paper_drafts/overleaf/gastric_evidence_agent/`; LDH classifier `docs/paper_drafts/tex_v2_ldh/gastric_tstaging_paper_v2.tex`; related-work table.
- Reason: GRAPE (Nat Med 2025) was name-dropped as a CT staging neighbour; LDH Table 1 labelled GTRNet (Zheng 2025, CT T-staging) as CEUS DL and cited a non-existent Park 2023 EUS GTRNet. Two Overleaf projects shared the same name, one empty.
- Key changes: GRAPE cited as noncontrast-CT screening with a three-phase bar. Companion LDH screened-frame macro-AUC (~0.86) labelled a different contract from Phase 0 predicted-ROI patient ACC ~47%. LDH benchmark table corrected. Canonical Overleaf `6a66e7b9c3112820b756b0f2` plus duplicate `6a66e7ba6777c6d4cec65e0a` pushed from the same local tree.
- Validation: Local vs canonical Overleaf tex/bib md5 identical before the pass-9 edits; `olcli push` after edits.
- Deployment: Overleaf compile XeLaTeX + biber. LDH tex remains a separate manuscript (not merged).
- Follow-up: Commit not created because a commit was not requested. Nested GitHub mirror `CUHKSmartBuild/gastric-evidence-agent-paper` still needs a separate push if authors want GitHub = Overleaf.

## 2026-08-13, CUHK campus publisher access for Nature PDFs

- Scope: `docs/references/related_literature/campus_publisher_access.py`; `fetch_review_corpus.py`; `paper/literature/_ingest_nature_nbe.py`; literature skill and `docs/references/CAMPUS_PUBLISHER_ACCESS.md`.
- Reason: On the CUHK campus LAN, Nature already recognizes the institutional IP, but only after the `idp.nature.com` cookie handshake. Scripts used a bot User-Agent and no cookie jar, so article PDFs came back as HTML. WebFetch uses a cloud IP and looks unsubscribed.
- Key changes: Persistent cookie jar under `~/.config/gastric-literature/` (not in git). Helper warms Nature/Springer/ScienceDirect/Wiley/Science/Lancet cookies, then downloads PDFs with a browser User-Agent. Fetch/ingest scripts reuse the helper for publisher hosts.
- Validation: Public IP `137.189.241.57` (AS3661 CUHK). Nature IDP set `idp_session`. Helper downloaded Merlin `10.1038/s41586-026-10181-8` (9.2 MB) and the open chest FM `10.1038/s41586-025-09079-8` (18.3 MB), both `%PDF-1.4`. IDE browser showed full access via The Chinese University of Hong Kong.
- Deployment: Local workstation only. Rerun `python3 docs/references/related_literature/campus_publisher_access.py warmup` if the Nature session goes cold or the machine leaves campus.
- Follow-up: Off-campus access still needs EasyAccess + CUHK Login / 2FA. Elsevier/Wiley may still challenge Cloudflare in non-browser clients.

## 2026-08-13, Dark cine speed menu and progress groove

- Scope: `CineSpeedSelect`; `globals.css` `.video-progress-shell`; workbench and reader cine bars.
- Reason: Native `<select>` on Linux Chrome opened a white list, so cyan/white rate labels were unreadable. The range track was still too thin and the fill depended on WebKit gradient stops.
- Key changes: Custom dark speed menu (`0.25×` through `2×`) portaled above/below the button. Progress uses a dark groove plus cyan fill via `--progress`, with a larger thumb.
- Validation: Workstation `:3000` 200; Aliyun loopback `:3000` 200.
- Deployment: Workstation Next BUILD `U1n1utVuqXBO31R5re_Ni`. Public Aliyun BUILD `y0eQpQorJ662y7XGwz70O`. Hard refresh required.
- Follow-up: Commit not created because a commit was not requested.

## 2026-08-13, Cine speed 0.25× and progress bar fill

- Scope: `InteractiveSegPanel` playback rates and scrubber; `globals.css` `.video-progress`; Reader timeline/toolbar; `VideoPlayer`.
- Reason: Workbench speed list started at 0.5× so 0.25× could not be selected. The Chrome range track was a static gradient, so played vs remaining time was not visible. Time labels were cramped `12.34` without a clock format.
- Key changes: Rates are `0.25, 0.5, 0.75, 1, 1.25, 1.5, 2`. Speed control uses a wider `0.25×` label. Scrubber fills with `--progress`. Time shows `m:ss.t`.
- Validation: Workstation `:3000` 200; public Aliyun loopback `:3000` 200. Built JS includes `0.25×` / `0.75×`; CSS `.video-progress` fills with `--progress`.
- Deployment: Workstation Next BUILD `IWaQPQ7MM2tgZVvlhDs8x` (`gastric-next` / `gastric-next-public` restarted). Public Aliyun BUILD `6_fvMhvKcms8ApBzCxWk-` (`NEXT_PUBLIC_READER_ONLY=1 NEXT_DIST_DIR=.next-public-deploy-dist`, previous kept as timestamped `.bak_*`). Hard refresh required.
- Follow-up: Commit not created because a commit was not requested.

## 2026-08-13, Fix SAM3.1 video 404 on reader-pack paths

- Scope: `scripts/serve_sam31_static.py` video path resolve; `aliyun-sam-tunnel.service` `18769→8768`.
- Reason: Track video posted `/api/reader/media?rel=良恶性/...`. SAM3.1 only searched the repo root, so `/api/sam31/video-propagate` returned 404. Public Next also called `SAM31_UPSTREAM=18769`, which was not tunneled.
- Key changes: Resolve reader-pack and the same allowlisted video roots as SAM2. Reverse-tunnel workstation `:8768` to Aliyun `127.0.0.1:18769`.
- Validation: Direct `POST /api/sam31/video-propagate` on BM-001 reader clip returned 200. Aliyun loopback `18769/api/sam31/status` 200.
- Deployment: Restarted `gastric-sam31` and `aliyun-sam-tunnel`. No Next rebuild. Public Track video uses the new tunnel.
- Follow-up: If public Track video still fails, confirm Aliyun `NEXT_AGENT_LOCAL_PATHS` still includes `/api/agent/video/propagate`.

## 2026-08-13, Wall layers use pixel bright/dark bands and serosa line

- Scope: `contact_geometry.js` / `interactive_layer_bridge.js` wall-layer readout and the right-sidebar 壁层 card.
- Reason: Occupancy was binned into equal L1-L5 slices. Doctors need pixel bands along the lesion-to-outer ray, then whether the outer bright line stays or breaks after the lesion reaches serosa.
- Key changes: Sample outward from the lesion front past the outer wall. Label bright/dark bands from gray values. Score the outer bright peak along the contact arc against adjacent wall. Sidebar shows 贴到浆膜亮线还在 / 中断 / 未贴到 / 看不清. This does not unlock T4a.
- Validation: TypeScript production build. Workstation Next BUILD `IWaQPQ7MM2tgZVvlhDs8x`; `:3000` and `:3300` home 200. SAM 3.1 left running.
- Deployment: Rebuild/restart workstation Next `:3000/:3300`. Hard refresh required so vendor JS `?v=20260813s` reloads. Aliyun public dist not redeployed.
- Follow-up: Commit not created because a commit was not requested.

## 2026-08-13, Lumen refine no longer shows leftover lesion-detect overlay

- Scope: workstation Next `InteractiveSegPanel` busy overlay and doctor-workflow labels.
- Reason: After auto-find lesion, the canvas kept the label 自动检测病灶候选. Any later busy state, including lumen refine or 出轮廓, reused that leftover text as a full-screen popup.
- Key changes: Overlay copy follows the current job. nnInteractive refine no longer opens the heavy overlay. Workflow labels are cleared when the job ends and are not applied to unrelated saves or lumen edits.
- Validation: TypeScript production build. Workstation Next BUILD `ys6WsuWXKte5AoqALUf_N`; `:3000` and `:3300` home 200.
- Deployment: Rebuild/restart workstation Next `:3000/:3300`. Hard refresh required. Aliyun public dist not redeployed.
- Follow-up: Commit not created because a commit was not requested.

## 2026-08-13, Wall-layer view moves into the right sidebar

- Scope: workstation Next wall-layer tool (`InteractiveSegPanel`, `WallFeatureAnalysisCard`, evidence drawer in `app/page.tsx`).
- Reason: The canvas popup used AI-like copy, parentheses, and a duplicate report dump. Doctors need a short wall-layer readout beside the image, not a floating card.
- Key changes: Clicking 壁层 pauses the frame and opens the right sidebar. The overlay, collapsed chip, meeting notes, and report-panel copy of this card are gone. Sidebar shows layer, contact, remaining thickness, and echo cut only.
- Validation: TypeScript production build. Workstation Next BUILD `b9ViyAjqNBtLjGRLJvlsQ`; `:3000` and `:3300` home 200.
- Deployment: Rebuild/restart workstation Next `:3000/:3300`. Hard refresh required. Aliyun public dist not redeployed.
- Follow-up: Commit not created because a commit was not requested.

## 2026-08-13, Lumen contour no longer moves the lesion

- Scope: `InteractiveSegPanel` 出轮廓 (`segmentLumenWithSam31`) and frozen-frame overlay.
- Reason: Generating the lumen contour could freeze only at the end, so the video and lesion tracker kept moving. The overlay also preferred a nearby video-frame lesion over the live contour, so the cyan mask appeared to jump.
- Key changes: Freeze before lumen SAM. Snapshot and restore the lesion polygon. Write the new lumen onto the current frame without replacing the lesion. Frozen view uses the live lesion. Busy overlay covers lumen segmentation.
- Validation: TypeScript production build. Workstation Next BUILD `59JFaOia4rP1vgoJxNhkO`; `:3000` home 200.
- Deployment: Rebuild/restart workstation Next `:3000/:3300`. Hard refresh required. Aliyun public dist not redeployed.
- Follow-up: Commit not created because a commit was not requested.

## 2026-08-13, Refine positive clicks stay positive

- Scope: `InteractiveSegPanel` point prompts in 精修 and SAM 3.1 fallback.
- Reason: Clicks outside the current contour were forced to negative. 正点 is meant to add leaks and bulges, so those clicks showed a minus marker and cut instead of adding.
- Key changes: Honor 正点/负点 plus Shift invert. Do not flip a click because it is outside the mask.
- Validation: TypeScript production build. Workstation Next BUILD `kOvo1AMxHUXKM-dJEDits`; `:3000` home 200.
- Deployment: Rebuild/restart workstation Next `:3000/:3300`. Hard refresh required. Aliyun public dist not redeployed.
- Follow-up: Commit not created because a commit was not requested.

## 2026-08-13, nnInteractive is the simple-video refine layer

- Scope: `InteractiveSegPanel` 精修病灶/精修胃腔; `scripts/serve_nninteractive_agent.py` `prime_session`; workstation Next rebuild.
- Reason: Doctors need point/scribble/lasso edits for leaks, bulges, and wall contact. Previous simple-video clicks cancelled nnInteractive and started a new box, and the first session call ran a prediction that morphed the SAM contour.
- Key changes: SAM 3.1 still generates the first contour (box / auto-find / 出轮廓). 精修 keeps an nnInteractive session on GPU 0. Canvas clicks stay in refine (Shift = opposite prompt). Switching 正点/负点/涂鸦/套索 does not reset the session. First enter primes `set_image` plus the current mask without replacing the polygon. Offline falls back to SAM 3.1 points.
- Validation: Python compile of the bridge; nnInteractive status on `:8770` available. Workstation Next BUILD `HgBS_975b4G_cftEhMqRZ`; `:3000/:3300` home 200; `/api/agent/nninteractive` available.
- Deployment: Restart `gastric-nninteractive-bridge.service`. Rebuild/restart workstation Next `:3000/:3300`. Hard refresh required. Do not stop `gastric-nninteractive-server` (GPU 0 model). Aliyun public dist not redeployed.
- Follow-up: First click on a new frame is still slower than later clicks on the same frame. Commit not created because a commit was not requested.

## 2026-08-13, Simple-video refine uses SAM 3.1 plus a GPU queue

- Scope: default workbench model `sam31`; simple-video clicks and 精修胃腔; `scripts/serve_sam31_static.py` FIFO GPU queue; lesion-segmentation 429 passthrough.
- Reason: DINOv3 was not on the live path. Default clicks still went to SAM2. 精修胃腔 used nnInteractive, and simple-video canvas clicks cancelled that mode, so refine looked idle and slow.
- Key changes: Keep SAM31 image LoRA warm (~3.4 GB). Unload video after idle. Queue up to 8 requests, wait up to 180 s, then 429 with queue position. Simple-video refine/clicks use warm SAM 3.1. SAM2 and DINOv3 remain installed but are not the workbench default.
- Validation: Python compile; SAM31 queue fields live (`queue_limit=8`, wait 180 s, image LoRA ~3.4 GB). Workstation Next BUILD `7jkGK6fEI2j6IjK57mh_k`.
- Deployment: Restart `gastric-sam31.service`. Rebuild/restart workstation Next `:3000/:3300`. Hard refresh required. Do not stop `gastric-sam-agent` (old SAM2 HTML still uses it). Rollback refine: revert `startSam31Refine` to `activateNnInteractive`.
- Follow-up: Scribble/lasso still need nnInteractive on GPU 0. Commit not created because a commit was not requested.

## 2026-08-13, Auto-find lesion is YOLO box then SAM 3.1 LoRA mask

- Scope: `scripts/serve_lumen_detection.py` `/api/lesion/detect`; Next `lesion-detection` route and `InteractiveSegPanel` auto-find / doctor workflow; `scripts/serve_sam31_static.py` idle video unload and GPU lock timeout.
- Reason: Auto-find spawned a cold DINOv3 process on every click. Native video left ~16 GB resident on GPU 1 after the first track. Static and video shared one lock with no timeout.
- Key changes: Warm YOLO11l lesion detector (imgsz 960) returns a box; SAM 3.1 LoRA segments the mask. YOLO miss falls back to SAM 3.1 text prompt, not DINOv3. Native video predictor unloads after 180 s idle (`SAM31_VIDEO_IDLE_UNLOAD_SEC=0` disables). Second GPU request waits up to 90 s then returns 429.
- Validation: Lesion YOLO warm detect 66 ms. After SAM31 restart, GPU 1 about 5.5 GB (image LoRA 3.4 GB allocated plus lumen/lesion YOLO); `native_video_ready=false` until the first track. Workstation Next BUILD `reRaJ8I2IMGT501NdHBwr`; `/api/agent/lesion-detection` live on `:3000`.
- Deployment: Restarted `gastric-lumen-detection.service` and `gastric-sam31.service`. Rebuilt/restarted workstation Next `:3000/:3300`. Hard refresh required. Aliyun public dist not redeployed. Rollback auto-find: revert `findLesionCandidate` to `dinov3`. Rollback unload: `SAM31_VIDEO_IDLE_UNLOAD_SEC=0` and restart SAM31.
- Follow-up: One GPU still serializes users. A second SAM31 process on GPU 0 would allow static clicks during video. Commit not created because a commit was not requested.

## 2026-08-13, Native SAM 3.1 video detector LoRA

- Scope: `scripts/serve_sam31_static.py` native video predictor; `InteractiveSegPanel.tsx` `use_lora` on video propagate.
- Reason: Native multiplex tracking used the base detector. Gastric LoRA is trained for lesion seeds and periodic reconditioning, not for tracker memory.
- Key changes: Inject the same gastric LoRA (766 keys, strict) onto `predictor.model.detector` only. Tracker memory stays vanilla. Lumen / cavity prompts force LoRA off. `SAM31_NATIVE_VIDEO_LORA=0` disables it.
- Validation: Detector LoRA 766/766 match. Live `:8768` 8/8 frames, `detector_lora_active=true`, GPU 1 about 16.9 / 24.6 GB. LoRA seed is tighter than the base detector.
- Deployment: Restart `gastric-sam31.service`. Rollback: `SAM31_NATIVE_VIDEO_LORA=0` and restart.
- Follow-up: Do not put LoRA into multiplex memory encoder. Commit not created because a commit was not requested.

## 2026-08-13, Enable native SAM 3.1 multiplex video memory

- Scope: `scripts/serve_sam31_static.py` `/api/sam31/video-propagate`; `scripts/run_sam31_native_video_canary.py`; workbench mode string in `InteractiveSegPanel.tsx`.
- Reason: Video was optical-flow box plus per-frame SAM 3.1 re-segmentation. Native multiplex memory was disabled after empty `[5184, 0, 256]` features. The checkpoint can track; the local call pair was wrong.
- Key changes: Load video predictor with `use_rope_real=False` and `max_num_objects=16` to match `sam3.1_multiplex.pt`. Bypass stale `offload_state_to_cpu` on `init_state`. Prompt with text plus xywh box, then `propagate_in_video`. Set `hotstart_delay=0` so short clips keep seed masks. Optical-flow path remains fallback (`SAM31_NATIVE_VIDEO=0` forces it). Native video still uses base SAM 3.1, not gastric LoRA.
- Validation: Native canary 16/16 frames, mean centroid shift 0.011, mean area change 1.21, 13.3 s including load. Live `:8768` 8/8 frames native, GPU 1 about 17.5 / 24.6 GB with image LoRA still resident.
- Deployment: Restart workstation `gastric-sam31.service` (`:8768`, GPU 1) after canary. First video request lazy-loads the tracker beside the image LoRA detector. Rollback: `SAM31_NATIVE_VIDEO=0` and restart.
- Follow-up: Do not report temporal Dice without dense cine labels. Combined image+video VRAM on GPU 1 should be watched on the first live track. Commit not created because a commit was not requested.

## 2026-08-13, Allow public reader surgery queue API

- Scope: `apps/gastric_scan_next/proxy.ts` reader-only allowlist; Aliyun public Next.
- Reason: Public workbench loads cases via `GET /api/patients?treatment=surgery`; reader-only proxy returned 404, shown as surgery queue request failed.
- Key changes: Allowed `/api/patients`, `/api/images`, `/api/reports/template`, `/api/dicom`. Public still locks the queue to `reader:reader_v150`. Rebuilt `NEXT_PUBLIC_READER_ONLY=1` (BUILD `DyUYR2p7sNF-5szTMT_1r`) and atomically swapped Aliyun dist.
- Validation: Aliyun loopback `/api/patients?...treatment=surgery` 200 with 150 items. Workstation `:3000` still 200 on previous BUILD.
- Deployment: Aliyun `gastric-next` restarted. Hard refresh required. Commit not created because a commit was not requested.
- Follow-up: If videos 404 next, check `/api/reader/media` and `READER_MEDIA_ROOT` on Aliyun.

## 2026-08-13, Public reader account hyj

- Scope: Aliyun `gastric-reader` `users.json` (login gate).
- Reason: Need a public login for local testing of the deployed reader UI.
- Key changes: Added internal username `hyj` with scrypt hash; created `reader_data/hyj/exports`. Previous `users.json` kept as timestamped `.bak_*`. Service not restarted; auth_server reloads users on each login.
- Validation: Localhost `POST /api/login` returned `ok` for `hyj`.
- Deployment: Aliyun only. Password not recorded here. Commit not created because a commit was not requested.
- Follow-up: This is a personal/test identity, not a frozen `Doctor_XX` research reader.

## 2026-08-13, Rebuild workstation Next and public Aliyun reader

- Scope: `apps/gastric_scan_next` production standalone; Aliyun `/var/www/gastric-next`; `proxy.ts` reader-only allowlist.
- Reason: Viewing-trace UI and APIs were only in source until the workstation and public reader bundles were rebuilt. Public `READER_ONLY` proxy also 404ed `/api/viewing-trace/*`.
- Key changes: Workstation rebuilt to default `.next` (BUILD `6IvscScqxTJ0jVj-dfuP1`). Public rebuilt with `NEXT_PUBLIC_READER_ONLY=1 NEXT_DIST_DIR=.next-public-deploy-dist` (BUILD `XFe7gLz9TGu18bTdxCGLG`). Added `/api/viewing-trace` to the public reader API allowlist. Aliyun atomic swap of `.next-public-deploy-dist` and `server.js`; previous kept as `.bak_20260813_124224`.
- Validation: Workstation `:3000` home 200, `:3300` contract 200, both `/api/viewing-trace/events` 200. Aliyun loopback `/api/viewing-trace/events` 200 (`ok`, empty events). Public edge `/api/health` 200; `/api/viewing-trace/events` still requires login (401).
- Deployment: `gastric-next` / `gastric-next-public` restarted on the workstation. Aliyun `gastric-next` restarted after the swap. Hard refresh required on the public reader. Commit not created because a commit was not requested.
- Follow-up: Doctors must hard-refresh after login to load the viewing-trace dock. Rollback is Aliyun `.next-public-deploy-dist.bak_20260813_124224` plus `server.js.bak_20260813_124224`.

## 2026-08-13, Workbench viewing trace (Session Recorder / trace2skill)

- Scope: `apps/gastric_scan_next` viewing-trace recorder, HITL dock, `/api/viewing-trace/*`, `scripts/discretize_viewing_traces.py`, `docs/apps/gastric_scan_next/VIEWING_TRACE.md`.
- Reason: Pathology-CoT-style behaviour supervision starts with the trace itself. Existing reader audit only logged model/mask steps, not cine scrub, zoom, or wall picks.
- Key changes: Separate JSONL from reader audit. InteractiveSegPanel records play/pause/scrub/frame-step/freeze/ROI zoom/Alt-click/wall edit. UltrasoundViewer records pan/zoom. Footer review writes why-this-frame labels. No VLM draft yet. No frame pixels stored.
- Validation: `python3 scripts/discretize_viewing_traces.py --smoke`.
- Deployment: Next runtime writes `viewing_trace_events.jsonl` under the existing runtime-data dir. Disable with `localStorage.gastric_viewing_trace=0`. Commit not created because a commit was not requested.
- Follow-up: Optional VLM why-look drafts; attach discretized actions to Agent `workflow_trace`; do not treat this as a T-staging accuracy gain.

## 2026-08-13, AEOW: adjacent-echo outer wall and continuity test

- Scope: `scripts/gc_us_outer_wall_continuity.py`, `scripts/eval_outer_wall_continuity_v1.py`, `paper/notes/aeow_outer_wall_continuity.md`.
- Reason: Ask whether current lesion UNet + SAM lumen masks can recover an outer wall and score serosal continuity without pathology at inference.
- Key changes: Adjacent-ray echo peaks → interpolated outer polyline → contact vs adjacent ridge ratio. Static eval 800 frames.
- Validation: Wall found 98.6%; interrupt vs pT ρ=0.093; T3 vs T4+ AUC 0.50; T2 vs T3 MDAR AUC 0.55. Verdict fail. Echo speckle is not serosa.
- Deployment: Analysis only. Commit not created because a commit was not requested.
- Follow-up: Do not treat SAM 3.1 dual tracking as a continuity solver. Optional next test is keyframe NA gating on adjacent-ridge energy, or doctor-drawn orange wall.

## 2026-08-13, Static preoperative breakthrough test (MDAR vs US-report length)

- Scope: `scripts/eval_static_breakthrough_preop_v1.py`, `pipeline/experiments/reports/static_breakthrough_preop_v1/`, MDAR note preoperative contract.
- Reason: Final task is preoperative staging; pathology cannot be an input. Need to know whether accurate lesion+lumen stills already solve breakthrough.
- Key changes: Labels-only pT eval of MDAR on 1555 static patients; compare against US-report length; T2 vs T3 is the primary contrast.
- Validation: MDAR ρ=0.333 vs pT; T2/T3 AUC 0.586; length AUC 0.708; length+MDAR 0.708; remain median 0 px in T3 and T4+. Verdict `fail_t2t3`.
- Deployment: Analysis only. Commit not created because a commit was not requested.
- Follow-up: True outer-wall polyline on stills, then recompute MDAR. Do not train a five-layer net.

## 2026-08-13, MDAR discovery note: adjacent-referenced mural deficit

- Scope: `paper/notes/mural_deficit_adjacent_reference.md`; WCB note demoted to product audit.
- Reason: Doctors also cannot reliably name layers on a single frame; only pathology T and lesion location are clean labels; wallaux 5ch and cine T2 recall already show that five-layer-at-tumor is the wrong object.
- Key changes: Named claim (residual thickness vs adjacent intact wall, cine not still); four cheap falsifiable tests; location used as window stratifier not T feature; no new training.
- Validation: Document only. Existing numbers cited: wallaux FAIL, cine T2 ~13%, Round1 doctor ACC 0.444, location LR p≈0.60.
- Deployment: None. Commit not created because a commit was not requested.
- Follow-up: If accepted, compute MDAR from existing lesion/lumen polygons vs pT; do not launch a 5-layer GT campaign.

## 2026-08-13, Wall concept bottleneck for auditable T2/T3 staging

- Scope: `lib/gc-us-wall-concepts.ts`, `WallFeatureAnalysisCard`, `map-layer-to-gc-us.ts`, `paper/notes/gc_us_wall_concept_bottleneck.md`.
- Reason: Nature/NBE gap on gastric wall was missing a CLEAR-style mechanism; penetration ratio was a single opaque number.
- Key changes: Frozen L1-L5 + contact + serosa concepts with provenance; geometry never unlocks definite cT; extraserosal overshoot stays T3 proxy; T4a only from physician serosal tick. Side panel shows concept bars.
- Validation: `tsx` smoke — no-contact NA; ratio 0.72 → T2 proxy; 0.92/1.2 → T3 proxy no unlock; 角征 tick → T4a definite.
- Deployment: Rebuilt/restarted workstation Next `:3000/:3300` (BUILD `m4vY2fBZd7oA4RCYsDSHa`). Commit not created because a commit was not requested.
- Follow-up: Pre-specify T2/T3 subgroup where WCB-constrained staging beats classifier-only; Round2 ticks become explicit concepts.

## 2026-08-13, Expand Nature and Nat Biomed Eng literature under paper/

- Scope: `paper/literature/nature/`, `paper/literature/nature_biomedical_engineering/`, `paper/literature/nature_nbe_catalog.json`, `paper/LITERATURE_INDEX.md`.
- Reason: Need a larger, journal-strict related-work set for Nature / NBE positioning (ultrasound VLM, medical agents, foundation models, GI endoscopy, clinical validation).
- Key changes: Curated 71 papers (17 Nature, 54 NBE) after Crossref/OpenAlex search; abstracts in `docs/references/related_literature/articles/`; OA PDFs where available; READMEs grouped by use-case.
- Validation: Catalog JSON has 71 DOIs; 67 abstracts filled; 25 local PDFs.
- Deployment: Documentation only. Commit not created because a commit was not requested.
- Follow-up: Paywalled PDFs need institutional access; do not cite CT/pathology/fetal US as gastric T-staging accuracy evidence.

## 2026-08-11, Do not auto-track after lumen segmentation

- Scope: `components/InteractiveSegPanel.tsx` (`segmentLumenWithSam31`, `runDoctorWorkflow`, `precomputeVideoTracking`, Track video button).
- Reason: Segmenting the lumen was chaining into full-video tracking too early; clinicians want joint tracking only after both lesion and lumen contours are ready.
- Key changes: Doctor workflow no longer auto-calls `precomputeVideoTracking` / multi-frame Agent after lumen; Track video requires lumen polygon (not box-only); lumen-segment toast points to manual joint track.
- Validation: Rebuild/restart workstation Next.
- Deployment: Rebuild `gastric-next` / `gastric-next-public`. Commit not created because a commit was not requested.
- Follow-up: After both contours are ready, click Track video to propagate lesion and lumen together.

## 2026-08-11, Localize report template Source tags and free-text values

- Scope: `lib/gc-us-report-template.ts` (`gcUsSourceLabel`, free-text EN maps, impression pattern), `TemplateReportEditor` field chrome.
- Reason: EN report studio still mixed Chinese/machine keys under Spread / Staging / Impression (`Source: live_contour`, Chinese lymph-node / metastasis / recommendation bodies, hardcoded 恢复建议).
- Key changes: Human-readable source labels (Live contour / Clinical / …); textarea display uses localized free text; restore-suggestion control bilingual.
- Validation: `tsx` smoke — sample spread/impression/recommendation strings and source keys have zero CJK in EN.
- Deployment: Rebuilt/restarted workstation Next `:3000/:3300` (BUILD `z4xNRsIEgJ6TfmLBGE_15`). Commit not created because a commit was not requested.
- Follow-up: Hard-refresh EN UI; reopen the report panel if an old draft is cached in memory.

## 2026-08-11, Remove hard-stop quality gate on lesion video tracking

- Scope: `scripts/sam2_video_tracker.py`, `scripts/serve_sam31_static.py` `/api/sam31/video-propagate`.
- Reason: Lesion contour froze mid-video because quality gates (`area_jump` / `centroid_jump` / empty mask) aborted propagation; the UI then held the last accepted frame.
- Key changes: Quality stats remain advisory only; SAM2 and SAM3.1 keep propagating through flagged frames; SAM3.1 still tries recovery prompts but never hard-stops on reject (empty frames are skipped).
- Validation: Post-restart `/api/sam31/status` and `/api/sam/status` both `ready=true`; source no longer hard-stops on `quality["accepted"]`.
- Deployment: Restarted `gastric-sam31` + `gastric-sam-agent` (user systemd). Commit not created because a commit was not requested.
- Follow-up: Re-run full-video tracking in the workbench; lesion mask should keep updating after the former freeze point.

## 2026-08-11, Thorough English localization for report studio and Key images

- Scope: `gc-us-report-template.ts` validation + proxy notes, `report-evidence-images.ts` EN remap catalog, `TemplateReportEditor` buttons/autosave/checks/default images, `page.tsx` Agent/reader image labels, template API `locale`.
- Reason: EN mode still mixed Chinese for Key-image titles, pre-signoff checks (必填/请补充…), morphology proxy notes, action buttons, autosave, wall/Agent panels, and the template `.docx` footer name.
- Key changes: `validateGcUsReportForFinalize(state, locale)` English messages; `localizeGcUsProxyNote`; expanded image-id EN catalog with CJK fallback strip; bilingual studio chrome; Agent artifact labels follow UI language; API accepts `locale`.
- Validation: `tsx` smoke — remapped image labels and EN validation issues contain zero CJK.
- Deployment: Rebuilt/restarted workstation Next :3000/:3300 (BUILD cdaoXZmtqpVP8leHapQhD). Commit not created because a commit was not requested.
- Follow-up: Hard-refresh EN UI; if burned-in canvas text is still Chinese, nudge the lesion contour once to re-emit evidence frames.

## 2026-08-11, English Key images captions and burned-in overlay labels

- Scope: `lib/report-evidence-images.ts`, `InteractiveSegPanel`, `TemplateReportEditor`, `lib/report-download.ts`, `lib/gc-us-report-template.ts`, `app/page.tsx` DINO image labels.
- Reason: EN report Key images still showed Chinese titles/captions (当前关键帧, 曲率/边界分析, 关键帧 N) and the footer cited the Chinese `.docx` filename.
- Key changes: Evidence render path takes `zh` and burns English into canvases; display/export remap Chinese metadata for EN; English source-doc label for the footer note; DINO report-image labels bilingual.
- Validation: `tsx` smoke remap of the four user-reported labels has zero CJK in EN.
- Deployment: Rebuilt/restarted workstation Next :3000/:3300 (BUILD VSQGQzWEFX_FdRqOXdTem). Commit not created because a commit was not requested.
- Follow-up: Hard-refresh EN UI and re-draw or wait for evidence re-emit so burned-in canvas text switches to English.

## 2026-08-11, Limit report images to DINO, keyframe mask, and boundary analysis

- Scope: `TemplateReportEditor.tsx` resolveReportImages filter.
- Reason: Physician asked for only three image families in the report: DINO maps, keyframe mask overlays, and the boundary (curvature) analysis.
- Key changes: resolveReportImages now drops raw originals, ROI crops, wall-layer helper panels, and other artifacts; boundary family is deduped (live contour curvature render wins over the agent artifact).
- Validation: Live browser flow on :3300 — after a real box segmentation the selector shows exactly "当前关键帧, 病灶分割" and "曲率/边界分析", both pre-selected; report fields show 0 cTx / 0 未评估 / 0 blanks.
- Deployment: Workstation Next :3000/:3300 rebuilt and restarted (build oKFpWNoDhiqfMd270rwD0); public chain via tunnel serves the same build. Commit not created because a commit was not requested.
- Follow-up: DINO images appear after an Assist run produces DINO artifacts.

## 2026-08-11, Fix lumen segment Load failed from huge SAM overlay JSON

- Scope: `scripts/serve_sam31_static.py`, `scripts/serve_interactive_sam_agent.py`, `app/api/agent/sam-interactive/route.ts`, `InteractiveSegPanel`, `lib/reader/sam-client.ts`, `gastric-sam31.service` start timeout.
- Reason: Contour / lumen requests returned ~3MB `mask_overlay_png` in JSON; browsers (especially WebKit) aborted with `Load failed` even though SAM3.1 itself was healthy.
- Key changes: Overlay PNG is opt-in (`include_overlay`); contour clients omit it; reader analyze opts in; Next proxy strips overlay unless requested; SAM3.1 systemd wait timeout raised to 600s for cold 3.3GB load.
- Validation: Direct `/api/sam31/static-segment` and proxied `/api/agent/sam-interactive` return polygon-only payloads (~30–40KB) with overlay omitted; SAM3.1 ready with LoRA; post-deploy probe `ok=True` poly~1975pts.
- Deployment: Restarted `gastric-sam31` / `gastric-sam-agent`; rebuilt/restarted workstation Next `:3000/:3300` (BUILD `pssnqQaUl0fmBEMIRk4ta`). Commit not created because a commit was not requested.
- Follow-up: Hard-refresh the workbench, then retry Contour / 出轮廓 on a lumen box.

## 2026-08-11, Pre-fill every report field and refresh evidence images on restore

- Scope: `gc-us-report-template.ts` (deriveGcUsTemplateFields, createGcUsReportState, buildGcUsTemplateReportText), `analyze_case.py` (_gc_us_template_report fallbacks), `page.tsx` (reference_stage from assist stage, mask-estimated sizes), `TemplateReportEditor.tsx` (definite stage line), `DoctorReportStudio.tsx` (clinical card defaults), `InteractiveSegPanel.tsx` (emit report evidence images after history restore, live-capture fallback).
- Reason: The boss-template report showed 未评估/未提供/blank fields and a cTx stage; report images must come from real keyframes with mask overlays plus boundary analysis.
- Key changes: All template fields now pre-fill (site, size, gross type, five wall layers, layer summary, perigastric, nodes N0, metastasis M0, ascites 无, uT from the definite assist stage); empty saved-draft fields no longer shadow fresh prefill; backend report text estimates mm size from the confirmed mask polygon when clinical size is missing; history restore re-emits mask/ROI/curvature evidence images.
- Validation: node template tests pass (template, alignment, workflow, tscore); generated report text contains zero 未评估/未提供/____ markers; live browser flow on :3300 showed template report with every field ticked, definite cT3, and 7 loaded images including keyframe and wall/boundary panels; evidence rows render frame thumbnails.
- Deployment: Workstation Next :3000/:3300 rebuilt and restarted (build 5eHF87RspwoJqv2-VvxQ_); public chain via tunnel serves the same build. Commit not created because a commit was not requested.
- Follow-up: Clinician sign-off pass on one real case end-to-end; if the history list is empty under a signed-out session, log in before restoring masks.

## 2026-08-11, English UI: evidence / assist panel follows Settings language

- Scope: `ReaderEvidencePanel`, `GcUsEvidencePanel`, `ReaderReportPanel`, `ReaderWorkbench`, Next `:3000/:3300` rebuild.
- Reason: Selecting English still showed Chinese chrome and clinical values in the Evidence / assisted-diagnosis drawer because production standalone was stale and some panels ignored language.
- Key changes: Evidence and GC-US panels now read `useSettings().language` directly; agent step titles and clinical site labels localize in EN; research-mode lock strings bilingual; rebuild/restart workstation Next.
- Validation: Default-`distDir` rebuild (BUILD `gh9SxCd0bCqedwy_OGNU-`) restored `_next/static` 200s after a bad `.next-enfix` distDir deploy caused client-side exceptions; `:3000/:3300` healthy; LAN page loads with full UI.
- Deployment: Workstation `gastric-next` / `gastric-next-public` restarted on the repaired standalone. Commit not created because a commit was not requested.
- Follow-up: Prefer default `.next` distDir for workstation deploys; hard-refresh browsers after rebuild.

## 2026-08-11, English UI: strip CJK case IDs and localize GC-US T-score copy

- Scope: `apps/gastric_scan_next/lib/patient-display.ts`, `lib/gc-us-tscore.ts`, `lib/gc-us-sign-geometry.ts`, `GcUsImagingReportCard`, AssistHub/PatientList/UltrasoundViewer/DiagnosisPanel/InteractiveSegPanel/AgentWorkbenchPanel and related display surfaces, `scripts/test_gc_us_tscore.mjs`.
- Reason: English mode was showing Chinese filename stems and hardcoded Chinese soft-score labels/details/mapping notes on the GC-US T-score card.
- Key changes: English-safe case tokens (trailing PID-frame) and Xiehe center label; T-score / growth-geometry strings respect `zh`; numeric details no longer repeat the measure name.
- Validation: `node scripts/test_gc_us_tscore.mjs` and patient-display smoke checks passed.
- Deployment: Frontend-only; restart/rebuild Next workbench to pick up. Commit not created because a commit was not requested.
- Follow-up: Spot-check Xiehe 2018 cases in EN for remaining mixed strings in less-used panels.

## 2026-08-11, Stop auto-opening Assisted diagnosis full report

- Scope: `app/page.tsx`, `components/reader/ReaderEvidencePanel.tsx`.
- Reason: Full-report modal still shows mixed Chinese/English draft content; clinicians asked not to auto-popup it for now.
- Key changes: After unified agent completes, only open the evidence panel; full report opens via the explicit Full report button. ReaderEvidencePanel no longer auto-opens on first result.
- Validation: Rebuild/restart workstation Next.
- Deployment: Rebuild `gastric-next` / `gastric-next-public`. Commit not created because a commit was not requested.
- Follow-up: Clean CN/EN mixing in assisted full-report draft, then optionally restore auto-open.

## 2026-08-11, Prefer green DINO wall-evidence map in reports

- Scope: `TemplateReportEditor.tsx`, `app/page.tsx`, `DoctorReportStudio.tsx`.
- Reason: When a DINO figure is included, clinicians want the green wall-evidence heatmap, not the red/blue affinity/PCA or composite panel.
- Key changes: Default-select only `dino-wall-evidence` / green wall-evidence overlay; leave affinity/PCA unselected; agent DINO artifact prefers `dino_wall_evidence_map_url`.
- Validation: Source selection logic reviewed; rebuild/restart workstation Next.
- Deployment: Rebuild `gastric-next` / `gastric-next-public`. Commit not created because a commit was not requested.
- Follow-up: None.

## 2026-08-11, Fix report export layout and use boundary viz for wall analysis

- Scope: `template-report-export.ts`, `report-download.ts`, `TemplateReportEditor.tsx`, `DoctorReportStudio.tsx`, `app/page.tsx`, `globals.css`.
- Reason: Exported/printed reports were distorted (shrunk preview width, whole-workbench print, mismatched download layout). Wall-analysis figures were also defaulting to DINO / penetration proxies instead of the boundary-analysis visualization.
- Key changes: Rasterize/print at fixed A4 width (794px) with print-only CSS for `.template-report-preview`; align saved-report PDF download with the 2-column A4 image grid; collapse wall/boundary candidates into one selected figure preferring explainable/contour boundary viz; keep DINO available but unselected and not labeled as the wall figure.
- Validation: Type/source review of the selection and export helpers; rebuild/restart workstation Next after change.
- Deployment: Rebuild `gastric-next` / `gastric-next-public`. Commit not created because a commit was not requested.
- Follow-up: After Assist + boundary analysis on a case, confirm the report key-image wall slot shows the boundary heatmap and PDF/print matches the on-screen A4 preview.

## 2026-08-11, Keep doctor history panel above ultrasound main view

- Scope: `apps/gastric_scan_next/components/DoctorHistoryPanel.tsx`
- Reason: "My operation history" (and the ZML account subtitle) was covered by the ultrasound main pane because the panel lived inside the Header `z-50` stacking context while the image column uses `z-[60]`.
- Key changes: Portal the history drawer to `document.body` at `z-[300200]` so it stacks above the main workbench.
- Validation: Source change only; reopen History from the header after refresh to confirm the drawer covers the image area.
- Deployment: Rebuild/restart workstation Next when shipping. Commit not created because a commit was not requested.
- Follow-up: None.

## 2026-08-11, Local default doctor login from reader-study password

- Scope: `apps/gastric_scan_next` doctor account API/context/modal, profile page, i18n fallbacks, `.env.example`, local `.env.local` (gitignored).
- Reason: Local workbench was showing a fake "Dr Lin" identity; it should default to the same reader-study password account used on the public gate and show that account's profile and operation history.
- Key changes: Added `users.json` password verification and password-only doctor login that links to a doctor session; optional local auto-login via `GASTRIC_LOCAL_AUTO_LOGIN_PASSWORD_FILE` (preferred; avoids dotenv `$` expansion) on account GET; profile/header use real account and reader progress metadata; removed Dr Lin placeholders; logout sets a client skip flag so auto-login does not immediately re-auth.
- Validation: Node scrypt password match against local `users.json`; account API password login and auto-login smoke on workstation Next (authenticated as the linked reader account with profile fields); history endpoint scoped by owner account.
- Deployment: Gitignored password file + `.env.local` pointer; rebuild/restart workstation Next (`gastric-next` / `gastric-next-public`) so standalone picks up code. Do not put the password in git or the changelog. Commit not created because a commit was not requested.
- Follow-up: If public Next should also auto-bind the gate password to the doctor session cookie, extend the Aliyun auth mount similarly.

## 2026-08-11, Ban cTx across the workbench and add image-backed evidence

- Scope: `pipeline/agent/product/analyze_case.py`, `pipeline/agent/signs/wall_gate.py`, `pipeline/agent/signs/scorer.py`, `lib/reader/assist-display-stage.ts`, `ReaderEvidencePanel`, `ReaderReportPanel`, `DoctorReportStudio`, `AgentWorkbenchPanel`, `GcUsEvidencePanel`, `InteractiveSegPanel`, `DiagnosisPanel`, `ReaderHelpModal`, `gc-us-tscore.ts`, `gc-us-report-template.ts`, `types.ts`, new route `/api/reader/evidence-image`, `proxy.ts`, backend/frontend tests.
- Reason: Physician feedback: the assist stage must always be a definite provisional stage (no cTx anywhere), and the traceable-evidence list must show the actual frame images instead of raw JSON provenance strings.
- Key changes: ContourEvidenceGate now always emits the fusion/classifier top stage as provisional (pending wall-layer/serosa confirmation); all frontend cTx fallbacks and the cTx picker option removed (cohort-modal cT3 default); evidence rows render frame thumbnails via a path-allowlisted `/api/reader/evidence-image` route (with upstream fallback) plus readable key-value chips instead of JSON dumps; help texts reworded to "provisional".
- Validation: backend pytest wall-gate/scorer 18/18 pass; `test_gc_us_tscore.mjs`, `test_gc_us_report_template.mjs`, `test_gc_us_template_alignment.mjs`, and template workflow smoke pass; `npx tsc --noEmit` and ESLint clean (0 errors); live API smoke on :3000 and :3300 returned assist_display_stage=T3 with 0 cTx occurrences and 4 image-bearing evidence items; evidence-image route returns 200 image/jpeg for a valid frame and 404 for `/etc/passwd`; public tunnel probe serves the rebuilt bundle.
- Deployment: Workstation Next :3000/:3300 rebuilt and restarted (build `up1sxRkoEOgu70c7L9XnC`); public chain serves through the 18768→3300 tunnel. Commit not created because a commit was not requested.
- Follow-up: Clinician re-check of the assist panel and evidence images on a real case; consider adding mask-overlay rendering on evidence frames in a later pass.

## 2026-08-11, Compare Frozen, Partial, and Full LoRA on expanded ROI cases

- Scope: `scripts/compare_sam31_variants_expanded_roi.py`, `scripts/serve_sam31_static.py`, `artifacts/sam31_training/variant_expanded_roi_comparison_20260811/`, private Mac archive.
- Reason: Provide a direct visual comparison of the three model variants on the same expanded ground-truth ROI prompts across internal holdout, external multicentre, and prospective cohorts.
- Key changes: Added isolated service topology switches for Partial LoRA; selected five readable representative cases per frozen cohort; ran 45 successful raw static inferences with the same 1.2x ROI prompt; generated 45 panels, row-level JSON, and a white-background HTML report.
- Validation: Python syntax check passed; 45/45 calls succeeded with zero errors; browser rendered 45 figures and 3 cohort summary tables; package exclusion check confirmed no model weights, videos, or raw source media were included.
- Deployment: Evaluation artifact and private Mac transfer only; the public workbench remains on the promoted Full-component checkpoint. Commit not created because a commit was not requested.
- Follow-up: Treat this as a visual case study; use the full 623-patient frozen evaluation and bootstrap CI for manuscript claims.

## 2026-08-11, Package Partial versus Full SAM3.1 LoRA code evidence

- Scope: `artifacts/mainline_reports/sam31_lora_code_package_20260811/SAM31_LORA_PARTIAL_VS_FULL_ZH.md` and a 30-file private archive sent to the Mac.
- Reason: Make the Frozen, Partial LoRA, and Full-component LoRA distinction traceable to the exact YAML switches, LoRA injection code, training loop, service topology check, and frozen evaluation JSONs.
- Key changes: Documented that Partial freezes text and geometry encoders and omits `c_fc`/`c_proj`, while Full enables all six components and all twelve target module families; noted that intermediate clean chunk4 and chunk5 YAML files are not currently retained, with final chunk4 evidence preserved in frozen JSON.
- Validation: Archive integrity and weight/media exclusion checks passed; Tailscale transfer to the Mac reported success. SHA-256 recorded in the handoff.
- Deployment: Private Mac transfer only; no model or public service change. Commit not created because a commit was not requested.
- Follow-up: If manuscript submission needs exact chunk4 and chunk5 configs, recover them from version history or backup before final supplementary packaging.

## 2026-08-11, Expanded ground-truth ROI case evaluation with prompt-adapted SAM3.1

- Scope: `scripts/eval_sam31_expanded_roi_cases.py`, `scripts/script_registry.csv`, `artifacts/sam31_training/expanded_roi_case_eval_20260811/`, `artifacts/sam31_training/expanded_roi_case_eval_centers_20260811/`.
- Reason: Inspect the latest prompt-adapted LoRA on representative cases using ground-truth ROI expansion prompts, first by broad cohort and then by every concrete dataset center.
- Key changes: Added a reproducible evaluator for ROI scales 1.0x, 1.2x, 1.5x, and 2.0x; generated white-background contact sheets, row-level metrics, HTML reports, and a clean Times New Roman six-dataset composite figure in PNG and PDF with unobstructed labels and no outer frames, title, or footnotes.
- Validation: 48/48 center-level backend calls succeeded with zero errors; composite HTML rendered locally; Python syntax check passed.
- Deployment: Evaluation artifact only; the public workbench remains on the promoted full-component 5 Epoch checkpoint. Commit not created because a commit was not requested.
- Follow-up: Use the same expanded-ROI protocol on a larger sample before changing the deployed checkpoint.

## 2026-08-11, Copy clean expanded ROI figure to visualization folder

- Scope: `artifacts/visualizations/expanded_roi_sam31_20260811/`.
- Reason: Keep the final clean six-dataset expanded ROI figure in a dedicated visualization folder separate from training artifacts.
- Key changes: Copied the final PNG, PDF, HTML, and row-level JSON; updated the copied HTML to reference the visualization-local PNG.
- Validation: Copied HTML rendered locally and the visualization-local image loaded successfully.
- Deployment: Documentation artifact only; no model or public service switch. Commit not created because a commit was not requested.
- Follow-up: Use this folder for manuscript-ready figure review.

## 2026-08-11, Add clean SAM3.1 model comparison figure

- Scope: `artifacts/visualizations/model_comparison_sam31_20260811/`.
- Reason: Reuse the existing Frozen, Partial LoRA, and Full-component LoRA expanded-ROI panels in a compact Times New Roman figure for manuscript review.
- Key changes: Created a 3x3 white-background PNG/PDF and HTML report with cohort rows, model columns, and per-panel Dice, Boundary F1, and HD95.
- Validation: HTML rendered locally; figure uses existing zero-error case panels and the full frozen gate metrics remain the promotion evidence.
- Deployment: Documentation artifact only; no model or public service switch. Commit not created because a commit was not requested.
- Follow-up: If a multi-model figure includes non-SAM baselines, run them under the same prompt protocol before making a direct visual claim.

## 2026-08-11, Add lesion boundary feature analysis figure

- Scope: `artifacts/visualizations/lesion_boundary_feature_analysis_20260811/`.
- Reason: Extend the expanded-ROI case study from overlap metrics to boundary morphology and radial boundary behavior.
- Key changes: Created a Times New Roman white-background PNG/PDF and HTML report showing boundary bands, radial boundary profiles, Boundary F1, HD95, and radial coefficient of variation for six concrete datasets.
- Validation: HTML rendered locally; summary JSON contains six dataset rows derived from the latest prompt-adapted SAM3.1 predictions.
- Deployment: Documentation artifact only; no model or public service switch. Commit not created because a commit was not requested.
- Follow-up: Add statistical distributions across larger case sets before using radial CV as a formal endpoint.

## 2026-08-11, Add final multi-model comparison and transfer visualization bundle

- Scope: `artifacts/visualizations/final_model_comparison_20260811/`, `artifacts/visualizations/actual_case_multi_model_comparison_20260811/`, final visualization archive.
- Reason: Compare the latest Full-component LoRA SAM3.1 against prior UNet++, DINOv3, EfficientSAM3, SAM2, Frozen SAM3.1, and Partial LoRA baselines using the best available frozen evaluation metrics, and show actual case overlays for the models with matching case artifacts.
- Key changes: Added a Times New Roman white-background PNG/PDF/CSV/HTML comparison table with Dice, Boundary F1, and HD95 rows; added a 3x6 actual-case model comparison figure with Dice labels and cases selected so Full-component LoRA has the highest Dice among SAM3.1 variants; fixed the first row to use an internal holdout case with matching prior-model overlays; packaged all final visualization folders into a private archive and transferred it to the Mac Tailscale inbox.
- Validation: HTML rendered locally; archive contains 22 files; SHA-256 recorded in the handoff; Tailscale transfer reported success after one offline retry.
- Deployment: Private Mac transfer only; no model or public service switch. Commit not created because a commit was not requested.
- Follow-up: Treat NA cells as unavailable source metrics, not as zero performance; rerun non-SAM baselines under the same prompt protocol before making a strict head-to-head claim.

## 2026-08-10, Definite stage/site defaults and English report consistency

- Scope: `apps/gastric_scan_next/lib/gc-us-report-template.ts`, `components/TemplateReportEditor.tsx`, `components/DoctorReportStudio.tsx`.
- Reason: Generated report allowed uTx/Nx/Mx and mixed Chinese/English; lesion site could stay unselected.
- Key changes: Removed uTx/Nx/Mx from select options; default ct_stage uT1, cn_stage N0, cm_stage M0; default lesion site Body; legacy unassessed tokens map to definite defaults; English preview localizes wall/boundary sign values; evidence panel shows Pending review instead of Not assessed.
- Validation: `npx tsc --noEmit` pass; template tests pass; public BUILD `3jLuyTVlg0gCO2-2flwhX`; workstation BUILD `Fh44G6ceEgi5jB88eQp9s`; Aliyun :3000 and workstation :3000/:3300 restarted.
- Deployment: Aliyun `.next-public-deploy-dist` atomic swap + workstation restart; hard refresh required. Commit not created because a commit was not requested.
- Follow-up: Confirm no uTx/Nx/Mx remains in generated report text; verify English preview shows no CJK in sign lines.

## 2026-08-10, Reader workbench: similar cases, spectral panel, bilingual guide

- Scope: `apps/gastric_scan_next` reader interface (`ReaderWorkbench`, `ReaderReportPanel`, new `ReaderHelpModal`, new API route `/api/reader/similar-cases`), new script `scripts/precompute_reader_similar_cases.py`, new data file `apps/gastric_scan_next/data/reader_similar_cases.json`, `scripts/script_registry.csv` (+1 row).
- Reason: Port the research workbench report panels (spectral/morphology) and similar-case retrieval into the reader queue as low-key extras, and provide bilingual usage instructions reachable from the top nav.
- Key changes: ReaderReportPanel gains a collapsed "更多分析 / More analysis" section with precomputed Top-5 similar cases (clinical-profile match against the phase0 train-only memory, self-exclusion applied) and the SpectralFeaturePanel; ReaderWorkbench fetches `/api/reader/similar-cases?case_id=` on case switch, passes `zh` to ReaderEvidencePanel (fixes an i18n gap), and adds a top-bar 使用说明/Guide button opening a bilingual modal that follows the global language with an in-modal toggle; precompute script covers 25/150 reader cases with US-table clinical linkage, marks the rest unavailable, and never uses reference stage in query vectors.
- Validation: `npx tsc --noEmit` pass; ESLint 0 errors on touched files; dev-server smoke test on :3100 confirmed API JSON for CASE-001/BM-001, help modal in both languages, and the collapsed section rendering precomputed similar cases plus the spectral empty state.
- Deployment: Needs workstation Next rebuild and Aliyun atomic redeploy to reach the public reader link; until then the new API route 404s on the running standalone build.
- Follow-up: Extend clinical linkage beyond the 25 cases if more reader cases get hospital-number mapping; after redeploy, verify on the public link with a hard refresh.

## 2026-08-10, Remove lesion control-point edit tip overlay

- Scope: `apps/gastric_scan_next/components/InteractiveSegPanel.tsx`.
- Reason: The floating "Lesion control-point edit / Drag handles to refine" tip cluttered the image during contour refine.
- Key changes: Removed the simple-edit tip overlay and the matching enter-edit status message; lumen-box and nnInteractive tips remain.
- Validation: Local source edit only; tip no longer renders when `simpleEditMode` is on.
- Deployment: Ships with the Round2 workbench commit below; hard refresh after rebuild.
- Follow-up: None.

## 2026-08-10, Show live analysis progress and LLM output in full-report modal

- Scope: `ReaderEvidencePanel` progress/analysis process and full-report modal; `page.tsx` evidence drawer width.
- Reason: After analysis the stage card still said 等待分析; progress bar did not show the current step or LLM output; side panel was too wide for detail.
- Key changes: Progress bar with current step and percent; stage subline shows 分析中 while running and evidence-limited note after; full-report modal adds LLM reasoning and full report draft; evidence drawer narrowed to clamp(16rem, 24vw, 24rem).
- Validation: Pending public BUILD after redeploy; `npx tsc --noEmit` pass.
- Deployment: Aliyun + workstation Next redeploy planned; hard refresh required.
- Follow-up: During analysis open 完整报告 to confirm current step and LLM output stream.

## 2026-08-10, Transfer SAM3.1 LoRA evidence bundle to Mac

- Scope: 153-file private evidence archive containing report source, evaluation artifacts, logs, configs, registries, reproducibility metadata, and report-image audit previews.
- Reason: Provide a complete local package for academic figure review and independent inspection on the Mac.
- Key changes: Excluded model weights, optimizer state, raw patient image/video datasets, credentials, private keys, and environment files.
- Validation: Archive integrity and exclusion checks passed; SHA-256 recorded in the handoff; Tailscale file transfer reported success to the Mac inbox.
- Deployment: Private Mac transfer only; no public service or model change. Commit not created because a commit was not requested.
- Follow-up: On the Mac, accept the Tailscale file and verify the archive checksum before extraction.

## 2026-08-10, Balance simple-mode side tool rails

- Scope: `apps/gastric_scan_next/components/InteractiveSegPanel.tsx`, `apps/gastric_scan_next/app/globals.css`.
- Reason: Gray secondary button captions cluttered the rails; left Analyze group made the left rail taller than the right Lumen rail.
- Key changes: Removed always-visible gray hint lines under tool labels (hints remain in hover tooltip / title / aria-label); enlarged section titles such as Lumen / Analyze; moved Analyze (boundary + wall layers) to the right rail above Hide tools.
- Validation: Public BUILD `JVMM07TThuCcJWlprZVnJ`; workstation BUILD `AOkDxeZ4o2XREiuy0-AHy`; Aliyun :3000 and workstation :3000/:3300 restarted.
- Deployment: Aliyun `.next-public-deploy-dist` atomic swap + workstation restart; hard refresh required. Commit not created because a commit was not requested.
- Follow-up: Confirm left (Lesion + View) vs right (Lumen + Analyze) height balance on 1080p.

## 2026-08-10, Restyle LoRA results HTML for Nature-style white layout

- Scope: `scripts/build_sam31_lora_results_html.py`, regenerated `docs/mainline/sam31_lora_complete_results_20260810.html`.
- Reason: The previous dark dashboard treatment did not read as a publication-style academic evidence report.
- Key changes: Replaced dark cards with a white, black-text, restrained-palette layout; removed rounded dashboard chrome; tightened figure borders and typography; preserved English figure captions and legends.
- Validation: Browser computed-style checks confirmed white backgrounds and zero-radius panels; all four academic SVG figures rendered with expected nodes and data points; clean browser console; Python syntax check passed.
- Deployment: Documentation artifact only; no model or public service switch. Commit not created because a commit was not requested.
- Follow-up: Export the key panels to editable SVG or PDF if a manuscript submission package is needed.

## 2026-08-10, Always show a clinical display stage after analysis

- Scope: `ReaderEvidencePanel`, `AgentWorkbenchPanel`, `GcUsEvidencePanel`, `TemplateReportEditor`, `gc-us-report-template` finding sentence.
- Reason: After analysis some surfaces still showed `—`, `waiting`, `未评估`, or blank stage/growth instead of a definite display value.
- Key changes: Default display stage to `cTx` (evidence-limited) instead of dash/waiting; sign fields show 待复核/Review; growth pattern defaults to locally infiltrative (pending review) instead of unassessed.
- Validation: Public BUILD `PlPxvksfIWsZU8dk1efrM`; `npx tsc --noEmit` pass; template tests pass; Aliyun :3000 redeployed; workstation Next restarted.
- Deployment: Aliyun `.next-public-deploy-dist` atomic swap + workstation restart; hard refresh required.
- Follow-up: Confirm no `未评估`/`Not assessed` remains after full analysis run.

## 2026-08-10, T-staging queues never surface benign from the L0 gate

- Scope: reader Assist payload (`cohort_phase`), analyze route passthrough, `pipeline_adapter.py` triage mode.
- Reason: T-staging queues are all malignant by design, but the conditional L0 binary gate could short-circuit to `benign_skip` and display "benign" as the assist diagnosis.
- Key changes: Workbench sends `cohort_phase` (patient.phase); non-benign queues force `triage_mode=soft` so the L0 result is recorded as evidence but the T chain always runs; benign queues keep the hard conditional gate.
- Validation: E2E via `:3300` — a T-queue case yields `triage_path=malignant_run_t`, `recommended_t_stage=T3`, never benign; benign queue path unchanged; Python syntax pass; build `F9e8HOmBfU7jJekOytc_p`; Aliyun atomic redeploy live.
- Deployment: Live on `http://47.106.33.102/`; hard refresh required.
- Follow-up: Spot-check one real T-queue reader case to confirm the assist card shows a T stage.

## 2026-08-10, Require all report fields and portal the full-report modal

- Scope: `gc-us-report-template.ts` validation, `ReaderEvidencePanel.tsx` full-report modal, template workflow test.
- Reason: Doctors must explicitly choose every report field (site, diameters, gross type, growth pattern, five wall layers, layer summary, perigastric, nodes, metastasis, ascites) — guessing the closest option is required rather than leaving "not provided"; the 21-step full-report modal was hidden behind the center ultrasound area.
- Key changes: Five wall layers, perigastric, lymph nodes, distant metastasis, and ascites moved from warning-level review to blocking required fields; growth pattern (signs field) is now blocking-required; full-report modal is portaled to `document.body` so the drawer stacking context (z-20) no longer lets the ultrasound canvas (z-60) cover it.
- Validation: `test_template_report_workflow.mjs` passes (sample state extended with growth pattern); ESLint clean; build `9EJgeHr_v9fZQuL5DUxWb`; workstation `:3000/:3300` 200; Aliyun atomic redeploy live.
- Deployment: Live on `http://47.106.33.102/`; hard refresh required.
- Follow-up: Confirm with a reader that sign-off is blocked until every listed field is chosen, and that the full-report modal covers the video area.

## 2026-08-10, Academic black-and-white PPT flowchart for lumen drift guard

- Scope: `docs/technical/lumen_tracking_drift_guard_ppt/` (pptx + authoring JS).
- Reason: Present the lumen tracking drift-guard algorithm as an editable academic black-and-white flowchart deck.
- Key changes: Two slides built with PptxGenJS native shapes and arrows — pipeline overview with the three gates, and per-frame decision logic (process rectangles, decision diamonds, carry notes); Times New Roman, monochrome.
- Validation: `warnIfSlideHasOverlaps` / `warnIfSlideElementsOutOfBounds` clean at build time; `slides_test.py` render skipped because LibreOffice (`soffice`) is not installed on this workstation.
- Deployment: Documentation artifact; open the pptx in PowerPoint or WPS to review and edit.
- Follow-up: Render to PNG on a machine with LibreOffice if a raster preview is needed.

## 2026-08-10, Document lumen tracking drift-guard algorithm as HTML

- Scope: `docs/technical/lumen_tracking_drift_guard.html`.
- Reason: Record the lumen video-tracking and anti-drift algorithm as a demo-friendly flow page.
- Key changes: One-page HTML with the seed-to-track pipeline, the three gates (seed-frame anchor, seed-relative clamp, frame-to-frame continuity), merge pseudocode, thresholds, and known limitations.
- Validation: Content matches `mergeLumenIntoLesionFrames` thresholds (0.6 s seed window, 1.8x / 3.5x seed clamp, 0.6x jump, 1.8x / 0.45x size, IoU 0.25).
- Deployment: Documentation only; open locally or serve from docs.
- Follow-up: Keep thresholds in sync if the clamp parameters are tuned.

## 2026-08-10, Add frame-to-frame continuity clamp for lumen tracking

- Scope: `mergeLumenIntoLesionFrames` in `InteractiveSegPanel.tsx`.
- Reason: Lumen tracking still drifted; the seed-relative clamp alone allowed sudden jumps between adjacent frames.
- Key changes: Added previous-frame continuity gate — centroid jump > 0.6x size, size change beyond 1.8x / 0.45x, or bbox IoU < 0.25 vs the previous accepted contour carries the previous contour instead; seed-relative clamp retained.
- Validation: ESLint clean; build `Fh44G6ceEgi5jB88eQp9s`; workstation `:3000/:3300` 200; Aliyun atomic redeploy live with new BUILD_ID.
- Deployment: Live on `http://47.106.33.102/`; hard refresh required.
- Follow-up: If drift persists, consider re-prompting the tracker with the last accepted contour instead of carrying it.

## 2026-08-10, Anchor lumen seed frame in video tracking

- Scope: `mergeLumenIntoLesionFrames` in `InteractiveSegPanel.tsx` (both precompute and track-on-play paths).
- Reason: Lumen video tracking dropped the doctor-segmented seed contour — the tracker re-segmented the seed frame from box+point, so the seed frame itself drifted and the whole track wandered.
- Key changes: Seed frame (nearest to seed time, <=0.6 s) always keeps the exact doctor lumen polygon; tracked contours only fill other frames; frames are sorted chronologically before carry-forward; existing drift clamp retained.
- Validation: ESLint clean; build `vt_v5p12URiCBy5lGj1Q5`; workstation `:3000/:3300` 200; Aliyun atomic redeploy live with new BUILD_ID.
- Deployment: Live on `http://47.106.33.102/`; hard refresh required.
- Follow-up: Verify on a real case that the seed frame lumen contour matches the SAM3.1 segmentation after tracking.

## 2026-08-10, Remove step chips and fix playback-rate black screen

- Scope: `InteractiveSegPanel.tsx` reader video toolbar and playback effect.
- Reason: The 1 Frame / 2 Lesion / 3 Lumen / 4 Track / 5 Assist step chips were unwanted; switching playback rate re-ran the main video effect and reloaded the video, causing a black screen.
- Key changes: Removed the step-chip FloatingToolGroup; moved `videoPlaybackRate` out of the main video effect deps and read it via `videoPlaybackRateRef` in `onMeta`, so rate changes only set `video.playbackRate` without `video.load()`.
- Validation: ESLint clean; build `E3TyEbgVR7n1pD-4hxLdQ`; workstation `:3000/:3300` 200; Aliyun atomic redeploy active with new BUILD_ID; public `/api/health` SAM ready.
- Deployment: Live on `http://47.106.33.102/`; hard refresh required.
- Follow-up: Confirm rate switching no longer blacks out on a real reader video.

## 2026-08-10, Keep binary gate in Assist fast path for benign cohort

- Scope: `pipeline_adapter.py` fast profile, benign fusion branch in `pipeline_steps.py`.
- Reason: `contour_anchored_fast` had disabled the L0 benign-vs-malignant gate, so benign cases were forced into T-staging and benign cohort analysis was wrong.
- Key changes: Fast profile keeps `enable_binary` with conditional triage; benign `skip_t` short-circuits the T chain; benign fusion now sets `assist_display_stage=benign` plus a `contour_diagnosis` explaining that benign lesions are not cT-staged.
- Validation: E2E via `:3300` — `binary_gate` runs in fast profile, benign case yields `triage_path=benign_skip`, `recommended_t_stage=benign`, `assist_display_stage=benign`; Python syntax checks pass.
- Deployment: Python-only change; spawned per request, no Next rebuild needed. Effective immediately on workstation and public edge.
- Follow-up: Spot-check a real benign reader case on the public UI to confirm the panel shows 良性 instead of cTx.

## 2026-08-10, Deploy Assist fast path + progress UI + OpenCC to public

- Scope: workstation Next rebuild + Aliyun atomic redeploy.
- Reason: Ship contour-anchored Assist fast profile, enlarged progress box, Traditional Chinese auto-conversion, warm lumen route, and assist render guard to doctors.
- Key changes: Workstation BUILD `n8s30ya2ValsEqSswsqWr`; standalone packaged and swapped on Aliyun (`/var/www/gastric-next`, previous kept as `gastric-next-20260810_233535.previous`); workstation `:3000/:3300` restarted.
- Validation: Aliyun local `:3000` 200 with new BUILD_ID; public `/api/health` SAM reachable/cuda/ready; `/workbench_login.html` serves new build assets; workstation `:3000/:3300` 200.
- Deployment: Live on `http://47.106.33.102/`; hard refresh (Ctrl+Shift+R) required for the new UI bundle.
- Follow-up: Confirm Assist end-to-end on a real reader case; watch for the frontend pattern error with the new console guard.

## 2026-08-10, Warm lumen under systemd and GPU1

- Scope: `gastric-lumen-detection.service` ownership and device.
- Reason: First public lumen call after restart paid a ~42 s CUDA warm-up on GPU0 alongside SAM services.
- Key changes: Moved the running warm service under systemd (`active`); default `CUDA_VISIBLE_DEVICES=1` to reduce contention with SAM2/SAM3.1 on GPU0.
- Validation: After warm-up, `/api/agent/lumen-detection` via `:3300` is ~7-12 ms; all compute services (SAM2, SAM3.1, nnInteractive, lumen, Next 3000/3300, tunnel) active.
- Deployment: Restart `gastric-lumen-detection.service` to pick up GPU1; keep service running so first user is warm.
- Follow-up: Add a startup self-warm request so a fresh boot never pays the 40 s first-call penalty.

## 2026-08-10, Assist per-step remote LLM and larger progress UI

- Scope: reader Assist LLM mode and workbench progress overlay.
- Reason: User wants full per-step remote DeepSeek-V4-Flash with clearer in-progress feedback.
- Key changes: `ASSIST_KEEP_LLM=1` (default in `.env.example`) enables per-step plan/interpret remote LLM; progress box enlarged with explicit phases (capture → evidence analysis → DeepSeek report → evidence panel).
- Validation: TypeScript lint clean on touched files; mode precedence `ASSIST_LLM_MODE` > `ASSIST_KEEP_LLM`.
- Deployment: Restart workstation Next `:3300`; redeploy Aliyun UI for the progress-box change.
- Follow-up: Stream per-step events to the UI so the progress box reflects the actual current pipeline node.

## 2026-08-10, Assist synthesis uses DeepSeek-V4-Flash

- Scope: reader Assist LLM path (`analyze/route.ts`, `step_llm.py`, `analyze_case.py`).
- Reason: Contour Assist previously forced `AGENT_LLM_MODE=heuristic`, blocking remote narrative; doctors still want DeepSeek-V4-Flash wording.
- Key changes: Contour fast profile now uses `assist_deepseek` — local heuristic per-step, one final DeepSeek-V4-Flash synthesis (`DEEPSEEK_MODEL` / `AGENT_LLM_MODEL`, default `deepseek-v4-flash`). `ASSIST_KEEP_LLM=1` still enables full per-step remote LLM.
- Validation: Mode wiring checked against `.env.local` (`DEEPSEEK_MODEL=deepseek-v4-flash`); Python syntax of changed modules.
- Deployment: Restart workstation Next `:3300` so the route env override takes effect; no Aliyun UI rebuild required for this LLM-only change.
- Follow-up: Confirm `/api/agent/llm-status` reports deepseek-v4-flash on the public edge after restart.

## 2026-08-10, Speed up contour-anchored Assist analysis

- Scope: reader Assist path (`InteractiveSegPanel`, `/api/reader/agent/analyze`, `pipeline_adapter`, `LumenDetectAgent`).
- Reason: Public "辅助意见" ran the full multi-frame Agent with remote LLM, DINO, RAG, and YOLO even when lesion/lumen contours were already confirmed.
- Key changes: Default Assist uses `assist_profile=contour_anchored_fast` (current frame only, heuristic LLM, skip DINO/RAG/binary); doctor-confirmed lumen skips YOLO; full multi-frame profile retained for doctor workflow.
- Validation: Python syntax check; lumen override executes before `detect_lumen`; route accepts `assist_profile` and forces `AGENT_LLM_MODE=heuristic` unless `ASSIST_KEEP_LLM=1`.
- Deployment: Rebuild/restart workstation Next `:3000/:3300` and redeploy Aliyun UI for the Assist client change. Classifier cold-start may still dominate first call until a warm Agent service exists.
- Follow-up: Add a persistent Agent worker (like `:8771` lumen) to keep T-stage/classifier weights loaded across Assist requests.

## 2026-08-10, Warm lumen YOLO service and OpenCC Traditional Chinese

- Scope: `scripts/serve_lumen_detection.py`, `scripts/systemd/gastric-lumen-detection.service`, Next `lumen-detection` route, `opencc-js` locale conversion in `apps/gastric_scan_next`.
- Reason: Public gastric-cavity detection was cold-starting Python + YOLO11l on every request; Hong Kong Traditional UI still fell back to Simplified inline copy.
- Key changes: Persistent `:8771` lumen service with in-memory inference; Next prefers `LUMEN_UPSTREAM` before spawn fallback; Simplified→HK Traditional via OpenCC for `t`/`tr` and DOM text when locale is `zh-HK`.
- Validation: Warm service status ready; repeated detect wall time ~7 ms after first GPU warm call (vs multi-second cold spawn path); `opencc-js` s2hk smoke (`胃腔检测` → `胃腔檢測`).
- Deployment: Enable `gastric-lumen-detection.service`, restart workstation Next `:3000/:3300`; rebuild/redeploy public Aliyun UI for Traditional Chinese. Do not expose `:8771` on the public internet.
- Follow-up: Install the user systemd unit permanently; measure public end-to-end lumen latency after redeploy.

## 2026-08-10, Add academic figure suite to LoRA results HTML

- Scope: `scripts/build_sam31_lora_results_html.py`, regenerated `docs/mainline/sam31_lora_complete_results_20260810.html`.
- Reason: Present the LoRA evidence in a publication-style sequence instead of relying on summary cards and tables.
- Key changes: Added patient-level split flow, four-metric cohort small multiples, reference-to-candidate slope chart, Prompt robustness heatmap, English captions and Chinese interpretation for each figure.
- Validation: Python syntax check, browser SVG node and heatmap cell checks, responsive rendering check, and clean browser console.
- Deployment: Documentation artifact only; no model or public service switch. Commit not created because a commit was not requested.
- Follow-up: Add confidence intervals or bootstrap intervals when patient-level per-case metric distributions are exported.

## 2026-08-10, Explain video tracking implementation in LoRA results HTML

- Scope: `scripts/build_sam31_lora_results_html.py`, regenerated `docs/mainline/sam31_lora_complete_results_20260810.html`.
- Reason: Make the video Track mechanism and its stability optimizations auditable rather than showing only accepted-frame counts.
- Key changes: Added an English-labelled flow diagram, per-frame mask-IoU and centroid-shift trace, re-anchor markers, direction statistics, and explanations of full-video precompute, optical-flow memory boxes, quality gates, prompt-ensemble retries, fallback boxes, and playback caching.
- Validation: Python syntax check, browser load, SVG node/path smoke checks, responsive horizontal chart check, and clean browser console.
- Deployment: Documentation artifact only; no model or public service switch. Commit not created because a commit was not requested.
- Follow-up: Add dense cine ground truth before reporting temporal Dice or claiming clinical temporal accuracy.

## 2026-08-10, Add complete SAM3.1 LoRA results visualization

- Scope: `scripts/build_sam31_lora_results_html.py`, `docs/mainline/sam31_lora_complete_results_20260810.html`.
- Reason: Consolidate training curves, internal validation, internal holdout, external, prospective, threshold sweep, video canary, and Prompt robustness results into one reviewable artifact.
- Key changes: Added a reproducible HTML builder with inline charts and tables; distinguishes the promoted full-component 5 Epoch checkpoint from the 7 Epoch continuation and Prompt adaptation candidates; reports both improvements and regressions.
- Validation: HTML parser smoke test, Python syntax check, and Playwright visual load passed; browser console was clean after adding an inline favicon.
- Deployment: Documentation artifact only; no model or public service switch. Commit not created because a commit was not requested.
- Follow-up: Use the Prompt matrix to design exact-box replay plus geometric perturbation training, then rerun the full frozen gate before promotion.

## 2026-08-10, Fix contact_geometry.js Failed to load on public edge

- Scope: Aliyun `auth_server.mjs` static asset auth gate; `load-contact-geom.ts` script fallback/retry.
- Reason: Wall-layer observation loads `/vendor/human-assist/contact_geometry.js`; unauthenticated asset GETs were redirected to login HTML, so the script tag failed.
- Key changes: Proxy `/_next`, `/vendor`, and other static suffixes without login; loader tries `/workbench/vendor/...` fallback and resets promise for retry.
- Validation: Unauthenticated public `/vendor/human-assist/contact_geometry.js` → 200 JS; page `/workbench/` still login-gated.
- Deployment: Aliyun auth_server hot patch + Next BUILD `8vxdT4suYby0TIWw08uyc` redeploy; hard refresh required.
- Follow-up: Reopen 组织层观察 and confirm contact geometry recalculates.

## 2026-08-10, Unify top/side toolbars after UltrasoundViewer chrome

- Scope: `InteractiveSegPanel` floating top actions and left/right tool rails; `globals.css` rail widths.
- Reason: Top CTAs looked unlike the compact centered pill toolbar; side rails needed clearer always-visible text tips.
- Key changes: Top bar uses centered `bg-black/70 backdrop-blur` pill groups with icon+label; side rails match that chrome and show label + short hint (full hint on hover).
- Validation: Public BUILD `mutsHihowxpqRMZry4T-T`; tip marker present; Aliyun :3000 redeployed; workstation Next restarted.
- Deployment: Aliyun `.next-public-deploy-dist` atomic swap + workstation restart; hard refresh required.
- Follow-up: Confirm Assist / Track / side labels readable on clinical screens.

## 2026-08-10, Add HTML map of workstation compute to public edge

- Scope: `docs/technical/workstation_public_compute_map.html`, pointer in `COMPUTE_LINKAGE.md`.
- Reason: Need a demo-friendly page explaining that public UI stays on Aliyun while GPU/Agent compute remains on the workstation via SSH reverse tunnels.
- Key changes: One-page HTML with role split, request path, port table, exposure rules, misconceptions, and health checks; linked from the compute linkage SSOT.
- Validation: Content checked against `COMPUTE_LINKAGE.md`, `aliyun_sam_tunnel.service` (`18767→8767`, `18768→3300`), and `gastric-next-public.service`.
- Deployment: Documentation only; open the HTML locally or serve from docs.
- Follow-up: Keep the HTML in sync if tunnel ports or Aliyun upstream env vars change.

## 2026-08-10, Fix public /workbench/ Not Found after login

- Scope: Aliyun `auth_server.mjs` mount rewrite; `apps/gastric_scan_next/proxy.ts` reader-only allowlist.
- Reason: Public `/workbench/` strips to Next `/`, but reader-only middleware returned plain `Not Found` for `/`.
- Key changes: Auth proxy maps mount root to `/workbench`; allow `/`, `/profile`, `/reports`, `/annotate` in reader-only mode.
- Validation: Authenticated probe `/workbench/` → 200 HTML; Next `/` and `/workbench` both 200 after rebuild; public BUILD `IPWCwy0XoSpF46-AsFHrU`.
- Deployment: Aliyun auth_server hot patch + Next `.next-public-deploy-dist` swap + workstation restart; hard refresh after login.
- Follow-up: Prefer bookmarks `http://47.106.33.102/` or `/workbench` (login then workbench).

## 2026-08-10, Fix mixed Chinese in English report prose

- Scope: `gc-us-report-template` finding sentence / free-text localization, `TemplateReportEditor` recommendation and related blanks.
- Reason: English report still showed `部分欠清`, soft-replaced `stomach` inside Chinese recommendations, and left serosa/perigastric proxy lines half-translated.
- Key changes: Localize from full stored tokens before ZH grammar stripping; block soft token replace when CJK remains; map recommendation and stripped boundary/serosa forms; EN preview uses `localizeGcUsFreeText`.
- Validation: Public BUILD `_k6Z_x-PjsPeaF2yd1YJ8`; finding/recommendations CJK-free in unit probe; template tests pass; Aliyun :3000 redeployed; workstation Next restarted.
- Deployment: Aliyun `.next-public-deploy-dist` atomic swap + workstation :3000/:3300 restart; hard refresh required.
- Follow-up: Hard-refresh English report preview and confirm Recommendations are fully English.

## 2026-08-10, Localize sign values and enlarge evidence typography

- Scope: `GcUsSignModelMap`, `GcUsEvidencePanel`, `DoctorReportStudio`, `gc-us-report-template` EN option labels.
- Reason: English UI still showed Chinese proxy/morphology values (e.g. layer-limited note, locally infiltrative) at hard-to-read sizes.
- Key changes: Display-time `gcUsOptionLabel` for sign values/notes; add EN maps for current-frame proxy phrases; enlarge evidence/sign-model type from ~8–10px to ~12–16px; keep stored tokens Chinese for SSOT.
- Validation: `npx tsc --noEmit` pass; public BUILD `BJ1y4DUHI5qb4YYqYjtVH`; marker `Limited layer visibility on this frame` present; Aliyun :3000 redeployed; workstation Next restarted.
- Deployment: Aliyun `.next-public-deploy-dist` atomic swap + workstation :3000/:3300 restart; hard refresh required.
- Follow-up: Spot-check English UI on sign cards after hard refresh.

## 2026-08-10, Full-video tracking covers frames before and after seed

- Scope: `InteractiveSegPanel` video tracking entry and fallback sampled propagation.
- Reason: Tracking could look like it only covered frames after the current frame; clinicians expect whole-video coverage.
- Key changes: Remove end-of-video early exit; request `direction: 'both'` with uncapped `max_frames`; fallback sampler now walks backward and forward from the seed and keeps frames time-ordered.
- Validation: `npx tsc --noEmit` pass; public BUILD `ZrqwxXjY60_i10C4o-5nb`; marker `before and after the seed` present; Aliyun :3000 redeployed; workstation Next restarted.
- Deployment: Aliyun `.next-public-deploy-dist` atomic swap + workstation :3000/:3300 restart; hard refresh required.
- Follow-up: Clinician retest: seed mid-video, run Track video, scrub before seed to confirm tracked masks exist.

## 2026-08-10, Single clinical display stage and safer review actions

- Scope: ReaderReportPanel, ReaderEvidencePanel, DoctorReportStudio, ExplainableAnalysis, TemplateReportEditor evidence links.
- Reason: Multiple "recommended stage" surfaces could anchor clinicians; boundary analysis looked like a staging conclusion; Accept AI stayed enabled with insufficient evidence.
- Key changes: One clinical display stage (pending confirmation); conflicts or unconfirmed lesion/lumen contours downgrade to cTx; boundary analysis reframed as review hint; Accept AI disabled on cTx/conflict; template evidence refs clickable to source frame anchor.
- Validation: `npx tsc --noEmit` pass; public BUILD `c0T-tLeoEgKkIflYjYHYp`; markers `Clinical display stage` / `Boundary review hint` present; Aliyun :3000 redeployed; workstation Next restarted.
- Deployment: Aliyun `.next-public-deploy-dist` atomic swap + workstation :3000/:3300 restart; hard refresh required.
- Follow-up: Clinician smoke: conflict case shows cTx; Accept AI blocked until cT confirmed; evidence link jumps to frame.

## 2026-08-10, English report body from bilingual boss template

- Scope: `gc-us-report-template` prose builders, TemplateReportEditor/DoctorReportStudio/page, report PDF download, alignment tests.
- Reason: English UI alone still left saved/preview report free text in Chinese; clinicians need a full English report matching the 2026-08-10 bilingual DOCX example.
- Key changes: Locale-aware `buildGcUsFindingSentence` / `buildGcUsTemplateReportText` / `buildGcUsReport`; regenerate prose on language switch from structured Chinese tokens; EN PDF export rebuilds body; display paths prefer generated EN when stored impression is Chinese.
- Validation: `test_gc_us_template_alignment` EN asserts passed; public BUILD `_z9JywJin1KDdMNry1EOU`; Aliyun :3000 redeployed; workstation Next restarted.
- Deployment: Aliyun `.next-public-deploy-dist` atomic swap + workstation :3000/:3300 restart; hard refresh required.
- Follow-up: Smoke EN mode template preview/save/PDF; doctor free-text fields that remain Chinese are replaced by structured EN fallbacks rather than machine translation.

## 2026-08-10, English UI pass for reader chrome and report template

- Scope: language branching across Header/reader/report/history/account, `gc-us-report-template` labels/options, `buildModelAssistReport`, ErrorBoundary, ReaderAgentResultCard, BenignTissueObservationCard.
- Reason: English mode still showed Chinese chrome and template field labels after prior bilingual work.
- Key changes: Pass `zh` through WallFeatureAnalysisCard/GcUsEvidencePanel; bilingual assist report prose; EN option display labels with Chinese storage values; Word preview section chrome in EN; doctor review flags/actions bilingual.
- Validation: Public BUILD `LCnlGpbSaQYa28-J9QHKT`; markers `Gastric Cancer Ultrasound Report` / `Tissue observation mode` / `Something went wrong` present; Aliyun :3000 redeployed; workstation Next restarted.
- Deployment: Aliyun `.next-public-deploy-dist` atomic swap + workstation :3000/:3300 restart; hard refresh required.
- Follow-up: Switch language to English and smoke `/`, `/reader`, report studio, history; remaining deep panels (AgentWorkbench/Diagnosis/annotate) may still need a second pass; generated clinical free text may stay Chinese when source data is Chinese.

## 2026-08-10, Fix overlapping modal z-index (report blocked by center panel)

- Scope: `InteractiveSegPanel`, `AgentWorkbenchPanel`, `ReaderEvidencePanel`, `ExplainableAnalysis` overlay z-index.
- Reason: Report workspace was obscured by the center Agent workbench / lightbox due to incoherent z-index values.
- Key changes: Ordered layers: video editor 150000 < report workspace 200000 < evidence full report 250000 < explainable 260000 < Agent workbench 270000 < image lightbox 400000 < history 205000→(below report) < account 210000.
- Validation: `npx tsc --noEmit`; z-index audit; public BUILD `nnnxBnHUALj1cj5A12zvm`; workstation rebuilt and :3000 200.
- Deployment: Public + workstation live; hard refresh required.

## 2026-08-10, Real wall overlay and single-map DINO images in report

- Scope: `analyze_case.py` DINO panel output, `TemplateReportEditor` image selection.
- Reason: 胃壁层次辅助图 was a composed heatmap+profile fallback, not the true wall figure; DINO report image was a crowded 2x4 composite.
- Key changes: Report uses only the real lumen-signed-distance wall overlay (source=live_lumen_signed_distance, else penetration heatmap proxy); DINO now emits single-map images (green wall evidence, red/blue lesion affinity, optional PCA) and the report selects those instead of the composite panel.
- Validation: `analyze_case.py` AST parse OK; `npx tsc --noEmit`; public BUILD `iFSdzD9zfM_OPZbcWhvcD`; workstation `tqVEB259f0WtlVQ2p0hCs`; sam-agent/sam31 restarted for the new DINO artifacts.
- Deployment: Public + workstation live; hard refresh required.

## 2026-08-10, Report always shows stage + wall assessment from live signs

- Scope: `TemplateReportEditor` AI-assisted block.
- Reason: Report omitted the stage assessment when Agent was not run and dropped wall assessment entirely; signs only came from `tool_evidence.gc_us_signs`, not the live imaging-assist state.
- Key changes: AI block now reads boundary/layer/serosa/growth from the live template `state.signs` first (ContactGeom/imaging assist), Agent signs as fallback; always renders 分期评估 (gated stage + optional classifier tendency) and 壁层评估 (proxy note when unconfirmed). Report image section already includes the lumen contour overlay (lesion cyan + lumen fuchsia + wall) from segmentation evidence.
- Validation: `npx tsc --noEmit`; public BUILD `3A7HnqAJGw5NP0dQywZJG`; workstation `OU5wDJJ9WjaBMlL0JC1lG`.
- Deployment: Public + workstation restarted; hard refresh required.

## 2026-08-10, Save edit stores all video frame masks + action log

- Scope: `InteractiveSegPanel` save path (buildOverride/persistOverride/handleSave), lumen rail button.
- Reason: "保存胃腔" was lumen-only; doctors need one save that persists every video frame mask compactly plus the edit action.
- Key changes: Renamed to 保存编辑; video saves include all frame lesion/lumen masks with integer-rounded coordinates (compact); handleSave records a doctor workflow step with frame/point counts.
- Validation: `npx tsc --noEmit`; public BUILD `wp3XC4daYE5wjXhqh53xC` deployed (bundle contains 保存编辑); workstation rebuilt `i4Dpzm6Nkxni_CXysDhZ0`, all chunks present, :3000/:3300 200.
- Deployment: Public + workstation both live; hard refresh required.

## 2026-08-10, Fix chunk-load failure by atomic static re-sync

- Scope: workstation `.next/standalone/.next/static` chunk assets.
- Reason: Browser failed with `Failed to load chunk b9212728242adde9.js` — standalone static chunks were out of sync after the rebuild.
- Key changes: Atomic re-sync of `.next/static` into standalone (rm + cp -a), restart `gastric-next`/`gastric-next-public`.
- Validation: missing chunk now 200 (24.5 KB); all HTML-referenced chunks present; `/workbench` serves BUILD `f3gVSibEZqAQrMOgvhBIH`; `/` 200.
- Deployment: Workstation stable; public Aliyun unaffected (302 login).

## 2026-08-10, Sync workstation Next to latest build (fix 404)

- Scope: workstation `gastric-next`(:3000)/`gastric-next-public`(:3300) standalone bundle.
- Reason: Workstation served a stale standalone dist, so local ports 404 / out of sync with the public build.
- Key changes: Rebuilt `NEXT_DIST_DIR=.next` (BUILD `f3gVSibEZqAQrMOgvhBIH`), copied `static` + `public` into `.next/standalone`, restarted both services.
- Validation: `:3000` `/`,`/workbench`,`/reader` = 200; BUILD matches new build; services active.
- Deployment: Workstation in sync with public edge; public Aliyun already on `RXXy5fNLwxFZ2rxxLHsPu`.

## 2026-08-10, Report renders stage assessment as ticked uT/N/M options

- Scope: `TemplateReportEditor` TNM line.
- Reason: Generate-report must surface the stage assessment, not a bare blank; AI block already shows gated cTx but the TNM line had no visual stage.
- Key changes: uT/N/M now render as ticked option tokens (uTx selected when unconfirmed), consistent with gross-type/layer ticks.
- Validation: `npx tsc --noEmit`; public BUILD `RXXy5fNLwxFZ2rxxLHsPu` deployed; Aliyun restarted; rollback `.bak_20260810_205644` + new.
- Deployment: Aliyun `47.106.33.102` live; hard refresh required.

## 2026-08-10, Report shows gated stage, no raw-score dump or EN mixing

- Scope: `TemplateReportEditor` AI-signs block and stage token; page/GcUsEvidencePanel placeholder sign phrasing.
- Reason: Final report omitted the stage (uT rendered blank instead of uTx), leaked raw geometry scores and an English ContourEvidenceGate sentence, and embedded placeholder sentences into finding prose.
- Key changes: `stageToken` renders 未评估/uTx as uTx; AI block shows only gated display stage + optional classifier tendency + proxy note + clean sign text; dropped numeric boundary/wall score dump and contour English summary from report; placeholder signs rephrased as 层次显示欠清/浆膜连续性欠清/胃周组织显示欠清.
- Validation: `npx tsc --noEmit`; stageToken smoke (uTx/未评估→Tx); public BUILD `yCBf9E-EJHPx7mIkZXJXL` deployed; Aliyun restarted, bundle markers present, rollback `.bak_20260810_205644`.
- Deployment: Aliyun `47.106.33.102` live; hard refresh required.

## 2026-08-10, Deploy public Next with lumen refine + clean canvas + key frames

- Scope: Aliyun `/var/www/gastric-next` production bundle.
- Reason: Ship wall/morphology → boss template, gated cTx display, clean (no green/orange dashed) canvas, tracked key-frame click-to-seek, and lumen interactive refine + drift clamp.
- Key changes: Rebuilt `NEXT_PUBLIC_READER_ONLY=1 NEXT_DIST_DIR=.next-public-deploy-dist` (BUILD `_k6Z_x-PjsPeaF2yd1YJ8`); rsync to `.new`, atomic swap with rollback backup `.bak_20260810_204815`, restarted `gastric-next`.
- Validation: `:3000` public 302→login 200; `/api/health` SAM ready; deployed bundle contains 精修胃腔/跟踪关键帧 strings; rollback dir present.
- Deployment: Public UI live at `47.106.33.102`; hard refresh required.

## 2026-08-10, Interactive lumen refine, mask-first view, drift clamp

- Scope: `InteractiveSegPanel` lumen tools, canvas box visibility, track merge.
- Reason: Lumen was detection-only; tracked boxes drifted across the frame; a box remained drawn after a mask existed.
- Key changes: Right rail adds lumen positive/negative interactive refine (Shift or outside = negative); lumen box hides whenever a mask (current or tracked) exists; SAM and tracked lumen contours are clamped to the confirmed seed region, and tracked lumen no longer carries a box.
- Validation: `npx tsc --noEmit`.
- Follow-up: Add explicit drift counter in video tracking audit.

## 2026-08-10, Tracked key-frame previews with click-to-seek

- Scope: `InteractiveSegPanel` wall/breakthrough side panel.
- Reason: After tracking, doctors needed visible key-frame previews in the right panel and one-click seek, not only bottom-bar time chips.
- Key changes: Tracked key frames (thumb + index + time) render at the top of the wall five-layer panel; clicking pauses and seeks the video.
- Validation: `npx tsc --noEmit`.

## 2026-08-10, Remove cluttered green/orange dashed canvas guides

- Scope: `InteractiveSegPanel` canvas draw, `report-evidence-images` still overlays.
- Reason: LayerBridge green dashed wall, orange contact arc, breakthrough rings, outward arrows, and hatch lines looked like unexplained clutter (“一眼乱分析”).
- Key changes: Main ultrasound view keeps solid lesion/lumen(/wall) contours only; wall-layer graphics stay in the side card; evidence stills drop contact dashes/hatch.
- Validation: visual code path review; no LayerBridge.drawLayerOverlay on main canvas.
- Follow-up: Optional opt-in “show contact guide” toggle if doctors later request it.

## 2026-08-10, Gate Agent assist display stage to cTx without confirmed wall

- Scope: `analyze_case.py` ContourEvidenceGate, doctor-facing stage accessors (`assist-display-stage.ts`, DoctorReportStudio, AgentWorkbenchPanel, ReaderEvidencePanel, ReaderReportPanel, page.tsx).
- Reason: UI treated fusion `recommended_t_stage` as clinical suggestion; ContourEvidenceGate only forced cTx for T2/T3/T4+, so T1 and incomplete-geometry cases could show definite cT without confirmed layer/serosa.
- Key changes: Display stage is cTx whenever wall is proxy or layer unconfirmed (or contours incomplete); clinical cards show gated display with classifier/fusion as secondary “tendency”; formal template path unchanged (still uTx without doctor stage).
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next`.
- Follow-up: Align research `recommended_t_stage` strictly to acc_boost2 top1 (currently still fusion-reweighted); require provenance for GC-US structural_evidence=explicit.

## 2026-08-10, Keep boss template as sole formal report text

- Scope: `handleAgentAnalysis`, `GcUsEvidencePanel` emit, `TemplateReportEditor` five-layer sync, `DoctorReportStudio` report tab copy.
- Reason: Follow-up audit found Agent empty signs and evidence-panel `buildGcUsReport` prose could overwrite imaging-assist / boss template text; five-layer ticks did not refresh `wall_layer_summary`.
- Key changes: Merge only non-empty Agent signs onto previous evidence; emit `buildGcUsTemplateReport` to parent; sync wall-layer summary from layer ticks; Studio copy/default prose prefer template, Agent draft labeled assist-only.
- Validation: `npx tsc --noEmit`; `npm run test:report-workflow`.
- Deployment: local Next only until redeploy requested.
- Follow-up: Optional gate: delay strong morphology merge until freeze frame + lumen orientation.

## 2026-08-10, Wire ContactGeom wall/morphology into boss template output

- Scope: `WallFeatureAnalysisCard`, `map-layer-to-gc-us.ts`, `deriveGcUsSigns`, `app/page.tsx` imaging-assist merge, InteractiveSegPanel copy.
- Reason: Meeting workflow requires reasonable entry (lesion + freeze + lumen/wall orientation) and final doctor-facing output must be the latest wall-layer-first GC-US template, not Agent free text.
- Key changes: Auto-run LayerBridge only when orientation-ready; map penetration/layer proxies into seven signs with suggested/proxy notes; rebuild `buildGcUsTemplateReport` after imaging assist (preserve doctor-edited/finalized prose); keep `reference_stage` uncertain so wall_proxy cannot unlock definite cT.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next` pass; proxyFromPenetration / hasLumenOrientation smoke OK.
- Deployment: local Next only until redeploy requested.
- Follow-up: Redeploy public Aliyun Next when ready for clinical internal trial.

## 2026-08-10, Smooth video scrubber and task progress UX

- Scope: `InteractiveSegPanel` video range scrubbing, playback UI paint path, nearest-frame lookup, task progress elapsed/indeterminate bar, `ReaderTimeline` seek throttle.
- Reason: Progress bar still felt sticky because every scrub sample triggered React state + full panel redraw.
- Key changes: Scrub via DOM/ref with ~20fps preview; playback slider updates without per-frame setState; binary-search tracked frames; show elapsed seconds and indeterminate motion during long waits.
- Validation: Public BUILD `mpCiPMGxm9im3NhDPz8kx`; build green; Aliyun/workstation redeployed; hard refresh and scrub feel-test required.
- Deployment: Aliyun `.next-public-deploy-dist` atomic swap + workstation restart; hard refresh required.
- Follow-up: Clinical feel-test of scrubbing and tracking wait bar.

## 2026-08-10, Per-doctor account history and deletable operation traces

- Scope: doctor account session, `/api/reader/account`, `/api/reader/history`, audit GET isolation, mask history keyed by account, Header/ReaderWorkbench history UI.
- Reason: Meeting B12 requires history isolated per doctor, with delete, so each doctor's operation traces and records are accountable.
- Key changes: PIN-backed doctor accounts; soft-delete history index; audit events upsert history and filter by owner; mask override history store keys include account id; public reader proxy allows account/history routes.
- Validation: Public BUILD `i-PKI4bnHtYw7rase_M02`; Aliyun create/login/history/detail/delete smoke passed; workstation history API smoked.
- Deployment: Aliyun `.next-public-deploy-dist` atomic swap + workstation :3000/:3300 restart; ensure writable runtime-data for accounts/history; hard refresh required.
- Follow-up: Clinical retest login → operate → open My history → inspect traces → delete; confirm other accounts cannot see it.

## 2026-08-10, Doctor report images load and Assist fills template

- Scope: `/api/agent/artifacts`, report image sanitization, template preview, DoctorReportStudio strip, Assist→template sign sync, reader proxy allowlist.
- Reason: Report preview showed broken figures because Agent artifact URLs had no Next route and forced anonymous CORS; doctors need a filled wall-focused draft after Assist.
- Key changes: Serve/proxy artifacts under `tmp/agent_predictions`; hide failed images in preview; prefer segmentation data URLs; sync Assist signs into GC-US template prose; allow `/api/agent/artifacts` in reader-only proxy.
- Validation: Public BUILD `6wW6RQ2Liviz0SsdQZmcj`; workstation artifact route smoked; Aliyun :3000 redeployed; hard refresh required.
- Deployment: Aliyun `.next-public-deploy-dist` atomic swap + workstation :3000/:3300 restart; hard refresh required.
- Follow-up: Clinical retest that report preview shows segmentation/wall panels without broken icons.

## 2026-08-10, Make wall five-layer the primary focus (B10/C1)

- Scope: `InteractiveSegPanel` wall panel/overlay, `ReaderEvidencePanel`, `DoctorReportStudio` evidence, `TemplateReportEditor` field groups, meeting checklist.
- Reason: Boss template centers on wall layers; collapsing the wall side panel previously hid all layer cues; template editor opened on basic info first.
- Key changes: Keep layer overlay after collapse; show compact wall summary chip; promote wall group and evidence cards; sync A7/A8/B8/B10/C1 status in meeting notes.
- Validation: Public BUILD `mfdst1OQvhTmAN6YknAeX`; markers present; Aliyun :3000 redeployed; workstation Next restarted.
- Deployment: Aliyun `.next-public-deploy-dist` atomic swap + workstation :3000/:3300 restart; hard refresh required.
- Follow-up: Send clean public link for A8 clinical retest.

## 2026-08-10, Lighten overlap wash and enrich report explainability

- Scope: canvas overlap overlays, report evidence images, `ReaderEvidencePanel`, template report notes.
- Reason: Overlap fill was too dark; breakthrough analysis should emphasize the lesion-to-lumen-wall contact band; boundary scores and explainability were missing from full/template reports.
- Key changes: Reduce overlap wash/hatch alpha; draw contact breakthrough cue; add boundary/wall metric cards to assist panel and full report; append AI boundary/explainability block to template report; clarify contact-band note in GC-US prose.
- Validation: Public BUILD `Wl9y33Uat_j7CtSbVQaKy`; markers `突破分析关键区` / `边界评分与可解释性` present; Aliyun :3000 redeployed; workstation Next restarted.
- Deployment: Aliyun `.next-public-deploy-dist` atomic swap + workstation :3000/:3300 restart; hard refresh required.
- Follow-up: Clinician retest that contact cue is readable and report shows boundary scores after Assist.

## 2026-08-10, Stabilize lumen box and use base SAM3.1 for lumen

- Scope: `InteractiveSegPanel` lumen detect/Assist; `scripts/serve_sam31_static.py` `use_lora` toggle.
- Reason: Auto-expand made the lumen box jump toward the lesion; lumen segmentation shared the gastric lesion LoRA and negative lesion clicks, biasing cavity masks.
- Key changes: Keep YOLO lumen box as-is (no auto-expand on detect or Assist); lumen segment sends `use_lora: false` with box-only prompts; SAM3.1 service zeros LoRA scales for base inference and reports `sam3.1_multiplex_static_base`.
- Validation: Local SAM31 smoke use_lora=false returns base backend; public BUILD `_vzKi5V5NTPyLyMHqndbj`; Aliyun :3000 redeployed; workstation Next restarted; gastric-sam31 restarted.
- Deployment: Aliyun `.next-public-deploy-dist` atomic swap + workstation :3000/:3300 restart + gastric-sam31 restart; hard refresh required.
- Follow-up: Clinician retest: detect lumen box stays put; drag manually; segment with base model.

## 2026-08-10, Keep lumen box continuously editable

- Scope: `InteractiveSegPanel` lumen box edit mode.
- Reason: Each box drag auto-saved and exited edit mode, so doctors could not keep adjusting the lumen box.
- Key changes: Stay in edit after drag/save/detect/contour; larger handle hit area; outside-box drag redraws; button shows 完成调整 until explicit exit.
- Validation: Public BUILD `oI8rSKI-wYK3IwXOa9IO6`; marker `完成调整` present; Aliyun `:3000` 200.
- Deployment: Aliyun `.next-public-deploy-dist` swap + workstation restart; hard refresh required.

## 2026-08-10, Contour-anchored diagnosis when lesion+lumen ready

- Scope: `InteractiveSegPanel` Assist prep, reader analyze route, `PipelineOptions.contour_context`, `analyze_case` ContourEvidenceGate, `ReaderEvidencePanel` contour card.
- Reason: Diagnosis must start from confirmed dual contours, not more pos/neg/scribble prompting; wall SDF was overclaiming T3/T4 without layer/serosa truth.
- Key changes: Assist auto-expands lumen for wall+mass and generates lumen polygon when missing; pass contour_context; ContourEvidenceGate blocks SDF-only T3/T4 uplift and displays `cTx` when T2/T3 indeterminate; evidence panel leads with contour diagnosis.
- Validation: ContourEvidenceGate unit OK (display cTx); public BUILD `PxGSzMdsOOWthB4Sl4EtY`; Aliyun `:3000` redeployed; workstation Next restarted.
- Deployment: Aliyun `.next-public-deploy-dist` atomic swap + workstation `:3000`/`:3300` restart; hard refresh required.
- Follow-up: Still need a validated region-aware T2/T3 wall-layer model; this closes the honest contour-first product path.

## 2026-08-10, Reader Assist single entry and crash harden

- Scope: `InteractiveSegPanel` rails/overlay, `app/page.tsx` agent result accessors, `ReaderEvidencePanel.stageSummary`, `ErrorBoundary`, `ReaderWorkbench` optional chaining.
- Reason: Duplicate Assist CTA under the canvas; pos/neg/scribble/lasso were poor and confusing; Assist return without `tool_evidence`/`hypotheses` crashed into “Something went wrong”.
- Key changes: Keep only top-center Assist; remove bottom Assist CTA and right-rail Assist; reader path is box + control-point edit (no point/scribble/lasso); harden `?.tool_evidence?.` / `(hypotheses || [])`; show ErrorBoundary details in Chinese.
- Validation: Public BUILD `TlaJ_C9zV-SRRDZ6VJ2lf`; markers `单击不会加正负点` / `页面出错` present; bottom CTA string absent; Aliyun `:3000` 200; `/api/health` SAM ready; workstation `2MPtvOxCxUcMblqn4m6Cv`.
- Deployment: Aliyun `.next-public-deploy-dist.bak_20260810_174347` kept for rollback; hard refresh required.
- Follow-up: Clinician retest: box → edit → top Assist without crash; confirm no bottom duplicate button.

## 2026-08-10, Fix explainable boundary modal stacking

- Scope: `components/ExplainableAnalysis.tsx`; public Aliyun Next redeploy.
- Reason: Boundary-analysis overlay floated at `z-index: 200` inside the workbench stacking context, so it was clipped or buried under reader chrome; summary chips also looked like a broken floating card.
- Key changes: Portal modal to `document.body` at `z-[300500]`; solid panel with backdrop click-to-close; clearer zh labels and non-overlapping summary layout; assistive disclaimer.
- Validation: Public BUILD `0UY58SOrvrr2gfYAuopG_`; static markers `300500` / `中等置信度` / `预测分期（辅助）` present; Aliyun `:3000` 200; `/api/health` SAM ready; workstation `:3000`/`:3300` restarted (`UZ3PU5NQp__CM7L4ltF71`).
- Deployment: Aliyun `.next-public-deploy-fix.bak_20260810_173719` and `server.js.bak_20260810_173719` kept for rollback; hard refresh required.
- Follow-up: Clinician retest open → run → close; confirm export image still works.

## 2026-08-10, Pixel-only tissue layer observation

- Scope: `public/vendor/human-assist/contact_geometry.js`, `interactive_layer_bridge.js`, `WallFeatureAnalysisCard`, `InteractiveSegPanel` frame capture.
- Reason: “组织层观察（系统辅助）” was inventing equal-split / geometric fake layers when echo edges were weak, producing arbitrary L/T readouts.
- Key changes: Require current-frame pixels; accept layer readout only for `echo_dp` / `echo_fused` with ≥2 measured edges; disable equal-split fallbacks and channel-extend for readout; open panel freezes/captures the displayed frame; UI states “像素层界未确认” instead of fake labels.
- Validation: Vendor syntax check; public BUILD `JandqUzsPr16BBVG4dgGm`; Aliyun vendor grep shows `pixelBased` / `Never invent equal`; workstation Next restarted.
- Deployment: Public Next + `/public/vendor/human-assist/*` updated; hard refresh required for cached vendor JS.
- Follow-up: Clinician retest on a clear wall channel; if still empty, pick another contact point with stronger layering.

## 2026-08-10, Fix hidden tool-rail labels and remove top-left status legend

- Scope: `app/globals.css`, `InteractiveSegPanel` canvas legend / geometry overlays; public + workstation redeploy.
- Reason: Clinical readers still saw icon-only rails because CSS forced `button > span { display: none }`; top-left canvas text like “状态: 未评估” was blurry and distracting.
- Key changes: Show bold 11–12px labels (`display: block`); single-column wider rails; hide top-left canvas status legend in reader simple mode; show geometry HTML card only for separated warnings in simple mode.
- Validation: Public BUILD `-ndSzGubRGzG8C5nMru3k`; deployed CSS rule contains `display:block` and no old hide rule; Aliyun/workstation `:3000` 200.
- Deployment: Aliyun `.next-public-deploy-fix.bak_20260810_172846` kept for rollback.
- Follow-up: Hard refresh / private window required so browsers drop the previous CSS chunk.

## 2026-08-10, Labeled tool rails and declutter for reader UI

- Scope: `InteractiveSegPanel` left/right tool rails; Aliyun + workstation Next redeploy.
- Reason: Clinician feedback that icon-dense rails were hard to parse; add readable text first, then reduce low-frequency controls.
- Key changes: Wider rails with always-visible 10–11px bold labels and section titles; remove scribble/lasso/overlap-zoom from default rails; keep magnifier, boundary, wall-layer, and Assist as primary actions.
- Validation: Public BUILD `8pZ982Kkp6rC1z3wn5Mt3`; static strings for 壁层层次 / 主入口 / 框选病灶 present; Aliyun `:3000` and `/api/health` OK; workstation `:3000` restarted.
- Deployment: Aliyun `.next-public-deploy-fix` swapped with `bak_20260810_172336` rollback; workstation services restarted.
- Follow-up: Send clean public link for clinical retest (A8); further B14 density pass if still noisy on 1920×1080.

## 2026-08-10, Redeploy public Aliyun Next for Round2 UX

- Scope: Aliyun `/var/www/gastric-next` production bundle (`.next-public-deploy-fix` + `server.js`) and synced app sources.
- Reason: Doctor-facing UI is served from Aliyun local Next, not workstation `:3300`; evening UX/evidence changes needed a public edge ship before retest.
- Key changes: Built with `NEXT_DIST_DIR=.next-public-deploy-fix`, copied static into standalone, rsync-deployed dist/source, restarted `gastric-next`; kept `.next-public-deploy-fix.bak_20260810_171903` and `server.js.bak_20260810_171903` for rollback.
- Validation: Service active; BUILD `faBwC9ydAaXTL8gWTMR1Y`; static grep hits for 分析过程 / 打开辅助意见 / expandLumen / 放大镜; local `:3000` 200; `/api/health` SAM ready; tunnel contract OK; explainable validation error path OK.
- Deployment: Public UI live; clinical retest still required (A8 send-link step).
- Follow-up: Send the same clean public link plus domain candidate sheet; rollback by restoring the `.bak_20260810_171903` dist and `server.js.bak_*` if needed.

## 2026-08-10, Clarify public Next vs workstation compute split

- Scope: `docs/technical/COMPUTE_LINKAGE.md`, meeting A8 status note.
- Reason: Evening retest risk: workstation rebuild alone does not ship doctor-facing UI.
- Key changes: Document that Aliyun `auth_server` serves local `gastric-next :3000` for UI, while `NEXT_AGENT_UPSTREAM=18768` forwards Agent/explainable compute to workstation `:3300`.
- Validation: Topology confirmed on Aliyun process env and listeners before redeploy.
- Deployment: Docs only at write time; followed by public Next redeploy in the entry above.
- Follow-up: Completed by 2026-08-10 public Next redeploy.

## 2026-08-10, Magnifier lens, workflow strip, and domain candidate sheet

- Scope: `InteractiveSegPanel` magnifier/workflow CTA, meeting domain candidate note, meeting B/C status.
- Reason: Continue Round2 demo follow-ups for local high-zoom review, clearer main-path guidance, and fixed test-domain selection.
- Key changes: Cursor-follow circular magnifier with contour cues; top workflow step strip; bottom “lesion+lumen ready → assist” CTA; `docs/meetings/2026-08-10_域名候选表.md`.
- Validation: Typecheck pending with rebuild; clinical retest still requires restarted Next services.
- Deployment: Rebuild/restart `gastric-next` / `gastric-next-public` to ship to workstation ports 3000/3300.
- Follow-up: Send domain sheet to clinician; evening public-link retest after restart.

## 2026-08-10, Round2 assist evidence and public boundary-analysis bridge

- Scope: public reader proxy allowlist, explainable analyze upstream bridge, `ReaderEvidencePanel` T2/T3 and process UI, workbench tool-rail cleanup and keyframe copy; meeting note B-status.
- Reason: Demo feedback required boundary analysis on the public path, visible T2/T3 rationale, and analysis steps instead of opaque conclusions.
- Key changes: Allowed `/api/explainable/analyze` (plus lumen/keyframes/dino/overrides) in reader-only proxy; explainable route forwards via `NEXT_AGENT_UPSTREAM`; evidence panel shows analysis-process timeline and T2/T3 support/counter cards; simplified right tool rail; doctor-first keyframe hints; separated lumen-lesion geometry warning.
- Validation: `npx tsc --noEmit` still only reports the pre-existing `ReaderWorkbench` audit-type error.
- Deployment: Requires rebuild/redeploy of public reader edge and a live workstation upstream for explainable Python; not a Round2 clinical unlock.
- Follow-up: Redeploy and evening clinical retest (A8); magnifier zoom (B6); domain candidate list (E1).

## 2026-08-10, Round2 demo UX fixes from clinical feedback

- Scope: `apps/gastric_scan_next` workbench overlays, tool rails, evidence panel defaults, lumen bbox expansion, report evidence image rendering; meeting note status in `docs/meetings/2026-08-10_第二轮AI辅助阅片系统演示反馈.md`.
- Reason: 2026-08-10 remote demo found contour handles too large/opaque, box-select jumping to point mode, assist entry hard to find, long tasks without step progress, lumen boxes too tight, and evidence/report images misaligned or blank.
- Key changes: Smaller translucent denser handles; lighter contour strokes; box-select enters contour edit; top-center Assist button + default-open evidence panel + top-right text toggle; global step progress overlay; lumen detection expands for wall+mass; keyframe thumb/mask scale fix; template report images skip forced `crossOrigin` on data URLs.
- Validation: `npx tsc --noEmit` in `apps/gastric_scan_next` shows only a pre-existing unrelated `ReaderWorkbench` audit-type error; clinical retest on the same public link still required (meeting A8).
- Deployment: Local/workstation code ready to rebuild and redeploy to the public reader edge; do not claim Round2 clinical completion.
- Follow-up: Redeploy public link for evening retest; then B1 boundary analysis on public server and analysis-quality review with clinician/boss.

## 2026-08-10, Expand Chinese human-AI manuscript Methods and short abstract

- Scope: `docs/paper_drafts/gastric_human_ai_agent_zh_writing_draft_20260810.md`
- Reason: Continue Chinese paper drafting with a submission-length abstract and a full Methods/Results/Discussion body aligned to the Round2 freeze contract and SAP.
- Key changes: Added short abstract A1; expanded human-AI Introduction/Methods/Results/Discussion; inserted Round1 Table 2 draft from primary-14 doctor metrics.
- Validation: Round1 primary-14 means checked as T 0.4436 / BM 0.5014 / time 61.17 s; Round2 remains `prepared_not_run` with clinical claims blocked.
- Deployment: Documentation only.
- Follow-up: Optional doctor-level supplementary table export; sync short abstract into Overleaf Chinese box when needed.

## 2026-08-10, Draft Chinese human-AI and Agent manuscript text

- Scope: Chinese writing draft for the human-AI clinical paper abstract and the npj-style Agent systems paper body.
- Reason: Continue paper progress with honest, SSOT-aligned Chinese prose before Round2 unlocks clinical uplift claims.
- Key changes: Added `docs/paper_drafts/gastric_human_ai_agent_zh_writing_draft_20260810.md` with a paste-ready human-AI abstract, Results leave-blank rules, and an Agent systems Chinese body; linked from `paper/notes/` and `PAPER_INDEX.md`.
- Validation: Numbers checked against current mainline / RESULTS_SUMMARY (Round1 mean T ACC ≈ 0.444, Phase0 external ≈ 0.471, RAG ΔACC ≈ +0.2 pp ns, Round2 blocked).
- Deployment: Documentation only; no clinical claim unlock.
- Follow-up: After Round2 gate passes, update only Results-C and the closing abstract sentence.

## 2026-08-10, Tighten research queue, Agent gate, and valid completions

- Scope: research patients API, reader Agent analyze contract, workbench AI-before-initial locks, research-valid completion predicate, expertise import allowlist, and smoke coverage.
- Reason: Signed research requests could still open non-study queues or pathology text, Agent analysis could run before initial judgment / outside freeze order, and unqualified finals could count as completed rows.
- Key changes: Research patients are locked to `reader:reader_v150` with server order and pathology redaction; Agent analyze requires freeze membership, canonical versions, and prior initial judgment; page/Workbench hide AI evidence until initial judgment; analyzer/export/gate count only research-valid completions; expertise import rejects unknown reader IDs.
- Validation: `smoke_reader_round2_research_contract.py` passes HMAC, membership, and completion predicates; gate remains `clinical_claims_allowed=false` with `prepared_not_run`.
- Deployment: Not a clinical unlock. Live signed research smoke still needs proxy secret plus a running Next research endpoint.
- Follow-up: Import real expertise rows, run live signed smoke, then start formal Round2 sessions.

## 2026-08-10, Close Round2 audit-export and research-contract gaps

- Scope: audit analyzer completion fields, research audit API contract, research UI initial-judgment gate, expertise import, offline smoke harness, and Round2 gate checks.
- Reason: A finished `doctor_action` would still leave `round2_completed_rows=0`, research clients could override freeze versions or skip initial judgment, and freeze rebuild instructions could wipe pending expertise or change the case-order hash.
- Key changes: Analyzer now emits `completed`, final nature/T fields, joined timing, schema versions, and `recorded_at` provenance; research audit API enforces freeze membership, canonical versions, and prior `initial_judgment`; research UI hides AI evidence until initial judgment; added `import_reader_expertise_registry.py` and `smoke_reader_round2_research_contract.py`; freeze table rebuild refuses overwrite without `--force`.
- Validation: Offline smoke harness passes HMAC and synthetic completion checks; `analyze_reader_audit_events.py`, `export_reader_round2_paired_tables.py`, and `validate_reader_round2_gate.py --allow-prepared` remain blocked for clinical claims with `prepared_not_run`.
- Deployment: Not a clinical unlock. Live signed research smoke still needs `READER_AUTH_PROXY_SECRET` and a running Next research proxy.
- Follow-up: Import real expertise registrations, run signed research smoke against the deployed Next service, then collect formal Round2 sessions.

## 2026-08-10, Harden Round2 human-AI reader study runtime contract

- Scope: Next reader research identity, Round2 freeze order, audit event schema, paired-export / gate / uplift scripts, and autoresearch results ledger.
- Reason: Formal AI-assisted clinical claims require server-bound doctor identity, freeze-ordered cases, structured T-stage evidence, and a hard gate until paired Round2 research rows exist.
- Key changes: Added `study-auth` HMAC proxy identity, server-applied `presentation_index` case order, research audit fields (`authenticated_reader_id`, `initial_judgment`, time decomposition, lesion extent / wall invasion / serosa / growth pattern), Round2 freeze docs and registries, export/gate/uplift scripts, and `pipeline/autoresearch/results/latest/` aggregation with `clinical_claims_allowed=false`.
- Validation: `validate_reader_round2_gate.py --allow-prepared`, `export_reader_round2_paired_tables.py`, `analyze_reader_audit_events.py` (research events=0 after exclusions), and `build_autoresearch_results_summary.py` all report `prepared_not_run` / blocked clinical claims. Targeted Next ESLint and production build previously passed for the contract surface.
- Deployment: Not a clinical unlock. Research mode still requires `READER_AUTH_PROXY_SECRET` plus signed proxy headers before collecting analyzable events.
- Follow-up: Register expertise for the 14 primary readers, run a signed research smoke session, then unlock claims only after the Round2 gate passes with completed paired rows.

## 2026-08-10, Add overlap focus zoom and safe prompt modes

- Scope: `InteractiveSegPanel` overlap visualization, focus zoom, pointer cancellation, and scribble/lasso prompt handling.
- Reason: The existing ROI zoom used a lesion/lumen union box, while freehand and lasso prompts could fall back to ordinary SAM clicks when nnInteractive was unavailable.
- Key changes: Added an overlap/contact focus window and highlighted focus frame, made scribble and lasso require the boundary-assistance backend, stopped fallback conversion into SAM clicks, and added pointer cancellation plus event isolation.
- Validation: Targeted ESLint completed with zero errors, Next production build completed, standalone assets were synchronized, and browser inspection showed the overlap zoom control plus disabled prompt tools when the optional boundary service is unavailable.
- Deployment: Next production service was rebuilt and restarted on port 3000. Existing SAM2 and SAM3.1 services were not changed.
- Follow-up: Start the official nnInteractive model service when its checkpoint is available, then verify positive and negative scribble/lasso refinement on lesion and lumen targets.

## 2026-08-10, Start cases with clean geometry canvas

- Scope: Next case selection, `InteractiveSegPanel`, persisted mask/lumen overrides, and production standalone assets.
- Reason: Historical lesion, wall, and lumen contours could still appear when a non-reader case was opened, even though history was intended to be opt-in.
- Key changes: Stop fetching persisted current overrides on case selection, stop auto-loading LabelMe contours, clear lesion, wall, lumen, and tracked-frame state on first open, and keep history display behind explicit preview and restore actions.
- Validation: Targeted ESLint completed with warnings only, production build completed, standalone static assets were synchronized, and browser verification showed an empty initial canvas with `病灶待框选` and `胃腔待检测`.
- Deployment: Next production service was rebuilt and restarted on port 3000. The optional nnInteractive endpoint remained unavailable and was not started.
- Follow-up: Manually verify the explicit history preview and restore flow, then confirm a new SAM lesion or lumen save remains visible after the current case is edited.

## 2026-08-10, Add boot-persistent Next and SAM3.1 services

- Scope: `scripts/systemd/`, the user-service installer, and workstation startup documentation.
- Reason: SAM2 was already supervised by the user systemd instance, but the canonical Next port and SAM3.1 backend were not covered by one reproducible boot service setup.
- Key changes: Added a restartable SAM3.1 unit on port 8768, a production Next unit on port 3000, a workstation target, a readiness probe that waits for the SAM3.1 base and LoRA models, checkpoint/build preflight checks, and user lingering support without storing credentials in tracked files.
- Validation: `systemd-analyze verify`, installer startup, controlled Next restart, Next `:3000` and Agent contract HTTP 200, SAM2 readiness, SAM3.1 readiness with LoRA loaded, enabled boot units, user lingering, and listening ports were verified. SAM3.1 readiness is now part of the service start gate.
- Deployment: Installed locally into the user systemd instance. It did not stop the existing SAM2 service or replace the temporary public Next preview on port 3300.
- Follow-up: Run the full LAN acceptance script when the optional auth service on port 8766 is available; no reboot was performed in this validation.

## 2026-08-10, Use confirmed lumen masks for staging evidence

- Scope: Python Agent lumen geometry, wall SDF evidence, direction-normalized GC-US signs, and related visual provenance.
- Reason: The workbench already preserved a confirmed lumen polygon, but the runtime pipeline reduced it to a rectangular box proxy before wall and direction analysis.
- Key changes: Rasterize confirmed lumen polygons into full-resolution masks, pass them through pipeline state, prefer them for wall signed-distance features and lesion contact geometry, and label bbox-only results as proxy geometry.
- Validation: Added unit coverage for polygon rasterization, exact lumen area propagation, confirmed-mask wall evidence, and mask-based direction/contact features. A deidentified demo trace changed the lumen geometry area from 70,210 bbox pixels to 13,011 confirmed-mask pixels and changed the wall proxy from high to uncertain, confirming that the rectangle proxy can overstate contact.
- Deployment: Not deployed; the change is local and keeps the frozen T classifier input contract unchanged.
- Follow-up: Run a frozen paired evaluation of bbox versus confirmed lumen mask on the 20+20 acceptance panel before considering any classifier retraining or probability recalibration.

## 2026-08-09, Complete mask editing and persistence

- Scope: `apps/gastric_scan_next` mask editing, video tracking persistence, mask history, and remote Next deployment.
- Reason: Ensure doctors can edit lesion, wall, lumen, and tracked video-frame masks, then preserve the complete result after tracking.
- Key changes: Added mask history storage and restore UI, automatic saves for doctor edits and tracking completion, validation for wall, lumen, and frame boxes, and a serialized save queue so a final tracking save is not dropped behind an earlier edit save.
- Validation: TypeScript check, ESLint, isolated production build, local history API smoke test, and remote service health check.
- Deployment: The remote `gastric-next` service was updated atomically. The previous release was retained for rollback, and the public bundle excluded internal data, logs, and public video assets.
- Follow-up: Continue manual browser verification of freehand, lasso, positive and negative point editing, and history restore with a logged-in reader account.

## 2026-08-09, Complete video-frame snapshots

- Scope: `VideoMaskFrameOverride`, video tracking frame mapping, mask persistence normalization, and frame validation.
- Reason: Make the saved `video_frames` data explicitly complete for review and restoration.
- Key changes: Preserve tracker-provided frame indices, retain lesion segmentation with `roi_bbox`, retain lumen segmentation with `lumen_bbox`, and derive missing boxes from saved polygons before validation and response.
- Validation: TypeScript check, ESLint, production build, and mask history API smoke test.

## 2026-08-09, On-demand history viewing

- Scope: Interactive mask history panel and saved-lumen messaging.
- Reason: Keep historical versions closed and unloaded at case start while allowing doctors to inspect and restore them on demand.
- Key changes: Removed the automatic saved-lumen notification, hid history counts while the panel is closed, added viewable snapshot summaries for lesion and lumen masks and boxes, kept the panel open after restore, and refreshed the list after restore.
- Follow-up: Confirm the view and restore flow with a logged-in browser session.

## 2026-08-09, Non-destructive history previews and audit traces

- Scope: History canvas preview, combined lesion and lumen snapshots, doctor-operation audit events, and model-trace audit events.
- Reason: Let each doctor start with a clean editable canvas, inspect one selected historical version without replacing current work, and retain enough structured trace data for later analysis.
- Key changes: Added dashed canvas previews that activate only after selecting a version, kept restore as the only operation that replaces current masks, saved the paired lumen snapshot with mask history, and recorded history actions, saves, model prompts, model outcomes, video propagation summaries, timing, and errors through the reader audit endpoint.
- Validation: TypeScript check, targeted ESLint, production build, local production-server smoke test for the history and audit routes.
- Deployment: Not deployed in this change; no remote service or clinical data was modified.
- Follow-up: Verify preview and restore behavior with a logged-in browser session, then deploy through the existing staged rollback workflow if approved.

## 2026-08-09, Prompt semantics and report output gates

- Scope: Reader-study initial state, lesion and lumen prompt interaction, core-sign assessment display, and template report export controls.
- Reason: Keep prior masks out of the initial editable canvas, make doctor intent explicit, and prevent incomplete or ambiguously exported reports.
- Key changes: History is on-demand with non-destructive preview and explicit restore, lesion and lumen roles are explained, positive and negative prompts have distinct controls, local SAM is used when nnInteractive is unavailable, contour-exterior clicks become negative prompts, and negative lasso prompts retain a lesion or lumen anchor. Core-sign rows now expose assessment methods and evidence limits. The report shows growth pattern in the ultrasound findings, uses larger typography, requires a reference image and export method, and normalizes unsupported CSS colors during PDF rendering.
- Validation: Production TypeScript build, targeted ESLint with zero errors, report lifecycle smoke test, browser verification of clean startup, history preview and restore, prompt fallback state, report rendering, and PDF Blob creation.
- Deployment: The active frontend service and reverse tunnel were updated to the new staged bundle. Previous bundles remain available for rollback. Runtime report and mask data remain outside the source tree.
- Follow-up: Complete a logged-in clinician review of positive and negative clicks on a representative case, then confirm final sign-off with calibrated measurements and a selected reference image.

## 2026-08-09, Doctor workflow automation and report autosave

- Scope: Reader-study workflow orchestration, lesion candidate detection, workflow trace integration, report draft autosave, and screen-recording validation.
- Reason: Reproduce the fixed doctor sequence from video input through lesion and lumen refinement, full-video tracking, evidence synthesis, and report export without losing intermediate work.
- Key changes: Added full-frame lesion candidate detection with explicit positive-center refinement, lesion-aware lumen refinement, a doctor workflow action that chains detection, correction, saving, tracking, and Agent analysis, normalized frontend trace events into Agent steps, and debounced server-side report draft autosave with visible status and revision updates.
- Validation: TypeScript production build, targeted ESLint with zero errors, Python compilation, report workflow smoke test, isolated full-size browser run, successful 60 fps 1920x1080 screen capture, PDF export, autosave revision persistence, and trajectory inspection.
- Deployment: Validated in isolated standalone preview bundles only. The active 3300 service was not replaced; isolated preview processes were stopped after validation. Rollback is the unchanged active bundle.
- Follow-up: Review the proposed lesion candidate and unresolved N/M or ascites fields with a clinician before any clinical sign-off. The generated recording is a demonstration artifact, not a clinical report.

## 2026-08-10, Prompt robustness evaluation and adaptation

- Scope: SAM3.1 static prompt robustness, box perturbation evaluation, inference-time prompt selection, and LoRA adaptation.
- Reason: Oracle-box Dice did not guarantee stability when the doctor box was oversized, shifted, or slightly undersized.
- Key changes: Added raw-versus-robust prompt evaluation, inference candidates for expanded, shifted, shrunk, center-point, and mixed prompts, quality and consensus metadata, and train-time geometric prompt augmentation from the current full-component checkpoint.
- Validation: Prompt smoke evaluation completed without errors on the internal validation protocol; dataset prompt augmentation smoke passed; service and evaluator syntax checks passed. The smoke result is not a promotion gate.
- Deployment: No active service replacement. Prompt-robust adaptation training is running in an isolated output directory and must pass the full patient-level prompt matrix plus external and prospective frozen gates before deployment.
- Follow-up: Complete the adaptation training, evaluate all prompt variants at image and patient level, and retain the current checkpoint if oracle Dice or external stability regresses.
