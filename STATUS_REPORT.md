# Status Report - ss-biomass-pfd

## Current Progress

### 平台与后端
- 前端：Excel 风格多 Sheet（Case / Feed / Specs / Chemistry / Flowsheet / Thermodynamics / Results）。
- 后端分阶段固定温度模型：INCI → SLAG → RGPOX；配置驱动（`config/*.json`）。
- 模块：`species`、`elemental`、`tar_models`、`pyrolysis`、`gibbs`、`thermo_baseline`、`balance_audit`、`reference_streams`、`ta_tuning` 等。

### INCI 阶段（Phase 7A，**已收口**）

**流程**：进料对齐 DBI 边界 → Hamel 热解 → Gibbs 主组分 → 受限平衡 TA（WGS / 甲烷化 / 可选 Ox）→ 生物质 N/S 微量分配 → tar 出口质量闭合。

**对标口径**：
- 主目标：**湿基** CO / H₂ / CO₂ / CH₄ / H₂O（`rmsd_inci_primary_pct`）。
- 参考：`data/reference/inci_streams.csv`（13PGI-1）；HCN/HCl 未建模。

**Case-1 进料（DBI 边界，非烧嘴内部分配）**：Biomass 4000、CO₂IN 757.7、H₂OIN 782.1、O₂IN 1343（全流股，95% O₂）、N₂IN 0、样品 11#。

**调参过程摘要**：

| 阶段 | 动作 | 结果 |
|------|------|------|
| 1 | 进料 / tar / N·S 微量对齐 | NH₃、H₂S、Ar 贴 DBI；N₂ 受无 N₂IN 约束暂搁置 |
| 2 | 发现 WGS TA 过猛（−120°C, η=1） | H₂O 14.6% vs DBI 20.25%；H₂ 偏高 |
| 3 | 对标目标改为湿基五组分 | 以 H₂O 为关键耦合变量 |
| 4 | TA+η 联合扫描 | RMSD_wet ≈ 1.18%，η_WGS=0.6 等 |
| 5 | **收口：η 全为 1，纯 TA** | **WGS +40°C，Meth +350°C**；RMSD_wet **1.18%**，全湿基 **0.94%** |

**Case-1 当前出口湿基 vol%（模型 vs DBI）**：

| 物种 | 模型 | DBI | Δ (pp) |
|------|------|-----|--------|
| H₂ | 26.11 | 26.54 | −0.43 |
| CO | 26.50 | 24.82 | +1.68 |
| CO₂ | 22.43 | 21.50 | +0.93 |
| CH₄ | 5.17 | 4.40 | +0.77 |
| H₂O | 18.67 | 20.25 | −1.58 |
| NH₃ / H₂S / Ar | — | — | < 0.02 pp |
| N₂ | 0.64 | 2.00 | 待 N₂IN / 边界 |

**对标策略（当前）**：**仅 Case-1 对 DBI stream table**（`inci_streams.csv` / 湿基 13PGI-1）；Case-2/3 **搁置**，不参与 INCI 湿基验收，待 PDF 提取进料与出口表后再启用。

**已知剩余差距（不阻塞 INCI 收口）**：H₂O ~1.6 pp、CO ~1.7 pp（WGS 与水平衡权衡）；气相质量 −99 kg/h；DBI total 中 ~294 kg/h 夹带固相未建；Case-2/3 进料与湿基 CSV 未对齐。

**默认化学参数（`config/model_parameters.json`）**：
- `TA DeltaT WGS (C) = +40`，`TA DeltaT Meth (C) = +350`
- `WGS / Meth Equilibrium Approach Eta = 1.0`
- `Biomass N to NH3 Frac = 0.016`，`Biomass S Release Frac = 0.45`

**工具**：`scripts/tune_inci_ta_wet.py`（`--compare` 全湿基打印；网格扫描调 TA）。

### 自动化验证
- 当前：**45 passed**（`pytest`）。
- INCI 相关：`test_inci_*`、`test_ta_wet_tuning`、`test_temperature_approach`、`test_inci_validation_stage` 等。

### 文档与资产
- `doc/`：算法、受限平衡、微量物种、质量审计、DBI 元素审计。
- `doc/core_streams.*`、`doc/core_topology.svg`：物流拓扑（本地，不入 Git）。
- `data/reference/`：PDF 提取 CSV（本地，不入 Git）。

## Task TODOs

- [x] INCI Phase 7A：进料 / tar / 微量 / 湿基 TA 收口（Case-1）。
- [x] 湿基对标指标与 `ta_tuning` / 审计模块。
- [ ] Phase-7B：RGPOX 出口湿基对标（DBI，优先 Case-1）。
- [ ] ~~Case-2/3~~ **搁置**：缺 DBI stream table / 边界进料；不以之为 INCI 验收依据。
- [ ] N₂ 边界（N₂IN 或烧嘴分配口径）。
- [ ] 夹带固相 ~294 kg/h；TA 微调 H₂O 或热解 H₂O 分配。
- [ ] Excel / VBA 迁移与批量 RMSD 报告。

## Run

```bash
cd /Users/liuzhen/AI-projects/ss-biomass-pfd
python3 -m pip install -r requirements.txt
pytest
streamlit run app.py

# INCI 湿基对标一览
python3 scripts/tune_inci_ta_wet.py --compare
```
