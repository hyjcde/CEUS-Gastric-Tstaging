"""方案 3: 冻结 MedSigLIP-448 特征提取。预处理在 preprocess.py（方案 2）。

e_full[i,j] = L2(MedSigLIP(full_frame[i,j]))
e_roi[i,j]  = L2(MedSigLIP(roi_crop[i,j]))
各 1152 维。整段 eval + requires_grad=False + no_grad，不训 ViT。
四份 npz 供下游共用同一视觉输入。改 expand 时 full 可复用，ROI 必须重编。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor

from .constants import CACHE_DIR, DATASET_DIR, EMBED_DIM, ROI_EXPAND, SPLIT_FILES, WEIGHT_BYTES, WEIGHT_DIR, WEIGHT_SHA256, cache_dir_for_expand, cache_dir_for_pad
from .preprocess import assert_processor, expand_roi, full_frame, load_mask, load_pair, repo_path, square_pad

_abs_path = repo_path
_load_mask = load_mask
_square_pad = square_pad


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(8 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def assert_weights() -> Path:
    """方案 3: 拒绝大小或 SHA 不对的 medsiglip-448 权重。"""
    weight = WEIGHT_DIR / "model.safetensors"
    if not weight.is_file() or weight.stat().st_size != WEIGHT_BYTES:
        raise FileNotFoundError(f"MedSigLIP weight missing or incomplete: {weight}")
    digest = sha256_file(weight)
    if digest != WEIGHT_SHA256:
        raise RuntimeError(f"MedSigLIP sha256 mismatch {digest}")
    return WEIGHT_DIR


def load_frozen_encoder(device: str):
    """方案 3: 完全冻结视觉 encoder。eval + 关掉梯度，训练图不含 ViT。"""
    assert_weights()
    model = AutoModel.from_pretrained(str(WEIGHT_DIR), local_files_only=True).to(device).eval()
    model.requires_grad_(False)
    processor = AutoProcessor.from_pretrained(str(WEIGHT_DIR), local_files_only=True)
    contract = assert_processor(processor)
    return model, processor, contract


@torch.no_grad()
def encode_images(model, processor, images: list[Image.Image], device: str) -> np.ndarray:
    """方案 2.1 + 3: 官方 processor 后 get_image_features，L2 到 1152 维。"""
    inputs = processor(images=images, return_tensors="pt")
    pixel = inputs["pixel_values"].to(device)
    embeds = model.get_image_features(pixel_values=pixel)
    embeds = torch.nn.functional.normalize(embeds, p=2, dim=-1)
    if embeds.shape[-1] != EMBED_DIM:
        raise RuntimeError(f"embedding dim {embeds.shape[-1]}, expected {EMBED_DIM}")
    return embeds.float().cpu().numpy()


def _full_lookup(src_npz: Path) -> dict[str, np.ndarray]:
    with np.load(src_npz, allow_pickle=True) as data:
        paths = np.asarray(data["crop_ui_path"]).astype(str)
        full = np.asarray(data["e_full"])
    return {path: full[i] for i, path in enumerate(paths)}


def encode_split(
    resolved_csv: Path,
    out_npz: Path,
    device: str,
    batch_size: int,
    expand: float = ROI_EXPAND,
    pad: str = "black",
    reuse_full: dict[str, np.ndarray] | None = None,
    bbox_mode: str = "all",
    model=None,
    processor=None,
) -> dict[str, object]:
    table = pd.read_csv(resolved_csv)
    usable = table[(table["crop_ui_path"] != "") & (table["mask_path"] != "")].reset_index(drop=True)
    if model is None or processor is None:
        model, processor, _contract = load_frozen_encoder(device)
    full_all = np.zeros((len(usable), EMBED_DIM), dtype=np.float32)
    roi_all = np.zeros((len(usable), EMBED_DIM), dtype=np.float32)
    area_all = np.zeros(len(usable), dtype=np.float32)
    keep = []
    errors: list[dict[str, str]] = []
    cursor = 0
    batch_full: list[Image.Image] = []
    batch_roi: list[Image.Image] = []
    reused_full: list[np.ndarray] = []
    encode_full = reuse_full is None

    def flush() -> None:
        nonlocal cursor
        if not batch_roi:
            return
        images = (batch_full + batch_roi) if encode_full else batch_roi
        stacked = encode_images(model, processor, images, device)
        n = len(batch_roi)
        if encode_full:
            full_all[cursor : cursor + n] = stacked[:n]
            roi_all[cursor : cursor + n] = stacked[n:]
        else:
            full_all[cursor : cursor + n] = np.stack(reused_full, axis=0)
            roi_all[cursor : cursor + n] = stacked
        cursor += n
        batch_full.clear()
        batch_roi.clear()
        reused_full.clear()

    for i, row in usable.iterrows():
        crop_key = str(row["crop_ui_path"])
        try:
            full, roi, area = load_pair(
                _abs_path(crop_key),
                _abs_path(row["mask_path"]),
                expand=expand,
                pad=pad,
                bbox_mode=bbox_mode,
            )
        except Exception as exc:
            errors.append({"crop_ui_path": crop_key, "error": f"{type(exc).__name__}: {exc}"})
            continue
        if reuse_full is not None:
            cached = reuse_full.get(crop_key)
            if cached is None:
                errors.append({"crop_ui_path": crop_key, "error": "missing_cached_e_full"})
                continue
            reused_full.append(cached)
        else:
            batch_full.append(full)
        batch_roi.append(roi)
        area_all[len(keep)] = area
        keep.append(int(i))
        if len(batch_roi) >= batch_size:
            flush()
            if cursor and cursor % 512 == 0:
                print(f"  encoded {cursor}/{len(usable)} expand={expand}", flush=True)
    flush()
    kept = usable.iloc[keep[:cursor]].reset_index(drop=True)
    out_npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_npz,
        e_full=full_all[:cursor],
        e_roi=roi_all[:cursor],
        mask_area=area_all[:cursor],
        expand=np.asarray([float(expand)], dtype=np.float32),
        pad=np.asarray([str(pad)]),
        bbox_mode=np.asarray([str(bbox_mode)]),
        label=kept["label"].to_numpy(dtype=np.int64),
        patient_id=kept["patient_id"].astype(str).to_numpy(),
        source=kept["source"].astype(str).to_numpy(),
        crop_ui_path=kept["crop_ui_path"].astype(str).to_numpy(),
        clinical=np.stack([json.loads(x) for x in kept["clinical_22"]], axis=0).astype(np.float32),
    )
    return {
        "rows": int(len(table)),
        "usable": int(len(usable)),
        "encoded": int(cursor),
        "failed": int(len(errors)),
        "expand": float(expand),
        "pad": str(pad),
        "bbox_mode": str(bbox_mode),
        "reused_full": int(reuse_full is not None),
        "errors": errors[:20],
    }


def ensure_mask_areas(cache_dir: Path) -> dict[str, int]:
    """Add mask_area to existing npz files that were encoded before this field existed."""
    written = {}
    for split in SPLIT_FILES:
        npz_path = cache_dir / f"{split}_embeddings.npz"
        if not npz_path.is_file():
            continue
        with np.load(npz_path, allow_pickle=True) as data:
            if "mask_area" in data.files:
                written[split] = int(len(data["mask_area"]))
                continue
            payload = {key: data[key] for key in data.files}
            paths = np.asarray(data["crop_ui_path"]).astype(str)
        resolved = cache_dir / f"{split}_resolved.csv"
        mask_by_crop: dict[str, str] = {}
        if resolved.is_file():
            table = pd.read_csv(resolved)
            for _, row in table.iterrows():
                mask_by_crop[str(row["crop_ui_path"])] = str(row.get("mask_path", ""))
        areas = np.zeros(len(paths), dtype=np.float32)
        for i, crop in enumerate(paths):
            mask_path = mask_by_crop.get(crop, "")
            if not mask_path:
                continue
            try:
                full = full_frame(_abs_path(crop))
                mask = load_mask(_abs_path(mask_path), full.size)
                areas[i] = float(mask.mean()) if mask.size else 0.0
            except Exception:
                areas[i] = 0.0
        payload["mask_area"] = areas
        np.savez_compressed(npz_path, **payload)
        written[split] = int(len(areas))
        print(f"mask_area {split} {written[split]}", flush=True)
    return written


def encode_all(
    device: str = "cuda:0",
    batch_size: int = 8,
    expand: float = ROI_EXPAND,
    dest: Path | None = None,
    reuse_full: bool = True,
    pad: str = "black",
    bbox_mode: str = "all",
) -> dict[str, object]:
    """方案 3: 预计算并缓存四份冻结 embedding。15/25% 缓存复用 20% 的 e_full。"""
    dest = dest or (cache_dir_for_pad(pad) if str(pad).lower() != "black" else cache_dir_for_expand(expand))
    if dest.resolve() == CACHE_DIR.resolve() and str(pad).lower() != "black":
        raise ValueError("refusing to overwrite the 20% black-pad cache")
    if dest.resolve() == CACHE_DIR.resolve() and str(bbox_mode) != "all":
        raise ValueError("refusing to overwrite the 20% all-nonzero-bbox cache; use a new dest")
    dest.mkdir(parents=True, exist_ok=True)
    model, processor, contract = load_frozen_encoder(device)
    summary: dict[str, object] = {
        "expand": float(expand),
        "pad": str(pad),
        "bbox_mode": str(bbox_mode),
        "dest": str(dest),
        "processor": contract,
        "embed_dim": EMBED_DIM,
        "weight_dir": str(WEIGHT_DIR),
    }
    for split, rel in SPLIT_FILES.items():
        resolved = dest / f"{split}_resolved.csv"
        if not resolved.is_file():
            source_resolved = CACHE_DIR / f"{split}_resolved.csv"
            if source_resolved.is_file():
                resolved.write_text(source_resolved.read_text(encoding="utf-8"), encoding="utf-8")
            else:
                published = DATASET_DIR / rel
                if published.is_file():
                    resolved = published
                else:
                    raise FileNotFoundError(resolved)
        lookup = None
        src_npz = CACHE_DIR / f"{split}_embeddings.npz"
        if reuse_full and src_npz.is_file() and dest != CACHE_DIR:
            lookup = _full_lookup(src_npz)
        summary[split] = encode_split(
            resolved,
            dest / f"{split}_embeddings.npz",
            device,
            batch_size,
            expand=expand,
            pad=pad,
            reuse_full=lookup,
            bbox_mode=bbox_mode,
            model=model,
            processor=processor,
        )
        print(split, summary[split], flush=True)
    (dest / "encode_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
