#!/usr/bin/env python3
"""Scan dataset/ and generate inventory JSON + HTML dashboard."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET = PROJECT_ROOT / "dataset"
OUT_DIR = DATASET / "inventory"
OUT_JSON = OUT_DIR / "dataset_inventory.json"
OUT_HTML = OUT_DIR / "index.html"


def count_files(directory: Path, extensions: tuple[str, ...]) -> int:
    if not directory.exists():
        return 0
    total = 0
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        if any(name.endswith(ext) for ext in extensions):
            total += 1
    return total


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def counter_from_rows(rows: list[dict[str, str]], column: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        counter[row.get(column, "") or "(empty)"] += 1
    return dict(counter.most_common())


def view_stats(base: Path) -> dict[str, int]:
    return {
        "images": count_files(base / "images", (".png", ".jpg", ".jpeg")),
        "annotations": count_files(
            base / "annotations", (".json", ".nii", ".nii.gz", ".txt")
        ),
        "roi_masks": count_files(base / "roi_masks", (".png", ".nii", ".nii.gz")),
        "overlays": count_files(base / "overlays", (".png", ".jpg", ".jpeg")),
    }


def scan_internal() -> dict:
    manifest_rows = read_csv_rows(DATASET / "internal" / "manifest.csv")
    groups = []
    internal_root = DATASET / "internal"
    for pool in ("training_2018_2024", "prospective_2025"):
        pool_path = internal_root / pool
        if not pool_path.exists():
            continue
        for year_dir in sorted(pool_path.iterdir()):
            if not year_dir.is_dir():
                continue
            entry = {
                "pool": pool,
                "year": year_dir.name,
                "views": {},
            }
            for view in ("original", "crop_ui", "crop_roi"):
                view_path = year_dir / view
                if view_path.exists():
                    entry["views"][view] = view_stats(view_path)
            groups.append(entry)

    return {
        "manifest_rows": len(manifest_rows),
        "unmatched_rows": len(read_csv_rows(internal_root / "unmatched_files.csv")),
        "error_rows": len(read_csv_rows(internal_root / "errors.csv")),
        "manifest_by_pool": counter_from_rows(manifest_rows, "group_targets"),
        "groups": groups,
    }


def scan_external() -> dict:
    manifest_rows = read_csv_rows(DATASET / "external" / "manifest.csv")
    newzip_rows = read_csv_rows(DATASET / "external" / "new_external_zip_manifest.csv")
    centers = []

    external_root = DATASET / "external"
    for center_dir in sorted(external_root.iterdir()):
        if not center_dir.is_dir() or center_dir.name.startswith("."):
            continue
        entry = {"folder": center_dir.name, "views": {}}
        for view in ("original", "crop_ui", "crop_roi"):
            view_path = center_dir / view
            if view_path.exists():
                entry["views"][view] = view_stats(view_path)
        centers.append(entry)

    return {
        "manifest_rows": len(manifest_rows),
        "newzip_manifest_rows": len(newzip_rows),
        "combined_manifest_rows": len(manifest_rows) + len(newzip_rows),
        "unmatched_rows": len(read_csv_rows(external_root / "unmatched_files.csv")),
        "error_rows": len(read_csv_rows(external_root / "errors.csv")),
        "manifest_by_center": counter_from_rows(manifest_rows, "group_targets"),
        "newzip_by_center": counter_from_rows(newzip_rows, "group_targets"),
        "centers": centers,
    }


def scan_lumen() -> dict:
    root = DATASET / "lumen_detection"
    if not root.exists():
        return {}
    result = {}
    for sub in sorted(root.iterdir()):
        if not sub.is_dir():
            continue
        result[sub.name] = {
            "images_train": count_files(sub / "images" / "train", (".png", ".jpg", ".jpeg")),
            "images_val": count_files(sub / "images" / "val", (".png", ".jpg", ".jpeg")),
            "images_test": count_files(sub / "images" / "test", (".png", ".jpg", ".jpeg")),
            "labels_train": count_files(sub / "labels" / "train", (".txt", ".json")),
            "labels_val": count_files(sub / "labels" / "val", (".txt", ".json")),
            "labels_test": count_files(sub / "labels" / "test", (".txt", ".json")),
        }
    return result


def scan_tables() -> dict:
    tables_root = DATASET / "tables"
    files = []
    for path in sorted(tables_root.glob("*")):
        if path.is_file():
            files.append(
                {
                    "name": path.name,
                    "size_mb": round(path.stat().st_size / 1024 / 1024, 3),
                }
            )
    centers = read_csv_rows(tables_root / "center_name_registry.csv")
    master_rows = read_csv_rows(tables_root / "patient_clinical_master.csv")
    return {
        "files": files,
        "center_registry_rows": len(centers),
        "centers": centers,
        "patient_clinical_master_rows": len(master_rows),
    }


def load_overlay_audit() -> dict:
    path = DATASET / "tables" / "external_hospital_overlay_audit.csv"
    if not path.exists():
        return {}
    rows = read_csv_rows(path)
    by_center: dict[str, dict] = {}
    for row in rows:
        center = row.get("center_folder", "")
        if center not in by_center:
            by_center[center] = {"total": 0, "mismatch": 0, "lanzhou_504": 0}
        by_center[center]["total"] += 1
        if str(row.get("mismatch", "")).lower() in {"true", "1"}:
            by_center[center]["mismatch"] += 1
        detected = row.get("detected_hospitals", "")
        if "中核五〇四医院" in detected or "504" in row.get("ocr_header", ""):
            by_center[center]["lanzhou_504"] += 1
    return {
        "audit_csv": str(path.relative_to(PROJECT_ROOT)),
        "by_center": by_center,
        "mislabel_fix": {
            "issue": "外省整理.zip 内「湖北窦」曾被误标为湖北中西医结合医院",
            "fix": "2026-05-20 重分类为 中核五〇四医院（帧头 OCR: LanZhou 504 Hospital）",
            "doc": "dataset/tables/external_hubei_mislabel_remediation.md",
        },
    }


def scan_modeling_csv() -> dict:
    regions = (
        PROJECT_ROOT
        / "pipeline/data/tstaging_4class_region_contrastive_full/regions"
    )
    if not regions.exists():
        return {}
    splits = {}
    for path in sorted(regions.glob("*_clinical.csv")):
        rows = read_csv_rows(path)
        splits[path.stem] = {
            "rows": len(rows),
            "patients": len({r.get("patient_id", "") for r in rows if r.get("patient_id")}),
            "labels": dict(Counter(r.get("label", "") for r in rows).most_common()),
        }
    return splits


def build_inventory() -> dict:
    internal = scan_internal()
    external = scan_external()

    internal_original_images = sum(
        g["views"].get("original", {}).get("images", 0) for g in internal["groups"]
    )

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "project_root": str(PROJECT_ROOT),
        "dataset_root": str(DATASET),
        "summary": {
            "internal_manifest": internal["manifest_rows"],
            "external_manifest": external["manifest_rows"],
            "external_newzip_manifest": external["newzip_manifest_rows"],
            "total_manifest": internal["manifest_rows"] + external["combined_manifest_rows"],
            "internal_physical_original_images": internal_original_images,
            "lumen_detection_train": sum(
                v.get("images_train", 0)
                for v in scan_lumen().values()
            ),
        },
        "calibers": [
            {
                "name": "正式 manifest 口径",
                "scope": "dataset/internal + external manifest.csv",
                "frames": internal["manifest_rows"] + external["manifest_rows"],
                "use": "分割、ROI、正式物理数据统计",
            },
            {
                "name": "manifest + newzip",
                "scope": "正式 manifest + new_external_zip_manifest.csv",
                "frames": internal["manifest_rows"] + external["combined_manifest_rows"],
                "use": "含新增外部 zip 的磁盘可用标注图像",
            },
            {
                "name": "T 分期建模 CSV",
                "scope": "pipeline/data/.../regions/*_clinical.csv",
                "frames": sum(v["rows"] for v in scan_modeling_csv().values()),
                "use": "4 类 T 分期训练与 AUC 评估",
            },
        ],
        "internal": internal,
        "external": external,
        "lumen_detection": scan_lumen(),
        "tables": scan_tables(),
        "modeling_splits": scan_modeling_csv(),
        "overlay_audit": load_overlay_audit(),
        "docs": [
            {"title": "外省整理误标修复说明", "path": "dataset/tables/external_hubei_mislabel_remediation.md"},
            {"title": "DATASET_GUIDE.md", "path": "dataset/DATASET_GUIDE.md"},
            {"title": "README.md", "path": "dataset/README.md"},
            {"title": "tables/README.md", "path": "dataset/tables/README.md"},
        ],
    }


def _fmt_num(value: int | float | None) -> str:
    if value is None:
        return "—"
    return f"{int(value):,}"


def _pct(part: int, total: int) -> str:
    if not total:
        return "—"
    return f"{(part / total) * 100:.1f}%"


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _render_table(headers: list[str], rows: list[list[str]]) -> str:
    thead = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body_rows = []
    for row in rows:
        cells = []
        for idx, cell in enumerate(row):
            cls = ' class="num"' if idx > 0 and cell.replace(",", "").isdigit() else ""
            cells.append(f"<td{cls}>{cell}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    tbody = "".join(body_rows)
    return f"<table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>"


def _render_bar(value: int, max_value: int) -> str:
    width = min(100, (value / max_value) * 100) if max_value else 0
    return (
        f'<div class="bar-cell">{_fmt_num(value)}'
        f'<div class="bar"><span style="width:{width:.1f}%"></span></div></div>'
    )


def _render_body(data: dict) -> str:
    s = data["summary"]
    internal = data["internal"]
    external = data["external"]
    tables = data["tables"]

    kpis = [
        ("正式 manifest 总帧", s["total_manifest"] - external.get("newzip_manifest_rows", 0)),
        ("internal manifest", s["internal_manifest"]),
        ("external manifest", s["external_manifest"]),
        ("newzip manifest", s["external_newzip_manifest"]),
        ("物理 original 图像", s["internal_physical_original_images"]),
        ("临床主表患者行", tables["patient_clinical_master_rows"]),
    ]
    kpi_html = '<div class="kpi-grid">' + "".join(
        f'<div class="kpi"><div class="val">{_fmt_num(v)}</div><div class="lbl">{_esc(l)}</div></div>'
        for l, v in kpis
    ) + "</div>"

    overview_rows = [
        ["internal/", _fmt_num(internal["manifest_rows"]), "协和内部直接手术，含 training_2018_2024 + prospective_2025"],
        ["external/ (原多中心)", _fmt_num(external["manifest_rows"]), "莆田/肿瘤/三明/莆田二院等"],
        ["external/ (newzip)", _fmt_num(external["newzip_manifest_rows"]), "外省整理 + 德化医院等新增外部"],
        ["合计 (manifest+newzip)", _fmt_num(s["total_manifest"]), "磁盘正式预处理成功样本"],
    ]

    caliber_rows = [
        [c["name"], f'<code>{_esc(c["scope"])}</code>', _fmt_num(c["frames"]), c["use"]]
        for c in data["calibers"]
    ]

    int_max = max([1, *internal.get("manifest_by_pool", {}).values()])
    int_pool_rows = [
        [
            f'<code>{_esc(k)}</code>',
            _fmt_num(v),
            _pct(v, internal["manifest_rows"]),
            _render_bar(v, int_max),
        ]
        for k, v in internal.get("manifest_by_pool", {}).items()
    ]

    int_year_rows = []
    for group in internal.get("groups", []):
        views = group.get("views", {})
        pool_label = group["pool"].replace("training_2018_2024", "train池").replace(
            "prospective_2025", "前瞻池"
        )
        badge = (
            '<span class="badge warn">建议独立 test</span>'
            if "prospective" in group["pool"]
            else '<span class="badge ok">训练主池</span>'
        )
        int_year_rows.append(
            [
                pool_label,
                group["year"],
                _fmt_num(views.get("original", {}).get("images", 0)),
                _fmt_num(views.get("crop_ui", {}).get("images", 0)),
                _fmt_num(views.get("crop_roi", {}).get("images", 0)),
                badge,
            ]
        )

    ext_max = max(
        [
            *external.get("manifest_by_center", {}).values(),
            *external.get("newzip_by_center", {}).values(),
            1,
        ],
        default=1,
    )
    ext_center_rows = [
        [
            _esc(k),
            _fmt_num(v),
            _pct(v, external["manifest_rows"]),
            _render_bar(v, ext_max),
        ]
        for k, v in external.get("manifest_by_center", {}).items()
    ]
    ext_phys_rows = []
    for center in external.get("centers", []):
        count = center.get("views", {}).get("original", {}).get("images", 0)
        size = "大中心" if count > 500 else ("小中心" if count < 50 else "中")
        ext_phys_rows.append([_esc(center["folder"]), _fmt_num(count), size])

    newzip_rows = [
        [_esc(k), _render_bar(v, ext_max)]
        for k, v in external.get("newzip_by_center", {}).items()
    ]

    label_names = {"0": "T1", "1": "T2", "2": "T3", "3": "T4+"}
    model_rows = []
    total_model_rows = 0
    for name, info in data.get("modeling_splits", {}).items():
        total_model_rows += info.get("rows", 0)
        labels = ", ".join(
            f'{label_names.get(l, f"L{l}")}:{n}'
            for l, n in info.get("labels", {}).items()
        )
        model_rows.append(
            [
                f"<code>{_esc(name)}</code>",
                _fmt_num(info.get("rows", 0)),
                _fmt_num(info.get("patients", 0)),
                labels,
            ]
        )

    table_file_rows = [
        [f"<code>{_esc(f['name'])}</code>", str(f["size_mb"])]
        for f in tables.get("files", [])
    ]

    center_cols = [
        "standard_hospital_name",
        "folder_name",
        "tstaging_manifest",
        "tstaging_split",
        "manifest_frames",
        "clinical_patients",
        "benign_data",
        "malignant_data",
    ]
    center_rows = [
        [_esc(c.get(col, "—")) for col in center_cols]
        for c in tables.get("centers", [])
    ]

    lumen_rows = []
    for name, stats in data.get("lumen_detection", {}).items():
        total = (
            stats.get("images_train", 0)
            + stats.get("images_val", 0)
            + stats.get("images_test", 0)
        )
        lumen_rows.append(
            [
                _esc(name),
                _fmt_num(stats.get("images_train", 0)),
                _fmt_num(stats.get("images_val", 0)),
                _fmt_num(stats.get("images_test", 0)),
                _fmt_num(total),
            ]
        )

    doc_items = "".join(
        f'<li><a href="../../{_esc(d["path"])}">{_esc(d["title"])}</a> '
        f'<code>{_esc(d["path"])}</code></li>'
        for d in data.get("docs", [])
    )

    quality_html = ""
    audit = data.get("overlay_audit") or {}
    if audit:
        fix = audit.get("mislabel_fix", {})
        quality_html = f"""
