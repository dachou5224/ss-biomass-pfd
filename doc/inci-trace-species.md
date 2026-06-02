# INCI 微量气体组分：DBI 对标与模型计算方法

本文档说明 stream **13PGI-1**（INCI 出口粗煤气）全组分表的来源、基准换算，以及 NICE_SIM 原型中微量组分的分配算法。

## 1. DBI 参考数据

### 1.1 来源

| 字段 | 值 |
|------|-----|
| 文档 | `doc/TR5_APPENDIX 02_PFD & Stream Table_Unit 13_INCI Gasifier_DBI.pdf` |
| 页码 | 第 3 页（Process Design Case I） |
| Stream ID | 13PGI-1 |
| 描述 | Raw gas from INCI |
| 温度 | 900 °C |
| 压力 | 1.601 MPa(a) |
| 气相质量流量 | 6580 kg/h |
| 总质量流量 | 6874.3 kg/h |

**说明**：当前 PDF 附录仅包含 **Case-1（Process Design Case I）** 的 13PGI-1 全组分湿基表；Case-2/Case-3 的同类 stream table 尚未收录。

### 1.2 湿基 mol/mol %（DBI 原文）

机器可读副本见 `data/reference/inci_streams.csv`（**自 PDF 提取，不纳入 Git**，见 [`data/reference/README.md`](../data/reference/README.md)）；运行时由 `reference_streams.load_inci_stream_reference()` 加载。

| 组分 | 湿基 mol/mol % |
|------|----------------|
| CO | 24.82 |
| H₂ | 26.54 |
| CO₂ | 21.50 |
| CH₄ | 4.40 |
| H₂O | 20.25 |
| H₂S | 0.01594 |
| COS | 0.00065 |
| N₂ | 2.000 |
| NH₃ | 0.01225 |
| HCN | 0.0001 |
| Ar | 0.45 |

### 1.3 基准换算

#### 湿基 vol%

分母为**全部气相物种**（含 H₂O 与微量气体）的摩尔分数之和：

\[
y_i^{\mathrm{wet}} = \frac{n_i}{\sum_j n_j} \times 100\%
\]

#### 全干气 vol%（含微量）

从湿基换算时，**排除 H₂O**，其余组分按干气总量归一化：

\[
y_i^{\mathrm{dry,full}} = \frac{y_i^{\mathrm{wet}}}{100 - y_{\mathrm{H_2O}}^{\mathrm{wet}}} \times 100\%, \quad i \neq \mathrm{H_2O}
\]

Case-1 换算结果（由 CSV 湿基自动计算 `dry_full_mol_pct`）：

| 组分 | 全干气 mol/mol % |
|------|------------------|
| CO | 31.12 |
| H₂ | 33.28 |
| CO₂ | 26.96 |
| CH₄ | 5.52 |
| H₂S | 0.020 |
| COS | 0.0008 |
| N₂ | 2.51 |
| NH₃ | 0.015 |
| HCN | 0.00013 |
| Ar | 0.56 |

#### 四主组分干基 vol%（历史对标口径）

早期 UI 与 RMSD 仅对比 CO/H₂/CO₂/CH₄ 四组分，分母为**四者之和**（不含 H₂O、不含微量）：

\[
y_i^{\mathrm{dry,4}} = \frac{y_i^{\mathrm{wet}}}{\sum_{k \in \{\mathrm{CO,H_2,CO_2,CH_4}\}} y_k^{\mathrm{wet}}} \times 100\%
\]

`REFERENCE_CASES["Case-1"]["expected"]["inci_comp"]` 仍保留此口径，与 DBI 四组分列一致。

## 2. 模型中微量组分的计算方法

微量气体在 INCI 出口**不参与 Gibbs 平衡**，而是在主组分（Gibbs + TA）求解完成后，按元素守恒与进料惰性气进行**后分配**。实现：`backend._allocate_trace_species_from_biomass()`。

### 2.1 设计原则

1. **硫（S）**：全部来自生物质元素分析，按 configurable split 分配至 H₂S 与 COS。
2. **氮（N）**：生物质中的 N 全部进入气相 NH₃（原型暂未建模 HCN、N₂ 化反应）。
3. **N₂ / Ar**：来自显式 N₂ 进料与 O₂ 杂质，**不由 Gibbs 生成**。
4. 分配时对主组分做**化学计量扣减**（H₂、CO），保持元素平衡。

### 2.2 硫分配：H₂S 与 COS

输入：

- `biomass_s_mol_h`：生物质进料硫元素摩尔流量（mol/h）
- `h2s_split`：H₂S 占总硫的摩尔分率（UI：`H2S/COS split to H2S`，默认 0.8）

计算：

\[
\dot{n}_{\mathrm{H_2S}} = \dot{n}_{\mathrm{S,biomass}} \times f_{\mathrm{H_2S}}
\]

\[
\dot{n}_{\mathrm{COS}} = \dot{n}_{\mathrm{S,biomass}} - \dot{n}_{\mathrm{H_2S}}
\]

化学计量扣减（COS 消耗 CO，H₂S 与 NH₃ 消耗 H₂）：

\[
\dot{n}_{\mathrm{CO}} \leftarrow \dot{n}_{\mathrm{CO}} - \dot{n}_{\mathrm{COS}}
\]

\[
\dot{n}_{\mathrm{H_2}} \leftarrow \dot{n}_{\mathrm{H_2}} - 2\dot{n}_{\mathrm{H_2S}} - \tfrac{3}{2}\dot{n}_{\mathrm{NH_3}}
\]

