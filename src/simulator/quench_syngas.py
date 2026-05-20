"""
激冷后湿合成气平衡温度计算（干气显热 vs 蒸发吸热）

移植自 gasifier-model/src/gasifier/quench_syngas.py，与常见 Excel 单变量求解一致：
- 假定出口温度 Tout，由饱和关系得 y_H2O = P_sat(Tout) / P_total
- 干气流量 Vdry 不变，蒸发水量使湿基水蒸气摩尔分数达到 y_H2O
- Q_release = Vdry * Cp_gas * (T_gas_in - Tout)
- Q_absorb = m_H2O * (H_vapor(Tout) - H_water_in)
- 平衡时 ΔQ = Q_release - Q_absorb = 0

RGPOX 反应区出口已含 H2O 时，见 ``evaluate_quench_wet_inlet`` / ``rgpox_quench``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import numpy as np
from scipy.optimize import brentq

NM3_PER_KMOL = 22.414
M_H2O = 18.015

_T_C = np.array(
    [
        0, 20, 40, 60, 80, 100, 120, 140, 150, 160, 170, 175, 180, 190, 200,
        210, 220, 230, 240, 250, 260, 270, 280, 290, 300, 310, 320, 330, 340, 350,
    ],
    dtype=float,
)
_P_SAT_MPA = np.array(
    [
        0.0006117, 0.002339, 0.007385, 0.019946, 0.047414, 0.10135, 0.19867,
        0.36154, 0.47616, 0.61823, 0.79219, 0.8928, 1.0028, 1.2546, 1.5549,
        1.9077, 2.3198, 2.8021, 3.3469, 3.9762, 4.6923, 5.4990, 6.4120, 7.4360,
        8.5810, 9.8560, 11.274, 12.845, 14.586, 16.513,
    ],
    dtype=float,
)
_HF_KJKG = np.array(
    [
        0.0, 83.96, 167.57, 251.18, 335.02, 419.1, 503.81, 589.24, 632.28,
        675.62, 719.35, 741.37, 763.43, 807.85, 852.45, 897.76, 943.75, 990.47,
        1037.7, 1085.8, 1134.9, 1185.2, 1236.9, 1290.3, 1345.9, 1404.3, 1466.1,
        1532.4, 1604.3, 1672.9,
    ],
    dtype=float,
)
_HG_KJKG = np.array(
    [
        2501.6, 2538.1, 2574.5, 2609.7, 2643.8, 2676.2, 2706.3, 2733.9, 2746.6,
        2758.2, 2768.4, 2773.4, 2778.1, 2787.6, 2796.4, 2804.2, 2811.2, 2817.2,
        2803.4, 2801.5, 2796.6, 2789.7, 2779.6, 2766.2, 2749.0, 2727.3, 2700.1,
        2665.9, 2622.0, 2563.9,
    ],
    dtype=float,
)

DEFAULT_T_WATER_IN_CELSIUS = 42.0
DEFAULT_COOLING_WATER_MASS_FLOW_KG_H = 80_000.0
DEFAULT_CP_H2O_VAPOR_KJ_NM3_C = 1.85


def liquid_water_enthalpy_approx_cp(T_celsius: float, cp_kj_kg_k: float = 4.18) -> float:
    return cp_kj_kg_k * float(T_celsius)


def saturation_pressure_water_mpa(T_celsius: float) -> float:
    T = float(T_celsius)
    if T < _T_C[0] or T > _T_C[-1]:
        raise ValueError(f"温度 T={T}°C 超出蒸汽表范围 [{_T_C[0]}, {_T_C[-1]}]°C")
    return float(np.interp(T, _T_C, _P_SAT_MPA))


def wet_h2o_mole_fraction(T_celsius: float, P_total_mpa_abs: float) -> float:
    P_tot = float(P_total_mpa_abs)
    if P_tot <= 0:
        raise ValueError("P_total_mpa_abs 必须为正")
    y = saturation_pressure_water_mpa(T_celsius) / P_tot
    return float(np.clip(y, 1e-12, 0.999999))


def saturation_enthalpy_liquid_kj_kg(T_celsius: float) -> float:
    T = float(T_celsius)
    if T < _T_C[0] or T > _T_C[-1]:
        raise ValueError(f"温度 T={T}°C 超出蒸汽表范围 [{_T_C[0]}, {_T_C[-1]}]°C")
    return float(np.interp(T, _T_C, _HF_KJKG))


def saturation_enthalpy_vapor_kj_kg(T_celsius: float) -> float:
    T = float(T_celsius)
    if T < _T_C[0] or T > _T_C[-1]:
        raise ValueError(f"温度 T={T}°C 超出蒸汽表范围 [{_T_C[0]}, {_T_C[-1]}]°C")
    return float(np.interp(T, _T_C, _HG_KJKG))


def resolve_water_inlet_enthalpy_kj_kg(
    T_water_in_celsius: float,
    *,
    H_water_in_kj_kg: Optional[float] = None,
    water_inlet_saturated_liquid: bool = False,
) -> float:
    if H_water_in_kj_kg is not None:
        return float(H_water_in_kj_kg)
    T = float(T_water_in_celsius)
    if water_inlet_saturated_liquid:
        return saturation_enthalpy_liquid_kj_kg(T)
    return liquid_water_enthalpy_approx_cp(T)


def mol_h_to_nm3_h(n_mol_h: float) -> float:
    return float(n_mol_h) / 1000.0 * NM3_PER_KMOL


def nm3_h_to_mol_h(v_nm3_h: float) -> float:
    return float(v_nm3_h) / NM3_PER_KMOL * 1000.0


@dataclass
class QuenchSyngasState:
    T_out_c: float
    P_sat_mpa: float
    y_h2o: float
    V_h2o_nm3_h: float
    m_h2o_kg_h: float
    H_vapor_kj_kg: float
    Q_absorb_kj_h: float
    Q_release_kj_h: float
    delta_Q_kj_h: float
    T_water_in_celsius: float
    H_water_in_kj_kg: float
    cooling_water_mass_flow_kg_h: Optional[float]
    evaporation_within_flow_limit: bool
    m_h2o_added_kg_h: float = 0.0
    n_h2o_in_kmol_h: float = 0.0
    n_h2o_out_kmol_h: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "T_out_C": self.T_out_c,
            "P_sat_MPa_a": self.P_sat_mpa,
            "y_H2O": self.y_h2o,
            "V_H2O_Nm3_h": self.V_h2o_nm3_h,
            "m_H2O_kg_h": self.m_h2o_kg_h,
            "m_H2O_added_kg_h": self.m_h2o_added_kg_h,
            "H_vapor_kJ_kg": self.H_vapor_kj_kg,
            "Q_absorb_kJ_h": self.Q_absorb_kj_h,
            "Q_release_kJ_h": self.Q_release_kj_h,
            "delta_Q_kJ_h": self.delta_Q_kj_h,
            "T_water_in_C": self.T_water_in_celsius,
            "H_water_in_kJ_kg": self.H_water_in_kj_kg,
            "cooling_water_mass_flow_kg_h": self.cooling_water_mass_flow_kg_h,
            "evaporation_within_flow_limit": self.evaporation_within_flow_limit,
            "n_H2O_in_kmol_h": self.n_h2o_in_kmol_h,
            "n_H2O_out_kmol_h": self.n_h2o_out_kmol_h,
        }


def evaluate_quench_syngas(
    T_out_celsius: float,
    V_dry_nm3_h: float,
    T_gas_in_celsius: float,
    P_total_mpa_abs: float,
    cp_gas_kj_nm3_c: float,
    *,
    T_water_in_celsius: float = DEFAULT_T_WATER_IN_CELSIUS,
    H_water_in_kj_kg: Optional[float] = None,
    water_inlet_saturated_liquid: bool = False,
    cooling_water_mass_flow_kg_h: Optional[float] = DEFAULT_COOLING_WATER_MASS_FLOW_KG_H,
) -> QuenchSyngasState:
    """干气进口急冷试算（无进口 H2O）。"""
    return evaluate_quench_wet_inlet(
        T_out_celsius,
        V_dry_nm3_h,
        T_gas_in_celsius,
        P_total_mpa_abs,
        cp_gas_kj_nm3_c,
        V_h2o_in_nm3_h=0.0,
        T_water_in_celsius=T_water_in_celsius,
        H_water_in_kj_kg=H_water_in_kj_kg,
        water_inlet_saturated_liquid=water_inlet_saturated_liquid,
        cooling_water_mass_flow_kg_h=cooling_water_mass_flow_kg_h,
        cp_h2o_vapor_kj_nm3_c=DEFAULT_CP_H2O_VAPOR_KJ_NM3_C,
    )


def evaluate_quench_wet_inlet(
    T_out_celsius: float,
    V_dry_nm3_h: float,
    T_gas_in_celsius: float,
    P_total_mpa_abs: float,
    cp_gas_kj_nm3_c: float,
    *,
    V_h2o_in_nm3_h: float = 0.0,
    cp_h2o_vapor_kj_nm3_c: float = DEFAULT_CP_H2O_VAPOR_KJ_NM3_C,
    T_water_in_celsius: float = DEFAULT_T_WATER_IN_CELSIUS,
    H_water_in_kj_kg: Optional[float] = None,
    water_inlet_saturated_liquid: bool = False,
    cooling_water_mass_flow_kg_h: Optional[float] = DEFAULT_COOLING_WATER_MASS_FLOW_KG_H,
) -> QuenchSyngasState:
    """含进口水蒸气的急冷试算：蒸发量 = 出口饱和量 − 进口 H2O。"""
    T_out = float(T_out_celsius)
    P_tot = float(P_total_mpa_abs)
    if P_tot <= 0:
        raise ValueError("P_total_mpa_abs 必须为正")

    h_w_in = resolve_water_inlet_enthalpy_kj_kg(
        T_water_in_celsius,
        H_water_in_kj_kg=H_water_in_kj_kg,
        water_inlet_saturated_liquid=water_inlet_saturated_liquid,
    )

    y = wet_h2o_mole_fraction(T_out, P_tot)
    P_sat = saturation_pressure_water_mpa(T_out)

    V_dry = float(V_dry_nm3_h)
    V_h2o_in = max(float(V_h2o_in_nm3_h), 0.0)
    n_dry_kmol_h = V_dry / NM3_PER_KMOL
    n_h2o_in_kmol_h = V_h2o_in / NM3_PER_KMOL
    n_h2o_out_kmol_h = n_dry_kmol_h * y / (1.0 - y)
    n_h2o_add_kmol_h = max(n_h2o_out_kmol_h - n_h2o_in_kmol_h, 0.0)

    m_h2o_out = n_h2o_out_kmol_h * M_H2O
    m_h2o_add = n_h2o_add_kmol_h * M_H2O
    V_h2o_out = n_h2o_out_kmol_h * NM3_PER_KMOL

    within_flow = True
    if cooling_water_mass_flow_kg_h is not None:
        fmax = float(cooling_water_mass_flow_kg_h)
        if fmax <= 0:
            raise ValueError("cooling_water_mass_flow_kg_h 必须为正或 None")
        within_flow = m_h2o_add <= fmax + 1e-6

    H_vap = saturation_enthalpy_vapor_kj_kg(T_out)
    Q_abs = m_h2o_add * (H_vap - h_w_in)
    delta_t = float(T_gas_in_celsius) - T_out
    Q_rel = V_dry * float(cp_gas_kj_nm3_c) * delta_t + V_h2o_in * float(cp_h2o_vapor_kj_nm3_c) * delta_t

    return QuenchSyngasState(
        T_out_c=T_out,
        P_sat_mpa=P_sat,
        y_h2o=y,
        V_h2o_nm3_h=V_h2o_out,
        m_h2o_kg_h=m_h2o_out,
        H_vapor_kj_kg=H_vap,
        Q_absorb_kj_h=Q_abs,
        Q_release_kj_h=Q_rel,
        delta_Q_kj_h=Q_rel - Q_abs,
        T_water_in_celsius=float(T_water_in_celsius),
        H_water_in_kj_kg=h_w_in,
        cooling_water_mass_flow_kg_h=cooling_water_mass_flow_kg_h,
        evaporation_within_flow_limit=within_flow,
        m_h2o_added_kg_h=m_h2o_add,
        n_h2o_in_kmol_h=n_h2o_in_kmol_h,
        n_h2o_out_kmol_h=n_h2o_out_kmol_h,
    )


def solve_wet_syngas_temperature_after_quench(
    V_dry_nm3_h: float,
    T_gas_in_celsius: float,
    P_total_mpa_abs: float,
    cp_gas_kj_nm3_c: float,
    *,
    V_h2o_in_nm3_h: float = 0.0,
    cp_h2o_vapor_kj_nm3_c: float = DEFAULT_CP_H2O_VAPOR_KJ_NM3_C,
    T_water_in_celsius: float = DEFAULT_T_WATER_IN_CELSIUS,
    H_water_in_kj_kg: Optional[float] = None,
    water_inlet_saturated_liquid: bool = False,
    cooling_water_mass_flow_kg_h: Optional[float] = DEFAULT_COOLING_WATER_MASS_FLOW_KG_H,
    T_bracket_low_c: float = 50.0,
    T_bracket_high_c: Optional[float] = None,
    xtol: float = 1e-4,
) -> Tuple[float, QuenchSyngasState]:
    T_hi = T_bracket_high_c
    if T_hi is None:
        T_hi = min(float(T_gas_in_celsius) - 0.5, 349.0)
    T_lo = float(T_bracket_low_c)
    if T_lo >= T_hi:
        raise ValueError("温度搜索区间无效：T_bracket_low_c 须小于上界")

    def residual(T: float) -> float:
        st = evaluate_quench_wet_inlet(
            T,
            V_dry_nm3_h,
            T_gas_in_celsius,
            P_total_mpa_abs,
            cp_gas_kj_nm3_c,
            V_h2o_in_nm3_h=V_h2o_in_nm3_h,
            cp_h2o_vapor_kj_nm3_c=cp_h2o_vapor_kj_nm3_c,
            T_water_in_celsius=T_water_in_celsius,
            H_water_in_kj_kg=H_water_in_kj_kg,
            water_inlet_saturated_liquid=water_inlet_saturated_liquid,
            cooling_water_mass_flow_kg_h=cooling_water_mass_flow_kg_h,
        )
        return st.delta_Q_kj_h

    f_lo = residual(T_lo)
    f_hi = residual(T_hi)
    if f_lo * f_hi > 0:
        raise ValueError(
            f"在给定区间 [{T_lo}, {T_hi}] °C 内未找到变号，无法保证存在根。"
            f" f({T_lo})={f_lo:.4g}, f({T_hi})={f_hi:.4g}。"
            "请检查输入或扩大/移动搜索区间。"
        )

    T_root = brentq(residual, T_lo, T_hi, xtol=xtol, rtol=1e-8)
    final = evaluate_quench_wet_inlet(
        T_root,
        V_dry_nm3_h,
        T_gas_in_celsius,
        P_total_mpa_abs,
        cp_gas_kj_nm3_c,
        V_h2o_in_nm3_h=V_h2o_in_nm3_h,
        cp_h2o_vapor_kj_nm3_c=cp_h2o_vapor_kj_nm3_c,
        T_water_in_celsius=T_water_in_celsius,
        H_water_in_kj_kg=H_water_in_kj_kg,
        water_inlet_saturated_liquid=water_inlet_saturated_liquid,
        cooling_water_mass_flow_kg_h=cooling_water_mass_flow_kg_h,
    )
    return float(T_root), final


def solve_outlet_t_for_wet_h2o_pct(
    target_h2o_wet_pct: float,
    P_total_mpa_abs: float,
    *,
    T_bracket_low_c: float = 100.0,
    T_bracket_high_c: float = 200.0,
) -> float:
    """由目标湿基 H2O vol% 反求饱和出口温度。"""
    target = float(target_h2o_wet_pct) / 100.0
    P_tot = float(P_total_mpa_abs)

    def residual(T: float) -> float:
        return wet_h2o_mole_fraction(T, P_tot) - target

    return float(brentq(residual, T_bracket_low_c, T_bracket_high_c, xtol=1e-4, rtol=1e-8))
