"""Spread Simulator 前端工作簿：Guide / PFD / Model_Input / Model_Output。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from openpyxl import load_workbook
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Font as XLFont, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.utils.dataframe import dataframe_to_rows

from .backend import run_fixed_temperature_simulation
from .contracts import SimulationResult
from .data import REFERENCE_CASES, build_chem_df, build_feed_df, build_specs_df
from .excel_theme import (
    SPEC_UNITS,
    SheetLayout,
    TableBlock,
    apply_hint_bar,
    apply_page_title,
    format_workbook,
    write_stream_cards,
)
from .pfd_diagram import (
    ASSETS_DIR,
    PFD_WORKBOOK_IMAGE,
    build_stream_callouts,
    export_annotated_pfd,
    resolve_pfd_workbook_image,
)
from .parameters import PROJECT_ROOT
from .spreadsheet_ui import (
    VBA_EXPORT_DIR,
    filter_user_chem_df,
    filter_user_specs_df,
    write_vba_internals_module,
)

DEFAULT_EXPORT_PATH = PROJECT_ROOT / "export" / "Biomass_PFD_Simulator.xlsx"
DEFAULT_WPS_EXPORT_PATH = PROJECT_ROOT / "export" / "Biomass_PFD_Simulator_WPS.xlsm"

SHEET_GUIDE = "Guide"
SHEET_WS = "WebService"
SHEET_PFD = "PFD"
SHEET_INPUT = "Model_Input"
SHEET_OUTPUT = "Model_Output"

# 标签从左到右 = 软件典型流程：首页 → 输入 → 运行 → 结果 → 流程图
WORKBOOK_SHEET_ORDER = (
    SHEET_GUIDE,
    SHEET_INPUT,
    SHEET_WS,
    SHEET_OUTPUT,
    SHEET_PFD,
)

WS_API_URL = "https://simapi.nice-ai.dev"
WS_SCRIPT_PATH = "export/js/WebServiceDemo.js"

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
                "换算(K)": None,
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
            "质量流量 (t/h)": None,
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


def _block_range(block: TableBlock) -> str:
    col_end = get_column_letter(block.col_end)
    return f"$A${block.data_start}:${col_end}${block.data_end}"


def _apply_specs_conversion_formulas(ws, block: TableBlock) -> None:
    for r in range(block.data_start, block.data_end + 1):
        if ws.cell(row=r, column=3).value == "°C":
            ws.cell(row=r, column=4, value=f"=B{r}+273.15")


def _apply_feed_formulas(ws, block: TableBlock) -> None:
    for r in range(block.data_start, block.data_end + 1):
        ws.cell(row=r, column=5, value=f"=IFERROR(B{r}/1000,0)")


def _build_input_quick_checks(ws, start_row: int, feed_block: TableBlock) -> TableBlock:
    checks = pd.DataFrame(
        [
            {"指标": "总进料质量流量", "计算结果": None, "单位": "kg/h", "说明": "SUM 全部进料流股"},
            {"指标": "BIOMASS 流量", "计算结果": None, "单位": "kg/h", "说明": "SUMIFS 按流股名筛选"},
            {"指标": "蒸汽总量 (H2OIN)", "计算结果": None, "单位": "kg/h", "说明": "SUMIFS"},
            {"指标": "氧气总量 (O2IN+O2POX)", "计算结果": None, "单位": "kg/h", "说明": "SUMIFS"},
            {"指标": "生物质占比", "计算结果": None, "单位": "%", "说明": "BIOMASS / 总进料"},
            {"指标": "最小进料压力", "计算结果": None, "单位": "bar", "说明": "MIN 压力列"},
            {"指标": "输入状态", "计算结果": None, "单位": "—", "说明": "IF + COUNTIF 基础完整性检查"},
        ]
    )
    block = _write_table(
        ws,
        checks,
        start_row,
        title="输入快速核算（Excel 公式）",
        editable=False,
        value_cols=(2,),
        col_end=4,
        number_format="#,##0.0",
    )
    mass_rng = f"$B${feed_block.data_start}:$B${feed_block.data_end}"
    stream_rng = f"$A${feed_block.data_start}:$A${feed_block.data_end}"
    press_rng = f"$D${feed_block.data_start}:$D${feed_block.data_end}"
    r = block.data_start
    ws.cell(row=r, column=2, value=f"=SUM({mass_rng})")
    ws.cell(row=r + 1, column=2, value=f'=IFERROR(SUMIFS({mass_rng},{stream_rng},"BIOMASS"),0)')
    ws.cell(row=r + 2, column=2, value=f'=IFERROR(SUMIFS({mass_rng},{stream_rng},"H2OIN"),0)')
    ws.cell(row=r + 3, column=2, value=f'=IFERROR(SUMIFS({mass_rng},{stream_rng},"O2IN")+SUMIFS({mass_rng},{stream_rng},"O2POX"),0)')
    ws.cell(row=r + 4, column=2, value=f"=IFERROR(B{r+1}/B{r}*100,0)")
    ws.cell(row=r + 5, column=2, value=f"=MIN({press_rng})")
    ws.cell(row=r + 6, column=2, value=f'=IF(AND(B{r}>0,B{r+5}>0,COUNTIF({mass_rng},"<=0")=0),"OK","CHECK")')
    return block


def _apply_inci_validation_formulas(ws, block: TableBlock) -> None:
    for r in range(block.data_start, block.data_end + 1):
        ws.cell(row=r, column=4, value=f"=IFERROR(C{r}-B{r},0)")
        ws.cell(row=r, column=5, value=f"=IFERROR(D{r}/B{r}*100,0)")


def _reorder_workbook_sheets(wb) -> None:
    """按 WORKBOOK_SHEET_ORDER 排列标签页（计算软件式流程顺序）。"""
    for target_idx, name in enumerate(WORKBOOK_SHEET_ORDER):
        if name not in wb.sheetnames:
            continue
        current_idx = wb.sheetnames.index(name)
        if current_idx != target_idx:
            wb.move_sheet(wb[name], offset=target_idx - current_idx)


def _define_named_ranges(wb, layouts: Dict[str, SheetLayout]) -> None:
    def add(name: str, sheet: str, ref: str) -> None:
        wb.defined_names.add(DefinedName(name=name, attr_text=f"'{sheet}'!{ref}"))

    in_lay = layouts.get(SHEET_INPUT)
    if in_lay:
        block_map = {b.title: b for b in in_lay.blocks}
        meta = block_map.get("工况标识")
        specs = block_map.get("操作条件（反应器）")
        feed = block_map.get("进料流股")
        chem = block_map.get("化学与平衡调参")
        checks = block_map.get("输入快速核算（Excel 公式）")
        if meta:
            add("Input_CaseID", SHEET_INPUT, f"$B${meta.data_start}")
            add("Input_BiomassSample", SHEET_INPUT, f"$B${meta.data_start + 1}")
        if specs:
            add("Input_Specs_Table", SHEET_INPUT, _block_range(specs))
        if feed:
            add("Input_Feed_Table", SHEET_INPUT, _block_range(feed))
        if chem:
            add("Input_Chem_Table", SHEET_INPUT, _block_range(chem))
        if checks:
            add("Input_Checks_Table", SHEET_INPUT, _block_range(checks))
    ws_lay = layouts.get(SHEET_WS)
    if ws_lay and ws_lay.api_key_row:
        add("Input_API_Key", SHEET_WS, f"$B${ws_lay.api_key_row}")
    if ws_lay and ws_lay.log_block:
        add("Output_WS_Log_Table", SHEET_WS, _block_range(ws_lay.log_block))
    if ws_lay and ws_lay.health_block:
        add("Output_API_Health_Table", SHEET_WS, _block_range(ws_lay.health_block))

    out_lay = layouts.get(SHEET_OUTPUT)
    if out_lay:
        block_map = {b.title: b for b in out_lay.blocks}
        kpi = block_map.get("关键物流与对标误差")
        inci_val = block_map.get("Validation — INCI 干基四组分")
        if kpi:
            add("Output_KPI_Table", SHEET_OUTPUT, _block_range(kpi))
        if inci_val:
            add("Output_INCI_Validation", SHEET_OUTPUT, _block_range(inci_val))


def _build_guide(ws, case_id: str, layout: SheetLayout) -> None:
    """软件首页：标准作业流程 + 模块入口（与各 Sheet 标签顺序一致）。"""
    layout.col_end = 4
    layout.hint_row = 3
    row = DATA_START_ROW

    workflow = pd.DataFrame(
        [
            {
                "步骤": "1",
                "模块": SHEET_INPUT,
                "任务": "编辑工况、进料、化学参数",
                "入口": "→ 打开 Model_Input",
            },
            {
                "步骤": "2",
                "模块": SHEET_WS,
                "任务": "配置口令，在 WPS JS 宏控制台运行命令",
                "入口": "→ 打开 WebService",
            },
            {
                "步骤": "3",
                "模块": SHEET_OUTPUT,
                "任务": "查看 KPI、组成与 DBI 对标",
                "入口": "→ 打开 Model_Output",
            },
            {
                "步骤": "4",
                "模块": SHEET_PFD,
                "任务": "查看流程图与流股物流卡片",
                "入口": "→ 打开 PFD",
            },
        ]
    )
    layout.blocks.append(
        _write_table(
            ws,
            workflow,
            row,
            title="标准作业流程（标签页顺序：输入 → 运行 → 结果 → 流程图）",
            editable=False,
            col_end=4,
            number_format=None,
        )
    )

    row = layout.blocks[-1].data_end + 2
    modules = pd.DataFrame(
        [
            {"模块": "模型输入", "工作表": SHEET_INPUT, "说明": "黄色单元格可编辑；公式列只读", "快捷": "→ Model_Input"},
            {"模块": "在线计算", "工作表": SHEET_WS, "说明": "联调台 · 日志 · API 密钥", "快捷": "→ WebService"},
            {"模块": "计算结果", "工作表": SHEET_OUTPUT, "说明": "物流 KPI · 组成 · 对标", "快捷": "→ Model_Output"},
            {"模块": "工艺流程", "工作表": SHEET_PFD, "说明": "PFD 示意图 + 流股卡片", "快捷": "→ PFD"},
        ]
    )
    layout.blocks.append(
        _write_table(
            ws,
            modules,
            row,
            title="模块导航",
            editable=False,
            col_end=4,
            number_format=None,
        )
    )

    row = layout.blocks[-1].data_end + 2
    meta = pd.DataFrame(
        [
            {"项目": "产品", "内容": "生物质气化 Spread Simulator"},
            {"项目": "当前工况", "内容": case_id},
            {"项目": "计算服务", "内容": WS_API_URL},
            {"项目": "内部常数", "内容": "VBE · ModelInternals（与 config JSON 同源）"},
        ]
    )
    layout.blocks.append(
        _write_table(ws, meta, row, title="工程信息", editable=False, col_end=2, number_format=None)
    )


def _build_webservice(ws, layout: SheetLayout) -> None:
    """WebService 联调台：计算软件式分区（状态 / 连接 / 运行 / 日志 / 结果）。"""
    layout.col_end = 8
    layout.hint_row = 3
    row = DATA_START_ROW

    health = pd.DataFrame(
        [
            {
                "检查项": "API 总览",
                "灯": "●",
                "状态": "待检查",
                "读数": "—",
                "说明": "绿=正常 · 黄=偏慢/密钥问题 · 红=离线/错误",
            },
            {
                "检查项": "GET /health",
                "灯": "●",
                "状态": "待检查",
                "读数": "—",
                "说明": "服务连通（无需 API Key）",
            },
            {
                "检查项": "POST 计算",
                "灯": "●",
                "状态": "待命",
                "读数": "—",
                "说明": "运行联调命令时更新",
            },
        ]
    )
    health_block = _write_table(
        ws,
        health,
        row,
        title="API 健康监控",
        editable=False,
        col_end=5,
        number_format=None,
    )
    layout.blocks.append(health_block)
    layout.health_block = health_block
    row = layout.blocks[-1].data_end + 2

    status = pd.DataFrame(
        [
            {
                "模块": "计算服务",
                "状态": "Biomass Web Client",
                "指标": "健康检查",
                "读数": "运行命令后更新",
            },
            {
                "模块": "服务地址",
                "状态": WS_API_URL,
                "指标": "计算接口",
                "读数": "/v1/compute/simulate-lite",
            },
        ]
    )
    layout.blocks.append(
        _write_table(
            ws,
            status,
            row,
            title="系统状态",
            editable=False,
            col_end=4,
            number_format=None,
        )
    )
    row = layout.blocks[-1].data_end + 2

    conn = pd.DataFrame(
        [
            {"配置项": "API 访问密钥", "值": "", "备注": "必填 · 向管理员索取 · 黄色格可编辑"},
            {"配置项": "脚本文件", "值": "WebServiceDemo.js", "备注": "向管理员索取 · 粘贴到 WPS JS 宏（Excel 用 Script Lab Code）"},
        ]
    )
    key_block = _write_table(
        ws,
        conn,
        row,
        title="连接与授权",
        editable=True,
        value_cols=(2,),
        col_end=3,
        number_format=None,
    )
    layout.blocks.append(key_block)
    for r in range(key_block.data_start, key_block.data_end + 1):
        if "API" in str(ws.cell(row=r, column=1).value or ""):
            layout.api_key_row = r
            break

    row = layout.blocks[-1].data_end + 2
    quick = pd.DataFrame(
        [
            {"#": "1", "操作": "安装 Script Lab 并粘贴 WebServiceDemo.js", "说明": "插入 → 加载项；脚本见 export/js/（WPS 用户用 xlsm 内嵌宏）"},
            {"#": "2", "操作": "填写访问口令", "说明": "见上方「连接与授权」黄色格并保存"},
            {"#": "3", "操作": "Script Lab Console 执行下方命令", "说明": "日志区自动刷新；不必打开浏览器控制台"},
            {"#": "4", "操作": "查看结果", "说明": "本页日志 DONE → Model_Output 页 KPI 表"},
        ]
    )
    layout.blocks.append(
        _write_table(ws, quick, row, title="快速上手", editable=False, col_end=3, number_format=None)
    )

    row = layout.blocks[-1].data_end + 2
    cmds = pd.DataFrame(
        [
            {"#": "①", "命令": "await validateWorkbookTemplate();", "说明": "检查命名区域是否齐全（推荐先运行）"},
            {"#": "②", "命令": "await refreshApiHealthMonitor();", "说明": "刷新健康灯（绿/黄/红，无需密钥）"},
            {"#": "③", "命令": "await runWebServiceHealthCheck();", "说明": "健康检查 + 写运行日志"},
            {"#": "④", "命令": "await runWebServiceLiteDemo();", "说明": "读取 Model_Input 并计算写回 KPI"},
        ]
    )
    layout.blocks.append(
        _write_table(
            ws,
            cmds,
            row,
            title="运行命令（Script Lab Console 逐条粘贴；WPS 用 JS 宏控制台）",
            editable=False,
            col_end=3,
            number_format=None,
        )
    )

    row = layout.blocks[-1].data_end + 2
    log_placeholder = pd.DataFrame(
        [{"时间": "—", "步骤": "待命", "说明": "执行运行命令后自动刷新"}]
        + [{"时间": "", "步骤": "", "说明": ""} for _ in range(9)]
    )
    log_block = _write_table(
        ws,
        log_placeholder,
        row,
        title="运行日志",
        editable=False,
        col_end=3,
        number_format=None,
    )
    layout.blocks.append(log_block)
    layout.log_block = log_block

    row = layout.blocks[-1].data_end + 2
    layout.nav_row = row
    ws.cell(row=row, column=1, value="→ 查看计算结果（Model_Output · 关键物流与对标误差）")

    row += 2
    tips = pd.DataFrame(
        [
            {"现象": "TEMPLATE · 缺少命名区域", "处理": "运行 build_simulator_workbook.py 重建 xlsx；见运行日志「修复」行"},
            {"现象": "ERROR · 缺少 API Key", "处理": "在「连接与授权」填写 API 访问密钥"},
            {"现象": "HTTP 401", "处理": "密钥无效，联系管理员更新后重试"},
            {"现象": "Load failed", "处理": "检查网络 / HTTPS；WPS 用户用 JS 宏运行同一脚本"},
        ]
    )
    layout.blocks.append(
        _write_table(ws, tips, row, title="故障诊断", editable=False, col_end=2, number_format=None)
    )

    layout.footer_row = layout.blocks[-1].data_end + 2


def _build_model_input(
    ws,
    case_id: str,
    feed_df: pd.DataFrame,
    specs_df: pd.DataFrame,
    chem_df: pd.DataFrame,
    layout: SheetLayout,
) -> None:
    layout.hint_row = 3
    layout.subtitle = f"工况 {case_id} · 步骤 1/4 · 修改黄色单元格后前往 WebService 运行"
    _init_sheet_header(ws, layout, "模型输入", layout.subtitle)
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
            col_end=4,
            number_format="#,##0.0",
        )
    )
    _apply_specs_conversion_formulas(ws, layout.blocks[-1])
    row = layout.blocks[-1].data_end + 3
    layout.blocks.append(
        _write_table(
            ws,
            _prepare_feed_display(feed_df),
            row,
            title="进料流股",
            editable=True,
            value_cols=(2, 3, 4),
            col_end=5,
            number_format="#,##0.0",
        )
    )
    _apply_feed_formulas(ws, layout.blocks[-1])
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
    row = layout.blocks[-1].data_end + 3
    layout.blocks.append(_build_input_quick_checks(ws, row, feed_block=layout.blocks[-2]))

    row = layout.blocks[-1].data_end + 2
    layout.nav_row = row
    ws.cell(
        row=row,
        column=1,
        value=f"→ 下一步：到「{SHEET_WS}」运行计算    ·    「{SHEET_OUTPUT}」查看结果",
    )


def _build_model_output(
    ws,
    res: SimulationResult,
    layout: SheetLayout,
) -> None:
    layout.hint_row = 3
    layout.subtitle = "步骤 3/4 · 只读" + (
        f" · 匹配 {res.matched_case}" if res.matched_case else ""
    )
    _init_sheet_header(ws, layout, "计算结果", layout.subtitle)
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
        val_df["偏差(pp)"] = None
        val_df["相对误差(%)"] = None
        layout.blocks.append(
            _write_table(
                ws,
                val_df,
                row,
                title="Validation — INCI 干基四组分",
                editable=False,
                value_cols=(2, 3, 4, 5),
                col_end=5,
                number_format="0.00",
            )
        )
        _apply_inci_validation_formulas(ws, layout.blocks[-1])
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

    row = layout.blocks[-1].data_end + 2
    layout.nav_row = row
    ws.cell(
        row=row,
        column=1,
        value=f"→ 返回「{SHEET_INPUT}」改参数  ·  「{SHEET_WS}」重算  ·  「{SHEET_PFD}」看流程图",
    )


def _build_model_output_placeholder(ws, layout: SheetLayout) -> None:
    layout.hint_row = 3
    layout.subtitle = f"步骤 3/4 · 先在「{SHEET_WS}」运行命令，KPI 将写入下方表格"
    _init_sheet_header(ws, layout, "计算结果", layout.subtitle)
    row = DATA_START_ROW
    kpi = pd.DataFrame(
        [
            {"指标": "TOTAL_FEED_KG_H", "数值": None, "单位": "kg/h"},
            {"指标": "INCI_FEED_KG_H", "数值": None, "单位": "kg/h"},
            {"指标": "RGPOX_FEED_KG_H", "数值": None, "单位": "kg/h"},
            {"指标": "SLAG_FEED_KG_H", "数值": None, "单位": "kg/h"},
            {"指标": "O2IN_SUM_MOL_PCT", "数值": None, "单位": "%"},
            {"指标": "NEGATIVE_FEED_COUNT", "数值": None, "单位": "-"},
        ]
    )
    block = _write_table(
        ws,
        kpi,
        row,
        title="关键物流与对标误差（WebService 联调后自动填充）",
        editable=False,
        value_cols=(2,),
        col_end=3,
        number_format="#,##0.0",
    )
    layout.blocks.append(block)
    layout.kpi_row_start = block.data_start
    layout.kpi_row_end = block.data_end
    row = block.data_end + 3
    msg = pd.DataFrame(
        {
            "说明": [
                "运行 runWebServiceLiteDemo() 后，上表将被在线计算结果覆盖。",
                "完整 INCI/RGPOX 组成表需 Streamlit 仿真或导出时 run_simulation=True。",
            ]
        }
    )
    layout.blocks.append(
        _write_table(ws, msg, row, title="状态", editable=False, col_end=1, number_format=None)
    )
    row = layout.blocks[-1].data_end + 2
    layout.nav_row = row
    ws.cell(row=row, column=1, value=f"→ 「{SHEET_WS}」运行计算    ·    「{SHEET_PFD}」工艺流程")


def _build_pfd(
    ws,
    feed_df: pd.DataFrame,
    result: Optional[SimulationResult],
    layout: SheetLayout,
) -> List:
    layout.hint_row = 3
    layout.subtitle = "步骤 4/4 · 示意图 + 流股卡片（随输入/结果更新）"
    _init_sheet_header(ws, layout, "工艺流程图", layout.subtitle)
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
        # 官方流程图较大，限制在 PFD 页左侧区域，右侧留给流股卡片
        max_w, max_h = (680, 520)
        if png_path.name == PFD_WORKBOOK_IMAGE.name:
            max_w, max_h = (700, 530)
        scale = min(max_w / max(img.width, 1), max_h / max(img.height, 1), 1.0)
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
    """构建 Spread Simulator 前端工作簿（Guide / WebService / Input / PFD / Output）。"""
    feed_df = feed_df if feed_df is not None else build_feed_df(case_id)
    specs_df = specs_df if specs_df is not None else build_specs_df()
    chem_df = chem_df if chem_df is not None else build_chem_df(case_id)

    if result is None and run_simulation:
        result = run_fixed_temperature_simulation(feed_df, specs_df, chem_df)

    if write_vba:
        write_vba_internals_module(VBA_EXPORT_DIR)

    # 标注 SVG 仍可选生成；Excel 嵌入优先使用 export/assets/流程示意图.png
    _, annotated_png = export_annotated_pfd(feed_df, result, case_id=case_id)
    png_path = resolve_pfd_workbook_image(annotated_png=annotated_png)

    layouts: Dict[str, SheetLayout] = {
        SHEET_GUIDE: SheetLayout(sheet=SHEET_GUIDE, title_row=1, hint_row=3, col_end=2),
        SHEET_WS: SheetLayout(sheet=SHEET_WS, title_row=1, hint_row=3, col_end=8),
        SHEET_PFD: SheetLayout(
            sheet=SHEET_PFD,
            title_row=1,
            hint_row=3,
            col_end=10,
            pfd_image_anchor="B5",
            pfd_cards_origin=(4, 12),
        ),
        SHEET_INPUT: SheetLayout(sheet=SHEET_INPUT, title_row=1, hint_row=3, col_end=5),
        SHEET_OUTPUT: SheetLayout(sheet=SHEET_OUTPUT, title_row=1, hint_row=3, col_end=5),
    }

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        wb = writer.book
        for name in WORKBOOK_SHEET_ORDER:
            wb.create_sheet(title=name)
        # 删除默认 Sheet
        if "Sheet" in wb.sheetnames:
            del wb["Sheet"]

        _build_guide(wb[SHEET_GUIDE], case_id, layouts[SHEET_GUIDE])
        _build_webservice(wb[SHEET_WS], layouts[SHEET_WS])
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
    _reorder_workbook_sheets(wb)
    format_workbook(wb, layouts=layouts)
    _define_named_ranges(wb, layouts)
    _apply_workbook_hyperlinks(wb, layouts)
    out_buf = BytesIO()
    wb.save(out_buf)
    wb.close()
    data = _embed_pfd_image(out_buf.getvalue(), png_path, layouts[SHEET_PFD])
    return data


def _apply_cell_sheet_link(cell, sheet: str, *, bold: bool = False) -> None:
    cell.hyperlink = f"#{sheet}!A1"
    cell.font = XLFont(
        name="Calibri",
        size=12 if bold else 11,
        bold=bold,
        underline="single",
        color="2563EB",
    )


def _apply_workbook_hyperlinks(wb, layouts: Dict[str, SheetLayout]) -> None:
    """工作簿内跨表导航链接。"""
    exact_links = {
        "→ 打开 Model_Input": SHEET_INPUT,
        "→ Model_Input": SHEET_INPUT,
        "→ 打开 WebService": SHEET_WS,
        "→ WebService": SHEET_WS,
        "→ 打开 Model_Output": SHEET_OUTPUT,
        "→ Model_Output": SHEET_OUTPUT,
        "→ 打开 PFD": SHEET_PFD,
        "→ PFD": SHEET_PFD,
    }
    if SHEET_GUIDE in wb.sheetnames:
        for row in wb[SHEET_GUIDE].iter_rows(min_col=1, max_col=6):
            for cell in row:
                val = cell.value
                if isinstance(val, str) and val.strip() in exact_links:
                    _apply_cell_sheet_link(cell, exact_links[val.strip()])

    ws_lay = layouts.get(SHEET_WS)
    if ws_lay and ws_lay.nav_row and SHEET_WS in wb.sheetnames:
        cell = wb[SHEET_WS].cell(row=ws_lay.nav_row, column=1)
        if cell.value and "Model_Output" in str(cell.value):
            _apply_cell_sheet_link(cell, SHEET_OUTPUT, bold=True)


def write_simulator_workbook(
    path: Path | str | None = None,
    *,
    wps_ready: bool = False,
    wps_path: Path | str | None = None,
    **kwargs: Any,
) -> Path:
    out = Path(path) if path is not None else DEFAULT_EXPORT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    data = build_simulator_workbook(**kwargs)
    out.write_bytes(data)
    if wps_ready:
        from .wps_jsa_pack import write_wps_simulator_workbook

        wps_out = Path(wps_path) if wps_path is not None else DEFAULT_WPS_EXPORT_PATH
        write_wps_simulator_workbook(data, wps_out)
    return out
