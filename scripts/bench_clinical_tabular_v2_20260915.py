#!/usr/bin/env python3
"""Extended clinical-tabular T-staging benchmark (v2): more models + tuning + fusion.

Adds on top of v1 (bench_clinical_tabular_zml100_20260915.py):
  - catboost, optuna-tuned RF/XGB/LGBM (5-fold patient-level CV on train pool, QWK objective)
  - ordinal models (ridge-round; cumulative binary decomposition with logreg)
  - soft-voting ensemble of v1 top-4
  - FUSION: official imaging cls probs (patient-level mean) + clin features -> logreg/RF/LGBM,
    fusion head trained on val (n=140), evaluated on external / zml100 / prospective

Clean reads: external (n=381, zero train overlap) and zml100_strict (n=39).
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, cohen_kappa_score, confusion_matrix, roc_auc_score
from sklearn.model_selection import StratifiedKFold
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
ZML_IMG_EVAL = ROOT / "pipeline/experiments/reports/dinov3_roi_lora_mlp/zml100_eval_20260915"
CLS_RUN = ROOT / "pipeline/experiments/reports/dinov3_roi_lora_mlp/phase0_20260828_full"
OUT = ROOT / "pipeline/experiments/reports/clinical_tabular_zml100_20260915"
OUT.mkdir(parents=True, exist_ok=True)

CLIN11 = ["age_norm", "sex_norm", "lauren_type_norm", "differentiation_norm",
          "tumor_length_cm_norm", "tumor_thickness_cm_norm", "tumor_location_norm",
          "cea_value_norm", "ca199_value_norm", "cea_binary_norm", "ca199_binary_norm"]
CAT = ["sex_norm", "lauren_type_norm", "differentiation_norm",
       "tumor_location_norm", "cea_binary_norm", "ca199_binary_norm"]
SIZE_COLS = {"tumor_length_cm_norm", "tumor_thickness_cm_norm"}
CLASSES = ["T1", "T2", "T3", "T4+"]
PROB_COLS = [f"prob_{c}" for c in CLASSES]
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


def metrics(y, pred, proba):
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


# ---------------- ordinal models ----------------
class RidgeRound:
    def fit(self, X, y):
        self.m = Ridge(alpha=1.0)
        self.m.fit(X, y.astype(float))
        return self

    def predict(self, X):
        return np.clip(np.round(self.m.predict(X)), 0, 3).astype(int)

    def predict_proba(self, X):
        s = np.clip(self.m.predict(X), 0, 3)
        d = np.abs(s[:, None] - np.arange(4)[None, :])
        p = np.exp(-2.0 * d)
        return p / p.sum(axis=1, keepdims=True)


class OrdinalLogReg:
    """Cumulative binary decomposition: P(y>k) for k=0..2, multinomial from differences."""

    def fit(self, X, y):
        self.heads = []
        for k in range(3):
            h = make_pipeline(StandardScaler(), LogisticRegression(
                max_iter=3000, class_weight="balanced"))
            h.fit(X, (y > k).astype(int))
            self.heads.append(h)
        return self

    def predict_proba(self, X):
        gt = np.stack([h.predict_proba(X)[:, 1] for h in self.heads], axis=1)  # P(y>k)
        p0 = 1 - gt[:, 0]
        p1 = gt[:, 0] - gt[:, 1]
        p2 = gt[:, 1] - gt[:, 2]
        p3 = gt[:, 2]
        p = np.clip(np.stack([p0, p1, p2, p3], axis=1), 1e-6, None)
        return p / p.sum(axis=1, keepdims=True)

    def predict(self, X):
        return self.predict_proba(X).argmax(axis=1)


# ---------------- optuna tuning ----------------
def tune(model_kind: str, X, y, n_trials: int = 30) -> dict:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)

    def build(trial):
        if model_kind == "rf":
            return RandomForestClassifier(
                n_estimators=trial.suggest_int("n_estimators", 300, 900),
                max_depth=trial.suggest_int("max_depth", 3, 18),
                min_samples_leaf=trial.suggest_int("min_samples_leaf", 1, 12),
                max_features=trial.suggest_float("max_features", 0.3, 1.0),
                class_weight="balanced", random_state=0, n_jobs=8)
        if model_kind == "xgb":
            return __import__("xgboost").XGBClassifier(
                n_estimators=trial.suggest_int("n_estimators", 300, 900),
                max_depth=trial.suggest_int("max_depth", 2, 8),
                learning_rate=trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                subsample=trial.suggest_float("subsample", 0.6, 1.0),
                colsample_bytree=trial.suggest_float("colsample_bytree", 0.5, 1.0),
                min_child_weight=trial.suggest_float("min_child_weight", 0.5, 8.0),
                tree_method="hist", random_state=0, n_jobs=8,
                objective="multi:softprob", num_class=4)
        return __import__("lightgbm").LGBMClassifier(
            n_estimators=trial.suggest_int("n_estimators", 300, 900),
            learning_rate=trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            num_leaves=trial.suggest_int("num_leaves", 7, 63),
            min_child_samples=trial.suggest_int("min_child_samples", 5, 60),
            feature_fraction=trial.suggest_float("feature_fraction", 0.5, 1.0),
            class_weight="balanced", random_state=0, n_jobs=8, verbose=-1)

    def objective(trial):
        scores = []
        for tr_idx, va_idx in cv.split(X, y):
            clf = build(trial)
            if model_kind == "xgb":
                counts = np.bincount(y[tr_idx], minlength=4)
                clf.fit(X[tr_idx], y[tr_idx],
                        sample_weight=(len(tr_idx) / (4 * counts))[y[tr_idx]])
            else:
                clf.fit(X[tr_idx], y[tr_idx])
            scores.append(cohen_kappa_score(y[va_idx], clf.predict(X[va_idx]), weights="quadratic"))
        return float(np.mean(scores))

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    print(f"[tune] {model_kind} best CV QWK={study.best_value:.4f} params={study.best_params}", flush=True)
    return study.best_params


def main() -> None:
    # ---------- data ----------
    train_df = pd.concat([load_split(RD / "train_clinical.csv"), load_split(RD / "val_clinical.csv")])
    train_pat = patient_level(train_df)
    train_pids = set(train_pat["patient_id"])
    counts = np.bincount(train_pat["class_label"].to_numpy(dtype=int), minlength=4)

    zm = pd.read_csv(ZML_MANIFEST)
    zm["patient_id"] = zm["patient_id"].astype(str)
    sources = [RD / "train_clinical.csv", RD / "val_clinical.csv",
               RD / "test_prospective_clinical.csv", RD / "test_external_clinical.csv", PROSP_FULL]
    lookup = patient_level(pd.concat(
        [load_split(s)[lambda d: d["patient_id"].isin(set(zm["patient_id"]))] for s in sources]))
    zml = zm.merge(lookup[["patient_id"] + feature_set("clin11")], on="patient_id", how="left")
    zml["class_label"] = zml["src_pT"].map(LABEL_MAP)
    zml_cov = zml[zml["age_norm"].notna()].copy()
    zml_cov["leak"] = zml_cov["patient_id"].isin(train_pids)

    prosp = patient_level(load_split(PROSP_FULL))
    ext = patient_level(load_split(RD / "test_external_clinical.csv"))

    # ---------- imaging probs (official cls model), patient level ----------
    def img_probs(frame_csv: Path) -> pd.DataFrame:
        df = pd.read_csv(frame_csv, low_memory=False)
        g = df.groupby("patient_id", as_index=False)
        out = g[PROB_COLS].mean()
        out.columns = ["patient_id"] + [f"img_p{i}" for i in range(4)]
        out["patient_id"] = out["patient_id"].astype(str)
        return out

    img = {
        "val": img_probs(CLS_RUN / "val_frame_predictions.csv"),
        "external": img_probs(CLS_RUN / "test_external_frame_predictions.csv"),
        "prospective_full": img_probs(CLS_RUN / "test_prospective_frame_predictions.csv"),
    }
    zml_img = pd.read_csv(ZML_IMG_EVAL / "zml100_official_case_predictions.csv")
    zml_img = zml_img.rename(columns={c: f"img_p{i}" for i, c in enumerate(PROB_COLS)})
    zml_img = zml_img[["patient_id"] + [f"img_p{i}" for i in range(4)]]  # patient_id == CASE-xxx

    val_pat = patient_level(load_split(RD / "val_clinical.csv"))
    val_fuse = val_pat.merge(img["val"], on="patient_id", how="inner")
    ext_fuse = ext.merge(img["external"], on="patient_id", how="inner")
    prosp_fuse = prosp.merge(img["prospective_full"], on="patient_id", how="inner")
    zml_fuse = zml_cov.merge(zml_img, left_on="case_id", right_on="patient_id", how="inner",
                             suffixes=("", "_img"))
    print(f"[fuse] val={len(val_fuse)} ext={len(ext_fuse)} prosp={len(prosp_fuse)} zml={len(zml_fuse)}",
          flush=True)

    eval_dfs = {
        "zml100_full": zml_cov,
        "zml100_strict": zml_cov[~zml_cov["leak"]],
        "prospective_full": prosp,
        "external": ext,
    }
    fuse_eval = {
        "zml100_full": zml_fuse,
        "zml100_strict": zml_fuse[~zml_fuse["leak"]],
        "prospective_full": prosp_fuse,
        "external": ext_fuse,
    }

    results: list[dict] = []

    def run_eval(clf, name: str, feat_cols: list[str], tag: str, train_df_, eval_map,
                 prefitted: bool = False):
        if not prefitted:
            Xtr = train_df_[feat_cols].to_numpy(dtype=np.float32)
            ytr = train_df_["class_label"].to_numpy(dtype=int)
            counts_ = np.bincount(ytr, minlength=4)
            sw_ = (len(ytr) / (4 * counts_))[ytr]
            try:
                if name.startswith("xgboost"):
                    clf.fit(Xtr, ytr, sample_weight=sw_)
                else:
                    clf.fit(Xtr, ytr)
            except Exception as exc:
                print(f"[v2] {tag}/{name} fit FAILED: {exc}", flush=True)
                return
        for set_name, df in eval_map.items():
            if df.empty:
                continue
            X = df[feat_cols].to_numpy(dtype=np.float32)
            y = df["class_label"].to_numpy(dtype=int)
            try:
                pred = clf.predict(X)
                proba = clf.predict_proba(X) if hasattr(clf, "predict_proba") else None
                if proba is not None and getattr(proba, "shape", (0, 0))[1] != 4:
                    proba = None
            except Exception as exc:
                print(f"[v2] {tag}/{name} eval FAILED on {set_name}: {exc}", flush=True)
                continue
            m = metrics(y, pred, proba)
            m.update({"model": name, "features": tag, "eval_set": set_name})
            results.append(m)
        line = {r["eval_set"]: round(r["acc"], 3) for r in results if r["model"] == name and r["features"] == tag}
        print(f"[v2] {tag}/{name}: {line}", flush=True)

    IMG4 = [f"img_p{i}" for i in range(4)]

    for feat_name in ["clin11", "clin9_safe"]:
        feats = feature_set(feat_name)
        X_train = train_pat[feats].to_numpy(dtype=np.float32)
        y_train = train_pat["class_label"].to_numpy(dtype=int)
        sw = (len(y_train) / (4 * counts))[y_train]

        zoo: dict[str, object] = {}
        zoo["catboost"] = lambda: __import__("catboost").CatBoostClassifier(
            iterations=600, learning_rate=0.05, depth=6, loss_function="MultiClass",
            auto_class_weights="Balanced", random_state=0, verbose=False)
        zoo["ridge_round"] = lambda: make_pipeline(StandardScaler(), RidgeRound())
        zoo["ordinal_logreg"] = lambda: OrdinalLogReg()
        zoo["rf_tuned"] = lambda: RandomForestClassifier(
            **tune("rf", X_train, y_train), class_weight="balanced", random_state=0, n_jobs=8)
        zoo["xgboost_tuned"] = lambda: __import__("xgboost").XGBClassifier(
            **tune("xgb", X_train, y_train), tree_method="hist", random_state=0, n_jobs=8,
            objective="multi:softprob", num_class=4)
        zoo["lightgbm_tuned"] = lambda: __import__("lightgbm").LGBMClassifier(
            **tune("lgbm", X_train, y_train), class_weight="balanced", random_state=0,
            n_jobs=8, verbose=-1)

        fitted: dict[str, object] = {}
        for name, ctor in zoo.items():
            print(f"[v2] {feat_name}/{name} ...", flush=True)
            try:
                clf = ctor()
                run_eval(clf, name, feats, feat_name, train_pat, eval_dfs)
                fitted[name] = clf
            except Exception as exc:
                print(f"[v2] {feat_name}/{name} FAILED: {exc}", flush=True)

        # soft vote of v1 top4 (refit quickly) + tuned trees
        try:
            from tabpfn import TabPFNClassifier
            from tabpfn.constants import ModelVersion
            cat_idx = [i for i, c in enumerate(feats) if c in CAT]
            top4 = {
                "rf": RandomForestClassifier(n_estimators=600, class_weight="balanced",
                                             random_state=0, n_jobs=8),
                "xgb": __import__("xgboost").XGBClassifier(
                    n_estimators=500, max_depth=4, learning_rate=0.05, subsample=0.9,
                    colsample_bytree=0.9, tree_method="hist", random_state=0, n_jobs=8,
                    objective="multi:softprob", num_class=4),
                "lgbm": __import__("lightgbm").LGBMClassifier(
                    n_estimators=500, learning_rate=0.05, class_weight="balanced",
                    random_state=0, n_jobs=8, verbose=-1),
                "tabpfn": TabPFNClassifier.create_default_for_version(
                    ModelVersion.V2_5, device="cuda", random_state=0,
                    balance_probabilities=True, ignore_pretraining_limits=True,
                    memory_saving_mode="auto", categorical_features_indices=cat_idx,
                    show_progress_bar=False),
            }
            for m_ in top4.values():
                m_.fit(X_train, y_train)

            class SoftVote:
                def predict_proba(self, X):
                    return np.mean([m_.predict_proba(X) for m_ in top4.values()], axis=0)

                def predict(self, X):
                    return self.predict_proba(X).argmax(axis=1)

            run_eval(SoftVote(), "softvote_rf_xgb_lgbm_tabpfn", feats, feat_name,
                     train_pat.head(0), eval_dfs, prefitted=True)
        except Exception as exc:
            print(f"[v2] {feat_name}/softvote FAILED: {exc}", flush=True)

        # ---------- fusion: imaging probs + clin ----------
        fuse_feats = IMG4 + feats
        for fname, fctor in {
            "fusion_logreg": lambda: make_pipeline(StandardScaler(), LogisticRegression(
                max_iter=3000, class_weight="balanced", C=1.0)),
            "fusion_rf": lambda: RandomForestClassifier(
                n_estimators=600, class_weight="balanced", random_state=0, n_jobs=8),
            "fusion_lightgbm": lambda: __import__("lightgbm").LGBMClassifier(
                n_estimators=500, learning_rate=0.05, class_weight="balanced",
                random_state=0, n_jobs=8, verbose=-1),
        }.items():
            print(f"[v2] {feat_name}/{fname} ...", flush=True)
            try:
                run_eval(fctor(), fname, fuse_feats, f"{feat_name}+img", val_fuse, fuse_eval)
            except Exception as exc:
                print(f"[v2] {feat_name}/{fname} FAILED: {exc}", flush=True)

    # imaging-only reference rows
    for set_name, df in [("external", ext_fuse), ("prospective_full", prosp_fuse),
                         ("zml100_full", zml_fuse), ("zml100_strict", zml_fuse[~zml_fuse["leak"]])]:
        if df.empty:
            continue
        y = df["class_label"].to_numpy(dtype=int)
        proba = df[IMG4].to_numpy(dtype=float)
        m = metrics(y, proba.argmax(axis=1), proba)
        m.update({"model": "imaging_only_official", "features": "img_probs", "eval_set": set_name})
        results.append(m)

    res_df = pd.DataFrame(results)
    res_df.to_csv(OUT / "clinical_tabular_benchmark_v2_results.csv", index=False)
    (OUT / "clinical_tabular_benchmark_v2_summary.json").write_text(
        json.dumps({"results": results}, indent=2, ensure_ascii=False), encoding="utf-8")

    for scope in ["external", "zml100_strict", "zml100_full", "prospective_full"]:
        print(f"\n=== {scope} (v2) ===")
        sub = res_df[res_df["eval_set"] == scope].sort_values("acc", ascending=False)
        print(sub[["model", "features", "acc", "qwk", "auc_macro", "n"]].head(14).to_string(index=False))
    print(f"\n-> {OUT}")


if __name__ == "__main__":
    main()
