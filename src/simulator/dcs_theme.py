"""Streamlit DCS / Aspen 风格主题（CSS 注入与面板组件）。"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Literal, Optional

import streamlit as st

DCS_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

:root {
  --dcs-bg: #0a0e17;
  --dcs-panel: #121a2b;
  --dcs-panel-2: #0f1624;
  --dcs-border: #2a3a52;
  --dcs-border-bright: #3d5a80;
  --dcs-cyan: #22d3ee;
  --dcs-green: #34d399;
  --dcs-amber: #fbbf24;
  --dcs-red: #f87171;
  --dcs-text: #e2e8f0;
  --dcs-muted: #94a3b8;
  --dcs-tag-bg: #1e293b;
}

.stApp {
  background: linear-gradient(165deg, #070b12 0%, #0a0e17 40%, #0d1520 100%);
  font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
}

/* 隐藏 Streamlit 顶栏/工具条，避免遮挡 DCS 页眉与侧栏「工程站」 */
header[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"] {
  display: none !important;
  height: 0 !important;
  min-height: 0 !important;
  overflow: hidden !important;
  visibility: hidden !important;
}

/* 侧栏：为残余固定层留出空间 */
[data-testid="stSidebar"] [data-testid="stSidebarContent"],
[data-testid="stSidebar"] > div:first-child {
  padding-top: 0.5rem !important;
}

/* 主内容区（兼容 1.38–1.40+ 多种 DOM 结构） */
[data-testid="stMainBlockContainer"],
[data-testid="stAppViewContainer"] .main .block-container,
section[data-testid="stMain"] > div {
  padding-top: 1rem !important;
  padding-bottom: 2rem;
  max-width: 1480px;
}

/* 顶栏 DCS 眉 */
.dcs-header {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  margin: 0 0 14px 0;
  scroll-margin-top: 1rem;
  background: linear-gradient(90deg, #0f1c2e 0%, #152238 50%, #0f1c2e 100%);
  border: 1px solid var(--dcs-border-bright);
  border-left: 4px solid var(--dcs-cyan);
  box-shadow: 0 4px 24px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.04);
  position: relative;
  z-index: 1;
}
.dcs-header-title {
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--dcs-cyan);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.dcs-header-sub {
  font-size: 0.78rem;
  color: var(--dcs-muted);
  margin-top: 2px;
}
.dcs-lamp-row {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.dcs-lamp {
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.72rem;
  padding: 4px 10px;
  border-radius: 2px;
  border: 1px solid var(--dcs-border);
  background: var(--dcs-tag-bg);
  color: var(--dcs-muted);
}
.dcs-lamp.ok { border-color: #059669; color: var(--dcs-green); background: #052e1a; }
.dcs-lamp.warn { border-color: #b45309; color: var(--dcs-amber); background: #292107; }
.dcs-lamp.idle { border-color: var(--dcs-border); color: var(--dcs-muted); }

/* 面板（Aspen 数据页 / DCS 弹窗） */
/* Streamlit 原生 bordered container ≈ DCS 面板 */
div[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--dcs-panel) !important;
  border: 1px solid var(--dcs-border) !important;
  border-top: 2px solid var(--dcs-border-bright) !important;
  border-radius: 2px !important;
  margin-bottom: 12px !important;
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.2);
}

.dcs-panel {
  background: var(--dcs-panel);
  border: 1px solid var(--dcs-border);
  border-top: 2px solid var(--dcs-border-bright);
  border-radius: 2px;
  padding: 0;
  margin-bottom: 14px;
  box-shadow: inset 0 0 0 1px rgba(0,0,0,0.2);
}

.dcs-panel-hd-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  padding: 8px 0 10px 0;
  margin-bottom: 4px;
  border-bottom: 1px solid var(--dcs-border);
}
.dcs-panel-hd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: linear-gradient(180deg, #1a2740 0%, #152238 100%);
  border-bottom: 1px solid var(--dcs-border);
}
.dcs-panel-tag {
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--dcs-amber);
  letter-spacing: 0.06em;
}
.dcs-panel-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--dcs-text);
  margin-left: 10px;
}
.dcs-panel-body {
  padding: 12px 14px 14px;
}
.dcs-section-label {
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.7rem;
  color: var(--dcs-cyan);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  margin: 16px 0 8px 0;
  padding-left: 8px;
  border-left: 3px solid var(--dcs-cyan);
}

/* 流程图面框 */
.dcs-faceplate {
  border: 2px solid var(--dcs-border-bright);
  border-radius: 2px;
  padding: 6px;
  background: #0c121c;
  box-shadow: inset 0 0 40px rgba(0,0,0,0.5);
}
.dcs-faceplate-label {
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.65rem;
  color: var(--dcs-muted);
  text-align: center;
  margin-bottom: 4px;
  letter-spacing: 0.15em;
}

/* Streamlit 组件覆写 */
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #0c1018 0%, #101828 100%);
  border-right: 1px solid var(--dcs-border);
}
[data-testid="stSidebar"] .stMarkdown h3 {
  color: var(--dcs-cyan) !important;
  font-size: 0.9rem !important;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.stTabs [data-baseweb="tab-list"] {
  gap: 4px;
  background: var(--dcs-panel-2);
  border: 1px solid var(--dcs-border);
  border-radius: 2px;
  padding: 4px;
}
.stTabs [data-baseweb="tab"] {
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--dcs-muted);
  background: transparent;
  border-radius: 2px;
  padding: 8px 16px;
}
.stTabs [aria-selected="true"] {
  background: #1e3a5f !important;
  color: var(--dcs-cyan) !important;
  border-bottom: 2px solid var(--dcs-cyan) !important;
}

div[data-testid="stDataEditor"] {
  border: 1px solid var(--dcs-border-bright);
  border-radius: 2px;
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.82rem;
}
div[data-testid="stDataEditor"] [role="grid"] {
  background: #0f1624;
}

.stButton > button[kind="primary"] {
  background: linear-gradient(180deg, #0e7490 0%, #155e75 100%) !important;
  border: 1px solid var(--dcs-cyan) !important;
  color: #ecfeff !important;
  font-family: "IBM Plex Mono", monospace !important;
  font-weight: 600 !important;
  letter-spacing: 0.08em !important;
  text-transform: uppercase !important;
  box-shadow: 0 0 12px rgba(34, 211, 238, 0.25) !important;
}
.stButton > button[kind="primary"]:hover {
  box-shadow: 0 0 20px rgba(34, 211, 238, 0.4) !important;
}

div[data-testid="stMetric"] {
  background: var(--dcs-panel);
  border: 1px solid var(--dcs-border);
  border-left: 3px solid var(--dcs-green);
  padding: 10px 14px;
  border-radius: 2px;
}
div[data-testid="stMetricLabel"] {
  font-family: "IBM Plex Mono", monospace;
  font-size: 0.68rem !important;
  color: var(--dcs-muted) !important;
  text-transform: uppercase;
}
div[data-testid="stMetricValue"] {
  font-family: "IBM Plex Mono", monospace;
  color: var(--dcs-green) !important;
}

.stCaption, .stMarkdown p small {
  color: var(--dcs-muted) !important;
}

#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
</style>
"""


