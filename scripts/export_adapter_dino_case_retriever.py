#!/usr/bin/env python3
"""Export Adapter-DINO Case-RAG retriever artifacts for Agent runtime."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.neighbors import NeighborhoodComponentsAnalysis
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from train_adapter_dinov3_case_rag_from_cache import (  # noqa: E402
    load_all,
    patient_features,
)
from train_learned_dino_case_rag import normalize_rows  # noqa: E402

DEFAULT_FEATURE_DIR = PROJECT_ROOT / "pipeline" / "data" / "adapter_dinov3_case_rag_features" / "last2blocks_clean_mlp_512"
DEFAULT_OUTPUT = PROJECT_ROOT / "pipeline" / "agent" / "memory" / "retriever" / "adapter_dinov3_v1"
META_COLS = ["clinical_patient_uid", "patient_id", "class_label", "T_stage", "source", "split_name"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export adapter-DINO retriever for Agent memory.")
    p.add_argument("--feature-dir", type=Path, default=DEFAULT_FEATURE_DIR)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--pca-components", type=int, default=128)
    p.add_argument("--nca-components", type=int, default=32)
    p.add_argument("--top-k", type=int, default=9)
    p.add_argument("--temperature", type=float, default=0.2)
    p.add_argument("--seed", type=int, default=20260518)
    return p.parse_args()


def main() -> None:
    import joblib

    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    tables, vectors = load_all(args.feature_dir)
    train_table, train_x = tables["train"], vectors["train"]
    train_y = train_table["class_label"].astype(int).to_numpy()

    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()
    x_train = scaler.fit_transform(imputer.fit_transform(train_x)).astype(np.float32)

    pca_components = min(args.pca_components, x_train.shape[0] - 1, x_train.shape[1])
    pca = PCA(n_components=pca_components, random_state=args.seed)
    train_pca = pca.fit_transform(x_train).astype(np.float32)

    nca_components = min(args.nca_components, train_pca.shape[0] - 1, train_pca.shape[1])
    nca = NeighborhoodComponentsAnalysis(
        n_components=nca_components,
        init="pca",
        max_iter=100,
        random_state=args.seed,
    )
    learned_train = normalize_rows(nca.fit_transform(train_pca, train_y).astype(np.float32))

    joblib.dump(imputer, args.output_dir / "imputer.joblib")
    joblib.dump(scaler, args.output_dir / "scaler.joblib")
    joblib.dump(pca, args.output_dir / "pca.joblib")
    joblib.dump(nca, args.output_dir / "nca.joblib")

    np.savez_compressed(
        args.output_dir / "train_memory_learned.npz",
        embeddings=learned_train,
        labels=train_y,
    )

    meta = train_table[META_COLS].fillna("").astype(str).to_dict(orient="records")
    with open(args.output_dir / "train_memory_meta.json", "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    config = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "feature_dir": str(args.feature_dir),
        "train_patients": int(len(meta)),
        "feature_dim_raw": int(train_x.shape[1]),
        "pca_components": int(pca_components),
        "nca_components": int(nca_components),
        "top_k": int(args.top_k),
        "temperature": float(args.temperature),
        "method": "adapter_learned_nca",
        "fusion_alpha_recommended": 0.3,
    }
    with open(args.output_dir / "retriever_config.json", "w") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"Exported retriever to {args.output_dir} ({len(meta)} patients)")


if __name__ == "__main__":
    main()
