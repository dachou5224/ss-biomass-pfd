from __future__ import annotations

from typing import Dict, List

import pandas as pd

from .thermo_baseline import THERMO_BASELINE_VERSION, get_thermo_reference_rows


THERMO_METHODS = [
    {"Category": "Gas EOS", "Method": "RK-Soave", "Enabled": True, "Used By": "INCI/SLAG/RGPOX RGibbs"},
    {"Category": "Free Water", "Method": "IAPWS-95", "Enabled": True, "Used By": "H2O property"},
    {"Category": "NC Enthalpy", "Method": "HCOALGEN", "Enabled": True, "Used By": "Biomass/Tar/Ash"},
    {"Category": "NC Density", "Method": "DCOALIGT", "Enabled": True, "Used By": "Biomass/Tar/Ash"},
]


COMPONENT_PARAMETER_ROWS = [
    {"Component": "CO/H2/CO2/CH4/H2O/N2/O2/Ar", "Type": "Conventional", "Source": "Shomate (gasifier-model thermo_data aligned)", "Thermo Hook": "get_gibbs_free_energy(species, T)"},
    {"Component": "H2S/COS", "Type": "Conventional(minor)", "Source": "Shomate low-T extension (gasifier-model)", "Thermo Hook": "get_gibbs_free_energy('H2S'|'COS', T)"},
    {"Component": "Char(C)", "Type": "Pseudo conventional solid", "Source": "Approximate Cp/S/H model (gasifier-model)", "Thermo Hook": "get_gibbs_free_energy('C', T)"},
    {"Component": "Biomass", "Type": "Nonconventional", "Source": "Ultimate/proximate analysis", "Thermo Hook": "get_nc_enthalpy('Biomass', T)"},
    {"Component": "Tar", "Type": "Nonconventional", "Source": "Empirical formula CHO0.082N0.01", "Thermo Hook": "get_nc_enthalpy('Tar', T)"},
    {"Component": "Ash", "Type": "Nonconventional", "Source": "Inert assumption", "Thermo Hook": "get_nc_density('Ash', T)"},
]


def get_methods_df() -> pd.DataFrame:
    return pd.DataFrame(THERMO_METHODS)


def get_component_params_df() -> pd.DataFrame:
    return pd.DataFrame(COMPONENT_PARAMETER_ROWS)


def get_thermo_baseline_df() -> pd.DataFrame:
    return pd.DataFrame(get_thermo_reference_rows())


def build_thermo_call_trace() -> List[Dict[str, str]]:
    return [
        {
            "Module": "DECOMP (RYield)",
            "Thermo Call": "biomass_to_elemental_moles + allocate_tar_moles_from_carbon",
            "Method": "HCOALGEN concept + Hamel-style fuel-aware tar surrogate allocator (bfb-gasifier aligned)",
            "Purpose": "Map biomass feed to elemental ledger and tar pseudo species",
        },
        {
            "Module": "INCI (RGibbs)",
            "Thermo Call": "get_gibbs_free_energy(species, T)",
            "Method": f"Shomate baseline ({THERMO_BASELINE_VERSION}) + constrained Gibbs",
            "Purpose": "Minimize Gibbs free energy under element balance constraints (T_gibbs decoupled from fixed T_out)",
        },
        {
            "Module": "INCI Equation Basis",
            "Thermo Call": "Elemental + Gibbs formulation (no fixed extents)",
            "Method": "Drying/Pyrolysis release + equilibrium reaction-set basis",
            "Purpose": "C+H2O<->CO+H2; C+CO2<->2CO; CO+H2O<->CO2+H2; CO+3H2<->CH4+H2O; C+O2->CO2; CO+0.5O2->CO2; H2+0.5O2->H2O; CH4+2O2->CO2+2H2O",
        },
        {
            "Module": "INCI Oxidation Stage",
            "Thermo Call": "oxidation temperature-approach extents via K(T+ΔT)",
            "Method": "Post-equilibrium bounded oxidation tuning (CO/H2/CH4 oxidation)",
            "Purpose": "Adjust oxidation-side equilibrium tendency without O2 stream splitting",
        },
        {
            "Module": "INCI Temperature Approach",
            "Thermo Call": "post-equilibrium extent tuning via K(T+ΔT) for WGS/Meth/Oxidation",
            "Method": "Temperature approach on selected reactions (WGS/Meth/Ox-CO/Ox-H2/Ox-CH4)",
            "Purpose": "Provides bounded calibration knobs while keeping Gibbs baseline",
        },
        {
            "Module": "SLAGTMZ (RGibbs)",
            "Thermo Call": "get_gibbs_free_energy(C/O/H species, T)",
            "Method": f"Shomate baseline ({THERMO_BASELINE_VERSION}) + constrained Gibbs",
            "Purpose": "Bottom slag char oxidation equilibrium",
        },
        {
            "Module": "TARCOMP (RYield)",
            "Thermo Call": "decompose_tar_formula(formula, yield_factor)",
            "Method": "Empirical tar cracking assumption",
            "Purpose": "Convert tar to C/H2/N2/O2 pseudo-products",
        },
        {
            "Module": "RGPOX (RGibbs)",
            "Thermo Call": "get_gibbs_free_energy + CH4 target clamp + minor sulfur split",
            "Method": f"Shomate baseline ({THERMO_BASELINE_VERSION}) + constrained Gibbs + empirical minor allocation",
            "Purpose": "High-temperature partial oxidation equilibrium",
        },
    ]


def summarize_method_signature(method_df: pd.DataFrame) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for _, row in method_df.iterrows():
        out[str(row["Category"])] = f"{row['Method']} (enabled={bool(row['Enabled'])})"
    return out
