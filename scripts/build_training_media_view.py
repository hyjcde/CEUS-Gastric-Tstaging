#!/usr/bin/env python3
"""Build modality-grouped training media view (symlinks, no copies).

Default: **exclude loop_still** video links (静图循环不算视频).
Images/masks for those samples are still linked; only the fake MP4 is skipped.

Layout
------
dataset/training_views/
  t_staging/                 # 恶性 T 分期（胃癌）
    by_modality/
      internal/<year>/{images,videos_real,roi_masks,annotations,overlays}/
      prospective/2025/...
      external/<hospital>/...
    by_patient/
      <cohort>/<year_or_hospital>/<patient_key>/{images,videos,roi_masks,annotations,overlays,pathology.json}
    pathology/
      labels_by_patient.csv
      labels_by_sample.csv
  benign_malignant/          # 良恶性 / 胃炎外部（与 T 分期分开）
    by_modality/
      external/<hospital>/{images,videos,roi_masks,annotations,overlays}/
    pathology/
      clinical_records.csv -> ../../gastritis_external/clinical_records.csv
  README.md
  inventory.json

Source of truth for pixels remains dataset/**/crop_ui and gastritis_external.
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
DEFAULT_OUT = PROJECT_ROOT / "dataset" / "training_views"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_name(text: str, max_len: int = 120) -> str:
    """Filesystem-safe name that keeps trailing '_' distinct (e.g. id 1560 vs 1560_)."""
    s = str(text or "unknown").strip()
    s = s.replace("::", "--")
    for ch in ["/", "\\", ":", "*", "?", '"', "<", ">", "|", "\0"]:
        s = s.replace(ch, "_")
    # collapse only internal runs of underscores; keep edges meaningful
    while "__" in s:
        s = s.replace("__", "_")
    s = s.strip(".") or "unknown"
    return s[:max_len]


def ensure_link(target: Path, link: Path) -> bool:
    """Create relative symlink link -> target. Return True if linked."""
    if not target.exists():
        return False
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        if link.is_symlink() and link.resolve() == target.resolve():
            return True
        link.unlink()
    rel = os.path.relpath(target, start=link.parent)
    link.symlink_to(rel)
    return True


def truthy(x: object) -> bool:
    return str(x or "").strip().lower() in {"1", "true", "yes", "y"}


def tstaging_bucket(row: dict) -> tuple[str, str]:
    """Return (cohort_dir, year_or_hospital)."""
    cohort = (row.get("cohort") or "internal").strip()
    year = (row.get("year") or "").strip()
    hospital = (row.get("standard_hospital_name") or row.get("center_id") or "unknown").strip()
    if cohort == "prospective":
        return "prospective", year or "2025"
    if cohort == "external":
        # external year field is often Chinese folder alias; use hospital
        return "external", safe_name(hospital)
    # internal
    if year in {"2018", "2019", "2020_2023", "2024", "2025"}:
        return "internal", year
    return "internal", safe_name(year or "unknown_year")


def build_tstaging(out: Path, root: Path, *, include_loop: bool = False) -> dict:
    samp_path = root / "data/registry/patient_media_sample_index.csv"
    preg_path = root / "data/registry/patient_media_registry.csv"
    samples = list(csv.DictReader(samp_path.open(encoding="utf-8-sig")))
    patients = {
        r["patient_id"]: r for r in csv.DictReader(preg_path.open(encoding="utf-8-sig"))
    }

    base = out / "t_staging"
    by_mod = base / "by_modality"
    by_pat = base / "by_patient"
    pathol = base / "pathology"
    pathol.mkdir(parents=True, exist_ok=True)

    stats = Counter()
    sample_label_rows = []
    linked_patients: set[str] = set()

    for r in samples:
        img = r.get("image_path") or ""
        roi = r.get("roi_mask_path") or ""
        ann = r.get("annotation_path") or ""
        vid = r.get("crop_video_path") or ""
        if not img:
            continue
        # skip template leftover
        if "{center}" in img or "{center}" in vid:
            stats["skipped_center_placeholder"] += 1
            continue

        cohort_dir, bucket = tstaging_bucket(r)
        mod_root = by_mod / cohort_dir / bucket
        mode = r.get("video_mode") or ""
        skip_loop_video = mode == "loop_still" and not include_loop
        if skip_loop_video:
            stats["skipped_loop_still_video"] += 1
            vid_dir = None
        elif mode == "cached":
            vid_dir = "videos_real"
        elif mode == "loop_still":
            vid_dir = "videos_loop"
        else:
            vid_dir = "videos_other" if vid else None

        stem = Path(img).stem
        # modality flat dirs
        pairs = [
            (img, mod_root / "images" / Path(img).name),
            (roi, mod_root / "roi_masks" / Path(roi).name if roi else None),
            (ann, mod_root / "annotations" / Path(ann).name if ann else None),
        ]
        if vid and vid_dir:
            pairs.append((vid, mod_root / vid_dir / Path(vid).name))
        # overlay beside images
        if img:
            ov = (root / img).parent.parent / "overlays" / f"{stem}_overlay.jpg"
            if ov.exists():
                pairs.append((str(ov.relative_to(root)), mod_root / "overlays" / ov.name))

        for src, dst in pairs:
            if not src or dst is None:
                continue
            if ensure_link(root / src, dst):
                stats[f"link_{dst.parent.name}"] += 1
            else:
                stats[f"miss_{dst.parent.name}"] += 1

        # by_patient tree — key by patient_id so DICOM1/DICOM2 views stay under one patient
        pid = r.get("patient_id") or "unknown"
        pkey = safe_name(pid)
        pref = by_pat / cohort_dir / bucket / pkey
        for src, sub, name in [
            (img, "images", Path(img).name),
            (roi, "roi_masks", Path(roi).name if roi else ""),
            (ann, "annotations", Path(ann).name if ann else ""),
            (vid if not skip_loop_video else "", "videos", Path(vid).name if vid and not skip_loop_video else ""),
        ]:
            if not src or not name:
                continue
            if ensure_link(root / src, pref / sub / name):
                stats["patient_links"] += 1

        meta = patients.get(pid, {})
        pathol_path = pref / "pathology.json"
        prev = {}
        if pathol_path.exists():
            try:
                prev = json.loads(pathol_path.read_text(encoding="utf-8"))
            except Exception:
                prev = {}
        sample_ids = list(prev.get("sample_ids") or [])
        sid = r.get("sample_id")
        if sid and sid not in sample_ids:
            sample_ids.append(sid)
        canon_keys = list(prev.get("canonical_patient_keys") or [])
        ck = r.get("canonical_patient_key")
        if ck and ck not in canon_keys:
            canon_keys.append(ck)
        pathol_json = {
            "patient_id": pid,
            "canonical_patient_key": meta.get("canonical_patient_key") or (canon_keys[0] if canon_keys else ""),
            "canonical_patient_keys": canon_keys,
            "sample_ids": sample_ids,
            "sample_id": sample_ids[0] if sample_ids else r.get("sample_id"),
            "cohort": r.get("cohort"),
            "year": r.get("year"),
            "hospital": r.get("standard_hospital_name"),
            "t_stage": meta.get("t_stage") or r.get("t_stage") or "",
            "class_label": meta.get("class_label") or r.get("class_label") or "",
            "clinical_patient_uid": meta.get("clinical_patient_uid") or r.get("clinical_patient_uid") or "",
            "split": meta.get("split") or r.get("split") or "",
            "video_modes": sorted(
                set((prev.get("video_modes") or []) + ([mode] if mode else []))
            ),
            "has_clinical": truthy(meta.get("has_clinical")),
            "usable_for_training": truthy(meta.get("usable_for_training")),
        }
        pathol_path.write_text(json.dumps(pathol_json, ensure_ascii=False, indent=2), encoding="utf-8")

        sample_label_rows.append(
            {
                "sample_id": r.get("sample_id"),
                "patient_id": pid,
                "cohort_dir": cohort_dir,
                "bucket": bucket,
                "t_stage": pathol_json["t_stage"],
                "class_label": pathol_json["class_label"],
                "video_mode": mode,
                "image_path": img,
                "crop_video_path": vid,
                "roi_mask_path": roi,
                "annotation_path": ann,
                "view_images": str((mod_root / "images" / Path(img).name).relative_to(out)),
                "view_video": (
                    str((mod_root / vid_dir / Path(vid).name).relative_to(out))
                    if vid and vid_dir
                    else ""
                ),
                "usable_for_training": int(pathol_json["usable_for_training"]),
            }
        )
        linked_patients.add(pid)
        stats["samples"] += 1

    # pathology tables
    with (pathol / "labels_by_sample.csv").open("w", encoding="utf-8", newline="") as f:
        fields = list(sample_label_rows[0].keys()) if sample_label_rows else ["sample_id"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(sample_label_rows)

    patient_rows = []
    for pid, meta in sorted(patients.items()):
        cohort = meta.get("cohort") or ""
        # bucket guess from samples
        items = [r for r in samples if r.get("patient_id") == pid]
        if items:
            cdir, bucket = tstaging_bucket(items[0])
        else:
            cdir, bucket = (cohort or "internal"), "unknown"
        patient_rows.append(
            {
                "patient_id": pid,
                "canonical_patient_key": meta.get("canonical_patient_key"),
                "cohort_dir": cdir,
                "bucket": bucket,
                "hospital": meta.get("standard_hospital_name"),
                "t_stage": meta.get("t_stage") or "",
                "class_label": meta.get("class_label") or "",
                "clinical_patient_uid": meta.get("clinical_patient_uid") or "",
                "split": meta.get("split") or "",
                "has_clinical": int(truthy(meta.get("has_clinical"))),
                "has_real_video": int(truthy(meta.get("has_real_video"))),
                "usable_for_training": int(truthy(meta.get("usable_for_training"))),
                "image_count": meta.get("image_count"),
                "real_video_count": meta.get("real_video_count"),
                "loop_still_count": meta.get("loop_still_count"),
                "patient_dir": str((by_pat / cdir / bucket / safe_name(pid)).relative_to(out)),
            }
        )

    with (pathol / "labels_by_patient.csv").open("w", encoding="utf-8", newline="") as f:
        fields = list(patient_rows[0].keys()) if patient_rows else ["patient_id"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(patient_rows)

    # convenience: only patients with image+video+pathology(T)
    complete = [
        p
        for p in patient_rows
        if p["usable_for_training"] and p["has_clinical"] and int(p.get("image_count") or 0) > 0
    ]
    with (pathol / "patients_image_video_pathology.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(complete[0].keys()) if complete else ["patient_id"])
        w.writeheader()
        w.writerows(complete)

    return {
        "task": "t_staging",
        "samples_linked": stats["samples"],
        "patients_in_registry": len(patients),
        "patients_with_media_links": len(linked_patients),
        "patients_image_video_pathology": len(complete),
        "exclude_loop_still_video": not include_loop,
        "skipped_loop_still_video": int(stats.get("skipped_loop_still_video") or 0),
        "link_counts": {k: v for k, v in stats.items() if k.startswith("link_") or k == "patient_links"},
        "miss_counts": {k: v for k, v in stats.items() if k.startswith("miss_")},
    }


def build_benign_malignant(out: Path, root: Path) -> dict:
    """Gastritis external as benign_malignant layout (separate from T-stage)."""
    ge = root / "dataset/gastritis_external"
    base = out / "benign_malignant"
    by_mod = base / "by_modality" / "external"
    pathol = base / "pathology"
    pathol.mkdir(parents=True, exist_ok=True)

    stats = Counter()
    manif = ge / "manifest.csv"
    if not manif.exists():
        return {"task": "benign_malignant", "error": "gastritis manifest missing"}

    rows = list(csv.DictReader(manif.open(encoding="utf-8-sig")))
    # expected columns vary — inspect flexibly
    for r in rows:
        center = safe_name(r.get("center") or r.get("hospital") or "unknown")
        # find crop_ui image path fields
        img = (
            r.get("processed_crop_ui_image")
            or r.get("crop_ui_image")
            or r.get("image_path")
            or r.get("processed_image")
            or ""
        )
        if not img:
            for key in r:
                val = r.get(key) or ""
                if "crop_ui" in val.replace("\\", "/") and "/images/" in val.replace("\\", "/") and val.lower().endswith(
                    (".jpg", ".jpeg", ".png")
                ):
                    img = val
                    break
        if not img:
            # reconstruct from center + filename if present
            fn = r.get("filename") or r.get("image_name") or ""
            cand = ge / "processed_images" / (r.get("center") or center) / "crop_ui" / "images" / fn
            if cand.exists():
                img = str(cand.relative_to(root))
        if not img:
            stats["skip_no_image"] += 1
            continue
        img_p = root / img if not Path(img).is_absolute() else Path(img)
        if not img_p.exists():
            # try relative to gastritis
            alt = ge / img
            if alt.exists():
                img_p = alt
                img = str(alt.relative_to(root))
            else:
                stats["miss_image"] += 1
                continue

        stem = img_p.stem
        crop_ui = img_p.parent.parent  # .../crop_ui
        mod = by_mod / center
        ensure_link(img_p, mod / "images" / img_p.name)
        stats["link_images"] += 1
        for sub, suffix in [
            ("roi_masks", ".png"),
            ("annotations", ".json"),
            ("overlays", "_overlay.jpg"),
        ]:
            if sub == "overlays":
                src = crop_ui / sub / f"{stem}_overlay.jpg"
            elif sub == "annotations":
                src = crop_ui / sub / f"{stem}.json"
            else:
                src = crop_ui / sub / f"{stem}.png"
                if not src.exists():
                    src = crop_ui / sub / f"{stem}.jpg"
            if src.exists():
                ensure_link(src, mod / sub / src.name)
                stats[f"link_{sub}"] += 1

    # videos from video_manifest
    vm = ge / "video_manifest.csv"
    if vm.exists():
        for r in csv.DictReader(vm.open(encoding="utf-8-sig")):
            center = safe_name(r.get("center") or "unknown")
            vp = r.get("video_path") or ""
            if not vp:
                continue
            src = root / vp if (root / vp).exists() else ge / vp
            if not src.exists():
                # path may already be absolute under ge
                src = Path(vp)
            if not src.exists():
                stats["miss_video"] += 1
                continue
            # disambiguate duplicate basenames from 图片/视频 twin folders
            out_name = src.name
            link = by_mod / center / "videos" / out_name
            if link.exists() or link.is_symlink():
                parent_tag = safe_name(src.parent.name)
                out_name = f"{parent_tag}__{src.name}"
                link = by_mod / center / "videos" / out_name
            if ensure_link(src, link):
                stats["link_videos"] += 1
            else:
                stats["miss_video"] += 1

    # pathology symlink + compact export
    clin = ge / "clinical_records.csv"
    if clin.exists():
        ensure_link(clin, pathol / "clinical_records.csv")
        # also copy a slim train table
        slim = []
        for r in csv.DictReader(clin.open(encoding="utf-8-sig")):
            slim.append(
                {
                    "center": r.get("center"),
                    "patient_id": r.get("patient_id"),
                    "patient_key": r.get("patient_key"),
                    "diagnosis": r.get("diagnosis"),
                    "pathology": r.get("pathology"),
                    "ultrasound_result": r.get("ultrasound_result"),
                    "gastroscopy": r.get("gastroscopy"),
                    "task": "benign_malignant",
                    "scope": "external",
                }
            )
        with (pathol / "labels_by_patient.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(slim[0].keys()) if slim else ["patient_id"])
            w.writeheader()
            w.writerows(slim)

    return {
        "task": "benign_malignant",
        "centers": sorted({p.name for p in by_mod.iterdir()}) if by_mod.exists() else [],
        "stats": dict(stats),
        "note": "Separated from t_staging; gastritis/inflammation, not T1–T4+",
    }


def write_readme(out: Path, inv: dict) -> None:
    text = f"""# 训练媒体视图（软链，不拷贝原片）

