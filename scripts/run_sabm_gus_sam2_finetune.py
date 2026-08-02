#!/usr/bin/env python3
"""Patient-level SABM-GUS fine-tuning on the current SAM2 mask-prompt path."""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data/processed/sms/baseline_2d_unet_holdout_crop_ui/dataset_manifest.json"
DEFAULT_SAM2_CHECKPOINT = Path.home() / (
    ".cache/huggingface/hub/models--facebook--sam2.1-hiera-tiny/"
    "snapshots/de431c4043854a71d8101e17995dfe596bf101a5/"
    "sam2.1_hiera_tiny.pt"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--sam2-checkpoint", type=Path, default=DEFAULT_SAM2_CHECKPOINT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--val-fraction", type=float, default=0.1)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--max-train-samples", type=int, default=None)
    parser.add_argument("--max-holdout-samples", type=int, default=20)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--image-size", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=20260802)
    parser.add_argument("--device", default="cuda:0")
    return parser.parse_args()


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else (ROOT / path).resolve()


def patient_key(row: dict[str, Any]) -> str:
    value = str(row.get("sample_id", row.get("case_id", "")))
    return re.sub(r"-\d+$", "", value)


def load_rows(manifest: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    train = [row for row in payload["cases"] if row.get("target_split") == "training"]
    holdout = [row for row in payload["cases"] if row.get("target_split") == "test"]
    train = [row for row in train if Path(row["prepared_image"]).is_file() and Path(row["prepared_label"]).is_file()]
    holdout = [row for row in holdout if Path(row["prepared_image"]).is_file() and Path(row["prepared_label"]).is_file()]
    return train, holdout


def patient_split(rows: list[dict[str, Any]], val_fraction: float, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    patients = sorted({patient_key(row) for row in rows})
    rng = np.random.default_rng(seed)
    rng.shuffle(patients)
    val_patients = set(patients[: max(1, int(len(patients) * val_fraction))])
    train = [row for row in rows if patient_key(row) not in val_patients]
    val = [row for row in rows if patient_key(row) in val_patients]
    return train, val


def corrupt_mask(mask: np.ndarray, rng: random.Random) -> np.ndarray:
    binary = (mask > 0).astype(np.uint8)
    if binary.sum() == 0:
        return binary.astype(np.float32)
    mode = rng.choice(("erode", "dilate", "shift", "partial", "identity"))
    if mode == "identity":
        return binary.astype(np.float32)
    if mode in {"erode", "dilate"}:
        size = rng.choice((5, 7, 9, 11, 15))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
        binary = cv2.erode(binary, kernel) if mode == "erode" else cv2.dilate(binary, kernel)
    elif mode == "shift":
        dx, dy = rng.randint(-35, 35), rng.randint(-35, 35)
        matrix = np.float32([[1, 0, dx], [0, 1, dy]])
        binary = cv2.warpAffine(binary, matrix, (binary.shape[1], binary.shape[0]))
    else:
        ys, xs = np.where(binary > 0)
        angle = rng.uniform(0, 2 * np.pi)
        cx, cy = float(xs.mean()), float(ys.mean())
        side = ((np.indices(binary.shape)[1] - cx) * np.cos(angle) +
                (np.indices(binary.shape)[0] - cy) * np.sin(angle)) > 0
        binary = binary * side.astype(np.uint8)
    return binary.astype(np.float32)


def mask_to_box(mask: np.ndarray, jitter: bool, rng: random.Random, size: int) -> np.ndarray:
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return np.array([0, 0, size - 1, size - 1], dtype=np.float32)
    x1, y1, x2, y2 = map(float, (xs.min(), ys.min(), xs.max(), ys.max()))
    if jitter:
        dx, dy = max(x2 - x1, 1.0) * 0.1, max(y2 - y1, 1.0) * 0.1
        x1 -= rng.uniform(0, dx)
        y1 -= rng.uniform(0, dy)
        x2 += rng.uniform(0, dx)
        y2 += rng.uniform(0, dy)
    return np.array([max(0, x1), max(0, y1), min(size - 1, x2), min(size - 1, y2)], dtype=np.float32)


class PromptDataset(Dataset):
    def __init__(self, rows: list[dict[str, Any]], image_size: int, train: bool, seed: int) -> None:
        self.rows = rows
        self.image_size = image_size
        self.train = train
        self.seed = seed
        self.mean = torch.tensor([123.675, 116.28, 103.53]).view(3, 1, 1)
        self.std = torch.tensor([58.395, 57.12, 57.375]).view(3, 1, 1)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, Any]:
        row = self.rows[index]
        image = cv2.imread(row["prepared_image"], cv2.IMREAD_COLOR)
        target_native = cv2.imread(row["prepared_label"], cv2.IMREAD_GRAYSCALE)
        if image is None or target_native is None:
            raise RuntimeError(f"Unreadable sample: {row['case_id']}")
        original_height, original_width = target_native.shape[:2]
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image = cv2.resize(image, (self.image_size, self.image_size), interpolation=cv2.INTER_LINEAR)
        target = cv2.resize(target_native, (self.image_size, self.image_size), interpolation=cv2.INTER_NEAREST)
        rng = random.Random(self.seed + index * 1009)
        if self.train and rng.random() < 0.5:
            image = np.ascontiguousarray(image[:, ::-1])
            target = np.ascontiguousarray(target[:, ::-1])
        if self.train and rng.random() < 0.5:
            image = np.ascontiguousarray(image[::-1, :])
            target = np.ascontiguousarray(target[::-1, :])
        target_binary = (target > 0).astype(np.float32)
        prompt_mask = corrupt_mask(target_binary, rng) if self.train else corrupt_mask(target_binary, random.Random(self.seed + index * 1009))
        image_tensor = torch.from_numpy(image).permute(2, 0, 1).float()
        image_tensor = (image_tensor - self.mean) / self.std
        target_tensor = torch.from_numpy(target_binary).float().unsqueeze(0)
        prompt_tensor = torch.from_numpy(cv2.resize(prompt_mask, (256, 256), interpolation=cv2.INTER_NEAREST)).float().unsqueeze(0)
        return {
            "image": image_tensor,
            "target": target_tensor,
            "prompt_mask": prompt_tensor,
            "box": torch.from_numpy(mask_to_box(target_binary, self.train, rng, self.image_size)),
            "case_id": row["case_id"],
            "label_path": row["prepared_label"],
            "original_height": original_height,
            "original_width": original_width,
        }


class SAM2PromptSegmenter(nn.Module):
    def __init__(self, checkpoint: Path) -> None:
        super().__init__()
        from sam2.build_sam import build_sam2

        self.sam2_model = build_sam2("configs/sam2.1/sam2.1_hiera_t.yaml", str(checkpoint))
        for parameter in self.sam2_model.image_encoder.parameters():
            parameter.requires_grad = False
        for parameter in self.sam2_model.sam_mask_decoder.parameters():
            parameter.requires_grad = True
        for parameter in self.sam2_model.sam_prompt_encoder.parameters():
            parameter.requires_grad = True

    def forward(self, images: torch.Tensor, boxes: torch.Tensor, mask_prompt: torch.Tensor | None) -> torch.Tensor:
        batch_size = images.shape[0]
        with torch.no_grad():
            backbone = self.sam2_model.forward_image(images)
            _, vision_feats, _, feat_sizes = self.sam2_model._prepare_backbone_features(backbone)
            if self.sam2_model.directly_add_no_mem_embed:
                vision_feats[-1] = vision_feats[-1] + self.sam2_model.no_mem_embed
            feats = [
                feat.permute(1, 2, 0).view(batch_size, -1, *feat_size)
                for feat, feat_size in zip(vision_feats, feat_sizes)
            ]
        sparse, dense = self.sam2_model.sam_prompt_encoder(points=None, boxes=boxes, masks=mask_prompt)
        high_res = feats[:-1] if self.sam2_model.use_high_res_features_in_sam else None
        low_res, _, _, _ = self.sam2_model.sam_mask_decoder(
            image_embeddings=feats[-1],
            image_pe=self.sam2_model.sam_prompt_encoder.get_dense_pe(),
            sparse_prompt_embeddings=sparse,
            dense_prompt_embeddings=dense,
            multimask_output=False,
            repeat_image=False,
            high_res_features=high_res,
        )
        return low_res


def boundary_map(probability: torch.Tensor) -> torch.Tensor:
    dilated = F.max_pool2d(probability, 3, 1, 1)
    eroded = -F.max_pool2d(-probability, 3, 1, 1)
    return dilated - eroded


def loss_fn(logits: torch.Tensor, target: torch.Tensor) -> tuple[torch.Tensor, dict[str, float]]:
    probability = torch.sigmoid(logits)
    bce = F.binary_cross_entropy_with_logits(logits, target)
    intersection = (probability * target).sum(dim=(1, 2, 3))
    dice = 1 - ((2 * intersection + 1e-6) / (probability.sum(dim=(1, 2, 3)) + target.sum(dim=(1, 2, 3)) + 1e-6)).mean()
    boundary = F.l1_loss(boundary_map(probability), boundary_map(target))
    total = bce + dice + 0.25 * boundary
    return total, {"total": float(total.detach()), "bce": float(bce.detach()), "dice_loss": float(dice.detach()), "boundary": float(boundary.detach())}


def binary_metrics(pred: np.ndarray, target: np.ndarray) -> dict[str, float]:
    pred = pred > 0
    target = target > 0
    inter = np.logical_and(pred, target).sum()
    union = np.logical_or(pred, target).sum()
    pred_edge = cv2.morphologyEx(pred.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    target_edge = cv2.morphologyEx(target.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    pred_hit = np.logical_and(pred_edge > 0, cv2.dilate(target_edge, np.ones((5, 5), np.uint8)) > 0).sum()
    target_hit = np.logical_and(target_edge > 0, cv2.dilate(pred_edge, np.ones((5, 5), np.uint8)) > 0).sum()
    precision = pred_hit / max((pred_edge > 0).sum(), 1)
    recall = target_hit / max((target_edge > 0).sum(), 1)
    return {
        "dice": float(2 * inter / max(pred.sum() + target.sum(), 1)),
        "iou": float(inter / max(union, 1)),
        "boundary_f1": float(2 * precision * recall / max(precision + recall, 1e-8)),
    }


def run_epoch(model: SAM2PromptSegmenter, loader: DataLoader, device: torch.device, optimizer: Any = None) -> dict[str, float]:
    training = optimizer is not None
    model.train(training)
    totals = {"loss": 0.0, "bce": 0.0, "dice_loss": 0.0, "boundary": 0.0, "dice": 0.0, "iou": 0.0}
    count = 0
    for batch in loader:
        images = batch["image"].to(device)
        target = F.interpolate(batch["target"].to(device), size=(256, 256), mode="nearest")
        boxes = batch["box"].to(device)
        prompt = batch["prompt_mask"].to(device)
        if training:
            optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=device.type == "cuda"):
            logits = model(images, boxes, prompt)
            total, parts = loss_fn(logits, target)
        if training:
            total.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
        probability = torch.sigmoid(logits)
        pred = probability > 0.5
        inter = (pred * target.bool()).sum()
        totals["loss"] += parts["total"]
        totals["bce"] += parts["bce"]
        totals["dice_loss"] += parts["dice_loss"]
        totals["boundary"] += parts["boundary"]
        totals["dice"] += float((2 * inter / (pred.sum() + target.sum()).clamp_min(1)).detach())
        totals["iou"] += float((inter / (pred | target.bool()).sum().clamp_min(1)).detach())
        count += 1
    return {key: value / max(count, 1) for key, value in totals.items()}


@torch.no_grad()
def evaluate_holdout(model: SAM2PromptSegmenter, rows: list[dict[str, Any]], args: argparse.Namespace, device: torch.device, output_dir: Path) -> dict[str, Any]:
    model.eval()
    dataset = PromptDataset(rows, args.image_size, train=False, seed=args.seed + 100)
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False, num_workers=max(0, args.num_workers // 2), pin_memory=True)
    per_case: list[dict[str, Any]] = []
    for batch in loader:
        images = batch["image"].to(device)
        boxes = batch["box"].to(device)
        prompt = batch["prompt_mask"].to(device)
        for mode, mask_input in (("box", None), ("box_plus_corrupted_mask", prompt)):
            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=device.type == "cuda"):
                logits = model(images, boxes, mask_input)
            prediction = (torch.sigmoid(logits).cpu().numpy()[:, 0] > 0.5).astype(np.uint8)
            for index, case_id in enumerate(batch["case_id"]):
                height = int(batch["original_height"][index])
                width = int(batch["original_width"][index])
                pred_native = cv2.resize(prediction[index], (width, height), interpolation=cv2.INTER_NEAREST)
                target_native = cv2.imread(batch["label_path"][index], cv2.IMREAD_GRAYSCALE) > 0
                metrics = binary_metrics(pred_native, target_native)
                per_case.append({"case_id": case_id, "mode": mode, **metrics})
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "holdout_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["case_id", "mode", "dice", "iou", "boundary_f1"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(per_case)
    summary = {"case_count": len(rows), "modes": {}}
    for mode in ("box", "box_plus_corrupted_mask"):
        values = [row for row in per_case if row["mode"] == mode]
        summary["modes"][mode] = {
            "n": len(values),
            "mean_dice": float(np.mean([row["dice"] for row in values])) if values else None,
            "mean_iou": float(np.mean([row["iou"] for row in values])) if values else None,
            "mean_boundary_f1": float(np.mean([row["boundary_f1"] for row in values])) if values else None,
        }
    (output_dir / "holdout_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    args = parse_args()
    manifest = resolve(args.manifest)
    checkpoint = resolve(args.sam2_checkpoint)
    output_dir = resolve(args.output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True)
    train_rows, holdout_rows = load_rows(manifest)
    train_rows, val_rows = patient_split(train_rows, args.val_fraction, args.seed)
    if args.max_train_samples:
        train_rows = train_rows[: args.max_train_samples]
        val_rows = val_rows[: max(1, args.max_train_samples // 8)]
    holdout_rows = holdout_rows[: args.max_holdout_samples]
    train_loader = DataLoader(
        PromptDataset(train_rows, args.image_size, train=True, seed=args.seed + 17),
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=True,
        drop_last=True,
    )
    val_loader = DataLoader(
        PromptDataset(val_rows, args.image_size, train=False, seed=args.seed + 31),
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=max(0, args.num_workers // 2),
        pin_memory=True,
    )
    device = torch.device(args.device if torch.cuda.is_available() else "cpu")
    model = SAM2PromptSegmenter(checkpoint).to(device)
    optimizer = torch.optim.AdamW([parameter for parameter in model.parameters() if parameter.requires_grad], lr=args.learning_rate, weight_decay=0.01)
    best_val = -1.0
    best_epoch = -1
    history: list[dict[str, Any]] = []
    best_path = output_dir / "best_sabm_gus_sam2.pt"
    for epoch in range(1, args.epochs + 1):
        train_metrics = run_epoch(model, train_loader, device, optimizer)
        with torch.no_grad():
            val_metrics = run_epoch(model, val_loader, device)
        row = {"epoch": epoch, "train": train_metrics, "val": val_metrics}
        history.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if val_metrics["dice"] > best_val:
            best_val = val_metrics["dice"]
            best_epoch = epoch
            torch.save({"model_state_dict": model.state_dict(), "epoch": epoch, "best_val_dice": best_val}, best_path)
    (output_dir / "train_history.json").write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    fresh = SAM2PromptSegmenter(checkpoint).to(device)
    state = torch.load(best_path, map_location="cpu")
    fresh.load_state_dict(state["model_state_dict"], strict=True)
    with torch.no_grad():
        fresh_val = run_epoch(fresh, val_loader, device)
    replay = {"best_epoch": best_epoch, "logged_val_dice": best_val, "fresh_val": fresh_val, "dice_gap": fresh_val["dice"] - best_val}
    (output_dir / "checkpoint_replay_check.json").write_text(json.dumps(replay, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = evaluate_holdout(fresh, holdout_rows, args, device, output_dir)
    run_manifest = {
        "method": "SABM-GUS-SAM2",
        "manifest": str(manifest),
        "checkpoint": str(best_path),
        "train_images": len(train_rows),
        "val_images": len(val_rows),
        "holdout_patients": len({patient_key(row) for row in holdout_rows}),
        "best_epoch": best_epoch,
        "best_val_dice": best_val,
        "fresh_replay": replay,
        "holdout_summary": summary,
        "status": "candidate" if abs(replay["dice_gap"]) <= 0.02 else "blocked",
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(run_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(run_manifest, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
