#!/usr/bin/env python3
"""Same-frame A/B for lesion-aware wall clustering.

Arms: live 56x28 M0, full brush k=3, exclude-lesion k=3 at dilate 0/3/5/10,
plus k=2 exclude at d=5.

  python3 scripts/eval_lesion_aware_wall_cluster_v1.py --help
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
    clarify_deepest_echo,
    cluster_brush_band,
    rasterize_polygon,
    to_gray,
)

DEFAULT_FIXTURES = ROOT / "pipeline/data/wall_layer_fixtures/v1"
DEFAULT_OUT = ROOT / "pipeline/experiments/reports/lesion_aware_wall_cluster_v1"
DILATE_LIST = (0, 3, 5, 10)


def load_meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_frame(meta: dict) -> Path:
    frame = Path(str(meta.get("frame_path") or ""))
    if not frame.is_absolute():
        frame = ROOT / frame
    return frame


def run_case(meta: dict) -> dict:
    frame_path = resolve_frame(meta)
    image = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
    if image is None:
        return {
            "case_id": meta.get("case_id"),
            "display_id": meta.get("display_id"),
            "status": "missing_frame",
            "skip_reason": "missing_frame",
        }
    gray = to_gray(image)
    lesion = as_xy(meta.get("lesion_polygon"))
    wall = as_xy(meta.get("wall_polygon"))
    lumen = as_xy(meta.get("lumen_polygon"))
    lesion_mask = rasterize_polygon(gray.shape, lesion)
    brush = float(meta.get("brush_radius") or 8)
    lumen_center = lumen.mean(axis=0) if len(lumen) >= 3 else None
    cavity = str(meta.get("cavity_side_source") or "heuristic")
    live = clarify_deepest_echo(gray, lesion, lumen if len(lumen) else None, wall, brush)
    full = cluster_brush_band(
        gray, wall, lesion_mask,
        brush_radius=brush, k=3, dilate_px=0, exclude_lesion=False,
        lumen_center=lumen_center, lesion_poly=lesion, cavity_side_source=cavity,
    )
    exclude = {}
    for dilate in DILATE_LIST:
        exclude[f"d{dilate}"] = cluster_brush_band(
            gray, wall, lesion_mask,
            brush_radius=brush, k=3, dilate_px=dilate, exclude_lesion=True,
            lumen_center=lumen_center, lesion_poly=lesion, cavity_side_source=cavity,
        )
    exclude_k2 = cluster_brush_band(
        gray, wall, lesion_mask,
        brush_radius=brush, k=2, dilate_px=5, exclude_lesion=True,
        lumen_center=lumen_center, lesion_poly=lesion, cavity_side_source=cavity,
    )
    payload = {
        "case_id": meta.get("case_id"),
        "display_id": meta.get("display_id"),
        "pT_ref": meta.get("pT_ref"),
        "site": meta.get("site"),
        "time_sec": meta.get("time_sec"),
        "wall_source": meta.get("wall_source"),
        "lesion_source": meta.get("lesion_source"),
        "zml_keyframe_id": meta.get("zml_keyframe_id"),
        "zml_pixel_readout": meta.get("zml_pixel_readout") or {},
        "cavity_side_source": full.cavity_side_source,
        "brush_radius": brush,
        "status": "ok",
        "live_m0": {k: v for k, v in live.items() if k not in {"named", "coords"}},
        "full_brush_k3": full.summary(),
        "exclude_k3": {key: arm.summary() for key, arm in exclude.items()},
        "exclude_k2_d5": exclude_k2.summary(),
        "bright_dark_bright": {
            "full_brush_k3": full.bright_dark_bright,
            **{f"exclude_{key}": arm.bright_dark_bright for key, arm in exclude.items()},
        },
        "_arms": {
            "full": full,
            **exclude,
            "live": live,
        },
        "_image": image,
        "_gray": gray,
        "_lesion": lesion,
        "_wall": wall,
        "_lesion_mask": lesion_mask,
    }
    return payload


def write_score_sheet(out_dir: Path, rows: list[dict]) -> None:
    path = out_dir / "doctor_score_sheet.csv"
    fields = [
        "display_id", "case_id", "pT_ref", "wall_source",
        "score_exclude_vs_full_0to3", "notes",
        "live_m0_looks_contaminated", "preferred_dilate_px",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "display_id": row.get("display_id"),
                "case_id": row.get("case_id"),
                "pT_ref": row.get("pT_ref"),
                "wall_source": row.get("wall_source"),
                "score_exclude_vs_full_0to3": "",
                "notes": "",
                "live_m0_looks_contaminated": "",
                "preferred_dilate_px": "",
            })


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate lesion-aware wall clustering A/B.")
    parser.add_argument("--fixtures", default=str(DEFAULT_FIXTURES))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--render", action="store_true", default=True)
    parser.add_argument("--no-render", action="store_false", dest="render")
    args = parser.parse_args()
    fixture_root = Path(args.fixtures)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "per_case").mkdir(exist_ok=True)
    metas = sorted(fixture_root.glob("CASE-*/meta.json"))
    if not metas:
        print(f"no fixtures in {fixture_root}", flush=True)
        return 2
    if args.render:
        from render_lesion_aware_wall_cluster_panel import render_case, render_index
    summaries = []
    rendered = []
    for meta_path in metas:
        meta = load_meta(meta_path)
        result = run_case(meta)
        arms = result.pop("_arms", None)
        image = result.pop("_image", None)
        result.pop("_gray", None)
        lesion = result.pop("_lesion", None)
        wall = result.pop("_wall", None)
        lesion_mask = result.pop("_lesion_mask", None)
        (out_dir / "per_case" / f"{result['case_id']}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        summaries.append(result)
        if args.render and arms and image is not None:
            panel = render_case(out_dir / "panels", result, image, lesion, wall, lesion_mask, arms)
            rendered.append(panel)
        print(
            f"{result.get('display_id')} full_bdb={result.get('bright_dark_bright', {}).get('full_brush_k3')} "
            f"ex_d5={result.get('bright_dark_bright', {}).get('exclude_d5')} "
            f"wall={result.get('wall_source')}",
            flush=True,
        )
    summary = {
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_cases": len(summaries),
        "cases": summaries,
        "note": (
            "Wall strokes are public ZML paints from 2026-08-28. "
            "Pixel readout ticks are workbench hints, not doctor cT. "
            "Does not unlock cT."
        ),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_score_sheet(out_dir, summaries)
    if args.render and rendered:
        render_index(out_dir / "panels", rendered)
    readme = (
        "# lesion_aware_wall_cluster_v1\n\n"
        "Same-frame arms: live 56x28 M0, full brush k=3, exclude-lesion k=3 at "
        "dilate 0/3/5/10. Doctor score sheet is empty until reviewed.\n\n"
        "wall_source zml_keyframe / zml_mask_override is a public ZML stroke. "
        "Pixel readout is a workbench hint, not a doctor continuity answer.\n"
    )
    (out_dir / "README.md").write_text(readme, encoding="utf-8")
    print(f"wrote {out_dir / 'summary.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
