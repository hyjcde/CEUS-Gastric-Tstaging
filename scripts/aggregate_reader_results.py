#!/usr/bin/env python3
"""Aggregate reader study results across readers × passes.

Reads reader JSONs exported from apps/tstage_reader_study/index.html and
joins with the v2 subset (truth T-stage, AI pred) to produce:

  1. per_case_<out-prefix>.csv      one row per (case × reader × pass)
  2. summary_<out-prefix>.md        cross-reader metrics + AI-uplift table
  3. summary_<out-prefix>.json      same metrics in machine-readable form

Usage:
    python3 scripts/aggregate_reader_results.py \
        --results-dir docs/clinical_validation/reader_study_150/collected_results \
        --subset-csv  docs/clinical_validation/reader_study_150/reader_subset_v2.csv \
        --out-prefix  aggregate_2026_06_12
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "docs/clinical_validation/reader_study_150/collected_results"
DEFAULT_SUBSET_CSV = PROJECT_ROOT / "docs/clinical_validation/reader_study_150/reader_subset_v2.csv"
DEFAULT_OUT_DIR = PROJECT_ROOT / "docs/clinical_validation/reader_study_150/aggregate"

# Skip partial exports (auto-saved mid-way) by default; opt-in via flag.
PARTIAL_SUFFIX_RE = re.compile(r"_partial(\.json)?$|partial\.json$", re.IGNORECASE)

T_TO_CODE = {"T1": 0, "T2": 1, "T3": 2, "T4": 3, "T4+": 3}
CODE_TO_T = {0: "T1", 1: "T2", 2: "T3", 3: "T4+"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR,
                   help="Folder of reader JSON exports (recursive glob *.json)")
    p.add_argument("--subset-csv", type=Path, default=DEFAULT_SUBSET_CSV,
                   help="v2 subset CSV (case_id, arm, pathology_t_stage, ai_pred, ...)")
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR,
                   help="Output directory")
    p.add_argument("--out-prefix", type=str, default="aggregate",
                   help="Output filename prefix")
    p.add_argument("--include-partial", action="store_true",
                   help="Include _partial JSONs (mid-session exports)")
    return p.parse_args()


def load_subset(path: Path) -> pd.DataFrame:
    """Load the v2 subset CSV and normalise truth / AI pred to T-stage strings.

    The CSV stores `pathology_t_stage` / `truth` / `ai_pred` as integer codes
    0=T1, 1=T2, 2=T3, 3=T4+ (the `truth` column may also be the same code, or
    a string 'T1'...'T4' depending on which script generated the subset).
    """
    df = pd.read_csv(path)
    if "pathology_t_stage" not in df.columns:
        raise SystemExit(f"subset CSV missing 'pathology_t_stage': {path}")
    df["truth"] = df["pathology_t_stage"].apply(_to_t_label)
    if "truth" in df.columns and df["truth"].dtype == object:
        # also normalise the pre-computed truth column if both exist
        df["truth"] = df["truth"].apply(_to_t_label)
    if "ai_pred" in df.columns:
        df["ai_choice"] = df["ai_pred"].apply(
            lambda x: CODE_TO_T.get(int(x), "T?")
        )
    return df


def _to_t_label(v: Any) -> str:
    """Normalise a raw truth/AI cell to T1/T2/T3/T4+."""
    if pd.isna(v):
        return "?"
    s = str(v).strip()
    if s in T_TO_CODE:
        return s
    if s in ("0", "1", "2", "3"):
        return CODE_TO_T[int(s)]
    if s.lower() in ("t4a", "t4b", "t4"):
        return "T4+"
    return s  # unknown — keep as-is


def collect_jsons(results_dir: Path, include_partial: bool) -> list[Path]:
    """Glob all reader JSONs in the results directory."""
    if not results_dir.exists():
        return []
    paths = sorted(results_dir.rglob("*.json"))
    if not include_partial:
        paths = [p for p in paths if not PARTIAL_SUFFIX_RE.search(p.name)]
    return paths


def parse_reader_json(path: Path) -> dict[str, Any] | None:
    """Parse one reader JSON; return None if schema doesn't match."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [skip] {path.name}: {e}", file=sys.stderr)
        return None
    # schema sanity
    for key in ("reader_id", "pass", "results"):
        if key not in data:
            print(f"  [skip] {path.name}: missing key '{key}'", file=sys.stderr)
            return None
    if not isinstance(data["results"], list):
        print(f"  [skip] {path.name}: 'results' not a list", file=sys.stderr)
        return None
    data["_source_file"] = path.name
    return data


