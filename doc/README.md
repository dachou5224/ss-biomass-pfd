# Documentation Index

## Reference Documents

- `生物质气化平衡模型说明文档-20250922.docx`: 原始需求与工况参考文档。

## 模型参数（JSON）

可调参数与默认化学/反应器设置已外置到 [`config/`](../config/)（**可提交 Git**），说明见 [`config/README.md`](../config/README.md)。运行时由 `src/simulator/parameters.py` 加载；`_comment` 键为中文说明，加载时自动忽略。

| 文件 | 内容 |
|------|------|
| `model_parameters.json` | 反应器、化学、Tar、平衡、Gibbs 数值、物种列表等 |
| `reference_cases.json` | Case-1/2/3 进料与对标 expected |
| `biomass_samples.json` | 8# / 11# 工业分析 |
| `dbi_inlet.json` | DBI 边界进料对标 |
| `thermo_shomate.json` | Shomate 热力学系数 |

PDF 提取的参考物流 CSV 仍在 `data/reference/`（**不纳入 Git**）。

## Excel 工作簿（Spread Simulator 前端）

- **零基础用户请先读**：[`excel_用户操作手册.md`](excel_用户操作手册.md)（日常操作、看结果、排错，无需懂 JS/API）。
- `../export/Biomass_PFD_Simulator.xlsx`：由 `python3 scripts/build_simulator_workbook.py` 生成（`export/*.xlsx` 不纳入 Git）。
- 主 Sheet（流程顺序）：**Guide** → **Model_Input** → **WebService** → **Model_Output** → **PFD**。
- 内部常数：`../export/vba/ModelInternals.bas`（导入 VBE，与 `config/model_parameters.json` 同源）。
- Streamlit 侧边栏 **「下载 Excel」** 可导出当前编辑状态与仿真结果。
- 模板校验：`validateWorkbookTemplate()`；规范见 `../src/simulator/workbook_template.py`。
- 模块：`src/simulator/excel_export.py`、`spreadsheet_ui.py`、`pfd_diagram.py`。

## Technical Documents

- `algorithm-overview.md`: 当前 Python 原型的流程与算法说明（INCI/SLAG/RGPOX、Gibbs、tar、minor 组分）。
- `excel_api_contract.md`: Excel JS 联调 API 契约（`/v1/compute/*` 纯计算，`/v1/demo/*` 适配层）。
- **`excel_用户操作手册.md`**: **零基础日常操作**（改表 → WebService 运行 → Model_Output 看 KPI；推荐最终用户）。
- **`excel_workbook_api_上手教程.md`**: 安装 Script Lab、API Key、分步联调（比用户手册更偏安装与排错细节）。
- `excel_js_local_test.md`: 进阶/无头 CLI（`excel_ws_cli.py`）与 WPS 简要说明。
- `VPS_DEPLOYMENT.md`: VPS 运维与 `simapi.nice-ai.dev` 部署（SSH、systemd、Nginx、certbot）。
- `api_error_codes.md`: API HTTP 状态码与 `journalctl` 可观测性约定。
- `restricted-equilibrium-inci.md`: INCI 受限平衡（WGS/甲烷化 TA 与 η）的物理化学依据。
- `inci-trace-species.md`: INCI 出口微量气体（H₂S/COS/NH₃/N₂/Ar）分配算法与 DBI stream 13PGI-1 全组分表说明。
- `../data/reference/README.md`: **PDF 提取参考数据仅本地使用，禁止 push**；生成步骤与文件名列表。
- `../data/reference/inci_streams.csv`（本地）: Case-1 stream 13PGI-1 湿基 mol/mol 全组分。
- `../data/reference/dbi_inci_stream_table_case1.csv`（本地）: Case-1 全流股 stream table；`python3 scripts/extract_dbi_inci_stream_table.py`。
- `inci-mass-balance-audit.md`: INCI 湿基 H2O / 气相质量偏差守恒审计（Case-1）。
- `dbi-inci-element-balance-audit.md`: 自 DBI 全量 stream table 的 INCI 边界 **C/H/O/N/S** 元素衡算（`scripts/audit_dbi_inci_element_balance.py` 生成）。
