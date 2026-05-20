import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.backend import run_fixed_temperature_simulation
from simulator.data import build_chem_df, build_feed_df, build_specs_df
from simulator.parameters import model_parameters
from pdf_reference_data import requires_dbi_rgpox_inlet_json


@requires_dbi_rgpox_inlet_json
def test_rgpox_validation_ante_quench_wet_rmsd_case1():
    """Gibbs+TA @1400°C 对标 15PGR-1 反应区湿基（非急冷后 15PGR-2）。"""
    limit = float(model_parameters()["numerical"]["rgpox_validation_wet_rmsd_limit_case1"])
    res = run_fixed_temperature_simulation(
        build_feed_df("Case-1"),
        build_specs_df(),
        build_chem_df("Case-1"),
    )
    assert res.rmsd_pox_wet_ante_pct is not None
    assert res.rmsd_pox_primary_pct == res.rmsd_pox_wet_ante_pct
    assert res.rmsd_pox_wet_ante_pct < limit
    assert res.pox_comp_wet_ante_vol_pct["H2O"] < res.pox_comp_wet_vol_pct["H2O"]
    assert res.rgpox_inlet_audit is not None
    assert res.rgpox_inlet_audit.ready_for_ta_tuning


def test_rgpox_ta_params_in_unit_trace():
    res = run_fixed_temperature_simulation(
        build_feed_df("Case-1"),
        build_specs_df(),
        build_chem_df("Case-1"),
    )
    notes = next(row.notes for row in res.unit_trace if row.unit_name == "RGPOX(RGibbs)")
    assert "TA(WGS,Meth)" in notes


def test_rgpox_pox_ash_still_matches_dbi():
    res = run_fixed_temperature_simulation(
        build_feed_df("Case-1"),
        build_specs_df(),
        build_chem_df("Case-1"),
    )
    assert abs(res.pox_ash_kg_h - 73.33) < 1.0
