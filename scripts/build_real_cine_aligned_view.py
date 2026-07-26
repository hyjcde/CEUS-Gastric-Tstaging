#!/usr/bin/env python3
"""Build clearly aligned REAL-CINE (video_mode=cached) training view.

Outputs
-------
dataset/training_views/t_staging_real_cine/
  by_modality/{internal|prospective|external}/<bucket>/{images,videos,roi_masks,annotations,overlays}/
  by_patient/<cohort>/<bucket>/<patient_id>/{images,videos,roi_masks,annotations,overlays,pathology.json}
  alignment/
    samples_real_cine.csv              # every cached sample, paths + labels
    patients_real_cine.csv             # one row per patient with real cine
    patients_aligned_supervised.csv    # real cine + T/pathology label (train-ready)
    patients_real_cine_unlabeled.csv   # real cine but missing T label
  README.md
  inventory.json

Only `video_mode=cached` is included. loop_still is excluded.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = PROJECT_ROOT / "dataset" / "training_views" / "t_staging_real_cine"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_name(text: str, max_len: int = 120) -> str:
    s = str(text or "unknown").strip().replace("::", "--")
    for ch in ["/", "\\", ":", "*", "?", '"', "<", ">", "|", "\0"]:
        s = s.replace(ch, "_")
    while "__" in s:
        s = s.replace("__", "_")
    return (s.strip(".") or "unknown")[:max_len]


def truthy(x: object) -> bool:
    return str(x or "").strip().lower() in {"1", "true", "yes", "y"}


def ensure_link(target: Path, link: Path) -> bool:
    if not target.exists():
        return False
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        if link.is_symlink() and link.resolve() == target.resolve():
            return True
        link.unlink()
    link.symlink_to(os.path.relpath(target, start=link.parent))
    return True


def bucket_for(row: dict) -> tuple[str, str]:
    cohort = (row.get("cohort") or "internal").strip()
    year = (row.get("year") or "").strip()
    hospital = (row.get("standard_hospital_name") or row.get("center_id") or "unknown").strip()
    if cohort == "prospective":
        return "prospective", year or "2025"
    if cohort == "external":
        return "external", safe_name(hospital)
    if year in {"2018", "2019", "2020_2023", "2024", "2025"}:
        return "internal", year
    return "internal", safe_name(year or "unknown_year")


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = fields or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--clean", action="store_true")
    args = ap.parse_args()

    root = PROJECT_ROOT
    out = args.out if args.out.is_absolute() else root / args.out
    if args.clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    samp = list(
        csv.DictReader((root / "data/registry/patient_media_sample_index.csv").open(encoding="utf-8-sig"))
    )
    preg = {
        r["patient_id"]: r
        for r in csv.DictReader((root / "data/registry/patient_media_registry.csv").open(encoding="utf-8-sig"))
    }

    cached = [r for r in samp if r.get("video_mode") == "cached" and "{center}" not in (r.get("crop_video_path") or "")]
    print(f"[real-cine] cached samples: {len(cached)}")

    by_mod = out / "by_modality"
    by_pat = out / "by_patient"
    align = out / "alignment"
    align.mkdir(parents=True, exist_ok=True)

    sample_rows: list[dict] = []
    stats = Counter()
    by_patient_items: dict[str, list[dict]] = defaultdict(list)

    for r in cached:
        img = r.get("image_path") or ""
        roi = r.get("roi_mask_path") or ""
        ann = r.get("annotation_path") or ""
        vid = r.get("crop_video_path") or ""
        raw = r.get("raw_video_path") or ""
        if not img or not vid:
            stats["skip_missing_path_field"] += 1
            continue
        img_p, vid_p = root / img, root / vid
        if not img_p.exists() or not vid_p.exists():
            stats["skip_missing_file"] += 1
            continue

        cohort_dir, bucket = bucket_for(r)
        mod = by_mod / cohort_dir / bucket
        stem = Path(img).stem

        pairs = [
            (img_p, mod / "images" / img_p.name),
            (vid_p, mod / "videos" / vid_p.name),
        ]
        if roi and (root / roi).exists():
            pairs.append((root / roi, mod / "roi_masks" / Path(roi).name))
        if ann and (root / ann).exists():
            pairs.append((root / ann, mod / "annotations" / Path(ann).name))
        ov = img_p.parent.parent / "overlays" / f"{stem}_overlay.jpg"
        if ov.exists():
            pairs.append((ov, mod / "overlays" / ov.name))

        for src, dst in pairs:
            if ensure_link(src, dst):
                stats[f"link_{dst.parent.name}"] += 1

        pid = r.get("patient_id") or "unknown"
        pref = by_pat / cohort_dir / bucket / safe_name(pid)
        for src, sub, name in [
            (img_p, "images", img_p.name),
            (vid_p, "videos", vid_p.name),
            (root / roi if roi else None, "roi_masks", Path(roi).name if roi else ""),
            (root / ann if ann else None, "annotations", Path(ann).name if ann else ""),
        ]:
            if src is None or not name:
                continue
            if ensure_link(src, pref / sub / name):
                stats["patient_links"] += 1
        if ov.exists():
            ensure_link(ov, pref / "overlays" / ov.name)

        meta = preg.get(pid, {})
        t_stage = (meta.get("t_stage") or r.get("t_stage") or "").strip()
        class_label = (meta.get("class_label") or r.get("class_label") or "").strip()
        aligned = bool(t_stage) and truthy(meta.get("usable_for_training"))

        sample_row = {
            "sample_id": r.get("sample_id"),
            "patient_id": pid,
            "canonical_patient_key": r.get("canonical_patient_key"),
            "cohort": r.get("cohort"),
            "cohort_dir": cohort_dir,
            "bucket": bucket,
            "year": r.get("year"),
            "hospital": r.get("standard_hospital_name") or meta.get("standard_hospital_name"),
            "t_stage": t_stage,
            "class_label": class_label,
            "split": meta.get("split") or r.get("split") or "",
            "video_mode": "cached",
            "video_match_status": r.get("video_match_status") or "",
            "aligned_supervised": int(aligned),
            "image_path": img,
            "crop_video_path": vid,
            "raw_video_path": raw,
            "roi_mask_path": roi,
            "annotation_path": ann,
            "overlay_path": str(ov.relative_to(root)) if ov.exists() else "",
            "view_image": str((mod / "images" / img_p.name).relative_to(out)),
            "view_video": str((mod / "videos" / vid_p.name).relative_to(out)),
            "patient_dir": str(pref.relative_to(out)),
        }
        sample_rows.append(sample_row)
        by_patient_items[pid].append(sample_row)

        # pathology.json (merge samples)
        pathol_path = pref / "pathology.json"
        prev = {}
        if pathol_path.exists():
            try:
                prev = json.loads(pathol_path.read_text(encoding="utf-8"))
            except Exception:
                prev = {}
        sids = list(prev.get("sample_ids") or [])
        if sample_row["sample_id"] not in sids:
            sids.append(sample_row["sample_id"])
        pathol_path.write_text(
            json.dumps(
                {
                    "patient_id": pid,
                    "canonical_patient_key": meta.get("canonical_patient_key") or r.get("canonical_patient_key"),
                    "cohort": cohort_dir,
                    "bucket": bucket,
                    "hospital": sample_row["hospital"],
                    "t_stage": t_stage,
                    "class_label": class_label,
                    "clinical_patient_uid": meta.get("clinical_patient_uid") or "",
                    "split": sample_row["split"],
                    "aligned_supervised": aligned,
                    "n_real_cine_clips": len(sids),
                    "sample_ids": sids,
                    "video_mode": "cached",
                    "has_clinical": truthy(meta.get("has_clinical")),
                    "usable_for_training": truthy(meta.get("usable_for_training")),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    # patient alignment tables
    patient_rows = []
    for pid, items in sorted(by_patient_items.items()):
        meta = preg.get(pid, {})
        t_stage = (meta.get("t_stage") or items[0].get("t_stage") or "").strip()
        aligned = bool(t_stage) and truthy(meta.get("usable_for_training"))
        patient_rows.append(
            {
                "patient_id": pid,
                "canonical_patient_key": meta.get("canonical_patient_key") or items[0].get("canonical_patient_key"),
                "cohort": items[0]["cohort"],
                "cohort_dir": items[0]["cohort_dir"],
                "bucket": items[0]["bucket"],
                "hospital": items[0]["hospital"],
                "t_stage": t_stage,
                "class_label": meta.get("class_label") or items[0].get("class_label") or "",
                "split": meta.get("split") or items[0].get("split") or "",
                "n_real_cine_clips": len(items),
                "n_raw_plus_crop": sum(1 for x in items if x.get("video_match_status") == "raw+crop"),
                "aligned_supervised": int(aligned),
                "has_clinical": int(truthy(meta.get("has_clinical"))),
                "primary_image": items[0]["image_path"],
                "primary_video": items[0]["crop_video_path"],
                "primary_roi": items[0]["roi_mask_path"],
                "patient_dir": items[0]["patient_dir"],
                "sample_ids": "|".join(x["sample_id"] for x in items),
            }
        )

    supervised = [r for r in patient_rows if r["aligned_supervised"]]
    unlabeled = [r for r in patient_rows if not r["aligned_supervised"]]
    supervised_samples = [r for r in sample_rows if r["aligned_supervised"]]

    write_csv(align / "samples_real_cine.csv", sample_rows)
    write_csv(align / "samples_aligned_supervised.csv", supervised_samples)
    write_csv(align / "patients_real_cine.csv", patient_rows)
    write_csv(align / "patients_aligned_supervised.csv", supervised)
    write_csv(align / "patients_real_cine_unlabeled.csv", unlabeled)

    inv = {
        "created_at": utc_now(),
        "definition": "video_mode=cached only (true cine crop). loop_still excluded.",
        "samples_real_cine": len(sample_rows),
        "patients_real_cine": len(patient_rows),
        "patients_aligned_supervised": len(supervised),
        "patients_real_cine_unlabeled": len(unlabeled),
        "samples_aligned_supervised": len(supervised_samples),
        "by_cohort_supervised_patients": dict(Counter(r["cohort_dir"] for r in supervised)),
        "by_cohort_unlabeled_patients": dict(Counter(r["cohort_dir"] for r in unlabeled)),
        "link_stats": {k: v for k, v in stats.items()},
        "alignment_rule": {
            "real_cine": "patient_media_sample_index.video_mode == cached",
            "supervised": "has t_stage AND usable_for_training AND image+crop_video+roi on disk",
            "split": "ALWAYS by patient_id",
        },
    }
    (out / "inventory.json").write_text(json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = f"""# T 分期 · 真视频（real cine）对齐视图

