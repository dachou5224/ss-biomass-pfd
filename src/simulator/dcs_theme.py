"""Streamlit 浅色工程仪表盘主题（CSS 与布局组件）。"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Literal, Optional

import streamlit as st

# 参考：生物质气化模拟器浅色 SaaS 仪表盘（#F8F9FA 底、#005A8C 主色、语义色 KPI）
SIM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
  --sim-bg: #f4f6f9;
  --sim-card: #ffffff;
  --sim-border: #e5e7eb;
  --sim-border-soft: #eef1f5;
  --sim-text: #1e293b;
  --sim-muted: #64748b;
  --sim-primary: #005a8c;
  --sim-primary-hover: #004a73;
  --sim-blue: #2563eb;
  --sim-green: #16a34a;
  --sim-orange: #ea580c;
  --sim-red: #dc2626;
  --sim-purple: #7c3aed;
  --sim-teal: #0d9488;
  --sim-input-bg: #fffbeb;
  --sim-input-border: #d97706;
  --sim-input-accent: #f59e0b;
  --sim-output-bg: #f1f5f9;
  --sim-output-border: #94a3b8;
}

.stApp {
  background: var(--sim-bg) !important;
  font-family: "Inter", "PingFang SC", "Microsoft YaHei", sans-serif !important;
  color: var(--sim-text);
}

header[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"] {
  display: none !important;
}

[data-testid="stMainBlockContainer"],
section[data-testid="stMain"] > div {
  padding-top: 0.75rem !important;
  max-width: 1600px;
}

[data-testid="stSidebar"],
[data-testid="stSidebar"] > div,
[data-testid="stSidebarContent"],
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
  background: var(--sim-card) !important;
  color: var(--sim-text) !important;
}
[data-testid="stSidebar"],
[data-testid="stSidebar"] > div:first-child {
  min-width: 21.5rem !important;
  max-width: 21.5rem !important;
}
[data-testid="stSidebar"] {
  border-right: 1px solid var(--sim-border) !important;
}
[data-testid="stSidebar"] [data-testid="stDataEditor"],
[data-testid="stSidebar"] [data-testid="stDataFrame"] {
  overflow-x: auto !important;
}
[data-testid="stSidebar"] [data-testid="stDataEditor"] > div {
  min-width: 100% !important;
}
[data-testid="stSidebar"] .stMarkdown h3 {
  color: var(--sim-primary) !important;
  font-weight: 700 !important;
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span {
  color: var(--sim-text) !important;
}
[data-testid="stSidebar"] [data-baseweb="input"],
[data-testid="stSidebar"] [data-baseweb="select"] > div,
[data-testid="stSidebar"] div[data-baseweb="base-input"],
[data-testid="stSidebar"] [data-testid="stNumberInput"] input,
[data-testid="stSidebar"] [data-testid="stTextInput"] input,
[data-testid="stSidebar"] [data-testid="stSelectbox"] > div > div {
  background-color: #f8fafc !important;
  color: var(--sim-text) !important;
  border-color: var(--sim-border) !important;
}
[data-testid="stSidebar"] [data-baseweb="radio"] label {
  color: var(--sim-text) !important;
}
[data-testid="stSidebar"] hr {
  border-color: var(--sim-border-soft) !important;
}
[data-testid="stSidebar"] .stDownloadButton > button,
[data-testid="stSidebar"] .stButton > button {
  background: #ffffff !important;
  color: var(--sim-text) !important;
  border: 1px solid var(--sim-border) !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
  background: var(--sim-primary) !important;
  color: #ffffff !important;
  border: none !important;
}

/* Expander / 折叠区 */
details[data-testid="stExpander"],
[data-testid="stExpander"] details {
  background: var(--sim-card) !important;
  border: 1px solid var(--sim-border) !important;
  border-radius: 10px !important;
  overflow: hidden;
}
details[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary {
  background: #f8fafc !important;
  color: var(--sim-text) !important;
}
details[data-testid="stExpander"] summary:hover,
[data-testid="stExpander"] summary:hover {
  background: #f1f5f9 !important;
}
details[data-testid="stExpander"] summary svg,
[data-testid="stExpander"] summary svg {
  fill: var(--sim-muted) !important;
}
details[data-testid="stExpander"] > div,
[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
  background: var(--sim-card) !important;
  color: var(--sim-text) !important;
  border-top: 1px solid var(--sim-border-soft) !important;
}

/* 主区表单控件 */
section[data-testid="stMain"] [data-baseweb="input"],
section[data-testid="stMain"] [data-baseweb="select"] > div,
section[data-testid="stMain"] div[data-baseweb="base-input"] {
  background-color: #ffffff !important;
  color: var(--sim-text) !important;
  border-color: var(--sim-border) !important;
}

/* 提示框 */
div[data-testid="stAlert"] {
  background-color: #ffffff !important;
  color: var(--sim-text) !important;
  border: 1px solid var(--sim-border) !important;
  border-radius: 10px !important;
}
div[data-testid="stAlert"] [data-testid="stMarkdownContainer"] p {
  color: var(--sim-text) !important;
}

/* 数据表 */
[data-testid="stDataFrame"],
[data-testid="stDataFrame"] div[data-testid="stDataFrameResizable"],
[data-testid="stDataFrame"] [data-testid="glideDataEditor"] {
  background: var(--sim-card) !important;
}
[data-testid="stDataFrame"] [role="gridcell"],
[data-testid="stDataFrame"] [role="columnheader"] {
  background: var(--sim-card) !important;
  color: var(--sim-text) !important;
}

/* 图表容器 */
[data-testid="stVegaLiteChart"],
[data-testid="stArrowVegaLiteChart"],
[data-testid="stArrowChart"] {
  background: var(--sim-card) !important;
  border: 1px solid var(--sim-border-soft);
  border-radius: 10px;
  padding: 8px;
}

/* 顶栏 */
.sim-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 14px 18px;
  margin-bottom: 16px;
  background: var(--sim-card);
  border: 1px solid var(--sim-border);
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
}
.sim-header-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--sim-text);
}
.sim-header-sub {
  font-size: 0.82rem;
  color: var(--sim-muted);
  margin-top: 2px;
}
.sim-badge-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.sim-badge {
  font-size: 0.75rem;
  font-weight: 600;
  padding: 5px 12px;
  border-radius: 999px;
  border: 1px solid var(--sim-border);
  background: #f8fafc;
  color: var(--sim-muted);
}
.sim-badge.run {
  color: var(--sim-blue);
  background: #eff6ff;
  border-color: #bfdbfe;
}
.sim-badge.run::before {
  content: "";
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--sim-blue);
  margin-right: 6px;
  vertical-align: middle;
  animation: sim-pulse 1.4s ease infinite;
}
.sim-badge.ok { color: #166534; background: #ecfdf5; border-color: #bbf7d0; }
.sim-badge.warn { color: #9a3412; background: #fff7ed; border-color: #fed7aa; }
.sim-badge.idle { color: var(--sim-muted); background: #f1f5f9; }
@keyframes sim-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

/* 白卡片面板 */
div[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--sim-card) !important;
  border: 1px solid var(--sim-border) !important;
  border-radius: 12px !important;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04) !important;
  margin-bottom: 12px !important;
}

.dcs-panel-hd-bar {
  padding: 10px 0 8px 0;
  margin-bottom: 6px;
  border-bottom: 1px solid var(--sim-border-soft);
}
.dcs-panel-tag {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--sim-primary);
  letter-spacing: 0.04em;
}
.dcs-panel-title {
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--sim-text);
  margin-left: 8px;
}

.dcs-section-label {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--sim-primary);
  margin: 14px 0 8px 0;
  padding-left: 10px;
  border-left: 3px solid var(--sim-primary);
}

.dcs-faceplate {
  border: 1px solid var(--sim-border);
  border-radius: 12px;
  padding: 10px;
  background: #fafbfc;
}
.dcs-faceplate-label {
  font-size: 0.72rem;
  color: var(--sim-muted);
  text-align: center;
  margin-bottom: 6px;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
  gap: 6px;
  background: var(--sim-card);
  border: 1px solid var(--sim-border);
  border-radius: 10px;
  padding: 6px;
}
.stTabs [data-baseweb="tab"] {
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--sim-muted);
  border-radius: 8px;
  padding: 8px 18px;
}
.stTabs [aria-selected="true"] {
  background: #eff6ff !important;
  color: var(--sim-primary) !important;
}

.stButton > button[kind="primary"] {
  background: var(--sim-primary) !important;
  border: none !important;
  color: #fff !important;
  font-weight: 600 !important;
  border-radius: 10px !important;
  box-shadow: 0 2px 6px rgba(0, 90, 140, 0.25) !important;
}
.stButton > button[kind="primary"]:hover {
  background: var(--sim-primary-hover) !important;
}
.stButton > button[kind="secondary"] {
  border-radius: 10px !important;
  border-color: var(--sim-border) !important;
}

div[data-testid="stMetric"] {
  background: var(--sim-card);
  border: 1px solid var(--sim-border);
  border-radius: 10px;
  padding: 10px 12px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
div[data-testid="stMetricLabel"] {
  color: var(--sim-muted) !important;
  font-size: 0.72rem !important;
}
div[data-testid="stMetricValue"] {
  color: var(--sim-text) !important;
  font-weight: 700 !important;
}

div[data-testid="stDataEditor"] {
  border: 1px solid var(--sim-border);
  border-radius: 10px;
}

/* 结果牌 */
.dcs-result-card {
  background: var(--sim-card);
  border: 1px solid var(--sim-border);
  border-radius: 12px;
  margin-bottom: 14px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
}
.dcs-result-hd {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--sim-border-soft);
  background: #f8fafc;
}
.dcs-result-title { font-size: 0.9rem; font-weight: 600; color: var(--sim-text); }
.dcs-result-status {
  font-size: 0.72rem;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 999px;
}
.dcs-result-status.idle { color: var(--sim-muted); background: #f1f5f9; }
.dcs-result-status.ready { color: #9a3412; background: #fff7ed; }
.dcs-result-status.ok { color: #166534; background: #ecfdf5; }
.dcs-result-status.warn { color: #9a3412; background: #fff7ed; }
.dcs-result-status.err { color: #991b1b; background: #fef2f2; }
.dcs-result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
}
.dcs-result-cell {
  padding: 12px 14px;
  border-right: 1px solid var(--sim-border-soft);
  border-bottom: 1px solid var(--sim-border-soft);
}
.dcs-result-label {
  font-size: 0.68rem;
  color: var(--sim-muted);
}
.dcs-result-value {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--sim-primary);
  margin-top: 4px;
}
.dcs-result-unit { font-size: 0.72rem; color: var(--sim-muted); margin-left: 2px; font-weight: 500; }
.dcs-result-placeholder { padding: 16px; color: var(--sim-muted); font-size: 0.85rem; }

/* 右侧 KPI 卡 */
.sim-side-panel {
  background: var(--sim-card);
  border: 1px solid var(--sim-border);
  border-radius: 12px;
  padding: 14px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
}
.sim-side-title {
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--sim-text);
  margin-bottom: 12px;
}
.sim-kpi-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.sim-kpi-tile {
  background: #f8fafc;
  border: 1px solid var(--sim-border-soft);
  border-radius: 10px;
  padding: 12px;
}
.sim-kpi-tile .lbl {
  font-size: 0.68rem;
  color: var(--sim-muted);
  line-height: 1.3;
}
.sim-kpi-tile .val {
  font-size: 1.15rem;
  font-weight: 700;
  margin-top: 6px;
}
.sim-kpi-tile .val.blue { color: var(--sim-blue); }
.sim-kpi-tile .val.green { color: var(--sim-green); }
.sim-kpi-tile .val.orange { color: var(--sim-orange); }
.sim-kpi-tile .val.red { color: var(--sim-red); }
.sim-kpi-tile .val.purple { color: var(--sim-purple); }
.sim-kpi-tile .val.teal { color: var(--sim-teal); }

/* 底部 KPI 条 */
.sim-kpi-strip {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 10px;
  margin-top: 14px;
}
@media (max-width: 1100px) {
  .sim-kpi-strip { grid-template-columns: repeat(3, 1fr); }
}
.sim-strip-item {
  background: var(--sim-card);
  border: 1px solid var(--sim-border);
  border-radius: 10px;
  padding: 10px 12px;
  text-align: center;
}
.sim-strip-item .lbl { font-size: 0.65rem; color: var(--sim-muted); }
.sim-strip-item .val { font-size: 0.95rem; font-weight: 700; margin-top: 4px; }

.stCaption, .stMarkdown p small { color: var(--sim-muted) !important; }

/* —— 用户输入区 / 只读结果区（对齐 Excel 琥珀可编辑 vs 灰只读）—— */
.sim-user-input-rail {
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  border: 2px solid var(--sim-input-border);
  border-radius: 12px;
  padding: 12px 14px;
  margin-bottom: 14px;
}
.sim-user-input-rail .rail-title {
  font-size: 1rem;
  font-weight: 700;
  color: #92400e;
}
.sim-user-input-rail .rail-sub {
  font-size: 0.72rem;
  color: #b45309;
  margin-top: 4px;
  line-height: 1.4;
}
.sim-legend {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 0.68rem;
  color: var(--sim-muted);
  margin-bottom: 12px;
  padding: 8px 10px;
  background: #ffffff;
  border: 1px dashed var(--sim-border);
  border-radius: 8px;
}
.sim-legend-row { display: flex; align-items: center; gap: 8px; }
.sim-legend-chip {
  width: 14px;
  height: 14px;
  border-radius: 3px;
  flex-shrink: 0;
}
.sim-legend-chip.edit {
  background: var(--sim-input-bg);
  border: 2px solid var(--sim-input-border);
}
.sim-legend-chip.read {
  background: var(--sim-output-bg);
  border: 1px solid var(--sim-output-border);
}
.sim-zone-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 10px 0 6px 0;
}
.sim-zone-head.input .sim-zone-badge {
  background: #fef3c7;
  color: #92400e;
  border: 1px solid #fcd34d;
}
.sim-zone-head.output .sim-zone-badge {
  background: #ecfdf5;
  color: #166534;
  border: 1px solid #bbf7d0;
}
.sim-zone-badge {
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  padding: 3px 8px;
  border-radius: 4px;
  text-transform: uppercase;
}
.sim-zone-head-title {
  font-size: 0.86rem;
  font-weight: 600;
  color: var(--sim-text);
}
.sim-zone-tag {
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--sim-primary);
  min-width: 1.2rem;
}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.sim-zone-marker.sim-zone-input) {
  background: var(--sim-input-bg) !important;
  border: 2px solid var(--sim-input-border) !important;
  border-radius: 10px !important;
  box-shadow: inset 0 0 0 1px #fde68a !important;
  margin-bottom: 8px !important;
}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.sim-zone-marker.sim-zone-input)
  [data-testid="stDataEditor"] {
  border: 1px solid var(--sim-input-border) !important;
  border-radius: 8px;
}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.sim-zone-marker.sim-zone-input)
  label[data-testid="stWidgetLabel"] p {
  font-weight: 600 !important;
  color: #92400e !important;
}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.sim-zone-marker.sim-zone-output) {
  background: var(--sim-output-bg) !important;
  border: 1px solid var(--sim-output-border) !important;
  border-radius: 10px !important;
  margin-bottom: 8px !important;
}
.sim-action-bar {
  background: #ffffff;
  border: 1px solid var(--sim-border);
  border-radius: 10px;
  padding: 10px 12px;
  margin: 12px 0;
}
.sim-tools-bar {
  opacity: 0.92;
}
.sim-feed-line-label {
  font-size: 0.82rem;
  margin: 10px 0 4px 0;
  color: var(--sim-text);
}
.sim-feed-line-label .sim-feed-pfd {
  font-size: 0.72rem;
  color: var(--sim-muted);
  font-weight: 500;
}
.sim-feed-status {
  font-size: 0.78rem;
  color: var(--sim-text);
  background: #ffffff;
  border: 1px dashed var(--sim-input-border);
  border-radius: 8px;
  padding: 10px 12px;
  margin: 8px 0 4px 0;
  line-height: 1.5;
}
.sim-feed-status b {
  color: #92400e;
}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.sim-zone-marker.sim-zone-input)
  [data-testid="stNumberInput"] {
  background: #fffdf5;
  border-radius: 8px;
}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.sim-zone-marker.sim-zone-input)
  [data-testid="stNumberInput"] label p {
  font-size: 0.72rem !important;
  font-weight: 600 !important;
  color: #92400e !important;
}
.sim-output-rail-title {
  font-size: 0.9rem;
  font-weight: 700;
  color: #475569;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--sim-border-soft);
}
.sim-side-panel.output {
  background: var(--sim-output-bg);
  border-color: var(--sim-output-border);
}
.sim-side-panel.output .sim-side-title::after {
  content: " · 只读";
  font-size: 0.68rem;
  font-weight: 500;
  color: var(--sim-muted);
}

#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
</style>
"""

