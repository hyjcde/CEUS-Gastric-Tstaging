"""ROI-masked patch tokens from frozen MedSigLIP. Reuses the 20% global cache."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor

from .constants import CACHE_DIR, DATASET_DIR, EMBED_DIM, SPATIAL_CACHE_DIR, SPLIT_FILES, WEIGHT_DIR
from .encode import _abs_path, _load_mask, assert_weights


GRID = 32


def _mask_grid(mask_path: Path, image_size: tuple[int, int]) -> np.ndarray:
    # Stretch to 448 then 32, same geometry as the official processor.
    mask = _load_mask(mask_path, image_size)
    canvas = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
    at_input = canvas.resize((448, 448), Image.NEAREST)
    grid = np.array(at_input.resize((GRID, GRID), Image.NEAREST)) > 0
    return grid.reshape(-1)


def _patch_tokens(vision, pixel: torch.Tensor) -> torch.Tensor:
    hidden = vision(pixel_values=pixel).last_hidden_state
    if hidden.shape[1] == GRID * GRID + 1:
        hidden = hidden[:, 1:]
    elif hidden.shape[1] != GRID * GRID:
        raise RuntimeError(f"unexpected patch count {hidden.shape}")
    return torch.nn.functional.normalize(hidden, p=2, dim=-1)


def _masked_mean(patches: torch.Tensor, keep: torch.Tensor) -> torch.Tensor:
    fill = patches.masked_fill(~keep.unsqueeze(-1), 0.0)
    denom = keep.sum(dim=1).clamp(min=1).unsqueeze(-1)
    mean = fill.sum(dim=1) / denom
    empty = keep.any(dim=1).unsqueeze(-1)
    fallback = patches.mean(dim=1)
    return torch.where(empty, mean, fallback)


def encode_spatial(
    device: str = "cuda:0",
    batch_size: int = 8,
    dest: Path | None = None,
    limit: int | None = None,
) -> dict[str, object]:
    assert_weights()
    dest = dest or SPATIAL_CACHE_DIR
    dest.mkdir(parents=True, exist_ok=True)
    model = AutoModel.from_pretrained(str(WEIGHT_DIR), local_files_only=True).to(device).eval()
    processor = AutoProcessor.from_pretrained(str(WEIGHT_DIR), local_files_only=True)
    vision = model.vision_model
    summary: dict[str, object] = {"dest": str(dest), "grid": GRID}
    for split, rel in SPLIT_FILES.items():
        src = CACHE_DIR / f"{split}_embeddings.npz"
        if not src.is_file():
            raise FileNotFoundError(src)
        resolved = CACHE_DIR / f"{split}_resolved.csv"
        if not resolved.is_file():
            resolved = DATASET_DIR / rel
        table = pd.read_csv(resolved)
        mask_by_crop = {str(row["crop_ui_path"]): str(row.get("mask_path", "")) for _, row in table.iterrows()}
        with np.load(src, allow_pickle=True) as data:
            paths = np.asarray(data["crop_ui_path"]).astype(str)
            e_full = np.asarray(data["e_full"])
            e_roi = np.asarray(data["e_roi"])
            payload = {key: data[key] for key in data.files}
        lesion = np.zeros((len(paths), EMBED_DIM), dtype=np.float32)
        context = np.zeros((len(paths), EMBED_DIM), dtype=np.float32)
        images: list = []
        grids: list[np.ndarray] = []
        idxs: list[int] = []

        def flush() -> None:
            if not images:
                return
            pixel = processor(images=images, return_tensors="pt")["pixel_values"].to(device)
            with torch.no_grad():
                patches = _patch_tokens(vision, pixel)
                keep = torch.from_numpy(np.stack(grids, axis=0)).to(device)
                les = _masked_mean(patches, keep)
                ctx = _masked_mean(patches, ~keep)
            start = idxs[0]
            lesion[idxs] = les.float().cpu().numpy()
            context[idxs] = ctx.float().cpu().numpy()
            images.clear()
            grids.clear()
            idxs.clear()
            if start and start % 256 == 0:
                print(f"  spatial {split} {start}/{len(paths)}", flush=True)

        n_use = len(paths) if limit is None else min(int(limit), len(paths))
        for i, crop in enumerate(paths[:n_use]):
            mask_path = mask_by_crop.get(crop, "")
            image_path = _abs_path(crop)
            try:
                image = Image.open(image_path).convert("RGB")
                grid = _mask_grid(_abs_path(mask_path), image.size) if mask_path else np.zeros(GRID * GRID, dtype=bool)
            except Exception:
                grid = np.zeros(GRID * GRID, dtype=bool)
                image = Image.new("RGB", (448, 448))
            images.append(image)
            grids.append(grid)
            idxs.append(i)
            if len(images) >= batch_size:
                flush()
        flush()
        out = dest / f"{split}_embeddings.npz"
        payload["e_full"] = np.concatenate([e_full, lesion], axis=1).astype(np.float32)
        payload["e_roi"] = np.concatenate([e_roi, context], axis=1).astype(np.float32)
        payload["e_lesion"] = lesion
        payload["e_context"] = context
        payload["spatial"] = np.asarray([1], dtype=np.int64)
        np.savez_compressed(out, **payload)
        summary[split] = {
            "encoded": int(n_use),
            "source_rows": int(len(paths)),
            "dim": int(payload["e_full"].shape[1]),
        }
        print(split, summary[split], flush=True)
    (dest / "encode_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
