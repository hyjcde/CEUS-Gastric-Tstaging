"""Hard-label vote of existing 4-class heads. Rule is locked on val, then scored on held-out."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from .constants import (
    CLASS_NAMES,
    ENSEMBLE2_REPORT_DIR,
    ENSEMBLE3_REPORT_DIR,
    ENSEMBLE4_REPORT_DIR,
    ENSEMBLE_REPORT_DIR,
    LOCKMACRO_REPORT_DIR,
    EXPAND15_REPORT_DIR,
    LAYERS_REPORT_DIR,
    OPT_REPORT_DIR,
    PLAN_LITERAL_REPORT_DIR,
    PLAN_REPORT_DIR,
)
from .metrics import confusion, md_confusion, per_center, score_arrays
from .train import _jsonable, _metric_row, _write_summary


MEMBERS = {
    "default_gated": OPT_REPORT_DIR / "mlp_concat_gated",
    "time192": PLAN_LITERAL_REPORT_DIR / "xlarge_concat_gated_time192",
    "expand15": EXPAND15_REPORT_DIR / "mlp_concat_gated",
    "small_mean": PLAN_REPORT_DIR / "mlp_concat_mean",
}

MEMBERS_V2 = {
    "default_gated": OPT_REPORT_DIR / "mlp_concat_gated",
    "time192": PLAN_LITERAL_REPORT_DIR / "xlarge_concat_gated_time192",
    "expand15": EXPAND15_REPORT_DIR / "mlp_concat_gated",
    "layers_time": LAYERS_REPORT_DIR / "tabpfn_time_concat_gated",
}

MEMBERS_V3 = {
    "default_gated": OPT_REPORT_DIR / "mlp_concat_gated",
    "expand15_time": EXPAND15_REPORT_DIR / "tabpfn_time_concat_gated",
    "layers_time": LAYERS_REPORT_DIR / "tabpfn_time_concat_gated",
    "time192": PLAN_LITERAL_REPORT_DIR / "xlarge_concat_gated_time192",
}

MEMBERS_V4 = {
    "default_gated": OPT_REPORT_DIR / "mlp_concat_gated",
    "expand15": EXPAND15_REPORT_DIR / "mlp_concat_gated",
    "expand15_time": EXPAND15_REPORT_DIR / "tabpfn_time_concat_gated",
    "time192_macro": LOCKMACRO_REPORT_DIR / "tabpfn_time_concat_gated",
}


def _load_split(run_dir: Path, split: str) -> pd.DataFrame:
    path = run_dir / f"{split}_predictions.csv"
    table = pd.read_csv(path)
    table["patient_id"] = table["patient_id"].astype(str)
    return table


def _aligned(split: str, names: list[str], members: dict[str, Path] | None = None) -> pd.DataFrame:
    catalog = members or MEMBERS
    frames = []
    for name in names:
        table = _load_split(catalog[name], split)
        keep = table[["patient_id", "center", "y", "pred"]].rename(columns={"pred": name})
        frames.append(keep)
    out = frames[0]
    for extra in frames[1:]:
        pred_col = [c for c in extra.columns if c not in {"patient_id", "center", "y"}][0]
        out = out.merge(extra[["patient_id", pred_col]], on="patient_id", how="inner")
    return out


def _vote_row(preds: list[int], fallback: int) -> int:
    counts = Counter(preds)
    top = counts.most_common()
    if len(top) == 1 or top[0][1] > top[1][1]:
        return int(top[0][0])
    return int(fallback)


def apply_rule(table: pd.DataFrame, names: list[str], rule: str) -> np.ndarray:
    default = table[names[0]].to_numpy(dtype=int)
    stacked = table[names].to_numpy(dtype=int)
    out = default.copy()
    for i, row in enumerate(stacked):
        if rule == "majority_fallback_default":
            out[i] = _vote_row(row.tolist(), fallback=int(default[i]))
        elif rule == "t3_rescue":
            # If default says T4+ and a T3-strong member says T3, take T3. Else majority.
            voted = _vote_row(row.tolist(), fallback=int(default[i]))
            if int(default[i]) == 3:
                for name in ("time192", "layers_time", "expand15_time"):
                    if name in names and int(table.iloc[i][name]) == 2:
                        voted = 2
                        break
            out[i] = voted
        elif rule == "default_only":
            out[i] = int(default[i])
        else:
            raise ValueError(rule)
    return out


def _pack(table: pd.DataFrame, pred: np.ndarray) -> dict[str, object]:
    y = table["y"].to_numpy(dtype=int)
    sources = table["center"].astype(str).tolist()
    metrics = score_arrays(y, pred)
    metrics["confusion"] = confusion(y, pred)
    metrics["centers"] = per_center(y, pred, sources)
    metrics["predictions"] = [
        {"patient_id": pid, "source": src, "y": int(yy), "pred": int(pp)}
        for pid, src, yy, pp in zip(table["patient_id"], sources, y, pred)
    ]
    return metrics


def run_ensemble(
    report_dir: Path | None = None,
    members: dict[str, Path] | None = None,
) -> dict[str, object]:
    catalog = members or MEMBERS
    report_dir = report_dir or ENSEMBLE_REPORT_DIR
    names = [n for n in catalog if (catalog[n] / "val_predictions.csv").is_file()]
    if len(names) < 2:
        raise FileNotFoundError(f"need at least two member prediction CSVs, found {names}")
    rules = ("default_only", "majority_fallback_default", "t3_rescue")
    val_table = _aligned("val", names, members=catalog)
    scored_rules = []
    for rule in rules:
        pred = apply_rule(val_table, names, rule)
        metrics = score_arrays(val_table["y"].to_numpy(dtype=int), pred)
        scored_rules.append({"rule": rule, "val_acc": float(metrics["acc"]), "val": metrics})
    scored_rules.sort(key=lambda r: (-r["val_acc"], r["rule"]))
    chosen = scored_rules[0]["rule"]

    evals = {}
    for split in ("val", "test_prospective", "test_external"):
        table = _aligned(split, names, members=catalog)
        pred = apply_rule(table, names, chosen)
        evals[split] = _pack(table, pred)
        pred_path = report_dir / f"{split}_predictions.csv"
        report_dir.mkdir(parents=True, exist_ok=True)
        pred_path.write_text(
            "split,center,patient_id,y,pred,T_true,T_pred,adjacent\n"
            + "".join(
                f"{split},{r['source']},{r['patient_id']},{r['y']},{r['pred']},"
                f"{CLASS_NAMES[r['y']]},{CLASS_NAMES[r['pred']]},{int(abs(r['y']-r['pred'])<=1)}\n"
                for r in evals[split]["predictions"]
            ),
            encoding="utf-8",
        )

    spec = {
        "name": f"vote_{chosen}",
        "fusion": "n/a",
        "pool": "vote",
        "head": "ensemble",
        "size": "n/a",
        "n_params": 0,
        "class_weight": "n/a",
        "clinical": "inherited",
        "pool_proj": False,
        "ordinal_weight": 0.0,
        "lock": "acc",
        "members": names,
        "rule": chosen,
        "val_rule_table": scored_rules,
    }
    best = {"epoch": 0, "val_acc": float(evals["val"]["acc"])}
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {"best": best, "spec": spec, "eval": evals, "val_rules": scored_rules}
    for metrics in evals.values():
        metrics.pop("predictions", None)
    (report_dir / "metrics.json").write_text(json.dumps(_jsonable(payload), indent=2), encoding="utf-8")
    _write_summary(report_dir, spec, best, evals)
    compare = [
        "# GastricUS label-vote ensemble",
        "",
        f"Members: {', '.join(names)}.",
        "Rule locked on val exact ACC, then applied to prospective and external.",
        "",
        "| rule | val ACC |",
        "|------|--------:|",
    ]
    for row in scored_rules:
        mark = " (chosen)" if row["rule"] == chosen else ""
        compare.append(f"| {row['rule']}{mark} | {row['val_acc']:.4f} |")
    compare += [
        "",
        "| split | ACC | adj | T3 |",
        "|-------|----:|----:|---:|",
        _metric_row("val", evals["val"]).replace("| val |", "| val |") ,
        _metric_row("test_prospective", evals["test_prospective"]),
        _metric_row("test_external", evals["test_external"]),
        "",
        "This is a ceiling check on frozen heads. It does not unfreeze MedSigLIP.",
        "",
    ]
    (report_dir / "COMPARE.md").write_text("\n".join(compare), encoding="utf-8")
    (report_dir / "SUMMARY.md").write_text(
        (report_dir / "SUMMARY.md").read_text(encoding="utf-8")
        + "\nLocked vote rule on val: "
        + chosen
        + f". Members: {', '.join(names)}.\n",
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