### 2.3 氮分配：NH₃

\[
\dot{n}_{\mathrm{NH_3}} = \dot{n}_{\mathrm{N,biomass}}
\]

**已知偏差**：DBI Case-1 湿基 NH₃ 仅 ~0.012%，而模型将生物质 N 全部转为 NH₃ 时干基可达 ~0.6% 量级，说明 DBI 中大部分 N 可能进入 HCN、N₂ 或固相，而非全部 NH₃。HCN 在 DBI 表中为 0.0001% 湿基，当前原型**未建模 HCN**。

### 2.4 惰性气：N₂ 与 Ar

`backend._feed_inert_moles()` 汇总 INCI 侧进料：

\[
\dot{n}_{\mathrm{N_2,feed}} = \dot{n}_{\mathrm{N_2IN}} + \dot{n}_{\mathrm{N_2,imp}}
\]

\[
\dot{n}_{\mathrm{Ar,feed}} = \dot{n}_{\mathrm{Ar,imp}}
\]

O₂ 杂质模型（`backend._o2_impurity_moles()`）：设 O₂ 纯度为 \(\phi_{\mathrm{O_2}}\)（vol%），则

\[
\dot{n}_{\mathrm{imp}} = \dot{n}_{\mathrm{O_2}} \left(\frac{1}{\phi_{\mathrm{O_2}}/100} - 1\right)
\]

杂质按 3.25 Ar : 1.75 N₂（mol 比）分配：

\[
\dot{n}_{\mathrm{N_2,imp}} = \dot{n}_{\mathrm{imp}} \times \frac{1.75}{5.0}, \quad
\dot{n}_{\mathrm{Ar,imp}} = \dot{n}_{\mathrm{imp}} \times \frac{3.25}{5.0}
\]

生物质氮中未进入 NH₃ 的部分按 `_split_biomass_n()` 转为 N₂（见 2.3）。

#### Phase 3C：N₂ makeup（DBI 组成闭合）

Case-1 中 DBI 13PGI-1 湿基 N₂ = **2.0%**，而 O₂IN 杂质 + 生物质 N₂ 化合计仅 ~0.65%。该差额在 PFD 进料表（N₂IN=0）中无显式对应，视为 stream table 的**惰性气补齐项**。

`backend._apply_inci_n2_makeup()` 在 trace 分配之后执行：

\[
\Delta n_{\mathrm{N_2}} = \frac{y_{\mathrm{target}} \sum_j n_j - n_{\mathrm{N_2}}}{1 - y_{\mathrm{target}}}
\]

其中 \(y_{\mathrm{target}}\) 为湿基 mol 分率目标，\(\sum_j n_j\) 为 `INCI_WET_SPECIES` 总湿摩尔。

| 参数 | 默认 | 说明 |
|------|------|------|
| `INCI N2 Makeup Mode` | `dbi_reference` | `off` / `target_wet_pct` / `dbi_reference` |
| `INCI N2 Target Wet mol%` | 2.0 | 固定目标或 DBI 缺失时回退 |

审计口径：makeup N₂ 记入虚拟进料 `N2-makeup` 与元素衡算进 N，保持质量闭合约束；**不参与 Gibbs/TA**。

### 2.5 vol% 汇总口径

模型输出三种组成视图（`backend._dry_vol_pct` / `_wet_vol_pct`）：

| 视图 | 物种集合 | 分母 |
|------|----------|------|
| 四主组分干基 | CO, H₂, CO₂, CH₄ | 四者摩尔流量之和 |
| 全干气 | CO, H₂, CO₂, CH₄, H₂S, COS, NH₃, N₂, Ar | 除 H₂O 外全部气相物种 |
| 湿基 | 全干气 + H₂O | 全部气相物种（含 H₂O） |

**注意**：四主组分干基分母**不含**微量气体，因此四组分 vol% 之和为 100%，与全干气/湿基口径不可直接数值对比。

### 2.6 未建模物种

| DBI 物种 | 原型状态 |
|----------|----------|
| HCN | 未建模；全组分 RMSD 计算时排除 |
| HCl | 生物质 Cl 100%→HCl；见 `_split_biomass_cl()` |

## 3. RMSD 对标口径

| 指标 | 对比键 | 说明 |
|------|--------|------|
| `rmsd_inci_pct` | CO, H₂, CO₂, CH₄ | 四主组分干基（历史） |
| `rmsd_inci_wet_pct` | 五组分 + H₂O | 主组分湿基 |
| `rmsd_inci_dry_full_pct` | 全干气（模型已建模物种） | 与 `inci_comp_dry_full` 对比 |
| `rmsd_inci_wet_full_pct` | 全湿基（排除 HCN/HCl） | 与 `inci_comp_wet_full` 对比 |

## 4. 相关代码索引

| 模块 | 职责 |
|------|------|
| `data/reference/inci_streams.csv`（本地，勿 push） | DBI PDF 提取的 INCI 参考物流（湿基 mol/mol） |
| `reference_streams.py` | CSV 加载、湿/干基换算、`REFERENCE_CASES` 注入 |
| `data.py` | 工况进料、`REFERENCE_CASES` 框架 |
| `backend.py` | `_allocate_trace_species_from_biomass()`、`_feed_inert_moles()` |
| `species.py` | `INCI_DRY_SPECIES`、`INCI_WET_SPECIES`、`MINOR_SPECIES` |
