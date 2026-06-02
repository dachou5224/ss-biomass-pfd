# Status Report - ss-biomass-pfd

## 当前进展（2026-05-30）

### 1) 模型里程碑
- INCI Phase 7A：**已收口**（Case-1 湿基对标完成）。
- RGPOX 阶段性验证：**已完成**（`13fc83e`）。
- 反应区（15PGR-1）CH4 相对误差高但绝对值很小，已标记为 **acceptable**。
- 生物质元素衡算支持 **Model_Input Chemistry 表覆盖**样品分析（`elemental.py` / `backend.py`）。

### 2) 产品主线
- 已停止「全量 VBA 迁移」；主线为 **Excel/WPS 前端 + Python API**。
- 并行保留：**Streamlit DCS UI**（`web_ui.py` / `dcs_theme.py`）、**Gibbs Spike** Excel 工具链（非主路径）。
- Streamlit UI 已完成一轮面向操作员流程的体验收敛：**结果总览前置为首个 Tab、顶部增加运行准备总览、自定义工况不再误报为 warning**。
- React + Vite Web 前端 MVP **已完成 QA 通关并上线 full 结果页**（2026-05-30）：
  - `frontend/` 骨架、API 集成、Vite proxy、VPS 部署配置均已到位
  - 关键 Bug 已修复（见下方 QA 小结）
  - 结果区已按 **INCI / POX** 拆块展示 dry/wet 组成、PFD 物流编号，并嵌入 `core-topology.png`
  - 出于数据合规，公网 full 结果页与 `simulate-full` 响应已移除 **DBI 对标数据** 与 **单元追踪/AUDIT**

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
- `POST /v1/compute/simulate-full` ✅ 已部署
- Excel 适配层：`/v1/demo/*`（兼容）

### 3b) React + Vite 前端 QA 小结（2026-05-30）

| # | 级别 | 描述 | 状态 |
|---|------|------|------|
| ISSUE-001 | 🔴 Critical | IPv6 `[::1]` hostname 不被 `isLocalDevHost` 识别 → 绕过 Vite proxy → CORS 崩溃 | ✅ 已修 `0ef064d` |
| ISSUE-002 | 🟡 Medium | 模板载入失败时 Run 按钮标签无法区分"未载入"与"载入失败" | ✅ 已修 `a5a6c84` |
| ISSUE-003 | 🟡 Medium | 进料区初始无 empty-state 提示，白屏显示 | ✅ 已修 `a5a6c84` |
| ISSUE-004 | 🔵 Low | Header 显示内部 API 路径，非用户信息 | ✅ 已修 `a5a6c84` |
| ISSUE-005 | 🟠 High | 生产 VPS 缺少 `/v1/compute/simulate-full` 端点 → 点击求解报 404 | ✅ 已修并部署 |
| ISSUE-006 | 🟠 High | 本地 Vite `/api` 代理错误跟随 `VITE_API_BASE_URL`，导致 5174 联调实际打到远端旧 API | ✅ 已修 `74d4fd0` |
| ISSUE-007 | 🟠 High | `Case-2` 的 `simulate-full` 比较表返回 `NaN`，前端 `response.json()` 解析失败 | ✅ 已修 `f6010a5` |

