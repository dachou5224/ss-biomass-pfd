import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.backend import run_fixed_temperature_simulation
from simulator.data import build_chem_df, build_feed_df, build_specs_df
from simulator.elemental import biomass_fc_dry_pct, biomass_vm_dry_pct


def test_case1_vm_fc_resolve_from_11_sample():
    chem = {r.Field: str(r.Value) for _, r in build_chem_df("Case-1").iterrows()}
    assert chem["Sample"] == "11#"
    assert biomass_vm_dry_pct(chem) == pytest.approx(75.01)
    assert biomass_fc_dry_pct(chem) == pytest.approx(16.99)


def test_case1_unit_trace_reports_sample_vm():
    res = run_fixed_temperature_simulation(build_feed_df("Case-1"), build_specs_df(), build_chem_df("Case-1"))
    inci = next(row for row in res.unit_trace if row.unit_name.startswith("INCI(RGibbs)"))
    assert "VM_dry=75.0" in inci.notes
