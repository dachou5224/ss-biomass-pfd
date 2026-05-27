# Mac Microsoft Excel — 开发联调说明

> 本机仅有 **Mac Excel** 时，按本文在本地验证；邮件分发给用户见 [`excel_用户操作手册.md`](excel_用户操作手册.md)。

## 1. 生成工作簿

```bash
cd /path/to/ss-biomass-pfd
python3 scripts/build_simulator_workbook.py --case Case-1 --no-wps
```

- **`Biomass_PFD_Simulator.xlsx`**：Excel 联调用（当前主线）  
- 加 `--no-wps` 可跳过 WPS xlsm（无 WPS 环境时推荐）

需要同时试 WPS 封装时，去掉 `--no-wps`。

## 2. 本机 Excel 一次性配置

1. 打开 `export/Biomass_PFD_Simulator.xlsx`  
2. **插入 → 加载项 → Script Lab**  
3. **Code** 页粘贴 `export/js/WebServiceDemo.js` 全文  
4. **WebService** 页黄格填 `SIM_API_KEY`（与线上一致）→ 保存  

Script Lab 代码**不会**写入 xlsx；仅存在本机 Excel。换机器需重贴。

## 3. 冒烟（Console）

```javascript
await refreshApiHealthMonitor();
await runWebServiceLiteDemo();
```

**WebService** 运行日志应出现 **DONE**，**Model_Output** KPI 表有数。

## 4. 邮件分发包（给用户）

**不要只发 xlsx。** 建议 zip 内含：

| 文件 | 说明 |
|------|------|
| `Biomass_PFD_Simulator.xlsx` | 工作簿 |
| `WebServiceDemo.js` | 用户粘贴到 Script Lab（首次） |
| `excel_用户操作手册.md` | 用户说明（可转 PDF） |

打包示例：

```bash
python3 scripts/package_excel_mail_zip.py
# 输出 export/Biomass_PFD_Simulator_Excel分发.zip
```

用户侧：**不能**「只收 xlsx 就开箱即用」；首次必须粘贴 js + 填口令。

## 5. 无 Excel 时的自动化

```bash
export SIM_API_KEY='你的密钥'
./scripts/run_excel_headless_e2e.sh
```

见 [`excel_js_local_test.md`](excel_js_local_test.md)。

## 6. 与 WPS 路线关系

| 阶段 | 文件 |
|------|------|
| **当前（Mac Excel 开发）** | `.xlsx` + Script Lab |
| **后续（WPS 用户生产）** | `_WPS.xlsm`，见 [`excel_wps_用户操作手册.md`](excel_wps_用户操作手册.md) |

两套表格结构相同，共用 `WebServiceDemo.js` 与 API。
