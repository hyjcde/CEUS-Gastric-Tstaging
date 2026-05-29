#!/usr/bin/env python3
from __future__ import annotations

import importlib
import io
import json
import numbers
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a mapping in {path}")
    return payload


def resolve_project_path(value: str | None, *, required: bool = True) -> Path | None:
    if value in (None, ""):
        if required:
            raise ValueError("Missing required path value in config")
        return None
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def resolve_project_path_or_literal(value: str | None, *, required: bool = True) -> Path | str | None:
    if value in (None, ""):
        if required:
            raise ValueError("Missing required path value in config")
        return None

    raw = str(value)
    candidate = Path(raw)
    candidates = [candidate]
    if not candidate.is_absolute():
        candidates.append(PROJECT_ROOT / candidate)

    for item in candidates:
        if item.exists():
            return item.resolve()

    if raw.endswith(".pt"):
        from repo_paths import resolve_yolo_weight

        yolo = resolve_yolo_weight(raw)
        if yolo.is_file():
            return yolo
    return raw


def compute_experiment_name(config: dict, explicit_name: str | None) -> str:
    if explicit_name:
        return explicit_name

    experiment_cfg = config.get("experiment", {})
    train_cfg = config.get("train", {})
    task_name = experiment_cfg.get("task_name", "detection")
    model_alias = experiment_cfg.get("model_alias", str(train_cfg.get("model", "yolo11")).replace(".", "_")).lower()
    data_version = experiment_cfg.get("data_version", "dataset_v00000000")
    run_id = experiment_cfg.get("run_id", "r001")
    date_tag = datetime.now().strftime("%Y%m%d")
    return f"{task_name}_{model_alias}_{data_version}_{date_tag}_{run_id}"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_yaml(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)


def write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=json_default) + "\n", encoding="utf-8")


