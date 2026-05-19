"""
SimilarityTool — retrieve similar historical cases via FAISS index.

Searches a pre-built case memory (classification probabilities +
morphological features + clinical features) to find the top-k most
similar patients. Returns de-identified summaries with T-stage
distribution statistics for case-based reasoning.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from .base import BaseTool, ToolParameter
from ..core.repo_paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

DEFAULT_INDEX_DIR = PROJECT_ROOT / "pipeline" / "agent" / "memory" / "index"


class SimilarityTool(BaseTool):
    name = "retrieve_similar"
    description = (
        "Retrieve the most similar historical cases from the case memory. "
        "Returns de-identified summaries with T-stage distribution among "
        "similar cases. Most useful for borderline T2/T3 decisions."
    )
    parameters = [
        ToolParameter("query_vector", "list",
                       "Feature vector for the current case", required=True),
        ToolParameter("top_k", "int",
                       "Number of similar cases to retrieve", required=False),
    ]

    def __init__(self, index_dir: Path = DEFAULT_INDEX_DIR):
        self._index_dir = index_dir
        self._index = None
        self._metadata: List[Dict] = []
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return

        index_path = self._index_dir / "case_index.faiss"
        meta_path = self._index_dir / "case_metadata.json"

        if not index_path.exists() or not meta_path.exists():
            logger.warning("Case memory index not found at %s", self._index_dir)
            self._loaded = True
            return

        try:
            import faiss
            self._index = faiss.read_index(str(index_path))
            with open(meta_path) as f:
                self._metadata = json.load(f)
            logger.info("Loaded FAISS index with %d cases", self._index.ntotal)
        except ImportError:
            logger.warning("faiss-cpu not installed; SimilarityTool disabled")
        except Exception as e:
            logger.warning("Failed to load case memory: %s", e)
        self._loaded = True

    def execute(self, query_vector: Optional[List[float]] = None,
                top_k: int = 5, **kwargs) -> Dict[str, Any]:
        self._ensure_loaded()

        if self._index is None:
            return {
                "available": False,
                "reason": "Case memory index not built yet",
                "similar_cases": [],
                "stage_distribution": {},
                "runtime_invocation": {
                    "api_kind": "faiss_vector_search",
                    "called": False,
                    "index_path": str(self._index_dir / "case_index.faiss"),
                },
            }

        if query_vector is None:
            return {"error": "query_vector is required", "similar_cases": []}

        vec = np.array(query_vector, dtype=np.float32).reshape(1, -1)
        expected_dim = self._index.d
        if vec.shape[1] != expected_dim:
            # Pad or truncate to match index dimension
            if vec.shape[1] < expected_dim:
                pad = np.zeros((1, expected_dim - vec.shape[1]), dtype=np.float32)
                vec = np.concatenate([vec, pad], axis=1)
            else:
                vec = vec[:, :expected_dim]

        k = min(top_k, self._index.ntotal)
        distances, indices = self._index.search(vec, k)

        similar_cases = []
        stage_counts: Dict[str, int] = {}
        for i, idx in enumerate(indices[0]):
            if idx < 0 or idx >= len(self._metadata):
                continue
            meta = self._metadata[idx]
            data_source = str(meta.get("data_source", "unknown"))
            cohort_year = ""
            for token in data_source.replace("/", " ").replace("-", " ").split():
                if len(token) == 4 and token.isdigit() and token.startswith("20"):
                    cohort_year = token
                    break
            case_summary = {
                "rank": i + 1,
                "patient_id": str(meta.get("patient_id", "")).strip(),
                "similarity": round(1.0 / (1.0 + float(distances[0][i])), 4),
                "T_stage": meta.get("T_stage", "unknown"),
                "data_source": data_source,
                "cohort_year": cohort_year,
                "key_features": meta.get("key_features", {}),
            }
            similar_cases.append(case_summary)
            stage = meta.get("T_stage", "unknown")
            stage_counts[stage] = stage_counts.get(stage, 0) + 1

        return {
            "available": True,
            "similar_cases": similar_cases,
            "stage_distribution": stage_counts,
            "total_in_memory": self._index.ntotal,
            "runtime_invocation": {
                "api_kind": "faiss_vector_search",
                "called": True,
                "index_path": str(self._index_dir / "case_index.faiss"),
                "metadata_path": str(self._index_dir / "case_metadata.json"),
                "query_dim": int(vec.shape[1]),
                "top_k": k,
                "hits": len(similar_cases),
            },
        }
