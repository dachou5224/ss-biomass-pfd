#!/usr/bin/env python3
"""从 DBI INCI Gasifier 附录 PDF 提取 stream table 为长表 CSV。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd
import pdfplumber

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF = PROJECT_ROOT / "doc" / "TR5_APPENDIX 02_PFD & Stream Table_Unit 13_INCI Gasifier_DBI.pdf"
DEFAULT_OUT = PROJECT_ROOT / "data" / "reference" / "dbi_inci_stream_table_case1.csv"

CASE_ID = "Case-1"
PDF_BASENAME = "TR5_APPENDIX 02_PFD & Stream Table_Unit 13_INCI Gasifier_DBI.pdf"

SECTION_BY_MARKER = {
    "FLUID PHASE (gas)": "fluid_phase",
    "SOLID PHASE": "solid_phase",
    "FLUID PHASE (organic volatile": "fluid_phase_volatiles",
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


def _stream_ids(table: list[list]) -> list[tuple[int, str]]:
    for row in table:
        if row and _cell_text(row[1]) == "STREAM / UNIT No.":
            out: list[tuple[int, str]] = []
            for j, cell in enumerate(row):
                sid = _cell_text(cell)
                if sid.startswith("13"):
                    out.append((j, sid))
            return out
    return []


def _section_from_label(label: str) -> str | None:
    upper = label.upper()
    for marker, name in SECTION_BY_MARKER.items():
        if upper.startswith(marker.upper()):
            return name
    return None


def _property_name(label: str, unit: str, section: str) -> str:
    key = label.lower().replace(" ", "_")
    if label.upper() in GAS_SPECIES:
        return label.upper() if label.upper() != "AR" else "Ar"
    if label == "AR":
        return "Ar"
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
    streams = _stream_ids(table)
    if not streams:
        return []

    section = "overall"
    rows: list[dict[str, str]] = []
    pending_remark_stream: str | None = None

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
        if not label and unit:
            # remark 续行等：拼到 remark_2
            if pending_remark_stream:
                for j, sid in streams:
                    cont = _cell_text(row[j])
                    if cont:
                        for r in rows:
                            if (
                                r["stream_id"] == sid
                                and r["section"] == "stream_info"
                                and r["property"] == "remark_2"
                            ):
                                r["value"] = f"{r['value']} {cont}".strip()
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
            if label.startswith("remark"):
                pending_remark_stream = sid if raw else pending_remark_stream
            entry = {
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
            rows.append(entry)

    return rows


def extract_stream_table(
    pdf_path: Path | str = DEFAULT_PDF,
    *,
    pages: tuple[int, ...] = (2, 3),
) -> pd.DataFrame:
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"DBI PDF 不存在: {path}")

    all_rows: list[dict[str, str]] = []
    with pdfplumber.open(path) as doc:
        for page_no in pages:
            if page_no < 1 or page_no > len(doc.pages):
                raise ValueError(f"页码越界: {page_no} (共 {len(doc.pages)} 页)")
            page = doc.pages[page_no - 1]
            tables = page.extract_tables()
            if not tables:
                raise ValueError(f"第 {page_no} 页未检测到表格")
            table = tables[0]
            design_case = _design_case_label(table)
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
        raise ValueError("未解析到任何 stream table 行")
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="提取 DBI INCI stream table 为 CSV")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF, help="DBI PDF 路径")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="输出 CSV 路径")
    parser.add_argument(
        "--nonempty-only",
        action="store_true",
        help="仅保留 value 非空的行（默认输出全量含空单元格）",
    )
    args = parser.parse_args()

    df = extract_stream_table(args.pdf)
    if args.nonempty_only:
        df = df.loc[df["value"].astype(str).str.len() > 0].copy()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False, encoding="utf-8")
    streams = sorted(df["stream_id"].unique())
    print(f"已写入 {args.out}")
    print(f"  行数: {len(df)}  流股: {len(streams)}  -> {', '.join(streams)}")
    print("  注意: PDF 提取数据仅保存在本地，已配置 .gitignore，请勿 git add / push。")


if __name__ == "__main__":
    main()
