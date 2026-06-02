import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.backend import (
    _allocate_trace_species_from_biomass,
    _feed_inert_moles,
    _feed_map,
    run_fixed_temperature_simulation,
)
from simulator.data import REFERENCE_CASES, build_chem_df, build_feed_df, build_specs_df
from simulator.elemental import biomass_to_elemental_moles


def test_allocate_trace_species_from_biomass_element_balance():
    biomass = biomass_to_elemental_moles("8#", 4000.0)
    nh3_frac = 0.016
    s_release = 0.45
    h2s_split = 0.961
    major, minor = _allocate_trace_species_from_biomass(
        {"CO": 1e5, "H2": 1e5, "CO2": 5e4, "CH4": 1e4, "H2O": 5e4, "O2": 0.0, "N2": 0.0, "Ar": 0.0},
        biomass_s_mol_h=biomass["S"],
        biomass_n_mol_h=biomass["N"],
        biomass_cl_mol_h=biomass.get("Cl", 0.0),
        feed_n2_mol_h=5000.0,
        feed_ar_mol_h=100.0,
        h2s_split=h2s_split,
        nh3_frac_of_biomass_n=nh3_frac,
        s_release_frac=s_release,
    )
    s_gas = biomass["S"] * s_release
    assert minor["H2S"] == pytest.approx(s_gas * h2s_split, rel=1e-9)
    assert minor["COS"] == pytest.approx(s_gas * (1.0 - h2s_split), rel=1e-9)
    assert minor["NH3"] == pytest.approx(biomass["N"] * nh3_frac, rel=1e-9)
    assert minor["HCl"] == pytest.approx(biomass.get("Cl", 0.0), rel=1e-9)
    assert major["N2"] == pytest.approx(5000.0 + biomass["N"] * (1.0 - nh3_frac) / 2.0, rel=1e-9)


def test_case1_biomass_cl_routes_to_hcl_in_syngas():
    feed_df = build_feed_df("Case-1")
    feed = _feed_map(feed_df)
    chem = {r.Field: r.Value for _, r in build_chem_df("Case-1").iterrows()}
    sample = REFERENCE_CASES["Case-1"]["sample"]
    biomass = biomass_to_elemental_moles(sample, feed["Biomass"])
    res = run_fixed_temperature_simulation(feed_df, build_specs_df(), build_chem_df("Case-1"))

    assert biomass["Cl"] == pytest.approx(3800.0 * 0.0092 * 1000.0 / 35.453, rel=1e-4)
    assert res.inci_minor_vol_pct["HCl"] > 0.0
    assert res.inci_comp_wet_full_vol_pct.get("HCl", 0.0) > 0.0


def test_inci_trace_species_present_and_dilute_dry_basis():
    feed_df = build_feed_df("Case-1")
    feed = _feed_map(feed_df)
    chem = {r.Field: r.Value for _, r in build_chem_df("Case-1").iterrows()}
    sample = REFERENCE_CASES["Case-1"]["sample"]
    biomass = biomass_to_elemental_moles(sample, feed["Biomass"])
    res = run_fixed_temperature_simulation(feed_df, build_specs_df(), build_chem_df("Case-1"))

    assert res.inci_minor_vol_pct["NH3"] > 0.0
    assert res.inci_minor_vol_pct["H2S"] >= 0.0
    # 生物质 N 大部分→N2，少量→NH3
    assert res.inci_inert_dry_vol_pct["N2"] > 0.5
    assert res.inci_comp_wet_full_vol_pct["NH3"] < 0.05
    assert res.inci_inert_dry_vol_pct["Ar"] > 0.1
    assert (
        sum(res.inci_comp_dry_vol_pct.values())
        + sum(res.inci_minor_vol_pct.values())
        + sum(res.inci_inert_dry_vol_pct.values())
    ) == pytest.approx(100.0, abs=0.05)

    n2_feed, ar_feed = _feed_inert_moles(feed, chem)
    assert n2_feed > 0.0
    assert ar_feed > 0.0
    assert biomass["N"] > 0.0
    assert biomass["S"] > 0.0
