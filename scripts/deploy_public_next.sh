#!/usr/bin/env bash
# Atomic public reader-only deploy for Aliyun Next (:80 auth → :3000).
#
# Local:
#   bash scripts/deploy_public_next.sh
#
# CI (after npm build already produced .next-public-deploy-dist):
#   bash scripts/deploy_public_next.sh --skip-build --remote aliyun-reader
#
# Required remote layout:
#   /var/www/gastric-next/.next-public-deploy-dist
#   /var/www/gastric-next/server.js
#   systemd: gastric-next.service
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/apps/gastric_scan_next"
DIST_NAME=".next-public-deploy-dist"
REMOTE="${DEPLOY_SSH_HOST:-aliyun-reader}"
REMOTE_APP="${DEPLOY_REMOTE_APP:-/var/www/gastric-next}"
SKIP_BUILD=0
SKIP_VERIFY=0

usage() {
  cat <<'EOF'
Usage: deploy_public_next.sh [--skip-build] [--skip-verify] [--remote HOST]

Builds NEXT_PUBLIC_READER_ONLY=1 into apps/gastric_scan_next/.next-public-deploy-dist,
rsyncs atomically to Aliyun /var/www/gastric-next, restarts gastric-next.

Environment:
  DEPLOY_SSH_HOST     SSH host (default: aliyun-reader)
  DEPLOY_REMOTE_APP   Remote app dir (default: /var/www/gastric-next)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-build) SKIP_BUILD=1 ;;
    --skip-verify) SKIP_VERIFY=1 ;;
    --remote) REMOTE="${2:?}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

DIST="$APP/$DIST_NAME"
STAMP="$(date +%Y%m%d_%H%M%S)"

if [[ ! -d "$APP" ]]; then
  echo "Missing app dir: $APP" >&2
  exit 1
fi

if [[ "$SKIP_BUILD" -eq 0 ]]; then
  echo "[deploy] build reader-only → $DIST_NAME"
  cd "$APP"
  if [[ ! -d node_modules ]]; then
    npm ci
  fi
  rm -rf "$DIST"
  NEXT_PUBLIC_READER_ONLY=1 NEXT_DIST_DIR="$DIST_NAME" npm run build
fi

if [[ ! -f "$DIST/BUILD_ID" || ! -f "$DIST/standalone/server.js" ]]; then
  echo "Build incomplete: need $DIST/BUILD_ID and standalone/server.js" >&2
  exit 1
fi

BUILD_ID="$(tr -d '\n\r' < "$DIST/BUILD_ID")"
echo "[deploy] BUILD_ID=$BUILD_ID remote=$REMOTE"

# Package static assets into standalone for completeness (harmless if already present).
mkdir -p "$DIST/standalone/.next" "$DIST/standalone/data"
rm -rf "$DIST/standalone/.next/static"
cp -a "$DIST/static" "$DIST/standalone/.next/static"
if [[ -d "$APP/public" ]]; then
  rm -rf "$DIST/standalone/public"
  cp -a "$APP/public" "$DIST/standalone/public"
fi
if [[ -f "$APP/data/reader_v150_clinical.json" ]]; then
  cp -a "$APP/data/reader_v150_clinical.json" "$DIST/standalone/data/reader_v150_clinical.json"
fi
cp -a "$DIST/BUILD_ID" "$DIST/standalone/BUILD_ID"

echo "[deploy] rsync dist → ${REMOTE}:${REMOTE_APP}/.next-public-deploy-dist.new"
rsync -az --delete \
  --exclude standalone \
  --exclude cache \
  "$DIST/" \
  "${REMOTE}:${REMOTE_APP}/.next-public-deploy-dist.new/"

echo "[deploy] rsync server.js"
rsync -az \
  "$DIST/standalone/server.js" \
  "${REMOTE}:${REMOTE_APP}/server.js.new"

# Keep Next runtime deps in sync when standalone node_modules exists.
if [[ -d "$DIST/standalone/node_modules" ]]; then
  echo "[deploy] rsync standalone node_modules (may take a minute)"
  rsync -az --delete \
    "$DIST/standalone/node_modules/" \
    "${REMOTE}:${REMOTE_APP}/node_modules/"
fi

echo "[deploy] atomic swap + restart"
ssh -o BatchMode=yes "$REMOTE" "set -euo pipefail
APP='$REMOTE_APP'
STAMP='$STAMP'
BUILD='$BUILD_ID'
systemctl stop gastric-next
if [[ -d \"\$APP/.next-public-deploy-dist\" ]]; then
  mv \"\$APP/.next-public-deploy-dist\" \"\$APP/.next-public-deploy-dist.bak_\$STAMP\"
fi
mv \"\$APP/.next-public-deploy-dist.new\" \"\$APP/.next-public-deploy-dist\"
ln -sfn .next-public-deploy-dist \"\$APP/.next\"
if [[ -f \"\$APP/server.js\" ]]; then
  cp -a \"\$APP/server.js\" \"\$APP/server.js.bak_\$STAMP\"
fi
mv \"\$APP/server.js.new\" \"\$APP/server.js\"
systemctl start gastric-next
sleep 2
systemctl is-active gastric-next
echo BUILD=\$(cat \"\$APP/.next/BUILD_ID\")
test \"\$(cat \"\$APP/.next/BUILD_ID\")\" = \"\$BUILD\"
curl -fsS -o /dev/null -w 'next3000=%{http_code}\\n' --max-time 15 http://127.0.0.1:3000/
curl -fsS -o /dev/null -w 'edge_login=%{http_code}\\n' --max-time 15 http://127.0.0.1/workbench_login.html || true
"

if [[ "$SKIP_VERIFY" -eq 0 ]]; then
  echo "[deploy] public smoke"
  curl -fsS -o /dev/null -w "public_root=%{http_code}\n" --max-time 15 http://47.106.33.102/ || true
  curl -fsS -o /dev/null -w "public_clinical=%{http_code}\n" --max-time 15 http://47.106.33.102/clinical/task1.html || true
fi

echo "[deploy] done BUILD_ID=$BUILD_ID"
