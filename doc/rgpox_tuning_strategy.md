# RGPOX 调参策略（Phase 3B 基线重启）

## 1. 为何回退

Phase 4 在 **错误的 15PGR-1 气量目标**（7787 湿基反推 ≈6572 kg/h）下，把模型 ~7283 kg/h 误判为「偏高 +711」，从而选择了 **限 O₂、关后置 char 燃烧** 等 **减气** 手段。

PDF 权威基线（Phase 4F 已对齐）为：

| 流股 | PDF (kg/h) | Phase 3B 基线模型 | Phase 4E  landed |
|------|------------|-------------------|------------------|
| 15PGR-1 湿煤气 | **7760** | **~7701 (−59)** | ~7283 (−477) |
| 15PGR-2 湿煤气 | **8843** | ~8469 (−374) | ~8603 (−241) |
| 15PGR-1 湿基 RMSD | — | **~2.3%** | ~1.6% |

**结论**：组成可在 Phase 4 路径上改善，但气量方向反了。调参应自 Phase 3B 基线重新出发，**双目标**（质量 + 组成）分开扫描，禁止再用湿基反推气量。

## 2. 当前默认配置（Case-1）

`config/model_parameters.json`：

```json
"RGPOX TA DeltaT WGS (C)": -160.0,
"RGPOX TA DeltaT Meth (C)": 0.0,
"rgpox.char_gasification": {
  "o2_to_gibbs_mode": "full_feed",
  "reaction_sequence": "gas_equilibrium_first",
  "post_char_use_remaining_o2": false,
  "enable_boudouard": true,
  "gasification_order": "boudouard_first",
  "hetero_ta": { "enabled": true, "dt_boudouard_c": -100.0, "eta_boudouard": 1.0 }
}
```

- **INCI** 保持 Phase 3A 冻结（WGS/Meth TA、固相边界、N₂ makeup 等），不在此文档改动。
- **对标流股**：组成 → 15PGR-1 湿基 `pox_comp_wet_ante`；质量 → `pox_gas_ante_kg_h=7760`、`pox_gas_kg_h=8843`（Unit 15 PDF p2）。

## 3. 调参维度与优先级

### 第一优先级：进料质量闭合（不改 RGPOX 机理）

| 缺口 | 约值 | 手段 |
|------|------|------|
| 15PGI-1 气相 | −112 kg/h | INCI 侧（已部分用 N₂ makeup）；是否继续补惰性/轻组分需单独决策 |
| 继承到 POX | 同上 | 先接受进料缺口，避免在 POX 用「减气」掩盖 |

### 第二优先级：RGPOX TA（仅改 vol%，不改 kg/h）

- 扫描 `RGPOX TA DeltaT WGS (C)`（Phase 3B 已证 −120°C 较优）
- Meth TA @1400°C 几乎无效，低优先级

### 第三优先级：char / O₂ 路径（**质量–组成 Pareto**）

在 **full_feed** 附近小步扫描，**同时记录** `pox_gas_ante_kg_h` 与 `rmsd_pox_wet_ante_pct`：

| 旋钮 | 增气倾向 | 组成倾向 | 备注 |
|------|----------|----------|------|
| `o2_to_gibbs_mode`: full_feed → char_stoich_co2 | ↓ | CO↓ CO₂↑ | Phase 4 主路径 |
| `o2_to_gibbs_char_mol_ratio` ↑ | ↑/↓ 视后置 | 氧化强度 | 与 full_feed 联用前先单扫 |
| `post_char_use_remaining_o2` | ↑ | 偏氧化 | 仅在 **PDF 7760** 以下仍缺气时考虑 |
| `reaction_sequence`: gas_equilibrium_first | 视 O₂ 分档 | 常改善 RMSD | 与 char_before 对比时 **同时看气量** |
| Boudouard / CO₂ 置换 | ↓ CO₂ / ↑ CO | 还原 | 缺 CO₂ 时再开，会牺牲气量或 CO₂ |

**禁止**：用 `pox_gas_kg_h=7787` 或湿基反推 6572 作为 15PGR-1 目标。

## 4. 推荐工作流

```bash
# 基线分解（质量 + 15PGR-1/2 组成）
python3 scripts/analyze_rgpox_gap.py

# PDF/JSON 气量审计
python3 scripts/audit_dbi_validation_baseline.py --case Case-1

# TA 扫描（组成优先，15PGR-1 湿基 RMSD）
python3 scripts/tune_rgpox_ta_wet.py --case Case-1 --phase wgs --top 15
python3 scripts/tune_rgpox_ta_wet.py --case Case-1 --compare
```

### Phase 5A 结论（Case-1，Phase 3B 基线 + 仅 TA）

在 `full_feed` + `char_before_gibbs` 下 **TA 只改 15PGR-1 湿基 vol%，不改 kg/h**（`pox_gas_ante` 恒 ~7701）。

