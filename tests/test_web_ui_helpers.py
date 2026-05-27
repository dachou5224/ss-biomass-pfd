"""网页 UI 辅助：进料校验与结果格式化。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.web_ui import (
    carbon_conversion_pct,
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
