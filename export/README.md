# Excel / Spread Simulator 前端

面向 **Spread Simulator** 的精简工作簿（非 Streamlit 全量 Tab 镜像）：

| Sheet（标签从左到右） | 用途 |
|---------------------|------|
| **Guide** | 工程首页 · 标准作业流程 · 模块导航 |
| **Model_Input** | 步骤 1：工况、进料、化学参数（黄格可编辑） |
| **WebService** | 步骤 2：联调台 · API Key · 运行日志 · 运行命令 |
| **Model_Output** | 步骤 3：KPI、组成、DBI 对标（只读） |
| **PFD** | 步骤 4：流程图 + 流股卡片 |

- 默认 xlsx：`Biomass_PFD_Simulator.xlsx`（`export/*.xlsx` 不入 Git）
- **Excel 流程图**：`export/assets/流程示意图.png`（PFD 页嵌入，优先于 SVG 自动截图）
- 可选标注 SVG：`export/assets/pfd_<case>.svg`（构建时生成，供开发参考）
- **内部模型常数**：`export/vba/ModelInternals.bas` → 导入 Excel VBE，勿放在前端 Sheet

生成命令：

```bash
python3 scripts/build_simulator_workbook.py
python3 scripts/build_simulator_workbook.py --case Case-1 --no-run
```

Streamlit 侧边栏可下载同一工作簿。

## WPS JS / Office JS WebService 轻量联调 Demo

- JS 脚本：`export/js/WebServiceDemo.js`（默认 `https://simapi.nice-ai.dev`）
- **零基础分步教程（推荐）**：`doc/excel_workbook_api_上手教程.md`
- **进阶 / 无头 CLI**：`doc/excel_js_local_test.md`
- 配置示例（勿提交真实密钥）：`export/js/WebServiceDemo.config.example.js`
- 生产 API：`https://simapi.nice-ai.dev`（`GET /health`；`POST` 需 `X-API-Key`）
- 本地 Python：`python3 scripts/run_excel_webservice_demo.py --host 127.0.0.1 --port 8765`
- 纯计算端点（推荐）：`POST /v1/compute/simulate-lite`（JSON，仅计算结果）
- 输入命名区域：`Input_CaseID` / `Input_Feed_Table` / `Input_Chem_Table` / `Input_API_Key`
- 输出命名区域：`Output_KPI_Table`（Model_Output）、`Output_WS_Log_Table`（WebService 页运行日志，脚本自动填写）

说明：该 demo 仅验证 **Excel 读输入 + 调服务 + 回填输出**，不执行两台反应器 Gibbs 全流程。后端已区分“纯计算契约”和“Excel 适配契约”，避免 UI 布局变更影响计算服务。

## Gibbs 迁移 Spike（方案 B 探针）

- 工作簿：`Gibbs_Spike_Test.xlsx`（`python3 scripts/build_gibbs_spike_workbook.py`）
- VBA：`vba/GibbsSpike.bas` → 导入后另存 `.xlsm`，运行 `RunGibbsSpikeCase1`
- Python 对照：`src/simulator/gibbs_spike.py`（3 维约化 + SLSQP vs 全维 scipy）

## 界面设计

- **流程模拟器风格**：深蓝页眉、蓝色分区条、琥珀色可编辑单元格、灰色只读结果区。
- **Model_Input**：工况 → 操作条件 → 进料 → 化学调参，自上而下分区。
- **Model_Input 显式公式**：温度换算(K)、kg/h→t/h、输入快速核算（SUM/SUMIFS/IF/COUNTIF）。
- **Model_Output**：顶部 KPI 条（物流与 RMSD）+ 组成/对标表。
- **VBA 迁移锚点**：预置命名区域（`Input_*` / `Output_*`）供 VBA 通过 `Range("...")` 直接访问。
- **PFD**：左侧流程图（PNG 可选）+ 右侧流股卡片（四行 PFD 标注）。
- **Guide**：快速导航含工作表超链接。
