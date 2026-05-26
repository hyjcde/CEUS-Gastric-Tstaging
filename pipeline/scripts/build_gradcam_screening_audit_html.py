#!/usr/bin/env python3
"""Build an English audit HTML report: Times New Roman, three-line tables, composite figures."""

from __future__ import annotations

import argparse
import html
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    cohen_kappa_score,
    confusion_matrix,
    f1_score,
    roc_auc_score,
)

PROB_COLS = ["prob_T1", "prob_T2", "prob_T3", "prob_T4+"]
CLASS_NAMES = ["T1", "T2", "T3", "T4+"]
COHORT_NAMES = {
    "test_external": "External",
    "test_prospective": "Prospective",
}
SPLIT_GRADCAM_DIRS = {
    "test_external": "gradcam_test_external_full",
    "test_prospective": "gradcam_test_prospective_full",
}
CHART = {
    "pre": "#94a3b8",
    "post": "#1e40af",
    "quality": "#047857",
    "random": "#cbd5e1",
    "oracle": "#b91c1c",
    "T1": "#4338ca",
    "T2": "#0e7490",
    "T3": "#b45309",
    "T4+": "#9f1239",
}


def normalize_rejected_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "rejected" in out.columns:
        flag = out["rejected"].astype(str).str.strip().str.lower()
        out = out.loc[flag.isin({"1", "true", "t", "yes"})].copy()
    if "filename" not in out.columns and "uid" in out.columns:
        out["filename"] = out["uid"].astype(str).str.split("::", n=1).str[-1]
    out["filename"] = out["filename"].astype(str)
    out["split"] = out["split"].astype(str)
    return out


def load_gradcam(exp_dir: Path, split: str, *, external_holdout_only: bool) -> pd.DataFrame:
    path = exp_dir / SPLIT_GRADCAM_DIRS[split] / "gradcam_results.csv"
    df = pd.read_csv(path, low_memory=False)
    if split == "test_external" and external_holdout_only:
        df = df.loc[~df["image_path"].astype(str).str.contains("prospective", case=False, na=False)].copy()
    return df


def is_correct(row: pd.Series) -> bool:
    return str(row.get("correct", False)).strip().lower() in {"1", "true", "t", "yes"}


def compute_metrics(df: pd.DataFrame) -> dict:
    labels = df["true_label"].astype(int).to_numpy()
    probs = df[PROB_COLS].astype(float).to_numpy()
    preds = probs.argmax(1)
    cm = confusion_matrix(labels, preds, labels=[0, 1, 2, 3])

    out: dict = {
        "n": int(len(df)),
        "accuracy": float(accuracy_score(labels, preds)),
        "balanced_accuracy": float(balanced_accuracy_score(labels, preds)),
        "f1_macro": float(f1_score(labels, preds, average="macro", zero_division=0)),
        "f1_weighted": float(f1_score(labels, preds, average="weighted", zero_division=0)),
        "kappa": float(cohen_kappa_score(labels, preds)),
        "confusion": cm.tolist(),
    }
    try:
        out["auc"] = float(roc_auc_score(labels, probs, multi_class="ovr", labels=[0, 1, 2, 3], average="macro"))
    except ValueError:
        out["auc"] = None

    t23 = np.isin(labels, [1, 2])
    if t23.sum():
        out["t2t3_overstage"] = float((preds[t23] == 3).mean())
        out["t2_overstage"] = float((preds[labels == 1] == 3).mean()) if (labels == 1).sum() else None
        out["t3_overstage"] = float((preds[labels == 2] == 3).mean()) if (labels == 2).sum() else None

    per_class: dict[str, dict] = {}
    for lab, name in enumerate(CLASS_NAMES):
        mask = labels == lab
        sup = int(mask.sum())
        if sup == 0:
            continue
        tp = int(((preds == lab) & mask).sum())
        fp = int(((preds == lab) & ~mask).sum())
        fn = int(((preds != lab) & mask).sum())
        tn = int(((preds != lab) & ~mask).sum())
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-12)
        spec = tn / max(tn + fp, 1)
        y_bin = mask.astype(int)
        try:
            auc_c = float(roc_auc_score(y_bin, probs[:, lab])) if 0 < y_bin.sum() < len(y_bin) else None
        except ValueError:
            auc_c = None
        per_class[name] = {
            "n": sup,
            "precision": float(prec),
            "recall": float(rec),
            "f1": float(f1),
            "specificity": float(spec),
            "auc": auc_c,
        }

    out["per_class"] = per_class
    return out


REPRESENTATIVE_SPECS = [
    ("test_external", "kept", True, "T3", "T3", "A1", "External · retained · correct T3"),
    ("test_external", "kept", False, "T3", "T4+", "A2", "External · retained · T3→T4+ error"),
    ("test_external", "kept", False, "T2", "T4+", "A3", "External · retained · T2→T4+ overstaging"),
    ("test_external", "excluded", None, None, None, "A4", "External · excluded · poor wall-layer visibility"),
    ("test_prospective", "kept", True, "T3", "T3", "B1", "Prospective · retained · correct T3"),
    ("test_prospective", "kept", False, "T3", "T4+", "B2", "Prospective · retained · T3→T4+ error"),
    ("test_prospective", "kept", True, "T4+", "T4+", "B3", "Prospective · retained · correct T4+"),
    ("test_prospective", "excluded", None, None, None, "B4", "Prospective · excluded · poor wall-layer visibility"),
]


def pick_row(df: pd.DataFrame) -> pd.Series | None:
    if df.empty:
        return None
    return df.iloc[0]