**完整回归已覆盖：**
- 后端：`pytest -q tests/test_webservice_demo.py tests/test_api_app.py` → **9 passed**
- 前端：`npm run build` 通过
- 浏览器：本地 5174 + 8765 联调下，**Case-1、Case-2、移动端窄屏** 均已手测通过；结果区可按 INCI / POX 对照 PFD 流股查看干湿基组成。
- 碳转化率审计：已修正 **POX 碳转化率** 的展示口径，改为优先按 `15PGI-1` 入口固相边界核算，不再把 INCI `ash_to_pox` 与 RGPOX `pox_ash` 混算。当前 `Case-1` 下 POX 仍显示 `100%`，经审计这是**模型假设结果**而非前端错误：RGPOX 入口固相为 `275.3 kg/h`，其中矿物 `73.312 kg/h`，而 `pox_ash=73.312 kg/h`，等价于残炭为零；根因是默认 `RGPOX_C_CONV=1.0` 且 `use_dbi_boundary_mass=true`。
- INCI 碳转化率审计：已确认 main 口径偏高由两层原因叠加造成：1) 模型内部 `INCI_C_CONV=0.9` 当前只作用于 char pool，使 Case-1 的 **overall biomass carbon conversion** 约为 `97.50%`；2) 结果页/API 仍按 `outlet_gas_C / inlet_total_C`（含 `CO2IN/CIN`）展示，进一步抬高到 `97.77%`。而按 PFD/stream table 边界（`13C-4`、`13LBS-1`、`15PGI-1`）反推，DBI 对应的 INCI carbon conversion 应约为 **`88.35%`**。
- 下一阶段：已在 `exp/inci-overall-carbon-conv` 建立 DBI 全面对齐计划，后续将先修正 INCI 未转化碳去向与 `15PGI-1` 固相耦合，再统一 KPI/API 语义并执行 main/exp/DBI 三方回归。
- Phase 1 已执行：实验分支现已固化第一版 DBI/PFD 边界基线。`src/simulator/reference_streams.py` 新增按 `13C-4` / `13LBS-1` / `15PGI-1` 计算 overall biomass carbon conversion 的 helper，`src/simulator/data.py` 会在本地 DBI 文件可用时将 `dbi_inci_boundary_basis` 挂入 `REFERENCE_CASES[..]["expected"]`；Case-1 当前可直接读到本地基线值，供后续 Phase 2/3 调整时对比。
- Phase 2 / 4 已执行：实验分支已把 INCI 固相边界与 KPI 语义同步切到 DBI/PFD 口径。当前 Case-1：
  - `char_to_pox≈201.988 kg/h`
  - `ash_to_pox≈73.312 kg/h`
  - `inci_slag=122 kg/h`
  - `carbon_conversion_inci_pct=88.3456%`
  上述数值已经与本地 DBI 边界基线一致。
- Phase 3A 已执行：当前按用户要求改为“一个一个来”，先完成 INCI-only 调参，不再与 POX 联合搜索。Case-1 默认 INCI 参数现为：
  - `TA DeltaT WGS (C) = 100`
  - `TA DeltaT Meth (C) = 425`
  - `WGS Equilibrium Approach Eta = 0.85`
  - `Meth Equilibrium Approach Eta = 0.70`
  对应 INCI 拟合评分由旧默认值 `10.8311` 改善到 `7.5401`；当前 INCI 湿基偏差约为：
  - `CO +0.011 vol%`
  - `H2 +0.284 vol%`
  - `CO2 +0.290 vol%`
  - `CH4 -1.177 vol%`
  - `H2O +1.935 vol%`
- Phase 3B 已执行：RGPOX-only TA 扫描确认 `WGS=-120°C` 为当前最优（15PGR-1 RMSD≈1.994%），Ox/Meth TA 在 1400°C 下对组成无实质影响。质量流偏差（`inci_top`≈−576 kg/h）无法仅靠 POX TA 消除，需后续从 INCI 出口总气量继续排查。
- **Phase 4F validation 基线（2026-05-31）**：对照 Unit 15 PDF（`TR5_APPENDIX 04_1` p2）修正 `reference_cases.json`：`pox_gas_ante_kg_h=7760`、`pox_gas_kg_h=8843`；废弃 `7787`/反推 `6571`。
- **POX 调参回 Phase 3B（2026-05-31）**：Phase 4 在错误气量目标下「减气」方向有误；默认已回 `full_feed` + `char_before_gibbs` + WGS −120°C（15PGR-1 湿煤气 ~7701 kg/h，RMSD ~2.3%）。后续策略见 `doc/rgpox_tuning_strategy.md`。
- **Phase 6C 冻结（2026-05-31）**：RGPOX 反应区默认 `gas_equilibrium_first` + WGS −160 + hetero Boud −100；15PGR-1 ante≈7701、RMSD≈2.27%。**TA/char 调参收口**。
- **Phase 7 验收（2026-05-31）**：急冷改为 **T+P→Psat/P 正向**（P_abs=1.5 MPa，T_out=160.384°C）；15PGR-2 **8770 kg/h** vs DBI 8843（Δ−0.8%），湿基 RMSD≈1.86%，**acceptable 冻结**。完整指标见 `doc/pox_dbi_acceptance_baseline.md`。

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

见 `TODO.md`：P0/P1/P2 大部分已完成；当前新增 **结果区流程对照增强 / INCI-POX 分块展示**。
