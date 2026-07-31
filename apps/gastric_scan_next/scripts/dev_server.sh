#!/usr/bin/env bash
# 胃癌 T 分期前端 — 后台稳定运行 LAN dev server（webpack，避开 Turbopack inotify 限制）
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$APP_DIR/logs"
PID_FILE="$LOG_DIR/dev.pid"
LOG_FILE="$LOG_DIR/dev.log"
PORT="${PORT:-3000}"

export GASTRIC_ROOT="${GASTRIC_ROOT:-/data/research/gastric/GastricTstaging}"
export GASTRIC_DATASET_ROOT="${GASTRIC_DATASET_ROOT:-$GASTRIC_ROOT/dataset}"
export PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python)}"
export WATCHPACK_POLLING="${WATCHPACK_POLLING:-true}"
export CHOKIDAR_USEPOLLING="${CHOKIDAR_USEPOLLING:-true}"

# Load repo-root secrets into Next process (A6) without printing them
if [[ -f "$GASTRIC_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$GASTRIC_ROOT/.env"
  set +a
fi
if [[ -f "$APP_DIR/.env.local" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$APP_DIR/.env.local"
  set +a
fi
DS_KEY_FILE="${DEEPSEEK_API_KEY_FILE:-$GASTRIC_ROOT/docs/clinical_validation/reader_study_v150/server/deepseek_api_key.txt}"
if [[ -z "${DEEPSEEK_API_KEY:-}" && -f "$DS_KEY_FILE" ]]; then
  export DEEPSEEK_API_KEY="$(tr -d '\r\n' < "$DS_KEY_FILE")"
fi
if [[ -z "${AGENT_API_KEY:-}${POE_API_KEY:-}" && -n "${DEEPSEEK_API_KEY:-}" ]]; then
  export AGENT_API_KEY="${DEEPSEEK_API_KEY}"
  export AGENT_LLM_BASE_URL="${AGENT_LLM_BASE_URL:-${DEEPSEEK_BASE_URL:-https://api.deepseek.com}}"
  export AGENT_LLM_MODEL="${AGENT_LLM_MODEL:-${DEEPSEEK_MODEL:-deepseek-chat}}"
fi

LAN_FIXED_IP="${LAN_FIXED_IP:-10.13.199.162}"
LAN_IP_DETECTED="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}')"
LAN_IP_DETECTED="${LAN_IP_DETECTED:-127.0.0.1}"
if ip -4 addr show 2>/dev/null | grep -qE "inet ${LAN_FIXED_IP}(/| )"; then
  LAN_IP="$LAN_FIXED_IP"
else
  LAN_IP="$LAN_IP_DETECTED"
fi
export LAN_FIXED_IP
export NEXT_ALLOWED_DEV_ORIGINS="${NEXT_ALLOWED_DEV_ORIGINS:-${LAN_FIXED_IP},${LAN_IP_DETECTED}}"

mkdir -p "$LOG_DIR"

port_up() {
  curl -sf -m 2 "http://127.0.0.1:${PORT}/" -o /dev/null 2>/dev/null
}

is_running() {
  if port_up; then
    return 0
  fi
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

stop_server() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE")"
    echo "Stopping Next (pid=$pid)..."
    kill "$pid" 2>/dev/null || true
    sleep 1
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$PID_FILE"
  fi
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${PORT}/tcp" 2>/dev/null || true
  fi
  pkill -f "gastric_scan_next/node_modules/.bin/next" 2>/dev/null || true
  pkill -f "next dev --webpack -H 0.0.0.0 -p ${PORT}" 2>/dev/null || true
  echo "Stopped."
}

start_server() {
  if port_up; then
    echo "Next already up on :$PORT"
    echo "  Local:   http://127.0.0.1:$PORT"
    echo "  Network: http://${LAN_IP}:$PORT"
    # refresh pid best-effort
    local listen_pid
    listen_pid="$(ss -tlnp 2>/dev/null | awk -v p=":${PORT}" '$4 ~ p {print; exit}' | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' || true)"
    if [[ -n "${listen_pid:-}" ]]; then
      echo "$listen_pid" >"$PID_FILE"
    fi
    exit 0
  fi

  cd "$APP_DIR"
  echo "Starting Next LAN server (webpack + polling)..."
  echo "  Log: $LOG_FILE"
  setsid env \
    GASTRIC_ROOT="$GASTRIC_ROOT" \
    GASTRIC_DATASET_ROOT="$GASTRIC_DATASET_ROOT" \
    PYTHON_BIN="$PYTHON_BIN" \
    WATCHPACK_POLLING="$WATCHPACK_POLLING" \
    CHOKIDAR_USEPOLLING="$CHOKIDAR_USEPOLLING" \
    LAN_FIXED_IP="$LAN_FIXED_IP" \
    NEXT_ALLOWED_DEV_ORIGINS="$NEXT_ALLOWED_DEV_ORIGINS" \
    NEXT_DISABLE_TURBOPACK=1 \
    npx next dev --webpack -H 0.0.0.0 -p "$PORT" \
    >>"$LOG_FILE" 2>&1 < /dev/null &
  echo $! >"$PID_FILE"

  for _ in $(seq 1 60); do
    if port_up; then
      echo "Ready (pid=$(cat "$PID_FILE"))."
      echo "  Local:   http://127.0.0.1:$PORT"
      echo "  Network: http://${LAN_IP}:$PORT"
      exit 0
    fi
    sleep 1
  done

  echo "Server started but health check timed out. Check log: $LOG_FILE"
  tail -30 "$LOG_FILE" || true
  exit 1
}

status_server() {
  if port_up; then
    echo "Running on :$PORT (pid_file=$(cat "$PID_FILE" 2>/dev/null || echo n/a))"
    curl -sf -o /dev/null -w "HTTP %{http_code}\n" "http://127.0.0.1:$PORT/" 2>/dev/null || echo "HTTP check failed"
    echo "Network: http://${LAN_IP}:$PORT"
  else
    echo "Not running."
    exit 1
  fi
}

case "${1:-start}" in
  start)   start_server ;;
  stop)    stop_server ;;
  restart) stop_server; start_server ;;
  status)  status_server ;;
  log)     tail -f "$LOG_FILE" ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|log}"
    exit 1
    ;;
esac
