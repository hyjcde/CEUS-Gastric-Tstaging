#!/usr/bin/env python3
"""Run Grad-CAM on test_external / test_prospective and zip outputs."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PIPELINE_ROOT.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
from build_gradcam_screening_html import build_html as build_screening_html

RUN_SCRIPT = PIPELINE_ROOT / "scripts" / "run_4class_gradcam.py"

DEFAULT_EXP = (
    "pipeline/experiments/tree/gastric_tstage_4class/classification/"
    "dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301"
)

SPLIT_SPECS = {
    "test_external": {
        "input_csv_suffix": "eval/test_external/test_predictions.csv",
        "output_dir_name": "gradcam_test_external_full",
        "slim_zip_name": "gradcam_test_external_slim.zip",
    },
    "test_prospective": {
        "input_csv_suffix": "eval/test_prospective/test_predictions.csv",
        "output_dir_name": "gradcam_test_prospective_full",
        "slim_zip_name": "gradcam_test_prospective_slim.zip",
    },
}


def resolve_panel_path(panel_path: object, project_root: Path) -> Path | None:
    if panel_path is None or pd.isna(panel_path) or not str(panel_path).strip():
        return None
    path = Path(str(panel_path))
    if path.is_file():
        return path
    candidate = project_root / path
    if candidate.is_file():
        return candidate
    return None


def filter_results_df(df: pd.DataFrame, split: str, external_holdout_only: bool) -> pd.DataFrame:
    if split != "test_external" or not external_holdout_only:
        return df
    mask = ~df["image_path"].astype(str).str.contains("prospective", case=False, na=False)
    return df.loc[mask].copy()


def collect_pack_files(
    output_dir: Path,
    results_df: pd.DataFrame,
    pack_mode: str,
    project_root: Path,
    tmp_dir: Path | None = None,
) -> list[tuple[Path, Path]]:
    """Return (absolute_path, archive_relative_path) pairs to include in zip."""
    files: list[tuple[Path, Path]] = []
    arc_root = Path(output_dir.name)

    if pack_mode == "full":
        for path in sorted(output_dir.rglob("*")):
            if path.is_file():
                files.append((path, arc_root / path.relative_to(output_dir)))
        return files

    for _, row in results_df.iterrows():
        panel = resolve_panel_path(row.get("panel_path"), project_root)
        if panel is None:
            continue
        try:
            rel = panel.relative_to(output_dir)
        except ValueError:
            rel = Path("panels") / panel.name
        files.append((panel, arc_root / rel))

    csv_path = output_dir / "gradcam_results.csv"
    if csv_path.is_file():
        slim_csv = (tmp_dir or output_dir) / "gradcam_results.csv"
        results_df.to_csv(slim_csv, index=False)
        files.append((slim_csv, arc_root / "gradcam_results.csv"))
    html_path = output_dir / "gradcam_screening.html"
    if html_path.is_file():
        files.append((html_path, arc_root / "gradcam_screening.html"))
    return files


def zip_pack_files(files: list[tuple[Path, Path]], zip_path: Path) -> int:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for src, arc in files:
            zf.write(src, arcname=str(arc))
    return len(files)


def summarize_split(
    output_dir: Path,
    split: str,
    input_csv: Path,
    results_df: pd.DataFrame | None = None,
) -> dict:
    results_csv = output_dir / "gradcam_results.csv"
    panel_count = sum(1 for _ in output_dir.rglob("*_panel.png"))
    summary = {
        "split": split,
        "input_csv": str(input_csv),
        "output_dir": str(output_dir),
        "panel_png_count": panel_count,
        "gradcam_results_rows": 0,
        "packed_panel_count": 0,
        "correct": 0,
        "misclassified": 0,
    }
    df = results_df
    if df is None and results_csv.is_file():
        df = pd.read_csv(results_csv)
    if df is not None:
        summary["gradcam_results_rows"] = int(len(df))
        summary["packed_panel_count"] = int(df["panel_path"].notna().sum()) if "panel_path" in df.columns else 0
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
        "Contents per split (slim zip):",
        "  - gradcam_screening.html  (offline doctor screening UI)",
        "  - panels/<T*/correct|misclassified...>/*_panel.png",
        "  - gradcam_results.csv",
        "",
        "Doctor workflow: unzip, double-click gradcam_screening.html, mark bad images, export rejected CSV.",
        "",
        "Note: external slim pack excludes int/prospective rows duplicated in test_prospective.",
        "",
    ]
    for summary in summaries:
        lines.extend(
            [
                f"Split: {summary['split']}",
                f"  generated panels: {summary['panel_png_count']}",
                f"  packed panels: {summary.get('packed_panel_count', summary['panel_png_count'])}",
                f"  gradcam_results rows: {summary['gradcam_results_rows']}",
                f"  correct / misclassified: {summary['correct']} / {summary['misclassified']}",
                f"  pack_mode: {summary.get('pack_mode', 'slim')}",
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
        "--pack-mode",
        choices=("slim", "full"),
        default="slim",
        help="slim: panel PNG + gradcam_results.csv only; full: entire output dir",
    )
    parser.add_argument(
        "--include-prospective-in-external",
        action="store_true",
        help="Keep int/prospective rows in external pack (default: excluded as duplicate)",
    )
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
    external_holdout_only = not args.include_prospective_in_external

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

        results_df = None
        results_csv = output_dir / "gradcam_results.csv"
        if results_csv.is_file():
            results_df = pd.read_csv(results_csv)
            results_df = filter_results_df(results_df, split, external_holdout_only)

        summary = summarize_split(output_dir, split, input_csv, results_df)
        summary["pack_mode"] = args.pack_mode
        summary["external_holdout_only"] = bool(external_holdout_only and split == "test_external")

        screening_html = output_dir / "gradcam_screening.html"
        if results_csv.is_file():
            html_summary = build_screening_html(
                results_csv,
                screening_html,
                split=split,
                root_dir=output_dir,
            )
            summary["screening_html"] = html_summary["html"]
            summary["screening_cases"] = html_summary["cases"]
            print(f"Screening HTML: {screening_html} ({html_summary['cases']} cases)")

        summaries.append(summary)

        if not args.no_zip:
            if args.pack_mode == "slim":
                zip_name = spec["slim_zip_name"]
            else:
                zip_name = f"{output_dir.name}.zip"
            zip_path = pack_root / zip_name
            with tempfile.TemporaryDirectory(prefix="gradcam_pack_") as tmp:
                pack_files = collect_pack_files(
                    output_dir,
                    results_df if results_df is not None else pd.DataFrame(),
                    args.pack_mode,
                    PROJECT_ROOT,
                    tmp_dir=Path(tmp),
                )
                n_files = zip_pack_files(pack_files, zip_path)
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
        "pack_mode": args.pack_mode,
        "external_holdout_only": external_holdout_only,
        "splits": summaries,
    }
    manifest_path = pack_root / "gradcam_test_sets_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_readme(pack_root / "README_gradcam_test_sets.txt", summaries, zip_paths)
    print(f"\nManifest: {manifest_path}")


if __name__ == "__main__":
    main()
