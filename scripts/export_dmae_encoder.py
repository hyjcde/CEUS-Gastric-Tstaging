#!/usr/bin/env python3
"""Export a Deblurring-MAE pretraining checkpoint to a timm ViT-B/16 encoder state_dict.

The MAE checkpoint (checkpoint-XXX.pth, key ``model``) holds encoder + decoder.
We keep the encoder part (patch_embed / cls_token / pos_embed / blocks / norm),
which is key-compatible with ``timm.create_model('vit_base_patch16_224')``,
verify with a strict load, and save the clean state_dict for downstream use.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ckpt", type=Path, required=True, help="MAE checkpoint-XXX.pth")
    parser.add_argument("--output", type=Path, required=True, help="output encoder .pth")
    args = parser.parse_args()

    import timm  # local import: only needed here

    raw = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    state = raw.get("model", raw)
    drop_prefixes = ("decoder", "mask_token", "head")
    encoder = {k: v for k, v in state.items() if not k.startswith(drop_prefixes)}

    model = timm.create_model(
        "vit_base_patch16_224", pretrained=False, num_classes=0, global_pool="", dynamic_img_size=True
    )
    result = model.load_state_dict(encoder, strict=True)
    print(f"[export] strict load OK: missing={list(result.missing_keys)} unexpected={list(result.unexpected_keys)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), args.output)
    meta = {
        "source_ckpt": str(args.ckpt),
        "epoch": raw.get("epoch") if isinstance(raw, dict) else None,
        "tensors": len(encoder),
        "format": "timm vit_base_patch16_224 encoder state_dict (num_classes=0, global_pool='')",
    }
    args.output.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"[export] saved {len(encoder)} tensors -> {args.output}")


if __name__ == "__main__":
    main()
