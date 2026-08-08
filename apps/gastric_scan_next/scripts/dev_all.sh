#!/usr/bin/env bash
# 一键启动主工作站 (3000) + 视频标注 (3100)
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VIDEO_ROOT="${VIDEO_ANNOTATOR_ROOT:-/data/research/gastric/Tstaging/archived/legacy_tools_v1/annotators/video_annotator}"
VIDEO_PORT="${VIDEO_ANNOTATOR_PORT:-3100}"
GASTRIC_ROOT="${GASTRIC_ROOT:-/data/research/gastric/GastricTstaging}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python)}"
NNINTERACTIVE_SERVER_PYTHON_BIN="${NNINTERACTIVE_SERVER_PYTHON_BIN:-/tmp/gastric-nninteractive-venv/bin/python}"
if [[ ! -x "$NNINTERACTIVE_SERVER_PYTHON_BIN" ]]; then
  NNINTERACTIVE_SERVER_PYTHON_BIN="$PYTHON_BIN"
fi
NNINTERACTIVE_BRIDGE_PYTHON_BIN="${NNINTERACTIVE_BRIDGE_PYTHON_BIN:-$NNINTERACTIVE_SERVER_PYTHON_BIN}"
SAM_HOST="${SAM_HOST:-0.0.0.0}"
SAM_PORT="${SAM_PORT:-8767}"
SAM31_HOST="${SAM31_HOST:-0.0.0.0}"
SAM31_PORT="${SAM31_PORT:-8768}"
SAM31_CUDA_VISIBLE_DEVICES="${SAM31_CUDA_VISIBLE_DEVICES:-1}"
SAM31_CHECKPOINT="${SAM31_CHECKPOINT:-$GASTRIC_ROOT/external/sam3.1/sam3.1_multiplex.pt}"
SAM31_LORA_CHECKPOINT="${SAM31_LORA_CHECKPOINT:-$GASTRIC_ROOT/artifacts/sam31_training/sam31_gastric_lora_full/best_lora_weights.pt}"
NNINTERACTIVE_HOST="${NNINTERACTIVE_HOST:-127.0.0.1}"
NNINTERACTIVE_PORT="${NNINTERACTIVE_PORT:-8770}"
NNINTERACTIVE_AUTOSTART="${NNINTERACTIVE_AUTOSTART:-0}"
NN_INTERACTIVE_SERVER_URL="${NN_INTERACTIVE_SERVER_URL:-}"
NN_INTERACTIVE_API_KEY="${NN_INTERACTIVE_API_KEY:-}"
NNINTERACTIVE_SERVER_AUTOSTART="${NNINTERACTIVE_SERVER_AUTOSTART:-0}"
NNINTERACTIVE_SERVER_HOST="${NNINTERACTIVE_SERVER_HOST:-127.0.0.1}"
NNINTERACTIVE_SERVER_PORT="${NNINTERACTIVE_SERVER_PORT:-1527}"
NNINTERACTIVE_SERVER_DEVICE="${NNINTERACTIVE_SERVER_DEVICE:-cuda:0}"
NNINTERACTIVE_PATCH_SIZE="${NNINTERACTIVE_PATCH_SIZE:-128}"
TEMPORAL_CHECKPOINT="$GASTRIC_ROOT/experiments/prompt_mask_agent/r003_temporal_adapter/full_proxy/best_sam2_temporal_adapter.pt"
if [[ -z "${SAM2_VIDEO_CHECKPOINT:-}" && -f "$TEMPORAL_CHECKPOINT" ]]; then
  SAM2_VIDEO_CHECKPOINT="$TEMPORAL_CHECKPOINT"
fi
LOG_DIR="$APP_DIR/logs"
SAM_LOG="$LOG_DIR/sam_agent.log"
SAM_PID="$LOG_DIR/sam_agent.pid"
NNINTERACTIVE_LOG="$LOG_DIR/nninteractive_bridge.log"
NNINTERACTIVE_PID="$LOG_DIR/nninteractive_bridge.pid"
NNINTERACTIVE_SERVER_LOG="$LOG_DIR/nninteractive_server.log"
NNINTERACTIVE_SERVER_PID="$LOG_DIR/nninteractive_server.pid"

mkdir -p "$LOG_DIR"

echo "==> Starting main workstation..."
bash "$APP_DIR/scripts/dev_server.sh" start

