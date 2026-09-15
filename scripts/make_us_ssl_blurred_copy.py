#!/usr/bin/env python3
"""Build the Deblurring-MAE paired dataset from the us_ssl_v2_200k frame set.

Replicates the official DeblurringMIM protocol (blurred_images.py):
  grayscale read -> cv2.GaussianBlur((0, 0), sigma=1.1) -> save as jpg.

Output tree (CorruptDataset expects <root>/<train|val>/<class_dir>/<files>):

  data/pretrain/us_ssl_v2_mae_deblur/
    orig/train/all/*.jpg      -> symlinks to the original frames
    orig/val/all/*.jpg        -> symlinks (512 frames, seed-0 random split)
    blurred/train/all/*.jpg   -> real blurred grayscale jpgs
    blurred/val/all/*.jpg     -> real blurred grayscale jpgs

CPU only; safe to run while GPU training is ongoing (use nice).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "data" / "pretrain" / "us_ssl_v2_200k" / "images"
DST = PROJECT_ROOT / "data" / "pretrain" / "us_ssl_v2_mae_deblur"


def blur_one(task: tuple[str, str, float]) -> str:
    src, dst, sigma = task
    if os.path.exists(dst):
        return dst
    img = cv2.imread(src, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RuntimeError(f"cv2.imread failed: {src}")
    blurred = cv2.GaussianBlur(img, (0, 0), sigma)
    cv2.imwrite(dst, blurred, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return dst


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=SRC)
    parser.add_argument("--dst", type=Path, default=DST)
    parser.add_argument("--sigma", type=float, default=1.1)
    parser.add_argument("--n-val", type=int, default=512)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()

    frames = sorted(p for p in args.src.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if not frames:
        raise RuntimeError(f"no frames under {args.src}")
    rng = random.Random(args.seed)
    val_set = set(rng.sample(range(len(frames)), min(args.n_val, len(frames))))

    t0 = time.time()
    tasks: list[tuple[str, str, float]] = []
    for idx, path in enumerate(frames):
        split = "val" if idx in val_set else "train"
        orig_link = args.dst / "orig" / split / "all" / path.name
        orig_link.parent.mkdir(parents=True, exist_ok=True)
        if not orig_link.exists():
            os.symlink(path.resolve(), orig_link)
        blur_path = args.dst / "blurred" / split / "all" / path.name
        blur_path.parent.mkdir(parents=True, exist_ok=True)
        tasks.append((str(path), str(blur_path), args.sigma))

    print(f"[blur] {len(frames)} frames ({len(frames) - len(val_set)} train / {len(val_set)} val), "
          f"sigma={args.sigma}, workers={args.workers}", flush=True)
    done = 0
    with Pool(args.workers) as pool:
        for _ in pool.imap_unordered(blur_one, tasks, chunksize=64):
            done += 1
            if done % 20000 == 0:
                print(f"[blur] {done}/{len(tasks)} ({time.time() - t0:.0f}s)", flush=True)

    summary = {
        "src": str(args.src),
        "dst": str(args.dst),
        "sigma": args.sigma,
        "n_frames": len(frames),
        "n_train": len(frames) - len(val_set),
        "n_val": len(val_set),
        "seed": args.seed,
        "elapsed_sec": round(time.time() - t0, 1),
        "protocol": "grayscale -> cv2.GaussianBlur((0,0), sigma) -> jpg q95 (DeblurringMIM blurred_images.py)",
    }
    (args.dst / "blur_manifest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"[blur] done in {time.time() - t0:.0f}s -> {args.dst}", flush=True)


if __name__ == "__main__":
    main()
