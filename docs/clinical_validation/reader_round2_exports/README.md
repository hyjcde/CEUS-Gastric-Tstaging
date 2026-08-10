# Round2 paired export workspace

> Freeze ID: `reader_round2_freeze_20260810`  
> Status: `prepared_not_run` for Round2 doctor events; Round1 baseline tables are available.

## Purpose

Hold auditable exports for the same-doctor, same-case AI-assisted reader study.

## Rebuild

```bash
# Round1 baseline + paired skeleton + report-quality template
python3 scripts/export_reader_round2_paired_tables.py

# Filter research audit events (QA exclusions applied)
python3 scripts/analyze_reader_audit_events.py --environment research

# After Round2 research events exist:
python3 scripts/analyze_reader_audit_events.py --environment research
python3 scripts/export_reader_round2_paired_tables.py \
  --round2-case-csv docs/clinical_validation/reader_round2_exports/reader_case_level_from_audit.csv

# Rebuild the autoresearch aggregate after every export
python3 scripts/build_autoresearch_results_summary.py
```

## Current outputs

| File | Meaning |
|------|---------|
| `round1_case_level.csv` | No-AI baseline from frozen Round2 manifest |
| `round1_doctor_level.csv` | Per-doctor Round1 accuracy / time |
| `paired_round1_round2_skeleton.csv` | Paired keys with Round2 fields empty / not_started |
| `report_quality_scores_template.csv` | Blinded 1-5 score sheet template |
| `export_status.json` | Machine-readable completion gate |
| `audit_events_summary.json` | Research-filtered audit event counts |

The analyzer scans `GASTRIC_RUNTIME_DATA_DIR`, the production
`apps/gastric_scan_next/runtime-data/`, the development `/tmp/gastric-scan-next/`,
and the legacy app data path. Research events are accepted only when the
server-bound `authenticated_reader_id` is present at the top level.

## Gate

Do not write AI-assisted clinical uplift claims until:

1. `export_status.json` shows `round2_completed_rows > 0`
2. events use `environment=research`
3. QA exclusions are applied
4. expertise registry is no longer all `pending`

Aggregated with model/Agent foundations in:

```text
pipeline/autoresearch/results/latest/RESULTS_SUMMARY.md
```

Rebuild:

```bash
python3 scripts/build_autoresearch_results_summary.py
```
