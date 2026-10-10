"""Lesion-mask geometry tokens. Sidecar only; does not overwrite embedding caches."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from .constants import CACHE_DIR, DATASET_DIR, MASK_GEOM_CACHE, SPLIT_FILES
from .encode import _abs_path, _load_mask

GEOM_DIM = 10
GEOM_FIELDS = (
    "area",
    "bbox_h",
    "bbox_w",
    "aspect",
    "centroid_y",
    "centroid_x",
    "row_thickness",
    "solidity",
    "border_contact",
    "edge_clearance",
)


def _geom(mask: np.ndarray) -> np.ndarray:
    out = np.zeros(GEOM_DIM, dtype=np.float32)
    h, w = mask.shape
    ys, xs = np.where(mask)
    if len(xs) == 0 or h == 0 or w == 0:
        return out
    area = float(len(xs) / mask.size)
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    bh = max(y1 - y0 + 1, 1)
    bw = max(x1 - x0 + 1, 1)
    aspect = min(bh / bw, 8.0) / 8.0
    row_w = mask[y0 : y1 + 1].sum(axis=1)
    thick = float(np.median(row_w[row_w > 0]) / w) if np.any(row_w) else 0.0
    contact = 0.0
    if h > 1 and w > 1:
        border = mask[0].sum() + mask[-1].sum() + mask[:, 0].sum() + mask[:, -1].sum()
        contact = float(border / max(len(xs), 1))
    clearance = float(min(y0, h - 1 - y1, x0, w - 1 - x1) / max(min(h, w), 1))
    out[:] = (
        area,
        bh / h,
        bw / w,
        aspect,
        float(ys.mean() / h),
        float(xs.mean() / w),
        thick,
        float(len(xs) / max(bh * bw, 1)),
        contact,
        clearance,
    )
    return out


def build_mask_geom(dest: Path | None = None) -> dict[str, object]:
    dest = dest or MASK_GEOM_CACHE
    dest.parent.mkdir(parents=True, exist_ok=True)
    pids: list[str] = []
    splits: list[str] = []
    feats: list[np.ndarray] = []
    summary: dict[str, object] = {"dest": str(dest), "fields": list(GEOM_FIELDS), "layout": "patient mean of 10-d frame geom"}
    for split, rel in SPLIT_FILES.items():
        npz = CACHE_DIR / f"{split}_embeddings.npz"
        csv = DATASET_DIR / rel
        if not npz.is_file():
            raise FileNotFoundError(npz)
        with np.load(npz, allow_pickle=True) as data:
            crops = np.asarray(data["crop_ui_path"]).astype(str)
            patient_ids = np.asarray(data["patient_id"]).astype(str)
        mask_by_crop: dict[str, str] = {}
        if csv.is_file():
            import pandas as pd

            table = pd.read_csv(csv)
            for _, row in table.iterrows():
                mask_by_crop[str(row.get("crop_ui_path", ""))] = str(row.get("mask_path", ""))
        bags: dict[str, list[np.ndarray]] = {}
        for crop, pid in zip(crops, patient_ids):
            mask_path = mask_by_crop.get(crop, "")
            vec = np.zeros(GEOM_DIM, dtype=np.float32)
            if mask_path:
                crop_abs = _abs_path(crop)
                try:
                    size = Image.open(crop_abs).size
                    vec = _geom(_load_mask(_abs_path(mask_path), size))
                except (OSError, ValueError):
                    vec = np.zeros(GEOM_DIM, dtype=np.float32)
            bags.setdefault(str(pid), []).append(vec)
        n = 0
        for pid, frames in bags.items():
            pids.append(pid)
            splits.append(split)
            feats.append(np.mean(np.stack(frames, axis=0), axis=0))
            n += 1
        summary[split] = {"patients": n, "dim": GEOM_DIM}
        print("mask-geom", split, summary[split], flush=True)
    stacked = np.stack(feats, axis=0).astype(np.float32)
    np.savez_compressed(
        dest,
        patient_id=np.asarray(pids),
        split=np.asarray(splits),
        embedding=stacked,
        fields=np.asarray(GEOM_FIELDS),
        meta=json.dumps(summary),
    )
    return summary


def load_mask_geom_map(path: Path | None = None) -> dict[str, np.ndarray]:
    path = path or MASK_GEOM_CACHE
    with np.load(path, allow_pickle=True) as data:
        pids = np.asarray(data["patient_id"]).astype(str)
        emb = np.asarray(data["embedding"], dtype=np.float32)
    return {pid: emb[i] for i, pid in enumerate(pids)}
