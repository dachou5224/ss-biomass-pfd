"""本地 PDF 提取参考数据路径与 pytest 跳过标记（文件不纳入 Git）。"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PDF_REFERENCE_DIR = PROJECT_ROOT / "data" / "reference"


def pdf_reference_file(name: str) -> Path:
    return PDF_REFERENCE_DIR / name


HAS_INCI_STREAMS_CSV = pdf_reference_file("inci_streams.csv").is_file()
HAS_DBI_STREAM_TABLE_CSV = pdf_reference_file("dbi_inci_stream_table_case1.csv").is_file()
HAS_DBI_MASS_BALANCE_CSV = pdf_reference_file("dbi_inci_mass_balance_case1.csv").is_file()
HAS_DBI_RGPOX_INLET_JSON = (PROJECT_ROOT / "config" / "dbi_rgpox_inlet.json").is_file()
HAS_RGPOX_STREAMS_CSV = pdf_reference_file("rgpox_streams.csv").is_file()
HAS_DBI_RGPOX_STREAM_TABLE_CSV = pdf_reference_file("dbi_rgpox_stream_table_case1.csv").is_file()

requires_inci_streams_csv = pytest.mark.skipif(
    not HAS_INCI_STREAMS_CSV,
    reason="缺少 data/reference/inci_streams.csv（PDF 提取，不纳入 Git）",
)
requires_dbi_stream_table_csv = pytest.mark.skipif(
    not HAS_DBI_STREAM_TABLE_CSV,
    reason="缺少 data/reference/dbi_inci_stream_table_case1.csv（运行 scripts/extract_dbi_inci_stream_table.py）",
)
requires_dbi_mass_balance_csv = pytest.mark.skipif(
    not HAS_DBI_MASS_BALANCE_CSV,
    reason="缺少 data/reference/dbi_inci_mass_balance_case1.csv（PDF 提取，不纳入 Git）",
)
requires_dbi_rgpox_inlet_json = pytest.mark.skipif(
    not HAS_DBI_RGPOX_INLET_JSON,
    reason="缺少 config/dbi_rgpox_inlet.json（本地 DBI 提取，不纳入 Git）",
)
requires_rgpox_streams_csv = pytest.mark.skipif(
    not HAS_RGPOX_STREAMS_CSV,
    reason="缺少 data/reference/rgpox_streams.csv（运行 scripts/extract_dbi_rgpox_stream_table.py）",
)
requires_dbi_rgpox_stream_table_csv = pytest.mark.skipif(
    not HAS_DBI_RGPOX_STREAM_TABLE_CSV,
    reason="缺少 data/reference/dbi_rgpox_stream_table_case1.csv（运行 scripts/extract_dbi_rgpox_stream_table.py）",
)
