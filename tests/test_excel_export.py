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
    SHEET_WS,
    WORKBOOK_SHEET_ORDER,
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


def test_resolve_pfd_workbook_image_prefers_official_diagram(tmp_path, monkeypatch):
    from simulator.pfd_diagram import PFD_WORKBOOK_IMAGE, resolve_pfd_workbook_image

    official = tmp_path / "流程示意图.png"
    official.write_bytes(b"fake")
    fallback = tmp_path / "pfd_Case-1.png"
    fallback.write_bytes(b"fake2")
    monkeypatch.setattr("simulator.pfd_diagram.PFD_WORKBOOK_IMAGE", official)
    assert resolve_pfd_workbook_image(annotated_png=fallback) == official


def test_build_simulator_workbook_sheet_order():
    data = build_simulator_workbook(case_id="Case-1", run_simulation=True, write_vba=False)
    assert len(data) > 5000
    wb = openpyxl.load_workbook(BytesIO(data), read_only=True)
    assert wb.sheetnames == list(WORKBOOK_SHEET_ORDER)
    wb.close()


def test_webservice_sheet_has_api_key_named_range():
    data = build_simulator_workbook(case_id="Case-1", run_simulation=False, write_vba=False)
    wb = openpyxl.load_workbook(BytesIO(data))
    assert "Input_API_Key" in wb.defined_names
    assert "Output_WS_Log_Table" in wb.defined_names
    assert "Output_API_Health_Table" in wb.defined_names
    ref = wb.defined_names["Input_API_Key"].attr_text
    assert ref.startswith(f"'{SHEET_WS}'!")
    ws = wb[SHEET_WS]
    assert any(
        "API" in str(c.value or "")
        for row in ws.iter_rows(max_row=50)
        for c in row
    )
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
    # 进料区应有显式公式列（kg/h -> t/h）
    has_formula = False
    for row in ws_in.iter_rows(min_row=10, max_row=60, min_col=5, max_col=5):
        formula = row[0].value
        if isinstance(formula, str) and formula.startswith("=IFERROR(B") and "/1000" in formula:
            has_formula = True
            break
    assert has_formula
    # 命名区域用于 VBA OOP 访问
    names = set(wb.defined_names.keys())
    assert "Input_Feed_Table" in names
    assert "Input_Chem_Table" in names
    assert "Input_API_Key" in names
    assert "Output_WS_Log_Table" in names
    assert "Output_API_Health_Table" in names
    assert "Output_KPI_Table" in names
    wb.close()


def test_vba_internals_module_generated(tmp_path):
    path = write_vba_internals_module(tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "ModelInternals" in text
    assert "INCI_C_CONVERSION" in text or "inci_c_conversion" in text.lower()
    assert "Tar Formula" in text or "Tar_Formula" in text
