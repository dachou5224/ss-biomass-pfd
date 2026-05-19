from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .balance_audit import build_inci_mass_audit
from .contracts import ElementBalance, SimulationResult, UnitResult
from .data import INCI_C_CONVERSION, REFERENCE_CASES
from .elemental import BIOMASS_SAMPLES, biomass_to_elemental_moles
from .feed_streams import inci_o2_stream_species_kg_h
from .gibbs import solve_gibbs_major
from .parameters import (
    ATOMIC_WEIGHT,
    CELSIUS_TO_KELVIN_OFFSET,
    DEFAULT_BIOMASS_SAMPLE_FALLBACK,
    DEFAULT_CHEMISTRY_SETUP,
    EQUILIBRIUM_CFG,
    MOLECULAR_WEIGHT,
    NUMERICAL_CFG,
    RGPOX_CFG,
    SLAG_CFG,
)
from .pyrolysis import allocate_pyrolysis_products_elemental
from .species import (
    INCI_DRY_SPECIES,
    INCI_MAJOR_KEYS,
    INCI_UNMODELLED_WET_SPECIES,
    INCI_WET_SPECIES,
    MAJOR_SPECIES,
    MINOR_SPECIES,
    elemental_totals_from_species,
    species_flow_mass_kg_h,
)
from .tar_models import parse_tar_yield_mass_kg_h, tar_allocation_mass_kg_h
from .thermo import build_thermo_call_trace
from .thermo_baseline import R_CONST, get_gibbs_free_energy

_EQ = EQUILIBRIUM_CFG
_NUM = NUMERICAL_CFG
_MW = MOLECULAR_WEIGHT


def _feed_map(feed_df: pd.DataFrame) -> Dict[str, float]:
    values: Dict[str, float] = {}
    for _, row in feed_df.iterrows():
        values[str(row["Stream"])] = float(row["MassFlow_kg_h"])
    return values


def _spec_map(specs_df: pd.DataFrame) -> Dict[str, float]:
    return {str(r["Parameter"]): float(r["Value"]) for _, r in specs_df.iterrows()}


def _chem_map(chem_df: pd.DataFrame) -> Dict[str, str]:
    return {str(r["Field"]): str(r["Value"]) for _, r in chem_df.iterrows()}


def _kg_to_mol_h(mass_kg_h: float, mw_kg_kmol: float) -> float:
    return max(mass_kg_h, 0.0) / mw_kg_kmol * 1000.0


def _o2_impurity_moles(o2_mol_h: float, o2_purity_vol: float) -> Tuple[float, float]:
    """POSTO2 / O2POX 等仍按纯 O2 质量 + 纯度估算杂质（mol/h）。"""
    lo, hi = _EQ["o2_purity_vol_clip"]
    o2_frac = np.clip(o2_purity_vol / 100.0, lo, hi)
    impurity = max(o2_mol_h, 0.0) * (1.0 / o2_frac - 1.0)
    n2_imp = impurity * float(_EQ["o2_impurity_n2_frac_of_impurity"])
    ar_imp = impurity * float(_EQ["o2_impurity_ar_frac_of_impurity"])
    return n2_imp, ar_imp


def _inci_o2_species_kg_h(feed_map: Dict[str, float], chem: Dict[str, str]) -> Dict[str, float]:
    return inci_o2_stream_species_kg_h(feed_map.get("O2IN", 0.0), chem)


def _equilibrium_constant_wgs(t_k: float) -> float:
    delta_g = (
        get_gibbs_free_energy("CO2", t_k)
        + get_gibbs_free_energy("H2", t_k)
        - get_gibbs_free_energy("CO", t_k)
        - get_gibbs_free_energy("H2O", t_k)
    )
    return float(np.exp(-delta_g / (R_CONST * t_k)))


def _equilibrium_constant_meth(t_k: float) -> float:
    delta_g = (
        get_gibbs_free_energy("CH4", t_k)
        + get_gibbs_free_energy("H2O", t_k)
        - get_gibbs_free_energy("CO", t_k)
        - 3.0 * get_gibbs_free_energy("H2", t_k)
    )
    return float(np.exp(-delta_g / (R_CONST * t_k)))


def _meth_equilibrium_ch4(flow: Dict[str, float], t_meth_k: float, p_bar: float) -> float:
    """CH4 mol/h at meth equilibrium for fixed CO/H2/H2O: CO + 3H2 <-> CH4 + H2O."""
    eps = 1e-18
    co = max(flow.get("CO", 0.0), eps)
    h2 = max(flow.get("H2", 0.0), eps)
    h2o = max(flow.get("H2O", 0.0), eps)
    k_meth = _equilibrium_constant_meth(t_meth_k)
    p_ratio = max(p_bar / float(_EQ["pressure_ratio_bar"]), eps)
    return k_meth * co * (h2**3) / h2o / (p_ratio**2)


def _apply_meth_approach(
    state: Dict[str, float],
    t_meth_k: float,
    p_bar: float,
    eta_meth: float,
) -> None:
    """
    Restricted methanation: move CH4 toward equilibrium at T_meth, but only when
    that equilibrium is lower than the Gibbs result (reverse methanation allowed).
    """
    if eta_meth <= 1e-12:
        return
    eps = 1e-12
    ch4_now = max(state.get("CH4", 0.0), 0.0)
    ch4_eq = _meth_equilibrium_ch4(state, t_meth_k, p_bar)
    if ch4_eq >= ch4_now:
        return
    delta = eta_meth * (ch4_eq - ch4_now)
    delta = max(delta, -ch4_now)
    delta = min(delta, 0.0)
    h2o_after = state.get("H2O", 0.0) + delta
    if h2o_after < eps:
        delta = max(-(state.get("H2O", 0.0) - eps), delta)
    state["CH4"] = max(ch4_now + delta, eps)
    state["CO"] = max(state.get("CO", 0.0) - delta, eps)
    state["H2"] = max(state.get("H2", 0.0) - 3.0 * delta, eps)
    state["H2O"] = max(state.get("H2O", 0.0) + delta, eps)


def _equilibrium_constant_ox_co(t_k: float) -> float:
    delta_g = (
        get_gibbs_free_energy("CO2", t_k)
        - get_gibbs_free_energy("CO", t_k)
        - 0.5 * get_gibbs_free_energy("O2", t_k)
    )
    return float(np.exp(-delta_g / (R_CONST * t_k)))


