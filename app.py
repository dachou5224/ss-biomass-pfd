from __future__ import annotations

import os
import sys

import pandas as pd
import streamlit as st

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_PATH = os.path.join(CURRENT_DIR, "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from simulator.data import REFERENCE_CASES
from simulator.dcs_theme import (
    action_bar,
    faceplate_image,
    inject_dcs_theme,
    input_zone,
    output_zone,
    render_dcs_header,
    render_input_legend,
    render_kpi_strip,
    render_performance_panel,
    render_result_card,
    render_user_input_rail_header,
    render_workflow_overview,
    section_label,
    tools_bar,
)
from simulator.excel_export import build_simulator_workbook
from simulator.web_ui import (
    PFD_SECTION_LABELS,
    TUNING_SECTIONS,
    UI_MODE_OPTIONS,
    UiMode,
    apply_biomass_preset,
    apply_biomass_property_table,
    apply_case_template,
    apply_feed_stream_table,
    apply_o2in_composition_table,
    apply_tuning_property_table,
    biomass_property_table,
    biomass_sample_options,
    bottom_kpi_strip,
    build_chem_df_from_inputs,
    build_feed_df_from_inputs,
    build_specs_df_from_inputs,
    comparison_wet_df,
    feed_balance_preview,
    feed_stream_table,
    format_results_json,
    format_results_markdown,
    init_session_state,
    performance_summary_tiles,
    render_o2in_number_inputs,
    render_section_feed_number_inputs,
    pfd_feed_summary_df,
    pfd_image_path,
    result_card_cells,
    result_status,
    run_simulation,
    tuning_property_table,
    tuning_table_column_config,
    validate_inputs,
    wet_composition_df,
)

st.set_page_config(
    page_title="生物质气化过程模拟器",
    page_icon="⚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_dcs_theme()
init_session_state()
inputs = st.session_state.inputs
res = st.session_state.result
solve_errors: list[str] = list(st.session_state.get("solve_errors") or [])
case_ids = list(REFERENCE_CASES.keys())
preview = feed_balance_preview(inputs)
o2_ok = abs(preview["o2in_sum_mol_pct"] - 100.0) <= 0.5

card_status, card_label = result_status(inputs, res, solve_errors)
run_state = "idle"
if solve_errors:
    run_state = "warn"
elif res is not None:
    run_state = "ok" if res.matched_case else "warn"
elif inputs.get("pfd_feeds"):
    run_state = "ready"

# —— 侧栏：用户输入区（对标 Excel Model_Input 琥珀可编辑区）——
with st.sidebar:
    render_user_input_rail_header()
    render_input_legend()

    with input_zone("① 工况与系统边界", tag="1", subtitle="选择模板或切换 CASE 后点「载入模板」"):
        def _on_case_change() -> None:
            apply_case_template(st.session_state.sidebar_case)
            st.session_state.solve_errors = []

        inputs["case_id"] = st.selectbox(
            "工况 CASE",
            options=case_ids,
            index=case_ids.index(inputs["case_id"]) if inputs["case_id"] in case_ids else 0,
            key="sidebar_case",
            on_change=_on_case_change,
        )
        inputs["system_p_bar"] = st.number_input(
            "系统压力 [bar]",
            value=float(inputs["system_p_bar"]),
            min_value=1.0,
            max_value=50.0,
            step=0.5,
        )
        if st.button("载入模板默认值", use_container_width=True):
            apply_case_template(st.session_state.sidebar_case)
            st.session_state.solve_errors = []
            st.rerun()

    with input_zone(
        "② INCI 进料流股",
        tag="2",
        subtitle="每条流股三个数字框：流量 · 温度 · 压力",
    ):
        render_section_feed_number_inputs(inputs, "INCI")

    with input_zone("③ 氧化剂 O2IN", tag="3", subtitle="三个 mol% 数字框，合计应接近 100"):
        render_o2in_number_inputs(inputs)

    st.markdown(
        f'<div class="sim-feed-status">'
        f'<div>INCI 进料合计：<b>{preview["inci_feed_kg_h"]:.0f}</b> kg/h</div>'
        f'<div>O2IN 组分合计：<b>{preview["o2in_sum_mol_pct"]:.2f}</b>%'
        f'{" ✓" if o2_ok else " · 建议调至 100%"}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )

    with action_bar():
        if st.button("运行求解并刷新结果", type="primary", use_container_width=True):
            errs = validate_inputs(inputs)
            st.session_state.solve_errors = errs
            if errs:
                st.session_state.result = None
            else:
                with st.spinner("求解中…"):
                    st.session_state.result = run_simulation(inputs)
            st.rerun()

    with tools_bar():
        st.caption("导出与备份")
        st.download_button(
            "下载 Markdown",
            data=format_results_markdown(inputs, res),
            file_name=f"result_{inputs['case_id']}.md",
            mime="text/markdown",
            use_container_width=True,
        )
        st.download_button(
            "下载 JSON",
            data=format_results_json(inputs, res),
            file_name=f"result_{inputs['case_id']}.json",
            mime="application/json",
            use_container_width=True,
        )
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
                "导出 Excel 工作簿",
                data=xlsx_bytes,
                file_name=f"Biomass_PFD_{inputs['case_id']}.xlsx",
                use_container_width=True,
            )
        except ImportError as exc:
            st.caption(f"Excel: {exc}")

    st.caption("主区「扩展输入」可编辑 RGPOX / SLAG / 生物质 / 调参")

render_dcs_header(
    case_id=inputs["case_id"],
    run_state=run_state,
    subtitle="左侧输入 → 运行求解 → 首个 Tab 查看结果总览 / 右侧查看性能汇总",
)

if solve_errors:
    overview_notice = solve_errors[0]
    overview_tone = "error"
elif res is not None and res.matched_case:
    overview_notice = f"已完成 {res.matched_case} 求解，对标表与气体组成已刷新。"
    overview_tone = "ok"
elif res is not None:
    overview_notice = "自定义工况已求解；当前结果有效，但不参与 Case-1/2/3 DBI 对标。"
    overview_tone = "info"
elif o2_ok:
    overview_notice = "输入已基本就绪；点击「运行求解并刷新结果」后，首个 Tab 会直接显示结果总览。"
    overview_tone = "info"
else:
    overview_notice = "先把 O2IN 组分调到接近 100%，再运行求解，可避免来回试错。"
    overview_tone = "warn"

match_label = res.matched_case if res is not None and res.matched_case else ("自定义工况" if res is not None else inputs["case_id"])
render_workflow_overview(
    [
        (
            "输入状态",
            "待修正" if solve_errors else ("可计算" if o2_ok else "需核对 O2IN"),
            f"负流量 {int(preview['negative_feed_count'])} 条",
        ),
        ("总进料", f"{preview['total_feed_kg_h']:.0f} kg/h", f"INCI {preview['inci_feed_kg_h']:.0f} kg/h"),
        ("氧化剂合计", f"{preview['o2in_sum_mol_pct']:.2f} mol%", "建议维持在 100% 附近"),
        ("当前工况", str(match_label), "模板工况或已求解的自定义工况"),
    ],
    notice=overview_notice,
    tone=overview_tone,
)

if solve_errors:
    for msg in solve_errors:
        st.error(msg)
elif res is None:
    if abs(preview["o2in_sum_mol_pct"] - 100.0) > 0.05:
        st.warning(
            f"O2IN 组分合计 {preview['o2in_sum_mol_pct']:.2f}%（建议 100%）。"
        )

col_main, col_side = st.columns([3.2, 1], gap="medium")

with col_side:
    st.markdown('<div class="sim-output-rail-title">计算结果区</div>', unsafe_allow_html=True)
    render_performance_panel(performance_summary_tiles(inputs, res))
    if res is not None:
        st.caption("冷煤气效率为基于干基组成与流量的估算代理。")

with col_main:
    tab_result, tab_pfd, tab_more = st.tabs(
        ["结果总览", "工艺流程图", "扩展输入"]
    )

    with tab_result:
        with output_zone("关键指标", subtitle="只读 · 求解后更新"):
            render_result_card(
                status=card_status,
                status_label=card_label,
                cells=result_card_cells(inputs, res),
            )
        if res is not None:
            with output_zone("气体组成", subtitle="只读图表"):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**INCI 出口湿基 vol%**")
                    st.bar_chart(
                        wet_composition_df("INCI", res.inci_comp_wet_vol_pct).set_index(
                            "组分"
                        )
                    )
                with c2:
                    st.markdown("**RGPOX 出口湿基 vol%**")
                    st.bar_chart(
                        wet_composition_df("RGPOX", res.pox_comp_wet_vol_pct).set_index(
                            "组分"
                        )
                    )

        with st.expander("详细求解结果与对标", expanded=res is not None):
            if res is None:
                st.info("完成「重新计算」后显示湿基组成、DBI 对标与单元追踪。")
                with output_zone("进料一览", subtitle="只读预览"):
                    st.dataframe(
                        pfd_feed_summary_df(inputs),
                        hide_index=True,
                        use_container_width=True,
                    )
            else:
                if res.matched_case:
                    st.success(f"工况匹配 · {res.matched_case}")
                else:
                    st.info("自定义工况已求解 · 当前结果不参与 Case-1/2/3 DBI 对标。")

                out_l, out_r = st.columns(2)
                with out_l:
                    with output_zone("13PGI-1 · INCI 湿基 vol%"):
                        st.dataframe(
                            wet_composition_df("INCI", res.inci_comp_wet_vol_pct),
                            hide_index=True,
                            use_container_width=True,
                        )
                        if res.rmsd_inci_primary_pct is not None:
                            st.caption(
                                f"RMSD vs DBI: **{res.rmsd_inci_primary_pct:.2f}%**"
                            )
                with out_r:
                    with output_zone("15PGR-2 · RGPOX 急冷湿基 vol%"):
                        if res.quench_t_out_c is not None:
                            st.caption(
                                f"T_out {res.quench_t_out_c:.0f}°C · "
                                f"H2O 注入 {res.quench_h2o_added_kg_h or 0:.0f} kg/h"
                            )
                        st.dataframe(
                            wet_composition_df("RGPOX", res.pox_comp_wet_vol_pct),
                            hide_index=True,
                            use_container_width=True,
                        )
                        if res.rmsd_pox_primary_pct is not None:
                            st.caption(
                                f"RMSD vs DBI: **{res.rmsd_pox_primary_pct:.2f}%**"
                            )

                if res.matched_case:
                    expected = REFERENCE_CASES[res.matched_case]["expected"]
                    section_label("DBI 对标")
                    c1, c2 = st.columns(2)
                    inci_wet = dict(
                        expected.get("inci_comp_wet", expected["inci_comp"])
                    )
                    inci_wet.setdefault("H2O", float("nan"))
                    pox_wet = dict(expected.get("pox_comp_wet", expected["pox_comp"]))
                    pox_wet.setdefault("H2O", float("nan"))
                    with c1:
                        with output_zone("INCI 对标偏差"):
                            st.dataframe(
                                comparison_wet_df(inci_wet, res.inci_comp_wet_vol_pct),
                                hide_index=True,
                                use_container_width=True,
                            )
                    with c2:
                        with output_zone("RGPOX 对标偏差"):
                            st.dataframe(
                                comparison_wet_df(pox_wet, res.pox_comp_wet_vol_pct),
                                hide_index=True,
                                use_container_width=True,
                            )

                with output_zone("进料台账", subtitle="只读汇总"):
                    st.dataframe(
                        pfd_feed_summary_df(inputs),
                        hide_index=True,
                        use_container_width=True,
                    )
                with output_zone("单元追踪 / AUDIT"):
                    st.dataframe(
                        pd.DataFrame([x.__dict__ for x in res.unit_trace]),
                        hide_index=True,
                        use_container_width=True,
                    )

    with tab_pfd:
        with output_zone("工艺流程图", subtitle="只读 · 随进料与求解更新"):
            faceplate_image(pfd_image_path(), "工艺流程图")
        render_kpi_strip(bottom_kpi_strip(inputs, res))

    with tab_more:
        st.markdown(
            "扩展输入与 Excel **Model_Input** 其余黄底单元格对应；"
            "侧栏已覆盖 CASE、系统压力、INCI 进料与 O2IN。"
        )
        mode_labels = [label for _, label in UI_MODE_OPTIONS]
        mode_keys: list[UiMode] = [key for key, _ in UI_MODE_OPTIONS]
        mode_index = (
            mode_keys.index(st.session_state.ui_mode)
            if st.session_state.ui_mode in mode_keys
            else 0
        )
        with input_zone("输入类别", tag="+"):
            picked = st.radio(
                "选择要编辑的内容",
                options=mode_labels,
                index=mode_index,
                horizontal=True,
                label_visibility="collapsed",
            )
            st.session_state.ui_mode = mode_keys[mode_labels.index(picked)]
        ui_mode: UiMode = st.session_state.ui_mode

        if ui_mode == "feeds":
            with output_zone(
                "INCI 进料台账（只读）",
                subtitle="在左侧侧栏改流量/温压；此处显示 PFD 位号与相态",
            ):
                st.dataframe(
                    feed_stream_table(inputs, "INCI"),
                    hide_index=True,
                    use_container_width=True,
                )

            with input_zone("生物质工业/元素分析", tag="A", subtitle="Value 列可编辑"):
                bc1, bc2 = st.columns([1.2, 1])
                with bc1:
                    preset = st.selectbox(
                        "样品库",
                        options=biomass_sample_options(),
                        index=biomass_sample_options().index(
                            inputs.get("biomass", {}).get("preset", "11#")
                        )
                        if inputs.get("biomass", {}).get("preset")
                        in biomass_sample_options()
                        else 0,
                    )
                with bc2:
                    if st.button("载入样品", use_container_width=True):
                        apply_biomass_preset(inputs, preset)
                        st.rerun()
                bio_df = st.data_editor(
                    biomass_property_table(inputs),
                    column_config={
                        "Tag": st.column_config.TextColumn("Tag", disabled=True),
                        "Group": st.column_config.TextColumn("Group", disabled=True),
                        "Description": st.column_config.TextColumn("Description", disabled=True),
                        "Value": st.column_config.NumberColumn(
                            "Value ✎", format="%.4f", help="可编辑"
                        ),
                        "Unit": st.column_config.TextColumn("Unit", disabled=True),
                    },
                    hide_index=True,
                    use_container_width=True,
                    key="bio_props_editor",
                )
                apply_biomass_property_table(inputs, bio_df)
                inputs.setdefault("biomass", {})["preset"] = preset

            for section, panel_tag, step_tag in (
                ("RGPOX", "U15", "B"),
                ("SLAG", "SLAG", "C"),
            ):
                with input_zone(
                    PFD_SECTION_LABELS[section],
                    tag=step_tag,
                    subtitle="每条流股：流量 · 温度 · 压力 数字框",
                ):
                    render_section_feed_number_inputs(inputs, section)  # type: ignore[arg-type]

            with input_zone("RGPOX 氧化剂", tag="D"):
                o2pox = inputs.setdefault("o2pox", {})
                o2pox["purity_vol_pct"] = st.number_input(
                    "O2 纯度 [90–100 vol%] ✎",
                    value=float(o2pox.get("purity_vol_pct", 95.0)),
                    min_value=90.0,
                    max_value=100.0,
                    step=0.5,
                )

        else:
            with input_zone(
                "受限平衡与热解 / Tar",
                tag="T",
                subtitle="Value 列可编辑 · 对标 Excel Chemistry 黄底",
            ):
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

        with output_zone("当前进料一览", subtitle="只读 · 汇总侧栏与扩展输入"):
            st.dataframe(
                pfd_feed_summary_df(inputs), hide_index=True, use_container_width=True
            )
