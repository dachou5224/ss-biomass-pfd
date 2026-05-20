#!/usr/bin/env python3
"""RGPOX 湿基 TA 调参：网格扫描或打印全湿基组成 vs DBI 15PGR-2。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from simulator.backend import _calc_rmsd_pct
from simulator.data import REFERENCE_CASES, build_chem_df, build_feed_df, build_specs_df
from simulator.parameters import INCI_WET_MAJOR_KEYS, model_parameters
from simulator.ta_tuning import (
    grid_search_rgpox_ta,
    ref_rgpox_h2o,
    rgpox_wet_major_reference,
    set_rgpox_ta_on_chem_df,
)
from simulator.backend import run_fixed_temperature_simulation


def print_full_wet_compare(case_id: str) -> None:
    dbi_ante = REFERENCE_CASES[case_id]["expected"].get("pox_comp_wet_ante")
    dbi_post = REFERENCE_CASES[case_id]["expected"]["pox_comp_wet"]
    chem = build_chem_df(case_id)
    mp = model_parameters()["chemistry_setup"]
    res = run_fixed_temperature_simulation(build_feed_df(case_id), build_specs_df(), chem)
    m = res.pox_comp_wet_vol_pct
    keys = list(INCI_WET_MAJOR_KEYS)
    print(f"=== {case_id} RGPOX 湿基 vs DBI ===")
    print(
        f"TA WGS={mp['RGPOX TA DeltaT WGS (C)']:+.0f}°C  Meth={mp['RGPOX TA DeltaT Meth (C)']:+.0f}°C  "
        f"η_WGS={mp['RGPOX WGS Equilibrium Approach Eta']:.2f}  η_Meth={mp['RGPOX Meth Equilibrium Approach Eta']:.2f}"
    )
    if dbi_ante:
        rmsd_ante = _calc_rmsd_pct(m, dbi_ante, keys)
        print(f"RMSD 15PGR-1 反应区 @1400°C = {rmsd_ante:.3f}%  (Gibbs+TA 对标目标)")
    rmsd_post = _calc_rmsd_pct(m, dbi_post, keys)
    print(f"RMSD 15PGR-2 急冷后 = {rmsd_post:.3f}%  (需急冷模型，非本阶段 TA 目标)")
    print(f"pox_ash={res.pox_ash_kg_h:.2f} kg/h")
    ref = dbi_ante or dbi_post
    label = "15PGR-1" if dbi_ante else "15PGR-2"
    print(f"{'物种':<6} {'模型':>10} {label:>10} {'Δ pp':>10}")
    for s in keys:
        mv, dv = m.get(s, 0.0), ref.get(s, 0.0)
        print(f"{s:<6} {mv:10.4f} {dv:10.4f} {mv - dv:+10.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="RGPOX TA 湿基调参 / 对标打印")
    parser.add_argument("--case", default="Case-1")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--phase", choices=("wgs", "wgs_meth", "full"), default="wgs_meth")
    args = parser.parse_args()

    if args.compare:
        print_full_wet_compare(args.case)
        return

    if args.phase == "wgs":
        grid = dict(
            dt_wgs_values=(-160, -120, -80, -40, 0, 40, 80, 120),
            dt_meth_values=(0.0,),
            eta_wgs_values=(1.0,),
            eta_meth_values=(1.0,),
        )
    elif args.phase == "wgs_meth":
        grid = dict(
            dt_wgs_values=(-120, -80, -40, 0, 40, 80),
            dt_meth_values=(-100, 0, 100, 200, 350, 500),
            eta_wgs_values=(1.0,),
            eta_meth_values=(1.0,),
        )
    else:
        grid = dict(
            dt_wgs_values=(-80, -40, 0, 40),
            dt_meth_values=(0, 200, 350),
            dt_ox_co_values=(-80, 0, 80),
            dt_ox_h2_values=(-80, 0, 80),
            dt_ox_ch4_values=(0.0,),
            eta_wgs_values=(1.0,),
            eta_meth_values=(1.0,),
        )

    results = grid_search_rgpox_ta(args.case, **grid)
    h2o_ref = ref_rgpox_h2o(args.case)
    print(f"=== {args.case} RGPOX 湿基 TA 扫描 (15PGR-1 H2O={h2o_ref:.2f}%) phase={args.phase} ===")
    print(
        f"{'RMSD':>7} {'dH2O':>6} {'WGS':>5} {'Meth':>5} {'OxCO':>5} {'OxH2':>5}  "
        f"组成 (湿基 vol%)"
    )
    for row in results[: args.top]:
        m = row.comp_wet_vol_pct
        print(
            f"{row.rmsd_wet_pct:7.3f} {m.get('H2O', 0) - h2o_ref:+6.2f} "
            f"{row.dt_wgs_c:5.0f} {row.dt_meth_c:5.0f} {row.dt_ox_co_c:5.0f} {row.dt_ox_h2_c:5.0f}  "
            f"H2O={m.get('H2O', 0):.2f} CO={m.get('CO', 0):.2f} H2={m.get('H2', 0):.2f} "
            f"CO2={m.get('CO2', 0):.2f} CH4={m.get('CH4', 0):.3f}"
        )


if __name__ == "__main__":
    main()
