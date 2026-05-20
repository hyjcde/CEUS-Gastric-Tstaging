#!/usr/bin/env bash
set -euo pipefail

ROOT="${VIDEO_ANNOTATOR_ROOT:-/data/research/gastric/Tstaging/archived/legacy_tools_v1/annotators/video_annotator}"
PORT="${VIDEO_ANNOTATOR_PORT:-3100}"

if [[ ! -d "$ROOT" ]]; then
  echo "Video annotator not found: $ROOT" >&2
  echo "Set VIDEO_ANNOTATOR_ROOT to the gastric-annotator directory." >&2
  exit 1
fi

cd "$ROOT"
export GASTRIC_ROOT="${GASTRIC_ROOT:-/data/research/gastric/GastricTstaging}"
export DATA_ROOT="${DATA_ROOT:-$ROOT/data}"

echo "Starting video annotator at http://localhost:${PORT}"
echo "Root: $ROOT"
echo "Data: $DATA_ROOT"

exec npm run dev -- -p "$PORT"
