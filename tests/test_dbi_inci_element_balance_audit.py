"""DBI INCI 五元素衡算审计脚本（依赖本地 stream table CSV）。"""

from pathlib import Path

import pytest

from pdf_reference_data import PDF_REFERENCE_DIR

CSV_PATH = PDF_REFERENCE_DIR / "dbi_inci_stream_table_case1.csv"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not CSV_PATH.is_file(), reason="缺少 dbi_inci_stream_table_case1.csv")
def test_dbi_element_balance_audit_runs():
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from audit_dbi_inci_element_balance import run_audit

    result = run_audit(CSV_PATH)
    assert result.inlet.C > 1000
    assert result.outlet_gas.O > 500
    # DBI 表已知：氮出口远大于进料
    assert result.rel_err_pct()["N"] < -50