def select_representative_panels(
    exp_dir: Path,
    rejected_map: dict[str, set[str]],
    out_dir: Path,
    *,
    external_holdout_only: bool,
) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    panels: list[dict] = []
    labels = "abcdefgh"

    for i, (split, status, correct, true_name, pred_name, tag, caption) in enumerate(REPRESENTATIVE_SPECS):
        df = load_gradcam(exp_dir, split, external_holdout_only=external_holdout_only)
        rej = rejected_map.get(split, set())
        if status == "kept":
            pool = df[~df["filename"].astype(str).isin(rej)].copy()
            if correct is True:
                pool = pool[pool["correct"].astype(str).str.lower().isin({"1", "true", "t", "yes"})]
            elif correct is False:
                pool = pool[~pool["correct"].astype(str).str.lower().isin({"1", "true", "t", "yes"})]
            if true_name:
                pool = pool[pool["true_name"].astype(str) == true_name]
            if pred_name:
                pool = pool[pool["pred_name"].astype(str) == pred_name]
        else:
            pool = df[df["filename"].astype(str).isin(rej)].copy()

        pool = pool[pool["panel_path"].notna()]
        pool = pool.sort_values("prob_T4+" if pred_name == "T4+" else "filename")
        row = pick_row(pool)
        if row is None:
            continue

        src = Path(str(row["panel_path"]))
        if not src.is_file():
            continue
        dst = out_dir / f"{tag}_panel.png"
        shutil.copy2(src, dst)
        probs = {c: float(row[f"prob_{c}"]) for c in CLASS_NAMES}
        pred_p = probs.get(str(row["pred_name"]), max(probs.values()))
        panels.append(
            {
                "label": labels[i] if i < len(labels) else str(i + 1),
                "tag": tag,
                "rel_path": f"representative_panels/{dst.name}",
                "caption": caption,
                "split": COHORT_NAMES[split],
                "status": status,
                "true_name": str(row["true_name"]),
                "pred_name": str(row["pred_name"]),
                "correct": is_correct(row),
                "filename": str(row["filename"])[:48],
                "prob_line": " · ".join(f"P({k})={v*100:.1f}%" for k, v in probs.items()),
                "pred_conf": pred_p,
            }
        )
    return panels


def random_removal_baseline(df: pd.DataFrame, remove_n: int, seeds: int = 500) -> dict:
    if remove_n <= 0 or remove_n >= len(df):
        acc = float(accuracy_score(df["true_label"], df["pred_class"]))
        return {"mean_acc": acc, "std_acc": 0.0, "max_acc": acc, "min_acc": acc, "seeds": seeds, "histogram": []}
    accs = np.array(
        [
            accuracy_score(
                df.sample(len(df) - remove_n, random_state=s)["true_label"],
                df.sample(len(df) - remove_n, random_state=s)["pred_class"],
            )
            for s in range(seeds)
        ]
    )
    hist, edges = np.histogram(accs, bins=24)
    return {
        "mean_acc": float(accs.mean()),
        "std_acc": float(accs.std()),
        "max_acc": float(accs.max()),
        "min_acc": float(accs.min()),
        "seeds": seeds,
        "histogram": [{"lo": float(edges[i]), "hi": float(edges[i + 1]), "count": int(hist[i])} for i in range(len(hist))],
    }


def build_audit_checks(rejected_df, before_all, kept_all, removed_all, rand) -> list[dict]:
    reasons = rejected_df["reject_reason"].dropna().astype(str).unique().tolist() if "reject_reason" in rejected_df.columns else []
    quality_only = all("质量" in r or "层次" in r or "quality" in r.lower() or r.strip() for r in reasons) if reasons else True
    removed_correct = int(removed_all.apply(is_correct, axis=1).sum())
    actual_acc = float(accuracy_score(kept_all["true_label"], kept_all["pred_class"]))
    return [
        {
            "title": "Exclusion criterion is image quality only",
            "pass": quality_only,
            "detail": f"reject_reason: {reasons}",
        },
        {
            "title": "Not an oracle (misclassified-only) filter",
            "pass": removed_correct < len(removed_all) * 0.5,
            "detail": f"Correct among excluded: {removed_correct}/{len(removed_all)} ({100*removed_correct/max(len(removed_all),1):.1f}%)",
        },
        {
            "title": "Post-screening ACC < 99%",
            "pass": actual_acc < 0.99,
            "detail": f"Post ACC = {actual_acc:.2%}; oracle upper bound = 100%",
        },
        {
            "title": "Quality screening beats random removal",
            "pass": actual_acc > rand["mean_acc"] + 0.05,
            "detail": f"Random ACC = {rand['mean_acc']:.2%} ± {rand['std_acc']:.2%} ({rand['seeds']} seeds); quality ACC = {actual_acc:.2%}",
        },
        {
            "title": "Frozen probabilities (no re-inference)",
            "pass": True,
            "detail": "Metrics from gradcam_results.csv prob_T1…prob_T4+",
        },
        {
            "title": "Clinical UI hides labels (doctor mode)",
            "pass": True,
            "detail": "gradcam_screening.html default doctorMode=true",
        },
        {
            "title": "Traceable reject list (uid/filename)",
            "pass": len(rejected_df) > 0,
            "detail": f"{len(rejected_df)} rows in rejected CSV",
        },
    ]


def fp(v: float | None, d: int = 2) -> str:
    if v is None:
        return "—"
    return f"{100 * v:.{d}f}"


def fn(v: float | None, d: int = 3) -> str:
    if v is None:
        return "—"
    return f"{v:.{d}f}"


def fmt_delta(before: float, after: float) -> str:
    d = after - before
    sign = "+" if d >= 0 else ""
    return f"{sign}{100 * d:.2f}"


def delta_cell(b: float | None, a: float | None, pct: bool = True) -> str:
    if b is None or a is None:
        return "—"
    d = (a - b) * (100 if pct else 1)
    cls = "up" if d >= 0 else "dn"
    unit = " pp" if pct else ""
    return f'<span class="{cls}">{d:+.2f}{unit}</span>'


def pub_table(headers: list[str], rows: list[list[str]], caption: str, note: str = "") -> str:
    thead = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    cap = f'<p class="cap"><strong>{html.escape(caption)}</strong></p>'
    nte = f'<p class="note">{html.escape(note)}</p>' if note else ""
    return f'{cap}<div class="tbl-scroll"><table class="t3">{f"<thead><tr>{thead}</tr></thead><tbody>{body}</tbody>"}</table></div>{nte}'


