#!/usr/bin/env python3
"""Generate completeness checks and Table-1-style stats for the external test set."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXT = PROJECT_ROOT / "dataset" / "external"
SPLIT = PROJECT_ROOT / "pipeline" / "data" / "tstaging_4class"
DEFAULT_OUT = PROJECT_ROOT / "docs" / "dataset"

LABEL_NAMES = {0: "T1", 1: "T2", 2: "T3", 3: "T4+"}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8-sig") as handle:
        return [{key.lstrip("\ufeff"): value for key, value in row.items()} for row in csv.DictReader(handle)]


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def center_from_image_path(image_path: str) -> str:
    return image_path.split("/external/")[1].split("/")[0]


def build_report() -> dict:
    manifest = read_csv(EXT / "manifest.csv")
    test_ext = read_csv(SPLIT / "test_external.csv")
    test_clin = read_csv(SPLIT / "test_external_clinical.csv")
    errors = read_csv(EXT / "errors.csv")

    manifest_by_center = Counter(row.get("group_targets", "") for row in manifest)
    label_by_center: dict[str, Counter[int]] = defaultdict(Counter)
    patients_by_center: dict[str, set[str]] = defaultdict(set)

    for row in test_ext:
        center = center_from_image_path(row["image_path"])
        label_by_center[center][int(row["label"])] += 1
        patients_by_center[center].add(row["patient_id"].lower())

    per_center: list[dict] = []
    for center in sorted(manifest_by_center.keys()):
        manifest_frames = manifest_by_center[center]
        labeled_frames = sum(label_by_center[center].values())
        unlabeled_frames = manifest_frames - labeled_frames
        per_center.append(
            {
                "hospital": center,
                "manifest_frames": manifest_frames,
                "labeled_frames": labeled_frames,
                "unlabeled_frames": unlabeled_frames,
                "patients": len(patients_by_center[center]),
                "T1": label_by_center[center][0],
                "T2": label_by_center[center][1],
                "T3": label_by_center[center][2],
                "T4+": label_by_center[center][3],
                "T1_pct": round(100 * label_by_center[center][0] / labeled_frames, 1) if labeled_frames else 0.0,
                "T2_pct": round(100 * label_by_center[center][1] / labeled_frames, 1) if labeled_frames else 0.0,
                "T3_pct": round(100 * label_by_center[center][2] / labeled_frames, 1) if labeled_frames else 0.0,
                "T4+_pct": round(100 * label_by_center[center][3] / labeled_frames, 1) if labeled_frames else 0.0,
            }
        )

    totals = {
        "hospital": "合计",
        "manifest_frames": sum(row["manifest_frames"] for row in per_center),
        "labeled_frames": sum(row["labeled_frames"] for row in per_center),
        "unlabeled_frames": sum(row["unlabeled_frames"] for row in per_center),
        "patients": sum(row["patients"] for row in per_center),
        "T1": sum(row["T1"] for row in per_center),
        "T2": sum(row["T2"] for row in per_center),
        "T3": sum(row["T3"] for row in per_center),
        "T4+": sum(row["T4+"] for row in per_center),
    }
    labeled_total = totals["labeled_frames"]
    totals.update(
        {
            "T1_pct": round(100 * totals["T1"] / labeled_total, 1),
            "T2_pct": round(100 * totals["T2"] / labeled_total, 1),
            "T3_pct": round(100 * totals["T3"] / labeled_total, 1),
            "T4+_pct": round(100 * totals["T4+"] / labeled_total, 1),
        }
    )
    per_center.append(totals)

    label_rows: list[dict] = []
    for label_id, label_name in LABEL_NAMES.items():
        row = {
            "class_id": label_id,
            "T_stage": label_name,
            "total": sum(label_by_center[center][label_id] for center in label_by_center),
        }
        for center in sorted(manifest_by_center.keys()):
            row[center] = label_by_center[center][label_id]
        label_rows.append(row)

    integrity_issues: list[str] = []
    for center in sorted(manifest_by_center.keys()):
        manifest_frames = manifest_by_center[center]
        crop_ui_frames = len(list((EXT / center / "crop_ui" / "images").glob("*.jpg")))
        if manifest_frames != crop_ui_frames:
            integrity_issues.append(f"{center}: manifest={manifest_frames} crop_ui={crop_ui_frames}")

    missing_paths = sum(1 for row in test_ext if not Path(row["image_path"]).exists())
    patients_per_case = Counter(row["patient_id"].lower() for row in test_ext)
    patient_values = sorted(patients_per_case.values())

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overview": {
            "centers": len(manifest_by_center),
            "manifest_frames": len(manifest),
            "labeled_frames": len(test_ext),
            "unlabeled_frames": len(manifest) - len(test_ext),
            "errors": len(errors),
            "missing_image_paths": missing_paths,
            "integrity_issues": integrity_issues,
        },
        "patient_stats": {
            "unique_patients": len(patients_per_case),
            "frames_min": min(patient_values),
            "frames_max": max(patient_values),
            "frames_median": patient_values[len(patient_values) // 2],
            "patients_1_frame": sum(1 for value in patient_values if value == 1),
            "patients_ge_10_frames": sum(1 for value in patient_values if value >= 10),
        },
        "clinical_match": dict(Counter(row.get("clinical_match_status", "") for row in test_clin)),
        "per_center": per_center,
        "label_by_center": label_rows,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# 外部测试集详细统计",
        "",
        f"> 生成时间：{report['generated_at']}",
        "",
        "## 完整性确认",
        "",
        "| 检查项 | 结果 |",
        "|--------|------|",
    ]

    overview = report["overview"]
    lines.extend(
        [
            f"| 外部中心数 | {overview['centers']} |",
            f"| manifest 总帧数 | {overview['manifest_frames']} |",
            f"| test_external 有标签帧 | {overview['labeled_frames']} |",
            f"| 无 pT 标签帧 | {overview['unlabeled_frames']} |",
            f"| 预处理错误 | {overview['errors']} |",
            f"| test CSV 路径缺失 | {overview['missing_image_paths']} |",
            f"| manifest vs crop_ui 不一致 | {'无' if not overview['integrity_issues'] else '; '.join(overview['integrity_issues'])} |",
            "",
            "## 总体 T 分期分布（test_external）",
            "",
        ]
    )

    total_labeled = overview["labeled_frames"]
    for label_id, label_name in LABEL_NAMES.items():
        count = sum(row[label_name] for row in report["per_center"] if row["hospital"] != "合计")
        lines.append(f"- **{label_name}**：{count} 帧（{100 * count / total_labeled:.1f}%）")
    lines.append("")

    patient_stats = report["patient_stats"]
    lines.extend(
        [
            "## 患者层面",
            "",
            f"- 独立患者数：**{patient_stats['unique_patients']}**",
            f"- 每患者帧数：min={patient_stats['frames_min']}, median={patient_stats['frames_median']}, max={patient_stats['frames_max']}",
            f"- 仅 1 帧患者：{patient_stats['patients_1_frame']} 人",
            f"- ≥10 帧患者：{patient_stats['patients_ge_10_frames']} 人",
            "",
        ]
    )

    if report["clinical_match"]:
        lines.extend(["## 临床特征匹配", ""])
        for key, value in sorted(report["clinical_match"].items()):
            lines.append(f"- {key or '(empty)'}：{value}")
        lines.append("")

    headers = [
        "医院",
        "manifest",
        "有标签",
        "无标签",
        "患者",
        "T1",
        "T2",
        "T3",
        "T4+",
        "T1%",
        "T2%",
        "T3%",
        "T4+%",
    ]
    lines.extend(
        [
            "## Table 1：按医院统计",
            "",
            "| " + " | ".join(headers) + " |",
            "|" + "|".join(["---"] * len(headers)) + "|",
        ]
    )
    for row in report["per_center"]:
        lines.append(
            "| {hospital} | {manifest_frames} | {labeled_frames} | {unlabeled_frames} | {patients} | "
            "{T1} | {T2} | {T3} | {T4+} | {T1_pct} | {T2_pct} | {T3_pct} | {T4+_pct} |".format(**row)
        )

    centers = [row["hospital"] for row in report["per_center"] if row["hospital"] != "合计"]
    lines.extend(
        [
            "",
            "## 按 T 分期 × 医院交叉表",
            "",
            "| T分期 | 合计 | " + " | ".join(centers) + " |",
            "|-------|------|" + "|".join(["---"] * len(centers)) + "|",
        ]
    )
    for row in report["label_by_center"]:
        values = [str(row[center]) for center in centers]
        lines.append(f"| {row['T_stage']} | {row['total']} | " + " | ".join(values) + " |")

    lines.extend(
        [
            "",
            "## 文件位置",
            "",
            "- 主评估 CSV：`pipeline/data/tstaging_4class/test_external.csv`",
            "- 按院切片：`pipeline/data/tstaging_4class/test_ext_{医院名}.csv`",
            "- 统一 manifest：`dataset/external/manifest.csv`",
            "- 本报告 CSV：`docs/dataset/external_test_set_by_center.csv`",
            "",
        ]
    )
    return "\n".join(lines)


def write_excel(path: Path, report: dict) -> None:
    import pandas as pd

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(report["per_center"]).to_excel(writer, sheet_name="by_center", index=False)
        pd.DataFrame(report["label_by_center"]).to_excel(writer, sheet_name="label_x_center", index=False)
        overview = report["overview"] | report["patient_stats"]
        pd.DataFrame([overview]).to_excel(writer, sheet_name="overview", index=False)


def write_outputs(out_dir: Path, report: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "external_test_set_statistics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "external_test_set_statistics.md").write_text(render_markdown(report), encoding="utf-8")
    write_csv(out_dir / "external_test_set_by_center.csv", report["per_center"])
    write_csv(out_dir / "external_test_set_label_by_center.csv", report["label_by_center"])
    try:
        write_excel(out_dir / "external_test_set_statistics.xlsx", report)
    except Exception as exc:
        print(f"[WARN] Excel export skipped: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    report = build_report()
    write_outputs(args.out_dir, report)
    print(json.dumps(report["overview"], ensure_ascii=False, indent=2))
    print(f"[INFO] Wrote reports to {args.out_dir}")


if __name__ == "__main__":
    main()
