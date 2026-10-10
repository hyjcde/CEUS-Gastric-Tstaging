"""Last-N encoder layer patch means, concatenated to the frozen 1152-d global pool.

Does not overwrite the 20% cache or the spatial (lesion/context) cache.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from transformers import AutoModel, AutoProcessor

from .constants import CACHE_DIR, DATASET_DIR, EMBED_DIM, LAYERS_CACHE_DIR, ROI_EXPAND, SPLIT_FILES, WEIGHT_DIR
from .encode import _abs_path, assert_weights, load_pair


GRID = 32
N_LAYER_TOKENS = 4


def _layer_means(vision, pixel: torch.Tensor, n_layers: int = N_LAYER_TOKENS) -> torch.Tensor:
    # Current SigLIP VisionTransformer does not return hidden_states. Hook the last N layers.
    captured: list[torch.Tensor] = []

    def _hook(_module, _inp, output):
        hidden = output[0] if isinstance(output, (tuple, list)) else output
        captured.append(hidden)
        return output

    layers = vision.encoder.layers
    start = max(0, len(layers) - int(n_layers))
    handles = [layers[i].register_forward_hook(_hook) for i in range(start, len(layers))]
    try:
        vision(pixel_values=pixel)
    finally:
        for handle in handles:
            handle.remove()
    if len(captured) != int(n_layers):
        raise RuntimeError(f"captured {len(captured)} layer states, expected {n_layers}")
    if hasattr(vision, "post_layernorm"):
        captured[-1] = vision.post_layernorm(captured[-1])
    pooled = []
    for hidden in captured:
        tokens = hidden
        if tokens.shape[1] == GRID * GRID + 1:
            tokens = tokens[:, 1:]
        elif tokens.shape[1] != GRID * GRID:
            raise RuntimeError(f"unexpected patch count {tokens.shape}")
        pooled.append(torch.nn.functional.normalize(tokens.mean(dim=1), p=2, dim=-1))
    return torch.cat(pooled, dim=-1)


def encode_layers(
    device: str = "cuda:0",
    batch_size: int = 8,
    dest: Path | None = None,
    expand: float = ROI_EXPAND,
    n_layers: int = N_LAYER_TOKENS,
    limit: int | None = None,
) -> dict[str, object]:
    assert_weights()
    dest = dest or LAYERS_CACHE_DIR
    if dest.resolve() in {CACHE_DIR.resolve()}:
        raise ValueError("refusing to overwrite the 20% global cache")
    dest.mkdir(parents=True, exist_ok=True)
    model = AutoModel.from_pretrained(str(WEIGHT_DIR), local_files_only=True).to(device).eval()
    processor = AutoProcessor.from_pretrained(str(WEIGHT_DIR), local_files_only=True)
    vision = model.vision_model
    layer_dim = EMBED_DIM * int(n_layers)
    summary: dict[str, object] = {
        "dest": str(dest),
        "n_layers": int(n_layers),
        "layer_dim": int(layer_dim),
        "embed_dim": int(EMBED_DIM + layer_dim),
        "expand": float(expand),
    }
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
        n_use = len(paths) if limit is None else min(int(limit), len(paths))
        full_layers = np.zeros((n_use, layer_dim), dtype=np.float32)
        roi_layers = np.zeros((n_use, layer_dim), dtype=np.float32)
        images_full: list = []
        images_roi: list = []
        idxs: list[int] = []

        def flush() -> None:
            if not images_full:
                return
            pixel = processor(images=images_full + images_roi, return_tensors="pt")["pixel_values"].to(device)
            with torch.no_grad():
                stacked = _layer_means(vision, pixel, n_layers=n_layers)
            n = len(images_full)
            start = idxs[0]
            full_layers[idxs] = stacked[:n].float().cpu().numpy()
            roi_layers[idxs] = stacked[n:].float().cpu().numpy()
            images_full.clear()
            images_roi.clear()
            idxs.clear()
            if start and start % 256 == 0:
                print(f"  layers {split} {start}/{n_use}", flush=True)

        for i, crop in enumerate(paths[:n_use]):
            mask_path = mask_by_crop.get(crop, "")
            try:
                full, roi, _area = load_pair(_abs_path(crop), _abs_path(mask_path), expand=expand)
            except Exception:
                full = None
                roi = None
            if full is None or roi is None:
                # keep zeros; concat still matches the cached global row
                continue
            images_full.append(full)
            images_roi.append(roi)
            idxs.append(i)
            if len(images_full) >= batch_size:
                flush()
        flush()
        out = dest / f"{split}_embeddings.npz"
        payload["e_full"] = np.concatenate([e_full[:n_use], full_layers], axis=1).astype(np.float32)
        payload["e_roi"] = np.concatenate([e_roi[:n_use], roi_layers], axis=1).astype(np.float32)
        payload["e_full_layers"] = full_layers
        payload["e_roi_layers"] = roi_layers
        payload["layers"] = np.asarray([int(n_layers)], dtype=np.int64)
        if n_use < len(paths):
            for key in list(payload.keys()):
                value = payload[key]
                if isinstance(value, np.ndarray) and value.shape[:1] == (len(paths),):
                    payload[key] = value[:n_use]
        dest.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(out, **payload)
        if resolved.is_file():
            (dest / f"{split}_resolved.csv").write_text(resolved.read_text(encoding="utf-8"), encoding="utf-8")
        summary[split] = {
            "encoded": int(n_use),
            "source_rows": int(len(paths)),
            "dim": int(payload["e_full"].shape[1]),
        }
        print(split, summary[split], flush=True)
    (dest / "encode_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
