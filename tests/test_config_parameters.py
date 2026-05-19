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
    assert mp["chemistry_setup"]["Meth Equilibrium Approach Eta"] == pytest.approx(1.0)
    assert mp["chemistry_setup"]["TA DeltaT WGS (C)"] == pytest.approx(40.0)
    assert mp["chemistry_setup"]["TA DeltaT Meth (C)"] == pytest.approx(350.0)


def test_reference_cases_match_legacy_case1_feeds():
    case = REFERENCE_CASES["Case-1"]
    assert case["feeds"]["Biomass"] == (4000.0, 25.0, 15.0)
    assert case["sample"] == "11#"


def test_biomass_and_dbi_inlet_from_config():
    assert "11#" in BIOMASS_SAMPLES
    assert BIOMASS_SAMPLES["11#"].cd_pct_dry == pytest.approx(45.609)
    inlet = dbi_case1_inlet()
    assert inlet["13OG2-1"]["total_kg_h"] == pytest.approx(1343.0)


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
