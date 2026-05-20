# Excel / Spread Simulator 前端

面向 **Spread Simulator** 的精简工作簿（非 Streamlit 全量 Tab 镜像）：

| Sheet | 用途 |
|-------|------|
| **Guide** | 目录与使用说明 |
| **PFD** | 工艺流程图（`doc/core_topology.svg` + 流股四行简表） |
| **Model_Input** | 用户可调：工况、进料、操作温度/压力、化学调参 |
| **Model_Output** | 仿真摘要、组成、DBI 对标、质量审计要点 |

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

## 界面设计

- **流程模拟器风格**：深蓝页眉、蓝色分区条、琥珀色可编辑单元格、灰色只读结果区。
- **Model_Input**：工况 → 操作条件 → 进料 → 化学调参，自上而下分区。
- **Model_Output**：顶部 KPI 条（物流与 RMSD）+ 组成/对标表。
- **PFD**：左侧流程图（PNG 可选）+ 右侧流股卡片（四行 PFD 标注）。
- **Guide**：快速导航含工作表超链接。
