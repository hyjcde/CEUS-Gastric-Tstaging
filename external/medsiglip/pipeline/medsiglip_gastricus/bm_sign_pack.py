"""BM-sign pack: the five 良性报告填空 fields.

This is not the T-staging 11-field clinical pack. Do not fold ulcer or
wall-layer into CLINICAL_FIELD_SPECS. Size and site overlap that pack,
but BM keeps a 9-site codebook (clinical-11 only has 4 location codes).

Fields (5), encoded as 10 numbers: each {name}_norm + {name}_missing.

1. lesion_site     贲门 / 胃底 / 胃体大弯 / 胃体小弯 / 胃体前壁 / 胃体后壁 / 胃角 / 胃窦 / 幽门
2. max_diameter_cm 最大径, cm
3. max_thickness_cm 最厚径, cm
4. ulcer_present   溃疡 无=0 有=1
5. wall_layers     胃壁层次 存在 / 模糊 / 消失 / 其他

Train: fill from clinical master or parsed ultrasound text when present.
Do not impute ulcer or wall from the gold benign/malignant label.
Inference: doctor ticks on the BM form, sent as `bm_report.fields`.
Empty ticks stay missing so Assist-first still works.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

BM_SIGN_PACK_NAME = "bm_sign5"
BM_SIGN_N_FIELDS = 5
BM_SIGN_DIM = 10  # 5 x (norm, missing)

BM_LESION_SITES = (
    "贲门",
    "胃底",
    "胃体（大弯）",
    "胃体（小弯）",
    "胃体（前壁）",
    "胃体（后壁）",
    "胃角",
    "胃窦",
    "幽门",
)
BM_SITE_TO_CODE = {name: i for i, name in enumerate(BM_LESION_SITES)}
BM_SITE_MAX_CODE = len(BM_LESION_SITES) - 1  # 8

BM_WALL_LAYERS = ("存在", "模糊", "消失", "其他")
BM_WALL_TO_CODE = {name: i for i, name in enumerate(BM_WALL_LAYERS)}
BM_WALL_MAX_CODE = len(BM_WALL_LAYERS) - 1  # 3

# 9-site -> clinical-11 tumor_location (0 贲门/胃底, 1 胃体, 2 胃角/胃窦, 3 全胃)
BM_SITE_TO_CLINICAL11_LOCATION = {
    "贲门": 0,
    "胃底": 0,
    "胃体（大弯）": 1,
    "胃体（小弯）": 1,
    "胃体（前壁）": 1,
    "胃体（后壁）": 1,
    "胃角": 2,
    "胃窦": 2,
    "幽门": 2,
}

BM_SIGN_FIELDS = (
    "lesion_site",
    "max_diameter_cm",
    "max_thickness_cm",
    "ulcer_present",
    "wall_layers",
)

DEFAULT_NORM_STATS = {
    "max_diameter_cm": {"mean": 4.0, "std": 2.5},
    "max_thickness_cm": {"mean": 1.4, "std": 0.7},
}

_SIZE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:[*x×X]\s*(\d+(?:\.\d+)?))?\s*(mm|cm|厘米|毫米)",
    flags=re.I,
)


def _nonempty(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _finite_positive(value: object) -> float | None:
    if value is None or value is False or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def parse_lesion_site(value: object) -> str | None:
    text = _nonempty(value)
    if text is None or text in {"____", "——"}:
        return None
    for site in BM_LESION_SITES:
        if site in text:
            return site
    if "贲门" in text:
        return "贲门"
    if "胃底" in text:
        return "胃底"
    if "胃角" in text:
        return "胃角"
    if "幽门" in text:
        return "幽门"
    if "胃窦" in text:
        return "胃窦"
    if "胃体" in text:
        if "小弯" in text:
            return "胃体（小弯）"
        if "前壁" in text:
            return "胃体（前壁）"
        if "后壁" in text:
            return "胃体（后壁）"
        return "胃体（大弯）"
    return None


def parse_ulcer_present(value: object) -> int | None:
    if value is True:
        return 1
    if value is False:
        return 0
    text = _nonempty(value)
    if text is None:
        return None
    lowered = text.lower()
    if text in {"有", "是"} or lowered in {"1", "true", "yes", "present"}:
        return 1
    if text in {"无", "否"} or lowered in {"0", "false", "no", "none", "absent"}:
        return 0
    if "无溃疡" in text or "未见溃疡" in text:
        return 0
    if "溃疡" in text:
        return 1
    return None


def parse_wall_layers(value: object) -> str | None:
    text = _nonempty(value)
    if text is None:
        return None
    if text in BM_WALL_TO_CODE:
        return text
    if any(token in text for token in ("层次消失", "结构消失", "层次中断")):
        return "消失"
    if any(token in text for token in ("层次模糊", "结构模糊", "层次不清")):
        return "模糊"
    if any(token in text for token in ("层次清晰", "层次存在", "层次完整", "层次尚清")):
        return "存在"
    if text in {"其他", "其它"}:
        return "其他"
    return None


def parse_sizes_from_text(text: object) -> tuple[float | None, float | None]:
    raw = _nonempty(text)
    if raw is None:
        return None, None
    hits = _SIZE_RE.findall(raw)
    if not hits:
        return None, None
    diameters: list[float] = []
    thicknesses: list[float] = []
    for first, second, unit in hits:
        scale = 0.1 if unit.lower() in {"mm", "毫米"} else 1.0
        a = float(first) * scale
        diameters.append(a)
        if second:
            thicknesses.append(float(second) * scale)
    diameter = max(diameters) if diameters else None
    thickness = max(thicknesses) if thicknesses else None
    if diameter and thickness and thickness > diameter:
        diameter, thickness = thickness, diameter
    return diameter, thickness


def fields_from_report(payload: object) -> dict[str, Any]:
    """Accept bm_report, bm_report.fields, or a flat dict."""
    if not isinstance(payload, dict):
        return empty_fields()
    raw = payload.get("fields") if isinstance(payload.get("fields"), dict) else payload
    site = parse_lesion_site(raw.get("lesion_site") or raw.get("site") or raw.get("tumor_location"))
    diameter = _finite_positive(raw.get("maximum_diameter_cm") or raw.get("max_diameter_cm") or raw.get("tumor_length_cm"))
    thickness = _finite_positive(
        raw.get("maximum_thickness_cm") or raw.get("max_thickness_cm") or raw.get("tumor_thickness_cm")
    )
    ulcer = parse_ulcer_present(raw.get("ulcer_present") if "ulcer_present" in raw else raw.get("ulcer"))
    wall = parse_wall_layers(raw.get("wall_layers") or raw.get("layer_structure"))
    return {
        "lesion_site": site,
        "max_diameter_cm": diameter,
        "max_thickness_cm": thickness,
        "ulcer_present": ulcer,
        "wall_layers": wall,
        "wall_layers_other": _nonempty(raw.get("wall_layers_other")) or "",
    }


def fields_from_ultrasound_text(text: object) -> dict[str, Any]:
    raw = _nonempty(text) or ""
    diameter, thickness = parse_sizes_from_text(raw)
    return {
        "lesion_site": parse_lesion_site(raw),
        "max_diameter_cm": diameter,
        "max_thickness_cm": thickness,
        "ulcer_present": parse_ulcer_present(raw),
        "wall_layers": parse_wall_layers(raw),
        "wall_layers_other": "",
    }


def empty_fields() -> dict[str, Any]:
    return {
        "lesion_site": None,
        "max_diameter_cm": None,
        "max_thickness_cm": None,
        "ulcer_present": None,
        "wall_layers": None,
        "wall_layers_other": "",
    }


def merge_fields(*parts: dict[str, Any]) -> dict[str, Any]:
    out = empty_fields()
    for part in parts:
        if not part:
            continue
        for key in out:
            value = part.get(key)
            if value in (None, "", []):
                continue
            out[key] = value
    return out


def n_filled(fields: dict[str, Any]) -> int:
    return sum(
        1
        for key in BM_SIGN_FIELDS
        if fields.get(key) not in (None, "")
    )


def encode_fields(
    fields: dict[str, Any],
    norm_stats: dict[str, dict[str, float]] | None = None,
) -> list[float]:
    stats = norm_stats or DEFAULT_NORM_STATS
    vector: list[float] = []
    site = fields.get("lesion_site")
    if site in BM_SITE_TO_CODE:
        vector.extend([BM_SITE_TO_CODE[site] / BM_SITE_MAX_CODE, 0.0])
    else:
        vector.extend([0.0, 1.0])

    for name in ("max_diameter_cm", "max_thickness_cm"):
        value = _finite_positive(fields.get(name))
        if value is None:
            vector.extend([0.0, 1.0])
            continue
        mean = float(stats[name]["mean"])
        std = max(float(stats[name]["std"]), 1e-6)
        vector.extend([(value - mean) / std, 0.0])

    ulcer = fields.get("ulcer_present")
    if ulcer in (0, 1):
        vector.extend([float(ulcer), 0.0])
    else:
        vector.extend([0.0, 1.0])

    wall = fields.get("wall_layers")
    if wall in BM_WALL_TO_CODE:
        vector.extend([BM_WALL_TO_CODE[wall] / BM_WALL_MAX_CODE, 0.0])
    else:
        vector.extend([0.0, 1.0])
    if len(vector) != BM_SIGN_DIM:
        raise RuntimeError(f"bm_sign dim {len(vector)}, expected {BM_SIGN_DIM}")
    return vector


def encode_report(payload: object, norm_stats: dict[str, dict[str, float]] | None = None) -> dict[str, Any]:
    fields = fields_from_report(payload)
    vector = encode_fields(fields, norm_stats=norm_stats)
    return {
        "fields": fields,
        "vector": vector,
        "n_filled": n_filled(fields),
        "pack": BM_SIGN_PACK_NAME,
        "dim": BM_SIGN_DIM,
        "clinical11_location": BM_SITE_TO_CLINICAL11_LOCATION.get(fields.get("lesion_site")),
    }


def dumps_fields(fields: dict[str, Any]) -> str:
    return json.dumps(fields, ensure_ascii=False, sort_keys=True)