def build_per_case(subset: pd.DataFrame, reader_data: list[dict]) -> pd.DataFrame:
    """One row per (case × reader × pass)."""
    # Index subset by case_id
    sub_idx = subset.set_index("case_id")

    rows = []
    for d in reader_data:
        rid = d["reader_id"]
        pass_num = d["pass"]
        for r in d["results"]:
            cid = r["case_id"]
            choice = r.get("t_choice", "SKIP")
            arm = r.get("arm", "")
            ts = r.get("ts", "")
            sub_row = sub_idx.loc[cid] if cid in sub_idx.index else None
            if sub_row is None:
                truth, ai_choice, cohort = "?", "?", "?"
            else:
                truth = sub_row.get("truth", "?")
                ai_choice = sub_row.get("ai_choice", "?")
                cohort = sub_row.get("cohort", "?")
            agree_ai = (choice == ai_choice) if ai_choice != "?" else None
            correct_truth = (choice == truth) if truth != "?" else None
            rows.append({
                "reader_id": rid,
                "pass": pass_num,
                "case_id": cid,
                "arm": arm,
                "cohort": cohort,
                "reader_choice": choice,
                "truth": truth,
                "ai_choice": ai_choice,
                "agree_with_ai": agree_ai,
                "correct_vs_truth": correct_truth,
                "ts": ts,
            })
    return pd.DataFrame(rows)


def cohens_kappa(annotations: list[str], references: list[str]) -> float | None:
    """Two-rater Cohen's kappa, all-class."""
    pairs = [(a, r) for a, r in zip(annotations, references)
             if a in T_TO_CODE and r in T_TO_CODE]
    if not pairs:
        return None
    n = len(pairs)
    classes = sorted({c for pair in pairs for c in pair})
    # observed agreement
    po = sum(1 for a, r in pairs if a == r) / n
    # expected agreement
    pe = 0.0
    for c in classes:
        p_a = sum(1 for a, _ in pairs if a == c) / n
        p_r = sum(1 for _, r in pairs if r == c) / n
        pe += p_a * p_r
    if pe >= 1.0:
        return None
    return (po - pe) / (1 - pe)


def compute_metrics(per_case: pd.DataFrame) -> dict[str, Any]:
    """Cross-reader metrics + AI uplift (paired, pass 2 - pass 1)."""
    out: dict[str, Any] = {"per_reader": {}, "ai_uplift": {}}

    valid = per_case[per_case["reader_choice"].isin(T_TO_CODE)].copy()
    valid["reader_code"] = valid["reader_choice"].map(T_TO_CODE)
    valid["truth_code"] = valid["truth"].map(T_TO_CODE)
    valid["ai_code"] = valid["ai_choice"].map(T_TO_CODE)

    # per-reader × per-pass
    for (rid, pn), g in valid.groupby(["reader_id", "pass"]):
        n = len(g)
        if n == 0:
            continue
        correct = g["correct_vs_truth"].sum()
        agree_ai = g["agree_with_ai"].sum()
        out["per_reader"].setdefault(rid, {})[f"pass{pn}"] = {
            "n_valid": int(n),
            "n_skipped": int((per_case[
                (per_case["reader_id"] == rid) & (per_case["pass"] == pn)
            ]["reader_choice"] == "SKIP").sum()),
            "accuracy_vs_truth": round(correct / n, 4),
            "n_correct": int(correct),
            "agree_with_ai_rate": round(agree_ai / n, 4),
            "n_agree_ai": int(agree_ai),
            "t_distribution": g["reader_choice"].value_counts().to_dict(),
        }

    # AI uplift: per-reader paired (pass 2 - pass 1), restricted to cases
    # both passes answered
    p1 = valid[valid["pass"] == 1].set_index(["reader_id", "case_id"])
    p2 = valid[valid["pass"] == 2].set_index(["reader_id", "case_id"])
    common = p1.index.intersection(p2.index)
    if len(common):
        reader_ids = sorted({c[0] for c in common})
        p1_readers = set(p1.index.get_level_values(0).unique())
        p2_readers = set(p2.index.get_level_values(0).unique())
        for rid in reader_ids:
            if rid not in p1_readers or rid not in p2_readers:
                continue
            p1r = p1.loc[rid]   # indexed by case_id only
            p2r = p2.loc[rid]
            common_cases = p1r.index.intersection(p2r.index)
            if len(common_cases) == 0:
                continue
            p1c = p1r.loc[common_cases]
            p2c = p2r.loc[common_cases]
            n = len(common_cases)
            p1_correct = (p1c["reader_code"] == p1c["truth_code"]).sum()
            p2_correct = (p2c["reader_code"] == p2c["truth_code"]).sum()
            out["ai_uplift"][rid] = {
                "n_paired": int(n),
                "pass1_accuracy": round(p1_correct / n, 4),
                "pass2_accuracy": round(p2_correct / n, 4),
                "abs_uplift": round((p2_correct - p1_correct) / n, 4),
            }

    # cross-reader kappa (pass 1 only, by default; extendable)
    p1_only = valid[valid["pass"] == 1]
    readers = sorted(p1_only["reader_id"].unique())
    if len(readers) >= 2:
        out["cohens_kappa_pass1"] = {}
        for i, r1 in enumerate(readers):
            for r2 in readers[i + 1:]:
                g1 = p1_only[p1_only["reader_id"] == r1].set_index("case_id")
                g2 = p1_only[p1_only["reader_id"] == r2].set_index("case_id")
                common = g1.index.intersection(g2.index)
                a = g1.loc[common, "reader_code"].astype(int).tolist()
                b = g2.loc[common, "reader_code"].astype(int).tolist()
                # convert back to T labels for kappa helper
                a_lab = [CODE_TO_T[x] for x in a]
                b_lab = [CODE_TO_T[x] for x in b]
                kap = cohens_kappa(a_lab, b_lab)
                if kap is not None:
                    out["cohens_kappa_pass1"][f"{r1}_vs_{r2}"] = round(kap, 4)

    return out


