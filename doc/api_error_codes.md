# API 错误码与可观测性（v1）

服务在 `src/simulator/api/app.py` 对每个请求输出结构化访问日志：

```
[api] ts=... method=POST path=/v1/compute/simulate-lite status=200 latency_ms=42 request_id=
```

可选请求头 `X-Request-ID` 会原样出现在日志中，便于与 Excel/WPS 客户端 `console.log` 对齐。

## HTTP 状态码

| 状态 | 含义 | 典型原因 |
|------|------|----------|
| 200 | 成功 | 正常 JSON/TSV 响应 |
| 204 | OPTIONS 预检 | CORS preflight |
| 400 | 请求无效 | JSON 解析失败、缺少必填字段 |
| 401 | 未授权 | 已配置 `SIM_API_KEY` 但未提供或错误的 `X-API-Key` |
| 404 | 路径不存在 | URL 拼写错误 |
| 405 | 方法不允许 | 对只支持 POST 的路径使用 GET |
| 413 | 载荷过大 | 超过 Nginx `client_max_body_size`（默认 2m） |
| 429 | 过多请求 | Nginx `limit_req` 触发 |
| 500 | 服务器错误 | 计算异常或未捕获错误 |
| 502/504 | 网关错误 | systemd 未启动或计算超时（Nginx `proxy_read_timeout`） |

## 响应体（JSON 错误）

错误响应尽量为 JSON：

```json
{"error": "unauthorized", "message": "missing or invalid X-API-Key"}
```

客户端（`WebServiceDemo.js`）应检查 `response.ok` 与 `error` 字段，并在单元格或面板展示 `message`。

## 运维查看

```bash
journalctl -u ss-biomass-api -f
sudo tail -f /var/log/nginx/error.log
```

部署与密钥配置见 `doc/VPS_DEPLOYMENT.md`。
