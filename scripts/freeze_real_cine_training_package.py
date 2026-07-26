#!/usr/bin/env python3
"""Freeze real-cine supervised package: clean eval roles, split tables, labeling queue.

Reads dataset/training_views/t_staging_real_cine/alignment/*.csv (from
build_real_cine_aligned_view.py) and writes:

  alignment/patients_with_eval_role.csv
  alignment/samples_with_eval_role.csv
  splits/by_legacy_split/<split>/{patients,samples}.csv
  splits/by_eval_role/<role>/{patients,samples}.csv
  splits/leakage_report.json
  splits/SUMMARY.md
  by_split/<eval_role>/<patient_dir_name>  -> symlink into by_patient/...
  labeling_queue/{README.md,patients.csv,by_hospital/<医院>.csv}

eval_role policy (reporting-safe; does not rewrite registry):
  - prospective + legacy test_external*  -> test_prospective
  - internal + legacy test_external*     -> test_internal_holdout
  - else keep legacy_split

Hard rule: patient_id never appears in more than one eval_role.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VIEW = PROJECT_ROOT / "dataset" / "training_views" / "t_staging_real_cine"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def eval_role(cohort_dir: str, legacy_split: str) -> str:
    c = (cohort_dir or "").strip()
    s = (legacy_split or "").strip()
    if c == "prospective" and s.startswith("test_external"):
        return "test_prospective"
    if c == "internal" and s.startswith("test_external"):
        return "test_internal_holdout"
    return s or "unknown"


def ensure_symlink(target: Path, link: Path) -> bool:
    if not target.exists():
        return False
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        if link.is_symlink() and link.resolve() == target.resolve():
            return True
        if link.is_symlink() or link.is_file():
            link.unlink()
        else:
            return False
    link.symlink_to(os.path.relpath(target, start=link.parent))
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--view", type=Path, default=DEFAULT_VIEW)
    args = ap.parse_args()
    view = args.view if args.view.is_absolute() else PROJECT_ROOT / args.view
    align = view / "alignment"
    if not (align / "patients_aligned_supervised.csv").exists():
        raise SystemExit(
            f"missing {align}/patients_aligned_supervised.csv — run "
            "scripts/build_real_cine_aligned_view.py first"
        )

    patients = list(csv.DictReader((align / "patients_aligned_supervised.csv").open(encoding="utf-8-sig")))
    samples = list(csv.DictReader((align / "samples_aligned_supervised.csv").open(encoding="utf-8-sig")))
    unlabeled = list(csv.DictReader((align / "patients_real_cine_unlabeled.csv").open(encoding="utf-8-sig")))

    # enrich supervised
    for r in patients:
        r["legacy_split"] = (r.get("split") or "").strip()
        r["eval_role"] = eval_role(r.get("cohort_dir") or "", r["legacy_split"])
        notes = []
        if r["cohort_dir"] == "external" and r["legacy_split"] in {"train", "val"}:
            notes.append("external_in_fit_split_legacy")
        if r["legacy_split"] != r["eval_role"]:
            notes.append(f"remapped_from_{r['legacy_split']}")
        r["eval_note"] = "|".join(notes)

    pid_role = {r["patient_id"]: r["eval_role"] for r in patients}
    for r in samples:
        r["legacy_split"] = (r.get("split") or "").strip()
        r["eval_role"] = pid_role.get(r["patient_id"]) or eval_role(r.get("cohort_dir") or "", r["legacy_split"])

    write_csv(align / "patients_with_eval_role.csv", patients)
    write_csv(align / "samples_with_eval_role.csv", samples)

    splits_root = view / "splits"
    by_legacy: dict[str, list[dict]] = defaultdict(list)
    by_role: dict[str, list[dict]] = defaultdict(list)
    for r in patients:
        by_legacy[r["legacy_split"]].append(r)
        by_role[r["eval_role"]].append(r)

    samp_legacy: dict[str, list[dict]] = defaultdict(list)
    samp_role: dict[str, list[dict]] = defaultdict(list)
    for r in samples:
        samp_legacy[r["legacy_split"]].append(r)
        samp_role[r["eval_role"]].append(r)

    for split, rows in sorted(by_legacy.items()):
        write_csv(splits_root / "by_legacy_split" / split / "patients.csv", rows)
        write_csv(splits_root / "by_legacy_split" / split / "samples.csv", samp_legacy.get(split, []))
    for role, rows in sorted(by_role.items()):
        write_csv(splits_root / "by_eval_role" / role / "patients.csv", rows)
        write_csv(splits_root / "by_eval_role" / role / "samples.csv", samp_role.get(role, []))

    # leakage: patient in >1 eval_role
    role_sets: dict[str, set[str]] = {k: {r["patient_id"] for r in v} for k, v in by_role.items()}
    leaks = []
    roles = sorted(role_sets)
    for i, a in enumerate(roles):
        for b in roles[i + 1 :]:
            inter = role_sets[a] & role_sets[b]
            if inter:
                leaks.append({"a": a, "b": b, "n": len(inter), "examples": sorted(inter)[:10]})

    # also check patient_id uniqueness in supervised table
    pid_counts = Counter(r["patient_id"] for r in patients)
    dup_pids = [p for p, n in pid_counts.items() if n > 1]

    report = {
        "created_at": utc_now(),
        "n_patients_supervised": len(patients),
        "n_samples_supervised": len(samples),
        "by_legacy_split_patients": {k: len(v) for k, v in sorted(by_legacy.items())},
        "by_eval_role_patients": {k: len(v) for k, v in sorted(by_role.items())},
        "by_eval_role_samples": {k: len(v) for k, v in sorted(samp_role.items())},
        "by_cohort_x_eval_role": dict(
            Counter((r["cohort_dir"], r["eval_role"]) for r in patients)
        ),
        "remapped_patients": sum(1 for r in patients if r["legacy_split"] != r["eval_role"]),
        "external_in_fit_split_legacy": sum(
            1 for r in patients if "external_in_fit_split_legacy" in (r.get("eval_note") or "")
        ),
        "patient_id_duplicate_rows": len(dup_pids),
        "eval_role_leakage": leaks,
        "leakage_pass": len(leaks) == 0 and len(dup_pids) == 0,
        "policy": {
            "prospective_test_external": "-> test_prospective",
            "internal_test_external": "-> test_internal_holdout",
            "external_train_val": "kept (legacy; 福建省肿瘤医院 historically in fit)",
            "split_unit": "patient_id",
        },
    }
    # JSON-serialize tuple keys
    report["by_cohort_x_eval_role"] = {
        f"{a}|{b}": n for (a, b), n in Counter((r["cohort_dir"], r["eval_role"]) for r in patients).items()
    }
    (splits_root / "leakage_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary = f"""# Real-cine supervised splits

