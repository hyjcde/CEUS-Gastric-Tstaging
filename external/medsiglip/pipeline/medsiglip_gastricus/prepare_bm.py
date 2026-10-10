"""Build resolved BM CSVs with BM-sign pack columns.

Does not change the T-staging 11-field pack. Ulcer / wall stay missing
unless a report or ultrasound sentence actually has them.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pandas as pd

from .bm_sign_pack import (
    BM_SIGN_DIM,
    DEFAULT_NORM_STATS,
    encode_fields,
    fields_from_ultrasound_text,
    merge_fields,
    n_filled,
)
from .constants import (
    BM_CACHE_DIR,
    BM_DATASET_DIR,
    BM_GASTRITIS_CLINICAL,
    BM_TSTAGING_CLINICAL_DIR,
    CLINICAL_FIELDS,
    MAIN_ROOT,
    SPLIT_FILES,
)


def _abs(rel: object) -> Path:
    path = Path(str(rel))
    return path if path.is_absolute() else MAIN_ROOT / path


def _mask_path(image_rel: str) -> str:
    image = _abs(image_rel)
    if "crop_ui/images" in image_rel.replace("\\", "/"):
        for suffix in (".png", ".jpg"):
            cand = image.parent.parent / "roi_masks" / f"{image.stem}{suffix}"
            if cand.is_file():
                return str(cand.relative_to(MAIN_ROOT))
    return ""


def _load_gastritis() -> pd.DataFrame:
    if not BM_GASTRITIS_CLINICAL.is_file():
        return pd.DataFrame()
    table = pd.read_csv(BM_GASTRITIS_CLINICAL)
    table.columns = [str(c).lstrip("\ufeff") for c in table.columns]
    return table


def _load_tstaging_clinical() -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {}
    if not BM_TSTAGING_CLINICAL_DIR.is_dir():
        return lookup
    for path in sorted(BM_TSTAGING_CLINICAL_DIR.glob("*_clinical.csv")):
        if "match_fail" in path.name:
            continue
        table = pd.read_csv(path, low_memory=False)
        if "patient_id" not in table.columns:
            continue
        for _, row in table.iterrows():
            pid = str(row.get("patient_id") or "").strip()
            if not pid or pid in lookup:
                continue
            lookup[pid] = {name: row.get(name) for name in CLINICAL_FIELDS}
            lookup[pid]["clinical_patient_uid"] = row.get("clinical_patient_uid")
    return lookup


def _clinical22_from_row(row: dict[str, object]) -> list[float]:
    from .constants import CATEGORICAL_ALLOWED, CONTINUOUS_FIELDS, MAX_CODE

    vector: list[float] = []
    for name in CLINICAL_FIELDS:
        raw = row.get(name)
        missing = raw in (None, "", -1, "-1") or (isinstance(raw, float) and pd.isna(raw))
        if name in CONTINUOUS_FIELDS:
            if missing:
                vector.extend([0.0, 1.0])
            else:
                stats = DEFAULT_NORM_STATS.get(
                    "max_diameter_cm" if "length" in name else "max_thickness_cm",
                    {"mean": 0.0, "std": 1.0},
                )
                if name == "age":
                    stats = {"mean": 61.2, "std": 11.4}
                elif name == "cea_value":
                    stats = {"mean": 12.6, "std": 70.6}
                elif name == "ca199_value":
                    stats = {"mean": 49.6, "std": 162.2}
                elif name == "tumor_length_cm":
                    stats = {"mean": 5.17, "std": 2.37}
                elif name == "tumor_thickness_cm":
                    stats = {"mean": 1.49, "std": 0.61}
                value = float(raw)
                vector.extend([(value - stats["mean"]) / max(stats["std"], 1e-6), 0.0])
            continue
        allowed = CATEGORICAL_ALLOWED.get(name, set())
        max_code = MAX_CODE.get(name, 1)
        try:
            code = int(float(raw))
        except (TypeError, ValueError):
            code = None
        if missing or code is None or code not in allowed:
            vector.extend([0.0, 1.0])
        else:
            vector.extend([code / max(max_code, 1), 0.0])
    return vector


def _gastritis_fields(row: pd.Series, gastritis: pd.DataFrame) -> dict[str, object]:
    if gastritis.empty:
        return {}
    keys = {
        str(row.get("raw_patient_id") or "").strip(),
        str(row.get("patient_id") or "").strip().split("::")[-1],
    }
    keys.discard("")
    hit = gastritis[gastritis["patient_id"].astype(str).isin(keys) | gastritis["patient_key"].astype(str).isin(keys)]
    if hit.empty:
        return {}
    rec = hit.iloc[0]
    parsed = fields_from_ultrasound_text(rec.get("ultrasound_result") or rec.get("diagnosis") or "")
    age = rec.get("age")
    sex = rec.get("sex")
    try:
        parsed["_age"] = float(age)
    except (TypeError, ValueError):
        parsed["_age"] = None
    try:
        parsed["_sex"] = int(float(sex))
    except (TypeError, ValueError):
        parsed["_sex"] = None
    return parsed


def prepare_bm(dest: Path | None = None) -> dict[str, object]:
    dest = dest or BM_CACHE_DIR
    dest.mkdir(parents=True, exist_ok=True)
    gastritis = _load_gastritis()
    tstaging = _load_tstaging_clinical()
    summary: dict[str, object] = {"dest": str(dest), "splits": {}}
    filled_counter = Counter()
    for split in SPLIT_FILES:
        src = BM_DATASET_DIR / f"splits/{split}.csv"
        if not src.is_file():
            raise FileNotFoundError(src)
        table = pd.read_csv(src)
        records = []
        for _, row in table.iterrows():
            image_rel = str(row["image_path"])
            mask_rel = _mask_path(image_rel)
            roi_rel = str(row.get("roi_path") or "")
            pid = str(row["patient_id"])
            raw_pid = str(row.get("raw_patient_id") or "")
            t_row = tstaging.get(pid) or tstaging.get(raw_pid) or {}
            g_fields = _gastritis_fields(row, gastritis)
            from_t = {
                "lesion_site": None,
                "max_diameter_cm": t_row.get("tumor_length_cm") if t_row else None,
                "max_thickness_cm": t_row.get("tumor_thickness_cm") if t_row else None,
                "ulcer_present": None,
                "wall_layers": None,
            }
            if t_row.get("tumor_location") in (0, 1, 2, 3):
                # Keep missing 9-site; coarse location stays in clinical-11 only.
                pass
            fields = merge_fields(from_t, g_fields)
            if fields.get("max_diameter_cm") in (-1, "-1"):
                fields["max_diameter_cm"] = None
            if fields.get("max_thickness_cm") in (-1, "-1"):
                fields["max_thickness_cm"] = None
            vector = encode_fields(fields)
            clinical_src = dict(t_row)
            if g_fields.get("_age") is not None and clinical_src.get("age") in (None, "", -1):
                clinical_src["age"] = g_fields["_age"]
            if g_fields.get("_sex") in (0, 1) and clinical_src.get("sex") in (None, "", -1):
                clinical_src["sex"] = g_fields["_sex"]
            clinical22 = _clinical22_from_row(clinical_src)
            filled = n_filled(fields)
            filled_counter[filled] += 1
            records.append(
                {
                    "crop_ui_path": image_rel,
                    "mask_path": mask_rel,
                    "roi_fallback_path": roi_rel if _abs(roi_rel).is_file() else "",
                    "patient_id": pid,
                    "raw_patient_id": raw_pid,
                    "label": int(row["label"]),
                    "source": row.get("source"),
                    "center_id": row.get("center_id"),
                    "split": split,
                    "has_mask": int(bool(mask_rel)),
                    "bm_sign_n_filled": filled,
                    "bm_sign_json": json.dumps(fields, ensure_ascii=False),
                    "bm_sign_10": json.dumps(vector),
                    "clinical_22": json.dumps(clinical22),
                    "clinical": json.dumps(clinical22 + vector),
                }
            )
        out = pd.DataFrame.from_records(records)
        out_path = dest / f"{split}_resolved.csv"
        out.to_csv(out_path, index=False)
        summary["splits"][split] = {
            "rows": int(len(out)),
            "patients": int(out["patient_id"].nunique()),
            "with_mask": int(out["has_mask"].sum()),
            "label_0": int((out["label"] == 0).sum()),
            "label_1": int((out["label"] == 1).sum()),
            "bm_sign_any": int((out["bm_sign_n_filled"] > 0).sum()),
            "path": str(out_path),
        }
        print(split, summary["splits"][split], flush=True)
    summary["bm_sign_n_filled"] = dict(filled_counter)
    summary["bm_sign_dim"] = BM_SIGN_DIM
    (dest / "prepare_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary
