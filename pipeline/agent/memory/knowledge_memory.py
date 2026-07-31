from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

from ..core.repo_paths import PROJECT_ROOT

_BUILTIN_NOTES = [
    {
        "source": "medical-agent-design",
        "title": "Sequential task chain",
        "content": "Break clinical reasoning into stable stages: data intake, tool execution, evidence aggregation, report synthesis, and manual review recommendation.",
    },
    {
        "source": "medical-agent-design",
        "title": "Memory-enhanced reasoning",
        "content": "Use long-term case memory for similar historical cases and short-term session memory for the current reader workflow. Do not mix the two layers.",
    },
    {
        "source": "medical-agent-design",
        "title": "External capacity enhancement",
        "content": "Treat segmentation, classification, morphology, clinical scoring, and retrieval as explicit tools so the medical agent does not rely on unsupported free-form inference.",
    },
]


def _tokenize(text: str) -> List[str]:
    return [token for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fff]+", text.lower()) if token]


def _iter_doc_files() -> Iterable[Path]:
    for rel_dir in ("docs/mainline", "docs/evaluation", "docs/data_governance", "docs/experiment_governance"):
        directory = PROJECT_ROOT / rel_dir
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*.md")):
            yield path


@dataclass
class KnowledgeMemory:
    snippets: List[Dict[str, str]]

    @classmethod
    def build(cls) -> "KnowledgeMemory":
        snippets = list(_BUILTIN_NOTES)
        for path in _iter_doc_files():
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            excerpt = " ".join(lines[:12])[:1200]
            if not excerpt:
                continue
            snippets.append({
                "source": str(path.relative_to(PROJECT_ROOT)),
                "title": path.stem,
                "content": excerpt,
            })
        return cls(snippets=snippets)

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, str]]:
        query_tokens = set(_tokenize(query))
        if not query_tokens:
            return self.snippets[:top_k]

        scored = []
        for snippet in self.snippets:
            haystack = f"{snippet['title']} {snippet['content']}"
            tokens = set(_tokenize(haystack))
            overlap = len(query_tokens & tokens)
            if overlap <= 0:
                continue
            scored.append((overlap, snippet))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [snippet for _, snippet in scored[:top_k]]

