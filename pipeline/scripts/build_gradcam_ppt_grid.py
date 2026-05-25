#!/usr/bin/env python3
"""Build PPT-ready grid: 8 columns (one dataset each), 6 visualization rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PIPELINE_ROOT.parent
CLASS_NAMES = ["T1", "T2", "T3", "T4+"]

# Pipeline order: crop_ui → ROI/det → segmentation → Grad-CAM (global then ROI-local)
ROW_SPECS = [
    ("original", "Original (crop_ui)", "_original_display.png"),
    ("expanded_roi", "Grad-CAM region\n(ROI expand + 40 px)", "_expanded_roi_box.png"),
    ("pred_lesion", "Pred lesion\n(DINOv3 seg)", "_pred_lesion_overlay.png"),
    ("gt_lesion", "GT lesion", "_gt_lesion_overlay.png"),
    ("global_gradcam", "Global Grad-CAM\n(@ predicted class)", "_global_gradcam_on_original.png"),
    ("roi_gradcam", "ROI Grad-CAM\n(local branch)", "_roi_gradcam_on_original.png"),
]

TIMES_REGULAR = [
    Path.home() / ".fonts" / "Times.TTF",
    Path("/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"),
]
TIMES_BOLD = [
    Path.home() / ".fonts" / "Timesbd.TTF",
    Path("/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman_Bold.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"),
]
_FONT_CACHE: dict[tuple[bool, int], ImageFont.FreeTypeFont] = {}


def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    key = (bold, size)
    if key not in _FONT_CACHE:
        paths = TIMES_BOLD if bold else TIMES_REGULAR
        for path in paths:
            if path.is_file():
                _FONT_CACHE[key] = ImageFont.truetype(str(path), size=size)
                break
        else:
            _FONT_CACHE[key] = ImageFont.load_default()
    return _FONT_CACHE[key]


def load_rgb(path: Path | None, max_side: int | None = None) -> np.ndarray | None:
    if path is None or not path.is_file():
        return None
    img = np.array(Image.open(path).convert("RGB"))
    if max_side is not None and max(img.shape[0], img.shape[1]) > max_side:
        h, w = img.shape[:2]
        s = max_side / float(max(h, w))
        img = cv2.resize(img, (int(round(w * s)), int(round(h * s))), interpolation=cv2.INTER_AREA)
    return img


def letterbox_cell(
    img: np.ndarray,
    cell_w: int,
    cell_h: int,
    bg: tuple[int, int, int] = (255, 255, 255),
    fill: float = 0.94,
) -> np.ndarray:
    h, w = img.shape[:2]
    scale = min(cell_w / w, cell_h / h) * fill
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.full((cell_h, cell_w, 3), bg, dtype=np.uint8)
    y0 = (cell_h - nh) // 2
    x0 = (cell_w - nw) // 2
    canvas[y0 : y0 + nh, x0 : x0 + nw] = resized
    return canvas


def find_ppt_assets(gradcam_dir: Path, image_path: str, true_label: int, pred: int) -> dict[str, Path | None]:
    """Locate ppt_assets by filename stem (pred folder may differ from CSV)."""
    stem = Path(image_path).stem
    out: dict[str, Path | None] = {key: None for key, _, _ in ROW_SPECS}
    for key, _, suffix in ROW_SPECS:
        hits = sorted(gradcam_dir.glob(f"**/ppt_assets/{stem}{suffix}"))
        if hits:
            out[key] = hits[0]
    if all(v is not None for v in out.values()):
        return out

    true_name = CLASS_NAMES[int(true_label)]
    pred_name = CLASS_NAMES[int(pred)]
    status = "correct" if int(true_label) == int(pred) else f"misclassified_as_{pred_name}"
    ppt_root = gradcam_dir / "panels" / true_name / status / "ppt_assets"
    if ppt_root.is_dir():
        for key, _, suffix in ROW_SPECS:
            if out[key] is not None:
                continue
            cand = ppt_root / f"{stem}{suffix}"
            if cand.is_file():
                out[key] = cand
    return out


def merge_gradcam_preds(df: pd.DataFrame, gradcam_dir: Path) -> pd.DataFrame:
    """Use model preds from gradcam_results.csv when available."""
    results_csv = gradcam_dir / "gradcam_results.csv"
    if not results_csv.is_file():
        return df
    res = pd.read_csv(results_csv)
    if "image_path" not in res.columns:
        return df
    pred_cols = ["pred_class", "pred_name", "prob_T1", "prob_T2", "prob_T3", "prob_T4+"]
    keep = ["image_path"] + [c for c in pred_cols if c in res.columns]
    res = res[keep].drop_duplicates(subset=["image_path"])
    out = df.merge(res, on="image_path", how="left", suffixes=("", "_gc"))
    if "pred_class" in out.columns:
        out["pred"] = out["pred_class"].fillna(out.get("pred")).astype(int)
    return out


def column_title_lines(row: pd.Series) -> list[str]:
    gt = CLASS_NAMES[int(row["label"])]
    pr = str(row.get("pred_name", CLASS_NAMES[int(row.get("pred", row["label"]))]))
    ds = str(row.get("dataset_display", row.get("dataset_key", "")))
    pid = str(row.get("patient_id", ""))
    if int(row["label"]) == int(row.get("pred", row["label"])):
        line2 = f"{pid}  GT {gt} (ok)"
    else:
        line2 = f"{pid}  GT {gt} -> {pr}"
    lines = [ds, line2]
    prob_cols = ["prob_T1", "prob_T2", "prob_T3", "prob_T4+"]
    if prob_cols[0] in row.index and not pd.isna(row.get(prob_cols[0])):
        pred_i = int(row.get("pred", row["label"]))
        pp = float(row[prob_cols[pred_i]])
        lines.append(f"P({CLASS_NAMES[pred_i]})={pp:.2f}")
    return lines


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_multiline_in_box(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    box: tuple[int, int, int, int],
    font_size: int,
    *,
    align: str = "left",
    valign: str = "center",
    color: tuple[int, int, int] = (20, 20, 20),
    line_gap: int | None = None,
) -> None:
    """Draw multiline bold text inside (x0, y0, x1, y1), aligned to the image cell."""
    font = _load_font(font_size, bold=True)
    if line_gap is None:
        line_gap = max(4, font_size // 5)
    sizes = [_text_size(draw, line, font) for line in lines]
    total_h = sum(h for _, h in sizes) + line_gap * max(0, len(lines) - 1)
    x0, y0, x1, y1 = box
    box_w, box_h = x1 - x0, y1 - y0
    if valign == "center":
        y = y0 + max(0, (box_h - total_h) // 2)
    elif valign == "bottom":
        y = y1 - total_h
    else:
        y = y0
    for line, (tw, th) in zip(lines, sizes):
        if align == "right":
            x = x1 - tw - 4
        elif align == "center":
            x = x0 + max(0, (box_w - tw) // 2)
        else:
            x = x0 + 4
        draw.text(
            (x, y),
            line,
            font=font,
            fill=color,
            stroke_width=1,
            stroke_fill=(255, 255, 255),
        )
        y += th + line_gap


def build_grid(
    df: pd.DataFrame,
    gradcam_dir: Path,
    output_path: Path,
    cell_w: int = 480,
    cell_h: int = 300,
    header_h: int = 88,
    label_w: int = 248,
    dpi: int = 200,
    row_keys: list[str] | None = None,
    title_font_size: int = 26,
    header_font_size: int = 19,
    row_label_font_size: int = 22,
    title_text: str | None = None,
) -> None:
    df = merge_gradcam_preds(df, gradcam_dir)
    n = len(df)
    if row_keys is None:
        row_keys = [spec[0] for spec in ROW_SPECS]
    row_labels = {spec[0]: spec[1] for spec in ROW_SPECS}
    n_rows = len(row_keys)

    title_h = 52
    canvas_w = label_w + n * cell_w
    canvas_h = title_h + header_h + n_rows * cell_h
    canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    if title_text is None:
        title_text = "T2/T3 pipeline: ROI & seg → Grad-CAM (6 ext + internal val + prospective)"
    title_font = _load_font(title_font_size, bold=True)
    tw, th = _text_size(draw, title_text, title_font)
    draw.text(
        (label_w + max(0, (n * cell_w - tw) // 2), (title_h - th) // 2),
        title_text,
        font=title_font,
        fill=(0, 0, 0),
        stroke_width=1,
        stroke_fill=(255, 255, 255),
    )

    placeholder = np.full((cell_h, cell_w, 3), 235, dtype=np.uint8)
    y0 = title_h + header_h

    for col, (_, row) in enumerate(df.iterrows()):
        img_path = Path(str(row["image_path"]))
        true_label = int(row["label"])
        pred = int(row.get("pred", true_label))
        assets = find_ppt_assets(gradcam_dir, str(img_path), true_label, pred)
        fallback_orig = load_rgb(img_path)

        x_col = label_w + col * cell_w
        header_img = Image.new("RGB", (cell_w, header_h), (255, 255, 255))
        hdraw = ImageDraw.Draw(header_img)
        draw_multiline_in_box(
            hdraw,
            column_title_lines(row),
            (0, 0, cell_w, header_h),
            header_font_size,
            align="center",
            valign="center",
        )
        canvas.paste(header_img, (x_col, title_h))

        for r, key in enumerate(row_keys):
            y_cell = y0 + r * cell_h
            path = assets.get(key)
            cell_img = load_rgb(path)
            if cell_img is None:
                if key == "original" and fallback_orig is not None:
                    cell_img = fallback_orig
                else:
                    cell_img = placeholder
            cell = letterbox_cell(cell_img, cell_w, cell_h)
            canvas.paste(Image.fromarray(cell), (x_col, y_cell))

    for r, key in enumerate(row_keys):
        y_cell = y0 + r * cell_h
        label_img = Image.new("RGB", (label_w, cell_h), (255, 255, 255))
        ldraw = ImageDraw.Draw(label_img)
        draw_multiline_in_box(
            ldraw,
            row_labels.get(key, key).split("\n"),
            (0, 0, label_w, cell_h),
            row_label_font_size,
            align="right",
            valign="center",
        )
        canvas.paste(label_img, (0, y_cell))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, dpi=(dpi, dpi))
    print(f"Saved: {output_path} ({canvas.size[0]}x{canvas.size[1]})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build multi-row PPT grid from Grad-CAM ppt_assets")
    parser.add_argument(
        "--cases-csv",
        type=Path,
        default=PIPELINE_ROOT / "data/tstaging_4class/eval/t2t3_ppt_grid_8sources.csv",
    )
    parser.add_argument("--gradcam-dir", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "docs/mainline/figures/results/t2t3_gradcam_ppt_grid_8x6_multicenter.png",
    )
    parser.add_argument("--cell-w", type=int, default=480)
    parser.add_argument("--cell-h", type=int, default=300)
    parser.add_argument("--label-w", type=int, default=248)
    parser.add_argument("--header-h", type=int, default=88)
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--row-label-font", type=int, default=22)
    parser.add_argument("--header-font", type=int, default=19)
    parser.add_argument("--title-font", type=int, default=26)
    parser.add_argument(
        "--rows",
        type=str,
        default="all",
        help="Comma-separated row keys or 'all'. Keys: original,expanded_roi,pred_lesion,gt_lesion,global_gradcam,roi_gradcam",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Figure title (default: multi-center grid title)",
    )
    args = parser.parse_args()

    df = pd.read_csv(args.cases_csv)
    if "pred" not in df.columns and "pred_class" in df.columns:
        df["pred"] = df["pred_class"]

    if args.rows.strip().lower() == "all":
        row_keys = [spec[0] for spec in ROW_SPECS]
    elif args.rows.strip().lower() == "original":
        row_keys = ["original"]
    else:
        row_keys = [x.strip() for x in args.rows.split(",") if x.strip()]

    build_grid(
        df,
        args.gradcam_dir,
        args.output,
        cell_w=args.cell_w,
        cell_h=args.cell_h,
        header_h=args.header_h,
        label_w=args.label_w,
        dpi=args.dpi,
        row_keys=row_keys,
        title_font_size=args.title_font,
        header_font_size=args.header_font,
        row_label_font_size=args.row_label_font,
        title_text=args.title,
    )

    meta = {
        "cases_csv": str(args.cases_csv),
        "gradcam_dir": str(args.gradcam_dir),
        "output": str(args.output),
        "datasets": df["dataset_display"].astype(str).tolist() if "dataset_display" in df.columns else [],
        "row_keys": row_keys,
        "font": "Times New Roman Bold",
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
