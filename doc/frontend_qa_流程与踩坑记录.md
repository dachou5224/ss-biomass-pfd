# React + Vite 前端 QA 流程与踩坑记录

> 记录于 2026-05-29，基于 gstack `/qa` skill 在 macOS 本地的实战经验。

---

## 工具链架构

```
Copilot Agent
    │
    │  curl --noproxy '*' -X POST /command
    ▼
browse HTTP Server (Bun 运行 src/server.ts, 端口随机)
    │
    │  Playwright API
    ▼
Chromium 无头浏览器
    │
    ▼
http://[::1]:5174  (Vite dev server)
    │
    │  /api/* (Vite proxy)
    ▼
https://simapi.nice-ai.dev  (生产 Python API)
```

### 各工具职责

| 工具 | 职责 |
|------|------|
| `gstack /qa skill` | QA 工作流编排脚本 |
| **bun** | 编译/运行 browse server（Node.js 替代，启动更快） |
| **Playwright Chromium** | 无头浏览器驱动 |
| **browse binary** | 将浏览器操作封装为 HTTP API（`goto`、`snapshot`、`click`、`screenshot`、`console`） |

### Browse 服务状态文件

```
<项目根>/.gstack/browse.json
```

内容示例：
```json
{
  "pid": 38464,
  "port": 46434,
  "token": "cd9197f0-...",
  "startedAt": "2026-05-29T05:30:14.828Z",
  "serverPath": "/Users/.../gstack/browse/src/server.ts"
}
```

每次 `curl` 调用前先读该文件确认 port 和 token。

---

## 一次性安装步骤（首次使用）

```bash
# 1. 安装 bun（GitHub SSL 问题时用 npm 安装）
npm install -g bun

# 2. 在 browse skill 目录安装依赖
cd ~/.agents/skills/gstack/browse
bun install

# 3. 安装 Playwright + Chromium
bun run playwright install chromium

# 4. 编译 browse binary（可选，也可直接运行 server.ts）
bun build src/cli.ts --compile --outfile dist/browse
```

> **注意：** `~/.agents/skills/gstack` 可能是 `~/AI-projects/gstack` 的符号链接，两者同 inode。

---

## 每次 QA 前的启动流程

```bash
# 1. 确认/启动 Vite dev server（使用 5174，避开被 PM2 占用的 5173）
cd /path/to/project/frontend
npm run dev -- --port 5174 --host &

# 2. 启动 browse server（后台运行，detach）
cd ~/.agents/skills/gstack/browse
nohup bun run src/server.ts > /tmp/browse.log 2>&1 &

# 3. 等几秒，读取状态文件获取 port 和 token
sleep 3
cat <项目根>/.gstack/browse.json

# 4. 设置变量
PORT=<port_from_json>
TOKEN=<token_from_json>
```

---

## 常用 Browse API 调用

```bash
BASE="--noproxy '*' -s -X POST http://127.0.0.1:$PORT/command \
  -H 'Authorization: Bearer $TOKEN' \
  -H 'Content-Type: application/json'"

# 导航
curl $BASE -d '{"command":"goto","args":["http://[::1]:5174"]}'

# 截图
curl $BASE -d '{"command":"screenshot","args":["/path/to/out.png"]}'

# 带元素标注的截图（用于定位可点击元素）
curl $BASE -d '{"command":"snapshot","args":["-i","-a","-o","/path/to/annotated.png"]}'

# 点击（@eN 是 snapshot -i 输出的元素编号）
curl $BASE -d '{"command":"click","args":["@e7"]}'

# 查看 console 错误
curl $BASE -d '{"command":"console","args":["--errors"]}'

# 执行 JS
curl $BASE -d '{"command":"js","args":["window.location.hostname"]}'
```

> `snapshot -i` 返回的文本列表即为带 `@eN` 编号的可交互元素，直接用编号点击。

---

## 踩坑记录

### 坑 1：`http_proxy` 环境变量拦截本机请求

**现象：** `curl http://127.0.0.1:PORT` 返回 `000`（连接失败）或请求被代理拒绝。

