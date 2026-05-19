"""Excel Spread Simulator 前端工作簿导出。"""

import os
import sys
from io import BytesIO
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

openpyxl = pytest.importorskip("openpyxl")

from simulator.excel_export import (
    SHEET_GUIDE,
    SHEET_INPUT,
    SHEET_OUTPUT,
    SHEET_PFD,
    build_simulator_workbook,
)
from simulator.spreadsheet_ui import (
    USER_CHEMISTRY_FIELDS,
    USER_OPERATING_SPECS,
    filter_user_chem_df,
    filter_user_specs_df,
    write_vba_internals_module,
)
from simulator.data import build_chem_df, build_feed_df, build_specs_df


def test_build_simulator_workbook_four_main_sheets():
    data = build_simulator_workbook(case_id="Case-1", run_simulation=True, write_vba=False)
    assert len(data) > 5000
    wb = openpyxl.load_workbook(BytesIO(data), read_only=True)
    assert wb.sheetnames == [SHEET_GUIDE, SHEET_PFD, SHEET_INPUT, SHEET_OUTPUT]
    wb.close()


def test_model_input_excludes_internal_specs_and_chemistry():
    specs = build_specs_df()
    chem = build_chem_df("Case-1")
    user_specs = filter_user_specs_df(specs)
    user_chem = filter_user_chem_df(chem)
    assert set(user_specs["Parameter"]) == set(USER_OPERATING_SPECS)
    assert "INCI_HEAT_LOSS_MW" not in set(user_specs["Parameter"])
    assert set(user_chem["Field"]) == set(USER_CHEMISTRY_FIELDS)
    assert "Tar Formula" not in set(user_chem["Field"])


def test_workbook_has_simulator_styling():
    data = build_simulator_workbook(case_id="Case-1", run_simulation=True, write_vba=False)
    wb = openpyxl.load_workbook(BytesIO(data))
    ws_in = wb["Model_Input"]
    assert ws_in["A1"].font.bold
    assert ws_in.sheet_properties.tabColor is not None
    # 进料区数值列应为可编辑样式（琥珀底）
    editable = False
    for row in ws_in.iter_rows(min_row=10, max_row=40, min_col=2, max_col=2):
        cell = row[0]
        if isinstance(cell.value, (int, float)) and cell.fill and cell.fill.fgColor:
            rgb = getattr(cell.fill.fgColor, "rgb", None) or ""
            if "FFFBEB" in str(rgb).upper() or "FFFF" in str(rgb).upper():
                editable = True
                break
    assert editable
    wb.close()


def test_vba_internals_module_generated(tmp_path):
    path = write_vba_internals_module(tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "ModelInternals" in text
    assert "INCI_C_CONVERSION" in text or "inci_c_conversion" in text.lower()
    assert "Tar Formula" in text or "Tar_Formula" in text
