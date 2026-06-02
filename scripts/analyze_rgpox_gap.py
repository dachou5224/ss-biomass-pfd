#!/usr/bin/env python3
"""Case-1 RGPOX 15PGR-1/15PGR-2 质量与组成 vs DBI 分解。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.backend import run_fixed_temperature_simulation  # noqa: E402
from simulator.data import REFERENCE_CASES  # noqa: E402
from simulator.reference_streams import expected_pox_gas_ante_kg_h  # noqa: E402
from simulator.parameters import INCI_WET_MAJOR_KEYS, model_parameters  # noqa: E402
from simulator.species import MOLECULAR_WEIGHT, species_flow_mass_kg_h  # noqa: E402
from simulator.webservice_demo import (  # noqa: E402
    build_chem_df_from_inputs,
    build_feed_df_from_inputs,
    build_specs_df_from_inputs,
    _merge_inputs,
)


def _dry_mass_kg_h(flow: dict) -> float:
    return sum(
        max(flow.get(sp, 0.0), 0.0) * MOLECULAR_WEIGHT[sp] / 1000.0
        for sp in flow
        if sp != "H2O" and sp in MOLECULAR_WEIGHT
    )


def main() -> None:
    case_id = "Case-1"
    inputs = _merge_inputs({"case_id": case_id})
    res = run_fixed_temperature_simulation(
        build_feed_df_from_inputs(inputs),
        build_specs_df_from_inputs(inputs),
        build_chem_df_from_inputs(inputs),
    )
    exp = REFERENCE_CASES[case_id]["expected"]
    mp = model_parameters()["chemistry_setup"]

    print("=== RGPOX 调参基线 (Case-1) ===")
    print(
        f"TA WGS={mp['RGPOX TA DeltaT WGS (C)']:+.0f}°C  Meth={mp['RGPOX TA DeltaT Meth (C)']:+.0f}°C  "
        f"η_WGS={mp['RGPOX WGS Equilibrium Approach Eta']:.2f}"
    )
    if res.rgpox_inlet_audit:
        a = res.rgpox_inlet_audit
        print(f"进料门禁: ready={a.ready_for_ta_tuning}  blockers={a.blockers or '—'}")
        print(f"15PGI-1 气相湿基 RMSD(继承 INCI): {a.gas_wet_rmsd_pct:.3f}%")

    print("\n--- 边界质量 (kg/h) ---")
    if res.rgpox_inlet_audit:
        for row in res.rgpox_inlet_audit.mass_rows:
            if row.component in ("fluid_gas", "volatiles", "solid", "TOTAL", "oxygen_total"):
                print(
                    f"  {row.stream_id:8s} {row.component:14s} "
                    f"model={row.model_kg_h:8.1f} DBI={row.dbi_kg_h:8.1f} Δ={row.delta_kg_h:+8.1f}"
                )

    dbi_post = float(exp["pox_gas_kg_h"])
    dbi_ante = expected_pox_gas_ante_kg_h(exp)
    ante = res.pox_gas_ante_kg_h
    post = res.pox_gas_kg_h
    char_cfg = model_parameters()["rgpox"].get("char_gasification", {})
    print("\n--- char / O2 / 反应顺序 (Phase 4C) ---")
    print(
        f"  顺序={char_cfg.get('reaction_sequence', '—')}  "
        f"O2→Gibbs={char_cfg.get('o2_to_gibbs_mode', '—')}  "
        f"CO2置换={char_cfg.get('char_co2_replace_fraction', 0.0):.2f}"
    )
    rgpox_notes = next((row.notes for row in res.unit_trace if row.unit_name == "RGPOX(RGibbs)"), "")
    if "char gasif" in rgpox_notes:
        print(f"  {rgpox_notes.split('; slag out')[0].split('slag out')[0].split('→ Gibbs; ')[-1]}")
    dbi_quench_water = dbi_post - dbi_ante
    model_quench = float(res.quench_h2o_added_kg_h or 0.0)
    print("\n--- 反应区 / 急冷 ---")
    print(f"  15PGR-1 反应区气相: {ante:,.1f} kg/h  DBI={dbi_ante:,.1f}  Δ={ante - dbi_ante:+,.1f}")
    print(
        f"  急冷加水:           {model_quench:,.1f} kg/h  DBI≈{dbi_quench_water:,.1f}  "
        f"Δ={model_quench - dbi_quench_water:+,.1f}  T_out={res.quench_t_out_c:.1f}°C"
    )
    print(f"  15PGR-2 出口气相:   {post:,.1f} kg/h  DBI={dbi_post:,.1f}  Δ={post - dbi_post:+,.1f}")
    print(
        f"  缺口分解(表观):     Δ15PGR-2 ≈ Δ15PGR-1 + Δ急冷加水 "
        f"= {ante - dbi_ante:+,.0f} + {model_quench - dbi_quench_water:+,.0f} "
        f"= {ante - dbi_ante + model_quench - dbi_quench_water:+,.0f}"
    )
    print("  注：Phase 7 主因假定为激冷水平衡/气液平衡，非 INCI 进料；见 scripts/analyze_quench_balance.py")
    print(f"  pox_ash:            {res.pox_ash_kg_h:.2f}  DBI={exp['pox_ash_kg_h']}")

    print("\n--- 15PGR-1 湿基 vol% (Gibbs+TA 对标) ---")
    ref_ante = exp.get("pox_comp_wet_ante", {})
    print(f"  RMSD = {res.rmsd_pox_wet_ante_pct:.3f}%")
    print(f"  {'物种':<6} {'模型':>8} {'DBI':>8} {'Δ pp':>8}")
    for sp in INCI_WET_MAJOR_KEYS:
        mv = res.pox_comp_wet_ante_vol_pct.get(sp, 0.0)
        dv = ref_ante.get(sp, 0.0)
        print(f"  {sp:<6} {mv:8.3f} {dv:8.3f} {mv - dv:+8.3f}")

    print("\n--- 15PGR-2 湿基 vol% (急冷后) ---")
    ref_post = exp["pox_comp_wet"]
    print(f"  RMSD = {res.rmsd_pox_wet_pct:.3f}%")
    for sp in INCI_WET_MAJOR_KEYS:
        mv = res.pox_comp_wet_vol_pct.get(sp, 0.0)
        dv = ref_post.get(sp, 0.0)
        print(f"  {sp:<6} {mv:8.3f} {dv:8.3f} {mv - dv:+8.3f}")

    print("\n--- 结论提示 ---")
    print("  · RGPOX 反应区已冻结 Phase 6C（见 doc/rgpox_tuning_strategy.md §8）。")
    print(
        f"  · 15PGR-1 Δ={ante - dbi_ante:+,.0f} kg/h；15PGR-2 Δ={post - dbi_post:+,.0f} kg/h（PDF 7760/8843）。"
    )
    print("  · 下一阶段：急冷水平衡/气液平衡见 doc/quench_benchmark.md、scripts/analyze_quench_balance.py")


if __name__ == "__main__":
    main()
