#!/usr/bin/env python3
"""Probe SAM2 + DINOv3 mask fusion on a patient-level holdout."""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
from torch.utils.data import DataLoader

from run_sabm_gus_sam2_finetune import (
    DEFAULT_SAM2_CHECKPOINT,
    PromptDataset,
    SAM2PromptSegmenter,
    binary_metrics,
    load_rows,
    patient_key,
)
from agent.tools.dinov3_segmentation_tool import DINOv3SegmentationTool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("data/processed/sms/baseline_2d_unet_holdout_crop_ui/dataset_manifest.json"))
    parser.add_argument("--sam2-checkpoint", type=Path, default=Path("experiments/segmentation/model_compare_20260802/sabm_gus_sam2_finetune_r001/best_sabm_gus_sam2.pt"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-patients", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--num-workers", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20260803)
    parser.add_argument("--device", default="cuda:0")
    return parser.parse_args()


def resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else (root / path).resolve()


def select_patients(rows: list[dict[str, Any]], max_patients: int) -> list[dict[str, Any]]:
    by_patient: dict[str, dict[str, Any]] = {}
    for row in rows:
        by_patient.setdefault(patient_key(row), row)
    return [by_patient[key] for key in sorted(by_patient)[:max_patients]]


def make_fusions(
    sam_probability: np.ndarray,
    dino_probability: np.ndarray,
    sam_mask: np.ndarray,
    dino_mask: np.ndarray,
) -> dict[str, np.ndarray]:
    kernel = np.ones((5, 5), np.uint8)
    agreement = np.logical_and(sam_mask, dino_mask).sum() / max(np.logical_or(sam_mask, dino_mask).sum(), 1)
    dino_area = float(dino_mask.mean())
    gate_accepts_dino = 0.002 <= dino_area <= 0.25 and agreement >= 0.08
    soft_mean = (0.7 * sam_probability + 0.3 * dino_probability) >= 0.5
    return {
        "sam_only": sam_mask,
        "dino_only": dino_mask,
        "intersection": sam_mask & dino_mask,
        "union": sam_mask | dino_mask,
        "soft_mean": soft_mean,
        "sam_primary_dino_dilate": sam_mask & (cv2.dilate(dino_mask.astype(np.uint8), kernel) > 0),
        "reliability_gate": soft_mean if gate_accepts_dino else sam_mask,
    }


def main() -> None:
    args = parse_args()
    root = Path.cwd()
    manifest = resolve(root, args.manifest)
    checkpoint = resolve(root, args.sam2_checkpoint)
    output_dir = resolve(root, args.output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    _, holdout = load_rows(manifest)
    rows = select_patients(holdout, args.max_patients)
    dataset = PromptDataset(rows, 1024, train=False, seed=args.seed)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers, pin_memory=True)
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    sam = SAM2PromptSegmenter(DEFAULT_SAM2_CHECKPOINT).to(device).eval()
    state = torch.load(checkpoint, map_location="cpu")
    sam.load_state_dict(state["model_state_dict"], strict=True)
    sam.eval()
    dino = DINOv3SegmentationTool(device=device)
    records: list[dict[str, Any]] = []
    rng = random.Random(args.seed)
    with torch.no_grad():
        for batch in loader:
            images = batch["image"].to(device)
            boxes = batch["box"].to(device)
            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=device.type == "cuda"):
                sam_logits = sam(images, boxes, None)
            sam_probability_batch = torch.sigmoid(sam_logits).cpu().numpy()[:, 0]
            for index, case_id in enumerate(batch["case_id"]):
                # The dataset loader preserves row order; locate by case ID for clarity.
                row = next(row for row in rows if row["case_id"] == case_id)
                image_path = str(row["prepared_image"])
                dino_result = dino.execute(image_path=image_path, output_dir=str(output_dir / "dino_outputs"))
                dino_probability = dino.get_cached_probability(image_path)
                dino_mask = dino.get_cached_mask(image_path)
                height = int(batch["original_height"][index])
                width = int(batch["original_width"][index])
                sam_probability = cv2.resize(
                    sam_probability_batch[index].astype(np.float32),
                    (width, height),
                    interpolation=cv2.INTER_LINEAR,
                )
                sam_mask = sam_probability >= 0.5
                target = cv2.imread(batch["label_path"][index], cv2.IMREAD_GRAYSCALE) > 0
                if dino_probability is None or dino_mask is None:
                    dino_probability = np.zeros_like(target, dtype=np.float32)
                    dino_mask = np.zeros_like(target, dtype=bool)
                else:
                    dino_probability = dino_probability.astype(np.float32)
                    dino_mask = dino_mask > 127
                fusions = make_fusions(sam_probability, dino_probability, sam_mask, dino_mask)
                agreement = float(np.logical_and(sam_mask, dino_mask).sum() / max(np.logical_or(sam_mask, dino_mask).sum(), 1))
                dino_area = float(dino_mask.mean())
                for variant, mask in fusions.items():
                    metrics = binary_metrics(mask, target)
                    records.append(
                        {
                            "case_id": case_id,
                            "variant": variant,
                            "dice": metrics["dice"],
                            "iou": metrics["iou"],
                            "boundary_f1": metrics["boundary_f1"],
                            "sam_area": float(sam_mask.mean()),
                            "dino_area": dino_area,
                            "sam_dino_agreement_iou": agreement,
                            "dino_available": bool(dino_result.get("mask_available", False)),
                        }
                    )

    with (output_dir / "per_case.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = list(records[0].keys()) if records else ["case_id", "variant"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    summary: dict[str, Any] = {"patient_count": len(rows), "variants": {}}
    for variant in sorted({record["variant"] for record in records}):
        values = [record for record in records if record["variant"] == variant]
        summary["variants"][variant] = {
            "n": len(values),
            "mean_dice": float(np.mean([value["dice"] for value in values])),
            "mean_iou": float(np.mean([value["iou"] for value in values])),
            "mean_boundary_f1": float(np.mean([value["boundary_f1"] for value in values])),
        }
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
