#!/usr/bin/env python3
"""RGPOX 湿基 TA / char 气化调参：网格扫描或打印全湿基组成 vs DBI 15PGR-1。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from simulator.backend import _calc_rmsd_pct, run_fixed_temperature_simulation
from simulator.data import REFERENCE_CASES, build_chem_df, build_feed_df, build_specs_df
from simulator.parameters import INCI_WET_MAJOR_KEYS, model_parameters
from simulator.ta_tuning import (
    RgpoxCharTuneResult,
    RgpoxCombinedTaTuneResult,
    evaluate_rgpox_char_gasification,
    grid_search_rgpox_char_gasification,
    grid_search_rgpox_combined_ta,
    grid_search_rgpox_ta,
    ref_rgpox_h2o,
    rgpox_wet_major_reference,
)


def print_full_wet_compare(case_id: str) -> None:
    dbi_ante = REFERENCE_CASES[case_id]["expected"].get("pox_comp_wet_ante")
    dbi_post = REFERENCE_CASES[case_id]["expected"]["pox_comp_wet"]
    chem = build_chem_df(case_id)
    mp = model_parameters()["chemistry_setup"]
    res = run_fixed_temperature_simulation(build_feed_df(case_id), build_specs_df(), chem)
    m = res.pox_comp_wet_ante_vol_pct
    keys = list(INCI_WET_MAJOR_KEYS)
    print(f"=== {case_id} RGPOX 湿基 vs DBI ===")
    print(
        f"TA WGS={mp['RGPOX TA DeltaT WGS (C)']:+.0f}°C  Meth={mp['RGPOX TA DeltaT Meth (C)']:+.0f}°C  "
        f"η_WGS={mp['RGPOX WGS Equilibrium Approach Eta']:.2f}  η_Meth={mp['RGPOX Meth Equilibrium Approach Eta']:.2f}"
    )
    char_cfg = model_parameters()["rgpox"]["char_gasification"]
    print(
        f"char: seq={char_cfg.get('reaction_sequence')}  O2→Gibbs={char_cfg.get('o2_to_gibbs_mode')}  "
        f"CO2置换={char_cfg.get('char_co2_replace_fraction')}  Boud={char_cfg.get('enable_boudouard')}  "
        f"steam={char_cfg.get('enable_steam_gasification')}@{char_cfg.get('char_steam_fraction')}"
    )
    if dbi_ante:
        rmsd_ante = _calc_rmsd_pct(m, dbi_ante, keys)
        print(f"RMSD 15PGR-1 反应区 @1400°C = {rmsd_ante:.3f}%  (Gibbs+TA 对标目标)")
    rmsd_post = _calc_rmsd_pct(m, dbi_post, keys)
    print(f"RMSD 15PGR-2 急冷后 = {rmsd_post:.3f}%  (需急冷模型，非本阶段 TA 目标)")
    print(f"pox_ash={res.pox_ash_kg_h:.2f} kg/h  pox_gas_ante={res.pox_gas_ante_kg_h:.1f} kg/h")
    ref = dbi_ante or dbi_post
    label = "15PGR-1" if dbi_ante else "15PGR-2"
    print(f"{'物种':<6} {'模型':>10} {label:>10} {'Δ pp':>10}")
    for s in keys:
        mv, dv = m.get(s, 0.0), ref.get(s, 0.0)
        print(f"{s:<6} {mv:10.4f} {dv:10.4f} {mv - dv:+10.4f}")


def _print_char_row(row: RgpoxCharTuneResult, h2o_ref: float) -> None:
    d = row.delta_pp
    print(
        f"{row.co_co2_mae_pp:6.2f} {row.rmsd_wet_pct:6.3f} "
        f"{d.get('CO', 0):+5.2f} {d.get('CO2', 0):+5.2f} {d.get('H2', 0):+5.2f} "
        f"{row.h2o_wet_pct - h2o_ref:+5.2f} {row.pox_ash_kg_h:6.2f} {row.pox_gas_ante_kg_h:7.0f}  "
        f"R={row.char_co2_replace_fraction:.2f} B={int(row.enable_boudouard)} "
        f"S={int(row.enable_steam_gasification)}@{row.char_steam_fraction:.1f} "
        f"O2={row.o2_to_gibbs_mode}"
    )


def _print_combined_ta_row(row: RgpoxCombinedTaTuneResult) -> None:
    d = row.delta_pp
    alpha = row.char_boud_fraction
    alpha_s = f"{alpha:.2f}" if alpha is not None else "  —"
    print(
        f"{row.rmsd_wet_pct:7.3f} {row.pox_gas_ante_kg_h:7.0f} {alpha_s:>5} "
        f"{row.dt_wgs_c:+5.0f} {row.dt_meth_c:+5.0f} {row.dt_ox_co_c:+5.0f} {row.dt_ox_h2_c:+5.0f} "
        f"{row.dt_boudouard_c:+5.0f} {row.dt_char_steam_c:+5.0f}  "
        f"CO{d.get('CO', 0):+5.2f} CO2{d.get('CO2', 0):+5.2f} H2{d.get('H2', 0):+5.2f} H2O{d.get('H2O', 0):+5.2f}"
    )


def run_combined_ta_scan(case_id: str, phase: str, top: int, min_ante: float | None) -> None:
    ref = rgpox_wet_major_reference(case_id) or {}
    print(f"=== {case_id} Phase 6 联合 TA 扫描（middle-way + hetero_ta，η=1.0）===")
    print(f"DBI 15PGR-1: CO={ref.get('CO', 0):.2f}% CO2={ref.get('CO2', 0):.2f}% H2O={ref.get('H2O', 0):.2f}%")
    if min_ante is not None:
        print(f"过滤: pox_gas_ante >= {min_ante:.0f} kg/h")
    print(
        f"{'RMSD':>7} {'ante':>7} {'α':>5} {'WGS':>5} {'Met':>5} {'OxC':>5} {'OxH':>5} "
        f"{'Boud':>5} {'Stm':>5}  Δpp"
    )

    if phase == "combined_ta_phase6d":
        grid = dict(
            dt_wgs_values=(-160, -150, -145, -140),
            dt_meth_values=(0.0,),
            dt_boudouard_values=(-100, -90, -80),
            dt_char_steam_values=(-60, -40, -20, 0, 20),
            char_boud_fraction_values=(0.0, 0.1, 0.15, 0.2, 0.25, 0.3),
            char_overrides={"gasification_order": "boudouard_first"},
            min_ante_kg_h=min_ante,
            sort_by="phase6d",
        )
    elif phase == "combined_ta":
        grid = dict(
            dt_wgs_values=(-160, -120, -80, -40, 0, 40),
            dt_meth_values=(0.0, 200.0),
            dt_boudouard_values=(-80, -40, 0, 40, 80),
            dt_char_steam_values=(-80, -40, 0, 40, 80),
            min_ante_kg_h=min_ante,
        )
    elif phase == "combined_ta_wide":
        grid = dict(
            dt_wgs_values=(-160, -120, -80, -40, 0, 40, 80),
            dt_meth_values=(-100.0, 0.0, 100.0, 300.0),
            dt_ox_co_values=(-80.0, 0.0, 80.0),
            dt_ox_h2_values=(-80.0, 0.0, 80.0),
            dt_boudouard_values=(-120, -60, 0, 60, 120),
            dt_char_steam_values=(-120, -60, 0, 60, 120),
            min_ante_kg_h=min_ante,
        )
    elif phase == "combined_ta_coarse":
        grid = dict(
            dt_wgs_values=(-120, -60, 0, 60),
            dt_meth_values=(0.0,),
            dt_boudouard_values=(-60, 0, 60),
            dt_char_steam_values=(-60, 0, 60),
            min_ante_kg_h=min_ante,
        )
    elif phase == "combined_ta_fine":
        grid = dict(
            dt_wgs_values=(-160, -140, -120),
            dt_meth_values=(0.0,),
            dt_boudouard_values=(-100, -80, -60),
            dt_char_steam_values=(0.0,),
            min_ante_kg_h=min_ante,
        )
    else:
        raise ValueError(f"unknown combined phase: {phase}")

    results = grid_search_rgpox_combined_ta(case_id, **grid)
    print(f"有效组合: {len(results)}")
    for row in results[:top]:
        _print_combined_ta_row(row)


def run_char_scan(case_id: str, phase: str, top: int) -> None:
    ref = rgpox_wet_major_reference(case_id) or {}
    h2o_ref = ref_rgpox_h2o(case_id)
    baseline_co2 = ref.get("CO2", 0.0)
    baseline_co = ref.get("CO", 0.0)

    if phase == "char_reduce":
        grid = dict(
            char_co2_replace_values=(0.375, 0.25, 0.15, 0.0),
            enable_boudouard_values=(True, False),
            enable_steam_values=(True, False),
            char_steam_fraction_values=(1.0, 0.5),
            o2_to_gibbs_mode_values=("char_stoich_co",),
            sort_by="co_co2",
        )
        title = "第1轮：削弱 char 后置还原（固定 char_stoich_co）"
    elif phase == "char_o2":
        grid = dict(
            char_co2_replace_values=(0.375, 0.15, 0.0),
            enable_boudouard_values=(True, False),
            enable_steam_values=(True,),
            char_steam_fraction_values=(1.0,),
            o2_to_gibbs_mode_values=("char_stoich_co", "char_stoich_co2"),
            sort_by="co_co2",
        )
        title = "第2轮：O₂→Gibbs 模式（char_stoich_co vs char_stoich_co2）"
    elif phase == "char_combo":
        grid = dict(
            char_co2_replace_values=(0.0, 0.15),
            enable_boudouard_values=(False,),
            enable_steam_values=(True, False),
            char_steam_fraction_values=(0.5, 1.0),
            o2_to_gibbs_mode_values=("char_stoich_co2", "char_stoich_co"),
            sort_by="co_co2",
        )
        title = "第3轮：组合（低还原 + 加强 O₂）"
    elif phase == "char_mass":
        title = "Phase 4E：o2_to_gibbs_char_mol_ratio × post_char O₂"
        results: list[RgpoxCharTuneResult] = []
        base = {
            "o2_to_gibbs_mode": "char_stoich_co2",
            "char_co2_replace_fraction": 0.0,
            "enable_boudouard": False,
            "enable_steam_gasification": True,
            "char_steam_fraction": 1.0,
            "reaction_sequence": "gas_equilibrium_first",
        }
        for ratio in (0.5, 0.65, 0.75, 0.85, 0.95, 1.0):
            for post in (False, True):
                results.append(
                    evaluate_rgpox_char_gasification(
                        case_id,
                        char_overrides={**base, "o2_to_gibbs_char_mol_ratio": ratio, "post_char_use_remaining_o2": post},
                    )
                )
        results.sort(key=lambda r: (r.co_co2_mae_pp, r.rmsd_wet_pct))
        ref = rgpox_wet_major_reference(case_id) or {}
        h2o_ref = ref_rgpox_h2o(case_id)
        print(f"=== {case_id} RGPOX char 扫描 — {title} ===")
        print(f"DBI 15PGR-1 参考: CO={ref.get('CO', 0):.2f}%  CO2={ref.get('CO2', 0):.2f}%")
        print(
            f"{'|ΔCO|+|ΔCO2|':>12} {'RMSD':>6} {'ΔCO':>6} {'ΔCO2':>6} {'ΔH2':>6} "
            f"{'ash':>6} {'gas_a':>7}  ratio post_O2"
        )
        for row in results[:top]:
            d = row.delta_pp
            print(
                f"{row.co_co2_mae_pp:12.2f} {row.rmsd_wet_pct:6.3f} {d.get('CO', 0):+6.2f} "
                f"{d.get('CO2', 0):+6.2f} {d.get('H2', 0):+6.2f} {row.pox_ash_kg_h:6.2f} "
                f"{row.pox_gas_ante_kg_h:7.0f}  {row.o2_to_gibbs_char_mol_ratio or 0:.2f} {row.post_char_use_remaining_o2}"
            )
        return
    else:
        raise ValueError(f"unknown char phase: {phase}")

    results = grid_search_rgpox_char_gasification(case_id, **grid)
    print(f"=== {case_id} RGPOX char 扫描 — {title} ===")
    print(f"DBI 15PGR-1 参考: CO={baseline_co:.2f}%  CO2={baseline_co2:.2f}%  H2O={h2o_ref:.2f}%")
    print(
        f"{'|ΔCO|+|ΔCO2|':>12} {'RMSD':>6} {'ΔCO':>6} {'ΔCO2':>6} {'ΔH2':>6} {'ΔH2O':>6} "
        f"{'ash':>6} {'gas_a':>7}  参数"
    )
    for row in results[:top]:
        _print_char_row(row, h2o_ref)


def main() -> None:
    parser = argparse.ArgumentParser(description="RGPOX 湿基 TA / char 调参 / 对标打印")
    parser.add_argument("--case", default="Case-1")
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--compare", action="store_true", help="打印当前默认参数全湿基对标")
    parser.add_argument(
        "--phase",
        choices=(
            "wgs",
            "wgs_meth",
            "full",
            "char_reduce",
            "char_o2",
            "char_combo",
            "char_mass",
            "char_all",
            "combined_ta",
            "combined_ta_wide",
            "combined_ta_coarse",
            "combined_ta_fine",
            "combined_ta_phase6d",
        ),
        default="wgs_meth",
    )
    parser.add_argument(
        "--min-ante",
        type=float,
        default=None,
        help="联合 TA 扫描时过滤 pox_gas_ante_kg_h 下限（kg/h）",
    )
    args = parser.parse_args()

    if args.compare:
        print_full_wet_compare(args.case)
        return

    if args.phase.startswith("char"):
        if args.phase == "char_all":
            for ph in ("char_reduce", "char_o2", "char_combo", "char_mass"):
                run_char_scan(args.case, ph, args.top)
                print()
            return
        run_char_scan(args.case, args.phase, args.top)
        return

    if args.phase.startswith("combined_ta"):
        run_combined_ta_scan(args.case, args.phase, args.top, args.min_ante)
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