start_sam_agent() {
  if curl -sf -m 3 "http://127.0.0.1:$SAM_PORT/api/sam/status" -o /dev/null 2>/dev/null \
    && curl -sf -m 3 "http://127.0.0.1:$SAM_PORT/api/sam/video-status" -o /dev/null 2>/dev/null; then
    echo "SAM2 LAN inference already up: http://127.0.0.1:$SAM_PORT"
    return 0
  fi

  echo "==> Starting SAM2 LAN inference on :$SAM_PORT ..."
  nohup setsid env \
    GASTRIC_ROOT="$GASTRIC_ROOT" \
    SAM_HOST="$SAM_HOST" \
    SAM_PORT="$SAM_PORT" \
    SAM2_VIDEO_CHECKPOINT="${SAM2_VIDEO_CHECKPOINT:-}" \
    "${PYTHON_BIN:-python3}" "$GASTRIC_ROOT/scripts/serve_interactive_sam_agent.py" \
    --host "$SAM_HOST" \
    --port "$SAM_PORT" \
    >> "$SAM_LOG" 2>&1 \
    < /dev/null &
  echo $! > "$SAM_PID"

  for _ in $(seq 1 60); do
    if curl -sf -m 3 "http://127.0.0.1:$SAM_PORT/api/sam/status" -o /dev/null 2>/dev/null \
      && curl -sf -m 3 "http://127.0.0.1:$SAM_PORT/api/sam/video-status" -o /dev/null 2>/dev/null; then
      echo "SAM2 LAN inference ready: http://${SAM_HOST}:$SAM_PORT"
      return 0
    fi
    sleep 1
  done

  echo "SAM2 inference started but health check timed out. Check log: $SAM_LOG"
}

start_sam31_static() {
  if curl -sf -m 3 "http://127.0.0.1:$SAM31_PORT/api/sam31/status" -o /dev/null 2>/dev/null; then
    echo "SAM3.1 static inference already up: http://127.0.0.1:$SAM31_PORT"
    return 0
  fi

  if [[ ! -f "$SAM31_CHECKPOINT" ]]; then
    echo "SAM3.1 static inference skipped (checkpoint not found: $SAM31_CHECKPOINT)"
    return 0
  fi

  echo "==> Starting SAM3.1 static inference on :$SAM31_PORT (GPU $SAM31_CUDA_VISIBLE_DEVICES) ..."
  nohup setsid env \
    GASTRIC_ROOT="$GASTRIC_ROOT" \
    SAM31_CHECKPOINT="$SAM31_CHECKPOINT" \
    SAM31_LORA_CHECKPOINT="$SAM31_LORA_CHECKPOINT" \
    CUDA_VISIBLE_DEVICES="$SAM31_CUDA_VISIBLE_DEVICES" \
    "${PYTHON_BIN:-python3}" "$GASTRIC_ROOT/scripts/serve_sam31_static.py" \
    --host "$SAM31_HOST" \
    --port "$SAM31_PORT" \
    >> "$LOG_DIR/sam31_static.log" 2>&1 \
    < /dev/null &
  echo $! > "$LOG_DIR/sam31_static.pid"

  for _ in $(seq 1 120); do
    if curl -sf -m 3 "http://127.0.0.1:$SAM31_PORT/api/sam31/status" -o /dev/null 2>/dev/null; then
      echo "SAM3.1 static inference ready: http://${SAM31_HOST}:$SAM31_PORT"
      return 0
    fi
    sleep 1
  done

  echo "SAM3.1 static inference started but health check timed out. Check log: $LOG_DIR/sam31_static.log"
}

start_nninteractive_server() {
  if [[ -n "$NN_INTERACTIVE_SERVER_URL" ]]; then
    echo "nnInteractive official server uses configured URL: $NN_INTERACTIVE_SERVER_URL"
    return 0
  fi
  if [[ "$NNINTERACTIVE_SERVER_AUTOSTART" == "0" || "$NNINTERACTIVE_SERVER_AUTOSTART" == "false" ]]; then
    echo "nnInteractive official server skipped (NNINTERACTIVE_SERVER_AUTOSTART=$NNINTERACTIVE_SERVER_AUTOSTART)"
    return 0
  fi
  if curl -sf -m 3 "http://127.0.0.1:$NNINTERACTIVE_SERVER_PORT/healthz" -o /dev/null 2>/dev/null; then
    NN_INTERACTIVE_SERVER_URL="http://127.0.0.1:$NNINTERACTIVE_SERVER_PORT"
    echo "nnInteractive official server already up: $NN_INTERACTIVE_SERVER_URL"
    return 0
  fi

  echo "==> Starting official nnInteractive server on :$NNINTERACTIVE_SERVER_PORT ..."
  nohup setsid env \
    NNINTERACTIVE_PATCH_SIZE="$NNINTERACTIVE_PATCH_SIZE" \
    NN_INTERACTIVE_API_KEY="$NN_INTERACTIVE_API_KEY" \
    "$NNINTERACTIVE_SERVER_PYTHON_BIN" "$GASTRIC_ROOT/scripts/serve_nninteractive_server.py" \
    --model nnInteractive_v1.0 \
    --host "$NNINTERACTIVE_SERVER_HOST" \
    --port "$NNINTERACTIVE_SERVER_PORT" \
    --device "$NNINTERACTIVE_SERVER_DEVICE" \
    --no-torch-compile \
    >> "$NNINTERACTIVE_SERVER_LOG" 2>&1 \
    < /dev/null &
  echo $! > "$NNINTERACTIVE_SERVER_PID"

  for _ in $(seq 1 180); do
    if curl -sf -m 3 "http://127.0.0.1:$NNINTERACTIVE_SERVER_PORT/healthz" -o /dev/null 2>/dev/null; then
      NN_INTERACTIVE_SERVER_URL="http://127.0.0.1:$NNINTERACTIVE_SERVER_PORT"
      echo "nnInteractive official server ready: $NN_INTERACTIVE_SERVER_URL"
      return 0
    fi
    sleep 1
  done

  echo "nnInteractive official server started but health check timed out. Check log: $NNINTERACTIVE_SERVER_LOG"
}

