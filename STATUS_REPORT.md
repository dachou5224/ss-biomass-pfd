# Status Report - ss-biomass-pfd

## 当前进展（2026-05-29）

### 1) 模型里程碑
- INCI Phase 7A：**已收口**（Case-1 湿基对标完成）。
- RGPOX 阶段性验证：**已完成**（`13fc83e`）。
- 反应区（15PGR-1）CH4 相对误差高但绝对值很小，已标记为 **acceptable**。
- 生物质元素衡算支持 **Model_Input Chemistry 表覆盖**样品分析（`elemental.py` / `backend.py`）。

### 2) 产品主线
- 已停止「全量 VBA 迁移」；主线为 **Excel/WPS 前端 + Python API**。
- 并行保留：**Streamlit DCS UI**（`web_ui.py` / `dcs_theme.py`）、**Gibbs Spike** Excel 工具链（非主路径）。
- Streamlit UI 已完成一轮面向操作员流程的体验收敛：**结果总览前置为首个 Tab、顶部增加运行准备总览、自定义工况不再误报为 warning**。
- React + Vite Web 前端 MVP **已完成 QA 通关**（2026-05-29）：
  - `frontend/` 骨架、API 集成、Vite proxy、VPS 部署配置均已到位
  - 关键 Bug 已修复（见下方 QA 小结）
  - **待办**: 生产服务器需部署 `/v1/compute/simulate-full` 端点（本地 routes.py 已支持，VPS 未同步）

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
- `POST /v1/compute/simulate-lite` ✅ 已部署
- `POST /v1/compute/simulate-full` ⚠️ **未部署到 VPS**（本地 routes.py 已支持，需 `scripts/sync_vps.sh` 推送）
- Excel 适配层：`/v1/demo/*`（兼容）

### 3b) React + Vite 前端 QA 小结（2026-05-29）

| # | 级别 | 描述 | 状态 |
|---|------|------|------|
| ISSUE-001 | 🔴 Critical | IPv6 `[::1]` hostname 不被 `isLocalDevHost` 识别 → 绕过 Vite proxy → CORS 崩溃 | ✅ 已修 `0ef064d` |
| ISSUE-002 | 🟡 Medium | 模板载入失败时 Run 按钮标签无法区分"未载入"与"载入失败" | ✅ 已修 `a5a6c84` |
| ISSUE-003 | 🟡 Medium | 进料区初始无 empty-state 提示，白屏显示 | ✅ 已修 `a5a6c84` |
| ISSUE-004 | 🔵 Low | Header 显示内部 API 路径，非用户信息 | ✅ 已修 `a5a6c84` |
| ISSUE-005 | 🟠 High | 生产 VPS 缺少 `/v1/compute/simulate-full` 端点 → 点击求解报 404 | ⚠️ 待 VPS 部署 |

**模板载入 OK，Case 切换 OK，O2IN 组成校验 OK，Run button 可用。**  
唯一遗留：VPS 需 `sync_vps.sh` + 重启服务以部署 `simulate-full`。

### 4) Excel Spread Simulator 前端
工作簿 Sheet 顺序：**Guide → Model_Input → WebService → Model_Output → PFD**

| 能力 | 实现 |
|------|------|
| 联调脚本 | `export/js/WebServiceDemo.js`（WPS JS + Office JS） |
| 运行日志 | `Output_WS_Log_Table` |
| API 健康灯 | `Output_API_Health_Table`（绿/黄/红） |
| 模板校验 | `validateWorkbookTemplate()` + `workbook_template.py` |
| 无头 E2E | `scripts/excel_ws_cli.py`、`run_excel_headless_e2e.sh` |
| 教程 | Excel：`excel_用户操作手册.md`、`excel_mac_开发联调.md`；WPS：`excel_wps_用户操作手册.md` |

生成工作簿：`python3 scripts/build_simulator_workbook.py --case Case-1 --no-wps`（Mac Excel 开发可跳过 xlsm；`export/*` 不入 Git）

### 5) 自动化测试
- 全量：**96 passed**（含 `test_webservice_demo`、`test_excel_ws_headless`、`test_workbook_template`、`test_gibbs_spike`、`test_web_ui_helpers` 等）
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
**约束**：**当前运行中的 Docker 容器一律不动**（2026-05-25 确认）。  
**建议**：定期 `deploy/vps_health_check.sh`（journal/apt/tmp/pip 缓存）；长期可考虑升配内存；可选清理 `/root/.cache/pip`、旧 IDE server 缓存（见 `doc/VPS_DEPLOYMENT.md` §11）。

---

## 交接重点

1. Excel 联调以 `WebServiceDemo.js` + 最新工作簿为准；API 基址 `https://simapi.nice-ai.dev`。  
2. 联调前运行 `validateWorkbookTemplate()`；失败看 WebService **TEMPLATE/修复** 行。  
3. 无头/CI 用 `excel_ws_cli.py --e2e`；生产 Key 用 `SIM_API_KEY` 环境变量。  
4. VPS 同步：`./scripts/sync_vps.sh`；巡检：`deploy/vps_health_check.sh`。  
5. Streamlit 当前推荐操作顺序：左侧输入 → **运行求解并刷新结果** → 首个 Tab 查看结果总览。  
6. 若要在本机继续做 Safari 自动化审查，需手动开启 Safari Develop 菜单下的 **Allow Remote Automation** 与 **Allow JavaScript from Apple Events**。  
7. 勿扩展 VBA 主路径；勿用 trycloudflare 作生产。

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

见 `TODO.md`：P0/P1/P2 大部分已完成；当前新增 **React + Vite 前端 MVP 收口 / VPS 静态托管落地**。
