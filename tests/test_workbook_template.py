"""工作簿命名区域模板校验。"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.workbook_template import (
    REQUIRED_NAMES,
    TEMPLATE_REBUILD_CMD,
    format_template_fix_message,
    validate_workbook_names,
)


def test_validate_all_present():
    names = list(REQUIRED_NAMES) + [
        "Input_API_Key",
        "Output_WS_Log_Table",
        "Output_API_Health_Table",
    ]
    result = validate_workbook_names(names)
    assert result.ok
    assert not result.missing_required
    assert not result.missing_recommended


def test_validate_missing_required():
    result = validate_workbook_names(["Input_CaseID"])
    assert not result.ok
    assert "Input_Feed_Table" in result.missing_required
    assert "Output_KPI_Table" in result.missing_required


def test_validate_missing_recommended_only():
    result = validate_workbook_names(list(REQUIRED_NAMES))
    assert result.ok
    assert "Output_WS_Log_Table" in result.missing_recommended


def test_fix_message_contains_rebuild_cmd():
    result = validate_workbook_names(["Input_CaseID"])
    msg = format_template_fix_message(result)
    assert TEMPLATE_REBUILD_CMD in msg
    assert "Input_Feed_Table" in msg
