import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.backend import run_fixed_temperature_simulation
from simulator.data import build_chem_df, build_feed_df, build_specs_df
from simulator.parameters import dbi_rgpox_case1_inlet, model_parameters
from pdf_reference_data import requires_dbi_rgpox_inlet_json


@requires_dbi_rgpox_inlet_json
def test_rgpox_o2pox_feed_matches_dbi_15og1():
    dbi_o2 = dbi_rgpox_case1_inlet()["15OG1"]["total_kg_h"]
    feed_o2 = build_feed_df("Case-1").loc[build_feed_df("Case-1")["Stream"] == "O2POX", "MassFlow_kg_h"].iloc[0]
    assert feed_o2 == dbi_o2


@requires_dbi_rgpox_inlet_json
def test_rgpox_inlet_audit_present_for_case1():
    res = run_fixed_temperature_simulation(
        build_feed_df("Case-1"),
        build_specs_df(),
        build_chem_df("Case-1"),
    )
    audit = res.rgpox_inlet_audit
    assert audit is not None
    assert audit.case_id == "Case-1"
    assert audit.gas_wet_rmsd_pct is not None
    streams = {row.stream_id for row in audit.mass_rows}
    assert "15PGI-1" in streams
    assert "15OG1" in streams


@requires_dbi_rgpox_inlet_json
def test_rgpox_inlet_o2_and_entrained_solid_aligned_case1():
    tol = float(model_parameters()["numerical"]["rgpox_inlet_mass_tol_kg_h"])
    res = run_fixed_temperature_simulation(
        build_feed_df("Case-1"),
        build_specs_df(),
        build_chem_df("Case-1"),
    )
    audit = res.rgpox_inlet_audit
    assert audit is not None
    og = next(r for r in audit.mass_rows if r.stream_id == "15OG1" and r.component == "oxygen_total")
    solid = next(r for r in audit.mass_rows if r.stream_id == "15PGI-1" and r.component == "solid")
    assert abs(og.delta_kg_h) < tol
    assert abs(solid.delta_kg_h) < tol


@requires_dbi_rgpox_inlet_json
def test_rgpox_inlet_gate_passes_after_entrained_solid_fix():
    res = run_fixed_temperature_simulation(
        build_feed_df("Case-1"),
        build_specs_df(),
        build_chem_df("Case-1"),
    )
    audit = res.rgpox_inlet_audit
    assert audit is not None
    assert audit.ready_for_ta_tuning is True
