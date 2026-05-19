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

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from PIL import Image
from torchvision import transforms

from lib.models import DualBranchClassifier, SingleBranchClassifier
from lib.transforms import get_val_transforms
from lib.experiment_tree import derive_gradcam_output_dir

CLASS_NAMES = ["T1", "T2", "T3", "T4+"]
BASE_DIR = Path("/data/research/gastric/Tstaging")


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


def get_target_layer(model, cfg):
    """Determine the target layer for GradCAM based on model type."""
    model_type = cfg.get("model_type", "single_branch")

    if model_type == "dual_branch":
        # Hook the global branch's last conv block
        backbone = model.g_backbone
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


def make_overlay(img_np, cam, alpha=0.4):
    """Overlay GradCAM heatmap on image."""
    h, w = img_np.shape[:2]
    cam_resized = cv2.resize(cam, (w, h))
    heatmap = cv2.applyColorMap(np.uint8(255 * cam_resized), cv2.COLORMAP_JET)
    heatmap = cv2.cvtColor(heatmap, cv2.COLOR_BGR2RGB)
    overlay = (heatmap * alpha + img_np * (1 - alpha)).clip(0, 255).astype(np.uint8)
    return overlay


def _load_mask_for_image(img_path, mask_dir, global_size):
    """Load predicted segmentation mask and return as a single-channel tensor."""
    stem = Path(img_path).stem
    mask_loaded = False
    mask_np = None
    if mask_dir is not None:
        for ext in ['.png', '.jpg', '.npy']:
            mp = Path(mask_dir) / f"{stem}{ext}"
            if mp.exists():
                if ext == '.npy':
                    mask_np = np.load(str(mp))
                else:
                    mask_np = np.array(Image.open(mp).convert('L'))
                mask_loaded = True
                break
    if mask_loaded and mask_np is not None:
        mask_np = (mask_np > 127).astype(np.float32)
        mask_pil = Image.fromarray((mask_np * 255).astype(np.uint8))
        mask_pil = mask_pil.resize((global_size, global_size), Image.NEAREST)
        mask_tensor = torch.from_numpy(np.array(mask_pil).astype(np.float32) / 255.0)
        return mask_tensor.unsqueeze(0)
    return torch.zeros(1, global_size, global_size)


def process_samples(
    model,
    cfg,
    df,
    device,
    output_dir,
    max_samples=None,
    dual_cam_on_misclass: bool = True,
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

    target_layer = get_target_layer(model, cfg)
    gradcam = GradCAM(model, target_layer)
    clinical_cols = cfg.get("clinical_cols") or []
    use_clinical = bool(cfg.get("clinical_dim", 0) > 0 and clinical_cols)

    results = []

    if max_samples and len(df) > max_samples:
        df = df.sample(max_samples, random_state=42)

    for idx, (_, row) in enumerate(df.iterrows()):
        img_path = row["image_path"]
        if not Path(img_path).is_absolute():
            img_path = str(BASE_DIR / img_path)

        true_label = int(row["label"])
        true_name = CLASS_NAMES[true_label]

        try:
            g_img = Image.open(img_path).convert("RGB")
        except Exception as e:
            print(f"  Skip {img_path}: {e}")
            continue

        g_tensor = g_transform(g_img).unsqueeze(0).to(device)

        if use_mask_channel:
            mask_ch = _load_mask_for_image(img_path, mask_dir, global_size).to(device)
            g_tensor = torch.cat([g_tensor.squeeze(0), mask_ch], dim=0).unsqueeze(0)

        if is_dual:
            roi_path = row.get("roi_path", "")
            if pd.notna(roi_path) and str(roi_path).strip() and Path(str(roi_path)).exists():
                l_img = Image.open(str(roi_path)).convert("RGB")
            else:
                w, h = g_img.size
                crop_w, crop_h = int(w * 0.6), int(h * 0.6)
                left, top = (w - crop_w) // 2, (h - crop_h) // 2
                l_img = g_img.crop((left, top, left + crop_w, top + crop_h))

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

        cam_pred, probs, pred_class = gradcam.generate(
            input_tensors, target_class=None, cfg=cfg
        )
        pred_name = CLASS_NAMES[pred_class]
        is_correct = pred_class == true_label

        cam_true = None
        if (not is_correct) and dual_cam_on_misclass and pred_class != true_label:
            cam_true, _, _ = gradcam.generate(
                input_tensors, target_class=true_label, cfg=cfg
            )

        status = "correct" if is_correct else f"misclassified_as_{pred_name}"
        subdir = output_dir / true_name / status
        subdir.mkdir(parents=True, exist_ok=True)

        img_np = np.array(
            g_img.resize(
                (global_size if is_dual else image_size, global_size if is_dual else image_size)
            )
        )
        overlay_pred = make_overlay(img_np, cam_pred)

        prob_str = " ".join(f"{CLASS_NAMES[i]}={probs[i]:.2f}" for i in range(4))

        if cam_true is not None:
            overlay_true = make_overlay(img_np, cam_true)
            fig, axes = plt.subplots(1, 3, figsize=(16, 5))
            axes[0].imshow(img_np)
            axes[0].set_title(f"True: {true_name}", fontsize=12)
            axes[0].axis("off")
            axes[1].imshow(overlay_pred)
            axes[1].set_title(
                f"GradCAM @ Pred {pred_name}\n{prob_str}", fontsize=9
            )
            axes[1].axis("off")
            axes[2].imshow(overlay_true)
            axes[2].set_title(f"GradCAM @ True {true_name}", fontsize=12)
            axes[2].axis("off")
        else:
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))
            axes[0].imshow(img_np)
            axes[0].set_title(f"True: {true_name}", fontsize=12)
            axes[0].axis("off")
            axes[1].imshow(overlay_pred)
            axes[1].set_title(
                f"GradCAM @ Pred {pred_name}\n{prob_str}", fontsize=10
            )
            axes[1].axis("off")

        fname = Path(row.get("filename", Path(img_path).name)).stem
        fig.savefig(subdir / f"{fname}.png", dpi=150, bbox_inches="tight")
        plt.close(fig)

        row_out = {
            "filename": fname,
            "image_path": img_path,
            "true_label": true_label,
            "true_name": true_name,
            "pred_class": pred_class,
            "pred_name": pred_name,
            "correct": is_correct,
            "dual_gradcam": bool(cam_true is not None),
            **{f"prob_{CLASS_NAMES[i]}": float(probs[i]) for i in range(4)},
        }
        results.append(row_out)

        if (idx + 1) % 50 == 0:
            print(f"  Processed {idx + 1}/{len(df)} images")

    gradcam.remove_hooks()

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
        if not Path(data_dir).is_absolute():
            data_dir = BASE_DIR / data_dir
        test_csv = Path(data_dir) / "test_prospective.csv"

    print(f"Input CSV: {test_csv}")
    df = pd.read_csv(test_csv)

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

    process_samples(
        model,
        cfg,
        df,
        device,
        output_dir,
        args.max_samples,
        dual_cam_on_misclass=not args.no_dual_cam,
    )
    print("\nDone.")


if __name__ == "__main__":
    main()
