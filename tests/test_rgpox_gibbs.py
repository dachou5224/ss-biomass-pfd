import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.backend import run_fixed_temperature_simulation
from simulator.data import REFERENCE_CASES, build_chem_df, build_feed_df, build_specs_df
from simulator.parameters import RGPOX_T_C, dbi_rgpox_case1_inlet
from simulator.rgpox import (
    RGPOX_EQUATION_BASIS,
    build_entrained_solid,
    build_rgpox_inlet_bundle,
    compute_pox_ash_kg_h,
    pyrolyze_rgpox_volatiles,
    resolve_entrained_solid,
    solve_rgpox_gibbs_equilibrium,
)
from pdf_reference_data import requires_dbi_rgpox_inlet_json


def test_rgpox_temperature_locked_to_dbi_1400c():
    assert RGPOX_T_C == 1400.0
    result = run_fixed_temperature_simulation(
        build_feed_df("Case-1"),
        build_specs_df(),
        build_chem_df("Case-1"),
    )
    rgpox_trace = next(row for row in result.unit_trace if row.unit_name == "RGPOX(RGibbs)")
    assert "1400.0C" in rgpox_trace.notes or "1400C" in rgpox_trace.notes
    assert "volatile pyro" in rgpox_trace.notes.lower()
    assert "entrained solid" in rgpox_trace.notes.lower()


@requires_dbi_rgpox_inlet_json
def test_rgpox_entrained_solid_matches_dbi_case1():
    basis = REFERENCE_CASES["Case-1"]["expected"]["dbi_inci_boundary_basis"]
    char_to_pox = basis["entrained_solid_carbon_kg_h"]
    ash_to_pox = basis["entrained_solid_total_kg_h"] - char_to_pox
    ent = resolve_entrained_solid(case_id="Case-1", char_to_pox_kg_h=char_to_pox, ash_to_pox_kg_h=ash_to_pox)
    dbi = dbi_rgpox_case1_inlet()["15PGI-1"]
    assert abs(ent.total_kg_h - dbi["solid_kg_h"]) < 0.05
    assert abs(ent.minerals_kg_h - dbi["solid_kg_h"] * 0.2663) < 0.5


@requires_dbi_rgpox_inlet_json
def test_rgpox_pox_ash_matches_dbi_outlet_solid_case1():
    res = run_fixed_temperature_simulation(
        build_feed_df("Case-1"),
        build_specs_df(),
        build_chem_df("Case-1"),
    )
    assert abs(res.pox_ash_kg_h - 73.33) < 1.0


def test_rgpox_volatile_pyrolysis_adds_elements_to_gibbs():
    vol = pyrolyze_rgpox_volatiles(18.49, tar_formula="CHO0.082N0.01", tar_fuel_type="biomass")
    assert vol.tar_mass_kg_h == 18.49
    assert vol.elemental_mol_h["C"] > 0.0
    assert vol.elemental_mol_h["H"] > 0.0
    assert vol.elemental_mol_h["O"] > 0.0

    inci_flow = {"CO": 100.0, "H2": 80.0, "CO2": 20.0, "CH4": 5.0, "H2O": 800.0}
    inci_flow.update({"NH3": 0.5, "H2S": 0.2, "COS": 0.01})
    ent = build_entrained_solid(10.0, carbon_wt_pct_dry=73.37, minerals_wt_pct_dry=26.63)
    bundle = build_rgpox_inlet_bundle(
        inci_flow,
        entrained=ent,
        volatile_pyro=vol,
        char_conversion=1.0,
        o2_pox_mol_h=30.0,
        o2_n2_imp_mol_h=1.0,
        o2_ar_imp_mol_h=0.5,
    )
    stage = solve_rgpox_gibbs_equilibrium(bundle, p_bar=15.0, char_conversion=1.0)
    assert stage.pox_ash_kg_h == compute_pox_ash_kg_h(ent, char_conversion=1.0, char_unreacted_mol_h=stage.char_unreacted_mol_h)
    assert abs(stage.pox_ash_kg_h - ent.minerals_kg_h) < 0.01
    assert bundle.char_gasification is not None
    assert (
        bundle.char_gasification.char_reacted_co2_replace_mol_h > 0.0
        or bundle.char_gasification.char_reacted_steam_mol_h > 0.0
    )


def test_rgpox_equation_basis_in_thermo_trace():
    result = run_fixed_temperature_simulation(
        build_feed_df("Case-1"),
        build_specs_df(),
        build_chem_df("Case-1"),
    )
    rgpox_rows = [row for row in result.thermo_trace if row.get("Module") == "RGPOX (RGibbs)"]
    assert len(rgpox_rows) == 1
    assert "minimum Gibbs" in rgpox_rows[0]["Method"]
    assert result.rmsd_pox_wet_pct is not None
    assert RGPOX_EQUATION_BASIS in next(
        row.notes for row in result.unit_trace if row.unit_name == "RGPOX(RGibbs)"
    )
