"""Why T2 is missed. Uses existing prediction CSVs and frozen clinical. No patient IDs in the report."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from .constants import (
    CACHE_DIR,
    CLASS_NAMES,
    CLINICAL_FIELDS,
    EXPAND15_REPORT_DIR,
    EXPAND25_REPORT_DIR,
    OPT_REPORT_DIR,
    PLAN_LITERAL_REPORT_DIR,
    T2_ERROR_REPORT_DIR,
)

MEMBERS = {
    "default_mlp": OPT_REPORT_DIR / "mlp_concat_gated",
    "expand15_mlp": EXPAND15_REPORT_DIR / "mlp_concat_gated",
    "expand25_mlp": EXPAND25_REPORT_DIR / "mlp_concat_gated",
    "expand15_time": EXPAND15_REPORT_DIR / "tabpfn_time_concat_gated",
    "time192": PLAN_LITERAL_REPORT_DIR / "xlarge_concat_gated_time192",
}

SPLITS = ("test_prospective", "test_external")
PRED_NAMES = ("T1", "T2", "T3", "T4+")


def _patient_table(npz: Path) -> pd.DataFrame:
    with np.load(npz, allow_pickle=True) as data:
        pids = np.asarray(data["patient_id"]).astype(str)
        labels = np.asarray(data["label"]).astype(int)
        clinical = np.asarray(data["clinical"], dtype=np.float32)
        areas = np.asarray(data["mask_area"], dtype=np.float32) if "mask_area" in data.files else np.zeros(len(pids))
        sources = np.asarray(data["source"]).astype(str)
    rows = []
    for pid in sorted(set(pids.tolist())):
        idx = np.where(pids == pid)[0]
        ys = labels[idx]
        y = int(Counter(ys.tolist()).most_common(1)[0][0])
        clin = clinical[idx].mean(axis=0)
        item = {
            "patient_id": pid,
            "y": y,
            "n_frames": int(len(idx)),
            "mask_area": float(areas[idx].mean()),
            "source": str(Counter(sources[idx].tolist()).most_common(1)[0][0]),
        }
        for i, name in enumerate(CLINICAL_FIELDS):
            item[name] = float(clin[2 * i])
            item[f"{name}_missing"] = float(clin[2 * i + 1])
        rows.append(item)
    return pd.DataFrame(rows)


def _load_pred(run_dir: Path, split: str) -> pd.DataFrame:
    path = run_dir / f"{split}_predictions.csv"
    if not path.is_file():
        alt = run_dir / "test_prospective_predictions.csv"
        if split == "test_prospective" and (run_dir / "prospective_predictions.csv").is_file():
            path = run_dir / "prospective_predictions.csv"
        elif split == "test_external" and (run_dir / "external_predictions.csv").is_file():
            path = run_dir / "external_predictions.csv"
        elif not path.is_file():
            raise FileNotFoundError(path)
    table = pd.read_csv(path)
    table["patient_id"] = table["patient_id"].astype(str)
    return table[["patient_id", "center", "y", "pred", "T_true", "T_pred"]]


def _dest_share(pred: np.ndarray) -> dict[str, float]:
    n = max(len(pred), 1)
    return {name: float(np.mean(pred == i)) for i, name in enumerate(PRED_NAMES)}


def _mean_sd(values: np.ndarray) -> str:
    if len(values) == 0:
        return "n/a"
    return f"{float(values.mean()):.3f} (sd {float(values.std()):.3f}, n={len(values)})"


def analyze_t2(report_dir: Path | None = None) -> dict[str, object]:
    report_dir = report_dir or T2_ERROR_REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    bags = {split: _patient_table(CACHE_DIR / f"{split}_embeddings.npz") for split in SPLITS}
    lines = [
        "# T2 error analysis",
        "",
        "Patient-level only. No patient identifiers. Numbers from existing prediction CSVs",
        "and the frozen 20% clinical/mask-area cache. Do not treat this as a new 0.75 claim.",
        "",
        "T2 is the smallest class: prospective 34 / 425 (8.0%), external 67 / 485 (13.8%),",
        "validation 11 / 128. Locking validation exact ACC can drop T2 to protect T4+.",
        "",
        "## Where true T2 is sent",
        "",
        "| model | split | n T2 | to T1 | to T2 | to T3 | to T4+ | off2 share |",
        "|-------|-------|-----:|------:|------:|------:|-------:|-----------:|",
    ]
    payload: dict[str, object] = {"splits": {}, "members": {}}
    for split in SPLITS:
        bag = bags[split]
        t2 = bag[bag["y"] == 1].copy()
        payload["splits"][split] = {"n_t2": int(len(t2)), "n": int(len(bag))}
        for name, run in MEMBERS.items():
            pred_path = run / f"{split}_predictions.csv"
            if not pred_path.is_file():
                continue
            pred = _load_pred(run, split)
            merged = t2.merge(pred, on="patient_id", how="inner")
            dest = _dest_share(merged["pred"].to_numpy(dtype=int))
            off2 = float(np.mean(np.abs(merged["pred"].to_numpy(dtype=int) - 1) >= 2))
            lines.append(
                "| {m} | {s} | {n} | {t1:.3f} | {t2:.3f} | {t3:.3f} | {t4:.3f} | {o:.3f} |".format(
                    m=name,
                    s=split.replace("test_", ""),
                    n=int(len(merged)),
                    t1=dest["T1"],
                    t2=dest["T2"],
                    t3=dest["T3"],
                    t4=dest["T4+"],
                    o=off2,
                )
            )
    default_pro = _load_pred(MEMBERS["default_mlp"], "test_prospective")
    default_ext = _load_pred(MEMBERS["default_mlp"], "test_external")
    lines += [
        "",
        "## Default 20% MLP: T2 vs other classes (clinical / bag size)",
        "",
        "Values are the stored `_norm` field (0-1-ish). Missing rate is the paired missing flag.",
        "",
        "| split | group | n | thickness | length | mask area | frames | thickness missing |",
        "|-------|-------|--:|----------:|-------:|----------:|-------:|------------------:|",
    ]
    for split, pred in (("test_prospective", default_pro), ("test_external", default_ext)):
        bag = bags[split]
        merged = bag.merge(pred.rename(columns={"y": "y_predrow"}), on="patient_id", how="inner")
        t2 = merged[merged["y"] == 1].copy()
        t2["ok"] = t2["pred"] == 1
        for label, part in (("T2 correct", t2[t2["ok"]]), ("T2 wrong", t2[~t2["ok"]]), ("all T2", t2)):
            lines.append(
                "| {s} | {g} | {n} | {th} | {ln} | {ar} | {fr} | {ms:.3f} |".format(
                    s=split.replace("test_", ""),
                    g=label,
                    n=int(len(part)),
                    th=_mean_sd(part["tumor_thickness_cm"].to_numpy()),
                    ln=_mean_sd(part["tumor_length_cm"].to_numpy()),
                    ar=_mean_sd(part["mask_area"].to_numpy()),
                    fr=_mean_sd(part["n_frames"].to_numpy()),
                    ms=float(part["tumor_thickness_cm_missing"].mean()) if len(part) else 0.0,
                )
            )
        all_t = merged
        ycol = "y"
        for cls, cname in ((0, "true T1"), (1, "true T2"), (2, "true T3"), (3, "true T4+")):
            part = all_t[all_t[ycol] == cls]
            lines.append(
                "| {s} | {g} | {n} | {th} | {ln} | {ar} | {fr} | {ms:.3f} |".format(
                    s=split.replace("test_", ""),
                    g=cname,
                    n=int(len(part)),
                    th=_mean_sd(part["tumor_thickness_cm"].to_numpy()),
                    ln=_mean_sd(part["tumor_length_cm"].to_numpy()),
                    ar=_mean_sd(part["mask_area"].to_numpy()),
                    fr=_mean_sd(part["n_frames"].to_numpy()),
                    ms=float(part["tumor_thickness_cm_missing"].mean()) if len(part) else 0.0,
                )
            )

    # overlap of T2 mistakes across models
    lines += [
        "",
        "## Cross-model T2 mistakes (default vs 15% vs 25% MLP)",
        "",
        "Count of true-T2 patients missed by each pair. High overlap means the same hard cases.",
        "",
        "| split | missed by default | also missed by 15% | also missed by 25% | missed by all three | 25% recovers default miss |",
        "|-------|------------------:|-------------------:|-------------------:|--------------------:|--------------------------:|",
    ]
    for split in SPLITS:
        bag = bags[split]
        t2_ids = set(bag.loc[bag["y"] == 1, "patient_id"].astype(str))
        wrong = {}
        for key in ("default_mlp", "expand15_mlp", "expand25_mlp"):
            pred = _load_pred(MEMBERS[key], split)
            hit = pred[pred["patient_id"].isin(t2_ids)]
            wrong[key] = set(hit.loc[hit["pred"] != 1, "patient_id"].astype(str))
        d, a, b = wrong["default_mlp"], wrong["expand15_mlp"], wrong["expand25_mlp"]
        lines.append(
            "| {s} | {dn} | {an} | {bn} | {alln} | {rec} |".format(
                s=split.replace("test_", ""),
                dn=len(d),
                an=len(d & a),
                bn=len(d & b),
                alln=len(d & a & b),
                rec=len(d - b),
            )
        )

    lines += [
        "",
        "## What this says",
        "",
        "1. T2 is rare. Validation has 11 T2 patients, so a lock on exact ACC can ignore T2.",
        "2. On the default 20% MLP, missed T2 splits about evenly into T1 (understage) and T4+ (jump).",
        "   Prospective default: 13/34 to T1, 9/34 to T4+, only 3/34 to T3. External: 22/67 to T1, 21/67 to T4+.",
        "3. TIME-192 heads send almost all T2 to T3/T4+. That is why 15% TIME has the best external exact ACC",
        "   (0.5794) and T2 recall near 0.",
        "4. ROI 25% MLP has the best external T2 recall (0.4478) among these heads, but exact ACC stays 0.5196.",
        "5. First `--head tabpfn` (small, 2026-08-21) lifted T2 vs the first MLP, but exact ACC was 0.4776 / 0.4804.",
        "   The current default concat-gated xlarge path had not yet been re-tested with `--head tabpfn`.",
        "6. Thickness/length of true T2 sit between T1 and T3. Wrong T2 cases are not a single size regime.",
        "7. Padding was only black square-pad. Reflect / edge / mean pad had not been encoded.",
        "",
        "Expand 15/20/25 MLP already exists. Do not re-run those three caches.",
        "",
    ]
    text = "\n".join(lines) + "\n"
    (report_dir / "SUMMARY.md").write_text(text, encoding="utf-8")
    (report_dir / "T2_ERROR.md").write_text(text, encoding="utf-8")
    (report_dir / "metrics.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"report": str(report_dir), "splits": payload["splits"]}