| 旋钮 | 扫描范围 | 15PGR-1 RMSD | 说明 |
|------|----------|--------------|------|
| **RGPOX WGS TA** | −120…+120°C | **2.042% @ −120°C**（最优） | 更正 → CO↑/CO₂↓ 略好，但 H₂O/H₂ 恶化，总 RMSD 变差 |
| RGPOX Meth TA | −200…+700°C | 2.042%（不变） | 1400°C 下甲烷化 TA 无效应 |
| OxCO / OxH2 TA | ±120°C | 2.042%（不变） | 同上 |
| RGPOX WGS η | 0.70…1.00 | 2.042%（≈不变） | 微调有限 |

**组成（WGS=−120°C，当前默认）** vs DBI `pox_comp_wet_ante`：

| 物种 | Δ pp |
|------|------|
| CO | −2.49 |
| H₂ | −2.19 |
| CO₂ | +2.21 |
| H₂O | +2.24 |
| CH₄ | −0.09 |

**气量（TA 无关，同一基线）**：

| 流股 | 模型 | PDF | Δ |
|------|------|-----|---|
| 15PGR-1 湿煤气 | 7701 | 7760 | **−59** |
| 15PGR-2 湿煤气 | 8584 | 8843 | **−259** |
| pox_ash | 73.31 | 73.33 | ≈0 |

**含义**：TA 阶段已到头；剩余 ~2 pp 对称偏差需 **反应路径/进料**（非 TA）才能再压。气量上 15PGR-1 已接近 PDF（−0.8%），15PGR-2 缺口更大，与急冷加水/进料继承有关，不能靠 TA 修。

### Phase 5B 结论（char 调参，WGS=−120°C 不变）

扫描 `o2_to_gibbs_mode` × `reaction_sequence` × `post_char` × `o2_to_gibbs_char_mol_ratio`（组成 sort_by RMSD）。

**已落地默认**（`config/model_parameters.json`）：

| 项 | 值 |
|----|-----|
| O₂→Gibbs | `char_stoich_co2` |
| 反应顺序 | `gas_equilibrium_first` |
| 后置 O₂ char | `post_char_use_remaining_o2=true` |
| O₂/char-C ratio | **0.82** |
| Boudouard / CO₂ 置换 | 关 |

| 指标 | Phase 3B (full_feed) | **Phase 5B (landed)** | PDF |
|------|---------------------|----------------------|-----|
| 15PGR-1 RMSD | 2.04% | **0.70%** | — |
| 15PGR-1 湿煤气 | 7701 | **7455** | 7760 |
| 15PGR-2 湿煤气 | 8584 | **8483** | 8843 |
| pox_ash | 73.31 | 73.31 | 73.33 |

**组成 Δ pp（15PGR-1）**：CO +0.68，CO₂ −0.95，H₂O +0.76（原 ±2.2 pp 级偏差大幅收窄）。

**气量**：为换组成牺牲 **~246 kg/h** ante（相对 3B），但仍优于 Phase 4E 限 O₂ 路径（−477）。在 **ante≥7600** 约束下 char 无法同时 beat 2.04% RMSD——组成与全量 O₂ 进 Gibbs 不可兼得。

char/O₂ 扫描脚本：`tune_rgpox_ta_wet.py --phase char_o2|char_mass|char_combo`。

`char_gasification`、`gas_equilibrium_first`、限 O₂ 等实现 **不删除**，仅默认配置回退；后续 Pareto 扫描仍可通过 `char_overrides` / `tune_rgpox_ta_wet.py --phase char_*` 调用。

## 6. Phase 6C：middle-way + 联合 TA（η=1.0，只调 ΔT）

### 6.1 默认配置（已落地）

| 项 | 值 |
|----|-----|
| O₂→Gibbs | `full_feed` |
| 反应顺序 | `gas_equilibrium_first` |
| 后置 char O₂ | `post_char_use_remaining_o2=false` |
| char 慢反应 | Boudouard 优先 + steam 补余 |
| `hetero_ta.enabled` | **true** |
| **RGPOX WGS TA** | **−160°C** |
| **Boudouard TA** | **−100°C** |
| char steam TA | 0°C（boud_first 下 char 已被 Boud 路径吃完） |

### 6.2 扫描命令

```bash
# 细网格 WGS×Boud（9 组）
python3 scripts/tune_rgpox_ta_wet.py --case Case-1 --phase combined_ta_fine --min-ante 7680

# 全网格（~300 组）
python3 scripts/tune_rgpox_ta_wet.py --case Case-1 --phase combined_ta --min-ante 7680 --top 20
```

### 6.3 Case-1 结果（ante≥7680）

