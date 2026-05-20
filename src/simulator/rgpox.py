"""Unit 15 RGPOX：INCI 气相继承 + 夹带固相/挥发分 + 固定温度最小 Gibbs（1400°C）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple

from .gibbs import GibbsSolveResult, solve_gibbs_major
from .parameters import (
    ATOMIC_WEIGHT,
    GIBBS_ELEMENTS,
    MAJOR_SPECIES,
    MINOR_SPECIES,
    RGPOX_CFG,
    RGPOX_T_C,
    dbi_rgpox_case1_inlet,
)
from .species import elemental_totals_from_species
from .tar_models import TarFuelType, allocate_tar_from_mass_kg_h

RGPOX_EQUATION_BASIS = (
    "C+H2O<->CO+H2; C+CO2<->2CO; CO+H2O<->CO2+H2; CO+3H2<->CH4+H2O; "
    "C+O2->CO2; CO+0.5O2->CO2; H2+0.5O2->H2O; CH4+2O2->CO2+2H2O"
)

_FORMULA_TOKEN = re.compile(r"([A-Z][a-z]?)([\d.]*)")


@dataclass(frozen=True)
class RgpoxEntrainedSolid:
    """15PGI-1 夹带粉尘（DBI：73.37%C + 26.63% 矿物，干基 wt%）。"""

    total_kg_h: float
    carbon_kg_h: float
    minerals_kg_h: float
    carbon_mol_h: float


@dataclass(frozen=True)
class RgpoxVolatilePyrolysis:
    """RGPOX 入口挥发分热解 → 元素进 Gibbs。"""

    tar_mass_kg_h: float
    elemental_mol_h: Dict[str, float]


@dataclass(frozen=True)
class RgpoxInletBundle:
    elemental_feed_mol_h: Dict[str, float]
    entrained: RgpoxEntrainedSolid
    volatile_pyro: RgpoxVolatilePyrolysis
    trace_minor_mol_h: Dict[str, float]


@dataclass(frozen=True)
class RgpoxStageResult:
    elemental_feed_mol_h: Dict[str, float]
    major_flow_mol_h: Dict[str, float]
    minor_flow_mol_h: Dict[str, float]
    outlet_flow_mol_h: Dict[str, float]
    gibbs: GibbsSolveResult
    entrained: RgpoxEntrainedSolid
    volatile_pyro: RgpoxVolatilePyrolysis
    pox_ash_kg_h: float
    t_c: float
    t_k: float


def parse_empirical_formula(formula: str) -> Dict[str, float]:
    """解析经验式如 CHO0.082N0.01 → 每摩尔分子各元素原子数。"""
    out: Dict[str, float] = {}
    for el, num in _FORMULA_TOKEN.findall(formula.strip()):
        out[el] = out.get(el, 0.0) + (float(num) if num else 1.0)
    return out


def empirical_formula_mw(formula: str) -> float:
    atoms = parse_empirical_formula(formula)
    return sum(atoms[el] * ATOMIC_WEIGHT[el] for el in atoms)


def decompose_tar_mass_to_elements(tar_mass_kg_h: float, formula: str) -> Dict[str, float]:
    """挥发分质量 → 元素摩尔流量（用于 RGPOX 热解并入 Gibbs）。"""
    if tar_mass_kg_h <= 0.0:
        return {el: 0.0 for el in GIBBS_ELEMENTS}
    mw = empirical_formula_mw(formula)
    n_mol_h = max(tar_mass_kg_h, 0.0) * 1000.0 / mw
    atoms = parse_empirical_formula(formula)
    return {el: n_mol_h * atoms.get(el, 0.0) for el in GIBBS_ELEMENTS}


def build_entrained_solid(
    solid_kg_h: float,
    *,
    carbon_wt_pct_dry: float,
    minerals_wt_pct_dry: float,
) -> RgpoxEntrainedSolid:
    total = max(solid_kg_h, 0.0)
    c_kg = total * max(carbon_wt_pct_dry, 0.0) / 100.0
    m_kg = total * max(minerals_wt_pct_dry, 0.0) / 100.0
    c_mol = c_kg / ATOMIC_WEIGHT["C"] * 1000.0
    return RgpoxEntrainedSolid(
        total_kg_h=total,
        carbon_kg_h=c_kg,
        minerals_kg_h=m_kg,
        carbon_mol_h=c_mol,
    )


def resolve_entrained_solid(
    *,
    case_id: Optional[str],
    char_to_pox_kg_h: float,
    ash_to_pox_kg_h: float,
) -> RgpoxEntrainedSolid:
    """Case-1 用 DBI 15PGI-1 夹带固相；其它工况回退 SEP2 路由估算。"""
    cfg = RGPOX_CFG.get("entrained_solid", {})
    c_pct = float(cfg.get("dust_carbon_wt_pct_dry", 73.37))
    m_pct = float(cfg.get("dust_minerals_wt_pct_dry", 26.63))
    if case_id == "Case-1" and cfg.get("use_dbi_boundary_mass", True):
        try:
            pgi = dbi_rgpox_case1_inlet()["15PGI-1"]
        except (FileNotFoundError, KeyError, TypeError):
            pgi = None
        if pgi is not None:
            return build_entrained_solid(
                float(pgi["solid_kg_h"]),
                carbon_wt_pct_dry=float(pgi.get("solid_dust_carbon_wt_pct_dry", c_pct)),
                minerals_wt_pct_dry=float(pgi.get("solid_dust_minerals_wt_pct_dry", m_pct)),
            )
    total = max(char_to_pox_kg_h, 0.0) + max(ash_to_pox_kg_h, 0.0)
    if total <= 0.0:
        return build_entrained_solid(0.0, carbon_wt_pct_dry=c_pct, minerals_wt_pct_dry=m_pct)
    c_frac = max(char_to_pox_kg_h, 0.0) / total * 100.0
    m_frac = max(ash_to_pox_kg_h, 0.0) / total * 100.0
    return build_entrained_solid(total, carbon_wt_pct_dry=c_frac, minerals_wt_pct_dry=m_frac)


def pyrolyze_rgpox_volatiles(
    tar_mass_kg_h: float,
    *,
    tar_formula: str,
    tar_fuel_type: TarFuelType = "biomass",
    target_hc_ratio: float | None = None,
) -> RgpoxVolatilePyrolysis:
    """
    15PGI-1 夹带挥发分在 RGPOX 入口热解：surrogate C/H + 经验式 O/N → 元素进 Gibbs。
    """
    mass = max(tar_mass_kg_h, 0.0)
    if mass <= 1e-12:
        return RgpoxVolatilePyrolysis(tar_mass_kg_h=0.0, elemental_mol_h={el: 0.0 for el in GIBBS_ELEMENTS})
    tar = allocate_tar_from_mass_kg_h(mass, fuel_type=tar_fuel_type, target_hc_ratio=target_hc_ratio)
    empirical = decompose_tar_mass_to_elements(mass, tar_formula)
    elem = {el: 0.0 for el in GIBBS_ELEMENTS}
    elem["C"] = tar.carbon_mol_h
    elem["H"] = tar.hydrogen_mol_h
    elem["O"] = empirical.get("O", 0.0)
    # N 已在 INCI 气相 NH3/N2 中分配，不再从 tar 经验式重复注入
    elem["N"] = 0.0
    return RgpoxVolatilePyrolysis(tar_mass_kg_h=mass, elemental_mol_h=elem)


def compute_pox_ash_kg_h(entrained: RgpoxEntrainedSolid, *, char_conversion: float) -> float:
    """15PGR-1 出口固相：夹带矿物 + 未反应残碳。"""
    conv = max(0.0, min(float(char_conversion), 1.0))
    residual_c_kg = entrained.carbon_kg_h * (1.0 - conv)
    return entrained.minerals_kg_h + residual_c_kg


def build_rgpox_inlet_bundle(
    inci_outlet_flow: Dict[str, float],
    *,
    entrained: RgpoxEntrainedSolid,
    volatile_pyro: RgpoxVolatilePyrolysis,
    char_conversion: float,
    o2_pox_mol_h: float,
    o2_n2_imp_mol_h: float,
    o2_ar_imp_mol_h: float,
) -> RgpoxInletBundle:
    """
    RGPOX 进料包：INCI 气相（原样）+ 夹带碳（部分反应）+ 挥发分热解元素 + O2POX。
    矿物灰分不进 Gibbs，由 compute_pox_ash_kg_h 计为出口 slag。
    """
    inci_major = {k: inci_outlet_flow.get(k, 0.0) for k in MAJOR_SPECIES}
    trace_minor = {k: max(inci_outlet_flow.get(k, 0.0), 0.0) for k in MINOR_SPECIES}
    elem = elemental_totals_from_species(inci_major, list(GIBBS_ELEMENTS))
    conv = max(0.0, min(float(char_conversion), 1.0))
    elem["C"] += entrained.carbon_mol_h * conv
    for el in GIBBS_ELEMENTS:
        elem[el] += volatile_pyro.elemental_mol_h.get(el, 0.0)
    elem["O"] += 2.0 * max(o2_pox_mol_h, 0.0)
    elem["N"] += 2.0 * max(o2_n2_imp_mol_h, 0.0)
    elem["Ar"] += max(o2_ar_imp_mol_h, 0.0)
    return RgpoxInletBundle(
        elemental_feed_mol_h=elem,
        entrained=entrained,
        volatile_pyro=volatile_pyro,
        trace_minor_mol_h=trace_minor,
    )


def build_rgpox_elemental_feed(
    inci_outlet_flow: Dict[str, float],
    *,
    entrained: RgpoxEntrainedSolid,
    volatile_pyro: RgpoxVolatilePyrolysis,
    char_conversion: float,
    o2_pox_mol_h: float,
    o2_n2_imp_mol_h: float,
    o2_ar_imp_mol_h: float,
) -> Dict[str, float]:
    """兼容旧接口：返回元素进料 dict。"""
    return build_rgpox_inlet_bundle(
        inci_outlet_flow,
        entrained=entrained,
        volatile_pyro=volatile_pyro,
        char_conversion=char_conversion,
        o2_pox_mol_h=o2_pox_mol_h,
        o2_n2_imp_mol_h=o2_n2_imp_mol_h,
        o2_ar_imp_mol_h=o2_ar_imp_mol_h,
    ).elemental_feed_mol_h


def solve_rgpox_gibbs_equilibrium(
    inlet: RgpoxInletBundle | Dict[str, float],
    inci_trace_minor_mol_h: Dict[str, float] | None = None,
    *,
    entrained: RgpoxEntrainedSolid | None = None,
    volatile_pyro: RgpoxVolatilePyrolysis | None = None,
    char_conversion: float = 1.0,
    p_bar: float,
    t_c: float | None = None,
) -> RgpoxStageResult:
    """固定 T 最小 Gibbs；微量含硫/氮自 INCI 直通。"""
    if isinstance(inlet, RgpoxInletBundle):
        elem = dict(inlet.elemental_feed_mol_h)
        entrained_eff = inlet.entrained
        volatile_eff = inlet.volatile_pyro
        minor = dict(inlet.trace_minor_mol_h)
    else:
        elem = dict(inlet)
        entrained_eff = entrained or RgpoxEntrainedSolid(0.0, 0.0, 0.0, 0.0)
        volatile_eff = volatile_pyro or RgpoxVolatilePyrolysis(0.0, {el: 0.0 for el in GIBBS_ELEMENTS})
        minor = dict(inci_trace_minor_mol_h or {})

    t_c_eff = RGPOX_T_C if t_c is None else float(t_c)
    t_k = t_c_eff + 273.15
    gibbs = solve_gibbs_major(elem, MAJOR_SPECIES, t_k, p_bar)
    major = dict(gibbs.species_flow_mol_h)
    minor = {k: max(minor.get(k, 0.0), 0.0) for k in MINOR_SPECIES}
    outlet = {**major, **minor}
    ash_kg = compute_pox_ash_kg_h(entrained_eff, char_conversion=char_conversion)
    return RgpoxStageResult(
        elemental_feed_mol_h=elem,
        major_flow_mol_h=major,
        minor_flow_mol_h=minor,
        outlet_flow_mol_h=outlet,
        gibbs=gibbs,
        entrained=entrained_eff,
        volatile_pyro=volatile_eff,
        pox_ash_kg_h=ash_kg,
        t_c=t_c_eff,
        t_k=t_k,
    )


def rgpox_stage_notes(result: RgpoxStageResult) -> str:
    ent = result.entrained
    vol = result.volatile_pyro
    return (
        f"{result.gibbs.message}; T={result.t_c:.1f}C (DBI fixed), "
        f"inlet=INCI gas + entrained solid {ent.total_kg_h:.1f} kg/h "
        f"(C {ent.carbon_kg_h:.1f} + ash {ent.minerals_kg_h:.1f}), "
        f"volatile pyro {vol.tar_mass_kg_h:.2f} kg/h → Gibbs; "
        f"slag out {result.pox_ash_kg_h:.2f} kg/h; "
        f"EqBasis: {RGPOX_EQUATION_BASIS}; trace=INCI passthrough (NH3/H2S/COS)"
    )
