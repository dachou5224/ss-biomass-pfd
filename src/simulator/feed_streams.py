"""边界进料 stream 组成拆分（对标 DBI PFD stream table）。"""

from __future__ import annotations

from typing import Dict, Mapping

from .parameters import DBI_O2IN_MOL_PCT, DEFAULT_CHEMISTRY_SETUP, MOLECULAR_WEIGHT

GAS_SPECIES_MW = {k: MOLECULAR_WEIGHT[k] for k in ("O2", "N2", "Ar", "CO2", "H2O")}


def split_gas_stream_mass_kg_h(total_kg_h: float, mol_pct: Mapping[str, float]) -> Dict[str, float]:
    """由 stream 总质量 (kg/h) 与 mol% 组成拆分到各物种质量。"""
    if total_kg_h <= 0.0:
        return {k: 0.0 for k in mol_pct}
    avg_mw = sum(float(mol_pct[k]) / 100.0 * GAS_SPECIES_MW[k] for k in mol_pct)
    n_mol_h = total_kg_h / avg_mw * 1000.0
    return {k: n_mol_h * float(mol_pct[k]) / 100.0 * GAS_SPECIES_MW[k] / 1000.0 for k in mol_pct}


def o2in_mol_pct_from_chem(chem: Mapping[str, str]) -> Dict[str, float]:
    return {
        "O2": float(chem.get("O2IN O2 mol%", str(DEFAULT_CHEMISTRY_SETUP["O2IN O2 mol%"]))),
        "N2": float(chem.get("O2IN N2 mol%", str(DEFAULT_CHEMISTRY_SETUP["O2IN N2 mol%"]))),
        "Ar": float(chem.get("O2IN Ar mol%", str(DEFAULT_CHEMISTRY_SETUP["O2IN Ar mol%"]))),
    }


def inci_o2_stream_species_kg_h(o2in_total_kg_h: float, chem: Mapping[str, str]) -> Dict[str, float]:
    """O2IN = 13OG2-1 全流股质量 (kg/h)，按 mol% 拆分。"""
    return split_gas_stream_mass_kg_h(o2in_total_kg_h, o2in_mol_pct_from_chem(chem))
