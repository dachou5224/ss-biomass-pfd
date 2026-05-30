# TODO - ss-biomass-pfd（交接版）

## P0（当前迭代必须完成）

- [x] **后端结构重整**：已把 demo 脚本路由迁移到正式 API 包结构（`src/simulator/api/...`），`scripts/run_excel_webservice_demo.py` 仅保留启动薄壳。
- [x] **接口契约冻结**：已固定纯计算契约 `/v1/compute/*`（与 UI 无关），`/v1/demo/*` 作为 Excel 适配层；文档见 `doc/excel_api_contract.md`。
- [x] **前后端边界明确**：已在契约文档明确“后端纯计算、Excel JS 负责命名区域映射”。
- [x] **VPS 生产模板落地**：已新增 `deploy/systemd/ss-biomass-api.service` 与 `deploy/nginx-simapi.conf.example`。

## P1（上线前必须完成）

- [x] **HTTPS 正式部署**：`https://simapi.nice-ai.dev`（Let's Encrypt，经 Cloudflare 代理至 VPS）。
- [x] **VPS 部署脚本与运维文档**：`deploy/deploy.sh`、`deploy/env.example`、`doc/VPS_DEPLOYMENT.md`；线上路径 `/opt/ss-biomass-pfd`。
- [x] **鉴权**：VPS 已生成 `SIM_API_KEY`（`/etc/default/ss-biomass-api`）；轮换见 `doc/VPS_DEPLOYMENT.md` §7。
- [x] **限流/保护**：Nginx `limit_req` / `client_max_body_size 2m` / proxy 超时已启用（HTTP 引导配置）。
- [x] **CORS 收敛**：VPS 已设 `SIM_API_ALLOWED_ORIGINS=https://nice-ai.dev,https://www.nice-ai.dev`。
- [x] **可观测性**：结构化访问日志 + `doc/api_error_codes.md`。

## P2（稳定性与体验）

- [x] **Excel JS 客户端增强**：WebService 页运行日志 + API 健康监控（绿/黄/红）；见 `Output_WS_Log_Table`、`Output_API_Health_Table`。
- [x] **无头 E2E**：`scripts/excel_ws_cli.py`、`run_excel_headless_e2e.sh`、`tests/test_excel_ws_headless.py`。
- [x] **命名区域健壮性**：`validateWorkbookTemplate()` / 联调前检查；缺失时写运行日志「TEMPLATE/修复」与健康灯；见 `workbook_template.py`。
- [x] **联调手册**：`doc/excel_用户操作手册.md`（零基础日常操作）；安装细节见 `excel_workbook_api_上手教程.md`。
- [x] **Streamlit UI 首轮体验优化**：结果总览前置、顶部运行准备总览、自定义工况提示去 warning 化；见 `app.py`、`web_ui.py`、`dcs_theme.py`。
- [x] **React + Vite 前端 MVP 收口**：QA 通关（2026-05-29）；ISSUE-001~005 已修，VPS 已部署 `simulate-full`。
- [x] **冷煤气效率公式修复（2026-05-29）**：移除 `_dry_syngas_lhv_mj_per_kg` 中错误 `/1000.0`；并修正 CGE 基准混用问题，统一改为 **全干基组成 × 干气质量**，避免把 quench 水和湿气总质量误计入化学能。阶段 CGE 分母已统一为**设备入口总化学能**：INCI 按 INCI 边界入口，POX 按 INCI 出口干气 + tar + 入 POX 炭 + RGPOX 直接进料；其中 tar 按经验式估算 LHV 并计入。默认工况现为：INCI≈70.3%，POX 段≈95.2%，总 CGE≈68.5%。VPS 已同步生效。
- [x] **结果区流程对照增强（2026-05-30）**：full API `compositions` 已补齐 `INCI/POX` 结构化 dry/wet 数据；前端结果区已拆成两块，分别展示 `13PGI-1`、`15PGR-1`、`15PGR-2` 对应组成，并嵌入 `frontend/public/core-topology.png` 供用户对照 PFD 物流编号。
- [x] **完整前后端回归（2026-05-30）**：`pytest -q` 聚焦 API 用例、`frontend npm run build`、本地浏览器回归（Case-1、Case-2、移动端）均已完成；本轮额外修复两项 QA 问题：1) 本地 Vite 代理误跟随 `VITE_API_BASE_URL` 指向远端，导致 5174 联调测错后端；2) Case-2 `simulate-full` 比较表含 `NaN`，会打炸前端 JSON 解析。对应提交：`74d4fd0`、`f6010a5`。

## 风险与注意事项

- [ ] **严禁提交 DBI/PDF 数据**：`data/reference/**`、相关 `config` 本地文件、`doc/*DBI*.pdf` 均不得入库。
- [ ] **临时隧道不可用于生产**：`trycloudflare` 仅本地 demo，正式必须是 `nice-ai.dev` 体系 HTTPS。
- [ ] **避免退回 VBA 主路径**：VBA 仅兼容保留，不再作为主实现路线。

## 当前可用验证清单（已完成）

- [x] `run_excel_webservice_demo.py` 本地服务可用
- [x] `WebServiceDemo.js` 发起请求并回填 `Output_KPI_Table`
- [x] HTTPS 隧道场景联调通过（用于 demo 验证）
- [x] `pytest` 全量通过（87 passed）
- [x] `scripts/sync_vps.sh` 本机 → VPS 同步与 deploy
- [x] VPS 资源巡检脚本 `deploy/vps_health_check.sh`（2026-05-25 实测：磁盘 72%、API 正常、内存偏紧）

## P3（运维稳态，持续）

- [x] **Docker 容器**：**全部保持运行，不做停服/prune**（用户确认 2026-05-25）
- [ ] **VPS 内存**：在不动 Docker 前提下，靠 journal/log/缓存清理 + 监控；长期仍建议升配
- [ ] **接口版本策略**：`/v1` 保持兼容，规划 `/v2` 变更窗口
- [ ] **可选**：`/root/.cache/pip`、旧 `.vscode-server` 缓存清理（见 `doc/VPS_DEPLOYMENT.md` §11）
