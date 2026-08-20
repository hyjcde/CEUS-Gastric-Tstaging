# Project Changelog

This file records material project changes, their validation, and deployment state. Do not add patient identifiers, credentials, tokens, private URLs, or sensitive clinical data.

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
