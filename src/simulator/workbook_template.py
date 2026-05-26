"""Spread Simulator 工作簿命名区域校验（JS / CLI 共用约定）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

# 与 export/js/WebServiceDemo.js 保持同步
TEMPLATE_REBUILD_CMD = "python3 scripts/build_simulator_workbook.py --case Case-1"

NAMED_RANGE_SPECS: Tuple[dict, ...] = (
    {
        "name": "Input_CaseID",
        "tier": "required",
        "sheet": "Model_Input",
        "hint": "工况标识（Case ID）",
    },
    {
        "name": "Input_Feed_Table",
        "tier": "required",
        "sheet": "Model_Input",
        "hint": "进料流股表",
    },
    {
        "name": "Input_Chem_Table",
        "tier": "required",
        "sheet": "Model_Input",
        "hint": "化学与平衡调参表",
    },
    {
        "name": "Output_KPI_Table",
        "tier": "required",
        "sheet": "Model_Output",
        "hint": "KPI 写回目标表",
    },
    {
        "name": "Input_API_Key",
        "tier": "recommended",
        "sheet": "WebService",
        "hint": "API 访问密钥（黄色可编辑格）",
    },
    {
        "name": "Output_WS_Log_Table",
        "tier": "recommended",
        "sheet": "WebService",
        "hint": "运行日志区（脚本自动刷新）",
    },
    {
        "name": "Output_API_Health_Table",
        "tier": "recommended",
        "sheet": "WebService",
        "hint": "API 健康监控（绿/黄/红）",
    },
)

REQUIRED_NAMES = tuple(s["name"] for s in NAMED_RANGE_SPECS if s["tier"] == "required")
RECOMMENDED_NAMES = tuple(s["name"] for s in NAMED_RANGE_SPECS if s["tier"] == "recommended")


@dataclass
class TemplateValidationResult:
    ok: bool
    missing_required: List[str] = field(default_factory=list)
    missing_recommended: List[str] = field(default_factory=list)

    @property
    def missing_all(self) -> List[str]:
        return [*self.missing_required, *self.missing_recommended]


def validate_workbook_names(defined_names: Sequence[str]) -> TemplateValidationResult:
    names = set(defined_names)
    missing_required = [s["name"] for s in NAMED_RANGE_SPECS if s["tier"] == "required" and s["name"] not in names]
    missing_recommended = [
        s["name"] for s in NAMED_RANGE_SPECS if s["tier"] == "recommended" and s["name"] not in names
    ]
    return TemplateValidationResult(
        ok=not missing_required,
        missing_required=missing_required,
        missing_recommended=missing_recommended,
    )


def validate_workbook(wb) -> TemplateValidationResult:
    return validate_workbook_names(wb.defined_names.keys())


def hint_for_name(name: str) -> str:
    for spec in NAMED_RANGE_SPECS:
        if spec["name"] == name:
            return str(spec["hint"])
    return name


def sheet_for_name(name: str) -> str:
    for spec in NAMED_RANGE_SPECS:
        if spec["name"] == name:
            return str(spec["sheet"])
    return ""


def format_template_fix_message(result: TemplateValidationResult) -> str:
    if result.ok and not result.missing_recommended:
        return "模板检查通过：必需命名区域齐全"
    lines: List[str] = []
    if result.missing_required:
        lines.append("缺少必需命名区域：" + "、".join(result.missing_required))
        for name in result.missing_required[:4]:
            lines.append(f"  · {name}（{sheet_for_name(name)} · {hint_for_name(name)}）")
    if result.missing_recommended:
        lines.append("缺少推荐命名区域：" + "、".join(result.missing_recommended))
    lines.append(f"修复：在本机项目根目录运行 {TEMPLATE_REBUILD_CMD}")
    lines.append("然后重新打开 xlsx，粘贴最新 export/js/WebServiceDemo.js")
    return "\n".join(lines)


def format_template_log_summary(result: TemplateValidationResult) -> str:
    if result.ok and not result.missing_recommended:
        return "必需+推荐命名区域齐全"
    if not result.ok:
        return f"缺少 {len(result.missing_required)} 个必需区域：{', '.join(result.missing_required[:3])}"
    return f"缺少推荐区域：{', '.join(result.missing_recommended[:3])}"