start_nninteractive_bridge() {
  if [[ -z "$NN_INTERACTIVE_SERVER_URL" ]]; then
    echo "nnInteractive bridge skipped (NN_INTERACTIVE_SERVER_URL is not configured)"
    return 0
  fi
  if curl -sf -m 3 "http://127.0.0.1:$NNINTERACTIVE_PORT/api/nninteractive/status" -o /dev/null 2>/dev/null; then
    echo "nnInteractive bridge already up: http://127.0.0.1:$NNINTERACTIVE_PORT"
    return 0
  fi

  echo "==> Starting nnInteractive bridge on :$NNINTERACTIVE_PORT ..."
  nohup setsid env \
    NN_INTERACTIVE_SERVER_URL="$NN_INTERACTIVE_SERVER_URL" \
    NN_INTERACTIVE_API_KEY="$NN_INTERACTIVE_API_KEY" \
    NNINTERACTIVE_HOST="$NNINTERACTIVE_HOST" \
    NNINTERACTIVE_PORT="$NNINTERACTIVE_PORT" \
    "$NNINTERACTIVE_BRIDGE_PYTHON_BIN" "$GASTRIC_ROOT/scripts/serve_nninteractive_agent.py" \
    --host "$NNINTERACTIVE_HOST" \
    --port "$NNINTERACTIVE_PORT" \
    >> "$NNINTERACTIVE_LOG" 2>&1 \
    < /dev/null &
  echo $! > "$NNINTERACTIVE_PID"

  for _ in $(seq 1 30); do
    if curl -sf -m 3 "http://127.0.0.1:$NNINTERACTIVE_PORT/api/nninteractive/status" -o /dev/null 2>/dev/null; then
      echo "nnInteractive bridge ready: http://${NNINTERACTIVE_HOST}:$NNINTERACTIVE_PORT"
      return 0
    fi
    sleep 1
  done

  echo "nnInteractive bridge started but health check timed out. Check log: $NNINTERACTIVE_LOG"
}

if [[ "${SAM_AUTOSTART:-1}" != "0" && "${SAM_AUTOSTART:-1}" != "false" ]]; then
  start_sam_agent
else
  echo "SAM2 LAN inference skipped (SAM_AUTOSTART=$SAM_AUTOSTART)"
fi

if [[ "${SAM31_AUTOSTART:-1}" != "0" && "${SAM31_AUTOSTART:-1}" != "false" ]]; then
  start_sam31_static
else
  echo "SAM3.1 static inference skipped (SAM31_AUTOSTART=$SAM31_AUTOSTART)"
fi

start_nninteractive_server
if [[ "$NNINTERACTIVE_AUTOSTART" != "0" && "$NNINTERACTIVE_AUTOSTART" != "false" ]]; then
  start_nninteractive_bridge
else
  echo "nnInteractive bridge skipped (NNINTERACTIVE_AUTOSTART=$NNINTERACTIVE_AUTOSTART)"
fi

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
echo "LAN:   http://${LAN_FIXED_IP:-10.13.199.162}:3000"
echo "SAM2:  http://${SAM_HOST}:$SAM_PORT/interactive_video_agent.html"
echo "SAM3.1 static: http://${SAM31_HOST}:$SAM31_PORT"
echo "nnInteractive bridge: http://${NNINTERACTIVE_HOST}:$NNINTERACTIVE_PORT"
echo "Annot: http://127.0.0.1:3000/annotate"
if [[ -d "$VIDEO_ROOT" ]]; then
  echo "Video: http://127.0.0.1:$VIDEO_PORT"
fi
echo "Tip: run scripts/serve_visual_review.sh for Grad-CAM screening (:3110) + mainline figures (:3111)"
