"""T-staging LoRA on last MedSigLIP vision blocks. Full paints the mask; ROI is official crop_roi."""

from __future__ import annotations

import json
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

from .constants import (
    CLASS_NAMES,
    DATASET_DIR,
    DEFAULT_FOURCLASS_CKPT,
    EMBED_DIM,
    N_CLASSES,
    PLAN_COMPLETE_REPORT_DIR,
    ROOT,
    SPLIT_FILES,
    TSTAGING_LORA_REPORT_DIR,
    WEIGHT_DIR,
)
from .encode import assert_weights
from .preprocess import load_lora_views, official_roi_from_crop_ui
from .metrics import center_of
from .model import GastricUSFromScratch
from .train import (
    _clinical_batch,
    _cosine_warmup,
    _is_better,
    _jsonable,
    _select_frame_idx,
    _write_summary,
    ordinal_rank_loss,
)


def _abs(path: object) -> Path:
    value = Path(str(path))
    return value if value.is_absolute() else ROOT / value


class ImageBagDataset(Dataset):
    def __init__(
        self,
        split: str,
        max_frames: int = 6,
        expand: float = 0.20,
        frame_sample: str = "prefix",
        seed: int = 20260821,
    ) -> None:
        table = pd.read_csv(DATASET_DIR / SPLIT_FILES[split])
        usable = table[(table["crop_ui_path"] != "") & (table["mask_path"] != "")].reset_index(drop=True)
        bags: dict[str, dict[str, list]] = defaultdict(
            lambda: {"crop": [], "mask": [], "roi": [], "clinical": [], "label": [], "source": [], "area": []}
        )
        for _, row in usable.iterrows():
            pid = str(row["patient_id"])
            crop = str(row["crop_ui_path"])
            bags[pid]["crop"].append(crop)
            bags[pid]["mask"].append(str(row["mask_path"]))
            official = official_roi_from_crop_ui(_abs(crop))
            bags[pid]["roi"].append(str(official) if official is not None else "")
            bags[pid]["clinical"].append(json.loads(row["clinical_22"]))
            bags[pid]["label"].append(int(row["label"]))
            bags[pid]["source"].append(str(row["source"]))
            bags[pid]["area"].append(0.0)
        self.bags = bags
        self.pids = sorted(bags)
        self.max_frames = max_frames
        self.expand = expand
        self.frame_sample = frame_sample
        self.seed = seed

    def __len__(self) -> int:
        return len(self.pids)

    def labels(self) -> list[int]:
        out = []
        for pid in self.pids:
            ys = self.bags[pid]["label"]
            out.append(int(max(set(ys), key=ys.count)))
        return out

    def __getitem__(self, idx: int) -> dict[str, object]:
        pid = self.pids[idx]
        bag = self.bags[pid]
        keep = _select_frame_idx(len(bag["crop"]), self.max_frames, self.frame_sample, pid, bag["area"], self.seed)
        fulls: list[Image.Image] = []
        rois: list[Image.Image] = []
        for i in keep:
            full, roi = load_lora_views(
                _abs(bag["crop"][i]),
                _abs(bag["mask"][i]) if bag["mask"][i] else None,
                expand=self.expand,
                official_roi=_abs(bag["roi"][i]) if bag["roi"][i] else None,
            )
            fulls.append(full)
            rois.append(roi)
        clinical = np.mean([bag["clinical"][i] for i in keep], axis=0)
        labels = [bag["label"][i] for i in keep]
        label = int(max(set(labels), key=labels.count))
        source = Counter(bag["source"]).most_common(1)[0][0]
        return {
            "full": fulls,
            "roi": rois,
            "clinical": torch.from_numpy(np.asarray(clinical, dtype=np.float32)),
            "label": torch.tensor(label, dtype=torch.long),
            "n": torch.tensor(len(keep), dtype=torch.long),
            "patient_id": pid,
            "source": source,
        }