def render_markdown_summary(metrics: dict, per_case: pd.DataFrame,
                            n_partial: int, sources: list[str]) -> str:
    lines = []
    lines.append(f"# Reader study aggregate summary")
    lines.append(f"_Generated: {datetime.now().isoformat(timespec='seconds')}_")
    lines.append(f"_Sources: {len(sources)} JSON file(s) ({n_partial} partial excluded by default)_")
    if sources:
        for s in sources:
            lines.append(f"  - `{s}`")
    lines.append("")

    # per-reader table
    lines.append("## Per-reader × per-pass")
    lines.append("")
    lines.append("| Reader | Pass | n_valid | n_skip | accuracy_vs_truth | agree_with_ai | n_correct | n_agree_ai |")
    lines.append("|--------|------|--------:|-------:|------------------:|--------------:|----------:|-----------:|")
    pr = metrics.get("per_reader", {})
    for rid in sorted(pr):
        for pn in sorted(p for p in pr[rid] if p.startswith("pass")):
            d = pr[rid][pn]
            lines.append(
                f"| {rid} | {pn} | {d['n_valid']} | {d['n_skipped']} | "
                f"{d['accuracy_vs_truth']:.3f} | {d['agree_with_ai_rate']:.3f} | "
                f"{d['n_correct']} | {d['n_agree_ai']} |"
            )
    lines.append("")

    # AI uplift
    up = metrics.get("ai_uplift", {})
    if up:
        lines.append("## AI uplift (paired, Pass 2 − Pass 1)")
        lines.append("")
        lines.append("| Reader | n_paired | Pass 1 acc | Pass 2 acc | abs_uplift |")
        lines.append("|--------|---------:|-----------:|-----------:|-----------:|")
        for rid in sorted(up):
            d = up[rid]
            lines.append(
                f"| {rid} | {d['n_paired']} | {d['pass1_accuracy']:.3f} | "
                f"{d['pass2_accuracy']:.3f} | {d['abs_uplift']:+.3f} |"
            )
        lines.append("")

    # kappa
    kap = metrics.get("cohens_kappa_pass1", {})
    if kap:
        lines.append("## Inter-reader agreement (Cohen's κ, Pass 1)")
        lines.append("")
        lines.append("| Pair | κ |")
        lines.append("|------|--:|")
        for pair, k in sorted(kap.items()):
            lines.append(f"| {pair} | {k:.3f} |")
        lines.append("")

    # T-distribution sanity
    lines.append("## T-stage distribution (readers' choices)")
    lines.append("")
    valid = per_case[per_case["reader_choice"].isin(T_TO_CODE)]
    if not valid.empty:
        ct = valid.groupby(["reader_id", "pass", "reader_choice"]).size().unstack(fill_value=0)
        lines.append(ct.to_markdown())
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    # 1. collect
    paths = collect_jsons(args.results_dir, args.include_partial)
    if not paths:
        print(f"[warn] no reader JSONs in {args.results_dir}", file=sys.stderr)
        return 1
    print(f"[info] found {len(paths)} reader JSON(s) in {args.results_dir}")

    # 2. parse
    reader_data = []
    for p in paths:
        d = parse_reader_json(p)
        if d is not None:
            reader_data.append(d)
    if not reader_data:
        print("[err] no valid reader JSONs parsed", file=sys.stderr)
        return 1
    n_partial = sum(1 for p in paths if PARTIAL_SUFFIX_RE.search(p.name))
    sources = [d["_source_file"] for d in reader_data]

    # 3. load subset
    if not args.subset_csv.exists():
        print(f"[err] subset CSV not found: {args.subset_csv}", file=sys.stderr)
        return 1
    subset = load_subset(args.subset_csv)
    print(f"[info] subset has {len(subset)} cases (arms: {subset['arm'].value_counts().to_dict()})")

    # 4. per-case table
    per_case = build_per_case(subset, reader_data)
    per_case_csv = args.out_dir / f"per_case_{args.out_prefix}.csv"
    per_case.to_csv(per_case_csv, index=False)
    print(f"[ok] per-case -> {per_case_csv} ({len(per_case)} rows)")

    # 5. metrics
    metrics = compute_metrics(per_case)
    summary_json = args.out_dir / f"summary_{args.out_prefix}.json"
    summary_json.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[ok] summary JSON -> {summary_json}")

    # 6. markdown
    summary_md = args.out_dir / f"summary_{args.out_prefix}.md"
    summary_md.write_text(render_markdown_summary(metrics, per_case, n_partial, sources),
                          encoding="utf-8")
    print(f"[ok] summary MD   -> {summary_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
