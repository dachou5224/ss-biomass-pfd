# Excel 在线计算 — 用户操作手册（Microsoft Excel）

> 适用 **Microsoft Excel 桌面版**（含 **Mac**）。  
> 分发包：**`Biomass_PFD_Simulator.xlsx`** + **`WebServiceDemo.js`**（两个都要，脚本不会随 xlsx 自动带走）。

---

## 1. 三张表

| 工作表 | 用途 |
|--------|------|
| **Model_Input** | 改**黄色格子**里的进料和参数 |
| **WebService** | 填口令、看状态灯、看运行日志、复制运行命令 |
| **Model_Output** | 看算完后的 **KPI 结果表** |

**流程**：Model_Input 改数并保存 → Script Lab 运行命令 → WebService 看日志 → Model_Output 看结果。

---

## 2. 第一次使用（约 15 分钟，只做一次）

### 2.1 打开工作簿

双击 **`Biomass_PFD_Simulator.xlsx`**（不要用 WPS 专用 `*_WPS.xlsm`）。

### 2.2 安装 Script Lab（Mac Excel）

1. 菜单 **插入 → 加载项**（Insert → Add-ins）  
2. 搜索 **Script Lab** → **添加**  
3. 功能区出现 **Script Lab** 选项卡即成功  

搜不到：浏览器打开 [Microsoft AppSource - Script Lab](https://appsource.microsoft.com)，或联系 IT 允许 Office 加载项。

### 2.3 粘贴联调脚本（只做一次）

1. 用**记事本**或 VS Code 打开 **`WebServiceDemo.js`**（不要用 Word）  
2. **全选** → **复制**  
3. Excel → **Script Lab** → **Code** 页  
4. 删掉示例代码，**粘贴**整份文件  

脚本保存在本机 Script Lab 里；**换电脑或重装 Office 要再粘贴一次**。

### 2.4 填写访问口令

1. 打开 **WebService**  
2. **「连接与授权」** → **「API 访问密钥」** 黄格粘贴口令 → **保存**（Cmd + S）  

---

## 3. 每次计算

### 步骤 1 — 改输入

**Model_Input** 只改**黄色格** → **保存**。

### 步骤 2 — 运行

1. **WebService** 看 **「API 健康监控」**（建议为**绿**）  
2. **Script Lab → Console**  
3. 从 **「运行命令」** 表**逐条复制**到 Console，按 **Enter**：

| 顺序 | 命令 | 说明 |
|------|------|------|
| ① | `await validateWorkbookTemplate();` | 新工作簿或报错时 |
| ② | `await refreshApiHealthMonitor();` | 刷新状态灯 |
| ③ | `await runWebServiceHealthCheck();` | 可选 |
| ④ | `await runWebServiceLiteDemo();` | **正式计算（必跑）** |

4. 回到 **WebService** 看 **「运行日志」** 是否 **DONE**

**熟练后**：② → ④。

### 步骤 3 — 看结果

**Model_Output** → **「关键物流与对标误差」** 表。  
**NEGATIVE_FEED_COUNT** 应为 **0**；改大进料后再跑 ④，**TOTAL_FEED_KG_H** 应变大。

---

## 4. 状态灯与日志

| 灯色 | 建议 |
|------|------|
| **绿** | 可运行 ④ |
| **黄** | 查口令 |
| **红** | 查网络 / VPN |
| **灰** | 先运行 ② |

---

## 5. 常见问题（Excel）

| 现象 | 处理 |
|------|------|
| 提示找不到 `runWebServiceLiteDemo` | Script Lab **Code** 是否已粘贴完整 `WebServiceDemo.js` |
| `Load failed` / 网络错误 | 检查能否访问外网；公司代理可能拦截 |
| 日志缺少口令 | WebService 黄格填口令并保存 |
| 有 DONE 但 Output 没数 | 确认看 **「关键物流与对标误差」** 表 |
| 只发了 xlsx、没发 js | 向管理员索取 **WebServiceDemo.js** 并粘贴到 Script Lab |

---

## 6. WPS 用户

请改用 **`Biomass_PFD_Simulator_WPS.xlsm`**，说明见 [`excel_wps_用户操作手册.md`](excel_wps_用户操作手册.md)。**不要用 Excel 打开 WPS 版 xlsm。**

---

## 7. 每日清单

```
□ Biomass_PFD_Simulator.xlsx 已打开，Script Lab 已粘贴脚本
□ Model_Input：黄格改好 → 保存
□ WebService：口令已填
□ Script Lab Console：运行 ④
□ 运行日志 DONE → Model_Output KPI 合理
```
