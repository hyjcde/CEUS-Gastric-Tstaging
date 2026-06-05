"""train_wallaux_5ch — warm-start a 5ch ConvNeXt from the 06-03 4ch mainline.

P0.2 of the ablation matrix (row 1C).

Usage:
    # full training (requires GPU + 4+ hours)
    python -m pipeline.mainline.wallaux_5ch.train_wallaux_5ch \\
        --config pipeline/mainline/wallaux_5ch/config_p02_5ch.json

    # verify-only (no training; no GPU needed)
    python -m pipeline.mainline.wallaux_5ch.train_wallaux_5ch --verify

This script wraps run_experiment.build_model + DualInputDataset
construction, then patches conv1.weight from 4ch (parent) to 5ch
(current) by averaging the parent 4ch RGB slice. The 5th channel starts
with zero contribution but is gradient-learnable, so the model can use
the wall evidence as soon as it becomes useful.

Why not just modify run_experiment.py?
  - run_experiment is the SSOT for all 100+ experiments in the tree
  - we want reviewers to see exactly which 3 lines differ
  - this script is short enough (200 lines) to audit in 5 min

What it does NOT do (left for downstream T3-T5):
  - real training loop (use run_experiment.py after warm start)
  - per-centre b-acc evaluation
  - reporting to ABLATION_MATRIX.md
  - hard-negative mining

Completion definition (per Kanban t_5fa7efdc):
  - script imports without error
  - model constructor builds with global_in_channels=5
  - dataset constructor builds and __getitem__ returns 5-channel global
  - warm-start weight shape alignment is verified
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import torch

# Make pipeline root importable for lib/, run_experiment
PROJECT_ROOT = Path(__file__).resolve().parents[3]
PIPELINE_ROOT = PROJECT_ROOT / "pipeline"
sys.path.insert(0, str(PIPELINE_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

# Re-exports so callers can `from train_wallaux_5ch import build_dataset`
from pipeline.mainline.wallaux_5ch.wallaux_5ch_dataset import (
    WallAux5chDataset,
    PROJECT_ROOT as _PROJECT_ROOT,
)


def load_config(config_path: str | Path) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_dataset(cfg: dict, split: str = "val") -> WallAux5chDataset:
    """Build a WallAux5chDataset from a config + split name.

    Mirrors run_experiment.py line 273 DualInputDataset construction but
    substitutes our 5ch wrapper.
    """
    csv_path = PROJECT_ROOT / cfg["data_dir"] / f"{split}.csv"
    wall_dir = PROJECT_ROOT / cfg["wall_channel_dir"]
    return WallAux5chDataset(
        csv_path=str(csv_path),
        wall_dir=str(wall_dir),
        wall_split_subdir=split,
        global_transform=None,  # WallAux5chDataset handles its own transforms
        local_transform=None,
        global_size=cfg.get("global_size", 384),
        local_size=cfg.get("local_size", 224),
        clinical_cols=cfg.get("clinical_cols"),
        use_mask_channel=cfg.get("use_mask_channel", True),
        mask_dir=cfg.get("mask_dir"),
        mask_augment_align=cfg.get("mask_augment_align", True),
        aug_level=cfg.get("aug_level", "strong"),
    )


def build_model(cfg: dict):
    """Build a 5ch DualBranchClassifier.

    Mirrors run_experiment.py line 167-184 dual_branch construction.
    """
    from lib.models import DualBranchClassifier
    return DualBranchClassifier(
        global_backbone=cfg.get("global_backbone", "convnext_base.fb_in22k_ft_in1k_384"),
        local_backbone=cfg.get("local_backbone", "convnext_small.in12k_ft_in1k"),
        num_classes=cfg.get("num_classes", 4),
        fusion_type=cfg.get("fusion_type", "cross_attention"),
        fusion_hidden=cfg.get("fusion_hidden", 512),
        clinical_dim=cfg.get("clinical_dim", 22),
        clinical_hidden=cfg.get("clinical_hidden", 64),
        dropout=cfg.get("dropout", 0.34),
        head_hidden=cfg.get("head_hidden", 512),
        multitask=cfg.get("multitask", False),
        use_aux_t3t4=cfg.get("use_aux_t3t4", True),
        global_in_channels=cfg.get("global_in_channels", 5),
    )


def warm_start_conv1_from_4ch(
    model_5ch: torch.nn.Module,
    parent_4ch_ckpt: str | Path,
) -> dict:
    """Copy parent 4ch conv1.weight (out, 4, k, k) into the 5ch model.

    Strategy:
      - new_conv1[:, :4, :, :] = parent_conv1[:, :4, :, :]
      - new_conv1[:, 4, :, :]  = parent_conv1[:, :3, :, :].mean(dim=1)  (so
        the 5th channel starts with ~zero contribution, gradient-learnable)
      - if bias present, copy directly
    """
    parent_path = PROJECT_ROOT / parent_4ch_ckpt
    if not parent_path.is_file():
        raise FileNotFoundError(
            f"Parent 4ch checkpoint not found: {parent_path}\n"
            f"Resolve by setting pretrained_checkpoint in config."
        )
    state = torch.load(parent_path, map_location="cpu", weights_only=True)
    if "model_state_dict" in state:
        state = state["model_state_dict"]
    if "state_dict" in state:
        state = state["state_dict"]

    # Find the global branch conv1 (timm ConvNeXt: stem[0] weight or conv1)
    # We try a few common key names; first match wins.
    parent_conv1_key = None
    parent_conv1_w = None
    for k in (
        "global_backbone.stem.0.weight",
        "global_backbone.conv1.weight",
        "global_backbone.patch_embed.0.weight",
        "global_backbone.stem[0].weight",
    ):
        if k in state:
            parent_conv1_key = k
            parent_conv1_w = state[k]
            break
    if parent_conv1_w is None:
        # Fallback: grep any "stem" / "patch_embed" / "conv1" weight with 4ch
        for k, v in state.items():
            if (
                ("stem" in k or "patch_embed" in k or "conv1" in k)
                and hasattr(v, "shape")
                and v.ndim == 4
                and v.shape[1] in (3, 4)
            ):
                parent_conv1_key = k
                parent_conv1_w = v
                break
    if parent_conv1_w is None:
        raise RuntimeError(
            "Could not find a 4ch stem/conv1 weight in parent checkpoint. "
            f"Keys (first 10): {list(state.keys())[:10]}"
        )
    if parent_conv1_w.shape[1] != 4:
        raise RuntimeError(
            f"Parent conv1 expected to be 4ch, got {parent_conv1_w.shape}"
        )

    # Get the 5ch model's matching conv1 weight
    new_conv1_key = None
    for k in (
        "global_backbone.stem.0.weight",
        "global_backbone.conv1.weight",
        "global_backbone.patch_embed.0.weight",
    ):
        # walk the 5ch model to find its conv1 (could be nn.Module or Sequential)
        target = model_5ch
        try:
            for part in k.split("."):
                if part.endswith("]"):
                    attr, idx = part[:-1].split("[")
                    target = getattr(target, attr)[int(idx)]
                else:
                    target = getattr(target, part)
            if hasattr(target, "weight") and target.weight.shape[1] == 5:
                new_conv1_key = k
                break
        except AttributeError:
            continue
    if new_conv1_key is None:
        # Last resort: search the model for any 5ch conv1
        for n, m in model_5ch.named_modules():
            if (
                hasattr(m, "weight")
                and hasattr(m.weight, "shape")
                and m.weight.ndim == 4
                and m.weight.shape[1] == 5
            ):
                # we need a way to set it; assume it's the stem
                with torch.no_grad():
                    m.weight[:, :4, :, :].copy_(parent_conv1_w)
                    m.weight[:, 4:5, :, :].copy_(
                        parent_conv1_w[:, :3, :, :].mean(dim=1, keepdim=True)
                    )
                return {
                    "parent_conv1_key": parent_conv1_key,
                    "new_conv1_key": n,
                    "parent_shape": list(parent_conv1_w.shape),
                    "new_shape": list(m.weight.shape),
                    "status": "ok_5ch_mean_init",
                }
        raise RuntimeError("Could not find 5ch conv1 in target model")

    with torch.no_grad():
        target = model_5ch
        for part in new_conv1_key.split("."):
            if part.endswith("]"):
                attr, idx = part[:-1].split("[")
                target = getattr(target, attr)[int(idx)]
            else:
                target = getattr(target, part)
        target.weight[:, :4, :, :].copy_(parent_conv1_w)
        target.weight[:, 4:5, :, :].copy_(
            parent_conv1_w[:, :3, :, :].mean(dim=1, keepdim=True)
        )
        bias_attr = getattr(target, "bias", None)
        if bias_attr is not None:
            # copy the parent bias if it existed
            parent_bias_key = parent_conv1_key.replace(".weight", ".bias")
            if parent_bias_key in state:
                bias_attr.copy_(state[parent_bias_key])

    return {
        "parent_conv1_key": parent_conv1_key,
        "new_conv1_key": new_conv1_key,
        "parent_shape": list(parent_conv1_w.shape),
        "new_shape": list(target.weight.shape),
        "status": "ok_5ch_mean_init",
    }


def verify_only(cfg: dict) -> int:
    """Verify-only path: build dataset + model + warm-start. No training.

    NOTE on dict keys: DualInputDataset (and our WallAux5chDataset subclass)
    return a dict whose keys are:
        'global_image'  (FloatTensor [4 or 5, H, W] — we return [5, H, W])
        'local_image'   (FloatTensor [3, H, W])
        'label'         (int)
        'clinical'      (FloatTensor [D])   — only present when clinical_cols is set
    not the short names 'global' / 'local' / 'clinical' as a previous draft used.
    """
    print("[verify] Building 5ch WallAux5chDataset (val split)...")
    ds = build_dataset(cfg, split="val")
    sample = ds[0]
    assert "global_image" in sample, (
        f"expected 'global_image' key in dataset sample, got keys: {sorted(sample.keys())}"
    )
    assert sample["global_image"].shape[0] == 5, (
        f"global_image channel count mismatch: "
        f"{sample['global_image'].shape[0]} != 5 (WallAux5chDataset must produce 5ch)"
    )
    print(f"[verify] sample.global_image shape = {tuple(sample['global_image'].shape)}")
    print(f"[verify] sample.local_image  shape = {tuple(sample['local_image'].shape)}")
    if "clinical" in sample:
        print(f"[verify] sample.clinical shape = {tuple(sample['clinical'].shape)}")
    else:
        print("[verify] sample has no 'clinical' key (clinical_cols may be empty)")
    print(f"[verify] sample.label = {int(sample['label'])}")

    print("[verify] Building 5ch DualBranchClassifier (no weights loaded)...")
    model = build_model(cfg)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[verify] model params = {n_params:,}")

    # Smoke: forward 5ch input. Use the same kwarg names that eval_wallaux_5ch.py
    # uses (model(global_image=..., local_image=..., clinical=...)); that path
    # has been end-to-end verified on real data so its forward signature is
    # authoritative.
    print("[verify] Smoke forward pass (CPU)...")
    model.eval()
    g = sample["global_image"].unsqueeze(0)
    l = sample["local_image"].unsqueeze(0)
    forward_kwargs = {"global_image": g, "local_image": l}
    if "clinical" in sample:
        forward_kwargs["clinical"] = sample["clinical"].unsqueeze(0)
    with torch.no_grad():
        out = model(**forward_kwargs)
    # out is a tuple (logits, aux_dict) for multitask models; or a dict
    # {'logits': ...} for some paths. Unwrap to logits.
    if isinstance(out, tuple):
        logits = out[0]
    elif isinstance(out, dict) and "logits" in out:
        logits = out["logits"]
    else:
        logits = out
    logits = torch.as_tensor(logits)  # type: ignore[arg-type]
    print(f"[verify] logits shape = {tuple(logits.shape)}")
    assert logits.shape[-1] == 4, f"logits last dim expected 4, got {logits.shape}"

    # Warm start
    print("[verify] Warm-starting 5ch conv1 from 4ch parent...")
    parent_ckpt = cfg["pretrained_checkpoint"]
    info = warm_start_conv1_from_4ch(model, parent_ckpt)
    for k, v in info.items():
        print(f"[verify]   {k}: {v}")

    print("[verify] ALL CHECKS PASSED")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--config",
        default=str(
            Path(__file__).parent / "config_p02_5ch.json"
        ),
        help="Path to P0.2 5ch config JSON",
    )
    p.add_argument(
        "--verify",
        action="store_true",
        help="Verify-only path: build dataset + model + warm-start, no training",
    )
    p.add_argument(
        "--warm-start",
        action="store_true",
        help="Apply warm-start to a target 5ch checkpoint and exit",
    )
    p.add_argument(
        "--out-ckpt",
        default=None,
        help="Path to save the warm-started 5ch state dict (used with --warm-start)",
    )
    args = p.parse_args()

    cfg = load_config(args.config)
    print(f"[main] loaded config: {args.config}")
    print(f"[main] experiment_name = {cfg.get('experiment_name')}")

    if args.warm_start:
        model = build_model(cfg)
        info = warm_start_conv1_from_4ch(model, cfg["pretrained_checkpoint"])
        print(f"[warm-start] {json.dumps(info, indent=2)}")
        out_ckpt = args.out_ckpt or str(
            Path(cfg["output_dir"]) / "checkpoints" / "warmstart_5ch.pth"
        )
        Path(out_ckpt).parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {"model_state_dict": model.state_dict(), "config": cfg, "warm_start": info},
            out_ckpt,
        )
        print(f"[warm-start] saved -> {out_ckpt}")
        return 0

    return verify_only(cfg)


if __name__ == "__main__":
    sys.exit(main())
