#!/usr/bin/env python3
"""Compute crop_ui offset within original image via template matching."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2


def compute_offset(original_path: Path, crop_path: Path) -> dict:
    original = cv2.imread(str(original_path), cv2.IMREAD_GRAYSCALE)
    crop = cv2.imread(str(crop_path), cv2.IMREAD_GRAYSCALE)
    if original is None:
        raise FileNotFoundError(f"Cannot read original image: {original_path}")
    if crop is None:
        raise FileNotFoundError(f"Cannot read crop_ui image: {crop_path}")

    result = cv2.matchTemplate(original, crop, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    offset_x, offset_y = int(max_loc[0]), int(max_loc[1])
    crop_h, crop_w = crop.shape[:2]
    orig_h, orig_w = original.shape[:2]

    return {
        "offsetX": offset_x,
        "offsetY": offset_y,
        "originalWidth": orig_w,
        "originalHeight": orig_h,
        "cropWidth": crop_w,
        "cropHeight": crop_h,
        "matchScore": float(max_val),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original", required=True)
    parser.add_argument("--crop", required=True)
    args = parser.parse_args()

    try:
        payload = compute_offset(Path(args.original), Path(args.crop))
        print(json.dumps(payload))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
