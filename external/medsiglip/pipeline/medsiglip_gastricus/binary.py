"""Serosa / T3-vs-T4+ binary heads and 4-class cascade on the frozen cache."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from torch.optim.lr_scheduler import LambdaLR
from torch.utils.data import DataLoader

from .constants import (
    BINARY_REPORT_DIR,
    CACHE_DIR,
    CLASS_NAMES,
    DEFAULT_FOURCLASS_CKPT,
    OPT_REPORT_DIR,
    T34_REPORT_DIR,
)
from .metrics import mcnemar_exact, md_confusion, score_arrays, score_binary
from .model import GastricUSFromScratch
from .train import PatientBagDataset, _clinical_batch, _cosine_warmup, _jsonable, collate, confusion

BINARY_RUNS = (
    {"name": "serosa_gated", "task": "serosa", "pool": "gated"},
    {"name": "serosa_mean", "task": "serosa", "pool": "mean_views"},
    {"name": "t34_gated", "task": "t34", "pool": "gated"},
    {"name": "t34_mean", "task": "t34", "pool": "mean_views"},
)


def _loaders(task: str, batch_size: int, max_frames: int) -> dict[str, DataLoader]:
    loaders = {}
    for split_name in ("train", "val", "test_prospective", "test_external"):
        path = CACHE_DIR / f"{split_name}_embeddings.npz"
        if not path.is_file():
            continue
        loaders[split_name] = DataLoader(
            PatientBagDataset(path, max_frames=max_frames, task=task),
            batch_size=batch_size,
            shuffle=split_name == "train",
            collate_fn=collate,
        )
    return loaders


@torch.no_grad()
def _predict(model: torch.nn.Module, loader: DataLoader, device: str, clinical_dim: int) -> dict[str, object]:
    model.eval()
    logits_all: list[torch.Tensor] = []
    ys: list[int] = []
    pids: list[str] = []
    sources: list[str] = []
    for batch in loader:
        logits = model(
            batch["e_full"].to(device),
            batch["e_roi"].to(device),
            batch["valid"].to(device),
            _clinical_batch(batch, device, clinical_dim),
        )
        logits_all.append(logits.detach().cpu())
        ys.extend(batch["label"].cpu().numpy().astype(int).tolist())
        pids.extend(batch["patient_id"])
        sources.extend(batch["source"])
    logits = torch.cat(logits_all, dim=0).numpy()
    pred = logits.argmax(axis=-1).astype(int)
    if logits.shape[1] == 2:
        score = logits[:, 1] - logits[:, 0]
    else:
        score = logits[:, -1]
    return {
        "logit": score,
        "pred": pred,
        "y": np.asarray(ys, dtype=int),
        "patient_id": pids,
        "source": sources,
        "logits": logits,
    }


def _write_binary_summary(report_dir: Path, spec: dict, best: dict, evals: dict[str, dict]) -> None:
    pos_name = "T4+" if spec["task"] == "serosa" else "T4+ (vs T3)"
    lines = [
        f"# MedSigLIP-448 GastricUS {spec['name']}",
        "",
        f"- task: {spec['task']}",
        f"- pool: {spec['pool']}",
        f"- trainable params: {spec.get('n_params', 0)}",
        f"- best val epoch: {best['epoch']} (lock = val acc)",
        f"- positive class: {pos_name}",
        "",
        "| split | n | n_pos | ACC | bal ACC | AUC | rec_pos | rec_neg | prev_true | prev_pred |",
        "|-------|--:|------:|----:|--------:|----:|--------:|--------:|----------:|----------:|",
    ]
    for name, metrics in evals.items():
        lines.append(
            "| {name} | {n} | {np_:.0f} | {acc:.4f} | {bal:.4f} | {auc:.4f} | {rp:.4f} | {rn:.4f} | {pt:.4f} | {pp:.4f} |".format(
                name=name,
                n=int(metrics["n"]),
                np_=metrics["n_pos"],
                acc=float(metrics["acc"]),
                bal=float(metrics["balanced_acc"]),
                auc=float(metrics["auc"]),
                rp=float(metrics["recall_pos"]),
                rn=float(metrics["recall_neg"]),
                pt=float(metrics["prev_true"]),
                pp=float(metrics["prev_pred"]),
            )
        )
    (report_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def train_binary(
    task: str,
    pool: str,
    device: str = "cuda:0",
    epochs: int = 80,
    batch_size: int = 16,
    lr: float = 2e-4,
    weight_decay: float = 2e-4,
    max_frames: int = 16,
    seed: int = 20260821,
    size: str = "xlarge",
    warmup_epochs: int = 8,
    patience: int = 25,
    label_smoothing: float = 0.05,
    grad_clip: float = 1.0,
    clinical: str = "raw",
    report_dir: Path | None = None,
    run_name: str = "",
) -> dict[str, object]:
    if task not in {"serosa", "t34"}:
        raise ValueError(task)
    torch.manual_seed(seed)
    np.random.seed(seed)
    clinical_dim = 0 if clinical == "none" else 22
    name = run_name or f"{task}_{pool}"
    report_dir = Path(report_dir or (BINARY_REPORT_DIR / name))
    report_dir.mkdir(parents=True, exist_ok=True)
    loaders = _loaders(task, batch_size, max_frames)
    model = GastricUSFromScratch(
        clinical_dim=clinical_dim,
        fusion="concat",
        pool=pool,
        size=size,
        pool_proj=False,
        residual=True,
        n_classes=2,
    ).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = LambdaLR(opt, lambda epoch: _cosine_warmup(epoch, epochs, warmup_epochs))
    labels = loaders["train"].dataset.labels()
    counts = Counter(labels)
    weights = [len(labels) / (2 * max(counts.get(i, 1), 1)) for i in range(2)]
    loss_fn = torch.nn.CrossEntropyLoss(
        weight=torch.tensor(weights, dtype=torch.float32, device=device),
        label_smoothing=label_smoothing,
    )
    spec = {
        "name": name,
        "task": task,
        "pool": pool,
        "fusion": "concat",
        "size": size,
        "n_params": model.n_parameters(),
        "clinical": clinical,
        "n_train": len(labels),
        "n_pos_train": int(counts.get(1, 0)),
        "class_weight": weights,
    }
    print(
        f"run {name} params={spec['n_params']} n_train={spec['n_train']} "
        f"pos={spec['n_pos_train']} weights={weights}",
        flush=True,
    )
    best = {"val_acc": -1.0, "val_balanced_acc": -1.0, "epoch": 0}
    history = []
    ckpt = report_dir / "best_model.pt"
    stale = 0
    for epoch in range(1, epochs + 1):
        model.train()
        running = 0.0
        seen = 0
        for batch in loaders["train"]:
            opt.zero_grad(set_to_none=True)
            logits = model(
                batch["e_full"].to(device),
                batch["e_roi"].to(device),
                batch["valid"].to(device),
                _clinical_batch(batch, device, clinical_dim),
            )
            loss = loss_fn(logits, batch["label"].to(device))
            loss.backward()
            if grad_clip > 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
            opt.step()
            running += float(loss.item()) * int(batch["label"].numel())
            seen += int(batch["label"].numel())
        scheduler.step()
        val_pred = _predict(model, loaders["val"], device, clinical_dim)
        val_metrics = score_binary(val_pred["y"], val_pred["pred"], val_pred["logit"])
        row = {
            "epoch": epoch,
            "train_loss": running / max(seen, 1),
            "lr": float(scheduler.get_last_lr()[0]),
            **{f"val_{k}": v for k, v in val_metrics.items()},
        }
        history.append(row)
        print(row, flush=True)
        better = float(val_metrics["acc"]) > float(best["val_acc"]) or (
            float(val_metrics["acc"]) == float(best["val_acc"])
            and float(val_metrics["balanced_acc"]) > float(best["val_balanced_acc"])
        )
        if better:
            best = {
                "val_acc": float(val_metrics["acc"]),
                "val_balanced_acc": float(val_metrics["balanced_acc"]),
                "epoch": epoch,
                "val": val_metrics,
            }
            torch.save({"model": model.state_dict(), "epoch": epoch, "val": val_metrics, "spec": spec}, ckpt)
            stale = 0
        else:
            stale += 1
            if stale >= patience:
                print(f"early stop at epoch {epoch}, best={best['epoch']}", flush=True)
                break
    model.load_state_dict(torch.load(ckpt, map_location=device)["model"])
    evals = {}
    for split_name, loader in loaders.items():
        if split_name == "train":
            continue
        pred = _predict(model, loader, device, clinical_dim)
        metrics = score_binary(pred["y"], pred["pred"], pred["logit"])
        evals[split_name] = metrics
        pred_path = report_dir / f"{split_name}_predictions.csv"
        with pred_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["split", "patient_id", "source", "y", "pred", "logit"])
            for pid, src, y, p, logit in zip(
                pred["patient_id"], pred["source"], pred["y"], pred["pred"], pred["logit"]
            ):
                writer.writerow([split_name, pid, src, int(y), int(p), float(logit)])
    final = {"best": best, "history": history, "eval": evals, "spec": spec}
    (report_dir / "metrics.json").write_text(json.dumps(_jsonable(final), indent=2), encoding="utf-8")
    _write_binary_summary(report_dir, spec, best, evals)
    return final


def _load_fourclass(device: str) -> tuple[GastricUSFromScratch, int]:
    ckpt = torch.load(DEFAULT_FOURCLASS_CKPT, map_location=device)
    spec = ckpt.get("spec", {})
    clinical_dim = 0 if spec.get("clinical") == "none" else 22
    model = GastricUSFromScratch(
        clinical_dim=clinical_dim,
        fusion=spec.get("fusion", "concat"),
        pool=spec.get("pool", "gated"),
        size=spec.get("size", "xlarge"),
        pool_proj=bool(spec.get("pool_proj", False)),
        residual=bool(spec.get("residual", True)),
        n_classes=4,
    ).to(device)
    model.load_state_dict(ckpt["model"])
    model.eval()
    return model, clinical_dim


def _load_binary(report_dir: Path, device: str) -> tuple[GastricUSFromScratch, int]:
    ckpt = torch.load(report_dir / "best_model.pt", map_location=device)
    spec = ckpt.get("spec", {})
    clinical_dim = 0 if spec.get("clinical") == "none" else 22
    model = GastricUSFromScratch(
        clinical_dim=clinical_dim,
        fusion="concat",
        pool=spec.get("pool", "gated"),
        size=spec.get("size", "xlarge"),
        pool_proj=False,
        residual=True,
        n_classes=2,
    ).to(device)
    model.load_state_dict(ckpt["model"])
    model.eval()
    return model, clinical_dim


def evaluate_cascade(
    binary_dir: Path,
    device: str = "cuda:0",
    batch_size: int = 16,
    max_frames: int = 16,
    dest: Path | None = None,
) -> dict[str, object]:
    dest = Path(dest or (BINARY_REPORT_DIR / "cascade_gated"))
    dest.mkdir(parents=True, exist_ok=True)
    four, four_dim = _load_fourclass(device)
    binary, bin_dim = _load_binary(binary_dir, device)
    evals = {}
    for split_name in ("val", "test_prospective", "test_external"):
        full_loader = DataLoader(
            PatientBagDataset(CACHE_DIR / f"{split_name}_embeddings.npz", max_frames=max_frames, task="t4"),
            batch_size=batch_size,
            shuffle=False,
            collate_fn=collate,
        )
        four_pred = _predict(four, full_loader, device, four_dim)
        bin_pred = _predict(binary, full_loader, device, bin_dim)
        y = four_pred["y"]
        gate = four_pred["pred"]
        refined = gate.copy()
        use_bin = (gate == 2) | (gate == 3)
        refined[use_bin] = np.where(bin_pred["pred"][use_bin] == 1, 3, 2)
        metrics = score_arrays(y, refined)
        metrics["confusion"] = confusion(y, refined)
        oracle = (y == 2) | (y == 3)
        oracle_bin = score_binary((y[oracle] == 3).astype(int), bin_pred["pred"][oracle], bin_pred["logit"][oracle])
        metrics["oracle_t34"] = oracle_bin
        metrics["n_gated_to_binary"] = int(use_bin.sum())
        evals[split_name] = metrics
        pred_path = dest / f"{split_name}_predictions.csv"
        with pred_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["split", "patient_id", "source", "y", "pred_4class", "pred_cascade", "used_binary"])
            for pid, src, yi, g, r, used in zip(
                four_pred["patient_id"], four_pred["source"], y, gate, refined, use_bin.astype(int)
            ):
                writer.writerow([split_name, pid, src, int(yi), int(g), int(r), int(used)])
    lines = [
        "# Cascade: default 4-class gated + T3/T4 binary refine",
        "",
        "4-class checkpoint: `medsiglip_gastricus_opt_xlarge_20260821/mlp_concat_gated`.",
        "If the 4-class head predicts T3 or T4+, replace it with the T3-vs-T4+ binary head.",
        "oracle_t34 is the binary head on true T3/T4 only (upper bound if the gate were perfect).",
        "",
        "| split | n | ACC | adj | QWK | T3 | T4+ | serosa | n_refine | oracle_n | oracle_ACC | oracle_AUC |",
        "|-------|--:|----:|----:|----:|---:|----:|-------:|---------:|---------:|-----------:|-----------:|",
    ]
    for name, metrics in evals.items():
        oracle = metrics["oracle_t34"]
        lines.append(
            "| {name} | {n} | {acc:.4f} | {adj:.4f} | {qwk:.4f} | {t3:.4f} | {t4:.4f} | {ser:.4f} | "
            "{nr} | {on} | {oa:.4f} | {auc:.4f} |".format(
                name=name,
                n=int(metrics["n"]),
                acc=float(metrics["acc"]),
                adj=float(metrics["adj_acc"]),
                qwk=float(metrics["qwk"]),
                t3=float(metrics["recall_T3"]),
                t4=float(metrics["recall_T4+"]),
                ser=float(metrics["serosa_acc"]),
                nr=int(metrics["n_gated_to_binary"]),
                on=int(oracle["n"]),
                oa=float(oracle["acc"]),
                auc=float(oracle["auc"]),
            )
        )
    for name, metrics in evals.items():
        lines += ["", f"## {name} confusion (rows = true)", ""]
        lines += md_confusion(metrics["confusion"])
    (dest / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (dest / "metrics.json").write_text(json.dumps(_jsonable({"eval": evals}), indent=2), encoding="utf-8")
    return {"eval": evals, "report": str(dest)}


def _read_pred_csv(path: Path) -> tuple[np.ndarray, np.ndarray]:
    y: list[int] = []
    pred: list[int] = []
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            y.append(int(row["y"]))
            pred.append(int(row["pred"] if "pred" in row and row["pred"] != "" else row.get("pred_cascade", "0")))
    return np.asarray(y, dtype=int), np.asarray(pred, dtype=int)


def write_mcnemar(dest: Path) -> dict[str, object]:
    dest.mkdir(parents=True, exist_ok=True)
    pairs = {
        "default_vs_t34pair": (
            OPT_REPORT_DIR / "mlp_concat_gated",
            T34_REPORT_DIR / "gated_t34_acc",
            "pred",
            "pred",
        ),
        "default_vs_cascade": (
            OPT_REPORT_DIR / "mlp_concat_gated",
            dest.parent / "cascade_gated",
            "pred",
            "pred_cascade",
        ),
    }
    out: dict[str, object] = {}
    lines = [
        "# Paired exact McNemar",
        "",
        "Same patients. Cell counts are exact-ACC disagreements.",
        "`p_exact` is two-sided binomial on the discordant pairs.",
        "",
        "| pair | split | n | ACC_A | ACC_B | A right B wrong | A wrong B right | discord | p_exact |",
        "|------|-------|--:|------:|------:|----------------:|----------------:|--------:|--------:|",
    ]
    for pair_name, (dir_a, dir_b, col_a, col_b) in pairs.items():
        out[pair_name] = {}
        for split_name in ("val", "test_prospective", "test_external"):
            path_a = dir_a / f"{split_name}_predictions.csv"
            path_b = dir_b / f"{split_name}_predictions.csv"
            if not path_a.is_file() or not path_b.is_file():
                continue
            y_a, pred_a = _read_named(path_a, col_a)
            y_b, pred_b = _read_named(path_b, col_b)
            if len(y_a) != len(y_b) or not np.array_equal(y_a, y_b):
                raise ValueError(f"patient/label mismatch {pair_name} {split_name}")
            stats = mcnemar_exact(y_a, pred_a, pred_b)
            out[pair_name][split_name] = stats
            lines.append(
                "| {pair} | {split} | {n} | {aa:.4f} | {ab:.4f} | {n01} | {n10} | {nd} | {p:.4f} |".format(
                    pair=pair_name,
                    split=split_name,
                    n=int(stats["n"]),
                    aa=float(stats["acc_a"]),
                    ab=float(stats["acc_b"]),
                    n01=int(stats["n_a_right_b_wrong"]),
                    n10=int(stats["n_a_wrong_b_right"]),
                    nd=int(stats["n_discordant"]),
                    p=float(stats["p_exact"]),
                )
            )
    (dest / "MCNEMAR.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (dest / "mcnemar.json").write_text(json.dumps(_jsonable(out), indent=2), encoding="utf-8")
    return out


def _read_named(path: Path, pred_col: str) -> tuple[np.ndarray, np.ndarray]:
    y: list[int] = []
    pred: list[int] = []
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = sorted(reader, key=lambda r: r["patient_id"])
        for row in rows:
            y.append(int(row["y"]))
            pred.append(int(row[pred_col]))
    return np.asarray(y, dtype=int), np.asarray(pred, dtype=int)


def _binary_compare(results: list[dict[str, object]]) -> str:
    lines = [
        "# GastricUS binary serosa / T3-vs-T4+",
        "",
        "Same frozen MedSigLIP-448 cache. Heads are 2-class only.",
        "serosa: T4+ vs not-T4+ on all patients. t34: T4+ vs T3 on the T3/T4 subset only.",
        "",
        "| run | task | pool | n_train | val ACC / bal / AUC | prosp ACC / bal / AUC | ext ACC / bal / AUC |",
        "|-----|------|------|--------:|--------------------:|----------------------:|--------------------:|",
    ]
    for item in results:
        ev = item["eval"]
        spec = item["spec"]
        val = ev["val"]
        pro = ev.get("test_prospective", {})
        ext = ev.get("test_external", {})
        lines.append(
            "| {name} | {task} | {pool} | {nt} | {va:.4f} / {vb:.4f} / {vu:.4f} | "
            "{pa:.4f} / {pb:.4f} / {pu:.4f} | {ea:.4f} / {eb:.4f} / {eu:.4f} |".format(
                name=spec["name"],
                task=spec["task"],
                pool=spec["pool"],
                nt=int(spec["n_train"]),
                va=float(val["acc"]),
                vb=float(val["balanced_acc"]),
                vu=float(val["auc"]),
                pa=float(pro.get("acc", 0.0)),
                pb=float(pro.get("balanced_acc", 0.0)),
                pu=float(pro.get("auc", 0.0)),
                ea=float(ext.get("acc", 0.0)),
                eb=float(ext.get("balanced_acc", 0.0)),
                eu=float(ext.get("auc", 0.0)),
            )
        )
    return "\n".join(lines) + "\n"


def train_binary_sweep(
    device: str = "cuda:0",
    epochs: int = 80,
    batch_size: int = 16,
    lr: float = 2e-4,
    size: str = "xlarge",
    warmup_epochs: int = 8,
    patience: int = 25,
) -> dict[str, object]:
    dest_root = BINARY_REPORT_DIR
    dest_root.mkdir(parents=True, exist_ok=True)
    results = []
    for spec in BINARY_RUNS:
        dest = dest_root / spec["name"]
        print(f"=== binary {spec['name']} ===", flush=True)
        results.append(
            train_binary(
                task=spec["task"],
                pool=spec["pool"],
                device=device,
                epochs=epochs,
                batch_size=batch_size,
                lr=lr,
                size=size,
                warmup_epochs=warmup_epochs,
                patience=patience,
                report_dir=dest,
                run_name=spec["name"],
            )
        )
    compare = _binary_compare(results)
    (dest_root / "COMPARE.md").write_text(compare, encoding="utf-8")
    print(compare, flush=True)
    cascade = evaluate_cascade(dest_root / "t34_gated", device=device, batch_size=batch_size)
    print("cascade", {k: {kk: v[kk] for kk in ("n", "acc", "recall_T3", "recall_T4+") if kk in v} for k, v in cascade["eval"].items()}, flush=True)
    mcnemar = write_mcnemar(dest_root / "paired")
    print("mcnemar", mcnemar, flush=True)
    return {
        "runs": [r["spec"]["name"] for r in results],
        "report": str(dest_root),
        "cascade": cascade["report"],
    }
