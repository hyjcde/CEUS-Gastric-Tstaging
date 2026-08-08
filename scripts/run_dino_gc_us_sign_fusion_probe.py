#!/usr/bin/env python3
"""Patient-level DINOv3 + structured GC-US sign fusion probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, roc_auc_score
from sklearn.preprocessing import StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SIGN_CSV = (
    PROJECT_ROOT
    / "pipeline/data/gc_us_tscore_features_v1/feature_pack_v1/patient_features.csv"
)
DEFAULT_DINO_ROOT = PROJECT_ROOT / "pipeline/data/dinov3_tstaging_region_features"
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "pipeline/experiments/reports/dino_gc_us_sign_fusion_probe_20260801"
)

SPLIT_DIRS = {
    "train": "train_vitb16_last",
    "val": "val_vitb16_last",
    "test_external": "external_vitb16_last",
    "test_prospective": "internal_prospective_full_vitb16_last",
}
SIGN_PREFIXES = (
    "morph_",
    "margin_",
    "wall_",
    "bt_",
    "growth_",
    "seg_",
    "dyn_",
)
CLASS_NAMES = ["T1", "T2", "T3", "T4+"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sign-csv", type=Path, default=DEFAULT_SIGN_CSV)
    parser.add_argument("--dino-root", type=Path, default=DEFAULT_DINO_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--pca-components", type=int, default=96)
    parser.add_argument("--seed", type=int, default=20260801)
    return parser.parse_args()


def read_dino_patient_features(
    feature_dir: Path,
) -> tuple[pd.DataFrame, np.ndarray]:
    manifest = pd.read_csv(
        feature_dir / "frame_feature_manifest.csv",
        dtype={"patient_id": str},
        low_memory=False,
    )
    payload = np.load(feature_dir / "frame_dinov3_region_features.npz", allow_pickle=True)
    features = payload["features"].astype(np.float32)
    if len(manifest) != features.shape[0]:
        raise ValueError(f"manifest/features mismatch: {len(manifest)} vs {features.shape[0]}")
    rows: list[dict[str, str]] = []
    vectors: list[np.ndarray] = []
    for patient_id, group in manifest.groupby("patient_id", sort=True):
        indices = group.index.to_numpy()
        patient_x = features[indices]
        vectors.append(
            np.concatenate(
                [patient_x.mean(axis=0), patient_x.max(axis=0), patient_x.std(axis=0)],
                axis=0,
            ).astype(np.float32)
        )
        rows.append({"patient_id": str(patient_id)})
    return pd.DataFrame(rows), np.vstack(vectors)


def boundary_auc(y_true: np.ndarray, probs: np.ndarray, low: int, high: int) -> float:
    mask = np.isin(y_true, [low, high])
    if mask.sum() < 4 or len(np.unique(y_true[mask])) < 2:
        return float("nan")
    denominator = probs[mask, low] + probs[mask, high]
    score = probs[mask, high] / np.maximum(denominator, 1e-8)
    return float(roc_auc_score((y_true[mask] == high).astype(int), score))


def metrics(y_true: np.ndarray, probs: np.ndarray) -> dict[str, float]:
    pred = probs.argmax(axis=1)
    result = {
        "auc_macro_ovr": float(
            roc_auc_score(y_true, probs, multi_class="ovr", average="macro")
        ),
        "accuracy": float(accuracy_score(y_true, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, pred)),
    }
    result.update(
        {
            "t1_t2_auc": boundary_auc(y_true, probs, 0, 1),
            "t2_t3_auc": boundary_auc(y_true, probs, 1, 2),
            "t3_t4_auc": boundary_auc(y_true, probs, 2, 3),
        }
    )
    return result


def make_model(name: str, seed: int) -> object:
    if name == "logreg":
        return LogisticRegression(
            C=0.5,
            class_weight="balanced",
            max_iter=3000,
            random_state=seed,
        )
    return RandomForestClassifier(
        n_estimators=500,
        max_depth=8,
        min_samples_leaf=5,
        class_weight="balanced_subsample",
        n_jobs=-1,
        random_state=seed,
    )


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    signs = pd.read_csv(args.sign_csv, dtype={"patient_id": str}, low_memory=False)
    signs["patient_id"] = signs["patient_id"].astype(str)
    signs["label"] = pd.to_numeric(signs["label"], errors="coerce")
    signs = signs[signs["label"].notna()].copy()
    sign_cols = [
        col
        for col in signs.columns
        if col.startswith(SIGN_PREFIXES)
        and pd.api.types.is_numeric_dtype(signs[col])
    ]
    if not sign_cols:
        raise RuntimeError("No numeric structured sign columns were found")
    signs = signs[["patient_id", "label", "eval_split", *sign_cols]].drop_duplicates(
        "patient_id"
    )
    signs["eval_split"] = signs["eval_split"].replace(
        {"test_external": "test_external", "test_prospective": "test_prospective"}
    )

    split_frames: dict[str, pd.DataFrame] = {}
    dino_vectors: dict[str, np.ndarray] = {}
    for split, dirname in SPLIT_DIRS.items():
        frame, vectors = read_dino_patient_features(args.dino_root / dirname)
        frame["split"] = split
        split_frames[split] = frame
        dino_vectors[split] = vectors

    joined: dict[str, pd.DataFrame] = {}
    dino_joined: dict[str, np.ndarray] = {}
    overlap_rows = []
    for split, frame in split_frames.items():
        expected_eval = split
        if split == "test_prospective":
            expected_eval = "test_prospective"
        frame = frame.merge(
            signs[signs["eval_split"] == expected_eval],
            on="patient_id",
            how="inner",
            validate="one_to_one",
        )
        original = split_frames[split]
        index = original["patient_id"].isin(frame["patient_id"]).to_numpy()
        joined[split] = frame.reset_index(drop=True)
        dino_joined[split] = dino_vectors[split][index]
        overlap_rows.append(
            {
                "split": split,
                "dino_patients": len(original),
                "sign_patients": int((signs["eval_split"] == expected_eval).sum()),
                "joined_patients": len(frame),
            }
        )

    train_ids = set(joined["train"]["patient_id"])
    for split in ("val", "test_external", "test_prospective"):
        overlap_rows.append(
            {
                "split": f"train_vs_{split}",
                "dino_patients": len(train_ids),
                "sign_patients": len(joined[split]),
                "joined_patients": len(train_ids & set(joined[split]["patient_id"])),
            }
        )
    pd.DataFrame(overlap_rows).to_csv(args.output_dir / "join_audit.csv", index=False)

    train_signs = joined["train"][sign_cols].to_numpy(dtype=np.float32)
    sign_imputer = SimpleImputer(strategy="median")
    sign_scaler = StandardScaler()
    train_signs_scaled = sign_scaler.fit_transform(sign_imputer.fit_transform(train_signs))
    sign_features = {
        split: sign_scaler.transform(
            sign_imputer.transform(joined[split][sign_cols].to_numpy(dtype=np.float32))
        )
        for split in joined
    }

    train_dino = dino_joined["train"]
    dino_imputer = SimpleImputer(strategy="median")
    dino_scaler = StandardScaler()
    train_dino_scaled = dino_scaler.fit_transform(dino_imputer.fit_transform(train_dino))
    n_components = min(args.pca_components, train_dino_scaled.shape[0] - 1, train_dino_scaled.shape[1])
    dino_pca = PCA(n_components=n_components, random_state=args.seed)
    train_dino_pca = dino_pca.fit_transform(train_dino_scaled)
    dino_features = {
        split: dino_pca.transform(
            dino_scaler.transform(dino_imputer.transform(dino_joined[split]))
        )
        for split in joined
    }

    feature_sets = {
        "signs_only": {split: sign_features[split] for split in joined},
        "dino_only": {split: dino_features[split] for split in joined},
        "dino_plus_signs": {
            split: np.concatenate([dino_features[split], sign_features[split]], axis=1)
            for split in joined
        },
    }
    results = []
    y_train = joined["train"]["label"].to_numpy(dtype=int)
    for feature_set, arrays in feature_sets.items():
        for model_name in ("logreg", "random_forest"):
            model = make_model(model_name, args.seed)
            model.fit(arrays["train"], y_train)
            for split in ("val", "test_external", "test_prospective"):
                y_true = joined[split]["label"].to_numpy(dtype=int)
                probs = model.predict_proba(arrays[split])
                row = {
                    "feature_set": feature_set,
                    "model": model_name,
                    "split": split,
                    "n_patients": len(y_true),
                    "dino_components": n_components,
                    "sign_feature_count": len(sign_cols),
                    **metrics(y_true, probs),
                }
                results.append(row)
    result_df = pd.DataFrame(results)
    result_df.to_csv(args.output_dir / "fusion_results.csv", index=False)
    meta = {
        "sign_csv": str(args.sign_csv),
        "dino_root": str(args.dino_root),
        "sign_feature_count": len(sign_cols),
        "sign_features": sign_cols,
        "dino_components": n_components,
        "joined_patients": {split: len(frame) for split, frame in joined.items()},
        "class_counts": {
            split: joined[split]["label"].value_counts().sort_index().to_dict()
            for split in joined
        },
        "note": "Exploratory patient-level fusion using cached workstation DINOv3 features and structured GC-US sign features.",
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.output_dir / "README.md").write_text(
        "\n".join(
            [
                "# DINOv3 + GC-US sign fusion probe",
                "",
                "This is an exploratory patient-level fusion using cached DINOv3 region features and structured morphology/margin/wall/growth/dynamics signs.",
                "",
                "It is not a frozen paper result until patient split, clinical availability, and external/prospective cohort boundaries are independently audited.",
                "",
                "Outputs: `fusion_results.csv`, `join_audit.csv`, `summary.json`.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(result_df.to_string(index=False))


if __name__ == "__main__":
    main()