生成时间：{inv.get("created_at")}

```bash
python3 scripts/build_training_media_view.py
# 重建前清空：
python3 scripts/build_training_media_view.py --clean
```

## 设计（在已有 crop_ui 之上）

原数据已经按中心/年份整理在 `dataset/**/crop_ui/`。  
本视图只做 **训练友好入口**：

1. **任务分开**
   - `t_staging/`：恶性胃癌 T 分期（有图 / 视频 / mask / 病理分期标签）
   - `benign_malignant/`：良恶性/胃炎外部（与 T 分期拆开，禁止混进 T1–T4+）
2. **内外部 × 年份/中心**
   - T 分期：`internal/2018|2019|2020_2023|2024`、`prospective/2025`、`external/<医院>`
   - 良恶性：`external/<医院>`
3. **模态分目录（方便 DataLoader）**
   - `images/` · `videos_real/`（**仅真 cine**）· `roi_masks/` · `annotations/` · `overlays/`
   - **默认不链 `videos_loop`**（`loop_still` 静图循环已排除；需要时加 `--include-loop`）
4. **按病人**
   - `t_staging/by_patient/<cohort>/<bucket>/<patient_key>/…` + `pathology.json`（`videos/` 仅真 cine）
5. **病理/标签表**
   - `t_staging/pathology/labels_by_patient.csv`
   - `t_staging/pathology/patients_image_video_pathology.csv`（图+可用临床）
   - `benign_malignant/pathology/clinical_records.csv`

