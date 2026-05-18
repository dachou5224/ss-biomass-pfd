from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .contracts import ElementBalance, SimulationResult, UnitResult
from .data import REFERENCE_CASES
from .elemental import BIOMASS_SAMPLES, biomass_to_elemental_moles
from .gibbs import solve_gibbs_major
from .species import MAJOR_SPECIES, MINOR_SPECIES, elemental_totals_from_species
from .tar_models import allocate_tar_moles_from_carbon
from .thermo import build_thermo_call_trace


def _feed_map(feed_df: pd.DataFrame) -> Dict[str, float]:
    values: Dict[str, float] = {}
    for _, row in feed_df.iterrows():
        values[str(row["Stream"])] = float(row["MassFlow_kg_h"])
    return values


def _spec_map(specs_df: pd.DataFrame) -> Dict[str, float]:
    return {str(r["Parameter"]): float(r["Value"]) for _, r in specs_df.iterrows()}


def _chem_map(chem_df: pd.DataFrame) -> Dict[str, str]:
    return {str(r["Field"]): str(r["Value"]) for _, r in chem_df.iterrows()}


def _kg_to_mol_h(mass_kg_h: float, mw_kg_kmol: float) -> float:
    return max(mass_kg_h, 0.0) / mw_kg_kmol * 1000.0


def _build_elemental_inlet(feed_map: Dict[str, float], sample_id: str, o2_purity_vol: float = 95.0) -> Tuple[Dict[str, float], float]:
    bio = biomass_to_elemental_moles(sample_id, feed_map.get("Biomass", 0.0))
    inlet = {k: bio.get(k, 0.0) for k in ("C", "H", "O", "N", "S", "Ar")}
    ash_kg_h = bio["Ash_kg_h"]

    # CIN as solid carbon carrier
    inlet["C"] += _kg_to_mol_h(feed_map.get("CIN", 0.0), 12.011)

    # Main gas feeds
    inlet["O"] += 2.0 * _kg_to_mol_h(feed_map.get("O2IN", 0.0), 31.998)
    inlet["H"] += 2.0 * _kg_to_mol_h(feed_map.get("H2OIN", 0.0), 18.015)
    inlet["O"] += 1.0 * _kg_to_mol_h(feed_map.get("H2OIN", 0.0), 18.015)
    inlet["N"] += 2.0 * _kg_to_mol_h(feed_map.get("N2IN", 0.0), 28.014)
    inlet["C"] += 1.0 * _kg_to_mol_h(feed_map.get("CO2IN", 0.0), 44.009)
    inlet["O"] += 2.0 * _kg_to_mol_h(feed_map.get("CO2IN", 0.0), 44.009)
    inlet["O"] += 2.0 * _kg_to_mol_h(feed_map.get("POSTO2", 0.0), 31.998)
    inlet["H"] += 2.0 * _kg_to_mol_h(feed_map.get("POSTH2O", 0.0), 18.015)
    inlet["O"] += 1.0 * _kg_to_mol_h(feed_map.get("POSTH2O", 0.0), 18.015)
    inlet["C"] += 1.0 * _kg_to_mol_h(feed_map.get("POSTCO2", 0.0), 44.009)
    inlet["O"] += 2.0 * _kg_to_mol_h(feed_map.get("POSTCO2", 0.0), 44.009)
    inlet["O"] += 2.0 * _kg_to_mol_h(feed_map.get("O2POX", 0.0), 31.998)

    # Optional O2 impurity split assumption
    o2_total_mol = _kg_to_mol_h(feed_map.get("O2IN", 0.0), 31.998) + _kg_to_mol_h(feed_map.get("POSTO2", 0.0), 31.998) + _kg_to_mol_h(feed_map.get("O2POX", 0.0), 31.998)
    o2_frac = np.clip(o2_purity_vol / 100.0, 0.5, 1.0)
    impurity = o2_total_mol * (1.0 / o2_frac - 1.0)
    n2_imp = impurity * (1.75 / 5.0)
    ar_imp = impurity * (3.25 / 5.0)
    inlet["N"] += 2.0 * n2_imp
    inlet["Ar"] += ar_imp

    return inlet, ash_kg_h


def _apply_tar_allocator(inlet: Dict[str, float], tar_yield_factor: float, tar_hc_target: float) -> Tuple[Dict[str, float], Dict[str, float]]:
    c_total = inlet["C"]
    c_to_tar = np.clip(c_total * tar_yield_factor, 0.0, 0.2 * c_total)
    tar_moles = allocate_tar_moles_from_carbon(c_to_tar, target_hc_ratio=tar_hc_target)

    # Equivalent elemental consumption by tar pseudo species.
    c_in_tar = 10.0 * tar_moles["TAR1_C10H8"] + 16.0 * tar_moles["TAR2_C16H34"]
    h_in_tar = 8.0 * tar_moles["TAR1_C10H8"] + 34.0 * tar_moles["TAR2_C16H34"]
    inlet_after = dict(inlet)
    inlet_after["C"] = max(inlet_after["C"] - c_in_tar, 0.0)
    inlet_after["H"] = max(inlet_after["H"] - h_in_tar, 0.0)
    return inlet_after, tar_moles