def make_collate(processor):
    def collate(batch: list[dict[str, object]]) -> dict[str, object]:
        max_t = max(int(item["n"]) for item in batch)
        images: list[Image.Image] = []
        index: list[tuple[int, int, str]] = []
        for b, item in enumerate(batch):
            n = int(item["n"])
            for t in range(n):
                images.append(item["full"][t])
                index.append((b, t, "full"))
                images.append(item["roi"][t])
                index.append((b, t, "roi"))
        pixels = processor(images=images, return_tensors="pt")["pixel_values"]
        bsz = len(batch)
        pixel_full = torch.zeros(bsz, max_t, *pixels.shape[1:])
        pixel_roi = torch.zeros(bsz, max_t, *pixels.shape[1:])
        valid = torch.zeros(bsz, max_t, dtype=torch.bool)
        cursor = 0
        for b, t, view in index:
            if view == "full":
                pixel_full[b, t] = pixels[cursor]
            else:
                pixel_roi[b, t] = pixels[cursor]
                valid[b, t] = True
            cursor += 1
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
    config = LoraConfig(r=rank, lora_alpha=alpha, target_modules=targets, bias="none")
    wrapped = get_peft_model(backbone, config)
    vision = wrapped.get_base_model().vision_model if hasattr(wrapped, "get_base_model") else wrapped.vision_model
    def _keep_grad(_module, _inp, output):
        if torch.is_tensor(output):
            output.requires_grad_(True)
        return output

    vision.embeddings.patch_embedding.register_forward_hook(_keep_grad)
    if hasattr(wrapped, "gradient_checkpointing_enable"):
        wrapped.gradient_checkpointing_enable()
    elif hasattr(vision.encoder, "gradient_checkpointing"):
        vision.encoder.gradient_checkpointing = True
    return wrapped, targets, n_layers


def wrap_full_last_n(backbone, last_n: int):
    """Unfreeze the last N vision encoder layers and the pooling head. No LoRA."""
    for param in backbone.parameters():
        param.requires_grad = False
    n_layers = len(backbone.vision_model.encoder.layers)
    start = max(0, n_layers - last_n)
    names = []
    for i in range(start, n_layers):
        for param in backbone.vision_model.encoder.layers[i].parameters():
            param.requires_grad = True
        names.append(f"vision_model.encoder.layers.{i}")
    for module in (backbone.vision_model.post_layernorm, backbone.vision_model.head):
        for param in module.parameters():
            param.requires_grad = True
        names.append(module.__class__.__name__)
    vision = backbone.vision_model

    def _keep_grad(_module, _inp, output):
        if torch.is_tensor(output):
            output.requires_grad_(True)
        return output

    vision.embeddings.patch_embedding.register_forward_hook(_keep_grad)
    if hasattr(backbone, "gradient_checkpointing_enable"):
        backbone.gradient_checkpointing_enable()
    elif hasattr(vision.encoder, "gradient_checkpointing"):
        vision.encoder.gradient_checkpointing = True
    return backbone, names, n_layers


@torch.no_grad()
def evaluate_images(model: DualViewLoRA, loader: DataLoader, device: str, clinical_dim: int = 22) -> dict[str, object]:
    model.eval()
    ys: list[int] = []
    preds: list[int] = []
    sources: list[str] = []
    pids: list[str] = []
    for batch in loader:
        with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=device.startswith("cuda")):
            logits = model(
                batch["pixel_full"].to(device),
                batch["pixel_roi"].to(device),
                batch["valid"].to(device),
                _clinical_batch(batch, device, clinical_dim),
            )
        pred = logits.argmax(dim=-1).cpu().numpy().astype(int)
        y = batch["label"].cpu().numpy().astype(int)
        ys.extend(y.tolist())
        preds.extend(pred.tolist())
        sources.extend(batch["source"])
        pids.extend(batch["patient_id"])
    from .metrics import confusion, per_center, score_arrays

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


