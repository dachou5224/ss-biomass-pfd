import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.backend import run_fixed_temperature_simulation
from simulator.data import build_chem_df, build_feed_df, build_specs_df
from simulator.parameters import model_parameters


def test_inci_validation_metric_present_for_reference_cases():
    mp = model_parameters()
    wet_limit = float(mp["numerical"]["inci_validation_wet_rmsd_limit_case1"])

    # DBI 湿基 stream table 仅 Case-1；Case-2/3 搁置，不测湿基 RMSD
    case1 = run_fixed_temperature_simulation(
        build_feed_df("Case-1"),
        build_specs_df(),
        build_chem_df("Case-1"),
    )
    assert case1.rmsd_inci_wet_pct is not None
    assert case1.rmsd_inci_primary_pct == case1.rmsd_inci_wet_pct
    assert case1.rmsd_inci_wet_pct < wet_limit
    assert case1.matched_case == "Case-1"

    for case_id in ("Case-2", "Case-3"):
        result = run_fixed_temperature_simulation(
            build_feed_df(case_id),
            build_specs_df(),
            build_chem_df(case_id),
        )
        assert result.rmsd_inci_pct is not None
        assert result.rmsd_inci_wet_pct is None
        assert result.matched_case == case_id


def test_inci_equation_basis_is_exposed_in_thermo_trace():
    result = run_fixed_temperature_simulation(
        build_feed_df("Case-1"),
        build_specs_df(),
        build_chem_df("Case-1"),
    )
    modules = {row["Module"] for row in result.thermo_trace}
    assert "INCI Equation Basis" in modules
    assert "INCI Oxidation Stage" in modules
