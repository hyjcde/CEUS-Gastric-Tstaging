"""Merge 20% full/ROI with 15% and 25% ROI tokens. Does not overwrite those caches."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .constants import CACHE_DIR, MULTI1525_CACHE_DIR, SPLIT_FILES, cache_dir_for_expand


def _index(paths: np.ndarray) -> dict[str, int]:
    return {str(p): i for i, p in enumerate(paths)}


def merge_multi_expand(dest: Path | None = None) -> dict[str, object]:
    dest = dest or MULTI1525_CACHE_DIR
    if dest.resolve() == CACHE_DIR.resolve():
        raise ValueError("refusing to overwrite the 20% cache")
    dest.mkdir(parents=True, exist_ok=True)
    src20 = CACHE_DIR
    src15 = cache_dir_for_expand(0.15)
    src25 = cache_dir_for_expand(0.25)
    summary: dict[str, object] = {
        "dest": str(dest),
        "src20": str(src20),
        "src15": str(src15),
        "src25": str(src25),
        "layout": "e_full=concat(full20, roi15); e_roi=concat(roi20, roi25); dim=2304",
    }
    for split in SPLIT_FILES:
        p20 = src20 / f"{split}_embeddings.npz"
        p15 = src15 / f"{split}_embeddings.npz"
        p25 = src25 / f"{split}_embeddings.npz"
        for path in (p20, p15, p25):
            if not path.is_file():
                raise FileNotFoundError(path)
        with np.load(p20, allow_pickle=True) as a, np.load(p15, allow_pickle=True) as b, np.load(
            p25, allow_pickle=True
        ) as c:
            paths = np.asarray(a["crop_ui_path"]).astype(str)
            idx15 = _index(np.asarray(b["crop_ui_path"]).astype(str))
            idx25 = _index(np.asarray(c["crop_ui_path"]).astype(str))
            order15 = np.asarray([idx15[p] for p in paths], dtype=np.int64)
            order25 = np.asarray([idx25[p] for p in paths], dtype=np.int64)
            e_full = np.concatenate([np.asarray(a["e_full"]), np.asarray(b["e_roi"])[order15]], axis=1)
            e_roi = np.concatenate([np.asarray(a["e_roi"]), np.asarray(c["e_roi"])[order25]], axis=1)
            payload = {key: a[key] for key in a.files}
        payload["e_full"] = e_full.astype(np.float32)
        payload["e_roi"] = e_roi.astype(np.float32)
        payload["multi_expand"] = np.asarray([15, 20, 25], dtype=np.int64)
        np.savez_compressed(dest / f"{split}_embeddings.npz", **payload)
        resolved = src20 / f"{split}_resolved.csv"
        if resolved.is_file():
            (dest / f"{split}_resolved.csv").write_text(resolved.read_text(encoding="utf-8"), encoding="utf-8")
        summary[split] = {"rows": int(len(paths)), "dim": int(e_full.shape[1])}
        print(split, summary[split], flush=True)
    (dest / "encode_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
