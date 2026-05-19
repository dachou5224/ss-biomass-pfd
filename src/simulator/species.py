from __future__ import annotations

from typing import Dict, Iterable

from .parameters import (
    ATOM_COUNT,
    ATOMIC_WEIGHT,
    INCI_DRY_SPECIES,
    INCI_MAJOR_KEYS,
    INCI_UNMODELLED_WET_SPECIES,
    INCI_WET_SPECIES,
    MAJOR_SPECIES,
    MINOR_SPECIES,
    MOLECULAR_WEIGHT,
)


def elemental_totals_from_species(flow_mol_h: Dict[str, float], elements: Iterable[str]) -> Dict[str, float]:
    totals = {el: 0.0 for el in elements}
    for sp, mol in flow_mol_h.items():
        if mol <= 0.0:
            continue
        for el in elements:
            totals[el] += mol * ATOM_COUNT.get(sp, {}).get(el, 0)
    return totals


def species_flow_mass_kg_h(flow_mol_h: Dict[str, float]) -> float:
    """物种摩尔流量 → 总质量流量 (kg/h)。未登记分子量的物种忽略。"""
    return sum(
        max(mol, 0.0) * MOLECULAR_WEIGHT[sp] / 1000.0
        for sp, mol in flow_mol_h.items()
        if sp in MOLECULAR_WEIGHT
    )
