#!/usr/bin/env python3
"""Benchmark the active SAM2 prompt model on a patient-disjoint holdout."""

from __future__ import annotations

import argparse
import base64
import csv
import json
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data/processed/sms/baseline_2d_unet_holdout_crop_ui/dataset_manifest.json"
MODES = ("box", "jitter_box", "point", "box_plus_point")


def patient_key(sample_id: str) -> str:
    return re.sub(r"[-_]\d+$", "", str(sample_id))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--sam-url", default="http://127.0.0.1:8767/api/sam/interactive-analyze")
    parser.add_argument("--max-patients", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260802)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def load_cases(manifest: Path, max_patients: int) -> list[dict[str, str]]:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    by_patient: dict[str, dict[str, str]] = {}
    for row in data.get("cases", []):
        if row.get("target_split") != "test":
            continue
        image = Path(str(row.get("prepared_image", "")))
        label = Path(str(row.get("prepared_label", "")))
        if not image.is_file() or not label.is_file():
            continue
        key = patient_key(str(row.get("sample_id", row.get("case_id", ""))))
        by_patient.setdefault(key, row)
    return [by_patient[key] for key in sorted(by_patient)[:max_patients]]


def mask_bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)


def encode_image(image: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    if not ok:
        raise RuntimeError("image encoding failed")
    return base64.b64encode(encoded.tobytes()).decode("ascii")


def polygon_mask(polygon: object, width: int, height: int) -> np.ndarray:
    if not isinstance(polygon, list) or len(polygon) < 3:
        return np.zeros((height, width), dtype=np.uint8)
    points = np.asarray(
        [[float(point[0]), float(point[1])] for point in polygon if isinstance(point, list) and len(point) >= 2],
        dtype=np.float32,
    )
    if len(points) < 3:
        return np.zeros((height, width), dtype=np.uint8)
    if float(np.max(np.abs(points))) <= 1.5:
        points[:, 0] *= width
        points[:, 1] *= height
    points[:, 0] = np.clip(points[:, 0], 0, width - 1)
    points[:, 1] = np.clip(points[:, 1], 0, height - 1)
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [np.round(points).astype(np.int32)], 1)
    return mask


def boundary(mask: np.ndarray) -> np.ndarray:
    eroded = cv2.erode(mask.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=1)
    return ((mask > 0) & (eroded == 0)).astype(np.uint8)


def segmentation_metrics(pred: np.ndarray, target: np.ndarray) -> dict[str, float | int]:
    pred = pred > 0
    target = target > 0
    intersection = int(np.logical_and(pred, target).sum())
    union = int(np.logical_or(pred, target).sum())
    dice = 2 * intersection / max(int(pred.sum()) + int(target.sum()), 1)
    iou = intersection / max(union, 1)
    pred_boundary = boundary(pred)
    target_boundary = boundary(target)
    kernel = np.ones((5, 5), np.uint8)
    pred_hit = int(np.logical_and(pred_boundary > 0, cv2.dilate(target_boundary, kernel) > 0).sum())
    target_hit = int(np.logical_and(target_boundary > 0, cv2.dilate(pred_boundary, kernel) > 0).sum())
    precision = pred_hit / max(int(pred_boundary.sum()), 1)
    recall = target_hit / max(int(target_boundary.sum()), 1)
    boundary_f1 = 2 * precision * recall / max(precision + recall, 1e-8)
    return {
        "dice": round(float(dice), 6),
        "iou": round(float(iou), 6),
        "boundary_f1": round(float(boundary_f1), 6),
        "empty_prediction": int(pred.sum() == 0),
    }


def make_prompt(
    mode: str,
    bbox: tuple[int, int, int, int],
    center: tuple[float, float],
    width: int,
    height: int,
    rng: np.random.Generator,
) -> dict[str, object]:
    x1, y1, x2, y2 = bbox
    if mode == "jitter_box":
        dx = float(rng.uniform(-0.10, 0.10) * (x2 - x1))
        dy = float(rng.uniform(-0.10, 0.10) * (y2 - y1))
        x1, y1 = max(0, int(round(x1 + dx))), max(0, int(round(y1 + dy)))
        x2, y2 = min(width - 1, int(round(x2 + dx))), min(height - 1, int(round(y2 + dy)))
    prompt: dict[str, object] = {}
    if mode in {"box", "jitter_box", "box_plus_point"}:
        prompt["box"] = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
    if mode in {"point", "box_plus_point"}:
        prompt["clicks"] = [{"x": center[0], "y": center[1], "label": "positive"}]
    return prompt


def request_sam(url: str, payload: dict[str, object]) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cases = load_cases(args.manifest, args.max_patients)
    rng = np.random.default_rng(args.seed)
    rows: list[dict[str, object]] = []

    for case in cases:
        image = cv2.imread(str(case["prepared_image"]), cv2.IMREAD_COLOR)
        target = cv2.imread(str(case["prepared_label"]), cv2.IMREAD_GRAYSCALE)
        if image is None or target is None:
            continue
        height, width = target.shape[:2]
        bbox = mask_bbox(target)
        if bbox is None:
            continue
        ys, xs = np.where(target > 0)
        center = (float(xs.mean()), float(ys.mean()))
        image_b64 = encode_image(image)
        for mode in MODES:
            payload: dict[str, object] = {
                "case_id": str(case.get("case_id", "")),
                "frame_png_b64": image_b64,
                "image_width": width,
                "image_height": height,
                "llm_report": False,
                **make_prompt(mode, bbox, center, width, height, rng),
            }
            started = time.perf_counter()
            try:
                response = request_sam(args.sam_url, payload)
                predicted = polygon_mask(response.get("mask_polygon"), width, height)
                result = {
                    "patient_key": patient_key(str(case.get("sample_id", case.get("case_id", "")))),
                    "case_id": case.get("case_id"),
                    "mode": mode,
                    "sam_score": response.get("sam_score"),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    **segmentation_metrics(predicted, target),
                }
            except Exception as exc:
                result = {
                    "patient_key": patient_key(str(case.get("sample_id", case.get("case_id", "")))),
                    "case_id": case.get("case_id"),
                    "mode": mode,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            rows.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)

    with (args.output_dir / "per_case.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = sorted({key for row in rows for key in row})
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    summary: dict[str, object] = {
        "model": "active_sam2.1_hiera_tiny_finetune",
        "patients": len(cases),
        "modes": {},
    }
    for mode in MODES:
        valid = [row for row in rows if row.get("mode") == mode and "dice" in row]
        summary["modes"][mode] = {
            "n": len(valid),
            "mean_dice": round(float(np.mean([row["dice"] for row in valid])), 6) if valid else None,
            "mean_iou": round(float(np.mean([row["iou"] for row in valid])), 6) if valid else None,
            "mean_boundary_f1": round(float(np.mean([row["boundary_f1"] for row in valid])), 6) if valid else None,
            "empty_prediction_rate": round(float(np.mean([row["empty_prediction"] for row in valid])), 6) if valid else None,
            "median_latency_ms": round(float(np.median([row["latency_ms"] for row in valid])), 2) if valid else None,
        }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
