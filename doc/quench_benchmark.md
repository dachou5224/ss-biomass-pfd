# Phase 7：急冷室后 15PGR-2 湿煤气对标

RGPOX 反应区（15PGR-1）调参已在 **Phase 6C** 冻结（见 `doc/rgpox_tuning_strategy.md` §8）。本阶段只对 **激冷后出口物流 15PGR-2** 做质量流与组成对标，**不改动** Gibbs/TA/char，**也不把 INCI 进料差值作为 Phase 7 主因**。

## 1. 权威参考（Case-1，Unit 15 PDF）

| 流股 | 含义 | PDF 湿煤气 kg/h |
|------|------|-----------------|
| **15PGR-1** | 反应区 @1400°C，急冷前 | **7760** |
| **15PGR-2** | 急冷室出口湿煤气 | **8843** |
| 急冷加水（表观） | 15PGR-2 − 15PGR-1 | **1083** |

组成参考：`config/reference_cases.json` → `pox_comp_wet`；H₂O **39.033%**（湿基 vol%）。

## 2. 问题定位：15PGR-2 的 T、P 决定气相饱和水

### 2.0 控制方程（Phase 7 建模原则）

**15PGR-2 出口温度 T 与压力 P 决定饱和状态下进入气相的水量**；湿基 H₂O vol% 是 T、P 的结果，不是独立输入。

干气物种 mol/h 在急冷段不变（无反应），则：

\[
y_{\mathrm{H_2O}} = \frac{P_{\mathrm{sat,H_2O}}(T_{15\mathrm{PGR}\text{-}2})}{P_{15\mathrm{PGR}\text{-}2}}
\]

\[
n_{\mathrm{H_2O,gas}} = n_{\mathrm{dry}} \cdot \frac{y_{\mathrm{H_2O}}}{1 - y_{\mathrm{H_2O}}}, \qquad
\Delta n_{\mathrm{H_2O}} = n_{\mathrm{H_2O,gas}} - n_{\mathrm{H_2O,in}}
\]

\[
\dot m_{15\mathrm{PGR}\text{-}2} = \dot m_{\mathrm{dry}} + \dot m_{\mathrm{H_2O,gas}}
\]

DBI 流股表（`data/reference/rgpox_streams.csv`）给出 **15PGR-2：T≈159°C，P=1.601 MPa，8843 kg/h**。

| 边界 | DBI | 说明 |
|------|-----|------|
| T_out | **159°C** | 急冷室出口气相温度 |
| P | **1.601 MPa** | 与 15PGR-1 相同系统压力 |
| y_H2O（表值） | 39.033% | 应对应 T、P 下的饱和（或近饱和）分率 |

**自洽校核**（本项目 `saturation_pressure_water_mpa`）：T=159°C、P=1.601 MPa → **y≈37.73%**；要得到 39.033% 需 **T≈160.4°C**。流股表 T 与 H₂O% 略有偏差。**工程上接受模型 T_out≈160.4°C（与 DBI 159°C 差 ~1°C），不再单独调 T**；继续以 `outlet_h2o_wet_pct` 反求 T 的现有默认即可。

当前默认配置用 `outlet_h2o_wet_pct=39.033` **反求 T**（≈160.4°C），在组成上贴 DBI，但 **不是「T、P 决定饱和水」的正向建模顺序**。Phase 7 应改为：

1. 输入 **T_out、P**（P=1.601 MPa；T 默认仍由 H₂O% 反求 ≈160.4°C，与 DBI 159°C 差 ~1°C **已接受**）；
2. 由 Psat/P 得 **y_H2O** 与 **n_H2O,gas**；
3. 汇总 **15PGR-2 质量流** 与 DBI 8843 kg/h 对标。

水平衡（显热 → 蒸发 + 冷却水）决定 **能否达到该 T_out**，与上式 **联立**；但 **气相水量一旦 T、P 确定，即由气液平衡锁定**。

### 2.1 观测（Phase 6C 基线，2026-05-31）

| 指标 | 模型 | DBI | Δ |
|------|------|-----|---|
| 15PGR-1 | 7701 | 7760 | −59（**冻结，本阶段不追**） |
| 急冷加水 | 766 | 1083 | **−317** |
| **15PGR-2** | **8467** | **8843** | **−376** |
| 15PGR-2 组成 RMSD | 1.25% | — | H₂O 锁定 39.033% |

质量闭合仍成立：`pox_gas_kg_h ≈ pox_gas_ante_kg_h + quench_h2o_added_kg_h`。

### 2.2 质量缺口机理

**15PGR-2 气量缺口（−376 kg/h）在 T、P 饱和框架下主要反映 `n_dry`（15PGR-1 干气摩尔基数）偏小**，而非 INCI 进料需单独回推：

