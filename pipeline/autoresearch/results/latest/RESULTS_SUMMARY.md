# Autoresearch Results Summary

> Generated: `2026-08-10T06:54:28Z`  
> Bundle: `autoresearch_results_20260810_human_ai_closure`  
> Clinical AI-assisted claims: **BLOCKED**

## 0. Verdict

Human-AI collaborative mainline scaffolding is aggregated. Round1 no-AI baseline and model/Agent foundations are reportable. Formal Round2 AI-assisted doctor uplift remains blocked (completed_rows=0, expertise_registered=0).

## 1. Model foundation (reportable as system base)

| Line | Backend | Key metric | Role |
|------|---------|------------|------|
| Agent final T | `tstage_acc_boost2_screened_20260603` | prosp ACC 0.72; held-out 399 ACC 0.556 | production final |
| Phase 0 audit T | `tstage_acc_boost2_phase0_20260610` | pred-ROI ~0.471 | separate audit table |
| Segmentation | `lesion_segmentation_unet_fulldata_convnext_base` | Agent primary | not SAM3.1 |

## 2. Agent offline acceptance (foundation only)

| Cohort | n | base T-only | full Agent | delta |
|--------|---:|------------:|-----------:|------:|
| internal | 20 | 0.7 | 0.7 | 0.0 |
| external | 20 | 0.45 | 0.5 | 0.05 |

Do not treat this panel as doctor AI-assisted uplift.

## 3. Offline AI on reader v150 bundle (sensitivity only)

- BM ACC: `0.66`
- T ACC: `0.57` (T2 recall `0.1333`)
- Not interchangeable with formal Round2 doctor sessions.

## 4. Round1 no-AI doctor baseline (reportable)

- Primary complete-150 readers: **14**
- Mean T ACC: **0.4436**
- Mean BM ACC: **0.5014**
- Mean reading time (sec): **61.17**
- Source: `docs/clinical_validation/reader_round2_exports/round1_doctor_level.csv`

## 5. Round2 AI-assisted paired study (current gate)

- Freeze ID: `reader_round2_freeze_20260810`
- Execution status: `prepared_not_run`
- Planned / pairable rows: `2400` / `2312`
- Round2 completed rows: **0**
- Research audit events: **0**
- Expertise primary registered: **0** / 14
- Scaffold ready: `True`
- Clinical claims allowed: `False`
- Uplift status: `blocked_until_round2_data`

Blocked endpoints: primary T uplift, junior+AI vs senior no-AI, report-quality gain, inter-reader variance reduction, AI correction/induction rates.

## 6. Runtime contract

- Server-bound research identity: `True`
- Server-applied case order: `True`
- Structured evidence: `lesion_extent, wall_invasion_depth, serosal_breakthrough, growth_pattern`
- These are preparation gates, not completed clinical observations.

## 7. Evidence index

| Bucket | Claim level | Path | Metric | Value |
|--------|-------------|------|--------|-------|
| model_foundation | reportable | `docs/mainline/asset_freeze_decision_20260809.md` | acc_boost2 / Phase0 split | frozen |
| agent_acceptance | foundation_only | `pipeline/experiments/reports/gastric_us_agent_frozen_validation_clean_20260809/SUMMARY.md` | full Agent ACC internal/external 20+20 | 0.70 / 0.50 |
| offline_v150_ai | sensitivity_only | `artifacts/eval/reader_study_v150_two_phase_v2/SUMMARY.md` | AI BM/T on reader bundle | 0.66 / 0.57 |
| round1_no_ai | reportable | `docs/clinical_validation/reader_round2_exports/round1_doctor_level.csv` | primary mean T/BM ACC | 0.4436/0.5014 |
| round2_freeze | scaffold | `data/registry/reader_round2_study_freeze_20260810.json` | execution_status | prepared_not_run |
| round2_gate | blocked_clinical | `docs/clinical_validation/reader_round2_exports/round2_gate_status.json` | clinical_claims_allowed | false |
| round2_uplift | blocked_clinical | `docs/clinical_validation/reader_round2_exports/expertise_uplift_summary.json` | status | blocked_until_round2_data |
| round2_runtime_contract | scaffold | `data/registry/reader_round2_study_freeze_20260810.json` | server auth / order / structured evidence | implemented, research not started |
| paper_evidence_chain | design | `docs/paper_drafts/human_ai_reader_evidence_chain_20260810.md` | narrative_priority | A clinical > D model foundation |
| sap | preregistered | `docs/READER_ROUND2_STATISTICAL_ANALYSIS_PLAN_20260810.md` | primary_endpoint | paired delta T ACC |

## 8. Next unlock steps

1. Register expertise tiers for 14 primary readers before Round2 start.
2. Run authenticated `environment=research` Round2 sessions per freeze order.
3. Re-run:

```bash
python3 scripts/analyze_reader_audit_events.py --environment research
python3 scripts/export_reader_round2_paired_tables.py \
  --round2-case-csv docs/clinical_validation/reader_round2_exports/reader_case_level_from_audit.csv
python3 scripts/validate_reader_round2_gate.py
python3 scripts/analyze_reader_round2_expertise_uplift.py
python3 scripts/build_autoresearch_results_summary.py
```

4. Only after gate `clinical_claims_allowed=true`, promote human-AI uplift into paper Results-C.
