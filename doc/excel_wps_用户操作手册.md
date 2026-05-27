# WPS 表格在线计算 — 用户操作手册

> 分发 **`Biomass_PFD_Simulator_WPS.xlsm`**（内嵌 JS 宏，无需另要 `WebServiceDemo.js`）。  
> **仅 WPS 表格桌面版**；**不要用 Microsoft Excel 打开**。

操作步骤与 Excel 版相同（改表 → 运行命令 → 看 KPI），区别仅在于：

| 项目 | WPS |
|------|-----|
| 打开 | `Biomass_PFD_Simulator_WPS.xlsm` |
| 首次 | 启用宏；**不要**新建 JS 宏 |
| 运行 | **开发工具 → JS 宏 → 控制台**（不是 Script Lab） |
| 命令表 | 仍在 **WebService** 工作表 |

构建：`python3 scripts/build_simulator_workbook.py --case Case-1`（默认同时生成 xlsm）。

若宏未加载，见 `export/template/wps_jsa/README.md` 与 `scripts/capture_wps_jsa_template.py`。

当前项目 **本地开发以 Mac Microsoft Excel 为主**时，请先按 [`excel_用户操作手册.md`](excel_用户操作手册.md) 验证；WPS 版在具备 WPS 环境后再验收。
