"""LoRA last vision blocks on BM bags. Full paints the mask; ROI is official crop_roi."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from peft import get_peft_model_state_dict, set_peft_model_state_dict
from PIL import Image
from torch.optim.lr_scheduler import LambdaLR
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModel, AutoProcessor

from .constants import BM_CACHE_DIR, BM_LORA_REPORT_DIR, EMBED_DIM, MAIN_ROOT, WEIGHT_DIR
from .encode import assert_weights
from .metrics import score_binary
from .model import GastricUSFromScratch
from .preprocess import load_lora_views
from .train import _cosine_warmup, _select_frame_idx
from .unfreeze import DualViewLoRA, make_collate, wrap_lora


def _abs(rel: object) -> Path:
    path = Path(str(rel or ""))
    if not str(path):
        return path
    return path if path.is_absolute() else MAIN_ROOT / path


class BmImageBagDataset(Dataset):
    def __init__(
        self,
        split: str,
        cache_dir: Path,
        max_frames: int = 4,
        expand: float = 0.20,
        seed: int = 20260826,
    ) -> None:
        table = pd.read_csv(cache_dir / f"{split}_resolved.csv")
        bags: dict[str, dict[str, list]] = defaultdict(
            lambda: {"crop": [], "mask": [], "fallback": [], "clinical": [], "label": [], "source": [], "area": []}
        )
        for _, row in table.iterrows():
            pid = str(row["patient_id"])
            bags[pid]["crop"].append(str(row["crop_ui_path"]))
            bags[pid]["mask"].append(str(row.get("mask_path") or ""))
            bags[pid]["fallback"].append(str(row.get("roi_fallback_path") or ""))
            bags[pid]["clinical"].append(json.loads(row["clinical"]))
            bags[pid]["label"].append(int(row["label"]))
            bags[pid]["source"].append(str(row.get("source") or ""))
            bags[pid]["area"].append(float(row.get("has_mask") or 0))
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
        keep = _select_frame_idx(len(bag["crop"]), self.max_frames, "area", pid, bag["area"], self.seed)
        fulls: list[Image.Image] = []
        rois: list[Image.Image] = []
        for i in keep:
            full, roi = load_lora_views(
                _abs(bag["crop"][i]),
                _abs(bag["mask"][i]) if bag["mask"][i] else None,
                expand=self.expand,
                official_roi=_abs(bag["fallback"][i]) if bag["fallback"][i] else None,
            )
            fulls.append(full)
            rois.append(roi)
        clinical = np.mean([bag["clinical"][i] for i in keep], axis=0)
        labels = [bag["label"][i] for i in keep]
        return {
            "full": fulls,
            "roi": rois,
            "clinical": torch.from_numpy(np.asarray(clinical, dtype=np.float32)),
            "label": torch.tensor(int(max(set(labels), key=labels.count)), dtype=torch.long),
            "n": torch.tensor(len(keep), dtype=torch.long),
            "patient_id": pid,
            "source": Counter(bag["source"]).most_common(1)[0][0] if bag["source"] else "",
        }


@torch.no_grad()
def evaluate_bm(model: DualViewLoRA, loader: DataLoader, device: str, clinical_dim: int) -> dict[str, object]:
    model.eval()
    ys, preds, logits, pids, sources = [], [], [], [], []
    for batch in loader:
        with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=device.startswith("cuda")):
            out = model(
                batch["pixel_full"].to(device),
                batch["pixel_roi"].to(device),
                batch["valid"].to(device),
                batch["clinical"].to(device),
            )
        prob = torch.softmax(out.float(), dim=-1)[:, 1]
        pred = out.argmax(dim=-1)
        ys.append(batch["label"].numpy())
        preds.append(pred.cpu().numpy())
        logits.append(prob.cpu().numpy())
        pids.extend(batch["patient_id"])
        sources.extend(batch["source"])
    y = np.concatenate(ys)
    pred = np.concatenate(preds)
    logit = np.concatenate(logits)
    metrics = score_binary(y, pred, logit)
    metrics["predictions"] = [
        {
            "patient_id": str(pids[i]),
            "source": str(sources[i]),
            "y": int(y[i]),
            "pred": int(pred[i]),
            "p_malignant": float(logit[i]),
        }
        for i in range(len(y))
    ]
    return metrics


def train_unfreeze_bm(
    device: str = "cuda:0",
    epochs: int = 20,
    max_frames: int = 4,
    last_n: int = 2,
    lora_r: int = 8,
    lora_alpha: int = 16,
    encoder_lr: float = 5e-6,
    head_lr: float = 1e-4,
    expand: float = 0.20,
    warmup_epochs: int = 3,
    patience: int = 8,
    freeze_head_epochs: int = 3,
    seed: int = 20260826,
    cache_dir: Path | None = None,
    report_dir: Path | None = None,
) -> dict[str, object]:
    torch.manual_seed(seed)
    np.random.seed(seed)
    assert_weights()
    cache_dir = cache_dir or BM_CACHE_DIR
    tag = f"lora{last_n}_r{lora_r}_official_roi"
    report_dir = report_dir or (BM_LORA_REPORT_DIR / tag)
    report_dir.mkdir(parents=True, exist_ok=True)

    processor = AutoProcessor.from_pretrained(str(WEIGHT_DIR), local_files_only=True)
    backbone = AutoModel.from_pretrained(str(WEIGHT_DIR), local_files_only=True)
    backbone, targets, n_layers = wrap_lora(backbone, last_n=last_n, rank=lora_r, alpha=lora_alpha)
    train_ds = BmImageBagDataset("train", cache_dir, max_frames=max_frames, expand=expand, seed=seed)
    val_ds = BmImageBagDataset("val", cache_dir, max_frames=max_frames, expand=expand, seed=seed)
    clinical_dim = int(train_ds[0]["clinical"].numel())
    head = GastricUSFromScratch(
        clinical_dim=clinical_dim,
        fusion="concat",
        pool="gated",
        size="xlarge",
        n_classes=2,
    )
    model = DualViewLoRA(backbone, head).to(device)
    collate = make_collate(processor)
    train_loader = DataLoader(train_ds, batch_size=1, shuffle=True, collate_fn=collate, num_workers=0)
    loaders = {
        "train": train_loader,
        "val": DataLoader(val_ds, batch_size=1, shuffle=False, collate_fn=collate, num_workers=0),
        "test_prospective": DataLoader(
            BmImageBagDataset("test_prospective", cache_dir, max_frames=max_frames, expand=expand, seed=seed),
            batch_size=1,
            shuffle=False,
            collate_fn=collate,
            num_workers=0,
        ),
        "test_external": DataLoader(
            BmImageBagDataset("test_external", cache_dir, max_frames=max_frames, expand=expand, seed=seed),
            batch_size=1,
            shuffle=False,
            collate_fn=collate,
            num_workers=0,
        ),
    }
    counts = np.bincount(np.asarray(train_ds.labels()), minlength=2).astype(np.float64)
    weights = torch.tensor(counts.sum() / np.clip(counts, 1, None), dtype=torch.float32, device=device)
    weights = weights / weights.mean()
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights)
    opt = torch.optim.AdamW(
        [
            {"params": [p for p in model.backbone.parameters() if p.requires_grad], "lr": encoder_lr},
            {"params": model.head.parameters(), "lr": head_lr},
        ],
        weight_decay=2e-4,
    )
    scheduler = LambdaLR(opt, lambda epoch: _cosine_warmup(epoch, epochs, warmup_epochs))
    spec = {
        "task": "binary_benign_malignant",
        "backbone": "google/medsiglip-448",
        "weight_dir": str(WEIGHT_DIR),
        "views": "full_polygon + official_crop_roi",
        "last_n": last_n,
        "lora_r": lora_r,
        "lora_alpha": lora_alpha,
        "encoder_lr": encoder_lr,
        "head_lr": head_lr,
        "max_frames": max_frames,
        "expand": expand,
        "clinical_dim": clinical_dim,
        "n_vision_layers": n_layers,
        "lora_targets": targets,
        "freeze_head_epochs": freeze_head_epochs,
        "embed_dim": EMBED_DIM,
    }
    (report_dir / "spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    print(
        f"bm-lora MedSigLIP-448 {tag} patients={len(train_ds)} "
        f"clinical_dim={clinical_dim} last_n={last_n} layers={n_layers}",
        flush=True,
    )

    best = {"auc": -1.0, "epoch": 0}
    history = []
    ckpt = report_dir / "best_adapters.pt"
    stale = 0
    for epoch in range(1, epochs + 1):
        freeze_head = epoch <= int(freeze_head_epochs)
        for param in model.head.parameters():
            param.requires_grad = not freeze_head
        model.train()
        running = 0.0
        seen = 0
        for step, batch in enumerate(loaders["train"], 1):
            opt.zero_grad(set_to_none=True)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=device.startswith("cuda")):
                logits = model(
                    batch["pixel_full"].to(device),
                    batch["pixel_roi"].to(device),
                    batch["valid"].to(device),
                    batch["clinical"].to(device),
                )
                loss = loss_fn(logits, batch["label"].to(device))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            running += float(loss.item())
            seen += 1
            if step % 100 == 0 or step == len(train_ds):
                print(f"  epoch {epoch} {step}/{len(train_ds)} loss={running / seen:.4f}", flush=True)
        scheduler.step()
        val = evaluate_bm(model, loaders["val"], device, clinical_dim)
        slim = {k: val[k] for k in ("n", "acc", "auc", "recall_pos", "recall_neg", "balanced_acc")}
        row = {"epoch": epoch, "train_loss": running / max(seen, 1), "val": slim}
        history.append(row)
        print(json.dumps({"epoch": epoch, "train_loss": row["train_loss"], **{f"val_{k}": slim[k] for k in slim}}), flush=True)
        if float(slim["auc"]) > best["auc"]:
            best = {"auc": float(slim["auc"]), "acc": float(slim["acc"]), "epoch": epoch, "val": slim}
            torch.save(
                {
                    "adapters": get_peft_model_state_dict(model.backbone),
                    "head": model.head.state_dict(),
                    "epoch": epoch,
                    "val": slim,
                    "spec": spec,
                },
                ckpt,
            )
            stale = 0
        else:
            stale += 1
            if stale >= patience:
                print(f"early stop at epoch {epoch}, best={best['epoch']}", flush=True)
                break

    saved = torch.load(ckpt, map_location=device, weights_only=False)
    set_peft_model_state_dict(model.backbone, saved["adapters"])
    model.head.load_state_dict(saved["head"])
    evals = {}
    for name, loader in loaders.items():
        if name == "train":
            continue
        metrics = evaluate_bm(model, loader, device, clinical_dim)
        rows = metrics.pop("predictions")
        evals[name] = metrics
        with (report_dir / f"{name}_predictions.csv").open("w", encoding="utf-8") as handle:
            handle.write("patient_id,source,y,pred,p_malignant\n")
            for rec in rows:
                handle.write(
                    f"{rec['patient_id']},{rec['source']},{rec['y']},{rec['pred']},{rec['p_malignant']:.6f}\n"
                )
    payload = {"best": best, "eval": evals, "history": history, "spec": spec}
    (report_dir / "metrics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (report_dir / "COMPARE.md").write_text(
        "\n".join(
            [
                "# GastricUS BM LoRA (mask polygon + official crop_roi)",
                "",
                f"Lock epoch {best['epoch']}, val AUC {best['auc']:.4f}, acc {best.get('acc', 0):.4f}.",
                "",
                "| split | n | AUC | Acc | Sens | Spec |",
                "|-------|--:|----:|----:|-----:|-----:|",
                *[
                    f"| {name} | {row['n']} | {row['auc']:.4f} | {row['acc']:.4f} | {row['recall_pos']:.4f} | {row['recall_neg']:.4f} |"
                    for name, row in evals.items()
                ],
                "",
                "Full view paints the lesion polygon on crop_ui. ROI is the official crop_roi image, with crop_roi/roi_masks painted when present.",
                "Do not recompute an expand-box ROI when official crop_roi exists. LoRA last 2 vision blocks. Do not promote Assist until unseen-center numbers are in.",
            ]
        ),
        encoding="utf-8",
    )
    return payload
