"""Long unfreeze + plan 6.2 TabPFN clinical expert.

Does not change the CLI default. Writes a new report folder only.
TabPFN never sees image embeddings. TIME-192 and 4-class OOF stay frozen.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.optim.lr_scheduler import LambdaLR
from torch.utils.data import DataLoader
from transformers import AutoModel, AutoProcessor

from .constants import (
    CACHE_DIR,
    CLASS_NAMES,
    DATASET_DIR,
    DEFAULT_FOURCLASS_CKPT,
    LONGRUN_REPORT_DIR,
    N_CLASSES,
    PLAN_COMPLETE_REPORT_DIR,
    SPLIT_FILES,
    WADI_DATASET_DIR,
    WEIGHT_DIR,
)
from .encode import assert_weights
from .metrics import center_of
from .model import GastricUSFromScratch
from .tabpfn_clinical import (
    TIME192_CACHE,
    build_tabpfn_cache,
    build_time192_cache,
    load_tabpfn_map,
    load_time192_map,
)
from .train import (
    _clinical_batch,
    _cosine_warmup,
    _is_better,
    _jsonable,
    _write_summary,
    ordinal_rank_loss,
    t2_off2_loss,
)
from .unfreeze import (
    DualViewLoRA,
    ImageBagDataset,
    evaluate_images,
    make_collate,
    wrap_full_last_n,
)


class _Tee:
    def __init__(self, *streams) -> None:
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            stream.write(data)
            stream.flush()
        return len(data)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()

    def isatty(self) -> bool:
        return False


def _tabpfn_vector(pid: str, time_map: dict[str, np.ndarray], proba_map: dict[str, np.ndarray]) -> np.ndarray:
    if pid not in time_map or pid not in proba_map:
        raise KeyError("missing TabPFN clinical row")
    return np.concatenate([time_map[pid], proba_map[pid]], axis=0).astype(np.float32)


class TabpfnBagDataset(ImageBagDataset):
    def __init__(self, split: str, tabpfn_map: dict[str, np.ndarray], **kwargs) -> None:
        super().__init__(split, **kwargs)
        self.tabpfn_map = tabpfn_map

    def __getitem__(self, idx: int) -> dict[str, object]:
        item = super().__getitem__(idx)
        pid = str(item["patient_id"])
        item["clinical"] = torch.from_numpy(self.tabpfn_map[pid])
        return item


def ensure_tabpfn_maps(
    tabpfn_device: str = "cpu",
    seed: int = 20260821,
    mode: str = "tabpfn",
) -> dict[str, np.ndarray]:
    if not (CACHE_DIR / "tabpfn_clin11_oof.npz").is_file():
        build_tabpfn_cache(CACHE_DIR, device=tabpfn_device, seed=seed)
    proba_map = load_tabpfn_map(CACHE_DIR)
    if mode == "tabpfn":
        return proba_map
    if mode != "tabpfn_both":
        raise ValueError(mode)
    if not (CACHE_DIR / TIME192_CACHE).is_file():
        build_time192_cache(CACHE_DIR, device=tabpfn_device, seed=seed)
    time_map = load_time192_map(CACHE_DIR, cache_name=TIME192_CACHE)
    common = sorted(set(time_map) & set(proba_map))
    if len(common) != len(time_map) or len(common) != len(proba_map):
        print(
            f"tabpfn key overlap n={len(common)} time={len(time_map)} oof={len(proba_map)}",
            flush=True,
        )
    return {pid: _tabpfn_vector(pid, time_map, proba_map) for pid in common}


def assert_wadi_development_contract() -> dict[str, object]:
    """Verify that the clinical pack uses exactly the frozen WADI development patients."""
    pairs = {
        "train": WADI_DATASET_DIR / "development/train_maincenter_1062.csv",
        "val": WADI_DATASET_DIR / "development/dev_maincenter_128.csv",
    }
    summary: dict[str, object] = {}
    sets: dict[str, set[str]] = {}
    for split, wadi_path in pairs.items():
        legacy_path = DATASET_DIR / SPLIT_FILES[split]
        if not wadi_path.is_file() or not legacy_path.is_file():
            raise FileNotFoundError(f"missing contract table: {wadi_path} or {legacy_path}")
        wadi = pd.read_csv(wadi_path, usecols=["patient_id", "label"])
        clinical = pd.read_csv(
            legacy_path,
            usecols=["patient_id", "label", "lauren_type_missing", "differentiation_missing"],
        )
        wadi_ids = set(wadi["patient_id"].astype(str))
        clinical_ids = set(clinical["patient_id"].astype(str))
        if wadi_ids != clinical_ids:
            raise RuntimeError(
                f"{split} clinical/WADI membership mismatch: "
                f"clinical_only={len(clinical_ids - wadi_ids)} wadi_only={len(wadi_ids - clinical_ids)}"
            )
        wadi_y = wadi.assign(patient_id=wadi["patient_id"].astype(str)).groupby("patient_id")["label"].first()
        clinical_y = (
            clinical.assign(patient_id=clinical["patient_id"].astype(str))
            .groupby("patient_id")["label"]
            .first()
        )
        if not wadi_y.sort_index().equals(clinical_y.sort_index()):
            raise RuntimeError(f"{split} clinical/WADI labels differ")
        patient_clinical = clinical.assign(patient_id=clinical["patient_id"].astype(str)).groupby("patient_id").first()
        sets[split] = wadi_ids
        summary[split] = {
            "patients": len(wadi_ids),
            "lauren_available": int((patient_clinical["lauren_type_missing"] == 0).sum()),
            "differentiation_available": int((patient_clinical["differentiation_missing"] == 0).sum()),
        }
    overlap = sets["train"] & sets["val"]
    if overlap:
        raise RuntimeError(f"WADI train/val overlap: {len(overlap)} patients")
    summary["train_val_overlap"] = 0
    return summary


def assert_tabpfn_coverage(
    tabpfn_map: dict[str, np.ndarray],
    splits: tuple[str, ...] = ("train", "val"),
) -> None:
    missing = 0
    n = 0
    for split in splits:
        pids = ImageBagDataset(split, max_frames=1).pids
        n += len(pids)
        missing += sum(1 for pid in pids if pid not in tabpfn_map)
    if missing:
        raise RuntimeError(f"TabPFN map missing {missing}/{n} crop+mask patients")
    dim = int(next(iter(tabpfn_map.values())).shape[-1])
    print(f"tabpfn coverage {n - missing}/{n} dim={dim}", flush=True)


def _warm_fusion_pool(head: GastricUSFromScratch, ckpt: Path) -> None:
    payload = torch.load(ckpt, map_location="cpu", weights_only=False)
    src = payload.get("model") or payload.get("head") or {}
    own = head.state_dict()
    keep = {k: v for k, v in src.items() if k in own and tuple(v.shape) == tuple(own[k].shape)}
    missing, unexpected = head.load_state_dict(keep, strict=False)
    print(
        f"warm_fusion_pool {ckpt} loaded={len(keep)} skipped_head={sum(1 for k in missing if k.startswith('head.'))}",
        flush=True,
    )
    del unexpected


def _trainable_backbone(model: DualViewLoRA) -> dict[str, torch.Tensor]:
    names = {n for n, p in model.backbone.named_parameters() if p.requires_grad}
    return {k: v.detach().cpu() for k, v in model.backbone.state_dict().items() if k in names}


def _save_last(
    path: Path,
    model: DualViewLoRA,
    opt: torch.optim.Optimizer,
    scheduler: LambdaLR,
    epoch: int,
    best: dict[str, object],
    history: list[dict[str, object]],
    stale: int,
    spec: dict[str, object],
) -> None:
    torch.save(
        {
            "head": model.head.state_dict(),
            "backbone": _trainable_backbone(model),
            "optimizer": opt.state_dict(),
            "scheduler": scheduler.state_dict(),
            "epoch": epoch,
            "best": best,
            "history": history,
            "stale": stale,
            "spec": spec,
            "mode": "full",
        },
        path,
    )


def train_longrun(
    device: str = "cuda:0",
    epochs: int = 48,
    max_frames: int = 8,
    last_n: int = 16,
    encoder_lr: float = 5e-6,
    head_lr: float = 1e-4,
    weight_decay: float = 2e-4,
    expand: float = 0.20,
    warmup_epochs: int = 4,
    patience: int = 16,
    accum: int = 4,
    label_smoothing: float = 0.05,
    grad_clip: float = 1.0,
    lock: str = "acc",
    ordinal_weight: float = 0.5,
    seed: int = 20260821,
    tabpfn_device: str = "cpu",
    clinical: str = "tabpfn",
    pool: str = "mean_views",
    size: str = "xlarge",
    report_dir: Path | None = None,
    warm_fusion: bool = True,
    resume: bool = False,
    num_workers: int = 0,
    log_every: int = 50,
    command: list[str] | None = None,
    t2_off2_weight: float = 0.4,
    clinical_dropout: float = 0.15,
    min_t2_recall: float = 0.20,
    evaluate_audits: bool = False,
) -> dict[str, object]:
    if clinical not in {"tabpfn", "tabpfn_both", "raw"}:
        raise ValueError(clinical)
    if pool not in {"mean_views", "gated"}:
        raise ValueError(pool)
    if not 0.0 <= clinical_dropout < 1.0:
        raise ValueError("clinical_dropout must be in [0, 1)")
    contract = assert_wadi_development_contract()
    print(f"wadi development contract {json.dumps(contract, sort_keys=True)}", flush=True)
    torch.manual_seed(seed)
    np.random.seed(seed)
    if device.startswith("cuda"):
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cudnn.benchmark = True
    assert_weights()
    tabpfn_map: dict[str, np.ndarray] | None = None
    if clinical in {"tabpfn", "tabpfn_both"}:
        tabpfn_map = ensure_tabpfn_maps(tabpfn_device=tabpfn_device, seed=seed, mode=clinical)
        coverage_splits = ("train", "val", "test_prospective", "test_external") if evaluate_audits else ("train", "val")
        assert_tabpfn_coverage(tabpfn_map, splits=coverage_splits)
        clinical_dim = int(next(iter(tabpfn_map.values())).shape[-1])
        auto_name = f"full{last_n}_{size}_{pool}_tabpfn{clinical_dim}_t2guard"
    else:
        clinical_dim = 22
        auto_name = f"full{last_n}_{size}_{pool}_clin22_t2guard"
        if float(t2_off2_weight) > 0:
            auto_name += "_t2cost"
    report_dir = Path(report_dir) if report_dir else (LONGRUN_REPORT_DIR / auto_name)
    report_dir.mkdir(parents=True, exist_ok=True)
    log_handle = (report_dir / "train.log").open("a", encoding="utf-8")
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = _Tee(old_out, log_handle)
    sys.stderr = _Tee(old_err, log_handle)
    try:
        return _train_longrun_body(
            device=device,
            epochs=epochs,
            max_frames=max_frames,
            last_n=last_n,
            encoder_lr=encoder_lr,
            head_lr=head_lr,
            weight_decay=weight_decay,
            expand=expand,
            warmup_epochs=warmup_epochs,
            patience=patience,
            accum=accum,
            label_smoothing=label_smoothing,
            grad_clip=grad_clip,
            lock=lock,
            ordinal_weight=ordinal_weight,
            seed=seed,
            report_dir=report_dir,
            warm_fusion=warm_fusion,
            resume=resume,
            num_workers=num_workers,
            log_every=log_every,
            command=command,
            tabpfn_map=tabpfn_map,
            clinical_dim=clinical_dim,
            clinical=clinical,
            pool=pool,
            size=size,
            t2_off2_weight=float(t2_off2_weight),
            clinical_dropout=float(clinical_dropout),
            min_t2_recall=float(min_t2_recall),
            evaluate_audits=bool(evaluate_audits),
        )
    finally:
        sys.stdout = old_out
        sys.stderr = old_err
        log_handle.close()


def _train_longrun_body(
    *,
    device: str,
    epochs: int,
    max_frames: int,
    last_n: int,
    encoder_lr: float,
    head_lr: float,
    weight_decay: float,
    expand: float,
    warmup_epochs: int,
    patience: int,
    accum: int,
    label_smoothing: float,
    grad_clip: float,
    lock: str,
    ordinal_weight: float,
    seed: int,
    report_dir: Path,
    warm_fusion: bool,
    resume: bool,
    num_workers: int,
    log_every: int,
    command: list[str] | None,
    tabpfn_map: dict[str, np.ndarray] | None,
    clinical_dim: int,
    clinical: str,
    pool: str,
    size: str,
    t2_off2_weight: float,
    clinical_dropout: float,
    min_t2_recall: float,
    evaluate_audits: bool,
) -> dict[str, object]:
    (report_dir / "command.json").write_text(
        json.dumps(
            {
                "argv": command or sys.argv,
                "device": device,
                "epochs": epochs,
                "last_n": last_n,
                "max_frames": max_frames,
                "encoder_lr": encoder_lr,
                "head_lr": head_lr,
                "resume": resume,
                "t2_off2_weight": t2_off2_weight,
                "clinical_dropout": clinical_dropout,
                "min_t2_recall": min_t2_recall,
                "evaluate_audits": evaluate_audits,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    processor = AutoProcessor.from_pretrained(str(WEIGHT_DIR), local_files_only=True)
    ds_kw = {"max_frames": max_frames, "expand": expand, "seed": seed}
    if tabpfn_map is not None:
        ds_kw["tabpfn_map"] = tabpfn_map
        make_ds = TabpfnBagDataset
    else:
        make_ds = ImageBagDataset
    train_ds = make_ds("train", **ds_kw)
    val_ds = make_ds("val", **ds_kw)
    collate = make_collate(processor)
    loader_kw = {"batch_size": 1, "collate_fn": collate, "num_workers": num_workers, "pin_memory": device.startswith("cuda")}
    train_loader = DataLoader(train_ds, shuffle=True, **loader_kw)
    val_loader = DataLoader(val_ds, shuffle=False, **loader_kw)
    extra = {}
    if evaluate_audits:
        extra = {
            split: DataLoader(make_ds(split, **ds_kw), shuffle=False, **loader_kw)
            for split in ("test_prospective", "test_external")
        }
    backbone = AutoModel.from_pretrained(str(WEIGHT_DIR), local_files_only=True)
    backbone, targets, n_layers = wrap_full_last_n(backbone, last_n=last_n)
    head = GastricUSFromScratch(
        clinical_dim=clinical_dim,
        fusion="concat",
        pool=pool,
        size=size,
        pool_proj=False,
        residual=True,
    )
    last_path = report_dir / "last.pt"
    best_path = report_dir / "best_model.pt"
    resumed = False
    if resume and last_path.is_file():
        resumed = True
    elif warm_fusion:
        warm_ckpt = (
            PLAN_COMPLETE_REPORT_DIR / "tabpfn_concat_mean/best_model.pt"
            if clinical == "tabpfn" and pool == "mean_views" and size == "xlarge"
            else DEFAULT_FOURCLASS_CKPT
        )
        _warm_fusion_pool(head, warm_ckpt)
    model = DualViewLoRA(backbone, head).to(device)
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
        "name": report_dir.name,
        "fusion": "concat",
        "pool": pool,
        "head": "mlp_full_tabpfn" if clinical in {"tabpfn", "tabpfn_both"} else "mlp_full",
        "mode": "full",
        "size": size,
        "n_params": n_trainable,
        "class_weight": "balanced",
        "clinical": (
            f"tabpfn_oof4={clinical_dim}"
            if clinical == "tabpfn"
            else (f"tabpfn_time192+oof4={clinical_dim}" if clinical == "tabpfn_both" else "raw22")
        ),
        "clinical_dropout": clinical_dropout,
        "pool_proj": False,
        "ordinal_weight": ordinal_weight,
        "ordinal_mode": "rank",
        "t2_off2_weight": t2_off2_weight,
        "lock": lock,
        "last_n": last_n,
        "encoder_lr": encoder_lr,
        "head_lr": head_lr,
        "weight_decay": weight_decay,
        "max_frames": max_frames,
        "expand": expand,
        "accum": accum,
        "epochs": epochs,
        "warmup_epochs": warmup_epochs,
        "patience": patience,
        "seed": seed,
        "n_vision_layers": n_layers,
        "lora_targets": targets,
        "resume": resume,
        "data_contract": "WADI 1062/128 membership with versioned clinical sidecar",
        "audit_evaluation": evaluate_audits,
        "min_t2_recall": min_t2_recall,
        "plan": (
            "5.1 mean full/ROI views, 6.2 TabPFN clinical OOF, partial MedSigLIP fine-tune"
            if clinical == "tabpfn" and pool == "mean_views"
            else f"concat, {pool}, {clinical}, partial MedSigLIP fine-tune"
        ),
    }
    (report_dir / "spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    best = {"val_adj_acc": -1.0, "val_acc": -1.0, "val_qwk": -1.0, "val_macro_recall": -1.0}
    history: list[dict[str, object]] = []
    stale = 0
    start_epoch = 1
    if resumed:
        payload = torch.load(last_path, map_location=device, weights_only=False)
        model.backbone.load_state_dict(payload["backbone"], strict=False)
        model.head.load_state_dict(payload["head"])
        opt.load_state_dict(payload["optimizer"])
        scheduler.load_state_dict(payload["scheduler"])
        best = payload.get("best") or best
        history = list(payload.get("history") or [])
        stale = int(payload.get("stale") or 0)
        start_epoch = int(payload.get("epoch") or 0) + 1
        print(f"resume {last_path} next_epoch={start_epoch} best_epoch={best.get('epoch')}", flush=True)
    print(
        f"longrun {spec['name']} trainable={n_trainable} last_n={last_n}/{n_layers} "
        f"frames={max_frames} clinical={clinical_dim} accum={accum} "
        f"epochs={epochs} start={start_epoch}",
        flush=True,
    )
    epoch_log = report_dir / "epoch.log"
    for epoch in range(start_epoch, epochs + 1):
        model.train()
        running = 0.0
        seen = 0
        n_bags = len(train_ds)
        opt.zero_grad(set_to_none=True)
        for step, batch in enumerate(train_loader, 1):
            labels_b = batch["label"].to(device)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=device.startswith("cuda")):
                clinical_b = _clinical_batch(batch, device, clinical_dim)
                if clinical_dropout > 0:
                    drop = torch.rand(clinical_b.shape[0], 1, device=clinical_b.device) < clinical_dropout
                    clinical_b = clinical_b.masked_fill(drop, 0.0)
                    if clinical in {"tabpfn", "tabpfn_both"}:
                        clinical_b[:, -4:] = torch.where(
                            drop,
                            torch.full_like(clinical_b[:, -4:], 0.25),
                            clinical_b[:, -4:],
                        )
                logits = model(
                    batch["pixel_full"].to(device),
                    batch["pixel_roi"].to(device),
                    batch["valid"].to(device),
                    clinical_b,
                )
                loss = loss_fn(logits, labels_b)
                if ordinal_weight > 0:
                    loss = loss + ordinal_weight * ordinal_rank_loss(logits, labels_b)
                if t2_off2_weight > 0:
                    loss = loss + t2_off2_weight * t2_off2_loss(logits, labels_b)
                loss = loss / accum
            loss.backward()
            if step % accum == 0 or step == n_bags:
                if grad_clip > 0:
                    torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
                opt.step()
                opt.zero_grad(set_to_none=True)
            running += float(loss.item()) * accum
            seen += 1
            if step % log_every == 0 or step == n_bags:
                print(f"  epoch {epoch} {step}/{n_bags} loss={running / seen:.4f}", flush=True)
        scheduler.step()
        val_metrics = evaluate_images(model, val_loader, device, clinical_dim=clinical_dim)
        slim = {
            k: val_metrics[k]
            for k in ("n", "acc", "adj_acc", "off2", "qwk", "serosa_acc", "macro_recall", "t2_recall", "recall_T3")
        }
        row = {
            "epoch": epoch,
            "train_loss": running / max(seen, 1),
            "lr_encoder": float(opt.param_groups[0]["lr"]),
            "lr_head": float(opt.param_groups[1]["lr"]),
            **{f"val_{k}": v for k, v in slim.items()},
        }
        history.append(row)
        line = json.dumps({k: (float(v) if isinstance(v, (float, np.floating)) else v) for k, v in row.items()})
        print(line, flush=True)
        with epoch_log.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        current_t2 = float(val_metrics["t2_recall"])
        best_t2 = float((best.get("val") or {}).get("t2_recall", 0.0))
        current_qualified = current_t2 >= min_t2_recall
        best_qualified = best_t2 >= min_t2_recall
        guarded_better = (
            current_qualified and not best_qualified
            or current_qualified == best_qualified and _is_better(val_metrics, best, lock)
        )
        if guarded_better:
            best = {
                "val_adj_acc": float(val_metrics["adj_acc"]),
                "val_acc": float(val_metrics["acc"]),
                "val_qwk": float(val_metrics["qwk"]),
                "val_macro_recall": float(val_metrics["macro_recall"]),
                "epoch": epoch,
                "val": slim,
            }
            torch.save(
                {
                    "head": model.head.state_dict(),
                    "backbone": _trainable_backbone(model),
                    "epoch": epoch,
                    "val": slim,
                    "spec": spec,
                    "mode": "full",
                },
                best_path,
            )
            stale = 0
        else:
            stale += 1
        _save_last(last_path, model, opt, scheduler, epoch, best, history, stale, spec)
        if stale >= patience:
            print(f"early stop at epoch {epoch}, best={best.get('epoch')}", flush=True)
            break
    if not best_path.is_file():
        raise RuntimeError(f"no checkpoint written under {report_dir}")
    saved = torch.load(best_path, map_location=device, weights_only=False)
    model.backbone.load_state_dict(saved["backbone"], strict=False)
    model.head.load_state_dict(saved["head"])
    final = {
        "best": best,
        "history": history,
        "eval": {"val": evaluate_images(model, val_loader, device, clinical_dim=clinical_dim)},
        "spec": spec,
    }
    for split, loader in extra.items():
        final["eval"][split] = evaluate_images(model, loader, device, clinical_dim=clinical_dim)
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
    return {
        "report": str(report_dir),
        "best_epoch": int(best.get("epoch") or 0),
        "acc": {name: float(block["acc"]) for name, block in final["eval"].items()},
    }