def _equilibrium_constant_ox_h2(t_k: float) -> float:
    delta_g = (
        get_gibbs_free_energy("H2O", t_k)
        - get_gibbs_free_energy("H2", t_k)
        - 0.5 * get_gibbs_free_energy("O2", t_k)
    )
    return float(np.exp(-delta_g / (R_CONST * t_k)))


def _equilibrium_constant_ox_ch4(t_k: float) -> float:
    delta_g = (
        get_gibbs_free_energy("CO2", t_k)
        + 2.0 * get_gibbs_free_energy("H2O", t_k)
        - get_gibbs_free_energy("CH4", t_k)
        - 2.0 * get_gibbs_free_energy("O2", t_k)
    )
    return float(np.exp(-delta_g / (R_CONST * t_k)))


def _apply_inci_temperature_approach(
    flow: Dict[str, float],
    t_gibbs_k: float,
    p_bar: float,
    dt_wgs_c: float,
    dt_meth_c: float,
    eta_wgs: float,
    eta_meth: float,
    dt_ox_co_c: float,
    dt_ox_h2_c: float,
    dt_ox_ch4_c: float,
) -> Dict[str, float]:
    if (
        abs(dt_wgs_c) < 1e-9
        and abs(dt_meth_c) < 1e-9
        and abs(eta_wgs - 1.0) < 1e-9
        and abs(eta_meth - 1.0) < 1e-9
        and abs(dt_ox_co_c) < 1e-9
        and abs(dt_ox_h2_c) < 1e-9
        and abs(dt_ox_ch4_c) < 1e-9
    ):
        return dict(flow)

    n0 = {
        "CO": max(flow.get("CO", 0.0), 0.0),
        "H2": max(flow.get("H2", 0.0), 0.0),
        "CO2": max(flow.get("CO2", 0.0), 0.0),
        "CH4": max(flow.get("CH4", 0.0), 0.0),
        "H2O": max(flow.get("H2O", 0.0), 0.0),
        "O2": max(flow.get("O2", 0.0), 0.0),
    }
    eps = float(_NUM["restricted_equilibrium_zero_tol"])
    t_min = float(_EQ["ta_min_t_k"])
    t_wgs_eff = max(t_gibbs_k + dt_wgs_c, t_min)
    t_meth_eff = max(t_gibbs_k + dt_meth_c, t_min)
    t_ox_co_eff = max(t_gibbs_k + dt_ox_co_c, t_min)
    t_ox_h2_eff = max(t_gibbs_k + dt_ox_h2_c, t_min)
    t_ox_ch4_eff = max(t_gibbs_k + dt_ox_ch4_c, t_min)
    k_wgs = _equilibrium_constant_wgs(t_wgs_eff)
    k_ox_co = _equilibrium_constant_ox_co(t_ox_co_eff)
    k_ox_h2 = _equilibrium_constant_ox_h2(t_ox_h2_eff)
    k_ox_ch4 = _equilibrium_constant_ox_ch4(t_ox_ch4_eff)
    p_ratio = max(p_bar / float(_EQ["pressure_ratio_bar"]), eps)

    def _solve_wgs_extent(state: Dict[str, float]) -> float:
        low = -min(state["CO2"], state["H2"]) + eps
        high = min(state["CO"], state["H2O"]) - eps
        if low >= high:
            return 0.0

        def f(x: float) -> float:
            denom = max((state["CO"] - x) * (state["H2O"] - x), eps)
            q = ((state["CO2"] + x) * (state["H2"] + x)) / denom
            return np.log(max(q, eps) / max(k_wgs, eps))

        f_low = f(low)
        f_high = f(high)
        if f_low * f_high > 0:
            return low if abs(f_low) < abs(f_high) else high
        for _ in range(int(_EQ["extent_solver_max_iter"])):
            mid = 0.5 * (low + high)
            f_mid = f(mid)
            if abs(f_mid) < float(_EQ["extent_solver_tol"]):
                return mid
            if f_low * f_mid <= 0:
                high = mid
                f_high = f_mid
            else:
                low = mid
                f_low = f_mid
        return 0.5 * (low + high)

    def _solve_ox_co_extent(state: Dict[str, float]) -> float:
        low = -state["CO2"] + eps
        high = min(state["CO"], 2.0 * state["O2"]) - eps
        if low >= high:
            return 0.0

        def f(x: float) -> float:
            denom = max((state["CO"] - x) * np.sqrt(max(state["O2"] - 0.5 * x, eps)), eps)
            q = ((state["CO2"] + x) / denom) * (p_ratio ** -0.5)
            return np.log(max(q, eps) / max(k_ox_co, eps))

        f_low = f(low)
        f_high = f(high)
        if f_low * f_high > 0:
            return low if abs(f_low) < abs(f_high) else high
        for _ in range(int(_EQ["extent_solver_max_iter"])):
            mid = 0.5 * (low + high)
            f_mid = f(mid)
            if abs(f_mid) < float(_EQ["extent_solver_tol"]):
                return mid
            if f_low * f_mid <= 0:
                high = mid
                f_high = f_mid
            else:
                low = mid
                f_low = f_mid
        return 0.5 * (low + high)

    def _solve_ox_h2_extent(state: Dict[str, float]) -> float:
        low = -state["H2O"] + eps
        high = min(state["H2"], 2.0 * state["O2"]) - eps
        if low >= high:
            return 0.0

        def f(x: float) -> float:
            denom = max((state["H2"] - x) * np.sqrt(max(state["O2"] - 0.5 * x, eps)), eps)
            q = ((state["H2O"] + x) / denom) * (p_ratio ** -0.5)
            return np.log(max(q, eps) / max(k_ox_h2, eps))

        f_low = f(low)
        f_high = f(high)
        if f_low * f_high > 0:
            return low if abs(f_low) < abs(f_high) else high
        for _ in range(int(_EQ["extent_solver_max_iter"])):
            mid = 0.5 * (low + high)
            f_mid = f(mid)
            if abs(f_mid) < float(_EQ["extent_solver_tol"]):
                return mid
            if f_low * f_mid <= 0:
                high = mid
                f_high = f_mid
            else:
                low = mid
                f_low = f_mid
        return 0.5 * (low + high)

    def _solve_ox_ch4_extent(state: Dict[str, float]) -> float:
        low = -min(state["CO2"], state["H2O"] / 2.0) + eps
        high = min(state["CH4"], state["O2"] / 2.0) - eps
        if low >= high:
            return 0.0

        def f(x: float) -> float:
            denom = max((state["CH4"] - x) * ((state["O2"] - 2.0 * x) ** 2), eps)
            q = (
                ((state["CO2"] + x) * ((state["H2O"] + 2.0 * x) ** 2))
                / denom
                * (p_ratio ** -2.0)
            )
            return np.log(max(q, eps) / max(k_ox_ch4, eps))

        f_low = f(low)
        f_high = f(high)
        if f_low * f_high > 0:
            return low if abs(f_low) < abs(f_high) else high
        for _ in range(int(_EQ["extent_solver_max_iter"])):
            mid = 0.5 * (low + high)
            f_mid = f(mid)
            if abs(f_mid) < float(_EQ["extent_solver_tol"]):
                return mid
            if f_low * f_mid <= 0:
                high = mid
                f_high = f_mid
            else:
                low = mid
                f_low = f_mid
        return 0.5 * (low + high)

    st = dict(n0)
    x1 = _solve_wgs_extent(st)
    x1 *= eta_wgs
    st["CO"] -= x1
    st["H2O"] -= x1
    st["CO2"] += x1
    st["H2"] += x1

    _apply_meth_approach(st, t_meth_eff, p_bar, eta_meth)

    x3 = _solve_ox_co_extent(st)
    st["CO"] -= x3
    st["O2"] -= 0.5 * x3
    st["CO2"] += x3

    x4 = _solve_ox_h2_extent(st)
    st["H2"] -= x4
    st["O2"] -= 0.5 * x4
    st["H2O"] += x4

    x5 = _solve_ox_ch4_extent(st)
    st["CH4"] -= x5
    st["O2"] -= 2.0 * x5
    st["CO2"] += x5
    st["H2O"] += 2.0 * x5

    tuned = dict(flow)
    for key in ("CO", "H2", "CO2", "CH4", "H2O", "O2"):
        tuned[key] = max(st[key], eps)
    return tuned