<section id="quality"><h2>12. 外部数据质量（帧头 OCR 审计）</h2>
<p class="note"><strong>{_esc(fix.get("issue", ""))}</strong> — {_esc(fix.get("fix", ""))}
见 <a href="../../{_esc(fix.get("doc", ""))}">修复说明</a>。</p>
<p>审计文件：<code>{_esc(audit.get("audit_csv", ""))}</code>（全 newzip 原图帧头 OCR，当前文件夹标签与帧头一致则 <code>mismatch=0</code>）</p>
"""
        audit_rows = []
        for center, stats in sorted(audit.get("by_center", {}).items()):
            audit_rows.append(
                [
                    _esc(center),
                    _fmt_num(stats.get("total", 0)),
                    _fmt_num(stats.get("lanzhou_504", 0)),
                    _fmt_num(stats.get("mismatch", 0)),
                ]
            )
        if audit_rows:
            quality_html += _render_table(
                ["中心目录", "审计图像数", "帧头含 504/兰州", "与目录不一致"],
                audit_rows,
            )
        quality_html += """
<p>典型样例 <code>hbd1-3.jpg</code> 帧头为 <strong>LanZhou 504 Hospital</strong>，现归属 <code>dataset/external/中核五〇四医院/</code>，不再使用 <code>湖北中西医结合医院</code>。</p>
</section>
"""

    return f"""
{kpi_html}
<section id="overview"><h2>1. 总览</h2>
<p class="note"><strong>口径提醒：</strong>做分割/ROI 实验以 <code>manifest.csv</code> 为准；做 T 分期 AUC 以 <code>pipeline/data/.../regions/*_clinical.csv</code> 为准。二者不可混用。</p>
{_render_table(["数据块", "manifest 成功样本", "说明"], overview_rows)}
</section>

<section id="calibers"><h2>2. 统计口径对照</h2>
{_render_table(["口径", "范围", "帧/行数", "用途"], caliber_rows)}
</section>

<section id="tree"><h2>3. 目录结构</h2>
<pre class="tree">dataset/
├── DATASET_GUIDE.md
├── README.md
├── inventory/          ← 本盘点页
├── internal/
│   ├── manifest.csv
│   ├── training_2018_2024/{{2018,2019,2020_2023,2024}}/
│   └── prospective_2025/2025/
├── external/
│   ├── manifest.csv
│   ├── new_external_zip_manifest.csv
│   └── {{各中心}}/{{original,crop_ui,crop_roi}}/
├── lumen_detection/
└── tables/</pre>
</section>

<section id="internal"><h2>4. 内部数据 (internal/)</h2>
<h3>4.1 manifest 按池分布</h3>
{_render_table(["group_targets", "样本数", "占比", ""], int_pool_rows)}
<p>未匹配：{_fmt_num(internal.get("unmatched_rows", 0))} · 预处理错误：{_fmt_num(internal.get("error_rows", 0))}</p>
<h3>4.2 按年份 × 视图（物理文件数，original/images）</h3>
{_render_table(["池", "年份", "original", "crop_ui", "crop_roi", "建议"], int_year_rows)}
</section>

<section id="external"><h2>5. 外部数据 (external/)</h2>
<h3>5.1 原多中心 manifest</h3>
{_render_table(["中心 (group_targets)", "manifest 帧", "占比", ""], ext_center_rows)}
<h3>5.2 各中心物理规模 (original/images)</h3>
{_render_table(["目录名", "original 图像", "规模"], ext_phys_rows)}
<p>未匹配：{_fmt_num(external.get("unmatched_rows", 0))} · 错误：{_fmt_num(external.get("error_rows", 0))}</p>
</section>

<section id="newzip"><h2>6. 新增外部 zip (new_external_zip_manifest)</h2>
{_render_table(["中心", "manifest 帧"], newzip_rows)}
<p class="note">newzip 数据已写入独立建模 split <code>test_external_newzip_clinical.csv</code>；未匹配 pT 的图像保留在 manifest 但不进入建模 CSV。</p>
</section>

<section id="modeling"><h2>7. T 分期建模 CSV</h2>
<p>路径：<code>pipeline/data/tstaging_4class_region_contrastive_full/regions/</code></p>
{_render_table(["split 文件", "CSV 行数", "patient_id", "label 分布"], model_rows)}
<p>建模 CSV 行数合计：<strong>{_fmt_num(total_model_rows)}</strong>（各 split 可能有重复样本行，去重图像数以 DATASET_GUIDE 为准）</p>
</section>

<section id="tables"><h2>8. 临床表资产 (tables/)</h2>
{_render_table(["文件", "大小 (MB)"], table_file_rows)}
<p>患者临床主表行数：<strong>{_fmt_num(tables.get("patient_clinical_master_rows", 0))}</strong></p>
</section>

<section id="centers"><h2>9. 多中心标准命名对照</h2>
{_render_table(center_cols, center_rows) if center_rows else "<p>无数据</p>"}
</section>

<section id="lumen"><h2>10. 胃腔检测 (lumen_detection/)</h2>
{_render_table(["子集", "train", "val", "test", "合计"], lumen_rows)}
</section>

<section id="docs"><h2>11. 相关文档</h2>
<ul>
{doc_items}
<li><a href="dataset_inventory.json">dataset_inventory.json</a> — 机器可读盘点数据</li>
</ul>
</section>
{quality_html}
"""


def render_html(data: dict) -> str:
    body = _render_body(data)
    meta = (
        f"生成时间：{_esc(data['generated_at'])} · "
        f"数据根目录：{_esc(data['dataset_root'])} · "
        f"重新生成：<code>python scripts/build_dataset_inventory.py</code>"
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>GastricTstaging — 完整数据集盘点</title>
  <style>
    :root {{
      --bg: #ffffff;
      --surface: #f8fafc;
      --surface2: #f1f5f9;
      --border: #e2e8f0;
      --text: #0f172a;
      --muted: #64748b;
      --accent: #0e7490;
      --accent2: #047857;
      --warn: #b45309;
      --ok: #16a34a;
      --font: "Segoe UI", system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
      --mono: ui-monospace, "Cascadia Code", monospace;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      font-family: var(--font);
      background: var(--bg);
      color: var(--text);
      line-height: 1.55;
      font-size: 14px;
    }}
    .layout {{
      display: grid;
      grid-template-columns: 220px 1fr;
      min-height: 100vh;
    }}
    @media (max-width: 900px) {{
      .layout {{ grid-template-columns: 1fr; }}
      nav.side {{ position: relative; height: auto; }}
    }}
    nav.side {{
      position: sticky;
      top: 0;
      height: 100vh;
      overflow-y: auto;
      background: var(--surface);
      border-right: 1px solid var(--border);
      padding: 1.25rem 1rem;
    }}
    nav.side h2 {{
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin-bottom: 0.75rem;
    }}
    nav.side a {{
      display: block;
      color: var(--muted);
      text-decoration: none;
      padding: 0.35rem 0.5rem;
      border-radius: 6px;
      font-size: 0.86rem;
      margin-bottom: 2px;
    }}
    nav.side a:hover {{ color: var(--accent); background: var(--surface2); }}
    main {{ padding: 2rem 2.5rem 4rem; max-width: 1200px; }}
    header.hero {{
      margin-bottom: 2rem;
      padding-bottom: 1.5rem;
      border-bottom: 1px solid var(--border);
    }}
    header.hero h1 {{ font-size: 1.75rem; margin-bottom: 0.4rem; }}
    header.hero .subtitle {{ color: var(--muted); max-width: 48em; }}
    .meta {{ margin-top: 0.75rem; font-size: 0.85rem; color: var(--muted); }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
      gap: 0.75rem;
      margin: 1.25rem 0 2rem;
    }}
    .kpi {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1rem;
    }}
    .kpi .val {{ font-size: 1.6rem; font-weight: 700; color: var(--accent); }}
    .kpi .lbl {{ font-size: 0.78rem; color: var(--muted); margin-top: 0.2rem; }}
    section {{ margin-bottom: 2.5rem; scroll-margin-top: 1rem; }}
    section h2 {{
      font-size: 1.2rem;
      color: var(--accent);
      margin-bottom: 0.85rem;
      padding-bottom: 0.35rem;
      border-bottom: 1px solid var(--border);
    }}
    section h3 {{ font-size: 1rem; margin: 1rem 0 0.5rem; color: var(--text); }}
    p.note {{
      background: #fffbeb;
      border: 1px solid #fde68a;
      border-radius: 8px;
      padding: 0.75rem 1rem;
      font-size: 0.88rem;
      color: #92400e;
      margin-bottom: 1rem;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.86rem;
      margin-bottom: 1rem;
    }}
    th, td {{
      border: 1px solid var(--border);
      padding: 0.45rem 0.6rem;
      text-align: left;
    }}
    th {{ background: var(--surface2); font-weight: 600; }}
    td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    code, .mono {{ font-family: var(--mono); font-size: 0.82em; }}
    .tree {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1rem 1.25rem;
      font-family: var(--mono);
      font-size: 0.8rem;
      white-space: pre;
      overflow-x: auto;
    }}
    .badge {{
      display: inline-block;
      padding: 0.15rem 0.5rem;
      border-radius: 999px;
      font-size: 0.72rem;
      font-weight: 600;
      border: 1px solid var(--border);
      background: var(--surface2);
      color: var(--muted);
    }}
    .badge.ok {{ border-color: var(--ok); color: var(--ok); }}
    .badge.warn {{ border-color: var(--warn); color: var(--warn); }}
    a {{ color: var(--accent); }}
    .bar-cell {{ min-width: 120px; }}
    .bar {{
      height: 6px;
      background: var(--surface2);
      border-radius: 3px;
      overflow: hidden;
      margin-top: 4px;
    }}
    .bar > span {{
      display: block;
      height: 100%;
      background: var(--accent);
    }}
  </style>
</head>
<body>
  <div class="layout">
    <nav class="side">
      <h2>数据集盘点</h2>
      <a href="#overview">总览</a>
      <a href="#calibers">统计口径</a>
      <a href="#tree">目录树</a>
      <a href="#internal">内部数据</a>
      <a href="#external">外部数据</a>
      <a href="#newzip">新增 zip</a>
      <a href="#modeling">建模 CSV</a>
      <a href="#tables">临床表</a>
      <a href="#centers">多中心对照</a>
      <a href="#lumen">胃腔检测</a>
      <a href="#docs">相关文档</a>
      <a href="#quality">数据质量</a>
    </nav>
    <main>
      <header class="hero">
        <h1>完整数据集盘点</h1>
        <p class="subtitle">
          基于 <code>dataset/</code> 目录的正式预处理数据、manifest 清单、临床表与 T 分期建模 split 的交互式盘点页。
          实验前请区分 <strong>manifest 物理口径</strong> 与 <strong>建模 CSV 口径</strong>。
        </p>
        <p class="meta">{meta}</p>
      </header>
      <div id="app">{body}</div>
    </main>
  </div>
</body>
</html>
"""


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = build_inventory()
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_HTML.write_text(render_html(data), encoding="utf-8")
    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_HTML}")
    print(f"Summary: {data['summary']}")


if __name__ == "__main__":
    main()
