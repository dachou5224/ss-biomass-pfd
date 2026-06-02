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
- [x] **公网结果脱敏（2026-05-30）**：前端已移除所有 DBI 对标区块与单元追踪/AUDIT 区块；`simulate-full` full payload 不再返回 `comparison`、`unit_trace` 和 `rmsd_*` 对标派生指标，仅保留公开展示所需结果数据。
- [x] **POX 碳转化率口径审计（2026-05-30）**：已修正前端/接口展示用的 POX 碳转化率计算口径，避免将 INCI `ash_to_pox` 与 RGPOX `15PGI-1` 边界固相混用。Case-1 审计结果显示：当前 POX=100% 不是前端 bug，而是因为 `15PGI-1` 固相按 `275.3 kg/h`、`73.37% C / 26.63% minerals` 进入 RGPOX，且默认 `RGPOX_C_CONV=1.0`，导致 `pox_ash≈minerals`、残炭为零；后续若需更保守数值，应调整 POX 固相边界耦合或 `RGPOX_C_CONV` 建模假设。
- [ ] **exp 分支 DBI 全面对齐方案（2026-05-30）**：在 `exp/inci-overall-carbon-conv` 上分阶段推进：1) 冻结 Case-1 的 PFD/stream table 对齐基线；2) 修正 INCI 未转化碳去向（底渣残碳 + `15PGI-1` 夹带固相碳）；3) 联动校正 POX 入口固相与 dry/wet 结果；4) 将 `carbon_conversion_*` 统一收敛为按 PFD 边界定义的阶段 KPI；5) 跑 main/exp/DBI 三方回归，确认是否值得替换 main 语义。
- [x] **Phase 1 基线冻结（2026-05-30）**：实验分支已补充 DBI/PFD 边界基线 helper。当前 `REFERENCE_CASES["Case-1"]["expected"]` 在本地 DBI 文件存在时会自动挂接 `dbi_inci_boundary_basis`，用 `13C-4`、`13LBS-1`、`15PGI-1` 反推出 INCI overall biomass carbon conversion，作为后续 Phase 2/3 的统一对比基线。
- [x] **Phase 2 固相边界对齐（2026-05-30）**：实验分支已将 INCI 固相路由改为优先服从本地 DBI/PFD 边界基线。Case-1 当前已对齐到 `char_to_pox≈201.988 kg/h`、`ash_to_pox≈73.312 kg/h`、`inci_slag=122 kg/h`，不再依赖固定 `CHAR_TO_SLAG_FRAC / ASH_TO_SLAG_FRAC` 近似分流。
- [x] **Phase 4 KPI 语义切换（2026-05-30）**：`carbon_conversion_inci_pct` 已改为读取 biomass-only 口径，不再以 `outlet_gas_C / inlet_total_C` 作为主路径。Case-1 当前显示值 `88.3456%`，已与 `dbi_inci_boundary_basis` 的 `88.3458%` 一致。
- [x] **Phase 3A INCI-only 调参（2026-05-31）**：按“一个一个来”的策略，仅对 INCI 受限平衡参数做窄网格搜索，并已将默认值更新为 `TA WGS=100°C`、`TA Meth=425°C`、`WGS η=0.85`、`Meth η=0.70`。Case-1 的 INCI 拟合评分由 `10.8311` 改善至 `7.5401`，当前 INCI 湿基主要偏差约为 `CO +0.011`、`H2 +0.284`、`CO2 +0.290`、`CH4 -1.177`、`H2O +1.935 vol%`。
- [x] **Phase 3B POX-only 调参（2026-05-31）**：在 INCI 默认值固定后单独扫描 RGPOX TA/WGS/Meth/Ox*。Case-1 最优为 `RGPOX TA WGS=-120°C`（RMSD 15PGR-1≈1.994%）；Ox/Meth TA 对 1400°C 组成几乎无效应。TA alone 无法收敛 `inci_top_kg_h`（约 −576 kg/h），主因是 Phase 2 DBI 固相边界对齐改变了 RGPOX 进料量。
- [x] **Phase 4F POX validation 基线（2026-05-31）**：Unit 15 PDF 求证后统一 POX 气量口径：`7760`（15PGR-1 湿）、`8843`（15PGR-2 湿）；删除 `7787`/反推 `6571` 混用链。本地提取：`scripts/extract_dbi_rgpox_stream_table.py`；审计：`scripts/audit_dbi_validation_baseline.py`。
- [x] **Phase 4 回退 → POX 调参重启（2026-05-31）**：默认配置恢复 Phase 3B（`full_feed` + `char_before_gibbs` + RGPOX WGS −120°C）；Phase 4 char 试验保留为可选扫描。策略见 `doc/rgpox_tuning_strategy.md`。
- [x] **Phase 5B POX char 调参（2026-05-31）**：TA 冻结 −120°C；char `co2+gas_first+post_O₂ ratio=0.82`，15PGR-1 RMSD 2.04%→**0.70%**，ante 7701→7455（PDF 7760，Δ−305）。
- [x] **Phase 6C 冻结（2026-05-31）**：middle-way + 联合 TA（WGS −160、Boud −100、η=1）；15PGR-1 ante≈7701、RMSD≈2.27%、CO/CO₂ 最优折中。Phase 6D char 分流扫描 0 命中 Pareto，**默认停在 6C**。见 `doc/rgpox_tuning_strategy.md` §8。
- [x] **Phase 7 急冷对标（15PGR-2，2026-05-31）**：T+P→Psat/P 正向；8770 vs 8843 kg/h（−0.8%）、RMSD≈1.86%，**acceptable 冻结**。见 `doc/pox_dbi_acceptance_baseline.md`、`doc/quench_benchmark.md`。

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
