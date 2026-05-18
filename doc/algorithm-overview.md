# Biomass Gasification Algorithm Overview

## Scope

当前实现为固定温度模式，包含：

- INCI（RGibbs）
- SLAGTMZ（RGibbs）
- RGPOX（RGibbs）
- tar 经验分配与 minor 组分简化

## Core Data Flow

1. 读取前端表格输入（feed/spec/chem）。
2. 将生物质与各路进料统一为元素摩尔总账（C/H/O/N/S/Ar）。
3. 使用 tar surrogate 模型分配 tar 碳与氢占比。
4. INCI 阶段执行主组分 Gibbs 最小化。
5. SLAG 阶段处理 char/ash 分流与高温平衡。
6. RGPOX 阶段汇总上游气体与补氧后执行 Gibbs 最小化。
7. 基于分配系数计算 H2S/COS 与 NH3（minor 组分）。
8. 输出 dry vol%（major/minor）、单元 trace、元素守恒表、对标 RMSD。

## Module Responsibilities

- `src/simulator/backend.py`: 全流程编排与结果组织。
- `src/simulator/gibbs.py`: 主组分平衡求解（Shomate + SLSQP）。
- `src/simulator/elemental.py`: 生物质样品与元素入口换算。
- `src/simulator/species.py`: 物种分子量/原子计数与元素汇总函数。
- `src/simulator/tar_models.py`: Hamel 风格 tar surrogate 分配。
- `src/simulator/thermo.py`: 热力学调用链展示数据。
- `src/simulator/data.py`: 默认参数与参考工况（Case-1/2/3）。
- `src/simulator/contracts.py`: 前后端数据契约（含 element balance）。

## Current Model Notes

- minor 组分为工程简化，不是完整自由能极值求解。
- 参考工况对比采用 RMSD（major 四组分）。
- 元素守恒表用于快速定位模型闭合性问题（当前重点在 H/O 残差校准）。
