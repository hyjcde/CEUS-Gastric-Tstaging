"""
ClassificationTool — wraps the mask4ch Dual-v2 T-staging classifier.

Loads the best checkpoint (EMA weights preferred), runs inference on
a single frame (global 4-ch image + ROI), and returns the 4-class
probability distribution with uncertainty metrics.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import torch
from PIL import Image

from .base import BaseTool, ToolParameter
from ..core.repo_paths import PROJECT_ROOT, first_existing_path

logger = logging.getLogger(__name__)

PIPELINE_DIR = PROJECT_ROOT / "pipeline"

# Frozen mainline (scoreboard Promote): mask4ch + clinical22 full data, 20260423.
_FROZEN_MASK4CH_RUN = (
    PIPELINE_DIR / "experiments" / "tree" / "gastric_tstage_4class"
    / "classification" / "dual_mask4ch"
    / "tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301"
)

DEFAULT_EXP_DIR = first_existing_path(
    _FROZEN_MASK4CH_RUN,
    PIPELINE_DIR / "experiments" / "tstaging_4class_dual_v2_mask4ch_20260302_201944",
    PROJECT_ROOT / "pipeline" / "experiments" / "tree" / "gastric_tstage_4class"
    / "classification" / "dual_convnext"
    / "tstaging_4class_dual_v2_multitask_lumen_lesion_features_20260416_161710",
) or _FROZEN_MASK4CH_RUN

CLASS_NAMES = ["T1", "T2", "T3", "T4+"]
CLINICAL_FEATURE_NAMES = [
    "seg_area_ratio",
    "seg_bbox_area_ratio",
    "seg_long_axis_ratio",
    "seg_short_axis_ratio",
    "seg_irregularity",
    "seg_boundary_clarity",
    "seg_lumen_inside_ratio",
    "seg_lumen_box_area_ratio",
    "seg_has_lumen",
]


def _load_classifier(exp_dir: Path, device: torch.device):
    """Reconstruct model from config.json and load best_model.pth."""
    import sys
    sys.path.insert(0, str(PIPELINE_DIR))
    from lib.models import DualBranchClassifier
    from lib.transforms import get_val_transforms

    config_path = exp_dir / "config.json"
    with open(config_path) as f:
        cfg = json.load(f)

    num_classes = cfg.get("num_classes", 4)
    model_nc = num_classes - 1 if cfg.get("loss") == "coral" else num_classes

    model = DualBranchClassifier(
        global_backbone=cfg.get("global_backbone",
                                "convnext_base.fb_in22k_ft_in1k_384"),
        local_backbone=cfg.get("local_backbone",
                               "convnext_small.in12k_ft_in1k"),
        num_classes=model_nc,
        pretrained=False,
        fusion_type=cfg.get("fusion_type", "concat"),
        fusion_hidden=cfg.get("fusion_hidden", 256),
        dropout=cfg.get("dropout", 0.3),
        head_hidden=cfg.get("head_hidden", 512),
        global_in_channels=cfg.get("global_in_channels", 3),
        clinical_dim=cfg.get("clinical_dim", 0),
        multitask=cfg.get("multitask", False),
    )

    ckpt_path = exp_dir / "best_model.pth"
    ckpt = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    if "ema_state_dict" in ckpt:
        model.load_state_dict(ckpt["ema_state_dict"], strict=False)
    elif "model_state_dict" in ckpt:
        model.load_state_dict(ckpt["model_state_dict"], strict=False)
    else:
        model.load_state_dict(ckpt, strict=False)

    model = model.to(device).eval()

    # Build val transforms
    g_size = cfg.get("global_size", 384)
    l_size = cfg.get("image_size", 224)
    hist_eq = cfg.get("hist_eq", False)
    norm_stats = cfg.get("normalize_stats", "imagenet")
    g_transform = get_val_transforms(g_size, hist_eq=hist_eq,
                                      normalize_stats=norm_stats)
    l_transform = get_val_transforms(l_size, hist_eq=hist_eq,
                                      normalize_stats=norm_stats)

    return model, cfg, g_transform, l_transform


def _prepare_global_input(image_path: str, mask_path: Optional[str],
                          transform, use_mask_channel: bool,
                          device: torch.device) -> torch.Tensor:
    """Prepare 3-ch or 4-ch global input tensor."""
    img = Image.open(image_path).convert("RGB")
    img_t = transform(img)  # (3, H, W)

    if use_mask_channel and mask_path:
        mask = Image.open(mask_path).convert("L")
        # Resize mask to match the transformed image size
        h, w = img_t.shape[1], img_t.shape[2]
        mask_resized = mask.resize((w, h), Image.NEAREST)
        mask_t = torch.from_numpy(
            np.array(mask_resized, dtype=np.float32) / 255.0
        ).unsqueeze(0)  # (1, H, W)
        img_t = torch.cat([img_t, mask_t], dim=0)  # (4, H, W)
    elif use_mask_channel:
        # No mask available: use zeros
        h, w = img_t.shape[1], img_t.shape[2]
        img_t = torch.cat([img_t, torch.zeros(1, h, w)], dim=0)

    return img_t.unsqueeze(0).to(device)


def _prepare_local_input(roi_path: Optional[str], image_path: str,
                         roi_bbox: Optional[Dict],
                         transform, device: torch.device) -> torch.Tensor:
    """Prepare ROI local input. Falls back to center crop."""
    if roi_path and Path(roi_path).exists():
        roi_img = Image.open(roi_path).convert("RGB")
    elif roi_bbox:
        img = Image.open(image_path).convert("RGB")
        roi_img = img.crop((roi_bbox["x1"], roi_bbox["y1"],
                            roi_bbox["x2"], roi_bbox["y2"]))
    else:
        # Center crop fallback
        img = Image.open(image_path).convert("RGB")
        w, h = img.size
        cw, ch = int(w * 0.6), int(h * 0.6)
        left = (w - cw) // 2
        top = (h - ch) // 2
        roi_img = img.crop((left, top, left + cw, top + ch))

    roi_t = transform(roi_img)
    return roi_t.unsqueeze(0).to(device)


def _bbox_from_mask(mask_bin: np.ndarray) -> Optional[Dict[str, int]]:
    ys, xs = np.where(mask_bin > 0)
    if ys.size == 0 or xs.size == 0:
        return None
    return {
        "x1": int(xs.min()),
        "y1": int(ys.min()),
        "x2": int(xs.max()) + 1,
        "y2": int(ys.max()) + 1,
    }


def _clamp_ratio(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def _estimate_boundary_clarity(mask_bin: np.ndarray) -> float:
    contours, _ = cv2.findContours(mask_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return 0.0
    contour = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(contour))
    perimeter = float(cv2.arcLength(contour, True))
    if area <= 0 or perimeter <= 0:
        return 0.0
    circularity = (4.0 * np.pi * area) / (perimeter * perimeter)
    return _clamp_ratio(circularity)


def _infer_structured_features(
    image_path: str,
    mask_path: Optional[str],
    roi_bbox: Optional[Dict[str, Any]],
    mask_array: Optional[np.ndarray] = None,
    clinical_features: Optional[Dict[str, Any]] = None,
) -> List[float]:
    if clinical_features:
        return [
            float(clinical_features.get(name, 0.0) or 0.0)
            for name in CLINICAL_FEATURE_NAMES
        ]

    image = cv2.imread(image_path)
    if image is None:
        return [0.0] * len(CLINICAL_FEATURE_NAMES)

    img_h, img_w = image.shape[:2]
    image_area = float(max(img_h * img_w, 1))
    resolved_bbox = dict(roi_bbox) if roi_bbox else None
    mask_bin: Optional[np.ndarray] = None

    if mask_array is not None:
        mask = mask_array.astype(np.uint8)
        if mask.shape[:2] != (img_h, img_w):
            mask = cv2.resize(mask, (img_w, img_h), interpolation=cv2.INTER_NEAREST)
        mask_bin = (mask > 127).astype(np.uint8)
        if resolved_bbox is None:
            resolved_bbox = _bbox_from_mask(mask_bin)
    elif mask_path and Path(mask_path).exists():
        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if mask is not None:
            if mask.shape[:2] != (img_h, img_w):
                mask = cv2.resize(mask, (img_w, img_h), interpolation=cv2.INTER_NEAREST)
            mask_bin = (mask > 127).astype(np.uint8)
            if resolved_bbox is None:
                resolved_bbox = _bbox_from_mask(mask_bin)

    lesion_area_ratio = 0.0
    irregularity = 0.0
    boundary_clarity = 0.0
    if mask_bin is not None:
        lesion_pixels = float(mask_bin.sum())
        lesion_area_ratio = _clamp_ratio(lesion_pixels / image_area)
        contours, _ = cv2.findContours(mask_bin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            contour = max(contours, key=cv2.contourArea)
            area = float(cv2.contourArea(contour))
            perimeter = float(cv2.arcLength(contour, True))
            if area > 0 and perimeter > 0:
                circularity = min((4.0 * np.pi * area) / (perimeter * perimeter), 1.0)
                irregularity = float(max(0.0, 1.0 - circularity))
                boundary_clarity = _estimate_boundary_clarity(mask_bin)

    bbox_area_ratio = 0.0
    long_axis_ratio = 0.0
    short_axis_ratio = 0.0
    if resolved_bbox:
        x1 = int(resolved_bbox.get("x1", 0))
        y1 = int(resolved_bbox.get("y1", 0))
        x2 = int(resolved_bbox.get("x2", x1))
        y2 = int(resolved_bbox.get("y2", y1))
        bw = max(x2 - x1, 0)
        bh = max(y2 - y1, 0)
        bbox_area_ratio = _clamp_ratio((bw * bh) / image_area)
        long_axis_ratio = _clamp_ratio(max(bw, bh) / max(img_h, img_w, 1))
        short_axis_ratio = _clamp_ratio(min(bw, bh) / max(min(img_h, img_w), 1))

    return [
        round(lesion_area_ratio, 6),
        round(bbox_area_ratio, 6),
        round(long_axis_ratio, 6),
        round(short_axis_ratio, 6),
        round(irregularity, 6),
        round(boundary_clarity, 6),
        0.0,
        0.0,
        0.0,
    ]


def _prepare_clinical_tensor(
    image_path: str,
    mask_path: Optional[str],
    roi_bbox: Optional[Dict[str, Any]],
    cfg: Dict[str, Any],
    device: torch.device,
    mask_array: Optional[np.ndarray] = None,
    clinical_features: Optional[Dict[str, Any]] = None,
) -> Optional[torch.Tensor]:
    clinical_dim = int(cfg.get("clinical_dim", 0) or 0)
    if clinical_dim <= 0:
        return None

    inferred = _infer_structured_features(
        image_path=image_path,
        mask_path=mask_path,
        roi_bbox=roi_bbox,
        mask_array=mask_array,
        clinical_features=clinical_features,
    )
    values = inferred[:clinical_dim]
    if len(values) < clinical_dim:
        values.extend([0.0] * (clinical_dim - len(values)))
    return torch.tensor([values], dtype=torch.float32, device=device)


class ClassificationTool(BaseTool):
    name = "classify"
    description = (
        "Run the dual-branch T-staging classifier on one frame. Returns "
        "4-class probabilities (T1/T2/T3/T4+), top-1 and top-2 stages, "
        "and an uncertainty score."
    )
    parameters = [
        ToolParameter("image_path", "str",
                       "Absolute path to the ultrasound image"),
        ToolParameter("mask_path", "str",
                       "Path to predicted mask (4th channel)", required=False),
        ToolParameter("mask_array", "ndarray",
                      "In-memory binary mask array for structured feature extraction",
                      required=False),
        ToolParameter("roi_path", "str",
                       "Path to ROI crop image", required=False),
        ToolParameter("roi_bbox", "dict",
                       "ROI bounding box {x1,y1,x2,y2} from segmentation",
                       required=False),
        ToolParameter("clinical_features", "dict",
                      "Optional structured lesion/lumen features aligned with training columns",
                      required=False),
    ]

    def __init__(self, exp_dir: Path = DEFAULT_EXP_DIR,
                 device: Optional[torch.device] = None):
        self._exp_dir = exp_dir
        self._device = device or torch.device(
            "cuda:0" if torch.cuda.is_available() else "cpu")
        self._model = None
        self._load_error: Optional[str] = None
        self._cfg = None
        self._g_transform = None
        self._l_transform = None

    def _ensure_model(self):
        if self._model is None:
            try:
                self._model, self._cfg, self._g_transform, self._l_transform = (
                    _load_classifier(self._exp_dir, self._device)
                )
            except Exception as exc:
                self._load_error = str(exc)
                logger.warning("Classification model unavailable: %s", exc)

    def execute(self, image_path: str,
                mask_path: Optional[str] = None,
                mask_array: Optional[np.ndarray] = None,
                roi_path: Optional[str] = None,
                roi_bbox: Optional[Dict] = None,
                clinical_features: Optional[Dict[str, Any]] = None,
                **kwargs) -> Dict[str, Any]:
        try:
            self._ensure_model()

            if self._model is None or self._cfg is None or self._g_transform is None or self._l_transform is None:
                raise RuntimeError(self._load_error or "Classification model checkpoint unavailable")

            use_mask = self._cfg.get("use_mask_channel", False)
            global_input = _prepare_global_input(
                image_path, mask_path, self._g_transform, use_mask, self._device)
            local_input = _prepare_local_input(
                roi_path, image_path, roi_bbox, self._l_transform, self._device)
            clinical_input = _prepare_clinical_tensor(
                image_path=image_path,
                mask_path=mask_path,
                roi_bbox=roi_bbox,
                cfg=self._cfg,
                device=self._device,
                mask_array=mask_array,
                clinical_features=clinical_features,
            )

            with torch.no_grad():
                output = self._model(global_input, local_input, clinical_input)

            # Handle multitask output (dict) vs simple logits
            if isinstance(output, dict):
                logits = output.get("logits", output.get("main", None))
                if logits is None:
                    logits = list(output.values())[0]
            else:
                logits = output

            probs = torch.softmax(logits, dim=1)[0].cpu().numpy()

            sorted_idx = np.argsort(probs)[::-1]
            top1_idx = int(sorted_idx[0])
            top2_idx = int(sorted_idx[1])

            uncertainty = 1.0 - float(probs[top1_idx] - probs[top2_idx])

            return {
                "available": True,
                "runtime_invocation": {
                    "api_kind": "local_torch_inference",
                    "forward_pass": True,
                    "checkpoint": str(self._exp_dir / "best_model.pth"),
                    "experiment_dir": str(self._exp_dir),
                    "global_backbone": self._cfg.get("global_backbone"),
                    "device": str(self._device),
                },
                "structured_features": {
                    name: round(float(value), 4)
                    for name, value in zip(
                        CLINICAL_FEATURE_NAMES,
                        (clinical_input[0].detach().cpu().tolist() if clinical_input is not None else [])
                        + [0.0] * len(CLINICAL_FEATURE_NAMES),
                    )
                },
                "probabilities": {
                    CLASS_NAMES[i]: round(float(probs[i]), 4)
                    for i in range(len(CLASS_NAMES))
                },
                "top1_stage": CLASS_NAMES[top1_idx],
                "top1_prob": round(float(probs[top1_idx]), 4),
                "top2_stage": CLASS_NAMES[top2_idx],
                "top2_prob": round(float(probs[top2_idx]), 4),
                "uncertainty": round(uncertainty, 4),
            }
        except Exception as exc:
            logger.warning("Classification inference unavailable: %s", exc)
            return {
                "available": False,
                "runtime_invocation": {
                    "api_kind": "local_torch_inference",
                    "forward_pass": False,
                    "checkpoint": str(self._exp_dir / "best_model.pth"),
                    "experiment_dir": str(self._exp_dir),
                    "device": str(self._device),
                    "error": str(exc),
                },
                "error": str(exc),
                "probabilities": {stage: 0.0 for stage in CLASS_NAMES},
                "top1_stage": "Unavailable",
                "top1_prob": 0.0,
                "top2_stage": "Unavailable",
                "top2_prob": 0.0,
                "uncertainty": 1.0,
            }
