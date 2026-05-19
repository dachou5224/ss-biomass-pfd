import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.inlet_comparison import aggregate_inlet_comparison, build_inci_inlet_comparison


def test_inlet_comparison_case1_aligned_with_dbi():
    rows = build_inci_inlet_comparison("Case-1")
    assert rows is not None
    agg = {r.component: r for r in aggregate_inlet_comparison(rows)}
    assert agg["TOTAL"].delta_kg_h == pytest.approx(0.0, abs=1.0)
    assert agg["H2O"].delta_kg_h == pytest.approx(0.0, abs=0.5)
    assert agg["CO2"].delta_kg_h == pytest.approx(0.0, abs=0.5)
    assert agg["O2"].delta_kg_h == pytest.approx(0.0, abs=0.5)
