#!/usr/bin/env bash
# Deploy human_assist_v2.html to the trial server.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/human_assist_v2.html"
HOST="${DEPLOY_HOST:-47.106.33.102}"
USER="${DEPLOY_USER:-root}"
REMOTE_PATH="${DEPLOY_PATH:-}"
SSH_KEY="${DEPLOY_SSH_KEY:-}"

if [[ ! -f "$SRC" ]]; then
  echo "missing $SRC" >&2
  exit 1
fi

if [[ -z "$REMOTE_PATH" ]]; then
  echo "Set DEPLOY_PATH to the remote web root that contains human_assist_v2.html" >&2
  echo "Example: DEPLOY_PATH=/opt/gastric/public ./scripts/deploy_human_assist_v2.sh" >&2
  exit 1
fi

SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)
if [[ -n "$SSH_KEY" ]]; then
  SSH_OPTS+=(-i "$SSH_KEY")
fi

echo "==> Uploading to ${USER}@${HOST}:${REMOTE_PATH}/human_assist_v2.html"
scp "${SSH_OPTS[@]}" "$SRC" "${USER}@${HOST}:${REMOTE_PATH}/human_assist_v2.html"

echo "==> Verifying live page contains lang switch"
if curl -fsS --max-time 20 "http://${HOST}/human_assist_v2.html" | grep -q 'btnLangSwitch'; then
  echo "OK: http://${HOST}/human_assist_v2.html has #btnLangSwitch"
else
  echo "WARN: live HTML does not yet show btnLangSwitch (path/cache?)" >&2
  exit 2
fi
