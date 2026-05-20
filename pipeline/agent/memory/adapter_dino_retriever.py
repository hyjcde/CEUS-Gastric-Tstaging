"""
Adapter-DINO Case-RAG retriever for Agent runtime.

Loads exported train-memory embeddings (NCA space) + sklearn transforms.
Query requires frame-level adapter features (cached npz) or online encoding (future).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ..core.repo_paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

DEFAULT_RETRIEVER_DIR = (
    PROJECT_ROOT / "pipeline" / "agent" / "memory" / "retriever" / "adapter_dinov3_v1"
)
LABEL_NAMES = ["T1", "T2", "T3", "T4+"]


def _normalize_rows(x: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-8)
    return (x / norms).astype(np.float32)


def _softmax_vote(
    query_x: np.ndarray,
    memory_x: np.ndarray,
    memory_y: np.ndarray,
    top_k: int,
    temperature: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    sims = query_x @ memory_x.T
    k = min(top_k, sims.shape[1])
    order = np.argsort(-sims, axis=1)[:, :k]
    picked = np.take_along_axis(sims, order, axis=1)
    weights = np.exp(picked / max(temperature, 1e-4))
    weights = weights / np.maximum(weights.sum(axis=1, keepdims=True), 1e-8)
    probs = np.zeros((query_x.shape[0], 4), dtype=np.float32)
    for i in range(query_x.shape[0]):
        for j, mem_idx in enumerate(order[i]):
            probs[i, int(memory_y[mem_idx])] += weights[i, j]
    return probs, order, picked


class AdapterDINORetriever:
    def __init__(self, retriever_dir: Path = DEFAULT_RETRIEVER_DIR):
        self.retriever_dir = Path(retriever_dir)
        self._loaded = False
        self._config: Dict[str, Any] = {}
        self._memory_x: Optional[np.ndarray] = None
        self._memory_y: Optional[np.ndarray] = None
        self._memory_meta: List[Dict[str, Any]] = []
        self._imputer = None
        self._scaler = None
        self._pca = None
        self._nca = None

    def _ensure_loaded(self) -> bool:
        if self._loaded:
            return self._memory_x is not None
        self._loaded = True
        config_path = self.retriever_dir / "retriever_config.json"
        mem_path = self.retriever_dir / "train_memory_learned.npz"
        meta_path = self.retriever_dir / "train_memory_meta.json"
        if not (config_path.exists() and mem_path.exists() and meta_path.exists()):
            logger.info("Adapter-DINO retriever artifacts missing at %s", self.retriever_dir)
            return False
        try:
            import joblib

            with open(config_path) as f:
                self._config = json.load(f)
            payload = np.load(mem_path, allow_pickle=False)
            self._memory_x = payload["embeddings"].astype(np.float32)
            self._memory_y = payload["labels"].astype(np.int32)
            with open(meta_path) as f:
                self._memory_meta = json.load(f)
            self._imputer = joblib.load(self.retriever_dir / "imputer.joblib")
            self._scaler = joblib.load(self.retriever_dir / "scaler.joblib")
            self._pca = joblib.load(self.retriever_dir / "pca.joblib")
            self._nca = joblib.load(self.retriever_dir / "nca.joblib")
            logger.info("Loaded Adapter-DINO retriever: %d train patients", len(self._memory_meta))
            return True
        except Exception as exc:
            logger.warning("Failed to load Adapter-DINO retriever: %s", exc)
            self._memory_x = None
            return False

    @property
    def available(self) -> bool:
        return self._ensure_loaded()

    def embed_patient_vector(self, patient_feature: np.ndarray) -> np.ndarray:
        """Project raw 39936-d patient mean vector → learned NCA space (normalized)."""
        assert self._imputer is not None
        x = patient_feature.reshape(1, -1).astype(np.float32)
        x = self._scaler.transform(self._imputer.transform(x)).astype(np.float32)
        x = self._nca.transform(self._pca.transform(x)).astype(np.float32)
        return _normalize_rows(x)[0]

    def lookup_by_raw_patient_feature(
        self,
        patient_feature: np.ndarray,
        top_k: Optional[int] = None,
        exclude_patient_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.available:
            return {"available": False, "reason": "retriever_not_built"}
        q = self.embed_patient_vector(patient_feature).reshape(1, -1)
        return self._search_learned(
            q,
            int(top_k or self._config.get("top_k", 9)),
            float(self._config.get("temperature", 0.2)),
            exclude_patient_id=exclude_patient_id,
        )

    def _search_learned(
        self,
        query_x: np.ndarray,
        top_k: int,
        temperature: float,
        exclude_patient_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        assert self._memory_x is not None and self._memory_y is not None
        probs, order, scores = _softmax_vote(
            query_x, self._memory_x, self._memory_y, top_k=top_k, temperature=temperature
        )
        similar_cases = []
        stage_counts: Dict[str, int] = {}
        for rank, mem_idx in enumerate(order[0]):
            meta = self._memory_meta[int(mem_idx)]
            pid = str(meta.get("patient_id", "")).strip()
            if exclude_patient_id and pid == str(exclude_patient_id).strip():
                continue
            stage = str(meta.get("T_stage", "unknown"))
            similar_cases.append({
                "rank": len(similar_cases) + 1,
                "patient_id": pid,
                "clinical_patient_uid": str(meta.get("clinical_patient_uid", "")),
                "similarity": round(float(scores[0, rank]), 4),
                "T_stage": stage,
                "retriever": "adapter_dino_nca",
                "key_features": {"rag_prob_vector": probs[0].tolist()},
            })
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
            if len(similar_cases) >= top_k:
                break

        return {
            "available": True,
            "retriever": "adapter_dino_learned_nca",
            "similar_cases": similar_cases,
            "stage_distribution": stage_counts,
            "rag_probabilities": {
                name: round(float(probs[0, i]), 4) for i, name in enumerate(LABEL_NAMES)
            },
            "runtime_invocation": {
                "api_kind": "adapter_dino_nca_vote",
                "called": True,
                "top_k": top_k,
                "temperature": temperature,
            },
        }
