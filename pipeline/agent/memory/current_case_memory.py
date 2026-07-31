from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from ..core.repo_paths import PROJECT_ROOT, TMP_DIR

CACHE_DIR = TMP_DIR / "agent_case_memory"
CACHE_PATH = CACHE_DIR / "current_case_memory.json"
CACHE_VERSION = 2


def _extract_patient_id(filename: str) -> str:
    stem = re.sub(r"\.[^.]+$", "", filename)
    z_match = re.search(r"(Z\d{7,})", stem, re.I)
    if z_match:
        return z_match.group(1).upper()

    matches = re.findall(r"\d{6,}", stem)
    return matches[-1] if matches else stem


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_binary(value: Any) -> float:
    return 1.0 if value else 0.0


def _map_sex(value: Any) -> float:
    text = str(value or "").strip().lower()
    if text in {"male", "男", "1"}:
        return 1.0
    if text in {"female", "女", "0"}:
        return 0.0
    return 0.0


def _map_lauren(value: Any) -> float:
    text = str(value or "").strip().lower()
    mapping = {"intestinal": 1.0, "1": 1.0, "diffuse": 2.0, "2": 2.0, "mixed": 3.0, "3": 3.0}
    return mapping.get(text, 0.0)


def _map_diff(value: Any) -> float:
    text = str(value or "").strip().lower()
    mapping = {
        "well differentiated": 1.0,
        "well": 1.0,
        "moderately differentiated": 2.0,
        "moderate": 2.0,
        "moderately-poorly differentiated": 3.0,
        "poorly differentiated": 3.0,
        "poor": 3.0,
        "undetermined": 4.0,
        "4": 4.0,
    }
    return mapping.get(text, _safe_float(value))


def _stage_from_clinical(entry: Dict[str, Any]) -> str:
    pathology = entry.get("pathology") if isinstance(entry, dict) else None
    p_t = ""
    if isinstance(pathology, dict):
        p_t = str(pathology.get("pT", "")).strip()
    mapping = {
        "1": "T1",
        "1.0": "T1",
        "2": "T2",
        "2.0": "T2",
        "3": "T3",
        "3.0": "T3",
        "4": "T4a",
        "4.0": "T4a",
        "5": "T4b",
        "5.0": "T4b",
    }
    return mapping.get(p_t, "unknown")


def _vector_from_record(record: Dict[str, Any]) -> np.ndarray:
    clinical = record.get("clinical", {}) or {}
    biomarkers = clinical.get("biomarkers", {}) if isinstance(clinical, dict) else {}
    tumor_size = clinical.get("tumorSize", {}) if isinstance(clinical, dict) else {}
    pathology = clinical.get("pathology", {}) if isinstance(clinical, dict) else {}

    vector = np.zeros(17, dtype=np.float32)
    vector[4] = record.get("annotation_ratio", 0.0)
    vector[5] = record.get("overlay_ratio", 0.0)
    vector[6] = record.get("roi_ratio", 0.0)
    vector[7] = min(record.get("frame_count", 0), 50) / 50.0
    vector[8] = 1.0 if record.get("cohort_year") == "2025" else 0.0
    vector[9] = _safe_float(clinical.get("age")) / 100.0
    vector[10] = _map_sex(clinical.get("sex"))
    vector[11] = 0.0
    vector[12] = _safe_float(tumor_size.get("length")) / 10.0
    vector[13] = _safe_float(tumor_size.get("thickness")) / 5.0
    vector[14] = _safe_binary(biomarkers.get("cea_positive"))
    vector[15] = _safe_binary(biomarkers.get("ca199_positive"))
    vector[16] = _map_diff(pathology.get("differentiation")) / 4.0
    return vector


