"""config/*.json 加载与关键参数一致性。"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.data import DEFAULT_CHEMISTRY_SETUP, DEFAULT_REACTOR_SPECS, REFERENCE_CASES
from simulator.elemental import BIOMASS_SAMPLES
from simulator.parameters import (
    INCI_C_CONVERSION,
    dbi_case1_inlet,
    load_json_config,
    model_parameters,
)
from simulator.thermo_baseline import R_CONST, SHOMATE_DB


def test_model_parameters_json_loads_without_comment_keys():
    mp = model_parameters()
    assert "_comment" not in mp
    assert mp["reactor_specs"]["INCI_T_C"] == 900.0
    assert mp["chemistry_setup"]["WGS Equilibrium Approach Eta"] == pytest.approx(0.85)
    assert mp["chemistry_setup"]["Meth Equilibrium Approach Eta"] == pytest.approx(0.7)
    assert mp["chemistry_setup"]["TA DeltaT WGS (C)"] == pytest.approx(100.0)
    assert mp["chemistry_setup"]["TA DeltaT Meth (C)"] == pytest.approx(425.0)
    assert mp["inci_fbr_solids"]["fly_ash_to_slag_mass_ratio"] == pytest.approx(2.5027)


def test_reference_cases_match_legacy_case1_feeds():
    case = REFERENCE_CASES["Case-1"]
    assert case["feeds"]["Biomass"] == (4000.0, 25.0, 15.0)
    assert case["sample"] == "11#"
    exp = case["expected"]
    assert exp["pox_gas_ante_kg_h"] == pytest.approx(7760.0)
    assert exp["pox_gas_kg_h"] == pytest.approx(8843.0)
    mp = model_parameters()
    char_cfg = mp["rgpox"]["char_gasification"]
    assert char_cfg["o2_to_gibbs_mode"] == "full_feed"
    assert char_cfg["reaction_sequence"] == "gas_equilibrium_first"
    assert char_cfg.get("post_char_use_remaining_o2") is False
    assert char_cfg.get("enable_boudouard") is True
    het = char_cfg.get("hetero_ta", {})
    assert het.get("enabled") is True
    assert het.get("dt_boudouard_c") == pytest.approx(-100.0)
    assert mp["chemistry_setup"]["RGPOX TA DeltaT WGS (C)"] == pytest.approx(-160.0)


def test_biomass_and_dbi_inlet_from_config():
    assert "11#" in BIOMASS_SAMPLES
    s11 = BIOMASS_SAMPLES["11#"]
    assert s11.cd_pct_dry == pytest.approx(45.609)
    assert s11.vd_pct_dry == pytest.approx(75.01)
    assert s11.fcd_pct_dry == pytest.approx(16.99)
    s8 = BIOMASS_SAMPLES["8#"]
    assert s8.vd_pct_dry == pytest.approx(77.6)
    assert s8.fcd_pct_dry == pytest.approx(17.64)
    assert s11.cl_pct_dry == pytest.approx(0.92)
    assert s11.ad_pct + s11.vd_pct_dry + s11.fcd_pct_dry == pytest.approx(100.0, abs=0.02)
    assert (
        s11.cd_pct_dry
        + s11.hd_pct_dry
        + s11.nd_pct_dry
        + s11.sd_pct_dry
        + s11.od_pct_dry
        + s11.ad_pct
        + s11.cl_pct_dry
        == pytest.approx(100.0, abs=0.02)
    )
    inlet = dbi_case1_inlet()
    assert inlet["13OG2-1"]["total_kg_h"] == pytest.approx(1343.0)


def test_build_chem_df_vm_fc_follow_sample():
    from simulator.data import build_chem_df

    chem = {r.Field: r.Value for _, r in build_chem_df("Case-1").iterrows()}
    assert chem["Sample"] == "11#"
    assert float(chem["Biomass VM Dry wt%"]) == pytest.approx(75.01)
    assert float(chem["Biomass FC Dry wt%"]) == pytest.approx(16.99)


def test_defaults_wired_to_data_module():
    assert INCI_C_CONVERSION == 0.90
    assert DEFAULT_REACTOR_SPECS["ASH_TO_SLAG_FRAC"] == 0.60
    assert DEFAULT_CHEMISTRY_SETUP["Tar Yield Factor"] == "0.01 * C_dry"


def test_thermo_shomate_has_co():
    assert "CO" in SHOMATE_DB
    assert R_CONST == pytest.approx(8.3144626)


def test_strip_comments_nested():
    raw = load_json_config("model_parameters")
    assert "species" in raw
