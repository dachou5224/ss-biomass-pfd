"""WPS xlsm 密封（JDEData.bin + 隐藏脚本表）。"""

from __future__ import annotations

import os
import sys

import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from io import BytesIO
from pathlib import Path

import pytest

from simulator.excel_export import build_simulator_workbook
from simulator.wps_jsa_pack import (
    MACRO_SOURCE_SHEET,
    build_macro_source_payload,
    inject_macro_source_sheet,
    seal_workbook_for_wps,
)


def test_macro_payload_includes_exports_footer():
    payload = build_macro_source_payload()
    assert "__ss_exports__" in payload
    assert "runWebServiceLiteDemo" in payload
    assert len(payload) < 32000


def test_inject_macro_source_sheet_creates_hidden_sheet():
    raw = build_simulator_workbook(case_id="Case-1", run_simulation=False, write_vba=False)
    sealed = inject_macro_source_sheet(raw)
    with zipfile.ZipFile(BytesIO(sealed), "r") as zf:
        wb_xml = zf.read("xl/workbook.xml").decode("utf-8")
    assert MACRO_SOURCE_SHEET in wb_xml


def test_seal_workbook_adds_jde_data_and_rels(tmp_path: Path):
    raw = build_simulator_workbook(case_id="Case-1", run_simulation=False, write_vba=False)
    xlsm = seal_workbook_for_wps(raw)
    out = tmp_path / "test.xlsm"
    out.write_bytes(xlsm)
    with zipfile.ZipFile(BytesIO(xlsm), "r") as zf:
        names = set(zf.namelist())
        assert "xl/JDEData.bin" in names
        bootstrap = zf.read("xl/JDEData.bin").decode("utf-8")
        assert "runWebServiceLiteDemo" in bootstrap
        assert "__ssEnsureLoaded" in bootstrap
        rels = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        assert "JDEData.bin" in rels
        ct = zf.read("[Content_Types].xml").decode("utf-8")
        assert "JDEData.bin" in ct
        assert "ns0:" not in ct
        assert "macroEnabled" in ct
        rels = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        assert "ns0:" not in rels
        assert MACRO_SOURCE_SHEET in zf.read("xl/workbook.xml").decode("utf-8")
