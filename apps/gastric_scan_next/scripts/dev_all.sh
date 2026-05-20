#!/usr/bin/env bash
# 一键启动主工作站 (3000) + 视频标注 (3100)
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VIDEO_ROOT="${VIDEO_ANNOTATOR_ROOT:-/data/research/gastric/Tstaging/archived/legacy_tools_v1/annotators/video_annotator}"
VIDEO_PORT="${VIDEO_ANNOTATOR_PORT:-3100}"
LOG_DIR="$APP_DIR/logs"

mkdir -p "$LOG_DIR"

echo "==> Starting main workstation..."
bash "$APP_DIR/scripts/dev_server.sh" start

if [[ -d "$VIDEO_ROOT" ]]; then
  echo "==> Starting video annotator on :$VIDEO_PORT ..."
  pkill -f "next dev -p $VIDEO_PORT" 2>/dev/null || true
  sleep 1
  nohup env GASTRIC_ROOT="${GASTRIC_ROOT:-/data/research/gastric/GastricTstaging}" \
    bash -lc "cd '$VIDEO_ROOT' && npm run dev -- -H 0.0.0.0 -p $VIDEO_PORT" \
    >> "$LOG_DIR/video_annotator.log" 2>&1 \
    < /dev/null &
  echo $! > "$LOG_DIR/video_annotator.pid"

  for _ in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:$VIDEO_PORT/" -o /dev/null 2>/dev/null; then
      echo "Video annotator ready: http://127.0.0.1:$VIDEO_PORT"
      break
    fi
    sleep 1
  done
else
  echo "Video annotator skipped (not found: $VIDEO_ROOT)"
fi

echo
echo "Main:  http://127.0.0.1:3000"
echo "Annot: http://127.0.0.1:3000/annotate"
if [[ -d "$VIDEO_ROOT" ]]; then
  echo "Video: http://127.0.0.1:$VIDEO_PORT"
fi
