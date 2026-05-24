#!/usr/bin/env python3
"""Run Grad-CAM on test splits and assemble a folder bundle for clinical screening."""

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
from build_gradcam_screening_html import (
    SCREENING_DATA_DIR,
    build_unified_html as build_screening_html,
)

RUN_SCRIPT = PIPELINE_ROOT / "scripts" / "run_4class_gradcam.py"
DEFAULT_BUNDLE_NAME = "gradcam_clinical_screening"

DEFAULT_EXP = (
    "pipeline/experiments/tree/gastric_tstage_4class/classification/"
    "dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301"
)

SPLIT_SPECS = {
    "test_external": {
        "input_csv_suffix": "eval/test_external/test_predictions.csv",
        "output_dir_name": "gradcam_test_external_full",
        "include_in_unified": True,
    },
    "test_prospective": {
        "input_csv": "pipeline/data/tstaging_4class_prospective_full/test_prospective_full_clinical.csv",
        "output_dir_name": "gradcam_test_prospective_full",
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


def copy_screening_bundle(src_root: Path, dst_root: Path) -> None:
    """Copy gradcam_screening.html + screening_data/ to bundle root."""
    html_src = src_root / "gradcam_screening.html"
    if html_src.is_file():
        shutil.copy2(html_src, dst_root / "gradcam_screening.html")
    data_src = src_root / SCREENING_DATA_DIR
    data_dst = dst_root / SCREENING_DATA_DIR
    if data_src.is_dir():
        if data_dst.exists():
            shutil.rmtree(data_dst)
        shutil.copytree(data_src, data_dst)


def materialize_split_folder(
    output_dir: Path,
    bundle_root: Path,
    split_name: str,
    results_df: pd.DataFrame,
    pack_mode: str,
    project_root: Path,
) -> dict:
    """Copy split panels (+ csv) into bundle_root/split_name/."""
    dst = bundle_root / split_name
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)

    copied_panels = 0
    seen: set[str] = set()

    if pack_mode == "full":
        for path in sorted(output_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(output_dir)
            if rel.name == "gradcam_screening.html" or rel.parts[:1] == (SCREENING_DATA_DIR,):
                continue
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            if path.name.endswith("_panel.png"):
                copied_panels += 1
    else:
        for _, row in results_df.iterrows():
            panel = resolve_panel_path(row.get("panel_path"), project_root)
            if panel is None:
                continue
            try:
                rel = panel.relative_to(output_dir)
            except ValueError:
                rel = Path("panels") / panel.name
            key = str(rel).replace("\\", "/")
            if key in seen:
                continue
            seen.add(key)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(panel, target)
            copied_panels += 1

    results_df.to_csv(dst / "gradcam_results.csv", index=False)
    return {
        "split_dir": str(dst),
        "copied_panels": copied_panels,
        "results_rows": int(len(results_df)),
    }


def verify_bundle_layout(bundle_root: Path) -> dict:
    """Ensure deliverable is one folder with HTML at root."""
    bundle_root = bundle_root.resolve()
    html = bundle_root / "gradcam_screening.html"
    data_dir = bundle_root / SCREENING_DATA_DIR
    manifest = data_dir / "manifest.js"
    checks = {
        "bundle_root": str(bundle_root),
        "html_at_root": html.is_file(),
        "screening_data": data_dir.is_dir(),
        "manifest_js": manifest.is_file(),
        "chunk_files": len(list(data_dir.glob("chunk_*.js"))),
        "split_dirs": [],
        "errors": [],
    }
    if not checks["html_at_root"]:
        checks["errors"].append("缺少根目录 gradcam_screening.html")
    if not checks["screening_data"]:
        checks["errors"].append("缺少 screening_data/ 目录")
    if not checks["manifest_js"]:
        checks["errors"].append("缺少 screening_data/manifest.js")

    for name in ("gradcam_test_external_full", "gradcam_test_prospective_full"):
        split_dir = bundle_root / name
        if split_dir.is_dir():
            n_panels = sum(1 for _ in split_dir.rglob("*_panel.png"))
            checks["split_dirs"].append({"name": name, "panels": n_panels})
            if n_panels == 0:
                checks["errors"].append(f"{name}/ 下没有 panel 图片")
        nested_html = split_dir / "gradcam_screening.html"
        if nested_html.is_file():
            checks["errors"].append(f"{name}/ 内不应有 gradcam_screening.html（唯一入口在根目录）")

    checks["ok"] = len(checks["errors"]) == 0
    return checks


def build_clinical_folder_bundle(
    bundle_root: Path,
    split_jobs: list[dict],
    unified_html_sources: list[dict],
    *,
    pack_mode: str,
    project_root: Path,
) -> dict:
    """Assemble one self-contained folder: HTML + screening_data at root, images in subfolders."""
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    bundle_root.mkdir(parents=True)

    write_bundle_readme(bundle_root / "README_筛图说明.txt")
    (bundle_root / "打开请双击_gradcam_screening.html.txt").write_text(
        "请双击同目录下的 gradcam_screening.html 开始筛图。\n"
        "请勿只拷贝 HTML，整个文件夹需一起拷贝。\n",
        encoding="utf-8",
    )

    split_stats: list[dict] = []
    for job in split_jobs:
        stats = materialize_split_folder(
            job["output_dir"],
            bundle_root,
            job["split_name"],
            job["results_df"],
            pack_mode,
            project_root,
        )
        stats["split"] = job["split"]
        split_stats.append(stats)
        print(
            f"  {job['split_name']}: {stats['copied_panels']} panels, "
            f"{stats['results_rows']} csv rows"
        )

    screening_summary = build_screening_html(
        unified_html_sources,
        bundle_root / "gradcam_screening.html",
    )
    print(
        f"  HTML at root: {bundle_root / 'gradcam_screening.html'} "
        f"({screening_summary['cases']} cases, chunks={screening_summary.get('chunk_count')})"
    )

    layout = verify_bundle_layout(bundle_root)
    if not layout["ok"]:
        raise RuntimeError("Bundle layout invalid: " + "; ".join(layout["errors"]))

    total_bytes = sum(f.stat().st_size for f in bundle_root.rglob("*") if f.is_file())
    return {
        "bundle_root": str(bundle_root.resolve()),
        "size_mb": round(total_bytes / (1024 * 1024), 2),
        "splits": split_stats,
        "screening_summary": screening_summary,
        "layout": layout,
    }


def zip_pack_files(files: list[tuple[Path, Path]], zip_path: Path) -> int:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for src, arc in files:
            zf.write(src, arcname=str(arc))
    return len(files)


def zip_folder(folder: Path, zip_path: Path) -> int:
    if zip_path.exists():
        zip_path.unlink()
    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(folder)))
                count += 1
    return count


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


