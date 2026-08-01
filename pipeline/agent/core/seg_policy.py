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
      - unet: always UNet ConvNeXt-B fulldata (production mask)
      - dino: explicit DINOv3 candidate override for exploratory runs
      - auto: keep UNet as production mask; retain DINO as evidence candidate;
        use DINO only when the production mask is unavailable
    """
    dino_obs = dino_obs or {"available": False}
    su = _mask_score(unet_obs, unet_mask)
    sd = _mask_score(dino_obs, dino_mask)
    if policy == "unet":
        chosen, key = unet_mask, "unet_convnext_fulldata"
    elif policy == "dino":
        if dino_mask is not None and np.asarray(dino_mask).any():
            chosen, key = dino_mask, "dinov3_vitb16_explicit"
        else:
            chosen, key = unet_mask, "unet_convnext_fallback_from_dino"
    else:
        # Auto is production-safe: DINO is compared and reported, but cannot
        # silently replace the primary mask with an exploratory candidate.
        if unet_mask is not None and np.asarray(unet_mask).any():
            chosen, key = unet_mask, "unet_convnext_auto"
        elif dino_mask is not None and np.asarray(dino_mask).any():
            chosen, key = dino_mask, "dinov3_vitb16_fallback"
        else:
            chosen, key = None, "none"

    merged = {
        "unet": unet_obs,
        "dinov3": dino_obs,
        "selection": {
            "policy": policy,
            "chosen_backend": key,
            "unet_score": round(su, 4),
            "dinov3_score": round(sd, 4),
            "rationale": (
                f"auto keeps production UNet when available; DINO remains evidence candidate "
                f"(unet_score={su:.3f}, dino_score={sd:.3f})"
                if policy == "auto"
                else f"forced {policy}"
            ),
        },
        "mask_available": chosen is not None and bool(np.asarray(chosen).any()),
        "mask_role": (
            "production" if key.startswith("unet")
            else "explicit_candidate_override" if key == "dinov3_vitb16_explicit"
            else "candidate_fallback" if key.startswith("dinov3")
            else "unavailable"
        ),
        "dino_usage": "evidence_only" if policy == "auto" else "explicit_policy",
        "candidate_mask_available": bool(dino_mask is not None and np.asarray(dino_mask).any()),
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
