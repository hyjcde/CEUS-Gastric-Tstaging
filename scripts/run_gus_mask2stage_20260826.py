#!/usr/bin/env python3
"""GUS-Mask2Stage: complete runnable pipeline for official T-stage tables.

Think first, then run one step at a time:

  python3 scripts/run_gus_mask2stage_20260826.py --plan
  python3 scripts/run_gus_mask2stage_20260826.py --preflight
  python3 scripts/run_gus_mask2stage_20260826.py --smoke --gpu 1
  python3 scripts/run_gus_mask2stage_20260826.py --phase0 --gpu 1
  python3 scripts/run_gus_mask2stage_20260826.py --train --gpu 1
  python3 scripts/run_gus_mask2stage_20260826.py --eval --gpu 1
  python3 scripts/run_gus_mask2stage_20260826.py --phase1 --gpu 1
  python3 scripts/run_gus_mask2stage_20260826.py --phase2 --gpu 1
  python3 scripts/run_gus_mask2stage_20260826.py --phase3 --gpu 1
  python3 scripts/run_gus_mask2stage_20260826.py --phase4

Official contract: dataset/task_datasets/t_staging/maincenter_retrospective_v20260821
  train 1062 / val 128 / prospective 425 / external 485 patients.

Core model uses image + lesion mask + 1-10 keyframes only.
Clinical fields, similar-case labels, and doctor first-impression are out.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import yaml
from torch.utils.data import DataLoader
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "pipeline") not in sys.path:
    sys.path.insert(0, str(ROOT / "pipeline"))

from lib.gus_mask2stage import (  # noqa: E402
    CLASS_NAMES,
    GEOM_NAMES,
    PREOP18,
    PatientBagGUSDataset,
    build_gus_model,
    compute_geom_stats,
    fold_ordinal_pn_weights,
    geom_sanity_check,
    gus_collate,
    gus_loss,
    legacy_coral_to_probs,
    move_batch,
    param_groups,
    reaggregate_frame_probs,
    resolve_backbone_name,
    score_predictions,
    set_seed,
    sigmoid_region_weights_from_d,
)
from lib.mask_pooled_ordinal import MaskPooledOrdinalClassifier  # noqa: E402
from lib.transforms import get_val_transforms  # noqa: E402
from lib.datasets import _resolve_repo_path  # noqa: E402

CONFIG = ROOT / "pipeline/configs/tstaging_4class_gus_mask2stage_20260826.yaml"
REPORT = ROOT / "pipeline/experiments/reports/gus_mask2stage_20260826"
SPLITS = ("train", "val", "test_prospective", "test_external")
LOCKED = {"test_prospective": 425, "test_external": 485}
MASK_VARIANTS = ("M0", "M1", "M2", "M3", "M4", "M5", "M6")
AGG_VARIANTS = ("A0", "A1", "A2", "A3", "A4", "A5")
ORD_VARIANTS = ("O0", "O1", "O2", "O3")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--plan", action="store_true")
    p.add_argument("--preflight", action="store_true")
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--phase0", action="store_true", help="re-aggregate the live mask-pool CORAL checkpoint")
    p.add_argument("--train", action="store_true", help="train one variant (default M4/A4/O3)")
    p.add_argument("--eval", action="store_true")
    p.add_argument("--phase1", action="store_true", help="mask-usage matrix M0-M6")
    p.add_argument("--phase2", action="store_true", help="aggregation matrix A0-A5 on a locked visual ckpt")
    p.add_argument("--phase3", action="store_true", help="ordinal head matrix O0-O3")
    p.add_argument("--phase4", action="store_true", help="optional tabular second stage on dumped features")
    p.add_argument("--dump-features", action="store_true")
    p.add_argument("--variant", default="", help="M0-M6, default yaml")
    p.add_argument("--agg", default="", help="A0-A5, default yaml")
    p.add_argument("--ordinal", default="", help="O0-O3, default yaml")
    p.add_argument("--splits", default="val,test_prospective,test_external")
    p.add_argument("--gpu", type=int, default=1)
    p.add_argument("--epochs", type=int, default=0)
    p.add_argument("--limit-train", type=int, default=0)
    p.add_argument("--limit-eval", type=int, default=0)
    p.add_argument("--ckpt", default="")
    p.add_argument("--skip-locked", action="store_true", help="do not score prospective/external")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def load_cfg(args: argparse.Namespace | None = None) -> dict:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if args is not None:
        if args.variant:
            cfg["variant"] = args.variant
        if args.agg:
            cfg["aggregation"] = args.agg
        if args.ordinal:
            cfg["ordinal"] = args.ordinal
        if args.epochs:
            cfg["epochs"] = int(args.epochs)
    cfg["backbone"] = resolve_backbone_name(cfg.get("backbone"))
    return cfg


def split_csv(cfg: dict, name: str) -> Path:
    return ROOT / cfg["data_dir"] / f"{name}.csv"


def device_of(gpu: int) -> torch.device:
    if torch.cuda.is_available():
        return torch.device(f"cuda:{gpu}")
    return torch.device("cpu")


def attach_geom_stats(cfg: dict, *, max_rows: int = 0, cache: bool = True) -> None:
    """Train-fold geom mean/std. Val and test must reuse these values."""
    if not cfg.get("standardize_geom", True):
        cfg["geom_mean"] = None
        cfg["geom_std"] = None
        return
    if cfg.get("geom_mean") is not None and cfg.get("geom_std") is not None:
        return
    cache_path = REPORT / "geom_stats_train.npz"
    if cache and max_rows <= 0 and cache_path.is_file():
        packed = np.load(cache_path)
        cfg["geom_mean"] = packed["mean"]
        cfg["geom_std"] = packed["std"]
        print("geom_stats cached n=", int(packed["n"]), flush=True)
        return
    mean, std, n = compute_geom_stats(split_csv(cfg, "train"), max_rows=max_rows)
    cfg["geom_mean"] = mean
    cfg["geom_std"] = std
    if cache and max_rows <= 0:
        REPORT.mkdir(parents=True, exist_ok=True)
        np.savez(cache_path, mean=mean, std=std, n=n)
    print("geom_stats n=", n, "dim=", int(len(mean)), flush=True)


def make_loader(cfg: dict, split: str, is_train: bool, limit: int = 0, max_frames: int | None = None) -> DataLoader:
    ds = PatientBagGUSDataset(
        split_csv(cfg, split),
        max_frames=int(max_frames or cfg.get("max_frames", 10)),
        image_size=int(cfg.get("image_size", 384)),
        context_size=int(cfg.get("context_size", 384)),
        n_points=int(cfg.get("n_points", 24)),
        is_train=is_train,
        context_expand=float(cfg.get("context_expand", 0.45)),
        mask_perturb=is_train and cfg.get("variant") not in {"M0", "M5"},
        return_alt_mask=is_train and float(cfg.get("lambda_mask_cons", 0)) > 0,
        geom_mean=cfg.get("geom_mean"),
        geom_std=cfg.get("geom_std"),
        drop_invalid_geom=str(cfg.get("variant", "")) == "M5",
    )
    if limit:
        ds.patients = ds.patients[:limit]
    return DataLoader(
        ds,
        batch_size=int(cfg.get("batch_size", 2)) if is_train else 1,
        shuffle=is_train,
        num_workers=int(cfg.get("num_workers", 4)),
        pin_memory=True,
        collate_fn=gus_collate,
        drop_last=False,
    )


def preflight(cfg: dict) -> dict:
    report = {"pack": cfg["data_dir"], "backbone": cfg["backbone"], "splits": {}, "leaks": {}}
    ids = {}
    for name in SPLITS:
        path = split_csv(cfg, name)
        df = pd.read_csv(path)
        pids = set(df["patient_id"].astype(str))
        ids[name] = pids
        missing_img = 0
        missing_mask = 0
        for img, mask in zip(df["image_path"].astype(str), df["mask_path"].astype(str)):
            if _resolve_repo_path(img) is None:
                missing_img += 1
            if _resolve_repo_path(mask) is None:
                missing_mask += 1
        report["splits"][name] = {
            "rows": int(len(df)),
            "patients": int(len(pids)),
            "label_counts": {str(k): int(v) for k, v in df.groupby("patient_id")["label"].first().value_counts().items()},
            "missing_images": missing_img,
            "missing_masks": missing_mask,
            "expected_patients": LOCKED.get(name),
        }
    report["leaks"]["train_val"] = len(ids["train"] & ids["val"])
    report["leaks"]["train_prosp"] = len(ids["train"] & ids["test_prospective"])
    report["leaks"]["train_ext"] = len(ids["train"] & ids["test_external"])
    report["leaks"]["val_prosp"] = len(ids["val"] & ids["test_prospective"])
    report["ok"] = (
        all(v == 0 for v in report["leaks"].values())
        and all(b["missing_images"] == 0 and b["missing_masks"] == 0 for b in report["splits"].values())
        and report["splits"]["test_prospective"]["patients"] == 425
        and report["splits"]["test_external"]["patients"] == 485
    )
    return report


def print_plan(cfg: dict) -> None:
    cov = preflight(cfg)
    plan = {
        "model": "GUS-Mask2Stage",
        "core_inputs": ["doctor keyframes", "lesion mask"],
        "excluded": ["clinical fields", "similar-case labels", "doctor first impression"],
        "backbone": cfg["backbone"],
        "default_variant": f"{cfg['variant']}/{cfg['aggregation']}/{cfg['ordinal']}",
        "geom": {
            "dim": 12,
            "from": "clean_full_mask_before_aug",
            "names": list(GEOM_NAMES),
            "standardize": "train_fold_mean_std",
        },
        "phases": {
            "0": "live mask-pool CORAL checkpoint, single vs multi-frame aggregation",
            "1": "mask usage M0-M6",
            "2": "aggregation A0-A5 on a locked visual checkpoint",
            "3": "ordinal head O0-O3",
            "4": "optional OOF tabular fusion, only if it beats MLP/CatBoost",
        },
        "preflight": cov,
    }
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(plan, indent=2, ensure_ascii=False))


@torch.no_grad()
def predict_loader(model, loader, device, cfg) -> tuple[pd.DataFrame, pd.DataFrame]:
    model.eval()
    patient_rows = []
    frame_rows = []
    for batch in tqdm(loader, desc="predict", leave=False):
        batch = move_batch(batch, device)
        out = model(batch)
        probs = out["probs"].float().cpu().numpy()
        y = batch["label"].cpu().numpy()
        pids = batch["patient_id"]
        ev = out["frame_evidence"].float().cpu().numpy()
        valid = batch["valid"].cpu().numpy()
        area = batch["area"].cpu().numpy()
        bottleneck = out["bottleneck"].float().cpu().numpy()
        for i, pid in enumerate(pids):
            patient_rows.append({
                "patient_id": str(pid),
                "y_true": int(y[i]),
                "y_pred": int(probs[i].argmax()),
                "p_t1": float(probs[i, 0]),
                "p_t2": float(probs[i, 1]),
                "p_t3": float(probs[i, 2]),
                "p_t4": float(probs[i, 3]),
                "q_t2": float(out["q"][i, 0].cpu()),
                "q_t3": float(out["q"][i, 1].cpu()),
                "q_t4": float(out["q"][i, 2].cpu()),
                "n_frames": int(valid[i].sum()),
                **{f"z{k}": float(bottleneck[i, k]) for k in range(min(32, bottleneck.shape[1]))},
            })
            for t in range(valid.shape[1]):
                if not valid[i, t]:
                    continue
                frame_rows.append({
                    "patient_id": str(pid),
                    "y_true": int(y[i]),
                    "frame_index": int(t),
                    "area": float(area[i, t]),
                    "u_t2": float(ev[i, t, 0]),
                    "u_t3": float(ev[i, t, 1]),
                    "u_t4": float(ev[i, t, 2]),
                    "p_t1": float("nan"),
                    "p_t2": float("nan"),
                    "p_t3": float("nan"),
                    "p_t4": float("nan"),
                })
    pat = pd.DataFrame(patient_rows)
    frm = pd.DataFrame(frame_rows)
    if len(pat):
        pat.attrs["metrics"] = score_predictions(
            pat["y_true"].to_numpy(),
            pat[["p_t1", "p_t2", "p_t3", "p_t4"]].to_numpy(),
        )
    return pat, frm


def write_split_scores(model, cfg, device, splits: list[str], tag: str, limit: int = 0) -> dict:
    attach_geom_stats(cfg)
    scores = {}
    REPORT.mkdir(parents=True, exist_ok=True)
    for split in splits:
        loader = make_loader(cfg, split, is_train=False, limit=limit)
        pat, frm = predict_loader(model, loader, device, cfg)
        metrics = dict(pat.attrs.get("metrics", {}))
        if split in LOCKED:
            metrics["expected_n"] = LOCKED[split]
            metrics["complete"] = metrics.get("n") == LOCKED[split]
        pat.to_csv(REPORT / f"{tag}_{split}_patients.csv", index=False)
        frm.to_csv(REPORT / f"{tag}_{split}_frames.csv", index=False)
        (REPORT / f"{tag}_{split}_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        scores[split] = metrics
        print({"eval": split, "tag": tag, **metrics}, flush=True)
    (REPORT / f"{tag}_scores.json").write_text(json.dumps(scores, indent=2), encoding="utf-8")
    return scores


def count_params(model) -> dict:
    return {
        "trainable": int(sum(p.numel() for p in model.parameters() if p.requires_grad)),
        "frozen": int(sum(p.numel() for p in model.parameters() if not p.requires_grad)),
        "total": int(sum(p.numel() for p in model.parameters())),
    }


def run_smoke(cfg: dict, device: torch.device) -> None:
    geom_check = geom_sanity_check()
    print("geom_sanity", geom_check, flush=True)
    attach_geom_stats(cfg, max_rows=80, cache=False)
    loader = make_loader(cfg, "val", is_train=False, limit=2, max_frames=3)
    model = build_gus_model(cfg, device)
    model.eval()
    batch = move_batch(next(iter(loader)), device)
    with torch.no_grad():
        out = model(batch)
    print("smoke ok")
    print("full_rgb", tuple(batch["full_rgb"].shape))
    print("ctx_rgb", tuple(batch["ctx_rgb"].shape))
    print("ctx_mask", tuple(batch["ctx_mask"].shape))
    print("radial_xy", tuple(batch["radial_xy"].shape))
    print("full_sdf", tuple(batch["full_sdf"].shape), "ctx_sdf", tuple(batch["ctx_sdf"].shape))
    print("valid", batch["valid"][0].tolist(), "n_frames", int(batch["n_frames"][0]))
    print("geom", tuple(batch["geom"].shape), "geom_valid", batch["geom_valid"][0].tolist())
    if bool(batch["geom_valid"][0, 0]):
        print("geom0", {n: float(batch["geom"][0, 0, i]) for i, n in enumerate(GEOM_NAMES)})
    d = torch.linspace(-0.6, 0.7, 14).view(1, 1, 1, 14)
    bands = sigmoid_region_weights_from_d(d)
    print("region_band_mass", [float(bands[0, i].sum()) for i in range(4)])
    print("probs", tuple(out["probs"].shape), out["probs"][0].tolist())
    print("q", out["q"][0].tolist())
    print("frame_evidence", tuple(out["frame_evidence"].shape))
    print("params", count_params(model))
    if device.type == "cuda":
        print("vram_mb", round(torch.cuda.max_memory_allocated(device) / 1024 ** 2))
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "smoke.json").write_text(json.dumps({
        "probs": [float(x) for x in out["probs"][0].cpu()],
        "q": [float(x) for x in out["q"][0].cpu()],
        "params": count_params(model),
        "backbone": cfg["backbone"],
        "geom_dim": int(batch["geom"].shape[-1]),
        "geom_sanity": geom_check,
    }, indent=2), encoding="utf-8")


class _EMA:
    def __init__(self, model: torch.nn.Module, decay: float = 0.999):
        self.decay = decay
        self.shadow = {k: v.detach().clone() for k, v in model.state_dict().items() if v.dtype.is_floating_point}

    def update(self, model: torch.nn.Module) -> None:
        for k, v in model.state_dict().items():
            if k in self.shadow and v.dtype.is_floating_point:
                self.shadow[k].mul_(self.decay).add_(v.detach(), alpha=1.0 - self.decay)

    def copy_to(self, model: torch.nn.Module) -> dict:
        raw = {k: v.detach().clone() for k, v in model.state_dict().items()}
        model.load_state_dict({**raw, **self.shadow}, strict=False)
        return raw


def run_train(cfg: dict, args: argparse.Namespace, device: torch.device) -> Path:
    set_seed(int(cfg.get("seed", 20260826)))
    attach_geom_stats(cfg)
    REPORT.mkdir(parents=True, exist_ok=True)
    tag = f"{cfg['variant']}_{cfg['aggregation']}_{cfg['ordinal']}"
    ckpt_path = REPORT / f"best_{tag}.pth"
    train_loader = make_loader(cfg, "train", is_train=True, limit=args.limit_train)
    val_loader = make_loader(cfg, "val", is_train=False, limit=args.limit_eval)
    model = build_gus_model(cfg, device)
    model.set_unfreeze(1)
    train_y = pd.read_csv(split_csv(cfg, "train")).groupby("patient_id")["label"].first().to_numpy()
    cfg["ordinal_pn_weights"] = fold_ordinal_pn_weights(train_y)
    print("ordinal_pn_weights", cfg["ordinal_pn_weights"].tolist(), flush=True)
    opt = torch.optim.AdamW(param_groups(model, cfg), weight_decay=float(cfg.get("weight_decay", 0.05)))
    epochs = int(cfg.get("epochs", 80))
    warmup = int(cfg.get("warmup_epochs", 5))
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(epochs - warmup, 1))
    amp_on = device.type == "cuda" and bool(cfg.get("amp", True))
    try:
        scaler = torch.amp.GradScaler("cuda", enabled=amp_on)
        autocast_ctx = lambda: torch.amp.autocast("cuda", enabled=amp_on)
    except TypeError:
        scaler = torch.cuda.amp.GradScaler(enabled=amp_on)
        autocast_ctx = lambda: torch.cuda.amp.autocast(enabled=amp_on)
    ema = _EMA(model, float(cfg.get("ema_decay", 0.999))) if cfg.get("ema", True) else None
    accum = max(1, int(cfg.get("gradient_accumulation", 6)))
    best = -1.0
    bad = 0
    history = []
    print("train", tag, "params", count_params(model), "patients", len(train_loader.dataset), flush=True)
    opt.zero_grad(set_to_none=True)
    for epoch in range(1, epochs + 1):
        mode = model.set_unfreeze(epoch)
        model.train()
        losses = []
        for step, batch in enumerate(train_loader, start=1):
            batch = move_batch(batch, device)
            if int(batch["valid"].sum()) == 0:
                continue
            with autocast_ctx():
                out = model(batch)
                out_alt = None
                if "alt_ctx_mask" in batch and float(cfg.get("lambda_mask_cons", 0)) > 0:
                    out_alt = model(batch, use_alt_mask=True)
                loss_d = gus_loss(out, batch["label"], cfg, out_alt, valid=batch["valid"])
                loss = loss_d["loss"] / accum
            scaler.scale(loss).backward()
            losses.append(float(loss_d["loss"].detach().cpu()))
            if step % accum == 0:
                scaler.unscale_(opt)
                torch.nn.utils.clip_grad_norm_(model.parameters(), float(cfg.get("grad_clip", 1.0)))
                scaler.step(opt)
                scaler.update()
                opt.zero_grad(set_to_none=True)
                if ema is not None:
                    ema.update(model)
        if epoch > warmup:
            sched.step()
        raw = None
        if ema is not None:
            raw = ema.copy_to(model)
        pat, _ = predict_loader(model, val_loader, device, cfg)
        metrics = dict(pat.attrs.get("metrics", {}))
        if raw is not None:
            model.load_state_dict(raw, strict=False)
        row = {"epoch": epoch, "unfreeze": mode, "train_loss": float(np.mean(losses) if losses else 0.0), **metrics}
        history.append(row)
        print(row, flush=True)
        qwk = float(metrics.get("qwk", -1))
        if qwk > best:
            best = qwk
            bad = 0
            state = ema.shadow if ema is not None else model.state_dict()
            torch.save({
                "model_state_dict": {k: v.cpu() for k, v in state.items()},
                "config": cfg,
                "epoch": epoch,
                "val": metrics,
                "tag": tag,
            }, ckpt_path)
            pat.to_csv(REPORT / f"best_{tag}_val_patients.csv", index=False)
        else:
            bad += 1
        (REPORT / f"history_{tag}.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
        if bad >= int(cfg.get("early_stopping", 12)):
            print("early stop", epoch, "best_qwk", best, flush=True)
            break
    print("wrote", ckpt_path, "best_qwk", best, flush=True)
    return ckpt_path


def load_trained(cfg: dict, device: torch.device, ckpt: Path) -> torch.nn.Module:
    blob = torch.load(ckpt, map_location=device, weights_only=False)
    saved_cfg = dict(cfg)
    if isinstance(blob, dict) and "config" in blob:
        saved_cfg.update({k: blob["config"][k] for k in ("variant", "aggregation", "ordinal", "backbone") if k in blob["config"]})
    model = build_gus_model(saved_cfg, device)
    state = blob["model_state_dict"] if isinstance(blob, dict) and "model_state_dict" in blob else blob
    model.load_state_dict(state, strict=False)
    model.eval()
    return model


def default_ckpt(cfg: dict, explicit: str) -> Path:
    if explicit:
        path = Path(explicit)
        return path if path.is_absolute() else ROOT / path
    tag = f"{cfg['variant']}_{cfg['aggregation']}_{cfg['ordinal']}"
    return REPORT / f"best_{tag}.pth"


def run_eval(cfg: dict, args: argparse.Namespace, device: torch.device) -> None:
    ckpt = default_ckpt(cfg, args.ckpt)
    if not ckpt.exists():
        raise SystemExit(f"missing {ckpt}; train first")
    model = load_trained(cfg, device, ckpt)
    splits = [s.strip() for s in args.splits.split(",") if s.strip()]
    if args.skip_locked:
        splits = [s for s in splits if s not in LOCKED]
    tag = ckpt.stem
    write_split_scores(model, cfg, device, splits, tag=tag, limit=args.limit_eval)


# ---------------------------------------------------------------------------
# Phase 0: existing live T-stage checkpoint, no retrain
# ---------------------------------------------------------------------------

def _clinical18(row, missing_all: bool = False) -> torch.Tensor:
    if missing_all:
        vec = []
        for i, col in enumerate(PREOP18):
            vec.append(1.0 if col.endswith("_missing") else 0.0)
        return torch.tensor(vec, dtype=torch.float32)
    vec = []
    for col in PREOP18:
        val = row.get(col, 0.0)
        vec.append(0.0 if pd.isna(val) else float(val))
    return torch.tensor(vec, dtype=torch.float32)


@torch.no_grad()
def infer_existing_split(cfg: dict, split: str, device: torch.device, drop_clinical: bool) -> pd.DataFrame:
    from PIL import Image

    ckpt = ROOT / cfg["existing_t_ckpt"]
    yaml_cfg = yaml.safe_load((ROOT / cfg["existing_t_yaml"]).read_text(encoding="utf-8"))
    model = MaskPooledOrdinalClassifier(
        backbone_name=yaml_cfg.get("backbone", "convnext_tiny.fb_in22k_ft_in1k"),
        pretrained=False,
        image_size=int(yaml_cfg.get("global_size", 384)),
        dropout=float(yaml_cfg.get("dropout", 0.3)),
        num_classes=3,
        clinical_dim=int(yaml_cfg.get("clinical_dim", 18)),
        clinical_hidden=int(yaml_cfg.get("clinical_hidden", 64)),
        head_hidden=int(yaml_cfg.get("head_hidden", 256)),
        lesion_region_kernel=int(yaml_cfg.get("lesion_region_kernel", 5)),
        drop_path_rate=float(yaml_cfg.get("drop_path_rate", 0.1)),
        pool_mode=str(yaml_cfg.get("pool_mode", "mask_regions")),
    ).to(device)
    blob = torch.load(ckpt, map_location=device, weights_only=False)
    state = blob.get("model_state_dict", blob)
    model.load_state_dict(state, strict=False)
    model.eval()
    transform = get_val_transforms(int(yaml_cfg.get("global_size", 384)))
    df = pd.read_csv(split_csv(cfg, split))
    rows = []
    for _, row in tqdm(df.iterrows(), total=len(df), desc=f"phase0 {split}", leave=False):
        img_path = _resolve_repo_path(row.get("image_path", ""))
        mask_path = _resolve_repo_path(row.get("mask_path", ""))
        if img_path is None:
            continue
        image = Image.open(img_path).convert("RGB")
        rgb = transform(image)
        if mask_path is not None:
            mask = Image.open(mask_path).convert("L").resize((rgb.size(-1), rgb.size(-1)), Image.NEAREST)
            marr = np.array(mask, dtype=np.float32)
            if marr.max() > 1:
                marr = marr / 255.0
            mten = torch.from_numpy((marr > 0.5).astype(np.float32)).unsqueeze(0)
        else:
            mten = torch.zeros(1, rgb.size(-1), rgb.size(-1))
        x = torch.cat([rgb, mten], dim=0).unsqueeze(0).to(device)
        clin = _clinical18(row, missing_all=drop_clinical).unsqueeze(0).to(device)
        logits = model(x, None, clin)
        probs = legacy_coral_to_probs(logits)[0].cpu().numpy()
        rows.append({
            "patient_id": str(row["patient_id"]),
            "y_true": int(row["label"]),
            "p_t1": float(probs[0]),
            "p_t2": float(probs[1]),
            "p_t3": float(probs[2]),
            "p_t4": float(probs[3]),
            "area": float(mten.sum().cpu()),
            "source": str(row.get("source", "")),
        })
    return pd.DataFrame(rows)


def run_phase0(cfg: dict, args: argparse.Namespace, device: torch.device) -> None:
    REPORT.mkdir(parents=True, exist_ok=True)
    splits = [s.strip() for s in args.splits.split(",") if s.strip()]
    if args.skip_locked:
        splits = [s for s in splits if s not in LOCKED]
    summary = {}
    for split in splits:
        frames = infer_existing_split(cfg, split, device, drop_clinical=False)
        frames_noclin = infer_existing_split(cfg, split, device, drop_clinical=True)
        frames.to_csv(REPORT / f"phase0_{split}_frames.csv", index=False)
        modes = {
            "B0_first_frame": "B0",
            "B1a_star_or_area": "B1a",
            "B1b_largest_mask": "B1b",
            "B1c_max_expected_rank": "B1c",
            "B2_mean": "B2",
            "B3_threshold_topk_mean": "B3",
            "B3_threshold_max": "B3-max",
        }
        split_scores = {}
        for name, mode in modes.items():
            pat = reaggregate_frame_probs(frames, mode)
            metrics = score_predictions(pat["y_true"].to_numpy(), pat[["p_t1", "p_t2", "p_t3", "p_t4"]].to_numpy())
            pat.to_csv(REPORT / f"phase0_{split}_{name}.csv", index=False)
            split_scores[name] = metrics
            print({"phase0": split, "mode": name, **metrics}, flush=True)
        pat_nc = reaggregate_frame_probs(frames_noclin, "B3")
        split_scores["B4_no_clinical_B3"] = score_predictions(
            pat_nc["y_true"].to_numpy(), pat_nc[["p_t1", "p_t2", "p_t3", "p_t4"]].to_numpy()
        )
        summary[split] = split_scores
    (REPORT / "phase0_scores.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("phase0 wrote", REPORT / "phase0_scores.json")


# ---------------------------------------------------------------------------
# Phases 1-4
# ---------------------------------------------------------------------------

def run_phase_matrix(cfg: dict, args: argparse.Namespace, device: torch.device, key: str, values: tuple[str, ...]) -> None:
    base = dict(cfg)
    matrix = {}
    for value in values:
        cfg_i = dict(base)
        cfg_i[key] = value
        if key == "variant":
            args.variant = value
        if key == "aggregation":
            args.agg = value
        if key == "ordinal":
            args.ordinal = value
        print("=== train", key, value, flush=True)
        if args.dry_run:
            matrix[value] = {"skipped": "dry-run"}
            continue
        ckpt = run_train(cfg_i, args, device)
        model = load_trained(cfg_i, device, ckpt)
        splits = ["val"] if args.skip_locked else ["val", "test_prospective", "test_external"]
        matrix[value] = write_split_scores(model, cfg_i, device, splits, tag=ckpt.stem, limit=args.limit_eval)
    (REPORT / f"phase_{key}_matrix.json").write_text(json.dumps(matrix, indent=2), encoding="utf-8")


def run_phase2_locked(cfg: dict, args: argparse.Namespace, device: torch.device) -> None:
    """Re-aggregate a locked visual checkpoint; no retrain except reporting A3 from saved frames if present."""
    attach_geom_stats(cfg)
    ckpt = default_ckpt(cfg, args.ckpt)
    if not ckpt.exists():
        raise SystemExit(f"phase2 needs {ckpt}")
    model = load_trained(cfg, device, ckpt)
    splits = [s.strip() for s in args.splits.split(",") if s.strip()]
    if args.skip_locked:
        splits = [s for s in splits if s not in LOCKED]
    summary = {}
    for split in splits:
        loader = make_loader(cfg, split, is_train=False, limit=args.limit_eval)
        pat_model, frm = predict_loader(model, loader, device, cfg)
        # Reconstruct crude per-frame class probs from patient q is not available;
        # use the model's native patient output as A4, and re-run with swapped agg.
        split_scores = {"A4_native": dict(pat_model.attrs.get("metrics", {}))}
        for agg in AGG_VARIANTS:
            cfg_i = dict(cfg)
            cfg_i["aggregation"] = agg
            cfg_i["use_star"] = agg == "A5"
            model_i = build_gus_model(cfg_i, device)
            blob = torch.load(ckpt, map_location=device, weights_only=False)
            model_i.load_state_dict(blob["model_state_dict"], strict=False)
            model_i.eval()
            pat, _ = predict_loader(model_i, loader, device, cfg_i)
            split_scores[agg] = dict(pat.attrs.get("metrics", {}))
            pat.to_csv(REPORT / f"phase2_{split}_{agg}.csv", index=False)
            print({"phase2": split, "agg": agg, **split_scores[agg]}, flush=True)
        summary[split] = split_scores
        frm.to_csv(REPORT / f"phase2_{split}_frames.csv", index=False)
    (REPORT / "phase2_scores.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def _feature_table(pat: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    cols = ["p_t1", "p_t2", "p_t3", "p_t4", "q_t2", "q_t3", "q_t4", "n_frames"]
    zcols = [c for c in pat.columns if c.startswith("z")]
    x = pat[cols + zcols].to_numpy(dtype=np.float64)
    y = pat["y_true"].to_numpy(dtype=int)
    return x, y


def run_phase4(cfg: dict, args: argparse.Namespace) -> None:
    """Second-stage fusion on already-dumped visual OOF/val tables. No image forward."""
    val_path = REPORT / f"best_{cfg['variant']}_{cfg['aggregation']}_{cfg['ordinal']}_val_patients.csv"
    if args.ckpt:
        stem = Path(args.ckpt).stem
        val_path = REPORT / f"{stem}_val_patients.csv"
        if not val_path.exists():
            val_path = REPORT / f"best_{cfg['variant']}_{cfg['aggregation']}_{cfg['ordinal']}_val_patients.csv"
    if not val_path.exists():
        raise SystemExit(f"phase4 needs dumped visual table {val_path}; run --train or --eval first")
    val = pd.read_csv(val_path)
    x_val, y_val = _feature_table(val)
    from sklearn.linear_model import LogisticRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.model_selection import StratifiedKFold
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    x_val_s = scaler.fit_transform(x_val)
    models = {
        "F1_logreg": LogisticRegression(max_iter=400, class_weight="balanced"),
        "F1_mlp": MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=400, random_state=20260826),
    }
    try:
        from catboost import CatBoostClassifier
        models["F2_catboost"] = CatBoostClassifier(depth=4, iterations=200, verbose=False, loss_function="MultiClass")
    except Exception:
        pass
    try:
        from tabpfn import TabPFNClassifier
        models["F3_tabpfn"] = TabPFNClassifier()
    except Exception:
        pass

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=20260826)
    matrix = {"note": "Fit on official val only. This is a diagnostic second stage, not nested OOF of the visual net."}
    for name, clf in models.items():
        oof = np.zeros((len(y_val), 4), dtype=np.float64)
        ok = True
        for tr, te in skf.split(x_val_s, y_val):
            try:
                clf.fit(x_val_s[tr], y_val[tr])
                if hasattr(clf, "predict_proba"):
                    oof[te] = clf.predict_proba(x_val_s[te])
                else:
                    pred = clf.predict(x_val_s[te])
                    oof[te] = np.eye(4)[pred]
            except Exception as exc:
                matrix[name] = {"error": str(exc)}
                ok = False
                break
        if ok:
            matrix[name] = score_predictions(y_val, oof)
            print({"phase4": name, **matrix[name]}, flush=True)
    # apply locked visual vs best second stage on sealed tests if tables exist
    for split in ("test_prospective", "test_external"):
        path = REPORT / f"best_{cfg['variant']}_{cfg['aggregation']}_{cfg['ordinal']}_{split}_patients.csv"
        if not path.exists():
            continue
        te = pd.read_csv(path)
        x_te, y_te = _feature_table(te)
        x_te_s = scaler.transform(x_te)
        split_block = {"F0_visual": score_predictions(y_te, te[["p_t1", "p_t2", "p_t3", "p_t4"]].to_numpy())}
        for name, clf in models.items():
            if name in matrix and "error" in matrix[name]:
                continue
            try:
                clf.fit(x_val_s, y_val)
                proba = clf.predict_proba(x_te_s)
                split_block[name] = score_predictions(y_te, proba)
            except Exception as exc:
                split_block[name] = {"error": str(exc)}
        matrix[split] = split_block
        print({"phase4_locked": split, **{k: v.get("qwk") if isinstance(v, dict) else v for k, v in split_block.items()}}, flush=True)
    (REPORT / "phase4_scores.json").write_text(json.dumps(matrix, indent=2), encoding="utf-8")
    print("phase4 wrote", REPORT / "phase4_scores.json")
    print("TabICL is not used. LimiX is not used unless a later clinical-missing pack is added.")


def main() -> None:
    args = parse_args()
    cfg = load_cfg(args)
    if not any([
        args.plan, args.preflight, args.smoke, args.phase0, args.train, args.eval,
        args.phase1, args.phase2, args.phase3, args.phase4, args.dump_features,
    ]):
        raise SystemExit("choose --plan / --preflight / --smoke / --phase0 / --train / --eval / --phase1-4")
    if args.plan:
        print_plan(cfg)
        return
    if args.preflight:
        report = preflight(cfg)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        REPORT.mkdir(parents=True, exist_ok=True)
        (REPORT / "preflight.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        if not report["ok"]:
            raise SystemExit("preflight failed")
        return
    if args.dry_run and args.train:
        print(json.dumps({"would_train": True, **{k: cfg[k] for k in ("variant", "aggregation", "ordinal", "backbone", "epochs")}}, indent=2))
        return
    device = device_of(args.gpu)
    if args.smoke:
        run_smoke(cfg, device)
        return
    if args.phase0:
        run_phase0(cfg, args, device)
        return
    if args.train:
        run_train(cfg, args, device)
        return
    if args.eval or args.dump_features:
        run_eval(cfg, args, device)
        return
    if args.phase1:
        run_phase_matrix(cfg, args, device, "variant", MASK_VARIANTS)
        return
    if args.phase2:
        run_phase2_locked(cfg, args, device)
        return
    if args.phase3:
        run_phase_matrix(cfg, args, device, "ordinal", ORD_VARIANTS)
        return
    if args.phase4:
        run_phase4(cfg, args)
        return


if __name__ == "__main__":
    main()
