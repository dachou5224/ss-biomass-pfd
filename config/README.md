# 模型参数配置（JSON）

本目录为**可提交 Git** 的模型参数源；与 `data/reference/` 下自 PDF 提取的参考物流 CSV 不同。

## 注释约定

标准 JSON 不支持 `//` 注释。本仓库使用 **`_comment` 键**（及顶层 `_meta`）写说明，由 `src/simulator/parameters.py` 加载时自动剔除，不影响程序读取。

```json
"reactor_specs": {
  "_comment": "反应器温度 (°C)、系统压力 (bar)",
  "INCI_T_C": 900.0
}
```

## 文件说明

| 文件 | 内容 |
|------|------|
| `model_parameters.json` | 反应器、化学设置、Tar/平衡/Gibbs 数值、物种列表、路径等 |
| `reference_cases.json` | Case-1/2/3 进料与对标 expected（POX：`pox_gas_ante_kg_h` 7760 / `pox_gas_kg_h` 8843，Unit 15 PDF p2） |
| `biomass_samples.json` | 8# / 11# 生物质分析 |
| `dbi_inlet.json` | DBI Case-1 边界进料（inlet 对标） |
| `thermo_shomate.json` | Shomate 系数与固体碳近似 |

修改 JSON 后需**重启** Python 进程或 Streamlit 应用。
