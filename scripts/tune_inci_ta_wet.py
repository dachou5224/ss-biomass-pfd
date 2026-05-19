#!/usr/bin/env python3
"""INCI 湿基 TA 调参：网格扫描或打印全湿基组成 vs DBI。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from simulator.backend import run_fixed_temperature_simulation, _calc_rmsd_pct
from simulator.data import REFERENCE_CASES, build_chem_df, build_feed_df, build_specs_df
from simulator.parameters import INCI_WET_MAJOR_KEYS, model_parameters
from simulator.species import INCI_UNMODELLED_WET_SPECIES
from simulator.ta_tuning import grid_search_inci_ta, ref_h2o, set_ta_on_chem_df


def _wet_full_keys(case_id: str) -> list[str]:
    dbi = REFERENCE_CASES[case_id]["expected"].get("inci_comp_wet_full", {})
    return [k for k in dbi if k not in INCI_UNMODELLED_WET_SPECIES]


def print_full_wet_compare(case_id: str, *, eta1: bool) -> None:
    dbi = REFERENCE_CASES[case_id]["expected"]["inci_comp_wet_full"]
    chem = build_chem_df(case_id)
    if eta1:
        chem = set_ta_on_chem_df(
            chem,
            dt_wgs_c=float(chem.loc[chem["Field"] == "TA DeltaT WGS (C)", "Value"].iloc[0]),
            dt_meth_c=float(chem.loc[chem["Field"] == "TA DeltaT Meth (C)", "Value"].iloc[0]),
            eta_wgs=1.0,
            eta_meth=1.0,
        )
    res = run_fixed_temperature_simulation(build_feed_df(case_id), build_specs_df(), chem)
    m = res.inci_comp_wet_full_vol_pct
    keys = _wet_full_keys(case_id)
    rmsd5 = _calc_rmsd_pct(m, dbi, list(INCI_WET_MAJOR_KEYS))
    rmsd_all = _calc_rmsd_pct(m, dbi, keys)
    mp = model_parameters()["chemistry_setup"]
    print(f"=== {case_id} 全湿基 vs DBI (13PGI-1) ===")
    print(
        f"TA WGS={mp['TA DeltaT WGS (C)']:+.0f}°C  Meth={mp['TA DeltaT Meth (C)']:+.0f}°C  "
        f"η_WGS={mp['WGS Equilibrium Approach Eta']:.2f}  η_Meth={mp['Meth Equilibrium Approach Eta']:.2f}"
    )
    print(f"RMSD 五主+H2O={rmsd5:.3f}%  全湿基(已建模)={rmsd_all:.3f}%")
    print(f"{'物种':<6} {'模型':>10} {'DBI':>10} {'Δ pp':>10}")
    for s in keys:
        mv, dv = m.get(s, 0.0), dbi.get(s, 0.0)
        print(f"{s:<6} {mv:10.4f} {dv:10.4f} {mv - dv:+10.4f}")
    unmodelled = [k for k in dbi if k in INCI_UNMODELLED_WET_SPECIES]
    if unmodelled:
        print(f"(DBI 未建模: {', '.join(f'{k}={dbi[k]:.4f}%' for k in unmodelled)})")


def main() -> None:
    parser = argparse.ArgumentParser(description="INCI TA 湿基调参 / 对标打印")
    parser.add_argument("--case", default="Case-1")
    parser.add_argument("--top", type=int, default=15, help="网格扫描打印前 N 组")
    parser.add_argument("--compare", action="store_true", help="打印当前 config 全湿基对比")
    parser.add_argument("--eta1", action="store_true", help="与 --compare 联用：强制 η=1")
    args = parser.parse_args()

    if args.compare:
        print_full_wet_compare(args.case, eta1=args.eta1)
        return

    results = grid_search_inci_ta(args.case)
    h2o_ref = ref_h2o(args.case)
    print(f"=== {args.case} 湿基主组分 TA 扫描 (DBI H2O={h2o_ref:.2f}%) ===")
    print(f"{'RMSD':>7} {'dH2O':>6} {'WGS':>5} {'Meth':>5} {'eWGS':>5} {'eMet':>5}  组成 (湿基 vol%)")
    for row in results[: args.top]:
        m = row.comp_wet_vol_pct
        print(
            f"{row.rmsd_wet_pct:7.3f} {m.get('H2O', 0) - h2o_ref:+6.2f} "
            f"{row.dt_wgs_c:5.0f} {row.dt_meth_c:5.0f} {row.eta_wgs:5.2f} {row.eta_meth:5.2f}  "
            f"H2O={m.get('H2O', 0):.2f} CO={m.get('CO', 0):.2f} H2={m.get('H2', 0):.2f} "
            f"CO2={m.get('CO2', 0):.2f} CH4={m.get('CH4', 0):.2f}"
        )


if __name__ == "__main__":
    main()
