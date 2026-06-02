#!/usr/bin/env python3
"""Case-1 激冷室：气液平衡 vs 热平衡诊断（Phase 7）。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import simulator.backend as be  # noqa: E402
from simulator.backend import run_fixed_temperature_simulation  # noqa: E402
from simulator.data import REFERENCE_CASES  # noqa: E402
from simulator.parameters import RGPOX_T_C, model_parameters  # noqa: E402
from simulator.quench_syngas import (  # noqa: E402
    evaluate_quench_wet_inlet,
    mol_h_to_nm3_h,
    resolve_water_inlet_enthalpy_kj_kg,
    saturation_enthalpy_vapor_kj_kg,
)
from simulator.reference_streams import expected_pox_gas_ante_kg_h  # noqa: E402
from simulator.rgpox_quench import apply_rgpox_quench  # noqa: E402
from simulator.species import species_flow_mass_kg_h  # noqa: E402
from simulator.webservice_demo import (  # noqa: E402
    build_chem_df_from_inputs,
    build_feed_df_from_inputs,
    build_specs_df_from_inputs,
    _merge_inputs,
)


def _capture_ante_flow(case_id: str) -> dict:
    captured: dict = {}
    orig = be.apply_rgpox_quench

    def _hook(flow, **kw):
        captured["flow"] = dict(flow)
        return orig(flow, **kw)

    be.apply_rgpox_quench = _hook
    try:
        inputs = _merge_inputs({"case_id": case_id})
        run_fixed_temperature_simulation(
            build_feed_df_from_inputs(inputs),
            build_specs_df_from_inputs(inputs),
            build_chem_df_from_inputs(inputs),
        )
    finally:
        be.apply_rgpox_quench = orig
    return captured["flow"]


def main() -> None:
    case_id = "Case-1"
    exp = REFERENCE_CASES[case_id]["expected"]
    qcfg = dict(model_parameters()["quench"])
    dbi_ante = expected_pox_gas_ante_kg_h(exp)
    dbi_post = float(exp["pox_gas_kg_h"])
    dbi_quench = dbi_post - dbi_ante

    flow = _capture_ante_flow(case_id)
    n_dry = sum(max(flow.get(sp, 0.0), 0.0) for sp in flow if sp != "H2O")
    n_h2o_in = max(flow.get("H2O", 0.0), 0.0)
    v_dry = mol_h_to_nm3_h(n_dry)
    v_h2o_in = mol_h_to_nm3_h(n_h2o_in)

    print("=== Case-1 激冷室热平衡 / 气液平衡诊断 (Phase 7) ===")
    print(f"DBI: 15PGR-1={dbi_ante:.0f}  急冷加水≈{dbi_quench:.0f}  15PGR-2={dbi_post:.0f} kg/h")
    print(f"15PGR-1 干气 V_dry≈{v_dry:,.0f} Nm³/h  进口 H2O V≈{v_h2o_in:,.0f} Nm³/h  T_in={RGPOX_T_C:.0f}°C")

    modes = (
        ("saturation_temperature（当前默认）", dict(qcfg)),
        ("heat_balance（热平衡求 T_out）", {**qcfg, "mode": "heat_balance"}),
    )
    for label, cfg in modes:
        r = apply_rgpox_quench(flow, species=list(flow.keys()), t_gas_in_c=RGPOX_T_C, cfg=cfg)
        st = r.quench_state
        post = species_flow_mass_kg_h(r.flow_mol_h_post)
        print(f"\n--- {label} ---")
        print(
            f"  T_out={r.t_out_c:.2f}°C  y_H2O={r.y_h2o * 100:.3f}%  "
            f"H2O_add={r.h2o_added_kg_h:.1f} kg/h  15PGR-2={post:.0f} kg/h"
        )
        if st:
            print(
                f"  Q_release={st.Q_release_kj_h / 1e6:.2f} MJ/h  "
                f"Q_absorb={st.Q_absorb_kj_h / 1e6:.2f} MJ/h  "
                f"ΔQ={st.delta_Q_kj_h / 1e6:+.2f} MJ/h"
            )

    t_out = float(qcfg.get("outlet_h2o_wet_pct") and 160.384)
    if qcfg.get("outlet_h2o_wet_pct") is not None:
        from simulator.quench_syngas import solve_outlet_t_for_wet_h2o_pct

        t_out = solve_outlet_t_for_wet_h2o_pct(
            float(qcfg["outlet_h2o_wet_pct"]),
            float(qcfg["p_total_mpa_abs"]),
            T_bracket_low_c=float(qcfg.get("T_bracket_low_c", 100.0)),
            T_bracket_high_c=float(qcfg.get("T_bracket_high_c", 200.0)),
        )
    st_sat = evaluate_quench_wet_inlet(
        t_out,
        v_dry,
        RGPOX_T_C,
        float(qcfg["p_total_mpa_abs"]),
        float(qcfg["cp_gas_kj_nm3_c"]),
        V_h2o_in_nm3_h=v_h2o_in,
        T_water_in_celsius=float(qcfg["T_water_in_celsius"]),
        cooling_water_mass_flow_kg_h=float(qcfg["cooling_water_mass_flow_kg_h"]),
    )
    h_vap = saturation_enthalpy_vapor_kj_kg(t_out)
    h_w_in = resolve_water_inlet_enthalpy_kj_kg(float(qcfg["T_water_in_celsius"]))
    m_close = st_sat.Q_release_kj_h / max(h_vap - h_w_in, 1e-6)

    print("\n--- T + P → 饱和 y（15PGR-2 气液平衡）---")
    from simulator.quench_syngas import wet_h2o_mole_fraction

    p_mpa = float(qcfg["p_total_mpa_abs"])
    for t_label, t_c in (("DBI 流股表", 159.0), ("39.033% 反求 T", 160.384)):
        y = wet_h2o_mole_fraction(t_c, p_mpa)
        cfg_tp = {**qcfg, "mode": "saturation_temperature", "outlet_t_c": t_c}
        cfg_tp.pop("outlet_h2o_wet_pct", None)
        r = apply_rgpox_quench(flow, species=list(flow.keys()), t_gas_in_c=RGPOX_T_C, cfg=cfg_tp)
        post = species_flow_mass_kg_h(r.flow_mol_h_post)
        print(
            f"  {t_label}: T={t_c}°C  y={y * 100:.3f}%  H2O_add={r.h2o_added_kg_h:.0f}  "
            f"15PGR-2={post:.0f} kg/h (DBI 8843)"
        )

    print("\n--- 机理注记 ---")
    print("  15PGR-2 出口 T、P 决定气相饱和水：y=P_sat(T)/P，n_H2O,gas=n_dry·y/(1−y)。")
    print("  湿基 H2O% 是 T、P 的结果；Phase 7 应优先 outlet_t_c=159°C + P=1.601 MPa，而非以 H2O% 反推 T。")


if __name__ == "__main__":
    main()
