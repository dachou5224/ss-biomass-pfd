import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.backend import run_fixed_temperature_simulation
from simulator.data import REFERENCE_CASES, build_chem_df, build_feed_df, build_specs_df


def test_case1_pox_gas_ante_before_quench():
    res = run_fixed_temperature_simulation(build_feed_df("Case-1"), build_specs_df(), build_chem_df("Case-1"))
    exp = REFERENCE_CASES["Case-1"]["expected"]
    dbi_post = float(exp["pox_gas_kg_h"])
    dbi_ante = float(exp["pox_gas_ante_kg_h"])
    assert res.pox_gas_ante_kg_h > 0.0
    assert res.pox_gas_kg_h == pytest.approx(
        res.pox_gas_ante_kg_h + res.quench_h2o_added_kg_h,
        abs=0.5,
    )
    assert res.pox_gas_ante_kg_h < res.pox_gas_kg_h
    assert dbi_ante == pytest.approx(7760.0, abs=0.5)
    assert dbi_post == pytest.approx(8843.0, abs=0.5)
    assert res.rgpox_inlet_audit is not None
    assert res.rgpox_inlet_audit.ready_for_ta_tuning
    assert res.rmsd_pox_wet_ante_pct is not None
    assert res.rmsd_pox_wet_ante_pct < 2.5
    assert res.pox_gas_ante_kg_h == pytest.approx(7701.0, rel=0.01)
    assert abs(res.pox_ash_kg_h - 73.33) < 1.0
    assert res.pox_comp_wet_vol_pct["H2O"] == pytest.approx(41.661, abs=0.05)


def test_case1_post_quench_wet_gas_mass_flow_baseline():
    """Phase 7：T+P→Psat/P 急冷；绝压 1.5 MPa，T≈160.4°C。"""
    res = run_fixed_temperature_simulation(build_feed_df("Case-1"), build_specs_df(), build_chem_df("Case-1"))
    exp = REFERENCE_CASES["Case-1"]["expected"]
    dbi_post = float(exp["pox_gas_kg_h"])
    assert res.quench_t_out_c == pytest.approx(160.384, abs=0.05)
    assert res.quench_h2o_added_kg_h == pytest.approx(1069.0, rel=0.02)
    assert res.pox_gas_kg_h == pytest.approx(8770.0, rel=0.01)
    assert res.pox_gas_kg_h == pytest.approx(dbi_post, rel=0.05)  # 当前约 −0.8%，Phase 7 继续收窄
    assert res.rmsd_pox_wet_pct is not None
    assert res.rmsd_pox_wet_pct < 2.0  # H2O 由 T+P 得 ~41.7%，DBI 39.033%，RMSD 高于旧「锁湿度」模式
