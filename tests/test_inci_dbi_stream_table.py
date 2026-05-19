import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdf_reference_data import requires_inci_streams_csv

from simulator.data import REFERENCE_CASES
from simulator.reference_streams import load_inci_stream_reference, wet_mol_pct_to_dry_full
from simulator.backend import run_fixed_temperature_simulation
from simulator.data import build_chem_df, build_feed_df, build_specs_df


@requires_inci_streams_csv
def test_wet_mol_pct_to_dry_full_case1():
    stream = load_inci_stream_reference("Case-1")
    assert stream is not None
    dry = wet_mol_pct_to_dry_full(stream["wet_mol_pct"])
    assert dry["CO"] == pytest.approx(31.12226, abs=1e-4)
    assert "H2O" not in dry
    assert sum(dry.values()) == pytest.approx(100.0, abs=0.02)
    assert dry == stream["dry_full_mol_pct"]


@requires_inci_streams_csv
def test_reference_case1_has_full_stream_table_from_csv():
    expected = REFERENCE_CASES["Case-1"]["expected"]
    stream = load_inci_stream_reference("Case-1")
    assert stream is not None
    assert expected["inci_comp_wet_full"] == stream["wet_mol_pct"]
    assert expected["inci_comp_dry_full"] == stream["dry_full_mol_pct"]
    assert expected["inci_comp_wet"] == stream["wet_major_mol_pct"]
    meta = expected["inci_stream_meta"]
    assert meta["stream_id"] == "13PGI-1"
    assert meta["temperature_c"] == 900.0


@requires_inci_streams_csv
def test_case1_full_rmsd_fields_populated():
    res = run_fixed_temperature_simulation(build_feed_df("Case-1"), build_specs_df(), build_chem_df("Case-1"))
    assert res.matched_case == "Case-1"
    assert res.rmsd_inci_dry_full_pct is not None
    assert res.rmsd_inci_wet_full_pct is not None
    assert "H2S" in res.inci_comp_dry_full_vol_pct
    assert "H2O" in res.inci_comp_wet_full_vol_pct
