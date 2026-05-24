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
from build_gradcam_screening_html import build_split_screening_html, build_unified_html as build_screening_html

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
        "include_in_unified": True,
    },
    "test_prospective": {
        # 2025 前瞻全部为测试集：磁盘 crop_ui 2430 张（含 145 张无 pT，占位标签）
        "input_csv": "pipeline/data/tstaging_4class_prospective_full/test_prospective_full_clinical.csv",
        "output_dir_name": "gradcam_test_prospective_full",
        "slim_zip_name": "gradcam_test_prospective_slim.zip",
        "include_in_unified": True,
    },
}


def resolve_split_input_csv(exp_dir: Path, spec: dict) -> Path:
    if spec.get("input_csv"):
        path = Path(spec["input_csv"])
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path
    return exp_dir / spec["input_csv_suffix"]


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
    seen_arc: set[str] = set()
    arc_root = Path(output_dir.name)

    def add_file(src: Path, arc: Path) -> None:
        key = str(arc).replace("\\", "/")
        if key in seen_arc:
            return
        seen_arc.add(key)
        files.append((src, arc))

    if pack_mode == "full":
        for path in sorted(output_dir.rglob("*")):
            if path.is_file():
                add_file(path, arc_root / path.relative_to(output_dir))
        return files

    for _, row in results_df.iterrows():
        panel = resolve_panel_path(row.get("panel_path"), project_root)
        if panel is None:
            continue
        try:
            rel = panel.relative_to(output_dir)
        except ValueError:
            rel = Path("panels") / panel.name
        add_file(panel, arc_root / rel)

    csv_path = output_dir / "gradcam_results.csv"
    if csv_path.is_file():
        slim_csv = (tmp_dir or output_dir) / "gradcam_results.csv"
        results_df.to_csv(slim_csv, index=False)
        add_file(slim_csv, arc_root / "gradcam_results.csv")
    html_path = output_dir / "gradcam_screening.html"
    if html_path.is_file():
        add_file(html_path, arc_root / "gradcam_screening.html")
    return files

def update_files_in_zip(zip_path: Path, updates: list[tuple[Path, str]]) -> None:
    """Replace or add small files in an existing zip without repacking panels."""
    if not zip_path.is_file():
        return
    with zipfile.ZipFile(zip_path, "a", compression=zipfile.ZIP_DEFLATED) as zf:
        for src, arc in updates:
            if src.is_file():
                zf.write(src, arcname=arc)