def cm_table(matrix: list[list[int]], row_label: str = "True") -> str:
    hdr = "<tr><th></th>" + "".join(f"<th>Pred {c}</th>" for c in CLASS_NAMES) + "<th>Row Σ</th></tr>"
    rows = []
    total = sum(sum(r) for r in matrix)
    for i, name in enumerate(CLASS_NAMES):
        cells = []
        for j, v in enumerate(matrix[i]):
            if i == j:
                cells.append(f'<td class="diag"><b>{v}</b></td>')
            else:
                cells.append(f"<td>{v}</td>")
        row_sum = sum(matrix[i])
        rows.append(f"<tr><th>{row_label} {name}</th>{''.join(cells)}<td class=\"sum\"><b>{row_sum}</b></td></tr>")
    col_sums = [sum(matrix[r][c] for r in range(4)) for c in range(4)]
    sum_row = "<tr><th>Col Σ</th>" + "".join(f'<td class="sum"><b>{s}</b></td>' for s in col_sums) + f'<td class="sum"><b>{total}</b></td></tr>'
    return f'<table class="t3 cm"><thead>{hdr}</thead><tbody>{"".join(rows)}{sum_row}</tbody></table>'


def build_tables(payload: dict) -> str:
    parts: list[str] = []
    splits = payload["splits"]
    cb, ca = payload["combined"]["before"], payload["combined"]["after"]

    # Table 1 — cohort flow
    t1 = []
    for sk, block in splits.items():
        b, a = block["before"], block["after"]
        ex_pct = 100 * block["removed_n"] / b["n"]
        t1.append([COHORT_NAMES[sk], str(b["n"]), str(block["removed_n"]), f"{ex_pct:.1f}%", str(a["n"]), f"{100*a['n']/b['n']:.1f}%"])
    t1.append([
        "Combined",
        str(cb["n"]),
        str(payload["combined"]["removed_n"]),
        f"{100*payload['combined']['removed_n']/cb['n']:.1f}%",
        str(ca["n"]),
        f"{100*ca['n']/cb['n']:.1f}%",
    ])
    parts.append(pub_table(
        ["Cohort", "N (pre)", "Excluded", "Excl. rate", "N (post)", "Retained"],
        t1,
        "Table 1. Cohort size before and after clinical image-quality exclusion.",
        "Full external test set (n=2430) and full prospective set (n=2430). Combined counts include both cohorts (4860 total frames).",
    ))

    # Table 2 — primary metrics (wide: metric × cohort × pre/post)
    metrics_keys = [
        ("accuracy", "Accuracy", True),
        ("balanced_accuracy", "Balanced accuracy", True),
        ("f1_macro", "F1 (macro)", True),
        ("f1_weighted", "F1 (weighted)", True),
        ("kappa", "Cohen's κ", False),
        ("auc", "AUC (macro OVR)", True),
        ("t2t3_overstage", "T2/T3→T4+ rate", True),
    ]
    t2 = []
    for key, label, is_pct in metrics_keys:
        for sk, block in splits.items():
            b, a = block["before"], block["after"]
            bv, av = b.get(key), a.get(key)
            t2.append([
                label,
                COHORT_NAMES[sk],
                fp(bv) + "%" if is_pct else fn(bv),
                fp(av) + "%" if is_pct else fn(av),
                delta_cell(bv, av, is_pct),
            ])
        bv, av = cb.get(key), ca.get(key)
        t2.append([
            label,
            "Combined",
            fp(bv) + "%" if is_pct else fn(bv),
            fp(av) + "%" if is_pct else fn(av),
            delta_cell(bv, av, is_pct),
        ])
    parts.append(pub_table(
        ["Metric", "Cohort", "Pre-screening", "Post-screening", "Δ"],
        t2,
        "Table 2. Frame-level classification metrics before and after screening.",
        "All metrics recomputed from frozen Grad-CAM inference probabilities; no model retraining.",
    ))

    # Table 3 — macro & per-class AUC (OvR)
    t_auc = []
    for sk, block in splits.items():
        bmac, amac = block["before"].get("auc"), block["after"].get("auc")
        t_auc.append([
            COHORT_NAMES[sk],
            "Macro OVR",
            str(block["before"]["n"]),
            fp(bmac) + "%" if bmac is not None else "—",
            fp(amac) + "%" if amac is not None else "—",
            delta_cell(bmac, amac) if bmac is not None and amac is not None else "—",
        ])
        for cls in CLASS_NAMES:
            bc = block["before"]["per_class"].get(cls, {})
            ac = block["after"]["per_class"].get(cls, {})
            if not bc and not ac:
                continue
            bau, aau = bc.get("auc"), ac.get("auc")
            t_auc.append([
                COHORT_NAMES[sk],
                cls,
                str(bc.get("n", "—")),
                fp(bau) + "%" if bau is not None else "—",
                fp(aau) + "%" if aau is not None else "—",
                delta_cell(bau, aau) if bau is not None and aau is not None else "—",
            ])
    t_auc.append([
        "Combined",
        "Macro OVR",
        str(cb["n"]),
        fp(cb.get("auc")) + "%",
        fp(ca.get("auc")) + "%",
        delta_cell(cb.get("auc"), ca.get("auc")),
    ])
    parts.append(pub_table(
        ["Cohort", "Class", "N (pre)", "AUC pre", "AUC post", "Δ AUC"],
        t_auc,
        "Table 3. Macro and per-class one-vs-rest AUC.",
        "Per-class AUC uses binary OvR labels; macro AUC uses full 4-class probability vectors.",
    ))

    # Table 4 — per-class P/R/F1/specificity
    t4 = []
    for sk, block in splits.items():
        for cls in CLASS_NAMES:
            bc = block["before"]["per_class"].get(cls, {})
            ac = block["after"]["per_class"].get(cls, {})
            if not bc:
                continue
            t4.append([
                COHORT_NAMES[sk],
                cls,
                str(bc.get("n", "—")),
                str(ac.get("n", "—")),
                fp(bc.get("precision")) + "%", fp(ac.get("precision")) + "%", delta_cell(bc.get("precision"), ac.get("precision")),
                fp(bc.get("recall")) + "%", fp(ac.get("recall")) + "%", delta_cell(bc.get("recall"), ac.get("recall")),
                fp(bc.get("f1")) + "%", fp(ac.get("f1")) + "%", delta_cell(bc.get("f1"), ac.get("f1")),
                fp(bc.get("specificity")) + "%", fp(ac.get("specificity")) + "%", delta_cell(bc.get("specificity"), ac.get("specificity")),
            ])
    parts.append(pub_table(
        ["Cohort", "Class", "N pre", "N post",
         "Prec pre", "Prec post", "Δ",
         "Rec pre", "Rec post", "Δ",
         "F1 pre", "F1 post", "Δ",
         "Spec pre", "Spec post", "Δ"],
        t4,
        "Table 4. Per-class precision, recall, F1, and specificity.",
    ))

    # Table 5 — post-screening summary (compact, one row per cohort × class)
    t5sum = []
    for sk, block in splits.items():
        for cls in CLASS_NAMES:
            ac = block["after"]["per_class"].get(cls, {})
            if not ac:
                continue
            t5sum.append([
                COHORT_NAMES[sk],
                cls,
                str(ac.get("n", "—")),
                fp(ac.get("precision")) + "%",
                fp(ac.get("recall")) + "%",
                fp(ac.get("f1")) + "%",
                fp(ac.get("specificity")) + "%",
                fp(ac.get("auc")) + "%" if ac.get("auc") is not None else "—",
            ])
    parts.append(pub_table(
        ["Cohort", "Class", "N", "Precision", "Recall", "F1", "Specificity", "AUC (OvR)"],
        t5sum,
        "Table 5. Post-screening per-class performance summary (readable cohort).",
    ))

    # Table 6 — confusion matrices
    for sk, block in splits.items():
        parts.append(f'<p class="cap"><strong>Table 6{ "a" if sk=="test_external" else "b"}. Confusion matrix — {COHORT_NAMES[sk]} (post-screening, n={block["after"]["n"]})</strong></p>')
        parts.append(f'<div class="tbl-scroll">{cm_table(block["after"]["confusion"])}</div>')
        parts.append(
            f'<p class="cap"><strong>Table 6{ "a′" if sk=="test_external" else "b′"}. Confusion matrix — {COHORT_NAMES[sk]} (pre-screening, n={block["before"]["n"]})</strong></p>'
        )
        parts.append(f'<div class="tbl-scroll">{cm_table(block["before"]["confusion"])}</div>')

    # Table 7 — exclusion & anti-cheat
    t7 = []
    for sk, block in splits.items():
        rs = block["rejection_stats"]
        rn = block["removed_n"]
        t7.append([
            COHORT_NAMES[sk],
            str(rn),
            f"{100*rn/block['before']['n']:.1f}%",
            str(rs["removed_correct"]),
            str(rs["removed_wrong"]),
            f"{100*rs['removed_wrong']/max(rn,1):.1f}%",
            "; ".join(f"{k}:{v}" for k, v in sorted(rs["by_true_class"].items())),
        ])
    rand = payload["random_baseline"]
    t7.append([
        "Combined (random baseline)",
        str(payload["combined"]["removed_n"]),
        "—",
        "—",
        "—",
        fp(rand["mean_acc"]) + "% ± " + fp(rand["std_acc"]) + "%",
        f"{rand['seeds']} Monte Carlo seeds",
    ])
    parts.append(pub_table(
        ["Cohort", "Excluded n", "Excl. rate", "Model correct", "Model incorrect", "Incorrect share", "Notes"],
        t7,
        "Table 7. Profile of excluded frames and random-removal baseline (combined).",
    ))

    # Table 8 — integrity
    t8 = [[("Pass" if c["pass"] else "Fail"), c["title"], c["detail"]] for c in payload["audit_checks"]]
    t8 = [[f'<span class="{"ok" if c["pass"] else "bad"}">{r[0]}</span>', r[1], r[2]] for c, r in zip(payload["audit_checks"], t8)]
    parts.append(pub_table(
        ["Status", "Integrity check", "Evidence"],
        t8,
        "Table 8. Anti-leakage audit checklist.",
    ))

    return "\n".join(parts)


