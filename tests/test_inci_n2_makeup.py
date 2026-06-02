import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.backend import (
    _apply_inci_n2_makeup,
    _compute_inci_n2_makeup_mol_h,
    run_fixed_temperature_simulation,
)
from simulator.data import build_chem_df, build_feed_df, build_specs_df
from simulator.species import MOLECULAR_WEIGHT


def _chem_df_with_mode(mode: str) -> pd.DataFrame:
    chem_df = build_chem_df("Case-1")
    mask = chem_df["Field"] == "INCI N2 Makeup Mode"
    if mask.any():
        chem_df.loc[mask, "Value"] = mode
    else:
        chem_df = pd.concat(
            [chem_df, pd.DataFrame([{"Field": "INCI N2 Makeup Mode", "Value": mode}])],
            ignore_index=True,
        )
    return chem_df


def test_compute_inci_n2_makeup_mol_h_reaches_target():
    flow = {"N2": 100.0, "CO": 10000.0, "H2": 10000.0, "CO2": 8000.0, "CH4": 2000.0, "H2O": 6000.0}
    delta = _compute_inci_n2_makeup_mol_h(flow, 2.0)
    assert delta > 0.0
    out = _apply_inci_n2_makeup(flow, delta)
    wet_total = sum(out.values())
    assert 100.0 * out["N2"] / wet_total == pytest.approx(2.0, abs=1e-6)


def test_case1_default_n2_makeup_aligns_dbi_wet_n2():
    res = run_fixed_temperature_simulation(
        build_feed_df("Case-1"),
        build_specs_df(),
        build_chem_df("Case-1"),
    )
    assert res.inci_n2_makeup_mol_h > 3900.0
    assert res.inci_comp_wet_full_vol_pct["N2"] == pytest.approx(2.0, abs=0.05)
    assert res.inci_top_kg_h > 6450.0
    audit = res.inci_mass_audit
    assert audit is not None
    assert audit.n2_makeup_kg_h == pytest.approx(
        res.inci_n2_makeup_mol_h * MOLECULAR_WEIGHT["N2"] / 1000.0,
        abs=0.01,
    )
    assert audit.mass_closure_rel_err_pct < 0.05
    assert any(row.stream_id == "N2-makeup" for row in audit.stream_ledger)


def test_case1_n2_makeup_off_skips_makeup():
    res = run_fixed_temperature_simulation(
        build_feed_df("Case-1"),
        build_specs_df(),
        _chem_df_with_mode("off"),
    )
    assert res.inci_n2_makeup_mol_h == pytest.approx(0.0)
    assert res.inci_comp_wet_full_vol_pct["N2"] < 1.0
