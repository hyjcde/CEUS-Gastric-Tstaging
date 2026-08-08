#!/usr/bin/env python3
"""Append scoreboard + baseline rows to experiments/registry.csv (idempotent)."""

from __future__ import annotations

import csv
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCOREBOARD = PROJECT_ROOT / "pipeline/experiments/tables/tstaging_4class_mainline_scoreboard.csv"
REGISTRY = PROJECT_ROOT / "experiments/registry.csv"
BASELINE_REGISTRY = PROJECT_ROOT / "pipeline/experiments/mainlines/tstaging_4class/baseline_registry.yaml"

STRUCTURE_RUN = (
    "pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/"
    "tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301"
)

FIELDNAMES = [
    "experiment_id",
    "task",
    "display_name",
    "status",
    "config_path",
    "run_dir",
    "metrics_summary_path",
    "data_version",
    "storage_root",
    "artifact_policy",
    "is_git_trackable",
    "notes",
]


def storage_and_policy(experiment_id: str, task: str, run_dir: str) -> tuple[str, str, str]:
    if experiment_id.endswith("_baseline_v1"):
        return f"experiments/baselines/{experiment_id.replace('_baseline_v1', '')}_baseline_v1/", "index_only", "yes"
    if run_dir.startswith("pipeline/experiments/tree"):
        return "pipeline/experiments/tree", "generated_large", "no"
    if run_dir.startswith("experiments/"):
        return run_dir.split("/")[0] + "/" + run_dir.split("/")[1] if "/" in run_dir else "experiments", "generated", "no"
    if task == "tstage" and not run_dir:
        return "pipeline/experiments/reports", "report_only", "partial"
    return "experiments", "needs_review", "review"


def rel_run_dir(path: str) -> str:
    if not path:
        return ""
    p = Path(path)
    if p.is_absolute():
        try:
            return str(p.relative_to(PROJECT_ROOT))
        except ValueError:
            return path.replace(str(PROJECT_ROOT) + "/", "")
    return path


def enrich(row: dict[str, str]) -> dict[str, str]:
    eid = row.get("experiment_id", "")
    task = row.get("task", "")
    run_dir = row.get("run_dir", "")
    sr, ap, gt = storage_and_policy(eid, task, run_dir)
    row.setdefault("storage_root", sr)
    row.setdefault("artifact_policy", ap)
    row.setdefault("is_git_trackable", gt)
    return row


def load_baselines() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    metrics_path = "pipeline/experiments/tables/tstaging_4class_mainline_scoreboard.csv"

    if yaml and BASELINE_REGISTRY.exists():
        data = yaml.safe_load(BASELINE_REGISTRY.read_text(encoding="utf-8")) or {}
        run = data.get("run") or {}
        metrics = data.get("metrics") or {}
        eid = data.get("baseline_id", "structure_mask4ch_clinical22")
        run_dir = rel_run_dir(run.get("run_dir", STRUCTURE_RUN))
        row = {
            "experiment_id": eid,
            "task": "tstage",
            "display_name": data.get("display_name", ""),
            "status": data.get("status", "frozen"),
            "config_path": (data.get("config") or {}).get("path", ""),
            "run_dir": run_dir,
            "metrics_summary_path": metrics_path,
            "data_version": "tstage_4class_region_contrastive_full",
            "notes": (
                f"external_auc={metrics.get('test_external_auc', '')}; "
                f"prospective_auc={metrics.get('test_prospective_auc', '')}"
            ),
        }
        rows.append(enrich(row))

    baseline_dirs = {
        "detection_baseline_v1": ("detection", "needs_review", ""),
        "segmentation_baseline_v1": ("segmentation", "needs_review", ""),
        "tstage_baseline_v1": ("tstage", "frozen", STRUCTURE_RUN),
    }
    for dirname, (task, status, run_dir) in baseline_dirs.items():
        rows.append(
            enrich(
                {
                    "experiment_id": dirname,
                    "task": task,
                    "display_name": dirname,
                    "status": status,
                    "config_path": f"experiments/baselines/{dirname}/",
                    "run_dir": run_dir,
                    "metrics_summary_path": metrics_path if task == "tstage" else "",
                    "data_version": "",
                    "notes": "see experiments/baselines README + run_pointer.txt",
                }
            )
        )
    return rows


def main() -> None:
    existing_ids: set[str] = set()
    rows: list[dict[str, str]] = []
    fieldnames = FIELDNAMES

    if REGISTRY.exists():
        with REGISTRY.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                fieldnames = list(reader.fieldnames)
                for col in FIELDNAMES:
                    if col not in fieldnames:
                        fieldnames.append(col)
            for row in reader:
                eid = row.get("experiment_id", "")
                existing_ids.add(eid)
                full = {k: row.get(k, "") for k in fieldnames}
                rows.append(enrich(full))

    def upsert(new_row: dict[str, str]) -> None:
        new_row = enrich(new_row)
        eid = new_row["experiment_id"]
        if eid in existing_ids:
            for i, row in enumerate(rows):
                if row.get("experiment_id") == eid:
                    for k, v in new_row.items():
                        if v and (not row.get(k) or row.get(k) == "needs_review"):
                            row[k] = v
                    rows[i] = enrich(row)
                    return
            return
        rows.append(new_row)
        existing_ids.add(eid)

    for row in load_baselines():
        upsert(row)

    metrics_path = "pipeline/experiments/tables/tstaging_4class_mainline_scoreboard.csv"
    if SCOREBOARD.exists():
        with SCOREBOARD.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                row = {k.strip(): v for k, v in row.items() if k}
                eid = row.get("stage_id", "")
                if not eid:
                    continue
                run_dir = STRUCTURE_RUN if eid == "structure_mask4ch_clinical22" else ""
                upsert(
                    {
                        "experiment_id": eid,
                        "task": "tstage",
                        "display_name": row.get("display_name", eid),
                        "status": row.get("decision", "completed").lower(),
                        "config_path": row.get("config_path", ""),
                        "run_dir": run_dir,
                        "metrics_summary_path": metrics_path,
                        "data_version": "tstage_4class_region_contrastive_full",
                        "notes": (
                            f"external_auc={row.get('external_auc', '')}; "
                            f"prospective_auc={row.get('prospective_auc', '')}"
                        ),
                    }
                )

    with REGISTRY.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows({k: r.get(k, "") for k in fieldnames} for r in rows)
    print(f"Wrote {len(rows)} rows to {REGISTRY}")


if __name__ == "__main__":
    main()
