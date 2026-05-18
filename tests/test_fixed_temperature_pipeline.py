import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.backend import run_fixed_temperature_simulation
from simulator.data import build_chem_df, build_feed_df, build_specs_df


def _run(case_id: str):
    return run_fixed_temperature_simulation(
        build_feed_df(case_id),
        build_specs_df(),
        build_chem_df(case_id),
    )


def test_cases_return_major_and_minor_outputs():
    for case_id in ("Case-1", "Case-2", "Case-3"):
        res = _run(case_id)
        assert set(res.inci_comp_dry_vol_pct.keys()) == {"CO", "H2", "CO2", "CH4"}
        assert set(res.pox_comp_dry_vol_pct.keys()) == {"CO", "H2", "CO2", "CH4"}
        assert set(res.inci_minor_vol_pct.keys()) == {"H2S", "COS", "NH3"}
        assert set(res.pox_minor_vol_pct.keys()) == {"H2S", "COS", "NH3"}
        assert res.matched_case == case_id


def test_element_balance_is_bounded_for_reference_cases():
    for case_id in ("Case-1", "Case-2", "Case-3"):
        res = _run(case_id)
        by_el = {row.element: row.rel_error_pct for row in res.element_balance}
        assert by_el["C"] < 10.0
        assert by_el["N"] < 1e-6
        assert by_el["S"] < 1e-6
        assert by_el["Ar"] < 1e-6
        assert by_el["H"] < 40.0
        assert by_el["O"] < 40.0
