# Python -> VBA Migration Mapping

## Migration Strategy

优先保持“接口和计算顺序一致”，再做语言翻译。  
建议在 Excel 中按模块导入 `.bas/.cls`，不要把全部逻辑放到一个 Module。

## Proposed VBA Modules

| Python Module | VBA Target | Responsibility |
| --- | --- | --- |
| `contracts.py` | `Class SimulationResult`, `Class UnitResult`, `Class ElementBalance` | 结果对象与字段结构 |
| `species.py` | `modSpeciesData.bas` | 物种常量、分子量、原子计数 |
| `elemental.py` | `modElementalFeed.bas` | 生物质到元素摩尔换算 |
| `tar_models.py` | `modTarModel.bas` | tar surrogate 分配 |
| `gibbs.py` | `modGibbsSolver.bas` | 目标函数、约束与优化调用 |
| `backend.py` | `modFlowsheetOrchestrator.bas` | INCI/SLAG/RGPOX 流程编排 |
| `data.py` | `modCaseData.bas` | 默认参数、参考工况 |
| `thermo.py` | `modThermoTrace.bas` | 调用链与参数来源展示 |

## Workbook Sheet Mapping

- Case Manager -> `CaseManager` sheet
- Feed Streams -> `FeedStreams` sheet
- Reactor Specs -> `ReactorSpecs` sheet
- Chemistry Setup -> `ChemistrySetup` sheet
- Thermodynamics -> `Thermo` sheet
- Results & Validation -> `Results` sheet

## Function-Level Migration Priority

1. `biomass_to_elemental_moles`
2. `allocate_tar_moles_from_carbon`
3. `solve_gibbs_major`
4. `run_fixed_temperature_simulation`
5. 结果写回与 trace 生成函数

## VBA Implementation Notes

- 使用统一的单位约定（kg/h、mol/h、K、bar），避免在多个子程序重复换算。
- 物种/元素字典可用 `Scripting.Dictionary` 或二维表结构实现。
- 优化器若不直接使用 Excel Solver，可先落地“受限迭代近似版”，保持接口不变后再替换。
- 建议先迁移 `Case-1` 全链路，再逐步扩展到 Case-2/3 与批量评估。
