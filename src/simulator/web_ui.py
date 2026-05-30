"""Streamlit 网页计算器：PFD 流股进料、可编辑生物质分析、高阶调参。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Mapping, Optional, Tuple

import pandas as pd

from .backend import run_fixed_temperature_simulation
from .contracts import SimulationResult

from .data import REFERENCE_CASES, build_chem_df, build_feed_df, build_specs_df
from .elemental import BIOMASS_ANALYSIS_CHEM_KEYS, BIOMASS_SAMPLES
from .parameters import ATOMIC_WEIGHT, DEFAULT_CHEMISTRY_SETUP, DEFAULT_REACTOR_SPECS, MOLECULAR_WEIGHT
from .rgpox import empirical_formula_mw, parse_empirical_formula
from .pfd_diagram import FEED_TO_PFD, PFD_WORKBOOK_IMAGE

WET_MAIN_SPECIES: Tuple[str, ...] = ("H2", "CO", "CO2", "CH4", "H2O")

SectionId = Literal["INCI", "RGPOX", "SLAG"]
UiMode = Literal["quick", "feeds", "tuning"]

UI_MODE_OPTIONS: Tuple[Tuple[UiMode, str], ...] = (
    ("feeds", "进料扩展"),
    ("tuning", "物性调参"),
)


@dataclass(frozen=True)
class PfdFeedLine:
    """PFD 标签下的单条模型进料线（可多条汇入同一 PFD stream）。"""

    pfd_stream_id: str
    section: SectionId
    line_label: str
    backend_stream: str
    default_temp_c: float
    default_pressure_bar: float = 15.0


# 模型 Stream 名 → 默认温压；PFD 编号见 pfd_diagram.FEED_TO_PFD
PFD_FEED_LINES: Tuple[PfdFeedLine, ...] = (
    # —— INCI 边界 ——
    PfdFeedLine("13C-4", "INCI", "生物质", "Biomass", 25.0),
    PfdFeedLine("13C-4", "INCI", "CO₂ 进料", "CO2IN", 25.0),
    PfdFeedLine("13C-4", "INCI", "碳进料 CIN", "CIN", 25.0),
    PfdFeedLine("13HS1-1", "INCI", "工艺水 / 蒸汽", "H2OIN", 285.0),
    PfdFeedLine("13OG2-1", "INCI", "氧化剂（全流股质量）", "O2IN", 280.0),
    PfdFeedLine("13N2-1", "INCI", "N₂ 补充进料", "N2IN", 25.0),
    # —— RGPOX ——
    PfdFeedLine("15OG1", "RGPOX", "POX 用氧（全流股质量）", "O2POX", 20.0),
    # —— SLAG / 返气（进入 SLAG 单元，非 RGPOX 主进料）——
    PfdFeedLine("SLAG-返气", "SLAG", "O₂", "POSTO2", 280.0),
    PfdFeedLine("SLAG-返气", "SLAG", "H₂O", "POSTH2O", 280.0),
    PfdFeedLine("SLAG-返气", "SLAG", "CO₂", "POSTCO2", 250.0),
)

PFD_SECTION_LABELS: Dict[SectionId, str] = {
    "INCI": "INCI 进料（Unit 13 边界）",
    "RGPOX": "RGPOX 进料（Unit 15）",
    "SLAG": "SLAG 段返气 / 补充（POST*）",
}

BACKEND_STREAMS: Tuple[str, ...] = tuple(dict.fromkeys(line.backend_stream for line in PFD_FEED_LINES))

O2IN_COMPOSITION_KEYS: Tuple[str, ...] = ("O2", "N2", "Ar")
O2IN_CHEM_FIELDS: Dict[str, str] = {
    "O2": "O2IN O2 mol%",
    "N2": "O2IN N2 mol%",
    "Ar": "O2IN Ar mol%",
}

BIOMASS_UI_FIELDS: Tuple[Tuple[str, str, str], ...] = (
    ("mad_pct", "收到基水分 Mad (%)", "工分"),
    ("ad_pct", "干基灰分 Ad (%)", "工分"),
    ("cd_pct_dry", "干基碳 C (%)", "元分（干基）"),
    ("hd_pct_dry", "干基氢 H (%)", "元分（干基）"),
    ("od_pct_dry", "干基氧 O (%)", "元分（干基）"),
    ("nd_pct_dry", "干基氮 N (%)", "元分（干基）"),
    ("sd_pct_dry", "干基硫 S (%)", "元分（干基）"),
)


@dataclass(frozen=True)
class TuningParam:
    field: str
    label: str
    help_text: str
    reference: str
    section: str
    kind: Literal["number", "text", "select"] = "number"
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step: Optional[float] = None
    options: Optional[Tuple[str, ...]] = None


def _ref(val: Any) -> str:
    return f"Case-1 参考：`{val}`"


TUNING_PARAMS: Tuple[TuningParam, ...] = (
    TuningParam(
        "TA DeltaT WGS (C)",
        "INCI · WGS ΔT (°C)",
        "受限平衡 WGS 参考温度偏移；湿基收口约 +40°C。",
        _ref("+40"),
        "INCI 受限平衡",
        min_value=-200.0,
        max_value=200.0,
        step=5.0,
    ),
    TuningParam(
        "TA DeltaT Meth (C)",
        "INCI · 甲烷化 ΔT (°C)",
        "甲烷化 TA；Case-1 约 +350°C。",
        _ref("+350"),
        "INCI 受限平衡",
        min_value=-200.0,
        max_value=500.0,
        step=10.0,
    ),
    TuningParam(
        "WGS Equilibrium Approach Eta",
        "INCI · WGS η",
        "1.0 = 完全趋近。",
        _ref("1.0"),
        "INCI 受限平衡",
        min_value=0.0,
        max_value=1.0,
        step=0.05,
    ),
    TuningParam(
        "Meth Equilibrium Approach Eta",
        "INCI · 甲烷化 η",
        "1.0 = 完全趋近。",
        _ref("1.0"),
        "INCI 受限平衡",
        min_value=0.0,
        max_value=1.0,
        step=0.05,
    ),
    TuningParam(
        "RGPOX TA DeltaT WGS (C)",
        "RGPOX · WGS ΔT (°C)",
        "15PGR-1 湿基对标约 −130°C。",
        _ref("-130"),
        "RGPOX 受限平衡",
        min_value=-250.0,
        max_value=100.0,
        step=5.0,
    ),
    TuningParam(
        "RGPOX TA DeltaT Meth (C)",
        "RGPOX · 甲烷化 ΔT (°C)",
        "RGPOX 段甲烷化 TA。",
        _ref("0"),
        "RGPOX 受限平衡",
        min_value=-200.0,
        max_value=500.0,
        step=10.0,
    ),
    TuningParam(
        "RGPOX WGS Equilibrium Approach Eta",
        "RGPOX · WGS η",
        "RGPOX 段 WGS 趋近度。",
        _ref("1.0"),
        "RGPOX 受限平衡",
        min_value=0.0,
        max_value=1.0,
        step=0.05,
    ),
    TuningParam(
        "RGPOX Meth Equilibrium Approach Eta",
        "RGPOX · 甲烷化 η",
        "RGPOX 段甲烷化趋近度。",
        _ref("1.0"),
        "RGPOX 受限平衡",
        min_value=0.0,
        max_value=1.0,
        step=0.05,
    ),
    TuningParam(
        "Biomass VM Dry wt%",
        "干燥基挥发分 VM (%)",
        "Hamel 热解分配。",
        _ref("75"),
        "热解与 Tar",
        min_value=0.0,
        max_value=100.0,
        step=1.0,
    ),
    TuningParam(
        "Tar Yield Factor",
        "Tar 产率表达式",
        "如 `0.01 * C_dry`。",
        _ref("0.01 * C_dry"),
        "热解与 Tar",
        kind="text",
    ),
    TuningParam(
        "Tar target H/C",
        "Tar 目标 H/C",
        "RGPOX 前 tar 挥发分氢碳比。",
        _ref("1.2"),
        "热解与 Tar",
        min_value=0.5,
        max_value=2.5,
        step=0.05,
    ),
    TuningParam(
        "Pyrolysis Scheme",
        "热解方案",
        "当前后端为 Hamel。",
        _ref("hamel"),
        "热解与 Tar",
        kind="select",
        options=("hamel",),
    ),
    TuningParam(
        "Pyrolysis Tar Carbon Frac",
        "热解碳进 Tar 比例",
        "0 为默认路径。",
        _ref("0"),
        "热解与 Tar",
        min_value=0.0,
        max_value=1.0,
        step=0.05,
    ),
    TuningParam(
        "Biomass N to NH3 Frac",
        "生物质 N → NH₃",
        "释放氮中进入 NH₃ 的份额。",
        _ref("0.016"),
        "生物质 N / S",
        min_value=0.0,
        max_value=1.0,
        step=0.002,
    ),
    TuningParam(
        "Biomass S Release Frac",
        "生物质 S 释放比例",
        "进入气相硫化物的硫释放份额。",
        _ref("0.45"),
        "生物质 N / S",
        min_value=0.0,
        max_value=1.0,
        step=0.05,
    ),
    TuningParam(
        "H2S/COS split to H2S",
        "硫化物进 H₂S 比例",
        "其余进入 COS。",
        _ref("0.961"),
        "生物质 N / S",
        min_value=0.0,
        max_value=1.0,
        step=0.02,
    ),
)

TUNING_SECTIONS: Tuple[str, ...] = tuple(dict.fromkeys(p.section for p in TUNING_PARAMS))


def pfd_image_path() -> Optional[str]:
    if PFD_WORKBOOK_IMAGE.is_file():
        return str(PFD_WORKBOOK_IMAGE)
    return None


def biomass_analysis_from_sample(sample_id: str) -> Dict[str, float]:
    s = BIOMASS_SAMPLES[sample_id]
    return {
        "preset": sample_id,
        "mad_pct": s.mad_pct,
        "ad_pct": s.ad_pct,
        "cd_pct_dry": s.cd_pct_dry,
        "hd_pct_dry": s.hd_pct_dry,
        "nd_pct_dry": s.nd_pct_dry,
        "sd_pct_dry": s.sd_pct_dry,
        "od_pct_dry": s.od_pct_dry,
    }


def lines_by_section(section: SectionId) -> Tuple[PfdFeedLine, ...]:
    return tuple(line for line in PFD_FEED_LINES if line.section == section)


def group_lines_by_pfd_stream(lines: Tuple[PfdFeedLine, ...]) -> List[Tuple[str, Tuple[PfdFeedLine, ...]]]:
    order: List[str] = []
    buckets: Dict[str, List[PfdFeedLine]] = {}
    for line in lines:
        if line.pfd_stream_id not in buckets:
            order.append(line.pfd_stream_id)
            buckets[line.pfd_stream_id] = []
        buckets[line.pfd_stream_id].append(line)
    return [(pid, tuple(buckets[pid])) for pid in order]


def _feed_row_defaults(case_id: str, backend_stream: str, temp_c: float, p_bar: float) -> Dict[str, float]:
    case = REFERENCE_CASES[case_id]
    mass = float(case["feeds"].get(backend_stream, (0.0, temp_c, p_bar))[0])
    tpl = case["feeds"].get(backend_stream, (mass, temp_c, p_bar))
    return {
        "mass_kg_h": mass,
        "temp_c": float(tpl[1]) if len(tpl) > 1 else temp_c,
        "pressure_bar": float(tpl[2]) if len(tpl) > 2 else p_bar,
    }


def default_pfd_feeds(case_id: str, system_p_bar: float) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for line in PFD_FEED_LINES:
        out[line.backend_stream] = _feed_row_defaults(
            case_id,
            line.backend_stream,
            line.default_temp_c,
            system_p_bar,
        )
    return out


def default_o2in_composition() -> Dict[str, float]:
    return {
        "O2": float(DEFAULT_CHEMISTRY_SETUP["O2IN O2 mol%"]),
        "N2": float(DEFAULT_CHEMISTRY_SETUP["O2IN N2 mol%"]),
        "Ar": float(DEFAULT_CHEMISTRY_SETUP["O2IN Ar mol%"]),
    }


def default_inputs(case_id: str = "Case-1") -> Dict[str, Any]:
    sample_id = REFERENCE_CASES[case_id]["sample"]
    chem = {row["Field"]: row["Value"] for _, row in build_chem_df(case_id).iterrows()}
    return {
        "case_id": case_id,
        "system_p_bar": float(DEFAULT_REACTOR_SPECS["SYSTEM_P_BAR"]),
        "biomass": biomass_analysis_from_sample(sample_id),
        "pfd_feeds": default_pfd_feeds(case_id, float(DEFAULT_REACTOR_SPECS["SYSTEM_P_BAR"])),
        "o2in_composition": default_o2in_composition(),
        "o2pox": {"purity_vol_pct": float(DEFAULT_CHEMISTRY_SETUP["O2 Purity vol%"])},
        "chemistry": {p.field: chem.get(p.field, DEFAULT_CHEMISTRY_SETUP.get(p.field)) for p in TUNING_PARAMS},
    }


def init_session_state() -> None:
    sess = st_session()
    if "inputs" not in sess:
        sess["inputs"] = default_inputs("Case-1")
    if "result" not in sess:
        sess["result"] = None
    if "sidebar_case" not in sess:
        sess["sidebar_case"] = sess["inputs"]["case_id"]
    if "ui_mode" not in sess or sess["ui_mode"] == "quick":
        sess["ui_mode"] = "feeds"
    if "solve_errors" not in sess:
        sess["solve_errors"] = []


def st_session() -> Dict[str, Any]:
    import streamlit as st

    return st.session_state


def apply_case_template(case_id: str) -> None:
    st_session()["inputs"] = default_inputs(case_id)
    st_session()["result"] = None


def apply_biomass_preset(inputs: Dict[str, Any], preset_id: str) -> None:
    inputs["biomass"] = biomass_analysis_from_sample(preset_id)


def build_feed_df_from_inputs(inputs: Mapping[str, Any]) -> pd.DataFrame:
    case_id = str(inputs["case_id"])
    base = build_feed_df(case_id)
    pfd_feeds: Dict[str, Dict[str, float]] = dict(inputs.get("pfd_feeds") or {})
    for idx, stream in enumerate(base["Stream"]):
        row = pfd_feeds.get(str(stream))
        if not row:
            continue
        base.at[idx, "MassFlow_kg_h"] = float(row.get("mass_kg_h", 0.0))
        if "temp_c" in row:
            base.at[idx, "Temp_C"] = float(row["temp_c"])
        if "pressure_bar" in row:
            base.at[idx, "Pressure_bar"] = float(row["pressure_bar"])
    return base


def build_specs_df_from_inputs(inputs: Mapping[str, Any]) -> pd.DataFrame:
    df = build_specs_df()
    p_bar = float(inputs.get("system_p_bar", DEFAULT_REACTOR_SPECS["SYSTEM_P_BAR"]))
    df.loc[df["Parameter"] == "SYSTEM_P_BAR", "Value"] = p_bar
    return df


def build_chem_df_from_inputs(inputs: Mapping[str, Any]) -> pd.DataFrame:
    case_id = str(inputs["case_id"])
    df = build_chem_df(case_id)
    biomass: Dict[str, Any] = dict(inputs.get("biomass") or {})
    preset = str(biomass.get("preset", REFERENCE_CASES[case_id]["sample"]))
    df.loc[df["Field"] == "Sample", "Value"] = preset

    attr_to_chem = {v: k for k, v in BIOMASS_ANALYSIS_CHEM_KEYS.items()}
    for attr, _label, _group in BIOMASS_UI_FIELDS:
        chem_key = attr_to_chem.get(attr)
        if chem_key and attr in biomass:
            if (df["Field"] == chem_key).any():
                df.loc[df["Field"] == chem_key, "Value"] = float(biomass[attr])
            else:
                df = pd.concat(
                    [df, pd.DataFrame([{"Field": chem_key, "Value": float(biomass[attr])}])],
                    ignore_index=True,
                )

    o2in = dict(inputs.get("o2in_composition") or {})
    for sp, chem_field in O2IN_CHEM_FIELDS.items():
        if sp in o2in:
            df.loc[df["Field"] == chem_field, "Value"] = float(o2in[sp])

    o2pox = dict(inputs.get("o2pox") or {})
    if "purity_vol_pct" in o2pox:
        df.loc[df["Field"] == "O2 Purity vol%", "Value"] = float(o2pox["purity_vol_pct"])

    chem_overrides: Dict[str, Any] = dict(inputs.get("chemistry") or {})
    for field, val in chem_overrides.items():
        mask = df["Field"] == field
        if mask.any():
            df.loc[mask, "Value"] = val
    return df


def biomass_sample_options() -> List[str]:
    return sorted(BIOMASS_SAMPLES.keys(), key=lambda s: (len(s), s))


def feed_stream_table(inputs: Mapping[str, Any], section: SectionId) -> pd.DataFrame:
    """Aspen 风格 STREAM 表（按工段）。"""
    pfd_feeds = dict(inputs.get("pfd_feeds") or {})
    rows = []
    for line in lines_by_section(section):
        data = pfd_feeds.get(
            line.backend_stream,
            {
                "mass_kg_h": 0.0,
                "temp_c": line.default_temp_c,
                "pressure_bar": line.default_pressure_bar,
            },
        )
        phase = "VAPOR" if line.backend_stream in ("O2IN", "H2OIN", "N2IN", "O2POX", "POSTO2", "POSTH2O", "POSTCO2") else "MIXED"
        rows.append(
            {
                "PFD_Tag": line.pfd_stream_id,
                "Stream_ID": line.backend_stream,
                "Description": line.line_label,
                "Phase": phase,
                "MassFlow_kg_h": float(data.get("mass_kg_h", 0.0)),
                "Temp_C": float(data.get("temp_c", line.default_temp_c)),
                "Pressure_bar": float(data.get("pressure_bar", line.default_pressure_bar)),
            }
        )
    return pd.DataFrame(rows)


def apply_feed_stream_table(inputs: Dict[str, Any], df: pd.DataFrame) -> None:
    pfd_feeds = inputs.setdefault("pfd_feeds", {})
    for _, row in df.iterrows():
        key = str(row["Stream_ID"])
        pfd_feeds[key] = {
            "mass_kg_h": float(row["MassFlow_kg_h"]),
            "temp_c": float(row["Temp_C"]),
            "pressure_bar": float(row["Pressure_bar"]),
        }


def feed_stream_sidebar_table(inputs: Mapping[str, Any], section: SectionId) -> pd.DataFrame:
    """侧栏专用：仅保留流股名 + 三个可编辑数值列（避免宽表把输入列挤出视口）。"""
    pfd_feeds = dict(inputs.get("pfd_feeds") or {})
    rows = []
    for line in lines_by_section(section):
        data = pfd_feeds.get(
            line.backend_stream,
            {
                "mass_kg_h": 0.0,
                "temp_c": line.default_temp_c,
                "pressure_bar": line.default_pressure_bar,
            },
        )
        rows.append(
            {
                "流股": line.line_label,
                "kg_h": float(data.get("mass_kg_h", 0.0)),
                "T_C": float(data.get("temp_c", line.default_temp_c)),
                "P_bar": float(data.get("pressure_bar", line.default_pressure_bar)),
            }
        )
    return pd.DataFrame(rows)


def apply_feed_stream_sidebar_table(
    inputs: Dict[str, Any],
    df: pd.DataFrame,
    section: SectionId,
) -> None:
    """与 feed_stream_sidebar_table 行序一致写回 pfd_feeds。"""
    pfd_feeds = inputs.setdefault("pfd_feeds", {})
    lines = lines_by_section(section)
    if len(df) != len(lines):
        return
    for idx, line in enumerate(lines):
        row = df.iloc[idx]
        pfd_feeds[line.backend_stream] = {
            "mass_kg_h": float(row["kg_h"]),
            "temp_c": float(row["T_C"]),
            "pressure_bar": float(row["P_bar"]),
        }


def feed_stream_sidebar_column_config():
    import streamlit as st

    return {
        "流股": st.column_config.TextColumn("流股", disabled=True, width="medium"),
        "kg_h": st.column_config.NumberColumn(
            "流量 kg/h ✎",
            format="%.1f",
            min_value=0.0,
            step=10.0,
            width="small",
        ),
        "T_C": st.column_config.NumberColumn(
            "°C ✎", format="%.0f", step=5.0, width="small"
        ),
        "P_bar": st.column_config.NumberColumn(
            "bar ✎", format="%.1f", min_value=0.1, step=0.5, width="small"
        ),
    }


def _feed_line_state(
    inputs: Mapping[str, Any],
    line: PfdFeedLine,
) -> Dict[str, float]:
    pfd_feeds = dict(inputs.get("pfd_feeds") or {})
    data = pfd_feeds.get(line.backend_stream, {})
    return {
        "mass_kg_h": float(data.get("mass_kg_h", 0.0)),
        "temp_c": float(data.get("temp_c", line.default_temp_c)),
        "pressure_bar": float(data.get("pressure_bar", line.default_pressure_bar)),
    }


def write_pfd_feed_line(
    inputs: Dict[str, Any],
    line: PfdFeedLine,
    *,
    mass_kg_h: float,
    temp_c: float,
    pressure_bar: float,
) -> None:
    """写回单条进料（供数字框 UI 与测试使用）。"""
    inputs.setdefault("pfd_feeds", {})[line.backend_stream] = {
        "mass_kg_h": float(mass_kg_h),
        "temp_c": float(temp_c),
        "pressure_bar": float(pressure_bar),
    }


def render_section_feed_number_inputs(inputs: Dict[str, Any], section: SectionId) -> None:
    """侧栏/主区：按流股展示数字框（流量 · 温度 · 压力），避免窄侧栏表格裁列。"""
    import streamlit as st

    case_id = str(inputs.get("case_id", "Case-1"))
    lines = lines_by_section(section)
    for idx, line in enumerate(lines):
        if idx > 0:
            st.divider()
        cur = _feed_line_state(inputs, line)
        st.markdown(
            f'<div class="sim-feed-line-label"><b>{line.line_label}</b>'
            f' <span class="sim-feed-pfd">{line.pfd_stream_id}</span></div>',
            unsafe_allow_html=True,
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            mass = st.number_input(
                "流量 kg/h",
                value=cur["mass_kg_h"],
                min_value=0.0,
                step=10.0,
                format="%.1f",
                key=f"pfd_{case_id}_{section}_{line.backend_stream}_m",
                label_visibility="visible",
            )
        with c2:
            temp = st.number_input(
                "温度 °C",
                value=cur["temp_c"],
                step=5.0,
                format="%.0f",
                key=f"pfd_{case_id}_{section}_{line.backend_stream}_t",
            )
        with c3:
            press = st.number_input(
                "压力 bar",
                value=cur["pressure_bar"],
                min_value=0.1,
                step=0.5,
                format="%.1f",
                key=f"pfd_{case_id}_{section}_{line.backend_stream}_p",
            )
        write_pfd_feed_line(
            inputs,
            line,
            mass_kg_h=float(mass),
            temp_c=float(temp),
            pressure_bar=float(press),
        )


def render_o2in_number_inputs(inputs: Dict[str, Any]) -> None:
    """氧化剂 O2IN：三组分 mol% 数字框。"""
    import streamlit as st

    o2in = inputs.setdefault("o2in_composition", {})
    case_id = str(inputs.get("case_id", "Case-1"))
    labels = {"O2": "O₂ mol%", "N2": "N₂ mol%", "Ar": "Ar mol%"}
    cols = st.columns(3)
    for col, sp in zip(cols, O2IN_COMPOSITION_KEYS):
        with col:
            o2in[sp] = float(
                st.number_input(
                    labels[sp],
                    value=float(o2in.get(sp, 0.0)),
                    min_value=0.0,
                    max_value=100.0,
                    step=0.05,
                    format="%.3f",
                    key=f"o2in_{case_id}_{sp}",
                )
            )


def biomass_property_table(inputs: Mapping[str, Any]) -> pd.DataFrame:
    biomass = dict(inputs.get("biomass") or {})
    rows = []
    for attr, label, group in BIOMASS_UI_FIELDS:
        unit = "wt% (as-rec)" if attr == "mad_pct" else "wt% (dry)"
        rows.append(
            {
                "Tag": attr,
                "Description": label,
                "Group": group,
                "Value": float(biomass.get(attr, 0.0)),
                "Unit": unit,
            }
        )
    return pd.DataFrame(rows)


def apply_biomass_property_table(inputs: Dict[str, Any], df: pd.DataFrame) -> None:
    biomass = inputs.setdefault("biomass", {})
    for _, row in df.iterrows():
        tag = str(row["Tag"])
        if tag in {f[0] for f in BIOMASS_UI_FIELDS}:
            biomass[tag] = float(row["Value"])


def o2in_composition_table(inputs: Mapping[str, Any]) -> pd.DataFrame:
    o2in = dict(inputs.get("o2in_composition") or {})
    return pd.DataFrame(
        [{"Component": sp, "mol_pct": float(o2in.get(sp, 0.0))} for sp in O2IN_COMPOSITION_KEYS]
    )


def apply_o2in_composition_table(inputs: Dict[str, Any], df: pd.DataFrame) -> None:
    o2in = inputs.setdefault("o2in_composition", {})
    for _, row in df.iterrows():
        o2in[str(row["Component"])] = float(row["mol_pct"])


def tuning_property_table(chemistry: Mapping[str, Any], section: str) -> pd.DataFrame:
    """调参表：Value 统一为字符串，避免 data_editor 列类型冲突。"""
    rows = []
    for p in TUNING_PARAMS:
        if p.section != section:
            continue
        val = chemistry.get(p.field, DEFAULT_CHEMISTRY_SETUP.get(p.field, ""))
        rows.append(
            {
                "Parameter": p.field,
                "Description": p.label,
                "Kind": p.kind,
                "Value": "" if val is None else str(val),
                "Reference": p.reference.replace("Case-1 参考：", ""),
            }
        )
    return pd.DataFrame(rows)


def apply_tuning_property_table(chemistry: Dict[str, Any], df: pd.DataFrame) -> None:
    by_field = {p.field: p for p in TUNING_PARAMS}
    for _, row in df.iterrows():
        field = str(row["Parameter"])
        raw = str(row["Value"]).strip()
        spec = by_field.get(field)
        if spec and spec.kind == "number":
            chemistry[field] = float(raw)
        else:
            chemistry[field] = raw


def tuning_table_column_config():
    import streamlit as st

    return {
        "Parameter": st.column_config.TextColumn("Parameter", disabled=True, width="medium"),
        "Description": st.column_config.TextColumn("Description", disabled=True),
        "Kind": st.column_config.TextColumn("Kind", disabled=True, width="small"),
        "Value": st.column_config.TextColumn("Value ✎", width="medium", help="可编辑"),
        "Reference": st.column_config.TextColumn("Ref", disabled=True, width="small"),
    }


def stream_table_column_config():
    import streamlit as st

    return {
        "PFD_Tag": st.column_config.TextColumn("PFD Tag", disabled=True, width="small"),
        "Stream_ID": st.column_config.TextColumn("Stream", disabled=True, width="medium"),
        "Description": st.column_config.TextColumn("Description", disabled=True, width="medium"),
        "Phase": st.column_config.TextColumn("Phase", disabled=True, width="small"),
        "MassFlow_kg_h": st.column_config.NumberColumn(
            "Mass Flow ✎",
            format="%.2f",
            min_value=0.0,
            step=10.0,
            width="medium",
            help="可编辑：质量流量 kg/h",
        ),
        "Temp_C": st.column_config.NumberColumn(
            "T ✎", format="%.1f", step=5.0, width="small", help="可编辑：温度 °C"
        ),
        "Pressure_bar": st.column_config.NumberColumn(
            "P ✎",
            format="%.1f",
            min_value=0.1,
            step=0.5,
            width="small",
            help="可编辑：压力 bar",
        ),
    }


def pfd_feed_summary_df(inputs: Mapping[str, Any]) -> pd.DataFrame:
    """进料一览：PFD 编号 + 模型 stream。"""
    rows = []
    pfd_feeds = dict(inputs.get("pfd_feeds") or {})
    for line in PFD_FEED_LINES:
        data = pfd_feeds.get(line.backend_stream, {})
        rows.append(
            {
                "工段": line.section,
                "PFD": line.pfd_stream_id,
                "进料项": line.line_label,
                "模型 Stream": line.backend_stream,
                "kg/h": round(float(data.get("mass_kg_h", 0.0)), 2),
                "°C": round(float(data.get("temp_c", 0.0)), 1),
                "bar": round(float(data.get("pressure_bar", 0.0)), 1),
                "汇入PFD": FEED_TO_PFD.get(line.backend_stream, "—"),
            }
        )
    return pd.DataFrame(rows)


def wet_composition_df(title: str, comp: Dict[str, float]) -> pd.DataFrame:
    rows = [{"组分": sp, "湿基 vol%": round(comp.get(sp, 0.0), 3)} for sp in WET_MAIN_SPECIES]
    return pd.DataFrame(rows)


def _section_feed_kg_h(inputs: Mapping[str, Any], section: SectionId) -> float:
    pfd_feeds = dict(inputs.get("pfd_feeds") or {})
    total = 0.0
    for line in lines_by_section(section):
        total += float(pfd_feeds.get(line.backend_stream, {}).get("mass_kg_h", 0.0))
    return total


def feed_balance_preview(inputs: Mapping[str, Any]) -> Dict[str, float]:
    """未求解前的进料侧 KPI（与 Excel simulate-lite 口径接近）。"""
    pfd_feeds = dict(inputs.get("pfd_feeds") or {})
    total = sum(float(v.get("mass_kg_h", 0.0)) for v in pfd_feeds.values())
    negative = sum(
        1 for v in pfd_feeds.values() if float(v.get("mass_kg_h", 0.0)) < -1e-9
    )
    o2in = dict(inputs.get("o2in_composition") or {})
    o2in_sum = sum(float(o2in.get(sp, 0.0)) for sp in O2IN_COMPOSITION_KEYS)
    return {
        "total_feed_kg_h": total,
        "inci_feed_kg_h": _section_feed_kg_h(inputs, "INCI"),
        "rgpox_feed_kg_h": _section_feed_kg_h(inputs, "RGPOX"),
        "slag_feed_kg_h": _section_feed_kg_h(inputs, "SLAG"),
        "o2in_sum_mol_pct": o2in_sum,
        "negative_feed_count": float(negative),
    }


def validate_inputs(inputs: Mapping[str, Any]) -> List[str]:
    """提交求解前的轻量校验（人话提示）。"""
    errors: List[str] = []
    preview = feed_balance_preview(inputs)
    if preview["negative_feed_count"] > 0:
        errors.append("存在负的进料流量（kg/h），请检查各流股表。")
    o2_sum = preview["o2in_sum_mol_pct"]
    if abs(o2_sum - 100.0) > 0.5:
        errors.append(
            f"O2IN 组分 mol% 合计为 {o2_sum:.2f}%，应接近 100%。"
        )
    if preview["total_feed_kg_h"] <= 0:
        errors.append("总进料为 0，请至少填写一条流股的质量流量。")
    biomass = dict(inputs.get("biomass") or {})
    for attr, label, _ in BIOMASS_UI_FIELDS:
        v = float(biomass.get(attr, 0.0))
        if v < 0:
            errors.append(f"生物质 {label} 不能为负数。")
            break
    return errors


def run_simulation(inputs: Mapping[str, Any]) -> SimulationResult:
    return run_fixed_temperature_simulation(
        build_feed_df_from_inputs(inputs),
        build_specs_df_from_inputs(inputs),
        build_chem_df_from_inputs(inputs),
    )


def result_card_cells(
    inputs: Mapping[str, Any],
    res: SimulationResult | None,
) -> List[Tuple[str, str, str]]:
    """结果牌网格：有求解结果用模型输出，否则用进料预览。"""
    if res is not None:
        match = res.matched_case or "自定义进料"
        rmsd = res.rmsd_inci_primary_pct
        rmsd_s = f"{rmsd:.2f}%" if rmsd is not None else "—"
        return [
            ("13PGI-1 气体", f"{res.inci_top_kg_h:.0f}", "kg/h"),
            ("15PGR 气体", f"{res.pox_gas_kg_h:.0f}", "kg/h"),
            ("INCI 渣", f"{res.inci_slag_kg_h:.0f}", "kg/h"),
            ("Tar", f"{res.inci_tar_kg_h:.1f}", "kg/h"),
            ("对标", str(match), ""),
            ("INCI RMSD", rmsd_s, ""),
        ]
    prev = feed_balance_preview(inputs)
    return [
        ("总进料", f"{prev['total_feed_kg_h']:.0f}", "kg/h"),
        ("INCI 进料", f"{prev['inci_feed_kg_h']:.0f}", "kg/h"),
        ("RGPOX 进料", f"{prev['rgpox_feed_kg_h']:.0f}", "kg/h"),
        ("O2IN 合计", f"{prev['o2in_sum_mol_pct']:.2f}", "mol%"),
        ("负流量条数", f"{int(prev['negative_feed_count'])}", "条"),
        ("系统压力", f"{float(inputs.get('system_p_bar', 0)):.1f}", "bar"),
    ]


def result_status(
    inputs: Mapping[str, Any],
    res: SimulationResult | None,
    solve_errors: List[str],
) -> Tuple[Literal["idle", "ready", "ok", "warn", "error"], str]:
    if solve_errors:
        return "error", "输入待修正"
    if res is not None:
        return ("ok", "求解完成") if res.matched_case else ("ok", "自定义工况已求解")
    if inputs.get("pfd_feeds"):
        return "ready", "待计算（进料已填）"
    return "idle", "待填写进料"


def format_results_markdown(
    inputs: Mapping[str, Any],
    res: SimulationResult | None,
) -> str:
    lines = [
        f"# 生物质气化计算 · {inputs.get('case_id', '')}",
        "",
    ]
    if res is None:
        prev = feed_balance_preview(inputs)
        lines.extend(
            [
                "## 进料预览（未求解）",
                f"- 总进料: {prev['total_feed_kg_h']:.2f} kg/h",
                f"- INCI: {prev['inci_feed_kg_h']:.2f} kg/h",
                f"- RGPOX: {prev['rgpox_feed_kg_h']:.2f} kg/h",
                f"- O2IN mol% 合计: {prev['o2in_sum_mol_pct']:.2f}",
                "",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            "## 求解结果",
            f"- 对标工况: {res.matched_case or '无匹配'}",
            f"- 13PGI-1 气体: {res.inci_top_kg_h:.2f} kg/h",
            f"- 13LBS 渣: {res.inci_slag_kg_h:.2f} kg/h",
            f"- Tar: {res.inci_tar_kg_h:.2f} kg/h",
            f"- 15PGR 气体: {res.pox_gas_kg_h:.2f} kg/h",
            f"- POX 灰: {res.pox_ash_kg_h:.2f} kg/h",
        ]
    )
    if res.rmsd_inci_primary_pct is not None:
        lines.append(f"- INCI 湿基主组分 RMSD: {res.rmsd_inci_primary_pct:.2f}%")
    if res.rmsd_pox_primary_pct is not None:
        lines.append(f"- RGPOX 湿基主组分 RMSD: {res.rmsd_pox_primary_pct:.2f}%")
    lines.append("")
    return "\n".join(lines)


# 干基合成气 LHV 估算（MJ/kg，用于冷煤气效率代理）
_BIOMASS_LHV_MJ_PER_KG = 18.5
_CHAR_LHV_MJ_PER_KG = 32.8    # 纯碳 LHV（炭黑 / 未转化炭）
_DULONG_C_COEFF = 0.338
_DULONG_H_COEFF = 1.428
_DULONG_S_COEFF = 0.095
_WATER_LATENT_HEAT_MJ_PER_KG = 2.442
_SYNGAS_LHV_MJ_PER_KG: Dict[str, float] = {
    "H2": 120.0,    # 120 MJ/kg
    "CO": 10.1,     # 10.1 MJ/kg
    "CH4": 50.2,    # 50.2 MJ/kg
    "CO2": 0.0,
    "N2": 0.0,
    "Ar": 0.0,
}
def _dry_syngas_lhv_mj_per_kg(comp: Mapping[str, float]) -> float:
    """由干基 vol% 估算合成气质量加权低位热值 (MJ/kg)。"""
    mass_weighted_lhv = 0.0
    mass_denom = 0.0
    for sp, value in comp.items():
        mw = MOLECULAR_WEIGHT.get(sp)
        if mw is None or sp == "H2O":
            continue
        y = max(float(value), 0.0)
        if y <= 0.0:
            continue
        w = y * mw
        mass_denom += w
        mass_weighted_lhv += w * _SYNGAS_LHV_MJ_PER_KG.get(sp, 0.0)
    if mass_denom <= 0.0:
        return 0.0
    return mass_weighted_lhv / mass_denom  # already MJ/kg


def _dry_gas_mass_kg_h(
    wet_gas_mass_kg_h: float,
    dry_comp: Mapping[str, float],
    wet_h2o_vol_pct: float,
) -> float:
    """由湿气总质量 + 干基组成 + 湿基 H2O 体积分数反推干气质量。"""
    dry_total = sum(max(float(value), 0.0) for sp, value in dry_comp.items() if sp != "H2O")
    if wet_gas_mass_kg_h <= 0.0 or dry_total <= 0.0:
        return 0.0
    dry_avg_mw = sum(
        max(float(value), 0.0) / dry_total * MOLECULAR_WEIGHT[sp]
        for sp, value in dry_comp.items()
        if sp != "H2O" and sp in MOLECULAR_WEIGHT and float(value) > 0.0
    )
    if dry_avg_mw <= 0.0:
        return 0.0
    wet_h2o_frac = max(0.0, min(float(wet_h2o_vol_pct), 100.0)) / 100.0
    wet_avg_mw = (1.0 - wet_h2o_frac) * dry_avg_mw + wet_h2o_frac * MOLECULAR_WEIGHT["H2O"]
    if wet_avg_mw <= 0.0:
        return 0.0
    dry_mass_frac = (1.0 - wet_h2o_frac) * dry_avg_mw / wet_avg_mw
    return wet_gas_mass_kg_h * dry_mass_frac


def _dry_syngas_energy_mj_h(
    wet_gas_mass_kg_h: float,
    dry_comp: Mapping[str, float],
    wet_h2o_vol_pct: float,
) -> float:
    """干基组成对应的化学能：LHV(dry gas) × 干气质量。"""
    dry_mass_kg_h = _dry_gas_mass_kg_h(wet_gas_mass_kg_h, dry_comp, wet_h2o_vol_pct)
    if dry_mass_kg_h <= 0.0:
        return 0.0
    return dry_mass_kg_h * _dry_syngas_lhv_mj_per_kg(dry_comp)


def _stream_lhv_mj_per_kg(stream: str) -> float:
    if stream == "Biomass":
        return _BIOMASS_LHV_MJ_PER_KG
    return 0.0


def _section_feed_chemical_energy_mj_h(inputs: Mapping[str, Any], section: str) -> float:
    pfd = dict(inputs.get("pfd_feeds") or {})
    energy = 0.0
    for line in PFD_FEED_LINES:
        if line.section != section:
            continue
        mass_kg_h = float((pfd.get(line.backend_stream) or {}).get("mass_kg_h", 0.0))
        energy += max(mass_kg_h, 0.0) * _stream_lhv_mj_per_kg(line.backend_stream)
    return energy


def _total_feed_chemical_energy_mj_h(inputs: Mapping[str, Any]) -> float:
    pfd = dict(inputs.get("pfd_feeds") or {})
    energy = 0.0
    for stream, row in pfd.items():
        energy += max(float((row or {}).get("mass_kg_h", 0.0)), 0.0) * _stream_lhv_mj_per_kg(str(stream))
    return energy


def _tar_lhv_mj_per_kg(formula: str) -> float:
    """由 tar 经验式按 Dulong 相关式估算 LHV (MJ/kg)。"""
    try:
        atoms = parse_empirical_formula(str(formula))
        mw = empirical_formula_mw(str(formula))
    except (KeyError, ValueError):
        return 0.0
    if mw <= 0.0:
        return 0.0
    c_wt_pct = 100.0 * atoms.get("C", 0.0) * ATOMIC_WEIGHT["C"] / mw
    h_wt_pct = 100.0 * atoms.get("H", 0.0) * ATOMIC_WEIGHT["H"] / mw
    o_wt_pct = 100.0 * atoms.get("O", 0.0) * ATOMIC_WEIGHT["O"] / mw
    s_wt_pct = 100.0 * atoms.get("S", 0.0) * ATOMIC_WEIGHT["S"] / mw
    h_available = max(h_wt_pct - o_wt_pct / 8.0, 0.0)
    hhv = (
        _DULONG_C_COEFF * c_wt_pct
        + _DULONG_H_COEFF * h_available
        + _DULONG_S_COEFF * s_wt_pct
    )
    water_from_h_kg_per_kg = 9.0 * h_wt_pct / 100.0
    return max(hhv - _WATER_LATENT_HEAT_MJ_PER_KG * water_from_h_kg_per_kg, 0.0)


def carbon_conversion_pct(res: SimulationResult) -> Optional[float]:
    """INCI 碳元素气相转化率（含 Tar 计入气相 C）。"""
    rows = (
        res.inci_mass_audit.element_balance
        if res.inci_mass_audit is not None
        else res.element_balance
    )
    for row in rows:
        if row.stage == "INCI" and row.element == "C" and row.inlet_mol_h > 1e-9:
            return 100.0 * row.outlet_gas_mol_h / row.inlet_mol_h
    return None


def h2_co_ratio_dry(res: SimulationResult) -> Optional[float]:
    """INCI 出口干基 H2/CO（vol% 比 ≈ 摩尔比）。"""
    comp = res.inci_comp_dry_vol_pct
    co = float(comp.get("CO", 0.0))
    if co <= 1e-9:
        return None
    return float(comp.get("H2", 0.0)) / co


def cold_gas_efficiency_inci_pct(
    inputs: Mapping[str, Any],
    res: SimulationResult,
) -> Optional[float]:
    """INCI 冷煤气效率：INCI 出口干气化学能 / INCI 入口总化学能。
    当前默认工况下 INCI 入口化学能主要来自 Biomass。
    """
    energy_out = _dry_syngas_energy_mj_h(
        res.inci_top_kg_h,
        res.inci_comp_dry_full_vol_pct,
        float(res.inci_comp_wet_full_vol_pct.get("H2O", 0.0)),
    )
    if energy_out <= 0.0:
        return None
    energy_in = _section_feed_chemical_energy_mj_h(inputs, "INCI")
    if energy_in <= 0.0:
        return None
    return 100.0 * energy_out / energy_in


def cold_gas_efficiency_pox_pct(
    inputs: Mapping[str, Any],
    res: SimulationResult,
) -> Optional[float]:
    """POX 冷煤气效率：RGPOX 出口干气化学能 / POX 入口总化学能。
    POX 入口总化学能包括 INCI 出口干气、tar、入 POX 炭以及 RGPOX 边界直接进料。
    """
    energy_out = _dry_syngas_energy_mj_h(
        res.pox_gas_kg_h,
        res.pox_comp_dry_full_vol_pct,
        float(res.pox_comp_wet_vol_pct.get("H2O", 0.0)),
    )
    if energy_out <= 0.0:
        return None

    energy_inci_gas = _dry_syngas_energy_mj_h(
        res.inci_top_kg_h,
        res.inci_comp_dry_full_vol_pct,
        float(res.inci_comp_wet_full_vol_pct.get("H2O", 0.0)),
    )
    if energy_inci_gas <= 0.0:
        return None

    if res.inci_mass_audit is not None:
        char_to_pox_kg_h = res.inci_mass_audit.char_to_pox_kg_h
    else:
        char_to_pox_kg_h = 0.0
    energy_char = char_to_pox_kg_h * _CHAR_LHV_MJ_PER_KG
    tar_formula = str(DEFAULT_CHEMISTRY_SETUP.get("Tar Formula", "CHO0.082N0.01"))
    energy_tar = max(res.inci_tar_kg_h, 0.0) * _tar_lhv_mj_per_kg(tar_formula)

    energy_in = energy_inci_gas + energy_tar + energy_char + _section_feed_chemical_energy_mj_h(inputs, "RGPOX")
    if energy_in <= 1e-6:
        return None
    return 100.0 * energy_out / energy_in


def cold_gas_efficiency_pct(
    inputs: Mapping[str, Any],
    res: SimulationResult,
) -> Optional[float]:
    """综合冷煤气效率：RGPOX 最终出口干气化学能 / 全系统外部入口总化学能。
    最终产品按 RGPOX 出口干气计；Quench 加水只改变湿气质量，不应抬高 CGE。
    """
    energy_out = _dry_syngas_energy_mj_h(
        res.pox_gas_kg_h,
        res.pox_comp_dry_full_vol_pct,
        float(res.pox_comp_wet_vol_pct.get("H2O", 0.0)),
    )
    if energy_out <= 0.0:
        return None
    energy_in = _total_feed_chemical_energy_mj_h(inputs)
    if energy_in <= 0.0:
        return None
    return 100.0 * energy_out / energy_in


def _fmt_metric(value: Optional[float], *, digits: int = 1, suffix: str = "") -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}{suffix}"


def performance_summary_tiles(
    inputs: Mapping[str, Any],
    res: SimulationResult | None,
) -> List[Tuple[str, str, str, str]]:
    """右侧性能汇总：(标签, 值, 单位, 语义色 blue|green|orange|red|purple|teal)。"""
    if res is not None:
        rmsd = res.rmsd_inci_primary_pct
        cge = cold_gas_efficiency_pct(inputs, res)
        c_conv = carbon_conversion_pct(res)
        h2co = h2_co_ratio_dry(res)
        return [
            ("冷煤气效率", _fmt_metric(cge), "%", "blue"),
            ("碳转化率", _fmt_metric(c_conv), "%", "green"),
            ("H2/CO 比", _fmt_metric(h2co, digits=2), "", "orange"),
            ("粗合成气产量", f"{res.inci_pgi_total_kg_h:.0f}", "kg/h", "red"),
            ("INCI RMSD", _fmt_metric(rmsd), "%", "purple"),
            ("RGPOX 气体", f"{res.pox_gas_kg_h:.0f}", "kg/h", "teal"),
        ]
    prev = feed_balance_preview(inputs)
    return [
        ("总进料", f"{prev['total_feed_kg_h']:.0f}", "kg/h", "blue"),
        ("INCI 进料", f"{prev['inci_feed_kg_h']:.0f}", "kg/h", "green"),
        ("O2IN 合计", f"{prev['o2in_sum_mol_pct']:.1f}", "mol%", "orange"),
        ("系统压力", f"{float(inputs.get('system_p_bar', 0)):.1f}", "bar", "purple"),
    ]


def bottom_kpi_strip(
    inputs: Mapping[str, Any],
    res: SimulationResult | None,
) -> List[Tuple[str, str, str, str]]:
    """底部横向 KPI 条。"""
    if res is not None:
        return [
            ("13PGI-1 气体", f"{res.inci_top_kg_h:.0f}", "kg/h", "blue"),
            ("13LBS 渣", f"{res.inci_slag_kg_h:.0f}", "kg/h", "green"),
            ("Tar", f"{res.inci_tar_kg_h:.1f}", "kg/h", "orange"),
            ("15PGR 气体", f"{res.pox_gas_kg_h:.0f}", "kg/h", "red"),
            ("POX 灰", f"{res.pox_ash_kg_h:.1f}", "kg/h", "purple"),
            ("对标", str(res.matched_case or "自定义"), "", "teal"),
        ]
    prev = feed_balance_preview(inputs)
    return [
        ("总进料", f"{prev['total_feed_kg_h']:.0f}", "kg/h", "blue"),
        ("INCI", f"{prev['inci_feed_kg_h']:.0f}", "kg/h", "green"),
        ("RGPOX", f"{prev['rgpox_feed_kg_h']:.0f}", "kg/h", "orange"),
        ("SLAG", f"{prev['slag_feed_kg_h']:.0f}", "kg/h", "red"),
        ("O2IN Σ", f"{prev['o2in_sum_mol_pct']:.1f}", "%", "purple"),
        ("负流量", f"{int(prev['negative_feed_count'])}", "条", "teal"),
    ]


def format_results_json(
    inputs: Mapping[str, Any],
    res: SimulationResult | None,
) -> str:
    payload: Dict[str, Any] = {
        "case_id": inputs.get("case_id"),
        "system_p_bar": inputs.get("system_p_bar"),
        "feed_preview": feed_balance_preview(inputs),
    }
    if res is not None:
        payload["solve"] = {
            "matched_case": res.matched_case,
            "inci_top_kg_h": res.inci_top_kg_h,
            "inci_slag_kg_h": res.inci_slag_kg_h,
            "inci_tar_kg_h": res.inci_tar_kg_h,
            "pox_gas_kg_h": res.pox_gas_kg_h,
            "pox_ash_kg_h": res.pox_ash_kg_h,
            "rmsd_inci_primary_pct": res.rmsd_inci_primary_pct,
            "rmsd_pox_primary_pct": res.rmsd_pox_primary_pct,
        }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def comparison_wet_df(expected: Dict[str, float], model: Dict[str, float]) -> pd.DataFrame:
    rows = []
    for sp in WET_MAIN_SPECIES:
        ref = expected.get(sp)
        sim = model.get(sp, 0.0)
        delta = sim - ref if ref is not None else None
        rows.append(
            {
                "组分": sp,
                "DBI": round(ref, 3) if ref is not None else None,
                "模型": round(sim, 3),
                "Δ pp": round(delta, 3) if delta is not None else None,
            }
        )
    return pd.DataFrame(rows)
