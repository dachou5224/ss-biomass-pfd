from __future__ import annotations

import os
import sys

import pandas as pd
import streamlit as st

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_PATH = os.path.join(CURRENT_DIR, "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from simulator.backend import run_fixed_temperature_simulation
from simulator.data import REFERENCE_CASES
from simulator.dcs_theme import (
    dcs_panel,
    faceplate_image,
    inject_dcs_theme,
    render_dcs_header,
    section_label,
)
from simulator.excel_export import build_simulator_workbook
from simulator.web_ui import (
    PFD_SECTION_LABELS,
    TUNING_SECTIONS,
    apply_biomass_preset,
    apply_biomass_property_table,
    apply_case_template,
    apply_feed_stream_table,
    apply_o2in_composition_table,
    apply_tuning_property_table,
    biomass_property_table,
    biomass_sample_options,
    build_chem_df_from_inputs,
    build_feed_df_from_inputs,
    build_specs_df_from_inputs,
    comparison_wet_df,
    feed_stream_table,
    init_session_state,
    o2in_composition_table,
    pfd_feed_summary_df,
    pfd_image_path,
    stream_table_column_config,
    tuning_property_table,
    tuning_table_column_config,
    wet_composition_df,
)

st.set_page_config(
    page_title="生物质气化 · DCS",
    page_icon="⚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_dcs_theme()
init_session_state()
inputs = st.session_state.inputs
res = st.session_state.result

run_state = "idle"
if res is not None:
    run_state = "ok" if res.matched_case else "warn"
elif inputs.get("pfd_feeds"):
    run_state = "ready"

render_dcs_header(case_id=inputs["case_id"], run_state=run_state)

# —— 侧栏：工程操作站 ——
with st.sidebar:
    st.markdown("### 工程站")
    case_ids = list(REFERENCE_CASES.keys())

    def _on_case_change() -> None:
        apply_case_template(st.session_state.sidebar_case)

    st.selectbox(
        "CASE 模板",
        options=case_ids,
        key="sidebar_case",
        on_change=_on_case_change,
    )
    if st.button("LOAD DEFAULTS", use_container_width=True):
        apply_case_template(st.session_state.sidebar_case)
        st.rerun()

    st.divider()
    inputs["system_p_bar"] = st.number_input(
        "SYSTEM P (bar)",
        value=float(inputs["system_p_bar"]),
        min_value=1.0,
        max_value=50.0,
        step=0.5,
    )

    st.divider()
    if st.button("▶ RUN SOLVE", type="primary", use_container_width=True):
        with st.spinner("SOLVING…"):
            st.session_state.result = run_fixed_temperature_simulation(
                build_feed_df_from_inputs(inputs),
                build_specs_df_from_inputs(inputs),
                build_chem_df_from_inputs(inputs),
            )
        st.rerun()

    try:
        xlsx_bytes = build_simulator_workbook(
            case_id=inputs["case_id"],
            feed_df=build_feed_df_from_inputs(inputs),
            specs_df=build_specs_df_from_inputs(inputs),
            chem_df=build_chem_df_from_inputs(inputs),
            result=st.session_state.result,
            run_simulation=st.session_state.result is None,
        )
        st.download_button(
            "EXPORT XLSX",
            data=xlsx_bytes,
            file_name=f"Biomass_PFD_{inputs['case_id']}.xlsx",
            use_container_width=True,
        )
    except ImportError as exc:
        st.caption(f"Excel: {exc}")

tab_feed, tab_props, tab_result = st.tabs(
    ["FEEDS / 进料", "PROPERTIES / 物性与调参", "RESULTS / 结果"]
)

# ═══════════════════════════════════════════════════════════════
# FEEDS — Aspen Stream Manager 风格
# ═══════════════════════════════════════════════════════════════
with tab_feed:
    top_l, top_r = st.columns([1.05, 1])
    with top_l:
        faceplate_image(pfd_image_path(), "PFD FACEPLATE")
    with top_r:
        with dcs_panel("SOLIDS", "FEED CHARACTERIZATION — 生物质", hint="Proximate / Ultimate"):
            bc1, bc2 = st.columns([1.2, 1])
            with bc1:
                preset = st.selectbox(
                    "Library sample",
                    options=biomass_sample_options(),
                    index=biomass_sample_options().index(inputs.get("biomass", {}).get("preset", "11#"))
                    if inputs.get("biomass", {}).get("preset") in biomass_sample_options()
                    else 0,
                    label_visibility="collapsed",
                )
            with bc2:
                if st.button("LOAD LIBRARY → TABLE", use_container_width=True):
                    apply_biomass_preset(inputs, preset)
                    st.rerun()
            bio_df = st.data_editor(
                biomass_property_table(inputs),
                column_config={
                    "Tag": st.column_config.TextColumn("Tag", disabled=True, width="small"),
                    "Description": st.column_config.TextColumn("Description", disabled=True),
                    "Group": st.column_config.TextColumn("Group", disabled=True, width="small"),
                    "Value": st.column_config.NumberColumn("Value", format="%.4f", step=0.01),
                    "Unit": st.column_config.TextColumn("Unit", disabled=True, width="small"),
                },
                hide_index=True,
                use_container_width=True,
                key="bio_props_editor",
            )
            apply_biomass_property_table(inputs, bio_df)
            inputs.setdefault("biomass", {})["preset"] = preset

    for section, panel_tag in (
        ("INCI", "U13"),
        ("RGPOX", "U15"),
        ("SLAG", "SLAG"),
    ):
        section_label(PFD_SECTION_LABELS[section])
        with dcs_panel(
            panel_tag,
            f"STREAM TABLE — {section}",
            hint="Editable: Mass Flow · T · P  |  Aspen-style inlet specification",
        ):
            edited = st.data_editor(
                feed_stream_table(inputs, section),  # type: ignore[arg-type]
                column_config=stream_table_column_config(),
                hide_index=True,
                use_container_width=True,
                num_rows="fixed",
                key=f"feed_editor_{section}",
            )
            apply_feed_stream_table(inputs, edited)

    section_label("OXIDIZER COMPOSITION")
    oc1, oc2 = st.columns(2)
    with oc1:
        with dcs_panel("13OG2-1", "INCI OXIDIZER — mol% (O2IN split)"):
            o2_df = st.data_editor(
                o2in_composition_table(inputs),
                column_config={
                    "Component": st.column_config.TextColumn("Component", disabled=True),
                    "mol_pct": st.column_config.NumberColumn("mol%", format="%.3f", min_value=0.0, max_value=100.0),
                },
                hide_index=True,
                use_container_width=True,
                key="o2in_editor",
            )
            apply_o2in_composition_table(inputs, o2_df)
    with oc2:
        with dcs_panel("15OG1", "RGPOX O2 — purity (vol%)"):
            o2pox = inputs.setdefault("o2pox", {})
            o2pox["purity_vol_pct"] = st.number_input(
                "O2 purity vol%",
                value=float(o2pox.get("purity_vol_pct", 95.0)),
                min_value=90.0,
                max_value=100.0,
                step=0.5,
                label_visibility="collapsed",
            )
            st.caption("N₂/Ar 杂质由纯度推算（POSTO2 / O2POX）")

# ═══════════════════════════════════════════════════════════════
# PROPERTIES
# ═══════════════════════════════════════════════════════════════
with tab_props:
    with dcs_panel("REACTION", "RESTRICTED EQUILIBRIUM & PYROLYSIS", hint="TA / Tar / VM"):
        chemistry = inputs.setdefault("chemistry", {})
        for section_name in TUNING_SECTIONS:
            st.markdown(f"**{section_name}**")
            edited_tune = st.data_editor(
                tuning_property_table(chemistry, section_name),
                column_config=tuning_table_column_config(),
                hide_index=True,
                use_container_width=True,
                key=f"tune_{section_name}",
            )
            apply_tuning_property_table(chemistry, edited_tune)
            st.caption("—")

# ═══════════════════════════════════════════════════════════════
# RESULTS
# ═══════════════════════════════════════════════════════════════
with tab_result:
    res = st.session_state.result
    if res is None:
        st.info("在侧栏点击 **▶ RUN SOLVE** 或完成进料后运行求解。")
        st.dataframe(pfd_feed_summary_df(inputs), hide_index=True, use_container_width=True)
        st.stop()

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("13PGI-1 GAS", f"{res.inci_top_kg_h:.0f} kg/h")
    m2.metric("13LBS SLAG", f"{res.inci_slag_kg_h:.0f} kg/h")
    m3.metric("TAR", f"{res.inci_tar_kg_h:.1f} kg/h")
    m4.metric("15PGR GAS", f"{res.pox_gas_kg_h:.0f} kg/h")
    m5.metric("POX ASH", f"{res.pox_ash_kg_h:.1f} kg/h")

    if res.matched_case:
        st.success(f"CASE MATCH · {res.matched_case}")
    else:
        st.warning("CUSTOM FEED — no Case-1/2/3 signature match")

    out_l, out_r = st.columns(2)
    with out_l:
        with dcs_panel("13PGI-1", "INCI OUTLET — wet vol%"):
            st.dataframe(wet_composition_df("INCI", res.inci_comp_wet_vol_pct), hide_index=True, use_container_width=True)
            if res.rmsd_inci_primary_pct is not None:
                st.caption(f"RMSD vs DBI: **{res.rmsd_inci_primary_pct:.2f}%**")
    with out_r:
        with dcs_panel("15PGR-2", "RGPOX OUTLET — quenched wet vol%"):
            if res.quench_t_out_c is not None:
                st.caption(f"T_out {res.quench_t_out_c:.0f}°C · H2O inj {res.quench_h2o_added_kg_h or 0:.0f} kg/h")
            st.dataframe(wet_composition_df("RGPOX", res.pox_comp_wet_vol_pct), hide_index=True, use_container_width=True)
            if res.rmsd_pox_primary_pct is not None:
                st.caption(f"RMSD vs DBI: **{res.rmsd_pox_primary_pct:.2f}%**")

    if res.matched_case:
        expected = REFERENCE_CASES[res.matched_case]["expected"]
        with st.expander("DBI BENCHMARK TABLES"):
            c1, c2 = st.columns(2)
            inci_wet = dict(expected.get("inci_comp_wet", expected["inci_comp"]))
            inci_wet.setdefault("H2O", float("nan"))
            pox_wet = dict(expected.get("pox_comp_wet", expected["pox_comp"]))
            pox_wet.setdefault("H2O", float("nan"))
            with c1:
                st.dataframe(comparison_wet_df(inci_wet, res.inci_comp_wet_vol_pct), hide_index=True, use_container_width=True)
            with c2:
                st.dataframe(comparison_wet_df(pox_wet, res.pox_comp_wet_vol_pct), hide_index=True, use_container_width=True)

    with st.expander("STREAM LEDGER"):
        st.dataframe(pfd_feed_summary_df(inputs), hide_index=True, use_container_width=True)
    with st.expander("UNIT TRACE / AUDIT"):
        st.dataframe(pd.DataFrame([x.__dict__ for x in res.unit_trace]), hide_index=True, use_container_width=True)
