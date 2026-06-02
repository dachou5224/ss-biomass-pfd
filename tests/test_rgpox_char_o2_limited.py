"""Phase 4A：char 蒸汽气化 + 限氧 O2POX vs DBI 15PGR-1 气量。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.backend import run_fixed_temperature_simulation
from simulator.data import REFERENCE_CASES, build_chem_df, build_feed_df, build_specs_df
from simulator.parameters import model_parameters
from simulator.reference_streams import expected_pox_gas_ante_kg_h
from simulator.rgpox import (
    apply_char_gasification,
    apply_char_co2_displacement,
    _equilibrium_constant_boudouard,
    _equilibrium_constant_char_steam,
    o2_to_gibbs_char_mol_ratio_from_cfg,
    resolve_rgpox_o2_to_gibbs_mol_h,
    resolve_rgpox_post_char_o2_mol_h,
)


def _dbi_ante_target_kg_h(case_id: str = "Case-1") -> float:
    return expected_pox_gas_ante_kg_h(REFERENCE_CASES[case_id]["expected"])


def test_resolve_o2_char_stoich_modes():
    assert resolve_rgpox_o2_to_gibbs_mol_h(100.0, 40.0, mode="char_stoich_co") == pytest.approx(20.0)
    assert resolve_rgpox_o2_to_gibbs_mol_h(10.0, 40.0, mode="char_stoich_co") == pytest.approx(10.0)
    assert resolve_rgpox_o2_to_gibbs_mol_h(100.0, 40.0, mode="char_stoich_co2") == pytest.approx(40.0)
    assert resolve_rgpox_o2_to_gibbs_mol_h(100.0, 40.0, mode="char_stoich_co2", char_mol_ratio=0.75) == pytest.approx(30.0)
    assert resolve_rgpox_o2_to_gibbs_mol_h(100.0, 40.0, mode="full_feed") == pytest.approx(100.0)


def test_o2_ratio_from_cfg_and_post_char_remaining():
    cfg = {
        "o2_to_gibbs_mode": "char_stoich_co2",
        "o2_to_gibbs_char_mol_ratio": 0.8,
        "post_char_use_remaining_o2": True,
    }
    assert o2_to_gibbs_char_mol_ratio_from_cfg(cfg) == pytest.approx(0.8)
    assert resolve_rgpox_post_char_o2_mol_h(100.0, 40.0, char_cfg=cfg) == pytest.approx(68.0)
    cfg["post_char_use_remaining_o2"] = False
    assert resolve_rgpox_post_char_o2_mol_h(100.0, 40.0, char_cfg=cfg) == pytest.approx(0.0)


def test_char_co2_displacement_strips_co2_and_h2o():
    out, rx, left = apply_char_co2_displacement(
        {"CO": 100.0, "H2": 50.0, "CO2": 40.0, "CH4": 1.0, "H2O": 40.0},
        25.0,
    )
    assert rx == pytest.approx(25.0)
    assert left == pytest.approx(0.0)
    assert out["CO2"] == pytest.approx(15.0)
    assert out["H2O"] == pytest.approx(15.0)
    assert out["CO"] == pytest.approx(125.0)
    assert out["H2"] == pytest.approx(75.0)


def test_o2_first_char_path_prefers_burn_over_steam():
    gi = apply_char_gasification(
        {"CO": 100.0, "H2": 50.0, "CO2": 10.0, "CH4": 1.0, "H2O": 30.0},
        char_c_mol_h=20.0,
        o2_feed_mol_h=20.0,
        mode="char_stoich_co",
        enable_steam=True,
        gasification_order="o2_first",
    )
    assert gi.char_reacted_o2_mol_h == pytest.approx(10.0)
    assert gi.char_reacted_steam_mol_h == pytest.approx(0.0)
    assert gi.char_unreacted_mol_h == pytest.approx(0.0)
    assert gi.major_flow_mol_h["CO"] == pytest.approx(120.0)
    assert gi.major_flow_mol_h["H2"] == pytest.approx(50.0)


def test_char_steam_gasification_mass_neutral_on_h2o():
    gi = apply_char_gasification(
        {"CO": 100.0, "H2": 50.0, "CO2": 10.0, "CH4": 1.0, "H2O": 30.0},
        char_c_mol_h=20.0,
        o2_feed_mol_h=0.0,
        mode="char_stoich_co",
    )
    assert gi.char_reacted_steam_mol_h == pytest.approx(20.0)
    assert gi.char_unreacted_mol_h == pytest.approx(0.0)
    assert gi.major_flow_mol_h["H2O"] == pytest.approx(10.0)
    assert gi.major_flow_mol_h["CO"] == pytest.approx(120.0)
    assert gi.major_flow_mol_h["H2"] == pytest.approx(70.0)


def test_hetero_ta_boudouard_limits_extent_when_enabled():
    het_cfg = {"hetero_ta": {"enabled": True, "dt_boudouard_c": 0.0, "eta_boudouard": 0.6}}
    gi = apply_char_gasification(
        {"CO": 80.0, "H2": 50.0, "CO2": 40.0, "CH4": 1.0, "H2O": 30.0},
        char_c_mol_h=25.0,
        o2_feed_mol_h=0.0,
        mode="full_feed",
        enable_steam=False,
        enable_boudouard=True,
        gasification_order="boudouard_first",
        char_cfg=het_cfg,
        t_c=1400.0,
    )
    assert gi.char_reacted_boudouard_mol_h == pytest.approx(15.0, rel=0.02)
    assert gi.char_unreacted_mol_h == pytest.approx(10.0, rel=0.02)


def test_char_boud_fraction_splits_char_between_boud_and_steam():
    """char_boud_fraction：α×char 走 Boudouard，(1−α)×char 走异相 steam，两路独立预算。"""
    het_cfg = {
        "hetero_ta": {"enabled": False},
        "char_boud_fraction": 0.6,
    }
    gi = apply_char_gasification(
        {"CO": 100.0, "H2": 50.0, "CO2": 200.0, "CH4": 1.0, "H2O": 200.0},
        char_c_mol_h=100.0,
        o2_feed_mol_h=0.0,
        mode="full_feed",
        enable_steam=True,
        enable_boudouard=True,
        char_cfg=het_cfg,
        t_c=1400.0,
    )
    assert gi.char_reacted_boudouard_mol_h == pytest.approx(60.0, rel=0.02)
    assert gi.char_reacted_steam_mol_h == pytest.approx(40.0, rel=0.02)
    assert gi.char_unreacted_mol_h == pytest.approx(0.0, abs=0.1)


def test_hetero_ta_char_steam_eta_reduces_conversion():
    het_cfg = {"hetero_ta": {"enabled": True, "dt_char_steam_c": 0.0, "eta_char_steam": 0.5}}
    gi = apply_char_gasification(
        {"CO": 100.0, "H2": 50.0, "CO2": 10.0, "CH4": 1.0, "H2O": 100.0},
        char_c_mol_h=20.0,
        o2_feed_mol_h=0.0,
        mode="full_feed",
        enable_steam=True,
        enable_boudouard=False,
        char_cfg=het_cfg,
        t_c=1400.0,
    )
    assert gi.char_reacted_steam_mol_h == pytest.approx(10.0, rel=0.05)
    assert gi.char_unreacted_mol_h == pytest.approx(10.0, rel=0.05)
    assert _equilibrium_constant_char_steam(1673.15) > 1.0


def test_case1_pox_phase6c_middle_way_combined_ta():
    """Phase 6C：middle-way + 联合 TA（WGS=-160 Boud=-100 hetero_ta）。"""
    res = run_fixed_temperature_simulation(build_feed_df("Case-1"), build_specs_df(), build_chem_df("Case-1"))
    char_cfg = model_parameters()["rgpox"]["char_gasification"]
    chem = model_parameters()["chemistry_setup"]
    assert char_cfg["o2_to_gibbs_mode"] == "full_feed"
    assert char_cfg["reaction_sequence"] == "gas_equilibrium_first"
    assert char_cfg.get("post_char_use_remaining_o2") is False
    assert char_cfg.get("enable_boudouard") is True
    het = char_cfg.get("hetero_ta", {})
    assert het.get("enabled") is True
    assert chem["RGPOX TA DeltaT WGS (C)"] == pytest.approx(-160.0)
    assert het.get("dt_boudouard_c") == pytest.approx(-100.0)
    assert res.rmsd_pox_wet_ante_pct is not None
    assert res.rmsd_pox_wet_ante_pct < 2.5
    assert abs(res.pox_ash_kg_h - 73.33) < 1.5
    dbi_ante = _dbi_ante_target_kg_h()
    assert res.pox_gas_ante_kg_h == pytest.approx(7701.0, rel=0.01)
    assert res.pox_gas_ante_kg_h == pytest.approx(dbi_ante, rel=0.04)


def test_char_before_gibbs_baseline_beats_gas_first_on_mass_and_rmsd_at_full_feed(monkeypatch):
    """Phase 3B 基线：full_feed 下 char_before 同时优于 gas_equilibrium_first 的质量与 RMSD。"""
    import simulator.rgpox as rgpox_mod

    def _run(seq: str):
        cfg = dict(rgpox_mod.RGPOX_CFG)
        cg = dict(cfg.get("char_gasification", {}))
        cg["o2_to_gibbs_mode"] = "full_feed"
        cg["reaction_sequence"] = seq
        cfg["char_gasification"] = cg
        monkeypatch.setattr(rgpox_mod, "RGPOX_CFG", cfg)
        return run_fixed_temperature_simulation(build_feed_df("Case-1"), build_specs_df(), build_chem_df("Case-1"))

    legacy = _run("char_before_gibbs")
    gas_first = _run("gas_equilibrium_first")
    dbi_ante = _dbi_ante_target_kg_h()
    assert legacy.rmsd_pox_wet_ante_pct < gas_first.rmsd_pox_wet_ante_pct
    assert legacy.pox_gas_ante_kg_h == pytest.approx(gas_first.pox_gas_ante_kg_h, rel=1e-4)
    assert legacy.pox_gas_ante_kg_h == pytest.approx(dbi_ante, rel=0.04)


def test_case1_full_feed_o2_still_high_ante(monkeypatch):
    import simulator.rgpox as rgpox_mod

    cfg = dict(rgpox_mod.RGPOX_CFG)
    char_cfg = dict(cfg.get("char_gasification", {}))
    char_cfg["o2_to_gibbs_mode"] = "full_feed"
    cfg["char_gasification"] = char_cfg
    monkeypatch.setattr(rgpox_mod, "RGPOX_CFG", cfg)

    res = run_fixed_temperature_simulation(build_feed_df("Case-1"), build_specs_df(), build_chem_df("Case-1"))
    assert res.pox_gas_ante_kg_h > 7500.0
