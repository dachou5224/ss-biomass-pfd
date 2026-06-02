"""DBI Unit 15 RGPOX stream table 全量 CSV（自 PDF 提取，本地-only）一致性检查。"""

from pathlib import Path

import pandas as pd
import pytest

from pdf_reference_data import PDF_REFERENCE_DIR, requires_dbi_rgpox_stream_table_csv

CSV_PATH = PDF_REFERENCE_DIR / "dbi_rgpox_stream_table_case1.csv"
PDF_PATH = (
    Path(__file__).resolve().parents[1]
    / "doc"
    / "TR5_APPENDIX 04_1_PFD & Stream Table_Unit 15_RGPOx Gasifier_0.05vol.%HCl_DBI.pdf"
)


def _val(df: pd.DataFrame, stream_id: str, section: str, prop: str) -> str:
    row = df[
        (df["stream_id"] == stream_id)
        & (df["section"] == section)
        & (df["property"] == prop)
    ]
    assert len(row) == 1, f"{stream_id} {section} {prop}"
    return str(row.iloc[0]["value"])


@requires_dbi_rgpox_stream_table_csv
def test_dbi_rgpox_stream_table_csv_covers_streams():
    df = pd.read_csv(CSV_PATH)
    assert set(df["case"]) == {"Case-1"}
    streams = sorted(df["stream_id"].unique())
    assert "15PGI-1" in streams
    assert "15PGR-1" in streams
    assert "15PGR-2" in streams
    assert len(df) >= 200


@requires_dbi_rgpox_stream_table_csv
def test_dbi_rgpox_stream_table_key_values_match_pdf():
    df = pd.read_csv(CSV_PATH)
    assert _val(df, "15PGI-1", "fluid_phase", "flow_kg_h") == "6580"
    assert _val(df, "15OG1", "fluid_phase", "flow_kg_h") == "956.0"
    assert _val(df, "15PGR-1", "fluid_phase", "flow_kg_h") == "7760"
    assert _val(df, "15PGR-1-dry", "fluid_phase", "flow_kg_h") == "6039"
    assert _val(df, "15PGR-2", "fluid_phase", "flow_kg_h") == "8843"
    assert _val(df, "15PGR-2-dry", "fluid_phase", "flow_kg_h") == "5990"
    assert _val(df, "15PGR-1", "fluid_phase", "CO") == "33.23%"
    assert _val(df, "15PGR-2", "fluid_phase", "H2O") == "39.033%"
    assert _val(df, "15PGR-1", "solid_phase", "flow_kg_h") == "73.33"


@requires_dbi_rgpox_stream_table_csv
def test_reference_cases_pox_mass_matches_pdf_table():
    from simulator.data import REFERENCE_CASES

    exp = REFERENCE_CASES["Case-1"]["expected"]
    assert exp["pox_gas_ante_kg_h"] == pytest.approx(7760.0, abs=0.5)
    assert exp["pox_gas_kg_h"] == pytest.approx(8843.0, abs=0.5)


@pytest.mark.skipif(not PDF_PATH.is_file(), reason="Unit 15 PDF 未放在 doc/ 目录")
def test_extract_rgpox_script_regenerates_csv(tmp_path):
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    from extract_dbi_rgpox_stream_table import extract_stream_table

    df = extract_stream_table(PDF_PATH)
    assert len(df) >= 200
    assert "15PGR-1" in df["stream_id"].values
    assert "15PGR-2" in df["stream_id"].values