def train_unfreeze(
    device: str = "cuda:0",
    epochs: int = 40,
    max_frames: int = 6,
    last_n: int = 4,
    mode: str = "lora",
    lora_r: int = 16,
    lora_alpha: int = 32,
    encoder_lr: float = 2e-5,
    head_lr: float = 2e-4,
    weight_decay: float = 2e-4,
    expand: float = 0.20,
    warmup_epochs: int = 3,
    patience: int = 12,
    label_smoothing: float = 0.05,
    grad_clip: float = 1.0,
    lock: str = "acc",
    ordinal_weight: float = 0.5,
    seed: int = 20260821,
    report_dir: Path | None = None,
    warm_head: bool = False,
    warm_ckpt: Path | None = None,
    freeze_head_epochs: int = 0,
    batch_size: int = 4,
    num_workers: int = 4,
) -> dict[str, object]:
    torch.manual_seed(seed)
    np.random.seed(seed)
    assert_weights()
    if mode not in {"lora", "full"}:
        raise ValueError(mode)
    head_tag = "warmhead" if warm_head else "concat_gated"
    if int(freeze_head_epochs) > 0:
        head_tag = f"{head_tag}_freezehead{int(freeze_head_epochs)}"
    tag = (
        f"full{last_n}_{head_tag}"
        if mode == "full"
        else f"lora{last_n}_r{lora_r}_{head_tag}_officialroi"
    )
    report_dir = report_dir or (TSTAGING_LORA_REPORT_DIR / tag)
    report_dir.mkdir(parents=True, exist_ok=True)
    processor = AutoProcessor.from_pretrained(str(WEIGHT_DIR), local_files_only=True)
    backbone = AutoModel.from_pretrained(str(WEIGHT_DIR), local_files_only=True)
    if mode == "full":
        backbone, targets, n_layers = wrap_full_last_n(backbone, last_n=last_n)
    else:
        backbone, targets, n_layers = wrap_lora(backbone, last_n=last_n, rank=lora_r, alpha=lora_alpha)
    head = GastricUSFromScratch(
        clinical_dim=22,
        fusion="concat",
        pool="gated",
        size="xlarge",
        pool_proj=False,
        residual=True,
    )
    if warm_head:
        ckpt_path = Path(warm_ckpt) if warm_ckpt else DEFAULT_FOURCLASS_CKPT
        if not ckpt_path.is_file():
            alt = PLAN_COMPLETE_REPORT_DIR / "mlp_concat_gated" / "best_model.pt"
            if alt.is_file():
                ckpt_path = alt
        payload = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        missing, unexpected = head.load_state_dict(payload["model"], strict=True)
        print(f"warm_head {ckpt_path} missing={list(missing)} unexpected={list(unexpected)}", flush=True)
    model = DualViewLoRA(backbone, head).to(device)
    train_ds = ImageBagDataset("train", max_frames=max_frames, expand=expand, seed=seed)
    val_ds = ImageBagDataset("val", max_frames=max_frames, expand=expand, seed=seed)
    collate = make_collate(processor)
    loader_kw = {"collate_fn": collate, "num_workers": int(num_workers), "pin_memory": device.startswith("cuda")}
    if int(num_workers) > 0:
        loader_kw["persistent_workers"] = True
        loader_kw["prefetch_factor"] = 2
    train_loader = DataLoader(train_ds, batch_size=max(int(batch_size), 1), shuffle=True, **loader_kw)
    val_loader = DataLoader(val_ds, batch_size=max(int(batch_size), 1), shuffle=False, **loader_kw)
    extra = {}
    for split in ("test_prospective", "test_external"):
        extra[split] = DataLoader(
            ImageBagDataset(split, max_frames=max_frames, expand=expand, seed=seed),
            batch_size=max(int(batch_size), 1),
            shuffle=False,
            **loader_kw,
        )
    counts = Counter(train_ds.labels())
    weights = [len(train_ds) / (N_CLASSES * max(counts.get(i, 1), 1)) for i in range(N_CLASSES)]
    loss_fn = torch.nn.CrossEntropyLoss(
        weight=torch.tensor(weights, dtype=torch.float32, device=device),
        label_smoothing=label_smoothing,
    )
    opt = torch.optim.AdamW(
        [
            {"params": [p for p in model.backbone.parameters() if p.requires_grad], "lr": encoder_lr},
            {"params": model.head.parameters(), "lr": head_lr},
        ],
        weight_decay=weight_decay,
    )
    scheduler = LambdaLR(opt, lambda epoch: _cosine_warmup(epoch, epochs, warmup_epochs))
    n_trainable = int(sum(p.numel() for p in model.parameters() if p.requires_grad))
    spec = {
        "name": tag,
        "warm_head": warm_head,
        "warm_ckpt": str(warm_ckpt or DEFAULT_FOURCLASS_CKPT) if warm_head else "",
        "fusion": "concat",
        "pool": "gated",
        "head": "mlp_full" if mode == "full" else "mlp_lora",
        "mode": mode,
        "size": "xlarge",
        "n_params": n_trainable,
        "class_weight": "balanced",
        "clinical": "raw",
        "pool_proj": False,
        "ordinal_weight": ordinal_weight,
        "lock": lock,
        "last_n": last_n,
        "lora_r": lora_r,
        "lora_alpha": lora_alpha,
        "encoder_lr": encoder_lr,
        "head_lr": head_lr,
        "max_frames": max_frames,
        "expand": expand,
        "n_vision_layers": n_layers,
        "lora_targets": targets,
        "freeze_head_epochs": freeze_head_epochs,
        "views": "full_polygon + official_crop_roi",
        "task": "t_staging_4class",
        "batch_size": int(batch_size),
        "num_workers": int(num_workers),
    }
    (report_dir / "spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(
        f"unfreeze {spec['name']} trainable={n_trainable} last_n={last_n} "
        f"frames={max_frames} batch={batch_size} workers={num_workers}",
        flush=True,
    )
    best = {"val_adj_acc": -1.0, "val_acc": -1.0, "val_qwk": -1.0, "val_macro_recall": -1.0}
    history = []
    ckpt = report_dir / "best_adapters.pt"
    stale = 0
    log_path = report_dir / "train.log"
    for epoch in range(1, epochs + 1):
        freeze_head = epoch <= int(freeze_head_epochs)
        for param in model.head.parameters():
            param.requires_grad = not freeze_head
        model.train()
        running = 0.0
        seen = 0
        n_steps = len(train_loader)
        for step, batch in enumerate(train_loader, 1):
            opt.zero_grad(set_to_none=True)
            labels_b = batch["label"].to(device)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=device.startswith("cuda")):
                logits = model(
                    batch["pixel_full"].to(device),
                    batch["pixel_roi"].to(device),
                    batch["valid"].to(device),
                    _clinical_batch(batch, device, 22),
                )
                loss = loss_fn(logits, labels_b)
                if ordinal_weight > 0:
                    loss = loss + ordinal_weight * ordinal_rank_loss(logits, labels_b)
            loss.backward()
            if grad_clip > 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
            opt.step()
            running += float(loss.item())
            seen += 1
            if step % 20 == 0 or step == n_steps:
                print(f"  epoch {epoch} {step}/{n_steps} loss={running / seen:.4f}", flush=True)
        scheduler.step()
        val_metrics = evaluate_images(model, val_loader, device, clinical_dim=22)
        slim = {
            k: val_metrics[k]
            for k in ("n", "acc", "adj_acc", "off2", "qwk", "serosa_acc", "macro_recall", "t2_recall", "recall_T3")
        }
        row = {
            "epoch": epoch,
            "train_loss": running / max(seen, 1),
            "lr_encoder": float(scheduler.get_last_lr()[0]) * 0 + float(opt.param_groups[0]["lr"]),
            "lr_head": float(opt.param_groups[1]["lr"]),
            **{f"val_{k}": v for k, v in slim.items()},
        }
        history.append(row)
        line = json.dumps({k: (float(v) if isinstance(v, (float, np.floating)) else v) for k, v in row.items()})
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        if _is_better(val_metrics, best, lock):
            best = {
                "val_adj_acc": float(val_metrics["adj_acc"]),
                "val_acc": float(val_metrics["acc"]),
                "val_qwk": float(val_metrics["qwk"]),
                "val_macro_recall": float(val_metrics["macro_recall"]),
                "epoch": epoch,
                "val": slim,
            }
            payload = {
                "head": model.head.state_dict(),
                "epoch": epoch,
                "val": slim,
                "spec": spec,
                "mode": mode,
            }
            if mode == "full":
                trainable_names = {n for n, p in model.backbone.named_parameters() if p.requires_grad}
                payload["backbone"] = {
                    k: v.detach().cpu() for k, v in model.backbone.state_dict().items() if k in trainable_names
                }
            else:
                payload["adapters"] = get_peft_model_state_dict(model.backbone)
            torch.save(payload, ckpt)
            stale = 0
        else:
            stale += 1
            if stale >= patience:
                print(f"early stop at epoch {epoch}, best={best['epoch']}", flush=True)
                break
    saved = torch.load(ckpt, map_location=device, weights_only=False)
    if mode == "full":
        model.backbone.load_state_dict(saved["backbone"], strict=False)
    else:
        set_peft_model_state_dict(model.backbone, saved["adapters"])
    model.head.load_state_dict(saved["head"])
    final = {
        "best": best,
        "history": history,
        "eval": {"val": evaluate_images(model, val_loader, device)},
        "spec": spec,
    }
    for split, loader in extra.items():
        final["eval"][split] = evaluate_images(model, loader, device)
    for split, metrics in final["eval"].items():
        rows = metrics.pop("predictions")
        (report_dir / f"{split}_predictions.csv").write_text(
            "split,center,patient_id,y,pred,T_true,T_pred,adjacent\n"
            + "".join(
                f"{split},{center_of(r['source'])},{r['patient_id']},{r['y']},{r['pred']},"
                f"{CLASS_NAMES[r['y']]},{CLASS_NAMES[r['pred']]},{int(abs(r['y']-r['pred'])<=1)}\n"
                for r in rows
            ),
            encoding="utf-8",
        )
    (report_dir / "metrics.json").write_text(json.dumps(_jsonable(final), indent=2), encoding="utf-8")
    _write_summary(report_dir, spec, best, final["eval"])
    return final


