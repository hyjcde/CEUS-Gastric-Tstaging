#!/usr/bin/env python3
"""Autopsy of GUS O3 decode on the epoch-12 val dump. No training.

Reads best_M4_A4_O3_val_patients.csv, then optionally re-forwards the
checkpoint to inspect frame-level Top-K overlap.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "pipeline/experiments/reports/gus_mask2stage_20260826"
if str(ROOT / "pipeline") not in sys.path:
    sys.path.insert(0, str(ROOT / "pipeline"))

from lib.gus_mask2stage import quadratic_weighted_kappa  # noqa: E402


def _metrics(y: np.ndarray, pred: np.ndarray, probs: np.ndarray) -> dict:
    rec = []
    for c in range(4):
        mask = y == c
        rec.append(float((pred[mask] == c).mean()) if mask.any() else 0.0)
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, roc_auc_score

    q_true = np.stack([(y > 0).astype(np.float64), (y > 1).astype(np.float64), (y > 2).astype(np.float64)], axis=1)
    q_pred = np.stack([probs[:, 1:].sum(1), probs[:, 2:].sum(1), probs[:, 3:].sum(1)], axis=1)
    auroc = [float(roc_auc_score(q_true[:, k], q_pred[:, k])) for k in range(3)]
    return {
        "accuracy": float(accuracy_score(y, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "macro_f1": float(f1_score(y, pred, average="macro", labels=[0, 1, 2, 3], zero_division=0)),
        "qwk": quadratic_weighted_kappa(y, pred),
        "recall_t1": rec[0],
        "recall_t2": rec[1],
        "recall_t3": rec[2],
        "recall_t4": rec[3],
        "middle_recall": float((rec[1] + rec[2]) / 2.0),
        "min_recall": float(min(rec)),
        "ordinal_mae": float(np.mean(np.abs(pred - y))),
        "adjacent_error": float(np.mean(np.abs(pred - y) == 1)),
        "severe_error": float(np.mean(np.abs(pred - y) >= 2)),
        "auroc_t2plus": auroc[0],
        "auroc_t3plus": auroc[1],
        "auroc_t4plus": auroc[2],
        "pred_counts": {f"T{i+1}": int((pred == i).sum()) for i in range(4)},
        "confusion": np.histogram2d(y, pred, bins=np.arange(5) - 0.5)[0].astype(int).tolist(),
    }


def _summarize(name: str, series: pd.Series) -> dict:
    arr = series.to_numpy(dtype=np.float64)
    q = np.percentile(arr, [0, 25, 50, 75, 100])
    return {
        "n": int(len(arr)),
        "mean": float(arr.mean()),
        "std": float(arr.std()),
        "min": float(q[0]),
        "q25": float(q[1]),
        "median": float(q[2]),
        "q75": float(q[3]),
        "max": float(q[4]),
    }


def analyze_csv(path: Path) -> dict:
    df = pd.read_csv(path)
    y = df["y_true"].to_numpy(dtype=int)
    pred = df["y_pred"].to_numpy(dtype=int)
    probs = df[["p_t1", "p_t2", "p_t3", "p_t4"]].to_numpy(dtype=np.float64)
    q = df[["q_t2", "q_t3", "q_t4"]].to_numpy(dtype=np.float64)
    df["a1"] = df["q_t2"]
    df["a2"] = np.where(df["q_t2"] > 1e-6, df["q_t3"] / df["q_t2"], 0.0)
    df["a3"] = np.where(df["q_t3"] > 1e-6, df["q_t4"] / df["q_t3"], 0.0)
    df["expected"] = df["q_t2"] + df["q_t3"] + df["q_t4"]
    df["top2"] = np.argsort(-probs, axis=1)[:, 1]
    df["margin"] = probs.max(axis=1) - np.sort(probs, axis=1)[:, -2]
    df["mono_ok"] = (df["q_t2"] + 1e-8 >= df["q_t3"]) & (df["q_t3"] + 1e-8 >= df["q_t4"])

    decodes = {}
    decodes["argmax"] = _metrics(y, pred, probs)

    thr = ((q[:, 0] >= 0.5).astype(int) + (q[:, 1] >= 0.5).astype(int) + (q[:, 2] >= 0.5).astype(int))
    # keep same probs for AUROC; hard labels change
    decodes["threshold_0.5"] = _metrics(y, thr, probs)
    decodes["threshold_0.5"]["pred_from"] = "q>=0.5 crossings"

    exp_pred = np.clip(np.round(df["expected"].to_numpy()), 0, 3).astype(int)
    decodes["expected_round"] = _metrics(y, exp_pred, probs)
    decodes["expected_round"]["pred_from"] = "round(q2+q3+q4)"

    # fixed cuts on expected stage: 0.5 / 1.5 / 2.5
    ev = df["expected"].to_numpy()
    cut = np.where(ev < 0.5, 0, np.where(ev < 1.5, 1, np.where(ev < 2.5, 2, 3)))
    decodes["expected_cuts_0.5_1.5_2.5"] = _metrics(y, cut, probs)

    by_true = {}
    for c, name in enumerate(("T1", "T2", "T3", "T4+")):
        sub = df[df["y_true"] == c]
        by_true[name] = {
            "n": int(len(sub)),
            "pred_counts": {f"T{i+1}": int((sub["y_pred"] == i).sum()) for i in range(4)},
            "top2_counts": {f"T{i+1}": int((sub["top2"] == i).sum()) for i in range(4)},
            "p_t1": _summarize("p", sub["p_t1"]),
            "p_t2": _summarize("p", sub["p_t2"]),
            "p_t3": _summarize("p", sub["p_t3"]),
            "p_t4": _summarize("p", sub["p_t4"]),
            "q_t2": _summarize("q", sub["q_t2"]),
            "q_t3": _summarize("q", sub["q_t3"]),
            "q_t4": _summarize("q", sub["q_t4"]),
            "a1": _summarize("a", sub["a1"]),
            "a2": _summarize("a", sub["a2"]),
            "a3": _summarize("a", sub["a3"]),
            "expected": _summarize("e", sub["expected"]),
            "margin": _summarize("m", sub["margin"]),
        }

    t3 = df[df["y_true"] == 2]
    t3_as_t4 = t3[t3["y_pred"] == 3]
    enrich_cols = [
        "patient_id", "y_true", "y_pred", "top2", "margin",
        "p_t1", "p_t2", "p_t3", "p_t4",
        "q_t2", "q_t3", "q_t4", "a1", "a2", "a3", "expected", "mono_ok",
    ]
    enrich_path = REPORT / "best_M4_A4_O3_val_patients_o3_autopsy.csv"
    df[enrich_cols].to_csv(enrich_path, index=False)

    thr_cal = {}
    for name, col, truth in (
        ("t2plus", "q_t2", y > 0),
        ("t3plus", "q_t3", y > 1),
        ("t4plus", "q_t4", y > 2),
    ):
        p = df[col].to_numpy()
        t = truth.astype(np.float64)
        pred_pos = float((p >= 0.5).mean())
        true_pos = float(t.mean())
        thr_cal[name] = {
            "true_rate": true_pos,
            "pred_rate_0.5": pred_pos,
            "brier": float(((p - t) ** 2).mean()),
            "mean_p": float(p.mean()),
            "sens_0.5": float(((p >= 0.5) & (t == 1)).sum() / max(t.sum(), 1)),
            "spec_0.5": float(((p < 0.5) & (t == 0)).sum() / max((1 - t).sum(), 1)),
        }

    return {
        "n": int(len(df)),
        "true_counts": {f"T{i+1}": int((y == i).sum()) for i in range(4)},
        "pred_counts": {f"T{i+1}": int((pred == i).sum()) for i in range(4)},
        "mono_ok": int(df["mono_ok"].sum()),
        "any_t2_argmax": int((pred == 1).sum()),
        "any_t3_argmax": int((pred == 2).sum()),
        "p_t2_mean": float(df["p_t2"].mean()),
        "p_t3_mean": float(df["p_t3"].mean()),
        "t3_as_t4_p3_mean": float(t3_as_t4["p_t3"].mean()) if len(t3_as_t4) else None,
        "t3_as_t4_p4_mean": float(t3_as_t4["p_t4"].mean()) if len(t3_as_t4) else None,
        "t3_as_t4_margin": float((t3_as_t4["p_t4"] - t3_as_t4["p_t3"]).mean()) if len(t3_as_t4) else None,
        "enriched_csv": str(enrich_path),
        "threshold_calibration": thr_cal,
        "decodes": decodes,
        "by_true": by_true,
    }


def analyze_frames(cfg_gpu: int) -> dict | None:
    import torch
    import yaml
    from torch.utils.data import DataLoader

    from lib.gus_mask2stage import PatientBagGUSDataset, build_gus_model, compute_geom_stats, gus_collate, move_batch

    cfg = yaml.safe_load((ROOT / "pipeline/configs/tstaging_4class_gus_mask2stage_20260826.yaml").read_text())
    cache = REPORT / "geom_stats_train.npz"
    if cache.is_file():
        packed = np.load(cache)
        mean, std = packed["mean"], packed["std"]
    else:
        mean, std, _ = compute_geom_stats(ROOT / cfg["data_dir"] / "train.csv")
    ds = PatientBagGUSDataset(
        ROOT / cfg["data_dir"] / "val.csv",
        max_frames=int(cfg.get("max_frames", 10)),
        image_size=int(cfg.get("image_size", 384)),
        context_size=int(cfg.get("context_size", 384)),
        n_points=int(cfg.get("n_points", 24)),
        is_train=False,
        context_expand=float(cfg.get("context_expand", 0.45)),
        geom_mean=mean,
        geom_std=std,
    )
    loader = DataLoader(ds, batch_size=1, shuffle=False, num_workers=2, collate_fn=gus_collate)
    device = torch.device(f"cuda:{cfg_gpu}" if torch.cuda.is_available() else "cpu")
    model = build_gus_model(cfg, device)
    blob = torch.load(REPORT / "best_M4_A4_O3.pth", map_location=device, weights_only=False)
    model.load_state_dict(blob["model_state_dict"], strict=False)
    model.eval()

    frame_pred = {0: 0, 1: 0, 2: 0, 3: 0}
    patient_frame_has_mid = 0
    overlap_pairs = []
    n_pat = 0
    with torch.no_grad():
        for batch in loader:
            batch = move_batch(batch, device)
            out = model(batch)
            valid = batch["valid"][0].cpu().numpy()
            u = out["frame_evidence"][0].float().cpu().numpy()
            y = int(batch["label"][0].cpu())
            n_pat += 1
            a = 1.0 / (1.0 + np.exp(-np.clip(u, -20, 20)))
            q = np.stack([a[:, 0], a[:, 0] * a[:, 1], a[:, 0] * a[:, 1] * a[:, 2]], axis=1)
            p = np.stack([1 - q[:, 0], q[:, 0] - q[:, 1], q[:, 1] - q[:, 2], q[:, 2]], axis=1)
            p = np.clip(p, 0, None)
            has_mid = False
            tops = []
            for t in range(valid.shape[0]):
                if not valid[t]:
                    continue
                cls = int(p[t].argmax())
                frame_pred[cls] += 1
                if cls in (1, 2):
                    has_mid = True
                tops.append(int(np.argmax(u[t])))
            if has_mid:
                patient_frame_has_mid += 1
            # A4 independent top-1 frame per threshold
            fill = -1e9
            uu = u.copy()
            uu[~valid] = fill
            idx = uu.argmax(axis=0)
            overlap_pairs.append({
                "y": y,
                "same_01": int(idx[0] == idx[1]),
                "same_12": int(idx[1] == idx[2]),
                "same_02": int(idx[0] == idx[2]),
                "all_same": int(idx[0] == idx[1] == idx[2]),
            })
    ov = pd.DataFrame(overlap_pairs)
    return {
        "n_patients": n_pat,
        "frame_pred_counts": {f"T{k+1}": v for k, v in frame_pred.items()},
        "patients_with_any_mid_frame": patient_frame_has_mid,
        "topk1_overlap_mean": {
            "t2_t3": float(ov["same_01"].mean()),
            "t3_t4": float(ov["same_12"].mean()),
            "t2_t4": float(ov["same_02"].mean()),
            "all_three": float(ov["all_same"].mean()),
        },
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--gpu", type=int, default=1)
    p.add_argument("--skip-frames", action="store_true")
    args = p.parse_args()
    csv_path = REPORT / "best_M4_A4_O3_val_patients.csv"
    report = analyze_csv(csv_path)
    if not args.skip_frames:
        try:
            report["frames"] = analyze_frames(args.gpu)
        except Exception as exc:
            report["frames"] = {"error": str(exc)}
    out = REPORT / "o3_decode_autopsy_epoch12.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "wrote": str(out),
        "pred_counts": report["pred_counts"],
        "decodes": {
            k: {
                "qwk": v.get("qwk"),
                "accuracy": v.get("accuracy"),
                "pred_counts": v.get("pred_counts"),
                "recall_t2": v.get("recall_t2"),
                "recall_t3": v.get("recall_t3"),
            }
            for k, v in report["decodes"].items()
        },
        "frames": report.get("frames"),
    }, indent=2))


if __name__ == "__main__":
    main()
