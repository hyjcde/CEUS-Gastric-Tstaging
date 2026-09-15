#!/usr/bin/env python3
"""Score ROI LoRA+MLP T-staging checkpoints on the ZML reader 100-case frozen test set.

Case-level aggregation = mean of frame probs -> argmax (same as training patient_metrics).
Also scores doctor zml_ct on the same cases for context.

Usage:
  python3 scripts/score_zml_roi_cls.py \
      --ckpt gentle=pipeline/experiments/reports/dinov3_roi_lora_mlp/us_ssl_v2_gentle_20260915/best_roi_lora_mlp.pt \
      --output-dir pipeline/experiments/reports/dinov3_roi_lora_mlp/zml100_eval_20260915
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
from PIL import Image
from sklearn.metrics import accuracy_score, cohen_kappa_score, confusion_matrix
from torch.utils.data import DataLoader, Dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from train_dinov3_roi_lora_mlp import (  # noqa: E402
    CLASS_NAMES,
    IMAGENET_MEAN,
    IMAGENET_STD,
    RoiLoraMlp,
    apply_gaussian_blur,
    inject_lora,
    letterbox_rgb,
    load_timm_mae_backbone,
    patient_metrics,
)

LABEL_MAP = {"T1": 0, "T2": 1, "T3": 2, "T4": 3, "T4+": 3}
DEFAULT_FRAMES = PROJECT_ROOT / "pipeline/data/zml_reader_100_testset_20260915/frames.csv"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ckpt", nargs="+", required=True, metavar="LABEL=PATH")
    p.add_argument("--frames-csv", type=Path, default=DEFAULT_FRAMES)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--device", default="cuda:0" if torch.cuda.is_available() else "cpu")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--num-workers", type=int, default=4)
    return p.parse_args()


def resolve_path(value: object) -> Path | None:
    if value is None or not str(value).strip():
        return None
    path = Path(str(value))
    if path.exists():
        return path
    cand = PROJECT_ROOT / path
    return cand if cand.exists() else None


def build_model_from_ckpt(ckpt_path: Path, device: torch.device) -> tuple[torch.nn.Module, float]:
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    args = dict(ckpt.get("config", {}))  # vars(args) from training
    yaml_cfg: dict = {}
    cfg_path = resolve_path(args.get("config"))
    if cfg_path is not None:
        yaml_cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    model_cfg = yaml_cfg.get("model", {})
    paths_cfg = yaml_cfg.get("paths", {})
    family = str(model_cfg.get("backbone_family", "dinov3"))

    if family == "timm_mae":
        weights = resolve_path(paths_cfg.get("checkpoint_path"))
        backbone = load_timm_mae_backbone(model_cfg, weights)
    else:
        repo = resolve_path(paths_cfg.get("dinov3_repo"))
        weights = resolve_path(paths_cfg.get("checkpoint_path"))
        hub_model = str(model_cfg.get("hub_model", "dinov3_vitb16"))
        if repo is None:
            raise FileNotFoundError(f"dinov3_repo not found (from {cfg_path})")
        backbone = torch.hub.load(str(repo), hub_model, source="local", weights=str(weights) if weights else None)

    inject_lora(
        backbone,
        int(args.get("lora_blocks", 4)),
        int(args.get("lora_rank", 8)),
        float(args.get("lora_alpha", 16.0)),
        float(args.get("lora_dropout") or 0.0),
        train_norms=True,
    )
    model = RoiLoraMlp(
        backbone,
        embed_dim=int(ckpt.get("embed_dim", 768)),
        hidden_dim=int(args.get("mlp_hidden", 512)),
        dropout=0.0,
        class_count=len(ckpt.get("class_names", CLASS_NAMES)),
    )
    missing, unexpected = model.load_state_dict(ckpt["model_state_dict"], strict=False)
    if missing or unexpected:
        raise RuntimeError(f"state_dict mismatch: missing={missing[:4]} unexpected={unexpected[:4]}")
    blur_sigma = float(args.get("input_blur_sigma") or model_cfg.get("input_blur_sigma") or 0.0)
    return model.to(device).eval(), blur_sigma


class ZmlRoiDataset(Dataset):
    def __init__(self, df: pd.DataFrame, image_size: int, blur_sigma: float) -> None:
        self.df = df.reset_index(drop=True)
        self.image_size = int(image_size)
        self.blur_sigma = float(blur_sigma)

    def __len__(self) -> int:
        return len(self.df)

    def __getitem__(self, index: int) -> dict:
        row = self.df.iloc[index]
        image = Image.open(row["roi_path"]).convert("RGB")
        if self.blur_sigma > 0:
            image = apply_gaussian_blur(image, self.blur_sigma)
        image = letterbox_rgb(image, self.image_size)
        arr = np.asarray(image, dtype=np.float32) / 255.0
        arr = (arr - IMAGENET_MEAN) / IMAGENET_STD
        return {
            "image": torch.from_numpy(arr).permute(2, 0, 1).contiguous(),
            "label": int(row["class_label"]),
            "patient_id": str(row["case_id"]),
            "sample_id": str(row["frame_id"]),
        }


def collate(batch: list[dict]) -> dict:
    return {
        "images": torch.stack([b["image"] for b in batch]),
        "labels": torch.tensor([b["label"] for b in batch], dtype=torch.long),
        "patient_ids": [b["patient_id"] for b in batch],
        "sample_ids": [b["sample_id"] for b in batch],
    }


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    device = torch.device(args.device)

    frames = pd.read_csv(args.frames_csv, low_memory=False)
    frames = frames[frames["roi_path"].notna()].copy()
    frames["roi_path"] = frames["roi_path"].map(lambda p: str(resolve_path(p) or ""))
    frames = frames[frames["roi_path"].ne("")].reset_index(drop=True)
    frames["class_label"] = frames["gold_t"].map(LABEL_MAP)
    if frames["class_label"].isna().any():
        raise ValueError("unmapped gold_t values")
    frames["class_label"] = frames["class_label"].astype(int)
    print(f"[zml] usable ROI frames: {len(frames)}, cases: {frames['case_id'].nunique()}", flush=True)

    # doctor reference (case level)
    doc = frames.groupby("case_id")["zml_ct"].first().dropna().map(LABEL_MAP)

    summary: dict[str, object] = {"n_frames": int(len(frames)), "n_cases": int(frames["case_id"].nunique())}
    for spec in args.ckpt:
        label, _, path = spec.partition("=")
        ckpt_path = resolve_path(path)
        if ckpt_path is None:
            raise FileNotFoundError(path)
        model, blur_sigma = build_model_from_ckpt(ckpt_path, device)
        print(f"[zml] scoring {label} (blur_sigma={blur_sigma}) ...", flush=True)

        ds = ZmlRoiDataset(frames, image_size=512, blur_sigma=blur_sigma)
        loader = DataLoader(ds, batch_size=args.batch_size, shuffle=False,
                            num_workers=args.num_workers, collate_fn=collate)
        rows: list[dict] = []
        with torch.no_grad():
            for batch in loader:
                logits = model(batch["images"].to(device))
                probs = torch.softmax(logits.float(), dim=1).cpu().numpy()
                for i in range(len(batch["patient_ids"])):
                    row = {"patient_id": batch["patient_ids"][i], "sample_id": batch["sample_ids"][i],
                           "class_label": int(batch["labels"][i])}
                    for ci, name in enumerate(CLASS_NAMES):
                        row[f"prob_{name}"] = float(probs[i, ci])
                    rows.append(row)
        frame_df = pd.DataFrame(rows)
        frame_df.to_csv(args.output_dir / f"zml100_{label}_frame_predictions.csv", index=False)

        metrics = patient_metrics(frame_df)
        prob_cols = [f"prob_{n}" for n in CLASS_NAMES]
        case = frame_df.groupby("patient_id", sort=False)
        case_df = case[prob_cols].mean()
        case_df["class_label"] = case["class_label"].first()
        case_df["pred"] = case_df[prob_cols].to_numpy().argmax(axis=1)
        case_df["zml_ct"] = doc
        case_df.to_csv(args.output_dir / f"zml100_{label}_case_predictions.csv")

        cm = confusion_matrix(case_df["class_label"], case_df["pred"], labels=[0, 1, 2, 3])
        per_class_recall = np.diag(cm) / np.maximum(cm.sum(axis=1), 1)
        entry = {
            "case_acc": float(metrics["accuracy"]),
            "case_qwk": float(metrics["quadratic_kappa"]),
            "case_auc_macro_ovr": float(metrics["auc_macro_ovr"]),
            "case_mae": float(metrics["mae"]),
            "case_off_by_one": float(metrics["off_by_one"]),
            "per_class_recall": {n: float(per_class_recall[i]) for i, n in enumerate(CLASS_NAMES)},
            "confusion": cm.tolist(),
            "n_cases": int(len(case_df)),
            "blur_sigma": blur_sigma,
        }
        summary[label] = entry
        print(f"[zml] {label}: acc={entry['case_acc']:.3f} qwk={entry['case_qwk']:.3f} "
              f"auc={entry['case_auc_macro_ovr']:.3f} recall={entry['per_class_recall']}", flush=True)
        del model
        torch.cuda.empty_cache()

    # doctor metrics on the same cases
    gold = frames.groupby("case_id")["class_label"].first()
    common = gold.index.intersection(doc.index)
    if len(common):
        d_acc = accuracy_score(gold.loc[common], doc.loc[common])
        d_qwk = cohen_kappa_score(gold.loc[common], doc.loc[common], weights="quadratic")
        d_cm = confusion_matrix(gold.loc[common], doc.loc[common], labels=[0, 1, 2, 3])
        d_recall = np.diag(d_cm) / np.maximum(d_cm.sum(axis=1), 1)
        summary["doctor_zml"] = {
            "case_acc": float(d_acc), "case_qwk": float(d_qwk),
            "per_class_recall": {n: float(d_recall[i]) for i, n in enumerate(CLASS_NAMES)},
            "confusion": d_cm.tolist(), "n_cases": int(len(common)),
        }
        print(f"[zml] doctor zml: acc={d_acc:.3f} qwk={d_qwk:.3f}", flush=True)

    (args.output_dir / "zml100_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[zml] summary -> {args.output_dir / 'zml100_summary.json'}", flush=True)


if __name__ == "__main__":
    main()
