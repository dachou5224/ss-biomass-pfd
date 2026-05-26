#!/usr/bin/env bash
# VPS 资源与 API 健康巡检（只读 + 可选清理）
# 用法:
#   bash deploy/vps_health_check.sh              # 巡检
#   bash deploy/vps_health_check.sh --cleanup    # 巡检后执行磁盘清理
set -euo pipefail

CLEANUP=0
if [[ "${1:-}" == "--cleanup" ]]; then
  CLEANUP=1
fi

log() { echo "[$(date '+%F %T')] $*"; }

warn() { echo "[WARN] $*" >&2; }

fail=0

check_pct() {
  local used=$1
  local label=$2
  local yellow=${3:-80}
  local red=${4:-90}
  if (( used >= red )); then
    warn "$label 使用率 ${used}% ≥ ${red}%（危险）"
    fail=1
  elif (( used >= yellow )); then
    warn "$label 使用率 ${used}% ≥ ${yellow}%（偏高）"
  else
    log "$label 使用率 ${used}%（正常）"
  fi
}

log "=== 磁盘 / 内存 ==="
df -h /
df -i /
free -h
uptime

disk_used=$(df / | awk 'NR==2 {gsub(/%/,"",$5); print $5}')
inode_used=$(df -i / | awk 'NR==2 {gsub(/%/,"",$5); print $5}')
check_pct "${disk_used:-0}" "根分区"
check_pct "${inode_used:-0}" "inode" 85 95

log "=== 大目录 ==="
du -sh /var/lib/docker /var/log /tmp /var/cache/apt 2>/dev/null | sort -hr || true

if command -v docker >/dev/null 2>&1; then
  log "=== Docker ==="
  docker system df || true
fi

log "=== 服务 ==="
for svc in ss-biomass-api nginx sshd docker; do
  if systemctl list-unit-files "${svc}.service" &>/dev/null; then
    st=$(systemctl is-active "$svc" 2>/dev/null || echo inactive)
    log "$svc: $st"
    [[ "$st" == "active" ]] || { warn "$svc 未 active"; fail=1; }
  fi
done

log "=== API 本机 health ==="
if curl -sS -o /dev/null -w "HTTP:%{http_code} total:%{time_total}s\n" --max-time 8 http://127.0.0.1:8765/health; then
  :
else
  warn "127.0.0.1:8765/health 失败"
  fail=1
fi

if (( CLEANUP )); then
  log "=== 执行磁盘清理 ==="
  ROOT="$(cd "$(dirname "$0")/.." && pwd)"
  bash "$ROOT/deploy/vps_disk_cleanup.sh"
fi

log "=== 完成（exit=$fail）==="
exit "$fail"
