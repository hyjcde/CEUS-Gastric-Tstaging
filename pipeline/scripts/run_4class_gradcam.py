"""
4类 T-staging GradCAM 分析脚本

支持:
  - DualBranchClassifier (Global + ROI 双分支)
  - SingleBranchClassifier (单分支)
  - 按类别 + 预测正确/错误 分组输出
  - 特别关注 T2 错分样本
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import json
import re
import shutil
from typing import Optional

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as mpl_fm
import numpy as np
from PIL import ImageDraw, ImageFont
import pandas as pd
import torch
from PIL import Image
from torchvision import transforms

from lib.models import DualBranchClassifier, SingleBranchClassifier
from lib.transforms import get_val_transforms
from lib.experiment_tree import derive_gradcam_output_dir
from lib.datasets import resolve_global_image_path

CLASS_NAMES = ["T1", "T2", "T3", "T4+"]
PIPELINE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PIPELINE_ROOT.parent
BASE_DIRS = [PROJECT_ROOT, Path("/data/research/gastric/Tstaging")]
PREDICTED_ROI_DIRS = [
    PROJECT_ROOT / "pipeline/data/tstaging_4class_predicted_roi_v2/predicted_roi",
    PROJECT_ROOT / "pipeline/data/tstaging_4class_predicted_roi_full/predicted_roi",
    PROJECT_ROOT / "pipeline/data/tstaging_4class_forced_pipeline_20260322/predicted_roi",
]
REGION_TABLE_DIRS = [
    PIPELINE_ROOT / "data" / "tstaging_4class_region_contrastive_full" / "regions",
    PIPELINE_ROOT / "data" / "tstaging_4class_anatomic_region_contrastive" / "regions",
]
BOX_COLS = [
    "crop_box_x1",
    "crop_box_y1",
    "crop_box_x2",
    "crop_box_y2",
    "lumen_box_x1",
    "lumen_box_y1",
    "lumen_box_x2",
    "lumen_box_y2",
    "lumen_box_count",
    "lesion_pred_mask_path",
    "mask_path",
    "predicted_mask_path",
]
FORCED_MASK_CSVS = [
    PIPELINE_ROOT / "data" / "tstaging_4class_forced_pipeline_20260322" / "test_external_forced_output_roi.csv",
    PIPELINE_ROOT / "data" / "tstaging_4class_forced_pipeline_20260322" / "test_prospective_forced_output_roi.csv",
    PIPELINE_ROOT / "data" / "tstaging_4class_forced_pipeline_20260322" / "train_forced_output_roi.csv",
    PIPELINE_ROOT / "data" / "tstaging_4class_forced_pipeline_20260322" / "val_forced_output_roi.csv",
]
_FORCED_MASK_INDEX: dict[tuple[str, int], str] | None = None

TIMES_NEW_ROMAN_CANDIDATES = [
    Path.home() / ".fonts" / "Times.TTF",
    Path("/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"),
]
TIMES_NEW_ROMAN_BOLD_CANDIDATES = [
    Path.home() / ".fonts" / "Timesbd.TTF",
    Path("/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman_Bold.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"),
]
_TNR_FONT_CACHE: dict[tuple[bool, int], ImageFont.FreeTypeFont] = {}


def configure_times_new_roman() -> str:
    """Matplotlib + PIL use Times New Roman (or closest serif)."""
    tnr_path = next((p for p in TIMES_NEW_ROMAN_CANDIDATES if p.is_file()), None)
    if tnr_path is not None:
        mpl_fm.fontManager.addfont(str(tnr_path))
        family = mpl_fm.FontProperties(fname=str(tnr_path)).get_name()
    else:
        family = "Times New Roman"
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": [family, "Times New Roman", "Times", "DejaVu Serif"],
            "axes.titlesize": 10,
            "axes.labelsize": 10,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "figure.titlesize": 12,
        }
    )
    return family


def _tnr_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (bold, size)
    if key not in _TNR_FONT_CACHE:
        paths = TIMES_NEW_ROMAN_BOLD_CANDIDATES if bold else TIMES_NEW_ROMAN_CANDIDATES
        for path in paths:
            if path.is_file():
                _TNR_FONT_CACHE[key] = ImageFont.truetype(str(path), size=size)
                break
        else:
            _TNR_FONT_CACHE[key] = ImageFont.load_default()
    return _TNR_FONT_CACHE[key]


def draw_text_tnr(
    rgb: np.ndarray,
    text: str,
    xy: tuple[int, int],
    size: int = 22,
    color: tuple[int, int, int] = (255, 255, 255),
    stroke_width: int = 0,
    stroke_fill: tuple[int, int, int] = (0, 0, 0),
    bold: bool = True,
) -> np.ndarray:
    pil = Image.fromarray(rgb)
    draw = ImageDraw.Draw(pil)
    draw.text(
        xy,
        text,
        font=_tnr_font(size, bold=bold),
        fill=color,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
    )
    return np.array(pil)


configure_times_new_roman()


# ------------------------------------------------------------------
# GradCAM implementation for dual-branch models
# ------------------------------------------------------------------
def forward_main_logits(model, input_tensors):
    """Match Trainer._forward_model / eval: multitask dict -> main logits."""
    if len(input_tensors) == 3:
        out = model(input_tensors[0], input_tensors[1], input_tensors[2])
    else:
        out = model(*input_tensors)
    if isinstance(out, dict):
        out = out["main"]
    return out


def logits_to_class_probs(logits, loss_type: str):
    """Match pipeline/lib/trainer.py _evaluate (coral vs softmax)."""
    if loss_type == "coral":
        cum_probs = torch.sigmoid(logits.float())
        cum_probs = torch.cat(
            [
                torch.ones(logits.size(0), 1, device=logits.device, dtype=logits.dtype),
                cum_probs,
                torch.zeros(logits.size(0), 1, device=logits.device, dtype=logits.dtype),
            ],
            dim=1,
        )
        probs = cum_probs[:, :-1] - cum_probs[:, 1:]
        probs = torch.clamp(probs, min=0)
        probs = probs / probs.sum(dim=1, keepdim=True)
        return probs
    return torch.softmax(logits.float(), dim=1)


class GradCAM:
    """GradCAM that hooks into a specific layer of a model."""

    def __init__(self, model, target_layer):
        self.model = model
        self.gradients = None
        self.activations = None
        self._handles = [
            target_layer.register_forward_hook(self._save_activation),
            target_layer.register_full_backward_hook(self._save_gradient),
        ]

    def _save_activation(self, module, inp, out):
        self.activations = out.detach()

    def _save_gradient(self, module, grad_in, grad_out):
        self.gradients = grad_out[0].detach()

    def _cam_from_grad_act(self):
        grads = self.gradients.cpu().numpy()[0]
        acts = self.activations.cpu().numpy()[0]
        weights = grads.mean(axis=(1, 2))
        cam = (weights[:, None, None] * acts).sum(axis=0)
        cam = np.maximum(cam, 0)
        if cam.max() > 0:
            cam = cam / cam.max()
        return cam

    def generate(self, input_tensors, target_class=None, cfg=None):
        """
        Args:
            input_tensors: tuple of tensors for model forward
            target_class: int or None (GradCAM target; None -> pred_class)
            cfg: experiment config (loss + num_classes → coral vs softmax, same as Trainer)
        Returns:
            cam: numpy (H, W) normalized 0-1
            probs: numpy (num_classes,)
            pred_class: int
        """
        cfg = cfg or {}
        self.model.eval()
        self.model.zero_grad()

        logits = forward_main_logits(self.model, input_tensors)
        nc = int(cfg.get("num_classes", logits.size(1)))
        use_coral = cfg.get("loss") in ("coral", "ordinal") and coral_probs_match_logits(logits, nc)
        loss_mode = "coral" if use_coral else "ce"

        probs_t = logits_to_class_probs(logits, loss_mode)
        probs = probs_t[0].detach().cpu().numpy()
        pred_class = int(probs_t.argmax(dim=1).item())

        if target_class is None:
            target_class = pred_class

        if loss_mode == "coral":
            score = probs_t[0, target_class]
        else:
            score = logits[0, target_class]
        score.backward(retain_graph=False)

        cam = self._cam_from_grad_act()
        return cam, probs, pred_class

    def remove_hooks(self):
        for h in self._handles:
            h.remove()


BEST_LUMEN_YOLO = PROJECT_ROOT / (
    "experiments/detection/detection_yolo11l_lumen_locator_cropui_combined_plus_zip2_20260417_r001"
    "/ultralytics/weights/best.pt"
)
BEST_LESION_YOLO = PROJECT_ROOT / (
    "experiments/detection/detection_yolo11l_lesion_holdout_cropui_imgsz960_"
    "dataset_v20260409_holdout_cropui_20260409_r001/ultralytics/weights/best.pt"
)


def get_target_layer(model, cfg, branch: str = "global"):
    """Target layer for Grad-CAM: global branch (full frame) or local branch (ROI)."""
    model_type = cfg.get("model_type", "single_branch")

    if model_type == "dual_branch":
        backbone = model.l_backbone if branch == "local" else model.g_backbone
    else:
        backbone = model.backbone

    # ConvNeXt: stages[-1].blocks[-1]
    if hasattr(backbone, "stages"):
        return backbone.stages[-1].blocks[-1]
    # UniFormer: blocks4[-1]
    if hasattr(backbone, "blocks4"):
        return backbone.blocks4[-1]
    # Generic timm: last named child before head
    children = list(backbone.children())
    return children[-2] if len(children) > 1 else children[-1]


def load_model(exp_dir: Path, device):
    """Load model and config from experiment directory."""
    config_path = exp_dir / "config.json"
    weights_path = exp_dir / "best_model.pth"

    with open(config_path) as f:
        cfg = json.load(f)

    model_type = cfg.get("model_type", "single_branch")

    if model_type == "dual_branch":
        model = DualBranchClassifier(
            global_backbone=cfg.get("global_backbone", "convnext_base.fb_in22k_ft_in1k_384"),
            local_backbone=cfg.get("local_backbone", "convnext_small.in12k_ft_in1k"),
            pretrained=False,
            global_size=cfg.get("global_size", 384),
            local_size=cfg.get("local_size", 224),
            num_classes=cfg.get("num_classes", 4),
            fusion_type=cfg.get("fusion_type", "cross_attention"),
            fusion_hidden=cfg.get("fusion_hidden", 256),
            dropout=cfg.get("dropout", 0.3),
            clinical_dim=cfg.get("clinical_dim", 0),
            clinical_hidden=cfg.get("clinical_hidden", 64),
            head_hidden=cfg.get("head_hidden", None),
            global_in_channels=cfg.get("global_in_channels", 3),
        )
    else:
        backbone_name = cfg.get("backbone",
                                cfg.get("global_backbone", "convnext_base.fb_in22k_ft_in1k_384"))
        model = SingleBranchClassifier(
            backbone_name=backbone_name,
            pretrained=False,
            image_size=cfg.get("image_size", 224),
            num_classes=cfg.get("num_classes", 4),
            dropout=cfg.get("dropout", 0.3),
            head_hidden=cfg.get("head_hidden", None),
        )

    ckpt = torch.load(weights_path, map_location="cpu", weights_only=False)
    if "ema_state_dict" in ckpt:
        state = ckpt["ema_state_dict"]
    elif "model_state_dict" in ckpt:
        state = ckpt["model_state_dict"]
    else:
        state = ckpt
    model.load_state_dict(state, strict=False)
    model = model.to(device).eval()

    return model, cfg


def coral_probs_match_logits(logits, num_classes: int) -> bool:
    return logits.size(1) == num_classes - 1


def resolve_path(value: object) -> Path | None:
    if value is None or pd.isna(value) or not str(value).strip():
        return None
    path = Path(str(value))
    if path.is_file():
        return path
    for base in BASE_DIRS:
        candidate = base / path
        if candidate.is_file():
            return candidate
    return None


def resolve_crop_ui_path(value: object) -> Path | None:
    """Prefer crop_ui frame (training/inference standard), not original DICOM export."""
    raw = resolve_path(value)
    if raw is None:
        return None
    if "crop_ui" in str(raw).replace("\\", "/") and raw.is_file():
        return raw
    name = raw.name
    text = str(raw).replace("\\", "/")
    hospital = None
    m = re.search(r"dataset/external/([^/]+)/", text)
    if m:
        hospital = m.group(1)
    for base in BASE_DIRS:
        if hospital:
            for sub in ("crop_ui/images", "crop_ui"):
                cand = base / "dataset/external" / hospital / sub / name
                if cand.is_file():
                    return cand
        if "/original/" in text:
            for repl in (
                text.replace("/original/images/", "/crop_ui/images/"),
                text.replace("/original/", "/crop_ui/images/"),
            ):
                cand = Path(repl)
                if not cand.is_absolute():
                    for b in BASE_DIRS:
                        c2 = b / cand
                        if c2.is_file():
                            return c2
                elif cand.is_file():
                    return cand
    return raw


def resolve_predicted_roi_path(row) -> str | None:
    """Fallback global/ROI image when crop_ui is unavailable (e.g. putian_2024 pty* rows)."""
    image_path = row.get("image_path")
    if image_path is None or pd.isna(image_path):
        return None
    roi_path = row.get("roi_path")
    if roi_path is not None and not pd.isna(roi_path):
        resolved = resolve_path(roi_path)
        if resolved is not None:
            return str(resolved)
    stem = Path(str(image_path)).stem
    for root in PREDICTED_ROI_DIRS:
        for suffix in (f"{stem}_pred_roi.jpg", f"{stem}_roi.jpg"):
            candidate = root / suffix
            if candidate.is_file():
                return str(candidate)
    return None


def resolve_gradcam_image_path(row) -> str | None:
    """Best-effort crop_ui path for GradCAM (dataset resolver + legacy fallbacks)."""
    resolved = resolve_global_image_path(row)
    if resolved is not None:
        return resolved
    image_path = row.get("image_path")
    if image_path is not None and not pd.isna(image_path):
        for resolver in (resolve_crop_ui_path, resolve_path):
            candidate = resolver(image_path)
            if candidate is not None:
                return str(candidate)
    return resolve_predicted_roi_path(row)


def labelme_lesion_mask(image_path: str, shape: tuple[int, int]) -> np.ndarray:
    """GT lesion polygon from crop_ui labelme JSON."""
    path = resolve_crop_ui_path(image_path) or resolve_path(image_path)
    if path is None:
        return np.zeros(shape, dtype=np.uint8)
    candidates = [
        path.parent.parent / "annotations" / f"{path.stem}.json",
        Path(str(path).replace("/images/", "/annotations/")).with_suffix(".json"),
    ]
    ann_path = next((p for p in candidates if p.is_file()), None)
    if ann_path is None:
        return np.zeros(shape, dtype=np.uint8)
    try:
        payload = json.loads(ann_path.read_text(encoding="utf-8"))
    except Exception:
        return np.zeros(shape, dtype=np.uint8)
    mask = np.zeros(shape, dtype=np.uint8)
    for shape_obj in payload.get("shapes", []):
        label = str(shape_obj.get("label", "")).lower()
        if "lesion" not in label and "tumor" not in label and "肿瘤" not in label and "病灶" not in label:
            continue
        pts = np.array(shape_obj.get("points", []), dtype=np.float32)
        if len(pts) < 3:
            continue
        pts[:, 0] = np.clip(pts[:, 0], 0, shape[1] - 1)
        pts[:, 1] = np.clip(pts[:, 1], 0, shape[0] - 1)
        cv2.fillPoly(mask, [pts.astype(np.int32)], 1)
    return mask


def load_gt_roi_mask_png(image_path: str, shape: tuple[int, int]) -> np.ndarray:
    """GT binary mask from crop_ui/roi_masks when available."""
    path = resolve_crop_ui_path(image_path) or resolve_path(image_path)
    if path is None:
        return np.zeros(shape, dtype=np.uint8)
    for cand in (
        path.parent.parent / "roi_masks" / f"{path.name}",
        path.parent.parent / "roi_masks" / f"{path.stem}.png",
    ):
        if cand.is_file():
            arr = np.array(Image.open(cand).convert("L"))
            if arr.shape[:2] != shape:
                arr = cv2.resize(arr, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
            return (arr > 127).astype(np.uint8)
    return np.zeros(shape, dtype=np.uint8)


def load_gt_lesion_mask(image_path: str, shape: tuple[int, int]) -> np.ndarray:
    gt = load_gt_roi_mask_png(image_path, shape)
    if gt.sum() > 0:
        return gt
    return labelme_lesion_mask(image_path, shape)


def gt_pred_compare_overlay(rgb: np.ndarray, gt: np.ndarray, pred: np.ndarray) -> np.ndarray:
    out = rgb.astype(np.float32).copy()
    if gt.sum() > 0:
        m = gt > 0
        out[m] = out[m] * 0.45 + np.array([60, 220, 80], dtype=np.float32) * 0.55
    if pred.sum() > 0:
        m = pred > 0
        out[m] = out[m] * 0.45 + np.array([255, 210, 40], dtype=np.float32) * 0.55
    return np.clip(out, 0, 255).astype(np.uint8)


def bbox_dict_to_tuple(bbox: dict | None) -> tuple[int, int, int, int] | None:
    if not bbox:
        return None
    try:
        return (
            int(bbox["x1"]),
            int(bbox["y1"]),
            int(bbox["x2"]),
            int(bbox["y2"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def crop_rgb(rgb: np.ndarray, box: tuple[int, int, int, int] | None, pad: float = 0.08) -> np.ndarray:
    if box is None:
        h, w = rgb.shape[:2]
        cx, cy = w // 2, h // 2
        cw, ch = int(w * 0.6) // 2, int(h * 0.6) // 2
        box = (cx - cw, cy - ch, cx + cw, cy + ch)
    x1, y1, x2, y2 = box
    h, w = rgb.shape[:2]
    bw, bh = x2 - x1, y2 - y1
    px, py = int(bw * pad), int(bh * pad)
    x1 = max(0, x1 - px)
    y1 = max(0, y1 - py)
    x2 = min(w, x2 + px)
    y2 = min(h, y2 + py)
    if x2 <= x1 or y2 <= y1:
        return rgb.copy()
    return rgb[y1:y2, x1:x2].copy()


def expanded_roi_box(
    shape: tuple[int, int],
    lesion_box: tuple[int, int, int, int] | None = None,
    focus_mask: np.ndarray | None = None,
    extra_boxes: list[tuple[int, int, int, int]] | None = None,
    pad_ratio: float = 0.22,
) -> tuple[int, int, int, int] | None:
    """Union lesion / anatomic-focus / det boxes, then pad outward (ROI 外扩)."""
    boxes: list[tuple[int, int, int, int]] = []
    if lesion_box is not None:
        boxes.append(lesion_box)
    if focus_mask is not None:
        fb = mask_bbox((focus_mask > 0.08).astype(np.uint8))
        if fb is not None:
            boxes.append(fb)
    if extra_boxes:
        boxes.extend([b for b in extra_boxes if b is not None])
    return union_boxes(boxes, shape, pad_ratio=pad_ratio)


def expand_box_pixels(
    box: tuple[int, int, int, int],
    shape: tuple[int, int],
    pad_px: int = 40,
) -> tuple[int, int, int, int]:
    """Outward padding in pixels (Grad-CAM display region = expanded ROI + pad_px)."""
    h, w = shape
    x1, y1, x2, y2 = box
    return (
        max(0, int(x1) - int(pad_px)),
        max(0, int(y1) - int(pad_px)),
        min(w - 1, int(x2) + int(pad_px)),
        min(h - 1, int(y2) + int(pad_px)),
    )


def build_gradcam_region_mask(
    shape: tuple[int, int],
    *,
    mode: str,
    lesion_box: tuple[int, int, int, int] | None,
    lesion_seg: np.ndarray | None,
    lumen_box: tuple[int, int, int, int] | None,
    extra_boxes: list[tuple[int, int, int, int]] | None,
    roi_expand_pad: float,
    roi_cam_pad_px: int,
) -> tuple[np.ndarray, tuple[int, int, int, int] | None, tuple[int, int, int, int] | None]:
    """
    Returns (focus_mask, expanded_roi_box, gradcam_region_box).

    roi_expand_px: rectangular Grad-CAM mask = expanded ROI union box + fixed pad_px (not lesion_wall seg).
    """
    expanded = expanded_roi_box(
        shape,
        lesion_box=lesion_box,
        focus_mask=None,
        extra_boxes=extra_boxes,
        pad_ratio=roi_expand_pad,
    )
    if mode == "roi_expand_px":
        if expanded is None:
            return np.zeros(shape, dtype=np.float32), None, None
        cam_box = expand_box_pixels(expanded, shape, pad_px=roi_cam_pad_px)
        mask = box_mask(cam_box, shape).astype(np.float32)
        return mask, expanded, cam_box

    wall_mask = build_cam_focus_mask(
        shape,
        lesion_box=lesion_box,
        lesion_seg=lesion_seg,
        lumen_box=lumen_box,
        mode=mode,
    )
    return wall_mask, expanded, expanded


def paste_roi_cam_to_full(
    cam: np.ndarray,
    full_shape: tuple[int, int],
    roi_box: tuple[int, int, int, int],
    focus_mask_full: np.ndarray | None = None,
) -> np.ndarray:
    """Embed local-branch Grad-CAM (computed on expanded ROI crop) into full-image coordinates."""
    oh, ow = full_shape
    x1, y1, x2, y2 = roi_box
    rh = int(y2 - y1 + 1)
    rw = int(x2 - x1 + 1)
    if rh <= 0 or rw <= 0:
        return np.zeros((oh, ow), dtype=np.float32)
    cam_r = cv2.resize(cam.astype(np.float32), (rw, rh), interpolation=cv2.INTER_LINEAR)
    if focus_mask_full is not None and focus_mask_full.shape[:2] == (oh, ow):
        fm = focus_mask_full[y1 : y2 + 1, x1 : x2 + 1].astype(np.float32)
        if fm.shape[:2] == (rh, rw):
            cam_r = cam_r * (fm > 0.08).astype(np.float32)
    full = np.zeros((oh, ow), dtype=np.float32)
    full[y1 : y2 + 1, x1 : x2 + 1] = cam_r
    if full.max() > 0:
        full /= full.max()
    return full


def resize_for_display(rgb: np.ndarray, max_side: int = 1024) -> np.ndarray:
    h, w = rgb.shape[:2]
    if max(h, w) <= max_side:
        return rgb
    scale = max_side / float(max(h, w))
    return cv2.resize(rgb, (int(round(w * scale)), int(round(h * scale))), interpolation=cv2.INTER_AREA)


class LesionDetectionTool:
    """YOLO lesion locator (best holdout crop_ui YOLO11-L @ imgsz960)."""

    def __init__(
        self,
        weights_path: Path = BEST_LESION_YOLO,
        conf: float = 0.25,
        imgsz: int = 960,
        device: str | None = None,
    ):
        self._weights_path = Path(weights_path)
        self._conf = conf
        self._imgsz = imgsz
        self._device = device
        self._model = None
        self._load_error: Optional[str] = None

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        if not self._weights_path.is_file():
            self._load_error = f"Lesion YOLO weights missing: {self._weights_path}"
            return
        try:
            from ultralytics import YOLO

            self._model = YOLO(str(self._weights_path))
        except Exception as exc:
            self._load_error = str(exc)

    def predict_box(self, image_path: str) -> dict | None:
        self._ensure_model()
        if self._model is None:
            return None
        try:
            results = self._model.predict(
                source=image_path,
                imgsz=self._imgsz,
                conf=self._conf,
                verbose=False,
                save=False,
                device=self._device,
            )
            return select_lumen_box(results[0])
        except Exception:
            return None


def image_merge_key(value: object) -> str | None:
    p = resolve_path(value)
    if p is None:
        text = str(value).strip()
        return text if text else None
    return str(p.resolve())


def patient_frame_key(row_or_path) -> tuple[str, int] | None:
    """Match crop_ui vs original paths via patient_id + frame index (e.g. pt189-3)."""
    if isinstance(row_or_path, pd.Series):
        patient = str(row_or_path.get("patient_id", "") or "").strip().lower()
        path = row_or_path.get("image_path", "")
    else:
        patient = ""
        path = row_or_path
    name = Path(str(path)).name
    m = re.search(r"(pt\d+)[^0-9]*(\d+)", name, flags=re.IGNORECASE)
    if m:
        return m.group(1).lower(), int(m.group(2))
    if patient:
        m2 = re.search(r"(\d+)", name)
        if m2:
            return patient.lower(), int(m2.group(1))
    return None


def to_float(value: object) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        out = float(value)
        return out if np.isfinite(out) else None
    except Exception:
        return None


def row_box(row: pd.Series, prefix: str, shape: tuple[int, int]) -> tuple[int, int, int, int] | None:
    vals = [to_float(row.get(f"{prefix}_{k}")) for k in ("x1", "y1", "x2", "y2")]
    if any(v is None for v in vals):
        return None
    h, w = shape
    x1, y1, x2, y2 = vals
    if x2 <= x1 or y2 <= y1:
        return None
    return (
        int(np.clip(round(x1), 0, w - 1)),
        int(np.clip(round(y1), 0, h - 1)),
        int(np.clip(round(x2), 0, w - 1)),
        int(np.clip(round(y2), 0, h - 1)),
    )


def mask_bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    if mask is None or mask.sum() == 0:
        return None
    ys, xs = np.where(mask > 0)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def union_boxes(
    boxes: list[tuple[int, int, int, int]],
    shape: tuple[int, int],
    pad_ratio: float = 0.12,
) -> tuple[int, int, int, int] | None:
    if not boxes:
        return None
    h, w = shape
    x1 = min(b[0] for b in boxes)
    y1 = min(b[1] for b in boxes)
    x2 = max(b[2] for b in boxes)
    y2 = max(b[3] for b in boxes)
    bw = max(x2 - x1 + 1, 1)
    bh = max(y2 - y1 + 1, 1)
    pad = int(max(bw, bh) * pad_ratio)
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(w - 1, x2 + pad)
    y2 = min(h - 1, y2 + pad)
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def scale_box(
    box: tuple[int, int, int, int],
    src_shape: tuple[int, int],
    dst_shape: tuple[int, int],
) -> tuple[int, int, int, int]:
    sh, sw = src_shape
    dh, dw = dst_shape
    x1, y1, x2, y2 = box
    sx = dw / max(sw, 1)
    sy = dh / max(sh, 1)
    return (
        int(np.clip(round(x1 * sx), 0, dw - 1)),
        int(np.clip(round(y1 * sy), 0, dh - 1)),
        int(np.clip(round(x2 * sx), 0, dw - 1)),
        int(np.clip(round(y2 * sy), 0, dh - 1)),
    )


def resolve_det_focus_box(
    row: pd.Series,
    shape: tuple[int, int],
    lesion_mask: np.ndarray | None = None,
    pad_ratio: float = 0.12,
) -> tuple[tuple[int, int, int, int] | None, str]:
    """Union of lumen detection box + lesion/crop box (deploy-realism ROI)."""
    boxes: list[tuple[int, int, int, int]] = []
    tags: list[str] = []
    lumen = row_box(row, "lumen_box", shape)
    if lumen is not None:
        boxes.append(lumen)
        tags.append("lumen")
    crop = row_box(row, "crop_box", shape)
    if crop is not None:
        boxes.append(crop)
        tags.append("crop")
    if lesion_mask is not None:
        lesion_box = mask_bbox(lesion_mask)
        if lesion_box is not None:
            boxes.append(lesion_box)
            tags.append("lesion_mask")
    focus = union_boxes(boxes, shape, pad_ratio=pad_ratio)
    return focus, "+".join(tags) if tags else "none"


def _mask_center_u8(lesion: np.ndarray, fallback_box: tuple[int, int, int, int] | None) -> np.ndarray:
    m = cv2.moments(lesion.astype(np.uint8))
    if m["m00"] > 0:
        return np.array([m["m10"] / m["m00"], m["m01"] / m["m00"]], dtype=np.float32)
    if fallback_box is not None:
        x1, y1, x2, y2 = fallback_box
        return np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0], dtype=np.float32)
    h, w = lesion.shape[:2]
    return np.array([w / 2.0, h / 2.0], dtype=np.float32)


def _unit_vector(vec: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vec))
    if norm < 1e-6:
        return np.array([0.0, 1.0], dtype=np.float32)
    return (vec / norm).astype(np.float32)


def _half_plane_masks(shape: tuple[int, int], center: np.ndarray, direction: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    proj = (xx - center[0]) * direction[0] + (yy - center[1]) * direction[1]
    return (proj >= 0).astype(np.uint8), (proj < 0).astype(np.uint8)


def lesion_lumen_interstitial_mask(
    lesion: np.ndarray,
    lumen_box: tuple[int, int, int, int] | None,
    outer_px: int = 14,
    inner_px: int = 6,
) -> np.ndarray:
    """
    Pixels between lesion and lumen (outer wall band + bridge), lumen-facing side only.
    Same geometry as build_tstaging_anatomic_regions.anatomic_masks.
    """
    shape = lesion.shape[:2]
    lesion_u8 = (lesion > 0).astype(np.uint8)
    if lesion_u8.sum() == 0 or lumen_box is None:
        return np.zeros(shape, dtype=np.uint8)

    lesion_box_fb = mask_bbox(lesion_u8)
    lesion_c = _mask_center_u8(lesion_u8, lesion_box_fb)
    x1, y1, x2, y2 = lumen_box
    lumen_c = np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0], dtype=np.float32)
    outward = _unit_vector(lesion_c - lumen_c)
    outer_half, _inner_half = _half_plane_masks(shape, lesion_c, outward)

    k_outer = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (outer_px * 2 + 1, outer_px * 2 + 1))
    k_inner = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (inner_px * 2 + 1, inner_px * 2 + 1))
    dilated = cv2.dilate(lesion_u8, k_outer)
    eroded = cv2.erode(lesion_u8, k_inner)
    ring = ((dilated > 0) & (eroded == 0)).astype(np.uint8)
    outer_band = (ring & outer_half).astype(np.uint8)

    bridge = np.zeros(shape, dtype=np.uint8)
    p1 = tuple(np.round(lumen_c).astype(int))
    p2 = tuple(np.round(lesion_c).astype(int))
    thickness = max(12, int(min(shape) * 0.035))
    cv2.line(bridge, p1, p2, 1, thickness=thickness, lineType=cv2.LINE_AA)
    bridge = ((bridge > 0) & (lesion_u8 == 0)).astype(np.uint8)

    return ((outer_band > 0) | (bridge > 0)).astype(np.uint8)


def build_cam_focus_mask(
    shape: tuple[int, int],
    lesion_box: tuple[int, int, int, int] | None = None,
    lesion_seg: np.ndarray | None = None,
    lumen_box: tuple[int, int, int, int] | None = None,
    pad_ratio: float = 0.06,
    mode: str = "lesion_wall",
    wall_outer_px: int = 14,
    wall_inner_px: int = 6,
) -> np.ndarray:
    """
    Grad-CAM may only appear on:
      - lesion (病灶), and/or
      - wall / gap between lesion and lumen (病灶–胃腔间), NOT lumen fluid interior.

    mode=lesion_wall (default): lesion seg/box ∪ outer_band ∪ bridge (anatomic).
    mode=lesion: lesion only.
    mode=seg: segmentation mask only.
    mode=union: full lumen box + lesion (legacy, not recommended).
    """
    h, w = shape
    mask = np.zeros((h, w), dtype=np.float32)
    if mode == "union":
        boxes = [b for b in (lumen_box, lesion_box) if b is not None]
        if lesion_seg is not None and lesion_seg.sum() > 0:
            mask = np.maximum(mask, (lesion_seg > 0).astype(np.float32))
        for box in boxes:
            x1, y1, x2, y2 = box
            mask[y1 : y2 + 1, x1 : x2 + 1] = 1.0
        return mask

    lesion_u8 = np.zeros((h, w), dtype=np.uint8)
    if lesion_seg is not None and lesion_seg.sum() > 0:
        lesion_u8 = (lesion_seg > 0).astype(np.uint8)
    elif lesion_box is not None:
        lesion_u8 = expanded_box_mask(lesion_box, (h, w), expand_ratio=pad_ratio)

    if lesion_u8.sum() > 0:
        mask = lesion_u8.astype(np.float32)
    elif lesion_box is not None:
        mask = expanded_box_mask(lesion_box, (h, w), expand_ratio=pad_ratio).astype(np.float32)

    if mode == "seg":
        return mask

    if mode == "lesion_wall" and lesion_u8.sum() > 0:
        try:
            from lib.anatomic_focus import build_anatomic_focus_float

            mask = build_anatomic_focus_float(
                lesion_u8,
                lumen_box=lumen_box,
                outer_px=wall_outer_px,
                inner_px=wall_inner_px,
            )
        except Exception:
            if lumen_box is not None:
                interstitial = lesion_lumen_interstitial_mask(
                    lesion_u8, lumen_box, outer_px=wall_outer_px, inner_px=wall_inner_px
                )
                mask = np.maximum(mask, interstitial.astype(np.float32))

    if mode == "lesion":
        return mask

    if mask.sum() == 0 and lumen_box is not None:
        mask = expanded_box_mask(lumen_box, (h, w), expand_ratio=pad_ratio).astype(np.float32)
    return mask


def expanded_box_mask(
    box: tuple[int, int, int, int],
    shape: tuple[int, int],
    expand_ratio: float = 0.06,
) -> np.ndarray:
    h, w = shape
    x1, y1, x2, y2 = box
    pad_x = int(round((x2 - x1 + 1) * expand_ratio))
    pad_y = int(round((y2 - y1 + 1) * expand_ratio))
    x1 = int(np.clip(x1 - pad_x, 0, w - 1))
    x2 = int(np.clip(x2 + pad_x, 0, w - 1))
    y1 = int(np.clip(y1 - pad_y, 0, h - 1))
    y2 = int(np.clip(y2 + pad_y, 0, h - 1))
    out = np.zeros((h, w), dtype=np.uint8)
    out[y1 : y2 + 1, x1 : x2 + 1] = 1
    return out


def constrain_cam_to_mask(
    cam: np.ndarray,
    focus_mask: np.ndarray,
    out_shape: tuple[int, int] | None = None,
) -> np.ndarray:
    """Zero Grad-CAM outside focus_mask; renormalize inside mask only."""
    if focus_mask is None or focus_mask.sum() == 0:
        return cam
    h, w = out_shape if out_shape is not None else focus_mask.shape[:2]
    cam_r = cv2.resize(cam.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
    if focus_mask.shape[:2] != (h, w):
        m = cv2.resize(focus_mask.astype(np.float32), (w, h), interpolation=cv2.INTER_NEAREST)
    else:
        m = focus_mask.astype(np.float32)
    m = (m > 0.5).astype(np.float32)
    out = cam_r * m
    if out.max() > 0:
        out /= out.max()
    return out


def constrain_cam_to_box(
    cam: np.ndarray,
    box: tuple[int, int, int, int] | None,
    out_shape: tuple[int, int],
) -> np.ndarray:
    """Backward-compatible rectangular mask."""
    if box is None:
        return cam
    h, w = out_shape
    mask = np.zeros((h, w), dtype=np.float32)
    x1, y1, x2, y2 = box
    mask[y1 : y2 + 1, x1 : x2 + 1] = 1.0
    return constrain_cam_to_mask(cam, mask, out_shape)


def draw_det_box(img_np: np.ndarray, box: tuple[int, int, int, int] | None) -> np.ndarray:
    if box is None:
        return img_np
    out = img_np.copy()
    x1, y1, x2, y2 = box
    cv2.rectangle(out, (x1, y1), (x2, y2), (255, 180, 0), 2, lineType=cv2.LINE_AA)
    return out


def enrich_clinical_columns(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Merge clinical22 fields when input CSV lacks them (e.g. minimal PPT case lists)."""
    clinical_cols = list(cfg.get("clinical_cols") or [])
    if not clinical_cols:
        return df
    missing = [c for c in clinical_cols if c not in df.columns]
    if not missing:
        return df
    tables = []
    for region_dir in REGION_TABLE_DIRS:
        if not region_dir.is_dir():
            continue
        for path in sorted(region_dir.glob("*_clinical.csv")):
            try:
                header = pd.read_csv(path, nrows=0).columns
                keep = ["image_path", "sample_id"] + [c for c in clinical_cols if c in header]
                tables.append(pd.read_csv(path, usecols=keep, low_memory=False))
            except Exception:
                continue
    if not tables:
        return df
    region = pd.concat(tables, ignore_index=True).drop_duplicates(subset=["image_path"], keep="first")
    merge_cols = [c for c in clinical_cols if c in region.columns]
    if not merge_cols:
        return df
    out = df.merge(region[["image_path"] + merge_cols], on="image_path", how="left", suffixes=("", "_clin"))
    for col in merge_cols:
        alt = f"{col}_clin"
        if alt in out.columns:
            if col not in out.columns:
                out[col] = out[alt]
            else:
                out[col] = out[col].combine_first(out[alt])
            out = out.drop(columns=[alt])
    return out


