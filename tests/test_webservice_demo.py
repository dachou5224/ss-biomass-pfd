import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.webservice_demo import (
    build_compute_response,
    build_full_compute_response,
    build_input_read_response,
    build_output_pack_response,
    build_output_pack_tsv,
)


def test_input_read_response_returns_tables_and_checks():
    payload = {
        "case_id": "Case-1",
        "system_p_bar": 16.5,
        "pfd_feeds": {
            "Biomass": {"mass_kg_h": 4100},
            "O2IN": {"mass_kg_h": 1400},
        },
        "o2in_composition": {"O2": 95.0, "N2": 1.75, "Ar": 3.25},
    }
    res = build_input_read_response(payload)
    assert res["mode"] == "input-read"
    assert "feed" in res["tables"]
    assert "specs" in res["tables"]
    assert "chemistry" in res["tables"]
    assert abs(res["checks"]["o2in_sum_mol_pct"] - 100.0) < 1e-9
    assert res["checks"]["o2in_is_100_pct"] is True


def test_output_pack_response_has_named_range_matrix():
    payload = {
        "case_id": "Case-1",
        "pfd_feeds": {
            "Biomass": {"mass_kg_h": 4000},
            "CO2IN": {"mass_kg_h": 757.7},
            "H2OIN": {"mass_kg_h": 782.1},
            "O2IN": {"mass_kg_h": 1343},
        },
        "o2in_composition": {"O2": 90.0, "N2": 5.0, "Ar": 5.0},
    }
    res = build_output_pack_response(payload)
    assert res["mode"] == "output-pack"
    assert "Output_Demo_KPI" in res["named_ranges"]
    matrix = res["named_ranges"]["Output_Demo_KPI"]
    assert len(matrix) >= 5
    assert matrix[0][0] == "TOTAL_FEED_KG_H"
    assert res["status"] == "ok"


def test_compute_response_is_ui_agnostic():
    res = build_compute_response({"case_id": "Case-1"})
    assert "named_ranges" not in res
    assert "mode" not in res
    assert len(res["kpi_rows"]) >= 5


def test_output_pack_warns_when_o2_sum_invalid():
    payload = {
        "case_id": "Case-1",
        "o2in_composition": {"O2": 94.0, "N2": 1.75, "Ar": 3.25},  # 99.0
    }
    res = build_output_pack_response(payload)
    assert res["checks"]["o2in_is_100_pct"] is False
    assert res["status"] == "check"


def test_output_pack_tsv_has_header_and_status():
    tsv = build_output_pack_tsv({"case_id": "Case-1"})
    lines = [x for x in tsv.splitlines() if x.strip()]
    assert lines[0] == "METRIC\tVALUE\tUNIT"
    assert lines[1].startswith("STATUS\t")


def test_full_compute_response_returns_result_sections():
    res = build_full_compute_response({"case_id": "Case-1"})
    assert "checks" in res
    assert "result_summary" in res
    assert "performance" in res
    assert "compositions" in res
    assert "tables" in res
    assert "feed_summary" in res["tables"]
    assert "unit_trace" in res["tables"]
