#!/usr/bin/env bash
# 启动 Grad-CAM 筛图、主线文档图、主工作站与视频标注，便于完整查看可视化。
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="${GASTRIC_ROOT:-/data/research/gastric/GastricTstaging}"
LOG_DIR="$APP_DIR/logs"
mkdir -p "$LOG_DIR"

GRADCAM_PORT="${GRADCAM_SCREENING_PORT:-3110}"
DOCS_PORT="${MAINLINE_DOCS_PORT:-3111}"
GRADCAM_BUNDLE="${GRADCAM_SCREENING_ROOT:-$REPO_ROOT/pipeline/experiments/tree/gastric_tstage_4class/classification/dual_mask4ch/tstaging_4class_dual_v2_mask4ch_clinical22_full_20260423_092301/gradcam_clinical_screening}"
DOCS_ROOT="${MAINLINE_DOCS_ROOT:-$REPO_ROOT/docs/mainline}"

GRADCAM_PID="$LOG_DIR/gradcam_screening.pid"
DOCS_PID="$LOG_DIR/mainline_docs.pid"

stop_http() {
  local pid_file="$1"
  local label="$2"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "Stopping $label (pid=$pid)..."
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$pid_file"
  fi
}

start_http() {
  local port="$1"
  local root="$2"
  local pid_file="$3"
  local log_file="$4"
  local label="$5"

  if [[ ! -d "$root" ]]; then
    echo "Skip $label: directory not found ($root)" >&2
    return 0
  fi

  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null; then
      echo "$label already running (pid=$pid, port=$port)"
      return 0
    fi
  fi

  fuser -k "${port}/tcp" 2>/dev/null || true
  sleep 1

  echo "Starting $label on :$port ..."
  nohup python3 -m http.server "$port" --bind 0.0.0.0 --directory "$root" \
    >> "$log_file" 2>&1 < /dev/null &
  echo $! > "$pid_file"

  for _ in $(seq 1 15); do
    if curl -sf "http://127.0.0.1:${port}/" -o /dev/null 2>/dev/null; then
      echo "$label ready: http://127.0.0.1:${port}/"
      return 0
    fi
    sleep 1
  done
  echo "$label started but health check timed out. See $log_file" >&2
}

case "${1:-start}" in
  start)
    start_http "$GRADCAM_PORT" "$GRADCAM_BUNDLE" "$GRADCAM_PID" "$LOG_DIR/gradcam_screening.log" "Grad-CAM screening"
    start_http "$DOCS_PORT" "$DOCS_ROOT" "$DOCS_PID" "$LOG_DIR/mainline_docs.log" "Mainline docs"
    bash "$APP_DIR/scripts/dev_all.sh"
    ;;
  stop)
    stop_http "$GRADCAM_PID" "Grad-CAM screening"
    stop_http "$DOCS_PID" "Mainline docs"
    bash "$APP_DIR/scripts/dev_server.sh" stop
    if [[ -f "$LOG_DIR/video_annotator.pid" ]]; then
      kill "$(cat "$LOG_DIR/video_annotator.pid")" 2>/dev/null || true
      rm -f "$LOG_DIR/video_annotator.pid"
    fi
    pkill -f "next dev -p ${VIDEO_ANNOTATOR_PORT:-3100}" 2>/dev/null || true
    ;;
  status)
    for item in \
      "Grad-CAM:$GRADCAM_PORT:$GRADCAM_PID" \
      "Mainline docs:$DOCS_PORT:$DOCS_PID"; do
      IFS=: read -r label p pf <<< "$item"
      if [[ -f "$pf" ]] && kill -0 "$(cat "$pf")" 2>/dev/null; then
        echo "$label running on :$p (pid=$(cat "$pf"))"
      else
        echo "$label not running"
      fi
    done
    bash "$APP_DIR/scripts/dev_server.sh" status || true
    ;;
  *)
    echo "Usage: $0 {start|stop|status}"
    exit 1
    ;;
esac

LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "=== 可视化访问地址 ==="
echo "Grad-CAM 筛图:     http://127.0.0.1:${GRADCAM_PORT}/gradcam_screening.html"
echo "主线文档/组图:     http://127.0.0.1:${DOCS_PORT}/gastric_tstaging_project_logic_white.html"
echo "主工作站:          http://127.0.0.1:3000"
echo "视频/MedDINO标注:  http://127.0.0.1:${VIDEO_ANNOTATOR_PORT:-3100}"
if [[ -n "${LAN_IP:-}" ]]; then
  echo "--- 局域网 ---"
  echo "Grad-CAM: http://${LAN_IP}:${GRADCAM_PORT}/gradcam_screening.html"
  echo "主线文档: http://${LAN_IP}:${DOCS_PORT}/gastric_tstaging_project_logic_white.html"
fi
