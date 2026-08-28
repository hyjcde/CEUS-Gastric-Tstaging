#!/usr/bin/env python3
"""Compare SAM3.1, DINOv3 full-image, and DINOv3 ROI LoRA; score ROI x1.10.

Research only. Does not replace UNet segmentation_primary or public Assist.

Three published protocols stay on their own canvases:
  SAM3.1 run2     oracle GT box, full image, patient-mean Dice (registry)
  DINOv3 last-2   automatic, no box, crop_ui full image (SMS)
  DINOv3 ROI m025 GT crop already cut, letterbox 512 (SMS)

ROI +10% means the method's current box is scaled by 1.10:
  SAM: tight oracle box * 1.10, still scored on the full image
  DINO ROI: current m025 crop box * 1.10, scored on letterbox 512
  DINO full: saved pred vs GT, Dice restricted to GT box * 1.10
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from eval_sam31_static_registry import (  # noqa: E402
    call_backend,
    group_for,
    mask_metric,
    polygon_mask,
    read_mask,
)
from render_dinov3_roi_crop_panel import fit_cell, load_font, overlay_mask  # noqa: E402
from render_dinov3_roi_lora_pred_panel import dice_on_masks, pick_buckets, tensorize  # noqa: E402
from run_unet2d_segmentation_baseline import load_records  # noqa: E402
from train_dinov3_roi_lora_seg import load_model, load_yaml, upsample_logits  # noqa: E402


DEFAULT_CONFIG = PROJECT_ROOT / "configs/segmentation/dinov3/vitb16_roi_lora_mlp_512_m025.yaml"
DEFAULT_CKPT = (
    PROJECT_ROOT
    / "experiments/segmentation/dinov3_vitb16_roi_lora_mlp_512_m025_20260828_full/checkpoints/best.pt"
)
DEFAULT_MANIFEST = PROJECT_ROOT / "data/processed/sms/gt_lesion_crop_upper_bound_v2_m025/dataset_manifest.json"
DEFAULT_LAST2 = (
    PROJECT_ROOT
    / "experiments/segmentation"
    / "segmentation_dinov3_vitb16_last2blocks_holdout_cropui_dataset_v20260409_20260511_r001"
)
DEFAULT_REGISTRY = PROJECT_ROOT / "data/registry/patient_media_sample_index.csv"
DEFAULT_REPORT = PROJECT_ROOT / "pipeline/experiments/reports/sam_dino_roi_expand10_20260828"
DEFAULT_VIZ = PROJECT_ROOT / "results/visualizations/segmentation"
BOX_SCALE = 1.10


def parse_cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CKPT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--last2-run", type=Path, default=DEFAULT_LAST2)
    parser.add_argument("--registry-csv", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--viz-dir", type=Path, default=DEFAULT_VIZ)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--sam-threshold", type=float, default=0.05)
    parser.add_argument("--sam-port", type=int, default=8768)
    parser.add_argument("--box-scale", type=float, default=BOX_SCALE)
    parser.add_argument("--per-bucket", type=int, default=2)
    parser.add_argument("--max-score", type=int, default=0, help="0 = whole split")
    parser.add_argument("--skip-sam-full", action="store_true")
    parser.add_argument("--skip-panel", action="store_true")
    parser.add_argument(
        "--split",
        action="append",
        dest="splits",
        choices=("external_eval", "prospective_eval"),
        default=None,
    )
    return parser.parse_args()


def inclusive_to_exclusive(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    return int(x1), int(y1), int(x2) + 1, int(y2) + 1


def exclusive_to_inclusive(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    return int(x1), int(y1), int(x2) - 1, int(y2) - 1


def scale_exclusive_box(
    box: tuple[int, int, int, int],
    width: int,
    height: int,
    scale: float,
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    crop_w = max(1.0, (x2 - x1) * float(scale))
    crop_h = max(1.0, (y2 - y1) * float(scale))
    nx1 = int(round(cx - crop_w / 2.0))
    ny1 = int(round(cy - crop_h / 2.0))
    nx2 = int(round(cx + crop_w / 2.0))
    ny2 = int(round(cy + crop_h / 2.0))
    if nx1 < 0:
        nx2 -= nx1
        nx1 = 0
    if ny1 < 0:
        ny2 -= ny1
        ny1 = 0
    if nx2 > width:
        nx1 -= nx2 - width
        nx2 = width
    if ny2 > height:
        ny1 -= ny2 - height
        ny2 = height
    nx1 = max(0, nx1)
    ny1 = max(0, ny1)
    nx2 = min(width, max(nx1 + 1, nx2))
    ny2 = min(height, max(ny1 + 1, ny2))
    return nx1, ny1, nx2, ny2


def letterbox_meta(width: int, height: int, size: int) -> tuple[int, int, int, int]:
    scale = min(size / max(width, 1), size / max(height, 1))
    nw = max(1, int(round(width * scale)))
    nh = max(1, int(round(height * scale)))
    ox = (size - nw) // 2
    oy = (size - nh) // 2
    return nw, nh, ox, oy


def unletterbox_mask(pred: np.ndarray, crop_w: int, crop_h: int) -> np.ndarray:
    nw, nh, ox, oy = letterbox_meta(crop_w, crop_h, pred.shape[1])
    patch = pred[oy : oy + nh, ox : ox + nw]
    restored = np.asarray(Image.fromarray((patch * 255).astype(np.uint8)).resize((crop_w, crop_h), Image.NEAREST))
    return restored > 0


def paste_exclusive(full_h: int, full_w: int, box: tuple[int, int, int, int], crop_mask: np.ndarray) -> np.ndarray:
    x1, y1, x2, y2 = box
    full = np.zeros((full_h, full_w), dtype=np.uint8)
    crop_w = max(1, x2 - x1)
    crop_h = max(1, y2 - y1)
    if crop_mask.shape[1] != crop_w or crop_mask.shape[0] != crop_h:
        crop_mask = np.asarray(
            Image.fromarray((crop_mask.astype(np.uint8) * 255)).resize((crop_w, crop_h), Image.NEAREST)
        ) > 0
    full[y1:y2, x1:x2] = crop_mask.astype(np.uint8)
    return full


def summarize_scores(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    by_patient: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row.get(key) is None:
            continue
        by_patient[str(row["patient_id"])].append(float(row[key]))
    patient_means = [float(np.mean(v)) for v in by_patient.values()]
    arr = np.asarray(values, dtype=np.float64)
    return {
        "n_images": float(len(values)),
        "n_patients": float(len(patient_means)),
        "image_mean": float(arr.mean()) if len(arr) else float("nan"),
        "patient_mean": float(np.mean(patient_means)) if patient_means else float("nan"),
        "zero_dice": float(np.mean(arr < 1e-6)) if len(arr) else float("nan"),
    }


def infer_roi(
    model: torch.nn.Module,
    device: torch.device,
    image: Image.Image,
    mask: Image.Image,
    size: int,
    threshold: float,
) -> tuple[np.ndarray, np.ndarray, Image.Image, float]:
    tensor, gt, boxed = tensorize(image, mask, size)
    logits = upsample_logits(model(tensor.unsqueeze(0).to(device)), (size, size))
    pred = (torch.sigmoid(logits)[0, 0].cpu().numpy() >= threshold).astype(np.uint8)
    return pred, gt, boxed, dice_on_masks(pred, gt)


def load_last2_pred(last2_run: Path, split: str, case_id: str) -> np.ndarray | None:
    path = last2_run / "inference" / split / "predictions_png" / f"{case_id}.png"
    if not path.exists():
        return None
    return (np.asarray(Image.open(path).convert("L")) > 0).astype(np.uint8)


def last2_published_dice(last2_run: Path, split: str) -> float | None:
    path = last2_run / "evaluation" / split / "sms_binary" / "summary.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return float(payload.get("mean_dice"))


def crop_pair(image: Image.Image, mask: Image.Image, exclusive_box: tuple[int, int, int, int]) -> tuple[Image.Image, Image.Image]:
    return image.crop(exclusive_box), mask.crop(exclusive_box)


def draw_boxes(
    image: Image.Image,
    boxes: list[tuple[tuple[int, int, int, int], tuple[int, int, int]]],
) -> Image.Image:
    out = image.convert("RGB").copy()
    draw = ImageDraw.Draw(out)
    width = max(3, min(out.size) // 180)
    for box, color in boxes:
        x1, y1, x2, y2 = box
        draw.rectangle([x1, y1, x2, y2], outline=color, width=width)
    return out


def sam_predict(
    port: int,
    image_path: Path,
    box: dict[str, float],
    width: int,
    height: int,
    threshold: float,
) -> np.ndarray:
    payload = {
        "frame_png_b64": "data:image/jpeg;base64," + base64.b64encode(image_path.read_bytes()).decode("ascii"),
        "image_width": width,
        "image_height": height,
        "box": box,
        "threshold": float(np.clip(threshold, 0.01, 0.99)),
    }
    prediction = call_backend(port, payload)
    return polygon_mask(prediction.get("mask_polygon"), height, width)


def sam_status(port: int) -> dict[str, Any]:
    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/sam31/status")
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def score_sam_registry(args: argparse.Namespace, scale: float) -> dict[str, Any]:
    rows = list(csv.DictReader(args.registry_csv.open(encoding="utf-8")))
    selected = [
        row
        for row in rows
        if row.get("split") in {"test_external", "test_external_newzip"}
        and row.get("cohort") in {"external", "prospective"}
        and str(row.get("usable_for_training", "true")).lower() in {"true", "1", "yes"}
    ]
    by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in selected:
        by_group[group_for(row)].append(row)
    if args.max_score:
        by_group = {name: values[: args.max_score] for name, values in by_group.items()}

    results: list[dict[str, Any]] = []
    started = time.time()
    for group, group_rows in sorted(by_group.items()):
        for index, row in enumerate(group_rows, start=1):
            image_path = Path(row.get("image_path", ""))
            if not image_path.is_absolute():
                image_path = (PROJECT_ROOT / image_path).resolve()
            mask_path = Path(row.get("roi_mask_path", ""))
            if not mask_path.is_absolute():
                mask_path = (PROJECT_ROOT / mask_path).resolve()
            image = np.asarray(Image.open(image_path).convert("RGB"))
            height, width = image.shape[:2]
            gt = read_mask(mask_path, height, width)
            item: dict[str, Any] = {
                "group": group,
                "patient_id": row.get("patient_id", ""),
                "sample_id": row.get("sample_id", ""),
                "status": "ok",
            }
            if gt is None or not gt.any():
                item.update({"status": "error", "error": "empty_mask"})
                results.append(item)
                continue
            ys, xs = np.where(gt)
            box = {"x1": float(xs.min()), "y1": float(ys.min()), "x2": float(xs.max()), "y2": float(ys.max())}
            if abs(scale - 1.0) > 1e-6:
                cx = (box["x1"] + box["x2"]) / 2.0
                cy = (box["y1"] + box["y2"]) / 2.0
                half_w = (box["x2"] - box["x1"]) * scale / 2.0
                half_h = (box["y2"] - box["y1"]) * scale / 2.0
                box = {
                    "x1": max(0.0, cx - half_w),
                    "y1": max(0.0, cy - half_h),
                    "x2": min(float(width - 1), cx + half_w),
                    "y2": min(float(height - 1), cy + half_h),
                }
            try:
                pred = sam_predict(args.sam_port, image_path, box, width, height, args.sam_threshold)
                item["metric"] = mask_metric(gt, pred)
            except Exception as exc:  # noqa: BLE001
                item.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
            results.append(item)
            if index % 100 == 0:
                print(json.dumps({"sam_group": group, "processed": index, "scale": scale}, ensure_ascii=False), flush=True)

    valid = [row for row in results if row.get("status") == "ok" and "metric" in row]
    summary: dict[str, Any] = {
        "protocol": "frozen_registry_static_sam31_oracle_box_v1",
        "box_scale": scale,
        "n_results": len(results),
        "n_valid": len(valid),
        "n_errors": len(results) - len(valid),
        "elapsed_seconds": round(time.time() - started, 2),
        "groups": {},
    }
    for group in sorted(by_group):
        group_valid = [row for row in valid if row["group"] == group]
        mapped = [
            {
                "patient_id": row["patient_id"],
                "dice": row["metric"]["dice"],
            }
            for row in group_valid
        ]
        summary["groups"][group] = summarize_scores(mapped, "dice")
    return {"summary": summary, "n_rows": len(results)}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_panel(
    split: str,
    picked: list[dict[str, Any]],
    scored: list[dict[str, Any]],
    output: Path,
    box_scale: float,
) -> None:
    cell = 220
    gap = 10
    label_h = 36
    cols = 6
    header = 72
    font = load_font(16)
    caption_font = load_font(13, cjk=True)
    title_font = load_font(20)
    width = gap + cols * (cell + gap)
    height = header + len(picked) * (cell + label_h + gap) + gap
    sheet = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    roi = summarize_scores(scored, "dice_roi")
    roi10 = summarize_scores(scored, "dice_roi_x110")
    full = summarize_scores(scored, "dice_full")
    title = (
        f"{split}: SAM oracle vs DINO full vs DINO ROI m025 / x{box_scale:.2f}. "
        f"n={len(scored)}  ROI {roi['image_mean']:.3f}  ROI+10% {roi10['image_mean']:.3f}  "
        f"full {full['image_mean']:.3f}"
    )
    draw.text((gap, 8), title, fill=(240, 240, 240), font=title_font)
    draw.text(
        (gap, 34),
        "Protocols differ. Do not rank 0.855 vs 0.854. Yellow=GT box, red=m025 crop, cyan=crop x1.10.",
        fill=(170, 170, 170),
        font=font,
    )
    headers = [
        "crop_ui + boxes",
        "GT",
        "SAM oracle",
        "DINO full auto",
        "DINO ROI m025",
        f"DINO ROI x{box_scale:.2f}",
    ]
    for col, text in enumerate(headers):
        draw.text((gap + col * (cell + gap), header - 22), text, fill=(180, 180, 180), font=font)

    for row_i, row in enumerate(picked):
        full_rgb = Image.open(row["original_image"]).convert("RGB")
        gt_img = Image.fromarray((row["gt_full"] * 255).astype(np.uint8), mode="L")
        boxed = draw_boxes(
            full_rgb,
            [
                (exclusive_to_inclusive(row["gt_box_ex"]), (255, 220, 40)),
                (row["crop_box_inc"], (255, 70, 70)),
                (exclusive_to_inclusive(row["crop_box_x110_ex"]), (80, 220, 255)),
            ],
        )
        sam_img = Image.fromarray((row["sam_oracle"] * 255).astype(np.uint8), mode="L") if row.get("sam_oracle") is not None else Image.new("L", full_rgb.size, 0)
        full_pred_img = Image.fromarray((row["full_pred"] * 255).astype(np.uint8), mode="L")
        roi_img = Image.fromarray((row["roi_full"] * 255).astype(np.uint8), mode="L")
        roi10_img = Image.fromarray((row["roi_x110_full"] * 255).astype(np.uint8), mode="L")
        tiles = [
            fit_cell(boxed, cell),
            fit_cell(overlay_mask(full_rgb, gt_img, (0, 220, 80)), cell),
            fit_cell(overlay_mask(overlay_mask(full_rgb, gt_img, (0, 220, 80)), sam_img, (255, 70, 70)), cell),
            fit_cell(overlay_mask(overlay_mask(full_rgb, gt_img, (0, 220, 80)), full_pred_img, (255, 70, 70)), cell),
            fit_cell(overlay_mask(overlay_mask(full_rgb, gt_img, (0, 220, 80)), roi_img, (255, 70, 70)), cell),
            fit_cell(overlay_mask(overlay_mask(full_rgb, gt_img, (0, 220, 80)), roi10_img, (255, 70, 70)), cell),
        ]
        y = header + row_i * (cell + label_h + gap)
        for col, tile in enumerate(tiles):
            sheet.paste(tile, (gap + col * (cell + gap), y))
        sam_txt = f"{row['dice_sam']:.3f}" if row.get("dice_sam") is not None else "na"
        draw.text(
            (gap, y + cell + 4),
            (
                f"{row['bucket']}  SAM {sam_txt}  full {row['dice_full']:.3f}  "
                f"ROI {row['dice_roi']:.3f}  ROI+10% {row['dice_roi_x110']:.3f}  |  {row['case_id']}"
            ),
            fill=(200, 200, 200),
            font=caption_font,
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    sheet.save(output.with_suffix(".pdf"))


def main() -> None:
    args = parse_cli()
    splits = args.splits or ["external_eval", "prospective_eval"]
    args.report_dir.mkdir(parents=True, exist_ok=True)
    args.viz_dir.mkdir(parents=True, exist_ok=True)

    config = load_yaml(args.config)
    image_size = int(config.get("model", {}).get("input_size", 512))
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    model, info = load_model(config, device)
    ckpt = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    _, _, eval_sources = load_records(args.manifest.resolve())
    sam_ready = False
    try:
        status = sam_status(args.sam_port)
        sam_ready = bool(status.get("ready"))
    except Exception as exc:  # noqa: BLE001
        status = {"ready": False, "error": str(exc)}

    report: dict[str, Any] = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "note": "GT-box / oracle-box upper bound. Not deployable. Do not replace Assist.",
        "box_scale": args.box_scale,
        "dino_roi_ckpt": str(args.checkpoint),
        "dino_full_run": str(args.last2_run),
        "sam_status": status,
        "init_info": {k: info.get(k) for k in ("lora_modules", "trainable", "total")},
        "splits": {},
    }

    for split in splits:
        records = list(eval_sources.get(split, []))
        if args.max_score:
            records = records[: args.max_score]
        if not records:
            raise RuntimeError(f"No records for {split}")
        scored: list[dict[str, Any]] = []
        started = time.time()
        with torch.no_grad():
            for index, rec in enumerate(records, start=1):
                full = Image.open(rec.original_image).convert("RGB")
                full_m = Image.open(rec.original_label).convert("L")
                if full.size != full_m.size:
                    full_m = full_m.resize(full.size, Image.NEAREST)
                width, height = full.size
                if rec.crop_box is None:
                    raise RuntimeError(f"Missing crop_box: {rec.case_id}")
                crop_ex = inclusive_to_exclusive(rec.crop_box)
                crop_x110_ex = scale_exclusive_box(crop_ex, width, height, args.box_scale)
                roi_img, roi_mask = crop_pair(full, full_m, crop_ex)
                roi10_img, roi10_mask = crop_pair(full, full_m, crop_x110_ex)
                pred_roi, gt_roi, _, dice_roi = infer_roi(model, device, roi_img, roi_mask, image_size, args.threshold)
                pred_roi10, gt_roi10, _, dice_roi10 = infer_roi(
                    model, device, roi10_img, roi10_mask, image_size, args.threshold
                )
                gt_full = (np.asarray(full_m, dtype=np.uint8) > 0).astype(np.uint8)
                ys, xs = np.where(gt_full)
                if len(xs) == 0:
                    gt_box_ex = (0, 0, width, height)
                else:
                    gt_box_ex = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
                gt_box_x110_ex = scale_exclusive_box(gt_box_ex, width, height, args.box_scale)
                full_pred = load_last2_pred(args.last2_run, split, rec.case_id)
                if full_pred is None or full_pred.shape != gt_full.shape:
                    dice_full = None
                    dice_full_x110 = None
                    full_pred = np.zeros_like(gt_full)
                else:
                    dice_full = dice_on_masks(full_pred, gt_full)
                    x1, y1, x2, y2 = gt_box_x110_ex
                    dice_full_x110 = dice_on_masks(full_pred[y1:y2, x1:x2], gt_full[y1:y2, x1:x2])
                scored.append(
                    {
                        "record": rec,
                        "case_id": rec.case_id,
                        "patient_id": rec.patient_id,
                        "original_image": rec.original_image,
                        "crop_box_inc": rec.crop_box,
                        "crop_box_x110_ex": crop_x110_ex,
                        "gt_box_ex": gt_box_ex,
                        "gt_full": gt_full,
                        "full_pred": full_pred,
                        "roi_full": paste_exclusive(height, width, crop_ex, unletterbox_mask(pred_roi, roi_img.size[0], roi_img.size[1])),
                        "roi_x110_full": paste_exclusive(
                            height, width, crop_x110_ex, unletterbox_mask(pred_roi10, roi10_img.size[0], roi10_img.size[1])
                        ),
                        "dice_roi": dice_roi,
                        "dice_roi_x110": dice_roi10,
                        "dice_full": dice_full,
                        "dice_full_x110": dice_full_x110,
                    }
                )
                if index % 100 == 0:
                    print(json.dumps({"split": split, "processed": index}, ensure_ascii=False), flush=True)
        split_summary = {
            "n": len(scored),
            "elapsed_seconds": round(time.time() - started, 2),
            "dino_full_published_image_mean": last2_published_dice(args.last2_run, split),
            "dino_roi_m025": summarize_scores(scored, "dice_roi"),
            "dino_roi_m025_x110": summarize_scores(scored, "dice_roi_x110"),
            "dino_full_recomputed": summarize_scores(scored, "dice_full"),
            "dino_full_inside_gt_x110": summarize_scores(scored, "dice_full_x110"),
        }
        report["splits"][split] = split_summary
        write_json(args.report_dir / f"{split}_dino_rows.json", {"summary": split_summary, "n": len(scored)})
        print(json.dumps({"split": split, **split_summary}, ensure_ascii=False), flush=True)

        if not args.skip_panel:
            picked = pick_buckets(
                [{"dice": row["dice_roi"], "patient_id": row["patient_id"], **row} for row in scored],
                args.per_bucket,
            )
            for row in picked:
                if sam_ready:
                    try:
                        height, width = row["gt_full"].shape
                        x1, y1, x2, y2 = row["gt_box_ex"]
                        pred = sam_predict(
                            args.sam_port,
                            Path(row["original_image"]),
                            {"x1": float(x1), "y1": float(y1), "x2": float(x2 - 1), "y2": float(y2 - 1)},
                            width,
                            height,
                            args.sam_threshold,
                        )
                        row["sam_oracle"] = pred.astype(np.uint8)
                        row["dice_sam"] = dice_on_masks(pred, row["gt_full"])
                    except Exception as exc:  # noqa: BLE001
                        row["sam_oracle"] = None
                        row["dice_sam"] = None
                        row["sam_error"] = str(exc)
                else:
                    row["sam_oracle"] = None
                    row["dice_sam"] = None
            panel_path = args.viz_dir / f"sam_dino_roi_compare_{split}_20260828.png"
            render_panel(split, picked, scored, panel_path, args.box_scale)
            split_summary["panel"] = str(panel_path)
            split_summary["shown"] = [
                {
                    "bucket": row["bucket"],
                    "case_id": row["case_id"],
                    "dice_roi": row["dice_roi"],
                    "dice_roi_x110": row["dice_roi_x110"],
                    "dice_full": row["dice_full"],
                    "dice_sam": row.get("dice_sam"),
                }
                for row in picked
            ]
            report["splits"][split] = split_summary
            print({"panel": str(panel_path), "shown": split_summary["shown"]}, flush=True)

    if not args.skip_sam_full:
        if not sam_ready:
            report["sam_registry_x110"] = {"skipped": True, "reason": "sam_backend_not_ready"}
        else:
            report["sam_registry_x110"] = score_sam_registry(args, args.box_scale)
            print(json.dumps(report["sam_registry_x110"]["summary"], ensure_ascii=False), flush=True)

    write_json(args.report_dir / "summary.json", report)
    print(json.dumps({"report": str(args.report_dir / "summary.json")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