def _apply_inci_gas_oxidation(
    flow: Dict[str, float],
    o2_mol_h: float,
) -> Tuple[Dict[str, float], float]:
    if o2_mol_h <= 1e-12:
        return dict(flow), 0.0

    out = dict(flow)
    o2_left = max(o2_mol_h, 0.0)

    # CH4 + 2O2 -> CO2 + 2H2O
    ch4 = max(out.get("CH4", 0.0), 0.0)
    x_ch4 = min(ch4, o2_left / 2.0)
    if x_ch4 > 0.0:
        out["CH4"] = ch4 - x_ch4
        out["CO2"] = max(out.get("CO2", 0.0), 0.0) + x_ch4
        out["H2O"] = max(out.get("H2O", 0.0), 0.0) + 2.0 * x_ch4
        o2_left -= 2.0 * x_ch4

    # H2 + 0.5O2 -> H2O
    h2 = max(out.get("H2", 0.0), 0.0)
    x_h2 = min(h2, 2.0 * o2_left)
    if x_h2 > 0.0:
        out["H2"] = h2 - x_h2
        out["H2O"] = max(out.get("H2O", 0.0), 0.0) + x_h2
        o2_left -= 0.5 * x_h2

    # CO + 0.5O2 -> CO2
    co = max(out.get("CO", 0.0), 0.0)
    x_co = min(co, 2.0 * o2_left)
    if x_co > 0.0:
        out["CO"] = co - x_co
        out["CO2"] = max(out.get("CO2", 0.0), 0.0) + x_co
        o2_left -= 0.5 * x_co

    out["O2"] = max(out.get("O2", 0.0), 0.0) + max(o2_left, 0.0)
    return out, max(o2_left, 0.0)


def _build_inci_elemental_inlet(
    feed_map: Dict[str, float], sample_id: str, chem: Dict[str, str]
) -> Tuple[Dict[str, float], float]:
    bio = biomass_to_elemental_moles(sample_id, feed_map.get("Biomass", 0.0))
    inlet = {k: bio.get(k, 0.0) for k in ("C", "H", "O", "N", "S", "Ar")}
    ash_kg_h = bio["Ash_kg_h"]
    moisture_kg_h = feed_map.get("Biomass", 0.0) * BIOMASS_SAMPLES[sample_id].mad_pct / 100.0
    moisture_h2o_mol_h = _kg_to_mol_h(moisture_kg_h, 18.015)
    inlet["H"] += 2.0 * moisture_h2o_mol_h
    inlet["O"] += 1.0 * moisture_h2o_mol_h

    co2_carrier = feed_map.get("CIN", 0.0) + feed_map.get("CO2IN", 0.0)
    inlet["C"] += 1.0 * _kg_to_mol_h(co2_carrier, 44.009)
    inlet["O"] += 2.0 * _kg_to_mol_h(co2_carrier, 44.009)

    o2_parts = _inci_o2_species_kg_h(feed_map, chem)
    inlet["O"] += 2.0 * _kg_to_mol_h(o2_parts.get("O2", 0.0), 31.998)
    inlet["H"] += 2.0 * _kg_to_mol_h(feed_map.get("H2OIN", 0.0), 18.015)
    inlet["O"] += 1.0 * _kg_to_mol_h(feed_map.get("H2OIN", 0.0), 18.015)
    inlet["N"] += 2.0 * _kg_to_mol_h(feed_map.get("N2IN", 0.0), 28.014)
    inlet["N"] += 2.0 * _kg_to_mol_h(o2_parts.get("N2", 0.0), 28.014)
    inlet["Ar"] += _kg_to_mol_h(o2_parts.get("Ar", 0.0), 39.948)

    return inlet, ash_kg_h


def _feed_inert_moles(feed_map: Dict[str, float], chem: Dict[str, str]) -> Tuple[float, float]:
    o2_parts = _inci_o2_species_kg_h(feed_map, chem)
    n2_mol = _kg_to_mol_h(feed_map.get("N2IN", 0.0), 28.014) + _kg_to_mol_h(o2_parts.get("N2", 0.0), 28.014)
    ar_mol = _kg_to_mol_h(o2_parts.get("Ar", 0.0), 39.948)
    return n2_mol, ar_mol


