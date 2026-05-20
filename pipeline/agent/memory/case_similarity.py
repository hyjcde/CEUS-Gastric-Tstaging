"""
Medical block-weighted case similarity for Agent memory retrieval.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

from .multimodal_case_vector import BLOCK_SLICES, DEFAULT_BLOCK_WEIGHTS, VECTOR_DIM


def _normalize_block(block: np.ndarray) -> np.ndarray:
    block = np.asarray(block, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(block))
    if norm < 1e-8:
        return block
    return block / norm


def block_cosine(a: np.ndarray, b: np.ndarray, start: int, end: int) -> float:
    """Cosine similarity on vector slice [start:end)."""
    sa = _normalize_block(a[start:end])
    sb = _normalize_block(b[start:end])
    denom = float(np.linalg.norm(sa) * np.linalg.norm(sb))
    if denom < 1e-8:
        return 0.0
    return float(np.dot(sa, sb))


def weighted_block_similarity(
    query: np.ndarray,
    memory: np.ndarray,
    weights: Optional[Dict[str, float]] = None,
    boundary_boost: bool = False,
) -> Tuple[float, Dict[str, float]]:
    """
    Compute medically weighted similarity in [0, 1].

    boundary_boost: up-weight wall/boundary blocks when query shows T2/T3 ambiguity.
    """
    weights = dict(weights or DEFAULT_BLOCK_WEIGHTS)
    q = np.asarray(query, dtype=np.float32).reshape(-1)
    m = np.asarray(memory, dtype=np.float32).reshape(-1)

    dim = max(len(q), len(m), VECTOR_DIM)
    if len(q) < dim:
        q = np.pad(q, (0, dim - len(q)))
    if len(m) < dim:
        m = np.pad(m, (0, dim - len(m)))

    if boundary_boost and dim >= 28:
        t2t3 = float(q[1] + q[2])
        if t2t3 >= 0.45:
            weights = dict(weights)
            weights["wall"] = min(0.55, weights.get("wall", 0.4) + 0.10)
            weights["boundary"] = min(0.35, weights.get("boundary", 0.25) + 0.08)
            total = sum(weights.values())
            weights = {k: v / total for k, v in weights.items()}

    per_block: Dict[str, float] = {}
    score = 0.0
    for name, (start, end) in BLOCK_SLICES.items():
        if end > dim:
            continue
        sim = block_cosine(q, m, start, end)
        per_block[name] = round(sim, 4)
        score += weights.get(name, 0.0) * sim

    return round(float(np.clip(score, 0.0, 1.0)), 4), per_block


def l2_to_similarity(distance: float) -> float:
    return round(1.0 / (1.0 + max(float(distance), 0.0)), 4)


def rank_memory_vectors(
    query: np.ndarray,
    memory_matrix: np.ndarray,
    top_k: int = 5,
    weights: Optional[Dict[str, float]] = None,
    boundary_boost: bool = False,
) -> List[Tuple[int, float, Dict[str, float]]]:
    """Return [(index, similarity, block_scores), ...] sorted desc."""
    hits: List[Tuple[int, float, Dict[str, float]]] = []
    for idx in range(memory_matrix.shape[0]):
        sim, blocks = weighted_block_similarity(
            query, memory_matrix[idx], weights=weights, boundary_boost=boundary_boost
        )
        hits.append((idx, sim, blocks))
    hits.sort(key=lambda x: -x[1])
    return hits[:top_k]
