# Frontend (React + Vite)

这是 Streamlit Web UI 的迁移起点：前端用 React + Vite，后端继续复用仓库里的 Python 纯计算服务。

## 运行

```bash
cd frontend
npm install
npm run dev
```

开发时浏览器始终请求同源 `/api/*`，Vite 再把它代理到后端。默认代理到 `http://127.0.0.1:8765/*`，因此本地可先启动：

```bash
python3 scripts/run_excel_webservice_demo.py --host 127.0.0.1 --port 8765
```

## 构建

```bash
npm run build
```

产物输出到 `frontend/dist/`，适合直接由 Nginx 托管。

## 环境变量

- `VITE_API_BASE_URL`：浏览器侧 API 前缀，默认 `/api`
- `VITE_API_PROXY_TARGET`：开发态 Vite 代理目标；可填本地 API，也可填 `https://simapi.nice-ai.dev`
- `VITE_API_KEY`：可选；若线上启用了 `SIM_API_KEY`，前端可通过此变量注入 `X-API-Key`

### 本地直连 VPS API（推荐）

如果你不想本地再启动 Python API，只需在 `frontend/.env.local` 里写：

```bash
VITE_API_BASE_URL=/api
VITE_API_PROXY_TARGET=https://simapi.nice-ai.dev
VITE_API_KEY=你的 key
```

然后重启 `npm run dev`。这样浏览器仍然访问本地 `127.0.0.1:5173/api/...`，由 Vite 转发到 VPS，避免跨域和 `Failed to fetch`。
