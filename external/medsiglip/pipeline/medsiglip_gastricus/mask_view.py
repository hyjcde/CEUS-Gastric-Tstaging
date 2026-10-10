"""Encode a lesion-overlay third view. Reuses 20% full/ROI tokens. New cache only."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor

from .constants import CACHE_DIR, DATASET_DIR, EMBED_DIM, MASKVIEW_CACHE_DIR, SPLIT_FILES, WEIGHT_DIR
from .encode import _abs_path, _load_mask, assert_weights, encode_images


def _overlay(crop: Path, mask_path: Path) -> Image.Image:
    full = Image.open(crop).convert("RGB")
    mask = _load_mask(mask_path, full.size)
    arr = np.asarray(full).astype(np.float32)
    highlight = np.array([255.0, 48.0, 48.0], dtype=np.float32)
    if mask.any():
        arr[mask] = arr[mask] * 0.35 + highlight * 0.65
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def encode_mask_view(
    device: str = "cuda:0",
    batch_size: int = 8,
    dest: Path | None = None,
) -> dict[str, object]:
    assert_weights()
    dest = dest or MASKVIEW_CACHE_DIR
    if dest.resolve() == CACHE_DIR.resolve():
        raise ValueError("refusing to overwrite the 20% cache")
    dest.mkdir(parents=True, exist_ok=True)
    model = AutoModel.from_pretrained(str(WEIGHT_DIR), local_files_only=True).to(device).eval()
    processor = AutoProcessor.from_pretrained(str(WEIGHT_DIR), local_files_only=True)
    summary: dict[str, object] = {
        "dest": str(dest),
        "src20": str(CACHE_DIR),
        "layout": "e_full=concat(full20, mask_overlay); e_roi=concat(roi20, mask_overlay); dim=2304",
    }
    for split, rel in SPLIT_FILES.items():
        src = CACHE_DIR / f"{split}_embeddings.npz"
        if not src.is_file():
            raise FileNotFoundError(src)
        resolved = CACHE_DIR / f"{split}_resolved.csv"
        csv = resolved if resolved.is_file() else DATASET_DIR / rel
        table = pd.read_csv(csv)
        mask_by_crop = {str(row["crop_ui_path"]): str(row.get("mask_path", "")) for _, row in table.iterrows()}
        with np.load(src, allow_pickle=True) as data:
            paths = np.asarray(data["crop_ui_path"]).astype(str)
            e_full = np.asarray(data["e_full"])
            e_roi = np.asarray(data["e_roi"])
            payload = {key: data[key] for key in data.files}
        n = len(paths)
        e_mask = np.zeros((n, EMBED_DIM), dtype=np.float32)
        batch: list[Image.Image] = []
        idxs: list[int] = []

        def flush() -> None:
            if not batch:
                return
            stacked = encode_images(model, processor, batch, device)
            for local, row_i in enumerate(idxs):
                e_mask[row_i] = stacked[local]
            batch.clear()
            idxs.clear()

        for i, crop in enumerate(paths):
            mask_path = mask_by_crop.get(crop, "")
            if not mask_path:
                continue
            try:
                batch.append(_overlay(_abs_path(crop), _abs_path(mask_path)))
                idxs.append(i)
            except (OSError, ValueError):
                continue
            if len(batch) >= batch_size:
                flush()
                if (i + 1) % 512 == 0:
                    print(f"  mask-view {split} {i + 1}/{n}", flush=True)
        flush()
        payload["e_full"] = np.concatenate([e_full, e_mask], axis=1).astype(np.float32)
        payload["e_roi"] = np.concatenate([e_roi, e_mask], axis=1).astype(np.float32)
        payload["e_mask"] = e_mask
        np.savez_compressed(dest / f"{split}_embeddings.npz", **payload)
        if resolved.is_file():
            (dest / f"{split}_resolved.csv").write_text(resolved.read_text(encoding="utf-8"), encoding="utf-8")
        summary[split] = {"rows": int(n), "dim": int(payload["e_full"].shape[1])}
        print(split, summary[split], flush=True)
    (dest / "encode_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    del model
    if device.startswith("cuda"):
        torch.cuda.empty_cache()
    return summary
