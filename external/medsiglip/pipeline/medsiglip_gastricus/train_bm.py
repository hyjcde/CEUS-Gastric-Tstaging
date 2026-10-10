"""GastricUS BM head: frozen embeddings + clinical-11 + BM-sign5 -> 2-class."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from .constants import BM_CACHE_DIR, BM_REPORT_DIR, SPLIT_FILES
from .metrics import score_binary
from .model import GastricUSFromScratch
from .train import PatientBagDataset, collate


def _predict(model, loader, device: str) -> dict[str, np.ndarray]:
    ys, preds, logits, pids, sources = [], [], [], [], []
    model.eval()
    with torch.no_grad():
        for batch in loader:
            out = model(
                batch["e_full"].to(device),
                batch["e_roi"].to(device),
                batch["valid"].to(device),
                batch["clinical"].to(device),
            )
            logit = out["logits"] if isinstance(out, dict) else out
            prob = torch.softmax(logit.float(), dim=-1)[:, 1]
            pred = logit.argmax(dim=-1)
            ys.append(batch["label"].numpy())
            preds.append(pred.cpu().numpy())
            logits.append(prob.cpu().numpy())
            pids.extend(batch["patient_id"])
            sources.extend(batch["source"])
    return {
        "y": np.concatenate(ys),
        "pred": np.concatenate(preds),
        "logit": np.concatenate(logits),
        "patient_id": np.asarray(pids),
        "source": np.asarray(sources),
    }


def _write_eval(report_dir: Path, name: str, pred: dict[str, np.ndarray], metrics: dict) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    pd_rows = [
        {
            "patient_id": str(pred["patient_id"][i]),
            "source": str(pred["source"][i]),
            "y": int(pred["y"][i]),
            "pred": int(pred["pred"][i]),
            "p_malignant": float(pred["logit"][i]),
        }
        for i in range(len(pred["y"]))
    ]
    import csv

    with (report_dir / f"{name}_predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(pd_rows[0]))
        writer.writeheader()
        writer.writerows(pd_rows)
    (report_dir / f"{name}_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")


def train_bm(
    device: str = "cuda:0",
    epochs: int = 60,
    batch_size: int = 16,
    lr: float = 2e-4,
    cache_dir: Path | None = None,
    report_dir: Path | None = None,
    fusion: str = "concat",
    pool: str = "gated",
    size: str = "xlarge",
    seed: int = 20260825,
) -> dict[str, object]:
    cache_dir = cache_dir or BM_CACHE_DIR
    report_dir = report_dir or (BM_REPORT_DIR / f"{fusion}_{pool}_{size}")
    report_dir.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(seed)
    np.random.seed(seed)

    loaders = {}
    clinical_dim = None
    for split in SPLIT_FILES:
        npz = cache_dir / f"{split}_embeddings.npz"
        if not npz.is_file():
            raise FileNotFoundError(npz)
        data = PatientBagDataset(npz)
        if clinical_dim is None:
            clinical_dim = int(data[0]["clinical"].numel())
        loaders[split] = DataLoader(
            data,
            batch_size=batch_size,
            shuffle=split == "train",
            collate_fn=collate,
            num_workers=0,
        )

    model = GastricUSFromScratch(
        clinical_dim=clinical_dim,
        fusion=fusion,
        pool=pool,
        size=size,
        n_classes=2,
    ).to(device)
    labels = loaders["train"].dataset.labels()
    counts = np.bincount(np.asarray(labels), minlength=2).astype(np.float64)
    weights = counts.sum() / np.clip(counts, 1, None)
    weights = torch.tensor(weights / weights.mean(), dtype=torch.float32, device=device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    best = {"auc": -1.0, "epoch": 0}
    history = []
    for epoch in range(1, epochs + 1):
        model.train()
        losses = []
        for batch in loaders["train"]:
            opt.zero_grad(set_to_none=True)
            out = model(
                batch["e_full"].to(device),
                batch["e_roi"].to(device),
                batch["valid"].to(device),
                batch["clinical"].to(device),
            )
            logit = out["logits"] if isinstance(out, dict) else out
            loss = torch.nn.functional.cross_entropy(logit, batch["label"].to(device), weight=weights)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            losses.append(float(loss.detach().cpu()))
        val_pred = _predict(model, loaders["val"], device)
        val = score_binary(val_pred["y"], val_pred["pred"], val_pred["logit"])
        history.append({"epoch": epoch, "train_loss": float(np.mean(losses)), "val": val})
        print(f"bm epoch {epoch} loss={np.mean(losses):.4f} val_auc={val['auc']:.4f} acc={val['acc']:.4f}", flush=True)
        if val["auc"] > best["auc"]:
            best = {"auc": val["auc"], "acc": val["acc"], "epoch": epoch, "val": val}
            torch.save({"model": model.state_dict(), "clinical_dim": clinical_dim, "epoch": epoch}, report_dir / "best_model.pt")
    ckpt = torch.load(report_dir / "best_model.pt", map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model"])
    evals = {}
    for split, loader in loaders.items():
        pred = _predict(model, loader, device)
        metrics = score_binary(pred["y"], pred["pred"], pred["logit"])
        evals[split] = metrics
        _write_eval(report_dir, split, pred, metrics)
    payload = {
        "best": best,
        "eval": evals,
        "history": history,
        "clinical_dim": clinical_dim,
        "fusion": fusion,
        "pool": pool,
        "size": size,
        "cache": str(cache_dir),
    }
    (report_dir / "metrics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (report_dir.parent / "COMPARE.md").write_text(
        "\n".join(
            [
                "# GastricUS BM",
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
                "Clinical vector is clinical-11 (22) plus BM-sign5 (10). Ulcer / wall are missing unless a report text had them.",
            ]
        ),
        encoding="utf-8",
    )
    return payload
