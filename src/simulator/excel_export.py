"""Spread Simulator 前端工作簿：Guide / PFD / Model_Input / Model_Output。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Font as XLFont
from openpyxl.utils.dataframe import dataframe_to_rows

from .backend import run_fixed_temperature_simulation
from .contracts import SimulationResult
from .data import REFERENCE_CASES, build_chem_df, build_feed_df, build_specs_df
from .excel_theme import (
    SPEC_UNITS,
    SheetLayout,
    TableBlock,
    apply_page_title,
    format_workbook,
    write_stream_cards,
)
from .pfd_diagram import ASSETS_DIR, build_stream_callouts, export_annotated_pfd
from .parameters import PROJECT_ROOT
from .spreadsheet_ui import (
    VBA_EXPORT_DIR,
    filter_user_chem_df,
    filter_user_specs_df,
    write_vba_internals_module,
)

DEFAULT_EXPORT_PATH = PROJECT_ROOT / "export" / "Biomass_PFD_Simulator.xlsx"

SHEET_GUIDE = "Guide"
SHEET_PFD = "PFD"
SHEET_INPUT = "Model_Input"
SHEET_OUTPUT = "Model_Output"

# 版心：第 1–3 行标题/提示，数据自第 5 行起（0-based startrow=4）
DATA_START_ROW = 5


def _dict_to_df(value_col: str, data: dict) -> pd.DataFrame:
    return pd.DataFrame({"组分": list(data.keys()), value_col: list(data.values())})


def _prepare_specs_display(specs_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in specs_df.iterrows():
        key = str(r["Parameter"])
        rows.append(
            {
                "参数": key,
                "数值": r["Value"],
                "单位": SPEC_UNITS.get(key, "—"),
            }
        )
    return pd.DataFrame(rows)


def _prepare_chem_display(chem_df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "参数": chem_df["Field"],
            "数值": chem_df["Value"],
        }
    )


def _prepare_feed_display(feed_df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "流股": feed_df["Stream"],
            "质量流量 (kg/h)": feed_df["MassFlow_kg_h"],
            "温度 (°C)": feed_df["Temp_C"],
            "压力 (bar)": feed_df["Pressure_bar"],
        }
    )


def _write_table(
    ws,
    df: pd.DataFrame,
    start_row: int,
    *,
    title: str,
    editable: bool = False,
    value_cols: Tuple[int, ...] = (2,),
    col_end: int = 4,
    number_format: Optional[str] = "#,##0.0",
) -> TableBlock:
    """写入区块标题 + 表头 + 数据，返回版式块信息。"""
    banner_row = start_row
    header_row = start_row + 1
    data_start = start_row + 2
    for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=True)):
        for c_idx, value in enumerate(row, start=1):
            ws.cell(row=header_row + r_idx, column=c_idx, value=value)
    data_end = header_row + len(df)
    return TableBlock(
        title=title,
        header_row=header_row,
        data_start=data_start,
        data_end=data_end,
        col_end=col_end,
        editable=editable,
        value_cols=value_cols,
        number_format=number_format,
    )


def _init_sheet_header(ws, layout: SheetLayout, title: str, subtitle: str) -> None:
    apply_page_title(ws, layout, title, subtitle)


def _build_guide(ws, case_id: str, layout: SheetLayout) -> None:
    _init_sheet_header(
        ws,
        layout,
        "生物质气化 Spread Simulator",
        "导航 · 使用说明 · 快速跳转",
    )
    row = DATA_START_ROW
    nav = pd.DataFrame(
        [
            {"页面": "→ Model Input", "说明": "修改进料、操作条件与化学调参（黄色单元格）"},
            {"页面": "→ PFD", "说明": "查看工艺流程与流股物流卡片"},
            {"页面": "→ Model Output", "说明": "查看仿真物流、组成与 DBI 对标"},
        ]
    )
    layout.blocks.append(
        _write_table(ws, nav, row, title="快速导航", editable=False, col_end=2, number_format=None)
    )
    row = layout.blocks[-1].data_end + 3
    idx = pd.DataFrame(
        [
            {"页面": SHEET_GUIDE, "说明": "本页：目录与使用说明"},
            {"页面": SHEET_PFD, "说明": "工艺流程图 + 流股卡片"},
            {"页面": SHEET_INPUT, "说明": "用户可调输入"},
            {"页面": SHEET_OUTPUT, "说明": "仿真结果（只读）"},
        ]
    )
    layout.blocks.append(
        _write_table(ws, idx, row, title="工作簿结构", editable=False, col_end=2, number_format=None)
    )
    row = layout.blocks[-1].data_end + 3
    notes = pd.DataFrame(
        {
            "项目": ["产品", "当前工况", "内部参数", "重算流程"],
            "说明": [
                "生物质气化 Spread Simulator（Excel 前端 MVP）",
                case_id,
                "VBE → ModelInternals（与 config/model_parameters.json 同源）",
                "改 Model_Input → 运行引擎 → 刷新 Output / PFD",
            ],
        }
    )
    layout.blocks.append(
        _write_table(ws, notes, row, title="项目信息", editable=False, col_end=2, number_format=None)
    )


def _build_model_input(
    ws,
    case_id: str,
    feed_df: pd.DataFrame,
    specs_df: pd.DataFrame,
    chem_df: pd.DataFrame,
    layout: SheetLayout,
) -> None:
    _init_sheet_header(
        ws,
        layout,
        "Model Input — 模型输入",
        f"当前参考工况：{case_id} · 黄色单元格可编辑",
    )
    row = DATA_START_ROW
    meta = pd.DataFrame(
        [
            {"参数": "Case_ID", "数值": case_id, "单位": "—", "说明": "参考工况标签"},
            {
                "参数": "Biomass_Sample",
                "数值": REFERENCE_CASES[case_id]["sample"],
                "单位": "—",
                "说明": "应与化学表 Sample 一致",
            },
        ]
    )
    layout.blocks.append(
        _write_table(
            ws,
            meta,
            row,
            title="工况标识",
            editable=True,
            value_cols=(2,),
            col_end=4,
            number_format=None,
        )
    )
    row = layout.blocks[-1].data_end + 3
    layout.blocks.append(
        _write_table(
            ws,
            _prepare_specs_display(filter_user_specs_df(specs_df)),
            row,
            title="操作条件（反应器）",
            editable=True,
            value_cols=(2,),
            col_end=3,
            number_format="#,##0.0",
        )
    )
    row = layout.blocks[-1].data_end + 3
    layout.blocks.append(
        _write_table(
            ws,
            _prepare_feed_display(feed_df),
            row,
            title="进料流股",
            editable=True,
            value_cols=(2, 3, 4),
            col_end=4,
            number_format="#,##0.0",
        )
    )
    row = layout.blocks[-1].data_end + 3
    layout.blocks.append(
        _write_table(
            ws,
            _prepare_chem_display(filter_user_chem_df(chem_df)),
            row,
            title="化学与平衡调参",
            editable=True,
            value_cols=(2,),
            col_end=2,
            number_format=None,
        )
    )


def _build_model_output(
    ws,
    res: SimulationResult,
    layout: SheetLayout,
) -> None:
    _init_sheet_header(
        ws,
        layout,
        "Model Output — 模型输出",
        "仿真结果（只读）" + (f" · 匹配 {res.matched_case}" if res.matched_case else ""),
    )
    row = DATA_START_ROW
    summary = pd.DataFrame(
        [
            {"指标": "INCI 气相", "数值": res.inci_top_kg_h, "单位": "kg/h"},
            {"指标": "INCI tar", "数值": res.inci_tar_kg_h, "单位": "kg/h"},
            {"指标": "INCI PGI 合计", "数值": res.inci_pgi_total_kg_h, "单位": "kg/h"},
            {"指标": "INCI 渣 13LBS-1", "数值": res.inci_slag_kg_h, "单位": "kg/h"},
            {"指标": "RGPOX 出口气", "数值": res.pox_gas_kg_h, "单位": "kg/h"},
            {"指标": "RGPOX 灰", "数值": res.pox_ash_kg_h, "单位": "kg/h"},
            {"指标": "RMSD INCI 湿基主组分", "数值": res.rmsd_inci_primary_pct, "单位": "%"},
            {"指标": "RMSD INCI 干基四组分", "数值": res.rmsd_inci_pct, "单位": "%"},
        ]
    )
    block = _write_table(
        ws,
        summary,
        row,
        title="关键物流与对标误差",
        editable=False,
        value_cols=(2,),
        col_end=3,
        number_format="#,##0.0",
    )
    layout.blocks.append(block)
    layout.kpi_row_start = block.data_start
    layout.kpi_row_end = block.data_end

    row = block.data_end + 3
    for title, data, fmt in [
        ("INCI 干基 vol%", res.inci_comp_dry_vol_pct, "0.00"),
        ("INCI 湿基 vol%", res.inci_comp_wet_vol_pct, "0.00"),
        ("RGPOX 干基 vol%", res.pox_comp_dry_vol_pct, "0.00"),
        ("RGPOX 湿基 vol%", res.pox_comp_wet_vol_pct, "0.00"),
    ]:
        df = _dict_to_df("vol%", data)
        layout.blocks.append(
            _write_table(
                ws,
                df,
                row,
                title=title,
                editable=False,
                value_cols=(2,),
                col_end=2,
                number_format=fmt,
            )
        )
        row = layout.blocks[-1].data_end + 3

    if res.matched_case:
        expected = REFERENCE_CASES[res.matched_case]["expected"]
        val_df = _dict_to_df("DBI 参考", expected["inci_comp"]).merge(
            _dict_to_df("模型", res.inci_comp_dry_vol_pct),
            on="组分",
            how="left",
        )
        val_df["偏差"] = val_df["模型"] - val_df["DBI 参考"]
        layout.blocks.append(
            _write_table(
                ws,
                val_df,
                row,
                title="Validation — INCI 干基四组分",
                editable=False,
                value_cols=(2, 3, 4),
                col_end=4,
                number_format="0.00",
            )
        )
        row = layout.blocks[-1].data_end + 3

    if res.inci_mass_audit is not None:
        audit = res.inci_mass_audit
        audit_df = pd.DataFrame(
            [
                {"指标": "质量闭合误差", "数值": audit.mass_closure_rel_err_pct, "单位": "%"},
                {"指标": "13PGI-1 气+tar", "数值": audit.pgi_total_kg_h, "单位": "kg/h"},
                {"指标": "13LBS-1 渣", "数值": audit.slag_to_u14_kg_h, "单位": "kg/h"},
            ]
        )
        layout.blocks.append(
            _write_table(
                ws,
                audit_df,
                row,
                title="INCI 质量审计",
                editable=False,
                value_cols=(2,),
                col_end=3,
                number_format="#,##0.0",
            )
        )


def _build_model_output_placeholder(ws, layout: SheetLayout) -> None:
    _init_sheet_header(ws, layout, "Model Output — 模型输出", "尚无仿真结果")
    msg = pd.DataFrame({"说明": ["请在 Streamlit 运行仿真，或导出时启用 run_simulation。"]})
    layout.blocks.append(
        _write_table(ws, msg, DATA_START_ROW, title="状态", editable=False, col_end=1, number_format=None)
    )


def _build_pfd(
    ws,
    feed_df: pd.DataFrame,
    result: Optional[SimulationResult],
    layout: SheetLayout,
) -> List:
    _init_sheet_header(
        ws,
        layout,
        "PFD — 工艺流程与物流",
        "左侧为流程图（若已生成 PNG）；右侧为流股卡片，与 Model Output 同步",
    )
    callouts = build_stream_callouts(feed_df, result)
    card_row, card_col = layout.pfd_cards_origin
    write_stream_cards(ws, callouts, start_row=card_row, start_col=card_col, cards_per_row=2)
    return callouts


def _embed_pfd_image(xlsx_bytes: bytes, png_path: Optional[Path], layout: SheetLayout) -> bytes:
    buf = BytesIO(xlsx_bytes)
    wb = load_workbook(buf)
    if SHEET_PFD not in wb.sheetnames:
        wb.close()
        return xlsx_bytes
    ws = wb[SHEET_PFD]
    if png_path is not None and png_path.is_file():
        img = XLImage(str(png_path))
        scale = min(900 / max(img.width, 1), 380 / max(img.height, 1), 1.0)
        img.width = int(img.width * scale)
        img.height = int(img.height * scale)
        ws.add_image(img, layout.pfd_image_anchor)
    out = BytesIO()
    wb.save(out)
    wb.close()
    return out.getvalue()


def build_simulator_workbook(
    *,
    case_id: str = "Case-1",
    feed_df: pd.DataFrame | None = None,
    specs_df: pd.DataFrame | None = None,
    chem_df: pd.DataFrame | None = None,
    result: Optional[SimulationResult] = None,
    run_simulation: bool = True,
    write_vba: bool = True,
) -> bytes:
    """构建 Spread Simulator 前端工作簿（4 个主 Sheet，流程模拟器版式）。"""
    feed_df = feed_df if feed_df is not None else build_feed_df(case_id)
    specs_df = specs_df if specs_df is not None else build_specs_df()
    chem_df = chem_df if chem_df is not None else build_chem_df(case_id)

    if result is None and run_simulation:
        result = run_fixed_temperature_simulation(feed_df, specs_df, chem_df)

    if write_vba:
        write_vba_internals_module(VBA_EXPORT_DIR)

    _, png_path = export_annotated_pfd(feed_df, result, case_id=case_id)

    layouts: Dict[str, SheetLayout] = {
        SHEET_GUIDE: SheetLayout(sheet=SHEET_GUIDE, title_row=1, hint_row=3, col_end=2),
        SHEET_PFD: SheetLayout(
            sheet=SHEET_PFD,
            title_row=1,
            hint_row=3,
            col_end=10,
            pfd_image_anchor="B14",
            pfd_cards_origin=(4, 7),
        ),
        SHEET_INPUT: SheetLayout(sheet=SHEET_INPUT, title_row=1, hint_row=3, col_end=4),
        SHEET_OUTPUT: SheetLayout(sheet=SHEET_OUTPUT, title_row=1, hint_row=3, col_end=4),
    }

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        wb = writer.book
        for name in (SHEET_GUIDE, SHEET_PFD, SHEET_INPUT, SHEET_OUTPUT):
            wb.create_sheet(title=name)
        # 删除默认 Sheet
        if "Sheet" in wb.sheetnames:
            del wb["Sheet"]

        _build_guide(wb[SHEET_GUIDE], case_id, layouts[SHEET_GUIDE])
        _build_pfd(wb[SHEET_PFD], feed_df, result, layouts[SHEET_PFD])
        _build_model_input(
            wb[SHEET_INPUT],
            case_id,
            feed_df,
            specs_df,
            chem_df,
            layouts[SHEET_INPUT],
        )
        if result is None:
            _build_model_output_placeholder(wb[SHEET_OUTPUT], layouts[SHEET_OUTPUT])
        else:
            _build_model_output(wb[SHEET_OUTPUT], result, layouts[SHEET_OUTPUT])

    wb = load_workbook(BytesIO(buf.getvalue()))
    format_workbook(wb, layouts=layouts)
    _apply_guide_hyperlinks(wb[SHEET_GUIDE])
    out_buf = BytesIO()
    wb.save(out_buf)
    wb.close()
    data = _embed_pfd_image(out_buf.getvalue(), png_path, layouts[SHEET_PFD])
    return data


def _apply_guide_hyperlinks(ws) -> None:
    """为 Guide 页「→ …」行添加工作表内链接。"""
    targets = {
        "→ Model Input": SHEET_INPUT,
        "→ PFD": SHEET_PFD,
        "→ Model Output": SHEET_OUTPUT,
    }
    for row in ws.iter_rows(min_col=1, max_col=1):
        cell = row[0]
        if not isinstance(cell.value, str):
            continue
        for prefix, sheet in targets.items():
            if cell.value.strip().startswith(prefix):
                cell.hyperlink = f"#{sheet}!A1"
                cell.font = XLFont(name="Calibri", size=11, underline="single", color="2563EB")
                break


def write_simulator_workbook(path: Path | str | None = None, **kwargs: Any) -> Path:
    out = Path(path) if path is not None else DEFAULT_EXPORT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    out.write_bytes(build_simulator_workbook(**kwargs))
    return out
