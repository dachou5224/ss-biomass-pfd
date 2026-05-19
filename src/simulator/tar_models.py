from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal, Tuple

import numpy as np

from .elemental import BIOMASS_SAMPLES
from .parameters import TAR_MODELS_CFG
from .species import ATOMIC_WEIGHT


TarSurrogate = str
TarFuelType = Literal["coal", "biomass"]
TarComponent = Literal["TAR1", "TAR2"]

TAR_SURROGATE_FORMULA: Dict[TarSurrogate, Tuple[int, int]] = {
    k: tuple(v) for k, v in TAR_MODELS_CFG["surrogate_formula"].items()
}

TAR_SURROGATE_HC_RATIO: Dict[TarSurrogate, float] = {
    name: h / c for name, (c, h) in TAR_SURROGATE_FORMULA.items()
}

TAR_TARGET_HC_RATIO: Dict[TarFuelType, float] = dict(TAR_MODELS_CFG["target_hc_ratio"])

TAR_SURROGATES_BY_FUEL: Dict[TarFuelType, Tuple[TarSurrogate, TarSurrogate]] = {
    k: tuple(v) for k, v in TAR_MODELS_CFG["surrogates_by_fuel"].items()
}

_TAR_BLEND_TOL = float(TAR_MODELS_CFG["blend_tol"])
_TAR_CARBON_FLOOR = float(TAR_MODELS_CFG["carbon_floor"])


@dataclass(frozen=True)
class TarAllocation:
    fuel_type: TarFuelType
    surrogate_map: Dict[TarComponent, TarSurrogate]
    tar_mol_h: Dict[TarComponent, float]
    carbon_mol_h: float
    hydrogen_mol_h: float


def calc_tar_surrogate_fractions(
    fuel_type: TarFuelType,
    target_hc_ratio: float | None = None,
) -> Dict[TarSurrogate, float]:
    """Fuel-aware Hamel-style two-surrogate linear blend."""
    surrogate_a, surrogate_b = TAR_SURROGATES_BY_FUEL[fuel_type]
    r_a = TAR_SURROGATE_HC_RATIO[surrogate_a]
    r_b = TAR_SURROGATE_HC_RATIO[surrogate_b]
    r_target = TAR_TARGET_HC_RATIO[fuel_type] if target_hc_ratio is None else target_hc_ratio
    if np.isclose(r_a, r_b):
        raise ValueError("Tar surrogate H/C ratios are degenerate.")
    x_a = (r_target - r_b) / (r_a - r_b)
    tol = _TAR_BLEND_TOL
    if x_a < -tol or x_a > 1.0 + tol:
        raise ValueError(
            f"Target H/C={r_target:.6f} out of representable range "
            f"[{min(r_a, r_b):.6f}, {max(r_a, r_b):.6f}]"
        )
    x_a = float(np.clip(x_a, 0.0, 1.0))
    fractions = {k: 0.0 for k in TAR_SURROGATE_FORMULA}
    fractions[surrogate_a] = x_a
    fractions[surrogate_b] = 1.0 - x_a
    return fractions


def get_tar_component_mapping(fuel_type: TarFuelType) -> Dict[TarComponent, TarSurrogate]:
    surrogate_a, surrogate_b = TAR_SURROGATES_BY_FUEL[fuel_type]
    return {"TAR1": surrogate_a, "TAR2": surrogate_b}


def allocate_tar_moles_from_carbon(
    carbon_mol_h: float,
    fuel_type: TarFuelType = "biomass",
    target_hc_ratio: float | None = None,
) -> TarAllocation:
    try:
        fractions = calc_tar_surrogate_fractions(fuel_type=fuel_type, target_hc_ratio=target_hc_ratio)
    except ValueError:
        fractions = calc_tar_surrogate_fractions(fuel_type=fuel_type, target_hc_ratio=None)
    mapping = get_tar_component_mapping(fuel_type)
    c_avg = 0.0
    for surrogate, frac in fractions.items():
        c_avg += frac * TAR_SURROGATE_FORMULA[surrogate][0]
    n_tar_total = max(carbon_mol_h, 0.0) / max(c_avg, _TAR_CARBON_FLOOR)
    tar_mol_h = {
        "TAR1": n_tar_total * fractions[mapping["TAR1"]],
        "TAR2": n_tar_total * fractions[mapping["TAR2"]],
    }
    carbon_to_tar = (
        TAR_SURROGATE_FORMULA[mapping["TAR1"]][0] * tar_mol_h["TAR1"]
        + TAR_SURROGATE_FORMULA[mapping["TAR2"]][0] * tar_mol_h["TAR2"]
    )
    hydrogen_to_tar = (
        TAR_SURROGATE_FORMULA[mapping["TAR1"]][1] * tar_mol_h["TAR1"]
        + TAR_SURROGATE_FORMULA[mapping["TAR2"]][1] * tar_mol_h["TAR2"]
    )
    return TarAllocation(
        fuel_type=fuel_type,
        surrogate_map=mapping,
        tar_mol_h=tar_mol_h,
        carbon_mol_h=carbon_to_tar,
        hydrogen_mol_h=hydrogen_to_tar,
    )