def attach_existing_zip_stats(summaries: list[dict], pack_root: Path) -> list[Path]:
    zip_paths: list[Path] = []
    for summary in summaries:
        split = summary.get("split", "")
        spec = SPLIT_SPECS.get(split, {})
        zip_name = spec.get("slim_zip_name") or f"{spec.get('output_dir_name', split)}.zip"
        zip_path = pack_root / zip_name
        if zip_path.is_file():
            summary["zip_path"] = str(zip_path)
            summary["zip_size_mb"] = round(zip_path.stat().st_size / (1024 * 1024), 2)
            zip_paths.append(zip_path)
    return zip_paths


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
    *,
    resume: bool = False,
) -> None:
    spec = SPLIT_SPECS[split]
    input_csv = resolve_split_input_csv(exp_dir, spec)
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
    if resume:
        cmd.append("--resume")
    print(f"\n=== Grad-CAM: {split} ===")
    print(" ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT))


def write_readme(path: Path, summaries: list[dict], zip_paths: list[Path], bundle_path: Path | None = None) -> None:
    lines = [
        "Grad-CAM 测试集筛图包",
        "====================",
        f"生成时间: {datetime.now(timezone.utc).isoformat()}",
        "",
        "【医生用法 — 推荐】",
        "  1. 解压对应 zip（外部 / 前瞻 分开筛，标注互不影响）",
        "  2. 进入文件夹，双击 gradcam_screening.html",
        "  3. 只需标记质量差的图：按 X 或点「标记剔除」",
        "  4. 图质量好：直接翻下一张，不用点保留",
        "  5. 筛完后点「导出剔除 CSV」，发回算法组",
        "",
        "【每个 slim zip 内含】",
        "  - gradcam_screening.html  （离线筛图网页，双击即用）",
        "  - gradcam_results.csv     （预测结果与 panel 路径）",
        "  - panels/.../*_panel.png  （Grad-CAM 可视化大图）",
        "",
        "【合并包 gradcam_test_clinical_bundle.zip】",
        "  含外部 + 前瞻两个文件夹 + 统一 gradcam_screening.html + 本说明",
        "  若两个数据集一起筛，解压后打开根目录 gradcam_screening.html",
        "",
        "【样本量说明】",
        "  - test_external: 2430 张（含内部前瞻 253 张重复行，纯外部 holdout 2177 张）",
        "  - test_prospective: 2430 张（2025 前瞻全部为测试集，crop_ui 全量）",
        "  - 旧 test_prospective.csv 253 张为历史 holdout，不用于 2025 筛图",
        "  - 统一 HTML = 外部 holdout 2177 + 前瞻 2430",
        "",
    ]
    for summary in summaries:
        lines.extend(
            [
                f"Split: {summary['split']}",
                f"  gradcam_results 行数: {summary['gradcam_results_rows']}",
                f"  panel PNG 文件数: {summary['panel_png_count']}",
                f"  打包 panel 数: {summary.get('packed_panel_count', summary['panel_png_count'])}",
                f"  正确 / 分错: {summary['correct']} / {summary['misclassified']}",
                f"  pack_mode: {summary.get('pack_mode', 'slim')}",
                "",
            ]
        )
    lines.append("ZIP 文件:")
    for zp in zip_paths:
        size_mb = zp.stat().st_size / (1024 * 1024) if zp.is_file() else 0
        lines.append(f"  - {zp.name} ({size_mb:.1f} MB)")
    if bundle_path and bundle_path.is_file():
        size_mb = bundle_path.stat().st_size / (1024 * 1024)
        lines.append(f"  - {bundle_path.name} ({size_mb:.1f} MB) [合并包]")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_bundle_readme(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "Grad-CAM 测试集筛图 — 合并包",
                "========================",
                "",
                "文件夹说明:",
                "  gradcam_test_external_full/   外部测试 2430 张 → 打开内层 gradcam_screening.html",
                "  gradcam_test_prospective_full/ 2025 前瞻测试 2430 张 → 打开内层 gradcam_screening.html",
                "  gradcam_screening.html         统一视图（外部 holdout + 前瞻全量，与分文件夹标注分开保存）",
                "",
                "操作建议:",
                "  • 临床筛图优先用分文件夹 HTML（外部、前瞻分开，localStorage 不冲突）",
                "  • 默认保留；仅对质量差的图按 X 剔除",
                "  • 筛完务必导出 gradcam_rejected.csv",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def build_clinical_bundle(
    pack_root: Path,
    exp_dir: Path,
    split_output_dirs: list[Path],
    unified_html: Path | None,
) -> Path | None:
    bundle_path = pack_root / "gradcam_test_clinical_bundle.zip"
    if bundle_path.exists():
        bundle_path.unlink()
    with tempfile.TemporaryDirectory(prefix="gradcam_bundle_") as tmp:
        tmp_dir = Path(tmp)
        readme = tmp_dir / "README_筛图说明.txt"
        write_bundle_readme(readme)
        with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            zf.write(readme, arcname="README_筛图说明.txt")
            if unified_html and unified_html.is_file():
                zf.write(unified_html, arcname="gradcam_screening.html")
            for output_dir in split_output_dirs:
                if not output_dir.is_dir():
                    continue
                arc_root = output_dir.name
                for path in sorted(output_dir.rglob("*")):
                    if path.is_file():
                        zf.write(path, arcname=str(Path(arc_root) / path.relative_to(output_dir)))
    return bundle_path if bundle_path.is_file() else None


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
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume Grad-CAM runs from existing gradcam_results.csv (do not wipe output dirs)",
    )
    parser.add_argument(
        "--refresh-pack",
        action="store_true",
        help="Regenerate HTML and update HTML/README inside existing zips (no panel repack)",
    )
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
    split_output_dirs: list[Path] = []

    for split in args.splits:
        spec = SPLIT_SPECS[split]
        output_dir = exp_dir / spec["output_dir_name"]
        input_csv = resolve_split_input_csv(exp_dir, spec)

        if not args.skip_run:
            if output_dir.exists() and args.max_samples is None and not args.resume:
                shutil.rmtree(output_dir)
            run_gradcam_split(exp_dir, split, output_dir, gradcam_extra, resume=args.resume)

        if not output_dir.is_dir():
            print(f"Warning: missing output dir for {split}: {output_dir}")
            continue

        split_output_dirs.append(output_dir)

        results_df = None
        results_csv = output_dir / "gradcam_results.csv"
        if results_csv.is_file():
            results_df = pd.read_csv(results_csv)
            results_df = filter_results_df(results_df, split, external_holdout_only)

        summary = summarize_split(output_dir, split, input_csv, results_df)
        summary["pack_mode"] = args.pack_mode
        summary["external_holdout_only"] = bool(external_holdout_only and split == "test_external")
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

    screening_sources: list[dict] = []
    for split in args.splits:
        spec = SPLIT_SPECS[split]
        output_dir = exp_dir / spec["output_dir_name"]
        results_csv = output_dir / "gradcam_results.csv"
        if results_csv.is_file():
            screening_sources.append(
                {
                    "results_csv": results_csv,
                    "split": split,
                    "root_dir": output_dir,
                    "path_prefix": spec["output_dir_name"],
                    "external_holdout_only": bool(external_holdout_only and split == "test_external"),
                    "include_in_unified": bool(spec.get("include_in_unified", False)),
                }
            )
    screening_summary = None
    screening_html: Path | None = None
    split_html_summaries: list[dict] = []
    if screening_sources:
        unified_sources = [src for src in screening_sources if src.get("include_in_unified")]
        if unified_sources:
            screening_html = exp_dir / "gradcam_screening.html"
            # Unified view: 2430 unique test images (external holdout + prospective).
            unified_for_html = []
            for src in unified_sources:
                u = dict(src)
                if u.get("split") == "test_external":
                    u["external_holdout_only"] = True
                unified_for_html.append(u)
            screening_summary = build_screening_html(unified_for_html, screening_html)
            shutil.copy2(screening_html, pack_root / "gradcam_screening.html")
            print(
                f"Unified screening HTML: {screening_html} "
                f"({screening_summary['cases']} cases, splits={screening_summary['split_counts']})"
            )
        for src in screening_sources:
            split = str(src["split"])
            split_html = Path(src["root_dir"]) / "gradcam_screening.html"
            split_src = {**src, "external_holdout_only": False}
            split_summary = build_split_screening_html(split_src, split_html)
            split_html_summaries.append({"split": split, **split_summary})
            print(
                f"Split screening HTML: {split_html} "
                f"({split_summary['cases']} cases, storage={split_summary.get('split_counts', {})})"
            )

    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "exp_dir": str(exp_dir),
        "layout": args.layout,
        "cam_focus": args.cam_focus,
        "pack_mode": args.pack_mode,
        "external_holdout_only": external_holdout_only,
        "splits": summaries,
    }
    if screening_summary:
        manifest["screening_html"] = screening_summary["html"]
        manifest["screening_cases"] = screening_summary["cases"]
        manifest["screening_split_counts"] = screening_summary["split_counts"]
    if split_html_summaries:
        manifest["split_screening_html"] = split_html_summaries
    manifest_path = pack_root / "gradcam_test_sets_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    bundle_path = None
    if args.refresh_pack:
        readme_tmp = pack_root / "README_筛图说明.txt"
        write_bundle_readme(readme_tmp)
        for split in args.splits:
            spec = SPLIT_SPECS[split]
            output_dir = exp_dir / spec["output_dir_name"]
            split_html = output_dir / "gradcam_screening.html"
            zip_path = pack_root / spec["slim_zip_name"]
            if split_html.is_file() and zip_path.is_file():
                update_files_in_zip(
                    zip_path,
                    [(split_html, f"{output_dir.name}/gradcam_screening.html")],
                )
                print(f"Updated HTML in {zip_path.name}")
        bundle_path = pack_root / "gradcam_test_clinical_bundle.zip"
        if bundle_path.is_file() and screening_html and screening_html.is_file():
            bundle_updates = [(screening_html, "gradcam_screening.html")]
            if readme_tmp.is_file():
                bundle_updates.append((readme_tmp, "README_筛图说明.txt"))
            for split in args.splits:
                spec = SPLIT_SPECS[split]
                output_dir = exp_dir / spec["output_dir_name"]
                split_html = output_dir / "gradcam_screening.html"
                if split_html.is_file():
                    bundle_updates.append((split_html, f"{output_dir.name}/gradcam_screening.html"))
            update_files_in_zip(bundle_path, bundle_updates)
            print(f"Updated HTML in {bundle_path.name}")
        zip_paths = attach_existing_zip_stats(summaries, pack_root)
        if bundle_path.is_file():
            manifest["clinical_bundle_zip"] = str(bundle_path)
            manifest["clinical_bundle_size_mb"] = round(bundle_path.stat().st_size / (1024 * 1024), 2)
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    elif not args.no_zip and split_output_dirs:
        bundle_path = build_clinical_bundle(
            pack_root,
            exp_dir,
            split_output_dirs,
            screening_html if screening_summary else None,
        )
        if bundle_path:
            size_mb = round(bundle_path.stat().st_size / (1024 * 1024), 2)
            print(f"Clinical bundle: {bundle_path} ({size_mb} MB)")
            manifest["clinical_bundle_zip"] = str(bundle_path)
            manifest["clinical_bundle_size_mb"] = size_mb
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.no_zip and not args.refresh_pack:
        zip_paths = attach_existing_zip_stats(summaries, pack_root)
        bundle_path = pack_root / "gradcam_test_clinical_bundle.zip"
        if bundle_path.is_file():
            manifest["clinical_bundle_zip"] = str(bundle_path)
            manifest["clinical_bundle_size_mb"] = round(bundle_path.stat().st_size / (1024 * 1024), 2)
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    write_readme(pack_root / "README_gradcam_test_sets.txt", summaries, zip_paths, bundle_path if bundle_path and Path(bundle_path).is_file() else None)
    print(f"\nManifest: {manifest_path}")


if __name__ == "__main__":
    main()
