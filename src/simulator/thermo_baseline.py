from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np

from .parameters import R_CONST, SHOMATE_DB, SOLID_CARBON_THERMO, THERMO_BASELINE_VERSION


def _get_coeffs(species: str, t_k: float) -> Sequence[float]:
    if species not in SHOMATE_DB:
        raise ValueError(f"Species '{species}' not found in SHOMATE_DB")
    row = SHOMATE_DB[species]
    if t_k < row["T_min"] or t_k > row["T_max"]:
        raise ValueError(f"Temperature {t_k:.2f} K out of valid range [{row['T_min']}, {row['T_max']}] for {species}")
    return row["Low"] if t_k < row["T_cut"] else row["High"]


def _solid_carbon_approx(prop_type: str, t_k: float) -> float:
    cp_c = SOLID_CARBON_THERMO["cp"]
    s_ref = SOLID_CARBON_THERMO["s_ref"]
    t_ref = SOLID_CARBON_THERMO["reference_t_k"]
    if prop_type == "Cp":
        return cp_c
    if prop_type == "H":
        return cp_c * (t_k - t_ref)
    if prop_type == "S":
        return s_ref + cp_c * np.log(t_k / t_ref)
    raise ValueError(f"Unsupported property type '{prop_type}'")


def shomate_property(species: str, t_k: float, prop_type: str) -> float:
    if t_k <= 0.0:
        raise ValueError(f"Temperature must be positive, got {t_k}")
    if species == "C":
        return _solid_carbon_approx(prop_type, t_k)
    coeffs = _get_coeffs(species, t_k)
    t = t_k / 1000.0
    a, b, c, d, e, f, g, _h_const = coeffs
    if prop_type == "Cp":
        return a + b * t + c * t**2 + d * t**3 + e / (t**2)
    if prop_type == "H":
        h_kj_mol = a * t + b * t**2 / 2 + c * t**3 / 3 + d * t**4 / 4 - e / t + f
        return h_kj_mol * 1000.0
    if prop_type == "S":
        return a * np.log(t) + b * t + c * t**2 / 2 + d * t**3 / 3 - e / (2 * t**2) + g
    raise ValueError(f"Unsupported property type '{prop_type}'")


def get_enthalpy_molar(species: str, t_k: float) -> float:
    return shomate_property(species, t_k, "H")


def get_entropy_molar(species: str, t_k: float) -> float:
    return shomate_property(species, t_k, "S")


def get_gibbs_free_energy(species: str, t_k: float) -> float:
    return get_enthalpy_molar(species, t_k) - t_k * get_entropy_molar(species, t_k)


def get_thermo_reference_rows() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for sp, row in SHOMATE_DB.items():
        rows.append(
            {
                "Species": sp,
                "Model": "Shomate",
                "T_range_K": f"{row['T_min']:.0f}-{row['T_max']:.0f}",
                "T_cut_K": f"{row['T_cut']:.0f}",
                "Source": "gasifier-model/src/gasifier/thermo_data.py",
                "BaselineVersion": THERMO_BASELINE_VERSION,
            }
        )
    rows.append(
        {
            "Species": "C",
            "Model": "Approximate solid carbon Cp/S/H",
            "T_range_K": ">=298",
            "T_cut_K": "-",
            "Source": "gasifier-model/src/gasifier/thermo_data.py (engineering approximation)",
            "BaselineVersion": THERMO_BASELINE_VERSION,
        }
    )
    return rows
