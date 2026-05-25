#!/usr/bin/env bash
# VPS 磁盘清理（含 Docker 临时文件）
# 用法（在 VPS 上 root 执行）:
#   bash deploy/vps_disk_cleanup.sh
#   bash deploy/vps_disk_cleanup.sh --aggressive   # 额外 prune 未使用镜像/卷
set -euo pipefail

AGGRESSIVE=0
if [[ "${1:-}" == "--aggressive" ]]; then
  AGGRESSIVE=1
fi

log() { echo "[$(date '+%F %T')] $*"; }

log "=== 清理前 ==="
df -h /
df -i /
echo
free -h
echo

log "=== 大目录 Top 10 ==="
du -xh /var/lib/docker /var/log /tmp /var/cache /root 2>/dev/null | sort -hr | head -15 || true
echo

if command -v docker >/dev/null 2>&1; then
  log "=== Docker 占用 ==="
  docker system df || true
  echo

  log "停止已退出容器、清理 dangling 镜像/网络/构建缓存..."
  docker container prune -f || true
  docker image prune -f || true
  docker network prune -f || true
  docker builder prune -f --filter 'until=24h' 2>/dev/null || docker builder prune -f 2>/dev/null || true

  if [[ "$AGGRESSIVE" == "1" ]]; then
    log "aggressive: 清理未使用镜像与匿名卷（--volumes）..."
    docker system prune -af --volumes || true
  else
    log "常规: docker system prune（保留未标记为 dangling 的镜像）..."
    docker system prune -f || true
  fi

  log "=== Docker 清理后 ==="
  docker system df || true
else
  log "未安装 docker，跳过 Docker 清理"
fi
echo

log "=== 系统日志与缓存 ==="
journalctl --vacuum-size=200M 2>/dev/null || true
journalctl --vacuum-time=14d 2>/dev/null || true
apt-get clean -y 2>/dev/null || yum clean all -y 2>/dev/null || true
find /var/log -type f -name '*.gz' -mtime +14 -delete 2>/dev/null || true
find /var/log -type f -name '*.1' -mtime +14 -delete 2>/dev/null || true
find /tmp -mindepth 1 -maxdepth 1 -mtime +7 -exec rm -rf {} + 2>/dev/null || true
find /var/tmp -mindepth 1 -maxdepth 1 -mtime +7 -exec rm -rf {} + 2>/dev/null || true
echo

log "=== 清理后 ==="
df -h /
df -i /
echo
free -h

log "=== 关键服务状态 ==="
for svc in sshd docker nginx ss-biomass-api; do
  if systemctl list-unit-files "$svc.service" &>/dev/null; then
    systemctl is-active "$svc" 2>/dev/null && log "$svc: active" || log "$svc: inactive/failed"
  fi
done

log "完成。若 SSH 仍异常，执行: systemctl restart sshd"
