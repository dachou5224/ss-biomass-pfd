import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.data import REFERENCE_CASES
from simulator.inci_conversion import (
    InciFlyAshSlagParams,
    resolve_inci_char_for_overall_biomass_conversion,
    resolve_inci_solid_routing,
    resolve_inci_solid_routing_fly_ash_ratio,
)
from simulator.backend import run_fixed_temperature_simulation
from simulator.web_ui import default_inputs, build_chem_df_from_inputs, build_feed_df_from_inputs, build_specs_df_from_inputs


def test_overall_target_maps_to_effective_char_conversion():
    target = resolve_inci_char_for_overall_biomass_conversion(
        biomass_total_c_mol_h=100.0,
        char_pool_c_mol_h=25.0,
        target_conversion=0.9,
    )

    assert target.residual_char_mol_h == pytest.approx(10.0)
    assert target.reactive_char_mol_h == pytest.approx(15.0)
    assert target.effective_char_conversion == pytest.approx(0.6)


def test_overall_target_cannot_create_extra_conversion_when_nonchar_is_already_high():
    target = resolve_inci_char_for_overall_biomass_conversion(
        biomass_total_c_mol_h=100.0,
        char_pool_c_mol_h=20.0,
        target_conversion=0.5,
    )

    assert target.residual_char_mol_h == pytest.approx(20.0)
    assert target.reactive_char_mol_h == pytest.approx(0.0)
    assert target.effective_char_conversion == pytest.approx(0.0)


def test_fly_ash_ratio_reproduces_case1_dbi_stream_table_solids():
    basis = REFERENCE_CASES["Case-1"]["expected"]["dbi_inci_boundary_basis"]
    biomass_c_mol_h = basis["biomass_carbon_in_kg_h"] * 1000.0 / 12.011
    routing = resolve_inci_solid_routing_fly_ash_ratio(
        biomass_total_c_mol_h=biomass_c_mol_h,
        char_pool_c_mol_h=biomass_c_mol_h,
        target_conversion=basis["overall_biomass_carbon_conversion_pct"] / 100.0,
        fly_ash_params=InciFlyAshSlagParams(
            fly_ash_to_slag_mass_ratio=275.3 / 110.0,
            fly_ash_residual_carbon_wt_pct_dry=73.37,
            slag_residual_carbon_wt_pct_dry=0.0,
        ),
    )

    assert routing.char_to_pox_kg_h == pytest.approx(basis["entrained_solid_carbon_kg_h"], abs=0.05)
    assert routing.ash_to_pox_kg_h == pytest.approx(
        basis["entrained_solid_total_kg_h"] - basis["entrained_solid_carbon_kg_h"],
        abs=0.05,
    )
    assert routing.slag_to_u14_kg_h == pytest.approx(110.0, abs=0.1)
    assert routing.fly_ash_to_slag_mass_ratio == pytest.approx(275.3 / 110.0, rel=1e-3)
    assert routing.char_to_slag_kg_h == pytest.approx(0.0, abs=1e-9)


def test_dbi_boundary_mode_overrides_inci_solid_routing():
    routing = resolve_inci_solid_routing(
        biomass_total_c_mol_h=100.0,
        char_pool_c_mol_h=1000.0,
        ash_kg_h=12.0,
        target_conversion=0.9,
        ash_to_slag_frac=0.6,
        char_to_slag_frac=0.55,
        slag_residual_c_ash_mass_ratio=9.0,
        solid_routing_mode="DBI Boundary",
        dbi_boundary_basis={
            "bottom_slag_carbon_kg_h": 1.0,
            "bottom_slag_total_kg_h": 6.0,
            "entrained_solid_carbon_kg_h": 4.0,
            "entrained_solid_total_kg_h": 7.0,
        },
    )

    assert routing.char_to_slag_kg_h == pytest.approx(1.0)
    assert routing.char_to_pox_kg_h == pytest.approx(4.0)
    assert routing.ash_to_slag_kg_h == pytest.approx(5.0)
    assert routing.ash_to_pox_kg_h == pytest.approx(3.0)
    assert routing.effective_ash_kg_h == pytest.approx(8.0)
    assert routing.target_residual_c_kg_h == pytest.approx(1.0)
    assert routing.slag_to_u14_kg_h == pytest.approx(6.0)


def test_case1_default_fly_ash_ratio_matches_dbi_stream_table():
    inputs = default_inputs("Case-1")
    res = run_fixed_temperature_simulation(
        build_feed_df_from_inputs(inputs),
        build_specs_df_from_inputs(inputs),
        build_chem_df_from_inputs(inputs),
    )
    basis = REFERENCE_CASES["Case-1"]["expected"]["dbi_inci_boundary_basis"]
    audit = res.inci_mass_audit
    assert audit is not None
    assert audit.solid_routing_mode == "Fly Ash Ratio"
    assert audit.char_to_pox_kg_h == pytest.approx(basis["entrained_solid_carbon_kg_h"], abs=1e-2)
    assert audit.ash_to_pox_kg_h == pytest.approx(
        basis["entrained_solid_total_kg_h"] - basis["entrained_solid_carbon_kg_h"],
        abs=1e-2,
    )
    assert res.inci_slag_kg_h == pytest.approx(110.0, abs=0.2)
    assert audit.fly_ash_to_slag_ratio == pytest.approx(275.3 / 110.0, rel=1e-3)
