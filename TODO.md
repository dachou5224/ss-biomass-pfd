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

- [ ] **Excel JS 客户端增强**：增加错误提示面板/状态回写单元格（非仅 console）。
- [ ] **命名区域健壮性**：缺失命名区域时提示“如何修复模板”。
- [ ] **接口版本策略**：`/v1` 保持兼容，规划 `/v2` 变更窗口。
- [x] **联调手册**：`doc/excel_workbook_api_上手教程.md`（零基础 Excel + Script Lab）；WPS 见同文档第十二节。

## 风险与注意事项

- [ ] **严禁提交 DBI/PDF 数据**：`data/reference/**`、相关 `config` 本地文件、`doc/*DBI*.pdf` 均不得入库。
- [ ] **临时隧道不可用于生产**：`trycloudflare` 仅本地 demo，正式必须是 `nice-ai.dev` 体系 HTTPS。
- [ ] **避免退回 VBA 主路径**：VBA 仅兼容保留，不再作为主实现路线。

## 当前可用验证清单（已完成）

- [x] `run_excel_webservice_demo.py` 本地服务可用
- [x] `WebServiceDemo.js` 发起请求并回填 `Output_KPI_Table`
- [x] HTTPS 隧道场景联调通过（用于 demo 验证）
- [x] `pytest` 全量通过（76 passed）
