import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.backend import run_fixed_temperature_simulation
from simulator.data import build_chem_df, build_feed_df, build_specs_df
from simulator.parameters import model_parameters
from simulator.ta_tuning import evaluate_inci_wet_rmsd


def test_default_ta_meets_case1_wet_rmsd_target():
    mp = model_parameters()
    limit = float(mp["numerical"]["inci_validation_wet_rmsd_limit_case1"])
    chem = build_chem_df("Case-1")
    res = run_fixed_temperature_simulation(build_feed_df("Case-1"), build_specs_df(), chem)
    assert res.rmsd_inci_wet_pct is not None
    assert res.rmsd_inci_primary_pct == res.rmsd_inci_wet_pct
    assert res.rmsd_inci_wet_pct < limit
    assert res.rmsd_inci_wet_pct < res.rmsd_inci_pct


def test_wet_ta_defaults_improve_over_legacy_aggressive_ta():
    feed = build_feed_df("Case-1")
    specs = build_specs_df()
    base = build_chem_df("Case-1")
    legacy = evaluate_inci_wet_rmsd(
        "Case-1",
        dt_wgs_c=-120.0,
        dt_meth_c=500.0,
        eta_wgs=1.0,
        eta_meth=1.0,
        feed_df=feed,
        specs_df=specs,
        chem_df=base,
    )
    res = run_fixed_temperature_simulation(feed, specs, base)
    assert res.rmsd_inci_wet_pct is not None
    assert res.rmsd_inci_wet_pct < legacy.rmsd_wet_pct
    assert res.inci_comp_wet_vol_pct["H2O"] > legacy.comp_wet_vol_pct["H2O"]
