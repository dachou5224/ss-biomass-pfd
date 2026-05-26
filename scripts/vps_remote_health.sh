#!/usr/bin/env bash
# 本机触发 VPS 资源巡检
set -euo pipefail
HOST="${VPS_SSH_HOST:-nice-ai-LZ}"
REMOTE="${VPS_REMOTE_PATH:-/opt/ss-biomass-pfd}"
CLEANUP="${1:-}"

ARGS=""
if [[ "$CLEANUP" == "--cleanup" ]]; then
  ARGS="--cleanup"
fi

for i in 1 2 3 4 5; do
  if ssh -o BatchMode=yes -o ConnectTimeout=25 nice-ai-LZ \
    "cd ${REMOTE} && bash deploy/vps_health_check.sh ${ARGS}"; then
    exit 0
  fi
  sleep 3
done
echo "VPS 巡检失败（SSH 超时）" >&2
exit 1
