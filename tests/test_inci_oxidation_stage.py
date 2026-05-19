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


def test_inci_oxidation_ta_knob_changes_inci_composition():
    specs_df = build_specs_df()
    feed_df = build_feed_df("Case-1")
    chem_df = build_chem_df("Case-1")

    chem_with_oxid = _set_chem_value(chem_df, "TA DeltaT OxCO (C)", 120.0)
    chem_with_oxid = _set_chem_value(chem_with_oxid, "TA DeltaT OxH2 (C)", 120.0)
    chem_with_oxid = _set_chem_value(chem_with_oxid, "TA DeltaT OxCH4 (C)", 120.0)
    res_with_oxid = run_fixed_temperature_simulation(feed_df, specs_df, chem_with_oxid)
    chem_no_oxid = _set_chem_value(chem_df, "TA DeltaT OxCO (C)", 0.0)
    chem_no_oxid = _set_chem_value(chem_no_oxid, "TA DeltaT OxH2 (C)", 0.0)
    chem_no_oxid = _set_chem_value(chem_no_oxid, "TA DeltaT OxCH4 (C)", 0.0)
    res_no_oxid = run_fixed_temperature_simulation(feed_df, specs_df, chem_no_oxid)

    notes_with = [u.notes for u in res_with_oxid.unit_trace if u.unit_name == "INCI(RGibbs)"][0]
    notes_no = [u.notes for u in res_no_oxid.unit_trace if u.unit_name == "INCI(RGibbs)"][0]
    assert "TA_OX(CO,H2,CH4)=(120.0,120.0,120.0)" in notes_with
    assert "TA_OX(CO,H2,CH4)=(0.0,0.0,0.0)" in notes_no


def test_inci_trace_reports_oxidation_basis():
    result = run_fixed_temperature_simulation(
        build_feed_df("Case-1"),
        build_specs_df(),
        build_chem_df("Case-1"),
    )
    inci_notes = [u.notes for u in result.unit_trace if u.unit_name == "INCI(RGibbs)"][0]
    assert "C+O2->CO2" in inci_notes
    assert "TA_OX(CO,H2,CH4)=" in inci_notes
