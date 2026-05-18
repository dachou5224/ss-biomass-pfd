# Status Report - ss-biomass-pfd

## Current Progress
- Frontend保持Excel风格多Sheet（Case/Feed/Specs/Chemistry/Flowsheet/Thermodynamics/Results）。
- 后端已从dummy升级为分阶段可运行模型（固定温度）：
  - 新增元素总账与物种底座：`species.py`、`elemental.py`
  - 新增Hamel风格tar代理分配：`tar_models.py`
  - 新增主组分Gibbs求解：`gibbs.py`（Shomate + SLSQP）
  - 重构流程编排：`backend.py`（INCI/SLAG/RGPOX + minor简化 + case对比RMSD）
  - 扩展契约：`contracts.py`（`ElementBalance`、minor字段）
- UI联动更新：
  - Results页新增 INCI/RGPOX minor species 展示
  - 新增元素守恒检查表（mol/h + 相对误差）
  - Thermo trace 文案更新为显式调用链（含tar allocator/minor分配）
- 依赖更新：`requirements.txt` 增加 `scipy`（Gibbs求解器依赖）。
- 自动化验证：
  - 新增 `tests/test_fixed_temperature_pipeline.py`
  - 覆盖 Case-1/2/3 输出结构与元素守恒边界断言
  - 当前测试状态：`2 passed`
- 文档结构化：
  - 新建 `doc/` 目录，归档参考文档 `生物质气化平衡模型说明文档-20250922.docx`
  - 新增 `doc/algorithm-overview.md`（算法与模块说明）
  - 新增 `doc/python-to-vba-mapping.md`（Python 到 VBA 迁移映射）
  - 新增 `doc/README.md`（文档索引）

## Task TODOs
- [x] Replace heuristic backend path with staged Gibbs-driven pipeline (INCI/SLAG/RGPOX).
- [x] Add elemental ledger + minor species simplified layer + tar surrogate allocator.
- [x] Add UI transparency for minor species and element-balance table.
- [ ] Continue Phase-7 validation calibration: reduce H/O balance residual and improve POX RMSD.
- [ ] Add explicit reaction-constraint and delta-T table editor (Eq.3-15/Table 4 mapping).
- [ ] Add benchmark import/export (CSV/Excel) and RMSD batch report across selected cases.
- [ ] Align thermo parameter source with `../gasifier-model` reusable functions (where applicable).
- [x] Prepare VBA migration map: Python function -> VBA module/procedure signature.

## Run
```bash
cd /Users/liuzhen/AI-projects/ss-biomass-pfd
python3 -m pip install -r requirements.txt
streamlit run app.py
```
