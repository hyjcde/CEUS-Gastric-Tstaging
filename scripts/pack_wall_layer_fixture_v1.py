#!/usr/bin/env python3
"""Pack a frozen wall-layer fixture bag from reader v150 cases.

Harvests lesion polygons from the zml keyframe dump and optional doctor
wall_polygon from live runtime. If no doctor line exists, writes a
provisional lesion-axis line and marks wall_source accordingly.

  python3 scripts/pack_wall_layer_fixture_v1.py --help
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from wall_lesion_aware_cluster import (  # noqa: E402
    as_xy,
    provisional_wall_from_lesion,
    rasterize_polygon,
)

DEFAULT_CASES = ("P008", "P019", "P040", "P076")
DISPLAY_TO_CASE = {
    "P008": "CASE-008",
    "P019": "CASE-019",
    "P040": "CASE-040",
    "P076": "CASE-076",
    "CASE-008": "CASE-008",
    "CASE-019": "CASE-019",
    "CASE-040": "CASE-040",
    "CASE-076": "CASE-076",
}
FROZEN = ROOT / "pipeline/data/zml_reader_v150_frozen_20260827"
CLINICAL = ROOT / "apps/gastric_scan_next/data/reader_v150_clinical.json"
PACKAGE = ROOT / "docs/clinical_validation/reader_study_v150/package_summary.json"
ZML_STATE = (
    ROOT
    / "runtime/gastric_scan_next/backups/zml_rereview_20260826_232057"
    / "doctor_case_state.json"
)
LIVE_STATE = ROOT / "runtime/gastric_scan_next/doctor_case_state.json"
LIVE_MASKS = ROOT / "runtime/gastric_scan_next/mask_overrides.json"
LUMEN_BACKUP = (
    ROOT
    / "runtime/gastric_scan_next/backups/zml_rereview_20260826_223057"
    / "lumen_overrides.json"
)
DEFAULT_OUT = ROOT / "pipeline/data/wall_layer_fixtures/v1"


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def relpath(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def clean_poly(points) -> list[list[float]]:
    pts = as_xy(points)
    return [[round(float(x), 2), round(float(y), 2)] for x, y in pts.tolist()]


def pick_keyframe(entries: list, case_id: str, account: str | None = None) -> dict | None:
    rows = [row for row in entries if str(row.get("case_id")) == case_id]
    if account:
        preferred = [row for row in rows if str(row.get("account_id")) == account]
        if preferred:
            rows = preferred
    best = None
    best_n = -1
    for row in rows:
        for kf in row.get("doctor_keyframes") or []:
            n = len(kf.get("lesionPolygon") or [])
            if n > best_n:
                best = kf
                best_n = n
    return best


def pick_wall(entries: list, masks: dict, case_id: str) -> tuple[list, str]:
    for row in entries:
        if str(row.get("case_id")) != case_id:
            continue
        for kf in row.get("doctor_keyframes") or []:
            wall = clean_poly(kf.get("wallPolygon") or [])
            if len(wall) >= 4:
                return wall, "doctor_keyframe"
    for key, row in (masks or {}).items():
        if case_id not in str(key):
            continue
        if not isinstance(row, dict):
            continue
        wall = clean_poly(row.get("wall_polygon") or [])
        if len(wall) >= 4:
            return wall, "doctor_mask_override"
    return [], ""


def pick_lumen(lumen_map: dict, case_id: str) -> tuple[list, dict | None, str]:
    row = lumen_map.get(case_id) or lumen_map.get(f"{case_id}::{case_id}") or {}
    if not isinstance(row, dict):
        return [], None, ""
    poly = clean_poly(row.get("lumen_polygon") or [])
    box = row.get("lumen_bbox") or row.get("lumen_box")
    if len(poly) >= 3:
        return poly, box if isinstance(box, dict) else None, "lumen_polygon"
    if isinstance(box, dict):
        try:
            x1, y1 = float(box["x1"]), float(box["y1"])
            x2, y2 = float(box["x2"]), float(box["y2"])
            poly = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
            return poly, box, "lumen_bbox"
        except (KeyError, TypeError, ValueError):
            return [], None, ""
    return [], None, ""


def clinical_site(clinical: dict, case_id: str) -> str:
    by_case = clinical.get("by_case") if isinstance(clinical, dict) else None
    row = (by_case or clinical or {}).get(case_id) or {}
    return str(row.get("tumor_location") or "").strip()


def package_pt(package: dict, case_id: str) -> str:
    for case in package.get("cases") or []:
        if str(case.get("case_id")) == case_id:
            return str(case.get("reference_pt") or "").strip()
    return ""


def frozen_row(frames_csv: Path, case_id: str) -> dict:
    if not frames_csv.exists():
        return {}
    with frames_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if str(row.get("case_id")) == case_id:
                return row
    return {}


def pack_one(
    token: str,
    *,
    zml_entries: list,
    live_entries: list,
    masks: dict,
    lumen_map: dict,
    clinical: dict,
    package: dict,
    out_root: Path,
    brush_radius: float,
) -> dict:
    case_id = DISPLAY_TO_CASE.get(token.upper(), token)
    display_id = next((key for key, value in DISPLAY_TO_CASE.items() if value == case_id and key.startswith("P")), case_id)
    frozen = frozen_row(FROZEN / "frames.csv", case_id)
    image_path = Path(frozen.get("image_path") or FROZEN / "images" / f"{case_id}.jpg")
    mask_path = Path(frozen.get("mask_path") or FROZEN / "masks" / f"{case_id}.png")
    skip = ""
    if not image_path.exists():
        skip = "missing_frame"
    kf = pick_keyframe(zml_entries, case_id, "zml") or pick_keyframe(zml_entries, case_id)
    lesion = clean_poly((kf or {}).get("lesionPolygon") or [])
    if len(lesion) < 3 and mask_path.exists():
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask is not None:
            contours, _ = cv2.findContours((mask > 0).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                biggest = max(contours, key=cv2.contourArea)
                lesion = clean_poly(biggest.reshape(-1, 2))
    if len(lesion) < 3 and not skip:
        skip = "missing_lesion"
    wall, wall_source = pick_wall(live_entries + zml_entries, masks, case_id)
    if len(wall) < 4 and image_path.exists() and len(lesion) >= 3:
        image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if image is not None:
            wall = clean_poly(provisional_wall_from_lesion(np.asarray(lesion, dtype=np.float32), image.shape))
            wall_source = "provisional_lesion_axis"
    lumen_poly, lumen_box, lumen_source = pick_lumen(lumen_map, case_id)
    time_sec = float((kf or {}).get("timeSec") or frozen.get("time_sec") or 0.0)
    meta = {
        "case_id": case_id,
        "display_id": display_id,
        "time_sec": time_sec,
        "frame_path": relpath(image_path),
        "mask_path": relpath(mask_path) if mask_path.exists() else "",
        "lesion_polygon": lesion,
        "wall_polygon": wall,
        "wall_source": wall_source,
        "lumen_polygon": lumen_poly,
        "lumen_bbox": lumen_box,
        "cavity_side_source": lumen_source or "heuristic",
        "brush_radius": brush_radius,
        "pT_ref": package_pt(package, case_id) or str(frozen.get("gold") or ""),
        "site": clinical_site(clinical, case_id),
        "artifact_note": "",
        "analyzable_note": "",
        "skip_reason": skip,
        "packed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    dest = out_root / case_id
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if image_path.exists() and len(lesion) >= 3:
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is not None:
            preview = image.copy()
            cv2.polylines(preview, [np.round(as_xy(lesion)).astype(np.int32)], True, (0, 0, 220), 2)
            if len(wall) >= 2:
                cv2.polylines(preview, [np.round(as_xy(wall)).astype(np.int32)], False, (0, 210, 255), 2)
            cv2.imwrite(str(dest / "preview.jpg"), preview)
    return meta


def main() -> int:
    parser = argparse.ArgumentParser(description="Pack wall-layer fixtures for lesion-aware clustering.")
    parser.add_argument("--cases", default=",".join(DEFAULT_CASES), help="Comma-separated P008,P019,... or CASE-008")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--brush-radius", type=float, default=8.0)
    args = parser.parse_args()
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    tokens = [item.strip() for item in str(args.cases).split(",") if item.strip()]
    zml = load_json(ZML_STATE, {"entries": []})
    live = load_json(LIVE_STATE, {"entries": []})
    masks = load_json(LIVE_MASKS, {})
    lumen_map = load_json(LUMEN_BACKUP, {})
    clinical = load_json(CLINICAL, {})
    package = load_json(PACKAGE, {})
    rows = []
    for token in tokens:
        meta = pack_one(
            token,
            zml_entries=list(zml.get("entries") or []),
            live_entries=list(live.get("entries") or []),
            masks=masks if isinstance(masks, dict) else {},
            lumen_map=lumen_map if isinstance(lumen_map, dict) else {},
            clinical=clinical if isinstance(clinical, dict) else {},
            package=package if isinstance(package, dict) else {},
            out_root=out_root,
            brush_radius=float(args.brush_radius),
        )
        rows.append(meta)
        print(
            f"{meta['display_id']} {meta['case_id']} wall={meta['wall_source'] or 'none'} "
            f"lesion={len(meta['lesion_polygon'])} skip={meta['skip_reason'] or '-'}",
            flush=True,
        )
    manifest = out_root / "manifest.csv"
    fields = [
        "display_id", "case_id", "pT_ref", "site", "time_sec", "wall_source",
        "cavity_side_source", "brush_radius", "skip_reason", "frame_path",
    ]
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for meta in rows:
            writer.writerow({key: meta.get(key, "") for key in fields})
    readme = (
        "# wall_layer_fixtures v1\n\n"
        "Offline bag for lesion-aware wall clustering. Images stay in the frozen "
        "reader pack; this folder only stores meta and a small preview.\n\n"
        "wall_source=provisional_lesion_axis is not a doctor line. Do not report "
        "agreement until a real wall_polygon is harvested.\n"
    )
    (out_root / "README.md").write_text(readme, encoding="utf-8")
    print(f"wrote {manifest}", flush=True)
    return 0 if all(not row.get("skip_reason") for row in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