Generated: {report['created_at']}

## Use which table?

| 目的 | 读 |
|------|----|
| 跟历史 registry 一致 | `by_legacy_split/` |
| **汇报 / 泛化评测（推荐）** | `by_eval_role/` |
| 病人级软链 | `../by_split/<eval_role>/` |

## eval_role 规模（病人 / 样本）

| role | patients | samples |
|------|--------:|--------:|
"""
    for role in sorted(by_role):
        summary += f"| `{role}` | {len(by_role[role])} | {len(samp_role.get(role, []))} |\n"
    summary += f"""
- remapped from legacy: **{report['remapped_patients']}**（prospective/internal 误落在 test_external*）
- external 仍在 train/val（遗留，福建省肿瘤医院）: **{report['external_in_fit_split_legacy']}**
- patient_id 跨 eval_role 泄漏: **{'PASS' if report['leakage_pass'] else 'FAIL'}**

## 训练建议

1. Fit：`by_eval_role/train` + `val`
2. 外推：`test_external` + `test_external_newzip`
3. 前瞻：`test_prospective`（含从 test_external 纠正的 46 人）
4. 内部 holdout：`test_internal_holdout`（勿并进 external 汇报）
5. 划分单位：**patient_id**
"""
    (splits_root / "SUMMARY.md").write_text(summary, encoding="utf-8")

    # by_split symlinks -> by_patient
    by_split_root = view / "by_split"
    if by_split_root.exists():
        # remove only symlinks/empty role dirs we own
        for p in by_split_root.rglob("*"):
            if p.is_symlink():
                p.unlink()
    n_links = 0
    for r in patients:
        role = r["eval_role"]
        patient_rel = r.get("patient_dir") or ""
        if not patient_rel:
            continue
        target = view / patient_rel
        # patient_dir like by_patient/external/北京友谊医院/xxx
        name = Path(patient_rel).name
        link = by_split_root / role / name
        if ensure_symlink(target, link):
            n_links += 1

    # labeling queue
    q = view / "labeling_queue"
    q.mkdir(parents=True, exist_ok=True)
    for r in unlabeled:
        r["queue_priority"] = {
            "prospective": "P1_prospective",
            "external": "P2_external",
            "internal": "P0_internal",
        }.get(r.get("cohort_dir") or "", "P3_other")
        r["n_real_cine_clips"] = r.get("n_real_cine_clips") or ""
    write_csv(q / "patients.csv", unlabeled)
    by_hosp: dict[str, list[dict]] = defaultdict(list)
    for r in unlabeled:
        by_hosp[(r.get("hospital") or r.get("bucket") or "unknown").strip() or "unknown"].append(r)
    for hosp, rows in sorted(by_hosp.items(), key=lambda x: (-len(x[1]), x[0])):
        safe = "".join("_" if c in '/\\:*?"<>|' else c for c in hosp)[:80] or "unknown"
        write_csv(q / "by_hospital" / f"{safe}.csv", rows)

    q_readme = f"""# 真视频无 T 标签 · 标注队列

