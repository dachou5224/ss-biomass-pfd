import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.data import REFERENCE_CASES
from simulator.reference_streams import overall_biomass_carbon_conversion_from_boundary_streams


def test_overall_biomass_carbon_conversion_from_boundary_streams():
    basis = overall_biomass_carbon_conversion_from_boundary_streams(
        biomass_feed_kg_h=100.0,
        biomass_moisture_wt_pct=10.0,
        biomass_carbon_wt_pct_dry=50.0,
        bottom_slag_kg_h=5.0,
        bottom_slag_carbon_wt_pct_dry=20.0,
        entrained_solid_kg_h=10.0,
        entrained_solid_carbon_wt_pct_dry=40.0,
    )

    assert basis["biomass_dry_kg_h"] == pytest.approx(90.0)
    assert basis["biomass_carbon_in_kg_h"] == pytest.approx(45.0)
    assert basis["bottom_slag_carbon_kg_h"] == pytest.approx(1.0)
    assert basis["entrained_solid_carbon_kg_h"] == pytest.approx(4.0)
    assert basis["unconverted_carbon_kg_h"] == pytest.approx(5.0)
    assert basis["overall_biomass_carbon_conversion_pct"] == pytest.approx(88.8888888889)


def test_reference_cases_attach_local_dbi_boundary_basis_when_available():
    basis = REFERENCE_CASES["Case-1"]["expected"].get("dbi_inci_boundary_basis")
    if basis is None:
        pytest.skip("local DBI stream-table inputs unavailable")

    assert basis["overall_biomass_carbon_conversion_pct"] is not None
    assert basis["unconverted_carbon_kg_h"] == pytest.approx(
        basis["bottom_slag_carbon_kg_h"] + basis["entrained_solid_carbon_kg_h"]
    )
    assert basis["basis_streams"] == {
        "biomass_feed": "13C-4",
        "bottom_slag": "13LBS-1",
        "entrained_solid": "15PGI-1",
    }
    assert 0.0 < basis["overall_biomass_carbon_conversion_pct"] < 100.0
