from __future__ import annotations

from typing import Dict, List

import pandas as pd


THERMO_METHODS = [
    {"Category": "Gas EOS", "Method": "RK-Soave", "Enabled": True, "Used By": "INCI/SLAG/RGPOX RGibbs"},
    {"Category": "Free Water", "Method": "IAPWS-95", "Enabled": True, "Used By": "H2O property"},
    {"Category": "NC Enthalpy", "Method": "HCOALGEN", "Enabled": True, "Used By": "Biomass/Tar/Ash"},
    {"Category": "NC Density", "Method": "DCOALIGT", "Enabled": True, "Used By": "Biomass/Tar/Ash"},
]


COMPONENT_PARAMETER_ROWS = [
    {"Component": "CO", "Type": "Conventional", "Source": "Shomate/NIST style coefficients", "Thermo Hook": "get_standard_gibbs('CO', T)"},
    {"Component": "H2", "Type": "Conventional", "Source": "Shomate/NIST style coefficients", "Thermo Hook": "get_standard_gibbs('H2', T)"},
    {"Component": "CO2", "Type": "Conventional", "Source": "Shomate/NIST style coefficients", "Thermo Hook": "get_standard_gibbs('CO2', T)"},
    {"Component": "CH4", "Type": "Conventional", "Source": "Shomate/NIST style coefficients", "Thermo Hook": "get_standard_gibbs('CH4', T)"},
    {"Component": "H2O", "Type": "Conventional", "Source": "IAPWS-95 / vapor branch", "Thermo Hook": "get_water_props(T, P)"},
    {"Component": "O2,N2,Ar", "Type": "Conventional", "Source": "EOS + ideal mixing", "Thermo Hook": "get_mixture_mu(...)"},
    {"Component": "Biomass", "Type": "Nonconventional", "Source": "Ultimate/proximate analysis", "Thermo Hook": "get_nc_enthalpy('Biomass', T)"},
    {"Component": "Tar", "Type": "Nonconventional", "Source": "Empirical formula CHO0.082N0.01", "Thermo Hook": "get_nc_enthalpy('Tar', T)"},
    {"Component": "Ash", "Type": "Nonconventional", "Source": "Inert assumption", "Thermo Hook": "get_nc_density('Ash', T)"},
]


def get_methods_df() -> pd.DataFrame:
    return pd.DataFrame(THERMO_METHODS)


def get_component_params_df() -> pd.DataFrame:
    return pd.DataFrame(COMPONENT_PARAMETER_ROWS)


def build_thermo_call_trace() -> List[Dict[str, str]]:
    return [
        {
            "Module": "DECOMP (RYield)",
            "Thermo Call": "biomass_to_elemental_moles + allocate_tar_moles_from_carbon",
            "Method": "HCOALGEN concept + Hamel-style tar surrogate allocator",
            "Purpose": "Map biomass feed to elemental ledger and tar pseudo species",
        },
        {
            "Module": "INCI (RGibbs)",
            "Thermo Call": "get_standard_gibbs(species, T), get_mixture_mu(T, P, y)",
            "Method": "RK-Soave + constrained Gibbs",
            "Purpose": "Minimize Gibbs free energy under element balance constraints",
        },
        {
            "Module": "SLAGTMZ (RGibbs)",
            "Thermo Call": "get_standard_gibbs(C/O/H species, T)",
            "Method": "RK-Soave + constrained Gibbs",
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
            "Thermo Call": "get_standard_gibbs + CH4 target clamp + minor sulfur split",
            "Method": "RK-Soave + constrained Gibbs + empirical minor allocation",
            "Purpose": "High-temperature partial oxidation equilibrium",
        },
    ]


def summarize_method_signature(method_df: pd.DataFrame) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for _, row in method_df.iterrows():
        out[str(row["Category"])] = f"{row['Method']} (enabled={bool(row['Enabled'])})"
    return out
