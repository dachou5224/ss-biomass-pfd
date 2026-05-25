#!/usr/bin/env bash
# 本机 → VPS 同步代码并执行 deploy/deploy.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${VPS_SSH_HOST:-nice-ai-LZ}"
REMOTE="${VPS_REMOTE_PATH:-/opt/ss-biomass-pfd}"

cd "$ROOT"
echo "==> rsync 到 ${HOST}:${REMOTE}"
rsync -avz --delete \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' \
  --exclude 'doc/*DBI*.pdf' \
  --exclude 'export/*.xlsx' --exclude 'export/*.xlsm' \
  ./ "${HOST}:${REMOTE}/"

if [[ -d data/reference ]]; then
  echo "==> rsync data/reference"
  rsync -avz data/reference/ "${HOST}:${REMOTE}/data/reference/"
fi

echo "==> 远程 deploy.sh"
ssh -o BatchMode=yes -o ConnectTimeout=25 -o ServerAliveInterval=10 "${HOST}" \
  "cd ${REMOTE} && bash deploy/deploy.sh"

echo "==> 健康检查"
curl -sS -A ss-biomass-pfd-sync/1.0 -o /dev/null -w "https://simapi.nice-ai.dev/health HTTP:%{http_code} total:%{time_total}s\n" \
  --connect-timeout 15 --max-time 60 https://simapi.nice-ai.dev/health
