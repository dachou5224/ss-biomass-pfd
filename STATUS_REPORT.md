# Status Report - ss-biomass-pfd

## 当前进展（2026-05-21）

### 1) 模型里程碑
- INCI Phase 7A：**已收口**（Case-1 湿基对标完成）。
- RGPOX 阶段性验证：**已完成并推送**（`13fc83e feat: wrap up RGPOX validation phase`）。
- 反应区（15PGR-1）口径下 CH4 相对误差高但绝对值很小，已标记为 **acceptable**。

### 2) 迁移策略变更（关键）
- 已停止“全量 VBA 迁移”主线。
- 新主线：**Excel/WPS 作为前端 + Python API 计算服务（WebService）**。
- 前端技术栈优先：**WPS JS**，并兼容 **MS Excel Office JS** 联调。

### 3) 已打通的最小链路（JS → API）
- 后端轻量服务：
  - `src/simulator/api/app.py` + `src/simulator/api/routes.py` + `src/simulator/api/schemas.py`
  - `scripts/run_excel_webservice_demo.py`（仅启动薄壳）
  - `src/simulator/webservice_demo.py`
- 已可用接口：
  - `GET /health`
  - `POST /v1/compute/simulate-lite`（纯计算契约，UI 无关）
  - `POST /v1/demo/input-read`
  - `POST /v1/demo/output-pack`
  - `POST /v1/demo/simulate-lite`
  - `POST /v1/demo/output-pack.tsv`
  - `POST /v1/demo/simulate-lite.tsv`
- 前端 JS demo：
  - `export/js/WebServiceDemo.js`
  - 支持 WPS JS / Office JS 双桥接
  - 已加入详细 `console.log` 进度日志
  - 默认调用纯计算端点 `/v1/compute/simulate-lite`，Excel 命名区域映射保留在前端
- 契约与部署资产：
  - `doc/excel_api_contract.md`（v1 契约冻结：纯计算 vs Excel 适配）
  - `deploy/systemd/ss-biomass-api.service`
  - `deploy/nginx-simapi.conf.example`
  - API 运行时加固已接入：可选 `X-API-Key` 校验、CORS 白名单配置、请求结构化日志

### 4) 网络与 HTTPS 实测结论
- Excel JS 对 `http://127.0.0.1` 在容器环境下可能失败（`Load failed`）。
- 通过 HTTPS（cloudflared 临时隧道）已实测打通：
  - 请求成功（HTTP 200）
  - `Output_KPI_Table` 成功回填
  - 控制台到 `DONE`
- 结论：生产部署必须走 **正式 HTTPS 域名**（VPS + Nginx + certbot）。

### 5) 自动化测试状态
- 全量：`76 passed`
- 新增 webservice demo 测试：
  - `tests/test_webservice_demo.py`（5 passed）

### 6) 数据合规策略（必须遵守）
- DBI PDF 与任何提取结构化数据严禁 push 到 Git。
- 当前忽略策略已覆盖：
  - `data/reference/**`
  - `config/dbi_rgpox_inlet.json`
  - `doc/*DBI*.pdf`

---

## 交接重点（给下一位 agent）

1. 优先推进“后端可部署化”，不要再扩展 VBA 主路径。  
2. JS 客户端继续以 `export/js/WebServiceDemo.js` 为基线。  
3. 生产地址应替换为 `https://<正式子域名>`，不要依赖 `trycloudflare`。  
4. 进入公网前必须补齐：鉴权、限流、CORS 白名单、请求日志。  

---

## 运行与联调命令

```bash
cd /Users/liuzhen/AI-projects/ss-biomass-pfd
python3 -m pip install -r requirements.txt
pytest

# 本地 WebService demo
python3 scripts/run_excel_webservice_demo.py --host 127.0.0.1 --port 8765

# 健康检查
curl -sS http://127.0.0.1:8765/health
```
