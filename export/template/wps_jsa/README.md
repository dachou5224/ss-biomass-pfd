# WPS 开箱即用 xlsm 模板

构建脚本会把 `export/js/WebServiceDemo.js` 写入工作簿隐藏表 `__MacroSrc__`，并把固定启动器 `bootstrap.js` 密封为 `xl/JDEData.bin`。

## 若用户打开 xlsm 后宏未加载

在 **WPS 表格** 中：

1. 新建空白表 → **开发工具 → JS 宏** → 输入 `function __probe(){}` → 保存  
2. **另存为** `reference_minimal.xlsm`  
3. 在项目根执行：

```bash
python3 scripts/capture_wps_jsa_template.py /路径/reference_minimal.xlsm
```

4. 重新构建：

```bash
python3 scripts/build_simulator_workbook.py --case Case-1
```

`packaging.json` 中的 `jde_relationship_type` / `jde_content_type` 会更新为与本机 WPS 一致。
