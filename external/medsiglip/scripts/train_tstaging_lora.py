#!/usr/bin/env python3
"""T-staging 4-class LoRA in one file.

Full view = crop_ui + mask polygon. ROI = official crop_roi (mask-box only if missing).
LoRA last 2 of 27 MedSigLIP-448 vision blocks, r=8. Head is the default concat-gated xlarge.

    cd /data/research/gastric/GastricTstaging/medsiglip
    python3 scripts/train_tstaging_lora.py --device cuda:0

Current run defaults: warm-head, freeze-head 3, last-2, r=8, batch 4, max-frames 6, 20 epochs.
Does not write the frozen 20% embedding cache. Public Assist is unchanged.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from peft import LoraConfig, get_peft_model, get_peft_model_state_dict, set_peft_model_state_dict
from PIL import Image
from torch.optim.lr_scheduler import LambdaLR
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel, AutoProcessor

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "pipeline") not in sys.path:
    sys.path.insert(0, str(ROOT / "pipeline"))

from medsiglip_gastricus.constants import (  # noqa: E402
    CLASS_NAMES,
    DATASET_DIR,
    DEFAULT_FOURCLASS_CKPT,
    EMBED_DIM,
    N_CLASSES,
    PLAN_COMPLETE_REPORT_DIR,
    SPLIT_FILES,
    TSTAGING_LORA_REPORT_DIR,
    WEIGHT_DIR,
)
from medsiglip_gastricus.metrics import center_of, confusion, per_center, score_arrays  # noqa: E402
from medsiglip_gastricus.model import GastricUSFromScratch  # noqa: E402

PAD = "black"
ROI_EXPAND = 0.20


def _abs(path: object) -> Path:
    value = Path(str(path or ""))
    if not str(value):
        return value
    return value if value.is_absolute() else ROOT / value


def assert_weights() -> Path:
    if not (WEIGHT_DIR / "config.json").is_file():
        raise FileNotFoundError(f"MedSigLIP weights missing: {WEIGHT_DIR}")
    return WEIGHT_DIR


def full_frame(image: str | Path | Image.Image) -> Image.Image:
    if isinstance(image, Image.Image):
        return image.convert("RGB")
    return Image.open(_abs(image)).convert("RGB")


def load_mask(path: Path, size: tuple[int, int]) -> np.ndarray:
    mask = np.array(Image.open(path).convert("L").resize(size, Image.NEAREST))
    return mask > 0


def square_pad(crop: Image.Image) -> Image.Image:
    cw, ch = crop.size
    side = max(cw, ch)
    if cw == side and ch == side:
        return crop
    canvas = Image.new("RGB", (side, side), (0, 0, 0))
    canvas.paste(crop, ((side - cw) // 2, (side - ch) // 2))
    return canvas


def overlay_mask_polygon(image: Image.Image, mask: np.ndarray, fill_alpha: float = 0.22) -> Image.Image:
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
    try:
        from scipy import ndimage

        ring = binary & ~ndimage.binary_erosion(binary, iterations=2)
    except Exception:
        ring = binary
    out[ring] = highlight
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def official_roi_from_crop_ui(crop_ui: Path) -> Path | None:
    crop_ui = Path(crop_ui)
    cursor = crop_ui
    while cursor.name != "crop_ui" and cursor != cursor.parent:
        cursor = cursor.parent
    if cursor.name != "crop_ui":
        return None
    cand = cursor.parent / "crop_roi" / crop_ui.relative_to(cursor)
    return cand if cand.is_file() else None


def roi_mask_for(official_roi: Path) -> Path | None:
    stem = official_roi.stem
    parent = official_roi.parent
    for folder in ("roi_masks", "masks"):
        for suffix in (".png", ".jpg"):
            cand = parent.parent / folder / f"{stem}{suffix}"
            if cand.is_file():
                return cand
    return None


def expanded_box(mask: np.ndarray, size: tuple[int, int], expand: float) -> tuple[int, int, int, int]:
    width, height = size
    ys, xs = np.where(mask)
    if len(xs) == 0:
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        return left, top, left + side - 1, top + side - 1
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())
    pad_x = int(round(max(x1 - x0 + 1, 1) * float(expand)))
    pad_y = int(round(max(y1 - y0 + 1, 1) * float(expand)))
    return max(0, x0 - pad_x), max(0, y0 - pad_y), min(width - 1, x1 + pad_x), min(height - 1, y1 + pad_y)


def load_lora_views(
    crop_ui: Path,
    mask_path: Path | None,
    official_roi: Path | None = None,
    expand: float = ROI_EXPAND,
) -> tuple[Image.Image, Image.Image]:
    full = full_frame(crop_ui)
    if mask_path is not None and Path(mask_path).is_file():
        mask = load_mask(Path(mask_path), full.size)
        full_view = overlay_mask_polygon(full, mask, fill_alpha=0.16)
    else:
        full_view = full
        mask = None
    if official_roi is not None and Path(official_roi).is_file():
        roi_rgb = full_frame(official_roi)
        roi_mask_path = roi_mask_for(Path(official_roi))
        if roi_mask_path is not None:
            roi_rgb = overlay_mask_polygon(roi_rgb, load_mask(roi_mask_path, roi_rgb.size), fill_alpha=0.30)
        return full_view, square_pad(roi_rgb)
    if mask is not None:
        x0, y0, x1, y1 = expanded_box(mask, full.size, expand)
        roi_rgb = full.crop((x0, y0, x1 + 1, y1 + 1))
        roi_mask = mask[y0 : y1 + 1, x0 : x1 + 1]
        return full_view, square_pad(overlay_mask_polygon(roi_rgb, roi_mask, fill_alpha=0.30))
    return full_view, square_pad(full)


def select_frame_idx(n: int, max_frames: int) -> list[int]:
    return list(range(n if n <= max_frames else max_frames))


def cosine_warmup(epoch: int, epochs: int, warmup: int) -> float:
    if epoch < warmup:
        return float(epoch + 1) / max(warmup, 1)
    progress = (epoch - warmup) / max(epochs - warmup, 1)
    return 0.01 + 0.5 * 0.99 * (1.0 + math.cos(math.pi * progress))


def ordinal_rank_loss(logits: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    prob = torch.softmax(logits, dim=-1)
    ranks = torch.arange(N_CLASSES, device=logits.device, dtype=prob.dtype)
    expected = (prob * ranks).sum(dim=-1)
    return torch.nn.functional.smooth_l1_loss(expected, y.float())


def jsonable(value):
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    return value


class ImageBagDataset(Dataset):
    def __init__(self, split: str, max_frames: int = 6, expand: float = ROI_EXPAND, seed: int = 20260826) -> None:
        table = pd.read_csv(DATASET_DIR / SPLIT_FILES[split])
        usable = table[(table["crop_ui_path"] != "") & (table["mask_path"] != "")].reset_index(drop=True)
        bags: dict[str, dict[str, list]] = defaultdict(
            lambda: {"crop": [], "mask": [], "roi": [], "clinical": [], "label": [], "source": []}
        )
        for _, row in usable.iterrows():
            pid = str(row["patient_id"])
            crop = str(row["crop_ui_path"])
            official = official_roi_from_crop_ui(_abs(crop))
            bags[pid]["crop"].append(crop)
            bags[pid]["mask"].append(str(row["mask_path"]))
            bags[pid]["roi"].append(str(official) if official is not None else "")
            bags[pid]["clinical"].append(json.loads(row["clinical_22"]))
            bags[pid]["label"].append(int(row["label"]))
            bags[pid]["source"].append(str(row["source"]))
        self.bags = bags
        self.pids = sorted(bags)
        self.max_frames = max_frames
        self.expand = expand
        self.seed = seed

    def __len__(self) -> int:
        return len(self.pids)

    def labels(self) -> list[int]:
        return [int(max(set(self.bags[pid]["label"]), key=self.bags[pid]["label"].count)) for pid in self.pids]

    def __getitem__(self, idx: int) -> dict[str, object]:
        pid = self.pids[idx]
        bag = self.bags[pid]
        keep = select_frame_idx(len(bag["crop"]), self.max_frames)
        fulls, rois = [], []
        for i in keep:
            full, roi = load_lora_views(
                _abs(bag["crop"][i]),
                _abs(bag["mask"][i]) if bag["mask"][i] else None,
                official_roi=_abs(bag["roi"][i]) if bag["roi"][i] else None,
                expand=self.expand,
            )
            fulls.append(full)
            rois.append(roi)
        labels = [bag["label"][i] for i in keep]
        return {
            "full": fulls,
            "roi": rois,
            "clinical": torch.from_numpy(np.mean([bag["clinical"][i] for i in keep], axis=0).astype(np.float32)),
            "label": torch.tensor(int(max(set(labels), key=labels.count)), dtype=torch.long),
            "n": torch.tensor(len(keep), dtype=torch.long),
            "patient_id": pid,
            "source": Counter(bag["source"]).most_common(1)[0][0],
        }


def make_collate(processor):
    def collate(batch: list[dict[str, object]]) -> dict[str, object]:
        max_t = max(int(item["n"]) for item in batch)
        images: list[Image.Image] = []
        index: list[tuple[int, int, str]] = []
        for b, item in enumerate(batch):
            for t in range(int(item["n"])):
                images.append(item["full"][t])
                index.append((b, t, "full"))
                images.append(item["roi"][t])
                index.append((b, t, "roi"))
        pixels = processor(images=images, return_tensors="pt")["pixel_values"]
        bsz = len(batch)
        pixel_full = torch.zeros(bsz, max_t, *pixels.shape[1:])
        pixel_roi = torch.zeros(bsz, max_t, *pixels.shape[1:])
        valid = torch.zeros(bsz, max_t, dtype=torch.bool)
        for cursor, (b, t, view) in enumerate(index):
            if view == "full":
                pixel_full[b, t] = pixels[cursor]
            else:
                pixel_roi[b, t] = pixels[cursor]
                valid[b, t] = True
        return {
            "pixel_full": pixel_full,
            "pixel_roi": pixel_roi,
            "valid": valid,
            "clinical": torch.stack([item["clinical"] for item in batch], dim=0),
            "label": torch.stack([item["label"] for item in batch], dim=0),
            "patient_id": [item["patient_id"] for item in batch],
            "source": [item["source"] for item in batch],
        }

    return collate


class DualViewLoRA(torch.nn.Module):
    def __init__(self, backbone, head: GastricUSFromScratch) -> None:
        super().__init__()
        self.backbone = backbone
        self.head = head

    def encode(self, pixel: torch.Tensor) -> torch.Tensor:
        feats = self.backbone.get_image_features(pixel_values=pixel)
        return torch.nn.functional.normalize(feats, p=2, dim=-1)

    def forward(
        self,
        pixel_full: torch.Tensor,
        pixel_roi: torch.Tensor,
        valid: torch.Tensor,
        clinical: torch.Tensor,
    ) -> torch.Tensor:
        bsz, max_t = valid.shape
        e_full = pixel_full.new_zeros(bsz, max_t, EMBED_DIM)
        e_roi = pixel_roi.new_zeros(bsz, max_t, EMBED_DIM)
        idx = valid.nonzero(as_tuple=False)
        if idx.numel() == 0:
            return self.head(e_full, e_roi, valid, clinical)
        full_list = pixel_full[idx[:, 0], idx[:, 1]]
        roi_list = pixel_roi[idx[:, 0], idx[:, 1]]
        stacked = torch.cat([full_list, roi_list], dim=0)
        embeds = self.encode(stacked)
        n = full_list.shape[0]
        e_full[idx[:, 0], idx[:, 1]] = embeds[:n]
        e_roi[idx[:, 0], idx[:, 1]] = embeds[n:]
        return self.head(e_full, e_roi, valid, clinical)


def wrap_lora(backbone, last_n: int, rank: int, alpha: int):
    n_layers = len(backbone.vision_model.encoder.layers)
    start = max(0, n_layers - last_n)
    targets = []
    for i in range(start, n_layers):
        prefix = f"vision_model.encoder.layers.{i}"
        for name in (
            "self_attn.q_proj",
            "self_attn.k_proj",
            "self_attn.v_proj",
            "self_attn.out_proj",
            "mlp.fc1",
            "mlp.fc2",
        ):
            targets.append(f"{prefix}.{name}")
    for param in backbone.parameters():
        param.requires_grad = False
    wrapped = get_peft_model(backbone, LoraConfig(r=rank, lora_alpha=alpha, target_modules=targets, bias="none"))
    vision = wrapped.get_base_model().vision_model if hasattr(wrapped, "get_base_model") else wrapped.vision_model

    def _keep_grad(_module, _inp, output):
        if torch.is_tensor(output):
            output.requires_grad_(True)
        return output

    vision.embeddings.patch_embedding.register_forward_hook(_keep_grad)
    if hasattr(wrapped, "gradient_checkpointing_enable"):
        wrapped.gradient_checkpointing_enable()
    return wrapped, targets, n_layers


def resolve_warm_ckpt(path: Path | None) -> Path:
    ckpt = Path(path) if path else DEFAULT_FOURCLASS_CKPT
    if ckpt.is_file():
        return ckpt
    alt = PLAN_COMPLETE_REPORT_DIR / "mlp_concat_gated" / "best_model.pt"
    if alt.is_file():
        return alt
    raise FileNotFoundError(f"warm-head checkpoint missing: {ckpt}")


def make_head() -> GastricUSFromScratch:
    return GastricUSFromScratch(
        clinical_dim=22,
        fusion="concat",
        pool="gated",
        size="xlarge",
        pool_proj=False,
        residual=True,
    )


def loader_kwargs(processor, device: str, num_workers: int) -> dict[str, object]:
    kw: dict[str, object] = {
        "collate_fn": make_collate(processor),
        "num_workers": int(num_workers),
        "pin_memory": device.startswith("cuda"),
    }
    if int(num_workers) > 0:
        kw["persistent_workers"] = True
        kw["prefetch_factor"] = 2
    return kw


@torch.no_grad()
def evaluate(model: DualViewLoRA, loader: DataLoader, device: str) -> dict[str, object]:
    model.eval()
    ys, preds, sources, pids = [], [], [], []
    for batch in loader:
        with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=device.startswith("cuda")):
            logits = model(
                batch["pixel_full"].to(device),
                batch["pixel_roi"].to(device),
                batch["valid"].to(device),
                batch["clinical"].to(device),
            )
        pred = logits.argmax(dim=-1).cpu().numpy().astype(int)
        y = batch["label"].cpu().numpy().astype(int)
        ys.extend(y.tolist())
        preds.extend(pred.tolist())
        sources.extend(batch["source"])
        pids.extend(batch["patient_id"])
    y_arr = np.asarray(ys, dtype=int)
    pred_arr = np.asarray(preds, dtype=int)
    metrics = score_arrays(y_arr, pred_arr)
    metrics["confusion"] = confusion(y_arr, pred_arr)
    metrics["centers"] = per_center(y_arr, pred_arr, sources)
    metrics["predictions"] = [
        {"patient_id": pid, "source": src, "y": int(y), "pred": int(p)}
        for pid, src, y, p in zip(pids, sources, y_arr, pred_arr)
    ]
    return metrics


def write_predictions(report_dir: Path, split: str, rows: list[dict[str, object]]) -> None:
    (report_dir / f"{split}_predictions.csv").write_text(
        "split,center,patient_id,y,pred,T_true,T_pred,adjacent\n"
        + "".join(
            f"{split},{center_of(r['source'])},{r['patient_id']},{r['y']},{r['pred']},"
            f"{CLASS_NAMES[r['y']]},{CLASS_NAMES[r['pred']]},{int(abs(r['y'] - r['pred']) <= 1)}\n"
            for r in rows
        ),
        encoding="utf-8",
    )


def write_compare(report_dir: Path, best: dict, evals: dict[str, dict[str, object]]) -> None:
    lines = [
        "# T-staging LoRA (official crop_roi)",
        "",
        f"Lock epoch {best.get('epoch', 0)}, val ACC {float(best.get('val_acc', 0)):.4f}.",
        "",
        "| split | n | ACC | adj | QWK | T2 | T3 |",
        "|-------|--:|----:|----:|----:|---:|---:|",
    ]
    for name, row in evals.items():
        lines.append(
            f"| {name} | {row['n']} | {row['acc']:.4f} | {row['adj_acc']:.4f} | "
            f"{row['qwk']:.4f} | {row['t2_recall']:.4f} | {row['recall_T3']:.4f} |"
        )
    lines += [
        "",
        "Full paints crop_ui mask. ROI is official crop_roi. LoRA last 2 vision blocks.",
        "Do not promote Assist until prospective and external exact ACC are in.",
        "",
    ]
    (report_dir / "COMPARE.md").write_text("\n".join(lines), encoding="utf-8")


def build_model(args: argparse.Namespace):
    assert_weights()
    processor = AutoProcessor.from_pretrained(str(WEIGHT_DIR), local_files_only=True)
    backbone = AutoModel.from_pretrained(str(WEIGHT_DIR), local_files_only=True)
    backbone, targets, n_layers = wrap_lora(backbone, last_n=args.last_n, rank=args.lora_r, alpha=args.lora_alpha)
    head = make_head()
    warm_ckpt = ""
    if args.warm_head:
        ckpt = resolve_warm_ckpt(Path(args.warm_ckpt) if args.warm_ckpt else None)
        payload = torch.load(ckpt, map_location="cpu", weights_only=False)
        missing, unexpected = head.load_state_dict(payload["model"], strict=True)
        warm_ckpt = str(ckpt)
        print(f"warm_head {ckpt} missing={list(missing)} unexpected={list(unexpected)}", flush=True)
    model = DualViewLoRA(backbone, head).to(args.device)
    return model, processor, targets, n_layers, warm_ckpt


def train(args: argparse.Namespace) -> dict[str, object]:
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    tag = f"lora{args.last_n}_r{args.lora_r}_warmhead_freezehead{args.freeze_head_epochs}_officialroi"
    report_dir = Path(args.report_dir) if args.report_dir else (TSTAGING_LORA_REPORT_DIR / tag)
    report_dir.mkdir(parents=True, exist_ok=True)
    model, processor, targets, n_layers, warm_ckpt = build_model(args)
    kw = loader_kwargs(processor, args.device, args.num_workers)
    train_ds = ImageBagDataset("train", max_frames=args.max_frames, expand=args.expand, seed=args.seed)
    loaders = {
        "train": DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, **kw),
        "val": DataLoader(
            ImageBagDataset("val", max_frames=args.max_frames, expand=args.expand, seed=args.seed),
            batch_size=args.batch_size,
            shuffle=False,
            **kw,
        ),
        "test_prospective": DataLoader(
            ImageBagDataset("test_prospective", max_frames=args.max_frames, expand=args.expand, seed=args.seed),
            batch_size=args.batch_size,
            shuffle=False,
            **kw,
        ),
        "test_external": DataLoader(
            ImageBagDataset("test_external", max_frames=args.max_frames, expand=args.expand, seed=args.seed),
            batch_size=args.batch_size,
            shuffle=False,
            **kw,
        ),
    }
    counts = Counter(train_ds.labels())
    weights = [len(train_ds) / (N_CLASSES * max(counts.get(i, 1), 1)) for i in range(N_CLASSES)]
    loss_fn = torch.nn.CrossEntropyLoss(
        weight=torch.tensor(weights, dtype=torch.float32, device=args.device),
        label_smoothing=args.label_smoothing,
    )
    opt = torch.optim.AdamW(
        [
            {"params": [p for p in model.backbone.parameters() if p.requires_grad], "lr": args.encoder_lr},
            {"params": model.head.parameters(), "lr": args.head_lr},
        ],
        weight_decay=args.weight_decay,
    )
    scheduler = LambdaLR(opt, lambda epoch: cosine_warmup(epoch, args.epochs, args.warmup_epochs))
    spec = {
        "script": str(Path(__file__).resolve()),
        "name": tag,
        "task": "t_staging_4class",
        "backbone": "google/medsiglip-448",
        "views": "full_polygon + official_crop_roi",
        "last_n": args.last_n,
        "lora_r": args.lora_r,
        "lora_alpha": args.lora_alpha,
        "lora_targets": targets,
        "n_vision_layers": n_layers,
        "encoder_lr": args.encoder_lr,
        "head_lr": args.head_lr,
        "max_frames": args.max_frames,
        "batch_size": args.batch_size,
        "num_workers": args.num_workers,
        "freeze_head_epochs": args.freeze_head_epochs,
        "warm_head": args.warm_head,
        "warm_ckpt": warm_ckpt,
        "n_params": int(sum(p.numel() for p in model.parameters() if p.requires_grad)),
        "lock": args.lock,
    }
    (report_dir / "spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(
        f"tstaging-lora {tag} patients={len(train_ds)} last_n={args.last_n} "
        f"lora={spec['n_params']} batch={args.batch_size}",
        flush=True,
    )
    best = {"val_acc": -1.0, "val_adj_acc": -1.0, "epoch": 0}
    history = []
    ckpt = report_dir / "best_adapters.pt"
    stale = 0
    for epoch in range(1, args.epochs + 1):
        freeze_head = epoch <= int(args.freeze_head_epochs)
        for param in model.head.parameters():
            param.requires_grad = not freeze_head
        model.train()
        running = 0.0
        seen = 0
        n_steps = len(loaders["train"])
        for step, batch in enumerate(loaders["train"], 1):
            opt.zero_grad(set_to_none=True)
            labels_b = batch["label"].to(args.device)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=args.device.startswith("cuda")):
                logits = model(
                    batch["pixel_full"].to(args.device),
                    batch["pixel_roi"].to(args.device),
                    batch["valid"].to(args.device),
                    batch["clinical"].to(args.device),
                )
                loss = loss_fn(logits, labels_b)
                if args.ordinal_weight > 0:
                    loss = loss + args.ordinal_weight * ordinal_rank_loss(logits, labels_b)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            running += float(loss.item())
            seen += 1
            if step % 20 == 0 or step == n_steps:
                print(f"  epoch {epoch} {step}/{n_steps} loss={running / seen:.4f}", flush=True)
        scheduler.step()
        val = evaluate(model, loaders["val"], args.device)
        slim = {k: val[k] for k in ("n", "acc", "adj_acc", "off2", "qwk", "serosa_acc", "macro_recall", "t2_recall", "recall_T3")}
        row = {"epoch": epoch, "train_loss": running / max(seen, 1), **{f"val_{k}": slim[k] for k in slim}}
        history.append(row)
        print(json.dumps({k: (float(v) if isinstance(v, (float, np.floating)) else v) for k, v in row.items()}), flush=True)
        with (report_dir / "train.log").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(jsonable(row)) + "\n")
        if float(slim["acc"]) > float(best["val_acc"]):
            best = {"val_acc": float(slim["acc"]), "val_adj_acc": float(slim["adj_acc"]), "epoch": epoch, "val": slim}
            torch.save(
                {
                    "adapters": get_peft_model_state_dict(model.backbone),
                    "head": model.head.state_dict(),
                    "epoch": epoch,
                    "val": slim,
                    "spec": spec,
                    "mode": "lora",
                },
                ckpt,
            )
            stale = 0
        else:
            stale += 1
            if stale >= args.patience:
                print(f"early stop at epoch {epoch}, best={best['epoch']}", flush=True)
                break
    saved = torch.load(ckpt, map_location=args.device, weights_only=False)
    set_peft_model_state_dict(model.backbone, saved["adapters"])
    model.head.load_state_dict(saved["head"])
    evals = {}
    for name, loader in loaders.items():
        if name == "train":
            continue
        metrics = evaluate(model, loader, args.device)
        write_predictions(report_dir, name, metrics.pop("predictions"))
        evals[name] = metrics
    payload = {"best": best, "eval": evals, "history": history, "spec": spec}
    (report_dir / "metrics.json").write_text(json.dumps(jsonable(payload), indent=2), encoding="utf-8")
    write_compare(report_dir, best, evals)
    print(f"report={report_dir}", flush=True)
    return payload


def eval_ckpt(args: argparse.Namespace) -> dict[str, object]:
    ckpt_path = Path(args.ckpt)
    payload = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    spec = dict(payload.get("spec") or {})
    args.last_n = int(spec.get("last_n", args.last_n))
    args.lora_r = int(spec.get("lora_r", args.lora_r))
    args.lora_alpha = int(spec.get("lora_alpha", args.lora_alpha))
    args.warm_head = False
    model, processor, _, _, _ = build_model(args)
    set_peft_model_state_dict(model.backbone, payload["adapters"])
    model.head.load_state_dict(payload["head"])
    dest = Path(args.report_dir) if args.report_dir else ckpt_path.parent / "heldout_eval"
    dest.mkdir(parents=True, exist_ok=True)
    kw = loader_kwargs(processor, args.device, 0)
    evals = {}
    for split in ("val", "test_prospective", "test_external"):
        loader = DataLoader(
            ImageBagDataset(split, max_frames=args.max_frames, expand=args.expand, seed=args.seed),
            batch_size=args.batch_size,
            shuffle=False,
            **kw,
        )
        metrics = evaluate(model, loader, args.device)
        write_predictions(dest, split, metrics.pop("predictions"))
        evals[split] = metrics
    best = {"epoch": int(payload.get("epoch") or 0), "val_acc": float((payload.get("val") or {}).get("acc") or 0)}
    (dest / "metrics.json").write_text(json.dumps(jsonable({"best": best, "spec": spec, "eval": evals}), indent=2), encoding="utf-8")
    write_compare(dest, best, evals)
    print(f"report={dest}", flush=True)
    return {"report": str(dest), "acc": {k: float(v["acc"]) for k, v in evals.items()}}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval", action="store_true", help="Score --ckpt instead of training.")
    parser.add_argument("--ckpt", default="")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--max-frames", type=int, default=6)
    parser.add_argument("--last-n", type=int, default=2)
    parser.add_argument("--lora-r", type=int, default=8)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--encoder-lr", type=float, default=5e-6)
    parser.add_argument("--head-lr", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=2e-4)
    parser.add_argument("--warmup-epochs", type=int, default=3)
    parser.add_argument("--freeze-head-epochs", type=int, default=3)
    parser.add_argument("--patience", type=int, default=12)
    parser.add_argument("--label-smoothing", type=float, default=0.05)
    parser.add_argument("--ordinal-weight", type=float, default=0.5)
    parser.add_argument("--expand", type=float, default=ROI_EXPAND)
    parser.add_argument("--lock", default="acc")
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--warm-head", action="store_true", default=True)
    parser.add_argument("--no-warm-head", action="store_false", dest="warm_head")
    parser.add_argument("--warm-ckpt", default="")
    parser.add_argument("--report-dir", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.eval:
        if not args.ckpt:
            raise SystemExit("--eval needs --ckpt")
        print("eval", eval_ckpt(args), flush=True)
        return 0
    print("train", {k: v["acc"] for k, v in train(args)["eval"].items()}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
