import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.backend import run_fixed_temperature_simulation
from simulator.data import build_chem_df, build_feed_df, build_specs_df
from simulator.pyrolysis import allocate_pyrolysis_products_elemental


def _set_chem_value(df: pd.DataFrame, field: str, value: str) -> pd.DataFrame:
    out = df.copy()
    out.loc[out["Field"] == field, "Value"] = value
    return out


def test_no_tar_1d_scheme_disables_tar_and_routes_nitrogen_to_n2():
    split = allocate_pyrolysis_products_elemental(
        nC=10.0,
        nH=12.0,
        nO=5.0,
        nN=0.6,
        nS=0.1,
        tar_carbon_frac=0.3,
        target_tar_hc_ratio=1.2,
        tar_fuel_type="biomass",
        include_tar_internal=True,
        scheme="no-tar-1d",
    )
    vol = split.volatile_species_mol_h
    assert split.tar_allocation.carbon_mol_h == 0.0
    assert vol.get("NH3", 0.0) == 0.0
    assert vol.get("N2", 0.0) > 0.0


def test_pipeline_accepts_no_tar_1d_pyrolysis_scheme():
    feed_df = build_feed_df("Case-1")
    specs_df = build_specs_df()
    chem_df = build_chem_df("Case-1")
    chem_df = _set_chem_value(chem_df, "Pyrolysis Scheme", "no-tar-1d")

    res = run_fixed_temperature_simulation(feed_df, specs_df, chem_df)
    inci_notes = [u.notes for u in res.unit_trace if u.unit_name == "INCI(RGibbs)"][0]
    assert "PyroScheme=no-tar-1d" in inci_notes
