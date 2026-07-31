"""Grad-CAM for L1 classification tool (local ROI branch, lumen-masked overlay)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import cv2
import numpy as np


def compute_gradcam_overlay(
    clf: Any,
    image_path: Path,
    mask_array: Optional[np.ndarray] = None,
    *,
    roi_path: Optional[str] = None,
    roi_bbox: Optional[Dict[str, int]] = None,
    lumen_bbox: Optional[Dict[str, int]] = None,
) -> Optional[np.ndarray]:
    """
    Grad-CAM on the local (ROI) branch — same crop as classify() local input.

    Heatmap is composited onto the full frame only inside ``lumen_bbox`` when
    provided; pixels outside the lumen box stay as the original image.
    """
    try:
        import torch
        import torch.nn as nn

        from agent.tools.classification_tool import (
            _prepare_clinical_tensor,
            _prepare_global_input,
            _prepare_local_input,
            resolve_local_roi_pil,
        )

        clf._ensure_model()
        if clf._model is None or clf._g_transform is None:
            return None
        model = clf._model
        device = clf._device
        cfg = clf._cfg or {}

        target_module = _find_last_conv(model.l_backbone)
        if target_module is None:
            return None

        activations, gradients = [], []
        fh = bh = None

        def fwd_hook(_, __, output):
            activations.append(output.detach())

        def bwd_hook(_, grad_input, grad_output):
            if grad_output[0] is not None:
                gradients.append(grad_output[0].detach())

        fh = target_module.register_forward_hook(fwd_hook)
        bh = target_module.register_full_backward_hook(bwd_hook)

        img_path = str(image_path)
        global_x = _prepare_global_input(
            img_path,
            None,
            clf._g_transform,
            bool(cfg.get("use_mask_channel", False)),
            device,
            mask_array=mask_array,
            lumen_bbox=lumen_bbox,
            cfg=cfg,
        )
        local_x = _prepare_local_input(
            roi_path,
            img_path,
            roi_bbox,
            clf._l_transform,
            device,
            mask_array=mask_array,
            lumen_bbox=lumen_bbox,
            cfg=cfg,
        )
        clinical = _prepare_clinical_tensor(
            image_path=img_path,
            mask_path=None,
            roi_bbox=roi_bbox,
            cfg=cfg,
            device=device,
            mask_array=mask_array,
        )

        model.zero_grad()
        out = model(global_x, local_x, clinical)
        logits = out.get("logits") if isinstance(out, dict) else out
        probs = torch.softmax(logits, dim=1)[0]
        top1 = int(probs.argmax().item())
        probs[top1].backward()

        if not activations or not gradients:
            return None

        act = activations[0][0]
        grad = gradients[0][0]
        weights = grad.mean(dim=(1, 2))
        cam = (weights[:, None, None] * act).sum(dim=0).cpu().numpy()
        cam = np.maximum(cam, 0)
        cam = cam / (cam.max() + 1e-8)

        _, roi_bbox_on_full, _ = resolve_local_roi_pil(
            img_path,
            roi_path=roi_path,
            roi_bbox=roi_bbox,
            mask_array=mask_array,
            lumen_bbox=lumen_bbox,
            cfg=cfg,
        )

        img_bgr = cv2.imread(img_path)
        if img_bgr is None:
            return None
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        return _composite_cam_on_full(
            img_rgb,
            cam,
            roi_bbox_on_full=roi_bbox_on_full,
            lumen_bbox=lumen_bbox,
        )
    except Exception:
        return None
    finally:
        if fh is not None:
            fh.remove()
        if bh is not None:
            bh.remove()


def _composite_cam_on_full(
    img_rgb: np.ndarray,
    cam: np.ndarray,
    *,
    roi_bbox_on_full: Optional[Dict[str, int]],
    lumen_bbox: Optional[Dict[str, int]],
) -> np.ndarray:
    """Paste ROI-branch CAM onto full image, clipped to lumen box."""
    h, w = img_rgb.shape[:2]
    heat_u8 = (cam * 255).astype(np.uint8)
    heat_color = cv2.applyColorMap(heat_u8, cv2.COLORMAP_JET)
    heat_rgb = cv2.cvtColor(heat_color, cv2.COLOR_BGR2RGB)

    if roi_bbox_on_full:
        x1, y1, x2, y2 = (
            int(roi_bbox_on_full["x1"]),
            int(roi_bbox_on_full["y1"]),
            int(roi_bbox_on_full["x2"]),
            int(roi_bbox_on_full["y2"]),
        )
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        rw, rh = max(x2 - x1, 1), max(y2 - y1, 1)
        heat_roi = cv2.resize(heat_rgb, (rw, rh))
        roi_rgb = img_rgb[y1:y2, x1:x2]
        blended_roi = (0.5 * roi_rgb + 0.5 * heat_roi).astype(np.uint8)
        out = img_rgb.copy()
        out[y1:y2, x1:x2] = blended_roi
    else:
        if lumen_bbox:
            lx1 = int(max(0, lumen_bbox["x1"]))
            ly1 = int(max(0, lumen_bbox["y1"]))
            lx2 = int(min(w, lumen_bbox["x2"]))
            ly2 = int(min(h, lumen_bbox["y2"]))
            rw, rh = max(lx2 - lx1, 1), max(ly2 - ly1, 1)
            heat_roi = cv2.resize(heat_rgb, (rw, rh))
            roi_rgb = img_rgb[ly1:ly2, lx1:lx2]
            blended_roi = (0.5 * roi_rgb + 0.5 * heat_roi).astype(np.uint8)
            out = img_rgb.copy()
            out[ly1:ly2, lx1:lx2] = blended_roi
        else:
            rh, rw = heat_rgb.shape[:2]
            heat_rgb = cv2.resize(heat_rgb, (min(rw, w), min(rh, h)))
            rh, rw = heat_rgb.shape[:2]
            blended = (0.5 * img_rgb[:rh, :rw] + 0.5 * heat_rgb).astype(np.uint8)
            out = img_rgb.copy()
            out[:rh, :rw] = blended

    if lumen_bbox:
        lx1 = int(max(0, lumen_bbox["x1"]))
        ly1 = int(max(0, lumen_bbox["y1"]))
        lx2 = int(min(w, lumen_bbox["x2"]))
        ly2 = int(min(h, lumen_bbox["y2"]))
        lumen_mask = np.zeros((h, w), dtype=bool)
        lumen_mask[ly1:ly2, lx1:lx2] = True
        out = np.where(lumen_mask[..., None], out, img_rgb)

    return out


def _find_last_conv(model):
    import torch.nn as nn

    last = None
    for m in model.modules():
        if isinstance(m, nn.Conv2d):
            last = m
    return last
