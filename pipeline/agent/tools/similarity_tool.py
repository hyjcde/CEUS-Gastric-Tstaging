"""
SimilarityTool — retrieve similar historical cases for Case-RAG.

Backends (priority):
  1. Block-weighted extended vector (28-d: cls + morph + clinical + wall + boundary)
  2. Legacy FAISS L2 index (17-d) when extended memory not built
  3. Adapter-DINO NCA retriever when query has cached adapter features

Medical principle: similarity = weighted match on **invasion pattern** (wall/boundary),
not raw pixel cosine on whole image.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from .base import BaseTool, ToolParameter
from ..core.repo_paths import PROJECT_ROOT
from ..memory.adapter_dino_retriever import AdapterDINORetriever
from ..memory.case_similarity import l2_to_similarity, rank_memory_vectors
from ..memory.multimodal_case_vector import VECTOR_DIM, extract_multimodal_case_vector

logger = logging.getLogger(__name__)

DEFAULT_INDEX_DIR = PROJECT_ROOT / "pipeline" / "agent" / "memory" / "index"


class SimilarityTool(BaseTool):
    name = "retrieve_similar"
    description = (
        "Retrieve similar historical cases from case memory using medically weighted "
        "multimodal vectors (wall/boundary-heavy). Returns T-stage distribution for Case-RAG."
    )
    parameters = [
        ToolParameter("query_vector", "list", "Legacy 17-d or extended 28-d vector", required=False),
        ToolParameter("case_context", "object", "Tool outputs: classification, morphology, clinical, wall", required=False),
        ToolParameter("top_k", "int", "Number of similar cases", required=False),
        ToolParameter("patient_id", "string", "Exclude self from hits", required=False),
        ToolParameter("adapter_patient_feature", "list", "Raw 39936-d adapter mean vector if cached", required=False),
    ]

    def __init__(self, index_dir: Path = DEFAULT_INDEX_DIR):
        self._index_dir = Path(index_dir)
        self._index = None
        self._metadata: List[Dict] = []
        self._memory_matrix: Optional[np.ndarray] = None
        self._loaded = False
        self._dino = AdapterDINORetriever()

    def _ensure_loaded(self):
        if self._loaded:
            return

        ext_matrix_path = self._index_dir / "case_matrix_extended.npy"
        ext_meta_path = self._index_dir / "case_metadata_extended.json"
        if ext_matrix_path.exists() and ext_meta_path.exists():
            self._memory_matrix = np.load(ext_matrix_path).astype(np.float32)
            with open(ext_meta_path) as f:
                self._metadata = json.load(f)
            logger.info("Loaded extended case matrix: %d × %d", *self._memory_matrix.shape)

        index_path = self._index_dir / "case_index.faiss"
        meta_path = self._index_dir / "case_metadata.json"
        if index_path.exists() and meta_path.exists() and not self._metadata:
            try:
                import faiss
                self._index = faiss.read_index(str(index_path))
                with open(meta_path) as f:
                    self._metadata = json.load(f)
                logger.info("Loaded FAISS index with %d cases", self._index.ntotal)
            except ImportError:
                logger.warning("faiss-cpu not installed; SimilarityTool disabled")
            except Exception as exc:
                logger.warning("Failed to load case memory: %s", exc)

        self._loaded = True

    def _resolve_query_vector(
        self,
        query_vector: Optional[List[float]],
        case_context: Optional[Dict[str, Any]],
    ) -> tuple[np.ndarray, Dict[str, Any]]:
        meta: Dict[str, Any] = {"source": "query_vector"}
        if case_context:
            bundle = extract_multimodal_case_vector(
                cls_results=case_context.get("cls_results") or [],
                morph_results=case_context.get("morph_results") or [],
                clinical_info=case_context.get("clinical_info"),
                wall_evidence=case_context.get("wall_evidence"),
            )
            meta = {"source": "case_context", **bundle.metadata}
            return bundle.extended, meta

        if query_vector is None:
            return np.zeros(VECTOR_DIM, dtype=np.float32), meta

        vec = np.array(query_vector, dtype=np.float32).reshape(-1)
        if len(vec) < VECTOR_DIM:
            out = np.zeros(VECTOR_DIM, dtype=np.float32)
            out[: len(vec)] = vec
            return out, meta
        return vec[:VECTOR_DIM], meta

    def _search_extended(
        self,
        query: np.ndarray,
        top_k: int,
        patient_id: Optional[str],
        boundary_boost: bool,
    ) -> List[Dict[str, Any]]:
        assert self._memory_matrix is not None
        hits = rank_memory_vectors(
            query,
            self._memory_matrix,
            top_k=top_k + 5,
            boundary_boost=boundary_boost,
        )
        similar: List[Dict[str, Any]] = []
        for idx, sim, block_scores in hits:
            if idx >= len(self._metadata):
                continue
            meta = self._metadata[idx]
            pid = str(meta.get("patient_id", "")).strip()
            if patient_id and pid == str(patient_id).strip():
                continue
            similar.append({
                "rank": len(similar) + 1,
                "patient_id": pid,
                "similarity": sim,
                "T_stage": meta.get("T_stage", "unknown"),
                "data_source": meta.get("data_source", "unknown"),
                "key_features": meta.get("key_features", {}),
                "block_similarity": block_scores,
                "retriever": "block_weighted_extended",
            })
            if len(similar) >= top_k:
                break
        return similar

    def _search_faiss(self, query: np.ndarray, top_k: int, patient_id: Optional[str]) -> List[Dict[str, Any]]:
        assert self._index is not None
        vec = query[:17].reshape(1, -1).astype(np.float32)
        expected_dim = self._index.d
        if vec.shape[1] != expected_dim:
            if vec.shape[1] < expected_dim:
                pad = np.zeros((1, expected_dim - vec.shape[1]), dtype=np.float32)
                vec = np.concatenate([vec, pad], axis=1)
            else:
                vec = vec[:, :expected_dim]

        k = min(top_k + 3, self._index.ntotal)
        distances, indices = self._index.search(vec, k)
        similar: List[Dict[str, Any]] = []
        for i, idx in enumerate(indices[0]):
            if idx < 0 or idx >= len(self._metadata):
                continue
            meta = self._metadata[idx]
            pid = str(meta.get("patient_id", "")).strip()
            if patient_id and pid == str(patient_id).strip():
                continue
            similar.append({
                "rank": len(similar) + 1,
                "patient_id": pid,
                "similarity": l2_to_similarity(float(distances[0][i])),
                "T_stage": meta.get("T_stage", "unknown"),
                "data_source": meta.get("data_source", "unknown"),
                "key_features": meta.get("key_features", {}),
                "retriever": "faiss_l2_legacy",
            })
            if len(similar) >= top_k:
                break
        return similar

    def execute(
        self,
        query_vector: Optional[List[float]] = None,
        case_context: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
        patient_id: Optional[str] = None,
        adapter_patient_feature: Optional[List[float]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        self._ensure_loaded()
        top_k = int(kwargs.get("top_k", top_k))

        # Adapter-DINO path (invasion-pattern embedding)
        if adapter_patient_feature and self._dino.available:
            dino_payload = self._dino.lookup_by_raw_patient_feature(
                np.array(adapter_patient_feature, dtype=np.float32),
                top_k=top_k,
                exclude_patient_id=patient_id,
            )
            if dino_payload.get("available"):
                stage_counts: Dict[str, int] = {}
                for case in dino_payload.get("similar_cases", []):
                    st = case.get("T_stage", "unknown")
                    stage_counts[st] = stage_counts.get(st, 0) + 1
                dino_payload["stage_distribution"] = stage_counts
                dino_payload["total_in_memory"] = len(self._dino._memory_meta) if self._dino._memory_meta else 0
                return dino_payload

        query, query_meta = self._resolve_query_vector(query_vector, case_context)
        boundary_boost = float(query[1] + query[2]) >= 0.45 or query_meta.get("penetration_risk") in {"medium", "high"}

        similar_cases: List[Dict[str, Any]] = []
        backend = "none"
        if self._memory_matrix is not None:
            similar_cases = self._search_extended(query, top_k, patient_id, boundary_boost)
            backend = "block_weighted_extended"
        elif self._index is not None:
            similar_cases = self._search_faiss(query, top_k, patient_id)
            backend = "faiss_l2_legacy"

        if not similar_cases:
            return {
                "available": False,
                "reason": "Case memory index not built yet",
                "similar_cases": [],
                "stage_distribution": {},
                "runtime_invocation": {
                    "api_kind": "case_similarity",
                    "called": False,
                    "index_path": str(self._index_dir),
                },
            }

        stage_counts: Dict[str, int] = {}
        for case in similar_cases:
            st = case.get("T_stage", "unknown")
            stage_counts[st] = stage_counts.get(st, 0) + 1

        return {
            "available": True,
            "similar_cases": similar_cases,
            "stage_distribution": stage_counts,
            "total_in_memory": (
                int(self._memory_matrix.shape[0])
                if self._memory_matrix is not None
                else (self._index.ntotal if self._index else 0)
            ),
            "query_meta": query_meta,
            "boundary_boost": boundary_boost,
            "runtime_invocation": {
                "api_kind": "case_similarity",
                "called": True,
                "backend": backend,
                "index_path": str(self._index_dir),
                "query_dim": int(query.shape[0]),
                "top_k": top_k,
                "hits": len(similar_cases),
            },
        }
