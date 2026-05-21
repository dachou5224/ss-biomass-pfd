# TODO - ss-biomass-pfd（交接版）

## P0（当前迭代必须完成）

- [x] **后端结构重整**：已把 demo 脚本路由迁移到正式 API 包结构（`src/simulator/api/...`），`scripts/run_excel_webservice_demo.py` 仅保留启动薄壳。
- [x] **接口契约冻结**：已固定纯计算契约 `/v1/compute/*`（与 UI 无关），`/v1/demo/*` 作为 Excel 适配层；文档见 `doc/excel_api_contract.md`。
- [x] **前后端边界明确**：已在契约文档明确“后端纯计算、Excel JS 负责命名区域映射”。
- [x] **VPS 生产模板落地**：已新增 `deploy/systemd/ss-biomass-api.service` 与 `deploy/nginx-simapi.conf.example`。

## P1（上线前必须完成）

- [ ] **HTTPS 正式部署**：子域名（建议 `simapi.nice-ai.dev`）+ Nginx + certbot。
- [ ] **鉴权**：API Key（Header）校验能力已实现，待 VPS 生产环境启用与密钥轮换流程补齐。
- [ ] **限流/保护**：Nginx `limit_req`、请求体大小限制、超时。
- [ ] **CORS 收敛**：白名单配置能力已实现，待生产域名最终确认后收敛并固化。
- [ ] **可观测性**：请求结构化日志已输出，待补齐统一错误码规范文档。

## P2（稳定性与体验）

- [ ] **Excel JS 客户端增强**：增加错误提示面板/状态回写单元格（非仅 console）。
- [ ] **命名区域健壮性**：缺失命名区域时提示“如何修复模板”。
- [ ] **接口版本策略**：`/v1` 保持兼容，规划 `/v2` 变更窗口。
- [ ] **联调手册**：WPS JS 与 MS Excel Script Lab 两套操作手册同步维护。

## 风险与注意事项

- [ ] **严禁提交 DBI/PDF 数据**：`data/reference/**`、相关 `config` 本地文件、`doc/*DBI*.pdf` 均不得入库。
- [ ] **临时隧道不可用于生产**：`trycloudflare` 仅本地 demo，正式必须是 `nice-ai.dev` 体系 HTTPS。
- [ ] **避免退回 VBA 主路径**：VBA 仅兼容保留，不再作为主实现路线。

## 当前可用验证清单（已完成）

- [x] `run_excel_webservice_demo.py` 本地服务可用
- [x] `WebServiceDemo.js` 发起请求并回填 `Output_KPI_Table`
- [x] HTTPS 隧道场景联调通过（用于 demo 验证）
- [x] `pytest` 全量通过（76 passed）