生成：`python3 scripts/build_real_cine_aligned_view.py --clean`

## 定义

- **只要真视频**：`video_mode=cached`（`videos/` 目录）
- **不要** `loop_still`（静图循环）
- **对齐清楚**：
  - 样本级：`alignment/samples_real_cine.csv`
  - 病人级：`alignment/patients_real_cine.csv`
  - **可监督训练（图+真视频+T病理）**：`patients_aligned_supervised.csv` / `samples_aligned_supervised.csv`
  - 有真视频但缺 T 标签：`patients_real_cine_unlabeled.csv`

## 规模

| 集合 | 数量 |
|------|-----:|
| 真视频样本 | {len(sample_rows)} |
| 有真视频的病人 | {len(patient_rows)} |
| **已对齐可训练**（有 T） | **{len(supervised)} 人 / {len(supervised_samples)} 样本** |
| 真视频但无 T 标签 | {len(unlabeled)} 人 |

监督病人按桶：`{dict(Counter(r['cohort_dir'] for r in supervised))}`

## 目录

```text
by_modality/<internal|prospective|external>/<年或医院>/
  images/  videos/  roi_masks/  annotations/  overlays/
by_patient/<cohort>/<bucket>/<patient_id>/
  images/ videos/ roi_masks/ annotations/ overlays/ pathology.json
alignment/*.csv
```

## 训练怎么读

1. 病人列表：`alignment/patients_aligned_supervised.csv`
2. 样本列表：`alignment/samples_aligned_supervised.csv`
3. 划分：**按 patient_id**
4. 视频路径列：`crop_video_path` 或视图内 `view_video`

未标注的 627 名真视频病人不要当 T 分期监督；可另做标注队列。
"""
    (out / "README.md").write_text(readme, encoding="utf-8")
    print(json.dumps(inv, ensure_ascii=False, indent=2))
    print(f"[ok] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
