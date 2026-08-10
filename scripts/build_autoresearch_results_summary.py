#!/usr/bin/env python3
"""Aggregate mainline, Agent, and human-AI reader evidence into autoresearch results.

Writes a machine-readable RESULTS_SUMMARY.json plus RESULTS_SUMMARY.md under
pipeline/autoresearch/results/<stamp>/ and refreshes the `latest` symlink-like
copy (plain directory refresh).

This does not invent clinical uplift. Round2 AI-assisted endpoints stay blocked
until research paired rows exist.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "pipeline/autoresearch/results"

FREEZE = ROOT / "data/registry/reader_round2_study_freeze_20260810.json"
EXPORT_STATUS = ROOT / "docs/clinical_validation/reader_round2_exports/export_status.json"
GATE = ROOT / "docs/clinical_validation/reader_round2_exports/round2_gate_status.json"
UPLIFT = ROOT / "docs/clinical_validation/reader_round2_exports/expertise_uplift_summary.json"
AUDIT = ROOT / "docs/clinical_validation/reader_round2_exports/audit_events_summary.json"
ROUND1_DOC = ROOT / "docs/clinical_validation/reader_round2_exports/round1_doctor_level.csv"
MANIFEST_SUM = ROOT / "data/registry/reader_round2_ai_assisted_manifest.summary.json"
ORDER_SUM = ROOT / "data/registry/reader_round2_case_order_20260810.summary.json"
AGENT_FROZEN = ROOT / "pipeline/experiments/reports/gastric_us_agent_frozen_validation_clean_20260809/frozen_validation_summary.json"
AGENT_SUMMARY_MD = ROOT / "pipeline/experiments/reports/gastric_us_agent_frozen_validation_clean_20260809/SUMMARY.md"
V150_TWO_PHASE = ROOT / "artifacts/eval/reader_study_v150_two_phase_v2/SUMMARY.md"
ASSET_FREEZE = ROOT / "docs/mainline/asset_freeze_decision_20260809.md"
EVIDENCE_CHAIN = ROOT / "docs/paper_drafts/human_ai_reader_evidence_chain_20260810.md"


def load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fnum(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def agent_panel_from_json(data: dict | None) -> dict[str, Any]:
    if not data:
        return {
            "status": "missing",
            "source": str(AGENT_FROZEN.relative_to(ROOT)),
            "cohorts": [],
        }
    cohorts: list[dict[str, Any]] = []
    raw = data.get("cohorts")
    if isinstance(raw, dict):
        for name, block in raw.items():
            if not isinstance(block, dict):
                continue
            views = block.get("views") or {}
            base = (views.get("base_t_only") or {}) if isinstance(views, dict) else {}
            full = (views.get("full_agent") or {}) if isinstance(views, dict) else {}
            base_acc = base.get("patient_acc")
            full_acc = full.get("patient_acc")
            delta = None
            if isinstance(base_acc, (int, float)) and isinstance(full_acc, (int, float)):
                delta = round(float(full_acc) - float(base_acc), 4)
            cohorts.append(
                {
                    "cohort": name,
                    "n": block.get("n"),
                    "base_t_only_acc": base_acc,
                    "full_agent_acc": full_acc,
                    "delta": delta,
                    "mean_rag_weight": block.get("mean_rag_weight"),
                }
            )
    if not cohorts:
        # fallback from SUMMARY.md SSOT (accepted 2026-08-09)
        cohorts = [
            {"cohort": "internal", "n": 20, "base_t_only_acc": 0.700, "full_agent_acc": 0.700, "delta": 0.0, "mean_rag_weight": 0.235},
            {"cohort": "external", "n": 20, "base_t_only_acc": 0.450, "full_agent_acc": 0.500, "delta": 0.050, "mean_rag_weight": 0.200},
        ]
    return {
        "status": "foundation_only",
        "role": "Agent offline acceptance panel; not Round2 doctor benefit",
        "source": str(AGENT_FROZEN.relative_to(ROOT)) if AGENT_FROZEN.exists() else str(AGENT_SUMMARY_MD.relative_to(ROOT)),
        "protocol": data.get("protocol"),
        "cohorts": cohorts,
    }


def model_foundation() -> dict[str, Any]:
    return {
        "agent_final_t": {
            "backend_id": "tstage_acc_boost2_screened_20260603",
            "prospective_patient_acc": 0.720,
            "external_patient_acc_all_485": 0.629,
            "external_patient_acc_heldout_399": 0.556,
            "note": "Agent final T; legacy external must report held-out 399",
        },
        "phase0_audit_t": {
            "backend_id": "tstage_acc_boost2_phase0_20260610",
            "external_patient_acc_doctor_roi_approx": 0.464,
            "external_patient_acc_predicted_roi_approx": 0.471,
            "note": "Strict generalization audit line; report in separate table",
        },
        "segmentation_primary": "lesion_segmentation_unet_fulldata_convnext_base",
        "sam31_role": "interactive_candidate_not_agent_primary",
        "asset_freeze_doc": str(ASSET_FREEZE.relative_to(ROOT)),
    }


def offline_v150_ai() -> dict[str, Any]:
    return {
        "status": "offline_model_eval_on_reader_bundle",
        "role": "sensitivity / feasibility only; not formal Round2 doctor AI-assisted",
        "source": str(V150_TWO_PHASE.relative_to(ROOT)) if V150_TWO_PHASE.exists() else None,
        "phase1_bm_acc": 0.66,
        "phase2_t_acc": 0.57,
        "t2_recall": 0.1333,
    }


def round1_block(rows: list[dict[str, str]]) -> dict[str, Any]:
    primary = [r for r in rows if str(r.get("include_in_primary_complete150")).lower() == "true"]
    t_acc = [fnum(r.get("t_accuracy")) for r in primary]
    bm_acc = [fnum(r.get("bm_accuracy")) for r in primary]
    t_acc = [x for x in t_acc if x is not None]
    bm_acc = [x for x in bm_acc if x is not None]
    times = [fnum(r.get("mean_reading_time_sec")) for r in primary]
    times = [x for x in times if x is not None]
    doctor_table = [
        {
            "reader_id": r["reader_id"],
            "primary": str(r.get("include_in_primary_complete150")).lower() == "true",
            "n_pairable": int(float(r["n_pairable"])) if r.get("n_pairable") else None,
            "bm_accuracy": fnum(r.get("bm_accuracy")),
            "t_accuracy": fnum(r.get("t_accuracy")),
            "mean_reading_time_sec": fnum(r.get("mean_reading_time_sec")),
        }
        for r in rows
    ]
    return {
        "status": "available",
        "condition": "no_ai",
        "primary_complete150_readers": len(primary),
        "mean_t_accuracy_primary": None if not t_acc else round(mean(t_acc) or 0.0, 4),
        "mean_bm_accuracy_primary": None if not bm_acc else round(mean(bm_acc) or 0.0, 4),
        "mean_reading_time_sec_primary": None if not times else round(mean(times) or 0.0, 2),
        "source_csv": str(ROUND1_DOC.relative_to(ROOT)),
        "doctors": doctor_table,
    }


def evidence_rows(summary: dict[str, Any]) -> list[dict[str, str]]:
    rows = [
        {"bucket": "model_foundation", "claim_level": "reportable", "path": "docs/mainline/asset_freeze_decision_20260809.md", "metric": "acc_boost2 / Phase0 split", "value": "frozen"},
        {"bucket": "agent_acceptance", "claim_level": "foundation_only", "path": "pipeline/experiments/reports/gastric_us_agent_frozen_validation_clean_20260809/SUMMARY.md", "metric": "full Agent ACC internal/external 20+20", "value": "0.70 / 0.50"},
        {"bucket": "offline_v150_ai", "claim_level": "sensitivity_only", "path": "artifacts/eval/reader_study_v150_two_phase_v2/SUMMARY.md", "metric": "AI BM/T on reader bundle", "value": "0.66 / 0.57"},
        {"bucket": "round1_no_ai", "claim_level": "reportable", "path": "docs/clinical_validation/reader_round2_exports/round1_doctor_level.csv", "metric": "primary mean T/BM ACC", "value": f"{summary['human_ai']['round1_no_ai'].get('mean_t_accuracy_primary')}/{summary['human_ai']['round1_no_ai'].get('mean_bm_accuracy_primary')}"},
        {"bucket": "round2_freeze", "claim_level": "scaffold", "path": "data/registry/reader_round2_study_freeze_20260810.json", "metric": "execution_status", "value": summary["human_ai"]["round2"]["execution_status"]},
        {"bucket": "round2_gate", "claim_level": "blocked_clinical", "path": "docs/clinical_validation/reader_round2_exports/round2_gate_status.json", "metric": "clinical_claims_allowed", "value": str(summary["human_ai"]["round2"]["clinical_claims_allowed"]).lower()},
        {"bucket": "round2_uplift", "claim_level": "blocked_clinical", "path": "docs/clinical_validation/reader_round2_exports/expertise_uplift_summary.json", "metric": "status", "value": summary["human_ai"]["round2"]["uplift_status"]},
        {"bucket": "round2_runtime_contract", "claim_level": "scaffold", "path": "data/registry/reader_round2_study_freeze_20260810.json", "metric": "server auth / order / structured evidence", "value": "implemented, research not started"},
        {"bucket": "paper_evidence_chain", "claim_level": "design", "path": "docs/paper_drafts/human_ai_reader_evidence_chain_20260810.md", "metric": "narrative_priority", "value": "A clinical > D model foundation"},
        {"bucket": "sap", "claim_level": "preregistered", "path": "docs/READER_ROUND2_STATISTICAL_ANALYSIS_PLAN_20260810.md", "metric": "primary_endpoint", "value": "paired delta T ACC"},
    ]
    return rows


def render_md(summary: dict[str, Any]) -> str:
    ha = summary["human_ai"]
    r1 = ha["round1_no_ai"]
    r2 = ha["round2"]
    mf = summary["model_foundation"]
    lines = [
        "# Autoresearch Results Summary",
        "",
        f"> Generated: `{summary['created_at']}`  ",
        f"> Bundle: `{summary['bundle_id']}`  ",
        f"> Clinical AI-assisted claims: **{'ALLOWED' if summary['clinical_claims_allowed'] else 'BLOCKED'}**",
        "",
        "## 0. Verdict",
        "",
        summary["verdict"],
        "",
        "## 1. Model foundation (reportable as system base)",
        "",
        "| Line | Backend | Key metric | Role |",
        "|------|---------|------------|------|",
        f"| Agent final T | `{mf['agent_final_t']['backend_id']}` | prosp ACC {mf['agent_final_t']['prospective_patient_acc']}; held-out 399 ACC {mf['agent_final_t']['external_patient_acc_heldout_399']} | production final |",
        f"| Phase 0 audit T | `{mf['phase0_audit_t']['backend_id']}` | pred-ROI ~{mf['phase0_audit_t']['external_patient_acc_predicted_roi_approx']} | separate audit table |",
        f"| Segmentation | `{mf['segmentation_primary']}` | Agent primary | not SAM3.1 |",
        "",
        "## 2. Agent offline acceptance (foundation only)",
        "",
        "| Cohort | n | base T-only | full Agent | delta |",
        "|--------|---:|------------:|-----------:|------:|",
    ]
    for c in summary["agent_acceptance"]["cohorts"]:
        lines.append(
            f"| {c.get('cohort')} | {c.get('n')} | {c.get('base_t_only_acc')} | {c.get('full_agent_acc')} | {c.get('delta')} |"
        )
    lines += [
        "",
        "Do not treat this panel as doctor AI-assisted uplift.",
        "",
        "## 3. Offline AI on reader v150 bundle (sensitivity only)",
        "",
        f"- BM ACC: `{summary['offline_v150_ai'].get('phase1_bm_acc')}`",
        f"- T ACC: `{summary['offline_v150_ai'].get('phase2_t_acc')}` (T2 recall `{summary['offline_v150_ai'].get('t2_recall')}`)",
        "- Not interchangeable with formal Round2 doctor sessions.",
        "",
        "## 4. Round1 no-AI doctor baseline (reportable)",
        "",
        f"- Primary complete-150 readers: **{r1.get('primary_complete150_readers')}**",
        f"- Mean T ACC: **{r1.get('mean_t_accuracy_primary')}**",
        f"- Mean BM ACC: **{r1.get('mean_bm_accuracy_primary')}**",
        f"- Mean reading time (sec): **{r1.get('mean_reading_time_sec_primary')}**",
        f"- Source: `{r1.get('source_csv')}`",
        "",
        "## 5. Round2 AI-assisted paired study (current gate)",
        "",
        f"- Freeze ID: `{r2.get('freeze_id')}`",
        f"- Execution status: `{r2.get('execution_status')}`",
        f"- Planned / pairable rows: `{r2.get('planned_rows')}` / `{r2.get('baseline_pairable_rows')}`",
        f"- Round2 completed rows: **{r2.get('round2_completed_rows')}**",
        f"- Research audit events: **{r2.get('research_event_count')}**",
        f"- Expertise primary registered: **{r2.get('expertise_primary_registered')}** / 14",
        f"- Scaffold ready: `{r2.get('scaffold_ready')}`",
        f"- Clinical claims allowed: `{r2.get('clinical_claims_allowed')}`",
        f"- Uplift status: `{r2.get('uplift_status')}`",
        "",
        "Blocked endpoints: primary T uplift, junior+AI vs senior no-AI, report-quality gain, inter-reader variance reduction, AI correction/induction rates.",
        "",
        "## 6. Runtime contract",
        "",
        f"- Server-bound research identity: `{r2.get('runtime_contract', {}).get('research_identity', {}).get('server_bound', False)}`",
        f"- Server-applied case order: `{r2.get('runtime_contract', {}).get('case_order_server_applied', False)}`",
        f"- Structured evidence: `{', '.join(r2.get('runtime_contract', {}).get('structured_evidence_fields', []))}`",
        "- These are preparation gates, not completed clinical observations.",
        "",
        "## 7. Evidence index",
        "",
        "| Bucket | Claim level | Path | Metric | Value |",
        "|--------|-------------|------|--------|-------|",
    ]
    for row in summary["evidence_index"]:
        lines.append(
            f"| {row['bucket']} | {row['claim_level']} | `{row['path']}` | {row['metric']} | {row['value']} |"
        )
    lines += [
        "",
        "## 8. Next unlock steps",
        "",
        "1. Register expertise tiers for 14 primary readers before Round2 start.",
        "2. Run authenticated `environment=research` Round2 sessions per freeze order.",
        "3. Re-run:",
        "",
        "```bash",
        "python3 scripts/analyze_reader_audit_events.py --environment research",
        "python3 scripts/export_reader_round2_paired_tables.py \\",
        "  --round2-case-csv docs/clinical_validation/reader_round2_exports/reader_case_level_from_audit.csv",
        "python3 scripts/validate_reader_round2_gate.py",
        "python3 scripts/analyze_reader_round2_expertise_uplift.py",
        "python3 scripts/build_autoresearch_results_summary.py",
        "```",
        "",
        "4. Only after gate `clinical_claims_allowed=true`, promote human-AI uplift into paper Results-C.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stamp", default=None, help="Output stamp directory name (default UTC date)")
    args = ap.parse_args()

    stamp = args.stamp or datetime.now(timezone.utc).strftime("%Y%m%d")
    bundle_id = f"autoresearch_results_{stamp}_human_ai_closure"

    freeze = load_json(FREEZE) or {}
    export_status = load_json(EXPORT_STATUS) or {}
    gate = load_json(GATE) or {}
    uplift = load_json(UPLIFT) or {}
    audit = load_json(AUDIT) or {}
    manifest_sum = load_json(MANIFEST_SUM) or {}
    round1_rows = read_csv(ROUND1_DOC)

    clinical_allowed = bool(gate.get("clinical_claims_allowed"))
    summary: dict[str, Any] = {
        "schema_version": "autoresearch_results_summary_v1",
        "bundle_id": bundle_id,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "clinical_claims_allowed": clinical_allowed,
        "verdict": (
            "Human-AI collaborative mainline scaffolding is aggregated. "
            "Round1 no-AI baseline and model/Agent foundations are reportable. "
            "Formal Round2 AI-assisted doctor uplift remains blocked "
            f"(completed_rows={export_status.get('round2_completed_rows', 0)}, "
            f"expertise_registered={uplift.get('expertise_primary_registered', 0)})."
        ),
        "model_foundation": model_foundation(),
        "agent_acceptance": agent_panel_from_json(load_json(AGENT_FROZEN)),
        "offline_v150_ai": offline_v150_ai(),
        "human_ai": {
            "round1_no_ai": round1_block(round1_rows),
            "round2": {
                "freeze_id": freeze.get("freeze_id") or "reader_round2_freeze_20260810",
                "execution_status": freeze.get("execution_status") or export_status.get("execution_status"),
                "planned_rows": freeze.get("manifest", {}).get("planned_rows") or export_status.get("manifest_rows"),
                "baseline_pairable_rows": freeze.get("manifest", {}).get("baseline_pairable_rows")
                or manifest_sum.get("baseline_pairable_rows"),
                "round2_completed_rows": export_status.get("round2_completed_rows", 0),
                "research_event_count": audit.get("event_count", 0),
                "excluded_event_count": audit.get("excluded_event_count"),
                "expertise_primary_registered": uplift.get("expertise_primary_registered", 0),
                "scaffold_ready": gate.get("scaffold_ready"),
                "clinical_claims_allowed": clinical_allowed,
                "uplift_status": uplift.get("status"),
                "claims_allowed": uplift.get("claims_allowed"),
                "endpoints": uplift.get("endpoints"),
                "case_order_seed": freeze.get("case_order", {}).get("seed"),
                "runtime_contract": freeze.get("runtime_contract", {}),
                "exports_dir": "docs/clinical_validation/reader_round2_exports",
                "evidence_chain": str(EVIDENCE_CHAIN.relative_to(ROOT)),
            },
        },
        "pointers": {
            "freeze_contract": "docs/READER_ROUND2_FREEZE_CONTRACT_20260810.md",
            "endpoints": "docs/READER_ROUND2_ENDPOINTS_AND_REPORT_QUALITY_20260810.md",
            "runbook": "docs/READER_ROUND2_EXECUTION_RUNBOOK_20260810.md",
            "sap": "docs/READER_ROUND2_STATISTICAL_ANALYSIS_PLAN_20260810.md",
            "mainline": "docs/mainline/tstaging_current_mainline.md",
            "next_steps_autoresearch": "docs/agent_memory/plan/NEXT_STEPS_AUTORESEARCH.md",
        },
    }
    summary["evidence_index"] = evidence_rows(summary)

    out_dir = OUT_ROOT / stamp
    latest = OUT_ROOT / "latest"
    out_dir.mkdir(parents=True, exist_ok=True)
    if latest.exists():
        shutil.rmtree(latest)
    latest.mkdir(parents=True, exist_ok=True)

    for dest in (out_dir, latest):
        (dest / "RESULTS_SUMMARY.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (dest / "RESULTS_SUMMARY.md").write_text(render_md(summary), encoding="utf-8")
        with (dest / "evidence_index.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["bucket", "claim_level", "path", "metric", "value"])
            w.writeheader()
            w.writerows(summary["evidence_index"])

        # Snapshot key doctor table for offline reading
        if round1_rows:
            with (dest / "round1_doctor_level_snapshot.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(round1_rows[0].keys()))
                w.writeheader()
                w.writerows(round1_rows)

        # Copy gate/uplift/export status for self-contained bundle
        for src, name in (
            (GATE, "round2_gate_status.json"),
            (UPLIFT, "expertise_uplift_summary.json"),
            (EXPORT_STATUS, "export_status.json"),
            (AUDIT, "audit_events_summary.json"),
            (FREEZE, "reader_round2_study_freeze_20260810.json"),
        ):
            if src.exists():
                shutil.copy2(src, dest / name)

    # Append to trial ledger (append-only; skip exact duplicate of last row path)
    ledger = OUT_ROOT / "trial_ledger.csv"
    ledger_row = {
        "bundle_id": bundle_id,
        "created_at": summary["created_at"],
        "kind": "human_ai_closure_aggregate",
        "clinical_claims_allowed": str(clinical_allowed).lower(),
        "round1_mean_t_acc": summary["human_ai"]["round1_no_ai"].get("mean_t_accuracy_primary"),
        "round2_completed_rows": summary["human_ai"]["round2"].get("round2_completed_rows"),
        "uplift_status": summary["human_ai"]["round2"].get("uplift_status"),
        "path": str((OUT_ROOT / stamp).relative_to(ROOT)),
    }
    skip_append = False
    if ledger.exists():
        existing = list(csv.DictReader(ledger.open(encoding="utf-8")))
        if existing and existing[-1].get("path") == ledger_row["path"] and existing[-1].get("kind") == ledger_row["kind"]:
            # refresh same stamp: rewrite last row metadata by rewriting file
            existing[-1] = ledger_row
            with ledger.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(ledger_row.keys()))
                w.writeheader()
                w.writerows(existing)
            skip_append = True
    if not skip_append:
        write_header = not ledger.exists()
        with ledger.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(ledger_row.keys()))
            if write_header:
                w.writeheader()
            w.writerow(ledger_row)

    print(json.dumps({"out_dir": str(out_dir), "latest": str(latest), "clinical_claims_allowed": clinical_allowed}, indent=2))


if __name__ == "__main__":
    main()
