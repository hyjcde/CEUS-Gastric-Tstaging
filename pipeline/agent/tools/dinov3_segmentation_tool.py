"""
DINOv3SegmentationTool — candidate lesion segmentation backend for Agent use.

This adapter keeps the DINOv3 candidate behind the same tool-style contract as
the deployed UNet segmentation tool. It is intentionally lazy-loaded because the
backbone is heavy and should only be instantiated when the Agent actually asks
for candidate segmentation evidence.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np
import torch
import yaml

from .base import BaseTool, ToolParameter
from .segmentation_tool import crop_roi_from_mask
from ..core.repo_paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

SCRIPT_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

DEFAULT_BACKEND_ID = "lesion_segmentation_dinov3_vitb16_last2blocks_candidate_20260512"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "segmentation" / "dinov3" / "vitb16_last_blocks_adapter.yaml"
DEFAULT_RUN_MANIFEST = (
    PROJECT_ROOT
    / "experiments"
    / "segmentation"
    / "segmentation_dinov3_vitb16_last2blocks_holdout_cropui_dataset_v20260409_20260511_r001"
    / "dinov3_run_manifest.json"
)
DEFAULT_CHECKPOINT = (
    PROJECT_ROOT
    / "experiments"
    / "segmentation"
    / "segmentation_dinov3_vitb16_last2blocks_holdout_cropui_dataset_v20260409_20260511_r001"
    / "checkpoints"
    / "best.pt"
)
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
VALIDATION_SUMMARY = {
    "internal_holdout_dice": 0.7499,
    "internal_holdout_iou": 0.6269,
    "internal_holdout_zero_dice_ratio": 0.0082,
    "external_eval_dice": 0.6820,
    "external_eval_iou": 0.5524,
    "external_eval_zero_dice_ratio": 0.0172,
    "prospective_eval_dice": 0.7144,
    "prospective_eval_iou": 0.5900,
    "prospective_eval_zero_dice_ratio": 0.0185,
    "baseline": "lesion_segmentation_unetplusplus_resnet34_imagenet_cropui_20260415",
    "external_dice_delta_vs_baseline": 0.0383,
    "prospective_dice_delta_vs_baseline": -0.0056,
}


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return payload


def _resolve_project_path(value: str | Path | None, *, required: bool = True) -> Optional[Path]:
    if value in (None, ""):
        if required:
            raise ValueError("Missing required path")
        return None
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


class DINOv3SegmentationTool(BaseTool):
    name = "segment_dinov3_candidate"
    description = (
        "Run the DINOv3 ViT-B/16 last-2-block candidate lesion segmentation "
        "backend. Returns mask/ROI evidence plus backend provenance."
    )
    parameters = [
        ToolParameter("image_path", "str", "Absolute path to the crop_ui ultrasound image"),
        ToolParameter("output_dir", "str", "Optional directory for saving mask and probability map", required=False),
        ToolParameter("threshold", "float", "Segmentation probability threshold", required=False, default=0.5),
    ]

    def __init__(
        self,
        config_path: Path = DEFAULT_CONFIG_PATH,
        checkpoint_path: Path = DEFAULT_CHECKPOINT,
        run_manifest_path: Path = DEFAULT_RUN_MANIFEST,
        backend_id: str = DEFAULT_BACKEND_ID,
        device: Optional[torch.device] = None,
        trust_label: str = "caution",
    ) -> None:
        self.config_path = config_path
        self.checkpoint_path = checkpoint_path
        self.run_manifest_path = run_manifest_path
        self.backend_id = backend_id
        self.trust_label = trust_label
        self.device = device or torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        self._model: Optional[torch.nn.Module] = None
        self._config: Optional[dict] = None
        self._load_error: Optional[str] = None
        self._mask_cache: Dict[str, np.ndarray] = {}
        self._prob_cache: Dict[str, np.ndarray] = {}

    def _load_model(self) -> torch.nn.Module:
        from run_dinov3_segmentation import build_dinov3_model

        config = _load_yaml(self.config_path)
        paths_cfg = dict(config.get("paths", {}))
        paths_cfg["checkpoint_path"] = str(_resolve_project_path(paths_cfg.get("checkpoint_path")))
        model = build_dinov3_model(config.get("model", {}), paths_cfg)
        checkpoint_path = self.checkpoint_path
        if not checkpoint_path.exists() and self.run_manifest_path.exists():
            manifest = json.loads(self.run_manifest_path.read_text(encoding="utf-8"))
            checkpoint_path = Path(manifest.get("best_checkpoint", checkpoint_path)).resolve()
        checkpoint = torch.load(str(checkpoint_path), map_location="cpu", weights_only=False)
        state = checkpoint.get("model_state_dict", checkpoint)
        missing, unexpected = model.load_state_dict(state, strict=False)
        if missing:
            logger.warning("DINOv3 candidate loaded with missing keys: %s", missing[:8])
        if unexpected:
            logger.warning("DINOv3 candidate loaded with unexpected keys: %s", unexpected[:8])
        model = model.to(self.device).eval()
        self._config = config
        logger.info("Loaded DINOv3 candidate segmentation checkpoint: %s", checkpoint_path)
        return model

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        try:
            self._model = self._load_model()
        except Exception as exc:
            self._load_error = f"{type(exc).__name__}: {exc}"
            logger.warning("DINOv3 candidate segmentation unavailable: %s", self._load_error)

    def _preprocess(self, img_bgr: np.ndarray) -> torch.Tensor:
        input_size = int((self._config or {}).get("model", {}).get("input_size", 512))
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(img_rgb, (input_size, input_size), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255.0
        resized = (resized - IMAGENET_MEAN) / IMAGENET_STD
        tensor = torch.from_numpy(resized).permute(2, 0, 1).unsqueeze(0)
        return tensor.to(device=self.device, dtype=torch.float32)

    def _predict_probability(self, img_bgr: np.ndarray) -> np.ndarray:
        assert self._model is not None
        h, w = img_bgr.shape[:2]
        tensor = self._preprocess(img_bgr)
        with torch.no_grad():
            logits = self._model(tensor)
            if isinstance(logits, dict):
                logits = logits.get("logits") if "logits" in logits else logits.get("mask_logits")
                if logits is None:
                    raise KeyError("DINOv3 model output dict does not contain logits or mask_logits")
            prob = torch.sigmoid(logits)[0, 0].detach().cpu().numpy()
        return cv2.resize(prob, (w, h), interpolation=cv2.INTER_LINEAR).astype(np.float32)

    def _save_outputs(self, output_dir: Path, image_path: str, prob: np.ndarray, mask: np.ndarray) -> dict[str, str]:
        output_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(image_path).stem
        mask_path = output_dir / f"{stem}_dinov3_mask.png"
        prob_path = output_dir / f"{stem}_dinov3_probability.npy"
        cv2.imwrite(str(mask_path), mask)
        np.save(str(prob_path), prob)
        return {"mask_path": str(mask_path), "probability_map_path": str(prob_path)}

    def execute(self, image_path: str, output_dir: str | None = None, threshold: float = 0.5, **kwargs) -> Dict[str, Any]:
        del kwargs
        self._ensure_model()
        img = cv2.imread(image_path)
        if img is None:
            return {
                "available": False,
                "mask_available": False,
                "roi_source": "error",
                "backend_id": self.backend_id,
                "trust_label": self.trust_label,
                "error": "Could not read image",
            }
        h, w = img.shape[:2]
        if self._model is None:
            return {
                "available": False,
                "mask_available": False,
                "roi_source": "model_unavailable",
                "backend_id": self.backend_id,
                "trust_label": self.trust_label,
                "error": self._load_error or "DINOv3 checkpoint unavailable",
                "validation_summary": VALIDATION_SUMMARY,
                "image_height": h,
                "image_width": w,
            }

        prob = self._predict_probability(img)
        mask = (prob >= float(threshold)).astype(np.uint8) * 255
        self._prob_cache[image_path] = prob
        self._mask_cache[image_path] = mask
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        bbox = crop_roi_from_mask(img_rgb, mask)
        foreground = int((mask > 127).sum())
        area_ratio = round(foreground / max(h * w, 1), 6)
        result: Dict[str, Any] = {
            "available": True,
            "mask_available": bbox is not None,
            "roi_source": "dinov3_candidate" if bbox is not None else "dinov3_empty_mask",
            "roi_bbox": bbox,
            "lesion_area_ratio": area_ratio,
            "zero_dice_risk": bool(foreground == 0 or area_ratio < 0.0005),
            "probability_map_stats": {
                "min": float(prob.min()),
                "max": float(prob.max()),
                "mean": float(prob.mean()),
                "threshold": float(threshold),
            },
            "image_height": h,
            "image_width": w,
            "backend_id": self.backend_id,
            "trust_label": self.trust_label,
            "validation_summary": VALIDATION_SUMMARY,
        }
        if output_dir:
            result.update(self._save_outputs(Path(output_dir), image_path, prob, mask))
        return result

    def get_cached_mask(self, image_path: str) -> Optional[np.ndarray]:
        return self._mask_cache.get(image_path)

    def predict_mask_raw(self, image_path: str, threshold: float = 0.5) -> Optional[np.ndarray]:
        if image_path in self._mask_cache:
            return self._mask_cache[image_path]
        result = self.execute(image_path=image_path, threshold=threshold)
        if not result.get("available"):
            return None
        return self._mask_cache.get(image_path)

    def get_cached_probability(self, image_path: str) -> Optional[np.ndarray]:
        return self._prob_cache.get(image_path)