def enrich_detection_boxes(df: pd.DataFrame, region_dirs: list[Path] | None = None) -> pd.DataFrame:
    """Attach lumen/crop box columns from region-contrastive manifests."""
    need = [c for c in BOX_COLS if c not in df.columns]
    if not need:
        return df
    dirs = region_dirs or [d for d in REGION_TABLE_DIRS if d.is_dir()]
    tables = []
    for region_dir in dirs:
        for path in sorted(region_dir.glob("*_clinical.csv")):
            try:
                header = pd.read_csv(path, nrows=0).columns
                keep = ["sample_id", "image_path"] + [c for c in BOX_COLS if c in header]
                tables.append(pd.read_csv(path, usecols=keep, low_memory=False))
            except Exception:
                continue
    if not tables:
        return df
    region = pd.concat(tables, ignore_index=True)
    region = region.drop_duplicates(subset=["sample_id"], keep="first")
    add_cols = [c for c in BOX_COLS if c in region.columns]
    if not add_cols:
        return df

    def attach_pf_key(frame: pd.DataFrame) -> pd.DataFrame:
        keys = frame.apply(patient_frame_key, axis=1)
        frame = frame.copy()
        frame["_pf_patient"] = [k[0] if k else None for k in keys]
        frame["_pf_frame"] = [k[1] if k else None for k in keys]
        return frame

    region = attach_pf_key(region)
    out = attach_pf_key(df.copy())

    if "sample_id" in out.columns and "sample_id" in region.columns:
        region_sub = region[["sample_id"] + add_cols].drop_duplicates("sample_id")
        out = out.merge(region_sub, on="sample_id", how="left", suffixes=("", "_sid"))

    pf = region[["_pf_patient", "_pf_frame"] + add_cols].dropna(subset=["_pf_patient", "_pf_frame"])
    pf = pf.drop_duplicates(subset=["_pf_patient", "_pf_frame"], keep="first")
    out = out.merge(pf, on=["_pf_patient", "_pf_frame"], how="left", suffixes=("", "_pf"))

    for col in add_cols:
        for suffix in ("_pf", "_sid"):
            alt = f"{col}{suffix}"
            if alt in out.columns:
                if col not in out.columns:
                    out[col] = out[alt]
                else:
                    out[col] = out[col].combine_first(out[alt])
                out = out.drop(columns=[alt])

    drop_cols = [c for c in ("_pf_patient", "_pf_frame") if c in out.columns]
    out = out.drop(columns=drop_cols)

    if "predicted_mask_path" not in out.columns or out["predicted_mask_path"].isna().all():
        paths = []
        for _, r in out.iterrows():
            img = resolve_path(r.get("image_path"))
            mp = resolve_predicted_mask_path(r, str(img) if img else "", None)
            paths.append(str(mp) if mp else np.nan)
        out["predicted_mask_path"] = paths
    return out