def _build_total_system_inlet_elements(inci_inlet: Dict[str, float], feed_map: Dict[str, float], o2_purity_vol: float) -> Dict[str, float]:
    total = dict(inci_inlet)
    total["O"] += 2.0 * _kg_to_mol_h(feed_map.get("POSTO2", 0.0), 31.998)
    total["H"] += 2.0 * _kg_to_mol_h(feed_map.get("POSTH2O", 0.0), 18.015)
    total["O"] += 1.0 * _kg_to_mol_h(feed_map.get("POSTH2O", 0.0), 18.015)
    total["C"] += 1.0 * _kg_to_mol_h(feed_map.get("POSTCO2", 0.0), 44.009)
    total["O"] += 2.0 * _kg_to_mol_h(feed_map.get("POSTCO2", 0.0), 44.009)
    total["O"] += 2.0 * _kg_to_mol_h(feed_map.get("O2POX", 0.0), 31.998)

    # O2 purity impurity for post/pox oxygen streams
    for key in ("POSTO2", "O2POX"):
        o2_mol = _kg_to_mol_h(feed_map.get(key, 0.0), 31.998)
        n2_imp, ar_imp = _o2_impurity_moles(o2_mol, o2_purity_vol)
        total["N"] += 2.0 * n2_imp
        total["Ar"] += ar_imp
    return total


def _inci_feed_stream_mass_kg_h(feed_map: Dict[str, float]) -> float:
    """INCI 边界进料 stream 质量加和（O2IN 为全流股质量）。"""
    return sum(
        feed_map.get(k, 0.0)
        for k in ("Biomass", "CIN", "O2IN", "H2OIN", "N2IN", "CO2IN")
    )


def _split_biomass_n(n_mol_h: float, nh3_frac: float) -> Tuple[float, float]:
    """元素 N (mol/h) → NH3 与 N2（来自生物质）摩尔流。"""
    frac = float(np.clip(nh3_frac, 0.0, 1.0))
    n_nh3 = max(n_mol_h, 0.0) * frac
    n_n2 = max(n_mol_h - n_nh3, 0.0) / 2.0
    return n_nh3, n_n2


def _split_biomass_s(s_mol_h: float, h2s_frac: float, release_frac: float) -> Tuple[float, float]:
    """元素 S (mol/h) → 气相 H2S / COS 摩尔流。"""
    s_gas = max(s_mol_h, 0.0) * float(np.clip(release_frac, 0.0, 1.0))
    frac = float(np.clip(h2s_frac, 0.0, 1.0))
    n_h2s = s_gas * frac
    n_cos = s_gas - n_h2s
    return n_h2s, n_cos


