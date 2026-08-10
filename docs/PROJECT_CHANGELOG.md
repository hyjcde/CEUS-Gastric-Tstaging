# Project Changelog

This file records material project changes, their validation, and deployment state. Do not add patient identifiers, credentials, tokens, private URLs, or sensitive clinical data.

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
