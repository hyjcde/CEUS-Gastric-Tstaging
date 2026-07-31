#!/usr/bin/env python3
"""Generate crop_ui MP4 clips for reader-study cases (prospective + external).

Sources:
- Prospective: dataset/internal/manifest.csv (group_targets contains prospective_2025)
- External: dataset/external/manifest.csv

For each slice:
- Raw AVI/MP4: ffmpeg spatial crop using ui_crop_rect
- Single-frame DICOM/JPG: export cropped still, then loop to short MP4 for the viewer

Output layout (matches dataset/DATASET_GUIDE.md):
  dataset/internal/prospective_2025/2025/crop_ui/videos/{token}.mp4
  dataset/internal/training_2018_2024/{year}/crop_ui/videos/{token}.mp4
  dataset/external/{center}/crop_ui/videos/{token}.mp4
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
try:
    import pydicom
except ImportError:  # Optional unless a DICOM source is actually read.
    pydicom = None
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys_path_inserted = False
if str(PROJECT_ROOT / "scripts") not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT / "scripts"))

from reader_video_config import (  # noqa: E402
    DEFAULT_CONFIG_PATH,
    find_video_in_roots,
    get_raw_video_search_roots,
    load_video_paths_config,
    media_token_from_sample_id,
)
from repo_paths import (  # noqa: E402
    PROJECT_ROOT as REPO_ROOT,
    RAW_LEGACY_EXTERNAL_SURGERY,
    RAW_LEGACY_GASTRIC,
)

DEFAULT_MANIFEST = PROJECT_ROOT / "dataset/internal/manifest.csv"
DEFAULT_EXTERNAL_MANIFEST = PROJECT_ROOT / "dataset/external/manifest.csv"
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "dataset/internal/prospective_2025/2025/crop_ui/videos"
)
DEFAULT_EXTERNAL_OUTPUT_DIR = PROJECT_ROOT / "dataset/external/crop_ui/videos"
EXTERNAL_DATASET_ROOT = PROJECT_ROOT / "dataset/external"
INTERNAL_TRAINING_ROOT = PROJECT_ROOT / "dataset/internal/training_2018_2024"
INTERNAL_YEAR_PREFIXES: list[tuple[str, str]] = [
    ("2018直接手术", "2018"),
    ("2019年直接手术", "2019"),
    ("20-23直接手术", "2020_2023"),
    ("2024年直接手术", "2024"),
]
LEGACY_INTERNAL_PREFIX = "胃癌分期/"
LEGACY_EXTERNAL_PREFIX = "胃癌直接手术外部测试集/"
RAW_PREFIX = LEGACY_INTERNAL_PREFIX
RAW_ROOT = RAW_LEGACY_GASTRIC
EXTERNAL_RAW_ROOT = RAW_LEGACY_EXTERNAL_SURGERY
VIDEO_EXTS = {".avi", ".mp4", ".mov", ".mkv"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crop prospective ultrasound videos for reader study.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--external-manifest", type=Path, default=DEFAULT_EXTERNAL_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--external-output-dir", type=Path, default=DEFAULT_EXTERNAL_OUTPUT_DIR)
    parser.add_argument(
        "--cohort",
        choices=("prospective", "internal", "external", "all"),
        default="prospective",
        help="Which cohort manifest rows to crop (internal=training_2018_2024 by year).",
    )
    parser.add_argument(
        "--reader-study-manifest",
        type=Path,
        default=PROJECT_ROOT / "docs/clinical_validation/reader_study_150/admin_manifest.json",
        help="If set and non-empty, only crop frames listed in reader-study admin manifest.",
    )
    parser.add_argument(
        "--skip-reader-filter",
        action="store_true",
        help="Process all manifest rows for the cohort (ignore reader-study manifest).",
    )
    parser.add_argument("--loop-seconds", type=float, default=5.0, help="Duration for single-frame loop MP4.")
    parser.add_argument("--fps", type=int, default=10)
    parser.add_argument("--limit", type=int, default=0, help="Debug: process at most N manifest rows.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="video_paths.config.json")
    parser.add_argument(
        "--raw-video-only",
        action="store_true",
        help="Only crop from true raw cine (AVI/MP4); skip still→loop fallback.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-crop even if output MP4 already exists.",
    )
    parser.add_argument(
        "--internal-years",
        type=str,
        default="",
        help="Comma-separated internal training years (2018,2019,2020_2023,2024); default=all.",
    )
    return parser.parse_args()


def crop_source_search_roots(config: dict, *, raw_video_only: bool) -> list[str]:
    if raw_video_only:
        return get_raw_video_search_roots(config)
    excluded = {
        str(Path(config.get("crop_output_dir", "")).resolve()),
        str(Path(config.get("external_crop_output_dir", "")).resolve()),
    }
    roots = [
        p
        for p in config.get("video_search_roots", [])
        if str(Path(p).resolve()) not in excluded
    ]
    raw_roots = get_raw_video_search_roots(config)
    merged: list[str] = []
    seen: set[str] = set()
    for root in [*roots, *raw_roots]:
        key = str(Path(root).resolve())
        if key not in seen:
            seen.add(key)
            merged.append(root)
    return merged


def resolve_source_media(
    row: pd.Series,
    config: dict,
    *,
    raw_video_only: bool = False,
) -> tuple[str, Path]:
    sample_id = str(row["sample_id"])
    token = media_token_from_sample_id(sample_id) or ""
    patient_id = re.match(r"([A-Za-z]?\d+)", token)
    patient_id = patient_id.group(1) if patient_id else ""
    search_roots = crop_source_search_roots(config, raw_video_only=raw_video_only)
    if config.get("prefer_raw_video_before_still", True) or raw_video_only:
        video_hit = find_video_in_roots(
            token,
            search_roots,
            patient_id=patient_id,
            recursive=bool(config.get("recursive_search", True)),
        )
        if video_hit and video_hit.suffix.lower() in VIDEO_EXTS:
            return "video", video_hit
    if raw_video_only:
        raise FileNotFoundError(f"no raw cine for token={token}")
    still_path = resolve_still_path(row)
    return still_path.suffix.lower().lstrip("."), still_path


def resolve_still_path(row: pd.Series) -> Path:
    src = Path(str(row["image_source"]))
    if src.is_file():
        return src
    resolved = resolve_raw_path(str(row["image_source"]))
    if resolved.is_file():
        return resolved
    sample_id = str(row.get("sample_id", ""))
    if sample_id:
        for center_dir in (PROJECT_ROOT / "dataset/external").iterdir():
            if not center_dir.is_dir():
                continue
            images_dir = center_dir / "crop_ui" / "images"
            if not images_dir.is_dir():
                continue
            for name in (f"{sample_id}.jpg", f"{Path(src.name).name}"):
                candidate = images_dir / name
                if candidate.is_file():
                    return candidate
    return resolved


def parse_rect(text: str) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = [int(float(v)) for v in str(text).split(",")]
    return x1, y1, x2, y2


def crop_filter(rect: tuple[int, int, int, int]) -> str:
    x1, y1, x2, y2 = rect
    w, h = max(1, x2 - x1), max(1, y2 - y1)
    return (
        f"crop={w}:{h}:{x1}:{y1},"
        "scale=trunc(iw/2)*2:trunc(ih/2)*2,"
        "setsar=1,format=yuv420p"
    )


def even_crop_slice(rgb: np.ndarray, rect: tuple[int, int, int, int]) -> np.ndarray:
    x1, y1, x2, y2 = rect
    cropped = rgb[y1:y2, x1:x2]
    h, w = cropped.shape[:2]
    even_h = h - (h % 2)
    even_w = w - (w % 2)
    return cropped[:even_h, :even_w]


def resolve_raw_path(image_source: str) -> Path:
    rel = str(image_source).replace("\\", "/")
    root_str = str(REPO_ROOT).replace("\\", "/")
    if rel.startswith(root_str):
        rel = rel[len(root_str) :].lstrip("/")
    if rel.startswith("_compat/"):
        rel = rel[len("_compat/") :]
    if rel.startswith(LEGACY_EXTERNAL_PREFIX):
        return EXTERNAL_RAW_ROOT / rel[len(LEGACY_EXTERNAL_PREFIX) :]
    if rel.startswith(LEGACY_INTERNAL_PREFIX):
        return RAW_ROOT / rel[len(LEGACY_INTERNAL_PREFIX) :]
    if rel.startswith(RAW_PREFIX):
        rel = rel[len(RAW_PREFIX) :]
    return RAW_ROOT / rel


def sample_to_output_name(sample_id: str) -> tuple[str, str] | None:
    # 2025直接手术__1000937_(1) -> 1000937_(1).mp4
    # 2025直接手术__Z0225102-1 -> Z0225102-1.mp4
    if "__" not in sample_id:
        return None
    token = sample_id.split("__", 1)[1]
    patient_id = re.match(r"([A-Za-z]?\d+)", token)
    return (patient_id.group(1) if patient_id else token), f"{token}.mp4"


def load_rgb_frame(path: Path) -> np.ndarray:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTS:
        rgb = np.array(Image.open(path).convert("RGB"))
        return rgb
    if suffix == ".dcm":
        if pydicom is None:
            raise RuntimeError("Reading DICOM requires the optional pydicom dependency")
        ds = pydicom.dcmread(str(path))
        pixel_array = ds.pixel_array
        if len(pixel_array.shape) == 2:
            img_min = float(pixel_array.min())
            img_max = float(pixel_array.max())
            if img_max > img_min:
                img_norm = ((pixel_array - img_min) / (img_max - img_min) * 255).astype(np.uint8)
            else:
                img_norm = np.zeros_like(pixel_array, dtype=np.uint8)
            return cv2.cvtColor(img_norm, cv2.COLOR_GRAY2RGB)
        return pixel_array.astype(np.uint8)
    raise ValueError(f"Unsupported still source: {path}")


def write_loop_mp4_from_still(
    still_path: Path,
    rect: tuple[int, int, int, int],
    output_path: Path,
    *,
    loop_seconds: float,
    fps: int,
) -> None:
    rgb = load_rgb_frame(still_path)
    cropped = even_crop_slice(rgb, rect)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="crop_reader_") as tmp:
        png_path = Path(tmp) / "frame.png"
        Image.fromarray(cropped).save(png_path)
        cmd = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-framerate",
            str(fps),
            "-i",
            str(png_path),
            "-t",
            str(loop_seconds),
            "-vf",
            "format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)


def transcode_cropped_video(
    video_path: Path,
    rect: tuple[int, int, int, int],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        crop_filter(rect),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def rows_from_reader_manifest(reader_manifest: Path, manifest: pd.DataFrame) -> pd.DataFrame | None:
    if not reader_manifest.exists() or reader_manifest.stat().st_size == 0:
        return None
    data = json.loads(reader_manifest.read_text(encoding="utf-8"))
    picked: list[pd.Series] = []
    for case in data.get("cases", []):
        for frame in case.get("frames", [])[:2]:
            image_path = str(frame.get("image_path", ""))
            sample_id = Path(image_path).stem
            if not sample_id:
                continue
            hit = manifest[manifest["sample_id"].astype(str) == sample_id]
            if hit.empty:
                continue
            picked.append(hit.iloc[0])
    if not picked:
        return None
    return pd.DataFrame(picked).drop_duplicates(subset=["sample_id"])


def internal_year_output(year: str) -> Path:
    return INTERNAL_TRAINING_ROOT / year / "crop_ui" / "videos"


def external_center_output(row: pd.Series, fallback: Path = DEFAULT_EXTERNAL_OUTPUT_DIR) -> Path:
    center = str(row.get("group_targets", "")).strip()
    if center and center not in {"training_2018_2024", "prospective_2025"}:
        return EXTERNAL_DATASET_ROOT / center / "crop_ui" / "videos"
    return fallback


def cohort_jobs(args: argparse.Namespace, config: dict) -> list[tuple[str, Path, Path, pd.DataFrame]]:
    jobs: list[tuple[str, Path, Path, pd.DataFrame]] = []
    if args.cohort in {"prospective", "all"}:
        out_dir = args.output_dir
        if out_dir == DEFAULT_OUTPUT_DIR:
            out_dir = Path(config.get("crop_output_dir", out_dir))
        manifest = pd.read_csv(args.manifest, low_memory=False)
        rows = manifest[
            manifest["group_targets"].astype(str).str.contains("prospective_2025", na=False)
        ].copy()
        jobs.append(("prospective", args.manifest, out_dir, rows))
    if args.cohort in {"internal", "all"}:
        manifest = pd.read_csv(args.manifest, low_memory=False)
        training = manifest[
            ~manifest["group_targets"].astype(str).str.contains("prospective_2025", na=False)
        ].copy()
        year_filter = {
            y.strip()
            for y in str(args.internal_years).split(",")
            if y.strip()
        }
        for prefix, year in INTERNAL_YEAR_PREFIXES:
            if year_filter and year not in year_filter:
                continue
            sub = training[training["sample_id"].astype(str).str.startswith(prefix)].copy()
            if sub.empty:
                continue
            jobs.append((f"internal_{year}", args.manifest, internal_year_output(year), sub))
    if args.cohort in {"external", "all"}:
        out_dir = args.external_output_dir
        if out_dir == DEFAULT_EXTERNAL_OUTPUT_DIR:
            out_dir = Path(config.get("external_crop_output_dir", out_dir))
        manifest = pd.read_csv(args.external_manifest, low_memory=False)
        jobs.append(("external", args.external_manifest, out_dir, manifest.copy()))
    return jobs


def main() -> None:
    args = parse_args()
    config = load_video_paths_config(args.config)
    results: list[dict] = []
    for cohort, manifest_path, output_dir, rows in cohort_jobs(args, config):
        use_reader_filter = (
            not args.skip_reader_filter
            and args.reader_study_manifest.exists()
            and args.reader_study_manifest.stat().st_size > 0
        )
        if use_reader_filter:
            reader_rows = rows_from_reader_manifest(args.reader_study_manifest, rows)
            if reader_rows is not None:
                rows = reader_rows
                print(f"[INFO] {cohort} reader-study frame list: {len(rows)} slices")
            else:
                print(f"[WARN] {cohort}: no manifest rows matched reader-study frames")

        if args.limit:
            rows = rows.head(args.limit)

        print(f"[INFO] Cropping {cohort} -> {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        for _, row in rows.iterrows():
            sample_id = str(row["sample_id"])
            parsed = sample_to_output_name(sample_id)
            if not parsed:
                results.append(
                    {"cohort": cohort, "sample_id": sample_id, "status": "skip", "error": "unparsed sample_id"}
                )
                continue
            patient_id, out_name = parsed
            row_output_dir = (
                external_center_output(row, output_dir)
                if cohort == "external"
                else output_dir
            )
            out_path = row_output_dir / out_name
            if not args.force and out_path.exists() and out_path.stat().st_size > 0:
                results.append(
                    {
                        "cohort": cohort,
                        "sample_id": sample_id,
                        "patient_id": patient_id,
                        "output": str(out_path.relative_to(PROJECT_ROOT)),
                        "source": "",
                        "status": "ok",
                        "mode": "cached",
                    }
                )
                continue
            rect = parse_rect(str(row["ui_crop_rect"]))

            if args.dry_run:
                kind, src = resolve_source_media(row, config, raw_video_only=args.raw_video_only)
                results.append(
                    {
                        "cohort": cohort,
                        "sample_id": sample_id,
                        "patient_id": patient_id,
                        "output": str(out_path),
                        "source": str(src),
                        "status": "dry_run",
                        "mode": kind,
                    }
                )
                continue

            try:
                kind, src = resolve_source_media(row, config, raw_video_only=args.raw_video_only)
                if not src.exists():
                    raise FileNotFoundError(src)
                if kind == "video" or src.suffix.lower() in VIDEO_EXTS:
                    try:
                        transcode_cropped_video(src, rect, out_path)
                        mode = "raw_cropped"
                    except (subprocess.CalledProcessError, OSError) as ffmpeg_exc:
                        if args.raw_video_only:
                            raise
                        still = resolve_still_path(row)
                        if still.is_file() and (
                            still.suffix.lower() in IMAGE_EXTS or still.suffix.lower() == ".dcm"
                        ):
                            write_loop_mp4_from_still(
                                still,
                                rect,
                                out_path,
                                loop_seconds=args.loop_seconds,
                                fps=args.fps,
                            )
                            mode = "loop_still_fallback"
                        else:
                            raise ffmpeg_exc
                elif args.raw_video_only:
                    raise ValueError(f"raw-video-only: unsupported source {src}")
                elif src.suffix.lower() in IMAGE_EXTS or src.suffix.lower() == ".dcm":
                    write_loop_mp4_from_still(
                        src,
                        rect,
                        out_path,
                        loop_seconds=args.loop_seconds,
                        fps=args.fps,
                    )
                    mode = "loop_still"
                else:
                    raise ValueError(f"unsupported source type: {src.suffix}")
                results.append(
                    {
                        "cohort": cohort,
                        "sample_id": sample_id,
                        "patient_id": patient_id,
                        "output": str(out_path.relative_to(PROJECT_ROOT)),
                        "source": str(src.relative_to(PROJECT_ROOT)),
                        "status": "ok",
                        "mode": mode,
                    }
                )
                print(f"[OK] {cohort}/{out_name} <- {src.name} ({mode})")
            except Exception as exc:  # noqa: BLE001
                results.append(
                    {
                        "cohort": cohort,
                        "sample_id": sample_id,
                        "patient_id": patient_id,
                        "output": str(out_path),
                        "source": str(row.get("image_source", "")),
                        "status": "error",
                        "error": str(exc),
                    }
                )
                print(f"[ERR] {cohort}/{sample_id}: {exc}")

    report = pd.DataFrame(results)
    slug = str(args.cohort).replace("/", "_")
    report_path = PROJECT_ROOT / "dataset" / f"video_crop_report_{slug}.csv"
    report.to_csv(report_path, index=False)

    ok = int((report["status"] == "ok").sum()) if not report.empty else 0
    err = int((report["status"] == "error").sum()) if not report.empty else 0
    print(
        json.dumps(
            {
                "cohort": args.cohort,
                "processed": len(report),
                "ok": ok,
                "errors": err,
                "report": str(report_path.relative_to(PROJECT_ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