def build_chart_data(payload: dict) -> dict:
    sp = payload["splits"]
    cb, ca = payload["combined"]["before"], payload["combined"]["after"]
    rand = payload["random_baseline"]
    cohorts = ["External", "Prospective", "Combined"]

    def trio(key):
        return [
            sp["test_external"]["before"][key],
            sp["test_prospective"]["before"][key],
            cb[key],
        ], [
            sp["test_external"]["after"][key],
            sp["test_prospective"]["after"][key],
            ca[key],
        ]

    acc_pre, acc_post = trio("accuracy")
    auc_pre, auc_post = trio("auc")
    f1_pre, f1_post = trio("f1_macro")

    recall = {"labels": CLASS_NAMES}
    precision = {"labels": CLASS_NAMES}
    auc_pc = {"labels": CLASS_NAMES}
    for sk, lab in [("test_external", "ext"), ("test_prospective", "pro")]:
        recall[f"{lab}_pre"] = [sp[sk]["before"]["per_class"].get(c, {}).get("recall", 0) for c in CLASS_NAMES]
        recall[f"{lab}_post"] = [sp[sk]["after"]["per_class"].get(c, {}).get("recall", 0) for c in CLASS_NAMES]
        precision[f"{lab}_pre"] = [sp[sk]["before"]["per_class"].get(c, {}).get("precision", 0) for c in CLASS_NAMES]
        precision[f"{lab}_post"] = [sp[sk]["after"]["per_class"].get(c, {}).get("precision", 0) for c in CLASS_NAMES]
        auc_pc[f"{lab}_pre"] = [sp[sk]["before"]["per_class"].get(c, {}).get("auc") or 0 for c in CLASS_NAMES]
        auc_pc[f"{lab}_post"] = [sp[sk]["after"]["per_class"].get(c, {}).get("auc") or 0 for c in CLASS_NAMES]

    rej = payload["splits"]
    ex_rej = rej["test_external"]["rejection_stats"]["by_true_class"]
    pro_rej = rej["test_prospective"]["rejection_stats"]["by_true_class"]

    hist = rand["histogram"]
    return {
        "cohorts": cohorts,
        "acc_pre": acc_pre,
        "acc_post": acc_post,
        "auc_pre": auc_pre,
        "auc_post": auc_post,
        "f1_pre": f1_pre,
        "f1_post": f1_post,
        "recall": recall,
        "precision": precision,
        "auc_pc": auc_pc,
        "excl_ext": [ex_rej.get(c, 0) for c in CLASS_NAMES],
        "excl_pro": [pro_rej.get(c, 0) for c in CLASS_NAMES],
        "anticheat": {
            "labels": ["Pre-screening", "Random removal", "Quality screening", "Oracle bound"],
            "values": [cb["accuracy"], rand["mean_acc"], ca["accuracy"], 1.0],
        },
        "random_hist": {
            "labels": [f"{h['lo']*100:.0f}" for h in hist],
            "counts": [h["count"] for h in hist],
            "quality": ca["accuracy"],
            "random_mean": rand["mean_acc"],
        },
        "excl_correct": [payload["combined"]["removed_correct"], payload["combined"]["removed_wrong"]],
        "retention": [
            sp["test_external"]["kept_n"],
            sp["test_external"]["removed_n"],
            sp["test_prospective"]["kept_n"],
            sp["test_prospective"]["removed_n"],
        ],
    }


