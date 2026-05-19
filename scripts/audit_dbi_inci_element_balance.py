#!/usr/bin/env python3
"""DBI stream table：INCI 边界 C/H/O/N/S 元素衡算审计，可生成 Markdown 报告。"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = PROJECT_ROOT / "data" / "reference" / "dbi_inci_stream_table_case1.csv"
DEFAULT_DOC = PROJECT_ROOT / "doc" / "dbi-inci-element-balance-audit.md"

ELEMENTS = ("C", "H", "O", "N", "S")

BOUNDARY_INLET = ("13C-4", "13HS1-1", "13OG2-1")
BOUNDARY_OUTLET_STREAMS = ("13PGI-1", "13LBS-1")

# 气相物种 → 元素原子数（与 species.ATOM_COUNT 一致）
ATOM_COUNT = {
    "CO": {"C": 1, "O": 1},
    "H2": {"H": 2},
    "CO2": {"C": 1, "O": 2},
    "CH4": {"C": 1, "H": 4},
    "H2O": {"H": 2, "O": 1},
    "O2": {"O": 2},
    "N2": {"N": 2},
    "H2S": {"H": 2, "S": 1},
    "COS": {"C": 1, "O": 1, "S": 1},
    "NH3": {"N": 1, "H": 3},
    "HCN": {"H": 1, "C": 1, "N": 1},
}

MW = {
    "CO": 28.010,
    "H2": 2.016,
    "CO2": 44.009,
    "CH4": 16.043,
    "H2O": 18.015,
    "O2": 31.998,
    "N2": 28.014,
    "Ar": 39.948,
    "H2S": 34.081,
    "COS": 60.075,
    "NH3": 17.031,
    "HCN": 27.026,
}

ATOMIC_MASS = {"C": 12.011, "H": 1.008, "O": 15.999, "N": 14.007, "S": 32.06}

# Tar 经验式（与 config chemistry_setup Tar Formula 一致）
TAR_EMPIRICAL = {"C": 1.0, "H": 1.0, "O": 0.082, "N": 0.01}
TAR_MW = sum(TAR_EMPIRICAL[el] * ATOMIC_MASS[el] for el in TAR_EMPIRICAL)


@dataclass
class ElementKgH:
    C: float = 0.0
    H: float = 0.0
    O: float = 0.0
    N: float = 0.0
    S: float = 0.0

    def as_dict(self) -> Dict[str, float]:
        return {el: getattr(self, el) for el in ELEMENTS}

    def __add__(self, other: "ElementKgH") -> "ElementKgH":
        return ElementKgH(
            *(getattr(self, el) + getattr(other, el) for el in ELEMENTS)
        )

    def __sub__(self, other: "ElementKgH") -> "ElementKgH":
        return ElementKgH(
            *(getattr(self, el) - getattr(other, el) for el in ELEMENTS)
        )


@dataclass
class AuditResult:
    inlet: ElementKgH = field(default_factory=ElementKgH)
    outlet_gas: ElementKgH = field(default_factory=ElementKgH)
    outlet_tar: ElementKgH = field(default_factory=ElementKgH)
    outlet_entrained: ElementKgH = field(default_factory=ElementKgH)
    outlet_slag: ElementKgH = field(default_factory=ElementKgH)
    inlet_lines: List[str] = field(default_factory=list)
    outlet_lines: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def outlet_total(self) -> ElementKgH:
        return self.outlet_gas + self.outlet_tar + self.outlet_entrained + self.outlet_slag

    def gap(self) -> ElementKgH:
        return self.inlet - self.outlet_total

    def rel_err_pct(self) -> Dict[str, float]:
        out = {}
        for el in ELEMENTS:
            denom = max(abs(getattr(self.inlet, el)), 1e-9)
            out[el] = getattr(self.gap(), el) / denom * 100.0
        return out


def _parse_pct(value: object) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    s = str(value).strip().replace("%", "")
    if not s:
        return 0.0
    return float(s) / 100.0


def _parse_float(value: object, default: float = 0.0) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    s = str(value).strip()
    if not s:
        return default
    return float(s)


def load_stream_table(csv_path: Path) -> pd.DataFrame:
    if not csv_path.is_file():
        raise FileNotFoundError(f"DBI stream table 不存在: {csv_path}")
    return pd.read_csv(csv_path)


def stream_lookup(df: pd.DataFrame, stream_id: str) -> Dict[Tuple[str, str], str]:
    sub = df.loc[df["stream_id"] == stream_id]
    out: Dict[Tuple[str, str], str] = {}
    for _, row in sub.iterrows():
        val = row["value"]
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue
        out[(str(row["section"]), str(row["property"]))] = str(val).strip()
    return out


def _flow_kg(props: Mapping[Tuple[str, str], str], section: str) -> float:
    for key in ((section, "flow_kg_h"), ("overall", "flow_kg_h")):
        if key in props:
            return _parse_float(props[key])
    return 0.0


def _wt_dry_kg(dry_mass_kg: float, wt_frac: float) -> float:
    return dry_mass_kg * wt_frac


def gas_elements_kg_h(
    mass_kg_h: float,
    props: Mapping[Tuple[str, str], str],
    section: str = "fluid_phase",
    unit_suffix: str = "mol%",
) -> Tuple[ElementKgH, float, float]:
    """由气相质量流量与湿基 mol% 求元素质量。"""
    species = list(MW.keys())
    y: Dict[str, float] = {}
    for sp in species:
        key = (section, sp)
        if key in props:
            y[sp] = _parse_pct(props[key])
    if not y or mass_kg_h <= 0:
        return ElementKgH(), 0.0, 0.0
    mw_avg = sum(y[sp] * MW[sp] for sp in y)
    f_mol = mass_kg_h * 1000.0 / mw_avg
    el = ElementKgH()
    for sp, frac in y.items():
        n_mol = f_mol * frac
        for atom, count in ATOM_COUNT.get(sp, {}).items():
            setattr(el, atom, getattr(el, atom) + n_mol * count * ATOMIC_MASS[atom] / 1000.0)
    return el, f_mol, mw_avg


def tar_elements_kg_h(mass_kg_h: float) -> ElementKgH:
    if mass_kg_h <= 0:
        return ElementKgH()
    n_mol = mass_kg_h * 1000.0 / TAR_MW
    return ElementKgH(
        C=n_mol * TAR_EMPIRICAL["C"] * ATOMIC_MASS["C"] / 1000.0,
        H=n_mol * TAR_EMPIRICAL["H"] * ATOMIC_MASS["H"] / 1000.0,
        O=n_mol * TAR_EMPIRICAL["O"] * ATOMIC_MASS["O"] / 1000.0,
        N=n_mol * TAR_EMPIRICAL["N"] * ATOMIC_MASS["N"] / 1000.0,
        S=0.0,
    )


def entrained_elements_kg_h(mass_kg_h: float, props: Mapping[Tuple[str, str], str]) -> ElementKgH:
    """夹带固相：表给干基 C 与 minerals；char 按元素碳计，灰分为无机不计 CHONS。"""
    if mass_kg_h <= 0:
        return ElementKgH()
    c_frac = _parse_pct(props.get(("solid_phase", "carbon"), "0"))
    return ElementKgH(C=mass_kg_h * c_frac)


def audit_case1(df: pd.DataFrame) -> AuditResult:
    res = AuditResult()

    # --- 13C-4 ---
    c4 = stream_lookup(df, "13C-4")
    solid_kg = _flow_kg(c4, "solid_phase")
    co2_kg = _flow_kg(c4, "fluid_phase")
    moist = _parse_pct(c4.get(("solid_phase", "moisture"), "0"))
    dry_kg = solid_kg * (1.0 - moist)
    water_kg = solid_kg * moist

    bio = ElementKgH(
        C=_wt_dry_kg(dry_kg, _parse_pct(c4.get(("solid_phase", "carbon"), "0"))),
        H=_wt_dry_kg(dry_kg, _parse_pct(c4.get(("solid_phase", "hydrogen"), "0")))
        + water_kg * (2 * ATOMIC_MASS["H"] / 18.015),
        O=_wt_dry_kg(dry_kg, _parse_pct(c4.get(("solid_phase", "oxygen"), "0")))
        + water_kg * (ATOMIC_MASS["O"] / 18.015),
        N=_wt_dry_kg(dry_kg, _parse_pct(c4.get(("solid_phase", "nitrogen"), "0"))),
        S=_wt_dry_kg(dry_kg, _parse_pct(c4.get(("solid_phase", "sulfur"), "0"))),
    )
    co2_el = ElementKgH(
        C=co2_kg * ATOMIC_MASS["C"] / MW["CO2"],
        O=co2_kg * (2 * ATOMIC_MASS["O"] / MW["CO2"]),
    )
    res.inlet += bio + co2_el
    res.inlet_lines.append(
        f"| 13C-4 固相 {solid_kg:.1f} kg/h（干 {dry_kg:.1f}，水 {water_kg:.1f}） | "
        + _fmt_row(bio)
        + " |"
    )
    res.inlet_lines.append(f"| 13C-4 气相 CO₂ {co2_kg:.1f} kg/h | " + _fmt_row(co2_el) + " |")

    # --- 13HS1-1 ---
    hs = stream_lookup(df, "13HS1-1")
    steam_kg = _flow_kg(hs, "fluid_phase")
    steam_el = ElementKgH(
        H=steam_kg * (2 * ATOMIC_MASS["H"] / 18.015),
        O=steam_kg * (ATOMIC_MASS["O"] / 18.015),
    )
    res.inlet += steam_el
    res.inlet_lines.append(f"| 13HS1-1 蒸汽 {steam_kg:.1f} kg/h | " + _fmt_row(steam_el) + " |")

    # --- 13OG2-1 ---
    og = stream_lookup(df, "13OG2-1")
    og_kg = _flow_kg(og, "fluid_phase")
    og_el, _, _ = gas_elements_kg_h(
        og_kg,
        og,
        section="fluid_phase",
    )
    res.inlet += og_el
    res.inlet_lines.append(f"| 13OG2-1 O₂ 流 {og_kg:.1f} kg/h（95%O₂+杂质） | " + _fmt_row(og_el) + " |")

    # --- 13PGI-1 出口 ---
    pgi = stream_lookup(df, "13PGI-1")
    gas_kg = _flow_kg(pgi, "fluid_phase")
    res.outlet_gas, f_mol, mw_avg = gas_elements_kg_h(gas_kg, pgi, "fluid_phase")
    res.outlet_lines.append(
        f"| 13PGI-1 气相 {gas_kg:.1f} kg/h（F≈{f_mol:.0f} mol/h，MW≈{mw_avg:.2f}） | "
        + _fmt_row(res.outlet_gas)
        + " |"
    )

    tar_kg = _flow_kg(pgi, "fluid_phase_volatiles")
    res.outlet_tar = tar_elements_kg_h(tar_kg)
    res.outlet_lines.append(
        f"| 13PGI-1 挥发分/tar {tar_kg:.2f} kg/h（经验式 CHO₀.₀₈₂N₀.₀₁） | "
        + _fmt_row(res.outlet_tar)
        + " |"
    )

    ent_kg = _flow_kg(pgi, "solid_phase")
    res.outlet_entrained = entrained_elements_kg_h(ent_kg, pgi)
    res.outlet_lines.append(
        f"| 13PGI-1 夹带固相 {ent_kg:.2f} kg/h（表列 C_dry {pgi.get(('solid_phase','carbon'),'0')}） | "
        + _fmt_row(res.outlet_entrained)
        + " |"
    )

    # --- 13LBS-1 渣（无机，不计燃料元素）---
    lbs = stream_lookup(df, "13LBS-1")
    slag_kg = _flow_kg(lbs, "solid_phase")
    res.outlet_slag = ElementKgH()
    res.outlet_lines.append(f"| 13LBS-1 渣 {slag_kg:.1f} kg/h（100% minerals，无机） | " + _fmt_row(res.outlet_slag) + " |")

    res.notes.extend(
        [
            "进料包络：13C-4 + 13HS1-1 + 13OG2-1（不含烧嘴内部分配 13HS1-2~5 / 13OG2-2~5 / 13OGS-1）。",
            "出口包络：13PGI-1（气相 + tar + 夹带固相）+ 13LBS-1；不含 13COO1-11 旁路。",
            "生物质灰分（干基 8%）按无机计，未进入 C/H/O/N/S 燃料元素列。",
            "Tar 无表内元素分析，按项目默认经验式 CHO₀.₀₈₂N₀.₀₁ 换算。",
            "夹带固相仅计表列碳；未列 H/N/S。",
            "Ar、Cl 不参与 C/H/O/N/S 衡算。",
        ]
    )
    return res


def _fmt_row(el: ElementKgH) -> str:
    d = el.as_dict()
    return " | ".join(f"{d[e]:.2f}" for e in ELEMENTS)


def _fmt_gap_row(gap: ElementKgH, rel: Dict[str, float]) -> str:
    parts = []
    for e in ELEMENTS:
        v = getattr(gap, e)
        parts.append(f"{v:+.2f} ({rel[e]:+.1f}%)")
    return " | ".join(parts)


def render_markdown(result: AuditResult, *, csv_path: Path) -> str:
    gap = result.gap()
    rel = result.rel_err_pct()
    total_out = result.outlet_total

    lines = [
        "# DBI Stream Table：INCI 边界 C/H/O/N/S 元素衡算审计（Case-1）",
        "",
        "本文档由 `scripts/audit_dbi_inci_element_balance.py` 根据",
        "`data/reference/dbi_inci_stream_table_case1.csv` 自动生成。",
        "数据源：DBI PDF *TR5_APPENDIX 02 … Unit 13 INCI Gasifier*，Process Design Case I。",
        "",
        "## 1. 审计范围",
        "",
        "### 1.1 边界流股",
        "",
        "| 方向 | Stream | 说明 |",
        "|------|--------|------|",
        "| 进 | 13C-4 | 生物质固相 4000 kg/h + CO₂ 载体气 757.7 kg/h |",
        "| 进 | 13HS1-1 | HP 蒸汽 782.1 kg/h |",
        "| 进 | 13OG2-1 | O₂ 流 1343 kg/h（95% O₂ + 1.75% N₂ + 3.25% Ar） |",
        "| 出 | 13PGI-1 | 气相 6580 kg/h + 挥发分 18.49 kg/h + 夹带固相 275.33 kg/h |",
        "| 出 | 13LBS-1 | 渣 110 kg/h |",
        "",
        "不包含：13COO1-11（后气化旁路）、13HS1-2~5 / 13OG2-2~5 / 13OGS-1（总管→烧嘴内部分配）。",
        "",
        "### 1.2 换算假设",
        "",
    ]
    for note in result.notes:
        lines.append(f"- {note}")
    lines.extend(
        [
            "",
            "## 2. 进料元素流量（kg 元素/h）",
            "",
            "| 来源 | C | H | O | N | S |",
            "|------|-----|-----|-----|-----|-----|",
        ]
    )
    lines.extend(result.inlet_lines)
    lines.append("| **进料合计** | " + _fmt_row(result.inlet) + " |")

    lines.extend(
        [
            "",
            "## 3. 出口元素流量（kg 元素/h）",
            "",
            "| 去向 | C | H | O | N | S |",
            "|------|-----|-----|-----|-----|-----|",
        ]
    )
    lines.extend(result.outlet_lines)
    lines.append("| **出口合计** | " + _fmt_row(total_out) + " |")

    lines.extend(
        [
            "",
            "## 4. 元素衡算（进 − 出）",
            "",
            "| 元素 | 进料 kg/h | 出口 kg/h | 差额 kg/h | 相对进料 % | 闭合？ |",
            "|------|-----------|-----------|-----------|------------|--------|",
        ]
    )
    for el in ELEMENTS:
        inn = getattr(result.inlet, el)
        out = getattr(total_out, el)
        g = getattr(gap, el)
        r = rel[el]
        closed = "≈闭合" if abs(r) < 5.0 else "未闭合"
        lines.append(
            f"| **{el}** | {inn:.2f} | {out:.2f} | {g:+.2f} | {r:+.1f} | {closed} |"
        )

    lines.extend(
        [
            "",
            "## 5. 分项结论",
            "",
        ]
    )
    lines.extend(_conclusions(result))
    lines.extend(
        [
            "",
            "## 6. 复现",
            "",
            "```bash",
            "python3 scripts/audit_dbi_inci_element_balance.py",
            "python3 scripts/audit_dbi_inci_element_balance.py --write-doc",
            "```",
            "",
            f"输入：`{csv_path.relative_to(PROJECT_ROOT)}`",
            "",
        ]
    )
    return "\n".join(lines)


def _conclusions(result: AuditResult) -> List[str]:
    rel = result.rel_err_pct()
    gap = result.gap()
    lines: List[str] = []

    def bullet(el: str, text: str) -> None:
        lines.append(f"### {el}")
        lines.append("")
        lines.append(text)
        lines.append("")

    # C
    c_ok = abs(rel["C"]) < 10
    bullet(
        "碳（C）",
        f"进料 {result.inlet.C:.1f} kg/h，出口合计 {result.outlet_total.C:.1f} kg/h（气相 "
        f"{result.outlet_gas.C:.1f} + tar {result.outlet_tar.C:.1f} + 夹带碳 {result.outlet_entrained.C:.1f}）。"
        f"差额 {gap.C:+.1f} kg/h（{rel['C']:+.1f}%）。"
        + (
            "在 tar 经验式与夹带固相仅计表列碳的假设下，**碳大致可闭合或略盈余**。"
            if c_ok
            else "**碳未闭合**：出口显著高于进料时，需核对 CO₂ 载体是否应计入、夹带碳是否重复计量。"
        ),
    )

    # H
    h_text = (
        f"进料 {result.inlet.H:.1f} kg/h（蒸汽 + 生物质），出口 {result.outlet_total.H:.1f} kg/h，"
        f"差额 {gap.H:+.1f} kg/h（{rel['H']:+.1f}%）。"
    )
    if abs(rel["H"]) < 5.0:
        h_text += "在表列气相组成下，**氢大致闭合**（tar/夹带固相未计 H）。"
    elif gap.H < 0:
        h_text += "出口略高于进料，可能与气相 H₂O/H₂/CH₄ 湿基换算或进料水分口径有关。"
    else:
        h_text += "出口低于进料时，氢可能进入未表化的固相或未给出的 tar/char 氢含量。"
    bullet("氢（H）", h_text)

    # O
    bullet(
        "氧（O）",
        f"进料 {result.inlet.O:.1f} kg/h，出口 {result.outlet_total.O:.1f} kg/h，差额 {gap.O:+.1f} kg/h（{rel['O']:+.1f}%）。"
        "O 为最大通量元素；**少量相对误差对应较大绝对 kg/h 差额**，需结合 CO₂/O₂/蒸汽与 H₂O 湿基组成交叉核对。",
    )

    # N
    bullet(
        "氮（N）",
        f"进料 {result.inlet.N:.2f} kg/h（生物质 + O₂ 流 N₂ 杂质），出气相 N {result.outlet_gas.N:.2f} kg/h，"
        f"全出口 {result.outlet_total.N:.2f} kg/h，差额 {gap.N:+.2f} kg/h（{rel['N']:+.1f}%）。"
        "**未闭合**：13PGI-1 湿基 N₂≈2% 引入的 N 远大于边界进料 N；燃料氮（~32 kg/h）在气相 NH₃+HCN 中仅 ~0.5 kg/h，"
        "其余燃料氮在表中无固相/tar 归属。**可能存在未列入边界的 N₂ 进料，或出口 N₂ 为惰性填充而非严格元素衡算。**",
    )

    # S
    bullet(
        "硫（S）",
        f"进料 {result.inlet.S:.2f} kg/h，出口气相 H₂S/COS 合计 {result.outlet_gas.S:.3f} kg/h，"
        f"差额 {gap.S:+.2f} kg/h（{rel['S']:+.1f}%）。"
        + (
            "气相硫远低于生物质进料硫，**大部分硫可能进入固相（渣/夹带）但表未给出 S%**。"
            if gap.S > 0.5
            else "硫大致可由气相微量组分解释。"
        ),
    )

    lines.append("## 5.1 总评")
    lines.append("")
    n_open = sum(1 for el in ELEMENTS if abs(rel[el]) >= 5.0)
    lines.append(
        f"在 DBI p2–p3 stream table 可见数据下，五元素中约 **{n_open}** 项相对进料偏差 ≥5%，"
        "**不能将本表视为严格元素守恒的物料衡算基线**。"
        "宜用于流股流量与气相组成对标；闭合衡算需补充：N₂ 边界进料、固相/tar 元素分析、"
        "或与模型一致的反应器出口分相计量。"
    )
    lines.append("")
    return lines


def run_audit(csv_path: Path) -> AuditResult:
    df = load_stream_table(csv_path)
    return audit_case1(df)


def main() -> None:
    parser = argparse.ArgumentParser(description="DBI INCI C/H/O/N/S 元素衡算")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--write-doc", action="store_true", help="写入 doc/dbi-inci-element-balance-audit.md")
    parser.add_argument("--json", type=Path, help="可选：输出 JSON 摘要")
    args = parser.parse_args()

    result = run_audit(args.csv)
    md = render_markdown(result, csv_path=args.csv)

    if args.write_doc:
        DEFAULT_DOC.write_text(md, encoding="utf-8")
        print(f"已写入 {DEFAULT_DOC}")
    else:
        print(md)

    if args.json:
        payload = {
            "inlet": result.inlet.as_dict(),
            "outlet": result.outlet_total.as_dict(),
            "gap": result.gap().as_dict(),
            "rel_err_pct": result.rel_err_pct(),
        }
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"已写入 {args.json}")


if __name__ == "__main__":
    main()
