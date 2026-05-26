# Status Report - ss-biomass-pfd

## 当前进展（2026-05-25）

### 1) 模型里程碑
- INCI Phase 7A：**已收口**（Case-1 湿基对标完成）。
- RGPOX 阶段性验证：**已完成**（`13fc83e`）。
- 反应区（15PGR-1）CH4 相对误差高但绝对值很小，已标记为 **acceptable**。
- 生物质元素衡算支持 **Model_Input Chemistry 表覆盖**样品分析（`elemental.py` / `backend.py`）。

### 2) 产品主线
- 已停止「全量 VBA 迁移」；主线为 **Excel/WPS 前端 + Python API**。
- 并行保留：**Streamlit DCS UI**（`web_ui.py` / `dcs_theme.py`）、**Gibbs Spike** Excel 工具链（非主路径）。

### 3) 生产 API（P0/P1 完成）
| 项 | 状态 |
|----|------|
| 域名 | `https://simapi.nice-ai.dev`（Cloudflare → VPS `198.23.175.235`） |
| 安装路径 | `/opt/ss-biomass-pfd` |
| 鉴权 | `SIM_API_KEY` + Header `X-API-Key` |
| 部署 | `deploy/deploy.sh`、`scripts/sync_vps.sh` |
| 文档 | `doc/VPS_DEPLOYMENT.md`、`doc/api_error_codes.md`、`doc/excel_api_contract.md` |

接口（纯计算契约）：
- `GET /health`
- `POST /v1/compute/simulate-lite`
- Excel 适配层：`/v1/demo/*`（兼容）

### 4) Excel Spread Simulator 前端
工作簿 Sheet 顺序：**Guide → Model_Input → WebService → Model_Output → PFD**

| 能力 | 实现 |
|------|------|
| 联调脚本 | `export/js/WebServiceDemo.js`（WPS JS + Office JS） |
| 运行日志 | `Output_WS_Log_Table` |
| API 健康灯 | `Output_API_Health_Table`（绿/黄/红） |
| 模板校验 | `validateWorkbookTemplate()` + `workbook_template.py` |
| 无头 E2E | `scripts/excel_ws_cli.py`、`run_excel_headless_e2e.sh` |
| 教程 | `doc/excel_workbook_api_上手教程.md` |

生成工作簿：`python3 scripts/build_simulator_workbook.py --case Case-1`（`export/*.xlsx` 不入 Git）

### 5) 自动化测试
- 全量：**87 passed**（含 `test_webservice_demo`、`test_excel_ws_headless`、`test_workbook_template`、`test_gibbs_spike` 等）
- 联网 E2E：设置 `SIM_API_KEY` 或 `SKIP_NETWORK_TESTS=1` 跳过

### 6) Git / 发布
- 远程：`origin/main` @ `github.com:dachou5224/ss-biomass-pfd`（SSH push）
- 近期主题 commit：API baseline → Excel WebService/健康灯 → VPS 运维 → 模板校验

### 7) 数据合规（必须遵守）
- 严禁 push：`data/reference/**`、`doc/*DBI*.pdf`、`config/dbi_rgpox_inlet.json`
- API Key 仅存 VPS `/etc/default/ss-biomass-api`，勿入 Git

---

## VPS 运行态（2026-05-25 巡检）

| 指标 | 值 | 评价 |
|------|-----|------|
| 磁盘 `/` | **72%**（16G/24G，可用 ~6.4G） | 正常（清理后） |
| inode | 19% | 正常 |
| 内存 | 961 MiB，swap **~860 MiB 在用** | **偏紧** |
| Docker | 6 容器运行中，镜像 ~8.5 GB | 均为在用，无法 prune |
| API 本机 | `127.0.0.1:8765/health` **200**，~5 ms | 正常 |
| 公网 | `https://simapi.nice-ai.dev/health` **200**，~1 s | 正常 |
| 服务 | `sshd` / `nginx` / `docker` / `ss-biomass-api` | 均 active |

**资源风险**：1 GB 内存 VPS 同时跑 6 个 Docker + API，swap 常驻；曾出现 inotify `No space left on device`（磁盘满时）。  
**建议**：定期 `deploy/vps_health_check.sh`；评估下线长期不用容器或升级内存；可选清理 `/root/.cache/pip`、旧 IDE server 缓存（见 `doc/VPS_DEPLOYMENT.md` §11）。

---

## 交接重点

1. Excel 联调以 `WebServiceDemo.js` + 最新工作簿为准；API 基址 `https://simapi.nice-ai.dev`。  
2. 联调前运行 `validateWorkbookTemplate()`；失败看 WebService **TEMPLATE/修复** 行。  
3. 无头/CI 用 `excel_ws_cli.py --e2e`；生产 Key 用 `SIM_API_KEY` 环境变量。  
4. VPS 同步：`./scripts/sync_vps.sh`；巡检：`deploy/vps_health_check.sh`。  
5. 勿扩展 VBA 主路径；勿用 trycloudflare 作生产。

---

## 常用命令

```bash
cd /path/to/ss-biomass-pfd
pytest

# 本地 API
python3 scripts/run_excel_webservice_demo.py --host 127.0.0.1 --port 8765

# Excel 无头 E2E
export SIM_API_KEY=...
python3 scripts/excel_ws_cli.py --e2e

# 生成工作簿
python3 scripts/build_simulator_workbook.py --case Case-1

# VPS 同步 + 部署
./scripts/sync_vps.sh

# 公网健康
curl -sS https://simapi.nice-ai.dev/health
```

## 待办（摘要）

见 `TODO.md`：P0/P1/P2 大部分已完成；剩余 **接口版本策略（/v2）** 与持续合规提醒。
