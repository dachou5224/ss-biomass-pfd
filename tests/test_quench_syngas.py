"""急冷湿合成气：移植自 gasifier-model，含 RGPOX 集成测试。"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.backend import run_fixed_temperature_simulation
from simulator.data import build_chem_df, build_feed_df, build_specs_df
from simulator.parameters import model_parameters
from simulator.quench_syngas import (
    DEFAULT_COOLING_WATER_MASS_FLOW_KG_H,
    evaluate_quench_syngas,
    liquid_water_enthalpy_approx_cp,
    solve_outlet_t_for_wet_h2o_pct,
    solve_wet_syngas_temperature_after_quench,
)
from simulator.rgpox_quench import apply_rgpox_quench


def test_trial_175c_matches_excel_magnitude():
    st = evaluate_quench_syngas(
        175.0,
        V_dry_nm3_h=5647.0,
        T_gas_in_celsius=1397.0,
        P_total_mpa_abs=1.6013,
        cp_gas_kj_nm3_c=2.31,
        T_water_in_celsius=42.0,
        cooling_water_mass_flow_kg_h=DEFAULT_COOLING_WATER_MASS_FLOW_KG_H,
    )
    assert st.T_water_in_celsius == 42.0
    assert st.H_water_in_kj_kg == liquid_water_enthalpy_approx_cp(42.0)
    assert st.evaporation_within_flow_limit is True
    assert np.isclose(st.Q_release_kj_h, 5647.0 * 2.31 * (1397.0 - 175.0), rtol=1e-9)
    assert 0.8e6 < st.delta_Q_kj_h < 1.2e6
    assert 0.54 < st.y_h2o < 0.57


def test_wet_inlet_quench_solve_residual():
    v_dry = 5647.0
    y_in = 0.2655
    n_dry = v_dry / 22.414
    v_h2o_in = n_dry * y_in / (1 - y_in) * 22.414
    T_out, st = solve_wet_syngas_temperature_after_quench(
        v_dry,
        1400.0,
        1.601,
        2.31,
        V_h2o_in_nm3_h=v_h2o_in,
        cooling_water_mass_flow_kg_h=91855.0,
        T_bracket_low_c=150.0,
        T_bracket_high_c=220.0,
    )
    assert abs(st.delta_Q_kj_h) < 100.0
    assert T_out > 160.0


def test_outlet_t_for_dbi_h2o_case1():
    t = solve_outlet_t_for_wet_h2o_pct(39.033, 1.601)
    assert 159.0 < t < 162.0


def test_rgpox_quench_dry_species_unchanged():
    flow = {"CO": 100.0, "H2": 80.0, "CO2": 50.0, "CH4": 1.0, "H2O": 40.0, "N2": 10.0}
    cfg = {
        "mode": "saturation_temperature",
        "p_total_mpa_abs": 1.601,
        "outlet_h2o_wet_pct": 39.033,
        "cp_gas_kj_nm3_c": 2.31,
        "T_water_in_celsius": 42.0,
        "cooling_water_mass_flow_kg_h": 91855.0,
    }
    res = apply_rgpox_quench(flow, species=list(flow.keys()) + ["Ar", "H2S"], cfg=cfg)
    for sp in ("CO", "H2", "CO2", "CH4", "N2"):
        assert res.flow_mol_h_post[sp] == flow[sp]
    assert res.flow_mol_h_post["H2O"] > flow["H2O"]
    assert abs(res.y_h2o * 100 - 39.033) < 0.05


def test_rgpox_validation_post_quench_wet_rmsd_case1():
    limit = float(model_parameters()["numerical"]["rgpox_validation_wet_post_quench_rmsd_limit_case1"])
    res = run_fixed_temperature_simulation(
        build_feed_df("Case-1"),
        build_specs_df(),
        build_chem_df("Case-1"),
    )
    assert res.quench_t_out_c is not None
    assert res.quench_h2o_added_kg_h is not None
    assert res.rmsd_pox_wet_pct is not None
    assert res.rmsd_pox_wet_pct < limit
    wet = res.pox_comp_wet_vol_pct
    assert abs(wet["H2O"] - 39.033) < 0.15
