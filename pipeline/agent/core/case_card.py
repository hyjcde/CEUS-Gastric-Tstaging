"""
Patient-level CaseCard: the fundamental input unit for the abdominal ultrasound Agent.

Each CaseCard aggregates all frames, annotations, ROI, masks, and
whitelisted clinical information for one patient. Fields that could
leak the ground-truth label (pathology, pT_stage, discharge_diagnosis)
are strictly excluded.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import unquote

from .repo_paths import PROJECT_ROOT, get_predicted_masks_dir

logger = logging.getLogger(__name__)

PATIENTS_DIR = PROJECT_ROOT / "dataset" / "patients"
PREDICTED_MASKS_DIR = get_predicted_masks_dir()

# ── privacy whitelist / blacklist ─────────────────────────────────────
CLINICAL_WHITELIST = {
    "age", "sex",
    "tumor_location", "tumor_length_cm", "tumor_thickness_cm",
    "CEA_value", "CEA_status", "CA199_value", "CA199_status",
    "differentiation", "lauren_type",
}

CLINICAL_BLACKLIST = {
    "pathology", "discharge_diagnosis",
    "pT_stage", "pN_stage_detailed", "N_positive", "pM_stage", "pStage",
    "name", "data_sources",
}


# ── dataclasses ───────────────────────────────────────────────────────
@dataclass
class FrameInfo:
    """Information for a single ultrasound frame."""
    image_path: str
    frame_index: int = 0
    annotation_path: Optional[str] = None
    overlay_path: Optional[str] = None
    roi_path: Optional[str] = None
    predicted_mask_path: Optional[str] = None


_LOCATION_LABELS = {0: "cardia", 1: "upper/fundus", 2: "body", 3: "antrum/pylorus"}
_DIFF_LABELS = {1: "well", 2: "moderate", 3: "poor", 4: "undifferentiated"}
_LAUREN_LABELS = {1: "intestinal", 2: "diffuse", 3: "mixed"}


@dataclass
class ClinicalInfo:
    """Whitelisted clinical features (all optional)."""
    age: Optional[int] = None
    sex: Optional[int] = None               # 0=female, 1=male
    tumor_location: Optional[int] = None
    tumor_length_cm: Optional[float] = None
    tumor_thickness_cm: Optional[float] = None
    CEA_value: Optional[str] = None
    CEA_status: Optional[int] = None
    CA199_value: Optional[str] = None
    CA199_status: Optional[int] = None
    differentiation: Optional[int] = None
    lauren_type: Optional[int] = None
    gross_type: Optional[str] = None        # "ulcerative"/"elevated"/"infiltrative"

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def to_agent_dict(self) -> Dict[str, Any]:
        """Human-readable version for the LLM context."""
        d = self.to_dict()
        loc = d.get("tumor_location")
        if loc is not None:
            d["tumor_location_name"] = _LOCATION_LABELS.get(loc, f"code_{loc}")
        diff = d.get("differentiation")
        if diff is not None:
            d["differentiation_name"] = _DIFF_LABELS.get(diff, f"grade_{diff}")
        lt = d.get("lauren_type")
        if lt is not None:
            d["lauren_type_name"] = _LAUREN_LABELS.get(lt, f"type_{lt}")
        return d

    def has_any(self) -> bool:
        return any(v is not None for v in asdict(self).values())


@dataclass
class CaseCard:
    """
    Patient-level case card — the standard input unit for the agent.

    Contains multi-frame visual assets, optional clinical info, and
    metadata. Ground-truth labels are stored separately for evaluation
    but never exposed to the agent during inference.
    """
    patient_id: str
    data_source: str                         # e.g. "internal/prospective"
    frames: List[FrameInfo] = field(default_factory=list)
    clinical: Optional[ClinicalInfo] = None

    # Ground-truth kept for evaluation only — NEVER passed to the agent
    gt_T_stage: Optional[str] = None         # "T1" / "T2" / "T3" / "T4a" ...
    gt_T_label: Optional[int] = None         # 0-3
    gt_label_bm: Optional[str] = None        # "malignant" / "benign"

    @property
    def num_frames(self) -> int:
        return len(self.frames)

    def to_agent_context(self) -> Dict[str, Any]:
        """
        Produce a dict safe to show the LLM — no file paths, no GT labels,
        no blacklisted clinical fields.
        """
        ctx: Dict[str, Any] = {
            "patient_id": self.patient_id,
            "data_source": self.data_source,
            "num_frames": self.num_frames,
        }
        if self.clinical and self.clinical.has_any():
            ctx["clinical"] = self.clinical.to_agent_dict()
        return ctx

    def to_dict(self) -> Dict[str, Any]:
        """Full serialisation (for local storage / debugging)."""
        d: Dict[str, Any] = {
            "patient_id": self.patient_id,
            "data_source": self.data_source,
            "num_frames": self.num_frames,
            "frames": [asdict(f) for f in self.frames],
        }
        if self.clinical:
            d["clinical"] = self.clinical.to_dict()
        if self.gt_T_stage is not None:
            d["gt_T_stage"] = self.gt_T_stage
            d["gt_T_label"] = self.gt_T_label
        return d


# ── loaders ───────────────────────────────────────────────────────────

def _safe_int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, str):
        val = val.strip().replace("/", "")
        if not val:
            return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _extract_gross_type(raw: Dict[str, Any]) -> Optional[str]:
    """Extract tumour gross type from pathology / discharge text.

    Gross type (大体分型) is observable during endoscopy — it does NOT leak
    invasion depth.  However, ulcerative tumours behave differently on abdominal ultrasound:
    peri-ulcer fibrosis and inflammation mimic deeper invasion, leading to
    overstaging bias.  The LLM Agent can use this to calibrate.
    """
    text = ""
    for key in ("pathology", "pathology_diagnosis", "discharge_diagnosis"):
        val = raw.get(key)
        if val and isinstance(val, str) and len(val) > 3:
            text += val + " "
    if not text:
        return None
    if "溃疡型" in text or "溃疡" in text:
        return "ulcerative"
    if "浸润型" in text or "弥漫浸润" in text:
        return "infiltrative"
    if "隆起型" in text or "隆起" in text:
        return "elevated"
    return None


def _parse_clinical(raw: Dict[str, Any]) -> Optional[ClinicalInfo]:
    """Extract whitelisted clinical fields, coerce types."""
    filtered = {k: raw.get(k) for k in CLINICAL_WHITELIST if k in raw}
    if not filtered:
        return None

    return ClinicalInfo(
        age=_safe_int(filtered.get("age")),
        sex=_safe_int(filtered.get("sex")),
        tumor_location=_safe_int(filtered.get("tumor_location")),
        tumor_length_cm=_safe_float(filtered.get("tumor_length_cm")),
        tumor_thickness_cm=_safe_float(filtered.get("tumor_thickness_cm")),
        CEA_value=filtered.get("CEA_value") if isinstance(filtered.get("CEA_value"), str) else None,
        CEA_status=_safe_int(filtered.get("CEA_status")),
        CA199_value=filtered.get("CA199_value") if isinstance(filtered.get("CA199_value"), str) else None,
        CA199_status=_safe_int(filtered.get("CA199_status")),
        differentiation=_safe_int(filtered.get("differentiation")),
        lauren_type=_safe_int(filtered.get("lauren_type")),
        gross_type=_extract_gross_type(raw),
    )


def _resolve_predicted_mask(image_path: str,
                            mask_dir: Path = PREDICTED_MASKS_DIR) -> Optional[str]:
    """Derive predicted mask path from image path stem."""
    stems = []
    raw_stem = Path(image_path).stem
    stems.append(raw_stem)
    if "__" in raw_stem:
        stems.append(raw_stem.split("__")[-1])

    expanded: List[str] = []
    for stem in stems:
        expanded.append(stem)
        expanded.append(stem.replace("_(", " ("))
        expanded.append(stem.replace("pty", "pt", 1))
        expanded.append(stem.replace("pty", "pt", 1).replace("_(", " ("))

    seen = set()
    for stem in expanded:
        if not stem or stem in seen:
            continue
        seen.add(stem)
        for ext in (".png", ".jpg", ".npy"):
            candidate = mask_dir / f"{stem}{ext}"
            if candidate.exists():
                return str(candidate)
    return None


def _resolve_legacy_csv_asset(path_value: Any, source: str) -> Optional[str]:
    if path_value is None:
        return None

    raw = str(path_value).strip()
    if not raw or raw.lower() == "nan":
        return None

    decoded = unquote(raw)
    absolute = Path(decoded)
    if absolute.is_absolute() and absolute.exists():
        return str(absolute)

    direct = PROJECT_ROOT / decoded
    if direct.exists():
        return str(direct)

    parts = Path(decoded).parts
    if len(parts) < 4 or parts[0] != "dataset":
        return str(direct)

    filename = parts[-1]
    if filename.endswith("_roi.jpg"):
        filename = filename[:-8] + ".jpg"

    def _first_existing(paths: List[Path]) -> Optional[str]:
        for candidate in paths:
            if candidate.exists():
                return str(candidate)
        return None

    def _search_by_token(target_dir: Path, raw_name: str) -> Optional[str]:
        if not target_dir.exists():
            return None

        stem = Path(raw_name).stem
        frame_markers = re.findall(r"\((\d+)\)|-(\d+)$", stem)
        flat_markers = [item for pair in frame_markers for item in pair if item]

        token_candidates: List[str] = []
        for candidate in [
            stem,
            stem.replace(" (", "_("),
            stem.replace("pty", "pt", 1),
            stem.replace("pty", "pt", 1).replace(" (", "_("),
        ]:
            if candidate:
                token_candidates.append(candidate)

        token_candidates.extend(re.findall(r"Z\d{6,}|[A-Za-z]*\d{5,}[A-Za-z0-9-]*", stem))

        seen_tokens = set()
        ordered_tokens = []
        for token in sorted(token_candidates, key=len, reverse=True):
            if token and token not in seen_tokens:
                seen_tokens.add(token)
                ordered_tokens.append(token)

        for token in ordered_tokens:
            matches = list(target_dir.glob(f"*{token}*.*"))
            if not matches:
                continue
            if flat_markers:
                for marker in flat_markers:
                    filtered = [
                        match for match in matches
                        if f"({marker})" in match.stem or match.stem.endswith(f"-{marker}")
                    ]
                    if filtered:
                        return str(filtered[0])
            return str(matches[0])
        return None

    if parts[1] == "internal":
        split_name = parts[2]
        leaf = parts[4] if len(parts) > 4 else parts[-2]
        if split_name == "train" and len(parts) >= 6:
            year = parts[3]
            cohort_root = PROJECT_ROOT / "dataset" / "internal" / "training_2018_2024" / year
        elif split_name == "prospective":
            cohort_root = PROJECT_ROOT / "dataset" / "internal" / "prospective_2025" / "2025"
        else:
            return str(direct)

        subdir = Path("crop_roi") / "images" if leaf == "roi" else Path("original") / "images"
        candidate = cohort_root / subdir / filename
        if candidate.exists():
            return str(candidate)
        searched = _search_by_token(cohort_root / subdir, filename)
        if searched:
            return searched
        return str(candidate)

    if parts[1] == "external" and len(parts) >= 5:
        legacy_source = parts[2]
        leaf = parts[3]
        current_subdir = Path("crop_roi/images") if leaf == "roi" else Path("original/images")

        source_folders = {
            "putian": ["莆田1胃癌直接手术"],
            "putian_2024_new": ["莆田1胃癌直接手术", "莆田2胃癌直接手术"],
            "multicenter": ["肿瘤医院直接手术", "三明胃癌直接手术"],
            "zhongliu": ["肿瘤医院直接手术"],
        }.get(legacy_source, [])

        normalized_names = []
        base_name = filename
        normalized_names.append(base_name)
        normalized_names.append(base_name.replace("pty", "pt", 1))
        normalized_names.append(base_name.replace(" (", "_("))
        normalized_names.append(base_name.replace("pty", "pt", 1).replace(" (", "_("))

        for folder_name in source_folders:
            target_dir = PROJECT_ROOT / "dataset" / "external" / folder_name / current_subdir
            exact = _first_existing([target_dir / name for name in normalized_names])
            if exact:
                return exact

            for name in normalized_names:
                searched = _search_by_token(target_dir, name)
                if searched:
                    return searched

        return str(PROJECT_ROOT / decoded)

    return str(direct)


def load_case_card_from_patient_info(json_path: Path,
                                     mask_dir: Path = PREDICTED_MASKS_DIR) -> CaseCard:
    """
    Build a CaseCard from a patient_info.json file.

    Ground-truth labels are read for evaluation but kept separate
    from the agent-visible context.
    """
    with open(json_path) as f:
        info = json.load(f)

    patient_id = info["patient_id"]
    data_source = info.get("dataset", "unknown")

    # ── frames ────────────────────────────────────────────────────
    frames: List[FrameInfo] = []
    images = info.get("images", [])
    ann_map = {a["filename"].replace(".json", ""): a["path"]
               for a in info.get("annotations", [])}
    ov_map = {o["filename"].replace("_overlay.jpg", ""): o["path"]
              for o in info.get("overlays", [])}
    roi_map = {r["filename"].replace("_roi.jpg", ""): r["path"]
               for r in info.get("roi", [])}

    for img in images:
        img_path = img["path"]
        img_stem = Path(img["filename"]).stem

        frames.append(FrameInfo(
            image_path=img_path,
            frame_index=img.get("frame", 0),
            annotation_path=ann_map.get(img_stem),
            overlay_path=ov_map.get(img_stem),
            roi_path=roi_map.get(img_stem),
            predicted_mask_path=_resolve_predicted_mask(img_path, mask_dir),
        ))

    # ── clinical (whitelisted only) ───────────────────────────────
    clinical = None
    if "clinical_info" in info:
        clinical = _parse_clinical(info["clinical_info"])

    # ── ground-truth labels (for evaluation, not for agent) ───────
    gt_T_stage = info.get("T_stage")
    gt_T_label = _safe_int(info.get("T_label"))
    gt_label_bm = info.get("label_bm")

    return CaseCard(
        patient_id=patient_id,
        data_source=data_source,
        frames=frames,
        clinical=clinical,
        gt_T_stage=gt_T_stage,
        gt_T_label=gt_T_label,
        gt_label_bm=gt_label_bm,
    )


def load_case_cards_from_csv(csv_path: Path,
                             patients_dir: Path = PATIENTS_DIR,
                             mask_dir: Path = PREDICTED_MASKS_DIR,
                             require_existing_images: bool = False) -> List[CaseCard]:
    """
    Build CaseCards for all unique patients in a pipeline CSV
    (e.g. test_prospective.csv). Falls back to CSV-only construction
    when patient_info.json is not found.
    """
    import pandas as pd

    df = pd.read_csv(csv_path)
    if "patient_id" not in df.columns:
        raise ValueError(f"CSV {csv_path} missing 'patient_id' column")

    cards: List[CaseCard] = []
    seen: set = set()

    for pid, group in df.groupby("patient_id"):
        pid_str = str(pid)
        if pid_str in seen:
            continue
        seen.add(pid_str)

        # Try to find patient_info.json
        json_found = False
        if patients_dir.exists():
            for subdir in patients_dir.iterdir():
                candidate = subdir / pid_str / "patient_info.json"
                if candidate.exists():
                    cards.append(load_case_card_from_patient_info(candidate, mask_dir))
                    json_found = True
                    break

        if json_found:
            continue

        # Fallback: build from CSV rows directly
        source = group["source"].iloc[0] if "source" in group.columns else "unknown"
        frames = []
        for _, row in group.iterrows():
            img_path = _resolve_legacy_csv_asset(row["image_path"], source)
            roi_path = _resolve_legacy_csv_asset(row.get("roi_path"), source)
            frames.append(FrameInfo(
                image_path=str(img_path) if img_path else "",
                roi_path=str(roi_path) if roi_path else None,
                predicted_mask_path=_resolve_predicted_mask(str(img_path), mask_dir) if img_path else None,
            ))

        gt_stage = group["T_stage"].iloc[0] if "T_stage" in group.columns else None
        gt_label = _safe_int(group["label"].iloc[0]) if "label" in group.columns else None

        cards.append(CaseCard(
            patient_id=pid_str,
            data_source=source,
            frames=frames,
            gt_T_stage=gt_stage,
            gt_T_label=gt_label,
            gt_label_bm="malignant",
        ))

    if require_existing_images:
        filtered: List[CaseCard] = []
        for card in cards:
            valid_frames = [
                frame for frame in card.frames
                if frame.image_path and Path(frame.image_path).exists()
            ]
            if not valid_frames:
                continue
            card.frames = valid_frames
            filtered.append(card)
        cards = filtered

    logger.info("Loaded %d CaseCards from %s", len(cards), csv_path.name)
    return cards