def build_forced_mask_index() -> dict[tuple[str, int], str]:
    """Map (patient_id, frame_idx) -> predicted_mask_path from forced pipeline tables."""
    global _FORCED_MASK_INDEX
    if _FORCED_MASK_INDEX is not None:
        return _FORCED_MASK_INDEX
    index: dict[tuple[str, int], str] = {}
    for csv_path in FORCED_MASK_CSVS:
        if not csv_path.is_file():
            continue
        try:
            usecols = ["patient_id", "predicted_mask_path", "mask_path", "global_image_path", "original_image_path"]
            df = pd.read_csv(csv_path, usecols=lambda c: c in usecols, low_memory=False)
        except Exception:
            df = pd.read_csv(csv_path, low_memory=False)
        for _, r in df.iterrows():
            for key in ("predicted_mask_path", "mask_path"):
                mp = resolve_path(r.get(key))
                if mp is None:
                    continue
                pf = patient_frame_key(
                    pd.Series({"patient_id": r.get("patient_id"), "image_path": r.get("global_image_path") or r.get("original_image_path")})
                )
                if pf is not None:
                    index[pf] = str(mp)
    _FORCED_MASK_INDEX = index
    return index


def resolve_predicted_mask_path(
    row: pd.Series,
    img_path: str,
    mask_dir: str | Path | None,
) -> Path | None:
    """Mask used by mask4ch ConvNeXt (forced-pipeline UNet/threshold seg, not DINO)."""
    for key in ("predicted_mask_path", "mask_path", "lesion_pred_mask_path"):
        p = resolve_path(row.get(key))
        if p is not None and p.is_file():
            return p
    pf = patient_frame_key(row if isinstance(row, pd.Series) else pd.Series({"image_path": img_path}))
    if pf is not None:
        cached = build_forced_mask_index().get(pf)
        if cached:
            p = resolve_path(cached)
            if p is not None and p.is_file():
                return p
    if mask_dir is None:
        return None
    mask_dir = Path(mask_dir)
    stem = Path(img_path).stem
    for ext in (".png", ".jpg", ".npy"):
        mp = mask_dir / f"{stem}{ext}"
        if mp.is_file():
            return mp
    if pf is not None:
        patient, frame = pf
        for pattern in (f"{patient}-{frame}_mask.png", f"{patient}_{frame}_mask.png"):
            mp = mask_dir / pattern
            if mp.is_file():
                return mp
        for mp in mask_dir.glob(f"*{patient}*{frame}*mask*.png"):
            if mp.is_file():
                return mp
    return None


