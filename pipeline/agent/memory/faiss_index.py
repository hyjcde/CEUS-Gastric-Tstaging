"""
FAISS index wrapper for case memory.

Provides build / save / load / search operations for the case vector store.
Uses IndexFlatL2 since the dataset is small (~1500 patients).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class CaseIndex:
    """Thin wrapper around a FAISS IndexFlatL2."""

    def __init__(self, dim: int = 17):
        self.dim = dim
        self._index = None
        self._metadata: List[Dict[str, Any]] = []

    @property
    def ntotal(self) -> int:
        if self._index is None:
            return 0
        return self._index.ntotal

    def build(self, vectors: np.ndarray,
              metadata: List[Dict[str, Any]]) -> None:
        """Build index from a matrix and metadata list."""
        import faiss

        assert vectors.ndim == 2 and vectors.shape[1] == self.dim, (
            f"Expected (N, {self.dim}), got {vectors.shape}")
        assert len(metadata) == vectors.shape[0], (
            f"Metadata length {len(metadata)} != vectors {vectors.shape[0]}")

        self._index = faiss.IndexFlatL2(self.dim)
        self._index.add(vectors.astype(np.float32))
        self._metadata = list(metadata)
        logger.info("Built FAISS index: %d vectors, dim=%d",
                     self.ntotal, self.dim)

    def save(self, index_dir: Path) -> None:
        """Save index and metadata to disk."""
        import faiss

        index_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(index_dir / "case_index.faiss"))
        with open(index_dir / "case_metadata.json", "w") as f:
            json.dump(self._metadata, f, indent=2, default=str)
        logger.info("Saved index to %s (%d entries)", index_dir, self.ntotal)

    def load(self, index_dir: Path) -> None:
        """Load index and metadata from disk."""
        import faiss

        self._index = faiss.read_index(str(index_dir / "case_index.faiss"))
        with open(index_dir / "case_metadata.json") as f:
            self._metadata = json.load(f)
        self.dim = self._index.d
        logger.info("Loaded index from %s (%d entries, dim=%d)",
                     index_dir, self.ntotal, self.dim)

    def search(self, query: np.ndarray,
               top_k: int = 5) -> Tuple[np.ndarray, np.ndarray, List[Dict]]:
        """
        Search for nearest neighbours.

        Returns (distances, indices, metadata_list).
        """
        if self._index is None or self.ntotal == 0:
            return np.array([]), np.array([]), []

        q = query.astype(np.float32).reshape(1, -1)
        if q.shape[1] != self.dim:
            # Pad or truncate
            if q.shape[1] < self.dim:
                q = np.concatenate(
                    [q, np.zeros((1, self.dim - q.shape[1]), dtype=np.float32)],
                    axis=1)
            else:
                q = q[:, :self.dim]

        k = min(top_k, self.ntotal)
        distances, indices = self._index.search(q, k)

        metas = []
        for idx in indices[0]:
            if 0 <= idx < len(self._metadata):
                metas.append(self._metadata[idx])
            else:
                metas.append({})

        return distances[0], indices[0], metas
