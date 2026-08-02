#!/usr/bin/env python3
"""Fine-tune and replay-check the SABM-GUS EfficientSAM3 candidate.

This entry point deliberately uses the current GastricTstaging manifest,
patient-level train/validation splitting, boundary-aware loss, and prompt
consistency. A checkpoint is only considered usable after a fresh model
reload produces a comparable validation score.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
import torch.nn.functional as F

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "scripts") not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT / "scripts"))

from efficientsam3_runtime import (  # noqa: E402
    EfficientSAM3Segmenter,
    PromptBuilder,
    autocast_context,
    compute_binary_metrics,
    create_promptable_loader,
    load_promptable_records,
    load_yaml,
    resolve_project_path,
    run_prompt_mode_evaluation,
    save_json,
    set_seed,
    split_train_val,
    write_yaml,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune SABM-GUS EfficientSAM3 candidate.")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--max-train-samples", type=int, default=None)
    parser.add_argument("--max-eval-samples", type=int, default=20)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--boundary-weight", type=float, default=0.25)
    parser.add_argument("--consistency-weight", type=float, default=0.05)
    parser.add_argument("--learning-rate", type=float, default=None)
    return parser.parse_args()


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def device_from_name(name: str) -> torch.device:
    if name.startswith("cuda") and torch.cuda.is_available():
        return torch.device(name)
    return torch.device("cpu")


def boundary_map(probability: torch.Tensor) -> torch.Tensor:
    dilated = F.max_pool2d(probability, kernel_size=3, stride=1, padding=1)
    eroded = -F.max_pool2d(-probability, kernel_size=3, stride=1, padding=1)
    return dilated - eroded


def dice_loss_from_logits(logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    probability = torch.sigmoid(logits)
    intersection = (probability * target).sum(dim=(1, 2, 3))
    denominator = probability.sum(dim=(1, 2, 3)) + target.sum(dim=(1, 2, 3))
    return (1.0 - (2.0 * intersection + 1e-6) / (denominator + 1e-6)).mean()


def loss_bundle(
    logits: torch.Tensor,
    target: torch.Tensor,
    *,
    bce_loss: nn.Module,
    boundary_weight: float,
    consistency_logits: torch.Tensor | None = None,
    consistency_weight: float = 0.0,
) -> tuple[torch.Tensor, dict[str, float]]:
    probability = torch.sigmoid(logits)
    segmentation = bce_loss(logits, target) + dice_loss_from_logits(logits, target)
    target_boundary = boundary_map(target)
    boundary = F.l1_loss(boundary_map(probability), target_boundary)
    consistency = (
        F.mse_loss(probability, torch.sigmoid(consistency_logits))
        if consistency_logits is not None and consistency_weight > 0
        else torch.zeros((), device=logits.device)
    )
    total = segmentation + boundary_weight * boundary + consistency_weight * consistency
    return total, {
        "segmentation": float(segmentation.detach().item()),
        "boundary": float(boundary.detach().item()),
        "consistency": float(consistency.detach().item()),
        "total": float(total.detach().item()),
    }


def forward_batch(
    model: EfficientSAM3Segmenter,
    batch: dict[str, Any],
    device: torch.device,
    *,
    amp: bool,
    bce_loss: nn.Module,
    boundary_weight: float,
    consistency_weight: float,
) -> tuple[torch.Tensor, dict[str, float], dict[str, float]]:
    images = batch["image"].to(device=device, dtype=torch.float32, non_blocking=True)
    masks = batch["mask"].to(device=device, dtype=torch.float32, non_blocking=True)
    with autocast_context(device, amp):
        output = model.forward_with_prompts(images, batch["prompt"])
        logits = F.interpolate(output["low_res_masks"], size=masks.shape[-2:], mode="bilinear", align_corners=False)
        alternative_logits = None
        if consistency_weight > 0 and any(prompt is not None for prompt in batch["alt_prompt"]):
            alt_output = model.forward_with_prompts(
                images,
                [
                    prompt if prompt is not None else batch["prompt"][index]
                    for index, prompt in enumerate(batch["alt_prompt"])
                ],
            )
            alternative_logits = F.interpolate(
                alt_output["low_res_masks"],
                size=masks.shape[-2:],
                mode="bilinear",
                align_corners=False,
            )
        total, parts = loss_bundle(
            logits,
            masks,
            bce_loss=bce_loss,
            boundary_weight=boundary_weight,
            consistency_logits=alternative_logits,
            consistency_weight=consistency_weight,
        )
    metrics = compute_binary_metrics(logits.detach(), masks, threshold=0.5)
    return total, parts, metrics


def run_epoch(
    model: EfficientSAM3Segmenter,
    loader,
    device: torch.device,
    *,
    optimizer: torch.optim.Optimizer | None,
    scaler: torch.amp.GradScaler,
    amp: bool,
    bce_loss: nn.Module,
    boundary_weight: float,
    consistency_weight: float,
) -> dict[str, float]:
    training = optimizer is not None
    model.train(training)
    totals = {"total": 0.0, "segmentation": 0.0, "boundary": 0.0, "consistency": 0.0, "dice": 0.0, "iou": 0.0}
    batches = 0
    for batch in loader:
        if training:
            optimizer.zero_grad(set_to_none=True)
        total, parts, metrics = forward_batch(
            model,
            batch,
            device,
            amp=amp,
            bce_loss=bce_loss,
            boundary_weight=boundary_weight,
            consistency_weight=consistency_weight if training else 0.0,
        )
        if training:
            scaler.scale(total).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            scaler.step(optimizer)
            scaler.update()
        totals["total"] += parts["total"]
        totals["segmentation"] += parts["segmentation"]
        totals["boundary"] += parts["boundary"]
        totals["consistency"] += parts["consistency"]
        totals["dice"] += metrics["dice"]
        totals["iou"] += metrics["iou"]
        batches += 1
    return {key: value / max(batches, 1) for key, value in totals.items()}


def load_fresh_model(config: dict[str, Any], checkpoint_path: Path, device: torch.device) -> EfficientSAM3Segmenter:
    replay_config = copy.deepcopy(config)
    # Keep the same converted EfficientSAM3 base checkpoint used during
    # training. Clearing it before loading the wrapper checkpoint can leave
    # non-trainable external weights initialized differently across processes.
    model = EfficientSAM3Segmenter(replay_config)
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    return model.to(device).eval()


def main() -> None:
    args = parse_args()
    config_path = resolve_path(args.config)
    config = load_yaml(config_path)
    output_dir = resolve_path(args.output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run_command.txt").write_text(" ".join(__import__("sys").argv) + "\n", encoding="utf-8")
    write_yaml(output_dir / "project_config_snapshot.yaml", config)

    seed = int(config.get("train", {}).get("seed", 666))
    set_seed(seed)
    random.seed(seed)
    torch.manual_seed(seed)
    device = device_from_name(args.device)
    train_cfg = config.get("train", {})
    eval_cfg = config.get("evaluation", {})
    paths_cfg = config.get("paths", {})
    dataset_root = resolve_project_path(paths_cfg.get("dataset_root"))
    if dataset_root is None:
        raise ValueError("dataset_root could not be resolved")
    manifest_path = dataset_root / "dataset_manifest.json"
    train_all, holdout, eval_sources = load_promptable_records(manifest_path)
    train_records, val_records, split_summary = split_train_val(
        train_all,
        float(train_cfg.get("val_fraction", 0.1)),
        seed,
    )
    if args.max_train_samples is not None:
        train_records = train_records[: args.max_train_samples]
        val_records = val_records[: max(1, args.max_train_samples // 8)]
    if args.max_eval_samples is not None:
        holdout = holdout[: args.max_eval_samples]
    resolution = int(train_cfg.get("image_size", 1008))
    batch_size = int(train_cfg.get("batch_size", 2))
    num_workers = int(train_cfg.get("num_workers", 4))
    prompt_cfg = config.get("prompt", {})
    prompt_builder = PromptBuilder(
        train_modes=list(prompt_cfg.get("train_modes", ["box", "single_positive_point", "positive_plus_negative_points", "box_plus_point"])),
        eval_modes=list(prompt_cfg.get("eval_modes", ["box", "single_positive_point", "box_plus_point"])),
        box_jitter=float(prompt_cfg.get("box_jitter", 0.1)),
        point_jitter=float(prompt_cfg.get("point_jitter", 0.03)),
        negative_band=float(prompt_cfg.get("negative_band", 0.15)),
        prompt_dropout_prob=0.0,
        use_prompt_dropout=False,
    )
    train_loader = create_promptable_loader(
        train_records,
        resolution=resolution,
        batch_size=batch_size,
        num_workers=num_workers,
        prompt_builder=prompt_builder,
        prompt_seed=seed + 17,
        train=True,
        consistency_enabled=args.consistency_weight > 0,
        brightness_jitter=float(train_cfg.get("augmentation", {}).get("brightness_jitter", 0.08)),
        contrast_jitter=float(train_cfg.get("augmentation", {}).get("contrast_jitter", 0.08)),
        hflip_prob=float(train_cfg.get("augmentation", {}).get("hflip_prob", 0.5)),
    )
    val_loader = create_promptable_loader(
        val_records,
        resolution=resolution,
        batch_size=batch_size,
        num_workers=max(0, num_workers // 2),
        prompt_builder=prompt_builder,
        prompt_seed=seed + 31,
        train=False,
        consistency_enabled=False,
    )
    model = EfficientSAM3Segmenter(config).to(device)
    learning_rate = args.learning_rate or float(train_cfg.get("lr", 1e-4))
    optimizer = torch.optim.AdamW(
        [parameter for parameter in model.parameters() if parameter.requires_grad],
        lr=learning_rate,
        weight_decay=float(train_cfg.get("weight_decay", 1e-4)),
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(args.epochs, 1))
    amp = bool(train_cfg.get("amp", True)) and device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=amp)
    bce_loss = nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([float(train_cfg.get("positive_class_weight", 2.0))], device=device).view(1, 1, 1)
    )
    history: list[dict[str, float]] = []
    best_val = -1.0
    best_epoch = -1
    best_path = output_dir / "checkpoints" / "best.pt"
    best_path.parent.mkdir(parents=True, exist_ok=True)
    for epoch in range(1, args.epochs + 1):
        train_metrics = run_epoch(
            model,
            train_loader,
            device,
            optimizer=optimizer,
            scaler=scaler,
            amp=amp,
            bce_loss=bce_loss,
            boundary_weight=args.boundary_weight,
            consistency_weight=args.consistency_weight,
        )
        with torch.no_grad():
            val_metrics = run_epoch(
                model,
                val_loader,
                device,
                optimizer=None,
                scaler=scaler,
                amp=amp,
                bce_loss=bce_loss,
                boundary_weight=args.boundary_weight,
                consistency_weight=0.0,
            )
        scheduler.step()
        row = {
            "epoch": float(epoch),
            "train_total": train_metrics["total"],
            "train_segmentation": train_metrics["segmentation"],
            "train_boundary": train_metrics["boundary"],
            "train_consistency": train_metrics["consistency"],
            "train_dice": train_metrics["dice"],
            "train_iou": train_metrics["iou"],
            "val_total": val_metrics["total"],
            "val_dice": val_metrics["dice"],
            "val_iou": val_metrics["iou"],
            "lr": float(optimizer.param_groups[0]["lr"]),
        }
        history.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if val_metrics["dice"] > best_val:
            best_val = val_metrics["dice"]
            best_epoch = epoch
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "epoch": epoch,
                    "best_val_dice": best_val,
                    "config": config,
                },
                best_path,
            )
    save_json(
        output_dir / "train_val_split.json",
        {
            "split_summary": split_summary,
            "train_images": len(train_records),
            "val_images": len(val_records),
            "train_patient_count": len({record.patient_id for record in train_records}),
            "val_patient_count": len({record.patient_id for record in val_records}),
            "train_case_ids": [record.case_id for record in train_records],
            "val_case_ids": [record.case_id for record in val_records],
        },
    )
    (output_dir / "train_metrics.json").write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    fresh_model = load_fresh_model(config, best_path, device)
    with torch.no_grad():
        fresh_val = run_epoch(
            fresh_model,
            val_loader,
            device,
            optimizer=None,
            scaler=scaler,
            amp=amp,
            bce_loss=bce_loss,
            boundary_weight=args.boundary_weight,
            consistency_weight=0.0,
        )
    replay_gap = fresh_val["dice"] - best_val
    replay_status = "pass" if abs(replay_gap) <= 0.02 else "blocked"
    save_json(
        output_dir / "checkpoint_replay_check.json",
        {
            "best_epoch": best_epoch,
            "logged_best_val_dice": best_val,
            "fresh_val_dice": fresh_val["dice"],
            "fresh_val_iou": fresh_val["iou"],
            "val_dice_gap": replay_gap,
            "status": replay_status,
        },
    )
    print(json.dumps({"checkpoint_replay": replay_status, "gap": replay_gap}, ensure_ascii=False), flush=True)

    evaluation_rows: list[dict[str, Any]] = []
    (output_dir / "evaluation").mkdir(parents=True, exist_ok=True)
    for mode in list(eval_cfg.get("prompt_modes", prompt_builder.eval_modes)):
        evaluation_rows.append(
            run_prompt_mode_evaluation(
                fresh_model,
                holdout,
                resolution=resolution,
                batch_size=int(eval_cfg.get("batch_size", batch_size)),
                num_workers=max(0, num_workers // 2),
                device=device,
                threshold=float(eval_cfg.get("threshold", 0.5)),
                experiment_dir=output_dir,
                split_name="internal_holdout",
                prompt_mode=str(mode),
                prompt_builder=prompt_builder,
                prompt_seed=seed + 101,
                representative_examples_per_bucket=1,
                )
        )
    save_json(output_dir / "evaluation" / "overall_summary.json", evaluation_rows)
    save_json(
        output_dir / "run_manifest.json",
        {
            "method": "SABM-GUS",
            "base_model": "EfficientSAM3",
            "config": str(config_path),
            "dataset_manifest": str(manifest_path),
            "output_dir": str(output_dir),
            "epochs": args.epochs,
            "best_epoch": best_epoch,
            "best_val_dice": best_val,
            "boundary_weight": args.boundary_weight,
            "consistency_weight": args.consistency_weight,
            "replay_status": replay_status,
            "evaluation_rows": evaluation_rows,
        },
    )
    print(json.dumps({"output_dir": str(output_dir), "replay_status": replay_status, "evaluation_rows": evaluation_rows}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