def _add_minor_species(
    major: Dict[str, float],
    sulfur_mol_h: float,
    h2s_split: float,
    nh3_fraction_of_n: float = 0.02,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    flow = dict(major)
    sulfur_total = max(sulfur_mol_h, 0.0)
    n_h2s = sulfur_total * np.clip(h2s_split, 0.0, 1.0)
    n_cos = sulfur_total - n_h2s
    # Pull elemental donors from major pool with simple preserving transforms.
    flow["H2"] = max(flow.get("H2", 0.0) - n_h2s, 1e-9)
    flow["CO"] = max(flow.get("CO", 0.0) - n_cos, 1e-9)

    n_from_n2 = max(flow.get("N2", 0.0), 0.0) * np.clip(nh3_fraction_of_n, 0.0, 0.2)
    flow["N2"] = max(flow.get("N2", 0.0) - n_from_n2, 1e-9)
    n_nh3 = 2.0 * n_from_n2
    flow["H2"] = max(flow.get("H2", 0.0) - 1.5 * n_nh3, 1e-9)

    minor = {"H2S": n_h2s, "COS": n_cos, "NH3": n_nh3}
    return flow, minor


def _dry_vol_pct(flow_mol_h: Dict[str, float], keys: List[str]) -> Dict[str, float]:
    total = sum(max(flow_mol_h.get(k, 0.0), 0.0) for k in keys if k != "H2O")
    if total <= 0:
        return {k: 0.0 for k in keys}
    return {k: round(100.0 * max(flow_mol_h.get(k, 0.0), 0.0) / total, 3) for k in keys}


def _match_reference_case(feed_map: Dict[str, float], sample: str) -> str | None:
    for case_id, payload in REFERENCE_CASES.items():
        if payload["sample"] != sample:
            continue
        matched = True
        for stream, (mass, _, _) in payload["feeds"].items():
            if abs(feed_map.get(stream, -999999.0) - mass) > 1e-1:
                matched = False
                break
        if matched:
            return case_id
    return None


def _calc_rmsd_pct(pred: Dict[str, float], ref: Dict[str, float], keys: List[str]) -> float:
    if not keys:
        return 0.0
    arr = [pred.get(k, 0.0) - ref.get(k, 0.0) for k in keys]
    return float(np.sqrt(np.mean(np.square(arr))))


def run_fixed_temperature_simulation(
    feed_df: pd.DataFrame,
    specs_df: pd.DataFrame,
    chemistry_df: pd.DataFrame,
) -> SimulationResult:
    feed = _feed_map(feed_df)
    specs = _spec_map(specs_df)
    chem = _chem_map(chemistry_df)

    sample = chem.get("Sample", "8#")
    if sample not in BIOMASS_SAMPLES:
        sample = "8#"

    tar_factor_text = chem.get("Tar Yield Factor", "0.01")
    tar_yield_factor = 0.01
    if "0.01" not in tar_factor_text:
        try:
            tar_yield_factor = float(tar_factor_text)
        except ValueError:
            tar_yield_factor = 0.01

    h2s_split = float(chem.get("H2S/COS split to H2S", "0.8"))
    o2_purity = float(chem.get("O2 Purity vol%", "95.0"))
    tar_hc = float(chem.get("Tar target H/C", "1.2"))
    p_bar = float(specs.get("SYSTEM_P_BAR", 15.0))
    t_inci_k = float(specs.get("INCI_T_C", 900.0)) + 273.15
    t_slag_k = float(specs.get("SLAG_T_C", 800.0)) + 273.15
    t_pox_k = float(specs.get("RGPOX_T_C", 1400.0)) + 273.15
    inci_c_conv = np.clip(float(specs.get("INCI_C_CONV", 0.85)), 0.0, 1.0)
    pox_c_conv = np.clip(float(specs.get("RGPOX_C_CONV", 1.0)), 0.0, 1.0)
    ash_to_slag = np.clip(float(specs.get("ASH_TO_SLAG_FRAC", 0.60)), 0.0, 1.0)
    char_to_slag = np.clip(float(specs.get("CHAR_TO_SLAG_FRAC", 0.55)), 0.0, 1.0)

    inlet_elem, ash_kg_h = _build_elemental_inlet(feed, sample, o2_purity_vol=o2_purity)
    inlet_elem_for_inci, tar_moles = _apply_tar_allocator(inlet_elem, tar_yield_factor=tar_yield_factor, tar_hc_target=tar_hc)

    # INCI: convert only fraction of carbon into gas-phase Gibbs pool.
    inci_elem = dict(inlet_elem_for_inci)
    c_for_inci = inci_elem["C"] * inci_c_conv
    char_after_inci = max(inci_elem["C"] - c_for_inci, 0.0)
    inci_elem["C"] = c_for_inci
    inci_major = solve_gibbs_major(inci_elem, MAJOR_SPECIES, t_inci_k, p_bar)
    inci_major_flow = dict(inci_major.species_flow_mol_h)
    inci_minor = {sp: 0.0 for sp in MINOR_SPECIES}

    # SLAG section receives char fraction + post feeds.
    char_to_slag_mol = char_after_inci * char_to_slag
    char_to_pox_mol = char_after_inci - char_to_slag_mol
    slag_elem = {
        "C": char_to_slag_mol,
        "H": 2.0 * _kg_to_mol_h(feed.get("POSTH2O", 0.0), 18.015),
        "O": 2.0 * _kg_to_mol_h(feed.get("POSTO2", 0.0), 31.998)
        + _kg_to_mol_h(feed.get("POSTH2O", 0.0), 18.015)
        + 2.0 * _kg_to_mol_h(feed.get("POSTCO2", 0.0), 44.009),
        "N": 0.0,
        "Ar": 0.0,
    }
    # target residual carbon in solids around 10 wt% of (ash + carbon) by reducing reactive C feed.
    ash_slag_kg_h = ash_kg_h * ash_to_slag
    target_residual_c_kg_h = ash_slag_kg_h / 9.0
    target_residual_c_mol = _kg_to_mol_h(target_residual_c_kg_h, 12.011)
    slag_elem["C"] = max(slag_elem["C"] - target_residual_c_mol, 0.0)
    slag_major = solve_gibbs_major(slag_elem, MAJOR_SPECIES, t_slag_k, p_bar)

    # RGPOX: INCI gas + tar cracked carbon/hydrogen + char remainder + O2POX
    tar_crack = {
        "C": 10.0 * tar_moles["TAR1_C10H8"] + 16.0 * tar_moles["TAR2_C16H34"],
        "H": 8.0 * tar_moles["TAR1_C10H8"] + 34.0 * tar_moles["TAR2_C16H34"],
    }
    pox_elem = elemental_totals_from_species(inci_major_flow, ["C", "H", "O", "N", "Ar"])
    pox_elem["C"] += char_to_pox_mol * pox_c_conv + tar_crack["C"]
    pox_elem["H"] += tar_crack["H"]
    pox_elem["O"] += 2.0 * _kg_to_mol_h(feed.get("O2POX", 0.0), 31.998)
    pox_elem["S"] = inlet_elem["S"]

    pox_major = solve_gibbs_major(pox_elem, MAJOR_SPECIES, t_pox_k, p_bar)
    pox_major_flow, pox_minor = _add_minor_species(pox_major.species_flow_mol_h, sulfur_mol_h=pox_elem["S"], h2s_split=h2s_split)

    # CH4 empirical clamp by temperature.
    ch4_target_lookup = {
        1300.0: float(chem.get("RGPOX CH4 Target @1300C (%)", "0.55")),
        1400.0: float(chem.get("RGPOX CH4 Target @1400C (%)", "0.1")),
        1500.0: float(chem.get("RGPOX CH4 Target @1500C (%)", "0.05")),
    }
    t_c = float(specs.get("RGPOX_T_C", 1400.0))
    if t_c in ch4_target_lookup:
        dry_total = sum(pox_major_flow.get(s, 0.0) for s in MAJOR_SPECIES if s != "H2O")
        target_ch4 = dry_total * ch4_target_lookup[t_c] / 100.0
        delta = pox_major_flow.get("CH4", 0.0) - target_ch4
        if delta > 0.0:
            pox_major_flow["CH4"] = max(target_ch4, 1e-9)
            pox_major_flow["CO"] += delta
            pox_major_flow["H2"] += 3.0 * delta
            pox_major_flow["H2O"] = max(pox_major_flow.get("H2O", 0.0) - delta, 1e-9)

    inci_vol = _dry_vol_pct(inci_major_flow, ["CO", "H2", "CO2", "CH4"])
    pox_vol = _dry_vol_pct(pox_major_flow, ["CO", "H2", "CO2", "CH4"])
    inci_minor_vol = _dry_vol_pct({**inci_major_flow, **inci_minor}, list(MINOR_SPECIES))
    pox_minor_vol = _dry_vol_pct({**pox_major_flow, **pox_minor}, list(MINOR_SPECIES))

    # Mass proxies for reporting.
    inci_top_kg_h = (
        feed.get("Biomass", 0.0) * 0.92
        + feed.get("CIN", 0.0) * 0.35
        + feed.get("O2IN", 0.0)
        + feed.get("H2OIN", 0.0)
        + feed.get("N2IN", 0.0)
        + feed.get("CO2IN", 0.0)
    )
    inci_slag_kg_h = ash_kg_h * ash_to_slag + target_residual_c_kg_h
    pox_gas_kg_h = inci_top_kg_h + feed.get("O2POX", 0.0) + feed.get("POSTO2", 0.0) * 0.1
    pox_ash_kg_h = ash_kg_h * (1.0 - ash_to_slag) + 0.02 * feed.get("Biomass", 0.0)

    balance_in = dict(inlet_elem)
    out_species = dict(pox_major_flow)
    for sp, val in slag_major.species_flow_mol_h.items():
        out_species[sp] = out_species.get(sp, 0.0) + val
    out_species["H2S"] = pox_minor["H2S"]
    out_species["COS"] = pox_minor["COS"]
    out_species["NH3"] = pox_minor["NH3"]
    balance_out = elemental_totals_from_species(out_species, ["C", "H", "O", "N", "S", "Ar"])
    balance_out["C"] += target_residual_c_mol + char_to_pox_mol * (1.0 - pox_c_conv)
    balance_rows = [
        ElementBalance(el, balance_in.get(el, 0.0), balance_out.get(el, 0.0))
        for el in ["C", "H", "O", "N", "S", "Ar"]
    ]

    unit_trace: List[UnitResult] = [
        UnitResult("Mix1", "ok", "Feed gas merged for INCI", feed.get("O2IN", 0.0) + feed.get("H2OIN", 0.0) + feed.get("N2IN", 0.0) + feed.get("CO2IN", 0.0), feed.get("O2IN", 0.0) + feed.get("H2OIN", 0.0) + feed.get("N2IN", 0.0) + feed.get("CO2IN", 0.0)),
        UnitResult("DECOMP", "ok", "Biomass normalized to elemental feed + tar surrogates", feed.get("Biomass", 0.0), feed.get("Biomass", 0.0)),
        UnitResult("INCI(RGibbs)", "ok" if inci_major.success else "warn", inci_major.message, feed.get("Biomass", 0.0) + feed.get("CIN", 0.0), inci_top_kg_h + inci_slag_kg_h),
        UnitResult("SEP2", "ok", "Gas/tar/ash/char split performed", inci_top_kg_h + inci_slag_kg_h, inci_top_kg_h + inci_slag_kg_h),
        UnitResult("SLAGTMZ(RGibbs)", "ok" if slag_major.success else "warn", slag_major.message, feed.get("POSTO2", 0.0) + feed.get("POSTH2O", 0.0) + feed.get("POSTCO2", 0.0) + inci_slag_kg_h, inci_slag_kg_h),
        UnitResult("SEP3", "ok", "Slag gas-solid split applied", inci_slag_kg_h, inci_slag_kg_h),
        UnitResult("TARCOMP", "ok", "Tar cracked with Hamel-style surrogate split", feed.get("Biomass", 0.0) * tar_yield_factor, feed.get("Biomass", 0.0) * tar_yield_factor),
        UnitResult("RGPOX(RGibbs)", "ok" if pox_major.success else "warn", pox_major.message, inci_top_kg_h + feed.get("O2POX", 0.0), pox_gas_kg_h + pox_ash_kg_h),
    ]

    matched_case = _match_reference_case(feed, sample)
    rmsd_inci = None
    rmsd_pox = None
    if matched_case:
        expected = REFERENCE_CASES[matched_case]["expected"]
        rmsd_inci = _calc_rmsd_pct(inci_vol, expected["inci_comp"], ["CO", "H2", "CO2", "CH4"])
        rmsd_pox = _calc_rmsd_pct(pox_vol, expected["pox_comp"], ["CO", "H2", "CO2", "CH4"])

    return SimulationResult(
        inci_top_kg_h=round(inci_top_kg_h, 3),
        inci_slag_kg_h=round(inci_slag_kg_h, 3),
        pox_gas_kg_h=round(pox_gas_kg_h, 3),
        pox_ash_kg_h=round(pox_ash_kg_h, 3),
        inci_comp_dry_vol_pct=inci_vol,
        pox_comp_dry_vol_pct=pox_vol,
        inci_minor_vol_pct=inci_minor_vol,
        pox_minor_vol_pct=pox_minor_vol,
        rmsd_inci_pct=rmsd_inci,
        rmsd_pox_pct=rmsd_pox,
        unit_trace=unit_trace,
        thermo_trace=build_thermo_call_trace(),
        element_balance=balance_rows,
        matched_case=matched_case,
    )