**原因：** 系统设置了 `http_proxy=http://127.0.0.1:3213`，所有 `curl` 请求都会通过代理，包括 localhost。

**解决：** 所有 `curl` 命令加 `--noproxy '*'`：
```bash
curl --noproxy '*' http://127.0.0.1:46434/...
```

---

### 坑 2：IPv6 下 `window.location.hostname` 含方括号

**现象：** Vite 在 macOS 上以 `host: '0.0.0.0'` 启动时，实际监听在 IPv6 `*:5174`。
访问 `http://[::1]:5174` 时，`window.location.hostname` 返回 `"[::1]"`（含方括号），而非 `"::1"`。

**影响：** `isLocalDevHost()` 未匹配 → 绕过 Vite proxy → 直接调用生产 URL → CORS 报错。

**解决（`frontend/src/api.ts`）：**
```typescript
function isLocalDevHost(hostname: string) {
  // RFC 3986: IPv6 in URLs is wrapped with [], hostname includes brackets
  return hostname === 'localhost'
    || hostname === '127.0.0.1'
    || hostname === '::1'
    || hostname === '[::1]'
}
```

---

### 坑 3：Port 5173 被 PM2 占用

**现象：** Vite 启动到 5173 后，browse 导航到 5173 显示的是另一个项目（Markdown 编辑器）。

**原因：** PM2 管理着名为 `my-editor` 的进程，持续占用 5173；kill 掉后会自动重启。

**解决：** 改用 5174 端口：
```bash
npm run dev -- --port 5174 --host
```

---

### 坑 4：Browse binary CLI 崩溃（"Server crashed twice"）

**现象：** 直接运行 `browse` binary 报 `Server crashed twice in a row — aborting`。

**原因：** Binary 尝试启动内嵌 server，但端口或环境问题导致连接失败；server 进程本身运行正常。

**解决：** 不用 binary，直接手动启动 server：
```bash
bun run ~/.agents/skills/gstack/browse/src/server.ts &
```
然后通过 HTTP API 直接调用（见上方 curl 示例）。

---

### 坑 5：`console --errors` 返回历史错误，无法判断当前页状态

**现象：** 修复 CORS bug 后，`console --errors` 仍返回修复前的旧错误记录。

**原因：** browse server 维护整个 session 的 console 日志，不会因 `goto` 而清空。

**解决：** 用时间戳过滤，或通过 JS 验证当前行为：
```bash
# 检查当前 API base URL 实际是什么
curl $BASE -d '{"command":"js","args":["window.location.hostname"]}'

# 检查 Vite 实际服务的源码（最可靠）
curl --noproxy '*' http://[::1]:5174/src/api.ts | grep isLocalDevHost
```

---

### 坑 6：`about:blank` 导航被 browse 禁止

**现象：** 试图用 `goto about:blank` 来清除 console 历史，收到 `Blocked: scheme "about:" is not allowed`。

**解决：** 改用清空 console 的 JS：
```bash
curl $BASE -d '{"command":"js","args":["console.clear()"]}'
```
或直接通过时间戳判断哪些是新错误。

---

## 生产 API 快速验证

在修 CORS 问题时，可直接 curl 生产 API 验证端点是否已部署：

```bash
API_KEY="your_api_key_here"

# 验证健康
curl --noproxy '*' https://simapi.nice-ai.dev/health

# 验证某端点是否存在（404 = 未部署，200 = 已部署）
curl --noproxy '*' -s -o /dev/null -w "%{http_code}" \
  -X POST https://simapi.nice-ai.dev/v1/compute/simulate-full \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```

---

## 相关文件

| 文件 | 用途 |
|------|------|
| `.gstack/browse.json` | Browse server 运行状态（port、token、pid） |
| `.gstack/qa-reports/` | QA 报告与截图 |
| `frontend/src/api.ts` | API base URL 解析逻辑（含 IPv6 fix） |
| `frontend/vite.config.ts` | Vite proxy 配置 |
| `frontend/.env.local` | 本地 API key（**严禁 commit**） |