| 指标 | Phase 3B | **Phase 6C** | Phase 5B |
|------|----------|--------------|----------|
| 15PGR-1 ante | 7701 | **7701** | 7455 |
| RMSD | 2.04% | **2.27%** | 0.70% |
| ΔCO / ΔCO₂ (pp) | −2.5 / +2.2 | **−1.3 / +1.0** | +0.7 / −1.0 |

**含义**：联合 TA 在 **不牺牲气量** 前提下显著收窄 CO–CO₂ 偏差；总 RMSD 仍略高于 3B（H₂/H₂O 未解）。Phase 5B 仍是组成极限参考。

### 6.4 异相 TA 机理注记

full-O₂ Gibbs 后 bulk 气相常 **Q≥K**，char 慢反应在严格平衡下不应正向进行。实现采用混合模式：Q<K 时求平衡幅度；Q≥K 时用 `exp(ΔT/200)` 缩放动力学上限（ΔT=0 恢复全 char 转化，ante≈7701）。

## 7. Phase 6D：char 分流 α + 联合 TA

### 7.1 动机

Phase 6C 在 `boudouard_first` 下 char **全部走 Boudouard**，`dt_char_steam` **无效**；剩余误差集中在 **H₂↓ / H₂O↑**（各 ~3.4 pp）。引入 `char_boud_fraction`（记作 **α**）：

- **α × char** → C+CO₂→2CO（保 CO/CO₂ 与气量）
- **(1−α) × char** → C+H₂O→CO+H₂（补 H₂、耗 H₂O）

### 7.2 扫描命令

```bash
python3 scripts/tune_rgpox_ta_wet.py --case Case-1 --phase combined_ta_phase6d --min-ante 7680 --top 25
```

网格：α∈{0, 0.1, …, 0.3} × WGS × Boud × Steam TA；排序优先满足 Pareto 目标（\|ΔCO\|、\|ΔCO₂\|<1.5 pp，\|ΔH₂\|、\|ΔH₂O\|<2 pp，ante≥7680）。

### 7.3 Case-1 扫描结论（2026-05）

| 方案 | ante | RMSD | \|ΔCO\|+\|ΔCO₂\| | \|ΔH₂\|+\|ΔH₂O\| | 备注 |
|------|------|------|-------------------|-------------------|------|
| **6C（α 未设）** | **7701** | **2.27%** | **2.3 pp** | **6.8 pp** | 默认，CO/CO₂ 最优 |
| 6D 折中 α=0.25 | 7684 | 2.43% | 6.8 pp | **3.6 pp** | WGS−140 Boud−80 |
| 6D 低 α=0.10 | 7676 | 2.79% | 8.4 pp | **2.6 pp** | H₂/H₂O 最佳方向 |

**结论**：在 **ante≥7680** 约束下，**无任何 α+TA 组合**同时满足四主组分 \|Δ\|<2 pp 或 Phase 6D Pareto 目标（164 组有效扫描，0 命中）。char 分流是 **H₂/H₂O ↔ CO/CO₂ 的显式 Pareto 旋钮**：降低 α 改善 H₂/H₂O，但 CO/CO₂ 恶化且 RMSD 上升。**默认配置仍保持 Phase 6C**；需优先 H₂/H₂O 时可试 α≈0.20–0.25 + WGS 略放松（−140～−145°C）+ Boud −80～−90°C。

## 8. 推荐冻结基线（2026-05-31）

**决策**：RGPOX 反应区（15PGR-1）调参 **停在 Phase 6C**，不再推进 TA / char 分流 / Phase 6D 为默认主线。

| 项 | 冻结值 |
|----|--------|
| 阶段代号 | **Phase 6C** |
| O₂→Gibbs | `full_feed` |
| 反应顺序 | `gas_equilibrium_first` |
| char 路径 | `boudouard_first` + `hetero_ta` |
| RGPOX WGS TA | **−160°C** |
| Boudouard TA | **−100°C** |
| char steam TA | 0°C（路径上无效，保留配置位） |
| η（WGS / Meth / hetero） | 全 **1.0** |

**Case-1 冻结指标（对标 PDF 15PGR-1 @1400°C）**：

| 指标 | 模型 | DBI | Δ |
|------|------|-----|---|
| 湿煤气 kg/h | **7701** | 7760 | **−59** |
| RMSD（湿基 vol%） | **2.27%** | — | — |
| ΔCO / ΔCO₂ | −1.3 / +1.0 pp | — | 当前最优折中 |
| ΔH₂ / ΔH₂O | −3.4 / +3.4 pp | — | 已知剩余缺口 |

**下一阶段**：不再扫 RGPOX TA，转 **急冷室 15PGR-2 对标**（见 `doc/quench_benchmark.md`）。15PGR-2 组成 RMSD ~1.2%，**主缺口在湿煤气 kg/h（−376）**；工程判断主因在 **激冷室水平衡 / 气液两相平衡**，而非 INCI 进料传导。
