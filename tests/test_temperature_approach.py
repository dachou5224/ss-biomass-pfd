import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.backend import run_fixed_temperature_simulation
from simulator.data import build_chem_df, build_feed_df, build_specs_df


def _set_chem_value(df: pd.DataFrame, field: str, value: float) -> pd.DataFrame:
    out = df.copy()
    out.loc[out["Field"] == field, "Value"] = value
    return out


def test_meth_approach_reduces_ch4_from_gibbs_baseline():
    feed_df = build_feed_df("Case-1")
    specs_df = build_specs_df()
    chem_default = build_chem_df("Case-1")
    chem_no_meth = _set_chem_value(chem_default, "Meth Equilibrium Approach Eta", 0.0)
    chem_no_meth = _set_chem_value(chem_no_meth, "TA DeltaT Meth (C)", 0.0)
    chem_no_meth = _set_chem_value(chem_no_meth, "TA DeltaT WGS (C)", 0.0)
    chem_no_meth = _set_chem_value(chem_no_meth, "WGS Equilibrium Approach Eta", 0.0)
    chem_meth = _set_chem_value(chem_default, "Meth Equilibrium Approach Eta", 0.7)
    chem_meth = _set_chem_value(chem_meth, "TA DeltaT Meth (C)", 375.0)
    chem_meth = _set_chem_value(chem_meth, "TA DeltaT WGS (C)", 70.0)

    res_no_meth = run_fixed_temperature_simulation(feed_df, specs_df, chem_no_meth)
    res_meth = run_fixed_temperature_simulation(feed_df, specs_df, chem_meth)

    assert res_meth.inci_comp_wet_vol_pct["CH4"] < res_no_meth.inci_comp_wet_vol_pct["CH4"]
    assert res_meth.rmsd_inci_wet_pct is not None
    assert res_meth.rmsd_inci_wet_pct < res_no_meth.rmsd_inci_wet_pct


def test_temperature_approach_knobs_change_inci_composition():
    specs_df = build_specs_df()
    changed = False
    for case_id in ("Case-1", "Case-2", "Case-3"):
        feed_df = build_feed_df(case_id)
        chem_base = build_chem_df(case_id)
        chem_base = _set_chem_value(chem_base, "Meth Equilibrium Approach Eta", 0.0)
        chem_base = _set_chem_value(chem_base, "TA DeltaT Meth (C)", 0.0)
        res_base = run_fixed_temperature_simulation(feed_df, specs_df, chem_base)
        chem_ta = _set_chem_value(chem_base, "Meth Equilibrium Approach Eta", 0.7)
        chem_ta = _set_chem_value(chem_ta, "TA DeltaT Meth (C)", 450.0)
        res_ta = run_fixed_temperature_simulation(feed_df, specs_df, chem_ta)
        if res_base.inci_comp_dry_vol_pct != res_ta.inci_comp_dry_vol_pct:
            changed = True
            break
    assert changed


def test_temperature_approach_defaults_use_restricted_equilibrium():
    feed_df = build_feed_df("Case-2")
    specs_df = build_specs_df()
    chem_df = build_chem_df("Case-2")
    res = run_fixed_temperature_simulation(feed_df, specs_df, chem_df)

    inci_notes = [u.notes for u in res.unit_trace if u.unit_name == "INCI(RGibbs)"][0]
    assert "TA(WGS,Meth)=(100.0,425.0)C" in inci_notes
    assert "ETA(WGS,Meth)=(0.85,0.70)" in inci_notes
    assert res.inci_comp_wet_vol_pct["CH4"] < 6.5
    assert res.rmsd_inci_wet_pct is None  # Case-2 无湿基 CSV
    assert res.rmsd_inci_pct is not None
    assert res.rmsd_inci_pct < 3.0
