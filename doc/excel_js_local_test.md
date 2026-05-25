# Excel / WPS 本地联调（生产 API）

> **第一次用？** 请先读 **[excel_workbook_api_上手教程.md](excel_workbook_api_上手教程.md)**（假设你不会 JS/API，从生成工作簿到 Script Lab 逐步操作）。

生产服务：`https://simapi.nice-ai.dev`（VPS + HTTPS，已验收 `/health`）。

## 0. Agent / Shell 无头测试（无 Excel 进程）

**Microsoft Excel / WPS 没有**可在终端里执行 `WebServiceDemo.js` 的官方 headless CLI。  
推荐用本仓库 CLI，逻辑与 JS 一致（`openpyxl` 读命名区域 + `curl` 调 API）：

```bash
cd ss-biomass-pfd
python3 scripts/build_simulator_workbook.py --case Case-1 --no-run   # 若无 xlsx
python3 scripts/excel_ws_cli.py --health-only
python3 scripts/excel_ws_cli.py --write-back   # 读 xlsx → POST → 写回 Output_KPI_Table
```

| 能力 | Excel 桌面 + JS 宏 | `excel_ws_cli.py` |
|------|-------------------|-------------------|
| 读 `Input_*` 命名区域 | ✅ | ✅ |
| `fetch` 生产 API | ✅ | ✅（curl） |
| 写 `Output_KPI_Table` | ✅ | ✅（`--write-back`） |
| Agent/CI 无人值守 | ❌ | ✅ |

其它方案（了解即可）：LibreOffice `soffice --headless`（**不**跑 Office JS）；Windows 第三方 `excelcli`（.NET，非 Mac 官方）；`pytest` 测 Python 契约（`tests/test_webservice_demo.py`）。

## 1. 准备 API Key

在终端读取（**勿提交到 Git**）：

```bash
ssh nice-ai-LZ 'grep SIM_API_KEY /etc/default/ss-biomass-api'
```

记下 `SIM_API_KEY=` 后的十六进制字符串。

## 2. 工作簿命名区域

与 `export/js/WebServiceDemo.js` 对齐，至少需要：

| 命名区域 | 用途 |
|----------|------|
| `Input_CaseID` | 如 `Case-1` |
| `Input_Feed_Table` | 流股 ID、kg/h、°C、bar |
| `Input_Chem_Table` | O2IN 组分 mol% 等 |
| `Input_API_Key` | 生产 API Key（单行单元格） |
| `Output_KPI_Table` | 回填 metric / value / unit |

可用 `python3 scripts/build_simulator_workbook.py` 生成带 `Input_*` / `Output_*` 的 xlsx，再手动增加 `Input_API_Key` 单元格并定义同名命名区域。

## 3. WPS 表格（JSA）

1. 打开工作簿，确认上述命名区域存在且 `Input_API_Key` 已填密钥。
2. **开发工具 → JS 宏**，粘贴 `export/js/WebServiceDemo.js` 全文（或从仓库加载）。
3. 在宏编辑器控制台先测连通性：

   ```javascript
   await runWebServiceHealthCheck();
   ```

   应看到 `status: ok`。

4. 再跑完整联调：

   ```javascript
   await runWebServiceLiteDemo();
   ```

5. 查看 **控制台** `[WebServiceDemo]` 日志；`Output_KPI_Table` 应出现 `TOTAL_FEED_KG_H` 等 KPI。

若不想用命名区域存密钥，可在运行前执行：

```javascript
window.DEMO_API_KEY = "你的密钥";
await runWebServiceLiteDemo();
```

## 4. Microsoft Excel（Office Scripts / Script Lab）

1. 打开 [Script Lab](https://aka.ms/scriptlab) 或工作簿内 Office Scripts。
2. 粘贴 `WebServiceDemo.js`，确保工作簿命名区域与 WPS 相同。
3. 运行 `runWebServiceHealthCheck()`，再运行 `runWebServiceLiteDemo()`。

Office JS 需 **允许访问外部 API**（组织策略可能限制；若 `Load failed` 多为网络/HTTPS 策略问题）。

## 5. 常见错误

| 现象 | 处理 |
|------|------|
| `缺少 API Key` | 填写 `Input_API_Key` 或设置 `window.DEMO_API_KEY` |
| `HTTP 401` | 密钥与 VPS `/etc/default/ss-biomass-api` 不一致 |
| `Load failed` / 网络错误 | 确认使用 `https://simapi.nice-ai.dev`，非 `http://127.0.0.1` |
| 命名区域错误 | 用名称管理器检查 `Input_Feed_Table` 等是否存在 |

## 6. 切回本地 Python 服务

```javascript
window.DEMO_BASE_URL = "http://127.0.0.1:8765";
window.DEMO_API_KEY = "";
await runWebServiceLiteDemo();
```

本地需先启动：`python3 scripts/run_excel_webservice_demo.py --host 127.0.0.1 --port 8765`
