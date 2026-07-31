"""
Ablation experiment configurations.

Defines 7 experimental conditions for systematic ablation:
  1. Baseline-Single:  per-frame argmax, majority vote
  2. Baseline-Avg:     per-frame probs averaged, argmax
  3. Agent-QS:         + QualityTool + quality-weighted aggregation
  4. Agent-QSM:        + MorphologyTool
  5. Agent-QSM-C:      + ClinicalTool
  6. Agent-Full:       + SimilarityTool (RAG)
  7. Agent-Full-NoLLM: full tools but rule-based (no LLM scheduler)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AblationConfig:
    """Configuration for one ablation condition."""
    name: str
    description: str
    use_quality: bool = False
    use_segmentation: bool = True
    use_classification: bool = True
    use_morphology: bool = False
    use_clinical: bool = False
    use_rag: bool = False
    use_llm: bool = True
    max_steps: int = 8


ABLATION_CONFIGS = {
    "baseline_single": AblationConfig(
        name="Baseline-Single",
        description="Per-frame argmax → majority vote (no agent)",
        use_quality=False, use_segmentation=True,
        use_classification=True, use_morphology=False,
        use_clinical=False, use_rag=False, use_llm=False,
        max_steps=0,
    ),
    "baseline_avg": AblationConfig(
        name="Baseline-Avg",
        description="Multi-frame probability average → argmax (no agent)",
        use_quality=False, use_segmentation=True,
        use_classification=True, use_morphology=False,
        use_clinical=False, use_rag=False, use_llm=False,
        max_steps=0,
    ),
    "agent_qs": AblationConfig(
        name="Agent-QS",
        description="Agent with quality check + quality-weighted classification",
        use_quality=True, use_segmentation=True,
        use_classification=True, use_morphology=False,
        use_clinical=False, use_rag=False, use_llm=True,
    ),
    "agent_qsm": AblationConfig(
        name="Agent-QSM",
        description="Agent-QS + morphology features",
        use_quality=True, use_segmentation=True,
        use_classification=True, use_morphology=True,
        use_clinical=False, use_rag=False, use_llm=True,
    ),
    "agent_qsm_c": AblationConfig(
        name="Agent-QSM-C",
        description="Agent-QSM + clinical features",
        use_quality=True, use_segmentation=True,
        use_classification=True, use_morphology=True,
        use_clinical=True, use_rag=False, use_llm=True,
    ),
    "agent_full": AblationConfig(
        name="Agent-Full",
        description="Full agent with all tools including RAG",
        use_quality=True, use_segmentation=True,
        use_classification=True, use_morphology=True,
        use_clinical=True, use_rag=True, use_llm=True,
    ),
    "agent_full_nollm": AblationConfig(
        name="Agent-Full-NoLLM",
        description="All tools but rule-based scheduling (no LLM)",
        use_quality=True, use_segmentation=True,
        use_classification=True, use_morphology=True,
        use_clinical=True, use_rag=True, use_llm=False,
    ),
}


def get_ablation_config(name: str) -> AblationConfig:
    if name not in ABLATION_CONFIGS:
        raise ValueError(f"Unknown ablation: {name}. "
                          f"Available: {list(ABLATION_CONFIGS.keys())}")
    return ABLATION_CONFIGS[name]


def list_ablation_configs() -> List[str]:
    return list(ABLATION_CONFIGS.keys())
