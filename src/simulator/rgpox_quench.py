"""RGPOX 急冷段：无反应，干气组成不变，按饱和湿度更新 H2O。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from .parameters import QUENCH_CFG, RGPOX_T_C
from .quench_syngas import (
    QuenchSyngasState,
    evaluate_quench_wet_inlet,
    mol_h_to_nm3_h,
    solve_outlet_t_for_wet_h2o_pct,
    solve_wet_syngas_temperature_after_quench,
    wet_h2o_mole_fraction,
)


@dataclass
class RgpoxQuenchResult:
    flow_mol_h_post: Dict[str, float]
    t_out_c: float
    y_h2o: float
    h2o_added_mol_h: float
    h2o_added_kg_h: float
    mode: str
    quench_state: Optional[QuenchSyngasState] = None

    @property
    def delta_q_kj_h(self) -> float | None:
        if self.quench_state is None:
            return None
        return self.quench_state.delta_Q_kj_h


def _dry_mol_h(flow_mol_h: Dict[str, float], species: Iterable[str]) -> float:
    return sum(max(float(flow_mol_h.get(sp, 0.0)), 0.0) for sp in species if sp != "H2O")


def _resolve_outlet_t_c(cfg: Dict[str, object], p_mpa: float) -> float:
    """15PGR-2 出口 T；优先显式 outlet_t_c，其次才用 outlet_h2o_wet_pct 反求（标定捷径）。"""
    if cfg.get("outlet_t_c") is not None:
        return float(cfg["outlet_t_c"])
    target = cfg.get("outlet_h2o_wet_pct")
    if target is not None:
        return solve_outlet_t_for_wet_h2o_pct(
            float(target),
            p_mpa,
            T_bracket_low_c=float(cfg.get("T_bracket_low_c", 100.0)),
            T_bracket_high_c=float(cfg.get("T_bracket_high_c", 200.0)),
        )
    raise ValueError("quench 配置需 outlet_t_c（推荐，T+P→Psat/P）或 outlet_h2o_wet_pct（反求 T）")


def apply_rgpox_quench(
    flow_mol_h: Dict[str, float],
    *,
    species: Iterable[str],
    t_gas_in_c: float | None = None,
    p_mpa_abs: float | None = None,
    cfg: Dict[str, object] | None = None,
) -> RgpoxQuenchResult:
    """
    将 15PGR-1 反应区物流经急冷变为 15PGR-2 湿煤气（无化学反应）。

    气相水量（水气比）由 **15PGR-2 出口 T、绝压 P** 下饱和蒸气压决定：
    y_H2O = P_sat(T_out) / P_abs → n_H2O,gas = n_dry · y / (1−y)。
    默认 ``outlet_t_c`` + ``p_total_mpa_abs`` 正向计算；``outlet_h2o_wet_pct`` 仅作反求 T 的标定捷径。

    mode:
    - ``saturation_temperature``: outlet_t_c + P → Psat/P → 气相 H2O
    - ``heat_balance``: 热平衡求 T_out（须与 Psat/P 联立，否则 y 与 T 不一致）
    """
    cfg = dict(cfg if cfg is not None else QUENCH_CFG)
    mode = str(cfg.get("mode", "saturation_temperature"))
    p_mpa = float(p_mpa_abs if p_mpa_abs is not None else cfg.get("p_total_mpa_abs", 1.601))
    t_in = float(t_gas_in_c if t_gas_in_c is not None else cfg.get("T_gas_in_celsius", RGPOX_T_C))
    cp_gas = float(cfg.get("cp_gas_kj_nm3_c", 2.31))
    cp_h2o = float(cfg.get("cp_h2o_vapor_kj_nm3_c", 1.85))
    t_water = float(cfg.get("T_water_in_celsius", 42.0))
    water_flow = cfg.get("cooling_water_mass_flow_kg_h")
    water_flow_kg_h = None if water_flow is None else float(water_flow)

    n_dry = _dry_mol_h(flow_mol_h, species)
    n_h2o_in = max(float(flow_mol_h.get("H2O", 0.0)), 0.0)
    v_dry = mol_h_to_nm3_h(n_dry)
    v_h2o_in = mol_h_to_nm3_h(n_h2o_in)

    if mode == "heat_balance":
        t_out, quench_state = solve_wet_syngas_temperature_after_quench(
            v_dry,
            t_in,
            p_mpa,
            cp_gas,
            V_h2o_in_nm3_h=v_h2o_in,
            cp_h2o_vapor_kj_nm3_c=cp_h2o,
            T_water_in_celsius=t_water,
            water_inlet_saturated_liquid=bool(cfg.get("water_inlet_saturated_liquid", False)),
            cooling_water_mass_flow_kg_h=water_flow_kg_h,
            T_bracket_low_c=float(cfg.get("T_bracket_low_c", 100.0)),
            T_bracket_high_c=float(cfg.get("T_bracket_high_c", 250.0)),
        )
    elif mode == "saturation_temperature":
        t_out = _resolve_outlet_t_c(cfg, p_mpa)
        quench_state = evaluate_quench_wet_inlet(
            t_out,
            v_dry,
            t_in,
            p_mpa,
            cp_gas,
            V_h2o_in_nm3_h=v_h2o_in,
            cp_h2o_vapor_kj_nm3_c=cp_h2o,
            T_water_in_celsius=t_water,
            water_inlet_saturated_liquid=bool(cfg.get("water_inlet_saturated_liquid", False)),
            cooling_water_mass_flow_kg_h=water_flow_kg_h,
        )
    else:
        raise ValueError(f"未知 quench mode: {mode}")

    y = wet_h2o_mole_fraction(t_out, p_mpa)
    n_h2o_out = n_dry * y / (1.0 - y) if n_dry > 0 else 0.0
    n_h2o_add = max(n_h2o_out - n_h2o_in, 0.0)

    post = {sp: max(float(flow_mol_h.get(sp, 0.0)), 0.0) for sp in species if sp != "H2O"}
    post["H2O"] = n_h2o_out

    return RgpoxQuenchResult(
        flow_mol_h_post=post,
        t_out_c=t_out,
        y_h2o=y,
        h2o_added_mol_h=n_h2o_add,
        h2o_added_kg_h=n_h2o_add * 18.015 / 1000.0,
        mode=mode,
        quench_state=quench_state,
    )
