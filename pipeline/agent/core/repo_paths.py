from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Iterable

PROJECT_ROOT_ENV_KEYS = (
    "GASTRIC_ROOT",
    "GASTRIC_TSTAGING_ROOT",
    "GASTRIC_PROJECT_ROOT",
)


def _is_repo_root(path: Path) -> bool:
    return (
        path.exists()
        and (path / "dataset").exists()
        and (path / "pipeline").exists()
    )


def _iter_search_roots(start: Path) -> Iterable[Path]:
    current = start.resolve()
    while True:
        yield current
        if current.parent == current:
            break
        current = current.parent


@lru_cache(maxsize=1)
def get_project_root() -> Path:
    for env_key in PROJECT_ROOT_ENV_KEYS:
        env_value = os.getenv(env_key)
        if env_value:
            candidate = Path(env_value).expanduser().resolve()
            if _is_repo_root(candidate):
                return candidate

    seed_paths = [
        Path.cwd(),
        Path(__file__).resolve(),
        Path(__file__).resolve().parents[4],
    ]
    for seed in seed_paths:
        for candidate in _iter_search_roots(seed):
            if _is_repo_root(candidate):
                return candidate

    return Path(__file__).resolve().parents[4]


PROJECT_ROOT = get_project_root()
DATASET_DIR = PROJECT_ROOT / "dataset"
PIPELINE_DIR = PROJECT_ROOT / "pipeline"
APPS_DIR = PROJECT_ROOT / "apps"
TMP_DIR = PROJECT_ROOT / "tmp"


def resolve_repo_path(*parts: str) -> Path:
    return PROJECT_ROOT.joinpath(*parts)


def first_existing_path(*paths: Path) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def get_predicted_masks_dir() -> Path:
    return first_existing_path(
        PIPELINE_DIR / "data" / "predicted_masks",
        PROJECT_ROOT / "data" / "predicted_masks",
    ) or (PIPELINE_DIR / "data" / "predicted_masks")

