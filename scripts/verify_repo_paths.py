#!/usr/bin/env python3
"""Verify critical repo paths, symlinks, and manifest samples."""

from __future__ import annotations

import csv
import json
import random
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "metadata"


def check_exists(path: Path, label: str, checks: list[dict]) -> None:
    ok = path.exists()
    checks.append(
        {
            "name": label,
            "path": str(path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path),
            "ok": ok,
            "is_symlink": path.is_symlink(),
            "resolved": str(path.resolve()) if ok else None,
        }
    )


def check_symlink(link: Path, label: str, checks: list[dict]) -> None:
    ok = link.is_symlink() and link.resolve().exists()
    checks.append(
        {
            "name": label,
            "path": str(link),
            "ok": ok,
            "is_symlink": link.is_symlink(),
            "resolved": str(link.resolve()) if link.exists() or link.is_symlink() else None,
        }
    )


def sample_manifest_images(manifest: Path, n: int = 20) -> list[dict]:
    if not manifest.exists():
        return [{"error": f"missing manifest {manifest}"}]
    rows: list[dict] = []
    with manifest.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        all_rows = list(reader)
    if not all_rows:
        return [{"error": "empty manifest"}]
    sample = random.sample(all_rows, min(n, len(all_rows)))
    missing = []
    for row in sample:
        raw = row.get("image_path") or row.get("output_image") or ""
        if not raw:
            continue
        p = Path(raw)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        if not p.exists():
            missing.append(str(raw))
    return [{"sampled": len(sample), "missing_count": len(missing), "missing_paths": missing[:10]}]


def run_root_check() -> dict:
    import subprocess

    script = PROJECT_ROOT / "scripts" / "check_repo_root.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    try:
        summary = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        summary = {"pass": False, "error": proc.stdout or proc.stderr}
    summary["exit_code"] = proc.returncode
    return summary


def main() -> int:
    import sys

    checks: list[dict] = []
    critical = [
        (PROJECT_ROOT / "REPO_LAYOUT.md", "repo_layout"),
        (PROJECT_ROOT / "dataset" / "DATASET_GUIDE.md", "dataset_guide"),
        (PROJECT_ROOT / "docs" / "ARCHITECTURE.md", "architecture"),
        (PROJECT_ROOT / "docs" / "README.md", "docs_readme"),
        (PROJECT_ROOT / "data" / "raw" / "legacy_gastric_staging", "raw_legacy_gastric"),
        (PROJECT_ROOT / "archive" / "docs_legacy" / "docs_copy", "docs_legacy_copy"),
        (PROJECT_ROOT / "artifacts" / "model_weights" / "yolo", "model_weights_yolo"),
        (PROJECT_ROOT / "models" / "README.md", "models_readme"),
        (PROJECT_ROOT / "pipeline" / "agent" / "product" / "analyze_case.py", "agent_analyze_case"),
        (PROJECT_ROOT / "apps" / "gastric_scan_next" / "package.json", "gastric_scan_next"),
        (PROJECT_ROOT / "apps" / "direction_annotator" / "package.json", "direction_annotator"),
        (PROJECT_ROOT / "experiments" / "registry.csv", "experiments_registry"),
    ]
    for path, label in critical:
        check_exists(path, label, checks)

    batch_canonical = PROJECT_ROOT / "data" / "annotation" / "batches" / "direction_annotation_batch.json"
    check_exists(batch_canonical, "direction_batch_canonical", checks)
    compat_dir = PROJECT_ROOT / "_compat"
    check_exists(compat_dir / "README.md", "compat_readme", checks)

    internal_manifest = PROJECT_ROOT / "dataset" / "internal" / "manifest.csv"
    external_manifest = PROJECT_ROOT / "dataset" / "external" / "manifest.csv"
    manifest_results = {
        "internal": sample_manifest_images(internal_manifest),
        "external": sample_manifest_images(external_manifest),
    }

    root_check = run_root_check()

    failed = [c for c in checks if not c.get("ok")]
    manifest_missing = sum(
        r.get("missing_count", 0) for r in manifest_results.values() if isinstance(r, dict)
    )
    overall_pass = (
        len(failed) == 0
        and manifest_missing == 0
        and root_check.get("pass") is True
    )

    report = {
        "date": date.today().isoformat(),
        "project_root": str(PROJECT_ROOT),
        "pass": overall_pass,
        "root_check": root_check,
        "checks": checks,
        "manifest_samples": manifest_results,
        "failed_count": len(failed),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"verify_{date.today().strftime('%Y%m%d')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"pass": overall_pass, "output": str(out_path), "failed": len(failed)}, ensure_ascii=False))
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
