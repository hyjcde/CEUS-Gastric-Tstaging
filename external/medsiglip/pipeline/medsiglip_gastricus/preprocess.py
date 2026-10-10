"""方案 2: 图像预处理。Full 不去裁；ROI 按 mask 现算框再外扩、pad。

2.1  Full-frame: freeze crop_ui RGB，几何不动，交给官方 SiglipImageProcessor -> 448x448。
2.2  ROI: mask 轴对齐框，宽高各外扩 expand（默认 0.20，方案写 15%-25%），
     短边 pad 成正方形，再走同一套 processor。不用现成 crop_roi。

当前 20% 主缓存的框是全部非零像素（bbox=all），与已落盘 e_full / e_roi 一致。
bbox=largest 只走新缓存，禁止覆盖主缓存。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .constants import IMAGE_SIZE, ROI_EXPAND, ROOT

PROCESSOR_MEAN = (0.5, 0.5, 0.5)
PROCESSOR_STD = (0.5, 0.5, 0.5)
BBOX_MODES = ("all", "largest")
PAD_MODES = ("black", "reflect", "edge", "mean")


def repo_path(value: object) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else ROOT / path


def full_frame(image: str | Path | Image.Image) -> Image.Image:
    """方案 2.1: 完整关键帧转 RGB。不裁、不 pad、不手写 resize。"""
    if isinstance(image, Image.Image):
        return image.convert("RGB")
    return Image.open(repo_path(image)).convert("RGB")


def load_mask(path: Path, size: tuple[int, int]) -> np.ndarray:
    """Mask 最近邻缩到与 crop_ui 同尺寸，再二值化。"""
    mask = np.array(Image.open(path).convert("L").resize(size, Image.NEAREST))
    return mask > 0


def _label_bool(mask: np.ndarray) -> tuple[np.ndarray, int]:
    try:
        from scipy import ndimage

        labeled, count = ndimage.label(mask)
        return labeled.astype(np.int32), int(count)
    except Exception:
        return mask.astype(np.int32), int(bool(mask.any()))


def lesion_bbox(mask: np.ndarray, mode: str = "all") -> tuple[int, int, int, int] | None:
    """方案 2.2: 从病灶 mask 取轴对齐框。all=全部非零；largest=最大连通域。"""
    if mode not in BBOX_MODES:
        raise ValueError(mode)
    if not mask.any():
        return None
    if mode == "largest":
        labeled, count = _label_bool(mask)
        if count <= 0:
            return None
        counts = np.bincount(labeled.ravel())
        if counts.size <= 1:
            return None
        counts[0] = 0
        ys, xs = np.where(labeled == int(counts.argmax()))
    else:
        ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def square_pad(crop: Image.Image, pad: str = "black") -> Image.Image:
    """方案 2.2: 短边 pad 成正方形，再交给官方 processor 做 448 resize。"""
    mode = str(pad).lower()
    if mode not in PAD_MODES:
        raise ValueError(f"unknown pad {pad}")
    cw, ch = crop.size
    side = max(cw, ch)
    if cw == side and ch == side:
        return crop
    pad_w = side - cw
    pad_h = side - ch
    left = pad_w // 2
    right = pad_w - left
    top = pad_h // 2
    bottom = pad_h - top
    if mode == "black":
        canvas = Image.new("RGB", (side, side), (0, 0, 0))
        canvas.paste(crop, (left, top))
        return canvas
    arr = np.asarray(crop)
    if mode == "mean":
        color = tuple(int(round(x)) for x in arr.reshape(-1, 3).mean(axis=0))
        canvas = Image.new("RGB", (side, side), color)
        canvas.paste(crop, (left, top))
        return canvas
    padded = np.pad(arr, ((top, bottom), (left, right), (0, 0)), mode=mode)
    return Image.fromarray(padded)


def expand_roi(
    image: Image.Image,
    mask: np.ndarray,
    expand: float = ROI_EXPAND,
    pad: str = "black",
    bbox_mode: str = "all",
) -> Image.Image:
    """方案 2.2: mask 框宽高各外扩 expand，clip 到边界，短边 pad。空 mask 退回中心正方形。"""
    width, height = image.size
    box = lesion_bbox(mask, mode=bbox_mode)
    if box is None:
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        return image.crop((left, top, left + side, top + side))
    x0, y0, x1, y1 = box
    bw = max(x1 - x0 + 1, 1)
    bh = max(y1 - y0 + 1, 1)
    pad_x = int(round(bw * float(expand)))
    pad_y = int(round(bh * float(expand)))
    x0 = max(0, x0 - pad_x)
    y0 = max(0, y0 - pad_y)
    x1 = min(width - 1, x1 + pad_x)
    y1 = min(height - 1, y1 + pad_y)
    return square_pad(image.crop((x0, y0, x1 + 1, y1 + 1)), pad=pad)


def overlay_mask_polygon(
    image: Image.Image,
    mask: np.ndarray,
    fill_alpha: float = 0.22,
    contour: bool = True,
) -> Image.Image:
    """Paint lesion fill and a 2px ring so LoRA sees the polygon, not only a box."""
    rgb = image.convert("RGB")
    arr = np.asarray(rgb).astype(np.float32)
    binary = np.squeeze(mask)
    if binary.ndim > 2:
        binary = binary[..., 0]
    if binary.shape[:2] != arr.shape[:2]:
        binary = np.array(
            Image.fromarray((binary > 0).astype(np.uint8) * 255).resize((arr.shape[1], arr.shape[0]), Image.NEAREST)
        )
    binary = binary > 0
    if not binary.any():
        return rgb
    highlight = np.array([255.0, 40.0, 40.0], dtype=np.float32)
    out = arr.copy()
    out[binary] = out[binary] * (1.0 - float(fill_alpha)) + highlight * float(fill_alpha)
    if contour:
        try:
            from scipy import ndimage

            ring = binary & ~ndimage.binary_erosion(binary, iterations=2)
        except Exception:
            ring = binary
        out[ring] = highlight
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def expanded_box(
    mask: np.ndarray,
    size: tuple[int, int],
    expand: float = ROI_EXPAND,
    bbox_mode: str = "all",
) -> tuple[int, int, int, int]:
    width, height = size
    box = lesion_bbox(mask, mode=bbox_mode)
    if box is None:
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        return left, top, left + side - 1, top + side - 1
    x0, y0, x1, y1 = box
    pad_x = int(round(max(x1 - x0 + 1, 1) * float(expand)))
    pad_y = int(round(max(y1 - y0 + 1, 1) * float(expand)))
    return (
        max(0, x0 - pad_x),
        max(0, y0 - pad_y),
        min(width - 1, x1 + pad_x),
        min(height - 1, y1 + pad_y),
    )


def official_roi_from_crop_ui(crop_ui: Path) -> Path | None:
    """Map crop_ui/images/X.jpg to the already-made crop_roi/images/X.jpg."""
    crop_ui = Path(crop_ui)
    cursor = crop_ui
    while cursor.name != "crop_ui" and cursor != cursor.parent:
        cursor = cursor.parent
    if cursor.name != "crop_ui":
        return None
    cand = cursor.parent / "crop_roi" / crop_ui.relative_to(cursor)
    return cand if cand.is_file() else None


def _roi_mask_for(official_roi: Path) -> Path | None:
    stem = official_roi.stem
    parent = official_roi.parent
    for folder in ("roi_masks", "masks"):
        for suffix in (".png", ".jpg"):
            cand = parent.parent / folder / f"{stem}{suffix}"
            if cand.is_file():
                return cand
    return None


def load_lora_views(
    crop_ui: Path,
    mask_path: Path | None,
    expand: float = ROI_EXPAND,
    pad: str = "black",
    official_roi: Path | None = None,
) -> tuple[Image.Image, Image.Image]:
    """Full = crop_ui + polygon. ROI prefers official crop_roi, then mask-box."""
    full = full_frame(crop_ui)
    if mask_path is not None and Path(mask_path).is_file():
        mask = load_mask(Path(mask_path), full.size)
        full_view = overlay_mask_polygon(full, mask, fill_alpha=0.16, contour=True)
    else:
        full_view = full
        mask = None

    if official_roi is not None and Path(official_roi).is_file():
        roi_rgb = full_frame(official_roi)
        roi_mask_path = _roi_mask_for(Path(official_roi))
        if roi_mask_path is not None:
            roi_mask = load_mask(roi_mask_path, roi_rgb.size)
            roi_rgb = overlay_mask_polygon(roi_rgb, roi_mask, fill_alpha=0.30, contour=True)
        return full_view, square_pad(roi_rgb, pad=pad)

    if mask is not None:
        x0, y0, x1, y1 = expanded_box(mask, full.size, expand=expand)
        roi_rgb = full.crop((x0, y0, x1 + 1, y1 + 1))
        roi_mask = mask[y0 : y1 + 1, x0 : x1 + 1]
        return full_view, square_pad(overlay_mask_polygon(roi_rgb, roi_mask, fill_alpha=0.30, contour=True), pad=pad)
    return full_view, square_pad(full, pad=pad)


def load_pair(
    crop_ui: Path,
    mask_path: Path,
    expand: float = ROI_EXPAND,
    pad: str = "black",
    bbox_mode: str = "all",
) -> tuple[Image.Image, Image.Image, float]:
    """方案 2: 返回 (full 关键帧, ROI crop, mask 面积占比)。"""
    full = full_frame(crop_ui)
    mask = load_mask(mask_path, full.size)
    roi = expand_roi(full, mask, expand=expand, pad=pad, bbox_mode=bbox_mode)
    area = float(mask.mean()) if mask.size else 0.0
    return full, roi, area


def _processor_size(image_processor) -> tuple[int, int]:
    size = getattr(image_processor, "size", None)
    if isinstance(size, dict):
        return int(size.get("height", 0)), int(size.get("width", 0))
    height = int(getattr(size, "height", 0) or 0)
    width = int(getattr(size, "width", 0) or 0)
    return height, width


def assert_processor(processor) -> dict[str, object]:
    """方案 2.1: 官方 processor 必须是 448、mean/std=0.5、只 resize 不 center-crop。"""
    image = getattr(processor, "image_processor", processor)
    height, width = _processor_size(image)
    if height != IMAGE_SIZE or width != IMAGE_SIZE:
        raise RuntimeError(f"processor size {height}x{width}, expected {IMAGE_SIZE}x{IMAGE_SIZE}")
    mean = tuple(float(x) for x in image.image_mean)
    std = tuple(float(x) for x in image.image_std)
    if mean != PROCESSOR_MEAN or std != PROCESSOR_STD:
        raise RuntimeError(f"processor mean/std {mean}/{std}, expected {PROCESSOR_MEAN}/{PROCESSOR_STD}")
    if not bool(getattr(image, "do_resize", True)):
        raise RuntimeError("processor do_resize must be true")
    if bool(getattr(image, "do_center_crop", False)):
        raise RuntimeError("processor must not center-crop; square-pad ROI would be clipped")
    return {
        "image_processor_type": type(image).__name__,
        "size": [height, width],
        "resample": int(getattr(image, "resample", 3)),
        "rescale_factor": float(getattr(image, "rescale_factor", 1.0 / 255.0)),
        "image_mean": list(mean),
        "image_std": list(std),
        "do_resize": True,
        "do_center_crop": False,
    }
