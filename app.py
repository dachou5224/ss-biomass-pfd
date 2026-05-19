from __future__ import annotations

import os
import sys

import pandas as pd
import streamlit as st

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_PATH = os.path.join(CURRENT_DIR, "src")
DOC_PATH = os.path.join(CURRENT_DIR, "doc")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from simulator.backend import run_fixed_temperature_simulation
from simulator.data import REFERENCE_CASES, build_chem_df, build_feed_df, build_specs_df
from simulator.excel_export import build_simulator_workbook
from simulator.thermo import get_component_params_df, get_methods_df, get_thermo_baseline_df, summarize_method_signature


st.set_page_config(page_title="Biomass PFD Spreadsheet Simulator", layout="wide")


def _init_state() -> None:
    if "case_id" not in st.session_state:
        st.session_state.case_id = "Case-1"
    if "feed_df" not in st.session_state:
        st.session_state.feed_df = build_feed_df(st.session_state.case_id)
    if "specs_df" not in st.session_state:
        st.session_state.specs_df = build_specs_df()
    if "chem_df" not in st.session_state:
        st.session_state.chem_df = build_chem_df(st.session_state.case_id)
    if "thermo_methods_df" not in st.session_state:
        st.session_state.thermo_methods_df = get_methods_df()
    if "result" not in st.session_state:
        st.session_state.result = None


def _load_case(case_id: str) -> None:
    st.session_state.case_id = case_id
    st.session_state.feed_df = build_feed_df(case_id)
    st.session_state.specs_df = build_specs_df()
    st.session_state.chem_df = build_chem_df(case_id)
    st.session_state.result = None


