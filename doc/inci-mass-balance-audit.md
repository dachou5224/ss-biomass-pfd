# INCI 质量与元素守恒审计（Case-1）

本文档记录 stream **13PGI-1** / **13LBS-1** 质量衡算结论。流程拓扑见 `doc/core_topology.svg`。

## 1. INCI 边界物流（SVG / PFD）

```text
进料 (Mix1 / DECOMP 前)
  13C-4   Biomass + CO2 carrier (757.7 kg/h gas)
  13HS1-1 HP Steam (782.1 kg/h, 100% H2O)
  13OG2-1 O2 stream (1343 kg/h; 95% O2 + 1.75% N2 + 3.25% Ar)

INCI 反应器 13R-101
  └─ SEP2
       ├─ 13PGI-1  顶流 → 粗煤气 → RGPOX
       └─ 13LBS-1  底流 → Unit 14 渣线（部分固相）
            另：char/ash 分路由 → RGPOX（模型内 SEP2 后分支）
```

## 2. 质量闭合（Case-1）

正确闭合口径：**元素进料质量 + 灰分 = 气相 + tar + 底流固相(灰 + char)**

| 项目 | kg/h |
|------|------|
| 进料 stream 加和 | ~6566 |
| 进料 元素 + 灰分 | ~6642 |
| **13PGI-1 气相** | ~6413 |
| **SEP2 底流固相** (灰 + char) | ~230 |
| **反应器出口合计** | ~6642 |
| **闭合相对误差** | **< 0.01%** |

说明：

- `feed_stream` 加和 **低于** `feed_element+ash`，因 Biomass 流股内的灰分 (~183 kg/h) 已计入 4000 kg 进料，但在元素矩阵中单独以 `Ash_kg_h` 跟踪。
- **此前审计仅对比气相 vs DBI，未把 SEP2 底流固相计入出口**，造成“进料 > 气相”的假象（~154 kg/h 差额 ≈ 灰 + char）。

### 13LBS-1 渣流 vs 全底流

| 流股 | 模型 kg/h | DBI | 说明 |
|------|-----------|-----|------|
| 13PGI-1 气相 | ~6413 | gas 6580 | 组成/TA 问题，非守恒丢失 |
| SEP2 底流 (灰+char) | ~230 | — | 全固相离开 INCI |
| **13LBS-1 / inci_slag** | **~122** | **122** | 灰分渣 + 目标残碳；**不含** routed char |
| char → RGPOX | ~21 | — | 45% char_after |
| char → 渣线 | ~25 | — | 55% char_after，未并入 DBI slag 122 |

DBI `inci_slag_kg_h = 122` 与模型 `slag_to_u14`（ash_to_slag + residual_c）一致；**不是** SEP2 全部底流。

DBI `13PGI-1 total_flow = 6874` vs `gas_flow = 6580`：相差 **294 kg/h** = 挥发分 **18.5** + 夹带固相 **275.3**（模型已计入 tar，夹带固相待后续）。

### DBI 边界进料 vs p2 stream table

| 口径 | kg/h | 说明 |
|------|------|------|
| **INCI 边界进料** | 13C-4 4758 + 13HS1-1 782 + 13OG2-1 1343 (+ N2) | `dbi_inci_mass_balance_case1.csv` |
| 模型 feeds 加和 | 6566 | Aspen lump 与 PFD stream 口径不同 |

p2 stream table 还列有 13HS1-2~5、13OG2-2~5、13OGS-1 等，那是 **蒸汽/氧气总管到各烧嘴的内部分配**，不是 INCI 包络上的额外进料；做边界质量衡算时不应计入，也不应与 13HS1-1 / 13OG2-1 加总。

## 3. 元素守恒

INCI 段（气 + tar + char vs 元素进料）：C/H/O/N/S 相对误差均 < 0.1%。灰分为无机固相，不参与 C/H/O 元素矩阵。

## 4. Tar / 挥发分

- DBI：`Tar Yield Factor = 0.01 × C_dry` → Case-1 **18.49 kg/h** 有机挥发分随 13PGI-1 顶流。
- 模型：`tar_outlet_mass_kg_h` 在热解阶段分配，与 `Tar Internal Path`（RGPOX 裂解）**解耦**；默认 tar 计入 SEP2 顶流质量，不进 Gibbs 气相组成。
- 质量闭合：**气相 + tar + 底流固相** ≈ 元素进料 + 灰。

## 5. 代码

| 字段 | 含义 |
|------|------|
| `InciMassAudit.reactor_out_total_kg_h` | 气 + tar + SEP2 底流 |
| `InciMassAudit.pgi_total_kg_h` | 13PGI-1 气相 + tar |
| `InciMassAudit.tar_kg_h` | 挥发分质量 |
| `InciMassAudit.dbi_net_inlet_kg_h` | DBI 边界进料（不含烧嘴内部分配） |
| `InciMassAudit.bottom_solids_kg_h` | 灰 + char |
| `InciMassAudit.slag_to_u14_kg_h` | 13LBS-1 / DBI slag |
| `InciMassAudit.mass_closure_rel_err_pct` | 元素+灰 vs 气+tar+底流 |
| `InciMassAudit.stream_ledger` | PFD stream 台账（含 DBI\| 参考行） |

## 6. 仍未闭合的 DBI 差距（非守恒）

| 差距 | 量级 | 性质 |
|------|------|------|
| 气相 6413 vs DBI 6580 | ~2.5% | 气相组成 / TA / H2O |
| total_flow 6874 vs 模型气+固 6642 | ~3.5% | DBI 多相流股口径 |
| 湿基 H2O 8.3% vs 20.25% | — | TA 消耗 H2O，见 H2O 阶梯 |
