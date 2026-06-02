import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdf_reference_data import requires_inci_streams_csv

from simulator.backend import run_fixed_temperature_simulation
from simulator.data import REFERENCE_CASES, build_chem_df, build_feed_df, build_specs_df


def test_inci_stage_element_balance_tight_for_case1():
    res = run_fixed_temperature_simulation(build_feed_df("Case-1"), build_specs_df(), build_chem_df("Case-1"))
    audit = res.inci_mass_audit
    assert audit is not None
    by_el = {row.element: row.rel_error_pct for row in audit.element_balance}
    assert by_el["C"] < 0.01
    assert by_el["H"] < 0.4
    assert by_el["O"] < 0.01
    assert by_el["N"] < 0.01
    assert by_el["S"] < 0.01


def test_inci_mass_closure_includes_bottom_solids_case1():
    res = run_fixed_temperature_simulation(build_feed_df("Case-1"), build_specs_df(), build_chem_df("Case-1"))
    audit = res.inci_mass_audit
    assert audit is not None
    assert audit.mass_closure_rel_err_pct < 0.05
    assert audit.reactor_out_total_kg_h == pytest.approx(
        audit.pgi_total_kg_h + audit.bottom_solids_kg_h, abs=0.01
    )
    assert audit.bottom_solids_kg_h == pytest.approx(audit.ash_mass_kg_h + audit.char_mass_kg_h, abs=0.01)
    assert audit.slag_to_u14_kg_h == pytest.approx(res.inci_slag_kg_h, rel=1e-9)
    assert audit.slag_to_u14_kg_h == pytest.approx(110.0, abs=0.5)


def test_inci_gas_mass_from_species_not_proxy():
    res = run_fixed_temperature_simulation(build_feed_df("Case-1"), build_specs_df(), build_chem_df("Case-1"))
    audit = res.inci_mass_audit
    assert audit is not None
    assert res.inci_top_kg_h == pytest.approx(audit.gas_mass_kg_h, rel=1e-9)
    assert res.inci_top_kg_h > 6300.0
    assert res.inci_top_kg_h < 6700.0


@requires_inci_streams_csv
def test_h2o_budget_shows_ta_consumption_case1():
    res = run_fixed_temperature_simulation(build_feed_df("Case-1"), build_specs_df(), build_chem_df("Case-1"))
    audit = res.inci_mass_audit
    assert audit is not None
    steps = {row.step: row.h2o_mol_h for row in audit.h2o_budget}
    assert steps["Gibbs 平衡后 H2O"] > steps["TA (WGS/甲烷化) 后 H2O"]
    assert audit.h2o_wet_pct_model == pytest.approx(res.inci_comp_wet_vol_pct["H2O"], abs=0.05)
    assert audit.dbi_h2o_wet_pct == pytest.approx(20.25, abs=0.01)
    gap_row = audit.h2o_budget[-1]
    assert "DBI 对标所需 H2O" in gap_row.step
    assert gap_row.note is not None
    assert "缺口" in gap_row.note
    # Phase 3A 后模型湿基 H2O 可能高于 DBI 目标，预算行应如实反映缺口正负
    assert gap_row.h2o_mol_h != steps["INCI 出口气相 H2O"]


def test_stream_ledger_lists_pfd_streams():
    res = run_fixed_temperature_simulation(build_feed_df("Case-1"), build_specs_df(), build_chem_df("Case-1"))
    audit = res.inci_mass_audit
    assert audit is not None
    ids = {row.stream_id for row in audit.stream_ledger}
    assert "13PGI-1" in ids
    assert "13LBS-1" in ids
    assert "SEP2-bottom" in ids
