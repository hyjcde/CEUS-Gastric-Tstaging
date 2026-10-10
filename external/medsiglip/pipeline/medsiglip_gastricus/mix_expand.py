"""Mix 15 / 20 / 25% ROI tokens from existing caches. Does not overwrite those caches.

avg:  e_full = full20; e_roi = mean(roi15, roi20, roi25)
area: e_full = full20; e_roi = roi25 if lesion small, roi15 if large, else roi20
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from .constants import AREAROI_CACHE_DIR, AVGROI_CACHE_DIR, CACHE_DIR, SPLIT_FILES, cache_dir_for_expand
from .preprocess import load_mask, repo_path


def _index(paths: np.ndarray) -> dict[str, int]:
    return {str(p): i for i, p in enumerate(paths)}


def _mask_from_crop(crop: str) -> Path:
    path = repo_path(crop)
    return path.parent.parent / "roi_masks" / f"{path.stem}.png"


def _areas(paths: np.ndarray) -> np.ndarray:
    out = np.zeros(len(paths), dtype=np.float32)
    for i, crop in enumerate(paths):
        mask_path = _mask_from_crop(str(crop))
        if not mask_path.is_file():
            continue
        try:
            image = Image.open(repo_path(crop))
            mask = load_mask(mask_path, image.size)
            out[i] = float(mask.mean()) if mask.size else 0.0
        except Exception:
            out[i] = 0.0
    return out


def _align(src: dict[str, np.ndarray], paths: np.ndarray) -> np.ndarray:
    order = np.asarray([src["index"][str(p)] for p in paths], dtype=np.int64)
    return src["e_roi"][order]


def _load_roi(cache: Path, split: str) -> dict[str, object]:
    path = cache / f"{split}_embeddings.npz"
    if not path.is_file():
        raise FileNotFoundError(path)
    with np.load(path, allow_pickle=True) as data:
        paths = np.asarray(data["crop_ui_path"]).astype(str)
        return {
            "paths": paths,
            "index": _index(paths),
            "e_roi": np.asarray(data["e_roi"], dtype=np.float32),
            "payload": {key: data[key] for key in data.files},
        }


def _write_split(dest: Path, split: str, payload: dict[str, object], e_roi: np.ndarray, extra: dict[str, object]) -> dict[str, int]:
    dest.mkdir(parents=True, exist_ok=True)
    out = dict(payload)
    out["e_roi"] = e_roi.astype(np.float32)
    out.update(extra)
    np.savez_compressed(dest / f"{split}_embeddings.npz", **out)
    return {"rows": int(e_roi.shape[0]), "dim": int(e_roi.shape[1])}


def merge_avg_roi(dest: Path | None = None) -> dict[str, object]:
    dest = dest or AVGROI_CACHE_DIR
    if dest.resolve() in {CACHE_DIR.resolve(), cache_dir_for_expand(0.15).resolve(), cache_dir_for_expand(0.25).resolve()}:
        raise ValueError("refusing to overwrite a source cache")
    src20 = CACHE_DIR
    src15 = cache_dir_for_expand(0.15)
    src25 = cache_dir_for_expand(0.25)
    summary: dict[str, object] = {"dest": str(dest), "mode": "avg_roi15_20_25"}
    for split in SPLIT_FILES:
        a = _load_roi(src20, split)
        b = _load_roi(src15, split)
        c = _load_roi(src25, split)
        paths = a["paths"]
        e_roi = (_align(b, paths) + np.asarray(a["e_roi"]) + _align(c, paths)) / 3.0
        norms = np.linalg.norm(e_roi, axis=1, keepdims=True).clip(min=1e-8)
        e_roi = e_roi / norms
        summary[split] = _write_split(dest, split, a["payload"], e_roi, {"mix_mode": np.asarray(["avg"])})
        print(split, summary[split], flush=True)
    (dest / "encode_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def merge_area_roi(dest: Path | None = None) -> dict[str, object]:
    dest = dest or AREAROI_CACHE_DIR
    if dest.resolve() in {CACHE_DIR.resolve(), cache_dir_for_expand(0.15).resolve(), cache_dir_for_expand(0.25).resolve()}:
        raise ValueError("refusing to overwrite a source cache")
    src20 = CACHE_DIR
    src15 = cache_dir_for_expand(0.15)
    src25 = cache_dir_for_expand(0.25)
    train = _load_roi(src20, "train")
    areas_train = _areas(train["paths"])
    positive = areas_train[areas_train > 0]
    if positive.size == 0:
        raise RuntimeError("mask_area all zero; cannot build area-picked ROI cache")
    lo, hi = np.quantile(positive, [0.33, 0.67])
    summary: dict[str, object] = {
        "dest": str(dest),
        "mode": "area_pick: small->25, mid->20, large->15",
        "q33": float(lo),
        "q67": float(hi),
        "train_nonzero": int(positive.size),
    }
    for split in SPLIT_FILES:
        a = _load_roi(src20, split)
        b = _load_roi(src15, split)
        c = _load_roi(src25, split)
        paths = a["paths"]
        areas = _areas(paths)
        roi15 = _align(b, paths)
        roi20 = np.asarray(a["e_roi"])
        roi25 = _align(c, paths)
        pick = np.full(len(paths), 20, dtype=np.int16)
        e_roi = roi20.copy()
        small = areas <= lo
        large = areas >= hi
        e_roi[small] = roi25[small]
        e_roi[large] = roi15[large]
        pick[small] = 25
        pick[large] = 15
        empty = areas <= 0
        e_roi[empty] = roi20[empty]
        pick[empty] = 20
        summary[split] = _write_split(
            dest,
            split,
            a["payload"],
            e_roi,
            {"mix_mode": np.asarray(["area"]), "mask_area": areas, "roi_expand_pick": pick},
        )
        summary[f"{split}_pick"] = {
            "e15": int((pick == 15).sum()),
            "e20": int((pick == 20).sum()),
            "e25": int((pick == 25).sum()),
        }
        print(split, summary[split], summary[f"{split}_pick"], flush=True)
    (dest / "encode_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