def write_redirect_stub(html_path: Path, target_href: str, title: str = "请使用根目录筛图工具") -> None:
    """Replace legacy per-split HTML with auto-redirect to the unified bundle entry."""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        f"""<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0;url={target_href}">
<title>{title}</title>
<style>body{{font-family:sans-serif;padding:40px;line-height:1.7}}</style>
</head><body>
<p>此文件已弃用。正在跳转到统一筛图入口…</p>
<p>若未自动跳转，请打开：<a href="{target_href}">{target_href}</a></p>
</body></html>
""",
        encoding="utf-8",
    )


def write_legacy_redirect_stubs(exp_dir: Path, bundle_name: str = "gradcam_clinical_screening") -> None:
    """Point old experiment subfolder HTML paths to the unified bundle."""
    targets = {
        exp_dir / "gradcam_screening.html": f"{bundle_name}/gradcam_screening.html",
        exp_dir / "gradcam_test_external_full" / "gradcam_screening.html": (
            f"../{bundle_name}/gradcam_screening.html?split=test_external"
        ),
        exp_dir / "gradcam_test_prospective_full" / "gradcam_screening.html": (
            f"../{bundle_name}/gradcam_screening.html?split=test_prospective"
        ),
    }
    for path, href in targets.items():
        if path.parent.is_dir() or path.parent == exp_dir:
            write_redirect_stub(path, href, title="GradCAM 筛图（已迁移）")


