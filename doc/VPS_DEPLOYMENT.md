# ss-biomass-pfd VPS 运维与部署

本文说明如何在个人 VPS（`nice-ai.dev` 体系）上部署 **Excel/WPS 联调 API**（`simapi.nice-ai.dev`），并与相邻项目（`bayes_EPL`、`coros-pulse-ai`）保持同一运维习惯：**SSH + systemd + Nginx + certbot**。

## 1. 环境与访问

| 项 | 值 |
|----|-----|
| SSH 别名（本机 `~/.ssh/config`） | `nice-ai-LZ` |
| 公网 IP | `198.23.175.235` |
| 系统用户 | `root` |
| 主机名（示例） | `racknerd-a6a98d6` |
| API 安装路径 | `/opt/ss-biomass-pfd` |
| 本地监听 | `127.0.0.1:8765`（仅 Nginx 反代，不对外暴露） |
| 对外域名 | `https://simapi.nice-ai.dev` |

连通性检查（在本机执行）：

```bash
ssh -o BatchMode=yes nice-ai-LZ 'hostname && systemctl is-active nginx'
```

**勿将** SSH 私钥、`SIM_API_KEY` 明文写入 Git 或聊天记录。

## 2. 前置条件

1. **DNS**：`simapi.nice-ai.dev` A 记录指向 `198.23.175.235`（在域名面板配置；未生效前无法签发 Let's Encrypt）。
2. VPS 已安装：`python3`、`python3-venv`、`nginx`、`certbot`（`python3-certbot-nginx`）。
3. 仓库代码已在 VPS 上（`git clone` 或 `deploy/deploy.sh` / `rsync`）。

## 3. 一键部署（推荐）

在 **VPS** 上，将本仓库放到 `/opt/ss-biomass-pfd` 后：

```bash
cd /opt/ss-biomass-pfd
sudo bash deploy/deploy.sh
```

脚本会：

- 创建/更新 `.venv` 并 `pip install -r requirements.txt`
- 若不存在则生成 `/etc/default/ss-biomass-api`（含随机 `SIM_API_KEY`）
- 安装并 `enable --now` systemd 单元 `ss-biomass-api`
- 安装 Nginx 站点 `simapi.nice-ai.dev`（含限流、`client_max_body_size`）
- 在 DNS 已生效时尝试 `certbot --nginx -d simapi.nice-ai.dev`（默认联系邮箱 `dachou5224@gmail.com`）

从 **本机** 同步代码并触发部署（开发机有最新未 push 提交时适用）：

```bash
cd /path/to/ss-biomass-pfd
rsync -avz --delete \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
  --exclude 'doc/*DBI*.pdf' \
  --exclude 'export/*.xlsx' --exclude 'export/*.xlsm' \
  ./ nice-ai-LZ:/opt/ss-biomass-pfd/
# data/reference 不入 Git，但 VPS 运行 API 必需（至少 inci_streams.csv）
rsync -avz data/reference/ nice-ai-LZ:/opt/ss-biomass-pfd/data/reference/
ssh nice-ai-LZ 'cd /opt/ss-biomass-pfd && bash deploy/deploy.sh'
```

## 4. 手动分步部署

### 4.1 代码与虚拟环境

```bash
sudo mkdir -p /opt/ss-biomass-pfd
sudo chown "$USER":"$USER" /opt/ss-biomass-pfd
cd /opt/ss-biomass-pfd
git clone https://github.com/dachou5224/ss-biomass-pfd.git .   # 或 rsync 自开发机

python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
```

### 4.2 运行时环境变量

复制模板并编辑（**仅保存在 VPS**）：

```bash
sudo cp deploy/env.example /etc/default/ss-biomass-api
sudo chmod 600 /etc/default/ss-biomass-api
sudo nano /etc/default/ss-biomass-api
```

关键变量见 `deploy/env.example`：

- `SIM_API_KEY`：非空则 `POST` 必须带 `X-API-Key`
- `SIM_API_ALLOWED_ORIGINS`：CORS 白名单，逗号分隔

### 4.3 systemd

```bash
sudo cp deploy/systemd/ss-biomass-api.service /etc/systemd/system/
sudo chown -R www-data:www-data /opt/ss-biomass-pfd
sudo systemctl daemon-reload
sudo systemctl enable --now ss-biomass-api
sudo systemctl status ss-biomass-api
curl -sS http://127.0.0.1:8765/health
```

### 4.4 Nginx + HTTPS

```bash
sudo cp deploy/nginx-simapi.conf.example /etc/nginx/conf.d/simapi.nice-ai.dev.conf
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d simapi.nice-ai.dev --non-interactive --agree-tos -m dachou5224@gmail.com
curl -sS https://simapi.nice-ai.dev/health
```

## 5. 运维命令

| 操作 | 命令 |
|------|------|
| 查看 API 日志 | `journalctl -u ss-biomass-api -f` |
| 重启 API | `sudo systemctl restart ss-biomass-api` |
| 重载 Nginx | `sudo nginx -t && sudo systemctl reload nginx` |
| 更新代码后 | `cd /opt/ss-biomass-pfd && git pull && bash deploy/deploy.sh` |
| 本机同步+部署 | `./scripts/sync_vps.sh`（rsync + deploy） |
| 资源巡检 | `bash deploy/vps_health_check.sh` |
| 磁盘清理 | `bash deploy/vps_disk_cleanup.sh`（可加 `--aggressive`） |
| 查看 API Key（勿泄露） | `sudo grep SIM_API_KEY /etc/default/ss-biomass-api` |

