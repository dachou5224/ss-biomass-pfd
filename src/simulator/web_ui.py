"""Streamlit 网页计算器：PFD 流股进料、可编辑生物质分析、高阶调参。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Mapping, Optional, Tuple

import pandas as pd

from .data import REFERENCE_CASES, build_chem_df, build_feed_df, build_specs_df
from .elemental import BIOMASS_ANALYSIS_CHEM_KEYS, BIOMASS_SAMPLES
from .parameters import DEFAULT_CHEMISTRY_SETUP, DEFAULT_REACTOR_SPECS
from .pfd_diagram import FEED_TO_PFD, PFD_WORKBOOK_IMAGE

WET_MAIN_SPECIES: Tuple[str, ...] = ("H2", "CO", "CO2", "CH4", "H2O")

SectionId = Literal["INCI", "RGPOX", "SLAG"]


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
        "Value": st.column_config.TextColumn("Value", width="medium"),
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
            "Mass Flow", format="%.2f", min_value=0.0, step=10.0, width="medium"
        ),
        "Temp_C": st.column_config.NumberColumn("T", format="%.1f", step=5.0, width="small"),
        "Pressure_bar": st.column_config.NumberColumn("P", format="%.1f", min_value=0.1, step=0.5, width="small"),
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