def write_bundle_readme(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "Grad-CAM 测试集筛图 — 使用说明",
                "========================",
                "",
                "【文件夹结构】",
                "  gradcam_screening.html           ← 双击打开（唯一入口）",
                "  screening_data/                  索引分片（自动加载，勿删）",
                "  gradcam_test_external_full/      外部测试 panel 图片",
                "  gradcam_test_prospective_full/   2025 前瞻 panel 图片",
                "",
                "【操作步骤】",
                "  1. 将整个文件夹拷贝到本地（不要只拷 HTML）",
                "  2. 双击 gradcam_screening.html",
                "  3. 顶部标签切换：全部 / 外部测试 / 2025前瞻",
                "  4. 质量差点「✕ 剔除」或按 X；质量好点「✓ 保留」或按 K",
                "  5. 可按数据集分别导出剔除 CSV",
                "",
                "【快捷键】",
                "  → 下一张   X 剔除   K 保留   Z 撤销   F 全屏   ? 帮助",
                "  Home 跳到未浏览   1/2/3 快选原因   +/- 缩放",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_readme(path: Path, bundle_info: dict, summaries: list[dict]) -> None:
    lines = [
        "Grad-CAM 临床筛图文件夹",
        "====================",
        f"生成时间: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"交付文件夹: {bundle_info.get('bundle_root', '')}",
        f"总大小: {bundle_info.get('size_mb', 0)} MB",
        "",
        "打开方式: 进入文件夹，双击 gradcam_screening.html",
        "",
        "目录结构:",
        "  gradcam_screening.html",
        "  screening_data/",
        "  gradcam_test_external_full/panels/...",
        "  gradcam_test_prospective_full/panels/...",
        "  README_筛图说明.txt",
        "",
    ]
    for summary in summaries:
        lines.extend(
            [
                f"Split: {summary['split']}",
                f"  gradcam_results 行数: {summary['gradcam_results_rows']}",
                f"  panel PNG 文件数: {summary['panel_png_count']}",
                f"  正确 / 分错: {summary['correct']} / {summary['misclassified']}",
                "",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch Grad-CAM + assemble clinical screening folder")
    parser.add_argument("--exp-dir", type=str, default=DEFAULT_EXP)
    parser.add_argument(
        "--splits",
        nargs="+",
        choices=tuple(SPLIT_SPECS),
        default=["test_external", "test_prospective"],
    )
    parser.add_argument("--skip-run", action="store_true", help="Only package existing outputs")
    parser.add_argument(
        "--zip",
        action="store_true",
        help="Also create a zip archive of the folder bundle (optional)",
    )
    parser.add_argument(
        "--pack-mode",
        choices=("slim", "full"),
        default="slim",
        help="slim: panel PNG + gradcam_results.csv only; full: entire split output dir",
    )
    parser.add_argument(
        "--include-prospective-in-external",
        action="store_true",
        help="Keep int/prospective rows in external unified view (default: excluded as duplicate)",
    )
    parser.add_argument(
        "--bundle-root",
        type=str,
        default=None,
        help=f"Output folder (default: exp_dir/{DEFAULT_BUNDLE_NAME})",
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
        help="Resume Grad-CAM runs from existing gradcam_results.csv",
    )
    parser.add_argument(
        "--refresh-pack",
        action="store_true",
        help="Rebuild folder bundle (HTML + panels) from existing Grad-CAM outputs",
    )
    args, unknown = parser.parse_known_args()

    exp_dir = Path(args.exp_dir)
    if not exp_dir.is_absolute():
        exp_dir = PROJECT_ROOT / exp_dir
    if not exp_dir.is_dir():
        raise SystemExit(f"Experiment dir not found: {exp_dir}")

    gradcam_extra = ["--layout", args.layout, "--cam-focus", args.cam_focus]
    if args.max_samples is not None:
        gradcam_extra.extend(["--max-samples", str(args.max_samples)])
    gradcam_extra.extend(unknown)

    bundle_root = Path(args.bundle_root) if args.bundle_root else exp_dir / DEFAULT_BUNDLE_NAME
    external_holdout_only = not args.include_prospective_in_external

    summaries: list[dict] = []
    split_jobs: list[dict] = []

    for split in args.splits:
        spec = SPLIT_SPECS[split]
        output_dir = exp_dir / spec["output_dir_name"]
        input_csv = resolve_split_input_csv(exp_dir, spec)

        if not args.skip_run and not args.refresh_pack:
            if output_dir.exists() and args.max_samples is None and not args.resume:
                shutil.rmtree(output_dir)
            run_gradcam_split(exp_dir, split, output_dir, gradcam_extra, resume=args.resume)

        if not output_dir.is_dir():
            print(f"Warning: missing output dir for {split}: {output_dir}")
            continue

        results_csv = output_dir / "gradcam_results.csv"
        if results_csv.is_file():
            results_df = pd.read_csv(results_csv)
            pack_df = filter_results_df(results_df, split, external_holdout_only)
        else:
            pack_df = None

        summary = summarize_split(output_dir, split, input_csv, pack_df)
        summary["pack_mode"] = args.pack_mode
        summaries.append(summary)

        if pack_df is not None and len(pack_df):
            split_jobs.append(
                {
                    "split": split,
                    "split_name": spec["output_dir_name"],
                    "output_dir": output_dir,
                    "results_df": pack_df,
                }
            )

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
    unified_for_html: list[dict] = []
    if screening_sources:
        unified_for_html = []
        for src in screening_sources:
            if not src.get("include_in_unified"):
                continue
            u = dict(src)
            if u.get("split") == "test_external":
                u["external_holdout_only"] = True
            unified_for_html.append(u)

    bundle_info: dict = {}
    if split_jobs and unified_for_html and (args.skip_run or args.refresh_pack or not args.skip_run):
        print(f"\n=== Assembling folder bundle: {bundle_root} ===")
        bundle_info = build_clinical_folder_bundle(
            bundle_root,
            split_jobs,
            unified_for_html,
            pack_mode=args.pack_mode,
            project_root=PROJECT_ROOT,
        )
        write_legacy_redirect_stubs(exp_dir, bundle_name=bundle_root.name)
        screening_summary = bundle_info.get("screening_summary")
        print(f"Bundle ready: {bundle_root} ({bundle_info['size_mb']} MB)")
        print(f"Open: {bundle_root / 'gradcam_screening.html'}")

    zip_path = None
    if args.zip and bundle_root.is_dir():
        zip_path = bundle_root.parent / f"{bundle_root.name}.zip"
        n = zip_folder(bundle_root, zip_path)
        size_mb = round(zip_path.stat().st_size / (1024 * 1024), 2)
        print(f"Optional zip: {zip_path} ({size_mb} MB, {n} files)")

    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "exp_dir": str(exp_dir),
        "bundle_root": str(bundle_root.resolve()),
        "bundle_size_mb": bundle_info.get("size_mb"),
        "layout": args.layout,
        "cam_focus": args.cam_focus,
        "pack_mode": args.pack_mode,
        "external_holdout_only": external_holdout_only,
        "splits": summaries,
    }
    if screening_summary:
        manifest["screening_html"] = str((bundle_root / "gradcam_screening.html").resolve())
        manifest["screening_cases"] = screening_summary["cases"]
        manifest["screening_split_counts"] = screening_summary["split_counts"]
        manifest["screening_chunks"] = screening_summary.get("chunk_count")
    if bundle_info:
        manifest["bundle_splits"] = bundle_info.get("splits")
        manifest["bundle_layout"] = bundle_info.get("layout")
    if zip_path and zip_path.is_file():
        manifest["zip_path"] = str(zip_path)
        manifest["zip_size_mb"] = round(zip_path.stat().st_size / (1024 * 1024), 2)

    manifest_path = bundle_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_readme(bundle_root / "README_交付说明.txt", bundle_info, summaries)
    print(f"\nDeliverable folder: {bundle_root.resolve()}")
    print(f"  gradcam_screening.html  ← 根目录唯一入口")
    print(f"  manifest.json           ← 包内清单")


if __name__ == "__main__":
    main()