def load_lesion_mask_np(
    img_path: str,
    row: pd.Series,
    mask_dir: str | Path | None,
    shape: tuple[int, int],
) -> np.ndarray | None:
    mp = resolve_predicted_mask_path(row, img_path, mask_dir)
    if mp is None:
        return None
    if mp.suffix == ".npy":
        arr = np.load(str(mp))
    else:
        arr = np.array(Image.open(mp).convert("L"))
    if arr.shape[:2] != shape:
        arr = cv2.resize(arr, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
    binary = (arr > 127).astype(np.uint8)
    return binary if binary.sum() > 0 else None


def load_lesion_mask_from_seg_tool(
    seg_tool,
    img_path: str,
    shape: tuple[int, int],
    label_prefix: str = "seg",
) -> tuple[np.ndarray | None, str]:
    """Run live segmentation (UNet or DINOv3) at crop_ui resolution."""
    if seg_tool is None:
        return None, "seg_unavailable"
    mask_u8 = seg_tool.predict_mask_raw(img_path)
    if mask_u8 is None:
        return None, "seg_failed"
    if mask_u8.shape[:2] != shape:
        mask_u8 = cv2.resize(mask_u8, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
    binary = (mask_u8 > 127).astype(np.uint8)
    if label_prefix == "dinov3":
        label = "DINOv3 ViT-B/16 seg (ext Dice 0.68)"
    else:
        enc = getattr(seg_tool, "_loaded_encoder", None) or "unet"
        label = f"UNet live ({enc})"
    return (binary if binary.sum() > 0 else None), label


def mask_tensor_from_binary(mask_bin: np.ndarray | None, global_size: int) -> torch.Tensor:
    if mask_bin is None or mask_bin.sum() == 0:
        return torch.zeros(1, global_size, global_size)
    mask_pil = Image.fromarray((mask_bin * 255).astype(np.uint8))
    mask_pil = mask_pil.resize((global_size, global_size), Image.NEAREST)
    t = torch.from_numpy(np.array(mask_pil).astype(np.float32) / 255.0)
    return t.unsqueeze(0)


def mask_binary_panel(lesion: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """High-contrast seg panel (white lesion on black) so mask is always visible."""
    h, w = shape
    if lesion is None or lesion.sum() == 0:
        panel = np.zeros((h, w, 3), dtype=np.uint8)
        return draw_text_tnr(panel, "mask missing", (12, max(12, h // 2 - 12)), size=20, color=(200, 80, 80))
    m = lesion.astype(np.uint8)
    if m.shape[:2] != (h, w):
        m = cv2.resize(m, (w, h), interpolation=cv2.INTER_NEAREST)
    panel = np.zeros((h, w, 3), dtype=np.uint8)
    panel[m > 0] = (255, 255, 255)
    return panel


def mask_channel_panel(img_np: np.ndarray, mask_disp: np.ndarray) -> np.ndarray:
    """Visualize the 4th channel fed to ConvNeXt global branch."""
    if mask_disp is None or mask_disp.sum() == 0:
        out = (img_np.astype(np.float32) * 0.25).astype(np.uint8)
        return draw_text_tnr(out, "ch4 empty", (12, 12), size=18, color=(255, 100, 100))
    m = (mask_disp > 0).astype(np.float32)
    out = img_np.astype(np.float32).copy()
    out = out * (1 - 0.55 * m[..., None]) + np.array([0, 255, 180], dtype=np.float32) * (0.55 * m[..., None])
    return np.clip(out, 0, 255).astype(np.uint8)


def make_overlay(
    img_np: np.ndarray,
    cam: np.ndarray,
    alpha: float = 0.4,
    focus_mask: np.ndarray | None = None,
) -> np.ndarray:
    """Overlay Grad-CAM; heat only where focus_mask>0 (avoids bleed outside lesion box)."""
    h, w = img_np.shape[:2]
    cam_resized = cv2.resize(cam.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
    if focus_mask is not None and focus_mask.shape[:2] == (h, w):
        m = (focus_mask > 0.5).astype(np.float32)
        cam_resized = cam_resized * m
    heatmap = cv2.applyColorMap(np.uint8(255 * np.clip(cam_resized, 0, 1)), cv2.COLORMAP_JET)
    heatmap = cv2.cvtColor(heatmap, cv2.COLOR_BGR2RGB)
    if focus_mask is not None and focus_mask.shape[:2] == (h, w):
        m3 = (focus_mask > 0.5).astype(np.float32)[..., None]
        overlay = (heatmap * alpha * m3 + img_np * (1 - alpha * m3)).clip(0, 255).astype(np.uint8)
    else:
        overlay = (heatmap * alpha + img_np * (1 - alpha)).clip(0, 255).astype(np.uint8)
    return overlay


def box_mask(box: tuple[int, int, int, int] | None, shape: tuple[int, int]) -> np.ndarray:
    out = np.zeros(shape, dtype=np.uint8)
    if box is None:
        return out
    x1, y1, x2, y2 = box
    out[y1 : y2 + 1, x1 : x2 + 1] = 1
    return out


def resize_mask_to_disp(
    mask: np.ndarray | None,
    orig_shape: tuple[int, int],
    disp_shape: tuple[int, int],
) -> np.ndarray:
    h, w = disp_shape
    if mask is None or mask.sum() == 0:
        return np.zeros((h, w), dtype=np.uint8)
    oh, ow = orig_shape
    if mask.shape[:2] != (oh, ow):
        mask = cv2.resize(mask.astype(np.uint8), (ow, oh), interpolation=cv2.INTER_NEAREST)
    return cv2.resize(mask.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)


def scale_box_to_disp(
    box: tuple[int, int, int, int] | None,
    orig_shape: tuple[int, int],
    disp_shape: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    if box is None:
        return None
    return scale_box(box, orig_shape, disp_shape)


def overlay_pred_lesion(rgb: np.ndarray, lesion: np.ndarray) -> np.ndarray:
    out = rgb.astype(np.float32).copy()
    if lesion.sum() > 0:
        m = lesion > 0
        out[m] = out[m] * 0.45 + np.array([255, 220, 0], dtype=np.float32) * 0.55
    bgr = cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
    cnts, _ = cv2.findContours((lesion * 255).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(bgr, cnts, -1, (0, 255, 255), 2, lineType=cv2.LINE_AA)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def overlay_pred_lumen(rgb: np.ndarray, lumen_box: tuple[int, int, int, int] | None) -> np.ndarray:
    out = rgb.astype(np.float32).copy()
    if lumen_box is not None:
        lumen = box_mask(lumen_box, rgb.shape[:2])
        m = lumen > 0
        out[m] = out[m] * 0.55 + np.array([30, 160, 255], dtype=np.float32) * 0.45
        x1, y1, x2, y2 = lumen_box
        bgr = cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
        cv2.rectangle(bgr, (x1, y1), (x2, y2), (255, 150, 0), 3, lineType=cv2.LINE_AA)
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return rgb.copy()


def overlay_combined(
    rgb: np.ndarray,
    lesion: np.ndarray,
    lumen_box: tuple[int, int, int, int] | None,
    cam: np.ndarray | None,
    det_box: tuple[int, int, int, int] | None = None,
    alpha_cam: float = 0.42,
) -> np.ndarray:
    out = overlay_pred_lesion(rgb, lesion)
    out = overlay_pred_lumen(out, lumen_box)
    if cam is not None:
        out = make_overlay(out, cam, alpha=alpha_cam)
    if det_box is not None:
        out = draw_det_box(out, det_box)
    return out


def _draw_box_outline(
    bgr: np.ndarray,
    box: tuple[int, int, int, int] | None,
    color: tuple[int, int, int],
    thickness: int = 2,
    dashed: bool = False,
) -> None:
    if box is None:
        return
    x1, y1, x2, y2 = box
    if not dashed:
        cv2.rectangle(bgr, (x1, y1), (x2, y2), color, thickness, lineType=cv2.LINE_AA)
        return
    for x_start, x_end in ((x1, x2), (x2, x1)):
        for y in range(y1, y2, 12):
            cv2.line(bgr, (x_start, y), (x_start, min(y + 6, y2)), color, thickness, lineType=cv2.LINE_AA)
    for y_start, y_end in ((y1, y2), (y2, y1)):
        for x in range(x1, x2, 12):
            cv2.line(bgr, (x, y_start), (min(x + 6, x2), y_start), color, thickness, lineType=cv2.LINE_AA)


def integrated_prediction_panel(
    rgb: np.ndarray,
    lesion: np.ndarray,
    lumen_box: tuple[int, int, int, int] | None,
    crop_box: tuple[int, int, int, int] | None,
    det_box: tuple[int, int, int, int] | None,
    cam: np.ndarray | None,
    probs: np.ndarray,
    true_label: int,
    pred_class: int,
    roi_thumb: np.ndarray | None = None,
    cam_focus_mask: np.ndarray | None = None,
) -> np.ndarray:
    """
    Single canvas: upstream predictions (lesion seg + lumen det) + downstream T-stage pred + CAM.
    """
    h, w = rgb.shape[:2]
    base = rgb.astype(np.float32).copy()

    # 1) Dim outside focus ROI so lesion+lumen region stands out
    focus = np.zeros((h, w), dtype=np.float32)
    if det_box is not None:
        x1, y1, x2, y2 = det_box
        focus[y1 : y2 + 1, x1 : x2 + 1] = 1.0
    elif lesion.sum() > 0 or lumen_box is not None:
        focus = np.maximum(focus, (lesion > 0).astype(np.float32))
        if lumen_box is not None:
            focus = np.maximum(focus, box_mask(lumen_box, (h, w)).astype(np.float32))
    base = base * (0.35 + 0.65 * focus[..., None])

    # 2) Predicted lumen region (detection)
    if lumen_box is not None:
        lm = box_mask(lumen_box, (h, w)) > 0
        base[lm] = base[lm] * 0.5 + np.array([40, 150, 255], dtype=np.float32) * 0.5

    # 3) Predicted lesion segmentation region
    if lesion.sum() > 0:
        lm = lesion > 0
        base[lm] = base[lm] * 0.42 + np.array([255, 220, 40], dtype=np.float32) * 0.58

    out = np.clip(base, 0, 255).astype(np.uint8)
    bgr = cv2.cvtColor(out, cv2.COLOR_RGB2BGR)

    # 4) Contours / boxes
    if lesion.sum() > 0:
        cnts, _ = cv2.findContours((lesion * 255).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(bgr, cnts, -1, (0, 255, 255), 2, lineType=cv2.LINE_AA)
    _draw_box_outline(bgr, lumen_box, (255, 160, 40), thickness=3)
    _draw_box_outline(bgr, crop_box, (255, 0, 255), thickness=2, dashed=True)
    _draw_box_outline(bgr, det_box, (0, 200, 255), thickness=2, dashed=True)

    # 5) Grad-CAM strictly inside lesion focus (not whole lumen field)
    if cam is not None:
        cam_use = cam
        if cam_focus_mask is not None and cam_focus_mask.shape[:2] == (h, w):
            cam_use = constrain_cam_to_mask(cam, cam_focus_mask, (h, w))
        cam_rgb = make_overlay(
            cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), cam_use, alpha=0.38, focus_mask=cam_focus_mask
        )
        bgr = cv2.cvtColor(cam_rgb, cv2.COLOR_RGB2BGR)

    out_rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    # 6) Prediction text banner (Times New Roman via PIL)
    true_name = CLASS_NAMES[true_label]
    pred_name = CLASS_NAMES[pred_class]
    ok = true_label == pred_class
    banner_h = 92
    overlay = out_rgb.copy()
    cv2.rectangle(overlay, (0, 0), (w, banner_h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.72, out_rgb, 0.28, 0, out_rgb)
    title = f"GT {true_name}  |  Pred {pred_name}  ({'OK' if ok else 'ERR'})  |  P={probs[pred_class]:.2f}"
    prob_line = "  ".join(f"{CLASS_NAMES[i]}:{probs[i]:.2f}" for i in range(4))
    out_rgb = draw_text_tnr(out_rgb, title, (12, 8), size=22, stroke_width=1, stroke_fill=(0, 0, 0))
    out_rgb = draw_text_tnr(out_rgb, prob_line, (12, 44), size=18, color=(200, 220, 255))

    # 7) Legend
    leg_y = h - 82
    leg_patch = out_rgb.copy()
    cv2.rectangle(leg_patch, (8, leg_y - 8), (w - 8, h - 8), (0, 0, 0), -1)
    cv2.addWeighted(leg_patch, 0.55, out_rgb, 0.45, 0, out_rgb)
    legends = [
        "Yellow: lesion seg (live)",
        "Blue: lumen det box",
        "Jet: CAM on lesion + lesion–lumen wall gap",
        "Not shown: lumen fluid interior",
    ]
    for i, txt in enumerate(legends):
        out_rgb = draw_text_tnr(out_rgb, txt, (14, leg_y + i * 18), size=15, color=(230, 230, 230))

    # 8) ROI inset (local branch sees this crop)
    if roi_thumb is not None:
        inset = cv2.resize(roi_thumb, (min(120, w // 3), min(120, h // 3)))
        ih, iw = inset.shape[:2]
        y0, x0 = h - ih - 12, w - iw - 12
        out_rgb[y0 : y0 + ih, x0 : x0 + iw] = inset
        bgr = cv2.cvtColor(out_rgb, cv2.COLOR_RGB2BGR)
        cv2.rectangle(bgr, (x0 - 2, y0 - 2), (x0 + iw + 2, y0 + ih + 2), (255, 255, 255), 2)
        out_rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        out_rgb = draw_text_tnr(out_rgb, "ROI in", (x0, max(4, y0 - 22)), size=15)

    return out_rgb


def _prob_axis(ax, probs: np.ndarray, true_label: int, pred_class: int) -> None:
    colors = ["#9ecae1"] * 4
    colors[pred_class] = "#d62728"
    colors[true_label] = "#2ca02c" if true_label == pred_class else "#98df8a"
    ax.bar(CLASS_NAMES, probs, color=colors, edgecolor="#333333", linewidth=0.6)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Probability")
    ax.grid(axis="y", alpha=0.25)
    status = "Correct" if true_label == pred_class else "Misclassified"
    ax.set_title(
        f"GT: {CLASS_NAMES[true_label]}  |  Pred: {CLASS_NAMES[pred_class]}  ({status})",
        fontsize=11,
        fontweight="bold",
    )
    for i, p in enumerate(probs):
        ax.text(i, min(p + 0.03, 1.02), f"{p:.2f}", ha="center", fontsize=9)


def _panel_axis(fig, gs, row: int, col: int, image: np.ndarray, title: str) -> None:
    ax = fig.add_subplot(gs[row, col])
    ax.imshow(image)
    ax.set_title(title, fontsize=10, pad=4)
    ax.set_aspect("equal")
    ax.axis("off")


def save_review_panel(
    save_path: Path,
    img_np: np.ndarray,
    gt_lesion_disp: np.ndarray,
    lesion_disp: np.ndarray,
    lumen_box_disp: tuple[int, int, int, int] | None,
    lesion_box_disp: tuple[int, int, int, int] | None,
    det_box_disp: tuple[int, int, int, int] | None,
    cam_global_pred: np.ndarray,
    cam_global_true: np.ndarray | None,
    cam_local_pred: np.ndarray | None,
    cam_local_true: np.ndarray | None,
    pred_roi_np: np.ndarray,
    probs: np.ndarray,
    true_label: int,
    pred_class: int,
    det_box_src: str,
    seg_source: str = "UNet live",
    cam_focus_mask: np.ndarray | None = None,
    cam_focus_roi: np.ndarray | None = None,
    cam_roi_full_pred: np.ndarray | None = None,
    cam_roi_full_true: np.ndarray | None = None,
    expanded_box_disp: tuple[int, int, int, int] | None = None,
) -> None:
    """4×3 equal panels: crop_ui + GT + live seg/YOLO + global/ROI Grad-CAM on original frame."""
    true_name = CLASS_NAMES[true_label]
    pred_name = CLASS_NAMES[pred_class]
    h, w = img_np.shape[:2]

    gt_binary = mask_binary_panel(gt_lesion_disp, (h, w))
    gt_binary = draw_text_tnr(gt_binary, "GT", (8, 8), size=18, color=(80, 220, 80)) if gt_lesion_disp.sum() > 0 else gt_binary
    pred_overlay = overlay_pred_lesion(img_np, lesion_disp)
    gt_compare = gt_pred_compare_overlay(img_np, gt_lesion_disp, lesion_disp)
    lumen_panel = overlay_pred_lumen(img_np, lumen_box_disp)
    lesion_box_panel = draw_det_box(img_np.copy(), lesion_box_disp)
    lesion_box_panel = draw_det_box(lesion_box_panel, lumen_box_disp) if lumen_box_disp else lesion_box_panel

    cam_g_pred = make_overlay(img_np, cam_global_pred, focus_mask=cam_focus_mask)
    cam_g_true = (
        make_overlay(img_np, cam_global_true, focus_mask=cam_focus_mask)
        if cam_global_true is not None
        else None
    )
    cam_l_pred = (
        make_overlay(pred_roi_np, cam_local_pred, focus_mask=cam_focus_roi)
        if cam_local_pred is not None
        else pred_roi_np
    )
    cam_l_true = (
        make_overlay(pred_roi_np, cam_local_true, focus_mask=cam_focus_roi)
        if cam_local_true is not None
        else None
    )
    cam_roi_on_orig_pred = (
        make_overlay(img_np, cam_roi_full_pred, focus_mask=cam_focus_mask)
        if cam_roi_full_pred is not None
        else cam_l_pred
    )
    cam_roi_on_orig_true = (
        make_overlay(img_np, cam_roi_full_true, focus_mask=cam_focus_mask)
        if cam_roi_full_true is not None
        else cam_l_true
    )
    expanded_panel = draw_det_box(img_np.copy(), expanded_box_disp) if expanded_box_disp else img_np.copy()
    if expanded_box_disp is not None:
        expanded_panel = draw_text_tnr(
            expanded_panel, "expanded ROI", (8, h - 28), size=16, color=(255, 200, 80)
        )

    integrated = integrated_prediction_panel(
        img_np,
        lesion_disp,
        lumen_box_disp,
        lesion_box_disp,
        det_box_disp,
        cam_global_pred,
        probs,
        true_label,
        pred_class,
        roi_thumb=cv2.resize(pred_roi_np, (min(120, w // 3), min(120, h // 3))),
        cam_focus_mask=cam_focus_mask,
    )

    fig = plt.figure(figsize=(18, 20), dpi=150, facecolor="white")
    gs = fig.add_gridspec(4, 3, wspace=0.05, hspace=0.10)

    tiles = [
        (0, 0, img_np, "crop_ui frame"),
        (0, 1, gt_binary, "GT lesion (labelme / roi_masks)"),
        (0, 2, pred_overlay, f"Pred lesion seg ({seg_source})"),
        (1, 0, gt_compare, "GT (green) vs Pred (yellow)"),
        (1, 1, lumen_panel, "Pred lumen YOLO11-L"),
        (1, 2, lesion_box_panel, "Pred lesion YOLO11-L box"),
        (2, 0, expanded_panel, "Expanded ROI (local Grad-CAM region)"),
        (2, 1, cam_g_pred, f"Grad-CAM global @ Pred {pred_name}"),
        (2, 2, cam_roi_on_orig_pred, f"ROI Grad-CAM→original @ Pred {pred_name}"),
        (3, 0, integrated, "Integrated predictions + global CAM"),
        (3, 1,
         cam_roi_on_orig_true if cam_roi_on_orig_true is not None else (
             cam_g_true if cam_g_true is not None else cam_roi_on_orig_pred
         ),
         f"ROI Grad-CAM→original @ True {true_name}"
         if cam_roi_on_orig_true is not None
         else (f"Grad-CAM @ True {true_name}" if cam_g_true is not None else f"ROI CAM @ Pred {pred_name}")),
    ]
    for row, col, image, title in tiles:
        _panel_axis(fig, gs, row, col, image, title)

    ax_prob = fig.add_subplot(gs[3, 2])
    _prob_axis(ax_prob, probs, true_label, pred_class)

    fig.suptitle(
        f"mask4ch crop_ui pipeline  |  GT {true_name} → Pred {pred_name}  |  {seg_source}",
        fontsize=12,
        y=0.995,
    )
    save_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _load_mask_for_image(img_path, row, mask_dir, global_size):
    """Load predicted segmentation mask (same resolver as review panels)."""
    mp = resolve_predicted_mask_path(row, img_path, mask_dir)
    if mp is None:
        return torch.zeros(1, global_size, global_size)
    if mp.suffix == ".npy":
        mask_np = np.load(str(mp))
    else:
        mask_np = np.array(Image.open(mp).convert("L"))
    mask_np = (mask_np > 127).astype(np.float32)
    mask_pil = Image.fromarray((mask_np * 255).astype(np.uint8))
    mask_pil = mask_pil.resize((global_size, global_size), Image.NEAREST)
    mask_tensor = torch.from_numpy(np.array(mask_pil).astype(np.float32) / 255.0)
    return mask_tensor.unsqueeze(0)


def _row_resume_key(row, img_path: str) -> str:
    raw = row.get("image_path")
    if raw is not None and not pd.isna(raw) and str(raw).strip():
        return str(raw).strip()
    return str(img_path)


def _load_resume_state(output_dir: Path) -> tuple[list[dict], set[str]]:
    results: list[dict] = []
    done_keys: set[str] = set()
    csv_path = output_dir / "gradcam_results.csv"
    if not csv_path.is_file():
        return results, done_keys
    prev = pd.read_csv(csv_path)
    results = prev.to_dict("records")
    for _, row in prev.iterrows():
        for col in ("image_path", "crop_ui_path"):
            value = row.get(col)
            if value is not None and not pd.isna(value) and str(value).strip():
                done_keys.add(str(value).strip())
    return results, done_keys


def process_samples(
    model,
    cfg,
    df,
    device,
    output_dir,
    max_samples=None,
    resume: bool = False,
    dual_cam_on_misclass: bool = True,
    mask_cam_to_det_box: bool = True,
    det_box_pad: float = 0.12,
    layout: str = "panel",
    live_seg: bool = True,
    seg_backend: str = "dinov3",
    seg_checkpoint: Path | None = None,
    seg_config: Path | None = None,
    cam_focus_mode: str = "roi_expand_px",
    roi_expand_pad: float = 0.22,
    roi_cam_pad_px: int = 40,
    overlay_on_original: bool = True,
    display_max_side: int = 1024,
):
    """Run GradCAM on all samples and save organized output.

    For misclassified samples, runs GradCAM w.r.t. predicted class (why the model
    chose that stage) and w.r.t. true class (what signal aligns with ground truth).
    """
    model_type = cfg.get("model_type", "single_branch")
    is_dual = model_type == "dual_branch"
    use_mask_channel = cfg.get("use_mask_channel", False)
    mask_dir = cfg.get("mask_dir", None)

    global_size = cfg.get("global_size", 384)
    local_size = cfg.get("local_size", 224)
    image_size = cfg.get("image_size", 224)

    g_transform = get_val_transforms(global_size if is_dual else image_size)
    l_transform = get_val_transforms(local_size) if is_dual else None

    gradcam_global = GradCAM(model, get_target_layer(model, cfg, "global"))
    gradcam_local = GradCAM(model, get_target_layer(model, cfg, "local")) if is_dual else None
    clinical_cols = cfg.get("clinical_cols") or []
    use_clinical = bool(cfg.get("clinical_dim", 0) > 0 and clinical_cols)

    results = []

    seg_tool = None
    lumen_tool = None
    lesion_det_tool = None
    seg_label_prefix = "unet"
    if live_seg:
        try:
            from agent.tools.lumen_detection_tool import LumenDetectionTool

            if seg_backend == "dinov3":
                from agent.tools.dinov3_segmentation_tool import DINOv3SegmentationTool

                seg_kw: dict = {"device": device}
                if seg_checkpoint is not None:
                    seg_kw["checkpoint_path"] = Path(seg_checkpoint)
                if seg_config is not None:
                    seg_kw["config_path"] = Path(seg_config)
                seg_tool = DINOv3SegmentationTool(**seg_kw)
                seg_tool._ensure_model()
                seg_label_prefix = "dinov3"
                if seg_tool._model is None:
                    print(f"Warning: DINOv3 seg unavailable ({seg_tool._load_error}); fallback UNet")
                    from agent.tools.segmentation_tool import SegmentationTool

                    seg_tool = SegmentationTool(device=device)
                    seg_tool._ensure_model()
                    seg_label_prefix = "unet"
            else:
                from agent.tools.segmentation_tool import SegmentationTool

                seg_tool = SegmentationTool(device=device)
                seg_tool._ensure_model()
                seg_label_prefix = "unet"

            lumen_tool = LumenDetectionTool(
                weights_path=BEST_LUMEN_YOLO,
                device=str(device),
            )
            lesion_det_tool = LesionDetectionTool(device=str(device))
            lumen_tool._ensure_model()
            lesion_det_tool._ensure_model()

            if seg_backend == "dinov3" and seg_label_prefix == "dinov3":
                ckpt = getattr(seg_tool, "checkpoint_path", None)
                print(
                    "Segmentation: DINOv3 ViT-B/16 last-2-blocks "
                    f"(holdout best; ext Dice≈0.68) [{ckpt}]"
                )
            elif getattr(seg_tool, "_model", None) is not None:
                enc = getattr(seg_tool, "_loaded_encoder", "loaded")
                print(f"Segmentation: UNet ({enc})")
            else:
                print(f"Warning: segmentation unavailable ({getattr(seg_tool, '_load_error', '?')})")
                seg_tool = None
                live_seg = False
            print(f"Lumen YOLO: {BEST_LUMEN_YOLO.name} (loaded={lumen_tool._model is not None})")
            print(f"Lesion YOLO: {BEST_LESION_YOLO.name} (loaded={lesion_det_tool._model is not None})")
        except Exception as exc:
            print(f"Warning: live model init failed ({exc}); CSV/fallback paths")
            seg_tool = None
            live_seg = False

    if max_samples and len(df) > max_samples:
        df = df.sample(max_samples, random_state=42)

    results, done_keys = _load_resume_state(output_dir) if resume else ([], set())
    if resume and done_keys:
        print(f"Resume: {len(done_keys)} rows already in {output_dir / 'gradcam_results.csv'}")

    for idx, (_, row) in enumerate(df.iterrows()):
        img_resolved = resolve_gradcam_image_path(row)
        if img_resolved is None:
            print(f"  Skip missing crop_ui image: {row['image_path']}")
            continue
        img_path = str(Path(img_resolved))
        resume_key = _row_resume_key(row, img_path)
        if resume and resume_key in done_keys:
            continue
        if "crop_ui" not in img_path.replace("\\", "/"):
            print(f"  Warning: not crop_ui path: {img_path}")

        true_label = int(row["label"])
        true_name = CLASS_NAMES[true_label]

        try:
            g_img = Image.open(img_path).convert("RGB")
        except Exception as e:
            print(f"  Skip {img_path}: {e}")
            continue

        orig_h, orig_w = np.array(g_img).shape[:2]
        gt_lesion_mask = load_gt_lesion_mask(img_path, (orig_h, orig_w))

        seg_src = "forced CSV"
        if live_seg and seg_tool is not None:
            lesion_mask, seg_src = load_lesion_mask_from_seg_tool(
                seg_tool, img_path, (orig_h, orig_w), label_prefix=seg_label_prefix
            )
            if lesion_mask is None:
                lesion_mask = load_lesion_mask_np(img_path, row, mask_dir, (orig_h, orig_w))
                seg_src = "UNet empty; CSV fallback"
        else:
            lesion_mask = load_lesion_mask_np(img_path, row, mask_dir, (orig_h, orig_w))

        lumen_box_orig = None
        lesion_box_orig = None
        if lumen_tool is not None:
            lumen_out = lumen_tool.execute(image_path=img_path)
            lumen_box_orig = bbox_dict_to_tuple(lumen_out.get("lumen_bbox"))
        if lesion_det_tool is not None:
            lesion_pick = lesion_det_tool.predict_box(img_path)
            lesion_box_orig = bbox_dict_to_tuple(lesion_pick)
        if lesion_box_orig is None and lesion_mask is not None:
            lesion_box_orig = mask_bbox(lesion_mask)
        if lumen_box_orig is None:
            lumen_box_orig = row_box(row, "lumen_box", (orig_h, orig_w))
        if lesion_box_orig is None:
            lesion_box_orig = row_box(row, "crop_box", (orig_h, orig_w))

        det_boxes = [b for b in (lumen_box_orig, lesion_box_orig, mask_bbox(lesion_mask)) if b is not None]
        det_box_orig = union_boxes(det_boxes, (orig_h, orig_w), pad_ratio=det_box_pad)
        det_box_src = "live YOLO11-L lumen+lesion" if lumen_tool else "CSV/seg union"

        g_tensor = g_transform(g_img).unsqueeze(0).to(device)

        if use_mask_channel:
            if live_seg and lesion_mask is not None:
                mask_ch = mask_tensor_from_binary(lesion_mask, global_size).to(device)
            else:
                mask_ch = _load_mask_for_image(img_path, row, mask_dir, global_size).to(device)
            g_tensor = torch.cat([g_tensor.squeeze(0), mask_ch], dim=0).unsqueeze(0)

        orig_rgb = np.array(g_img)
        focus_mask_orig, expanded_box_orig, gradcam_region_box = build_gradcam_region_mask(
            (orig_h, orig_w),
            mode=cam_focus_mode,
            lesion_box=lesion_box_orig,
            lesion_seg=lesion_mask,
            lumen_box=lumen_box_orig,
            extra_boxes=[b for b in (lumen_box_orig, det_box_orig) if b is not None],
            roi_expand_pad=roi_expand_pad,
            roi_cam_pad_px=roi_cam_pad_px,
        )
        roi_box_for_local = expanded_box_orig if expanded_box_orig is not None else lesion_box_orig
        pred_roi_np = crop_rgb(orig_rgb, roi_box_for_local, pad=0.0)
        pred_roi_disp = cv2.resize(pred_roi_np, (local_size, local_size), interpolation=cv2.INTER_LINEAR)

        if is_dual:
            l_img = Image.fromarray(pred_roi_np).convert("RGB")
            l_tensor = l_transform(l_img).unsqueeze(0).to(device)
            input_tensors = (g_tensor, l_tensor)
        else:
            input_tensors = (g_tensor,)

        if use_clinical:
            cli_vals = [float(row[col]) for col in clinical_cols]
            cli_tensor = torch.tensor([cli_vals], dtype=torch.float32, device=device)
            if is_dual:
                input_tensors = (g_tensor, l_tensor, cli_tensor)
            else:
                input_tensors = (g_tensor, cli_tensor)

        cam_global_pred, probs, pred_class = gradcam_global.generate(
            input_tensors, target_class=None, cfg=cfg
        )
        pred_name = CLASS_NAMES[pred_class]
        is_correct = pred_class == true_label

        cam_global_true = None
        cam_local_pred = None
        cam_local_true = None
        if is_dual and gradcam_local is not None:
            cam_local_pred, _, _ = gradcam_local.generate(input_tensors, target_class=pred_class, cfg=cfg)
        if (not is_correct) and dual_cam_on_misclass and pred_class != true_label:
            cam_global_true, _, _ = gradcam_global.generate(
                input_tensors, target_class=true_label, cfg=cfg
            )
            if is_dual and gradcam_local is not None:
                cam_local_true, _, _ = gradcam_local.generate(
                    input_tensors, target_class=true_label, cfg=cfg
                )

        status = "correct" if is_correct else f"misclassified_as_{pred_name}"
        subdir = output_dir / true_name / status
        subdir.mkdir(parents=True, exist_ok=True)

        if overlay_on_original:
            img_np = resize_for_display(orig_rgb, max_side=display_max_side)
            disp_h, disp_w = img_np.shape[:2]
            disp_shape = (disp_h, disp_w)
        else:
            disp_size = global_size if is_dual else image_size
            disp_shape = (disp_size, disp_size)
            img_np = np.array(g_img.resize(disp_shape))
        det_box_disp = scale_box_to_disp(det_box_orig, (orig_h, orig_w), disp_shape)
        lumen_box_disp = scale_box_to_disp(lumen_box_orig, (orig_h, orig_w), disp_shape)
        lesion_box_disp = scale_box_to_disp(lesion_box_orig, (orig_h, orig_w), disp_shape)
        display_region_box = (
            gradcam_region_box
            if cam_focus_mode == "roi_expand_px" and gradcam_region_box is not None
            else expanded_box_orig
        )
        expanded_box_disp = scale_box_to_disp(display_region_box, (orig_h, orig_w), disp_shape)
        gt_lesion_disp = resize_mask_to_disp(gt_lesion_mask, (orig_h, orig_w), disp_shape)
        lesion_disp = resize_mask_to_disp(lesion_mask, (orig_h, orig_w), disp_shape)

        cam_focus_disp = cv2.resize(focus_mask_orig, (disp_shape[1], disp_shape[0]), interpolation=cv2.INTER_NEAREST)

        cam_focus_roi = None
        if roi_box_for_local is not None:
            x1, y1, x2, y2 = roi_box_for_local
            roi_mask_crop = focus_mask_orig[y1 : y2 + 1, x1 : x2 + 1]
            if roi_mask_crop.size > 0:
                cam_focus_roi = cv2.resize(
                    roi_mask_crop.astype(np.float32),
                    (pred_roi_disp.shape[1], pred_roi_disp.shape[0]),
                    interpolation=cv2.INTER_NEAREST,
                )

        if mask_cam_to_det_box:
            cam_global_pred = constrain_cam_to_mask(cam_global_pred, cam_focus_disp, disp_shape)
            if cam_global_true is not None:
                cam_global_true = constrain_cam_to_mask(cam_global_true, cam_focus_disp, disp_shape)
            if cam_local_pred is not None:
                cam_local_pred = constrain_cam_to_mask(
                    cam_local_pred,
                    cam_focus_roi if cam_focus_roi is not None else np.ones(pred_roi_disp.shape[:2]),
                    pred_roi_disp.shape[:2],
                )
            if cam_local_true is not None:
                cam_local_true = constrain_cam_to_mask(
                    cam_local_true,
                    cam_focus_roi if cam_focus_roi is not None else np.ones(pred_roi_disp.shape[:2]),
                    pred_roi_disp.shape[:2],
                )

        cam_roi_full_pred = None
        cam_roi_full_true = None
        paste_focus = None if cam_focus_mode == "roi_expand_px" else focus_mask_orig
        if is_dual and roi_box_for_local is not None:
            if cam_local_pred is not None:
                cam_roi_full_pred = paste_roi_cam_to_full(
                    cam_local_pred, (orig_h, orig_w), roi_box_for_local, paste_focus
                )
                if cam_focus_mode == "roi_expand_px":
                    cam_roi_full_pred = constrain_cam_to_mask(
                        cam_roi_full_pred, focus_mask_orig, (orig_h, orig_w)
                    )
                cam_roi_full_pred = cv2.resize(
                    cam_roi_full_pred, (disp_shape[1], disp_shape[0]), interpolation=cv2.INTER_LINEAR
                )
            if cam_local_true is not None:
                cam_roi_full_true = paste_roi_cam_to_full(
                    cam_local_true, (orig_h, orig_w), roi_box_for_local, paste_focus
                )
                if cam_focus_mode == "roi_expand_px":
                    cam_roi_full_true = constrain_cam_to_mask(
                        cam_roi_full_true, focus_mask_orig, (orig_h, orig_w)
                    )
                cam_roi_full_true = cv2.resize(
                    cam_roi_full_true, (disp_shape[1], disp_shape[0]), interpolation=cv2.INTER_LINEAR
                )

        fname = Path(row.get("filename", Path(img_path).name)).stem
        panel_dir = output_dir / "panels" / true_name / status
        panel_dir.mkdir(parents=True, exist_ok=True)
        panel_path = panel_dir / f"{fname}_panel.png"

        if layout == "panel":
            save_review_panel(
                panel_path,
                img_np=img_np,
                gt_lesion_disp=gt_lesion_disp,
                lesion_disp=lesion_disp,
                lumen_box_disp=lumen_box_disp,
                lesion_box_disp=lesion_box_disp,
                det_box_disp=det_box_disp,
                cam_global_pred=cam_global_pred,
                cam_global_true=cam_global_true,
                cam_local_pred=cam_local_pred,
                cam_local_true=cam_local_true,
                pred_roi_np=pred_roi_disp,
                probs=probs,
                true_label=true_label,
                pred_class=pred_class,
                det_box_src=det_box_src,
                seg_source=seg_src,
                cam_focus_mask=cam_focus_disp,
                cam_focus_roi=cam_focus_roi,
                cam_roi_full_pred=cam_roi_full_pred,
                cam_roi_full_true=cam_roi_full_true,
                expanded_box_disp=expanded_box_disp,
            )
            ppt_dir = panel_dir / "ppt_assets"
            ppt_dir.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(
                str(ppt_dir / f"{fname}_original_display.png"),
                cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR),
            )
            cv2.imwrite(
                str(ppt_dir / f"{fname}_pred_lesion_overlay.png"),
                cv2.cvtColor(overlay_pred_lesion(img_np, lesion_disp), cv2.COLOR_RGB2BGR),
            )
            if gt_lesion_disp.sum() > 0:
                gt_overlay = img_np.astype(np.float32).copy()
                m = gt_lesion_disp > 0
                gt_overlay[m] = gt_overlay[m] * 0.45 + np.array([80, 220, 80], dtype=np.float32) * 0.55
                cv2.imwrite(
                    str(ppt_dir / f"{fname}_gt_lesion_overlay.png"),
                    cv2.cvtColor(np.clip(gt_overlay, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR),
                )
            cv2.imwrite(
                str(ppt_dir / f"{fname}_global_gradcam_on_original.png"),
                cv2.cvtColor(
                    make_overlay(img_np, cam_global_pred, focus_mask=cam_focus_disp),
                    cv2.COLOR_RGB2BGR,
                ),
            )
            if expanded_box_disp is not None:
                cv2.imwrite(
                    str(ppt_dir / f"{fname}_expanded_roi_box.png"),
                    cv2.cvtColor(
                        draw_det_box(img_np.copy(), expanded_box_disp),
                        cv2.COLOR_RGB2BGR,
                    ),
                )
            if cam_roi_full_pred is not None:
                full_overlay_path = panel_dir / f"{fname}_roi_gradcam_on_original.png"
                cv2.imwrite(
                    str(full_overlay_path),
                    cv2.cvtColor(
                        make_overlay(img_np, cam_roi_full_pred, focus_mask=cam_focus_disp),
                        cv2.COLOR_RGB2BGR,
                    ),
                )
                cv2.imwrite(
                    str(ppt_dir / f"{fname}_roi_gradcam_on_original.png"),
                    cv2.imread(str(full_overlay_path)),
                )
            shutil.copy2(panel_path, subdir / f"{fname}.png")
        else:
            overlay_pred = make_overlay(img_np, cam_global_pred)
            img_with_box = draw_det_box(img_np, det_box_disp)
            prob_str = " ".join(f"{CLASS_NAMES[i]}={probs[i]:.2f}" for i in range(4))
            if cam_global_true is not None:
                overlay_true = make_overlay(img_np, cam_global_true)
                fig, axes = plt.subplots(1, 3, figsize=(16, 5))
                axes[0].imshow(img_with_box)
                axes[0].set_title(f"True: {true_name}\n det={det_box_src}", fontsize=10)
                axes[0].axis("off")
                axes[1].imshow(overlay_pred)
                axes[1].set_title(f"GradCAM @ Pred {pred_name}\n{prob_str}", fontsize=9)
                axes[1].axis("off")
                axes[2].imshow(overlay_true)
                axes[2].set_title(f"GradCAM @ True {true_name}", fontsize=10)
                axes[2].axis("off")
            else:
                fig, axes = plt.subplots(1, 2, figsize=(12, 5))
                axes[0].imshow(img_with_box)
                axes[0].set_title(f"True: {true_name}", fontsize=10)
                axes[0].axis("off")
                axes[1].imshow(overlay_pred)
                axes[1].set_title(f"GradCAM @ Pred {pred_name}\n{prob_str}", fontsize=9)
                axes[1].axis("off")
            fig.savefig(subdir / f"{fname}.png", dpi=150, bbox_inches="tight")
            plt.close(fig)
            shutil.copy2(subdir / f"{fname}.png", panel_path)

        row_out = {
            "filename": fname,
            "image_path": img_path,
            "true_label": true_label,
            "true_name": true_name,
            "pred_class": pred_class,
            "pred_name": pred_name,
            "correct": is_correct,
            "dual_gradcam": bool(cam_global_true is not None),
            "crop_ui_path": img_path,
            "gt_lesion_pixels": int(gt_lesion_mask.sum()) if gt_lesion_mask is not None else 0,
            "det_box_masked": bool(mask_cam_to_det_box and det_box_orig is not None),
            "det_box_source": det_box_src,
            "lumen_box_live": str(lumen_box_orig),
            "lesion_box_live": str(lesion_box_orig),
            "segmentation_source": seg_src,
            "mask_pixels": int(lesion_disp.sum()) if lesion_disp is not None else 0,
            "panel_path": str(panel_path),
            **{f"prob_{CLASS_NAMES[i]}": float(probs[i]) for i in range(4)},
        }
        results.append(row_out)
        done_keys.add(resume_key)

        if (idx + 1) % 50 == 0:
            print(f"  Processed {idx + 1}/{len(df)} images")
            pd.DataFrame(results).to_csv(output_dir / "gradcam_results.csv", index=False)

    gradcam_global.remove_hooks()
    if gradcam_local is not None:
        gradcam_local.remove_hooks()

    results_df = pd.DataFrame(results)
    results_df.to_csv(output_dir / "gradcam_results.csv", index=False)

    print(f"\n{'='*60}")
    print(f"GradCAM Summary: {len(results)} images")
    print(f"{'='*60}")
    for cls_idx, cls_name in enumerate(CLASS_NAMES):
        cls_df = results_df[results_df["true_label"] == cls_idx]
        n = len(cls_df)
        correct = cls_df["correct"].sum()
        print(
            f"  {cls_name}: {n} images, {correct} correct ({correct/n*100:.1f}%)"
            if n > 0
            else f"  {cls_name}: 0 images"
        )

    return results_df


def main():
    parser = argparse.ArgumentParser(description="4-class T-staging GradCAM")
    parser.add_argument("--exp-dir", type=str, required=True,
                        help="Experiment directory (contains best_model.pth)")
    parser.add_argument("--test-csv", type=str, default=None,
                        help="Test CSV (default: test_prospective.csv in data_dir)")
    parser.add_argument(
        "--input-csv",
        type=str,
        default=None,
        help="Use an arbitrary CSV (e.g. test_predictions.csv or t2_misclassified_frames.csv)",
    )
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory (default: exp_dir/gradcam_analysis)")
    parser.add_argument("--max-samples", type=int, default=None,
                        help="Max samples to process (None = all)")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip rows already present in output gradcam_results.csv",
    )
    parser.add_argument("--t2-only", action="store_true",
                        help="Only process T2 samples (for focused analysis)")
    parser.add_argument(
        "--t2-errors-only",
        action="store_true",
        help="Only rows with true T2 (label==1) and pred!=1 (requires pred column)",
    )
    parser.add_argument(
        "--no-dual-cam",
        action="store_true",
        help="Disable second GradCAM @ true class for misclassified samples",
    )
    parser.add_argument(
        "--no-det-box-mask",
        action="store_true",
        help="Do not zero Grad-CAM outside lumen/crop/lesion detection union",
    )
    parser.add_argument(
        "--det-box-pad",
        type=float,
        default=0.12,
        help="Padding ratio when unioning lumen + crop + lesion boxes (default 0.12)",
    )
    parser.add_argument(
        "--layout",
        choices=("panel", "simple"),
        default="panel",
        help="panel: 3x3 equal review composite; simple: legacy 2–3 column layout",
    )
    parser.add_argument(
        "--no-live-seg",
        action="store_true",
        help="Use forced-pipeline CSV masks instead of live segmentation inference",
    )
    parser.add_argument(
        "--seg-backend",
        choices=("dinov3", "unet"),
        default="dinov3",
        help="Live segmentation backend: dinov3 (best external Dice) or unet fulldata",
    )
    parser.add_argument(
        "--seg-checkpoint",
        type=str,
        default=None,
        help="Override DINOv3 seg checkpoint (default: holdout best.pt, ext Dice 0.682)",
    )
    parser.add_argument(
        "--seg-config",
        type=str,
        default=None,
        help="Override DINOv3 seg YAML config",
    )
    parser.add_argument(
        "--cam-focus",
        choices=("roi_expand_px", "lesion_wall", "lesion", "seg", "union"),
        default="roi_expand_px",
        help="CAM region: roi_expand_px=expanded ROI rect + --roi-cam-pad-px (default); "
        "lesion_wall=seg wall band mask",
    )
    parser.add_argument(
        "--roi-expand-pad",
        type=float,
        default=0.22,
        help="Ratio pad when building expanded ROI box before +px (default 0.22)",
    )
    parser.add_argument(
        "--roi-cam-pad-px",
        type=int,
        default=40,
        help="Extra pixel pad on expanded ROI for Grad-CAM heatmap display (default 40)",
    )
    parser.add_argument(
        "--display-max-side",
        type=int,
        default=1024,
        help="Longest side when overlaying Grad-CAM on original crop_ui frame (default 1024)",
    )
    parser.add_argument(
        "--no-overlay-original",
        action="store_true",
        help="Use legacy 384px square display instead of original aspect ratio",
    )
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    exp_dir = Path(args.exp_dir)

    print(f"Loading model from {exp_dir}")
    model, cfg = load_model(exp_dir, device)

    if args.input_csv:
        test_csv = Path(args.input_csv)
    elif args.test_csv:
        test_csv = Path(args.test_csv)
    else:
        data_dir = cfg.get("data_dir", "pipeline/data/tstaging_4class")
        data_path = Path(data_dir)
        if not data_path.is_absolute():
            for base in BASE_DIRS:
                candidate = base / data_dir
                if candidate.exists():
                    data_path = candidate
                    break
        test_csv = data_path / "test_prospective.csv"

    print(f"Input CSV: {test_csv}")
    df = pd.read_csv(test_csv)
    df = enrich_detection_boxes(df)
    df = enrich_clinical_columns(df, cfg)
    n_with_lumen = int(df["lumen_box_x1"].notna().sum()) if "lumen_box_x1" in df.columns else 0
    print(f"Detection boxes merged: lumen_box present on {n_with_lumen}/{len(df)} rows")

    if args.t2_only:
        df = df[df["label"] == 1]
        print(f"T2-only mode: {len(df)} samples")

    if args.t2_errors_only:
        if "pred" not in df.columns:
            raise SystemExit("--t2-errors-only requires a 'pred' column (e.g. test_predictions.csv)")
        df = df[(df["label"] == 1) & (df["pred"] != 1)]
        print(f"T2-errors-only: {len(df)} samples")

    output_dir = derive_gradcam_output_dir(exp_dir, test_csv, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Output: {output_dir}")
    print(f"Device: {device}")
    print(f"Model type: {cfg.get('model_type', 'single_branch')}")
    print(f"Samples: {len(df)}")
    print(
        f"Grad-CAM region: {args.cam_focus}"
        + (f" (expanded ROI + {args.roi_cam_pad_px}px)" if args.cam_focus == "roi_expand_px" else "")
        + "; target = predicted class (real backward)"
    )

    seg_ckpt = Path(args.seg_checkpoint) if args.seg_checkpoint else None
    seg_cfg_path = Path(args.seg_config) if args.seg_config else None

    process_samples(
        model,
        cfg,
        df,
        device,
        output_dir,
        args.max_samples,
        resume=args.resume,
        dual_cam_on_misclass=not args.no_dual_cam,
        mask_cam_to_det_box=not args.no_det_box_mask,
        det_box_pad=args.det_box_pad,
        layout=args.layout,
        live_seg=not args.no_live_seg,
        seg_backend=args.seg_backend,
        seg_checkpoint=seg_ckpt,
        seg_config=seg_cfg_path,
        cam_focus_mode=args.cam_focus,
        roi_expand_pad=args.roi_expand_pad,
        roi_cam_pad_px=args.roi_cam_pad_px,
        overlay_on_original=not args.no_overlay_original,
        display_max_side=args.display_max_side,
    )
    print("\nDone.")


if __name__ == "__main__":
    main()
