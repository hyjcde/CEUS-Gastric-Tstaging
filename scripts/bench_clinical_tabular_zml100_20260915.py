#!/usr/bin/env python3
"""Clinical-tabular-only T-staging benchmark, evaluated on the ZML reader 100-case test set.

Question: with ONLY the clinical table, trained on ALL training data (train+val patient
pool), which ML model does best on zml100?

Feature variants:
  - clin11      : house clin11 *_norm + *_missing (22 cols; incl. tumor length/thickness)
  - clin9_safe  : drops tumor_length/thickness (provenance unclear, possible pathology
                  leakage + strongly T-correlated) -> 18 cols

Eval: zml100 clinical-covered cases (full + strict no-train/val-overlap),
prospective-full + external reference. Doctor and imaging-model context on identical cases.
TabPFN uses cached v2.5 weights (create_default_for_version), no license download.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, cohen_kappa_score, confusion_matrix, roc_auc_score
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

warnings.filterwarnings("ignore")

ROOT = Path("/data/research/gastric/GastricTstaging")
RD = ROOT / "pipeline/data/tstaging_4class_region_contrastive_full/regions"
PROSP_FULL = ROOT / "pipeline/data/tstaging_4class_prospective_full/test_prospective_full_clinical.csv"
ZML_MANIFEST = ROOT / "pipeline/data/zml_reader_100_testset_20260915/manifest.csv"
ZML_FRAMES = ROOT / "pipeline/data/zml_reader_100_testset_20260915/frames.csv"
ZML_IMG_EVAL = ROOT / "pipeline/experiments/reports/dinov3_roi_lora_mlp/zml100_eval_20260915"
OUT = ROOT / "pipeline/experiments/reports/clinical_tabular_zml100_20260915"
OUT.mkdir(parents=True, exist_ok=True)

CLIN11 = ["age_norm", "sex_norm", "lauren_type_norm", "differentiation_norm",
          "tumor_length_cm_norm", "tumor_thickness_cm_norm", "tumor_location_norm",
          "cea_value_norm", "ca199_value_norm", "cea_binary_norm", "ca199_binary_norm"]
CAT = ["sex_norm", "lauren_type_norm", "differentiation_norm",
       "tumor_location_norm", "cea_binary_norm", "ca199_binary_norm"]
SIZE_COLS = {"tumor_length_cm_norm", "tumor_thickness_cm_norm"}
CLASSES = ["T1", "T2", "T3", "T4+"]
LABEL_MAP = {"T1": 0, "T2": 1, "T3": 2, "T4": 3, "T4+": 3}


def feature_set(name: str) -> list[str]:
    base = [c for c in CLIN11 if not (name == "clin9_safe" and c in SIZE_COLS)]
    return base + [c.replace("_norm", "_missing") for c in base]


def patient_level(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values("class_label").groupby("patient_id", as_index=False).first()


def load_split(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df["patient_id"] = df["patient_id"].astype(str)
    return df


def metrics(y: np.ndarray, pred: np.ndarray, proba: np.ndarray | None) -> dict:
    out = {"acc": float(accuracy_score(y, pred)),
           "qwk": float(cohen_kappa_score(y, pred, weights="quadratic"))}
    if proba is not None and len(np.unique(y)) == 4:
        try:
            out["auc_macro"] = float(roc_auc_score(y, proba, multi_class="ovr", average="macro"))
        except Exception:
            out["auc_macro"] = None
    else:
        out["auc_macro"] = None
    cm = confusion_matrix(y, pred, labels=[0, 1, 2, 3])
    out["recall_per_class"] = {c: float(np.diag(cm)[i] / max(cm[i].sum(), 1)) for i, c in enumerate(CLASSES)}
    out["n"] = int(len(y))
    return out


def make_tabpfn(feats: list[str]):
    from tabpfn import TabPFNClassifier
    from tabpfn.constants import ModelVersion

    cat_idx = [i for i, c in enumerate(feats) if c in CAT]
    try:
        return TabPFNClassifier.create_default_for_version(
            ModelVersion.V2_5, device="cuda", random_state=0, n_estimators="auto",
            balance_probabilities=True, ignore_pretraining_limits=True,
            memory_saving_mode="auto", categorical_features_indices=cat_idx,
            show_progress_bar=False)
    except TypeError:
        return TabPFNClassifier.create_default_for_version(ModelVersion.V2_5)


def main() -> None:
    train_df = pd.concat([load_split(RD / "train_clinical.csv"), load_split(RD / "val_clinical.csv")])
    train_pat = patient_level(train_df)
    train_pids = set(train_pat["patient_id"])
    counts = np.bincount(train_pat["class_label"].to_numpy(dtype=int), minlength=4)
    print(f"[bench] train pool: {len(train_pat)} patients, class dist "
          f"{dict(zip(CLASSES, counts.tolist()))}", flush=True)

    zm = pd.read_csv(ZML_MANIFEST)
    zm["patient_id"] = zm["patient_id"].astype(str)
    sources = [RD / "train_clinical.csv", RD / "val_clinical.csv",
               RD / "test_prospective_clinical.csv", RD / "test_external_clinical.csv",
               PROSP_FULL]
    lookup = patient_level(pd.concat(
        [load_split(s)[lambda d: d["patient_id"].isin(set(zm["patient_id"]))] for s in sources]))
    zml = zm.merge(lookup[["patient_id"] + feature_set("clin11")], on="patient_id", how="left")
    zml["class_label"] = zml["src_pT"].map(LABEL_MAP)
    zml_cov = zml[zml["age_norm"].notna()].copy()
    zml_cov["leak"] = zml_cov["patient_id"].isin(train_pids)
    print(f"[bench] zml100 clinical coverage: {len(zml_cov)}/100 "
          f"(leak-in-train/val: {int(zml_cov['leak'].sum())})", flush=True)

    prosp = patient_level(load_split(PROSP_FULL))
    ext = patient_level(load_split(RD / "test_external_clinical.csv"))

    eval_dfs = {
        "zml100_full": zml_cov,
        "zml100_strict": zml_cov[~zml_cov["leak"]],
        "prospective_full": prosp,
        "external": ext,
    }

    models = {
        "prior_majority": lambda: DummyClassifier(strategy="prior"),
        "logreg": lambda: make_pipeline(StandardScaler(), LogisticRegression(
            max_iter=3000, class_weight="balanced", C=1.0)),
        "svm_rbf": lambda: make_pipeline(StandardScaler(), SVC(
            kernel="rbf", C=1.0, class_weight="balanced", probability=True, random_state=0)),
        "knn15": lambda: make_pipeline(StandardScaler(), KNeighborsClassifier(n_neighbors=15)),
        "mlp_128x2": lambda: make_pipeline(StandardScaler(), MLPClassifier(
            hidden_layer_sizes=(128, 128), max_iter=600, early_stopping=True, random_state=0)),
        "random_forest": lambda: RandomForestClassifier(
            n_estimators=600, class_weight="balanced", random_state=0, n_jobs=8),
        "extra_trees": lambda: ExtraTreesClassifier(
            n_estimators=600, class_weight="balanced", random_state=0, n_jobs=8),
        "histgb": lambda: HistGradientBoostingClassifier(random_state=0),
        "xgboost": lambda: __import__("xgboost").XGBClassifier(
            n_estimators=500, max_depth=4, learning_rate=0.05, subsample=0.9,
            colsample_bytree=0.9, tree_method="hist", random_state=0, n_jobs=8,
            objective="multi:softprob", num_class=4),
        "lightgbm": lambda: __import__("lightgbm").LGBMClassifier(
            n_estimators=500, learning_rate=0.05, class_weight="balanced",
            random_state=0, n_jobs=8, verbose=-1),
        "tabpfn_v25": None,  # constructed per feature set
    }

    results: list[dict] = []
    for feat_name in ["clin11", "clin9_safe"]:
        feats = feature_set(feat_name)
        X_train = train_pat[feats].to_numpy(dtype=np.float32)
        y_train = train_pat["class_label"].to_numpy(dtype=int)
        sw = (len(y_train) / (4 * counts))[y_train]

        for name in models:
            print(f"[bench] {feat_name} / {name} ...", flush=True)
            try:
                clf = make_tabpfn(feats) if name == "tabpfn_v25" else models[name]()
                if name == "xgboost":
                    clf.fit(X_train, y_train, sample_weight=sw)
                else:
                    clf.fit(X_train, y_train)
            except Exception as exc:
                print(f"[bench] {name} FAILED at fit: {exc}", flush=True)
                continue
            for set_name, df in eval_dfs.items():
                if df.empty:
                    continue
                X = df[feats].to_numpy(dtype=np.float32)
                y = df["class_label"].to_numpy(dtype=int)
                try:
                    pred = clf.predict(X)
                    proba = clf.predict_proba(X) if hasattr(clf, "predict_proba") else None
                    if proba is not None and getattr(proba, "shape", (0, 0))[1] != 4:
                        proba = None
                except Exception as exc:
                    print(f"[bench] {name} FAILED on {set_name}: {exc}", flush=True)
                    continue
                m = metrics(y, pred, proba)
                m.update({"model": name, "features": feat_name, "eval_set": set_name})
                results.append(m)
                if set_name.startswith("zml100"):
                    zp = df[["case_id", "patient_id", "src_pT", "class_label", "leak"]].copy()
                    zp["pred"] = pred
                    zp.to_csv(OUT / f"zml100_preds_{feat_name}_{name}_{set_name}.csv", index=False)
            acc_f = [r["acc"] for r in results if r["model"] == name
                     and r["features"] == feat_name and r["eval_set"] == "zml100_full"]
            acc_s = [r["acc"] for r in results if r["model"] == name
                     and r["features"] == feat_name and r["eval_set"] == "zml100_strict"]
            print(f"[bench] {feat_name}/{name}: full={acc_f} strict={acc_s}", flush=True)

    res_df = pd.DataFrame(results)
    res_df.to_csv(OUT / "clinical_tabular_benchmark_results.csv", index=False)

    # ---------- doctor + imaging context on identical cases ----------
    covered_pids = set(zml_cov["patient_id"])
    covered_cases = set(zml_cov["case_id"])
    strict_cases = set(zml_cov.loc[~zml_cov["leak"], "case_id"])
    frames = pd.read_csv(ZML_FRAMES, low_memory=False)
    doc = frames.groupby("case_id")["zml_ct"].first().dropna().map(LABEL_MAP)
    gold = zml.set_index("case_id")["class_label"]

    ctx: dict[str, object] = {}
    for scope, case_set in [("covered76", covered_cases), ("strict39", strict_cases)]:
        common = [c for c in case_set if c in doc.index and c in gold.index]
        if common:
            ctx[f"doctor_zml@{scope}"] = metrics(gold.loc[common].to_numpy(),
                                                 doc.loc[common].to_numpy(), None)
        for img_model in ["official", "aggressive", "gentle"]:
            f = ZML_IMG_EVAL / f"zml100_{img_model}_case_predictions.csv"
            if f.exists():
                cp = pd.read_csv(f)
                cp = cp[cp["patient_id"].isin(case_set)]
                if len(cp):
                    ctx[f"{img_model}@{scope}"] = metrics(cp["class_label"].to_numpy(),
                                                          cp["pred"].to_numpy(), None)

    payload = {
        "feature_sets": {"clin11": feature_set("clin11"), "clin9_safe": feature_set("clin9_safe")},
        "n_train_patients": int(len(train_pat)),
        "train_class_dist": {CLASSES[i]: int(counts[i]) for i in range(4)},
        "zml100_clinical_coverage": int(len(zml_cov)),
        "zml100_leak_cases": int(zml_cov["leak"].sum()),
        "results": results,
        "context": ctx,
    }
    (OUT / "clinical_tabular_benchmark_summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    for scope in ["zml100_full", "zml100_strict", "prospective_full", "external"]:
        print(f"\n=== {scope} ===")
        sub = res_df[res_df["eval_set"] == scope].sort_values("acc", ascending=False)
        print(sub[["model", "features", "acc", "qwk", "auc_macro", "n"]].to_string(index=False))
    print("\n=== context ===")
    for k, v in ctx.items():
        print(f"{k:24s} acc={v['acc']:.3f} qwk={v['qwk']:.3f} n={v['n']}")
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
