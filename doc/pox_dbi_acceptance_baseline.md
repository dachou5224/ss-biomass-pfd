# Case-1 POX/DBI 验收基线（2026-05-31）

**状态：acceptable — 冻结为默认配置，不再继续 Phase 6D/7 微调。**

本文件记录 `exp/inci-overall-carbon-conv` 分支在合并 main 前的 Case-1 全链路对标结论。权威 DBI 数字来源：Unit 15 PDF / `config/reference_cases.json` / `data/reference/rgpox_streams.csv`（本地，不入 Git）。

## 1. 冻结配置摘要

| 阶段 | 模块 | 关键参数 |
|------|------|----------|
| INCI | `model_parameters.json` → `inci` | TA WGS −100°C、Meth −425°C；边界 KPI 按 PFD |
| RGPOX 反应区（15PGR-1） | `char_gasification` | `full_feed` + `gas_equilibrium_first` + `boudouard_first`；WGS −160°C、Boud −100°C、hetero η=1 |
| 急冷（15PGR-2） | `quench` | `p_total_mpa_abs=1.5`；`outlet_t_c=160.384`；`outlet_h2o_wet_pct=null`（T+P→Psat/P 正向） |

详见 `doc/rgpox_tuning_strategy.md` §8、`doc/quench_benchmark.md`。

## 2. Case-1 验收指标

| 指标 | 模型 | DBI | Δ | 判定 |
|------|------|-----|---|------|
| 15PGR-1 湿煤气 kg/h | 7701 | 7760 | −59 (−0.8%) | acceptable（Phase 6C 冻结） |
| 15PGR-2 湿煤气 kg/h | **8770** | **8843** | **−73 (−0.8%)** | **acceptable** |
| 急冷加水（表观）kg/h | 1069 | 1083 | −14 | acceptable |
| 15PGR-1 湿基 RMSD | 2.27% | — | — | acceptable |
| 15PGR-2 湿基 RMSD | 1.86% | — | H₂O +2.6 pp | acceptable |
| 15PGR-2 H₂O vol% | 41.66% | 39.033% | +2.6 pp | T+P 饱和结果，acceptable |
| pox_ash kg/h | 73.31 | 73.33 | ≈0 | pass |
| INCI 碳转化率 | 88.35% | ~88.35% | ≈0 | pass |
| POX 碳转化率 | 100% | 无单列 | C_conv=1 假设 | 文档化，非 bug |
| 全厂 CGE（LHV 估算） | ~58.8% | 无单列 | — | 参考值 |

质量闭合：`pox_gas_kg_h = pox_gas_ante_kg_h + quench_h2o_added_kg_h`。

## 3. 机理结论（存档）

1. **Phase 6D char 分流**：在 ante≥7680、CO/CO₂ 优先约束下，联合扫描 0 命中 Pareto；默认停在 Phase 6C。
2. **15PGR-2 气量**：旧默认 `outlet_h2o_wet_pct` 反求 T 时 ΔQ≈+18 MJ/h 未闭合，15PGR-2≈8467 kg/h。改为 **T+P 正向 Psat/P** 后，8770 kg/h，与 DBI 差 −0.8%。
3. **1083 kg/h 表观急冷加水**：DBI 非独立物流，为 8843−7760；与 T≈160.4°C + P=1.5 MPa + ~41.7% y 自洽。
4. **T 差 ~1°C**：模型 T_out=160.384°C vs DBI 流股表 159°C，工程接受，不再单独调 T。

## 4. 回归命令

```bash
pytest tests/test_rgpox_gap_baseline.py tests/test_quench_syngas.py \
  tests/test_inci_conversion.py tests/test_reference_streams.py -q

PYTHONPATH=src python3 scripts/analyze_rgpox_gap.py
PYTHONPATH=src python3 scripts/analyze_quench_balance.py
```

## 5. 后续（非阻塞）

- 可选：将 `quench_delta_q_mj_h` 写入 API 摘要
- 可选：`scripts/analyze_pox_dbi_gap.py` 全景误差报告
- **不做**：为凑 8843 改 Phase 6C TA/char；无 T、P 依据的假加水
