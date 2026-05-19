"""
SegmentationTool — wraps UNet segmentation models.

Supports both the older ConvNeXt-Tiny (strict) and the newer
ConvNeXt-Base (fulldata, Dice 0.87) checkpoint.  The encoder name
is read from the checkpoint metadata so the correct architecture
is instantiated automatically.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np
import torch

from .base import BaseTool, ToolParameter
from ..core.repo_paths import PROJECT_ROOT, first_existing_path

logger = logging.getLogger(__name__)

DEFAULT_SEG_MODEL = first_existing_path(
    PROJECT_ROOT / "pipeline" / "experiments" / "tree" / "segmentation_auxiliary" / "segmentation" / "segmentation_misc" / "segmentation_fulldata" / "checkpoints" / "best_model.pth",
    PROJECT_ROOT / "pipeline" / "experiments" / "segmentation_fulldata" / "best_model.pth",
    PROJECT_ROOT / "experiments" / "segmentation" / "efficientsam3_stagec_pilot_eval_r002" / "best_model.pth",
) or (PROJECT_ROOT / "pipeline" / "experiments" / "tree" / "segmentation_auxiliary" / "segmentation" / "segmentation_misc" / "segmentation_fulldata" / "checkpoints" / "best_model.pth")
_FALLBACK_SEG_MODEL = first_existing_path(
    PROJECT_ROOT / "pipeline" / "experiments" / "tree" / "segmentation_auxiliary" / "segmentation" / "segmentation_misc" / "segmentation_strict" / "analysis" / "legacy_root_files" / "best_segmentation_model.pth",
    PROJECT_ROOT / "pipeline" / "experiments" / "segmentation_strict" / "best_segmentation_model.pth",
    PROJECT_ROOT / "experiments" / "segmentation" / "segmentation_unetplusplus_pytorch_holdout_cropui_dataset_v20260409_holdout_cropui_20260415_r001" / "best_model.pth",
) or (PROJECT_ROOT / "pipeline" / "experiments" / "tree" / "segmentation_auxiliary" / "segmentation" / "segmentation_misc" / "segmentation_strict" / "analysis" / "legacy_root_files" / "best_segmentation_model.pth")
IMG_SIZE = 384
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

_ENCODER_FALLBACK = "tu-convnext_tiny"


def _load_seg_model(model_path: Path, device: torch.device):
    """Load smp UNet segmentation model; auto-detect encoder from checkpoint."""
    import segmentation_models_pytorch as smp

    if not model_path.exists() and _FALLBACK_SEG_MODEL.exists():
        logger.warning("Primary seg checkpoint not found: %s; falling back to %s",
                       model_path, _FALLBACK_SEG_MODEL)
        model_path = _FALLBACK_SEG_MODEL

    ckpt = torch.load(str(model_path), map_location="cpu", weights_only=False)
    encoder_name = ckpt.get("encoder", _ENCODER_FALLBACK)

    model = smp.Unet(
        encoder_name=encoder_name,
        encoder_weights=None,
        in_channels=3, classes=1, activation=None,
    )
    model.load_state_dict(ckpt["model_state_dict"])
    model = model.to(device).eval()
    logger.info("Segmentation model loaded: encoder=%s, val_dice=%.4f (%s)",
                encoder_name, ckpt.get("val_dice", 0), model_path.name)
    return model, encoder_name


def _predict_mask(model, img_bgr: np.ndarray,
                  device: torch.device) -> np.ndarray:
    """Run segmentation inference, return binary mask at original resolution."""
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w = img_rgb.shape[:2]

    resized = cv2.resize(img_rgb, (IMG_SIZE, IMG_SIZE)).astype(np.float32) / 255.0
    t = torch.from_numpy(resized).permute(2, 0, 1)
    mean = torch.tensor(IMAGENET_MEAN).view(3, 1, 1)
    std = torch.tensor(IMAGENET_STD).view(3, 1, 1)
    t = ((t - mean) / std).unsqueeze(0).to(device)

    with torch.no_grad():
        logits = model(t)
        mask = (torch.sigmoid(logits) > 0.5).float()

    mask_np = mask[0, 0].cpu().numpy()
    mask_orig = cv2.resize(mask_np, (w, h), interpolation=cv2.INTER_NEAREST)
    return (mask_orig * 255).astype(np.uint8)


def crop_roi_from_mask(img_np: np.ndarray, mask_np: np.ndarray,
                       padding_ratio: float = 0.1,
                       min_size: int = 32) -> Optional[Dict[str, Any]]:
    """
    Extract ROI bounding box from binary mask.
    Returns bbox dict or None if no valid contour found.
    """
    mask_bin = (mask_np > 127).astype(np.uint8)
    contours, _ = cv2.findContours(mask_bin, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    all_pts = np.vstack(contours)
    x, y, w, h = cv2.boundingRect(all_pts)
    img_h, img_w = img_np.shape[:2]
    pad_x = int(w * padding_ratio)
    pad_y = int(h * padding_ratio)
    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(img_w, x + w + pad_x)
    y2 = min(img_h, y + h + pad_y)
    if (x2 - x1) < min_size or (y2 - y1) < min_size:
        return None

    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}


class SegmentationTool(BaseTool):
    name = "segment"
    description = (
        "Run lesion segmentation on an ultrasound frame. Returns mask "
        "availability, ROI bounding box, and lesion area ratio. Falls "
        "back to center-crop if no lesion is detected."
    )
    parameters = [
        ToolParameter("image_path", "str",
                       "Absolute path to the ultrasound image"),
    ]

    def __init__(self, model_path: Path = DEFAULT_SEG_MODEL,
                 device: Optional[torch.device] = None):
        self._model_path = model_path
        self._device = device or torch.device(
            "cuda:0" if torch.cuda.is_available() else "cpu")
        self._model = None
        self._load_error: Optional[str] = None
        self._mask_cache: Dict[str, np.ndarray] = {}
        self._loaded_encoder: Optional[str] = None

    def _ensure_model(self):
        if self._model is None:
            try:
                self._model, self._loaded_encoder = _load_seg_model(self._model_path, self._device)
            except Exception as exc:
                self._load_error = str(exc)
                logger.warning("Segmentation model unavailable: %s", exc)

    def _runtime_invocation(self, *, forward_pass: bool) -> Dict[str, Any]:
        return {
            "api_kind": "local_torch_inference",
            "forward_pass": forward_pass,
            "checkpoint": str(self._model_path),
            "encoder": self._loaded_encoder,
            "device": str(self._device),
        }

    def execute(self, image_path: str, **kwargs) -> Dict[str, Any]:
        self._ensure_model()

        img = cv2.imread(image_path)
        if img is None:
            return {"mask_available": False, "roi_source": "error",
                    "error": "Could not read image"}

        if self._model is None:
            h, w = img.shape[:2]
            crop_ratio = 0.6
            cx, cy = w // 2, h // 2
            cw, ch = int(w * crop_ratio) // 2, int(h * crop_ratio) // 2
            return {
                "mask_available": False,
                "available": False,
                "roi_source": "model_unavailable",
                "error": self._load_error or "Segmentation model checkpoint unavailable",
                "roi_bbox": {"x1": cx - cw, "y1": cy - ch, "x2": cx + cw, "y2": cy + ch},
                "lesion_area_ratio": 0.0,
                "image_height": h,
                "image_width": w,
                "runtime_invocation": self._runtime_invocation(forward_pass=False),
            }

        mask_np = _predict_mask(self._model, img, self._device)
        self._mask_cache[image_path] = mask_np
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w = img_rgb.shape[:2]

        bbox = crop_roi_from_mask(img_rgb, mask_np)
        lesion_pixels = int(np.sum(mask_np > 127))
        total_pixels = h * w
        area_ratio = round(lesion_pixels / total_pixels, 4) if total_pixels > 0 else 0.0

        if bbox is not None:
            return {
                "available": True,
                "mask_available": True,
                "roi_source": "predicted",
                "roi_bbox": bbox,
                "lesion_area_ratio": area_ratio,
                "image_height": h,
                "image_width": w,
                "runtime_invocation": self._runtime_invocation(forward_pass=True),
            }

        # Fallback: center crop (60%)
        crop_ratio = 0.6
        cx, cy = w // 2, h // 2
        cw, ch = int(w * crop_ratio) // 2, int(h * crop_ratio) // 2
        return {
            "available": True,
            "mask_available": False,
            "roi_source": "center_crop",
            "roi_bbox": {"x1": cx - cw, "y1": cy - ch,
                         "x2": cx + cw, "y2": cy + ch},
            "lesion_area_ratio": area_ratio,
            "image_height": h,
            "image_width": w,
            "runtime_invocation": self._runtime_invocation(forward_pass=True),
        }

    def predict_mask_raw(self, image_path: str) -> Optional[np.ndarray]:
        """Direct access for other tools that need the raw mask array."""
        if image_path in self._mask_cache:
            return self._mask_cache[image_path]
        self._ensure_model()
        img = cv2.imread(image_path)
        if img is None:
            return None
        mask = _predict_mask(self._model, img, self._device)
        self._mask_cache[image_path] = mask
        return mask

    def get_cached_mask(self, image_path: str) -> Optional[np.ndarray]:
        """Return cached mask if available, None otherwise."""
        return self._mask_cache.get(image_path)