def _allocate_trace_species_from_biomass(
    major_flow: Dict[str, float],
    *,
    biomass_s_mol_h: float,
    biomass_n_mol_h: float,
    feed_n2_mol_h: float,
    feed_ar_mol_h: float,
    h2s_split: float,
    nh3_frac_of_biomass_n: float,
    s_release_frac: float,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    生物质 N/S 元素守恒分配至 N2/NH3、H2S/COS；进料 N2/Ar 叠加至主气。
    """
    flow = dict(major_flow)
    n_h2s, n_cos = _split_biomass_s(biomass_s_mol_h, h2s_split, s_release_frac)
    n_nh3, n_n2_bio = _split_biomass_n(biomass_n_mol_h, nh3_frac_of_biomass_n)

    flow["H2"] = max(flow.get("H2", 0.0) - 2.0 * n_h2s - 1.5 * n_nh3, 1e-9)
    flow["CO"] = max(flow.get("CO", 0.0) - n_cos, 1e-9)
    flow["N2"] = max(feed_n2_mol_h, 0.0) + n_n2_bio
    flow["Ar"] = max(feed_ar_mol_h, 0.0)

    minor = {"H2S": n_h2s, "COS": n_cos, "NH3": n_nh3}
    return flow, minor


def _add_minor_species(
    major: Dict[str, float],
    sulfur_mol_h: float,
    h2s_split: float,
    biomass_n_mol_h: float,
    feed_n2_mol_h: float,
    feed_ar_mol_h: float,
    nh3_frac_of_biomass_n: float,
    s_release_frac: float,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    return _allocate_trace_species_from_biomass(
        major,
        biomass_s_mol_h=sulfur_mol_h,
        biomass_n_mol_h=biomass_n_mol_h,
        feed_n2_mol_h=feed_n2_mol_h,
        feed_ar_mol_h=feed_ar_mol_h,
        h2s_split=h2s_split,
        nh3_frac_of_biomass_n=nh3_frac_of_biomass_n,
        s_release_frac=s_release_frac,
    )


def _dry_vol_pct(flow_mol_h: Dict[str, float], keys: List[str]) -> Dict[str, float]:
    total = sum(max(flow_mol_h.get(k, 0.0), 0.0) for k in keys if k != "H2O")
    if total <= 0:
        return {k: 0.0 for k in keys}
    digits = int(_NUM["vol_pct_round_digits"])
    return {k: round(100.0 * max(flow_mol_h.get(k, 0.0), 0.0) / total, digits) for k in keys}


def _wet_vol_pct(flow_mol_h: Dict[str, float], keys: List[str]) -> Dict[str, float]:
    total = sum(max(flow_mol_h.get(k, 0.0), 0.0) for k in keys)
    if total <= 0:
        return {k: 0.0 for k in keys}
    digits = int(_NUM["vol_pct_round_digits"])
    return {k: round(100.0 * max(flow_mol_h.get(k, 0.0), 0.0) / total, digits) for k in keys}


def _match_reference_case(feed_map: Dict[str, float], sample: str) -> str | None:
    for case_id, payload in REFERENCE_CASES.items():
        if payload["sample"] != sample:
            continue
        matched = True
        for stream, (mass, _, _) in payload["feeds"].items():
            if abs(feed_map.get(stream, -999999.0) - mass) > float(_NUM["reference_feed_match_tol_kg_h"]):
                matched = False
                break
        if matched:
            return case_id
    return None


def _calc_rmsd_pct(pred: Dict[str, float], ref: Dict[str, float], keys: List[str]) -> float:
    if not keys:
        return 0.0
    arr = [pred.get(k, 0.0) - ref.get(k, 0.0) for k in keys]
    return float(np.sqrt(np.mean(np.square(arr))))


def run_fixed_temperature_simulation(
    feed_df: pd.DataFrame,
    specs_df: pd.DataFrame,
    chemistry_df: pd.DataFrame,
) -> SimulationResult:
    feed = _feed_map(feed_df)
    specs = _spec_map(specs_df)
    chem = _chem_map(chemistry_df)

    sample = chem.get("Sample", DEFAULT_BIOMASS_SAMPLE_FALLBACK)
    if sample not in BIOMASS_SAMPLES:
        sample = DEFAULT_BIOMASS_SAMPLE_FALLBACK

    tar_factor_text = chem.get("Tar Yield Factor", DEFAULT_CHEMISTRY_SETUP["Tar Yield Factor"])
    tar_yield_mass_kg_h = parse_tar_yield_mass_kg_h(feed.get("Biomass", 0.0), sample, tar_factor_text)
    def _chem_float(key: str) -> float:
        return float(chem.get(key, str(DEFAULT_CHEMISTRY_SETUP[key])))

    h2s_split = _chem_float("H2S/COS split to H2S")
    nh3_frac = _chem_float("Biomass N to NH3 Frac")
    s_release_frac = _chem_float("Biomass S Release Frac")
    o2_purity = _chem_float("O2 Purity vol%")
    tar_hc = _chem_float("Tar target H/C")
    pyro_scheme = chem.get("Pyrolysis Scheme", DEFAULT_CHEMISTRY_SETUP["Pyrolysis Scheme"]).strip().lower()
    vm_dry_wt = np.clip(_chem_float("Biomass VM Dry wt%"), 0.0, 100.0)
    vm_frac = vm_dry_wt / 100.0
    dt_wgs_c = float(chem.get("TA DeltaT WGS (C)", "0.0"))
    dt_meth_c = float(chem.get("TA DeltaT Meth (C)", "0.0"))
    eta_wgs = np.clip(float(chem.get("WGS Equilibrium Approach Eta", "1.0")), 0.0, 1.0)
    eta_meth = np.clip(float(chem.get("Meth Equilibrium Approach Eta", "1.0")), 0.0, 1.0)
    dt_ox_co_c = float(chem.get("TA DeltaT OxCO (C)", "0.0"))
    dt_ox_h2_c = float(chem.get("TA DeltaT OxH2 (C)", "0.0"))
    dt_ox_ch4_c = float(chem.get("TA DeltaT OxCH4 (C)", "0.0"))
    tar_fuel_type = chem.get("Tar Fuel Type", "biomass").strip().lower()
    tar_internal_flag = chem.get("Tar Internal Path", "off").strip().lower() in ("on", "true", "1", "yes")
    pyro_tar_c_frac = float(chem.get("Pyrolysis Tar Carbon Frac", "0.0"))
    p_bar = float(specs.get("SYSTEM_P_BAR", 15.0))
    t_inci_k = float(specs.get("INCI_T_C", 900.0)) + CELSIUS_TO_KELVIN_OFFSET
    t_slag_k = float(specs.get("SLAG_T_C", 800.0)) + CELSIUS_TO_KELVIN_OFFSET
    t_pox_k = float(specs.get("RGPOX_T_C", 1400.0)) + CELSIUS_TO_KELVIN_OFFSET
    inci_c_conv = INCI_C_CONVERSION
    pox_c_conv = np.clip(float(specs.get("RGPOX_C_CONV", 1.0)), 0.0, 1.0)
    ash_to_slag = np.clip(float(specs.get("ASH_TO_SLAG_FRAC", 0.60)), 0.0, 1.0)
    char_to_slag = np.clip(float(specs.get("CHAR_TO_SLAG_FRAC", 0.55)), 0.0, 1.0)

    inci_inlet_elem, ash_kg_h = _build_inci_elemental_inlet(feed, sample, chem)
    total_inlet_elem = _build_total_system_inlet_elements(inci_inlet_elem, feed, o2_purity)
    o2_in_parts = _inci_o2_species_kg_h(feed, chem)
    co2_in_kg_h = feed.get("CO2IN", 0.0) + feed.get("CIN", 0.0)

    biomass_elem = biomass_to_elemental_moles(sample, feed.get("Biomass", 0.0))
    biomass_moisture_kg_h = feed.get("Biomass", 0.0) * BIOMASS_SAMPLES[sample].mad_pct / 100.0
    biomass_moisture_h2o_mol_h = _kg_to_mol_h(biomass_moisture_kg_h, 18.015)
    biomass_vm_elem = {
        "C": biomass_elem["C"] * vm_frac,
        "H": biomass_elem["H"],
        "O": biomass_elem["O"],
        "N": biomass_elem["N"],
        "S": biomass_elem["S"],
    }
    biomass_nonvm_elem = {
        "C": max(biomass_elem["C"] - biomass_vm_elem["C"], 0.0),
        "H": 0.0,
        "O": 0.0,
        "N": 0.0,
        "S": 0.0,
    }
    pyro_split = allocate_pyrolysis_products_elemental(
        nC=biomass_vm_elem["C"],
        nH=biomass_vm_elem["H"],
        nO=biomass_vm_elem["O"],
        nN=biomass_vm_elem["N"],
        nS=biomass_vm_elem["S"],
        tar_carbon_frac=pyro_tar_c_frac,
        target_tar_hc_ratio=tar_hc,
        tar_fuel_type=tar_fuel_type,
        include_tar_internal=tar_internal_flag,
        scheme=pyro_scheme,
        tar_outlet_mass_kg_h=tar_yield_mass_kg_h,
        nh3_frac_of_n=nh3_frac,
        s_release_frac=s_release_frac,
        h2s_split=h2s_split,
    )

    inci_external = {
        "C": _kg_to_mol_h(co2_in_kg_h, 44.009),
        "H": 2.0 * (_kg_to_mol_h(feed.get("H2OIN", 0.0), 18.015) + biomass_moisture_h2o_mol_h),
        "O": 2.0 * _kg_to_mol_h(o2_in_parts.get("O2", 0.0), 31.998)
        + (_kg_to_mol_h(feed.get("H2OIN", 0.0), 18.015) + biomass_moisture_h2o_mol_h)
        + 2.0 * _kg_to_mol_h(co2_in_kg_h, 44.009),
        "N": max(inci_inlet_elem["N"] - biomass_elem["N"], 0.0),
        "Ar": inci_inlet_elem["Ar"] - biomass_elem["Ar"],
    }
    inci_from_pyro = elemental_totals_from_species(pyro_split.volatile_species_mol_h, ["C", "H", "O", "N", "Ar"])
    char_pool = pyro_split.char_carbon_mol_h + biomass_nonvm_elem["C"]
    reactive_char = char_pool * inci_c_conv
    char_after_inci = max(char_pool - reactive_char, 0.0)

    # INCI Gibbs feed assembled from volatile release + external oxidants + reactive char fraction.
    inci_elem = {
        "C": inci_from_pyro["C"] + reactive_char + _kg_to_mol_h(co2_in_kg_h, 44.009),
        "H": inci_from_pyro["H"] + inci_external["H"],
        "O": inci_from_pyro["O"] + inci_external["O"],
        "N": inci_from_pyro["N"] + inci_external["N"],
        "Ar": inci_from_pyro["Ar"] + inci_external["Ar"],
        "S": biomass_vm_elem["S"],
    }
    inci_major = solve_gibbs_major(inci_elem, MAJOR_SPECIES, t_inci_k, p_bar)
    h2o_after_gibbs_mol_h = max(inci_major.species_flow_mol_h.get("H2O", 0.0), 0.0)
    inci_major_flow = _apply_inci_temperature_approach(
        dict(inci_major.species_flow_mol_h),
        t_gibbs_k=t_inci_k,
        p_bar=p_bar,
        dt_wgs_c=dt_wgs_c,
        dt_meth_c=dt_meth_c,
        eta_wgs=eta_wgs,
        eta_meth=eta_meth,
        dt_ox_co_c=dt_ox_co_c,
        dt_ox_h2_c=dt_ox_h2_c,
        dt_ox_ch4_c=dt_ox_ch4_c,
    )
    h2o_after_ta_mol_h = max(inci_major_flow.get("H2O", 0.0), 0.0)
    inci_feed_n2, inci_feed_ar = _feed_inert_moles(feed, chem)
    inci_major_flow, inci_minor = _allocate_trace_species_from_biomass(
        inci_major_flow,
        biomass_s_mol_h=biomass_elem["S"],
        biomass_n_mol_h=biomass_elem["N"],
        feed_n2_mol_h=inci_feed_n2,
        feed_ar_mol_h=inci_feed_ar,
        h2s_split=h2s_split,
        nh3_frac_of_biomass_n=nh3_frac,
        s_release_frac=s_release_frac,
    )
    inci_outlet_flow = {**inci_major_flow, **inci_minor}

    # SLAG section receives char fraction + post feeds.
    char_to_slag_mol = char_after_inci * char_to_slag
    char_to_pox_mol = char_after_inci - char_to_slag_mol
    char_to_slag_kg_h = char_to_slag_mol * 12.011 / 1000.0
    char_to_pox_kg_h = char_to_pox_mol * 12.011 / 1000.0
    ash_slag_kg_h = ash_kg_h * ash_to_slag
    ash_pox_kg_h = ash_kg_h * (1.0 - ash_to_slag)
    slag_elem = {
        "C": char_to_slag_mol,
        "H": 2.0 * _kg_to_mol_h(feed.get("POSTH2O", 0.0), 18.015),
        "O": 2.0 * _kg_to_mol_h(feed.get("POSTO2", 0.0), 31.998)
        + _kg_to_mol_h(feed.get("POSTH2O", 0.0), 18.015)
        + 2.0 * _kg_to_mol_h(feed.get("POSTCO2", 0.0), 44.009),
        "N": 0.0,
        "Ar": 0.0,
    }
    post_o2_mol = _kg_to_mol_h(feed.get("POSTO2", 0.0), 31.998)
    post_n2_imp, post_ar_imp = _o2_impurity_moles(post_o2_mol, o2_purity)
    slag_elem["N"] += 2.0 * post_n2_imp
    slag_elem["Ar"] += post_ar_imp
    # target residual carbon in solids around 10 wt% of (ash + carbon) by reducing reactive C feed.
    target_residual_c_kg_h = ash_slag_kg_h / float(SLAG_CFG["target_residual_c_ash_mass_ratio"])
    target_residual_c_mol = _kg_to_mol_h(target_residual_c_kg_h, ATOMIC_WEIGHT["C"])
    slag_elem["C"] = max(slag_elem["C"] - target_residual_c_mol, 0.0)
    slag_major = solve_gibbs_major(slag_elem, MAJOR_SPECIES, t_slag_k, p_bar)

    # 13LBS-1：去 Unit 14 的渣流（灰分渣 + 目标残碳；与 DBI inci_slag_kg_h 对标）
    slag_to_u14_kg_h = ash_slag_kg_h + target_residual_c_kg_h

    # RGPOX: INCI 主气相进 Gibbs；NH3/H2S/COS 作为微量组分直通（不在 POX 内重分配）
    tar_crack = {
        "C": pyro_split.tar_allocation.carbon_mol_h if tar_internal_flag else 0.0,
        "H": pyro_split.tar_allocation.hydrogen_mol_h if tar_internal_flag else 0.0,
    }
    inci_major_for_pox = {k: inci_outlet_flow.get(k, 0.0) for k in MAJOR_SPECIES}
    inci_trace_minor = {k: inci_outlet_flow.get(k, 0.0) for k in MINOR_SPECIES}
    pox_elem = elemental_totals_from_species(inci_major_for_pox, ["C", "H", "O", "N", "Ar"])
    pox_elem["C"] += char_to_pox_mol * pox_c_conv + tar_crack["C"]
    pox_elem["H"] += tar_crack["H"]
    pox_elem["O"] += 2.0 * _kg_to_mol_h(feed.get("O2POX", 0.0), 31.998)
    pox_o2_mol = _kg_to_mol_h(feed.get("O2POX", 0.0), 31.998)
    pox_n2_imp, pox_ar_imp = _o2_impurity_moles(pox_o2_mol, o2_purity)
    pox_elem["N"] += 2.0 * pox_n2_imp
    pox_elem["Ar"] += pox_ar_imp

    pox_major = solve_gibbs_major(pox_elem, MAJOR_SPECIES, t_pox_k, p_bar)
    pox_major_flow = dict(pox_major.species_flow_mol_h)
    pox_minor = dict(inci_trace_minor)

    # CH4 empirical clamp by temperature.
    ch4_target_lookup = {
        1300.0: float(chem.get("RGPOX CH4 Target @1300C (%)", "0.55")),
        1400.0: float(chem.get("RGPOX CH4 Target @1400C (%)", "0.1")),
        1500.0: float(chem.get("RGPOX CH4 Target @1500C (%)", "0.05")),
    }
    t_c = float(specs.get("RGPOX_T_C", 1400.0))
    if t_c in ch4_target_lookup:
        dry_total = sum(pox_major_flow.get(s, 0.0) for s in MAJOR_SPECIES if s != "H2O")
        target_ch4 = dry_total * ch4_target_lookup[t_c] / 100.0
        delta = pox_major_flow.get("CH4", 0.0) - target_ch4
        if delta > 0.0:
            pox_major_flow["CH4"] = max(target_ch4, 1e-9)
            pox_major_flow["CO"] += delta
            pox_major_flow["H2"] += 3.0 * delta
            pox_major_flow["H2O"] = max(pox_major_flow.get("H2O", 0.0) - delta, 1e-9)

    inci_dry_all = _dry_vol_pct(inci_outlet_flow, list(INCI_DRY_SPECIES))
    inci_vol = {k: inci_dry_all[k] for k in INCI_MAJOR_KEYS}
    inci_dry_full = dict(inci_dry_all)
    inci_wet_all = _wet_vol_pct(inci_outlet_flow, list(INCI_WET_SPECIES))
    inci_wet_vol = {k: inci_wet_all[k] for k in list(INCI_MAJOR_KEYS) + ["H2O"]}
    inci_wet_full = dict(inci_wet_all)
    inci_minor_vol = {k: inci_dry_all[k] for k in MINOR_SPECIES}
    inci_inert_vol = {k: inci_dry_all[k] for k in ("N2", "Ar")}

    pox_outlet_flow = {**pox_major_flow, **pox_minor}
    pox_dry_all = _dry_vol_pct(pox_outlet_flow, list(INCI_DRY_SPECIES))
    pox_vol = {k: pox_dry_all[k] for k in INCI_MAJOR_KEYS}
    pox_wet_all = _wet_vol_pct(pox_outlet_flow, list(INCI_WET_SPECIES))
    pox_wet_vol = {k: pox_wet_all[k] for k in list(INCI_MAJOR_KEYS) + ["H2O"]}
    pox_minor_vol = {k: pox_dry_all[k] for k in MINOR_SPECIES}

    inci_gas_mass_kg_h = species_flow_mass_kg_h(inci_outlet_flow)
    inci_tar_kg_h = tar_allocation_mass_kg_h(pyro_split.tar_allocation)
    inci_top_kg_h = inci_gas_mass_kg_h
    inci_pgi_total_kg_h = inci_gas_mass_kg_h + inci_tar_kg_h
    inci_slag_kg_h = slag_to_u14_kg_h
    pox_gas_kg_h = species_flow_mass_kg_h(pox_outlet_flow)
    pox_ash_kg_h = ash_kg_h * (1.0 - ash_to_slag) + float(RGPOX_CFG["ash_extra_biomass_frac"]) * feed.get("Biomass", 0.0)

    matched_case = _match_reference_case(feed, sample)
    feed_h2o_mol_h = biomass_moisture_h2o_mol_h + _kg_to_mol_h(feed.get("H2OIN", 0.0), 18.015)
    pyro_h2o_mol_h = max(pyro_split.volatile_species_mol_h.get("H2O", 0.0), 0.0)
    dbi_gas_mass = None
    dbi_total_flow = None
    dbi_slag_mass = None
    dbi_h2o_wet = None
    if matched_case:
        expected = REFERENCE_CASES[matched_case]["expected"]
        meta = expected.get("inci_stream_meta", {})
        wet_full = expected.get("inci_comp_wet_full", {})
        dbi_gas_mass = meta.get("gas_flow_kg_h")
        dbi_total_flow = meta.get("total_flow_kg_h")
        dbi_slag_mass = expected.get("inci_slag_kg_h")
        dbi_h2o_wet = wet_full.get("H2O")
    inci_mass_audit = build_inci_mass_audit(
        feed_map=feed,
        inlet_elem=inci_inlet_elem,
        gas_flow_mol_h=inci_outlet_flow,
        char_carbon_mol_h=char_after_inci,
        ash_kg_h=ash_kg_h,
        ash_to_slag_kg_h=ash_slag_kg_h,
        ash_to_pox_kg_h=ash_pox_kg_h,
        char_to_slag_kg_h=char_to_slag_kg_h,
        char_to_pox_kg_h=char_to_pox_kg_h,
        slag_to_u14_kg_h=slag_to_u14_kg_h,
        feed_h2o_mol_h=feed_h2o_mol_h,
        pyro_h2o_mol_h=pyro_h2o_mol_h,
        h2o_after_gibbs_mol_h=h2o_after_gibbs_mol_h,
        h2o_after_ta_mol_h=h2o_after_ta_mol_h,
        wet_species_keys=tuple(INCI_WET_SPECIES),
        tar_mass_kg_h=inci_tar_kg_h,
        tar_allocation=pyro_split.tar_allocation,
        biomass_s_mol_h=biomass_elem["S"],
        s_release_frac=s_release_frac,
        matched_case=matched_case,
        dbi_gas_mass_kg_h=dbi_gas_mass,
        dbi_total_flow_kg_h=dbi_total_flow,
        dbi_slag_mass_kg_h=dbi_slag_mass,
        dbi_h2o_wet_pct=dbi_h2o_wet,
    )

    balance_in = dict(total_inlet_elem)
    out_species = dict(pox_outlet_flow)
    for sp, val in slag_major.species_flow_mol_h.items():
        out_species[sp] = out_species.get(sp, 0.0) + val
    balance_out = elemental_totals_from_species(out_species, ["C", "H", "O", "N", "S", "Ar"])
    balance_out["C"] += target_residual_c_mol + char_to_pox_mol * (1.0 - pox_c_conv)
    solid_s_mol_h = max(biomass_elem["S"], 0.0) * max(0.0, 1.0 - min(max(s_release_frac, 0.0), 1.0))
    balance_out["S"] += solid_s_mol_h
    balance_rows = [
        ElementBalance(el, balance_in.get(el, 0.0), balance_out.get(el, 0.0))
        for el in ["C", "H", "O", "N", "S", "Ar"]
    ]

    unit_trace: List[UnitResult] = [
        UnitResult("Mix1", "ok", "Feed gas merged for INCI", feed.get("O2IN", 0.0) + feed.get("H2OIN", 0.0) + feed.get("N2IN", 0.0) + feed.get("CO2IN", 0.0) + feed.get("CIN", 0.0), feed.get("O2IN", 0.0) + feed.get("H2OIN", 0.0) + feed.get("N2IN", 0.0) + feed.get("CO2IN", 0.0) + feed.get("CIN", 0.0)),
        UnitResult("DECOMP", "ok", "Drying/pyrolysis volatile release + char pool generation", feed.get("Biomass", 0.0), feed.get("Biomass", 0.0)),
        UnitResult(
            "INCI(RGibbs)",
            "ok" if inci_major.success else "warn",
            f"{inci_major.message}; PyroScheme={pyro_scheme}; VM_dry={vm_dry_wt:.1f} wt%; T={t_inci_k-273.15:.1f}C, C_conv={inci_c_conv:.2f} (fixed), trace=biomass S/N balance + feed N2/Ar, TA(WGS,Meth)=({dt_wgs_c:.1f},{dt_meth_c:.1f})C, ETA(WGS,Meth)=({eta_wgs:.2f},{eta_meth:.2f}), TA_OX(CO,H2,CH4)=({dt_ox_co_c:.1f},{dt_ox_h2_c:.1f},{dt_ox_ch4_c:.1f})C; EqBasis: C+H2O<->CO+H2, C+CO2<->2CO, CO+H2O<->CO2+H2, CO+3H2<->CH4+H2O, C+O2->CO2, CO+0.5O2->CO2, H2+0.5O2->H2O, CH4+2O2->CO2+2H2O",
            feed.get("Biomass", 0.0) + feed.get("CIN", 0.0),
            inci_top_kg_h + inci_slag_kg_h,
        ),
        UnitResult("SEP2", "ok", "Gas/tar/ash/char split performed", inci_pgi_total_kg_h + inci_slag_kg_h, inci_pgi_total_kg_h + inci_slag_kg_h),
        UnitResult("SLAGTMZ(RGibbs)", "ok" if slag_major.success else "warn", slag_major.message, feed.get("POSTO2", 0.0) + feed.get("POSTH2O", 0.0) + feed.get("POSTCO2", 0.0) + inci_slag_kg_h, inci_slag_kg_h),
        UnitResult("SEP3", "ok", "Slag gas-solid split applied", inci_slag_kg_h, inci_slag_kg_h),
        UnitResult(
            "TARCOMP",
            "ok",
            f"Tar outlet {inci_tar_kg_h:.2f} kg/h; internal crack path={'on' if tar_internal_flag else 'off'}",
            inci_tar_kg_h,
            inci_tar_kg_h if tar_internal_flag else 0.0,
        ),
        UnitResult("RGPOX(RGibbs)", "ok" if pox_major.success else "warn", pox_major.message, inci_top_kg_h + feed.get("O2POX", 0.0), pox_gas_kg_h + pox_ash_kg_h),
    ]

    rmsd_inci = None
    rmsd_pox = None
    rmsd_inci_wet = None
    rmsd_pox_wet = None
    rmsd_inci_dry_full = None
    rmsd_inci_wet_full = None
    if matched_case:
        expected = REFERENCE_CASES[matched_case]["expected"]
        rmsd_inci = _calc_rmsd_pct(inci_vol, expected["inci_comp"], ["CO", "H2", "CO2", "CH4"])
        rmsd_pox = _calc_rmsd_pct(pox_vol, expected["pox_comp"], ["CO", "H2", "CO2", "CH4"])
        if "inci_comp_wet" in expected:
            wet_keys = list(expected["inci_comp_wet"].keys())
            rmsd_inci_wet = _calc_rmsd_pct(inci_wet_vol, expected["inci_comp_wet"], wet_keys)
        if "pox_comp_wet" in expected:
            wet_keys = list(expected["pox_comp_wet"].keys())
            rmsd_pox_wet = _calc_rmsd_pct(pox_wet_vol, expected["pox_comp_wet"], wet_keys)
        if "inci_comp_dry_full" in expected:
            dry_full_keys = [k for k in expected["inci_comp_dry_full"] if k in inci_dry_full]
            rmsd_inci_dry_full = _calc_rmsd_pct(inci_dry_full, expected["inci_comp_dry_full"], dry_full_keys)
        if "inci_comp_wet_full" in expected:
            wet_full_keys = [
                k
                for k in expected["inci_comp_wet_full"]
                if k in inci_wet_full and k not in INCI_UNMODELLED_WET_SPECIES
            ]
            rmsd_inci_wet_full = _calc_rmsd_pct(inci_wet_full, expected["inci_comp_wet_full"], wet_full_keys)

    rmsd_inci_primary = rmsd_inci_wet if rmsd_inci_wet is not None else rmsd_inci

    return SimulationResult(
        inci_top_kg_h=round(inci_top_kg_h, int(_NUM["mass_round_digits"])),
        inci_tar_kg_h=round(inci_tar_kg_h, int(_NUM["mass_round_digits"])),
        inci_pgi_total_kg_h=round(inci_pgi_total_kg_h, int(_NUM["mass_round_digits"])),
        inci_slag_kg_h=round(inci_slag_kg_h, int(_NUM["mass_round_digits"])),
        pox_gas_kg_h=round(pox_gas_kg_h, int(_NUM["mass_round_digits"])),
        pox_ash_kg_h=round(pox_ash_kg_h, int(_NUM["mass_round_digits"])),
        inci_comp_dry_vol_pct=inci_vol,
        pox_comp_dry_vol_pct=pox_vol,
        inci_comp_wet_vol_pct=inci_wet_vol,
        pox_comp_wet_vol_pct=pox_wet_vol,
        inci_comp_dry_full_vol_pct=inci_dry_full,
        inci_comp_wet_full_vol_pct=inci_wet_full,
        inci_minor_vol_pct=inci_minor_vol,
        inci_inert_dry_vol_pct=inci_inert_vol,
        pox_minor_vol_pct=pox_minor_vol,
        rmsd_inci_pct=rmsd_inci,
        rmsd_pox_pct=rmsd_pox,
        rmsd_inci_wet_pct=rmsd_inci_wet,
        rmsd_pox_wet_pct=rmsd_pox_wet,
        rmsd_inci_dry_full_pct=rmsd_inci_dry_full,
        rmsd_inci_wet_full_pct=rmsd_inci_wet_full,
        rmsd_inci_primary_pct=rmsd_inci_primary,
        unit_trace=unit_trace,
        thermo_trace=build_thermo_call_trace(),
        element_balance=balance_rows,
        inci_mass_audit=inci_mass_audit,
        matched_case=matched_case,
    )
