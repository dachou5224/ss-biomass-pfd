"""Unit 15 RGPOX：INCI 气相继承 + 夹带固相/挥发分 + 固定温度最小 Gibbs（1400°C）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Dict, Mapping, Optional, Tuple

import numpy as np

from .gibbs import GibbsSolveResult, solve_gibbs_major
from .parameters import (
    ATOMIC_WEIGHT,
    EQUILIBRIUM_CFG,
    GIBBS_ELEMENTS,
    MAJOR_SPECIES,
    MINOR_SPECIES,
    R_CONST,
    RGPOX_CFG,
    RGPOX_T_C,
    dbi_rgpox_case1_inlet,
)
from .thermo_baseline import get_gibbs_free_energy
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
class CharGasificationResult:
    """夹带 char 进 RGPOX 前的显式气化（CO2 置换 / 蒸汽 / Boudouard / 限氧 partial burn）。"""

    major_flow_mol_h: Dict[str, float]
    char_reacted_co2_replace_mol_h: float
    char_reacted_steam_mol_h: float
    char_reacted_boudouard_mol_h: float
    char_reacted_o2_mol_h: float
    char_unreacted_mol_h: float
    syngas_h2_oxidized_mol_h: float
    o2_feed_mol_h: float
    o2_to_gibbs_mol_h: float
    o2_bypass_mol_h: float
    mode: str


@dataclass(frozen=True)
class RgpoxInletBundle:
    elemental_feed_mol_h: Dict[str, float]
    entrained: RgpoxEntrainedSolid
    volatile_pyro: RgpoxVolatilePyrolysis
    trace_minor_mol_h: Dict[str, float]
    char_gasification: CharGasificationResult | None = None


@dataclass(frozen=True)
class RgpoxReactionSequenceResult:
    """RGPOX 反应顺序：气相平衡 → char 异相（或 legacy char→Gibbs）。"""

    stage: RgpoxStageResult
    major_flow_mol_h: Dict[str, float]
    reaction_sequence: str


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
    char_unreacted_mol_h: float
    char_gasification: CharGasificationResult | None
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
    """Case-1 可回退 DBI 15PGI-1 夹带固相；默认优先 SEP2 路由估算。"""
    cfg = RGPOX_CFG.get("entrained_solid", {})
    c_pct = float(cfg.get("dust_carbon_wt_pct_dry", 73.37))
    m_pct = float(cfg.get("dust_minerals_wt_pct_dry", 26.63))
    routing_total = max(char_to_pox_kg_h, 0.0) + max(ash_to_pox_kg_h, 0.0)
    if routing_total > 1e-9 and not cfg.get("use_dbi_boundary_mass", False):
        c_frac = max(char_to_pox_kg_h, 0.0) / routing_total * 100.0
        m_frac = max(ash_to_pox_kg_h, 0.0) / routing_total * 100.0
        return build_entrained_solid(routing_total, carbon_wt_pct_dry=c_frac, minerals_wt_pct_dry=m_frac)
    if case_id == "Case-1" and cfg.get("use_dbi_boundary_mass", False):
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


def compute_pox_ash_kg_h(
    entrained: RgpoxEntrainedSolid,
    *,
    char_conversion: float,
    char_unreacted_mol_h: float = 0.0,
) -> float:
    """15PGR-1 出口固相：夹带矿物 + 未反应残碳。"""
    conv = max(0.0, min(float(char_conversion), 1.0))
    residual_c_kg = entrained.carbon_kg_h * (1.0 - conv) + max(char_unreacted_mol_h, 0.0) * ATOMIC_WEIGHT["C"] / 1000.0
    return entrained.minerals_kg_h + residual_c_kg


def _normalize_o2_to_gibbs_mode(mode: str) -> str:
    return (mode or "char_stoich_co").strip().lower()


def o2_to_gibbs_char_mol_ratio_from_cfg(char_cfg: Mapping[str, object] | None = None) -> float | None:
    """显式 mol O₂ / mol char-C 上限；未配置时由 o2_to_gibbs_mode 推断（0.5 或 1.0）。"""
    cfg = dict(char_cfg or _rgpox_char_gasification_cfg())
    if "o2_to_gibbs_char_mol_ratio" in cfg:
        return max(float(cfg["o2_to_gibbs_char_mol_ratio"]), 0.0)
    mode_norm = _normalize_o2_to_gibbs_mode(str(cfg.get("o2_to_gibbs_mode", "char_stoich_co")))
    if mode_norm in ("char_stoich_co", "char_co", "stoich_co"):
        return 0.5
    if mode_norm in ("char_stoich_co2", "char_co2", "stoich_co2"):
        return 1.0
    return None


def resolve_rgpox_o2_to_gibbs_mol_h(
    o2_feed_mol_h: float,
    char_c_mol_h: float,
    *,
    mode: str,
    char_mol_ratio: float | None = None,
) -> float:
    """解析进入 Gibbs 氧化的 O₂ 上限（mol/h）。"""
    o2_feed = max(o2_feed_mol_h, 0.0)
    char_c = max(char_c_mol_h, 0.0)
    mode_norm = _normalize_o2_to_gibbs_mode(mode)
    if mode_norm in ("full_feed", "full", "legacy"):
        return o2_feed
    if mode_norm in ("off", "none", "zero"):
        return 0.0
    ratio = char_mol_ratio
    if ratio is None:
        if mode_norm in ("char_stoich_co", "char_co", "stoich_co"):
            ratio = 0.5
        elif mode_norm in ("char_stoich_co2", "char_co2", "stoich_co2"):
            ratio = 1.0
        else:
            raise ValueError(f"unknown RGPOX o2_to_gibbs_mode: {mode!r}")
    return min(o2_feed, max(float(ratio), 0.0) * char_c)


def resolve_rgpox_post_char_o2_mol_h(
    o2_feed_mol_h: float,
    char_c_mol_h: float,
    *,
    char_cfg: Mapping[str, object] | None = None,
) -> float:
    """gas_equilibrium_first：Gibbs 后用于 char 异相的剩余 O₂POX（mol/h）。"""
    cfg = dict(char_cfg or _rgpox_char_gasification_cfg())
    if not bool(cfg.get("post_char_use_remaining_o2", False)):
        return 0.0
    mode = str(cfg.get("o2_to_gibbs_mode", "char_stoich_co"))
    ratio = o2_to_gibbs_char_mol_ratio_from_cfg(cfg)
    o2_gibbs = resolve_rgpox_o2_to_gibbs_mol_h(
        max(o2_feed_mol_h, 0.0),
        max(char_c_mol_h, 0.0),
        mode=mode,
        char_mol_ratio=ratio,
    )
    return max(max(o2_feed_mol_h, 0.0) - o2_gibbs, 0.0)


def apply_char_co2_displacement(
    major_flow: Mapping[str, float],
    char_c_mol_h: float,
) -> Tuple[Dict[str, float], float, float]:
    """
    char 以 syngas CO₂ 置换方式进入气相：先剥离 CO₂，再 C+H₂O→CO+H₂（净效应接近 DBI char–syngas 耦合）。
    返回 (新 major 流, 已反应 char mol, 未反应 char mol)。
    """
    flow = {k: max(float(major_flow.get(k, 0.0)), 0.0) for k in MAJOR_SPECIES}
    char_left = max(char_c_mol_h, 0.0)
    if char_left <= 0.0:
        return flow, 0.0, 0.0
    co2 = flow.get("CO2", 0.0)
    rx = min(char_left, co2)
    if rx <= 0.0:
        return flow, 0.0, char_left
    flow["CO2"] = co2 - rx
    flow["H2O"] = max(flow.get("H2O", 0.0) - rx, 0.0)
    flow["CO"] = flow.get("CO", 0.0) + rx
    flow["H2"] = flow.get("H2", 0.0) + rx
    return flow, rx, char_left - rx


def _char_hetero_ta_params(char_cfg: Mapping[str, object] | None) -> Dict[str, float | bool]:
    """char 异相 Boudouard / 水汽变换（C+H2O→CO+H2）TA 参数。"""
    cfg = dict(char_cfg or {})
    het = dict(cfg.get("hetero_ta") or {})
    return {
        "enabled": bool(het.get("enabled", cfg.get("enable_hetero_ta", False))),
        "dt_boudouard_c": float(het.get("dt_boudouard_c", cfg.get("dt_boudouard_c", 0.0))),
        "dt_char_steam_c": float(het.get("dt_char_steam_c", cfg.get("dt_char_steam_c", 0.0))),
        "eta_boudouard": max(float(het.get("eta_boudouard", cfg.get("eta_boudouard", 1.0))), 0.0),
        "eta_char_steam": max(float(het.get("eta_char_steam", cfg.get("eta_char_steam", 1.0))), 0.0),
    }


def _equilibrium_constant_boudouard(t_k: float) -> float:
    """C + CO₂ ↔ 2CO（固相 C 活度≈1）。"""
    delta_g = (
        2.0 * get_gibbs_free_energy("CO", t_k)
        - get_gibbs_free_energy("CO2", t_k)
        - get_gibbs_free_energy("C", t_k)
    )
    return float(np.exp(-delta_g / (R_CONST * t_k)))


def _equilibrium_constant_char_steam(t_k: float) -> float:
    """异相水汽变换 / 蒸汽气化：C + H₂O ↔ CO + H₂。"""
    delta_g = (
        get_gibbs_free_energy("CO", t_k)
        + get_gibbs_free_energy("H2", t_k)
        - get_gibbs_free_energy("H2O", t_k)
        - get_gibbs_free_energy("C", t_k)
    )
    return float(np.exp(-delta_g / (R_CONST * t_k)))


def _char_hetero_kinetic_scale(dt_c: float, *, tau_c: float = 200.0) -> float:
    """气相对 char 反应已达过饱和（Q≥K）时，用 ΔT 缩放动力学上限（0→1）。"""
    if abs(dt_c) < 1e-9:
        return 1.0
    return max(0.0, min(1.0, float(np.exp(dt_c / tau_c))))


def _char_hetero_forward_extent(
    q0: float,
    k_eq: float,
    x_max: float,
    *,
    q_fn: Callable[[float], float],
    dt_c: float,
    eta: float,
    eps: float,
) -> float:
    """
    char 异相 TA：Q<K 时求平衡幅度；Q≥K 时 bulk 气相不需 char 转化，仍允许慢反应动力学上限×exp(ΔT/τ)。
    """
    x_max = max(x_max, 0.0)
    if x_max <= eps:
        return 0.0
    k_eq = max(k_eq, eps)
    if q0 < k_eq:
        x_eq = _solve_hetero_extent(q_fn, k_eq, x_max, eps=eps)
        return min(float(eta) * x_eq, x_max)
    kin = _char_hetero_kinetic_scale(dt_c)
    return min(float(eta) * kin * x_max, x_max)


def _solve_hetero_extent(
    q_fn: Callable[[float], float],
    k_eq: float,
    x_max: float,
    *,
    eps: float,
) -> float:
    """在 [0, x_max] 上求 Q(x)=K 的正向反应幅度；若无根则返回 0 或 x_max。"""
    if x_max <= eps:
        return 0.0
    k_eq = max(k_eq, eps)
    q0 = q_fn(0.0)
    if q0 >= k_eq:
        return 0.0
    q_max = q_fn(x_max - eps)
    if q_max <= k_eq:
        return max(x_max - eps, 0.0)

    low, high = 0.0, x_max - eps
    f_low = np.log(max(q0, eps) / k_eq)
    f_high = np.log(max(q_max, eps) / k_eq)
    if f_low * f_high > 0:
        return max(x_max - eps, 0.0) if abs(f_high) < abs(f_low) else 0.0

    tol = float(EQUILIBRIUM_CFG["extent_solver_tol"])
    max_iter = int(EQUILIBRIUM_CFG["extent_solver_max_iter"])
    for _ in range(max_iter):
        mid = 0.5 * (low + high)
        f_mid = np.log(max(q_fn(mid), eps) / k_eq)
        if abs(f_mid) < tol:
            return mid
        if f_low * f_mid <= 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid
    return 0.5 * (low + high)


def _react_char_boudouard(
    flow: Dict[str, float],
    char_remaining: float,
    *,
    ta: Mapping[str, float | bool] | None = None,
    t_c: float = RGPOX_T_C,
) -> Tuple[float, float]:
    """C + CO₂ → 2CO；可选异相 TA（ΔT + η）限制转化幅度。"""
    if char_remaining <= 0.0:
        return 0.0, char_remaining
    co2 = flow.get("CO2", 0.0)
    if co2 <= 0.0:
        return 0.0, char_remaining

    eps = float(EQUILIBRIUM_CFG.get("extent_solver_tol", 1e-10))
    x_max = min(char_remaining, co2)
    ta_eff = dict(ta or _char_hetero_ta_params(None))
    if not ta_eff["enabled"]:
        boud_rx = x_max
    else:
        t_k = max(t_c + 273.15 + float(ta_eff["dt_boudouard_c"]), float(EQUILIBRIUM_CFG["ta_min_t_k"]))
        k_eq = _equilibrium_constant_boudouard(t_k)
        co = max(flow.get("CO", 0.0), eps)
        co2 = max(co2, eps)
        q0 = co**2 / co2

        def q_at(x: float) -> float:
            return (co + 2.0 * x) ** 2 / max(co2 - x, eps)

        boud_rx = _char_hetero_forward_extent(
            q0,
            k_eq,
            x_max,
            q_fn=q_at,
            dt_c=float(ta_eff["dt_boudouard_c"]),
            eta=float(ta_eff["eta_boudouard"]),
            eps=eps,
        )

    if boud_rx <= 0.0:
        return 0.0, char_remaining
    flow["CO2"] = co2 - boud_rx
    flow["CO"] = flow.get("CO", 0.0) + 2.0 * boud_rx
    return boud_rx, char_remaining - boud_rx


def _react_char_steam(
    flow: Dict[str, float],
    char_remaining: float,
    steam_cap: float,
    *,
    ta: Mapping[str, float | bool] | None = None,
    t_c: float = RGPOX_T_C,
) -> Tuple[float, float]:
    """C + H₂O → CO + H₂（异相水汽变换）；可选 TA 限制转化。"""
    if char_remaining <= 0.0 or steam_cap <= 0.0:
        return 0.0, char_remaining
    h2o = flow.get("H2O", 0.0)
    if h2o <= 0.0:
        return 0.0, char_remaining

    eps = float(EQUILIBRIUM_CFG.get("extent_solver_tol", 1e-10))
    x_max = min(char_remaining, h2o, steam_cap)
    ta_eff = dict(ta or _char_hetero_ta_params(None))
    if not ta_eff["enabled"]:
        steam_rx = x_max
    else:
        t_k = max(t_c + 273.15 + float(ta_eff["dt_char_steam_c"]), float(EQUILIBRIUM_CFG["ta_min_t_k"]))
        k_eq = _equilibrium_constant_char_steam(t_k)
        co = max(flow.get("CO", 0.0), eps)
        h2 = max(flow.get("H2", 0.0), eps)
        h2o = max(h2o, eps)
        q0 = co * h2 / h2o

        def q_at(x: float) -> float:
            return (co + x) * (h2 + x) / max(h2o - x, eps)

        steam_rx = _char_hetero_forward_extent(
            q0,
            k_eq,
            x_max,
            q_fn=q_at,
            dt_c=float(ta_eff["dt_char_steam_c"]),
            eta=float(ta_eff["eta_char_steam"]),
            eps=eps,
        )

    if steam_rx <= 0.0:
        return 0.0, char_remaining
    flow["H2O"] = h2o - steam_rx
    flow["CO"] = flow.get("CO", 0.0) + steam_rx
    flow["H2"] = flow.get("H2", 0.0) + steam_rx
    return steam_rx, char_remaining - steam_rx


def apply_syngas_h2_limited_oxidation(
    major_flow: Mapping[str, float],
    o2_mol_h: float,
) -> Tuple[Dict[str, float], float, float]:
    """限 O₂ 将 syngas H₂ 部分氧化为 H₂O（H₂ + ½O₂ → H₂O），不进入 Gibbs 全量 O2POX。"""
    flow = {k: max(float(major_flow.get(k, 0.0)), 0.0) for k in MAJOR_SPECIES}
    o2_avail = max(o2_mol_h, 0.0)
    if o2_avail <= 0.0:
        return flow, 0.0, 0.0
    h2 = flow.get("H2", 0.0)
    h2_rx = min(h2, 2.0 * o2_avail)
    o2_used = 0.5 * h2_rx
    if h2_rx > 0.0:
        flow["H2"] = h2 - h2_rx
        flow["H2O"] = flow.get("H2O", 0.0) + h2_rx
    return flow, h2_rx, o2_used


def apply_char_gasification(
    major_flow: Mapping[str, float],
    *,
    char_c_mol_h: float,
    o2_feed_mol_h: float,
    mode: str = "char_stoich_co",
    enable_steam: bool = True,
    enable_boudouard: bool = True,
    char_steam_fraction: float = 1.0,
    gasification_order: str = "steam_first",
    char_cfg: Mapping[str, object] | None = None,
    t_c: float = RGPOX_T_C,
) -> CharGasificationResult:
    """
    夹带 char 异相气化：C+H2O→CO+H2、C+CO2→2CO、C+0.5O2→CO。
    可选 hetero_ta（Boudouard / 异相水汽变换 ΔT + η）限制慢反应趋近平衡的程度。
    """
    cfg = dict(char_cfg or {})
    hetero_ta = _char_hetero_ta_params(cfg)
    flow = {k: max(float(major_flow.get(k, 0.0)), 0.0) for k in MAJOR_SPECIES}
    char_remaining = max(char_c_mol_h, 0.0)
    steam_frac = max(0.0, min(float(char_steam_fraction), 1.0))
    steam_cap = char_remaining * steam_frac
    co2_replace_rx = 0.0
    steam_rx = 0.0
    boud_rx = 0.0
    o2_rx = 0.0
    h2_ox_rx = 0.0
    mode_norm = _normalize_o2_to_gibbs_mode(mode)
    order = (gasification_order or "steam_first").strip().lower()
    split_raw = cfg.get("char_boud_fraction")
    use_char_split = split_raw is not None

    def _run_steam_on(char_budget: float, cap: float) -> float:
        nonlocal steam_rx, char_remaining
        if not enable_steam or char_budget <= 0.0 or cap <= 0.0:
            return char_budget
        rx, char_left = _react_char_steam(
            flow,
            char_budget,
            cap,
            ta=hetero_ta,
            t_c=t_c,
        )
        steam_rx += rx
        char_remaining -= rx
        return char_left

    def _run_boud_on(char_budget: float) -> float:
        nonlocal boud_rx, char_remaining
        if not enable_boudouard or char_budget <= 0.0:
            return char_budget
        rx, char_left = _react_char_boudouard(
            flow,
            char_budget,
            ta=hetero_ta,
            t_c=t_c,
        )
        boud_rx += rx
        char_remaining -= rx
        return char_left

    def _run_steam() -> None:
        nonlocal char_remaining
        if char_remaining <= 0.0 or steam_cap <= steam_rx:
            return
        char_left = _run_steam_on(char_remaining, steam_cap - steam_rx)
        char_remaining = char_left

    def _run_boud() -> None:
        nonlocal char_remaining
        if char_remaining <= 0.0:
            return
        char_remaining = _run_boud_on(char_remaining)

    def _run_o2_char() -> None:
        nonlocal o2_rx, char_remaining
        o2_avail = max(o2_feed_mol_h - o2_rx, 0.0)
        if char_remaining > 0.0 and o2_avail > 0.0:
            o2_char_rx = min(o2_avail, 0.5 * char_remaining)
            char_from_o2 = 2.0 * o2_char_rx
            if char_from_o2 > 0.0:
                flow["CO"] = flow.get("CO", 0.0) + char_from_o2
                char_remaining -= char_from_o2
                o2_rx += o2_char_rx

    if use_char_split:
        alpha = max(0.0, min(float(split_raw), 1.0))
        boud_char = char_c_mol_h * alpha
        steam_char = char_c_mol_h * (1.0 - alpha) * steam_frac
        char_remaining = 0.0
        boud_left = _run_boud_on(boud_char)
        steam_left = _run_steam_on(steam_char, steam_char)
        char_remaining = boud_left + steam_left
    elif order in ("o2_first", "char_o2_first", "o2_before_steam"):
        _run_o2_char()
        _run_steam()
        _run_boud()
    elif order in ("boudouard_first", "boud_first", "co2_first"):
        _run_boud()
        _run_steam()
    else:
        _run_steam()
        _run_boud()

    if order not in ("o2_first", "char_o2_first", "o2_before_steam"):
        o2_budget = resolve_rgpox_o2_to_gibbs_mol_h(o2_feed_mol_h, char_c_mol_h, mode=mode_norm)
        if char_remaining > 0.0 and o2_budget > 0.0:
            o2_char_rx = min(o2_budget - o2_rx, 0.5 * char_remaining)
            o2_char_rx = max(o2_char_rx, 0.0)
            char_from_o2 = 2.0 * o2_char_rx
            if char_from_o2 > 0.0:
                flow["CO"] = flow.get("CO", 0.0) + char_from_o2
                char_remaining -= char_from_o2
                o2_rx += o2_char_rx

    if mode_norm in ("full_feed", "full", "legacy"):
        o2_to_gibbs = max(o2_feed_mol_h, 0.0)
        o2_bypass = 0.0
    else:
        o2_to_gibbs = 0.0
        o2_bypass = max(max(o2_feed_mol_h, 0.0) - o2_rx, 0.0)

    return CharGasificationResult(
        major_flow_mol_h=flow,
        char_reacted_co2_replace_mol_h=co2_replace_rx,
        char_reacted_steam_mol_h=steam_rx,
        char_reacted_boudouard_mol_h=boud_rx,
        char_reacted_o2_mol_h=o2_rx,
        char_unreacted_mol_h=char_remaining,
        syngas_h2_oxidized_mol_h=h2_ox_rx,
        o2_feed_mol_h=max(o2_feed_mol_h, 0.0),
        o2_to_gibbs_mol_h=o2_to_gibbs,
        o2_bypass_mol_h=o2_bypass,
        mode=mode_norm,
    )


def prepare_rgpox_char_gasification(
    major_flow: Mapping[str, float],
    *,
    char_c_mol_h: float,
    o2_feed_mol_h: float,
    char_cfg: Mapping[str, object] | None = None,
    t_c: float = RGPOX_T_C,
) -> CharGasificationResult:
    """RGPOX char 全路径：CO₂ 置换 + 常规气化 + 限 H₂ 氧化。"""
    cfg = dict(char_cfg or _rgpox_char_gasification_cfg())
    mode = str(cfg.get("o2_to_gibbs_mode", "char_stoich_co"))
    mode_norm = _normalize_o2_to_gibbs_mode(mode)
    if mode_norm in ("full_feed", "full", "legacy"):
        return apply_char_gasification(
            major_flow,
            char_c_mol_h=char_c_mol_h,
            o2_feed_mol_h=o2_feed_mol_h,
            mode=mode_norm,
            enable_steam=bool(cfg.get("enable_steam_gasification", True)),
            enable_boudouard=bool(cfg.get("enable_boudouard", True)),
            char_steam_fraction=float(cfg.get("char_steam_fraction", 1.0)),
            gasification_order=str(cfg.get("gasification_order", "steam_first")),
            char_cfg=cfg,
            t_c=t_c,
        )

    replace_frac = max(0.0, min(float(cfg.get("char_co2_replace_fraction", 0.0)), 1.0))
    replace_char = char_c_mol_h * replace_frac
    remainder_char = char_c_mol_h - replace_char
    flow, disp_rx, replace_left = apply_char_co2_displacement(major_flow, replace_char)
    hetero_ta = _char_hetero_ta_params(cfg)
    extra_steam = 0.0
    extra_boud = 0.0
    if replace_left > 0.0:
        extra_boud, replace_left = _react_char_boudouard(flow, replace_left, ta=hetero_ta, t_c=t_c)
        if replace_left > 0.0:
            extra_steam, replace_left = _react_char_steam(flow, replace_left, replace_left, ta=hetero_ta, t_c=t_c)

    gi = apply_char_gasification(
        flow,
        char_c_mol_h=remainder_char + replace_left,
        o2_feed_mol_h=o2_feed_mol_h,
        mode=mode_norm,
        enable_steam=bool(cfg.get("enable_steam_gasification", True)),
        enable_boudouard=bool(cfg.get("enable_boudouard", True)),
        char_steam_fraction=float(cfg.get("char_steam_fraction", 1.0)),
        gasification_order=str(cfg.get("gasification_order", "boudouard_first")),
        char_cfg=cfg,
        t_c=t_c,
    )
    h2_o2_frac = max(0.0, min(float(cfg.get("syngas_h2_o2_fraction", 0.0)), 1.0))
    h2_flow, h2_ox_rx, o2_h2_used = apply_syngas_h2_limited_oxidation(
        gi.major_flow_mol_h,
        gi.o2_bypass_mol_h * h2_o2_frac,
    )
    return CharGasificationResult(
        major_flow_mol_h=h2_flow,
        char_reacted_co2_replace_mol_h=disp_rx,
        char_reacted_steam_mol_h=gi.char_reacted_steam_mol_h + extra_steam,
        char_reacted_boudouard_mol_h=gi.char_reacted_boudouard_mol_h + extra_boud,
        char_reacted_o2_mol_h=gi.char_reacted_o2_mol_h,
        char_unreacted_mol_h=gi.char_unreacted_mol_h,
        syngas_h2_oxidized_mol_h=h2_ox_rx,
        o2_feed_mol_h=gi.o2_feed_mol_h,
        o2_to_gibbs_mol_h=gi.o2_to_gibbs_mol_h,
        o2_bypass_mol_h=max(gi.o2_bypass_mol_h - o2_h2_used, 0.0),
        mode=gi.mode,
    )


def _rgpox_char_gasification_cfg() -> Dict[str, object]:
    return dict(RGPOX_CFG.get("char_gasification", {}))


def _normalize_reaction_sequence(value: str) -> str:
    norm = (value or "gas_equilibrium_first").strip().lower()
    if norm in ("char_before_gibbs", "legacy", "char_first"):
        return "char_before_gibbs"
    return "gas_equilibrium_first"


def build_rgpox_gas_phase_inlet_bundle(
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
    气相先进 Gibbs 路径：INCI 气相 + 挥发分 + 限氧 O₂，**不含** char 碳。
    快反应（WGS / 有限氧化）在 1400°C 平衡中建立，char 异相反应后置。
    """
    inci_major = {k: inci_outlet_flow.get(k, 0.0) for k in MAJOR_SPECIES}
    trace_minor = {k: max(inci_outlet_flow.get(k, 0.0), 0.0) for k in MINOR_SPECIES}
    conv = max(0.0, min(float(char_conversion), 1.0))
    char_cfg = _rgpox_char_gasification_cfg()
    mode_norm = _normalize_o2_to_gibbs_mode(str(char_cfg.get("o2_to_gibbs_mode", "char_stoich_co")))
    char_c_mol = entrained.carbon_mol_h * conv
    o2_ratio = o2_to_gibbs_char_mol_ratio_from_cfg(char_cfg)
    elem = elemental_totals_from_species(inci_major, list(GIBBS_ELEMENTS))
    for el in GIBBS_ELEMENTS:
        elem[el] += volatile_pyro.elemental_mol_h.get(el, 0.0)
    if mode_norm in ("full_feed", "full", "legacy"):
        elem["O"] += 2.0 * max(o2_pox_mol_h, 0.0)
    else:
        o2_gas = resolve_rgpox_o2_to_gibbs_mol_h(
            max(o2_pox_mol_h, 0.0),
            char_c_mol,
            mode=mode_norm,
            char_mol_ratio=o2_ratio,
        )
        elem["O"] += 2.0 * o2_gas
    elem["N"] += 2.0 * max(o2_n2_imp_mol_h, 0.0)
    elem["Ar"] += max(o2_ar_imp_mol_h, 0.0)
    return RgpoxInletBundle(
        elemental_feed_mol_h=elem,
        entrained=entrained,
        volatile_pyro=volatile_pyro,
        trace_minor_mol_h=trace_minor,
        char_gasification=None,
    )


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
    RGPOX 进料包：INCI 气相 + 夹带 char 显式气化 + 挥发分热解元素 + 限氧 O2POX。
    矿物灰分不进 Gibbs，由 compute_pox_ash_kg_h 计为出口 slag。
    """
    inci_major = {k: inci_outlet_flow.get(k, 0.0) for k in MAJOR_SPECIES}
    trace_minor = {k: max(inci_outlet_flow.get(k, 0.0), 0.0) for k in MINOR_SPECIES}
    conv = max(0.0, min(float(char_conversion), 1.0))
    char_cfg = _rgpox_char_gasification_cfg()
    mode_norm = _normalize_o2_to_gibbs_mode(str(char_cfg.get("o2_to_gibbs_mode", "char_stoich_co")))
    char_c_mol = entrained.carbon_mol_h * conv
    char_gi: CharGasificationResult | None = None

    if mode_norm in ("full_feed", "full", "legacy"):
        elem = elemental_totals_from_species(inci_major, list(GIBBS_ELEMENTS))
        elem["C"] += char_c_mol
        for el in GIBBS_ELEMENTS:
            elem[el] += volatile_pyro.elemental_mol_h.get(el, 0.0)
        elem["O"] += 2.0 * max(o2_pox_mol_h, 0.0)
    else:
        char_gi = prepare_rgpox_char_gasification(
            inci_major,
            char_c_mol_h=char_c_mol,
            o2_feed_mol_h=max(o2_pox_mol_h, 0.0),
            char_cfg=char_cfg,
        )
        elem = elemental_totals_from_species(char_gi.major_flow_mol_h, list(GIBBS_ELEMENTS))
        elem["C"] += char_gi.char_unreacted_mol_h
        for el in GIBBS_ELEMENTS:
            elem[el] += volatile_pyro.elemental_mol_h.get(el, 0.0)
        elem["O"] += 2.0 * char_gi.o2_to_gibbs_mol_h

    elem["N"] += 2.0 * max(o2_n2_imp_mol_h, 0.0)
    elem["Ar"] += max(o2_ar_imp_mol_h, 0.0)
    return RgpoxInletBundle(
        elemental_feed_mol_h=elem,
        entrained=entrained,
        volatile_pyro=volatile_pyro,
        trace_minor_mol_h=trace_minor,
        char_gasification=char_gi,
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


def _finalize_rgpox_stage_with_char(
    stage: RgpoxStageResult,
    *,
    entrained: RgpoxEntrainedSolid,
    char_conversion: float,
    char_gasification: CharGasificationResult,
    final_major: Dict[str, float],
) -> RgpoxStageResult:
    conv = max(0.0, min(float(char_conversion), 1.0))
    char_unreacted = entrained.carbon_mol_h * (1.0 - conv) + char_gasification.char_unreacted_mol_h
    ash_kg = compute_pox_ash_kg_h(
        entrained,
        char_conversion=1.0,
        char_unreacted_mol_h=char_unreacted,
    )
    minor = dict(stage.minor_flow_mol_h)
    return RgpoxStageResult(
        elemental_feed_mol_h=dict(stage.elemental_feed_mol_h),
        major_flow_mol_h=dict(final_major),
        minor_flow_mol_h=minor,
        outlet_flow_mol_h={**final_major, **minor},
        gibbs=stage.gibbs,
        entrained=stage.entrained,
        volatile_pyro=stage.volatile_pyro,
        pox_ash_kg_h=ash_kg,
        char_unreacted_mol_h=char_unreacted,
        char_gasification=char_gasification,
        t_c=stage.t_c,
        t_k=stage.t_k,
    )


def run_rgpox_reaction_sequence(
    inci_outlet_flow: Dict[str, float],
    *,
    entrained: RgpoxEntrainedSolid,
    volatile_pyro: RgpoxVolatilePyrolysis,
    char_conversion: float,
    o2_pox_mol_h: float,
    o2_n2_imp_mol_h: float,
    o2_ar_imp_mol_h: float,
    p_bar: float,
    t_c: float | None = None,
    apply_ta: Callable[[Dict[str, float]], Dict[str, float]],
) -> RgpoxReactionSequenceResult:
    """
    RGPOX 反应顺序（默认 gas_equilibrium_first）：
    1) 气相 INCI + 挥发分 + O₂ → Gibbs @1400°C → TA（快反应平衡）
    2) 平衡气相上施加 char 异相气化（CO₂ 置换 / Boudouard / 蒸汽 / 限氧 char burn）
    """
    char_cfg = _rgpox_char_gasification_cfg()
    sequence = _normalize_reaction_sequence(str(char_cfg.get("reaction_sequence", "gas_equilibrium_first")))
    conv = max(0.0, min(float(char_conversion), 1.0))
    char_c_mol = entrained.carbon_mol_h * conv
    bundle_kwargs = dict(
        inci_outlet_flow=inci_outlet_flow,
        entrained=entrained,
        volatile_pyro=volatile_pyro,
        char_conversion=char_conversion,
        o2_pox_mol_h=o2_pox_mol_h,
        o2_n2_imp_mol_h=o2_n2_imp_mol_h,
        o2_ar_imp_mol_h=o2_ar_imp_mol_h,
    )

    if sequence == "char_before_gibbs":
        inlet = build_rgpox_inlet_bundle(**bundle_kwargs)
        stage = solve_rgpox_gibbs_equilibrium(
            inlet,
            p_bar=p_bar,
            t_c=t_c,
            char_conversion=char_conversion,
        )
        major = apply_ta(dict(stage.major_flow_mol_h))
        return RgpoxReactionSequenceResult(stage=stage, major_flow_mol_h=major, reaction_sequence=sequence)

    gas_inlet = build_rgpox_gas_phase_inlet_bundle(**bundle_kwargs)
    gas_stage = solve_rgpox_gibbs_equilibrium(
        gas_inlet,
        p_bar=p_bar,
        t_c=t_c,
        char_conversion=char_conversion,
    )
    gas_after_ta = apply_ta(dict(gas_stage.major_flow_mol_h))
    char_cfg_post = dict(char_cfg)
    char_cfg_post["syngas_h2_o2_fraction"] = 0.0
    o2_post = resolve_rgpox_post_char_o2_mol_h(
        max(o2_pox_mol_h, 0.0),
        char_c_mol,
        char_cfg=char_cfg,
    )
    if o2_post > 0.0:
        char_cfg_post["gasification_order"] = "o2_first"
    t_c_eff = RGPOX_T_C if t_c is None else float(t_c)
    char_gi = prepare_rgpox_char_gasification(
        gas_after_ta,
        char_c_mol_h=char_c_mol,
        o2_feed_mol_h=o2_post,
        char_cfg=char_cfg_post,
        t_c=t_c_eff,
    )
    final_major = dict(char_gi.major_flow_mol_h)
    stage = _finalize_rgpox_stage_with_char(
        gas_stage,
        entrained=entrained,
        char_conversion=char_conversion,
        char_gasification=char_gi,
        final_major=final_major,
    )
    return RgpoxReactionSequenceResult(stage=stage, major_flow_mol_h=final_major, reaction_sequence=sequence)


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
    char_gi = inlet.char_gasification if isinstance(inlet, RgpoxInletBundle) else None
    conv = max(0.0, min(float(char_conversion), 1.0))
    gi_unreacted = char_gi.char_unreacted_mol_h if char_gi is not None else 0.0
    char_unreacted = entrained_eff.carbon_mol_h * (1.0 - conv) + gi_unreacted
    ash_kg = compute_pox_ash_kg_h(
        entrained_eff,
        char_conversion=1.0,
        char_unreacted_mol_h=char_unreacted,
    )
    return RgpoxStageResult(
        elemental_feed_mol_h=elem,
        major_flow_mol_h=major,
        minor_flow_mol_h=minor,
        outlet_flow_mol_h=outlet,
        gibbs=gibbs,
        entrained=entrained_eff,
        volatile_pyro=volatile_eff,
        pox_ash_kg_h=ash_kg,
        char_unreacted_mol_h=char_unreacted,
        char_gasification=char_gi,
        t_c=t_c_eff,
        t_k=t_k,
    )


def rgpox_stage_notes(result: RgpoxStageResult, *, reaction_sequence: str | None = None) -> str:
    ent = result.entrained
    vol = result.volatile_pyro
    seq = _normalize_reaction_sequence(reaction_sequence or "gas_equilibrium_first")
    seq_note = f"seq={seq}"
    char_note = ""
    gi = result.char_gasification
    if gi is not None:
        char_note = (
            f"; char gasif CO2rep={gi.char_reacted_co2_replace_mol_h:.0f} "
            f"steam={gi.char_reacted_steam_mol_h:.0f} "
            f"boud={gi.char_reacted_boudouard_mol_h:.0f} "
            f"O2={gi.char_reacted_o2_mol_h:.0f} "
            f"H2ox={gi.syngas_h2_oxidized_mol_h:.0f} mol/h "
            f"(mode={gi.mode}, O2_bypass={gi.o2_bypass_mol_h:.0f} mol/h)"
        )
    return (
        f"{result.gibbs.message}; T={result.t_c:.1f}C (DBI fixed), {seq_note}, "
        f"inlet=INCI gas + entrained solid {ent.total_kg_h:.1f} kg/h "
        f"(C {ent.carbon_kg_h:.1f} + ash {ent.minerals_kg_h:.1f}), "
        f"volatile pyro {vol.tar_mass_kg_h:.2f} kg/h → Gibbs; "
        f"slag out {result.pox_ash_kg_h:.2f} kg/h{char_note}; "
        f"EqBasis: {RGPOX_EQUATION_BASIS}; trace=INCI passthrough (NH3/H2S/COS)"
    )
