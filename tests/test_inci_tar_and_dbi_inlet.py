import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pdf_reference_data import requires_dbi_mass_balance_csv

from simulator.backend import run_fixed_temperature_simulation
from simulator.data import build_chem_df, build_feed_df, build_specs_df
from simulator.reference_streams import load_dbi_inci_mass_balance
from simulator.tar_models import parse_tar_yield_mass_kg_h, tar_allocation_mass_kg_h
from simulator.pyrolysis import allocate_pyrolysis_products_elemental


def test_parse_tar_yield_mass_matches_dbi_volatiles_case1():
    # Case-1 现用 11# 样品，tar ≈ 0.01 × C_dry
    mass = parse_tar_yield_mass_kg_h(4000.0, "11#", "0.01 * C_dry")
    assert mass == pytest.approx(17.33, abs=0.05)


def test_pyrolysis_tar_outlet_decoupled_from_internal_path():
    split = allocate_pyrolysis_products_elemental(
        nC=100.0,
        nH=120.0,
        nO=50.0,
        nN=2.0,
        nS=0.5,
        tar_carbon_frac=0.0,
        target_tar_hc_ratio=1.2,
        tar_fuel_type="biomass",
        include_tar_internal=False,
        tar_outlet_mass_kg_h=18.49,
    )
    assert split.tar_allocation.carbon_mol_h > 0.0
    assert tar_allocation_mass_kg_h(split.tar_allocation) == pytest.approx(18.49, rel=0.02)


def test_case1_pipeline_tar_mass_on_pgi_outlet():
    res = run_fixed_temperature_simulation(build_feed_df("Case-1"), build_specs_df(), build_chem_df("Case-1"))
    # 11# 样品：0.01 × C_dry ≈ 17.33 kg/h
    assert res.inci_tar_kg_h == pytest.approx(17.33, abs=0.15)
    assert res.inci_pgi_total_kg_h == pytest.approx(res.inci_top_kg_h + res.inci_tar_kg_h, abs=0.01)
    audit = res.inci_mass_audit
    assert audit is not None
    assert audit.tar_kg_h == pytest.approx(res.inci_tar_kg_h, rel=1e-9)
    assert audit.dbi_volatiles_kg_h == pytest.approx(18.49, abs=0.05)  # DBI 参考值；模型 tar 随 11# 样品


@requires_dbi_mass_balance_csv
def test_dbi_inci_boundary_mass_balance_case1():
    bal = load_dbi_inci_mass_balance("Case-1")
    assert bal is not None
    assert bal["net_inlet_sum_kg_h"] == pytest.approx(6883.1, abs=0.2)
    ids = {r["stream_id"] for r in bal["net_inlet"]}
    assert ids == {"13C-4", "13HS1-1", "13OG2-1"}
    assert "circulation_sum_kg_h" not in bal