健康检查：

```bash
curl -sS https://simapi.nice-ai.dev/health
# 带鉴权的 POST 示例（将 KEY 换为 /etc/default 中的值）
curl -sS -X POST https://simapi.nice-ai.dev/v1/compute/simulate-lite \
  -H 'Content-Type: application/json' -H 'X-API-Key: KEY' \
  -d '{"case_id":"Case-1","feed_rows":[],"chem_rows":[]}'
```

## 6. Excel / WPS 客户端

- JS 基线：`export/js/WebServiceDemo.js`
- 将 `API_BASE` 改为 `https://simapi.nice-ai.dev`
- 若启用 `SIM_API_KEY`，在请求头加入 `X-API-Key`（见 `doc/excel_api_contract.md`）

## 7. 密钥轮换

1. 在 VPS 生成新 key：`openssl rand -hex 32`
2. 更新 `/etc/default/ss-biomass-api` 中 `SIM_API_KEY`
3. `sudo systemctl restart ss-biomass-api`
4. 同步更新 Excel JS / 联调脚本中的 Header

## 8. 故障排查

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| certbot 失败 | DNS 未指向 VPS | 先 `dig +short simapi.nice-ai.dev` |
| `502 Bad Gateway` | systemd 未启动或 8765 未监听 | `systemctl status ss-biomass-api` |
| CORS 错误 | Origin 不在白名单 | 调整 `SIM_API_ALLOWED_ORIGINS` 后重启 |
| `401` / 403 | API Key 不匹配 | 核对 `X-API-Key` 与 `/etc/default` |
| Excel `Load failed` | 用了 HTTP 或非 HTTPS | 必须用正式 `https://simapi...` |

## 10. Agent 操作约定

Cursor Agent 在本机可通过 `ssh nice-ai-LZ '...'` 执行上述命令；敏感信息仅从 VPS 文件读取，不写入仓库。

## 11. 资源稳态与巡检（2026-05-25 基线）

### 11.1 当前基线（RackNerd 24G / 1G RAM）

| 指标 | 典型值 | 阈值建议 |
|------|--------|----------|
| 磁盘 `/` | ~72%（~6.4G 可用） | ≥85% 告警，≥90% 紧急清理 |
| inode | ~19% | ≥85% 告警 |
| 内存 + swap | RAM ~720 MiB，swap **~860 MiB** | swap 长期 >700 MiB 建议减载或升配 |
| API 本机 latency | ~5 ms | — |
| 公网 health | ~1 s（经 Cloudflare） | >10 s 排查网络/VPS 负载 |

### 11.2 巡检脚本

在 **VPS** 上（代码同步后）：

```bash
cd /opt/ss-biomass-pfd
bash deploy/vps_health_check.sh          # 只读巡检，异常 exit 1
bash deploy/vps_health_check.sh --cleanup  # 巡检 + 磁盘清理
bash deploy/vps_disk_cleanup.sh          # 仅清理（Docker/journal/apt/tmp）
```

从 **本机**：

```bash
ssh nice-ai-LZ 'cd /opt/ss-biomass-pfd && bash deploy/vps_health_check.sh'
```

建议 **每周** cron（VPS root）：`0 4 * * 0 cd /opt/ss-biomass-pfd && bash deploy/vps_health_check.sh --cleanup >> /var/log/ss-biomass-health.log 2>&1`

### 11.3 磁盘占用说明

- **Docker**（~8.5 GB）：6 个运行中容器（chem_portal、searchlight 等），`docker system prune` 无法释放除非停服。
- **`/root`**（~3.5 GB）：含 `.vscode-server`、`.cursor-server`、`gasifier-1d-kinetic/.venv` 等开发残留。
- **可选手动清理**（确认无业务影响后）：
  ```bash
  pip cache purge 2>/dev/null || rm -rf /root/.cache/pip
  # 旧 IDE 远程缓存（会随下次连接重建）
  rm -rf /root/.vscode-server/extensions/.obsolete 2>/dev/null
  ```

### 11.4 SSH 慢 / reset

多因 **内存不足 + 磁盘满** 导致 sshd 无法 spawn shell。处理顺序：

1. `df -h /` — 若 >85%，先 `vps_disk_cleanup.sh`
2. `free -h` — 若 swap 满，重启非必需 Docker 或 `systemctl restart sshd`
3. 通过 RackNerd **VNC 控制台**登录若 SSH 完全不可用

### 11.5 ss-biomass-api 与资源

API 本机占用很小（health ~5 ms）。VPS 瓶颈主要在 **Docker 共存 + 1G 内存**，非 API 进程本身。API 日志：`journalctl -u ss-biomass-api -n 50 --no-pager`。

## 12. 与 TODO / STATUS 的对应关系

- P1 **HTTPS / Nginx / 限流**：§4.4 + `deploy/nginx-simapi.conf.example`
- P1 **鉴权 / CORS**：`/etc/default/ss-biomass-api` + `deploy/env.example`
- P1 **可观测性**：`journalctl` + `doc/api_error_codes.md`
- P2/P3 **VPS 稳态**：§11 + `deploy/vps_health_check.sh`、`deploy/vps_disk_cleanup.sh`
- 项目总览：`../STATUS_REPORT.md`、`../TODO.md`
