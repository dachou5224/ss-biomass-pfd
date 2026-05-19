# INCI 受限平衡（Restricted Equilibrium）说明

## 1. 背景

INCI 出口 **900℃** 下，全局 Gibbs 最小化默认四种主气体**同时达到平衡**。
实际炉内各反应速率差异大，DBI RGibbs 对**慢反应**采用 **Restricted Equilibrium + Approach Temperature（TA）** 单独处理。

本原型在 Gibbs 主平衡之后，按固定顺序施加 TA 链：

1. **WGS**：`CO + H₂O ↔ CO₂ + H₂`
2. **甲烷化（仅允许逆向修正）**：`CO + 3H₂ ↔ CH₄ + H₂O`

反应温度 `INCI_T_C = 900℃` **不变**；TA 只改变“该反应参照哪一档热力学平衡”以及“趋近该平衡的程度”。

---

## 2. 两个旋钮：ΔT 与 η 各管什么

| 符号 | 名称 | 物理角色 | 类比 |
|------|------|----------|------|
| **ΔT_r** | Approach Temperature | 决定反应 *r* 的**参考平衡温度** \(T_{\mathrm{eff}} = T_{\mathrm{reactor}} + \Delta T_r\)，从而确定**目标平衡常数** \(K_r(T_{\mathrm{eff}})\) | “这条反应按哪一档温度下的平衡来对齐” |
| **η_r** | Equilibrium Approach Eta | 决定从 Gibbs 结果**向该目标平衡移动多少**（0 = 不移动，1 = 完全到达 \(K_r(T_{\mathrm{eff}})\) 约束下的平衡位移） | “有没有时间/速率走到那个平衡” |

对甲烷化，代码中的关系（概念式）为：

\[
n_{\mathrm{CH_4,new}} = n_{\mathrm{CH_4,Gibbs}} + \eta_{\mathrm{Meth}} \cdot \bigl(n_{\mathrm{CH_4,eq}}(T_{\mathrm{eff,Meth}}) - n_{\mathrm{CH_4,Gibbs}}\bigr)
\]

其中仅当 \(n_{\mathrm{CH_4,eq}} < n_{\mathrm{CH_4,Gibbs}}\) 时才执行逆向甲烷化（Restricted Meth 模式）。

---

## 3. η_Meth 与 ΔT_Meth 是否“双重抑制”？

**结论：不是。** 二者正交，作用在不同维度：

| 维度 | ΔT_Meth = +500℃ | η_Meth = 0.65 |
|------|-----------------|---------------|
| 控制对象 | **目标平衡在哪里**（\(T_{\mathrm{eff}} = 1400℃\) 下的甲烷化平衡 → 平衡 CH₄ 更低） | **走多远**（只完成 65% 的位移，未到目标平衡） |
| 若单独使用 ΔT、η=1 | 会一次性把 CH₄ 拉到 \(T_{\mathrm{eff}}\) 对应的平衡值，H₂/CO 联动过大 | — |
| 若单独使用 η、ΔT=0 | 在 900℃ 甲烷化平衡参照下，Gibbs 态往往**无法逆向**（Q≪K），η 几乎无效 | — |
| **组合** | 先确定**物理上合理的受限平衡终点**（高温参照、低 CH₄） | 再表达**动力学未完全达到**该终点 |

因此：

- **ΔT_Meth** 回答：“若甲烷化能平衡，应参照哪一档温度下的平衡？” → 无催化剂、900℃ 慢反应 → 参照更高温（+500℃）下的低-CH₄ 平衡。
- **η_Meth** 回答：“实际有没有走到那个平衡？” → 否，只走到 65%。

这不是两个独立惩罚项相加，而是 RGibbs 标准写法中的 **\(T_{\mathrm{eff}}\) + approach degree** 配对；与 `η ≈ 1 - exp(-Da)`（Damköhler 接近度）含义一致：**ΔT 定热力学参照，η 定动力学接近度**。

