"""Plan-literal leftovers: clinical-only TabPFN, TIME-192, 64/128 gated, frame sample."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .constants import CACHE_DIR, CLASS_NAMES, PLAN_LITERAL_REPORT_DIR
from .encode import ensure_mask_areas
from .metrics import center_of, confusion, md_confusion, per_center, score_arrays
from .tabpfn_clinical import build_tabpfn_cache, load_tabpfn_map
from .train import _compare_markdown, _jsonable, _write_summary, train


def _score_tabpfn_split(
    cache_dir: Path, split: str, proba_map: dict[str, np.ndarray]
) -> dict[str, object]:
    path = cache_dir / f"{split}_embeddings.npz"
    with np.load(path, allow_pickle=True) as data:
        pids = np.asarray(data["patient_id"]).astype(str)
        labels = np.asarray(data["label"], dtype=int)
        sources = np.asarray(data["source"]).astype(str) if "source" in data.files else np.full(len(pids), "")
    by_pid: dict[str, dict[str, list]] = {}
    for i, pid in enumerate(pids):
        rec = by_pid.setdefault(pid, {"y": [], "src": []})
        rec["y"].append(int(labels[i]))
        rec["src"].append(str(sources[i]))
    ordered = sorted(by_pid)
    y = np.asarray([int(max(set(by_pid[pid]["y"]), key=by_pid[pid]["y"].count)) for pid in ordered], dtype=int)
    src = [max(set(by_pid[pid]["src"]), key=by_pid[pid]["src"].count) for pid in ordered]
    pred = np.asarray([int(np.argmax(proba_map[pid])) for pid in ordered], dtype=int)
    metrics = score_arrays(y, pred)
    metrics["confusion"] = confusion(y, pred)
    metrics["centers"] = per_center(y, pred, src)
    metrics["predictions"] = [
        {"patient_id": pid, "source": s, "y": int(yi), "pred": int(pi)}
        for pid, s, yi, pi in zip(ordered, src, y, pred)
    ]
    return metrics


def evaluate_clinical_only(
    cache_dir: Path = CACHE_DIR,
    report_dir: Path | None = None,
    tabpfn_device: str = "cpu",
    seed: int = 20260821,
) -> dict[str, object]:
    report_dir = report_dir or (PLAN_LITERAL_REPORT_DIR / "tabpfn_clinical_only")
    report_dir.mkdir(parents=True, exist_ok=True)
    build_tabpfn_cache(cache_dir, device=tabpfn_device, seed=seed)
    proba_map = load_tabpfn_map(cache_dir)
    evals = {}
    for split in ("train", "val", "test_prospective", "test_external"):
        path = cache_dir / f"{split}_embeddings.npz"
        if path.is_file():
            evals[split] = _score_tabpfn_split(cache_dir, split, proba_map)
    spec = {
        "name": "tabpfn_clinical_only",
        "fusion": "none",
        "pool": "none",
        "head": "tabpfn_only",
        "size": "none",
        "n_params": 0,
        "class_weight": "tabpfn_balance",
        "clinical": "clin11",
        "pool_proj": False,
        "ordinal_weight": 0.0,
        "ordinal_mode": "none",
        "t34_weight": 0.0,
        "aux_serosa_weight": 0.0,
        "lock": "none",
    }
    best = {"epoch": 0, "val_acc": float(evals["val"]["acc"]) if "val" in evals else 0.0}
    for split_name, metrics in evals.items():
        rows = list(metrics["predictions"])
        pred_path = report_dir / f"{split_name}_predictions.csv"
        pred_path.write_text(
            "split,center,patient_id,y,pred,T_true,T_pred,adjacent\n"
            + "".join(
                f"{split_name},{center_of(r['source'])},{r['patient_id']},{r['y']},{r['pred']},"
                f"{CLASS_NAMES[r['y']]},{CLASS_NAMES[r['pred']]},{int(abs(r['y']-r['pred'])<=1)}\n"
                for r in rows
            ),
            encoding="utf-8",
        )
    payload = {"spec": spec, "eval": evals, "note": "Image embeddings are not used. Train scores are 5-fold OOF."}
    (report_dir / "metrics.json").write_text(json.dumps(_jsonable(payload), indent=2), encoding="utf-8")
    _write_summary(report_dir, spec, best, evals)
    return payload


LITERAL_RUNS = (
    {
        "name": "small_concat_gated_128_nores",
        "size": "small",
        "fusion": "concat",
        "pool": "gated",
        "head": "mlp",
        "residual": False,
        "pool_out": 128,
        "frame_sample": "prefix",
    },
    {
        "name": "small_concat_gated_64_nores",
        "size": "small",
        "fusion": "concat",
        "pool": "gated",
        "head": "mlp",
        "residual": False,
        "pool_out": 64,
        "frame_sample": "prefix",
    },
    {
        "name": "xlarge_concat_gated_area",
        "size": "xlarge",
        "fusion": "concat",
        "pool": "gated",
        "head": "mlp",
        "residual": True,
        "pool_out": None,
        "frame_sample": "area",
    },
    {
        "name": "xlarge_concat_gated_random",
        "size": "xlarge",
        "fusion": "concat",
        "pool": "gated",
        "head": "mlp",
        "residual": True,
        "pool_out": None,
        "frame_sample": "random",
    },
    {
        "name": "xlarge_concat_gated_time192",
        "size": "xlarge",
        "fusion": "concat",
        "pool": "gated",
        "head": "tabpfn_time",
        "residual": True,
        "pool_out": None,
        "frame_sample": "prefix",
    },
)


def train_plan_literal_sweep(
    device: str = "cuda:0",
    epochs: int = 80,
    batch_size: int = 16,
    lr: float = 2e-4,
    tabpfn_device: str = "cpu",
    warmup_epochs: int = 8,
    patience: int = 25,
    cache_dir: Path = CACHE_DIR,
) -> dict[str, object]:
    dest_root = PLAN_LITERAL_REPORT_DIR
    dest_root.mkdir(parents=True, exist_ok=True)
    results = []
    print("mask_area", ensure_mask_areas(cache_dir), flush=True)
    clin = evaluate_clinical_only(cache_dir=cache_dir, tabpfn_device=tabpfn_device)
    print(
        "clinical-only",
        {k: {m: clin["eval"][k][m] for m in ("n", "acc", "adj_acc", "qwk")} for k in clin["eval"]},
        flush=True,
    )
    for spec in LITERAL_RUNS:
        dest = dest_root / spec["name"]
        print(f"=== literal {spec['name']} ===", flush=True)
        result = train(
            device=device,
            epochs=epochs,
            batch_size=batch_size,
            lr=lr,
            head=spec["head"],
            tabpfn_device=tabpfn_device,
            fusion=spec["fusion"],
            pool=spec["pool"],
            class_weight="balanced",
            size=spec["size"],
            warmup_epochs=warmup_epochs,
            patience=patience,
            lock="acc",
            ordinal_weight=0.5,
            pool_proj=False,
            residual=bool(spec["residual"]),
            clinical="raw",
            report_dir=dest,
            run_name=spec["name"],
            cache_dir=cache_dir,
            frame_sample=str(spec["frame_sample"]),
            pool_out=spec["pool_out"],
        )
        results.append(result)
    compare = _compare_markdown(results)
    (dest_root / "COMPARE.md").write_text(compare, encoding="utf-8")
    print(compare, flush=True)
    return {"runs": [r["spec"]["name"] for r in results], "report": str(dest_root)}
