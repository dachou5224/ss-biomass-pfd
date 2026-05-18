from __future__ import annotations

from typing import Dict, Iterable


ATOMIC_WEIGHT = {
    "C": 12.011,
    "H": 1.008,
    "O": 15.999,
    "N": 14.007,
    "S": 32.06,
    "Ar": 39.948,
}

MOLECULAR_WEIGHT = {
    "CO": 28.010,
    "H2": 2.016,
    "CO2": 44.009,
    "CH4": 16.043,
    "H2O": 18.015,
    "O2": 31.998,
    "N2": 28.014,
    "Ar": 39.948,
    "H2S": 34.081,
    "COS": 60.075,
    "NH3": 17.031,
}

ATOM_COUNT = {
    "CO": {"C": 1, "O": 1},
    "H2": {"H": 2},
    "CO2": {"C": 1, "O": 2},
    "CH4": {"C": 1, "H": 4},
    "H2O": {"H": 2, "O": 1},
    "O2": {"O": 2},
    "N2": {"N": 2},
    "Ar": {"Ar": 1},
    "H2S": {"H": 2, "S": 1},
    "COS": {"C": 1, "O": 1, "S": 1},
    "NH3": {"N": 1, "H": 3},
}

MAJOR_SPECIES = ("CO", "H2", "CO2", "CH4", "H2O", "O2", "N2", "Ar")
MINOR_SPECIES = ("H2S", "COS", "NH3")


def elemental_totals_from_species(flow_mol_h: Dict[str, float], elements: Iterable[str]) -> Dict[str, float]:
    totals = {el: 0.0 for el in elements}
    for sp, mol in flow_mol_h.items():
        if mol <= 0.0:
            continue
        for el in elements:
            totals[el] += mol * ATOM_COUNT.get(sp, {}).get(el, 0)
    return totals