def eval_unfreeze(
    ckpt_path: Path,
    device: str = "cuda:0",
    max_frames: int = 6,
    expand: float = 0.20,
    report_dir: Path | None = None,
) -> dict[str, object]:
    """Score a saved LoRA/full checkpoint on val, prospective, and external."""
    assert_weights()
    payload = torch.load(Path(ckpt_path), map_location="cpu", weights_only=False)
    spec = dict(payload.get("spec") or {})
    last_n = int(spec.get("last_n", 4))
    mode = str(payload.get("mode") or spec.get("mode") or "lora")
    processor = AutoProcessor.from_pretrained(str(WEIGHT_DIR), local_files_only=True)
    backbone = AutoModel.from_pretrained(str(WEIGHT_DIR), local_files_only=True)
    if mode == "full":
        backbone, _, _ = wrap_full_last_n(backbone, last_n=last_n)
    else:
        backbone, _, _ = wrap_lora(
            backbone,
            last_n=last_n,
            rank=int(spec.get("lora_r", 16)),
            alpha=int(spec.get("lora_alpha", 32)),
        )
    head = GastricUSFromScratch(
        clinical_dim=22,
        fusion="concat",
        pool="gated",
        size="xlarge",
        pool_proj=False,
        residual=True,
    )
    model = DualViewLoRA(backbone, head).to(device)
    if mode == "full":
        model.backbone.load_state_dict(payload["backbone"], strict=False)
    else:
        set_peft_model_state_dict(model.backbone, payload["adapters"])
    model.head.load_state_dict(payload["head"])
    collate = make_collate(processor)
    evals = {}
    for split in ("val", "test_prospective", "test_external"):
        loader = DataLoader(
            ImageBagDataset(split, max_frames=max_frames, expand=expand),
            batch_size=1,
            shuffle=False,
            collate_fn=collate,
            num_workers=0,
        )
        evals[split] = evaluate_images(model, loader, device)
    dest = Path(report_dir) if report_dir else Path(ckpt_path).parent / "heldout_eval"
    dest.mkdir(parents=True, exist_ok=True)
    best = {"epoch": int(payload.get("epoch") or 0), "val_acc": float((payload.get("val") or {}).get("acc") or 0)}
    spec.setdefault("name", dest.name)
    spec.setdefault("fusion", "concat")
    spec.setdefault("pool", "gated")
    spec.setdefault("head", "eval_unfreeze")
    spec.setdefault("n_params", 0)
    for split, metrics in evals.items():
        rows = metrics.pop("predictions")
        (dest / f"{split}_predictions.csv").write_text(
            "split,center,patient_id,y,pred,T_true,T_pred,adjacent\n"
            + "".join(
                f"{split},{center_of(r['source'])},{r['patient_id']},{r['y']},{r['pred']},"
                f"{CLASS_NAMES[r['y']]},{CLASS_NAMES[r['pred']]},{int(abs(r['y']-r['pred'])<=1)}\n"
                for r in rows
            ),
            encoding="utf-8",
        )
    (dest / "metrics.json").write_text(
        json.dumps(_jsonable({"best": best, "spec": spec, "eval": evals}), indent=2),
        encoding="utf-8",
    )
    _write_summary(dest, spec, best, evals)
    return {"report": str(dest), "acc": {k: float(v["acc"]) for k, v in evals.items()}}