# 兼容旧名
DCS_CSS = SIM_CSS


def inject_dcs_theme() -> None:
    st.markdown(SIM_CSS, unsafe_allow_html=True)


def render_user_input_rail_header() -> None:
    """侧栏顶：明确「用户输入区」标识（对标 Excel Model_Input 黄底）。"""
    st.markdown(
        """
        <div class="sim-user-input-rail">
          <div class="rail-title">用户输入区</div>
          <div class="rail-sub">每条流股下有三个数字框（流量·温度·压力）；改完点「重新计算」。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_input_legend() -> None:
    st.markdown(
        """
        <div class="sim-legend">
          <div class="sim-legend-row">
            <span class="sim-legend-chip edit"></span>
            <span>琥珀底 · 需要您填写或修改（流量、温度、压力、组分等）</span>
          </div>
          <div class="sim-legend-row">
            <span class="sim-legend-chip read"></span>
            <span>灰底 · 只读计算结果（组成、KPI、对标表）</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _zone_head(kind: Literal["input", "output"], title: str, *, tag: str = "") -> None:
    tag_html = f'<span class="sim-zone-tag">{tag}</span>' if tag else ""
    badge = "用户输入" if kind == "input" else "计算结果"
    st.markdown(
        f'<div class="sim-zone-head {kind}">{tag_html}'
        f'<span class="sim-zone-badge">{badge}</span>'
        f'<span class="sim-zone-head-title">{title}</span></div>',
        unsafe_allow_html=True,
    )


@contextmanager
def input_zone(
    title: str,
    *,
    subtitle: str = "",
    tag: str = "",
) -> Iterator[None]:
    """可编辑输入区块（琥珀边框容器）。"""
    _zone_head("input", title, tag=tag)
    if subtitle:
        st.caption(subtitle)
    with st.container(border=True):
        st.markdown('<div class="sim-zone-marker sim-zone-input"></div>', unsafe_allow_html=True)
        yield


@contextmanager
def output_zone(title: str, *, subtitle: str = "") -> Iterator[None]:
    """只读结果区块（灰底容器）。"""
    _zone_head("output", title)
    if subtitle:
        st.caption(subtitle)
    with st.container(border=True):
        st.markdown('<div class="sim-zone-marker sim-zone-output"></div>', unsafe_allow_html=True)
        yield


@contextmanager
def action_bar() -> Iterator[None]:
    """主操作按钮区（重新计算）。"""
    st.markdown('<div class="sim-action-bar">', unsafe_allow_html=True)
    yield
    st.markdown("</div>", unsafe_allow_html=True)


@contextmanager
def tools_bar() -> Iterator[None]:
    """导出/下载等次要操作。"""
    st.markdown('<div class="sim-tools-bar">', unsafe_allow_html=True)
    yield
    st.markdown("</div>", unsafe_allow_html=True)


def _panel_title_bar(tag: str, title: str, *, hint: str = "") -> None:
    hint_html = (
        f'<span style="color:var(--sim-muted);font-size:0.72rem;margin-left:8px">{hint}</span>'
        if hint
        else ""
    )
    st.markdown(
        f'<div class="dcs-panel-hd-bar">'
        f'<span class="dcs-panel-tag">{tag}</span>'
        f'<span class="dcs-panel-title">{title}</span>'
        f"{hint_html}</div>",
        unsafe_allow_html=True,
    )


@contextmanager
def dcs_panel(tag: str, title: str, *, hint: str = "") -> Iterator[None]:
    with st.container(border=True):
        _panel_title_bar(tag, title, hint=hint)
        yield


def panel_header(tag: str, title: str, *, hint: str = "") -> None:
    _panel_title_bar(tag, title, hint=hint)


def panel_footer() -> None:
    pass


def section_label(text: str) -> None:
    st.markdown(f'<div class="dcs-section-label">{text}</div>', unsafe_allow_html=True)


def render_result_card(
    *,
    status: Literal["idle", "ready", "ok", "warn", "error"],
    status_label: str,
    cells: list[tuple[str, str, str]] | None = None,
    placeholder: str = "修改参数后点击「重新计算」，结果将显示在此处。",
) -> None:
    status_class = status
    rows_html = ""
    if cells:
        parts = []
        for label, value, unit in cells:
            unit_html = f'<span class="dcs-result-unit">{unit}</span>' if unit else ""
            parts.append(
                f'<div class="dcs-result-cell">'
                f'<div class="dcs-result-label">{label}</div>'
                f'<div class="dcs-result-value">{value}{unit_html}</div>'
                f"</div>"
            )
        rows_html = f'<div class="dcs-result-grid">{"".join(parts)}</div>'
    else:
        rows_html = f'<div class="dcs-result-placeholder">{placeholder}</div>'

    st.markdown(
        f"""
        <div class="dcs-result-card">
          <div class="dcs-result-hd">
            <span class="dcs-result-title">关键指标</span>
            <span class="dcs-result-status {status_class}">{status_label}</span>
          </div>
          {rows_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_dcs_header(
    *,
    case_id: str,
    run_state: Literal["idle", "ready", "ok", "warn"] = "idle",
    subtitle: str = "固定温链条 · INCI 900°C · RGPOX 1400°C",
) -> None:
    """顶栏：中文标题 + 运行状态徽章。"""
    badge_map = {
        "idle": ("idle", "待输入"),
        "ready": ("run", "就绪"),
        "ok": ("ok", "运行完成"),
        "warn": ("warn", "请核对"),
    }
    badge_cls, badge_txt = badge_map[run_state]
    st.markdown(
        f"""
        <div class="sim-header">
          <div>
            <div class="sim-header-title">生物质气化过程模拟器</div>
            <div class="sim-header-sub">{subtitle}</div>
          </div>
          <div class="sim-badge-row">
            <span class="sim-badge {badge_cls}">{badge_txt}</span>
            <span class="sim-badge">工况 {case_id}</span>
            <span class="sim-badge">固定温求解</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_performance_panel(
    tiles: list[tuple[str, str, str, str]],
    *,
    title: str = "系统性能汇总",
) -> None:
    """右侧 2×2 语义色 KPI 卡。accent: blue|green|orange|red|purple|teal"""
    parts = []
    for label, value, unit, accent in tiles:
        unit_s = f" {unit}" if unit else ""
        parts.append(
            f'<div class="sim-kpi-tile">'
            f'<div class="lbl">{label}</div>'
            f'<div class="val {accent}">{value}{unit_s}</div>'
            f"</div>"
        )
    grid = "".join(parts)
    st.markdown(
        f'<div class="sim-side-panel output">'
        f'<div class="sim-side-title">{title}</div>'
        f'<div class="sim-kpi-grid">{grid}</div></div>',
        unsafe_allow_html=True,
    )


def render_kpi_strip(items: list[tuple[str, str, str, str]]) -> None:
    """底部横向 KPI 条。accent 用于 val 的 CSS 类。"""
    parts = []
    for label, value, unit, accent in items:
        unit_s = f" {unit}" if unit else ""
        parts.append(
            f'<div class="sim-strip-item">'
            f'<div class="lbl">{label}</div>'
            f'<div class="val {accent}">{value}{unit_s}</div>'
            f"</div>"
        )
    st.markdown(
        f'<div class="sim-kpi-strip">{"".join(parts)}</div>',
        unsafe_allow_html=True,
    )


def faceplate_image(image_path: Optional[str], caption: str = "工艺流程图") -> None:
    st.markdown(
        f'<div class="dcs-faceplate"><div class="dcs-faceplate-label">{caption}</div>',
        unsafe_allow_html=True,
    )
    if image_path:
        st.image(image_path, use_container_width=True)
    else:
        st.markdown(
            "<p style='color:#94a3b8;text-align:center;padding:2rem'>暂无流程图</p>",
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)
