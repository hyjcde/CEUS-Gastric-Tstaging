"""Case input loading for the deterministic agent pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.repo_paths import PROJECT_ROOT


class InputMode(str, Enum):
    STATIC = "static"
    VIDEO = "video"
    FRONTEND = "frontend"


@dataclass
class FrameRef:
    image_path: str
    roi_path: Optional[str] = None
    frame_id: Optional[str] = None
    frame_index: int = 0


@dataclass(frozen=True)
class ProspectiveCropAssets:
    """crop_ui 标注链路静帧 / overlay / ROI，与 clip 编号配对。"""

    sample_id: str
    sync_path: Path
    overlay_path: Path
    roi_path: Path


@dataclass
class CaseInput:
    case_id: str
    patient_id: str
    input_mode: InputMode
    frames: List[FrameRef]
    clinical: Dict[str, Any] = field(default_factory=dict)
    report_text: Dict[str, Any] = field(default_factory=dict)
    gt_t_stage: Optional[str] = None
    data_source: str = ""
    reference: Dict[str, Any] = field(default_factory=dict)
    video_path: Optional[str] = None
    clip_name: Optional[str] = None

    @property
    def primary_frame(self) -> FrameRef:
        if not self.frames:
            raise ValueError("CaseInput has no frames")
        return self.frames[0]

    @property
    def primary_image_path(self) -> str:
        return self.primary_frame.image_path

    @classmethod
    def from_cases_json(
        cls,
        cases_path: Path,
        case_id: str,
    ) -> "CaseInput":
        doc = json.loads(cases_path.read_text(encoding="utf-8"))
        case = next(c for c in doc.get("cases", []) if c.get("case_id") == case_id)
        frames: List[FrameRef] = []
        for idx, f in enumerate(case.get("frames", [])):
            img = f.get("image_path")
            if not img or not Path(img).exists():
                continue
            frames.append(
                FrameRef(
                    image_path=str(img),
                    roi_path=f.get("roi_path"),
                    frame_id=f.get("frame_id"),
                    frame_index=idx,
                )
            )
        if not frames:
            raise FileNotFoundError(f"{case_id}: no readable frames in cases.json")

        ref = case.get("reference_standard") or {}
        gt = ref.get("pathology_t_stage") if isinstance(ref, dict) else None
        clinical = dict(case.get("clinical") or {})
        return cls(
            case_id=case_id,
            patient_id=str(case.get("patient_id") or case_id),
            input_mode=InputMode.STATIC,
            frames=frames,
            clinical=clinical,
            gt_t_stage=str(gt) if gt else None,
            data_source=str(case.get("data_source") or clinical.get("source") or ""),
            reference=ref if isinstance(ref, dict) else {},
        )

    @classmethod
    def from_internal_prospective_video(
        cls,
        case_id: str,
        *,
        clip_index: int = 1,
        variant: str = "crop_ui",
        reader_root: Optional[Path] = None,
        n_key_frames: int = 4,
    ) -> "CaseInput":
        """
        2025 内部前瞻队列视频：dataset/internal/prospective_2025/2025/{crop_ui|raw}_patient_videos。

        case_id 对应 reader_study selected_cases（如 CASE-002 → patient 1465025）。
        """
        reader_root = reader_root or (
            PROJECT_ROOT / "docs" / "clinical_validation" / "reader_study_2025_raw"
        )
        patient_id, gt_t, clinical = _load_reader_case_meta(reader_root, case_id)
        if variant == "raw":
            video_root = (
                PROJECT_ROOT / "dataset" / "internal" / "prospective_2025" / "2025" / "raw_patient_videos"
            )
        else:
            video_root = (
                PROJECT_ROOT / "dataset" / "internal" / "prospective_2025" / "2025" / "crop_ui" / "videos"
            )
        clip_name = f"{patient_id}_({clip_index}).mp4"
        clip_path = video_root / clip_name
        if not clip_path.exists():
            raise FileNotFoundError(f"Internal prospective video not found: {clip_path}")

        frames = _extract_key_frames_from_clip(case_id, clip_path, n_key_frames=n_key_frames)
        if not clinical.get("cohort"):
            clinical["cohort"] = "prospective"
        clinical.setdefault("source", "int/prospective")

        return cls(
            case_id=case_id,
            patient_id=str(patient_id),
            input_mode=InputMode.VIDEO,
            frames=frames,
            clinical=clinical,
            gt_t_stage=gt_t,
            video_path=str(clip_path),
            clip_name=clip_name,
            data_source="int/prospective_2025",
        )

    @classmethod
    def from_reader_study_video(
        cls,
        case_id: str,
        clip: str = "clip_01.mp4",
        reader_root: Optional[Path] = None,
        n_key_frames: int = 4,
    ) -> "CaseInput":
        reader_root = reader_root or (
            PROJECT_ROOT / "docs" / "clinical_validation" / "reader_study_2025_raw"
        )
        case_dir = reader_root / "images" / case_id
        clip_path = case_dir / clip
        if not clip_path.exists():
            raise FileNotFoundError(f"Video clip not found: {clip_path}")

        patient_id, gt_t, clinical = _load_reader_case_meta(reader_root, case_id)
        frames = _extract_key_frames_from_clip(case_id, clip_path, n_key_frames=n_key_frames)

        return cls(
            case_id=case_id,
            patient_id=str(patient_id),
            input_mode=InputMode.VIDEO,
            frames=frames,
            clinical=clinical,
            gt_t_stage=gt_t,
            video_path=str(clip_path),
            clip_name=clip,
            data_source="reader_study_2025_raw",
        )

    @classmethod
    def from_frontend_payload(cls, payload: Dict[str, Any]) -> "CaseInput":
        frame_plan: List[FrameRef] = []
        raw_frames = payload.get("frames") or []
        if raw_frames:
            for idx, f in enumerate(raw_frames):
                if isinstance(f, dict) and f.get("image_path"):
                    frame_plan.append(
                        FrameRef(
                            image_path=str(f["image_path"]),
                            roi_path=f.get("roi_path"),
                            frame_index=idx,
                        )
                    )
        elif payload.get("image_path"):
            frame_plan.append(
                FrameRef(
                    image_path=str(payload["image_path"]),
                    roi_path=payload.get("roi_path"),
                    frame_index=0,
                )
            )
        if not frame_plan:
            raise ValueError("frontend payload missing image_path / frames[]")

        clinical_raw = payload.get("clinical") or {}
        return cls(
            case_id=str(payload.get("case_token") or payload.get("patient_id") or "unknown"),
            patient_id=str(payload.get("patient_id") or "unknown"),
            input_mode=InputMode.FRONTEND,
            frames=frame_plan,
            clinical=clinical_raw if isinstance(clinical_raw, dict) else {},
            report_text=payload.get("report_text") or {},
            data_source=str(payload.get("data_source") or ""),
        )


def _pick_key_frame_indices(sampled: List[Dict[str, Any]], n: int) -> List[int]:
    if len(sampled) <= n:
        return list(range(len(sampled)))
    scores = [float(s.get("motion_delta", 0)) + float(s.get("sharpness", 0)) for s in sampled]
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    picked = sorted(order[:n])
    return picked


def resolve_prospective_crop_assets(
    patient_id: str,
    clip_index: int,
    *,
    year_root: Optional[Path] = None,
) -> Optional[ProspectiveCropAssets]:
    """
    前瞻 crop_ui 标注资产：images / overlays / crop_roi，按 patient + clip 序号解析。

    例：1465025 + clip_index=1 → 2025直接手术__1465025_(1).jpg
    """
    root = year_root or (PROJECT_ROOT / "dataset" / "internal" / "prospective_2025" / "2025")
    token = f"{patient_id}_({clip_index})"
    images_dir = root / "crop_ui" / "images"
    matches = sorted(images_dir.glob(f"*__{token}.jpg"))
    if not matches:
        matches = sorted(images_dir.glob(f"*{token}.jpg"))
    if not matches:
        return None
    sample_stem = matches[0].stem
    overlay = root / "crop_ui" / "overlays" / f"{sample_stem}_overlay.jpg"
    roi = root / "crop_roi" / "images" / f"{sample_stem}.jpg"
    if not overlay.exists() or not roi.exists():
        return None
    return ProspectiveCropAssets(
        sample_id=sample_stem,
        sync_path=matches[0],
        overlay_path=overlay,
        roi_path=roi,
    )


def _load_reader_case_meta(reader_root: Path, case_id: str) -> tuple[str, Optional[str], Dict[str, Any]]:
    import csv

    patient_id = case_id
    gt_t: Optional[str] = None
    selected_path = reader_root / "selected_cases.csv"
    if selected_path.exists():
        with selected_path.open(encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                if row.get("case_id") == case_id:
                    patient_id = row.get("patient_id") or case_id
                    gt_t = row.get("pathology_t_stage") or gt_t
                    break
    clinical = _clinical_from_reader_csv(reader_root / "clinical_for_reading.csv", case_id)
    return str(patient_id), gt_t, clinical


def _extract_key_frames_from_clip(
    case_id: str,
    clip_path: Path,
    *,
    n_key_frames: int = 4,
) -> List[FrameRef]:
    import sys

    import cv2

    scripts_dir = PROJECT_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from generate_video_deep_dive import sample_video  # type: ignore

    sampled = sample_video(Path(clip_path), max_frames=64)
    rgb_frames = sampled["rgb_frames"]
    motion = sampled.get("motion_scores", [])
    sharpness = sampled.get("sharpness", [])
    frame_items = [
        {
            "motion_delta": float(motion[i]) if i < len(motion) else 0.0,
            "sharpness": float(sharpness[i]) if i < len(sharpness) else 0.0,
        }
        for i in range(len(rgb_frames))
    ]
    key_indices = _pick_key_frame_indices(frame_items, n_key_frames)
    tmp_dir = PROJECT_ROOT / "docs" / "agent" / "clinical_report_assets" / "_tmp_frames"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    frames: List[FrameRef] = []
    for i, idx in enumerate(key_indices):
        rgb = rgb_frames[idx]
        out_path = tmp_dir / f"{case_id}_k{i}.jpg"
        cv2.imwrite(str(out_path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        frames.append(
            FrameRef(
                image_path=str(out_path),
                frame_id=f"key_{i}",
                frame_index=i,
            )
        )
    return frames


def _clinical_from_reader_csv(csv_path: Path, case_id: str) -> Dict[str, Any]:
    import csv

    with csv_path.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            if row.get("case_id") == case_id or row.get("display_id") == case_id:
                return {k: v for k, v in row.items() if v not in (None, "")}
    return {}
