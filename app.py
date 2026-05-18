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
from simulator.data import REFERENCE_CASES, build_chem_df, build_feed_df, build_specs_df
from simulator.thermo import get_component_params_df, get_methods_df, summarize_method_signature


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
    st.session_state.specs_df = st.data_editor(st.session_state.specs_df, use_container_width=True, num_rows="fixed")

with tab_chem:
    st.markdown("#### Sheet: Chemistry Setup")
    st.session_state.chem_df = st.data_editor(st.session_state.chem_df, use_container_width=True, num_rows="fixed")

with tab_flow:
    st.markdown("#### Sheet: Flowsheet")
    st.markdown(
        """
        `Mix1 -> DECOMP -> INCI(RGibbs) -> SEP2 -> [SLAGTMZ -> SEP3 recycle] + [TARCOMP -> RGPOX]`
        """
    )
    st.info("Run simulation in Results & Validation tab to populate module-by-module status.")
    if st.session_state.result is not None:
        trace_df = pd.DataFrame([x.__dict__ for x in st.session_state.result.unit_trace])
        st.dataframe(trace_df, hide_index=True, use_container_width=True)

with tab_thermo:
    st.markdown("#### Sheet: Thermodynamics")
    st.markdown("**Method Setup (explicit):**")
    st.session_state.thermo_methods_df = st.data_editor(st.session_state.thermo_methods_df, use_container_width=True, num_rows="fixed")
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
        k1.metric("INCI Top kg/h", f"{res.inci_top_kg_h:.2f}")
        k2.metric("INCI Slag kg/h", f"{res.inci_slag_kg_h:.2f}")
        k3.metric("RGPOX Gas kg/h", f"{res.pox_gas_kg_h:.2f}")
        k4.metric("RGPOX Ash kg/h", f"{res.pox_ash_kg_h:.2f}")

        c_inci, c_pox = st.columns(2)
        with c_inci:
            st.markdown("**INCI Composition (dry vol%)**")
            st.dataframe(_dict_to_df("NICE_SIM", res.inci_comp_dry_vol_pct), hide_index=True, use_container_width=True)
            st.markdown("**INCI Minor Species (dry vol%)**")
            st.dataframe(_dict_to_df("NICE_SIM", res.inci_minor_vol_pct), hide_index=True, use_container_width=True)
        with c_pox:
            st.markdown("**RGPOX Composition (dry vol%)**")
            st.dataframe(_dict_to_df("NICE_SIM", res.pox_comp_dry_vol_pct), hide_index=True, use_container_width=True)
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
            st.success(f"Matched reference case: {res.matched_case}")
            c3, c4 = st.columns(2)
            with c3:
                st.markdown("**INCI vs DBI**")
                st.dataframe(inci_expected_df, hide_index=True, use_container_width=True)
                if res.rmsd_inci_pct is not None:
                    st.caption(f"RMSD: {res.rmsd_inci_pct:.2f}%")
            with c4:
                st.markdown("**RGPOX vs DBI**")
                st.dataframe(pox_expected_df, hide_index=True, use_container_width=True)
                if res.rmsd_pox_pct is not None:
                    st.caption(f"RMSD: {res.rmsd_pox_pct:.2f}%")
        else:
            st.info("Current feed does not exactly match Case-1/2/3 signature. Displaying model-predicted simulation output.")

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
