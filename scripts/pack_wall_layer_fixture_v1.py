#!/usr/bin/env python3
"""Pack a frozen wall-layer fixture bag from reader v150 cases.

Prefers the latest public ZML wall stroke (doctor_case_state / mask_overrides),
extracts that cine time, and pairs the same-frame lesion when it exists.

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

from wall_lesion_aware_cluster import as_xy, provisional_wall_from_lesion  # noqa: E402

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
PUBLIC_PULL = Path("/tmp/zml_runtime_20260829")
MEDIA = ROOT / "docs/clinical_validation/reader_study_v150"
NEAR_LESION_SEC = 0.30


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


def grab_frame(video_path: Path, time_sec: float):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(time_sec)) * 1000.0)
    ok, frame = cap.read()
    if not ok:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ok, frame = cap.read()
    cap.release()
    return frame if ok else None


def video_path_for(case_id: str, package: dict) -> Path | None:
    for case in package.get("cases") or []:
        if str(case.get("case_id")) != case_id:
            continue
        frames = case.get("frames") or []
        if frames:
            rel = str(frames[0].get("video_rel") or "")
            if rel:
                path = MEDIA / rel
                return path if path.exists() else None
    fallback = MEDIA / "images" / case_id / "clip_01.mp4"
    return fallback if fallback.exists() else None


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
    hit = harvest_zml_wall(entries, masks, case_id)
    if hit:
        return hit["wall"], hit["wall_source"]
    return [], ""


def slim_readout(readout) -> dict:
    if not isinstance(readout, dict):
        return {}
    ticks = []
    for tick in readout.get("ticks") or []:
        if not isinstance(tick, dict):
            continue
        ticks.append({
            "layer": tick.get("layer"),
            "nameZh": tick.get("nameZh"),
            "labelZh": tick.get("labelZh"),
            "status": tick.get("status"),
        })
    return {
        "painted_layers": readout.get("paintedLayers"),
        "note_zh": readout.get("noteZh"),
        "ticks": ticks,
        "source": readout.get("source"),
    }


def harvest_zml_wall(entries: list, masks: dict, case_id: str, account: str = "zml") -> dict | None:
    cands: list[dict] = []
    for row in entries:
        if str(row.get("account_id")) != account or str(row.get("case_id")) != case_id:
            continue
        updated = str(row.get("updated_at") or "")
        for kf in row.get("doctor_keyframes") or []:
            wall = clean_poly(kf.get("wallPolygon") or [])
            if len(wall) < 4:
                continue
            bands = kf.get("wallLayerBands") or []
            cands.append({
                "wall": wall,
                "lesion": clean_poly(kf.get("lesionPolygon") or []),
                "time_sec": float(kf.get("timeSec") or 0.0),
                "keyframe_id": str(kf.get("id") or ""),
                "n_bands": len(bands),
                "visibility": kf.get("wallVisibility"),
                "anchor": kf.get("serosaAnchorMode"),
                "updated_at": updated,
                "wall_source": "zml_keyframe",
                "readout": slim_readout(kf.get("wallLayerReadout")),
            })
    for key, row in (masks or {}).items():
        if account not in str(key) or case_id not in str(key):
            continue
        if not isinstance(row, dict):
            continue
        wall = clean_poly(row.get("wall_polygon") or [])
        if len(wall) < 4:
            continue
        time_sec = float(row.get("video_time_sec") or 0.0)
        readout = {}
        for entry in entries:
            if str(entry.get("account_id")) != account or str(entry.get("case_id")) != case_id:
                continue
            for kf in entry.get("doctor_keyframes") or []:
                if abs(float(kf.get("timeSec") or 0.0) - time_sec) > 0.02:
                    continue
                readout = slim_readout(kf.get("wallLayerReadout"))
                break
        cands.append({
            "wall": wall,
            "lesion": clean_poly(row.get("mask_polygon") or []),
            "time_sec": time_sec,
            "keyframe_id": str(key),
            "n_bands": 0,
            "visibility": None,
            "anchor": None,
            "updated_at": str(row.get("updated_at") or ""),
            "wall_source": "zml_mask_override",
            "readout": readout,
        })
    if not cands:
        return None
    cands.sort(key=lambda item: (item["updated_at"], item["n_bands"], len(item["wall"])))
    return cands[-1]


def nearest_zml_lesion(entries: list, case_id: str, time_sec: float, account: str = "zml") -> tuple[list, float, str]:
    best: list = []
    best_dt = 1e9
    best_id = ""
    for row in entries:
        if str(row.get("account_id")) != account or str(row.get("case_id")) != case_id:
            continue
        for kf in row.get("doctor_keyframes") or []:
            lesion = clean_poly(kf.get("lesionPolygon") or [])
            if len(lesion) < 3:
                continue
            dt = abs(float(kf.get("timeSec") or 0.0) - time_sec)
            if dt < best_dt:
                best, best_dt, best_id = lesion, dt, str(kf.get("id") or "")
    return best, best_dt, best_id


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
    dest = out_root / case_id
    dest.mkdir(parents=True, exist_ok=True)
    skip = ""
    entries = list(live_entries) + list(zml_entries)
    hit = harvest_zml_wall(entries, masks, case_id)
    wall, wall_source = ([], "")
    time_sec = float(frozen.get("time_sec") or 0.0)
    lesion: list = []
    lesion_source = ""
    keyframe_id = ""
    n_bands = 0
    if hit:
        wall = hit["wall"]
        wall_source = hit["wall_source"]
        time_sec = hit["time_sec"]
        keyframe_id = hit["keyframe_id"]
        n_bands = int(hit.get("n_bands") or 0)
        if len(hit.get("lesion") or []) >= 3:
            lesion = hit["lesion"]
            lesion_source = "same_frame"
    if len(lesion) < 3:
        near, dt, near_id = nearest_zml_lesion(entries, case_id, time_sec)
        if len(near) >= 3 and dt <= NEAR_LESION_SEC:
            lesion = near
            lesion_source = f"nearest_kf_{near_id}_dt{dt:.3f}"
        elif len(near) >= 3:
            lesion_source = f"other_kf_{near_id}_dt{dt:.3f}_not_used"
    video = video_path_for(case_id, package)
    frame = grab_frame(video, time_sec) if video else None
    image_path = dest / "frame.jpg"
    if frame is None:
        frozen_img = Path(frozen.get("image_path") or FROZEN / "images" / f"{case_id}.jpg")
        if frozen_img.exists():
            image_path = frozen_img
            if not skip and not hit:
                skip = "missing_zml_wall_used_frozen_frame"
        else:
            skip = "missing_frame"
    else:
        cv2.imwrite(str(image_path), frame)
    if len(wall) < 4:
        skip = skip or "missing_zml_wall"
    if len(wall) < 4 and image_path.exists() and len(lesion) >= 3:
        image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if image is not None:
            wall = clean_poly(provisional_wall_from_lesion(np.asarray(lesion, dtype=np.float32), image.shape))
            wall_source = "provisional_lesion_axis"
    lumen_poly, lumen_box, lumen_source = pick_lumen(lumen_map, case_id)
    meta = {
        "case_id": case_id,
        "display_id": display_id,
        "time_sec": time_sec,
        "zml_keyframe_id": keyframe_id,
        "zml_wall_updated_at": (hit or {}).get("updated_at", ""),
        "zml_wall_bands": n_bands,
        "zml_pixel_readout": (hit or {}).get("readout") or {},
        "frame_path": relpath(image_path),
        "lesion_polygon": lesion,
        "lesion_source": lesion_source,
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
    (dest / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR) if image_path.exists() else None
    if image is not None:
        preview = image.copy()
        if len(lesion) >= 3:
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
    parser.add_argument("--state", default=str(PUBLIC_PULL / "doctor_case_state.json" if (PUBLIC_PULL / "doctor_case_state.json").exists() else LIVE_STATE))
    parser.add_argument("--masks", default=str(PUBLIC_PULL / "mask_overrides.json" if (PUBLIC_PULL / "mask_overrides.json").exists() else LIVE_MASKS))
    args = parser.parse_args()
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    tokens = [item.strip() for item in str(args.cases).split(",") if item.strip()]
    zml = load_json(ZML_STATE, {"entries": []})
    live = load_json(Path(args.state), {"entries": []})
    masks = load_json(Path(args.masks), {})
    public_lumen = PUBLIC_PULL / "lumen_overrides.json"
    lumen_map = load_json(public_lumen if public_lumen.exists() else LUMEN_BACKUP, {})
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
            f"{meta['display_id']} {meta['case_id']} t={meta['time_sec']} "
            f"wall={meta['wall_source']}:{len(meta['wall_polygon'])} "
            f"lesion={meta.get('lesion_source') or '-'}:{len(meta['lesion_polygon'])} "
            f"skip={meta['skip_reason'] or '-'}",
            flush=True,
        )
    manifest = out_root / "manifest.csv"
    fields = [
        "display_id", "case_id", "pT_ref", "site", "time_sec", "wall_source",
        "lesion_source", "zml_keyframe_id", "cavity_side_source", "brush_radius",
        "skip_reason", "frame_path",
    ]
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for meta in rows:
            writer.writerow({key: meta.get(key, "") for key in fields})
    readme = (
        "# wall_layer_fixtures v1\n\n"
        "Prefers public ZML wall strokes. Frame is extracted at the paint time, "
        "not the old frozen keyframe. Pair a lesion only if it sits on the same "
        "frame, or within 0.30 s. Distant keyframes stay unused.\n"
    )
    (out_root / "README.md").write_text(readme, encoding="utf-8")
    print(f"wrote {manifest}", flush=True)
    return 0 if all(not row.get("skip_reason") for row in rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
