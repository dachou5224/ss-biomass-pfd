# Frontend (React + Vite)

这是 Streamlit Web UI 的迁移起点：前端用 React + Vite，后端继续复用仓库里的 Python 纯计算服务。

## 运行

```bash
cd frontend
npm install
npm run dev
```

开发时默认把 `/api/*` 代理到 `http://127.0.0.1:8765/*`，因此本地需要先启动：

```bash
python3 scripts/run_excel_webservice_demo.py --host 127.0.0.1 --port 8765
```

## 构建

```bash
npm run build
```

产物输出到 `frontend/dist/`，适合直接由 Nginx 托管。

## 环境变量

- `VITE_API_BASE_URL`：默认 `/api`
- `VITE_API_KEY`：可选；若线上启用了 `SIM_API_KEY`，前端可通过此变量注入 `X-API-Key`
