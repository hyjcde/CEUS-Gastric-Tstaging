"""Lesion mask selection: UNet (production) vs DINOv3 (FM candidate)."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np


def _mask_score(obs: Dict[str, Any], mask: Optional[np.ndarray]) -> float:
    if mask is None or not np.asarray(mask).any():
        if not obs.get("mask_available"):
            return -1.0
    area = float(obs.get("lesion_area_ratio") or 0.0)
    if area <= 0.0 or area > 0.25:
        return 0.15
    if obs.get("zero_dice_risk"):
        return 0.25
    area_score = 1.0 if 0.0008 <= area <= 0.12 else 0.55
    prob_stats = obs.get("probability_map_stats") or {}
    mean_prob = float(prob_stats.get("mean", 0.55))
    return area_score + min(mean_prob, 1.0) * 0.35


def choose_lesion_mask(
    *,
    unet_obs: Dict[str, Any],
    dino_obs: Optional[Dict[str, Any]],
    unet_mask: Optional[np.ndarray],
    dino_mask: Optional[np.ndarray],
    policy: str = "auto",
) -> Tuple[Optional[np.ndarray], str, Dict[str, Any]]:
    """
    Returns (chosen_mask, backend_key, merged_observation).

    policy:
      - unet: always UNet ConvNeXt-B fulldata (registry primary)
      - dino: always DINOv3 ViT candidate (FM features)
      - auto: score both; DINO gets +0.05 prior (prospective Dice 0.714 vs UNet baseline)
    """
    dino_obs = dino_obs or {"available": False}
    su = _mask_score(unet_obs, unet_mask)
    sd = _mask_score(dino_obs, dino_mask)
    if dino_obs.get("available"):
        sd += 0.05  # registry: prospective_eval_dice 0.7144, ext +0.038 vs UNet++

    if policy == "unet":
        chosen, key = unet_mask, "unet_convnext_fulldata"
    elif policy == "dino":
        chosen, key = dino_mask if dino_obs.get("available") else unet_mask, "dinov3_vitb16_candidate"
    else:
        if sd > su and dino_mask is not None and np.asarray(dino_mask).any():
            chosen, key = dino_mask, "dinov3_vitb16_auto"
        else:
            chosen, key = unet_mask, "unet_convnext_auto"

    merged = {
        "unet": unet_obs,
        "dinov3": dino_obs,
        "selection": {
            "policy": policy,
            "chosen_backend": key,
            "unet_score": round(su, 4),
            "dinov3_score": round(sd, 4),
            "rationale": (
                f"auto picked {key} (unet_score={su:.3f}, dino_score={sd:.3f})"
                if policy == "auto"
                else f"forced {policy}"
            ),
        },
        "mask_available": chosen is not None and bool(np.asarray(chosen).any()),
        "lesion_area_ratio": (
            unet_obs.get("lesion_area_ratio")
            if key.startswith("unet")
            else dino_obs.get("lesion_area_ratio", unet_obs.get("lesion_area_ratio"))
        ),
        "roi_bbox": dino_obs.get("roi_bbox") if key.startswith("dinov3") else unet_obs.get("roi_bbox"),
        "roi_source": key,
        "available": True,
    }
    if key.startswith("unet"):
        merged.update({k: unet_obs.get(k) for k in ("image_height", "image_width", "runtime_invocation") if k in unet_obs})
    else:
        merged.update({k: dino_obs.get(k) for k in ("image_height", "image_width", "backend_id", "trust_label") if k in dino_obs})

    return chosen, key, merged
