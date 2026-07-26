#!/usr/bin/env python3
"""Build patient-centric training view from patient_media registries.

Does not copy/move media. Writes data/registry/patient_training_view/.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "data/registry/patient_training_view"


def truthy(x: object) -> bool:
    return str(x or "").strip().lower() in {"1", "true", "yes", "y"}


def exists(root: Path, rel: str) -> bool:
    return bool(rel) and (root / rel).exists()


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    root = PROJECT_ROOT
    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    samp = list(
        csv.DictReader((root / "data/registry/patient_media_sample_index.csv").open(encoding="utf-8-sig"))
    )
    preg = {
        r["patient_id"]: r
        for r in csv.DictReader((root / "data/registry/patient_media_registry.csv").open(encoding="utf-8-sig"))
    }

    enriched: list[dict] = []
    for r in samp:
        img = r.get("image_path") or ""
        roi = r.get("roi_mask_path") or ""
        ann = r.get("annotation_path") or ""
        vid = r.get("crop_video_path") or ""
        ov = ""
        if img:
            stem = Path(img).stem
            cand = (root / img).parent.parent / "overlays" / f"{stem}_overlay.jpg"
            if cand.exists():
                ov = str(cand.relative_to(root))
        meta = preg.get(r.get("patient_id") or "", {})
        row = dict(r)
        # Sample index can miss T on some clips; inherit patient registry labels.
        row["t_stage"] = (meta.get("t_stage") or r.get("t_stage") or "").strip()
        row["class_label"] = (meta.get("class_label") or r.get("class_label") or "").strip()
        row["usable_for_training"] = meta.get("usable_for_training") or r.get("usable_for_training") or ""
        row["overlay_path_resolved"] = ov
        row["paths_ok"] = int(exists(root, img) and exists(root, roi) and exists(root, ann) and exists(root, vid))
        row["is_real_cine"] = int(r.get("video_mode") == "cached")
        row["is_loop_still"] = int(r.get("video_mode") == "loop_still")
        row["usable"] = int(truthy(row.get("usable_for_training")))
        enriched.append(row)

    by_p: dict[str, list[dict]] = defaultdict(list)
    for r in enriched:
        by_p[r["patient_id"]].append(r)

    patient_rows: list[dict] = []
    for pid, items in sorted(by_p.items()):
        meta = preg.get(pid, {})
        n_real = sum(r["is_real_cine"] for r in items)
        n_loop = sum(r["is_loop_still"] for r in items)
        n_ok = sum(r["paths_ok"] for r in items)
        splits = sorted({(r.get("split") or "") for r in items if r.get("split")})
        stages = sorted({(r.get("t_stage") or "") for r in items if r.get("t_stage")})
        patient_rows.append(
            {
                "patient_id": pid,
                "canonical_patient_key": meta.get("canonical_patient_key") or items[0].get("canonical_patient_key"),
                "cohort": meta.get("cohort") or items[0].get("cohort"),
                "center_id": meta.get("center_id") or items[0].get("center_id"),
                "standard_hospital_name": meta.get("standard_hospital_name")
                or items[0].get("standard_hospital_name"),
                "registry_split": meta.get("split") or "",
                "sample_splits": "|".join(splits),
                "t_stage": meta.get("t_stage") or ("|".join(stages) if stages else ""),
                "class_label": meta.get("class_label") or "",
                "n_samples": len(items),
                "n_paths_ok": n_ok,
                "n_real_cine": n_real,
                "n_loop_still": n_loop,
                "has_real_cine": int(n_real > 0),
                "usable_for_training": int(truthy(meta.get("usable_for_training"))),
                "has_clinical": int(truthy(meta.get("has_clinical"))),
                "has_mask": int(truthy(meta.get("has_mask"))),
                "primary_image": next((r["image_path"] for r in items if r["paths_ok"]), ""),
                "primary_roi": next((r["roi_mask_path"] for r in items if r["paths_ok"]), ""),
                "primary_video_real": next(
                    (r["crop_video_path"] for r in items if r["is_real_cine"] and r["paths_ok"]), ""
                ),
                "primary_video_any": next((r["crop_video_path"] for r in items if r["paths_ok"]), ""),
                "quality_flags": meta.get("quality_flags") or "",
            }
        )

    cols_sample = [
        "patient_id",
        "canonical_patient_key",
        "sample_id",
        "cohort",
        "year",
        "center_id",
        "split",
        "t_stage",
        "class_label",
        "video_mode",
        "video_match_status",
        "image_path",
        "roi_mask_path",
        "annotation_path",
        "overlay_path_resolved",
        "crop_video_path",
        "raw_video_path",
        "usable",
        "is_real_cine",
        "paths_ok",
        "usable_for_training",
        "quality_flags",
    ]

    img_train = [
        r
        for r in enriched
        if r["usable"] and r["paths_ok"] and (r.get("t_stage") or r.get("class_label"))
    ]
    # Video training: real cine only — loop_still is excluded (not a true ultrasound video).
    vid_train = [r for r in img_train if r["is_real_cine"]]
    excluded_loop = [r for r in img_train if r["is_loop_still"]]
    img_patients = {r["patient_id"] for r in img_train}
    vid_patients = {r["patient_id"] for r in vid_train}

    write_csv(out / "patients.csv", patient_rows, list(patient_rows[0].keys()))
    write_csv(out / "samples_image_train.csv", img_train, cols_sample)
    write_csv(out / "samples_video_real_cine.csv", vid_train, cols_sample)
    write_csv(out / "samples_excluded_loop_still.csv", excluded_loop, cols_sample)
    write_csv(
        out / "patients_image_train.csv",
        [p for p in patient_rows if p["patient_id"] in img_patients],
        list(patient_rows[0].keys()),
    )
    write_csv(
        out / "patients_video_real_cine.csv",
        [p for p in patient_rows if p["patient_id"] in vid_patients],
        list(patient_rows[0].keys()),
    )

    with (out / "patient_bundles.jsonl").open("w", encoding="utf-8") as f:
        for pid, items in sorted(by_p.items()):
            meta = preg.get(pid, {})
            bundle = {
                "patient_id": pid,
                "cohort": meta.get("cohort") or items[0].get("cohort"),
                "t_stage": meta.get("t_stage") or "",
                "split": meta.get("split") or "",
                "usable_for_training": truthy(meta.get("usable_for_training")),
                "samples": [
                    {
                        "sample_id": r["sample_id"],
                        "video_mode": r.get("video_mode"),
                        "image": r.get("image_path"),
                        "roi_mask": r.get("roi_mask_path"),
                        "annotation": r.get("annotation_path"),
                        "overlay": r.get("overlay_path_resolved"),
                        "crop_video": r.get("crop_video_path"),
                        "raw_video": r.get("raw_video_path") or None,
                        "t_stage": r.get("t_stage") or None,
                        "split": r.get("split") or None,
                    }
                    for r in items
                ],
            }
            f.write(json.dumps(bundle, ensure_ascii=False) + "\n")

    still_needs = [
        "DONE: quarantine dataset/external/{center} → dataset/_quarantine/external__center_placeholder/",
        "DONE: real-cine supervised package → dataset/training_views/t_staging_real_cine/",
        "DONE: quarantine all loop_still crop MP4 (7527) → dataset/_quarantine/loop_still/",
        "DONE: prospective/internal mislabeled as test_external* → eval_role remap in t_staging_real_cine/splits/",
        "OPEN: 848 patients lack T/clinical — see t_staging_real_cine/labeling_queue/ for real-cine subset (627)",
        "OPEN: Rebuild joins for Putian/external into legacy region CSVs (path drift; prefer patient_media_*)",
        "KEEP: Prefer Phase0 screened contracts for clean image generalization eval",
        "KEEP: Do not mix gastritis_external into T-stage splits",
    ]

    summary = {
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_registry": "data/registry/patient_media_sample_index.csv + patient_media_registry.csv",
        "patients_total": len(patient_rows),
        "patients_usable_registry": sum(p["usable_for_training"] for p in patient_rows),
        "patients_with_image_train_samples": len(img_patients),
        "patients_with_real_cine_train_samples": len(vid_patients),
        "samples_image_train": len(img_train),
        "samples_video_real_cine": len(vid_train),
        "samples_excluded_loop_still": len(excluded_loop),
        "exclude_loop_still_from_video": True,
        "patients_no_clinical_or_t": sum(1 for p in patient_rows if not p["has_clinical"]),
        "patients_only_loop_still": sum(
            1 for p in patient_rows if p["n_loop_still"] and not p["n_real_cine"]
        ),
        "still_needs_organizing": still_needs,
        "how_to_train": {
            "image_model_sample_csv": str((out / "samples_image_train.csv").relative_to(root)),
            "video_model_sample_csv": str((out / "samples_video_real_cine.csv").relative_to(root)),
            "excluded_loop_still_csv": str((out / "samples_excluded_loop_still.csv").relative_to(root)),
            "patient_table": str((out / "patients.csv").relative_to(root)),
            "patient_bundles_jsonl": str((out / "patient_bundles.jsonl").relative_to(root)),
            "split_rule": "ALWAYS split by patient_id, never by sample_id/image",
            "video_rule": "cached only; loop_still excluded",
        },
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = f"""# 病人级训练视图（logical，不搬像素）

生成时间：{summary['created_at']}

```bash
python3 scripts/build_patient_training_view.py
```

## 怎么用

| 目标 | 读哪个 |
|------|--------|
| 按病人组织 | `patients.csv` / `patient_bundles.jsonl` |
| 图像/分割训练 | `samples_image_train.csv`（{len(img_train)} 样本 / {len(img_patients)} 病人） |
| 视频 cine 训练 | `samples_video_real_cine.csv`（{len(vid_train)} 样本 / {len(vid_patients)} 病人） |
| 已排除 loop | `samples_excluded_loop_still.csv`（{len(excluded_loop)}，**不要当视频**） |

硬规则：train/val/test **按 patient_id 划分**；视频只用 `cached`，不用 `loop_still`。

## 规模

- 病人总计：{len(patient_rows)}
- registry 可训练：{summary['patients_usable_registry']}
- 无临床/T：{summary['patients_no_clinical_or_t']}
- 仅有 loop_still：{summary['patients_only_loop_still']}

## 还需要整理

"""
    for item in still_needs:
        readme += f"- {item}\n"
    readme += "\n物理文件仍在 `dataset/**/crop_ui/`；本目录只做索引。\n"
    (out / "README.md").write_text(readme, encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"[ok] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
