# VBA 模块（Spread Simulator 内部参数）

将 `ModelInternals.bas` 导入 Excel **VBE**（Alt+F11 → 文件 → 导入）。

- **ModelInternals**：固定反应器分配、Tar 分子式、Gibbs/物种/热力学常数等。
- 用户可调项仅出现在工作簿 **Model_Input**（进料、操作温度/压力、化学调参）。

重新生成：`python3 scripts/build_simulator_workbook.py`
