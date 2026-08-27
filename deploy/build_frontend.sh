#!/usr/bin/env bash
# GapirAI.uz — Frontend deploy script
# Usage: bash deploy/build_frontend.sh [server]
# Builds Next.js standalone, copies static assets, restarts service.
#
# Without arguments: runs locally (for dev)
# With "server": deploys to remote server via SSH

set -euo pipefail
cd "$(dirname "$0")/.."

BUILD_DIR="frontend"
STANDALONE="$BUILD_DIR/.next/standalone"

echo ">>> 1. Installing dependencies..."
cd "$BUILD_DIR"
npm install --prefer-offline 2>/dev/null || npm install

echo ">>> 2. Building Next.js (standalone)..."
npm run build

# Возвращаемся в корень проекта: шаги 3-4 и ветка "server" используют
# пути от корня (frontend/.next/...), а npm-шаги выполнялись внутри frontend/.
cd ..

echo ">>> 3. Copying static assets into standalone..."
mkdir -p "$STANDALONE/.next/static"
cp -r "$BUILD_DIR/.next/static/"* "$STANDALONE/.next/static/"
# Copy public dir if it exists
[ -d "$BUILD_DIR/public" ] && cp -r "$BUILD_DIR/public" "$STANDALONE/public" 2>/dev/null || true

echo ">>> 4. Verifying static files..."
for f in $(ls "$STANDALONE/.next/static/css/" 2>/dev/null | head -1); do
  echo "  CSS: $f ($(wc -c < "$STANDALONE/.next/static/css/$f") bytes)"
done

if [ "${1:-}" = "server" ]; then
  echo ">>> 5. Deploying to server..."
  ssh_cmd() { ssh -F "${HOME}/.ssh/config" whimco "$@"; }
  
  # Copy standalone directory to server
  tar czf /tmp/ai-dubber-frontend.tar.gz \
    -C "$STANDALONE" . \
    --exclude=node_modules/.cache
  
  scp -F "${HOME}/.ssh/config" /tmp/ai-dubber-frontend.tar.gz whimco:/tmp/
  ssh_cmd 'cd /opt/ai-dubber/frontend/.next/standalone && tar xzf /tmp/ai-dubber-frontend.tar.gz && rm /tmp/ai-dubber-frontend.tar.gz'
  
  # Also copy public assets if they exist
  [ -d "public" ] && tar czf /tmp/ai-dubber-public.tar.gz -C public . && \
    scp -F "${HOME}/.ssh/config" /tmp/ai-dubber-public.tar.gz whimco:/tmp/ && \
    ssh_cmd 'cd /opt/ai-dubber/frontend/.next/standalone && mkdir -p public && tar xzf /tmp/ai-dubber-public.tar.gz -C public && rm /tmp/ai-dubber-public.tar.gz'
  
  ssh_cmd 'systemctl restart ai-dubber-frontend && sleep 1 && systemctl is-active ai-dubber-frontend && echo "SERVICE: OK"'
  echo ">>> Deploy complete. Verify: curl -s -o /dev/null -w \"%{http_code}\" http://185.233.184.192/"
else
  echo ">>> 5. Starting local dev server..."
  echo "  Run: cd frontend && PORT=3000 node $STANDALONE/server.js"
  echo "  Or:  bash deploy/build_frontend.sh server  (to deploy remotely)"
fi

echo ">>> Done."
