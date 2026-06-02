#!/usr/bin/env python3
"""Case-1 INCI 13PGI-1 气相质量流量 vs DBI 分解（元素/摩尔/分物种）。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulator.backend import (  # noqa: E402
    DEFAULT_BIOMASS_SAMPLE_FALLBACK,
    _allocate_trace_species_from_biomass,
    _apply_inci_n2_makeup,
    _apply_restricted_equilibrium_ta,
    _build_inci_elemental_inlet,
    _chem_text,
    _compute_inci_n2_makeup_mol_h,
    _feed_inert_moles,
    _feed_map,
    _kg_to_mol_h,
    _match_reference_case,
    _resolve_inci_fly_ash_params,
    _resolve_inci_n2_makeup_target_wet_pct,
    _resolve_inci_target_conversion,
    run_fixed_temperature_simulation,
)
from simulator.data import REFERENCE_CASES  # noqa: E402
from simulator.elemental import BIOMASS_SAMPLES, biomass_sample_from_chem, biomass_vm_dry_pct, biomass_to_elemental_moles_for_chem  # noqa: E402
from simulator.feed_streams import inci_o2_stream_species_kg_h  # noqa: E402
from simulator.gibbs import solve_gibbs_major  # noqa: E402
from simulator.inci_conversion import resolve_inci_solid_routing  # noqa: E402
from simulator.parameters import (  # noqa: E402
    CELSIUS_TO_KELVIN_OFFSET,
    DEFAULT_CHEMISTRY_SETUP,
    INCI_FBR_SOLIDS_CFG,
    INCI_WET_SPECIES,
    MAJOR_SPECIES,
    SLAG_CFG,
)
from simulator.pyrolysis import allocate_pyrolysis_products_elemental  # noqa: E402
from simulator.reference_streams import load_inci_stream_reference  # noqa: E402
from simulator.species import MOLECULAR_WEIGHT, elemental_totals_from_species, species_flow_mass_kg_h  # noqa: E402
from simulator.tar_models import parse_tar_yield_mass_kg_h, tar_allocation_mass_kg_h  # noqa: E402
from simulator.webservice_demo import (  # noqa: E402
    build_chem_df_from_inputs,
    build_feed_df_from_inputs,
    build_specs_df_from_inputs,
    _merge_inputs,
)


def _snap(name: str, flow: dict) -> tuple[float, float]:
    wet_mol = sum(max(flow.get(k, 0.0), 0.0) for k in INCI_WET_SPECIES if k in MOLECULAR_WEIGHT)
    mass = species_flow_mass_kg_h(flow)
    elem = elemental_totals_from_species(flow, ["C", "H", "O", "N", "S"])
    print(f"\n=== {name} ===")
    print(f"  wet mol/h: {wet_mol:,.0f} | mass: {mass:,.1f} kg/h | MW: {mass / wet_mol * 1000:.3f} g/mol")
    print(
        f"  C/H/O kg/h: {elem['C'] * 12.011 / 1000:.1f} / "
        f"{elem['H'] * 1.008 / 1000:.1f} / {elem['O'] * 16 / 1000:.1f}"
    )
    return mass, wet_mol


def main() -> None:
    inputs = _merge_inputs({"case_id": "Case-1"})
    feed_df = build_feed_df_from_inputs(inputs)
    specs_df = build_specs_df_from_inputs(inputs)
    chem_df = build_chem_df_from_inputs(inputs)
    res = run_fixed_temperature_simulation(feed_df, specs_df, chem_df)
    audit = res.inci_mass_audit

    feed = _feed_map(feed_df)
    specs = {r["Parameter"]: r["Value"] for _, r in specs_df.iterrows()}
    chem = {r["Field"]: str(r["Value"]) for _, r in chem_df.iterrows()}
    sample = chem.get("Sample", DEFAULT_BIOMASS_SAMPLE_FALLBACK)
    matched = _match_reference_case(feed, sample)
    dbi_basis = REFERENCE_CASES[matched]["expected"].get("dbi_inci_boundary_basis") if matched else None

    tar_yield = parse_tar_yield_mass_kg_h(
        feed.get("Biomass", 0.0),
        sample,
        chem.get("Tar Yield Factor", DEFAULT_CHEMISTRY_SETUP["Tar Yield Factor"]),
    )
    vm_frac = biomass_vm_dry_pct(chem) / 100.0
    biomass_elem = biomass_to_elemental_moles_for_chem(chem, feed.get("Biomass", 0.0))
    bio_sample = biomass_sample_from_chem(chem)
    moisture_mol = _kg_to_mol_h(feed.get("Biomass", 0.0) * bio_sample.mad_pct / 100.0, 18.015)
    vm_elem = {k: biomass_elem[k] * (vm_frac if k == "C" else 1.0) for k in biomass_elem}
    nonvm_c = max(biomass_elem["C"] - vm_elem["C"], 0.0)

    pyro = allocate_pyrolysis_products_elemental(
        nC=vm_elem["C"],
        nH=vm_elem["H"],
        nO=vm_elem["O"],
        nN=vm_elem["N"],
        nS=vm_elem["S"],
        tar_carbon_frac=float(chem.get("Pyrolysis Tar Carbon Frac", "0")),
        target_tar_hc_ratio=float(chem.get("Tar target H/C", DEFAULT_CHEMISTRY_SETUP["Tar target H/C"])),
        tar_fuel_type=chem.get("Tar Fuel Type", "biomass").strip().lower(),
        include_tar_internal=chem.get("Tar Internal Path", "off").strip().lower() in ("on", "true", "1", "yes"),
        scheme=chem.get("Pyrolysis Scheme", DEFAULT_CHEMISTRY_SETUP["Pyrolysis Scheme"]).strip().lower(),
        tar_outlet_mass_kg_h=tar_yield,
        nh3_frac_of_n=float(chem.get("Biomass N to NH3 Frac", 0.5)),
        s_release_frac=float(chem.get("Biomass S Release Frac", 0.5)),
        h2s_split=float(chem.get("H2S/COS split to H2S", 0.9)),
    )

    inci_inlet_elem, ash_kg = _build_inci_elemental_inlet(feed, sample, chem)
    co2_kg = feed.get("CO2IN", 0.0) + feed.get("CIN", 0.0)
    o2_parts = inci_o2_stream_species_kg_h(feed.get("O2IN", 0.0), chem)
    inci_ext = {
        "C": _kg_to_mol_h(co2_kg, 44.009),
        "H": 2.0 * (_kg_to_mol_h(feed.get("H2OIN", 0.0), 18.015) + moisture_mol),
        "O": 2.0 * _kg_to_mol_h(o2_parts.get("O2", 0.0), 31.998)
        + (_kg_to_mol_h(feed.get("H2OIN", 0.0), 18.015) + moisture_mol)
        + 2.0 * _kg_to_mol_h(co2_kg, 44.009),
        "N": max(inci_inlet_elem["N"] - biomass_elem["N"], 0.0),
        "Ar": inci_inlet_elem["Ar"] - biomass_elem["Ar"],
    }
    from_pyro = elemental_totals_from_species(pyro.volatile_species_mol_h, ["C", "H", "O", "N", "Ar"])
    routing = resolve_inci_solid_routing(
        biomass_total_c_mol_h=biomass_elem["C"],
        char_pool_c_mol_h=pyro.char_carbon_mol_h + nonvm_c,
        ash_kg_h=ash_kg,
        target_conversion=_resolve_inci_target_conversion(chem, dbi_basis),
        ash_to_slag_frac=float(specs.get("ASH_TO_SLAG_FRAC", 0.6)),
        char_to_slag_frac=float(specs.get("CHAR_TO_SLAG_FRAC", 0.55)),
        slag_residual_c_ash_mass_ratio=float(SLAG_CFG["target_residual_c_ash_mass_ratio"]),
        dbi_boundary_basis=dbi_basis,
        solid_routing_mode=_chem_text(
            chem,
            "INCI Solid Routing Mode",
            str(INCI_FBR_SOLIDS_CFG.get("default_routing_mode", "Fly Ash Ratio")),
        ),
        fly_ash_params=_resolve_inci_fly_ash_params(chem),
    )
    inci_elem = {
        "C": from_pyro["C"] + routing.reactive_char_mol_h + _kg_to_mol_h(co2_kg, 44.009),
        "H": from_pyro["H"] + inci_ext["H"],
        "O": from_pyro["O"] + inci_ext["O"],
        "N": from_pyro["N"] + inci_ext["N"],
        "Ar": from_pyro["Ar"] + inci_ext["Ar"],
        "S": vm_elem["S"],
    }

    t_k = float(specs.get("INCI_T_C", 900.0)) + CELSIUS_TO_KELVIN_OFFSET
    p_bar = float(specs.get("SYSTEM_P_BAR", 15.0))
    gibbs = solve_gibbs_major(inci_elem, MAJOR_SPECIES, t_k, p_bar)
    post_gibbs = dict(gibbs.species_flow_mol_h)
    post_ta = _apply_restricted_equilibrium_ta(
        dict(gibbs.species_flow_mol_h),
        t_gibbs_k=t_k,
        p_bar=p_bar,
        dt_wgs_c=float(chem.get("TA DeltaT WGS (C)", 0.0)),
        dt_meth_c=float(chem.get("TA DeltaT Meth (C)", 0.0)),
        eta_wgs=float(chem.get("WGS Equilibrium Approach Eta", 1.0)),
        eta_meth=float(chem.get("Meth Equilibrium Approach Eta", 1.0)),
        dt_ox_co_c=float(chem.get("TA DeltaT OxCO (C)", 0.0)),
        dt_ox_h2_c=float(chem.get("TA DeltaT OxH2 (C)", 0.0)),
        dt_ox_ch4_c=float(chem.get("TA DeltaT OxCH4 (C)", 0.0)),
    )
    n2, ar = _feed_inert_moles(feed, chem)
    post_trace, minor = _allocate_trace_species_from_biomass(
        post_ta,
        biomass_s_mol_h=biomass_elem["S"],
        biomass_n_mol_h=biomass_elem["N"],
        biomass_cl_mol_h=biomass_elem.get("Cl", 0.0),
        feed_n2_mol_h=n2,
        feed_ar_mol_h=ar,
        h2s_split=float(chem.get("H2S/COS split to H2S", 0.9)),
        nh3_frac_of_biomass_n=float(chem.get("Biomass N to NH3 Frac", 0.5)),
        s_release_frac=float(chem.get("Biomass S Release Frac", 0.5)),
    )
    final = {**post_trace, **minor}
    n2_target = _resolve_inci_n2_makeup_target_wet_pct(chem, matched)
    if n2_target is not None:
        makeup = _compute_inci_n2_makeup_mol_h(final, n2_target)
        if makeup > 0.0:
            final = _apply_inci_n2_makeup(final, makeup)
            print(f"\n  (模型已启用 N2 makeup +{makeup:.0f} mol/h → 湿基 N2={n2_target:.2f}%)")

    _snap("Gibbs 出口 (pre-TA)", post_gibbs)
    _snap("TA 后 (pre-trace)", post_ta)
    base_mass, model_mol = _snap("最终 13PGI-1 气相", final)

    ref = load_inci_stream_reference("Case-1", basis="wet_mol_pct")
    dbi_wet = {k: v / 100.0 for k, v in ref["wet_mol_pct"].items()}
    norm = sum(dbi_wet.values())
    dbi_wet = {k: v / norm for k, v in dbi_wet.items()}
    dbi_gas = 6580.0
    dbi_mol_ref = 298_400.0
    dbi_flow = {k: dbi_mol_ref * dbi_wet.get(k, 0.0) for k in INCI_WET_SPECIES}
    scale = dbi_gas / species_flow_mass_kg_h(dbi_flow)
    dbi_flow = {k: v * scale for k, v in dbi_flow.items()}
    dbi_mol = sum(dbi_flow.values())

    print("\n=== 汇总 ===")
    print(f"Model: {base_mass:.1f} kg/h | {model_mol:,.0f} mol/h | MW={base_mass / model_mol * 1000:.3f}")
    print(f"DBI:   {dbi_gas:.1f} kg/h | {dbi_mol:,.0f} mol/h | MW={dbi_gas / dbi_mol * 1000:.3f}")
    print(f"Δ mass {base_mass - dbi_gas:+.1f} kg/h | Δ mol {model_mol - dbi_mol:+,.0f} ({100 * (model_mol / dbi_mol - 1):+.2f}%)")

    print("\n分物种质量差 (model − DBI) kg/h:")
    for sp in ["H2", "CO", "CO2", "CH4", "H2O", "N2", "Ar", "H2S", "NH3", "COS"]:
        mm = max(final.get(sp, 0.0), 0.0) * MOLECULAR_WEIGHT[sp] / 1000.0
        md = max(dbi_flow.get(sp, 0.0), 0.0) * MOLECULAR_WEIGHT[sp] / 1000.0
        if mm > 0.5 or md > 0.5:
            print(f"  {sp:4s} {mm - md:+8.1f}  (model {mm:.1f}, DBI {md:.1f})")

    bio_c = biomass_elem["C"] * 12.011 / 1000.0
    gas_c = elemental_totals_from_species(final, ["C"])["C"] * 12.011 / 1000.0
    print("\n碳去向:")
    print(f"  biomass C in:     {bio_c:.1f} kg/h")
    print(f"  gas phase C:      {gas_c:.1f} kg/h ({100 * gas_c / bio_c:.1f}% of biomass C)")
    print(f"  tar outlet:       {tar_allocation_mass_kg_h(pyro.tar_allocation):.2f} kg/h (DBI 18.49)")
    print(f"  char → POX:       {routing.char_to_pox_kg_h:.1f} kg/h")
    print(f"  reactive char→Gibbs: {routing.reactive_char_mol_h * 12.011 / 1000:.1f} kg C/h")

    print("\n阶段质量变化:")
    for label, flow in [("Gibbs pre-TA", post_gibbs), ("TA pre-trace", post_ta)]:
        m = species_flow_mass_kg_h(flow)
        print(f"  {label}: {m:.1f} kg/h ({m - base_mass:+.1f} vs final)")

    print("\n灵敏度 (气相 kg/h vs 当前 {:.1f}):".format(base_mass))
    tar_plus = parse_tar_yield_mass_kg_h(feed.get("Biomass", 0.0), sample, "0.0105 * C_dry")
    pyro2 = allocate_pyrolysis_products_elemental(
        nC=vm_elem["C"],
        nH=vm_elem["H"],
        nO=vm_elem["O"],
        nN=vm_elem["N"],
        nS=vm_elem["S"],
        tar_carbon_frac=0.0,
        target_tar_hc_ratio=float(chem.get("Tar target H/C", 1.2)),
        tar_fuel_type="biomass",
        include_tar_internal=False,
        scheme=chem.get("Pyrolysis Scheme", "coal").strip().lower(),
        tar_outlet_mass_kg_h=tar_plus,
        nh3_frac_of_n=0.5,
        s_release_frac=0.5,
        h2s_split=0.9,
    )
    inci2 = dict(inci_elem)
    inci2["C"] = (
        elemental_totals_from_species(pyro2.volatile_species_mol_h, ["C"])["C"]
        + routing.reactive_char_mol_h
        + _kg_to_mol_h(co2_kg, 44.009)
    )
    inci2["H"] = elemental_totals_from_species(pyro2.volatile_species_mol_h, ["H"])["H"] + inci_ext["H"]
    inci2["O"] = elemental_totals_from_species(pyro2.volatile_species_mol_h, ["O"])["O"] + inci_ext["O"]
    g2 = solve_gibbs_major(inci2, MAJOR_SPECIES, t_k, p_bar)
    f2 = _apply_restricted_equilibrium_ta(
        dict(g2.species_flow_mol_h),
        t_gibbs_k=t_k,
        p_bar=p_bar,
        dt_wgs_c=100.0,
        dt_meth_c=425.0,
        eta_wgs=0.85,
        eta_meth=0.70,
        dt_ox_co_c=0.0,
        dt_ox_h2_c=0.0,
        dt_ox_ch4_c=0.0,
    )
    f2, m2 = _allocate_trace_species_from_biomass(
        f2,
        biomass_s_mol_h=biomass_elem["S"],
        biomass_n_mol_h=biomass_elem["N"],
        biomass_cl_mol_h=biomass_elem.get("Cl", 0.0),
        feed_n2_mol_h=n2,
        feed_ar_mol_h=ar,
        h2s_split=0.9,
        nh3_frac_of_biomass_n=0.5,
        s_release_frac=0.5,
    )
    m_tar = species_flow_mass_kg_h({**f2, **m2})
    print(f"  Tar 0.0105×C_dry ({tar_plus:.2f} kg/h): {m_tar:.1f} ({m_tar - base_mass:+.1f})")

    f3 = dict(final)
    f3["N2"] = dbi_flow["N2"]
    m_n2 = species_flow_mass_kg_h(f3)
    print(f"  补齐 N2 至 DBI 2%: {m_n2:.1f} ({m_n2 - base_mass:+.1f})")

    f4 = {k: model_mol * dbi_wet.get(k, 0.0) for k in INCI_WET_SPECIES}
    m_comp = species_flow_mass_kg_h(f4)
    print(f"  保持模型 mol、换 DBI 组成: {m_comp:.1f} ({m_comp - base_mass:+.1f})")

    f5 = {k: v * dbi_mol / model_mol for k, v in final.items()}
    m_scale = species_flow_mass_kg_h(f5)
    print(f"  保持模型组成、×DBI 总 mol: {m_scale:.1f} ({m_scale - dbi_gas:+.1f} vs DBI)")

    print(f"\nGibbs 进料元素 (mol/h): C={inci_elem['C']:,.0f} H={inci_elem['H']:,.0f} O={inci_elem['O']:,.0f}")
    if audit and audit.h2o_budget:
        print("\nH2O 阶梯 (mol/h):")
        for row in audit.h2o_budget:
            print(f"  {row.step}: {row.h2o_mol_h:.0f}")


if __name__ == "__main__":
    main()
