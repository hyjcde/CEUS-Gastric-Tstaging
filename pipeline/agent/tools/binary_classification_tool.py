"""
BinaryClassificationTool — wraps the single-branch benign-vs-malignant ConvNeXt.

Current local candidate (2026-08-02, L0 stage-1):
  pipeline/experiments/tree/gastric_binary/classification/single_convnext/
    binary_clean_audit_v1_20260802_103058/best_model.pth

Validation reference:
  pipeline/experiments/tree/gastric_binary/.../analysis/.../*.md
  (held-out screened external 2966 patient: AUC 0.755, Sens 54.8% / Spec 83.6%)

This tool is the **gating input** for the two-stage clinical workflow:
  1. If P(benign) is high-confidence and segmentation morphology agrees,
     the agent may finish with a benign recommendation and skip T-staging.
  2. Otherwise the T-staging tool chain (classify, wall_evidence, ...) runs.

Output schema (consumed by AgentDecisionPolicy and downstream trace JSON):
  {
    "top1_label": "benign" | "malignant",
    "top1_prob": float,
    "top2_label": str,
    "top2_prob": float,
    "probabilities": {"benign": float, "malignant": float},
    "uncertainty": float,                  # Shannon entropy normalised to [0,1]
    "gate_decision": "skip_t" | "run_t",   # rule-based gate, NOT the model's call
    "gate_threshold_skip_t": float,        # the rule threshold (e.g. 0.95)
    "backend_id": str,
    "available": bool
  }
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
from PIL import Image

from .base import BaseTool, ToolParameter
from ..core.repo_paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

PIPELINE_DIR = PROJECT_ROOT / "pipeline"

_BINARY_RUN_CANDIDATES = [
    PIPELINE_DIR
    / "experiments"
    / "tree"
    / "gastric_binary"
    / "classification"
    / "single_convnext"
    / "binary_clean_audit_v1_20260802_103058",
    PIPELINE_DIR
    / "experiments"
    / "tree"
    / "gastric_binary"
    / "classification"
    / "single_image_only"
    / "binary_current_gastritis_screened_eval_image_only_20260531_121138",
]
BINARY_RUN_DIR = next(
    (candidate for candidate in _BINARY_RUN_CANDIDATES if (candidate / "best_model.pth").exists()),
    _BINARY_RUN_CANDIDATES[0],
)
BINARY_CKPT = BINARY_RUN_DIR / "best_model.pth"
BINARY_CONFIG = BINARY_RUN_DIR / "config.json"
BINARY_BACKEND_ID = f"{BINARY_RUN_DIR.parent.name}/{BINARY_RUN_DIR.name}"

CLASS_NAMES = ["benign", "malignant"]

# Default gate rule: high-confidence benign → skip T. This is intentionally
# conservative — the binary model's held-out Sens is only 54.8%, so we ONLY
# skip T when benign confidence is overwhelming (>= 0.95) and the agent
# downstream sees no conflicting morphology (the policy layer handles that).
DEFAULT_GATE_SKIP_T_THRESHOLD = 0.95


def _load_binary(device: torch.device):
    """Reconstruct the binary ConvNeXt-small classifier and load EMA weights."""
    sys.path.insert(0, str(PIPELINE_DIR))
    from lib.models import SingleBranchClassifier
    from lib.transforms import get_val_transforms

    cfg = json.loads(BINARY_CONFIG.read_text())
    backbone = cfg["backbone"]
    image_size = int(cfg["image_size"])
    num_classes = int(cfg.get("num_classes", 2))
    head_hidden = int(cfg.get("head_hidden", 512))
    dropout = float(cfg.get("dropout", 0.4))

    model = SingleBranchClassifier(
        backbone_name=backbone,
        pretrained=False,
        image_size=image_size,
        dropout=dropout,
        num_classes=num_classes,
        head_hidden=head_hidden,
    )
    ckpt = torch.load(str(BINARY_CKPT), map_location="cpu", weights_only=False)
    if "ema_state_dict" in ckpt:
        model.load_state_dict(ckpt["ema_state_dict"], strict=False)
    elif "model_state_dict" in ckpt:
        model.load_state_dict(ckpt["model_state_dict"], strict=False)
    else:
        model.load_state_dict(ckpt, strict=False)
    model = model.to(device).eval()

    transform = get_val_transforms(image_size, hist_eq=True, normalize_stats="imagenet")
    return model, transform, cfg


def _shannon_entropy_norm(probs: np.ndarray) -> float:
    """Normalised Shannon entropy in [0, 1]. 0=peaked, 1=uniform."""
    n = len(probs)
    if n <= 1:
        return 0.0
    eps = 1e-12
    p = np.clip(probs, eps, 1.0)
    H = -float((p * np.log(p)).sum())
    H_max = float(np.log(n))
    return H / H_max if H_max > 0 else 0.0


class BinaryClassificationTool(BaseTool):
    """
    Benign-vs-malignant image-only classifier.

    Inputs:
      - image_path: single cropped frame, ideally 224x224 (will be resized)
      - frame_index (optional): index in the CaseCard, for trace labelling

    Output: see module docstring.
    """

    name = "binary_classify"
    description = (
        "Run the L0 single-branch ConvNeXt screening model on one frame and return "
        "benign-vs-malignant probabilities with a conservative routing decision. "
        "This is pre-staging screening evidence, not a final diagnosis; doctor review remains required."
    )
    parameters = [
        ToolParameter(
            "image_path",
            "str",
            "Path to the ultrasound frame (cropped ROI preferred).",
        ),
        ToolParameter(
            "frame_index",
            "int",
            "Index of this frame in the CaseCard (0..N-1).",
            required=False,
            default=0,
        ),
        ToolParameter(
            "gate_skip_t_threshold",
            "float",
            "If P(benign) > this AND top1=='benign', gate_decision='skip_t'.",
            required=False,
            default=DEFAULT_GATE_SKIP_T_THRESHOLD,
        ),
    ]

    def __init__(self, device: Optional[str] = None, lazy: bool = True):
        self._device_str = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._device = torch.device(self._device_str)
        self._model = None
        self._transform = None
        self._cfg: Dict[str, Any] = {}
        self._lazy = lazy

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        if not BINARY_CKPT.exists():
            raise FileNotFoundError(
                f"Binary checkpoint not found: {BINARY_CKPT}. "
                "Set BinaryClassificationTool.BINARY_RUN_DIR to a compatible local run."
            )
        self._model, self._transform, self._cfg = _load_binary(self._device)
        logger.info("BinaryClassificationTool loaded on %s", self._device_str)

    def execute(
        self,
        image_path: str,
        frame_index: int = 0,
        gate_skip_t_threshold: float = DEFAULT_GATE_SKIP_T_THRESHOLD,
        **kwargs,  # absorb auto-injected roi_path, mask_path etc. from react_loop
    ) -> Dict[str, Any]:
        if not Path(str(image_path)).exists():
            return self._unavailable(
                image_path, reason=f"image not found: {image_path}"
            )

        try:
            self._ensure_loaded()
        except Exception as exc:  # noqa: BLE001
            logger.exception("BinaryClassificationTool load failed")
            return self._unavailable(image_path, reason=str(exc))

        try:
            rgb_pil = Image.open(str(image_path)).convert("RGB")
        except Exception as exc:  # noqa: BLE001
            return {
                "available": False,
                "error": f"PIL open failed: {exc}",
                "backend_id": BINARY_BACKEND_ID,
            }

        x = self._transform(rgb_pil)  # torchvision Compose, returns Tensor
        x = x.unsqueeze(0).to(self._device)

        with torch.no_grad():
            logits = self._model(x)
        probs = torch.softmax(logits, dim=-1).squeeze(0).cpu().numpy()
        order = np.argsort(probs)[::-1]
        top1_idx, top2_idx = int(order[0]), int(order[1])
        top1_label = CLASS_NAMES[top1_idx]
        top2_label = CLASS_NAMES[top2_idx]
        top1_prob = float(probs[top1_idx])
        top2_prob = float(probs[top2_idx])
        uncertainty = _shannon_entropy_norm(probs)

        # Gate: only skip T when benign wins by a wide margin.
        gate_skip = (
            top1_label == "benign" and top1_prob >= gate_skip_t_threshold
        )

        return {
            "available": True,
            "backend_id": BINARY_BACKEND_ID,
            "model_task": "binary_gastritis",
            "model_family": "single_branch",
            "image_path": str(image_path),
            "frame_index": int(frame_index),
            "top1_label": top1_label,
            "top1_prob": round(top1_prob, 4),
            "top2_label": top2_label,
            "top2_prob": round(top2_prob, 4),
            "probabilities": {
                CLASS_NAMES[0]: round(float(probs[0]), 4),
                CLASS_NAMES[1]: round(float(probs[1]), 4),
            },
            "uncertainty": round(uncertainty, 4),
            "gate_decision": "skip_t" if gate_skip else "run_t",
            "gate_skip_t_threshold": float(gate_skip_t_threshold),
            "gate_threshold_status": "engineering_conservative_not_clinically_calibrated",
            "clinical_role": "pre_staging_screening",
            "routing_only": True,
            "requires_doctor_review": True,
            "trust_label": "caution",
            "device": self._device_str,
        }

    @staticmethod
    def _unavailable(image_path: str, reason: str) -> Dict[str, Any]:
        return {
            "available": False,
            "backend_id": BINARY_BACKEND_ID,
            "image_path": str(image_path),
            "error": reason,
            "top1_label": None,
            "top1_prob": None,
            "gate_decision": "run_t",  # conservative: still run T-staging
            "gate_threshold_status": "engineering_conservative_not_clinically_calibrated",
            "clinical_role": "pre_staging_screening",
            "routing_only": True,
            "requires_doctor_review": True,
            "trust_label": "caution",
        }
