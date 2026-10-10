"""方案未写、仓库必须补的数据合同: 干净四份 CSV + freeze crop_ui + mask 路径。

不用 20260531，不用上层 t_staging/splits（train 含外部），不用 Phase 0 train。
Full 图是 crop_ui/images，mask 是 crop_ui/roi_masks。不用现成 crop_roi 当主输入。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from .constants import CLINICAL_FIELDS, DATASET_DIR, INTERNAL_CROP_UI, ROOT, SPLIT_FILES


def _norm(text: str) -> str:
    return text.replace("--", "-").replace(" ", "_").lower()


def _stem_key(stem: str) -> str:
    return _norm(stem.rsplit("__", 1)[-1])


def _index_crop_ui(view_dir: Path) -> dict[str, Path]:
    images = view_dir / "images"
    index: dict[str, Path] = {}
    if not images.is_dir():
        return index
    for path in images.iterdir():
        if not path.is_file():
            continue
        stem = path.stem
        keys = {_stem_key(stem), _norm(stem)}
        parts = stem.split("__")
        if len(parts) >= 2:
            keys.add(_norm("__".join(parts[-2:])))
        for key in keys:
            index.setdefault(key, path)
    return index


def _old_keys(image_path: str, patient_id: str, source: str) -> list[str]:
    stem = Path(image_path).stem
    pid = str(patient_id).strip()
    keys: list[str] = []

    ds = re.match(r"^\d{4}_DS_Crop_(.+)$", stem, flags=re.I)
    if ds:
        rest = ds.group(1)
        keys.extend([_norm(rest), _norm(rest.replace("--", "-"))])

    prosp = re.match(r"^Surgery_2025_[^_]+_(\d+)\s*\((\d+)\)$", stem, flags=re.I)
    if prosp:
        keys.append(_norm(f"{prosp.group(1)}_({prosp.group(2)})"))

    y20 = re.match(r"^Surgery_2020_2023_(.+)$", stem, flags=re.I)
    if y20:
        keys.append(_norm(y20.group(1)))

    y19 = re.match(r"^Surgery_2019_(\d+)-(.+)$", stem, flags=re.I)
    if y19:
        rest = y19.group(2)
        keys.append(_norm(rest))
        keys.append(_norm(f"DICOM{y19.group(1)}__{rest}"))

    y24 = re.match(r"^Surgery_2024_(.+)$", stem, flags=re.I)
    if y24:
        rest = y24.group(1)
        keys.append(_norm(rest))
        # Surgery_2024_1-1050679-1 or Surgery_2024_2-Z0077923
        tail = re.sub(r"^\d+-", "", rest)
        keys.append(_norm(tail))

    keys.append(_norm(stem))
    if pid:
        keys.append(_norm(pid))
    # unique preserve order
    seen: set[str] = set()
    out: list[str] = []
    for key in keys:
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _mask_for(image_path: Path) -> Path | None:
    mask = Path(str(image_path).replace("/images/", "/roi_masks/")).with_suffix(".png")
    return mask if mask.is_file() else None


def _existing_crop_ui(raw: str) -> tuple[Path | None, Path | None]:
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    if path.is_file() and "crop_ui" in path.as_posix():
        return path, _mask_for(path)
    return None, None


def _lookup(index: dict[str, Path], keys: list[str]) -> Path | None:
    for key in keys:
        hit = index.get(key)
        if hit is not None:
            return hit
    # unique prefix fallback
    for key in keys:
        if len(key) < 4:
            continue
        matches = [p for k, p in index.items() if k == key or k.startswith(key + "-") or k.startswith(key + "_")]
        uniq = {p.resolve() for p in matches}
        if len(uniq) == 1:
            return next(iter(uniq))
    return None


def resolve_row(row: pd.Series, indexes: dict[str, dict[str, Path]]) -> dict[str, object]:
    raw = str(row["image_path"])
    source = str(row.get("source") or "")
    patient_id = str(row["patient_id"])
    image, mask = _existing_crop_ui(raw)
    status = "direct" if image is not None else ""
    if image is None and source in indexes:
        image = _lookup(indexes[source], _old_keys(raw, patient_id, source))
        if image is not None:
            mask = _mask_for(image)
            status = "mapped"
    if image is None:
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT / path
        if path.is_file():
            image, mask = path, _mask_for(path)
            status = "legacy_exists"
    if image is None:
        status = "unmapped"
    elif mask is None:
        status = status + "_no_mask" if status else "no_mask"
    clinical = []
    for field in CLINICAL_FIELDS:
        clinical.append(float(row.get(f"{field}_norm", 0.0) or 0.0))
        clinical.append(float(row.get(f"{field}_missing", 1.0) or 0.0))
    return {
        "split": row.get("split"),
        "source": source,
        "patient_id": patient_id,
        "label": int(row["label"]),
        "T_stage": row.get("T_stage"),
        "legacy_image_path": raw,
        "crop_ui_path": "" if image is None else str(image),
        "mask_path": "" if mask is None else str(mask),
        "resolve_status": status,
        "clinical_22": json.dumps(clinical),
    }


def write_resolved(out_dir: Path) -> dict[str, object]:
    from .build_clean_dataset import write_dataset

    inventory = write_dataset(DATASET_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {"dataset": str(DATASET_DIR.relative_to(ROOT)), "splits": {}}
    for split, rel in SPLIT_FILES.items():
        table = pd.read_csv(DATASET_DIR / rel)
        table.to_csv(out_dir / f"{split}_resolved.csv", index=False)
        summary["splits"][split] = {
            "rows": int(len(table)),
            "usable": int(len(table)),
            "patients": int(table["patient_id"].nunique()),
            "role": table["role"].iloc[0] if len(table) else "",
        }
    (out_dir / "resolve_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    summary["inventory"] = inventory
    return summary
