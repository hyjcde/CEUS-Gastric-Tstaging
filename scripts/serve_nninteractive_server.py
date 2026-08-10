#!/usr/bin/env python3
"""Run the official nnInteractive server from the checked-out source tree.

The official v1.0 checkpoint uses a 192^3 inference patch. On a 24 GiB
workstation GPU that patch can exceed the available memory during the server's
startup warmup, especially while SAM services are also resident. The wrapper
keeps the official model and interaction implementation, but defaults the
runtime patch to 128^3 and disables cuDNN benchmark workspace selection.

Usage:
  .venv-nninteractive/bin/python scripts/serve_nninteractive_server.py \
    --model nnInteractive_v1.0 --host 127.0.0.1 --port 1527 --device cuda:0

Set NNINTERACTIVE_PATCH_SIZE=192 to restore the checkpoint patch size when
running on a GPU with enough memory. Set it to 0 to leave the source default
unchanged.
"""

from __future__ import annotations

import os
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "external" / "nnInteractive"
CLIENT_ROOT = SOURCE_ROOT / "client"
DEFAULT_ENV_PYTHON = ROOT / ".venv-nninteractive" / "bin" / "python"
PATCH_SIZE = int(os.getenv("NNINTERACTIVE_PATCH_SIZE", "128"))

if not (SOURCE_ROOT / "nnInteractive").is_dir():
    raise SystemExit(
        f"Official nnInteractive source is missing at {SOURCE_ROOT}. "
        "Clone https://github.com/MIC-DKFZ/nnInteractive there first."
    )
if not CLIENT_ROOT.is_dir():
    raise SystemExit(f"Official nnInteractive client source is missing at {CLIENT_ROOT}")
if PATCH_SIZE < 0 or (PATCH_SIZE and PATCH_SIZE % 32):
    raise SystemExit("NNINTERACTIVE_PATCH_SIZE must be 0 or a positive multiple of 32")
try:
    nnunet_version = tuple(int(part) for part in version("nnunetv2").split(".")[:2])
except (PackageNotFoundError, ValueError) as error:
    raise SystemExit(
        "nnunetv2>=2.7.0 is required. Use the dedicated "
        f"{DEFAULT_ENV_PYTHON} environment."
    ) from error
if nnunet_version < (2, 7):
    raise SystemExit(
        f"nnunetv2 {version('nnunetv2')} is too old for the official source. "
        f"Use {DEFAULT_ENV_PYTHON}."
    )

os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")
sys.path[:0] = [str(SOURCE_ROOT), str(CLIENT_ROOT)]

import torch
from nnInteractive.inference.inference_session import nnInteractiveInferenceSession


_original_init = nnInteractiveInferenceSession.__init__


def _patched_init(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)
    if self.device.type == "cuda":
        torch.backends.cudnn.benchmark = False


nnInteractiveInferenceSession.__init__ = _patched_init

_original_initialize = nnInteractiveInferenceSession.initialize_from_loaded_artifacts


def _patched_initialize(self, artifacts):
    _original_initialize(self, artifacts)
    if PATCH_SIZE:
        configuration_manager = self.configuration_manager
        if configuration_manager is not None:
            configuration_manager.configuration["patch_size"] = [PATCH_SIZE] * 3


nnInteractiveInferenceSession.initialize_from_loaded_artifacts = _patched_initialize


def main() -> int:
    from nnInteractive.inference.server.main import main as official_main

    return int(official_main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
