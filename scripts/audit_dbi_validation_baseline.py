#!/usr/bin/env python3
"""对照 reference_cases.json、RGPOX 质量衡算 CSV 与 Unit 15 PDF 提取长表，报告不一致项。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.parameters import load_json_config, model_parameters  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TABLE = PROJECT_ROOT / "data" / "reference" / "dbi_rgpox_stream_table_case1.csv"


def _val(df, stream_id: str, section: str, prop: str) -> float | None:
    import pandas as pd

    if not isinstance(df, pd.DataFrame):
        return None
    mask = (df["stream_id"] == stream_id) & (df["section"] == section) & (df["property"] == prop)
    subset = df.loc[mask, "value"]
    if subset.empty:
        return None
    text = str(subset.iloc[0]).strip().replace("%", "")
    if not text:
        return None
    return float(text)


def main() -> None:
    parser = argparse.ArgumentParser(description="审计 DBI validation 基线一致性")
    parser.add_argument("--case", default="Case-1")
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    args = parser.parse_args()

    import pandas as pd

    ref = load_json_config("reference_cases")[args.case]["expected"]
    paths = model_parameters()["paths"]
    mb_path = PROJECT_ROOT / paths["dbi_rgpox_mass_balance_csv"]
    mb = pd.read_csv(mb_path) if mb_path.is_file() else None
    table = pd.read_csv(args.table) if args.table.is_file() else None

    checks: list[tuple[str, float | None, float | None, str]] = []

    def add(label: str, json_key: str, pdf_sid: str, pdf_section: str = "fluid_phase", csv_role: str | None = None):
        json_v = ref.get(json_key)
        pdf_v = _val(table, pdf_sid, pdf_section, "flow_kg_h") if table is not None else None
        csv_v = None
        if mb is not None and csv_role:
            row = mb.loc[(mb["case"] == args.case) & (mb["balance_role"] == csv_role)]
            if not row.empty:
                csv_v = float(row.iloc[0]["mass_kg_h"])
        checks.append((label, json_v, pdf_v or csv_v, json_key))

    add("15PGR-1 湿煤气 (Gibbs)", "pox_gas_ante_kg_h", "15PGR-1", csv_role="outlet_gas_ante")
    add("15PGR-2 湿煤气 (急冷后)", "pox_gas_kg_h", "15PGR-2", csv_role="outlet_gas_post")
    add("15PGR-1 slag", "pox_ash_kg_h", "15PGR-1", pdf_section="solid_phase")
    if table is not None:
        checks.append(
            (
                "15PGR-1-dry 干气",
                ref.get("pox_gas_ante_dry_kg_h"),
                _val(table, "15PGR-1-dry", "fluid_phase", "flow_kg_h"),
                "pox_gas_ante_dry_kg_h",
            )
        )
        checks.append(
            (
                "15PGR-2-dry 干气",
                ref.get("pox_gas_dry_kg_h"),
                _val(table, "15PGR-2-dry", "fluid_phase", "flow_kg_h"),
                "pox_gas_dry_kg_h",
            )
        )

    print(f"=== DBI validation 基线审计 ({args.case}) ===")
    print(f"reference_cases.json vs PDF/CSV")
    if table is None:
        print(f"  警告: 缺少 {args.table}，运行 scripts/extract_dbi_rgpox_stream_table.py")
    print(f"{'指标':<28} {'JSON':>10} {'PDF/CSV':>10} {'Δ':>10} 状态")
    issues = 0
    for label, json_v, auth_v, _ in checks:
        if json_v is None:
            print(f"{label:<28} {'—':>10} {auth_v or '—':>10} {'—':>10}  JSON 缺字段")
            issues += 1
            continue
        if auth_v is None:
            print(f"{label:<28} {json_v:10.2f} {'—':>10} {'—':>10}  无 PDF/CSV")
            continue
        delta = float(json_v) - float(auth_v)
        ok = abs(delta) < 0.51
        status = "OK" if ok else "MISMATCH"
        if not ok:
            issues += 1
        print(f"{label:<28} {float(json_v):10.2f} {float(auth_v):10.2f} {delta:+10.2f}  {status}")

    wet_ante = ref.get("pox_comp_wet_ante", {})
    if table is not None and wet_ante:
        print("\n--- 15PGR-1 湿基主组分 (JSON vs PDF) ---")
        for sp in ("CO", "H2", "CO2", "CH4", "H2O"):
            pdf_v = _val(table, "15PGR-1", "fluid_phase", sp)
            json_v = wet_ante.get(sp)
            if pdf_v is None or json_v is None:
                continue
            d = float(json_v) - pdf_v
            print(f"  {sp:<4} JSON={json_v:8.3f}  PDF={pdf_v:8.3f}  Δ={d:+.3f}")

    print(f"\n不一致项: {issues}")
    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