def inject_dcs_theme() -> None:
    st.markdown(DCS_CSS, unsafe_allow_html=True)


def _panel_title_bar(tag: str, title: str, *, hint: str = "") -> None:
    hint_html = (
        f'<span style="color:#94a3b8;font-size:0.72rem;margin-left:8px">{hint}</span>' if hint else ""
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


def render_dcs_header(
    *,
    case_id: str,
    run_state: Literal["idle", "ready", "ok", "warn"] = "idle",
    subtitle: str = "Fixed-T Chain · INCI 900°C · RGPOX 1400°C",
) -> None:
    lamp_class = {"idle": "idle", "ready": "warn", "ok": "ok", "warn": "warn"}[run_state]
    lamp_text = {
        "idle": "MODEL IDLE",
        "ready": "INPUT READY",
        "ok": "SOLVE OK",
        "warn": "REVIEW",
    }[run_state]
    st.markdown(
        f"""
        <div class="dcs-header">
          <div>
            <div class="dcs-header-title">Biomass Gasification · Spread Simulator</div>
            <div class="dcs-header-sub">{subtitle}</div>
          </div>
          <div class="dcs-lamp-row">
            <span class="dcs-lamp {lamp_class}">{lamp_text}</span>
            <span class="dcs-lamp">CASE: {case_id}</span>
            <span class="dcs-lamp">MODE: FIXED-T</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def faceplate_image(image_path: Optional[str], caption: str = "PFD OVERVIEW") -> None:
    st.markdown(
        f'<div class="dcs-faceplate"><div class="dcs-faceplate-label">{caption}</div>',
        unsafe_allow_html=True,
    )
    if image_path:
        st.image(image_path, use_container_width=True)
    else:
        st.markdown(
            "<p style='color:#64748b;text-align:center;padding:2rem'>NO PFD IMAGE</p>",
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)
