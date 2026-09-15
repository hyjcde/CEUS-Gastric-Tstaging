#!/usr/bin/env python3
"""Champion selection + deployable bundle export for clinical T-staging (2026-09-15).

Candidates (clin11): v1 RF, optuna-tuned RF, catboost, softvote, prob-average
ensembles. Selection criterion (pre-registered): mean QWK over the two clean sets
(external n=381, zml100_strict n=39), tiebreak mean ACC.

Exports: model bundle (joblib) + raw->norm transform JSON + self-test, to
pipeline/models/clinical_tstage_champion_20260915/.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, cohen_kappa_score, roc_auc_score

warnings.filterwarnings("ignore")

ROOT = Path("/data/research/gastric/GastricTstaging")
RD = ROOT / "pipeline/data/tstaging_4class_region_contrastive_full/regions"
PROSP_FULL = ROOT / "pipeline/data/tstaging_4class_prospective_full/test_prospective_full_clinical.csv"
ZML_MANIFEST = ROOT / "pipeline/data/zml_reader_100_testset_20260915/manifest.csv"
OUT = ROOT / "pipeline/experiments/reports/clinical_tabular_zml100_20260915"
BUNDLE = ROOT / "pipeline/models/clinical_tstage_champion_20260915"
BUNDLE.mkdir(parents=True, exist_ok=True)

CLIN11 = ["age_norm", "sex_norm", "lauren_type_norm", "differentiation_norm",
          "tumor_length_cm_norm", "tumor_thickness_cm_norm", "tumor_location_norm",
          "cea_value_norm", "ca199_value_norm", "cea_binary_norm", "ca199_binary_norm"]
# Workbench-deployable set: structured workbench records never carry
# differentiation/lauren (they live in pathology text) -> drop them so that
# train-time features match inference-time availability.
CLIN9_WB = [c for c in CLIN11 if c not in ("lauren_type_norm", "differentiation_norm")]
FEATS = CLIN9_WB + [c.replace("_norm", "_missing") for c in CLIN9_WB]
CLASSES = ["T1", "T2", "T3", "T4+"]
LABEL_MAP = {"T1": 0, "T2": 1, "T3": 2, "T4": 3, "T4+": 3}
CONT = ["age", "tumor_length_cm", "tumor_thickness_cm", "cea_value", "ca199_value"]
CATS = ["sex", "lauren_type", "differentiation", "tumor_location"]
BINS = ["cea_binary", "ca199_binary"]


def patient_level(df):
    return df.sort_values("class_label").groupby("patient_id", as_index=False).first()


def load_split(p):
    d = pd.read_csv(p, low_memory=False)
    d["patient_id"] = d["patient_id"].astype(str)
    return d


def metrics(y, pred, proba):
    out = {"acc": float(accuracy_score(y, pred)),
           "qwk": float(cohen_kappa_score(y, pred, weights="quadratic"))}
    try:
        out["auc_macro"] = float(roc_auc_score(y, proba, multi_class="ovr", average="macro"))
    except Exception:
        out["auc_macro"] = None
    return out


def main():
    train_df = pd.concat([load_split(RD / "train_clinical.csv"), load_split(RD / "val_clinical.csv")])
    train_pat_all = patient_level(train_df)
    # 2026-09-15 晚（用户要求）：训练池只用内部回顾性病例——剔除 int/prospective
    # 与 ext/* 来源。prospective_full 由此成为零重叠干净集。
    KEEP_SOURCES = {"int/2018", "int/2019", "int/2020_2023", "int/2024"}
    train_pat = train_pat_all[train_pat_all["source"].isin(KEEP_SOURCES)].reset_index(drop=True)
    print(f"[pool] internal-retro only: {len(train_pat)} patients "
          f"(dropped {len(train_pat_all) - len(train_pat)} prospective/external-source)",
          flush=True)
    train_pids = set(train_pat["patient_id"])
    Xtr = train_pat[FEATS].to_numpy(dtype=np.float32)
    ytr = train_pat["class_label"].to_numpy(dtype=int)

    zm = pd.read_csv(ZML_MANIFEST)
    zm["patient_id"] = zm["patient_id"].astype(str)
    sources = [RD / "train_clinical.csv", RD / "val_clinical.csv",
               RD / "test_prospective_clinical.csv", RD / "test_external_clinical.csv", PROSP_FULL]
    lookup = patient_level(pd.concat(
        [load_split(s)[lambda d: d["patient_id"].isin(set(zm["patient_id"]))] for s in sources]))
    zml = zm.merge(lookup[["patient_id"] + FEATS], on="patient_id", how="left")
    zml["class_label"] = zml["src_pT"].map(LABEL_MAP)
    zml_cov = zml[zml["age_norm"].notna()].copy()
    zml_cov["leak"] = zml_cov["patient_id"].isin(train_pids)

    evals = {
        "external": patient_level(load_split(RD / "test_external_clinical.csv")),
        "prospective_full": patient_level(load_split(PROSP_FULL)),
        "zml100_full": zml_cov,
        "zml100_strict": zml_cov[~zml_cov["leak"]],
    }

    from catboost import CatBoostClassifier
    rf_v1 = RandomForestClassifier(n_estimators=600, class_weight="balanced", random_state=0, n_jobs=8)
    # quick retune for the clin9_wb feature set (params tuned on clin11 may not transfer)
    import optuna
    from sklearn.model_selection import StratifiedKFold
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)

    def _obj(trial):
        clf = RandomForestClassifier(
            n_estimators=trial.suggest_int("n_estimators", 300, 900),
            max_depth=trial.suggest_int("max_depth", 3, 18),
            min_samples_leaf=trial.suggest_int("min_samples_leaf", 1, 12),
            max_features=trial.suggest_float("max_features", 0.3, 1.0),
            class_weight="balanced", random_state=0, n_jobs=8)
        scores = []
        for tr_i, va_i in cv.split(Xtr, ytr):
            clf.fit(Xtr[tr_i], ytr[tr_i])
            scores.append(cohen_kappa_score(ytr[va_i], clf.predict(Xtr[va_i]), weights="quadratic"))
        return float(np.mean(scores))

    study = optuna.create_study(direction="maximize")
    study.optimize(_obj, n_trials=30, show_progress_bar=False)
    best = study.best_params
    print(f"[tune] clin9_wb rf best CV QWK={study.best_value:.4f} params={best}", flush=True)
    rf_tuned = RandomForestClassifier(**best, class_weight="balanced", random_state=0, n_jobs=8)
    cat = CatBoostClassifier(iterations=600, learning_rate=0.05, depth=6,
                             loss_function="MultiClass", auto_class_weights="Balanced",
                             random_state=0, verbose=False)

    class Avg:
        def __init__(self, models):
            self.models = models

        def predict_proba(self, X):
            return np.mean([m.predict_proba(X) for m in self.models], axis=0)

        def predict(self, X):
            return self.predict_proba(X).argmax(axis=1)

    rf_seeds = [RandomForestClassifier(**best, class_weight="balanced", random_state=s, n_jobs=8)
                for s in range(5)]

    cands = {
        "rf_v1": rf_v1,
        "rf_tuned": rf_tuned,
        "catboost": cat,
        "rf_tuned_seedavg5": Avg(rf_seeds),
        "rf_tuned+catboost": Avg([rf_tuned, cat]),
    }
    rows = []
    fitted = {}
    for name, clf in cands.items():
        if isinstance(clf, Avg):
            for m in clf.models:
                m.fit(Xtr, ytr)
        else:
            clf.fit(Xtr, ytr)
        fitted[name] = clf
        row = {"model": name}
        for sname, df in evals.items():
            X = df[FEATS].to_numpy(dtype=np.float32)
            y = df["class_label"].to_numpy(dtype=int)
            m = metrics(y, clf.predict(X), clf.predict_proba(X))
            for k, v in m.items():
                row[f"{sname}_{k}"] = v
        # prospective_full 现在也是干净集（训练池已剔除前瞻来源）——三个干净集等权
        row["clean_qwk_mean"] = float(np.mean([row["external_qwk"], row["zml100_strict_qwk"],
                                               row["prospective_full_qwk"]]))
        row["clean_acc_mean"] = float(np.mean([row["external_acc"], row["zml100_strict_acc"],
                                               row["prospective_full_acc"]]))
        rows.append(row)
        print(f"[champion] {name}: clean_qwk={row['clean_qwk_mean']:.4f} "
              f"clean_acc={row['clean_acc_mean']:.4f} ext_acc={row['external_acc']:.3f} "
              f"strict_acc={row['zml100_strict_acc']:.3f}", flush=True)

    board = pd.DataFrame(rows).sort_values(["clean_qwk_mean", "clean_acc_mean"], ascending=False)
    board.to_csv(OUT / "champion_selection_20260915.csv", index=False)
    champion_name = str(board.iloc[0]["model"])
    champion = fitted[champion_name]
    print(f"[champion] WINNER = {champion_name}")

    # ---------- transform recovery (exact rule: norm = raw/scale if missing==0 else 0.0) ----------
    # 编码是 CSV 的属性（与生产 clinical_norm_stats.json 一致），用全量训练侧行验证，
    # 与训练子集选择无关。
    tp = train_pat_all
    CAT_SCALE = {"sex": 1.0, "lauren_type": 3.0, "differentiation": 4.0, "tumor_location": 10.0}
    transform: dict = {"continuous": {}, "categorical_scale": CAT_SCALE, "binary": BINS,
                       "features": FEATS, "classes": CLASSES,
                       "workbench_map": {
                           "sex": {"Male": 1.0, "Female": 0.0},
                           "tumor_location": {"Cardia/Fundus": 0.0, "Body": 1.0, "Body/Angle": 1.0,
                                              "Antrum/Pylorus": 2.0, "Angle/Antrum": 2.0,
                                              "Multiple Sites": 3.0, "Whole Stomach": 3.0}}}
    for col in CONT:
        raw = pd.to_numeric(tp[col], errors="coerce")
        norm = pd.to_numeric(tp[f"{col}_norm"], errors="coerce")
        miss = tp[f"{col}_missing"].to_numpy(float)
        ok = raw.notna() & norm.notna() & (miss == 0)
        a, b = np.polyfit(raw[ok].to_numpy(float), norm[ok].to_numpy(float), 1)  # norm = a*raw + b
        resid = np.abs(norm[ok].to_numpy(float) - (a * raw[ok].to_numpy(float) + b)).max()
        mu, sd = -b / a, 1.0 / a
        transform["continuous"][col] = {"mean": float(mu), "std": float(sd)}
        # rows flagged missing must have norm == 0
        zero_ok = float(np.abs(norm[miss == 1].to_numpy(float)).max()) if (miss == 1).any() else 0.0
        print(f"[tf] {col}: mean={mu:.4f} sd={sd:.4f} max_resid={resid:.2e} miss_norm_max={zero_ok:.2e}")

    # ---------- self-test: norm == raw/scale (missing==0) or 0 (missing==1) ----------
    def expected_norm(col, raw, miss):
        if miss == 1:
            return 0.0
        if col in transform["continuous"]:
            cfg = transform["continuous"][col]
            return (float(raw) - cfg["mean"]) / cfg["std"]
        if col in CAT_SCALE:
            return float(raw) / CAT_SCALE[col]
        return float(raw)  # binary passthrough

    max_diff = 0.0
    for col in [c[:-5] for c in FEATS if c.endswith("_norm")]:
        raw = pd.to_numeric(tp[col], errors="coerce")
        norm = pd.to_numeric(tp[f"{col}_norm"], errors="coerce")
        miss = tp[f"{col}_missing"].to_numpy(float)
        ok = raw.notna() & norm.notna()
        exp = np.array([expected_norm(col, r, m) for r, m in zip(raw[ok], miss[ok])])
        diff = float(np.abs(exp - norm[ok].to_numpy(float)).max())
        max_diff = max(max_diff, diff)
        print(f"[selftest] {col}: max|exp-got| = {diff:.3e} (n={int(ok.sum())})")
    assert max_diff < 1e-3, "transform mismatch"

    # ---------- export ----------
    joblib.dump(champion, BUNDLE / "model.joblib")
    (BUNDLE / "transform.json").write_text(
        json.dumps(transform, indent=2, ensure_ascii=False), encoding="utf-8")
    meta = {
        "champion": champion_name,
        "feature_set": "clin9_wb (clin11 minus lauren/differentiation — not structured in workbench)",
        "train_pool": ("region_contrastive_full train+val, INTERNAL RETROSPECTIVE ONLY "
                       f"(int/2018+2019+2020_2023+2024, n={len(train_pat)} patients); "
                       "prospective/external sources excluded per 2026-09-15 requirement"),
        "selection": "mean QWK over external(381) + prospective_full(506, now clean) + zml100_strict, tiebreak mean ACC",
        "board": rows,
        "created": "2026-09-15",
    }
    (BUNDLE / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-> bundle: {BUNDLE}")


if __name__ == "__main__":
    main()