| T_out 来源 | T (°C) | y_H2O | H₂O_add | 15PGR-2 |
|------------|--------|-------|---------|---------|
| DBI 流股表 T | 159 | 37.73% | ~625 | ~8326 |
| 由 39.033% 反求 T（当前默认） | 160.4 | 39.03% | ~766 | ~8467 |
| **DBI 目标** | 159（表） | 39.033%（表） | **~1083** | **8843** |

同一 T、P 下，H₂O 气相量 ∝ **n_dry**。模型 `n_dry` 对应干气质量 ~5843 kg/h，DBI 15PGR-1 干气 **6039 kg/h**；基数差 ~3% 叠加 y 标定方式，表观「急冷加水」差距放大。

### 2.3 水平衡（次要联立方程）

当前默认 `saturation_temperature` 用 **H₂O% 反求 T**（见 §2.0）；诊断脚本还显示 **ΔQ≈+18 MJ/h**（显热未进蒸发/冷却水）。`heat_balance` 模式可闭合 ΔQ，但会解出过高 T 与 y，因未与 **Psat/P 气液平衡** 耦合。

### 2.4 与 15PGR-1 的关系

15PGR-1 湿气量 −59 kg/h 在 Phase 6C 冻结。**Phase 7 不单独修 INCI**；在 **T、P → y → n_H2O,gas** 链条上， ante 侧 **n_dry** 偏小会直接压低 15PGR-2 气相总质量。

## 3. 急冷模型（T + P_abs → Psat/P）

**控制关系**：15PGR-2 出口 **绝压 P=1.5 MPa(a)**（15 bar 表压）、**T≈160.4°C** →  
`y_H2O = P_sat(T)/P_abs` → `n_H2O,gas = n_dry · y/(1−y)`。  
湿基 H₂O% 是结果，**不是**主输入；`outlet_h2o_wet_pct` 仅 DBI 验收参考（39.033%）。

默认配置（`config/model_parameters.json` → `quench`）：

| 参数 | 值 |
|------|-----|
| `p_total_mpa_abs` | **1.5** |
| `outlet_t_c` | **160.384** |
| `outlet_h2o_wet_pct` | **null** |

Case-1 效果（Phase 6C + 新急冷）：15PGR-2 **~8770 kg/h**（DBI 8843，Δ **~−73**），H₂O **~41.66%**（DBI 39.033%）。

## 4. Phase 7 工作包

### P7-A 诊断基线 ✅

- [x] `analyze_rgpox_gap.py`：15PGR-2 质量分解
- [x] `analyze_quench_balance.py`：saturation vs heat_balance vs ΔQ
- [ ] 将 `quench_delta_q_mj_h` 等摘要写入 `SimulationResult` / API（可选）

### P7-B 15PGR-2：P + T（冻结）→ 饱和水 → 质量流（**优先**）

1. **P=1.601 MPa**、**T_out≈160.4°C**（由 39.033% 反求；与 DBI 159°C 差 ~1°C，**不再调**）
2. 由 Psat/P 得 y、n_H2O,gas、15PGR-2 kg/h，对标 **8843 kg/h**
3. 校核 `n_dry` 与水平衡（ΔQ）；**不**为凑质量改 T

### P7-C 水平衡耦合（在 P7-B 之后）

在 P7-B 框架内扫描：`cp_gas`、冷却水流量/入口 T、出口 P、是否 `water_inlet_saturated_liquid` 等。

### P7-D 验收 ✅（2026-05-31 acceptable）

| 指标 | 验收值 | DBI | 判定 |
|------|--------|-----|------|
| 15PGR-2 kg/h | **8770** | 8843 | Δ−73（−0.8%）**acceptable** |
| H₂O vol% | 41.66% | 39.033% | +2.6 pp（T+P 饱和）**acceptable** |
| 15PGR-2 RMSD | **1.86%** | — | ≤2% **acceptable** |
| 急冷加水 | 1069 | 1083 | Δ−14 **acceptable** |

完整存档：`doc/pox_dbi_acceptance_baseline.md`。

## 5. 常用命令

```bash
# 质量 + 组成分解
PYTHONPATH=src python3 scripts/analyze_rgpox_gap.py

# 激冷热平衡 / 气液平衡诊断
PYTHONPATH=src python3 scripts/analyze_quench_balance.py

pytest tests/test_quench_syngas.py tests/test_rgpox_gap_baseline.py -q
```

## 6. 边界

| Phase 7 做 | Phase 7 不做 |
|------------|--------------|
| 改进 `quench.*`：T、P → Psat/P → 气相 H₂O | 以 H₂O% 为主输入、绕过 T+P 平衡 |
| 水平衡与 T_out 联立 | 修改 Phase 6C RGPOX TA/char |
| 新增 15PGR-2 质量流测试 | 无 T、P 依据的「假加水」 |
