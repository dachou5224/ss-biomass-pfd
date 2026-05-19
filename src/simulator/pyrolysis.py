from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np

from .tar_models import TarAllocation, allocate_tar_from_mass_kg_h, allocate_tar_moles_from_carbon


@dataclass(frozen=True)
class PyrolysisSplit:
    volatile_species_mol_h: Dict[str, float]
    char_carbon_mol_h: float
    tar_allocation: TarAllocation


def allocate_pyrolysis_products_elemental(
    *,
    nC: float,
    nH: float,
    nO: float,
    nN: float,
    nS: float,
    tar_carbon_frac: float,
    target_tar_hc_ratio: float,
    tar_fuel_type: str,
    include_tar_internal: bool,
    scheme: str = "hamel",
    tar_outlet_mass_kg_h: float = 0.0,
    nh3_frac_of_n: float = 0.016,
    s_release_frac: float = 0.45,
    h2s_split: float = 0.961,
) -> PyrolysisSplit:
    """
    Elemental pyrolysis allocation (Hamel-style) for INCI front-end decomposition.
    """
    scheme_key = (scheme or "hamel").strip().lower()

    def _assign_n_s(out: Dict[str, float], n_n: float, n_s: float) -> None:
        n_nh3, n_n2 = _split_n(n_n, nh3_frac_of_n)
        n_h2s, _ = _split_s(n_s, h2s_split, s_release_frac)
        out["NH3"] = n_nh3
        out["N2"] = n_n2
        out["H2S"] = n_h2s

    def _split_n(n_mol_h: float, nh3_frac: float) -> Tuple[float, float]:
        frac = float(np.clip(nh3_frac, 0.0, 1.0))
        n_nh3 = max(n_mol_h, 0.0) * frac
        n_n2 = max(n_mol_h - n_nh3, 0.0) / 2.0
        return n_nh3, n_n2

    def _split_s(s_mol_h: float, h2s_frac: float, release_frac: float) -> Tuple[float, float]:
        s_gas = max(s_mol_h, 0.0) * float(np.clip(release_frac, 0.0, 1.0))
        frac = float(np.clip(h2s_frac, 0.0, 1.0))
        n_h2s = s_gas * frac
        return n_h2s, s_gas - n_h2s

    out = {
        "CO": 0.0,
        "CO2": 0.0,
        "CH4": 0.0,
        "H2O": 0.0,
        "H2": 0.0,
        "N2": 0.0,
        "NH3": 0.0,
        "H2S": 0.0,
    }
    _assign_n_s(out, float(nN), float(nS))

    if scheme_key in ("no-tar-1d", "no_tar_1d", "kinetics_no_tar"):
        c_total = max(float(nC), 0.0)
        o_total = max(float(nO), 0.0)
        # gasifier-1d-kinetic reference: no tar branch and nitrogen to N2.
        out["N2"] = max(float(nN), 0.0) / 2.0
        out["NH3"] = 0.0

        h_effective = max(float(nH) - 2.0 * out["H2S"], 0.0)
        nco = min(c_total, o_total)
        c_left = c_total - nco
        o_left = o_total - nco

        nch4 = min(c_left, h_effective / 4.0)
        c_left -= nch4
        h_effective -= 4.0 * nch4

        # no-tar reference keeps CO2 minimal in pyrolysis.
        nco2 = 0.0
        nh2o = min(o_left, h_effective / 2.0)
        o_left -= nh2o
        h_effective -= 2.0 * nh2o
        nh2 = max(h_effective, 0.0) / 2.0
        no2 = max(o_left, 0.0) / 2.0

        out["CO"] = max(nco, 0.0)
        out["CO2"] = max(nco2, 0.0)
        out["CH4"] = max(nch4, 0.0)
        out["H2O"] = max(nh2o, 0.0)
        out["H2"] = max(nh2, 0.0)
        out["O2"] = max(no2, 0.0)
        tar_allocation = allocate_tar_moles_from_carbon(
            0.0,
            fuel_type=tar_fuel_type if tar_fuel_type in ("coal", "biomass") else "biomass",
            target_hc_ratio=target_tar_hc_ratio,
        )
        return PyrolysisSplit(
            volatile_species_mol_h=out,
            char_carbon_mol_h=max(c_left, 0.0),
            tar_allocation=tar_allocation,
        )

    # N/S first to minor species, then allocate remaining H into main volatiles.
    h_effective = max(float(nH) - 3.0 * out["NH3"] - 2.0 * out["H2S"], 0.0)
    c_total = max(float(nC), 0.0)
    o_total = max(float(nO), 0.0)

    fuel = tar_fuel_type if tar_fuel_type in ("coal", "biomass") else "biomass"
    if tar_outlet_mass_kg_h > 1e-12:
        tar_allocation = allocate_tar_from_mass_kg_h(
            tar_outlet_mass_kg_h,
            fuel_type=fuel,
            target_hc_ratio=target_tar_hc_ratio,
        )
    else:
        tar_frac = float(np.clip(tar_carbon_frac if include_tar_internal else 0.0, 0.0, 0.9))
        tar_allocation = allocate_tar_moles_from_carbon(
            tar_frac * c_total,
            fuel_type=fuel,
            target_hc_ratio=target_tar_hc_ratio,
        )

    c_to_tar = tar_allocation.carbon_mol_h
    h_to_tar = tar_allocation.hydrogen_mol_h

    c_left = max(c_total - c_to_tar, 0.0)
    h_left = max(h_effective - h_to_tar, 0.0)
    o_left = o_total

    # Priority: CO, CH4, CO2, H2O, H2.
    nco = min(c_left, o_left)
    c_left -= nco
    o_left -= nco

    nch4 = min(c_left, h_left / 4.0)
    c_left -= nch4
    h_left -= 4.0 * nch4

    nco2 = min(c_left, o_left / 2.0)
    c_left -= nco2
    o_left -= 2.0 * nco2

    nco_fb = min(c_left, o_left)
    nco += nco_fb
    c_left -= nco_fb
    o_left -= nco_fb

    nh2o = min(h_left / 2.0, o_left)
    h_left -= 2.0 * nh2o
    o_left -= nh2o

    nh2 = max(h_left, 0.0) / 2.0

    out["CO"] = max(nco, 0.0)
    out["CO2"] = max(nco2, 0.0)
    out["CH4"] = max(nch4, 0.0)
    out["H2O"] = max(nh2o, 0.0)
    out["H2"] = max(nh2, 0.0)

    return PyrolysisSplit(
        volatile_species_mol_h=out,
        char_carbon_mol_h=max(c_left, 0.0),
        tar_allocation=tar_allocation,
    )
