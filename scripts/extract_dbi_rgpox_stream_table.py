#!/usr/bin/env python3
"""从 DBI Unit 15 RGPOX 附录 PDF 提取 stream table 为长表 CSV，并生成 rgpox_streams.csv。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd
import pdfplumber

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF = (
    PROJECT_ROOT / "doc" / "TR5_APPENDIX 04_1_PFD & Stream Table_Unit 15_RGPOx Gasifier_0.05vol.%HCl_DBI.pdf"
)
DEFAULT_TABLE_OUT = PROJECT_ROOT / "data" / "reference" / "dbi_rgpox_stream_table_case1.csv"
DEFAULT_STREAMS_OUT = PROJECT_ROOT / "data" / "reference" / "rgpox_streams.csv"

CASE_ID = "Case-1"
PDF_BASENAME = "TR5_APPENDIX 04_1_PFD & Stream Table_Unit 15_RGPOx Gasifier_0.05vol.%HCl_DBI.pdf"

# PDF 表头重复 15PGR-1/15PGR-2，按列序映射为唯一 stream_id
RGPOX_COLUMN_STREAM_IDS = (
    "15PGI-1",
    "15OG1",
    "15PGR-1",
    "15PGR-1-dry",
    "15PGR-2",
    "15PGR-2-dry",
)

STREAM_DESCRIPTIONS = {
    "15PGI-1": "Raw syngas from INCI (S/L/G boundary)",
    "15OG1": "Oxygen to RGPOX",
    "15PGR-1": "RGPOX outlet ante quench wet gas @1400C (15PGR-1****)",
    "15PGR-1-dry": "RGPOX outlet ante quench dry gas @1400C",
    "15PGR-2": "RGPOX outlet after quench wet gas",
    "15PGR-2-dry": "RGPOX outlet after quench dry gas",
}

SECTION_BY_MARKER = {
    "FLUID PHASE (gas)": "fluid_phase",
    "FLUID PHASE (organic volatile": "fluid_phase_volatiles",
    "SOLID PHASE": "solid_phase",
}

GAS_SPECIES = {
    "CO",
    "CO2",
    "H2",
    "CH4",
    "H2O",
    "H2S",
    "COS",
    "N2",
    "NH3",
    "HCN",
    "AR",
    "HCL",
    "O2",
}


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\n", " ")).strip()


def _design_case_label(table: list[list]) -> str:
    for row in table[:4]:
        if not row:
            continue
        for cell in row:
            text = _cell_text(cell)
            if text.startswith("PROCESS DESIGN CASE"):
                return text
    return ""


def _stream_columns(table: list[list]) -> list[tuple[int, str]]:
    for row in table:
        if row and _cell_text(row[1]) == "STREAM / UNIT No.":
            cols: list[tuple[int, str]] = []
            idx = 0
            for j, cell in enumerate(row):
                raw = _cell_text(cell)
                if not raw.startswith("15"):
                    continue
                sid = RGPOX_COLUMN_STREAM_IDS[idx] if idx < len(RGPOX_COLUMN_STREAM_IDS) else raw
                cols.append((j, sid))
                idx += 1
            return cols
    return []


def _section_from_label(label: str) -> str | None:
    upper = label.upper()
    for marker, name in SECTION_BY_MARKER.items():
        if upper.startswith(marker.upper()):
            return name
    if upper.startswith("FLUID PHASE"):
        return "fluid_phase"
    return None


def _property_name(label: str, unit: str, section: str) -> str:
    key = label.lower().replace(" ", "_")
    if label.upper() in GAS_SPECIES:
        return label.upper() if label.upper() != "AR" else "Ar"
    if label.upper() == "HCL":
        return "HCl"
    if key == "flow" and unit:
        u = unit.replace("³", "3").replace("∙", ".")
        u = re.sub(r"[^a-zA-Z0-9_]+", "_", u).strip("_").lower()
        return f"flow_{u}" if u else "flow"
    return key


def _parse_stream_table_page(
    table: list[list],
    *,
    page: int,
    case_id: str,
    design_case: str,
) -> list[dict[str, str]]:
    streams = _stream_columns(table)
    if not streams:
        return []

    section = "overall"
    rows: list[dict[str, str]] = []

    for row in table:
        if not row:
            continue
        label = _cell_text(row[1]) if len(row) > 1 else ""
        unit = _cell_text(row[2]) if len(row) > 2 else ""

        if label == "STREAM / UNIT No.":
            continue
        sec = _section_from_label(label)
        if sec:
            section = sec
            continue
        if not label:
            continue
        if label.startswith("PROCESS DESIGN CASE"):
            continue

        prop = _property_name(label, unit, section)
        if label in ("medium", "phase") or label.startswith("remark"):
            sec = "stream_info"
            prop = label.replace(" ", "_")
        else:
            sec = section

        for j, sid in streams:
            raw = _cell_text(row[j]) if j < len(row) else ""
            rows.append(
                {
                    "case": case_id,
                    "design_case": design_case,
                    "source_pdf": PDF_BASENAME,
                    "source_page": str(page),
                    "stream_id": sid,
                    "section": sec,
                    "property": prop,
                    "unit": unit,
                    "value": raw,
                }
            )

    return rows


def extract_stream_table(
    pdf_path: Path | str = DEFAULT_PDF,
    *,
    pages: tuple[int, ...] = (2,),
) -> pd.DataFrame:
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"DBI Unit 15 PDF 不存在: {path}")

    all_rows: list[dict[str, str]] = []
    with pdfplumber.open(path) as doc:
        for page_no in pages:
            if page_no < 1 or page_no > len(doc.pages):
                raise ValueError(f"页码越界: {page_no} (共 {len(doc.pages)} 页)")
            page = doc.pages[page_no - 1]
            tables = page.extract_tables()
            if not tables:
                raise ValueError(f"第 {page_no} 页未检测到表格")
            design_case = _design_case_label(tables[0])
            for table in tables:
                all_rows.extend(
                    _parse_stream_table_page(
                        table,
                        page=page_no,
                        case_id=CASE_ID,
                        design_case=design_case,
                    )
                )

    df = pd.DataFrame(all_rows)
    if df.empty:
        raise ValueError("未解析到任何 Unit 15 stream table 行")
    return df


def _table_value(df: pd.DataFrame, stream_id: str, section: str, prop: str) -> str | None:
    mask = (df["stream_id"] == stream_id) & (df["section"] == section) & (df["property"] == prop)
    subset = df.loc[mask, "value"]
    if subset.empty:
        return None
    text = str(subset.iloc[0]).strip()
    return text or None


def _parse_mol_pct(text: str) -> float:
    cleaned = text.strip().replace("%", "")
    if cleaned.upper().endswith("E-04") or "E-" in cleaned.upper():
        return float(cleaned)
    return float(cleaned)


def build_rgpox_streams_csv(table_df: pd.DataFrame, *, case_id: str = CASE_ID) -> pd.DataFrame:
    """由长表生成 rgpox_streams.csv（组分 mol/mol % 长表）。"""
    stream_specs = (
        ("15PGR-1", "wet_mol_pct", "fluid_phase"),
        ("15PGR-1-dry", "dry_mol_pct", "fluid_phase"),
        ("15PGR-2", "wet_mol_pct", "fluid_phase"),
        ("15PGR-2-dry", "dry_mol_pct", "fluid_phase"),
    )
    species_rows = table_df.loc[
        (table_df["section"] == "fluid_phase") & table_df["property"].isin(sorted(GAS_SPECIES | {"Ar", "HCl"}))
    ]
    out_rows: list[dict[str, object]] = []
    for stream_id, basis, section in stream_specs:
        flow_raw = _table_value(table_df, stream_id, section, "flow_kg_h")
        temp_raw = _table_value(table_df, stream_id, "overall", "temperature")
        pres_raw = _table_value(table_df, stream_id, "overall", "pressure")
        if flow_raw is None:
            continue
        meta = {
            "case": case_id,
            "stream_id": stream_id.replace("-dry", ""),
            "basis": basis,
            "description": STREAM_DESCRIPTIONS[stream_id],
            "temperature_c": float(temp_raw) if temp_raw else None,
            "pressure_mpa_a": float(pres_raw.replace("MPa(a)", "").strip()) if pres_raw else None,
            "gas_flow_kg_h": float(flow_raw),
            "total_flow_kg_h": float(flow_raw),
            "source": PDF_BASENAME,
        }
        comp = species_rows.loc[species_rows["stream_id"] == stream_id]
        for _, row in comp.iterrows():
            raw = str(row["value"]).strip()
            if not raw:
                continue
            prop = str(row["property"])
            if prop == "AR":
                prop = "Ar"
            elif prop == "HCL":
                prop = "HCl"
            out_rows.append(
                {
                    **meta,
                    "component": prop,
                    "mol_pct": _parse_mol_pct(raw),
                }
            )
    if not out_rows:
        raise ValueError("未能从 Unit 15 长表生成 rgpox_streams 组分行")
    return pd.DataFrame(out_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="提取 DBI Unit 15 RGPOX stream table")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF, help="Unit 15 PDF 路径")
    parser.add_argument("--table-out", type=Path, default=DEFAULT_TABLE_OUT, help="长表 CSV")
    parser.add_argument("--streams-out", type=Path, default=DEFAULT_STREAMS_OUT, help="rgpox_streams.csv")
    parser.add_argument("--table-only", action="store_true", help="仅生成长表，不写 rgpox_streams.csv")
    args = parser.parse_args()

    table_df = extract_stream_table(args.pdf)
    args.table_out.parent.mkdir(parents=True, exist_ok=True)
    table_df.to_csv(args.table_out, index=False, encoding="utf-8")
    streams = sorted(table_df["stream_id"].unique())
    print(f"已写入 {args.table_out}")
    print(f"  行数: {len(table_df)}  流股: {len(streams)}  -> {', '.join(streams)}")

    if args.table_only:
        return

    streams_df = build_rgpox_streams_csv(table_df)
    args.streams_out.parent.mkdir(parents=True, exist_ok=True)
    streams_df.to_csv(args.streams_out, index=False, encoding="utf-8")
    print(f"已写入 {args.streams_out}")
    print(f"  组分行: {len(streams_df)}  stream/basis: {streams_df[['stream_id','basis']].drop_duplicates().to_dict('records')}")
    print("  注意: PDF 提取数据仅保存在本地，已配置 .gitignore，请勿 git add / push。")


if __name__ == "__main__":
    main()