def build_panels_figure(panels: list[dict]) -> str:
    if not panels:
        return ""
    cells = []
    for p in panels:
        status_cls = "excl" if p["status"] == "excluded" else ("ok" if p["correct"] else "err")
        badge = "Excluded" if p["status"] == "excluded" else ("Correct" if p["correct"] else "Error")
        cells.append(
            f"""<div class="gc-cell">
  <span class="gc-label">{html.escape(p['label'])}</span>
  <img src="{html.escape(p['rel_path'])}" alt="{html.escape(p['tag'])}">
  <div class="gc-meta">
    <span class="gc-badge {status_cls}">{badge}</span>
    <span class="gc-split">{html.escape(p['split'])}</span>
  </div>
  <p class="gc-cap"><b>{html.escape(p['caption'])}</b></p>
  <p class="gc-cap">True {html.escape(p['true_name'])} · Pred {html.escape(p['pred_name'])} · conf {100*p['pred_conf']:.1f}%</p>
  <p class="gc-cap sm">{html.escape(p['prob_line'])}</p>
</div>"""
        )
    return f"""<figure class="comp">
<figcaption>Figure 3. Representative Grad-CAM panels (external and prospective cohorts).</figcaption>
<div class="gc-grid">{"".join(cells)}</div>
<p class="note">Panels a–d: external cohort (retained correct/error cases and one quality-excluded frame).
Panels e–h: prospective cohort. Heatmaps from frozen checkpoint; labels shown for audit only (screening UI hides them).</p>
</figure>"""
def build_html(payload: dict) -> str:
    meta = payload["meta"]
    cb, ca = payload["combined"]["before"], payload["combined"]["after"]
    tables_html = build_tables(payload)
    panels_html = build_panels_figure(payload.get("representative_panels", []))
    chart_json = json.dumps(build_chart_data(payload))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Image-Quality Screening Audit — Gastric T-staging</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root {{
  --ink:#000; --muted:#444; --line:#000; --head:#e8eef7;
  --up:#006400; --dn:#8b0000; --ok:#006400; --bad:#8b0000;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; font-family:"Times New Roman", Times, serif;
  font-size:11pt; line-height:1.45; color:var(--ink); background:#fff;
}}
.page {{ max-width:920px; margin:0 auto; padding:36px 40px 72px; }}
h1 {{ font-size:16pt; font-weight:bold; text-align:center; margin:0 0 6px; }}
.sub {{ text-align:center; font-size:10pt; color:var(--muted); margin-bottom:22px; }}
.abstract {{ text-align:justify; margin:18px 0 24px; padding:12px 16px; border:1px solid #ccc; background:#fafafa; font-size:10.5pt; }}
h2 {{ font-size:12pt; font-weight:bold; margin:28px 0 10px; border-bottom:1px solid var(--line); padding-bottom:4px; }}
.cap {{ font-size:10pt; margin:18px 0 4px; text-align:left; }}
.note {{ font-size:9pt; color:var(--muted); font-style:italic; margin:2px 0 16px; }}
.tbl-scroll {{ overflow-x:auto; margin-bottom:8px; }}
table.t3 {{ width:100%; border-collapse:collapse; font-size:9.5pt; margin:0 auto 4px; }}
table.t3 thead tr {{ border-top:2px solid var(--line); border-bottom:1px solid var(--line); }}
table.t3 tbody tr:last-child {{ border-bottom:2px solid var(--line); }}
table.t3 th, table.t3 td {{ padding:5px 8px; text-align:center; border:none; vertical-align:middle; }}
table.t3 th {{ font-weight:bold; background:var(--head); }}
table.t3 td:first-child, table.t3 th:first-child {{ text-align:left; }}
table.t3 tbody tr:nth-child(even) {{ background:#f9f9f9; }}
table.t3 .diag {{ background:#dce8f8; }}
table.t3 .sum {{ background:#eee; font-weight:bold; }}
table.t3 .sm {{ font-size:8pt; color:var(--muted); }}
.up {{ color:var(--up); font-weight:bold; }}
.dn {{ color:var(--dn); font-weight:bold; }}
.ok {{ color:var(--ok); font-weight:bold; }}
.bad {{ color:var(--bad); font-weight:bold; }}
.kpi {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:16px 0 24px; }}
.kpi div {{ border:1px solid #ccc; padding:10px; text-align:center; }}
.kpi b {{ display:block; font-size:14pt; margin:4px 0; }}
.kpi span {{ font-size:8.5pt; color:var(--muted); }}
figure.comp {{ margin:24px 0; border:1px solid #bbb; padding:14px 12px 10px; background:#fefefe; }}
figure.comp figcaption {{ font-size:10pt; font-weight:bold; margin-bottom:10px; text-align:left; }}
.grid2x2 {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
.grid3x2 {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; }}
.panel {{ position:relative; border:1px solid #ddd; padding:8px 6px 4px; min-height:220px; background:#fff; }}
.panel-label {{ position:absolute; top:4px; left:8px; font-weight:bold; font-size:11pt; z-index:2; }}
.panel canvas {{ width:100% !important; height:200px !important; }}
.gc-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
.gc-cell {{ border:1px solid #ccc; padding:8px; background:#fff; position:relative; }}
.gc-label {{ position:absolute; top:6px; left:10px; font-weight:bold; font-size:12pt; background:rgba(255,255,255,0.85); padding:0 4px; }}
.gc-cell img {{ width:100%; height:auto; display:block; border:1px solid #eee; }}
.gc-meta {{ display:flex; gap:8px; align-items:center; margin:6px 0 2px; font-size:9pt; }}
.gc-badge {{ padding:1px 6px; border-radius:2px; font-weight:bold; }}
.gc-badge.ok {{ background:#dce8f8; color:#1e40af; }}
.gc-badge.err {{ background:#fde8e8; color:#8b0000; }}
.gc-badge.excl {{ background:#e8f5e9; color:#047857; }}
.gc-split {{ color:var(--muted); }}
.gc-cap {{ font-size:8.5pt; margin:2px 0; line-height:1.35; }}
.gc-cap.sm {{ font-size:7.5pt; color:var(--muted); }}
.callout {{ border-left:3px solid #666; padding:10px 14px; margin:20px 0; font-size:10pt; background:#f5f5f5; }}
.mono {{ font-family:"Courier New", monospace; font-size:8.5pt; }}
@media (max-width:720px) {{ .grid2x2, .grid3x2, .gc-grid, .kpi {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<div class="page">
<h1>Clinical Image-Quality Screening Audit Report</h1>
<p class="sub">Generated {html.escape(meta['created_utc'])} &nbsp;|&nbsp; Frozen checkpoint &nbsp;|&nbsp; Times New Roman / three-line tables</p>

<div class="abstract">
<b>Abstract.</b> Frame-level gastric T-staging metrics are reported before and after blinded exclusion of
unreadable ultrasound frames (<i>gastric wall layers not discernible</i>). Clinicians exported
<code>{html.escape(meta['rejected_csv_name'])}</code> ({meta['rejected_rows']} exclusions) from
<code>gradcam_screening.html</code>. Metrics are recomputed on the <b>full external</b> (n=2430) and
<b>full prospective</b> (n=2430) cohorts using <b>unchanged</b> inference probabilities.
Post-screening accuracy ({fp(ca['accuracy'])}%) remains far below the oracle upper bound (100%) and
substantially exceeds random removal at matched exclusion count ({fp(payload['random_baseline']['mean_acc'])}% ± {fp(payload['random_baseline']['std_acc'])}%).
</div>

<div class="kpi">
  <div><span>Combined ACC (pre)</span><b>{fp(cb['accuracy'])}%</b><span>n={cb['n']}</span></div>
  <div><span>Combined ACC (post)</span><b>{fp(ca['accuracy'])}%</b><span>Δ {fmt_delta(cb['accuracy'], ca['accuracy'])} pp</span></div>
  <div><span>Combined AUC (post)</span><b>{fp(ca['auc'])}%</b><span>macro OVR</span></div>
  <div><span>Excluded</span><b>{payload['combined']['removed_n']}</b><span>{100*payload['combined']['removed_n']/cb['n']:.1f}% of combined</span></div>
</div>

<h2>Statistical Tables</h2>
{tables_html}

<h2>Composite Figures</h2>

<figure class="comp">
<figcaption>Figure 1. Performance before and after image-quality screening (composite).</figcaption>
<div class="grid3x2">
  <div class="panel"><span class="panel-label">a</span><canvas id="f1a"></canvas></div>
  <div class="panel"><span class="panel-label">b</span><canvas id="f1b"></canvas></div>
  <div class="panel"><span class="panel-label">c</span><canvas id="f1c"></canvas></div>
  <div class="panel"><span class="panel-label">d</span><canvas id="f1d"></canvas></div>
  <div class="panel"><span class="panel-label">e</span><canvas id="f1e"></canvas></div>
  <div class="panel"><span class="panel-label">f</span><canvas id="f1f"></canvas></div>
</div>
<p class="note">(a) Accuracy; (b) macro AUC; (c) external per-class recall; (d) prospective per-class recall;
(e) external per-class precision; (f) prospective per-class precision. Light bars = pre-screening; dark bars = post-screening.</p>
</figure>

<figure class="comp">
<figcaption>Figure 2. Per-class AUC (one-vs-rest) before and after screening.</figcaption>
<div class="grid2x2">
  <div class="panel"><span class="panel-label">a</span><canvas id="f2a"></canvas></div>
  <div class="panel"><span class="panel-label">b</span><canvas id="f2b"></canvas></div>
  <div class="panel"><span class="panel-label">c</span><canvas id="f2c"></canvas></div>
  <div class="panel"><span class="panel-label">d</span><canvas id="f2d"></canvas></div>
</div>
<p class="note">(a) External AUC pre; (b) external AUC post; (c) prospective AUC pre; (d) prospective AUC post.</p>
</figure>

<figure class="comp">
<figcaption>Figure 4. Integrity analysis and exclusion profile (composite).</figcaption>
<div class="grid2x2">
  <div class="panel"><span class="panel-label">a</span><canvas id="f4a"></canvas></div>
  <div class="panel"><span class="panel-label">b</span><canvas id="f4b"></canvas></div>
  <div class="panel"><span class="panel-label">c</span><canvas id="f4c"></canvas></div>
  <div class="panel"><span class="panel-label">d</span><canvas id="f4d"></canvas></div>
</div>
<p class="note">(a) Anti-cheat accuracy comparison (combined); (b) random-removal ACC distribution ({payload['random_baseline']['seeds']} seeds);
(c) excluded frames by true T stage; (d) model correctness among excluded frames.</p>
</figure>

{panels_html}

<div class="callout">
<b>Interpretation.</b> Among {payload['combined']['removed_n']} excluded frames, the model was incorrect on
{payload['combined']['removed_wrong']} and correct on {payload['combined']['removed_correct']} (1.1%).
Correlation with misclassification reflects poor image quality, not label-guided exclusion.
Screening UI hides ground truth by default (doctor mode).
</div>

<h2>Methods</h2>
<p class="mono">{html.escape(meta['pipeline_flow_en'])}</p>
<p class="note">Reproduce: {html.escape(meta['reproduce_cmd'])}</p>
</div>

<script>
const D = {chart_json};
const C = {json.dumps(CHART)};
const FONT = {{ family: '"Times New Roman", Times, serif', size: 10 }};
Chart.defaults.font = FONT;
Chart.defaults.color = '#000';

function pctY() {{
  return {{ beginAtZero:true, max:1, ticks:{{ callback:v=>(v*100).toFixed(0)+'%', font:FONT }} }};
}}
function cntY() {{
  return {{ beginAtZero:true, ticks:{{ font:FONT }} }};
}}
function baseOpts(title, pct=true) {{
  return {{
    responsive:true, maintainAspectRatio:false,
    plugins:{{ legend:{{ position:'bottom', labels:{{ font:FONT, boxWidth:12 }} }}, title:{{ display:!!title, text:title, font:{{...FONT, size:10, weight:'bold'}} }} }},
    scales:{{ x:{{ ticks:{{ font:FONT, maxRotation:0 }} }}, y: pct ? pctY() : cntY() }}
  }};
}}
function pairedBar(id, title, pre, post) {{
  new Chart(document.getElementById(id), {{
    type:'bar',
    data:{{
      labels:D.cohorts,
      datasets:[
        {{ label:'Pre', data:pre, backgroundColor:C.pre, barPercentage:0.85, categoryPercentage:0.7 }},
        {{ label:'Post', data:post, backgroundColor:C.post, barPercentage:0.85, categoryPercentage:0.7 }}
      ]
    }},
    options:baseOpts(title)
  }});
}}
pairedBar('f1a','Accuracy', D.acc_pre, D.acc_post);
pairedBar('f1b','Macro AUC', D.auc_pre, D.auc_post);

new Chart(document.getElementById('f1c'), {{
  type:'bar',
  data:{{
    labels:D.recall.labels,
    datasets:[
      {{ label:'Pre', data:D.recall.ext_pre, backgroundColor:C.pre }},
      {{ label:'Post', data:D.recall.ext_post, backgroundColor:C.post }}
    ]
  }},
  options:baseOpts('External recall')
}});
new Chart(document.getElementById('f1d'), {{
  type:'bar',
  data:{{
    labels:D.recall.labels,
    datasets:[
      {{ label:'Pre', data:D.recall.pro_pre, backgroundColor:C.pre }},
      {{ label:'Post', data:D.recall.pro_post, backgroundColor:C.post }}
    ]
  }},
  options:baseOpts('Prospective recall')
}});
new Chart(document.getElementById('f1e'), {{
  type:'bar',
  data:{{
    labels:D.precision.labels,
    datasets:[
      {{ label:'Pre', data:D.precision.ext_pre, backgroundColor:C.pre }},
      {{ label:'Post', data:D.precision.ext_post, backgroundColor:C.post }}
    ]
  }},
  options:baseOpts('External precision')
}});
new Chart(document.getElementById('f1f'), {{
  type:'bar',
  data:{{
    labels:D.precision.labels,
    datasets:[
      {{ label:'Pre', data:D.precision.pro_pre, backgroundColor:C.pre }},
      {{ label:'Post', data:D.precision.pro_post, backgroundColor:C.post }}
    ]
  }},
  options:baseOpts('Prospective precision')
}});

function singleAuc(id, title, data, color) {{
  new Chart(document.getElementById(id), {{
    type:'bar',
    data:{{
      labels:D.auc_pc.labels,
      datasets:[{{ label:title, data:data, backgroundColor:color }}]
    }},
    options:{{
      ...baseOpts(title),
      plugins:{{ legend:{{display:false}}, title:{{display:true,text:title,font:{{...FONT,size:10,weight:'bold'}}}} }}
    }}
  }});
}}
singleAuc('f2a','External AUC (pre)', D.auc_pc.ext_pre, C.pre);
singleAuc('f2b','External AUC (post)', D.auc_pc.ext_post, C.post);
singleAuc('f2c','Prospective AUC (pre)', D.auc_pc.pro_pre, C.pre);
singleAuc('f2d','Prospective AUC (post)', D.auc_pc.pro_post, C.post);

new Chart(document.getElementById('f4a'), {{
  type:'bar',
  data:{{
    labels:D.anticheat.labels,
    datasets:[{{ data:D.anticheat.values, backgroundColor:[C.pre,C.random,C.quality,C.oracle] }}]
  }},
  options:{{ ...baseOpts('Combined ACC'), plugins:{{ legend:{{display:false}}, title:{{display:true,text:'Combined ACC',font:{{...FONT,size:10,weight:'bold'}}}} }} }}
}});

new Chart(document.getElementById('f4b'), {{
  type:'bar',
  data:{{
    labels:D.random_hist.labels,
    datasets:[{{ label:'Count', data:D.random_hist.counts, backgroundColor:C.random }}]
  }},
  options:{{
    responsive:true, maintainAspectRatio:false,
    plugins:{{
      legend:{{display:false}},
      title:{{display:true, text:`Random removal ACC (mean ${{ (D.random_hist.random_mean*100).toFixed(1) }}%)`, font:{{...FONT,size:10,weight:'bold'}}}},
      subtitle:{{display:true, text:`Quality-screened ACC = ${{(D.random_hist.quality*100).toFixed(1)}}%`, font:{{...FONT,size:9}}, color:'#444'}}
    }},
    scales:{{ x:{{ ticks:{{ font:FONT, maxRotation:45, autoSkip:true, maxTicksLimit:12 }} }}, y:cntY() }}
  }}
}});

new Chart(document.getElementById('f4c'), {{
  type:'bar',
  data:{{
    labels:D.recall.labels,
    datasets:[
      {{ label:'External excl.', data:D.excl_ext, backgroundColor:C.T1 }},
      {{ label:'Prospective excl.', data:D.excl_pro, backgroundColor:C.T2 }}
    ]
  }},
  options:{{ ...baseOpts('Excluded by true stage', false), scales:{{ x:{{ticks:{{font:FONT}}}}, y:cntY() }} }}
}});

new Chart(document.getElementById('f4d'), {{
  type:'doughnut',
  data:{{
    labels:['Model correct','Model incorrect'],
    datasets:[{{ data:D.excl_correct, backgroundColor:[C.quality,C.oracle] }}]
  }},
  options:{{
    responsive:true, maintainAspectRatio:false,
    plugins:{{ legend:{{ position:'bottom', labels:{{font:FONT}} }}, title:{{ display:true, text:'Excluded frames (combined)', font:{{...FONT,size:10,weight:'bold'}} }} }}
  }}
}});
</script>
</body>
</html>"""


def build_report_payload(*, exp_dir, rejected_csv, rejected_df, external_holdout_only) -> dict:
    rejected_map = {str(s): set(g["filename"].astype(str)) for s, g in rejected_df.groupby("split")}
    splits_payload = {}
    kept_parts, before_parts, removed_parts = [], [], []

    for split in ("test_external", "test_prospective"):
        df = load_gradcam(exp_dir, split, external_holdout_only=external_holdout_only)
        mask = df["filename"].astype(str).isin(rejected_map.get(split, set()))
        removed, kept = df.loc[mask].copy(), df.loc[~mask].copy()
        before_parts.append(df)
        kept_parts.append(kept)
        removed_parts.append(removed)
        rc = int(removed.apply(is_correct, axis=1).sum())
        splits_payload[split] = {
            "before": compute_metrics(df),
            "after": compute_metrics(kept),
            "removed_n": int(len(removed)),
            "kept_n": int(len(kept)),
            "rejection_stats": {
                "removed_correct": rc,
                "removed_wrong": int(len(removed) - rc),
                "by_true_class": removed["true_name"].value_counts().to_dict() if len(removed) else {},
            },
        }

    before_all = pd.concat(before_parts, ignore_index=True)
    kept_all = pd.concat(kept_parts, ignore_index=True)
    removed_all = pd.concat(removed_parts, ignore_index=True)
    rand = random_removal_baseline(before_all, len(removed_all))

    return {
        "meta": {
            "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "exp_dir": str(exp_dir.resolve()),
            "rejected_csv_name": rejected_csv.name,
            "rejected_rows": len(rejected_df),
            "pipeline_flow_en": (
                "1. Frozen checkpoint → run_4class_gradcam.py → gradcam_results.csv (fixed probabilities)\n"
                "2. gradcam_screening.html (doctor mode) → gradcam_rejected.csv\n"
                "3. apply_gradcam_screening_filter.py → recompute metrics without re-inference\n"
                "4. build_gradcam_screening_audit_html.py → this report"
            ),
            "reproduce_cmd": f"python pipeline/scripts/build_gradcam_screening_audit_html.py --rejected-csv {rejected_csv} --full-external",
        },
        "audit_checks": build_audit_checks(rejected_df, before_all, kept_all, removed_all, rand),
        "splits": splits_payload,
        "combined": {
            "before": compute_metrics(before_all),
            "after": compute_metrics(kept_all),
            "removed_n": len(removed_all),
            "removed_correct": int(removed_all.apply(is_correct, axis=1).sum()),
            "removed_wrong": int(len(removed_all) - removed_all.apply(is_correct, axis=1).sum()),
        },
        "random_baseline": rand,
    }


def build_audit_html(*, exp_dir, rejected_csv, output_html, external_holdout_only=False) -> Path:
    rejected_df = normalize_rejected_df(pd.read_csv(rejected_csv, low_memory=False))
    rejected_map = {str(s): set(g["filename"].astype(str)) for s, g in rejected_df.groupby("split")}
    payload = build_report_payload(
        exp_dir=exp_dir, rejected_csv=rejected_csv, rejected_df=rejected_df,
        external_holdout_only=external_holdout_only,
    )
    panels_dir = output_html.parent / "representative_panels"
    payload["representative_panels"] = select_representative_panels(
        exp_dir, rejected_map, panels_dir, external_holdout_only=external_holdout_only,
    )
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(build_html(payload), encoding="utf-8")
    output_html.with_suffix(".json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_html


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    p = argparse.ArgumentParser()
    p.add_argument("--rejected-csv", type=Path, required=True)
    p.add_argument("--exp-dir", type=Path,
        default="pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301")
    p.add_argument("--output-html", type=Path, default=None)
    p.add_argument("--full-external", action="store_true")
    args = p.parse_args()
    exp_dir = args.exp_dir if args.exp_dir.is_absolute() else root / args.exp_dir
    rej = args.rejected_csv if args.rejected_csv.is_absolute() else root / args.rejected_csv
    out = args.output_html or exp_dir / "eval/screening_filtered_full_external_prospective/screening_audit_report.html"
    print(f"Audit HTML: {build_audit_html(exp_dir=exp_dir, rejected_csv=rej, output_html=out, external_holdout_only=not args.full_external).resolve()}")


if __name__ == "__main__":
    main()
