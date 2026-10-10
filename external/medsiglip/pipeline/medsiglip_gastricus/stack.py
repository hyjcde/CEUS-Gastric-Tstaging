"""Soft-prob stack of existing frozen heads. New folder. Does not overwrite votes."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from .constants import (
    CACHE_DIR,
    CLASS_NAMES,
    EXPAND15_REPORT_DIR,
    LAYERS_CACHE_DIR,
    LAYERS_REPORT_DIR,
    N_CLASSES,
    OPT_REPORT_DIR,
    PLAN_LITERAL_REPORT_DIR,
    STACK_REPORT_DIR,
    cache_dir_for_expand,
)
from .metrics import confusion, per_center, score_arrays
from .model import GastricUSFromScratch
from .tabpfn_clinical import TIME192_CACHE, load_time192_map
from .train import (
    PatientBagDataset,
    _clinical_batch,
    _jsonable,
    _metric_row,
    _write_summary,
    collate,
)

MEMBERS = {
    "default_gated": {
        "ckpt": OPT_REPORT_DIR / "mlp_concat_gated" / "best_model.pt",
        "cache": CACHE_DIR,
        "head": "mlp",
        "embed_dim": 1152,
        "clinical_dim": 22,
    },
    "expand15_time": {
        "ckpt": EXPAND15_REPORT_DIR / "tabpfn_time_concat_gated" / "best_model.pt",
        "cache": cache_dir_for_expand(0.15),
        "head": "tabpfn_time",
        "embed_dim": 1152,
        "clinical_dim": 192,
    },
    "layers_time": {
        "ckpt": LAYERS_REPORT_DIR / "tabpfn_time_concat_gated" / "best_model.pt",
        "cache": LAYERS_CACHE_DIR,
        "head": "tabpfn_time",
        "embed_dim": 5760,
        "clinical_dim": 192,
    },
    "time192": {
        "ckpt": PLAN_LITERAL_REPORT_DIR / "xlarge_concat_gated_time192" / "best_model.pt",
        "cache": CACHE_DIR,
        "head": "tabpfn_time",
        "embed_dim": 1152,
        "clinical_dim": 192,
    },
}

SPLITS = ("train", "val", "test_prospective", "test_external")


def _device(name: str) -> str:
    if name.startswith("cuda") and torch.cuda.is_available():
        return name
    return "cpu"


def _load_member(spec: dict[str, object], device: str) -> torch.nn.Module:
    ckpt = torch.load(spec["ckpt"], map_location=device, weights_only=False)
    saved = ckpt.get("spec") or {}
    model = GastricUSFromScratch(
        clinical_dim=int(spec["clinical_dim"]),
        fusion=str(saved.get("fusion", "concat")),
        pool=str(saved.get("pool", "gated")),
        size=str(saved.get("size", "xlarge")),
        pool_proj=bool(saved.get("pool_proj", False)),
        residual=bool(saved.get("residual", True)),
        pool_out=saved.get("pool_out"),
        embed_dim=int(spec["embed_dim"]),
    ).to(device)
    model.load_state_dict(ckpt["model"])
    model.eval()
    return model


def _loader(cache: Path, split: str, head: str) -> DataLoader:
    tabpfn_map = None
    if head == "tabpfn_time":
        tabpfn_map = load_time192_map(CACHE_DIR, cache_name=TIME192_CACHE)
    return DataLoader(
        PatientBagDataset(cache / f"{split}_embeddings.npz", tabpfn_map=tabpfn_map),
        batch_size=16,
        shuffle=False,
        collate_fn=collate,
    )


@torch.no_grad()
def _dump_member(name: str, spec: dict[str, object], device: str) -> dict[str, dict[str, np.ndarray]]:
    model = _load_member(spec, device)
    clinical_dim = int(spec["clinical_dim"])
    out: dict[str, dict[str, np.ndarray]] = {}
    for split in SPLITS:
        path = spec["cache"] / f"{split}_embeddings.npz"
        if not path.is_file():
            continue
        loader = _loader(spec["cache"], split, str(spec["head"]))
        pids: list[str] = []
        ys: list[int] = []
        sources: list[str] = []
        logits_all: list[np.ndarray] = []
        for batch in loader:
            logits = model(
                batch["e_full"].to(device),
                batch["e_roi"].to(device),
                batch["valid"].to(device),
                _clinical_batch(batch, device, clinical_dim, clinical="raw"),
            )
            logits_all.append(logits.detach().cpu().numpy())
            pids.extend(batch["patient_id"])
            ys.extend(batch["label"].cpu().numpy().astype(int).tolist())
            sources.extend(batch["source"])
        out[split] = {
            "patient_id": np.asarray(pids),
            "y": np.asarray(ys, dtype=np.int64),
            "source": np.asarray(sources),
            "logits": np.concatenate(logits_all, axis=0).astype(np.float32),
        }
        print(f"stack dump {name} {split} n={len(pids)}", flush=True)
    del model
    if device.startswith("cuda"):
        torch.cuda.empty_cache()
    return out


def _align(dumps: dict[str, dict[str, dict[str, np.ndarray]]], split: str, names: list[str]) -> dict[str, object]:
    base = dumps[names[0]][split]
    index = {str(pid): i for i, pid in enumerate(base["patient_id"])}
    order = [index[str(pid)] for pid in base["patient_id"]]
    y = base["y"][order]
    source = base["source"][order]
    pids = np.asarray([str(pid) for pid in base["patient_id"]])
    probs = []
    logits = []
    for name in names:
        block = dumps[name][split]
        lookup = {str(pid): i for i, pid in enumerate(block["patient_id"])}
        idx = np.asarray([lookup[str(pid)] for pid in pids], dtype=np.int64)
        if not np.array_equal(block["y"][idx], y):
            raise ValueError(f"label mismatch in {name} {split}")
        logit = block["logits"][idx]
        logits.append(logit)
        exp = np.exp(logit - logit.max(axis=1, keepdims=True))
        probs.append(exp / exp.sum(axis=1, keepdims=True))
    return {
        "patient_id": pids,
        "y": y,
        "source": source,
        "probs": np.stack(probs, axis=1).astype(np.float32),
        "logits": np.stack(logits, axis=1).astype(np.float32),
    }


def _pack(y: np.ndarray, pred: np.ndarray, pids: np.ndarray, sources: np.ndarray) -> dict[str, object]:
    metrics = score_arrays(y, pred)
    metrics["confusion"] = confusion(y, pred)
    metrics["centers"] = per_center(y, pred, sources.astype(str).tolist())
    metrics["predictions"] = [
        {"patient_id": str(pid), "source": str(src), "y": int(yy), "pred": int(pp)}
        for pid, src, yy, pp in zip(pids, sources, y, pred)
    ]
    return metrics


def _uniform(probs: np.ndarray) -> np.ndarray:
    return probs.mean(axis=1)


def _mix_grid(val_probs: np.ndarray, y: np.ndarray) -> np.ndarray:
    grid = (0.0, 0.25, 0.5, 1.0)
    best_w = np.ones(val_probs.shape[1], dtype=np.float32)
    best_acc = -1.0
    for w0 in grid:
        for w1 in grid:
            for w2 in grid:
                for w3 in grid:
                    raw = np.asarray([w0, w1, w2, w3], dtype=np.float32)
                    if float(raw.sum()) <= 0:
                        continue
                    w = raw / raw.sum()
                    pred = (val_probs * w.reshape(1, -1, 1)).sum(axis=1).argmax(axis=1)
                    acc = float((pred == y).mean())
                    if acc > best_acc:
                        best_acc = acc
                        best_w = w
    return best_w


def _apply_mix(probs: np.ndarray, weights: np.ndarray) -> np.ndarray:
    return (probs * weights.reshape(1, -1, 1)).sum(axis=1)


def _train_linear(train_x: np.ndarray, train_y: np.ndarray, val_x: np.ndarray, val_y: np.ndarray) -> np.ndarray:
    device = "cpu"
    x_tr = torch.from_numpy(train_x)
    y_tr = torch.from_numpy(train_y)
    x_va = torch.from_numpy(val_x)
    counts = np.bincount(train_y, minlength=N_CLASSES).astype(np.float32)
    weights = len(train_y) / (N_CLASSES * np.maximum(counts, 1.0))
    loss_fn = torch.nn.CrossEntropyLoss(weight=torch.tensor(weights), label_smoothing=0.05)
    best_state = None
    best_acc = -1.0
    for seed in (20260821, 20260822, 7):
        torch.manual_seed(seed)
        model = torch.nn.Linear(train_x.shape[1], N_CLASSES)
        opt = torch.optim.AdamW(model.parameters(), lr=3e-3, weight_decay=1e-3)
        for _ in range(400):
            model.train()
            opt.zero_grad(set_to_none=True)
            loss_fn(model(x_tr), y_tr).backward()
            opt.step()
            model.eval()
            pred = model(x_va).argmax(dim=-1).numpy()
            acc = float((pred == val_y).mean())
            if acc > best_acc:
                best_acc = acc
                best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
    model = torch.nn.Linear(train_x.shape[1], N_CLASSES)
    model.load_state_dict(best_state)
    model.eval()
    return model


def _write_preds(report_dir: Path, split: str, metrics: dict[str, object]) -> None:
    rows = metrics["predictions"]
    (report_dir / f"{split}_predictions.csv").write_text(
        "split,center,patient_id,y,pred,T_true,T_pred,adjacent\n"
        + "".join(
            f"{split},{r['source']},{r['patient_id']},{r['y']},{r['pred']},"
            f"{CLASS_NAMES[r['y']]},{CLASS_NAMES[r['pred']]},{int(abs(r['y']-r['pred'])<=1)}\n"
            for r in rows
        ),
        encoding="utf-8",
    )


def run_stack(device: str = "cuda:0", report_dir: Path | None = None) -> dict[str, object]:
    report_dir = report_dir or STACK_REPORT_DIR
    device = _device(device)
    names = [name for name, spec in MEMBERS.items() if Path(spec["ckpt"]).is_file()]
    if len(names) < 2:
        raise FileNotFoundError(f"need at least two member checkpoints, found {names}")
    dumps = {}
    for name in names:
        dumps[name] = _dump_member(name, MEMBERS[name], device)
    aligned = {split: _align(dumps, split, names) for split in SPLITS if split in dumps[names[0]]}
    val = aligned["val"]
    train = aligned["train"]
    val_probs = val["probs"]
    mix_w = _mix_grid(val_probs, val["y"])
    train_x = train["probs"].reshape(len(train["y"]), -1)
    val_x = val_probs.reshape(len(val["y"]), -1)
    linear = _train_linear(train_x, train["y"], val_x, val["y"])

    candidates = {
        "uniform_mean": lambda probs: _uniform(probs),
        "val_mix": lambda probs: _apply_mix(probs, mix_w),
        "train_linear": lambda probs: linear(torch.from_numpy(probs.reshape(len(probs), -1))).detach().numpy(),
    }
    scored = []
    for rule, fn in candidates.items():
        pred = fn(val_probs).argmax(axis=1)
        acc = float((pred == val["y"]).mean())
        scored.append({"rule": rule, "val_acc": acc})
    scored.sort(key=lambda row: (-row["val_acc"], row["rule"]))
    chosen = scored[0]["rule"]
    apply = candidates[chosen]

    evals = {}
    report_dir.mkdir(parents=True, exist_ok=True)
    for split, block in aligned.items():
        pred = apply(block["probs"]).argmax(axis=1)
        evals[split] = _pack(block["y"], pred, block["patient_id"], block["source"])
        _write_preds(report_dir, split, evals[split])

    spec = {
        "name": f"stack_{chosen}",
        "fusion": "n/a",
        "pool": "stack",
        "head": "stack",
        "size": "n/a",
        "n_params": int(16 * N_CLASSES + N_CLASSES) if chosen == "train_linear" else 0,
        "class_weight": "balanced",
        "clinical": "inherited",
        "pool_proj": False,
        "ordinal_weight": 0.0,
        "lock": "acc",
        "members": names,
        "rule": chosen,
        "mix_weights": {name: float(w) for name, w in zip(names, mix_w)},
        "val_rule_table": scored,
    }
    best = {"epoch": 0, "val_acc": float(evals["val"]["acc"])}
    payload = {"best": best, "spec": spec, "eval": {k: dict(v) for k, v in evals.items()}, "val_rules": scored}
    for metrics in payload["eval"].values():
        metrics.pop("predictions", None)
    (report_dir / "metrics.json").write_text(json.dumps(_jsonable(payload), indent=2), encoding="utf-8")
    _write_summary(report_dir, spec, best, evals)
    compare = [
        "# GastricUS softmax stack",
        "",
        f"Members: {', '.join(names)}.",
        "Rules locked on val exact ACC, then applied to prospective and external.",
        "",
        "| rule | val ACC |",
        "|------|--------:|",
    ]
    for row in scored:
        mark = " (chosen)" if row["rule"] == chosen else ""
        compare.append(f"| {row['rule']}{mark} | {row['val_acc']:.4f} |")
    compare += [
        "",
        f"val_mix weights: {spec['mix_weights']}",
        "",
        "| split | n | ACC | adj | T3 |",
        "|-------|--:|----:|----:|---:|",
        _metric_row("val", evals["val"]),
        _metric_row("test_prospective", evals["test_prospective"]),
        _metric_row("test_external", evals["test_external"]),
        "",
        "Does not overwrite hard-vote folders. Does not unfreeze MedSigLIP.",
        "",
    ]
    (report_dir / "COMPARE.md").write_text("\n".join(compare), encoding="utf-8")
    (report_dir / "SUMMARY.md").write_text(
        (report_dir / "SUMMARY.md").read_text(encoding="utf-8")
        + f"\nLocked stack rule on val: {chosen}. Members: {', '.join(names)}.\n",
        encoding="utf-8",
    )
    return {
        "rule": chosen,
        "members": names,
        "val_acc": float(evals["val"]["acc"]),
        "prosp_acc": float(evals["test_prospective"]["acc"]),
        "ext_acc": float(evals["test_external"]["acc"]),
        "report": str(report_dir),
    }