def maybe_item(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    return value


def scalarize(value: Any) -> Any:
    value = maybe_item(value)
    if isinstance(value, numbers.Number):
        return float(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): scalarize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [scalarize(item) for item in value]
    return value


def json_default(value: Any) -> Any:
    return scalarize(value)


def flatten_dict(payload: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in payload.items():
        next_key = f"{prefix}/{key}" if prefix else str(key)
        if isinstance(value, dict):
            flat.update(flatten_dict(value, next_key))
        else:
            flat[next_key] = scalarize(value)
    return flat


class TeeWriter(io.TextIOBase):
    def __init__(self, *streams: io.TextIOBase) -> None:
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            stream.write(data)
            stream.flush()
        return len(data)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


@contextmanager
def tee_output(log_path: Path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        stdout_writer = TeeWriter(sys.stdout, handle)
        stderr_writer = TeeWriter(sys.stderr, handle)
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = stdout_writer
        sys.stderr = stderr_writer
        try:
            yield
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr


def build_swanlab_config(config: dict, exp_name: str, phase: str, experiment_dir: Path, extra_config: dict[str, Any]) -> dict:
    swanlab_cfg = config.get("swanlab", {})
    experiment_cfg = config.get("experiment", {})
    data_cfg = config.get("data", {})
    train_cfg = config.get("train", {})

    description = swanlab_cfg.get("description")
    if not description:
        description = (
            f"{experiment_cfg.get('baseline_name', 'detection_baseline')} {phase} run "
            f"for {exp_name} using {data_cfg.get('view', 'crop_ui')}."
        )

    run_config = {
        "experiment": experiment_cfg,
        "data": data_cfg,
        "train": train_cfg,
        "paths": {
            "experiment_dir": str(experiment_dir),
        },
        "phase": phase,
        **extra_config,
    }

    return {
        "enabled": bool(swanlab_cfg.get("enabled", True)),
        "strict": bool(swanlab_cfg.get("strict", False)),
        "project": swanlab_cfg.get("project", "gastric_tstaging_detection"),
        "workspace": swanlab_cfg.get("workspace"),
        "experiment_name": swanlab_cfg.get("experiment_name") or f"{exp_name}-{phase}",
        "description": description,
        "job_type": swanlab_cfg.get("job_type", phase),
        "group": swanlab_cfg.get("group", experiment_cfg.get("baseline_name", "detection_baseline_v1")),
        "tags": list(swanlab_cfg.get("tags", ["detection", "yolo11", data_cfg.get("view", "crop_ui"), phase])),
        "logdir": str((experiment_dir / swanlab_cfg.get("logdir", "swanlab")).resolve()),
        "mode": swanlab_cfg.get("mode", "local"),
        "public": swanlab_cfg.get("public"),
        "config": run_config,
        "resume": swanlab_cfg.get("resume", "never"),
        "reinit": True,
        "parallel": swanlab_cfg.get("parallel"),
    }


def init_swanlab_run(config: dict) -> tuple[Any | None, dict[str, Any]]:
    metadata = {
        "enabled": bool(config.get("enabled", False)),
        "active": False,
        "mode": config.get("mode"),
        "project": config.get("project"),
        "experiment_name": config.get("experiment_name"),
        "logdir": config.get("logdir"),
        "error": None,
    }
    if not config.get("enabled", False):
        return None, metadata

    try:
        import swanlab
    except ImportError as exc:
        metadata["error"] = f"SwanLab import failed: {exc}"
        if config.get("strict", False):
            raise
        return None, metadata

    init_kwargs = {
        "project": config.get("project"),
        "workspace": config.get("workspace"),
        "experiment_name": config.get("experiment_name"),
        "description": config.get("description"),
        "job_type": config.get("job_type"),
        "group": config.get("group"),
        "tags": config.get("tags"),
        "config": config.get("config"),
        "logdir": config.get("logdir"),
        "mode": config.get("mode"),
        "public": config.get("public"),
        "resume": config.get("resume"),
        "reinit": config.get("reinit"),
    }
    if config.get("parallel") is not None:
        init_kwargs["parallel"] = config.get("parallel")
    if config.get("id") is not None:
        init_kwargs["id"] = config.get("id")

    try:
        run = swanlab.init(**init_kwargs)
    except Exception as exc:
        metadata["error"] = f"SwanLab init failed: {exc}"
        if config.get("strict", False):
            raise
        return None, metadata

    metadata.update(
        {
            "active": True,
            "run_id": getattr(run, "id", None),
            "run_url": getattr(run, "url", None),
        }
    )
    return run, metadata


def finish_swanlab_run(run: Any | None) -> None:
    if run is None:
        return
    finish = getattr(run, "finish", None)
    if callable(finish):
        finish()


def log_swanlab(run: Any | None, payload: dict[str, Any]) -> None:
    if run is None:
        return
    flattened = flatten_dict(payload)
    numeric_payload = {}
    for key, value in flattened.items():
        if isinstance(value, bool):
            numeric_payload[key] = int(value)
        elif isinstance(value, numbers.Number):
            numeric_payload[key] = value
    if numeric_payload:
        run.log(numeric_payload)


def bootstrap_ultralytics_custom_modules(custom_modules: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    if not custom_modules:
        return []

    import ultralytics.nn.tasks as tasks

    registered: list[dict[str, str]] = []
    for item in custom_modules:
        if not isinstance(item, dict):
            raise ValueError(f"Each custom module entry must be a mapping, got: {item!r}")
        module_name = item.get("module")
        symbols = item.get("symbols", [])
        if not module_name:
            raise ValueError(f"Missing `module` in custom module entry: {item!r}")
        if not symbols:
            raise ValueError(f"Missing `symbols` in custom module entry: {item!r}")

        imported = importlib.import_module(str(module_name))
        for symbol in symbols:
            obj = getattr(imported, str(symbol), None)
            if obj is None:
                raise AttributeError(f"Module {module_name} does not export symbol {symbol}")
            setattr(tasks, str(symbol), obj)
            registered.append({"module": str(module_name), "symbol": str(symbol)})
    return registered


def collect_validation_metrics(metrics: Any, class_names: list[str] | None = None) -> dict[str, Any]:
    if metrics is None or not hasattr(metrics, "box"):
        return {}

    summary = {
        "map50_95": scalarize(metrics.box.map),
        "map50": scalarize(metrics.box.map50),
        "map75": scalarize(metrics.box.map75),
        "precision": scalarize(metrics.box.mp),
        "recall": scalarize(metrics.box.mr),
    }
    if class_names:
        per_class = {}
        maps_value = scalarize(metrics.box.maps)
        if isinstance(maps_value, list):
            maps = maps_value
        elif isinstance(maps_value, numbers.Number):
            maps = [float(maps_value)]
        else:
            maps = []
        for index, class_name in enumerate(class_names):
            if index < len(maps):
                per_class[class_name] = maps[index]
        summary["per_class_map50_95"] = per_class
    return summary
