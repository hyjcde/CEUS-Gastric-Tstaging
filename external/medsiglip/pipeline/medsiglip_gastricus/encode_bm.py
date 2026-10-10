"""Frozen MedSigLIP encode for the BM GastricUS head."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from .constants import BM_CACHE_DIR, EMBED_DIM, MAIN_ROOT, ROI_EXPAND, SPLIT_FILES
from .encode import encode_images, load_frozen_encoder
from .preprocess import full_frame, load_mask, load_pair, square_pad


def _abs(rel: object) -> Path:
    path = Path(str(rel or ""))
    if not str(path):
        return path
    return path if path.is_absolute() else MAIN_ROOT / path


def _load_views(row: pd.Series, expand: float, pad: str) -> tuple[Image.Image, Image.Image, float]:
    crop = _abs(row["crop_ui_path"])
    mask = _abs(row.get("mask_path") or "")
    fallback = _abs(row.get("roi_fallback_path") or "")
    full = full_frame(crop)
    area = float(load_mask(mask, full.size).mean()) if mask.is_file() else 0.0
    if fallback.is_file():
        return full, square_pad(full_frame(fallback), pad=pad), area
    if mask.is_file():
        return load_pair(crop, mask, expand=expand, pad=pad)
    return full, square_pad(full, pad=pad), 0.0


def encode_bm_split(
    resolved_csv: Path,
    out_npz: Path,
    device: str,
    batch_size: int,
    expand: float = ROI_EXPAND,
    model=None,
    processor=None,
) -> dict[str, object]:
    table = pd.read_csv(resolved_csv)
    if model is None or processor is None:
        model, processor, _ = load_frozen_encoder(device)
    full_all = np.zeros((len(table), EMBED_DIM), dtype=np.float32)
    roi_all = np.zeros((len(table), EMBED_DIM), dtype=np.float32)
    area_all = np.zeros(len(table), dtype=np.float32)
    keep: list[int] = []
    errors: list[dict[str, str]] = []
    cursor = 0
    batch_full: list[Image.Image] = []
    batch_roi: list[Image.Image] = []

    def flush() -> None:
        nonlocal cursor
        if not batch_roi:
            return
        stacked = encode_images(model, processor, batch_full + batch_roi, device)
        n = len(batch_roi)
        full_all[cursor : cursor + n] = stacked[:n]
        roi_all[cursor : cursor + n] = stacked[n:]
        cursor += n
        batch_full.clear()
        batch_roi.clear()

    for i, row in table.iterrows():
        try:
            full, roi, area = _load_views(row, expand=expand, pad="black")
        except Exception as exc:
            errors.append({"crop_ui_path": str(row["crop_ui_path"]), "error": f"{type(exc).__name__}: {exc}"})
            continue
        batch_full.append(full)
        batch_roi.append(roi)
        area_all[len(keep)] = area
        keep.append(int(i))
        if len(batch_roi) >= batch_size:
            flush()
            if cursor and cursor % 256 == 0:
                print(f"  bm encoded {cursor}/{len(table)}", flush=True)
    flush()
    kept = table.iloc[keep[:cursor]].reset_index(drop=True)
    clinical = np.stack([json.loads(x) for x in kept["clinical"]], axis=0).astype(np.float32)
    out_npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out_npz,
        e_full=full_all[:cursor],
        e_roi=roi_all[:cursor],
        mask_area=area_all[:cursor],
        expand=np.asarray([float(expand)], dtype=np.float32),
        label=kept["label"].to_numpy(dtype=np.int64),
        patient_id=kept["patient_id"].astype(str).to_numpy(),
        source=kept["source"].astype(str).to_numpy(),
        crop_ui_path=kept["crop_ui_path"].astype(str).to_numpy(),
        clinical=clinical,
        bm_sign_n_filled=kept["bm_sign_n_filled"].to_numpy(dtype=np.int64),
    )
    return {
        "rows": int(len(table)),
        "encoded": int(cursor),
        "failed": int(len(errors)),
        "clinical_dim": int(clinical.shape[1]) if len(clinical) else 0,
        "errors": errors[:12],
    }


def encode_bm(
    device: str = "cuda:0",
    batch_size: int = 8,
    expand: float = ROI_EXPAND,
    dest: Path | None = None,
) -> dict[str, object]:
    dest = dest or BM_CACHE_DIR
    dest.mkdir(parents=True, exist_ok=True)
    model, processor, contract = load_frozen_encoder(device)
    summary: dict[str, object] = {
        "dest": str(dest),
        "expand": float(expand),
        "processor": contract,
        "main_root": str(MAIN_ROOT),
    }
    for split in SPLIT_FILES:
        resolved = dest / f"{split}_resolved.csv"
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        summary[split] = encode_bm_split(
            resolved,
            dest / f"{split}_embeddings.npz",
            device,
            batch_size,
            expand=expand,
            model=model,
            processor=processor,
        )
        print(split, summary[split], flush=True)
    (dest / "encode_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