def tar_blend_molecular_weight(
    fuel_type: TarFuelType,
    target_hc_ratio: float | None = None,
) -> float:
    """Tar 双 surrogate 混合物的平均分子量 (kg/kmol)。"""
    fractions = calc_tar_surrogate_fractions(fuel_type=fuel_type, target_hc_ratio=target_hc_ratio)
    mw = 0.0
    for surrogate, frac in fractions.items():
        c_atoms, h_atoms = TAR_SURROGATE_FORMULA[surrogate]
        mw += frac * (c_atoms * ATOMIC_WEIGHT["C"] + h_atoms * ATOMIC_WEIGHT["H"])
    return mw


def tar_allocation_mass_kg_h(tar: TarAllocation) -> float:
    """由 surrogate 摩尔数直接求 tar 质量 (kg/h)。"""
    mass = 0.0
    for key, n_mol in tar.tar_mol_h.items():
        surrogate = tar.surrogate_map[key]
        c_atoms, h_atoms = TAR_SURROGATE_FORMULA[surrogate]
        mw = c_atoms * ATOMIC_WEIGHT["C"] + h_atoms * ATOMIC_WEIGHT["H"]
        mass += n_mol * mw / 1000.0
    return mass


def parse_tar_yield_mass_kg_h(biomass_kg_h: float, sample_id: str, yield_text: str) -> float:
    """
    解析 Tar Yield Factor 为 kg/h 质量。

    DBI 口径：'0.01 * C_dry' = 干基碳质量的 1%（Case-1 ≈ 18.49 kg/h）。
    """
    text = (yield_text or "").strip().lower()
    sample = BIOMASS_SAMPLES.get(sample_id, BIOMASS_SAMPLES["8#"])
    dry_kg_h = max(biomass_kg_h, 0.0) * (1.0 - sample.mad_pct / 100.0)
    if "c_dry" in text and "0.01" in text:
        c_dry_kg_h = dry_kg_h * sample.cd_pct_dry / 100.0
        return 0.01 * c_dry_kg_h
    try:
        return max(float(text), 0.0) * dry_kg_h
    except ValueError:
        return 0.0


def allocate_tar_from_mass_kg_h(
    tar_mass_kg_h: float,
    fuel_type: TarFuelType = "biomass",
    target_hc_ratio: float | None = None,
) -> TarAllocation:
    """由目标 tar 质量 (kg/h) 反推 surrogate 摩尔分配。"""
    if tar_mass_kg_h <= 1e-12:
        return allocate_tar_moles_from_carbon(0.0, fuel_type=fuel_type, target_hc_ratio=target_hc_ratio)
    fractions = calc_tar_surrogate_fractions(fuel_type=fuel_type, target_hc_ratio=target_hc_ratio)
    mapping = get_tar_component_mapping(fuel_type)
    mw = tar_blend_molecular_weight(fuel_type, target_hc_ratio)
    n_total = tar_mass_kg_h * 1000.0 / mw
    tar_mol_h = {
        "TAR1": n_total * fractions[mapping["TAR1"]],
        "TAR2": n_total * fractions[mapping["TAR2"]],
    }
    carbon_to_tar = (
        TAR_SURROGATE_FORMULA[mapping["TAR1"]][0] * tar_mol_h["TAR1"]
        + TAR_SURROGATE_FORMULA[mapping["TAR2"]][0] * tar_mol_h["TAR2"]
    )
    hydrogen_to_tar = (
        TAR_SURROGATE_FORMULA[mapping["TAR1"]][1] * tar_mol_h["TAR1"]
        + TAR_SURROGATE_FORMULA[mapping["TAR2"]][1] * tar_mol_h["TAR2"]
    )
    return TarAllocation(
        fuel_type=fuel_type,
        surrogate_map=mapping,
        tar_mol_h=tar_mol_h,
        carbon_mol_h=carbon_to_tar,
        hydrogen_mol_h=hydrogen_to_tar,
    )