## 推荐训练读法

| 任务 | 模态目录 | 标签 |
|------|----------|------|
| T 分期图像 | `t_staging/by_modality/**/images` + `roi_masks` | `pathology/labels_by_sample.csv` |
| T 分期视频 | **`t_staging_real_cine/`** 或 `t_staging/**/videos_real` | 仅 `video_mode=cached` |
| 按病人 batch | `t_staging/by_patient/...` / `t_staging_real_cine/by_patient/...` | `pathology.json` |
| 良恶性 | `benign_malignant/by_modality/external/<医院>/` | `pathology/labels_by_patient.csv` |

硬规则：split 必须按 **patient_id**；**不要用 loop_still**。

## 库存摘要

```json
{json.dumps(inv, ensure_ascii=False, indent=2)}
```

物理 SSOT 仍是 `dataset/internal|external|gastritis_external`；本目录可随时 `--clean` 重建。
"""
    (out / "README.md").write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--clean", action="store_true", help="Remove existing training_views before rebuild")
    parser.add_argument("--skip-benign", action="store_true")
    parser.add_argument(
        "--include-loop",
        action="store_true",
        help="Also symlink loop_still MP4s under videos_loop/ (default: exclude)",
    )
    args = parser.parse_args()

    root = PROJECT_ROOT
    out = args.out if args.out.is_absolute() else root / args.out
    if args.clean and out.exists():
        # Keep t_staging_real_cine/ (built by build_real_cine_aligned_view.py).
        for name in ("t_staging", "benign_malignant", "README.md", "inventory.json", "COMPLETENESS.md"):
            p = out / name
            if p.is_dir():
                print(f"[clean] {p}")
                shutil.rmtree(p)
            elif p.is_file():
                p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    print(f"[build] t_staging (include_loop={args.include_loop}) ...")
    ts = build_tstaging(out, root, include_loop=args.include_loop)
    print(json.dumps(ts, ensure_ascii=False, indent=2))

    bm = {"skipped": True}
    if not args.skip_benign:
        print("[build] benign_malignant ...")
        bm = build_benign_malignant(out, root)
        print(json.dumps(bm, ensure_ascii=False, indent=2))

    inv = {
        "created_at": utc_now(),
        "out": str(out.relative_to(root)),
        "exclude_loop_still_video": not args.include_loop,
        "t_staging": ts,
        "benign_malignant": bm,
        "source": {
            "t_staging_media": "dataset/**/crop_ui + data/registry/patient_media_*.csv",
            "benign_malignant": "dataset/gastritis_external",
        },
    }
    (out / "inventory.json").write_text(json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8")
    write_readme(out, inv)
    print(f"[ok] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