**反例（才算双重抑制）**：若同时对 CH₄ 做 (a) 甲烷化 TA 拉低，(b) 额外乘经验系数 `CH4_scale=0.65`，且两者无明确分工——当前实现**没有**这类重复缩放。

---

## 4. WGS：TA 选择依据

### 4.1 物理先验

- WGS **放热**；同等组成下，**较低**参考温度 → \(K_{\mathrm{WGS}}\) 相对有利于 **CO₂ + H₂** 产物侧。
- INCI 900℃ 气相中，WGS 通常**比甲烷化快**，更接近局部平衡；故默认 **η_WGS = 1.0**（全幅度趋近 TA 指定的 WGS 平衡位移）。
- ΔT_WGS 符号：**负值**表示在低于炉温的参考温度下评估 WGS 平衡，用于获得适度 **正向 WGS**（CO + H₂O → CO₂ + H₂）。

### 4.2 偏差信号 → 调节方向

| 观测（相对 DBI） | 含义 | 建议调节 |
|------------------|------|----------|
| CO **偏高**，CO₂ **偏低** | 全局 Gibbs 后 WGS 不足 | **减小** ΔT_WGS（更负，如 −120 → −150）或保持 η_WGS=1 |
| CO **偏低**，CO₂ **偏高** | WGS 过头 | **增大** ΔT_WGS（趋向 0 或略正） |
| H₂、CH₄ 同时被牵动 | WGS 与 H 元素再分配有关 | 小步调 ΔT_WGS，**固定** ΔT_Meth / η_Meth 观察解耦 |

### 4.3 默认值 −120℃ 的选取过程

1. **固定** 900℃ 炉温与 Gibbs 主平衡（不改 `INCI_T_C`）。
2. **固定** 甲烷化侧初值（ΔT_Meth、η_Meth 待定），先扫 ΔT_WGS ∈ {0, −40, −80, −120, −160}。
3. 以 Case-1/2/3 **CO、CO₂ 偏差异号最小** 为准则，−120℃ 使三工况 CO 偏差降至 **±0.6% 以内**，CO₂ **±1% 以内**。
4. η_WGS 保持 1.0：WGS 速率相对甲烷化足够快，不再额外削弱。

**当前默认**：`TA DeltaT WGS (C) = −120`，`WGS Equilibrium Approach Eta = 1.0`。

---

## 5. 甲烷化：TA 选择依据

### 5.1 物理先验

- 甲烷化 **强放热**；**无 INCI 甲烷化催化剂**。
- 900℃ 气相甲烷化速率常数小，停留时间有限 → **不能**假设达到 900℃ 甲烷化平衡。
- 全局 Gibbs 因 C/H/O 耦合，常给出 **偏高 CH₄、偏低 H₂**（相对 DBI 13PGI-1）。
- **正 ΔT_Meth**：在 \(T_{\mathrm{eff}} = T + \Delta T\) 评估 \(K_{\mathrm{Meth}}(T_{\mathrm{eff}})\)；温度越高，平衡 CH₄ 越低 → 允许从 Gibbs 态 **逆向甲烷化**。
- **η_Meth < 1**：不完全到达 \(T_{\mathrm{eff}}\) 下的甲烷化平衡，保留有限速率含义。

### 5.2 偏差信号 → 调节方向

| 观测（相对 DBI） | 含义 | 建议调节 |
|------------------|------|----------|
| CH₄ **偏高**，H₂ **偏低** | 甲烷化相对受限不足 | **增大** ΔT_Meth（+450 → +550）或 **略增** η_Meth |
| CH₄ **偏低**，H₂ **偏高** | 逆向甲烷化过头 | **减小** ΔT_Meth 或 **减小** η_Meth |
| CO、CO₂ 已对齐，仅 CH₄ 差 | 应**只动**甲烷化参数 | **勿**再改 ΔT_WGS |

