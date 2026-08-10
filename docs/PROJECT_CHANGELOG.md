# Project Changelog

This file records material project changes, their validation, and deployment state. Do not add patient identifiers, credentials, tokens, private URLs, or sensitive clinical data.

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
