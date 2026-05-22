#!/usr/bin/env python3
"""Run Grad-CAM on test_external / test_prospective and zip outputs."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PIPELINE_ROOT.parent
RUN_SCRIPT = PIPELINE_ROOT / "scripts" / "run_4class_gradcam.py"

DEFAULT_EXP = (
    "pipeline/experiments/tree/gastric_tstage_4class/classification/"
    "dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301"
)

SPLIT_SPECS = {
    "test_external": {
        "input_csv_suffix": "eval/test_external/test_predictions.csv",
        "output_dir_name": "gradcam_test_external_full",
    },
    "test_prospective": {
        "input_csv_suffix": "eval/test_prospective/test_predictions.csv",
        "output_dir_name": "gradcam_test_prospective_full",
    },
}


def zip_output_dir(output_dir: Path, zip_path: Path) -> int:
    if zip_path.exists():
        zip_path.unlink()
    file_count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(output_dir.rglob("*")):
            if not path.is_file():
                continue
            arc = Path(output_dir.name) / path.relative_to(output_dir)
            zf.write(path, arcname=str(arc))
            file_count += 1
    return file_count


def summarize_split(output_dir: Path, split: str, input_csv: Path) -> dict:
    results_csv = output_dir / "gradcam_results.csv"
    panel_count = sum(1 for _ in output_dir.rglob("*_panel.png"))
    summary = {
        "split": split,
        "input_csv": str(input_csv),
        "output_dir": str(output_dir),
        "panel_png_count": panel_count,
        "gradcam_results_rows": 0,
        "correct": 0,
        "misclassified": 0,
    }
    if results_csv.is_file():
        df = pd.read_csv(results_csv)
        summary["gradcam_results_rows"] = int(len(df))
        if "correct" in df.columns:
            summary["correct"] = int(df["correct"].sum())
            summary["misclassified"] = int((~df["correct"].astype(bool)).sum())
        if "true_name" in df.columns:
            summary["by_true_class"] = df["true_name"].value_counts().to_dict()
    return summary


def run_gradcam_split(
    exp_dir: Path,
    split: str,
    output_dir: Path,
    extra_args: list[str],
) -> None:
    spec = SPLIT_SPECS[split]
    input_csv = exp_dir / spec["input_csv_suffix"]
    if not input_csv.is_file():
        raise FileNotFoundError(f"Missing input CSV: {input_csv}")

    cmd = [
        sys.executable,
        str(RUN_SCRIPT),
        "--exp-dir",
        str(exp_dir),
        "--input-csv",
        str(input_csv),
        "--output-dir",
        str(output_dir),
        *extra_args,
    ]
    print(f"\n=== Grad-CAM: {split} ===")
    print(" ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT))


def write_readme(path: Path, summaries: list[dict], zip_paths: list[Path]) -> None:
    lines = [
        "Grad-CAM full test-set batch",
        "===========================",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Contents per split:",
        "  - panels/<T*/correct|misclassified...>/*_panel.png",
        "  - gradcam_results.csv",
        "  - ppt_assets/ (when produced)",
        "",
    ]
    for summary in summaries:
        lines.extend(
            [
                f"Split: {summary['split']}",
                f"  panels: {summary['panel_png_count']}",
                f"  gradcam_results rows: {summary['gradcam_results_rows']}",
                f"  correct / misclassified: {summary['correct']} / {summary['misclassified']}",
                "",
            ]
        )
    lines.append("ZIP files:")
    for zp in zip_paths:
        size_mb = zp.stat().st_size / (1024 * 1024) if zp.is_file() else 0
        lines.append(f"  - {zp.name} ({size_mb:.1f} MB)")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch Grad-CAM on test splits + zip")
    parser.add_argument("--exp-dir", type=str, default=DEFAULT_EXP)
    parser.add_argument(
        "--splits",
        nargs="+",
        choices=tuple(SPLIT_SPECS),
        default=["test_external", "test_prospective"],
    )
    parser.add_argument("--skip-run", action="store_true", help="Only package existing outputs")
    parser.add_argument("--no-zip", action="store_true")
    parser.add_argument(
        "--pack-root",
        type=str,
        default=None,
        help="Directory for zip files (default: exp_dir/gradcam_test_sets_pack)",
    )
    parser.add_argument("--layout", choices=("panel", "simple"), default="panel")
    parser.add_argument(
        "--cam-focus",
        choices=("roi_expand_px", "lesion_wall", "lesion", "seg", "union"),
        default="roi_expand_px",
    )
    parser.add_argument("--max-samples", type=int, default=None)
    args, unknown = parser.parse_known_args()

    exp_dir = Path(args.exp_dir)
    if not exp_dir.is_absolute():
        exp_dir = PROJECT_ROOT / exp_dir
    if not exp_dir.is_dir():
        raise SystemExit(f"Experiment dir not found: {exp_dir}")

    gradcam_extra = [
        "--layout",
        args.layout,
        "--cam-focus",
        args.cam_focus,
    ]
    if args.max_samples is not None:
        gradcam_extra.extend(["--max-samples", str(args.max_samples)])
    gradcam_extra.extend(unknown)

    pack_root = Path(args.pack_root) if args.pack_root else exp_dir / "gradcam_test_sets_pack"
    pack_root.mkdir(parents=True, exist_ok=True)

    summaries: list[dict] = []
    zip_paths: list[Path] = []

    for split in args.splits:
        spec = SPLIT_SPECS[split]
        output_dir = exp_dir / spec["output_dir_name"]
        input_csv = exp_dir / spec["input_csv_suffix"]

        if not args.skip_run:
            if output_dir.exists() and args.max_samples is None:
                shutil.rmtree(output_dir)
            run_gradcam_split(exp_dir, split, output_dir, gradcam_extra)

        if not output_dir.is_dir():
            print(f"Warning: missing output dir for {split}: {output_dir}")
            continue

        summary = summarize_split(output_dir, split, input_csv)
        summaries.append(summary)

        if not args.no_zip:
            zip_path = pack_root / f"{output_dir.name}.zip"
            n_files = zip_output_dir(output_dir, zip_path)
            summary["zip_path"] = str(zip_path)
            summary["zip_file_count"] = n_files
            summary["zip_size_mb"] = round(zip_path.stat().st_size / (1024 * 1024), 2)
            zip_paths.append(zip_path)
            print(f"Packed {split}: {zip_path} ({summary['zip_size_mb']} MB, {n_files} files)")

    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "exp_dir": str(exp_dir),
        "layout": args.layout,
        "cam_focus": args.cam_focus,
        "splits": summaries,
    }
    manifest_path = pack_root / "gradcam_test_sets_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_readme(pack_root / "README_gradcam_test_sets.txt", summaries, zip_paths)
    print(f"\nManifest: {manifest_path}")


if __name__ == "__main__":
    main()