生成：{utc_now()}

- 总病人：**{len(unlabeled)}**（有 `video_mode=cached`，缺可用 T）
- 按队列优先级：{dict(Counter(r['queue_priority'] for r in unlabeled))}
- 按队列/中心：`by_hospital/`
- 总表：`patients.csv`

**不要**把这些人直接并进监督训练。标完 T 后重跑：

```bash
python3 scripts/build_patient_media_registry.py
python3 scripts/build_real_cine_aligned_view.py --clean
python3 scripts/freeze_real_cine_training_package.py
```
"""
    (q / "README.md").write_text(q_readme, encoding="utf-8")

    # patch main README pointer
    readme = view / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        marker = "## 冻结拆分与标注队列"
        block = f"""## 冻结拆分与标注队列

复跑：`python3 scripts/freeze_real_cine_training_package.py`

| 路径 | 用途 |
|------|------|
| `splits/by_eval_role/` | **推荐**汇报/训练角色（已纠正 prospective→test_prospective） |
| `splits/by_legacy_split/` | 与 `patient_media_registry.split` 一致 |
| `by_split/<eval_role>/` | 按角色的病人软链（{n_links}） |
| `labeling_queue/` | {len(unlabeled)} 名真视频无 T |
| `alignment/patients_with_eval_role.csv` | 监督病人 + eval_role |
| `splits/leakage_report.json` | 泄漏检查（pass={report['leakage_pass']}） |

"""
        if marker in text:
            # replace from marker to end or next ## at start - append after inventory section
            pre, _, rest = text.partition(marker)
            # drop old block until EOF if no other section after - keep simple: rewrite tail
            text = pre.rstrip() + "\n\n" + block
        else:
            text = text.rstrip() + "\n\n" + block
        readme.write_text(text, encoding="utf-8")

    print(json.dumps({**report, "by_split_links": n_links, "labeling_queue": len(unlabeled)}, ensure_ascii=False, indent=2))
    print(f"[ok] {view}/splits  by_split={n_links}  queue={len(unlabeled)}")
    return 0 if report["leakage_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
