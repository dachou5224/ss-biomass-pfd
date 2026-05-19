"""PFD 拓扑图标注与可选 PNG 导出（供 Excel PFD 页嵌入）。"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .contracts import SimulationResult
from .parameters import PROJECT_ROOT

TOPOLOGY_SVG = PROJECT_ROOT / "doc" / "core_topology.svg"
ASSETS_DIR = PROJECT_ROOT / "export" / "assets"

# (x, y) 标注框左上角，与 doc/core_topology.svg 坐标系一致
STREAM_ANCHORS: Dict[str, Tuple[int, int]] = {
    "13C-4": (48, 108),
    "13HS1-1": (48, 208),
    "13OG2-1": (48, 288),
    "13PGI-1": (520, 128),
    "13LBS-1": (380, 400),
    "15OG1": (708, 8),
    "15PGR-1": (720, 248),
    "15PGR-2": (1000, 88),
}

# 进料表 Stream 名 → PFD 标签（多路合并为一路时求和）
FEED_TO_PFD: Dict[str, str] = {
    "Biomass": "13C-4",
    "CIN": "13C-4",
    "CO2IN": "13C-4",
    "H2OIN": "13HS1-1",
    "O2IN": "13OG2-1",
    "O2POX": "15OG1",
    "POSTO2": "INCI_POST",
    "POSTH2O": "INCI_POST",
    "POSTCO2": "INCI_POST",
}


@dataclass(frozen=True)
class StreamCallout:
    stream_id: str
    line1: str
    line2: str
    line3: str
    line4: str

    def as_rows(self) -> List[str]:
        return [self.stream_id, self.line1, self.line2, self.line3, self.line4]


def _fmt_flow(mass: float, temp: float, pressure: float) -> Tuple[str, str, str]:
    return (
        f"{mass:,.1f} kg/h",
        f"{temp:.0f} °C  |  {pressure:.0f} bar",
        "Model feed",
    )


def _aggregate_feed_callouts(feed_df: pd.DataFrame) -> Dict[str, StreamCallout]:
    buckets: Dict[str, List[dict]] = {}
    for _, row in feed_df.iterrows():
        name = str(row["Stream"])
        tag = FEED_TO_PFD.get(name)
        if not tag:
            continue
        buckets.setdefault(tag, []).append(row)

    out: Dict[str, StreamCallout] = {}
    for tag, rows in buckets.items():
        if tag == "INCI_POST":
            mass = sum(float(r["MassFlow_kg_h"]) for r in rows)
            if mass <= 0:
                continue
            names = "+".join(str(r["Stream"]) for r in rows if float(r["MassFlow_kg_h"]) > 0)
            t = float(rows[0]["Temp_C"])
            p = float(rows[0]["Pressure_bar"])
            out[tag] = StreamCallout(
                "INCI 返气",
                _fmt_flow(mass, t, p)[0],
                _fmt_flow(mass, t, p)[1],
                "Post-gas inj.",
                names[:40],
            )
            continue
        mass = sum(float(r["MassFlow_kg_h"]) for r in rows)
        t = sum(float(r["Temp_C"]) * float(r["MassFlow_kg_h"]) for r in rows) / mass if mass else 0.0
        p = float(rows[0]["Pressure_bar"])
        names = "+".join(str(r["Stream"]) for r in rows if float(r["MassFlow_kg_h"]) > 0)
        label = {
            "13C-4": "Biomass+CO2",
            "13HS1-1": "Steam",
            "13OG2-1": "Oxygen",
            "15OG1": "POX O2",
        }.get(tag, tag)
        f0, f1, _ = _fmt_flow(mass, t, p)
        out[tag] = StreamCallout(tag, f0, f1, label, names[:36])
    return out


def _result_callouts(result: SimulationResult) -> Dict[str, StreamCallout]:
    out: Dict[str, StreamCallout] = {}
    gas = result.inci_top_kg_h
    tar = result.inci_tar_kg_h
    total = result.inci_pgi_total_kg_h
    slag = result.inci_slag_kg_h
    dry = result.inci_comp_dry_vol_pct
    major = " ".join(f"{k} {dry.get(k, 0):.1f}%" for k in ("CO", "H2", "CO2", "CH4") if k in dry)
    out["13PGI-1"] = StreamCallout(
        "13PGI-1",
        f"气 {gas:,.0f} + tar {tar:,.0f} kg/h",
        f"合计 {total:,.0f} kg/h",
        "Dry major vol%",
        major[:36] or "—",
    )
    out["13LBS-1"] = StreamCallout(
        "13LBS-1",
        f"{slag:,.1f} kg/h",
        "Slag / solids",
        "→ Unit 14",
        "SEP2 底流",
    )
    pox = result.pox_gas_kg_h
    pdry = result.pox_comp_dry_vol_pct
    pmajor = " ".join(f"{k} {pdry.get(k, 0):.1f}%" for k in ("CO", "H2", "CO2", "CH4") if k in pdry)
    out["15PGR-2"] = StreamCallout(
        "15PGR-2",
        f"{pox:,.0f} kg/h",
        "RGPOX 出口气",
        "Dry major vol%",
        pmajor[:36] or "—",
    )
    return out


def build_stream_callouts(
    feed_df: pd.DataFrame,
    result: Optional[SimulationResult] = None,
) -> List[StreamCallout]:
    merged: Dict[str, StreamCallout] = _aggregate_feed_callouts(feed_df)
    if result is not None:
        merged.update(_result_callouts(result))
    order = [
        "13C-4",
        "13HS1-1",
        "13OG2-1",
        "INCI_POST",
        "13PGI-1",
        "13LBS-1",
        "15OG1",
        "15PGR-2",
    ]
    seen = set()
    items: List[StreamCallout] = []
    for key in order:
        if key in merged and key not in seen:
            items.append(merged[key])
            seen.add(key)
    for key, callout in merged.items():
        if key not in seen:
            items.append(callout)
            seen.add(key)
    return items


def callouts_to_excel_grid(callouts: List[StreamCallout]) -> pd.DataFrame:
    """PFD 页旁侧物流简表（每流股 4 行数据 + 空行分隔）。"""
    rows: List[dict] = []
    for c in callouts:
        rows.append({"流股": c.stream_id, "行": 1, "内容": c.line1})
        rows.append({"流股": "", "行": 2, "内容": c.line2})
        rows.append({"流股": "", "行": 3, "内容": c.line3})
        rows.append({"流股": "", "行": 4, "内容": c.line4})
        rows.append({"流股": "", "行": "", "内容": ""})
    return pd.DataFrame(rows)


def _inject_svg_callouts(svg_text: str, callouts: List[StreamCallout]) -> str:
    by_id = {c.stream_id: c for c in callouts}
    also = {c.stream_id.split()[0]: c for c in callouts}
    fragments: List[str] = []
    for stream_id, (x, y) in STREAM_ANCHORS.items():
        c = by_id.get(stream_id) or also.get(stream_id)
        if c is None:
            continue
        lines = c.as_rows()
        fragments.append(
            f'  <g class="callout" data-stream="{stream_id}">\n'
            f'    <rect x="{x}" y="{y}" width="168" height="72" rx="4" '
            f'fill="#fffbeb" stroke="#b45309" stroke-width="1.2"/>\n'
        )
        for i, text in enumerate(lines):
            safe = (
                text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            weight = "bold" if i == 0 else "normal"
            size = 11 if i == 0 else 10
            fragments.append(
                f'    <text x="{x + 6}" y="{y + 16 + i * 14}" class="small" '
                f'font-weight="{weight}" font-size="{size}px">{safe}</text>\n'
            )
        fragments.append("  </g>\n")

    if "</svg>" not in svg_text:
        return svg_text
    return svg_text.replace("</svg>", "".join(fragments) + "</svg>", 1)


def convert_svg_to_png(svg_path: Path, png_path: Path) -> bool:
    png_path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("rsvg-convert"):
        subprocess.run(
            ["rsvg-convert", "-o", str(png_path), str(svg_path)],
            check=False,
            capture_output=True,
        )
        return png_path.is_file()
    if sys.platform == "darwin" and shutil.which("qlmanage"):
        subprocess.run(
            ["qlmanage", "-t", "-s", "1200", "-o", str(png_path.parent), str(svg_path)],
            check=False,
            capture_output=True,
        )
        thumb = png_path.parent / f"{svg_path.name}.png"
        if thumb.is_file():
            thumb.replace(png_path)
            return True
    return False


def export_annotated_pfd(
    feed_df: pd.DataFrame,
    result: Optional[SimulationResult] = None,
    *,
    case_id: str = "Case-1",
) -> Tuple[Optional[Path], Optional[Path]]:
    """写出带物流标注的 SVG，并尝试生成 PNG。返回 (svg_path, png_path)。"""
    if not TOPOLOGY_SVG.is_file():
        return None, None
    callouts = build_stream_callouts(feed_df, result)
    svg_text = TOPOLOGY_SVG.read_text(encoding="utf-8")
    annotated = _inject_svg_callouts(svg_text, callouts)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    safe_case = re.sub(r"[^\w\-]+", "_", case_id)
    svg_out = ASSETS_DIR / f"pfd_{safe_case}.svg"
    png_out = ASSETS_DIR / f"pfd_{safe_case}.png"
    svg_out.write_text(annotated, encoding="utf-8")
    if convert_svg_to_png(svg_out, png_out):
        return svg_out, png_out
    return svg_out, None