@dataclass
class CurrentCaseMemory:
    cache_path: Path = CACHE_PATH

    def __post_init__(self):
        self.records: List[Dict[str, Any]] = []
        self._load_or_build()

    def _load_or_build(self) -> None:
        if self.cache_path.exists():
            loaded = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if loaded and isinstance(loaded, dict) and loaded.get("cache_version") == CACHE_VERSION:
                records = loaded.get("records", [])
                if records and len(records[0].get("vector", [])) == 17:
                    self.records = records
                    return

        self.records = self._build_records()
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps({"cache_version": CACHE_VERSION, "records": self.records}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _build_records(self) -> List[Dict[str, Any]]:
        cohorts = [
            {
                "cohort_year": "2025",
                "label": "internal-2025-surgery",
                "images_dir": PROJECT_ROOT / "dataset" / "internal" / "prospective_2025" / "2025" / "original" / "images",
                "annotations_dir": PROJECT_ROOT / "dataset" / "internal" / "prospective_2025" / "2025" / "original" / "annotations",
                "overlays_dir": PROJECT_ROOT / "dataset" / "internal" / "prospective_2025" / "2025" / "original" / "overlays",
                "roi_dir": PROJECT_ROOT / "dataset" / "internal" / "prospective_2025" / "2025" / "crop_roi" / "images",
                "clinical_path": PROJECT_ROOT / "apps" / "gastric_scan_next" / "data" / "clinical_data.json",
            },
            {
                "cohort_year": "2024",
                "label": "internal-2024-surgery",
                "images_dir": PROJECT_ROOT / "dataset" / "internal" / "training_2018_2024" / "2024" / "original" / "images",
                "annotations_dir": PROJECT_ROOT / "dataset" / "internal" / "training_2018_2024" / "2024" / "original" / "annotations",
                "overlays_dir": PROJECT_ROOT / "dataset" / "internal" / "training_2018_2024" / "2024" / "original" / "overlays",
                "roi_dir": PROJECT_ROOT / "dataset" / "internal" / "training_2018_2024" / "2024" / "crop_roi" / "images",
                "clinical_path": PROJECT_ROOT / "apps" / "gastric_scan_next" / "data" / "clinical_data_2024.json",
            },
        ]

        records: List[Dict[str, Any]] = []
        for cohort in cohorts:
            clinical_data = {}
            if cohort["clinical_path"].exists():
                clinical_data = json.loads(cohort["clinical_path"].read_text(encoding="utf-8"))

            grouped: Dict[str, Dict[str, Any]] = {}
            for filename in sorted(os.listdir(cohort["images_dir"])):
                if filename.startswith(".") or not filename.lower().endswith((".jpg", ".jpeg")):
                    continue
                patient_id = _extract_patient_id(filename)
                record = grouped.setdefault(patient_id, {
                    "patient_id": patient_id,
                    "cohort_year": cohort["cohort_year"],
                    "data_source": cohort["label"],
                    "frame_count": 0,
                    "annotation_count": 0,
                    "overlay_count": 0,
                    "roi_count": 0,
                    "image_names": [],
                })
                record["frame_count"] += 1
                record["image_names"].append(filename)
                if (cohort["annotations_dir"] / re.sub(r"\.(jpg|jpeg)$", ".json", filename, flags=re.I)).exists():
                    record["annotation_count"] += 1
                if (cohort["overlays_dir"] / re.sub(r"\.(jpg|jpeg)$", "_overlay.jpg", filename, flags=re.I)).exists():
                    record["overlay_count"] += 1
                if (cohort["roi_dir"] / filename).exists():
                    record["roi_count"] += 1

            for patient_id, record in grouped.items():
                clinical = clinical_data.get(patient_id) or clinical_data.get(patient_id.lstrip("0")) or clinical_data.get(patient_id.upper()) or {}
                frame_count = max(record["frame_count"], 1)
                record["annotation_ratio"] = round(record["annotation_count"] / frame_count, 4)
                record["overlay_ratio"] = round(record["overlay_count"] / frame_count, 4)
                record["roi_ratio"] = round(record["roi_count"] / frame_count, 4)
                record["clinical"] = clinical
                record["T_stage"] = _stage_from_clinical(clinical)
                record["vector"] = _vector_from_record(record).tolist()
                records.append(record)

        return records

    def search(
        self,
        query_vector: List[float] | np.ndarray,
        top_k: int = 5,
        cohort_year: Optional[str] = None,
        exclude_patient_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not self.records:
            return []

        query = np.asarray(query_vector, dtype=np.float32)
        if query.ndim == 1:
            query = query.reshape(1, -1)

        scored: List[Dict[str, Any]] = []
        for record in self.records:
            if cohort_year and record.get("cohort_year") != cohort_year:
                continue
            if exclude_patient_id and str(record.get("patient_id")) == str(exclude_patient_id):
                continue

            vector = np.asarray(record.get("vector", []), dtype=np.float32)
            if vector.size == 0:
                continue
            denom = (np.linalg.norm(query[0]) * np.linalg.norm(vector)) or 1.0
            similarity = float(np.dot(query[0], vector) / denom)
            preview_image_path = None
            image_names = record.get("image_names") or []
            if image_names:
                images_dir = None
                for cohort in (
                    {
                        "cohort_year": "2025",
                        "images_dir": PROJECT_ROOT / "dataset" / "internal" / "prospective_2025" / "2025" / "original" / "images",
                    },
                    {
                        "cohort_year": "2024",
                        "images_dir": PROJECT_ROOT / "dataset" / "internal" / "training_2018_2024" / "2024" / "original" / "images",
                    },
                ):
                    if cohort["cohort_year"] == record.get("cohort_year"):
                        images_dir = cohort["images_dir"]
                        break
                if images_dir and images_dir.exists():
                    candidate = images_dir / image_names[0]
                    if candidate.exists():
                        preview_image_path = str(candidate)

            scored.append({
                "patient_id": record["patient_id"],
                "cohort_year": record["cohort_year"],
                "data_source": record["data_source"],
                "T_stage": record.get("T_stage", "unknown"),
                "frame_count": record.get("frame_count", 0),
                "annotation_ratio": record.get("annotation_ratio", 0.0),
                "overlay_ratio": record.get("overlay_ratio", 0.0),
                "roi_ratio": record.get("roi_ratio", 0.0),
                "similarity": round(similarity, 4),
                "preview_image_path": preview_image_path,
            })

        scored.sort(key=lambda item: item["similarity"], reverse=True)
        return scored[:top_k]