### 5.3 默认值 +500℃、η=0.65 的选取过程

1. 在 ΔT_WGS = −120℃ 已锁定 CO/CO₂ 的前提下，扫描 ΔT_Meth ∈ {+350…+550}、η_Meth ∈ {0.55…0.75}。
2. **ΔT_Meth** 先定“参照平衡”：+500℃（\(T_{\mathrm{eff}}=1400℃\)）时，Case-1 Gibbs 出口 CH₄ 可从 ~14%（干基主组分）降至逆向平衡附近 ~5% 量级。
3. **η_Meth = 0.65** 在 +500℃ 参照下微调，使三工况 CH₄ 偏差 **< +0.9%** 且 H₂ 不被过拉（Case-1 H₂ 偏差 ≈ +0.1%）。
4. 若 η=1.0、ΔT=+500：CH₄ 过低、H₂/CO 联动过大；若 ΔT=+500、η=0：无甲烷化 TA 效果——说明 **两者必须配合**，但非双重抑制。

**当前默认**：`TA DeltaT Meth (C) = +500`，`Meth Equilibrium Approach Eta = 0.65`。

---

## 6. 组合标定流程（推荐顺序）

```
Gibbs @900℃
    ↓
[Step A] 调 ΔT_WGS（η_WGS=1）→ 对齐 CO / CO₂
    ↓
[Step B] 调 ΔT_Meth → 确定甲烷化参照平衡，使 CH₄ 量级接近 DBI
    ↓
[Step C] 调 η_Meth → 微调 CH₄ 与 H₂，避免过调
    ↓
微量组分（H₂S/COS/NH₃/N₂）由生物质元素平衡分配，不参与 TA
```

**禁止做法**：仅扫 ΔT_Meth / η_Meth 同时拟合 CO、CO₂、CH₄、H₂——会把 WGS 该承担的分量误塞给甲烷化。

---

## 7. 收口默认（Case-1，η=1，纯 TA）

对标：**湿基** 13PGI-1（`data/reference/inci_streams.csv`）。

| 指标 | 值 |
|------|-----|
| `TA DeltaT WGS (C)` | **+40** |
| `TA DeltaT Meth (C)` | **+350** |
| `WGS / Meth Equilibrium Approach Eta` | **1.0 / 1.0** |
| RMSD 五主+H₂O | **~1.18%** |
| RMSD 全湿基（已建模物种） | **~0.94%** |

主偏差：H₂O −1.6 pp、CO +1.7 pp；H₂ 已对齐。Ox TA 在出口 O₂≈0 时无效。

调参工具：`python3 scripts/tune_inci_ta_wet.py --compare`

---

## 8. 参数速查表

| Chemistry Setup 字段 | 默认（收口） | 主要影响 | 说明 |
|---------------------|-------------|---------|------|
| `TA DeltaT WGS (C)` | **+40** | CO ↔ CO₂、H₂O | 正 ΔT → 减弱正向 WGS，保留 H₂O |
| `WGS Equilibrium Approach Eta` | **1.0** | WGS 位移幅度 | 收口阶段固定为 1 |
| `TA DeltaT Meth (C)` | **+350** | CH₄ ↔ CO/H₂ | 略低于旧 +500，避免 CH₄ 过低 |
| `Meth Equilibrium Approach Eta` | **1.0** | CH₄/H₂ | 收口阶段固定为 1 |
| `TA DeltaT OxCO/H2/CH4 (C)` | 0 | 残余 O₂ 氧化 | INCI 出口通常无 O₂，暂不调 |

---

## 9. 参考

- DBI Unit 13 INCI RGibbs：Restricted Equilibrium / Table 4（Eq.3–15）
- `doc/algorithm-overview.md`：整体计算流程
- `src/simulator/backend.py`：`_apply_inci_temperature_approach`、`_apply_meth_approach`
- `生物质气化平衡模型说明文档-20250922.docx`：原始工况与对标数据
