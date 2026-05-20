"""Excel Spread Simulator 视觉主题与版式（流程模拟器风格）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, NamedStyle, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

# 色板（流程模拟器：深蓝标题 / 琥珀可编辑 / 灰只读输出）
CLR_TITLE_BG = "0F172A"
CLR_SECTION_BG = "1E40AF"
CLR_SECTION_FG = "FFFFFF"
CLR_TABLE_HEAD_BG = "334155"
CLR_TABLE_HEAD_FG = "F8FAFC"
CLR_EDIT_BG = "FFFBEB"
CLR_EDIT_BORDER = "D97706"
CLR_READONLY_BG = "F1F5F9"
CLR_READONLY_ALT = "E2E8F0"
CLR_KPI_BG = "ECFDF5"
CLR_KPI_BORDER = "059669"
CLR_CARD_BG = "FFFFFF"
CLR_CARD_BORDER = "94A3B8"
CLR_STREAM_HEAD = "B45309"
CLR_HINT_BG = "EFF6FF"
CLR_WARN_BG = "FEF2F2"

FONT_TITLE = Font(name="Calibri", size=16, bold=True, color="FFFFFF")
FONT_SECTION = Font(name="Calibri", size=11, bold=True, color=CLR_SECTION_FG)
FONT_TABLE_HEAD = Font(name="Calibri", size=10, bold=True, color=CLR_TABLE_HEAD_FG)
FONT_BODY = Font(name="Calibri", size=10)
FONT_KPI_LABEL = Font(name="Calibri", size=9, color="475569")
FONT_KPI_VALUE = Font(name="Calibri", size=14, bold=True, color="0F766E")
FONT_STREAM_ID = Font(name="Calibri", size=11, bold=True, color=CLR_STREAM_HEAD)
FONT_HINT = Font(name="Calibri", size=9, italic=True, color="64748B")

FILL_TITLE = PatternFill("solid", fgColor=CLR_TITLE_BG)
FILL_SECTION = PatternFill("solid", fgColor=CLR_SECTION_BG)
FILL_TABLE_HEAD = PatternFill("solid", fgColor=CLR_TABLE_HEAD_BG)
FILL_EDIT = PatternFill("solid", fgColor=CLR_EDIT_BG)
FILL_READONLY = PatternFill("solid", fgColor=CLR_READONLY_BG)
FILL_READONLY_ALT = PatternFill("solid", fgColor=CLR_READONLY_ALT)
FILL_KPI = PatternFill("solid", fgColor=CLR_KPI_BG)
FILL_CARD = PatternFill("solid", fgColor=CLR_CARD_BG)
FILL_STREAM_HEAD = PatternFill("solid", fgColor="FEF3C7")
FILL_HINT = PatternFill("solid", fgColor=CLR_HINT_BG)
FILL_WARN = PatternFill("solid", fgColor=CLR_WARN_BG)

THIN = Side(style="thin", color="CBD5E1")
MEDIUM = Side(style="medium", color=CLR_EDIT_BORDER)
BORDER_TABLE = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
BORDER_EDIT = Border(left=MEDIUM, right=MEDIUM, top=MEDIUM, bottom=MEDIUM)
BORDER_CARD = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

ALIGN_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
ALIGN_LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
ALIGN_RIGHT = Alignment(horizontal="right", vertical="center")

TAB_COLORS = {
    "Guide": "64748B",
    "PFD": "0D9488",
    "Model_Input": "2563EB",
    "Model_Output": "EA580C",
}

SPEC_UNITS: Dict[str, str] = {
    "INCI_T_C": "°C",
    "SLAG_T_C": "°C",
    "RGPOX_T_C": "°C",
    "SYSTEM_P_BAR": "bar",
}


@dataclass
class TableBlock:
    """工作表内一个数据区块（1-based 行号）。"""

    title: str
    header_row: int
    data_start: int
    data_end: int
    col_end: int = 6
    editable: bool = False
    value_cols: Tuple[int, ...] = (2,)
    number_format: Optional[str] = None


@dataclass
class SheetLayout:
    sheet: str
    title_row: int = 1
    col_end: int = 8
    hint_row: Optional[int] = None
    blocks: List[TableBlock] = field(default_factory=list)
    kpi_row_start: Optional[int] = None
    kpi_row_end: Optional[int] = None
    pfd_image_anchor: str = "A14"
    pfd_cards_origin: Tuple[int, int] = (4, 8)  # row, col for stream cards


def _merge_row(ws: Worksheet, row: int, col_start: int, col_end: int, value: str, font: Font, fill: PatternFill) -> None:
    ws.merge_cells(start_row=row, start_column=col_start, end_row=row, end_column=col_end)
    cell = ws.cell(row=row, column=col_start, value=value)
    cell.font = font
    cell.fill = fill
    cell.alignment = ALIGN_LEFT if row > 1 else ALIGN_CENTER
    for c in range(col_start + 1, col_end + 1):
        ws.cell(row=row, column=c).fill = fill


def _set_row_heights(ws: Worksheet, row: int, height: float, col_end: int) -> None:
    ws.row_dimensions[row].height = height


def apply_page_title(ws: Worksheet, layout: SheetLayout, title: str, subtitle: str = "") -> None:
    col_end = max(layout.col_end, 6)
    layout.col_end = col_end
    _merge_row(ws, layout.title_row, 1, col_end, title, FONT_TITLE, FILL_TITLE)
    _set_row_heights(ws, layout.title_row, 32, col_end)
    if subtitle:
        r = layout.title_row + 1
        _merge_row(ws, r, 1, col_end, subtitle, FONT_HINT, FILL_HINT)
        _set_row_heights(ws, r, 18, col_end)


def apply_hint_bar(ws: Worksheet, row: int, col_end: int, text: str) -> None:
    _merge_row(ws, row, 1, col_end, text, FONT_HINT, FILL_HINT)
    _set_row_heights(ws, row, 22, col_end)


def apply_section_banner(ws: Worksheet, block: TableBlock) -> None:
    _merge_row(ws, block.header_row - 1, 1, block.col_end, block.title, FONT_SECTION, FILL_SECTION)
    _set_row_heights(ws, block.header_row - 1, 22, block.col_end)


def apply_table_block(ws: Worksheet, block: TableBlock, zebra: bool = True) -> None:
    apply_section_banner(ws, block)
    for c in range(1, block.col_end + 1):
        cell = ws.cell(row=block.header_row, column=c)
        if cell.value is not None:
            cell.font = FONT_TABLE_HEAD
            cell.fill = FILL_TABLE_HEAD
            cell.alignment = ALIGN_CENTER
            cell.border = BORDER_TABLE
    _set_row_heights(ws, block.header_row, 20, block.col_end)

    for r in range(block.data_start, block.data_end + 1):
        alt = zebra and (r - block.data_start) % 2 == 1
        base_fill = FILL_READONLY_ALT if alt and not block.editable else FILL_READONLY
        edit_fill = FILL_EDIT if block.editable else base_fill
        _set_row_heights(ws, r, 18, block.col_end)
        for c in range(1, block.col_end + 1):
            cell = ws.cell(row=r, column=c)
            if block.editable and c in block.value_cols:
                cell.fill = FILL_EDIT
                cell.border = BORDER_EDIT
                cell.font = Font(name="Calibri", size=10, bold=True, color="92400E")
            else:
                cell.fill = edit_fill if block.editable else base_fill
                cell.border = BORDER_TABLE
                cell.font = FONT_BODY
            if block.number_format and c in block.value_cols and isinstance(cell.value, (int, float)):
                cell.number_format = block.number_format
            if c in block.value_cols and isinstance(cell.value, (int, float)):
                cell.alignment = ALIGN_RIGHT
            else:
                cell.alignment = ALIGN_LEFT


def apply_kpi_strip(ws: Worksheet, row_start: int, row_end: int, col_end: int = 8) -> None:
    """结果页顶部 KPI：指标 | 数值 | 单位 强化显示。"""
    for r in range(row_start, row_end + 1):
        lc = ws.cell(row=r, column=1)
        vc = ws.cell(row=r, column=2)
        uc = ws.cell(row=r, column=3)
        if lc.value:
            lc.font = FONT_KPI_LABEL
            lc.fill = FILL_KPI
            lc.alignment = ALIGN_LEFT
            lc.border = Border(
                left=Side(style="thin", color=CLR_KPI_BORDER),
                top=Side(style="thin", color=CLR_KPI_BORDER),
                bottom=Side(style="thin", color=CLR_KPI_BORDER),
            )
        if vc.value is not None and vc.value != "":
            vc.font = FONT_KPI_VALUE
            vc.fill = FILL_KPI
            vc.alignment = ALIGN_RIGHT
            vc.border = Border(
                top=Side(style="thin", color=CLR_KPI_BORDER),
                bottom=Side(style="thin", color=CLR_KPI_BORDER),
            )
            if isinstance(vc.value, (int, float)):
                label = str(lc.value or "")
                if "RMSD" in label or "误差" in label:
                    vc.number_format = "0.00"
                else:
                    vc.number_format = "#,##0.0"
        if uc.value:
            uc.font = FONT_KPI_LABEL
            uc.fill = FILL_KPI
            uc.alignment = ALIGN_CENTER
            uc.border = Border(
                right=Side(style="thin", color=CLR_KPI_BORDER),
                top=Side(style="thin", color=CLR_KPI_BORDER),
                bottom=Side(style="thin", color=CLR_KPI_BORDER),
            )
        _set_row_heights(ws, r, 28, col_end)


def write_stream_cards(
    ws: Worksheet,
    callouts: Sequence,
    start_row: int,
    start_col: int,
    cards_per_row: int = 2,
) -> Tuple[int, int]:
    """在 PFD 页写入流股卡片（模拟器物流标签）。返回 (末行, 末列)。"""
    card_w = 4
    card_h = 5
    row = start_row
    col = start_col
    idx = 0
    for c in callouts:
        if idx > 0 and idx % cards_per_row == 0:
            row += card_h + 1
            col = start_col
        base_row, base_col = row, col
        lines = c.as_rows()
        head = ws.cell(row=base_row, column=base_col, value=lines[0])
        head.font = FONT_STREAM_ID
        head.fill = FILL_STREAM_HEAD
        head.alignment = ALIGN_LEFT
        ws.merge_cells(
            start_row=base_row,
            start_column=base_col,
            end_row=base_row,
            end_column=base_col + card_w - 1,
        )
        for border_cell in range(base_col, base_col + card_w):
            ws.cell(row=base_row, column=border_cell).border = BORDER_CARD
        for i, text in enumerate(lines[1:], start=1):
            cell = ws.cell(row=base_row + i, column=base_col, value=text)
            cell.font = FONT_BODY
            cell.fill = FILL_CARD
            cell.alignment = ALIGN_LEFT
            ws.merge_cells(
                start_row=base_row + i,
                start_column=base_col,
                end_row=base_row + i,
                end_column=base_col + card_w - 1,
            )
            for cc in range(base_col, base_col + card_w):
                ws.cell(row=base_row + i, column=cc).fill = FILL_CARD
                ws.cell(row=base_row + i, column=cc).border = BORDER_CARD
        _set_row_heights(ws, base_row, 20, base_col + card_w)
        col += card_w + 1
        idx += 1
    end_row = row + card_h
    end_col = col
    return end_row, end_col


def apply_sheet_tab_color(ws: Worksheet, sheet_name: str) -> None:
    color = TAB_COLORS.get(sheet_name, "64748B")
    ws.sheet_properties.tabColor = color


def apply_column_widths(ws: Worksheet, widths: Dict[str, float]) -> None:
    for col, w in widths.items():
        ws.column_dimensions[col].width = w


def apply_view_options(ws: Worksheet, freeze: Optional[str] = None, zoom: int = 100) -> None:
    ws.sheet_view.zoomScale = zoom
    if freeze:
        ws.freeze_panes = freeze


def apply_hyperlink_nav(ws: Worksheet, links: Iterable[Tuple[str, str, int]]) -> None:
    """(显示文本, 目标 Sheet, 行)"""
    for text, target, row in links:
        cell = ws.cell(row=row, column=1, value=text)
        cell.hyperlink = f"#{target}!A1"
        cell.font = Font(name="Calibri", size=11, underline="single", color="2563EB")


def format_workbook(
    wb: Workbook,
    *,
    layouts: Dict[str, SheetLayout],
    guide_links_row: int = 8,
) -> None:
    """对工作簿各 Sheet 应用统一主题。"""
    default_widths = {"A": 22, "B": 16, "C": 14, "D": 14, "E": 16, "F": 14, "G": 18, "H": 18}

    if "Guide" in wb.sheetnames and "Guide" in layouts:
        ws = wb["Guide"]
        lay = layouts["Guide"]
        apply_page_title(ws, lay, "生物质气化 Spread Simulator", "Spreadsheet 前端 · 导航与说明")
        apply_hint_bar(
            ws,
            lay.hint_row or 3,
            lay.col_end,
            "① 在 Model_Input 修改黄色单元格  →  ② 运行重算  →  ③ 查看 Model_Output 与 PFD",
        )
        apply_column_widths(ws, {"A": 18, "B": 52, "C": 12})
        apply_view_options(ws, freeze="A5", zoom=110)
        apply_sheet_tab_color(ws, "Guide")
        for block in lay.blocks:
            apply_table_block(ws, block, zebra=False)

    if "Model_Input" in wb.sheetnames and "Model_Input" in layouts:
        ws = wb["Model_Input"]
        lay = layouts["Model_Input"]
        apply_page_title(
            ws,
            lay,
            "Model Input — 模型输入",
            f"工况设定与进料 · 仅黄色区域为用户可调参数",
        )
        if lay.hint_row:
            apply_hint_bar(
                ws,
                lay.hint_row,
                lay.col_end,
                "提示：修改后请执行重算；固定常数见 VBE 模块 ModelInternals",
            )
        apply_column_widths(
            ws,
            {"A": 24, "B": 14, "C": 12, "D": 28, "E": 14, "F": 12, "G": 16, "H": 16},
        )
        for block in lay.blocks:
            apply_table_block(ws, block)
        apply_view_options(ws, freeze="A6", zoom=100)
        apply_sheet_tab_color(ws, "Model_Input")
        ws.sheet_view.showGridLines = True

    if "Model_Output" in wb.sheetnames and "Model_Output" in layouts:
        ws = wb["Model_Output"]
        lay = layouts["Model_Output"]
        apply_page_title(ws, lay, "Model Output — 模型输出", "仿真结果（只读）· 组成与 DBI 对标")
        apply_column_widths(ws, default_widths)
        if lay.kpi_row_start and lay.kpi_row_end:
            apply_kpi_strip(ws, lay.kpi_row_start, lay.kpi_row_end, lay.col_end)
        for block in lay.blocks:
            fmt = "0.00" if "vol%" in block.title or "RMSD" in block.title else "#,##0.00"
            block.number_format = fmt if "vol%" in block.title else "#,##0.0"
            apply_table_block(ws, block, zebra=True)
        apply_view_options(ws, freeze="A6", zoom=100)
        apply_sheet_tab_color(ws, "Model_Output")

    if "PFD" in wb.sheetnames and "PFD" in layouts:
        ws = wb["PFD"]
        lay = layouts["PFD"]
        if lay.hint_row:
            apply_hint_bar(
                ws,
                lay.hint_row,
                max(lay.col_end, 8),
                "流程图：export/assets/流程示意图.png；右侧流股卡片随 Model Output 更新",
            )
        apply_column_widths(
            ws,
            {"A": 2, "B": 14, "C": 36, "D": 14, "E": 14, "F": 14, "G": 20, "H": 20, "I": 20, "J": 20},
        )
        apply_view_options(ws, freeze=None, zoom=90)
        apply_sheet_tab_color(ws, "PFD")
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
