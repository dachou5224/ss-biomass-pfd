"""网页 UI 辅助：进料校验与结果格式化。"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.web_ui import (
    carbon_conversion_pct,
    carbon_conversion_pox_pct,
    cold_gas_efficiency_pct,
    default_inputs,
    feed_balance_preview,
    format_results_markdown,
    h2_co_ratio_dry,
    lines_by_section,
    performance_summary_tiles,
    result_status,
    run_simulation,
    validate_inputs,
    write_pfd_feed_line,
)
from simulator.contracts import ElementBalance, H2OBudgetRow, InciMassAudit, MassStreamRow, SimulationResult, StageElementBalance
from simulator.inlet_comparison import InletCompareRow
from simulator.parameters import RGPOX_CFG
from simulator.rgpox_inlet_comparison import RgpoxInletAudit


def test_feed_balance_preview_sums_feeds():
    inputs = default_inputs("Case-1")
    prev = feed_balance_preview(inputs)
    assert prev["total_feed_kg_h"] > 0
    assert prev["inci_feed_kg_h"] > 0
    assert abs(prev["o2in_sum_mol_pct"] - 100.0) < 0.1


def test_validate_inputs_flags_bad_o2in():
    inputs = default_inputs("Case-1")
    inputs["o2in_composition"] = {"O2": 50.0, "N2": 1.0, "Ar": 1.0}
    errs = validate_inputs(inputs)
    assert any("O2IN" in e for e in errs)


def test_default_inputs_case1_uses_updated_inci_ta_defaults():
    inputs = default_inputs("Case-1")
    chem = inputs["chemistry"]
    assert chem["TA DeltaT WGS (C)"] == pytest.approx(100.0)
    assert chem["TA DeltaT Meth (C)"] == pytest.approx(425.0)
    assert chem["WGS Equilibrium Approach Eta"] == pytest.approx(0.85)
    assert chem["Meth Equilibrium Approach Eta"] == pytest.approx(0.7)


def test_format_results_markdown_includes_case():
    inputs = default_inputs("Case-1")
    md = format_results_markdown(inputs, None)
    assert "Case-1" in md
    assert "进料预览" in md


def test_write_pfd_feed_line_updates_inputs():
    inputs = default_inputs("Case-1")
    biomass_line = lines_by_section("INCI")[0]
    assert biomass_line.backend_stream == "Biomass"
    write_pfd_feed_line(inputs, biomass_line, mass_kg_h=4321.0, temp_c=30.0, pressure_bar=16.0)
    assert inputs["pfd_feeds"]["Biomass"]["mass_kg_h"] == 4321.0
    assert inputs["pfd_feeds"]["Biomass"]["temp_c"] == 30.0


def test_performance_summary_tiles_populated_after_solve():
    inputs = default_inputs("Case-1")
    res = run_simulation(inputs)
    tiles = performance_summary_tiles(inputs, res)
    labels = [t[0] for t in tiles]
    values = [t[1] for t in tiles]
    assert "冷煤气效率" in labels
    assert all(v != "—" for v in values)
    assert cold_gas_efficiency_pct(inputs, res) is not None
    assert carbon_conversion_pct(res) is not None
    assert h2_co_ratio_dry(res) is not None


def test_result_status_treats_custom_solution_as_completed():
    inputs = default_inputs("Case-1")
    inputs["pfd_feeds"]["Biomass"]["mass_kg_h"] = 4200.0
    res = run_simulation(inputs)
    status, label = result_status(inputs, res, [])
    assert res.matched_case is None
    assert status == "ok"
    assert label == "自定义工况已求解"


def test_carbon_conversion_pox_uses_rgpox_boundary_solid_basis():
    res = SimulationResult(
        inci_top_kg_h=0.0,
        inci_tar_kg_h=0.0,
        inci_pgi_total_kg_h=0.0,
        inci_slag_kg_h=0.0,
        pox_gas_kg_h=0.0,
        pox_gas_ante_kg_h=0.0,
        pox_ash_kg_h=110.0,
        inci_comp_dry_vol_pct={},
        pox_comp_dry_vol_pct={},
        inci_comp_wet_vol_pct={},
        pox_comp_wet_vol_pct={},
        pox_comp_wet_ante_vol_pct={},
        quench_t_out_c=None,
        quench_h2o_added_kg_h=None,
        inci_comp_dry_full_vol_pct={},
        pox_comp_dry_full_vol_pct={},
        inci_comp_wet_full_vol_pct={},
        pox_comp_wet_full_vol_pct={},
        inci_minor_vol_pct={},
        inci_inert_dry_vol_pct={},
        pox_minor_vol_pct={},
        rmsd_inci_pct=None,
        rmsd_pox_pct=None,
        rmsd_inci_wet_pct=None,
        rmsd_pox_wet_pct=None,
        rmsd_pox_wet_ante_pct=None,
        rmsd_inci_dry_full_pct=None,
        rmsd_inci_wet_full_pct=None,
        rmsd_inci_primary_pct=None,
        rmsd_pox_primary_pct=None,
        unit_trace=[],
        thermo_trace=[],
        element_balance=[ElementBalance("C", 0.0, 0.0)],
        inci_mass_audit=InciMassAudit(
            feed_stream_mass_kg_h=0.0,
            feed_element_mass_kg_h=0.0,
            biomass_carbon_in_kg_h=0.0,
            gas_mass_kg_h=0.0,
            bottom_solids_kg_h=0.0,
            slag_to_u14_kg_h=0.0,
            char_to_pox_kg_h=20.0,
            ash_to_pox_kg_h=90.0,
            reactor_out_total_kg_h=0.0,
            mass_closure_rel_err_pct=0.0,
            char_mass_kg_h=0.0,
            ash_mass_kg_h=0.0,
            element_balance=[StageElementBalance("INCI", "C", 1.0, 1.0, 0.0)],
            h2o_budget=[H2OBudgetRow("step", 0.0)],
            stream_ledger=[MassStreamRow("id", "out", "desc", 0.0)],
        ),
        rgpox_inlet_audit=RgpoxInletAudit(
            case_id="synthetic",
            mass_rows=[InletCompareRow("15PGI-1", "solid", 0.0, 200.0)],
            composition_rows=[],
            aggregated_mass=[],
            gas_wet_rmsd_pct=None,
            ready_for_ta_tuning=True,
            blockers=(),
        ),
        matched_case=None,
    )

    solid_cfg = dict(RGPOX_CFG.get("entrained_solid", {}))
    carbon_in = 200.0 * float(solid_cfg["dust_carbon_wt_pct_dry"]) / 100.0
    mineral_in = 200.0 * float(solid_cfg["dust_minerals_wt_pct_dry"]) / 100.0
    expected = 100.0 * (carbon_in - (110.0 - mineral_in)) / carbon_in
    assert carbon_conversion_pox_pct(res) == pytest.approx(expected)
