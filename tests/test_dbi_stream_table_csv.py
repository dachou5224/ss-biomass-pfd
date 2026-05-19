"""DBI INCI stream table 全量 CSV（自 PDF 提取，本地-only）一致性检查。"""

from pathlib import Path

import pandas as pd
import pytest

from pdf_reference_data import PDF_REFERENCE_DIR, requires_dbi_stream_table_csv

CSV_PATH = PDF_REFERENCE_DIR / "dbi_inci_stream_table_case1.csv"
PDF_PATH = Path(__file__).resolve().parents[1] / "doc" / "TR5_APPENDIX 02_PFD & Stream Table_Unit 13_INCI Gasifier_DBI.pdf"


def _val(df: pd.DataFrame, stream_id: str, section: str, prop: str) -> str:
    row = df[
        (df["stream_id"] == stream_id)
        & (df["section"] == section)
        & (df["property"] == prop)
    ]
    assert len(row) == 1, f"{stream_id} {section} {prop}"
    return str(row.iloc[0]["value"])


@requires_dbi_stream_table_csv
def test_dbi_stream_table_csv_covers_all_streams():
    df = pd.read_csv(CSV_PATH)
    assert set(df["case"]) == {"Case-1"}
    streams = sorted(df["stream_id"].unique())
    assert len(streams) == 15
    assert "13PGI-1" in streams
    assert "13OG2-1" in streams
    assert len(df) >= 900


@requires_dbi_stream_table_csv
def test_dbi_stream_table_key_values_match_pdf():
    df = pd.read_csv(CSV_PATH)
    assert _val(df, "13C-4", "overall", "flow_kg_h") == "4758"
    assert _val(df, "13OG2-1", "fluid_phase", "O2") == "95.00%"
    assert _val(df, "13PGI-1", "fluid_phase", "flow_kg_h") == "6580"
    assert _val(df, "13PGI-1", "fluid_phase", "CO") == "24.82%"
    assert _val(df, "13LBS-1", "solid_phase", "flow_kg_h") == "110.0"


@pytest.mark.skipif(not PDF_PATH.is_file(), reason="DBI PDF 未放在 doc/ 目录")
def test_extract_script_regenerates_csv(tmp_path):
    import sys

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    from extract_dbi_inci_stream_table import extract_stream_table

    out = tmp_path / "out.csv"
    df = extract_stream_table(PDF_PATH)
    df.to_csv(out, index=False)
    assert len(df) >= 900
    assert "13PGI-1" in df["stream_id"].values