def _dict_to_df(title: str, data: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame({"Component": list(data.keys()), title: list(data.values())})


_init_state()

st.title("生物质气化 Spreadsheet Simulator (MVP)")
st.caption("固定温度模式：INCI=900℃, SLAG=800℃, RGPOX=1400℃")

with st.sidebar:
    st.markdown("### Excel 工作簿")
    st.caption("Guide / PFD / Model_Input / Model_Output；内部常数见 export/vba。")
    try:
        xlsx_bytes = build_simulator_workbook(
            case_id=st.session_state.case_id,
            feed_df=st.session_state.feed_df,
            specs_df=st.session_state.specs_df,
            chem_df=st.session_state.chem_df,
            result=st.session_state.result,
            run_simulation=st.session_state.result is None,
        )
        st.download_button(
            label="下载 Excel (.xlsx)",
            data=xlsx_bytes,
            file_name=f"Biomass_PFD_{st.session_state.case_id}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    except ImportError as exc:
        st.error("缺少 openpyxl，请执行: pip install openpyxl")
        st.caption(str(exc))

tab_case, tab_feed, tab_specs, tab_chem, tab_flow, tab_thermo, tab_result = st.tabs(
    [
        "Case Manager",
        "Feed Streams",
        "Reactor Specs",
        "Chemistry Setup",
        "Flowsheet",
        "Thermodynamics",
        "Results & Validation",
    ]
)

with tab_case:
    c1, c2 = st.columns([2, 3])
    with c1:
        selected_case = st.selectbox("Reference Case", options=list(REFERENCE_CASES.keys()), index=list(REFERENCE_CASES.keys()).index(st.session_state.case_id))
        if st.button("Load Selected Case", use_container_width=True):
            _load_case(selected_case)
            st.success(f"Loaded {selected_case}")
    with c2:
        expected = REFERENCE_CASES[st.session_state.case_id]["expected"]
        st.markdown("#### Case Snapshot")
        st.dataframe(
            pd.DataFrame(
                [
                    {"Metric": "INCI top outlet kg/h", "Value": expected["inci_top_kg_h"]},
                    {"Metric": "INCI slag outlet kg/h", "Value": expected["inci_slag_kg_h"]},
                    {"Metric": "RGPOX gas outlet kg/h", "Value": expected["pox_gas_kg_h"]},
                    {"Metric": "RGPOX ash outlet kg/h", "Value": expected["pox_ash_kg_h"]},
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )

with tab_feed:
    st.markdown("#### Sheet: Feed Streams")
    st.session_state.feed_df = st.data_editor(st.session_state.feed_df, use_container_width=True, num_rows="fixed")

with tab_specs:
    st.markdown("#### Sheet: Reactor Specs")
    st.caption("INCI 反应温度固定 900℃；碳转化率 INCI_C_CONVERSION=0.90 为模型定量，不在此表编辑。")
    st.session_state.specs_df = st.data_editor(st.session_state.specs_df, use_container_width=True, num_rows="fixed")

with tab_chem:
    st.markdown("#### Sheet: Chemistry Setup")
    st.caption(
        "INCI 受限平衡：WGS 与甲烷化分别用 TA DeltaT + Eta 调节；"
        "对标目标为湿基主组分 + H2O（CO/H₂/CO₂/CH₄/H₂O）。"
        "详见 doc/restricted-equilibrium-inci.md。"
        "甲烷化正 ΔT 表示慢反应在更高参考温度评估平衡；WGS 负 ΔT 表示放热反应在略低参考温度评估。"
    )
    st.session_state.chem_df = st.data_editor(st.session_state.chem_df, use_container_width=True, num_rows="fixed")

with tab_flow:
    st.markdown("#### Sheet: Flowsheet")
    st.markdown(
        """
        `Mix1 -> DECOMP -> INCI(RGibbs) -> SEP2 -> [SLAGTMZ -> SEP3 recycle] + [TARCOMP -> RGPOX]`
        """
    )
    topology_svg_path = os.path.join(DOC_PATH, "core_topology.svg")
    stream_csv_path = os.path.join(DOC_PATH, "core_streams.csv")
    if os.path.exists(topology_svg_path):
        st.markdown("**Core Process Topology (INCI -> RGPOX):**")
        with open(topology_svg_path, "r", encoding="utf-8") as f:
            st.markdown(f.read(), unsafe_allow_html=True)
    if os.path.exists(stream_csv_path):
        st.markdown("**Core Stream Table:**")
        st.dataframe(pd.read_csv(stream_csv_path), hide_index=True, use_container_width=True)
    st.info("Run simulation in Results & Validation tab to populate module-by-module status.")
    if st.session_state.result is not None:
        trace_df = pd.DataFrame([x.__dict__ for x in st.session_state.result.unit_trace])
        st.dataframe(trace_df, hide_index=True, use_container_width=True)

with tab_thermo:
    st.markdown("#### Sheet: Thermodynamics")
    st.markdown("**Method Setup (explicit):**")
    st.session_state.thermo_methods_df = st.data_editor(st.session_state.thermo_methods_df, use_container_width=True, num_rows="fixed")
    st.markdown("**Thermo Baseline Reference (aligned):**")
    st.dataframe(get_thermo_baseline_df(), hide_index=True, use_container_width=True)
    st.markdown("**Component Parameter Calls:**")
    st.dataframe(get_component_params_df(), hide_index=True, use_container_width=True)
    st.markdown("**Implementation Signature:**")
    method_signature = summarize_method_signature(st.session_state.thermo_methods_df)
    st.json(method_signature)
    if st.session_state.result is not None:
        st.markdown("**Runtime Thermo Call Trace:**")
        st.dataframe(pd.DataFrame(st.session_state.result.thermo_trace), hide_index=True, use_container_width=True)

with tab_result:
    st.markdown("#### Sheet: Results & Validation")
    if st.button("Run Fixed-Temperature Simulation", type="primary", use_container_width=True):
        st.session_state.result = run_fixed_temperature_simulation(
            st.session_state.feed_df,
            st.session_state.specs_df,
            st.session_state.chem_df,
        )
    if st.session_state.result is None:
        st.warning("No result yet. Click the run button.")
    else:
        res = st.session_state.result
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("INCI 气相 kg/h", f"{res.inci_top_kg_h:.2f}")
        k2.metric("INCI tar kg/h", f"{res.inci_tar_kg_h:.2f}")
        k3.metric("INCI Slag kg/h", f"{res.inci_slag_kg_h:.2f}")
        k4.metric("RGPOX Gas kg/h", f"{res.pox_gas_kg_h:.2f}")

        c_inci, c_pox = st.columns(2)
        with c_inci:
            st.markdown("**INCI Composition (dry vol%)**")
            st.dataframe(_dict_to_df("NICE_SIM", res.inci_comp_dry_vol_pct), hide_index=True, use_container_width=True)
            st.markdown("**INCI Composition (wet vol%, incl. H2O)**")
            st.dataframe(_dict_to_df("NICE_SIM", res.inci_comp_wet_vol_pct), hide_index=True, use_container_width=True)
            st.markdown("**INCI Minor Species (dry vol%)**")
            st.dataframe(_dict_to_df("NICE_SIM", res.inci_minor_vol_pct), hide_index=True, use_container_width=True)
            st.markdown("**INCI Inerts (dry vol%, N2/Ar from feed)**")
            st.dataframe(_dict_to_df("NICE_SIM", res.inci_inert_dry_vol_pct), hide_index=True, use_container_width=True)
            st.caption("干/湿基主组分 vol% 分母含 H2S/COS/NH3/N2/Ar 等微量气体。")
        with c_pox:
            st.markdown("**RGPOX Composition (dry vol%)**")
            st.dataframe(_dict_to_df("NICE_SIM", res.pox_comp_dry_vol_pct), hide_index=True, use_container_width=True)
            st.markdown("**RGPOX Composition (wet vol%, incl. H2O)**")
            st.dataframe(_dict_to_df("NICE_SIM", res.pox_comp_wet_vol_pct), hide_index=True, use_container_width=True)
            st.markdown("**RGPOX Minor Species (dry vol%)**")
            st.dataframe(_dict_to_df("NICE_SIM", res.pox_minor_vol_pct), hide_index=True, use_container_width=True)

        if res.matched_case:
            expected = REFERENCE_CASES[res.matched_case]["expected"]
            inci_expected_df = _dict_to_df("DBI_REF", expected["inci_comp"]).merge(
                _dict_to_df("NICE_SIM", res.inci_comp_dry_vol_pct), on="Component", how="left"
            )
            pox_expected_df = _dict_to_df("DBI_REF", expected["pox_comp"]).merge(
                _dict_to_df("NICE_SIM", res.pox_comp_dry_vol_pct), on="Component", how="left"
            )
            inci_expected_wet = dict(expected.get("inci_comp_wet", expected["inci_comp"]))
            if "H2O" not in inci_expected_wet:
                inci_expected_wet["H2O"] = float("nan")
            pox_expected_wet = dict(expected.get("pox_comp_wet", expected["pox_comp"]))
            if "H2O" not in pox_expected_wet:
                pox_expected_wet["H2O"] = float("nan")
            inci_expected_wet_df = _dict_to_df("DBI_REF", inci_expected_wet).merge(
                _dict_to_df("NICE_SIM", res.inci_comp_wet_vol_pct), on="Component", how="left"
            )
            pox_expected_wet_df = _dict_to_df("DBI_REF", pox_expected_wet).merge(
                _dict_to_df("NICE_SIM", res.pox_comp_wet_vol_pct), on="Component", how="left"
            )
            st.success(f"Matched reference case: {res.matched_case}")
            c3, c4 = st.columns(2)
            with c3:
                st.markdown("**INCI vs DBI**")
                st.dataframe(inci_expected_df, hide_index=True, use_container_width=True)
                st.markdown("**INCI vs DBI (wet, incl. H2O)**")
                st.dataframe(inci_expected_wet_df, hide_index=True, use_container_width=True)
                if res.rmsd_inci_primary_pct is not None:
                    st.caption(f"RMSD (湿基主组分, 对标目标): {res.rmsd_inci_primary_pct:.2f}%")
                if res.rmsd_inci_pct is not None:
                    st.caption(f"RMSD (干基四主, 历史): {res.rmsd_inci_pct:.2f}%")
                if expected.get("inci_comp_dry_full"):
                    inci_dry_full_df = _dict_to_df("DBI_REF", expected["inci_comp_dry_full"]).merge(
                        _dict_to_df("NICE_SIM", res.inci_comp_dry_full_vol_pct), on="Component", how="left"
                    )
                    st.markdown("**INCI vs DBI (dry full, incl. trace)**")
                    st.dataframe(inci_dry_full_df, hide_index=True, use_container_width=True)
                    if res.rmsd_inci_dry_full_pct is not None:
                        st.caption(f"RMSD (dry full): {res.rmsd_inci_dry_full_pct:.2f}%")
                if expected.get("inci_comp_wet_full"):
                    inci_wet_full_df = _dict_to_df("DBI_REF", expected["inci_comp_wet_full"]).merge(
                        _dict_to_df("NICE_SIM", res.inci_comp_wet_full_vol_pct), on="Component", how="left"
                    )
                    st.markdown("**INCI vs DBI (wet full, incl. trace + H2O)**")
                    st.dataframe(inci_wet_full_df, hide_index=True, use_container_width=True)
                    if res.rmsd_inci_wet_full_pct is not None:
                        st.caption(f"RMSD (wet full, excl. HCN): {res.rmsd_inci_wet_full_pct:.2f}%")
                    st.caption("DBI 全组分来源：data/reference/inci_streams.csv；HCN 未建模，RMSD 已排除。")
            with c4:
                st.markdown("**RGPOX vs DBI**")
                st.dataframe(pox_expected_df, hide_index=True, use_container_width=True)
                st.markdown("**RGPOX vs DBI (wet, incl. H2O)**")
                st.dataframe(pox_expected_wet_df, hide_index=True, use_container_width=True)
                if res.rmsd_pox_pct is not None:
                    st.caption(f"RMSD: {res.rmsd_pox_pct:.2f}%")
                if res.rmsd_pox_wet_pct is not None:
                    st.caption(f"RMSD (wet): {res.rmsd_pox_wet_pct:.2f}%")
        else:
            st.info("Current feed does not exactly match Case-1/2/3 signature. Displaying model-predicted simulation output.")

        if res.inci_mass_audit:
            audit = res.inci_mass_audit
            with st.expander("INCI 守恒审计（质量 / 元素 / H2O）", expanded=res.matched_case == "Case-1"):
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("进料(元素+灰) kg/h", f"{audit.feed_element_mass_kg_h:.1f}")
                m2.metric("13PGI-1 气相 kg/h", f"{audit.gas_mass_kg_h:.1f}")
                m3.metric("13PGI-1 tar kg/h", f"{audit.tar_kg_h:.1f}")
                m4.metric("气+tar 合计 kg/h", f"{audit.pgi_total_kg_h:.1f}")
                m5, m6, m7, m8 = st.columns(4)
                m5.metric("SEP2 底流固相 kg/h", f"{audit.bottom_solids_kg_h:.1f}")
                m6.metric("质量闭合误差", f"{audit.mass_closure_rel_err_pct:.3f}%")
                m7.metric("13LBS-1 渣 kg/h", f"{audit.slag_to_u14_kg_h:.1f}")
                m8.metric("湿基 H2O vol%", f"{audit.h2o_wet_pct_model:.2f}%")
                if audit.dbi_net_inlet_kg_h is not None:
                    st.caption(
                        f"DBI 边界进料 {audit.dbi_net_inlet_kg_h:.0f} kg/h "
                        f"(13C-4+13HS1-1+13OG2-1+N2) | "
                        f"模型进料 stream {audit.feed_stream_mass_kg_h:.0f} kg/h"
                    )
                if audit.dbi_gas_mass_kg_h is not None:
                    st.caption(
                        f"DBI 出口: gas {audit.dbi_gas_mass_kg_h:.0f} | "
                        f"volatiles {audit.dbi_volatiles_kg_h or 0:.1f} | "
                        f"total {audit.dbi_total_flow_kg_h or 0:.0f} | "
                        f"slag {audit.dbi_slag_mass_kg_h or 0:.0f} kg/h"
                    )
                if res.matched_case:
                    from simulator.inlet_comparison import aggregate_inlet_comparison, build_inci_inlet_comparison

                    inlet_rows = build_inci_inlet_comparison(res.matched_case)
                    if inlet_rows:
                        st.markdown("**INCI 边界进料组分：DBI vs 模型 (kg/h)**")
                        st.dataframe(
                            pd.DataFrame(
                                [
                                    {
                                        "Stream": r.stream_id,
                                        "Component": r.component,
                                        "DBI": round(r.dbi_kg_h, 2),
                                        "Model": round(r.model_kg_h, 2),
                                        "Delta": round(r.delta_kg_h, 2),
                                    }
                                    for r in inlet_rows
                                ]
                            ),
                            hide_index=True,
                            use_container_width=True,
                        )
                        st.markdown("**汇总（跨 stream 组分加总）**")
                        st.dataframe(
                            pd.DataFrame(
                                [
                                    {
                                        "Component": r.component,
                                        "DBI": round(r.dbi_kg_h, 2),
                                        "Model": round(r.model_kg_h, 2),
                                        "Delta": round(r.delta_kg_h, 2),
                                    }
                                    for r in aggregate_inlet_comparison(inlet_rows)
                                ]
                            ),
                            hide_index=True,
                            use_container_width=True,
                        )
                        st.caption(
                            "DBI 13C-4 proximate 与模型 11# 对齐；"
                            "CO2 在 13C-4 气相；O2IN 为 13OG2-1 全流股质量。"
                        )
                st.markdown("**INCI 边界物流 (PFD stream ID)**")
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Stream": row.stream_id,
                                "Dir": row.direction,
                                "Description": row.description,
                                "Mass_kg_h": row.mass_kg_h,
                                "Note": row.note,
                            }
                            for row in audit.stream_ledger
                        ]
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
                st.caption(
                    "进料 stream 加和 "
                    f"{audit.feed_stream_mass_kg_h:.1f} kg/h 低于元素+灰 "
                    f"{audit.feed_element_mass_kg_h:.1f} kg/h（生物质灰分已在 Biomass 流股内，"
                    "元素衡算需单独加灰分质量）。质量闭合：气相 + tar + 底流固相(灰+char) ≈ 元素进料 + 灰。"
                    " DBI 边界参考见台账 DBI| 行（仅包络 stream，不含 p2 烧嘴内部分配）。"
                )
                st.markdown("**INCI 段元素守恒（气相 + char vs 进料）**")
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Element": row.element,
                                "Inlet_mol_h": row.inlet_mol_h,
                                "Gas_mol_h": row.outlet_gas_mol_h,
                                "Solid_C_mol_h": row.outlet_solid_mol_h,
                                "RelErr_pct": row.rel_error_pct,
                            }
                            for row in audit.element_balance
                        ]
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
                st.markdown("**H2O 物料衡算 (mol/h)**")
                st.dataframe(
                    pd.DataFrame(
                        [{"Step": row.step, "H2O_mol_h": row.h2o_mol_h, "Note": row.note} for row in audit.h2o_budget]
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
                st.caption("详见 doc/inci-mass-balance-audit.md。湿基 H2O 偏差主因：TA 消耗 H2O，非元素丢失。")

        st.markdown("**Element Balance Check (mol/h)**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Element": b.element,
                        "Inlet_mol_h": b.inlet_mol_h,
                        "Outlet_mol_h": b.outlet_mol_h,
                        "RelErr_pct": b.rel_error_pct,
                    }
                    for b in res.element_balance
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
