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

## 9. 与 TODO / STATUS 的对应关系

- P1 **HTTPS / Nginx / 限流**：本节 4.4 + `deploy/nginx-simapi.conf.example`
- P1 **鉴权 / CORS**：`/etc/default/ss-biomass-api` + `deploy/env.example`
- P1 **可观测性**：`journalctl` + 结构化访问日志（见 `doc/api_error_codes.md` 错误码约定）

## 10. Agent 操作约定

Cursor Agent 在本机可通过 `ssh nice-ai-LZ '...'` 执行上述命令；敏感信息仅从 VPS 文件读取，不写入仓库。
